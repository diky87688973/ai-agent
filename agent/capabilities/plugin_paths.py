# -*- coding: utf-8 -*-
"""插件 UI/设置路径清单：只保存路径，不保存实现。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def load_plugin_paths(plugin_file: Any) -> Dict[str, str]:
    path = Path(plugin_file).with_name("plugin-ui.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    data = raw.get("paths", raw) if isinstance(raw, dict) else {}
    return {str(k): str(v) for k, v in data.items()}


__all__ = ["load_plugin_paths"]
