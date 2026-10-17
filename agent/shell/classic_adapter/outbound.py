# -*- coding: utf-8 -*-
"""出站适配：内核事件 → 经典 UI 认得的事件（服务端 → 前端）。

一个会话一条 `ClassicStream`。它做两件事：
  ① **翻译**：内核的 `tool_call` / `tool_result` / `step_started` / … 变成经典界面读的
     `tool_start` / `tool_end` / `llm_round` / …（字段名完全对齐，见 contract.py）；
  ② **补事件**：经典界面依赖一些内核没有的事件（`llm_request` / `llm_response` /
     `llm_done` / `mode_changed` / `heartbeat`），由这里按上下文合成。

三条硬约束：
  - 每帧必须带合法 `conversation_id`（`heartbeat` / `global_sse_ready` / `plugins_changed` 除外）；
  - `tool_call_id` 是 tool_start/tool_end 的唯一配对键，原样透传内核的 `call_id`；
  - `reasoning_delta` 跟在 `llm_round` 之后、且 `round` 相等，否则经典界面丢弃。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agent.shell.classic_adapter import contract as C


@dataclass
class _Pending:
    """一次工具调用的进站记录（供 tool_end 组装 preview 用）。"""

    tool_call_id: str
    script: str
    args: Dict[str, Any] = field(default_factory=dict)


class ClassicStream:
    """把一个会话的内核事件翻成经典界面事件序列。

    有状态但**只读内核**：状态全部是"经典界面需要而内核没提供"的派生量
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
        self.pending: Dict[str, _Pending] = {}
        #: 本回合是否已经发过 `error` 帧（防 `turn_ended` 收尾时重复报错）。
        self._error_sent = False
        self.run_id = ""
        # 内核事件不带 mode/model，但经典界面的 `conversation` 事件必须有它们。
        # 用注入的解析器现场取（adapter 从 live_state / provider 拿）。
        self.mode_resolver = mode_resolver
        self.model_resolver = model_resolver
        #: 上下文分段快照的**计算者**（装配方注入）。内核不产出 `context_layout`
        #: 事实，按分工由消费方（`_on_context_compacted`）计算。
        self.layout_resolver = layout_resolver
        self._step_had_llm = False   # 本步是否发过 llm_round（决定要不要补 llm_done）
        self._tools_in_step = 0
        # **这一次 translate 调用**对应的存储坐标（落盘旁路标的 `_seq`）。
        # 每个事件翻译前**重新设定、翻完即清**，绝不跨事件沿用。
        #
        # 不能做成"最近一帧的坐标"那种实例字段：本对象**按会话缓存**
        # （`adapter._streams`），一旦某次**回放**把历史坐标写进实例，之后所有实时帧
        # 都会被盖上那个**过期**坐标 —— 客户端拿旧坐标重连**又收到那批帧**，
        # assistant 正文被重复渲染（对话区多一个气泡），且游标永久失效。
        self._frame_seq: Optional[int] = None
        # 本轮是否停在"等用户作答"（由 `turn_ended.paused` 置位）。
        # 它是**宿主状态**：恢复靠用户操作触发新回合，内核不等待、不阻塞。
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
        # 存储坐标（落盘旁路标的 `_seq`）：**本事件**翻出的所有帧共用它。
        # 实时事件没有 `_seq` → 明确置 `None`，**不沿用上一次的**（那正是"粘滞"的来源）。
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

    # ── 逐事件翻译 ────────────────────────────────────────

    def _on_turn_started(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        self.run_id = str(d.get("run_id") or "")
        self.round = 0
        self.pending.clear()
        self.paused = False
        self._awaiting_confirm = False
        out: List[Dict[str, Any]] = []
        # `conversation` 是**必需**事件：经典界面靠它建立该会话的上下文
        # （`ensureConversationTab` + 同步模式/模型），并由
        # `withConversationContext` 设置 `renderingContextVisible`——
        # 没有它，后续 `usage` / `context_layout` 的渲染守卫不过，底栏永远不更新。
        # 内核的 `turn_started` 不带 mode/model，所以用注入的解析器现场取。
        # **不带 `model`**：模型不由服务端推送。
        # 若每轮都推一次，前端会照单接收并覆盖 `selectedModel` ⇒
        # "发一条消息，模型下拉自己跳回默认"。
        # 规则：**首次打开页面拉一次当前模型**，此后一律以**发送消息那一刻**
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

    def _on_input_claimed(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        # 经典界面**乐观渲染**用户气泡（agent-ui.js:2053），这里再发一次会重复。
        # 所以只回一个空的确认帧，供适配层更新自身状态。
        #
        # 例外：**别的会话投进来的消息**（`_sender` 非空）不是用户自己打的，
        # 前端没有乐观渲染它 —— 不回帧的话它在实时视图里**完全看不见**，
        # 只有刷新后才冒出来（而且会被当成用户自己说的话）。
        sender = str(d.get("_sender") or "").strip()
        if not sender:
            return []
        return [self._ev(
            C.EV_PEER_MESSAGE,
            content=str(d.get("content") or ""),
            sender=sender,
            sender_name=str(d.get("_sender_name") or ""),
        )]

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

        经典界面的步骤卡由 `llm_round` 起卡，而内核**不发"步"**
        （"趟"是宿主的实现细节）——只认"步开始"的话，**步骤面板彻底空**。

        这里让适配层吸收两种词汇：历史记录用"步开始"、当前用"模型调用开始"，
        对经典界面是同一件事——**新一轮要起卡了**。

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

        **`model` 不能为空**：请求快照要写出这一轮用的模型名，空串就回落注入的模型名。
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

        经典界面的 `assistant` 只在**有正文**时才应发；工具调用轮没有正文，
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
            # 正在等用户作答时**不发** `assistant`：暂停那一轮通常没有正文，
            # 而经典界面的 `assistant` 分支是 `if(!finalizeAssistantStream(c)){add("a", c||"");}`——
            # 没有流式气泡时它会 `add("a","")`，渲染出一个**空气泡**。
            # 那一轮的可见产出是确认模态，不是对话区里的文字。
            if content and not self._awaiting_confirm:
                out.append(self._ev(C.EV_ASSISTANT, content=content))
        # 上下文分段条：**每步发一次**。
        #
        # 不能只挂在 `context_compacted` 上——那条分支要求"真的发生了压缩"，
        # 而短会话永远不触发压缩 → **右栏上下文条恒为「—」**。
        # `context_layout` 由**事件的消费方**计算（这里算）；
        # 算不出来就不发这一帧。
        out += self._emit_layout()
        return out

    def _on_tool_call(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        call_id = str(d.get("call_id") or "")
        if not call_id:
            return []          # 没有 id 就配不上 tool_end，不如不发
        name = str(d.get("name") or "")
        args = d.get("arguments") if isinstance(d.get("arguments"), dict) else {}
        script = C.tool_script(name)
        self.pending[call_id] = _Pending(call_id, script, dict(args))
        self._tools_in_step += 1
        # 待确认卡由内核事实 `turn_awaiting_user` 转成：
        # `turn_awaiting_user`（带 `call_id`/标题/选项），由 `_on_turn_awaiting_user`
        # 转成卡片。那样选项以**工具声明**的为准，不比这里的模型原始入参更差。
        return [self._ev(C.EV_TOOL_START, tool_call_id=call_id, script=script, args=dict(args))]

    def _on_tool_progress(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        call_id = str(d.get("call_id") or "")
        text = str(d.get("text") or "")
        if not call_id or not text:
            return []
        frame = self._ev(
            C.EV_TOOL_PROGRESS,
            tool_call_id=call_id,
            stream=str(d.get("stream") or "stdout"),
            text=text,
            done=bool(d.get("done")),
        )
        # 命令在问人（winget / npm init 之类）时把提示透传给经典界面：
        # 它据此在工具卡里挂一条输入条（对照经典界面的 `renderRunCommandInputBar`）。
        awaiting = d.get("awaiting_input")
        if isinstance(awaiting, dict) and awaiting:
            frame["awaiting_input"] = awaiting
        return [frame]

    def _on_tool_suspended(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """工具声明"需要外部输入" → 经典界面的**待确认卡**（当前事实名）。

        与 `_on_turn_awaiting_user` 是同一件事的两种事实名：
        - `turn_awaiting_user`：回合级暂停事实，载荷扁平带 title/confirms；
        - `tool_suspended`：**工具级**挂起事实，选项在 `envelope` 里（当前）；

        适配层两个都认，吸收词汇差异。

        卡片挂在专用事实上：按两段式设计，首段**不产生**结果事实
        （那次调用还没返回），所以没有结果事件可以挂载。
        """
        call_id = str(d.get("call_id") or "")
        if not call_id:
            return []
        envelope = d.get("envelope") if isinstance(d.get("envelope"), dict) else {}
        if str(envelope.get("kind") or "") == "approval":
            # 审批帧带描述，按钮是同意和驳回，不带选项列表。
            desc = str(envelope.get("option_desc") or "").strip()
            self._awaiting_confirm = True
            self.pending.pop(call_id, None)
            return [self._ev(
                C.EV_TOOL_END,
                tool_call_id=call_id,
                ok=True,
                preview="",
                approval_required=True,
                approval_title="审批",
                approval_desc=desc,
            )]
        title = str(envelope.get("title") or "").strip()
        confirms = envelope.get("confirms")
        if not title or not isinstance(confirms, list) or not confirms:
            # 工具没给可渲染的选项（例如它要自由文本）：仍弹卡片，只留自定义输入
            title = title or f"{d.get('name') or '工具'}需要你的输入"
            confirms = []
        self._awaiting_confirm = True
        # 待确认卡已发：把这张卡从 `pending` 摘掉。内核紧接着还会发
        # `tool_ended{status:"suspended"}`，那会走 `_on_tool_ended` 的兜底分支
        # **再收一次同一张卡** —— 契约上就是重复帧：
        # 任何按 id 幂等渲染的客户端都会翻车。
        # 摘除动作在 return 之前执行。
        self.pending.pop(call_id, None)
        return [self._ev(
            C.EV_TOOL_END,
            tool_call_id=call_id,
            ok=True,                 # 停下来等用户是协议的一环
            preview="",
            user_confirm_required=True,
            user_confirm_title=title,
            user_confirm_options=[str(x) for x in confirms],
            user_confirm_multi=bool(envelope.get("multi")),
        )]

    def _on_turn_awaiting_user(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """回合停在"等用户作答" → 把内核事实变成经典界面的**待确认卡**。

        卡片挂在专用事实上的原因：按两段式设计，首段**不产生**结果事实
        （那次调用还没返回），所以没有结果事件可以挂载。内核为此产出这条专用事实，
        携带 `call_id` / `title` / `confirms`，选项以**工具声明**的为准
        （选项以**工具声明**的为准）。

        经典界面的卡片靠 `tool_end` 上的 `user_confirm_required` 渲染，所以这里发一个
        `tool_end`：卡片就是这次调用的界面呈现，而这次调用确实"停在了等人这一步"。

        发完同样把它从 `pending` 摘掉：
        否则内核随后补的终态会再收一次同一张卡，产生重复帧。
        """
        call_id = str(d.get("call_id") or "")
        title = str(d.get("title") or "").strip()
        confirms = d.get("confirms")
        if not call_id or not title or not isinstance(confirms, list) or not confirms:
            return []
        self._awaiting_confirm = True
        # 与 `_on_tool_suspended` 同理：摘掉，避免随后的终态事实重复收卡。
        # **必须在 `return` 之前**。
        self.pending.pop(call_id, None)
        return [self._ev(
            C.EV_TOOL_END,
            tool_call_id=call_id,
            ok=True,                 # 停下来等用户是协议的一环
            preview="",
            user_confirm_required=True,
            user_confirm_title=title,
            user_confirm_options=[str(x) for x in confirms],
            user_confirm_multi=bool(d.get("multi")),
        )]

    def _on_tool_started(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """**工具开始调用**：起工具卡，标签「进行中」。

        监听者也可以在这里起 RT、修剪参数——事件本身带 `arguments`。
        """
        call_id = str(d.get("call_id") or "")
        if not call_id:
            return []
        name = str(d.get("name") or "")
        args = d.get("arguments") if isinstance(d.get("arguments"), dict) else {}
        script = C.tool_script(name)
        self.pending[call_id] = _Pending(call_id, script, dict(args))
        self._tools_in_step += 1
        return [self._ev(C.EV_TOOL_START, tool_call_id=call_id, script=script,
                         args=dict(args))]

    def _on_tool_done(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """工具**成功完成** → 卡片标签绿色 `Done`。"""
        return self._finish_tool(d, ok=True)

    def _on_tool_failed(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """工具**失败** → 卡片标签红色 `Fail`。"""
        return self._finish_tool(d, ok=False)

    def _on_tool_canceled(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """工具**被取消** → 卡片标签 `Stoped`（预留：取消能力尚未接线，先让映射就位）。"""
        call_id = str(d.get("call_id") or "")
        pend = self.pending.pop(call_id, None)
        if pend is None:
            return []
        return [self._ev(C.EV_TOOL_END, tool_call_id=call_id,
                         ok=False, canceled=True, preview="")]

    def _on_tool_result(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """历史结果事实（`tool_result{ok, data, error}`）→ 收卡。

        当前用 `tool_done` / `tool_failed` / `tool_ended`；保留这一支是为了让
        以 `tool_result` 落盘的结果事实仍能被翻译。
        """
        return self._finish_tool(d, ok=bool(d.get("ok")))

    def _on_tool_ended(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """工具**终态**（与 `tool_started` 配对）。

        它在结果事实**之后**紧随发出（`tool_done` / `tool_failed` / `tool_suspended`
        已经各自把卡片收过尾了），所以到这里**只做兜底**：若还有没被收尾的卡片
        （例如出现了没预料到的终止路径），在这里收掉——保证**每张卡都有终态**，
        不会永远停在「进行中」。卡片已被收过就走空（`pending` 里没有了）。
        """
        call_id = str(d.get("call_id") or "")
        if not call_id or call_id not in self.pending:
            return []
        return self._finish_tool(d, ok=(str(d.get("status") or "") != "failed"))

    def _finish_tool(self, d: Dict[str, Any], *, ok: bool) -> List[Dict[str, Any]]:
        """工具结果 → 经典界面的 `tool_end`（含卡片标签与结果预览）。"""
        call_id = str(d.get("call_id") or "")
        pend = self.pending.pop(call_id, None)
        if pend is None:
            return []          # 经典界面找不到 tool_call_id 就整个忽略
        data = d.get("data")
        envelope = data if isinstance(data, dict) else {}
        error = str(d.get("error") or "")

        out: List[Dict[str, Any]] = []
        frame: Dict[str, Any] = {
            "tool_call_id": call_id,
            "ok": ok,
            "preview": _preview_json(pend.script, data, error, ok),
        }
        images = C.public_tool_images(d.get("attachments"))
        if images:
            frame["images"] = images
        # ⚠️ `script` 是**经典界面判别"这是哪类工具"的唯一依据**，原样带上。
        #
        # 经典界面的 `fillToolPreview(o,ev)` 第 2 行就是
        # `const sc=(ev.script||"").toLowerCase();`，之后**所有**预览分支
        # （`run_command` 的实时输出、`write_file`/`replace_in_file` 的 diff …）
        # 都以 `sc` 为条件。漏发它 → `sc=""` → 一个分支都不进 → 预览槽永远空白。
        #
        # 帧带 `api_name` + `script`（`agent_runtime.py`
        # 三处 yield 都是 `{"type":"tool_end","api_name":…,"script":…,"tool_call_id":…,
        # "ok":…,"preview":…}`）。经典界面的 `onToolEnd` 直接把这个帧当事件用，
        # 所以 `ev.script` 一定有值 —— **漏发它就是漏了经典界面契约的一半**。
        frame["script"] = pend.script
        frame["api_name"] = pend.script
        # ⚠️ `data.confirm_id` 不映射为 `user_confirm_required`。
        #
        # `confirm_id` 是**写盘门控的二阶提交锁**，不是"等用户点卡片"：
        # 写盘门控给**预览类工具的成功结果**挂上它，意思是
        # "锁已建好，模型接着调提交工具并把 `confirm_id` 传回来"。
        # 用户交互**不发生在这一步**。
        #
        # 契约里没有"写盘需要确认 / 允许提交 / 拒绝"这段卡片文案：
        # 那段文案在契约里**根本不存在**，而且 `user_confirm_required`
        # 在经典界面里是 **100% 走弹窗**的（`openUserConfirmModalFromToolEnd`，
        # 会 `userConfirmBlocking=true` + `goBtn.disabled=true`）。虚构它有双重害处：
        #   ① 用户看到一张没人触发的内嵌卡，还得手动点 ✅；
        #   ② **模型完全不知道**发生了这个交互（`tool_done` 已正常返回，模型以为流程在跑）。
        #
        # 真正的挂起只有一条路：工具自己 `Outcome.suspend` / `await_user=True`
        # （由 `_on_tool_suspended` 处理）——只有那时才弹模态。
        #
        # 清单：经典界面从 `todo_list_data` 读（`todo_list` 为真才继续读）
        if pend.script == "todo_list" and envelope.get("items") is not None:
            frame["todo_list"] = True
            frame["todo_list_data"] = {
                "items": envelope.get("items") or [],
                "collapsed": bool(envelope.get("collapsed")),
                "close": bool(envelope.get("close")),
            }
        out.append(self._ev(C.EV_TOOL_END, **frame))

        # `run_type` 切模式 → 补一帧 `mode_changed`。
        #
        # 该工具直接写 `live_state.set_mode()`，但**不发** `mode_changed`；
        # 而经典界面的模式按钮只在 `mode_changed`（与 `conversation`）时刷新，
        # 所以模型用工具切换模式后必须由这里补一帧，否则按钮停在旧值。
        # 对照：`goal` 不需要在这里补——经典界面自己在 `onToolEnd` 里读工具结果
        # 刷新「目标」按钮（实现在 agent-ui.js 的 goal 分支）。
        if ok and pend.script == "run_type":
            switched = str(envelope.get("action") or "") == "switch"
            mode = envelope.get("run_type")
            if switched and mode:
                out.append(self._ev(C.EV_MODE_CHANGED, mode=C.normalize_mode(mode)))
        return out

    def _on_usage(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """用量：**必须嵌套在 `usage` 键下**。

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
        # `error{where:"turn"}`，那会与这里的 `error{where:"model"}` **重复** ——
        # 同一个失败会产生两帧 error，用户看到两行错误。
        self._error_sent = True
        return [self._ev(C.EV_ERROR,
                         message=str(d.get("detail") or d.get("where") or "未知错误"))]

    def _on_turn_ended(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """回合结束。**暂停**（等用户作答）与**正常结束**都发 `done`，但暂停多一帧信令。

        暂停同样发 `done`：SSE 的生命周期要完整（客户端总能看到收尾），
        而"这不是正常收尾"由 `paused_for_user_confirm` 表达——
        经典界面收到它就把本轮标记为"待用户确认"，随后 `done` 会**短路收尾**
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
            # 前端本身也会在点停止时**乐观地**先标一遍；这里这一帧是让**后端**也确认
            # 收尾，两者一致。
            # **不带文案**：点停止时前端已经本地加了一条「任务已停止。」，
            # 再带 `message` 会让前端 `if(ev.message)add(...)` 又加一条（用户看到两行）。
            # 这一帧只负责信号（标记回合停止、复位状态、清服务端标记）。
            out.append(self._ev(C.EV_STOPPED))
        # `halted` 也要让观察面看得见：模型调用失败、护栏触顶（max_passes）等
        # 都走 `halted`；若适配层**丢掉**这个字段，那些情况在 UI 上就会
        # 和"正常完成"完全一样（`done{ok:true}`）——失败被静默伪装成成功。
        halted = bool(d.get("halted")) or bool(d.get("interrupted"))
        detail = str(d.get("detail") or "")
        if halted and detail and not self._error_sent:
            # **必须同时给 `message`**：经典界面的 error 分支是
            # `add("a", "错误: " + (ev.message || JSON.stringify(ev)))`
            # （`agent-ui.js:175`）—— 只给 `where`/`detail` 时它走
            # `JSON.stringify(ev)`，用户看到的是**原始 JSON**：
            # `错误: {"type":"error","where":"turn","detail":"模型调用失败：…"}`
            # `_on_error` 同样给 `message`。
            out.append(self._ev(C.EV_ERROR, message=detail,
                                where="turn", detail=detail))
        out.append(self._ev(C.EV_DONE, ok=not (stopped or halted)))
        self._error_sent = False   # 回合收尾，下一回合重新计
        # 回合收尾再发一次布局：此时本趟事实**已落盘**，那趟的上下文条
        # 才不是「—」（布局由 `_emit_layout` 计算并发出）。
        out += self._emit_layout()
        self.pending.clear()
        self.paused = paused
        return out

    def _on_context_compacted(self, d: Dict[str, Any]) -> List[Dict[str, Any]]:
        """压缩事实 → 补一帧 `context_layout`（经典界面靠它画底部分段条）。

        经典界面没有"压缩"这个事件，但**压缩后上下文变了**，分段条必须跟着变。

        **内核不产出 `context_layout` 事实**，且压缩器的
        report 里**没有 `layout` 键**，所以这条分支永不命中 ——
        右栏上下文条**恒为「—」**。因此 `context_layout` **由事件的消费方计算**
        （这里），内核不必为此新增事实。算不出来就不发。
        """
        layout = d.get("layout")
        if isinstance(layout, dict):
            return self._on_context_layout(layout)
        return self._emit_layout()

    def _emit_layout(self) -> List[Dict[str, Any]]:
        """算并发出 `context_layout`；算不出来返回空列表。

        两处调用（每步的 `model_message`、回合收尾的 `turn_ended`）都要它，
        所以抽出来。回合收尾同样发一次：布局是从**已落盘的事实**算的
        （`inbound.compute_context_layout`），而事实按趟增量落盘 —— 一趟开始算布局时
        本趟事实还没落盘，于是**那一趟的上下文条一直是「—」**，
        直到刷新（走 `history()`）或下一趟才出现。收尾时事实已经写下，这时补一帧就补齐了。
        """
        computed = self.layout_resolver() if self.layout_resolver is not None else None
        if isinstance(computed, dict):
            return self._on_context_layout(computed)
        return []


def _preview_json(script: str, data: Any, error: str, ok: bool) -> str:
    """`tool_end.preview` 是 **JSON 字符串**（经典界面会 `JSON.parse`，失败回落原文）。

    与回灌模型的信封同形（见 `session_log._tool_envelope`）：
      - 成功：`{"ok": true, "data": <工具结果>}`
      - 失败：`{"ok": false, "error": "…"}`（可选附带 `data`）

    内层字段仍各工具不同（经典界面读 `data.stdout` / `data.diffText` /
    `data.diff_text` / `data.confirm_id` / `data.restored_path`）。
    """
    import json

    if not ok:
        payload: Dict[str, Any] = {"ok": False, "error": error}
        if data is not None:
            payload["data"] = data
    elif isinstance(data, dict):
        payload = {"ok": True, "data": data}
    else:
        payload = {"ok": True, "data": {"value": data}}
    try:
        return json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return json.dumps({"ok": False, "error": "结果无法序列化"}, ensure_ascii=False)
