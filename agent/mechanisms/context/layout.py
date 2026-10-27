# -*- coding: utf-8 -*-
"""上下文 token 裁剪、分段布局与压缩区间。"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from agent.mechanisms.context.constants import SEGMENT_LABELS
from agent.mechanisms.context.rounds import tool_chain_balanced, turn_spans
from agent.mechanisms.context.tokens import approx_tokens_text, default_message_tokens

REASONING_OMIT_FMT = "…<此处省略约 {tokens} token 的推理>…"

def clip_reasoning_text(text: str, budget_tokens: int) -> str:
    """按 token 预算截断一段推理正文：取两头，中间删掉。

    - `budget_tokens < 0`：全量保留（原样返回）
    - `budget_tokens == 0`：整段丢弃（返回空串）
    - 否则若超出预算，保留开头与结尾各约一半，中间以省略标记代替。

    取两头而不是只留尾部：推理的开头是"我要干什么"、结尾是"结论是什么"，
    中间的过程模型能按这两头补出来。
    """
    s = str(text or "")
    if not s or budget_tokens < 0:
        return s
    if budget_tokens == 0:
        return ""
    if approx_tokens_text(s) <= budget_tokens:
        return s
    # 省略标记本身也占预算，先把它扣掉
    marker = REASONING_OMIT_FMT.format(tokens=budget_tokens)
    head_budget = max(1, budget_tokens // 2)
    tail_budget = max(1, budget_tokens - head_budget)
    head = _prefix_within_budget(s, head_budget)
    tail = _suffix_within_budget(s, tail_budget)
    if not head and not tail:
        return marker
    omitted = max(0, approx_tokens_text(s) - approx_tokens_text(head)
                  - approx_tokens_text(tail))
    return head + REASONING_OMIT_FMT.format(tokens=omitted) + tail


def _prefix_within_budget(text: str, budget_tokens: int) -> str:
    """取开头这一段，使其估算不超过预算（二分找最大长度）。"""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if approx_tokens_text(text[:mid]) <= budget_tokens:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo]


def _suffix_within_budget(text: str, budget_tokens: int) -> str:
    """取结尾这一段，使其估算不超过预算（二分找最长后缀）。"""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if approx_tokens_text(text[len(text) - mid:]) <= budget_tokens:
            lo = mid
        else:
            hi = mid - 1
    return text[len(text) - lo:] if lo else ""


def clip_reasoning(messages: List[Dict[str, Any]],
                   budget_tokens: int) -> List[Dict[str, Any]]:
    """按预算裁掉消息里的思维链（不改原列表、不改原消息）。

    思维链是模型的中间稿：整段回传就是让每次请求多背一大段必然未命中缓存的内容。
    按预算裁到两头保留，既省掉大部分钱，
    又让模型看得到"上一回合打算干什么、得出了什么"。

    统计口径（分段 token、预算估算）用的也是这一份 —— 两处不一致时，
    界面会把窗口算满、压缩也会提前或滞后触发。
    """
    out: List[Dict[str, Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            out.append(msg)
            continue
        if "reasoning_content" not in msg and "reasoning" not in msg:
            out.append(msg)
            continue
        clean = dict(msg)
        source = clean.pop("reasoning_content", None)
        if source is None:
            source = clean.pop("reasoning", None)
        clipped = clip_reasoning_text(str(source or ""), budget_tokens)
        if clipped:
            clean["reasoning_content"] = clipped
        out.append(clean)
    return out


def as_text_parts(text: Any) -> List[str]:
    """把可能为列表/字符串的注入内容归一成"每段一条"的正文列表。

    注入源（知识库 / Skills）常按条目给列表；直接塞进 `content` 会让模型收到
    Python 字面量。这里逐条转字符串并去掉空串。
    """
    if isinstance(text, (list, tuple)):
        items = list(text)
    else:
        items = [text]
    out: List[str] = []
    for it in items:
        t = str(it or "").strip()
        if t:
            out.append(t)
    return out


def merge_segment_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按 key+label 合并同一个插件的多条消息；tokens 相加，count 取首条自报数。"""
    merged: List[Dict[str, Any]] = []
    index: Dict[Tuple[str, str], int] = {}
    for row in rows:
        group = (str(row.get("key") or ""), str(row.get("label") or ""))
        pos = index.get(group)
        if pos is None:
            index[group] = len(merged)
            merged.append(dict(row))
            continue
        merged[pos]["tokens"] = int(merged[pos].get("tokens") or 0) + int(row.get("tokens") or 0)
    return merged


