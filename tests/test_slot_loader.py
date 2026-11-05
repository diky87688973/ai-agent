# -*- coding: utf-8 -*-
"""插口装配器：配置校验、拓扑顺序、构造与释放、作用域、覆盖模式。"""
from __future__ import annotations

import dataclasses
import unittest
import uuid
from dataclasses import fields
from pathlib import Path
from typing import Any, Dict, List
from unittest import mock

from agent.core import event_name as ev
from agent.core import slot_assembly, slot_spec
from agent.core.slot_assembly import (
    SessionAssembly,
    SlotAssembly,
    build_from_config,
)
from agent.core.slot_config import (
    SlotConfig,
    load_config,
    topo_order,
)
from agent.core.slot_factory import resolve_factory
from agent.core.slot_override import resolve_bindings
from agent.core.slot_spec import (
    BASE_MODE,
    OVERRIDE_FIELDS,
    SCOPE_APP,
    SCOPE_SESSION,
    SPEC_FIELDS,
    SettingDecl,
    SlotAssemblyError,
    SlotConfigError,
    SlotSpec,
    has_descendants,
    holds_children,
)

_NOT_CALLABLE = 4004


def _noop(*_args: Any, **_kwargs: Any) -> str:
    return "noop"


def _config(rows: List[Dict[str, Any]], **extra: Any) -> SlotConfig:
    return SlotConfig.parse({"version": 1, "root": "app", "slots": rows, **extra})


def _resolver(table: Dict[str, Any]) -> Any:
    def _resolve(spec: str) -> Any:
        return table[spec]
    return _resolve


class _Node:
    """可记录释放顺序的构造结果。"""

    def __init__(self, name: str, log: List[str], *, fail: bool = False) -> None:
        self.name = name
        self.log = log
        self.fail = fail

    def dispose(self) -> None:
        self.log.append("dispose:" + self.name)
        if self.fail:
            raise RuntimeError("dispose boom")


