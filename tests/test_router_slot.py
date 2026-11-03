# -*- coding: utf-8 -*-
"""模型路由 slot 的替换与回退。"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from agent.capabilities.slot_registry import SlotRegistry
from agent.mechanisms.provider_router import ROUTER_PATH, ProviderRouter


class _Provider:
    def __init__(self, tag):
        self.tag = tag
        self.model = tag

    def stream(self, request):
        yield self.tag


class RouterSlotTest(unittest.TestCase):
    def test_replace_router_selection(self) -> None:
        slots = SlotRegistry()
        router = ProviderRouter(
            default=_Provider("default"),
            resolve=lambda mid: _Provider("default"),
            default_id="default",
            slots=slots,
        )
        request = SimpleNamespace(model="")
        self.assertEqual(list(router.stream(request)), ["default"])
        binding = slots.bind(
            ROUTER_PATH,
            lambda request, mid, allowed, fallback, resolve: _Provider("new"),
            owner="plugin",
            mode="replace",
        )
        self.assertEqual(list(router.stream(request)), ["new"])
        binding.dispose()
        self.assertEqual(list(router.stream(request)), ["default"])


if __name__ == "__main__":
    unittest.main()
