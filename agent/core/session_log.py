# -*- coding: utf-8 -*-
"""会话记录：事实 append + 模型历史 derive。

纪律：模型可见 ⟺ 已记录 —— derive 只从已 append 的事实投影，
不维护第二份"仅供参考"的历史。
"""
from __future__ import annotations

import json
from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional

from agent.core.error_report import report_error
from agent.core.event_name import TOOL_CANCELED, TOOL_ENDED, TURN_STARTED
from agent.core.events import Event
from agent.core.model_call import PROVIDER_META_KEY
from agent.core.state_values import TOOL_CANCEL_INPUT_INSERTED, TOOL_CANCEL_INPUT_INSERTED_TEXT
from agent.core.state_values import TOOL_SUSPENDED as TOOL_STATUS_SUSPENDED


def _user_content(text: str, attachments: Any) -> Any:
    """用户消息的 content：无附件 → 纯字符串；有附件 → 多模态 content 数组。

    多模态形态（OpenAI 兼容）：`[{"type":"text",...}, {"type":"image_url",...}]`；
    附件以 `data:<mime>;base64,<data>` 内联。文本为空时只发图片。
    """
    if not isinstance(attachments, list) or not attachments:
        return text
    # 嵌图前做本地缩放与预算：内联 base64 计入请求体 48 MiB 上限，
    # 超出时整回合请求被拒。
    from agent.core.image_embed import build_embed_parts, placeholder_text

    parts, skipped = build_embed_parts(attachments)
    # 一张合法附件都没有 → 回落纯文本；但被跳过的附件仍要给模型一句说明，
    # 否则“图没发出去”这个事实在请求里完全消失。
    if not parts:
        note = placeholder_text(skipped, attachments)
        if note:
            return f"{text}\n{note}" if text else note
        return text
    if text:
        parts.insert(0, {"type": "text", "text": text})
    # 超预算的附件转占位文字，使模型知道有图未随请求发送。
    note = placeholder_text(skipped, attachments)
    if note:
        parts.append({"type": "text", "text": note})
    return parts


def _tool_content(text: Any, attachments: Any) -> Any:
    """工具消息的 content：无图 → 纯字符串；有图 → 多模态 content 数组。

    与 `_user_content` 同构，差别在文本处理：工具结果的正文已渲染好（可能是 JSON 串），
    原样保留成第一个 `text` 块，不做类型转换。

    空文本 + 有图时补一句默认说明：`content` 为空数组的 tool 消息在部分网关会被拒。
    """
    if not isinstance(attachments, list) or not attachments:
        return text
    from agent.core.image_embed import build_tool_parts

    parts, note = build_tool_parts(attachments)
    if not parts:
        return text
    body = text if isinstance(text, str) and text else "(工具返回了图片)"
    if note:
        body = f"{body}\n{note}"
    return [{"type": "text", "text": body}, *parts]


def _tool_envelope(*, ok: bool, data: Any = None, error: Any = None,
                   elapsed_s: Any = None) -> str:
    """回灌模型的工具结果信封（成功/失败同形）。

    - 成功：`{"ok": true, "data": …}`
    - 失败：`{"ok": false, "error": "…"}`，可选附带 `data`
    - 有计时时附带 `elapsed_s`（秒）
    """
    if ok:
        payload: dict[str, Any] = {"ok": True, "data": data}
    else:
        payload = {"ok": False, "error": str(error if error is not None else "")}
        if data is not None:
            payload["data"] = data
    if elapsed_s is not None:
        try:
            payload["elapsed_s"] = round(max(0.0, float(elapsed_s)), 3)
        except (TypeError, ValueError) as exc:
            report_error("agent.core.session_log.elapsed_s", exc)
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        if ok:
            return json.dumps({"ok": True, "data": str(data)}, ensure_ascii=False)
        return json.dumps(
            {"ok": False, "error": str(error if error is not None else "")},
            ensure_ascii=False,
        )


