# -*- coding: utf-8 -*-
"""插口树的绑定、解析、回退和事务测试。"""
from __future__ import annotations

import unittest

from agent.capabilities.slot_registry import (
    SlotRegistry,
    SlotRegistryError,
)


class SlotRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = SlotRegistry()
        self.path = "app/kernel/modules/compaction/build-context"
        self.registry.register_slot(
            self.path,
            kind="kernel-stage",
            contract={"input": "messages", "output": "context"},
            subtree=("child",),
            default=lambda value: ("default", value),
        )

    def test_slot_duplicate_rejected(self) -> None:
        with self.assertRaises(SlotRegistryError):
            self.registry.register_slot(self.path, default=lambda value: value)

    def test_replace_and_unbind_restores_default(self) -> None:
        original = self.registry.resolve(self.path)
        binding = self.registry.bind(
            self.path, lambda value: ("plugin", value), owner="plugin_a")
        self.assertEqual(self.registry.resolve(self.path)(1), ("plugin", 1))
        binding.dispose()
        self.assertIs(self.registry.resolve(self.path), original)
        self.assertEqual(self.registry.resolve(self.path)(1), ("default", 1))

    def test_priority_and_active_binding(self) -> None:
        low = self.registry.bind(
            self.path, lambda value: ("low", value), owner="low", priority=1)
        high = self.registry.bind(
            self.path, lambda value: ("high", value), owner="high", priority=10)
        self.assertIs(self.registry.active_binding(self.path), high)
        self.assertEqual(self.registry.resolve(self.path)(1), ("high", 1))
        high.dispose()
        self.assertIs(self.registry.active_binding(self.path), low)
        self.assertEqual(self.registry.resolve(self.path)(1), ("low", 1))

    def test_same_priority_conflict_rejected(self) -> None:
        self.registry.bind(self.path, lambda value: value, owner="a")
        with self.assertRaises(SlotRegistryError):
            self.registry.bind(self.path, lambda value: value, owner="b")

    def test_contract_version_mismatch_rejected(self) -> None:
        with self.assertRaises(SlotRegistryError):
            self.registry.bind(
                self.path, lambda value: value, owner="a",
                contract_version="2")

    def test_bind_unknown_path_rejected(self) -> None:
        """绑定未注册的插口必须报错，且错误里点名该路径。"""
        missing = "app/not/exposed"
        with self.assertRaises(SlotRegistryError) as caught:
            self.registry.bind(missing, lambda: None, owner="a")
        self.assertIn(missing, str(caught.exception))

    def test_wrap_receives_base(self) -> None:
        self.registry.bind(
            self.path,
            lambda base: lambda value: ("wrapped", base(value)),
            owner="wrapper",
            mode="wrap",
            priority=1,
        )
        self.assertEqual(
            self.registry.resolve(self.path)(4), ("wrapped", ("default", 4)))

    def test_extend_collection(self) -> None:
        path = "app/shell/app/shell/web-ui/actions"
        self.registry.register_slot(path, default=["base"], children="keyed")
        self.registry.bind(path, ["extra"], owner="a", mode="extend")
        self.assertEqual(self.registry.resolve_items(path), ["base", "extra"])
        self.assertEqual(self.registry.node(path).default, ["base"])

    def test_replace_subtree_applies_to_children(self) -> None:
        child = self.path + "/child"
        self.registry.register_slot(child, default=lambda: "child-default")
        binding = self.registry.bind(
            self.path, lambda: "subtree-root", owner="a",
            mode="replace_subtree")
        self.assertEqual(self.registry.resolve(self.path)(), "subtree-root")
        self.assertEqual(self.registry.resolve(child)(), "subtree-root")
        binding.dispose()
        self.assertEqual(self.registry.resolve(child)(), "child-default")

    def test_drop_owner_removes_bindings(self) -> None:
        self.registry.bind(self.path, lambda value: value, owner="a", priority=1)
        self.registry.bind(self.path, lambda value: value, owner="b", priority=2)
        self.assertEqual(self.registry.drop_owner("a"), 1)
        self.assertEqual([b.owner for b in self.registry.bindings_of(self.path)], ["b"])

    def test_transaction_rolls_back_new_slot(self) -> None:
        path = "app/test/rollback"
        with self.assertRaises(RuntimeError):
            with self.registry.transaction():
                self.registry.register_slot(path)
                raise RuntimeError("boom")
        with self.assertRaises(SlotRegistryError):
            self.registry.node(path)

    def test_execution_snapshot_freezes_bindings(self) -> None:
        with self.registry.execution_snapshot():
            binding = self.registry.bind(
                self.path, lambda value: ("snapshot", value), owner="a")
            self.assertEqual(self.registry.resolve(self.path)(1), ("default", 1))
            binding.dispose()
        self.assertEqual(self.registry.resolve(self.path)(1), ("default", 1))

    def test_describe_does_not_expose_implementation_objects(self) -> None:
        self.registry.bind(self.path, lambda value: value, owner="a")
        snapshot = self.registry.describe()
        row = snapshot["nodes"][0]
        self.assertTrue(row["bindings"][0]["implementation"].endswith("<lambda>"))
        self.assertIsInstance(row["default"], str)


if __name__ == "__main__":
    unittest.main()
