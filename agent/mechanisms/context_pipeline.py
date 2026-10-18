# -*- coding: utf-8 -*-
"""上下文管线：分块上下文、三段装配与摘要调度。

- 数据模型：六块（系统提示词 / 插件段落 / 记忆文件 / 近期记忆 /
  模式）+ Round（user 起轮）+ ContextChunk（命名块含轮）；
- 装配走三段拼接：头部（系统提示词 / 插件各段 / 记忆摘要）+ 对话 +
  尾部（本轮新输入 / 工具结果 / 模式），见 `assembles()`；
- 区块来源：系统提示词与摘要由会话注入，插件各段经 `ContextSources`
  注入源刷新，对话来自事实日志；
- 摘要调度：遮盖取段 / 工具链完整性外扩 / 素材切轮；
- 估算与统计：总量 / 分块 / 分段快照。

摘要生成（调用模型产出摘要文本）不在本模块范围（属压缩策略执行侧）。
token 估算见 `agent.mechanisms.context_tokens`（本模块再导出以保持旧导入可用）。
"""
from __future__ import annotations

import copy
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from agent.core.error_report import report_error
from agent.mechanisms.context_tokens import (  # noqa: F401 — 再导出供旧导入路径
    IMAGE_TOKENS_PER_IMAGE,
    approx_tokens_text,
    default_message_tokens,
)

CHUNK_SYSTEM = "系统提示词"
CHUNK_PLUGIN = "插件段落"
CHUNK_MEM = "记忆文件"
CHUNK_FULL = "近期记忆"
CHUNK_MODE = "模式"
CHUNK_ORDER = (CHUNK_SYSTEM, CHUNK_PLUGIN, CHUNK_MEM, CHUNK_FULL, CHUNK_MODE)

DEFAULT_FULL_USER_ROUNDS = 1
#: 思维链回传预算默认值（token）：超出取两头、中间以省略标记代替。
DEFAULT_REASONING_REPLAY_TOKENS = 8000

DEFAULT_SUMMARY_TOKEN_THRESHOLD = 700000
#: 最近这么多用户轮保留完整工具往返；更早的轮剥掉轮内工具往返。
#: 压缩时保留的最近用户轮数（0 = 允许压到 0 个用户轮）。
#: 剥掉工具往返的轮补的标注：不补的话模型会以为这些轮没调用过工具。


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

    思维链是模型的中间稿：整段回传就是让每次请求多背一大段**必然未命中缓存**的内容
    （实测一条会话里它占 prompt 的 72%）。按预算裁到两头保留，既省掉大部分钱，
    又让模型看得到"上一轮打算干什么、得出了什么"。

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


def _as_text_parts(text: Any) -> List[str]:
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
    """每个**用户轮**的起始下标（一条 user 起到下一条 user 前，为原子单位）。

    轮的边界只认 `user`：一条 user 之后的所有 `assistant` / `tool` 都属于这一轮 ——
    工具往返、悬空调用、多段回复都算轮内。压缩只允许整轮处理。
    """
    return [i for i, m in enumerate(messages or [])
            if isinstance(m, dict) and str(m.get("role") or "") == "user"]


