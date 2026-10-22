# -*- coding: utf-8 -*-
"""`docs/applicability.md` 校验：申报结构 + 与准则编号集合的双向比对。

编号集合在 `scripts/standards_rules.py`。集合外的编号即过期申报（失败）；
集合内的编号未申报视为继续适用（缺省即适用）。申报数与 N/A 占比每次打印，
占比持续上升是标准被逐条掏空的信号。

用法：python scripts/check_applicability.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, Set

from standards_rules import RULE_IDS, UPDATED, VERSION

# 在 GBK 控制台直接跑本脚本时，打印 ✅/中文会抛 UnicodeEncodeError ——
# 表现为「检查全过但退出码 1」（`ci.py` 用 PYTHONIOENCODING 掩盖了它）。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    # 旁路，刻意吞掉：不是所有 stdout 都支持 reconfigure（被重定向/被包装时会抛）。
    # 这只是"让打印别因编码失败"的尽力而为 —— 失败就按原编码走，不该阻断检查本身。
    pass

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs" / "applicability.md"

#: 准则编号：`A2` / `E2a` / `0.5`
_ID_RE = re.compile(r"^(?:[A-Z][0-9]*[a-z]?|[0-9]+\.[0-9]+)$")

#: 申报列只接受这一个值；"适用"不需要申报（缺省即适用）
NA = "不适用"
#: 原因的最小长度：一句话，不能只写"不需要"
MIN_REASON = 20


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _rows(text: str) -> Iterable[tuple[int, list[str]]]:
    """产出表格数据行（跳过表头、分隔行、空行与"（无）"占位）。"""
    header_seen = False
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = _cells(stripped)
        if not header_seen:
            header_seen = "准则" in cells
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if not cells or cells[0] in ("（无）", ""):
            continue
        yield lineno, cells


def check(text: str, known_ids: Set[str]) -> list[str]:
    """返回违规列表（空 = 通过）。"""
    out: list[str] = []
    seen: set[str] = set()
    for lineno, cells in _rows(text):
        if len(cells) != 4:
            out.append(f"第 {lineno} 行：需要 4 列（准则 / 申报 / 原因 / 风险由谁承担），实际 {len(cells)} 列")
            continue
        rule, verdict, reason, risk = cells
        if not _ID_RE.match(rule):
            out.append(f"第 {lineno} 行：准则编号格式非法「{rule}」")
            continue
        if rule in seen:
            out.append(f"第 {lineno} 行：重复申报「{rule}」")
        seen.add(rule)
        if verdict != NA:
            out.append(f"第 {lineno} 行：申报只能是「{NA}」，实际「{verdict}」")
        if len(reason) < MIN_REASON:
            out.append(f"第 {lineno} 行：原因少于 {MIN_REASON} 字，无法审计")
        if not risk:
            out.append(f"第 {lineno} 行：缺少「风险由谁承担」")
        if rule not in known_ids:
            out.append(f"第 {lineno} 行：标准手册里没有「{rule}」（过期申报？）")
    if "| 准则 | 申报 | 原因 | 风险由谁承担 |" not in text:
        out.append("缺少申报表头：`| 准则 | 申报 | 原因 | 风险由谁承担 |`")
    return out


def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def run(docs: Path) -> int:
    """校验一份申报表并把判定结果打印出来。"""
    if not docs.is_file():
        print(f"[FAIL] 缺少 {_rel(docs)}")
        return 1
    text = docs.read_text(encoding="utf-8")
    problems = check(text, RULE_IDS)
    declared = sum(1 for _ in _rows(text))
    ratio = declared / len(RULE_IDS) * 100
    print(f"准则 v{VERSION}（{UPDATED}）：申报 {declared} 条 / 标准 {len(RULE_IDS)} 条（N/A {ratio:.1f}%）")
    if problems:
        print("适用性申报不合规：")
        for problem in problems:
            print(f"  [FAIL] {problem}")
        return 1
    print("✅ 适用性申报有效，编号与准则集合双向对齐")
    return 0


def main() -> int:
    return run(DOCS)


if __name__ == "__main__":
    raise SystemExit(main())
