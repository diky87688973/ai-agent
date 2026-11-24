"""公共挂载来自宿主授权和有效声明，坏贡献不能进入发布代。"""
from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from dataclasses import replace

from agent.capabilities.file_viewer_contract import validate_file_viewers
from agent.capabilities.http_mounts import PREFIX, build_http_mounts
from agent.core.slot_config import SlotConfig
from agent.core.slot_spec import HOST_OWNER, SlotSpec
from scripts.check_slots import factory_shapes


class HttpMountsTest(unittest.TestCase):
    def test_unrelated_plugin_streams_public_files_without_host_branch(self):
        from pathlib import Path

        from agent.app import build_app
        from agent.shell.web.server import create_server
        from tests.testkit import local_auth

        with tempfile.TemporaryDirectory(prefix="http-mount-probe-") as temp:
            root = Path(temp)
            plugin = root / "plugins" / "document_probe"
            plugin.mkdir(parents=True)
            (plugin / "plugin-meta.json").write_text('{"name":"文件响应验证","version":"1"}', encoding="utf-8")
            (plugin / "plugin.py").write_text(
                'from agent.common.http_contract import FileResponse\n'
                'def make(ctx):\n'
                '    return lambda request: FileResponse(request.files.open("sample.bin"), "application/octet-stream")\n',
                encoding="utf-8")
            (plugin / "plugin-slots.json").write_text(json.dumps({"version": 1, "root": "app", "provides": [
                {"path": PREFIX + "media-content/proof", "kind": "http-route", "method": "GET", "factory": "plugin:make"}
            ]}), encoding="utf-8")
            manifest = root / "plugins.ini"
            manifest.write_text('[plugin:document_probe]\nenabled=1\n', encoding="utf-8")
            (root / "sample.bin").write_bytes(b"generic-stream")
            app = build_app(data_root=root / "data", plugins_dir=root / "plugins", plugins_path=manifest)
            server, _ = create_server(app, port=0, fs_root=[root], auth=local_auth(app))
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
            thread.start()
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                connection.request("GET", "/api/media", headers={"Range": "bytes=0-6"})
                response = connection.getresponse()
                self.assertEqual((response.status, response.read()), (206, b"generic"))
            finally:
                connection.close()
                server.shutdown()
                server.server_close()
                thread.join(3)
                app.dispose()

    def test_file_viewer_versions_extensions_and_order_conflicts(self):
        path = "app/shell/web-ui/file-viewers/proof"
        spec = SlotSpec(path=path, kind="ui-control", props={"version": 1, "extensions": [".png"]})
        config = SlotConfig(root="app", version=1, specs={path: spec})
        validate_file_viewers(config)
        for props in [{"version": 2, "extensions": [".png"]}, {"version": 1, "extensions": ["png"]},
                      {"version": 1, "extensions": []}]:
            with self.subTest(props=props), self.assertRaises(ValueError):
                validate_file_viewers(replace(config, specs={path: replace(spec, props=props)}))
        other = replace(spec, path=path + "-other", order=0)
        with self.assertRaises(ValueError):
            validate_file_viewers(replace(config, specs={path: spec, other.path: other}))

    def config(self):
        parent = SlotSpec(path=PREFIX + "document", kind="container", children="keyed",
                          props={"path": "/api/document", "methods": ["GET", "HEAD"]})
        child = SlotSpec(path=parent.path + "/read", kind="http-route", method="GET", factory="plugin:make")
        config = SlotConfig(root="app", version=1, specs={parent.path: parent, child.path: child},
                            origins={parent.path: HOST_OWNER, child.path: "document_probe"})
        return config, parent, child

    def test_unrelated_provider_is_immutable_and_has_no_duplicate_url(self):
        config, _, child = self.config()
        callback = lambda request: request.path
        mounted = build_http_mounts(config, {child.path: callback})
        self.assertIs(mounted["/api/document"].handlers["GET"], callback)
        with self.assertRaises(TypeError):
            mounted["/api/document"].handlers["HEAD"] = callback
        self.assertEqual(factory_shapes(config), [])
        host = replace(config, origins={path: HOST_OWNER for path in config.specs})
        self.assertTrue(factory_shapes(host))

    def test_invalid_mounts_and_handlers_are_rejected(self):
        for change in ["origin", "url", "methods", "duplicate_url", "parent", "method",
                       "duplicate_method", "repeated_path", "non_callable"]:
            with self.subTest(change=change):
                config, parent, child = self.config()
                built = {child.path: lambda request: request.path}
                if change == "origin":
                    config.origins[parent.path] = "probe"
                elif change == "url":
                    config.specs[parent.path] = replace(parent, props={"path": "/login", "methods": ["GET"]})
                elif change == "methods":
                    config.specs[parent.path] = replace(parent, props={"path": "/api/document", "methods": []})
                elif change == "duplicate_url":
                    twin = replace(parent, path=parent.path + "-twin")
                    config.specs[twin.path] = twin
                    config.origins[twin.path] = HOST_OWNER
                elif change == "parent":
                    config.specs.pop(parent.path)
                elif change == "method":
                    config.specs[child.path] = replace(child, method="POST")
                elif change == "duplicate_method":
                    twin = replace(child, path=parent.path + "/other")
                    config.specs[twin.path] = twin
                    built[twin.path] = built[child.path]
                elif change == "repeated_path":
                    config.specs[child.path] = replace(child, props={"path": "/api/document"})
                elif change == "non_callable":
                    built[child.path] = None
                with self.assertRaises(ValueError):
                    build_http_mounts(config, built)


if __name__ == "__main__":
    unittest.main()
