#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""经典 UI 的 JS 静态自检 —— 抓 `node --check` 抓不到的那类回归。

## 为什么需要它

`node --check` 只验语法。有一类错语法完全合法、运行时才炸：定义那行被删掉、
引用还在，例如

    10|    const tag=document.createElement("span");tag.className="tag tag-run";
    tag.textContent="运行中";          ← 定义行不见了，这里就是 `tag is not defined`

- `node --check` → 通过（语法没问题）；
- 浏览器 → `pageerror: tag is not defined`，`addLlmRound` 中途抛异常、
  思考卡建不出来（连带后续流式增量受影响）。
- 只有真跑一遍页面才会暴露。

这类"删了定义、留了引用"的错在改 UI 素材时容易发生：按注释块批量删除 / 还原，
很容易连半行代码一起删掉。

## 检查什么

1. 裸用未定义标识符：对每个"只出现一次赋值目标、但从未声明"的短标识符报警
   （重点覆盖 `tag` / `o` / `c` 这类在 UI 代码里高频复用的临时变量）；
2. 常见全局名未被误删：核心函数（`renderMarkdown` / `onToolStart` /
   `stopChatRunCountdown` / `flushPendingToolTags` / `markCurrentTurnStoped` …）
   仍然存在——它们是经典 UI 的骨架，被误删会静默失效。

不做完整的 JS 作用域分析（那需要解析器）；只做针对已知故障模式的检查，
误报可接受（宁可多看一眼）。

主脚本已按模块拆分（`agent/shell/ui_bundle.py` 的清单）。模块共用同一个
`<script>` 作用域，所以这里把所有同作用域模块拼成一份文本再检查，
报错行号会映射回具体模块文件。

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
    # 旁路，刻意吞掉：不是所有 stdout 都支持 reconfigure（被重定向/被包装时会抛）。
    # 这只是"让打印别因编码失败"的尽力而为 —— 失败就按原编码走，不该阻断检查本身。
    pass

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.shell.ui_bundle import (  # noqa: E402  （路径注入后才能导入）
    CLASSIC_DIR,
    UI_JS_MODULES,
    UI_POST_JS_MODULES,
    UI_PRE_JS_MODULES,
)

#: 与主脚本拼进同一个 script 的其它脚本（vendor 是第三方压缩代码，不参与检查；
#: 设置页脚本包在闭包里，也不参与"未定义调用"检查）。
SHARED_EXTRA_JS = tuple(
    rel for rel in UI_PRE_JS_MODULES + UI_POST_JS_MODULES
    if "/vendor/" not in rel and not rel.endswith("settings-ui.js")
)

#: 这些是经典 UI 的骨架函数，被误删会静默失效（页面不报错，功能没了）
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

#: 厂商模型 id 字面量：模型清单只能来自服务端 `/health` 与插件目录，
#: 前端一旦写死就变成第二权威（切换插件后仍然显示旧模型）。
_MODEL_ID_RE = re.compile(
    r"\b(?:deepseek|glm|claude|gpt|gemini|qwen|llama)-[A-Za-z0-9][A-Za-z0-9._-]*")


