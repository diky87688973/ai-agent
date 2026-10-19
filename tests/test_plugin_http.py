# -*- coding: utf-8 -*-
"""插件 web 接口的 HTTP 层测试。

覆盖：GET / POST / PUT / DELETE 四个动词转发、`:名字` 路径参数按位置取值、
请求体与查询串送达、面板脚本资源送达（类型白名单 + 越界拒绝）、
命名空间隔离与未声明路径的 404。

用真服务（夹具目录 + 随机端口）而不是桩：这一层的价值恰在
"路由拼得对不对、动词接没接上、路径穿不穿得出去"。
"""
from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.app import build_app  # noqa: E402
from agent.shell import web as web_mod  # noqa: E402
from agent.shell.ui_bundle import read_ui_css, read_ui_js  # noqa: E402

_FIXTURE_PLUGIN = '''# -*- coding: utf-8 -*-
"""测试夹具插件：把一个有状态的业务暴露成 web 接口。"""
from __future__ import annotations

from typing import Any, Dict, List

_TASKS: Dict[str, Dict[str, Any]] = {}


def register(ctx: Any) -> List[Any]:
    disposers: List[Any] = []

    def create(query: Dict[str, Any]) -> Any:
        body = query.get("body") or {}
        tid = f"t-{len(_TASKS) + 1}"
        _TASKS[tid] = {"id": tid, "prompt": str(body.get("prompt") or ""), "hits": 0}
        return 201, {"ok": True, "id": tid, "tag": query.get("tag")}

    def listing(query: Dict[str, Any]) -> Any:
        return 200, {"ok": True, "items": list(_TASKS.values())}

    def one(query: Dict[str, Any]) -> Any:
        tid = str(query.get("sid") or "")
        if tid not in _TASKS:
            return 404, {"ok": False, "error": "no such task"}
        _TASKS[tid]["hits"] += 1
        return 200, {"ok": True, "task": _TASKS[tid]}

    def bump(query: Dict[str, Any]) -> Any:
        tid = str(query.get("sid") or "")
        if tid not in _TASKS:
            return 404, {"ok": False, "error": "no such task"}
        body = query.get("body") or {}
        _TASKS[tid]["prompt"] = str(body.get("prompt") or _TASKS[tid]["prompt"])
        return 200, {"ok": True, "task": _TASKS[tid]}

    def drop(query: Dict[str, Any]) -> Any:
        tid = str(query.get("sid") or "")
        if _TASKS.pop(tid, None) is None:
            return 404, {"ok": False, "error": "no such task"}
        return 200, {"ok": True, "removed": tid}

    disposers.append(ctx.add_panel("board", title="夹具面板",
                                   html="<div id='probeBody'></div>",
                                   script_file="ui/panel.js",
                                   css_file="ui/panel.css"))
    disposers.append(ctx.add_action("board", label="夹具按钮"))
    disposers.append(ctx.add_route("POST", "tasks", create))
    disposers.append(ctx.add_route("GET", "tasks", listing))
    disposers.append(ctx.add_route("GET", "tasks/:sid", one))
    disposers.append(ctx.add_route("PUT", "tasks/:sid", bump))
    disposers.append(ctx.add_route("DELETE", "tasks/:sid", drop))
    return disposers
'''

_PANEL_JS = (
    "window.__probeLoaded = true;\n"
    "const api = window.aiAgentPlugins.for(window.aiAgentPluginCurrent);\n"
    "window.__probeUrl = api.url('tasks');\n"
)

