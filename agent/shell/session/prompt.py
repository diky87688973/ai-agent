# -*- coding: utf-8 -*-
"""系统提示词与运行态尾部。"""
from __future__ import annotations

from typing import Any, List

from agent.shell.environment_info import environment_section
from agent.shell.prompts import TODO_LIST_NOTE, resolve_mode_note, resolve_system_prompt


def system_prompt(*, app: Any, mesh: Any, cid: str,
                  prompt_sections: Any = None) -> str:
    """系统提示：mesh 显式设过就用它，否则基础提示词。"""
    meta = mesh.get_agent(cid)
    explicit = str(meta.get("system") or "")
    state = getattr(app, "live_state", None)
    mode = state.get_mode(cid) if state is not None else "auto"
    extra: List[Any] = []
    if prompt_sections is not None:
        extra.extend(prompt_sections.render(cid))
    extra.append(environment_section(cid))
    return resolve_system_prompt(
        mode=mode,
        registry=getattr(app, "registry", None),
        explicit=explicit or None,
        extra_sections=extra,
    )


def mode_note(*, app: Any, mesh: Any, cid: str) -> str:
    """请求尾部的临时执行模式、Todo 进度与插件尾部。"""
    meta = mesh.get_agent(cid)
    explicit = str(meta.get("system") or "")
    state = getattr(app, "live_state", None)
    mode = state.get_mode(cid) if state is not None else "auto"
    note = resolve_mode_note(mode=mode, explicit=explicit or None)
    prompt_tail = getattr(app, "prompt_tail", None)
    extra = prompt_tail.render(cid).strip() if prompt_tail is not None else ""
    todo_note = ""
    todo = state.get_todo(cid) if state is not None and hasattr(state, "get_todo") else None
    items = todo.get("items") if isinstance(todo, dict) else None
    if isinstance(items, list) and items:
        total = len(items)
        done = sum(1 for item in items if isinstance(item, dict) and item.get("done"))
        active = 0 if done == total else 1
        pending = max(0, total - done - active)
        todo_note = (
            f"{TODO_LIST_NOTE}\n"
            f"当前进度：{done} 已完成，{active} 进行中，{pending} 待处理"
        )
    parts = [part for part in (note, todo_note if note else "") if part]
    if extra:
        parts.append(extra)
    return "\n\n".join(parts)
