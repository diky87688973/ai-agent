# -*- coding: utf-8 -*-
"""片段合并：静态片段 + 插件片段 → 一棵配置；五类冲突与来源文案。"""
from __future__ import annotations

import ast
import collections
import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.core import event_name as ev  # noqa: E402
from agent.core import slot_fragments, slot_spec  # noqa: E402
from agent.core.slot_config import topo_order  # noqa: E402
from agent.core.slot_fragments import PLUGIN_PATH_ROOT, load_merged  # noqa: E402
from agent.core.slot_spec import (  # noqa: E402
    HOST_OWNER,
    SlotConfigError,
    SlotSpec,
)

_STATIC = {
    "version": 1,
    "root": "app",
    "slots": [
        {"path": "app/host", "kind": "container"},
        {"path": "app/host/services", "kind": "container"},
        {"path": "app/host/services/bus", "kind": "service",
         "factory": "agent.x:bus"},
        {"path": "app/boot", "kind": "container"},
        {"path": "app/boot/facade", "kind": "service",
         "factory": "agent.x:facade"},
        {"path": "app/host/services/context_sources", "kind": "service",
         "factory": "agent.x:sources"},
        {"path": "app/host/services/live_state", "kind": "service",
         "factory": "agent.x:live"},
        {"path": "app/auth", "kind": "container", "factory": "agent.x:auth",
         "frozen": True},
        {"path": "app/routes", "kind": "container",
         "children": "keyed"},
        {"path": "app/menu", "kind": "container",
         "children": "fixed", "fixed": ["a", "b"]},
        {"path": "app/closed", "kind": "container"},
    ],
}


def _plugin_slots(name: str, extra: Optional[List[Dict[str, Any]]] = None
                  ) -> Dict[str, Any]:
    rows = [{"path": f"{PLUGIN_PATH_ROOT}{name}/tools/{name}",
             "kind": "tool", "factory": "tools:build", "order": 0}]
    rows.extend(extra or [])
    return {"version": 1, "root": "app", "slots": rows}


