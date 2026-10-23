# -*- coding: utf-8 -*-
"""出站适配的回合与模型事件族：回合边界、LLM 卡片、用量与上下文布局。

经典界面靠这些帧起步骤卡、收尾回合、刷新底部分段条。
"""
from __future__ import annotations

from typing import Any, Dict, List

import agent.shell.classic_adapter.contract as C


class TurnFrames:
    """回合与模型事件的翻译（挂在 `ClassicStream` 上）。"""

    def _on_turn_started(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        self.run_id = str(d.get("run_id") or "")
        self.round = 0
        self.pending.clear()
        self.paused = False
        self._awaiting_confirm = False
        out: List[Dict[str, Any]] = []
        # `conversation` 是必需事件：经典界面靠它建立该会话的上下文
        # （`ensureConversationTab` + 同步模式/模型），并由
        # `withConversationContext` 设置 `renderingContextVisible`——
        # 没有它，后续 `usage` / `context_layout` 的渲染守卫不过，底栏永远不更新。
        # 内核的 `turn_started` 不带 mode/model，所以用注入的解析器现场取。
        # 不带 `model`：模型不由服务端推送。
        # 若每轮都推一次，前端会照单接收并覆盖 `selectedModel` ⇒
        # "发一条消息，模型下拉自己跳回默认"。
        # 规则：首次打开页面拉一次当前模型，此后一律以发送消息那一刻
        # 前端带来的 `model` 为准 —— 服务端不反向覆盖用户当场的选择。
        out.append(self._ev(C.EV_CONVERSATION, mode=self._resolve_mode()))
        out.append(self._ev(C.EV_RUN_STARTED, run_id=self.run_id))
        mode = d.get("mode")
        if mode:
            out.append(self._ev(C.EV_MODE_CHANGED, mode=C.normalize_mode(mode)))
        return out

    def _resolve_mode(self) -> str:
        """当前会话模式：由 adapter 注入的解析器取。"""
        if self.mode_resolver is None:
            return "auto"
        return C.normalize_mode(self.mode_resolver(self.cid))

    def _resolve_model(self) -> str:
        if self.model_resolver is None:
            return ""
        return str(self.model_resolver(self.cid) or "")

    def _on_queue_updated(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [self._ev(
            C.EV_QUEUE_UPDATED,
            revision=int(d.get("revision") or 0),
            items=list(d.get("items") or []),
        )]

    def _on_input_claimed(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        # 经典界面乐观渲染用户气泡（agent-ui.js:2053），这里再发一次会重复。
        # 所以只回一个空的确认帧，供适配层更新自身状态。
        #
        # 例外：别的会话投进来的消息（`_sender` 非空）不是用户自己打的，
        # 前端没有乐观渲染它 —— 不回帧的话它在实时视图里完全看不见，
        # 只有刷新后才冒出来（而且会被当成用户自己说的话）。
        sender = str(d.get("_sender") or "").strip()
        if sender:
            return [self._ev(
                C.EV_PEER_MESSAGE,
                content=str(d.get("content") or ""),
                sender=sender,
                sender_name=str(d.get("_sender_name") or ""),
            )]
        if bool(d.get("_from_queue")):
            return [self._ev(
                C.EV_QUEUED_USER,
                content=str(d.get("content") or ""),
                attachments=list(d.get("attachments") or []),
            )]
        return []

    def _on_step_started(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """新的 LLM 轮：经典界面以 `llm_round` 起卡，`reasoning_*` / `llm_request` 都依赖它。"""
        return self._begin_llm_round(d)

    def _on_llm_call_start(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """历史事实名 `llm_call_start`：保留以兼容以该名落盘的历史记录。"""
        return self._begin_llm_round({
            "model": d.get("model"),
            "reasoning_effort": d.get("effort"),
            "messages_count": d.get("messages"),
            "tools_count": d.get("tools"),
        })

    def _on_llm_started(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """同一含义的当前事实：模型模块在真正发起调用前发的 `llm_started`。

        经典界面的步骤卡由 `llm_round` 起卡，而内核不发"步"
        （"趟"是宿主的实现细节）——只认"步开始"的话，步骤面板彻底空。

        这里让适配层吸收两种词汇：历史记录用"步开始"、当前用"模型调用开始"，
        对经典界面是同一件事——新一轮要起卡了。

        顺带把 `llm_request.params` 用真实携带的信息填满
        （`model` / `messages` / `tools` 取自当轮实况）。
        """
        return self._begin_llm_round({
            "model": d.get("model"),
            "reasoning_effort": d.get("effort"),
            "messages_count": d.get("messages"),
            "tools_count": d.get("tools"),
        })

    def _begin_llm_round(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """起一张步骤卡：`llm_round` + `llm_request`，并置位"本步发过 llm"。

        `self._step_had_llm` 在这里置位——`reasoning_delta` / `llm_response` /
        `llm_done` 都以它为守卫（没有前置 `llm_round`，经典界面会把那些帧丢掉）。
        """
        self.round += 1
        self._step_had_llm = True
        self._tools_in_step = 0
        return [
            self._ev(C.EV_LLM_ROUND, round=self.round),
            self._ev(C.EV_LLM_REQUEST, round=self.round, params=self._request_params(d)),
        ]

    def _request_params(self, d: Dict[str, Any]) -> Dict[str, Any]:
        """`llm_request.params` 快照（经典界面把它 JSON 化后显示在"请求"折叠区）。

        内核没有该事件，这里按当轮实况组；拿不到的字段给 None——
        经典界面只是 `JSON.stringify`，显示 null 比显示假数字诚实。

        `model` 不能为空：请求快照要写出这一轮用的模型名，空串就回落注入的模型名。
        """
        return {
            "round": self.round,
            "model": d.get("model") or self._resolve_model(),
            "thinking": True,
            "reasoning_effort": d.get("reasoning_effort") or "",
            "temperature": d.get("temperature"),
            "messagesCount": d.get("messages_count"),
            "toolsCount": d.get("tools_count"),
            "hasTools": bool(d.get("tools_count")),
        }

    def _on_reasoning_delta(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        text = str(d.get("text") or "")
        if not text or not self._step_had_llm:
            return []          # 没有前置 llm_round，经典界面会丢弃
        return [self._ev(C.EV_REASONING_DELTA, delta=text, round=self.round)]

    def _on_assistant_delta(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        text = str(d.get("text") or "")
        if not text:
            return []
        return [self._ev(C.EV_ASSISTANT_DELTA, delta=text)]

    def _on_model_message(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """本步收束：补 `llm_response` + `llm_done`，并给最终正文。

        经典界面的 `assistant` 只在有正文时才应发；工具调用轮没有正文，
        发空串会让它渲染一个空气泡。
        """
        out: List[Dict[str, Any]] = []
        if self._step_had_llm:
            content = str(d.get("content") or "")
            reasoning = str(d.get("reasoning_content") or "")
            out.append(self._ev(
                C.EV_LLM_RESPONSE,
                round=self.round,
                params={
                    "round": self.round,
                    "toolCallsCount": len(d.get("tool_calls") or []),
                    "contentChars": len(content),
                    "reasoningChars": len(reasoning),
                },
            ))
            out.append(self._ev(C.EV_LLM_DONE))
            self._step_had_llm = False
            # 正在等用户作答时不发 `assistant`：暂停那一轮通常没有正文，
            # 而经典界面的 `assistant` 分支是 `if(!finalizeAssistantStream(c)){add("a", c||"");}`——
            # 没有流式气泡时它会 `add("a","")`，渲染出一个空气泡。
            # 那一轮的可见产出是确认模态，不是对话区里的文字。
            if content and not self._awaiting_confirm:
                out.append(self._ev(C.EV_ASSISTANT, content=content))
        # 上下文分段条：每步发一次。
        #
        # 不能只挂在 `context_compacted` 上——那条分支要求"真的发生了压缩"，
        # 而短会话永远不触发压缩 → 右栏上下文条恒为「—」。
        # `context_layout` 由事件的消费方计算（这里算）；
        # 算不出来就不发这一帧。
        out += self._emit_layout()
        return out

    def _on_usage(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """用量：必须嵌套在 `usage` 键下。

        经典界面读的是 `ev.usage.prompt_tokens`（agent-ui.js:156），不是平铺字段。
        字段名用 SSE 那套（与 `/api/usage-accumulator` 的 `total_*` 不同，不可复用）。
        """
        payload = {k: d.get(k) for k in C.SSE_USAGE_FIELDS if d.get(k) is not None}
        if not payload:
            return []
        return [self._ev(C.EV_USAGE, usage=payload)]

    def _on_context_layout(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """分段快照原样转发。

        段里的字段（key / label / tokens / count / pct）由装配方定，适配层不逐个
        列举：漏一个字段只会在这条路径上少（兜底路径 `layout_from_messages` 是全的），
        界面上表现为"同一个东西两条路径长得不一样"，极难查。
        """
        return [self._ev(C.EV_CONTEXT_LAYOUT, **dict(d or {}))]

    def _on_error(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        # 记下"本回合已经报过错"：`turn_ended` 收尾时若 `halted` 为真还会想补一帧
        # `error{where:"turn"}`，那会与这里的 `error{where:"model"}` 重复 ——
        # 同一个失败会产生两帧 error，用户看到两行错误。
        self._error_sent = True
        return [self._ev(C.EV_ERROR,
                         message=str(d.get("detail") or d.get("where") or "未知错误"))]

    def _on_turn_ended(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """回合结束。暂停（等用户作答）与正常结束都发 `done`，但暂停多一帧信令。

        暂停同样发 `done`：SSE 的生命周期要完整（客户端总能看到收尾），
        而"这不是正常收尾"由 `paused_for_user_confirm` 表达——
        经典界面收到它就把本轮标记为"待用户确认"，随后 `done` 会短路收尾
        （`if(endedAwaitingUserConfirm){hideChatLoading();return;}`：
        不提升思考、不刷新标题）。
        内核不阻塞、不等待；暂停 = 回合结束 + 信令；恢复由用户操作触发。
        """
        paused = bool(d.get("paused"))
        stopped = bool(d.get("stopped"))
        out: List[Dict[str, Any]] = []
        if self._step_had_llm:                 # 收尾步没收到 model_message 时兜底
            out.append(self._ev(C.EV_LLM_DONE))
            self._step_had_llm = False
        if paused:
            out.append(self._ev(C.EV_PAUSED_FOR_CONFIRM))
        if stopped:
            # 用户主动停止 → 经典界面的 `stopped`：它收到后会 `markCurrentTurnStoped()`
            # （把所有还开着的工具卡与当前 LLM 卡拉成 `Stoped`、复位回合状态、
            # 隐藏"思考中"）。
            # 前端本身也会在点停止时乐观地先标一遍；这里这一帧是让后端也确认
            # 收尾，两者一致。
            # 不带文案：点停止时前端已经本地加了一条「任务已停止。」，
            # 再带 `message` 会让前端 `if(ev.message)add(...)` 又加一条（用户看到两行）。
            # 这一帧只负责信号（标记回合停止、复位状态、清服务端标记）。
            out.append(self._ev(C.EV_STOPPED))
        # `halted` 也要让观察面看得见：模型调用失败、护栏触顶（max_passes）等
        # 都走 `halted`；若适配层丢掉这个字段，那些情况在 UI 上就会
        # 和"正常完成"完全一样（`done{ok:true}`）——失败被静默伪装成成功。
        halted = bool(d.get("halted")) or bool(d.get("interrupted"))
        detail = str(d.get("detail") or "")
        if halted and detail and not self._error_sent:
            # 必须同时给 `message`：经典界面的 error 分支是
            # `add("a", "错误: " + (ev.message || JSON.stringify(ev)))`
            # （`agent-ui.js:175`）—— 只给 `where`/`detail` 时它走
            # `JSON.stringify(ev)`，用户看到的是原始 JSON：
            # `错误: {"type":"error","where":"turn","detail":"模型调用失败：…"}`
            # `_on_error` 同样给 `message`。
            out.append(self._ev(C.EV_ERROR, message=detail,
                                where="turn", detail=detail))
        out.append(self._ev(C.EV_DONE, ok=not (stopped or halted)))
        self._error_sent = False   # 回合收尾，下一回合重新计
        # 回合收尾再发一次布局：此时本趟事实已落盘，那趟的上下文条
        # 才不是「—」（布局由 `_emit_layout` 计算并发出）。
        out += self._emit_layout()
        self.pending.clear()
        self.paused = paused
        return out

    def _on_context_compacted(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """压缩事实 → 补一帧 `context_layout`（经典界面靠它画底部分段条）。

        经典界面没有"压缩"这个事件，但压缩后上下文变了，分段条必须跟着变。

        内核不产出 `context_layout` 事实，且压缩器的
        report 里没有 `layout` 键，所以这条分支永不命中 ——
        右栏上下文条恒为「—」。因此 `context_layout` 由事件的消费方计算
        （这里），内核不必为此新增事实。算不出来就不发。
        """
        layout = d.get("layout")
        if isinstance(layout, dict):
            return self._on_context_layout(layout)
        return self._emit_layout()

    def _emit_layout(self) -> List[Dict[str, Any]]:
        """算并发出 `context_layout`；算不出来返回空列表。

        两处调用（每步的 `model_message`、回合收尾的 `turn_ended`）都要它，
        所以抽出来。回合收尾同样发一次：布局是从已落盘的事实算的
        （`inbound.compute_context_layout`），而事实按趟增量落盘 —— 一趟开始算布局时
        本趟事实还没落盘，于是那一趟的上下文条一直是「—」，
        直到刷新（走 `history()`）或下一趟才出现。收尾时事实已经写下，这时补一帧就补齐了。
        """
        computed = self.layout_resolver() if self.layout_resolver is not None else None
        if isinstance(computed, dict):
            return self._on_context_layout(computed)
        return []
