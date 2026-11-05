# -*- coding: utf-8 -*-
"""Rules 插件：目录约定、注入格式与片段声明。

旧口径是「调 `register(ctx)` 后看 ctx 收到什么」；`register` 已删，注册面改由
`plugin-slots.json` 声明。因此本文件核对两件事：
  运行时行为（目录缺失 / 只收 .md / 跳过隐藏与缓存 / 抬头与条数 / 上限 / 缓存）；
  片段声明的节点齐备、归属正确，且工厂产出的东西可用。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.core.slot_fragments import load_merged  # noqa: E402
from agent.mechanisms.context import ContextSources, SourceMeta  # noqa: E402
from plugins.rules import plugin as _PLUGIN  # noqa: E402


def _make_tree(root: Path) -> None:
    """构造样例规则目录：两级目录 + 各类应被跳过的条目。"""
    (root / "deps").mkdir(parents=True, exist_ok=True)
    (root / ".hidden").mkdir(exist_ok=True)
    (root / "__pycache__").mkdir(exist_ok=True)
    (root / "a.md").write_text("规则A", encoding="utf-8")
    (root / "deps" / "b.md").write_text("规则B", encoding="utf-8")
    (root / "notes.txt").write_text("不是规则", encoding="utf-8")
    (root / "README").write_text("无扩展名，不是规则", encoding="utf-8")
    (root / ".hidden" / "c.md").write_text("隐藏", encoding="utf-8")
    (root / "__pycache__" / "d.md").write_text("缓存", encoding="utf-8")
    (root / "empty.md").write_text("   \n", encoding="utf-8")


class RulesRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "rules"
        _make_tree(self.root)

    def test_missing_dir_stays_quiet(self) -> None:
        runtime = _PLUGIN.RulesRuntime(self.root / "nope")
        self.assertFalse(runtime.enabled)
        self.assertEqual(runtime.rule_files(), [])
        self.assertEqual(runtime.build_system_messages("c1"), [])
        self.assertEqual(runtime.attached_count("c1"), 0)

    def test_only_markdown_recursive_and_skips_hidden(self) -> None:
        runtime = _PLUGIN.RulesRuntime(self.root)
        self.assertTrue(runtime.enabled)
        rels = sorted(runtime.rel_of(path) for path in runtime.rule_files())
        # 只收 .md：notes.txt / README 不收；只收可见路径：.hidden/ 与 __pycache__/ 不收
        self.assertEqual(rels, ["a.md", "deps/b.md", "empty.md"])

    def test_one_message_per_file_with_prefix(self) -> None:
        runtime = _PLUGIN.RulesRuntime(self.root)
        messages = runtime.build_system_messages("c1")
        # empty.md 正文只有空白 → 不占条目
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0], "【规则 Rules a.md】\n规则A")
        self.assertEqual(messages[1], "【规则 Rules deps/b.md】\n规则B")

    def test_count_matches_messages(self) -> None:
        runtime = _PLUGIN.RulesRuntime(self.root)
        self.assertEqual(runtime.attached_count("c1"), len(runtime.build_system_messages("c1")))

    def test_oversized_file_is_skipped(self) -> None:
        runtime = _PLUGIN.RulesRuntime(self.root, max_bytes=3)
        rels = [runtime.rel_of(path) for path in runtime.rule_files()]
        self.assertIn("a.md", rels)                 # 扫描阶段仍列出
        self.assertEqual(runtime.build_system_messages("c1"), [])  # 但读不出正文

    def test_cache_reuses_content_until_file_changes(self) -> None:
        runtime = _PLUGIN.RulesRuntime(self.root)
        first = runtime.read_text(self.root / "a.md")
        self.assertEqual(first, "规则A")
        (self.root / "a.md").write_text("规则A改过", encoding="utf-8")
        self.assertEqual(runtime.read_text(self.root / "a.md"), "规则A改过")

    def test_missing_file_read_returns_empty(self) -> None:
        runtime = _PLUGIN.RulesRuntime(self.root)
        self.assertEqual(runtime.read_text(self.root / "gone.md"), "")


class RulesFragmentTest(unittest.TestCase):
    """片段声明：三个自有节点 + 一条落到壳层的段外观。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_merged(ROOT)

    def test_own_nodes_are_runtime_and_two_providers(self) -> None:
        own = {path: spec for path, spec in self.config.specs.items()
               if path.startswith("app/plugins/rules/") and spec.kind != "container"}
        self.assertEqual(sorted(own), [
            "app/plugins/rules/prompt/messages/files",
            "app/plugins/rules/prompt/system-appends/resources",
            "app/plugins/rules/runtime",
        ])
        for path in own:
            with self.subTest(path=path):
                self.assertEqual(self.config.origin_of(path), "rules")
        self.assertEqual(own["app/plugins/rules/runtime"].factory, "plugin:make_runtime")
        self.assertEqual(own["app/plugins/rules/prompt/messages/files"].factory,
                         "plugin:make_context_source")
        self.assertEqual(own["app/plugins/rules/prompt/system-appends/resources"].factory,
                         "plugin:make_prompt_section")

    def test_segment_node_carries_label_and_color(self) -> None:
        path = "app/shell/web-ui/left-panel/context_usage/rules"
        self.assertIn(path, self.config.specs)
        spec = self.config.specs[path]
        self.assertEqual(spec.kind, "ui-control")
        self.assertEqual(self.config.origin_of(path), "rules")
        self.assertEqual(spec.props.get("label"), "Rules")
        self.assertEqual(spec.props.get("color"), "green")

    def test_prompt_section_factory_returns_resource_lines(self) -> None:
        runtime = _PLUGIN.RulesRuntime(ROOT / "rules")
        fn = _PLUGIN.make_prompt_section(None, runtime)
        lines = fn("c1")
        self.assertEqual(lines[0], f"- 规则rules: {_PLUGIN.RULES_DIR}")
        self.assertIn("该目录中规则文件（*.md）会自动注入到上下文", lines[1])
        self.assertIn("USER_RULES.md为默认用户规则文件", lines[1])

    def test_resource_section_marks_missing_dir(self) -> None:
        runtime = _PLUGIN.RulesRuntime(ROOT / "rules" / "nope")
        lines = _PLUGIN.resource_directory_lines(runtime)
        self.assertEqual(lines[0], f"- 规则rules: {_PLUGIN.RULES_DIR}（不存在）")

    def test_context_source_factory_contributes_one_segment(self) -> None:
        """工厂产出的注入源交给 ContextSources：一段、标签 Rules、自报数等于正文条数。"""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name) / "rules"
        _make_tree(root)
        runtime = _PLUGIN.RulesRuntime(root)
        sources = ContextSources()
        source = _PLUGIN.make_context_source(None, runtime)
        meta = SourceMeta(key="rules", label="Rules", plugin="rules",
                          count=runtime.attached_count)
        disposer = sources.add(source, meta,
                               path="app/backend/context/sources/rules/files")
        segments = sources.collect_segments("c1")
        self.assertEqual({item[0] for item in segments.items}, {"rules"})
        self.assertEqual({item[1] for item in segments.items}, {"Rules"})
        self.assertEqual(len(segments.items), 2)
        self.assertEqual(segments.counts[0], 2)
        self.assertEqual(segments.counts[1], 1)
        disposer()
        self.assertEqual(sources.collect_segments("c1").items, ())


if __name__ == "__main__":
    unittest.main()
