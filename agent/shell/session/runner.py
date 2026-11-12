# -*- coding: utf-8 -*-
"""会话运行器：后台执行会话回合，消费会话待发送队列。

- 装配为 MeshState 激活器（activator）：闲时直启、忙时由 mesh 排队；
- 生命周期：try_begin_run（原子占位）→ 线程执行回合 → end_run（释放 + 队列抽干）；
- 单回合失败不打断抽干链；异常兜底释放占位并告警；wait_idle 供测试 / 壳层等待；
- 身份块经 system_prompt 注入通道进入上下文，不写初始事件流。
"""
from __future__ import annotations

import threading
import time
from contextlib import nullcontext
from typing import Any, Callable, Dict, Optional

from agent.core.error_report import report_error
from agent.core.thread_context import thread_with_context
from agent.mechanisms.live_state import GOAL_DEFAULT_MAX_ROUNDS, GOAL_MAX_ROUNDS_CAP
from agent.shell.session import goal, heartbeat, prompt, queue
from agent.shell.session import resume as resume_module

# 运行态心跳的间隔（秒）：远小于 `RunRegistry` 的存活期（默认 900 秒），
# 又不会有任何可观测开销（一次小文件写入）。
_HEARTBEAT_INTERVAL_SECONDS = 60.0

#: 目标/自主自动续跑的回合数上限：兜底防止"目标写歪 → 无限烧 token"。
#: 用户重新发消息会重置这个链（新回合 runner），所以正常使用不受影响。
_MAX_AUTO_ROUNDS = GOAL_DEFAULT_MAX_ROUNDS

INSERT_NONE = "none"
INSERT_STOP = "stop"
INSERT_READY = "ready"



