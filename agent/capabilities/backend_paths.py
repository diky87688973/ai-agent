# -*- coding: utf-8 -*-
"""后端扩展路径插口。"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from agent.capabilities.slot_registry import canonical_slot_path

#: Direct construction fallback; production boot passes the full manifest list.
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


def seed_backend_slots(paths: Any, backend: Iterable[Mapping[str, Any]]) -> None:
    for row in backend:
        paths.add_slot(
            canonical_slot_path(str(row["path"])), kind="container",
            children=str(row.get("children") or "none"),
            fixed_children=tuple(row.get("fixed") or ()), owner="*")


__all__ = ["BASE_BACKEND_SLOTS", "seed_backend_slots"]
