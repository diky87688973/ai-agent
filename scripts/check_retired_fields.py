#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""残留字段清扫门禁：已删除的节点字段不得在代码与片段里回潮。

本门禁只防已删字段名回潮，不承担「未知字段」防线；
未知字段由 `check_slot_fields` 的闭合白名单负责。

它是「防删掉的词回潮」这一个用途，不是第二道白名单，也不是通用禁词表：
往这里加词的后果是把闭合白名单退化成名单，越加越松。新增字段应从字段表派生，
要拒绝一个词就让它不存在于字段表，而不是把它写进这份扫描。

范围：agent/ plugins/ scripts/ tests/ 下的 .py 与 .json。
排除：docs/（文档要写明该字段已删）与 data/（回收站留有备份），二者都会自伤。

`RETIRED_FIELD` 用拼接构造，是为了避免扫中本文件自己，不是给任何词豁免；
扫描范围仍是全量，不许在这里加词。
"""
from __future__ import annotations

import argparse
import sys
from contextlib import suppress
from pathlib import Path

with suppress(AttributeError, OSError, ValueError):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent

SCAN_DIRS = ("agent", "plugins", "scripts", "tests")
SUFFIXES = (".py", ".json")
SKIP_PARTS = ("__pycache__", "retired")

#: 已删除的节点字段名；拼接以避免本文件被自己扫中。
RETIRED_FIELD = "mast" + "er"


def scan_file(path: Path, root: Path) -> list[str]:
    """返回该文件里所有命中行（相对路径:行号:内容）。"""
    rel = path.relative_to(root).as_posix()
    problems: list[str] = []
    for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if RETIRED_FIELD in line:
            problems.append(f"{rel}:{lineno} {line.strip()[:120]}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="检查已删除的节点字段是否回潮")
    ap.add_argument("--root", default=str(ROOT), help="扫描根目录")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    problems: list[str] = []
    scanned = 0
    for base in SCAN_DIRS:
        folder = root / base
        if not folder.is_dir():
            continue
        for path in folder.rglob("*"):
            if not path.is_file() or path.suffix not in SUFFIXES:
                continue
            rel = path.relative_to(root).as_posix()
            if any(part in rel for part in SKIP_PARTS):
                continue
            scanned += 1
            problems.extend(scan_file(path, root))

    print(f"扫描文件：{scanned}（{', '.join(SCAN_DIRS)} 下的 {'、'.join(SUFFIXES)}）")
    if problems:
        print(f"残留字段（已删除的节点字段 {RETIRED_FIELD} 回潮）：")
        for item in problems:
            print(f"  [FAIL] {item}")
        return 1
    print("✅ 无残留字段")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