class SessionRunner:
    """后台回合运行器：以 mesh 活跃集为唯一忙闲事实源。

    `auto_continue`：注入的判断函数（cid → bool）。回合结束后若为真，则自动再跑一个回合
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
        store_for: Optional[Callable[[str], Any]] = None,
        registry_for: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self._app = app
        self._mesh = mesh
        self._auto_continue = auto_continue
        self._goal_row = goal_row
        self._prompt_sections = prompt_sections
        self._store_for = store_for or (lambda _cid: None)
        self._registry_for = registry_for or (lambda _cid: None)
        self._lock = threading.Lock()
        self._threads: Dict[str, threading.Thread] = {}
        self._cancels: Dict[str, threading.Event] = {}  # cid → 取消信号（协作式）
        self._closed = False

    def set_store_for(self, store_for: Optional[Callable[[str], Any]]) -> None:
        self._store_for = store_for or (lambda _cid: None)

    def set_registry_for(self, registry_for: Optional[Callable[[str], Any]]) -> None:
        self._registry_for = registry_for or (lambda _cid: None)

    # ── 激活入口（装配到 MeshState.set_activator）──────────

    def start(self, cid: str, message: Dict[str, Any], *,
              queued: Optional[Dict[str, Any]] = None) -> str:
        """启动一个后台回合；占位失败（忙）返回空串（由 mesh 回退入队）。

        `message` 可带：
        - `content`：用户文本；
        - `attachments`：随本回合注入模型请求的附件；
        - `resume`：外部结果回灌——形如
          `{"call_id": ..., "ok": True, "data": ...}`。带它时这一回合没有用户发言，
          运行器先把结果写成 `tool_result` 事实，再跑回合让模型消费它。
        """
        key = str(cid or "").strip()
        with self._lock:
            if self._closed:
                return ""
        queued = queued if queued is not None else message.get("_queued_item")
        resuming = bool((queued or {}).get("_resume_inbox"))
        rid = self._mesh.try_begin_run(key)
        if not rid:
            return ""
        if queued is not None:
            text, attachments, resume, sender, meta = self._queued_input(queued)
        else:
            text = str(message.get("content") or "")
            attachments = message.get("attachments")
            resume = message.get("resume")
            meta = message.get("meta") if isinstance(message.get("meta"), dict) else {}
            sender = message.get("sender") if isinstance(message.get("sender"), dict) else None
            if sender is None and str(message.get("_sender") or "").strip():
                sender = {
                    "cid": str(message.get("_sender") or "").strip(),
                    "name": str(message.get("_sender_name") or "").strip(),
                }
        cancel_event = threading.Event()
        with self._lock:
            self._cancels[key] = cancel_event
        try:
            thread = thread_with_context(
                target=self._run_loop,
                args=(key, text, attachments, resume, sender, meta, queued, resuming),
                name=f"fan-mesh-{key[:12]}",
                daemon=True,
            )
            with self._lock:
                self._threads[key] = thread
            thread.start()
        except Exception as exc:
            # 占位已成功但线程没起来：不释放的话这个会话永远显示在跑，
            # 后续投递全被判忙、停止键也没有对应线程可停。
            with self._lock:
                self._threads.pop(key, None)
                self._cancels.pop(key, None)
            self._mesh.abort_run(key)
            report_error("shell.session_runner.start", exc, conversation_id=key)
            return ""
        return rid

    # ── 协作式取消 ───────────────────────────────────────

    def request_cancel(self, cid: str) -> bool:
        """Stop an active turn or settle an idle confirmation."""
        key = str(cid or "").strip()
        with self._lock:
            event = self._cancels.get(key)
        store = self._store_for(key) or getattr(self._app, "store", None)
        if event is None:
            return resume_module.interrupt_confirmation(
                self._app, key, store, on_pending=lambda: self._mesh.mark_stopped(key))
        self._mesh.mark_stopped(key, cancel=event)
        try:
            resume_module.interrupt_confirmation(self._app, key, store)
        except OSError as exc:
            report_error("shell.session_runner.cancel_confirmation", exc, conversation_id=key)
        return True

    def _cancel_check(self, cid: str):
        """给内核的停止检查（内核 `cancel` 参数的注入位）。"""

        with self._lock:
            event = self._cancels.get(cid)
        next_probe = 0.0
        stopped = False

        def check() -> bool:
            nonlocal next_probe, stopped
            if stopped or (event is not None and event.is_set()):
                return True
            now = time.monotonic()
            if now >= next_probe:
                # 跨进程停止靠磁盘标记，流式回调按时间间隔检查。
                next_probe = now + 0.1
                stopped = self._mesh.is_stopped(cid)
            return stopped

        return check

    # ── 回合执行与队列抽干 ────────────────────────────────

    def _heartbeat_until(self, cid: str, stop: threading.Event) -> None:
        heartbeat.heartbeat_until(
            mesh=self._mesh, cid=cid, stop=stop,
            interval=_HEARTBEAT_INTERVAL_SECONDS,
        )

    def _run_loop(self, cid: str, text: str, attachments: Any = None,
                  resume: Any = None, sender: Optional[Dict[str, Any]] = None,
                  meta: Any = None,
                  queued_item: Optional[Dict[str, Any]] = None, resuming: bool = False) -> None:
        stop_beat = self._start_heartbeat(cid)
        _auto_rounds = 0
        current_queue_item = queued_item
        from_queue = queued_item is not None
        paused = failed = False
        try:
            while True:
                paused = False
                if self._is_canceled(cid):
                    if current_queue_item is not None:
                        self._release_queued(cid, current_queue_item)
                    self._mesh.end_run(cid)
                    break
                try:
                    store = self._store_for(cid) or getattr(self._app, "store", None)
                    if queue.has_input(self._app, cid, text, attachments, resuming):
                        resume_module.interrupt_confirmation(self._app, cid, store)
                    if current_queue_item is not None and (resuming or queue.is_user_input(current_queue_item)):
                        if isinstance(resume, dict):
                            self._splice_resume(cid, resume)
                        queue.commit_user_input(cid, self._app, store, current_queue_item, batch=resuming)
                        current_queue_item = None
                        text, attachments, resume = "", None, None
                        meta = None if resuming else meta
                    paused = self._execute(cid, text, attachments, resume, sender,
                                           from_queue=from_queue, meta=meta)
                except Exception as exc:
                    report_error("shell.session_runner", exc, conversation_id=cid)
                    if current_queue_item is not None:
                        self._release_queued(cid, current_queue_item)
                    self._mesh.end_run(cid)
                    if isinstance(exc, OSError):
                        queue.notify_insert_failure(self._app, cid)
                    failed = True
                    break
                resuming = False
                if current_queue_item is not None:
                    self._complete_queued(cid, current_queue_item)
                    current_queue_item = None
                if self._is_canceled(cid) or paused or self._is_paused(cid):
                    self._mesh.end_run(cid)
                    break
                insert_state = self._insert_turn_state(cid)
                if insert_state == INSERT_STOP:
                    break
                if insert_state == INSERT_READY:
                    text, attachments, resume, sender, meta, from_queue = "", None, None, None, None, False
                    continue
                queued = self._claim_queued(cid)
                if queued is not None:
                    if self._is_canceled(cid) or not self._mesh.renew_run(cid):
                        self._release_queued(cid, queued)
                        self._mesh.end_run(cid)
                        break
                    text, attachments, resume, sender, meta = self._queued_input(queued)
                    current_queue_item = queued
                    from_queue = True
                    continue
                nxt_text = self._claim_goal_turn(
                    cid, _auto_rounds, renew=True, allow_insert=True)
                if nxt_text is None:
                    break
                if nxt_text:
                    _auto_rounds += 1
                text = nxt_text
                attachments = None
                resume = None
                sender = None
                meta = self._goal_followup_meta(cid) if nxt_text else None
        except Exception as exc:  # 兜底：释放占位（不续跑）
            failed = True
            self._mesh.abort_run(cid)
            report_error("shell.session_runner", exc, conversation_id=cid, where="aborted")
        finally:
            self._finish_run_loop(cid, stop_beat, failed=failed)

    def _finish_run_loop(self, cid: str, stop_beat: threading.Event, *, failed: bool) -> None:
        stop_beat.set()
        # 回合结束后可能没有下一次 append 负责补投失败的事实。
        self._flush_pending(cid)
        if self._mesh.is_stopped(cid):
            try:
                store = self._store_for(cid) or getattr(self._app, "store", None)
                resume_module.interrupt_confirmation(self._app, cid, store)
            except OSError as exc:
                report_error("shell.session_runner.finish_confirmation", exc, conversation_id=cid)
        with self._lock:
            if self._threads.get(cid) is threading.current_thread():
                self._threads.pop(cid, None)
                self._cancels.pop(cid, None)

        if not failed and not self._mesh.activate_inserts(cid):
            self._mesh.activate_queued(
                cid, lambda item: self.start(cid, {}, queued=item), user_only=self._is_paused(cid))

    def _start_heartbeat(self, cid: str) -> threading.Event:
        stop_beat = threading.Event()
        beater = thread_with_context(
            target=self._heartbeat_until, args=(cid, stop_beat),
            name=f"fan-mesh-beat-{cid[:12]}", daemon=True,
        )
        beater.start()
        return stop_beat

    def _insert_turn_state(self, cid: str) -> str:
        if self._is_canceled(cid):
            self._mesh.end_run(cid)
            return INSERT_STOP
        renewed = self._mesh.renew_for_insert(cid)
        if renewed is None:
            return INSERT_NONE
        if not renewed:
            self._mesh.end_run(cid)
            return INSERT_STOP
        return INSERT_READY

    def _claim_goal_turn(self, cid: str, auto_rounds: int, *, renew: bool = False,
                         allow_insert: bool = False) -> Optional[str]:
        """返回目标续跑文本；空串表示插入续跑；None 表示释放并停止。"""
        text = self._next_continuation_text(cid)
        if not text:
            if allow_insert and self._mesh.finish_or_continue_insert(cid):
                return ""
            return None
        if auto_rounds >= self._goal_limit(cid):
            report_error("shell.session_runner.goal_limit",
                         RuntimeError(f"自动轮次已达上限 {self._goal_limit(cid)}"),
                         conversation_id=cid)
            if allow_insert and self._mesh.finish_or_continue_insert(cid):
                return ""
            return None
        claimed = self._mesh.renew_run(cid) if renew else self._mesh.try_begin_run(cid)
        if not claimed:
            # 另一个回合同一时刻抢到运行位：目标续跑不能静默丢掉，
            # 转入会话队列，由当前回合计完后再抽干。
            self._queue_goal_followup(cid, text)
            return None
        self._note_goal_round(cid)
        return text

    def _is_paused(self, cid: str) -> bool:
        contexts = getattr(self._app, "session_contexts", None)
        if contexts is None:
            return False
        session = contexts.resolve_sync(cid)
        return bool(getattr(session, "pending_confirm", None))

    def _queue(self) -> Any:
        return queue.queue_of(self._app)

    def _claim_queued(self, cid: str) -> Any:
        return queue.claim(cid, self._app)

    def _release_queued(self, cid: str, item: Dict[str, Any]) -> None:
        queue.release(cid, item, self._app)

    def _complete_queued(self, cid: str, item: Dict[str, Any]) -> None:
        queue.complete(cid, item, self._app)

    def _queued_input(self, item: Dict[str, Any]) -> Any:
        return queue.input_of(item)

    def _flush_pending(self, cid: str) -> None:
        queue.flush_pending(cid, self._app)

    def _is_canceled(self, cid: str) -> bool:
        """该会话是否已被请求停止。"""
        with self._lock:
            event = self._cancels.get(cid)
        return bool(event is not None and event.is_set()) or self._mesh.is_stopped(cid)

    @staticmethod
    def _goal_round_note(meta: Any) -> str:
        if not isinstance(meta, dict) or meta.get("kind") != "goal_followup":
            return ""
        round_no = int(meta.get("goal_round") or 0)
        limit = int(meta.get("goal_limit") or _MAX_AUTO_ROUNDS)
        return (
            f"本轮是目标自动跟进第 {round_no}/{limit} 轮。"
            "轮数上限由宿主控制，不要尝试修改；接近上限时应先收敛并汇报进度。"
        )

    def _queue_goal_followup(self, cid: str, text: str) -> bool:
        queue_api = self._queue()
        if queue_api is None:
            return False
        meta = self._goal_followup_meta(cid) or {
            "kind": "goal_followup", "source": "goal", "goal_round": 0}
        try:
            queue_api.enqueue(
                cid, content=text, origin="system", delivery="after_turn",
                payload=dict(meta),
                dedupe_key=f"goal_followup:{cid}:{meta.get('goal_round', 0)}",
            )
            return True
        except Exception as exc:
            report_error("shell.session_runner.goal_queue", exc, conversation_id=cid)
            return False

    def _goal_limit(self, cid: str) -> int:
        if self._goal_row is None:
            return GOAL_DEFAULT_MAX_ROUNDS
        try:
            row = self._goal_row(cid)
        except Exception as exc:
            report_error("shell.session_runner.goal_limit", exc, conversation_id=cid)
            return GOAL_DEFAULT_MAX_ROUNDS
        if not isinstance(row, dict):
            return GOAL_DEFAULT_MAX_ROUNDS
        try:
            value = int(row.get("max_rounds") or GOAL_DEFAULT_MAX_ROUNDS)
        except (TypeError, ValueError):
            return GOAL_DEFAULT_MAX_ROUNDS
        return max(1, min(GOAL_MAX_ROUNDS_CAP, value))

    def _goal_followup_meta(self, cid: str) -> Any:
        if self._goal_row is None:
            return None
        try:
            row = self._goal_row(cid)
        except Exception as exc:
            report_error("shell.session_runner.goal_meta", exc, conversation_id=cid)
            return None
        if not isinstance(row, dict) or str(row.get("status") or "") != "active":
            return None
        return {"kind": "goal_followup", "source": "goal",
                "goal_round": int(row.get("rounds") or 0),
                "goal_limit": int(row.get("max_rounds") or GOAL_DEFAULT_MAX_ROUNDS)}

    def _note_goal_round(self, cid: str) -> None:
        goal.note_round(self._app, cid)

    def _next_continuation_text(self, cid: str) -> str:
        return goal.next_continuation_text(
            cid=cid, goal_row=self._goal_row, auto_continue=self._should_auto_continue,
        )

    def _should_auto_continue(self, cid: str) -> bool:
        return self._auto_continue is not None and bool(self._auto_continue(cid))

    def build_engine(self, cid: str, *, cancel: Any = None,
                     extra_system: str = "") -> Any:
        """构建一个完整上下文的会话引擎。

        Web、CLI、headless 共用同一份装配：系统提示词、插件章节、动态尾部
        与取消检查都在这里决定，调用方只负责 I/O 与生命周期。
        """
        system_prompt = self.system_prompt(cid)
        extra = str(extra_system or "").strip()
        if extra:
            system_prompt += "\n\n[附加指令]\n" + extra
        return self._app.session(
            cid,
            store=self._store_for(cid),
            registry=self._registry_for(cid),
            system_prompt=system_prompt,
            # 每趟重新求值：工具勾选后下一趟才能看到最新进度。
            mode_note=lambda: self.mode_note(cid),
            cancel=cancel,
        )

    def _execute(self, cid: str, text: str, attachments: Any = None,
                 resume: Any = None, sender: Optional[Dict[str, Any]] = None,
                 from_queue: bool = False, meta: Any = None) -> bool:
        """执行单个回合；引擎装配完成后再固定本轮 SlotSnapshot。"""
        continuation = (meta or {}).get("_confirmation_resume")
        if continuation:
            store = self._store_for(cid) or getattr(self._app, "store", None)
            if not resume_module.confirmation_can_resume(store, cid, *continuation):
                return False
        if isinstance(resume, dict):
            self._splice_resume(cid, resume)
            resume = None
        context = getattr(self._app, "context", None)
        lifecycle = getattr(context, "slot_lifecycle", None)
        with lifecycle.turn() if lifecycle is not None else nullcontext():
            engine = self.build_engine(
                cid, cancel=self._cancel_check(cid),
                extra_system=self._goal_round_note(meta))
            return self._execute_round(
                cid, text, attachments, sender, from_queue, meta, engine)

    def _execute_round(self, cid: str, text: str, attachments: Any = None,
                       sender: Optional[Dict[str, Any]] = None,
                       from_queue: bool = False, meta: Any = None,
                       engine: Any = None) -> bool:
        """执行单个回合：迭代事件至尽（回合过）；注入停止检查。

        `resume` 非空时（外部结果回灌）：先把结果写成 `tool_result` 事实，
        再跑回合。写法就是"拼接到上下文末尾"——这一刻上下文末端正好是那次工具调用，
        拼上去恰好是 `…assistant(tool_calls) → tool`（天然对齐，模型 API 才接受）。

        resume 的结果事实由运行器写入 store：运行器是回合的所有者，
        它清楚"什么时候该写、下一位读者是谁"。写前查重是硬要求——拼接没有幂等性，
        同一 `call_id` 交两次会产生两条 `tool` 消息（模型 API 直接拒绝）。
        """
        if engine is None:
            engine = self.build_engine(cid, cancel=self._cancel_check(cid))
        paused = False
        for event in engine.start_turn(text, attachments=attachments,
                                       sender=sender, from_queue=from_queue,
                                       meta=meta):
            if event.type == "turn_ended":
                paused = bool(event.data.get("paused"))
        if not paused or self._mesh.is_stopped(cid):
            store = self._store_for(cid) or getattr(self._app, "store", None)
            resume_module.interrupt_confirmation(self._app, cid, store)
        return paused

    def _splice_resume(self, cid: str, resume_data: Dict[str, Any]) -> None:
        resume_module.splice_resume(app=self._app, cid=cid, resume=resume_data)

    def registry_for(self, cid: str) -> Any:
        """当前会话的角色工具视图。"""
        return self._registry_for(cid)

    def system_prompt(self, cid: str) -> str:
        """当前会话的完整系统提示词（与 Web 回合使用同一份装配）。"""
        return self._system_prompt(cid)

    def mode_note(self, cid: str) -> str:
        """当前会话的动态请求尾部：模式、Todo 与插件尾部。"""
        return self._mode_note(cid)

    def _system_prompt(self, cid: str) -> str:
        return prompt.system_prompt(
            app=self._app, mesh=self._mesh, cid=cid,
            prompt_sections=self._prompt_sections,
            registry=self._registry_for(cid),
        )

    def _mode_note(self, cid: str) -> str:
        return prompt.mode_note(app=self._app, mesh=self._mesh, cid=cid)

    def shutdown(self, timeout: float = 5.0) -> bool:
        """停止接收新回合，取消并等待全部运行线程收尾。"""
        with self._lock:
            self._closed = True
            events = list(self._cancels.values())
            threads = list(self._threads.items())
        for event in events:
            event.set()
        current = threading.current_thread()
        deadline = time.time() + max(0.0, float(timeout))
        for _cid, thread in threads:
            if thread is current:
                continue
            thread.join(max(0.01, deadline - time.time()))
        with self._lock:
            alive = [cid for cid, thread in self._threads.items()
                     if thread is not current and thread.is_alive()]
        if alive:
            report_error("shell.session_runner.shutdown_timeout",
                         f"仍有 {len(alive)} 个回合线程未停止：{alive}",
                         conversation_id=alive[0])
            return False
        return True

    def wait_idle(self, cid: str, timeout: float = 10.0) -> bool:
        """等待 cid 无活跃运行并完成线程收尾；超时返回 False。"""
        key = str(cid or "").strip()
        deadline = time.time() + max(0.0, float(timeout))
        while True:
            with self._lock:
                thread = self._threads.get(key)
            alive = bool(thread is not None and thread.is_alive())
            if not self._mesh.is_running(key) and not alive:
                return True
            if time.time() >= deadline:
                return False
            if thread is not None:
                thread.join(max(0.01, deadline - time.time()))
            else:
                time.sleep(0.01)
