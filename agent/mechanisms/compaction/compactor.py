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

import json
import sys
from typing import Any, Callable, Dict, List, Optional

from agent.core.error_report import report_error
from agent.core.mode_marker import MODE_MARKER
from agent.core.ports import LogicalRequest
from agent.core.session_log import ensure_tool_pairs
from agent.mechanisms.context.contract import (
    DEFAULT_FULL_USER_ROUNDS,
    ContextCompactionPolicy,
)

_DEFAULT_POLICY = ContextCompactionPolicy()

#: 摘要桥接后缀：接在摘要正文之后，向模型标明上文是历史摘要、下文续当前对话。
SUMMARY_BRIDGE_TAIL = "\n\n【以上为历史摘要，下面继续当前对话】"

_SUMMARY_INSTRUCTION = (
    "把上面这段对话压缩成一份摘要，供另一个模型接着干，关键上下文不能丢。\n"
    "1) 识别对话场景（如开发、排障、写文档、数据分析等），按场景保留高价值信息。\n"
    "2) 降噪：去掉寒暄与无信息套话；多处矛盾时以用户最终意图与最后澄清为准；重复尝试可合并为一句。\n"
    "3) 事实粒度：保留可执行信息——路径、命令、版本号、明确数字、用户硬性约束（必须/禁止等）。\n"
    "4) 未完成：单独列出仍待处理或待用户确认的事项；已放弃的方案一句话带过即可。\n"
    "5) 输出：纯文本中文；建议分节（背景 / 关键结论 / 约束与约定 / 未完成与待确认 / 风险与注意点）；"
    "总篇幅不超过约 {max_chars} 字，在限制内尽量保留关键细节与可执行信息。\n"
    "6) 脉络连贯：关注「用户要什么 → 做了什么 → 得到什么结论」的因果链，不要只罗列事实；"
    "对每个关键结论尽量保留。\n"
    "7) 禁止编造：不得引入记录中未出现的文件名、结论或数字；不确定处请写「未在记录中明确」。\n"
    "8) 若剔除噪声后确实无可保留的实质信息：请仅输出「摘要为空」五个字（不要加标点或换行），"
    "使全文总字符数少于 10；不要输出其它占位或解释。\n"
    "9) 若素材含无法展开的占位标注（如长内容被省略的标记），简要记录其存在与主题，不要编造具体细节。\n"
    "10) 范围：`role=system` 的内容（系统提示词、知识库、Skills、记忆摘要）是"
    "智能体的常驻设定，不是对话内容 —— 不要把它们的正文归纳进摘要，"
    "也不要凭它们推断素材里没有的事；摘要只写对话与工具结果里真实发生的事。\n"
    "11) 只输出摘要正文：不要调用任何工具，不要复述这条要求，不要提及做过摘要。"
)


def _is_degenerate_summary_body(body: str) -> bool:
    """退化摘要：空串，或极短且仅含「摘要为空」占位。"""
    b = str(body or "").strip()
    if not b:
        return True
    if len(b) < 10 and "摘要为空" in b:
        return True
    return False


#: 每张图片的 token 估算值。固定取 384（不读配置），而不是官方上限 1024。
IMAGE_TOKENS_PER_IMAGE = 384


def count_images(content: Any) -> int:
    """content 里 `image_url` 块的个数。"""
    if not isinstance(content, list):
        return 0
    return sum(1 for p in content
               if isinstance(p, dict) and p.get("type") == "image_url")


def _approx_message_tokens(message: Optional[Dict[str, Any]]) -> int:
    """单条消息 token 估算 —— 与装配期同一个实现（`default_message_tokens`）。

    两处各写一份必然漂移：一处算了 `tool_calls`、另一处算了思维链，
    于是"压缩判定的体积"与"实际发出去的体积"对不上，阈值跟着失准。
    """
    return _DEFAULT_POLICY.message_tokens(message)


def _schemas_tokens(tools: Optional[List[Dict[str, Any]]]) -> int:
    """工具声明的 token 估算（每请求都带，属固定开销）。"""
    if not tools:
        return 0
    try:
        return _DEFAULT_POLICY.approx_tokens(json.dumps(tools, ensure_ascii=False))
    except (TypeError, ValueError):
        return 0


def _mode_note_tokens(mode_note: str) -> int:
    """尾部执行模式说明的 token 估算（也算进请求体）。"""
    return _DEFAULT_POLICY.approx_tokens(mode_note)


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
        lines.append(f"### {role}\n{body}")
    text = "\n\n".join(lines)
    if not text:
        return []
    return [{"role": "user", "content": "【待压缩的对话】\n" + text}]