def _render_tool_message(call_id: str, done: dict[str, Any] | None, name: str = "") -> dict[str, Any]:
    """把一次调用的结果收成一条 tool 消息。没有结果事实时说明「未记录」，不写 null。"""
    images = done.get("attachments") if isinstance(done, dict) else None
    elapsed_s = done.get("elapsed_s") if isinstance(done, dict) else None
    if done is None:
        content = _tool_envelope(
            ok=False, error=f"工具 {name} 已结束，但未记录结果")
    elif bool(done.get("ok")):
        content = _tool_envelope(
            ok=True, data=done.get("data"), elapsed_s=elapsed_s)
    else:
        content = _tool_envelope(
            ok=False, error=done.get("error"), data=done.get("data"),
            elapsed_s=elapsed_s)
    return {"role": "tool", "tool_call_id": call_id,
            "content": _tool_content(content, images)}


class SessionLogView:
    """`SessionLog` 的只读视图：暴露读取面，不暴露 `append`。

    模块拿到的 `ports.log` 是这个（由 `SessionLog.readonly` 产生）。
    """

    __slots__ = ("_log",)

    def __init__(self, log: "SessionLog") -> None:
        self._log = log

    @property
    def events(self) -> tuple:
        """事实序列的防御性快照：容器与载荷都不与内部共享。

        元组挡住 `append` / `clear` / `[0]=`；事件逐条深拷贝，挡住
        `view.events[0].data[...] = ...` 这类穿过元素改内部状态的做法。
        事实只能经 `Ports.emit` 追加。
        """
        return tuple(deepcopy(event) for event in self._log.events)

    def __getitem__(self, index: int) -> Event:
        """按序号取事实（`log.events[i]` 与 `len(log.events)` 这类读法仍可用）。"""
        return deepcopy(self._log.events[index])

    def derive_messages(self) -> list[dict[str, Any]]:
        return self._log.derive_messages()

    def derive_request_messages(self) -> list[dict[str, Any]]:
        return self._log.derive_request_messages()

    def derive_request_messages_from_latest_wake(self) -> list[dict[str, Any]] | None:
        return self._log.derive_request_messages_from_latest_wake()

    def user_input_sequence(self, ordinal: int) -> int | None:
        """Return the fact coordinate for a user message in the dialogue projection."""
        for event in self._log.events:
            if event.type != "input_claimed":
                continue
            if not str(event.data.get("content", "")) and not event.data.get("attachments"):
                continue
            if ordinal == 0:
                seq = event.data.get("_seq")
                return seq if isinstance(seq, int) and not isinstance(seq, bool) and seq >= 0 else None
            ordinal -= 1
        return None

    def __len__(self) -> int:
        return len(self._log.events)

    def __iter__(self):
        return iter(self.events)

    def __repr__(self) -> str:            # pragma: no cover - 诊断用
        return f"<SessionLogView {len(self._log.events)} events>"



def _closed_tool_calls(events: Any) -> set[str]:
    closed: set[str] = set()
    for ev in events:
        if ev.type != TOOL_ENDED or str(ev.data.get("status") or "") == TOOL_STATUS_SUSPENDED:
            continue
        cid = str(ev.data.get("call_id") or "")
        if cid:
            closed.add(cid)
    return closed


def _input_message(ev: Event) -> dict[str, Any] | None:
    content = str(ev.data.get("content", ""))
    attachments = ev.data.get("attachments")
    if not content and not attachments:
        return None
    if str(ev.data.get("kind") or "") == "wake":
        lines = ["【定时唤醒任务】"]
        job_id = str(ev.data.get("wake_job_id") or "").strip()
        if job_id:
            lines.append(f"job_id: {job_id}")
        due_at = str(ev.data.get("due_at") or "").strip()
        if due_at:
            lines.append(f"due_at: {due_at}")
        lines.extend(["reminder:", content])
        content = "\n".join(lines)
    return {"role": "user", "content": _user_content(content, attachments)}


def _model_message(ev: Event) -> dict[str, Any]:
    msg: dict[str, Any] = {
        "role": "assistant", "content": str(ev.data.get("content", ""))}
    reasoning = str(ev.data.get("reasoning_content") or "")
    if reasoning:
        msg["reasoning_content"] = reasoning
    # 嵌套结构一律深拷：投影结果不能与事实共享可变对象，否则下游改一下
    # （例如往 thinking_blocks 里补项）会回写进事实源，而事故点离改动点隔着几层。
    calls = ev.data.get("tool_calls") or []
    if calls:
        msg["tool_calls"] = deepcopy(calls)
    meta = ev.data.get(PROVIDER_META_KEY)
    if meta:
        msg[PROVIDER_META_KEY] = deepcopy(meta)
    return msg


