# -*- coding: utf-8 -*-
"""上下文压缩器 — 拼入前预算检查 + 同步摘要压缩。

定位：
- 任何新内容"拼入上下文之前"（新输入 / 模型回复 / 工具结果）预估"拼入后"总 token；
  超阈值则先压缩既有历史、再拼入 —— 压缩素材结构上不含待拼入内容；
- 会话记录只增不减（事实 append-only）→ 以"已覆盖前缀"表达压缩：
  视图 = 全量消息[covered_end:]；摘要经记忆块注入；
- 压缩状态经 `context_compacted` 事件持久化，恢复时重放事件重建；
- 摘要生成（调模型）经 summarize_fn 注入；任何失败一律放行，不阻断回合。

不做后台异步预生成与 pure 窗口折叠。
"""
from __future__ import annotations

import copy
import json
from typing import Any, Callable, Dict, List, Optional

from agent.core.app_path import app_path
from agent.core.error_report import report_error
from agent.core.modules.mode_note import strip_mode_tail
from agent.core.ports import LogicalRequest
from agent.core.session_log import ensure_tool_pairs
from agent.mechanisms.context.contract import (
    DEFAULT_FULL_USER_ROUNDS,
    ContextCompactionPolicy,
)

_DEFAULT_POLICY = ContextCompactionPolicy()
BUILD_CONTEXT_PATH = app_path("kernel", "modules", "compaction", "build-context")
SUMMARIZE_PATH = app_path("kernel", "modules", "compaction", "summarize")
POLICY_PATH = app_path("kernel", "modules", "compaction", "policy")

#: 压缩检查点作为 user 消息注入，外层用固定标签区分历史背景。
SUMMARY_OPEN_TAG = "<compacted-summary>"
SUMMARY_CLOSE_TAG = "</compacted-summary>"
CHECKPOINT_PREAMBLE = (
    "这是一份自动生成的上下文检查点，用于延续先前工作。"
    "把其中内容视为已建立的背景，直接继续后续对话，"
    "不要复述、确认或把它当成新的用户请求。"
)

