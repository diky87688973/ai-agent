# -*- coding: utf-8 -*-
"""会话运行器：后台执行会话回合，消费会话待发送队列。

- 装配为 MeshState 激活器（activator）：闲时直启、忙时由 mesh 排队；
- 生命周期：try_begin_run（原子占位）→ 线程执行回合 → end_run（释放 + 队列抽干）；
- 单回合失败不打断抽干链；异常兜底释放占位并告警；wait_idle 供测试 / 壳层等待；
- 身份块经 system_prompt 注入通道进入上下文，不写初始事件流。
"""
from __future__ import annotations

import sys
import threading
import time
from typing import Any, Callable, Dict, Optional

from agent.core.error_report import report_error
from agent.core.events import Event
from agent.shell.prompts import (
    resolve_mode_note,
    resolve_system_prompt,
)

# 运行态心跳的间隔（秒）：远小于 `RunRegistry` 的存活期（默认 900 秒），
# 又不会有任何可观测开销（一次小文件写入）。
_HEARTBEAT_INTERVAL_SECONDS = 60.0

#: 目标/自主自动续跑的轮数上限：兜底防止"目标写歪 → 无限烧 token"。
#: 用户重新发消息会重置这个链（新一轮 runner），所以正常使用不受影响。
_MAX_AUTO_ROUNDS = 50

#: 自主续跑提示的兜底文案：只有开了自主开关却没有目标时才会走到它。
#: 有目标时触发文案是目标（`goal`）里那条可编辑的文本。
AUTO_CONTINUE_PROMPT = (
    "（自主模式）请继续推进未完成的工作；若已全部完成或需要用户决策，"
    "请直接给出结论并停止，不要再调用工具。"
)


