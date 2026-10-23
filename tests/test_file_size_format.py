# -*- coding: utf-8 -*-
"""文件面板的大小显示：一律 KB 起，不出现"字节"。

文件面板是给人扫一眼量级的，同一列里混两种单位会让人来回换算。
所以 <1 KB 也换算成小数 KB（`288 字节` → `0.3 KB`）。

判定靠真的把函数跑起来（`node`），不是读源码猜 ——
边界（1023/1024、1048575/1048576）与舍入顺序都在这里钉死。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.shell.web.ui_bundle import read_ui_js  # noqa: E402


def _function_source(name: str) -> str:
    src = read_ui_js()
    i = src.index(f"function {name}(")
    ends = [x for x in (src.find("\nfunction ", i + 10), src.find("\n;", i + 10)) if x > 0]
    j = min(ends) if ends else -1
    return src[i:j if j > 0 else len(src)]


def _run(cases: list) -> list:
    """把函数抽出来交给 node 跑，返回每个输入的结果。"""
    node = shutil.which("node")
    if node is None:
        raise unittest.SkipTest("node 不在 PATH 上，跳过（无法真跑 JS）")
    script = _function_source("formatFileSize") + "\n" + (
        "const cases = " + json.dumps(cases) + ";\n"
        "const out = cases.map(c => { try { return formatFileSize(c); }"
        " catch (e) { return 'ERR:' + e.message; } });\n"
        "process.stdout.write(JSON.stringify(out));\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "probe.js"
        p.write_text(script, encoding="utf-8")
        r = subprocess.run([node, str(p)], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(f"node 执行失败：{r.stderr[:300]}")
    return json.loads(r.stdout)


class FileSizeFormatTest(unittest.TestCase):
    def test_never_uses_byte_unit(self) -> None:
        """任何大小都不出现"字节"。"""
        cases = [0, 1, 100, 288, 512, 1023, 1024, 1536, 1048575, 1048576, 1073741824]
        for text in _run(cases):
            with self.subTest(text=text):
                self.assertNotIn("字节", text)
                self.assertRegex(text, r"^\d+(\.\d+)? (KB|MB|GB|TB)$")

    def test_sub_kilobyte_becomes_decimal_kb(self) -> None:
        got = _run([288, 512, 100, 1023])
        self.assertEqual(got[0], "0.3 KB")
        self.assertEqual(got[1], "0.5 KB")
        self.assertEqual(got[2], "0.1 KB")
        self.assertEqual(got[3], "1 KB")

    def test_rounds_before_choosing_the_unit(self) -> None:
        """先舍入再定单位 —— 否则 1048575 会显示成 `1024 KB`。"""
        got = _run([1048575, 1048576, 1536, 1073741824])
        self.assertEqual(got[0], "1 MB")
        self.assertEqual(got[1], "1 MB")
        self.assertEqual(got[2], "1.5 KB")
        self.assertEqual(got[3], "1 GB")

    def test_bad_values_are_empty(self) -> None:
        got = _run([None, -1])
        self.assertEqual(got, ["", ""])


if __name__ == "__main__":
    unittest.main()
