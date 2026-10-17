# -*- coding: utf-8 -*-
"""架构洁癖检查：跨层私有导入、内核插件名、壳层 skill_manage 硬编码。

用法：python scripts/check_architecture_hygiene.py（工程根运行；违规时退出码 1）
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

LAYERS = ("core", "mechanisms", "capabilities", "shell")
ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = ROOT / "agent"
PLUGINS_DIR = ROOT / "plugins"
CLASSIC_JS = PACKAGE_ROOT / "shell" / "web_assets" / "classic" / "js"
PROMPTS_PY = PACKAGE_ROOT / "shell" / "prompts.py"

# 标识符边界：避免 `atts` 误伤 `tts` 这类短名。
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


# 门控单通路 / 预览只认 needs_preview：源码禁旁路字面量
_BANNED_GATE_LITERALS = (
    "_fallback_gate",
    "preview_tools=",
    "gate_resolver",
    "_TOOL_PATH_KEYS",
    "register_write_path_keys",
    "unregister_write_path_keys",
    "content_tools =",
)

# prompts 纪律段不得再手写整串内置写工具名单
_HANDWRITTEN_WRITE_TOOLS = (
    "write_file / replace_in_file / apply_patch / read_write / "
    "delete_file / file_ops / file_undo / archive"
)


def check_gate_single_path(package_root: Path = PACKAGE_ROOT) -> list[str]:
    """禁门控旁路字面量（_fallback_gate / preview_tools= / gate_resolver）。"""
    violations: list[str] = []
    for py in sorted(package_root.rglob("*.py")):
        rel = py.relative_to(ROOT)
        text = py.read_text(encoding="utf-8")
        for needle in _BANNED_GATE_LITERALS:
            if needle in text:
                violations.append(f"{rel}: 禁旁路字面量「{needle}」")
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


def check_no_silent_system_prompt(package_root: Path = PACKAGE_ROOT) -> list[str]:
    """禁把系统提示词失败吞成空串。"""
    violations: list[str] = []
    needle = "system_text = \"\""
    for py in sorted((package_root / "shell").rglob("*.py")):
        text = py.read_text(encoding="utf-8")
        # 仅禁止 except 后赋空串的苟且；初始赋值另论
        if "except" in text and needle in text:
            # 粗检：同一文件里 except 与 system_text = "" 同时出现且含 resolve_system_prompt
            if "resolve_system_prompt" in text and "except Exception:\n        system_text = \"\"" in text.replace("\r\n", "\n"):
                rel = py.relative_to(ROOT)
                violations.append(f"{rel}: 禁静默 system_text 空串")
    return violations


#: 写盘门控只认 quality 包；禁兼容模块路径回流
_BANNED_QUALITY_GATE_SHIM = (
    "mechanisms.quality_gate",
    "import quality_gate",
)


def check_no_quality_gate_shim(
    package_root: Path = PACKAGE_ROOT,
    plugins_dir: Path = PLUGINS_DIR,
) -> list[str]:
    """禁 `quality_gate` 兼容层：实现只在 mechanisms.quality。"""
    violations: list[str] = []
    roots = (package_root, plugins_dir, ROOT / "tests")
    for root in roots:
        if not root.is_dir():
            continue
        for py in sorted(root.rglob("*.py")):
            if "__pycache__" in py.parts:
                continue
            text = py.read_text(encoding="utf-8")
            rel = py.relative_to(ROOT)
            for needle in _BANNED_QUALITY_GATE_SHIM:
                if needle in text:
                    violations.append(f"{rel}: 禁兼容层「{needle}」，用 agent.mechanisms.quality")
    # 模块文件本身也不得回流
    shim = package_root / "mechanisms" / "quality_gate.py"
    if shim.is_file():
        violations.append(f"{shim.relative_to(ROOT)}: 禁保留 quality_gate 兼容模块")
    return violations


def check(
    package_root: Path = PACKAGE_ROOT,
    plugins_dir: Path = PLUGINS_DIR,
    js_root: Path = CLASSIC_JS,
    prompts: Path = PROMPTS_PY,
) -> list[str]:
    """跑全部洁癖规则，返回违规列表（空 = 通过）。"""
    out: list[str] = []
    out.extend(check_cross_layer_private_imports(package_root))
    out.extend(check_kernel_plugin_names(package_root, plugins_dir))
    out.extend(check_shell_js_skill_manage(js_root))
    out.extend(check_shell_prompts_skill_manage(prompts))
    out.extend(check_gate_single_path(package_root))
    out.extend(check_prompts_preview_from_registry(prompts))
    out.extend(check_no_silent_system_prompt(package_root))
    out.extend(check_no_quality_gate_shim(package_root, plugins_dir))
    return out


def main() -> int:
    violations = check()
    if violations:
        print("架构洁癖违规：")
        for v in violations:
            print(" - " + v)
        return 1
    print(
        "架构洁癖检查通过（跨层私有导入 / 内核插件名 / 壳层 skill_manage / "
        "门控单通路 / 提示词注册表 / 无 quality_gate 兼容层）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
