"""추가 설치 없이 쓰는 3D 마네킹: 뼈 방향 키프레임 → 원하는 방향·각도에서 렌더한 영상.

모든 방향이 같은 3D 동작을 자기 각도에서 본 영상을 레퍼런스로 받으므로, 한 손/두 손·궤적·박자가 구조적으로 같아진다.

좌표: 캐릭터 기준 +Y 위, +Z 앞(얼굴 방향), +X 캐릭터의 왼쪽. 길이 단위는 대략 미터(키 약 1.6).
포즈는 관절 각도 대신 '뼈가 향하는 방향(3D 벡터)'으로 적는다 (사람·LLM 모두 쓰기 쉽게).
"""
import json
from pathlib import Path

import cv2
import numpy as np

# 뼈: (부모 관절, 이 관절, 길이, 반지름)
BONES = {
    "r_upper": ("r_shoulder", "r_elbow", 0.27, 0.045),
    "r_fore": ("r_elbow", "r_hand", 0.25, 0.038),
    "l_upper": ("l_shoulder", "l_elbow", 0.27, 0.045),
    "l_fore": ("l_elbow", "l_hand", 0.25, 0.038),
    "r_thigh": ("r_hip", "r_knee", 0.42, 0.065),
    "r_shin": ("r_knee", "r_ankle", 0.42, 0.05),
    "l_thigh": ("l_hip", "l_knee", 0.42, 0.065),
    "l_shin": ("l_knee", "l_ankle", 0.42, 0.05),
}
REST = {
    "pelvis": [0.0, 0.0, 0.0], "spine": [0.0, 0.0, 0.0], "head": [0.0, 0.0],
    "r_upper": [-0.15, -1, 0.0], "r_fore": [-0.05, -1, 0.1], "l_upper": [0.15, -1, 0.0], "l_fore": [0.05, -1, 0.1],
    "r_thigh": [-0.08, -1, 0.0], "r_shin": [0.0, -1, 0.0], "l_thigh": [0.08, -1, 0.0], "l_shin": [0.0, -1, 0.0],
    "r_foot": [0.0, -0.2, 1.0], "l_foot": [0.0, -0.2, 1.0], "sword": None,
}
FACING_YAW = {"S": 0, "SE": 45, "E": 90, "NE": 135, "N": 180, "NW": -135, "W": -90, "SW": -45}


def _unit(v):
    v = np.asarray(v, np.float64)
    return v / (np.linalg.norm(v) + 1e-9)


def _rot_y(deg):
    a = np.radians(deg)
    return np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])


def _rot_x(deg):
    a = np.radians(deg)
    return np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]])


def _rot_z(deg):
    a = np.radians(deg)
    return np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])


def interpolate(keys, t):
    """keys: [{"t": 초, ...포즈}] → t초의 포즈 (부드러운 가감속, 방향은 정규화 보간)."""
    keys = sorted(keys, key=lambda k: k["t"])
    if t <= keys[0]["t"]:
        a = b = keys[0]
        w = 0.0
    elif t >= keys[-1]["t"]:
        a = b = keys[-1]
        w = 0.0
    else:
        i = max(j for j, k in enumerate(keys) if k["t"] <= t)
        a, b = keys[i], keys[i + 1]
        u = (t - a["t"]) / (b["t"] - a["t"])
        w = u * u * (3 - 2 * u)
    pose = {}
    for name, rest in REST.items():
        va, vb = a.get(name, rest), b.get(name, rest)
        if va is None or vb is None:
            pose[name] = va if vb is None else vb
            continue
        v = (1 - w) * np.asarray(va, float) + w * np.asarray(vb, float)
        pose[name] = v
    return pose


