# -*- coding: utf-8 -*-
"""视觉操作 2.0：持续视觉、全局独占、用户授权与键鼠动作。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, List

from agent.capabilities.plugin_paths import load_plugin_paths
from agent.core.error_report import report_error

from . import backend, step_log
from .config import load_config
from .routes import build_routes
from .state import VisionRuntime
from .tools import build_tools

PATHS = load_plugin_paths(__file__)

PLUGIN_NAME = "visual_operator_2"


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


def _step_log_path(ctx: Any) -> Any:
    app = getattr(ctx, "app", None)
    context = getattr(app, "context", None) if app is not None else None
    if context is None or not callable(getattr(context, "has", None)):
        return None
    if not context.has("error_log"):
        return None
    error_log = context.get("error_log")
    path = getattr(error_log, "path", None)
    return Path(path).parent / "visual_operator_2.steps.log" if path else None


def register(ctx: Any) -> List[Any]:
    config = load_config()
    step_log.configure(_step_log_path(ctx))
    monitor = backend.HumanInputMonitor(config.takeover_distance)
    monitor.register_inject_tag(backend.FOREIGN_INJECT_TAG)
    badge = backend.ControlBadge()
    runtime = VisionRuntime(
        config,
        publish=lambda event, payload: ctx.publish_event(event, payload),
        input_monitor=monitor,
        control_badge=badge,
    )
    monitor.bind(runtime.user_takeover)
    disposers: List[Any] = [runtime.close]
    try:
        disposers.extend(ctx.register_tool(tool) for tool in build_tools(runtime))
        disposers.append(ctx.add_context_assembly_hook(
            _observation_hook(runtime),
            path="app/backend/context/assembly-hooks/visual_operator_2/observations"))
        disposers.append(ctx.add_prompt_section(
            "visual_operator_2", _vision_prompt,
            path="app/backend/prompt/sections/visual_operator_2/discipline",
            after_tools=True))
        disposers.extend(build_routes(ctx, runtime))
        disposers.append(ctx.add_ui_item(
            PATHS["button"], kind="button",
            props={"label": "眼睛", "action": "visual.toggle",
                   "binding": {"input": {"standalone": True,
                                          "className": "mode-plus vision-eye-btn",
                                          "action": "visual.toggle",
                                          "text": "眼睛",
                                          "hidden": True,
                                          "host": ".left-tools"}},
                   "scripts": ["ui/eye-toggle.js", "ui/vision-frame.js"],
                   "styles": ["ui/vision-frame.css"]}, order=60))
        ctx.set_runtime(runtime)
    except Exception:
        for dispose in reversed(disposers):
            try:
                dispose()
            except Exception as exc:
                report_error("plugins.visual_operator_2.register_rollback", exc)
        raise
    return disposers
