# -*- coding: utf-8 -*-
"""启动配置：自装配树运行期所需的全部外部输入。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from agent.config import PROJECT_ROOT


@dataclass(frozen=True)
class HostBootConfig:
    """宿主服务装配所需的运行配置。"""

    data_root: Any
    live_state: Any = None
    mesh: Any = None
    slots: Any = None
    executors: Any = None
    provider: Any = None
    available: Any = ()
    default_model: str = ""
    store: Any = None
    context_factory: Any = None
    compactor_factory: Any = None
    plugins_root: Any = None
    plugin_data_root: Any = None
    project_root: Any = PROJECT_ROOT


@dataclass(frozen=True)
class BootConfig:
    data_root: Any
    host_config: Any
    backup_root: Any = None
    recycle_root: Any = None
    backup_retention_days: Any = None
    context_defaults: Dict[str, Any] = None
    image_turns: int = 1
    image_max: int = 8
    max_passes: int = 10
    available: tuple = ()
    default_model: str = ""
    config_ready: bool = False
    plugin_manifest: Any = ()


__all__ = ["BootConfig", "HostBootConfig"]
