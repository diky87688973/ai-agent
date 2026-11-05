# -*- coding: utf-8 -*-
"""插件事件出口：插件经此推送 SSE 事件（非事实帧）。"""
from __future__ import annotations

from typing import Any

from agent.core.context import SERVICE_PLUGIN_EVENTS
from agent.core.error_report import report_error


def publish_plugin_event(app: Any, name: str, event: str,
                         payload: Any = None) -> int:
    """推送插件 SSE 事件（非事实帧）；App 未接入出口时返回 0。

    插口 factory 都要推事件，取服务、绑插件名、吞错误这三步只在这里实现一次。
    """
    context = getattr(app, "context", None) if app is not None else None
    if context is None or not context.has(SERVICE_PLUGIN_EVENTS):
        return 0
    publisher = context.get(SERVICE_PLUGIN_EVENTS)
    try:
        return int(publisher(str(name or ""), str(event or ""), payload or {}))
    except Exception as exc:
        report_error("agent.capabilities.plugin_events.publish_event", exc)
        return 0
