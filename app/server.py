"""38Sprite 로컬 웹 서버.

ComfyUI에 딸린 파이썬(aiohttp·numpy·opencv·PIL 포함)으로 실행하면 따로 설치할 것이 없다.
  run_app.bat  또는  <ComfyUI>\\python_embeded\\python.exe -s app\\server.py --open
"""
import argparse
import asyncio
import io
import json
import sys
import time
import urllib.parse
import uuid
import webbrowser
import zipfile
from pathlib import Path

from aiohttp import web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spritegen import codex, comfy, export, matting  # noqa: E402
from spritegen import project as store  # noqa: E402
from spritegen.assemble import retime  # noqa: E402
from spritegen.directions import NAME_KO, SHEET_ORDER, generated_directions, preview_layout, source_of  # noqa: E402
from spritegen.pipeline import (JOBS, MOTION_SET, assemble_motion, cancel, default_seconds, pose_tools,  # noqa: E402
                                start_keyframes, start_motion, start_redraw, start_sheet, swap_version,
                                use_uploaded_sheet)
from spritegen.prompts import ANGLE_PRESETS, EFFECT_WORDS, auto_effects  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
routes = web.RouteTableDef()


@web.middleware
async def no_cache(request, handler):
    """화면 파일을 고치면 바로 반영되게 캐시하지 않는다."""
    resp = await handler(request)
    if request.path == "/" or request.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


ALLOWED_HOSTS = set()                                  # main()에서 채운다: 127.0.0.1:포트, localhost:포트


@web.middleware
async def same_origin(request, handler):
    """이 앱 화면에서 온 요청만 받는다. 다른 사이트가 몰래 작업을 시키거나 결과를 읽어 가지 못하게."""
    origin = request.headers.get("Origin")
    if request.host not in ALLOWED_HOSTS or (origin is not None and origin.split("://", 1)[-1] not in ALLOWED_HOSTS):
        return bad("이 앱 화면에서 온 요청만 받아요", 403)
    return await handler(request)


def bad(msg, status=400):
    return web.json_response({"error": msg}, status=status)


async def blocking(fn, *args):
    return await asyncio.get_running_loop().run_in_executor(None, fn, *args)


async def read_form(request):
    """multipart 폼을 {이름: 문자열 또는 (파일명, bytes)}로 읽는다."""
    out = {}
    reader = await request.multipart()
    async for part in reader:
        if part.filename:
            out[part.name] = (part.filename, await part.read(decode=False))
        else:
            raw = await part.read(decode=False)
            for enc in ("utf-8", "cp949"):              # 브라우저는 UTF-8, 윈도우 터미널은 cp949로 보내기도 한다
                try:
                    out[part.name] = raw.decode(enc).strip()
                    break
                except UnicodeDecodeError:
                    continue
            else:
                out[part.name] = raw.decode("utf-8", "replace").strip()
    return out


def project_view(p):
    p = dict(p)
    p["active_jobs"] = JOBS.active_for(p["id"])
    s = p["settings"]
    p["plan"] = {"order": SHEET_ORDER[s["count"]], "generated": generated_directions(s["count"], s["mirror"]),
                 "layout": preview_layout(s["count"])}
    return p


@routes.get("/")
async def index(_):
    return web.FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@routes.get("/api/status")
async def status(_):
    cfg = store.load_config()
    comfy_info, codex_info = await asyncio.gather(blocking(comfy.check, cfg["comfy_url"]), blocking(codex.check))
    return web.json_response({"config": cfg, "comfy": comfy_info, "codex": codex_info,
                              "presets": ANGLE_PRESETS, "dir_names": NAME_KO, "effect_words": EFFECT_WORDS,
                              "pose": pose_tools() is not None, "matting": matting.enabled()})


@routes.post("/api/config")
async def set_config(request):
    body = await request.json()
    cfg = store.load_config()
    url = str(body.get("comfy_url", "")).strip().rstrip("/")
    if not url.startswith("http"):
        return bad("ComfyUI 주소는 http://로 시작해야 해요")
    cfg["comfy_url"] = url
    store.save_config(cfg)
    return web.json_response(cfg)


@routes.get("/api/projects")
async def projects(_):
    return web.json_response(store.list_all())


@routes.post("/api/projects")
async def create_project(request):
    form = await read_form(request)
    if "file" not in form:
        return bad("삼면도 이미지를 올려 주세요")
    name, data = form["file"]
    suffix = Path(name).suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
        return bad("PNG, JPG, WEBP 이미지만 올릴 수 있어요")
    p = store.create(form.get("name") or Path(name).stem, data, suffix)
    return web.json_response(project_view(p))


