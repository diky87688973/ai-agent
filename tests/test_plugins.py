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

from agent.capabilities.plugins import (  # noqa: E402
    PluginHost,
    plugin_config_fields,
)
from agent.capabilities.registry import ToolPlugin, ToolRegistry  # noqa: E402
from agent.config import get_plugins  # noqa: E402
from agent.core.tool_call import ToolCallRequest, ToolPipeline  # noqa: E402
from agent.shell.settings_panel import list_plugins  # noqa: E402

#: 插件身份文件的内容。夹具一律写一份：身份只由它声明，没有它就不是插件。
_META = '{"version": "1.0"}\n'


def _write_meta(folder: Path) -> None:
    """给临时插件目录写身份文件（插件存在判据）。"""
    (folder / "plugin-meta.json").write_text(_META, encoding="utf-8")


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
        _write_meta(d)
        (d / "plugin.py").write_text(source, encoding="utf-8")

    # ── 发现 ──

    def test_discover_filters(self) -> None:

        self._write_plugin("good", _GOOD_PLUGIN)
        (self.dir / "noentry").mkdir()
        (self.dir / "noentry" / "other.py").write_text("x = 1", encoding="utf-8")
        (self.dir / "__pycache__").mkdir()
        (self.dir / "_private").mkdir()
        _write_meta(self.dir / "_private")
        (self.dir / "_private" / "plugin.py").write_text("x = 1", encoding="utf-8")
        (self.dir / "plain.txt").write_text("x", encoding="utf-8")
        self.assertEqual([i.name for i in self.host.discover()], ["good"])

    def test_discover_missing_dir(self) -> None:

        host = PluginHost(Path(self._tmp.name) / "no_such", self.registry)
        self.assertEqual(host.discover(), [])

    # ── 白名单 ──

    def test_load_enabled_filters_by_whitelist(self) -> None:
        """白名单只决定哪些插件模块被装载；插件资产不归装载器交付。

        旧前提：装完读 registry 验证工具已登记（当时由 register 交付）。
        新前提：装载器只负责模块就绪，故断言改为「报告 + 模块已加载」；
                资产交付由 `test_plugin_asset_delivery` 走真实启动验证。
        """
        self._write_plugin("a", _GOOD_PLUGIN.replace("plugin_demo", "tool_a"))
        self._write_plugin("b", _GOOD_PLUGIN.replace("plugin_demo", "tool_b"))
        reports = self.host.load_enabled(["a"])
        self.assertEqual([r.status for r in reports], ["loaded"])
        self.assertEqual(self.host.loaded_names(), ["a"])
        self.assertIn("fan_agent_plugins.a", sys.modules)
        self.assertNotIn("fan_agent_plugins.b", sys.modules)

    def test_unknown_name_reports_error(self) -> None:

        reports = self.host.load_enabled(["ghost"])
        self.assertEqual(reports[0].status, "error")

    def test_reload_skips_loaded(self) -> None:

        self._write_plugin("a", _GOOD_PLUGIN.replace("plugin_demo", "tool_a"))
        self.host.load_enabled(["a"])
        self.assertEqual(self.host.load_enabled(["a"]), [])

    # ── 装载契约 ──

    def test_missing_register_still_loads(self) -> None:
        """装载器只把模块准备好，不要求 plugin.py 定义 `register`。

        插件身份看 `plugin-meta.json`，`plugin.py` 只是可选入口：缺了 `register`
        仍属正常装载。
        """
        self._write_plugin("noreg", "x = 1\n")
        report = self.host.load_enabled(["noreg"])[0]
        self.assertEqual(report.status, "loaded", report.message)
        self.assertIn("fan_agent_plugins.noreg", sys.modules)
        self.assertEqual(self.host.loaded_names(), ["noreg"])

    def test_register_is_not_executed(self) -> None:
        """`register` 不再被装载器执行：它抛错也不影响装载。

        插件身份看 `plugin-meta.json`，装载只看模块能否导入；`register` 没有调用点。
        """
        src = (
            "def register(ctx):\n"
            "    raise RuntimeError('boom')\n"
        )
        self._write_plugin("boom", src)
        report = self.host.load_enabled(["boom"])[0]
        self.assertEqual(report.status, "loaded", report.message)
        self.assertIn("fan_agent_plugins.boom", sys.modules)

    def test_broken_import_isolated(self) -> None:
        """单个插件导入失败不连坐其余插件：报错归它自己，其他照常装载。"""
        self._write_plugin("bad_syntax", "def register(ctx:\n")
        self._write_plugin("good", _GOOD_PLUGIN)
        by_name = {r.name: r for r in self.host.load_enabled(["bad_syntax", "good"])}
        self.assertEqual(by_name["bad_syntax"].status, "error")
        self.assertIn("SyntaxError", by_name["bad_syntax"].message)
        self.assertEqual(by_name["good"].status, "loaded")
        self.assertIn("fan_agent_plugins.good", sys.modules)
        self.assertEqual(self.host.loaded_names(), ["good"])

    def test_module_namespace_and_unload(self) -> None:

        self._write_plugin("ns", _GOOD_PLUGIN.replace("plugin_demo", "tool_ns"))
        self.host.load_enabled(["ns"])
        self.assertIn("fan_agent_plugins.ns", sys.modules)
        self.host.unload("ns")
        self.assertNotIn("fan_agent_plugins.ns", sys.modules)

    def test_relative_submodule_import(self) -> None:

        root = self.dir / "pkg"
        root.mkdir()
        _write_meta(root)
        (root / "helper.py").write_text("VALUE = 'ok'\n", encoding="utf-8")
        (root / "plugin.py").write_text(
            "from .helper import VALUE\n"
            "\n"
            "def register(ctx):\n"
            "    return None\n",
            encoding="utf-8",
        )
        report = self.host.load_enabled(["pkg"])[0]
        self.assertEqual(report.status, "loaded", report.message)
        self.assertEqual(sys.modules["fan_agent_plugins.pkg.helper"].VALUE, "ok")
        self.host.unload("pkg")
        self.assertNotIn("fan_agent_plugins.pkg.helper", sys.modules)

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
        """插件声明的工具装进注册表后能被管线执行。

        旧前提：装载插件即交付工具，可直接跑管线。
        新前提：工具由绑定器登记，故此处直接向注册表注册同一形状的工具对象，
                验证「注册表 → 管线」这一段；「插件→注册表」由真实启动用例守。
        """
        self.host.load_enabled(["pipe"])

        class _Demo(ToolPlugin):
            name = "plugin_demo"
            description = "demo"
            parameters: dict = {}

            def execute(self, arguments):
                return {"echo": "ok"}

        self.registry.register(_Demo())
        pipeline = ToolPipeline()
        call = ToolCallRequest(call_id="c1", name="plugin_demo", arguments={})
        result = pipeline.execute(self.registry, call, SimpleNamespace(conversation_id="c"))
        self.assertTrue(result.ok)
        self.assertEqual(result.data, {"echo": "ok"})