class SessionRunner:
    """后台回合运行器：以 mesh 活跃集为唯一忙闲事实源。

    `auto_continue`：注入的判断函数（cid → bool）。回合结束后若为真，则自动再跑一轮
    ——这是「自主模式」的落地（`_autoEnabled` + `/api/chat/autonomous`）。

    `goal_row`：注入的取目标函数（cid → dict | None）。目标存在时它说了算：
    `active` 用目标文案续跑；`paused`/`done` 就停 —— 此时不看 `auto_continue`，
    否则"暂停"会被自主开关顶回去，用户点了暂停却看到模型继续跑。
    只有完全没有目标时才回落到 `auto_continue` + `AUTO_CONTINUE_PROMPT`。
    """

    def __init__(
        self,
        *,
        app: Any,
        mesh: Any,
        auto_continue: Optional[Callable[[str], bool]] = None,
        goal_row: Optional[Callable[[str], Any]] = None,
        prompt_sections: Any = None,
    ) -> None:
        self._app = app
        self._mesh = mesh
        self._auto_continue = auto_continue
        self._goal_row = goal_row
        self._prompt_sections = prompt_sections
        self._lock = threading.Lock()
        self._threads: Dict[str, threading.Thread] = {}
        self._cancels: Dict[str, threading.Event] = {}  # cid → 取消信号（协作式）

    # ── 激活入口（装配到 MeshState.set_activator）──────────

    def start(self, cid: str, message: Dict[str, Any]) -> str:
        """启动一个后台回合；占位失败（忙）返回空串（由 mesh 回退入队）。

        `message` 可带：
        - `content`：用户文本；
        - `attachments`：随本轮注入模型请求的附件；
        - `resume`：外部结果回灌——形如
          `{"call_id": ..., "ok": True, "data": ...}`。带它时这一轮没有用户发言，
          运行器先把结果写成 `tool_result` 事实，再跑回合让模型消费它。
        """
        key = str(cid or "").strip()
        rid = self._mesh.try_begin_run(key)
        if not rid:
            return ""
        text = str(message.get("content") or "")
        attachments = message.get("attachments")
        resume = message.get("resume")
        if not isinstance(resume, dict) and (text or attachments):
            pending_call = self._cancel_pending_for_new_input(key)
            if pending_call:
                resume = {
                    "call_id": pending_call,
                    "ok": False,
                    "error": "用户取消了这次确认（未作答）",
                }
        sender = message.get("sender") if isinstance(message.get("sender"), dict) else None
        if sender is None and str(message.get("_sender") or "").strip():
            sender = {
                "cid": str(message.get("_sender") or "").strip(),
                "name": str(message.get("_sender_name") or "").strip(),
            }
        cancel_event = threading.Event()
        with self._lock:
            self._cancels[key] = cancel_event
        thread = threading.Thread(
            target=self._run_loop,
            args=(key, text, attachments, resume, sender),
            name=f"fan-mesh-{key[:12]}",
            daemon=True,
        )
        with self._lock:
            self._threads[key] = thread
        thread.start()
        return rid

    # ── 协作式取消 ───────────────────────────────────────

    def request_cancel(self, cid: str) -> bool:
        """请求停止该会话当前回合；返回是否有活跃回合被标记。"""
        key = str(cid or "").strip()
        with self._lock:
            event = self._cancels.get(key)
        if event is None:
            return False
        event.set()
        return True

    def _cancel_check(self, cid: str):
        """给内核的停止检查（内核 `cancel` 参数的注入位）。"""

        def _check() -> bool:
            with self._lock:
                event = self._cancels.get(cid)
            return bool(event is not None and event.is_set())

        return _check

    # ── 回合执行与队列抽干 ────────────────────────────────

    def _heartbeat_until(self, cid: str, stop: threading.Event) -> None:
        """在 `stop` 被置位前，周期性续运行态心跳（旁路线程，异常不外抛）。

        间隔取 60 秒：远小于 `RunRegistry` 的存活期（默认 900 秒），
        又不会有任何可观测开销（一次小文件写入）。
        """
        while not stop.wait(_HEARTBEAT_INTERVAL_SECONDS):
            try:
                self._mesh.touch_run(cid)
            except Exception:
                # 心跳失败不影响回合本身；
                # 真的失败时 `RunRegistry` 会按 TTL 判定过期，行为退化成"没心跳"。
                pass

    def _run_loop(self, cid: str, text: str, attachments: Any = None,
                  resume: Any = None, sender: Optional[Dict[str, Any]] = None) -> None:
        # 运行态心跳由旁路线程周期性续期：这一趟从占位到释放可能持续很久，
        # 而 `RunRegistry` 用"心跳 + 存活期"判定在跑 —— 一次长工具调用
        # （`run_command` 跑 `ping -n 120`）期间没有心跳就会被误判成"已结束"，
        # 用户那边的停止键会消失。所以这里起一个轻量线程周期性续心跳。
        stop_beat = threading.Event()
        beater = threading.Thread(
            target=self._heartbeat_until, args=(cid, stop_beat),
            name=f"fan-mesh-beat-{cid[:12]}", daemon=True,
        )
        beater.start()
        # 因目标/自主而起的自动轮次计数，只用于兜底限流。
        _auto_rounds = 0
        current_queue_item = None
        from_queue = False
        try:
            while True:
                paused = False
                try:
                    paused = self._execute(cid, text, attachments, resume, sender,
                                           from_queue=from_queue)
                except Exception as exc:  # 单回合失败不打断抽干链
                    report_error("shell.session_runner", exc, conversation_id=cid)
                if current_queue_item is not None:
                    self._complete_queued(cid, current_queue_item)
                    current_queue_item = None
                if paused or self._is_paused(cid):
                    self._mesh.end_run(cid)
                    break
                resume = None
                sender = None
                from_queue = False
                queued = self._claim_queued(cid)
                if queued is not None:
                    if self._is_canceled(cid):
                        self._release_queued(cid, queued)
                        self._mesh.end_run(cid)
                        break
                    if not self._mesh.renew_run(cid):
                        self._release_queued(cid, queued)
                        self._mesh.end_run(cid)
                        break
                    text, attachments, resume, sender = self._queued_input(queued)
                    current_queue_item = queued
                    from_queue = True
                    continue
                # 取消优先：用户点了停止就不能再续跑。
                # 不判它会死循环 —— 取消位一经置位无人清除，而续跑判定只看目标状态，
                # 于是"起新一轮 → 新一轮开头立刻被取消 → 又续跑"会无限转下去，
                # CPU 打满、事实与 SSE 一起被灌爆，界面上"停止"等于没按。
                if self._is_canceled(cid):
                    self._mesh.end_run(cid)
                    break
                self._mesh.end_run(cid)
                nxt_text = self._claim_goal_turn(cid, _auto_rounds)
                if nxt_text is None:
                    break
                _auto_rounds += 1
                text = nxt_text
                attachments = None
                resume = None
                sender = None
        except Exception as exc:  # 兜底：释放占位（不续跑）
            self._mesh.abort_run(cid)
            report_error("shell.session_runner", exc, conversation_id=cid, where="aborted")
        finally:
            stop_beat.set()
            # 会话终点必须补投一次：`SessionStore.flush_pending` 只在
            # 下一次 `append` 时才顺带补投，收尾那一趟之后不会再有 `append`。
            # 不补投的话，某一趟落盘失败的事实就永远留在积压里，
            # 进程退出即彻底丢失。
            self._flush_pending(cid)
            with self._lock:
                if self._threads.get(cid) is threading.current_thread():
                    self._threads.pop(cid, None)
                self._cancels.pop(cid, None)

    def _claim_goal_turn(self, cid: str, auto_rounds: int) -> Optional[str]:
        text = self._next_continuation_text(cid)
        if not text:
            return None
        if auto_rounds >= _MAX_AUTO_ROUNDS:
            print(f"[session_runner] 自动轮次已达上限 {_MAX_AUTO_ROUNDS}，暂停续跑 "
                  f"cid={cid}", file=sys.stderr, flush=True)
            return None
        if not self._mesh.try_begin_run(cid):
            return None
        self._note_goal_round(cid)
        return text

    def _cancel_pending_for_new_input(self, cid: str) -> str:
        contexts = getattr(self._app, "session_contexts", None)
        if contexts is None:
            return ""
        session = contexts.resolve_sync(cid)
        pending = getattr(session, "pending_confirm", None)
        if not isinstance(pending, dict):
            return ""
        call_id = str(pending.get("call_id") or "").strip()
        if not call_id:
            return ""
        session.pending_confirm = None
        return call_id

    def _is_paused(self, cid: str) -> bool:
        contexts = getattr(self._app, "session_contexts", None)
        if contexts is None:
            return False
        session = contexts.resolve_sync(cid)
        return bool(getattr(session, "pending_confirm", None))

    def _queue(self) -> Any:
        return getattr(self._app, "conversation_queue", None)

    def _claim_queued(self, cid: str) -> Any:
        queue = self._queue()
        return queue.claim_after_turn(cid) if queue is not None else None

    def _release_queued(self, cid: str, item: Dict[str, Any]) -> None:
        queue = self._queue()
        if queue is not None:
            queue.release(cid, str(item.get("id") or ""))

    def _complete_queued(self, cid: str, item: Dict[str, Any]) -> None:
        queue = self._queue()
        if queue is not None:
            queue.complete(cid, str(item.get("id") or ""))

    def _queued_input(self, item: Dict[str, Any]) -> Any:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        content = str(item.get("content") or payload.get("content") or "")
        attachments = item.get("attachments") or payload.get("attachments")
        if isinstance(attachments, list):
            attachments = [row for row in attachments
                           if not isinstance(row, dict) or "data_base64" in row]
        resume = payload.get("resume")
        sender = item.get("sender") if isinstance(item.get("sender"), dict) else None
        return content, attachments, resume, sender

    def _flush_pending(self, cid: str) -> None:
        """把该会话积压的待重试事实补投出去（失败只留痕，不影响收尾）。"""
        store = getattr(self._app, "store", None)
        flusher = getattr(store, "flush_pending", None)
        if not cid or not callable(flusher):
            return
        try:
            written = flusher(cid)
        except Exception as exc:
            print(f"[session_runner] 待重试事实补投失败 cid={cid}: "
                  f"{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            return
        if written:
            print(f"[session_runner] 补投了 {written} 条先前落盘失败的事实 "
                  f"（cid={cid}）", file=sys.stderr, flush=True)

    def _is_canceled(self, cid: str) -> bool:
        """该会话是否已被请求停止。"""
        with self._lock:
            event = self._cancels.get(cid)
        return bool(event is not None and event.is_set())

    def _note_goal_round(self, cid: str) -> None:
        """给目标记一轮自动推进（供界面显示"已自动推进 N 轮"）。"""
        state = getattr(self._app, "live_state", None)
        note = getattr(state, "note_goal_round", None)
        if not callable(note):
            return
        try:
            note(cid)
        except Exception:
            # 计数只用于展示，记不上不影响续跑。
            pass

    def _next_continuation_text(self, cid: str) -> str:
        """回合结束后该自动发的下一条 user 输入；空串 = 到此为止。

        目标优先且目标说了算：只要这个会话有目标，触发与否完全由它的状态决定
        （`active` 发文案、`paused`/`done` 停），不叠加自主开关 ——
        否则暂停会被自主开关顶回去。
        没有目标时才回落到自主开关 + `AUTO_CONTINUE_PROMPT`。
        """
        if self._goal_row is not None:
            row = self._goal_row(cid)
            if isinstance(row, dict):
                if str(row.get("status") or "") != "active":
                    return ""
                return str(row.get("text") or "").strip()
        return AUTO_CONTINUE_PROMPT if self._should_auto_continue(cid) else ""

    def _should_auto_continue(self, cid: str) -> bool:
        """自主模式：回合结束后是否再自动跑一轮。"""
        if self._auto_continue is None:
            return False
        return bool(self._auto_continue(cid))

    def _execute(self, cid: str, text: str, attachments: Any = None,
                 resume: Any = None, sender: Optional[Dict[str, Any]] = None,
                 from_queue: bool = False) -> bool:
        """执行单个回合：迭代事件至尽（回合过）；注入停止检查。

        `resume` 非空时（外部结果回灌）：先把结果写成 `tool_result` 事实，
        再跑回合。写法就是"拼接到上下文末尾"——这一刻上下文末端正好是那次工具调用，
        拼上去恰好是 `…assistant(tool_calls) → tool`（天然对齐，模型 API 才接受）。

        resume 的结果事实由运行器写入 store：运行器是回合的所有者，
        它清楚"什么时候该写、下一位读者是谁"。写前查重是硬要求——拼接没有幂等性，
        同一 `call_id` 交两次会产生两条 `tool` 消息（模型 API 直接拒绝）。
        """
        if isinstance(resume, dict):
            self._splice_resume(cid, resume)
        engine = self._app.session(
            cid,
            system_prompt=self._system_prompt(cid),
            mode_note=self._mode_note(cid),
            cancel=self._cancel_check(cid),
        )
        paused = False
        for event in engine.start_turn(text, attachments=attachments,
                                       sender=sender, from_queue=from_queue):
            if str(getattr(event, "type", "")) == "turn_ended":
                paused = bool((getattr(event, "data", None) or {}).get("paused"))
        return paused

    def _splice_resume(self, cid: str, resume: Dict[str, Any]) -> None:
        """把外部结果拼进会话事实（写前查重；失败不抛，回合照跑）。"""
        store = getattr(self._app, "store", None)
        call_id = str(resume.get("call_id") or "")
        if store is None or not call_id:
            return
        try:
            ok = bool(resume.get("ok", True))
            existing = {str((e.data or {}).get("call_id") or "")
                        for e in store.load(cid)
                        if e.type in ("tool_done", "tool_failed")}
            if call_id in existing:
                return                      # 已交付过：不重复拼（幂等由这里保证）
            # 结果事实必须用内核当前认的名字：内核把 `tool_done` / `tool_failed`
            # 攒成"这次调用的结果"，再由随后的 `tool_ended` 取出交给模型。
            # 若写成别的名字，`tool_ended` 取不到结果 → 模型收到
            # 「已结束，但未记录结果」，而且要等这条被单独算作一条 tool 消息，
            # 同一个 `tool_call_id` 就有了两条 —— 模型 API 直接 400。
            name = str(resume.get("name") or "")
            # 结果事实本身不进模型上下文，要靠紧随的 tool_ended 收成 tool 消息。
            # 挂起时已经有过一条 status=suspended 的终态，那条不产出消息；
            # 这里再补一条 done/failed，模型才能看见用户的选择或取消。
            store.append(cid, [
                Event("tool_done" if ok else "tool_failed", {
                    "call_id": call_id,
                    "name": name,
                    "data": resume.get("data"),
                    "error": str(resume.get("error") or ""),
                }),
                Event("tool_ended", {
                    "call_id": call_id,
                    "name": name,
                    "status": "done" if ok else "failed",
                    "elapsed_ms": 0,
                }),
            ])
        except Exception as exc:
            print(f"[session_runner] resume 拼接失败 cid={cid}: {exc}",
                  file=sys.stderr, flush=True)

    def _system_prompt(self, cid: str) -> str:
        """系统提示：mesh 显式设过就用它，否则基础提示词（含工具速查）。

        系统提示必须有内容：只读 mesh 的 `system` 时它常为空串，
        模型便只知工具 schema、不知使用纪律。

        不含模式段：模式由 `_mode_note` 单独产出、只附加在请求尾部，
        这样切模式不会改动这一段，前缀缓存不失效。
        """
        meta = self._mesh.get_agent(cid)
        explicit = str(meta.get("system") or "")
        state = getattr(self._app, "live_state", None)
        mode = state.get_mode(cid) if state is not None else "auto"
        extra = (self._prompt_sections.render(cid)
                 if self._prompt_sections is not None else None)
        return resolve_system_prompt(
            mode=mode,
            registry=getattr(self._app, "registry", None),
            explicit=explicit or None,
            extra_sections=extra,
        )

    def _mode_note(self, cid: str) -> str:
        """请求尾部要附加的执行模式说明（临时；不落记录、不发事件）。"""
        meta = self._mesh.get_agent(cid)
        explicit = str(meta.get("system") or "")
        state = getattr(self._app, "live_state", None)
        mode = state.get_mode(cid) if state is not None else "auto"
        note = resolve_mode_note(mode=mode, explicit=explicit or None)
        prompt_tail = getattr(self._app, "prompt_tail", None)
        extra = prompt_tail.render(cid).strip() if prompt_tail is not None else ""
        return note + ("\n\n" + extra if extra else "")

    # ── 等待（测试 / 壳层）────────────────────────────────

    def wait_idle(self, cid: str, timeout: float = 10.0) -> bool:
        """等待 cid 无活跃运行（含队列抽干链）；超时返回 False。"""
        key = str(cid or "").strip()
        deadline = time.time() + max(0.0, float(timeout))
        while True:
            if not self._mesh.is_running(key):
                return True
            if time.time() >= deadline:
                return False
            with self._lock:
                thread = self._threads.get(key)
            if thread is not None:
                thread.join(max(0.01, deadline - time.time()))
            else:
                time.sleep(0.01)