@routes.get("/api/projects/{pid}")
async def get_project(request):
    try:
        return web.json_response(project_view(store.load(request.match_info["pid"])))
    except (OSError, ValueError):
        return bad("프로젝트를 찾지 못했어요", 404)


@routes.post("/api/projects/{pid}/settings")
async def set_settings(request):
    pid = request.match_info["pid"]
    body = await request.json()
    try:
        angle = max(0, min(80, int(body["angle"])))
        count = int(body["count"])
        style = body["style"]
        px = int(body.get("pixel_height", 64))
        if count not in (8, 4, 2) or style not in ("hd", "pixel") or not 24 <= px <= 160:
            raise ValueError
    except (KeyError, ValueError, TypeError):
        return bad("설정 값이 올바르지 않아요")
    settings = {"angle": angle, "count": count, "mirror": bool(body.get("mirror", True)), "style": style,
                "pixel_height": px}
    p = store.update(pid, lambda pr: pr.update(settings=settings))
    return web.json_response(project_view(p))


@routes.post("/api/projects/{pid}/sheet")
async def make_sheet(request):
    pid = request.match_info["pid"]
    info = await blocking(codex.check)
    if not info["ok"]:
        return bad(info.get("error", "Codex를 쓸 수 없어요"))
    return web.json_response(start_sheet(pid).to_dict())


@routes.post("/api/projects/{pid}/sheet/redraw")
async def redraw_sheet_cell(request):
    """방향 그림에서 한 방향만 Codex로 다시 그린다 (새 방향 그림으로 저장되고, 예전 그림은 기록에 남는다)."""
    pid = request.match_info["pid"]
    try:
        d = (await request.json()).get("dir")
    except json.JSONDecodeError:
        d = None
    p = store.load(pid)
    if not p.get("sheet"):
        return bad("먼저 방향 그림을 만들어 주세요")
    if d not in SHEET_ORDER[p["sheet"]["settings"]["count"]]:
        return bad("없는 방향이에요")
    info = await blocking(codex.check)
    if not info["ok"]:
        return bad(info.get("error", "Codex를 쓸 수 없어요"))
    return web.json_response(start_redraw(pid, d).to_dict())


@routes.post("/api/projects/{pid}/sheet/upload")
async def upload_sheet(request):
    pid = request.match_info["pid"]
    form = await read_form(request)
    if "file" not in form:
        return bad("방향 그림 파일을 올려 주세요")
    name, data = form["file"]
    p = await blocking(use_uploaded_sheet, pid, data, Path(name).suffix.lower() or ".png")
    return web.json_response(project_view(p))


@routes.post("/api/projects/{pid}/sheet/select")
async def select_sheet(request):
    pid = request.match_info["pid"]
    file = (await request.json()).get("file")

    def pick(pr):
        rec = next((s for s in pr["sheets"] if s["file"] == file), None)
        if rec:
            pr["sheet"] = rec
    return web.json_response(project_view(store.update(pid, pick)))


NO_R2V = "지금 영상 AI에는 레퍼런스 영상 따라 하기 기능이 없어요 (H3면 ref2va 모델, 사용자 워크플로면 r2v.json)"


def effects_from(form, text):
    """빛 효과 방식 (none | vivid | strip). 예전 화면의 strip_effects 체크박스로 온 요청도 받고, 없으면 설명으로 고른다."""
    if form.get("effects") in ("none", "vivid", "strip"):
        return form["effects"]
    if "strip_effects" in form:
        return "strip" if form["strip_effects"] == "1" else "vivid"
    return auto_effects(text)