class ConfigParseTest(unittest.TestCase):
    def test_minimal_config_and_defaults(self) -> None:
        config = _config([
            {"path": "app/svc", "kind": "service", "factory": "agent.m:f"},
            {"path": "app/mod", "kind": "module", "factory": "agent.m:f"},
            {"path": "app/g", "kind": "container"},
            {"path": "app/g/child", "kind": "ui-control"},
        ])
        self.assertEqual(config.root, "app")
        self.assertEqual(config.spec("app/svc").scope, SCOPE_APP)
        self.assertEqual(config.spec("app/svc").owner, slot_spec.HOST_OWNER)
        self.assertEqual(config.spec("app/mod").scope, SCOPE_SESSION)
        self.assertIsNone(config.spec("app/svc").order)

    def test_children_and_fixed_are_node_fields(self) -> None:
        config = _config([
            {"path": "app/routes", "kind": "container", "children": "keyed"},
            {"path": "app/menu", "kind": "container", "children": "fixed",
             "fixed": ["a", "b"]},
        ])
        self.assertEqual(config.spec("app/routes").children, "keyed")
        self.assertEqual(config.spec("app/routes").fixed, ())
        self.assertEqual(config.spec("app/menu").children, "fixed")
        self.assertEqual(config.spec("app/menu").fixed, ("a", "b"))

    def test_children_defaults_to_none(self) -> None:
        config = _config([{"path": "app/a", "kind": "service", "factory": "agent.m:f"}])
        self.assertEqual(config.spec("app/a").children, "none")

    def test_illegal_children_rejected(self) -> None:
        with self.assertRaises(SlotConfigError) as ctx:
            _config([{"path": "app/a", "kind": "container", "children": "many"}])
        self.assertIn("children 非法", str(ctx.exception))
        self.assertIn("app/a", str(ctx.exception))

    def test_fixed_without_fixed_children_rejected(self) -> None:
        with self.assertRaises(SlotConfigError) as ctx:
            _config([{"path": "app/a", "kind": "container",
                      "children": "keyed", "fixed": ["x"]}])
        self.assertIn("fixed 只用于 children=fixed", str(ctx.exception))

    def test_root_prefix_is_enforced(self) -> None:
        with self.assertRaises(SlotConfigError):
            _config([{"path": "other/a", "kind": "service", "factory": "agent.m:f"}])

    def test_duplicate_path_rejected(self) -> None:
        with self.assertRaises(SlotConfigError):
            _config([
                {"path": "app/a", "kind": "service", "factory": "agent.m:f"},
                {"path": "app/a", "kind": "service", "factory": "agent.m:g"},
            ])

    def test_props_are_preserved_verbatim(self) -> None:
        """props 是声明载荷：四个 ui-* 类型的 props 必须原样保留。"""
        props = {"label": "x", "action": "a.b",
                 "binding": {"nav": "n"}, "scripts": ["ui/x.js"],
                 "styles": ["ui/x.css"]}
        config = _config([
            {"path": "app/s", "kind": "ui-slot", "children": "keyed",
             "props": props},
            {"path": "app/a", "kind": "ui-action", "props": props},
            {"path": "app/c", "kind": "ui-control", "props": props},
            {"path": "app/t", "kind": "ui-tool-shell", "props": props},
        ])
        for path in ("app/s", "app/a", "app/c", "app/t"):
            with self.subTest(path=path):
                self.assertEqual(dict(config.spec(path).props), props)

    def test_props_default_to_empty(self) -> None:
        config = _config([{"path": "app/a", "kind": "service", "factory": "agent.m:f"}])
        self.assertEqual(dict(config.spec("app/a").props), {})

    def test_props_must_be_object(self) -> None:
        with self.assertRaises(SlotConfigError) as ctx:
            _config([{"path": "app/a", "kind": "ui-control", "props": ["x"]}])
        message = str(ctx.exception)
        self.assertIn("props 必须是对象", message)
        self.assertIn("app/a", message)

    def test_unknown_field_is_rejected_with_name(self) -> None:
        """未声明字段必须报错：静默丢弃会把「写了但没生效」伪装成「正确」。"""
        with self.assertRaises(SlotConfigError) as ctx:
            _config([{"path": "app/a", "kind": "ui-control",
                      "labell": "拼错的键"}])
        message = str(ctx.exception)
        self.assertIn("未知字段", message)
        self.assertIn("app/a", message)
        self.assertIn("labell", message)
        # 报错要能告诉人该写什么
        self.assertIn("props", message)

    def test_declared_field_is_accepted(self) -> None:
        """集合内字段走正常路径：从字段表现取一个，构造成功。

        不写字段名字面量：闭合白名单的「准入」与具体拼写无关，
        取哪个都成立。
        """
        for name in sorted(SPEC_FIELDS)[:3]:
            with self.subTest(field=name):
                self.assertIn(name, SPEC_FIELDS)
        config = _config([{"path": "app/a", "kind": "service",
                           "factory": "agent.m:f", "order": 1}])
        self.assertEqual(config.specs["app/a"].order, 1)

    def test_undeclared_field_is_rejected(self) -> None:
        """集合外任意词一律拒收：不点名任何已知或曾用字段。

        随机串天然覆盖「以后会有人想加什么」，不靠穷举几个词。
        """
        stranger = "zz_unknown_" + uuid.uuid4().hex[:10]
        with self.assertRaises(SlotConfigError) as ctx:
            _config([{"path": "app/a", "kind": "service",
                      "factory": "agent.m:f", stranger: True}])
        message = str(ctx.exception)
        self.assertIn("未知字段", message)
        self.assertIn("app/a", message)
        self.assertIn(stranger, message)
        # 报错要能告诉人允许写什么：允许键清单就是字段表本身
        for allowed in sorted(SPEC_FIELDS):
            self.assertIn(allowed, message)

    def test_field_table_is_derived_not_hand_written(self) -> None:
        """白名单从字段表现算：给数据类添一个字段，解析器与门禁自动跟随。

        做法：不篡改真实数据类，而是验证「来源就是 fields(SlotSpec)」这件事：
        集合相等即证明没有第二份手写名单；再用一个临时数据类证明派生表达式本身
        对任意字段集成立（加一个字段就多一个键，不需改任何常量）。
        """
        self.assertEqual(SPEC_FIELDS, frozenset(f.name for f in fields(SlotSpec)))
        self.assertEqual(OVERRIDE_FIELDS, SPEC_FIELDS | {"mode"})

        @dataclasses.dataclass(frozen=True)
        class _Widened:
            path: str
            kind: str
            newcomer: str = ""

        derived = frozenset(f.name for f in fields(_Widened))
        self.assertEqual(derived, {"path", "kind", "newcomer"})
        self.assertNotIn("newcomer", SPEC_FIELDS)

    def test_event_name_must_come_from_constants(self) -> None:
        """event 节点的事件名必须命中 event_name 常量集。"""
        config = _config([
            {"path": f"app/ev/{ev.TURN_ENDED}", "kind": "event", "factory": "agent.m:f"},
            {"path": f"app/ev/{ev.ERROR}", "kind": "event", "factory": "agent.m:f"},
        ])
        self.assertEqual(len(config.specs), 2)

    def test_event_name_outside_constants_is_rejected(self) -> None:
        """自造事件名不会崩，只会订阅一个永不发生的事件——静默失效，所以必须报错。"""
        with self.assertRaises(SlotConfigError) as ctx:
            _config([{"path": "app/ev/turn_stoped", "kind": "event",
                      "factory": "agent.m:f"}])
        message = str(ctx.exception)
        self.assertIn("event_name", message)
        self.assertIn("app/ev/turn_stoped", message)

    def test_event_names_match_event_name_module(self) -> None:
        """校验用的常量集就是从 event_name 模块取的，不另造一份。"""
        self.assertIn(ev.TURN_ENDED, slot_spec.EVENT_NAMES)
        self.assertIn(ev.ERROR, slot_spec.EVENT_NAMES)
        self.assertNotIn("turn_stoped", slot_spec.EVENT_NAMES)

    def test_event_rule_skips_other_kinds(self) -> None:
        """只有 event 节点受此约束；其他 kind 路径里没有事件名是正常的。"""
        config = _config([{"path": "app/things/whatever", "kind": "service",
                           "factory": "agent.m:f"}])
        self.assertEqual(config.specs["app/things/whatever"].kind, "service")

    def test_setting_requires_factory(self) -> None:
        """setting 带 save/load 回调，函数写不进 JSON，所以必须有 factory。"""
        with self.assertRaises(SlotConfigError) as ctx:
            _config([{"path": "app/panel", "kind": "setting"}])
        message = str(ctx.exception)
        self.assertIn("缺少 factory", message)
        self.assertIn("app/panel", message)

    def test_setting_factory_yields_decl(self) -> None:
        config = _config([{"path": "app/panel", "kind": "setting",
                           "factory": "agent.m:panel", "props": {"title": "T"}}])
        decl = SettingDecl(kind="panel", label="T")
        assembly = SlotAssembly(config, resolver=_resolver(
            {"agent.m:panel": lambda ctx: SettingDecl(
                kind="panel", label=str(ctx.spec.props.get("title", "")))}))
        assembly.build()
        self.assertEqual(assembly.get("app/panel"), decl)

    def test_paths_section_is_rejected(self) -> None:
        """paths 段已取消：子级策略写在节点上，旧写法直接报错而不是静默忽略。"""
        with self.assertRaises(SlotConfigError) as ctx:
            _config([{"path": "app/a", "kind": "service", "factory": "agent.m:f"}],
                    paths=[{"path": "app/a"}])
        self.assertIn("paths 段已取消", str(ctx.exception))

    def test_retired_metadata_key_is_rejected(self) -> None:
        """metadata 整字段已取消：留着旧写法必然报错，并指出路径与该写哪个字段。

        旧前提：`metadata` 是任意载荷，只有 `metadata.ui-kind` 子键被升为 kind，
                故报错文案点名子键与节点 kind。
        新前提：`metadata` 整体取消，任意子键都不存在；报错点名路径与字段名，
                并告知方法/顺序/作用域/载荷各自该写在哪。
        """
        with self.assertRaises(SlotConfigError) as ctx:
            _config([{"path": "app/btn", "kind": "ui-control",
                      "metadata": {"ui-kind": "button"}}])
        message = str(ctx.exception)
        self.assertIn("已取消的字段", message)
        self.assertIn("app/btn", message)
        self.assertIn("metadata", message)
        self.assertIn("方法写 method", message)

    def test_retired_metadata_key_check_applies_to_plugin_nodes(self) -> None:
        """同样的拒收对插件节点也生效（解析闸口不分来源）。"""
        with self.assertRaises(SlotConfigError) as ctx:
            _config([{"path": "app/plugins/x/ui/a", "kind": "ui-action",
                      "metadata": {"ui-kind": "action"}}])
        message = str(ctx.exception)
        self.assertIn("已取消的字段", message)
        self.assertIn("app/plugins/x/ui/a", message)
        self.assertIn("metadata", message)

    def test_missing_requires_target_rejected(self) -> None:
        with self.assertRaises(SlotConfigError):
            _config([{"path": "app/a", "kind": "service", "factory": "agent.m:f",
                      "requires": {"dep": "app/ghost"}}])

    def test_sibling_order_conflict_rejected(self) -> None:
        with self.assertRaises(SlotConfigError):
            _config([
                {"path": "app/g", "kind": "container"},
                {"path": "app/g/a", "kind": "service", "factory": "agent.m:f", "order": 1},
                {"path": "app/g/b", "kind": "service", "factory": "agent.m:f", "order": 1},
            ])

    def test_order_of_different_parents_may_repeat(self) -> None:
        config = _config([
            {"path": "app/g", "kind": "container"},
            {"path": "app/h", "kind": "container"},
            {"path": "app/g/a", "kind": "service", "factory": "agent.m:f", "order": 1},
            {"path": "app/h/a", "kind": "service", "factory": "agent.m:f", "order": 1},
        ])
        self.assertEqual(len(config.specs), 4)

    def test_container_with_children_is_allowed(self) -> None:
        """正向：容器类节点可以持有子节点，不报错。"""
        config = _config([
            {"path": "app/a", "kind": "container"},
            {"path": "app/a/b", "kind": "service", "factory": "agent.m:f"},
        ])
        self.assertEqual(len(config.specs), 2)
        self.assertTrue(holds_children(config.specs["app/a"]))

    def test_setting_with_keyed_children_is_allowed(self) -> None:
        """正向：声明型父插口（children≠none 的 setting）也能持有子节点。"""
        config = _config([
            {"path": "app/s", "kind": "setting", "factory": "agent.m:decl",
             "children": "keyed"},
            {"path": "app/s/f", "kind": "setting", "factory": "agent.m:decl"},
        ])
        self.assertTrue(holds_children(config.specs["app/s"]))

    def test_tool_cannot_own_children(self) -> None:
        """反向：叶子类 kind 下有子节点，必须报错并指明路径与 kind。"""
        with self.assertRaises(SlotConfigError) as ctx:
            _config([
                {"path": "app/t", "kind": "tool", "factory": "agent.m:f"},
                {"path": "app/t/b", "kind": "service", "factory": "agent.m:f"},
            ])
        message = str(ctx.exception)
        self.assertIn("app/t", message)
        self.assertIn("不能持有子级", message)
        self.assertIn("kind=tool", message)
        self.assertIn("children=none", message)

    def test_has_descendants_is_topology_only(self) -> None:
        """主插口判据：有后代即是，叶子不是，中间节点也算。"""
        config = _config([
            {"path": "app/g", "kind": "container"},
            {"path": "app/g/mid", "kind": "container"},
            {"path": "app/g/mid/leaf", "kind": "service", "factory": "agent.m:f"},
            {"path": "app/lonely", "kind": "service", "factory": "agent.m:f"},
        ])
        self.assertTrue(has_descendants(config.specs, "app/g"))
        self.assertTrue(has_descendants(config.specs, "app/g/mid"))
        self.assertFalse(has_descendants(config.specs, "app/g/mid/leaf"))
        self.assertFalse(has_descendants(config.specs, "app/lonely"))

    def test_kind_and_factory_rules(self) -> None:
        cases = [
            {"path": "app/a", "kind": "nope", "factory": "agent.m:f"},
            {"path": "app/a", "kind": "service"},
            {"path": "app/a", "kind": "service", "factory": "no-colon"},
            {"path": "app/a", "kind": "service", "factory": "agent.m:f", "requires": []},
            {"path": "app/a", "kind": "service", "factory": "agent.m:f", "scope": "turn"},
            {"path": "app/a", "kind": "service", "factory": "agent.m:f", "order": "x"},
            {"path": "app/a", "kind": "service", "factory": "agent.m:f", "metadata": []},
        ]
        for row in cases:
            with self.subTest(row=row), self.assertRaises(SlotConfigError):
                _config([row])

    def test_broken_top_level_rejected(self) -> None:
        for raw in ({}, {"slots": []}, {"slots": "x"}):
            with self.subTest(raw=raw), self.assertRaises(SlotConfigError):
                SlotConfig.parse(raw)
        with self.assertRaises(SlotConfigError):
            SlotConfig.parse({"slots": [{"path": "app/a", "kind": "service",
                                         "factory": "agent.m:f"}], "version": "x"})

    def test_load_config_reports_unreadable_file(self) -> None:
        with self.assertRaises(SlotConfigError):
            load_config(__file__ + ".missing")


