# -*- coding: utf-8 -*-
"""子智能体的持久化元数据形状。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


class SubagentError(Exception):
    """子智能体参数或权限错误。"""

    def __init__(self, message: str, code: str = "subagent_error") -> None:
        super().__init__(message)
        self.code = str(code or "subagent_error")


@dataclass(frozen=True)
class SubagentRecord:
    child_id: str
    parent_cid: str
    batch: str
    label: str
    context: str
    created_at: int

    def public(self, *, status: str = "idle", pending: int = 0) -> Dict[str, Any]:
        return {
            "child_id": self.child_id,
            "label": self.label,
            "context": self.context,
            "created_at": self.created_at,
            "status": status,
            "pending": int(pending),
        }


@dataclass
class BatchRecord:
    batch: str
    parent_cid: str
    created_at: int
    children: List[SubagentRecord] = field(default_factory=list)

    def public(self, *, statuses: Dict[str, Dict[str, Any]] | None = None) -> Dict[str, Any]:
        table = statuses or {}
        rows = []
        for child in self.children:
            info = table.get(child.child_id, {})
            rows.append(child.public(
                status=str(info.get("status") or "idle"),
                pending=int(info.get("pending") or 0),
            ))
        return {
            "batch": self.batch,
            "created_at": self.created_at,
            "children": rows,
        }
