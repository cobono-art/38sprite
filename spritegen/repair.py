"""그래도 남은 빛 효과를 그 장만 편집 AI로 다시 그리기 (선택 기능).

이미지 편집 모델(Qwen-Image 2.1 edit)이 있는 ComfyUI에 그 영상 프레임을 넣고 "효과만 지우고 나머지는 그대로"라고
시킨 뒤, 편집 AI가 크게 바꾼 곳만 원래 프레임에 끼워 넣는다 (2026-10-08 시험: 한 장 6~12초, 자세는 그대로, 큰 궤적이
깨끗이 사라짐. 첫 장면을 참고 그림으로 같이 주면 정면에서 자세까지 첫 장면으로 되돌려서 그 장만 넣는다).
고친 그림은 <동작>/repaired/<방향>/<프레임 번호>.png 에 두고, 시트를 조립할 때 그 프레임 대신 쓴다 (지우면 원래대로).
편집 모델과 영상 AI가 그래픽카드 하나를 같이 쓰므로, 고치기 전에 영상 AI 쪽 모델을 내리고(대기열이 비어 있을 때만)
고친 뒤 편집 모델도 내린다."""
import json
import urllib.request
import uuid
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from . import comfy

MODELS = {"unet": "qwen_image_2.1_int8_convrot.safetensors", "clip": "qwen3vl_8b_w4a8.safetensors",
          "vae": "qwen_image_2.1_vae_bf16.safetensors"}
NODE = "TextEncodeQwenImage21"
PROMPT = ("Remove all visual effects from this game sprite frame: every glowing light trail, crescent slash arc, streak, "
          "sparkle, star burst and glow. Keep the character exactly as it is: the same pose, face, hair, clothes and held "
          "item, at the same position and size, with the same colors, outlines and art style. The background stays one "
          "flat solid magenta (#FF00FF).")
CANDIDATES = ("http://127.0.0.1:8188", "http://127.0.0.1:8189", "http://127.0.0.1:8000")


def models(cfg):
    return dict(MODELS, **(cfg.get("edit_models") or {}))


def check(url, cfg=None):
    """그 ComfyUI에 편집 노드와 모델 파일이 있는지."""
    try:
        if not comfy.http_json(f"{url}/object_info/{NODE}", timeout=5):
            return False
        unets = comfy.http_json(f"{url}/object_info/UNETLoader", timeout=10)["UNETLoader"]["input"]["required"]["unet_name"][0]
    except Exception:  # noqa: BLE001 — 꺼져 있거나 다른 ComfyUI
        return False
    return models(cfg or {})["unet"] in unets


def find(cfg):
    """편집 AI ComfyUI 주소 (설정 edit_url, 없으면 흔한 포트에서 찾는다) 또는 None."""
    if cfg.get("edit_url"):
        return cfg["edit_url"] if check(cfg["edit_url"], cfg) else None
    return next((u for u in CANDIDATES if check(u, cfg)), None)


def workflow(image, prompt, seed, prefix, cfg):
    M = models(cfg)
    return {
        "e_unet": {"class_type": "UNETLoader", "inputs": {"unet_name": M["unet"], "weight_dtype": "default"}},
        "e_clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": M["clip"], "type": "qwen_image", "device": "default"}},
        "e_vae": {"class_type": "VAELoader", "inputs": {"vae_name": M["vae"]}},
        "e_cache": {"class_type": "QwenImage21Cache", "inputs": {"model": ["e_unet", 0], "device": "auto", "dtype": "default"}},
        "e_img": {"class_type": "LoadImage", "inputs": {"image": image}},
        "e_text": {"class_type": NODE, "inputs": {"clip": ["e_clip", 0], "prompt": prompt, "negative_prompt": "",
                                                   "resolution": 640, "images.image_1": ["e_img", 0], "vae": ["e_vae", 0]}},
        "e_sample": {"class_type": "KSampler", "inputs": {"model": ["e_cache", 0], "positive": ["e_text", 0],
                                                         "negative": ["e_text", 1], "latent_image": ["e_text", 2],
                                                         "seed": seed, "steps": 25, "cfg": 1.0, "sampler_name": "euler",
                                                         "scheduler": "simple", "denoise": 1.0}},
        "e_decode": {"class_type": "VAEDecode", "inputs": {"samples": ["e_sample", 0], "vae": ["e_vae", 0]}},
        "e_save": {"class_type": "SaveImage", "inputs": {"images": ["e_decode", 0], "filename_prefix": prefix}},
    }


def splice(orig, edit, thr=14.0):
    """편집 AI가 크게 바꾼 곳(색 차이 thr 넘음)만 편집 결과로, 나머지는 원래 픽셀 그대로 (몸이 미세하게 달라지지 않게)."""
    lab = lambda im: cv2.cvtColor(im, cv2.COLOR_RGB2LAB).astype(np.float32)   # noqa: E731
    m = (np.linalg.norm(lab(orig) - lab(edit), axis=2) > thr).astype(np.uint8)
    m = cv2.dilate(cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)), np.ones((5, 5), np.uint8))
    soft = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 1.5)[..., None]
    return (orig * (1 - soft) + edit * soft).astype(np.uint8)


def _post(url, path, body):
    req = urllib.request.Request(url + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()


def _idle(url):
    q = comfy.http_json(f"{url}/queue", timeout=10)
    return not q.get("queue_running") and not q.get("queue_pending")


def repair_frame(src, dst, edit_url, video_url, cfg, seed=11):
    """src 프레임에서 빛 효과를 지운 그림을 dst에 쓴다."""
    if video_url and video_url != edit_url:
        try:
            if not _idle(video_url):
                raise RuntimeError("영상 AI가 만드는 중이라 지금은 고칠 수 없어요 (그래픽카드를 같이 써요). 끝난 뒤에 해 주세요")
            _post(video_url, "/free", {"unload_models": True, "free_memory": True})
        except RuntimeError:
            raise
        except Exception:  # noqa: BLE001 — 영상 AI가 꺼져 있으면 그냥 진행
            pass
    orig = np.asarray(Image.open(src).convert("RGB"))
    name = comfy.upload(edit_url, src, f"repair_{uuid.uuid4().hex[:8]}.png")
    entry, _ = comfy.wait(edit_url, comfy.queue(edit_url, workflow(name, PROMPT, seed, "38sprite_repair/frame", cfg),
                                                uuid.uuid4().hex))
    tmp = Path(dst).parent / "_edit"
    files = comfy.download(edit_url, entry, tmp)
    edit = np.asarray(Image.open(files[0]).convert("RGB").resize((orig.shape[1], orig.shape[0]), Image.LANCZOS))
    for f in files:
        f.unlink(missing_ok=True)
    try:
        tmp.rmdir()
    except OSError:
        pass
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(splice(orig, edit)).save(dst)
    try:
        _post(edit_url, "/free", {"unload_models": True, "free_memory": True})
    except Exception:  # noqa: BLE001
        pass
    return dst
