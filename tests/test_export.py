"""게임 엔진용 내보내기: Aseprite JSON, Godot SpriteFrames 메타데이터, 사용법 안내, ZIP 내용."""
import json
import unittest

from helpers import TempDir, attack_frame, walk_frame, write_frames

from spritegen import export
from spritegen.assemble import assemble

META = {"image": "sheet_hd.png", "frame_w": 100, "frame_h": 120, "fps": 8.0, "pivot": [50, 110], "loop": False,
        "hit_frame": 3, "hit_frames": {"S": 3, "E": 4}, "hold_last": False, "frame_ms": 125.0, "order": ["S", "E"],
        "directions": {"S": [{"x": 0, "y": 0, "w": 100, "h": 120}], "E": [{"x": 0, "y": 120, "w": 100, "h": 120}]}}


class ExportTest(unittest.TestCase):
    def test_aseprite_one_shot_plays_once_with_game_info(self):
        a = export.aseprite_json(META, "sheet_hd.png")
        self.assertEqual(a["meta"]["frameTags"][0]["repeat"], "1")
        self.assertEqual(a["meta"]["hit_frame"], 3)
        self.assertEqual(a["meta"]["frame_ms"], 125.0)
        self.assertEqual(sorted(a["animations"]), ["E", "S"])
        self.assertEqual(a["frames"]["0"]["duration"], 125)

    def test_aseprite_loop_has_no_repeat(self):
        a = export.aseprite_json(dict(META, loop=True), "sheet_hd.png")
        self.assertNotIn("repeat", a["meta"]["frameTags"][0])

    def test_godot_metadata(self):
        tres = export.godot_tres([("", META, "sheet_hd.png")])
        self.assertIn('metadata/sprite_info = {"frame_ms": 125, "hit_frame": 3', tres)
        walk = {k: v for k, v in META.items() if k not in ("hit_frame", "hit_frames", "hold_last")}
        walk.update(loop=True, move_speed=120.5, velocity={"S": [0.0, 60.2]})
        merged = export.godot_tres([("attack", META, "a.png"), ("walk", walk, "w.png")])
        self.assertIn('"walk": {"frame_ms": 125, "move_speed": 120.5, "velocity": {"S": [0, 60.2]}}', merged)
        self.assertIn('"name": &"walk_S"', merged)

    def test_godot_value(self):
        self.assertEqual(export.godot_value({"a": [1, 2.5, True, "x"]}), '{"a": [1, 2.5, true, "x"]}')

    def test_usage_text_explains_game_info(self):
        text = export.usage_text("attack", {"hd": META})
        self.assertIn("hit_frame: 3", text)
        self.assertNotIn("move_speed", text)

    def test_engine_files_from_real_sheet(self):
        with TempDir() as td:
            folder = write_frames(td / "frames" / "E", [walk_frame(t) for t in range(64)])
            assemble({"E": folder}, 2, (160, 160), 140, td / "out", kind="loop", n_frames=8, char_px=110,
                     locomotion=True)
            files = export.engine_files(td / "out", "walk")
            for name in ("walk_aseprite.json", "godot/walk.tres", "godot/walk.tscn", "godot/sheet_hd.png",
                         "frames/hd/E/E_00.png", "frames/hd/W/W_00.png", "엔진에서_쓰는_법.txt"):
                self.assertIn(name, files)
            self.assertIn("move_speed", json.loads(files["walk_aseprite.json"])["meta"])
            self.assertIn("metadata/sprite_info", files["godot/walk.tres"].decode("utf-8"))

    def test_project_godot_merges_motions(self):
        with TempDir() as td:
            walk = write_frames(td / "w" / "E", [walk_frame(t) for t in range(64)])
            atk = write_frames(td / "a" / "E", [attack_frame(t) for t in range(48)])
            assemble({"E": walk}, 2, (160, 160), 140, td / "wout", kind="loop", n_frames=8, char_px=110)
            assemble({"E": atk}, 2, (160, 160), 140, td / "aout", kind="oneshot", n_frames=8, char_px=110)
            files = export.project_godot([("walk", td / "wout"), ("attack", td / "aout")])
            tres = files["godot_all/character.tres"].decode("utf-8")
            self.assertIn('&"walk_E"', tres)
            self.assertIn('&"attack_W"', tres)
            self.assertIn("margin = Rect2(", tres)                # 칸 크기·발 위치를 하나로 맞춤


class MotionKeyTest(unittest.TestCase):
    def test_motion_key(self):
        used = set()
        self.assertEqual(export.motion_key({"name": "걷기"}, used), "walk")
        self.assertEqual(export.motion_key({"name": "걷기 2"}, used), "walk2")
        self.assertEqual(export.motion_key({"name": "Moon Walk!"}), "moon_walk")
        self.assertEqual(export.motion_key({"name": "엉뚱한 동작"}), "motion")


if __name__ == "__main__":
    unittest.main()
