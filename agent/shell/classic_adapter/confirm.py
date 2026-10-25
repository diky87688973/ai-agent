# -*- coding: utf-8 -*-
"""会话暂停态与用户确认回路。

暂停是宿主状态：内核不阻塞、不等待，暂停 = 回合正常结束 + `paused_for_user_confirm`
信令，恢复由用户作答触发新回合。待确认内容的权威在
`SessionContext.pending_confirm`，本模块只读。

宿主需提供：`_app`、`_shell`、`_paused`（按会话记的瞬时暂停观测值）。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import agent.shell.classic_adapter.contract as C
from agent.core.error_report import report_error


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
            pending = getattr(session, "pending_confirm", None)
            if isinstance(pending, dict) and pending:
                out[cid] = pending.get("call_id")
        return out

    # ── 用户确认回路（`user_confirm` 工具的第二段）──────────
    #
    # 经典界面的确认模态在用户点「确认」后 POST 的是
    #   `{conversation_id, confirm: <用户选的文本>, mode, model}`
    # `agent-ui.js` 的 `submitUserConfirm` 就是这条请求，并期待返回体带 `run_id`——
    # 也就是说它期待服务端把选择送回模型，而不是只回一个"收到"。
    #
    # 工具声明也印证这点：次段调用要带 `confirm`（用户确认结果），模型才能完成回路。
    # 所以适配层必须把 `confirm` 经 `mesh.submit` 投回该会话：
    # 忙则入队（`queued: true`），闲则直接起新回合（拿到 `run_id`）。
    def user_confirm(self, cid: str, body: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """处理确认端点。两类请求在这里分流（经典界面两种情况共用一个端点）。"""
        cid = C.normalize_cid(cid)
        if not cid:
            return 400, {"error": "missing conversation_id"}
        approval = str(body.get("approval") or "").strip().lower()
        if approval:
            if approval not in ("agree", "reject"):
                return 400, {"ok": False, "error": "approval 只能是 agree 或 reject"}
            return 200, self.submit_approval(cid, approval == "agree")
        confirm_id = str(body.get("confirm_id") or "").strip()
        confirm_text = str(body.get("confirm") or "").strip()

        # ① 写盘门控：带 `confirm_id` → 解锁预览快照（内核既有行为，不动）。
        gate_result: Optional[Tuple[int, Dict[str, Any]]] = None
        if confirm_id:
            shell = self._shell
            confirmer = getattr(shell, "confirm", None) if shell is not None else None
            if callable(confirmer):
                gate_result = confirmer(cid, confirm_id)

        # ② 选择回填：带 `confirm` 文本 → 把用户选择送回模型（`user_confirm` 的第二段）。
        if confirm_text:
            submitted = self.submit_user_choice(cid, confirm_text)
            if gate_result is not None and gate_result[0] != 200:
                # 门控失败但选择已投出：两者都告诉前端，回填不算失败
                return 200, {**gate_result[1], **submitted, "confirmed": False}
            return 200, submitted

        if gate_result is not None:
            return gate_result

        # 既没有 `confirm_id` 也没有 `confirm` 文本：模态的「取消」走这里。
        #
        # 必须交给 `submit_user_choice`，不能就地返回 200 了事：
        #   ① 挂起会继续保持 —— 用户以为取消了，其实那次调用还在等作答；
        #   ② 那次调用的 `tool_result` 永不出现 → 悬空的 `assistant(tool_calls)`
        #      留在历史里 → 该会话之后每条消息都 400，不可自愈。
        # 交给 `submit_user_choice` 后，"取消"被当成"拒绝作答"记成工具结果，
        # 既闭合了配对，也让模型知道用户不想答（它可以改问法或换方案）。
        return 200, self.submit_user_choice(cid, "")

    def submit_user_choice(self, cid: str, text: str) -> Dict[str, Any]:
        """用户作答 → 把选择写成那次调用的返回值，再起新回合（两段式第二段）。

        选择不写成新用户发言：那样模型要重新理解一遍「左」是什么，还得自己判断
        该不该再问一次，往往会重复提问。写成工具返回值，模型看到的是"工具终于返回了
        答案"，接着往下做即可。

        权威状态在内核的 `SessionContext.pending_confirm`：
        首段返回信封时由管道记下，回合放行结束；这里读它拿到 `call_id`，写入那次调用
        唯一的 `tool_result`。
        """
        cid = C.normalize_cid(cid)
        if not cid:
            return {"ok": False, "error": "invalid conversation_id", "confirmed": False}
        mesh = getattr(self._app, "mesh", None)
        if mesh is None:
            return {"ok": False, "error": "mesh 不可用", "confirmed": False}

        # 挂起状态记在会话上下文里（内核侧写的），适配层只读。
        pending = self.pending_confirm(cid)
        call_id = str((pending or {}).get("call_id") or "")
        payload: Dict[str, Any] = {"content": "", "attachments": [], "mode": "", "model": ""}
        # 空文本 = 用户在模态上点了「取消」。这不是"没作答"，而是"拒绝作答"：
        # 拒绝也作为那次调用的结果交回去，否则
        #   ① 那次调用的 `tool_result` 永不出现 → 悬空的 `assistant(tool_calls)`
        #      留在历史里（该会话之后每条消息都 400，不可自愈）；
        #   ② 若照"起一个没有输入的新回合"处理，内核那一轮不产出任何事实
        #      → 永远不发 `done` → 前端「正在思考中」永久转圈、发送按钮消失
        #      （用户只能点「停止」逃生）。
        text = str(text or "")
        declined = not text.strip()
        if str((pending or {}).get("kind") or "") == "approval":
            # 审批挂起不接受选项文本。空 confirm 在这里不记成取消。
            return {
                "ok": False,
                "error": "当前挂起的是审批，confirm 文本不作为作答",
                "confirmed": False,
                "conversation_id": cid,
                "queued": False,
                "run_id": "",
                "resumed_call": "",
            }
        if call_id:
            # 经运行器提交结果：由它把结果拼成 `tool_result` 事实并起一轮。
            # 事实由运行器写入：适配层直接写会成为第二个事实写点，
            # 也会绕开"写前查重"。
            # `resume` 走消息体，所以忙时入队也正确（结果随队列入队，不会丢）。
            payload["resume"] = (
                {"call_id": call_id, "ok": False,
                 "error": "用户取消了这次确认（未作答）"}
                if declined else
                {"call_id": call_id, "ok": True, "data": {"confirm": text}}
            )
        elif declined:
            # 没有挂起调用可拒绝：不起空回合——那正是"永久转圈"的来源。
            return {"ok": True, "confirmed": False, "declined": True,
                    "conversation_id": cid, "queued": False, "run_id": "",
                    "resumed_call": "",
                    "note": "没有待确认的调用，取消未触发新回合"}
        if call_id:
            self._clear_pending(cid)

        try:
            result = mesh.submit(cid, dict(payload))
        except Exception as exc:
            report_error(
                "agent.shell.classic_adapter.confirm.ConfirmMixin.submit_user_choice", exc
            )
            return {"ok": False, "error": str(exc), "confirmed": False}
        return {
            "ok": True,
            "confirmed": not declined,
            "declined": declined,
            "conversation_id": cid,
            "queued": bool(result.get("queued")),
            "run_id": str(result.get("run_id") or ""),
            # 是否真的把结果交回给了内核（没有挂起调用时为假——退化成纯新回合）
            "resumed_call": call_id,
        }

    def submit_approval(self, cid: str, agreed: bool) -> Dict[str, Any]:
        """审批作答。同意时签发 `approval_id` 并记下 `option_id`；驳回的结果是「不同意」。

        结果写回挂起的那次 `approval_confirm`。
        """
        cid = C.normalize_cid(cid)
        if not cid:
            return {"ok": False, "error": "invalid conversation_id", "confirmed": False}
        mesh = getattr(self._app, "mesh", None)
        if mesh is None:
            return {"ok": False, "error": "mesh 不可用", "confirmed": False}
        pending = self.pending_confirm(cid)
        kind = str((pending or {}).get("kind") or "")
        call_id = str((pending or {}).get("call_id") or "")
        if kind != "approval" or not call_id:
            return {
                "ok": False,
                "error": "没有待审批的调用",
                "confirmed": False,
                "conversation_id": cid,
                "queued": False,
                "run_id": "",
                "resumed_call": "",
            }
        approval_id = ""
        if agreed:
            option_id = str((pending or {}).get("option_id") or "").strip()
            session = self._session(cid)
            if not option_id or session is None:
                return {
                    "ok": False,
                    "error": "待审批缺少 option_id",
                    "confirmed": False,
                    "conversation_id": cid,
                    "queued": False,
                    "run_id": "",
                    "resumed_call": "",
                }
            approval_id = session.grant_approval(option_id)
            data: Dict[str, Any] = {"decision": "同意", "approval_id": approval_id}
        else:
            data = {"decision": "不同意"}
        payload: Dict[str, Any] = {
            "content": "",
            "attachments": [],
            "mode": "",
            "model": "",
            "resume": {"call_id": call_id, "ok": True, "data": data},
        }
        self._clear_pending(cid)
        try:
            result = mesh.submit(cid, dict(payload))
        except Exception as exc:
            report_error(
                "agent.shell.classic_adapter.confirm.ConfirmMixin.submit_approval", exc
            )
            return {"ok": False, "error": str(exc), "confirmed": False}
        return {
            "ok": True,
            "confirmed": agreed,
            "decision": data["decision"],
            "approval_id": approval_id,
            "conversation_id": cid,
            "queued": bool(result.get("queued")),
            "run_id": str(result.get("run_id") or ""),
            "resumed_call": call_id,
        }

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
        pending = getattr(session, "pending_confirm", None) if session is not None else None
        return dict(pending) if isinstance(pending, dict) else None

    def _clear_pending(self, cid: str) -> None:
        """清掉该会话的待确认状态（作答已消费，留着会让下次作答回到旧调用上）。"""
        session = self._session(cid)
        if session is not None:
            session.pending_confirm = None


__all__ = ["ConfirmMixin"]
