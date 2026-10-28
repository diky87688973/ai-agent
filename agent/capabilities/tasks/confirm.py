# -*- coding: utf-8 -*-
"""用户确认与审批工具。"""
from __future__ import annotations

from typing import Any, Dict

from agent.capabilities.registry import ToolPlugin
from agent.capabilities.tasks.common import (
    ApprovalRequired,
    UserConfirmRequired,
    approval_text,
    normalize_confirms,
)


class UserConfirmTool(ToolPlugin):
    """用户分岔确认：两段式信封。"""

    name = "user_confirm"
    label = "等待确认"
    icon = "⚠️"
    description = (
        "向用户发起分岔确认。首段只用 title + confirms 挂起，等待宿主界面作答；"
        "宿主把确认结果写成工具结果，不作为工具入参。"
    )
    parameters = {
        "title": {"type": "string", "description": "标题（首段必填）"},
        "confirms": {"type": "array", "description": "候选项（首段必填；非空字符串数组）"},
        "multi": {"type": "boolean", "description": "是否支持多选（透传给宿主）"},
        "custom_option_index": {"type": "integer", "description": "自由输入绑定的选项下标（可选）"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if arguments.get("confirms") is None:
            raise ValueError("须提供 confirms（非空字符串数组）")
        confirms = normalize_confirms(arguments.get("confirms"))
        custom_index = arguments.get("custom_option_index")
        if custom_index is not None:
            cix = int(custom_index)
            if cix < 0 or cix >= len(confirms):
                raise ValueError("custom_option_index 须满足 0 <= i < len(confirms)")
        title = str(arguments.get("title") or "").strip()
        if not title:
            raise ValueError("首次发起须提供 title")
        raise UserConfirmRequired(
            title,
            confirms,
            multi=bool(arguments.get("multi", False)),
            custom_option_index=custom_index,
        )


class ApprovalConfirmTool(ToolPlugin):
    """操作审批。调用后挂起，等用户同意或驳回。

    同意时宿主把 `approval_id` 写入这次调用的结果，并在会话上下文记下
    `approval_id` → `option_id`。本工具没有回填入参。
    """

    name = "approval_confirm"
    label = "审批"
    icon = "🛂"
    description = (
        "向用户发起审批。入参为 option_id（需要放行的工具给出的操作 ID）"
        "和 option_desc（弹窗正文）。调用后挂起，等用户点同意或驳回。"
        "驳回的结果是「不同意」。同意的结果是「同意」，并带有宿主签发的 approval_id。"
        "approval_id 写在这次调用的结果里。再次调用本工具不会回填。"
    )
    parameters = {
        "option_id": {"type": "string", "description": "操作 ID，由需要审批的工具给出"},
        "option_desc": {"type": "string", "description": "弹窗正文，一句简短问话"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        option_id = approval_text(arguments.get("option_id"), "option_id", 200)
        option_desc = approval_text(arguments.get("option_desc"), "option_desc", 500)
        raise ApprovalRequired(option_id, option_desc)
