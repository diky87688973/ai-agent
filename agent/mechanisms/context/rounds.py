# -*- coding: utf-8 -*-
"""上下文轮次与工具链边界。"""
from __future__ import annotations

import copy
from typing import Any, Callable, Dict, List, Optional, Tuple


class Round:
    """一轮对话：一条 user 起至下一 user 前（消息为 OpenAI dict）。"""

    __slots__ = ("messages", "round_id")

    def __init__(self, round_id: Optional[str] = None) -> None:
        self.messages: List[Dict[str, Any]] = []
        self.round_id = round_id

    def append_message_dict(self, msg: Dict[str, Any]) -> None:
        self.messages.append(msg)

    def append(self, role: str, content: str, **extra: Any) -> None:
        m: Dict[str, Any] = {"role": role, "content": content}
        m.update(extra)
        self.messages.append(m)

    def calculate_tokens(self, approx_msg_fn: Callable[[Dict[str, Any]], int]) -> int:
        return sum(int(approx_msg_fn(m)) for m in self.messages)


class ContextChunk:
    """命名块；rounds 顺序 = 展平时该块内顺序。"""

    __slots__ = ("name", "rounds")

    def __init__(self, name: str) -> None:
        self.name = name
        self.rounds: List[Round] = []

    def append(self, role: str, content: str, is_new_msg: bool, **extra: Any) -> None:
        """is_new_msg 或空块 → 新开轮，否则追加至当前轮。"""
        if is_new_msg or not self.rounds:
            self.rounds.append(Round())
        self.rounds[-1].append(role, content, **extra)

    def get_count(self) -> int:
        return len(self.rounds)

    def calculate_tokens(self, approx_msg_fn: Callable[[Dict[str, Any]], int]) -> int:
        return sum(r.calculate_tokens(approx_msg_fn) for r in self.rounds)


#: 推理正文被截断时插在中间的话。写明省了多少，模型据此知道"这里原本有内容"。
REASONING_OMIT_FMT = "…<此处省略约 {tokens} token 的推理>…"




def flat_messages_to_user_rounds(msgs: List[Dict[str, Any]]) -> List[Round]:
    """扁平消息按 user 起轮切分为 Round 列表。"""
    rounds: List[Round] = []
    i = 0
    n = len(msgs)
    while i < n:
        if msgs[i].get("role") != "user":
            i += 1
            continue
        r = Round()
        rid = str(msgs[i].get("_agent_round_id") or "").strip() or None
        if rid:
            r.round_id = rid
        while i < n:
            r.append_message_dict(msgs[i])
            i += 1
            if i < n and msgs[i].get("role") == "user":
                break
        rounds.append(r)
    return rounds


def copy_round_list(src: List[Round], start: int, count: int) -> List[Round]:
    """深拷贝切段。"""
    out: List[Round] = []
    end = min(len(src), start + max(0, count))
    for j in range(start, end):
        nr = Round(round_id=src[j].round_id)
        for m in src[j].messages:
            nr.messages.append(copy.deepcopy(m))
        out.append(nr)
    return out


def find_first_user_index(messages: List[Dict[str, Any]]) -> Optional[int]:
    """首个 user 消息下标。"""
    for i, m in enumerate(messages):
        if m.get("role") == "user":
            return i
    return None


def user_turn_starts(messages: List[Dict[str, Any]]) -> List[int]:
    """每个用户轮的起始下标（一条 user 起到下一条 user 前，为原子单位）。

    轮的边界只认 `user`：一条 user 之后的所有 `assistant` / `tool` 都属于这一回合 ——
    工具往返、悬空调用、多段回复都算轮内。压缩只允许整轮处理。
    """
    return [i for i, m in enumerate(messages or [])
            if isinstance(m, dict) and str(m.get("role") or "") == "user"]


def turn_boundary_floor(messages: List[Dict[str, Any]], index: int) -> int:
    """把下标向下取整到最近的用户轮起始位置。

    不是轮边界时向前退到本回合的起点（宁可少压，也不从轮中间切开）::

        [user0][A][tool][A]  [user1][A]  [user2][A]
                        ↑ index=4（轮内）→ 取整到 3（user1 的位置）

    前面一条 user 都没有 → 返回 0。
    """
    idx = max(0, int(index))
    best = 0
    for s in user_turn_starts(messages):
        if s <= idx:
            best = s
        else:
            break
    return best


def is_turn_boundary(messages: List[Dict[str, Any]], index: int) -> bool:
    """下标是否正好落在某个用户轮起始处（`len` 也算：末尾之后是合法边界）。"""
    idx = int(index)
    if idx == len(messages or []):
        return True
    return idx in set(user_turn_starts(messages))


def turn_spans(messages: List[Dict[str, Any]]) -> List[Tuple[int, int]]:
    """每个用户轮的半开区间 `[start, end)` 列表（按顺序）。"""
    starts = user_turn_starts(messages)
    n = len(messages or [])
    out: List[Tuple[int, int]] = []
    for j, s in enumerate(starts):
        e = starts[j + 1] if j + 1 < len(starts) else n
        out.append((s, e))
    return out


def tool_chain_balanced(messages: List[Dict[str, Any]], start: int, end: int) -> bool:
    """区间 `[start, end)` 内工具链是否闭合。

    闭合 = 每条 `assistant.tool_calls` 的结果都在区间内，且没有孤立 `tool`
    （发起它的 assistant 落在区间外）。模型 API 对不闭合是硬拒绝。
    """
    pending: List[str] = []
    for m in (messages or [])[max(0, start):max(0, end)]:
        if not isinstance(m, dict):
            continue
        for tc in (m.get("tool_calls") or []):
            pending.append(str((tc or {}).get("id") or ""))
        tid = m.get("tool_call_id")
        if tid is not None:
            key = str(tid)
            if key not in pending:
                return False
            pending.remove(key)
    return not pending
