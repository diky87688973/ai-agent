# -*- coding: utf-8 -*-
"""Web HTTP 路由分发（_Handler）。"""
from __future__ import annotations

import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, unquote, urlparse

from agent.core.error_report import report_error
from agent.shell.service_keys import SERVICE_CLASSIC_ADAPTER
from agent.shell.web_api import WebShell
from agent.shell.web_static import (
    MAX_BODY_BYTES,
    SSE_HEARTBEAT_SEC,
    _plugin_asset_rel,
)


class _Handler(BaseHTTPRequestHandler):
    """路由分发。"""

    server_version = "ai-agent-web/1.0"
    protocol_version = "HTTP/1.1"

    # 由 serve() 注入
    shell: WebShell
    assets_dir: Path

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

    def _json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _plugin_route(self, method: str, body: Optional[Dict[str, Any]] = None) -> None:
        """把 `/api/plugin/<插件>/<段>` 转发给插件注册的端点。

        路径与查询串自己从请求行取（三个动词共用这一条，调用点不必各传一份）。
        路径里声明的 `:名字` 段由壳层按位置取值后交给 handler；除参数段外不做通配，
        「某插件挂了哪些端点形状」始终可枚举。无匹配时 404 并列出全部已注册端点。

        handler 收到的 dict：查询串 + 路径参数 + （有请求体时）`body`。
        """
        path = self._path()
        query = self._query()
        host = getattr(self.shell.app, "plugin_host", None) if self.shell.app else None
        contribs = getattr(host, "contributions", None) if host is not None else None
        if contribs is None:
            self._json(404, {"error": "插件系统未接入"})
            return
        # 面板脚本资产：`/api/plugin/<插件>/_asset/<插件目录内相对路径>`
        asset = _plugin_asset_rel(path)
        if asset is not None and method == "GET":
            self._plugin_asset(asset[0], asset[1])
            return
        hit = contribs.match(method, path)
        if hit is None:
            self._json(404, {"error": "插件端点不存在", "method": method, "path": path,
                             "available": [r.as_dict() for r in contribs.all_routes()]})
            return
        route, params = hit
        args: Dict[str, Any] = dict(query or {})
        if params:
            args.update(params)
        if body:
            args["body"] = body
        try:
            result = route.handler(args)
        except Exception as exc:  # 插件端点异常不该打挂壳层
            report_error("plugin.route", exc, plugin=str(route.plugin or ""))
            self._json(500, {"error": f"{type(exc).__name__}: {exc}",
                             "plugin": route.plugin})
            return
        if isinstance(result, tuple) and len(result) == 2:
            status, payload = int(result[0]), result[1]
        else:
            status, payload = 200, result
        if isinstance(payload, (dict, list)):
            self._json(status, payload if isinstance(payload, dict) else {"ok": True, "items": payload})
        else:
            self._bytes(status, str(payload).encode("utf-8"), "text/plain; charset=utf-8")

    def _plugin_asset(self, plugin: str, rel: str) -> None:
        """送出插件目录内的面板脚本。

        路径必须是该插件目录下的真实文件：先解析绝对路径，再校验它落在插件目录内
        （挡 `..` 与符号链接绕行）。只送文本类脚本，不送任意文件。
        """
        host = getattr(self.shell.app, "plugin_host", None) if self.shell.app else None
        base = getattr(host, "plugins_dir", None) if host is not None else None
        if base is None:
            self._json(404, {"error": "插件目录未接入"})
            return
        tracked = host.plugin_root(plugin) if host is not None else None
        root = Path(tracked).resolve() if tracked is not None else (Path(base) / plugin).resolve()
        target = (root / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            self._json(403, {"error": "路径越出插件目录"})
            return
        if not target.is_file():
            self._json(404, {"error": "脚本不存在", "path": f"{plugin}/{rel}"})
            return
        suffix = target.suffix.lower()
        ctype = {
            ".js": "application/javascript; charset=utf-8",
            ".mjs": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".html": "text/html; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
        }.get(suffix)
        if ctype is None:
            self._json(415, {"error": f"不送该类型：{suffix or '(无扩展名)'}"})
            return
        try:
            body = target.read_bytes()
        except OSError as exc:
            self._json(500, {"error": f"{type(exc).__name__}"})
            return
        self._bytes(200, body, ctype)

    def _bytes(self, status: int, body: bytes, content_type: str) -> None:
        """二进制响应（附件走这条：经典界面用 `<img src>` 直接引用）。"""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    # ── 经典界面适配层 ────────────────────────────────

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
        from agent.shell.web_ui_config import get_web_ui

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
            pass  # 浏览器刷新 / 关标签：正常断开
        finally:
            channel.close()   # 摘掉本连接的广播队列，避免长跑进程里堆积


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

    def _events_stream(self) -> None:
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
                frame = channel.next_frame(SSE_HEARTBEAT_SEC)
                if frame is None:
                    break
                self.wfile.write(frame.encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass  # 浏览器刷新 / 关标签：正常断开
        finally:
            self.shell.detach(channel)

    # ── GET ───────────────────────────────────────────────

    # 本项目未启用 N802（不追命名风格），无需抑制指令；
    # 无效的抑制指令本身会被 ruff 报警告（由 RUF100 守住）。
    def do_GET(self) -> None:
        try:
            path = self._path()
            query = self._query()
            if path == "/":
                self._classic_page()
            elif path == "/favicon.ico":
                self._asset("img/app_icon_128x128.png", "image/png")

            elif path.startswith("/assets/"):
                self._asset(path[len("/assets/") :])
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
                # 经典界面要 `ok:true` + 老事件名；由适配层翻译（内核事件名与它不同）
                classic = self._classic()
                if classic is not None:
                    self._json(200, classic.history(query.get("conversation_id", "")))
                else:
                    status, payload = self.shell.history(query.get("conversation_id", ""))
                    self._json(status, payload)
            elif path == "/api/chat/sessions":
                # 经典界面读 `s.id`（不是 `conversation_id`）+ `date_group`
                classic = self._classic()
                if classic is not None:
                    self._json(200, classic.sessions())
                else:
                    status, payload = self.shell.sessions()
                    self._json(status, payload)
            elif path == "/api/chat/ui-state":
                # 语义不同：内核存「模式/todo/自主」，经典界面存「布局(tabs)」。
                # 经典界面的 GET 不带 conversation_id（经典界面），
                # 所以有适配层时一律走它，不落到内核那套上。
                classic = self._classic()
                if classic is not None and not query.get("conversation_id"):
                    self._json(200, classic.ui_state_get())
                else:
                    status, payload = self.shell.ui_state(query.get("conversation_id", ""))
                    self._json(status, payload)
            elif path == "/api/fs/list":
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
                # 插件贡献的右栏面板清单；界面按它动态建标签，不为每个插件加分支
                self._json(200, {
                    "ok": True,
                    "panels": self.shell.panel_list(),
                    "loaded": self.shell.loaded_plugin_names(),
                })
            elif path == "/api/actions":
                # 插件贡献的输入区动作（输入框下面的按钮）；不声明就没有按钮
                self._json(200, {"ok": True, "actions": self.shell.action_list()})
            elif path == "/api/ctx-segment-styles":
                # 插件贡献的上下文段外观；开屏注册，不必靠空面板脚本
                self._json(200, {
                    "ok": True,
                    "styles": self.shell.ctx_segment_style_list(),
                })
            elif path == "/api/boot-scripts":
                # 插件贡献的开屏脚本；面板脚本预载之后再注入
                self._json(200, {
                    "ok": True,
                    "scripts": self.shell.boot_script_list(),
                })
            elif path == "/api/tool-labels":
                # 工具展示清单（中文名 + 图标）：由工具自己声明，界面不维护工具名表
                self._json(200, {"ok": True, "tools": self.shell.tool_list()})
            elif path.startswith("/api/plugin/"):
                # 插件自己的端点：命名空间内匹配声明过的路径形状（`:名字` 段可由请求填值）
                self._plugin_route("GET")
            elif path == "/api/dir-browse":
                status, payload = self.shell.dir_browse(query.get("path", ""))
                self._json(status, payload)
            elif path == "/api/reasoning-effort":
                status, payload = self.shell.reasoning_effort_get(
                    query.get("conversation_id", "")
                )
                self._json(status, payload)
            elif path == "/api/media":
                # 传 None：按全部可见根校验。`media_root` 只覆盖第一个盘根，
                # 生成物在别的盘上会被一律 403（`WebShell.media` 按全部可见根校验）。
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
                # 经典 UI 的 Markdown 渲染把工作区图片/视频重写成 `/workspace/<rel>`
                # （用的是同类静态路由）。这里把它接上：根 = `workspace_root`，
                # 复用 `media()` 的防越权校验（目标必须落在根内）。
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
        except Exception as exc:  # 壳层兜底：单请求失败不影响服务
            self._safe_error(exc)

    # ── POST / PUT ────────────────────────────────────────

    def do_POST(self) -> None:  # HTTP 动词命名（stdlib 约定）
        try:
            path = self._path()
            body = self._read_body()
            if path == "/api/chat/send":
                status, payload = self.shell.send(
                    str(body.get("conversation_id") or ""),
                    str(body.get("message") or ""),
                    str(body.get("mode") or ""),
                    body.get("images"),
                    str(body.get("model") or ""),
                )
                # 经典界面会读返回体里的 `attachments`（Array 且非空才重建附件条，
                # il.js:168 用它拼 /api/chat/attachment 的 URL）。内核返回体不含该字段，
                # 须由适配层补：登记本轮图片并给出可引用 id。
                classic = self._classic()
                if classic is not None and status == 200:
                    cid = str(payload.get("conversation_id") or "")
                    items = classic.inbound.remember_attachments(cid, body.get("images"))
                    if items:
                        payload = {
                            **payload,
                            "attachments": [
                                {"id": it["id"], "name": it["name"], "mime": it["mime"]}
                                for it in items
                            ],
                        }
                self._json(status, payload)
            elif path == "/api/chat/user-confirm":
                # 确认端点承载两类请求（经典界面两种情况共用一个端点）：
                #   ① 写盘门控：带 `confirm_id` → 解锁预览快照（内核既有行为）；
                #   ② 选择回填：带 `confirm` 文本 → 把用户选择送回模型
                #      （`user_confirm` 工具的第二段；经典界面期待返回体带 `run_id`）。
                # 适配层负责分流与回填，内核的 `shell.confirm` 原样复用。
                classic = self._classic()
                if classic is not None:
                    status, payload = classic.user_confirm(
                        str(body.get("conversation_id") or ""), body
                    )
                else:
                    status, payload = self.shell.confirm(
                        str(body.get("conversation_id") or ""),
                        str(body.get("confirm_id") or ""),
                    )
                self._json(status, payload)
            elif path == "/api/chat/title":
                status, payload = self.shell.title(str(body.get("conversation_id") or ""))
                self._json(status, payload)
            elif path == "/api/chat/autonomous":
                status, payload = self.shell.autonomous(
                    str(body.get("conversation_id") or ""),
                    body.get("enabled"),
                )
                self._json(status, payload)
            elif path == "/api/chat/stop":
                status, payload = self.shell.stop(str(body.get("conversation_id") or ""))
                self._json(status, payload)
            elif path == "/api/chat/goal":
                # 前端「目标」按钮：save=建/改、pause、resume、done、delete、get
                # `self.shell` 才是装配好的 App（`self.app` 属于 `WebShell`，不在处理器上）
                state = getattr(getattr(self, "shell", None), "app", None)
                state = getattr(state, "live_state", None)
                cid = str(body.get("conversation_id") or "").strip()
                action = str(body.get("action") or "get").strip().lower()
                if state is None or not cid:
                    self._json(400, {"ok": False, "error": "conversation_id 与 live_state 均必需"})
                    return
                try:
                    if action == "save":
                        # 「保存」只改文案：paused/done 保持原状态
                        # （否则改成重开会让自动续跑被重新触发），备注也不清除。
                        text = str(body.get("text") or "")
                        existing = state.get_goal(cid)
                        if existing is None:
                            goal = state.set_goal(cid, text)
                        else:
                            goal = state.update_goal(cid, text=text)
                    elif action == "get":
                        goal = state.get_goal(cid)
                    elif action in ("pause", "resume", "done"):
                        goal = state.update_goal(cid, status={"pause": "paused", "resume": "active",
                                                              "done": "done"}[action])
                    elif action == "delete":
                        state.delete_goal(cid)
                        goal = None
                    else:
                        self._json(400, {"ok": False, "error": f"未知 action：{action}"})
                        return
                except Exception as exc:
                    self._json(400, {"ok": False, "error": str(exc)})
                    return
                self._json(200, {"ok": True, "goal": goal})
            elif path == "/api/chat/command-input":
                # 预留通道：端点保持接通、可返回成功，内核暂不消费其内容
                classic = self._classic()
                self._json(200, classic.command_input(
                    str(body.get("conversation_id") or ""), body)
                    if classic else {"ok": False, "error": "适配层未装配"})
            elif path.startswith("/api/plugin/"):
                # 插件业务提交（生成任务、保存配置等）走这条
                self._plugin_route("POST", body)
            elif path == "/api/settings" or path.startswith("/api/settings/"):
                from agent.shell.settings_panel import handle_post

                status, payload = handle_post(
                    path, body, getattr(self.shell, "app", None))
                self._json(status, payload)
            else:
                self._json(404, {"error": "not found", "path": path})
        except Exception as exc:
            self._safe_error(exc)

    def do_PUT(self) -> None:  # HTTP 动词命名（stdlib 约定）
        try:
            path = self._path()
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
            self._safe_error(exc)

    def do_DELETE(self) -> None:  # HTTP 动词命名（stdlib 约定）
        """DELETE：会话关闭释放运行态；插件端点撤销任务 / 清缓存。"""
        try:
            path = self._path()
            query = self._query()
            if path == "/api/chat/sessions":
                status, payload = self.shell.release_conversation(
                    query.get("conversation_id", "") or query.get("id", "")
                )
                self._json(status, payload)
            elif path.startswith("/api/plugin/"):
                self._plugin_route("DELETE")
            else:
                self._json(404, {"error": "not found", "path": path})
        except Exception as exc:
            self._safe_error(exc)

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


