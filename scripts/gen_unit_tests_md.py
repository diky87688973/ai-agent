# -*- coding: utf-8 -*-
"""生成 / 校验 `docs/unit-tests.md`（单元测试用例清单）。

用法：
    python scripts/gen_unit_tests_md.py           # 重新生成
    python scripts/gen_unit_tests_md.py --check   # 只校验文档是否与用例一致（漂移即退出 1）

文档是代码的投影：用例增删改后忘了重新生成，`--check` 会失败；
这样"文档说 1165 个用例、实际 1164 个"这类漂移不可能悄悄留在库里。
"""
from __future__ import annotations

import inspect
import re
import sys
import unittest
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 直接用 `python scripts/gen_unit_tests_md.py` 运行时，sys.path[0] 是 scripts/；
# 测试模块要 `import agent`，必须把仓库根放进来（与 `python -m unittest` 一致）。
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
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


def collect() -> tuple[list[unittest.TestCase], OrderedDict[str, list[unittest.TestCase]]]:
    """发现全部用例并按测试文件分组（顺序稳定，便于逐字节比对）。"""
    loader = unittest.TestLoader()
    suite = loader.discover(str(TESTS), pattern="test_*.py", top_level_dir=str(TESTS))
    cases: list[unittest.TestCase] = []
    _walk(suite, cases)
    groups: OrderedDict[str, list[unittest.TestCase]] = OrderedDict()
    for case in cases:
        file = f"{case.__class__.__module__}.py"
        groups.setdefault(file, []).append(case)
    return cases, groups


def render() -> str:
    """渲染整份文档（不落盘）。"""
    cases, groups = collect()
    lines: list[str] = [
        "# 单元测试用例清单",
        "",
        f"共 **{len(cases)}** 个用例"
        "（`python -m unittest discover -s tests -p \"test_*.py\"`）。",
        "",
        "按测试文件分组；「测试目标」优先取方法 docstring，"
        "无则结合类 docstring 与方法名，再否则仅由方法名转写。",
        "",
        "本文件是生成的可读测试目录，不是事实源；事实源是 `tests/`。",
        "由 `python scripts/gen_unit_tests_md.py` 生成；"
        "`--check` 在 CI 里校验是否漂移，直接改动会被下一次生成覆盖。",
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

    return "\n".join(lines) + "\n"


def _display(path: Path) -> str:
    """报错时的路径展示：仓库内显示相对路径，仓库外（测试临时目录）显示绝对路径。"""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    content = render()
    if "--check" in args:
        if not OUT.is_file():
            print(f"[FAIL] 缺少 {_display(OUT)}；先跑 python scripts/gen_unit_tests_md.py")
            return 1
        current = OUT.read_text(encoding="utf-8")
        if current != content:
            print(
                f"[FAIL] {_display(OUT)} 与用例不一致"
                "（跑 python scripts/gen_unit_tests_md.py 重新生成后提交）"
            )
            return 1
        print(f"{_display(OUT)} 与用例一致")
        return 0
    OUT.write_text(content, encoding="utf-8")
    cases, groups = collect()
    with_doc = sum(1 for c in cases if inspect.getdoc(getattr(c, c._testMethodName, None)))
    print(f"wrote {_display(OUT)} ({OUT.stat().st_size} bytes)")
    print(f"files={len(groups)} cases={len(cases)} with_method_doc={with_doc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
