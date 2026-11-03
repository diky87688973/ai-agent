# -*- coding: utf-8 -*-
"""系统提示词 assemble 插口替换测试。"""
from __future__ import annotations

import unittest

from agent.capabilities.slot_registry import SlotRegistry
from agent.mechanisms.prompt_sections import ASSEMBLE_PATH, PromptSections


class PromptSlotTest(unittest.TestCase):
    def test_replace_prompt_assembly(self) -> None:
        slots = SlotRegistry()
        sections = PromptSections(slots)
        sections.add("## A", lambda cid: ["old"])
        self.assertEqual(sections.render("c"), ["## A\nold"])
        binding = slots.bind(
            ASSEMBLE_PATH, lambda cid: ["new"], owner="plugin", mode="replace")
        self.assertEqual(sections.render("c"), ["new"])
        binding.dispose()
        self.assertEqual(sections.render("c"), ["## A\nold"])


if __name__ == "__main__":
    unittest.main()
