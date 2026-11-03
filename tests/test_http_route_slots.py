# -*- coding: utf-8 -*-
"""HTTP route slot 的绑定、替换和回退。"""
from __future__ import annotations

import unittest

from agent.capabilities.slot_registry import SlotRegistry, route_slot_path
from agent.shell.web.web_route_slots import HttpRouteSlots
from agent.shell.web.web_routes import Handler


class HttpRouteSlotsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.slots = SlotRegistry()
        self.routes = HttpRouteSlots(self.slots)

    def test_default_bind_and_replace(self) -> None:
        self.routes.ensure_default("GET", "/health", lambda h, q, b=None: (200, {"old": True}))
        self.assertEqual(self.routes.resolve("GET", "/health")(None, {})[1],
                         {"old": True})
        binding = self.routes.bind(
            "GET", "/health", lambda h, q, b=None: (200, {"new": True}), "plugin")
        self.assertEqual(self.routes.resolve("GET", "/health")(None, {})[1],
                         {"new": True})
        binding.dispose()
        self.assertEqual(self.routes.resolve("GET", "/health")(None, {})[1],
                         {"old": True})

    def test_handler_dispatches_bound_route(self) -> None:
        self.routes.bind(
            "POST", "/api/chat/send",
            lambda handler, query, body=None: (201, {"bound": True}), "plugin")
        fake = type("Fake", (), {
            "shell": type("Shell", (), {"route_slots": self.routes})(),
            "_json": lambda self, status, payload: setattr(self, "response",
                                                           (status, payload)),
        })()
        self.assertTrue(Handler._slot_http(fake, "POST", "/api/chat/send", {}, {}))
        self.assertEqual(fake.response, (201, {"bound": True}))

    def test_post_slot_can_be_bound(self) -> None:
        binding = self.routes.bind(
            "POST", "/api/chat/send",
            lambda h, q, b=None: (201, {"method": "POST"}), "plugin")
        self.assertEqual(
            self.routes.resolve("POST", "/api/chat/send")(None, {}, {})[1],
            {"method": "POST"})
        binding.dispose()
        self.assertIsNone(self.routes.resolve("POST", "/api/chat/send"))

    def test_slot_can_be_bound(self) -> None:
        key = route_slot_path("GET", "/api/chat/history")
        self.assertIsNone(self.routes.resolve("GET", "/api/chat/history"))
        binding = self.routes.bind(
            "GET", "/api/chat/history",
            lambda h, q, b=None: (200, {"new": True}), "plugin")
        self.assertEqual(self.routes.resolve("GET", "/api/chat/history")(None, {})[1],
                         {"new": True})
        binding.dispose()
        self.assertIsNone(self.routes.resolve("GET", "/api/chat/history"))

    def test_path_is_injective(self) -> None:
        self.assertEqual(
            self.routes.path("GET", "/api/plugins/loaded"),
            route_slot_path("GET", "/api/plugins/loaded"),
        )
        self.assertNotEqual(
            self.routes.path("GET", "/api/chat/send"),
            self.routes.path("GET", "/api/chat_send"),
        )


if __name__ == "__main__":
    unittest.main()
