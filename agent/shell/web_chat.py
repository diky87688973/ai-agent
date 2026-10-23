# -*- coding: utf-8 -*-
"""聊天输入、待发送队列与停止 / 确认动作。"""
from __future__ import annotations

from typing import Any, Dict, Tuple

from agent.core.input_attachments import normalize_images
from agent.mechanisms.conversation_queue import QueueError
from agent.mechanisms.session_store import is_valid_conversation_id, new_conversation_id
from agent.shell.web_static import MODE_VALUES


class ChatActions:
    """提交输入、管理待发送队列、请求停止与确认写盘预览。"""

    def _send_draft(self, cid: str, text: str, attachments: Any, draft_id: str) -> Tuple[int, Dict[str, Any]]:
        """重发已召回草稿；身份由队列项决定。"""
        try:
            item = self.app.conversation_queue.resubmit_draft(
                cid, draft_id, content=text, attachments=attachments,
            )
        except QueueError as exc:
            return 409, {"ok": False, "error": str(exc)}
        if self.app.mesh.is_running(cid):
            return 200, {
                "ok": True, "conversation_id": cid, "run_id": "",
                "queued": True, "queue_item": item,
                "revision": self.app.conversation_queue.revision(cid),
            }
        claimed = self.app.conversation_queue.claim_item(cid, item["id"])
        if claimed is None:
            return 409, {"ok": False, "error": "消息已不在队列"}
        sender = claimed.get("sender") if isinstance(claimed.get("sender"), dict) else None
        start_payload: Dict[str, Any] = {
            "content": str(claimed.get("content") or ""),
            "attachments": claimed.get("attachments") or None,
        }
        if sender:
            start_payload["_sender"] = sender.get("cid")
            start_payload["_sender_name"] = sender.get("name")
        started = self.app.runner.start(cid, start_payload)
        if not started:
            self.app.conversation_queue.release(cid, item["id"])
            return 503, {"ok": False, "error": "会话启动失败"}
        self.app.conversation_queue.complete(cid, item["id"])
        return 200, {"ok": True, "conversation_id": cid,
                     "run_id": started, "queued": False}

    def send(
        self,
        cid: str,
        text: str,
        mode: str = "",
        images: Any = None,
        model: str = "",
        draft_id: str = "",
    ) -> Tuple[int, Dict[str, Any]]:
        """提交输入：空闲直接启动，忙时进入待发送队列。

        `images`：可选截图附件，形如 `[{mime, data_base64}]`；数量口径由
        `normalize_images` 统一控制；
        有图无字也算有效输入（纯截图提问是常见用法）。

        `model`：会话级模型选择（空串 = 不改动既有选择）。落 `live_state` 持久化 ——
        刷新页面乃至换进程，同一会话选的都是同一个模型。校验放在解析器落位之后，
        未配置的名字一律拒绝（400），避免"选择了却悄悄用默认模型"。
        """
        text = str(text or "").strip()
        attachments = normalize_images(images)
        if not text and not attachments:
            return 400, {"error": "empty message"}
        cid = str(cid or "").strip()
        if cid and not is_valid_conversation_id(cid):
            return 400, {"error": "invalid conversation_id"}
        if not cid:
            cid = new_conversation_id()
        mode = str(mode or "").strip().lower()
        if mode and mode not in MODE_VALUES:
            return 400, {"error": "invalid mode"}
        if mode:
            self.app.live_state.set_mode(cid, mode)
        want_model = str(model or "").strip()
        if want_model:
            allowed = self.available_models()
            if allowed and want_model not in allowed:
                # 有清单就按清单拒；清单为空（未配置）时不拦，交由 provider 决定
                return 400, {"error": f"unknown model: {want_model}"}
            before = str(self.app.live_state.get_model(cid) or "")
            self.app.live_state.set_model(cid, want_model)
            if before != want_model:
                self._announce_model(cid, want_model)
        if draft_id:
            return self._send_draft(cid, text, attachments, draft_id)
        payload: Dict[str, Any] = {"content": text}
        if attachments:
            payload["attachments"] = attachments
        try:
            result = self.app.mesh.submit(cid, payload)
        except QueueError as exc:
            return 503, {"ok": False, "error": str(exc)}
        if result.get("queued"):
            return 200, {
                "ok": True,
                "conversation_id": cid,
                "run_id": "",
                "queued": True,
                "queue_item": result.get("queue_item"),
                "revision": self.app.conversation_queue.revision(cid),
            }
        started = str(result.get("run_id") or "")
        if not started:
            return 503, {"error": "会话启动失败"}
        return 200, {
            "ok": True,
            "conversation_id": cid,
            "run_id": started,
            "queued": False,
        }

    def queue(self, cid: str) -> Tuple[int, Dict[str, Any]]:
        cid = str(cid or "").strip()
        if not cid or not is_valid_conversation_id(cid):
            return 400, {"ok": False, "error": "invalid conversation_id"}
        return 200, self.app.conversation_queue.list(cid)

    def queue_insert(self, cid: str, item_id: str) -> Tuple[int, Dict[str, Any]]:
        cid = str(cid or "").strip()
        if not cid or not is_valid_conversation_id(cid):
            return 400, {"ok": False, "error": "invalid conversation_id"}
        try:
            item = self.app.conversation_queue.set_insert(cid, item_id)
            if not self.app.mesh.is_running(cid):
                claimed = self.app.conversation_queue.claim_item(cid, item_id)
                if claimed is not None:
                    sender = claimed.get("sender") if isinstance(claimed.get("sender"), dict) else None
                    payload: Dict[str, Any] = {
                        "content": str(claimed.get("content") or ""),
                        "attachments": claimed.get("attachments") or None,
                    }
                    if sender:
                        payload["_sender"] = sender.get("cid")
                        payload["_sender_name"] = sender.get("name")
                    started = self.app.runner.start(cid, payload)
                    if not started:
                        self.app.conversation_queue.release(cid, item_id)
                        return 503, {"ok": False, "error": "会话启动失败"}
                    self.app.conversation_queue.complete(cid, item_id)
                    return 200, {"ok": True, "run_id": started,
                                 "revision": self.app.conversation_queue.revision(cid)}
        except QueueError as exc:
            return 409, {"ok": False, "error": str(exc)}
        return 200, {"ok": True, "item": item,
                     "revision": self.app.conversation_queue.revision(cid)}

    def queue_recall(self, cid: str, item_id: str) -> Tuple[int, Dict[str, Any]]:
        cid = str(cid or "").strip()
        if not cid or not is_valid_conversation_id(cid):
            return 400, {"ok": False, "error": "invalid conversation_id"}
        try:
            item = self.app.conversation_queue.recall(cid, item_id)
        except QueueError as exc:
            return 409, {"ok": False, "error": str(exc)}
        return 200, {"ok": True, "draft_queue_id": item["id"], "item": item,
                     "revision": self.app.conversation_queue.revision(cid)}

    def queue_cancel(self, cid: str, item_id: str) -> Tuple[int, Dict[str, Any]]:
        cid = str(cid or "").strip()
        if not cid or not is_valid_conversation_id(cid):
            return 400, {"ok": False, "error": "invalid conversation_id"}
        try:
            self.app.conversation_queue.cancel(cid, item_id)
        except QueueError as exc:
            return 409, {"ok": False, "error": str(exc)}
        return 200, {"ok": True, "revision": self.app.conversation_queue.revision(cid)}

    def confirm(self, cid: str, confirm_id: str) -> Tuple[int, Dict[str, Any]]:
        """确认一个写盘预览：按 cid 解析会话门控，不落默认桶。"""
        cid = str(cid or "").strip()
        confirm_id = str(confirm_id or "").strip()
        if not cid:
            return 400, {"error": "missing conversation_id"}
        if not confirm_id:
            return 400, {"error": "missing confirm_id"}
        gate = self.app.gate_for(cid)
        ok = bool(gate.confirm(confirm_id))
        if not ok:
            return 404, {
                "confirmed": False,
                "error": "confirm_id 无效、已消耗或不属于该会话",
            }
        return 200, {"confirmed": True, "conversation_id": cid, "confirm_id": confirm_id}

    def stop(self, cid: str) -> Tuple[int, Dict[str, Any]]:
        """请求停止当前回合（协作式取消）。

        经 `SessionRunner.request_cancel` 置位取消信号 → 内核在检查点（流式每帧 /
        工具执行前 / 步结算前）停止本轮，不再产生半成品落盘。这里不直接调
        `mesh.abort_run`：占位须由运行线程自己释放，否则忙闲事实源与实际线程不一致。
        """
        cid = str(cid or "").strip()
        if not cid:
            return 400, {"error": "missing conversation_id"}
        run_id = self.active_run(cid)
        runner = self.app.runner
        requested = bool(runner.request_cancel(cid)) if runner is not None else False
        return 200, {
            "stop_requested": requested,
            "conversation_id": cid,
            "run_id": run_id,
        }
