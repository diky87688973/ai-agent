# -*- coding: utf-8 -*-
"""present 工具：只返回文件元信息，不读取正文。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.capabilities.builtin.present_tool import PresentTool  # noqa: E402


class PresentToolTest(unittest.TestCase):
    def test_returns_metadata_without_reading_content(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            text = root / "note.txt"
            image = root / "shot.png"
            text.write_text("不该出现在结果里", encoding="utf-8")
            image.write_bytes(b"\x89PNG\r\n\x1a\n")
            result = PresentTool().execute({"files": [
                {"path": str(text)},
                {"path": str(image), "title": "截图"},
            ]})
            self.assertEqual(result["count"], 2)
            self.assertEqual(result["files"][0]["name"], "note.txt")
            self.assertEqual(result["files"][0]["kind"], "file")
            self.assertEqual(result["files"][1]["kind"], "image")
            self.assertEqual(result["files"][1]["title"], "截图")
            self.assertNotIn("content", result["files"][0])

    def test_rejects_missing_and_empty_lists(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tool = PresentTool()
            with self.assertRaises(ValueError):
                tool.execute({"files": []})
            with self.assertRaises(FileNotFoundError):
                tool.execute({"files": [{"path": str(Path(raw) / "missing.txt")}]})


if __name__ == "__main__":
    unittest.main()