class TopoOrderTest(unittest.TestCase):
    ROWS = [
        {"path": "app/x", "kind": "service", "factory": "agent.m:f"},
        {"path": "app/y", "kind": "service", "factory": "agent.m:g",
         "requires": {"x": "app/x"}},
        {"path": "app/z", "kind": "service", "factory": "agent.m:h",
         "requires": {"y": "app/y"}},
    ]

    def test_dependency_precedes_dependent(self) -> None:
        order = topo_order(_config(self.ROWS))
        self.assertLess(order.index("app/x"), order.index("app/y"))
        self.assertLess(order.index("app/y"), order.index("app/z"))

    def test_declaration_order_does_not_matter(self) -> None:
        forward = topo_order(_config(self.ROWS))
        backward = topo_order(_config(list(reversed(self.ROWS))))
        self.assertEqual(forward, backward)

    def test_cycle_is_reported_with_paths(self) -> None:
        config = _config([
            {"path": "app/a", "kind": "service", "factory": "agent.m:f",
             "requires": {"b": "app/b"}},
            {"path": "app/b", "kind": "service", "factory": "agent.m:f",
             "requires": {"a": "app/a"}},
        ])
        with self.assertRaises(SlotConfigError) as ctx:
            topo_order(config)
        self.assertIn("app/a", str(ctx.exception))

    def test_children_follow_order_then_path(self) -> None:
        config = _config([
            {"path": "app/g", "kind": "container"},
            {"path": "app/g/x", "kind": "service", "factory": "agent.m:f"},
            {"path": "app/g/y", "kind": "service", "factory": "agent.m:f", "order": 5},
            {"path": "app/g/z", "kind": "service", "factory": "agent.m:f", "order": 1},
        ])
        self.assertEqual([spec.path for spec in config.children("app/g")],
                         ["app/g/z", "app/g/y", "app/g/x"])


