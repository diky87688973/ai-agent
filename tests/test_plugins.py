# -*- coding: utf-8 -*-
"""插件加载器测试。

覆盖：发现过滤 / 白名单 / 契约与返回值 / 失败隔离与回滚 / 卸载语义 /
模块命名隔离 / 装载报告 / 配置解析 / 装配接线与管道端到端。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.capabilities.plugins import PluginContext, PluginHost  # noqa: E402
from agent.capabilities.registry import ToolRegistry  # noqa: E402
from agent.config import get_plugins  # noqa: E402
from agent.core.tool_call import ToolCallRequest, ToolPipeline  # noqa: E402

_GOOD_PLUGIN = '''\
from agent.capabilities.registry import ToolPlugin

class Demo(ToolPlugin):
    name = "plugin_demo"
    description = "demo"
    parameters = {}

    def execute(self, arguments):
        return {"echo": "ok"}

def register(ctx):
    return ctx.register_tool(Demo())
'''

class PluginHostTest(unittest.TestCase):
    """加载器行为（临时目录造插件）。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name) / "plugins"
        self.dir.mkdir()
        self.registry = ToolRegistry()
        self.host = PluginHost(self.dir, self.registry)

    def _write_plugin(self, name: str, source: str) -> None:
        d = self.dir / name
        d.mkdir(exist_ok=True)
        (d / "plugin.py").write_text(source, encoding="utf-8")

    # ── 发现 ──

    def test_discover_filters(self) -> None:

        self._write_plugin("good", _GOOD_PLUGIN)
        (self.dir / "noentry").mkdir()
        (self.dir / "noentry" / "other.py").write_text("x = 1", encoding="utf-8")
        (self.dir / "__pycache__").mkdir()
        (self.dir / "_private").mkdir()
        (self.dir / "_private" / "plugin.py").write_text("x = 1", encoding="utf-8")
        (self.dir / "plain.txt").write_text("x", encoding="utf-8")
        self.assertEqual([i.name for i in self.host.discover()], ["good"])

    def test_discover_missing_dir(self) -> None:

        host = PluginHost(Path(self._tmp.name) / "no_such", self.registry)
        self.assertEqual(host.discover(), [])

    # ── 白名单 ──

    def test_load_enabled_filters_by_whitelist(self) -> None:

        self._write_plugin("a", _GOOD_PLUGIN.replace("plugin_demo", "tool_a"))
        self._write_plugin("b", _GOOD_PLUGIN.replace("plugin_demo", "tool_b"))
        reports = self.host.load_enabled(["a"])
        self.assertEqual([r.status for r in reports], ["loaded"])
        self.assertEqual(self.host.loaded_names(), ["a"])
        self.assertIsNotNone(self.registry.get("tool_a"))
        self.assertIsNone(self.registry.get("tool_b"))

    def test_unknown_name_reports_error(self) -> None:

        reports = self.host.load_enabled(["ghost"])
        self.assertEqual(reports[0].status, "error")

    def test_reload_skips_loaded(self) -> None:

        self._write_plugin("a", _GOOD_PLUGIN.replace("plugin_demo", "tool_a"))
        self.host.load_enabled(["a"])
        self.assertEqual(self.host.load_enabled(["a"]), [])

    # ── 契约与装载 ──

    def test_register_via_ctx_returns_none(self) -> None:

        src = _GOOD_PLUGIN.replace(
            "    return ctx.register_tool(Demo())",
            "    ctx.register_tool(Demo())\n    return None",
        )
        self._write_plugin("v", src)
        self.assertEqual(self.host.load_enabled(["v"])[0].status, "loaded")
        self.assertIsNotNone(self.registry.get("plugin_demo"))
        self.host.unload("v")
        self.assertIsNone(self.registry.get("plugin_demo"))
        self.assertEqual(self.host.loaded_names(), [])

    def test_returned_disposer_list_reverse_order(self) -> None:

        src = (
            "def register(ctx):\n"
            "    import pathlib\n"
            "    base = pathlib.Path(__file__).parent\n"
            "    def make(tag):\n"
            "        def d():\n"
            "            with (base / 'order.txt').open('a', encoding='utf-8') as fh:\n"
            "                fh.write(tag)\n"
            "        return d\n"
            "    return [make('d1'), make('d2')]\n"
        )
        self._write_plugin("orders", src)
        self.host.load_enabled(["orders"])
        self.host.unload("orders")
        self.assertEqual((self.dir / "orders" / "order.txt").read_text(encoding="utf-8"), "d2d1")

    def test_register_raises_rolls_back(self) -> None:

        src = (
            "from agent.capabilities.registry import ToolPlugin\n"
            "\n"
            "class T(ToolPlugin):\n"
            "    name = 'will_rollback'\n"
            "    description = ''\n"
            "    parameters = {}\n"
            "    def execute(self, arguments):\n"
            "        return None\n"
            "\n"
            "def register(ctx):\n"
            "    ctx.register_tool(T())\n"
            "    raise RuntimeError('boom')\n"
        )
        self._write_plugin("boom", src)
        reports = self.host.load_enabled(["boom"])
        self.assertEqual(reports[0].status, "error")
        self.assertIn("boom", reports[0].message)
        self.assertIsNone(self.registry.get("will_rollback"))
        self.assertEqual(self.host.loaded_names(), [])

    def test_broken_import_isolated(self) -> None:

        self._write_plugin("bad", "def register(ctx:\n")
        self._write_plugin("good", _GOOD_PLUGIN)
        by_name = {r.name: r for r in self.host.load_enabled(["bad", "good"])}
        self.assertEqual(by_name["bad"].status, "error")
        self.assertIn("SyntaxError", by_name["bad"].message)
        self.assertEqual(by_name["good"].status, "loaded")
        self.assertIsNotNone(self.registry.get("plugin_demo"))

    def test_missing_register_reports_error(self) -> None:

        self._write_plugin("noreg", "x = 1\n")
        r = self.host.load_enabled(["noreg"])[0]
        self.assertEqual(r.status, "error")
        self.assertIn("register", r.message)

    def test_module_namespace_and_unload(self) -> None:

        self._write_plugin("ns", _GOOD_PLUGIN.replace("plugin_demo", "tool_ns"))
        self.host.load_enabled(["ns"])
        self.assertIn("fan_agent_plugins.ns", sys.modules)
        self.host.unload("ns")
        self.assertNotIn("fan_agent_plugins.ns", sys.modules)

    def test_unload_all_idempotent(self) -> None:

        self._write_plugin("a", _GOOD_PLUGIN.replace("plugin_demo", "tool_a"))
        self._write_plugin("b", _GOOD_PLUGIN.replace("plugin_demo", "tool_b"))
        self.host.load_enabled(["a", "b"])
        self.host.unload_all()
        self.assertEqual(self.host.loaded_names(), [])
        self.host.unload("a")
        self.host.unload_all()

    def test_reports_accumulate(self) -> None:

        self._write_plugin("a", _GOOD_PLUGIN.replace("plugin_demo", "tool_a"))
        self.host.load_enabled(["a"])
        self.host.load_enabled(["missing"])
        pairs = [(r.name, r.status) for r in self.host.reports()]
        self.assertIn(("a", "loaded"), pairs)
        self.assertIn(("missing", "error"), pairs)

    def test_plugin_tool_runs_via_pipeline(self) -> None:

        self._write_plugin("pipe", _GOOD_PLUGIN)
        self.host.load_enabled(["pipe"])
        pipeline = ToolPipeline()
        call = ToolCallRequest(call_id="c1", name="plugin_demo", arguments={})
        result = pipeline.execute(self.registry, call, SimpleNamespace(conversation_id="c"))
        self.assertTrue(result.ok)
        self.assertEqual(result.data, {"echo": "ok"})

