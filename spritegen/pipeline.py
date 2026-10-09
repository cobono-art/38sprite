"""작업 실행: 방향 그림 만들기(Codex) → 방향별 동작 영상(H3) → 스프라이트 시트."""
import json
import random
import shutil
import subprocess
import threading
import time
import traceback
import uuid
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from . import codex, comfy, matting
from . import project as store
from .assemble import assemble, retime
from .directions import detect_cells, directions_for, facing_problems, first_frames, generated_directions
from .effects import remove_effects
from .imaging import (KEY_MAGENTA, cutout_any, cutout_rgba, bg_pattern, estimate_bg, frame_alpha, frames_to_webp, load_frames,
                      load_ref, pixel_cell_size, sheet_alpha)
from .prompts import follow_prompt, mannequin_prompt, motion_prompt, redraw_prompt, reference_prompt, sheet_prompt
from . import mannequin as mq

EXAMPLES = __import__("pathlib").Path(__file__).resolve().parent / "examples"

FRAME_SIZE = (640, 640)


def motion_frame_size(m, fresh=False):
    """이 동작의 영상 크기 (가로, 세로). 도트 스타일은 결과가 키 74칸 안팎이라 480으로 만들어도 도트 품질이 같고 약 30%
    빠르다(2026-10-09 같은 시드 걷기 5방향: 640 방향당 80~85초 → 480 55~60초, 설정 pixel_video_size).
    이미 만든 동작은 만들 때의 크기 그대로 (한 방향만 다시 만들거나 시트를 다시 조립할 때 다른 방향과 맞게, 크기를
    적어 두기 전에 만든 동작은 640). fresh: 처음부터 새로 만들 때."""
    if not fresh:
        return tuple(m.get("frame_size") or FRAME_SIZE)
    if m["settings"]["style"] == "pixel":
        n = int(store.load_config().get("pixel_video_size", 480)) // 16 * 16
        return (n, n)
    return FRAME_SIZE

# 기본 모션 세트: 캐릭터 하나로 게임에 바로 넣을 동작 묶음. key는 내보낼 때 파일·애니메이션 이름으로 쓴다.
# 공격·피격은 방향마다 손·박자가 맞아야 해서 3D 마네킹, 쓰러짐은 처음 자세로 돌아오지 않는 동작(hold_end)이다.
MOTION_SET = [
    {"key": "idle", "name": "대기", "kind": "loop", "mode": "direct", "frames": 8,
     "text": "제자리에 서서 가볍게 숨 쉬며 대기한다. 어깨와 가슴만 아주 살짝 오르내리고 발은 움직이지 않는다"},
    {"key": "walk", "name": "걷기", "kind": "loop", "mode": "direct", "frames": 8,
     "text": "제자리에서 자연스럽게 걷는다. 팔과 다리를 번갈아 앞뒤로 움직인다"},
    {"key": "run", "name": "달리기", "kind": "loop", "mode": "direct", "frames": 8,
     "text": "제자리에서 팔을 크게 흔들며 힘차게 달린다"},
    {"key": "attack", "name": "공격", "kind": "oneshot", "mode": "mannequin", "frames": 8,
     "text": "오른손에 든 무기를 머리 위로 들었다가 앞을 향해 크게 한 번 내려친다 (무기가 없으면 오른손 주먹으로 앞을 친다)"},
    {"key": "hit", "name": "피격", "kind": "oneshot", "mode": "mannequin", "frames": 6,
     "text": "앞에서 공격을 맞아 상체가 뒤로 움찔 젖혀지며 반 걸음 밀렸다가 원래 자세로 돌아온다"},
    {"key": "death", "name": "쓰러짐", "kind": "oneshot", "mode": "direct", "frames": 8, "hold_end": True,
     "text": "힘이 빠지며 무릎이 꺾이고 뒤로 쓰러져 바닥에 눕는다. 누운 뒤에는 움직이지 않는다"},
]


class Job:
    def __init__(self, kind, pid, mid=None, label=""):
        self.id = "j" + uuid.uuid4().hex[:10]
        self.kind, self.pid, self.mid, self.label = kind, pid, mid, label
        self.status = "queued"
        self.message = "대기 중"
        self.progress = 0.0
        self.parts = {}
        self.error = None
        self.created = time.time()
        self.started = self.finished = None
        self.cancelled = False
        self.prompt_ids = []

    def to_dict(self):
        elapsed = (self.finished or time.time()) - self.started if self.started else 0
        return {"id": self.id, "kind": self.kind, "project": self.pid, "motion": self.mid, "label": self.label,
                "status": self.status, "message": self.message, "progress": round(self.progress, 3),
                "parts": self.parts, "error": self.error, "elapsed": round(elapsed)}


class JobManager:
    def __init__(self):
        self.jobs = {}

    def submit(self, job, fn):
        self.jobs[job.id] = job

        def run():
            job.started = time.time()
            job.status = "running"
            try:
                fn(job)
                job.status = "cancelled" if job.cancelled else "done"
                if not job.cancelled:
                    job.progress, job.message = 1.0, "완료"
            except Exception as e:  # noqa: BLE001 — 작업 실패는 화면에 그대로 보여준다
                job.status, job.error = "error", str(e)
                job.message = "실패"
                job.trace = traceback.format_exc()
            finally:
                job.finished = time.time()

        threading.Thread(target=run, daemon=True).start()
        return job

    def get(self, jid):
        return self.jobs.get(jid)

    def active_for(self, pid):
        return [j.to_dict() for j in self.jobs.values() if j.pid == pid and j.status in ("queued", "running")]


JOBS = JobManager()


# ---------- 방향 그림 ----------

def make_sheet(job, pid):
    p = store.load(pid)
    pdir = store.project_dir(pid)
    s = p["settings"]
    dirs = directions_for(s["count"])
    (pdir / "sheets").mkdir(exist_ok=True)
    out = pdir / "sheets" / f"sheet_{len(p['sheets']) + 1}.png"
    job.message = "Codex가 방향 그림을 그리는 중이에요 (보통 1~3분)"
    job.progress = 0.1
    prompt = sheet_prompt(dirs, s["angle"], s["style"], s["pixel_height"])
    codex.generate_image(prompt, [pdir / p["turnaround"]], out, workdir=pdir, log_path=out.with_suffix(".log"))
    job.progress, job.message = 0.9, "방향마다 캐릭터를 찾는 중"
    rec = {"file": f"sheets/{out.name}", "settings": dict(s), "created": store.now(), "problem": None}
    check_sheet(rec, np.asarray(Image.open(out).convert("RGB")))

    def upd(pr):
        pr["sheets"].append(rec)
        pr["sheet"] = rec
    store.update(pid, upd)
    if rec["problem"]:
        raise RuntimeError(rec["problem"] + " — 다시 그려 주세요")
    auto_fix_facing(job, pid, rec)


