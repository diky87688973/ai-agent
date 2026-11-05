# -*- coding: utf-8 -*-
"""轮次快照：轮内只读、变更下一轮生效、版本未变不重建、过期结果被拒。"""
from __future__ import annotations

import dataclasses
import json
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.core.slot_config import SlotConfig  # noqa: E402
from agent.core.slot_snapshot import SnapshotStore  # noqa: E402
from agent.core.slot_spec import (  # noqa: E402
    SCOPE_APP,
    SCOPE_SESSION,
    SlotConfigError,
    SlotSpec,
)


def _spec(path: str, scope: str = SCOPE_APP, *, requires: Any = None,
          props: Any = None, method: str = "") -> SlotSpec:
    return SlotSpec(path=path, kind="service", factory="m:f", scope=scope,
                    requires={} if requires is None else requires,
                    props={} if props is None else props,
                    method=method)


def _config(*specs: SlotSpec, origins: Any = None,
            subagent_tools: Any = None) -> SlotConfig:
    return SlotConfig(root="app", version=1,
                      specs={spec.path: spec for spec in specs},
                      origins={"app/a": "alpha"} if origins is None else origins,
                      subagent_tools={"alpha": ("t",)} if subagent_tools is None
                      else subagent_tools)


def _plain(value: Any) -> Any:
    """归一化成普通容器：只用于比对与序列化，不用于读写。"""
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: _plain(getattr(value, field.name))
                for field in dataclasses.fields(value)}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_plain(item) for item in value)
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    return value


def _mutable_paths(value: Any, path: str = "") -> List[str]:
    """递归找出仍可变的容器（list / set / dict），返回带路径的违规清单。"""
    found: List[str] = []
    if isinstance(value, Mapping):
        if isinstance(value, dict):
            found.append(path or "<root>")
        for key, item in value.items():
            found.extend(_mutable_paths(item, f"{path}.{key}"))
    elif isinstance(value, (list, tuple)):
        if isinstance(value, list):
            found.append(path or "<root>")
        for index, item in enumerate(value):
            found.extend(_mutable_paths(item, f"{path}[{index}]"))
    elif isinstance(value, (set, frozenset)):
        if isinstance(value, set):
            found.append(path or "<root>")
        for index, item in enumerate(value):
            found.extend(_mutable_paths(item, f"{path}[{index}]"))
    return found


class _Rebuilder:
    """按脚本重建：每次调用返回下一份配置与实例表，并记录调用次数。"""

    def __init__(self, steps: List[Tuple[SlotConfig, Dict[str, Any]]]) -> None:
        self.steps = list(steps)
        self.calls = 0

    def __call__(self) -> Tuple[SlotConfig, Mapping[str, Any]]:
        self.calls += 1
        if not self.steps:
            raise AssertionError("重建次数超出预期")
        return self.steps.pop(0)


class SnapshotImmutabilityTest(unittest.TestCase):
    def test_snapshot_dataclass_is_frozen(self) -> None:
        store = SnapshotStore(_config(_spec("app/a")), {"app/a": object()})
        snapshot = store.begin_turn()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            snapshot.version = 99  # type: ignore[misc]

    def test_built_mapping_rejects_writes(self) -> None:
        store = SnapshotStore(_config(_spec("app/a")), {"app/a": object()})
        snapshot = store.begin_turn()
        with self.assertRaises(TypeError):
            snapshot.built["app/a"] = object()  # type: ignore[index]
        with self.assertRaises(TypeError):
            snapshot.built["app/b"] = object()  # type: ignore[index]

    def test_paths_and_get(self) -> None:
        value = object()
        store = SnapshotStore(_config(_spec("app/a"), _spec("app/b")),
                              {"app/a": value, "app/b": "b"})
        snapshot = store.begin_turn()
        self.assertEqual(snapshot.paths(), ("app/a", "app/b"))
        self.assertTrue(snapshot.has("app/a"))
        self.assertIs(snapshot.get("app/a"), value)
        with self.assertRaises(SlotConfigError):
            snapshot.get("app/ghost")


