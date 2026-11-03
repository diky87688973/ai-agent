# -*- coding: utf-8 -*-
"""经典 UI 会话日期分组。"""
from __future__ import annotations

from typing import Optional

from agent.shell.timefmt import date_group


def session_date_group(mtime: float, now: Optional[float] = None) -> str:
    """修改时间 → 中文日期分组（口径直接取 `agent.shell.timefmt`，避免两处漂移）。"""
    return date_group(mtime, now)


# ── 内存态：经典界面需要、但内核不持有的三样东西 ─────────────────