def skeleton(pose):
    """포즈 → 관절 위치(캐릭터 좌표)."""
    P = {}
    pelvis = np.array([0.0, 0.92, 0.0]) + np.asarray(pose["pelvis"], float)
    pitch, twist, side = pose["spine"]
    chest_rot = _rot_y(twist) @ _rot_x(pitch) @ _rot_z(side)
    P["pelvis"] = pelvis
    P["chest"] = pelvis + chest_rot @ np.array([0, 0.30, 0])
    P["neck"] = pelvis + chest_rot @ np.array([0, 0.46, 0])
    hp, hy = pose["head"]
    P["head"] = P["neck"] + chest_rot @ _rot_y(hy) @ _rot_x(hp) @ np.array([0, 0.13, 0.01])
    P["r_shoulder"] = pelvis + chest_rot @ np.array([-0.19, 0.42, 0])
    P["l_shoulder"] = pelvis + chest_rot @ np.array([0.19, 0.42, 0])
    hip_rot = _rot_y(twist * 0.35)
    P["r_hip"] = pelvis + hip_rot @ np.array([-0.09, -0.02, 0])
    P["l_hip"] = pelvis + hip_rot @ np.array([0.09, -0.02, 0])
    for bone, (a, b, length, _) in BONES.items():
        P[b] = P[a] + _unit(pose[bone]) * length
    P["r_toe"] = P["r_ankle"] + _unit(pose["r_foot"]) * 0.15
    P["l_toe"] = P["l_ankle"] + _unit(pose["l_foot"]) * 0.15
    if pose.get("sword") is not None:
        d = _unit(pose["sword"])
        P["sword_grip"] = P["r_hand"] - d * 0.06
        P["sword_guard"] = P["r_hand"] + d * 0.05
        P["sword_tip"] = P["r_hand"] + d * 0.85
    return P


def poses_from_keys(keys, length, fps=24):
    """키프레임 → 프레임마다 관절 위치 목록."""
    return [skeleton(interpolate(keys, i / fps)) for i in range(length)]


def fit_keys(keys, seconds, lead=0.4, tail=0.5):
    """키프레임이 seconds보다 길면 앞뒤로 서 있는 구간(같은 자세가 이어지는 키)을 줄여 seconds 안에 넣는다.
    Codex 키프레임은 5초 영상 기준(처음 1.2초 서 있다가 동작)이라, 3초로 만들 때 동작은 그대로 두고 기다림만 줄인다.
    동작 자체가 길면 동작도 같은 비율로 줄인다."""
    if not keys or keys[-1]["t"] <= seconds:
        return keys

    def pose(k):
        return {n: v for n, v in k.items() if n != "t"}
    i0 = 0
    while i0 + 1 < len(keys) and pose(keys[i0]) == pose(keys[i0 + 1]):
        i0 += 1
    i1 = len(keys) - 1
    while i1 - 1 > i0 and pose(keys[i1]) == pose(keys[i1 - 1]):
        i1 -= 1
    a0, a1 = keys[i0]["t"], keys[i1]["t"]
    lead = min(lead, a0)
    k = min(1.0, (seconds - lead - tail) / max(a1 - a0, 1e-6))
    out = []
    for j, key in enumerate(keys):
        t = (0.0 if j == 0 else lead) if j <= i0 else lead + (min(key["t"], a1) - a0) * k + (tail if j > i1 else 0)
        t += 0.01 * max(0, j - max(i1, 1) - 1) + (0.01 * j if 0 < j < i0 else 0)   # 같은 시각이 겹치지 않게
        out.append(dict(key, t=round(t, 3)))
    out[-1]["t"] = max(out[-1]["t"], seconds)
    return out


# ---------- 레퍼런스 영상에서 뽑은 3D 뼈대(MediaPipe) → 마네킹 ----------

MP = {"l_ear": 7, "r_ear": 8, "l_shoulder": 11, "r_shoulder": 12, "l_elbow": 13, "r_elbow": 14, "l_wrist": 15,
      "r_wrist": 16, "l_hip": 23, "r_hip": 24, "l_knee": 25, "r_knee": 26, "l_ankle": 27, "r_ankle": 28,
      "l_foot": 31, "r_foot": 32}
UP = np.array([0.0, 1.0, 0.0])


