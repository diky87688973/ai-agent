# -*- coding: utf-8 -*-
"""会话暂停态与用户确认回路。

暂停是宿主状态：内核不阻塞、不等待，暂停 = 回合正常结束 + `paused_for_user_confirm`
信令，恢复由用户作答触发新回合。已持久化的挂起事实是待确认内容的权威。

宿主需提供：`_app`、`_shell`、`_paused`（按会话记的瞬时暂停观测值）。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import agent.shell.classic_adapter.contract as C
from agent.shell.session.resume import confirmation_store, load_pending


class ConfirmMixin:
    """暂停态、待确认状态与两段式作答。"""

    def is_paused(self, cid: str) -> bool:
        """该会话是否停在"等用户作答"（宿主状态）。

        内核不阻塞、不等待：暂停就是回合正常结束（资源已释放、服务可服务别的会话），
        只是多了一帧 `paused_for_user_confirm` 信令，让宿主知道"这不是正常收尾"。
        恢复由用户在界面上作答触发 `POST /api/chat/user-confirm` → 起新回合。
        所以"是否暂停"是适配层按会话记的状态，不是内核里的阻塞态。
        """
        cid = C.normalize_cid(cid)
        if not cid:
            return False
        return bool(self._paused.get(cid))

    def pause_state(self) -> Dict[str, Any]:
        """暂停态快照（供 /health 或诊断观察）。

        `pending_confirm` 从内核的 `SessionContext` 现读（权威在那里），
        本类不另存一份：两处各存一份迟早不一致。
        """
        return {
            "paused": sorted(cid for cid, on in self._paused.items() if on),
            "pending_confirm": self.pending_confirms(),
        }

    def pending_confirms(self) -> Dict[str, Any]:
        """全量扫一遍会话状态，给出当前所有待确认（`cid → call_id`）。

        `_paused` 不作复用来源：那是"上一次 `turn_ended` 说停着"的瞬时观测，
        而权威状态是 `SessionContext.pending_confirm`。两者可能短暂不一致
        （例如新回合还没收尾），所以可观测性接口一律以权威为准。
        """
        contexts = getattr(self._app, "session_contexts", None)
        if contexts is None:
            return {}
        buckets = contexts.buckets()
        out: Dict[str, Any] = {}
        for cid, session in buckets.items():
            with session.confirmation_lock:
                pending = session.pending_confirm
                if pending:
                    out[cid] = pending["call_id"]
        return out

    # ── 用户确认回路（`user_confirm` 工具的第二段）──────────
    #
    # 经典界面的确认模态在用户点「确认」后 POST 的是
    #   `{conversation_id, confirm: <用户选的文本>, mode, model}`
    # `agent-ui.js` 的 `submitUserConfirm` 就是这条请求，并期待返回体带 `run_id`——
    # 也就是说它期待服务端把选择送回模型，而不是只回一个"收到"。
    #
    # 工具声明不暴露 `confirm`：用户确认结果由宿主写成那次调用的工具结果。
    # 适配层据此把结果投回该会话：忙则入队（`queued: true`），
    # 闲则直接起新回合（拿到 `run_id`）。
    def user_confirm(self, cid: str, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """处理确认端点。两类请求在这里分流（经典界面两种情况共用一个端点）。"""
        cid = C.normalize_cid(cid)
        if not cid:
            return 400, {"error": "missing conversation_id"}
        approval = str(body.get("approval") or "").strip().lower()
        confirm_id = str(body.get("confirm_id") or "").strip()
        if confirm_id and "confirm" not in body and not approval:
            return self._shell.confirm(cid, confirm_id)
        call_id = str(body.get("call_id") or "").strip()
        request_id = str(body.get("request_id") or "").strip()
        if not call_id or not request_id:
            return 400, {"ok": False, "error": "缺少 call_id 或 request_id，请刷新确认卡片"}
        if body.get("retry_resume") is True:
            from agent.shell.session.resume import retry_confirmation

            result = retry_confirmation(self._app, cid, call_id, request_id)
            return (409 if result.get("expired") else 200), result
        if approval:
            if approval not in ("agree", "reject"):
                return 400, {"ok": False, "error": "approval 只能是 agree 或 reject"}
            result = self.submit_approval(cid, approval == "agree", call_id, request_id)
        else:
            result = self.submit_user_choice(cid, str(body.get("confirm") or ""), call_id, request_id)
        if result.get("expired"):
            return 409, result
        if confirm_id and result.get("ok"):
            _, gate_result = self._shell.confirm(cid, confirm_id)
            return 200, {**result, **gate_result}
        return 200, result

    def submit_user_choice(self, cid: str, text: str, call_id: str,
                           request_id: str) -> Dict[str, Any]:
        text = text.strip()
        result = self._app.resume_suspended(
            cid, call_id, {"confirm": text} if text else None,
            request_id=request_id, kind="confirm", ok=bool(text),
            error="" if text else "用户取消了这次确认（未作答）")
        return {**result, "confirmed": bool(text and result.get("ok")),
                "declined": not text and bool(result.get("ok")), "resumed_call": result.get("call_id", "")}

    def submit_approval(self, cid: str, agreed: bool, call_id: str,
                        request_id: str) -> Dict[str, Any]:
        def resolve(session, pending):
            decision = "同意" if agreed else "不同意"
            data = {"decision": decision}
            resolution = {"ok": True, "data": data,
                          "response": {"decision": decision, "confirmed": agreed, "approval_id": ""}}
            if agreed:
                option = str(pending.get("option_id") or "").strip()
                if not option:
                    return {"rejected": True, "error": "待审批缺少 option_id"}
                approval_id = session.grant_approval(option)
                data["approval_id"] = approval_id
                resolution["response"]["approval_id"] = approval_id
                resolution["rollback"] = lambda: session.approvals.pop(approval_id, None)
            return resolution

        return self._app.resume_suspended(
            cid, call_id, request_id=request_id, kind="approval", resolve=resolve)

    def _session(self, cid: str) -> Any:
        """取该会话的 `SessionContext`（待确认状态记在这里）。"""
        contexts = getattr(self._app, "session_contexts", None)
        if contexts is None:
            return None
        return contexts.resolve_sync(cid)

    def pending_confirm(self, cid: str) -> Optional[Dict[str, Any]]:
        """该会话当前挂着的待确认（`SessionContext.pending_confirm`）。

        它是跨回合的会话态：暂停发生在上一回合、作答在下一回合，
        它是跨回合状态，放回合级上下文会随回合消亡；适配层只读。
        """
        cid = C.normalize_cid(cid)
        if not cid:
            return None
        session = self._session(cid)
        if session is None:
            return None
        with session.confirmation_lock:
            pending = load_pending(session, confirmation_store(self._app, cid), cid)
            return dict(pending) if isinstance(pending, dict) else None


__all__ = ["ConfirmMixin"]
