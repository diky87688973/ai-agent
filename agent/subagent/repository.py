# -*- coding: utf-8 -*-
"""子 Agent 持久化仓库：会话路径、批次记录、fork 初始化。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from agent.core.error_report import report_error
from agent.mechanisms.session_store import SessionStore, new_conversation_id
from agent.subagent.batches import MAX_CHILDREN, BatchError, BatchStore
from agent.subagent.models import BatchRecord, SubagentError, SubagentRecord
from agent.subagent.seed import seed_child

MAX_LABEL = 120


class SubagentRepository:
    """只负责子 Agent 数据的持久化归属，不负责消息和运行态。"""

    def __init__(self, *, data_root: Path, parent_store: SessionStore) -> None:
        self.data_root = Path(data_root)
        self.parent_store = parent_store
        self.batches = BatchStore(self.data_root)
        self.child_sessions = self.data_root / "subagent" / "sessions"
        key_path = getattr(getattr(parent_store, "_cipher", None), "key_path", None)
        self.child_store = SessionStore(
            self.data_root,
            sessions_dir=self.child_sessions,
            key_path=key_path,
            sequence_source=parent_store,
        )
        if hasattr(parent_store, "add_scan_dir"):
            parent_store.add_scan_dir(self.child_sessions)
        self._children: Dict[str, SubagentRecord] = {}
        self._restore()

    def _restore(self) -> None:
        for batch in self.batches.iter_batches():
            for child in batch.children:
                self._children[child.child_id] = child

    def is_child(self, child_id: str) -> bool:
        return str(child_id or "").strip() in self._children

    def store_for(self, cid: str) -> SessionStore:
        return self.child_store if self.is_child(cid) else self.parent_store

    def record(self, child_id: str) -> SubagentRecord:
        child = self._children.get(str(child_id or "").strip())
        if child is None:
            raise SubagentError("子 Agent 不存在", "child_not_found")
        return child

    def prepare(
        self,
        *,
        parent_cid: str,
        batch: str,
        label: str,
        context: str,
    ) -> SubagentRecord:
        """分配 child id、播种会话并写入批次记录。"""
        record = self._batch_for(parent_cid, batch)
        if len(record.children) >= MAX_CHILDREN:
            raise SubagentError("批次已满（最多 10 个子 Agent）", "batch_full")
        child_id = new_conversation_id()
        try:
            seed_child(
                self.parent_store,
                self.child_store,
                child_id=child_id,
                parent_cid=parent_cid,
                batch=record.batch,
                label=label,
                context=context,
            )
            record = self.batches.add_child(
                parent_cid,
                record.batch,
                child_id=child_id,
                label=label,
                context=context,
            )
        except Exception:
            self.discard(child_id)
            raise
        child = next(item for item in record.children if item.child_id == child_id)
        self._children[child_id] = child
        return child

    def _batch_for(self, parent: str, batch: str) -> BatchRecord:
        batch_id = str(batch or "").strip()
        if not batch_id:
            return self.batches.create(parent)
        try:
            return self.batches.get(parent, batch_id)
        except BatchError as exc:
            raise SubagentError(str(exc), exc.code) from exc

    def discard(self, child_id: str) -> None:
        try:
            path = self.child_store.raw_path(child_id)
            if path.is_file():
                path.unlink()
        except (OSError, ValueError) as exc:
            report_error("agent.subagent.repository.discard", exc, child_id=child_id)

    def list_batches(self, parent_cid: str, batch: str = "") -> List[BatchRecord]:
        rows = self.batches.list_for_parent(parent_cid)
        if batch:
            rows = [row for row in rows if row.batch == batch]
            if not rows:
                raise SubagentError("批次不存在", "batch_not_found")
        return rows

    def latest_result(self, parent_cid: str, child_id: str) -> Dict[str, Any]:
        child = self.record(child_id)
        if child.parent_cid != str(parent_cid or "").strip():
            raise SubagentError("不是该父会话的子 Agent", "parent_mismatch")
        result = ""
        for event in reversed(self.child_store.load(child.child_id)):
            if str(event.type) == "model_message":
                result = str((event.data or {}).get("content") or "").strip()
                if result:
                    break
        return {
            "child_id": child.child_id,
            "batch": child.batch,
            "label": child.label,
            "result": result,
        }

    def history(self, parent_cid: str, child_id: str) -> Dict[str, Any]:
        child = self.record(child_id)
        if child.parent_cid != str(parent_cid or "").strip():
            raise SubagentError("不是该父会话的子 Agent", "parent_mismatch")
        return {
            "conversation_id": child.child_id,
            "parent_cid": child.parent_cid,
            "batch": child.batch,
            "label": child.label,
            "events": [
                {"type": event.type, **dict(event.data or {})}
                for event in self.child_store.load(child.child_id)
            ],
        }

    def shutdown(self) -> None:
        try:
            self.child_store.flush_all()
        except Exception as exc:
            report_error("agent.subagent.repository.shutdown", exc)
