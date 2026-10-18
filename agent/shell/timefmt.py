# -*- coding: utf-8 -*-
"""时间显示口径（壳层共享的纯函数）。

会话菜单按"自然日"分组，Web 壳与经典适配层**必须**用同一份实现：
两处各写一份时，跨年/夏令时/时区差异会让同一个会话在两个界面里落在不同分组。
本模块不依赖任何其它壳层模块，谁都可以向下依赖它。
"""
from __future__ import annotations

import time


def date_group(mtime: float, now: float | None = None) -> str:
    """把修改时间归入中文日期分组。

    分组：今天 / 昨天 / `xx月xx日`（按自然日比较，不按 24 小时）。
    非法/溢出时间戳无法归组，返回空串由调用方决定显示方式。
    """
    if not mtime:
        return ""
    reference = time.time() if now is None else now
    try:
        stamp = time.localtime(mtime)
        today = time.localtime(reference)
    except (OverflowError, OSError, ValueError):
        # 非法/溢出时间戳：无法归组，交给调用方显示空分组
        return ""
    day = (stamp.tm_year, stamp.tm_yday)
    today_day = (today.tm_year, today.tm_yday)
    if day == today_day:
        return "今天"
    # 昨天：把参考时间倒退一天比较（跨年由 tm_year 一起比对）
    yesterday = time.localtime(reference - 86400)
    if day == (yesterday.tm_year, yesterday.tm_yday):
        return "昨天"
    # 更早的按具体日期分组：「本周」「更早」看不出是哪天。
    return f"{stamp.tm_mon}月{stamp.tm_mday}日"