def new_motion(pid, cfg, fields, video=None):
    """동작을 기록하고 작업을 건다. fields: name, kind, source, text, frames, effects, mode (+ key, hold_end, auto_continue)."""
    p = store.load(pid)
    mid = "m" + time.strftime("%m%d%H%M%S") + uuid.uuid4().hex[:4]
    mdir = store.project_dir(pid) / "motions" / mid
    mdir.mkdir(parents=True)
    seconds = default_seconds(fields["kind"], fields["mode"], fields.get("source", "text"), fields.get("hold_end", False))
    motion = {"id": mid, "video": None, "seconds": seconds, **fields, "strip_effects": fields["effects"] == "strip",
              "settings": dict(p["settings"]), "sheet": p["sheet"]["file"], "status": "running",
              "created": store.now(), "result": None}
    if video:
        vname, vdata = video
        motion["video"] = "reference" + (Path(vname).suffix.lower() or ".mp4")
        (mdir / motion["video"]).write_bytes(vdata)
    store.update(pid, lambda pr: pr["motions"].insert(0, motion))
    if motion["mode"] == "mannequin":
        job = start_keyframes(pid, mid, cfg["comfy_url"])
    else:
        job = start_motion(pid, mid, cfg["comfy_url"], "master" if motion["mode"] == "master" else "all")
    store.update(pid, lambda pr: next(x for x in pr["motions"] if x["id"] == mid).update(job=job.id))
    motion["job"] = job.id
    return motion, job


@routes.post("/api/projects/{pid}/motions")
async def create_motion(request):
    pid = request.match_info["pid"]
    form = await read_form(request)
    p = store.load(pid)
    if not p.get("sheet"):
        return bad("먼저 방향 그림을 만들어 주세요")
    cfg = store.load_config()
    source = form.get("source", "text")
    kind = form.get("kind", "loop")
    text = form.get("text", "")
    if kind not in ("loop", "oneshot") or source not in ("text", "video"):
        return bad("동작 종류가 올바르지 않아요")
    if source == "text" and not text:
        return bad("동작 설명을 적어 주세요")
    if source == "video" and "video" not in form:
        return bad("레퍼런스 영상을 올려 주세요")
    mode = form.get("mode") if form.get("mode") in ("master", "mannequin") else "direct"
    info = await blocking(comfy.check, cfg["comfy_url"])
    if not info["ok"]:
        return bad(info.get("error", "영상 AI(ComfyUI)를 쓸 수 없어요"))
    if (source == "video" or mode == "mannequin") and not info["r2v"]:
        return bad(NO_R2V)
    fields = {"name": form.get("name") or (text[:20] if text else "레퍼런스 동작"), "kind": kind, "source": source,
              "text": text, "frames": max(4, min(24, int(form.get("frames") or 8))),
              "effects": effects_from(form, text), "mode": mode}
    motion, job = await blocking(new_motion, pid, cfg, fields, form.get("video") if source == "video" else None)
    return web.json_response({"motion": motion, "job": job.to_dict()})


@routes.get("/api/motion_set")
async def motion_set_items(_):
    return web.json_response(MOTION_SET)


@routes.post("/api/projects/{pid}/motion_set")
async def create_motion_set(request):
    """기본 모션 세트(대기·걷기·달리기·공격·피격·쓰러짐)를 한 번에 건다. 공격·피격은 3D 마네킹을 확인 없이 이어서 만든다."""
    pid = request.match_info["pid"]
    try:
        keys = (await request.json()).get("keys") or [x["key"] for x in MOTION_SET]
    except json.JSONDecodeError:
        keys = [x["key"] for x in MOTION_SET]
    if not store.load(pid).get("sheet"):
        return bad("먼저 방향 그림을 만들어 주세요")
    cfg = store.load_config()
    info, cx = await asyncio.gather(blocking(comfy.check, cfg["comfy_url"]), blocking(codex.check))
    if not info["ok"]:
        return bad(info.get("error", "영상 AI(ComfyUI)를 쓸 수 없어요"))
    created = []
    for item in MOTION_SET:
        if item["key"] not in keys:
            continue
        # 마네킹은 Codex(키프레임)와 레퍼런스 따라 하기 모델이 필요하다. 없으면 방향별 바로 만든다
        mode = item["mode"] if item["mode"] != "mannequin" or (info["r2v"] and cx["ok"]) else "direct"
        fields = {"name": item["name"], "key": item["key"], "kind": item["kind"], "source": "text", "text": item["text"],
                  "frames": item["frames"], "effects": "none", "mode": mode, "hold_end": item.get("hold_end", False),
                  "auto_continue": True, "set": True}
        motion, _ = await blocking(new_motion, pid, cfg, fields)
        created.append(motion)
    if not created:
        return bad("만들 동작을 하나 이상 골라 주세요")
    return web.json_response({"motions": created})


