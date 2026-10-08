"""H3가 칼 휘두르기 등에 멋대로 붙이는 베기 궤적·빛 이펙트를 지운다.

캐릭터 원래 색(첫 프레임)에 없는 채도 높은 빛(파랑·하늘·보라 계열)을 씨앗으로 잡고,
그 씨앗에 붙어 있는 아주 밝은 흰 띠(궤적의 심지)까지 넓혀서 투명하게 만든다.
칼날처럼 원래 있던 밝은 색은 첫 프레임 팔레트에 있으므로 건드리지 않는다.
"""
import cv2
import numpy as np


def character_palette(rgba, k=24):
    """첫 프레임 캐릭터의 색(Lab)을 k개로 요약한다."""
    rgb, a = rgba[..., :3], rgba[..., 3] > 200
    lab = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2LAB).reshape(-1, 3)[a.ravel()].astype(np.float32)
    k = min(k, len(lab))
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _, _, centers = cv2.kmeans(lab, k, None, crit, 2, cv2.KMEANS_PP_CENTERS)
    return centers


def effect_mask(rgba, palette_lab, foreign_dist=22.0, min_area=120):
    rgb = np.ascontiguousarray(rgba[..., :3])
    alpha = rgba[..., 3] > 0
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    dist = np.min(np.linalg.norm(lab[..., None, :] - palette_lab[None, None], axis=-1), axis=-1)
    foreign = dist > foreign_dist
    blueish = (h >= 80) & (h <= 150)
    glow = alpha & foreign & blueish & (s > 45) & (v > 70)                         # 파랑·하늘·보라 빛
    seed = cv2.morphologyEx(glow.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    near = cv2.dilate(seed, np.ones((15, 15), np.uint8), iterations=3).astype(bool)
    core = alpha & (s < 50) & (v > 228)                                           # 궤적의 흰 심지 (칼날보다 밝음)
    fringe = alpha & blueish & (s > 18) & (v > 140)                               # 빛 가장자리의 옅은 파랑
    mask = seed.astype(bool) | (near & (core | fringe))
    # 파란 빛 없이 새하얗기만 한 궤적: 아주 밝은 흰색의 큰 덩어리 (칼날 하이라이트는 가늘고 작아서 남는다)
    white = (alpha & (s < 25) & (v > 242)).astype(np.uint8)
    n, lab_w, stats_w, _ = cv2.connectedComponentsWithStats(white, connectivity=8)
    for i in range(1, n):
        if stats_w[i, cv2.CC_STAT_AREA] >= 400:
            mask |= lab_w == i
    # 남은 흰 테두리: 지운 영역에 이어진 밝은 픽셀을 따라 넓혀 간다 (칼날은 이보다 어두워서 멈춘다)
    region = (core | fringe).astype(np.uint8)
    m = mask.astype(np.uint8)
    for _ in range(40):
        grown = (cv2.dilate(m, np.ones((3, 3), np.uint8)) & region) | m
        if np.array_equal(grown, m):
            break
        m = grown
    mask = m.astype(bool)
    # 작은 점은 캐릭터 일부일 수 있으니 큰 덩어리만
    n, lab_cc, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = np.zeros_like(mask)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            keep |= lab_cc == i
    return cv2.dilate(keep.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)


def drop_slivers(im, min_share=0.01):
    """몸통에서 떨어진 작은 조각(지운 이펙트의 흔적)을 없앤다."""
    solid = (im[..., 3] > 32).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(solid, connectivity=8)
    if n <= 2:
        return im
    areas = stats[1:, cv2.CC_STAT_AREA]
    small = 1 + np.where(areas < areas.max() * min_share)[0]
    gone = np.isin(lab, small)
    im = im.copy()
    im[gone] = 0
    return im


def drop_detached(im, gap=0.06, max_share=0.15):
    """몸에서 멀리 떨어져 떠 있는 덩어리(베기 궤적의 꼬리 등)를 없앤다. 손에 붙어 있거나 가까운 칼은 남는다."""
    solid = (im[..., 3] > 32).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(solid, connectivity=8)
    if n <= 2:
        return im
    main = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    r = max(3, int(gap * im.shape[0]))
    near = cv2.dilate((lab == main).astype(np.uint8),
                      cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))).astype(bool)
    gone = np.zeros(lab.shape, bool)
    for i in range(1, n):
        if i == main or stats[i, cv2.CC_STAT_AREA] >= max_share * stats[main, cv2.CC_STAT_AREA]:
            continue
        comp = lab == i
        if not (comp & near).any():
            gone |= comp
    if not gone.any():
        return im
    im = im.copy()
    im[cv2.dilate(gone.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)] = 0
    return im


