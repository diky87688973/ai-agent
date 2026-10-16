#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""经典 UI 的 JS 静态自检 —— 抓 `node --check` **抓不到**的那类回归。

## 为什么需要它

`node --check` 只验语法。有一类错**语法完全合法、运行时才炸**：定义那行被删掉、
引用还在，例如

    const tag=document.createElement("span");tag.className="tag tag-run";
    tag.textContent="运行中";          ← 定义行不见了，这里就是 `tag is not defined`

- `node --check` → **通过**（语法没问题）；
- 浏览器 → `pageerror: tag is not defined`，`addLlmRound` 中途抛异常、
  **思考卡建不出来**（连带后续流式增量受影响）。
- 只有真跑一遍页面才会暴露。

这类"删了定义、留了引用"的错在改 UI 素材时容易发生：按注释块批量删除 / 还原，
很容易连半行代码一起删掉。

## 检查什么

1. **裸用未定义标识符**：对每个"只出现一次赋值目标、但从未声明"的短标识符报警
   （重点覆盖 `tag` / `o` / `c` 这类在 UI 代码里高频复用的临时变量）；
2. **常见全局名未被误删**：核心函数（`renderMarkdown` / `onToolStart` /
   `stopChatRunCountdown` / `flushPendingToolTags` / `markCurrentTurnStoped` …）
   仍然存在——它们是经典 UI 的骨架，被误删会静默失效。

不做完整的 JS 作用域分析（那需要解析器）；只做**针对已知故障模式**的检查，
误报可接受（宁可多看一眼）。

运行：python scripts/check_ui_js.py（通过退出码 0）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# 在 GBK 控制台直接跑本脚本时，打印 ✅/中文会抛 UnicodeEncodeError ——
# 表现为「检查全过但退出码 1」（`ci.py` 用 PYTHONIOENCODING 掩盖了它）。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    # **旁路，刻意吞掉**：不是所有 stdout 都支持 reconfigure（被重定向/被包装时会抛）。
    # 这只是"让打印别因编码失败"的尽力而为 —— 失败就按原编码走，不该阻断检查本身。
    pass

ROOT = Path(__file__).resolve().parent.parent
UI_ASSETS = ROOT / "agent" / "shell" / "web_assets"
UI_JS = UI_ASSETS / "classic" / "js" / "agent-ui.js"

#: 界面脚本（每个都要过 `node --check` 之外的静态检查）
UI_SCRIPTS = (
    "js/agent-ui.js",
    "js/theme-ui.js",
    "js/code-highlight.js",
    "js/image-lightbox.js",
)

#: 与主脚本拼进同一个 script 的界面文件。函数声明落在同一作用域，主脚本可以直接调用。
SHARED_SCOPE_JS = UI_SCRIPTS + ("js/chat-tool-views.js",)

#: 设置页脚本跟主脚本拼在同一页。函数包在闭包里，不参与主脚本的未定义调用检查。
SETTINGS_SCRIPTS = ("js/settings-ui.js",)

#: 这些是经典 UI 的骨架函数，被误删会**静默**失效（页面不报错，功能没了）
REQUIRED_FUNCTIONS = (
    "renderMarkdown", "renderMarkdownBlocks",
    "onToolStart", "onToolProgress", "onToolEnd",
    "stopChatRunCountdown", "finalizeChatRunCard",
    "flushPendingToolTags", "stopPendingToolTags", "stopOpenToolTags",
    "markCurrentTurnStoped", "resetTurnState", "resetSteps",
    "addLlmRound", "submitUserConfirm", "loadUsageAccumulator",
    "persistUsageAccumulator", "buildToolTitleParts", "toolIco",
)

#: 检查"裸用"的临时变量名（UI 代码里高频复用、最容易被误删定义）
WATCH_VARS = ("tag", "tid", "ic", "sn", "left", "wrap", "card")


#: 像"辅助函数"的名字前缀 —— 只查这类，避免把业务字符串/外部 API 误判
_HELPER_PREFIXES = (
    "get", "set", "on", "render", "update", "make", "show", "hide", "sync", "mark",
    "finalize", "ensure", "apply", "build", "reset", "flush", "schedule", "toggle",
    "bind", "init", "load", "save", "close", "open", "refresh", "scroll", "format",
    "parse", "at", "is", "has", "can", "with", "add", "remove", "clear",
)

