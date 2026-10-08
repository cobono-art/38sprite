"""방향별 H3 프레임 → 스프라이트 시트.

반복 동작: 방향마다 루프 한 바퀴를 찾고, 머리가 가장 낮은 순간(두 발 딛는 자세)을 시작으로 맞춘다.
한 번 하는 동작: 첫 자세에서 벗어났다 돌아오는 구간을 잘라, 가장 크게 움직인 순간(타격)이 꼭 들어가게 고른다.
모든 방향을 같은 칸 크기·같은 발 위치로 자르고, 만들지 않은 방향은 반대쪽을 좌우 반전해서 채운다.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image

from .comfy import FPS
from .directions import SHEET_ORDER, preview_layout, source_of
from .effects import remove_effects
from .imaging import (bbox, cutout_any, estimate_bg, frame_alpha, find_cycle, load_frames, pixelate, save_gif,
                      thumbnails)


def pick_loop(frames, alphas, n):
    th = thumbnails(frames, alphas)
    period, start, seam, scores = find_cycle(th, 14, 60)
    doubled = False
    # 망토·치마로 다리가 가려지면 한 걸음이 한 바퀴처럼 보인다. 두 배 간격(두 걸음)이 확실히 더 잘 맞으면
    # 그쪽이 진짜 한 바퀴다 (그대로 두면 같은 발로만 걷는다).
    near = [k for k in range(2 * period - 2, 2 * period + 3) if k in scores]
    if near and min(scores[k] for k in near) < 0.95 * scores[period]:
        period, start, seam, _ = find_cycle(th, 2 * period - 2, 2 * period + 2)
        doubled = True
    head_y = [bbox(alphas[i])[1] for i in range(start, start + period)]
    phase = int(np.argmax(head_y))
    n = min(n, period)
    picks = [start + (phase + round(i * period / n)) % period for i in range(n)]
    return picks, n * FPS / period, {"period_frames": period, "period_sec": round(period / FPS, 2),
                                     "loop_start": start, "phase_offset": phase, "seam_error": round(seam, 4),
                                     "half_step_fixed": doubled}


def motion_signal(alphas):
    """방향이 달라도 비슷하게 움직이는 신호: 실루엣 위쪽 30%에 든 양(팔을 머리 위로 드는 정도)과 실루엣 넓이.
    (실루엣 너비는 옆모습에서 팔을 벌려도 거의 안 변해서 쓰지 않는다)"""
    upper, area = [], []
    for a in alphas:
        x0, y0, x1, y1 = bbox(a)
        solid = a > 0.5
        upper.append(float(solid[int(y0):int(y0 + (y1 - y0) * 0.3)].sum()))
        area.append(float(solid.sum()))
    sig = np.stack([np.asarray(upper), np.asarray(area)], axis=1)
    return (sig - sig.mean(axis=0)) / (sig.std(axis=0) + 1e-6)


def best_lag(sig, ref, max_lag=10):
    """sig가 ref보다 몇 프레임 늦은지 (상관이 가장 큰 어긋남)."""
    n = min(len(sig), len(ref))
    best, lag_best = -1e9, 0
    for lag in range(-max_lag, max_lag + 1):
        a = ref[max(0, -lag):n - max(0, lag)]
        b = sig[max(0, lag):n - max(0, -lag)]
        if len(a) < 24:
            continue
        c = float((a * b).sum() / len(a))
        if c > best:
            best, lag_best = c, lag
    return lag_best


def oneshot_window(frames, alphas):
    """첫 자세에서 벗어났다 돌아오는 구간과 가장 크게 달라진 순간 (시작, 끝, 타격) 프레임."""
    th = thumbnails(frames, alphas)
    diff = np.abs(th - th[0]).mean(axis=1)          # 첫 자세와 얼마나 다른지
    active = np.where(diff > max(0.004, 0.2 * diff.max()))[0]
    start, end = (0, len(frames) - 1) if len(active) == 0 else (
        max(0, int(active[0]) - 2), min(len(frames) - 1, int(active[-1]) + 2))
    return start, end, int(np.argmax(diff))


def pick_oneshot(frames, alphas, n, window=None):
    """window를 주면 모든 방향이 같은 구간·같은 타격 프레임을 쓴다 (마네킹·마스터처럼 같은 박자를 따를 때)."""
    start, end, peak = window or oneshot_window(frames, alphas)
    end = min(end, len(frames) - 1)
    span = max(1, end - start)
    picks = [start + round(i * span / (n - 1)) for i in range(n)] if n > 1 else [start]
    if peak not in picks and start <= peak <= end:  # 타격 순간을 가장 가까운 칸에 넣는다
        j = int(np.argmin([abs(p - peak) for p in picks]))
        picks[j] = peak
        picks = sorted(set(picks))
    return picks, (len(picks) - 1) * FPS / span, {"action_start": start, "action_end": end,
                                                  "action_sec": round(span / FPS, 2), "peak_frame": peak,
                                                  "shared_window": window is not None}


def analyze_direction(frames_dir, kind, n_frames, strip_effects=False, window=None, override=None, loop=None):
    """override: {칸 번호: 영상 프레임 번호} — 사람이 '다른 장면으로 바꾸기'로 고른 프레임.
    loop: 기준 방향에서 고른 반복 구간 (picks, fps, rep) — 모든 방향이 같은 영상 박자를 따를 때 같은 프레임을 쓴다."""
    frames = load_frames(frames_dir)
    # 배경색은 프레임마다 잰다 (H3가 가끔 영상 중간에 배경색을 바꾼다)
    bgs = [estimate_bg(f) for f in frames]
    bg = bgs[0]
    alphas = [frame_alpha(f, b) for f, b in zip(frames, bgs)]
    if kind == "loop" and loop:
        lag = best_lag(motion_signal(alphas), loop[3])            # 같은 영상을 따라도 방향마다 몇 프레임씩 밀린다
        picks = [max(0, min(len(frames) - 1, p + lag)) for p in loop[0]]
        fps, rep = loop[1], dict(loop[2], shared_loop=True, lag_frames=lag)
    else:
        picks, fps, rep = (pick_loop(frames, alphas, n_frames) if kind == "loop"
                           else pick_oneshot(frames, alphas, n_frames, window))
    for k, fi in (override or {}).items():
        if 0 <= int(k) < len(picks):
            picks[int(k)] = max(0, min(len(frames) - 1, int(fi)))
    cx = [float(np.average(np.arange(a.shape[1]), weights=a.sum(axis=0) + 1e-6)) for a in alphas]
    rep["picked"] = picks
    rep["drift_x_px"] = round(max(cx) - min(cx), 1)
    rep["frames_touching_edge"] = sum(int(max(a[0].max(), a[-1].max(), a[:, 0].max(), a[:, -1].max()) > 0.5)
                                      for a in alphas)
    rgba = [cutout_any(frames[i], alphas[i], bgs[i]) for i in picks]
    if strip_effects:
        first = cutout_any(frames[0], alphas[0], bg)                         # 첫 프레임 = 캐릭터 원래 색
        rgba, removed = remove_effects(rgba, first, alphas, picks, bg)
        rep["effect_px_removed"] = removed
    boxes = [bbox(im[..., 3] / 255.0) if im[..., 3].any() else bbox(alphas[i]) for im, i in zip(rgba, picks)]
    return {"rgba": rgba, "boxes": boxes, "fps": fps, "report": rep}


def write_sheet(rows, order, fps, pivot, out_dir, name, loop):
    h, w = rows[order[0]][0].shape[:2]
    n = len(rows[order[0]])
    sheet = np.zeros((h * len(order), w * n, 4), np.uint8)
    dirs = {}
    for r, d in enumerate(order):
        dirs[d] = []
        for i, im in enumerate(rows[d]):
            sheet[r * h:(r + 1) * h, i * w:(i + 1) * w] = im
            dirs[d].append({"x": i * w, "y": r * h, "w": w, "h": h})
    Image.fromarray(sheet).save(Path(out_dir) / f"{name}.png")
    meta = {"image": f"{name}.png", "frame_w": w, "frame_h": h, "fps": round(fps, 2),
            "pivot": [round(pivot[0], 1), round(pivot[1], 1)], "loop": loop, "order": order, "directions": dirs}
    (Path(out_dir) / f"{name}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


GIF_STYLE = {"hd": {"gap": 8, "scale": 1}, "px": {"gap": 4, "scale": 3}}


def write_gifs(rows, order, count, fps, out_dir, res):
    """미리보기 GIF(나침반 배치)와 방향별 투명 GIF (다른 곳에 바로 얹어 쓰기 좋게)."""
    st = GIF_STYLE[res]
    save_gif(layout_frames(rows, count, gap=st["gap"]), fps, Path(out_dir) / f"preview_{res}.gif", scale=st["scale"])
    for d in order:
        save_gif(rows[d], fps, Path(out_dir) / f"{res}_{d}.gif", scale=st["scale"], transparent=True)


def retime(out_dir, count, fps):
    """후처리: 다 만든 시트의 재생 속도만 바꾼다. 시트 그림은 그대로 두고 JSON의 fps와 GIF만 다시 쓴다."""
    out_dir = Path(out_dir)
    for res in GIF_STYLE:
        meta_path = out_dir / f"sheet_{res}.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        sheet = np.asarray(Image.open(out_dir / meta["image"]).convert("RGBA"))
        rows = {d: [np.ascontiguousarray(sheet[r["y"]:r["y"] + r["h"], r["x"]:r["x"] + r["w"]]) for r in rects]
                for d, rects in meta["directions"].items()}
        meta["fps"] = round(fps, 2)
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        write_gifs(rows, meta["order"], count, fps, out_dir, res)


def layout_frames(rows, count, gap=8):
    """방향별 프레임을 미리보기 배치로 합친다 (8방향은 나침반, 4방향은 십자, 2방향은 좌우)."""
    grid = preview_layout(count)
    h, w = next(iter(rows.values()))[0].shape[:2]
    n = len(next(iter(rows.values())))
    R, C = len(grid), len(grid[0])
    out = []
    for i in range(n):
        canvas = np.zeros((R * h + (R - 1) * gap, C * w + (C - 1) * gap, 4), np.uint8)
        for r, line in enumerate(grid):
            for c, d in enumerate(line):
                if d and d in rows:
                    canvas[r * (h + gap):r * (h + gap) + h, c * (w + gap):c * (w + gap) + w] = rows[d][i]
        out.append(canvas)
    return out


def assemble(dir_folders, count, size, feet_y, out_dir, kind="loop", n_frames=8, hd_height=256,
             pixel_height=0, colors=20, smooth=24, palette_refs=None, strip_effects=False,
             window=None, window_from=None, char_px=None, hd_char=200, overrides=None, loop_from=None):
    """dir_folders: {만든 방향: 그 방향 PNG 프레임 폴더}. 시트·GIF·report.json을 out_dir에 쓴다.
    한 번 하는 동작에서 window(시작, 끝, 타격 프레임)나 window_from(기준 방향)을 주면 모든 방향을 같은 구간으로 자른다.
    반복 동작에서 loop_from(기준 방향)을 주면 그 방향에서 찾은 반복 구간을 모든 방향에 똑같이 쓴다
    (레퍼런스 영상·마네킹처럼 모든 방향이 같은 박자를 따를 때 — 방향마다 따로 찾으면 춤 박자가 어긋난다).
    char_px(영상 속 캐릭터 키)를 주면 캐릭터 키를 HD는 hd_char, 픽셀은 pixel_height로 맞춘다. 모든 동작에서 캐릭터
    크기가 같아서 게임에서 동작이 바뀌어도 그대로다 (칼을 크게 휘두르는 동작은 칸만 커진다).
    없으면 예전처럼 칸 높이를 hd_height·pixel_height로 맞춘다."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    order = SHEET_ORDER[count]
    if kind != "loop" and window is None and window_from in dir_folders:
        frames = load_frames(dir_folders[window_from])
        window = oneshot_window(frames, [frame_alpha(f, estimate_bg(f)) for f in frames])
    shared = None
    if kind == "loop":
        window = None
        if loop_from in dir_folders:
            frames = load_frames(dir_folders[loop_from])
            al = [frame_alpha(f, estimate_bg(f)) for f in frames]
            shared = (*pick_loop(frames, al, n_frames), motion_signal(al))
    overrides = overrides or {}
    done = {d: analyze_direction(folder, kind, n_frames, strip_effects, window, overrides.get(d), shared)
            for d, folder in dir_folders.items()}

    # 공통 칸: 가로는 화면 중앙 기준 좌우 대칭(반전해도 피벗이 그대로), 세로는 전체 합집합
    W, H = size
    boxes = [b for r in done.values() for b in r["boxes"]]
    pad = round(0.03 * H)
    half_w = max(max(W / 2 - b[0], b[2] - W / 2) for b in boxes) + pad
    x0, x1 = max(0, round(W / 2 - half_w)), min(W, round(W / 2 + half_w))
    y0 = max(0, int(min(b[1] for b in boxes)) - pad)
    y1 = min(H, int(max(max(b[3] for b in boxes), feet_y)) + pad)

    n = min(len(r["rgba"]) for r in done.values())
    rows, sources = {}, {}
    for d in order:
        src, flip = source_of(d, list(done))
        ims = [im[y0:y1, x0:x1] for im in done[src]["rgba"][:n]]
        rows[d] = [np.ascontiguousarray(im[:, ::-1] if flip else im) for im in ims]
        sources[d] = f"{src} 반전" if flip else "생성"

    loop = kind == "loop"
    fps = float(np.mean([r["fps"] for r in done.values()]))
    pivot = (W / 2 - x0, feet_y - y0)
    s = hd_char / char_px if char_px else hd_height / (y1 - y0)
    hd = {d: [np.asarray(Image.fromarray(im).resize((round(im.shape[1] * s), round(im.shape[0] * s)), Image.LANCZOS))
              for im in rows[d]] for d in order}
    write_sheet(hd, order, fps, (pivot[0] * s, pivot[1] * s), out_dir, "sheet_hd", loop)
    write_gifs(hd, order, count, fps, out_dir, "hd")

    if pixel_height:
        flat = [im for d in order for im in rows[d]]
        ps = pixel_height / char_px if char_px else pixel_height / (y1 - y0)
        px, _ = pixelate(flat, max(1, round((y1 - y0) * ps)), colors, palette_ref=palette_refs, smooth=smooth)
        prow = {d: px[k * n:(k + 1) * n] for k, d in enumerate(order)}
        write_sheet(prow, order, fps, (pivot[0] * ps, pivot[1] * ps), out_dir, "sheet_px", loop)
        write_gifs(prow, order, count, fps, out_dir, "px")

    report = {"kind": kind, "count": count, "order": order, "frames": n, "sprite_fps": round(fps, 2),
              "cell_crop": [x0, y0, x1, y1], "char_px": round(char_px, 1) if char_px else None, "sources": sources,
              "directions": {d: r["report"] for d, r in done.items()}}
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
