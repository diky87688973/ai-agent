# -*- coding: utf-8 -*-
"""JS 事件绑定审计：分级判准与输出格式。

沿用「重渲染列表用委托」这条初衷：列表项逐项绑算 per-item，模块级一次性
绑全局监听不算泄漏。负向用例与正向成对出现，防止判准日后悄悄退回旧版。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.scan_js_events import (  # noqa: E402
    EXCLUDED_VERDICTS,
    REVIEW_VERDICTS,
    _ephemeral_names,
    read_guide,
    render,
    scan_text,
)


class CollectTest(unittest.TestCase):
    def test_collects_add_listener_property_and_delegation(self) -> None:
        text = (
            'document.addEventListener("click", handle);\n'
            'card.addEventListener("click", handle);\n'
            'button.onclick = handle;\n'
        )
        bindings = scan_text(text, "fixture.js")
        self.assertEqual([b.kind for b in bindings],
                         ["addEventListener", "addEventListener", "property"])
        self.assertTrue(bindings[0].delegated)
        self.assertFalse(bindings[1].delegated)
        self.assertEqual(bindings[1].event, "click")
        self.assertEqual(bindings[2].event, "click")

    def test_collects_inline_html_and_renders_report(self) -> None:
        bindings = scan_text('<button onclick="save()">保存</button>', "fixture.html")
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].kind, "inline-html")
        text = render(bindings, 1)
        self.assertIn("JS 事件绑定审计", text)
        self.assertIn("inline-html", text)

    def test_property_assignment_matches_camel_case(self) -> None:
        """`onMouseDown` 这类大写事件名也要认，不能只匹配 `on[a-z]+`。"""
        bindings = scan_text('box.onMouseDown = handle;\n', "fixture.js")
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].kind, "property")


class CommentTest(unittest.TestCase):
    def test_bindings_inside_comments_are_ignored(self) -> None:
        """注释里的示例代码不是绑定——块注释与行内 `//` 都不算。"""
        text = (
            '/* 示例：list.addEventListener("click", handle); */\n'
            '// card.addEventListener("click", handle);\n'
            'button.onclick = handle;\n'
        )
        bindings = scan_text(text, "fixture.js")
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].kind, "property")

    def test_double_slash_inside_string_is_not_a_comment(self) -> None:
        """URL 里的 `//` 不得把后面的代码当成注释吞掉。"""
        text = 'var u = "https://example.com/a";\nbtn.addEventListener("click", h);\n'
        bindings = scan_text(text, "fixture.js")
        self.assertEqual(len(bindings), 1)


class ScopeVerdictTest(unittest.TestCase):
    def test_global_container_element_are_distinguished(self) -> None:
        """绑全局 / 容器根+closest / 元素自身，是三种不同结论。"""
        text = (
            'document.addEventListener("click", handle);\n'
            'list.addEventListener("click", function(ev){\n'
            '  var item = ev.target.closest(".row");\n'
            '  if(!item) return;\n'
            '});\n'
            'card.addEventListener("click", handle);\n'
        )
        bindings = scan_text(text, "fixture.js")
        self.assertEqual([b.scope for b in bindings],
                         ["global", "container", "element"])
        self.assertEqual([b.verdict for b in bindings],
                         ["global-once", "delegated-ok", "ok"])


class LoopVerdictTest(unittest.TestCase):
    def test_binding_inside_loop_is_per_item(self) -> None:
        text = (
            'function renderList(items){\n'
            '  items.forEach(function(it){\n'
            '    var row = document.createElement("div");\n'
            '    row.addEventListener("click", handle);\n'
            '  });\n'
            '}\n'
        )
        bindings = scan_text(text, "fixture.js")
        self.assertTrue(bindings[0].in_loop)
        self.assertTrue(bindings[0].render_fn)
        self.assertEqual(bindings[0].verdict, "per-item")

    def test_binding_after_loop_is_not_per_item(self) -> None:
        """循环结束后的绑定不算逐项绑——按花括号配平判，不按缩进或行序。"""
        text = (
            'items.forEach(function(it){ paint(it); });\n'
            'list.addEventListener("click", handle);\n'
        )
        bindings = scan_text(text, "fixture.js")
        self.assertFalse(bindings[0].in_loop)


class LeakRiskTest(unittest.TestCase):
    def test_anonymous_global_listener_in_render_fn_is_leak_risk(self) -> None:
        text = (
            'function ensureBox(){\n'
            '  document.addEventListener("keydown", function(ev){ close(); });\n'
            '}\n'
        )
        bindings = scan_text(text, "fixture.js")
        self.assertTrue(bindings[0].anonymous)
        self.assertEqual(bindings[0].verdict, "leak-risk")

    def test_module_level_global_listener_is_not_leak_risk(self) -> None:
        """模块级只绑一次，不是泄漏——负向用例，防止判准退回旧版。"""
        text = 'window.addEventListener("resize", function(){ repaint(); });\n'
        bindings = scan_text(text, "fixture.js")
        self.assertEqual(bindings[0].verdict, "global-once")

    def test_paired_remove_clears_leak_risk(self) -> None:
        """同文件、同目标、同事件、同回调、同 capture 才清除泄漏。"""
        text = (
            'function ensureBox(){\n'
            '  document.addEventListener("keydown", onKey);\n'
            '  document.removeEventListener("keydown", onKey);\n'
            '}\n'
        )
        bindings = scan_text(text, "fixture.js")
        self.assertFalse(bindings[0].anonymous)
        self.assertTrue(bindings[0].paired_remove)
        self.assertEqual(bindings[0].verdict, "global-once")

    def test_different_callback_is_not_paired(self) -> None:
        text = (
            'function ensureBox(){\n'
            '  document.addEventListener("keydown", onKey);\n'
            '  document.removeEventListener("keydown", otherKey);\n'
            '}\n'
        )
        binding = scan_text(text, "fixture.js")[0]
        self.assertFalse(binding.paired_remove)
        self.assertEqual(binding.verdict, "leak-risk")

    def test_capture_mismatch_is_not_paired(self) -> None:
        text = (
            'function ensureBox(){\n'
            '  document.addEventListener("keydown", onKey, true);\n'
            '  document.removeEventListener("keydown", onKey);\n'
            '}\n'
        )
        binding = scan_text(text, "fixture.js")[0]
        self.assertFalse(binding.paired_remove)
        self.assertEqual(binding.verdict, "leak-risk")

    def test_anonymous_callback_is_not_paired(self) -> None:
        text = (
            'function ensureBox(){\n'
            '  document.addEventListener("keydown", function(){ close(); });\n'
            '  document.removeEventListener("keydown", onKey);\n'
            '}\n'
        )
        binding = scan_text(text, "fixture.js")[0]
        self.assertFalse(binding.paired_remove)
        self.assertEqual(binding.verdict, "leak-risk")


class EphemeralTest(unittest.TestCase):
    def test_create_element_and_factory_count_as_new_node(self) -> None:
        """`createElement` 与本项目 `el()` 工厂都算新建节点。"""
        text = (
            'var a = document.createElement("div");\n'
            'var b = el("div", "cls");\n'
            'var c = document.getElementById("keep");\n'
        )
        names = _ephemeral_names(text)
        self.assertIn("a", names)
        self.assertIn("b", names)
        self.assertNotIn("c", names)

    def test_lookup_wins_over_create(self) -> None:
        """取节点的函数优先：`getXxx()` 指向已有容器，内部用 createElement 也不算新节点。"""
        self.assertNotIn("list", _ephemeral_names('var list = getAtList();\n'))

    def test_bare_assignment_is_recognised(self) -> None:
        """模块级申明、函数内懒赋值（无 var 前缀）也要认出来。"""
        self.assertIn("tip", _ephemeral_names('tip = document.createElement("div");\n'))

    def test_new_node_binding_is_excluded_as_ephemeral(self) -> None:
        text = (
            'function buildCard(){\n'
            '  var card = document.createElement("div");\n'
            '  card.addEventListener("click", handle);\n'
            '  return card;\n'
            '}\n'
        )
        bindings = scan_text(text, "fixture.js")
        self.assertTrue(bindings[0].ephemeral)
        self.assertEqual(bindings[0].verdict, "ephemeral")


class GuardTest(unittest.TestCase):
    def test_container_delegation_in_render_fn_is_not_render_path(self) -> None:
        """容器根委托写在渲染函数里也是正确写法，不该报可能累积。"""
        text = (
            'function ensureBox(){\n'
            '  var el = document.getElementById("box");\n'
            '  el.addEventListener("click", function(ev){\n'
            '    var btn = ev.target.closest(".btn");\n'
            '    if(!btn) return;\n'
            '  });\n'
            '}\n'
        )
        bindings = scan_text(text, "fixture.js")
        self.assertTrue(bindings[0].render_fn)
        self.assertEqual(bindings[0].scope, "container")
        self.assertEqual(bindings[0].verdict, "delegated-ok")

    def test_existing_guard_marker_is_recognised(self) -> None:
        """项目既有的 `_xxxDelegated` 惯例要被认出来，不能与可疑项同形。"""
        text = (
            'function bindList(){\n'
            '  if(list._listClickDelegated) return;\n'
            '  list._listClickDelegated = true;\n'
            '  list.addEventListener("click", handle);\n'
            '}\n'
        )
        bindings = scan_text(text, "fixture.js")
        self.assertTrue(bindings[0].guarded)
        self.assertEqual(bindings[0].verdict, "guarded-ok")


class RenderOutputTest(unittest.TestCase):
    def test_report_states_intent_and_read_guide(self) -> None:
        """输出本身要写明初衷与读法，换一个会话说不用翻文档也懂。"""
        text = (
            'items.forEach(function(it){\n'
            '  var d = document.createElement("div");\n'
            '  d.addEventListener("click", h);\n'
            '});\n'
        )
        report = render(scan_text(text, "fixture.js"), 1)
        self.assertIn("初衷", report)
        self.assertIn("per-item", report)
        self.assertIn("需确认", report)

    def test_clean_input_reports_nothing_to_review(self) -> None:
        report = render(scan_text('document.addEventListener("click", h);\n', "fixture.js"), 1)
        self.assertIn("没有需要复核的绑定", report)


class LoopBodyTest(unittest.TestCase):
    """第 1、4 条：语句式循环的循环体必须进 span，光配平头部括号不够。"""

    def _in_loop(self, src: str) -> bool:
        return scan_text(src, "fixture.js")[0].in_loop

    def test_for_loop_body_counts_as_loop(self) -> None:
        src = ('for(var i=0;i<n;i++){\n'
               '  list.addEventListener("click", h);\n'
               '}\n')
        self.assertTrue(self._in_loop(src))

    def test_while_loop_body_counts_as_loop(self) -> None:
        src = 'while(x){\n  list.addEventListener("click", h);\n}\n'
        self.assertTrue(self._in_loop(src))

    def test_for_of_body_counts_as_loop(self) -> None:
        src = 'for(const it of items){\n  list.addEventListener("click", h);\n}\n'
        self.assertTrue(self._in_loop(src))

    def test_for_in_body_counts_as_loop(self) -> None:
        src = 'for(const k in obj){\n  list.addEventListener("click", h);\n}\n'
        self.assertTrue(self._in_loop(src))

    def test_binding_after_for_header_is_not_loop(self) -> None:
        """负向：循环体结束之后的绑定不算循环内。"""
        src = 'for(var i=0;i<n;i++){}\nlist.addEventListener("click", h);\n'
        self.assertFalse(self._in_loop(src))

    def test_create_element_inside_for_is_per_item(self) -> None:
        """目标随节点新建也不能顶掉循环内这个结论。"""
        src = ('for(var i=0;i<n;i++){\n'
               '  var d = document.createElement("div");\n'
               '  d.addEventListener("click", handle);\n'
               '}\n')
        self.assertEqual(scan_text(src, "fixture.js")[0].verdict, "per-item")


class ArrowAnonymousTest(unittest.TestCase):
    """第 2 条：箭头回调也算匿名，否则全局监听的泄漏会被降级。"""

    def test_arrow_callback_is_anonymous(self) -> None:
        src = 'document.addEventListener("keydown", ev => { close(); });\n'
        self.assertTrue(scan_text(src, "fixture.js")[0].anonymous)

    def test_paren_arrow_callback_is_anonymous(self) -> None:
        src = 'document.addEventListener("keydown", (ev) => { close(); });\n'
        self.assertTrue(scan_text(src, "fixture.js")[0].anonymous)

    def test_async_arrow_callback_is_anonymous(self) -> None:
        src = 'document.addEventListener("keydown", async ev => { close(); });\n'
        self.assertTrue(scan_text(src, "fixture.js")[0].anonymous)

    def test_named_handler_reference_is_not_anonymous(self) -> None:
        """负向：具名函数引用可以摘除，不算匿名。"""
        src = 'document.addEventListener("keydown", onKey);\n'
        self.assertFalse(scan_text(src, "fixture.js")[0].anonymous)

    def test_arrow_global_listener_in_render_fn_is_leak_risk(self) -> None:
        src = ('function renderBox(){\n'
               '  document.addEventListener("keydown", ev => { close(); });\n'
               '}\n')
        self.assertEqual(scan_text(src, "fixture.js")[0].verdict, "leak-risk")


class ArrowRenderFnTest(unittest.TestCase):
    """第 3 条：箭头函数赋值也要认成具名函数。"""

    def test_arrow_assigned_render_fn_is_named(self) -> None:
        src = ('const renderList = () => {\n'
               '  var el = document.getElementById("b");\n'
               '  el.addEventListener("click", h);\n'
               '};\n')
        binding = scan_text(src, "fixture.js")[0]
        self.assertEqual(binding.func, "renderList")
        self.assertTrue(binding.render_fn)
        self.assertEqual(binding.verdict, "render-path")

    def test_arrow_assigned_non_render_fn_is_not_render(self) -> None:
        """负向：非渲染名的箭头函数不该被当成渲染路径。"""
        src = ('const wireList = () => {\n'
               '  var el = document.getElementById("b");\n'
               '  el.addEventListener("click", h);\n'
               '};\n')
        binding = scan_text(src, "fixture.js")[0]
        self.assertEqual(binding.func, "wireList")
        self.assertFalse(binding.render_fn)

    def test_expression_body_arrow_has_no_span(self) -> None:
        """负向：表达式体箭头没有块体，不该吞掉后面的代码。"""
        src = ('const twice = x => x * 2;\n'
               'card.addEventListener("click", h);\n')
        self.assertEqual(scan_text(src, "fixture.js")[0].func, "<module>")


class StringBracketTest(unittest.TestCase):
    """第 7 条：配平要跳过字符串，否则回调会被提前截断。"""

    def test_string_with_paren_does_not_truncate_callback(self) -> None:
        src = ('list.addEventListener("click", function(ev){\n'
               '  var s = "a) b } c";\n'
               '  var it = ev.target.closest(".row");\n'
               '});\n')
        self.assertEqual(scan_text(src, "fixture.js")[0].scope, "container")

    def test_template_literal_with_braces_is_skipped(self) -> None:
        src = ('list.addEventListener("click", function(ev){\n'
               '  var s = `x ${a} } y`;\n'
               '  var it = ev.target.closest(".row");\n'
               '});\n')
        self.assertEqual(scan_text(src, "fixture.js")[0].scope, "container")

    def test_string_with_paren_keeps_handler_detection(self) -> None:
        """负向对照：字符串里的括号不得让具名回调被误判成匿名。"""
        src = 'list.addEventListener("click", onRowClick);\nvar s = "a) b";\n'
        self.assertFalse(scan_text(src, "fixture.js")[0].anonymous)


class DelegateScopeTest(unittest.TestCase):
    """第 5 条：contains 只在事件对象上才算委托。"""

    def test_unrelated_contains_is_not_delegation(self) -> None:
        src = ('card.addEventListener("click", function(){\n'
               '  if(arr.contains(x)) log();\n'
               '});\n')
        self.assertEqual(scan_text(src, "fixture.js")[0].scope, "element")

    def test_event_target_closest_is_delegation(self) -> None:
        src = ('list.addEventListener("click", function(ev){\n'
               '  var it = ev.target.closest(".row");\n'
               '});\n')
        self.assertEqual(scan_text(src, "fixture.js")[0].scope, "container")

    def test_current_target_contains_is_delegation(self) -> None:
        src = ('panel.addEventListener("click", function(ev){\n'
               '  if(ev.currentTarget.contains(ev.target)) go();\n'
               '});\n')
        self.assertEqual(scan_text(src, "fixture.js")[0].scope, "container")


class PairedRemoveTest(unittest.TestCase):
    """第 6 条：摘除要同目标同事件，别的元素摘同名事件不解绑这一个。"""

    def test_other_element_remove_keeps_leak_risk(self) -> None:
        src = ('function ensureBox(){\n'
               '  document.addEventListener("keydown", function(ev){ close(); });\n'
               '}\n'
               'function other(){\n'
               '  otherEl.removeEventListener("keydown", handler);\n'
               '}\n')
        binding = scan_text(src, "fixture.js")[0]
        self.assertFalse(binding.paired_remove)
        self.assertEqual(binding.verdict, "leak-risk")

    def test_same_target_remove_clears_leak_risk(self) -> None:
        src = ('function ensureBox(){\n'
               '  document.addEventListener("keydown", onKey);\n'
               '  document.removeEventListener("keydown", onKey);\n'
               '}\n')
        binding = scan_text(src, "fixture.js")[0]
        self.assertTrue(binding.paired_remove)
        self.assertEqual(binding.verdict, "global-once")

    def test_different_event_remove_keeps_leak_risk(self) -> None:
        """负向：同目标但事件名不同，不算配对。"""
        src = ('function ensureBox(){\n'
               '  document.addEventListener("keydown", function(ev){ close(); });\n'
               '  document.removeEventListener("resize", onResize);\n'
               '}\n')
        self.assertFalse(scan_text(src, "fixture.js")[0].paired_remove)


class NestedRenderContextTest(unittest.TestCase):
    """渲染上下文看整条函数链：绑定写在内层小函数里，外层重建一样会反复安装。"""

    def test_binding_in_nested_fn_inside_render_is_render_path(self) -> None:
        src = ('function renderList(items){\n'
               '  function wire(it){\n'
               '    it.addEventListener("click", h);\n'
               '  }\n'
               '  items.forEach(wire);\n'
               '}\n')
        binding = scan_text(src, "fixture.js")[0]
        self.assertEqual(binding.func, "wire")
        self.assertTrue(binding.render_fn)
        self.assertEqual(binding.verdict, "render-path")

    def test_binding_in_nested_fn_outside_render_is_not_render_path(self) -> None:
        """负向：外层不叫渲染名时，不能因为嵌套就报渲染路径。"""
        src = ('function wireList(items){\n'
               '  function wire(it){\n'
               '    it.addEventListener("click", h);\n'
               '  }\n'
               '  items.forEach(wire);\n'
               '}\n')
        binding = scan_text(src, "fixture.js")[0]
        self.assertFalse(binding.render_fn)
        self.assertEqual(binding.verdict, "ok")


class ObjectMethodRenderTest(unittest.TestCase):
    """对象方法两种写法都要认成具名函数。"""

    def test_shorthand_object_method_is_named(self) -> None:
        src = ('var ui = {\n'
               '  renderPanel(){\n'
               '    var el = document.getElementById("p");\n'
               '    el.addEventListener("click", h);\n'
               '  }\n'
               '};\n')
        binding = scan_text(src, "fixture.js")[0]
        self.assertEqual(binding.func, "renderPanel")
        self.assertEqual(binding.verdict, "render-path")

    def test_function_valued_object_method_is_named(self) -> None:
        src = ('var ui = {\n'
               '  renderPanel: function(){\n'
               '    var el = document.getElementById("p");\n'
               '    el.addEventListener("click", h);\n'
               '  }\n'
               '};\n')
        binding = scan_text(src, "fixture.js")[0]
        self.assertEqual(binding.func, "renderPanel")
        self.assertEqual(binding.verdict, "render-path")

    def test_control_flow_header_is_not_a_method(self) -> None:
        """负向：`if(...){` 这类语句头不能被当成对象方法。"""
        src = ('if(x){\n'
               '  card.addEventListener("click", h);\n'
               '}\n')
        self.assertEqual(scan_text(src, "fixture.js")[0].func, "<module>")


class NamedGlobalListenerTest(unittest.TestCase):
    """具名回调只代表「能摘除」，不代表「已摘除」。"""

    def test_named_global_listener_in_render_fn_is_leak_risk(self) -> None:
        src = ('function renderBox(){\n'
               '  document.addEventListener("keydown", onKey);\n'
               '}\n')
        binding = scan_text(src, "fixture.js")[0]
        self.assertFalse(binding.anonymous)
        self.assertEqual(binding.verdict, "leak-risk")

    def test_named_global_listener_with_remove_is_global_once(self) -> None:
        """负向：真摘了就不算泄漏。"""
        src = ('function renderBox(){\n'
               '  document.addEventListener("keydown", onKey);\n'
               '  document.removeEventListener("keydown", onKey);\n'
               '}\n')
        self.assertEqual(scan_text(src, "fixture.js")[0].verdict, "global-once")

    def test_named_global_listener_at_module_level_is_global_once(self) -> None:
        """负向：模块级只绑一次，具名与否都不算泄漏。"""
        src = 'document.addEventListener("keydown", onKey);\n'
        binding = scan_text(src, "fixture.js")[0]
        self.assertFalse(binding.render_fn)
        self.assertEqual(binding.verdict, "global-once")


class ReadGuideTest(unittest.TestCase):
    """第 10 条：文案里的类别数要和常量一致，不靠手写。"""

    def test_read_guide_counts_match_constants(self) -> None:
        guide = read_guide()
        self.assertIn(str(len(REVIEW_VERDICTS)), guide)
        self.assertIn(str(len(EXCLUDED_VERDICTS)), guide)
        for name in REVIEW_VERDICTS:
            self.assertIn(name, guide)


if __name__ == "__main__":
    unittest.main()
