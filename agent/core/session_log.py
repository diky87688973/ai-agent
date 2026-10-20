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
    # 超出时整轮请求被拒。
    from agent.core.image_embed import build_embed_parts, placeholder_text

    parts, skipped = build_embed_parts(attachments)
    # 一张合法附件都没有 → 回落纯文本（单文本段不包成数组）
    if not parts:
        return text
    if text:
        parts.insert(0, {"type": "text", "text": text})
    # 超预算的附件转占位文字，使模型知道有图未随请求发送。
    note = placeholder_text(skipped)
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


def _tool_envelope(*, ok: bool, data: Any = None, error: Any = None) -> str:
    """回灌模型的工具结果信封（成功/失败同形）。

    - 成功：`{"ok": true, "data": …}`
    - 失败：`{"ok": false, "error": "…"}`，可选附带 `data`
    """
    if ok:
        payload: dict[str, Any] = {"ok": True, "data": data}
    else:
        payload = {"ok": False, "error": str(error if error is not None else "")}
        if data is not None:
            payload["data"] = data
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
    if done is None:
        content = _tool_envelope(
            ok=False, error=f"工具 {name} 已结束，但未记录结果")
    elif bool(done.get("ok")):
        content = _tool_envelope(ok=True, data=done.get("data"))
    else:
        content = _tool_envelope(
            ok=False, error=done.get("error"), data=done.get("data"))
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
        # 工具结果事实（`tool_done` / `tool_failed`）按 `call_id` 攒起来：
        # 终态事实 `tool_ended` 只标"结束了"，结果取自这一份（下方 tool_ended 分支回查 `_tool_results`）。
        _tool_results: dict[str, dict[str, Any]] = {}
        # 非挂起的 tool_ended 负责把结果收成消息。只有结果事实、没有这种终态时
        # （取消确认只写下了 tool_failed），在结果事实处直接收成消息。
        _closed: set[str] = set()
        for ev in self.events:
            if ev.type != "tool_ended" or str(ev.data.get("status") or "") == "suspended":
                continue
            cid = str(ev.data.get("call_id") or "")
            if cid:
                _closed.add(cid)
        _emitted: set[str] = set()
        for ev in self.events:
            if ev.type == "input_claimed":
                content = str(ev.data.get("content", ""))
                attachments = ev.data.get("attachments")
                # 无输入 = 无用户消息：接口确认触发的恢复轮没有用户发言，
                # 上下文末端就该是那次工具调用——拼上结果后恰好是
                # `…assistant(tool_calls) → tool`（天然对齐）。
                # 若这里凭空造一条空的 user 消息，序列变成
                # `…assistant(tool_calls) → user("") → tool`，模型 API 直接拒绝（400）：
                #   `Messages with role 'tool' must be a response to a preceding message with 'tool_calls'`
                # 回合层已经不发这种事实，这里是第二道——
                # 已落盘的记录里可能还留着，重新加载时也必须能派生
                # 出合法序列，否则那段历史会永远打不开。
                if not content and not attachments:
                    continue
                messages.append({
                    "role": "user",
                    "content": _user_content(content, attachments),
                })
            elif ev.type == "model_message":
                msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": str(ev.data.get("content", "")),
                }
                reasoning_content = str(ev.data.get("reasoning_content") or "")
                if reasoning_content:
                    msg["reasoning_content"] = reasoning_content
                tool_calls = ev.data.get("tool_calls") or []
                if tool_calls:
                    msg["tool_calls"] = tool_calls
                provider_meta = ev.data.get(PROVIDER_META_KEY)
                if provider_meta:
                    # 厂商私有元数据（例如 thinking 块与签名）原样透传：
                    # 内核不解释内容，适配器在回放时自行决定要不要用（B6 可选新增键）。
                    msg[PROVIDER_META_KEY] = provider_meta
                messages.append(msg)
            elif ev.type == "tool_ended":
                # 工具终态事实：`tool_ended{status, elapsed_ms}`。
                #
                # ⚠️ `tool_ended` 不带结果数据——它只标"这次调用结束了"。
                # 结果在同一次调用先发的 `tool_done{data}` / `tool_failed{error}` 里，
                # 所以这里必须回查那一份。
                # 判据：直接读 `tool_ended.data` 会让每条 tool 消息都是 `null`，
                # 模型看到的全是空，于是它如实报告"所有工具都返回 null"。
                status = str(ev.data.get("status") or "")
                if status == "suspended":
                    # 等外部输入：这次调用还没返回，交给模型就等于说"答完了"——
                    # 会产生两条 tool 消息，模型 API 直接拒绝（400）。
                    continue
                call_id = str(ev.data.get("call_id", ""))
                if call_id in _emitted:
                    continue
                done = _tool_results.get(call_id)      # 结果事实（done / failed）
                messages.append(_render_tool_message(
                    call_id, done, str(ev.data.get("name") or "")))
                _emitted.add(call_id)
            elif ev.type in ("tool_done", "tool_failed"):
                # 结果事实先攒着。后面有非挂起的终态时，由那条终态收成 tool 消息。
                # 没有这种终态时就在这里收成消息，否则取消只留在事实里，模型看不见。
                call_id = str(ev.data.get("call_id", ""))
                if call_id:
                    _tool_results[call_id] = {
                        "ok": ev.type == "tool_done",
                        "data": ev.data.get("data"),
                        "error": ev.data.get("error"),
                        # 工具附带的图片：只在派生对话时取用，不写入事件流。
                        "attachments": ev.data.get("attachments"),
                    }
                    if call_id not in _closed and call_id not in _emitted:
                        messages.append(_render_tool_message(call_id, _tool_results[call_id]))
                        _emitted.add(call_id)
            elif ev.type == "tool_result":
                # 落盘记录里"用户作答"的结果事实名（另一种结果事实格式）。
                #
                # 必须认这一条：把"用户作答"写成 `tool_result`（而不是
                # `tool_done` / `tool_failed`）是另一种结果事实格式，不认它则那次调用
                # 没有结果 —— 请求层只能补一句"这次工具调用没有产生结果"的占位，
                # 用户的选择（例如点了「确认写入」）在模型眼里就成了一句无结果的调用。
                #
                # 只在这里追加一条：`tool_ended` 对 `suspended` 状态不产出消息
                # （那时确实还没答），所以不会重复；反过来若同一 `call_id` 已经有了
                # 结果事实（`tool_done` / `tool_failed`），说明是新格式，
                # 由 `tool_ended` 统一产出 —— 这里必须让位，否则同一调用出现两条
                # `tool` 消息，模型 API 直接拒绝（400）。
                call_id = str(ev.data.get("call_id", ""))
                if not call_id or call_id in _tool_results:
                    continue
                # 「等用户作答」的中间结果：记下它（这样后到的真结果能替换掉），
                # 但不产出消息 —— 它按定义是"还没返回"，交给模型就等于说
                # "这次调用已经答完了"。
                if ev.data.get("await_user"):
                    _tool_results[call_id] = {"ok": True, "data": None, "error": ""}
                    continue
                if bool(ev.data.get("ok")):
                    content = _tool_envelope(ok=True, data=ev.data.get("data"))
                else:
                    content = _tool_envelope(
                        ok=False,
                        error=ev.data.get("error"),
                        data=ev.data.get("data"),
                    )
                _tool_results[call_id] = {
                    "ok": bool(ev.data.get("ok")),
                    "data": ev.data.get("data"),
                    "error": ev.data.get("error"),
                }
                messages.append(
                    {"role": "tool", "tool_call_id": call_id, "content": content}
                )
                _emitted.add(call_id)
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
             c2 若被静默丢弃就留下缺口（`core/modules.py` 的 deferred 分支必须补终态）；
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
