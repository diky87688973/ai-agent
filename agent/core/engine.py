# -*- coding: utf-8 -*-
"""引擎外观（`Engine`）：把模块链包成壳层要的"开始回合 / 事件流"两面。

壳层（`shell/`）只认两件事：`start_turn(text) -> Iterator[Event]`，以及一个能读的
事实日志 `log`。这个类把 `Host` + 模块链包成那个形状。

刻意保持的形状：

1. 回合逻辑在模块里、回合边界在宿主里；引擎只做装配与转发
   （`turn_started` / `turn_ended` 都是宿主的职责，定义在 `host.py` 顶部）。
2. 恢复靠事实：结果已经拼进日志，壳层只要把新事实写进日志/存储，
   恢复自然成立 —— 不靠内存里的游标。

事件唯一出口：模块事件与宿主事件都经宿主的 `sink` 出来，引擎在那里把它旁路给
`event_sink`（事件总线 → UI 适配层）。另开一条只进不出的缓冲会让观察面收不到宿主
事件（`turn_ended` 到不了适配层，界面一直"思考中"）。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Iterator, List, Optional

from agent.core.error_report import report_error
from agent.core.events import Event
from agent.core.host import MAX_PASSES_DEFAULT, Host, TurnResult
from agent.core.image_embed import KEEP_IMAGE_TURNS, MAX_EMBED_IMAGES
from agent.core.module import ModuleBase
from agent.core.modules import InputModule, build_default_chain
from agent.core.ports import ModelPort, ToolPort
from agent.core.session_log import SessionLog


class Engine:
    """会话引擎：一会话一实例。"""

    def __init__(
        self,
        *,
        conversation_id: str,
        log: Optional[SessionLog] = None,
        provider: Any = None,
        registry: Any = None,
        pipeline: Any = None,
        context: Any = None,
        compactor: Any = None,
        queued_input: Any = None,
        effort: str = "high",
        model: str = "",
        image_turns: int = KEEP_IMAGE_TURNS,
        image_max: int = MAX_EMBED_IMAGES,
        mode_note: str = "",
        modules: Optional[List[ModuleBase]] = None,
        input_module: Optional[InputModule] = None,
        max_passes: int = MAX_PASSES_DEFAULT,
        fact_sink: Optional[Callable[[List[Event]], None]] = None,
        event_sink: Optional[Callable[[Event], None]] = None,
        session_context: Any = None,
        cancel: Any = None,
        seq_allocator: Any = None,
        app_context: Any = None,
        session_contexts: Any = None,
    ) -> None:
        self.conversation_id = str(conversation_id or "")
        self.log = log if log is not None else SessionLog()
        self.provider = provider
        self.registry = registry
        self.pipeline = pipeline
        self.fact_sink = fact_sink
        # 事件旁路（观察面）：经典 UI 适配层靠它拿到实时事件流。
        # 没有它，整个 UI 收不到任何东西（界面永远"思考中"，
        # 因为适配层永远不产生 `done` 帧）。
        self.event_sink = event_sink
        # 会话上下文（装配方给了才有）：挂起信息记在这里——它要跨回合存活，
        # 宿主（UI 适配层）靠它拿到 `call_id`，把用户的选择交回来。
        self.session_context = session_context
        # 停止检查：宿主与模块在检查点问它是否该停。
        self.cancel = cancel
        #: 全局存储坐标分配器（装配方注入 `store.allocate_seq`）。
        #: 没有它，所有帧都不带 `id:` → 浏览器不回传 `Last-Event-ID`
        #: → 断线续传整条路径静默失效（帧带坐标 0/10）。
        self.seq_allocator = seq_allocator
        self.model_port = ModelPort(provider) if provider is not None else None
        self.tool_port = (
            ToolPort(
                registry=registry,
                pipeline=pipeline,
                app=app_context,
                sessions=session_contexts,
            )
            if registry is not None and pipeline is not None
            else None
        )
        self._input = input_module if input_module is not None else InputModule()
        # 宿主的出口就是引擎的旁路：唯一出口，模块事件与宿主事件都从这里出去。
        self._host = Host(
            modules if modules is not None
            else build_default_chain(input_module=self._input, context=context,
                                     compactor=compactor, queued_input=queued_input,
                                     effort=effort, model=model,
                                     image_turns=image_turns, image_max=image_max,
                                     mode_note=mode_note),
            sink=self._on_event,
            max_passes=max_passes,
            on_pass_end=self._flush_facts,
            seq_allocator=seq_allocator,
        )
        # 本回合尚未落盘的事实。按趟增量清空（见 `_flush_facts`）：
        # 攒到回合末尾的话，中途异常会把整回合的事实一起丢掉，
        # 而界面已经渲染过了（刷新即消失，连用户发言一起丢）。
        self._turn_events: List[Event] = []
        self.last_result: Optional[TurnResult] = None

    # ── 事件流 ─────────────────────────────────────────────

    def _on_event(self, event: Event) -> None:
        """宿主/模块的唯一出口：记下本回合事实，并旁路给观察面。"""
        self._turn_events.append(event)
        self._remember_suspend(event)
        if self.event_sink is None:
            return
        try:
            self.event_sink(event)
        except Exception as exc:
            # 旁路纪律：观察者异常不影响回合，但必须留痕（对齐 _remember_suspend）。
            report_error(
                "core.event_sink",
                exc,
                conversation_id=self.conversation_id,
                event_type=getattr(event, "type", None),
            )

    def _remember_suspend(self, event: Event) -> None:
        """把挂起信息记进会话上下文（宿主作答时靠 `call_id` 把结果交回来）。

        记在会话级而不是回合级：它要跨回合存活（挂起在上一回合、作答在下一回合）。
        """
        if self.session_context is None:
            return
        try:
            if event.type == "tool_suspended":
                envelope = (event.data or {}).get("envelope")
                envelope = envelope if isinstance(envelope, dict) else {}
                kind = str(envelope.get("kind") or "confirm")
                pending = {
                    "call_id": str((event.data or {}).get("call_id") or ""),
                    "kind": kind,
                    "title": str(envelope.get("title") or ""),
                    "options": [str(x) for x in (envelope.get("confirms") or [])],
                    "multi": bool(envelope.get("multi")),
                }
                if kind == "approval":
                    pending["option_id"] = str(envelope.get("option_id") or "")
                    pending["option_desc"] = str(envelope.get("option_desc") or "")
                self.session_context.pending_confirm = pending
            elif event.type == "turn_ended" and not bool((event.data or {}).get("paused")):
                self.session_context.pending_confirm = None   # 已消费，清掉
        except Exception as exc:
            # 不能静默：这里失败的症状是"UI 不弹确认"，从现象完全看不出是
            # 挂起状态没记上。吞掉异常保住回合，但必须把原因留痕。
            report_error(
                "core.suspend",
                exc,
                conversation_id=self.conversation_id,
            )

    def _flush_facts(self) -> None:
        """把尚未落盘的本回合事实写出去，然后清空待写列表。

        按趟调用（宿主的 `on_pass_end`），好处是批量与崩溃安全兼得：
        单次写盘摊到一整趟的事实上，而中途异常最多丢当前这一趟。
        攒到回合末尾一次写：门控在工具执行时抛异常的话，
        界面已渲染完整对话，而存储里一个字都没有、`/api/chat/history` 为空、
        刷新即消失（连用户发言一起丢）；已完成工具的事实丢失还会让
        下一轮重跑同一调用（重复副作用）。

        `SessionStore.append` 是原子的（追加前记偏移，失败 `truncate` 回滚），
        这一点是前提：若它逐行写，半写后重试整批会产生重复行与重复坐标。
        """
        if self.fact_sink is None or not self._turn_events:
            return
        batch = list(self._turn_events)
        self._turn_events.clear()          # 先清再写：写失败也不重复写已写的
        try:
            self.fact_sink(batch)
        except Exception as exc:
            # 重试由 `SessionStore` 的待重试队列承担 —— 重试的唯一归属是 `SessionStore` 的待重试队列
            # （`SessionStore._write_rows` 失败时把整批收进 `self._pending[cid]`，
            # 下次 `append` 先补投它）。
            #
            # 引擎这里放回 `_turn_events` 之后，同一批事实会被重新渲染一遍
            # （`_seq` 也重新分配）→ 磁盘上出现重复行与重复坐标。
            #
            # 真实路径每回合 `App.session(cid)` 新建引擎：挂在引擎上的批次会随
            # 引擎一起被 GC，用户发言永久丢失。store 跨回合、跨引擎实例存活，
            # 而 store 是落盘的唯一入口。
            #
            # 观察面（浏览器）已经收到并渲染了这些事实，所以必须留痕，
            # 不能静默 —— 重连读历史会读不到它们（等下一次 append 补投）。
            report_error(
                "core.fact_sink",
                exc,
                conversation_id=self.conversation_id,
                batch_size=len(batch),
            )

    def start_turn(self, user_text: str, attachments: Any = None,
                   sender: Any = None, from_queue: bool = False) -> Iterator[Event]:
        """跑一个回合，边跑边产出事实（保实时流语义）。

        顺序保证：事件由宿主/模块先入日志再出事件流，所以消费者看到的事实
        都已在日志里（断线重连能重放出来）。

        流式靠 `Host.run_iter`：宿主在事件产出那一刻就让出控制权，本生成器逐个吐。
        """
        atts = list(attachments) if isinstance(attachments, (list, tuple)) else []
        self._input.feed(str(user_text or ""), atts, sender=sender,
                          from_queue=from_queue)

        # 开新回合：就地清空上一回合没来得及落盘的事实（`clear()`，不重绑字段）。
        self._turn_events.clear()

        # `try/finally`：无论回合怎么结束都落盘。异常从模块链逃出来
        # （门控 / post 观察者抛异常会穿透 `ToolPipeline.execute`）时，
        # 之前攒的事实也要写下去——否则用户发言都保不住。
        try:
            for event in self._host.run_iter(
                log=self.log,
                conversation_id=self.conversation_id,
                model=self.model_port,
                tools=self.tool_port,
                cancel=self.cancel,
            ):
                yield event
        finally:
            self.last_result = self._host.last_result
            # 兜底：宿主每趟已经增量落过盘，这里写下最后一趟尚未落盘的部分。
            self._flush_facts()

    # ── 诊断与旁路 ─────────────────────────────────────────

    @property
    def paused(self) -> bool:
        """本轮是否停在"等外部输入"（挂起是终态，不是阻塞态）。"""
        return bool(self.last_result is not None and self.last_result.paused)

    def describe(self) -> Dict[str, Any]:
        """装配信息（`/health` 用）。"""
        return {
            "kernel": "core",
            "conversation_id": self.conversation_id,
            "modules": self._host.describe(),
            "max_passes": self._host.max_passes,
        }