def _tool_ended_message(ev: Event, results: dict[str, dict[str, Any]],
                        emitted: set[str]) -> dict[str, Any] | None:
    if str(ev.data.get("status") or "") == TOOL_STATUS_SUSPENDED:
        return None
    call_id = str(ev.data.get("call_id", ""))
    if call_id in emitted:
        return None
    emitted.add(call_id)
    return _render_tool_message(
        call_id, results.get(call_id), str(ev.data.get("name") or ""))


def _tool_result_message(ev: Event, closed: set[str],
                         results: dict[str, dict[str, Any]],
                         emitted: set[str]) -> dict[str, Any] | None:
    call_id = str(ev.data.get("call_id", ""))
    if not call_id:
        return None
    error = ev.data.get("error")
    if ev.type == TOOL_CANCELED:
        if ev.data.get("reason") != TOOL_CANCEL_INPUT_INSERTED:
            return None
        error = error or TOOL_CANCEL_INPUT_INSERTED_TEXT
    results[call_id] = {
        "ok": ev.type == "tool_done", "data": ev.data.get("data"),
        "error": error, "attachments": ev.data.get("attachments"),
        "elapsed_s": ev.data.get("elapsed_s")}
    if call_id in closed or call_id in emitted:
        return None
    emitted.add(call_id)
    return _render_tool_message(call_id, results[call_id])


def _tool_fact_message(ev: Event, results: dict[str, dict[str, Any]],
                       emitted: set[str]) -> dict[str, Any] | None:
    call_id = str(ev.data.get("call_id", ""))
    if not call_id or call_id in results:
        return None
    if ev.data.get("await_user"):
        results[call_id] = {"ok": True, "data": None, "error": ""}
        return None
    ok = bool(ev.data.get("ok"))
    elapsed_s = ev.data.get("elapsed_s")
    content = (_tool_envelope(ok=True, data=ev.data.get("data"),
                              elapsed_s=elapsed_s) if ok
               else _tool_envelope(ok=False, error=ev.data.get("error"),
                                   data=ev.data.get("data"),
                                   elapsed_s=elapsed_s))
    results[call_id] = {
        "ok": ok, "data": ev.data.get("data"), "error": ev.data.get("error"),
        "elapsed_s": elapsed_s}
    emitted.add(call_id)
    return {"role": "tool", "tool_call_id": call_id, "content": content}


