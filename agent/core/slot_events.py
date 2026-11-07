"""事件节点契约：宿主常量或声明式插件事件依赖。"""
from __future__ import annotations

import re
from typing import Mapping

from agent.core.slot_spec import EVENT_NAMES, SlotSpec

CHANNEL_PATH = re.compile(r"app/plugins/[A-Za-z0-9_-]+/events/[a-z][a-z0-9_-]*")


def event_type(spec: SlotSpec, specs: Mapping[str, SlotSpec]) -> str:
    """从显式事件依赖或宿主常量派生总线键，不创建第二份注册表。"""
    target = spec.requires.get("event")
    if target is not None:
        if spec.scope != "app":
            raise ValueError(f"插件事件订阅必须使用 app 作用域：{spec.path}")
        channel = specs.get(target)
        if channel is None or channel.kind != "event-channel":
            raise ValueError(f"事件依赖必须引用已声明的 event-channel：{spec.path} -> {target}")
        return channel.path
    matches = [part for part in spec.path.split("/") if part in EVENT_NAMES]
    if len(matches) != 1:
        raise ValueError(f"event 节点必须引用 event-channel 或包含唯一 event_name 常量：{spec.path}")
    return matches[0]


def channel_problem(spec: SlotSpec) -> str:
    """插件自有事件只能声明在自身事件命名空间，且不构造运行时对象。"""
    if (not CHANNEL_PATH.fullmatch(spec.path) or spec.scope != "app" or
            spec.factory or spec.requires or spec.children != "none"):
        return f"event-channel 必须是 app/plugins/<owner>/events/<name> 下无工厂、无依赖的 app 级叶节点：{spec.path}"
    return ""
