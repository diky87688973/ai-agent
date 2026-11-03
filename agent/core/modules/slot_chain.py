# -*- coding: utf-8 -*-
"""内核模块链的插口节点与逐会话构建。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.core.host import MAX_PASSES_DEFAULT
from agent.core.image_embed import KEEP_IMAGE_TURNS, MAX_EMBED_IMAGES
from agent.core.modules.compress_mod import CompressModule
from agent.core.modules.input_mod import InputModule
from agent.core.modules.model_mod import ModelModule
from agent.core.modules.queued_input_mod import QueuedInputModule
from agent.core.modules.tool_mod import ToolModule


def input_module(ctx: Any, children: Any = ()) -> Any:
    return InputModule()


def queued_input_module(ctx: Any, children: Any = ()) -> Any:
    return QueuedInputModule(queue=ctx.queued_input)


def compress_module(ctx: Any, children: Any = ()) -> Any:
    return CompressModule(
        context=ctx.context, compactor=ctx.compactor, mode_note=ctx.mode_note,
        image_turns=ctx.image_turns, image_max=ctx.image_max,
        appenders=[child.port_value() for child in children])


def model_module(ctx: Any, children: Any = ()) -> Any:
    return ModelModule(
        context=ctx.context, compactor=ctx.compactor, effort=ctx.effort,
        model=ctx.model, image_turns=ctx.image_turns,
        image_max=ctx.image_max, mode_note=ctx.mode_note,
        context_hooks=ctx.context_hooks)


def tool_module(ctx: Any, children: Any = ()) -> Any:
    return ToolModule()


@dataclass(frozen=True)
class AgentLoopConfig:
    """内核 AgentLoop 的会话预算；由内核模块组持有。"""

    image_turns: int = KEEP_IMAGE_TURNS
    image_max: int = MAX_EMBED_IMAGES
    max_passes: int = MAX_PASSES_DEFAULT


@dataclass(frozen=True)
class ModuleBuildContext:
    """一次回合内构造模块所需的会话参数。"""

    context: Any = None
    compactor: Any = None
    context_hooks: Any = None
    queued_input: Any = None
    effort: str = "high"
    model: str = ""
    image_turns: int = KEEP_IMAGE_TURNS
    image_max: int = MAX_EMBED_IMAGES
    mode_note: Any = ""




__all__ = ["AgentLoopConfig", "ModuleBuildContext", "input_module", "queued_input_module", "compress_module", "model_module", "tool_module"]
