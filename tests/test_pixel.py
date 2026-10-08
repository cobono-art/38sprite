"""도트 마감: 작은 잡티 합치기, 장마다 색이 바뀌는 지글거림 줄이기."""
import unittest

import numpy as np

from spritegen.imaging import merge_specks, pixelate


class PixelTest(unittest.TestCase):
    def test_merge_specks_keeps_dark_and_edges(self):
        q = np.ones((7, 7), np.int64)
        a = np.ones((7, 7), bool)
        protect = np.array([False, False, False, True])
        q[3, 3] = 2                                  # 면 안의 1픽셀 잡티 → 둘레 색(1)
        q[1, 5] = 3                                  # 어두운 색(눈) → 그대로
        q[0, 0] = 2                                  # 가장자리에 걸친 조각 → 그대로
        out = merge_specks(q, a, 4, protect, max_size=2)
        self.assertEqual(out[3, 3], 1)
        self.assertEqual(out[1, 5], 3)
        self.assertEqual(out[0, 0], 2)
        q[2:5, 2:5] = 2                              # 9픽셀 조각은 진짜 모양 → 그대로
        self.assertTrue((merge_specks(q, a, 4, protect, max_size=2)[2:5, 2:5] == 2).all())

    def test_hold_reduces_flicker(self):
        rng = np.random.default_rng(3)
        base = np.zeros((96, 64, 4), np.uint8)
        base[8:90, 12:52] = (200, 120, 60, 255)
        base[30:60, 20:44] = (90, 140, 200, 255)
        frames = []
        for _ in range(6):                          # 같은 그림에 잔잡음만 (대기 동작처럼 거의 안 움직임)
            f = base.copy()
            noise = rng.integers(-40, 41, size=f[..., :3].shape)
            f[..., :3] = np.clip(f[..., :3].astype(int) + noise * (f[..., 3:] > 0), 0, 255).astype(np.uint8)
            frames.append(f)

        def changes(out):
            return sum(int((np.abs(a[..., :3].astype(int) - b[..., :3].astype(int)).sum(-1) > 0).sum())
                       for a, b in zip(out, out[1:]))
        plain, _ = pixelate(frames, 48, 6, outline=False)
        held, _ = pixelate(frames, 48, 6, outline=False, seq_len=6)
        self.assertLessEqual(changes(held), changes(plain))


if __name__ == "__main__":
    unittest.main()
