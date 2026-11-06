# -*- coding: utf-8 -*-
"""子智能体创建、状态与列表；不直接持久化文件，不拼装消息。"""
from __future__ import annotations

import time
from typing import Any, Dict

from agent.common.status import AGENT_BUSY, AGENT_IDLE
from agent.core.error_report import report_error
from agent.core.input_attachments import normalize_images
from agent.mechanisms.mesh import MeshState
from agent.subagent.messaging import SubagentMessenger
from agent.subagent.models import SubagentError
from agent.subagent.repository import MAX_LABEL, SubagentRepository


class SubagentLifecycle:
    """创建会话、注册运行身份、启动首回合、计算忙闲。"""

    def __init__(
        self,
        *,
        repository: SubagentRepository,
        messenger: SubagentMessenger,
        mesh: MeshState,
        queue: Any = None,
    ) -> None:
        self.repository = repository
        self.messenger = messenger
        self.mesh = mesh
        self.queue = queue if queue is not None else mesh.queue

    def _status_fields(self, child_id: str) -> Dict[str, Any]:
        """按当前连续 run 派生忙闲与开始时间；插话沿用同一 run。"""
        started = self.mesh.run_started_at(child_id)
        if started is None:
            return {"status": AGENT_IDLE}
        return {
            "status": AGENT_BUSY,
            "busy_since": int(started),
            "busy_seconds": max(0, int(time.time() - started)),
        }

    def _validate(
        self,
        parent_cid: str,
        prompt: str,
        label: str,
        context: str,
        images: Any,
    ) -> tuple[str, str, str, str]:
        parent = str(parent_cid or "").strip()
        if not parent:
            raise SubagentError("缺少父会话 id", "missing_parent")
        if self.mesh.get_agent(parent).get("role") == "subagent":
            raise SubagentError("子智能体不能再创建子智能体", "depth_limit")
        text = str(prompt or "").strip()
        title = str(label or "").strip()
        if not text and not normalize_images(images):
            raise SubagentError("缺少任务内容", "empty_prompt")
        if not title:
            raise SubagentError("label 必填", "missing_label")
        if len(title) > MAX_LABEL:
            raise SubagentError(f"label 不能超过 {MAX_LABEL} 字", "label_too_long")
        mode = str(context or "").strip().lower()
        if mode not in ("fork", "fresh"):
            raise SubagentError("context 必须是 fork 或 fresh", "invalid_context")
        return parent, text, title, mode

    def create(
        self,
        parent_cid: str,
        *,
        prompt: str,
        label: str,
        context: str = "fork",
        batch: str = "",
        images: Any = None,
    ) -> Dict[str, Any]:
        parent, text, title, mode = self._validate(
            parent_cid, prompt, label, context, images,
        )
        child = self.repository.prepare(
            parent_cid=parent,
            batch=batch,
            label=title,
            context=mode,
        )
        self.mesh.upsert_agent(
            child.child_id,
            name=title,
            role="subagent",
            parent_cid=parent,
            batch=child.batch,
        )
        try:
            started = self.messenger.send_to_child(
                parent,
                child.child_id,
                msg=text,
                images=images,
            )
        except Exception as exc:
            report_error("agent.subagent.lifecycle.create_start", exc,
                         child_id=child.child_id)
            try:
                self.repository.abort(child.child_id)
                self.mesh.remove_agent(child.child_id)
            except Exception as cleanup_exc:
                report_error("agent.subagent.lifecycle.create_rollback", cleanup_exc,
                             child_id=child.child_id)
            raise SubagentError(
                f"子智能体首回合启动失败：{exc}", "start_failed",
            ) from exc
        fields = self._status_fields(child.child_id)
        return {
            "ok": True,
            "batch": child.batch,
            "child_id": child.child_id,
            "label": title,
            "status": fields["status"],
            **({"busy_since": fields["busy_since"],
                "busy_seconds": fields["busy_seconds"]}
               if "busy_seconds" in fields else {}),
            "queued": bool(started.get("queued")),
        }

    def list(self, parent_cid: str, batch: str = "") -> Dict[str, Any]:
        rows = self.repository.list_batches(str(parent_cid or "").strip(), batch)
        counts = {AGENT_BUSY: 0, AGENT_IDLE: 0}
        batches = []
        for row in rows:
            statuses = {}
            for child in row.children:
                pending = int(self.queue.size(child.child_id))
                fields = self._status_fields(child.child_id)
                status = str(fields["status"])
                counts[status] += 1
                statuses[child.child_id] = {**fields, "pending": pending}
            batches.append(row.public(statuses=statuses))
        return {"ok": True, "batches": batches, "counts": counts}

    def result(self, parent_cid: str, child_id: str) -> Dict[str, Any]:
        payload = self.repository.latest_result(parent_cid, child_id)
        child = self.repository.record(child_id)
        payload.update({
            "ok": True,
            **self._status_fields(child.child_id),
        })
        return payload

    def status(self, parent_cid: str, child_id: str) -> Dict[str, Any]:
        child = self.repository.record(child_id)
        if child.parent_cid != str(parent_cid or "").strip():
            raise SubagentError("不是该父会话的子智能体", "parent_mismatch")
        return {
            "ok": True,
            "child_id": child.child_id,
            "batch": child.batch,
            "label": child.label,
            **self._status_fields(child.child_id),
            "pending": int(self.queue.size(child.child_id)),
        }
