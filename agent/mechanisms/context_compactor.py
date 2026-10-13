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

from agent.core.ports import LogicalRequest
from agent.mechanisms.context_pipeline import approx_tokens_text

# 摘要桥接尾巴：接在摘要正文之后，向模型标明上文是历史摘要、下文续当前对话。
SUMMARY_BRIDGE_TAIL = "\n\n【以上为历史摘要，下面继续当前对话】"

_SUMMARY_SYSTEM_PROMPT = (
    "你是对话整理助手，任务是对下列「历史聊天记录」做摘要提取，不是续写对话、不是执行工具、不要输出工具调用。\n"
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
    "9) 若素材含无法展开的占位标注（如长内容被省略的标记），简要记录其存在与主题，不要编造具体细节。"
)


def _is_degenerate_summary_body(body: str) -> bool:
    """退化摘要：空串，或极短且仅含「摘要为空」占位。"""
    b = str(body or "").strip()
    if not b:
        return True
    if len(b) < 10 and "摘要为空" in b:
        return True
    return False


def _strip_tool_trace(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """素材剥离工具痕迹：去 tool 消息；user/assistant/system 仅保留文本。"""
    out: List[Dict[str, Any]] = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "")
        if role not in ("user", "assistant", "system"):
            continue
        content = m.get("content")
        text = ""
        if isinstance(content, str):
            text = content
        elif content is not None:
            try:
                text = json.dumps(content, ensure_ascii=False)
            except (TypeError, ValueError):
                text = str(content)
        if not text and role == "assistant":
            rc = m.get("reasoning_content")
            if isinstance(rc, str) and rc.strip():
                text = rc
        out.append({"role": role, "content": text})
    return out


#: 每张图片的 token 估算值。固定取 384（不读配置），而不是官方上限 1024。
IMAGE_TOKENS_PER_IMAGE = 384


def count_images(content: Any) -> int:
    """content 里 `image_url` 块的个数。"""
    if not isinstance(content, list):
        return 0
    return sum(1 for p in content
               if isinstance(p, dict) and p.get("type") == "image_url")


def _approx_message_tokens(message: Optional[Dict[str, Any]]) -> int:
    """单条消息 token 估算（content + reasoning + tool_calls）。

    **图片块按 `IMAGE_TOKENS_PER_IMAGE` 计、文本块按字符数计**：一张 8536 字符的截图会被算成 2000+
    （`//4+4`），而官方口径是**每图最多 1024**。按文本算会把预算高估一倍以上，
    于是"刚发一张图就触发压缩"。图片块按固定上限计，文本部分照旧。
    """
    if not isinstance(message, dict):
        return 0
    content = message.get("content")
    if isinstance(content, str):
        n = approx_tokens_text(content)
    elif content is None:
        n = 0
    elif isinstance(content, list):
        imgs = count_images(content)
        texts = [
            str(p.get("text") or "")
            for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        n = approx_tokens_text("".join(texts)) + imgs * IMAGE_TOKENS_PER_IMAGE
    else:
        try:
            n = approx_tokens_text(json.dumps(content, ensure_ascii=False))
        except (TypeError, ValueError):
            n = approx_tokens_text(str(content))
    rc = message.get("reasoning_content")
    if isinstance(rc, str) and rc.strip():
        n += approx_tokens_text(rc)
    tc = message.get("tool_calls")
    if isinstance(tc, list) and tc:
        try:
            n += approx_tokens_text(json.dumps(tc, ensure_ascii=False))
        except (TypeError, ValueError):
            n += 16
    return n


def make_provider_summarizer(
    provider: Any, *, max_chars: int = 2000
) -> Callable[[List[Dict[str, Any]]], str]:
    """构造基于模型 provider 的摘要生成函数。

    返回 fn(material) -> str：素材 JSON 序列化后单轮生成（无工具）；
    生成异常 / 空文本 → 返回空串（由调用方按失败放行处理）。
    """

    def _summarize(material: List[Dict[str, Any]]) -> str:
        if provider is None or not material:
            return ""
        payload = json.dumps(material, ensure_ascii=False)
        request = LogicalRequest(
            messages=[
                {
                    "role": "system",
                    "content": _SUMMARY_SYSTEM_PROMPT.format(max_chars=max(1, int(max_chars))),
                },
                {"role": "user", "content": payload},
            ],
            tools=[],
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
        summarize_fn: Optional[Callable[[List[Dict[str, Any]]], str]] = None,
        *,
        summary_token_threshold: int = 8000,
    ) -> None:
        self._summarize_fn = summarize_fn
        self.summary_token_threshold = max(1, int(summary_token_threshold))
        self.covered_end = 0
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
            except (TypeError, ValueError):
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

    def ensure_before_append(
        self,
        context: Any,
        messages: List[Dict[str, Any]],
        pending: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """拼入前预算检查：预估"拼入后"总 token；超阈值先压缩既有历史。

        context：上下文管线（set_summaries / rebuild_from_messages /
        total_token_estimate / dialogue_summary_excerpt_half_open）；
        messages：当前全量消息（不含待拼入）；pending：待拼入消息（仅用于估算，
        绝不进入压缩素材）。返回压缩事件数据（covered_end / summary / compressed_count）
        或 None（未触发 / 失败放行）。
        """
        try:
            if context is None:
                return None
            view = self.view_messages(messages)
            if not view:
                return None
            pending_tokens = _approx_message_tokens(pending)
            # 预演组装：视图装入对话块、摘要装入记忆块，再取全块估算
            context.set_summaries(self.summary_messages())
            context.rebuild_from_messages(view)
            if context.total_token_estimate() + pending_tokens <= self.summary_token_threshold:
                return None
            rng = context.dialogue_summary_excerpt_half_open(view)
            if not rng:
                return None
            e = min(int(rng[1]), len(view))
            if e <= 0:
                return None
            material = _strip_tool_trace(view[:e])
            if not material:
                return None
            text = ""
            if self._summarize_fn is not None:
                text = str(self._summarize_fn(material) or "").strip()
            if _is_degenerate_summary_body(text):
                return None
            body = text + SUMMARY_BRIDGE_TAIL
            self.covered_end += e
            self.summaries.append(body)
            return {
                "covered_end": self.covered_end,
                "summary": body,
                "compressed_count": e,
            }
        except Exception as exc:
            print(f"[compactor] 压缩检查失败（已放行）: {exc}", file=sys.stderr, flush=True)
            return None
