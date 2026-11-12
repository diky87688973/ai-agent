# -*- coding: utf-8 -*-
"""会话协作网格：Agent 注册表、运行占位与原子投递。"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agent.common.status import AGENT_IDLE, AGENT_STATUSES, require
from agent.core.error_report import report_error
from agent.mechanisms.conversation_queue import ConversationQueue
from agent.mechanisms.run_registry import RunRegistry, build_run_registry


class MeshState:
    """会话协作网格：注册表 / 运行占位 / 待发送队列（装配时单例注入）。"""

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        *,
        run_registry: Optional[RunRegistry] = None,
        input_queue: Optional[ConversationQueue] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._stopped: set[str] = set()
        # Per-session user input that triggers the next Inbox dispatch.
        self._pending_user_dispatch: Dict[str, str] = {}
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._queue = input_queue if input_queue is not None else ConversationQueue()
        self._runs: RunRegistry = run_registry if run_registry is not None else build_run_registry(
            (Path(storage_dir) / "runs") if storage_dir else None
        )
        self._activator: Optional[Callable[[str, Dict[str, Any]], str]] = None
        self._session_exists: Optional[Callable[[str], bool]] = None
        self._storage_dir = Path(storage_dir) if storage_dir else None
        if self._storage_dir is not None:
            self._load()

    # ── 装配 ─────────────────────────────

    def set_activator(self, activator: Optional[Callable[[str, Dict[str, Any]], str]]) -> None:
        with self._lock:
            self._activator = activator

    def set_session_exists(self, fn: Optional[Callable[[str], bool]]) -> None:
        with self._lock:
            self._session_exists = fn

    def session_exists(self, cid: str) -> bool:
        key = str(cid or "").strip()
        if not key:
            return False
        with self._lock:
            if key in self._agents:
                return True
            fn = self._session_exists
        if fn is None:
            return False
        return bool(fn(key))

    # ── 注册表 ───────────────────────────

    def upsert_agent(self, cid: str, **fields: Any) -> Dict[str, Any]:
        key = str(cid or "").strip()
        if not key:
            return {}
        now = int(time.time())
        if fields.get("status") is not None:
            fields["status"] = require(fields["status"], AGENT_STATUSES, "Agent 状态")
        with self._lock:
            item = dict(self._agents.get(key) or {})
            item.setdefault("cid", key)
            item.setdefault("status", AGENT_IDLE)
            item.setdefault("created_at", now)
            item["updated_at"] = now
            for name, value in fields.items():
                if value is not None:
                    item[name] = value
            self._agents[key] = item
            self._save_agents_locked()
            return dict(item)

    def get_agent(self, cid: str) -> Dict[str, Any]:
        with self._lock:
            return dict(self._agents.get(str(cid or "").strip()) or {})

    def list_agents(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {key: dict(value) for key, value in self._agents.items()}

    def remove_agent(self, cid: str) -> bool:
        """摘掉运行身份（子智能体创建失败回滚用）；不存在返回 False。"""
        key = str(cid or "").strip()
        if not key:
            return False
        with self._lock:
            if key not in self._agents:
                return False
            marker = self._stop_marker(key)
            if marker is not None:
                marker.unlink(missing_ok=True)
            self._stopped.discard(key)
            self._pending_user_dispatch.pop(key, None)
            self._agents.pop(key, None)
            self._save_agents_locked()
            return True

    # ── 待发送队列 ───────────────────────

    @property
    def queue(self) -> ConversationQueue:
        return self._queue

    def queue_size(self, cid: str) -> int:
        return self._queue.size(str(cid or "").strip())

    # ── 活跃集与投递 ─────────────────────

    def is_running(self, cid: str) -> bool:
        return self._runs.running(str(cid or "").strip())

    def running_cids(self) -> List[str]:
        return self._runs.running_cids()

    def active_run_id(self, cid: str) -> str:
        return self._runs.active_run_id(str(cid or "").strip())

    def run_started_at(self, cid: str) -> Optional[float]:
        """当前连续忙碌段的开始时间；未在跑返回 None。"""
        return self._runs.run_started_at(str(cid or "").strip())

    def touch_run(self, cid: str) -> None:
        self._runs.touch(str(cid or "").strip())

    def _stop_marker(self, cid: str) -> Optional[Path]:
        if self._storage_dir is None:
            return None
        key = hashlib.sha256(cid.encode("utf-8")).hexdigest()
        return self._storage_dir / "stopped" / key

    def is_stopped(self, cid: str) -> bool:
        with self._lock:
            marker = self._stop_marker(cid)
            return cid in self._stopped or (marker is not None and marker.is_file())

    def mark_stopped(self, cid: str, *, cancel: Optional[threading.Event] = None) -> None:
        with self._lock:
            if cancel is not None:
                cancel.set()
            self._stopped.add(cid)
            self._pending_user_dispatch.pop(cid, None)
            marker = self._stop_marker(cid)
            if marker is not None:
                try:
                    marker.parent.mkdir(parents=True, exist_ok=True)
                    marker.touch()
                    self._stopped.discard(cid)
                except OSError as exc:
                    report_error("agent.mechanisms.mesh.mark_stopped", exc, conversation_id=cid)

    def try_begin_run(self, cid: str, *, user_send: bool = False) -> str:
        key = str(cid or "").strip()
        if not key:
            return ""
        with self._lock:
            stopped = self.is_stopped(key)
            if stopped and not user_send:
                return ""
            rid = uuid.uuid4().hex[:12]
            if not self._runs.claim(key, rid):
                return ""
            marker = self._stop_marker(key) if stopped else None
            if marker is not None:
                try:
                    marker.unlink(missing_ok=True)
                except OSError as exc:
                    self._runs.release(key)
                    report_error("agent.mechanisms.mesh.try_begin_run", exc, conversation_id=key)
                    return ""
            self._stopped.discard(key)
            return rid

    def renew_run(self, cid: str, *, reset_started: bool = True) -> bool:
        key = str(cid or "").strip()
        if not key:
            return False
        with self._lock:
            return not self.is_stopped(key) and bool(self._runs.renew(
                key, uuid.uuid4().hex[:12], reset_started=reset_started))

    def renew_for_insert(self, cid: str) -> Optional[bool]:
        """检查并续用运行位；None=没有插入，True=已续用，False=运行位已丢。"""
        key = str(cid or "").strip()
        if not key:
            return False
        with self._lock:
            if self.is_stopped(key) or not self._queue.has_inserting(key):
                return None
            return bool(self._runs.renew(
                key, uuid.uuid4().hex[:12], reset_started=False))

    def finish_or_continue_insert(self, cid: str) -> bool:
        """原子收尾：有插入则续用运行位，否则释放；True 表示继续。"""
        key = str(cid or "").strip()
        if not key:
            return False
        with self._lock:
            if not self.is_stopped(key) and self._queue.has_inserting(key):
                return bool(self._runs.renew(
                    key, uuid.uuid4().hex[:12], reset_started=False))
            self._runs.release(key)
            return False

    def end_run(self, cid: str) -> None:
        with self._lock:
            self._runs.release(str(cid or "").strip())

    def abort_run(self, cid: str) -> None:
        with self._lock:
            self._runs.release(str(cid or "").strip())

    def _enqueue_message(self, key: str, message: Dict[str, Any], *,
                         origin: Optional[str] = None,
                         dedupe_key: str = "",
                         delivery: str = "after_turn",
                         insert: bool = False) -> Dict[str, Any]:
        payload = dict(message)
        nested_meta = payload.pop("meta", None)
        if isinstance(nested_meta, dict):
            for name, value in nested_meta.items():
                payload.setdefault(name, value)
            # 旧调用方仍读取 payload.meta；展开后的顶层字段供输入与渲染使用。
            payload["meta"] = dict(nested_meta)
        resolved_origin = str(origin or "").strip().lower()
        sender = None
        if resolved_origin not in ("user", "agent", "system"):
            resolved_origin = "user"
        if resolved_origin == "user" and str(payload.get("_sender") or "").strip():
            resolved_origin = "agent"
        if resolved_origin == "agent":
            sender = {
                "cid": str(payload.get("_sender") or "").strip(),
                "name": str(payload.get("_sender_name") or "").strip(),
                "thread_id": str(payload.get("_thread_id")
                                   or payload.get("thread_id") or "").strip(),
                "requires_reply": bool(payload.get("_requires_reply")
                                       if "_requires_reply" in payload
                                       else payload.get("requires_reply")),
            }
        elif resolved_origin == "user" and isinstance(payload.get("resume"), dict):
            resolved_origin = "system"
        queue_payload = dict(payload)
        queue_payload.pop("attachments", None)
        return self._queue.enqueue(
            key,
            content=str(payload.get("content") or ""),
            attachments=payload.get("attachments"),
            origin=resolved_origin,
            sender=sender,
            delivery=delivery,
            payload=queue_payload,
            dedupe_key=dedupe_key,
            insert=insert,
        )

    def submit_insert(self, cid: str, message: Dict[str, Any], *,
                      origin: Optional[str] = None,
                      dedupe_key: str = "") -> Dict[str, Any]:
        """原子插入投递：忙时等待安全点，空闲时启动，已终止时只入队。"""
        key = str(cid or "").strip()
        if not key:
            return {"queued": False, "inserted": False, "run_id": ""}
        with self._lock:
            item = self._enqueue_message(
                key, message, origin=origin, dedupe_key=dedupe_key,
                delivery="next_pass", insert=True)
            state = str(item.get("state") or "")
            rid = ""
            try:
                rid = self.activate_inserts(key)
            except Exception as exc:
                report_error("agent.mechanisms.mesh.MeshState.submit_insert", exc)
            return {
                "queued": True,
                "inserted": state == "inserting",
                "already_claimed": state == "claimed",
                "run_id": rid,
                "queue_item": item,
            }

    def promote_insert(self, cid: str, item_id: str) -> None:
        with self._lock:
            self._queue.set_insert(cid, item_id)
            self.activate_inserts(cid)

    def activate_inserts(self, cid: str) -> str:
        with self._lock:
            if (self._activator is not None and not self.is_stopped(cid)
                    and not self._runs.running(cid) and self._queue.has_inserting(cid)):
                return str(self._activator(cid, {}) or "")
            return ""

    def submit_user(self, cid: str, message: Dict[str, Any], *, draft_id: str = "") -> Dict[str, Any]:
        """Clear stop, enqueue the user's input, then dispatch under the same lock."""
        with self._lock:
            stopped = self.is_stopped(cid)
            marker = self._stop_marker(cid) if stopped else None
            try:
                if marker is not None:
                    marker.unlink(missing_ok=True)
                self._stopped.discard(cid)
            except OSError as exc:
                report_error("agent.mechanisms.mesh.submit_user", exc, conversation_id=cid)

            try:
                if draft_id:
                    item = self._queue.resubmit_draft(
                        cid, draft_id, content=message.get("content", ""),
                        attachments=message.get("attachments"), payload={"_inbox_user_send": True})
                else:
                    item = self._enqueue_message(cid, {**message, "_inbox_user_send": True})
            except Exception:
                if stopped:
                    self.mark_stopped(cid)
                raise
            self._pending_user_dispatch[cid] = item["id"]
            rid = ""
            if self._activator is not None:
                rid = self.activate_queued(
                    cid, lambda claimed: self._activator(cid, {"_queued_item": claimed}))
            return {"queued": not bool(rid), "run_id": rid, "queue_item": item}

    def activate_queued(self, cid: str, activate: Callable[[Dict[str, Any]], str], *,
                        user_only: bool = False) -> str:
        """Hand off queued input only while this session is idle."""
        with self._lock:
            if self._runs.running(cid):
                return ""
            user_item_id = self._pending_user_dispatch.get(cid)
            if self.is_stopped(cid) or (user_only and not user_item_id):
                return ""
            if not user_item_id and self._queue.has_inserting(cid):
                self.activate_inserts(cid)
                return ""
            item = (self._queue.claim_item(cid, user_item_id) if user_item_id
                    else self._queue.claim_after_turn(cid))
            if item is None and user_item_id:
                self._pending_user_dispatch.pop(cid, None)
                user_item_id = None
                if not user_only:
                    item = self._queue.claim_after_turn(cid)
            if item is None:
                return ""
            started = ""
            try:
                if user_item_id:
                    item["_resume_inbox"] = True
                started = activate(item)
                if started and user_item_id:
                    self._pending_user_dispatch.pop(cid, None)
            except Exception as exc:
                report_error("agent.mechanisms.mesh.activate_queued", exc, conversation_id=cid)
            finally:
                if not started:
                    self._queue.release(cid, item["id"])
            return started

    def submit(self, cid: str, message: Dict[str, Any], *,
               origin: Optional[str] = None,
               dedupe_key: str = "", user_send: bool = False) -> Dict[str, Any]:
        """原子投递：忙 / 无激活器 → 入队；闲 → 激活启动。"""
        key = str(cid or "").strip()
        if not key:
            return {"queued": False, "queued_count": 0, "run_id": ""}
        with self._lock:
            if user_send:
                return self.submit_user(key, message)
            if message.get("_confirmation_resume"):
                item = self._enqueue_message(key, message, origin=origin, dedupe_key=dedupe_key)
                rid = ""
                if self._activator is not None:
                    rid = self.activate_queued(
                        key, lambda claimed: self._activator(key, {"_queued_item": claimed}))
                return {"queued": not bool(rid), "run_id": rid, "queue_item": item}
            if self._runs.running(key) or self._activator is None or self.is_stopped(key):
                item = self._enqueue_message(
                    key, message, origin=origin, dedupe_key=dedupe_key)
                return {"queued": True, "queued_count": self._queue.size(key),
                        "run_id": "", "queue_item": item}
            if self._queue.has_inserting(key):
                item = self._enqueue_message(key, message, origin=origin, dedupe_key=dedupe_key)
                self.activate_inserts(key)
                return {"queued": True, "queued_count": self._queue.size(key),
                        "run_id": "", "queue_item": item}
            try:
                rid = str(self._activator(key, dict(message)) or "")
            except Exception as exc:
                report_error("agent.mechanisms.mesh.MeshState.submit", exc)
                item = self._enqueue_message(
                    key, message, origin=origin, dedupe_key=dedupe_key)
                return {"queued": True, "queued_count": self._queue.size(key),
                        "run_id": "", "queue_item": item}
            if rid:
                return {"queued": False, "queued_count": 0, "run_id": rid}
            item = self._enqueue_message(
                key, message, origin=origin, dedupe_key=dedupe_key)
            return {"queued": True, "queued_count": self._queue.size(key),
                    "run_id": "", "queue_item": item}

    # ── 持久化 ───────────────────────────

    def _agents_file(self) -> Optional[Path]:
        return (self._storage_dir / "agents.json") if self._storage_dir else None

    def _save_agents_locked(self) -> None:
        path = self._agents_file()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {"agents": {key: dict(value) for key, value in self._agents.items()}}
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        except Exception as exc:
            # 状态写失败只影响下次启动重建，内存中的网格仍可用。
            report_error("agent.mechanisms.mesh.MeshState._save_agents_locked", exc)

    def _load(self) -> None:
        try:
            path = self._agents_file()
            if path is not None and path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                agents = data.get("agents") if isinstance(data, dict) else None
                if isinstance(agents, dict):
                    self._agents.update({
                        str(key): dict(value)
                        for key, value in agents.items() if isinstance(value, dict)
                    })
        except Exception as exc:
            report_error("agent.mechanisms.mesh.MeshState._load", exc)
