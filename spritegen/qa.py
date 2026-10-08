"""자동 점검: 다 만든 시트에서 흔한 결함을 찾아 report.json의 "qa"에 적는다 (화면에서 경고로 보여 준다).

- hole: 다른 장에서는 꽉 차 있는 자리가 이 장에서만 뚫림 (배경 지우기가 옷·갑옷을 배경으로 착각)
- fringe: 가장자리에 마젠타(분홍)·초록 배경색이 번짐 (캐릭터 안쪽에도 그 색이 많으면 원래 색으로 본다)
- pink: 첫 장에 없던 분홍빛 효과가 생김 (영상 AI가 그리지 말라고 한 분홍 효과를 그림)
- shadow: 발밑에 회색 바닥 그림자가 남음
- seam: 반복 동작의 마지막 장 → 첫 장이 다른 장 사이보다 크게 튐
- edge: 영상 속 캐릭터가 화면 가장자리에 닿음 (칼끝·발이 잘렸을 수 있음)
- size: 한 방향만 캐릭터 키가 크게 다름
- empty: 캐릭터가 거의 없는 장
만들지 않고 반전으로 채운 방향은 원래 방향과 같아서 점검하지 않는다.
"""
import cv2
import numpy as np

K3 = np.ones((3, 3), np.uint8)


LUMA = np.array([0.299, 0.587, 0.114], np.float32)


