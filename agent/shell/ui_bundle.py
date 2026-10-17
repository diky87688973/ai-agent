# -*- coding: utf-8 -*-
"""经典界面内联打包。

把 CSS 与 JS **全部内联进一个 HTML**，运行时页面零额外请求：
素材位于 `agent/shell/web_assets/classic/`，
这里负责在进程启动时拼成一份完整 HTML。

三处关键细节：
  1. **hljs 浅色 CSS 要做作用域隔离**（`html[data-ui-theme="light"] .hljs`）——
     两套高亮配色同页共存，不隔离就会互相覆盖；
  2. JS 之间用 `;` 连接 —— 各文件末尾可能没有分号，直接拼会粘成语法错误；
  3. `{{APP_VERSION}}` 由服务端注入。
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

CLASSIC_DIR = Path(__file__).resolve().parent / "web_assets" / "classic"

_HTML_FILE = CLASSIC_DIR / "agent-ui.html"
_RESET_CSS = CLASSIC_DIR / "css" / "reset.css"
_UI_CSS = CLASSIC_DIR / "css" / "agent-ui.css"
_TOOL_CSS = CLASSIC_DIR / "css" / "chat-tool-views.css"
_EDITED_CSS = CLASSIC_DIR / "css" / "edited-files.css"
_SETTINGS_CSS = CLASSIC_DIR / "css" / "settings-ui.css"
_HLJS_DARK_CSS = CLASSIC_DIR / "css" / "vendor" / "hljs-github-dark.min.css"
_HLJS_LIGHT_CSS = CLASSIC_DIR / "css" / "vendor" / "hljs-github.min.css"
_THEME_JS = CLASSIC_DIR / "js" / "theme-ui.js"
_MARKED_JS = CLASSIC_DIR / "js" / "vendor" / "marked.min.js"
_HLJS_JS = CLASSIC_DIR / "js" / "vendor" / "highlight.min.js"
_CODE_HIGHLIGHT_JS = CLASSIC_DIR / "js" / "code-highlight.js"
_LIGHTBOX_JS = CLASSIC_DIR / "js" / "image-lightbox.js"
_UI_JS = CLASSIC_DIR / "js" / "agent-ui.js"
_TOOL_JS = CLASSIC_DIR / "js" / "chat-tool-views.js"
_EDITED_JS = CLASSIC_DIR / "js" / "edited-files.js"
_SETTINGS_JS = CLASSIC_DIR / "js" / "settings-ui.js"

APP_VERSION = "v0.1"


def _read(path: Path) -> str:
    """读素材；缺文件时给空串——缺一个高亮库不该让整个页面 500。"""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def scope_hljs_css(css: str, prefix: str) -> str:
    """把 `.hljs` 选择器限定到某主题下。

    负向后顾 `(?<![\\w-])` 是必要的：否则 `xxx.hljs` 这种也会被改到。
    """
    return re.sub(r"(?<![\w-])\.hljs", prefix + " .hljs", css)


def build_inline_css() -> str:
    """CSS 段：reset + 主样式 + hljs 深色 + hljs 浅色（作用域隔离）。"""
    parts = [
        _read(_RESET_CSS).rstrip(),
        _read(_UI_CSS),
        _read(_TOOL_CSS),
        _read(_EDITED_CSS),
        _read(_SETTINGS_CSS),
        _read(_HLJS_DARK_CSS),
        scope_hljs_css(_read(_HLJS_LIGHT_CSS), 'html[data-ui-theme="light"]'),
    ]
    return "\n\n".join(p for p in parts if p)


def build_inline_js() -> str:
    """JS 段：主题 → markdown 解析器 → 高亮库 → 高亮封装 → 灯箱 → 主脚本 → 工具视图 → 本轮编辑清单 → 设置页，用 `;` 连接。

    `marked` 排在主脚本前：主脚本在顶层就引用 `window.marked`。
    """
    parts = [
        _read(_THEME_JS),
        _read(_MARKED_JS),
        _read(_HLJS_JS),
        _read(_CODE_HIGHLIGHT_JS),
        _read(_LIGHTBOX_JS),
        _read(_UI_JS),
        _read(_TOOL_JS),
        _read(_EDITED_JS),
        _read(_SETTINGS_JS),
    ]
    return "\n;".join(p for p in parts if p)


@lru_cache(maxsize=1)
def inline_ui_html(version: Optional[str] = None) -> str:
    """拼出可直接返回给浏览器的完整 HTML（结果缓存，启动后不再读盘）。"""
    template = _read(_HTML_FILE)
    if not template:
        return (
            "<!doctype html><meta charset='utf-8'>"
            "<h1>经典界面素材缺失</h1>"
            f"<p>期望目录：{CLASSIC_DIR}</p>"
        )
    return (
        template.replace("{{CSS}}", build_inline_css())
        .replace("{{agent-ui.js}}", build_inline_js())
        .replace("{{APP_VERSION}}", str(version or APP_VERSION))
    )


def classic_assets_present() -> bool:
    """素材是否齐全（供 /health 自检）。"""
    return all(p.is_file() for p in (
        _HTML_FILE, _RESET_CSS, _UI_CSS, _TOOL_CSS, _EDITED_CSS, _HLJS_DARK_CSS, _HLJS_LIGHT_CSS,
        _THEME_JS, _MARKED_JS, _HLJS_JS, _CODE_HIGHLIGHT_JS, _LIGHTBOX_JS, _UI_JS,
        _TOOL_JS, _EDITED_JS, _SETTINGS_CSS, _SETTINGS_JS,
    ))
