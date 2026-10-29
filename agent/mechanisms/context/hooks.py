# -*- coding: utf-8 -*-
"""上下文拼装钩子。

插件注册后，模型请求组装阶段按注册顺序调用：

```text
context -> hook(context) -> context
```

钩子只返回新的消息列表，不保存宿主状态，也不直接写会话事实。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

from agent.core.error_report import report_error

ContextHook = Callable[[List[Dict[str, Any]], str], Any]


class ContextAssemblyHooks:
    """按注册顺序执行完整上下文钩子。"""

    def __init__(self) -> None:
        self._hooks: List[ContextHook] = []

    def add(self, hook: ContextHook) -> Callable[[], None]:
        if not callable(hook):
            raise ValueError("上下文钩子必须可调用")
        self._hooks.append(hook)

        def _dispose() -> None:
            try:
                self._hooks.remove(hook)
            except ValueError:
                return

        return _dispose

    def apply(self, messages: List[Dict[str, Any]], conversation_id: str) -> List[Dict[str, Any]]:
        current = list(messages or [])
        for hook in list(self._hooks):
            try:
                result = hook(list(current), str(conversation_id or ""))
            except Exception as exc:
                report_error("agent.mechanisms.context.hooks.apply", exc)
                continue
            if result is None:
                continue
            if not _valid_messages(result):
                report_error(
                    "agent.mechanisms.context.hooks.result",
                    ValueError("上下文钩子返回值必须是消息列表"),
                )
                continue
            current = list(result)
        return current


def _valid_messages(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    for item in value:
        if not isinstance(item, dict):
            return False
        if str(item.get("role") or "") not in ("system", "user", "assistant", "tool"):
            return False
    return True

__all__ = ["ContextAssemblyHooks", "ContextHook"]
