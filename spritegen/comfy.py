"""ComfyUI 연결: 상태 확인, 이미지 업로드, 워크플로 구성, 큐 넣기, 결과 받기.

영상 AI는 config.json의 video_backend로 고른다.
- "h3" (기본): MiniMax H3. 모델 파일 이름은 config.json의 models로 바꿀 수 있다.
- "custom": workflow_dir 폴더의 ComfyUI 워크플로(API 형식 JSON)에 값을 채워 쓴다. 다른 영상 모델로 교체할 때.
  자리표시자와 규칙은 docs/CUSTOM_WORKFLOW.md 참고.
"""
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

DEFAULT_MODELS = {                       # H3 모델 파일 이름 (config.json의 "models"로 바꿀 수 있다)
    "i2v": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
    "r2v": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
    "turbo_i2v": "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
    "turbo_r2v": "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors",
    "clip": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
    "video_vae": "minimax_h3_video_vae_int8_convrot.safetensors",
    "audio_vae": "minimax_h3_audio_vae_fp32.safetensors",
}
FPS = 24
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def settings():
    """(영상 AI 종류, 모델 이름들, 워크플로 폴더). 설정 파일을 매번 읽어서 앱을 다시 켜지 않아도 바뀐다."""
    from . import project
    cfg = project.load_config()
    models = dict(DEFAULT_MODELS, **(cfg.get("models") or {}))
    return cfg.get("video_backend", "h3"), models, project.ROOT / cfg.get("workflow_dir", "workflows")


def from_template(path, **values):
    """사용자 워크플로(API 형식 JSON)의 {{이름}} 자리표시자를 채운다. 값 전체가 자리표시자면 숫자 등 원래 형식으로 넣는다."""
    path = Path(path)
    if not path.exists():
        raise RuntimeError(f"영상 AI 워크플로 파일이 없어요: {path}")
    wf = json.loads(path.read_text(encoding="utf-8"))

    def fill(v):
        if isinstance(v, str):
            m = PLACEHOLDER.fullmatch(v)
            if m and m.group(1) in values:
                return values[m.group(1)]
            return PLACEHOLDER.sub(lambda mm: str(values.get(mm.group(1), mm.group(0))), v)
        if isinstance(v, list):
            return [fill(x) for x in v]
        if isinstance(v, dict):
            return {k: fill(x) for k, x in v.items()}
        return v
    return fill(wf)


def frames_for_seconds(seconds):
    """H3의 17k+5 프레임 격자에 맞춘다 (ComfyUI 공식 템플릿과 같은 계산)."""
    n = max(5, round(seconds * FPS))
    return n + (5 - n % 17) % 17


def http_json(url, payload=None, timeout=60):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return json.loads(body) if body.strip() else {}   # /queue 삭제, /interrupt는 빈 응답을 준다


CANDIDATES = ("http://127.0.0.1:8188", "http://127.0.0.1:8189", "http://127.0.0.1:8000")


def find_server(candidates=CANDIDATES):
    """켜져 있는 ComfyUI 찾기: H3 이미지→영상 모델 파일까지 있는 곳을 먼저, 없으면 처음 응답한 곳, 아무도 없으면 None.
    (ComfyUI 기본 포트는 8188이지만, 여러 개를 켜 두면 H3가 있는 쪽이 다른 포트일 수 있다. 최신 ComfyUI는 모델이
    없어도 H3 노드가 있어서 노드만 보면 엉뚱한 쪽을 고른다 — 2026-10-08 시험)"""
    _, M, _ = settings()
    first = None
    for url in candidates:
        try:
            http_json(f"{url}/system_stats", timeout=2)
        except (urllib.error.URLError, OSError, ValueError):
            continue
        first = first or url
        try:
            unets = http_json(f"{url}/object_info/UNETLoader", timeout=10)["UNETLoader"]["input"]["required"]["unet_name"][0]
            if M["i2v"] in unets:
                return url
        except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError, TypeError):
            pass
    return first


