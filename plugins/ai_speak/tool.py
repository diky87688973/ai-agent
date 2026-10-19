# -*- coding: utf-8 -*-
"""`ai_speak` 工具：校验 `msg`、取发布器、交给运行时入队。"""
from __future__ import annotations

from typing import Any, Dict

from agent.capabilities.registry import ToolPlugin
from agent.core.context import SERVICE_PLUGIN_EVENTS
from agent.core.session_scope import current_context

from .provider import SpeechEngineUnavailable
from .runtime import AISpeakRuntime
from .text import MessageValidationError, split_message

_DESCRIPTION = (
    "把你要对用户说的话直接说出来。用当前角色的第一人称、人类口语，像当面汇报，"
    "不使用播音腔、书面语，不解释自己在调用工具。每完成一步就调用一次，"
    "不等到全部做完。"
    "允许：中文、英文、数字、空格；中文标点 ，。？！；、：“”‘’（）；"
    "英文标点 . , ? ! ; : ' \" ( )；四则符号 + - * / × ÷（含全角 ＋－＊／）；"
    "百分号 % 或 ％。英文单词内可用 - 和 '。"
    "禁止其他符号、emoji、换行、Markdown、代码、链接。"
    "每个分句以边界标点结尾；后端按标点贪心拼装，单段上限取插件配置 "
    "max_segment_chars（默认 128 字），超过上限会失败并返回规范。"
    "一次最多 512 字。例如「进度 10%。」会读成「进度 百分之十。」；"
    "「5+3。」会读成「五加三。」。"
    "示例：主子，文件已经写好了，您要不要看一眼？"
)


class AISpeakTool(ToolPlugin):
    """模型主动调用的说话入口。"""

    name = "ai_speak"
    label = "AI说话"
    icon = "🔊"
    parallel_safe = False
    needs_preview = False
    write_path_keys = ()

    description = _DESCRIPTION
    parameters = {
        "msg": {
            "type": "string",
            "description": "要说的话；当前角色口吻、人类口语；单次最多 512 字。",
        }
    }

    def __init__(self, runtime: AISpeakRuntime) -> None:
        self._runtime = runtime

    def execute(self, arguments: Dict[str, Any]) -> Any:
        raw = (arguments or {}).get("msg")
        if not isinstance(raw, str):
            raise MessageValidationError("msg 必须是字符串", code="invalid_type")

        segments = split_message(raw, self._runtime.config.max_segment_chars)
        if not self._runtime.provider_ready():
            raise SpeechEngineUnavailable(
                "edge-tts 未安装。请执行: pip install edge-tts"
            )

        turn = current_context()
        if turn is None or turn.app is None:
            raise SpeechEngineUnavailable("AI说话只能在工具调用中执行")
        conversation_id = str(turn.conversation_id or "").strip()
        if not conversation_id:
            raise SpeechEngineUnavailable("缺少会话 id")
        publisher = turn.app.get(SERVICE_PLUGIN_EVENTS) if turn.app.has(SERVICE_PLUGIN_EVENTS) else None
        if publisher is None or not callable(publisher):
            raise SpeechEngineUnavailable("当前没有可用的插件事件出口")
        connected = getattr(publisher, "connected", None)
        if callable(connected) and not connected():
            raise SpeechEngineUnavailable("没有已连接的 Web 界面")

        queued = self._runtime.enqueue(
            conversation_id=conversation_id,
            call_id=str(turn.call_id or ""),
            segments=segments,
            voice=self._runtime.config.voice,
            publisher=publisher,
        )
        return {
            "accepted": True,
            "segments": queued,
            "characters": len(raw.strip()),
        }


def build(runtime: AISpeakRuntime) -> AISpeakTool:
    """构造工具；`SpeechBusy` 由运行时抛出，管道统一收成失败结果。"""
    return AISpeakTool(runtime)


__all__ = ["AISpeakTool", "build"]