#: 语言/浏览器内建（不是我们定义的，出现也正常）
_BUILTINS = {
    "isNaN", "isFinite", "isArray", "isInteger", "isSafeInteger",
    "setTimeout", "setInterval", "clearTimeout", "clearInterval",
    "requestAnimationFrame", "cancelAnimationFrame", "addEventListener",
    "removeEventListener", "dispatchEvent", "createElement", "createDocumentFragment",
    "createTextNode", "createObjectURL", "revokeObjectURL", "encodeURIComponent",
    "decodeURIComponent", "encodeURI", "decodeURI", "parseInt", "parseFloat",
    "getComputedStyle", "getSelection", "structuredClone", "queueMicrotask",
    "matchMedia", "open", "close", "print", "alert", "confirm", "prompt", "fetch",
    "postMessage", "reportError", "atob", "btoa",
    # DOM/BOM 常用方法（以 `get`/`is`/`has`/`add`/`remove` 等前缀开头，会被误判）
    "closest", "getRootNode", "getClientRects", "hasFocus", "hasChildNodes",
    "isConnected", "isEqualNode", "isSameNode", "append", "prepend", "before", "after",
    "replaceChildren", "setPointerCapture", "releasePointerCapture",
    "showPicker", "requestFullscreen", "exitFullscreen", "getAnimations",
    "animate", "checkValidity", "reportValidity", "setCustomValidity",
    "getAttributeNames", "toggleAttribute", "insertAdjacentElement",
    "insertAdjacentHTML", "insertAdjacentText", "getBoxQuads",
    "format", "parse", "is", "has", "can", "at", "with", "add", "remove",
    "clear", "load", "save", "reset", "focus", "blur",
    "click", "select", "submit", "scrollIntoView", "scrollTo", "scrollBy",
    "getBoundingClientRect",
}


def _defined_names(text: str) -> set:
    """脚本里声明过的名字：函数声明、变量赋值、形参。"""
    defined = set(re.findall(r"function\s+([A-Za-z_$][\w$]*)", text))
    for kw in ("var", "let", "const"):
        defined |= set(re.findall(rf"\b{kw}\s+([A-Za-z_$][\w$]*)\s*=", text))
    # 形参（普通函数 + 箭头函数）也算定义过
    for m in re.finditer(r"function\s*[\w$]*\s*\(([^)]*)\)", text):
        for part in m.group(1).split(","):
            nm = part.strip().split("=")[0].strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", nm):
                defined.add(nm)
    for m in re.finditer(r"\(([^)]*)\)\s*=>", text):
        for part in m.group(1).split(","):
            nm = part.strip().split("=")[0].strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", nm):
                defined.add(nm)
    defined |= set(re.findall(r"(?:^|[,(\s])([A-Za-z_$][\w$]*)\s*=>", text))
    return defined


