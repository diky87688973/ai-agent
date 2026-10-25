# -*- coding: utf-8 -*-
"""插件贡献面测试。

覆盖：面板 / 动作 / 端点三类贡献的注册与撤销；端点路径形状（`:名字` 参数段、
段数必须相等、精确优先于参数）；命名空间校验（`..`、反斜杠、空白、重名、动词）；
面板脚本资产路径校验；插件专属数据目录的隔离与落盘。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.capabilities.contributions import (  # noqa: E402
    ASSET_SEGMENT,
    ContributionError,
    ContributionRegistry,
)
from agent.capabilities.plugins import PluginContext, PluginHost  # noqa: E402
from agent.capabilities.registry import ToolRegistry  # noqa: E402
from agent.mechanisms.context import ContextSources  # noqa: E402


def _host(tmp: Path, **kwargs: Any) -> PluginHost:
    return PluginHost(
        tmp / "plugins", ToolRegistry(),
        event_bus=None,
        context_sources=ContextSources(),
        contributions=kwargs.pop("contributions", ContributionRegistry()),
        plugin_data_root=kwargs.pop("plugin_data_root", tmp / "data" / "plugin"),
    )


class ContributionRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.reg = ContributionRegistry()

    # ── 面板 ──

    def test_panel_register_and_dispose(self) -> None:
        d = self.reg.add_panel("a", "p1", title="面板一", html="<b>hi</b>")
        panel = self.reg.panel("a", "p1")
        self.assertIsNotNone(panel)
        self.assertEqual(panel.title, "面板一")
        self.assertEqual([p.panel_id for p in self.reg.panels_of("a")], ["p1"])
        d()
        self.assertIsNone(self.reg.panel("a", "p1"))

    def test_panel_duplicate_rejected(self) -> None:
        self.reg.add_panel("a", "p1", title="x")
        with self.assertRaises(ContributionError):
            self.reg.add_panel("a", "p1", title="y")

    def test_panel_script_file_builds_asset_url(self) -> None:
        self.reg.add_panel("a", "p1", title="x", script_file="ui/panel.js")
        d = self.reg.panel("a", "p1").as_dict()
        self.assertEqual(
            d["script"], f"/api/plugin/a/{ASSET_SEGMENT}/ui/panel.js")

    def test_panel_explicit_script_wins(self) -> None:
        self.reg.add_panel("a", "p1", title="x", script="/custom/x.js",
                           script_file="ui/panel.js")
        self.assertEqual(self.reg.panel("a", "p1").as_dict()["script"], "/custom/x.js")

    def test_panel_script_file_rejects_escape(self) -> None:
        for bad in ("../x.js", "ui/../../x.js", "/abs/x.js", r"C:\x.js", ""):
            with self.subTest(bad=bad):
                if not bad:
                    # 空值表示"没有脚本"，合法
                    self.reg.add_panel("a", "ok", title="x", script_file="")
                    continue
                with self.assertRaises(ContributionError):
                    self.reg.add_panel("a", f"p-{abs(hash(bad))}", title="x",
                                       script_file=bad)

    # ── 动作 ──

    def test_action_register_and_dispose(self) -> None:
        d = self.reg.add_action("a", "go", label="去", title="提示")
        act = self.reg.actions_of("a")[0]
        self.assertEqual(act.action_id, "go")
        self.assertEqual(act.panel, "go", "未指定 panel 时默认同名面板")
        d()
        self.assertEqual(self.reg.actions_of("a"), [])

    def test_action_explicit_panel(self) -> None:
        self.reg.add_action("a", "go", label="去", panel="board")
        self.assertEqual(self.reg.actions_of("a")[0].panel, "board")

    # ── 端点 ──

    def test_route_exact_match(self) -> None:
        self.reg.add_route("a", "GET", "tasks", lambda q: (200, {}))
        hit = self.reg.match("GET", "/api/plugin/a/tasks")
        self.assertIsNotNone(hit)
        self.assertEqual(hit[1], {}, "无参数段的端点不该给出路径参数")
        self.assertIsNone(self.reg.match("POST", "/api/plugin/a/tasks"))
        self.assertIsNone(self.reg.match("GET", "/api/plugin/a/tasks/x"))
        self.assertIsNone(self.reg.match("GET", "/api/plugin/b/tasks"))

    def test_route_path_parameter(self) -> None:
        self.reg.add_route("a", "GET", "tasks/:sid", lambda q: (200, {}))
        hit = self.reg.match("GET", "/api/plugin/a/tasks/t-1")
        self.assertIsNotNone(hit)
        self.assertEqual(hit[1], {"sid": "t-1"})

    def test_route_multi_segment_parameter(self) -> None:
        self.reg.add_route("a", "GET", "runs/:run/steps/:step", lambda q: (200, {}))
        hit = self.reg.match("GET", "/api/plugin/a/runs/r1/steps/s2")
        self.assertIsNotNone(hit)
        self.assertEqual(hit[1], {"run": "r1", "step": "s2"})

    def test_route_segment_count_must_match(self) -> None:
        self.reg.add_route("a", "GET", "tasks/:sid", lambda q: (200, {}))
        self.assertIsNone(self.reg.match("GET", "/api/plugin/a/tasks"))
        self.assertIsNone(self.reg.match("GET", "/api/plugin/a/tasks/t-1/extra"))

    def test_route_exact_wins_over_parameter(self) -> None:
        """同时声明 `tasks` 与 `tasks/:sid` 时，`tasks` 不能被参数路由抢走。"""
        self.reg.add_route("a", "GET", "tasks/:sid", lambda q: (200, {"which": "param"}))
        self.reg.add_route("a", "GET", "tasks", lambda q: (200, {"which": "exact"}))
        hit = self.reg.match("GET", "/api/plugin/a/tasks")
        status, payload = hit[0].handler({})
        self.assertEqual(payload["which"], "exact")

    def test_route_methods_supported(self) -> None:
        for method in ("GET", "POST", "PUT", "DELETE"):
            self.reg.add_route("a", method, f"m-{method.lower()}", lambda q: (200, {}))
        for method in ("GET", "POST", "PUT", "DELETE"):
            self.assertIsNotNone(self.reg.match(method, f"/api/plugin/a/m-{method.lower()}"))

    def test_route_rejects_bad_paths(self) -> None:
        for bad in ("../evil", "a\\b", "a b", "/abs", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(ContributionError):
                    self.reg.add_route("a", "GET", bad, lambda q: (200, {}))

    def test_route_rejects_bad_parameter_name(self) -> None:
        for bad in ("tasks/:", "tasks/:1x", "tasks/:a-b"):
            with self.subTest(bad=bad):
                with self.assertRaises(ContributionError):
                    self.reg.add_route("a", "GET", bad, lambda q: (200, {}))

    def test_route_rejects_bad_plugin_and_method(self) -> None:
        with self.assertRaises(ContributionError):
            self.reg.add_route("..", "GET", "x", lambda q: (200, {}))
        with self.assertRaises(ContributionError):
            self.reg.add_route("a", "PATCH", "x", lambda q: (200, {}))
        with self.assertRaises(ContributionError):
            self.reg.add_route("a", "GET", "x", "not-callable")

    def test_route_duplicate_rejected(self) -> None:
        self.reg.add_route("a", "GET", "tasks", lambda q: (200, {}))
        with self.assertRaises(ContributionError):
            self.reg.add_route("a", "GET", "tasks", lambda q: (200, {}))
        # 不同动词不算重名
        self.reg.add_route("a", "POST", "tasks", lambda q: (200, {}))

    # ── 卸载兜底 ──

    def test_drop_plugin_removes_every_kind(self) -> None:
        self.reg.add_panel("a", "p", title="x")
        self.reg.add_action("a", "go", label="去")
        self.reg.add_route("a", "GET", "x", lambda q: (200, {}))
        self.reg.add_ctx_segment_style("a", label="A", color="blue")
        self.reg.add_boot_script("a", "ui/tool-view.js")
        self.reg.add_panel("b", "p", title="x")
        self.assertEqual(self.reg.drop_plugin("a"), 5)
        # b 的贡献不该被牵连
        self.assertEqual([p.plugin for p in self.reg.all_panels()], ["b"])
        self.assertEqual(self.reg.all_actions(), [])
        self.assertEqual(self.reg.all_routes(), [])
        self.assertEqual(self.reg.all_ctx_segment_styles(), [])
        self.assertEqual(self.reg.all_boot_scripts(), [])

    def test_ctx_segment_style_register_and_dispose(self) -> None:
        d = self.reg.add_ctx_segment_style("a", label="Skills", color="plum")
        styles = self.reg.all_ctx_segment_styles()
        self.assertEqual(len(styles), 1)
        self.assertEqual(styles[0].as_dict(), {
            "plugin": "a", "label": "Skills", "color": "plum"})
        d()
        self.assertEqual(self.reg.all_ctx_segment_styles(), [])

    def test_boot_script_register_and_dispose(self) -> None:
        d = self.reg.add_boot_script("a", "ui/tool-view.js")
        scripts = self.reg.all_boot_scripts()
        self.assertEqual(len(scripts), 1)
        self.assertEqual(scripts[0].as_dict(), {
            "plugin": "a",
            "rel_path": "ui/tool-view.js",
            "script": f"/api/plugin/a/{ASSET_SEGMENT}/ui/tool-view.js",
        })
        d()
        self.assertEqual(self.reg.all_boot_scripts(), [])

    def test_boot_script_rejects_escape(self) -> None:
        for bad in ("../x.js", "ui/../../x.js", "/abs/x.js", r"C:\x.js", ""):
            with self.subTest(bad=bad):
                with self.assertRaises(ContributionError):
                    self.reg.add_boot_script("a", bad)


class PluginContextContributionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.reg = ContributionRegistry()
        self.host = _host(self.base, contributions=self.reg)

    def _ctx(self, name: str = "a") -> PluginContext:
        return PluginContext(name, self.host._registry, None,
                             self.host._context_sources, None, self.host, self.reg)

    def test_ctx_namespaces_contributions_by_plugin(self) -> None:
        ctx = self._ctx("a")
        ctx.add_panel("p", title="面板")
        ctx.add_action("go", label="去")
        ctx.add_route("GET", "x", lambda q: (200, {}))
        ctx.add_ctx_segment_style(label="A", color="blue")
        ctx.add_boot_script("ui/tool-view.js")
        self.assertEqual([p.plugin for p in self.reg.all_panels()], ["a"])
        self.assertEqual([a.plugin for a in self.reg.all_actions()], ["a"])
        self.assertEqual([r.plugin for r in self.reg.all_routes()], ["a"])
        self.assertEqual([s.plugin for s in self.reg.all_ctx_segment_styles()], ["a"])
        self.assertEqual([s.plugin for s in self.reg.all_boot_scripts()], ["a"])
        self.assertTrue(self.reg.all_routes()[0].full_path.startswith("/api/plugin/a/"))
        # 贡献 disposer 记入 ctx，register 失败时可回滚
        self.assertEqual(len(ctx._disposers), 5)

    def test_register_fail_after_add_panel_rolls_back(self) -> None:
        """register 在 add_panel 之后抛错 → 面板不得留在贡献表。"""
        plugins = self.base / "plugins"
        plugins.mkdir(parents=True)
        (plugins / "boom").mkdir()
        (plugins / "boom" / "plugin.py").write_text(
            "def register(ctx):\n"
            "    ctx.add_panel('p', title='会回滚')\n"
            "    raise RuntimeError('boom')\n",
            encoding="utf-8",
        )
        reports = self.host.load_enabled(["boom"])
        self.assertEqual(reports[0].status, "error")
        self.assertIsNone(self.reg.panel("boom", "p"))
        self.assertEqual(self.reg.all_panels(), [])

    def test_ctx_add_context_source_returns_disposer(self) -> None:
        ctx = self._ctx("a")
        d = ctx.add_context_source(lambda cid: ["注入"])
        self.assertEqual(len(self.host._context_sources._sources), 1)
        d()
        self.assertEqual(len(self.host._context_sources._sources), 0)

    # ── 插件专属数据目录 ──

    def test_data_dir_is_per_plugin_and_created(self) -> None:
        a = self._ctx("a").data_dir
        b = self._ctx("b").data_dir
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        self.assertNotEqual(a, b)
        self.assertTrue(a.is_dir())
        self.assertEqual(a.name, "a")
        self.assertEqual(a.parent.name, "plugin")

    def test_data_dir_sanitizes_plugin_name(self) -> None:
        d = self._ctx("we/ird..name").data_dir
        self.assertIsNotNone(d)
        # 净化后不会越出 plugin/ 目录
        self.assertEqual(d.parent, (self.base / "data" / "plugin").resolve())
        self.assertNotIn("..", d.name)
        self.assertNotIn("/", d.name)

    def test_data_dir_none_without_host_root(self) -> None:
        ctx = PluginContext("a", self.host._registry, None, None, None, None, None)
        self.assertIsNone(ctx.data_dir, "未接入宿主时应返回 None 而不是报错")

    def test_data_dir_path_is_absolute(self) -> None:
        self.assertTrue(self._ctx("a").data_dir.is_absolute())


class PluginAssetUrlTest(unittest.TestCase):
    """面板脚本资产路径的解析（壳层按它取文件）。"""

    def test_asset_rel_parsing(self) -> None:
        from agent.shell.web.web_static import plugin_asset_rel

        self.assertEqual(
            plugin_asset_rel("/api/plugin/a/_asset/ui/panel.js"), ("a", "ui/panel.js"))
        self.assertIsNone(plugin_asset_rel("/api/plugin/a/tasks"))
        self.assertIsNone(plugin_asset_rel("/api/plugin/_asset/x.js"))
        self.assertIsNone(plugin_asset_rel("/api/plugin/a/_asset/"))
        self.assertIsNone(plugin_asset_rel("/api/plugin/a/_asset/../x.js"))
        self.assertIsNone(plugin_asset_rel("/other/a/_asset/x.js"))
        # 插件自己声明的端点若正好叫 _asset，只有 `GET` 走资产分支；解析函数本身不管动词
        self.assertEqual(plugin_asset_rel("/api/plugin/a/_asset/x.svg"), ("a", "x.svg"))


class ExternalPluginRootAssetTest(unittest.TestCase):
    """外部 path= 插件：资产根走 plugin_root，而不是 plugins_dir/<name>。"""

    def test_plugin_asset_uses_tracked_root(self) -> None:
        from agent.shell.web.server import WebShell
        from agent.shell.web.web_routes import Handler

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        plugins_dir = base / "plugins"
        plugins_dir.mkdir()
        external = base / "elsewhere" / "extplug"
        (external / "ui").mkdir(parents=True)
        (external / "plugin.py").write_text(
            "def register(ctx):\n"
            "    ctx.add_panel('p', title='外', script_file='ui/panel.js')\n",
            encoding="utf-8",
        )
        marker = "/* external-asset-ok */\n"
        (external / "ui" / "panel.js").write_text(marker, encoding="utf-8")

        host = PluginHost(plugins_dir, ToolRegistry(), contributions=ContributionRegistry())
        reports = host.load_manifest([{"name": "extplug", "path": str(external)}])
        self.assertEqual(reports[0].status, "loaded")
        self.assertEqual(host.plugin_root("extplug"), external.resolve())
        # 默认目录下没有同名插件 —— 若仍按 plugins_dir/<name> 解析会 404
        self.assertFalse((plugins_dir / "extplug").exists())

        app = SimpleNamespace(plugin_host=host)
        shell = WebShell(app)
        captured: Dict[str, Any] = {}

        handler = object.__new__(Handler)
        handler.shell = shell

        def _json(status: int, payload: Any) -> None:
            captured["json"] = (status, payload)

        def _bytes(status: int, body: bytes, content_type: str) -> None:
            captured["bytes"] = (status, body, content_type)

        handler._json = _json  # type: ignore[method-assign]
        handler._bytes = _bytes  # type: ignore[method-assign]
        handler._plugin_asset("extplug", "ui/panel.js")
        self.assertIn("bytes", captured, msg=f"应送出资产，实际={captured}")
        status, body, ctype = captured["bytes"]
        self.assertEqual(status, 200)
        self.assertIn("javascript", ctype)
        self.assertEqual(body.decode("utf-8").replace("\r\n", "\n"), marker)


if __name__ == "__main__":
    unittest.main()
