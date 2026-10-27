# -*- coding: utf-8 -*-
"""上下文装配与分段快照。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent.core.modules.mode_note import mode_tail, strip_runtime_note


def assemble_with(context: Any, dialogue: Any, mode_note: str,
                   covered_end: int) -> Optional[List[Dict[str, Any]]]:
    """把对话装进上下文并装配出整份请求消息（头部 + 对话 + 尾部）。

    上下文缺能力（没实现 `set_dialogue` / `assembles`）时返回 None ——
    调用方据此退回"只有对话"的降级路径，而不是崩掉。
    """
    if context is None:
        return None
    if not (hasattr(context, "set_dialogue") and hasattr(context, "assembles")):
        return None
    context.set_dialogue(strip_runtime_note(dialogue), covered_end=covered_end)
    note = str(mode_note or "").strip()
    tail = [{"role": "system", "content": note}] if note else []
    return list(context.assembles(tail))


def segment_snapshot(context: Any, messages: Any,
                      budget_tokens: int = 0) -> Optional[Dict[str, Any]]:
    """把装配好的请求拆成分段快照（段名 + 各段估算 token）。

    口径与真正发出去的请求一致（同一份装配、同一个估算器）：
    头部各块（系统提示词 / 插件各段 / 记忆摘要）+ 对话
    + 尾部（本回合新输入 / 工具结果 / 执行模式）。

    `budget_tokens` 是各段 `pct` 的归一化基准（= 压缩阈值）。不传就只能拿"已用"
    当基准，剩余容量恒为 0 —— 界面那条永远显示 0%，所以调用方必须给。

    上下文缺分段能力（或算不出来）→ `None`，调用方不发这条事件。
    """
    if context is None or not hasattr(context, "layout_payload"):
        return None
    mode = mode_tail(messages)
    payload = context.layout_payload(tail_messages=mode,
                                     budget_tokens=int(budget_tokens or 0))
    if not payload or not payload.get("segments"):
        return None
    return payload