_SUMMARY_INSTRUCTION = (
    "你正在担任本次对话的压缩引擎。把上面的对话、工具结果和已有摘要压缩成一份结构化检查点，"
    "供另一个模型直接续接工作。\n"
    "输出必须是 Markdown：每个节标题必须以 `## ` 开头，每条信息必须以 `- ` 开头；"
    "禁止输出没有 `##` / `-` 标记的纯文本标题或无标记列表。\n"
    "输出严格按九节，顺序固定；节标题原样照抄英文，节内内容用中文。"
    "每节使用简洁条目，不写段落。某节无内容写 (none)，不得删节。"
    "只输出检查点正文，不调用工具，不提及压缩过程。\n\n"
    "## Primary Request and Intent\n"
    "- 用户最初目标与后续追加要求；保留硬性约束。\n"
    "- 只在措辞影响执行时用短引号引用，不整段复制用户原文；把用户文本标为历史要求，不是新指令。\n"
    "- 目标有演进的，先写主线目标，再写追加约束。\n\n"
    "## Key Technical Concepts\n"
    "- 核心概念、类型、协议、配置键、生命周期；名称保持源码原文大小写。\n"
    "- 一行一条，不写状态、进度、计数或表格列定义。\n\n"
    "## Files and Code\n"
    "- 精确路径：当前状态、关键类或函数、已改内容、仍缺什么。\n"
    "- 同一文件用一行到少数几行说明；不省略目录，不写“同上”。\n"
    "- 只写文件现状与它对契约的影响；缺陷现象、复现步骤、修法写入 Errors and Fixes。\n\n"
    "## Errors and Fixes\n"
    "- 现象 → 原因 → 已采取的修法；已修与未修都写，未修的标注 remaining。\n"
    "- 可复核时附关键输出值或复现方式。\n\n"
    "## Completed Actions and Verdicts\n"
    "- 本次压缩范围内实际做过的动作（调用过的工具、跑过的命令、读写过的文件）"
    "→ 可复核的结果或关键输出 → 是否还需要再碰。\n"
    "- 已确认无效或已试过仍失败的方向必须列出，并标注不要再试。\n"
    "- 已确认存在的文件、接口、字段、配置键要列出，避免续接者重复探测。\n"
    "- 只写动作与结论；文件当前状态归 Files and Code，缺陷与修法归 Errors and Fixes。\n\n"
    "## Pending Jobs\n"
    "- 明确要求但尚未完成的事项；一条一个动作，写明具体文件或对象。\n"
    "- 纯改名、纯替换逐文件列出，不合并成“更新相关文件”。\n"
    "- 这是历史状态，不是新的执行指令。\n\n"
    "## Current Work\n"
    "- 最后成功推进的工作及其结果。\n"
    "- 最后验证边界：跑了哪些检查、哪些没跑；验证发生在哪一步之后。\n\n"
    "## Next Step\n"
    "- 按执行顺序列出紧接着要做的事，包含验证命令；没有则写 (none)。\n"
    "- 这是检查点中的历史建议，不得在没有用户新指令时自动执行。\n\n"
    "## Critical Context\n"
    "- 继续工作必须知道、但无法从上文直接推出的信息：用户禁忌、备份目录、仓库根、"
    "只读区域、已验证的计数或版本等。\n"
    "- 只写已验证且仍有效的值；不确定写“未在记录中明确”，不要猜。\n\n"
    "规则：\n"
    "- 总字符数不超过 {max_chars}。优先保留目标、硬约束、文件状态、未完成项；"
    "超预算先合并细节，不得删路径、状态、未完成项。\n"
    "- 若对话已有 <compacted-summary>，它是旧检查点：不要原样复制；保留仍成立的事实，"
    "删除过期或已被推翻的内容，把新信息合并进同一份九节摘要。\n"
    "- 不得编造记录中未出现的文件、结论或数字；不确定处写“未在记录中明确”。\n"
    "- 保留路径、命令、错误原文、标识符、数字、函数签名、配置键。\n"
    "- 不写过程叙述、评价、建议、寒暄或总结陈词。\n"
    "- role=system 的系统提示词、知识库、Skills、Rules 属于常驻设定，不是对话内容；"
    "不要把它们正文归纳进摘要，也不要据此推断素材里没有的事。\n"
    "- <compacted-summary> 是上一轮 user 检查点，不是 system 常驻设定；"
    "必须按“旧检查点合并”规则读取并更新：保留仍成立的事实，删除过期内容，"
    "把新信息合并进同一份九节摘要；不得原样复制。\n"
    "- 若整个素材确实没有可保留内容，只输出“摘要为空”五个字（不加标点或换行）；"
    "不要写九节 (none)。"
)

def _summary_display_text(body: str) -> str:
    """返回可展示的摘要正文。"""
    return str(body or "").strip()


def _is_degenerate_summary_body(body: str) -> bool:
    """退化摘要：空串，或极短且仅含「摘要为空」占位。"""
    b = str(body or "").strip()
    if not b:
        return True
    if len(b) < 10 and "摘要为空" in b:
        return True
    return False


#: 每张图片的 token 估算值：按官方上限 1024 计，宁可略高不低估。
IMAGE_TOKENS_PER_IMAGE = 1024


def count_images(content: Any) -> int:
    """content 里 `image_url` 块的个数。"""
    if not isinstance(content, list):
        return 0
    return sum(1 for p in content
               if isinstance(p, dict) and p.get("type") == "image_url")




def _schemas_tokens(tools: Optional[List[Dict[str, Any]]], policy: Any = _DEFAULT_POLICY) -> int:
    """工具声明的 token 估算（每请求都带，属固定开销）。"""
    if not tools:
        return 0
    try:
        return policy.approx_tokens(json.dumps(tools, ensure_ascii=False))
    except (TypeError, ValueError):
        return 0


