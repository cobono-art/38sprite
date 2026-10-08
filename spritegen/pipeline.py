"""작업 실행: 방향 그림 만들기(Codex) → 방향별 동작 영상(H3) → 스프라이트 시트."""
import json
import random
import threading
import time
import traceback
import uuid

import cv2
import numpy as np
from PIL import Image

from . import codex, comfy
from . import project as store
from .assemble import assemble, retime
from .directions import detect_cells, directions_for, first_frames, generated_directions
from .effects import remove_effects
from .imaging import KEY_MAGENTA, cutout_any, estimate_bg, frame_alpha, frames_to_webp, load_frames, load_ref
from .prompts import follow_prompt, mannequin_prompt, motion_prompt, reference_prompt, sheet_prompt
from . import mannequin as mq

EXAMPLES = __import__("pathlib").Path(__file__).resolve().parent / "examples"

FRAME_SIZE = (640, 640)


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
    try:
        detect_cells(np.asarray(Image.open(out).convert("RGB")), dirs)
    except ValueError as e:
        rec["problem"] = str(e)

    def upd(pr):
        pr["sheets"].append(rec)
        pr["sheet"] = rec
    store.update(pid, upd)
    if rec["problem"]:
        raise RuntimeError(rec["problem"] + " — 다시 그려 주세요")


def use_uploaded_sheet(pid, data, suffix):
    """사용자가 직접 그린 방향 시트(3x3 나침반 배치)를 쓴다."""
    p = store.load(pid)
    pdir = store.project_dir(pid)
    (pdir / "sheets").mkdir(exist_ok=True)
    out = pdir / "sheets" / f"sheet_{len(p['sheets']) + 1}_upload{suffix}"
    out.write_bytes(data)
    rec = {"file": f"sheets/{out.name}", "settings": dict(p["settings"]), "created": store.now(),
           "problem": None, "uploaded": True}
    try:
        detect_cells(np.asarray(Image.open(out).convert("RGB")), directions_for(p["settings"]["count"]))
    except ValueError as e:
        rec["problem"] = str(e)

    def upd(pr):
        pr["sheets"].append(rec)
        pr["sheet"] = rec
    return store.update(pid, upd)


# ---------- 동작 ----------

def prepare_reference_video(src, dst, max_sec=5.0, max_side=640):
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