@routes.post("/api/projects/{pid}/motions/{mid}/retry")
async def retry_motion(request):
    pid, mid = request.match_info["pid"], request.match_info["mid"]
    cfg = store.load_config()
    info = await blocking(comfy.check, cfg["comfy_url"])
    if not info["ok"]:
        return bad(info.get("error", "영상 AI(ComfyUI)를 쓸 수 없어요"))
    m = store.find_motion(store.load(pid), mid)
    store.update(pid, lambda pr: next(x for x in pr["motions"] if x["id"] == mid).update(status="running", result=None))
    if m.get("mode") == "mannequin":
        job = start_keyframes(pid, mid, cfg["comfy_url"])
    else:
        job = start_motion(pid, mid, cfg["comfy_url"], "master" if m.get("mode") == "master" else "all")
    store.update(pid, lambda pr: next(x for x in pr["motions"] if x["id"] == mid).update(job=job.id))
    return web.json_response(job.to_dict())


@routes.post("/api/projects/{pid}/motions/{mid}/continue")
async def continue_motion(request):
    """마스터 확인 후: 마스터를 따라 나머지 방향을 만든다."""
    pid, mid = request.match_info["pid"], request.match_info["mid"]
    cfg = store.load_config()
    m = store.find_motion(store.load(pid), mid)
    store.update(pid, lambda pr: next(x for x in pr["motions"] if x["id"] == mid).update(status="running"))
    job = start_motion(pid, mid, cfg["comfy_url"], "mannequin" if m.get("mode") == "mannequin" else "rest")
    store.update(pid, lambda pr: next(x for x in pr["motions"] if x["id"] == mid).update(job=job.id))
    return web.json_response(job.to_dict())


@routes.post("/api/projects/{pid}/motions/{mid}/rekeys")
async def rekeys_motion(request):
    """마네킹 동작이 마음에 안 들 때: Codex가 키프레임을 다시 짠다."""
    pid, mid = request.match_info["pid"], request.match_info["mid"]
    store.update(pid, lambda pr: next(x for x in pr["motions"] if x["id"] == mid).update(status="running"))
    job = start_keyframes(pid, mid)
    store.update(pid, lambda pr: next(x for x in pr["motions"] if x["id"] == mid).update(job=job.id))
    return web.json_response(job.to_dict())


@routes.post("/api/projects/{pid}/motions/{mid}/remaster")
async def remaster_motion(request):
    """마스터가 마음에 안 들 때: 새 시드로 마스터만 다시 만든다."""
    pid, mid = request.match_info["pid"], request.match_info["mid"]
    cfg = store.load_config()
    store.update(pid, lambda pr: next(x for x in pr["motions"] if x["id"] == mid).update(
        status="running", seed=None, result=None))
    job = start_motion(pid, mid, cfg["comfy_url"], "master")
    store.update(pid, lambda pr: next(x for x in pr["motions"] if x["id"] == mid).update(job=job.id))
    return web.json_response(job.to_dict())


@routes.post("/api/projects/{pid}/motions/{mid}/redo")
async def redo_direction(request):
    """후처리: 한 방향만 새 시드로 다시 만든다 (반전으로 채운 방향이면 원래 방향을). 나머지 방향 영상은 그대로 두고
    시트를 다시 조립한다. 그 칸을 방향 그림에서 고친 뒤라면 고친 그림으로 만든다."""
    pid, mid = request.match_info["pid"], request.match_info["mid"]
    m = _done_motion(pid, mid)
    if not m:
        return bad("다 만든 동작만 한 방향을 다시 만들 수 있어요")
    try:
        d = (await request.json()).get("dir")
    except json.JSONDecodeError:
        d = None
    s = m["settings"]
    if d not in SHEET_ORDER[s["count"]]:
        return bad("없는 방향이에요")
    src, _ = source_of(d, generated_directions(s["count"], s["mirror"]))
    cfg = store.load_config()
    info = await blocking(comfy.check, cfg["comfy_url"])
    if not info["ok"]:
        return bad(info.get("error", "영상 AI(ComfyUI)를 쓸 수 없어요"))
    phase = {"mannequin": "mannequin", "master": "rest"}.get(m.get("mode"), "all")
    store.update(pid, lambda pr: next(x for x in pr["motions"] if x["id"] == mid).update(status="running", redo_error=None))
    job = start_motion(pid, mid, cfg["comfy_url"], phase, only=[src])
    store.update(pid, lambda pr: next(x for x in pr["motions"] if x["id"] == mid).update(job=job.id))
    return web.json_response({"job": job.to_dict(), "dir": src})


