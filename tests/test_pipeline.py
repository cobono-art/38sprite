"""파이프라인 도우미: 영상 길이, 걷기 판단, 시드 바꾸기, 배경 검사, 마네킹 키프레임 줄이기, 프롬프트 배경 지시."""
import json
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

    def test_turbo_steps_setting(self):
        from spritegen import project
        steps = lambda wf: wf["s_sched"]["inputs"]["steps"]   # noqa: E731
        saved = project.load_config
        try:
            project.load_config = lambda: {}
            self.assertEqual(steps(comfy.i2v_workflow("a.png", "a.png", "walk", 640, 640, 73, 1, "x")), 6)
            self.assertEqual(steps(comfy.i2v_workflow("a.png", "a.png", "walk", 640, 640, 73, 1, "x", turbo=False)), 20)
            project.load_config = lambda: {"turbo_steps": 8}
            self.assertEqual(steps(comfy.i2v_workflow("a.png", "a.png", "walk", 640, 640, 73, 1, "x")), 8)
            project.load_config = lambda: {}
            self.assertEqual(steps(comfy.r2v_workflow("a.png", "m.mp4", "p", 640, 640, 73, 1, "x", turbo=True)), 6)
            self.assertEqual(steps(comfy.r2v_workflow("a.png", "m.mp4", "p", 640, 640, 73, 1, "x")), 20)
        finally:
            project.load_config = saved

    def test_add_negative_node(self):
        """'빼는 낱말' 노드는 가이드까지 붙은 조건과 모델을 받아 BasicGuider로 넘긴다. 0이면 안 끼운다."""
        from spritegen import project
        saved = project.load_config
        try:
            project.load_config = lambda: {}
            wf = comfy.r2v_workflow("a.png", "m.mp4", "p", 640, 640, 73, 1, "x", turbo=True, guides=[("a.png", 0)])
            cond, model = wf["s_guider"]["inputs"]["conditioning"], wf["s_guider"]["inputs"]["model"]
            wf = comfy.add_negative(json.loads(json.dumps(wf)))
            n = wf["s_neg"]
            self.assertEqual(n["class_type"], comfy.NEG_NODE)
            self.assertEqual((n["inputs"]["conditioning"], n["inputs"]["model"]), (cond, model))
            self.assertEqual(n["inputs"]["clip"], ["m_clip", 0])
            self.assertEqual(n["inputs"]["weight"], 1.5)
            self.assertIn("slash trail", n["inputs"]["negative"])
            self.assertEqual(wf["s_guider"]["inputs"], {"model": ["s_neg", 0], "conditioning": ["s_neg", 1]})
            self.assertEqual(pl._reseed(wf)["s_neg"], wf["s_neg"])          # 새 시드로 다시 만들 때도 그대로
            project.load_config = lambda: {"negative_weight": 0}
            plain = comfy.i2v_workflow("a.png", "a.png", "walk", 640, 640, 73, 1, "x")
            self.assertNotIn("s_neg", comfy.add_negative(json.loads(json.dumps(plain))))
        finally:
            project.load_config = saved

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

    def test_wait_survives_short_disconnect(self):
        calls = {"n": 0}

        def flaky(server, prompt_id):
            calls["n"] += 1
            if calls["n"] < 3:
                raise OSError("WinError 10048")                  # 잠깐 연결 실패
            return ("running", None) if calls["n"] < 4 else ("done", {"outputs": {}})
        saved = comfy.state
        comfy.state = flaky
        try:
            entry, _ = comfy.wait("http://x", "p", poll=0)
            self.assertEqual(entry, {"outputs": {}})
            calls["n"] = -10**9                                  # 계속 실패하면 한도 뒤에 멈춘다
            with self.assertRaises(RuntimeError):
                comfy.wait("http://x", "p", poll=0.01, offline_limit=0.05)
        finally:
            comfy.state = saved

    def test_bg_drift(self):
        frames = [walk_frame(t) for t in range(20)] + [walk_frame(t, bg=(0, 230, 0)) for t in range(20, 30)]
        with TempDir() as td:
            drift, total = pl.bg_drift(write_frames(td, frames), step=1)
        self.assertEqual((drift, total), (10, 30))

    def test_bg_drift_catches_patterns(self):
        """마젠타 위에 그린 동심원 무늬도 배경이 바뀐 것으로 본다 (가장자리 중앙값은 마젠타 그대로라도)."""
        import cv2
        frames = [walk_frame(t) for t in range(10)]
        for t in range(10, 16):
            f = walk_frame(t).copy()
            h, w = f.shape[:2]
            for r in range(10, 2 * max(h, w), 18):
                cv2.circle(f, (w // 2, h // 2), r, (40, 200, 220), 5)
            frames.append(f)
        self.assertEqual(pl.bg_pattern(frames[0]), pl.bg_pattern(frames[0]))   # 결정적
        self.assertLess(pl.bg_pattern(frames[0]), 0.05)
        self.assertGreater(pl.bg_pattern(frames[12]), 0.1)
        with TempDir() as td:
            drift, total = pl.bg_drift(write_frames(td, frames), step=1)
        self.assertEqual((drift, total), (6, 16))

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

    def test_video_prompts_name_no_unwanted_things(self):
        """H3에는 원하지 않는 것을 이름으로 적지 않는다 (적으면 그 낱말이 내용으로 읽혀 오히려 궤적·빛이 생겼다).
        빛 효과를 살리는 동작(vivid)만 효과를 적는다."""
        texts = [prompts.tail(False), prompts.tail(False, gray=True),
                 prompts.motion_prompt("loop", "걷기", 45, "S"), prompts.motion_prompt("oneshot", "베기", 45, "E", "pixel"),
                 prompts.mannequin_prompt(45, "E", "베기"), prompts.reference_prompt("loop", 45, "S"),
                 prompts.follow_prompt("oneshot", 45, "SE")]
        for t in texts:
            low = t.lower()
            for word in ("trail", "glow", "particle", "sparkle", "effect", "shadow", "no blur", "no text", "no zoom"):
                self.assertNotIn(word, low, (word, t[:80]))
        self.assertNotIn("empty", prompts.mannequin_prompt(45, "E").lower())   # 마네킹 손이 비어도 캐릭터 무기는 그대로
        self.assertIn("sparkling", prompts.tail(True))

    def test_negative_node_file(self):
        """ComfyUI에 복사해 쓰는 노드 파일: 문법이 맞고, 앱이 찾는 노드 이름을 내보낸다 (torch 없이 문법만 본다)."""
        from pathlib import Path
        src = (Path(__file__).resolve().parent.parent / "comfyui_nodes" / "sprite_neg_h3" / "__init__.py").read_text(encoding="utf-8")
        compile(src, "sprite_neg_h3/__init__.py", "exec")
        self.assertIn(f'"{comfy.NEG_NODE}": SpriteNegativeH3', src.replace("NODE_CLASS_MAPPINGS = {", ""))


if __name__ == "__main__":
    unittest.main()
