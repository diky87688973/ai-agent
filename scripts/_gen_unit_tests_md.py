# -*- coding: utf-8 -*-
"""一次性生成 docs/unit-tests.md（单元测试用例清单）。"""
from __future__ import annotations

import inspect
import re
import unittest
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
OUT = ROOT / "docs" / "unit-tests.md"


def _walk(suite: unittest.TestSuite | unittest.TestCase, out: list) -> None:
    if isinstance(suite, unittest.TestSuite):
        for item in suite:
            _walk(item, out)
    else:
        out.append(suite)


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _method_label(name: str) -> str:
    if name.startswith("test_"):
        name = name[5:]
    return name.replace("_", " ")


def _objective(case: unittest.TestCase) -> str:
    meth = getattr(case, case._testMethodName, None)
    doc = inspect.getdoc(meth) if meth else None
    if doc:
        return _one_line(doc.split("\n\n")[0])
    label = _method_label(case._testMethodName)
    cls_doc = inspect.getdoc(case.__class__)
    if cls_doc:
        topic = _one_line(cls_doc.split("\n\n")[0]).rstrip("。.;；")
        if len(topic) > 48:
            topic = topic[:48] + "…"
        return f"覆盖「{topic}」：{label}"
    return f"覆盖：{label}"


def main() -> None:
    loader = unittest.TestLoader()
    suite = loader.discover(str(TESTS), pattern="test_*.py", top_level_dir=str(TESTS))
    cases: list[unittest.TestCase] = []
    _walk(suite, cases)

    groups: OrderedDict[str, list[unittest.TestCase]] = OrderedDict()
    for case in cases:
        file = f"{case.__class__.__module__}.py"
        groups.setdefault(file, []).append(case)

    lines: list[str] = [
        "# 单元测试用例清单",
        "",
        f"共 **{len(cases)}** 个用例"
        "（`python -m unittest discover -s tests -p \"test_*.py\"`）。",
        "",
        "按测试文件分组；「测试目标」优先取方法 docstring，"
        "无则结合类 docstring 与方法名，再否则仅由方法名转写。",
        "",
        "本文件可由 `python scripts/_gen_unit_tests_md.py` 重新生成。",
        "",
        "## 目录",
        "",
    ]
    for i, (file, items) in enumerate(groups.items(), 1):
        anchor = file.replace(".", "")
        lines.append(f"{i}. [{file}](#{anchor})（{len(items)}）")
    lines.append("")

    for file, items in groups.items():
        lines.extend(
            [
                f"## {file}",
                "",
                f"共 {len(items)} 个用例。",
                "",
                "| # | 类 | 方法 | 测试目标 |",
                "|---:|---|---|---|",
            ]
        )
        for i, case in enumerate(items, 1):
            cls = case.__class__.__name__
            meth = case._testMethodName
            obj = _objective(case).replace("|", "\\|")
            lines.append(f"| {i} | `{cls}` | `{meth}` | {obj} |")
        lines.append("")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with_doc = sum(
        1
        for c in cases
        if inspect.getdoc(getattr(c, c._testMethodName, None))
    )
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
    print(f"files={len(groups)} cases={len(cases)} with_method_doc={with_doc}")


if __name__ == "__main__":
    main()