@dataclass
class SessionLog:
    """append-only 事实序列。"""

    events: list[Event] = field(default_factory=list)

    def append(self, events: Iterable[Event]) -> None:
        """把一批已发生的事实追加进记录。"""
        self.events.extend(events)

    def readonly(self) -> "SessionLogView":
        """只读视图：能派生、能遍历，不能追加。

        给模块用（`Ports.log`）。模块要写事实必须走 `ports.emit(...)` ——
        那条路会同时入日志与通知观察面。直接 `log.append(...)` 会造成
        "模型看得见、观察面看不见"的单向秘密事实：模块直接
        `log.events.append(model_message)` 后，sink 只收到 `turn_started`/`turn_ended`，
        而 `derive_messages` 已经能看到那条"从没经过 emit"的回答。

        用视图而非元组：`SessionLog` 是共用数据契约
        （跨层共用），改它的字段类型会波及大量调用点；视图达到同等约束
        而不动契约。
        """
        return SessionLogView(self)

    @staticmethod
    def _derive_messages(events: Iterable[Event]) -> list[dict[str, Any]]:
        """从给定事实区间投影模型可见消息序列。"""
        messages: list[dict[str, Any]] = []
        results: dict[str, dict[str, Any]] = {}
        emitted: set[str] = set()
        event_rows = list(events)
        closed = _closed_tool_calls(event_rows)
        for ev in event_rows:
            if ev.type == "input_claimed":
                msg = _input_message(ev)
            elif ev.type == "model_message":
                msg = _model_message(ev)
            elif ev.type == "tool_ended":
                msg = _tool_ended_message(ev, results, emitted)
            elif ev.type in ("tool_done", "tool_failed", TOOL_CANCELED):
                msg = _tool_result_message(ev, closed, results, emitted)
            elif ev.type == "tool_result":
                msg = _tool_fact_message(ev, results, emitted)
            else:
                msg = None
            if msg is not None:
                messages.append(msg)
        return messages

    def _pair_repair_reasons(self, events: Iterable[Event]) -> dict[str, str]:
        """从事实流算出每个缺结果调用的成因，供配对修补选文案。

        只根据已发生的事判定，不按工具名猜：
          · 有 `tool_ended` 且状态是 suspended → 挂起型（在等外部输入）；
          · 有 `tool_started` 但没有 `tool_ended` → 中断型（执行中丢了终态）；
          · 其余（事实流里毫无痕迹）不入表 → 修补层用中性文案。

        不点名具体工具：同样会挂起的不只 `user_confirm`，视觉授权等
        一处又一处，按事件判才能一次盖全。
        """
        started: set[str] = set()
        ended: set[str] = set()
        suspended: set[str] = set()
        for ev in events:
            call_id = str((ev.data or {}).get("call_id") or "")
            if not call_id:
                continue
            if ev.type == "tool_started":
                started.add(call_id)
            elif ev.type == TOOL_ENDED:
                ended.add(call_id)
                if str((ev.data or {}).get("status") or "") == TOOL_STATUS_SUSPENDED:
                    suspended.add(call_id)
        reasons: dict[str, str] = {}
        for call_id in suspended:
            reasons[call_id] = REPAIR_REASON_SUSPENDED
        for call_id in started - ended:
            reasons.setdefault(call_id, REPAIR_REASON_INTERRUPTED)
        return reasons

    def derive_messages(self) -> list[dict[str, Any]]:
        """从完整事实流投影模型可见消息序列（供请求组装使用）。"""
        return self._derive_messages(self.events)

    def derive_request_messages_from_latest_wake(self) -> list[dict[str, Any]] | None:
        """只投影最近一次唤醒起的事实；没有唤醒时返回 ``None``。

        空闲时的独立唤醒只看到本批唤醒输入和后续工具链。插入当前回合时保留上下文。
        返回 ``None`` 与空列表语义不同：前者表示沿用完整会话历史。
        """
        start = None
        for index in range(len(self.events) - 1, -1, -1):
            ev = self.events[index]
            if ev.type != "input_claimed":
                continue
            if str(ev.data.get("kind") or "") != "wake":
                return None
            start = index
            break
        if start is None:
            return None
        queued_wake = bool(self.events[start].data.get("_from_queue"))
        while start > 0:
            previous = self.events[start - 1]
            if previous.type != "input_claimed" or not previous.data.get("_from_queue"):
                break
            if previous.data.get("kind") != "wake":
                return None
            start -= 1
        if queued_wake and start > 0 and self.events[start - 1].type != TURN_STARTED:
            return None
        window = self.events[start:]
        return ensure_tool_pairs(self._derive_messages(window),
                                 reasons=self._pair_repair_reasons(window))

    def derive_request_messages(self) -> list[dict[str, Any]]:
        """构造模型请求用的消息序列：在 `derive_messages()` 之上补齐 tool 配对。

        与 `derive_messages()` 的分工：
          · `derive_messages()` 是日志的忠实折叠 —— 反映事实真相。悬空的
            `assistant(tool_calls)`（等用户确认中）就是悬空的，不修饰；
          · 本方法给真正要发出去的请求用 —— 那里必须满足模型 API 的硬约束。

        模型 API 对"要求了工具调用却没给响应"是硬拒绝的：

            `An assistant message with 'tool_calls' must be followed by tool messages
             responding to each 'tool_call_id'`

        同类错误在别处也真实发生过（400）。这种缺口一旦进了历史，
        此后每个请求都带着它 —— 会话彻底打不开。两条产生缺口的路径：

          ① 批量挂起：模型一条消息要求 [ask_user(c1), echo(c2)]，c1 挂起后
             c2 若被静默丢弃就留下缺口（`core/modules/` 的 deferred 分支必须补终态）；
          ② 挂起后用户改说话（或刷新页面后直接打字）：挂起调用的结果只能靠
             用户作答补上；用户不答而是继续说话时，序列就成了
             `user → assistant(tool_calls) → user`。这是自然的用户路径，
             服务端不拦（确认界面刷新后即消失，用户无从作答）。

        补说明性占位（而非拒绝请求）：
          · 拒绝会把用户卡死在一个他无法理解的错误上；
          · 补占位让模型看得见"这次调用没有结果"，自行决定重发或换方案；
          · 这也是唯一能让已经写出缺口的记录重新可用的办法。
        """
        return ensure_tool_pairs(
            self.derive_messages(), reasons=self._pair_repair_reasons(self.events))