class ConfigImmutabilityTest(unittest.TestCase):
    """快照的 config 必须真只读：frozen 只锁字段赋值，不锁字段内容。"""

    def _snapshot(self):
        store = SnapshotStore(_config(_spec("app/a")), {"app/a": "a"})
        return store.begin_turn()

    def test_specs_cannot_be_written_through(self) -> None:
        snapshot = self._snapshot()
        with self.assertRaises(TypeError):
            snapshot.config.specs["app/evil"] = _spec("app/evil")

    def test_sources_cannot_be_written_through(self) -> None:
        snapshot = self._snapshot()
        with self.assertRaises(TypeError):
            snapshot.config.sources["app/evil"] = "x"

    def test_subagent_tools_cannot_be_written_through(self) -> None:
        snapshot = self._snapshot()
        with self.assertRaises(TypeError):
            snapshot.config.subagent_tools["beta"] = ("t",)

    def test_frozen_config_still_reads(self) -> None:
        snapshot = self._snapshot()
        self.assertEqual(snapshot.config.spec("app/a").path, "app/a")
        self.assertEqual(tuple(snapshot.config.sources), ("app/a",))
        self.assertEqual(dict(snapshot.config.subagent_tools), {"alpha": ("t",)})

    def test_caller_config_is_not_frozen(self) -> None:
        """冻结只作用于副本，调用方传进来的对象仍可正常使用。"""
        original = _config(_spec("app/a"))
        SnapshotStore(original, {"app/a": "a"}).begin_turn()
        original.specs["app/later"] = _spec("app/later")
        self.assertIn("app/later", original.specs)

    def test_rebuilt_config_is_also_frozen(self) -> None:
        first = _config(_spec("app/a"))
        second = _config(_spec("app/a"))
        store = SnapshotStore(first, {"app/a": "a"},
                              rebuild=_Rebuilder([(second, {"app/a": "a"})]))
        store.stage("reload")
        snapshot = store.begin_turn()
        with self.assertRaises(TypeError):
            snapshot.config.specs["app/evil"] = _spec("app/evil")
        with self.assertRaises(TypeError):
            snapshot.config.sources["app/evil"] = "x"
        with self.assertRaises(TypeError):
            snapshot.config.subagent_tools["beta"] = ("t",)


