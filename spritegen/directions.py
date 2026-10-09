"""방향 세트(8·4·2방향), 좌우 반전 규칙, 3x3 방향 시트에서 캐릭터 찾기, 방향별 첫 프레임 만들기."""
import cv2
import numpy as np
from PIL import Image, ImageFilter

# 방향 시트는 항상 나침반 배치 3x3 (위 = 화면 위쪽을 보는 뒷모습 N, 아래 = 카메라를 보는 정면 S)
LAYOUT = [["NW", "N", "NE"],
          ["W", None, "E"],
          ["SW", "S", "SE"]]

# 출력 시트의 행 순서 (S에서 시작해 시계 방향)
SHEET_ORDER = {
    8: ["S", "SW", "W", "NW", "N", "NE", "E", "SE"],
    4: ["S", "W", "N", "E"],
    2: ["W", "E"],
}
MIRROR = {"W": "E", "SW": "SE", "NW": "NE", "E": "W", "SE": "SW", "NE": "NW"}
LEFT_SIDE = {"W", "SW", "NW"}

FACING = {
    "S": "toward the bottom of the screen, toward the camera",
    "SE": "diagonally toward the lower-right of the screen",
    "E": "toward the right side of the screen, in profile",
    "NE": "diagonally toward the upper-right of the screen, mostly away from the camera",
    "N": "toward the top of the screen, with the back to the camera",
    "NW": "diagonally toward the upper-left of the screen, mostly away from the camera",
    "W": "toward the left side of the screen, in profile",
    "SW": "diagonally toward the lower-left of the screen",
}
# Codex에게 시트를 그리게 할 때 칸 설명
CELL_TEXT = {
    "NW": "facing up-left (away from the viewer, toward the upper-left)",
    "N": "facing up (back to the viewer)",
    "NE": "facing up-right (away from the viewer, toward the upper-right)",
    "W": "facing left",
    "E": "facing right",
    "SW": "facing down-left (toward the viewer, toward the lower-left)",
    "S": "facing down (toward the viewer)",
    "SE": "facing down-right (toward the viewer, toward the lower-right)",
}
NAME_KO = {"S": "아래", "SE": "오른쪽 아래", "E": "오른쪽", "NE": "오른쪽 위", "N": "위",
           "NW": "왼쪽 위", "W": "왼쪽", "SW": "왼쪽 아래"}


def directions_for(count):
    if count not in SHEET_ORDER:
        raise ValueError("방향 수는 8, 4, 2 중 하나여야 해요")
    return SHEET_ORDER[count]


def generated_directions(count, mirror):
    """실제로 영상을 만들 방향. 반전을 쓰면 왼쪽 방향은 오른쪽 결과를 뒤집어 쓴다."""
    dirs = directions_for(count)
    if not mirror:
        return list(dirs)
    return [d for d in dirs if d not in LEFT_SIDE]


def source_of(d, generated):
    """출력 방향 d를 어떤 생성 결과로 채울지: (방향, 반전 여부)."""
    if d in generated:
        return d, False
    if MIRROR.get(d) in generated:
        return MIRROR[d], True
    raise ValueError(f"{d} 방향을 채울 결과가 없어요")


def detect_cells(src, required, thresh=40):
    """3x3 시트에서 방향별 캐릭터를 찾는다. (배경색, {방향: bbox}, {방향: 마스크})를 돌려준다."""
    border = np.concatenate([src[0], src[-1], src[:, 0], src[:, -1]])
    bg = np.median(border, axis=0)
    mask = np.linalg.norm(src.astype(np.float32) - bg, axis=2) > thresh

    # 덩어리마다 무게중심이 속한 칸으로 배정 (위아래 캐릭터가 가까워도 섞이지 않게)
    merged = cv2.dilate(mask.astype(np.uint8), np.ones((5, 5), np.uint8))
    n, labels, stats, cents = cv2.connectedComponentsWithStats(merged, connectivity=8)
    H, W = src.shape[:2]
    owners = {}
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < 30:
            continue
        cx, cy = cents[i]
        name = LAYOUT[min(2, int(cy / H * 3))][min(2, int(cx / W * 3))]
        if name:
            owners.setdefault(name, []).append(i)
    missing = [d for d in required if d not in owners]
    if missing:
        raise ValueError(f"방향 시트에서 이 방향의 캐릭터를 못 찾았어요: {', '.join(missing)}")

    cells, masks = {}, {}
    for name, ids in owners.items():
        m = np.isin(labels, ids) & mask
        ys, xs = np.where(m)
        cells[name] = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        masks[name] = m
    return bg, cells, masks


def head_colors(src, dirs, frac=0.45):
    """방향마다 머리 쪽(캐릭터 윗부분 45%) 색 분포 (RGB 8x8x8 칸)."""
    _, cells, masks = detect_cells(src, dirs)
    out = {}
    for d in dirs:
        x0, y0, x1, y1 = cells[d]
        top = y0 + max(1, int((y1 - y0) * frac))
        px = src[y0:top, x0:x1][masks[d][y0:top, x0:x1]]
        if len(px) < 50:
            return {}
        q = (px // 32).astype(int)
        h = np.bincount(q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2], minlength=512).astype(float)
        out[d] = h / h.sum()
    return out


