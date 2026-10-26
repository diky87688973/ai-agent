# -*- coding: utf-8 -*-
"""父子智能体工具：创建、列表、状态、发送与子会话回父。"""
from __future__ import annotations

from typing import Any, Dict

from agent.capabilities.registry import ToolPlugin
from agent.core.session_scope import current_session_id
from agent.subagent.manager import SubagentManager
from agent.subagent.models import SubagentError

_IMAGE_PARAM = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "mime": {"type": "string"},
            "data_base64": {"type": "string"},
        },
    },
    "description": "图片附件，格式与 Web 输入一致",
}


class SubagentTool(ToolPlugin):
    """父会话管理子智能体。"""

    name = "subagent"
    label = "子智能体"
    icon = "◈"
    description = (
        "管理当前会话的子智能体。create 创建并立即执行首条任务；"
        "list 按批次查看；status 查询忙闲；result 读取最近一次输出；send 向子智能体发消息。"
        "send 强制插入当前回合（打断式发送）。"
    )
    parameters = {
        "action": {
            "type": "string",
            "enum": ["create", "list", "status", "result", "send"],
            "description": "create / list / status / result / send",
        },
        "prompt": {"type": "string", "description": "首条任务（create 必填）"},
        "label": {"type": "string", "description": "任务标题（create 必填，UI 展示）"},
        "batch": {"type": "string", "description": "批次号；不传自动新建，传回上次返回值"},
        "context": {
            "type": "string",
            "enum": ["fork", "fresh"],
            "description": "fork 复制父会话已完成回合；fresh 使用空上下文",
        },
        "images": _IMAGE_PARAM,
        "child_id": {"type": "string", "description": "子智能体 id（status / send 必填）"},
        "msg": {"type": "string", "description": "消息文本（send 必填）"},
    }

    def __init__(self, manager: SubagentManager) -> None:
        self._manager = manager

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        parent = str(current_session_id() or "").strip()
        if not parent:
            raise ValueError("缺少当前会话 id")
        action = str(arguments.get("action") or "").strip().lower()
        try:
            if action == "create":
                return self._manager.create(
                    parent,
                    prompt=str(arguments.get("prompt") or ""),
                    label=str(arguments.get("label") or ""),
                    context=str(arguments.get("context") or "fork"),
                    batch=str(arguments.get("batch") or ""),
                    images=arguments.get("images"),
                )
            if action == "list":
                return self._manager.list(parent, str(arguments.get("batch") or ""))
            if action == "status":
                return self._manager.status(
                    parent, str(arguments.get("child_id") or ""),
                )
            if action == "result":
                return self._manager.result(
                    parent, str(arguments.get("child_id") or ""),
                )
            if action == "send":
                return self._manager.send(
                    parent,
                    str(arguments.get("child_id") or ""),
                    msg=str(arguments.get("msg") or ""),
                    images=arguments.get("images"),
                )
        except SubagentError as exc:
            raise ValueError(str(exc)) from exc
        raise ValueError("action 必须是 create / list / status / result / send")


class SubagentSendTool(ToolPlugin):
    """子会话向直属父会话发送消息。"""

    name = "subagent_send"
    label = "发给父会话"
    icon = "↥"
    description = (
        "向直属父会话发送消息；只能用于子智能体会话。"
        "强制插入父会话当前回合（打断式发送）。"
    )
    parameters = {
        "msg": {"type": "string", "description": "消息文本"},
        "images": _IMAGE_PARAM,
    }

    def __init__(self, manager: SubagentManager) -> None:
        self._manager = manager

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        child = str(current_session_id() or "").strip()
        if not child:
            raise ValueError("缺少当前会话 id")
        try:
            return self._manager.send_to_parent(
                child,
                msg=str(arguments.get("msg") or ""),
                images=arguments.get("images"),
            )
        except SubagentError as exc:
            raise ValueError(str(exc)) from exc


def build(manager: SubagentManager) -> list[ToolPlugin]:
    return [SubagentTool(manager), SubagentSendTool(manager)]
