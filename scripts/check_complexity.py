# -*- coding: utf-8 -*-
"""复杂度门禁：实际超阈值集合 ↔ 阈值常量 ↔ 生成文档。

三件事一起做，缺一条阈值就只是纸面数字：
1. 实际超阈值但没登记 → 新增债务；
2. 登记了但实际已不超 → 过期登记，必须删；
3. `docs/complexity.md` 与当前采集结果不一致 → 生成物漂移。

用法：python scripts/check_complexity.py [--list]
"""
from __future__ import annotations

import sys
from pathlib import Path

# 在 GBK 控制台直接跑本脚本时，打印 ✅/中文会抛 UnicodeEncodeError ——
# 表现为「检查全过但退出码 1」（`ci.py` 用 PYTHONIOENCODING 掩盖了它）。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception as exc:
    # 旁路，刻意吞掉：不是所有 stdout 都支持 reconfigure（被重定向/被包装时会抛）。
    # 这只是"让打印别因编码失败"的尽力而为 —— 失败就按原编码走，不该阻断检查本身。
    print(f"[scripts.check_complexity.module] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from complexity_scan import (  # noqa: E402
    FUNC_SEP,
    collect,
    over_file_functions,
    over_threshold,
    render,
)
from quality_budgets import (  # noqa: E402
    MAX_FILE_FUNCTIONS,
    MAX_FILE_LINES,
    MAX_FUNCTION_LINES,
)

DOCS = ROOT / "docs" / "complexity.md"


def _render(root: Path) -> str:
    files, funcs, per_file = collect(root)
    return render(files, funcs, per_file, MAX_FILE_LINES,
                  MAX_FUNCTION_LINES, MAX_FILE_FUNCTIONS)


def _normalized(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n")).strip()


def check(root: Path = ROOT, docs: Path = DOCS,
          max_file_lines: int = MAX_FILE_LINES,
          max_function_lines: int = MAX_FUNCTION_LINES,
          max_file_functions: int = MAX_FILE_FUNCTIONS) -> list[str]:
    """返回违规列表（空 = 通过）；超过阈值没有豁免。"""
    files, funcs, per_file = collect(root)
    bad_files, bad_funcs = over_threshold(
        files, funcs, max_file_lines, max_function_lines)
    bad_counts = over_file_functions(per_file, max_file_functions)
    out: list[str] = []
    for path, size in sorted(bad_files.items()):
        out.append(f"超阈值文件：{path}（{size} 行）")
    for key, size in sorted(bad_funcs.items()):
        out.append(f"超阈值函数：{key}（{size} 行）")
    for path, count in sorted(bad_counts.items()):
        out.append(f"函数数超阈值文件：{path}（{count} 个函数）")
    expected = render(files, funcs, per_file, max_file_lines,
                      max_function_lines, max_file_functions)
    if not docs.is_file():
        out.append(f"缺少生成文档：{docs}")
    elif _normalized(docs.read_text(encoding="utf-8")) != _normalized(expected):
        out.append(f"生成文档已漂移：{docs}（运行 python scripts/gen_complexity_md.py）")
    return out


def _print_list() -> None:
    files, funcs, per_file = collect(ROOT)
    bad_files, bad_funcs = over_threshold(
        files, funcs, MAX_FILE_LINES, MAX_FUNCTION_LINES)
    print(f"阈值：文件 > {MAX_FILE_LINES} 行、函数 > {MAX_FUNCTION_LINES} 行、"
          f"文件函数数 > {MAX_FILE_FUNCTIONS}")
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
        print("复杂度超阈值：")
        for problem in problems:
            print(f"  [FAIL] {problem}")
        print()
        print("修法：拆分到阈值以内；没有豁免表。")
        return 1
    print("✅ 复杂度检查通过：无超阈值文件/函数")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