_GATE_ONLY_PLUGIN = '''
from agent.core.tool_call import GateDecision

def register(ctx):
    def deny_all(call, _ctx):
        return GateDecision(allow=False, reason="plugin gate")

    return ctx.add_pre_gate(deny_all)
'''

_GATE_BOOM_PLUGIN = '''
from agent.core.tool_call import GateDecision

def register(ctx):
    def deny_all(call, _ctx):
        return GateDecision(allow=False, reason="plugin gate")

    ctx.add_pre_gate(deny_all)
    raise RuntimeError("boom")
'''

class PluginGateTest(unittest.TestCase):
    """插件门控接缝：注册期可加检查扩展点（pre-gate）。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name) / "plugins"
        self.dir.mkdir()
        self.registry = ToolRegistry()
        self.pipeline = ToolPipeline()

    def _write_plugin(self, name: str, source: str) -> None:
        d = self.dir / name
        d.mkdir(exist_ok=True)
        (d / "plugin.py").write_text(source, encoding="utf-8")

    def test_pre_gate_blocks_then_unload_releases(self) -> None:

        self._write_plugin("tool", _GOOD_PLUGIN.replace("plugin_demo", "gate_target"))
        self._write_plugin("gate", _GATE_ONLY_PLUGIN)
        host = PluginHost(self.dir, self.registry, pipeline=self.pipeline)
        host.load_enabled(["tool", "gate"])
        call = ToolCallRequest(call_id="c1", name="gate_target", arguments={})
        ctx = SimpleNamespace(conversation_id="c")
        blocked = self.pipeline.execute(self.registry, call, ctx)
        self.assertFalse(blocked.ok)
        self.assertIn("plugin gate", blocked.error)
        host.unload("gate")
        self.assertTrue(self.pipeline.execute(self.registry, call, ctx).ok)

    def test_missing_pipeline_guards_and_post_observer(self) -> None:

        bare = PluginContext("x", self.registry)
        with self.assertRaises(RuntimeError):
            bare.add_pre_gate(lambda call, _c: None)
        with self.assertRaises(RuntimeError):
            bare.add_post_observer(lambda call, result, _c: None)
        seen = []
        hooked = PluginContext("y", self.registry, pipeline=self.pipeline)
        hooked.add_post_observer(lambda call, result, _c: seen.append((call.name, result.ok)))
        self._write_plugin("tool", _GOOD_PLUGIN.replace("plugin_demo", "obs_target"))
        host = PluginHost(self.dir, self.registry)
        host.load_enabled(["tool"])
        call = ToolCallRequest(call_id="c2", name="obs_target", arguments={})
        self.assertTrue(self.pipeline.execute(self.registry, call, SimpleNamespace(conversation_id="c")).ok)
        self.assertEqual(seen, [("obs_target", True)])

    def test_gate_rollback_on_register_error(self) -> None:

        self._write_plugin("tool", _GOOD_PLUGIN.replace("plugin_demo", "rb_target"))
        self._write_plugin("boom", _GATE_BOOM_PLUGIN)
        host = PluginHost(self.dir, self.registry, pipeline=self.pipeline)
        reports = {r.name: r.status for r in host.load_enabled(["tool", "boom"])}
        self.assertEqual(reports["boom"], "error")
        call = ToolCallRequest(call_id="c3", name="rb_target", arguments={})
        self.assertTrue(self.pipeline.execute(self.registry, call, SimpleNamespace(conversation_id="c")).ok)

class ConfigParseTest(unittest.TestCase):
    def test_get_plugins_parse(self) -> None:
        """清单解析只做解析：`[plugin:<名字>]` 节，节里没有字段也合法。

        名字合法性与目录存在性归装载方判（见 `PluginHost.load_manifest`），
        这里只管把清单读成结构。
        """

        with tempfile.TemporaryDirectory() as tmp:
            ini = Path(tmp) / "plugins.ini"
            ini.write_text(
                "[plugin:a]\nversion = 1.0\n\n[plugin:b]\n\n[plugin:c]\npath = D:/lab/c\n",
                encoding="utf-8")
            got = get_plugins(ini)
            self.assertEqual([e["name"] for e in got], ["a", "b", "c"])
            self.assertEqual(got[0]["version"], "1.0")
            self.assertEqual(got[1]["version"], "")
            # path 留空时本函数不填 —— 解析留给装载方按自己的插件根做
            self.assertEqual(got[0]["path"], "")
            self.assertEqual(got[2]["path"], "D:/lab/c")

            # 节名前缀不对、上层裸键都忽略
            ini.write_text("[other]\nx = 1\nenabled = a, b\n", encoding="utf-8")
            self.assertEqual(get_plugins(ini), [])

            # 空清单 = 不装任何插件
            ini.write_text("; 什么都不列\n", encoding="utf-8")
            self.assertEqual(get_plugins(ini), [])

    def test_load_manifest_resolves_paths_and_reports_errors(self) -> None:
        """装载方把 `path` 落到自己的插件根，并把配置错误变成报告。"""

        from agent.capabilities.contributions import ContributionRegistry
        from agent.capabilities.plugins import PluginHost
        from agent.mechanisms.context_pipeline import ContextSources

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugins"
            (root / "good").mkdir(parents=True)
            (root / "good" / "plugin.py").write_text(
                "def register(ctx):\n    return []\n", encoding="utf-8")
            host = PluginHost(root, ToolRegistry(), event_bus=None,
                              context_sources=ContextSources(),
                              contributions=ContributionRegistry(),
                              plugin_data_root=Path(tmp) / "data")
            reports = {r.name: r for r in host.load_manifest([
                {"name": "good", "version": "", "path": ""},
                {"name": "missing", "version": "", "path": ""},
                {"name": "../evil", "version": "", "path": ""},
            ])}
            self.assertEqual(host.loaded_names(), ["good"])
            self.assertEqual(reports["missing"].status, "error")
            self.assertEqual(reports["../evil"].status, "error")
            self.assertIn("非法", reports["../evil"].message)

class AppWiringTest(unittest.TestCase):
    def test_build_app_loads_whitelisted_plugin(self) -> None:

        from agent.app import build_app

        with tempfile.TemporaryDirectory() as tmp:
            pdir = Path(tmp) / "plugins"
            (pdir / "wired").mkdir(parents=True)
            (pdir / "wired" / "plugin.py").write_text(
                _GOOD_PLUGIN.replace("plugin_demo", "tool_wired"), encoding="utf-8"
            )
            with mock.patch("agent.app.get_plugins", return_value=["wired"]):
                app = build_app(plugins_dir=pdir)
            self.assertEqual(app.plugin_host.loaded_names(), ["wired"])
            self.assertIsNotNone(app.registry.get("tool_wired"))

    def test_build_app_empty_whitelist_noop(self) -> None:

        from agent.app import build_app

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("agent.app.get_plugins", return_value=[]):
                app = build_app(plugins_dir=Path(tmp) / "missing")
            self.assertEqual(app.plugin_host.loaded_names(), [])

if __name__ == "__main__":
    unittest.main()
