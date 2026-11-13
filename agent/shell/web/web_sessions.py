# -*- coding: utf-8 -*-
"""会话历史、名录、标题与运行态释放。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from agent.core.error_report import report_error
from agent.mechanisms.session_store import is_valid_conversation_id
from agent.mechanisms.session_title import (
    UNKNOWN_TITLE,
    fallback_title,
    is_placeholder_title,
)
from agent.shell.timefmt import date_group


class SessionActions:
    """会话历史投影、名录与标题派生；关闭标签时释放进程内运行态。"""

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
                for _, e in store.history_window(cid)[0]
            ],
        }

    def sessions(self) -> Tuple[int, Dict[str, Any]]:
        """会话名录（含派生标题）。

        标题 = 已生成并落盘的标题文件；没有则返回“未知标题”，不回读会话日志。
        """
        store = self.app.store
        rows: List[Dict[str, Any]] = []
        root = getattr(store, "data_root", None)
        directory = getattr(store, "sessions_dir", None)
        if directory is None and root is not None:
            directory = Path(root) / "session" / "raw"
        if store is not None and directory is not None:
            directory = Path(directory)
            if directory.is_dir():
                entries = []
                for path in directory.glob("*.raw"):
                    cid = path.stem
                    if not is_valid_conversation_id(cid):
                        continue
                    try:
                        mtime = path.stat().st_mtime
                    except OSError as exc:
                        report_error("agent.shell.web.web_sessions.sessions", exc)
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
        """关闭标签时释放进程内会话运行态，保留历史和终止标记。"""
        cid = str(conversation_id or "").strip()
        if not cid:
            return 400, {"ok": False, "error": "conversation_id 为空"}
        classic = self._classic_adapter()
        if classic is not None and callable(getattr(classic, "drop_session", None)):
            classic.drop_session(cid)
        else:
            contexts = getattr(self.app, "session_contexts", None)
            if contexts is not None:
                contexts.release(cid)
        return 200, {"ok": True, "conversation_id": cid, "released": True}

    def _derive_title(self, cid: str) -> str:
        """读取已落盘标题；已尝试生成但未保存时从首条用户消息恢复。"""
        stored = self.titles.load(cid) if self.titles is not None else ""
        if stored and not is_placeholder_title(stored):
            return stored
        if self.titles is not None and self.titles.generation_attempted(cid):
            fallback = fallback_title(self._conversation_messages(cid))
            if fallback:
                self.titles.save(cid, fallback, replace=False)
                recovered = self.titles.load(cid)
                return recovered if not is_placeholder_title(recovered) else fallback
        return UNKNOWN_TITLE

    def title(self, cid: str) -> Tuple[int, Dict[str, Any]]:
        """生成 / 读取会话标题。

        已生成过则直接返回；否则调用模型一次（无工具）→ 清洗 → 落盘；
        生成失败或输出占位词时，用首条用户消息截断后落盘；仍为空才返回“未知标题”。
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
        fallback = fallback_title(messages)
        generated = ""
        if fallback and self.title_generator is not None:
            if self.titles is None or not self.titles.claim_generation(cid):
                if self.titles is not None:
                    if self.titles.save(cid, fallback, replace=False) and self.session_catalog is not None:
                        self.session_catalog.touch(cid)
                    existing = self.titles.load(cid)
                cached = bool(existing and not is_placeholder_title(existing))
                return 200, {"ok": True, "conversation_id": cid,
                             "title": existing if cached else fallback, "cached": cached}
            try:
                generated = self.title_generator(messages)
            except Exception as exc:  # 旁路增强：不因标题失败而报错
                report_error("agent.shell.web.web_sessions.title", exc)
        if generated and not is_placeholder_title(generated):
            title = generated
        else:
            title = fallback
        if title and not is_placeholder_title(title):
            if (self.titles is not None and self.titles.save(cid, title)
                    and self.session_catalog is not None):
                self.session_catalog.touch(cid)
        else:
            title = UNKNOWN_TITLE
        return 200, {"ok": True, "conversation_id": cid, "title": title, "cached": False}

    def _conversation_messages(self, cid: str) -> List[Dict[str, Any]]:
        """事实源 → 模型消息序列（标题生成素材）。"""
        store = self.app.store
        if store is None:
            return []
        events = store.title_facts(cid)
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
