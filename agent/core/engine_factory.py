# -*- coding: utf-8 -*-
"""引擎工厂：把装配参数原样翻成模块链引擎。

单独成文件是为了让"参数必须落到引擎"这件事只有一个实现点：装配点只负责
收集依赖，转发与默认值不散落在调用处。
"""
from __future__ import annotations

from typing import Any

from agent.core.engine import Engine
from agent.core.host import MAX_PASSES_DEFAULT
from agent.core.image_embed import KEEP_IMAGE_TURNS, MAX_EMBED_IMAGES


def build_engine(
    *,
    conversation_id: str,
    log: Any,
    provider: Any = None,
    registry: Any = None,
    pipeline: Any = None,
    context: Any = None,
    compactor: Any = None,
    context_hooks: Any = None,
    queued_input: Any = None,
    fact_sink: Any = None,
    system_prompt: str = "",
    cancel: Any = None,
    effort: str = "high",
    model: str = "",
    image_turns: int = KEEP_IMAGE_TURNS,
    image_max: int = MAX_EMBED_IMAGES,
    max_passes: int = MAX_PASSES_DEFAULT,
    mode_note: Any = "",
    event_sink: Any = None,
    session_context: Any = None,
    seq_allocator: Any = None,
    app_context: Any = None,
    session_contexts: Any = None,
) -> Any:
    """组装引擎；`system_prompt` 已由调用方决定，这里不再二次注入。

    `cancel` 一路透传到宿主与端口：宿主在每趟开始前问一次、模型模块逐帧问、
    工具模块逐调用问（见 `core/host.py` 与 `core/modules/`）。取消时发出
    `turn_ended{stopped: true}`，适配层据此翻成经典界面的 `stopped` 帧。
    """
    return Engine(
        conversation_id=conversation_id,
        log=log,
        provider=provider,
        registry=registry,
        pipeline=pipeline,
        context=context,
        compactor=compactor,
        context_hooks=context_hooks,
        queued_input=queued_input,
        effort=effort,
        model=model,
        image_turns=image_turns,
        image_max=image_max,
        max_passes=max_passes,
        mode_note=mode_note,
        fact_sink=fact_sink,
        event_sink=event_sink,
        session_context=session_context,
        cancel=cancel,
        # 这一行不能少：签名收了 `seq_allocator`，漏传则「事件带存储坐标」
        # 在真实装配链路上完全失效 —— 内核层 `Ports`/`Host` 的盖章逻辑照常工作、
        # 单元测试直接构造 `Host(...)` 也能过，但真实运行里帧 `id:` 行为 0 条，
        # 浏览器 `Last-Event-ID` 恒空 → 断线期间的事件静默丢失（不重放、不报错）。
        # 存储侧的兜底补号会掩盖它（存储行有坐标、总线上的没有）。
        seq_allocator=seq_allocator,
        app_context=app_context,
        session_contexts=session_contexts,
    )
