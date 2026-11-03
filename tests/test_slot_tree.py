# -*- coding: utf-8 -*-
"""自装配树：清单、子节点、失败与回滚。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.core.slot import SlotContainer, SlotContribution, SlotLeaf
from agent.core.slot_tree import SlotRuntime, SlotTree, SlotTreeError


def make_leaf(ctx):
    return SlotLeaf(ctx.node.path)


def make_fail(ctx):
    raise RuntimeError("boom")


class SlotTreeTest(unittest.TestCase):
    def _tree(self, nodes, **kwargs):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8")
        json.dump({"root": "app", "nodes": nodes}, handle)
        handle.close()
        self.addCleanup(Path(handle.name).unlink)
        return SlotTree.load(Path(handle.name), runtime=SlotRuntime(**kwargs))

    def test_container_assembles_direct_children(self) -> None:
        tree = self._tree([
            {"path": "app/group", "factory": "tests.test_slot_tree:make_container"},
            {"path": "app/group/leaf", "factory": "tests.test_slot_tree:make_leaf"},
        ])
        root = tree.materialize(tree.roots()[0])
        self.assertTrue(tree.assemble(root))
        self.assertTrue(tree.node("app/group/leaf").assembled)

    def test_repeated_assembly_is_idempotent(self) -> None:
        tree = self._tree([
            {"path": "app/group", "factory": "tests.test_slot_tree:make_container"},
            {"path": "app/group/leaf", "factory": "tests.test_slot_tree:make_leaf"},
        ])
        root = tree.materialize(tree.roots()[0])
        self.assertTrue(tree.assemble(root))
        self.assertTrue(tree.assemble(root))
        self.assertTrue(tree.assemble(root))
        self.assertEqual(len(root._plugins), 1)
        disposed = []
        leaf = tree.node("app/group/leaf").instance
        leaf.dispose = lambda: disposed.append(True)
        tree.dispose_all()
        tree.dispose_all()
        self.assertEqual(disposed, [True])

    def test_dynamic_replacement_restores_previous(self) -> None:
        tree = self._tree([])
        path = "app/shell/web-ui/actions/example"
        calls = []

        def make(name):
            def register():
                calls.append(name + "-on")
                return lambda: calls.append(name + "-off")
            return lambda _ctx: SlotContribution(path, register, master=True)

        first = tree.add_dynamic(path, make("first"))
        second = tree.add_dynamic(path, make("second"), replace=True)
        self.assertEqual(calls, ["first-on", "first-off", "second-on"])
        second()
        self.assertEqual(calls[-2:], ["second-off", "first-on"])
        first()

    def test_static_session_node_can_be_replaced_and_restored(self) -> None:
        path = "app/kernel/modules/compress"
        tree = self._tree([
            {"path": path, "factory": "tests.test_slot_tree:make_leaf",
             "metadata": {"scope": "session"}},
        ])
        original = tree.node(path)
        replacement = tree.add_dynamic(path, make_leaf, replace=True)
        self.assertTrue(tree.node(path).metadata.get("dynamic"))
        replacement()
        self.assertIs(tree.node(path), original)
        self.assertFalse(tree.node(path).metadata.get("dynamic"))

    def test_disabled_child_is_not_materialized(self) -> None:
        tree = self._tree([
            {"path": "app/group", "factory": "tests.test_slot_tree:make_container"},
            {"path": "app/group/off", "factory": "tests.test_slot_tree:make_leaf",
             "enabled": False},
        ])
        root = tree.materialize(tree.roots()[0])
        self.assertTrue(tree.assemble(root))
        self.assertIsNone(tree.node("app/group/off").instance)

    def test_factory_failure_blocks_master(self) -> None:
        tree = self._tree([
            {"path": "app/group", "factory": "tests.test_slot_tree:make_container"},
            {"path": "app/group/bad", "factory": "tests.test_slot_tree:make_fail",
             "master": True},
        ])
        root = tree.materialize(tree.roots()[0])
        with self.assertRaises(SlotTreeError):
            tree.assemble(root)

    def test_requires_injects_value(self) -> None:
        tree = self._tree([
            {"path": "app/a", "factory": "tests.test_slot_tree:make_value",
             "metadata": {"value": "A"}},
            {"path": "app/b", "factory": "tests.test_slot_tree:make_consumer",
             "requires": {"source": "app/a"}},
        ])
        b = tree.materialize(tree.node("app/b"))
        self.assertTrue(tree.assemble(b))
        self.assertEqual(b.value, "A")


class _Container(SlotContainer):
    def __init__(self, path):
        super().__init__(path)


def make_container(ctx):
    return _Container(ctx.node.path)


class _Value(SlotLeaf):
    def __init__(self, path, value):
        super().__init__(path)
        self.value = value

    def port_value(self):
        return self.value


def make_value(ctx):
    return _Value(ctx.node.path, ctx.node.metadata["value"])


class _Consumer(_Value):
    def __init__(self, path, ports):
        super().__init__(path, ports["source"])


def make_consumer(ctx):
    return _Consumer(ctx.node.path, ctx.ports)


if __name__ == "__main__":
    unittest.main()