@routes.post("/api/projects/{pid}/motions/{mid}/versions/{vid}/swap")
async def swap_motion_version(request):
    """후처리: '이 방향만 다시 만들기' 전 결과와 지금 결과를 맞바꾼다 (되돌리기 / 다시 앞으로)."""
    pid, mid, vid = request.match_info["pid"], request.match_info["mid"], request.match_info["vid"]
    if not _done_motion(pid, mid):
        return bad("다 만든 동작만 되돌릴 수 있어요")
    try:
        report = await blocking(swap_version, pid, mid, vid)
    except RuntimeError as e:
        return bad(str(e))
    return web.json_response({"report": report, "motion": store.find_motion(store.load(pid), mid)})


@routes.post("/api/projects/{pid}/motions/{mid}/speed")
async def set_speed(request):
    """후처리: 다 만든 동작의 재생 속도만 바꾼다 (H3로 다시 만들지 않고 시트 JSON과 GIF만 다시 씀)."""
    pid, mid = request.match_info["pid"], request.match_info["mid"]
    try:
        fps = float((await request.json()).get("fps", 0))
    except (ValueError, TypeError, json.JSONDecodeError):
        return bad("재생 속도가 올바르지 않아요")
    if not 0.5 <= fps <= 60:
        return bad("재생 속도가 올바르지 않아요")
    m = store.find_motion(store.load(pid), mid)
    if m.get("status") != "done" or not m.get("result"):
        return bad("다 만든 동작만 속도를 바꿀 수 있어요")
    await blocking(retime, store.project_dir(pid) / m["result"]["dir"], m["settings"]["count"], fps)
    store.update(pid, lambda pr: next(x for x in pr["motions"] if x["id"] == mid).update(play_fps=round(fps, 2)))
    return web.json_response({"fps": round(fps, 2)})


def _done_motion(pid, mid):
    m = store.find_motion(store.load(pid), mid)
    return m if m.get("status") == "done" and m.get("result") else None


@routes.get("/api/projects/{pid}/motions/{mid}/frames/{d}")
async def motion_frames(request):
    """'다른 장면으로 바꾸기'용: 그 방향(반전 방향이면 원래 방향)의 H3 영상 프레임 목록과 지금 고른 프레임."""
    pid, mid, d = request.match_info["pid"], request.match_info["mid"], request.match_info["d"]
    m = _done_motion(pid, mid)
    if not m:
        return bad("다 만든 동작만 장면을 바꿀 수 있어요")
    s = m["settings"]
    if d not in SHEET_ORDER[s["count"]]:
        return bad("없는 방향이에요")
    src, flip = source_of(d, generated_directions(s["count"], s["mirror"]))
    folder = store.project_dir(pid) / "motions" / mid / "frames" / src
    rep = m["result"]["report"]["directions"].get(src, {})
    return web.json_response({"dir": d, "source": src, "flip": flip, "fps": comfy.FPS,
                              "files": sorted(f.name for f in folder.glob("*.png")),
                              "picked": rep.get("picked", []),
                              "overrides": (m.get("frame_overrides") or {}).get(src, {})})