class PluginIdentityFallbackTest(unittest.TestCase):
    """插件身份只来自 `plugin-meta.json`：列表里所有插件走同一条规则。"""

    @staticmethod
    def _plugin(root: Path, name: str) -> Path:
        folder = root / name
        folder.mkdir(parents=True)
        (folder / "plugin.py").write_text("PLUGIN_VERSION = '1.0'\n", encoding="utf-8")
        return folder

    def test_meta_supplies_identity_when_config_is_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = self._plugin(Path(tmp), "multi_model")
            (folder / "plugin-meta.json").write_text(
                '{"name":"多模型","desc":"每条模型自带网关与厂商","icon":"🧩",'
                '"version":"1.0","settings_tab":"模型"}\n', encoding="utf-8")
            fields = plugin_config_fields(folder)
            self.assertEqual(fields["name"], "多模型")
            self.assertEqual(fields["desc"], "每条模型自带网关与厂商")
            self.assertEqual(fields["icon"], "🧩")
            self.assertEqual(fields["version"], "1.0")
            self.assertEqual(fields["settings_tab"], "模型")
            self.assertEqual(fields["enable"], "1")

    def test_identity_ignores_plugin_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = self._plugin(Path(tmp), "skills")
            (folder / "plugin-meta.json").write_text(
                '{"name":"元数据名","desc":"元数据描述","version":"9.9"}\n',
                encoding="utf-8")
            (folder / "plugin-config.ini").write_text(
                "[config]\ndir = D:/skills\n", encoding="utf-8")
            fields = plugin_config_fields(folder)
            self.assertEqual(fields["name"], "元数据名")
            self.assertEqual(fields["desc"], "元数据描述")
            self.assertEqual(fields["version"], "9.9")
            self.assertEqual(fields["enable"], "1")

    def test_no_files_falls_back_to_folder_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = self._plugin(Path(tmp), "bare")
            fields = plugin_config_fields(folder)
            self.assertEqual(fields["id"], "bare")
            self.assertEqual(fields["name"], "")
            self.assertEqual(fields["enable"], "1")

    def test_list_plugins_shows_declared_name_without_a_config(self) -> None:
        """卡片标题取 `name` 而不是目录名 —— 不能只有配过的插件才显示中文名。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = self._plugin(root, "multi_model")
            (folder / "plugin-meta.json").write_text(
                '{"name":"多模型","desc":"每条模型自带网关与厂商","version":"1.0",'
                '"settings_tab":"模型"}\n', encoding="utf-8")
            manifest = root / "plugins.ini"
            manifest.write_text("[plugin:multi_model]\n", encoding="utf-8")
            cards = list_plugins(plugins_path=manifest, plugins_dir=root)["plugins"]
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0]["title"], "多模型")
            self.assertEqual(cards[0]["description"], "每条模型自带网关与厂商")
            self.assertEqual(cards[0]["version"], "v1.0")
            self.assertEqual(cards[0]["settings_tab"], "模型")


class ConfigParseTest(unittest.TestCase):
    def test_get_plugins_parse(self) -> None:
        """清单解析只做解析：`[plugin:<名字>]` 节，节里没有字段也合法。

        名字合法性与目录存在性归装载方判（见 `PluginHost.load_manifest`），
        这里只管把清单读成结构。
        """

        with tempfile.TemporaryDirectory() as tmp:
            ini = Path(tmp) / "plugins.ini"
            ini.write_text(
                "[plugin:a]\n\n[plugin:b]\n\n[plugin:c]\npath = D:/lab/c\n",
                encoding="utf-8")
            got = get_plugins(ini)
            self.assertEqual([e["name"] for e in got], ["a", "b", "c"])
            self.assertNotIn("version", got[0])
            # path 留空时本函数不填 —— 解析留给装载方按自己的插件根做
            self.assertEqual(got[0]["path"], "")
            self.assertEqual(got[2]["path"], "D:/lab/c")

            # 节名前缀不对、上层裸键都忽略
            ini.write_text("[other]\nx = 1\nenabled = a, b\n", encoding="utf-8")
            self.assertEqual(get_plugins(ini), [])

            # 空清单 = 不装任何插件
            ini.write_text("; 什么都不列\n", encoding="utf-8")
            self.assertEqual(get_plugins(ini), [])

    def test_profile_overlay_overrides_named_fields(self) -> None:
        """profile 只覆盖显式字段，未声明项继承基底。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "plugins.ini"
            base.write_text(
                "[plugin:a]\npath = D:/lab/a\n\n[plugin:b]\n",
                encoding="utf-8",
            )
            profile = root / "plugins.headless.ini"
            profile.write_text(
                "[profile]\nbase = plugins.ini\n\n"
                "[plugin:a]\nenabled = 0\n\n[plugin:c]\n",
                encoding="utf-8",
            )
            got = {entry["name"]: entry for entry in get_plugins(profile)}
            self.assertEqual(list(got), ["a", "b", "c"])
            self.assertEqual(got["a"]["enabled"], "0")
            self.assertEqual(got["a"]["path"], "D:/lab/a")
            self.assertEqual(got["b"]["enabled"], "1")
            self.assertEqual(got["c"]["enabled"], "1")

    def test_tree_only_rejects_external_path(self) -> None:
        """plugin_tree_only 打开时，清单里的树外 path 不得装载。"""
        from agent.capabilities.plugins import PluginHost

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plugins_dir = base / "plugins"
            plugins_dir.mkdir()
            external = base / "elsewhere" / "ext"
            external.mkdir(parents=True)
            _write_meta(external)
            (external / "plugin.py").write_text(
                "def register(ctx):\n    return []\n", encoding="utf-8"
            )
            host = PluginHost(plugins_dir, ToolRegistry())
            old = __import__("os").environ.get("AI_AGENT_PLUGIN_TREE_ONLY")
            __import__("os").environ["AI_AGENT_PLUGIN_TREE_ONLY"] = "1"
            try:
                reports = host.load_manifest(
                    [{"name": "ext", "path": str(external)}]
                )
            finally:
                if old is None:
                    __import__("os").environ.pop("AI_AGENT_PLUGIN_TREE_ONLY", None)
                else:
                    __import__("os").environ["AI_AGENT_PLUGIN_TREE_ONLY"] = old
            self.assertEqual(reports[0].status, "error")
            self.assertIn("越出", reports[0].message)
            self.assertEqual(host.loaded_names(), [])

    def test_load_logs_source_integrity(self) -> None:
        """装载时 stderr 须留下入口文件来源与完整性摘要。"""
        from io import StringIO
        from unittest.mock import patch

        from agent.capabilities.plugins import PluginHost

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugins"
            (root / "good").mkdir(parents=True)
            _write_meta(root / "good")
            entry = root / "good" / "plugin.py"
            entry.write_text("def register(ctx):\n    return []\n", encoding="utf-8")
            host = PluginHost(root, ToolRegistry())
            buf = StringIO()
            with patch("sys.stderr", buf):
                reports = host.load_manifest([{"name": "good"}])
            self.assertEqual(reports[0].status, "loaded")
            text = buf.getvalue()
            self.assertIn("[plugin.load] good", text)
            self.assertIn("source=", text)
            self.assertIn("sha256=", text)

    def test_load_manifest_resolves_paths_and_reports_errors(self) -> None:
        """装载方把 `path` 落到自己的插件根，并把配置错误变成报告。"""

        from agent.capabilities.contributions import ContributionRegistry
        from agent.capabilities.plugins import PluginHost
        from agent.mechanisms.context import ContextSources

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugins"
            (root / "good").mkdir(parents=True)
            _write_meta(root / "good")
            (root / "good" / "plugin.py").write_text(
                "def register(ctx):\n    return []\n", encoding="utf-8")
            (root / "off").mkdir(parents=True)
            _write_meta(root / "off")
            (root / "off" / "plugin.py").write_text(
                "def register(ctx):\n    return []\n", encoding="utf-8")
            host = PluginHost(root, ToolRegistry(), event_bus=None,
                              context_sources=ContextSources(),
                              contributions=ContributionRegistry(),
                              plugin_data_root=Path(tmp) / "data")
            reports = {r.name: r for r in host.load_manifest([
                {"name": "good", "version": "", "path": ""},
                {"name": "off", "enabled": "0"},
                {"name": "missing", "version": "", "path": ""},
                {"name": "../evil", "version": "", "path": ""},
            ])}
            self.assertEqual(host.loaded_names(), ["good"])
            self.assertNotIn("off", reports)
            self.assertEqual(reports["missing"].status, "error")
            self.assertEqual(reports["../evil"].status, "error")
            self.assertIn("非法", reports["../evil"].message)

