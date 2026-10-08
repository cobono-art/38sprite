"""AI 배경 지우기 (BEN v2, MIT, PramaLLC): 크로마키가 틀리는 곳만 고친다.

크로마키(마젠타)는 머리카락·반투명 가장자리·빛 효과에 강하지만 이런 것을 틀린다.
- 구멍: 배경과 비슷한 색(분홍·보라, 회색 배경 앞의 은색 칼날)을 배경으로 보고 뚫는다.
- 남는 것: 바닥 그림자·배경 얼룩·색 테두리를 캐릭터로 남긴다 (영상 AI가 배경색을 바꾼 프레임에서 특히).
- 빛 효과 장면에서 영상 AI가 배경을 빨강·주황·파랑 단색으로 바꾸면 효과 둘레의 번진 빛이 색 덩어리로 남는다.
AI 마스크는 반대로 빛 효과·가는 선에 약하다. 그래서 알파는 크로마키 것을 쓰고, 둘이 크게 다른 덩어리만 AI를 따른다.
(2026-10-08 홍보영상 스프라이트 23개로 맞춘 규칙)

모델 파일(BEN2.py, model.safetensors)은 config.json의 matting_dir, 없으면 models/ben2 에 둔다 (setup_matting.bat).
앱을 ComfyUI에 딸린 파이썬으로 돌리면 torch가 이미 있어서 따로 설치할 것이 없다.
"""
import importlib.util
import sys
import threading
import types
from pathlib import Path

import cv2
import numpy as np

MODEL_URL = "https://huggingface.co/PramaLLC/BEN2/resolve/main/"
FILES = ("BEN2.py", "model.safetensors")
SIZE = 1024                                   # BEN v2 입력 크기
_lock = threading.Lock()
_model = None


def model_dir():
    """모델 폴더 (파일이 다 있을 때만)."""
    from . import project
    cfg = project.load_config()
    d = Path(cfg.get("matting_dir") or project.ROOT / "models" / "ben2")
    return d if all((d / f).exists() for f in FILES) else None


def available():
    if model_dir() is None:
        return False
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def _timm_shim():
    """BEN2.py가 timm에서 쓰는 작은 함수 셋만 채워 넣는다 (timm이 없는 ComfyUI 파이썬에서도 돌게)."""
    import torch
    from torch import nn

    class DropPath(nn.Module):
        def __init__(self, p=0.0):
            super().__init__()
            self.p = p

        def forward(self, x):
            if self.p == 0.0 or not self.training:
                return x
            keep = 1 - self.p
            mask = x.new_empty((x.shape[0],) + (1,) * (x.ndim - 1)).bernoulli_(keep)
            return x * mask / keep

    layers = types.ModuleType("timm.models.layers")
    layers.DropPath = DropPath
    layers.to_2tuple = lambda x: tuple(x) if isinstance(x, (list, tuple)) else (x, x)
    layers.trunc_normal_ = lambda t, mean=0.0, std=1.0, a=-2.0, b=2.0: nn.init.trunc_normal_(t, mean, std, a, b)
    models = types.ModuleType("timm.models")
    models.layers = layers
    timm = types.ModuleType("timm")
    timm.models = models
    sys.modules.update({"timm": timm, "timm.models": models, "timm.models.layers": layers})
    return torch


