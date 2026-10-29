# -*- coding: utf-8 -*-
"""视觉操作 2.0 工具面。

工具只暴露动作；当前画面由内核上下文钩子自动注入。
"""
from __future__ import annotations

from typing import Any, Dict

from agent.capabilities.registry import ToolPlugin
from agent.core.session_scope import current_context

from .consent import VisionConsentRequired
from .state import VisionRuntime


def _cid() -> str:
    ctx = current_context()
    return str(getattr(ctx, "conversation_id", "") or "") if ctx is not None else ""


def _call_id() -> str:
    ctx = current_context()
    return str(getattr(ctx, "call_id", "") or "") if ctx is not None else ""


class VisionRequestOpenTool(ToolPlugin):
    name = "vision_request_open"
    label = "申请视觉授权"
    icon = "👁️"
    parallel_safe = False
    description = (
        "申请打开视觉。固定授权文案由眼睛工具提供，用户确认后工具恢复并返回一次性 consent_id。"
        "拿到 consent_id 后，必须在当前回合立即调用 vision_start(consent_id=...)，"
        "不得再让用户确认，不得先调用 ai_speak、解释或重新申请。"
        "在确认前不会截屏。"
    )
    parameters: Dict[str, Any] = {}

    def __init__(self, runtime: VisionRuntime) -> None:
        self._runtime = runtime

    def execute(self, arguments: Dict[str, Any]) -> Any:
        cid = _cid()
        if not cid:
            return {"ok": False, "error": "缺少会话上下文"}
        result = self._runtime.request_open(cid, _call_id())
        if not result.get("ok"):
            return result
        raise VisionConsentRequired(str(result["request_id"]), cid)


class VisionStartTool(ToolPlugin):
    name = "vision_start"
    label = "睁眼"
    icon = "👁️"
    parallel_safe = False
    description = "用用户确认后签发的 consent_id 打开视觉。没有凭证时拒绝。"
    parameters = {
        "consent_id": {"type": "string", "description": "眼睛工具签发的授权凭证"},
    }

    def __init__(self, runtime: VisionRuntime) -> None:
        self._runtime = runtime

    def execute(self, arguments: Dict[str, Any]) -> Any:
        return self._runtime.start(_cid(), str(arguments.get("consent_id") or ""))


class VisionFocusTool(ToolPlugin):
    name = "vision_focus"
    label = "聚焦"
    icon = "🎯"
    parallel_safe = False
    description = (
        "把光标移到指定区域中心；视觉局部图始终跟随光标。"
        "区域只用于移动光标，不保存固定聚焦范围；center_cursor=true 时把光标放到区域中心。"
        "region 的 x/y/width/height 是屏幕坐标区域，超出屏幕的部分会先裁剪。"
    )
    parameters = {
        "region": {
            "type": "object",
            "description": "屏幕坐标区域 {x,y,width,height}；为空表示恢复默认",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
            },
            "required": ["x", "y", "width", "height"],
        },
        "center_cursor": {"type": "boolean", "description": "是否把鼠标移到区域中心"},
    }

    def __init__(self, runtime: VisionRuntime) -> None:
        self._runtime = runtime

    def execute(self, arguments: Dict[str, Any]) -> Any:
        region = arguments.get("region")
        if region is not None and not isinstance(region, dict):
            raise ValueError("region 必须是对象")
        return self._runtime.focus(_cid(), region, bool(arguments.get("center_cursor")))


class VisionMoveTool(ToolPlugin):
    name = "vision_move"
    label = "移动鼠标"
    icon = "🖱️"
    parallel_safe = False
    description = "以当前观察的鼠标位置为起点，执行相对移动；精确点击优先使用 vision_move_to。"
    parameters = {
        "dx": {"type": "integer", "description": "水平相对位移"},
        "dy": {"type": "integer", "description": "垂直相对位移"},
    }

    def __init__(self, runtime: VisionRuntime) -> None:
        self._runtime = runtime

    def execute(self, arguments: Dict[str, Any]) -> Any:
        return self._runtime.move(_cid(), int(arguments["dx"]), int(arguments["dy"]))


