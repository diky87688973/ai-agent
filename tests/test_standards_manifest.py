# -*- coding: utf-8 -*-
"""准则清单门禁：手册编号/版本与 standards_rules 常量双向一致。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "scripts"))

import check_standards_manifest as gate  # noqa: E402


class StandardsManifestGateTest(unittest.TestCase):
    def test_current_manifest_matches_constants(self) -> None:
        version, updated, ids = gate.read_manifest()
        self.assertEqual(gate.compare(version, updated, ids), [])

    def test_missing_extra_and_version_are_reported(self) -> None:
        version, updated, ids = gate.read_manifest()
        current = set(ids)
        missing_id = sorted(current)[0]
        problems = gate.compare(version, updated, current - {missing_id})
        self.assertTrue(any("缺少编号" in problem for problem in problems))
        problems = gate.compare(version, updated, current | {"A999"})
        self.assertTrue(any("多出编号" in problem for problem in problems))
        problems = gate.compare("0.0", updated, current)
        self.assertTrue(any("版本不一致" in problem for problem in problems))

    def test_skills_disabled_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "plugins.ini"
            path.write_text("[plugin:skills]\nenabled = 0\n", encoding="utf-8")
            self.assertFalse(gate.skills_enabled(path))


if __name__ == "__main__":
    unittest.main()
