# -*- coding: utf-8 -*-
"""视觉操作 2.0：持续视觉、全局独占、用户授权与键鼠动作。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List

from agent.capabilities.plugin_events import publish_plugin_event

from . import backend, step_log
from .config import load_config
from .desktop import (
    DesktopParts,
    make_desktop_parts,
    make_vision_app,
    make_vision_click_text,
    make_vision_eye,
    make_vision_find,
    make_vision_keyboard,
    make_vision_mouse,
    make_vision_open,
    make_vision_type_into,
    make_vision_wait,
    make_vision_window,
)
from .routes import make_confirm, make_pending, make_revoke, make_status
from .state import VisionRuntime
from .tools import (
    VisionClickSequenceTool,
    VisionClickTool,
    VisionFocusTool,
    VisionKeyTool,
    VisionMoveFocusTool,
    VisionMovePointTool,
    VisionMoveTool,
    VisionRequestOpenTool,
    VisionStartTool,
    VisionStopTool,
    finish_tool,
)

PLUGIN_NAME = "visual_operator_2"


@dataclass(frozen=True)
class SlotRuntime:
    """插口装配期的运行时载体。

    `vision` 是有状态资源（帧队列、锁、线程、当前 owner、监控器与标记），
    必须全局唯一；`desktop` 里的 `captures` 也必须只有一份。
    20 个工具全部从同一份载体取，不自建。
    """

    vision: VisionRuntime
    desktop: DesktopParts


def make_runtime(ctx: Any, app: Any) -> SlotRuntime:
    """装配期构造运行时：步骤日志、输入监控、控制标记与视觉资源。

    `app` 由装配器按 requires 注入：步骤日志路径与插件事件出口都从它取。
    """
    config = load_config()
    step_log.configure(_step_log_path(app))
    monitor = backend.HumanInputMonitor(config.takeover_distance)
    monitor.register_inject_tag(backend.FOREIGN_INJECT_TAG)
    badge = backend.ControlBadge()
    vision = VisionRuntime(
        config,
        publish=lambda event, payload: publish_plugin_event(
            app, PLUGIN_NAME, event, payload),
        input_monitor=monitor,
        control_badge=badge,
    )
    monitor.bind(vision.user_takeover)
    return SlotRuntime(vision=vision, desktop=make_desktop_parts())


def make_tool_vision_request_open(ctx: Any, runtime: SlotRuntime) -> Any:
    return finish_tool(VisionRequestOpenTool(runtime.vision))


def make_tool_vision_start(ctx: Any, runtime: SlotRuntime) -> Any:
    return finish_tool(VisionStartTool(runtime.vision))


def make_tool_vision_focus(ctx: Any, runtime: SlotRuntime) -> Any:
    return finish_tool(VisionFocusTool(runtime.vision))


def make_tool_vision_move(ctx: Any, runtime: SlotRuntime) -> Any:
    return finish_tool(VisionMoveTool(runtime.vision))


def make_tool_vision_move_point(ctx: Any, runtime: SlotRuntime) -> Any:
    return finish_tool(VisionMovePointTool(runtime.vision))


def make_tool_vision_move_focus(ctx: Any, runtime: SlotRuntime) -> Any:
    return finish_tool(VisionMoveFocusTool(runtime.vision))


def make_tool_vision_click(ctx: Any, runtime: SlotRuntime) -> Any:
    return finish_tool(VisionClickTool(runtime.vision))


def make_tool_vision_click_sequence(ctx: Any, runtime: SlotRuntime) -> Any:
    return finish_tool(VisionClickSequenceTool(runtime.vision))


def make_tool_vision_key(ctx: Any, runtime: SlotRuntime) -> Any:
    return finish_tool(VisionKeyTool(runtime.vision))


def make_tool_vision_stop(ctx: Any, runtime: SlotRuntime) -> Any:
    return finish_tool(VisionStopTool(runtime.vision))


def make_tool_vision_app(ctx: Any, runtime: SlotRuntime) -> Any:
    return finish_tool(make_vision_app(runtime.vision, runtime.desktop))


def make_tool_vision_window(ctx: Any, runtime: SlotRuntime) -> Any:
    return finish_tool(make_vision_window(runtime.vision, runtime.desktop))


def make_tool_vision_eye(ctx: Any, runtime: SlotRuntime) -> Any:
    return finish_tool(make_vision_eye(runtime.vision, runtime.desktop))


def make_tool_vision_type_into(ctx: Any, runtime: SlotRuntime) -> Any:
    return finish_tool(make_vision_type_into(runtime.vision, runtime.desktop))


def make_tool_vision_keyboard(ctx: Any, runtime: SlotRuntime) -> Any:
    return finish_tool(make_vision_keyboard(runtime.vision, runtime.desktop))


def make_tool_vision_wait(ctx: Any, runtime: SlotRuntime) -> Any:
    return finish_tool(make_vision_wait(runtime.vision, runtime.desktop))


def make_tool_vision_find(ctx: Any, runtime: SlotRuntime) -> Any:
    return finish_tool(make_vision_find(runtime.vision, runtime.desktop))


def make_tool_vision_click_text(ctx: Any, runtime: SlotRuntime) -> Any:
    return finish_tool(make_vision_click_text(runtime.vision, runtime.desktop))


def make_tool_vision_mouse(ctx: Any, runtime: SlotRuntime) -> Any:
    return finish_tool(make_vision_mouse(runtime.vision, runtime.desktop))


def make_tool_vision_open(ctx: Any, runtime: SlotRuntime) -> Any:
    return finish_tool(make_vision_open(runtime.vision, runtime.desktop))


def _observation_hook(runtime: VisionRuntime):
    def hook(messages: List[dict], conversation_id: str) -> List[dict]:
        observation = runtime.observe(conversation_id)
        if observation is None:
            return messages
        runtime.publish_observation(observation)
        step_log.write(
            "observation", conversation_id=conversation_id,
            frame_id=observation.get("frame_id"),
            cursor=observation.get("cursor"),
            focus=observation.get("focus"),
            calibration=observation.get("calibration"))
        content: List[dict] = [{"type": "text", "text": observation["text"]}]
        for item in observation["images"]:
            label = str(item.get("label") or "")
            url = str(item.get("url") or "")
            if label:
                content.append({"type": "text", "text": label})
            if not url:
                continue
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": url,
                    "detail": str(item.get("detail") or "low"),
                },
            })
        return [*messages, {"role": "user", "content": content}]

    return hook


def _vision_prompt(_cid: str) -> str:
    return (
        "## 视觉帧\n"
        "该段落为视觉操作插件注入，所有视觉操作必须先查看清楚当前视觉注入内容后再操作，点击时看清楚鼠标位置和按钮关系!!!\n"
        "视觉操作前必须加载 skills：visual-operator-2 和 windows-desktop-operations。\n"
        "需要局部细节时用 vision_focus；每次移动或点击后必须看下一轮实时注入的视觉帧，用黄色光标标记确认目标，不能凭工具回执认定成功.\n"
        "绝对定位移动和点击工具必须传 check_points：当前校准帧 C1 随机标记中心的图内 xy；工具按随机真实屏幕点做 32px 校验，缺失或超差直接失败.原样读标记，不要自己换算屏幕坐标.\n"
        "完整图是全屏画面按比例缩放后的图, 无黑区无填充.\n"
        "需要放大时用 vision_focus 指定固定区域; 聚焦图 1:1 不跟随光标; 聚焦图内移动用 vision_move_focus.\n"
        "x、y 就是目标在这张图上量的像素位置, image_width、image_height 取 original_image_size.\n"
        "center_x、center_y 由你给出, 是你看到的这张图的中心像素, 用于与真实屏幕做双边中心对齐: "
        "x 方向用图宽与 center_x 对齐到屏幕宽, y 方向用图高与 center_y 对齐到屏幕高, 两边独立换算.\n"
        "你只报图上的 x、y 和这张图的 center_x、center_y, 屏幕坐标由工具按上述参数换算, 不要自己换算屏幕坐标.\n"
        "取点先读目标的上下左右四边像素位再取中点, 不凭感觉瞄; 画面刷新或布局变化后旧坐标作废, 重新看图取点.\n"
        "【最高禁令】禁止重复汇报!!!\n"
        "同一件事只报一次, 说完就停!!!\n"
        "禁止把已经说过的位置、坐标、状态、进度再说一遍.\n"
        "禁止用不同措辞、换句话、补充说明、自我纠正等任何形式重发同一内容.\n"
        "禁止说完一句话后再补一句意思相同的话; 已停手就停止出声, 不要继续声明自己停手了.\n"
        "一次回复只说新增信息; 没有新增信息就不说话, 直接结束回合."
    )


def _step_log_path(app: Any) -> Any:
    context = getattr(app, "context", None) if app is not None else None
    if context is None or not callable(getattr(context, "has", None)):
        return None
    if not context.has("error_log"):
        return None
    error_log = context.get("error_log")
    path = getattr(error_log, "path", None)
    return Path(path).parent / "visual_operator_2.steps.log" if path else None


def make_observation_hook(ctx: Any, runtime: SlotRuntime) -> Callable[..., Any]:
    """上下文拼装钩子：把当前画面作为一条用户消息接在末尾。"""
    return _observation_hook(runtime.vision)


def make_prompt_section(ctx: Any, runtime: SlotRuntime) -> Callable[[str], str]:
    """视觉帧提示词段；`after_tools` 语义由片段 props 携带。"""
    return _vision_prompt


def make_route_pending(ctx: Any, runtime: SlotRuntime) -> Callable[..., Any]:
    return make_pending(ctx, runtime.vision)


def make_route_status(ctx: Any, runtime: SlotRuntime) -> Callable[..., Any]:
    return make_status(ctx, runtime.vision)


def make_route_confirm(ctx: Any, runtime: SlotRuntime, app: Any) -> Callable[..., Any]:
    return make_confirm(app, runtime.vision)


def make_route_revoke(ctx: Any, runtime: SlotRuntime) -> Callable[..., Any]:
    return make_revoke(ctx, runtime.vision)


#: 20 个工具的插口工厂，顺序与 build_tools 一致。
TOOL_FACTORIES = (
    make_tool_vision_request_open, make_tool_vision_start, make_tool_vision_focus,
    make_tool_vision_move, make_tool_vision_move_point, make_tool_vision_move_focus,
    make_tool_vision_click, make_tool_vision_click_sequence, make_tool_vision_key,
    make_tool_vision_stop,
    make_tool_vision_app, make_tool_vision_window, make_tool_vision_eye,
    make_tool_vision_type_into, make_tool_vision_keyboard, make_tool_vision_wait,
    make_tool_vision_find, make_tool_vision_click_text, make_tool_vision_mouse,
    make_tool_vision_open,
)
