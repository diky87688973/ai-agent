# -*- coding: utf-8 -*-
"""视觉授权 HTTP 端点。"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from .consent import CONSENT_OPTIONS, CONSENT_TITLE
from .state import VisionRuntime


def _body(args: Any) -> Dict[str, Any]:
    if not isinstance(args, dict):
        return {}
    body = args.get("body")
    return body if isinstance(body, dict) else {}


def _cid(args: Any) -> str:
    body = _body(args)
    return str(body.get("conversation_id") or args.get("conversation_id") or "")


def build_routes(ctx: Any, runtime: VisionRuntime) -> List[Callable[[], None]]:
    def pending(args: Dict[str, Any]) -> Any:
        cid = _cid(args)
        if not cid:
            return 400, {"ok": False, "error": "缺少 conversation_id"}
        item = runtime.pending(cid)
        if item is None:
            return 200, {"ok": True, "pending": None}
        return 200, {
            "ok": True,
            "pending": {
                "conversation_id": item["conversation_id"],
                "request_id": item["request_id"],
                "title": CONSENT_TITLE,
                "options": list(CONSENT_OPTIONS),
            },
        }

    def status(args: Dict[str, Any]) -> Any:
        cid = _cid(args)
        if not cid:
            return 400, {"ok": False, "error": "缺少 conversation_id"}
        return 200, runtime.status(cid)

    def confirm(args: Dict[str, Any]) -> Any:
        cid = _cid(args)
        body = _body(args)
        result = runtime.confirm(cid, str(body.get("request_id") or ""),
                                 str(body.get("choice") or ""))
        if not result.get("ok"):
            return 400, result
        call_id = str(result.get("call_id") or "")
        if result.get("decision") == "agree":
            data = {"ok": True, "consent_id": result["consent_id"]}
            error = ""
            ok = True
        else:
            data = {"ok": False, "error": "用户拒绝了视觉授权"}
            error = "用户拒绝了视觉授权"
            ok = False
        resumed = ctx.resume_suspended(
            cid, call_id, data, ok=ok,
            name="vision_request_open", error=error)
        if not resumed.get("ok"):
            runtime.stop(cid)
            return 500, {"ok": False, "error": resumed.get("error"), "consent_id": ""}
        return 200, {
            "ok": True,
            "decision": result["decision"],
            "consent_id": result["consent_id"],
        }

    def revoke(args: Dict[str, Any]) -> Any:
        cid = _cid(args)
        if not cid:
            return 400, {"ok": False, "error": "缺少 conversation_id"}
        return 200, runtime.revoke(cid)

    return [
        ctx.add_route("GET", "eye-consent/pending", pending),
        ctx.add_route("GET", "eye-consent/status", status),
        ctx.add_route("POST", "eye-consent/confirm", confirm),
        ctx.add_route("POST", "eye-consent/revoke", revoke),
    ]

__all__ = ["build_routes"]
