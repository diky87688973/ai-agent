# -*- coding: utf-8 -*-
"""外部工具结果回灌。"""
from __future__ import annotations

from typing import Any, Dict

from agent.core.error_report import report_error
from agent.core.event_name import TOOL_DONE, TOOL_ENDED, TOOL_FAILED
from agent.core.events import Event
from agent.core.state_values import TOOL_DONE as TOOL_STATUS_DONE
from agent.core.state_values import TOOL_FAILED as TOOL_STATUS_FAILED


def splice_resume(*, app: Any, cid: str, resume: Dict[str, Any]) -> None:
    """把外部结果拼进会话事实（写前查重；失败不抛）。"""
    store = getattr(app, "store", None)
    call_id = str(resume.get("call_id") or "")
    if store is None or not call_id:
        return
    try:
        ok = bool(resume.get("ok", True))
        name = str(resume.get("name") or "")

        def _already_there(events) -> bool:
            return any(
                str((e.data or {}).get("call_id") or "") == call_id
                and e.type in (TOOL_DONE, TOOL_FAILED)
                for e in events
            )

        append_once = getattr(store, "append_if_absent", None)
        if callable(append_once):
            append_once(cid, _already_there, [
                Event(TOOL_DONE if ok else TOOL_FAILED, {
                    "call_id": call_id,
                    "name": name,
                    "data": resume.get("data"),
                    "error": str(resume.get("error") or ""),
                }),
                Event(TOOL_ENDED, {
                    "call_id": call_id,
                    "name": name,
                    "status": TOOL_STATUS_DONE if ok else TOOL_STATUS_FAILED,
                    "elapsed_ms": 0,
                }),
            ])
            return
        if _already_there(store.load(cid)):
            return
        store.append(cid, [
            Event(TOOL_DONE if ok else TOOL_FAILED, {
                "call_id": call_id,
                "name": name,
                "data": resume.get("data"),
                "error": str(resume.get("error") or ""),
            }),
            Event(TOOL_ENDED, {
                "call_id": call_id,
                "name": name,
                "status": TOOL_STATUS_DONE if ok else TOOL_STATUS_FAILED,
                "elapsed_ms": 0,
            }),
        ])
    except Exception as exc:
        report_error("agent.shell.session.resume.splice_resume", exc)
