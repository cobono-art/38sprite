"""파이프라인 도우미: 영상 길이, 걷기 판단, 시드 바꾸기, 배경 검사, 마네킹 키프레임 줄이기, 프롬프트 배경 지시."""
import unittest

from helpers import TempDir, walk_frame, write_frames

from spritegen import comfy, prompts
from spritegen import mannequin as mq
from spritegen import pipeline as pl


class PipelineHelpersTest(unittest.TestCase):
    def test_default_seconds(self):
        self.assertEqual(pl.default_seconds("loop", "direct"), 3)
        self.assertEqual(pl.default_seconds("oneshot", "mannequin"), 3)
        self.assertEqual(pl.default_seconds("oneshot", "direct", hold_end=True), 5)
        self.assertEqual(pl.default_seconds("loop", "direct", "video"), 5)
        self.assertEqual(pl.default_seconds("loop", "mannequin"), 5)

    def test_frames_for_seconds_grid(self):
        for sec, n in ((3.0, 73), (5, 124)):
            self.assertEqual(comfy.frames_for_seconds(sec), n)
            self.assertEqual((n - 5) % 17, 0)                   # H3의 17k+5 프레임 격자

    def test_is_locomotion(self):
        self.assertTrue(pl.is_locomotion({"key": "walk", "kind": "loop"}))
        self.assertTrue(pl.is_locomotion({"name": "제자리 달리기", "kind": "loop"}))
        self.assertFalse(pl.is_locomotion({"key": "idle", "name": "대기", "kind": "loop", "text": "걷지 않고 서 있다"}))
        self.assertFalse(pl.is_locomotion({"name": "문워크 춤", "kind": "loop"}))
        self.assertFalse(pl.is_locomotion({"name": "걸어가며 베기", "kind": "oneshot"}))

    def test_reseed_changes_only_the_seed(self):
        wf = comfy.i2v_workflow("a.png", "a.png", "walk", 640, 640, 73, 123, "x")
        wf2 = pl._reseed(wf)
        self.assertNotEqual(wf2["s_noise"]["inputs"]["noise_seed"], 123)
        wf2["s_noise"]["inputs"]["noise_seed"] = 123
        self.assertEqual(wf, wf2)
        self.assertIsNone(pl._reseed({"n": {"inputs": {"x": 1}}}))

    def test_find_server_prefers_h3(self):
        alive = {"http://127.0.0.1:8188": False, "http://127.0.0.1:8189": True}   # 8188은 켜져 있지만 H3 모델 없음
        h3 = comfy.DEFAULT_MODELS["i2v"]

        def fake(url, payload=None, timeout=60):
            base = url.rsplit("/", 2)[0] if "object_info" in url else url.rsplit("/", 1)[0]
            if base not in alive:
                raise OSError("connection refused")
            if url.endswith("/object_info/UNETLoader"):          # 모델 파일 목록 (H3 노드는 어느 쪽에나 있다)
                names = ["flux.safetensors"] + ([h3] if alive[base] else [])
                return {"UNETLoader": {"input": {"required": {"unet_name": [names]}}}}
            return {}
        saved = comfy.http_json
        comfy.http_json = fake
        try:
            self.assertEqual(comfy.find_server(), "http://127.0.0.1:8189")
            alive["http://127.0.0.1:8189"] = False
            self.assertEqual(comfy.find_server(), "http://127.0.0.1:8188")   # H3가 없으면 처음 응답한 곳
            alive.clear()
            self.assertIsNone(comfy.find_server())
        finally:
            comfy.http_json = saved

    def test_bg_drift(self):
        frames = [walk_frame(t) for t in range(20)] + [walk_frame(t, bg=(0, 230, 0)) for t in range(20, 30)]
        with TempDir() as td:
            drift, total = pl.bg_drift(write_frames(td, frames), step=1)
        self.assertEqual((drift, total), (10, 30))

    def test_fit_keys_shortens_waiting_only(self):
        pose_a, pose_b = {"r_elbow": [0, 0, 1]}, {"r_elbow": [1, 0, 0]}
        keys = [dict(pose_a, t=0.0), dict(pose_a, t=1.2), dict(pose_b, t=1.45), dict(pose_a, t=3.0),
                dict(pose_a, t=5.2)]
        out = mq.fit_keys(keys, 3.04)
        ts = [k["t"] for k in out]
        self.assertEqual(ts[0], 0.0)
        self.assertAlmostEqual(ts[1], 0.4)                       # 처음 기다림 1.2초 → 0.4초
        self.assertAlmostEqual(ts[3] - ts[1], 1.8, places=2)     # 동작 길이는 그대로
        self.assertEqual(ts[-1], 3.04)
        self.assertEqual(ts, sorted(ts))
        self.assertIs(mq.fit_keys(keys, 6.0), keys)              # 이미 들어가면 그대로

    def test_prompts_keep_magenta(self):
        tail = prompts.tail(False)
        self.assertIn("magenta (#FF00FF)", tail)
        self.assertIn("every single frame", tail)
        self.assertNotIn("magenta", prompts.tail(False, gray=True).split("character is lit")[0])
        m = prompts.mannequin_prompt(45, "S", "slash")
        self.assertIn("every single frame", m)                   # 마네킹 모드도 기본은 마젠타


if __name__ == "__main__":
    unittest.main()
