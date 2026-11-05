# -*- coding: utf-8 -*-
"""插件身份与数据目录的共享读法。

装配器与插件宿主都要读 `plugin-meta.json`、都要把插件名拼成目录名，
所以实现放在 core 这一层，上层引用同一份，不各写一份。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Mapping

#: 插件身份文件名。
PLUGIN_META_FILE = "plugin-meta.json"

#: 插件 meta 的编码：文件可能带 UTF-8 BOM，`utf-8-sig` 会吞掉它，
#: 对无 BOM 文件行为与 `utf-8` 完全一致。
PLUGIN_META_ENCODING = "utf-8-sig"


def safe_dir_name(name: str) -> str:
    """插件名 → 合法目录名：只留 `[A-Za-z0-9_-]`，其余换成 `_`。

    插件名会拼进文件路径，不净化就能用 `..` 或斜杠越出 `plugin/` 目录。
    """
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(name or "")).strip("_")
    return cleaned or "plugin"


def read_plugin_meta(plugin_root: Any) -> Dict[str, Any]:
    """读插件的身份声明；文件缺失或不是合法对象时返回空表。

    「没有身份声明」不是错误，调用方按空表处理；「文件损坏」也按缺失处理，
    与既有插件发现路径一致 —— 身份只影响展示，不阻断装载。
    """
    path = Path(plugin_root) / PLUGIN_META_FILE
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding=PLUGIN_META_ENCODING))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, Mapping):
        return {}
    return dict(data)


__all__ = ["PLUGIN_META_ENCODING", "PLUGIN_META_FILE", "read_plugin_meta",
           "safe_dir_name"]
