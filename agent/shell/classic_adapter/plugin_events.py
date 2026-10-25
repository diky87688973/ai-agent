# -*- coding: utf-8 -*-
"""插件事件发布器：把插件产生的非事实帧送到经典界面 SSE。

薄适配层，只暴露两个能力：

- `__call__(plugin, event, payload)` → 实际送达的连接数；
- `connected()` → 当前是否有 SSE 连接。

插件经 `SERVICE_PLUGIN_EVENTS` 取用，不 import 壳层实现。
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class PluginEventPublisher:
    """`ClassicAdapter.announce_plugin_event` 的窄接口。"""

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter

    def __call__(self, plugin: str, event: str,
                 payload: Optional[Dict[str, Any]] = None) -> int:
        return int(self._adapter.announce_plugin_event(plugin, event, payload))

    def connected(self) -> bool:
        return int(getattr(self._adapter, "channel_count", 0) or 0) > 0


__all__ = ["PluginEventPublisher"]
