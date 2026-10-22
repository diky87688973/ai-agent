# -*- coding: utf-8 -*-
"""Todo 清单工具。"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List

from agent.capabilities.registry import ToolPlugin
from agent.core.session_scope import current_session_id
from agent.mechanisms.live_state import LiveState


class TodoListTool(ToolPlugin):
    """会话执行清单。"""

    name = "todo_list"
    label = "待办清单"
    icon = "☑️"
    description = "会话待办清单：`action=create / check / uncheck / add_item / remove_item / replace_item / collapse / close / query`。"
    parameters = {
        "action": {
            "type": "string",
            "description": "create / check / uncheck / add_item / remove_item / replace_item / collapse / close / query",
        },
        "items": {"type": "array", "description": "create：非空数组（字符串或 {text, done} 对象）"},
        "indices": {"type": "array", "description": "check / uncheck：下标（int 或非空 int 数组）"},
        "item_index": {"type": "integer", "description": "add_item / remove_item / replace_item 的下标"},
        "text": {"type": "string", "description": "add_item / replace_item 的文本"},
    }

    def __init__(self, live_state: LiveState) -> None:
        self._state = live_state

    @staticmethod
    def _progress(items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """清单进度：done 计数 + 是否全部完成。

        全部完成时清单左边框转绿并给一个关闭键——那是"可以收工了"的信号，
        所以这个字段必须由服务端给出，而不是让每个前端各算一遍。
        """
        total = len(items)
        done = sum(1 for item in items if item.get("done"))
        return {"done_count": done, "total_count": total,
                "all_done": bool(total) and done == total}

    @staticmethod
    def _normalize_items(parsed: Any) -> List[Dict[str, Any]]:
        if not isinstance(parsed, list) or not parsed:
            raise ValueError("items 必须为非空数组")
        items: List[Dict[str, Any]] = []
        for i, it in enumerate(parsed):
            if isinstance(it, dict) and "text" in it:
                items.append({"text": str(it["text"]).strip(), "done": bool(it.get("done", False))})
            elif isinstance(it, str) and it.strip():
                items.append({"text": it.strip(), "done": False})
            else:
                raise ValueError(f"items[{i}] 须为非空字符串或 {{text, done}} 对象")
        return items

    @staticmethod
    def _as_int_list(value: Any, label: str) -> List[int]:
        if value is None:
            raise ValueError(f"缺少 {label}")
        if isinstance(value, int):
            return [value]
        if isinstance(value, list):
            if not value:
                raise ValueError(f"{label} 须为非空整数数组")
            out: List[int] = []
            for x in value:
                try:
                    out.append(int(x))
                except (TypeError, ValueError):
                    raise ValueError(f"{label} 须为 int 或非空 int 数组")
            return out
        raise ValueError(f"{label} 须为 int 或非空 int 数组")

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        cid = current_session_id()
        if not cid:
            raise RuntimeError("todo_list 须由宿主传入 conversation_id")
        action = str(arguments.get("action") or "").strip().lower()
        if not action:
            raise ValueError("缺少 action")
        if action == "create":
            raw = arguments.get("items")
            if not isinstance(raw, list):
                raise ValueError("create 需要 items（字符串数组或对象数组）")
            items = self._normalize_items(raw)
            lid = uuid.uuid4().hex[:12]
            data: Dict[str, Any] = {"list_id": lid, "items": items, "collapsed": False,
                                    **self._progress(items)}
            self._state.set_todo(cid, data)
            return data
        if action == "query":
            todo = self._state.get_todo(cid)
            return list(todo["items"]) if todo else None
        todo = self._state.get_todo(cid)
        if todo is None:
            raise ValueError("当前对话无活跃清单，请先用 create")
        if action in ("check", "uncheck"):
            indices = self._as_int_list(arguments.get("indices"), "indices")
            for idx in indices:
                if idx < 0 or idx >= len(todo["items"]):
                    raise IndexError(f"indices 含越界下标 {idx}，共 {len(todo['items'])} 项")
            for idx in indices:
                todo["items"][idx]["done"] = action == "check"
            self._state.set_todo(cid, todo)
            key = "checked" if action == "check" else "unchecked"
            return {
                "list_id": todo["list_id"],
                "items": todo["items"],
                key: indices,
                **self._progress(todo["items"]),
            }
        if action == "add_item":
            text = str(arguments.get("text") or "").strip()
            if not text:
                raise ValueError("add_item 需要 text")
            item = {"text": text, "done": False}
            ins = arguments.get("item_index")
            if ins is not None and isinstance(ins, int) and 0 <= ins <= len(todo["items"]):
                todo["items"].insert(ins, item)
            else:
                todo["items"].append(item)
            self._state.set_todo(cid, todo)
            return {"list_id": todo["list_id"], "items": todo["items"]}
        if action in ("remove_item", "replace_item"):
            raw_ix = arguments.get("item_index")
            if raw_ix is None:
                raise ValueError(f"{action} 需要 item_index（int）")
            try:
                ix = int(raw_ix)
            except (TypeError, ValueError):
                raise ValueError(f"{action} 需要 item_index（int）")
            if ix < 0 or ix >= len(todo["items"]):
                raise IndexError(f"item_index {ix} 越界，共 {len(todo['items'])} 项")
            if action == "remove_item":
                todo["items"].pop(ix)
            else:
                text = str(arguments.get("text") or "").strip()
                if not text:
                    raise ValueError("replace_item 需要 text")
                todo["items"][ix]["text"] = text
            self._state.set_todo(cid, todo)
            return {"list_id": todo["list_id"], "items": todo["items"],
                    **self._progress(todo["items"])}
        if action == "collapse":
            todo["collapsed"] = not todo.get("collapsed", False)
            self._state.set_todo(cid, todo)
            return {"list_id": todo["list_id"], "items": todo["items"],
                    "collapsed": todo["collapsed"], **self._progress(todo["items"])}
        if action == "close":
            self._state.set_todo(cid, None)
            return {"close": True}
        raise ValueError(f"未知 action: {action}")


#: 宿主交互能力：Web 壳层当前只支持两段式确认；TTY 宿主接入后再由宿主打开。
#: 环境判断不能放在模型或工具里，必须由壳层注入。
INTERACTIVE_UI_ENABLED = False