def make_provider_summarizer(
    provider: Any,
    *,
    max_chars: int = 2000,
    prefix_reuse: bool = True,
) -> Callable[..., str]:
    """构造基于模型 provider 的摘要生成函数。

    返回 fn(prefix, tools, system) -> str。摘要这一次调用与平常请求共用同一前缀：

        平常请求  系统提示词 + 插件各段 + 记忆摘要 + 对话 + 新输入/工具结果
        摘要请求  系统提示词 + 插件各段 + 记忆摘要 + 对话 + 压缩指令

    `prefix` 就是上一次请求消息列表里"溢出点之前"的那一段，逐字节相同，
    工具定义也照同一份带上 —— 这样前缀部分命中 provider 的 KV 缓存，
    只按压缩指令那点新增内容付费。`prefix_reuse=False` 时不带这份前缀，
    改发素材 JSON，前缀与平常请求无关，必然缓存未命中。

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
        head = list(prefix or []) if prefix_reuse else []
        if not head:
            # 没有可复用的前缀时只发素材和指令。要压的正文在素材里，请求自成一体。
            # 这里若返回空串，估算再大也不压，直到请求超窗口被拒绝。
            head = _material_messages(prefix, material)
        tail = instruction
        request = LogicalRequest(
            # 与平常请求走同一个补齐函数：压缩可能落在"工具调用已发出、结果还没
            # 回来"的中间态（例如某个调用在等用户确认），此时历史里
            # `assistant(tool_calls)` 是悬空的。模型 API 对悬空调用硬拒绝
            # （400：must be followed by tool messages）。
            # 两边补法一致，前缀逐字节相同不受影响。
            messages=ensure_tool_pairs(_DEFAULT_POLICY.clip(head, 0)
                                        + [{"role": "system", "content": tail}]),
            # 工具定义照平常请求带上（前缀的一部分，少一项整段缓存作废）。
            tools=list(tools or []) if prefix_reuse else [],
        )
        parts: List[str] = []
        try:
            for delta in provider.stream(request):
                if getattr(delta, "kind", "") == "text":
                    parts.append(str(getattr(delta, "text", "") or ""))
        except Exception as exc:
            print(f"[compactor] 摘要生成失败（已放行）: {exc}", file=sys.stderr, flush=True)
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
    ) -> None:
        self._summarize_fn = summarize_fn
        self.summary_token_threshold = max(1, int(summary_token_threshold))
        self.covered_end = 0
        #: 遮盖的末尾用户轮数：正常只压它们前面那一段；那里压不出空间时
        #: 连它们一起压（压不动就是请求超上限）。取值与 `[context] full_user_rounds`
        #: 同一个配置项。
        self.full_user_rounds = max(0, int(full_user_rounds))
        self._policy = policy or ContextCompactionPolicy(
            full_user_rounds=self.full_user_rounds,
        )
        #: 历次压缩产生的摘要，各占一条 system 消息（不合并、不持续更新）：
        #: 压缩范围只含 user/assistant 内容，摘要属系统设定、不在范围内。
        self.summaries: List[str] = []

    # ── 恢复────────────────────────────────

    def restore_from_events(self, events: Any) -> None:
        """从会话记录重放 `context_compacted` 事件重建状态（幂等；covered_end 单调不减）。"""
        covered = 0
        summaries: List[str] = []
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
            s = str(data.get("summary") or "").strip()
            if s:
                summaries.append(s)
        self.covered_end = covered
        self.summaries = summaries

    # ── 视图与注入──────────────────────────

    def view_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """未覆盖视图：全量消息去除已覆盖前缀。"""
        return list(messages[self.covered_end :])

    def summary_messages(self) -> List[Dict[str, Any]]:
        """摘要注入消息（记忆块；逐条独立成轮）：【历史摘要】前缀 + 正文。"""
        return [{"role": "system", "content": "【历史摘要】\n" + s} for s in self.summaries]

    # ── 拼入前检查────────────────────

    def _excerpt_range(self, view: List[Dict[str, Any]], context: Any):
        rng = self._policy.excerpt(view, token_fn=context.message_tokens)
        if not rng:
            return None
        start, end = int(rng[0]), min(int(rng[1]), len(view))
        if end <= 0:
            return None
        start = self._policy.floor(view, start)
        if not self._policy.balanced(view, start, end):
            return None
        return start, end

    def _summary_body(self, base: List[Dict[str, Any]],
                      messages: List[Dict[str, Any]], start: int, end: int,
                      context: Any, tools: Any) -> str:
        system = ""
        if hasattr(context, "system_text"):
            system = str(context.system_text() or "")
        text = ""
        if self._summarize_fn is not None:
            material = list(messages[start:end]) if messages else []
            text = str(self._summarize_fn(
                base, tools, system, material=material) or "").strip()
        if _is_degenerate_summary_body(text):
            return ""
        return text + SUMMARY_BRIDGE_TAIL

    def ensure_before_append(
        self,
        context: Any,
        messages: List[Dict[str, Any]],
        pending: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        mode_note: str = "",
        assembled: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """拼入前预算检查：超阈值先压缩既有历史；失败放行。"""
        try:
            if context is None:
                return None
            view = self.view_messages(messages)
            if not view or not assembled:
                return None
            base = ContextCompactor._context_without_new_input(list(assembled))
            base = ContextCompactor._strip_mode_tail(base, mode_note)
            if not base:
                return None
            pending_tokens = _approx_message_tokens(pending)
            context.set_summary_messages(self.summary_messages())
            context.set_dialogue(view)
            overhead = _schemas_tokens(tools) + _mode_note_tokens(mode_note)
            estimate = context.total_token_estimate() + pending_tokens + overhead
            if estimate <= self.summary_token_threshold:
                return None
            rng = self._excerpt_range(view, context)
            if rng is None:
                return None
            start, end = rng
            body = self._summary_body(base, messages, start, end, context, tools)
            if not body:
                return None
            self.covered_end += end
            self.summaries.append(body)
            if hasattr(context, "set_summary_messages"):
                context.set_summary_messages(self.summary_messages())
            return {"covered_end": self.covered_end, "summary": body,
                    "compressed_count": end}
        except Exception as exc:
            print(f"[compactor] 压缩检查失败（已放行）: {exc}",
                  file=sys.stderr, flush=True)
            return None

    @staticmethod
    def _strip_mode_tail(messages: Any, mode_note: str = "") -> List[Dict[str, Any]]:
        """剔除尾部的执行模式说明。

        判据（两条任一成立即认为是模式说明，从尾部连续剔除）：

        1. 与本次的 `mode_note` 正文相同 —— 最可靠，模式说明是现拼出来的；
        2. 正文以 `MODE_MARKER` 开头 —— 模式段的固定标记，`mode_note` 拿不到时兜底。

        只剔尾部的：模式说明永远附在最后，中间的 `system` 消息（系统提示 / 插件段 /
        知识库 / 摘要）一条都不能动。
        """
        note = str(mode_note or "").strip()
        out = list(messages or [])
        while out:
            last = out[-1]
            if not isinstance(last, dict) or str(last.get("role") or "") != "system":
                break
            text = str(last.get("content") or "").strip()
            if not text:
                break
            if note and text == note:
                out.pop()
                continue
            if text.startswith(MODE_MARKER):
                out.pop()
                continue
            break
        return out

    @staticmethod
    def _context_without_new_input(messages: Any) -> List[Dict[str, Any]]:
        """已拼好的上下文，去掉本轮新输入。

        会话里维护的上下文长这样（`ModelModule` 拼好的那一份）::

            上轮上下文 + [本轮新输入] + [执行模式]
            上轮上下文 = [系统提示][插件段-*][摘要-*][第y轮][回复]…[上轮输入]
                        （不含本轮新输入、不含执行模式）

        判据：先看当前回合由什么触发（跳过尾部连续的 `system` 之后看那一条）——

        - `tool`：当前是工具轮，触发者是工具结果 —— 整份都算上下文
          （含当前回合那条提问，以及本轮的工具调用与结果），什么都不删；
        - `user`：这就是本轮新输入，删掉它；尾部连续的 `system`
          （执行模式之类的附加说明）也一并删掉 —— 它属于"平常请求"，不属于"上轮上下文"；
        - `assistant`：当前回合已产出回复、也没有新输入，整份返回。

        调用方随后用压缩结果重拼：`zip + 本轮新输入 + 执行模式`。
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
            # 工具轮 / 已回复：没有"本轮新输入"可删。
            return msgs
        out = msgs[:i] + msgs[i + 1:]
        # 新输入后面的尾部 system（执行模式之类）也不属于上轮上下文，一并去掉。
        while out:
            last = out[-1]
            if isinstance(last, dict) and str(last.get("role") or "") == "system":
                out.pop()
                continue
            break
        return out
