# -*- coding: utf-8 -*-
"""工具注册表测试：插件协议 / 注册 / 解析 / 注销 / 声明导出。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.capabilities.builtin import echo  # noqa: E402
from agent.capabilities.registry import ToolPlugin, ToolRegistry  # noqa: E402


class _EchoForTest(ToolPlugin):
    """测试用回显插件。"""

    name = "echo_t"
    description = "测试回显"
    parameters = {"text": {"type": "string"}}

    def execute(self, arguments):
        return f"echo: {arguments.get('text', '')}"


class _AlphaTool(ToolPlugin):
    """排序用最小插件（a_tool）。"""

    name = "a_tool"

    def execute(self, arguments):
        return None


class _ParallelTool(ToolPlugin):
    """预埋标记插件（parallel_safe=True）。"""

    name = "p_tool"
    parallel_safe = True

    def execute(self, arguments):
        return None


class _NoExec:
    """非协议对象：execute 不可调用。"""

    name = "no_exec"
    parameters = {}
    execute = None


class ToolRegistryTest(unittest.TestCase):
    """ToolPlugin / ToolRegistry 行为。"""

    def setUp(self) -> None:
        self.registry = ToolRegistry()

    def test_register_and_get(self) -> None:
        """注册后可解析回同一实例。"""
        plugin = _EchoForTest()
        self.registry.register(plugin)
        self.assertIs(self.registry.get("echo_t"), plugin)

    def test_get_missing_returns_none(self) -> None:
        """未注册解析返回 None（管道转为"未知工具"回灌）。"""
        self.assertIsNone(self.registry.get("nope"))

    def test_register_duplicate_rejected(self) -> None:
        """重复注册被拒。"""
        self.registry.register(_EchoForTest())
        with self.assertRaises(ValueError):
            self.registry.register(_EchoForTest())

    def test_register_empty_name_rejected(self) -> None:
        """空名称注册被拒。"""
        bad = _EchoForTest()
        bad.name = "   "
        with self.assertRaises(ValueError):
            self.registry.register(bad)

    def test_register_non_dict_parameters_rejected(self) -> None:
        """parameters 非 dict 注册被拒。"""
        bad = _EchoForTest()
        bad.name = "bad_params"
        bad.parameters = "not-a-dict"
        with self.assertRaises(ValueError):
            self.registry.register(bad)

    def test_register_non_callable_execute_rejected(self) -> None:
        """execute 不可调用注册被拒。"""
        with self.assertRaises(ValueError):
            self.registry.register(_NoExec())

    def test_disposer_removes_plugin(self) -> None:
        """disposer 调用后插件被注销。"""
        dispose = self.registry.register(_EchoForTest())
        dispose()
        self.assertIsNone(self.registry.get("echo_t"))

    def test_disposer_idempotent_and_reregister(self) -> None:
        """disposer 幂等；注销后同名可再注册。"""
        dispose = self.registry.register(_EchoForTest())
        dispose()
        dispose()
        again = _EchoForTest()
        self.registry.register(again)
        self.assertIs(self.registry.get("echo_t"), again)

    def test_schemas_sorted_and_snapshot(self) -> None:
        """声明导出：按名称排序、含 parallel_safe、快照与实例解耦。"""
        self.registry.register(_EchoForTest())
        self.registry.register(_AlphaTool())
        schemas = self.registry.schemas()
        self.assertEqual([s["name"] for s in schemas], ["a_tool", "echo_t"])
        self.assertIn("parallel_safe", schemas[0])
        self.assertFalse(schemas[0]["parallel_safe"])
        schemas[0]["parameters"]["injected"] = 1
        self.assertNotIn("injected", self.registry.schemas()[0]["parameters"])

    def test_parallel_safe_predeclared(self) -> None:
        """parallel_safe 可声明并随声明导出。"""
        self.registry.register(_ParallelTool())
        self.assertTrue(self.registry.schemas()[0]["parallel_safe"])

    def test_execute_contract(self) -> None:
        """execute 返回裸值（管道负责包装信封）。"""
        self.registry.register(_EchoForTest())
        plugin = self.registry.get("echo_t")
        self.assertEqual(plugin.execute({"text": "hi"}), "echo: hi")

    def test_builtin_echo_integrates(self) -> None:
        """内置 echo 样板与注册表集成。"""
        self.registry.register(echo.build())
        plugin = self.registry.get("echo")
        self.assertEqual(plugin.execute({"text": "x"}), "echo: x")

    def test_dispose_all_clears_everything(self) -> None:
        """dispose_all 清空全部；旧句柄仍幂等。"""
        dispose_a = self.registry.register(_EchoForTest())
        self.registry.register(_AlphaTool())
        self.registry.dispose_all()
        self.assertIsNone(self.registry.get("echo_t"))
        self.assertIsNone(self.registry.get("a_tool"))
        dispose_a()

    def test_dispose_all_empty_ok(self) -> None:
        """无注册时 dispose_all 无操作。"""
        self.registry.dispose_all()


class ToolDisplayDeclarationTest(unittest.TestCase):
    """工具自带展示信息（label / icon）：界面不维护工具名表。"""

    def test_plugin_carries_display_fields(self) -> None:
        from agent.capabilities.registry import ToolPlugin

        class _T(ToolPlugin):
            name = "t_demo"
            label = "示例工具"
            icon = "🎈"

            def execute(self, arguments):
                return "ok"

        row = _T()
        self.assertEqual(row.label, "示例工具")
        self.assertEqual(row.icon, "🎈")

    def test_defaults_are_empty(self) -> None:
        from agent.capabilities.registry import ToolPlugin

        class _Bare(ToolPlugin):
            name = "t_bare"

            def execute(self, arguments):
                return ""

        self.assertEqual(_Bare().label, "")
        self.assertEqual(_Bare().icon, "")

    def test_display_list_shape(self) -> None:
        from agent.capabilities.registry import ToolRegistry

        class _T(ToolPlugin := __import__("agent.capabilities.registry",
                                          fromlist=["ToolPlugin"]).ToolPlugin):
            name = "t_x"
            label = "示例"
            icon = "🧪"

            def execute(self, arguments):
                return ""

        reg = ToolRegistry()
        reg.register(_T())
        rows = reg.display_list()
        self.assertEqual(rows, [{"name": "t_x", "label": "示例", "icon": "🧪"}])

if __name__ == "__main__":
    unittest.main()
