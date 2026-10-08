"""AI 배경 지우기 합치기 규칙 (AI 모델 없이 가짜 AI 마스크로): 구멍 채우기, 그림자 지우기, 가장자리 보존, 빛 효과."""
import unittest

import numpy as np
from helpers import MAGENTA, canvas

from spritegen import matting
from spritegen.imaging import estimate_bg, frame_alpha


def body_frame():
    im = canvas()
    im[40:120, 60:100] = (60, 120, 200)
    return im


class CombineTest(unittest.TestCase):
    def test_fills_confident_hole(self):
        im = body_frame()
        im[70:85, 72:88] = (250, 40, 245)                  # 몸 한가운데 마젠타에 가까운 색 → 크로마키가 구멍을 냄
        bg = estimate_bg(im)
        ka = frame_alpha(im, bg)
        self.assertLess(ka[77, 80], 0.5)
        ai = np.zeros(ka.shape, np.float32)
        ai[40:120, 60:100] = 1.0                           # AI는 몸 전체를 캐릭터로 봄
        a, info = matting.combine(im, ka, ai, bg, "all")
        self.assertGreater(a[77, 80], 0.9)
        self.assertGreater(info["filled"], 0)

    def test_does_not_fill_when_ai_unsure(self):
        im = body_frame()
        im[70:85, 72:88] = (250, 40, 245)
        bg = estimate_bg(im)
        ka = frame_alpha(im, bg)
        ai = np.zeros(ka.shape, np.float32)
        ai[40:120, 60:100] = 1.0
        ai[70:85, 72:88] = 0.8                             # 빛 궤적 안쪽처럼 애매한 곳
        a, _ = matting.combine(im, ka, ai, bg, "none", fill_conf=0.95)
        self.assertLess(a[77, 80], 0.5)

    def test_removes_shadow_keeps_thin_edges(self):
        im = canvas((200, 200, 200))                       # 회색 배경
        im[40:120, 60:100] = (60, 120, 200)
        im[120:128, 40:120] = (120, 120, 120)              # 발밑 그림자 (배경보다 어두운 회색)
        bg = estimate_bg(im)
        ka = frame_alpha(im, bg)
        self.assertGreater(ka[124, 50], 0.5)               # 크로마키는 그림자를 캐릭터로 남김
        ai = np.zeros(ka.shape, np.float32)
        ai[41:119, 61:99] = 1.0                            # AI 마스크는 가장자리가 1픽셀 더 좁다
        a, info = matting.combine(im, ka, ai, bg, "all")
        self.assertLess(a[124, 50], 0.1)                   # 그림자는 지움
        self.assertGreater(a[40, 80], 0.5)                 # 1픽셀 가장자리 차이는 크로마키 그대로
        self.assertGreater(info["removed"], 0)

    def test_vivid_on_key_background_keeps_effects(self):
        im = body_frame()
        im[20:30, 20:140] = (255, 230, 120)                # 몸에서 떨어진 빛줄기
        bg = estimate_bg(im)
        ka = frame_alpha(im, bg)
        ai = np.zeros(ka.shape, np.float32)
        ai[40:120, 60:100] = 1.0                           # AI는 빛을 배경으로 봄
        a, _ = matting.matte(im, ka, ai, bg, "vivid")
        self.assertGreater(a[25, 30], 0.9)
        b, _ = matting.matte(im, ka, ai, bg, "none")       # 효과 없이: 지운다
        self.assertLess(b[25, 30], 0.1)

    def test_light_alpha_on_changed_background(self):
        bg = (230, 44, 63)                                 # 영상 AI가 바꿔 버린 빨강 배경
        im = canvas(bg)
        im[10:20, 10:20] = (255, 255, 255)                 # 반짝이 (밝아짐)
        im[30:40, 10:20] = (238, 60, 75)                   # 옅은 번짐 (배경과 거의 같음)
        im[50:60, 10:20] = (150, 30, 40)                   # 같은 색으로 어두운 그림자
        im[70:80, 10:20] = (40, 220, 230)                  # 청록 고리 (색이 다름)
        a = matting.light_alpha(im, bg)
        self.assertGreater(a[15, 15], 0.9)
        self.assertLess(a[35, 15], 0.1)
        self.assertLess(a[55, 15], 0.1)
        self.assertGreater(a[75, 15], 0.9)

    def test_finish_keeps_green_character_on_green_background(self):
        im = canvas((40, 230, 40))
        im[40:120, 60:100] = (110, 200, 140)               # 초록빛 캐릭터 (초록 배경 프레임)
        a = np.zeros(im.shape[:2], np.float32)
        a[40:120, 60:100] = 1.0
        out = matting.finish(im, a, estimate_bg(im))
        self.assertEqual(tuple(out[80, 80, :3]), (110, 200, 140))   # 몸 안쪽 초록은 빼지 않는다

    def test_finish_despills_magenta_inside(self):
        im = canvas(MAGENTA)
        im[40:120, 60:100] = (200, 170, 205)               # 은색 갑옷에 비친 마젠타
        a = np.zeros(im.shape[:2], np.float32)
        a[40:120, 60:100] = 1.0
        r, g, b = (int(v) for v in matting.finish(im, a, estimate_bg(im))[80, 80, :3])
        self.assertLessEqual(min(r, b) - g, 2)             # 마젠타 배경은 안쪽도 분홍 기운을 뺀다


if __name__ == "__main__":
    unittest.main()