class _Repo:
    """临时仓库：写静态片段、若干插件片段与 plugins.ini。"""

    def __init__(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.root = Path(self._dir.name)

    def cleanup(self) -> None:
        self._dir.cleanup()

    def write_json(self, rel: str, payload: Dict[str, Any]) -> None:
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def write_ini(self, text: str) -> None:
        (self.root / "plugins.ini").write_text(text, encoding="utf-8")

    def plugin(self, name: str, extra: Optional[List[Dict[str, Any]]] = None) -> None:
        self.write_json(f"plugins/{name}/plugin-slots.json",
                        _plugin_slots(name, extra))


class MergeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = _Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write_json("plugin-slots.json", _STATIC)

    def merge(self) -> Any:
        return load_merged(self.repo.root)

    def test_static_only(self) -> None:
        config = self.merge()
        self.assertEqual(len(config.specs), len(_STATIC["slots"]))
        self.assertTrue(all(label.startswith("静态片段")
                            for label in config.sources.values()))

    def test_empty_subagent_tools_differs_from_absent(self) -> None:
        """声明为空与未声明是两回事：[] 入字典，缺键则不入。"""
        self.repo.plugin("empty")
        self.repo.plugin("silent")
        empty_file = self.repo.root / "plugins" / "empty" / "plugin-slots.json"
        payload = json.loads(empty_file.read_text(encoding="utf-8"))
        payload["subagent_tools"] = []
        empty_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        config = self.merge()
        self.assertEqual(config.subagent_tools.get("empty"), ())
        self.assertNotIn("silent", config.subagent_tools)

    def test_plugin_fragment_is_collected_with_owner(self) -> None:
        self.repo.plugin("alpha")
        config = self.merge()
        path = f"{PLUGIN_PATH_ROOT}alpha/tools/alpha"
        self.assertIn(path, config.specs)
        self.assertEqual(config.specs[path].owner, "alpha")
        self.assertIn("alpha", config.sources[path])

    def test_shell_node_without_factory_is_rejected(self) -> None:
        """合并路径也必须拦下空壳节点，否则「声明了但没实现」会一路上线。"""
        self.repo.plugin("alpha", [{"path": f"{PLUGIN_PATH_ROOT}alpha/set/a",
                                    "kind": "setting"}])
        with self.assertRaises(SlotConfigError) as caught:
            self.merge()
        message = str(caught.exception)
        self.assertIn(f"{PLUGIN_PATH_ROOT}alpha/set/a", message)
        self.assertIn("节点缺少 factory", message)

    def test_bad_factory_shape_is_rejected_after_merge(self) -> None:
        """factory 形状校验同样要对成品配置生效。"""
        self.repo.plugin("alpha", [{"path": f"{PLUGIN_PATH_ROOT}alpha/set/b",
                                    "kind": "service", "factory": "nodots"}])
        with self.assertRaises(SlotConfigError) as caught:
            self.merge()
        self.assertIn("factory 必须是 module:attr", str(caught.exception))

    def test_plugin_can_require_static_node(self) -> None:
        self.repo.plugin("alpha", [{
            "path": f"{PLUGIN_PATH_ROOT}alpha/tools/html",
            "kind": "tool", "factory": "tools:html", "order": 1,
            "requires": {"bus": "app/host/services/bus"},
        }])
        config = self.merge()
        self.assertEqual(
            config.specs[f"{PLUGIN_PATH_ROOT}alpha/tools/html"].requires,
            {"bus": "app/host/services/bus"})

    def test_plugin_without_fragment_is_ignored(self) -> None:
        (self.repo.root / "plugins" / "bare").mkdir(parents=True)
        config = self.merge()
        self.assertEqual(len(config.specs), len(_STATIC["slots"]))

    def test_disabled_plugin_fragment_is_skipped(self) -> None:
        self.repo.plugin("alpha")
        self.repo.plugin("beta")
        self.repo.write_ini("[plugin:alpha]\nenabled = 1\n\n"
                            "[plugin:beta]\nenabled = 0\n")
        config = self.merge()
        self.assertIn(f"{PLUGIN_PATH_ROOT}alpha/tools/alpha", config.specs)
        self.assertNotIn(f"{PLUGIN_PATH_ROOT}beta/tools/beta", config.specs)

    def test_missing_enabled_key_counts_as_enabled(self) -> None:
        self.repo.plugin("alpha")
        self.repo.write_ini("[plugin:alpha]\n")
        self.assertIn(f"{PLUGIN_PATH_ROOT}alpha/tools/alpha", self.merge().specs)


class MergeConflictTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = _Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write_json("plugin-slots.json", _STATIC)

    def assert_conflict(self, *needles: str, aggregated: bool = True) -> None:
        with self.assertRaises(SlotConfigError) as ctx:
            load_merged(self.repo.root)
        message = str(ctx.exception)
        if aggregated:
            self.assertIn("片段合并冲突", message)
        for needle in needles:
            self.assertIn(needle, message)

    def test_duplicate_path_within_one_fragment(self) -> None:
        """同一片段内重复声明同一条 path，报出两处。"""
        self.repo.write_json("plugins/alpha/plugin-slots.json", {
            "version": 1, "root": "app",
            "slots": [
                {"path": f"{PLUGIN_PATH_ROOT}alpha/tools/a", "kind": "tool",
                 "factory": "tools:a"},
                {"path": f"{PLUGIN_PATH_ROOT}alpha/tools/a", "kind": "tool",
                 "factory": "tools:b"},
            ],
        })
        self.assert_conflict("路径重复", f"{PLUGIN_PATH_ROOT}alpha/tools/a")

    def test_order_conflict_in_same_parent(self) -> None:
        """同一父节点下两个节点占同一个 order。"""
        self.repo.write_json("plugins/alpha/plugin-slots.json", {
            "version": 1, "root": "app",
            "slots": [
                {"path": f"{PLUGIN_PATH_ROOT}alpha/tools/a", "kind": "tool",
                 "factory": "tools:a", "order": 0},
                {"path": f"{PLUGIN_PATH_ROOT}alpha/tools/b", "kind": "tool",
                 "factory": "tools:b", "order": 0},
            ],
        })
        self.assert_conflict("同层 order 重复", "order=0", "alpha")

    def test_dangling_requires_names_source(self) -> None:
        self.repo.plugin("alpha", [{
            "path": f"{PLUGIN_PATH_ROOT}alpha/tools/x",
            "kind": "tool", "factory": "tools:x", "order": 1,
            "requires": {"bus": "app/host/services/ghost"},
        }])
        self.assert_conflict("依赖不存在", "app/host/services/ghost", "alpha")

    def test_plugin_fragment_cannot_reach_static_path(self) -> None:
        """插件片段写静态路径：路径不在本插件可声明范围内，报出路径与插件名。"""
        self.repo.write_json("plugins/alpha/plugin-slots.json", {
            "version": 1, "root": "app",
            "slots": [{"path": "app/host/services/bus", "kind": "service",
                       "factory": "agent.y:bus"}],
        })
        self.assert_conflict("缺少归属授权", "app/host/services/bus",
                             "不在 alpha 的可声明范围内")

    def test_frozen_subtree_check(self) -> None:
        """冻结子树的跨片段侵占由 _frozen_overrides 判定。

        插件片段被自身前缀限制，跨片段侵占在现行规则下不可达；
        这里直接驱动判定函数，证明它存在且同时报出两处来源。
        """
        specs = {
            "app/auth": SlotSpec(path="app/auth", kind="container",
                                 factory="agent.x:auth", frozen=True),
            "app/auth/inner": SlotSpec(path="app/auth/inner", kind="service",
                                        factory="agent.y:x"),
        }
        sources = {"app/auth": "静态片段", "app/auth/inner": "插件片段 alpha"}
        problems = slot_fragments._frozen_overrides(specs, sources)
        self.assertEqual(len(problems), 1)
        self.assertIn("冻结节点被覆盖", problems[0])
        self.assertIn("静态片段", problems[0])
        self.assertIn("插件片段 alpha", problems[0])

    def test_same_fragment_child_of_frozen_is_allowed(self) -> None:
        """同一片段内冻结节点带子节点不算被覆盖。"""
        specs = {
            "app/plugins/alpha": SlotSpec(path="app/plugins/alpha",
                                          kind="container", frozen=True),
            "app/plugins/alpha/tools": SlotSpec(
                path="app/plugins/alpha/tools", kind="container"),
        }
        sources = {path: "插件片段 alpha" for path in specs}
        self.assertEqual(slot_fragments._frozen_overrides(specs, sources), [])

    def test_plugin_fragment_out_of_own_prefix(self) -> None:
        """声明另一个插件前缀下的路径：没有授权，报出路径与插件名。"""
        self.repo.write_json("plugins/alpha/plugin-slots.json", {
            "version": 1, "root": "app",
            "slots": [{"path": "app/plugins/beta/tools/x", "kind": "tool",
                       "factory": "tools:x"}],
        })
        self.assert_conflict("缺少归属授权", "app/plugins/beta/tools/x",
                             "不在 alpha 的可声明范围内")

    def test_missing_static_fragment(self) -> None:
        with self.assertRaises(SlotConfigError) as ctx:
            load_merged(self.repo.root / "gone")
        self.assertIn("静态片段不存在", str(ctx.exception))

    def test_paths_section_in_fragment_is_rejected(self) -> None:
        """片段里出现 paths 段直接报错，并带上来源。"""
        self.repo.write_json("plugins/alpha/plugin-slots.json", {
            "version": 1, "root": "app",
            "slots": [{"path": f"{PLUGIN_PATH_ROOT}alpha/tools/a",
                       "kind": "tool", "factory": "tools:a"}],
            "paths": [{"path": "backend/routes", "children": "keyed"}],
        })
        with self.assertRaises(SlotConfigError) as ctx:
            load_merged(self.repo.root)
        message = str(ctx.exception)
        self.assertIn("paths 段已取消", message)
        self.assertIn("alpha", message)


class ProvidesTest(unittest.TestCase):
    """provides 的父插口判定：只看父节点自己的 children。"""

    def setUp(self) -> None:
        self.repo = _Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write_json("plugin-slots.json", _STATIC)

    def provide(self, path: str) -> None:
        self.repo.write_json("plugins/alpha/plugin-slots.json", {
            "version": 1, "root": "app",
            "slots": [{"path": f"{PLUGIN_PATH_ROOT}alpha/tools/alpha",
                       "kind": "tool", "factory": "tools:build", "order": 0}],
            "provides": [{"path": path, "kind": "ui-control",
                          "props": {"label": "x"}}],
        })

    def test_keyed_parent_accepts_contribution(self) -> None:
        """父节点 children=keyed：贡献被接受，owner 取父插口（宿主）。"""
        self.provide("app/routes/alpha_entry")
        config = load_merged(self.repo.root)
        spec = config.specs["app/routes/alpha_entry"]
        self.assertEqual(spec.owner, HOST_OWNER)
        self.assertEqual(spec.kind, "ui-control")

    def test_none_parent_rejects_contribution(self) -> None:
        """父节点存在但 children=none：报不接受贡献，并指明父路径。"""
        self.provide("app/closed/alpha_entry")
        with self.assertRaises(SlotConfigError) as ctx:
            load_merged(self.repo.root)
        message = str(ctx.exception)
        self.assertIn("父插口不接受贡献", message)
        self.assertIn("app/closed", message)
        self.assertIn("children=none", message)

    def test_fixed_parent_accepts_listed_child_only(self) -> None:
        self.provide("app/menu/a")
        self.assertIn("app/menu/a", load_merged(self.repo.root).specs)

    def test_fixed_parent_rejects_unlisted_child(self) -> None:
        self.provide("app/menu/z")
        with self.assertRaises(SlotConfigError) as ctx:
            load_merged(self.repo.root)
        message = str(ctx.exception)
        self.assertIn("父插口只接受固定子名", message)
        self.assertIn("z", message)

    def test_undeclared_parent_is_reported(self) -> None:
        self.provide("app/ghost/entry")
        with self.assertRaises(SlotConfigError) as ctx:
            load_merged(self.repo.root)
        self.assertIn("贡献的父插口未声明", str(ctx.exception))


class ReservedSlotTest(unittest.TestCase):
    """跨插件预留槽位：fixed 白名单里写一个本插件没有的子名，由别的插件填。

    场景就是 base_settings 的 interface.fixed 里预留 theme_style，
    实际由 theme_style 插件 provides 进来。父插口只认「子名在不在白名单」，
    不追究那条槽位最初归谁使用。
    """

    def setUp(self) -> None:
        self.repo = _Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write_json("plugin-slots.json", {
            "version": 1, "root": "app",
            "owners": {"app/settings/interface": "base_settings"},
            "slots": [{"path": "app/host", "kind": "container"}],
        })
        # 面板方：白名单里预先写好别人的槽位
        self.repo.write_json("plugins/base_settings/plugin-slots.json", {
            "version": 1, "root": "app",
            "slots": [{"path": "app/settings/interface", "kind": "setting",
                       "factory": "plugin:make_panel",
                       "children": "fixed",
                       "fixed": ["display_tool_items", "theme_style"]}],
        })

    def theme_style(self, child: str) -> None:
        self.repo.write_json("plugins/theme_style/plugin-slots.json", {
            "version": 1, "root": "app",
            "slots": [{"path": "app/plugins/theme_style/runtime",
                       "kind": "runtime", "factory": "plugin:make_runtime"}],
            "provides": [{"path": f"app/settings/interface/{child}",
                          "kind": "setting",
                          "factory": "plugin:make_setting"}],
        })

    def test_reserved_slot_can_be_filled_by_another_plugin(self) -> None:
        self.theme_style("theme_style")
        config = load_merged(self.repo.root)
        filled = config.specs["app/settings/interface/theme_style"]
        # 归属跟父插口走，不是贡献方
        self.assertEqual(filled.owner, "base_settings")
        self.assertEqual(filled.kind, "setting")

    def test_unreserved_name_is_still_rejected(self) -> None:
        """预留是「只开一个口子」，不是取消白名单。"""
        self.theme_style("not_reserved")
        with self.assertRaises(SlotConfigError) as ctx:
            load_merged(self.repo.root)
        message = str(ctx.exception)
        self.assertIn("父插口只接受固定子名", message)
        self.assertIn("not_reserved", message)


class OwnersGrantTest(unittest.TestCase):
    """owners 授权：被授权前缀下的路径可以声明，owner 取授权值。"""

    def setUp(self) -> None:
        self.repo = _Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write_json("plugin-slots.json", {
            "version": 1, "root": "app",
            "owners": {"app/settings/interface": "theme_style"},
            "slots": [{"path": "app/host", "kind": "container"}],
        })

    def declare(self, plugin: str, path: str) -> None:
        self.repo.write_json(f"plugins/{plugin}/plugin-slots.json", {
            "version": 1, "root": "app",
            "slots": [{"path": path, "kind": "setting",
                       "factory": "plugin:make_setting"}],
        })

    def test_authorized_prefix_is_declarable(self) -> None:
        """被授权给本插件的前缀下声明的路径通过，且 owner 是授权值。"""
        self.declare("theme_style", "app/settings/interface/theme_style")
        config = load_merged(self.repo.root)
        spec = config.specs["app/settings/interface/theme_style"]
        self.assertEqual(spec.owner, "theme_style")
        self.assertEqual(spec.kind, "setting")

    def test_same_path_is_rejected_for_unauthorized_plugin(self) -> None:
        """同一条路径换一个未获授权的插件就报错——挡的是授权，不是路径。"""
        self.declare("alpha", "app/settings/interface/theme_style")
        with self.assertRaises(SlotConfigError) as ctx:
            load_merged(self.repo.root)
        message = str(ctx.exception)
        self.assertIn("缺少归属授权", message)
        self.assertIn("app/settings/interface/theme_style", message)
        self.assertIn("不在 alpha 的可声明范围内", message)


def _merge_real_plugin(test: unittest.TestCase, name: str) -> Any:
    """把仓库里真实的插件片段放进临时仓库并启用，走公开合并路径。

    仓库里 visual_operator 是 `enabled=0`，合并会跳过它；而片段完整性
    与是否装载无关，故在临时仓库里启用后再验声明。
    """
    repo = _Repo()
    test.addCleanup(repo.cleanup)
    repo.write_json("plugin-slots.json", _STATIC)
    payload = json.loads((ROOT / "plugins" / name / "plugin-slots.json")
                         .read_text(encoding="utf-8"))
    repo.write_json(f"plugins/{name}/plugin-slots.json", payload)
    repo.write_ini(f"[plugin:{name}]\nenabled = 1\n")
    return load_merged(repo.root)


class RealRepoTest(unittest.TestCase):
    """仓库根的真实片段集合必须可合并：任何插件片段写坏，这里就红。"""

    def test_all_repo_fragments_merge(self) -> None:
        config = load_merged(ROOT)
        self.assertGreaterEqual(len(config.specs), 67)

    def test_knowledge_fragment_nodes_and_owner(self) -> None:
        config = load_merged(ROOT)
        prefix = f"{PLUGIN_PATH_ROOT}knowledge"
        owned = [path for path in config.specs if path.startswith(prefix)]
        self.assertEqual(len(owned), 11)
        for path in owned:
            self.assertEqual(config.specs[path].owner, "knowledge")
        self.assertEqual(config.specs[f"{prefix}/runtime"].kind, "runtime")
        for name in ("files", "checked", "checked-update"):
            self.assertEqual(config.specs[f"{prefix}/routes/{name}"].kind, "route")

    def test_static_fragment_has_no_plugin_path(self) -> None:
        """静态片段不得含 app/plugins/ 路径：插件的东西全由插件自己的片段提供。"""
        config = load_merged(ROOT)
        static_only = [path for path, label in config.sources.items()
                       if label.startswith("静态片段")
                       and path.startswith(PLUGIN_PATH_ROOT)]
        self.assertEqual(static_only, [])

    def test_no_fragment_carries_retired_metadata_key(self) -> None:
        """防回潮：仓库里任何片段都不得再出现 metadata（字段已取消）。"""
        fragments = [ROOT / "plugin-slots.json"]
        fragments += sorted((ROOT / "plugins").glob("*/plugin-slots.json"))
        self.assertGreater(len(fragments), 1, "未扫到插件片段")
        offenders: List[str] = []
        for path in fragments:
            raw = json.loads(path.read_text(encoding="utf-8"))
            rows = list(raw.get("slots") or ()) + list(raw.get("provides") or ())
            for row in rows:
                if "metadata" in row:
                    offenders.append(f"{path.name}:{row.get('path')}")
        self.assertEqual(offenders, [],
                         "片段里仍有 metadata：" + "、".join(offenders))
        self.assertIn("metadata", slot_spec.RETIRED_FIELDS)

    def test_ui_kinds_are_the_only_ui_spelling(self) -> None:
        """粗粒度的 ui 已拆成四个 kind；出现 ui 即回潮。"""
        config = load_merged(ROOT)
        self.assertNotIn("ui", {spec.kind for spec in config.specs.values()})
        for kind in ("ui-slot", "ui-action", "ui-control", "ui-tool-shell"):
            self.assertIn(kind, slot_spec.KINDS)

    def test_every_declared_props_survives_merge(self) -> None:
        """防回潮：片段里写的每一条 props 都必须逐字出现在合并结果里。

        这条是 props 静默丢弃的回归守卫。旧实现里 props 根本没有字段承载，
        47 条声明全部消失而测试全绿——「写了但没生效」伪装成「正确」。
        """
        declared: Dict[str, Any] = {}
        fragments = [ROOT / "plugin-slots.json"]
        fragments += sorted((ROOT / "plugins").glob("*/plugin-slots.json"))
        for path in fragments:
            doc = json.loads(path.read_text(encoding="utf-8"))
            for seg in ("slots", "provides"):
                for item in doc.get(seg) or ():
                    if "props" in item:
                        declared[item["path"]] = item["props"]
        self.assertGreater(len(declared), 0, "未扫到声明 props 的节点")
        config = load_merged(ROOT)
        missing = sorted(path for path in declared if path not in config.specs)
        self.assertEqual(missing, [], "合并结果里丢失节点：" + "、".join(missing))
        mismatched = sorted(path for path, props in declared.items()
                            if dict(config.specs[path].props) != props)
        self.assertEqual(mismatched, [], "props 与声明不一致：" + "、".join(mismatched))

    def test_ui_nodes_carry_their_props(self) -> None:
        """ui-* 节点的标签/动作/绑定/脚本全靠 props，声明类节点不允许空载荷。"""
        config = load_merged(ROOT)
        fragments = [ROOT / "plugin-slots.json"]
        fragments += sorted((ROOT / "plugins").glob("*/plugin-slots.json"))
        with_props = set()
        for path in fragments:
            doc = json.loads(path.read_text(encoding="utf-8"))
            for seg in ("slots", "provides"):
                for item in doc.get(seg) or ():
                    if "props" in item:
                        with_props.add(item["path"])
        ui_total = 0
        ui_with_props = 0
        for path, spec in config.specs.items():
            if not spec.kind.startswith("ui-"):
                continue
            ui_total += 1
            if spec.props:
                ui_with_props += 1
                self.assertIn(path, with_props)
        self.assertGreater(ui_total, 0)
        self.assertGreater(ui_with_props, 0)

    def test_base_settings_panels_match_declaration(self) -> None:
        """四个面板的 children 与 fixed 必须与 plugin-ui.json 一致。"""
        source = json.loads(
            (ROOT / "plugins" / "base_settings" / "plugin-ui.json")
            .read_text(encoding="utf-8"))
        fields: Dict[str, List[str]] = {}
        for row in source["settings"]["fields"]:
            fields.setdefault(row["panel"], []).append(row["key"])
        expected_fixed = {
            "app/settings/agent": ["reasoning_effort", "max_passes",
                                   "backup_retention_days", "reread_after_edit"],
            "app/settings/context": ["full_user_rounds", "summary_output_max_chars",
                                     "reasoning_replay_tokens", "image_turns",
                                     "image_max"],
            "app/settings/interface": ["display_tool_items", "display_tool_steps",
                                      "theme_style"],
        }
        #: 由别的插件 provides 进来的子项，不是 base_settings 自己的字段
        foreign = {"theme_style"}
        config = load_merged(ROOT)
        for panel_id in (row["id"] for row in source["settings"]["panels"]):
            with self.subTest(panel=panel_id):
                spec = config.specs[panel_id]
                self.assertEqual(spec.kind, "setting")
                self.assertEqual(spec.owner, "base_settings")
                if panel_id in expected_fixed:
                    self.assertEqual(spec.children, "fixed")
                    self.assertEqual(list(spec.fixed), expected_fixed[panel_id])
                    # 本面板自己的字段必须逐个有位置，多出来的只能是外来贡献
                    self.assertLessEqual(set(fields.get(panel_id, [])), set(spec.fixed))
                    self.assertEqual(set(spec.fixed) - set(fields.get(panel_id, [])),
                                     foreign & set(spec.fixed))
                else:
                    self.assertEqual(spec.children, "keyed")
                    self.assertEqual(spec.fixed, ())

    def test_base_settings_interface_accepts_foreign_setting(self) -> None:
        """interface 的 fixed 里备好了 theme_style 的位置（由 theme_style 插件 provides）。"""
        config = load_merged(ROOT)
        spec = config.specs["app/settings/interface"]
        self.assertIn("theme_style", spec.fixed)

    def test_theme_style_setting_decl_matches_plugin(self) -> None:
        """theme_style 的 SettingDecl 七个字段必须与 plugin.py 里的声明逐条对齐。"""
        sys.path.insert(0, str(ROOT / "plugins"))
        from theme_style import plugin as theme_plugin

        decl = theme_plugin.make_setting({}, theme_plugin.make_runtime({}))
        self.assertIsInstance(decl, slot_spec.SettingDecl)
        self.assertEqual(decl.kind, "select")
        self.assertEqual(decl.label, "界面风格")
        self.assertEqual(decl.default, theme_plugin.DEFAULT_STYLE)
        self.assertEqual(
            [dict(item) for item in decl.options],
            [{"value": "dsh", "label": "DSH 风格"},
             {"value": "minimal", "label": "极简风格"},
             {"value": "glass", "label": "玻璃风格"}])
        self.assertEqual(decl.hint, "保存后立即切换；关闭插件回到 DSH 风格。")
        # save / load 是函数，只能在 factory 里闭包构造
        self.assertTrue(callable(decl.save))
        self.assertTrue(callable(decl.load))

    def test_theme_style_fills_reserved_slot_in_repo(self) -> None:
        """真实仓库里的跨插件预留槽位：base_settings 预留，theme_style 填入。"""
        config = load_merged(ROOT)
        parent = config.specs["app/settings/interface"]
        self.assertEqual(parent.children, "fixed")
        self.assertIn("theme_style", parent.fixed)
        filled = config.specs["app/settings/interface/theme_style"]
        self.assertEqual(filled.kind, "setting")
        # 归属跟父插口，不跟贡献方
        self.assertEqual(filled.owner, "base_settings")
        self.assertEqual(filled.factory, "plugin:make_setting")
        self.assertEqual(dict(filled.requires),
                         {"runtime": "app/plugins/theme_style/runtime"})

    def test_ai_cosplay_has_no_legacy_registration_calls(self) -> None:
        """旧注册 API 彻底消失：plugin.py 里不得再有任何 `ctx.add_*` 之类的调用。"""
        tree = ast.parse((ROOT / "plugins" / "ai_cosplay" / "plugin.py")
                         .read_text(encoding="utf-8"))
        legacy = ("add_ui_item", "add_route", "add_mode_tail", "register_tool",
                  "subscribe", "set_subagent_tools", "set_runtime")
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr not in legacy:
                continue
            if isinstance(func.value, ast.Name) and func.value.id == "ctx":
                found.append(func.attr)
        self.assertEqual(sorted(found), [],
                         "plugin.py 仍有旧注册调用：" + "、".join(sorted(found)))

    def test_ai_cosplay_factories_all_exist(self) -> None:
        """片段引用的每个 ai_cosplay 工厂，都必须真的存在于 plugin.py 里。"""
        module = importlib.import_module("plugins.ai_cosplay.plugin")
        config = load_merged(ROOT)
        factories = {spec.factory for path, spec in config.specs.items()
                     if path.startswith("app/plugins/ai_cosplay/") and spec.factory}
        self.assertEqual(len(factories), 7)
        for factory in sorted(factories):
            with self.subTest(factory=factory):
                name = factory.partition(":")[2]
                self.assertTrue(callable(getattr(module, name, None)), name)

    def test_ai_cosplay_fragment_shape(self) -> None:
        """片段形状：runtime 1 / tool 1 / route 3 / event 1 / provider 1。"""
        config = load_merged(ROOT)
        own = [spec for path, spec in config.specs.items()
               if path.startswith("app/plugins/ai_cosplay/")]
        counts = collections.Counter(spec.kind for spec in own)
        self.assertEqual(counts["runtime"], 1)
        self.assertEqual(counts["tool"], 1)
        self.assertEqual(counts["route"], 3)
        self.assertEqual(counts["event"], 1)
        self.assertEqual(counts["provider"], 1)
        self.assertEqual(counts["container"], 4)
        # 必须真的在字典里且为空元组：`.get(..., ())` 会把「未声明」也当成空，
        # 于是装配层把 `[]` 当真值丢掉这类缺陷会被这条断言放过。
        self.assertIn("ai_cosplay", config.subagent_tools)
        self.assertEqual(config.subagent_tools["ai_cosplay"], ())

    def test_ai_cosplay_routes_keep_their_methods(self) -> None:
        """三个路由的 HTTP 方法保持现状：config/status 为 GET，played 为 POST。"""
        config = load_merged(ROOT)
        methods = {path.rsplit("/", 1)[-1]: spec.method
                   for path, spec in config.specs.items()
                   if path.startswith("app/plugins/ai_cosplay/routes/")}
        self.assertEqual(methods, {"config": "GET", "status": "GET",
                                   "played": "POST"})

    def test_ai_cosplay_event_names_come_from_constants(self) -> None:
        """event 节点的事件名必须是 event_name 里的常量值。"""
        config = load_merged(ROOT)
        names = {path.rsplit("/", 1)[-1]
                 for path in config.specs
                 if path.startswith("app/plugins/ai_cosplay/events/")}
        self.assertEqual(names, {ev.TURN_ENDED})
        self.assertTrue(names <= slot_spec.EVENT_NAMES)

    def test_ai_cosplay_panel_is_ui_control(self) -> None:
        """左栏面板是控件（带动作与脚本），不是可再被填的插口。"""
        config = load_merged(ROOT)
        spec = config.specs["app/shell/web-ui/runtime/left-panel/ai_cosplay"]
        self.assertEqual(spec.kind, "ui-control")
        self.assertEqual(spec.owner, "web_ui")
        self.assertEqual(spec.order, 10)
        self.assertEqual(sorted(spec.props),
                         ["action", "binding", "scripts", "styles"])

    def test_visual_operator_tool_nodes_resolve(self) -> None:
        """12 个 tool 节点：factory 互不相同、全部可解析、requires 指向同一个 runtime。"""
        config = _merge_real_plugin(self, "visual_operator")
        nodes = {path: spec for path, spec in config.specs.items()
                 if path.startswith("app/plugins/visual_operator/tools/")}
        self.assertEqual(len(nodes), 12)
        module = importlib.import_module("plugins.visual_operator.plugin")
        factories = set()
        for path, spec in sorted(nodes.items()):
            with self.subTest(path=path):
                self.assertEqual(spec.kind, "tool")
                self.assertEqual(spec.owner, "visual_operator")
                self.assertEqual(dict(spec.requires),
                                 {"runtime": "app/plugins/visual_operator/runtime"})
                self.assertTrue(spec.factory.startswith("plugin:"))
                attr = spec.factory.split(":", 1)[1]
                self.assertTrue(callable(getattr(module, attr, None)), spec.factory)
                factories.add(spec.factory)
        self.assertEqual(len(factories), 12)

    def test_visual_operator_runtime_is_shared(self) -> None:
        """12 个节点共用一份 runtime：captures 只有一份的接线前提。"""
        config = _merge_real_plugin(self, "visual_operator")
        runtime = config.specs["app/plugins/visual_operator/runtime"]
        self.assertEqual(runtime.kind, "runtime")
        self.assertEqual(runtime.factory, "plugin:make_runtime")
        self.assertEqual(runtime.owner, "visual_operator")

    def test_visual_operator_2_fragment_shape(self) -> None:
        """29 个声明节点：runtime 1 / tool 20 / route 4 / provider 2 / event 1 + 1 条 provides。"""
        config = load_merged(ROOT)
        prefix = "app/plugins/visual_operator_2/"
        own = {path: spec for path, spec in config.specs.items()
               if path.startswith(prefix)}
        declared = {path: spec for path, spec in own.items()
                    if spec.kind != "container"}
        self.assertEqual(len(declared), 28)
        counts = collections.Counter(spec.kind for spec in declared.values())
        self.assertEqual(counts["runtime"], 1)
        self.assertEqual(counts["tool"], 20)
        self.assertEqual(counts["route"], 4)
        self.assertEqual(counts["provider"], 2)
        self.assertEqual(counts["event"], 1)
        button = config.specs["app/shell/web-ui/input/buttons/visual_btn"]
        self.assertEqual(button.kind, "ui-control")
        self.assertEqual(button.order, 60)
        self.assertEqual(sorted(button.props),
                         ["action", "binding", "label", "scripts", "styles"])

    def test_visual_operator_2_owner_and_factories(self) -> None:
        """节点全归本插件，factory 互异且逐个可解析，requires 全指向同一 runtime。"""
        config = load_merged(ROOT)
        prefix = "app/plugins/visual_operator_2/"
        module = importlib.import_module("plugins.visual_operator_2.plugin")
        factories = set()
        for path, spec in sorted(config.specs.items()):
            if not path.startswith(prefix):
                continue
            self.assertEqual(spec.owner, "visual_operator_2", path)
            if spec.kind == "container":
                continue
            with self.subTest(path=path):
                attr = spec.factory.split(":", 1)[1]
                self.assertTrue(callable(getattr(module, attr, None)), spec.factory)
                if spec.kind == "runtime":
                    # runtime 要 App：步骤日志路径与事件出口都从它取。
                    self.assertEqual(dict(spec.requires),
                                     {"app": "app/boot/facade"})
                elif path == prefix + "routes/confirm":
                    # 确认路由要 App 的 resume_suspended 拉起挂起的工具调用。
                    self.assertEqual(dict(spec.requires),
                                     {"runtime": prefix + "runtime",
                                      "app": "app/boot/facade"})
                else:
                    self.assertEqual(dict(spec.requires),
                                     {"runtime": prefix + "runtime"})
                factories.add(spec.factory)
        self.assertEqual(len(factories), 28)

    def test_visual_operator_2_prompt_slots_semantics(self) -> None:
        """钩子落 user-messages、提示词段落 system-appends，且 after_tools 保留。"""
        config = load_merged(ROOT)
        hook = config.specs[
            "app/plugins/visual_operator_2/prompt/user-messages/observations"]
        self.assertEqual(hook.kind, "provider")
        self.assertEqual(hook.factory, "plugin:make_observation_hook")
        section = config.specs[
            "app/plugins/visual_operator_2/prompt/system-appends/discipline"]
        self.assertEqual(section.kind, "provider")
        self.assertEqual(section.factory, "plugin:make_prompt_section")
        self.assertIs(section.props.get("after_tools"), True)

    def test_visual_operator_2_route_methods(self) -> None:
        """四条授权路由的 HTTP 方法保持现状。"""
        config = load_merged(ROOT)
        prefix = "app/plugins/visual_operator_2/routes/"
        methods = {path[len(prefix):]: spec.method
                   for path, spec in config.specs.items()
                   if path.startswith(prefix)}
        self.assertEqual(methods, {"pending": "GET", "status": "GET",
                                   "confirm": "POST", "revoke": "POST"})

    def test_base_settings_declares_own_fields(self) -> None:
        """base_settings 自己只声明 11 条字段；interface 里那条 theme_style 是外来贡献。"""
        config = load_merged(ROOT)
        source = json.loads(
            (ROOT / "plugins" / "base_settings" / "plugin-ui.json")
            .read_text(encoding="utf-8"))
        own = {f"{row['panel']}/{row['key']}" for row in source["settings"]["fields"]}
        self.assertEqual(len(own), 11)
        for path in sorted(own):
            spec = config.specs[path]
            self.assertEqual(spec.kind, "setting")
            self.assertEqual(spec.owner, "base_settings")
        # 外来贡献归父插口 owner，不在 base_settings 的自有清单里
        foreign = config.specs["app/settings/interface/theme_style"]
        self.assertNotIn("app/settings/interface/theme_style", own)
        self.assertEqual(foreign.owner, "base_settings")


class MergeShapeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repo = _Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write_json("plugin-slots.json", _STATIC)
        self.repo.plugin("alpha")

    def test_merge_is_not_assembly(self) -> None:
        """合并只返回配置，不构造节点。"""
        config = load_merged(self.repo.root)
        self.assertFalse(hasattr(config, "values"))
        self.assertEqual(config.specs[f"{PLUGIN_PATH_ROOT}alpha/tools/alpha"].kind,
                         "tool")

    def test_static_owner_defaults_to_host(self) -> None:
        config = load_merged(self.repo.root)
        self.assertEqual(config.specs["app/host"].owner, HOST_OWNER)

    def test_root_and_version_come_from_static(self) -> None:
        config = load_merged(self.repo.root)
        self.assertEqual(config.root, "app")
        self.assertEqual(config.version, 1)


class AncestorFillTest(unittest.TestCase):
    """祖先补齐：按层级二分 owner，共用一级容器不得被单个插件夺走。"""

    def setUp(self) -> None:
        self.repo = _Repo()
        self.addCleanup(self.repo.cleanup)
        self.repo.write_json("plugin-slots.json", _STATIC)

    def test_three_generations_filled_for_single_plugin(self) -> None:
        self.repo.plugin("alpha")
        config = load_merged(self.repo.root)
        leaf = f"{PLUGIN_PATH_ROOT}alpha/tools/alpha"
        self.assertIn(leaf, config.specs)
        self.assertEqual(config.specs[f"{PLUGIN_PATH_ROOT}alpha"].owner, "alpha")
        self.assertEqual(
            config.specs[f"{PLUGIN_PATH_ROOT}alpha/tools"].owner, "alpha")
        for path in (f"{PLUGIN_PATH_ROOT}alpha",
                     f"{PLUGIN_PATH_ROOT}alpha/tools"):
            self.assertEqual(config.specs[path].kind, "container")
            self.assertIn(path, config.synthesized)

    def test_shared_root_belongs_to_host(self) -> None:
        self.repo.plugin("alpha")
        config = load_merged(self.repo.root)
        shared = PLUGIN_PATH_ROOT.rstrip("/")
        self.assertIn(shared, config.specs)
        self.assertEqual(config.specs[shared].owner, HOST_OWNER)
        self.assertIn(shared, config.synthesized)

    def test_shared_root_is_not_stolen_with_two_plugins(self) -> None:
        self.repo.plugin("alpha")
        self.repo.plugin("beta")
        config = load_merged(self.repo.root)
        shared = PLUGIN_PATH_ROOT.rstrip("/")
        self.assertEqual(config.specs[shared].owner, HOST_OWNER)
        self.assertEqual(config.specs[f"{PLUGIN_PATH_ROOT}alpha"].owner, "alpha")
        self.assertEqual(config.specs[f"{PLUGIN_PATH_ROOT}beta"].owner, "beta")

    def test_topo_order_puts_child_before_parent(self) -> None:
        self.repo.plugin("alpha")
        config = load_merged(self.repo.root)
        order = topo_order(config)
        leaf = f"{PLUGIN_PATH_ROOT}alpha/tools/alpha"
        chain = [leaf, f"{PLUGIN_PATH_ROOT}alpha/tools",
                 f"{PLUGIN_PATH_ROOT}alpha", PLUGIN_PATH_ROOT.rstrip("/")]
        for parent, child in zip(chain[1:], chain):
            self.assertLess(order.index(child), order.index(parent))

    def test_declared_ancestor_keeps_owner_and_is_not_duplicated(self) -> None:
        self.repo.write_json("plugin-slots.json", {
            "version": 1, "root": "app",
            "slots": [
                {"path": "app/host", "kind": "container"},
                {"path": PLUGIN_PATH_ROOT.rstrip("/"), "kind": "container",
                 "owner": "custom"},
            ],
        })
        self.repo.plugin("alpha")
        config = load_merged(self.repo.root)
        shared = PLUGIN_PATH_ROOT.rstrip("/")
        self.assertEqual(config.specs[shared].owner, "custom")
        self.assertNotIn(shared, config.synthesized)
        self.assertEqual(config.specs[f"{PLUGIN_PATH_ROOT}alpha"].owner, "alpha")

    def test_leaf_declared_as_ancestor_is_rejected(self) -> None:
        self.repo.write_json("plugin-slots.json", {
            "version": 1, "root": "app",
            "slots": [
                {"path": "app/host", "kind": "container"},
                {"path": f"{PLUGIN_PATH_ROOT}alpha/tools", "kind": "tool",
                 "factory": "tools:root", "owner": "alpha"},
            ],
        })
        self.repo.plugin("alpha")
        with self.assertRaises(SlotConfigError) as ctx:
            load_merged(self.repo.root)
        message = str(ctx.exception)
        self.assertIn("祖先不能持有子级", message)
        self.assertIn(f"{PLUGIN_PATH_ROOT}alpha/tools", message)
        self.assertIn("kind=tool", message)

    def test_declarative_parent_with_children_is_allowed(self) -> None:
        """设置面板这类声明型节点可挂子项：判据是 children≠none，不是 kind。"""
        self.repo.write_json("plugin-slots.json", {
            "version": 1, "root": "app",
            "owners": {"app/panel": "alpha"},
            "slots": [
                {"path": "app/host", "kind": "container"},
            ],
        })
        self.repo.write_json("plugins/alpha/plugin-slots.json", {
            "version": 1, "root": "app",
            "slots": [
                {"path": "app/panel", "kind": "setting", "children": "keyed",
                 "factory": "plugin:make_panel"},
                {"path": "app/panel/a", "kind": "setting",
                 "factory": "plugin:make_setting"},
            ],
        })
        config = load_merged(self.repo.root)
        self.assertEqual(config.specs["app/panel"].children, "keyed")
        self.assertIn("app/panel/a", config.specs)


if __name__ == "__main__":
    unittest.main()
