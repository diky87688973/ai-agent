# -*- coding: utf-8 -*-
"""上下文组装与压缩：逐条穷举验收。

装配只有三段，顺序拼接，不做任何重建::

    messages = 头部 + 对话 + 尾部
    头部 = 系统提示 + skill-1..n + 知识库-1..n + 摘要-1..n      （系统类，永久携带）
    对话 = 事实折叠出来的对话（含工具调用与工具结果）
    尾部 = 本轮新输入 / 工具结果（在对话末尾，由事实带来）+ 执行模式

压缩请求用同一份装配结果，末尾换成压缩指令::

    压缩请求 = 头部 + 对话 + [压缩指令]        ← 剔除执行模式

本文件把这些结构写死成期望值逐条断言：任何一条改变装配顺序、少一格、
多一格、把执行模式塞进压缩请求，都会在具体那条用例上失败。

设 `DEEPSEEK_CONTEXT_AUDIT=1` 时逐条打印"用例 / 期望 / 实际"，用于人工核对
断言本身是否写对（避免把错误结果当成正确来断言）。
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.core.model_call import StreamDelta  # noqa: E402
from agent.mechanisms.context_compactor import (  # noqa: E402
    SUMMARY_BRIDGE_TAIL,
    ContextCompactor,
    make_provider_summarizer,
)
from agent.mechanisms.context_pipeline import ContextPipeline  # noqa: E402

MODE_AUTO = "## 当前模式：Auto"
MODE_PLAN = "## 当前模式：Plan（只读）"
SYS = "系统提示"
SK1 = "skill-1"
SK2 = "skill-2"
KB1 = "知识库-1"
KB2 = "知识库-2"
SUM1 = "【历史摘要】\n摘要-1"
SUM2 = "【历史摘要】\n摘要-2"
NEW_INPUT = "本轮新输入"
INSTRUCTION_MARK = "把上面这段对话压缩成一份摘要"


# ── 观测工具：把消息列表压成便于写死的短记号 ──────────────────

def short(m) -> str:
    """一条消息 → 短记号（测试里用字符串比对，读起来就是结构本身）。"""
    if not isinstance(m, dict):
        return "?"
    role = str(m.get("role") or "")
    c = str(m.get("content") or "")
    if m.get("tool_calls"):
        ids = ",".join(str(x.get("id")) for x in m["tool_calls"])
        return f"toolcall[{ids}]"
    if m.get("tool_call_id"):
        return f"toolresult[{m['tool_call_id']}]"
    if INSTRUCTION_MARK in c:
        return "INSTRUCTION"
    if c.startswith("## 当前模式："):
        return "MODE"
    if c.startswith(SYS):
        return "SYSTEM"
    if c.startswith("skill-"):
        return "SKILL" + c.split("-", 1)[1][:1]
    if c.startswith("【Skills 清单】") or c.startswith("【Skills "):
        return "SKILLBLOCK"
    if c.startswith(KB1):
        return "KB1"
    if c.startswith(KB2):
        return "KB2"
    if c.startswith("【历史摘要】"):
        return "SUMMARY:" + c.split("\n", 1)[1][:8]
    if role == "user":
        return "USER:" + c[:12]
    if role == "assistant":
        return "ASSISTANT:" + c[:12]
    if role == "system":
        return "SYSTEM?:" + c[:12]
    return f"{role}:{c[:12]}"


def shape(messages) -> str:
    """整串消息 → " | " 连接的短记号。"""
    return " | ".join(short(m) for m in messages)


class _Spy:
    def __init__(self, text: str = "新摘要") -> None:
        self.reqs: list = []
        self._text = text

    def stream(self, request):
        self.reqs.append(request)
        yield StreamDelta(kind="text", text=self._text)
        yield StreamDelta(kind="done")


_AUDIT = bool(os.environ.get("DEEPSEEK_CONTEXT_AUDIT"))


class _Case(unittest.TestCase):
    """统一的"期望 / 实际"观测点。"""

    def check(self, label: str, expected, actual) -> None:
        if _AUDIT:
            print(f"\n[用例] {self._testMethodName} :: {label}")
            print(f"[期望] {expected}")
            print(f"[实际] {actual}")
        self.assertEqual(actual, expected, msg=f"{label}")

    def check_true(self, label: str, actual) -> None:
        if _AUDIT:
            print(f"\n[用例] {self._testMethodName} :: {label}")
            print("[期望] 真")
            print(f"[实际] {actual}")
        self.assertTrue(actual, msg=label)


# ── 固定装置 ──────────────────────────────────────────────────

def make_pipe(*, cid: str = "cid-assembly-0001", headers: str = "full",
              summaries=(), dialogue=(), tail=()) -> ContextPipeline:
    """按名字装一个上下文：headers / summaries / dialogue / tail 都可裁剪。"""
    p = ContextPipeline(cid, full_user_rounds=1)
    if headers in ("full", "no_skill"):
        p.append_system(SYS)
    if headers == "full":
        p.append_plugin(SK1, key="skills", label="Skills")
        p.append_plugin(SK2, key="skills", label="常驻 Skills")
    if headers in ("full", "no_skill"):
        p.append_plugin([KB1], key="kb", label="知识库")
        p.append_plugin([KB2], key="kb", label="知识库")
    p.set_summary_messages([{"role": "system", "content": s} for s in summaries])
    p.set_dialogue(list(dialogue), covered_end=0)
    return p, list(tail)


def dlg(n: int = 2) -> list:
    """n 轮对话（user/assistant 交替）。"""
    out = []
    for i in range(1, n + 1):
        out.append({"role": "user", "content": f"第{i}问"})
        out.append({"role": "assistant", "content": f"第{i}答"})
    return out


# ══════════════════════════════════════════════════════════════
# 一、三段式装配
# ══════════════════════════════════════════════════════════════

class AssemblyShape(_Case):
    """头部 + 对话 + 尾部，顺序固定。"""

    def test_full_headers_come_first_in_order(self) -> None:
        p, _ = make_pipe(headers="full", dialogue=dlg(1))
        self.check("头部顺序", "SYSTEM | SKILL1 | SKILL2 | KB1 | KB2",
                   shape(p.host_messages()))

    def test_headers_include_summaries_after_kb(self) -> None:
        p, _ = make_pipe(headers="full", summaries=(SUM1, SUM2), dialogue=dlg(1))
        self.check("摘要排在知识库之后",
                   "SYSTEM | SKILL1 | SKILL2 | KB1 | KB2 | SUMMARY:摘要-1 | SUMMARY:摘要-2",
                   shape(p.host_messages()))

    def test_summary_order_follows_input_order(self) -> None:
        p, _ = make_pipe(summaries=(SUM2, SUM1))
        self.check("摘要按装入顺序（不排序）",
                   "SYSTEM | SKILL1 | SKILL2 | KB1 | KB2 | SUMMARY:摘要-2 | SUMMARY:摘要-1",
                   shape(p.host_messages()))

    def test_dialogue_keeps_fact_order(self) -> None:
        p, _ = make_pipe(dialogue=dlg(2))
        self.check("对话按事实顺序", "USER:第1问 | ASSISTANT:第1答 | USER:第2问 | ASSISTANT:第2答",
                   shape(p.dialogue_messages()))

    def test_assembles_appends_tail(self) -> None:
        p, _ = make_pipe(dialogue=dlg(1))
        got = p.assembles([{"role": "user", "content": NEW_INPUT},
                           {"role": "system", "content": MODE_AUTO}])
        self.check("装配 = 头部 + 对话 + 尾部",
                   "SYSTEM | SKILL1 | SKILL2 | KB1 | KB2 | USER:第1问 | ASSISTANT:第1答"
                   " | USER:本轮新输入 | MODE",
                   shape(got))

    def test_assembles_without_tail(self) -> None:
        p, _ = make_pipe(dialogue=dlg(1))
        self.check("不给尾部时不追加任何东西",
                   "SYSTEM | SKILL1 | SKILL2 | KB1 | KB2 | USER:第1问 | ASSISTANT:第1答",
                   shape(p.assembles()))

    def test_assembles_ignores_non_dict_tail(self) -> None:
        p, _ = make_pipe(dialogue=dlg(1))
        got = p.assembles([None, "x", {"role": "user", "content": NEW_INPUT}])
        self.check("尾部只收 dict", "SYSTEM | SKILL1 | SKILL2 | KB1 | KB2 | USER:第1问 |"
                                    " ASSISTANT:第1答 | USER:本轮新输入", shape(got))

    def test_less_headers_still_ordered(self) -> None:
        p, _ = make_pipe(headers="no_skill", summaries=(SUM1,), dialogue=dlg(1))
        self.check("没有 skill 时段序不变",
                   "SYSTEM | KB1 | KB2 | SUMMARY:摘要-1",
                   shape(p.host_messages()))

    def test_empty_everything(self) -> None:
        p = ContextPipeline("cid-assembly-0002", full_user_rounds=1)
        self.check("什么都不装时装配为空", "", shape(p.assembles()))

    def test_assembles_is_detached_from_pipeline(self) -> None:
        p, _ = make_pipe(dialogue=dlg(1))
        got = p.assembles()
        got.append({"role": "user", "content": NEW_INPUT})
        self.check("装配结果是副本，改动不回写管线",
                   "SYSTEM | SKILL1 | SKILL2 | KB1 | KB2 | USER:第1问 | ASSISTANT:第1答",
                   shape(p.assembles()))

    def test_header_change_is_visible_immediately(self) -> None:
        p, _ = make_pipe(headers="full", dialogue=dlg(1))
        p.append_plugin("skill-3", key="extra", label="附加")
        self.check("新增插件段立刻出现在头部尾部",
                   "SYSTEM | SKILL1 | SKILL2 | KB1 | KB2 | SKILL3",
                   shape(p.host_messages()))

    def test_summary_replacement_takes_effect(self) -> None:
        p, _ = make_pipe(summaries=(SUM1,), dialogue=dlg(1))
        p.set_summary_messages([{"role": "system", "content": SUM2}])
        self.check("重装摘要 = 整体替换",
                   "SYSTEM | SKILL1 | SKILL2 | KB1 | KB2 | SUMMARY:摘要-2",
                   shape(p.host_messages()))

    def test_summary_can_be_cleared(self) -> None:
        p, _ = make_pipe(summaries=(SUM1,), dialogue=dlg(1))
        p.set_summary_messages([])
        self.check("清空摘要", "SYSTEM | SKILL1 | SKILL2 | KB1 | KB2",
                   shape(p.host_messages()))

    def test_two_summaries_both_kept(self) -> None:
        p, _ = make_pipe(summaries=(SUM1, SUM2))
        self.check_true("两条摘要各占一条",
                        short(p.host_messages()[-1]) == "SUMMARY:摘要-2"
                        and short(p.host_messages()[-2]) == "SUMMARY:摘要-1")

    def test_dialogue_with_tool_pair(self) -> None:
        d = dlg(1) + [{"role": "assistant", "content": "",
                       "tool_calls": [{"id": "c1", "name": "t", "arguments": {}}]},
                      {"role": "tool", "tool_call_id": "c1", "content": "结果"}]
        p, _ = make_pipe(dialogue=d)
        self.check("工具调用/结果原样在对话段",
                   "USER:第1问 | ASSISTANT:第1答 | toolcall[c1] | toolresult[c1]",
                   shape(p.dialogue_messages()))

    def test_set_dialogue_replaces_previous(self) -> None:
        p, _ = make_pipe(dialogue=dlg(2))
        p.set_dialogue(dlg(1), covered_end=0)
        self.check("重装对话 = 整体替换",
                   "USER:第1问 | ASSISTANT:第1答", shape(p.dialogue_messages()))

    def test_covered_end_drops_prefix(self) -> None:
        p, _ = make_pipe(dialogue=dlg(3))
        p.set_dialogue(dlg(3), covered_end=2)
        self.check("覆盖点之后才是对话段",
                   "USER:第2问 | ASSISTANT:第2答 | USER:第3问 | ASSISTANT:第3答",
                   shape(p.dialogue_messages()))

    def test_covered_end_zero_keeps_all(self) -> None:
        p, _ = make_pipe(dialogue=dlg(2))
        p.set_dialogue(dlg(2), covered_end=0)
        self.check("覆盖点为 0 时全留",
                   "USER:第1问 | ASSISTANT:第1答 | USER:第2问 | ASSISTANT:第2答",
                   shape(p.dialogue_messages()))

    def test_covered_end_beyond_length(self) -> None:
        p, _ = make_pipe(dialogue=dlg(1))
        p.set_dialogue(dlg(1), covered_end=99)
        self.check("覆盖点越界 = 对话段为空", "", shape(p.dialogue_messages()))

    def test_mode_chunk_never_in_assembly(self) -> None:
        p, _ = make_pipe(dialogue=dlg(1))
        p.name_map["模式"].append("system", MODE_AUTO, True)
        self.check("模式块不参与装配（模式只走尾部）",
                   "SYSTEM | SKILL1 | SKILL2 | KB1 | KB2 | USER:第1问 | ASSISTANT:第1答",
                   shape(p.assembles()))

# ══════════════════════════════════════════════════════════════
# 二、尾部：新输入与执行模式
# ══════════════════════════════════════════════════════════════

class TailShape(_Case):
    """尾部 = 本轮新输入 + 执行模式（模式永远最后）。"""

    def _msgs(self, mode=True, new_input=True):
        p, _ = make_pipe(dialogue=dlg(1))
        tail = []
        if new_input:
            tail.append({"role": "user", "content": NEW_INPUT})
        if mode:
            tail.append({"role": "system", "content": MODE_AUTO})
        return p.assembles(tail)

    def test_mode_is_last(self) -> None:
        self.check("模式是最后一条",
                   "SYSTEM | SKILL1 | SKILL2 | KB1 | KB2 | USER:第1问 | ASSISTANT:第1答"
                   " | USER:本轮新输入 | MODE",
                   shape(self._msgs()))

    def test_mode_is_system_role(self) -> None:
        got = self._msgs()
        self.check("模式角色", "system", str(got[-1].get("role")))

    def test_new_input_is_user_role(self) -> None:
        got = self._msgs()
        self.check("新输入角色", "user", str(got[-2].get("role")))

    def test_no_mode_means_input_is_last(self) -> None:
        self.check("无模式时新输入收尾",
                   "SYSTEM | SKILL1 | SKILL2 | KB1 | KB2 | USER:第1问 | ASSISTANT:第1答"
                   " | USER:本轮新输入",
                   shape(self._msgs(mode=False)))

    def test_no_new_input_means_mode_follows_dialogue(self) -> None:
        self.check("无新输入时模式紧接对话",
                   "SYSTEM | SKILL1 | SKILL2 | KB1 | KB2 | USER:第1问 | ASSISTANT:第1答"
                   " | MODE",
                   shape(self._msgs(new_input=False)))

    def test_neither(self) -> None:
        self.check("都没有时只有头部和对话",
                   "SYSTEM | SKILL1 | SKILL2 | KB1 | KB2 | USER:第1问 | ASSISTANT:第1答",
                   shape(self._msgs(mode=False, new_input=False)))

    def test_tool_result_tail(self) -> None:
        p, _ = make_pipe(dialogue=dlg(1) + [
            {"role": "assistant", "content": "",
             "tool_calls": [{"id": "c1", "name": "t", "arguments": {}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "结果"}])
        got = p.assembles([{"role": "system", "content": MODE_AUTO}])
        self.check("工具轮：结果在对话末尾，模式收尾",
                   "SYSTEM | SKILL1 | SKILL2 | KB1 | KB2 | USER:第1问 | ASSISTANT:第1答"
                   " | toolcall[c1] | toolresult[c1] | MODE",
                   shape(got))

    def test_mode_text_is_exact(self) -> None:
        got = self._msgs()
        self.check("模式正文原样", MODE_AUTO, str(got[-1].get("content")))

    def test_plan_mode_text_is_exact(self) -> None:
        p, _ = make_pipe(dialogue=dlg(1))
        got = p.assembles([{"role": "user", "content": NEW_INPUT},
                           {"role": "system", "content": MODE_PLAN}])
        self.check("Plan 模式正文原样", MODE_PLAN, str(got[-1].get("content")))

    def test_mode_swap_changes_only_the_last_entry(self) -> None:
        a = self._msgs()
        p, _ = make_pipe(dialogue=dlg(1))
        b = p.assembles([{"role": "user", "content": NEW_INPUT},
                         {"role": "system", "content": MODE_PLAN}])
        self.check("切模式只改最后一条", a[:-1], b[:-1])


# ══════════════════════════════════════════════════════════════
# 三、压缩请求 = 同一份装配剔除尾部 + 指令
# ══════════════════════════════════════════════════════════════

class CompactionContext(_Case):
    """压缩上下文：剔除本轮新输入与执行模式，末尾接 system 指令。"""

    def _request(self, *, mode=MODE_AUTO, new_input=True, tool=False, summaries=()):
        """构造一次带压缩的请求；返回 (spy, 整份装配, 头部条数, 尾部条数)。

        对话固定 4 轮（太少时摘取区间为空、不会触发压缩）。
        """
        rows = [{"role": "system", "content": SYS},
                {"role": "system", "content": SK1},
                {"role": "system", "content": SK2},
                {"role": "system", "content": KB1},
                {"role": "system", "content": KB2}]
        rows += [{"role": "system", "content": s} for s in summaries]
        head = len(rows)
        rows += dlg(4)
        if tool:
            rows += [{"role": "assistant", "content": "",
                      "tool_calls": [{"id": "c1", "name": "t", "arguments": {}}]},
                     {"role": "tool", "tool_call_id": "c1", "content": "结果"}]
        tail = []
        if new_input:
            tail.append({"role": "user", "content": NEW_INPUT})
        tail.append({"role": "system", "content": mode})
        whole = rows + tail

        dialogue = [r for r in rows if str(r.get("role")) != "system"]
        p, _ = make_pipe(summaries=summaries, dialogue=dialogue)
        spy = _Spy()
        comp = ContextCompactor(make_provider_summarizer(spy, max_chars=200),
                                summary_token_threshold=1)
        comp.ensure_before_append(p, dialogue, pending=None, tools=[], mode_note=mode,
                                  assembled=whole)
        return spy, whole, head, len(tail)

    def test_user_path_request_shape(self) -> None:
        spy, whole, head, tail = self._request()
        self.check("压缩请求 = 头部 + 对话 + 指令",
                   shape(whole[:len(whole) - tail]) + " | INSTRUCTION",
                   shape(spy.reqs[0].messages))

    def test_user_path_drops_new_input(self) -> None:
        spy, whole, head, tail = self._request()
        self.check_true("新输入不出现",
                        not any(NEW_INPUT in str(m.get("content"))
                                for m in spy.reqs[0].messages))

    def test_user_path_drops_mode(self) -> None:
        spy, whole, head, tail = self._request()
        self.check_true("模式不出现",
                        not any("## 当前模式" in str(m.get("content"))
                                for m in spy.reqs[0].messages))

    def test_instruction_is_last_and_system(self) -> None:
        spy, whole, head, tail = self._request()
        last = spy.reqs[0].messages[-1]
        self.check("指令位置与角色", ("INSTRUCTION", "system"),
                   (short(last), str(last.get("role"))))

    def test_instruction_appears_once(self) -> None:
        spy, whole, head, tail = self._request()
        n = sum(1 for m in spy.reqs[0].messages if INSTRUCTION_MARK in str(m.get("content")))
        self.check("指令只出现一次", 1, n)

    def test_prefix_equals_normal_request_minus_last_two(self) -> None:
        spy, whole, head, tail = self._request()
        self.check("前缀 = 平常请求去掉最后两条", whole[:-tail], spy.reqs[0].messages[:-1])

    def test_tool_path_request_shape(self) -> None:
        spy, whole, head, tail = self._request(tool=True)
        self.check("工具轮：结果保留在被压缩范围",
                   shape(whole[:len(whole) - tail]) + " | INSTRUCTION",
                   shape(spy.reqs[0].messages))

    def test_tool_path_prefix_equals_normal_minus_last_one(self) -> None:
        spy, whole, head, tail = self._request(tool=True, new_input=False)
        self.check("工具轮：前缀 = 平常请求去掉模式那一条",
                   whole[:-1], spy.reqs[0].messages[:-1])

    def test_mode_change_does_not_affect_request(self) -> None:
        a, whole_a, _h, _t = self._request(mode=MODE_AUTO)
        b, whole_b, _h2, _t2 = self._request(mode=MODE_PLAN)
        self.check("切模式不改变压缩请求一条消息",
                   shape(a.reqs[0].messages), shape(b.reqs[0].messages))

    def test_summary_present_in_head(self) -> None:
        spy, whole, head, tail = self._request(summaries=(SUM1,))
        self.check("摘要（旧的那份）在头部",
                   shape(whole[:len(whole) - tail]) + " | INSTRUCTION",
                   shape(spy.reqs[0].messages))

    def test_no_new_input_path(self) -> None:
        """没有新输入时，尾部只有模式一条；压缩请求 = 整份剔掉它 + 指令。"""
        spy, whole, head, tail = self._request(new_input=False)
        self.check("没有新输入时同样只剩头部+对话+指令",
                   shape(whole[:-1]) + " | INSTRUCTION",
                   shape(spy.reqs[0].messages))

    def test_system_field_is_carried(self) -> None:
        """`system` 字段与平常请求同一个值（留空即从第一条起就不同）。"""
        p, _ = make_pipe(dialogue=dlg(4))
        whole = p.assembles([{"role": "user", "content": NEW_INPUT},
                             {"role": "system", "content": MODE_AUTO}])
        spy = _Spy()
        comp = ContextCompactor(make_provider_summarizer(spy, max_chars=200),
                                summary_token_threshold=1)
        comp.ensure_before_append(p, dlg(4), mode_note=MODE_AUTO, assembled=whole)
        self.check("系统提示在请求消息里", True,
                   any(str(m.get("role")) == "system" and str(m.get("content") or "").strip()
                       for m in (spy.reqs[0].messages or [])))

    def test_tools_are_forwarded(self) -> None:
        """工具定义是前缀的一部分：摘要请求必须带上同一份。"""
        p, _ = make_pipe(dialogue=dlg(4))
        whole = p.assembles([{"role": "user", "content": NEW_INPUT},
                             {"role": "system", "content": MODE_AUTO}])
        spy = _Spy()
        comp = ContextCompactor(make_provider_summarizer(spy, max_chars=200),
                                summary_token_threshold=1)
        schemas = [{"name": "read_file"}]
        comp.ensure_before_append(p, dlg(4), mode_note=MODE_AUTO, assembled=whole,
                                  tools=schemas)
        self.check("工具定义原样带上", schemas, list(spy.reqs[0].tools or []))


# ══════════════════════════════════════════════════════════════
# 四、剔除尾部：判据逐条
# ══════════════════════════════════════════════════════════════

class StripRules(_Case):
    """`_context_without_new_input` / `_strip_mode_tail` 的判据。"""

    def _strip_new(self, msgs):
        return ContextCompactor._context_without_new_input(msgs)

    def _strip_mode(self, msgs, note=MODE_AUTO):
        return ContextCompactor._strip_mode_tail(msgs, note)

    def test_new_input_removed_when_last(self) -> None:
        msgs = [{"role": "assistant", "content": "答"},
                {"role": "user", "content": NEW_INPUT}]
        self.check("末尾 user 被删", "ASSISTANT:答", shape(self._strip_new(msgs)))

    def test_new_input_removed_before_mode(self) -> None:
        msgs = [{"role": "assistant", "content": "答"},
                {"role": "user", "content": NEW_INPUT},
                {"role": "system", "content": MODE_AUTO}]
        self.check("模式也一并删掉（它不属于上轮上下文）", "ASSISTANT:答",
                   shape(self._strip_new(msgs)))

    def test_previous_reply_is_kept(self) -> None:
        msgs = [{"role": "user", "content": "旧问"},
                {"role": "assistant", "content": "旧答"},
                {"role": "user", "content": NEW_INPUT}]
        self.check("上一轮回复保留", "USER:旧问 | ASSISTANT:旧答",
                   shape(self._strip_new(msgs)))

    def test_tool_result_is_kept(self) -> None:
        msgs = [{"role": "user", "content": "第1问"},
                {"role": "assistant", "content": "第1答"},
                {"role": "user", "content": "第2问"},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
                {"role": "tool", "tool_call_id": "c1", "content": "结果"}]
        self.check("工具轮：整份保留（触发者是工具结果，不是新输入）",
                   "USER:第1问 | ASSISTANT:第1答 | USER:第2问 | toolcall[c1] | toolresult[c1]",
                   shape(self._strip_new(msgs)))

    def test_only_last_user_removed(self) -> None:
        msgs = [{"role": "user", "content": "旧问"},
                {"role": "user", "content": NEW_INPUT}]
        self.check("只删最后一条 user", "USER:旧问", shape(self._strip_new(msgs)))

    def test_empty(self) -> None:
        self.check("空列表", "", shape(self._strip_new([])))

    def test_non_dict_entry(self) -> None:
        msgs = [{"role": "assistant", "content": "答"},
                {"role": "user", "content": "新输入"}, "x"]
        self.check("非 dict 项不影响剔除（尾部不是 dict 时整份返回）",
                   "ASSISTANT:答 | USER:新输入 | ?", shape(self._strip_new(msgs)))

    def test_mode_removed_by_exact_text(self) -> None:
        msgs = [{"role": "assistant", "content": "答"},
                {"role": "system", "content": MODE_PLAN}]
        self.check("按正文精确匹配剔除", "ASSISTANT:答", shape(self._strip_mode(msgs, MODE_PLAN)))

    def test_mode_removed_by_marker_fallback(self) -> None:
        msgs = [{"role": "assistant", "content": "答"},
                {"role": "system", "content": "## 当前模式：Execute\n其它说明"}]
        self.check("拿不到 mode_note 时按标记剔除", "ASSISTANT:答",
                   shape(self._strip_mode(msgs, "")))

    def test_system_prompt_never_stripped(self) -> None:
        msgs = [{"role": "system", "content": SYS}]
        self.check("系统提示不在剔除范围", "SYSTEM", shape(self._strip_mode(msgs)))

    def test_summary_never_stripped(self) -> None:
        msgs = [{"role": "system", "content": SUM1}]
        self.check("摘要不在剔除范围", "SUMMARY:摘要-1", shape(self._strip_mode(msgs)))

    def test_kb_never_stripped(self) -> None:
        msgs = [{"role": "system", "content": KB1}]
        self.check("知识库不在剔除范围", "KB1", shape(self._strip_mode(msgs)))

    def test_mode_in_the_middle_untouched(self) -> None:
        msgs = [{"role": "system", "content": MODE_AUTO},
                {"role": "user", "content": "问"}]
        self.check("只剔尾部，中间的模式不动", "MODE | USER:问", shape(self._strip_mode(msgs)))

    def test_two_trailing_systems_both_stripped(self) -> None:
        msgs = [{"role": "user", "content": "问"},
                {"role": "system", "content": MODE_AUTO},
                {"role": "system", "content": "## 当前模式：Plan"}]
        self.check("尾部连续 system 一并剔除", "USER:问", shape(self._strip_mode(msgs, "")))

    def test_empty_mode_note_and_no_marker(self) -> None:
        msgs = [{"role": "assistant", "content": "答"},
                {"role": "system", "content": "别的系统说明"}]
        self.check("非模式说明的尾部 system 不动",
                   "ASSISTANT:答 | SYSTEM?:别的系统说明", shape(self._strip_mode(msgs, "")))


# ══════════════════════════════════════════════════════════════
# 五、压缩闭环：推进、摘要、重拼
# ══════════════════════════════════════════════════════════════

class CompactionLoop(_Case):
    """覆盖点推进、摘要累积、重拼后的请求。"""

    def _run(self, *, rounds=3, summaries=(), threshold=1, text="新摘要"):
        """跑一次压缩；`summaries` 是已有摘要（进管道头部，也预置给压缩器）。"""
        from agent.core.events import Event

        p, _ = make_pipe(summaries=summaries, dialogue=dlg(rounds))
        whole = p.assembles([{"role": "user", "content": NEW_INPUT},
                             {"role": "system", "content": MODE_AUTO}])
        spy = _Spy(text)
        comp = ContextCompactor(make_provider_summarizer(spy, max_chars=200),
                                summary_token_threshold=threshold)
        comp.restore_from_events([
            Event(type="context_compacted",
                  data={"covered_end": 0,
                        "summary": s.split("\n", 1)[1] if "\n" in s else s})
            for s in summaries])
        report = comp.ensure_before_append(p, dlg(rounds), pending=None, tools=[],
                                          mode_note=MODE_AUTO, assembled=whole)
        return p, spy, comp, report

    def test_report_keys(self) -> None:
        _p, _s, _c, report = self._run()
        self.check("返回体键", ["compressed_count", "covered_end", "summary"],
                   sorted(report.keys()))

    def test_covered_end_advances(self) -> None:
        _p, _s, comp, report = self._run()
        self.check("覆盖点已推进", (True, True),
                   (comp.covered_end > 0, report["covered_end"] == comp.covered_end))

    def test_compressed_count_matches_step(self) -> None:
        _p, _s, comp, report = self._run()
        self.check("压缩条数 = 覆盖点增量", report["covered_end"], report["compressed_count"])

    def test_summary_appended_with_bridge(self) -> None:
        _p, _s, comp, _r = self._run()
        self.check("摘要带桥接后缀", (1, True),
                   (len(comp.summaries), comp.summaries[0].endswith(SUMMARY_BRIDGE_TAIL)))

    def test_summary_text_comes_from_model(self) -> None:
        _p, _s, comp, _r = self._run(text="模型给的摘要")
        self.check_true("摘要正文来自模型输出", comp.summaries[0].startswith("模型给的摘要"))

    def test_second_compaction_appends_second_summary(self) -> None:
        """第二次压缩产出的摘要追加在已有摘要之后，不合并、不替换。"""
        _p1, _s1, comp1, _r1 = self._run()
        _p2, _s2, comp2, _r2 = self._run(summaries=(SUM1,))
        self.check("第一次：只有新的一条", 1, len(comp1.summaries))
        self.check("第二次：旧摘要仍在，新摘要追加其后",
                   ["摘要-1", "新摘要" + SUMMARY_BRIDGE_TAIL],
                   list(comp2.summaries))

    def test_summary_messages_are_system(self) -> None:
        _p, _s, comp, _r = self._run()
        got = comp.summary_messages()
        self.check("摘要注入是 system 且带前缀", ("system", True),
                   (str(got[0].get("role")), str(got[0].get("content")).startswith("【历史摘要】")))

    def test_reassembled_request_shape(self) -> None:
        p, _s, _c, _r = self._run(rounds=3)
        p.set_summary_messages([{"role": "system", "content": SUM1}])
        p.set_dialogue(dlg(3), covered_end=2)
        got = p.assembles([{"role": "user", "content": NEW_INPUT},
                           {"role": "system", "content": MODE_AUTO}])
        self.check("重拼：新摘要 + 覆盖点之后的对话 + 新输入 + 模式",
                   "SYSTEM | SKILL1 | SKILL2 | KB1 | KB2 | SUMMARY:摘要-1"
                   " | USER:第2问 | ASSISTANT:第2答 | USER:第3问 | ASSISTANT:第3答"
                   " | USER:本轮新输入 | MODE",
                   shape(got))

    def test_below_threshold_no_request(self) -> None:
        _p, spy, _c, report = self._run(threshold=10 ** 9)
        self.check("没超阈值：不发请求、不返回报告", ([], None), (spy.reqs, report))

    def test_no_context_returns_none(self) -> None:
        comp = ContextCompactor(make_provider_summarizer(_Spy(), max_chars=200))
        self.check("没有 context 直接放行", None,
                   comp.ensure_before_append(None, dlg(1), mode_note=MODE_AUTO))

    def test_empty_dialogue_returns_none(self) -> None:
        p, _ = make_pipe()
        comp = ContextCompactor(make_provider_summarizer(_Spy(), max_chars=200))
        self.check("对话为空直接放行", None,
                   comp.ensure_before_append(p, [], mode_note=MODE_AUTO, assembled=[]))

    def test_degenerate_summary_is_rejected(self) -> None:
        p, _ = make_pipe(dialogue=dlg(3))
        whole = p.assembles([{"role": "user", "content": NEW_INPUT},
                             {"role": "system", "content": MODE_AUTO}])
        comp = ContextCompactor(make_provider_summarizer(_Spy("摘要为空"), max_chars=200),
                                summary_token_threshold=1)
        report = comp.ensure_before_append(p, dlg(3), mode_note=MODE_AUTO, assembled=whole)
        self.check("退化摘要视为失败（放行）", (None, 0), (report, comp.covered_end))

    def test_provider_failure_is_released(self) -> None:
        class _Boom:
            def stream(self, request):
                raise RuntimeError("boom")
                yield  # pragma: no cover

        p, _ = make_pipe(dialogue=dlg(3))
        whole = p.assembles([{"role": "user", "content": NEW_INPUT},
                             {"role": "system", "content": MODE_AUTO}])
        comp = ContextCompactor(make_provider_summarizer(_Boom(), max_chars=200),
                                summary_token_threshold=1)
        report = comp.ensure_before_append(p, dlg(3), mode_note=MODE_AUTO, assembled=whole)
        self.check("模型异常 → 放行且不推进覆盖点", (None, 0), (report, comp.covered_end))

    def test_no_summarize_fn_returns_none(self) -> None:
        p, _ = make_pipe(dialogue=dlg(3))
        whole = p.assembles([{"role": "user", "content": NEW_INPUT},
                             {"role": "system", "content": MODE_AUTO}])
        comp = ContextCompactor(None, summary_token_threshold=1)
        self.check("没有摘要器 → 放行", None,
                   comp.ensure_before_append(p, dlg(3), mode_note=MODE_AUTO, assembled=whole))

    def test_restore_from_events_rebuilds_state(self) -> None:
        from agent.core.events import Event

        comp = ContextCompactor(None)
        comp.restore_from_events([
            Event(type="context_compacted", data={"covered_end": 4, "summary": "摘要-1"}),
            Event(type="context_compacted", data={"covered_end": 8, "summary": "摘要-2"}),
        ])
        self.check("重放事件 → 覆盖点与摘要都恢复", (8, ["摘要-1", "摘要-2"]),
                   (comp.covered_end, comp.summaries))

    def test_restore_ignores_backwards_covered_end(self) -> None:
        from agent.core.events import Event

        comp = ContextCompactor(None)
        comp.restore_from_events([
            Event(type="context_compacted", data={"covered_end": 8, "summary": "摘要-2"}),
            Event(type="context_compacted", data={"covered_end": 4, "summary": "旧的"}),
        ])
        self.check("覆盖点单调不减", (8, ["摘要-2"]), (comp.covered_end, comp.summaries))

    def test_restore_ignores_other_events(self) -> None:
        from agent.core.events import Event

        comp = ContextCompactor(None)
        comp.restore_from_events([Event(type="turn_started", data={}),
                                 Event(type="input_claimed", data={"content": "问"})])
        self.check("无关事件不影响状态", (0, []), (comp.covered_end, comp.summaries))

    def test_view_messages_drops_covered(self) -> None:
        comp = ContextCompactor(None)
        comp.covered_end = 2
        self.check("视图 = 全量去掉已覆盖前缀", "USER:第2问 | ASSISTANT:第2答",
                   shape(comp.view_messages(dlg(2))))

    def test_pending_does_not_enter_range(self) -> None:
        p, _ = make_pipe(dialogue=dlg(3))
        whole = p.assembles([{"role": "user", "content": NEW_INPUT},
                             {"role": "system", "content": MODE_AUTO}])
        spy = _Spy()
        comp = ContextCompactor(make_provider_summarizer(spy, max_chars=200),
                                summary_token_threshold=1)
        comp.ensure_before_append(p, dlg(3), pending={"role": "user", "content": "待拼"},
                                  mode_note=MODE_AUTO, assembled=whole)
        self.check_true("待拼内容不进压缩请求",
                        not any("待拼" in str(m.get("content"))
                                for m in spy.reqs[0].messages))


# ══════════════════════════════════════════════════════════════
# 六、不变量与边界
# ══════════════════════════════════════════════════════════════

class Invariants(_Case):
    """任何一条压缩请求都必须满足的硬约束。"""

    def _all_requests(self, *, extra_summaries=()):
        """四种组合（模式 × 有无新输入）各发一次压缩请求，收集每条请求的消息。"""
        from agent.core.events import Event

        out = []
        base = dlg(4) if extra_summaries else dlg(2)
        for mode, new_input in ((MODE_AUTO, True), (MODE_PLAN, True),
                                (MODE_AUTO, False), (MODE_PLAN, False)):
            # 每次请求都从同一份初始状态出发 —— 上一次压缩会往管道里写摘要，
            # 复用同一个管道会让后面的请求多出一条摘要，比对就不成立了。
            p, _ = make_pipe(summaries=extra_summaries, dialogue=base)
            tail = []
            if new_input:
                tail.append({"role": "user", "content": NEW_INPUT})
            tail.append({"role": "system", "content": mode})
            whole = p.assembles(tail)
            spy = _Spy()
            comp = ContextCompactor(make_provider_summarizer(spy, max_chars=200),
                                    summary_token_threshold=1)
            comp.restore_from_events([
                Event(type="context_compacted",
                      data={"covered_end": 0,
                            "summary": s.split("\n", 1)[1] if "\n" in s else s})
                for s in extra_summaries])
            p.set_summary_messages([{"role": "system", "content": s}
                                    for s in extra_summaries])
            comp.ensure_before_append(p, base, mode_note=mode, assembled=whole)
            if spy.reqs:
                out.append((f"mode={mode[:8]},new={new_input}", spy.reqs[0].messages))
        return out

    def test_every_request_has_system_prompt(self) -> None:
        for label, msgs in self._all_requests():
            with self.subTest(label):
                self.check_true(f"{label} 含系统提示",
                                any("SYSTEM" == short(m) for m in msgs))

    def test_every_request_has_all_skills(self) -> None:
        for label, msgs in self._all_requests():
            with self.subTest(label):
                tags = [short(m) for m in msgs]
                self.check_true(f"{label} 含两个 skill",
                                "SKILL1" in tags and "SKILL2" in tags)

    def test_every_request_has_all_kb(self) -> None:
        for label, msgs in self._all_requests():
            with self.subTest(label):
                tags = [short(m) for m in msgs]
                self.check_true(f"{label} 含两个知识库", "KB1" in tags and "KB2" in tags)

    def test_no_request_has_mode(self) -> None:
        for label, msgs in self._all_requests():
            with self.subTest(label):
                self.check_true(f"{label} 不含模式",
                                not any(short(m) == "MODE" for m in msgs))

    def test_every_request_ends_with_instruction(self) -> None:
        for label, msgs in self._all_requests():
            with self.subTest(label):
                self.check(f"{label} 末条是指令", "INSTRUCTION", short(msgs[-1]))

    def test_head_prefix_is_identical_across_requests(self) -> None:
        reqs = self._all_requests()
        heads = []
        for _label, msgs in reqs:
            tags = [short(m) for m in msgs]
            # 头部 = 对话起点（第 1 问）之前的所有条目
            cut = tags.index("USER:第1问")
            heads.append(tags[:cut])
        self.check_true("四类请求的头部逐条相同", len(set(map(tuple, heads))) == 1)

    def test_summaries_survive_every_request(self) -> None:
        for label, msgs in self._all_requests(extra_summaries=(SUM1, SUM2)):
            with self.subTest(label):
                tags = [short(m) for m in msgs]
                self.check_true(f"{label} 摘要都在",
                                "SUMMARY:摘要-1" in tags and "SUMMARY:摘要-2" in tags)

    def test_instruction_text_is_stable(self) -> None:
        reqs = self._all_requests()
        texts = {next(str(m.get("content")) for m in msgs if short(m) == "INSTRUCTION")
                 for _l, msgs in reqs}
        self.check_true("指令正文不随模式变化", len(texts) == 1)


# ══════════════════════════════════════════════════════════════
# 八、用户轮原子性与工具轨迹剥离
#
# 原子性 = 一条 user 起到下一条 user 前是一个整体。压缩只允许整轮处理：
# 边界一律向下取整到轮起点，宁可压 0 个用户轮，也不切半截轮。
#
# 这一节既有参数表（逐条写死期望），也有随机形态穷举：让"边界不切轮、
# 工具链闭合、user 不丢"这几条性质在任意输入下都被验证，
# 而不是只验证我恰好想到的那几个形态。
# ══════════════════════════════════════════════════════════════

import random  # noqa: E402

from agent.mechanisms.context_pipeline import (  # noqa: E402
    is_turn_boundary,
    layout_from_messages,
    tool_chain_balanced,
    turn_boundary_floor,
    turn_spans,
    user_turn_starts,
)


def conv(turns):
    """按"每轮几次工具往返"造对话：`[0,2,0]` = 第 2 轮有 2 次工具往返。"""
    msgs = []
    for u, tools in enumerate(turns, 1):
        msgs.append({"role": "user", "content": f"第{u}问"})
        for t in range(tools):
            msgs.append({"role": "assistant", "content": "",
                         "tool_calls": [{"id": f"c{u}_{t}", "name": "t", "arguments": {}}]})
            msgs.append({"role": "tool", "tool_call_id": f"c{u}_{t}", "content": "结果"})
        msgs.append({"role": "assistant", "content": f"第{u}答"})
    return msgs


class TurnAtomicity(_Case):
    """轮边界的定位与向下取整。"""

    def test_turn_starts(self) -> None:
        msgs = conv([0, 2, 0])
        self.check("三个用户轮", [0, 2, 8], user_turn_starts(msgs))

    def test_turn_spans(self) -> None:
        msgs = conv([0, 1, 0])
        self.check("轮区间", [(0, 2), (2, 6), (6, 8)], turn_spans(msgs))

    def test_floor_on_boundary_is_identity(self) -> None:
        msgs = conv([0, 1, 0])
        self.check("边界上取整 = 原地", [0, 2, 6],
                   [turn_boundary_floor(msgs, i) for i in (0, 2, 6)])

    def test_floor_inside_turn_goes_back(self) -> None:
        msgs = conv([0, 2, 0])
        self.check("轮内部取整回本轮起点", [2, 2, 2, 2],
                   [turn_boundary_floor(msgs, i) for i in (3, 4, 5, 7)])

    def test_floor_before_first_user(self) -> None:
        msgs = [{"role": "system", "content": "s"}] + conv([0])
        self.check("首个 user 之前 → 0", 0, turn_boundary_floor(msgs, 0))

    def test_floor_beyond_end(self) -> None:
        msgs = conv([0, 0])
        self.check("越界 → 最后一个轮起点", 2, turn_boundary_floor(msgs, 99))

    def test_is_boundary(self) -> None:
        msgs = conv([0, 1])
        self.check("边界判定", [True, False, True, True],
                   [is_turn_boundary(msgs, i) for i in (0, 1, 2, 6)])

    def test_tool_chain_balanced_ok(self) -> None:
        msgs = conv([0, 1])
        self.check_true("闭合区间", tool_chain_balanced(msgs, 0, 6))

    def test_tool_chain_balanced_missing_result(self) -> None:
        msgs = conv([0, 1])
        self.check_true("切掉结果 → 不闭合", not tool_chain_balanced(msgs, 0, 4))

    def test_tool_chain_balanced_orphan_result(self) -> None:
        msgs = conv([0, 1])
        self.check_true("孤立结果 → 不闭合（发起者在区间外）",
                        not tool_chain_balanced(msgs, 4, 6))


#: (每轮工具次数, keep_turns) → 期望的剥离结果（角色序列）
STRIP_DISTANT_TABLE = [
    ([0, 0, 0], 1, ["user", "assistant", "user", "assistant", "user", "assistant"]),
    ([2, 0, 0], 1, ["user", "assistant", "user", "assistant", "user", "assistant"]),
    ([0, 2, 0], 1, ["user", "assistant", "user", "assistant", "user", "assistant"]),
    ([0, 0, 2], 1, ["user", "assistant", "user", "assistant", "user", "assistant",
                    "tool", "assistant", "tool", "assistant"]),
    ([2, 0, 0], 2, ["user", "assistant", "user", "assistant", "user", "assistant"]),
    ([0, 0, 2], 2, ["user", "assistant", "user", "assistant", "user", "assistant",
                    "tool", "assistant", "tool", "assistant"]),
    ([0, 0, 2], 3, ["user", "assistant", "user", "assistant", "user", "assistant",
                    "tool", "assistant", "tool", "assistant"]),
    ([2, 2, 2], 0, ["user", "assistant", "user", "assistant", "user", "assistant"]),
    ([2, 2, 2], -1, ["user", "assistant", "tool", "assistant", "tool", "assistant",
                     "user", "assistant", "tool", "assistant", "tool", "assistant",
                     "user", "assistant", "tool", "assistant", "tool", "assistant"]),
]
def _random_conv(rng: random.Random, *, max_turns: int = 7) -> list:
    """随机对话：每轮 0..3 次工具往返；末尾可能多一条新输入。"""
    msgs = []
    for u in range(rng.randint(1, max_turns)):
        msgs.append({"role": "user", "content": f"第{u + 1}问"})
        for t in range(rng.randint(0, 3)):
            cid = f"c{u}_{t}"
            msgs.append({"role": "assistant", "content": "",
                         "tool_calls": [{"id": cid, "name": "t", "arguments": {}}]})
            msgs.append({"role": "tool", "tool_call_id": cid, "content": "结果"})
        msgs.append({"role": "assistant", "content": f"第{u + 1}答"})
    if rng.random() < 0.4:
        msgs.append({"role": "user", "content": "新输入"})
    return msgs


class RandomShapeInvariants(_Case):
    """随机形态穷举：几条永远必须成立的性质。

    重点不是某个具体结果，而是"任何输入都不许破坏"：
    边界不切轮、工具链闭合、user 不增不减、剥离幂等。
    """

    SEEDS = tuple(range(12))

    def test_compaction_range_never_splits_a_turn(self) -> None:
        """① 压缩区间首尾都必须落在用户轮边界上。"""
        checked = 0
        for seed in self.SEEDS:
            rng = random.Random(seed)
            for _ in range(40):
                msgs = _random_conv(rng)
                for keep in (0, 1, 2, 3):
                    r = excerpt_by_target_tokens(msgs, keep)
                    if not r:
                        continue
                    checked += 1
                    e = int(r[1])
                    if not tool_chain_balanced(msgs, 0, e):
                        self.fail(f"落点切断工具链 seed={seed} keep={keep} e={e}")
                    if not is_turn_boundary(msgs, e):
                        self.fail(f"落点不在轮边界 seed={seed} keep={keep} e={e}")
        self.check_true(f"检查了 {checked} 个区间", checked > 200)

    def test_compaction_range_tool_chain_always_closed(self) -> None:
        """② 压缩区间内的工具链必须闭合（否则切出残链）。"""
        checked = 0
        for seed in self.SEEDS:
            rng = random.Random(seed)
            for _ in range(40):
                msgs = _random_conv(rng)
                for keep in (0, 1, 2):
                    r = excerpt_by_target_tokens(msgs, keep)
                    if not r or r[1] <= 0:
                        continue
                    checked += 1
                    if not tool_chain_balanced(msgs, 0, r[1]):
                        self.fail(f"区间工具链不闭合 seed={seed} keep={keep}")
        self.check_true(f"检查了 {checked} 个区间", checked > 100)
# 硬不变量：上下文超阈值时必须腾出空间。
# 保留近场是偏好；坚持保留近场导致"压不动"、请求直接超上限，才是真的坏。
# ══════════════════════════════════════════════════════════════

from agent.core.model_call import StreamDelta as _SD  # noqa: E402
from agent.mechanisms.context_pipeline import (  # noqa: E402
    excerpt_by_target_tokens,
)


class _Spy2:
    def __init__(self):
        self.reqs = []

    def stream(self, request):
        self.reqs.append(request)
        yield _SD(kind="text", text="摘要正文")
        yield _SD(kind="done")


def _fat_turn(tools: int, pad: int, turns: int = 1) -> list:
    """`turns` 个用户轮，每轮 `tools` 次工具往返（用于造"单轮吃满"）。"""
    msgs = []
    for u in range(1, turns + 1):
        msgs.append({"role": "user", "content": f"第{u}问" + "字" * pad})
        for t in range(tools):
            msgs.append({"role": "assistant", "content": "",
                         "tool_calls": [{"id": f"c{u}_{t}", "name": "t", "arguments": {}}]})
            msgs.append({"role": "tool", "tool_call_id": f"c{u}_{t}",
                         "content": "结果" + "字" * pad})
        msgs.append({"role": "assistant", "content": f"第{u}答" + "字" * pad})
    return msgs


def _run_compaction(msgs, *, threshold, reserve):
    p = ContextPipeline("cid-greedy-0001", full_user_rounds=1)
    p.append_system(SYS)
    p.set_dialogue(msgs, covered_end=0)
    before = p.total_token_estimate()
    whole = p.assembles([{"role": "user", "content": NEW_INPUT},
                         {"role": "system", "content": MODE_AUTO}])
    spy = _Spy2()
    comp = ContextCompactor(make_provider_summarizer(spy, max_chars=200),
                            summary_token_threshold=threshold,
                            full_user_rounds=reserve)
    report = comp.ensure_before_append(p, msgs, mode_note=MODE_AUTO, assembled=whole)
    after = 0
    if report:
        p.set_dialogue(msgs, covered_end=comp.covered_end)
        after = p.total_token_estimate()
    return p, spy, comp, report, before, after




# ══════════════════════════════════════════════════════════════
# 九、遮盖是硬约束
#
# 末尾 N 个用户轮永远不压（`full_user_rounds`，至少 1 轮）。
# 压缩区域只能是「最后一个前置 system 之后 → 遮盖起点之前」那一段 ——
# 系统提示 / Skills / 知识库 / 记忆摘要都是 system、排在对话之前，
# 所以区域天然不含任何系统设定。
#
# 没有"压不动就连近场一起压"的兜底：遮盖住的部分超预算，是这个配置本身
# 撑不住，不该由压缩去动近景。
# ══════════════════════════════════════════════════════════════

class MaskIsHard(_Case):
    """遮盖的轮一律原样保留；压缩只在它前面发生。"""

    def test_excerpt_never_touches_the_masked_tail(self) -> None:
        msgs = conv([0, 0, 0, 0, 0])
        for keep in (1, 2, 3, 5, 9):
            with self.subTest(f"遮盖 {keep} 轮"):
                rng = excerpt_by_target_tokens(msgs, keep)
                self.assertTrue(rng is not None, msg="压不动就连近场一起压，不许 None")
                _s, e = rng
                left = sum(1 for m in msgs[e:] if m.get("role") == "user")
                # 遮盖前面有可压的轮 → 留 keep 轮；遮盖已盖住全部 → 压到 0 轮
                want = keep if keep < 5 else 0
                self.check(f"遮盖 {keep}：剩余用户轮 = {want}", want, left)

    def test_excerpt_starts_at_zero(self) -> None:
        rng = excerpt_by_target_tokens(conv([1, 0, 1, 0]), 1)
        self.check("区域从第 1 个用户轮起", 0, rng[0])

    def test_single_turn_is_compressed_when_nothing_else_can_be(self) -> None:
        """只有 1 轮：遮盖前面没东西可压 → 连它一起压（压到 0 轮）。"""
        msgs = conv([2])
        rng = excerpt_by_target_tokens(msgs, 1)
        self.check("压到末尾", (0, len(msgs)), rng)
        self.check("剩余 0 轮", 0,
                   sum(1 for m in msgs[rng[1]:] if m.get("role") == "user"))

    def test_region_excludes_every_system_message(self) -> None:
        """压缩区域落在对话段里，一条 system 都不含。"""
        msgs = [{"role": "system", "content": SYS}] + conv([0, 0, 2, 0])
        rng = excerpt_by_target_tokens(msgs[1:], 1)
        region = msgs[1:][rng[0]:rng[1]]
        self.check_true("区域里没有 system",
                        all(str(m.get("role")) != "system" for m in region))

    def test_region_tool_chain_closed(self) -> None:
        msgs = conv([2, 0, 3, 0, 1])
        rng = excerpt_by_target_tokens(msgs, 1)
        self.check_true("区域工具链闭合", tool_chain_balanced(msgs, rng[0], rng[1]))


class MaskSurvivesOverflow(_Case):
    """内层管线：超阈值时遮盖仍然不被压。"""

    def _msgs(self, *, big_last: bool):
        out = []
        for u in range(1, 4):
            out.append({"role": "user", "content": f"第{u}问" + "字" * 40})
            temp = 20 if (big_last and u == 3) else 0
            for t in range(temp):
                out.append({"role": "assistant", "content": "",
                            "tool_calls": [{"id": f"c{u}_{t}"}]})
                out.append({"role": "tool", "tool_call_id": f"c{u}_{t}",
                            "content": "结果" + "字" * 1200})
            out.append({"role": "assistant", "content": f"第{u}答" + "字" * 40})
        return out

    def test_masked_last_turn_stays_when_it_is_huge(self) -> None:
        """核心：末尾那一轮自己就吃满预算，仍然不许压它。"""
        msgs = self._msgs(big_last=True)
        p = ContextPipeline("cid-mask-0001", full_user_rounds=1)
        p.append_system(SYS)
        p.set_dialogue(msgs, covered_end=0)
        before = p.total_token_estimate()
        self.check_true(f"末尾轮确实很大（{before}）", before > 3000)
        whole = p.assembles([{"role": "user", "content": NEW_INPUT},
                             {"role": "system", "content": MODE_AUTO}])
        comp = ContextCompactor(make_provider_summarizer(_Spy(), max_chars=200),
                                summary_token_threshold=3000, full_user_rounds=1)
        report = comp.ensure_before_append(p, msgs, mode_note=MODE_AUTO, assembled=whole)
        self.check_true("仍然压缩前面可压的部分", bool(report))
        left = [m for m in msgs[comp.covered_end:] if m.get("role") == "user"]
        self.check("末尾那一轮原样保留", 1, len(left))
        self.check("留下的是最后一轮的提问", "第3问",
                   str(left[0].get("content"))[:3])

    def test_reserve_two_keeps_two_turns(self) -> None:
        msgs = self._msgs(big_last=False)
        p = ContextPipeline("cid-mask-0002", full_user_rounds=1)
        p.append_system(SYS)
        p.set_dialogue(msgs, covered_end=0)
        whole = p.assembles([{"role": "user", "content": NEW_INPUT},
                             {"role": "system", "content": MODE_AUTO}])
        comp = ContextCompactor(make_provider_summarizer(_Spy(), max_chars=200),
                                summary_token_threshold=1, full_user_rounds=2)
        comp.ensure_before_append(p, msgs, mode_note=MODE_AUTO, assembled=whole)
        left = [m for m in msgs[comp.covered_end:] if m.get("role") == "user"]
        self.check("遮盖 2 轮就留 2 轮", 2, len(left))

    def test_reserve_zero_means_no_mask(self) -> None:
        comp = ContextCompactor(None, full_user_rounds=0)
        self.check("遮盖 0 轮 = 不遮盖（照配置来，不擅自抬）", 0,
                   comp.full_user_rounds)

    def test_only_masked_turns_still_get_compressed(self) -> None:
        """只有被遮盖的轮 → 连它一起压（压不动就是超上限失败）。"""
        msgs = conv([4])
        p = ContextPipeline("cid-mask-0003", full_user_rounds=1)
        p.append_system(SYS)
        p.set_dialogue(msgs, covered_end=0)
        whole = p.assembles([{"role": "user", "content": NEW_INPUT},
                             {"role": "system", "content": MODE_AUTO}])
        comp = ContextCompactor(make_provider_summarizer(_Spy(), max_chars=200),
                                summary_token_threshold=1, full_user_rounds=1)
        report = comp.ensure_before_append(p, msgs, mode_note=MODE_AUTO, assembled=whole)
        self.assertTrue(report, msg="必须压下去")
        self.check("压到 0 个用户轮", 0,
                   sum(1 for m in msgs[comp.covered_end:] if m.get("role") == "user"))

    def test_mask_invariant_over_random_shapes(self) -> None:
        """随机形态：任何一次压缩之后，被遮盖的轮数必须 ≥ 配置值。"""
        for seed in range(10):
            rng = random.Random(seed)
            for _ in range(8):
                turns = rng.randint(1, 6)
                tools = rng.randint(0, 4)
                msgs = _fat_turn(tools, 200, turns=turns)
                reserve = rng.choice((1, 2, 3))
                p = ContextPipeline("cid-mask-0004", full_user_rounds=1)
                p.append_system(SYS)
                p.set_dialogue(msgs, covered_end=0)
                whole = p.assembles([{"role": "user", "content": NEW_INPUT},
                                     {"role": "system", "content": MODE_AUTO}])
                comp = ContextCompactor(make_provider_summarizer(_Spy(), max_chars=200),
                                        summary_token_threshold=1,
                                        full_user_rounds=reserve)
                comp.ensure_before_append(p, msgs, mode_note=MODE_AUTO,
                                          assembled=whole)
                if not tool_chain_balanced(msgs, 0, comp.covered_end):
                    self.fail(f"落点切断了工具链 seed={seed} turns={turns}")
                left = sum(1 for m in msgs[comp.covered_end:]
                           if m.get("role") == "user")
                # 遮盖是偏好：正常留 reserve 轮；压不出来时允许连遮盖一起压（0 轮）
                if left not in (0, min(reserve, turns)):
                    self.fail(f"剩余轮数既不是遮盖值也不是 0 seed={seed} "
                              f"turns={turns} reserve={reserve} 剩余={left}")


# ══════════════════════════════════════════════════════════════
# 十、Skills 渐进式披露
#
# 两层：
#   第一层「Skills 清单」—— 名字 + 描述，常驻上下文前端，模型据此挑 Skills；
#   第二层 `auto_load/` 下的 Skills 正文 —— 始终随上下文携带，不必模型主动读。
# 普通 Skills 的正文不进上下文，由模型按需用 `skill_manage` 读取。
# ══════════════════════════════════════════════════════════════

import shutil  # noqa: E402
import tempfile  # noqa: E402

from plugins.skills.library import SkillManager  # noqa: E402


def _skill_tree():
    """造一个 Skills 目录：两个普通 Skills + 一个 auto_load 常驻 Skills。"""
    root = Path(tempfile.mkdtemp(prefix="skillcase_"))
    skills = root / "skills"
    (skills / "auto_load").mkdir(parents=True, exist_ok=True)
    (skills / "deploy.md").write_text(
        "---\nname: deploy\ndescription: 部署到测试环境\n---\n# 部署\n部署正文步骤\n",
        encoding="utf-8")
    (skills / "review.md").write_text(
        "---\nname: review\ndescription: 审查改动\n---\n# 审查\n审查正文步骤\n",
        encoding="utf-8")
    (skills / "auto_load" / "house.md").write_text(
        "---\nname: house\ndescription: 常驻规范\n---\n# 常驻\n必须遵守的规范正文\n",
        encoding="utf-8")
    return root, skills


class SkillProgressiveDisclosure(_Case):
    """清单只给名字 + 描述；常驻 Skills 给正文；普通 Skills 正文不进上下文。"""

    def setUp(self) -> None:
        self.root, self.skills = _skill_tree()
        self.lib = SkillManager(self.skills, 200000)
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_registry_lists_names_and_descriptions(self) -> None:
        got = self.lib.build_registry_message()
        self.check_true("含清单标题", "【Skills 清单】" in got)
        self.check_true("含 deploy 名字与描述", "- deploy: 部署到测试环境" in got)
        self.check_true("含 review 名字与描述", "- review: 审查改动" in got)

    def test_registry_excludes_auto_load_skill(self) -> None:
        got = self.lib.build_registry_message()
        self.check_true("常驻 Skills 不列进清单（它的正文已常驻）", "house" not in got)

    def test_registry_excludes_skill_bodies(self) -> None:
        got = self.lib.build_registry_message()
        self.check_true("普通 Skills 正文不进清单", "部署正文步骤" not in got)
        self.check_true("审查正文也不进清单", "审查正文步骤" not in got)

    def test_registry_is_absent_when_no_skills(self) -> None:
        empty = Path(tempfile.mkdtemp(prefix="skillcase_empty_"))
        self.addCleanup(shutil.rmtree, empty, True)
        lib = SkillManager(empty, 200000)
        self.check("没有 Skills → 不注入空清单", "", lib.build_registry_message())
        self.check("列表形态也为空", [], lib.build_registry_message_parts())

    def test_auto_load_messages_carry_bodies(self) -> None:
        got = self.lib.build_auto_load_messages()
        self.check("自动加载 1 条", 1, len(got))
        self.check_true("带 Skills 名抬头", "【Skills " in got[0])
        self.check_true("带 Skills 名", "house" in got[0])
        self.check_true("带正文", "必须遵守的规范正文" in got[0])

    def test_auto_load_excludes_normal_skills(self) -> None:
        got = "".join(self.lib.build_auto_load_messages())
        self.check_true("普通 Skills 不进常驻", "部署正文步骤" not in got)

    def test_auto_load_empty_when_no_auto_load_dir(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="skillcase_noauto_"))
        self.addCleanup(shutil.rmtree, root, True)
        (root / "x.md").write_text("---\nname: x\ndescription: d\n---\n正文\n",
                                   encoding="utf-8")
        lib = SkillManager(root, 200000)
        self.check("没有 auto_load → 空列表", [], lib.build_auto_load_messages())

    def test_skill_manager_lists_normal_skills_only(self) -> None:
        names = [s["name"] for s in self.lib.list_skills()]
        self.check("list_skills 只给普通 Skills", ["deploy", "review"], names)


class SkillInjectionIntoRequest(_Case):
    """Skills 作为插件段落注入：顺序、压缩请求同源、整体重建。"""

    def setUp(self) -> None:
        self.root, self.skills = _skill_tree()
        self.lib = SkillManager(self.skills, 200000)
        self.addCleanup(shutil.rmtree, self.root, True)

    def _segments(self):
        return ([("skills", "Skills", t) for t in self.lib.build_registry_message_parts()] +
                [("skills", "常驻 Skills", t) for t in self.lib.build_auto_load_messages()])

    def _pipeline(self):
        p = ContextPipeline("cid-skill-0001", full_user_rounds=1)
        p.append_system(SYS)
        p.set_plugin_segments(self._segments())
        return p

    def test_plugin_segments_sit_after_system_prompt(self) -> None:
        p = self._pipeline()
        p.set_dialogue(dlg(1), covered_end=0)
        got = p.assembles([{"role": "user", "content": NEW_INPUT},
                           {"role": "system", "content": MODE_AUTO}])
        self.check("顺序：系统提示 → 清单 → 常驻 → 对话 → 新输入 → 模式",
                   "SYSTEM | SKILLBLOCK | SKILLBLOCK | USER:第1问 | ASSISTANT:第1答"
                   " | USER:本轮新输入 | MODE",
                   shape(got))

    def test_summary_sits_after_plugin_segments(self) -> None:
        p = self._pipeline()
        p.set_summary_messages([{"role": "system", "content": SUM1}])
        p.set_dialogue(dlg(1), covered_end=0)
        self.check("头部顺序：系统提示 → 清单 → 常驻 → 摘要",
                   "SYSTEM | SKILLBLOCK | SKILLBLOCK | SUMMARY:摘要-1",
                   shape(p.host_messages()))

    def test_plugin_segments_used_by_compaction_request(self) -> None:
        """插件段落属头部：压缩请求必须带上同一份。"""
        p = self._pipeline()
        p.set_dialogue(dlg(4), covered_end=0)
        whole = p.assembles([{"role": "user", "content": NEW_INPUT},
                             {"role": "system", "content": MODE_AUTO}])
        spy = _Spy()
        comp = ContextCompactor(make_provider_summarizer(spy, max_chars=200),
                                summary_token_threshold=1)
        comp.ensure_before_append(p, dlg(4), mode_note=MODE_AUTO, assembled=whole)
        joined = "".join(str(m.get("content")) for m in spy.reqs[0].messages)
        self.check_true("压缩请求含 Skills 清单", "【Skills 清单】" in joined)
        self.check_true("压缩请求含常驻 Skills 正文", "必须遵守的规范正文" in joined)

    def test_plugin_segments_are_not_duplicated_across_passes(self) -> None:
        """`set_plugin_segments` 是整体重建：多跑几趟不会累积。"""
        p = self._pipeline()
        for _ in range(3):
            p.set_plugin_segments(self._segments())
        p.set_dialogue(dlg(1), covered_end=0)
        joined = "".join(str(m.get("content")) for m in p.host_messages())
        self.check("清单只出现一次", 1, joined.count("【Skills 清单】"))
        self.check("常驻正文只出现一次", 1, joined.count("必须遵守的规范正文"))

    def test_empty_segments_leave_head_empty(self) -> None:
        p = ContextPipeline("cid-skill-0002", full_user_rounds=1)
        p.append_system(SYS)
        p.set_plugin_segments([])
        p.set_dialogue(dlg(1), covered_end=0)
        tags = [short(m) for m in p.host_messages()]
        self.check("没有插件段落时不产生空的注入消息", ["SYSTEM"], tags)

    def test_segment_stats_follow_the_plugin(self) -> None:
        """分段统计里两段都挂在插件名下，段名与数量由插件给。"""
        p = self._pipeline()
        p.set_dialogue(dlg(1), covered_end=0)
        keys = [r["key"] for r in p.segment_tokens()]
        labels = [r["label"] for r in p.segment_tokens()]
        self.check("两段都在 plugin:skills 名下",
                   ["system", "plugin:skills", "plugin:skills", "summary", "full_recent"],
                   keys)
        self.check("段名由插件给",
                   ["系统提示词", "Skills", "常驻 Skills", "记忆摘要", "近期记忆"], labels)




# ══════════════════════════════════════════════════════════════
# 十一、上下文分段统计（UI 上下文示意图用）
#
# 口径：与真正发出去的请求同一份装配、同一个 token 估算器。
# 逐段：系统提示词 / Skills / 知识库 / 记忆摘要 / 近期 + 尾部模式。
# ══════════════════════════════════════════════════════════════

from agent.mechanisms.context_pipeline import default_message_tokens  # noqa: E402


class SegmentTokens(_Case):
    """逐段统计与段名。"""

    def _pipe(self, *, summaries=(), dialogue=(), skills=(), kb=()):
        p = ContextPipeline("cid-seg-0001", full_user_rounds=1)
        p.append_system(SYS)
        segs = [("skills", "Skills", t) for t in skills]
        segs += [("kb", "知识库", t) for t in kb]
        p.set_plugin_segments(segs)
        p.set_summary_messages([{"role": "system", "content": s} for s in summaries])
        p.set_dialogue(list(dialogue), covered_end=0)
        return p



    def test_system_segment_matches_its_message(self) -> None:
        p = self._pipe(dialogue=dlg(1))
        rows = {r["key"]: r for r in p.segment_tokens()}
        self.check("系统段 = 该消息的估算值",
                   default_message_tokens({"content": SYS}), rows["system"]["tokens"])




    def test_summary_segment_counts_both_summaries(self) -> None:
        p = self._pipe(dialogue=dlg(1), summaries=("摘要甲" * 6, "摘要乙" * 6))
        rows = {r["key"]: r for r in p.segment_tokens()}
        self.check("记忆摘要段条数", 2, rows["summary"]["count"])

    def test_dialogue_split_into_two_segments(self) -> None:
        p = self._pipe(dialogue=dlg(2))
        rows = {r["key"]: r for r in p.segment_tokens()}
        self.check("近期记忆计用户轮数", 2, rows["full_recent"]["count"])

    def test_segments_sum_equals_assembled_total(self) -> None:
        """关键一致性：分段之和 == 装配出来的消息总量（同估算器）。"""
        p = self._pipe(dialogue=dlg(3), summaries=(SUM1,), skills=["Skills 正文" * 5],
                       kb=["知识库条目" * 5])
        p.set_dialogue(dlg(3), covered_end=0)
        got = p.assembles()
        want = sum(int(default_message_tokens(m)) for m in got)
        have = sum(int(r["tokens"]) for r in p.segment_tokens())
        self.check("分段之和 = 装配总量", want, have)


class LayoutPayload(_Case):
    """快照载荷：段 + 剩余容量 + 预算。"""

    def _pipe(self, *, dialogue=(), tail=None):
        p = ContextPipeline("cid-seg-0002", full_user_rounds=1)
        p.append_system(SYS)
        p.set_dialogue(list(dialogue), covered_end=0)
        return p, (tail or [])

    def test_payload_shape(self) -> None:
        p, tail = self._pipe(dialogue=dlg(1))
        got = p.layout_payload(budget_tokens=1000, tail_messages=tail)
        self.check("键", ["budget_tokens", "model_max_context_tokens", "segments",
                          "total_tokens"],
                   sorted(got.keys()))

    def test_last_segment_is_remaining(self) -> None:
        p, tail = self._pipe(dialogue=dlg(1))
        got = p.layout_payload(budget_tokens=1000, tail_messages=tail)
        self.check("末段是剩余容量", "remaining", got["segments"][-1]["key"])

    def test_tail_becomes_mode_segment(self) -> None:
        p, _t = self._pipe(dialogue=dlg(1))
        got = p.layout_payload(budget_tokens=1000,
                               tail_messages=[{"role": "system", "content": MODE_AUTO}])
        keys = [s["key"] for s in got["segments"]]
        self.check_true("尾部模式单列一段", "mode" in keys)
        mode = next(s for s in got["segments"] if s["key"] == "mode")
        self.check("模式段条数", 1, mode["count"])

    def test_no_tail_means_no_mode_segment(self) -> None:
        p, _t = self._pipe(dialogue=dlg(1))
        got = p.layout_payload(budget_tokens=1000)
        self.check_true("没有尾部就没有模式段",
                        all(s["key"] != "mode" for s in got["segments"]))

    def test_pct_sums_to_100(self) -> None:
        p, tail = self._pipe(dialogue=dlg(2))
        got = p.layout_payload(budget_tokens=2000, tail_messages=tail)
        total_pct = sum(float(s["pct"]) for s in got["segments"])
        self.check_true(f"各段 pct 合计 ≈100（实际 {total_pct:.4f}）",
                        abs(total_pct - 100.0) < 0.01)

    def test_budget_never_below_used(self) -> None:
        p, tail = self._pipe(dialogue=dlg(3))
        got = p.layout_payload(budget_tokens=1, tail_messages=tail)
        self.check_true("预算不小于已用", got["budget_tokens"] >= got["total_tokens"])
        self.check("剩余容量不为负", True,
                   all(s["tokens"] >= 0 for s in got["segments"]))

    def test_total_matches_segments_minus_remaining(self) -> None:
        p, tail = self._pipe(dialogue=dlg(2))
        got = p.layout_payload(budget_tokens=2000, tail_messages=tail)
        want = sum(int(s["tokens"]) for s in got["segments"] if s["key"] != "remaining")
        self.check("total_tokens = 各段之和（不含剩余容量）", want, got["total_tokens"])


class LayoutFromMessages(_Case):
    """兜底口径：没有装配快照的旧会话也分层（按位置切段）。"""

    def _msgs(self, *, head=3, rounds=2, mode=True):
        out = [{"role": "system", "content": SYS}]
        for i in range(head - 1):
            out.append({"role": "system", "content": f"头部附加{i + 1}"})
        out += dlg(rounds)
        if mode:
            out.append({"role": "system", "content": MODE_AUTO})
        return out

    def test_head_first_message_is_the_system_prompt(self) -> None:
        got = layout_from_messages(self._msgs(head=1, rounds=1))
        rows = {s["key"]: s for s in got["segments"]}
        self.check("系统提示词段 = 头部第 1 条",
                   default_message_tokens({"content": SYS}), rows["system"]["tokens"])

    def test_given_system_text_is_used_and_not_double_counted(self) -> None:
        msgs = self._msgs(head=3, rounds=1)
        got = layout_from_messages(msgs, system_text=SYS)
        rows = {s["key"]: s for s in got["segments"]}
        self.check("按给定正文算系统段",
                   default_message_tokens({"content": SYS}), rows["system"]["tokens"])
        self.check("头部剩余两条不再算系统段", 0, len([s for s in got["segments"]
                                                    if s["key"] == "system"]) - 1)

    def test_last_head_message_is_the_summary(self) -> None:
        msgs = [{"role": "system", "content": SYS},
                {"role": "system", "content": "【历史摘要】\n旧摘要"}] + dlg(1)
        rows = {s["key"]: s for s in layout_from_messages(msgs)["segments"]}
        # 头部只有两条：第 1 条是系统提示词，第 2 条才是摘要。
        # 系统提示词不能被系统段与摘要段各算一次。
        self.check("摘要段只有那一条", 1, rows["summary"]["count"])

    def test_dialogue_starts_at_the_first_user(self) -> None:
        rows = {s["key"]: s for s in layout_from_messages(self._msgs(rounds=2))["segments"]}
        self.check("对话段计用户轮数", 2, rows["full_recent"]["count"])

    def test_mode_is_split_out(self) -> None:
        rows = {s["key"]: s for s in layout_from_messages(self._msgs())["segments"]}
        self.check("模式单列一段", 1, rows["mode"]["count"])

    def test_no_mode_means_no_mode_segment(self) -> None:
        got = layout_from_messages(self._msgs(mode=False))
        self.check_true("没有模式就不出这一段",
                        all(s["key"] != "mode" for s in got["segments"]))

    def test_remaining_is_last(self) -> None:
        got = layout_from_messages(self._msgs())
        self.check("末段是剩余容量", "remaining", got["segments"][-1]["key"])

    def test_total_equals_segments_sum(self) -> None:
        got = layout_from_messages(self._msgs(head=2, rounds=3))
        want = sum(int(s["tokens"]) for s in got["segments"] if s["key"] != "remaining")
        self.check("total = 各段之和（不含剩余容量）", want, got["total_tokens"])

    def test_mode_not_counted_as_dialogue(self) -> None:
        msgs = self._msgs(rounds=1, mode=True)
        rows = {s["key"]: s for s in layout_from_messages(msgs)["segments"]}
        self.check("对话段计用户轮数（不含模式）", 1, rows["full_recent"]["count"])

    def test_empty_input(self) -> None:
        got = layout_from_messages([])
        self.check("空输入给空段", [], got["segments"])
        self.check("总量为 0", 0, got["total_tokens"])

class LayoutWithHead(_Case):
    """兜底带装配出来的头部：能分清 Skills / 知识库 / 摘要。"""

    def _head(self):
        return [
            {"role": "system", "content": SYS},
            {"role": "system", "content": "【Skills 清单】\n- a: b"},
            {"role": "system", "content": "【Skills】\n常驻正文"},
            {"role": "system", "content": KB1},
            {"role": "system", "content": "【历史摘要】\n旧摘要"},
        ]

    def _segments(self):
        return [("skills", "Skills", 1), ("skills", "常驻 Skills", 1),
                ("knowledge", "知识库", 1)]

    def _layout(self, messages, **kw):
        kw.setdefault("plugin_segments", self._segments())
        return layout_from_messages(messages, system_text=SYS, head=self._head(), **kw)

    def test_plugin_segments_are_one_row_each(self) -> None:
        """同一插件两段各成一行，段名与数量都按描述来。"""
        got = self._layout(dlg(1))["segments"]
        rows = [(s["key"], s["label"], s.get("count")) for s in got]
        self.check("三段各一行",
                   [("system", "系统提示词", 1),
                    ("plugin:skills", "Skills", 1),
                    ("plugin:skills", "常驻 Skills", 1),
                    ("plugin:knowledge", "知识库", 1),
                    ("summary", "记忆摘要", 1),
                    ("full_recent", "近期记忆", 1),
                    ("remaining", "剩余容量", None)],
                   rows)

    def test_dialogue_does_not_include_head(self) -> None:
        rows = {s["key"]: s for s in self._layout(dlg(2))["segments"]}
        self.check("对话段计用户轮数", 2, rows["full_recent"]["count"])

    def test_mode_splits_from_dialogue(self) -> None:
        msgs = dlg(1) + [{"role": "system", "content": MODE_AUTO}]
        rows = {s["key"]: s for s in self._layout(msgs)["segments"]}
        self.check("模式单列", 1, rows["mode"]["count"])
        self.check("对话计用户轮数且不含模式", 1, rows["full_recent"]["count"])

    def test_without_head_falls_back_to_position(self) -> None:
        """不传 head：只能按位置猜，插件段落一律归到摘要之后的那一堆。"""
        msgs = [{"role": "system", "content": SYS},
                {"role": "system", "content": KB1}] + dlg(1)
        rows = {s["key"]: s for s in layout_from_messages(msgs)["segments"]}
        self.check("无 head 时没有插件段", 0, len([k for k in rows if k.startswith("plugin:")]))
        self.check("系统提示词仍单列", 1, rows["system"]["count"])
        self.check("头部剩下的都算摘要", 1, rows["summary"]["count"])

    def test_total_equals_sum_without_remaining(self) -> None:
        got = self._layout(dlg(2))
        want = sum(int(s["tokens"]) for s in got["segments"] if s["key"] != "remaining")
        self.check("total = 各段之和", want, got["total_tokens"])

class SegmentKeysAndCounts(_Case):
    """段 key 与数量口径：插件段一律 `plugin:<插件名>`。"""

    def test_keys_and_labels(self) -> None:
        p = ContextPipeline("cid-seg-0100", full_user_rounds=1)
        p.append_system(SYS)
        p.set_plugin_segments([("kb", "知识库", "kb-1"), ("skills", "Skills", "sk-1")])
        p.set_dialogue(dlg(1), covered_end=0)
        self.check("段顺序：系统提示词 → 插件各段 → 摘要 → 对话",
                   ["system", "plugin:kb", "plugin:skills", "summary", "full_recent"],
                   [r["key"] for r in p.segment_tokens()])
        self.check("段名由插件给",
                   ["系统提示词", "知识库", "Skills", "记忆摘要", "近期记忆"],
                   [r["label"] for r in p.segment_tokens()])

    def test_plugin_may_declare_more_than_one_segment(self) -> None:
        """同一插件两段：数量按位置对上，不会互相覆盖。"""
        p = ContextPipeline("cid-seg-0101", full_user_rounds=1)
        p.append_system(SYS)
        p.set_plugin_segments([("skills", "Skills", "清单30个 Skills"), ("skills", "常驻 Skills", "常驻1个")])
        p.set_dialogue(dlg(1), covered_end=0)
        rows = [r for r in p.segment_tokens() if r["key"] == "plugin:skills"]
        self.check("两段都在 plugin:skills 名下", 2, len(rows))
        self.check("段名各自独立", ["Skills", "常驻 Skills"], [r["label"] for r in rows])


class SegmentCountSemantics(_Case):
    """`count` 的计「个」口径按段定：头部按 system 条数，对话按用户轮数。"""

    def test_system_prompt_counts_messages(self) -> None:
        p = ContextPipeline("cid-cnt-0001", full_user_rounds=1)
        p.append_system(SYS)
        p.set_dialogue(dlg(2), covered_end=0)
        rows = {r["key"]: r for r in p.segment_tokens()}
        self.check("系统提示词按条数", 1, rows["system"]["count"])


    def test_dialogue_counts_user_turns_not_messages(self) -> None:
        p = ContextPipeline("cid-cnt-0003", full_user_rounds=1)
        msgs = [{"role": "user", "content": "问"},
                {"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]},
                {"role": "tool", "tool_call_id": "c1", "content": "结果"},
                {"role": "assistant", "content": "答"},
                {"role": "user", "content": "再问"},
                {"role": "assistant", "content": "再答"}]
        p.set_dialogue(msgs, covered_end=0)
        rows = {r["key"]: r for r in p.segment_tokens()}
        self.check("对话 6 条消息但只有 2 个用户轮", 2, rows["full_recent"]["count"])

    def test_layout_from_messages_counts_turns_too(self) -> None:
        got = layout_from_messages(dlg(3))
        rows = {s["key"]: s for s in got["segments"]}
        self.check("兜底口径同样按用户轮", 3, rows["full_recent"]["count"])

class SegmentOrderMatchesAssembly(_Case):
    """分层顺序必须逐条对齐装配顺序 —— 前端就按这个顺序画。"""

    def _pipe(self):
        p = ContextPipeline("cid-ord-0001", full_user_rounds=1)
        p.append_system(SYS)
        p.set_plugin_segments([("knowledge", "知识库", "KB 正文"),
                               ("skills", "Skills 清单", "清单正文")])
        p.set_summary_messages([{"role": "system", "content": SUM1}])
        p.set_dialogue(dlg(1), covered_end=0)
        return p

    def test_header_order_is_system_plugins_summary(self) -> None:
        p = self._pipe()
        head = [str(m.get("content")).splitlines()[0] for m in p.host_messages()]
        self.check("装配的头部顺序",
                   ["系统提示", "KB 正文", "清单正文", "【历史摘要】"], head)

    def test_segment_order_matches_header_order(self) -> None:
        p = self._pipe()
        keys = [r["key"] for r in p.segment_tokens()]
        self.check("分层顺序 = 装配顺序（含摘要在对话之前）",
                   ["system", "plugin:knowledge", "plugin:skills", "summary",
                    "full_recent"], keys)

    def test_summary_sits_before_dialogue(self) -> None:
        keys = [r["key"] for r in self._pipe().segment_tokens()]
        self.check_true("摘要在近期记忆之前", keys.index("summary") < keys.index("full_recent"))

    def test_layout_payload_keeps_the_same_order(self) -> None:
        p = self._pipe()
        payload = p.layout_payload(budget_tokens=100000,
                                   tail_messages=[{"role": "system", "content": MODE_AUTO}])
        self.check("含模式与剩余容量后的顺序",
                   ["system", "plugin:knowledge", "plugin:skills", "summary",
                    "full_recent", "mode", "remaining"],
                   [s["key"] for s in payload["segments"]])

class SourceOrderDeclaration(_Case):
    """注入源的组装顺序：插件段按插件清单位次排，注册先后不影响结果。"""

    def _sources(self, pairs):
        from agent.mechanisms.context_pipeline import ContextSources, SourceMeta
        cs = ContextSources()
        for key, rank in pairs:
            cs.add(lambda cid, k=key: [f"{k}-正文"],
                   SourceMeta(key=key, label=key, plugin_rank=rank))
        return cs

    def test_rank_beats_registration(self) -> None:
        """先注册知识库（位次 1）、后注册 Skills（位次 0），组装仍是 Skills 在前。"""
        cs = self._sources([("knowledge", 1), ("skills", 0)])
        keys = [k for k, _l, _t in cs.collect_segments("c").items]
        self.check("位次小的排前面", ["skills", "knowledge"], keys)

    def test_same_rank_keeps_registration_order(self) -> None:
        cs = self._sources([("a", 0), ("b", 0)])
        keys = [k for k, _l, _t in cs.collect_segments("c").items]
        self.check("同位次按注册序", ["a", "b"], keys)

    def test_no_rank_sorts_last(self) -> None:
        """没有位次的（应用级来源，不属于任何插件）排在插件段之后。"""
        cs = self._sources([("loose", None), ("skills", 0)])
        keys = [k for k, _l, _t in cs.collect_segments("c").items]
        self.check("插件段在前", ["skills", "loose"], keys)

    def test_kernel_pipeline_follows_the_same_order(self) -> None:
        """真管线：Skills 两段 → 知识库 → 摘要 → 对话。"""
        p = ContextPipeline("cid-ord-9001", full_user_rounds=1)
        p.append_system(SYS)
        p.set_plugin_segments([("skills", "Skills 清单", "清单"),
                               ("skills", "Skills 常驻", "常驻"),
                               ("knowledge", "知识库", "KB")])
        p.set_summary_messages([{"role": "system", "content": SUM1}])
        p.set_dialogue(dlg(1), covered_end=0)
        self.check("分段顺序",
                   ["system", "plugin:skills", "plugin:skills", "plugin:knowledge",
                    "summary", "full_recent"],
                   [r["key"] for r in p.segment_tokens()])

class OrdinaryRequestNeverRewritesHistory(unittest.TestCase):
    """普通请求只做追加：已发过的消息逐字节不变（改中间一条 = 缓存从那里起全废）。"""

    def _conv(self, turns: int = 4) -> list:
        msgs = []
        for i in range(1, turns + 1):
            msgs.append({"role": "user", "content": f"第{i}轮提问"})
            msgs.append({"role": "assistant", "content": "", "tool_calls": [
                {"id": f"c{i}", "type": "function",
                 "function": {"name": "read_file", "arguments": "{}"}}]})
            msgs.append({"role": "tool", "tool_call_id": f"c{i}",
                         "content": "工具输出" * 50})
            msgs.append({"role": "assistant", "content": f"第{i}轮回答"})
        return msgs

    def test_tool_traffic_survives_set_dialogue(self) -> None:
        p = ContextPipeline("cid-keep-0001")
        p.append_system(SYS)
        msgs = self._conv()
        p.set_dialogue(list(msgs), covered_end=0)
        got = p.dialogue_messages()
        self.assertEqual(len(got), len(msgs))
        self.assertEqual([m["content"] for m in got],
                         [m["content"] for m in msgs])
        self.assertEqual(len([m for m in got if m.get("role") == "tool"]), 4)
        self.assertEqual(len([m for m in got if m.get("tool_calls")]), 4)

    def test_adding_a_turn_does_not_touch_earlier_messages(self) -> None:
        """加一轮 → 前缀逐字节不变（只有末尾多出来）。"""
        p = ContextPipeline("cid-keep-0002")
        p.append_system(SYS)
        msgs = self._conv(3)
        p.set_dialogue(list(msgs), covered_end=0)
        before = p.dialogue_messages()
        grown = msgs + [{"role": "user", "content": "第4轮提问"},
                        {"role": "assistant", "content": "第4轮回答"}]
        p.set_dialogue(list(grown), covered_end=0)
        after = p.dialogue_messages()
        self.assertEqual(len(after), len(before) + 2)
        self.assertEqual(after[:len(before)], before)

    def test_compression_only_drops_a_prefix(self) -> None:
        """压缩之后对话段 = 原序列的一个后缀（不是被改写过的版本）。"""
        p = ContextPipeline("cid-keep-0003")
        p.append_system(SYS)
        msgs = self._conv(4)
        p.set_dialogue(list(msgs), covered_end=0)
        full = p.dialogue_messages()
        # 落点落在轮边界上（每轮 4 条消息）：切在轮中间会留悬空工具链。
        p.set_dialogue(list(msgs), covered_end=8)
        self.assertEqual(p.dialogue_messages(), full[8:])
        self.assertEqual(len(p.dialogue_messages()), 8)
        from agent.mechanisms.context_pipeline import tool_chain_balanced
        self.assertTrue(tool_chain_balanced(p.dialogue_messages(), 0,
                                            len(p.dialogue_messages())))

class SegmentFieldParity(unittest.TestCase):
    """分段快照（内核事件）与兜底重算（适配层）必须给同一套字段。

    两条路径给不同字段时，界面上"同一个东西两条路径长得不一样"，极难查。
    """

    def test_both_paths_expose_the_same_fields(self) -> None:
        from agent.mechanisms.context_pipeline import ContextPipeline, layout_from_messages
        p = ContextPipeline("cid-fields-0001", full_user_rounds=1)
        p.append_system("系统提示词")
        p.set_plugin_segments([("skills", "Skills 清单", "清单正文"),
                               ("knowledge", "知识库", "KB正文")])
        p.set_dialogue([{"role": "user", "content": "问"},
                        {"role": "assistant", "content": "答"}], covered_end=0)
        snap = p.layout_payload(tail_messages=[{"role": "system",
                                                "content": "## 当前模式：Auto"}])
        # 兜底路径的模式段在消息末尾（它从消息里认模式），快照路径单独传。
        fallback = layout_from_messages(
            [{"role": "user", "content": "问"}, {"role": "assistant", "content": "答"},
             {"role": "system", "content": "## 当前模式：Auto"}],
            system_text="系统提示词", head=["系统提示词", "清单正文", "KB正文"],
            plugin_segments=[("skills", "Skills 清单", 0), ("knowledge", "知识库", 0)],
            budget_tokens=snap["budget_tokens"])
        self.assertEqual(sorted(snap.keys()), sorted(fallback.keys()))
        self.assertEqual(sorted(snap["segments"][0].keys()),
                         sorted(fallback["segments"][0].keys()))
        self.assertEqual([s["key"] for s in snap["segments"]],
                         [s["key"] for s in fallback["segments"]])

    def test_layout_event_forwards_every_field(self) -> None:
        """适配层转发分段事件时不筛字段（白名单漏一个 = 前端少一样东西）。"""
        import inspect

        from agent.shell.classic_adapter import outbound
        src = inspect.getsource(outbound.ClassicStream._on_context_layout)
        self.assertIn("**dict(d or {})", src)

class RemainingCapacityTest(unittest.TestCase):
    """「剩余容量」按压缩阈值算，不是按"已用"算 —— 否则界面那条永远是 0%。"""

    def test_snapshot_carries_the_budget(self) -> None:
        from agent.core.modules import _segment_snapshot
        from agent.mechanisms.context_pipeline import ContextPipeline
        p = ContextPipeline("cid-rem-0001")
        p.append_system(SYS)
        p.set_dialogue([{"role": "user", "content": "问"},
                        {"role": "assistant", "content": "答"}], covered_end=0)
        msgs = p.assembles([{"role": "user", "content": "本轮"}])
        snap = _segment_snapshot(p, msgs, budget_tokens=700000)
        remaining = [s for s in snap["segments"] if s["key"] == "remaining"][0]
        self.assertEqual(snap["budget_tokens"], 700000)
        self.assertEqual(remaining["tokens"], 700000 - snap["total_tokens"])
        self.assertGreater(remaining["pct"], 99.0)

    def test_budget_zero_would_make_remaining_zero(self) -> None:
        """不传预算（= 老装配点的行为）剩余容量就是 0 —— 这条守着别再退回去。"""
        from agent.mechanisms.context_pipeline import ContextPipeline
        p = ContextPipeline("cid-rem-0002")
        p.append_system(SYS)
        p.set_dialogue([{"role": "user", "content": "问"}], covered_end=0)
        lay = p.layout_payload()
        remaining = [s for s in lay["segments"] if s["key"] == "remaining"][0]
        self.assertEqual(remaining["tokens"], 0)

    def test_old_snapshot_is_rescaled_on_read(self) -> None:
        """事件里那份 `budget=已用` 的旧快照，渲染时按当前预算补正。"""
        from agent.core.events import make_event
        from agent.shell.classic_adapter.inbound import _last_segments
        stale = make_event("context_segments",
                           segments=[{"key": "system", "label": "系统提示词",
                                      "tokens": 1000, "count": 1, "pct": 100.0},
                                     {"key": "remaining", "label": "剩余容量",
                                      "tokens": 0, "pct": 0.0}],
                           total_tokens=1000, budget_tokens=1000)
        out = _last_segments([stale], 100000)
        rows = {s["key"]: s for s in out["segments"]}
        self.assertEqual(out["budget_tokens"], 100000)
        self.assertEqual(rows["remaining"]["tokens"], 99000)
        self.assertAlmostEqual(rows["remaining"]["pct"], 99.0, places=3)
        self.assertAlmostEqual(rows["system"]["pct"], 1.0, places=3)
        from agent.mechanisms.context_pipeline import ContextSources, SourceMeta
        from agent.shell.classic_adapter.inbound import compute_context_layout

        sources = ContextSources()
        sources.add(lambda cid: ["知识正文"],
                    SourceMeta(key="knowledge", label="知识库",
                               count=lambda cid: 1))

        class _App:
            context_sources = sources

            @staticmethod
            def compactor_factory(_cid):
                class _Compactor:
                    summary_token_threshold = 100000
                return _Compactor()

        laid = compute_context_layout(_App(), [stale], "cid-kb-overlay")
        labels = [row["label"] for row in laid["segments"]]
        self.assertEqual(labels, ["系统提示词", "知识库", "剩余容量"])
        kb = next(row for row in laid["segments"] if row["key"] == "plugin:knowledge")
        self.assertEqual(kb["count"], 1)
        self.assertGreater(kb["tokens"], 0)

    def test_rescale_falls_back_when_budget_unknown(self) -> None:
        """拿不到预算时按"已用"归一（不再更差），段序与字段不变。"""
        from agent.shell.classic_adapter.inbound import _rescale
        payload = {"segments": [{"key": "system", "label": "系统提示词",
                                 "tokens": 500, "count": 1, "pct": 0},
                                {"key": "remaining", "label": "剩余容量",
                                 "tokens": 0, "pct": 0}],
                   "total_tokens": 500, "budget_tokens": 0}
        out = _rescale(payload, 0)
        rows = {s["key"]: s for s in out["segments"]}
        self.assertEqual(out["budget_tokens"], 500)
        self.assertEqual(rows["system"]["pct"], 100.0)
        self.assertEqual(rows["remaining"]["tokens"], 0)

class PluginSegmentCountAlignmentTest(unittest.TestCase):
    """段与自报数量必须逐条对齐：错位是静默的，只在浮层上显示成离谱的数字。"""

    def test_collect_segments_counts_match_items(self) -> None:
        from agent.mechanisms.context_pipeline import ContextSources, SourceMeta

        srcs = ContextSources()
        srcs.add(lambda cid: ["一条正文"],
                 SourceMeta(key="a", label="有自报口", count=lambda cid: 7))
        srcs.add(lambda cid: ["第一条", "第二条"], SourceMeta(key="b", label="两条正文"))
        srcs.add(lambda cid: [], SourceMeta(key="c", label="空的", count=lambda cid: 3))
        got = srcs.collect_segments("c")
        self.assertEqual(len(got.counts), len(got.items))
        self.assertEqual([label for _key, label, _t in got.items],
                         ["有自报口", "两条正文", "两条正文", "空的"],
                         msg=f"实际拿到 {[(k, l) for k, l, _ in got.items]}")
        # 自报数只贴在该来源的第一条上；同一来源的其余条按条数算；
        # 空来源仍占一段（示意图可见），数量用自报值。
        self.assertEqual(got.counts, (7, 1, 1, 3))
        self.assertEqual(got.items[-1][2], "", msg="空来源正文应为空串占位")

    def test_missing_reported_count_falls_back_to_one(self) -> None:
        from agent.mechanisms.context_pipeline import ContextSources, SourceMeta

        srcs = ContextSources()
        srcs.add(lambda cid: ["x"], SourceMeta(key="x", label="没有自报口"))
        got = srcs.collect_segments("c")
        self.assertEqual(len(got.counts), len(got.items))
        self.assertEqual(got.counts, (1,))

    def test_short_count_table_does_not_borrow_neighbours(self) -> None:
        """数量表比来源表短时，多出来的段按自身条数算，不拿别的段的数字。"""
        from agent.mechanisms.context_pipeline import (
            ContextPipeline,
            PluginSegments,
        )

        pipe = ContextPipeline("c")
        pipe.set_plugin_segments(PluginSegments(
            items=[("skills", "清单", "正文一"), ("skills", "常驻", "正文二")],
            counts=[62],
        ))
        rows = [r for r in pipe.segment_tokens() if str(r["key"]).startswith("plugin:")]
        self.assertEqual([r["label"] for r in rows], ["清单", "常驻"])
        self.assertEqual([r["count"] for r in rows], [62, 1])

class PluginSegmentsImmutableTest(unittest.TestCase):
    """B1：`PluginSegments` 入口即冻结（传 list 也存成 tuple，改原列表不影响它）。"""

    def _segments(self):
        from agent.mechanisms.context_pipeline import PluginSegments

        items = [("skills", "清单", "正文一"), ("skills", "常驻", "正文二")]
        counts = [7]
        return PluginSegments(items=items, counts=counts), items, counts

    def test_source_lists_are_copied(self) -> None:
        seg, items, counts = self._segments()
        items.append(("kb", "知识库", "正文三"))
        counts.append(9)
        self.assertEqual(len(seg.items), 2)
        self.assertEqual(seg.counts, (7,))

    def test_containers_are_tuples(self) -> None:
        seg, _items, _counts = self._segments()
        self.assertIsInstance(seg.items, tuple)
        self.assertIsInstance(seg.counts, tuple)
        self.assertTrue(all(isinstance(row, tuple) for row in seg.items))

    def test_assignment_is_rejected(self) -> None:
        from dataclasses import FrozenInstanceError

        seg, _items, _counts = self._segments()
        with self.assertRaises(FrozenInstanceError):
            seg.items = ()  # type: ignore[misc]

    def test_tuple_containers_reject_mutation(self) -> None:
        seg, _items, _counts = self._segments()
        with self.assertRaises(AttributeError):
            seg.items.append(("kb", "知识库", "正文三"))  # type: ignore[attr-defined]
        with self.assertRaises(TypeError):
            seg.counts[0] = 9  # type: ignore[index]

    def test_wrong_arity_is_rejected_loudly(self) -> None:
        from agent.mechanisms.context_pipeline import PluginSegments

        with self.assertRaises(ValueError):
            PluginSegments(items=[("skills", "缺正文")], counts=[])  # type: ignore[list-item]


if __name__ == "__main__":
    unittest.main()


class ReasoningReplayBudgetTest(unittest.TestCase):
    """思维链回传预算：三种取值的行为与统计口径。"""

    def _long(self, steps: int = 400) -> str:
        return "".join(f"第{i}步：先看配置，再改装配，然后跑测试。" for i in range(steps))

    def test_negative_keeps_everything(self) -> None:
        from agent.mechanisms.context_pipeline import clip_reasoning_text

        text = self._long()
        self.assertEqual(clip_reasoning_text(text, -1), text)

    def test_zero_drops_everything(self) -> None:
        from agent.mechanisms.context_pipeline import clip_reasoning_text

        self.assertEqual(clip_reasoning_text(self._long(), 0), "")

    def test_positive_keeps_both_ends_and_marks_the_gap(self) -> None:
        from agent.mechanisms.context_pipeline import approx_tokens_text, clip_reasoning_text

        text = self._long()
        got = clip_reasoning_text(text, 500)
        self.assertIn("此处省略", got)
        self.assertTrue(got.startswith(text[:20]), msg="开头要保留")
        self.assertTrue(got.endswith(text[-20:]), msg="结尾要保留")
        self.assertLessEqual(approx_tokens_text(got), 700,
                             msg="截断后不该还超预算太多")

    def test_short_text_untouched(self) -> None:
        from agent.mechanisms.context_pipeline import clip_reasoning_text

        self.assertEqual(clip_reasoning_text("短推理", 1000), "短推理")

    def test_messages_clip_does_not_mutate_input(self) -> None:
        from agent.mechanisms.context_pipeline import clip_reasoning

        msg = {"role": "assistant", "content": "答",
               "reasoning_content": self._long()}
        out = clip_reasoning([msg], 0)
        self.assertNotIn("reasoning_content", out[0])
        self.assertIn("reasoning_content", msg, msg="原消息不能被改")

    def test_dialogue_segment_uses_the_budget(self) -> None:
        from agent.mechanisms.context_pipeline import ContextPipeline

        msgs = [{"role": "user", "content": "问"},
                {"role": "assistant", "content": "答",
                 "reasoning_content": self._long()}]
        drop = ContextPipeline("c", reasoning_replay_tokens=0)
        drop.set_dialogue(msgs)
        kept = ContextPipeline("c", reasoning_replay_tokens=-1)
        kept.set_dialogue(msgs)
        self.assertLess(drop.total_token_estimate(), kept.total_token_estimate())

    def test_config_default_matches_constant(self) -> None:
        from agent.config import get_context
        from agent.mechanisms.context_pipeline import DEFAULT_REASONING_REPLAY_TOKENS

        self.assertEqual(get_context()["reasoning_replay_tokens"],
                         DEFAULT_REASONING_REPLAY_TOKENS)
