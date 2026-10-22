# -*- coding: utf-8 -*-
"""会话运行态心跳。"""
from __future__ import annotations

import threading
from typing import Any


def heartbeat_until(*, mesh: Any, cid: str, stop: threading.Event,
                    interval: float) -> None:
    """按固定间隔续运行态，直到 stop。失败不阻断回合。"""
    while not stop.wait(interval):
        try:
            mesh.touch_run(cid)
        except Exception:
            # 心跳失败不影响回合；登记表会按 TTL 退化，不阻断执行。
            pass
