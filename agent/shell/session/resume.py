# -*- coding: utf-8 -*-
"""外部工具结果回灌。"""
from __future__ import annotations

import sys
from typing import Any, Dict

from agent.core.events import Event


def splice_resume(*, app: Any, cid: str, resume: Dict[str, Any]) -> None:
    """把外部结果拼进会话事实（写前查重；失败不抛）。"""
    store = getattr(app, "store", None)
    call_id = str(resume.get("call_id") or "")
    if store is None or not call_id:
        return
    try:
        ok = bool(resume.get("ok", True))
        existing = {str((e.data or {}).get("call_id") or "")
                    for e in store.load(cid)
                    if e.type in ("tool_done", "tool_failed")}
        if call_id in existing:
            return
        name = str(resume.get("name") or "")
        store.append(cid, [
            Event("tool_done" if ok else "tool_failed", {
                "call_id": call_id,
                "name": name,
                "data": resume.get("data"),
                "error": str(resume.get("error") or ""),
            }),
            Event("tool_ended", {
                "call_id": call_id,
                "name": name,
                "status": "done" if ok else "failed",
                "elapsed_ms": 0,
            }),
        ])
    except Exception as exc:
        print(f"[session_runner] resume 拼接失败 cid={cid}: {exc}",
              file=sys.stderr, flush=True)
