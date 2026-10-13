# -*- coding: utf-8 -*-
"""事件总线（旁路）— 双轨机制之一，只做通知不参与控制流。

纪律：
- 纯通知，不参与控制流：订阅者异常被隔离（记录到 stderr），不影响主流程与其他订阅者；
- 按事件类型订阅；subscribe 返回幂等 disposer；
- 分发用快照遍历（分发过程中订阅/退订安全）；
- `subscribe_all` 为通配订阅（全类型）——SSE 多路复用等"观察一切"的消费者使用。
"""
from __future__ import annotations

import sys
import threading
from typing import Callable, Dict, List

from agent.core.events import Event

Handler = Callable[[Event], None]
ALL_EVENTS = "*"  # 通配订阅键


class EventBus:
    """发布/订阅总线：事件类型 → 订阅者列表（旁路，纯通知）。"""

    def __init__(self) -> None:
        self._subs: Dict[str, List[Handler]] = {}
        self._lock = threading.Lock()

    def subscribe(self, event_type: str, handler: Handler) -> Callable[[], None]:
        """订阅指定类型事件；返回幂等 disposer。"""
        key = str(event_type or "").strip()
        if not key:
            raise ValueError("事件类型不能为空")
        if not callable(handler):
            raise ValueError("handler 必须可调用")
        with self._lock:
            self._subs.setdefault(key, []).append(handler)

        def _dispose() -> None:
            with self._lock:
                handlers = self._subs.get(key)
                if not handlers or handler not in handlers:
                    return
                handlers.remove(handler)
                if not handlers:
                    self._subs.pop(key, None)

        return _dispose

    def subscribe_all(self, handler: Handler) -> Callable[[], None]:
        """订阅全部类型事件（通配）；返回幂等 disposer。

        用于"观察一切"的消费者（如 SSE 多路复用流）；与 `subscribe` 共用同一注册表，
        分发纪律一致（异常隔离、快照遍历）。
        """
        return self.subscribe(ALL_EVENTS, handler)

    def publish(self, event: Event) -> None:
        """分发事件：逐个调用订阅者；单个异常不阻断其余（旁路安全）。

        先派发通配订阅者，再派发该类型的订阅者（同批快照遍历，顺序稳定）。
        """
        key = str(getattr(event, "type", "") or "")
        with self._lock:
            handlers = list(self._subs.get(ALL_EVENTS, ())) + list(self._subs.get(key, ()))
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                print(
                    f"[event_bus] 订阅者异常（已隔离）{key}: {type(exc).__name__}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )

    def dispose_all(self) -> None:
        """清空全部订阅。"""
        with self._lock:
            self._subs.clear()
