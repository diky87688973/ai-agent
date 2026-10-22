# -*- coding: utf-8 -*-
"""上下文模型、布局、来源与管线。"""
from __future__ import annotations

from agent.mechanisms.context.contract import DEFAULT_FULL_USER_ROUNDS
from agent.mechanisms.context.layout import (
    REASONING_OMIT_FMT,
    adjust_excerpt_range_half_open,
    clip_reasoning,
    clip_reasoning_text,
    excerpt_by_target_tokens,
    layout_from_messages,
)
from agent.mechanisms.context.pipeline import (
    CHUNK_FULL,
    CHUNK_MEM,
    CHUNK_MODE,
    CHUNK_ORDER,
    CHUNK_PLUGIN,
    CHUNK_SYSTEM,
    DEFAULT_REASONING_REPLAY_TOKENS,
    DEFAULT_SUMMARY_TOKEN_THRESHOLD,
    ContextPipeline,
)
from agent.mechanisms.context.rounds import (
    ContextChunk,
    Round,
    copy_round_list,
    find_first_user_index,
    flat_messages_to_user_rounds,
    is_turn_boundary,
    tool_chain_balanced,
    turn_boundary_floor,
    turn_spans,
    user_turn_starts,
)
from agent.mechanisms.context.sources import (
    ContextSources,
    PluginSegments,
    SourceMeta,
    slug,
)
from agent.mechanisms.context.tokens import approx_tokens_text, default_message_tokens

__all__ = [
    "CHUNK_FULL", "CHUNK_MEM", "CHUNK_MODE", "CHUNK_ORDER", "CHUNK_PLUGIN", "CHUNK_SYSTEM",
    "DEFAULT_FULL_USER_ROUNDS", "DEFAULT_REASONING_REPLAY_TOKENS",
    "DEFAULT_SUMMARY_TOKEN_THRESHOLD", "REASONING_OMIT_FMT",
    "ContextChunk", "ContextPipeline", "ContextSources", "PluginSegments", "Round",
    "SourceMeta", "adjust_excerpt_range_half_open", "approx_tokens_text",
    "clip_reasoning", "clip_reasoning_text", "copy_round_list", "default_message_tokens",
    "excerpt_by_target_tokens", "find_first_user_index", "flat_messages_to_user_rounds",
    "is_turn_boundary", "layout_from_messages", "slug", "tool_chain_balanced",
    "turn_boundary_floor", "turn_spans", "user_turn_starts",
]