def _load(d=None):
    global _model
    if _model is not None:
        return _model
    d = Path(d) if d else model_dir()
    if d is None:
        raise RuntimeError("AI 배경 지우기 모델이 없어요 (setup_matting.bat)")
    import torch
    try:
        import timm.models.layers  # noqa: F401
    except ImportError:
        _timm_shim()
    spec = importlib.util.spec_from_file_location("ben2_model", d / "BEN2.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from safetensors.torch import load_file
    net = mod.BEN_Base()
    net.load_state_dict(load_file(str(d / "model.safetensors")), strict=True)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    net = net.to(dev).eval()
    if dev.type == "cuda":
        net = net.half()
    _model = (net, dev)
    return _model


def release():
    """GPU 메모리를 돌려준다 (영상 AI가 같은 그래픽카드를 쓴다)."""
    global _model
    with _lock:
        if _model is None:
            return
        _model = None
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass


def masks(frames, batch=4, d=None):
    """RGB 프레임들 → AI 알파(0~1, float32) 목록. GPU 메모리가 모자라면 한 장씩, 그래도 안 되면 CPU로."""
    import torch
    from PIL import Image
    with _lock:
        net, dev = _load(d)
        mean = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
        std = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
        out = []
        i = 0
        while i < len(frames):
            chunk = frames[i:i + batch]
            x = np.stack([np.asarray(Image.fromarray(f).resize((SIZE, SIZE), Image.LANCZOS)) for f in chunk])
            x = (torch.from_numpy(x).permute(0, 3, 1, 2).float() / 255 - mean) / std
            try:
                with torch.no_grad():
                    y = net(x.to(dev, torch.float16 if dev.type == "cuda" else torch.float32)).float()
            except torch.cuda.OutOfMemoryError:
                torch.cuda.empty_cache()
                if batch > 1:
                    batch = 1
                    continue
                global _model
                net, dev = net.float().cpu(), torch.device("cpu")
                _model = (net, dev)
                continue
            for k, f in enumerate(chunk):
                h, w = f.shape[:2]
                m = torch.nn.functional.interpolate(y[k:k + 1], size=(h, w), mode="bilinear", align_corners=False)
                out.append(m[0, 0].clamp(0, 1).cpu().numpy().astype(np.float32))
            i += len(chunk)
        return out


def enabled():
    """설정 matting: auto(기본, 모델이 있으면 씀) | off."""
    from . import project
    return project.load_config().get("matting", "auto") != "off" and available()


def cached_masks(paths, cache_dir):
    """프레임 파일들의 AI 알파. cache_dir에 PNG로 남겨 두고, 프레임보다 새 것이면 다시 쓴다
    ('다른 장면으로 바꾸기'·다시 조립할 때 새로 고른 프레임만 계산)."""
    from PIL import Image
    cache_dir = Path(cache_dir)
    out, todo = [None] * len(paths), []
    for k, p in enumerate(paths):
        c = cache_dir / Path(p).name
        if c.exists() and c.stat().st_mtime >= Path(p).stat().st_mtime:
            out[k] = np.asarray(Image.open(c), np.float32) / 255
        else:
            todo.append(k)
    if todo:
        cache_dir.mkdir(parents=True, exist_ok=True)
        ms = masks([np.asarray(Image.open(paths[k]).convert("RGB")) for k in todo])
        for k, m in zip(todo, ms):
            Image.fromarray((m * 255 + 0.5).astype(np.uint8)).save(cache_dir / Path(paths[k]).name)
            out[k] = m
    return out


K3 = np.ones((3, 3), np.uint8)


def _shadow_like(frame, region, bg):
    """바닥 그림자·배경 얼룩처럼 보이는지: 색이 거의 없고(회색빛) 배경보다 밝지 않다."""
    c = frame[region].astype(np.float32).mean(axis=0)
    sat = (c.max() - c.min()) / max(c.max(), 1.0)
    bgv = np.asarray(bg, np.float32)
    luma = lambda v: 0.299 * v[0] + 0.587 * v[1] + 0.114 * v[2]  # noqa: E731
    return sat < 0.25 and luma(c) <= luma(bgv) + 12


def _blobs(mask, min_area):
    """두께가 있는 덩어리만 (1~2픽셀 폭의 가장자리 차이는 크로마키 그대로 둔다) → (영역, 넓이)."""
    core = cv2.morphologyEx(mask, cv2.MORPH_OPEN, K3)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(core, connectivity=8)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            yield lab == i, int(stats[i, cv2.CC_STAT_AREA])


def combine(frame, ka, ai, bg, remove="all", fill_conf=0.8, min_area=24):
    """크로마키 알파 ka와 AI 알파 ai를 합친다 → (알파, {"filled": 채운 픽셀, "removed": 지운 픽셀}).
    - 구멍(크로마키는 배경, AI는 캐릭터)인 덩어리는 AI 알파로 채운다. 몸에 붙어 있고, AI가 평균 fill_conf 이상
      확신하고, 배경색 그대로가 아닌 곳만 (빛 궤적 안쪽은 AI가 0.7~0.9로 애매하게 보는데 채우면 어두운 얼룩이 된다).
      AI가 확실히 몸 안쪽이라고 보는 곳(fill_conf 넘게)이 반투명이면 불투명하게 (초록 배경 앞 초록 드래곤처럼
      배경과 색이 비슷한 캐릭터가 반쯤 비치는 것).
    - 남는 것(크로마키는 캐릭터, AI는 배경)인 덩어리는 remove가 all이면 다 지우고, shadow면 그림자처럼 보이는
      것만, none이면 그대로 둔다 (AI는 빛 효과를 배경으로 본다). all이면 몸에서 떨어진 작은 얼룩도 지운다.
    몸에 붙은 가장자리 몇 픽셀 차이는 크로마키를 그대로 둔다 (외곽선이 깎이지 않게)."""
    f = frame.astype(np.float32)
    out = ka.astype(np.float32).copy()
    dist = np.linalg.norm(f - np.asarray(bg, np.float32), axis=2)
    solid = ka > 0.5
    info = {"filled": 0, "removed": 0}
    miss = ((ai > 0.6) & (ka < 0.4)).astype(np.uint8)
    for reg, area in _blobs(miss, min_area):
        if float(dist[reg].mean()) < 20 or float(ai[reg].mean()) < fill_conf:
            continue
        near = cv2.dilate(reg.astype(np.uint8), K3, iterations=3) > 0
        if not (near & solid).any():                   # 몸에서 떨어진 조각은 채우지 않는다
            continue
        grow = cv2.dilate(reg.astype(np.uint8), K3, iterations=2) > 0
        out[grow] = np.maximum(out[grow], ai[grow])
        info["filled"] += area
    inner = (ai > max(fill_conf, 0.9)) & (dist >= 20) & (out < ai)
    out[inner] = ai[inner]
    if remove == "none":
        return out, info
    extra = ((ka > 0.6) & (ai < 0.15)).astype(np.uint8)
    for reg, area in _blobs(extra, min_area):
        if remove == "shadow" and not _shadow_like(frame, reg, bg):
            continue
        grow = cv2.dilate(reg.astype(np.uint8), K3, iterations=2) > 0
        out[grow] = np.minimum(out[grow], ai[grow])
        info["removed"] += area
    if remove == "all":                                # 몸(AI)에서 떨어진 얼룩: 가늘어도 지운다
        body = cv2.dilate((ai > 0.5).astype(np.uint8), K3, iterations=3) > 0
        n, lab, stats, _ = cv2.connectedComponentsWithStats((out > 0.3).astype(np.uint8), connectivity=8)
        for i in range(1, n):
            reg = lab == i
            if not (reg & body).any():
                out[reg] = 0
                info["removed"] += int(stats[i, cv2.CC_STAT_AREA])
    return out, info


def light_alpha(frame, bg, lo=50.0, hi=150.0, lo2=45.0, hi2=100.0):
    """빛 효과의 알파 (배경색이 마젠타·초록이 아닐 때): 넓고 부드럽게, 둘 중 큰 것.
    - 배경보다 밝아진 만큼 (가장 많이 밝아진 색 채널 기준): 빛은 더해지는 것이라 반짝이·광선·고리가 산다.
    - 배경과 색이 확실히 다른 만큼 (lo2 넘게): 분홍 배경 위 보라 고리, 연회색 배경 위 청록 고리처럼 밝기는 비슷해도
      색이 다른 효과. 배경보다 어두울수록 약하게 본다 (효과 둘레의 칙칙한 번짐).
    효과 둘레의 옅은 번짐(배경과 조금 다른 색)과, 배경과 같은 색인데 더 어두운 곳(바닥 그림자)은 남기지 않는다."""
    f = frame.astype(np.float32)
    b = np.asarray(bg, np.float32)
    w = np.array([0.299, 0.587, 0.114], np.float32)
    up = np.clip(((f - b).max(axis=2) - lo) / (hi - lo), 0, 1)
    diff = np.clip((np.linalg.norm(f - b, axis=2) - lo2) / (hi2 - lo2), 0, 1)
    darker = float(b @ w) - f @ w                     # 배경보다 얼마나 어두운지
    diff *= np.clip(1 - (darker - 10) / 40, 0, 1)
    cos = (f * b).sum(axis=2) / (np.linalg.norm(f, axis=2) * np.linalg.norm(b) + 1e-6)
    diff[(cos > 0.97) & (darker > 6)] = 0             # 배경색 그대로 어두워진 곳 = 그림자
    return cv2.GaussianBlur(np.maximum(up, diff), (0, 0), 0.8)


def matte(frame, ka, ai, bg, effects="none"):
    """최종 알파 → (알파, 정보).
    - none·strip: 캐릭터만. 크로마키에 AI로 구멍을 채우고 남은 그림자·얼룩·빛 조각을 지운다.
    - vivid (빛 효과를 살림): 확실한 구멍만 채우고 빛은 남긴다.
      · 마젠타·초록 배경: 크로마키가 빛을 잘 따니 그대로.
      · 그 밖의 배경(마네킹 모드의 회색, 영상 AI가 효과 장면에서 바꿔 버린 빨강·주황·연회색 단색): 크로마키는 효과
        둘레의 번진 빛까지 색 덩어리로 남긴다. 몸은 AI로, 빛은 light_alpha로 다시 딴다."""
    from .imaging import is_key_bg
    if effects != "vivid":
        return combine(frame, ka, ai, bg, "all")
    if is_key_bg(bg):
        return combine(frame, ka, ai, bg, "none", fill_conf=0.95)
    body, info = combine(frame, ka, ai, bg, "all", fill_conf=0.95)
    return np.maximum(body, light_alpha(frame, bg)), info


def finish(frame, a, bg, band=3):
    """알파로 오린 RGBA. 영상 AI가 배경을 초록으로 바꾼 프레임은 초록 빼기를 가장자리 band 픽셀 안에서만 한다
    (몸 안쪽까지 빼면 초록 드래곤이 회색이 된다). 마젠타 배경은 지금처럼 전체에서 분홍 기운을 뺀다: 은색 갑옷에
    비친 마젠타가 몸 안쪽에도 있고, 캐릭터 그림은 처음부터 분홍·보라를 피해서 그린다."""
    from .imaging import cutout_any, is_green_bg
    out = cutout_any(frame, a, bg)
    if is_green_bg(bg):
        solid = (a >= 0.5).astype(np.uint8)
        deep = (cv2.distanceTransform(solid, cv2.DIST_L2, 3) > band) & (a >= 0.99)
        out[deep, :3] = frame[deep]
    return out
