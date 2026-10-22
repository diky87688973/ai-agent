# -*- coding: utf-8 -*-
"""Rules 插件测试。

覆盖：目录缺失时的空行为 / 只收 `.md` 与递归子目录 / 隐藏段与 `__pycache__` 跳过 /
一文件一条与抬头格式 / 注入条数与自报数一致 / 单文件上限 / 资源目录两行 /
ContextSources 里的段 key、段名与计数 / disposer 全撤后注入消失。
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.mechanisms.context import ContextSources  # noqa: E402

_PLUGIN_MOD = "fan_agent_plugins.rules"


def _load_plugin_module():
    """从磁盘加载 Rules 插件模块（独立实例）。"""
    path = _ROOT / "plugins" / "rules" / "plugin.py"
    spec = importlib.util.spec_from_file_location(_PLUGIN_MOD, str(path))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PLUGIN_MOD] = module
    spec.loader.exec_module(module)
    return module


_PLUGIN = _load_plugin_module()


class _FakeCtx:
    """最小插件上下文：只记下注册了什么，用来验证 register 的贡献面。"""

    def __init__(self) -> None:
        self.runtime = None
        self.sources = ContextSources()
        self.sections = []
        self.styles = []
        self._disposers = []

    def set_runtime(self, runtime) -> None:
        self.runtime = runtime

    def add_context_source(self, fn, meta=None):
        return self.sources.add(fn, self._meta(meta))

    def _meta(self, meta):
        from agent.mechanisms.context import SourceMeta

        payload = meta if isinstance(meta, dict) else {}
        return SourceMeta(key="rules", label=str(payload.get("label") or ""),
                          plugin="rules", count=payload.get("count"))

    def add_prompt_section(self, section, fn):
        self.sections.append((section, fn))

        def _drop() -> None:
            self.sections = [row for row in self.sections if row[1] is not fn]

        return _drop

    def add_ctx_segment_style(self, *, label="", color=""):
        self.styles.append({"label": label, "color": color})
        return lambda: None


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


class RulesRegisterTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "rules"
        _make_tree(self.root)

    def _register(self, root: Path):
        ctx = _FakeCtx()
        disposers = _PLUGIN.register(ctx)
        ctx.runtime = _PLUGIN.RulesRuntime(root)
        return ctx, disposers

    def test_segment_key_label_and_count(self) -> None:
        ctx, _ = self._register(self.root)
        runtime = _PLUGIN.RulesRuntime(self.root)
        ctx.sources = ContextSources()
        ctx.add_context_source(runtime.build_system_messages,
                               {"label": _PLUGIN.SEGMENT_LABEL,
                                "count": runtime.attached_count})
        segments = ctx.sources.collect_segments("c1")
        keys = {item[0] for item in segments.items}
        self.assertEqual(keys, {"rules"})
        labels = {item[1] for item in segments.items}
        self.assertEqual(labels, {"Rules"})
        # 两条正文 → 两条段条目，只有第一条带自报数（2）
        self.assertEqual(len(segments.items), 2)
        self.assertEqual(segments.counts[0], 2)
        self.assertEqual(segments.counts[1], 1)

    def test_resource_section_lines(self) -> None:
        ctx, _ = self._register(self.root)
        self.assertEqual(len(ctx.sections), 1)
        heading, fn = ctx.sections[0]
        self.assertEqual(heading, _PLUGIN.RESOURCE_HEAD)
        lines = fn("c1")
        self.assertEqual(lines[0], f"- 规则rules: {_PLUGIN.RULES_DIR}")
        self.assertIn("该目录中规则文件（*.md）会自动注入到上下文", lines[1])
        self.assertIn("USER_RULES.md为默认用户规则文件", lines[1])

    def test_resource_section_marks_missing_dir(self) -> None:
        runtime = _PLUGIN.RulesRuntime(self.root / "nope")
        lines = _PLUGIN.resource_directory_lines(runtime)
        self.assertEqual(lines[0], f"- 规则rules: {_PLUGIN.RULES_DIR}（不存在）")

    def test_segment_style_registered(self) -> None:
        ctx, _ = self._register(self.root)
        self.assertEqual(ctx.styles[0]["label"], "Rules")
        self.assertTrue(ctx.styles[0]["color"])

    def test_dispose_removes_injection(self) -> None:
        ctx = _FakeCtx()
        disposers = _PLUGIN.register(ctx)
        self.assertTrue(ctx.sources.collect_segments("c1").items)
        for disposer in reversed(disposers):
            disposer()
        self.assertEqual(ctx.sources.collect_segments("c1").items, ())
        self.assertEqual(ctx.sections, [])


if __name__ == "__main__":
    unittest.main()