@routes.post("/api/projects/{pid}/motions/{mid}/frames")
async def swap_frame(request):
    """후처리: 한 칸을 영상의 다른 장면으로 바꾸고 시트를 다시 만든다. frame이 null이면 원래대로."""
    pid, mid = request.match_info["pid"], request.match_info["mid"]
    m = _done_motion(pid, mid)
    if not m:
        return bad("다 만든 동작만 장면을 바꿀 수 있어요")
    try:
        body = await request.json()
        slot = int(body["slot"])
        frame = None if body.get("frame") is None else int(body["frame"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return bad("바꿀 칸이 올바르지 않아요")
    s = m["settings"]
    if body.get("dir") not in SHEET_ORDER[s["count"]]:
        return bad("없는 방향이에요")
    src, _ = source_of(body["dir"], generated_directions(s["count"], s["mirror"]))

    def upd(pr):
        mm = next(x for x in pr["motions"] if x["id"] == mid)
        ov = dict(mm.get("frame_overrides") or {})
        slots = dict(ov.get(src) or {})
        if frame is None:
            slots.pop(str(slot), None)
        else:
            slots[str(slot)] = frame
        ov[src] = slots
        mm["frame_overrides"] = ov
    store.update(pid, upd)
    report = await blocking(assemble_motion, pid, mid)
    return web.json_response({"report": report})


def mark_interrupted():
    """서버가 꺼지면서 끊긴 동작을 '중단됨'으로 표시한다 (작업 정보는 메모리에만 있어서 다시 이어갈 수 없다)."""
    for item in store.list_all():
        def fix(pr):
            for m in pr["motions"]:
                if m.get("status") == "running":
                    m["status"] = "interrupted"
        store.update(item["id"], fix)


@routes.get("/api/jobs/{jid}")
async def get_job(request):
    job = JOBS.get(request.match_info["jid"])
    if not job:
        return bad("작업을 찾지 못했어요 (서버를 다시 켜면 진행 중이던 작업 정보는 사라져요)", 404)
    return web.json_response(job.to_dict())


@routes.post("/api/jobs/{jid}/cancel")
async def cancel_job(request):
    job = JOBS.get(request.match_info["jid"])
    if not job:
        return bad("작업을 찾지 못했어요", 404)
    await blocking(cancel, job, store.load_config()["comfy_url"])
    if job.mid and job.label != "redo":              # 한 방향 다시 만들기는 예전 시트가 그대로라 작업이 '완성'으로 돌린다
        store.update(job.pid, lambda pr: next(x for x in pr["motions"] if x["id"] == job.mid).update(status="cancelled"))
    return web.json_response(job.to_dict())


def zip_response(files, name):
    """files: [(ZIP 안 경로, 디스크 파일 Path 또는 bytes)]"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, src in files:
            if isinstance(src, bytes):
                z.writestr(arc, src)
            else:
                z.write(src, arc)
    return web.Response(body=buf.getvalue(), content_type="application/zip",
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(name)}"})


def motion_files(out, key, prefix=""):
    """동작 하나의 ZIP 내용: 결과 폴더(시트·JSON·GIF·report) + 엔진용 파일(Aseprite JSON, Godot, 프레임 PNG)."""
    files = [(prefix + f.name, f) for f in sorted(out.iterdir()) if f.is_file()]
    return files + [(prefix + arc, data) for arc, data in export.engine_files(out, key).items()]


@routes.get("/api/projects/{pid}/motions/{mid}/download")
async def download_motion(request):
    pid, mid = request.match_info["pid"], request.match_info["mid"]
    out = store.project_dir(pid) / "motions" / mid / "out"
    if not out.exists():
        return bad("아직 결과가 없어요", 404)
    p = store.load(pid)
    key = export.motion_key(store.find_motion(p, mid))
    files = await blocking(motion_files, out, key)
    return await blocking(zip_response, files, f"{p['name']}_{key}.zip")


@routes.get("/api/projects/{pid}/download")
async def download_project(request):
    """캐릭터 전체: 다 만든 동작마다 폴더 하나(엔진용 파일 포함) + 모든 동작을 합친 Godot SpriteFrames."""
    pid = request.match_info["pid"]
    p = store.load(pid)
    used, done = set(), []
    for m in reversed(p["motions"]):                   # 만든 순서대로
        out = store.project_dir(pid) / "motions" / m["id"] / "out"
        if m.get("status") == "done" and out.exists():
            done.append((export.motion_key(m, used), out))
    if not done:
        return bad("아직 다 만든 동작이 없어요", 404)

    def build():
        files = []
        for key, out in done:
            files += motion_files(out, key, f"{key}/")
        files += list(export.project_godot(done).items())
        return files
    return await blocking(zip_response, await blocking(build), f"{p['name']}_all.zip")


@routes.get("/files/{pid}/{tail:.*}")
async def files(request):
    base = store.project_dir(request.match_info["pid"]).resolve()
    path = (base / request.match_info["tail"]).resolve()
    if base not in path.parents or not path.is_file():
        return bad("파일을 찾지 못했어요", 404)
    return web.FileResponse(path, headers={"Cache-Control": "no-cache"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--open", action="store_true", help="브라우저 열기")
    args = ap.parse_args()
    cfg = store.load_config()
    port = args.port or cfg.get("port", 7870)
    store.PROJECTS.mkdir(exist_ok=True)
    mark_interrupted()
    ALLOWED_HOSTS.update({f"127.0.0.1:{port}", f"localhost:{port}"})
    app = web.Application(client_max_size=512 * 1024 * 1024, middlewares=[same_origin, no_cache])
    app.add_routes(routes)
    app.router.add_static("/static", STATIC)
    url = f"http://127.0.0.1:{port}"
    print(f"38Sprite: {url}  (ComfyUI: {cfg['comfy_url']})", flush=True)
    if args.open:
        webbrowser.open(url)
    web.run_app(app, host="127.0.0.1", port=port, print=None)


if __name__ == "__main__":
    main()
