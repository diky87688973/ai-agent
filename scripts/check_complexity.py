# -*- coding: utf-8 -*-
"""复杂度门禁：实际超阈值集合 ↔ `scripts/quality_budgets.py` 登记表 ↔ 生成文档。

三件事一起做，缺一条阈值就只是纸面数字：
1. 实际超阈值但没登记 → 新增债务；
2. 登记了但实际已不超 → 过期登记，必须删；
3. `docs/complexity.md` 与当前采集结果不一致 → 生成物漂移。

用法：python scripts/check_complexity.py [--list]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from complexity_scan import FUNC_SEP, collect, over_threshold, render  # noqa: E402
from quality_budgets import (  # noqa: E402
    FILE_COMPLEXITY,
    FUNCTION_COMPLEXITY,
    MAX_FILE_LINES,
    MAX_FUNCTION_LINES,
)

DOCS = ROOT / "docs" / "complexity.md"


def _render(root: Path) -> str:
    files, funcs, per_file = collect(root)
    return render(
        files,
        funcs,
        per_file,
        FILE_COMPLEXITY,
        FUNCTION_COMPLEXITY,
        MAX_FILE_LINES,
        MAX_FUNCTION_LINES,
    )


def _normalized(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n")).strip()


def check(
    root: Path = ROOT,
    docs: Path = DOCS,
    file_reasons: dict | None = None,
    func_reasons: dict | None = None,
    max_file_lines: int = MAX_FILE_LINES,
    max_function_lines: int = MAX_FUNCTION_LINES,
) -> list[str]:
    """返回违规列表（空 = 通过）。登记表与文档都可注入，便于负向用例。"""
    file_reasons = FILE_COMPLEXITY if file_reasons is None else file_reasons
    func_reasons = FUNCTION_COMPLEXITY if func_reasons is None else func_reasons
    files, funcs, per_file = collect(root)
    bad_files, bad_funcs = over_threshold(files, funcs, max_file_lines, max_function_lines)

    out: list[str] = []
    for path in sorted(bad_files):
        if path not in file_reasons:
            out.append(f"未登记的超阈值文件：{path}（{bad_files[path]} 行）")
        elif not str(file_reasons[path]).strip():
            out.append(f"登记缺少理由：{path}")
    for path in sorted(func_reasons):
        if path not in bad_funcs:
            out.append(f"过期登记（文件/函数已不超阈值）：{path}")
    for path in sorted(file_reasons):
        if path not in bad_files:
            out.append(f"过期登记（文件已不超阈值）：{path}")
    for key in sorted(bad_funcs):
        if key not in func_reasons:
            out.append(f"未登记的超阈值函数：{key}（{bad_funcs[key]} 行）")
        elif not str(func_reasons[key]).strip():
            out.append(f"登记缺少理由：{key}")

    expected = render(
        files, funcs, per_file, file_reasons, func_reasons,
        max_file_lines, max_function_lines,
    )
    if not docs.is_file():
        out.append(f"缺少生成文档：{docs}")
    elif _normalized(docs.read_text(encoding="utf-8")) != _normalized(expected):
        out.append(f"生成文档已漂移：{docs}（运行 python scripts/gen_complexity_md.py）")
    return out


def _print_list() -> None:
    files, funcs, per_file = collect(ROOT)
    bad_files, bad_funcs = over_threshold(files, funcs, MAX_FILE_LINES, MAX_FUNCTION_LINES)
    print(f"阈值：文件 > {MAX_FILE_LINES} 行、函数 > {MAX_FUNCTION_LINES} 行")
    print(f"超阈值文件 {len(bad_files)} 个：")
    for path in sorted(bad_files, key=lambda p: (-bad_files[p], p)):
        print(f"  {bad_files[path]:5d}  {path}（{per_file.get(path, 0)} 个函数）")
    print(f"超阈值函数 {len(bad_funcs)} 个：")
    for key in sorted(bad_funcs, key=lambda k: (-bad_funcs[k], k)):
        name = key.split(FUNC_SEP, 1)[-1]
        print(f"  {bad_funcs[key]:5d}  {name}  [{key.split(FUNC_SEP, 1)[0]}]")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--list" in args:
        _print_list()
        return 0
    problems = check()
    if problems:
        print("复杂度登记不一致：")
        for problem in problems:
            print(f"  [FAIL] {problem}")
        print()
        print("修法：在 scripts/quality_budgets.py 增删登记并重生成 docs/complexity.md。")
        return 1
    files, funcs, _ = collect(ROOT)
    print(
        f"✅ 复杂度登记一致（文件 {len(files)}、函数 {len(funcs)}、"
        f"超阈值 {len(FILE_COMPLEXITY)} 文件 / {len(FUNCTION_COMPLEXITY)} 函数）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
