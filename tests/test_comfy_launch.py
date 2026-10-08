"""영상 AI ComfyUI 켜기·다시 켜기: 실행 옵션 다루기 (실제로 켜지는 않는다)."""
import tempfile
import unittest
from pathlib import Path

from spritegen import comfy_launch as cl


class ComfyLaunchTest(unittest.TestCase):
    def test_local_port(self):
        self.assertEqual(cl.local_port("http://127.0.0.1:8189"), 8189)
        self.assertEqual(cl.local_port("http://localhost:8188/"), 8188)
        self.assertIsNone(cl.local_port("http://192.168.0.5:8188"))
        self.assertIsNone(cl.local_port(""))

    def test_with_node_only_when_custom_nodes_disabled(self):
        base = ["--port", "8189", "--disable-auto-launch"]
        self.assertEqual(cl.with_node(base), base)                       # 추가 노드를 켜 둔 ComfyUI는 그대로
        off = base + ["--disable-all-custom-nodes"]
        self.assertEqual(cl.with_node(off), off + ["--whitelist-custom-nodes", cl.NODE_DIR])
        self.assertEqual(cl.with_node(cl.with_node(off)), cl.with_node(off))   # 두 번 붙이지 않는다
        other = off + ["--whitelist-custom-nodes", "ComfyUI-GGUF", "--vram-headroom", "2"]
        self.assertEqual(cl.with_node(other), off + ["--whitelist-custom-nodes", "ComfyUI-GGUF", cl.NODE_DIR,
                                                     "--vram-headroom", "2"])

    def test_script_args(self):
        argv = [r"E:\ComfyUI\python_embeded\python.exe", "-u", "main.py", "--listen", "127.0.0.1", "--port", "8189"]
        self.assertEqual(cl.script_args(argv), ["--listen", "127.0.0.1", "--port", "8189"])
        self.assertEqual(cl.script_args(["python.exe", "-s", r"ComfyUI\main.py", "--windows-standalone-build"]),
                         ["--windows-standalone-build"])
        self.assertIsNone(cl.script_args(["python.exe", "server.py"]))

    def test_split_cmdline_keeps_quoted_paths(self):
        args = cl.split_cmdline('"C:\Program Files\py thon.exe" -u main.py --port 8189')
        self.assertEqual(args, ["C:\Program Files\py thon.exe", "-u", "main.py", "--port", "8189"])

    def test_comfy_root_and_node(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            py = td / "python_embeded" / "python.exe"
            py.parent.mkdir()
            (td / "ComfyUI" / "custom_nodes").mkdir(parents=True)
            (td / "ComfyUI" / "main.py").write_text("")
            root = cl.comfy_root(py)
            self.assertEqual(root, (td / "ComfyUI").resolve())
            self.assertFalse(cl.node_installed(root))
            (root / "custom_nodes" / cl.NODE_DIR).mkdir()
            (root / "custom_nodes" / cl.NODE_DIR / "__init__.py").write_text("")
            self.assertTrue(cl.node_installed(root))
            self.assertIsNone(cl.comfy_root(td / "nowhere" / "x" / "python.exe"))

    def test_autostart_needs_local_comfy(self):
        self.assertFalse(cl.autostart({}, "http://192.168.0.5:8188"))           # 다른 PC면 켜지 않는다
        self.assertFalse(cl.autostart({"comfy_autostart": False}, "http://127.0.0.1:8188"))


if __name__ == "__main__":
    unittest.main()
