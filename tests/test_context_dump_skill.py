# -*- coding: utf-8 -*-
"""内置 Skills：上下文导出指导。"""
from __future__ import annotations

import unittest
from pathlib import Path

from plugins.skills.library import SkillManager

_ROOT = Path(__file__).resolve().parent.parent


class ContextDumpSkillTest(unittest.TestCase):
    def setUp(self) -> None:
        self.library = SkillManager(None, builtin_dir=_ROOT / "skills")

    def test_skill_is_listed_and_readable(self) -> None:
        names = self.library.list_skill_names()
        self.assertIn("context-dump", names)
        text = self.library.get_skill("context-dump") or ""
        self.assertIn("scripts/dump_context.py", text)
        self.assertIn("--cid", text)
        self.assertIn("data/temp/qa-context", text)


if __name__ == "__main__":
    unittest.main()
