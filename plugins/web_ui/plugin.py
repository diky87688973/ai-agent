# -*- coding: utf-8 -*-
"""基础 WEB-UI 插件：从 plugin-ui.json 注册页面区域。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, List

from agent.capabilities.plugin_ui_tree import register_ui_tree


def register(ctx: Any) -> List[Any]:
    return register_ui_tree(ctx, Path(__file__).with_name("plugin-ui.json"))


PLUGIN_VERSION = "1.0"