def _partition_head(messages: List[Dict[str, Any]],
                    head: Optional[List[Dict[str, Any]]],
                    system_text: str):
    if head is not None:
        head_msgs = [m for m in head if isinstance(m, dict)]
        body = messages
    else:
        cut = next((i for i, m in enumerate(messages)
                    if str(m.get("role") or "") == "user"), len(messages))
        head_msgs, body = messages[:cut], messages[cut:]
    prompt = str(system_text or "").strip()
    rest_head = list(head_msgs)
    if prompt:
        if rest_head and str(rest_head[0].get("content") or "").strip() == prompt:
            rest_head = rest_head[1:]
    elif rest_head:
        rest_head = rest_head[1:]
    return prompt, head_msgs, rest_head, body


def _partition_plugins(rest_head: List[Dict[str, Any]],
                       plan: List[Tuple[str, str, int]]):
    plugin: List[List[Dict[str, Any]]] = []
    msg_i = 0
    for seg in plan:
        seg_count = int(seg[2]) if len(seg) > 2 else 0
        if seg_count > 0 and msg_i < len(rest_head):
            plugin.append([rest_head[msg_i]])
            msg_i += 1
        else:
            plugin.append([])
    summary = [m for m in rest_head[msg_i:]]
    return plugin, summary


def _split_mode(body: List[Dict[str, Any]]):
    mode: List[Dict[str, Any]] = []
    for m in reversed(body):
        if str(m.get("role") or "") == "system" \
                and str(m.get("content") or "").startswith("## 当前模式"):
            mode = [m]
            break
    return mode, [m for m in body if m not in mode]


