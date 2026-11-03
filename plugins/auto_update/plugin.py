# -*- coding: utf-8 -*-
"""自动更新插件：版本更新按钮。"""
from __future__ import annotations

from typing import Any, List

from agent.capabilities.plugin_paths import load_plugin_paths

PATHS = load_plugin_paths(__file__)



PLUGIN_VERSION = "1.0"


def register(ctx: Any) -> List[Any]:
    return [
        ctx.add_ui_item(
            PATHS["button"], kind="button",
            props={"label": "版本更新", "action": "auto_update.check",
                   "binding": {"nav": "update", "persistent": True,
                               "hidden": True, "className": "update-btn ui-nav-btn"},
                   "scripts": ["ui/update.js"]}, order=0),
    ]
