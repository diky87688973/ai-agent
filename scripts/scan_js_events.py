# -*- coding: utf-8 -*-
"""本地 JS 事件绑定审计：列出 addEventListener / onclick / 常用事件绑定。

不自动判失败。事件是否应该委托给顶层容器由模型判断，本脚本只提供清单。
GitHub Actions 不运行本脚本；由本地 `scripts/ci.py` 调用。
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOTS = (ROOT / "agent", ROOT / "plugins")
EXCLUDED_DIRS = frozenset({
    "vendor", "node_modules", ".git", "data", "dist", "build",
    "coverage_html", "__pycache__", ".venv", "venv",
})
JS_SUFFIXES = frozenset({".js", ".mjs", ".cjs"})
COMMON_EVENTS = frozenset({
    "click", "dblclick", "mousedown", "mouseup", "mousemove", "mouseover",
    "mouseout", "mouseenter", "mouseleave", "pointerdown", "pointerup",
    "pointermove", "keydown", "keyup", "keypress", "input", "change",
    "submit", "focus", "blur", "contextmenu", "wheel", "scroll",
    "touchstart", "touchmove", "touchend", "dragstart", "drag", "dragend",
    "drop", "paste", "copy", "cut",
})

_ADD_RE = re.compile(
    r"(?P<target>[A-Za-z_$][\w$]*(?:\s*(?:\.\s*[A-Za-z_$][\w$]*|\[[^\]]*\]|\([^()]*\)))*)\s*\.\s*addEventListener\s*\("
)
_PROP_RE = re.compile(
    r"(?P<target>[A-Za-z_$][\w$]*(?:\s*(?:\.\s*[A-Za-z_$][\w$]*|\[[^\]]*\]|\([^()]*\)))*)\s*\.\s*(?P<event>on[a-z]+)\s*="
)
_HTML_RE = re.compile(r"\bon(?P<event>click|dblclick|mousedown|mouseup|keydown|keyup|input|change|submit|focus|blur|contextmenu)\s*=\s*([\"'])")
_STRING_ARG_RE = re.compile(r"\s*(?P<quote>[\"'])(?P<event>[^\"']+)(?P=quote)")


@dataclass(frozen=True)
class Binding:
    """一条事件绑定。"""

    path: str
    line: int
    kind: str
    target: str
    event: str
    code: str
    delegated: bool


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _code_line(text: str, offset: int) -> str:
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    if end < 0:
        end = len(text)
    return text[start:end].strip()[:240]


def _is_comment_line(line: str) -> bool:
    s = line.lstrip()
    return s.startswith(("//", "/*", "*", "<!--"))


def _is_delegated_target(target: str) -> bool:
    t = re.sub(r"\s+", "", target).lower()
    return t in {"document", "window", "document.body", "document.documentelement"}


def scan_text(text: str, path: str = "<memory>") -> List[Binding]:
    """扫描一段 JS/HTML 文本。"""
    out: List[Binding] = []
    for match in _ADD_RE.finditer(text):
        line = _line_of(text, match.start())
        code = _code_line(text, match.start())
        if _is_comment_line(code):
            continue
        arg = _STRING_ARG_RE.match(text[match.end():])
        event = arg.group("event") if arg else "<dynamic>"
        target = re.sub(r"\s+", "", match.group("target"))
        out.append(Binding(path, line, "addEventListener", target, event, code,
                           _is_delegated_target(target)))
    if path.lower().endswith((".js", ".mjs", ".cjs")):
        for match in _PROP_RE.finditer(text):
            code = _code_line(text, match.start())
            if _is_comment_line(code):
                continue
            target = re.sub(r"\s+", "", match.group("target"))
            event = match.group("event")[2:]
            out.append(Binding(path, _line_of(text, match.start()), "property",
                               target, event, code, _is_delegated_target(target)))
    if path.lower().endswith((".html", ".htm")):
        for match in _HTML_RE.finditer(text):
            code = _code_line(text, match.start())
            if _is_comment_line(code):
                continue
            out.append(Binding(path, _line_of(text, match.start()), "inline-html",
                               "inline-html", match.group("event"), code, False))
    return out


def iter_source_files() -> Iterable[Path]:
    """遍历参与审计的 JS/HTML 源文件。"""
    for base in SCAN_ROOTS:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in (JS_SUFFIXES | {".html", ".htm"}):
                continue
            if path.name.endswith(".min.js"):
                continue
            if any(part.lower() in EXCLUDED_DIRS for part in path.parts):
                continue
            yield path


def scan_files(files: Sequence[Path]) -> Tuple[List[Binding], int]:
    bindings: List[Binding] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"[scan_js_events] 跳过不可读文件 {path}: {exc}", file=sys.stderr, flush=True)
            continue
        rel = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        bindings.extend(scan_text(text, str(rel)))
    return bindings, len(files)


def render(bindings: Sequence[Binding], file_count: int) -> str:
    lines = [
        "=== JS 事件绑定审计（本地）===",
        f"扫描文件：{file_count}",
        f"发现绑定：{len(bindings)}",
        "",
    ]
    for index, item in enumerate(bindings, start=1):
        level = "顶层" if item.delegated else "元素/动态"
        common = "" if item.event in COMMON_EVENTS or item.event == "<dynamic>" else "（非常用事件名）"
        lines.extend([
            f"[{index:03d}] {item.path}:{item.line}",
            f"  类型: {item.kind}",
            f"  目标: {item.target}",
            f"  事件: {item.event}{common}",
            f"  层级: {level}",
            f"  代码: {item.code}",
        ])
    lines.append("")
    lines.append("--- 汇总 ---")
    by_kind: dict[str, int] = {}
    by_target: dict[str, int] = {}
    for item in bindings:
        by_kind[item.kind] = by_kind.get(item.kind, 0) + 1
        by_target[item.target] = by_target.get(item.target, 0) + 1
    lines.append("类型: " + (", ".join(f"{k}={v}" for k, v in sorted(by_kind.items())) or "无"))
    lines.append("目标: " + (", ".join(f"{k}={v}" for k, v in sorted(by_target.items())) or "无"))
    lines.append("")
    lines.append("动态列表项禁止逐项绑定；顶层 document / 列表根容器上的委托不在此列。")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    if os.environ.get("GITHUB_ACTIONS", "").strip().lower() == "true":
        print("SKIP JS 事件绑定审计：GitHub Actions 无模型判断")
        return 0
    files = list(iter_source_files())
    bindings, file_count = scan_files(files)
    print(render(bindings, file_count))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