def check(server):
    """ComfyUI가 켜져 있고 고른 영상 AI를 쓸 수 있는지 확인한다."""
    backend, M, wdir = settings()
    info = {"url": server, "ok": False, "backend": backend, "i2v": False, "r2v": False, "turbo_i2v": False,
            "turbo_r2v": False}
    try:
        stats = http_json(f"{server}/system_stats", timeout=5)
        info["version"] = stats["system"].get("comfyui_version")
        dev = (stats.get("devices") or [{}])[0]
        info["gpu"] = dev.get("name")
    except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
        info["error"] = f"ComfyUI에 연결하지 못했어요 ({e})"
        return info
    if backend == "custom":
        info.update(i2v=(wdir / "i2v.json").exists(), r2v=(wdir / "r2v.json").exists())
        info["ok"] = info["i2v"]
        if not info["i2v"]:
            info["error"] = f"사용자 영상 AI 워크플로가 없어요: {wdir / 'i2v.json'}"
        return info
    try:
        nodes = http_json(f"{server}/object_info/MiniMaxH3ImageToVideo", timeout=10)
        unets = http_json(f"{server}/object_info/UNETLoader", timeout=10)["UNETLoader"]["input"]["required"]["unet_name"][0]
        loras = http_json(f"{server}/object_info/LoraLoaderModelOnly", timeout=10)[
            "LoraLoaderModelOnly"]["input"]["required"]["lora_name"][0]
    except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
        info["error"] = f"ComfyUI에 연결하지 못했어요 ({e})"
        return info
    if not nodes:
        info["error"] = "이 ComfyUI에는 MiniMax H3 노드가 없어요 (0.37 이상 필요)"
        return info
    info.update(i2v=M["i2v"] in unets, r2v=M["r2v"] in unets, turbo_i2v=M["turbo_i2v"] in loras,
                turbo_r2v=M["turbo_r2v"] in loras)
    info["ok"] = info["i2v"]
    if not info["i2v"]:
        info["error"] = f"H3 이미지→영상 모델({M['i2v']})이 이 ComfyUI의 models 폴더에 없어요"
    return info


def upload(server, path, name):
    """ComfyUI input 폴더에 올린다. 같은 이름은 덮어쓰므로 작업마다 다른 name을 줄 것."""
    path = Path(path)
    boundary = uuid.uuid4().hex
    ctype = "video/mp4" if path.suffix.lower() in (".mp4", ".mov", ".webm") else "image/png"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'.encode(),
        f"Content-Type: {ctype}\r\n\r\n".encode(), path.read_bytes(), b"\r\n",
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="overwrite"\r\n\r\ntrue\r\n',
        f"--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(f"{server}/upload/image", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        info = json.loads(r.read())
    return f"{info['subfolder']}/{info['name']}" if info.get("subfolder") else info["name"]


def _sampler_tail(wf, model, cond, latent, vae, steps, seed, prefix):
    wf["s_sampler"] = {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}}
    wf["s_sched"] = {"class_type": "BasicScheduler",
                     "inputs": {"model": model, "scheduler": "simple", "steps": steps, "denoise": 1.0}}
    wf["s_noise"] = {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}}
    wf["s_guider"] = {"class_type": "BasicGuider", "inputs": {"model": model, "conditioning": cond}}
    wf["s_run"] = {"class_type": "SamplerCustomAdvanced", "inputs": {
        "noise": ["s_noise", 0], "guider": ["s_guider", 0], "sampler": ["s_sampler", 0],
        "sigmas": ["s_sched", 0], "latent_image": latent}}
    wf["s_decode"] = {"class_type": "VAEDecode", "inputs": {"samples": ["s_run", 0], "vae": vae}}
    wf["s_save"] = {"class_type": "SaveImage", "inputs": {"images": ["s_decode", 0], "filename_prefix": prefix}}
    return wf


def _add_guides(wf, cond, latent, vae, guides):
    """guides: [(업로드된 이미지 이름, 프레임 번호), ...] — 그 프레임에 그 자세를 고정한다 (음수는 끝에서부터)."""
    for i, (image, frame_idx) in enumerate(guides or []):
        wf[f"g_img{i}"] = {"class_type": "LoadImage", "inputs": {"image": image}}
        wf[f"g_add{i}"] = {"class_type": "MiniMaxH3AddGuide", "inputs": {
            "positive": cond, "latent": latent, "frame_idx": int(frame_idx), "vae": vae, "image": [f"g_img{i}", 0]}}
        cond = [f"g_add{i}", 0]
    return cond


