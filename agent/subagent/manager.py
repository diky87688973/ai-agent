# -*- coding: utf-8 -*-
"""子 Agent 门面：组合持久化、生命周期与消息三个边界。"""
from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any, Dict

from agent.core import event_name as ev
from agent.core.error_report import report_error
from agent.mechanisms.mesh import MeshState
from agent.mechanisms.session_store import SessionStore
from agent.subagent.lifecycle import SubagentLifecycle
from agent.subagent.messaging import SubagentMessenger
from agent.subagent.models import SubagentError, SubagentRecord
from agent.subagent.repository import SubagentRepository


class SubagentManager:
    """对外只提供用例入口；内部依赖各自单一职责。"""

    def __init__(
        self,
        *,
        data_root: Path,
        parent_store: SessionStore,
        mesh: MeshState,
        queue: Any = None,
        event_bus: Any = None,
    ) -> None:
        self._repository = SubagentRepository(
            data_root=Path(data_root), parent_store=parent_store,
        )
        self._messenger = SubagentMessenger(
            repository=self._repository, mesh=mesh, queue=queue,
        )
        self._lifecycle = SubagentLifecycle(
            repository=self._repository,
            messenger=self._messenger,
            mesh=mesh,
            queue=queue if queue is not None else mesh.queue,
        )
        self.mesh = mesh
        self._event_bus = event_bus
        self._reported: Dict[str, str] = {}
        self._reported_lock = RLock()
        self._unsubscribe = None
        self._unsubscribe_start = None
        if event_bus is not None:
            self._unsubscribe = event_bus.subscribe(ev.TURN_ENDED, self._on_turn_ended)
            self._unsubscribe_start = event_bus.subscribe(ev.TURN_STARTED, self._on_turn_started)

    def _on_turn_started(self, event: Any) -> None:
        data = getattr(event, "data", None) or {}
        child_id = str(data.get("conversation_id") or "").strip()
        if child_id and self.is_child(child_id):
            with self._reported_lock:
                self._reported[child_id] = ""

    def _on_turn_ended(self, event: Any) -> None:
        data = getattr(event, "data", None) or {}
        child_id = str(data.get("conversation_id") or "").strip()
        if not child_id or not self.is_child(child_id):
            return
        child = self.record(child_id)
        latest = self._repository.latest_result(child.parent_cid, child_id)
        text = str(latest.get("result") or "").strip()
        if not text:
            text = "子智能体本轮没有输出。"
        with self._reported_lock:
            if self._reported.pop(child_id, "") == text:
                return
        try:
            self._messenger.send_to_parent(child_id, msg=text)
        except Exception as exc:
            report_error("agent.subagent.manager.completion_notice", exc,
                         child_id=child_id)

    def is_child(self, child_id: str) -> bool:
        return self._repository.is_child(child_id)

    def store_for(self, cid: str) -> SessionStore:
        return self._repository.store_for(cid)

    def record(self, child_id: str) -> SubagentRecord:
        return self._repository.record(child_id)

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
        return self._lifecycle.create(
            parent_cid,
            prompt=prompt,
            label=label,
            context=context,
            batch=batch,
            images=images,
        )

    def list(self, parent_cid: str, batch: str = "") -> Dict[str, Any]:
        return self._lifecycle.list(parent_cid, batch)

    def status(self, parent_cid: str, child_id: str) -> Dict[str, Any]:
        return self._lifecycle.status(parent_cid, child_id)

    def result(self, parent_cid: str, child_id: str) -> Dict[str, Any]:
        return self._lifecycle.result(parent_cid, child_id)

    def send(
        self,
        parent_cid: str,
        child_id: str,
        *,
        msg: str,
        images: Any = None,
    ) -> Dict[str, Any]:
        return self._messenger.send_to_child(
            parent_cid, child_id, msg=msg, images=images,
        )

    def send_to_parent(
        self,
        child_id: str,
        *,
        msg: str,
        images: Any = None,
    ) -> Dict[str, Any]:
        result = self._messenger.send_to_parent(child_id, msg=msg, images=images)
        if result.get("ok"):
            with self._reported_lock:
                self._reported[str(child_id)] = str(msg or "")
        return result

    def history(self, parent_cid: str, child_id: str) -> Dict[str, Any]:
        return self._repository.history(parent_cid, child_id)

    def shutdown(self) -> None:
        if callable(self._unsubscribe):
            try:
                self._unsubscribe()
            except Exception as exc:
                report_error("agent.subagent.manager.unsubscribe", exc)
            self._unsubscribe = None
        if callable(self._unsubscribe_start):
            try:
                self._unsubscribe_start()
            except Exception as exc:
                report_error("agent.subagent.manager.unsubscribe_start", exc)
            self._unsubscribe_start = None
        self._repository.shutdown()


__all__ = ["SubagentError", "SubagentManager"]