_PANEL_CSS = (
    "/* 夹具面板样式（属于插件，不该出现在壳层公共样式表里）*/\n"
    ".probe-row{padding:5px 10px}\n"
    ".probe-cb{width:16px;height:16px}\n"
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class PluginHttpTest(unittest.TestCase):
    """真服务 + 夹具插件；整类共用一个实例。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        base = Path(cls._tmp.name)
        plugins = base / "plugins"
        (plugins / "probe" / "ui").mkdir(parents=True)
        (plugins / "probe" / "plugin.py").write_text(_FIXTURE_PLUGIN, encoding="utf-8")
        (plugins / "probe" / "ui" / "panel.js").write_text(_PANEL_JS, encoding="utf-8")
        (plugins / "probe" / "ui" / "panel.css").write_text(_PANEL_CSS, encoding="utf-8")

        # 数据根走环境变量（`build_app` 不接受该参数）；装载清单走临时 `plugins.ini`
        # —— 真实工程那份列的是 knowledge / ai_speak，测试不该依赖它，也不该打补丁绕过。
        cls._env = mock.patch.dict(
            os.environ, {"AI_AGENT_DATA_ROOT": str(base / "data")})
        cls._env.start()
        cls.addClassCleanup(cls._env.stop)

        manifest = base / "plugins.ini"
        manifest.write_text("[plugin:probe]\n", encoding="utf-8")
        cls._manifest = mock.patch(
            "agent.config.DEFAULT_PLUGINS_PATH", manifest)
        cls._manifest.start()
        cls.addClassCleanup(cls._manifest.stop)
        cls.app = build_app(plugins_dir=plugins)
        cls.port = _free_port()
        cls.server, cls.shell = web_mod.create_server(
            cls.app, host="127.0.0.1", port=cls.port)
        cls._thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls._thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.server.shutdown()
            cls.server.server_close()
        except Exception:
            pass
        cls._thread.join(timeout=5)
        cls._tmp.cleanup()

    # ── 请求辅助 ──

    def req(self, method: str, path: str, payload: Any = None
            ) -> Tuple[int, Optional[Any], str, bytes]:
        url = f"http://127.0.0.1:{self.port}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=10) as resp:
                raw = resp.read()
                ctype = resp.headers.get("Content-Type", "")
                status = resp.status
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            ctype = exc.headers.get("Content-Type", "")
            status = exc.code
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            parsed = None
        return status, parsed, ctype, raw

    # ── 清单 ──

    def test_panels_and_actions_expose_script_url(self) -> None:
        status, data, _, _ = self.req("GET", "/api/panels")
        self.assertEqual(status, 200)
        board = next(p for p in data["panels"] if p["id"] == "board")
        self.assertEqual(board["plugin"], "probe")
        self.assertEqual(board["script"], "/api/plugin/probe/_asset/ui/panel.js")
        self.assertEqual(board["style"], "/api/plugin/probe/_asset/ui/panel.css")

        status, data, _, _ = self.req("GET", "/api/actions")
        self.assertEqual(status, 200)
        act = next(a for a in data["actions"] if a["id"] == "board")
        self.assertEqual(act["panel"], "board", "未指定面板的动作默认开同名面板")

    def test_panel_style_served_as_css(self) -> None:
        """插件的样式表由插件自己提供、按面板声明送达。"""
        status, _, ctype, raw = self.req("GET", "/api/plugin/probe/_asset/ui/panel.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", ctype)
        self.assertIn(b".probe-row", raw)

    def test_shell_public_stylesheet_does_not_carry_plugin_styles(self) -> None:
        """壳层的公共样式表里不该出现插件专属的样式规则。

        插件样式写进公共文件的话，插件没加载时页面也白带一份，而且插件的类名会和
        页面样式混在同一个文件里。
        只查样式表：主脚本模块里出现 `.kb-*` 是控制逻辑的选择器
        （面板渲染与事件绑定），那不是样式，也不该由插件提供。
        """
        text = read_ui_css()
        for sel in (".kb-cb", ".kb-file-row", ".kb-hint-bar", ".kb-body", ".kb-fpath"):
            with self.subTest(selector=sel):
                self.assertNotIn(sel, text)

    def test_plugin_style_source_declares_its_own_classes(self) -> None:
        """样式确实在插件里：插件目录下有自己的样式表。"""
        css = (_ROOT / "plugins/knowledge/ui/panel.css").read_text(encoding="utf-8")
        self.assertIn(".kb-file-row", css)
        self.assertIn(".kb-cb", css)

    def test_checked_files_reach_the_context(self) -> None:
        """经插件的勾选端点写进去的文件，必须真的变成注入上下文的系统消息。

        这是 knowledge 插件的核心语义：勾选状态与上下文注入必须看同一份状态。
        分成两处存放就会出现"界面显示已勾选、模型一个字都收不到"。
        """
        import tempfile

        with tempfile.TemporaryDirectory() as raw:
            kb_root = Path(raw) / "kb"
            (kb_root / "sub").mkdir(parents=True)
            (kb_root / "a.md").write_text("知识A：重启三步", encoding="utf-8")
            (kb_root / "sub" / "b.md").write_text("知识B：端口排查", encoding="utf-8")

            # 用真实插件运行时（不经 HTTP）：装一份指向该目录的知识库
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "kb_reach_probe", str(_ROOT / "plugins/knowledge/plugin.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            runtime = module.KBRuntime(kb_root, data_dir=Path(raw) / "data")

            accepted = runtime.set_checked(
                "c-reach", ["a.md", "sub/b.md", "../bad.txt", "missing.md"])
            # 越界路径与不存在的文件都不该被接受
            self.assertEqual(accepted, ["a.md", "sub/b.md"])

            msgs = runtime.build_system_messages("c-reach")
            self.assertEqual(len(msgs), 2, msg=f"两个勾选文件应各出一条：{msgs}")
            joined = "\n".join(msgs)
            self.assertIn("知识A：重启三步", joined)
            self.assertIn("知识B：端口排查", joined)
            self.assertTrue(all(m.startswith("【知识库：") for m in msgs), msg=str(msgs))

            # 取消勾选 → 不再注入
            self.assertEqual(runtime.set_checked("c-reach", []), [])
            self.assertEqual(runtime.build_system_messages("c-reach"), [])

    def test_plugin_panel_logic_lives_in_the_plugin(self) -> None:
        """面板的脚本与样式都在插件目录里，壳层不掺和插件面板的渲染。

        壳层只管按 `_asset` 路由送达；插件面板的取数与 DOM 都由插件脚本做 ——
        壳层认面板 id 就会变成"每加一个插件改一次壳层"。
        """
        ui = _ROOT / "plugins/knowledge/ui"
        self.assertTrue((ui / "panel.js").is_file())
        self.assertTrue((ui / "panel.css").is_file())
        plugin_js = (ui / "panel.js").read_text(encoding="utf-8")
        # 插件脚本经 API 客户端取数，不自己拼插件 URL 前缀
        self.assertIn("aiAgentPlugins", plugin_js)
        self.assertIn('api.get("files")', plugin_js)

        shell_js = read_ui_js()
        for token in ("kb-cb", "kb-file-row", "kb-fpath", "kb-hint-bar", "kbBody"):
            with self.subTest(token=token):
                self.assertNotIn(token, shell_js)

    def test_panel_script_served_as_javascript(self) -> None:
        status, _, ctype, raw = self.req("GET", "/api/plugin/probe/_asset/ui/panel.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", ctype)
        self.assertIn(b"__probeLoaded", raw)

    # ── 四个动词 ──

    def test_post_creates_and_receives_body_and_query(self) -> None:
        status, data, _, _ = self.req(
            "POST", "/api/plugin/probe/tasks?tag=x", {"prompt": "画一只猫"})
        self.assertEqual(status, 201)
        self.assertTrue(data["ok"])
        self.assertEqual(data["tag"], "x", "查询串要送达 handler")
        self.assertTrue(data["id"].startswith("t-"))

    def test_get_list_and_path_parameter(self) -> None:
        _, created, _, _ = self.req(
            "POST", "/api/plugin/probe/tasks", {"prompt": "列表用"})
        tid = created["id"]

        status, data, _, _ = self.req("GET", "/api/plugin/probe/tasks")
        self.assertEqual(status, 200)
        self.assertTrue(any(t["id"] == tid for t in data["items"]))

        status, data, _, _ = self.req("GET", f"/api/plugin/probe/tasks/{tid}")
        self.assertEqual(status, 200)
        self.assertEqual(data["task"]["id"], tid, "路径参数要按位置取到值")

    def test_put_updates_via_path_parameter(self) -> None:
        _, created, _, _ = self.req(
            "POST", "/api/plugin/probe/tasks", {"prompt": "改前"})
        tid = created["id"]
        status, data, _, _ = self.req(
            "PUT", f"/api/plugin/probe/tasks/{tid}", {"prompt": "改后"})
        self.assertEqual(status, 200)
        self.assertEqual(data["task"]["prompt"], "改后")

    def test_delete_removes(self) -> None:
        _, created, _, _ = self.req(
            "POST", "/api/plugin/probe/tasks", {"prompt": "待删"})
        tid = created["id"]
        status, data, _, _ = self.req("DELETE", f"/api/plugin/probe/tasks/{tid}")
        self.assertEqual(status, 200)
        self.assertEqual(data["removed"], tid)
        status, _, _, _ = self.req("GET", f"/api/plugin/probe/tasks/{tid}")
        self.assertEqual(status, 404, "删掉之后参数路由仍命中，但插件自己返回 404")

    # ── 资源送达 ──

    def test_asset_served_as_javascript(self) -> None:
        status, _, ctype, raw = self.req("GET", "/api/plugin/probe/_asset/ui/panel.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", ctype)
        self.assertIn(b"aiAgentPlugins", raw)

    def test_asset_rejects_non_whitelisted_type(self) -> None:
        status, _, _, _ = self.req("GET", "/api/plugin/probe/_asset/plugin.py")
        self.assertEqual(status, 415, "只送脚本类资产，不送任意文件")

    def test_asset_rejects_escape(self) -> None:
        for bad in ("/api/plugin/probe/_asset/../plugin.py",
                    "/api/plugin/probe/_asset/..%2Fplugin.py",
                    "/api/plugin/probe/_asset/nope.js"):
            with self.subTest(path=bad):
                status, _, _, _ = self.req("GET", bad)
                self.assertIn(status, (403, 404))

    # ── 隔离与拒绝 ──

    def test_unknown_path_and_plugin_are_404(self) -> None:
        for path in ("/api/plugin/probe/nope",
                     "/api/plugin/other/tasks",
                     "/api/plugin/probe/tasks/x/extra"):
            with self.subTest(path=path):
                status, _, _, _ = self.req("GET", path)
                self.assertEqual(status, 404)

    def test_404_lists_available_endpoints(self) -> None:
        status, data, _, _ = self.req("GET", "/api/plugin/probe/nope")
        self.assertEqual(status, 404)
        paths = {r["path"] for r in data["available"]}
        self.assertIn("/api/plugin/probe/tasks", paths)
        self.assertIn("/api/plugin/probe/tasks/:sid", paths)

    def test_parameter_route_does_not_capture_wrong_method(self) -> None:
        _, created, _, _ = self.req(
            "POST", "/api/plugin/probe/tasks", {"prompt": "动词隔离"})
        tid = created["id"]
        # 声明的是 GET/PUT/DELETE；POST 到带参路径不该命中
        status, _, _, _ = self.req("POST", f"/api/plugin/probe/tasks/{tid}")
        self.assertEqual(status, 404)

    def test_handler_exception_does_not_kill_shell(self) -> None:
        """插件端点抛错应变成 500，而不是打挂服务。"""
        calls: Dict[str, Any] = {}

        def boom(query: Dict[str, Any]) -> Any:
            raise RuntimeError("boom")

        reg = self.app.plugin_host.contributions
        d = reg.add_route("probe", "GET", "boom", boom)
        try:
            status, data, _, _ = self.req("GET", "/api/plugin/probe/boom")
            self.assertEqual(status, 500)
            self.assertIn("RuntimeError", str(data.get("error")))
            calls["ok"] = True
        finally:
            d()
        # 服务仍活着
        status, _, _, _ = self.req("GET", "/api/plugin/probe/tasks")
        self.assertEqual(status, 200)
        self.assertTrue(calls.get("ok"))


if __name__ == "__main__":
    unittest.main()
