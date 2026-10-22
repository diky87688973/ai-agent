# -*- coding: utf-8 -*-
"""恢复 = 往上下文末尾拼接工具结果。

    接口确认没有用户输入 → 恢复轮的上下文末端就是那次工具调用
    → 把结果拼接进去 → `…assistant(tool_calls) → tool` 天然对齐
    → 宿主重新调模型，闭环。

要证明三件事：
  ① 拼接后的消息序列恰好合法（`tool` 紧跟带 `tool_calls` 的 `assistant`；
     不插入任何用户消息）——这正是模型 API 的硬规则。
  ② 确认那一刻写入 `tool_result` 事实即完成拼接，恢复路径上没有外部结果暂存表。
  ③ 用现有真实存储（core.session_store）承载，端到端可跑。
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

from agent.core.events import Event
from agent.core.session_context import SessionContext
from agent.core.session_log import SessionLog


class _Facts:
    """最小事实源：append + scan（真实实现是 SessionStore）。"""

    def __init__(self) -> None:
        self.rows: List[Dict[str, Any]] = []

    def append(self, type_: str, **data: Any) -> str:
        self.rows.append({"type": type_, **data})
        return str(len(self.rows))

    def scan(self, type_: str) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.rows if r["type"] == type_]

class ContextSpliceTest(unittest.TestCase):
    """恢复即拼接。"""

    def _suspended_rows(self) -> List[Dict[str, Any]]:
        """挂起那一刻的上下文：用户输入 → 模型要调工具 → 工具调用（未返回）。"""
        return [
            {"type": "input_claimed", "content": "帮我问用户一个问题"},
            {"type": "model_message", "content": "",
             "tool_calls": [{"id": "call-1", "name": "ask_user"}]},
            {"type": "tool_call", "call_id": "call-1", "name": "ask_user"},
            {"type": "tool_suspended", "call_id": "call-1", "question": "选一个"},
        ]

    def test_spliced_result_lands_exactly_after_the_tool_call(self) -> None:
        """① 拼接后 `tool` 紧跟带 `tool_calls` 的 `assistant`——不插任何用户消息。"""
        rows = self._suspended_rows()
        # 用户确认 → 直接把结果拼到上下文末尾（没有暂存表）
        # 内核写结果的真实形态是两条：结果事实 `tool_done` + 终态 `tool_ended`
        rows.append({"type": "tool_done", "call_id": "call-1", "name": "ask_user",
                     "data": {"confirm": "甲"}})
        rows.append({"type": "tool_ended", "call_id": "call-1", "name": "ask_user",
                     "status": "ok"})

        messages = SessionLog(events=[Event(r["type"], {k: v for k, v in r.items()
                                                        if k != "type"}) for r in rows]
                              ).derive_messages()
        roles = [m["role"] for m in messages]
        self.assertEqual(roles, ["user", "assistant", "tool"],
                         msg=f"序列必须恰好是 user→assistant(tool_calls)→tool，实际 {roles}")
        self.assertEqual(messages[1]["tool_calls"][0]["id"], "call-1")
        self.assertEqual(messages[2]["tool_call_id"], "call-1",
                         msg="tool 消息必须应答那条 tool_call")
        self.assertEqual(
            messages[2]["content"],
            json.dumps({"ok": True, "data": {"confirm": "甲"}}, ensure_ascii=False),
        )

    def test_no_user_message_is_inserted_on_resume(self) -> None:
        """恢复轮没有用户输入：绝不能凭空多一条 user 消息——那会让请求序列非法。"""
        rows = self._suspended_rows()
        rows.append({"type": "tool_done", "call_id": "call-1", "name": "ask_user", "data": "甲"})
        rows.append({"type": "tool_ended", "call_id": "call-1", "name": "ask_user", "status": "ok"})
        messages = SessionLog(events=[Event(r["type"], {k: v for k, v in r.items()
                                                        if k != "type"}) for r in rows]
                              ).derive_messages()
        users = [m for m in messages if m["role"] == "user"]
        self.assertEqual(len(users), 1, msg="只有最初那条用户输入，恢复轮不产生新的")

    def test_stale_empty_input_in_old_records_is_tolerated(self) -> None:
        """第二道防线：会话记录里存着空的 `input_claimed` 时，派生仍必须给出合法序列。

        回合层按"无新输入不发 `input_claimed`"处理是第一道；但落盘的历史里可能已经
        存了空的那条。若派生层据此造一条空的 user 消息，那段记录就永远打不开——
        一加载就是非法序列。所以派生层也必须守住"无输入 = 无用户消息"。
        """
        rows = self._suspended_rows()
        # 在 `assistant(tool_calls)` 与 `tool_call` 之间插一条空的 input_claimed
        broken = rows[:2] + [{"type": "input_claimed", "content": ""}] + rows[2:]
        broken.append({"type": "tool_done", "call_id": "call-1", "name": "ask_user", "data": "甲"})
        broken.append({"type": "tool_ended", "call_id": "call-1", "name": "ask_user", "status": "ok"})
        messages = SessionLog(events=[Event(r["type"], {k: v for k, v in r.items()
                                                        if k != "type"}) for r in broken]
                              ).derive_messages()
        self.assertEqual([m["role"] for m in messages], ["user", "assistant", "tool"],
                         msg="空输入不该派生用户消息——否则老记录加载即非法")
        self.assertEqual(messages[2]["tool_call_id"], "call-1")

    def test_real_store_carries_the_splice(self) -> None:
        """③ 用现有真实存储：确认那一刻写下结果事实就完成了拼接。"""
        from agent.mechanisms.session_store import SessionStore

        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))
            cid = "splice-probe"
            events = [Event(r["type"], {k: v for k, v in r.items() if k != "type"})
                      for r in self._suspended_rows()]
            store.append(cid, events)

            # 用户确认 → 写结果事实 + 终态（内核写结果的真实形态，唯一写点）
            store.append(cid, [
                Event("tool_done", {"call_id": "call-1", "name": "ask_user",
                                    "data": {"confirm": "甲"}}),
                Event("tool_ended", {"call_id": "call-1", "name": "ask_user",
                                     "status": "ok"}),
            ])

            log = SessionLog(events=store.load(cid))
            messages = log.derive_messages()
            self.assertEqual([m["role"] for m in messages], ["user", "assistant", "tool"])
            # 落盘后仍可重建（重启/换进程都一样）
            again = SessionLog(events=store.load(cid)).derive_messages()
            self.assertEqual(again, messages)

    def test_no_staging_table_is_needed(self) -> None:
        """② 恢复路径上不需要外部结果暂存表之类的东西：事实源里只有工具结果。"""
        store = _Facts()
        for r in self._suspended_rows():
            store.append(r["type"], **{k: v for k, v in r.items() if k != "type"})
        store.append("tool_done", call_id="call-1", name="ask_user", data="甲")
        kinds = [r["type"] for r in store.rows]
        self.assertIn("tool_suspended", kinds, msg="挂起信息要落盘：宿主靠它知道有调用待解决")
        self.assertNotIn("extern_result", kinds, msg="不需要暂存表")
        delivered = store.scan("tool_done")
        self.assertEqual(len(delivered), 1)
        self.assertEqual(delivered[0]["call_id"], "call-1")

    def test_repeated_terminal_folds_to_one_tool_message(self) -> None:
        """同一 `call_id` 的终态写两次时，派生对话里只有一条 tool 消息。

        写前查重后，事实里也只有一组终态，派生结果同样是一条 tool 消息。
        """

        def _roles_and_tools(rows):
            messages = SessionLog(events=[
                Event(r["type"], {k: v for k, v in r.items() if k != "type"}) for r in rows
            ]).derive_messages()
            return [m["role"] for m in messages], len(
                [m for m in messages if m["role"] == "tool"])

        # 同一 call_id 的终态重复出现：派生时收成一条 tool 消息。
        naive = self._suspended_rows()
        for _ in range(2):
            naive.append({"type": "tool_done", "call_id": "call-1", "name": "a", "data": "甲"})
            naive.append({"type": "tool_ended", "call_id": "call-1", "name": "a",
                          "status": "ok"})
        roles, tools = _roles_and_tools(naive)
        self.assertEqual(tools, 1)
        self.assertEqual(roles, ["user", "assistant", "tool"])

        # 正面：写前查重（宿主应当这么做）→ 只有一条
        guarded = self._suspended_rows()
        for _ in range(2):                      # 用户连点两次确认
            already = {r["call_id"] for r in guarded if r["type"] == "tool_done"}
            if "call-1" not in already:
                guarded.append({"type": "tool_done", "call_id": "call-1",
                                "name": "ask_user", "data": "甲"})
                guarded.append({"type": "tool_ended", "call_id": "call-1",
                                "name": "ask_user", "status": "ok"})
        roles, tools = _roles_and_tools(guarded)
        self.assertEqual((roles, tools), (["user", "assistant", "tool"], 1))

class AwaitingFactTest(unittest.TestCase):
    """挂起信息落盘与"待解决"判定（宿主靠它知道有调用等人）。"""

    def test_pending_call_is_discoverable_from_facts(self) -> None:
        rows = [
            {"type": "tool_call", "call_id": "call-1"},
            {"type": "tool_suspended", "call_id": "call-1", "question": "选一个"},
        ]
        suspended = {r["call_id"] for r in rows if r["type"] == "tool_suspended"}
        resolved = {r["call_id"] for r in rows if r["type"] == "tool_done"}
        self.assertEqual(suspended - resolved, {"call-1"},
                         msg="待解决 = 已挂起且未回灌")

    def test_pending_state_is_readable_from_facts_not_from_session_context(self) -> None:
        """挂起状态从事实源可读 —— 判定"有待解决的调用"只凭事实就够。

        `SessionContext.pending_confirm` 上另存的一份是冗余的；这里钉住"仅凭事实就能判定待解决调用"，
        使该字段不再是判定依据。
        """
        rows = [
            {"type": "tool_call", "call_id": "call-1"},
            {"type": "tool_suspended", "call_id": "call-1", "question": "选一个"},
        ]
        pending = {r["call_id"] for r in rows if r["type"] == "tool_suspended"} - {
            r["call_id"] for r in rows if r["type"] == "tool_done"}
        self.assertEqual(pending, {"call-1"}, msg="待解决调用须仅凭事实可判定")
        # 同一份信息在会话上下文里的那份是冗余的
        ctx = SessionContext(conversation_id="x")
        self.assertTrue(hasattr(ctx, "pending_confirm"),
                        msg="该字段仍存在，但判定不该依赖它")

if __name__ == "__main__":
    unittest.main()

class ResumeSpliceNamingTest(unittest.TestCase):
    """`_splice_resume` 必须写内核当前认的结果事实名。

    写错名字的后果不是"没效果"，而是派生出一条多余的 tool 消息：
    同一 `tool_call_id` 出现两条，模型 API 直接 400
    （`Messages with role 'tool' must be a response to a preceding message with 'tool_calls'`）。
    这条用例钉住那个名字。
    """

    def test_written_fact_name_is_the_one_kernel_consumes(self) -> None:
        from agent.mechanisms.session_store import SessionStore
        from agent.shell.session.runner import SessionRunner

        class _Store:
            def __init__(self, s):
                self.s = s

            def load(self, cid):
                return self.s.load(cid)

            def append(self, cid, evs):
                return self.s.append(cid, evs)

        class _App:
            def __init__(self, store):
                self.store = store

            def session(self, *a, **k):
                raise AssertionError("不该走到创建引擎这一步")

        with tempfile.TemporaryDirectory() as tmp:
            store = SessionStore(Path(tmp))
            cid = "resume-naming-0001"
            store.append(cid, [
                Event("turn_started", {"text": "跑个工具"}),
                Event("model_message", {"content": "", "tool_calls": [
                    {"id": "call-1", "name": "ask_user", "arguments": {}}]}),
                Event("tool_started", {"call_id": "call-1", "name": "ask_user",
                                       "arguments": {}}),
                Event("tool_suspended", {"call_id": "call-1", "name": "ask_user"}),
            ])
            runner = SessionRunner.__new__(SessionRunner)
            runner._app = _App(_Store(store))
            runner._splice_resume(cid, {"call_id": "call-1", "ok": True,
                                        "data": "用户选了甲", "name": "ask_user"})
            # 连调两次：写前查重必须挡住第二次（拼接没有幂等性）
            runner._splice_resume(cid, {"call_id": "call-1", "ok": True,
                                        "data": "用户选了甲", "name": "ask_user"})

            facts = [e.type for e in store.load(cid)]
            self.assertEqual(facts.count("tool_done"), 1,
                             msg=f"结果事实应恰好一条，实际 {facts}")
            self.assertEqual(facts.count("tool_ended"), 1,
                             msg="结果后面必须有终态，模型才收得到这条 tool 消息")
            self.assertNotIn("tool_result", facts,
                             msg="不得写内核不认的名字（会造成两条 tool 消息 → API 400）")

            tool_msgs = [m for m in SessionLog(events=store.load(cid)).derive_messages()
                         if m["role"] == "tool"]
            self.assertEqual(len(tool_msgs), 1,
                             msg=f"同一 call_id 只允许一条 tool 消息，实际 {len(tool_msgs)}")
            payload = json.loads(str(tool_msgs[0]["content"]))
            self.assertEqual(payload.get("ok"), True, msg="回填须走统一信封")
            self.assertIn("用户选了甲", json.dumps(payload.get("data"), ensure_ascii=False),
                          msg="回填的内容必须真的到模型手里")