class NodeImmutabilityTest(unittest.TestCase):
    """节点内部的字典字段也必须锁死：只冻装节点的映射等于只锁了一半。"""

    def _original(self) -> SlotConfig:
        return _config(
            _spec("app/a", requires={"dep": "app/b"},
                  props={"label": "x", "binding": {"input": {"action": "a"}}},
                  method="GET"),
            _spec("app/b"))

    def test_requires_cannot_be_written_through(self) -> None:
        snapshot = SnapshotStore(self._original(), {"app/a": "a",
                                                    "app/b": "b"}).begin_turn()
        with self.assertRaises(TypeError):
            snapshot.config.specs["app/a"].requires["evil"] = "app/b"

    def test_props_cannot_be_written_through(self) -> None:
        snapshot = SnapshotStore(self._original(), {"app/a": "a",
                                                    "app/b": "b"}).begin_turn()
        with self.assertRaises(TypeError):
            snapshot.config.specs["app/a"].props["evil"] = "x"

    def test_nested_props_are_frozen_too(self) -> None:
        """嵌套层同病：props 里再套一层 dict 也是同样可写的。"""
        snapshot = SnapshotStore(self._original(), {"app/a": "a",
                                                    "app/b": "b"}).begin_turn()
        binding = snapshot.config.specs["app/a"].props["binding"]
        with self.assertRaises(TypeError):
            binding["input"]["action"] = "evil"

    def test_frozen_node_equals_original_but_is_not_it(self) -> None:
        """归一化值相等、身份必须不同：冻成原物就等于没冻。"""
        original = self._original()
        snapshot = SnapshotStore(original, {"app/a": "a",
                                            "app/b": "b"}).begin_turn()
        frozen = snapshot.config.specs["app/a"]
        self.assertEqual(_plain(frozen), _plain(original.specs["app/a"]))
        self.assertIsNot(frozen, original.specs["app/a"])

    def test_serialization_matches_original(self) -> None:
        """序列化逐字相同：对外契约不变。"""
        original = self._original()
        snapshot = SnapshotStore(original, {"app/a": "a",
                                            "app/b": "b"}).begin_turn()
        for path in ("app/a", "app/b"):
            with self.subTest(path=path):
                self.assertEqual(
                    json.dumps(_plain(snapshot.config.specs[path]),
                               sort_keys=True, default=str),
                    json.dumps(_plain(original.specs[path]),
                               sort_keys=True, default=str))

    def test_sequences_become_tuples(self) -> None:
        """序列必须转 tuple：list 能 append，等于只读有洞。"""
        original = _config(_spec("app/a", props={"options": ["x", "y"],
                                                  "binding": {"existing": ["z"]}}))
        snapshot = SnapshotStore(original, {"app/a": "a"}).begin_turn()
        props = snapshot.config.specs["app/a"].props
        self.assertIsInstance(props["options"], tuple)
        self.assertIsInstance(props["binding"]["existing"], tuple)
        with self.assertRaises(AttributeError):
            props["options"].append("EVIL")
        with self.assertRaises(AttributeError):
            props["binding"]["existing"].append("EVIL")

    def test_original_sequences_stay_lists(self) -> None:
        """冻结只作用于副本：原配置里的 list 必须仍是 list 且可写。"""
        original = _config(_spec("app/a", props={"options": ["x"]}))
        SnapshotStore(original, {"app/a": "a"}).begin_turn()
        self.assertIsInstance(original.specs["app/a"].props["options"], list)
        original.specs["app/a"].props["options"].append("later")
        self.assertEqual(original.specs["app/a"].props["options"], ["x", "later"])

    def test_no_mutable_container_survives_anywhere(self) -> None:
        """收口断言：快照全部节点的 requires/props 不得残留可变容器。"""
        original = _config(
            _spec("app/a", requires={"dep": "app/b"},
                  props={"options": [{"value": "x"}],
                         "scripts": ["ui/a.js"],
                         "binding": {"input": {"existing": ["#a"]}}},
                  method="GET"),
            _spec("app/b"))
        snapshot = SnapshotStore(original, {"app/a": "a",
                                            "app/b": "b"}).begin_turn()
        offenders: List[str] = []
        for path in snapshot.config.specs:
            node = snapshot.config.specs[path]
            for field in ("requires", "props"):
                offenders.extend(_mutable_paths(getattr(node, field),
                                                f"{path}.{field}"))
        self.assertEqual(offenders, [], "仍有可变容器：" + "、".join(offenders))

    def test_original_nodes_stay_writable(self) -> None:
        """装配方还要用原配置，冻结不得污染源对象。"""
        original = self._original()
        SnapshotStore(original, {"app/a": "a", "app/b": "b"}).begin_turn()
        original.specs["app/a"].requires["later"] = "app/b"
        original.specs["app/a"].props["later"] = 1
        self.assertEqual(original.specs["app/a"].requires["later"], "app/b")

    def test_rebuilt_nodes_are_frozen(self) -> None:
        first = self._original()
        second = self._original()
        store = SnapshotStore(first, {"app/a": "a", "app/b": "b"},
                              rebuild=_Rebuilder([(second, {"app/a": "a",
                                                            "app/b": "b"})]))
        store.stage("reload")
        snapshot = store.begin_turn()
        node = snapshot.config.specs["app/a"]
        with self.assertRaises(TypeError):
            node.requires["evil"] = "app/b"
        with self.assertRaises(TypeError):
            node.props["evil"] = "x"
        self.assertIsNot(node, second.specs["app/a"])


class UnknownPathTest(unittest.TestCase):
    def test_unknown_path_is_rejected(self) -> None:
        """装配结果出现配置没有的路径 = 合并与装配不同步，不得静默丢弃。"""
        with self.assertRaises(SlotConfigError) as ctx:
            SnapshotStore(_config(_spec("app/a")),
                          {"app/a": "a", "app/ghost": "x"})
        self.assertIn("app/ghost", str(ctx.exception))

    def test_unknown_path_in_rebuild_is_rejected(self) -> None:
        first = _config(_spec("app/a"))
        store = SnapshotStore(first, {"app/a": "a"},
                              rebuild=_Rebuilder([(first, {"app/ghost": "x"})]))
        store.stage("reload")
        with self.assertRaises(SlotConfigError) as ctx:
            store.begin_turn()
        self.assertIn("app/ghost", str(ctx.exception))