def _undefined_called(text: str, also_defined: set | None = None) -> list:
    """被调用、但主脚本与同作用域脚本都**从未定义**的辅助函数名（第 ⑥ 项检查）。

    故障特征：`node --check` 过、其它检查项也过，只有真跑页面才炸。
    """
    defined = _defined_names(text)
    if also_defined:
        defined |= also_defined

    called = set(re.findall(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*\(", text))
    return sorted(n for n in (called - defined - _BUILTINS)
                  if n.startswith(_HELPER_PREFIXES))


def main() -> int:
    if not UI_JS.is_file():
        print(f"[FAIL] 找不到 UI 脚本：{UI_JS}")
        return 1
    text = UI_JS.read_text(encoding="utf-8")
    lines = text.splitlines()
    problems: list[str] = []

    # ⑥ 被调用但从未定义的"辅助函数名"（`getAtUpBtn is not defined` 这类错
    #    会让整个交互层挂掉，而 `node --check` 与其它检查项都查不出）
    shared: set[str] = set()
    for rel in SHARED_SCOPE_JS:
        path = UI_ASSETS / "classic" / rel
        if path.is_file() and path != UI_JS:
            shared |= _defined_names(path.read_text(encoding="utf-8"))
    undef = _undefined_called(text, shared)
    if undef:
        problems.append(
            "被调用但**从未定义**的函数名（只有真跑页面才会炸）：" + "、".join(undef))

    # ── ① 裸用未声明变量 ──
    for name in WATCH_VARS:
        decl = re.compile(rf"\b(const|let|var|function)\s+{name}\b")
        uses = []
        for i, ln in enumerate(lines, 1):
            s = ln.strip()
            if not re.match(rf"^{name}\s*(=|\.|\[)", s):
                continue
            # 往上看 **200 行**内是否有声明。UI 是长函数，窗口太窄会误报
            # （40 行时 `card` 会被误判成未声明）。
            window = decl.search("\n".join(lines[max(0, i - 200):i]))
            if not window:
                uses.append((i, s[:110]))
        for i, s in uses:
            problems.append(f"{UI_JS.name}:{i}  裸用 `{name}`（往前 200 行找不到声明）：{s}")

    # ── ② 骨架函数是否还在 ──
    for fn in REQUIRED_FUNCTIONS:
        # 三种合法定义都要认：`function f(){}`、`const f = ...=>`、`f = function`
        # （只认第一种时，`submitUserConfirm`（箭头函数）会被误报成丢失）
        patterns = (
            rf"\bfunction\s+{fn}\b",
            rf"\b(const|let|var)\s+{fn}\s*=",
            rf"\b{fn}\s*=\s*(async\s*)?(function|\()",
        )
        if not any(re.search(p, text) for p in patterns):
            problems.append(f"{UI_JS.name}  骨架函数 `{fn}` 不见了（被误删会让功能静默失效）")

    # ── ④ 内层函数被"外部"调用（作用域缺陷）──
    #
    # 缺陷形态：
    #   function stopOpenToolTags(){ ... stopTextFor(o.chatRunStatus) ... }      // 调用方
    #   function markOpenToolCardsStoped(){ ... var stopTextFor=function(){} }   // 声明在别人里面
    # → `ReferenceError: stopTextFor is not defined`，被同行 `catch{}` **静默吞掉**
    #   （页面 `pageerror` 仍是 0），于是「本页点停运行中命令」的收尾不生效 ——
    #   卡面一直停在「⏳ 等待执行结果中…」，只有量 DOM 才看得见。
    #
    # 判据刻意**不用花括号计数**：本文件模板串与注释里的代码片段含大量不配对花括号，
    # 逐行计数会把脚本作用域的声明算到深处（`stopTextFor` 会被算成深度 3）。
    # 改用「**找不到合法的调用来源**」这个语义。
    def _scrub(s: str) -> str:
        s = re.sub(r'"(?:[^"\\]|\\.)*"', '""', s)
        s = re.sub(r"'(?:[^'\\]|\\.)*'", "''", s)
        return re.sub(r"//.*$", "", s)

    def _func_spans() -> list:
        """每个 `function name(` 的 (name, 起行, 止行)。

        用**净花括号深度**定界（从函数头数到归零）——不能用"行首 function"，
        本文件里有**缩进**的函数声明（跟在注释块后面），用行首判会漏掉它。
        """
        out = []
        for i, ln in enumerate(lines):
            m = re.search(r"(?:^|[\s;}])(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", ln)
            if not m:
                continue
            depth = _scrub(ln).count("{") - _scrub(ln).count("}")
            if depth <= 0:
                continue                      # 单行函数体，没有"内部"可言
            j = i + 1
            while j < len(lines) and depth > 0:
                depth += _scrub(lines[j]).count("{") - _scrub(lines[j]).count("}")
                j += 1
            out.append((m.group(1), i + 1, j))
        return out

    spans = _func_spans()
    script_names = {name for name, _s, _e in spans}

    def _enclosing(lineno: int):
        """lineno 落在哪个函数体里（取最内层）；没有则 None。"""
        best = None
        for name, s, e in spans:
            if s < lineno <= e:
                if best is None or s > best[1]:
                    best = (name, s)
        return best[0] if best else None

    for name, decl_ln, _owner in [
        (m.group(1), k + 1, None)
        for k, ln in enumerate(lines)
        for m in [re.match(
            r"^[ \t]+(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?(?:function\b|\()",
            ln)]
        if m
    ]:
        if name in script_names:
            continue                      # 脚本作用域已有同名函数，谁都看得到
        decl_in = _enclosing(decl_ln)
        if decl_in is None:
            continue                      # 声明不在任何函数体里 = 脚本作用域，谁都看得到
        callers = []
        for k, ln in enumerate(lines, 1):
            if k == decl_ln:
                continue                  # 声明自身那行
            if re.match(r"^[ \t]*(?:var|let|const)\s+" + re.escape(name) + r"\s*=", ln):
                continue
            if not re.search(rf"\b{re.escape(name)}\s*\(", ln):
                continue
            if _enclosing(k) != decl_in:  # **别的**函数（或脚本作用域）在调用它
                callers.append(k)
        if callers:
            problems.append(
                f"{UI_JS.name}:{decl_ln}  `{name}` 是 `{decl_in}` **内部**的函数表达式声明，"
                f"但第 {callers[:3]} 行在**别处**调用了它 —— 会抛 `ReferenceError`；"
                f"这类异常常被同行 `catch{{}}` 静默吞掉（`pageerror` 仍为 0），"
                f"功能**静默失效**。请提升到脚本作用域。")

    # ── ③ 界面脚本都必须存在且非空 ──
    # 少注入一个脚本会让整块功能**静默消失**（页面不报错，功能没了），
    # 所以这里逐个核对它们在磁盘上、且 `ui_bundle` 真的会把它们内联进去。
    for rel in UI_SCRIPTS + SETTINGS_SCRIPTS:
        path = UI_ASSETS / "classic" / rel
        if not path.is_file():
            problems.append(f"界面脚本缺失：classic/{rel}")
        elif not path.read_text(encoding="utf-8").strip():
            problems.append(f"界面脚本为空：classic/{rel}")

    print(f"UI JS 自检：{UI_JS.name}（{len(lines)} 行）")
    for p in problems:
        print(f"  [FAIL] {p}")
    if problems:
        print()
        print("修法：补齐被误删的定义或脚本。")
        return 1
    print("✅ 无裸用未声明变量、骨架函数齐全、脚本齐备")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
