# -*- coding: utf-8 -*-
"""AppContext 测试：注册 / 解析 / disposer / 逆序清理。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.core.context import AppContext  # noqa: E402


class AppContextTest(unittest.TestCase):
    """AppContext：注册表 + disposer 行为。"""

    def test_register_and_get(self) -> None:
        """注册后可解析回同一对象。"""
        ctx = AppContext()
        obj = object()
        ctx.register("demo", obj)
        self.assertIs(ctx.get("demo"), obj)

    def test_get_missing_raises(self) -> None:
        """未注册服务解析抛 KeyError。"""
        ctx = AppContext()
        with self.assertRaises(KeyError):
            ctx.get("nope")

    def test_register_duplicate_rejected(self) -> None:
        """重复注册被拒（防装配错误）。"""
        ctx = AppContext()
        ctx.register("demo", object())
        with self.assertRaises(ValueError):
            ctx.register("demo", object())

    def test_register_empty_name_rejected(self) -> None:
        """空名称注册被拒。"""
        ctx = AppContext()
        with self.assertRaises(ValueError):
            ctx.register("   ", object())

    def test_disposer_removes_service(self) -> None:
        """disposer 调用后服务被注销。"""
        ctx = AppContext()
        dispose = ctx.register("demo", object())
        dispose()
        with self.assertRaises(KeyError):
            ctx.get("demo")

    def test_disposer_idempotent(self) -> None:
        """disposer 幂等：二次调用无副作用，且不阻挡同名再注册。"""
        ctx = AppContext()
        dispose = ctx.register("demo", object())
        dispose()
        dispose()
        ctx.register("demo", "again")
        self.assertEqual(ctx.get("demo"), "again")

    def test_none_value_service_fully_disposed(self) -> None:
        """None 值服务：dispose 后内部登记无残留；dispose_all 不遗漏。"""
        ctx = AppContext()
        dispose = ctx.register("none_demo", None)
        dispose()
        self.assertEqual(len(ctx._disposers), 0)  # 白盒：登记已清
        # dispose_all 路径也须清空 None 值服务
        ctx.register("none_demo", None)
        ctx.dispose_all()
        self.assertEqual(len(ctx._services), 0)
        with self.assertRaises(KeyError):
            ctx.get("none_demo")

    def test_dispose_all_clears_everything(self) -> None:
        """dispose_all 后全部服务被清理；旧句柄仍幂等。"""
        ctx = AppContext()
        dispose_a = ctx.register("a", 1)
        ctx.register("b", 2)
        ctx.register("c", 3)
        ctx.dispose_all()
        for name in ("a", "b", "c"):
            with self.assertRaises(KeyError):
                ctx.get(name)
        dispose_a()  # 已注销后旧句柄仍幂等

    def test_dispose_all_empty_ok(self) -> None:
        """无注册时 dispose_all 为无操作。"""
        ctx = AppContext()
        ctx.dispose_all()

    def test_dispose_then_dispose_all_consistent(self) -> None:
        """先单独注销一个，再 dispose_all：剩余全部清理、无残留。"""
        ctx = AppContext()
        dispose_a = ctx.register("a", 1)
        ctx.register("b", 2)
        dispose_a()
        ctx.dispose_all()
        for name in ("a", "b"):
            with self.assertRaises(KeyError):
                ctx.get(name)


if __name__ == "__main__":
    unittest.main()
