# -*- coding: utf-8 -*-
"""基础 WEB-UI 插件：页面区域和基础插口。"""
from __future__ import annotations

from typing import Any, List

SLOTS = (
    ("web-ui", "fixed", ("nav", "chat", "input", "left-panel",
                         "right-panel", "runtime", "settings")),
    ("web-ui/nav", "fixed", ("buttons",)),
    ("web-ui/nav/buttons", "keyed", ()),
    ("web-ui/chat", "fixed", ("messages",)),
    ("web-ui/chat/messages", "fixed", ("user_msg", "ai_msg", "tools")),
    ("web-ui/chat/messages/tools", "keyed", ()),
    ("web-ui/input", "fixed", ("textarea", "buttons", "right-buttons")),
    ("web-ui/input/buttons", "keyed", ()),
    ("web-ui/input/right-buttons", "keyed", ()),
    ("web-ui/left-panel", "fixed", ("sessions", "context_usage")),
    ("web-ui/left-panel/sessions", "fixed", ("new", "list")),
    ("web-ui/left-panel/context_usage", "keyed", ()),
    ("web-ui/right-panel", "keyed", ()),
    ("web-ui/runtime", "fixed", ("left-panel", "right-panel")),
    ("web-ui/runtime/left-panel", "keyed", ()),
    ("web-ui/runtime/right-panel", "keyed", ()),
    ("web-ui/settings", "none", ()),
)


ITEMS = (
    ("web-ui/right-panel/steps", {"label": "步骤", "action": "panel.steps"}, 0),
    ("web-ui/right-panel/open_file", {"label": "打开文件", "action": "panel.open_file"}, None),
    ("web-ui/input/buttons/image_btn", {"label": "图片", "action": "input.image"}, 10),
    ("web-ui/input/buttons/mode_btn", {"label": "Auto+", "action": "input.mode"}, 20),
    ("web-ui/input/buttons/thinking_btn", {"label": "思考深度", "action": "input.thinking"}, 30),
    ("web-ui/input/right-buttons/goal_btn", {"label": "目标", "action": "input.goal"}, 10),
    ("web-ui/input/right-buttons/send_btn", {"label": "发送", "action": "input.send"}, 20),
    ("web-ui/input/right-buttons/stop_btn", {"label": "停止", "action": "input.stop"}, 30),
    ("web-ui/runtime/left-panel/inbox", {"label": "消息队列", "action": "runtime.inbox"}, 0),
    ("web-ui/runtime/right-panel/background_task", {"label": "后台任务", "action": "runtime.background"}, 0),
    ("web-ui/runtime/right-panel/subagent", {"label": "子智能体", "action": "runtime.subagent"}, None),
)


def register(ctx: Any) -> List[Any]:
    disposers: List[Any] = []
    for path, children, fixed in SLOTS:
        disposers.append(ctx.add_ui_slot(
            path, kind="container", children=children,
            fixed_children=fixed, owner="*"))
    for path, props, order in ITEMS:
        disposers.append(ctx.add_ui_item(path, kind="button", props=props, order=order))
    return disposers


PLUGIN_VERSION = "1.0"
