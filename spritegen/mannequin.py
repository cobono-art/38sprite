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


def motion_window(keys, length, fps=24, thresh=0.06, pad=2):
    """마네킹이 움직이는 구간과 가장 빠른 순간 (시작, 끝, 타격) 프레임. 모든 방향이 이 박자를 따르므로,
    한 번 하는 동작을 자를 때 방향마다 따로 찾지 않고 이 구간을 같이 쓴다."""
    prev, speed = None, [0.0]
    for i in range(length):
        P = skeleton(interpolate(keys, i / fps))
        if prev is not None:
            speed.append(sum(float(np.linalg.norm(P[k] - prev[k])) for k in P if k in prev))
        prev = P
    speed = np.asarray(speed)
    active = np.where(speed > thresh * speed.max())[0] if speed.max() > 0 else []
    if len(active) == 0:
        return 0, length - 1, length // 2
    return max(0, int(active[0]) - pad), min(length - 1, int(active[-1]) + pad), int(np.argmax(speed))


def fit_frame(keys, yaws, elevation, length, fps=24, margin=0.04, safety=1.12):
    """동작 내내 칼끝까지 화면 안에 들어오는 가장 큰 캐릭터 크기와 발 위치 → (char_height, bottom_margin).
    둘 다 화면 높이에 대한 비율이고, first_frames와 마네킹 렌더에 같이 쓴다."""
    e = np.radians(elevation)
    ce, se = np.cos(e), np.sin(e)
    reach, top, low = 0.0, 0.0, 0.0
    for i in range(0, length, 2):
        pts = np.array(list(skeleton(interpolate(keys, i / fps)).values()))
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


def render(P, yaw, elevation, size=640, scale=None, center=(0.5, 0.86), bg=(184, 184, 184)):
    """관절 위치를 정사영으로 그린다. yaw: 캐릭터가 보는 방향(도), elevation: 카메라가 내려다보는 각도(도)."""
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
            h, g, t = data
            cv2.line(img, tuple(np.round(h).astype(int)), tuple(np.round(g).astype(int)), (90, 60, 40), 7, cv2.LINE_AA)
            cv2.line(img, tuple(np.round(g).astype(int)), tuple(np.round(t).astype(int)), (60, 62, 70), 9, cv2.LINE_AA)
            cv2.line(img, tuple(np.round(g).astype(int)), tuple(np.round(t).astype(int)), (225, 230, 238), 5, cv2.LINE_AA)
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


def codex_keyframes(text, kind, example_path, workdir, seconds=5.2, log_path=None):
    """동작 설명(한국어 가능)을 Codex에게 주고 마네킹 키프레임 JSON을 받는다."""
    import subprocess
    from .codex import find_cli
    example = Path(example_path).read_text(encoding="utf-8")
    if kind == "loop":
        rule = (f"This is a LOOPING motion: the first and the last key must be identical and the motion must cycle "
                f"seamlessly over exactly {seconds} seconds (use one or two full cycles).")
    else:
        rule = (f"This is a ONE-SHOT action: hold the starting pose still until about 1.2 s, perform the action between "
                f"1.2 s and 3.0 s, return to exactly the starting pose by 3.0 s and hold it until {seconds} s.")
    prompt = (KEYFRAME_GUIDE + "\nExample (one-handed downward sword slash):\n" + example + "\n\n"
              f"Now write keyframes for this motion: \"{text}\".\n{rule}\n"
              "Use 6 to 12 keys with clear, readable poses that look right from any viewing angle and keep the feet on "
              "the ground unless the motion is a jump. Output ONLY the JSON object {\"name\": ..., \"keys\": [...]} with "
              "no explanation and no code fences. Do not run any commands or create any files.")
    out_file = Path(workdir) / "keyframes_answer.txt"
    cmd = [find_cli(), "exec", "--ignore-user-config", "--skip-git-repo-check", "-s", "read-only",
           "-C", str(workdir), "-o", str(out_file), "-"]
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