#: 补齐配对时填入的结果文案。模型需要知道这次调用没拿到回执，
#: 而不是把调用记录悄悄抹掉 —— 抹掉会让它以为从没发过，于是重发一遍。
#:
#: 统一成一句会把「执行中被中断」说成「在等用户答」，
#: 所以按事实流能确定的成因分三档。
#:
#: 这三句是给模型看的，第三人称指用户，不用“你”—— 否则模型会以为需要它去确认。
#: 三句一律不加句号，保持同形，便于日后逐字改文案时不漏标点。
REPAIR_REASON_SUSPENDED = "suspended"
REPAIR_REASON_INTERRUPTED = "interrupted"

#: 挂起型：等的是用户，而不是模型自己。
_REPAIR_TEXT_SUSPENDED = "无结果：用户未作答"
#: 中断型：已经开始了，但没等到终态（进程退出、回合被强停等）。
_REPAIR_TEXT_INTERRUPTED = "无结果：工具调用异常中断"
#: 未知型：事实流里没有任何该调用的痕迹，不猜原因。
_REPAIR_TEXT_UNKNOWN = "无结果：该调用没有回执"


def _missing_result_text(reason: str) -> str:
    """按成因取补位文案；未识别的成因一律用中性文案，不猜。"""
    if reason == REPAIR_REASON_SUSPENDED:
        return _REPAIR_TEXT_SUSPENDED
    if reason == REPAIR_REASON_INTERRUPTED:
        return _REPAIR_TEXT_INTERRUPTED
    return _REPAIR_TEXT_UNKNOWN


def _missing_result_message(call_id: str, reason: str) -> dict[str, Any]:
    """缺结果的补位消息；文案按成因取，未知成因用中性话。"""
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": _tool_envelope(ok=False, error=_missing_result_text(reason)),
    }


def ensure_tool_pairs(
    messages: list[dict[str, Any]],
    *,
    reasons: Optional[Mapping[str, str]] = None,
) -> list[dict[str, Any]]:
    """Pair each call occurrence and put its result directly after its declaration.

    Keep real results, synthesize missing ones, and omit results without a preceding
    unmatched call. The request projection leaves the stored events intact.
    """
    known_reasons = reasons or {}
    pending = defaultdict(deque)
    calls_by_index = {}
    results_by_index = defaultdict(list)
    matched = set()
    adjacent = None

    for index, msg in enumerate(messages):
        role = msg.get("role")
        if role == "tool":
            call_id = str(msg.get("tool_call_id") or "")
            owners = pending.get(call_id)
            if owners:
                owner = owners.pop() if owners[-1][0] == adjacent else owners.popleft()
                matched.add(owner)
                results_by_index[owner[0]].append(msg)
            continue
        adjacent = None
        calls = msg.get("tool_calls")
        if role != "assistant" or not isinstance(calls, list):
            continue
        ids = [str(call["id"]) for call in calls if isinstance(call, dict) and call.get("id")]
        calls_by_index[index] = ids
        adjacent = index
        for slot, call_id in enumerate(ids):
            pending[call_id].append((index, slot))

    out = []
    for index, msg in enumerate(messages):
        if msg.get("role") == "tool":
            continue
        out.append(msg)
        for slot, call_id in enumerate(calls_by_index.get(index, ())):
            if (index, slot) not in matched:
                out.append(_missing_result_message(call_id, known_reasons.get(call_id, "")))
        out.extend(results_by_index.get(index, ()))
    return out