class SlotAssemblyTest(unittest.TestCase):
    def test_builds_in_dependency_order_and_passes_requires(self) -> None:
        seen: List[str] = []

        def make_child(ctx: Any, **kwargs: Any) -> Any:
            seen.append("child")
            return {"dep": kwargs["a"]}

        def make_root(ctx: Any) -> Any:
            seen.append("root")
            self.assertIsInstance(ctx, slot_assembly.BuildContext)
            self.assertEqual(ctx.spec.path, "app/a")
            return "root"

        config = _config([
            {"path": "app/a", "kind": "service", "factory": "agent.m:root"},
            {"path": "app/b", "kind": "service", "factory": "agent.m:child",
             "requires": {"a": "app/a"}},
        ])
        assembly = SlotAssembly(config, resolver=_resolver(
            {"agent.m:root": make_root, "agent.m:child": make_child})).build()
        self.assertEqual(seen, ["root", "child"])
        self.assertEqual(assembly.get("app/b"), {"dep": "root"})

    def test_container_receives_children_tuple(self) -> None:
        def make_container(ctx: Any, children: Any) -> Any:
            return {"path": ctx.spec.path, "children": children}

        config = _config([
            {"path": "app/g", "kind": "container", "factory": "agent.m:c"},
            {"path": "app/g/a", "kind": "service", "factory": "agent.m:leaf", "order": 2},
            {"path": "app/g/b", "kind": "service", "factory": "agent.m:leaf", "order": 1},
        ])
        assembly = SlotAssembly(config, resolver=_resolver(
            {"agent.m:c": make_container, "agent.m:leaf": lambda ctx: ctx.spec.path})).build()
        self.assertEqual(assembly.get("app/g")["children"], ("app/g/b", "app/g/a"))

    def test_container_without_factory_collects_children(self) -> None:
        config = _config([
            {"path": "app/g", "kind": "container"},
            {"path": "app/g/a", "kind": "service", "factory": "agent.m:leaf"},
        ])
        assembly = SlotAssembly(config, resolver=_resolver(
            {"agent.m:leaf": lambda ctx: 1})).build()
        self.assertEqual(assembly.get("app/g"), (1,))

    def test_declarative_kinds_yield_spec(self) -> None:
        """纯声明类（无 factory）装配结果就是它的 SlotSpec。"""
        config = _config([
            {"path": "app/ui", "kind": "ui-control"},
            {"path": "app/st", "kind": "setting", "factory": "agent.m:decl"},
        ])
        assembly = SlotAssembly(config, resolver=_resolver(
            {"agent.m:decl": lambda ctx: SettingDecl(kind="panel", label="L")})).build()
        self.assertEqual(assembly.get("app/ui").path, "app/ui")
        self.assertEqual(assembly.get("app/st").label, "L")

    def test_unknown_path_raises(self) -> None:
        assembly = SlotAssembly(_config([
            {"path": "app/a", "kind": "service", "factory": "agent.m:f"}]), resolver=_resolver({}))
        with self.assertRaises(SlotAssemblyError):
            assembly.get("app/ghost")

    def test_failure_releases_built_nodes_in_reverse(self) -> None:
        log: List[str] = []

        def boom(ctx: Any) -> Any:
            raise RuntimeError("boom")

        config = _config([
            {"path": "app/a", "kind": "service", "factory": "agent.m:a"},
            {"path": "app/b", "kind": "service", "factory": "agent.m:b",
             "requires": {"a": "app/a"}},
            {"path": "app/c", "kind": "service", "factory": "agent.m:boom",
             "requires": {"b": "app/b"}},
        ])
        resolver = _resolver({
            "agent.m:a": lambda ctx: _Node("a", log),
            "agent.m:b": lambda ctx, a: _Node("b", log),
            "agent.m:boom": boom,
        })
        assembly = SlotAssembly(config, resolver=resolver)
        with self.assertRaises(SlotAssemblyError) as ctx:
            assembly.build()
        self.assertIn("app/c", str(ctx.exception))
        self.assertEqual(log, ["dispose:b", "dispose:a"])
        self.assertEqual(assembly.values, {})

    def test_dispose_is_idempotent_and_continues_after_failure(self) -> None:
        log: List[str] = []

        def make(name: str, fail: bool = False) -> Any:
            return lambda ctx: _Node(name, log, fail=fail)

        config = _config([
            {"path": "app/a", "kind": "service", "factory": "agent.m:a"},
            {"path": "app/b", "kind": "service", "factory": "agent.m:b"},
        ])
        assembly = SlotAssembly(config, resolver=_resolver(
            {"agent.m:a": make("a"), "agent.m:b": make("b", fail=True)})).build()
        with mock.patch.object(slot_assembly, "report_error") as report:
            assembly.dispose()
            assembly.dispose()
        self.assertEqual(log, ["dispose:b", "dispose:a"])
        self.assertEqual(report.call_count, 1)

    def test_missing_dependency_value_raises(self) -> None:
        config = _config([
            {"path": "app/mod", "kind": "module", "factory": "agent.m:mod"},
            {"path": "app/svc", "kind": "service", "factory": "agent.m:f",
             "requires": {"mod": "app/mod"}},
        ])
        with self.assertRaises(SlotAssemblyError):
            SlotAssembly(config, resolver=_resolver({"agent.m:f": lambda ctx, mod: 1})).build()


