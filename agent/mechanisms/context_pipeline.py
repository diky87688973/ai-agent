# -*- coding: utf-8 -*-
"""上下文管线：七块上下文与摘要调度。

- 数据模型：七块（系统提示词 / Skills / 知识库 / 记忆文件 / 远期记忆 /
  近期记忆 / 模式）+ Round（user 起轮）+ ContextChunk（命名块含轮）；
- 展平：系统 → Skills → 知识库 → 摘要 → 对话（远期 → 近期）→ 模式；
  空块跳过；末端统一过 sanitize_fn；
- 摘要调度：越界轮提取 / 半开取段区间 / 工具链完整性外扩 / 素材切轮；
- 待并摘要：暂存 → 合并 → 清空；
- 估算与统计：总量 / 分块 / 轮数。

装配说明：
- 最小集 = 系统块 + 对话块；Skills / 模式块保留结构、留空待能力接入；知识库块经 ContextSources 注入源刷新；
- 对话段以「远期 → 近期」时序展平；
- 摘要生成（调用模型产出摘要文本）不在本模块范围（属压缩策略执行侧）；
- 持久化重建走时序路径（rebuild_from_messages）。
"""
from __future__ import annotations

import copy
import sys
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

CHUNK_SYSTEM = "系统提示词"
CHUNK_SKILL = "Skills"
CHUNK_KB = "知识库"
CHUNK_MEM = "记忆文件"
CHUNK_PURE = "远期记忆"
CHUNK_FULL = "近期记忆"
CHUNK_MODE = "模式"
CHUNK_ORDER = (CHUNK_SYSTEM, CHUNK_SKILL, CHUNK_KB, CHUNK_MEM, CHUNK_PURE, CHUNK_FULL, CHUNK_MODE)

DEFAULT_PURE_USER_ROUNDS = 2
DEFAULT_FULL_USER_ROUNDS = 6
DEFAULT_SUMMARY_TOKEN_THRESHOLD = 8000


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


def approx_tokens_text(text: str) -> int:
    """粗略 token 估算：非空字符数 // 4 + 4；空串 0（缺省估算器，可整体替换）。"""
    s = str(text or "")
    if not s:
        return 0
    return len(s) // 4 + 4


def default_message_tokens(msg: Dict[str, Any]) -> int:
    """缺省消息 token 估算（接入时可替换为更精确实现）。

    多模态 content 里**图片块按每图固定上限计**：base64 是编码而非文本，
    拿它按字符估算会把一张截图算成两千多 token（官方口径每图最多 1024）。
    """
    content = msg.get("content")
    if isinstance(content, list):
        imgs = sum(1 for p in content
                   if isinstance(p, dict) and p.get("type") == "image_url")
        texts = "".join(str(p.get("text") or "") for p in content
                        if isinstance(p, dict) and p.get("type") == "text")
        # 与压缩器同一口径（`IMAGE_TOKENS_PER_IMAGE = 384`）。
        return approx_tokens_text(texts) + imgs * 384
    return approx_tokens_text(str(content or ""))


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


def dialogue_summary_excerpt_half_open_for_messages(
    messages: List[Dict[str, Any]],
    full_user_rounds: int,
    pure_user_rounds: int,
) -> Optional[Tuple[int, int]]:
    """摘要取段半开区间 [start, end)；无需摘要 → None。"""
    fu = find_first_user_index(messages)
    if fu is None:
        return None
    user_idxs = [i for i, m in enumerate(messages) if m.get("role") == "user" and i >= fu]
    k = len(user_idxs)
    fn = max(1, int(full_user_rounds))
    pn = max(0, int(pure_user_rounds))
    reserve = fn + pn
    if k <= reserve:
        if k <= fn:
            return None
        end_cap = user_idxs[k - fn]
    else:
        end_cap = user_idxs[k - reserve]
    start0 = fu
    if start0 >= end_cap:
        return None
    s_adj, e_adj = adjust_excerpt_range_half_open(messages, start0, end_cap)
    e_adj = min(e_adj, end_cap)
    if s_adj >= e_adj:
        return None
    return s_adj, e_adj


def excerpt_slice_to_rounds(
    messages: List[Dict[str, Any]],
    full_user_rounds: int,
    pure_user_rounds: int,
) -> List[Round]:
    """由摘要半开区间得到 Round 列表；区间空 / 越界 → []。"""
    rng = dialogue_summary_excerpt_half_open_for_messages(
        messages, full_user_rounds, pure_user_rounds
    )
    if not rng:
        return []
    s, e = int(rng[0]), int(rng[1])
    if s >= e or s >= len(messages):
        return []
    e = min(e, len(messages))
    return flat_messages_to_user_rounds(messages[s:e])


