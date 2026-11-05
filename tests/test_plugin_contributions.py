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

from agent.boot.config import BootConfig, HostBootConfig  # noqa: E402
from agent.capabilities.contributions import (  # noqa: E402
    ContributionError,
    ContributionRegistry,
)
from agent.capabilities.plugins import PluginHost  # noqa: E402
from agent.capabilities.registry import ToolRegistry  # noqa: E402
from agent.core.plugin_meta import safe_dir_name  # noqa: E402
from agent.core.slot_assembly import plugin_env  # noqa: E402
from agent.mechanisms.context import ContextSources  # noqa: E402


def _write_meta(folder: Path) -> None:
    """给临时插件目录写身份文件：身份只由它声明，没有它就不是插件。"""
    (folder / "plugin-meta.json").write_text('{"version": "1.0"}\n', encoding="utf-8")


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

    def test_drop_plugin_removes_routes(self) -> None:
        self.reg.add_route("a", "GET", "x", lambda q: (200, {}))
        self.reg.add_route("b", "GET", "x", lambda q: (200, {}))
        self.assertEqual(self.reg.drop_plugin("a"), 1)
        self.assertEqual([r.plugin for r in self.reg.all_routes()], ["b"])

    def test_route_namespace_is_per_plugin(self) -> None:
        """端点路径自带插件命名空间，两个插件同名端点互不覆盖。"""
        self.reg.add_route("a", "GET", "x", lambda q: (200, {}))
        self.assertEqual([r.plugin for r in self.reg.all_routes()], ["a"])
        self.assertTrue(self.reg.all_routes()[0].full_path.startswith("/api/plugin/a/"))
        self.reg.add_route("b", "GET", "x", lambda q: (200, {"b": True}))
        self.assertEqual(self.reg.match("GET", "/api/plugin/b/x")[0].handler({}),
                         (200, {"b": True}))

class ContributionWiringTest(unittest.TestCase):
    """上下文注入源与插件数据目录的接线（直连底层，不经已移除的注册面）。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.sources = ContextSources()

    def test_add_context_source_returns_disposer(self) -> None:
        d = self.sources.add(
            lambda cid: ["注入"],
            path="app/backend/context/sources/a/demo", owner="a")
        self.assertEqual(len(self.sources._sources), 1)
        d()
        self.assertEqual(len(self.sources._sources), 0)

    # ── 插件专属数据目录 ──

    def _boot(self, data_root: Path) -> BootConfig:
        host = HostBootConfig(data_root=data_root,
                              plugins_root=self.base / "plugins",
                              plugin_data_root=data_root / "plugin")
        return BootConfig(data_root=data_root, host_config=host)

    def test_data_dir_is_per_plugin_and_created(self) -> None:
        plugins = self.base / "plugins"
        for name in ("a", "b"):
            (plugins / name).mkdir(parents=True)
            _write_meta(plugins / name)
        boot = self._boot(self.base / "data")
        a, _ = plugin_env(boot, "a")
        b, _ = plugin_env(boot, "b")
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        self.assertNotEqual(a, b)
        self.assertTrue(a.is_dir())
        self.assertEqual(a.name, "a")
        self.assertEqual(a.parent.name, "plugin")

    def test_data_dir_sanitizes_plugin_name(self) -> None:
        d = safe_dir_name("we/ird..name")
        self.assertTrue(d)
        self.assertNotIn("..", d)
        self.assertNotIn("/", d)

    def test_data_dir_none_without_host_root(self) -> None:
        from dataclasses import replace

        plugins = self.base / "plugins" / "a"
        plugins.mkdir(parents=True)
        _write_meta(plugins)
        boot = self._boot(self.base / "data")
        bare = BootConfig(
            data_root=boot.data_root,
            host_config=replace(boot.host_config, plugin_data_root=None))
        data_dir, _ = plugin_env(bare, "a")
        self.assertIsNone(data_dir, "未接入宿主时应返回 None 而不是报错")

    def test_data_dir_path_is_absolute(self) -> None:
        plugins = self.base / "plugins" / "a"
        plugins.mkdir(parents=True)
        _write_meta(plugins)
        data_dir, _ = plugin_env(self._boot(self.base / "data"), "a")
        self.assertTrue(data_dir.is_absolute())


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
        _write_meta(external)
        (external / "plugin.py").write_text(
            "def register(ctx):\n"
            "    ctx.add_route('GET', 'x', lambda q: (200, {}),"
            " slot_path='app/backend/http/routes/extplug-x')\n",
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
