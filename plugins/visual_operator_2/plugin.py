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
        "视觉操作：当前画面由内核自动注入，包含完整图和鼠标局部图。"
        "需要视觉时先调用 vision_request_open，等待用户确认后再调用 "
        "vision_start(consent_id)。不要调用看屏工具。"
        "完整图在服务端非等比拉伸成正方形，不填黑边，避免模型层再加黑边。"
        "移动使用模型看到的图上的点：x、y 是目标点，width、height 是模型看到的整张图宽高，"
        "image_width、image_height 是原始截图宽高。"
        "vision_move_point 按屏幕宽 / 模型图宽 * x、屏幕高 / 模型图高 * y 换算；两个方向独立。"
        "不要按页面布局或窗口位置推算。"
        "先把鼠标移到目标中心，再调用 vision_click 点击当前位置。"
        "多个已确认点用 vision_click_sequence，坐标换算与 vision_move_point 相同，"
        "同样要传 width/height/image_width/image_height；interval_ms 缺省 60，最小 60。"
        "vision_click 不接受坐标，一次只点一下。"
        "工具返回值不含图片，视觉帧在下一轮上下文尾部注入。"
        "用户手动操作鼠标或键盘会立即闭眼并收回控制权，之后必须重新申请授权。"
        "vision_stop 只关闭视觉，不需要确认。"
    )


def register(ctx: Any) -> List[Any]:
    config = load_config()
    monitor = backend.HumanInputMonitor()
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
