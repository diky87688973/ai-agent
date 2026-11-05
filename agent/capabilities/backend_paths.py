# -*- coding: utf-8 -*-
"""后端扩展路径插口：宿主后端扩展点的唯一协议表。

这张表是 `PluginHost.backend`（`PathRegistry`）的种子：插件贡献的每一条后端
路径都要先在它划定的父子范围内通过校验。表中的模式可以带 `<参数>` 段，
它们是匹配模板而不是可装配节点，因此以代码常量承载、不进入插口节点图。
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from agent.capabilities.slot_registry import canonical_slot_path

#: 后端扩展点协议：路径、子级策略与固定子级。
BASE_BACKEND_SLOTS = (
    {'path': 'backend/tools', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/tools/<tool>', 'children': 'fixed', 'fixed': ('executor', 'post-write')},
    {'path': 'backend/tools/subagents/visibility', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/tools/pipeline/pre-gates', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/tools/pipeline/pre-gates/<plugin>', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/tools/pipeline/post-observers', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/tools/pipeline/post-observers/<plugin>', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/context/sources', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/context/sources/<plugin>', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/context/assembly-hooks', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/context/assembly-hooks/<plugin>', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/context/usage-segments', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/context/usage-segments/<plugin>', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/prompt/sections', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/prompt/sections/<section>', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/prompt/mode-tails', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/events/subscriptions', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/events/subscriptions/<event>', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/http/routes', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/models/catalog', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/models/providers', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/models/routing', 'children': 'keyed', 'fixed': ()},
    {'path': 'backend/runtime', 'children': 'keyed', 'fixed': ()},
)


def seed_backend_slots(paths: Any, backend: Iterable[Mapping[str, Any]] = BASE_BACKEND_SLOTS) -> None:
    """把协议表登记进 `PathRegistry`；登记失败即抛，不静默跳过。"""
    for row in backend:
        paths.add_slot(
            canonical_slot_path(str(row["path"])), kind="container",
            children=str(row.get("children") or "none"),
            fixed_children=tuple(row.get("fixed") or ()), owner="*")


__all__ = ["BASE_BACKEND_SLOTS", "seed_backend_slots"]
