# -*- coding: utf-8 -*-
"""经典 UI 会话标题与日期分组。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from agent.mechanisms.session_store import KEY_DATA, KEY_TYPE
from agent.shell.timefmt import date_group


def _scan_title(path: Path) -> str:
    """回落实现：从 .raw 前若干行找首条用户输入派生标题。

    只读文件前 400 行——一个会话可能有上万条事件，为标题读全文件不值得。
    行的键名取自 store 的 `KEY_TYPE` / `KEY_DATA`：硬编码字符串会随键名改动静默失配，
    硬编码字符串就会静默失配，标题悄悄退化成空。
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for _ in range(400):
                line = handle.readline()
                if not line:
                    break
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                if payload.get(KEY_TYPE) != "input_claimed":
                    continue
                data = payload.get(KEY_DATA) if isinstance(payload.get(KEY_DATA), dict) else payload
                content = str(data.get("content") or "").strip()
                if content:
                    return " ".join(content.split())[:40]
    except OSError:
        pass
    return ""




def _date_group(mtime: float, now: Optional[float] = None) -> str:
    """修改时间 → 中文日期分组（口径直接取 `agent.shell.timefmt`，避免两处漂移）。"""
    return date_group(mtime, now)


# ── 内存态：经典界面需要、但内核不持有的三样东西 ─────────────────
