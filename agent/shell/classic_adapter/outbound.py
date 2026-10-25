# -*- coding: utf-8 -*-
"""出站适配：内核事件 → 经典 UI 认得的事件（服务端 → 前端）。

一个会话一条 `ClassicStream`。它做两件事：
  ① 翻译：内核的 `tool_call` / `tool_result` / `step_started` / … 变成经典界面读的
     `tool_start` / `tool_end` / `llm_round` / …（字段名完全对齐，见 contract.py）；
  ② 补事件：经典界面依赖一些内核没有的事件（`llm_request` / `llm_response` /
     `llm_done` / `mode_changed` / `heartbeat`），由这里按上下文合成。

三条硬约束：
  - 每帧必须带合法 `conversation_id`（`heartbeat` / `global_sse_ready` / `plugins_changed` 除外）；
  - `tool_call_id` 是 tool_start/tool_end 的唯一配对键，原样透传内核的 `call_id`；
  - `reasoning_delta` 跟在 `llm_round` 之后、且 `round` 相等，否则经典界面丢弃。

逐事件翻译按事实族拆开：工具卡在 `outbound_tools.ToolFrames`，回合与模型卡片在
`outbound_turns.TurnFrames`；`ClassicStream` 只留按会话的状态与事件分派。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import agent.shell.classic_adapter.contract as C
from agent.shell.classic_adapter.outbound_tools import PendingToolCall, ToolFrames
from agent.shell.classic_adapter.outbound_turns import TurnFrames


class ClassicStream(ToolFrames, TurnFrames):
    """把一个会话的内核事件翻成经典界面事件序列。

    有状态但只读内核：状态全部是"经典界面需要而内核没提供"的派生量
    （当前轮次号、待配对工具、本步 LLM 卡片信息）。
    """

    def __init__(
        self,
        conversation_id: str,
        *,
        mode_resolver: Optional[Any] = None,
        model_resolver: Optional[Any] = None,
        layout_resolver: Optional[Any] = None,
    ) -> None:
        self.cid = C.normalize_cid(conversation_id)
        self.round = 0
        self.pending: Dict[str, PendingToolCall] = {}
        #: 本回合是否已经发过 `error` 帧（防 `turn_ended` 收尾时重复报错）。
        self._error_sent = False
        self.run_id = ""
        # 内核事件不带 mode/model，但经典界面的 `conversation` 事件必须有它们。
        # 用注入的解析器现场取（adapter 从 live_state / provider 拿）。
        self.mode_resolver = mode_resolver
        self.model_resolver = model_resolver
        #: 上下文分段快照的计算者（装配方注入）。内核不产出 `context_layout`
        #: 事实，按分工由消费方（`_on_context_compacted`）计算。
        self.layout_resolver = layout_resolver
        self._step_had_llm = False   # 本步是否发过 llm_round（决定要不要补 llm_done）
        self._tools_in_step = 0
        # 这一次 translate 调用对应的存储坐标（落盘旁路标的 `_seq`）。
        # 每个事件翻译前重新设定、翻完即清，绝不跨事件沿用。
        #
        # 不能做成"最近一帧的坐标"那种实例字段：本对象按会话缓存
        # （`adapter._streams`），一旦某次回放把历史坐标写进实例，之后所有实时帧
        # 都会被盖上那个过期坐标 —— 客户端拿旧坐标重连又收到那批帧，
        # assistant 正文被重复渲染（对话区多一个气泡），且游标永久失效。
        self._frame_seq: Optional[int] = None
        # 本轮是否停在"等用户作答"（由 `turn_ended.paused` 置位）。
        # 它是宿主状态：恢复靠用户操作触发新回合，内核不等待、不阻塞。
        self.paused = False
        # 本轮是否已发出待确认信封（决定要不要抑制收尾的空正文气泡）。
        self._awaiting_confirm = False

    def _ev(self, type_: str, **data: Any) -> Dict[str, Any]:
        """组一帧；除豁免事件外一律带上校验过的 conversation_id。

        带 `seq` 时额外给出 `id` 字段——`ClassicSseChannel` 用它发 SSE 的 `id:` 行，
        浏览器重连时经 `Last-Event-ID` 带回，适配层就能从该位置续传。
        """
        frame: Dict[str, Any] = {"type": type_, **data}
        if type_ not in C.CID_EXEMPT_EVENTS:
            frame["conversation_id"] = self.cid
        if self._frame_seq is not None:
            frame["seq"] = self._frame_seq
        return frame

    # ── 内核事件入口 ──────────────────────────────────────

    def translate(self, ev_type: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """一个内核事件 → 零到多帧老事件（按顺序）。"""
        payload = dict(data or {})
        # 存储坐标（落盘旁路标的 `_seq`）：本事件翻出的所有帧共用它。
        # 实时事件没有 `_seq` → 明确置 `None`，不沿用上一次的（那正是"粘滞"的来源）。
        raw_seq = payload.pop("_seq", None)
        self._frame_seq = (raw_seq
                           if isinstance(raw_seq, int)
                           and not isinstance(raw_seq, bool) and raw_seq >= 0
                           else None)
        handler = getattr(self, "_on_" + ev_type, None)
        if handler is None:
            self._frame_seq = None
            return []
        try:
            return list(handler(payload))
        finally:
            self._frame_seq = None      # 翻完即清，绝不留给下一个事件