def turn_boundary_floor(messages: List[Dict[str, Any]], index: int) -> int:
    """把下标**向下取整**到最近的用户轮起始位置。

    不是轮边界时向**前**退到本轮的起点（宁可少压，也不从轮中间切开）::

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
    """区间 `[start, end)` 内工具链是否**闭合**。

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
def layout_from_messages(
    messages: List[Dict[str, Any]],
    *,
    system_text: str = "",
    head: Optional[List[Dict[str, Any]]] = None,
    plugin_segments: Optional[List[Tuple[str, str, int]]] = None,
    budget_tokens: int = 0,
    token_fn: Optional[Callable[[Dict[str, Any]], int]] = None,
) -> Dict[str, Any]:
    """把请求的**头部 + 对话**切开分段并统计 token（观察面用）。

    `head` 是装配出来的头部：第 1 条是系统提示词，其后依次是**插件各段**
    （顺序与 `plugin_segments` 一致），再往后是记忆摘要。
    `plugin_segments` 是 `[(段 key, 段名, 主体数量)]` —— 由插件给，宿主不猜。

    插件内容与 Skills 清单**不在事实记录里**（每回合装配时注入），所以不传 `head`
    就只能退化：按位置猜，插件各段与摘要分不出来。

    模式从对话段里按正文认（`## 当前模式` 开头），单列一段。
    """
    counter = token_fn or default_message_tokens
    msgs = [m for m in (messages or []) if isinstance(m, dict)]
    budget_in = max(int(budget_tokens or 0), 1)
    if not msgs and not head:
        return {"segments": [], "total_tokens": 0, "budget_tokens": budget_in,
                "model_max_context_tokens": 0}

    if head is not None:
        head_msgs = [m for m in head if isinstance(m, dict)]
        body = msgs
    else:
        cut = next((i for i, m in enumerate(msgs)
                    if str(m.get("role") or "") == "user"), len(msgs))
        head_msgs, body = msgs[:cut], msgs[cut:]

    prompt = str(system_text or "").strip()
    rest_head = list(head_msgs)
    if prompt:
        # 给了系统提示词正文：头部第 1 条若与它同文，就不再重复计入。
        if rest_head and str(rest_head[0].get("content") or "").strip() == prompt:
            rest_head = rest_head[1:]
    elif rest_head:
        # 没给正文：头部第 1 条就是系统提示词，同样要从后面的分段里去掉 ——
        # 否则它会被系统段与摘要段各算一次。
        rest_head = rest_head[1:]
    plan = list(plugin_segments or [])
    # 空占位段不占头部消息：按「有正文才消费一条」对齐，避免知识库未勾选时
    # 把后面 Skills 的消息错贴到知识库段上。
    plugin: List[List[Dict[str, Any]]] = []
    msg_i = 0
    for seg in plan:
        seg_count = int(seg[2]) if len(seg) > 2 else 0
        if seg_count > 0 and msg_i < len(rest_head):
            plugin.append([rest_head[msg_i]])
            msg_i += 1
        elif seg_count > 0:
            plugin.append([])
        else:
            plugin.append([])
    # 插件各段之后剩下的都算记忆摘要（压缩产出的那份）。
    summary = [m for m in rest_head[msg_i:]]

    mode: List[Dict[str, Any]] = []
    for m in reversed(body):
        if str(m.get("role") or "") == "system" \
                and str(m.get("content") or "").startswith("## 当前模式"):
            mode = [m]
            break
    dialogue = [m for m in body if m not in mode]

    rows: List[Dict[str, Any]] = []

    def _row(key: str, items: List[Dict[str, Any]],
             tokens: Optional[int] = None, count: Optional[int] = None,
             label: str = "") -> None:
        rows.append({
            "key": key,
            "label": label or ContextPipeline.SEGMENT_LABELS.get(key, key),
            "tokens": int(tokens) if tokens is not None
            else sum(int(counter(m)) for m in items),
            "count": len(items) if count is None else int(count),
        })

    if prompt:
        _row("system", [], int(counter({"role": "system", "content": prompt})), count=1)
    elif head_msgs:
        _row("system", head_msgs[:1])
    # 头部内部顺序与装配一致：插件各段 → 记忆摘要；对话接在摘要之后。
    for i, seg in enumerate(plan):
        seg_key, seg_label = str(seg[0]), str(seg[1])
        seg_count = int(seg[2]) if len(seg) > 2 else len(plugin[i])
        _row(f"plugin:{seg_key}", plugin[i], count=seg_count, label=seg_label)
    _row("summary", summary)
    # 对话段计**用户轮数**（不是消息条数）：一轮里有问有答还有工具往返。
    _row("full_recent", dialogue,
         count=sum(1 for m in dialogue if str(m.get("role") or "") == "user"))
    if mode:
        _row("mode", mode)

    total = sum(int(r["tokens"]) for r in rows)
    budget = max(int(budget_tokens or 0), total, 1)
    segments: List[Dict[str, Any]] = []
    for row in rows:
        row = dict(row)
        row["pct"] = round(100.0 * row["tokens"] / budget, 6)
        segments.append(row)
    segments.append({
        "key": "remaining",
        "label": "剩余容量",
        "tokens": max(0, budget - total),
        "pct": round(100.0 * max(0, budget - total) / budget, 6),
    })
    return {
        "segments": segments,
        "total_tokens": total,
        "budget_tokens": budget,
        "model_max_context_tokens": 0,
    }


