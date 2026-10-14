# -*- coding: utf-8 -*-
"""Web 壳——HTTP/SSE 服务。

架构：
- **零新依赖**：只用标准库 `http.server.ThreadingHTTPServer`；
- **单流多路复用**：一个 `GET /api/events/stream` 广播全部会话事件，
  每个事件经 `Event.data` 携带 `conversation_id`（内核 emit 已注入），前端按 cid 分派；
- 承载：以 **EventBus 通配订阅**产出（旁路纪律）；
- **会话级门控**：确认端点按 cid 解析到该会话的门控（`App.gate_for`），
  不落默认桶——否则确认落空、提交被拒。

本模块属 L3 壳，只依赖 core / mechanisms / 既有装配面，内核无改动。
"""
from __future__ import annotations

import json
import mimetypes
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

from agent.app import App, build_app
from agent.capabilities.contributions import ASSET_SEGMENT
from agent.config import (
    PROJECT_ROOT,
    default_data_root,
    get_model_reasoning,
    get_reasoning_effort,
)
from agent.core import event_name as ev
from agent.core.context import SERVICE_CLASSIC_ADAPTER
from agent.mechanisms.model_provider import OpenAICompatibleProvider
from agent.mechanisms.session_store import (
    _KEY_DATA,
    _KEY_TYPE,
    SessionStore,
    is_valid_conversation_id,
    new_conversation_id,
)
from agent.mechanisms.session_title import (
    TitleStore,
    fallback_title,
    is_placeholder_title,
    make_provider_title_generator,
)

# 路径安全与可见范围的导入路径约定在本模块：外部按 `agent.shell.web` 导入这些名字。
from agent.shell.fspaths import (  # noqa: F401
    _default_fs_roots,
    _env_path,
    _env_roots,
    _fs_rejection,
    _is_drive_root,
    _list_drives,
    _normalize_roots,
    _parse_roots,
    _within_any_root,
)

# SSE 传输层的导入路径约定在本模块：`from agent.shell.web import _Channel` 可用。
from agent.shell.sse import _Channel, _event_seq, _sse_payload  # noqa: F401

ASSETS_DIR = Path(__file__).resolve().parent / "web_assets"
MAX_BODY_BYTES = 4 * 1024 * 1024  # 4 MB 请求体上限
SSE_HEARTBEAT_SEC = 15.0          # 取帧最长等待（秒）：超时就发保活帧，取值须小于网关空闲读超时
MODE_VALUES = ("auto", "plan", "execute")
MAX_IMAGES = 4                     # 单条消息的截图上限
_IMAGE_MIMES = ("image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif")
_BINARY_SNIFF_BYTES = 4096
_TITLE_SCAN_LINES = 400  # 派生标题只扫日志开头（会话日志可达数万条）
_FS_ROOT_ENV = "AI_AGENT_FS_ROOT"

# 扩展名 → 高亮语言
_LANG_BY_EXT = {
    "py": "python", "js": "javascript", "mjs": "javascript", "cjs": "javascript",
    "ts": "typescript", "tsx": "typescript", "jsx": "javascript", "json": "json",
    "yml": "yaml", "yaml": "yaml", "xml": "xml", "html": "html", "htm": "html",
    "css": "css", "scss": "scss", "md": "markdown", "java": "java", "go": "go",
    "rs": "rust", "sql": "sql", "sh": "bash", "bat": "batch", "cmd": "batch",
    "ps1": "powershell", "toml": "ini", "ini": "ini", "cfg": "ini", "c": "c",
    "h": "c", "cpp": "cpp", "hpp": "cpp", "cs": "csharp", "rb": "ruby",
    "php": "php", "kt": "kotlin", "swift": "swift", "lua": "lua", "r": "r",
}


def _lang_from_path(name: str) -> str:
    """文件名 → 高亮语言标记（未知扩展名返回空串）。"""
    suffix = Path(str(name or "")).suffix.lower().lstrip(".")
    return _LANG_BY_EXT.get(suffix, "")


def _plugin_asset_rel(path: str) -> Optional[Tuple[str, str]]:
    """`/api/plugin/<插件>/_asset/<相对路径>` → `(插件名, 相对路径)`；不是资产路径则 None。"""
    prefix = "/api/plugin/"
    marker = f"/{ASSET_SEGMENT}/"
    if not str(path or "").startswith(prefix):
        return None
    rest = path[len(prefix):]
    idx = rest.find(marker)
    if idx <= 0:
        return None
    plugin = rest[:idx]
    rel = rest[idx + len(marker):]
    if not plugin or not rel or ".." in rel.split("/"):
        return None
    return plugin, rel


def _looks_binary(path: Path) -> bool:
    """粗判二进制（含 NUL 字节即视为二进制；读取失败按文本处理）。"""
    try:
        with path.open("rb") as handle:
            chunk = handle.read(_BINARY_SNIFF_BYTES)
    except OSError:
        return False
    return b"\x00" in chunk