def _mode_note_tokens(mode_note: str, policy: Any = _DEFAULT_POLICY) -> int:
    """尾部执行模式说明的 token 估算（也算进请求体）。"""
    return policy.approx_tokens(mode_note)


def _material_messages(prefix: Optional[List[Dict[str, Any]]],
                       material: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """不复用前缀时的素材消息：把要压的正文按角色拼成可读文本。

    `material` 是调用方给的"要压的那一段"（没给就退回前缀本身）——
    这时不与平常请求共用前缀，所以只带要压的正文，不带整份上下文。
    """
    rows = material if material else prefix
    if not rows:
        return []
    lines: List[str] = []
    for msg in rows:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role") or "")
        body = msg.get("content")
        if not isinstance(body, str):
            try:
                body = json.dumps(body, ensure_ascii=False)
            except (TypeError, ValueError):
                body = str(body)
        calls = msg.get("tool_calls")
        if isinstance(calls, list) and calls:
            try:
                body = f"{body}\n[工具调用] {json.dumps(calls, ensure_ascii=False)}"
            except (TypeError, ValueError) as exc:
                report_error("agent.mechanisms.compaction.compactor._material_messages", exc)
        reasoning = msg.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning:
            body = f"[推理] {reasoning}\n{body}"
        lines.append(f"### {role}\n{body}")
    text = "\n\n".join(lines)
    if not text:
        return []
    return [{"role": "user", "content": "【待压缩的对话】\n" + text}]


def _prefix_before_material(
    prefix: Optional[List[Dict[str, Any]]],
    material: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """返回正常请求中紧邻可压缩素材前的头部。

    素材在正常请求里可能只是中间一段。摘要请求只保留素材及其前缀，
    因而不会把素材后仍需原文保留的最近轮次送进摘要模型。
    """
    rows = list(prefix or [])
    body = list(material or [])
    if not rows or not body or len(body) > len(rows):
        return []
    width = len(body)
    for index in range(len(rows) - width + 1):
        if rows[index:index + width] == body:
            return rows[:index]
    return []


def make_provider_summarizer(
    provider: Any,
    *,
    max_chars: int = 2000,
    prefix_reuse: bool = True,
) -> Callable[..., str]:
    """构造基于模型 provider 的摘要生成函数。

    返回 fn(prefix, tools, system) -> str。摘要请求只包含可压缩区间及其前缀：

        摘要请求  系统提示词 + 插件各段 + 旧摘要 + 可压缩对话 + 压缩指令

    `prefix` 是正常请求中紧邻可压缩素材前的头部，`material` 只含本次要压掉的
    消息；两者拼接后与正常请求的开头逐字节一致，可继续命中 provider 的 KV 缓存，
    同时不会把需要原文保留的最近轮次送给摘要模型。`prefix_reuse=False` 时
    只把素材展平成一条请求，不依赖正常请求前缀。

    生成异常 / 空文本 → 返回空串（由调用方按失败放行处理）。
    """

    def _summarize(
        prefix: Optional[List[Dict[str, Any]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        system: str = "",
        material: Optional[List[Dict[str, Any]]] = None,
        **_ignored: Any,
    ) -> str:
        if provider is None:
            return ""
        instruction = _SUMMARY_INSTRUCTION.format(max_chars=max(1, int(max_chars)))
        if prefix_reuse:
            head = copy.deepcopy(list(prefix or []))
            head.extend(copy.deepcopy(list(material or [])))
        else:
            # 不复用正常请求时把素材展平；请求只包含这次要压掉的内容。
            head = _material_messages(prefix, material)
        tail = instruction
        request = LogicalRequest(
            # 与平常请求走同一个补齐函数：压缩可能落在"工具调用已发出、结果还没
            # 回来"的中间态（例如某个调用在等用户确认），此时历史里
            # `assistant(tool_calls)` 是悬空的。模型 API 对悬空调用硬拒绝
            # （400：must be followed by tool messages）。
            # 两边补法一致，前缀逐字节相同不受影响。
            messages=ensure_tool_pairs(head + [{"role": "user", "content": tail}]),
            # 工具定义照平常请求带上（前缀的一部分，少一项整段缓存作废）。
            tools=list(tools or []) if prefix_reuse else [],
        )
        parts: List[str] = []
        try:
            for delta in provider.stream(request):
                if getattr(delta, "kind", "") == "text":
                    parts.append(str(getattr(delta, "text", "") or ""))
        except Exception as exc:
            report_error("agent.mechanisms.compaction.compactor._summarize", exc)
            return ""
        return "".join(parts).strip()

    return _summarize


class ContextCompactor:
    """会话级上下文压缩器：拼入前预算检查 + 已覆盖前缀视图。"""

    def __init__(
        self,
        summarize_fn: Optional[Callable[..., str]] = None,
        *,
        summary_token_threshold: int = 64000,
        full_user_rounds: int = DEFAULT_FULL_USER_ROUNDS,
        policy: Optional[ContextCompactionPolicy] = None,
        slots: Any = None,
    ) -> None:
        self._summarize_fn = summarize_fn
        self._slots = slots
        self.summary_token_threshold = max(1, int(summary_token_threshold))
        self.covered_end = 0
        self.loaded_prefix = 0
        #: 单一当前摘要；历次压缩只更新这一条。
        self.summary: str = ""
        #: 上一次正常请求的精确前缀快照（不含尾部注入）。
        self._sent_prefix: Optional[List[Dict[str, Any]]] = None
        self._sent_tools: Optional[List[Dict[str, Any]]] = None
        #: 配置要求优先保留的最近用户轮数。前面没有可压内容时逐级减到 1；
        #: 最低保留一轮，不能把整个近场压成摘要。
        self.full_user_rounds = max(1, int(full_user_rounds))
        self._policy = policy or ContextCompactionPolicy(
            full_user_rounds=self.full_user_rounds,
        )
        if self._slots is not None:
            # Slots are shared by every per-session compactor.  Only reserve
            # the paths here; never install a default that captures this
            # instance.  Per-instance policy/summarizer stay local unless a
            # plugin explicitly replaces the slot.
            for path in (BUILD_CONTEXT_PATH, SUMMARIZE_PATH, POLICY_PATH):
                if path not in self._slots.nodes:
                    self._slots.register_slot(
                        path, kind="kernel-stage", default=None,
                        default_owner="__host__")

    def _slot_bound(self, path: str) -> bool:
        if self._slots is None:
            return False
        try:
            return bool(self._slots.bindings_of(path))
        except Exception as exc:
            report_error("agent.mechanisms.compaction.compactor._slot_bound", exc)
            return False

    @staticmethod
    def _build_context_default(messages: Any, mode_note: str = "") -> List[Dict[str, Any]]:
        base = ContextCompactor._context_without_new_input(list(messages))
        return strip_mode_tail(base, mode_note)

    def build_context(self, messages: Any, mode_note: str = "") -> List[Dict[str, Any]]:
        if self._slot_bound(BUILD_CONTEXT_PATH):
            builder = self._slots.resolve(BUILD_CONTEXT_PATH)
            return builder(list(messages), mode_note)
        return self._build_context_default(messages, mode_note)

    def _message_tokens(self, message: Optional[Dict[str, Any]]) -> int:
        return self._policy_view().message_tokens(message)

    def _policy_view(self) -> Any:
        if self._slot_bound(POLICY_PATH):
            return self._slots.resolve(POLICY_PATH)
        return self._policy

    def _summarize_text(self, base: List[Dict[str, Any]], tools: Any,
                        system: str, material: List[Dict[str, Any]]) -> str:
        if self._slot_bound(SUMMARIZE_PATH):
            impl = self._slots.resolve(SUMMARIZE_PATH)
            return str(impl(base, tools, system, material=list(material)) or "").strip()
        return "" if self._summarize_fn is None else str(
            self._summarize_fn(base, tools, system, material=list(material)) or "").strip()

    # ── 恢复────────────────────────────────

    def restore_from_events(self, events: Any) -> None:
        """从会话记录重放 `context_compacted` 事件重建状态（幂等；covered_end 单调不减）。"""
        covered = 0
        summary = ""
        for e in events or []:
            if getattr(e, "type", "") != "context_compacted":
                continue
            data = getattr(e, "data", None) or {}
            try:
                c = int(data.get("covered_end") or 0)
            except (TypeError, ValueError) as exc:
                report_error("agent.mechanisms.compaction.compactor.ContextCompactor.restore_from_events", exc)
                continue
            if c < covered:
                continue
            covered = c
            text = str(data.get("summary") or "").strip()
            if text:
                summary = text
        self.covered_end = covered
        self.summary = summary

    # ── 视图与注入──────────────────────────

    @property
    def view_start(self) -> int:
        return max(0, self.covered_end - self.loaded_prefix)

    def view_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """未覆盖视图：全量消息去除已覆盖前缀。"""
        return list(messages[self.view_start :])

    def summary_messages(self) -> List[Dict[str, Any]]:
        """摘要作为单条 user 检查点注入；历史摘要不重复成多条。"""
        if not self.summary:
            return []
        return [{
            "role": "user",
            "content": (
                CHECKPOINT_PREAMBLE + "\n\n"
                + SUMMARY_OPEN_TAG + "\n" + self.summary + "\n" + SUMMARY_CLOSE_TAG
            ),
        }]

    def remember_sent_request(self, messages: List[Dict[str, Any]],
                              cache_prefix: List[Dict[str, Any]],
                              tools: Optional[List[Dict[str, Any]]]) -> None:
        """记录上一次正常请求的精确前缀；只作 KV 缓存提示，不作为业务事实。"""
        self._sent_prefix = copy.deepcopy(list(cache_prefix or []))
        self._sent_tools = copy.deepcopy(list(tools or []))

    def sent_prefix(self) -> Optional[List[Dict[str, Any]]]:
        if self._sent_prefix is None:
            return None
        return copy.deepcopy(self._sent_prefix)

    def sent_tools(self) -> Optional[List[Dict[str, Any]]]:
        if self._sent_tools is None:
            return None
        return copy.deepcopy(self._sent_tools)

    # ── 拼入前检查────────────────────

    def _excerpt_range(self, view: List[Dict[str, Any]], context: Any):
        policy = self._policy_view()
        rng = policy.excerpt(view, token_fn=context.message_tokens)
        if not rng:
            return None
        start, end = int(rng[0]), min(int(rng[1]), len(view))
        if end <= 0:
            return None
        start = policy.floor(view, start)
        if not policy.balanced(view, start, end):
            return None
        return start, end

    def _summary_body(self, base: List[Dict[str, Any]],
                      material: List[Dict[str, Any]],
                      context: Any, tools: Any) -> str:
        system = ""
        if hasattr(context, "system_text"):
            system = str(context.system_text() or "")
        text = self._summarize_text(base, tools, system, material)
        if _is_degenerate_summary_body(text):
            return ""
        return text

    def ensure_before_append(
        self,
        context: Any,
        messages: List[Dict[str, Any]],
        pending: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        mode_note: str = "",
        assembled: Optional[List[Dict[str, Any]]] = None,
        reasoning_budget: int | None = None,
    ) -> Optional[Dict[str, Any]]:
        """拼入前预算检查：超阈值先压缩既有历史；失败放行。"""
        try:
            if context is None:
                return None
            view = self.view_messages(messages)
            if not view or not assembled:
                return None
            base = self.sent_prefix()
            if base is None:
                # 没有快照时只能重建；压缩仍可进行，但不能声称缓存命中。
                base = self.build_context(list(assembled), mode_note)
            if not base:
                return None
            pending_tokens = self._message_tokens(pending)
            context.set_summary_messages(self.summary_messages())
            options = {} if reasoning_budget is None else {"reasoning_budget": reasoning_budget}
            context.set_dialogue(view, **options)
            dialogue_messages = getattr(context, "dialogue_messages", None)
            if callable(dialogue_messages):
                view = dialogue_messages()
            policy = self._policy_view()
            overhead = _schemas_tokens(tools, policy) + _mode_note_tokens(mode_note, policy)
            estimate = context.total_token_estimate() + pending_tokens + overhead
            if estimate <= self.summary_token_threshold:
                return None
            rng = self._excerpt_range(view, context)
            if rng is None:
                return None
            start, end = rng
            material = list(view[start:end])
            summary_prefix = _prefix_before_material(base, material)
            if not summary_prefix:
                host_messages = getattr(context, "host_messages", None)
                summary_prefix = list(host_messages()) if callable(host_messages) else []
            summary_tools = self.sent_tools()
            if summary_tools is None:
                summary_tools = list(tools or [])
            body = self._summary_body(summary_prefix, material, context, summary_tools)
            if not body:
                return None
            self.covered_end += end
            self.summary = body
            if hasattr(context, "set_summary_messages"):
                context.set_summary_messages(self.summary_messages())
            return {
                "covered_end": self.covered_end,
                "summary": body,
                "summary_text": _summary_display_text(body),
                "compressed_count": len(material),
                "compressed_tokens": sum(
                    self._message_tokens(message) for message in material
                ),
            }
        except Exception as exc:
            report_error("agent.mechanisms.compaction.compactor.ensure_before_append", exc)
            return None

    @staticmethod
    def _context_without_new_input(messages: Any) -> List[Dict[str, Any]]:
        """已拼好的上下文，去掉本回合新输入。

        会话里维护的上下文长这样（`ModelModule` 拼好的那一份）::

            上一回合上下文 + [本回合新输入] + [执行模式]
            上一回合上下文 = [系统提示][插件段-*][摘要-*][第y轮][回复]…[上一回合输入]
                        （不含本回合新输入、不含执行模式）

        判据：先看当前回合由什么触发（跳过尾部连续的 `system` 之后看那一条）——

        - `tool`：当前是工具调用，触发者是工具结果 —— 整份都算上下文
          （含当前回合那条提问，以及本回合的工具调用与结果），什么都不删；
        - `user`：这就是本回合新输入，删掉它；尾部连续的 `system`
          （执行模式之类的附加说明）也一并删掉 —— 它属于"平常请求"，不属于"上一回合上下文"；
        - `assistant`：当前回合已产出回复、也没有新输入，整份返回。

        调用方随后用压缩结果重拼：`zip + 本回合新输入 + 执行模式`。
        """
        msgs = list(messages or [])
        if not msgs:
            return msgs
        i = len(msgs) - 1
        while i >= 0 and isinstance(msgs[i], dict) \
                and str(msgs[i].get("role") or "") == "system":
            i -= 1
        if i < 0:
            return msgs
        if not isinstance(msgs[i], dict):
            return msgs
        if str(msgs[i].get("role") or "") != "user":
            # 工具调用 / 已回复：没有"本回合新输入"可删。
            return msgs
        out = msgs[:i] + msgs[i + 1:]
        # 新输入后面的尾部 system（执行模式之类）也不属于上一回合上下文，一并去掉。
        while out:
            last = out[-1]
            if isinstance(last, dict) and str(last.get("role") or "") == "system":
                out.pop()
                continue
            break
        return out
