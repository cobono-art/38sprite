"""프로젝트 저장소: projects/<id>/project.json + 입력·결과 파일."""
import json
import re
import threading
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "projects"
CONFIG = ROOT / "config.json"
_lock = threading.RLock()

DEFAULT_SETTINGS = {"angle": 45, "count": 8, "mirror": True, "style": "hd", "pixel_height": 64}
DEFAULT_CONFIG = {"comfy_url": "http://127.0.0.1:8189", "port": 7870}


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    return cfg


def save_config(cfg):
    CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def project_dir(pid):
    if not re.fullmatch(r"[a-z0-9-]+", pid):
        raise ValueError("잘못된 프로젝트 id")
    return PROJECTS / pid


def load(pid):
    with _lock:
        return json.loads((project_dir(pid) / "project.json").read_text(encoding="utf-8"))


def save(project):
    with _lock:
        path = project_dir(project["id"]) / "project.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(project, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)


def update(pid, fn):
    """project.json을 읽고 fn(project)로 고친 뒤 저장한다 (동시 수정 방지)."""
    with _lock:
        p = load(pid)
        fn(p)
        save(p)
        return p


def create(name, turnaround_bytes, suffix=".png"):
    pid = time.strftime("p%Y%m%d-") + uuid.uuid4().hex[:6]
    d = project_dir(pid)
    d.mkdir(parents=True)
    (d / f"turnaround{suffix}").write_bytes(turnaround_bytes)
    project = {"id": pid, "name": name or "새 캐릭터", "created": now(), "turnaround": f"turnaround{suffix}",
               "settings": dict(DEFAULT_SETTINGS), "sheet": None, "sheets": [], "motions": []}
    save(project)
    return project


def list_all():
    out = []
    if PROJECTS.exists():
        for f in sorted(PROJECTS.glob("*/project.json"), reverse=True):
            try:
                p = json.loads(f.read_text(encoding="utf-8"))
                out.append({"id": p["id"], "name": p["name"], "created": p["created"],
                            "turnaround": p["turnaround"], "motions": len(p.get("motions", []))})
            except (OSError, ValueError, KeyError):
                continue
    return out


def find_motion(project, mid):
    for m in project["motions"]:
        if m["id"] == mid:
            return m
    raise KeyError(mid)
