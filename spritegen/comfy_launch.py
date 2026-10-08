"""영상 AI ComfyUI를 켜고 다시 켜기 (ComfyUI가 이 PC에 있을 때만).

- 38Sprite를 켰을 때 ComfyUI가 꺼져 있으면 켠다 (설정 comfy_autostart, 기본 켬). 실행 옵션은 앱이 마지막으로 본 ComfyUI의
  옵션(설정 comfy_args — 켜져 있는 ComfyUI를 볼 때 기억해 둔다)을 쓰고, 없으면 --port만 붙인다.
- '빼는 낱말' 노드(custom_nodes/sprite_neg_h3)가 깔려 있어도 ComfyUI를 --disable-all-custom-nodes로 켜면 노드가 안 실린다.
  그래서 켤 때마다 --whitelist-custom-nodes sprite_neg_h3를 붙이고, 이미 노드 없이 켜져 있으면 화면의 버튼으로
  같은 옵션에 그것만 더해 다시 켤 수 있다 (돌고 있는 작업이 끊길 수 있어 묻지 않고 끄지는 않는다).
- 실행 중인 ComfyUI의 명령줄은 윈도에서만 읽는다 (PowerShell)."""
import json
import os
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

NODE_DIR = "sprite_neg_h3"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0            # PowerShell 창을 띄우지 않는다
NEW_CONSOLE = 0x00000010 if os.name == "nt" else 0          # ComfyUI는 자기 창에서 앱과 따로 돈다


def local_port(url):
    """이 PC의 ComfyUI 주소면 포트, 아니면 None."""
    u = urllib.parse.urlparse(url or "")
    return u.port if u.hostname in ("127.0.0.1", "localhost") and u.port else None


def comfy_root(python=None):
    """ComfyUI 폴더(main.py가 있는 곳). 앱은 ComfyUI의 파이썬으로 돈다: 포터블이면 python_embeded 옆의 ComfyUI,
    가상환경이면 ComfyUI/venv/Scripts/python.exe 위의 ComfyUI."""
    py = Path(python or sys.executable).resolve()
    for cand in (py.parent.parent / "ComfyUI", py.parent.parent.parent, py.parent.parent):
        if (cand / "main.py").exists():
            return cand
    return None


def node_installed(root):
    return bool(root) and (Path(root) / "custom_nodes" / NODE_DIR / "__init__.py").exists()


def with_node(args):
    """추가 노드를 모두 끄고 켜는 옵션이면 이 노드만 허용하는 옵션을 붙인다 (이미 있으면 그대로)."""
    args = list(args)
    if "--disable-all-custom-nodes" not in args:
        return args
    if "--whitelist-custom-nodes" not in args:
        return args + ["--whitelist-custom-nodes", NODE_DIR]
    i = j = args.index("--whitelist-custom-nodes") + 1
    while j < len(args) and not args[j].startswith("--"):
        j += 1
    if NODE_DIR not in args[i:j]:
        args.insert(j, NODE_DIR)
    return args


def default_args(port):
    return ["--listen", "127.0.0.1", "--port", str(port), "--disable-auto-launch"]


def split_cmdline(cmd):
    """윈도 명령줄 → 인자 목록 (윈도가 쓰는 규칙 그대로)."""
    if os.name != "nt":
        import shlex
        return shlex.split(cmd)
    import ctypes
    from ctypes import wintypes
    fn = ctypes.windll.shell32.CommandLineToArgvW
    fn.restype = ctypes.POINTER(wintypes.LPWSTR)
    n = ctypes.c_int()
    ptr = fn(cmd, ctypes.byref(n))
    try:
        return [ptr[i] for i in range(n.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(ptr)


def script_args(argv):
    """[python, (-s/-u ...), main.py, 옵션...] → main.py 뒤의 옵션만."""
    for i, a in enumerate(argv):
        if a.replace("\\", "/").split("/")[-1] == "main.py":
            return argv[i + 1:]
    return None


def running(port):
    """그 포트를 듣고 있는 ComfyUI → {"pid", "exe", "args"} 또는 None (윈도에서만)."""
    if os.name != "nt" or not port:
        return None
    ps = (f"$c = Get-NetTCPConnection -LocalPort {int(port)} -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; "
          "if ($c) { $p = Get-CimInstance Win32_Process -Filter \"ProcessId = $($c.OwningProcess)\"; "
          "@{pid=$p.ProcessId; exe=$p.ExecutablePath; cmd=$p.CommandLine} | ConvertTo-Json -Compress }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=30, creationflags=NO_WINDOW).stdout.strip()
        info = json.loads(out) if out else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if not info or not info.get("cmd"):
        return None
    args = script_args(split_cmdline(info["cmd"]))
    return {"pid": int(info["pid"]), "exe": info.get("exe"), "args": args} if args is not None else None


def start(root, python, args):
    """ComfyUI를 자기 창에서 켠다 (앱을 꺼도 계속 돈다)."""
    return subprocess.Popen([str(python), "-s", "main.py", *args], cwd=str(root), creationflags=NEW_CONSOLE)


def port_open(port, timeout=1.0):
    """그 포트에 무언가 켜져 있는지 (ComfyUI가 켜져 있는지 빠르게 본다)."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def autostart(cfg, url):
    """ComfyUI가 꺼져 있고 이 PC에 있으면 켠다 → 켰으면 True. 노드가 깔려 있으면 노드를 허용하는 옵션을 붙인다."""
    port = local_port(url)
    root = comfy_root()
    if not port or not root or not cfg.get("comfy_autostart", True):
        return False
    args = cfg.get("comfy_args") or default_args(port)
    if node_installed(root):
        args = with_node(args)
    start(root, sys.executable, args)
    return True


def restart_with_node(url, wait=30):
    """노드 없이 켜져 있는 ComfyUI를 같은 옵션 + 노드 허용으로 다시 켠다 → 새 옵션. 실패하면 RuntimeError."""
    port = local_port(url)
    root = comfy_root()
    if not port or not root:
        raise RuntimeError("이 PC의 ComfyUI가 아니라서 다시 켤 수 없어요")
    proc = running(port)
    if not proc:
        raise RuntimeError("켜져 있는 ComfyUI를 찾지 못했어요")
    args = with_node(proc["args"])
    subprocess.run(["taskkill", "/PID", str(proc["pid"]), "/F"], capture_output=True, timeout=30, creationflags=NO_WINDOW)
    for _ in range(wait * 2):                                # 포트가 비면 켠다
        if not port_open(port):
            break
        time.sleep(0.5)
    start(root, proc.get("exe") or sys.executable, args)
    return args
