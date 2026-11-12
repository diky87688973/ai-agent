# -*- coding: utf-8 -*-
"""外部工具结果回灌。"""
from __future__ import annotations

from typing import Any, Dict

from agent.core.error_report import report_error
from agent.core.event_name import CONFIRMATION_CLOSED, TOOL_DONE, TOOL_ENDED, TOOL_FAILED
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
            for event in reversed(events):
                if event.type == "input_claimed":
                    return True
                if event.data.get("call_id") != call_id:
                    continue
                if event.type in (TOOL_DONE, TOOL_FAILED):
                    return True
                if event.type == "tool_suspended":
                    return False
            return True

        store.append_if_absent(cid, _already_there, [
            Event(TOOL_DONE if ok else TOOL_FAILED, {
                "call_id": call_id,
                "name": name,
                "data": resume.get("data") if ok else None,
                "error": str(resume.get("error") or ""),
            }),
            Event(TOOL_ENDED, {
                "call_id": call_id,
                "name": name,
                "status": TOOL_STATUS_DONE if ok else TOOL_STATUS_FAILED,
                "elapsed_ms": 0,
            }),
        ], lookup={"call_id": call_id, "recent": True})
    except Exception as exc:
        report_error("agent.shell.session.resume.splice_resume", exc)


EXPIRED = "操作无效，该确认已过期"
UNANSWERED = "无结果：用户未作答"


def confirmation_store(app: Any, cid: str) -> Any:
    from agent.core.context import SERVICE_SUBAGENTS

    context = getattr(app, "context", None)
    if context is not None and context.has(SERVICE_SUBAGENTS):
        manager = context.get(SERVICE_SUBAGENTS)
        if manager.is_child(cid):
            return manager.store_for(cid)
    return getattr(app, "store", None)


def find_pending(store: Any, cid: str) -> Any:
    """Read the last unresolved suspension without allocating session state."""
    settled = set()
    if store is not None:
        indexed = getattr(store, "fact_matches", None)
        if callable(indexed):
            candidates = indexed(cid, pending=True)
        else:
            candidates = store.load(cid)
        for event in reversed(candidates):
            data = event.data
            call_id = str(data.get("call_id") or "")
            if event.type == "input_claimed":
                break
            if event.type in (TOOL_DONE, TOOL_FAILED):
                settled.add(call_id)
            elif event.type == "tool_suspended" and call_id and call_id not in settled:
                envelope = data.get("envelope") or {}
                return {**envelope, "call_id": call_id, "name": data.get("name", ""),
                        "kind": envelope.get("kind") or "confirm"}
    return None


def read_pending(session: Any, store: Any, cid: str) -> Any:
    """Snapshot confirmation state without creating or updating a session bucket."""
    if store is None:
        if session is None:
            return None
        with session.confirmation_lock:
            return session.pending_confirm
    current = find_pending(store, cid)
    if current is not None or session is None:
        return current
    # Prefer persisted state once the call exists in storage. An execution host
    # without a bound fact sink can only expose its current in-memory suspension.
    with session.confirmation_lock:
        pending = session.pending_confirm
        lookup = getattr(store, "fact_matches", None)
        if pending and callable(lookup) and not lookup(
            cid, call_id=pending["call_id"], confirmation=True, limit=1,
        ):
            return pending
    return None


def load_pending(session: Any, store: Any, cid: str) -> Any:
    """Restore the suspension into a session already held by its owner."""
    session.pending_confirm = read_pending(session, store, cid)
    return session.pending_confirm


