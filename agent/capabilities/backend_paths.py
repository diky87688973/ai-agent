# -*- coding: utf-8 -*-
"""后端扩展路径插口。"""
from __future__ import annotations

from typing import Any


def seed_backend_slots(paths: Any) -> None:
    slots = (
        ("backend/tools", "keyed", ()),
        ("backend/tools/<tool>", "fixed", ("executor", "post-write")),
        ("backend/tools/subagents/visibility", "keyed", ()),
        ("backend/tools/pipeline/pre-gates", "keyed", ()),
        ("backend/tools/pipeline/pre-gates/<plugin>", "keyed", ()),
        ("backend/tools/pipeline/post-observers", "keyed", ()),
        ("backend/tools/pipeline/post-observers/<plugin>", "keyed", ()),
        ("backend/context/sources", "keyed", ()),
        ("backend/context/sources/<plugin>", "keyed", ()),
        ("backend/context/assembly-hooks", "keyed", ()),
        ("backend/context/assembly-hooks/<plugin>", "keyed", ()),
        ("backend/context/usage-segments", "keyed", ()),
        ("backend/context/usage-segments/<plugin>", "keyed", ()),
        ("backend/prompt/sections", "keyed", ()),
        ("backend/prompt/sections/<section>", "keyed", ()),
        ("backend/prompt/mode-tails", "keyed", ()),
        ("backend/events/subscriptions", "keyed", ()),
        ("backend/events/subscriptions/<event>", "keyed", ()),
        ("backend/http/routes", "keyed", ()),
        ("backend/models/catalog", "keyed", ()),
        ("backend/models/providers", "keyed", ()),
        ("backend/models/routing", "keyed", ()),
        ("backend/runtime", "keyed", ()),
    )
    for pattern, children, fixed in slots:
        paths.add_slot(pattern, kind="container", children=children,
                       fixed_children=fixed, owner="*")


__all__ = ["seed_backend_slots"]
