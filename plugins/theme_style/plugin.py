# -*- coding: utf-8 -*-
"""主题风格插件：界面风格设置与风格资源加载。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.capabilities.plugin_paths import load_plugin_paths
from agent.core.error_report import report_error

PATHS = load_plugin_paths(__file__)



STYLE_ID = "theme_style"
DEFAULT_STYLE = "dsh"
STYLES = {"dsh", "minimal"}


def _state_path(ctx: Any) -> Optional[Path]:
    root = getattr(ctx, "data_dir", None)
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


def register(ctx: Any) -> List[Any]:
    def get_style(_args: Dict[str, Any]) -> Any:
        return 200, {"ok": True, "style": _load_style(ctx)}

    def save_style(value: Any) -> Dict[str, Any]:
        return _save_style(ctx, value)

    return [
        ctx.add_settings_item(
            PATHS["panel"], "theme_style",
            kind="select", label="界面风格", default=DEFAULT_STYLE,
            options=(
                {"value": "dsh", "label": "DSH 风格"},
                {"value": "minimal", "label": "极简风格"},
            ),
            hint="保存后立即切换；关闭插件回到 DSH 风格。",
            save=save_style,
            load=lambda: _load_style(ctx),
        ),
        ctx.add_route(
            "GET", "style", get_style,
            slot_path="app/backend/http/routes/theme_style-style"),
        ctx.add_ui_item(PATHS["button"], kind="button",
                        props={"label": "黑白切换", "action": "theme.toggle",
                               "binding": {"nav": "theme"},
                               "scripts": ["ui/theme-style.js"]}, order=1),
    ]