def model_id_literals(text: str) -> list[tuple[int, str]]:
    """返回含厂商模型 id 的行号与内容（0 条即通过）。"""
    return [
        (lineno, line.strip())
        for lineno, line in enumerate(text.splitlines(), 1)
        if _MODEL_ID_RE.search(line)
    ]



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
    """被调用、但主脚本与同作用域脚本都从未定义的辅助函数名（第 ⑥ 项检查）。

    故障特征：`node --check` 过、其它检查项也过，只有真跑页面才炸。
    """
    defined = _defined_names(text)
    if also_defined:
        defined |= also_defined

    called = set(re.findall(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*\(", text))
    return sorted(n for n in (called - defined - _BUILTINS)
                  if n.startswith(_HELPER_PREFIXES))


def _load_shared() -> tuple[list[str], list[tuple[str, int]], set[str]]:
    """把同作用域模块拼成一份文本，并给出每行的 (模块, 模块内行号) 映射。

    用 `\\n;\\n` 连接：分隔符独占一行，行号映射简单且不改变脚本语义。
    """
    lines: list[str] = [""]  # 让行号从 1 开始，与编辑器一致
    owner: list[tuple[str, int]] = [("", 0)]
    for rel in UI_JS_MODULES:
        text = (CLASSIC_DIR / "js" / rel).read_text(encoding="utf-8")
        lines.append(";")
        owner.append((rel, 0))
        for i, ln in enumerate(text.splitlines(), 1):
            lines.append(ln)
            owner.append((rel, i))
    extra_defined: set[str] = set()
    for rel in SHARED_EXTRA_JS:
        path = CLASSIC_DIR / rel
        if path.is_file():
            extra_defined |= _defined_names(path.read_text(encoding="utf-8"))
    return lines, owner, extra_defined


def _where(owner: list[tuple[str, int]], lineno: int) -> str:
    rel, local = owner[lineno] if 0 < lineno < len(owner) else ("?", lineno)
    return f"{rel}:{local}" if rel else f"?:{lineno}"


def _js_path(rel: str) -> Path:
    """模块清单里的相对路径：主脚本相对 `classic/js/`，其余相对 `classic/`。"""
    if rel in UI_JS_MODULES:
        return CLASSIC_DIR / "js" / rel
    return CLASSIC_DIR / rel


def main() -> int:
    missing = [
        rel for rel in UI_JS_MODULES + UI_PRE_JS_MODULES + UI_POST_JS_MODULES
        if not _js_path(rel).is_file()
    ]
    if missing:
        print(f"[FAIL] 找不到 UI 脚本：{', '.join(missing)}")
        return 1

    lines, owner, extra_defined = _load_shared()
    text = "\n".join(lines)
    problems: list[str] = []
    total = sum(len((CLASSIC_DIR / "js" / rel).read_text(encoding="utf-8").splitlines())
                for rel in UI_JS_MODULES)

    # ⑥ 被调用但从未定义的"辅助函数名"（`getAtUpBtn is not defined` 这类错
    #    会让整个交互层挂掉，而 `node --check` 与其它检查项都查不出）
    undef = _undefined_called(text, extra_defined)
    if undef:
        problems.append(
            "被调用但从未定义的函数名（只有真跑页面才会炸）：" + "、".join(undef))

    # ── ① 裸用未声明变量 ──
    for name in WATCH_VARS:
        decl = re.compile(rf"\b(const|let|var|function)\s+{name}\b")
        uses = []
        for i, ln in enumerate(lines, 1):
            s = ln.strip()
            if not re.match(rf"^{name}\s*(=|\.|\[)", s):
                continue
            # 往上看 200 行内是否有声明。UI 是长函数，窗口太窄会误报
            # （40 行时 `card` 会被误判成未声明）；跨模块拼接后窗口依旧有效。
            window = decl.search("\n".join(lines[max(0, i - 200):i]))
            if not window:
                uses.append((i, s[:110]))
        for i, s in uses:
            problems.append(f"{_where(owner, i)}  裸用 `{name}`（往前 200 行找不到声明）：{s}")

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
            problems.append(f"骨架函数 `{fn}` 不见了（被误删会让功能静默失效）")

    # ── ④ 内层函数被"外部"调用（作用域缺陷）──
    #
    # 缺陷形态：
    #   function stopOpenToolTags(){ ... stopTextFor(o.chatRunStatus) ... }      // 调用方
    #   function markOpenToolCardsStoped(){ ... var stopTextFor=function(){} }   // 声明在别人里面
    # → `ReferenceError: stopTextFor is not defined`，被同行 `catch{}` 静默吞掉
    #   （页面 `pageerror` 仍是 0），于是「本页点停运行中命令」的收尾不生效 ——
    #   卡面一直停在「⏳ 等待执行结果中…」，只有量 DOM 才看得见。
    #
    # 判据刻意不用花括号计数：模板串与注释里的代码片段含大量不配对花括号，
    # 逐行计数会把脚本作用域的声明算到深处（`stopTextFor` 会被算成深度 3）。
    # 改用「找不到合法的调用来源」这个语义。
    def _scrub(s: str) -> str:
        s = re.sub(r'"(?:[^"\\]|\\.)*"', '""', s)
        s = re.sub(r"'(?:[^'\\]|\\.)*'", "''", s)
        return re.sub(r"//.*$", "", s)

    def _func_spans() -> list:
        """每个 `function name(` 的 (name, 起行, 止行)。

        用净花括号深度定界（从函数头数到归零）——不能用"行首 function"，
        模块里也有缩进的函数声明（跟在注释块后面），用行首判会漏掉它。
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
            r"^[ \t]+(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|\()",
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
            if _enclosing(k) != decl_in:  # 别的函数（或脚本作用域）在调用它
                callers.append(k)
        if callers:
            problems.append(
                f"{_where(owner, decl_ln)}  `{name}` 是 `{decl_in}` 内部的函数表达式声明，"
                f"但 {_where(owner, callers[0])} 等处在别处调用了它 —— 会抛 "
                f"`ReferenceError`；这类异常常被同行 `catch{{}}` 静默吞掉"
                f"（`pageerror` 仍为 0），功能静默失效。请提升到脚本作用域。")

    # ── ③ 界面脚本都必须存在且非空 ──
    # 少注入一个脚本会让整块功能静默消失（页面不报错，功能没了），
    # 所以这里逐个核对它们在磁盘上、且 `ui_bundle` 真的会把它们内联进去。
    for rel in UI_JS_MODULES + UI_PRE_JS_MODULES + UI_POST_JS_MODULES:
        path = _js_path(rel)
        if path.is_file() and not path.read_text(encoding="utf-8").strip():
            problems.append(f"界面脚本为空：{path.relative_to(CLASSIC_DIR)}")

    # ── ⑤ 前端不得有厂商模型 id 种子 ──
    # 种子会在 `/health` 失败或插件切换后变成第二权威：页面显示旧模型、
    # 请求却按服务端清单拒绝，用户看到的是"保存了却没生效"。
    for path in sorted(CLASSIC_DIR.rglob("*.js")):
        if "vendor" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            # 单个静态文件读不到就跳过；它不该让整个检查无法给出其余结论。
            continue
        for lineno, line in model_id_literals(text):
            problems.append(
                f"{path.relative_to(CLASSIC_DIR)}:{lineno} 出现厂商模型 id 字面量：{line[:90]}")

    print(f"UI JS 自检：{len(UI_JS_MODULES)} 个主脚本模块（{total} 行）")
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
