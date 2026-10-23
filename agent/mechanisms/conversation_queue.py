# -*- coding: utf-8 -*-
"""会话待发送消息队列：用户输入与 Agent 投递的统一暂存区。"""
from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agent.core.error_report import report_error
from agent.core.image_embed import describe_image
from agent.core.input_attachments import (
    decode_attachment,
    encode_attachment,
    normalize_images,
)

_CID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_ACTIVE = ("queued", "inserting")
_VISIBLE = ("queued", "inserting")
_ORIGINS = ("user", "agent", "system")
_DELIVERIES = ("after_turn", "next_pass")


class QueueError(Exception):
    """队列校验或持久化失败。"""

    def __init__(self, message: str, code: str = "queue_error") -> None:
        super().__init__(message)
        self.code = str(code or "queue_error")


class ConversationQueue:
    """按会话保存待发送消息；所有状态变更持锁并落盘。"""

    def __init__(self, storage_dir: Optional[Path] = None) -> None:
        self._root = Path(storage_dir) if storage_dir else None
        self._lock = threading.RLock()
        self._items: Dict[str, List[Dict[str, Any]]] = {}
        self._revisions: Dict[str, int] = {}
        self._loaded: set = set()
        self._on_change: Optional[Callable[[str, Dict[str, Any]], None]] = None

    def set_change_listener(
        self, fn: Optional[Callable[[str, Dict[str, Any]], None]]
    ) -> None:
        with self._lock:
            self._on_change = fn

    def revision(self, cid: str) -> int:
        key = self._key(cid)
        with self._lock:
            self._ensure_locked(key)
            return int(self._revisions.get(key, 0))

    def size(self, cid: str) -> int:
        with self._lock:
            key = self._key(cid)
            self._ensure_locked(key)
            return sum(1 for item in self._items.get(key, []) if self._visible(item))

    def list(self, cid: str) -> Dict[str, Any]:
        with self._lock:
            key = self._key(cid)
            self._ensure_locked(key)
            items = [
                self._public(item, position=index + 1)
                for index, item in enumerate(self._ordered_locked(key))
                if self._visible(item)
            ]
            return {"conversation_id": key, "revision": int(self._revisions.get(key, 0)),
                    "items": items}

    def enqueue(
        self,
        cid: str,
        *,
        content: str = "",
        attachments: Any = None,
        origin: str = "user",
        sender: Optional[Dict[str, Any]] = None,
        delivery: str = "after_turn",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        key = self._key(cid)
        text = str(content or "").strip()
        origin = str(origin or "user").strip().lower()
        delivery = str(delivery or "after_turn").strip().lower()
        if origin not in _ORIGINS:
            raise QueueError("未知消息来源", "invalid_origin")
        if delivery not in _DELIVERIES:
            raise QueueError("未知投递方式", "invalid_delivery")
        if origin != "system" and not text and not normalize_images(attachments):
            raise QueueError("消息内容为空", "empty_message")
        normalized = normalize_images(attachments)
        raw_attachments = attachments if isinstance(attachments, list) else []
        if raw_attachments and not normalized:
            raise QueueError("附件不合法", "invalid_attachments")
        item_id = uuid.uuid4().hex
        now = int(time.time())
        with self._lock:
            self._ensure_locked(key)
            seq = max((int(item.get("seq") or 0) for item in self._items.get(key, [])),
                      default=0) + 1
            attachments_meta: List[Dict[str, Any]] = []
            blobs: List[tuple] = []
            for index, attachment in enumerate(normalized):
                raw = decode_attachment(attachment)
                mime, width, height = describe_image(
                    raw, str(attachment.get("mime") or "")
                )
                if not mime:
                    raise QueueError("附件不是图片", "invalid_attachments")
                aid = f"a{index}"
                attachments_meta.append({
                    "id": aid,
                    "mime": mime,
                    "size": len(raw),
                    "width": int(width),
                    "height": int(height),
                })
                blobs.append((aid, raw))
            item = {
                "id": item_id,
                "cid": key,
                "origin": origin,
                "content": text,
                "attachments": attachments_meta,
                "sender": dict(sender or {}) if origin == "agent" else None,
                "delivery": delivery,
                "state": "queued",
                "seq": seq,
                "created_at": now,
                "updated_at": now,
                "payload": dict(payload or {}),
            }
            self._write_item(item, blobs)
            self._items.setdefault(key, []).append(item)
            self._bump_locked(key)
            snapshot = self._snapshot_locked(key)
        self._notify(key, snapshot)
        return self._public(item, position=seq)

    def set_insert(self, cid: str, item_id: str) -> Dict[str, Any]:
        key = self._key(cid)
        with self._lock:
            self._ensure_locked(key)
            item = self._find_locked(key, item_id)
            if item is None or not self._visible(item):
                raise QueueError("消息不在队列", "not_found")
            item["state"] = "inserting"
            item["delivery"] = "next_pass"
            item["updated_at"] = int(time.time())
            self._write_item(item)
            self._bump_locked(key)
            snapshot = self._snapshot_locked(key)
            public = self._public(item, position=self._position_locked(key, item_id))
        self._notify(key, snapshot)
        return public

    def recall(self, cid: str, item_id: str) -> Dict[str, Any]:
        key = self._key(cid)
        with self._lock:
            self._ensure_locked(key)
            item = self._find_locked(key, item_id)
            if item is None or not self._visible(item):
                raise QueueError("消息不在队列", "not_found")
            item["state"] = "draft"
            item["updated_at"] = int(time.time())
            self._write_item(item)
            self._bump_locked(key)
            snapshot = self._snapshot_locked(key)
            public = self._public(item, position=0, with_data=True)
        self._notify(key, snapshot)
        return public

    def cancel(self, cid: str, item_id: str) -> bool:
        key = self._key(cid)
        with self._lock:
            self._ensure_locked(key)
            item = self._find_locked(key, item_id)
            if item is None or item.get("state") in ("delivered", "cancelled"):
                raise QueueError("消息不在队列", "not_found")
            if item.get("state") == "claimed":
                raise QueueError("消息已投递", "claimed")
            self._remove_locked(key, item)
            self._bump_locked(key)
            snapshot = self._snapshot_locked(key)
        self._notify(key, snapshot)
        return True

    def claim_item(self, cid: str, item_id: str) -> Optional[Dict[str, Any]]:
        key = self._key(cid)
        with self._lock:
            self._ensure_locked(key)
            item = self._find_locked(key, item_id)
            if item is None or item.get("state") not in _ACTIVE:
                return None
            item["state"] = "claimed"
            item["updated_at"] = int(time.time())
            self._write_item(item)
            self._bump_locked(key)
            snapshot = self._snapshot_locked(key)
            claimed = self._public(item, position=0, with_data=True)
        self._notify(key, snapshot)
        return claimed

    def claim_after_turn(self, cid: str) -> Optional[Dict[str, Any]]:
        return self._claim(cid, None)

    def claim_insert(self, cid: str) -> Optional[Dict[str, Any]]:
        return self._claim(cid, "inserting")

    def _claim(self, cid: str, state: Optional[str]) -> Optional[Dict[str, Any]]:
        try:
            key = self._key(cid)
        except QueueError:
            # 非法 cid 不参与队列，交给上层校验。
            return None
        with self._lock:
            self._ensure_locked(key)
            for item in self._ordered_locked(key):
                if item.get("state") not in _ACTIVE:
                    continue
                if state is not None and item.get("state") != state:
                    continue
                item["state"] = "claimed"
                item["updated_at"] = int(time.time())
                self._write_item(item)
                self._bump_locked(key)
                snapshot = self._snapshot_locked(key)
                claimed = self._public(item, position=0, with_data=True)
                break
            else:
                return None
        self._notify(key, snapshot)
        return claimed

    def release(self, cid: str, item_id: str) -> None:
        key = self._key(cid)
        with self._lock:
            self._ensure_locked(key)
            item = self._find_locked(key, item_id)
            if item is None or item.get("state") != "claimed":
                return
            item["state"] = "queued"
            item["updated_at"] = int(time.time())
            self._write_item(item)
            self._bump_locked(key)
            snapshot = self._snapshot_locked(key)
        self._notify(key, snapshot)

    def complete(self, cid: str, item_id: str) -> None:
        key = self._key(cid)
        with self._lock:
            self._ensure_locked(key)
            item = self._find_locked(key, item_id)
            if item is None:
                return
            self._remove_locked(key, item)
            self._bump_locked(key)
            snapshot = self._snapshot_locked(key)
        self._notify(key, snapshot)

    def resubmit_draft(
        self,
        cid: str,
        draft_id: str,
        *,
        content: str = "",
        attachments: Any = None,
        delivery: str = "after_turn",
    ) -> Dict[str, Any]:
        key = self._key(cid)
        with self._lock:
            self._ensure_locked(key)
            item = self._find_locked(key, draft_id)
            if item is None or item.get("state") != "draft":
                raise QueueError("草稿不存在", "not_found")
            origin = str(item.get("origin") or "user")
            sender = item.get("sender")
        fresh = self.enqueue(
            key,
            content=content,
            attachments=attachments,
            origin=origin,
            sender=sender,
            delivery=delivery,
        )
        with self._lock:
            old = self._find_locked(key, draft_id)
            if old is not None:
                self._remove_locked(key, old)
                self._bump_locked(key)
        return fresh

    # ── 存储 ──────────────────────────────────────────────

    def _key(self, cid: str) -> str:
        key = str(cid or "").strip()
        if not _CID_RE.match(key):
            raise QueueError("会话 ID 非法", "invalid_cid")
        return key

    def _queue_dir(self, cid: str) -> Optional[Path]:
        return self._root / cid if self._root is not None else None

    def _ensure_locked(self, cid: str) -> None:
        if cid in self._loaded:
            return
        self._loaded.add(cid)
        base = self._queue_dir(cid)
        revision = 0
        items: List[Dict[str, Any]] = []
        if base is not None:
            try:
                rev_file = base / "revision"
                if rev_file.is_file():
                    revision = int(rev_file.read_text(encoding="utf-8").strip() or 0)
            except (OSError, ValueError):
                revision = 0
            if base.is_dir():
                for child in base.iterdir():
                    if not child.is_dir() or child.name.startswith("."):
                        continue
                    meta = child / "meta.json"
                    if not meta.is_file():
                        continue
                    try:
                        item = json.loads(meta.read_text(encoding="utf-8"))
                    except (OSError, ValueError) as exc:
                        report_error("agent.mechanisms.conversation_queue.ConversationQueue._ensure_locked", exc)
                        continue
                    if not isinstance(item, dict) or item.get("cid") != cid:
                        continue
                    if item.get("state") == "claimed":
                        item["state"] = "queued"
                    items.append(item)
        items.sort(key=lambda row: int(row.get("seq") or 0))
        self._items[cid] = items
        self._revisions[cid] = max(revision, max(
            (int(row.get("seq") or 0) for row in items), default=0))

    def _ordered_locked(self, cid: str) -> List[Dict[str, Any]]:
        return sorted(self._items.get(cid, []),
                      key=lambda row: int(row.get("seq") or 0))

    def _find_locked(self, cid: str, item_id: str) -> Optional[Dict[str, Any]]:
        wanted = str(item_id or "").strip()
        for item in self._items.get(cid, []):
            if str(item.get("id") or "") == wanted:
                return item
        return None

    def _visible(self, item: Dict[str, Any]) -> bool:
        return item.get("state") in _VISIBLE and item.get("origin") != "system"

    def _position_locked(self, cid: str, item_id: str) -> int:
        position = 0
        for item in self._ordered_locked(cid):
            if not self._visible(item):
                continue
            position += 1
            if str(item.get("id") or "") == str(item_id or ""):
                return position
        return 0

    def _write_item(self, item: Dict[str, Any], blobs: Optional[List[tuple]] = None) -> None:
        base = self._queue_dir(str(item["cid"]))
        if base is None:
            return
        item_dir = base / str(item["id"])
        if blobs is not None:
            temp = base / f".{item['id']}.tmp"
            try:
                if temp.exists():
                    shutil.rmtree(temp)
                temp.mkdir(parents=True)
                for aid, raw in blobs:
                    (temp / aid).write_bytes(raw)
                (temp / "meta.json").write_text(
                    json.dumps(item, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                if item_dir.exists():
                    shutil.rmtree(item_dir)
                temp.replace(item_dir)
                self._write_revision(str(item["cid"]))
                return
            except OSError as exc:
                if temp.exists():
                    shutil.rmtree(temp, ignore_errors=True)
                raise QueueError(f"队列写入失败：{exc}", "persist_failed") from exc
        try:
            item_dir.mkdir(parents=True, exist_ok=True)
            temp = item_dir / ".meta.tmp"
            temp.write_text(
                json.dumps(item, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temp.replace(item_dir / "meta.json")
            self._write_revision(str(item["cid"]))
        except OSError as exc:
            raise QueueError(f"队列写入失败：{exc}", "persist_failed") from exc

    def _write_revision(self, cid: str) -> None:
        base = self._queue_dir(cid)
        if base is None:
            return
        try:
            base.mkdir(parents=True, exist_ok=True)
            (base / "revision").write_text(str(int(self._revisions.get(cid, 0))),
                                            encoding="utf-8")
        except OSError as exc:
            raise QueueError(f"队列写入失败：{exc}", "persist_failed") from exc

    def _remove_locked(self, cid: str, item: Dict[str, Any]) -> None:
        item_id = str(item.get("id") or "")
        self._items[cid] = [row for row in self._items.get(cid, [])
                            if str(row.get("id") or "") != item_id]
        base = self._queue_dir(cid)
        if base is not None:
            try:
                shutil.rmtree(base / item_id, ignore_errors=False)
            except OSError as exc:
                report_error("conversation_queue.remove", exc, conversation_id=cid)

    def _bump_locked(self, cid: str) -> None:
        self._revisions[cid] = int(self._revisions.get(cid, 0)) + 1
        self._write_revision(cid)

    def _snapshot_locked(self, cid: str) -> Dict[str, Any]:
        return {
            "conversation_id": cid,
            "revision": int(self._revisions.get(cid, 0)),
            "items": [
                self._public(item, position=index + 1)
                for index, item in enumerate(self._ordered_locked(cid))
                if self._visible(item)
            ],
        }

    def _public(self, item: Dict[str, Any], *, position: int,
                with_data: bool = False) -> Dict[str, Any]:
        out = {
            "id": str(item.get("id") or ""),
            "position": int(position),
            "origin": str(item.get("origin") or "user"),
            "content": str(item.get("content") or ""),
            "state": str(item.get("state") or "queued"),
            "delivery": str(item.get("delivery") or "after_turn"),
            "sender": dict(item.get("sender") or {}) if item.get("sender") else None,
            "attachments": [dict(row) for row in (item.get("attachments") or [])],
            "created_at": int(item.get("created_at") or 0),
            "updated_at": int(item.get("updated_at") or 0),
        }
        if with_data:
            out["payload"] = dict(item.get("payload") or {})
            out["attachments"] = [
                {**dict(row), "data_base64": self._read_blob(item, str(row.get("id") or ""))}
                for row in (item.get("attachments") or [])
            ]
        return out

    def _read_blob(self, item: Dict[str, Any], attachment_id: str) -> str:
        base = self._queue_dir(str(item.get("cid") or ""))
        if base is None:
            return ""
        path = base / str(item.get("id") or "") / attachment_id
        try:
            return encode_attachment(path.read_bytes())
        except OSError:
            # 附件缺失时仍允许恢复文本，取消整个 recall 会让消息无法编辑。
            return ""

    def _notify(self, cid: str, snapshot: Dict[str, Any]) -> None:
        fn = self._on_change
        if fn is None:
            return
        try:
            fn(cid, snapshot)
        except Exception as exc:
            report_error("conversation_queue.change", exc, conversation_id=cid)
