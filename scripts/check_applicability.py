# -*- coding: utf-8 -*-
"""`docs/applicability.md` 校验：不适用的申报必须可查、可双向比对。

用法：
    python scripts/check_applicability.py
    STANDARDS_DOC=/path/to/production-standards.md python scripts/check_applicability.py

未提供标准文档时只校验表结构与字段完整性，并显式打印"ID 覆盖未验证"。
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable, Set

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs" / "applicability.md"
STANDARDS_ENV = "STANDARDS_DOC"

#: 准则编号：`A2` / `E2a` / `0.5`
_ID_RE = re.compile(r"^(?:[A-Z][0-9]*[a-z]?|[0-9]+\.[0-9]+)$")
#: 标准手册里的条目：`**A2｜...**` 或 `### 0.5 ...`
_STD_BOLD_RE = re.compile(r"\*\*([A-Z0-9]+(?:\.[0-9]+)?[a-z]?)｜")
_STD_HEAD_RE = re.compile(r"(?m)^###\s+([0-9]+\.[0-9]+)\s")

#: 申报列只接受这一个值；"适用"不需要申报（缺省即适用）
NA = "不适用"
#: 原因的最小长度：一句话，不能只写"不需要"
MIN_REASON = 20


def load_standard_ids(text: str) -> Set[str]:
    """从标准手册抽取全部准则编号。"""
    return set(_STD_BOLD_RE.findall(text)) | set(_STD_HEAD_RE.findall(text))


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


def check(text: str, known_ids: Set[str] | None = None) -> list[str]:
    """返回违规列表（空 = 通过）。"""
    out: list[str] = []
    seen: set[str] = set()
    count = 0
    for lineno, cells in _rows(text):
        count += 1
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
        if known_ids is not None and rule not in known_ids:
            out.append(f"第 {lineno} 行：标准手册里没有「{rule}」（过期申报？）")
    if "| 准则 | 申报 | 原因 | 风险由谁承担 |" not in text:
        out.append("缺少申报表头：`| 准则 | 申报 | 原因 | 风险由谁承担 |`")
    return out


def main() -> int:
    if not DOCS.is_file():
        print(f"[FAIL] 缺少 {DOCS.relative_to(ROOT)}")
        return 1
    text = DOCS.read_text(encoding="utf-8")
    raw = os.environ.get(STANDARDS_ENV, "").strip()
    known: Set[str] | None = None
    if raw:
        std = Path(raw)
        if not std.is_file():
            print(f"[FAIL] {STANDARDS_ENV}={raw} 指向的文件不存在")
            return 1
        known = load_standard_ids(std.read_text(encoding="utf-8"))
        if not known:
            print(f"[FAIL] 未能从 {raw} 解析出准则编号")
            return 1

    problems = check(text, known)
    total = len(known) if known is not None else 0
    declared = sum(1 for _ in _rows(text))
    ratio = (declared / total * 100) if total else 0.0
    if known is None:
        print(f"申报 {declared} 条；未提供 {STANDARDS_ENV}，ID 覆盖与占比未验证")
    else:
        print(f"申报 {declared} 条 / 标准 {total} 条（N/A {ratio:.1f}%）")

    if problems:
        print("适用性申报不合规：")
        for problem in problems:
            print(f"  [FAIL] {problem}")
        return 1
    print("✅ 适用性申报结构有效")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