class WebShell:
    """Web 壳：持有一张 SSE 连接表 + 一张会话运行表，服务于共享的 App。"""

    def __init__(
        self,
        app: App,
        media_root: Optional[Path] = None,
        *,
        fs_roots: Any = None,
        titles_dir: Optional[Path] = None,
        title_generator: Any = None,
        workspace_root: Optional[Path] = None,
    ) -> None:
        self.app = app
        self.media_root = Path(media_root).resolve() if media_root else None
        # `/workspace/<相对路径>` 静态路由的根 —— 经典 UI 的 Markdown 渲染会把
        # 工作区绝对路径的图片/视频重写成这个路由（`agent-ui.js` 的
        # `markedImageHref`）。命名沿用，缺省 `<data_root>/workspace`。
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else None
        # 可见根：单个 Path / Path 列表 / None（None = 不限根，仅供测试与显式放开）
        self.fs_roots: List[Path] = _normalize_roots(fs_roots)
        self.titles = TitleStore(Path(titles_dir) if titles_dir else None)
        self.title_generator = title_generator
        self._channels: List[_Channel] = []
        self._lock = threading.Lock()
        self._runs: Dict[str, str] = {}  # cid → run_id（当前活跃回合）
        # 把壳自己交给适配层：它会复用本壳的 `_derive_title` 派生会话标题，
        # 避免适配层另写一套截断口径导致两侧标题不一致。
        try:
            classic = app.context.get(SERVICE_CLASSIC_ADAPTER)
        except Exception:
            classic = None
        if classic is not None:
            classic.adopt_shell(self)

    # ── SSE 连接表 ────────────────────────────────────────

    def attach(self) -> _Channel:
        channel = _Channel()
        with self._lock:
            self._channels.append(channel)
        return channel

    def detach(self, channel: _Channel) -> None:
        channel.close()
        with self._lock:
            if channel in self._channels:
                self._channels.remove(channel)

    def broadcast(self, event: ev.Event) -> None:
        """把内核事件广播到全部 SSE 连接（EventBus 通配订阅者）。"""
        frame = _sse_payload(event)
        if event.type == ev.TURN_STARTED:
            cid = str((event.data or {}).get("conversation_id") or "")
            rid = str((event.data or {}).get("run_id") or "")
            if cid and rid:
                with self._lock:
                    self._runs[cid] = rid
        elif event.type == ev.TURN_ENDED:
            cid = str((event.data or {}).get("conversation_id") or "")
            with self._lock:
                self._runs.pop(cid, None)
        with self._lock:
            channels = list(self._channels)
        for channel in channels:
            channel.push(frame)

    def active_run(self, cid: str) -> str:
        with self._lock:
            return str(self._runs.get(str(cid or "").strip()) or "")

    @property
    def channel_count(self) -> int:
        with self._lock:
            return len(self._channels)

    def available_models(self) -> List[str]:
        """可选的模型 id 列表（**只给 id，绝不给 key / url**）。

        凭据不下发：浏览器能拿到的东西，任何能打开页面的人都能抄走。
        会话选模型选的是"服务端已配置的哪一个 id"，凭据始终留在服务端。
        """
        models = getattr(self.app, "available_models", None)
        if callable(models):
            try:
                return [str(m) for m in (models() or [])]
            except Exception:
                return []
        return []

    # ── 业务动作──────────────────────────────────

    def send(
        self,
        cid: str,
        text: str,
        mode: str = "",
        images: Any = None,
        model: str = "",
    ) -> Tuple[int, Dict[str, Any]]:
        """提交输入：忙则 409，成功则后台回合并立即返回 run_id。

        `images`：可选截图附件，形如 `[{mime, data_base64}]`。仅接受图片 MIME，上限 `MAX_IMAGES` 张；
        **有图无字也算有效输入**（纯截图提问是常见用法）。

        `model`：会话级模型选择（空串 = 不改动既有选择）。**落 `live_state` 持久化** ——
        刷新页面乃至换进程，同一会话选的都是同一个模型。校验放在解析器落位之后，
        未配置的名字一律拒绝（400），避免"选择了却悄悄用默认模型"。
        """
        text = str(text or "").strip()
        attachments = _normalize_images(images)
        if not text and not attachments:
            return 400, {"error": "empty message"}
        cid = str(cid or "").strip()
        if cid and not is_valid_conversation_id(cid):
            return 400, {"error": "invalid conversation_id"}
        if not cid:
            cid = new_conversation_id()
        mode = str(mode or "").strip().lower()
        if mode and mode not in MODE_VALUES:
            return 400, {"error": "invalid mode"}
        if mode:
            self.app.live_state.set_mode(cid, mode)
        want_model = str(model or "").strip()
        if want_model:
            allowed = self.available_models()
            if allowed and want_model not in allowed:
                # 有清单就按清单拒；清单为空（未配置）时不拦，交由 provider 决定
                return 400, {"error": f"unknown model: {want_model}"}
            self.app.live_state.set_model(cid, want_model)
        # 忙闲事实源 = mesh 活跃集：同会话并发 → 409
        if self.app.mesh.is_running(cid):
            return 409, {"error": "当前会话仍在执行中，请等待完成或先停止。"}
        payload: Dict[str, Any] = {"content": text}
        if attachments:
            payload["attachments"] = attachments
        started = self.app.runner.start(cid, payload)
        if not started:
            return 409, {"error": "当前会话仍在执行中，请等待完成或先停止。"}
        return 200, {
            "ok": True,
            "conversation_id": cid,
            "run_id": started,
            "queued": False,
        }

    def history(self, cid: str) -> Tuple[int, Dict[str, Any]]:
        """会话历史投影（从事实源 derive）。"""
        cid = str(cid or "").strip()
        store = self.app.store
        if store is None:
            return 200, {"conversation_id": cid, "events": []}
        return 200, {
            "conversation_id": cid,
            "events": [
                {"type": e.type, **dict(e.data or {})}
                for e in store.load(cid)
            ],
        }

    def sessions(self) -> Tuple[int, Dict[str, Any]]:
        """会话名录（含派生标题）。

        标题 = 该会话首条用户输入的前 40 字（纯字符串派生，不调用模型）；无输入则留空，
        由前端回落显示短 id。按最近活动排序（.raw 修改时间倒序）。
        """
        store = self.app.store
        rows: List[Dict[str, Any]] = []
        root = getattr(store, "data_root", None)
        if store is not None and root is not None:
            directory = Path(root) / "sessions"
            if directory.is_dir():
                entries = []
                for path in directory.glob("*.raw"):
                    cid = path.stem
                    if not is_valid_conversation_id(cid):
                        continue
                    try:
                        mtime = path.stat().st_mtime
                    except OSError:
                        mtime = 0.0
                    entries.append((mtime, cid))
                for mtime, cid in sorted(entries, reverse=True):
                    rows.append(
                        {
                            "conversation_id": cid,
                            "short_id": cid[:8],
                            "title": self._derive_title(cid),
                            "mtime": int(mtime),
                            # 日期分组
                            "date_group": _date_group(mtime),
                        }
                    )
        return 200, {"sessions": [r["conversation_id"] for r in rows], "items": rows}

    def _derive_title(self, cid: str) -> str:
        """会话标题：优先已生成并落盘的标题，其次从事实源派生（首条用户输入）。

        会话日志可达数万条事件，**标题只需要开头**——故只读文件前若干行
        （`_TITLE_SCAN_LINES`），不整档 load；超限则退化为空（由前端显示短 id）。
        """
        stored = self.titles.load(cid) if self.titles is not None else ""
        if stored and not is_placeholder_title(stored):
            return stored
        store = self.app.store
        if store is None:
            return ""
        try:
            path = store.raw_path(cid)
        except (ValueError, AttributeError):
            return ""
        if not path.is_file():
            return ""
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for index, line in enumerate(handle):
                    if index >= _TITLE_SCAN_LINES:
                        break
                    try:
                        payload = json.loads(line)
                    except (TypeError, ValueError):
                        continue
                    if not isinstance(payload, dict):
                        continue
                    # 落盘行的键名取自 store 的 `_KEY_TYPE` / `_KEY_DATA`：
                    # 硬编码字符串会随键名改动静默失配，标题悄悄退化成空。
                    if payload.get(_KEY_TYPE) != "input_claimed":
                        continue
                    body = payload.get(_KEY_DATA)
                    if not isinstance(body, dict):
                        continue
                    text = str(body.get("content") or "").strip()
                    if text:
                        text = " ".join(text.split())
                        return text[:40] + ("…" if len(text) > 40 else "")
        except OSError:
            return ""
        return ""

    def title(self, cid: str) -> Tuple[int, Dict[str, Any]]:
        """生成 / 读取会话标题。

        已生成过则直接返回；否则调用模型一次（无工具）→ 清洗 → 落盘；生成失败回落派生标题。
        """
        cid = str(cid or "").strip()
        if not cid:
            return 400, {"error": "missing conversation_id"}
        if not is_valid_conversation_id(cid):
            return 400, {"error": "invalid conversation_id"}
        existing = self.titles.load(cid) if self.titles is not None else ""
        if existing and not is_placeholder_title(existing):
            return 200, {"ok": True, "conversation_id": cid, "title": existing, "cached": True}

        messages = self._conversation_messages(cid)
        generated = ""
        if self.title_generator is not None:
            try:
                generated = self.title_generator(messages)
            except Exception as exc:  # 旁路增强：不因标题失败而报错
                print(f"[web] 标题生成异常（已回退）: {exc}", file=sys.stderr, flush=True)
        title = generated if generated and not is_placeholder_title(generated) else fallback_title(messages)
        if title and self.titles is not None:
            self.titles.save(cid, title)
        return 200, {"ok": True, "conversation_id": cid, "title": title, "cached": False}

    def _conversation_messages(self, cid: str) -> List[Dict[str, Any]]:
        """事实源 → 模型消息序列（标题生成素材）。"""
        store = self.app.store
        if store is None:
            return []
        try:
            events = store.load(cid)
        except Exception:
            return []
        messages: List[Dict[str, Any]] = []
        for event in events:
            data = event.data or {}
            if event.type == "input_claimed":
                content = str(data.get("content") or "").strip()
                if content:
                    messages.append({"role": "user", "content": content})
            elif event.type == "model_message":
                content = str(data.get("content") or "").strip()
                if content:
                    messages.append({"role": "assistant", "content": content})
        return messages

    # ── 插件贡献（右栏面板）──

    def panel_list(self) -> List[Dict[str, Any]]:
        """插件贡献的面板清单；界面按它动态建标签，不为每个插件加分支。

        内置步骤栏由页面静态声明（常驻、内核自有），不由本端点返回。
        """
        host = getattr(self.app, "plugin_host", None)
        contribs = getattr(host, "contributions", None) if host is not None else None
        if contribs is None:
            return []
        return [p.as_dict() for p in contribs.all_panels()]

    def action_list(self) -> List[Dict[str, Any]]:
        """插件贡献的输入区动作（输入框下面的按钮）。

        界面按它渲染按钮，点开哪个面板由贡献里的 `panel` 指定 ——
        内核与页面都不写死任何插件入口。
        """
        host = getattr(self.app, "plugin_host", None)
        contribs = getattr(host, "contributions", None) if host is not None else None
        if contribs is None:
            return []
        return [a.as_dict() for a in contribs.all_actions()]

    def tool_list(self) -> List[Dict[str, Any]]:
        """工具展示清单：`[{name, label, icon}]`（来自工具自己的声明）。

        界面据此认识**所有**工具（含插件工具），不必在前端维护工具名表 ——
        加一个插件工具不需要改界面。
        """
        registry = getattr(self.app, "registry", None)
        if registry is None or not hasattr(registry, "display_list"):
            return []
        return registry.display_list()

    # ── 右栏文件查看器（文本 / 代码 / 表格）──

    def fs_list(self, path: str) -> Tuple[int, Dict[str, Any]]:
        """列目录（供右栏文件树 / @ 补全）；限定在可见根内。

        `rel` 是相对**命中的那个根**的路径；命不中根时退回文件名。
        """
        target, reason = self._resolve_fs(path or ".", must_exist=True)
        if target is None:
            return _fs_rejection(reason)
        if not target.is_dir():
            return 400, {"error": "not a directory"}
        entries: List[Dict[str, Any]] = []
        try:
            for child in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
                if child.name.startswith("."):
                    continue
                try:
                    stat = child.stat()
                except OSError:
                    continue
                entries.append(
                    {
                        "name": child.name,
                        "path": str(child),
                        "rel": self._rel_to_root(child),
                        "type": "dir" if child.is_dir() else "file",
                        "size": int(stat.st_size),
                        "mtime": int(stat.st_mtime),
                    }
                )
        except OSError as exc:
            return 500, {"error": f"{type(exc).__name__}"}
        return 200, {"path": str(target), "entries": entries}

    def fs_read(self, path: str, max_chars: int = 400000) -> Tuple[int, Dict[str, Any]]:
        """读文件（供右栏标签页）；文本 / 代码直读，xlsx 转表格，二进制给结构化提示。"""
        target, reason = self._resolve_fs(path, must_exist=True)
        if target is None:
            return _fs_rejection(reason)
        if not target.is_file():
            return 404, {"error": "not a file"}
        suffix = target.suffix.lower()
        if suffix in (".xlsx", ".xlsm", ".xls"):
            return self._read_table(target)
        if _looks_binary(target):
            return 200, {
                "path": str(target),
                "kind": "binary",
                "size": target.stat().st_size,
                "message": "二进制文件不在此处预览（图片 / 音视频请用媒体代理 /api/media）",
            }
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return 500, {"error": f"{type(exc).__name__}"}
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars]
        try:
            stat = target.stat()
        except OSError:
            stat = None
        return 200, {
            "path": str(target),
            "kind": "text",
            "lang": _lang_from_path(target.name),
            "content": text,
            "truncated": truncated,
            "size": int(stat.st_size) if stat else len(text.encode("utf-8")),
            "mtime": int(stat.st_mtime) if stat else 0,
        }

    def _read_table(self, target: Path) -> Tuple[int, Dict[str, Any]]:
        """xlsx/xls → 表格数据（缺 openpyxl 时给结构化提示，不报错）。"""
        try:
            import openpyxl  # type: ignore
        except Exception:
            return 200, {
                "path": str(target),
                "kind": "table",
                "message": "读取 xlsx 需要 openpyxl：pip install openpyxl",
                "sheets": [],
            }
        try:
            book = openpyxl.load_workbook(str(target), read_only=True, data_only=True)
        except Exception as exc:
            return 200, {
                "path": str(target),
                "kind": "table",
                "message": f"工作簿读取失败：{type(exc).__name__}: {exc}",
                "sheets": [],
            }
        sheets: List[Dict[str, Any]] = []
        try:
            for name in book.sheetnames:
                sheet = book[name]
                rows: List[List[str]] = []
                for index, row in enumerate(sheet.iter_rows(values_only=True)):
                    if index >= 500:
                        break
                    rows.append(["" if cell is None else str(cell) for cell in row])
                sheets.append({"name": name, "rows": rows})
        finally:
            try:
                book.close()
            except Exception:
                pass
        return 200, {"path": str(target), "kind": "table", "sheets": sheets}

    # ── 推理档位（GET|PUT /api/reasoning-effort）──

    def reasoning_effort_get(self, cid: str) -> Tuple[int, Dict[str, Any]]:
        """读会话级推理档位；同时给出全局默认。"""
        state = self.app.live_state
        if state is None:
            fallback = get_reasoning_effort()
            return 200, {"ok": True, "reasoning_effort": fallback, "global_default": fallback}
        cid = str(cid or "").strip()
        return 200, {
            "ok": True,
            "reasoning_effort": state.get_reasoning_effort(cid),
            "global_default": state.default_effort,
        }

    def reasoning_effort_set(self, cid: str, effort: str) -> Tuple[int, Dict[str, Any]]:
        """设置会话级推理档位。缺 cid 或非法值 → `ok:False`。"""
        state = self.app.live_state
        cid = str(cid or "").strip()
        if not cid:
            return 200, {"ok": False, "error": "conversation_id required"}
        if state is None:
            return 200, {"ok": False, "error": "live_state 不可用"}
        ok = state.set_reasoning_effort(cid, effort)
        return 200, {
            "ok": bool(ok),
            "reasoning_effort": state.get_reasoning_effort(cid),
        }

    # ── 自主模式──

    def autonomous(self, cid: str, enabled: Any) -> Tuple[int, Dict[str, Any]]:
        """开关会话自主模式：开启后回合结束会自动续跑（`SessionRunner.auto_continue`）。"""
        state = self.app.live_state
        cid = str(cid or "").strip()
        if not cid:
            return 200, {"ok": False, "error": "conversation_id required"}
        if state is None:
            return 200, {"ok": False, "error": "live_state 不可用"}
        state.set_autonomy(cid, bool(enabled))
        return 200, {"ok": True, "autonomy": state.get_autonomy(cid)}

    # ── 目录浏览（供 `@` 文件补全；GET /api/dir-browse）──

    def _browse_base(self) -> Path:
        """`@` 补全 / 相对路径的基准目录。

        可见根可能是「本机各盘根」这种很宽的范围，直接拿第一个当基准会让相对路径落在
        盘根（`agent/core` 会变成 `C:/`）。所以按具体程度挑：
        项目根（若在可见范围内）→ 进程工作目录（若在范围内）→ 第一个可见根。
        """
        roots = self.fs_roots or _default_fs_roots()
        if not roots:
            return Path.cwd()

        def inside(candidate: Path) -> bool:
            try:
                resolved = candidate.resolve()
            except OSError:
                return False
            for root in roots:
                try:
                    resolved.relative_to(root)
                    return True
                except ValueError:
                    continue
            return False

        # 显式给出的第一个根通常就是用户有意指定的工作区（夹具 / --fs-root），优先它；
        # 只有它是"太宽的根"（盘根）时才往下找更具体的位置。
        first = roots[0]
        if not _is_drive_root(first) and first.is_dir():
            return first
        for candidate in (PROJECT_ROOT, Path.cwd()):
            if candidate.is_dir() and inside(candidate):
                return candidate.resolve()
        return first

    def dir_browse(self, path: str) -> Tuple[int, Dict[str, Any]]:
        """列目录供 `@` 补全：`{current, parent, items:[{name,type,ext,path}]}`。

        语义：
          - `path="_drives_"` → 列出本机盘符（Windows「计算机」层）；
          - 盘符根（如 `D:/`）的 `parent` 也是 `_drives_`（可从盘根回到计算机层）；
          - 空 `path` → `_browse_base()` 给出的基准目录；
          - 目录排前、名称不区分大小写升序；
          - **访问不到就回落**（不报错），免得上层补全卡死。
        """
        base = self._browse_base()
        raw = str(path or "").strip()

        if raw == "_drives_":
            return 200, {"current": "计算机", "parent": "", "items": _list_drives()}

        if not raw:
            target = base
        else:
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = base / candidate
            try:
                resolved = candidate.resolve()
            except OSError:
                resolved = base
            target = resolved if resolved.is_dir() else base

        items: List[Dict[str, Any]] = []
        try:
            entries = sorted(
                (e for e in os.scandir(str(target)) if not e.name.startswith(".")),
                key=lambda e: (not e.is_dir(), e.name.lower()),
            )
        except OSError:
            entries = []
        for entry in entries[:1000]:
            try:
                is_dir = entry.is_dir()
            except OSError:
                continue
            items.append({
                "name": entry.name,
                "type": "dir" if is_dir else "file",
                "ext": os.path.splitext(entry.name)[1].lower(),
                "path": os.path.abspath(entry.path).replace("\\", "/"),
            })

        current = str(target).replace("\\", "/")
        stripped = current.rstrip("/")
        # 盘符根（"D:"）→ 上一级是「计算机」层
        if len(stripped) == 2 and stripped[1] == ":":
            parent = "_drives_"
        else:
            try:
                parent = str(Path(stripped).resolve().parent).replace("\\", "/")
            except OSError:
                parent = ""
        return 200, {"current": current, "parent": parent, "items": items}

    # ── 模型计价（用量底栏的费用换算）──────────────

    def model_pricing(self, model: str) -> Tuple[int, Dict[str, Any]]:
        """返回某模型的费率（元/百万 tokens）；查不到 → `ok:False`（UI 显示"未查到"）。"""
        pricing = getattr(self.app, "model_pricing", None)
        name = str(model or "").strip()
        if not name:
            name = str(getattr(self.app.provider, "model", "") or "")
        if pricing is None:
            return 200, {"ok": False, "model": name, "error": "pricing 不可用"}
        return 200, pricing.payload(name)

    def _rel_to_root(self, target: Path) -> str:
        """相对命中的那个可见根的路径；命不中根时退回文件名。"""
        try:
            resolved = target.resolve()
        except OSError:
            return target.name
        for root in self.fs_roots:
            try:
                return str(resolved.relative_to(root))
            except ValueError:
                continue
        return target.name

    def _resolve_fs(self, path: str, *, must_exist: bool) -> Tuple[Optional[Path], str]:
        """把请求路径解析到某个可见根内（防越权读盘）。

        返回 `(目标, 原因)`；原因为 `""` 表示成功，否则是拒绝理由：
          - `"outside"`：不在任何可见根内（403，安全边界）
          - `"missing"`：在可见根内但不存在（404，状态边界）
          - `"unknown"`：路径无法解析

        相对路径依次在**每个根**下试（命中即用）；绝对路径只有落在某个根内才接受——
        工具参数常带绝对路径（如 D:\\proj\\a.py、E:\\test.txt），查看器应能直接打开。
        越界与"不存在"必须分开报告：预览阶段尚未落盘的文件是 404，不是越权。
        """
        roots = self.fs_roots
        raw = str(path or "").strip()
        if not raw:
            return None, "unknown"

        def inside(candidate: Path) -> bool:
            if not roots:
                return True
            try:
                resolved = candidate.resolve()
            except OSError:
                return False
            for root in roots:
                try:
                    resolved.relative_to(root)
                    return True
                except ValueError:
                    continue
            return False

        candidate = Path(raw)
        if not candidate.is_absolute():
            # 相对路径：逐个根试，取第一个"存在"的；都不存在则报 missing
            for root in roots or [Path.cwd()]:
                joined = root / candidate
                if inside(joined):
                    if joined.exists():
                        return joined.resolve(), ""
            return None, "missing"

        if not inside(candidate):
            return None, "outside"
        if must_exist and not candidate.exists():
            return None, "missing"
        try:
            return candidate.resolve(), ""
        except OSError:
            return None, "unknown"

    def ui_state(self, cid: str) -> Tuple[int, Dict[str, Any]]:
        """UI 状态快照（模式 / todo / 自主 / 模型；落点 = live_state 按 cid）。"""
        cid = str(cid or "").strip()
        live = self.app.live_state
        return 200, {
            "conversation_id": cid,
            "mode": live.get_mode(cid),
            "todo": live.get_todo(cid),
            "autonomy": live.get_autonomy(cid),
            # 目标（Goal）：前端"目标"按钮据此回填状态；无目标时为 None。
            "goal": live.get_goal(cid),
            # 模型选择与可选清单：前端据此回填下拉（刷新后不丢）。
            # 只给 id —— 凭据（key / url）始终留在服务端。
            "model": live.get_model(cid),
            "available_models": self.available_models(),
            "running": self.app.mesh.is_running(cid),
            # 也在跑的全部会话（供中途接入的页面拉 `/api/chat/ui-state` 回填忙闲）。
            "running_cids": self.app.mesh.running_cids(),
        }

    def ui_state_put(self, cid: str, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        cid = str(cid or "").strip()
        mode = str(payload.get("mode") or "").strip().lower()
        if mode:
            if mode not in MODE_VALUES:
                return 400, {"error": "invalid mode"}
            self.app.live_state.set_mode(cid, mode)
        if "model" in payload:
            want = str(payload.get("model") or "").strip()
            allowed = self.available_models()
            if want and allowed and want not in allowed:
                return 400, {"error": f"unknown model: {want}"}
            self.app.live_state.set_model(cid, want)
        return self.ui_state(cid)

    def confirm(self, cid: str, confirm_id: str) -> Tuple[int, Dict[str, Any]]:
        """确认一个写盘预览：**按 cid 解析会话门控**，不落默认桶。"""
        cid = str(cid or "").strip()
        confirm_id = str(confirm_id or "").strip()
        if not cid:
            return 400, {"error": "missing conversation_id"}
        if not confirm_id:
            return 400, {"error": "missing confirm_id"}
        gate = self.app.gate_for(cid)
        ok = bool(gate.confirm(confirm_id))
        if not ok:
            return 404, {
                "confirmed": False,
                "error": "confirm_id 无效、已消耗或不属于该会话",
            }
        return 200, {"confirmed": True, "conversation_id": cid, "confirm_id": confirm_id}

    def stop(self, cid: str) -> Tuple[int, Dict[str, Any]]:
        """请求停止当前回合（协作式取消）。

        经 `SessionRunner.request_cancel` 置位取消信号 → 内核在检查点（流式每帧 /
        工具执行前 / 步结算前）停止本轮，不再产生半成品落盘。这里不直接调
        `mesh.abort_run`：占位须由运行线程自己释放，否则忙闲事实源与实际线程不一致。
        """
        cid = str(cid or "").strip()
        if not cid:
            return 400, {"error": "missing conversation_id"}
        run_id = self.active_run(cid)
        runner = self.app.runner
        requested = bool(runner.request_cancel(cid)) if runner is not None else False
        return 200, {
            "stop_requested": requested,
            "conversation_id": cid,
            "run_id": run_id,
        }

    def health(self) -> Tuple[int, Dict[str, Any]]:
        """服务健康 + 顶栏所需的模型信息。"""
        provider = self.app.provider
        model = str(getattr(provider, "model", "") or "")
        # 可选模型清单必须以装配面的清单为准（`config.ini` 的 `[model_reasoning] models`）：
        # provider 可能不持有 `allowed_models` 属性，只回一个模型会让前端模型下拉只剩一项，
        # 用户选其它模型还会被当非法拒掉。
        allowed = self.available_models()
        if not allowed:
            allowed = list(getattr(provider, "allowed_models", ()) or ())
            if not allowed:
                name = str(getattr(provider, "model", "") or "")
                allowed = [name] if name else []
        # 无白名单清单时把当前模型作为唯一候选下发（前端据此渲染模型菜单）；
        # 真正的多模型名单由装配面的配置提供。
        if not allowed and model:
            allowed = [model]
        return 200, {
            "ok": True,
            "service": "agent.web",
            "conversation_buckets": (
                self.app.session_contexts.active_count()
                if self.app.session_contexts is not None
                else 0
            ),
            "sse_channels": self.channel_count,
            "tools": len(self.app.registry.names()),
            "model": model,
            "allowed_models": allowed,
        }

    # ── 媒体（本地绝对路径 → 浏览器可访问）──

    def media(self, path: str, root: Optional[Path]) -> Tuple[int, Any, str]:
        """解析本地媒体文件供浏览器预览；限定在 root 之内（防越权读取）。

        返回 (status, body_bytes | error_payload, content_type)。

        `root` 为 None 时改用**全部可见根**：经典界面的 Markdown 会把正文里
        绝对路径指向的本地文件交给 `/api/media`，而它可能不在第一个根所在的盘上
        —— 只认单根会让别的盘一律 403。
        """
        raw = str(path or "").strip()
        if not raw:
            return 400, {"error": "missing path"}, "application/json"
        target = Path(raw)
        if root is None:
            if not _within_any_root(target, self.fs_roots or _default_fs_roots()):
                return 403, {"error": "path outside media root"}, "application/json"
        else:
            try:
                target.resolve().relative_to(Path(root).resolve())
            except (ValueError, OSError):
                return 403, {"error": "path outside media root"}, "application/json"
        if not target.is_file():
            return 404, {"error": "not found"}, "application/json"
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        try:
            return 200, target.read_bytes(), ctype
        except OSError as exc:
            return 500, {"error": f"{type(exc).__name__}"}, "application/json"


class _Handler(BaseHTTPRequestHandler):
    """路由分发。"""

    server_version = "ai-agent-web/1.0"
    protocol_version = "HTTP/1.1"

    # 由 serve() 注入
    shell: WebShell
    assets_dir: Path

    # ── 工具 ──────────────────────────────────────────────

    def handle_one_request(self) -> None:
        """读下一条请求行时，客户端提前断开**不算错误**。

        每次 SSE 连接被浏览器关掉（刷新标签、关标签、探针读够就走）时，
        `BaseHTTPRequestHandler.handle_one_request` 在**读下一条请求行**时抛
        `ConnectionAbortedError [WinError 10053]`，`socketserver` 把它当"处理请求时
        发生异常"打**整屏 traceback**。而 `_events_stream` 里已经吞掉了同类异常 ——
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

        路径必须是**该插件目录下的真实文件**：先解析绝对路径，再校验它落在插件目录内
        （挡 `..` 与符号链接绕行）。只送文本类脚本，不送任意文件。
        """
        host = getattr(self.shell.app, "plugin_host", None) if self.shell.app else None
        base = getattr(host, "plugins_dir", None) if host is not None else None
        if base is None:
            self._json(404, {"error": "插件目录未接入"})
            return
        root = (Path(base) / plugin).resolve()
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
        if app is None:
            return None
        try:
            return app.context.get(SERVICE_CLASSIC_ADAPTER)
        except Exception:
            return None

    def _classic_page(self) -> None:
        """经典界面页面：把经典界面素材内联成单页返回。"""
        from agent.shell.ui_bundle import APP_VERSION, inline_ui_html

        html = inline_ui_html(APP_VERSION)
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _classic_sse(self, query: Dict[str, str]) -> None:
        """事件流。两种格式任选，**默认经典界面格式**：

        - 默认（无 `format` 或 `format=classic`）：适配层翻译过的老事件
          （`conversation` / `tool_start` / `llm_round` …），经典 UI 用这条。
        - `format=kernel`：内核原生事件（`turn_started` / `tool_call` …）原样透传。
          给测试、运维探针，以及**未来的其它交互层**（命令行等）用——
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
        # 坐标是**全局单调**的，所以一个游标就够了——不需要客户端告诉服务端"续哪个会话"，
        # 浏览器的 `EventSource` 也就无需任何定制。
        # **没有游标就不续传**：经典界面各自 `GET /api/chat/history` 渲染已有内容，
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
                # 经典界面的 GET **不带 conversation_id**（agent-ui.js:186），
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
                self._json(200, {"ok": True, "panels": self.shell.panel_list()})
            elif path == "/api/actions":
                # 插件贡献的输入区动作（输入框下面的按钮）；不声明就没有按钮
                self._json(200, {"ok": True, "actions": self.shell.action_list()})
            elif path == "/api/tool-labels":
                # 工具展示清单（中文名 + 图标）：由工具自己声明，界面不维护工具名表
                self._json(200, {"ok": True, "tools": self.shell.tool_list()})
            elif path.startswith("/api/plugin/"):
                # 插件自己的端点：命名空间内匹配声明过的路径形状（`:名字` 段可由请求填值）
                self._plugin_route("GET")
            elif path == "/api/dir-browse":
                status, payload = self.shell.dir_browse(query.get("path", ""))
                self._json(status, payload)
            elif path == "/api/model-pricing":
                status, payload = self.shell.model_pricing(query.get("model", ""))
                self._json(status, payload)
            elif path == "/api/reasoning-effort":
                status, payload = self.shell.reasoning_effort_get(
                    query.get("conversation_id", "")
                )
                self._json(status, payload)
            elif path == "/api/media":
                # 传 None：按**全部可见根**校验。`media_root` 只覆盖第一个盘根，
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
                # 确认端点承载**两类**请求（经典界面两种情况共用一个端点）：
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
                        # 「保存」只改文案：paused/done 保持原状态，
                        # （那会让"只想改个字"变成重开自动续跑），也不要清掉备注。
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
            else:
                self._json(404, {"error": "not found", "path": path})
        except Exception as exc:
            self._safe_error(exc)

    def do_PUT(self) -> None:  # HTTP 动词命名（stdlib 约定）
        try:
            path = self._path()
            body = self._read_body()
            if path == "/api/chat/ui-state":
                # 经典界面的 PUT 直接发布局对象（agent-ui.js:1173），**不带 conversation_id**；
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
        """DELETE 只有插件端点会用（撤销任务 / 清插件自己的缓存）。"""
        try:
            path = self._path()
            if path.startswith("/api/plugin/"):
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


def _normalize_images(raw: Any) -> List[Dict[str, str]]:
    """校验并归一化截图附件。

    只接受 `{mime, data_base64}` 且 `mime` 为图片类型；超过 `MAX_IMAGES` 截断；
    非法项静默丢弃（附件是增强项，不应因单张坏图整体失败）。
    """
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, str]] = []
    for item in raw:
        if len(out) >= MAX_IMAGES:
            break
        if not isinstance(item, dict):
            continue
        mime = str(item.get("mime") or "").strip().lower()
        data = item.get("data_base64")
        if not isinstance(data, str) or not data.strip():
            continue
        if mime not in _IMAGE_MIMES:
            continue
        out.append({"mime": mime, "data_base64": data.strip()})
    return out


def _date_group(mtime: float, now: Optional[float] = None) -> str:
    """把修改时间归入中文日期分组。

    分组：今天 / 昨天 / `xx月xx日`（按自然日比较，不按 24 小时）。
    """
    if not mtime:
        return ""
    reference = time.time() if now is None else now
    try:
        stamp = time.localtime(mtime)
        today = time.localtime(reference)
    except (OverflowError, OSError, ValueError):
        return ""
    day = (stamp.tm_year, stamp.tm_yday)
    today_day = (today.tm_year, today.tm_yday)
    if day == today_day:
        return "今天"
    # 昨天：把参考时间倒退一天比较（跨年由 tm_year 一起比对）
    yesterday = time.localtime(reference - 86400)
    if day == (yesterday.tm_year, yesterday.tm_yday):
        return "昨天"
    # 更早的按具体日期分组：「本周」「更早」看不出是哪天。
    return f"{stamp.tm_mon}月{stamp.tm_mday}日"


def create_server(
    app: App,
    host: str = "127.0.0.1",
    port: int = 8765,
    assets_dir: Optional[Path] = None,
    media_root: Optional[Path] = None,
    fs_root: Any = None,
    titles_dir: Optional[Path] = None,
    title_generator: Any = None,
    workspace_root: Optional[Path] = None,
) -> Tuple[ThreadingHTTPServer, WebShell]:
    """构造（不启动）Web 服务；返回 (server, shell)。调 server.serve_forever() 启动。

    media_root：`/api/media` 可读取的根（缺省 = 文件可见根；防越权读盘）。
    fs_root：右栏文件查看器（`/api/fs/*`）的可见根，可传单个路径或路径列表；
        缺省 = `_default_fs_roots()` 给出的本机各盘根——与 agent 的实际读写范围对齐。
    titles_dir / title_generator：会话标题落盘目录与生成器（缺省按 app 的 provider 装配）。
    workspace_root：`/workspace/<相对路径>` 静态路由的根（经典 UI 的 Markdown 渲染
        会把工作区图片/视频重写成该路由）；缺省 `None` = 该路由返回 404。
    """
    if title_generator is None and app.provider is not None:
        title_generator = make_provider_title_generator(app.provider)
    roots = _normalize_roots(fs_root) or _default_fs_roots()
    shell = WebShell(
        app,
        media_root=media_root or (roots[0] if roots else Path.cwd()),
        fs_roots=roots,
        titles_dir=titles_dir,
        title_generator=title_generator,
        workspace_root=workspace_root,
    )
    # SSE 承载：订阅事件总线（通配）——旁路纪律，不影响控制流
    bus = app.event_bus
    if bus is not None:
        bus.subscribe_all(shell.broadcast)

    handler = type(
        "_BoundHandler",
        (_Handler,),
        {"shell": shell, "assets_dir": Path(assets_dir) if assets_dir else ASSETS_DIR},
    )
    # **必须关掉 `allow_reuse_address`，否则"绑不上就报错"根本不会发生**。
    #
    # ⚠️ 只加 `try/except OSError` 挡不住同端口二次绑定：
    # `ThreadingHTTPServer` 继承的 `allow_reuse_address = 1` 在 Windows 上会让
    # **同端口二次 bind 成功**（跨进程：别的进程已 LISTEN，本进程仍绑得上）。
    # 后果比"影子服务抢流量"更坏：**先绑的服务继续收全部连接，后绑的永远收不到请求**
    # —— 实际生效的是哪个进程，只由绑定时序决定。
    # 关掉它之后，二次 bind 会抛 `WinError 10048`，`except` 才真的会命中。
    class _Server(ThreadingHTTPServer):
        allow_reuse_address = False

    try:
        server = _Server((host, int(port)), handler)
    except OSError as exc:
        print(f"[web] 无法绑定 {host}:{port} —— {exc}", file=sys.stderr, flush=True)
        print("[web] 端口已被占用。请换端口；并注意**改代码后必须重启服务**，"
              "否则连上的仍是旧代码（`ui_bundle.inline_ui_html` 还有 `lru_cache`，"
              "连 JS 都要重启才生效）。", file=sys.stderr, flush=True)
        raise
    server.daemon_threads = True
    return server, shell


def build_shell_app(
    *,
    provider: Any = None,
    store: Any = None,
    data_root: Optional[Path] = None,
) -> App:
    """装配供 Web 壳使用的底座：默认真实 provider（按 config）+ 会话存储。"""
    if provider is None:
        cfg = get_model_reasoning()
        if not cfg["api_key"] or not cfg["api_base_url"]:
            raise RuntimeError(
                "缺少配置：config.ini 的 [model_reasoning]（api_base_url / api_key / model）"
            )
        provider = OpenAICompatibleProvider(
            base_url=cfg["api_base_url"], api_key=cfg["api_key"], model=cfg["model"]
        )
    if store is None:
        store = SessionStore(Path(data_root) if data_root else default_data_root())
    return build_app(provider=provider, store=store)


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    provider: Any = None,
    store: Any = None,
    data_root: Optional[Path] = None,
    media_root: Optional[Path] = None,
    fs_root: Any = None,
) -> int:
    """启动 Web 壳（阻塞）；Ctrl+C 退出。"""
    root = Path(data_root) if data_root else default_data_root()
    try:
        app = build_shell_app(provider=provider, store=store, data_root=root)
    except RuntimeError as exc:
        print(str(exc))
        return 2
    # 可见根优先级：显式参数 > 环境变量 > `_default_fs_roots()`（本机各盘根）
    roots = _normalize_roots(fs_root) or _env_roots("AI_AGENT_FS_ROOT") or _default_fs_roots()
    resolved_media = media_root or _env_path("AI_AGENT_MEDIA_ROOT") or (roots[0] if roots else Path.cwd())
    server, _shell = create_server(
        app,
        host=host,
        port=port,
        media_root=resolved_media,
        fs_root=roots,
        titles_dir=root / "titles",
        # 经典 UI 的 Markdown 渲染把工作区图片重写成 `/workspace/<rel>`，
        # 根取数据根下的 workspace/。
        workspace_root=root / "workspace",
    )
    print("=== AI Agent Web 壳 ===")
    print(f"主界面   http://{host}:{port}/")
    print(f"事件流   http://{host}:{port}/api/events/stream")
    shown = "；".join(str(r) for r in roots) if roots else "（不限根）"
    print(f"文件根   {shown}")
    print("         （右栏查看器 / @ 补全的可见范围；--fs-root 可改，多个用 ; 分隔）")
    print("（Ctrl+C 退出）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[已停止]")
    finally:
        server.shutdown()
        server.server_close()
        app.dispose()  # 会话运行态 + 进程级服务逆序清理
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="agent.shell.web", description="AI Agent Web 壳")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-root", default="")
    parser.add_argument(
        "--fs-root",
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "右栏文件查看器 / @ 补全的可见根；可重复指定多个。"
            f"默认 = 本机各盘根（与 agent 的读写范围一致）。亦可用 {_FS_ROOT_ENV}（{os.pathsep} 分隔）"
        ),
    )
    parser.add_argument(
        "--media-root",
        default="",
        help="/api/media 可读根（默认与第一个 --fs-root 相同）",
    )
    # 内核只有一个，不接受 `--kernel`：传入时由 argparse 直接报错，不会被静默忽略。
    args = parser.parse_args(list(argv) if argv is not None else None)
    return serve(
        host=args.host,
        port=args.port,
        data_root=Path(args.data_root) if args.data_root else None,
        fs_root=[Path(p) for p in args.fs_root] if args.fs_root else None,
        media_root=Path(args.media_root) if args.media_root else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())