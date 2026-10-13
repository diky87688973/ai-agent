# -*- coding: utf-8 -*-
"""依赖方向检查：shell → capabilities → mechanisms → core 单向。

规则：某层文件 import 了层级更高的 agent 子包 → 违规。
用法：python scripts/check_imports.py（在工程根运行；违规时退出码 1）
"""
from __future__ import annotations

import ast
from pathlib import Path

LAYERS = ("core", "mechanisms", "capabilities", "shell")
RANK = {name: i for i, name in enumerate(LAYERS)}
PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "agent"


def _layer_of(path: Path, root: Path) -> str | None:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return None
    return rel.parts[0] if rel.parts else None


def _iter_imports(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                yield node.module


def check(package_root: Path = PACKAGE_ROOT) -> list[str]:
    """扫描包内全部 .py，返回违规列表（空列表 = 通过）。"""
    violations: list[str] = []
    for py in sorted(package_root.rglob("*.py")):
        own = _layer_of(py, package_root)
        if own is None or own not in RANK:
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for mod in _iter_imports(tree):
            parts = mod.split(".")
            if len(parts) >= 2 and parts[0] == "agent" and parts[1] in RANK:
                target = parts[1]
                if RANK[target] > RANK[own]:
                    violations.append(
                        f"{py.relative_to(package_root.parent)}: "
                        f"[{own}] 不允许 import [{target}]（{mod}）"
                    )
    return violations


def main() -> int:
    violations = check()
    if violations:
        print("依赖方向违规：")
        for v in violations:
            print(" - " + v)
        return 1
    print("依赖方向检查通过（shell → capabilities → mechanisms → core）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
