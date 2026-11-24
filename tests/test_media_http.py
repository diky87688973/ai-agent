"""媒体公共路由：真实 HTTP、权限、范围、并发与插件代切换。"""
from __future__ import annotations

import concurrent.futures
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlencode

from agent.app import build_app
from agent.shell.web.server import create_server
from tests.testkit import local_auth


class MediaHTTPTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="media-http-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.files = self.root / "files"
        self.files.mkdir()
        self.manifest = self.root / "plugins.ini"
        self.manifest.write_text("[plugin:web_ui]\nenabled=1\n[plugin:media_viewer]\nenabled=1\n", encoding="utf-8")
        self.app = build_app(data_root=self.root / "data", plugins_path=self.manifest)
        self.addCleanup(self.app.dispose)
        self.auth = local_auth(self.app)
        self.server, self.shell = create_server(self.app, port=0, fs_root=[self.files],
                                                workspace_root=self.files, auth=self.auth)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop)
        self.file = self.files / "演示 空格.mp4"
        self.content = bytes(range(256)) * 4096
        self.file.write_bytes(self.content)

    def _stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(3)

    def request(self, path=None, method="GET", headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            target = path or "/api/media?" + urlencode({"path": str(self.file)})
            connection.request(method, target, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_info_head_and_full_content(self):
        status, headers, body = self.request("/api/media/info?" + urlencode({"path": str(self.file)}))
        data = json.loads(body)
        self.assertEqual((status, data["version"], data["kind"], data["name"]),
                         (200, 1, "video", self.file.name))
        self.assertEqual(data["size_bytes"], len(self.content))
        status, headers, body = self.request(method="HEAD", headers={"Range": "bytes=2-4"})
        self.assertEqual((status, len(body), int(headers["Content-Length"])), (200, 0, len(self.content)))
        self.assertEqual(headers["Content-Type"], "video/mp4")
        self.assertIn("filename*=UTF-8''", headers["Content-Disposition"])
        self.assertEqual(self.request()[2], self.content)

    def test_ranges_and_invalid_boundaries(self):
        for value, expected, section in [("bytes=10-19", self.content[10:20], "10-19"),
                                         ("bytes=1048570-", self.content[-6:], "1048570-1048575"),
                                         ("bytes=-8", self.content[-8:], "1048568-1048575")]:
            with self.subTest(value=value):
                status, headers, body = self.request(headers={"Range": value})
                self.assertEqual((status, body), (206, expected))
                self.assertEqual(headers["Content-Range"], f"bytes {section}/{len(self.content)}")
        for value in ["bytes=99999999-", "bytes=9-2", "bytes=-0", "bytes=bad", "bytes=-"]:
            with self.subTest(value=value):
                status, headers, _ = self.request(headers={"Range": value})
                self.assertEqual(status, 416)
                self.assertEqual(headers["Content-Range"], f"bytes */{len(self.content)}")
        self.assertEqual(self.request(headers={"Range": "bytes=0-1,5-8"})[0], 200)
        self.assertEqual(self.request(headers={"Range": "unknown=0-4"})[0], 200)

    def test_conditions_empty_files_and_safe_types(self):
        _, headers, _ = self.request(method="HEAD")
        self.assertEqual(self.request(headers={"If-Modified-Since": headers["Last-Modified"]})[0], 304)
        for condition in [headers["Last-Modified"], 'W/"fake"', '"fake"',
                          "Wed, 01 Jan 1997 00:00:00 GMT", "Wed, 01 Jan 2098 00:00:00 GMT"]:
            self.assertEqual(self.request(headers={"Range": "bytes=1-3", "If-Range": condition})[0], 200)
        self.file.write_bytes(b"")
        self.assertEqual(self.request()[0], 200)
        self.assertEqual(self.request(headers={"Range": "bytes=0-"})[0], 416)
        for name in ["script.svg", "script.html", "payload.exe"]:
            target = self.files / name
            target.write_text("<script>alert(1)</script>", encoding="utf-8")
            self.assertEqual(self.request("/api/media?" + urlencode({"path": str(target)}))[0], 415)
        status, headers, _ = self.request("/workspace/script.svg")
        self.assertEqual((status, headers["Content-Type"]), (200, "text/plain; charset=utf-8"))

    def test_permissions_missing_paths_and_authentication(self):
        outside = self.root / "outside.mp4"
        outside.write_bytes(b"private")
        for path, expected in [(str(outside), 403), (str(self.files / "missing.mp4"), 404),
                               (str(self.files), 403), ("file:///secret.mp4", 400), ("", 400)]:
            with self.subTest(path=path):
                self.assertEqual(self.request("/api/media?" + urlencode({"path": path}))[0], expected)
        self.auth.local_bypass = False
        self.auth.authenticator.local_bypass = False
        self.assertEqual(self.request()[0], 401)
        self.assertEqual(self.request(method="HEAD")[0], 401)

    def test_eight_independent_ranges_and_chat_health_remain_responsive(self):
        def read(index):
            return self.request(headers={"Range": f"bytes={index * 100}-{index * 100 + 99}"})
        with concurrent.futures.ThreadPoolExecutor(max_workers=9) as pool:
            jobs = [pool.submit(read, index) for index in range(8)]
            health = pool.submit(self.request, "/healthz")
            self.assertEqual(health.result()[0], 200)
            for index, job in enumerate(jobs):
                status, _, body = job.result()
                self.assertEqual((status, body), (206, self.content[index * 100:index * 100 + 100]))

    def test_workspace_media_and_method_permissions(self):
        target = self.files / "movie.mp4"
        target.write_bytes(b"movie")
        self.assertEqual(self.request("/workspace/movie.mp4")[2], b"movie")
        status, headers, body = self.request(method="OPTIONS")
        self.assertEqual(status, 405)
        self.assertEqual(set(headers["Allow"].split(", ")), {"GET", "HEAD"})

    def test_hot_unload_reload_and_leased_request_keep_consistent_routes(self):
        self.app.plugin_host.request_unload("web_ui")
        self.assertEqual(self.request(headers={"Range": "bytes=0-3"})[0], 206)
        self.app.reload_plugins(plugins_path=self.manifest)
        self.app.plugin_host.request_unload("media_viewer")
        self.assertEqual(self.request()[0], 503)
        self.app.reload_plugins(plugins_path=self.manifest)
        self.assertEqual(self.request(headers={"Range": "bytes=0-3"})[2], self.content[:4])
        with self.app.context.slot_lifecycle.turn():
            self.app.plugin_host.request_unload("media_viewer")
            self.assertEqual(self.app.context.slot_lifecycle.operations[-1]["status"], "queued")
            self.assertEqual(self.request(headers={"Range": "bytes=0-3"})[0], 206)
        self.assertEqual(self.request()[0], 503)


if __name__ == "__main__":
    unittest.main()
