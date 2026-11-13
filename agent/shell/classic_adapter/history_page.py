# -*- coding: utf-8 -*-
"""会话历史分页：轮次折叠、字符成本与页选择。

纯函数层：只依赖 `history_items` 的事实折叠，不读存储、不碰 HTTP、不写状态。
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from agent.shell.classic_adapter.contract import turn_status
from agent.shell.classic_adapter.history import history_items

HISTORY_PAGE_CHARS = 10_000


@dataclass(frozen=True)
class Round:
    """由宿主回合开始事实界定的一段历史。"""

    anchor: int | None
    items: Tuple[Dict[str, Any], ...]
    attachments: Tuple[Dict[str, Any], ...]
    chars: int


@dataclass(frozen=True)
class Page:
    """一页连续完整轮次。集合字段不可变，元素在返回前已深拷贝。"""

    items: Tuple[Dict[str, Any], ...]
    attachments: Tuple[Dict[str, Any], ...]
    start: int
    end: int
    chars: int
    has_more: bool
    next_before: int | None


def item_cost(item: Dict[str, Any]) -> int:
    """item 的界面文本量下界；图片只计公开元数据。"""
    if not isinstance(item, dict):
        return 0
    role = str(item.get("role") or "")
    total = 0
    if role == "tool":
        total += len(str(item.get("script") or ""))
        args = item.get("args")
        if args:
            total += len(json.dumps(args, ensure_ascii=False, separators=(",", ":")))
        for key in ("preview", "error"):
            total += len(str(item.get(key) or ""))
        images = item.get("images")
        if isinstance(images, list):
            total += len(json.dumps(images, ensure_ascii=False, separators=(",", ":")))
        return total
    total += len(str(item.get("content") or ""))
    attachments = item.get("attachments")
    if isinstance(attachments, list):
        for att in attachments:
            if isinstance(att, dict):
                total += len(str(att.get("name") or ""))
    return total


def _seq(event: Any) -> int | None:
    data = getattr(event, "data", None)
    value = data.get("_seq") if isinstance(data, dict) else None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _copy_items(items: Iterable[Dict[str, Any]]) -> Tuple[Dict[str, Any], ...]:
    return tuple(copy.deepcopy(item) for item in items)


def fold_rounds(events: Sequence[Any], *, partial: bool = False) -> List[Round]:
    """从宿主边界投影轮次，旧历史前缀按用户消息分页。"""
    rounds: List[Round] = []
    current: List[Any] = []

    def flush() -> None:
        if not current:
            return
        kind = getattr(current[0], "type", "")
        anchor = _seq(current[0]) if kind in ("turn_started", "input_claimed") else None
        items, attachments = history_items(current)
        if kind == "turn_started" and anchor is not None:
            end = next((event for event in reversed(current) if event.type == "turn_ended"), None)
            if end is None:
                status = "partial" if partial else "running"
            else:
                status = turn_status(end.data or {})
            final = next((item for item in reversed(items)
                          if item["role"] in ("assistant", "tool")), None)
            if final and final["role"] == "assistant" and status != "partial" and not final.get("tool_phase"):
                final["final_reply"] = True
            for item in items:
                item.update(turn_key=anchor, turn_status=status)
                if end is not None and end.data.get("elapsed_ms") is not None:
                    item["turn_elapsed_ms"] = end.data["elapsed_ms"]
        rounds.append(Round(
            anchor=anchor,
            items=_copy_items(items),
            attachments=tuple(copy.deepcopy(attachments)),
            chars=sum(item_cost(item) for item in items),
        ))

    explicit = False
    for event in events:
        kind = str(getattr(event, "type", ""))
        if current and (kind == "turn_started" or (not explicit and kind == "input_claimed")):
            flush()
            current = []
        explicit = explicit or kind == "turn_started"
        current.append(event)
    flush()
    return rounds


def _flatten(rounds: Sequence[Round]) -> Tuple[Dict[str, Any], ...]:
    return tuple(copy.deepcopy(item) for rnd in rounds for item in rnd.items)


def _attachments(rounds: Sequence[Round]) -> Tuple[Dict[str, Any], ...]:
    return tuple(copy.deepcopy(att) for rnd in rounds for att in rnd.attachments)


def select_page(rounds: Sequence[Round], *, before: int | None,
                budget: int = HISTORY_PAGE_CHARS) -> Page:
    """从新到旧选一页；`before` 是排他的轮 ID 边界。"""
    end = len(rounds)
    if before is not None:
        for index, rnd in enumerate(rounds):
            if rnd.anchor is not None and rnd.anchor >= before:
                end = index
                break

    start = end
    chars = 0
    while start > 0:
        start -= 1
        chars += rounds[start].chars
        if chars >= budget:
            break

    page = rounds[start:end]
    has_more = start > 0
    return Page(
        items=_flatten(page),
        attachments=_attachments(page),
        start=start,
        end=end,
        chars=chars,
        has_more=has_more,
        next_before=rounds[start].anchor if has_more else None,
    )
