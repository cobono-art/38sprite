"""웹 서버: 화면이 열리고, 다른 사이트에서 온 요청은 막고, 결과물 폴더는 시험용 임시 폴더를 쓴다."""
import asyncio
import importlib.util
import unittest

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from helpers import ROOT, TempDir

from spritegen import project as store


def load_server():
    spec = importlib.util.spec_from_file_location("app_server", ROOT / "app" / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ServerTest(unittest.TestCase):
    def test_pages_and_origin_check(self):
        server = load_server()

        async def run(projects):
            app = web.Application(middlewares=[server.same_origin, server.no_cache])
            app.add_routes(server.routes)
            app.router.add_static("/static", server.STATIC)
            client = TestClient(TestServer(app, host="127.0.0.1"))
            await client.start_server()
            host = f"127.0.0.1:{client.server.port}"
            server.ALLOWED_HOSTS.add(host)
            try:
                r = await client.get("/")
                self.assertEqual(r.status, 200)
                self.assertIn("38Sprite", await r.text())
                r = await client.get("/static/app.js")
                self.assertEqual(r.status, 200)
                r = await client.get("/api/projects", headers={"Origin": f"http://{host}"})
                self.assertEqual(r.status, 200)
                self.assertEqual(await r.json(), [])
                r = await client.post("/api/projects", headers={"Origin": "http://evil.example"})
                self.assertEqual(r.status, 403)                 # 다른 사이트에서 온 요청은 막는다
                r = await client.get("/api/motion_set", headers={"Origin": f"http://{host}"})
                self.assertEqual([x["key"] for x in await r.json()], ["idle", "walk", "run", "attack", "hit", "death"])
            finally:
                await client.close()

        with TempDir() as td:
            saved = store.PROJECTS
            store.PROJECTS = td / "projects"                    # 진짜 결과물 폴더는 건드리지 않는다
            try:
                asyncio.run(run(td))
            finally:
                store.PROJECTS = saved


if __name__ == "__main__":
    unittest.main()