class ContextSources:
    """上下文注入源注册表（扩展点）。

    每个来源 fn(conversation_id) -> List[str]（系统文本列表，每条独立成消息）；
    collect 按注册顺序串接，单个来源异常被隔离（记录 stderr），不影响其他来源与请求。
    """

    def __init__(self) -> None:
        self._sources: List[Callable[[str], List[str]]] = []
        self._lock = threading.Lock()

    def add(self, fn: Callable[[str], List[str]]) -> Callable[[], None]:
        """注册来源；返回幂等 disposer。"""
        if not callable(fn):
            raise ValueError("上下文来源必须可调用")
        with self._lock:
            self._sources.append(fn)

        def _dispose() -> None:
            with self._lock:
                if fn in self._sources:
                    self._sources.remove(fn)

        return _dispose

    def collect(self, conversation_id: str) -> List[str]:
        """收集全部来源的系统文本（顺序串接；异常隔离）。"""
        with self._lock:
            sources = list(self._sources)
        out: List[str] = []
        for fn in sources:
            try:
                parts = fn(conversation_id)
            except Exception as exc:
                print(
                    f"[context_sources] 来源异常（已隔离）: {type(exc).__name__}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
                continue
            for text in parts or []:
                t = str(text or "").strip()
                if t:
                    out.append(t)
        return out


class ContextPipeline:
    """会话级七块上下文管线（摘要生成由外部执行）。"""

    def __init__(
        self,
        conversation_id: str = "",
        *,
        pure_user_rounds: int = DEFAULT_PURE_USER_ROUNDS,
        full_user_rounds: int = DEFAULT_FULL_USER_ROUNDS,
        summary_token_threshold: int = DEFAULT_SUMMARY_TOKEN_THRESHOLD,
        sources: Optional["ContextSources"] = None,
    ) -> None:
        self.conversation_id = str(conversation_id or "")
        self.pure_user_rounds = max(0, int(pure_user_rounds))
        self.full_user_rounds = max(1, int(full_user_rounds))
        self.summary_token_threshold = max(1, int(summary_token_threshold))
        self._sources = sources
        self.chunks: List[ContextChunk] = []
        self.name_map: Dict[str, ContextChunk] = {}
        for nm in CHUNK_ORDER:
            c = ContextChunk(nm)
            self.chunks.append(c)
            self.name_map[nm] = c
        self.pending_mem_file_path: Optional[str] = None
        self.pending_over_rounds: Optional[List[Round]] = None

    # ── 结构──────────────────────────────────────

    def layout_payload(
        self,
        *,
        budget_tokens: int = 0,
        model_max_context_tokens: int = 0,
        token_fn: Optional[Callable[[Dict[str, Any]], int]] = None,
    ) -> Dict[str, Any]:
        """上下文分段快照。

        产出量纲一致：每段 `{key, label, tokens, pct, count?}`，末尾补
        `剩余容量`；`pct` 相对**预算**（取预算与已用中的较大者，保证各段之和不超过 100%）。
        key 用稳定的英文标识（`system` / `skill` / `knowledge` / `summary` / `pure` /
        `full_recent` / `mode`），label 用七块中文名——前端据此画上下文条与浮层。
        """
        counter = token_fn or default_message_tokens
        keys = ("system", "skill", "knowledge", "summary", "pure", "full_recent", "mode")
        rows: List[Dict[str, Any]] = []
        total = 0
        for key, chunk in zip(keys, self.chunks):
            tokens = int(chunk.calculate_tokens(counter))
            total += tokens
            rows.append({
                "key": key,
                "label": chunk.name,
                "tokens": tokens,
                "count": len(chunk.rounds),
            })
        budget = max(int(budget_tokens or 0), total, 1)
        remainder = max(0, budget - total)
        segments: List[Dict[str, Any]] = []
        for row in rows:
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
            "model_max_context_tokens": int(model_max_context_tokens or 0),
        }

    def add(self, chunk: ContextChunk) -> None:
        """扩展点：追加自定义块（默认七块之后；参与展平与统计）。"""
        self.chunks.append(chunk)
        self.name_map[chunk.name] = chunk

    # ── 内容装配──────────────────────────

    def append_system(self, text: str) -> None:
        """追加系统段（每段独立成轮）。"""
        self.name_map[CHUNK_SYSTEM].append("system", text, True)

    def system_text(self) -> str:
        """当前系统段全文（各段以空行相连）。

        模型否认看到图片时的最小上下文重试＝本方法结果 + 当前那条用户消息 ——
        最小上下文 = 这份系统提示 + 当前那条用户消息。
        """
        try:
            chunk = self.name_map[CHUNK_SYSTEM]
        except (KeyError, AttributeError):
            return ""
        parts: List[str] = []
        for rnd in getattr(chunk, "rounds", []) or []:
            for m in getattr(rnd, "messages", []) or []:
                if str(m.get("role") or "") == "system":
                    text = str(m.get("content") or "").strip()
                    if text:
                        parts.append(text)
        return "\n\n".join(parts)

    def append_skill(self, text: str) -> None:
        """追加 Skills 段（每段独立成轮）。"""
        self.name_map[CHUNK_SKILL].append("system", text, True)

    def append_kb(self, text: str) -> None:
        """追加知识库段（每段独立成轮）。"""
        self.name_map[CHUNK_KB].append("system", text, True)

    def set_kb(self, parts: List[str]) -> None:
        """整体设置知识库段（清空重建；空列表清空）。"""
        chunk = self.name_map[CHUNK_KB]
        chunk.rounds = []
        for text in parts:
            t = str(text or "").strip()
            if t:
                chunk.append("system", t, True)

    def set_summaries(self, summaries: List[Dict[str, Any]]) -> None:
        """设置摘要（记忆块；逐条独立成轮，深拷贝）。"""
        chunk = self.name_map[CHUNK_MEM]
        chunk.rounds = []
        for sm in summaries:
            r = Round()
            r.append_message_dict(copy.deepcopy(dict(sm)))
            chunk.rounds.append(r)

    def set_pure_rounds(self, rounds: List[Round]) -> None:
        """设置「远期记忆」块（深拷贝）。"""
        self.name_map[CHUNK_PURE].rounds = copy_round_list(rounds, 0, len(rounds))

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
        """用扁平消息重建「近期记忆」块（按时序切轮）。"""
        self.name_map[CHUNK_FULL].rounds = flat_messages_to_user_rounds(list(flat_messages))
        self._refresh_sources()

    def _refresh_sources(self) -> None:
        """从注入源刷新知识库块（无来源时不动）。"""
        if self._sources is None:
            return
        self.set_kb(self._sources.collect(self.conversation_id))

    # ── 展平──────────────────────────────────────

    def flatten_to_messages(
        self,
        sanitize_fn: Optional[Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]]] = None,
    ) -> List[Dict[str, Any]]:
        """按七块顺序展平（空块跳过；深拷贝；末端统一过 sanitize_fn）。"""
        built: List[Dict[str, Any]] = []
        for chunk in self.chunks:
            for r in chunk.rounds:
                for m in r.messages:
                    built.append(copy.deepcopy(m))
        if sanitize_fn is not None:
            built = sanitize_fn(built)
        return built

    # ── 窗口与摘要调度────────────────────

    def extract_over_rounds(self) -> List[Round]:
        """按 pure+full 窗口取应摘要的越界轮（深拷贝）。"""
        pure = self.name_map[CHUNK_PURE]
        full = self.name_map[CHUNK_FULL]
        window = self.pure_user_rounds + self.full_user_rounds
        pure_size = len(pure.rounds)
        full_size = len(full.rounds)
        over: List[Round] = []
        if full_size > window:
            over.extend(copy_round_list(pure.rounds, 0, pure_size))
            over.extend(copy_round_list(full.rounds, 0, full_size - window))
            return over
        if full_size == window:
            over.extend(copy_round_list(pure.rounds, 0, pure_size))
            return over
        if full_size < window:
            excess = full_size + pure_size - window
            if excess > 0:
                over.extend(copy_round_list(pure.rounds, 0, excess))
                return over
        return over

    def dialogue_summary_excerpt_half_open(
        self, messages: List[Dict[str, Any]]
    ) -> Optional[Tuple[int, int]]:
        """在扁平 transcript 上计算摘要半开区间。"""
        return dialogue_summary_excerpt_half_open_for_messages(
            messages, self.full_user_rounds, self.pure_user_rounds
        )

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