def turbo_steps():
    """터보 이미지→영상 단계 수 (설정 turbo_steps, 기본 6). 2026-10-08 시험: 걷기·달리기·쓰러짐 모두 8단계와 같은 품질에
    약 25% 빨랐고, 4단계는 배경에 잡티가 남았다. LoRA 이름은 8단계지만 6단계까지는 차이가 보이지 않았다."""
    from . import project
    return max(1, int(project.load_config().get("turbo_steps", 6)))


def i2v_workflow(first, last, prompt, width, height, length, seed, prefix, turbo=True, guides=None):
    """이미지→영상: 첫·끝 프레임 고정 (+ 중간 자세 고정). first가 None이면 텍스트→영상.
    사용자 워크플로에서는 중간 자세 고정(guides)은 쓰지 않는다."""
    backend, M, wdir = settings()
    steps = turbo_steps() if turbo else 20
    if backend == "custom":
        return from_template(wdir / "i2v.json", FIRST_IMAGE=first or "", LAST_IMAGE=last or first or "", PROMPT=prompt,
                             WIDTH=width, HEIGHT=height, LENGTH=length, SEED=seed, STEPS=steps,
                             PREFIX=prefix)
    wf = {
        "m_unet": {"class_type": "UNETLoader", "inputs": {"unet_name": M["i2v"], "weight_dtype": "default"}},
        "m_clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": M["clip"], "type": "minimax", "device": "default"}},
        "m_vae": {"class_type": "VAELoader", "inputs": {"vae_name": M["video_vae"]}},
        "i_cond": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {
            "clip": ["m_clip", 0], "vae": ["m_vae", 0], "prompt": prompt,
            "width": width, "height": height, "length": length}},
    }
    if first:
        wf["i_first"] = {"class_type": "LoadImage", "inputs": {"image": first}}
        wf["i_cond"]["inputs"]["first_frame"] = ["i_first", 0]
    if last:
        wf["i_last"] = {"class_type": "LoadImage", "inputs": {"image": last}}
        wf["i_cond"]["inputs"]["last_frame"] = ["i_last", 0]
    model = ["m_unet", 0]
    if turbo:
        wf["m_turbo"] = {"class_type": "LoraLoaderModelOnly",
                         "inputs": {"model": model, "lora_name": M["turbo_i2v"], "strength_model": 1.0}}
        model = ["m_turbo", 0]
    cond = _add_guides(wf, ["i_cond", 0], ["i_cond", 1], ["m_vae", 0], guides)
    return _sampler_tail(wf, model, cond, ["i_cond", 1], ["m_vae", 0], steps, seed, prefix)


def r2v_workflow(ref_image, ref_video, prompt, width, height, length, seed, prefix, turbo=False, guides=None):
    """레퍼런스 투 비디오: <Picture 1> = 캐릭터(그 방향), <Video 1> = 따라 할 동작 영상."""
    backend, M, wdir = settings()
    if backend == "custom":
        return from_template(wdir / "r2v.json", REF_IMAGE=ref_image, REF_VIDEO=ref_video, PROMPT=prompt, WIDTH=width,
                             HEIGHT=height, LENGTH=length, SEED=seed, STEPS=4 if turbo else 20, PREFIX=prefix)
    wf = {
        "m_unet": {"class_type": "UNETLoader", "inputs": {"unet_name": M["r2v"], "weight_dtype": "default"}},
        "m_clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": M["clip"], "type": "minimax", "device": "default"}},
        "m_vae": {"class_type": "VAELoader", "inputs": {"vae_name": M["video_vae"]}},
        "m_avae": {"class_type": "VAELoader", "inputs": {"vae_name": M["audio_vae"]}},
        "r_img": {"class_type": "LoadImage", "inputs": {"image": ref_image}},
        "r_video": {"class_type": "LoadVideo", "inputs": {"file": ref_video}},
        "r_parts": {"class_type": "GetVideoComponents", "inputs": {"video": ["r_video", 0]}},
        "r_cond": {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": {
            "clip": ["m_clip", 0], "vae": ["m_vae", 0], "audio_vae": ["m_avae", 0], "prompt": prompt,
            "width": width, "height": height, "length": length, "ref_image_size": "match",
            "ref_images.ref_image_0": ["r_img", 0], "ref_videos.ref_video_0": ["r_parts", 0]}},
    }
    model = ["m_unet", 0]
    if turbo:
        wf["m_turbo"] = {"class_type": "LoraLoaderModelOnly",
                         "inputs": {"model": model, "lora_name": M["turbo_r2v"], "strength_model": 1.0}}
        model = ["m_turbo", 0]
    cond = _add_guides(wf, ["r_cond", 0], ["r_cond", 1], ["m_vae", 0], guides)
    return _sampler_tail(wf, model, cond, ["r_cond", 1], ["m_vae", 0], 4 if turbo else 20, seed, prefix)


