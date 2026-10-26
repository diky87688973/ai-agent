# -*- coding: utf-8 -*-
"""SSE 通道：连接队列、广播、心跳与断线续传。

每条连接一条队列（广播语义）：多个消费者共享一条队列会瓜分事件，
表现为"步骤卡不出现、用量不动"。

通道以宿主混入的形式提供，宿主（`ClassicAdapter`）需给出：
`_app`、`_lock`、`_channels`、`_bus`、`_unsubscribe`、`_last_beat`、
`_stream(cid)` 与 `feed(ev_type, data)`。
"""
from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any, Dict, List, Optional

import agent.shell.classic_adapter.contract as C
from agent.core.error_report import report_error

#: 单会话待发队列上限：超出丢最旧的（UI 丢几帧旧事件好过整个服务被拖死）
_QUEUE_MAX = 512

#: 一次续传最多补多少条历史事件。游标很旧时宁可分几批补，
#: 也不一次把上万条塞进一条连接的队列（队列是有界的，塞爆就是丢帧）。
_REPLAY_LIMIT = 512


class ChannelMixin:
    """SSE 连接与广播。"""

    _lock: "threading.Lock"
    _channels: List["queue.Queue[Dict[str, Any]]"]
    _bus: Any
    _unsubscribe: Optional[Any]
    _last_beat: float

    def _init_channels(self) -> None:
        """建立通道表与总线订阅状态（适配门面构造时调用一次）。"""
        self._lock = threading.Lock()
        # 每条 SSE 连接各自一条队列（广播）。
        self._channels = []
        self._bus = None
        self._unsubscribe = None
        self._last_beat = time.time()

    def bind_bus(self, event_bus: Any) -> None:
        """记下事件总线，先不订阅。

        订阅是按需的：有 SSE 连接进来才订阅、最后一个连接断开就摘掉（实现在
        `attach` / `detach`）。两个理由：
          1. 没有客户端时翻译纯属白做功；
          2. 常驻订阅会变成一条谁都回收不掉的泄漏——`plugin_host.unload_all()`
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
            except Exception as exc:
                report_error(
                    "agent.shell.classic_adapter.channel.ChannelMixin._drop_subscription", exc
                )

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
        """一条新 SSE 连接：给它一条独立队列，并在首条连接时开始订阅总线。

        顺序是先入列、后订阅：反过来的话，从入列到订阅之间的那几毫秒里
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
        """连接断开（刷新 / 关标签）：摘掉队列；最后一条断开时退订总线。"""
        with self._lock:
            if box in self._channels:
                self._channels.remove(box)
            last = not self._channels
        if last:
            self._drop_subscription()

    def next_frame(
        self,
        box: "queue.Queue[Dict[str, Any]]",
        timeout: float = 1.0,
    ) -> Optional[Dict[str, Any]]:
        """从指定通道取一帧；超时返回 None（SSE 层据此发心跳）。"""
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
        self._broadcast({"type": C.EV_PLUGINS_CHANGED, "loaded": names})

    def announce_model(self, cid: str, model: str) -> None:
        """把模型变化推给同会话的其它标签页（发起方已写过服务端）。

        与 `announce_plugins` 同构：不是内核事件，不伪装成内核事件。
        接收方只更新页头与本地 tab 字段，不再回写 `live_state`。
        """
        key = C.normalize_cid(cid)
        if not key:
            return
        self._broadcast({
            "type": C.EV_CONVERSATION,
            "conversation_id": key,
            "model": str(model or ""),
        })

    def announce_settings(self) -> int:
        """广播设置变更信号；值由各标签页自行拉取，不随广播下发。"""
        return self._broadcast({"type": C.EV_SETTINGS_CHANGED})

    def announce_plugin_config(self, plugin: str) -> int:
        """广播已成功保存的插件配置；所有标签页自行刷新。"""
        return self._broadcast({
            "type": C.EV_PLUGIN_CONFIG_CHANGED,
            "plugin": str(plugin or ""),
        })

    def announce_plugin_event(self, plugin: str, event: str,
                              payload: Optional[Dict[str, Any]] = None) -> int:
        """广播一条插件事件，返回实际送达的 SSE 连接数。"""
        return self._broadcast(C.plugin_event_frame(plugin, event, payload))

    def _broadcast(self, frame: Dict[str, Any]) -> int:
        """把一帧推给所有已连接通道；通道满则丢最旧，绝不阻塞事件流。"""
        with self._lock:
            channels = list(self._channels)
        self._push_frames(channels, [frame], drop_oldest=True)
        return len(channels)

    def _push_frames(
        self,
        channels: List["queue.Queue[Dict[str, Any]]"],
        frames: List[Dict[str, Any]],
        *,
        drop_oldest: bool,
    ) -> None:
        """按通道投递帧。

        `drop_oldest=True`：实时帧在队列满时丢最旧的一帧，绝不阻塞事件流；
        `drop_oldest=False`：续传帧放弃该通道的剩余帧——宁可少补历史，
        也不能把实时事件挤掉。
        """
        for box in channels:
            for frame in frames:
                try:
                    box.put_nowait(frame)
                except queue.Full:
                    if not drop_oldest:
                        break
                    try:
                        box.get_nowait()
                        box.put_nowait(frame)
                    except queue.Empty:
                        break

    # ── 续传（断线重连从游标继续）──────────────────────────

    def replay_after(self, after_seq: int, only: Any = None, limit: int = _REPLAY_LIMIT) -> int:
        """把 `seq > after_seq` 的历史事件翻成老事件、投进通道，返回投出的帧数。

        跨会话：坐标是全局单调的，所以一个游标对所有会话都成立——
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
        self._push_frames(channels, frames, drop_oldest=False)
        return len(frames)

    def latest_seq(self) -> int:
        """当前全局最大坐标；没有任何坐标时返回 -1。"""
        store = getattr(self._app, "store", None)
        if store is None or not hasattr(store, "_scan_max_seq"):
            return -1
        try:
            return int(store._scan_max_seq())
        except Exception as exc:
            report_error("agent.shell.classic_adapter.channel.ChannelMixin.latest_seq", exc)
            return -1

    def cursor_of(self, request_headers: Any, query: Dict[str, str]) -> int:
        """取本次连接的续传游标。

        优先 `Last-Event-ID` 请求头（浏览器 `EventSource` 自动带上的标准位置），
        其次 `?last_event_id=`（非浏览器客户端显式指定）；都没有则 -1（从头开始）。
        非整数一律当 -1：游标不可信时重放全量，比断在半路安全。
        """
        candidates: List[str] = []
        if query:
            candidates.append(str(query.get("last_event_id") or ""))
        if request_headers is not None:
            try:
                candidates.append(str(request_headers.get("Last-Event-ID") or ""))
            except Exception as exc:
                # 旁路，刻意吞掉：`Last-Event-ID` 是断线续传的可选请求头。
                # 取不到（headers 实现异常）就少一个候选坐标，下面的循环会用
                # URL 查询参数那一路兜底——续传能力降级，不影响本次订阅。
                report_error("agent.shell.classic_adapter.channel.ChannelMixin.cursor_of", exc)
        for raw in candidates:
            text = raw.strip()
            if not text:
                continue
            try:
                return int(text)
            except ValueError:
                return -1
        return -1


class ClassicSseChannel:
    """一条 SSE 连接的取帧循环（由 web.py 的 handler 驱动）。"""

    def __init__(self, adapter: Any, heartbeat: float = C.HEARTBEAT_SECONDS_DEFAULT) -> None:
        self.adapter = adapter
        self.heartbeat = float(heartbeat)
        self._last_sent = time.time()
        # 每条连接自己的队列：多标签页各自收到完整事件流（不能共享队列）
        self._box = adapter.attach()

    def close(self) -> None:
        self.adapter.detach(self._box)

    def resume(self, after_seq: int) -> int:
        """重连续传：把全局坐标 `> after_seq` 的事件补进本连接的队列。

        只补这一条连接（不广播）——别的连接没断，它们不需要补。
        """
        return self.adapter.replay_after(after_seq, only=self._box)

    def next_payload(self) -> str:
        """返回一帧的文本；空闲超时则发心跳。

        带 `seq` 的帧发两行：`id: <seq>` + `data: <json>`。SSE 原生的
        `id:` 行会让浏览器在断线重连时经 `Last-Event-ID` 把游标带回来，
        适配层据此续传——不必重放全部，也不会丢掉中间那段。
        """
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


__all__ = ["ChannelMixin", "ClassicSseChannel"]
