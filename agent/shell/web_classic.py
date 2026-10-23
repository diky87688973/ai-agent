# -*- coding: utf-8 -*-
"""经典页面与 SSE 路由。"""
from __future__ import annotations

import json
from typing import Any, Dict

from agent.shell.service_keys import SERVICE_CLASSIC_ADAPTER
from agent.shell.web_ui_config import get_web_ui


class ClassicRoutes:
    server_version = "ai-agent-web/1.0"
    shell: Any

    def _classic(self) -> Any:
        """适配层实例；未装配时返回 None（旧页面仍可用）。"""
        app = getattr(self.shell, "app", None)
        if app is None or not hasattr(app, "context"):
            return None
        ctx = app.context
        if not hasattr(ctx, "has") or not ctx.has(SERVICE_CLASSIC_ADAPTER):
            return None
        return ctx.get(SERVICE_CLASSIC_ADAPTER)

    def _classic_page(self) -> None:
        """经典界面页面：把经典界面素材内联成单页返回。"""
        from agent.shell.ui_bundle import APP_VERSION, inline_ui_html

        html = inline_ui_html(APP_VERSION)
        # 开关按请求注入：素材缓存不含 ini，改 web-ui-config.ini 后刷新页面即生效。
        html = html.replace(
            "{{WEB_UI_JSON}}",
            json.dumps(get_web_ui(), ensure_ascii=False, separators=(",", ":")),
        )
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _classic_sse(self, query: Dict[str, str]) -> None:
        """事件流。两种格式任选，默认经典界面格式：

        - 默认（无 `format` 或 `format=classic`）：适配层翻译过的老事件
          （`conversation` / `tool_start` / `llm_round` …），经典 UI 用这条。
        - `format=kernel`：内核原生事件（`turn_started` / `tool_call` …）原样透传。
          给测试、运维探针，以及未来的其它交互层（命令行等）用——
          它们要的是内核事实，不是给经典界面的翻译结果。

        两条流分开：把内核事件名暴露成"另一套公开契约"会让适配层失去意义，
        但完全堵死原生事件又会让内核行为无法被直接观察。
        """
        if query.get("format") == "kernel":
            self._events_stream()
            return
        from agent.shell.classic_adapter.adapter import ClassicSseChannel

        classic = self._classic()
        if classic is None:
            self._json(503, {"error": "适配层未装配"})
            return
        channel = ClassicSseChannel(classic)
        # 断线续传：游标取 SSE 原生的 `Last-Event-ID`（浏览器自动带）或 `?last_event_id=`。
        # 坐标是全局单调的，所以一个游标就够了——不需要客户端告诉服务端"续哪个会话"，
        # 浏览器的 `EventSource` 也就无需任何定制。
        # 没有游标就不续传：经典界面各自 `GET /api/chat/history` 渲染已有内容，
        # 适配层再回放一遍就是重复气泡。
        cursor = classic.cursor_of(self.headers, query)
        if cursor >= 0:
            channel.resume(cursor)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            if hasattr(self.wfile, "flush"):
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
            while True:
                payload = channel.next_payload()
                self.wfile.write(payload.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return
        finally:
            channel.close()   # 摘掉本连接的广播队列，避免长跑进程里堆积
