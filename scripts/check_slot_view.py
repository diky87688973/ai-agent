#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""有效视图门禁：装配与绑定路径不得直读声明本体做构造。

判据：`SlotAssembly` / `SessionAssembly` / `SlotBinder` 的类内不出现 `.specs`
属性访问。构造只允许读有效视图（`spec()` / `paths()` / `children()`），
所以「覆盖写了但构造绕过它」在结构上不可能发生。

为什么按 `.specs` 属性名判：字段改名不会绕过它 —— 读声明本体必须经由这个属性，
换名字等于同时改 `SlotConfig` 定义，门禁会立刻在那一处报出来。

允许之处：`SlotConfig` 自己的方法（`spec` / `paths` / `children` / `by_scope`）、
`topo_order` 与有效视图求值本身 —— 它们是求值实现，不是构造路径。
"""
from __future__ import annotations

import argparse
import ast
import sys
from contextlib import suppress
from pathlib import Path

with suppress(AttributeError, OSError, ValueError):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent

SCAN_DIRS = ("agent",)
SKIP_PARTS = ("__pycache__",)

#: 构造路径所在的类：类内任何 `.specs` 访问都算绕过有效视图。
GUARDED_CLASSES = ("SlotAssembly", "SessionAssembly", "SlotBinder", "SlotBinderMixin")


def scan_source(rel: str, src: str) -> list[str]:
    """返回该文件里违规访问的位置；纯函数，供自检与用例直接调用。"""
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [f"{rel}:{exc.lineno} 语法错误：{exc.msg}"]
    problems: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name not in GUARDED_CLASSES:
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Attribute) or inner.attr != "specs":
                continue
            problems.append(
                f"{rel}:{inner.lineno} {node.name} 直读 .specs"
                "（构造只能读有效视图：spec() / paths() / children()）")
    return problems


def _self_check() -> int:
    bad = ("class SlotAssembly:\n"
           "    def build(self):\n"
           "        return self.config.specs['app/x']\n")
    if not scan_source("<self-check-bad>", bad):
        print("❌ 自检失败：装配类直读 .specs 未被抓出")
        return 1
    good = ("class SlotAssembly:\n"
            "    def build(self):\n"
            "        return self.config.spec('app/x')\n")
    if scan_source("<self-check-good>", good):
        print("❌ 自检失败：走 spec() 的写法被误判")
        return 1
    outside = ("class SlotConfig:\n"
               "    def spec(self, path):\n"
               "        return self.specs[path]\n")
    if scan_source("<self-check-outside>", outside):
        print("❌ 自检失败：非受管类的 .specs 访问被误判")
        return 1
    print("✅ 自检通过：装配类直读 .specs 被抓出；spec() 与非受管类不误判")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="检查装配路径是否直读声明本体")
    ap.add_argument("--root", default=str(ROOT), help="扫描根目录")
    ap.add_argument("--self-check", action="store_true",
                    help="跑负向自检：装配类直读 .specs 必须被抓")
    args = ap.parse_args(argv)
    if args.self_check:
        return _self_check()
    root = Path(args.root).resolve()

    problems: list[str] = []
    scanned = 0
    for base in SCAN_DIRS:
        folder = root / base
        if not folder.is_dir():
            continue
        for path in folder.rglob("*.py"):
            rel = path.relative_to(root).as_posix()
            if any(part in rel for part in SKIP_PARTS):
                continue
            scanned += 1
            problems.extend(scan_source(
                rel, path.read_text(encoding="utf-8", errors="replace")))

    print(f"扫描文件：{scanned}  受管类：{'、'.join(GUARDED_CLASSES)}")
    if problems:
        print("绕过有效视图：")
        for item in problems:
            print(f"  [FAIL] {item}")
        return 1
    print("✅ 装配路径只读有效视图")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
