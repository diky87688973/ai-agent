# -*- coding: utf-8 -*-
"""自动更新插件：版本更新按钮。"""
from __future__ import annotations

from typing import Any, List

PLUGIN_VERSION = "1.0"


def register(ctx: Any) -> List[Any]:
    return [
        ctx.add_ui_item(
            "web-ui/nav/buttons/update", kind="button",
            props={"label": "版本更新", "action": "auto_update.check",
                   "scripts": ["ui/update.js"]}, order=0),
    ]
