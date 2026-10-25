# -*- coding: utf-8 -*-
"""会话历史、名录、标题与运行态释放。"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from agent.core.error_report import report_error
from agent.mechanisms.session_store import KEY_DATA, KEY_TYPE, is_valid_conversation_id
from agent.mechanisms.session_title import fallback_title, is_placeholder_title
from agent.shell.timefmt import date_group
from agent.shell.web.web_static import TITLE_SCAN_LINES


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
        classic = self._classic_adapter()
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
        （`TITLE_SCAN_LINES`），不整档 load；超限则退化为空（由前端显示短 id）。
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
                    if index >= TITLE_SCAN_LINES:
                        break
                    try:
                        payload = json.loads(line)
                    except (TypeError, ValueError) as exc:
                        report_error("agent.shell.web.web_sessions.SessionActions._derive_title", exc)
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