def face_shares(src, dirs):
    """방향마다 '얼굴 색'이 정면(S)의 몇 배 보이는지 {방향: 비율}. 얼굴 색 = 정면 머리 쪽에만 많고 뒷모습(N)에는 거의 없는
    색(피부·눈). 후드·머리카락처럼 앞뒤에 다 있는 색은 빼고 본다. 정면에 그런 색이 거의 없으면(가면·로봇 등) {}."""
    h = head_colors(src, dirs)
    if not h or "S" not in h or "N" not in h:
        return {}
    face = h["S"] > 2 * h["N"] + 0.002
    total = h["S"][face].sum()
    if total < 0.03:
        return {}
    return {d: float(v[face].sum() / total) for d, v in h.items()}


def facing_problems(src, dirs):
    """8방향 그림에서 앞뒤가 바뀐 대각선을 찾는다 → [{"dir": 방향, "looks": "front" | "back"}].
    뒤 대각선(NE·NW)에 얼굴 색이 앞 대각선(SE·SW)만큼(0.75배 이상) 보이면 앞모습으로 잘못 그린 것, 앞 대각선에 얼굴 색이
    정면의 0.35배도 안 보이면 뒷모습으로 잘못 그린 것. 2026-10-09: 예전에는 머리 쪽 색 분포가 앞·뒤 중 어디를 닮았는지만
    봐서, 노란 후드가 머리를 덮은 캐릭터처럼 앞뒤 색이 비슷하면 놓쳤다. 시트 11장에서 틀린 칸(꼬마 HD NE·NW, 반실사 기사
    NE·NW, 모험가 NW)을 모두 잡고 멀쩡한 칸은 하나도 안 잡았다."""
    if not {"N", "S"} <= set(dirs):
        return []
    try:
        f = face_shares(src, dirs)
    except ValueError:
        return []
    if not f:
        return []
    front_ref = max([f[d] for d in ("SE", "SW") if d in f] or [1.0])
    out = []
    for d in ("NE", "NW"):
        if d in f and front_ref >= 0.5 and (f[d] >= 0.75 * front_ref or f[d] >= 0.8):
            out.append({"dir": d, "looks": "front"})
    for d in ("SE", "SW"):
        if d in f and f[d] < 0.35:
            out.append({"dir": d, "looks": "back"})
    return out


def cutout(src, cells, masks, name, scale, resample=Image.LANCZOS):
    """한 방향 캐릭터를 잘라 배율을 적용한 (RGB, 알파) 이미지 쌍을 돌려준다 (픽셀아트는 resample=NEAREST)."""
    x0, y0, x1, y1 = cells[name]
    crop = Image.fromarray(src[y0:y1, x0:x1])
    alpha = Image.fromarray((masks[name][y0:y1, x0:x1] * 255).astype(np.uint8))
    alpha = alpha.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(1))
    size = (max(1, round(crop.width * scale)), max(1, round(crop.height * scale)))
    return crop.resize(size, resample), alpha.resize(size, resample)


def first_frames(sheet_rgb, dirs, size=(640, 640), char_height=0.72, bottom_margin=0.12, scale_from=None,
                 resample=Image.LANCZOS, bg_color=None):
    """방향마다 같은 배율·같은 발 높이로 캐릭터를 배치한 첫 프레임을 만든다.

    scale_from: 배율 기준이 되는 (bbox 목록). 자세 시트 여러 장을 같은 배율로 맞출 때 기준 시트의 칸을 넘긴다.
    bg_color: 주면 캐릭터를 깨끗하게 오려(막힌 틈의 배경도 지움) 그 색 배경에 놓는다 (예: 마젠타 크로마키).
    돌려주는 값: ({방향: PIL 이미지}, {"scale", "feet_y", "size", "bg"})"""
    from .imaging import cutout_rgba, sheet_alpha
    W, H = size
    bg, cells, masks = detect_cells(sheet_rgb, dirs)
    ref = scale_from if scale_from is not None else [cells[d] for d in dirs]
    scale = char_height * H / float(np.median([b[3] - b[1] for b in ref]))
    feet_y = H - round(bottom_margin * H)
    color = tuple(int(v) for v in bg.round()) if bg_color is None else tuple(int(v) for v in bg_color)
    out = {}
    for d in dirs:
        if bg_color is None:
            crop, alpha = cutout(sheet_rgb, cells, masks, d, scale, resample)
            canvas = Image.new("RGB", (W, H), color)
            canvas.paste(crop, ((W - crop.width) // 2, feet_y - crop.height), alpha)
        else:
            x0, y0, x1, y1 = cells[d]
            pad = 4
            x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
            x1, y1 = min(sheet_rgb.shape[1], x1 + pad), min(sheet_rgb.shape[0], y1 + pad)
            crop = np.ascontiguousarray(sheet_rgb[y0:y1, x0:x1])
            own = cv2.dilate(masks[d][y0:y1, x0:x1].astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
            a = sheet_alpha(crop, bg) * own                      # 이 방향 캐릭터 덩어리만
            ys, xs = np.where(a > 0.02)
            rgba = Image.fromarray(cutout_rgba(crop, a, bg)).crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
            rgba = rgba.resize((max(1, round(rgba.width * scale)), max(1, round(rgba.height * scale))), resample)
            canvas = Image.new("RGBA", (W, H), color + (255,))
            canvas.alpha_composite(rgba, ((W - rgba.width) // 2, feet_y - rgba.height))
            canvas = canvas.convert("RGB")
        out[d] = canvas
    return out, {"scale": scale, "feet_y": feet_y, "size": [W, H], "bg": list(color), "cells": cells}


def preview_layout(count):
    """미리보기용 배치 (방향 이름 2차원 배열, None은 빈칸)."""
    if count == 8:
        return LAYOUT
    if count == 4:
        return [[None, "N", None], ["W", None, "E"], [None, "S", None]]
    return [["W", "E"]]
