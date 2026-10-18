# -*- coding: utf-8 -*-
"""复杂度采集与渲染（`check_complexity` 与 `gen_complexity_md` 共用）。

采集范围：`agent/` 与 `scripts/` 下的手写 Python，排除 `retired/` 与缓存目录。
行数按物理行算，函数行数按 `end_lineno - lineno + 1` 算。
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Iterable, Mapping, Tuple

SCAN_DIRS = ("agent", "scripts")
SKIP_PARTS = ("__pycache__", "retired")

#: 函数键的分隔符：`相对路径::函数名`
FUNC_SEP = "::"


def _iter_files(root: Path) -> Iterable[Tuple[str, Path]]:
    for base in SCAN_DIRS:
        base_dir = root / base
        if not base_dir.is_dir():
            continue
        for path in sorted(base_dir.rglob("*.py")):
            rel = path.relative_to(root).as_posix()
            if any(part in path.parts for part in SKIP_PARTS):
                continue
            yield rel, path


def _walk_functions(
    node: ast.AST,
    prefix: str,
    out: list[tuple[str, int]],
) -> None:
    """递归收集函数，`prefix` 带上类名与外层函数名，避免同名方法互相覆盖。"""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = f"{prefix}{child.name}"
            if child.end_lineno is not None:
                out.append((name, child.end_lineno - child.lineno + 1))
            _walk_functions(child, name + ".", out)
        elif isinstance(child, ast.ClassDef):
            _walk_functions(child, f"{prefix}{child.name}.", out)
        else:
            _walk_functions(child, prefix, out)


def collect(root: Path) -> Tuple[Dict[str, int], Dict[str, int], Dict[str, int]]:
    """返回 (文件行数, 函数行数, 文件函数个数)。

    函数键是 `相对路径::限定名`；限定名含类名与外层函数名，
    同名方法（两个类各有一个 `derive_messages`）不会互相覆盖。
    """
    files: Dict[str, int] = {}
    funcs: Dict[str, int] = {}
    per_file: Dict[str, int] = {}
    for rel, path in _iter_files(root):
        text = path.read_text(encoding="utf-8")
        files[rel] = len(text.splitlines())
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            # 语法坏文件由 ruff / 单测负责；复杂度采集跳过它，不影响其余文件
            continue
        found: list[tuple[str, int]] = []
        _walk_functions(tree, "", found)
        for name, size in found:
            funcs[f"{rel}{FUNC_SEP}{name}"] = size
        per_file[rel] = len(found)
    return files, funcs, per_file


def over_threshold(
    files: Mapping[str, int],
    funcs: Mapping[str, int],
    max_file_lines: int,
    max_function_lines: int,
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """筛出超阈值的文件与函数（保持输入顺序）。"""
    bad_files = {k: v for k, v in files.items() if v > max_file_lines}
    bad_funcs = {k: v for k, v in funcs.items() if v > max_function_lines}
    return bad_files, bad_funcs


def _sorted_rows(values: Mapping[str, int]) -> list[Tuple[str, int]]:
    return sorted(values.items(), key=lambda kv: (-kv[1], kv[0]))


def render(
    files: Mapping[str, int],
    funcs: Mapping[str, int],
    per_file: Mapping[str, int],
    file_reasons: Mapping[str, str],
    func_reasons: Mapping[str, str],
    max_file_lines: int,
    max_function_lines: int,
) -> str:
    """渲染 `docs/complexity.md`（确定性输出）。"""
    bad_files, bad_funcs = over_threshold(
        files, funcs, max_file_lines, max_function_lines
    )
    lines = [
        "# 复杂度登记",
        "",
        f"> 阈值：单文件 > {max_file_lines} 行、单函数 > {max_function_lines} 行。",
        "> 本文件由 `python scripts/gen_complexity_md.py` 生成；"
        "`scripts/check_complexity.py` 比对实际集合与本表。",
        "",
        "## 超阈值文件",
        "",
        "| 文件 | 行数 | 函数数 | 保留理由 |",
        "|---|---|---|---|",
    ]
    for path, size in _sorted_rows(bad_files):
        reason = file_reasons.get(path, "")
        lines.append(f"| `{path}` | {size} | {per_file.get(path, 0)} | {reason} |")
    if not bad_files:
        lines.append("| （无） | - | - | - |")

    lines += [
        "",
        "## 超阈值函数",
        "",
        "| 文件::函数 | 行数 | 保留理由 |",
        "|---|---|---|",
    ]
    for key, size in _sorted_rows(bad_funcs):
        reason = func_reasons.get(key, "")
        lines.append(f"| `{key}` | {size} | {reason} |")
    if not bad_funcs:
        lines.append("| （无） | - | - |")

    lines += [
        "",
        "## 采集范围",
        "",
        f"- 目录：{'、'.join('`' + d + '/`' for d in SCAN_DIRS)}",
        f"- 排除：{'、'.join('`' + p + '/`' for p in SKIP_PARTS)}",
        f"- 文件 {len(files)} 个、函数 {len(funcs)} 个；"
        f"超阈值文件 {len(bad_files)} 个、函数 {len(bad_funcs)} 个。",
        "",
    ]
    return "\n".join(lines)