def write_resolution(store: Any, cid: str, call_id: str, name: str,
                     result: Dict[str, Any], *, request_id: str = "", continue_after: bool = False) -> bool:
    if store is None:
        raise OSError("会话事实存储不可用")
    ok = bool(result.get("ok"))
    rows = [
        Event(TOOL_DONE if ok else TOOL_FAILED, {
            "call_id": call_id, "name": name, "data": result.get("data"),
            "error": str(result.get("error") or ""),
            **({"_confirmation_request_id": request_id} if continue_after else {}),
        }),
        Event(TOOL_ENDED, {
            "call_id": call_id, "name": name,
            "status": TOOL_STATUS_DONE if ok else TOOL_STATUS_FAILED, "elapsed_ms": 0,
        }),
    ]

    def skip(events):
        if not events:
            raise OSError("挂起事实尚未落盘或已经结算，请刷新后重试")
        current = events[-1].data
        envelope = current.get("envelope") or {}
        actual_request = str(envelope.get("request_id") or current.get("call_id") or "")
        return current.get("call_id") != call_id or bool(request_id and actual_request != request_id)

    return bool(store.append_if_absent(
        cid, skip, rows, retry_pending=False, lookup={"pending": True},
    ))


def confirmation_can_resume(store: Any, cid: str, call_id: str, request_id: str) -> bool:
    if store is None or not call_id or not request_id:
        return False
    facts = store.fact_matches(cid, call_id=call_id, resumable=True)
    return bool(facts and facts[0].data.get("_confirmation_request_id") == request_id)


def dispatch_confirmation(app: Any, cid: str, call_id: str, request_id: str) -> dict:
    """An accepted answer remains in the facts if scheduling the next turn fails."""
    try:
        dispatch = app.mesh.submit(
            cid, {"content": "", "_confirmation_resume": (call_id, request_id)}, origin="system",
            dedupe_key=f"confirmation:{call_id}:{request_id}",
        )
    except Exception as exc:
        report_error("session.resume.dispatch", exc, conversation_id=cid)
        dispatch = {}
    queued = bool(dispatch.get("queued"))
    run_id = str(dispatch.get("run_id") or "")
    result = {"ok": True, "conversation_id": cid, "call_id": call_id,
              "queued": queued, "run_id": run_id}
    if not queued and not run_id:
        result.update(resume_pending=True, error="确认已保存，续跑待重试")
    return result


def retry_confirmation(app: Any, cid: str, call_id: str, request_id: str) -> dict:
    session = app.session_contexts.resolve_sync(cid)
    with session.confirmation_lock:
        store = confirmation_store(app, cid)
        if not confirmation_can_resume(store, cid, call_id, request_id):
            return {"ok": False, "expired": True, "error": "这次确认无需再次续跑"}
        if app.mesh.is_stopped(cid):
            return {"ok": False, "error": "会话已终止，请发送新消息继续"}
        return dispatch_confirmation(app, cid, call_id, request_id)


def notify_closed(app: Any, cid: str, pending: Dict[str, Any], *, expired: bool) -> None:
    bus = getattr(app, "event_bus", None)
    if bus is not None:
        try:
            bus.publish(Event(CONFIRMATION_CLOSED, {
                "conversation_id": cid, "call_id": pending["call_id"],
                "request_id": pending.get("request_id") or pending["call_id"],
                "expired": expired,
            }))
        except Exception as exc:
            report_error("shell.session.resume.notify_closed", exc, conversation_id=cid)


def interrupt_confirmation(app: Any, cid: str, store: Any, *,
                           on_pending: Any = None) -> bool:
    contexts = getattr(app, "session_contexts", None)
    if contexts is None:
        return False
    session = contexts.resolve_sync(cid)
    if store is None and not session.pending_confirm:
        return False
    with session.confirmation_lock:
        pending = load_pending(session, store, cid)
        if pending is None:
            return False
        if on_pending is not None:
            on_pending()
        written = write_resolution(
            store, cid, pending["call_id"], pending.get("name", ""),
            {"ok": False, "error": UNANSWERED},
            request_id=str(pending.get("request_id") or pending["call_id"]),
        )
        session.pending_confirm = None
    if written:
        notify_closed(app, cid, pending, expired=True)
    return written
