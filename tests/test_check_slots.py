# -*- coding: utf-8 -*-
"""插口配置门禁：factory 两条写法、可解析性与入口行为的用例。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.core.slot_config import SlotConfig  # noqa: E402
from agent.core.slot_spec import (  # noqa: E402
    SlotConfigError,
    SlotSpec,
)
from scripts import check_slots  # noqa: E402

_PLUGIN_PATH = "app/plugins/knowledge/prompt/messages/knowledge"


def _config(rows: List[Dict[str, Any]]) -> SlotConfig:
    return SlotConfig.parse({"version": 1, "root": "app", "slots": rows})


def _mixed_rows() -> List[Dict[str, Any]]:
    """两个宿主工厂（一个重复）、一个抛错、一个不可调用、两个插件工厂。"""
    return [
        {"path": "app/a", "kind": "service", "factory": "agent.x:make_a"},
        {"path": "app/b", "kind": "service", "factory": "agent.x:make_a"},
        {"path": "app/c", "kind": "service", "factory": "agent.x:boom"},
        {"path": "app/d", "kind": "service", "factory": "agent.x:not_callable"},
        {"path": _PLUGIN_PATH, "kind": "provider", "factory": "plugin:lines"},
        {"path": "app/plugins/knowledge/x", "kind": "provider",
         "factory": "components:make"},
    ]


def _write(payload: Dict[str, Any]) -> Path:
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(payload, handle, ensure_ascii=False)
    handle.close()
    return Path(handle.name)


class FactoryShapeTest(unittest.TestCase):
    def test_host_form_is_accepted_on_any_path(self) -> None:
        cases = [("agent.boot.components:container", ""),
                 ("agent.boot.host_factories:make_plugin_host", ""),
                 ("agent.core.modules.slot_chain:input_module", _PLUGIN_PATH)]
        for spec, path in cases:
            with self.subTest(spec=spec, path=path):
                self.assertEqual(check_slots.factory_shape(spec, path), "")

    def test_plugin_form_is_accepted_under_plugin_path(self) -> None:
        for spec in ("plugin:knowledge_lines", "components:make_example",
                     "sub.tools:make_tool"):
            with self.subTest(spec=spec):
                self.assertEqual(
                    check_slots.factory_shape(spec, _PLUGIN_PATH), "")

    def test_plugin_form_is_rejected_outside_plugin_path(self) -> None:
        for path in ("", "app/host/services/x", "app/kernel/modules/input"):
            with self.subTest(path=path):
                reason = check_slots.factory_shape("plugin:knowledge_lines", path)
                self.assertIn("app/plugins/", reason)

    def test_rejects_plugins_prefix(self) -> None:
        reason = check_slots.factory_shape(
            "plugins.knowledge.plugin:knowledge_lines", _PLUGIN_PATH)
        self.assertIn("plugins.", reason)

    def test_rejects_slash_and_py(self) -> None:
        for spec, keyword in (
                ("plugins/knowledge/plugin.py:knowledge_lines", "路径分隔符"),
                ("knowledge/plugin:fn", "路径分隔符"),
                ("plugin.py:knowledge_lines", ".py"),
                ("knowledge\\plugin:fn", "路径分隔符"),
        ):
            with self.subTest(spec=spec):
                reason = check_slots.factory_shape(spec, _PLUGIN_PATH)
                self.assertNotEqual(reason, "")
                self.assertIn(keyword, reason)

    def test_rejects_malformed_forms(self) -> None:
        cases = {
            "": "module:attr",
            "nocolon": "module:attr",
            "agent.boot:": "为空",
            ":attr": "为空",
            "agent.boot:a:b": "冒号",
            "agent..boot:fn": "点分",
            "agent.boot:2bad": "标识符",
            "agent.boot:fn()": "标识符",
        }
        for spec, keyword in cases.items():
            with self.subTest(spec=spec):
                reason = check_slots.factory_shape(spec)
                self.assertNotEqual(reason, "")
                self.assertIn(keyword, reason)

    def test_missing_factory_is_left_to_loader_validation(self) -> None:
        """缺 factory 由 SlotConfig.parse 拦下，门禁不再重复判。"""
        with self.assertRaises(SlotConfigError):
            _config([{"path": "app/svc", "kind": "service"}])

    def test_factory_shapes_skips_declarative_and_container(self) -> None:
        config = _config([
            {"path": "app/ui", "kind": "ui-control"},
            {"path": "app/g", "kind": "container"},
        ])
        self.assertEqual(check_slots.factory_shapes(config), [])

    def test_factory_shapes_uses_node_path(self) -> None:
        """factory_shapes 自带路径判据；绕过 parse 直接构造才能单独测这一层。"""
        rows = [
            SlotSpec(path="app/svc", kind="service", factory="plugin:fn"),
            SlotSpec(path=_PLUGIN_PATH, kind="provider", factory="plugin:fn"),
        ]
        config = SlotConfig(root="app", version=1,
                            specs={spec.path: spec for spec in rows})
        problems = check_slots.factory_shapes(config)
        self.assertEqual(len(problems), 1)
        self.assertIn("app/svc", problems[0])

    def test_static_fragment_must_not_hold_plugin_paths(self) -> None:
        """静态片段出现 app/plugins/ 路径即报错（§2.14 与 §9 铁律项）。"""
        config = _config([
            {"path": _PLUGIN_PATH, "kind": "provider", "factory": "plugin:fn"},
        ])
        problems = check_slots.static_paths(config)
        self.assertEqual(len(problems), 1)
        self.assertIn("静态片段不应包含插件路径", problems[0])
        self.assertIn(_PLUGIN_PATH, problems[0])

    def test_static_fragment_without_plugin_paths_is_clean(self) -> None:
        config = _config([
            {"path": "app/host/services/bus", "kind": "service",
             "factory": "agent.x:bus"},
        ])
        self.assertEqual(check_slots.static_paths(config), [])

    def test_is_host_factory_and_is_plugin_path(self) -> None:
        self.assertTrue(check_slots.is_host_factory("agent.x:fn"))
        self.assertFalse(check_slots.is_host_factory("plugin:fn"))
        self.assertTrue(check_slots.is_plugin_path(_PLUGIN_PATH))
        self.assertFalse(check_slots.is_plugin_path("app/host/services/x"))


class ResolvableTest(unittest.TestCase):
    def test_missing_and_non_callable_are_reported(self) -> None:
        def importer(spec: str) -> Any:
            if spec.endswith(":boom"):
                raise AttributeError("no such attr")
            if spec.endswith(":not_callable"):
                return 42
            return lambda *a, **k: None

        problems, checked, skipped = check_slots.resolvable(
            _config(_mixed_rows()), importer)
        self.assertEqual(len(problems), 2)
        self.assertTrue(any("app/c" in line and "无法解析" in line
                            for line in problems))
        self.assertTrue(any("app/d" in line and "不可调用" in line
                            for line in problems))
        self.assertEqual(len(checked), 3)
        self.assertEqual(sorted(skipped), ["components:make", "plugin:lines"])

    def test_plugin_factory_is_skipped_not_failed(self) -> None:
        calls: List[str] = []

        def importer(spec: str) -> Any:
            calls.append(spec)
            return lambda *a, **k: None

        problems, _checked, skipped = check_slots.resolvable(
            _config(_mixed_rows()), importer)
        self.assertEqual(problems, [])
        self.assertEqual(len(skipped), 2)
        self.assertNotIn("plugin:lines", calls)

    def test_same_factory_is_resolved_once(self) -> None:
        calls: List[str] = []

        def importer(spec: str) -> Any:
            calls.append(spec)
            return lambda *a, **k: None

        _problems, _checked, _skipped = check_slots.resolvable(
            _config(_mixed_rows()), importer)
        self.assertEqual(calls.count("agent.x:make_a"), 1)


class MergedCheckTest(unittest.TestCase):
    """合并路径校验：插件片段里的空壳、坏 factory、坏 requires 必须被门禁抓到。"""

    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory(prefix="chkmerged-")
        self.addCleanup(self._dir.cleanup)
        self.root = Path(self._dir.name)
        self.write("plugin-slots.json", {"version": 1, "root": "app", "slots": [
            {"path": "app/host", "kind": "container"},
        ]})

    def write(self, rel: str, payload: Dict[str, Any]) -> None:
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def config_path(self) -> Path:
        return self.root / "plugin-slots.json"

    def test_plugin_shell_node_is_reported(self) -> None:
        """插件片段里的空壳节点：check() 必须返回非空且含该路径。"""
        self.write("plugins/alpha/plugin-slots.json", {
            "version": 1, "root": "app", "slots": [
                {"path": "app/plugins/alpha/set/a", "kind": "setting"},
            ]})
        problems = check_slots.check(self.config_path())
        self.assertTrue(problems, "合并路径的空壳节点没有被报出")
        joined = "\n".join(problems)
        self.assertIn("app/plugins/alpha/set/a", joined)
        self.assertIn("节点缺少 factory", joined)

    def test_merged_problems_reports_origin_fragment(self) -> None:
        """报错要能看出问题来自哪个片段。"""
        self.write("plugins/beta/plugin-slots.json", {
            "version": 1, "root": "app", "slots": [
                {"path": "app/plugins/beta/tool", "kind": "tool",
                 "factory": "tools:build", "requires": {"ghost": "app/ghost"}},
            ]})
        problems = check_slots.merged_problems(self.root)
        joined = "\n".join(problems)
        self.assertIn("app/ghost", joined)
        self.assertIn("beta", joined)

    def test_clean_merged_repo_passes(self) -> None:
        self.write("plugins/gamma/plugin-slots.json", {
            "version": 1, "root": "app", "slots": [
                {"path": "app/plugins/gamma/tool", "kind": "tool",
                 "factory": "tools:build"},
            ]})
        self.assertEqual(check_slots.merged_problems(self.root), [])

    def test_missing_static_fragment_is_reported(self) -> None:
        empty = self.root / "nowhere"
        empty.mkdir()
        problems = check_slots.merged_problems(empty)
        self.assertEqual(len(problems), 1)
        self.assertIn("静态片段不存在", problems[0])


class CheckEntryTest(unittest.TestCase):
    def test_static_check_does_not_import(self) -> None:
        """默认路径不得触发真实导入：factory 指向不存在的模块也应通过。"""
        path = _write({"version": 1, "root": "app", "slots": [
            {"path": "app/a", "kind": "service",
             "factory": "agent.absent_module:make_a"},
        ]})
        self.addCleanup(path.unlink)
        self.assertEqual(check_slots.check(path, merged=False), [])

    def test_resolve_switch_reports_unresolvable(self) -> None:
        path = _write({"version": 1, "root": "app", "slots": [
            {"path": "app/a", "kind": "service",
             "factory": "agent.absent_module:make_a"},
        ]})
        self.addCleanup(path.unlink)
        problems = check_slots.check(path, resolve=True, merged=False)
        self.assertEqual(len(problems), 1)
        self.assertIn("无法解析", problems[0])

    def test_resolve_does_not_fail_on_plugin_factory(self) -> None:
        """--resolve 不把插件实现当失败（仅跳过）；静态片段含插件路径另计。"""
        path = _write({"version": 1, "root": "app", "slots": [
            {"path": _PLUGIN_PATH, "kind": "provider", "factory": "plugin:lines"},
        ]})
        self.addCleanup(path.unlink)
        problems = check_slots.check(path, resolve=True, merged=False)
        self.assertFalse(any("无法解析" in line for line in problems))
        self.assertTrue(any("静态片段不应包含插件路径" in line
                            for line in problems))

    def test_missing_file_is_reported(self) -> None:
        problems = check_slots.check(ROOT / "plugin-slots.absent.json")
        self.assertEqual(len(problems), 1)
        self.assertIn("配置不存在", problems[0])

    def test_main_returns_zero_on_repo_config(self) -> None:
        self.assertEqual(check_slots.main([]), 0)

    def test_main_resolve_reports_plugin_skips(self) -> None:
        self.assertEqual(check_slots.main(["--resolve"]), 0)


if __name__ == "__main__":
    unittest.main()
