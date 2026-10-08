"""편집 AI로 고친 프레임: 바뀐 곳만 끼우기, 시트 조립 때 그 프레임 대신 쓰기."""
import json
import unittest

import numpy as np
from PIL import Image

from helpers import TempDir, attack_frame, write_frames

from spritegen.assemble import assemble
from spritegen.repair import splice


class RepairTest(unittest.TestCase):
    def test_splice_only_changed_area(self):
        orig = np.full((60, 60, 3), (255, 0, 255), np.uint8)
        orig[10:50, 20:40] = (200, 120, 60)                 # 캐릭터
        orig[5:15, 45:58] = (120, 240, 255)                 # 빛 궤적
        edit = orig.copy()
        edit[5:15, 45:58] = (255, 0, 255)                   # 편집 AI가 궤적만 지움
        edit[30, 30] = (201, 121, 61)                       # 몸의 아주 작은 차이는 무시
        out = splice(orig, edit)
        self.assertLess(np.abs(out[8, 50].astype(int) - (255, 0, 255)).max(), 4)   # 궤적 자리는 편집 결과(마젠타)
        self.assertTrue((out[30, 30] == orig[30, 30]).all())

    def test_assemble_uses_repaired_frame(self):
        with TempDir() as td:
            folder = write_frames(td / "motion" / "frames" / "E", [attack_frame(t) for t in range(48)])
            rep = assemble({"E": folder}, 2, (160, 160), 140, td / "out1", kind="oneshot", n_frames=8, char_px=110)
            k = rep["directions"]["E"]["picked"][3]
            fixed = attack_frame(k).copy()
            body = np.abs(fixed.astype(int) - (255, 0, 255)).sum(-1) > 60
            fixed[body] = (30, 200, 30)                      # 고친 그림은 몸 색이 다르다 (확인용)
            (td / "motion" / "repaired" / "E").mkdir(parents=True)
            Image.fromarray(fixed).save(td / "motion" / "repaired" / "E" / f"{k:05d}.png")
            assemble({"E": folder}, 2, (160, 160), 140, td / "out2", kind="oneshot", n_frames=8, char_px=110)
            meta = json.loads((td / "out2" / "sheet_hd.json").read_text(encoding="utf-8"))
            r = meta["directions"]["E"][3]
            cell = np.asarray(Image.open(td / "out2" / "sheet_hd.png").convert("RGBA"))[r["y"]:r["y"] + r["h"], r["x"]:r["x"] + r["w"]]
            solid = cell[..., 3] > 200
            self.assertGreater(((cell[..., 1] > 150) & (cell[..., 0] < 90) & solid).sum(), 0.5 * solid.sum())


if __name__ == "__main__":
    unittest.main()