def _layout_rows(prompt: str, head_msgs: List[Dict[str, Any]],
                 plan: List[Tuple[str, str, int]], plugin: List[List[Dict[str, Any]]],
                 summary: List[Dict[str, Any]], dialogue: List[Dict[str, Any]],
                 mode: List[Dict[str, Any]], counter: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    def add(key: str, items: List[Dict[str, Any]], tokens: Optional[int] = None,
            count: Optional[int] = None, label: str = "") -> None:
        rows.append({
            "key": key, "label": label or SEGMENT_LABELS.get(key, key),
            "tokens": int(tokens) if tokens is not None
            else sum(int(counter(m)) for m in items),
            "count": len(items) if count is None else int(count)})

    if prompt:
        add("system", [], int(counter({"role": "system", "content": prompt})), count=1)
    elif head_msgs:
        add("system", head_msgs[:1])
    for i, seg in enumerate(plan):
        seg_key, seg_label = str(seg[0]), str(seg[1])
        seg_count = int(seg[2]) if len(seg) > 2 else len(plugin[i])
        add(f"plugin:{seg_key}", plugin[i], count=seg_count, label=seg_label)
    add("summary", summary)
    add("full_recent", dialogue,
        count=sum(1 for m in dialogue if str(m.get("role") or "") == "user"))
    if mode:
        add("mode", mode)
    return rows


def layout_from_messages(
    messages: List[Dict[str, Any]],
    *,
    system_text: str = "",
    head: Optional[List[Dict[str, Any]]] = None,
    plugin_segments: Optional[List[Tuple[str, str, int]]] = None,
    budget_tokens: int = 0,
    model_max_context_tokens: int = 0,
    token_fn: Optional[Callable[[Dict[str, Any]], int]] = None,
) -> Dict[str, Any]:
    """把请求的头部 + 对话切开分段并统计 token（观察面用）。"""
    counter = token_fn or default_message_tokens
    msgs = [m for m in (messages or []) if isinstance(m, dict)]
    budget_in = max(int(budget_tokens or 0), 1)
    if not msgs and not head:
        return {"segments": [], "total_tokens": 0, "budget_tokens": budget_in,
                "model_max_context_tokens": int(model_max_context_tokens or 0)}
    prompt, head_msgs, rest_head, body = _partition_head(msgs, head, system_text)
    plan = list(plugin_segments or [])
    plugin, summary = _partition_plugins(rest_head, plan)
    mode, dialogue = _split_mode(body)
    rows = _layout_rows(prompt, head_msgs, plan, plugin, summary, dialogue, mode, counter)
    total = sum(int(r["tokens"]) for r in rows)
    budget = max(int(budget_tokens or 0), total, 1)
    segments = [{**row, "pct": round(100.0 * row["tokens"] / budget, 6)}
                for row in rows]
    segments.append({
        "key": "remaining", "label": "剩余容量",
        "tokens": max(0, budget - total),
        "pct": round(100.0 * max(0, budget - total) / budget, 6)})
    return {
        "segments": segments, "total_tokens": total, "budget_tokens": budget,
        "model_max_context_tokens": int(model_max_context_tokens or 0),
    }

def excerpt_by_target_tokens(
    messages: List[Dict[str, Any]],
    keep_turns: int,
    token_fn: Optional[Callable[[Dict[str, Any]], int]] = None,
) -> Optional[Tuple[int, int]]:
    """要压缩掉的区间 `[0, end)`：遮盖末尾 `keep_turns` 轮，压它前面的。

    遮盖是偏好（正常情况）：

    - 末尾 `keep_turns` 个用户轮不压 —— 那是模型的近场，手里的活全在那里；
    - 压缩区域只能是「最后一个前置 system 之后 → 遮盖起点之前」那一段。
      系统提示词 / Skills / 知识库 / 记忆摘要都是 `system`，位置在对话之前，
      所以这个区域天然只覆盖对话，不含任何系统设定。

    压不动就连近场一起压（这一条亘古不变）：遮盖前面没有可压的轮
    （例如总共只剩 1 轮、或遮盖已经盖住全部）时，连遮盖一起压掉 ——
    极端情况压缩后整个上下文 0 个用户轮，摘要接管全部历史，
    剩下的只有头部（系统提示 / 知识库 / 摘要）。
    遮盖是偏好，不是拒绝压缩的理由：压不动就是请求超上限直接失败。

    两者都没有（对话一条都没有）→ `None`。
    返回的 `end` 只会落在用户轮边界或工具链闭合处。
    """
    msgs = list(messages or [])
    spans = turn_spans(msgs)
    if not spans:
        return None
    keep = max(0, int(keep_turns))
    start = len(spans) - keep
    cut = 0
    if 0 < start < len(spans):
        # 正常路径：压遮盖前面那一段（`spans[0][0]` 恒为 0，落点即遮盖起点）。
        cut = spans[start][0]
    if cut <= 0:
        # 遮盖前面没有可压的轮 → 连遮盖一起压（压到末尾）。
        cut = len(msgs)
    # 落点不能切在悬空工具链上：往前收到工具链闭合为止。
    while cut > 0 and not tool_chain_balanced(msgs, 0, cut):
        cut -= 1
    if cut <= 0:
        return None
    return 0, cut
def adjust_excerpt_range_half_open(
    messages: List[Dict[str, Any]], start: int, end: int
) -> Tuple[int, int]:
    """半开区间 [start, end) 外扩以覆盖完整 tool 链。

    起点落在 tool 上 → 回扩至发起该链的 assistant；区间内含 tool_calls 的 assistant
    若其结果未闭合 → end 外扩至链尾；返回 [start, min(end, n))。
    """
    n = len(messages)
    start = max(0, min(start, n))
    end = max(start, min(end, n))
    if start >= end:
        return start, end
    if start < n and messages[start].get("role") == "tool":
        t = start
        while t > 0 and messages[t - 1].get("role") == "tool":
            t -= 1
        if t > 0:
            prev = messages[t - 1]
            if prev.get("role") == "assistant" and prev.get("tool_calls"):
                start = t - 1
    i = start
    while i < end:
        m = messages[i]
        if m.get("role") == "assistant" and m.get("tool_calls"):
            tc_list = m.get("tool_calls") or []
            need_ids = {
                str((tc or {}).get("id") or "")
                for tc in tc_list
                if isinstance(tc, dict) and (tc or {}).get("id")
            }
            need_ids.discard("")
            if not need_ids:
                i += 1
                continue
            j = i + 1
            while j < n and messages[j].get("role") == "tool":
                j += 1
            if j > end:
                end = min(j, n)
        i += 1
    return start, min(end, n)
