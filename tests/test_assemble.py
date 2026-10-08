"""시트 조립: 반복 동작의 한 바퀴·이동 속도, 한 번 동작의 타격 칸, 재생 속도 바꾸기."""
import json
import unittest

from helpers import TempDir, attack_frame, walk_frame, write_frames

import numpy as np

from spritegen.assemble import assemble, retime, set_move_scale, stance_dx


class AssembleTest(unittest.TestCase):
    def test_loop_walk_sheet_and_move_speed(self):
        with TempDir() as td:
            folder = write_frames(td / "frames" / "E", [walk_frame(t) for t in range(64)])
            rep = assemble({"E": folder}, 2, (160, 160), 140, td / "out", kind="loop", n_frames=8,
                           char_px=110, locomotion=True, ground_y=0.5)
            meta = json.loads((td / "out" / "sheet_hd.json").read_text(encoding="utf-8"))
            d = rep["directions"]["E"]
            self.assertIn(d["period_frames"], (16, 32))          # 한 바퀴 (두 걸음)
            self.assertEqual(meta["order"], ["W", "E"])
            self.assertEqual(len(meta["directions"]["E"]), rep["frames"])
            self.assertTrue(meta["loop"])
            self.assertAlmostEqual(meta["frame_ms"], round(1000 / meta["fps"], 1), places=1)
            self.assertGreater(meta["move_speed"], 0)            # 걷기는 이동 속도가 있다
            self.assertEqual(meta["velocity"]["E"][1], 0.0)      # 옆으로 가면 세로 속도 0
            self.assertLess(meta["velocity"]["W"][0], 0)         # 왼쪽은 음수
            self.assertEqual(rep["sources"]["W"], "E 반전")
            for f in ("sheet_hd.png", "preview_hd.gif", "hd_E.gif", "hd_W.gif", "report.json"):
                self.assertTrue((td / "out" / f).exists(), f)

    def test_oneshot_hit_frame(self):
        with TempDir() as td:
            folder = write_frames(td / "frames" / "E", [attack_frame(t) for t in range(48)])
            rep = assemble({"E": folder}, 2, (160, 160), 140, td / "out", kind="oneshot", n_frames=8, char_px=110)
            meta = json.loads((td / "out" / "sheet_hd.json").read_text(encoding="utf-8"))
            self.assertFalse(meta["loop"])
            self.assertFalse(meta["hold_last"])
            picked = rep["directions"]["E"]["picked"]
            peak = rep["directions"]["E"]["peak_frame"]
            self.assertTrue(17 <= peak <= 23, peak)              # 팔이 가장 길 때 (가운데 20)
            self.assertEqual(picked[meta["hit_frame"]], peak)   # 타격 칸 = 가장 크게 움직인 프레임
            self.assertEqual(meta["hit_frames"]["W"], meta["hit_frame"])
            self.assertNotIn("move_speed", meta)

    def test_retime_scales_speed(self):
        with TempDir() as td:
            folder = write_frames(td / "frames" / "E", [walk_frame(t) for t in range(64)])
            assemble({"E": folder}, 2, (160, 160), 140, td / "out", kind="loop", n_frames=8, char_px=110,
                     locomotion=True)
            before = json.loads((td / "out" / "sheet_hd.json").read_text(encoding="utf-8"))
            retime(td / "out", 2, before["fps"] * 2)
            after = json.loads((td / "out" / "sheet_hd.json").read_text(encoding="utf-8"))
            self.assertAlmostEqual(after["move_speed"], before["move_speed"] * 2, delta=0.2)
            self.assertAlmostEqual(after["frame_ms"], before["frame_ms"] / 2, delta=0.2)

    def test_stance_dx_tracks_planted_foot(self):
        """땅에 닿은 발이 장마다 3px씩 뒤로 가다가(디딤) 발을 바꿀 때 앞으로 튀는 제자리 걷기 → 3px/장."""
        alphas, x = [], 60
        for t in range(36):
            a = np.zeros((120, 120), np.float32)
            a[20:100, 50:70] = 1                            # 몸
            a[100:110, x:x + 8] = 1                          # 땅에 닿은 발
            alphas.append(a)
            x = x - 3 if t % 12 < 9 else x + 9               # 9장 디딤(뒤로 3px), 3장 발 바꿈(앞으로 9px)
        self.assertAlmostEqual(stance_dx(alphas), 3.0, delta=0.3)

    def test_move_scale_rewrites_speed(self):
        with TempDir() as td:
            folder = write_frames(td / "frames" / "E", [walk_frame(t) for t in range(64)])
            assemble({"E": folder}, 2, (160, 160), 140, td / "out", kind="loop", n_frames=8, char_px=110,
                     locomotion=True)
            before = json.loads((td / "out" / "sheet_hd.json").read_text(encoding="utf-8"))
            self.assertEqual(before["move_speed"], before["move_speed_auto"])
            set_move_scale(td / "out", 1.5)
            after = json.loads((td / "out" / "sheet_hd.json").read_text(encoding="utf-8"))
            self.assertAlmostEqual(after["move_speed"], before["move_speed_auto"] * 1.5, delta=0.2)
            self.assertAlmostEqual(after["velocity"]["E"][0], after["move_speed"], delta=0.2)
            self.assertEqual(after["move_scale"], 1.5)
            retime(td / "out", 2, after["fps"] * 2)          # 재생 속도를 바꿔도 배율은 그대로
            again = json.loads((td / "out" / "sheet_hd.json").read_text(encoding="utf-8"))
            self.assertAlmostEqual(again["move_speed"], again["move_speed_auto"] * 1.5, delta=0.3)

    def test_background_change_is_reported(self):
        frames = [walk_frame(t) for t in range(64)]
        frames[20:50] = [walk_frame(t, bg=(0, 230, 0)) for t in range(20, 50)]   # 영상 AI가 배경을 초록으로 바꿈
        with TempDir() as td:
            folder = write_frames(td / "frames" / "E", frames)
            rep = assemble({"E": folder}, 2, (160, 160), 140, td / "out", kind="loop", n_frames=8, char_px=110)
            self.assertEqual(rep["directions"]["E"]["bg_changed"], 30)
            self.assertIn("bg", [q["type"] for q in rep["qa"]])


if __name__ == "__main__":
    unittest.main()
