# -*- coding: utf-8 -*-
"""Web JSON API：会话 / 聊天 / 设置等业务动作（WebShell）。"""
from __future__ import annotations

import json
import mimetypes
import os
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:  # 只为注解：壳层不得在运行期依赖装配根（A2）
    from agent.app import App

from agent.config import PROJECT_ROOT, get_reasoning_effort
from agent.core import event_name as ev
from agent.core.input_attachments import MAX_IMAGES, normalize_images
from agent.mechanisms.conversation_queue import QueueError
from agent.mechanisms.session_store import (
    KEY_DATA,
    KEY_TYPE,
    is_valid_conversation_id,
    new_conversation_id,
)
from agent.mechanisms.session_title import (
    TitleStore,
    fallback_title,
    is_placeholder_title,
)
from agent.shell.fspaths import (
    _default_fs_roots,
    _fs_rejection,
    _is_drive_root,
    _list_drives,
    _normalize_roots,
    _within_any_root,
)
from agent.shell.service_keys import SERVICE_CLASSIC_ADAPTER
from agent.shell.sse import _Channel, _sse_payload
from agent.shell.timefmt import date_group
from agent.shell.web_static import (
    _TITLE_SCAN_LINES,
    MODE_VALUES,
    _lang_from_path,
    _looks_binary,
)


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
        ctx = getattr(app, "context", None)
        classic = (
            ctx.get(SERVICE_CLASSIC_ADAPTER)
            if ctx is not None and ctx.has(SERVICE_CLASSIC_ADAPTER)
            else None
        )
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

    def _announce_model(self, cid: str, model: str) -> None:
        """把模型变化广播给同会话的其它标签页（与 announce_plugins 同构）。

        只有发起方写服务端；接收方只更新页头与本地 tab 字段，不再回写，
        否则两个标签页会互相触发写服务端，形成重复写与竞态。
        """
        ctx = getattr(self.app, "context", None)
        classic = (
            ctx.get(SERVICE_CLASSIC_ADAPTER)
            if ctx is not None and ctx.has(SERVICE_CLASSIC_ADAPTER)
            else None
        )
        announce = getattr(classic, "announce_model", None) if classic is not None else None
        if callable(announce):
            announce(cid, model)

    def active_run(self, cid: str) -> str:
        with self._lock:
            return str(self._runs.get(str(cid or "").strip()) or "")

    @property
    def channel_count(self) -> int:
        with self._lock:
            return len(self._channels)

    def available_models(self) -> List[str]:
        """可选的模型 id 列表（只给 id，绝不给 key / url）。

        凭据不下发：浏览器能拿到的东西，任何能打开页面的人都能抄走。
        会话选模型选的是"服务端已配置的哪一个 id"，凭据始终留在服务端。
        """
        models = getattr(self.app, "available_models", None)
        if callable(models):
            return [str(m) for m in (models() or [])]
        return []

    # ── 业务动作──────────────────────────────────

    def _send_draft(self, cid: str, text: str, attachments: Any, draft_id: str) -> Tuple[int, Dict[str, Any]]:
        """重发已召回草稿；身份由队列项决定。"""
        try:
            item = self.app.conversation_queue.resubmit_draft(
                cid, draft_id, content=text, attachments=attachments,
            )
        except QueueError as exc:
            return 409, {"ok": False, "error": str(exc)}
        if self.app.mesh.is_running(cid):
            return 200, {
                "ok": True, "conversation_id": cid, "run_id": "",
                "queued": True, "queue_item": item,
                "revision": self.app.conversation_queue.revision(cid),
            }
        claimed = self.app.conversation_queue.claim_item(cid, item["id"])
        if claimed is None:
            return 409, {"ok": False, "error": "消息已不在队列"}
        sender = claimed.get("sender") if isinstance(claimed.get("sender"), dict) else None
        start_payload: Dict[str, Any] = {
            "content": str(claimed.get("content") or ""),
            "attachments": claimed.get("attachments") or None,
        }
        if sender:
            start_payload["_sender"] = sender.get("cid")
            start_payload["_sender_name"] = sender.get("name")
        started = self.app.runner.start(cid, start_payload)
        if not started:
            self.app.conversation_queue.release(cid, item["id"])
            return 503, {"ok": False, "error": "会话启动失败"}
        self.app.conversation_queue.complete(cid, item["id"])
        return 200, {"ok": True, "conversation_id": cid,
                     "run_id": started, "queued": False}

    def send(
        self,
        cid: str,
        text: str,
        mode: str = "",
        images: Any = None,
        model: str = "",
        draft_id: str = "",
    ) -> Tuple[int, Dict[str, Any]]:
        """提交输入：空闲直接启动，忙时进入待发送队列。

        `images`：可选截图附件，形如 `[{mime, data_base64}]`；数量口径由
        `normalize_images` 统一控制；
        有图无字也算有效输入（纯截图提问是常见用法）。

        `model`：会话级模型选择（空串 = 不改动既有选择）。落 `live_state` 持久化 ——
        刷新页面乃至换进程，同一会话选的都是同一个模型。校验放在解析器落位之后，
        未配置的名字一律拒绝（400），避免"选择了却悄悄用默认模型"。
        """
        text = str(text or "").strip()
        attachments = normalize_images(images)
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
            before = str(self.app.live_state.get_model(cid) or "")
            self.app.live_state.set_model(cid, want_model)
            if before != want_model:
                self._announce_model(cid, want_model)
        if draft_id:
            return self._send_draft(cid, text, attachments, draft_id)
        payload: Dict[str, Any] = {"content": text}
        if attachments:
            payload["attachments"] = attachments
        try:
            result = self.app.mesh.submit(cid, payload)
        except QueueError as exc:
            return 503, {"ok": False, "error": str(exc)}
        if result.get("queued"):
            return 200, {
                "ok": True,
                "conversation_id": cid,
                "run_id": "",
                "queued": True,
                "queue_item": result.get("queue_item"),
                "revision": self.app.conversation_queue.revision(cid),
            }
        started = str(result.get("run_id") or "")
        if not started:
            return 503, {"error": "会话启动失败"}
        return 200, {
            "ok": True,
            "conversation_id": cid,
            "run_id": started,
            "queued": False,
        }

    # ── 会话待发送队列 ────────────────────────────────

    def queue(self, cid: str) -> Tuple[int, Dict[str, Any]]:
        cid = str(cid or "").strip()
        if not cid or not is_valid_conversation_id(cid):
            return 400, {"ok": False, "error": "invalid conversation_id"}
        return 200, self.app.conversation_queue.list(cid)

    def queue_insert(self, cid: str, item_id: str) -> Tuple[int, Dict[str, Any]]:
        cid = str(cid or "").strip()
        if not cid or not is_valid_conversation_id(cid):
            return 400, {"ok": False, "error": "invalid conversation_id"}
        try:
            item = self.app.conversation_queue.set_insert(cid, item_id)
            if not self.app.mesh.is_running(cid):
                claimed = self.app.conversation_queue.claim_item(cid, item_id)
                if claimed is not None:
                    sender = claimed.get("sender") if isinstance(claimed.get("sender"), dict) else None
                    payload: Dict[str, Any] = {
                        "content": str(claimed.get("content") or ""),
                        "attachments": claimed.get("attachments") or None,
                    }
                    if sender:
                        payload["_sender"] = sender.get("cid")
                        payload["_sender_name"] = sender.get("name")
                    started = self.app.runner.start(cid, payload)
                    if not started:
                        self.app.conversation_queue.release(cid, item_id)
                        return 503, {"ok": False, "error": "会话启动失败"}
                    self.app.conversation_queue.complete(cid, item_id)
                    return 200, {"ok": True, "run_id": started,
                                 "revision": self.app.conversation_queue.revision(cid)}
        except QueueError as exc:
            return 409, {"ok": False, "error": str(exc)}
        return 200, {"ok": True, "item": item,
                     "revision": self.app.conversation_queue.revision(cid)}

    def queue_recall(self, cid: str, item_id: str) -> Tuple[int, Dict[str, Any]]:
        cid = str(cid or "").strip()
        if not cid or not is_valid_conversation_id(cid):
            return 400, {"ok": False, "error": "invalid conversation_id"}
        try:
            item = self.app.conversation_queue.recall(cid, item_id)
        except QueueError as exc:
            return 409, {"ok": False, "error": str(exc)}
        return 200, {"ok": True, "draft_queue_id": item["id"], "item": item,
                     "revision": self.app.conversation_queue.revision(cid)}

    def queue_cancel(self, cid: str, item_id: str) -> Tuple[int, Dict[str, Any]]:
        cid = str(cid or "").strip()
        if not cid or not is_valid_conversation_id(cid):
            return 400, {"ok": False, "error": "invalid conversation_id"}
        try:
            self.app.conversation_queue.cancel(cid, item_id)
        except QueueError as exc:
            return 409, {"ok": False, "error": str(exc)}
        return 200, {"ok": True, "revision": self.app.conversation_queue.revision(cid)}

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
                            "date_group": date_group(mtime),
                        }
                    )
        return 200, {"sessions": [r["conversation_id"] for r in rows], "items": rows}

    def release_conversation(self, conversation_id: str) -> Tuple[int, Dict[str, Any]]:
        """关闭/删除标签时释放进程内会话运行态（不动已落盘的 `.raw`）。"""
        cid = str(conversation_id or "").strip()
        if not cid:
            return 400, {"ok": False, "error": "conversation_id 为空"}
        ctx = getattr(self.app, "context", None)
        classic = (
            ctx.get(SERVICE_CLASSIC_ADAPTER)
            if ctx is not None and ctx.has(SERVICE_CLASSIC_ADAPTER)
            else None
        )
        if classic is not None and callable(getattr(classic, "drop_session", None)):
            classic.drop_session(cid)
        else:
            contexts = getattr(self.app, "session_contexts", None)
            if contexts is not None:
                contexts.release(cid)
        return 200, {"ok": True, "conversation_id": cid, "released": True}

    def _derive_title(self, cid: str) -> str:
        """会话标题：优先已生成并落盘的标题，其次从事实源派生（首条用户输入）。

        会话日志可达数万条事件，标题只需要开头——故只读文件前若干行
        （`_TITLE_SCAN_LINES`），不整档 load；超限则退化为空（由前端显示短 id）。
        """
        stored = self.titles.load(cid) if self.titles is not None else ""
        if stored and not is_placeholder_title(stored):
            return stored
        store = self.app.store
        if store is None or not hasattr(store, "raw_path"):
            return ""
        path = store.raw_path(cid)
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
                    # 落盘行的键名取自 store 的 `KEY_TYPE` / `KEY_DATA`：
                    # 硬编码字符串会随键名改动静默失配，标题悄悄退化成空。
                    if payload.get(KEY_TYPE) != "input_claimed":
                        continue
                    body = payload.get(KEY_DATA)
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
        events = store.load(cid)
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

    def loaded_plugin_names(self) -> List[str]:
        """当前已装载的插件名。页面用它决定上下文条里哪些插件段还在。"""
        host = getattr(self.app, "plugin_host", None)
        names = getattr(host, "loaded_names", None)
        if not callable(names):
            return []
        return [str(name) for name in names()]

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

    def ctx_segment_style_list(self) -> List[Dict[str, Any]]:
        """插件贡献的上下文段外观（段名 / 色名）；界面开屏按它注册，不必靠空面板脚本。"""
        host = getattr(self.app, "plugin_host", None)
        contribs = getattr(host, "contributions", None) if host is not None else None
        if contribs is None:
            return []
        listing = getattr(contribs, "all_ctx_segment_styles", None)
        if not callable(listing):
            return []
        return [s.as_dict() for s in listing()]

    def boot_script_list(self) -> List[Dict[str, Any]]:
        """插件贡献的开屏脚本；界面在面板脚本之后预载，无面板也能注入。"""
        host = getattr(self.app, "plugin_host", None)
        contribs = getattr(host, "contributions", None) if host is not None else None
        if contribs is None:
            return []
        listing = getattr(contribs, "all_boot_scripts", None)
        if not callable(listing):
            return []
        return [s.as_dict() for s in listing()]

    def tool_list(self) -> List[Dict[str, Any]]:
        """工具展示清单：`[{name, label, icon}]`（来自工具自己的声明）。

        界面据此认识所有工具（含插件工具），不必在前端维护工具名表 ——
        加一个插件工具不需要改界面。
        """
        registry = getattr(self.app, "registry", None)
        if registry is None or not hasattr(registry, "display_list"):
            return []
        return registry.display_list()

    # ── 右栏文件查看器（文本 / 代码 / 表格）──

    def fs_list(self, path: str) -> Tuple[int, Dict[str, Any]]:
        """列目录（供右栏文件树 / @ 补全）；限定在可见根内。

        `rel` 是相对命中的那个根的路径；命不中根时退回文件名。
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
          - 访问不到就回落（不报错），免得上层补全卡死。
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

        相对路径依次在每个根下试（命中即用）；绝对路径只有落在某个根内才接受——
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
        model_for = getattr(self.app, "model_for", None)
        current = (
            model_for(cid) if callable(model_for)
            else str(live.get_model(cid) or "")
        )
        return 200, {
            "conversation_id": cid,
            "mode": live.get_mode(cid),
            "todo": live.get_todo(cid),
            "autonomy": live.get_autonomy(cid),
            # 目标（Goal）：前端"目标"按钮据此回填状态；无目标时为 None。
            "goal": live.get_goal(cid),
            # 模型选择与可选清单：前端据此回填下拉（刷新后不丢）。
            # 只给 id —— 凭据（key / url）始终留在服务端。
            "model": current,
            "available_models": self.available_models(),
            # 会话级设置同源回填：模式 / 推理档位都属于会话，不属于某个标签页。
            "reasoning_effort": live.get_reasoning_effort(cid),
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
            before = str(self.app.live_state.get_model(cid) or "")
            self.app.live_state.set_model(cid, want)
            if want and before != want:
                self._announce_model(cid, want)
        return self.ui_state(cid)

    def confirm(self, cid: str, confirm_id: str) -> Tuple[int, Dict[str, Any]]:
        """确认一个写盘预览：按 cid 解析会话门控，不落默认桶。"""
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
        source = str(getattr(self.app, "model_config_state", "") or "")
        allowed = self.available_models()
        if source != "none":
            if not allowed:
                allowed = list(getattr(provider, "allowed_models", ()) or ())
                if not allowed:
                    allowed = [model] if model else []
            # 无白名单清单时把当前模型作为唯一候选下发（前端据此渲染模型菜单）；
            # 真正的多模型名单由装配面的配置提供。
            if not allowed and model:
                allowed = [model]
        elif not allowed:
            # 降级态保持空清单：不能报出一个实际选不了的 id（顶栏也不会假装有模型）。
            model = ""
        settings = getattr(self.app, "model_config", None)
        model_config = settings() if callable(settings) else {}
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
            # 全局默认档位：会话还没回填前，顶栏先按它显示（会话值以 ui-state 为准）。
            "reasoning_effort": (self.app.live_state.default_effort
                                 if self.app.live_state is not None else "high"),
            "max_images": MAX_IMAGES,
            "model_config": model_config,
        }

    # ── 媒体（本地绝对路径 → 浏览器可访问）──

    def media(self, path: str, root: Optional[Path]) -> Tuple[int, Any, str]:
        """解析本地媒体文件供浏览器预览；限定在 root 之内（防越权读取）。

        返回 (status, body_bytes | error_payload, content_type)。

        `root` 为 None 时改用全部可见根：经典界面的 Markdown 会把正文里
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