def auto_fix_facing(job, pid, rec, rounds=None):
    """방향 그림에서 앞뒤가 바뀐 대각선이 보이면 그 칸만 Codex로 다시 그린다 (설정 auto_redraw, 기본 2번까지 — 고친 그림이
    또 틀리면 한 번 더). Codex는 뒤 대각선(NE·NW)을 앞모습으로 그리는 실수가 잦다(2026-10-09 HD 시트에서도 또 나옴).
    예전에는 알려 주기만 하고 사람이 '한 방향만 다시 그리기'를 눌러야 했다. 다시 그리다 실패해도 그린 시트는 그대로 쓴다."""
    rounds = int(store.load_config().get("auto_redraw", 2)) if rounds is None else rounds
    for i in range(rounds):
        facing = rec.get("facing") or []
        if not facing:
            return
        try:
            for f in facing:
                job.message = (f"{f['dir']} 방향이 {'앞모습' if f['looks'] == 'front' else '뒷모습'}처럼 그려져서 "
                               f"그 칸만 다시 그리는 중이에요 ({i + 1}/{rounds})")
                redraw_direction(job, pid, f["dir"])
        except Exception as e:  # noqa: BLE001 — Codex가 실패해도 처음 그린 시트는 쓸 수 있다
            job.message = f"앞뒤가 바뀐 칸을 자동으로 다시 그리지 못했어요: {e}"
            return
        rec = store.load(pid)["sheet"]


def use_uploaded_sheet(pid, data, suffix):
    """사용자가 직접 그린 방향 시트(3x3 나침반 배치)를 쓴다."""
    p = store.load(pid)
    pdir = store.project_dir(pid)
    (pdir / "sheets").mkdir(exist_ok=True)
    out = pdir / "sheets" / f"sheet_{len(p['sheets']) + 1}_upload{suffix}"
    out.write_bytes(data)
    rec = {"file": f"sheets/{out.name}", "settings": dict(p["settings"]), "created": store.now(),
           "problem": None, "uploaded": True}
    check_sheet(rec, np.asarray(Image.open(out).convert("RGB")))

    def upd(pr):
        pr["sheets"].append(rec)
        pr["sheet"] = rec
    return store.update(pid, upd)


def check_sheet(rec, src):
    """방향 그림 점검: 방향마다 캐릭터를 찾고(problem), 실제로 영상을 만들 방향 중 앞뒤가 바뀐 대각선을 찾는다(facing)."""
    s = rec["settings"]
    try:
        detect_cells(src, directions_for(s["count"]))
    except ValueError as e:
        rec["problem"] = str(e)
        return
    rec["facing"] = facing_problems(src, generated_directions(s["count"], s["mirror"]))
    rec["pixel_cells"] = sheet_pixel_cells(src, s)


def sheet_pixel_cells(src, s):
    """도트 스타일 방향 그림의 실제 도트 키(칸 수). 코덱스는 지시한 키와 다르게 그린다(64칸으로 지시 → 약 74칸).
    도트 결과를 이 키로 만들면 결과 한 칸이 그림 한 칸과 맞아서, 64칸으로 줄일 때처럼 눈·허리띠·지팡이 구슬이 뭉개지지 않는다
    (2026-10-09 같은 걷기 영상 비교). 도트가 아니거나 못 재면 None — 그때는 설정한 키를 쓴다."""
    if s.get("style") != "pixel":
        return None
    gen = generated_directions(s["count"], s["mirror"])
    try:
        _, cells, masks = detect_cells(src, gen)
    except ValueError:
        return None
    cell, _ = pixel_cell_size(src, [(cells[d], masks[d]) for d in gen])
    if not cell:
        return None
    n = round(float(np.median([cells[d][3] - cells[d][1] for d in gen])) / cell)
    want = s.get("pixel_height", 64)
    return n if 0.5 * want <= n <= 2 * want else None


def pixel_height_for(p, m, sheet_rgb):
    """이 동작의 도트 키: 방향 그림에서 잰 칸 수(설정 pixel_auto_height, 기본 켬), 못 재면 설정한 키."""
    s = m["settings"]
    if s["style"] != "pixel":
        return 0
    if store.load_config().get("pixel_auto_height", True):
        rec = next((x for x in p.get("sheets", []) if x["file"] == m.get("sheet", p["sheet"]["file"])), None)
        cells = rec["pixel_cells"] if rec and "pixel_cells" in rec else sheet_pixel_cells(sheet_rgb, s)
        if cells:
            return cells
    return s["pixel_height"]


SHEET_CELL = {"NW": (0, 0), "N": (1, 0), "NE": (2, 0), "W": (0, 1), "E": (2, 1), "SW": (0, 2), "S": (1, 2), "SE": (2, 2)}


