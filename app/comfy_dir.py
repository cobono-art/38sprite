"""setup_negative.bat이 부르는 도우미: 영상 AI ComfyUI 폴더(main.py가 있는 곳)를 한 줄로 (모르면 빈 줄).
앱이 켜져 있는 영상 AI ComfyUI를 보고 기억해 둔 파이썬(config.json의 comfy_python)을 먼저 쓴다 — ComfyUI가 여러 개인
PC에서 python_path.txt의 파이썬이 다른 ComfyUI 것일 수 있다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spritegen import comfy_launch, project  # noqa: E402

print(comfy_launch.video_root(project.load_config()) or "")
