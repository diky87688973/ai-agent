# -*- coding: utf-8 -*-
"""压缩器依赖的窄上下文接口。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from agent.mechanisms.context.layout import clip_reasoning, excerpt_by_target_tokens
from agent.mechanisms.context.rounds import tool_chain_balanced, turn_boundary_floor
from agent.mechanisms.context.tokens import approx_tokens_text, default_message_tokens

DEFAULT_FULL_USER_ROUNDS = 5


@dataclass(frozen=True)
class ContextCompactionPolicy:
    """压缩器所需的上下文策略，不暴露 ContextPipeline 内部结构。"""

    full_user_rounds: int = DEFAULT_FULL_USER_ROUNDS

    def excerpt(
        self,
        messages: List[Dict[str, Any]],
        *,
        token_fn: Optional[Callable[[Dict[str, Any]], int]] = None,
    ) -> Optional[Tuple[int, int]]:
        return excerpt_by_target_tokens(
            messages, keep_turns=self.full_user_rounds, token_fn=token_fn,
        )

    @staticmethod
    def clip(messages: List[Dict[str, Any]], budget_tokens: int) -> List[Dict[str, Any]]:
        return clip_reasoning(messages, budget_tokens)

    @staticmethod
    def approx_tokens(text: str) -> int:
        return approx_tokens_text(str(text or ""))

    @staticmethod
    def message_tokens(message: Optional[Dict[str, Any]]) -> int:
        return int(default_message_tokens(message or {}))

    @staticmethod
    def balanced(messages: List[Dict[str, Any]], start: int, end: int) -> bool:
        return tool_chain_balanced(messages, start, end)

    @staticmethod
    def floor(messages: List[Dict[str, Any]], index: int) -> int:
        return turn_boundary_floor(messages, index)