def excerpt_by_target_tokens(
    messages: List[Dict[str, Any]],
    keep_turns: int,
    token_fn: Optional[Callable[[Dict[str, Any]], int]] = None,
) -> Optional[Tuple[int, int]]:
    """要压缩掉的区间 `[0, end)`：**遮盖末尾 `keep_turns` 轮，压它前面的**。

    遮盖是**偏好**（正常情况）：

    - 末尾 `keep_turns` 个用户轮不压 —— 那是模型的近场，手里的活全在那里；
    - 压缩区域只能是**「最后一个前置 system 之后 → 遮盖起点之前」**那一段。
      系统提示词 / Skills / 知识库 / 记忆摘要都是 `system`，位置在对话之前，
      所以这个区域天然只覆盖对话，不含任何系统设定。

    **压不动就连近场一起压**（这一条亘古不变）：遮盖前面没有可压的轮
    （例如总共只剩 1 轮、或遮盖已经盖住全部）时，连遮盖一起压掉 ——
    极端情况压缩后整个上下文 **0 个用户轮**，摘要接管全部历史，
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
        # 遮盖前面没有可压的轮 → **连遮盖一起压**（压到末尾）。
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







@dataclass(frozen=True)
class SourceMeta:
    """插件段落的描述：段 key 与段名。

    `key` 是**前端认的字段名**，也进 `context_layout.segments[].key`，
    所以与插件名一致；宿主不解释它的含义。
    """

    key: str = ""
    label: str = ""
    plugin: str = ""
    # 注入前缀：告诉模型这段是什么（如 `【知识库：a.md】`、`【Skills 清单】`）。
    # 前缀由来源给，宿主不替它拼 —— 拼错了模型会把它当对话内容。
    prefix: str = ""
    # 主体数量的取数口 `fn(conversation_id) -> int`（插件自报，如"勾选了几个文件"、
    # "清单里列了几个 Skills"）；不给时按消息条数算。
    count: Optional[Callable[[str], int]] = None
    # 插件在清单（`plugins.ini`）里的位次。插件段之间的组装顺序**按它排** ——
    # 清单靠前的插件，它的段也靠前。应用级来源（非插件）没有位次，排在最后。
    plugin_rank: Optional[int] = None


@dataclass(frozen=True)
class PluginSegments:
    """插件贡献的段落：段落表 + 各段主体数量。

    `items` 是 `[(段 key, 段名, 正文)]`，顺序即装配顺序；
    `counts` 是**按位置**对应的主体数量（同一个插件可以声明多段，按 key 存会互相覆盖）；
    """

    items: Tuple[Tuple[str, str, str], ...] = ()
    counts: Tuple[int, ...] = ()

    def __post_init__(self) -> None:
        """入口即冻结：调用方传 list 也落成 tuple（B1）。

        冻结对象却留着可变容器，等于只锁了门框：外部改一下原列表，
        装配顺序与数量就跟着变。这里逐项复制成元组，之后任何人都改不到。
        正文元素保持原样（可能已经是 `list[str]`，由装配侧再展开）。
        """
        frozen: List[Tuple[str, str, str]] = []
        for item in self.items:
            parts = tuple(item)
            if len(parts) != 3:
                raise ValueError(
                    f"PluginSegments 每项须为 (key, 段名, 正文)，收到 {parts!r}"
                )
            frozen.append((parts[0], parts[1], parts[2]))
        object.__setattr__(self, "items", tuple(frozen))
        object.__setattr__(self, "counts", tuple(int(c) for c in self.counts))


def slug(text: str) -> str:
    """把任意名字压成可用作段 key 的形状（只留字母数字与 `_`、`-`）。"""
    out = "".join(ch if (ch.isalnum() or ch in "_-") else "_" for ch in str(text or ""))
    return out.strip("_") or "source"


class ContextSources:
    """上下文注入源注册表（扩展点）。

    每个来源贡献**一段** `system` 文本，并自带段名（`SourceMeta`）：
    段 key 是插件名（前端按它找插件注册的渲染钩子），段名与主体数量由插件给。

    宿主不认识任何具体插件 —— 知识库、Skills 清单都只是"某个插件注册的一段"；
    来源函数是 `fn(conversation_id) -> List[str]`（文本列表，每条独立成消息）。
    `collect` 按注册顺序串接，单个来源异常被隔离（记录 stderr），不影响其他来源。
    """

    def __init__(self) -> None:
        self._sources: List[Tuple[str, str, Callable[[str], List[str]], Any, str, str]] = []
        self._lock = threading.Lock()
        #: 内容版本号：注册变化或来源自身的数据变化（例如勾选集合变了）时 +1。
        #: 装配侧据此判断缓存的收集结果还能不能用 —— 光看"有没有注册新来源"
        #: 判不出"同一个来源的数据换了"。
        self._version = 0

    @property
    def version(self) -> int:
        return int(self._version)

    def bump(self) -> None:
        """标记来源内容已变（勾选集合、磁盘文件等），让装配侧丢掉缓存重收集。"""
        with self._lock:
            self._version += 1

    def add(self, fn: Callable[[str], List[str]],
            meta: Optional["SourceMeta"] = None) -> Callable[[], None]:
        """注册一段注入源；返回幂等 disposer。

        `meta` 不给时按来源函数名兜底成一段段名等于 key 的来源。
        """
        if not callable(fn):
            raise ValueError("上下文来源必须可调用")
        info = meta if isinstance(meta, SourceMeta) else SourceMeta()
        key = info.key or slug(getattr(fn, "__name__", "") or "source")
        return self._register(self._sources,
                              (key, info.label or key, fn, info.count, info.prefix,
                               info.plugin_rank))

    def _register(self, bucket: List[Any], item: Any) -> Callable[[], None]:
        with self._lock:
            bucket.append(item)
            self._version += 1

        def _dispose() -> None:
            with self._lock:
                if item in bucket:
                    bucket.remove(item)
                    # 卸下来源也是内容变化。不打版本号的话，本趟还没作废的快照
                    # 会继续带着已经卸掉的那一段。
                    self._version += 1

        return _dispose

    def collect_segments(self, conversation_id: str) -> "PluginSegments":
        """收集注入源，返回 `PluginSegments`（异常隔离）。

        `items` 是 `[(段 key, 段名, 正文)]`；`counts` **按位置**对应 `items` ——
        同一个插件可以注册多个来源，它们共用段 key，按 key 存会互相覆盖。
        数量由来源自报，没有自报口的按消息条数算。
        """
        with self._lock:
            sources = list(self._sources)
        # 插件段按**插件清单位次**排：清单靠前的插件排在前面；
        # 没有位次的（应用级来源）排最后。稳定排序，同位次保持注册序。
        sources.sort(key=lambda s: (s[5] is None, s[5] if s[5] is not None else 0))
        items: List[Tuple[str, str, str]] = []
        counts: List[int] = []
        for key, label, fn, reported, prefix, _order in sources:
            texts = self._gather(fn, conversation_id)
            if texts is None:
                # 来源异常已隔离：不占位（占位会假装插件正常只是没内容）。
                continue
            amount = None
            if callable(reported):
                try:
                    amount = max(0, int(reported(conversation_id)))
                except Exception as exc:
                    report_error(
                        "context.source_count",
                        exc,
                        conversation_id=conversation_id,
                        source=key,
                    )
                    amount = None
            if not texts:
                # 空段仍占位：上下文示意图要看见已装载但尚未注入内容的插件
                # （例如知识库未勾选）。正文空串，装配进模型时会被跳过。
                items.append((key, label, ""))
                counts.append(amount if amount is not None else 0)
                continue
            for i, text in enumerate(texts):
                # 前缀在收集时统一加上：插件只管正文，前缀由它自己声明。
                items.append((key, label, f"{prefix}{text}" if prefix else text))
                # 一个来源给多条正文时只有第一条带自报数量，其余按条数算。
                counts.append(amount if i == 0 and amount is not None else 1)
        # 不变量：数量与正文**逐条对齐**。少了数量，管线那边会把别人的数量贴到
        # 自己的段上（按位置取值）；错位是静默的，只在浮层上表现为数字离谱。
        while len(counts) < len(items):
            counts.append(1)
        return PluginSegments(items=tuple(items), counts=tuple(counts))

    @staticmethod
    def _gather(
        fn: Callable[[str], List[str]], conversation_id: str,
    ) -> Optional[List[str]]:
        """收集一个来源。异常 → `None`（隔离、不占位）；正常无正文 → `[]`（占空段）。"""
        try:
            parts = fn(conversation_id)
        except Exception as exc:
            report_error(
                "context.source",
                exc,
                conversation_id=conversation_id,
            )
            return None
        out: List[str] = []
        for text in parts or []:
            t = str(text or "").strip()
            if t:
                out.append(t)
        return out


class ContextPipeline:
    """会话级上下文管线（摘要生成由外部执行）。"""

    def __init__(
        self,
        conversation_id: str = "",
        *,
        full_user_rounds: int = DEFAULT_FULL_USER_ROUNDS,
        summary_token_threshold: int = DEFAULT_SUMMARY_TOKEN_THRESHOLD,
        reasoning_replay_tokens: int = DEFAULT_REASONING_REPLAY_TOKENS,
        model_context_window: int = 0,
        sources: Optional["ContextSources"] = None,
    ) -> None:
        self.conversation_id = str(conversation_id or "")
        self.full_user_rounds = max(1, int(full_user_rounds))
        self.summary_token_threshold = max(1, int(summary_token_threshold))
        #: 思维链回传预算（token）：-1 全量、0 不回传、正数取两头中间省略。
        self.reasoning_replay_tokens = int(reasoning_replay_tokens)
        #: 模型上下文窗口（token）：界面按它算占用率；0 = 未配置，界面用预算兜底。
        self.model_context_window = int(model_context_window or 0)
        #: 最近这么多**用户轮**原样保留（含工具往返）；更早的轮剥掉轮内工具往返。
        #: 负数 = 不剥（全部保留）。
        self._sources = sources
        # 插件段落：`[(段 key, 段名)]`；有正文的段才与 CHUNK_PLUGIN 消息对齐。
        self._plugin_sources: List[Tuple[str, str]] = []
        # 插件自报的主体数量，**按段的位置**对应（缺省时段落行按消息条数算）。
        self._plugin_counts: List[int] = []
        #: 与 `_plugin_sources` 对齐：是否带进模型的正文（空占位为 False）。
        self._plugin_has_body: List[bool] = []
        #: 本趟链的注入源快照。`begin_pass` 收集，`end_pass` 丢掉。
        #: 这一趟里压缩与模型请求共用这一份；趟结束就放开，
        #: 下一趟若不来，知识库和 Skills 正文不会留在会话上。
        self._sources_snapshot: Any = None
        #: 快照对应的来源版本号（版本一变就重收集）
        self._sources_snapshot_version: int = -1
        self.chunks: List[ContextChunk] = []
        self.name_map: Dict[str, ContextChunk] = {}
        for nm in CHUNK_ORDER:
            c = ContextChunk(nm)
            self.chunks.append(c)
            self.name_map[nm] = c
        self.pending_mem_file_path: Optional[str] = None
        self.pending_over_rounds: Optional[List[Round]] = None

    # ── 结构──────────────────────────────────────

    #: 前端上下文条的段名与配色键（与 `segments()` 输出一致）。
    SEGMENT_LABELS = {
        "system": "系统提示词",
        "summary": "记忆摘要",
        "full_recent": "近期记忆",
        "mode": "模式",
    }

    def segment_tokens(
        self,
        *,
        token_fn: Optional[Callable[[Dict[str, Any]], int]] = None,
    ) -> List[Dict[str, Any]]:
        """按**当前装配**逐段统计 token：系统提示词 + 插件各段 + 记忆摘要 + 对话。

        口径与真正发出去的请求一致（同一个 `default_message_tokens`）。
        插件各段一段一条，key 是 `plugin:<插件名>`、段名与数量由插件给 ——
        内核不认识知识库、Skills 这些具体名字。

        **模式不在管线里** —— 它是请求尾部的临时后缀，由调用方单独算。

        返回 `[{key, label, tokens, count}]`（按装配顺序）。
        """
        counter = token_fn or default_message_tokens
        rows: List[Dict[str, Any]] = []
        for key, name in (("system", CHUNK_SYSTEM),
                          ("summary", CHUNK_MEM), ("full_recent", CHUNK_FULL)):
            chunk = self.name_map.get(name)
            tokens = 0
            msgs = 0
            users = 0
            if chunk is not None:
                for rnd in chunk.rounds:
                    for msg in rnd.messages:
                        tokens += int(counter(msg))
                        msgs += 1
                        if str(msg.get("role") or "") == "user":
                            users += 1
            rows.append({
                "key": key,
                "label": self.SEGMENT_LABELS[key],
                "tokens": tokens,
                # 计「个」的口径按段定：头部各段按消息条数，对话段按用户轮数。
                "count": users if key == "full_recent" else msgs,
            })
        # 段顺序**逐条对齐装配顺序**：系统提示词 → 插件各段 → 记忆摘要 → 近期记忆。
        # 前端就按这个顺序画，所以不能为了方便把摘要挪到末尾。
        head = [rows[0]] if rows else []
        tail = [r for r in rows[1:] if r["key"] == "full_recent"]
        summary = [r for r in rows[1:] if r["key"] != "full_recent"]
        return head + self._plugin_rows(counter) + summary + tail

    def _plugin_rows(
        self, counter: Callable[[Dict[str, Any]], int],
    ) -> List[Dict[str, Any]]:
        """插件贡献的段落：一段一条，key 用插件来源声明的名字。

        消息与段落**按顺序对齐**：`set_plugin_segments` 保证每条消息各成一轮、
        顺序与来源一致，所以这里按展平顺序数过去即可。
        """
        flat: List[Dict[str, Any]] = []
        chunk = self.name_map.get(CHUNK_PLUGIN)
        if chunk is not None:
            for rnd in chunk.rounds:
                flat.extend(rnd.messages)
        rows: List[Dict[str, Any]] = []
        counts = list(self._plugin_counts)
        has_body = list(getattr(self, "_plugin_has_body", []) or [])
        msg_i = 0
        for i, (key, label) in enumerate(self._plugin_sources):
            # 空占位不占消息槽，避免把后面插件的正文错算到本段。
            body = True if i >= len(has_body) else bool(has_body[i])
            msg = None
            if body and msg_i < len(flat):
                msg = flat[msg_i]
                msg_i += 1
            # 自报数量**按位置**对来源：数量表比来源表长说明两者已经错位，
            # 此时宁可退回"按消息条数"（1），也不要拿别人的数量去贴自己的段。
            reported = counts[i] if i < len(counts) else None
            rows.append({
                "key": f"plugin:{key}",
                "label": label,
                "tokens": int(counter(msg)) if msg is not None else 0,
                "count": (1 if msg is not None else 0) if reported is None else int(reported),
            })
        return rows

    def layout_payload(
        self,
        *,
        budget_tokens: int = 0,
        model_max_context_tokens: int = 0,
        token_fn: Optional[Callable[[Dict[str, Any]], int]] = None,
        tail_messages: Any = None,
    ) -> Dict[str, Any]:
        """上下文分段快照（前端画上下文条与浮层用）。

        每段 `{key, label, tokens, pct, count}`，末尾补 `剩余容量`；
        `pct` 相对**预算**（取预算与已用中的较大者，保证各段之和不超过 100%）。

        `tail_messages` 是请求尾部的临时后缀（本轮新输入 / 工具结果 / 执行模式），
        不在管线里持有，由调用方传进来单独算 `mode` 段。
        """
        counter = token_fn or default_message_tokens
        rows = self.segment_tokens(token_fn=counter)
        tail_tokens = sum(int(counter(m)) for m in (tail_messages or [])
                          if isinstance(m, dict))
        if tail_tokens:
            rows = [r for r in rows if r["key"] != "mode"]
            rows.append({
                "key": "mode",
                "label": self.SEGMENT_LABELS["mode"],
                "tokens": tail_tokens,
                "count": len([m for m in (tail_messages or []) if isinstance(m, dict)]),
            })
        total = sum(int(r["tokens"]) for r in rows)
        budget = max(int(budget_tokens or 0), total, 1)
        remainder = max(0, budget - total)
        segments: List[Dict[str, Any]] = []
        for row in rows:
            row = dict(row)
            row["pct"] = round(100.0 * row["tokens"] / budget, 6)
            segments.append(row)
        segments.append({
            "key": "remaining",
            "label": "剩余容量",
            "tokens": remainder,
            "pct": round(100.0 * remainder / budget, 6),
        })
        return {
            "segments": segments,
            "total_tokens": total,
            "budget_tokens": budget,
            # 模型窗口：界面按它算占用率。调用方没传时用实例上配的那个；
            # 都没配就给 0，界面退回用预算当分母（并标明是预算口径）。
            "model_max_context_tokens": int(model_max_context_tokens
                                            or self.model_context_window or 0),
        }

    def add(self, chunk: ContextChunk) -> None:
        """扩展点：追加自定义块（排在 `CHUNK_ORDER` 之后；参与展平与统计）。"""
        self.chunks.append(chunk)
        self.name_map[chunk.name] = chunk

    # ── 三段式装配（唯一装配入口）──────────────
    #
    # 发给模型的 messages 只有三段，顺序拼接，**不做任何重建**：
    #
    #   ① 头部（host）  系统提示 / Skills / 知识库 / 摘要 —— 本回合内逐字节稳定
    #   ② 对话（dialogue） 事实折叠出来的对话（含工具调用与工具结果）
    #   ③ 尾部（tail）  本轮新输入 / 工具结果 + 执行模式 —— 请求时才拼
    #
    #   messages = 头部 + 对话 + 尾部
    #
    # 压缩请求用的是同一份"头部 + 对话"，末尾换成压缩指令：
    #
    #   压缩请求 = 头部 + 对话 + [压缩指令]
    #
    # 两个请求共用同一个 `assembles()`：前缀相同不是靠比对保证的，而是同一份列表。

    def message_tokens(self, msg: Dict[str, Any]) -> int:
        """单条消息的 token 估算（与 `total_token_estimate` 用同一个口径）。"""
        return int(default_message_tokens(msg))

    def set_dialogue(self, messages: Any, *, covered_end: int = 0,
                     reasoning_budget: Optional[int] = None) -> None:
        """装对话段（②）。

        `covered_end`：已覆盖前缀长度（压缩器维护），那一段由摘要代表，
        不再进对话段。缺省 0 = 全量都是对话。

        `reasoning_budget`：思维链回传预算（token）。`-1` 全量、`0` 全丢、
        正数取两头中间省略；缺省用实例上的 `reasoning_replay_tokens`。
        **在这里裁**而不是在线上裁：分段统计与预算估算看的是同一份，
        两处不一致时界面会把窗口算满、压缩也会提前或滞后触发。
        事实流不动，记录与界面的事件照旧带完整推理。

        顺带从注入源刷新知识库 —— 这是"每回合开始"的挂点（对话每回合都重装）。
        """
        seq = list(messages or [])
        cut = max(0, int(covered_end or 0))
        if cut:
            seq = seq[cut:]
        budget = (self.reasoning_replay_tokens if reasoning_budget is None
                  else int(reasoning_budget))
        seq = clip_reasoning(seq, budget)
        self.name_map[CHUNK_FULL].rounds = flat_messages_to_user_rounds(seq)
        self._refresh_sources()

    def set_summary_messages(self, summaries: Any) -> None:
        """装摘要段（属头部①）。每次压缩后调用一次，装的是**全部**摘要。"""
        chunk = self.name_map[CHUNK_MEM]
        chunk.rounds = []
        for sm in summaries or []:
            if not isinstance(sm, dict):
                continue
            r = Round()
            r.append_message_dict(copy.deepcopy(dict(sm)))
            chunk.rounds.append(r)

    def plugin_segments(self) -> List[Tuple[str, str, int]]:
        """当前插件段落的 `[(段 key, 段名, 主体数量)]`（顺序与头部一致）。"""
        return [(key, label,
                 int(self._plugin_counts[i]) if i < len(self._plugin_counts) else 0)
                for i, (key, label) in enumerate(self._plugin_sources)]

    def host_messages(self) -> List[Dict[str, Any]]:
        """头部①：系统提示 / Skills / 插件段落 / 摘要，按 `CHUNK_ORDER` 顺序。

        模式块不在这里 —— 它是尾部③。
        """
        out: List[Dict[str, Any]] = []
        for name in (CHUNK_SYSTEM, CHUNK_PLUGIN, CHUNK_MEM):
            chunk = self.name_map.get(name)
            if chunk is None:
                continue
            for rnd in chunk.rounds:
                for m in rnd.messages:
                    out.append(copy.deepcopy(m))
        return out

    def dialogue_messages(self) -> List[Dict[str, Any]]:
        """对话段②：按事实顺序。"""
        chunk = self.name_map.get(CHUNK_FULL)
        if chunk is None:
            return []
        return [copy.deepcopy(m) for rnd in chunk.rounds for m in rnd.messages]

    def assembles(self, tail: Any = None) -> List[Dict[str, Any]]:
        """三段拼接：头部 + 对话 + 尾部。**唯一装配入口**，无重建。"""
        out = self.host_messages() + self.dialogue_messages()
        for m in tail or []:
            if isinstance(m, dict):
                out.append(copy.deepcopy(m))
        return out

    # ── 内容装配──────────────────────────

    def append_system(self, text: str) -> None:
        """追加系统段（每段独立成轮）。"""
        self.name_map[CHUNK_SYSTEM].append("system", text, True)

    def system_text(self) -> str:
        """当前系统段全文（各段以空行相连）。

        模型否认看到图片时的最小上下文重试＝本方法结果 + 当前那条用户消息 ——
        最小上下文 = 这份系统提示 + 当前那条用户消息。
        """
        chunk = self.name_map.get(CHUNK_SYSTEM) if hasattr(self, "name_map") else None
        if chunk is None:
            return ""
        parts: List[str] = []
        for rnd in getattr(chunk, "rounds", []) or []:
            for m in getattr(rnd, "messages", []) or []:
                if str(m.get("role") or "") == "system":
                    text = str(m.get("content") or "").strip()
                    if text:
                        parts.append(text)
        return "\n\n".join(parts)

    def append_plugin(self, text: str, key: str = "", label: str = "") -> None:
        """追加一段插件内容（每段独立成轮）。

        `text` 可能是列表（注入源常按"条目"给），必须**归一成字符串正文** ——
        直接把列表塞进 `content` 会让模型收到 Python 字面量
        （`['条目一']`），而不是条目本身。
        """
        for part in _as_text_parts(text):
            if not str(part).strip():
                continue
            self.name_map[CHUNK_PLUGIN].append("system", part, True)
            self._plugin_sources.append((key or slug(label), label or key))
            self._plugin_has_body.append(True)

    def set_plugin_segments(self, segments: Any) -> None:
        """整体设置插件段落（清空重建；空列表清空）。

        收 `PluginSegments`（段落表 + 数量表）；也接受裸的 `[(key, 段名, 正文)]`。
        **顺序即装配顺序**，每条正文各成一轮，所以统计时能按顺序逐段对上。
        """
        if isinstance(segments, PluginSegments):
            items, counts = segments.items, list(segments.counts)
        else:
            items, counts = list(segments or []), []
        chunk = self.name_map[CHUNK_PLUGIN]
        chunk.rounds = []
        self._plugin_sources = []
        self._plugin_counts = list(counts)
        #: 与 `_plugin_sources` 对齐：这段是否带了进模型的正文（空占位为 False）
        self._plugin_has_body: List[bool] = []
        for key, label, text in items:
            parts = [p for p in _as_text_parts(text) if str(p).strip()]
            if not parts:
                self._plugin_sources.append((key, label))
                self._plugin_has_body.append(False)
                continue
            for part in parts:
                chunk.append("system", part, True)
                self._plugin_sources.append((key, label))
                self._plugin_has_body.append(True)

    def set_summaries(self, summaries: List[Dict[str, Any]]) -> None:
        """设置摘要（记忆块；逐条独立成轮，深拷贝）。"""
        chunk = self.name_map[CHUNK_MEM]
        chunk.rounds = []
        for sm in summaries:
            r = Round()
            r.append_message_dict(copy.deepcopy(dict(sm)))
            chunk.rounds.append(r)

    def set_mode_tail(self, message: Optional[Dict[str, Any]]) -> None:
        """设置「模式」尾块（单条；None 清空）。"""
        chunk = self.name_map[CHUNK_MODE]
        chunk.rounds = []
        if message:
            r = Round()
            r.append_message_dict(copy.deepcopy(dict(message)))
            chunk.rounds.append(r)

    def append_new_msg(self, role: str, content: str, **extra: Any) -> None:
        """新开一轮（首条建议 role=user）。"""
        self.name_map[CHUNK_FULL].append(role, content, True, **extra)

    def append_msg(self, role: str, content: str, **extra: Any) -> None:
        """追加至当前最后一轮。"""
        self.name_map[CHUNK_FULL].append(role, content, False, **extra)

    def rebuild_from_messages(self, flat_messages: List[Dict[str, Any]]) -> None:
        """兼容入口：装对话段（等价 `set_dialogue(..., covered_end=0)`）。

        保留旧名只为不打断既有调用方；**内部不再"按 role 重建"** ——
        那种重建会打乱分块归属，装配一律走 `set_dialogue()` + `assembles()`。
        """
        self.set_dialogue(flat_messages, covered_end=0)

    def begin_pass(self) -> None:
        """一趟链开始：收集注入源。本趟内的装配共用这一份。"""
        self._drop_source_snapshot()
        self._refresh_sources()

    def end_pass(self) -> None:
        """一趟链结束：丢掉注入源快照。

        快照里是知识库正文和 Skills 正文。留到下一趟开始再清的话，
        下一趟若不来，这份内容就一直挂在会话上。
        插件段是从这份快照装上去的，一并卸掉；下一趟开始会重新装。
        """
        self._drop_source_snapshot()
        self.set_plugin_segments([])

    def _drop_source_snapshot(self) -> None:
        self._sources_snapshot = None
        self._sources_snapshot_version = -1

    def refresh_sources(self) -> None:
        """强制刷新注入源（界面勾选/文件改动后立刻生效用）。"""
        self._sources_snapshot = None
        self._refresh_sources()

    def _refresh_sources(self) -> None:
        """从注入源刷新**知识库**与 **Skills** 块（无来源时不动）。

        Skills 也走注入源：Skills 库注册「可用 Skills 清单」（渐进式披露第一层）
        与 `auto_load/` 常驻 Skills 正文（第二层）。

        **一趟链只收集一次**：压缩模块、压缩器内部、模型模块会各装一次对话。
        每次收集都要重列 Skills 目录、重读全部勾选文件。同一趟里收集两遍不只是
        白烧磁盘 —— 两遍之间源可变，于是"压缩看到的那份"和"发出去的那份"
        数字可能对不上。快照由 `begin_pass()` 在一趟开始时收集，
        `end_pass()` 在一趟结束时丢掉 —— 不留到下一趟，下一趟没来也不会占着内存。
        需要在本趟中途拿到新数据时调 `refresh_sources()`，或由来源 `bump()`。
        """
        if self._sources is None:
            return
        collect_segments = getattr(self._sources, "collect_segments", None)
        if not callable(collect_segments):
            return
        version = int(getattr(self._sources, "version", 0) or 0)
        if self._sources_snapshot is None or version != self._sources_snapshot_version:
            self._sources_snapshot = collect_segments(self.conversation_id)
            self._sources_snapshot_version = version
        self.set_plugin_segments(self._sources_snapshot)


    # ── 展平──────────────────────────────────────

    def flatten_to_messages(
        self,
        sanitize_fn: Optional[Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]] = None,
    ) -> List[Dict[str, Any]]:
        """按块顺序展平（空块跳过；深拷贝；末端统一过 sanitize_fn）。"""
        built: List[Dict[str, Any]] = []
        for chunk in self.chunks:
            for r in chunk.rounds:
                for m in r.messages:
                    built.append(copy.deepcopy(m))
        if sanitize_fn is not None:
            built = sanitize_fn(built)
        return built

    # ── 窗口与摘要调度────────────────────

    # ── 待并摘要──────────────────────────────────

    def put_new_mem_file(self, path: str, over_rounds: List[Round]) -> None:
        """暂存待处理摘要来源（路径 + 越界轮）。"""
        self.pending_mem_file_path = str(path)
        self.pending_over_rounds = list(over_rounds)

    def try_load_pending_mem_file(
        self,
        messages: List[Dict[str, Any]],
        merge_fn: Callable[[str, List[Dict[str, Any]]], None],
    ) -> None:
        """发模型前：委托 merge_fn 合并待并摘要，随后清空 pending（幂等由 merge_fn 侧负责）。"""
        merge_fn(self.conversation_id, messages)
        self.pending_mem_file_path = None
        self.pending_over_rounds = None

    # ── 估算与统计────────────────────────

    def total_token_estimate(
        self, approx_msg_fn: Callable[[Dict[str, Any]], int] = default_message_tokens
    ) -> int:
        """全部块 token 估算求和。"""
        return sum(c.calculate_tokens(approx_msg_fn) for c in self.chunks)

    def calculate_tokens(
        self, approx_msg_fn: Callable[[Dict[str, Any]], int] = default_message_tokens
    ) -> Dict[str, int]:
        """分块 token 估算（{块名: tokens}；空块计 0）。"""
        return {c.name: c.calculate_tokens(approx_msg_fn) for c in self.chunks}

    def calculate_round_count(self) -> Dict[str, int]:
        """分块轮数（{块名: 轮数}）。"""
        return {c.name: c.get_count() for c in self.chunks}