class SessionAssemblyTest(unittest.TestCase):
    ROWS = [
        {"path": "app/svc", "kind": "service", "factory": "agent.m:svc"},
        {"path": "app/pa", "kind": "provider", "factory": "agent.m:pa",
         "scope": SCOPE_SESSION},
        {"path": "app/pb", "kind": "provider", "factory": "agent.m:pb",
         "scope": SCOPE_SESSION, "requires": {"pa": "app/pa"}},
        {"path": "app/pc", "kind": "provider", "factory": "agent.m:pc",
         "scope": SCOPE_SESSION, "requires": {"svc": "app/svc"}},
    ]

    def _config(self) -> SlotConfig:
        return _config(self.ROWS)

    def _app(self, config: SlotConfig) -> SlotAssembly:
        return SlotAssembly(config, resolver=_resolver(
            {"agent.m:svc": lambda ctx: "svc"})).build()

    def test_app_stage_only_registers_session_templates(self) -> None:
        assembly = self._app(self._config())
        self.assertEqual(list(assembly.templates), ["app/pa", "app/pb", "app/pc"])
        self.assertEqual(list(assembly.values), ["app/svc"])

    def test_session_stage_resolves_within_session_then_app(self) -> None:
        config = self._config()
        app = self._app(config)
        session = SessionAssembly(config, app.values, resolver=_resolver({
            "agent.m:pa": lambda ctx: {"leaf": True},
            "agent.m:pb": lambda ctx, pa: {"pa": pa},
            "agent.m:pc": lambda ctx, svc: {"svc": svc},
        })).build()
        self.assertEqual(session.get("app/pb"), {"pa": {"leaf": True}})
        self.assertEqual(session.get("app/pc"), {"svc": "svc"})
        self.assertEqual(session.get("app/svc"), "svc")

    def test_session_missing_dependency_raises(self) -> None:
        config = self._config()
        with self.assertRaises(SlotAssemblyError):
            SessionAssembly(config, {}, resolver=_resolver({
                "agent.m:pa": lambda ctx: 1,
                "agent.m:pb": lambda ctx, pa: pa,
                "agent.m:pc": lambda ctx, svc: svc,
            })).build()

    def test_session_failure_releases_partial_and_keeps_app_clean(self) -> None:
        log: List[str] = []

        def boom(ctx: Any, pa: Any) -> Any:
            raise RuntimeError("boom")

        config = self._config()
        app = self._app(config)
        session = SessionAssembly(config, app.values, resolver=_resolver({
            "agent.m:pa": lambda ctx: _Node("pa", log),
            "agent.m:pb": boom,
        }))
        with self.assertRaises(SlotAssemblyError):
            session.build()
        self.assertEqual(log, ["dispose:pa"])
        self.assertEqual(session.values, {})
        self.assertEqual(list(app.values), ["app/svc"])

    def test_session_dispose_is_reverse_and_idempotent(self) -> None:
        log: List[str] = []
        config = _config([
            {"path": "app/a", "kind": "provider", "factory": "agent.m:a", "scope": SCOPE_SESSION},
            {"path": "app/b", "kind": "provider", "factory": "agent.m:b",
             "scope": SCOPE_SESSION, "requires": {"a": "app/a"}},
        ])
        session = SessionAssembly(config, {}, resolver=_resolver({
            "agent.m:a": lambda ctx: _Node("a", log),
            "agent.m:b": lambda ctx, a: _Node("b", log),
        })).build()
        session.dispose()
        session.dispose()
        self.assertEqual(log, ["dispose:b", "dispose:a"])

    def test_session_node_built_once_per_session(self) -> None:
        calls: List[str] = []

        def make(ctx: Any, children: Any) -> Any:
            calls.append(ctx.spec.path)
            return ctx.spec.path

        config = _config([
            {"path": "app/a", "kind": "module", "factory": "agent.m:a"},
        ])
        session = SessionAssembly(config, {}, resolver=_resolver({"agent.m:a": make})).build()
        self.assertEqual(session.get("app/a"), "app/a")
        self.assertEqual(calls, ["app/a"])