class SessionScopeTest(unittest.TestCase):
    def test_session_instances_never_enter_snapshot(self) -> None:
        """session 实例跨会话各不相同，固化进快照就会串实例。"""
        config = _config(_spec("app/a"), _spec("app/s", SCOPE_SESSION))
        store = SnapshotStore(config, {"app/a": "a", "app/s": "s"})
        snapshot = store.begin_turn()
        self.assertTrue(snapshot.has("app/a"))
        self.assertFalse(snapshot.has("app/s"))
        self.assertEqual(snapshot.paths(), ("app/a",))

    def test_rebuild_also_filters_session_instances(self) -> None:
        first = _config(_spec("app/a"))
        second = _config(_spec("app/a"), _spec("app/s", SCOPE_SESSION))
        store = SnapshotStore(first, {"app/a": "a"},
                              rebuild=_Rebuilder([(second, {"app/a": "a",
                                                            "app/s": "s"})]))
        store.stage("reload")
        snapshot = store.begin_turn()
        self.assertEqual(snapshot.version, 1)
        self.assertEqual(snapshot.paths(), ("app/a",))


class TurnBoundaryTest(unittest.TestCase):
    def test_same_snapshot_object_when_nothing_changed(self) -> None:
        """没有注册/注销时不得重建，也不得深拷 223 个节点。"""
        rebuilder = _Rebuilder([(_config(_spec("app/a")), {"app/a": "a"})])
        store = SnapshotStore(_config(_spec("app/a")), {"app/a": "a"},
                              rebuild=rebuilder)
        first = store.begin_turn()
        second = store.begin_turn()
        third = store.begin_turn()
        self.assertIs(first, second)
        self.assertIs(second, third)
        self.assertEqual(rebuilder.calls, 0)

    def test_staged_change_not_visible_within_turn(self) -> None:
        """轮内注册只进待生效集合，当前快照看不到。"""
        first = _config(_spec("app/a"))
        second = _config(_spec("app/a"), _spec("app/b"))
        rebuilder = _Rebuilder([(second, {"app/a": "a", "app/b": "b"})])
        store = SnapshotStore(first, {"app/a": "a"}, rebuild=rebuilder)
        snapshot = store.begin_turn()
        store.stage("plugin:add")
        self.assertTrue(store.has_pending)
        self.assertFalse(snapshot.has("app/b"))
        self.assertEqual(snapshot.version, 0)
        self.assertEqual(store.version, 0)

    def test_next_turn_sees_staged_change(self) -> None:
        first = _config(_spec("app/a"))
        second = _config(_spec("app/a"), _spec("app/b"))
        rebuilder = _Rebuilder([(second, {"app/a": "a", "app/b": "b"})])
        store = SnapshotStore(first, {"app/a": "a"}, rebuild=rebuilder)
        before = store.begin_turn()
        store.stage("plugin:add")
        after = store.begin_turn()
        self.assertIsNot(before, after)
        self.assertEqual(rebuilder.calls, 1)
        self.assertEqual(after.version, 1)
        self.assertTrue(after.has("app/b"))
        self.assertFalse(before.has("app/b"))
        self.assertFalse(store.has_pending)

    def test_staged_change_without_rebuild_entry_is_rejected(self) -> None:
        store = SnapshotStore(_config(_spec("app/a")), {"app/a": "a"})
        store.stage("plugin:add")
        with self.assertRaises(SlotConfigError):
            store.begin_turn()

    def test_rebuild_only_once_per_turn(self) -> None:
        """同一轮即便多次 begin_turn，也只在有待生效变更时重建一次。"""
        first = _config(_spec("app/a"))
        second = _config(_spec("app/a"), _spec("app/b"))
        rebuilder = _Rebuilder([(second, {"app/a": "a", "app/b": "b"})])
        store = SnapshotStore(first, {"app/a": "a"}, rebuild=rebuilder)
        store.stage("one")
        store.stage("two")
        snapshot = store.begin_turn()
        self.assertEqual(rebuilder.calls, 1)
        self.assertEqual(snapshot.version, 1)
        self.assertIs(store.begin_turn(), snapshot)
        self.assertEqual(rebuilder.calls, 1)


class StaleResultTest(unittest.TestCase):
    def test_result_from_old_version_is_rejected(self) -> None:
        first = _config(_spec("app/a"))
        second = _config(_spec("app/a"), _spec("app/b"))
        rebuilder = _Rebuilder([(second, {"app/a": "a", "app/b": "b"})])
        store = SnapshotStore(first, {"app/a": "a"}, rebuild=rebuilder)
        old = store.begin_turn()
        store.stage("plugin:add")
        store.begin_turn()
        self.assertTrue(store.accept(old.version) is False)
        self.assertTrue(store.accept(store.version))

    def test_result_from_current_version_is_accepted(self) -> None:
        store = SnapshotStore(_config(_spec("app/a")), {"app/a": "a"})
        snapshot = store.begin_turn()
        self.assertTrue(store.accept(snapshot.version))