FRONT = False      # True면 대기열 맨 앞에 넣는다 (급한 작업용)


def queue(server, wf, client_id, front=None):
    body = {"prompt": wf, "client_id": client_id}
    if FRONT if front is None else front:
        body["front"] = True
    res = http_json(f"{server}/prompt", body)
    if res.get("node_errors"):
        raise RuntimeError(f"ComfyUI가 워크플로를 거절했어요: {json.dumps(res['node_errors'], ensure_ascii=False)[:1500]}")
    return res["prompt_id"]


def state(server, prompt_id):
    """'done' | 'error' | 'running' | 'queued' | 'unknown'과 history 항목을 돌려준다."""
    hist = http_json(f"{server}/history/{prompt_id}")
    if prompt_id in hist:
        entry = hist[prompt_id]
        if entry.get("status", {}).get("status_str") == "error":
            return "error", entry
        return "done", entry
    q = http_json(f"{server}/queue")
    if any(item[1] == prompt_id for item in q.get("queue_running", [])):
        return "running", None
    if any(item[1] == prompt_id for item in q.get("queue_pending", [])):
        return "queued", None
    return "unknown", None


def error_text(entry):
    for kind, data in entry.get("status", {}).get("messages", []):
        if kind == "execution_error":
            return f"{data.get('node_type')}: {data.get('exception_message', '').strip()}"
    return "알 수 없는 오류"


def wait(server, prompt_id, poll=5, on_tick=None, offline_limit=120):
    """작업이 끝날 때까지 기다린다. 잠깐 연결이 안 되면(포트 부족·ComfyUI가 바쁨) offline_limit초까지 다시 묻는다
    (2026-10-08 실험 12개를 기다리다 한 번의 연결 오류로 전체가 멈춘 적이 있다)."""
    t0 = time.time()
    missing_since = offline_since = None
    while True:
        try:
            st, entry = state(server, prompt_id)
            offline_since = None
        except (urllib.error.URLError, OSError, ValueError) as e:
            offline_since = offline_since or time.time()
            if time.time() - offline_since > offline_limit:
                raise RuntimeError(f"ComfyUI에 {offline_limit}초 넘게 연결하지 못했어요 ({e})") from e
            time.sleep(poll)
            continue
        if st == "done":
            return entry, time.time() - t0
        if st == "error":
            raise RuntimeError(error_text(entry))
        if st == "unknown":
            # 큐에서도 기록에서도 안 보이면 누가 지운 것 (잠깐 안 보이는 경우를 감안해 1분 기다림)
            missing_since = missing_since or time.time()
            if time.time() - missing_since > 60:
                raise RuntimeError("ComfyUI 큐에서 작업이 사라졌어요 (취소됐거나 ComfyUI가 다시 켜졌어요)")
        else:
            missing_since = None
        if on_tick:
            on_tick(st, time.time() - t0)
        time.sleep(poll)


def download(server, entry, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for node_out in entry["outputs"].values():
        for img in node_out.get("images", []):
            qs = urllib.parse.urlencode({"filename": img["filename"], "subfolder": img["subfolder"], "type": img["type"]})
            dst = out_dir / img["filename"]
            with urllib.request.urlopen(f"{server}/view?{qs}", timeout=120) as r:
                dst.write_bytes(r.read())
            saved.append(dst)
    return sorted(saved)


def cancel(server, prompt_id):
    """대기 중이면 큐에서 빼고, 실행 중이면 중단한다."""
    try:
        http_json(f"{server}/queue", {"delete": [prompt_id]})
        st, _ = state(server, prompt_id)
        if st == "running":
            http_json(f"{server}/interrupt", {})
    except (urllib.error.URLError, OSError):
        pass
