# -*- coding: utf-8 -*-
"""经典界面内联打包。

把 CSS 与 JS 全部内联进一个 HTML，运行时页面零额外请求：
素材位于 `agent/shell/web_assets/classic/`，按下面的模块清单顺序拼成完整页面。

模块清单是唯一事实来源：`scripts/check_ui_js.py`、测试与验收脚本都从这里取，
新增/删除模块只改这一处。

四件关键细节：
  1. 顺序即语义：JS 模块共用一个 `<script>` 作用域，CSS 模块顺序即层叠顺序，
     调整清单顺序可能改变行为，不能随手重排；
  2. hljs 浅色 CSS 要做作用域隔离（`html[data-ui-theme="light"] .hljs`）——
     两套高亮配色同页共存，不隔离就会互相覆盖；
  3. JS 之间用 `;` 连接 —— 各文件末尾可能没有分号，直接拼会粘成语法错误；
  4. `{{APP_VERSION}}` 由服务端注入。
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

CLASSIC_DIR = Path(__file__).resolve().parent / "web_assets" / "classic"

#: 经典界面 JS 模块（相对 `classic/js/`，顺序即脚本执行顺序）。
UI_JS_MODULES = (
    "core/auth-client.js",
    "core/boot.js",
    "chat/todo.js",
    "chat/stream.js",
    "chat/confirm.js",
    "chat/conversation.js",
    "chat/history-paging.js",
    "composer/goal.js",
    "composer/state.js",
    "composer/pickers.js",
    "panels/panes.js",
    "plugins/host.js",
    "panels/file-viewer.js",
    "composer/model-sync.js",
    "composer/input.js",
    "render/paths.js",
    "render/markdown.js",
    "chat/bubbles.js",
    "chat/steps.js",
    "chat/context-usage.js",
    "tools/titles.js",
    "render/diff.js",
    "tools/previews.js",
    "chat/llm-rounds.js",
    "chat/tool-events.js",
    "chat/errors.js",
    "chat/send.js",
    "layout/splitters.js",
    "chat/queue.js",
    "chat/composer-layout.js",
    "chat/background-tasks.js",
    "chat/subagents.js",
    "shell/update.js",
    "shell/window-chrome.js",
)

#: 主脚本之前加载的脚本（vendor 与独立工具）。顺序同样有意义。
UI_PRE_JS_MODULES = (
    "js/theme-ui.js",
    "js/vendor/marked.min.js",
    "js/vendor/highlight.min.js",
    "js/code-highlight.js",
    "js/image-lightbox.js",
)

#: 主脚本之后加载的脚本：工具视图、文件图标、本回合编辑清单、设置页。
UI_POST_JS_MODULES = (
    "js/chat-tool-views.js",
    "js/file-icons.js",
    "js/edited-files.js",
    "js/settings-ui.js",
)

#: 经典界面 CSS 模块（相对 `classic/css/`，顺序即层叠顺序）。
UI_CSS_MODULES = (
    "reset.css",
    "layout.css",
    "chat-messages.css",
    "system-notice.css",
    "composer.css",
    "chat-queue.css",
    "background-tasks.css",
    "subagents.css",
    "update.css",
    "todo.css",
    "theme-light.css",
    "theme-tokens.css",
    "frame.css",
    "chat-tool-views.css",
    "chat-file-cards.css",
    "file-icons.css",
    "edited-files.css",
    "settings-ui.css",
    "theme-light-cursor.css",
    "side-tabs.css",
    "todo-card.css",
    "window-chrome.css",
)

_HTML_FILE = CLASSIC_DIR / "agent-ui.html"
_HLJS_DARK_CSS = CLASSIC_DIR / "css" / "vendor" / "hljs-github-dark.min.css"
_HLJS_LIGHT_CSS = CLASSIC_DIR / "css" / "vendor" / "hljs-github.min.css"

def _app_version() -> str:
    try:
        from agent.update.version import current_version
        return f"v{current_version()}"
    except Exception as exc:
        from agent.core.error_report import report_error
        report_error("agent.shell.web.ui_bundle.version", exc)
        return "v0.1.5"


APP_VERSION = _app_version()


def _read(path: Path) -> str:
    """读素材；缺文件时给空串——缺一个高亮库不该让整个页面 500。"""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def read_ui_js() -> str:
    """按清单顺序拼出经典界面同作用域脚本（测试与静态检查共用）。"""
    return "\n;".join(
        _read(CLASSIC_DIR / "js" / rel).rstrip("\n") for rel in UI_JS_MODULES
    )


def read_ui_css() -> str:
    """按清单顺序拼出经典界面样式（测试与静态检查共用）。"""
    return "\n\n".join(
        _read(CLASSIC_DIR / "css" / rel).rstrip("\n") for rel in UI_CSS_MODULES
    )


def scope_hljs_css(css: str, prefix: str) -> str:
    """把 `.hljs` 选择器限定到某主题下。

    负向后顾 `(?<![\\w-])` 是必要的：否则 `xxx.hljs` 这种也会被改到。
    """
    return re.sub(r"(?<![\w-])\.hljs", prefix + " .hljs", css)


def build_inline_css() -> str:
    """CSS 段：模块清单顺序 + hljs 深色 + hljs 浅色（作用域隔离）。"""
    parts = [
        read_ui_css(),
        _read(_HLJS_DARK_CSS),
        scope_hljs_css(_read(_HLJS_LIGHT_CSS), 'html[data-ui-theme="light"]'),
    ]
    return "\n\n".join(p for p in parts if p)


def build_inline_js() -> str:
    """JS 段：前置脚本 → 主脚本模块（共用作用域）→ 后置脚本，用 `;` 连接。

    `marked` 排在主脚本前：主脚本在顶层就引用 `window.marked`。
    """
    parts = [*(_read(CLASSIC_DIR / rel) for rel in UI_PRE_JS_MODULES),
             read_ui_js(),
             *(_read(CLASSIC_DIR / rel) for rel in UI_POST_JS_MODULES)]
    return "\n;".join(p.rstrip("\n") for p in parts if p)


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
    js_sources = {
        CLASSIC_DIR / rel for rel in UI_JS_MODULES + UI_PRE_JS_MODULES + UI_POST_JS_MODULES
    }
    css_sources = {CLASSIC_DIR / "css" / rel for rel in UI_CSS_MODULES}
    return all(p.is_file() for p in (
        _HTML_FILE, _HLJS_DARK_CSS, _HLJS_LIGHT_CSS, *js_sources, *css_sources,
    ))