def temporal_mask(im, t, alphas, palette_lab, bg=None, window=6, spike=1.08, radius=0.08):
    """파랗지 않은 이펙트(흰 원형 충격파 등)용: 이펙트는 몇 프레임에만 나오므로, 앞뒤 '깨끗한' 프레임의 캐릭터 윤곽
    (넉넉히 넓힌 것) 밖으로 튀어나온 밝거나 낯선 색, 또는 이펙트에 둘러싸인 배경색 덩어리를 이펙트로 본다.
    몸에 붙은 작은 조각(칼날)은 남기고, 몸에서 떨어진 것과 큰 덩어리는 지운다."""
    areas = [float((a > 0.5).sum()) for a in alphas]
    med = float(np.median(areas))
    if areas[t] <= med * spike:
        return None
    lo, hi = max(0, t - window), min(len(alphas), t + window + 1)
    clean = [i for i in range(lo, hi) if i != t and areas[i] <= med * spike]
    if not clean:   # 이펙트가 오래 남으면 양쪽에서 가장 가까운 깨끗한 프레임과 비교 (최대 window*4)
        before = next((i for i in range(t - 1, -1, -1) if areas[i] <= med * spike), None)
        after = next((i for i in range(t + 1, len(alphas)) if areas[i] <= med * spike), None)
        clean = [i for i in (before, after) if i is not None and abs(i - t) <= 4 * window]
    if not clean:
        return None
    ref = np.zeros(alphas[t].shape, np.uint8)
    for i in clean:
        ref |= (alphas[i] > 0.5).astype(np.uint8)
    r = max(3, int(radius * ref.shape[0]))
    ref = cv2.dilate(ref, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))).astype(bool)
    rgb = np.ascontiguousarray(im[..., :3])
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    dist = np.min(np.linalg.norm(lab[..., None, :] - palette_lab[None, None], axis=-1), axis=-1)
    bright = (hsv[..., 1] < 60) & (hsv[..., 2] > 170)
    odd = bright | (dist > 22)
    if bg is not None:   # 이펙트에 둘러싸여 배경으로 안 잡힌 배경색 영역
        odd |= np.linalg.norm(rgb.astype(np.float32) - np.asarray(bg, np.float32), axis=2) < 40
    cand = ((im[..., 3] > 0) & ~ref & odd).astype(np.uint8)
    if bg is not None:   # 윤곽 안쪽이라도 배경색 그대로인 곳은 이펙트가 가둔 배경
        inside_bg = (im[..., 3] > 0) & ref & (np.linalg.norm(rgb.astype(np.float32) - np.asarray(bg, np.float32), axis=2) < 25)
        cand |= cv2.morphologyEx(inside_bg.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    touch = cv2.dilate(ref.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    n, lab_cc, stats, _ = cv2.connectedComponentsWithStats(cand, connectivity=8)
    out = np.zeros(cand.shape, bool)
    for i in range(1, n):
        comp = lab_cc == i
        attached = (comp & touch).any()
        if not attached or stats[i, cv2.CC_STAT_AREA] > 0.25 * med:
            out |= comp
    return cv2.dilate(out.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)


def remove_effects(frames_rgba, ref_rgba, all_alphas=None, picks=None, bg=None):
    """frames_rgba의 각 프레임에서 이펙트를 지운 사본과, 프레임별 지운 픽셀 수를 돌려준다.
    all_alphas(클립 전체 프레임의 알파)와 picks(frames_rgba 각각의 원래 프레임 번호)를 주면 흰 이펙트도 지운다."""
    pal = character_palette(ref_rgba)
    out, removed = [], []
    for j, im in enumerate(frames_rgba):
        m = effect_mask(im, pal)
        if all_alphas is not None:
            tm = temporal_mask(im, picks[j] if picks else j, all_alphas, pal, bg)
            if tm is not None:
                m = m | tm
        before = int((im[..., 3] > 0).sum())
        if m.any():
            im = im.copy()
            im[m] = 0
            im = drop_slivers(im)
        im = drop_detached(im)
        out.append(im)
        removed.append(before - int((im[..., 3] > 0).sum()))
    return out, removed
