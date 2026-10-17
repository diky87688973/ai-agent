# -*- coding: utf-8 -*-
"""适配层门面：`ClassicAdapter`。

职责边界：
  - **只做形状翻译**：业务一律落到内核既有面；
  - **持有经典界面需要而内核不持有的内存态**（用量累计 / 勾选 / 附件 / 布局）；
  - **把内核事件流翻成经典界面事件流**（按会话一实例 `ClassicStream`）；
  - **不碰内核**：不加钩子、不改语义；`web.py` 只调本类的公开方法。

事件如何从内核流到这里：`web.py` 在会话事件入库时调用 `feed()`（它已经在写盘路径上），
本类按会话翻译并推进各自的发送队列；SSE 连接从队列取帧、并用心跳保活。
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from agent.shell.classic_adapter import contract as C
from agent.shell.classic_adapter.inbound import ClassicState, Inbound
from agent.shell.classic_adapter.outbound import ClassicStream

#: 单会话待发队列上限：超出丢最旧的（UI 丢几帧旧事件好过整个服务被拖死）
_QUEUE_MAX = 512

#: 一次续传最多补多少条历史事件。游标很旧时宁可分几批补，
#: 也不一次把上万条塞进一条连接的队列（队列是有界的，塞爆就是丢帧）。
_REPLAY_LIMIT = 512


class ClassicAdapter:
    """经典界面的适配门面。"""

    def __init__(self, app: Any) -> None:
        self._app = app
        self.state = ClassicState()
        self.inbound = Inbound(app, self.state)
        # `WebShell` 建好后会把自己挂到 `_shell`，让 inbound 能复用内核的标题派生
        # （保证与 `/api/chat/sessions` 同口径，不各写一套）。
        self._shell: Any = None
        self._unsubscribe: Optional[Any] = None
        self._bus: Any = None
        self._lock = threading.Lock()
        self._streams: Dict[str, ClassicStream] = {}
        # 每条 SSE 连接各自一条队列（广播）。
        # 共享队列会让多个消费者（两个标签页、或浏览器 + 探针）**瓜分**事件——
        # 表现为"步骤卡不出现、用量不动"。
        self._channels: List["queue.Queue[Dict[str, Any]]"] = []
        self._last_beat = time.time()
        # 按会话记的**暂停态**（宿主状态，非内核阻塞态）。
        #
        # 待确认内容记在内核的
        # `SessionContext.pending_confirm`（`app._pending_confirm_recorder` 写入），
        # 适配层只读（`pending_confirm`）。这里只留"是否暂停"这个瞬时观测值，
        # 供 `/health` 与诊断用。
        self._paused: Dict[str, bool] = {}

    # ── 会话与队列 ────────────────────────────────────────

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

        **计算口径只有一处**：`inbound.compute_context_layout` —— 刷新的
        `history()` 与这里的实时帧共用它，避免两条路径算出不同结果。

        对话与模式来自内核发的 `context_segments`（`ModelModule` 每次装配完请求发
        一条）：模式说明与工具轮的内部 system 注入不落记录，只有那份快照里有。
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

        **必须按会话取**，不能恒取全局的 `provider.model`：那个 `conversation` 帧
        会把用户选好的模型覆盖回默认，表现为下拉自己跳回默认。
        """
        live = getattr(self._app, "live_state", None)
        if live is not None:
            try:
                want = live.get_model(cid)
                if want:
                    return str(want)
            except Exception:
                # 判据：**读会话状态失败不该打断事件翻译**（这里只是给前端一个展示名）。
                # 取不到就落到下面的 provider 默认名 —— 退化结果仍然可用，
                # 而抛出去会让整条 SSE 帧丢失，代价远大于"显示的是默认模型名"。
                pass
        provider = getattr(self._app, "provider", None)
        return str(getattr(provider, "model", "") or "")

    def adopt_shell(self, shell: Any) -> None:
        """由 `WebShell` 调用：交出壳引用，让入站侧复用壳的标题派生等既有实现。"""
        self._shell = shell
        self.inbound._shell = shell

    def bind_bus(self, event_bus: Any) -> None:
        """记下事件总线，**先不订阅**。

        订阅是**按需**的：有 SSE 连接进来才订阅、最后一个连接断开就摘掉（实现在
        `attach` / `detach`）。两个理由：
          1. 没有客户端时翻译纯属白做功；
          2. 常驻订阅会变成一条**谁都回收不掉的泄漏**——`plugin_host.unload_all()`
             之后再数事件总线订阅，会多出这一条。
        """
        self._bus = event_bus

    def _ensure_subscribed(self) -> None:
        """第一条连接进来：开始订阅（已订阅则不动）。"""
        if self._unsubscribe is not None or self._bus is None:
            return
        self._unsubscribe = self._bus.subscribe_all(
            lambda event: self.feed(str(event.type), dict(event.data or {}))
        )

    def _drop_subscription(self) -> None:
        """最后一条连接断开：摘掉订阅，不留常驻观察者。"""
        dispose = self._unsubscribe
        self._unsubscribe = None
        if callable(dispose):
            try:
                dispose()
            except Exception:
                pass

    def dispose(self) -> None:
        """摘掉总线订阅、断开所有通道（幂等）。"""
        self._drop_subscription()
        with self._lock:
            self._channels.clear()
            self._streams.clear()

    @property
    def channel_count(self) -> int:
        """当前 SSE 连接数（供 /health 与测试观察）。"""
        with self._lock:
            return len(self._channels)

    @property
    def subscribed(self) -> bool:
        """当前是否订阅着事件总线（供测试证明"没人连时不占订阅"）。"""
        return self._unsubscribe is not None

    def attach(self) -> "queue.Queue[Dict[str, Any]]":
        """一条新 SSE 连接：给它一条独立队列，并在**首条连接**时开始订阅总线。

        顺序是**先入列、后订阅**：反过来的话，从入列到订阅之间的那几毫秒里
        发布的事件会既没进队列也没被翻译——直接消失。
        """
        box: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=_QUEUE_MAX)
        with self._lock:
            self._channels.append(box)
            first = len(self._channels) == 1
        if first:
            self._ensure_subscribed()
        return box

    def detach(self, box: "queue.Queue[Dict[str, Any]]") -> None:
        """连接断开（刷新 / 关标签）：摘掉队列；**最后一条**断开时退订总线。"""
        with self._lock:
            if box in self._channels:
                self._channels.remove(box)
            last = not self._channels
        if last:
            self._drop_subscription()

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
            except Exception:
                # 释放是收尾副作用：失败不得阻断关闭路径。
                pass

    # ── 入站（前端 → 服务端）：转发到 inbound ──────────────

    def sessions(self) -> Dict[str, Any]:
        return self.inbound.sessions()

    def history(self, cid: str) -> Dict[str, Any]:
        return self.inbound.history(cid)

    def ui_state_get(self) -> Dict[str, Any]:
        return self.inbound.ui_state_get()

    def ui_state_put(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return self.inbound.ui_state_put(body)

    def title(self, cid: str) -> Dict[str, Any]:
        return self.inbound.title(cid)

    def usage_get(self, cid: str) -> Dict[str, Any]:
        return self.inbound.usage_get(cid)

    def usage_put(self, cid: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return self.inbound.usage_put(cid, body)

    def command_input(self, cid: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return self.inbound.command_input(cid, body)

    def attachment(self, cid: str, ident: str) -> Tuple[int, bytes, str]:
        return self.inbound.attachment(cid, ident)

    def is_paused(self, cid: str) -> bool:
        """该会话是否停在"等用户作答"（宿主状态）。

        内核**不阻塞、不等待**：暂停就是回合正常结束（资源已释放、服务可服务别的会话），
        只是多了一帧 `paused_for_user_confirm` 信令，让宿主知道"这不是正常收尾"。
        恢复由用户在界面上作答触发 `POST /api/chat/user-confirm` → 起新回合。
        所以"是否暂停"是**适配层按会话记的状态**，不是内核里的阻塞态。
        """
        cid = C.normalize_cid(cid)
        if not cid:
            return False
        return bool(self._paused.get(cid))

    def _kernel_name(self) -> str:
        """当前内核名（`/health` 的 `kernel` 字段，观察面契约要它不消失）。"""
        return "core"

    def pause_state(self) -> Dict[str, Any]:
        """暂停态快照（供 /health 或诊断观察）。

        `pending_confirm` 从**内核的 `SessionContext`** 现读（权威在那里），
        本类不另存一份：两处各存一份迟早不一致。
        """
        return {
            "paused": sorted(cid for cid, on in self._paused.items() if on),
            "pending_confirm": self.pending_confirms(),
        }

    def pending_confirms(self) -> Dict[str, Any]:
        """全量扫一遍会话状态，给出**当前所有**待确认（`cid → call_id`）。

        `_paused` 不作复用来源：那是"上一次 `turn_ended` 说停着"的瞬时观测，
        而**权威状态**是 `SessionContext.pending_confirm`。两者可能短暂不一致
        （例如新回合还没收尾），所以可观测性接口一律以权威为准。
        """
        contexts = getattr(self._app, "session_contexts", None)
        if contexts is None:
            return {}
        buckets = contexts.buckets()
        out: Dict[str, Any] = {}
        for cid, session in buckets.items():
            pending = getattr(session, "pending_confirm", None)
            if isinstance(pending, dict) and pending:
                out[cid] = pending.get("call_id")
        return out

    # ── 用户确认回路（`user_confirm` 工具的第二段）──────────
    #
    # 经典界面的确认模态在用户点「确认」后 POST 的是
    #   `{conversation_id, confirm: <用户选的文本>, mode, model}`
    # `agent-ui.js` 的 `submitUserConfirm` 就是这条请求，并期待返回体带 `run_id`——
    # 也就是说**它期待服务端把选择送回模型**，而不是只回一个"收到"。
    #
    # 工具声明也印证这点：次段调用要带 `confirm`（用户确认结果），模型才能完成回路。
    # 所以适配层必须把 `confirm` 经 `mesh.submit` 投回该会话：
    # 忙则入队（`queued: true`），闲则直接起新回合（拿到 `run_id`）。
    def user_confirm(self, cid: str, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """处理确认端点。两类请求在这里分流（经典界面两种情况共用一个端点）。"""
        cid = C.normalize_cid(cid)
        if not cid:
            return 400, {"error": "missing conversation_id"}
        approval = str(body.get("approval") or "").strip().lower()
        if approval:
            if approval not in ("agree", "reject"):
                return 400, {"ok": False, "error": "approval 只能是 agree 或 reject"}
            return 200, self.submit_approval(cid, approval == "agree")
        confirm_id = str(body.get("confirm_id") or "").strip()
        confirm_text = str(body.get("confirm") or "").strip()

        # ① 写盘门控：带 `confirm_id` → 解锁预览快照（内核既有行为，不动）。
        gate_result: Optional[Tuple[int, Dict[str, Any]]] = None
        if confirm_id:
            shell = self._shell
            confirmer = getattr(shell, "confirm", None) if shell is not None else None
            if callable(confirmer):
                gate_result = confirmer(cid, confirm_id)

        # ② 选择回填：带 `confirm` 文本 → 把用户选择送回模型（`user_confirm` 的第二段）。
        if confirm_text:
            submitted = self.submit_user_choice(cid, confirm_text)
            if gate_result is not None and gate_result[0] != 200:
                # 门控失败但选择已投出：两者都告诉前端，回填不算失败
                return 200, {**gate_result[1], **submitted, "confirmed": False}
            return 200, submitted

        if gate_result is not None:
            return gate_result

        # 既没有 `confirm_id` 也没有 `confirm` 文本：模态的「取消」走这里。
        #
        # **必须交给 `submit_user_choice`**，不能就地返回 200 了事：
        #   ① 挂起会**继续保持** —— 用户以为取消了，其实那次调用还在等作答；
        #   ② 那次调用的 `tool_result` 永不出现 → 悬空的 `assistant(tool_calls)`
        #      留在历史里 → 该会话之后**每条消息都 400**，不可自愈。
        # 交给 `submit_user_choice` 后，"取消"被当成"**拒绝作答**"记成工具结果，
        # 既闭合了配对，也让模型知道用户不想答（它可以改问法或换方案）。
        return 200, self.submit_user_choice(cid, "")

    def submit_user_choice(self, cid: str, text: str) -> Dict[str, Any]:
        """用户作答 → 把选择写成那次调用的返回值，再起新回合（两段式第二段）。

        选择**不写成新用户发言**：那样模型要重新理解一遍「左」是什么，还得自己判断
        该不该再问一次，往往会重复提问。写成工具返回值，模型看到的是"工具终于返回了
        答案"，接着往下做即可。

        **权威状态在内核的 `SessionContext.pending_confirm`**：
        首段返回信封时由管道记下，回合放行结束；这里读它拿到 `call_id`，写入那次调用
        **唯一**的 `tool_result`。
        """
        cid = C.normalize_cid(cid)
        if not cid:
            return {"ok": False, "error": "invalid conversation_id", "confirmed": False}
        mesh = getattr(self._app, "mesh", None)
        if mesh is None:
            return {"ok": False, "error": "mesh 不可用", "confirmed": False}

        # 挂起状态记在会话上下文里（内核侧写的），适配层只读。
        pending = self.pending_confirm(cid) if hasattr(self, "pending_confirm") else None
        call_id = str((pending or {}).get("call_id") or "")
        payload: Dict[str, Any] = {"content": "", "attachments": [], "mode": "", "model": ""}
        # 空文本 = 用户在模态上点了「取消」。**这不是"没作答"，而是"拒绝作答"**：
        # 拒绝也作为那次调用的**结果**交回去，否则
        #   ① 那次调用的 `tool_result` 永不出现 → 悬空的 `assistant(tool_calls)`
        #      留在历史里（该会话之后**每条消息都 400**，不可自愈）；
        #   ② 若照"起一个没有输入的新回合"处理，内核那一轮不产出任何事实
        #      → **永远不发 `done`** → 前端「正在思考中」永久转圈、发送按钮消失
        #      （用户只能点「停止」逃生）。
        text = str(text or "")
        declined = not text.strip()
        if str((pending or {}).get("kind") or "") == "approval":
            # 审批挂起不接受选项文本。空 confirm 在这里不记成取消。
            return {
                "ok": False,
                "error": "当前挂起的是审批，confirm 文本不作为作答",
                "confirmed": False,
                "conversation_id": cid,
                "queued": False,
                "run_id": "",
                "resumed_call": "",
            }
        if call_id:
            # **经运行器提交结果**：由它把结果拼成 `tool_result` 事实并起一轮。
            # 事实由运行器写入：适配层直接写会成为第二个事实写点，
            # 也会绕开"写前查重"。
            # `resume` 走消息体，所以**忙时入队也正确**（结果随队列入队，不会丢）。
            payload["resume"] = (
                {"call_id": call_id, "ok": False,
                 "error": "用户取消了这次确认（未作答）"}
                if declined else
                {"call_id": call_id, "ok": True, "data": {"confirm": text}}
            )
        elif declined:
            # 没有挂起调用可拒绝：**不起空回合**——那正是"永久转圈"的来源。
            return {"ok": True, "confirmed": False, "declined": True,
                    "conversation_id": cid, "queued": False, "run_id": "",
                    "resumed_call": "",
                    "note": "没有待确认的调用，取消未触发新回合"}
        self._clear_pending(cid) if call_id else None

        try:
            result = mesh.submit(cid, dict(payload))
        except Exception as exc:
            return {"ok": False, "error": str(exc), "confirmed": False}
        return {
            "ok": True,
            "confirmed": not declined,
            "declined": declined,
            "conversation_id": cid,
            "queued": bool(result.get("queued")),
            "run_id": str(result.get("run_id") or ""),
            # 是否真的把结果交回给了内核（没有挂起调用时为假——退化成纯新回合）
            "resumed_call": call_id,
        }

    def submit_approval(self, cid: str, agreed: bool) -> Dict[str, Any]:
        """审批作答。同意时签发 `approval_id` 并记下 `option_id`；驳回的结果是「不同意」。

        结果写回挂起的那次 `approval_confirm`。
        """
        cid = C.normalize_cid(cid)
        if not cid:
            return {"ok": False, "error": "invalid conversation_id", "confirmed": False}
        mesh = getattr(self._app, "mesh", None)
        if mesh is None:
            return {"ok": False, "error": "mesh 不可用", "confirmed": False}
        pending = self.pending_confirm(cid) if hasattr(self, "pending_confirm") else None
        kind = str((pending or {}).get("kind") or "")
        call_id = str((pending or {}).get("call_id") or "")
        if kind != "approval" or not call_id:
            return {
                "ok": False,
                "error": "没有待审批的调用",
                "confirmed": False,
                "conversation_id": cid,
                "queued": False,
                "run_id": "",
                "resumed_call": "",
            }
        approval_id = ""
        if agreed:
            option_id = str((pending or {}).get("option_id") or "").strip()
            session = self._session(cid)
            if not option_id or session is None:
                return {
                    "ok": False,
                    "error": "待审批缺少 option_id",
                    "confirmed": False,
                    "conversation_id": cid,
                    "queued": False,
                    "run_id": "",
                    "resumed_call": "",
                }
            approval_id = session.grant_approval(option_id)
            data: Dict[str, Any] = {"decision": "同意", "approval_id": approval_id}
        else:
            data = {"decision": "不同意"}
        payload: Dict[str, Any] = {
            "content": "",
            "attachments": [],
            "mode": "",
            "model": "",
            "resume": {"call_id": call_id, "ok": True, "data": data},
        }
        self._clear_pending(cid)
        try:
            result = mesh.submit(cid, dict(payload))
        except Exception as exc:
            return {"ok": False, "error": str(exc), "confirmed": False}
        return {
            "ok": True,
            "confirmed": agreed,
            "decision": data["decision"],
            "approval_id": approval_id,
            "conversation_id": cid,
            "queued": bool(result.get("queued")),
            "run_id": str(result.get("run_id") or ""),
            "resumed_call": call_id,
        }

    def _session(self, cid: str) -> Any:
        """取该会话的 `SessionContext`（待确认状态记在这里）。"""
        contexts = getattr(self._app, "session_contexts", None)
        if contexts is None:
            return None
        return contexts.resolve_sync(cid)

    def pending_confirm(self, cid: str) -> Optional[Dict[str, Any]]:
        """该会话当前挂着的待确认（`SessionContext.pending_confirm`）。

        它是**跨回合**的会话态：暂停发生在上一回合、作答在下一回合，
        它是跨回合状态，放回合级上下文会随回合消亡；适配层只读。
        """
        cid = C.normalize_cid(cid)
        if not cid:
            return None
        session = self._session(cid)
        pending = getattr(session, "pending_confirm", None) if session is not None else None
        return dict(pending) if isinstance(pending, dict) else None

    def _clear_pending(self, cid: str) -> None:
        """清掉该会话的待确认状态（作答已消费，留着会让下次作答回到旧调用上）。"""
        session = self._session(cid)
        if session is not None:
            session.pending_confirm = None

    def feed(self, ev_type: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """喂一个内核事件；翻译后**广播**给所有已连接的 SSE 通道。

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
            # ── 以下记账**与"翻译出几帧"无关**，无条件执行 ──
            # 若放到 `if not frames: return` 之后，翻译成 0 帧的事件
            # （如 `input_claimed`）就会跳过记账——状态就会丢掉。
            #
            # 暂停态：`turn_ended.paused` 给出。**权威的待确认内容**在
            # `SessionContext.pending_confirm`（内核侧由 `app._pending_confirm_recorder` 写入）
            # —— 适配层只读它，不另存一份。
            if ev_type == "turn_ended":
                self._paused[cid] = bool((data or {}).get("paused"))
        if not frames:
            return []
        for box in channels:
            for frame in frames:
                try:
                    box.put_nowait(frame)
                except queue.Full:
                    try:
                        box.get_nowait()          # 丢最旧，绝不阻塞事件流
                        box.put_nowait(frame)
                    except queue.Empty:
                        pass
        return frames

    def next_frame(
        self,
        box: "queue.Queue[Dict[str, Any]]",
        timeout: float = 1.0,
    ) -> Optional[Dict[str, Any]]:
        """从**指定通道**取一帧；超时返回 None（SSE 层据此发心跳）。"""
        try:
            return box.get(timeout=max(0.0, timeout))
        except queue.Empty:
            # 超时无帧：SSE 层据此发心跳，不是错误
            return None

    def heartbeat(self) -> Dict[str, Any]:
        """心跳帧（豁免 `conversation_id` 校验）。"""
        self._last_beat = time.time()
        return {"type": C.EV_HEARTBEAT, "time": int(self._last_beat)}

    def announce_plugins(self, loaded: List[str]) -> None:
        """把已装载插件名推给每条 SSE 连接。

        开关是进程级的，这帧不带会话号。页面据此改按钮、关面板、重画上下文条。
        """
        names = sorted({str(name) for name in loaded if str(name or "").strip()})
        frame = {"type": C.EV_PLUGINS_CHANGED, "loaded": names}
        with self._lock:
            channels = list(self._channels)
        for box in channels:
            try:
                box.put_nowait(frame)
            except queue.Full:
                try:
                    box.get_nowait()
                    box.put_nowait(frame)
                except queue.Empty:
                    pass

    # ── 续传（断线重连从游标继续）──────────────────────────

    def replay_after(self, after_seq: int, only: Any = None, limit: int = _REPLAY_LIMIT) -> int:
        """把 `seq > after_seq` 的历史事件翻成老事件、投进通道，返回投出的帧数。

        **跨会话**：坐标是全局单调的，所以一个游标对所有会话都成立——
        这正是 SSE `Last-Event-ID` 的语义（一条流一个光标）。
        游标若按会话各自从 0 编号，一个值就无法表达"所有会话的位置"，
        额外带上 `?conversation_id=`。

        `only` 给定某条通道时只投给它（重连续传）；不给则广播给当前所有通道。
        `limit` 兜住"游标很旧"：宁可分几批补，也不一次把上万条塞进队列。
        """
        store = getattr(self._app, "store", None)
        if store is None or not hasattr(store, "tail_across"):
            return 0
        with self._lock:
            frames: List[Dict[str, Any]] = []
            rows = store.tail_across(int(after_seq), limit=limit)
            # 按会话分组翻译：每个会话一条 `ClassicStream`（翻译是有状态的，
            # 轮次号 / 待配对工具都按会话各自维护）。
            # 装配/契约错误（如缺 registry）直接冒泡，禁止吞成空回放。
            for seq, cid, event in rows:
                stream = self._stream(cid)
                payload = dict(event.data or {})
                payload["_seq"] = seq
                frames.extend(stream.translate(str(event.type), payload))
            channels = [only] if only is not None else list(self._channels)
        for box in channels:
            for frame in frames:
                try:
                    box.put_nowait(frame)
                except queue.Full:
                    break       # 通道已满：宁可少补历史，也不阻塞
        return len(frames)

    def latest_seq(self) -> int:
        """当前**全局**最大坐标；没有任何坐标时返回 -1。"""
        store = getattr(self._app, "store", None)
        if store is None or not hasattr(store, "_scan_max_seq"):
            return -1
        try:
            return int(store._scan_max_seq())
        except Exception:
            return -1

    def cursor_of(self, request_headers: Any, query: Dict[str, str]) -> int:
        """取本次连接的续传游标。

        优先 `Last-Event-ID` 请求头（浏览器 `EventSource` **自动**带上的标准位置），
        其次 `?last_event_id=`（非浏览器客户端显式指定）；都没有则 -1（从头开始）。
        非整数一律当 -1：游标不可信时重放全量，比断在半路安全。
        """
        candidates: List[str] = []
        if query:
            candidates.append(str(query.get("last_event_id") or ""))
        if request_headers is not None:
            try:
                candidates.append(str(request_headers.get("Last-Event-ID") or ""))
            except Exception:
                # **旁路，刻意吞掉**：`Last-Event-ID` 是断线续传的**可选**请求头。
                # 取不到（headers 实现异常）就少一个候选坐标，下面的循环会用
                # URL 查询参数那一路兜底——续传能力降级，不影响本次订阅。
                pass
        for raw in candidates:
            text = raw.strip()
            if not text:
                continue
            try:
                return int(text)
            except ValueError:
                return -1
        return -1

    # ── 供壳层组装会话事件 ────────────────────────────────

    def conversation_frame(self, cid: str) -> Dict[str, Any]:
        """`conversation` 事件（**必需**）：经典界面靠它初始化模式与顶栏模型。

        缺它 → 刷新后模式按钮回落 auto、`#hdrModel` 停在"模型加载中…"。
        """
        cid = C.normalize_cid(cid)
        live = getattr(self._app, "live_state", None)
        provider = getattr(self._app, "provider", None)
        mode = live.get_mode(cid) if live is not None else "auto"
        # 模型取**会话级选择**（没选过才回落 provider 默认）。
        # 不能恒取 `provider.model`：那样每来一帧就把用户的模型选择覆盖回默认
        # （表现为"发一条消息，模型下拉自己就跳回默认"），
        # 而用户接着发图时后端按**默认**模型的名字判能力（不认视觉）→ 图片被剥掉。
        model = live.get_model(cid) if live is not None else ""
        return {
            "type": C.EV_CONVERSATION,
            "conversation_id": cid,
            "mode": C.normalize_mode(mode),
            "model": model or str(getattr(provider, "model", "") or ""),
        }

    def health(self) -> Dict[str, Any]:
        """`/health`：`model` **必须在 `allowed_models` 里**，否则经典界面白名单校验丢弃它
        （agent-ui.js:496 vs 407），顶栏永远"模型加载中…"。

        其余字段（`service` / `tools` / …）保留内核原有口径——经典界面不看它们，
        但既有测试与运维探针按它们认服务，删掉就等于静默改了对外契约。
        """
        provider = getattr(self._app, "provider", None)
        model = str(getattr(provider, "model", "") or "")
        # 可选清单以**装配面**为准（`config.ini` 的 `[model_reasoning] models`）：
        # provider 未必有 `allowed_models` 属性，只读它会让清单退化成"只有当前模型"
        # ——模型下拉只画一项，而且选择会被白名单校验拒掉。
        resolver = getattr(self._app, "available_models", None)
        allowed = [str(m) for m in (resolver() if callable(resolver) else []) or []]
        if not allowed:
            allowed = [str(m) for m in (getattr(provider, "allowed_models", None) or [])]
        if model and model not in allowed:
            allowed = [model, *allowed]
        contexts = getattr(self._app, "session_contexts", None)
        buckets = contexts.active_count() if contexts is not None else 0
        tools = len(self._app.registry.names())
        return {
            "ok": True,
            "service": "agent.web",
            "conversation_buckets": buckets,
            "sse_channels": len(self._channels),
            "tools": tools,
            "model": model,
            "allowed_models": allowed,
            # 停在"等用户作答"的会话（宿主状态，非内核阻塞态）。
            "paused_conversations": sorted(cid for cid, on in self._paused.items() if on),
            # 权威待确认状态来自内核的 `SessionContext`（`cid → call_id`）：
            # 上面那个是瞬时观测，这个才是"现在真挂着哪几个待确认"。
            "pending_confirms": self.pending_confirms(),
            "kernel": self._kernel_name(),
        }


class ClassicSseChannel:
    """一条 SSE 连接的取帧循环（由 web.py 的 handler 驱动）。"""

    def __init__(self, adapter: ClassicAdapter, heartbeat: float = C.HEARTBEAT_SECONDS_DEFAULT) -> None:
        self.adapter = adapter
        self.heartbeat = float(heartbeat)
        self._last_sent = time.time()
        # 每条连接自己的队列：多标签页各自收到完整事件流（不能共享队列）
        self._box = adapter.attach()

    def close(self) -> None:
        self.adapter.detach(self._box)

    def resume(self, after_seq: int) -> int:
        """重连续传：把**全局坐标** `> after_seq` 的事件补进本连接的队列。

        只补这一条连接（不广播）——别的连接没断，它们不需要补。
        """
        return self.adapter.replay_after(after_seq, only=self._box)

    def next_payload(self) -> str:
        """返回一帧的文本；空闲超时则发心跳。

        带 `seq` 的帧发两行：`id: <seq>` + `data: <json>`。SSE 原生的
        `id:` 行会让浏览器在断线重连时经 `Last-Event-ID` 把游标带回来，
        适配层据此续传——不必重放全部，也不会丢掉中间那段。
        """
        import json

        frame = self.adapter.next_frame(self._box, timeout=1.0)
        if frame is None:
            if time.time() - self._last_sent >= self.heartbeat:
                frame = self.adapter.heartbeat()
            else:
                return ": keep-alive\n\n"      # 注释帧：经典界面忽略非 data: 行
        self._last_sent = time.time()
        try:
            body = json.dumps(frame, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            body = json.dumps({"type": C.EV_ERROR, "message": "事件序列化失败"})
        seq = frame.get("seq")
        if isinstance(seq, int) and not isinstance(seq, bool) and seq >= 0:
            return f"id: {seq}\ndata: {body}\n\n"
        return f"data: {body}\n\n"
