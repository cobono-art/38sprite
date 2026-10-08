"""이미지 처리 공용 함수: 배경 제거, 루프 찾기, 픽셀아트 마감, 시트·GIF 저장."""
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw


def load_frames(folder):
    files = sorted(Path(folder).glob("*.png"))
    if not files:
        raise FileNotFoundError(f"no PNG frames in {folder}")
    return [np.asarray(Image.open(p).convert("RGB")) for p in files]


def estimate_bg(frame):
    border = np.concatenate([frame[0], frame[-1], frame[:, 0], frame[:, -1]])
    return np.median(border, axis=0)


def alpha_mask(frame, bg, lo, hi):
    """배경색과 가까우면서 화면 테두리와 이어진 영역만 배경으로 보고 지운다 (캐릭터 안쪽 회색은 보존)."""
    dist = np.linalg.norm(frame.astype(np.float32) - bg, axis=2)
    near_bg = (dist < hi).astype(np.uint8)
    _, labels = cv2.connectedComponents(near_bg, connectivity=4)
    edge = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    bg_region = np.isin(labels, edge[edge != 0])

    a = np.ones(dist.shape, np.float32)
    soft = np.clip((dist - lo) / (hi - lo), 0, 1)
    a[bg_region] = soft[bg_region]

    # 떨어진 작은 얼룩 제거 (큰 덩어리 주변만 남김)
    solid = (a > 0.5).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(solid, connectivity=8)
    if n > 1:
        areas = stats[1:, cv2.CC_STAT_AREA]
        keep = 1 + np.where(areas >= max(50, areas.max() * 0.02))[0]
        keep_mask = cv2.dilate(np.isin(lab, keep).astype(np.uint8), np.ones((5, 5), np.uint8))
        a[keep_mask == 0] = 0
    return a


def decontaminate(frame, a, bg):
    """반투명 테두리에 섞인 배경색을 빼서 원래 색을 복원한다."""
    f = frame.astype(np.float32)
    safe = np.maximum(a, 0.05)[..., None]
    out = (f - (1 - a[..., None]) * bg) / safe
    return np.clip(np.where(a[..., None] > 0.05, out, f), 0, 255).astype(np.uint8)


def refine_edges(frame, a, bg, width=2):
    """바깥 테두리 width픽셀을 다시 푼다: 각 픽셀이 배경색과 바로 안쪽 캐릭터 색 사이 어디쯤인지로 투명도를 정하고,
    색은 안쪽 색을 쓴다. H3 영상에서 진한 외곽선 바깥에 남는 회색·밝은 번짐(어두운 배경에서 하얀 테두리로 보임)은
    투명해지고, 칼날처럼 안쪽도 밝은 곳은 그대로 남는다. (rgb, alpha)를 돌려준다."""
    f = frame.astype(np.float32)
    bgv = np.asarray(bg, np.float32)
    solid = (a > 0.5).astype(np.uint8)
    inner = cv2.erode(solid, np.ones((3, 3), np.uint8), iterations=width)
    band = (solid > 0) & (inner == 0)
    sig = width + 0.8
    w = cv2.GaussianBlur(inner.astype(np.float32), (0, 0), sig)
    fg = cv2.GaussianBlur(f * inner[..., None], (0, 0), sig) / np.maximum(w, 1e-4)[..., None]
    d = fg - bgv
    t = ((f - bgv) * d).sum(axis=2) / np.maximum((d * d).sum(axis=2), 1.0)
    ok = band & (w > 0.02) & ((d * d).sum(axis=2) > 400)       # 안쪽 색이 배경과 충분히 다를 때만
    a2 = a.copy()
    a2[ok] = np.minimum(a[ok], np.clip(t[ok], 0, 1))
    rgb = f.copy()
    rgb[ok] = fg[ok]
    return np.clip(rgb, 0, 255).astype(np.uint8), a2


KEY_MAGENTA = (255, 0, 255)


