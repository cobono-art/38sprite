"""레퍼런스 영상에서 프레임마다 사람 관절 33개의 3D 위치를 뽑는다 (MediaPipe Pose Landmarker).

ComfyUI 파이썬과 패키지가 섞이지 않게 앱 전용 가상환경(.venv-pose)에서 따로 실행한다:
  .venv-pose\\Scripts\\python.exe spritegen/pose_capture.py <영상> <모델 .task> <결과 .json>
결과: {"fps": 영상 fps, "frames": [[[x, y, z, 보임 정도] × 33] 또는 사람을 못 찾은 프레임은 null, ...]}
좌표는 MediaPipe의 세계 좌표 그대로다: 미터, 두 엉덩이 가운데가 원점, x 화면 오른쪽, y 아래, z 카메라에서 먼 쪽.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import vision

try:
    from mediapipe.tasks.python import BaseOptions
except ImportError:  # 버전마다 위치가 조금 다르다
    from mediapipe.tasks.python.core.base_options import BaseOptions


def main():
    video, model, out = sys.argv[1:4]
    tmp = None
    if not str(video).isascii():                       # OpenCV·MediaPipe는 한글 경로를 못 여는 경우가 있어 임시로 복사
        tmp = Path(tempfile.mkdtemp(prefix="38sprite_pose_"))
        video = str(shutil.copy(video, tmp / "video.mp4"))
    # 모델도 경로 대신 내용을 넘긴다 (MediaPipe가 한글 경로의 파일을 열지 못한다)
    opts = vision.PoseLandmarkerOptions(base_options=BaseOptions(model_asset_buffer=Path(model).read_bytes()),
                                        running_mode=vision.RunningMode.VIDEO, num_poses=1,
                                        min_pose_detection_confidence=0.4, min_pose_presence_confidence=0.4,
                                        min_tracking_confidence=0.4)
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    frames, i = [], 0
    with vision.PoseLandmarker.create_from_options(opts) as landmarker:
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
            res = landmarker.detect_for_video(image, int(round(i * 1000 / fps)))
            world = res.pose_world_landmarks[0] if res.pose_world_landmarks else None
            frames.append([[round(p.x, 4), round(p.y, 4), round(p.z, 4), round(p.visibility or 0.0, 3)] for p in world]
                          if world else None)
            i += 1
    cap.release()
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"fps": fps, "frames": frames}, f)
    found = sum(1 for f in frames if f)
    print(f"frames={len(frames)} found={found}", flush=True)


if __name__ == "__main__":
    main()
