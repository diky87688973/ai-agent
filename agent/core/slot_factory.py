# -*- coding: utf-8 -*-
"""factory 解析：`module:attr` → 可调用对象。

宿主实现从 `agent.*` 导入；插件实现按节点声明方定位，具体加载方式由启动器注入，
core 不自己建插件包。解析器是每节点一份，所以不必把路径塞进 factory 字符串。
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any, Callable, Optional

from agent.core.slot_config import SlotConfig
from agent.core.slot_spec import (
    HOST_OWNER,
    Resolver,
    SlotConfigError,
    is_plugin_factory,
)


def resolve_factory(spec: str) -> Callable[..., Any]:
    """把 `module:attr` 解析成可调用对象（只认宿主模块）。"""
    module_name, sep, attr = str(spec or "").partition(":")
    if not sep or not module_name or not attr:
        raise SlotConfigError(f"factory 必须是 module:attr：{spec!r}")
    try:
        factory = getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError) as exc:
        raise SlotConfigError(f"factory 不可解析：{spec}") from exc
    if not callable(factory):
        raise SlotConfigError(f"factory 不可调用：{spec}")
    return factory


#: 插件 factory 的解析器：由启动器注入，core 不自己建插件包。
#: 入参：声明方插件名、factory 原文、节点路径、插件根；返回可调用对象。
PluginFactories = Callable[[str, str, str, Path], Callable[..., Any]]


def missing_plugin_factories(origin: str, spec: str, path: str,
                            plugins_root: Path) -> Callable[..., Any]:
    """未注入插件解析器时的桩：直接报错，不静默回退到自建包。"""
    raise SlotConfigError(
        f"未注入插件 factory 解析器：{path}（factory={spec}，插件={origin}）。"
        "插件模块的包名与加载顺序归 capabilities 侧，core 不自行建立；"
        "需由启动器传入 plugin_factories（见 agent/boot/bootstrap.py）")


def plugin_factory(factories: PluginFactories, origin: str, spec: str,
                   path: str, plugins_root: Path) -> Callable[..., Any]:
    """插件声明的 factory → 可调用对象；失败时报节点、原文与插件名三样。"""
    if origin == HOST_OWNER:
        raise SlotConfigError(
            f"宿主节点不得引用插件实现：{path}（factory={spec}）")
    try:
        factory = factories(origin, spec, path, plugins_root)
    except SlotConfigError as exc:
        raise SlotConfigError(
            f"插件 factory 不可解析：{path}（factory={spec}，插件={origin}）：{exc}"
        ) from exc
    except (ImportError, AttributeError) as exc:
        raise SlotConfigError(
            f"插件 factory 不可解析：{path}（factory={spec}，插件={origin}）"
            f"：{type(exc).__name__}: {exc}") from exc
    if not callable(factory):
        raise SlotConfigError(
            f"插件 factory 不可调用：{path}（factory={spec}，插件={origin}）")
    return factory


def resolver_for(config: "SlotConfig", path: str,
                 factories: PluginFactories = missing_plugin_factories,
                 host: Optional[Resolver] = None,
                 ) -> Resolver:
    """给单个节点绑定解析器：同一个 factory 串，按节点归属走不同路径。

    `agent.*` 走宿主导入（可由 `host` 换掉，供测试注入）；其余一律当插件相对名，
    按 `origins[path]` 定位插件，具体怎么加载由注入的 `factories` 决定
    （core 不自己建插件包）。
    插件根取自 `config.plugins_root`：片段从哪来、工厂就从哪解析，不另传一个根。
    解析器是每节点一份，所以不需要把 path 塞进 factory 字符串里。
    """
    host_resolver = host or resolve_factory

    def resolve(spec: str) -> Callable[..., Any]:
        if not is_plugin_factory(spec):
            return host_resolver(spec)
        plugins_root = config.plugins_root
        if plugins_root is None:
            raise SlotConfigError(
                f"无 plugins_root，无法解析插件实现：{path}（factory={spec}，"
                f"插件={config.origin_of(path)}）。插件片段必须经 load_merged 带插件根加载")
        return plugin_factory(factories, config.origin_of(path), spec, path,
                              plugins_root)

    return resolve
