# -*- coding: utf-8 -*-
"""会话记录：事实 append + 模型历史 derive。

纪律：模型可见 ⟺ 已记录 —— derive 只从已 append 的事实投影，
不维护第二份"仅供参考"的历史。
"""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterable

from agent.core.error_report import report_error
from agent.core.events import Event
from agent.core.model_call import PROVIDER_META_KEY


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
    # 一张合法附件都没有 → 回落纯文本（单文本段不包成数组）
    if not parts:
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

    def __len__(self) -> int:
        return len(self._log.events)

    def __iter__(self):
        return iter(self.events)

    def __repr__(self) -> str:            # pragma: no cover - 诊断用
        return f"<SessionLogView {len(self._log.events)} events>"



def _closed_tool_calls(events: Any) -> set[str]:
    closed: set[str] = set()
    for ev in events:
        if ev.type != "tool_ended" or str(ev.data.get("status") or "") == "suspended":
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
    return {"role": "user", "content": _user_content(content, attachments)}


def _model_message(ev: Event) -> dict[str, Any]:
    msg: dict[str, Any] = {
        "role": "assistant", "content": str(ev.data.get("content", ""))}
    reasoning = str(ev.data.get("reasoning_content") or "")
    if reasoning:
        msg["reasoning_content"] = reasoning
    calls = ev.data.get("tool_calls") or []
    if calls:
        msg["tool_calls"] = calls
    meta = ev.data.get(PROVIDER_META_KEY)
    if meta:
        msg[PROVIDER_META_KEY] = meta
    return msg


def _tool_ended_message(ev: Event, results: dict[str, dict[str, Any]],
                        emitted: set[str]) -> dict[str, Any] | None:
    if str(ev.data.get("status") or "") == "suspended":
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
    results[call_id] = {
        "ok": ev.type == "tool_done", "data": ev.data.get("data"),
        "error": ev.data.get("error"), "attachments": ev.data.get("attachments"),
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

    def derive_messages(self) -> list[dict[str, Any]]:
        """从事实投影出模型可见消息序列（供请求组装使用）。"""
        messages: list[dict[str, Any]] = []
        results: dict[str, dict[str, Any]] = {}
        emitted: set[str] = set()
        closed = _closed_tool_calls(self.events)
        for ev in self.events:
            if ev.type == "input_claimed":
                msg = _input_message(ev)
            elif ev.type == "model_message":
                msg = _model_message(ev)
            elif ev.type == "tool_ended":
                msg = _tool_ended_message(ev, results, emitted)
            elif ev.type in ("tool_done", "tool_failed"):
                msg = _tool_result_message(ev, closed, results, emitted)
            elif ev.type == "tool_result":
                msg = _tool_fact_message(ev, results, emitted)
            else:
                msg = None
            if msg is not None:
                messages.append(msg)
        return messages

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
        return ensure_tool_pairs(self.derive_messages())


def ensure_tool_pairs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """保证 `assistant(tool_calls)` 的每个 id 都有对应的 tool 消息。

    由 `SessionLog.derive_request_messages` 保证每个 id 都有 tool 消息。
    保持为独立的纯函数：便于单测，也避免把"日志折叠"与"请求修补"混在一起。
    """
    answered = {str(m.get("tool_call_id") or "") for m in messages
                if m.get("role") == "tool"}
    out: list[dict[str, Any]] = []
    for msg in messages:
        out.append(msg)
        if msg.get("role") != "assistant":
            continue
        calls = msg.get("tool_calls") or []
        if not calls:
            continue
        for raw in calls:
            call_id = str(raw.get("id") or "")
            if not call_id or call_id in answered:
                continue
            out.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": _tool_envelope(
                    ok=False,
                    error=(
                        "这次工具调用没有产生结果（等待用户确认期间回合结束，"
                        "或用户转而发了新消息）。请按需重新发起。"
                    ),
                ),
            })
            answered.add(call_id)
    return out
