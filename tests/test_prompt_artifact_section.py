# -*- coding: utf-8 -*-
"""交付物章节：正文之外能直接看见的东西怎么写。

钉三件事：
  1. 基础提示词必须带「## 交付物」，否则模型只知有工具、不知输出格式；
  2. 段序在「编码准则」之后、「术语」之前，与 `prompts.py` 的拼装顺序一致；
  3. 章节只点名内置工具 —— 插件被卸载后提示词不得还指向不存在的工具。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.capabilities.registry import ToolRegistry  # noqa: E402
from agent.shell.prompts import build_system_prompt  # noqa: E402


def _prompt(mode: str = "auto") -> str:
    return build_system_prompt(registry=ToolRegistry(), mode=mode)


class ArtifactSectionTest(unittest.TestCase):
    """交付物章节的内容、位置与工具边界。"""

    def test_section_carries_output_mechanics(self) -> None:
        """内联语法、绝对路径、回看与临时目录这四条是章节的实际内容。"""

        prompt = _prompt()
        self.assertIn("## 交付物", prompt)
        for needle in ("![一句说明](绝对路径)", "绝对路径", "read_image",
                       "%TEMP%", "示意图", "`present`"):
            self.assertIn(needle, prompt, msg=needle)

    def test_section_sits_between_coding_and_terminology(self) -> None:
        """段序固定，术语表必须在它之后——否则「确认」两义会先入为主。"""

        prompt = _prompt()
        coding = prompt.index("## 编码准则")
        artifact = prompt.index("## 交付物")
        terminology = prompt.index("## 术语")
        self.assertLess(coding, artifact)
        self.assertLess(artifact, terminology)

    def test_every_mode_keeps_section(self) -> None:
        """模式段替换不得吞掉交付物章节。"""

        for mode in ("auto", "plan", "execute"):
            self.assertIn("## 交付物", _prompt(mode), msg=mode)

    def test_section_names_only_builtin_tools(self) -> None:
        """插件工具不写进基础提示词：卸载后提示词不能指向不存在的工具。"""

        prompt = _prompt()
        for plugin_tool in ("visualize", "vision_eye", "vision_click"):
            self.assertNotIn(plugin_tool, prompt, msg=plugin_tool)


if __name__ == "__main__":
    unittest.main()
