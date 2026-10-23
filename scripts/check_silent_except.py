#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""静默异常门禁：禁止以任何形式吞掉异常。

规则：

- `except` 体只有 `pass`/`continue`：失败；
- 裸 `except`：失败；
- `except Exception` / `BaseException` / `suppress(Exception)` 没有上报：失败；
- 宽捕获 + 无上报的 return/常量赋值：失败；
- 窄捕获 + 明确返回：允许；
- `report_error(...)`、`write_stderr(...)`、`print(..., file=sys.stderr)` 视为上报；
- `contextlib.suppress(SpecificError)`：允许。

注释、正则表、预算都不是豁免依据。
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
SCAN_DIRS = ("agent", "tests", "scripts", "plugins")
SKIP_PARTS = ("__pycache__", "retired")


def _broad(node: ast.ExceptHandler) -> bool:
    if node.type is None:
        return True
    names: list[str] = []
    if isinstance(node.type, ast.Name):
        names = [node.type.id]
    elif isinstance(node.type, ast.Tuple):
        names = [x.id for x in node.type.elts if isinstance(x, ast.Name)]
    return any(n in ("Exception", "BaseException") for n in names)


def _has_pass(node: ast.ExceptHandler) -> bool:
    return any(isinstance(stmt, ast.Pass) for stmt in node.body)


def _only_pass_continue(node: ast.ExceptHandler) -> bool:
    return (
        len(node.body) == 1
        and isinstance(node.body[0], (ast.Pass, ast.Continue))
    )


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _is_stderr(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg == "file" and isinstance(kw.value, ast.Attribute):
            return kw.value.attr == "stderr"
    return False


def _transforms(node: ast.ExceptHandler) -> bool:
    """宽捕获是否重新抛出，或构造受控的 ToolResult。"""
    for child in ast.walk(ast.Module(body=node.body, type_ignores=[])):
        if isinstance(child, ast.Raise):
            return True
        if isinstance(child, ast.Assign) and isinstance(child.value, ast.Call):
            if _call_name(child.value) == "ToolResult":
                return True
    return False


def _reports(node: ast.ExceptHandler) -> bool:
    for child in ast.walk(ast.Module(body=node.body, type_ignores=[])):
        if not isinstance(child, ast.Call):
            continue
        name = _call_name(child)
        if name == "report_error" and len(child.args) >= 2:
            return True
        if name == "write_stderr" and child.args:
            return True
        if name == "print" and _is_stderr(child):
            return True
    return False


def _fallback_constant(node: ast.AST | None) -> bool:
    if node is None:
        return True
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return not node.elts
    if isinstance(node, ast.Dict):
        return not node.keys
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return node.func.id == "set" and not node.args and not node.keywords
    return False


def _fallback_mask(node: ast.ExceptHandler) -> bool:
    if len(node.body) != 1:
        return False
    only = node.body[0]
    if isinstance(only, ast.Return):
        return _fallback_constant(only.value)
    if isinstance(only, ast.Assign):
        return _fallback_constant(only.value)
    return False


def _broad_suppress(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_name(node) != "suppress":
            continue
        for arg in node.args:
            if isinstance(arg, ast.Name) and arg.id in ("Exception", "BaseException"):
                lines.append(node.lineno)
            elif isinstance(arg, ast.Tuple):
                if any(isinstance(x, ast.Name) and x.id in ("Exception", "BaseException")
                       for x in arg.elts):
                    lines.append(node.lineno)
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="检查静默吞异常")
    args = ap.parse_args(argv)

    problems: list[str] = []
    checked = 0
    scanned = 0
    for base in SCAN_DIRS:
        for f in (ROOT / base).rglob("*.py"):
            rel = f.relative_to(ROOT).as_posix()
            if any(p in rel for p in SKIP_PARTS):
                continue
            scanned += 1
            src = f.read_text(encoding="utf-8")
            try:
                tree = ast.parse(src)
            except SyntaxError as exc:
                problems.append(f"{rel}:{exc.lineno} 语法错误：{exc.msg}")
                continue
            for line in _broad_suppress(tree):
                problems.append(f"{rel}:{line} 禁止 suppress(Exception/BaseException)")
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                checked += 1
                where = f"{rel}:{node.lineno}"
                if node.type is None:
                    problems.append(f"{where} 禁止裸 except")
                    continue
                if _has_pass(node) or _only_pass_continue(node):
                    problems.append(f"{where} except 体含 pass/continue")
                    continue
                if _broad(node) and not (_reports(node) or _transforms(node)):
                    problems.append(f"{where} 宽捕获未上报异常或转成明确结果")
                    continue
                if _broad(node) and _fallback_mask(node) and not _reports(node):
                    problems.append(f"{where} 宽捕获后返回默认值且未上报")
    print(f"扫描文件：{scanned}  检查 except：{checked}")
    if problems:
        print("静默异常：")
        for p in problems:
            print(f"  [FAIL] {p}")
        return 1
    print("✅ 无静默异常")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