def key_alpha(frame, key=KEY_MAGENTA, lo=0.2, hi=0.6):
    """마젠타 크로마키 배경의 알파. 마젠타 기운(min(R,B)-G)을 배경의 값으로 나눈 비율이 lo 아래면 캐릭터(빨강·피부·
    베이지도 여기), hi 위면 배경, 사이는 반투명. 캐릭터에 비친 옅은 분홍빛은 lo 아래라 불투명으로 남고 despill이 지운다."""
    f = frame.astype(np.float32) / 255
    m = keyness(f, is_green_bg(key))
    border = np.concatenate([m[0], m[-1], m[:, 0], m[:, -1]])
    mk = max(0.2, float(np.median(border)))
    a = 1 - np.clip((m / mk - lo) / (hi - lo), 0, 1)
    solid = (a > 0.5).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(solid, connectivity=8)
    if n > 1:                                   # 떨어진 작은 얼룩은 버린다
        areas = stats[1:, cv2.CC_STAT_AREA]
        keep = 1 + np.where(areas >= max(30, areas.max() * 0.002))[0]
        near = cv2.dilate(np.isin(lab, keep).astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
        a[~near] = 0
    return a


def keyness(f, green=False):
    """크로마키 기운: 마젠타는 min(R,B)-G, 초록은 G-max(R,B). (H3가 영상 중간에 배경을 초록 크로마키로 바꾸기도 한다)"""
    if green:
        return f[..., 1] - np.maximum(f[..., 0], f[..., 2])
    return np.minimum(f[..., 0], f[..., 2]) - f[..., 1]


def despill_green(rgb):
    """초록 스필 제거: G가 R·B 중 큰 값보다 높은 만큼만 깎는다."""
    f = rgb.astype(np.float32)
    s = np.clip(f[..., 1] - np.maximum(f[..., 0], f[..., 2]), 0, None)
    f[..., 1] -= s
    return np.clip(f, 0, 255).astype(np.uint8)


def is_green_bg(bg):
    r, g, b = [float(v) for v in bg]
    return g - max(r, b) > 50                 # 민트빛 초록까지


def despill_magenta(rgb):
    """마젠타 스필 제거: R·B가 G보다 높은 만큼(분홍 기운)만 깎는다. 깎아도 G 아래로는 안 내려가서 초록이 생기지 않는다."""
    f = rgb.astype(np.float32)
    s = np.clip(np.minimum(f[..., 0], f[..., 2]) - f[..., 1], 0, None)
    f[..., 0] -= s
    f[..., 2] -= s
    return np.clip(f, 0, 255).astype(np.uint8)


def is_key_bg(bg):
    """배경이 크로마키 색(마젠타, 또는 H3가 바꿔 버린 초록)인지 (회색 배경이면 아니다)."""
    r, g, b = [float(v) for v in bg]
    return min(r, b) - g > 80 or is_green_bg(bg)


def cutout_key(frame, key=None, a=None):
    """크로마키 배경의 RGBA: 알파는 마젠타 비율로, 바깥 테두리는 안쪽 색으로 풀고, 남은 분홍 기운은 despill."""
    key = estimate_bg(frame) if key is None else np.asarray(key, np.float32)
    a = key_alpha(frame, key) if a is None else a
    rgb, a2 = refine_edges(frame, a, key)
    return to_rgba((despill_green if is_green_bg(key) else despill_magenta)(rgb), a2)


def cutout_rgba(frame, a, bg):
    """배경을 지운 RGBA: 반투명 테두리의 배경색을 빼고, 바깥 테두리의 번짐을 정리한다."""
    rgb, a2 = refine_edges(decontaminate(frame, a, bg), a, bg)
    return to_rgba(rgb, a2)


def frame_alpha(frame, bg):
    """배경에 맞는 알파: 마젠타 같은 크로마키면 크로마키로, 회색이면 예전 방식(테두리와 이어진 배경색)으로."""
    return key_alpha(frame, bg) if is_key_bg(bg) else alpha_mask(frame, bg, 12, 40)


def cutout_any(frame, a, bg):
    return cutout_key(frame, bg, a) if is_key_bg(bg) else cutout_rgba(frame, a, bg)


def sheet_alpha(crop, bg, hole_dist=5, min_hole=40, flat=2.5):
    """Codex 방향 그림(단색 회색 배경)용 알파: 테두리와 이어진 배경에 더해, 팔과 몸 사이처럼 막힌 틈의
    배경색도 지운다. 그림 배경은 완전히 단색이라, 배경색과 거의 똑같고(hole_dist) 얼룩 없이 평평한(flat)
    덩어리만 틈으로 본다 — 은색 갑옷처럼 회색이어도 결이 있는 부분은 지우지 않는다."""
    a = alpha_mask(crop, bg, 12, 40)
    dist = np.linalg.norm(crop.astype(np.float32) - np.asarray(bg, np.float32), axis=2)
    holes = ((dist < hole_dist) & (a > 0.5)).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(holes, connectivity=4)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_hole:
            region = lab == i
            if float(dist[region].mean()) < flat:
                a[region] = 0
    return a


def thumbnails(frames, alphas, size=(48, 64)):
    out = []
    for f, a in zip(frames, alphas):
        g = cv2.cvtColor(f, cv2.COLOR_RGB2GRAY).astype(np.float32) * a + 255 * (1 - a)
        out.append(cv2.resize(g, size, interpolation=cv2.INTER_AREA).ravel() / 255.0)
    return np.stack(out)


def find_cycle(th, min_p, max_p, tol=1.15):
    """프레임 t와 t+p가 비슷한 주기 p와, 그 주기로 잘랐을 때 이음새가 가장 매끄러운 시작점을 찾는다.

    정면·뒷모습은 좌우 대칭이라 세 걸음 뒤(반대 발이 앞)도 처음과 비슷해 보인다. 그래서 점수가 최저점의
    tol배 이내인 골(local minimum) 중 가장 짧은 주기를 고른다 (= 두 걸음, 진짜 한 바퀴)."""
    curve = {}
    for p in range(min_p, min(max_p, len(th) - 1) + 1):
        curve[p] = np.mean(np.abs(th[:-p] - th[p:]), axis=1)
    score = {k: float(v.mean()) for k, v in curve.items()}
    ps = sorted(score)
    best = min(score.values())
    valleys = [p for i, p in enumerate(ps[1:-1], 1)
               if score[p] <= score[ps[i - 1]] and score[p] <= score[ps[i + 1]] and score[p] <= best * tol]
    p = min(valleys) if valleys else min(score, key=score.get)
    s = int(np.argmin(curve[p]))
    return p, s, float(curve[p][s]), {k: round(v, 4) for k, v in score.items()}


def bbox(a, thresh=0.1):
    ys, xs = np.where(a > thresh)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def load_ref(path):
    """단색 배경 원화를 잘라 RGBA로 돌려준다 (팔레트 기준용)."""
    f = np.asarray(Image.open(path).convert("RGB"))
    bg = estimate_bg(f)
    a = alpha_mask(f, bg, 12, 40)
    x0, y0, x1, y1 = bbox(a)
    return to_rgba(decontaminate(f, a, bg), a)[y0:y1, x0:x1]


def to_rgba(frame, a):
    alpha = (a * 255).round().astype(np.uint8)
    return np.dstack([np.where(alpha[..., None] > 0, frame, 0), alpha])


def majority_clean(q, a, k, protect, min_votes=6):
    """주변 8칸 중 min_votes칸 이상이 같은 색인데 혼자 다른 픽셀을 그 색으로 바꾼다 (면 안의 잡티 정리).
    색 경계에서는 이웃 표가 갈리므로 형태는 유지된다. protect(눈·선 같은 색)는 건드리지 않는다."""
    H, W = q.shape
    pad_q, pad_a = np.pad(q, 1, mode="edge"), np.pad(a, 1)
    votes = np.zeros((H, W, k), np.int16)
    eye = np.eye(k, dtype=np.int16)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                votes += eye[pad_q[1 + dy:H + 1 + dy, 1 + dx:W + 1 + dx]] * pad_a[1 + dy:H + 1 + dy, 1 + dx:W + 1 + dx, None]
    top = votes.argmax(-1)
    change = a & (votes.max(-1) >= min_votes) & (top != q) & ~protect[q]
    return np.where(change, top, q)


def pixelate(rgba_frames, height, colors, cluster=4, outline=True, palette_ref=None,
             dark_share=0.40, dark_luma=70, smooth=0, majority=True):
    """픽셀아트 마감: 공유 팔레트로 먼저 색을 정한 뒤, cluster x cluster 칸마다 가장 많은 색을 골라 줄인다
    (평균을 내지 않아 섞인 중간색이 생기지 않음). 칸 안에 어두운 색(밝기 dark_luma 미만, 눈·선)이
    dark_share 이상이면 그 색을 살린다 (sprite-gen의 detail bias와 같은 기준).
    palette_ref(원화 RGBA 목록)를 주면 팔레트를 원화에서 뽑아, 영상에서 바뀐 색을 원래 색으로 되돌린다.
    smooth>0이면 줄이기 전에 색 경계를 살리는 평탄화(mean shift, 색 반경 smooth)로 질감 잡티를 없앤다.
    다수결로 면 안의 잡티를 정리하고, 실루엣에 1px 외곽선을 두른다."""
    h0, w0 = rgba_frames[0].shape[:2]
    width = max(1, round(w0 * height / h0))
    big_w, big_h = width * cluster, height * cluster
    if smooth:
        rgba_frames = [np.dstack([cv2.pyrMeanShiftFiltering(np.ascontiguousarray(im[..., :3]), 6, smooth), im[..., 3]])
                       for im in rgba_frames]

    def shrink(im, size, cut=0.5):
        f = im.astype(np.float32) / 255
        premul = np.dstack([f[..., :3] * f[..., 3:4], f[..., 3]])
        rs = cv2.resize(premul, size, interpolation=cv2.INTER_AREA)
        alpha = rs[..., 3]
        return np.clip(rs[..., :3] / np.maximum(alpha, 1e-4)[..., None], 0, 1) * 255, alpha > cut

    mids = [shrink(im, (big_w, big_h)) for im in rgba_frames]

    # 모든 프레임이 같은 팔레트를 쓰게 (방향·프레임 사이 색 튐 방지)
    if palette_ref:
        # 원화는 완전히 불투명한 픽셀만 (테두리의 배경색 섞인 픽셀이 팔레트에 들어가지 않게)
        refs = [shrink(r, (max(1, round(r.shape[1] * big_h / r.shape[0])), big_h), cut=0.98) for r in palette_ref]
        opaque = np.concatenate([rgb[m] for rgb, m in refs]).astype(np.float32)
    else:
        opaque = np.concatenate([rgb[m] for rgb, m in mids]).astype(np.float32)
    k = min(colors, len(opaque))
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.5)
    _, _, centers = cv2.kmeans(opaque, k, None, crit, 4, cv2.KMEANS_PP_CENTERS)
    palette = centers.round().clip(0, 255).astype(np.uint8)
    pal_f = palette.astype(np.float32)
    luma = palette.astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    dark = luma < dark_luma                         # 눈·선 같은 어두운 색은 살리고, 정리 대상에서 뺀다

    out = []
    for rgb, m in mids:
        idx = np.argmin(((rgb[..., None, :] - pal_f) ** 2).sum(-1), axis=-1)
        blocks = idx.reshape(height, cluster, width, cluster).transpose(0, 2, 1, 3).reshape(height, width, -1)
        solid = m.reshape(height, cluster, width, cluster).transpose(0, 2, 1, 3).reshape(height, width, -1)
        counts = np.zeros((height, width, k), np.int32)
        for c in range(cluster * cluster):
            counts += np.eye(k, dtype=np.int32)[blocks[..., c]] * solid[..., c, None]
        q = counts.argmax(-1)
        dark_counts = np.where(dark, counts, 0)
        keep_dark = dark_counts.sum(-1) >= max(2, dark_share * cluster * cluster)
        q = np.where(keep_dark, dark_counts.argmax(-1), q)
        a = solid.mean(-1) >= 0.5

        # 외톨이 픽셀: 상하좌우 이웃이 모두 불투명하고 모두 나와 다른 색이면 이웃 중 많은 색으로
        pad_q = np.pad(q, 1, mode="edge")
        pad_a = np.pad(a, 1)
        nb = np.stack([pad_q[:-2, 1:-1], pad_q[2:, 1:-1], pad_q[1:-1, :-2], pad_q[1:-1, 2:]], -1)
        nb_a = np.stack([pad_a[:-2, 1:-1], pad_a[2:, 1:-1], pad_a[1:-1, :-2], pad_a[1:-1, 2:]], -1).all(-1)
        lone = a & nb_a & (nb != q[..., None]).all(-1) & ~dark[q]
        if lone.any():
            votes = np.zeros((height, width, k), np.int32)
            for j in range(4):
                votes += np.eye(k, dtype=np.int32)[nb[..., j]]
            q = np.where(lone, votes.argmax(-1), q)
        if majority:
            q = majority_clean(q, a, k, dark)

        img = np.dstack([palette[q], (a * 255).astype(np.uint8)])
        if outline:
            # 실루엣 바깥 1px에 맞닿은 색을 어둡게 한 외곽선
            ring = cv2.dilate(a.astype(np.uint8), np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], np.uint8)).astype(bool) & ~a
            src = np.zeros_like(img[..., :3], dtype=np.float32)
            cnt = np.zeros((height, width, 1), np.float32)
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                sh_a = np.roll(a, (dy, dx), (0, 1))[..., None]
                src += np.roll(img[..., :3], (dy, dx), (0, 1)).astype(np.float32) * sh_a
                cnt += sh_a
            line = (src / np.maximum(cnt, 1) * 0.35).astype(np.uint8)
            img[ring, :3] = line[ring]
            img[ring, 3] = 255
        out.append(img)
    return out, palette


