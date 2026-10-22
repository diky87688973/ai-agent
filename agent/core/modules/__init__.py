# -*- coding: utf-8 -*-
"""四个真实模块：输入 / 压缩 / 模型 / 工具。

每个模块的 `execute` 是生成器：`yield` 事实，`return` 控制信号
（`execute` 为生成器的契约见 `module.py` 顶部）。

模块只经端口访问外界（`Ports`），数据走事件，模块之间不互相 import、
不共享字段——它们共享的是事实日志与端口接口。
"""
from __future__ import annotations

from typing import Any, List, Optional

from agent.core.image_embed import KEEP_IMAGE_TURNS, MAX_EMBED_IMAGES
from agent.core.module import ModuleBase
from agent.core.modules.compress_mod import CompressModule
from agent.core.modules.input_mod import InputModule
from agent.core.modules.model_mod import ModelModule
from agent.core.modules.queued_input_mod import QueuedInputModule
from agent.core.modules.support import (
    TOOL_RESULT_MAX_CHARS,
    assemble_with,
    clip_tool_result,
    mode_tail,
    pending_tool_calls,
    prepare_dialogue,
    progress_emitter,
    safe_value,
    segment_snapshot,
    serialize_call,
    tail_expects_model,
    with_mode_note,
)
from agent.core.modules.tool_mod import ToolModule

__all__ = [
    "CompressModule",
    "QueuedInputModule",
    "InputModule",
    "ModelModule",
    "ToolModule",
    "TOOL_RESULT_MAX_CHARS",
    "build_default_chain",
    "assemble_with",
    "clip_tool_result",
    "mode_tail",
    "pending_tool_calls",
    "prepare_dialogue",
    "progress_emitter",
    "safe_value",
    "segment_snapshot",
    "serialize_call",
    "tail_expects_model",
    "with_mode_note",
]


def build_default_chain(
    *,
    input_module: Optional[ModuleBase] = None,
    context: Any = None,
    compactor: Any = None,
    queued_input: Any = None,
    effort: str = "high",
    model: str = "",
    image_turns: int = KEEP_IMAGE_TURNS,
    image_max: int = MAX_EMBED_IMAGES,
    mode_note: Any = "",
) -> List[ModuleBase]:
    """默认模块链：输入 → 待发送队列插入 → 压缩 → 模型 → 工具。

    顺序即语义：先认领输入、再收别的会话投进来的消息、再管预算、
    再问模型、最后执行工具（收尾）。插入模块必须在压缩之前 —— 它会产生新的
    用户轮次，压缩要看得见这些轮次。
    装配方可以换掉任意一环或插入自己的模块——宿主不关心链上有什么。
    """
    return [
        input_module if input_module is not None else InputModule(),
        QueuedInputModule(queue=queued_input),
        CompressModule(context=context, compactor=compactor, mode_note=mode_note,
                       image_turns=image_turns, image_max=image_max),
        ModelModule(context=context, compactor=compactor, effort=effort, model=model,
                    image_turns=image_turns, image_max=image_max,
                    mode_note=mode_note),
        ToolModule(),
    ]