def _capture_array(capture):
    """MediaPipe 결과 → (프레임, 33, 3) 마네킹 좌표(+X 캐릭터 왼쪽, +Y 위, +Z 앞). 못 찾은 프레임은 앞뒤로 메운다."""
    raw = capture["frames"]
    valid = [i for i, f in enumerate(raw) if f]
    if len(valid) < max(6, len(raw) // 3):
        raise RuntimeError("레퍼런스 영상에서 사람 자세를 거의 찾지 못했어요 (온몸이 잘 보이는 영상을 써 주세요)")
    arr = np.zeros((len(raw), 33, 3))
    for i in range(len(raw)):
        if raw[i]:
            a = np.asarray(raw[i], float)[:, :3]
        else:                                          # 가장 가까운 프레임 두 개 사이를 잇는다
            prev = max((j for j in valid if j < i), default=None)
            nxt = min((j for j in valid if j > i), default=None)
            if prev is None or nxt is None:
                a = np.asarray(raw[prev if nxt is None else nxt], float)[:, :3]
            else:
                w = (i - prev) / (nxt - prev)
                a = (1 - w) * np.asarray(raw[prev], float)[:, :3] + w * np.asarray(raw[nxt], float)[:, :3]
        arr[i] = np.stack([a[:, 0], -a[:, 1], -a[:, 2]], axis=1)   # 사람이 카메라를 보면 사람 왼쪽이 화면 오른쪽(+x)
    return arr


def _smooth(arr, radius, wrap):
    if radius <= 0:
        return arr
    n = len(arr)
    idx = np.arange(n)
    out = np.zeros_like(arr)
    weights = np.exp(-0.5 * (np.arange(-radius, radius + 1) / max(1.0, radius / 1.5)) ** 2)
    for k, w in zip(range(-radius, radius + 1), weights):
        j = (idx + k) % n if wrap else np.clip(idx + k, 0, n - 1)
        out += w * arr[j]
    return out / weights.sum()


def _frame_skeleton(a):
    """한 프레임의 3D 관절(엉덩이 중심) → 마네킹 관절 위치. 뼈 방향은 영상 그대로, 길이는 마네킹 길이로."""
    g = {k: a[i] for k, i in MP.items()}
    hip_mid, sh_mid = (g["l_hip"] + g["r_hip"]) / 2, (g["l_shoulder"] + g["r_shoulder"]) / 2
    up = _unit(sh_mid - hip_mid)
    across = g["l_shoulder"] - g["r_shoulder"]
    across = _unit(across - up * (across @ up))
    chest = np.stack([across, up, np.cross(across, up)], axis=1)          # 가슴의 좌우·위·앞 축
    hip_across = g["l_hip"] - g["r_hip"]
    hip_across = _unit(hip_across - UP * hip_across[1])
    hips = np.stack([hip_across, UP, np.cross(hip_across, UP)], axis=1)
    pelvis = np.array([0.0, 0.92, 0.0])
    P = {"pelvis": pelvis, "chest": pelvis + chest @ [0, 0.30, 0], "neck": pelvis + chest @ [0, 0.46, 0],
         "r_shoulder": pelvis + chest @ [-0.19, 0.42, 0], "l_shoulder": pelvis + chest @ [0.19, 0.42, 0],
         "r_hip": pelvis + hips @ [-0.09, -0.02, 0], "l_hip": pelvis + hips @ [0.09, -0.02, 0]}
    P["head"] = P["neck"] + _unit((g["l_ear"] + g["r_ear"]) / 2 - sh_mid) * 0.13
    for s in ("r", "l"):
        P[f"{s}_elbow"] = P[f"{s}_shoulder"] + 0.27 * _unit(g[f"{s}_elbow"] - g[f"{s}_shoulder"])
        P[f"{s}_hand"] = P[f"{s}_elbow"] + 0.25 * _unit(g[f"{s}_wrist"] - g[f"{s}_elbow"])
        P[f"{s}_knee"] = P[f"{s}_hip"] + 0.42 * _unit(g[f"{s}_knee"] - g[f"{s}_hip"])
        P[f"{s}_ankle"] = P[f"{s}_knee"] + 0.42 * _unit(g[f"{s}_ankle"] - g[f"{s}_knee"])
        P[f"{s}_toe"] = P[f"{s}_ankle"] + 0.15 * _unit(g[f"{s}_foot"] - g[f"{s}_ankle"])
    low = min(P[k][1] for k in ("r_ankle", "l_ankle", "r_toe", "l_toe"))
    lift = np.array([0.0, 0.03 - low, 0.0])           # 낮은 발이 땅(차렷 자세의 발끝 높이)에 닿게
    return {k: v + lift for k, v in P.items()}


def poses_from_capture(capture, length, loop=False, fps=24, smooth=2, blend=12):
    """레퍼런스 영상의 3D 뼈대 → 마네킹 관절 위치 목록 (length 프레임)과 한 바퀴 길이(프레임).
    - 몸이 보는 방향은 영상 전체의 평균 방향을 정면(+Z)으로 돌린다 (돌기·스핀은 그대로 남는다).
    - 반복 동작이면 끝 blend 프레임 동안 첫 자세로 이어 붙이고, 그 뒤로는 처음부터 다시 돈다.
    - 한 번 하는 동작이면 끝난 뒤 마지막 자세로 멈춰 있다."""
    arr = _capture_array(capture)
    src_fps = capture.get("fps") or fps
    if abs(src_fps - fps) > 0.5:                       # 영상 fps → 마네킹 fps
        t = np.arange(int(len(arr) * fps / src_fps)) * src_fps / fps
        arr = np.stack([arr[min(len(arr) - 1, int(round(x)))] for x in t])
    across = (arr[:, MP["l_hip"]] - arr[:, MP["r_hip"]]) + (arr[:, MP["l_shoulder"]] - arr[:, MP["r_shoulder"]])
    yaw = np.degrees(np.arctan2(np.mean(-across[:, 2]), np.mean(across[:, 0])))   # 앞 = 좌우선을 -90° 돌린 쪽
    arr = arr @ _rot_y(-yaw).T
    arr = _smooth(arr, smooth, wrap=loop)
    n = min(len(arr), length - 1)
    poses = [_frame_skeleton(arr[i]) for i in range(n)]
    if loop:
        b = min(blend, n // 3)
        for k in range(b):                             # 끝을 첫 자세로 부드럽게 잇는다
            w = (k + 1) / (b + 1)
            w = w * w * (3 - 2 * w)
            i = n - b + k
            poses[i] = {j: (1 - w) * poses[i][j] + w * poses[0][j] for j in poses[i]}
        return [poses[i % n] for i in range(length)], n
    return poses + [poses[-1]] * (length - n), n


def motion_window_poses(poses, thresh=0.06, pad=2):
    """마네킹이 움직이는 구간과 가장 빠른 순간 (시작, 끝, 타격) 프레임."""
    speed = [0.0] + [sum(float(np.linalg.norm(b[k] - a[k])) for k in b if k in a) for a, b in zip(poses, poses[1:])]
    speed = np.asarray(speed)
    active = np.where(speed > thresh * speed.max())[0] if speed.max() > 0 else []
    length = len(poses)
    if len(active) == 0:
        return 0, length - 1, length // 2
    return max(0, int(active[0]) - pad), min(length - 1, int(active[-1]) + pad), int(np.argmax(speed))


def motion_window(keys, length, fps=24, thresh=0.06, pad=2):
    """마네킹이 움직이는 구간과 가장 빠른 순간 (시작, 끝, 타격) 프레임. 모든 방향이 이 박자를 따르므로,
    한 번 하는 동작을 자를 때 방향마다 따로 찾지 않고 이 구간을 같이 쓴다."""
    return motion_window_poses(poses_from_keys(keys, length, fps), thresh, pad)


def fit_frame(keys, yaws, elevation, length, fps=24, margin=0.04, safety=1.12):
    """키프레임 동작 내내 칼끝까지 화면 안에 들어오는 크기·발 위치 (fit_frame_poses 참고)."""
    return fit_frame_poses(poses_from_keys(keys, length, fps), yaws, elevation, margin, safety)


def fit_frame_poses(poses, yaws, elevation, margin=0.04, safety=1.12):
    """동작 내내 칼끝까지 화면 안에 들어오는 가장 큰 캐릭터 크기와 발 위치 → (char_height, bottom_margin).
    둘 다 화면 높이에 대한 비율이고, first_frames와 마네킹 렌더에 같이 쓴다."""
    e = np.radians(elevation)
    ce, se = np.cos(e), np.sin(e)
    reach, top, low = 0.0, 0.0, 0.0
    for P in poses[::2]:
        pts = np.array(list(P.values()))
        for yaw in yaws:
            q = pts @ _rot_y(yaw).T
            y = q[:, 1] * ce - q[:, 2] * se
            reach = max(reach, float(np.abs(q[:, 0]).max()))
            top, low = max(top, float(y.max())), min(low, float(y.min()))
    A = reach * safety + 0.05                         # 팔·칼 두께
    T = top * safety + 0.13                           # 머리 반지름
    B = -low * safety + 0.05
    s = min((0.5 - margin) / A, (1 - 2 * margin) / (T + B))   # 화면 비율 / 미터
    feet = margin + T * s + ((1 - 2 * margin) - (T + B) * s) / 2
    char_height = s * (1.62 * ce + 0.15) / 0.9          # render_mannequin_refs의 크기 맞춤을 거꾸로
    return float(np.clip(char_height, 0.36, 0.72)), float(np.clip(1 - feet, 0.06, 0.3))


SKIN = (224, 214, 198)      # 목각 인형처럼 밝은 몸 (회색 배경과 확실히 구분되게)
RIGHT = (238, 172, 118)     # 오른쪽 팔다리: 따뜻한 색
LEFT = (128, 172, 230)      # 왼쪽 팔다리: 차가운 색
FACE = (250, 240, 226)
LINE = (36, 38, 44)


def _shade(color, k):
    return tuple(int(np.clip(c * k, 0, 255)) for c in color)


def _pt(p):
    return tuple(int(v) for v in np.round(p))


def _capsule_3d(img, pa, pb, r, color, k):
    """원기둥처럼 보이게: 외곽선 → 그늘 → 빛 받는 면(왼쪽 위로 비킴) → 하이라이트."""
    rr = max(1, int(round(r)))
    for (c, rad, off) in ((LINE, rr + 2, 0.0), (_shade(color, 0.7 * k), rr, 0.0),
                          (_shade(color, k), max(1, int(rr * 0.7)), 0.2), (_shade(color, 1.16 * k), max(1, int(rr * 0.26)), 0.38)):
        o = np.array([-off, -off]) * rr
        a, b = _pt(pa + o), _pt(pb + o)
        cv2.line(img, a, b, c, 2 * rad, cv2.LINE_AA)
        cv2.circle(img, a, rad, c, -1, cv2.LINE_AA)
        cv2.circle(img, b, rad, c, -1, cv2.LINE_AA)


def _ball_3d(img, p, r, color, k):
    _capsule_3d(img, p, p, r, color, k)


def render(P, yaw, elevation, size=640, scale=None, center=(0.5, 0.86), bg=(184, 184, 184), style="v1"):
    """관절 위치를 정사영으로 그린다. yaw: 캐릭터가 보는 방향(도), elevation: 카메라가 내려다보는 각도(도).
    v1(기본): 회색 캡슐 마네킹. v2: 밝은 목각 인형 + 입체 음영 + 얼굴·뒤통수 + 오른쪽 주황/왼쪽 파랑.
    v2는 H3가 알록달록한 팔다리를 빛나는 효과로 읽어 캐릭터에 분홍 테두리·소용돌이를 그려서 기본으로 쓰지 않는다."""
    if style == "v1":
        return _render_v1(P, yaw, elevation, size, scale, center, bg)
    W = H = size
    scale = scale or size * 0.42
    R = _rot_y(yaw)
    e = np.radians(elevation)
    ce, se = np.cos(e), np.sin(e)
    cx, cy = center[0] * W, center[1] * H

    def proj(p):
        q = R @ p
        return np.array([cx + q[0] * scale, cy - (q[1] * ce - q[2] * se) * scale]), q[1] * se + q[2] * ce

    depths = [proj(v)[1] for v in P.values()]
    d0, d1 = min(depths), max(depths)
    near = lambda d: 0.84 + 0.16 * (d - d0) / (d1 - d0 + 1e-6)          # noqa: E731 — 먼 쪽은 조금 어둡게

    prims = []

    def capsule(a, b, r, color):
        (pa, da), (pb, db) = proj(P[a]), proj(P[b])
        prims.append(((da + db) / 2, "cap", (pa, pb, r * scale, color, near((da + db) / 2))))

    capsule("r_hip", "l_hip", 0.105, SKIN)                 # 골반
    capsule("pelvis", "chest", 0.13, SKIN)                 # 허리
    capsule("chest", "neck", 0.155, SKIN)                  # 가슴
    capsule("r_shoulder", "l_shoulder", 0.085, SKIN)
    for bone, (a, b, _, r) in BONES.items():
        capsule(a, b, r * 1.15, RIGHT if bone.startswith("r_") else LEFT)
    capsule("r_ankle", "r_toe", 0.05, RIGHT)
    capsule("l_ankle", "l_toe", 0.05, LEFT)
    for side, color in (("r", RIGHT), ("l", LEFT)):
        p, d = proj(P[f"{side}_hand"])
        prims.append((d + 0.01, "ball", (p, 0.058 * scale, color, near(d))))
    hp, hd = proj(P["head"])
    prims.append((hd, "head", (hp, hd)))
    if "sword_tip" in P:
        (g, dg), (t, dt) = proj(P["sword_guard"]), proj(P["sword_tip"])
        (h, dh) = proj(P["sword_grip"])
        prims.append(((dg + dt) / 2 + 0.02, "sword", (h, g, t)))

    img = np.full((H, W, 3), bg, np.uint8)
    fwd = _face_dir(P)
    across = _unit(P["l_shoulder"] - P["r_shoulder"])
    up = _unit(P["head"] - P["neck"])
    for _, kind, data in sorted(prims, key=lambda x: x[0]):
        if kind == "cap":
            pa, pb, r, color, k = data
            _capsule_3d(img, pa, pb, r, color, k)
        elif kind == "ball":
            p, r, color, k = data
            _ball_3d(img, p, r, color, k)
        elif kind == "head":
            p, d = data
            _ball_3d(img, p, 0.125 * scale, SKIN, near(d))
            fc, fd = proj(P["head"] + fwd * 0.09)
            if fd > d:                                     # 얼굴이 보이면: 밝은 얼굴판 + 두 눈
                cv2.circle(img, _pt(fc), max(2, int(0.07 * scale)), FACE, -1, cv2.LINE_AA)
                for s in (-1, 1):
                    ep, edp = proj(P["head"] + fwd * 0.115 + across * (0.042 * s) + up * 0.018)
                    if edp > d:
                        cv2.circle(img, _pt(ep), max(2, int(0.016 * scale)), LINE, -1, cv2.LINE_AA)
            else:                                          # 등을 보이면: 어두운 뒤통수
                bc, _ = proj(P["head"] - fwd * 0.07 + up * 0.02)
                cv2.circle(img, _pt(bc), max(2, int(0.085 * scale)), _shade(SKIN, 0.55), -1, cv2.LINE_AA)
        elif kind == "sword":
            h, g, t = data
            cv2.line(img, _pt(h), _pt(g), (90, 60, 40), 7, cv2.LINE_AA)
            cv2.line(img, _pt(g), _pt(t), (60, 62, 70), 9, cv2.LINE_AA)
            cv2.line(img, _pt(g), _pt(t), (225, 230, 238), 5, cv2.LINE_AA)
    return img


def _render_v1(P, yaw, elevation, size=640, scale=None, center=(0.5, 0.86), bg=(184, 184, 184)):
    """예전 마네킹: 회색 캡슐, 오른쪽 팔다리만 조금 밝게, 얼굴은 점 하나."""
    W = H = size
    scale = scale or size * 0.42
    R = _rot_y(yaw)
    e = np.radians(elevation)
    ce, se = np.cos(e), np.sin(e)
    cx, cy = center[0] * W, center[1] * H

    def proj(p):
        q = R @ p
        sx = cx + q[0] * scale
        sy = cy - (q[1] * ce - q[2] * se) * scale
        depth = q[1] * se + q[2] * ce          # 클수록 카메라에 가까움
        return np.array([sx, sy]), depth

    prims = []   # (depth, kind, data)
    body = (118, 122, 132)
    light = (150, 154, 164)
    dark = (62, 64, 72)

    def capsule(a, b, r, color):
        (pa, da), (pb, db) = proj(P[a]), proj(P[b])
        prims.append(((da + db) / 2, "cap", (pa, pb, r * scale, color)))

    # 몸통: 골반~가슴~목을 굵은 캡슐로
    capsule("pelvis", "chest", 0.11, body)
    capsule("chest", "neck", 0.12, body)
    capsule("r_shoulder", "l_shoulder", 0.06, body)
    capsule("r_hip", "l_hip", 0.07, body)
    for bone, (a, b, _, r) in BONES.items():
        # 오른쪽 팔다리를 조금 밝게 칠해서 어느 쪽 손·발인지 영상에서도 구분되게
        capsule(a, b, r, light if bone.startswith("r_") else body)
    capsule("r_ankle", "r_toe", 0.04, light)
    capsule("l_ankle", "l_toe", 0.04, body)
    hp, hd = proj(P["head"])
    prims.append((hd, "head", (hp, 0.11 * scale, body)))
    fp, fd = proj(P["head"] + _face_dir(P) * 0.105)   # 얼굴 쪽 표시 — 앞모습/뒷모습 구분용
    if fd > hd:
        prims.append((fd + 0.001, "face", (fp, max(2.0, 0.028 * scale))))
    for side in ("r", "l"):
        p, d = proj(P[f"{side}_hand"])
        prims.append((d + 0.01, "ball", (p, 0.045 * scale, light if side == "r" else body)))
    if "sword_tip" in P:
        (g, dg), (t, dt) = proj(P["sword_guard"]), proj(P["sword_tip"])
        (h, dh) = proj(P["sword_grip"])
        prims.append(((dg + dt) / 2 + 0.02, "sword", (h, g, t)))

    img = np.full((H, W, 3), bg, np.uint8)
    for _, kind, data in sorted(prims, key=lambda x: x[0]):
        if kind == "cap":
            pa, pb, r, color = data
            _draw_capsule(img, pa, pb, r, color, dark)
        elif kind in ("head", "ball"):
            p, r, color = data
            cv2.circle(img, tuple(np.round(p).astype(int)), int(round(r)) + 2, dark, -1, cv2.LINE_AA)
            cv2.circle(img, tuple(np.round(p).astype(int)), int(round(r)), color, -1, cv2.LINE_AA)
        elif kind == "face":
            p, r = data
            cv2.circle(img, tuple(np.round(p).astype(int)), int(round(r)), dark, -1, cv2.LINE_AA)
        elif kind == "sword":
            # 든 물건은 몸과 같은 무채색으로: 흰 칼날로 그리면 마젠타 배경에서 너무 눈에 띄어, 지팡이를 든 캐릭터도
            # 칼을 든 모습으로 베껴 그린다 (2026-10-08 시험). 무엇을 들었는지는 첫 프레임(캐릭터 그림)이 정한다.
            h, g, t = data
            cv2.line(img, tuple(np.round(h).astype(int)), tuple(np.round(t).astype(int)), dark, 9, cv2.LINE_AA)
            cv2.line(img, tuple(np.round(h).astype(int)), tuple(np.round(t).astype(int)), light, 5, cv2.LINE_AA)
    return img


def _face_dir(P):
    """가슴 기준 앞쪽 방향 (어깨선과 위쪽의 외적)."""
    across = P["l_shoulder"] - P["r_shoulder"]
    up = P["neck"] - P["pelvis"]
    return _unit(np.cross(across, up))


def _draw_capsule(img, pa, pb, r, color, outline):
    a, b = tuple(np.round(pa).astype(int)), tuple(np.round(pb).astype(int))
    rr = max(1, int(round(r)))
    cv2.line(img, a, b, outline, 2 * rr + 4, cv2.LINE_AA)
    cv2.circle(img, a, rr + 2, outline, -1, cv2.LINE_AA)
    cv2.circle(img, b, rr + 2, outline, -1, cv2.LINE_AA)
    cv2.line(img, a, b, color, 2 * rr, cv2.LINE_AA)
    cv2.circle(img, a, rr, color, -1, cv2.LINE_AA)
    cv2.circle(img, b, rr, color, -1, cv2.LINE_AA)


def render_clip(keys, direction, elevation=45, seconds=5.2, fps=24, size=640):
    yaw = FACING_YAW[direction]
    n = int(round(seconds * fps))
    return [render(skeleton(interpolate(keys, i / fps)), yaw, elevation, size) for i in range(n)]


def save_mp4(frames, path, fps=24):
    h, w = frames[0].shape[:2]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for f in frames:
        writer.write(cv2.cvtColor(f, cv2.COLOR_RGB2BGR))
    writer.release()
    return Path(path)


def load_mp4(path):
    cap = cv2.VideoCapture(str(path))
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
    cap.release()
    return frames


def load_keys(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))["keys"]


KEYFRAME_GUIDE = """You write keyframes for a simple 3D mannequin used as a motion reference for game sprite animation.
Coordinate system (character-local): +Y is up, +Z is forward (the way the character faces), +X is the character's LEFT side
(so the right arm and right leg are on the -X side).
Each key is an object with "t" (seconds) and any of these fields (a missing field keeps the previous key's value):
- "pelvis": [x, y, z] hip offset from the rest position in meters (y < 0 crouches, z > 0 shifts forward)
- "spine": [pitch_forward_deg, twist_left_deg, side_tilt_deg] (twist_left > 0 turns the chest toward the character's left)
- "head": [pitch_down_deg, yaw_left_deg] relative to the chest
- "r_upper", "r_fore", "l_upper", "l_fore": direction vectors of the upper arms (shoulder to elbow) and forearms (elbow to wrist)
- "r_thigh", "r_shin", "l_thigh", "l_shin": direction vectors (hip to knee, knee to ankle); "r_foot", "l_foot": toe directions
- "sword": direction vector of the blade held in the RIGHT hand, or null when no sword is held
Directions are 3D vectors in the same frame and do not need to be normalized. Bone lengths: upper arm 0.27 m, forearm 0.25 m,
thigh 0.42 m, shin 0.42 m; shoulders sit 0.19 m to each side of the spine, 0.42 m above the hips.
"""


VIDEO_GUIDE = """The attached images are frames of a reference video of a person performing the motion, in time order,
taken at these times (seconds): {times}. Reproduce the person's BODY MOTION with the mannequin: write one key at each of
these times with the same pose as that frame (lean, crouch, arm and leg directions, which foot is forward), so the timing
matches the video. Read the pose in 3D: the person usually faces the camera, so the person's own RIGHT arm and leg appear on
the LEFT side of the image, and the mannequin's right side is -X. If the person turns around or travels across the floor,
keep the mannequin on the spot facing +Z and copy only the body movement (e.g. a moonwalk becomes sliding steps in place).
"""


def codex_keyframes(text, kind, example_path, workdir, seconds=5.2, log_path=None, images=None, times=None,
                    hold_end=False):
    """동작 설명(한국어 가능)을 Codex에게 주고 마네킹 키프레임 JSON을 받는다.
    images·times를 주면 레퍼런스 영상 프레임을 보여 주고 그 자세를 그 시각에 그대로 옮기게 한다 (영상 → 3D 마네킹).
    hold_end: 처음 자세로 돌아오지 않고 마지막 자세로 끝나는 한 번 동작 (쓰러짐 등)."""
    import subprocess
    from .codex import find_cli
    example = Path(example_path).read_text(encoding="utf-8")
    if kind == "loop":
        rule = (f"This is a LOOPING motion: the first and the last key must be identical and the motion must cycle "
                f"seamlessly over exactly {seconds} seconds (use one or two full cycles).")
    elif hold_end:
        rule = (f"This is a ONE-SHOT action that ENDS IN A DIFFERENT POSE: hold the starting pose still until about 1.2 s, "
                f"perform the action between 1.2 s and 3.2 s, then hold the final pose still until {seconds} s "
                "(do not return to the starting pose).")
    else:
        rule = (f"This is a ONE-SHOT action: hold the starting pose still until about 1.2 s, perform the action between "
                f"1.2 s and 3.0 s, return to exactly the starting pose by 3.0 s and hold it until {seconds} s.")
    video = ""
    if images:
        video = VIDEO_GUIDE.format(times=", ".join(f"{t:.2f}" for t in times))
        if kind == "loop":
            rule = (f"This is a LOOPING motion over exactly {seconds} seconds: follow the video poses at their times, "
                    "and make the last key identical to the first so the motion cycles seamlessly.")
        else:
            rule = (f"This is a ONE-SHOT action: follow the video poses at their times and hold the last pose until "
                    f"{seconds} s.")
    what = f"this motion: \"{text}\"" if text else "the motion in the reference video"
    prompt = (KEYFRAME_GUIDE + "\nExample (one-handed downward sword slash):\n" + example + "\n\n" + video +
              f"Now write keyframes for {what}.\n{rule}\n"
              f"Use {'one key per video frame' if images else '6 to 12 keys'} with clear, readable poses that look right "
              "from any viewing angle and keep the feet on the ground unless the motion is a jump. Output ONLY the JSON "
              "object {\"name\": ..., \"keys\": [...]} with no explanation and no code fences. Do not run any commands or "
              "create any files.")
    out_file = Path(workdir) / "keyframes_answer.txt"
    cmd = [find_cli(), "exec", "--ignore-user-config", "--skip-git-repo-check", "-s", "read-only",
           "-C", str(workdir), "-o", str(out_file)]
    if images:
        cmd += ["-i", *[str(p) for p in images]]
    cmd.append("-")
    out_file.unlink(missing_ok=True)                   # '다시 짜기'에서 예전 답을 읽지 않게
    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=600, cwd=str(workdir))
    if log_path:
        Path(log_path).write_text((proc.stdout or "") + "\n" + (proc.stderr or ""), encoding="utf-8")
    answer = out_file.read_text(encoding="utf-8") if out_file.exists() else proc.stdout
    start, end = answer.find("{"), answer.rfind("}")
    if start < 0 or end < 0:
        raise RuntimeError("Codex가 키프레임 JSON을 돌려주지 않았어요")
    data = json.loads(answer[start:end + 1])
    if not data.get("keys"):
        raise RuntimeError("키프레임이 비어 있어요")
    data["keys"] = sorted(data["keys"], key=lambda k: k["t"])
    return data