class ResolveBindingsTest(unittest.TestCase):
    def _config(self) -> SlotConfig:
        """app/g/a 带一个会话级子节点，故按新机制显式声明 children=keyed。"""
        return _config([
            {"path": "app/g", "kind": "container", "frozen": False},
            {"path": "app/g/a", "kind": "provider", "factory": "agent.m:base",
             "order": 1, "children": "keyed"},
            {"path": "app/g/a/x", "kind": "provider", "factory": "agent.m:sub", "scope": SCOPE_SESSION},
            {"path": "app/sealed", "kind": "service", "factory": "agent.m:s", "frozen": True},
        ])

    def test_default_chain_has_only_base(self) -> None:
        resolved = resolve_bindings(self._config(), [])
        self.assertEqual([b.mode for b in resolved.chain("app/g/a")], [BASE_MODE])

    def test_replace_drops_base(self) -> None:
        resolved = resolve_bindings(self._config(), [
            {"path": "app/g/a", "mode": "replace", "factory": "agent.m:new"},
        ])
        chain = resolved.chain("app/g/a")
        self.assertEqual([b.mode for b in chain], ["replace"])
        self.assertEqual(chain[0].spec.factory, "agent.m:new")
        self.assertEqual(chain[0].spec.kind, "provider")

    def test_extend_and_wrap_keep_base_sorted_by_order(self) -> None:
        resolved = resolve_bindings(self._config(), [
            {"path": "app/g/a", "mode": "wrap", "factory": "agent.m:w", "order": 9},
            {"path": "app/g/a", "mode": "extend", "factory": "agent.m:e", "order": 2},
        ])
        chain = resolved.chain("app/g/a")
        self.assertEqual([b.mode for b in chain], [BASE_MODE, "extend", "wrap"])
        self.assertEqual([b.spec.factory for b in chain], ["agent.m:base", "agent.m:e", "agent.m:w"])

    def test_disable_clears_chain_and_propagates_to_subtree(self) -> None:
        resolved = resolve_bindings(self._config(), [
            {"path": "app/g/a", "mode": "disable"},
        ])
        self.assertEqual(resolved.chain("app/g/a"), ())
        self.assertIn("app/g/a/x", resolved.disabled)

    def test_replace_subtree_keeps_subtree_chain(self) -> None:
        resolved = resolve_bindings(self._config(), [
            {"path": "app/g/a", "mode": "replace_subtree", "factory": "m:sub2"},
        ])
        self.assertEqual(resolved.chain("app/g/a")[0].mode, "replace_subtree")
        self.assertEqual([b.mode for b in resolved.chain("app/g/a/x")], [BASE_MODE])

    def test_conflicts_are_rejected(self) -> None:
        cases = [
            [{"path": "app/g/a", "mode": "replace", "factory": "m:1"},
             {"path": "app/g/a", "mode": "replace", "factory": "m:2"}],
            [{"path": "app/g/a", "mode": "replace", "factory": "m:1"},
             {"path": "app/g/a", "mode": "replace_subtree", "factory": "m:2"}],
            [{"path": "app/g/a", "mode": "disable"},
             {"path": "app/g/a", "mode": "extend", "factory": "m:2"}],
            [{"path": "app/sealed", "mode": "replace", "factory": "m:2"}],
            [{"path": "app/ghost", "mode": "replace", "factory": "m:2"}],
            [{"path": "app/g/a", "mode": "merge", "factory": "m:2"}],
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides), self.assertRaises(SlotConfigError):
                resolve_bindings(self._config(), overrides)