class StoreOwnershipTest(unittest.TestCase):
    def test_two_stores_are_independent(self) -> None:
        """两个 store 各自独立、版本互不共享；唯一性靠注入而非全局单例。"""
        one = SnapshotStore(_config(_spec("app/a")), {"app/a": "a"})
        two = SnapshotStore(_config(_spec("app/a")), {"app/a": "a"})
        self.assertIsNot(one, two)
        self.assertEqual(one.version, 0)
        self.assertEqual(two.version, 0)
        self.assertIsNot(one.current, two.current)

    def test_store_has_no_module_level_singleton(self) -> None:
        import agent.core.slot_snapshot as module

        leaked = [name for name, value in vars(module).items()
                  if isinstance(value, SnapshotStore)]
        self.assertEqual(leaked, [])

    def test_snapshot_is_stable_across_readers(self) -> None:
        """轮内多个读取点问同一个 store，拿到的是同一份快照。"""
        store = SnapshotStore(_config(_spec("app/a")), {"app/a": "a"})
        readers = [store.begin_turn() for _ in range(5)]
        self.assertEqual(len({id(item) for item in readers}), 1)


class RealRepoSerializationTest(unittest.TestCase):
    """真实仓库取样：一个带 options 的 setting、一个带脚本样式的 ui-control、一个空 props 容器。"""

    @classmethod
    def setUpClass(cls) -> None:
        ROOT = Path(__file__).resolve().parent.parent
        from agent.core.slot_fragments import load_merged

        cls.config = load_merged(ROOT)
        cls.snapshot = SnapshotStore(
            cls.config,
            {path: object() for path in cls.config.specs}).begin_turn()

    def _samples(self) -> List[str]:
        settings = [p for p, s in self.config.specs.items()
                    if s.kind == "setting" and "options" in s.props]
        ui = [p for p, s in self.config.specs.items()
              if s.kind == "ui-control" and "scripts" in s.props]
        empty = [p for p, s in self.config.specs.items()
                 if s.kind == "container" and not s.props]
        self.assertTrue(settings, "未找到带 options 的 setting")
        self.assertTrue(ui, "未找到带 scripts 的 ui-control")
        self.assertTrue(empty, "未找到空 props 的 container")
        return [settings[0], ui[0], empty[0]]

    def test_serialization_is_byte_identical(self) -> None:
        for path in self._samples():
            with self.subTest(path=path):
                frozen = self.snapshot.config.specs[path]
                original = self.config.specs[path]
                self.assertEqual(
                    json.dumps(_plain(frozen), sort_keys=True, default=str),
                    json.dumps(_plain(original), sort_keys=True, default=str))

    def test_values_equal_and_identity_differs(self) -> None:
        for path in self._samples():
            with self.subTest(path=path):
                frozen = self.snapshot.config.specs[path]
                self.assertEqual(_plain(frozen), _plain(self.config.specs[path]))
                self.assertIsNot(frozen, self.config.specs[path])

    def test_no_mutable_container_in_real_repo(self) -> None:
        """收口证据：真实仓库全部节点的 requires/props 不得残留任何可变容器。"""
        offenders: List[str] = []
        for path in self.snapshot.config.specs:
            node = self.snapshot.config.specs[path]
            for field in ("requires", "props"):
                offenders.extend(_mutable_paths(getattr(node, field),
                                                f"{path}.{field}"))
        self.assertEqual(offenders, [], "仍有可变容器：" + "、".join(offenders[:10]))

    def test_real_repo_lists_became_tuples(self) -> None:
        """真实载荷里的列表已全部转 tuple，且原配置里的仍是 list。"""
        converted = 0
        for path, spec in self.config.specs.items():
            for key, value in spec.props.items():
                if isinstance(value, list):
                    converted += 1
                    self.assertIsInstance(
                        self.snapshot.config.specs[path].props[key], tuple)
        self.assertGreater(converted, 0)
        self.assertIsInstance(next(
            value for spec in self.config.specs.values()
            for value in spec.props.values() if isinstance(value, list)), list)


if __name__ == "__main__":
    unittest.main()
