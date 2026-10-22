# -*- coding: utf-8 -*-
"""goal 工具。"""
from __future__ import annotations

from typing import Any, Dict

from agent.capabilities.registry import ToolPlugin
from agent.core.session_scope import current_session_id
from agent.mechanisms.live_state import GoalError, LiveState


class GoalTool(ToolPlugin):
    """目标（Goal）：可编辑的自主续跑任务对象。

    与"自主模式"同一机制 —— 回合结束后自动再发一条 user 输入；
    区别是那条输入就是这里的目标文案，所以自动续跑有了方向，也能随时改写。

    `active` 的目标会在每轮结束后持续触发；`paused` 保留但不触发；
    `done` 是终态。触发文案由用户或模型任一方设定。
    """

    name = "goal"
    label = "目标"
    icon = "🎯"
    description = (
        "管理本会话的目标文案。目标处于 active 时，每轮结束后系统会自动用该文案"
        "发起新一轮，直到你用 action=pause/done 停下。"
        "action: create=新建或整体改写；get=查询；update=局部改（文案/状态/备注）；"
        "pause=暂停触发；resume=恢复触发；done=标记达成；delete=删除。"
        "不要每轮都调 get 自查：自动触发的那一轮里，目标文案本身就是发来的消息，"
        "你不需要再查一次；只在用户问起目标状态、或你要动手改它之前查一次。"
    )
    parameters = {
        "action": {"type": "string",
                   "description": "create / get / update / pause / resume / done / delete"},
        "text": {"type": "string", "description": "目标文案（create 必填；update 可改）"},
        "note": {"type": "string", "description": "备注（可选，给人看）"},
        "status": {"type": "string", "description": "update 时的状态：active / paused / done"},
    }

    def __init__(self, live_state: LiveState) -> None:
        self._state = live_state

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """按 `action` 管理目标；返回扁平 dict（与 todo_list 等同约定）。

        参数错误一律 `raise ValueError` —— 管线会把它翻成 `ok=False` 的结果回灌给模型，
        比返回 `{"ok": False, ...}` 更直接：后者会被裹成 `data`，模型看到的是嵌套信封。
        """
        action = str(arguments.get("action") or "get").strip().lower()
        text = str(arguments.get("text") or "").strip()
        note = str(arguments.get("note") or "").strip()
        status = str(arguments.get("status") or "").strip().lower()
        cid = current_session_id()
        if not cid:
            raise RuntimeError("goal 须由宿主传入 conversation_id")
        try:
            if action == "create":
                return {"goal": self._state.set_goal(cid, text, note=note)}
            if action == "get":
                return {"goal": self._state.get_goal(cid)}
            if action == "update":
                return {"goal": self._state.update_goal(cid, text=text, status=status, note=note)}
            if action == "pause":
                return {"goal": self._state.update_goal(cid, status="paused")}
            if action == "resume":
                if text:
                    # 恢复时给出的文案优先：同会话已有目标也整体替换。
                    return {"goal": self._state.set_goal(cid, text)}
                if self._state.get_goal(cid) is None:
                    raise GoalError("目标不存在，且没有可恢复的文案")
                return {"goal": self._state.update_goal(cid, status="active")}
            if action == "done":
                return {"goal": self._state.update_goal(cid, status="done")}
            if action == "delete":
                return {"deleted": bool(self._state.delete_goal(cid))}
        except GoalError as exc:
            # 目标的语义错误（没有目标 / 空文案 / 非法状态）是可纠正的参数问题，
            # 交给管线回灌成 ok=False，模型看得到原因并自己改。
            raise ValueError(str(exc)) from exc
        raise ValueError(f"未知 action：{action}")
