# -*- coding: utf-8 -*-
"""经典界面展示开关：项目根 web-ui-config.ini 的 [web-ui] 节。

与内核 config.ini 分开，只决定界面画不画。
缺文件、缺节或空值时：对话区工具条目展示，步骤面板不绘制。
只有字符串 "1" 视为展示。
"""
from __future__ import annotations

import configparser
from pathlib import Path
from typing import Dict, Optional

from agent.config import PROJECT_ROOT

WEB_UI_CONFIG_PATH = PROJECT_ROOT / "web-ui-config.ini"


def _flag(raw: object, default: bool) -> bool:
    """空值回默认；只有 "1" 为开。"""
    text = str(raw or "").strip().strip("'\"")
    if not text:
        return default
    return text == "1"


def get_web_ui(path: Optional[Path] = None) -> Dict[str, bool]:
    """读取 [web-ui]。

    display_tool_items：对话区是否插入工具条目。
    display_tool_steps：右侧步骤面板是否绘制。
    """
    parser = configparser.ConfigParser()
    target = Path(path) if path is not None else WEB_UI_CONFIG_PATH
    if target.is_file():
        parser.read(str(target), encoding="utf-8-sig")
    values: Dict[str, str] = {}
    if parser.has_section("web-ui"):
        values = {k: str(v or "").strip() for k, v in parser.items("web-ui")}
    return {
        "display_tool_items": _flag(values.get("display_tool_items", ""), True),
        "display_tool_steps": _flag(values.get("display_tool_steps", ""), False),
    }
