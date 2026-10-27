# -*- coding: utf-8 -*-
"""Web HTTP 路由分发（Handler）。"""
from __future__ import annotations

import json
import mimetypes
import re
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, unquote, urlparse

from agent.core.context import SERVICE_BACKGROUND_TASKS, SERVICE_CONVERSATION_QUEUE, SERVICE_UPDATE
from agent.core.error_report import report_error
from agent.shell.web.web_api import WebShell
from agent.shell.web.web_auth import AuthMiddleware
from agent.shell.web.web_classic import ClassicRoutes
from agent.shell.web.web_plugin import PluginRoutes
from agent.shell.web.web_static import (
    MAX_BODY_BYTES,
    SSE_HEARTBEAT_SEC,
)


class Handler(AuthMiddleware, PluginRoutes, ClassicRoutes, BaseHTTPRequestHandler):
    """路由分发。"""

    server_version = "ai-agent-web/1.0"
    protocol_version = "HTTP/1.1"

    # 由 serve() 注入
    shell: WebShell
    assets_dir: Path
    auth_runtime: Any = None

    # ── 工具 ──────────────────────────────────────────────

    def handle_one_request(self) -> None:
        """读下一条请求行时，客户端提前断开不算错误。

        每次 SSE 连接被浏览器关掉（刷新标签、关标签、探针读够就走）时，
        `BaseHTTPRequestHandler.handle_one_request` 在读下一条请求行时抛
        `ConnectionAbortedError [WinError 10053]`，`socketserver` 把它当"处理请求时
        发生异常"打整屏 traceback。而 `_events_stream` 里已经吞掉了同类异常 ——
        噪声来自响应写完之后的那次读，与业务无关。
        这里按"正常断开"处理，让 stderr 只剩真正的问题。
        """
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # 客户端断开是 SSE/长连接场景的常态，
            # 与被请求的业务无关；吞掉它才能让 stderr 保住信噪比。
            self.close_connection = True

    def log_message(self, fmt: str, *args: Any) -> None:  # 静音逐请求日志
        pass

    def _json(self, status: int, payload: Dict[str, Any],
              headers: Optional[Dict[str, str]] = None) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _bytes(self, status: int, body: bytes, content_type: str) -> None:
        """二进制响应（附件走这条：经典界面用 `<img src>` 直接引用）。"""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    # ── 经典界面适配层 ────────────────────────────────

    def _read_body(self) -> Dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            return {}
        if length <= 0 or length > MAX_BODY_BYTES:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8", errors="replace"))
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _query(self) -> Dict[str, str]:
        parsed = urlparse(self.path)
        return {k: v[0] for k, v in parse_qs(parsed.query).items() if v}

    def _path(self) -> str:
        return urlparse(self.path).path.rstrip("/") or "/"

    # ── 静态资源───────────────────────────────────

    def _asset(self, rel: str, content_type: Optional[str] = None) -> None:
        target = (self.assets_dir / rel).resolve()
        try:
            target.relative_to(self.assets_dir.resolve())
        except ValueError:
            self._json(404, {"error": "not found"})
            return
        if not target.is_file():
            self._json(404, {"error": "not found"})
            return
        body = target.read_bytes()
        ctype = content_type or mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    # ── SSE───────────────────────────────────────

    def _stream_session_valid(self, identity: Any) -> bool:
        if identity is None:
            return True
        current = self._identity()
        if current is None:
            return False
        if identity.session is not None:
            return current.session is not None
        if identity.api_token:
            return current.api_token and current.principal == identity.principal
        return True

    def _events_stream(self) -> None:
        identity = getattr(self, "_auth_identity", None)
        channel = self.shell.attach()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                if not self._stream_session_valid(identity):
                    break
                frame = channel.next_frame(SSE_HEARTBEAT_SEC)
                if frame is None:
                    break
                self.wfile.write(frame.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            return
        finally:
            self.shell.detach(channel)

    # ── GET ───────────────────────────────────────────────

    # 本项目未启用 N802（不追命名风格），无需抑制指令；
    # 无效的抑制指令本身会被 ruff 报警告（由 RUF100 守住）。
    def _background_tasks(self) -> Any:
        app = getattr(self.shell, "app", None)
        context = getattr(app, "context", None)
        if context is None or not callable(getattr(context, "has", None)):
            return None
        if not context.has(SERVICE_BACKGROUND_TASKS):
            return None
        return context.get(SERVICE_BACKGROUND_TASKS)

    def _update_controller(self) -> Any:
        app = getattr(self.shell, "app", None)
        context = getattr(app, "context", None)
        if context is None or not callable(getattr(context, "has", None)):
            return None
        if not context.has(SERVICE_UPDATE):
            return None
        return context.get(SERVICE_UPDATE)

    def _get_update(self, path: str, query: Any) -> bool:
        if path == "/api/update/status":
            controller = self._update_controller()
            if controller is None:
                self._json(503, {"ok": False, "error": "update_unavailable"})
            else:
                self._json(200, {"ok": True, **controller.status()})
            return True
        if path == "/api/update/logs":
            controller = self._update_controller()
            if controller is None:
                self._json(503, {"ok": False, "error": "update_unavailable"})
            else:
                from agent.update.logs import tail
                self._json(200, {"ok": True, "items": tail(controller.root)})
            return True
        return False

    def _get_subagents(self, path: str, query: Any) -> bool:
        if path == "/api/subagents":
            status, payload = self.shell.subagents(
                str(query.get("conversation_id") or "").strip(),
                str(query.get("batch") or "").strip())
            self._json(status, payload)
            return True
        if path == "/api/subagents/history":
            status, payload = self.shell.subagent_history(
                str(query.get("conversation_id") or "").strip(),
                str(query.get("child_id") or "").strip())
            self._json(status, payload)
            return True
        return False

    def _get_background(self, path: str, query: Any) -> bool:
        if path != "/api/background/tasks":
            return False
        manager = self._background_tasks()
        if manager is None:
            self._json(503, {"ok": False, "error": "background_tasks_unavailable"})
            return True
        cid = str(query.get("conversation_id") or "").strip()
        try:
            batch = str(query.get("batch") or "").strip()
            if batch:
                result = manager.list_tasks(
                    cid, batch, task_id=str(query.get("task_id") or ""),
                    status=str(query.get("status") or ""))
            else:
                result = manager.snapshot(cid)
            self._json(200, result)
        except ValueError as exc:
            self._json(400, {"ok": False, "error": str(exc)})
        return True

    def _get_page(self, path: str, query: Any) -> bool:
        if path == "/":
            self._classic_page()
        elif path == "/favicon.ico":
            self._asset("img/app_icon_128x128.png", "image/png")
        elif path.startswith("/assets/"):
            self._asset(path[len("/assets/"):])
        elif path == "/health":
            classic = self._classic()
            if classic is not None:
                self._json(200, classic.health())
            else:
                status, payload = self.shell.health()
                self._json(status, payload)
        elif path == "/api/settings" or path.startswith("/api/settings/"):
            from agent.shell.settings_panel import handle_get
            status, payload = handle_get(path, query, self.shell.app)
            self._json(status, payload)
        elif path == "/api/chat/queue":
            status, payload = self.shell.queue(query.get("conversation_id", ""))
            self._json(status, payload)
        elif path == "/api/events/stream":
            self._classic_sse(query)
        elif path == "/api/usage-accumulator":
            classic = self._classic()
            self._json(200, classic.usage_get(query.get("conversation_id", ""))
                       if classic else {"ok": False, "error": "适配层未装配"})
        elif path == "/api/chat/attachment":
            classic = self._classic()
            if classic is None:
                self._json(503, {"error": "适配层未装配"})
            else:
                status, body, ctype = classic.attachment(
                    query.get("conversation_id", ""), query.get("id", ""))
                self._bytes(status, body, ctype)
        elif path == "/api/chat/history":
            classic = self._classic()
            if classic is not None:
                raw_before = str(query.get("before", "") or "").strip()
                before = None
                if raw_before:
                    try:
                        before = int(raw_before)
                    except (TypeError, ValueError):
                        self._json(200, {"ok": False, "error": "invalid before", "items": []})
                        return True
                    if before < 0:
                        self._json(200, {"ok": False, "error": "invalid before", "items": []})
                        return True
                meta = str(query.get("meta", "") or "").strip() == "1"
                self._json(200, classic.history(
                    query.get("conversation_id", ""), before=before, meta=meta))
            else:
                status, payload = self.shell.history(query.get("conversation_id", ""))
                self._json(status, payload)
        elif path == "/api/chat/sessions":
            classic = self._classic()
            if classic is not None:
                self._json(200, classic.sessions())
            else:
                status, payload = self.shell.sessions()
                self._json(status, payload)
        elif path == "/api/chat/ui-state":
            classic = self._classic()
            if classic is not None and not query.get("conversation_id"):
                self._json(200, classic.ui_state_get())
            else:
                status, payload = self.shell.ui_state(query.get("conversation_id", ""))
                self._json(status, payload)
        else:
            return False
        return True

    def _get_misc(self, path: str, query: Any) -> None:
        if path == "/api/fs/list":
            status, payload = self.shell.fs_list(query.get("path", ""))
            self._json(status, payload)
        elif path == "/api/fs/read":
            try:
                limit = int(query.get("max_chars") or 400000)
            except (TypeError, ValueError):
                limit = 400000
            status, payload = self.shell.fs_read(query.get("path", ""), limit)
            self._json(status, payload)
        elif path == "/api/panels":
            self._json(200, {"ok": True, "panels": self.shell.panel_list(),
                             "loaded": self.shell.loaded_plugin_names()})
        elif path == "/api/actions":
            self._json(200, {"ok": True, "actions": self.shell.action_list()})
        elif path == "/api/ctx-segment-styles":
            self._json(200, {"ok": True, "styles": self.shell.ctx_segment_style_list()})
        elif path == "/api/boot-scripts":
            self._json(200, {"ok": True, "scripts": self.shell.boot_script_list()})
        elif path == "/api/tool-labels":
            self._json(200, {"ok": True, "tools": self.shell.tool_list()})
        elif path.startswith("/api/plugin/"):
            self._plugin_route("GET")
        elif path == "/api/dir-browse":
            status, payload = self.shell.dir_browse(query.get("path", ""))
            self._json(status, payload)
        elif path == "/api/reasoning-effort":
            status, payload = self.shell.reasoning_effort_get(
                query.get("conversation_id", ""))
            self._json(status, payload)
        elif path == "/api/media":
            status, payload, ctype = self.shell.media(query.get("path", ""), None)
            if status == 200 and isinstance(payload, (bytes, bytearray)):
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(payload)
            else:
                self._json(status, payload if isinstance(payload, dict) else {"error": "?"})
        elif path.startswith("/workspace/"):
            rel = unquote(path[len("/workspace/"):])
            root = self.shell.workspace_root
            if root is None:
                self._json(404, {"error": "workspace 未配置"})
            else:
                status, payload, ctype = self.shell.media(
                    str((root / rel).resolve()), root)
                if status == 200 and isinstance(payload, (bytes, bytearray)):
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(payload)
                else:
                    self._json(status, payload if isinstance(payload, dict)
                               else {"error": "?"})
        else:
            self._json(404, {"error": "not found", "path": path})

    def do_GET(self) -> None:
        try:
            path = self._path()
            if not self._host_guard():
                return
            query = self._query()
            if self._auth_public_get(path):
                return
            if not self._auth_gate("GET", path):
                return
            if path == "/auth/csrf":
                runtime = getattr(self, "auth_runtime", None)
                status, payload, headers = runtime.routes.csrf(
                    getattr(self, "_auth_identity", None))
                self._json(status, payload, headers=headers)
                return
            if self._get_update(path, query):
                return
            if self._get_subagents(path, query):
                return
            if self._get_background(path, query):
                return
            if self._get_page(path, query):
                return
            self._get_misc(path, query)
        except Exception as exc:
            report_error("agent.shell.web.web_routes.Handler.do_GET", exc)
            self._safe_error(exc)

    # ── POST / PUT ────────────────────────────────────────

    def _post_chat_send(self, body: dict) -> None:
        status, payload = self.shell.send(
            str(body.get("conversation_id") or ""), str(body.get("message") or ""),
            str(body.get("mode") or ""), body.get("images"),
            str(body.get("model") or ""), str(body.get("draft_id") or ""))
        classic = self._classic()
        if classic is not None and status == 200:
            cid = str(payload.get("conversation_id") or "")
            items = classic.inbound.remember_attachments(cid, body.get("images"))
            if items:
                payload = {**payload, "attachments": [
                    {"id": it["id"], "name": it["name"], "mime": it["mime"]}
                    for it in items]}
        self._json(status, payload)

    def _post_update(self, path: str, body: dict) -> None:
        controller = self._update_controller()
        if controller is None:
            self._json(503, {"ok": False, "error": "update_unavailable"})
            return
        try:
            if path.endswith("/apply"):
                context = getattr(getattr(self.shell, "app", None), "context", None)
                manager = (context.get(SERVICE_BACKGROUND_TASKS)
                           if context is not None and context.has(SERVICE_BACKGROUND_TASKS)
                           else None)
                if manager is not None and callable(getattr(manager, "active_total", None)):
                    active = int(manager.active_total())
                    if active > 0:
                        raise ValueError(f"仍有 {active} 个后台任务，停止后再更新")
                queue = (context.get(SERVICE_CONVERSATION_QUEUE)
                         if context is not None
                         and context.has(SERVICE_CONVERSATION_QUEUE) else None)
                if queue is not None and callable(getattr(queue, "pending_total", None)):
                    queued = int(queue.pending_total())
                    if queued > 0:
                        raise ValueError(f"仍有 {queued} 条待发送消息，处理后再更新")
            if path.endswith("/check"):
                result = controller.check()
            elif path.endswith("/download"):
                result = controller.download()
            else:
                result = controller.apply()
        except (OSError, ValueError) as exc:
            self._json(400, {"ok": False, "error": str(exc)})
        else:
            self._json(200, {"ok": True, **result})

    def _post_background(self, path: str, body: dict) -> None:
        manager = self._background_tasks()
        if manager is None:
            self._json(503, {"ok": False, "error": "background_tasks_unavailable"})
            return
        if path == "/api/background/tasks/create":
            try:
                result = manager.create(
                    str(body.get("conversation_id") or ""), body.get("argv"),
                    str(body.get("cwd") or ""), int(body.get("timeout_sec") or 0),
                    str(body.get("label") or ""), str(body.get("batch") or ""))
            except (TypeError, ValueError) as exc:
                self._json(400, {"ok": False, "error": str(exc)})
            else:
                self._json(200 if result.get("ok") else 409, result)
        elif path == "/api/background/tasks/cancel":
            try:
                result = manager.cancel(
                    str(body.get("conversation_id") or ""),
                    str(body.get("task_id") or ""), str(body.get("reason") or ""))
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
            else:
                self._json(200 if result.get("ok") else 404, result)
        else:
            try:
                result = manager.output(
                    str(body.get("conversation_id") or ""),
                    str(body.get("task_id") or ""), bool(body.get("wait", False)),
                    int(body.get("timeout_ms") or 30_000))
            except (TypeError, ValueError) as exc:
                self._json(400, {"ok": False, "error": str(exc)})
            else:
                self._json(200 if result.get("ok") else 404, result)

    def _post_chat_misc(self, path: str, body: dict) -> bool:
        if path == "/api/chat/user-confirm":
            classic = self._classic()
            if classic is not None:
                status, payload = classic.user_confirm(
                    str(body.get("conversation_id") or ""), body)
            else:
                status, payload = self.shell.confirm(
                    str(body.get("conversation_id") or ""),
                    str(body.get("confirm_id") or ""))
            self._json(status, payload)
        elif path == "/api/chat/title":
            self._json(*self.shell.title(str(body.get("conversation_id") or "")))
        elif path == "/api/chat/autonomous":
            self._json(*self.shell.autonomous(
                str(body.get("conversation_id") or ""), body.get("enabled")))
        elif path == "/api/chat/stop":
            self._json(*self.shell.stop(str(body.get("conversation_id") or "")))
        elif path == "/api/chat/command-input":
            classic = self._classic()
            self._json(200, classic.command_input(
                str(body.get("conversation_id") or ""), body)
                if classic else {"ok": False, "error": "适配层未装配"})
        else:
            return False
        return True

    def _post_goal(self, body: dict) -> None:
        state = getattr(getattr(self.shell, "app", None), "live_state", None)
        cid = str(body.get("conversation_id") or "").strip()
        action = str(body.get("action") or "get").strip().lower()
        if state is None or not cid:
            self._json(400, {"ok": False, "error": "conversation_id 与 live_state 均必需"})
            return
        try:
            if action == "save":
                text = str(body.get("text") or "")
                goal = (state.set_goal(cid, text) if state.get_goal(cid) is None
                        else state.update_goal(cid, text=text))
            elif action == "get":
                goal = state.get_goal(cid)
            elif action == "resume":
                text = str(body.get("text") or "").strip()
                if text:
                    goal = state.set_goal(cid, text)
                elif state.get_goal(cid) is None:
                    self._json(400, {"ok": False, "error": "目标不存在，且没有可恢复的文案"})
                    return
                else:
                    goal = state.update_goal(cid, status="active")
            elif action in ("pause", "done"):
                goal = state.update_goal(
                    cid, status={"pause": "paused", "done": "done"}[action])
            elif action == "delete":
                state.delete_goal(cid)
                goal = None
            else:
                self._json(400, {"ok": False, "error": f"未知 action：{action}"})
                return
        except Exception as exc:
            report_error("agent.shell.web.web_routes.Handler.do_POST", exc)
            self._json(400, {"ok": False, "error": str(exc)})
            return
        self._json(200, {"ok": True, "goal": goal})

    def _post_queue(self, path: str, body: dict) -> bool:
        match = re.fullmatch(r"/api/chat/queue/([A-Za-z0-9_-]{8,64})/(insert|recall)", path)
        if match is None:
            return False
        if match.group(2) == "insert":
            self._json(*self.shell.queue_insert(
                str(body.get("conversation_id") or ""), match.group(1)))
        else:
            self._json(*self.shell.queue_recall(
                str(body.get("conversation_id") or ""), match.group(1)))
        return True

    def do_POST(self) -> None:
        try:
            path = self._path()
            if not self._host_guard():
                return
            if self._auth_post_login(path):
                return
            if not self._auth_gate("POST", path):
                return
            if self._auth_logout(path):
                return
            body = self._read_body()
            if path == "/api/chat/send":
                self._post_chat_send(body)
                return
            if path in ("/api/update/check", "/api/update/download", "/api/update/apply"):
                self._post_update(path, body)
                return
            if path == "/api/subagents/send":
                self._json(*self.shell.subagent_send(
                    str(body.get("conversation_id") or ""),
                    str(body.get("child_id") or ""), str(body.get("msg") or ""),
                    images=body.get("images")))
                return
            if path.startswith("/api/background/tasks/"):
                self._post_background(path, body)
                return
            if path == "/api/chat/goal":
                self._post_goal(body)
                return
            if self._post_chat_misc(path, body):
                return
            if path.startswith("/api/chat/queue/") and self._post_queue(path, body):
                return
            if path.startswith("/api/plugin/"):
                self._plugin_route("POST", body)
                return
            if path == "/api/settings" or path.startswith("/api/settings/"):
                from agent.shell.settings_panel import handle_post
                self._json(*handle_post(
                    path, body, getattr(self.shell, "app", None)))
                return
            self._json(404, {"error": "not found", "path": path})
        except Exception as exc:
            report_error("agent.shell.web.web_routes.Handler.do_POST", exc)
            self._safe_error(exc)

    def do_PUT(self) -> None:  # HTTP 动词命名（stdlib 约定）
        try:
            path = self._path()
            if not self._host_guard():
                return
            if not self._auth_gate("PUT", path):
                return
            body = self._read_body()
            if path == "/api/chat/ui-state":
                # 经典界面的 PUT 直接发布局对象（经典界面），不带 conversation_id；
                # 内核那套要求 conversation_id。用有无该字段区分两套语义。
                classic = self._classic()
                if classic is not None and not body.get("conversation_id"):
                    self._json(200, classic.ui_state_put(body))
                else:
                    status, payload = self.shell.ui_state_put(
                        str(body.get("conversation_id") or ""), body
                    )
                    self._json(status, payload)
            elif path == "/api/reasoning-effort":
                status, payload = self.shell.reasoning_effort_set(
                    str(body.get("conversation_id") or body.get("cid") or ""),
                    str(body.get("effort") or ""),
                )
                self._json(status, payload)
            elif path == "/api/usage-accumulator":
                classic = self._classic()
                self._json(200, classic.usage_put(
                    str(body.get("conversation_id") or ""), body)
                    if classic else {"ok": False, "error": "适配层未装配"})
            elif path.startswith("/api/plugin/"):
                self._plugin_route("PUT", body)
            else:
                self._json(404, {"error": "not found", "path": path})
        except Exception as exc:
            report_error("agent.shell.web.web_routes.Handler.do_PUT", exc)
            self._safe_error(exc)

    def do_DELETE(self) -> None:  # HTTP 动词命名（stdlib 约定）
        """DELETE：会话关闭释放运行态；插件端点撤销任务 / 清缓存。"""
        try:
            path = self._path()
            if not self._host_guard():
                return
            if not self._auth_gate("DELETE", path):
                return
            query = self._query()
            if path == "/api/chat/sessions":
                status, payload = self.shell.release_conversation(
                    query.get("conversation_id", "") or query.get("id", "")
                )
                self._json(status, payload)
            elif path.startswith("/api/chat/queue/"):
                match = re.fullmatch(
                    r"/api/chat/queue/([A-Za-z0-9_-]{8,64})", path
                )
                if match is None:
                    self._json(404, {"error": "not found", "path": path})
                else:
                    status, payload = self.shell.queue_cancel(
                        query.get("conversation_id", ""), match.group(1)
                    )
                    self._json(status, payload)
            elif path.startswith("/api/plugin/"):
                self._plugin_route("DELETE")
            else:
                self._json(404, {"error": "not found", "path": path})
        except Exception as exc:
            report_error("agent.shell.web.web_routes.Handler.do_DELETE", exc)
            self._safe_error(exc)

    def do_HEAD(self) -> None:
        path = self._path()
        if not self._host_guard():
            return
        if not self._auth_gate("HEAD", path):
            return
        self.send_response(405)
        self.send_header("Allow", "GET, POST, PUT, DELETE")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_OPTIONS(self) -> None:
        path = self._path()
        if not self._host_guard():
            return
        if not self._auth_gate("OPTIONS", path):
            return
        self.send_response(405)
        self.send_header("Allow", "GET, POST, PUT, DELETE")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _safe_error(self, exc: Exception) -> None:
        # 客户端提前断开（刷新 / 关标签 / SSE 关闭）不是服务故障：静默即可，不打日志
        if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return
        if isinstance(exc, OSError) and getattr(exc, "winerror", None) in (10053, 10054, 10058):
            return
        try:
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
        except Exception:
            print(f"[web] 响应失败：{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)


