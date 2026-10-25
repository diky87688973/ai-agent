# -*- coding: utf-8 -*-
"""子 Agent 父子消息投递；不持有会话或批次持久化职责。"""
from __future__ import annotations

from typing import Any, Dict, Optional

from agent.core.input_attachments import normalize_images
from agent.mechanisms.conversation_queue import QueueError
from agent.mechanisms.mesh import MeshState
from agent.subagent.models import SubagentError, SubagentRecord
from agent.subagent.repository import SubagentRepository


class SubagentMessenger:
    """校验父子关系，并通过 MeshState / ConversationQueue 投递。"""

    def __init__(self, *, repository: SubagentRepository, mesh: MeshState,
                 queue: Any = None) -> None:
        self.repository = repository
        self.mesh = mesh
        self.queue = queue if queue is not None else mesh.queue

    def _record_for_parent(self, parent_cid: str, child_id: str) -> SubagentRecord:
        child = self.repository.record(child_id)
        if child.parent_cid != str(parent_cid or "").strip():
            raise SubagentError("不是该父会话的子 Agent", "parent_mismatch")
        return child

    def _parent_name(self, parent_cid: str) -> str:
        meta = self.mesh.get_agent(parent_cid)
        return str(meta.get("name") or parent_cid[:12])

    def _child_name(self, child: SubagentRecord) -> str:
        return child.label or child.child_id[:12]

    def send_to_child(
        self,
        parent_cid: str,
        child_id: str,
        *,
        msg: str,
        images: Any = None,
    ) -> Dict[str, Any]:
        child = self._record_for_parent(parent_cid, child_id)
        return self._submit(
            child.child_id,
            parent_cid,
            msg,
            images,
            insert_send=True,
            sender_name=self._parent_name(parent_cid),
            sender_role="parent",
        )

    def send_to_parent(
        self,
        child_id: str,
        *,
        msg: str,
        images: Any = None,
    ) -> Dict[str, Any]:
        child = self.repository.record(child_id)
        return self._submit(
            child.parent_cid,
            child.child_id,
            msg,
            images,
            insert_send=True,
            sender_name=self._child_name(child),
            sender_role="subagent",
        )

    def _submit(
        self,
        target_cid: str,
        sender_cid: str,
        msg: str,
        images: Any,
        *,
        insert_send: bool,
        sender_name: Optional[str] = None,
        sender_role: str = "parent",
    ) -> Dict[str, Any]:
        text = str(msg or "").strip()
        attachments = normalize_images(images)
        if not text and not attachments:
            raise SubagentError("消息不能为空", "empty_message")
        payload: Dict[str, Any] = {
            "content": text,
            "_sender": sender_cid,
            "_sender_name": sender_name or sender_cid[:12],
            "_sender_role": sender_role,
            "_agent_peer_message": True,
            "_message_kind": "peer",
        }
        if attachments:
            payload["attachments"] = attachments
        try:
            result = self.mesh.submit(target_cid, payload)
        except QueueError as exc:
            raise SubagentError(str(exc), "queue_failed") from exc
        item = result.get("queue_item") if isinstance(result, dict) else None
        inserted = False
        if insert_send and isinstance(item, dict) and item.get("id"):
            try:
                self.queue.set_insert(target_cid, str(item["id"]))
                inserted = True
            except QueueError as exc:
                if exc.code != "not_found":
                    raise SubagentError(str(exc), "insert_failed") from exc
        return {
            "ok": True,
            "target_id": target_cid,
            "queued": bool(result.get("queued")),
            "inserted": inserted,
            "run_id": str(result.get("run_id") or ""),
        }
