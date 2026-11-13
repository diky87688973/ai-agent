# -*- coding: utf-8 -*-
"""子智能体 Web 动作：列表、历史、发送。"""
from __future__ import annotations

from typing import Any, Dict, Tuple

from agent.core.context import SERVICE_SUBAGENTS
from agent.subagent.models import SubagentError


class SubagentActions:
    """WebShell 的子智能体动作混入。"""

    def _subagent_manager(self) -> Any:
        context = getattr(self.app, "context", None)
        if context is None or not context.has(SERVICE_SUBAGENTS):
            return None
        return context.get(SERVICE_SUBAGENTS)

    def subagents(self, parent_cid: str, batch: str = "") -> Tuple[int, Dict[str, Any]]:
        manager = self._subagent_manager()
        if manager is None:
            return 503, {"ok": False, "error": "subagents_unavailable"}
        try:
            return 200, manager.list(parent_cid, batch)
        except SubagentError as exc:
            return 400, {"ok": False, "error": str(exc)}
        except ValueError as exc:
            return 400, {"ok": False, "error": str(exc)}

    def subagent_history(self, parent_cid: str, child_id: str, *,
                         before: str | None = None,
                         slice_history: bool = False) -> Tuple[int, Dict[str, Any]]:
        manager = self._subagent_manager()
        if manager is None:
            return 503, {"ok": False, "error": "subagents_unavailable"}
        try:
            cursor = int(before) if before is not None else None
            if cursor is not None and cursor < 0:
                raise ValueError("历史分页位置无效")
            child = manager.record(child_id)
            if child.parent_cid != str(parent_cid or "").strip():
                return 403, {"ok": False, "error": "parent_mismatch"}
            classic = self._classic_adapter()
            if classic is not None:
                payload = classic.history(child_id, store=manager.store_for(child_id),
                                          before=cursor, slice_history=slice_history)
                payload.update({
                    "ok": True,
                    "parent_cid": child.parent_cid,
                    "batch": child.batch,
                    "label": child.label,
                })
                return 200, payload
            return 200, {"ok": True, **manager.history(parent_cid, child_id)}
        except SubagentError as exc:
            return 404, {"ok": False, "error": str(exc)}
        except ValueError as exc:
            return 400, {"ok": False, "error": str(exc)}

    def subagent_send(
        self,
        parent_cid: str,
        child_id: str,
        msg: str,
        *,
        images: Any = None,
    ) -> Tuple[int, Dict[str, Any]]:
        manager = self._subagent_manager()
        if manager is None:
            return 503, {"ok": False, "error": "subagents_unavailable"}
        try:
            return 200, manager.send(
                parent_cid, child_id,
                msg=msg,
                images=images, user_send=True,
            )
        except SubagentError as exc:
            return 400, {"ok": False, "error": str(exc)}
        except ValueError as exc:
            return 400, {"ok": False, "error": str(exc)}
