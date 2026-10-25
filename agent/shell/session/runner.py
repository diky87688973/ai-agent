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
from agent.shell.session import goal, heartbeat, prompt, queue, resume

# 运行态心跳的间隔（秒）：远小于 `RunRegistry` 的存活期（默认 900 秒），
# 又不会有任何可观测开销（一次小文件写入）。
_HEARTBEAT_INTERVAL_SECONDS = 60.0

#: 目标/自主自动续跑的轮数上限：兜底防止"目标写歪 → 无限烧 token"。
#: 用户重新发消息会重置这个链（新一轮 runner），所以正常使用不受影响。
_MAX_AUTO_ROUNDS = 50



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

    def set_store_for(self, store_for: Optional[Callable[[str], Any]]) -> None:
        self._store_for = store_for or (lambda _cid: None)

    def set_registry_for(self, registry_for: Optional[Callable[[str], Any]]) -> None:
        self._registry_for = registry_for or (lambda _cid: None)

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
        meta = message.get("meta") if isinstance(message.get("meta"), dict) else {}
        thread = threading.Thread(
            target=self._run_loop,
            args=(key, text, attachments, resume, sender, meta),
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
        heartbeat.heartbeat_until(
            mesh=self._mesh, cid=cid, stop=stop,
            interval=_HEARTBEAT_INTERVAL_SECONDS,
        )

    def _run_loop(self, cid: str, text: str, attachments: Any = None,
                  resume: Any = None, sender: Optional[Dict[str, Any]] = None,
                  meta: Any = None) -> None:
        # 运行态心跳由旁路线程周期性续期：这一趟从占位到释放可能持续很久，
        # 而 `RunRegistry` 用"心跳 + 存活期"判定在跑 —— 一次长工具调用
        # （`run_command` 跑 `ping -n 120`）期间没有心跳就会被误判成"已结束"，
        # 用户那边的停止键会消失。所以这里起一个轻量线程周期性续心跳。
        stop_beat = self._start_heartbeat(cid)
        # 因目标/自主而起的自动轮次计数，只用于兜底限流。
        _auto_rounds = 0
        current_queue_item = None
        from_queue = False
        try:
            while True:
                paused = False
                try:
                    paused = self._execute(cid, text, attachments, resume, sender,
                                           from_queue=from_queue, meta=meta)
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
                meta = None
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
                    text, attachments, resume, sender, meta = self._queued_input(queued)
                    current_queue_item = queued
                    from_queue = True
                    continue
                insert_state = self._insert_turn_state(cid)
                if insert_state == "stop":
                    break
                if insert_state == "ready":
                    text = ""
                    attachments = None
                    resume = None
                    sender = None
                    meta = None
                    from_queue = False
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
                meta = None
        except Exception as exc:  # 兜底：释放占位（不续跑）
            self._mesh.abort_run(cid)
            report_error("shell.session_runner", exc, conversation_id=cid, where="aborted")
        finally:
            self._finish_run_loop(cid, stop_beat)

    def _finish_run_loop(self, cid: str, stop_beat: threading.Event) -> None:
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

    def _start_heartbeat(self, cid: str) -> threading.Event:
        stop_beat = threading.Event()
        beater = threading.Thread(
            target=self._heartbeat_until, args=(cid, stop_beat),
            name=f"fan-mesh-beat-{cid[:12]}", daemon=True,
        )
        beater.start()
        return stop_beat

    def _insert_turn_state(self, cid: str) -> str:
        if not queue.has_inserting(self._app, cid):
            return "none"
        if self._is_canceled(cid):
            self._mesh.end_run(cid)
            return "stop"
        if not self._mesh.renew_run(cid):
            self._mesh.end_run(cid)
            return "stop"
        return "ready"

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
        return bool(event is not None and event.is_set())

    def _note_goal_round(self, cid: str) -> None:
        goal.note_round(self._app, cid)

    def _next_continuation_text(self, cid: str) -> str:
        return goal.next_continuation_text(
            cid=cid, goal_row=self._goal_row, auto_continue=self._auto_continue,
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
            # 每个 pass 重新求值：工具勾选后下一趟才能看到最新进度。
            mode_note=lambda: self.mode_note(cid),
            cancel=cancel,
        )

    def _execute(self, cid: str, text: str, attachments: Any = None,
                 resume: Any = None, sender: Optional[Dict[str, Any]] = None,
                 from_queue: bool = False, meta: Any = None) -> bool:
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
        engine = self.build_engine(cid, cancel=self._cancel_check(cid))
        paused = False
        for event in engine.start_turn(text, attachments=attachments,
                                       sender=sender, from_queue=from_queue,
                                       meta=meta):
            if str(getattr(event, "type", "")) == "turn_ended":
                paused = bool((getattr(event, "data", None) or {}).get("paused"))
        return paused

    def _splice_resume(self, cid: str, resume_data: Dict[str, Any]) -> None:
        resume.splice_resume(app=self._app, cid=cid, resume=resume_data)

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
        )

    def _mode_note(self, cid: str) -> str:
        return prompt.mode_note(app=self._app, mesh=self._mesh, cid=cid)

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
