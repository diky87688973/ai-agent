"""Web 并发与异步停止验收：真实 HTTP、操作标识与清理终态。"""
from __future__ import annotations

import time
from typing import Any


def run(acc: Any) -> None:
    print("\n场景④ 并发与停止")
    cid = "accept-conc-01"
    acc.app.mesh.try_begin_run(cid)
    status, payload = acc.post("/api/chat/send", {"message": "再来", "conversation_id": cid})
    acc.check("同会话并发 send → 入队", status == 200 and bool(payload.get("queued")), f"{status} {payload}")
    queue = acc.app.conversation_queue.list(cid)
    acc.check("并发消息进入待发送队列", len(queue.get("items") or []) == 1, str(queue))
    for item in queue.get("items") or []:
        acc.app.conversation_queue.cancel(cid, item["id"])
    acc.app.mesh.end_run(cid)

    status, payload = acc.post("/api/chat/stop", {"conversation_id": cid})
    stop_id = str(payload.get("stop_id") or "")
    acc.check("stop 返回受理状态及操作标识",
               status in (200, 202) and payload.get("stop_requested") is True and bool(stop_id)
               and payload.get("conversation_id") == cid,
               f"{status} {payload}")
    deadline = time.monotonic() + 5
    while status == 202 and stop_id and time.monotonic() < deadline:
        time.sleep(0.02)
        status, payload = acc.post("/api/chat/stop", {
            "conversation_id": cid, "stop_id": stop_id})
    acc.check("stop 清理终态成功且操作标识不变",
               status == 200 and payload.get("state") == "completed"
               and payload.get("stop_id") == stop_id,
               f"{status} {payload}")

    started = acc.app.runner.start("accept-conc-02", {"content": "跑"})
    requested = acc.app.runner.request_cancel("accept-conc-02")
    acc.app.runner.wait_idle("accept-conc-02", timeout=25)
    acc.check("停止检查可置位并释放占位", bool(started) and requested and not acc.app.mesh.is_running("accept-conc-02"))

    status, payload = acc.post("/api/chat/send", {"message": "  "})
    acc.check("空消息 400", status == 400, str(payload))
    status, payload = acc.post(
        "/api/chat/send", {"message": "hi", "conversation_id": "../escape"}
    )
    acc.check("非法会话 id 400", status == 400, str(payload))

