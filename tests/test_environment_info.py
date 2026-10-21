# -*- coding: utf-8 -*-
"""环境章节：资源目录之后、编码准则之前，带本会话 ID。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.capabilities.registry import ToolRegistry  # noqa: E402
from agent.shell.environment_info import environment_section  # noqa: E402
from agent.shell.prompts import build_system_prompt  # noqa: E402


class EnvironmentSectionTest(unittest.TestCase):
    def test_section_is_after_resource_and_before_coding(self) -> None:
        cid = "0123456789abcdef0123456789abcdef"
        environment = environment_section(cid)
        prompt = build_system_prompt(
            registry=ToolRegistry(),
            extra_sections=["## 资源目录\n- 内置skills: /skills", environment],
        )
        self.assertIn("## 环境信息", prompt)
        self.assertIn(f"本会话ID: {cid}", prompt)
        self.assertLess(prompt.index("## 资源目录"), prompt.index("## 环境信息"))
        self.assertLess(prompt.index("## 环境信息"), prompt.index("## 编码准则"))


if __name__ == "__main__":
    unittest.main()
