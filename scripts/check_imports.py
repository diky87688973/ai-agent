# -*- coding: utf-8 -*-
"""依赖方向检查：shell → capabilities → mechanisms → core 单向。

规则：某层文件 import 了层级更高的 agent 子包 → 违规。
用法：
    python scripts/check_imports.py          # 方向门禁
    python scripts/check_imports.py --scc    # 打印包内强连通分量（审计用，不判失败）
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

LAYERS = ("core", "mechanisms", "capabilities", "shell", "entry")
RANK = {name: i for i, name in enumerate(LAYERS)}
PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "agent"

#: 装配根与入口：任何层都不得在运行期导入（`if TYPE_CHECKING:` 内的注解除外）。
#: `agent.app` 自己可以导入各层；`agent.entry.*` 在最上层，可以导入两者。
COMPOSITION_ROOTS = frozenset({"app", "entry"})


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
    """扫描包内全部 .py，返回违规列表（空列表 = 通过）。

    两条规则：
    1. 层内只能向下导入（`entry` 最高，`core` 最低）；
    2. `app` / `entry` 之外的文件不得运行期导入装配根（A2 反向依赖）。
    """
    violations: list[str] = []
    for py in sorted(package_root.rglob("*.py")):
        own = _layer_of(py, package_root)
        if own is None:
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in _iter_imports_without_typing_guard(tree):
            for mod in _imported_modules(node, py, package_root):
                parts = mod.split(".")
                if len(parts) < 2 or parts[0] != "agent":
                    continue
                target = parts[1]
                if own not in RANK:
                    continue
                if target in RANK and RANK[target] > RANK[own]:
                    violations.append(
                        f"{py.relative_to(package_root.parent)}: "
                        f"[{own}] 不允许 import [{target}]（{mod}）"
                    )
                elif target in COMPOSITION_ROOTS and own not in COMPOSITION_ROOTS:
                    violations.append(
                        f"{py.relative_to(package_root.parent)}: "
                        f"[{own}] 不得运行期依赖装配根 [{target}]（{mod}）"
                    )
    return violations


def _imported_modules(node: ast.AST, path: Path, package_root: Path) -> list[str]:
    """把一条 import 语句展开成完整的模块名（供方向检查逐条比对）。"""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not isinstance(node, ast.ImportFrom):
        return []
    mod = node.module or ""
    if not node.level:
        return [mod] if mod else []
    rel = path.relative_to(package_root)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        base_parts = parts[:-1]
    else:
        base_parts = parts[:-1]
    if node.level > 1:
        base_parts = base_parts[: len(base_parts) - (node.level - 1)]
    base = ".".join(["agent", *base_parts])
    return [f"{base}.{mod}" if mod else base]


def _is_type_checking(test: ast.expr) -> bool:
    """`if TYPE_CHECKING:` / `if typing.TYPE_CHECKING:` 体内的导入运行期不执行。"""
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def _iter_imports_without_typing_guard(tree: ast.AST):
    """遍历导入，但不下钻 `if TYPE_CHECKING:` 的分支（A2 解析规则）。"""
    stack: list[ast.AST] = [tree]
    while stack:
        node = stack.pop()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.If) and _is_type_checking(child.test):
                continue
            stack.append(child)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            yield node


def _module_table(package_root: Path) -> dict[str, bool]:
    """模块名 → 是否包（`__init__.py`）。"""
    table: dict[str, bool] = {}
    for py in sorted(package_root.rglob("*.py")):
        rel = py.relative_to(package_root)
        parts = list(rel.parts)
        is_pkg = parts[-1] == "__init__.py"
        if is_pkg:
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1][:-3]
        name = ".".join(["agent", *parts]) if parts else "agent"
        table[name] = is_pkg
    return table


def _import_targets(node: ast.AST, module: str, is_pkg: bool,
                    known: dict[str, bool]) -> set[str]:
    """按 A2 解析规则把一条导入展开成目标模块名集合。"""
    targets: set[str] = set()
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name in known:
                targets.add(alias.name)
        return targets
    if not isinstance(node, ast.ImportFrom):
        return targets

    if node.level:
        # 相对导入：从当前模块所在包往上退 level - 1 层
        base = module if is_pkg else module.rsplit(".", 1)[0]
        for _ in range(node.level - 1):
            base = base.rsplit(".", 1)[0] if "." in base else ""
        if node.module:
            base = f"{base}.{node.module}" if base else node.module
    else:
        base = node.module or ""
    if not base:
        return targets
    if base in known:
        targets.add(base)
    for alias in node.names:
        if alias.name == "*":
            continue
        candidate = f"{base}.{alias.name}"
        if candidate in known:
            targets.add(candidate)
    return targets


def _graph(package_root: Path) -> tuple[dict[str, bool], dict[str, set[str]]]:
    known = _module_table(package_root)
    graph: dict[str, set[str]] = {name: set() for name in known}
    for py in sorted(package_root.rglob("*.py")):
        rel = py.relative_to(package_root)
        parts = list(rel.parts)
        is_pkg = parts[-1] == "__init__.py"
        if is_pkg:
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1][:-3]
        module = ".".join(["agent", *parts]) if parts else "agent"
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in _iter_imports_without_typing_guard(tree):
            graph[module].update(_import_targets(node, module, is_pkg, known))
    return known, graph


def cycles(package_root: Path = PACKAGE_ROOT) -> list[list[str]]:
    """返回包内强连通分量（成员数 > 1）；每个分量内按名字排序。"""
    _known, graph = _graph(package_root)
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    out: list[list[str]] = []
    counter = 0

    def strongconnect(node: str) -> None:
        nonlocal counter
        index[node] = low[node] = counter
        counter += 1
        stack.append(node)
        on_stack.add(node)
        for nxt in sorted(graph.get(node, ())):
            if nxt not in index:
                strongconnect(nxt)
                low[node] = min(low[node], low[nxt])
            elif nxt in on_stack:
                low[node] = min(low[node], index[nxt])
        if low[node] == index[node]:
            group: list[str] = []
            while True:
                member = stack.pop()
                on_stack.discard(member)
                group.append(member)
                if member == node:
                    break
            if len(group) > 1:
                out.append(sorted(group))

    for node in sorted(graph):
        if node not in index:
            strongconnect(node)
    return sorted(out)


def main() -> int:
    if "--scc" in sys.argv[1:]:
        groups = cycles()
        if not groups:
            print("包内无循环依赖（强连通分量 0 组）")
            return 0
        print(f"包内循环依赖 {len(groups)} 组：")
        for i, group in enumerate(groups, 1):
            print(f"  [{i}] " + " ⇄ ".join(group))
        return 0
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
