# -*- coding: utf-8 -*-
"""静默异常门禁：结构判据的正负例。"""
from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

import check_silent_except as gate  # noqa: E402


def _handler(source: str) -> ast.ExceptHandler:
    tree = ast.parse(source)
    return next(n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler))


class SilentExceptStructureTest(unittest.TestCase):
    def test_broad_pass_is_rejected(self) -> None:
        handler = _handler("try:\n    f()\nexcept Exception:\n    pass\n")
        self.assertTrue(gate._broad(handler))
        self.assertTrue(gate._only_pass_continue(handler))

    def test_pass_in_multi_statement_is_rejected(self) -> None:
        handler = _handler(
            "try:\n    f()\nexcept Exception:\n    report_error('x', None)\n    pass\n"
        )
        self.assertTrue(gate._has_pass(handler))

    def test_narrow_return_is_allowed(self) -> None:
        handler = _handler("try:\n    f()\nexcept OSError:\n    return None\n")
        self.assertFalse(gate._broad(handler))
        self.assertFalse(gate._only_pass_continue(handler))

    def test_explicit_result_is_recognized(self) -> None:
        handler = _handler(
            "try:\n    f()\nexcept Exception as exc:\n    result = ToolResult(error=str(exc))\n"
        )
        self.assertTrue(gate._transforms(handler))

    def test_report_error_is_recognized(self) -> None:
        handler = _handler(
            "try:\n    f()\nexcept Exception as exc:\n    report_error('x', exc)\n"
        )
        self.assertTrue(gate._reports(handler))

    def test_arbitrary_call_is_not_a_transform(self) -> None:
        handler = _handler(
            "try:\n    f()\nexcept Exception:\n    result = build()\n"
        )
        self.assertFalse(gate._transforms(handler))

    def test_report_error_needs_payload(self) -> None:
        handler = _handler(
            "try:\n    f()\nexcept Exception:\n    report_error('x')\n"
        )
        self.assertFalse(gate._reports(handler))

    def test_suppress_exception_is_rejected(self) -> None:
        tree = ast.parse("with suppress(Exception):\n    f()\n")
        self.assertTrue(gate._broad_suppress(tree))


class SilentExceptGateRunTest(unittest.TestCase):
    def test_main_fails_on_broad_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "agent").mkdir()
            (root / "agent" / "bad.py").write_text(
                "try:\n    f()\nexcept Exception:\n    pass\n", encoding="utf-8"
            )
            with mock.patch.object(gate, "ROOT", root), \
                 mock.patch.object(gate, "SCAN_DIRS", ("agent",)):
                self.assertEqual(gate.main([]), 1)

    def test_main_passes_on_narrow_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "agent").mkdir()
            (root / "agent" / "ok.py").write_text(
                "try:\n    f()\nexcept OSError:\n    return None\n", encoding="utf-8"
            )
            with mock.patch.object(gate, "ROOT", root), \
                 mock.patch.object(gate, "SCAN_DIRS", ("agent",)):
                self.assertEqual(gate.main([]), 0)


if __name__ == "__main__":
    unittest.main()