def _holes(frames):
    """캐릭터 안쪽에 막힌 투명 구멍 중 '옷감 한가운데가 뚫린' 것만 잡는다. 팔과 몸 사이·다리 사이처럼 원래 뚫린 틈은
    둘레가 캐릭터의 어두운 외곽선이고, 배경 지우기·효과 지우기가 낸 구멍은 밝은 옷감(흰 옷·금발)에 외곽선 없이 난다."""
    bad = []
    for i, f in enumerate(frames):
        m = f[..., 3] > 128
        area = int(m.sum())
        if area == 0:
            continue
        n, lab, stats, _ = cv2.connectedComponentsWithStats((~m).astype(np.uint8), connectivity=4)
        outside = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])).tolist())
        luma = f[..., :3].astype(np.float32) @ LUMA
        for k in range(1, n):
            if k in outside or stats[k, cv2.CC_STAT_AREA] < max(12, 0.001 * area):
                continue
            ring = (cv2.dilate((lab == k).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & m
            if ring.any() and (luma[ring] < 80).mean() < 0.15 and luma[ring].mean() > 150:
                bad.append(i)
                break
    return bad


def _magenta_green(rgb):
    r, g, b = (rgb[..., c].astype(np.int16) for c in range(3))
    return ((np.minimum(r, b) - g) > 60) | ((g - np.maximum(r, b)) > 60)


def _fringe(frames):
    bad = []
    for i, f in enumerate(frames):
        solid = (f[..., 3] > 128).astype(np.uint8)
        if not solid.any():
            continue
        band = (cv2.dilate(solid, K3) - cv2.erode(solid, K3) > 0) & (f[..., 3] > 20)
        inner = cv2.erode(solid, K3, iterations=3) > 0
        key = _magenta_green(f[..., :3])
        edge_share = key[band].mean() if band.any() else 0.0
        inner_share = key[inner].mean() if inner.any() else 0.0
        if edge_share > 0.04 and edge_share > 3 * inner_share + 0.02:
            bad.append(i)
    return bad


def _pink_share(f):
    solid = f[..., 3] > 128
    if not solid.any():
        return 0.0
    r, g, b = (f[..., c].astype(np.int16) for c in range(3))
    return float((((np.minimum(r, b) - g) > 50) & (r > 150) & solid).sum() / solid.sum())


def _pink(frames):
    """첫 장에 없던 분홍(마젠타)빛 덩어리. 배경이 마젠타라 분홍 효과는 그리지 말라고 해 두는데도 영상 AI가
    가끔 그린다 (지팡이 구슬이 분홍으로 빛나는 등). 첫 장보다 분홍이 캐릭터의 1% 넘게 늘어난 장을 잡는다."""
    base = _pink_share(frames[0])
    return [i for i, f in enumerate(frames) if _pink_share(f) > base + 0.01]


def _shadow(frames):
    """발밑의 회색 바닥 그림자 (그리지 말라고 해도 영상 AI가 가끔 그린다). 실루엣 맨 아래 6% 줄이 대부분
    채도 없는 중간 회색이면 신발이 아니라 그림자로 본다 (검은·갈색 신발은 걸리지 않는다)."""
    bad = []
    for i, f in enumerate(frames):
        a = f[..., 3] > 128
        ys = np.where(a.any(axis=1))[0]
        if not len(ys):
            continue
        y0 = max(0, ys[-1] - max(2, int(0.06 * (ys[-1] - ys[0]))))
        band = a[y0:ys[-1] + 1]
        rgb = f[y0:ys[-1] + 1, :, :3].astype(np.int16)
        mx, mn = rgb.max(axis=2), rgb.min(axis=2)
        gray = (mx - mn < 18) & (mx > 60) & (mx < 215) & band
        if band.sum() > 20 and gray.sum() > 0.5 * band.sum():
            bad.append(i)
    return bad


def _small(f, w=32):
    h = max(1, round(f.shape[0] * w / f.shape[1]))
    a = f[..., 3:4].astype(np.float32) / 255
    return cv2.resize(f[..., :3].astype(np.float32) * a, (w, h), interpolation=cv2.INTER_AREA) / 255


def _seam(frames):
    th = [_small(f) for f in frames]
    steps = [np.abs(th[i + 1] - th[i]).mean() for i in range(len(th) - 1)]
    jump = np.abs(th[0] - th[-1]).mean()
    return bool(steps) and jump > 0.01 and jump > 2.2 * float(np.median(steps))


def _height(f):
    ys = np.where((f[..., 3] > 128).any(axis=1))[0]
    return int(ys[-1] - ys[0] + 1) if len(ys) else 0


def check(rows, generated, kind, dir_reports, effects="none"):
    """rows: {방향: HD RGBA 프레임 목록}, generated: 실제로 만든 방향, dir_reports: assemble의 방향별 report.
    효과를 살린 동작(effects="vivid")은 빛줄기가 밝고 외곽선이 없고 화면 끝까지 뻗어서 구멍·잘림·크기·빈 칸은 보지 않는다."""
    issues = []
    vivid = effects == "vivid"
    dirs = [d for d in rows if d in generated]
    for d in dirs:
        frames = rows[d]
        areas = [int((f[..., 3] > 128).sum()) for f in frames]
        med = float(np.median(areas)) or 1.0
        empty = [] if vivid else [i for i, a in enumerate(areas) if a < 0.3 * med]
        holes = [] if vivid else _holes(frames)
        fringe = _fringe(frames)
        pink = _pink(frames)
        if holes:
            issues.append({"type": "hole", "dir": d, "frames": holes})
        if fringe:
            issues.append({"type": "fringe", "dir": d, "frames": fringe})
        if pink:
            issues.append({"type": "pink", "dir": d, "frames": pink})
        shadow = _shadow(frames)
        if shadow:
            issues.append({"type": "shadow", "dir": d, "frames": shadow})
        if empty:
            issues.append({"type": "empty", "dir": d, "frames": empty})
        if kind == "loop" and len(frames) > 2 and _seam(frames):
            issues.append({"type": "seam", "dir": d, "frames": [len(frames) - 1, 0]})
        if not vivid and (dir_reports.get(d) or {}).get("frames_touching_edge", 0) > 3:
            issues.append({"type": "edge", "dir": d, "frames": []})
        rep = dir_reports.get(d) or {}
        if rep.get("bg_changed", 0) > 0.1 * max(1, rep.get("video_frames", 1)):   # 영상 AI가 배경색을 바꿈
            issues.append({"type": "bg", "dir": d, "frames": [], "count": rep["bg_changed"]})
    if kind == "loop" and not vivid:                  # 무기를 휘두르는 동작은 칼끝 때문에 키를 비교할 수 없다
        heights = {d: float(np.median([_height(f) for f in rows[d]])) for d in dirs}
        if len(heights) > 2:
            med = float(np.median(list(heights.values()))) or 1.0
            for d, h in heights.items():
                if abs(h - med) / med > 0.15:
                    issues.append({"type": "size", "dir": d, "frames": [], "ratio": round(h / med, 2)})
    return issues
