# -*- coding: utf-8 -*-
"""按父会话、批次分文件的子智能体元数据存储。"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Iterator, List

from agent.core.error_report import report_error
from agent.mechanisms.session_store import is_valid_conversation_id
from agent.subagent.models import BatchRecord, SubagentRecord

_BATCH_RE = re.compile(r"^sb-[A-Za-z0-9_-]{6,64}$")
MAX_CHILDREN = 10


class BatchError(Exception):
    """批次校验或写入失败。"""

    def __init__(self, message: str, code: str = "batch_error") -> None:
        super().__init__(message)
        self.code = str(code or "batch_error")


class BatchStore:
    """批次文件的读写；不存在跨父会话的公共索引。"""

    def __init__(self, data_root: Path) -> None:
        self.data_root = Path(data_root)
        self.root = self.data_root / "batches"
        self._lock = threading.RLock()

    def new_batch_id(self) -> str:
        return "sb-" + uuid.uuid4().hex[:12]

    def _parent_dir(self, parent_cid: str) -> Path:
        cid = str(parent_cid or "").strip()
        if not is_valid_conversation_id(cid):
            raise BatchError("非法父会话 id", "invalid_parent")
        return self.root / cid

    def _path(self, parent_cid: str, batch: str) -> Path:
        bid = str(batch or "").strip()
        if not _BATCH_RE.match(bid):
            raise BatchError("非法批次号", "invalid_batch")
        return self._parent_dir(parent_cid) / f"{bid}.json"

    def create(self, parent_cid: str) -> BatchRecord:
        with self._lock:
            bid = self.new_batch_id()
            record = BatchRecord(batch=bid, parent_cid=str(parent_cid), created_at=int(time.time()))
            self._write(record)
            return record

    def get(self, parent_cid: str, batch: str) -> BatchRecord:
        path = self._path(parent_cid, batch)
        if not path.is_file():
            raise BatchError("批次不存在", "batch_not_found")
        return self._read(path)

    def list_for_parent(self, parent_cid: str) -> List[BatchRecord]:
        directory = self._parent_dir(parent_cid)
        if not directory.is_dir():
            return []
        rows: List[BatchRecord] = []
        for path in directory.glob("*.json"):
            try:
                rows.append(self._read(path))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                report_error("agent.subagent.batches.BatchStore.list_for_parent", exc,
                             path=str(path))
        rows.sort(key=lambda item: item.created_at, reverse=True)
        return rows

    def add_child(
        self,
        parent_cid: str,
        batch: str,
        *,
        child_id: str,
        label: str,
        context: str,
    ) -> BatchRecord:
        with self._lock:
            record = self.get(parent_cid, batch)
            if len(record.children) >= MAX_CHILDREN:
                raise BatchError("批次已满（最多 10 个子智能体）", "batch_full")
            child = SubagentRecord(
                child_id=str(child_id),
                parent_cid=str(parent_cid),
                batch=record.batch,
                label=str(label),
                context=str(context),
                created_at=int(time.time()),
            )
            record.children.append(child)
            self._write(record)
            return record

    def remove_empty(self, parent_cid: str, batch: str) -> bool:
        """删除无子智能体的批次文件；有子智能体时保持不动。"""
        path = self._path(parent_cid, batch)
        with self._lock:
            if not path.is_file():
                return False
            record = self._read(path)
            if record.children:
                return False
            path.unlink()
            try:
                path.parent.rmdir()
            except OSError as exc:
                report_error("agent.subagent.batches.BatchStore.remove_empty", exc,
                             path=str(path.parent))
            return True

    def _read(self, path: Path) -> BatchRecord:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("批次文件不是对象")
        batch = str(raw.get("batch") or "").strip()
        parent = str(raw.get("parent_cid") or "").strip()
        if not _BATCH_RE.match(batch) or not is_valid_conversation_id(parent):
            raise ValueError("批次文件字段非法")
        children_raw = raw.get("children")
        children: List[SubagentRecord] = []
        if isinstance(children_raw, list):
            for item in children_raw:
                if not isinstance(item, dict):
                    continue
                child_id = str(item.get("child_id") or "").strip()
                label = str(item.get("label") or "").strip()
                context = str(item.get("context") or "").strip()
                if not is_valid_conversation_id(child_id) or not label:
                    continue
                if context not in ("fork", "fresh"):
                    continue
                children.append(SubagentRecord(
                    child_id=child_id,
                    parent_cid=parent,
                    batch=batch,
                    label=label,
                    context=context,
                    created_at=int(item.get("created_at") or 0),
                ))
        return BatchRecord(
            batch=batch,
            parent_cid=parent,
            created_at=int(raw.get("created_at") or 0),
            children=children,
        )

    def _write(self, record: BatchRecord) -> None:
        path = self._path(record.parent_cid, record.batch)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": 1,
            "batch": record.batch,
            "parent_cid": record.parent_cid,
            "created_at": record.created_at,
            "children": [
                {
                    "child_id": child.child_id,
                    "label": child.label,
                    "context": child.context,
                    "created_at": child.created_at,
                }
                for child in record.children
            ],
        }
        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
            os.replace(temp, path)
        finally:
            try:
                if temp.exists():
                    temp.unlink()
            except OSError as exc:
                report_error("agent.subagent.batches.BatchStore._write", exc,
                             path=str(temp))

    def iter_batches(self) -> Iterator[BatchRecord]:
        if not self.root.is_dir():
            return
        for path in self.root.glob("*/*.json"):
            try:
                yield self._read(path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                report_error("agent.subagent.batches.BatchStore.iter_batches", exc,
                             path=str(path))
