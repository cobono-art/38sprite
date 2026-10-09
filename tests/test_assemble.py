"""시트 조립: 반복 동작의 한 바퀴·이동 속도, 방향끼리 같은 걸음 수, 한 번 동작의 타격 칸, 재생 속도 바꾸기."""
import json
import unittest

from helpers import TempDir, attack_frame, walk_frame, write_frames

import numpy as np

from spritegen.assemble import assemble, common_cycle, retime, set_move_scale, stance_dx


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

    @staticmethod
    def curve(valleys, top=4.0):
        """반복 점수 곡선 흉내: 골(간격, 가장 좋은 것 대비 점수)마다 V자, 나머지는 높게. 간격 8~60."""
        return {p: min([top] + [rel + 0.12 * abs(p - v) for v, rel in valleys]) for p in range(8, 61)}

    def test_common_cycle_one_cycle_everywhere(self):
        """방향마다 따로 고르면 S는 한 바퀴(17), N·NE는 두 바퀴(48·45)를 골랐던 걷기 (2026-10-09 실제 골 위치):
        모두 한 바퀴씩, 방향마다 걷는 빠르기 차이(S가 빠름)는 그대로."""
        sc = {"S": self.curve([(9, 2.61), (17, 1.0), (26, 2.62), (35, 1.06), (52, 1.51)]),
              "SE": self.curve([(12, 6.64), (24, 1.0), (36, 6.68), (48, 1.02)]),
              "E": self.curve([(12, 2.26), (24, 1.0), (36, 2.51), (47, 1.31)]),
              "NE": self.curve([(9, 2.42), (19, 1.85), (26, 1.59), (36, 2.54), (45, 1.0)]),
              "N": self.curve([(10, 2.16), (20, 1.26), (28, 1.63), (39, 1.85), (48, 1.0)])}
        c, lengths = common_cycle(sc)
        self.assertAlmostEqual(c, 24, delta=2)
        self.assertEqual(lengths, {"S": 17, "SE": 24, "E": 24, "NE": 26, "N": 20})
        # 달리기: N만 세 바퀴(48)가 가장 잘 맞았다 → 한 바퀴(18)
        run = {"S": self.curve([(12, 1.0), (25, 1.29), (37, 1.4)]), "SE": self.curve([(16, 1.0), (31, 1.24)]),
               "E": self.curve([(15, 1.0), (31, 1.04), (46, 1.03)]), "N": self.curve([(12, 1.65), (18, 1.22), (30, 1.33), (48, 1.0)])}
        c, lengths = common_cycle(run)
        self.assertEqual(lengths["N"], 18)
        self.assertTrue(all(10 <= v <= 20 for v in lengths.values()), lengths)

    def test_common_cycle_doubles_when_one_step_looks_like_a_cycle(self):
        """망토로 다리가 가려져 한 걸음(12)이 한 바퀴처럼 보여도, 대부분 방향에서 두 걸음(24)이 확실히 더 맞으면 두 걸음."""
        sc = {d: self.curve([(12, 1.0), (24, 0.5), (36, 1.0), (48, 0.5)]) for d in ("S", "E", "N")}
        c, lengths = common_cycle(sc)
        self.assertEqual(set(lengths.values()), {24})

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
