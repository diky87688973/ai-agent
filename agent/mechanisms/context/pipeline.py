# -*- coding: utf-8 -*-
"""上下文管线装配。"""
from __future__ import annotations

import copy
from typing import Any, Callable, Dict, List, Optional, Tuple

from agent.mechanisms.context.constants import SEGMENT_LABELS as SEGMENT_LABELS_DEFAULT
from agent.mechanisms.context.contract import DEFAULT_FULL_USER_ROUNDS
from agent.mechanisms.context.layout import (
    as_text_parts,
    clip_reasoning,
    merge_segment_rows,
)
from agent.mechanisms.context.rounds import (
    ContextChunk,
    Round,
    flat_messages_to_user_rounds,
)
from agent.mechanisms.context.sources import (
    ContextSources,
    PluginSegments,
    slug,
)
from agent.mechanisms.context.tokens import default_message_tokens

CHUNK_SYSTEM = "系统提示词"
CHUNK_PLUGIN = "插件段落"
CHUNK_MEM = "记忆文件"
CHUNK_FULL = "近期记忆"
CHUNK_MODE = "模式"
CHUNK_ORDER = (CHUNK_SYSTEM, CHUNK_PLUGIN, CHUNK_MEM, CHUNK_FULL, CHUNK_MODE)

#: 思维链回传预算默认值（token）：超出取两头、中间以省略标记代替。
DEFAULT_REASONING_REPLAY_TOKENS = 8000

DEFAULT_SUMMARY_TOKEN_THRESHOLD = 64000
#: 最近这么多用户轮保留完整工具往返；更早的轮剥掉轮内工具往返。
#: 压缩时保留的最近用户轮数（0 = 允许压到 0 个用户轮）。
#: 剥掉工具往返的轮补的标注：不补的话模型会以为这些轮没调用过工具。


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
        #: 最近这么多用户轮原样保留（含工具往返）；更早的轮剥掉轮内工具往返。
        #: 负数 = 不剥（全部保留）。
        self._sources = sources
        # 插件段落：`[(段 key, 段名)]`；有正文的段才与 CHUNK_PLUGIN 消息对齐。
        self._plugin_sources: List[Tuple[str, str]] = []
        # 插件自报的主体数量，按段的位置对应（缺省时段落行按消息条数算）。
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
    SEGMENT_LABELS = SEGMENT_LABELS_DEFAULT

    def segment_tokens(
        self,
        *,
        token_fn: Optional[Callable[[Dict[str, Any]], int]] = None,
    ) -> List[Dict[str, Any]]:
        """按当前装配逐段统计 token：系统提示词 + 插件各段 + 记忆摘要 + 对话。

        口径与真正发出去的请求一致（同一个 `default_message_tokens`）。
        插件各段一段一条，key 是 `plugin:<插件名>`、段名与数量由插件给 ——
        内核不认识知识库、Skills 这些具体名字。

        模式不在管线里 —— 它是请求尾部的临时后缀，由调用方单独算。

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
        # 段顺序逐条对齐装配顺序：系统提示词 → 插件各段 → 记忆摘要 → 近期记忆。
        # 前端就按这个顺序画，所以不能为了方便把摘要挪到末尾。
        head = [rows[0]] if rows else []
        tail = [r for r in rows[1:] if r["key"] == "full_recent"]
        summary = [r for r in rows[1:] if r["key"] != "full_recent"]
        return head + self._plugin_rows(counter) + summary + tail

    def _plugin_rows(
        self, counter: Callable[[Dict[str, Any]], int],
    ) -> List[Dict[str, Any]]:
        """插件贡献的段落：一段一条，key 用插件来源声明的名字。

        消息与段落按顺序对齐：`set_plugin_segments` 保证每条消息各成一轮、
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
            # 自报数量按位置对来源：数量表比来源表长说明两者已经错位，
            # 此时宁可退回"按消息条数"（1），也不要拿别人的数量去贴自己的段。
            reported = counts[i] if i < len(counts) else None
            rows.append({
                "key": f"plugin:{key}",
                "label": label,
                "tokens": int(counter(msg)) if msg is not None else 0,
                "count": (1 if msg is not None else 0) if reported is None else int(reported),
            })
        return merge_segment_rows(rows)

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
        `pct` 相对预算（取预算与已用中的较大者，保证各段之和不超过 100%）。

        `tail_messages` 是请求尾部的临时后缀（本回合新输入 / 工具结果 / 执行模式），
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
    # 发给模型的 messages 只有三段，顺序拼接，不做任何重建：
    #
    #   ① 头部（host）  系统提示 / Skills / 知识库 / 摘要 —— 本回合内逐字节稳定
    #   ② 对话（dialogue） 事实折叠出来的对话（含工具调用与工具结果）
    #   ③ 尾部（tail）  本回合新输入 / 工具结果 + 执行模式 —— 请求时才拼
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
        在这里裁而不是在线上裁：分段统计与预算估算看的是同一份，
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
        """装摘要段（属头部①）。每次压缩后调用一次，装的是全部摘要。"""
        chunk = self.name_map[CHUNK_MEM]
        chunk.rounds = []
        for sm in summaries or []:
            if not isinstance(sm, dict):
                continue
            r = Round()
            r.append_message_dict(copy.deepcopy(dict(sm)))
            chunk.rounds.append(r)

    def plugin_segments(self) -> List[Tuple[str, str, int]]:
        """当前插件段落的 `[(段 key, 段名, 主体数量)]`。

        同一插件可发多条消息；同 key+label 的消息在视图里合并为一段，
        count 取该来源第一条的自报数，避免把后续消息的默认 1 相加。
        """
        out: List[Tuple[str, str, int]] = []
        seen = set()
        for i, (key, label) in enumerate(self._plugin_sources):
            group = (key, label)
            if group in seen:
                continue
            seen.add(group)
            count = int(self._plugin_counts[i]) if i < len(self._plugin_counts) else 0
            out.append((key, label, count))
        return out

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
        """三段拼接：头部 + 对话 + 尾部。唯一装配入口，无重建。"""
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

        `text` 可能是列表（注入源常按"条目"给），必须归一成字符串正文 ——
        直接把列表塞进 `content` 会让模型收到 Python 字面量
        （`['条目一']`），而不是条目本身。
        """
        for part in as_text_parts(text):
            if not str(part).strip():
                continue
            self.name_map[CHUNK_PLUGIN].append("system", part, True)
            self._plugin_sources.append((key or slug(label), label or key))
            self._plugin_has_body.append(True)

    def set_plugin_segments(self, segments: Any) -> None:
        """整体设置插件段落（清空重建；空列表清空）。

        收 `PluginSegments`（段落表 + 数量表）；也接受裸的 `[(key, 段名, 正文)]`。
        顺序即装配顺序，每条正文各成一轮，所以统计时能按顺序逐段对上。
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
            parts = [p for p in as_text_parts(text) if str(p).strip()]
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

        保留旧名只为不打断既有调用方；内部不再"按 role 重建" ——
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
        """从注入源刷新知识库与 Skills 块（无来源时不动）。

        Skills 也走注入源：Skills 库注册「可用 Skills 清单」（渐进式披露第一层）
        与 `auto_load/` 常驻 Skills 正文（第二层）。

        一趟链只收集一次：压缩模块、压缩器内部、模型模块会各装一次对话。
        每次收集都要重列 Skills 目录、重读全部勾选文件。同一趟里收集两遍不只是
        重复读盘 —— 两遍之间源可变，于是"压缩看到的那份"和"发出去的那份"
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