class VisionMovePointTool(ToolPlugin):
    name = "vision_move_point"
    label = "移动到点"
    icon = "🖱️"
    parallel_safe = False
    description = (
        "按模型看到的图上的点移动鼠标。x/y 是目标点在模型看到的图上的像素；"
        "center_x/center_y 是模型看到的图像中心坐标；image_width/image_height 是原始截图宽高。"
        "模型直接读图上的 x/y；用 center_x/center_y 对准屏幕中心后，双轴独立换算，模型不要自己换算。"
    )
    parameters = {
        "x": {"type": "integer", "description": "目标点在模型看到的图上的 x"},
        "y": {"type": "integer", "description": "目标点在模型看到的图上的 y"},
        "center_x": {"type": "integer", "description": "模型看到的图像中心 x"},
        "center_y": {"type": "integer", "description": "模型看到的图像中心 y"},
        "image_width": {"type": "integer", "description": "原始截图宽度"},
        "image_height": {"type": "integer", "description": "原始截图高度"},
    }

    def __init__(self, runtime: VisionRuntime) -> None:
        self._runtime = runtime

    def execute(self, arguments: Dict[str, Any]) -> Any:
        return self._runtime.move_point(
            _cid(),
            int(arguments["x"]), int(arguments["y"]),
            int(arguments["center_x"]), int(arguments["center_y"]),
            int(arguments["image_width"]), int(arguments["image_height"]),
        )


class VisionMoveFocusTool(ToolPlugin):
    name = "vision_move_focus"
    label = "移动到局部点"
    icon = "🎯"
    parallel_safe = False
    description = (
        "按聚焦小图上的点移动鼠标。x/y 是目标点在聚焦小图上的像素；"
        "width/height 是模型看到的聚焦小图宽高；image_width/image_height 是原始聚焦小图宽高。"
        "工具按当前 cursor 居中的聚焦区域换算屏幕落点。"
    )
    parameters = {
        "x": {"type": "integer", "description": "目标点在聚焦小图上的 x"},
        "y": {"type": "integer", "description": "目标点在聚焦小图上的 y"},
        "width": {"type": "integer", "description": "模型看到的聚焦小图宽度"},
        "height": {"type": "integer", "description": "模型看到的聚焦小图高度"},
        "image_width": {"type": "integer", "description": "原始聚焦小图宽度"},
        "image_height": {"type": "integer", "description": "原始聚焦小图高度"},
    }

    def __init__(self, runtime: VisionRuntime) -> None:
        self._runtime = runtime

    def execute(self, arguments: Dict[str, Any]) -> Any:
        return self._runtime.move_focus(
            _cid(),
            int(arguments["x"]), int(arguments["y"]),
            int(arguments["width"]), int(arguments["height"]),
            int(arguments["image_width"]), int(arguments["image_height"]),
        )


class VisionClickTool(ToolPlugin):
    name = "vision_click"
    label = "点击"
    icon = "🖱️"
    parallel_safe = False
    description = "在当前鼠标位置点击；不接收坐标。支持点击次数和间隔，间隔最小 72ms。"
    parameters = {
        "count": {"type": "integer", "minimum": 1, "maximum": 10,
                  "description": "点击次数，1~10"},
        "interval_ms": {"type": "integer", "minimum": 72, "maximum": 1000,
                        "default": 72, "description": "点击间隔，最小 72ms，缺省 72"},
    }

    def __init__(self, runtime: VisionRuntime) -> None:
        self._runtime = runtime

    def execute(self, arguments: Dict[str, Any]) -> Any:
        interval = int(arguments.get("interval_ms") or 72)
        if interval < 72:
            raise ValueError("interval_ms 不能小于 72")
        return self._runtime.click(
            _cid(), "left", int(arguments.get("count") or 1), interval)


