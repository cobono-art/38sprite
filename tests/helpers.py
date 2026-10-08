"""테스트용 가짜 영상 프레임: 마젠타 배경 위에 몸·다리·팔을 네모로 그린다 (영상 AI 없이 시트 조립을 시험)."""
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MAGENTA = (255, 0, 255)
SIZE = 160


def canvas(bg=MAGENTA, size=SIZE):
    return np.full((size, size, 3), bg, np.uint8)


def walk_frame(t, period=16, bg=MAGENTA):
    """옆으로 걷는 막대 사람: 다리 두 개가 period 프레임마다 한 바퀴 앞뒤로 벌어졌다 모인다. 발끝 y=140."""
    im = canvas(bg)
    im[50:110, 70:90] = (60, 120, 200)                 # 몸 (파랑)
    im[30:50, 72:88] = (240, 200, 160)                 # 머리
    swing = int(round(14 * np.sin(2 * np.pi * t / period)))
    for dx in (swing, -swing):                         # 다리 두 개
        x = 80 + dx
        im[110:140, x - 4:x + 4] = (40, 40, 40)
    return im


def attack_frame(t, start=10, end=30, bg=MAGENTA):
    """한 번 휘두르는 동작: start~end 사이에 팔이 앞으로 뻗었다가 돌아온다 (가장 길 때가 가운데)."""
    im = canvas(bg)
    im[50:110, 70:90] = (60, 120, 200)
    im[30:50, 72:88] = (240, 200, 160)
    im[110:140, 74:86] = (40, 40, 40)
    if start <= t <= end:
        reach = int(round(50 * np.sin(np.pi * (t - start) / (end - start))))
        if reach > 0:
            im[66:74, 90:90 + reach] = (230, 230, 60)  # 팔 (노랑)
    return im


def write_frames(folder, frames):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(frames):
        Image.fromarray(f).save(folder / f"f_{i:05d}_.png")
    return folder


class TempDir:
    def __enter__(self):
        self._td = tempfile.TemporaryDirectory()
        return Path(self._td.name)

    def __exit__(self, *exc):
        self._td.cleanup()
