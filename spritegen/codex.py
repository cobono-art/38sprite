"""Codex CLI로 이미지 만들기 ($imagegen). 사용자의 ChatGPT 로그인을 그대로 쓴다.

Codex 샌드박스는 프로젝트 폴더에 쓰지 못해서, 생성된 이미지는 ~/.codex/generated_images/<세션 id>/ 에 남는다.
실행 로그의 세션 id로 그 폴더를 찾아 결과를 복사해 온다.
"""
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
GEN_DIR = CODEX_HOME / "generated_images"
SESSION = re.compile(r"session id:\s*([0-9a-f-]{20,})")


def find_cli():
    for name in ("codex.cmd", "codex.exe", "codex"):
        path = shutil.which(name)
        if path:
            return path
    return None


def check():
    cli = find_cli()
    info = {"cli": cli, "logged_in": (CODEX_HOME / "auth.json").exists(), "ok": False}
    if not cli:
        info["error"] = "Codex CLI를 찾지 못했어요. 터미널에서 npm i -g @openai/codex 로 설치해 주세요"
        return info
    try:
        out = subprocess.run([cli, "--version"], capture_output=True, text=True, timeout=30)
        info["version"] = out.stdout.strip() or out.stderr.strip()
    except (OSError, subprocess.SubprocessError) as e:
        info["error"] = f"Codex CLI를 실행하지 못했어요 ({e})"
        return info
    if not info["logged_in"]:
        info["error"] = "Codex에 로그인되어 있지 않아요. 터미널에서 codex login 을 한 번 실행해 주세요"
        return info
    info["ok"] = True
    return info


def generate_image(prompt, refs, out_path, workdir, log_path=None, timeout=900):
    """프롬프트(와 참조 이미지)로 이미지를 한 장 만들어 out_path에 저장한다."""
    cli = find_cli()
    if not cli:
        raise RuntimeError("Codex CLI를 찾지 못했어요")
    # 사용자 설정 파일에 이 버전이 모르는 값이 있어도 돌아가게 설정 파일은 건너뛴다 (로그인은 그대로 씀)
    cmd = [cli, "exec", "--ignore-user-config", "--skip-git-repo-check", "-s", "read-only", "-C", str(workdir)]
    if refs:
        cmd += ["-i", *[str(r) for r in refs]]
    cmd.append("-")
    started = time.time()
    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, cwd=str(workdir))
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if log_path:
        Path(log_path).write_text(re.sub(r"data:image/[a-z]+;base64,[A-Za-z0-9+/=]+", "<image>", text), encoding="utf-8")

    found = []
    sessions = SESSION.findall(text)
    if sessions:
        found = sorted((GEN_DIR / sessions[-1]).glob("*.png"), key=lambda p: p.stat().st_mtime)
    if not found:
        found = sorted((p for p in GEN_DIR.glob("*/*.png") if p.stat().st_mtime >= started - 1),
                       key=lambda p: p.stat().st_mtime)
    if not found:
        tail = " ".join(text.strip().splitlines()[-3:])[:400]
        raise RuntimeError(f"Codex가 이미지를 만들지 못했어요. {tail}")
    shutil.copy(found[-1], out_path)
    return Path(out_path)