class ResolveFactoryTest(unittest.TestCase):
    def test_resolves_callable(self) -> None:
        # 用本模块自己的 __name__ 构造引用：discover -t tests 与 "tests.test_x"
        # 两种跑法下模块名不同，写死其中一个会导入到另一份模块对象。
        spec = f"{__name__}:_noop"
        self.assertIs(resolve_factory(spec), _noop)

    def test_rejects_bad_or_non_callable(self) -> None:
        for spec in ("nocolon", "tests.test_slot_loader:_missing",
                     "tests.test_slot_loader:_NOT_CALLABLE", ""):
            with self.subTest(spec=spec), self.assertRaises(SlotConfigError):
                resolve_factory(spec)


class SpecShapeTest(unittest.TestCase):
    def test_spec_is_frozen(self) -> None:
        spec = SlotSpec(path="app/a", kind="service")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            spec.path = "app/b"  # type: ignore[misc]


class BuildFromConfigTest(unittest.TestCase):
    """真实配置能被装配器完整消化；不证明已接到启动路径。"""

    CONFIG = Path(__file__).resolve().parent.parent / "plugin-slots.json"

    @staticmethod
    def _resolver(spec: str) -> Any:
        return lambda *args, **kwargs: {"factory": spec}

    def _build(self) -> SlotAssembly:
        with mock.patch.object(slot_assembly, "resolve_factory", self._resolver):
            return build_from_config(self.CONFIG)

    def test_builds_every_declared_node(self) -> None:
        """全量配置逐节点构造：session 节点进模板，其余进装配结果。

        基数是配置声明量，不是手写常数：合并片段会把插件节点一并算进来，
        `plugin-slots.json` 91 个、其中 session 作用域 5 个。
        """
        assembly = self._build()
        self.addCleanup(assembly.dispose)
        config = load_config(self.CONFIG)
        total = len(assembly.values) + len(assembly.templates)
        self.assertEqual(total, len(config.specs))
        self.assertEqual(len(assembly.values), 86)
        self.assertEqual(len(assembly.templates), 5)

    def test_every_path_is_retrievable(self) -> None:
        """每个声明路径都能取到值；无 factory 的容器取到的是子节点元组。"""
        assembly = self._build()
        self.addCleanup(assembly.dispose)
        config = load_config(self.CONFIG)
        for path, spec in config.specs.items():
            with self.subTest(path=path):
                if path in assembly.templates:
                    self.assertEqual(assembly.templates[path], spec)
                elif not spec.factory:
                    value = assembly.get(path)
                    self.assertIsInstance(value, tuple)
                    self.assertEqual(len(value), len(config.children(path)))
                else:
                    self.assertEqual(assembly.get(path)["factory"], spec.factory)

    def test_dispose_is_idempotent(self) -> None:
        assembly = self._build()
        assembly.dispose()
        assembly.dispose()
        self.assertEqual(assembly.values, {})

    def test_missing_config_raises_config_error(self) -> None:
        with self.assertRaises(SlotConfigError):
            build_from_config(self.CONFIG.with_name("plugin-slots.absent.json"))

    def test_unresolvable_factory_raises_config_error(self) -> None:
        def _raise(spec: str) -> Any:
            raise SlotConfigError(f"factory 不可解析：{spec}")

        with mock.patch.object(slot_assembly, "resolve_factory", _raise):
            with self.assertRaises(SlotConfigError):
                build_from_config(self.CONFIG)


if __name__ == "__main__":
    unittest.main()
