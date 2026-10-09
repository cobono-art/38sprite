"""도트 마감: 작은 잡티 합치기, 장마다 색이 바뀌는 지글거림 줄이기, 도트풍 그림의 칸 크기 재기, 원본 머리 붙이기."""
import unittest

import numpy as np

import cv2
import helpers  # noqa: F401 — 저장소 폴더를 sys.path에 (이 파일만 돌려도 되게)

from spritegen.imaging import head_mask, keep_head, merge_specks, pixel_cell_size, pixelate


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

    @staticmethod
    def fake_pixel_art(cell, rows=60, cols=34, seed=5, smooth_scale=None):
        """진짜 도트(색 5개 덩어리 + 어두운 외곽선)를 칸 cell px로 정수배 확대. smooth_scale을 주면 그것을 다시
        부드럽게(바이큐빅) 키운다 — 코덱스 그림처럼 작은 정수 칸 그림을 정수가 아닌 배율로 키운 '도트풍' 그림."""
        rng = np.random.default_rng(seed)
        low = cv2.resize(rng.random((6, 4)).astype(np.float32), (cols, rows), interpolation=cv2.INTER_CUBIC)
        idx = np.digitize(low, np.quantile(low, [0.2, 0.4, 0.6, 0.8]))
        pal = np.array([[220, 170, 40], [40, 120, 140], [230, 210, 190], [120, 70, 40], [200, 60, 60]], np.uint8)
        art = pal[idx]
        yy, xx = np.mgrid[:rows, :cols]
        body = ((yy - rows / 2) / (rows / 2)) ** 2 + ((xx - cols / 2) / (cols / 2)) ** 2 < 1
        edge = body & ~cv2.erode(body.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        art[edge] = (20, 16, 24)
        img = cv2.resize(art, (cols * cell, rows * cell), interpolation=cv2.INTER_NEAREST)
        mask = cv2.resize(body.astype(np.uint8), (cols * cell, rows * cell), interpolation=cv2.INTER_NEAREST)
        if smooth_scale:
            size = (round(img.shape[1] * smooth_scale), round(img.shape[0] * smooth_scale))
            img = cv2.resize(img, size, interpolation=cv2.INTER_CUBIC)
            mask = cv2.resize(mask, size, interpolation=cv2.INTER_NEAREST)
        return img, mask.astype(bool)

    def test_pixel_cell_size(self):
        """도트풍 그림의 칸 크기를 찾는다: 코덱스처럼 작은 정수 칸 그림을 부드럽게 키운 것(칸이 정수가 아님)과
        정수배로 키운 진짜 도트. 매끈한 그림은 도트가 아니라고 본다."""
        for cell, scale in ((4, 1.2246), (6, 1.1), (8, 1.2246), (7, None), (4, None)):
            img, mask = self.fake_pixel_art(cell, smooth_scale=scale)
            want = cell * (scale or 1)
            h, w = mask.shape
            p, score = pixel_cell_size(img, [((0, 0, w, h), mask)])
            self.assertIsNotNone(p, (cell, scale, score))
            self.assertAlmostEqual(p, want, delta=0.06)
            self.assertAlmostEqual(h / p, 60, delta=1)
        img, mask = self.fake_pixel_art(4, smooth_scale=1.3)
        smooth = cv2.GaussianBlur(img, (0, 0), 6)                       # HD처럼 칸 경계가 없는 그림
        h, w = mask.shape
        self.assertIsNone(pixel_cell_size(smooth, [((0, 0, w, h), mask)])[0])

    @staticmethod
    def doll(dy=0, face=(240, 200, 160), eye=(30, 30, 30)):
        """도트 인형 흉내 (40x24): 머리(후드·얼굴·눈) - 좁은 목 - 넓은 몸. dy만큼 아래로."""
        im = np.zeros((40, 24, 4), np.uint8)
        y = 2 + dy
        im[y:y + 12, 4:20] = (230, 180, 40, 255)          # 후드
        im[y + 4:y + 11, 7:17] = face + (255,)             # 얼굴
        im[y + 6, 9] = im[y + 6, 14] = eye + (255,)        # 눈
        im[y + 12:y + 14, 10:14] = (230, 180, 40, 255)     # 목 (좁음)
        im[y + 14:y + 30, 3:21] = (40, 120, 140, 255)      # 몸
        return im

    def test_head_mask_stops_at_neck(self):
        m = head_mask(self.doll())
        rows = np.where(m.any(1))[0]
        self.assertEqual((rows.min(), rows.max()), (2, 13))   # 후드 위 ~ 목, 몸은 빠짐

    def test_keep_head_pastes_original_where_it_matches(self):
        """머리가 한 칸 내려가고 얼굴색이 살짝 흔들린 장면 → 원본 머리를 그 자리에 그대로. 얼굴이 딴 모양이면 그대로 둔다."""
        ref = self.doll()
        wobbly = self.doll(dy=1, face=(236, 204, 156))       # 영상 AI를 거쳐 얼굴색이 살짝 다름
        wobbly[9, 10] = (120, 60, 40, 255)                   # 눈 자리 흔들림
        other = self.doll(face=(40, 120, 140), eye=(240, 240, 240))   # 머리가 돌아가 얼굴이 안 보임 (다른 색)
        other[2:14, 4:20, :3] = (90, 40, 140)
        out, n = keep_head([wobbly, other], ref)
        self.assertEqual(n, 1)
        self.assertTrue((out[0][3:15] == ref[2:14]).all())   # 원본 머리를 한 칸 아래에
        self.assertTrue((out[1] == other).all())

if __name__ == "__main__":
    unittest.main()
