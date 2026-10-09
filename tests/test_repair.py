"""편집 AI로 고친 프레임: 바뀐 곳만 끼우기, 시트 조립 때 그 프레임 대신 쓰기."""
import json
import unittest

import numpy as np
from PIL import Image

from helpers import TempDir, attack_frame, write_frames

from spritegen.assemble import assemble
from spritegen import repair
from spritegen.repair import merge_edit, splice


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

    def test_merge_edit_keeps_original_background(self):
        """공식 편집 AI가 배경을 짙은 분홍으로 칠해도, 합친 그림의 배경·지운 궤적 자리는 원래 영상의 마젠타."""
        orig = np.full((60, 60, 3), (255, 0, 255), np.uint8)
        orig[10:50, 20:40] = (200, 120, 60)
        orig[5:15, 45:58] = (120, 240, 255)                 # 빛 궤적
        edit = np.full((60, 60, 3), (215, 40, 134), np.uint8)   # 짙은 분홍 배경
        edit[10:50, 20:40] = (200, 120, 60)
        out = merge_edit(orig, edit)
        self.assertTrue((out[2, 2] == (255, 0, 255)).all())
        self.assertTrue((out[8, 50] == (255, 0, 255)).all())     # 궤적 자리
        self.assertTrue((out[30, 30] == (200, 120, 60)).all())

    def test_backend_picks_official_qwen_edit(self):
        """전용 노드가 없고 공식 노드 + qwen_image_edit 모델이 있으면 공식 방식(최신판, Lightning 4단계)."""
        lists = {"UNETLoader": ("unet_name", ["qwen_image_edit_fp8_e4m3fn.safetensors", "qwen_image_edit_2509_fp8_e4m3fn.safetensors",
                                              "other.safetensors"]),
                 "CLIPLoader": ("clip_name", ["qwen_2.5_vl_7b_fp8_scaled.safetensors"]),
                 "VAELoader": ("vae_name", ["qwen_image_vae.safetensors"]),
                 "LoraLoaderModelOnly": ("lora_name", ["Qwen-Image-Edit-Lightning-4steps-V1.0.safetensors"])}

        def fake(url, payload=None, timeout=60):
            node = url.rsplit("/", 1)[1]
            if node in lists:
                field, names = lists[node]
                return {node: {"input": {"required": {field: [names]}}}}
            return {node: {}} if node == repair.EDIT_NODE else {}
        saved = repair.comfy.http_json
        repair.comfy.http_json = fake
        try:
            self.assertEqual(repair.backend("http://x"), "qwen_edit")
            m = repair.edit_models("http://x", {})
            self.assertEqual(m["unet"], "qwen_image_edit_2509_fp8_e4m3fn.safetensors")
            wf = repair.workflow_edit("a.png", "p", 1, "x", m)
            self.assertEqual((wf["q_sample"]["inputs"]["steps"], wf["q_sample"]["inputs"]["cfg"]), (4, 1.0))
            self.assertEqual(wf["q_shift"]["inputs"]["model"], ["q_lora", 0])
            for node in wf.values():                        # 모든 연결이 있는 노드를 가리킨다
                for v in node["inputs"].values():
                    if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and v[0].startswith("q_"):
                        self.assertIn(v[0], wf)
            lists["LoraLoaderModelOnly"] = ("lora_name", [])
            wf = repair.workflow_edit("a.png", "p", 1, "x", repair.edit_models("http://x", {}))
            self.assertEqual((wf["q_sample"]["inputs"]["steps"], wf["q_sample"]["inputs"]["cfg"]), (20, 2.5))
            lists["VAELoader"] = ("vae_name", [])
            self.assertIsNone(repair.backend("http://x"))
        finally:
            repair.comfy.http_json = saved

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
