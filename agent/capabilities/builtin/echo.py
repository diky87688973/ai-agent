# -*- coding: utf-8 -*-
"""echo 工具：回显输入文本。"""
from __future__ import annotations

from typing import Any

from agent.capabilities.registry import ToolPlugin


class EchoTool(ToolPlugin):
    """回显输入文本。"""

    name = "echo"
    label = "回显"
    icon = "🔔"
    description = "回显输入文本。"
    parameters = {"text": {"type": "string", "description": "要回显的文本"}}

    def execute(self, arguments: dict[str, Any]) -> str:
        return f"echo: {arguments.get('text', '')}"


def build() -> EchoTool:
    """构造 echo 工具插件。"""
    return EchoTool()
