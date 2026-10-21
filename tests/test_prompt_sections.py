# -*- coding: utf-8 -*-
"""系统提示词章节：同章节合并，注入位置在用户规则之前。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.capabilities.registry import ToolRegistry  # noqa: E402
from agent.mechanisms.prompt_sections import PromptSections  # noqa: E402
from agent.shell.prompts import build_system_prompt  # noqa: E402


class PromptSectionsTest(unittest.TestCase):
    """同名章节合并与系统提示词注入位置。"""

    def test_same_heading_is_merged_once(self) -> None:
        sections = PromptSections()
        sections.add("## 资源目录", lambda _cid: ["系统skills: /system"], rank=0)
        sections.add("## 资源目录", lambda _cid: ["用户skills: /user"], rank=1)
        got = sections.render("cid")
        self.assertEqual(got, ["## 资源目录\n系统skills: /system\n用户skills: /user"])

    def test_extra_sections_sit_inside_the_system_prompt(self) -> None:
        prompt = build_system_prompt(
            registry=ToolRegistry(),
            user_rules="规则正文",
            extra_sections=["## 资源目录\n系统skills: /system"],
        )
        self.assertIn("## 资源目录\n系统skills: /system", prompt)
        self.assertLess(prompt.index("## 资源目录"), prompt.index("## 用户自定义规则"))


if __name__ == "__main__":
    unittest.main()
