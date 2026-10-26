# -*- coding: utf-8 -*-
"""更新资产归属：哪些插件配置不进入发布包。"""
from __future__ import annotations

from pathlib import Path

# 这些配置含用户凭据，不随更新包覆盖；更新时保留本地文件。
SENSITIVE_PLUGIN_CONFIGS = {
    "plugins/multi_model/plugin-config.ini",
}


def normalized(path: Path) -> str:
    return Path(path).as_posix().lstrip("./")


def is_sensitive_plugin_config(path: Path) -> bool:
    text = Path(path).as_posix().casefold()
    return any(text.endswith(str(item).casefold())
               for item in SENSITIVE_PLUGIN_CONFIGS)


def is_local_secret(path: Path) -> bool:
    name = Path(path).name.casefold()
    return (
        name == ".env"
        or name.endswith(".local.ini")
        or name.endswith(".local.toml")
        or name.endswith(".pem")
        or name.endswith(".key")
        or name.endswith(".p12")
        or name.endswith(".pfx")
    )