def save_sheet(frames_rgba, fps, pivot, direction, out_dir, name):
    h, w = frames_rgba[0].shape[:2]
    sheet = np.zeros((h, w * len(frames_rgba), 4), np.uint8)
    rects = []
    for i, im in enumerate(frames_rgba):
        sheet[:, i * w:(i + 1) * w] = im
        rects.append({"x": i * w, "y": 0, "w": w, "h": h})
    Image.fromarray(sheet).save(out_dir / f"{name}.png")
    meta = {"image": f"{name}.png", "frame_w": w, "frame_h": h, "fps": round(fps, 2),
            "pivot": [round(pivot[0], 1), round(pivot[1], 1)], "loop": True,
            "directions": {direction: rects}}
    (out_dir / f"{name}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def save_gif(frames_rgba, fps, path, scale=1, bg=(48, 52, 60), transparent=False):
    """transparent=True면 배경을 투명하게 (GIF는 반투명이 없어서 알파 50% 기준으로 자른다)."""
    imgs = []
    for im in frames_rgba:
        rgba = Image.fromarray(im)
        if scale != 1:
            rgba = rgba.resize((rgba.width * scale, rgba.height * scale), Image.NEAREST)
        if transparent:
            key = (255, 0, 255)
            arr = np.asarray(rgba).copy()
            hole = arr[..., 3] < 128
            arr[hole, :3] = key
            pal = Image.fromarray(arr[..., :3]).quantize(255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
            idx = np.asarray(pal).copy()
            idx[hole] = 255                            # 투명 전용 칸 (색은 0~254만 씀)
            out = Image.fromarray(idx.astype(np.uint8), "P")
            out.putpalette((pal.getpalette() + [0] * 768)[:765] + list(key))
            out.info["transparency"] = 255
            imgs.append(out)
        else:
            base = Image.new("RGBA", rgba.size, bg + (255,))
            base.alpha_composite(rgba)
            imgs.append(base.convert("RGB"))
    extra = {"transparency": 255, "disposal": 2} if transparent else {}
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=round(1000 / fps), loop=0, **extra)


def contact_sheet(frames, path, cols=8, every=None, scale=0.25):
    every = every or max(1, len(frames) // 24)
    idx = list(range(0, len(frames), every))
    th = [Image.fromarray(frames[i]).resize((round(frames[i].shape[1] * scale), round(frames[i].shape[0] * scale)))
          for i in idx]
    w, h = th[0].size
    rows = (len(th) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), (30, 30, 30))
    draw = ImageDraw.Draw(sheet)
    for n, (i, im) in enumerate(zip(idx, th)):
        x, y = (n % cols) * w, (n // cols) * h
        sheet.paste(im, (x, y))
        draw.text((x + 4, y + 2), str(i), fill=(255, 40, 40))
    sheet.save(path)


def frames_to_webp(frames_dir, out, scale=0.5, fps=24, quality=72):
    """PNG 프레임 폴더를 미리보기용 애니메이션 WebP로 묶는다."""
    files = sorted(Path(frames_dir).glob("*.png"))
    frames = []
    for p in files:
        im = Image.open(p).convert("RGB")
        if scale != 1:
            im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        frames.append(im)
    frames[0].save(out, save_all=True, append_images=frames[1:], duration=round(1000 / fps), loop=0,
                   quality=quality, method=4)
    return Path(out)
