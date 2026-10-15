"""시트 줄이기: Lanczos가 가장자리 밖에 남기는 거의 투명한 칸(투명도를 무시하는 화면에서 흰 점선 테두리)이 없다."""
import unittest

import helpers  # noqa: F401  (저장소 폴더를 불러오기 경로에)

import numpy as np
from PIL import Image

from spritegen.imaging import shrink_rgba


def figure():
    im = np.zeros((240, 200, 4), np.uint8)
    yy, xx = np.mgrid[:240, :200]
    body = ((yy - 130) / 80.0) ** 2 + ((xx - 100) / 55.0) ** 2 < 1
    im[body] = [70, 45, 30, 255]
    im[body & (xx > 100)] = [235, 230, 220, 255]          # 밝은 옷 (흰 테두리가 잘 튀는 색)
    return im


class ShrinkTest(unittest.TestCase):
    def test_no_faint_fringe(self):
        im = figure()
        plain = np.asarray(Image.fromarray(im).resize((86, 103), Image.LANCZOS))
        out = shrink_rgba(im, 0.43)
        faint = lambda a: int(((a > 0) & (a <= 12)).sum())
        self.assertGreater(faint(plain[..., 3]), 0)        # 그냥 Lanczos는 옅은 칸이 생긴다 (이 시험이 뜻이 있는지)
        self.assertEqual(faint(out[..., 3]), 0)
        self.assertEqual(out.shape[:2], (103, 86))

    def test_keeps_soft_edge_and_body(self):
        out = shrink_rgba(figure(), 0.43)
        a = out[..., 3]
        self.assertGreater(int((a == 255).sum()), 2000)                # 몸은 그대로 (줄인 타원 넓이 약 2560칸)
        self.assertGreater(int(((a > 12) & (a < 255)).sum()), 50)      # 부드러운 가장자리(반투명)는 남는다


if __name__ == "__main__":
    unittest.main()
