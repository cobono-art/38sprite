"""run_app.bat이 부르는 패키지 확인: 이 파이썬에 없는 패키지를 pip 이름으로 한 줄에 (다 있으면 빈 줄).
ComfyUI 기본 설치에는 OpenCV(cv2)가 없다 (다른 추가 노드가 깔아 둔 경우에만 있음)."""
import importlib.util

NEED = (("aiohttp", "aiohttp"), ("numpy", "numpy"), ("cv2", "opencv-python-headless"), ("PIL", "pillow"))
print(" ".join(pkg for mod, pkg in NEED if importlib.util.find_spec(mod) is None))
