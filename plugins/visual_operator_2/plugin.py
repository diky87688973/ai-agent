# -*- coding: utf-8 -*-
"""视觉操作 2.0：持续视觉、全局独占、用户授权与键鼠动作。"""
from __future__ import annotations

from typing import Any, List

from . import backend
from .config import load_config
from .routes import build_routes
from .state import VisionRuntime
from .tools import build_tools

PLUGIN_VERSION = "2.0"
PLUGIN_NAME = "visual_operator_2"


def _observation_hook(runtime: VisionRuntime):
    def hook(messages: List[dict], conversation_id: str) -> List[dict]:
        observation = runtime.observe(conversation_id)
        if observation is None:
            return messages
        runtime.publish_observation(observation)
        content: List[dict] = [{"type": "text", "text": observation["text"]}]
        image_index = 0
        for item in observation["images"]:
            if item.startswith("data:"):
                detail = "low" if image_index == 0 else "original"
                image_index += 1
                content.append({
                    "type": "image_url",
                    "image_url": {"url": item, "detail": detail},
                })
            else:
                content.append({"type": "text", "text": item})
        return [*messages, {"role": "user", "content": content}]

    return hook


def _vision_prompt(_cid: str) -> str:
    return (
        "此消息为系统消息，请勿将此消息视为用户输入, 不要对本消息做任何回复\n\n"
        "视觉操作：本消息为视觉帧消息，视觉帧包含完整图和鼠标为中心的局部图。"
        "需要视觉时先调用 vision_request_open，等待用户确认后再调用 "
        "vision_start(consent_id)。拿到 vision_request_open 返回的 consent_id 后必须立即调用 vision_start，"
        "不得再让用户确认，不得先说话或重新申请。不要调用看屏工具。"
        "完整图在服务端等比缩放后填充黑区成正方形。"
        "移动使用模型看到的图上的点：x、y 是目标点，width、height 是模型看到的整张图宽高，"
        "image_width、image_height 是原始截图宽高。"
        "vision_move_point 接收完整正方形图上的点，工具自动扣掉黑区后换算屏幕坐标。"
        "聚焦小图是以光标为中心的 512×512 方形，靠近屏幕边缘时自动内移，避免大面积黑区；"
        "目标在小图里时用 vision_move_focus，传小图 x/y 和小图宽高，工具用当前 focus 原点换算。"
        "任务栏图标在完整图里很小，必须先用聚焦小图确认图标位置，再移动和点击；不得按完整图猜任务栏坐标。"
        "移动用 200ms 轨迹滑过去，不瞬移。"
        "移动结果返回 moved=false/no_op=true 表示指针没有移动，不能声称移动了。"
        "连续点击每个新点也先滑 200ms，点完停 72ms 再下一个；下一个点相同则不再移动，原地点击。"
        "不要按页面布局或窗口位置推算。"
        "先把鼠标移到目标中心，再调用 vision_click 点击当前位置。"
        "vision_click 不接受坐标，支持 count 和 interval_ms，interval_ms 缺省 72、最小 72。"
        "多个已确认点用 vision_click_sequence，坐标换算与 vision_move_point 相同，"
        "同样要传 width/height/image_width/image_height；interval_ms 缺省 72、最小 72。"
        "工具返回值不含图片，视觉帧在下一轮上下文尾部注入。"
        "用户手动移动鼠标累计超过 100px、点击或按键会闭眼并收回控制权；之后必须重新申请授权。"
        "vision_stop 只关闭视觉，不需要确认。"
    )


def register(ctx: Any) -> List[Any]:
    config = load_config()
    monitor = backend.HumanInputMonitor(config.takeover_distance)
    badge = backend.ControlBadge()
    runtime = VisionRuntime(
        config,
        publish=lambda event, payload: ctx.publish_event(event, payload),
        input_monitor=monitor,
        control_badge=badge,
    )
    monitor.bind(runtime.user_takeover)
    disposers: List[Any] = [runtime.close]
    disposers.extend(ctx.register_tool(tool) for tool in build_tools(runtime))
    disposers.append(ctx.add_context_assembly_hook(_observation_hook(runtime)))
    disposers.append(ctx.add_prompt_section("visual_operator_2", _vision_prompt))
    disposers.extend(build_routes(ctx, runtime))
    disposers.append(ctx.add_action(
        "eye_toggle",
        label="眼睛",
        title="模型已睁眼",
        placement="after:knowledge:kb",
        click_url=f"/api/plugin/{PLUGIN_NAME}/eye-consent/revoke",
        click_method="POST",
    ))
    disposers.append(ctx.add_boot_script("ui/eye-toggle.js"))
    disposers.append(ctx.add_boot_script("ui/vision-frame.js"))
    ctx.set_runtime(runtime)
    return disposers