def redraw_direction(job, pid, d):
    """방향 그림에서 한 칸만 Codex로 다시 그려 바꿔 끼운 새 방향 그림을 만든다 (예: 뒷모습이어야 할 NE가 앞모습일 때).
    새 그림은 예전 칸의 캐릭터와 같은 키·같은 발 위치로 맞춘다. 반전을 쓰면 NE를 고치면 NW도 같이 고쳐진다."""
    p = store.load(pid)
    pdir = store.project_dir(pid)
    sh = p["sheet"]
    s = sh["settings"]
    src_path = pdir / sh["file"]
    work = pdir / "sheets" / "redraw"
    work.mkdir(parents=True, exist_ok=True)
    view = work / f"{src_path.stem}_{d}_{uuid.uuid4().hex[:4]}.png"
    job.message, job.progress = f"Codex가 {d} 방향만 다시 그리는 중이에요 (보통 1~3분)", 0.1
    codex.generate_image(redraw_prompt(d, s["angle"], s["style"], s["pixel_height"]), [src_path, pdir / p["turnaround"]],
                         view, workdir=pdir, log_path=view.with_suffix(".log"))
    job.message, job.progress = "새 그림을 방향 그림에 끼우는 중", 0.9
    sheet = Image.open(src_path).convert("RGB")
    sw, sh_ = sheet.size
    cx, cy = SHEET_CELL[d]
    box = (cx * sw // 3, cy * sh_ // 3, (cx + 1) * sw // 3, (cy + 1) * sh_ // 3)
    cw, ch = box[2] - box[0], box[3] - box[1]
    old = np.asarray(sheet.crop(box))
    bg = estimate_bg(old)
    ys, xs = np.where(sheet_alpha(old, bg) > 0.5)
    if len(ys):
        h_old, bottom, center = ys.max() - ys.min(), ys.max(), (xs.min() + xs.max()) / 2
    else:
        h_old, bottom, center = 0.75 * ch, 0.9 * ch, cw / 2
    v = np.asarray(Image.open(view).convert("RGB"))
    vbg = estimate_bg(v)
    fig = Image.fromarray(cutout_rgba(v, sheet_alpha(v, vbg), vbg))
    fig = fig.crop(fig.getbbox())
    k = h_old / fig.height
    fig = fig.resize((max(1, round(fig.width * k)), max(1, round(fig.height * k))),
                     Image.NEAREST if s["style"] == "pixel" else Image.LANCZOS)
    big = Image.new("RGBA", (cw * 3, ch * 3), tuple(int(c) for c in bg) + (255,))     # 칸 밖으로 나가도 잘리기만 하게
    big.alpha_composite(fig, (int(cw + center - fig.width / 2), int(ch + bottom - fig.height)))
    sheet.paste(big.crop((cw, ch, 2 * cw, 2 * ch)).convert("RGB"), box[:2])
    out = pdir / "sheets" / f"sheet_{len(p['sheets']) + 1}_fix{d}.png"
    sheet.save(out)
    rec = {"file": f"sheets/{out.name}", "settings": dict(s), "created": store.now(), "problem": None,
           "fixed": d, "from": sh["file"]}
    check_sheet(rec, np.asarray(sheet))

    def upd(pr):
        pr["sheets"].append(rec)
        pr["sheet"] = rec
    store.update(pid, upd)


def start_redraw(pid, d):
    return JOBS.submit(Job("sheet", pid, label=f"{d} 다시 그리기"), lambda j: redraw_direction(j, pid, d))


# ---------- 동작 ----------

def prepare_reference_video(src, dst, max_sec=5.0, max_side=FRAME_SIZE[0]):
    """레퍼런스 영상을 24fps·최대 max_sec초·긴 변 max_side로 맞춘다 (H3 레퍼런스 영상 입력 형식)."""
    cap = cv2.VideoCapture(str(src))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frames = []
    while len(frames) < int(fps * max_sec) + 2:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    if len(frames) < 12:
        raise RuntimeError("레퍼런스 영상을 읽지 못했거나 너무 짧아요 (0.5초 이상 필요)")
    duration = min(len(frames) / fps, max_sec)
    h, w = frames[0].shape[:2]
    k = min(1.0, max_side / max(h, w))
    size = (int(w * k) // 2 * 2, int(h * k) // 2 * 2)
    writer = cv2.VideoWriter(str(dst), cv2.VideoWriter_fourcc(*"mp4v"), comfy.FPS, size)
    for t in np.arange(0, duration, 1 / comfy.FPS):
        writer.write(cv2.resize(frames[min(len(frames) - 1, int(round(t * fps)))], size, interpolation=cv2.INTER_AREA))
    writer.release()
    return dst, duration


def pick_master(gen):
    """마스터 방향: 동작이 가장 잘 보이는 옆모습(E)을 먼저, 없으면 대각선, 그다음 첫 방향."""
    for d in ("E", "SE", "W", "SW", "S"):
        if d in gen:
            return d
    return gen[0]


def build_master_reference(frames_dir, dst):
    """마스터 영상에서 이펙트를 지우고 원래 배경에 다시 얹어 24fps mp4로 만든다 (나머지 방향의 레퍼런스)."""
    frames = load_frames(frames_dir)
    bg = estimate_bg(frames[0])
    alphas = [frame_alpha(f, bg) for f in frames]
    rgba = [cutout_any(f, a, bg) for f, a in zip(frames, alphas)]
    clean, _ = remove_effects(rgba, rgba[0], alphas, list(range(len(rgba))), bg)
    h, w = clean[0].shape[:2]
    writer = cv2.VideoWriter(str(dst), cv2.VideoWriter_fourcc(*"mp4v"), comfy.FPS, (w, h))
    for im in clean:
        a = im[..., 3:4].astype(np.float32) / 255
        comp = im[..., :3].astype(np.float32) * a + bg[None, None] * (1 - a)
        writer.write(cv2.cvtColor(comp.clip(0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR))
    writer.release()
    return dst


def effects_of(m):
    """빛 효과 방식: none(효과 없이 그림) | vivid(화려하게 살림) | strip(그린 뒤 지움). 예전 동작은 strip_effects로 판단."""
    return m.get("effects") or ("strip" if m.get("strip_effects") else "vivid")


def reference_stills(video, out_dir, count=10):
    """레퍼런스 영상(24fps로 맞춘 것)에서 고르게 count장을 뽑아 PNG로 저장한다 → (파일 목록, 시각 목록)."""
    cap = cv2.VideoCapture(str(video))
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    out_dir.mkdir(parents=True, exist_ok=True)
    idx = sorted({round(i * (len(frames) - 1) / (count - 1)) for i in range(count)})
    paths, times = [], []
    for k, i in enumerate(idx):
        im = frames[i]
        s = 384 / max(im.shape[:2])                    # Codex가 보기 충분한 크기로 줄인다
        im = cv2.resize(im, (round(im.shape[1] * s), round(im.shape[0] * s)), interpolation=cv2.INTER_AREA)
        path = out_dir / f"f{k:02d}.png"
        cv2.imwrite(str(path), im)
        paths.append(path)
        times.append(i / comfy.FPS)
    return paths, times


# ---------- 영상 → 3D 뼈대 (MediaPipe, 앱 전용 가상환경) ----------

POSE_MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/"
                  "latest/pose_landmarker_heavy.task")


def pose_tools():
    """레퍼런스 영상에서 3D 뼈대를 뽑는 도구 (가상환경 파이썬, 모델 파일). 하나라도 없으면 None
    (그러면 Codex가 영상 프레임을 보고 키프레임을 짠다). 만드는 법은 setup_pose.bat."""
    cfg = store.load_config()
    py = Path(cfg.get("pose_python") or store.ROOT / ".venv-pose" / "Scripts" / "python.exe")
    model = Path(cfg.get("pose_model") or store.ROOT / "models" / "pose_landmarker_heavy.task")
    return (py, model) if py.exists() and model.exists() else None


def capture_pose(tools, video, out):
    py, model = tools
    script = Path(__file__).resolve().parent / "pose_capture.py"
    proc = subprocess.run([str(py), str(script), str(video), str(model), str(out)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=900)
    if proc.returncode != 0 or not Path(out).exists():
        tail = " ".join((proc.stderr or proc.stdout or "").strip().splitlines()[-2:])[:300]
        raise RuntimeError(f"영상에서 뼈대를 뽑지 못했어요: {tail}")


BODY_DIR = Path(__file__).resolve().parent / "assets" / "body"
CHIBI = {"head": 2.0, "leg": 0.55, "arm": 0.7, "spine": 0.8, "neck": 0.6, "thick": 1.2}   # body_render.CHIBI와 같게
BODY_MODELS = {"clay": ("Superhero_Male_FullBody.gltf", None),
               "chibi": ("Superhero_Male_FullBody.gltf", None),     # 2~3등신: 머리 2배, 다리·팔·몸통 짧게 (body_render.CHIBI)
               "male": ("Superhero_Male_FullBody.gltf", "Hair_SimpleParted.gltf"),
               "female": ("Superhero_Female_FullBody.gltf", "Hair_Buns.gltf")}


def body_tools():
    """사람 3D 모델(Quaternius, CC0)로 마네킹 영상을 그리는 도구: (가상환경 파이썬, 몸 모델, 머리카락 모델 또는 None).
    기본은 머리카락 없는 점토 사람(clay). 원통 마네킹은 앞팔·뒤팔이 똑같아 보여서 영상 AI가 뒤쪽 빈손을 휘두르는 일이
    있었고(사용자도 알아보기 힘들다고 함), 사람 모델은 음영으로 어느 팔인지 보인다. 예전(2026-10-08 낮)에는 사람 모델이
    생김새까지 베껴 회색 사람을 그렸지만, 금지문 없는 새 프롬프트로는 공격 5방향에서 베끼기가 없었다(같은 날 저녁 시험).
    가상환경(setup_pose.bat)이 없으면 원통 마네킹. 설정 mannequin_body: clay(기본) | male | female | off(원통)."""
    cfg = store.load_config()
    kind = cfg.get("mannequin_body", "clay")
    py = Path(cfg.get("pose_python") or store.ROOT / ".venv-pose" / "Scripts" / "python.exe")
    if kind not in BODY_MODELS or not py.exists():
        return None
    body_name, hair_name = BODY_MODELS[kind]
    body = BODY_DIR / body_name
    chibi = "chibi" if kind == "chibi" else None
    return (py, body, BODY_DIR / hair_name if hair_name else None, chibi) if body.exists() else None


def render_body(tools, poses, dirs, mdir, elevation, size, scale, center, bg, name="mannequin_{d}.mp4"):
    """사람 모델을 poses대로 움직여 방향마다 mp4로 그린다 → {방향: 파일}. dirs: {방향: yaw}."""
    py, body, hair = tools[:3]
    chibi = tools[3] if len(tools) > 3 else None
    joints = list(poses[0])
    (mdir / "poses.json").write_text(json.dumps({"joints": joints, "frames": [[P[j].tolist() for j in joints] for P in poses]}))
    req = {"poses": str(mdir / "poses.json"), "model": str(body), "hair": str(hair) if hair and Path(hair).exists() else None,
           "out": str(mdir), "dirs": dirs, "elevation": elevation, "size": size, "scale": float(scale),
           "center": [float(c) for c in center], "bg": list(bg), "fps": comfy.FPS, "name": name,
           "chibi": CHIBI if chibi else None}
    (mdir / "body_request.json").write_text(json.dumps(req))
    proc = subprocess.run([str(py), str(Path(__file__).resolve().parent / "body_render.py"), str(mdir / "body_request.json")],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    if proc.returncode != 0:
        raise RuntimeError(" ".join((proc.stderr or proc.stdout).strip().splitlines()[-2:])[:300])
    return {d: Path(f) for d, f in json.loads(proc.stdout.strip().splitlines()[-1])["files"].items()}


def has_mannequin_motion(mdir):
    return (mdir / "pose_capture.json").exists() or (mdir / "keys.json").exists()


def mannequin_poses(m, mdir, length):
    """마네킹 동작 → (프레임마다 관절 위치, 한 바퀴 길이). 영상에서 뽑은 3D 뼈대가 있으면 그것, 없으면 Codex 키프레임."""
    cap = mdir / "pose_capture.json"
    if cap.exists():
        return mq.poses_from_capture(json.loads(cap.read_text(encoding="utf-8")), length, loop=m["kind"] == "loop")
    keys = json.loads((mdir / "keys.json").read_text(encoding="utf-8"))["keys"]
    if m["kind"] == "oneshot" and keys[-1]["t"] > length / comfy.FPS + 0.1:
        keys = mq.fit_keys(keys, length / comfy.FPS)   # 3초 영상이면 앞뒤 기다림만 줄여 동작이 다 들어가게
    return mq.poses_from_keys(keys, length), max(2, min(length - 1, round(keys[-1]["t"] * comfy.FPS)))


def default_seconds(kind, mode, source="text", hold_end=False):
    """영상 길이 (2026-10-08 시험): 텍스트 반복 동작은 3초면 5초와 같은 품질에 약 30% 빨랐다 (2.3초는 한 바퀴를
    천천히 걸어 나빠짐). 마네킹 한 번 동작은 키프레임의 기다림을 줄여 3초 (약 40% 빠름). 레퍼런스 영상 따라 하기,
    쓰러짐처럼 끝 자세로 끝나는 동작, 마네킹 반복 동작(춤 등)은 5초 그대로."""
    if source == "video" or hold_end:
        return 5
    if (kind == "loop" and mode == "direct") or (kind == "oneshot" and mode == "mannequin"):
        return 3
    return 5


def make_keyframes(job, pid, mid, server=None):
    """3D 마네킹 모드 1단계: 마네킹 동작을 정하고 확인용 미리보기를 만든다.
    - 레퍼런스 영상: 3D 뼈대 도구가 있으면 영상에서 프레임마다 관절을 뽑아 그대로 쓰고, 없으면 Codex가 프레임을 보고 옮긴다.
    - 텍스트 설명: Codex가 키프레임을 짠다.
    동작에 auto_continue가 있으면(모션 세트) 확인을 건너뛰고 server로 바로 방향별 영상까지 만든다."""
    p = store.load(pid)
    m = next(x for x in p["motions"] if x["id"] == mid)
    s = m["settings"]
    mdir = store.project_dir(pid) / "motions" / mid
    mdir.mkdir(parents=True, exist_ok=True)
    images = times = None
    tools = None
    if m["source"] == "video":
        job.message = "레퍼런스 영상 준비 중"
        prepared, _ = prepare_reference_video(mdir / m["video"], mdir / "reference_24fps.mp4")
        tools = pose_tools()
        if tools:
            job.message = "영상에서 3D 뼈대를 뽑는 중이에요 (MediaPipe)"
            capture_pose(tools, prepared, mdir / "pose_capture.json")
            (mdir / "keys.json").unlink(missing_ok=True)
        else:
            (mdir / "pose_capture.json").unlink(missing_ok=True)
            images, times = reference_stills(prepared, mdir / "ref_frames")
    if not tools:
        job.message = "Codex가 마네킹 키프레임을 짜는 중이에요 (보통 1~2분)"
        data = mq.codex_keyframes(m.get("text", ""), m["kind"], EXAMPLES / "oneshot_slash.json", mdir,
                                  log_path=mdir / "keyframes.log", images=images, times=times,
                                  hold_end=m.get("hold_end", False))
        (mdir / "keys.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    job.message = "마네킹 미리보기 만드는 중"
    gen = generated_directions(s["count"], s["mirror"])
    poses, _ = mannequin_poses(m, mdir, comfy.frames_for_seconds(m.get("seconds", 5)))
    rows = {}
    tools = body_tools()
    if tools:                                          # 사람 모델로: 실제 영상 AI에 넣을 모습 그대로 미리 본다
        try:
            files = render_body(tools, poses[::3][:42], {d: mq.FACING_YAW[d] for d in gen}, mdir, mannequin_elevation(s["angle"]), 256, 95,
                                (0.5, 0.9), (184, 184, 184), name="preview_{d}.mp4")
            for d, f in files.items():
                frames = mq.load_mp4(f)
                rows[d] = [np.dstack([fr, np.full(fr.shape[:2], 255, np.uint8)]) for fr in frames]
                f.unlink(missing_ok=True)
        except Exception as e:  # noqa: BLE001 — 사람 모델이 안 되면 원통 마네킹으로
            (mdir / "body_error.log").write_text(str(e), encoding="utf-8")
            rows = {}
    if not rows:
        for d in gen:
            frames = [mq.render(P, mq.FACING_YAW[d], mannequin_elevation(s["angle"]), 256, scale=95, center=(0.5, 0.9)) for P in poses[::3][:42]]
            rows[d] = [np.dstack([f, np.full(f.shape[:2], 255, np.uint8)]) for f in frames]
    from .assemble import layout_frames
    from .imaging import save_gif
    save_gif(layout_frames(rows, s["count"], gap=4), 8, mdir / "keys_preview.gif")
    if m.get("auto_continue") and server:
        run_motion(job, pid, mid, server, "mannequin")
        return
    _set_motion(pid, mid, status="keys_review")
    job.message = "키프레임 확인 대기"


# 마네킹 모드의 배경: 첫 프레임(가이드)과 마네킹 영상이 같은 색이어야 한다 — 다르면 H3(R2V)가 둘을 섞은 얼룩무늬
# 배경을 그린다. 기본은 둘 다 마젠타(크로마키로 깨끗하게 오린다), 설정 mannequin_bg: gray면 예전처럼 둘 다 회색.
MANNEQUIN_BG = (128, 128, 128)


def mannequin_bg():
    """마네킹 모드 배경색 (첫 프레임·마네킹 영상 공통)."""
    return MANNEQUIN_BG if store.load_config().get("mannequin_bg", "magenta") == "gray" else KEY_MAGENTA


def mannequin_elevation(angle):
    """마네킹을 내려다보는 각도. Codex가 'N도'로 그린 그림은 실제 N도보다 덜 내려다본 모습이라(45°로 그리면 30° 안팎으로
    얼굴이 정면에 가깝게 보인다), 마네킹도 2/3로 낮춰 그려야 캐릭터 그림과 시점이 맞는다."""
    return angle * 2 / 3


def render_mannequin_refs(pid, mid, gen, meta, server):
    """방향마다 그 방향에서 본 마네킹 영상을 만들어 올린다. 캐릭터 첫 프레임과 키·발 높이를 맞춘다."""
    p = store.load(pid)
    m = next(x for x in p["motions"] if x["id"] == mid)
    s = m["settings"]
    mdir = store.project_dir(pid) / "motions" / mid
    W, H = motion_frame_size(m)
    char_px = meta["char_px"]                          # 첫 프레임 캐릭터와 같은 크기로
    cos_e = max(0.3, np.cos(np.radians(mannequin_elevation(s["angle"]))))
    scale = 0.9 * char_px / (1.62 * cos_e + 0.15)
    length = comfy.frames_for_seconds(m.get("seconds", 5))
    poses, _ = mannequin_poses(m, mdir, length)
    # 마네킹이 든 막대(무기)는 영상에 그리지 않는다: 그리면 지팡이를 든 캐릭터도 칼을 든 모습으로 바뀐다
    # (2026-10-08 실험: 막대 있음 4개 중 2개 칼로 바뀜, 막대 없음 4개 모두 원래 무기). 무엇을 들었는지는 첫 프레임이
    # 정하고, 칼끝까지 화면에 들어오게 크기를 정하는 계산(frame_fit)에서만 막대를 쓴다.
    poses = [{k: v for k, v in P.items() if not k.startswith("sword")} for P in poses]
    center = (0.5, meta["feet_y"] / H)
    files = {}
    tools = body_tools()
    if tools:                                          # 사람 3D 모델로 그리면 H3가 사람 동작으로 더 잘 알아본다
        try:
            files = render_body(tools, poses, {d: mq.FACING_YAW[d] for d in gen}, mdir, mannequin_elevation(s["angle"]), W, scale, center,
                                mannequin_bg())
        except Exception as e:  # noqa: BLE001 — 사람 모델이 안 되면 원통 마네킹으로
            (mdir / "body_error.log").write_text(str(e), encoding="utf-8")
            files = {}
    for d in gen:
        if d not in files:
            frames = [mq.render(P, mq.FACING_YAW[d], mannequin_elevation(s["angle"]), W, scale=scale, center=center, bg=mannequin_bg())
                      for P in poses]
            files[d] = mq.save_mp4(frames, mdir / f"mannequin_{d}.mp4")
    return {d: comfy.upload(server, files[d], f"{pid}_{mid}_mq_{d}.mp4") for d in gen}


def bg_drift(frames_dir, step=2):
    """영상 AI가 배경을 마젠타가 아닌 색으로 바꾸거나 마젠타 위에 무늬를 그린 프레임 수 → (그런 프레임, 전체 프레임).
    step장마다 하나씩 본다."""
    files = sorted(Path(frames_dir).glob("*.png"))
    bad = 0
    for f in files[::step]:
        frame = np.asarray(Image.open(f).convert("RGB"))
        r, g, b = estimate_bg(frame)
        bad += int(min(r, b) - g <= 80 or bg_pattern(frame) > 0.1)
    return bad * step, len(files)


def _reseed(wf):
    """워크플로의 시드만 새로 (같은 시드면 같은 영상이 나온다). 시드 칸을 못 찾으면 None."""
    wf = json.loads(json.dumps(wf))
    found = False
    for node in wf.values():
        for k in ("seed", "noise_seed"):
            if isinstance(node.get("inputs", {}).get(k), int):
                node["inputs"][k] = random.randint(1, 2**31)
                found = True
    return wf if found else None


def _generate(job, server, items, mdir, expect_magenta=True):
    """items: [(방향, 워크플로)] — 큐에 넣고 순서대로 받아 frames/<방향>과 raw/<방향>.webp로 저장한다.
    expect_magenta: 받은 영상의 배경이 마젠타로 이어지는지 본다. 영상 AI가 배경을 다른 색으로 바꾼 프레임이 10%를
    넘으면 새 시드로 다시 만들어(bg_retry, 기본 2번) 가장 덜 바뀐 쪽을 쓴다 (배경이 바뀌는 건 프롬프트가 아니라 시드가 정한다 — 2026-10-08 실험). 크로마키로 깨끗하게 오리려면 처음부터
    끝까지 마젠타여야 한다."""
    client = uuid.uuid4().hex
    retries = int(store.load_config().get("bg_retry", 2)) if expect_magenta else 0
    queued = []
    for d, wf in items:
        prompt_id = comfy.queue(server, wf, client)
        job.prompt_ids.append(prompt_id)
        queued.append((d, wf, prompt_id))
    for i, (d, wf, prompt_id) in enumerate(queued):
        if job.cancelled:
            return False
        job.message = f"영상 AI 생성 중: {d} ({i + 1}/{len(queued)})"

        def tick(state, sec, d=d):
            if job.cancelled:                          # 큐에서 지운 작업을 1분씩 기다리지 않게
                raise RuntimeError("취소했어요")
            job.parts[d] = {"state": state, "sec": round(sec)}
        entry, sec = comfy.wait(server, prompt_id, on_tick=tick)
        frames_dir = mdir / "frames" / d
        if frames_dir.exists():
            shutil.rmtree(frames_dir)
        comfy.download(server, entry, frames_dir)
        check = {}
        if expect_magenta:
            drift, total = bg_drift(frames_dir)
            check = {"bg_drift": drift, "frames": total}
            for _ in range(retries):
                wf2 = _reseed(wf) if drift > 0.1 * total else None
                if not wf2:
                    break
                job.message = f"{d}: 영상 AI가 배경색을 바꿔서({drift}/{total}장) 새 시드로 한 번 더 만드는 중"
                pid2 = comfy.queue(server, wf2, client, front=True)
                job.prompt_ids.append(pid2)
                entry2, sec2 = comfy.wait(server, pid2, on_tick=tick)
                sec += sec2
                tmp = mdir / "frames" / f"{d}_retry"
                shutil.rmtree(tmp, ignore_errors=True)
                comfy.download(server, entry2, tmp)
                drift2, total2 = bg_drift(tmp)
                check["retried"] = check.get("retried", 0) + 1
                if drift2 < drift:                     # 덜 바뀐 쪽을 쓴다
                    shutil.rmtree(frames_dir)
                    tmp.rename(frames_dir)
                    drift, total = drift2, total2
                    check.update(bg_drift=drift, frames=total)
                else:
                    shutil.rmtree(tmp, ignore_errors=True)
        (mdir / "raw").mkdir(exist_ok=True)
        frames_to_webp(frames_dir, mdir / "raw" / f"{d}.webp", scale=0.5)
        job.parts[d] = {"state": "done", "sec": round(sec), **check}
        job.progress = 0.05 + 0.85 * (i + 1) / len(queued)
    return not job.cancelled


def frame_fit(m, s, gen, mdir):
    """영상 속 캐릭터 크기와 발 위치 (화면 높이에 대한 비율). 마네킹 공격은 동작을 미리 알아서,
    칼끝까지 화면 안에 들어오는 가장 큰 크기를 계산한다. 나머지 공격은 넉넉히 작게, 반복 동작은 크게."""
    if m["kind"] == "oneshot" and m.get("mode") == "mannequin" and has_mannequin_motion(mdir):
        poses, _ = mannequin_poses(m, mdir, comfy.frames_for_seconds(m.get("seconds", 5)))
        return mq.fit_frame_poses(poses, [mq.FACING_YAW[d] for d in gen], mannequin_elevation(s["angle"]))
    return (0.52, 0.14) if m["kind"] == "oneshot" else (0.72, 0.12)


def _set_motion(pid, mid, **fields):
    store.update(pid, lambda pr: next(x for x in pr["motions"] if x["id"] == mid).update(**fields))


# ---------- 한 방향 다시 만들기 전 결과 보관 (되돌리기) ----------

MAX_VERSIONS = 3


def _dir_items(d):
    """방향 하나에 딸린 것들 (동작 폴더 기준 경로): 영상 프레임, AI 마스크, 미리보기, 첫 프레임, 프롬프트, 마네킹 영상."""
    return [f"frames/{d}", f"ai/{d}", f"raw/{d}.webp", f"first/{d}.png", f"first/{d}.prompt.txt", f"mannequin_{d}.mp4"]


def save_version(pid, mid, dirs):
    """다시 만들기 직전: 그 방향들의 지금 결과를 versions/<번호>/ 에 복사해 둔다 → 번호.
    오래된 것부터 지워 MAX_VERSIONS개만 남긴다."""
    m = store.find_motion(store.load(pid), mid)
    mdir = store.project_dir(pid) / "motions" / mid
    vid = "v" + time.strftime("%m%d%H%M%S") + uuid.uuid4().hex[:3]
    vdir = mdir / "versions" / vid
    for d in dirs:
        for rel in _dir_items(d):
            src = mdir / rel
            if src.is_dir():
                shutil.copytree(src, vdir / rel)
            elif src.exists():
                (vdir / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, vdir / rel)
    ov = m.get("frame_overrides") or {}
    rec = {"id": vid, "dirs": list(dirs), "created": store.now(), "holds": "previous",
           "overrides": {d: ov.get(d) for d in dirs}, "sheet": m.get("sheet")}

    def upd(pr):
        mm = next(x for x in pr["motions"] if x["id"] == mid)
        vs = (mm.get("versions") or []) + [rec]
        for old in vs[:-MAX_VERSIONS]:
            shutil.rmtree(mdir / "versions" / old["id"], ignore_errors=True)
        mm["versions"] = vs[-MAX_VERSIONS:]
    store.update(pid, upd)
    return vid


def drop_version(pid, mid, vid):
    """다시 만들기가 실패했을 때: 지금 결과와 같은 사본이라 지운다."""
    shutil.rmtree(store.project_dir(pid) / "motions" / mid / "versions" / vid, ignore_errors=True)

    def upd(pr):
        mm = next(x for x in pr["motions"] if x["id"] == mid)
        mm["versions"] = [v for v in mm.get("versions") or [] if v["id"] != vid] or None
    store.update(pid, upd)


def swap_version(pid, mid, vid):
    """보관한 결과와 지금 결과를 맞바꾸고 시트를 다시 조립한다 (되돌리기, 다시 한 번 누르면 다시 앞으로)."""
    m = store.find_motion(store.load(pid), mid)
    rec = next((v for v in m.get("versions") or [] if v["id"] == vid), None)
    if not rec:
        raise RuntimeError("보관한 결과가 없어요")
    mdir = store.project_dir(pid) / "motions" / mid
    vdir = mdir / "versions" / vid
    for d in rec["dirs"]:
        for rel in _dir_items(d):
            cur, old, tmp = mdir / rel, vdir / rel, vdir / (rel + ".swap")
            if cur.exists():
                tmp.parent.mkdir(parents=True, exist_ok=True)
                cur.rename(tmp)
            if old.exists():
                cur.parent.mkdir(parents=True, exist_ok=True)
                old.rename(cur)
            if tmp.exists():
                tmp.rename(old)

    def upd(pr):
        mm = next(x for x in pr["motions"] if x["id"] == mid)
        r = next(v for v in mm["versions"] if v["id"] == vid)
        ov = dict(mm.get("frame_overrides") or {})
        now_ov = {d: ov.get(d) for d in r["dirs"]}
        for d, o in (r.get("overrides") or {}).items():
            if o:
                ov[d] = o
            else:
                ov.pop(d, None)
        mm["frame_overrides"] = ov or None
        r["overrides"] = now_ov
        if r.get("sheet"):
            mm["sheet"], r["sheet"] = r["sheet"], mm.get("sheet")
        r["holds"] = "redo" if r["holds"] == "previous" else "previous"
    store.update(pid, upd)
    return assemble_motion(pid, mid)


def run_motion(job, pid, mid, server, phase="all", only=None):
    """phase: 'all'(방향별 바로) | 'master'(마스터 방향만 만들고 확인 대기) | 'rest'(마스터를 따라 나머지 방향)
    | 'mannequin'(방향마다 마네킹을 따라). only: 이 방향들만 새 시드로 다시 만들고, 나머지 방향 영상은 그대로 둔 채
    시트를 다시 조립한다 ('이 방향만 다시 만들기')."""
    p = store.load(pid)
    pdir = store.project_dir(pid)
    m = next(x for x in p["motions"] if x["id"] == mid)
    s = m["settings"]
    if not p.get("sheet"):
        raise RuntimeError("먼저 방향 그림을 만들어 주세요")
    mdir = pdir / "motions" / mid
    gen = generated_directions(s["count"], s["mirror"])
    targets = [d for d in gen if d in only] if only else gen
    oneshot = m["kind"] == "oneshot"
    master = m.get("master") or pick_master(gen)

    fresh = not only and phase in ("all", "master", "mannequin")
    size = motion_frame_size(m, fresh)
    if fresh:
        _set_motion(pid, mid, frame_size=list(size))

    job.message = "방향별 첫 프레임 만드는 중"
    sheet_file = m.get("sheet", p["sheet"]["file"])
    if only and p["sheet"].get("from") == sheet_file:  # 이 동작을 만든 뒤 방향 그림에서 칸을 고쳤으면 고친 그림으로
        sheet_file = p["sheet"]["file"]
        _set_motion(pid, mid, sheet=sheet_file)
    sheet_rgb = np.asarray(Image.open(pdir / sheet_file).convert("RGB"))
    char_h, bottom = frame_fit(m, s, gen, mdir)
    # 마젠타 크로마키 배경에 깨끗하게 오린 캐릭터를 놓는다 (회색 배경보다 분리가 깨끗하다).
    # 마네킹 모드는 마네킹 영상과 같은 배경색이어야 한다 (mannequin_bg: 기본 마젠타, 설정으로 예전 회색).
    mannequin = m.get("mode") == "mannequin"
    gray = mannequin and mannequin_bg() != KEY_MAGENTA
    firsts, meta = first_frames(sheet_rgb, gen, size, char_height=char_h, bottom_margin=bottom,
                                resample=Image.NEAREST if s["style"] == "pixel" else Image.LANCZOS,
                                bg_color=None if gray else KEY_MAGENTA)
    meta["char_px"] = char_h * size[1]
    (mdir / "first").mkdir(parents=True, exist_ok=True)
    for d, im in firsts.items():
        if d in targets:                               # 다시 만들지 않는 방향은 그 영상을 만든 첫 프레임 그대로
            im.save(mdir / "first" / f"{d}.png")

    length = comfy.frames_for_seconds(m.get("seconds", 5))
    fx = effects_of(m) == "vivid"                   # 효과를 살리는 동작만 반짝이·빛을 화려하게 그린다
    hold_end = oneshot and m.get("hold_end", False)  # 쓰러짐처럼 마지막 자세로 끝나는 동작: 끝 프레임을 고정하지 않는다
    end_guides = lambda first: [(first, 0)] if hold_end else [(first, 0), (first, -1)]  # noqa: E731
    if only:                                           # 같은 시드면 같은 영상이 나오니 새 시드로, 그 방향의 장면 바꾸기만 지운다
        seed = random.randint(1, 2**31)
        job.version = save_version(pid, mid, targets)  # 마음에 안 들면 되돌릴 수 있게 지금 결과를 보관

        def clear(pr):
            mm = next(x for x in pr["motions"] if x["id"] == mid)
            ov = {k: v for k, v in (mm.get("frame_overrides") or {}).items() if k not in targets}
            mm["frame_overrides"] = ov or None
        store.update(pid, clear)
    else:
        seed = m.get("seed") or random.randint(1, 2**31)
        # 새로 만드는 프레임에는 예전에 바꿔 둔 장면 번호가 맞지 않으니 지운다
        _set_motion(pid, mid, seed=seed, master=master, frame_overrides=None)
    info = comfy.check(server)
    # 효과 없이 만들 동작은 '빼는 낱말' 노드(ComfyUI에 설치돼 있을 때만)로 빛 궤적·반짝임·빛무리를 생성 단계에서 뺀다.
    # 프롬프트에 "궤적 없이"라고 적으면 오히려 그 낱말이 내용으로 읽혀서, 빼는 건 이 노드로만 한다.
    def neg(wf):
        return comfy.add_negative(wf) if info.get("neg_node") and not fx else wf

    video = None
    if m["source"] == "video":
        job.message = "레퍼런스 영상 준비 중"
        prepared, _ = prepare_reference_video(mdir / m["video"], mdir / "reference_24fps.mp4", max_side=size[0])
        video = comfy.upload(server, prepared, f"{pid}_{mid}_ref.mp4")

    def direct_wf(d):
        first = comfy.upload(server, mdir / "first" / f"{d}.png", f"{pid}_{mid}_{d}.png")
        prefix = f"spritegen/{pid}/{mid}_{d}"
        if video:
            prompt = reference_prompt(m["kind"], s["angle"], d, m.get("text", ""), s["style"], fx)
            # 터보(4스텝)는 영상 속 사람이 보는 방향까지 베껴서, 방향을 다시 잡는 20스텝으로 만든다
            wf = comfy.r2v_workflow(first, video, prompt, *size, length, seed, prefix,
                                    turbo=False, guides=end_guides(first))
        else:
            prompt = motion_prompt(m["kind"], m["text"], s["angle"], d, s["style"], fx, hold_end)
            wf = comfy.i2v_workflow(first, None if hold_end else first, prompt, *size, length, seed, prefix)
        (mdir / "first" / f"{d}.prompt.txt").write_text(prompt, encoding="utf-8")
        return d, neg(wf)

    if phase == "master":
        job.parts = {master: {"state": "queued", "sec": 0}}
        if not _generate(job, server, [direct_wf(master)], mdir):
            return
        job.message = "마스터 영상 정리 중"
        build_master_reference(mdir / "frames" / master, mdir / "master_ref.mp4")
        _set_motion(pid, mid, status="review")
        job.message = "마스터 확인 대기"
        return

    if phase == "mannequin":
        if not has_mannequin_motion(mdir):
            raise RuntimeError("마네킹 키프레임이 없어요. 키프레임부터 다시 짜 주세요")
        if not info.get("r2v"):
            raise RuntimeError("지금 영상 AI에는 레퍼런스 영상 따라 하기 기능이 없어요 (H3면 ref2va 모델, 사용자 워크플로면 r2v.json)")
        job.message = "방향별 마네킹 영상 렌더링 중"
        refs_mq = render_mannequin_refs(pid, mid, targets, meta, server)
        job.parts = {d: {"state": "queued", "sec": 0} for d in targets}
        items = []
        for d in targets:
            first = comfy.upload(server, mdir / "first" / f"{d}.png", f"{pid}_{mid}_{d}.png")
            prompt = mannequin_prompt(s["angle"], d, m.get("text", ""), s["style"], fx, gray=gray)
            (mdir / "first" / f"{d}.prompt.txt").write_text(prompt, encoding="utf-8")
            # 레퍼런스가 이미 그 방향에서 본 영상이라, 그대로 따라 하는 터보(4스텝)가 오히려 맞다
            items.append((d, neg(comfy.r2v_workflow(first, refs_mq[d], prompt, *size, length, seed,
                                                    f"spritegen/{pid}/{mid}_{d}", turbo=info.get("turbo_r2v", False),
                                                    guides=end_guides(first)))))
        if not _generate(job, server, items, mdir, expect_magenta=not gray):
            return
    elif phase == "rest":
        if not (mdir / "master_ref.mp4").exists():
            raise RuntimeError("마스터 영상이 없어요. 마스터부터 다시 만들어 주세요")
        if not info.get("r2v"):
            raise RuntimeError("지금 영상 AI에는 레퍼런스 영상 따라 하기 기능이 없어요 (H3면 ref2va 모델, 사용자 워크플로면 r2v.json)")
        ref = comfy.upload(server, mdir / "master_ref.mp4", f"{pid}_{mid}_master.mp4")
        others = [d for d in targets if d != master]
        redo_master = bool(only) and master in targets  # 마스터 방향 자체를 다시 만들 때는 처음처럼 바로 만든다
        job.parts = {} if redo_master else {master: {"state": "done", "sec": 0}}
        job.parts.update({d: {"state": "queued", "sec": 0} for d in ([master] if redo_master else []) + others})
        items = [direct_wf(master)] if redo_master else []
        for d in others:
            first = comfy.upload(server, mdir / "first" / f"{d}.png", f"{pid}_{mid}_{d}.png")
            prompt = follow_prompt(m["kind"], s["angle"], d, m.get("text", ""), s["style"], fx)
            (mdir / "first" / f"{d}.prompt.txt").write_text(prompt, encoding="utf-8")
            # 4스텝 터보는 레퍼런스의 보는 방향까지 그대로 베껴서(옆모습 마스터 → 정면도 옆모습), 20스텝으로 만든다
            items.append((d, neg(comfy.r2v_workflow(first, ref, prompt, *size, length, seed,
                                                    f"spritegen/{pid}/{mid}_{d}", turbo=False,
                                                    guides=[(first, 0), (first, -1)]))))
        if not _generate(job, server, items, mdir):
            return
    else:
        job.parts = {d: {"state": "queued", "sec": 0} for d in targets}
        if not _generate(job, server, [direct_wf(d) for d in targets], mdir):
            return

    job.message = "스프라이트 시트로 정리하는 중"
    extra = {"master": master if phase == "rest" else None, "phase": phase}
    if only:
        extra = {"redone": targets}
    assemble_motion(pid, mid, extra)


LOCOMOTION_WORDS = ("걷", "달리", "뛰", "행진", "질주", "walk", "run", "jog", "march", "sprint")


def is_locomotion(m):
    """걷기·달리기처럼 실제 게임에서 캐릭터를 움직이며 쓰는 반복 동작인지 (이동 속도를 계산한다)."""
    if m.get("key") in ("walk", "run"):
        return True
    text = f"{m.get('name', '')} {m.get('text', '')}".lower()
    return m["kind"] == "loop" and m.get("key") not in ("idle",) and any(w in text for w in LOCOMOTION_WORDS)


def assemble_motion(pid, mid, extra=None):
    """만든 H3 프레임으로 스프라이트 시트를 (다시) 만든다. 생성 직후와 '다른 장면으로 바꾸기' 뒤에 쓴다."""
    p = store.load(pid)
    m = next(x for x in p["motions"] if x["id"] == mid)
    s = m["settings"]
    pdir = store.project_dir(pid)
    mdir = pdir / "motions" / mid
    gen = generated_directions(s["count"], s["mirror"])
    oneshot = m["kind"] == "oneshot"
    sheet_rgb = np.asarray(Image.open(pdir / m.get("sheet", p["sheet"]["file"])).convert("RGB"))
    char_h, bottom = frame_fit(m, s, gen, mdir)
    size = motion_frame_size(m)
    _, meta = first_frames(sheet_rgb, gen, size, char_height=char_h, bottom_margin=bottom)
    # 모든 방향이 같은 박자를 따르는 모드는 한 번 동작을 같은 구간으로 자른다 (칸끼리 시점이 맞게)
    window = span = None
    length = comfy.frames_for_seconds(m.get("seconds", 5))
    if m.get("mode") == "mannequin" and has_mannequin_motion(mdir):
        poses, period = mannequin_poses(m, mdir, length)
        if oneshot:
            window = mq.motion_window_poses(poses)
        else:                                          # 반복 마네킹: 동작 전체(키프레임·영상 길이)가 한 바퀴
            span = (0, period)
    master = m.get("master") or pick_master(gen)
    refs = [load_ref(mdir / "first" / f"{d}.png") for d in gen] if s["style"] == "pixel" else None
    pixel_h = pixel_height_for(p, m, sheet_rgb)
    report = assemble({d: mdir / "frames" / d for d in gen}, s["count"], size, meta["feet_y"], mdir / "out",
                      kind=m["kind"], n_frames=m.get("frames", 8),
                      pixel_height=pixel_h, palette_refs=refs,
                      strip_effects=effects_of(m) == "strip",
                      window=window, window_from=master if oneshot and m.get("mode") == "master" else None,
                      char_px=char_h * size[1], overrides=m.get("frame_overrides"),
                      hold_end=oneshot and m.get("hold_end", False), effects=effects_of(m), loop_span=span,
                      matting=matting.enabled(), locomotion=is_locomotion(m),
                      keep_heads=s["style"] == "pixel" and store.load_config().get("pixel_keep_head", True), move_scale=float(m.get("move_scale") or 1.0),
                      ground_y=max(0.25, float(np.sin(np.radians(mannequin_elevation(s["angle"]))))),
                      loop_from=("S" if "S" in gen else master)        # 박자 기준은 정면 (옆모습은 실루엣 신호가 달라 어긋남을 못 잰다)
                      if not oneshot and (m.get("source") == "video" or m.get("mode") in ("mannequin", "master")) else None)
    if m.get("play_fps"):                            # 사용자가 정해 둔 재생 속도는 다시 만들어도 그대로
        retime(mdir / "out", s["count"], m["play_fps"])

    def upd(pr):
        mm = next(x for x in pr["motions"] if x["id"] == mid)
        mm["status"] = "done"
        res = dict(mm.get("result") or {})
        res.update({"dir": f"motions/{mid}/out", "report": report, "finished": store.now(), "generated": gen,
                    "pixel_height": pixel_h or None})
        res.update(extra or {})
        mm["result"] = res
    store.update(pid, upd)
    return report


def start_motion(pid, mid, server, phase="all", only=None):
    job = Job("motion", pid, mid, label="redo" if only else phase)

    def fn(j):
        try:
            run_motion(j, pid, mid, server, phase, only)
        except Exception as e:
            # 한 방향 다시 만들기가 실패해도 예전 시트는 그대로 쓸 수 있게 '완성'으로 돌려 둔다
            fields = ({"status": "done", "redo_error": None if j.cancelled else str(e)} if only
                      else {"status": "cancelled" if j.cancelled else "error"})
            store.update(pid, lambda pr: next(x for x in pr["motions"] if x["id"] == mid).update(**fields))
            if only and getattr(j, "version", None):
                drop_version(pid, mid, j.version)
            raise
    return JOBS.submit(job, fn)


def start_keyframes(pid, mid, server=None):
    job = Job("motion", pid, mid, label="keys")

    def fn(j):
        try:
            make_keyframes(j, pid, mid, server)
        except Exception:
            _set_motion(pid, mid, status="error")
            raise
    return JOBS.submit(job, fn)


def start_sheet(pid):
    return JOBS.submit(Job("sheet", pid, label="방향 그림"), lambda j: make_sheet(j, pid))


def cancel(job, server):
    job.cancelled = True
    for prompt_id in job.prompt_ids:
        comfy.cancel(server, prompt_id)
