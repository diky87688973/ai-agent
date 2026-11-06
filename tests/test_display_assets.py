"""公共显示资产必须进入既有 JS 门禁。"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_comment_style, check_ui_js


class DisplayAssetGateTest(unittest.TestCase):
    def test_vendor_bundle_matches_provenance_and_own_comments_remain_checked(self):
        vendor = Path(__file__).resolve().parents[1] / "plugins" / "visualization" / "ui" / "vendor"
        for manifest in (vendor / "provenance.json", vendor / "echarts" / "provenance.json"):
            provenance = json.loads(manifest.read_text(encoding="utf-8"))
            for name, expected in provenance["files"].items():
                content = (manifest.parent / name).read_bytes()
                self.assertEqual(len(content), expected["bytes"])
                self.assertEqual(hashlib.sha256(content).hexdigest(), expected["sha256"])
        self.assertTrue(check_comment_style.scan_text("// TODO: remove this", ".js", check_comment_style.PRODUCTION_ONLY))

    def test_missing_or_empty_host_asset_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "missing.js"
            with (
                patch.object(check_ui_js, "ROOT", root),
                patch.object(check_ui_js, "UI_SHARED_JS_FILES", (path,)),
            ):
                self.assertTrue(check_ui_js._asset_problems())
                path.touch()
                self.assertTrue(check_ui_js._asset_problems())

    @unittest.skipUnless(shutil.which("node"), "需 Node 进行 JavaScript 语法检查")
    def test_invalid_host_javascript_fails_the_syntax_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "bad.js"
            path.write_text("function broken( {", encoding="utf-8")
            with (
                patch.object(check_ui_js, "ROOT", root),
                patch.object(check_ui_js, "UI_SHARED_JS_FILES", (path,)),
            ):
                self.assertTrue(any("bad.js" in item for item in check_ui_js._syntax_problems()))
