# -*- coding: utf-8 -*-
"""会话日志的行编解码：短键、存储坐标与事件对象的互转。

行格式是持久化契约：`{"t": <事件类型>, "d": <载荷>, "s": <全局存储坐标>}`，
`s` 可缺省。`_seq` 在事件产出时由 `emit` 标进载荷，落盘时提到顶层 `s`
并从载荷删除，每行只留一份；`conversation_id` 由文件名承载，读回时按会话补进载荷。
"""
from __future__ import annotations

import json
from typing import Any, Optional

from agent.core.events import Event

#: 落盘行的键名。会话日志里绝大多数行是流式增量，payload 只有几个字，
#: 键名按行数放大 —— 缩短键名是这一层最直接的省法。
#:
#: `s` 是全局存储坐标，不能省：SSE 的 `id:` 行用它，浏览器断线重连时经
#: `Last-Event-ID` 带回来，服务端据此从该位置续传（见 `cursor_of` / `replay_after`）。
#: 它跨会话共享、从不重置，所以与行号差一个常数；也不保证连续 ——
#: 事件在产出瞬间就拿号（那时还不知道会不会落盘），跳过的号不再补。
#: 游标只要求单调唯一，不要求连续。
# 落盘行短键：壳层读标题/历史也要同一份，故公开（禁止跨层 import 私有名）。
KEY_TYPE = "t"
KEY_DATA = "d"
KEY_SEQ = "s"

#: 落盘时不写的载荷字段：都能从别处还原，写了只增加每行体积。
#:
#: - `conversation_id`：文件名就是会话 ID。读盘的人（`load_with_seq` 的调用方、
#:   `tail_across`）手上已经有 `path.stem`，每行再存 36 字节纯属重复。
#:   内核事件在内存里仍带它（`emit` 注入，SSE 靠它分派到正确的会话页面），
#:   只有落盘这一份省掉；读回时由 `event_from_obj` 按会话补上。
#: - `_seq`：全局存储坐标，落盘时写成顶层 `s`（每行只留一份）。
DERIVED_KEYS = ("conversation_id", "_seq")


def valid_seq(raw: Any) -> bool:
    """`raw` 是否是可用的非负整数（排除 bool——它是 int 的子类）。"""
    return isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0


def seq_from_obj(obj: Any) -> Optional[int]:
    """从落盘对象取存储坐标：顶层 `s`；缺失或不是非负整数则返回 None。"""
    if not isinstance(obj, dict):
        return None
    raw = obj.get(KEY_SEQ)
    return raw if valid_seq(raw) else None


def event_seq(event: Any) -> Optional[int]:
    """事件载荷里的存储坐标 `_seq`；缺失或不是非负整数返回 None。"""
    data = getattr(event, "data", None)
    if isinstance(data, dict) and valid_seq(data.get("_seq")):
        return int(data["_seq"])
    return None


def event_to_json(event: Event) -> str:
    """事件 → 单行 JSON（data 以 default=str 兜底不可序列化值）。

    存储坐标 `_seq` 已在事件产出的那一刻由 `emit` 标进载荷（见 `core/ports.py`
    里的说明：事件一产出就被发布到总线，落盘在其后，所以坐标不能在落盘时才标）。
    这里把它提到顶层 `s`，并从 data 里删掉 —— 每行只留一份。

    `conversation_id` 同样从落盘内容里删掉：文件名已经是会话 ID（见 `DERIVED_KEYS`）。
    """
    data = dict(event.data) if isinstance(event.data, dict) else {}
    seq = data.get("_seq")
    payload: dict[str, Any] = {KEY_TYPE: event.type, KEY_DATA: data}
    if valid_seq(seq):
        payload[KEY_SEQ] = seq
    for key in DERIVED_KEYS:
        data.pop(key, None)
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def event_from_obj(obj: Any, conversation_id: str = "") -> Optional[Event]:
    """JSON 对象 → 事件；非对象或缺 `t` 返回 None。

    落盘行用的是短键（`t` / `d` / `s`，见 `KEY_*`）。`conversation_id` 不在落盘
    内容里（见 `DERIVED_KEYS`），由调用方按文件名传进来补回 data ——
    内核事件在内存里一律带它，续传翻译与 SSE 分派都依赖这一点。
    """
    if not isinstance(obj, dict):
        return None
    type_ = str(obj.get(KEY_TYPE) or "").strip()
    if not type_:
        return None
    data = obj.get(KEY_DATA)
    payload = dict(data) if isinstance(data, dict) else {}
    seq = seq_from_obj(obj)
    if seq is not None:
        payload["_seq"] = seq
    if conversation_id:
        payload.setdefault("conversation_id", conversation_id)
    return Event(type=type_, data=payload)