def make_keyframes(job, pid, mid):
    """3D 마네킹 모드 1단계: Codex가 동작 설명으로 키프레임을 짜고, 확인용 미리보기를 만든다."""
    p = store.load(pid)
    m = next(x for x in p["motions"] if x["id"] == mid)
    s = m["settings"]
    mdir = store.project_dir(pid) / "motions" / mid
    mdir.mkdir(parents=True, exist_ok=True)
    job.message = "Codex가 마네킹 키프레임을 짜는 중이에요 (보통 1분 안팎)"
    data = mq.codex_keyframes(m["text"], m["kind"], EXAMPLES / "oneshot_slash.json", mdir,
                              log_path=mdir / "keyframes.log")
    (mdir / "keys.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    job.message = "마네킹 미리보기 만드는 중"
    gen = generated_directions(s["count"], s["mirror"])
    rows = {}
    for d in gen:
        frames = [mq.render(mq.skeleton(mq.interpolate(data["keys"], t / 8)), mq.FACING_YAW[d], s["angle"], 256,
                            scale=95, center=(0.5, 0.9)) for t in range(0, 42)]
        rows[d] = [np.dstack([f, np.full(f.shape[:2], 255, np.uint8)]) for f in frames]
    from .assemble import layout_frames
    from .imaging import save_gif
    save_gif(layout_frames(rows, s["count"], gap=4), 8, mdir / "keys_preview.gif")
    _set_motion(pid, mid, status="keys_review")
    job.message = "키프레임 확인 대기"


# 마네킹 레퍼런스 영상은 회색 배경으로: 마젠타로 그리면 H3(R2V)가 마젠타·초록 얼룩무늬 배경을 섞어 그려
# 캐릭터를 오려 낼 수 없게 된다. 캐릭터 첫 프레임(가이드)도 마네킹 모드에선 회색이다 (run_motion) — 둘이 같아야 깨끗하다.
MANNEQUIN_BG = (128, 128, 128)


def render_mannequin_refs(pid, mid, gen, meta, server):
    """방향마다 그 방향에서 본 마네킹 영상을 만들어 올린다. 캐릭터 첫 프레임과 키·발 높이를 맞춘다."""
    p = store.load(pid)
    m = next(x for x in p["motions"] if x["id"] == mid)
    s = m["settings"]
    mdir = store.project_dir(pid) / "motions" / mid
    keys = json.loads((mdir / "keys.json").read_text(encoding="utf-8"))["keys"]
    W, H = FRAME_SIZE
    char_px = meta["char_px"]                          # 첫 프레임 캐릭터와 같은 크기로
    cos_e = max(0.3, np.cos(np.radians(s["angle"])))
    scale = 0.9 * char_px / (1.62 * cos_e + 0.15)
    length = comfy.frames_for_seconds(m.get("seconds", 5))
    names = {}
    for d in gen:
        frames = [mq.render(mq.skeleton(mq.interpolate(keys, i / comfy.FPS)), mq.FACING_YAW[d], s["angle"], W,
                            scale=scale, center=(0.5, meta["feet_y"] / H), bg=MANNEQUIN_BG) for i in range(length)]
        path = mq.save_mp4(frames, mdir / f"mannequin_{d}.mp4")
        names[d] = comfy.upload(server, path, f"{pid}_{mid}_mq_{d}.mp4")
    return names


def _generate(job, server, items, mdir):
    """items: [(방향, 워크플로)] — 큐에 넣고 순서대로 받아 frames/<방향>과 raw/<방향>.webp로 저장한다."""
    client = uuid.uuid4().hex
    queued = []
    for d, wf in items:
        prompt_id = comfy.queue(server, wf, client)
        job.prompt_ids.append(prompt_id)
        queued.append((d, prompt_id))
    for i, (d, prompt_id) in enumerate(queued):
        if job.cancelled:
            return False
        job.message = f"영상 AI 생성 중: {d} ({i + 1}/{len(queued)})"

        def tick(state, sec, d=d):
            job.parts[d] = {"state": state, "sec": round(sec)}
        entry, sec = comfy.wait(server, prompt_id, on_tick=tick)
        frames_dir = mdir / "frames" / d
        if frames_dir.exists():
            for f in frames_dir.glob("*.png"):
                f.unlink()
        comfy.download(server, entry, frames_dir)
        (mdir / "raw").mkdir(exist_ok=True)
        frames_to_webp(frames_dir, mdir / "raw" / f"{d}.webp", scale=0.5)
        job.parts[d] = {"state": "done", "sec": round(sec)}
        job.progress = 0.05 + 0.85 * (i + 1) / len(queued)
    return not job.cancelled


def frame_fit(m, s, gen, mdir):
    """영상 속 캐릭터 크기와 발 위치 (화면 높이에 대한 비율). 마네킹 공격은 동작을 미리 알아서,
    칼끝까지 화면 안에 들어오는 가장 큰 크기를 계산한다. 나머지 공격은 넉넉히 작게, 반복 동작은 크게."""
    if m["kind"] == "oneshot" and m.get("mode") == "mannequin" and (mdir / "keys.json").exists():
        keys = json.loads((mdir / "keys.json").read_text(encoding="utf-8"))["keys"]
        return mq.fit_frame(keys, [mq.FACING_YAW[d] for d in gen], s["angle"],
                            comfy.frames_for_seconds(m.get("seconds", 5)))
    return (0.52, 0.14) if m["kind"] == "oneshot" else (0.72, 0.12)


def _set_motion(pid, mid, **fields):
    store.update(pid, lambda pr: next(x for x in pr["motions"] if x["id"] == mid).update(**fields))


def run_motion(job, pid, mid, server, phase="all"):
    """phase: 'all'(방향별 바로) | 'master'(마스터 방향만 만들고 확인 대기) | 'rest'(마스터를 따라 나머지 방향)."""
    p = store.load(pid)
    pdir = store.project_dir(pid)
    m = next(x for x in p["motions"] if x["id"] == mid)
    s = m["settings"]
    if not p.get("sheet"):
        raise RuntimeError("먼저 방향 그림을 만들어 주세요")
    mdir = pdir / "motions" / mid
    gen = generated_directions(s["count"], s["mirror"])
    oneshot = m["kind"] == "oneshot"
    master = m.get("master") or pick_master(gen)

    job.message = "방향별 첫 프레임 만드는 중"
    sheet_rgb = np.asarray(Image.open(pdir / m.get("sheet", p["sheet"]["file"])).convert("RGB"))
    char_h, bottom = frame_fit(m, s, gen, mdir)
    # 마젠타 크로마키 배경에 깨끗하게 오린 캐릭터를 놓는다 (회색 배경보다 분리가 깨끗하다).
    # 마네킹 모드만은 회색: 첫 프레임(마젠타)과 마네킹 영상(회색) 배경이 다르면 R2V가 둘을 섞어 얼룩무늬 배경을 그린다.
    mannequin = m.get("mode") == "mannequin"
    firsts, meta = first_frames(sheet_rgb, gen, FRAME_SIZE, char_height=char_h, bottom_margin=bottom,
                                resample=Image.NEAREST if s["style"] == "pixel" else Image.LANCZOS,
                                bg_color=None if mannequin else KEY_MAGENTA)
    meta["char_px"] = char_h * FRAME_SIZE[1]
    (mdir / "first").mkdir(parents=True, exist_ok=True)
    for d, im in firsts.items():
        im.save(mdir / "first" / f"{d}.png")

    length = comfy.frames_for_seconds(m.get("seconds", 5))
    fx = not m.get("strip_effects", False)          # 이펙트를 지우지 않는 동작은 반짝이·빛을 화려하게 그린다
    seed = m.get("seed") or random.randint(1, 2**31)
    # 새로 만드는 프레임에는 예전에 바꿔 둔 장면 번호가 맞지 않으니 지운다
    _set_motion(pid, mid, seed=seed, master=master, frame_overrides=None)
    info = comfy.check(server)
    video = None
    if m["source"] == "video":
        job.message = "레퍼런스 영상 준비 중"
        prepared, _ = prepare_reference_video(mdir / m["video"], mdir / "reference_24fps.mp4")
        video = comfy.upload(server, prepared, f"{pid}_{mid}_ref.mp4")

    def direct_wf(d):
        first = comfy.upload(server, mdir / "first" / f"{d}.png", f"{pid}_{mid}_{d}.png")
        prefix = f"spritegen/{pid}/{mid}_{d}"
        if video:
            prompt = reference_prompt(m["kind"], s["angle"], d, m.get("text", ""), s["style"], fx)
            # 터보(4스텝)는 영상 속 사람이 보는 방향까지 베껴서, 방향을 다시 잡는 20스텝으로 만든다
            wf = comfy.r2v_workflow(first, video, prompt, *FRAME_SIZE, length, seed, prefix,
                                    turbo=False, guides=[(first, 0), (first, -1)])
        else:
            prompt = motion_prompt(m["kind"], m["text"], s["angle"], d, s["style"], fx)
            wf = comfy.i2v_workflow(first, first, prompt, *FRAME_SIZE, length, seed, prefix)
        (mdir / "first" / f"{d}.prompt.txt").write_text(prompt, encoding="utf-8")
        return d, wf

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
        if not (mdir / "keys.json").exists():
            raise RuntimeError("마네킹 키프레임이 없어요. 키프레임부터 다시 짜 주세요")
        if not info.get("r2v"):
            raise RuntimeError("지금 영상 AI에는 레퍼런스 영상 따라 하기 기능이 없어요 (H3면 ref2va 모델, 사용자 워크플로면 r2v.json)")
        job.message = "방향별 마네킹 영상 렌더링 중"
        refs_mq = render_mannequin_refs(pid, mid, gen, meta, server)
        job.parts = {d: {"state": "queued", "sec": 0} for d in gen}
        items = []
        for d in gen:
            first = comfy.upload(server, mdir / "first" / f"{d}.png", f"{pid}_{mid}_{d}.png")
            prompt = mannequin_prompt(s["angle"], d, m.get("text", ""), s["style"], fx)
            (mdir / "first" / f"{d}.prompt.txt").write_text(prompt, encoding="utf-8")
            # 레퍼런스가 이미 그 방향에서 본 영상이라, 그대로 따라 하는 터보(4스텝)가 오히려 맞다
            items.append((d, comfy.r2v_workflow(first, refs_mq[d], prompt, *FRAME_SIZE, length, seed,
                                                f"spritegen/{pid}/{mid}_{d}", turbo=info.get("turbo_r2v", False),
                                                guides=[(first, 0), (first, -1)])))
        if not _generate(job, server, items, mdir):
            return
    elif phase == "rest":
        if not (mdir / "master_ref.mp4").exists():
            raise RuntimeError("마스터 영상이 없어요. 마스터부터 다시 만들어 주세요")
        if not info.get("r2v"):
            raise RuntimeError("지금 영상 AI에는 레퍼런스 영상 따라 하기 기능이 없어요 (H3면 ref2va 모델, 사용자 워크플로면 r2v.json)")
        ref = comfy.upload(server, mdir / "master_ref.mp4", f"{pid}_{mid}_master.mp4")
        others = [d for d in gen if d != master]
        job.parts = {master: {"state": "done", "sec": 0}}
        job.parts.update({d: {"state": "queued", "sec": 0} for d in others})
        items = []
        for d in others:
            first = comfy.upload(server, mdir / "first" / f"{d}.png", f"{pid}_{mid}_{d}.png")
            prompt = follow_prompt(m["kind"], s["angle"], d, m.get("text", ""), s["style"], fx)
            (mdir / "first" / f"{d}.prompt.txt").write_text(prompt, encoding="utf-8")
            # 4스텝 터보는 레퍼런스의 보는 방향까지 그대로 베껴서(옆모습 마스터 → 정면도 옆모습), 20스텝으로 만든다
            items.append((d, comfy.r2v_workflow(first, ref, prompt, *FRAME_SIZE, length, seed,
                                                f"spritegen/{pid}/{mid}_{d}", turbo=False,
                                                guides=[(first, 0), (first, -1)])))
        if not _generate(job, server, items, mdir):
            return
    else:
        job.parts = {d: {"state": "queued", "sec": 0} for d in gen}
        if not _generate(job, server, [direct_wf(d) for d in gen], mdir):
            return

    job.message = "스프라이트 시트로 정리하는 중"
    assemble_motion(pid, mid, {"master": master if phase == "rest" else None, "phase": phase})


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
    _, meta = first_frames(sheet_rgb, gen, FRAME_SIZE, char_height=char_h, bottom_margin=bottom)
    # 모든 방향이 같은 박자를 따르는 모드는 한 번 동작을 같은 구간으로 자른다 (칸끼리 시점이 맞게)
    window = None
    if oneshot and m.get("mode") == "mannequin" and (mdir / "keys.json").exists():
        window = mq.motion_window(json.loads((mdir / "keys.json").read_text(encoding="utf-8"))["keys"],
                                  comfy.frames_for_seconds(m.get("seconds", 5)))
    master = m.get("master") or pick_master(gen)
    refs = [load_ref(mdir / "first" / f"{d}.png") for d in gen] if s["style"] == "pixel" else None
    report = assemble({d: mdir / "frames" / d for d in gen}, s["count"], FRAME_SIZE, meta["feet_y"], mdir / "out",
                      kind=m["kind"], n_frames=m.get("frames", 8),
                      pixel_height=s["pixel_height"] if s["style"] == "pixel" else 0, palette_refs=refs,
                      strip_effects=m.get("strip_effects", False),
                      window=window, window_from=master if oneshot and m.get("mode") == "master" else None,
                      char_px=char_h * FRAME_SIZE[1], overrides=m.get("frame_overrides"),
                      loop_from=("S" if "S" in gen else master)        # 박자 기준은 정면 (옆모습은 실루엣 신호가 달라 어긋남을 못 잰다)
                      if not oneshot and (m.get("source") == "video" or m.get("mode") in ("mannequin", "master")) else None)
    if m.get("play_fps"):                            # 사용자가 정해 둔 재생 속도는 다시 만들어도 그대로
        retime(mdir / "out", s["count"], m["play_fps"])

    def upd(pr):
        mm = next(x for x in pr["motions"] if x["id"] == mid)
        mm["status"] = "done"
        res = dict(mm.get("result") or {})
        res.update({"dir": f"motions/{mid}/out", "report": report, "finished": store.now(), "generated": gen})
        res.update(extra or {})
        mm["result"] = res
    store.update(pid, upd)
    return report


def start_motion(pid, mid, server, phase="all"):
    job = Job("motion", pid, mid, label=phase)

    def fn(j):
        try:
            run_motion(j, pid, mid, server, phase)
        except Exception:
            store.update(pid, lambda pr: next(x for x in pr["motions"] if x["id"] == mid).update(status="error"))
            raise
    return JOBS.submit(job, fn)


def start_keyframes(pid, mid):
    job = Job("motion", pid, mid, label="keys")

    def fn(j):
        try:
            make_keyframes(j, pid, mid)
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
