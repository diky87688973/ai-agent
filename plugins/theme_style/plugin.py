# -*- coding: utf-8 -*-
"""主题风格插件：界面风格设置与风格资源加载。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from agent.core.error_report import report_error
from agent.core.slot_spec import SettingDecl

DEFAULT_STYLE = "dsh"
STYLE_OPTIONS = (
    {"value": "dsh", "label": "DSH 风格"},
    {"value": "minimal", "label": "极简风格"},
    {"value": "glass", "label": "玻璃风格"},
)
STYLES = {option["value"] for option in STYLE_OPTIONS}


def _state_path(ctx: Any) -> Optional[Path]:
    root = ctx.data_dir
    return Path(root) / "style.json" if root is not None else None


def _load_style(ctx: Any) -> str:
    path = _state_path(ctx)
    if path is None or not path.is_file():
        return DEFAULT_STYLE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = str(payload.get("style") or DEFAULT_STYLE)
        return value if value in STYLES else DEFAULT_STYLE
    except (OSError, ValueError, TypeError) as exc:
        report_error("plugins.theme_style._load_style", exc)
        return DEFAULT_STYLE


def _save_style(ctx: Any, value: Any) -> Dict[str, Any]:
    style = str(value or "").strip()
    if style not in STYLES:
        return {"ok": False, "error": f"未知风格：{style}"}
    path = _state_path(ctx)
    if path is None:
        return {"ok": False, "error": "插件数据目录未接入"}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"style": style}, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


def make_runtime(ctx: Any) -> Dict[str, Any]:
    """装配期运行时：本插件唯一的状态是数据目录里的 style.json。"""
    return {"ctx": ctx}


def make_setting(ctx: Any, runtime: Dict[str, Any]) -> SettingDecl:
    """界面风格条目声明。

    `save` / `load` 是函数，写不进 JSON，所以只能在 factory 里闭包捕获 runtime；
    props 只承载展示形状。
    """
    owner = runtime["ctx"]
    return SettingDecl(
        kind="select",
        label="界面风格",
        default=DEFAULT_STYLE,
        options=STYLE_OPTIONS,
        hint="保存后立即切换；关闭插件回到 DSH 风格。",
        save=lambda value: _save_style(owner, value),
        load=lambda: _load_style(owner),
    )


def make_style_route(ctx: Any, runtime: Dict[str, Any],
                     ) -> Callable[[Dict[str, Any]], Any]:
    """`GET style`：返回当前风格名。"""
    owner = runtime["ctx"]

    def handler(_args: Dict[str, Any]) -> Any:
        return 200, {"ok": True, "style": _load_style(owner)}
    return handler
