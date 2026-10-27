# -*- coding: utf-8 -*-
"""适配层门面：`ClassicAdapter`。

职责边界：
  - 只做形状翻译：业务一律落到内核既有面；
  - 持有经典界面需要而内核不持有的内存态（用量累计 / 勾选 / 附件 / 布局）；
  - 把内核事件流翻成经典界面事件流（按会话一实例 `ClassicStream`）；
  - 不碰内核：不加钩子、不改语义；`web.py` 只调本类的公开方法。

事件如何从内核流到这里：`web.py` 在会话事件入库时调用 `feed()`（它已经在写盘路径上），
本类按会话翻译并推进各自的发送队列；SSE 连接从队列取帧、并用心跳保活。

入站请求的处理方法由 `Inbound` 提供，SSE 通道由 `ChannelMixin` 提供，
暂停态与确认回路由 `ConfirmMixin` 提供。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import agent.shell.classic_adapter.contract as C
from agent.core.error_report import report_error
from agent.core.input_attachments import MAX_IMAGES
from agent.shell.classic_adapter.channel import ChannelMixin, ClassicSseChannel
from agent.shell.classic_adapter.confirm import ConfirmMixin
from agent.shell.classic_adapter.inbound import ClassicState, Inbound
from agent.shell.classic_adapter.outbound import ClassicStream

__all__ = ["ClassicAdapter", "ClassicSseChannel"]


class ClassicAdapter(ChannelMixin, ConfirmMixin, Inbound):
    """经典界面的适配门面。"""

    def __init__(self, app: Any) -> None:
        Inbound.__init__(self, app, ClassicState())
        # 按会话一条翻译流。`_shell` 由 `adopt_shell` 注入，入站侧复用它派生标题
        # （保证与 `/api/chat/sessions` 同口径，不各写一套）。
        self._streams: Dict[str, ClassicStream] = {}
        self._init_channels()
        # 按会话记的暂停态（宿主状态，非内核阻塞态）。
        #
        # 待确认内容记在内核的
        # `SessionContext.pending_confirm`（`app._pending_confirm_recorder` 写入），
        # 适配层只读（`pending_confirm`）。这里只留"是否暂停"这个瞬时观测值，
        # 供 `/health` 与诊断用。
        self._paused: Dict[str, bool] = {}

    @property
    def inbound(self) -> "ClassicAdapter":
        """入站接口视图：入站方法由本类实现，`classic.inbound.*` 的取用点保持有效。"""
        return self

    # ── 会话与翻译流 ──────────────────────────────────────

    def _stream(self, cid: str) -> ClassicStream:
        stream = self._streams.get(cid)
        if stream is None:
            stream = ClassicStream(
                cid,
                mode_resolver=self._mode_of,
                model_resolver=self._model,
                layout_resolver=lambda _cid=cid: self._layout_for(_cid),
            )
            self._streams[cid] = stream
        return stream

    def _layout_for(self, cid: str) -> Optional[Dict[str, Any]]:
        """算当前会话的上下文分段快照（给经典界面的底部分段条用）。

        计算口径只有一处：`inbound.compute_context_layout` —— 刷新的
        `history()` 与这里的实时帧共用它，避免两条路径算出不同结果。

        对话与模式来自内核发的 `context_segments`（`ModelModule` 每次装配完请求发
        一条）：模式说明与工具调用的内部 system 注入不落记录，只有那份快照里有。
        插件段按当前注入源重算。适配层在这里换个名字转发给前端
        （前端认 `context_layout`）。

        算不出来返回 `None`，调用方不发那一帧。
        """
        store = getattr(self._app, "store", None)
        if store is None or not hasattr(store, "load"):
            return None
        events = list(store.load(cid))
        from agent.shell.classic_adapter.inbound import compute_context_layout

        return compute_context_layout(self._app, events, cid)

    def _mode_of(self, cid: str) -> str:
        live = getattr(self._app, "live_state", None)
        if live is None:
            return "auto"
        return str(live.get_mode(cid))

    def _model(self, cid: str = "") -> str:
        """当前会话用哪个模型（`conversation` 帧要把它同步给前端）。

        必须按会话取，不能恒取全局的 `provider.model`：那个 `conversation` 帧
        会把用户选好的模型覆盖回默认，表现为下拉自己跳回默认。
        """
        resolver = getattr(self._app, "model_for", None)
        if callable(resolver):
            try:
                want = str(resolver(cid) or "")
                if want:
                    return want
            except Exception as exc:
                # 判据同下：取会话模型只是给前端展示名，失败退回 live_state/默认名；
                # 这里抛出去会让整条 conversation 帧丢失。
                report_error("agent.shell.classic_adapter.adapter.ClassicAdapter._model", exc)
        live = getattr(self._app, "live_state", None)
        if live is not None:
            try:
                want = live.get_model(cid)
                if want:
                    return str(want)
            except Exception as exc:
                # 判据：读会话状态失败不该打断事件翻译（这里只是给前端一个展示名）。
                # 取不到就落到下面的 provider 默认名 —— 退化结果仍然可用，
                # 而抛出去会让整条 SSE 帧丢失，代价远大于"显示的是默认模型名"。
                report_error("agent.shell.classic_adapter.adapter.ClassicAdapter._model", exc)
        provider = getattr(self._app, "provider", None)
        return str(getattr(provider, "model", "") or "")

    def adopt_shell(self, shell: Any) -> None:
        """由 `WebShell` 调用：交出壳引用，让入站侧复用壳的标题派生等既有实现。"""
        self._shell = shell

    def drop_session(self, cid: str) -> None:
        """会话结束/关闭：清翻译流状态，并释放进程内会话运行态。"""
        key = str(cid or "").strip()
        with self._lock:
            self._streams.pop(key, None)
        self.state.clear_attachments(key)
        contexts = getattr(self._app, "session_contexts", None)
        if contexts is not None:
            try:
                contexts.release(key)
            except Exception as exc:
                # 释放是收尾副作用：失败不得阻断关闭路径。
                report_error("agent.shell.classic_adapter.adapter.ClassicAdapter.drop_session", exc)

    def dispose(self) -> None:
        """摘掉总线订阅、断开所有通道（幂等）。"""
        self._drop_subscription()
        with self._lock:
            self._channels.clear()
            self._streams.clear()

    # ── 内核事件入口 ──────────────────────────────────────

    def feed(self, ev_type: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """喂一个内核事件；翻译后广播给所有已连接的 SSE 通道。

        `web.py` 在事件入库路径上调用它——那里已经是"事实已落盘"的位置，
        所以翻译不会漏帧，也不改变内核时序。
        """
        cid = C.normalize_cid((data or {}).get("conversation_id"))
        if not cid:
            return []
        with self._lock:
            stream = self._stream(cid)
            frames = stream.translate(ev_type, data)
            channels = list(self._channels)
            # 用量累计（经典界面的 /api/usage-accumulator 要累计值）
            if ev_type == "usage":
                self.state.add_usage(cid, data)
            # ── 以下记账与"翻译出几帧"无关，无条件执行 ──
            # 若放到 `if not frames: return` 之后，翻译成 0 帧的事件
            # （如 `input_claimed`）就会跳过记账——状态就会丢掉。
            #
            # 暂停态：`turn_ended.paused` 给出。权威的待确认内容在
            # `SessionContext.pending_confirm`（内核侧由 `app._pending_confirm_recorder` 写入）
            # —— 适配层只读它，不另存一份。
            if ev_type == "turn_ended":
                self._paused[cid] = bool((data or {}).get("paused"))
        if not frames:
            return []
        self._push_frames(channels, frames, drop_oldest=True)
        return frames

    # ── 供壳层组装会话事件 ────────────────────────────────

    def conversation_frame(self, cid: str) -> Dict[str, Any]:
        """`conversation` 事件（必需）：经典界面靠它初始化模式与顶栏模型。

        缺它 → 刷新后模式按钮回落 auto、`#hdrModel` 停在"模型加载中…"。
        """
        cid = C.normalize_cid(cid)
        live = getattr(self._app, "live_state", None)
        mode = live.get_mode(cid) if live is not None else "auto"
        # 模型取会话级选择（没选过才回落 provider 默认）。
        # 不能恒取 `provider.model`：那样每来一帧就把用户的模型选择覆盖回默认
        # （表现为"发一条消息，模型下拉自己就跳回默认"），
        # 而用户接着发图时后端按默认模型的名字判能力（不认视觉）→ 图片被剥掉。
        model = self._model(cid)
        return {
            "type": C.EV_CONVERSATION,
            "conversation_id": cid,
            "mode": C.normalize_mode(mode),
            "model": model,
        }

    def health(self) -> Dict[str, Any]:
        """`/health`：`model` 必须在 `allowed_models` 里，否则经典界面白名单校验丢弃它
        （agent-ui.js:496 vs 407），顶栏永远"模型加载中…"。

        其余字段（`service` / `tools` / …）保留内核原有口径——经典界面不看它们，
        但既有测试与运维探针按它们认服务，删掉就等于静默改了对外契约。
        """
        provider = getattr(self._app, "provider", None)
        model = str(getattr(provider, "model", "") or "")
        # 可选清单以装配面为准（`config.ini` 的 `[model_reasoning] models`）：
        # provider 未必有 `allowed_models` 属性，只读它会让清单退化成"只有当前模型"
        # ——模型下拉只画一项，而且选择会被白名单校验拒掉。
        resolver = getattr(self._app, "available_models", None)
        allowed = [str(m) for m in (resolver() if callable(resolver) else []) or []]
        source = str(getattr(self._app, "model_config_state", "") or "")
        if not allowed and source != "none":
            allowed = [str(m) for m in (getattr(provider, "allowed_models", None) or [])]
        if not allowed and source == "none":
            model = ""
        if model and model not in allowed:
            allowed = [model, *allowed]
        contexts = getattr(self._app, "session_contexts", None)
        buckets = contexts.active_count() if contexts is not None else 0
        tools = len(self._app.registry.names())
        settings = getattr(self._app, "model_config", None)
        return {
            "ok": True,
            "service": "agent.web",
            "conversation_buckets": buckets,
            "sse_channels": len(self._channels),
            "tools": tools,
            "model": model,
            "allowed_models": allowed,
            "model_labels": {
                item.id: (item.label or item.id)
                for item in (getattr(self._app, "model_catalog", None).snapshot().entries
                             if getattr(self._app, "model_catalog", None) is not None else [])
            },
            # 全局默认档位：会话回填前顶栏先按它显示（会话值见 `/api/chat/ui-state`）。
            "reasoning_effort": (self._app.live_state.default_effort
                                 if self._app.live_state is not None else "high"),
            "max_images": MAX_IMAGES,
            "model_config": settings() if callable(settings) else {},
            # 停在"等用户作答"的会话（宿主状态，非内核阻塞态）。
            "paused_conversations": sorted(cid for cid, on in self._paused.items() if on),
            # 权威待确认状态来自内核的 `SessionContext`（`cid → call_id`）：
            # 上面那个是瞬时观测，这个才是"现在真挂着哪几个待确认"。
            "pending_confirms": self.pending_confirms(),
            "kernel": self._kernel_name(),
        }

    def _kernel_name(self) -> str:
        """当前内核名（`/health` 的 `kernel` 字段，观察面契约要它不消失）。"""
        return "core"