class VisionClickSequenceTool(ToolPlugin):
    name = "vision_click_sequence"
    label = "连续点击"
    icon = "🖱️"
    parallel_safe = False
    description = (
        "按模型看到的图上的多个点连续移动并点击。每个点的 x/y 都按 center_x/center_y "
        "图像中心和 image_width/image_height 原始尺寸做双轴换算；"
        "center_x/center_y 是模型可见图的中心点。"
    )
    parameters = {
        "points": {
            "type": "array",
            "description": "模型看到的图上的点序列",
            "items": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
                "required": ["x", "y"],
            },
        },
        "center_x": {"type": "integer", "description": "模型看到的图像中心 x"},
        "center_y": {"type": "integer", "description": "模型看到的图像中心 y"},
        "image_width": {"type": "integer", "description": "原始截图宽度"},
        "image_height": {"type": "integer", "description": "原始截图高度"},
        "interval_ms": {"type": "integer", "minimum": 72, "maximum": 1000,
                        "default": 72, "description": "点与点之间的间隔，最小 72，缺省 72"},
        "count": {"type": "integer", "description": "每个点点击次数，1~3"},
    }

    def __init__(self, runtime: VisionRuntime) -> None:
        self._runtime = runtime

    def execute(self, arguments: Dict[str, Any]) -> Any:
        points = arguments.get("points")
        if not isinstance(points, list) or not points:
            raise ValueError("points 不能为空")
        for point in points:
            if not isinstance(point, dict) or "x" not in point or "y" not in point:
                raise ValueError("每个 point 必须是 {x, y}")
        interval = int(arguments.get("interval_ms") or 72)
        if interval < 72:
            raise ValueError("interval_ms 不能小于 72")
        return self._runtime.click_sequence(
            _cid(), points,
            int(arguments["center_x"]), int(arguments["center_y"]),
            int(arguments["image_width"]), int(arguments["image_height"]),
            interval,
            int(arguments.get("count") or 1),
        )


class VisionKeyTool(ToolPlugin):
    name = "vision_key"
    label = "按键"
    icon = "⌨️"
    parallel_safe = False
    description = "按下键盘组合键，例如 [\"ctrl\", \"c\"]。"
    parameters = {
        "keys": {
            "type": "array",
            "description": "按键序列",
            "items": {"type": "string"},
            "minItems": 1,
        },
    }

    def __init__(self, runtime: VisionRuntime) -> None:
        self._runtime = runtime

    def execute(self, arguments: Dict[str, Any]) -> Any:
        keys = arguments.get("keys")
        if not isinstance(keys, list) or not keys:
            raise ValueError("keys 必须是非空数组")
        return self._runtime.key(_cid(), [str(x) for x in keys])


class VisionStopTool(ToolPlugin):
    name = "vision_stop"
    label = "闭眼"
    icon = "🙈"
    parallel_safe = False
    description = "关闭视觉，停止采集并清空队列；不需要用户确认。"
    parameters: Dict[str, Any] = {}

    def __init__(self, runtime: VisionRuntime) -> None:
        self._runtime = runtime

    def execute(self, arguments: Dict[str, Any]) -> Any:
        return self._runtime.stop(_cid())


SKILL_REQUIRED = (
    "视觉操作依赖 skills：visual-operator-2（视觉坐标/点击流程）和 "
    "windows-desktop-operations（窗口激活/打开应用）。调用任何视觉工具前先加载这两个 skills。"
)


def build_tools(runtime: VisionRuntime) -> list[ToolPlugin]:
    tools = [
        VisionRequestOpenTool(runtime),
        VisionStartTool(runtime),
        VisionMoveTool(runtime),
        VisionMovePointTool(runtime),
        VisionClickTool(runtime),
        VisionClickSequenceTool(runtime),
        VisionKeyTool(runtime),
        VisionStopTool(runtime),
    ]
    for tool in tools:
        tool.description = SKILL_REQUIRED + str(tool.description)
    return tools

__all__ = ["build_tools"]
