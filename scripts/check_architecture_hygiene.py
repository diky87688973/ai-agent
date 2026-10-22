# -*- coding: utf-8 -*-
"""架构约束检查：跨层私有导入、内核插件名、壳层 skill_manage 硬编码。

用法：python scripts/check_architecture_hygiene.py（工程根运行；违规时退出码 1）
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from quality_budgets import SAME_LAYER_PRIVATE_BUDGET

LAYERS = ("core", "mechanisms", "capabilities", "shell", "entry")
ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = ROOT / "agent"
PLUGINS_DIR = ROOT / "plugins"
CLASSIC_JS = PACKAGE_ROOT / "shell" / "web_assets" / "classic" / "js"
PROMPTS_PY = PACKAGE_ROOT / "shell" / "prompts.py"

# 标识符边界：避免 `atts` 误伤三字母短名。
_WORD = r"(?<![A-Za-z0-9_]){name}(?![A-Za-z0-9_])"


def _layer_of(path: Path, root: Path) -> str | None:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return None
    return rel.parts[0] if rel.parts else None


def _plugin_dir_names(plugins_dir: Path = PLUGINS_DIR) -> list[str]:
    if not plugins_dir.is_dir():
        return []
    return sorted(
        p.name for p in plugins_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name != "__pycache__"
    )


def _word_hits(text: str, name: str) -> bool:
    return re.search(_WORD.format(name=re.escape(name)), text) is not None


def check_cross_layer_private_imports(
    package_root: Path = PACKAGE_ROOT,
) -> list[str]:
    """跨层 `from agent.X import _priv` / `import agent.X._y` 违规列表。"""
    violations: list[str] = []
    for py in sorted(package_root.rglob("*.py")):
        own = _layer_of(py, package_root)
        if own is None or own not in LAYERS:
            continue
        rel = py.relative_to(package_root.parent)
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError as exc:
            violations.append(f"{rel}: 无法解析（{exc}）")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                parts = mod.split(".")
                if len(parts) < 2 or parts[0] != "agent" or parts[1] not in LAYERS:
                    continue
                target = parts[1]
                if target == own:
                    continue
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    if alias.name.startswith("_"):
                        violations.append(
                            f"{rel}:{node.lineno}: 跨层私有导入 "
                            f"[{own}] → [{target}]：from {mod} import {alias.name}"
                        )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    parts = alias.name.split(".")
                    if len(parts) < 2 or parts[0] != "agent" or parts[1] not in LAYERS:
                        continue
                    target = parts[1]
                    if target == own:
                        continue
                    priv = [p for p in parts[2:] if p.startswith("_")]
                    if priv:
                        violations.append(
                            f"{rel}:{node.lineno}: 跨层私有导入 "
                            f"[{own}] → [{target}]：import {alias.name}"
                        )
    return violations


def check_same_layer_private_imports(package_root: Path = PACKAGE_ROOT) -> list[str]:
    """同层跨模块私有名导入：只报告，超过预算才失败。"""
    hits: list[str] = []
    for py in sorted(package_root.rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError:
            continue
        source_parts = py.relative_to(package_root).parts
        if len(source_parts) < 2:
            continue
        source_layer = source_parts[0]
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            mod = node.module or ""
            parts = mod.split(".")
            if len(parts) < 2 or parts[0] != "agent":
                continue
            if parts[1] != source_layer or parts[1] == "app":
                continue
            for alias in node.names:
                if alias.name.startswith("_") and not alias.name.startswith("__"):
                    hits.append(f"{_rel_to_root(py)}:{node.lineno}: {mod}.{alias.name}")
    return hits


def check_test_method_names(tests_dir: Path | None = None) -> list[str]:
    """测试方法名必须是 test_ 前缀，避免批量改名把前缀吃掉。"""
    root = tests_dir if tests_dir is not None else ROOT / "tests"
    if not root.is_dir():
        return []
    out: list[str] = []
    for py in sorted(root.glob("test_*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError as exc:
            out.append(f"{_rel_to_root(py)}: 无法解析（{exc}）")
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("test") and not node.name.startswith("test_"):
                    out.append(f"{_rel_to_root(py)}:{node.lineno}: 测试方法名不规范：{node.name}")
    return out


def check_kernel_plugin_names(
    package_root: Path = PACKAGE_ROOT,
    plugins_dir: Path = PLUGINS_DIR,
) -> list[str]:
    """core / mechanisms 不得出现 skill_manage 或 plugins/ 目录名（词边界）。"""
    banned = ["skill_manage", *_plugin_dir_names(plugins_dir)]
    violations: list[str] = []
    for layer in ("core", "mechanisms"):
        base = package_root / layer
        if not base.is_dir():
            continue
        for py in sorted(base.rglob("*.py")):
            rel = py.relative_to(package_root.parent)
            text = py.read_text(encoding="utf-8")
            for name in banned:
                if _word_hits(text, name):
                    violations.append(
                        f"{rel}: 内核禁插件名「{name}」"
                    )
    return violations


def check_shell_js_skill_manage(js_root: Path = CLASSIC_JS) -> list[str]:
    """经典壳 JS 不得硬编码 skill_manage（插件资产允许）。"""
    violations: list[str] = []
    if not js_root.is_dir():
        return violations
    for js in sorted(js_root.rglob("*.js")):
        text = js.read_text(encoding="utf-8")
        if "skill_manage" in text:
            rel = js.relative_to(ROOT)
            violations.append(f"{rel}: 壳层 JS 禁 skill_manage")
    return violations


def check_shell_prompts_skill_manage(prompts: Path = PROMPTS_PY) -> list[str]:
    """prompts.py 不得含 skill_manage。"""
    if not prompts.is_file():
        return []
    text = prompts.read_text(encoding="utf-8")
    if "skill_manage" in text:
        return [f"{prompts.relative_to(ROOT)}: 壳层 prompts 禁 skill_manage"]
    return []


# 门控单通路 / 预览只认 needs_preview：AST 禁旁路符号（非子串）
_BANNED_GATE_NAMES = frozenset({
    "_fallback_gate",
    "gate_resolver",
    "_TOOL_PATH_KEYS",
    "register_write_path_keys",
    "unregister_write_path_keys",
})
_BANNED_GATE_ASSIGN_OR_KW = frozenset({
    "preview_tools",
    "content_tools",
})

# prompts 纪律段不得再手写整串内置写工具名单
_HANDWRITTEN_WRITE_TOOLS = (
    "write_file / replace_in_file / apply_patch / read_write / "
    "delete_file / file_ops / file_undo / archive"
)


def _rel_to_root(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _iter_assign_target_ids(target: ast.AST):
    """展开赋值目标上的 Name.id / Attribute.attr（含 Tuple/List/Starred）。"""
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, ast.Attribute):
        yield target.attr
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            yield from _iter_assign_target_ids(elt)
    elif isinstance(target, ast.Starred):
        yield from _iter_assign_target_ids(target.value)


def _gate_bypass_hits(tree: ast.AST) -> list[tuple[int, str]]:
    """扫描 AST，返回 (lineno, symbol) 旁路命中。"""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _BANNED_GATE_NAMES:
            hits.append((node.lineno, node.id))
        elif isinstance(node, ast.Attribute) and node.attr in _BANNED_GATE_NAMES:
            hits.append((node.lineno, node.attr))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                for sym in (alias.name, alias.asname):
                    if sym and sym in _BANNED_GATE_NAMES:
                        hits.append((node.lineno, sym))
        elif isinstance(node, ast.keyword) and node.arg in _BANNED_GATE_ASSIGN_OR_KW:
            hits.append((node.lineno, node.arg))
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                for name in _iter_assign_target_ids(t):
                    if name in _BANNED_GATE_ASSIGN_OR_KW:
                        hits.append((node.lineno, name))
        elif isinstance(node, ast.AnnAssign) and node.target is not None:
            for name in _iter_assign_target_ids(node.target):
                if name in _BANNED_GATE_ASSIGN_OR_KW:
                    hits.append((node.lineno, name))
        elif isinstance(node, ast.AugAssign):
            for name in _iter_assign_target_ids(node.target):
                if name in _BANNED_GATE_ASSIGN_OR_KW:
                    hits.append((node.lineno, name))
    return hits


def check_gate_single_path(package_root: Path = PACKAGE_ROOT) -> list[str]:
    """禁门控旁路符号（AST：Name/Attribute/导入别名/赋值与关键字参数）。"""
    violations: list[str] = []
    for py in sorted(package_root.rglob("*.py")):
        if "__pycache__" in py.parts:
            continue
        rel = _rel_to_root(py)
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError as exc:
            violations.append(f"{rel}: 无法解析（{exc}）")
            continue
        seen: set[tuple[int, str]] = set()
        for lineno, sym in _gate_bypass_hits(tree):
            key = (lineno, sym)
            if key in seen:
                continue
            seen.add(key)
            violations.append(f"{rel}:{lineno}: 禁旁路符号「{sym}」")
    return violations


def check_prompts_preview_from_registry(prompts: Path = PROMPTS_PY) -> list[str]:
    """prompts.py 须有 preview_write_tools_line，且无手写写工具长名单。"""
    if not prompts.is_file():
        return [f"{PROMPTS_PY.relative_to(ROOT)}: 缺失"]
    text = prompts.read_text(encoding="utf-8")
    rel = prompts.relative_to(ROOT)
    out: list[str] = []
    if "def preview_write_tools_line" not in text:
        out.append(f"{rel}: 缺少 preview_write_tools_line")
    if _HANDWRITTEN_WRITE_TOOLS in text:
        out.append(f"{rel}: 禁手写预览写类工具长名单")
    return out


def _assigns_empty_system_text(node: ast.AST) -> bool:
    if isinstance(node, ast.Assign):
        targets = node.targets
        value = node.value
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
        value = node.value
    else:
        return False
    if not isinstance(value, ast.Constant) or value.value != "":
        return False
    return any(isinstance(t, ast.Name) and t.id == "system_text" for t in targets)


def check_no_silent_system_prompt(package_root: Path = PACKAGE_ROOT) -> list[str]:
    """禁把系统提示词失败吞成空串。"""
    violations: list[str] = []
    for py in sorted((package_root / "shell").rglob("*.py")):
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError as exc:
            violations.append(f"{_rel_to_root(py)}: 无法解析（{exc}）")
            continue
        has_resolve = any(
            isinstance(node, ast.Name) and node.id == "resolve_system_prompt"
            for node in ast.walk(tree)
        ) or any(
            isinstance(node, ast.ImportFrom)
            and any(alias.name == "resolve_system_prompt" for alias in node.names)
            for node in ast.walk(tree)
        )
        if not has_resolve:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if any(_assigns_empty_system_text(stmt) for stmt in node.body):
                violations.append(f"{_rel_to_root(py)}:{node.lineno}: 禁静默 system_text 空串")
    return violations


def _quality_gate_import_hits(tree: ast.AST) -> list[tuple[int, str]]:
    """AST 检测 quality_gate / mechanisms.quality_gate 导入。"""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if "quality_gate" in parts:
                    hits.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            parts = mod.split(".") if mod else []
            if "quality_gate" in parts:
                hits.append((node.lineno, mod))
                continue
            for alias in node.names:
                if alias.name == "quality_gate" or alias.asname == "quality_gate":
                    label = f"{mod} import {alias.name}" if mod else alias.name
                    hits.append((node.lineno, label))
    return hits


_PROVIDER_NEUTRAL = frozenset({"base", "sse", "debug", "tool_schema"})


def check_provider_module_boundary(package_root: Path = PACKAGE_ROOT) -> list[str]:
    """Provider 具体实现只能依赖中性模块，不能互导。"""
    root = package_root / "mechanisms" / "providers"
    out: list[str] = []
    if not root.is_dir():
        return out
    for py in sorted(root.glob("*.py")):
        if py.name == "__init__.py":
            continue
        own = py.stem
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError as exc:
            out.append(f"{_rel_to_root(py)}: 无法解析（{exc}）")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            mod = node.module or ""
            if not mod.startswith("agent.mechanisms.providers."):
                continue
            target = mod.rsplit(".", 1)[-1]
            if target == own or target in _PROVIDER_NEUTRAL:
                continue
            out.append(f"{_rel_to_root(py)}:{node.lineno}: Provider 互导 {own} -> {target}")
    return out


def check_compactor_contract_boundary(package_root: Path = PACKAGE_ROOT) -> list[str]:
    """压缩器不得导入上下文管线的内部实现。"""
    path = package_root / "mechanisms" / "compaction" / "compactor.py"
    if not path.is_file():
        return []
    forbidden = (
        "agent.mechanisms.context.pipeline",
        "agent.mechanisms.context.layout",
        "agent.mechanisms.context.rounds",
        "agent.mechanisms.context.sources",
        "agent.mechanisms.context.tokens",
    )
    out: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [f"{_rel_to_root(path)}: 无法解析（{exc}）"]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod in forbidden:
                out.append(f"{_rel_to_root(path)}:{node.lineno}: 压缩器直依赖 {mod}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in forbidden:
                    out.append(f"{_rel_to_root(path)}:{node.lineno}: 压缩器直依赖 {alias.name}")
    return out


def check_no_quality_gate_shim(
    package_root: Path = PACKAGE_ROOT,
    plugins_dir: Path = PLUGINS_DIR,
    tests_dir: Path | None = None,
) -> list[str]:
    """禁 `quality_gate` 兼容层：实现只在 mechanisms.quality。"""
    violations: list[str] = []
    roots = (package_root, plugins_dir, tests_dir if tests_dir is not None else ROOT / "tests")
    for root in roots:
        if not root.is_dir():
            continue
        for py in sorted(root.rglob("*.py")):
            if "__pycache__" in py.parts:
                continue
            rel = _rel_to_root(py)
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
            except SyntaxError as exc:
                violations.append(f"{rel}: 无法解析（{exc}）")
                continue
            for lineno, label in _quality_gate_import_hits(tree):
                violations.append(
                    f"{rel}:{lineno}: 禁兼容层「{label}」，用 agent.mechanisms.quality"
                )
    # 模块文件本身也不得回流
    shim = package_root / "mechanisms" / "quality_gate.py"
    if shim.is_file():
        violations.append(f"{_rel_to_root(shim)}: 禁保留 quality_gate 兼容模块")
    return violations


def check(
    package_root: Path = PACKAGE_ROOT,
    plugins_dir: Path = PLUGINS_DIR,
    js_root: Path = CLASSIC_JS,
    prompts: Path = PROMPTS_PY,
) -> list[str]:
    """跑全部约束规则，返回违规列表（空 = 通过）。"""
    out: list[str] = []
    out.extend(check_cross_layer_private_imports(package_root))
    out.extend(check_test_method_names())
    same_layer = check_same_layer_private_imports(package_root)
    if len(same_layer) > SAME_LAYER_PRIVATE_BUDGET:
        out.extend(
            f"同层私有导入存量 {len(same_layer)} > 预算 {SAME_LAYER_PRIVATE_BUDGET}: {h}"
            for h in same_layer[:10]
        )
    out.extend(check_kernel_plugin_names(package_root, plugins_dir))
    out.extend(check_shell_js_skill_manage(js_root))
    out.extend(check_shell_prompts_skill_manage(prompts))
    out.extend(check_gate_single_path(package_root))
    out.extend(check_prompts_preview_from_registry(prompts))
    out.extend(check_no_silent_system_prompt(package_root))
    out.extend(check_no_quality_gate_shim(package_root, plugins_dir))
    out.extend(check_provider_module_boundary(package_root))
    out.extend(check_compactor_contract_boundary(package_root))
    return out


def main() -> int:
    violations = check()
    if violations:
        print("架构约束违规：")
        for v in violations:
            print(" - " + v)
        return 1
    print(
        "架构约束检查通过（跨层私有导入 / 内核插件名 / 壳层 skill_manage / "
        "门控单通路 / 提示词注册表 / 无 quality_gate 兼容层 / Provider 边界 / "
        "压缩器接口 / 同层私有导入 / 系统提示词静默兜底 / 测试命名）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