_TOOL_PLUGIN = '''\
from agent.capabilities.registry import ToolPlugin

class Demo(ToolPlugin):
    name = "tool_wired"
    description = "demo"
    parameters = {}

    def execute(self, arguments):
        return {"echo": "ok"}


def make_tool(ctx):
    return Demo()
'''

_TOOL_PLUGIN_SLOTS = '''{
  "version": 1,
  "root": "app",
  "slots": [
    {"path": "app/plugins/wired/tools/tool_wired", "kind": "tool",
     "factory": "plugin:make_tool"}
  ]
}
'''


class AppWiringTest(unittest.TestCase):
    def test_build_app_loads_whitelisted_plugin(self) -> None:
        """插件工具由片段声明，build_app 装配后就应在注册表里。"""
        from agent.app import build_app

        with tempfile.TemporaryDirectory() as tmp:
            pdir = Path(tmp) / "plugins"
            (pdir / "wired").mkdir(parents=True)
            _write_meta(pdir / "wired")
            (pdir / "wired" / "plugin-slots.json").write_text(
                _TOOL_PLUGIN_SLOTS, encoding="utf-8")
            (pdir / "wired" / "plugin.py").write_text(
                _TOOL_PLUGIN, encoding="utf-8")
            with mock.patch("agent.app.get_plugins", return_value=["wired"]):
                app = build_app(plugins_dir=pdir, data_root=Path(tmp) / "data")
            self.addCleanup(app.dispose)
            self.assertEqual(app.plugin_host.loaded_names(), ["wired"])
            self.assertIsNotNone(app.registry.get("tool_wired"))

    def test_build_app_empty_whitelist_noop(self) -> None:

        from agent.app import build_app

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("agent.app.get_plugins", return_value=[]):
                app = build_app(plugins_dir=Path(tmp) / "missing",
                                data_root=Path(tmp) / "data")
            self.addCleanup(app.dispose)
            self.assertEqual(app.plugin_host.loaded_names(), [])

if __name__ == "__main__":
    unittest.main()
