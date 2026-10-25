# -*- coding: utf-8 -*-
"""本地 JS 事件绑定审计：为重渲染列表是否逐项绑事件提供可判定的线索。

初衷（换一个会话也照这条读）：
    重渲染的列表——每次刷新都重建节点的那种——不给每个列表项单独绑事件。
    事件只在顶层 document 上绑一次，靠冒泡 + closest/contains 认目标。
    逐项绑的代价是每次重建都新建一批监听，节点删了监听还可能留在闭包里。
    这件事要读业务语义才能定，GitHub Actions 上没有模型，所以只跑本地。

做法：只输出分级清单，不自动失败。判定维度全部机械可复算——循环归属、
函数归属、委托守卫标记、目标是否随节点新建、document/window 上的监听
有没有配对摘除。模型只需复核"需确认"那几类。

判准是静态近似：括号配平会跳过字符串、模板字符串与注释，但不会真正解析 JS。
由本地 `scripts/ci.py` 调用；`GITHUB_ACTIONS=true` 时自行跳过。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
SCAN_ROOTS = (ROOT / "agent", ROOT / "plugins")
EXCLUDED_DIRS = frozenset({
    "vendor", "node_modules", ".git", "data", "dist", "build",
    "coverage_html", "__pycache__", ".venv", "venv",
})
JS_SUFFIXES = frozenset({".js", ".mjs", ".cjs"})
HTML_SUFFIXES = frozenset({".html", ".htm"})

#: 绑在这些对象上才算「全局」；委托判定另算，两者不是一回事。
GLOBAL_TARGETS = frozenset({
    "document", "window", "document.body", "document.documentelement",
})
#: 函数名带这些词视为渲染路径：这类函数会被反复调用，绑在里面的监听要看会不会累积。
RENDER_FN_RE = re.compile(
    r"render|create|build|update|refresh|mount|fill|paint|draw|append|insert|ensure",
    re.I,
)
#: 方法调用式循环：配平圆括号天然含回调体。
_LOOP_CALL_RE = re.compile(
    r"\.\s*(?:forEach|map|filter|reduce|some|every|find|flatMap|findIndex)\s*\(")
#: 语句式循环：头部括号只圈住条件，循环体在括号之后，必须另外吃掉。
#: `do...while` 的 while 只会圈到尾部条件，循环体识别不到；这类写法本项目没有，
#: 出现时按普通绑定处理，不会误报成循环内。
_LOOP_STMT_RE = re.compile(r"\b(?:for|while)\s*\(")
FUNC_RE = re.compile(
    r"(?:function\s+(?P<a>[A-Za-z_$][\w$]*)\s*\("
    r"|(?P<b>[A-Za-z_$][\w$]*)\s*[:=]\s*(?:async\s+)?function\s*\()"
)
#: 箭头函数赋值：`const renderX = (...) => {}` / `const renderX = () => {}`。
_ARROW_VAR_RE = re.compile(
    r"(?P<name>[A-Za-z_$][\w$]*)\s*[:=]\s*(?:async\s+)?"
    r"(?:\([^()]*\)|[A-Za-z_$][\w$]*)\s*=>")
#: ES6 对象/类方法简写：`renderPanel(){ ... }`，没有 function 关键字。
_OBJECT_METHOD_RE = re.compile(
    r"(?<![.\w])(?P<name>[A-Za-z_$][\w$]*)\s*\([^()]*\)\s*\{")
#: 上一条会把 `if(...){` / `for(...){` 这类语句头也照进去，按名字排掉。
_NOT_METHOD_NAMES = frozenset({
    "if", "for", "while", "switch", "catch", "with", "function", "return",
    "typeof", "do", "else", "try", "finally", "new", "delete", "void",
})
#: 委托守卫的既有惯例：`_kbClickDelegated` / `_pluginActionDelegated` / `dataset.bound`。
GUARD_RE = re.compile(r"_[A-Za-z]\w*(?:Delegated|Bound|Wired)\b|dataset\.bound")
#: 委托判准。`closest` 几乎只用于从事件目标向上找，出现即算。
#: `contains` 不同——数组、字符串、业务集合都有 contains，所以只认事件对象与 `this`
#: 上的那两种写法；否则一句无关的 `arr.contains(x)` 就能把元素监听抬成容器委托。
DELEGATE_CALL_RE = re.compile(
    r"\.\s*closest\s*\("
    r"|\b(?:ev|evt|e|event)\b(?:\?)?(?:\.[A-Za-z_$][\w$]*|\[[^\]]*\])*\.\s*contains\s*\("
    r"|\bthis\s*\.\s*contains\s*\(")
#: 匿名回调：`function(){...}`、`(a,b)=>{...}`、`x=>{...}`，均可带 `async`。
ANON_CALLBACK_RE = re.compile(
    r"^(?:async\s+)?(?:function\b|\([^()]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)")

_ADD_RE = re.compile(
    r"(?P<target>[A-Za-z_$][\w$]*(?:\s*(?:\.\s*[A-Za-z_$][\w$]*|\[[^\]]*\]|\([^()]*\)))*)\s*\.\s*addEventListener\s*\("
)
_PROP_RE = re.compile(
    r"(?P<target>[A-Za-z_$][\w$]*(?:\s*(?:\.\s*[A-Za-z_$][\w$]*|\[[^\]]*\]|\([^()]*\)))*)\s*\.\s*(?P<event>on[A-Za-z]+)\s*="
)
_HTML_RE = re.compile(
    r"\bon(?P<event>click|dblclick|mousedown|mouseup|keydown|keyup|input|change|submit|focus|blur|contextmenu)\s*=\s*([\"'])"
)
_STRING_ARG_RE = re.compile(r"\s*(?P<quote>[\"'])(?P<event>[^\"']+)(?P=quote)")


@dataclass(frozen=True)
class Binding:
    """一条事件绑定，附带静态可判定的上下文。"""

    path: str
    line: int
    kind: str
    target: str
    event: str
    code: str
    scope: str          # global / container / element
    delegated: bool     # 是否真的走了委托（全局监听，或容器根 + 目标识别）
    in_loop: bool       # 是否落在循环体内
    func: str           # 最内层具名函数，缺省 <module>
    render_fn: bool     # 所在函数是否渲染路径
    guarded: bool       # 同函数内是否有委托守卫标记
    ephemeral: bool     # 目标是否由 createElement 新建（随节点销毁）
    anonymous: bool     # 回调是否匿名（无法摘除）
    paired_remove: bool # 同目标同事件同回调同 capture 是否有配对摘除
    verdict: str        # 分级结论


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _code_line(text: str, offset: int) -> str:
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    if end < 0:
        end = len(text)
    return text[start:end].strip()[:240]


def _block_comment_mask(text: str) -> List[bool]:
    """逐字符标记是否位于块注释内，避免把注释里的示例代码当成绑定。"""
    mask = [False] * len(text)
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            for k in range(i, end):
                mask[k] = True
            i = end
        else:
            i += 1
    return mask


def _in_line_comment(text: str, offset: int) -> bool:
    """offset 是否落在本行 `//` 之后。引号内的 `//`（如 URL）不算。"""
    start = text.rfind("\n", 0, offset) + 1
    quote = ""
    i = start
    while i < offset:
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "\"'`":
            quote = ch
        elif ch == "/" and i + 1 < len(text) and text[i + 1] == "/":
            return True
        i += 1
    return False


def _is_comment_position(text: str, offset: int, block: Sequence[bool]) -> bool:
    if block[offset]:
        return True
    line = _code_line(text, offset)
    if line.startswith(("//", "/*", "<!--")):
        return True
    return _in_line_comment(text, offset)


def _skip_literal(text: str, idx: int) -> int:
    """idx 指向引号、模板反引号或注释开头时，返回该字面量之后的位置。

    配平必须跳过字面量：回调里一句 `var s = "a) b"` 会让按字符计数的配平
    提前收口，把整段回调截断，进而把委托判成元素绑定。
    """
    n = len(text)
    if idx >= n:
        return n
    ch = text[idx]
    if ch in "\"'`":
        quote = ch
        i = idx + 1
        while i < n:
            cur = text[i]
            if cur == "\\":
                i += 2
                continue
            if cur == quote:
                return i + 1
            if quote == "`" and cur == "$" and i + 1 < n and text[i + 1] == "{":
                close = _match_close(text, i + 1)
                i = (close + 1) if close > 0 else i + 2
                continue
            i += 1
        return n
    if ch == "/" and idx + 1 < n:
        nxt = text[idx + 1]
        if nxt == "/":
            end = text.find("\n", idx)
            return n if end < 0 else end
        if nxt == "*":
            end = text.find("*/", idx + 2)
            return n if end < 0 else end + 2
    return idx


def _match_close(text: str, open_idx: int) -> int:
    """从左括号求配对右括号下标；失败返回 -1。字符串与注释整段跳过。"""
    pairs = {"(": ")", "{": "}", "[": "]"}
    opener = text[open_idx]
    closer = pairs.get(opener)
    if closer is None:
        return -1
    depth = 0
    i = open_idx
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in "\"'`":
            i = _skip_literal(text, i)
            continue
        if ch == "/" and i + 1 < n and text[i + 1] in "/*":
            i = _skip_literal(text, i)
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _body_end(text: str, start: int) -> int:
    """语句式循环的循环体终点：有花括号就配平，没有就到语句结束。"""
    n = len(text)
    i = start
    while i < n and text[i] in " \t\r\n":
        i += 1
    if i >= n:
        return -1
    if text[i] == "{":
        return _match_close(text, i)
    depth = 0
    while i < n:
        ch = text[i]
        if ch in "\"'`":
            i = _skip_literal(text, i)
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth <= 0 and ch in ";\n":
            return i
        i += 1
    return n - 1


def _loop_spans(text: str) -> List[Tuple[int, int]]:
    """循环体区间。方法调用式配平括号即可；语句式还要额外吃掉循环体。"""
    spans: List[Tuple[int, int]] = []
    for match in _LOOP_CALL_RE.finditer(text):
        close = _match_close(text, match.end() - 1)
        if close > 0:
            spans.append((match.start(), close))
    for match in _LOOP_STMT_RE.finditer(text):
        head = _match_close(text, match.end() - 1)
        if head < 0:
            continue
        end = _body_end(text, head + 1)
        if end > head:
            spans.append((match.start(), end))
    return spans


def _func_spans(text: str) -> List[Tuple[int, int, str]]:
    """返回 (起点, 终点, 名字)。覆盖具名函数、赋值函数与箭头函数。"""
    spans: List[Tuple[int, int, str]] = []
    for match in FUNC_RE.finditer(text):
        brace = text.find("{", match.end())
        if brace < 0:
            continue
        close = _match_close(text, brace)
        if close > 0:
            name = match.group("a") or match.group("b") or "<anonymous>"
            spans.append((match.start(), close, name))
    for match in _ARROW_VAR_RE.finditer(text):
        brace = text.find("{", match.end())
        if brace < 0:
            continue
        # 只有块体箭头才有区间：表达式体（`x => x + 1`）后面跟的不是 `{`。
        if text[match.end():brace].strip():
            continue
        close = _match_close(text, brace)
        if close > 0:
            spans.append((match.start(), close, match.group("name")))
    for match in _OBJECT_METHOD_RE.finditer(text):
        if match.group("name") in _NOT_METHOD_NAMES:
            continue
        brace = text.rfind("{", match.start(), match.end())
        if brace < 0:
            continue
        close = _match_close(text, brace)
        if close > 0:
            spans.append((match.start(), close, match.group("name")))
    return spans


def _scope_of(target: str, callback: str) -> str:
    """`delegated` 判准：绑在全局 / 容器根且做目标识别 / 元素自身。"""
    lowered = re.sub(r"\s+", "", target).lower()
    if lowered in GLOBAL_TARGETS:
        return "global"
    if DELEGATE_CALL_RE.search(callback):
        return "container"
    return "element"


#: 赋值语句：`var X = 表达式` 或裸 `X = 表达式`；`(?!=)` 排掉 `==` 比较。
#: 两种都收，是因为模块级变量常在函数里懒赋值（`el = createElement(...)`）。
_ASSIGN_RE = re.compile(
    r"\b(?:(?:var|let|const)\s+)?(?P<name>[A-Za-z_$][\w$]*)\s*=(?!=)\s*(?P<rhs>[^;\n]*)")
#: 来源是「查找已有节点」：这类变量指向持久 DOM，即便查找函数内部用了 createElement。
_LOOKUP_CALL_RE = re.compile(r"getElementById|querySelector|\bget[A-Z]\w*\s*\(")
#: 来源是「创建新节点」，含本项目 `el()` 工厂；`(?<![.\w])` 排掉 `.el(` 这种属性访问。
_CREATE_CALL_RE = re.compile(r"createElement|createTextNode|cloneNode|(?<![.\w])el\s*\(")


def _ephemeral_names(text: str) -> frozenset:
    """挑出指向新建节点的变量名——这些节点随作用域销毁，挂在上面不会累积。

    查找优先于创建：`var list = getAtList()` 取的是页面上已有的容器，
    即使 getAtList 内部调用了 createElement 也不该算新节点。
    """
    fresh, kept = set(), set()
    for match in _ASSIGN_RE.finditer(text):
        name, rhs = match.group("name"), match.group("rhs")
        if _LOOKUP_CALL_RE.search(rhs):
            kept.add(name)
        elif _CREATE_CALL_RE.search(rhs):
            fresh.add(name)
    return frozenset(fresh - kept)


def _is_ephemeral(fresh: frozenset, target: str) -> bool:
    """目标名是否指向新建节点——这类监听随节点销毁，不累积。"""
    return target.split("(")[0].strip() in fresh


_CALLBACK_AFTER_EVENT_RE = re.compile(
    r"\s*,\s*(?P<callback>[A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)*)"
    r"\s*(?:,\s*(?P<capture>true|false)\s*)?\)?\s*$"
)


def _listener_callback(callback: str) -> tuple[str, bool]:
    """从 `(event, callback[, capture])` 取具名回调；匿名回调无法配对。"""
    arg = _STRING_ARG_RE.match(callback[1:] if callback.startswith("(") else callback)
    if not arg:
        return "", False
    rest = (callback[1:] if callback.startswith("(") else callback)[arg.end():]
    match = _CALLBACK_AFTER_EVENT_RE.match(rest)
    if not match:
        return "", False
    name = re.sub(r"\s+", "", match.group("callback"))
    return name, str(match.group("capture") or "false").lower() == "true"


def _has_paired_remove(text: str, target: str, event: str,
                       callback: str = "") -> bool:
    """同目标、同事件、同回调、同 capture 才算摘除。"""
    if not event or event == "<dynamic>":
        return False
    base = re.sub(r"\s+", "", target).split("(")[0]
    if not base:
        return False
    callback_name, capture = _listener_callback(callback)
    if not callback_name:
        return False
    pattern = (
        r"\b" + re.escape(base) + r"\s*\.\s*removeEventListener\s*\(\s*"
        r"[\"']" + re.escape(event) + r"[\"']\s*,\s*"
        r"(?P<callback>[A-Za-z_$][\w$]*(?:\s*\.\s*[A-Za-z_$][\w$]*)*)"
        r"\s*(?:,\s*(?P<capture>true|false)\s*)?\)"
    )
    for match in re.finditer(pattern, text):
        if re.sub(r"\s+", "", match.group("callback")) != callback_name:
            continue
        remove_capture = str(match.group("capture") or "false").lower() == "true"
        if remove_capture == capture:
            return True
    return False


def _verdict(kind: str, scope: str, in_loop: bool, render_fn: bool,
             guarded: bool, ephemeral: bool, paired_remove: bool) -> str:
    """分级。返回 REVIEW_VERDICTS 之一表示需复核，其余为已排除的写法。

    回调是否匿名不影响分级：能不能摘除与有没有摘除是两件事，后者才决定泄漏。
    匿名仅在报告里展示，供模型判断该监听能否被摘掉。
    """
    if in_loop:
        return "per-item"
    if scope == "global":
        # 渲染路径上反复执行就会反复安装监听。具名引用只代表「能摘除」，
        # 不保证「已经摘除」，也不排除每次传入不同的具名引用；所以只看配对摘除，
        # 不再要求回调匿名。模块级只执行一次，不算风险。
        if render_fn and not paired_remove:
            return "leak-risk"
        return "global-once"
    if scope == "container":
        # 容器根委托是正确写法，即便写在渲染函数里也只绑一次，不该报累积。
        return "delegated-ok"
    if render_fn and not ephemeral and not guarded:
        return "render-path"
    if guarded:
        return "guarded-ok"
    if ephemeral:
        return "ephemeral"
    return "ok"


def scan_text(text: str, path: str = "<memory>") -> List[Binding]:
    """扫描一段 JS/HTML 文本，返回带上下文的绑定清单。"""
    out: List[Binding] = []
    block = _block_comment_mask(text)
    loops = _loop_spans(text)
    funcs = _func_spans(text)
    ephem = _ephemeral_names(text)
    is_js = path.lower().endswith(tuple(JS_SUFFIXES))

    def build(match: "re.Match[str]", kind: str, event: str) -> None:
        start = match.start()
        if _is_comment_position(text, start, block):
            return
        target = re.sub(r"\s+", "", match.group("target"))
        open_paren = text.find("(", match.end() - 1)
        close_paren = _match_close(text, open_paren) if open_paren >= 0 else -1
        callback = text[open_paren:close_paren + 1] if close_paren > 0 else ""

        # 参数列表形如 ("click", function(){...})：跳过事件名再判回调是否匿名。
        body = callback[1:] if callback else ""
        arg = _STRING_ARG_RE.match(body)
        if arg:
            body = body[arg.end():]
        anonymous = bool(ANON_CALLBACK_RE.match(body.lstrip(" ,")))

        enclosing = [f for f in funcs if f[0] <= start <= f[1]]
        enclosing.sort(key=lambda f: f[1] - f[0])
        func_name = enclosing[0][2] if enclosing else "<module>"
        func_start = enclosing[0][0] if enclosing else 0
        # 渲染上下文看整条函数链：绑定可能写在内层小函数里，只要任一祖先函数
        # 是渲染路径，它就会随外层重建被反复安装。
        render_fn = any(RENDER_FN_RE.search(f[2]) for f in enclosing)
        scope = _scope_of(target, callback)
        in_loop = bool([s for s in loops if s[0] < start < s[1]])
        guarded = bool(GUARD_RE.search(text[func_start:start]))
        ephemeral = _is_ephemeral(ephem, target)
        paired = _has_paired_remove(text, target, event, callback)
        out.append(Binding(
            path=path,
            line=_line_of(text, start),
            kind=kind,
            target=target,
            event=event,
            code=_code_line(text, start),
            scope=scope,
            delegated=scope in ("global", "container"),
            in_loop=in_loop,
            func=func_name,
            render_fn=render_fn,
            guarded=guarded,
            ephemeral=ephemeral,
            anonymous=anonymous,
            paired_remove=paired,
            verdict=_verdict(kind, scope, in_loop, render_fn, guarded,
                             ephemeral, paired),
        ))

    for match in _ADD_RE.finditer(text):
        arg = _STRING_ARG_RE.match(text[match.end():])
        build(match, "addEventListener", arg.group("event") if arg else "<dynamic>")

    if is_js:
        for match in _PROP_RE.finditer(text):
            build(match, "property", match.group("event")[2:])

    if path.lower().endswith(tuple(HTML_SUFFIXES)):
        for match in _HTML_RE.finditer(text):
            if _is_comment_position(text, match.start(), block):
                continue
            out.append(Binding(
                path=path, line=_line_of(text, match.start()), kind="inline-html",
                target="inline-html", event=match.group("event"),
                code=_code_line(text, match.start()), scope="element", delegated=False,
                in_loop=False, func="<module>", render_fn=False, guarded=False,
                ephemeral=False, anonymous=True, paired_remove=False, verdict="inline",
            ))
    return out


def iter_source_files() -> Iterable[Path]:
    """遍历参与审计的 JS/HTML 源文件。

    排除名单只按相对 root 的路径段匹配：拿绝对路径的段去比，项目一旦
    放在 `D:\\data\\...` 之类目录下就会整仓被静默排除、输出 0 条且退出码 0。
    """
    allowed = JS_SUFFIXES | HTML_SUFFIXES
    for base in SCAN_ROOTS:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in allowed:
                continue
            if path.name.endswith(".min.js"):
                continue
            try:
                parts = path.relative_to(ROOT).parts
            except ValueError:
                parts = path.parts
            if any(part.lower() in EXCLUDED_DIRS for part in parts[:-1]):
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


#: 需要模型复核的结论；其余为已排除的写法。
REVIEW_VERDICTS = ("per-item", "leak-risk", "render-path", "inline")
#: 已按静态依据排除的结论——与 REVIEW_VERDICTS 互补，文案里的类别数由两者算出。
EXCLUDED_VERDICTS = ("delegated-ok", "global-once", "guarded-ok", "ephemeral", "ok")
VERDICT_TITLES = {
    "per-item": "循环内逐项绑定（最该看）",
    "leak-risk": "渲染路径上的全局监听且无配对摘除（会泄漏）",
    "render-path": "渲染函数内绑在持久目标上（可能累积）",
    "inline": "内联 HTML 事件（无法委托）",
}


def read_guide() -> str:
    """读法说明。类别数从常量算出，避免手写数字与判定漂移。"""
    return (f"读法：{' / '.join(REVIEW_VERDICTS)} 共 {len(REVIEW_VERDICTS)} 类"
            f"需逐个判断；其余 {len(EXCLUDED_VERDICTS)} 类已按静态依据排除。")


def render(bindings: Sequence[Binding], file_count: int,
           only: Sequence[str] | None = None) -> str:
    review = [b for b in bindings if b.verdict in REVIEW_VERDICTS]
    excluded = [b for b in bindings if b.verdict not in REVIEW_VERDICTS]
    shown = [b for b in review if not only or b.verdict in only]

    lines = [
        "=== JS 事件绑定审计（本地）===",
        "初衷：重渲染列表不逐项绑事件；事件只在顶层 document 上绑一次，靠冒泡 + closest 认目标。",
        read_guide(),
        "定位：只列线索、不判失败、不进 GitHub Actions（要读业务语义，CI 上没有模型）。",
        "",
        f"扫描文件：{file_count}",
        f"发现绑定：{len(bindings)}",
        f"需确认：{len(review)}    已排除：{len(excluded)}",
        "",
    ]
    if not shown:
        lines.append("没有需要复核的绑定。")
    for verdict in REVIEW_VERDICTS:
        group = [b for b in shown if b.verdict == verdict]
        if not group:
            continue
        lines.append(f"--- {verdict}｜{VERDICT_TITLES[verdict]}（{len(group)}）---")
        for index, item in enumerate(group, start=1):
            lines.extend([
                f"[{index:02d}] {item.path}:{item.line}",
                f"  目标: {item.target}    事件: {item.event}    类型: {item.kind}",
                f"  位置: 函数={item.func}{'（渲染路径）' if item.render_fn else ''}"
                f"  循环内={'是' if item.in_loop else '否'}",
                f"  依据: 作用域={item.scope}  守卫={'有' if item.guarded else '无'}"
                f"  随节点新建={'是' if item.ephemeral else '否'}"
                f"  配对摘除={'有' if item.paired_remove else '无'}",
                f"  代码: {item.code}",
            ])
        lines.append("")

    lines.append("--- 已排除 ---")
    by_verdict: Dict[str, int] = {}
    for item in excluded:
        by_verdict[item.verdict] = by_verdict.get(item.verdict, 0) + 1
    lines.append("  ".join(f"{k}={v}" for k, v in sorted(by_verdict.items())) or "无")
    lines.append("委托 = 全局监听，或容器根 + closest / 事件对象 contains 目标识别；"
                 "随节点新建与守卫标记不计入需确认。")
    lines.append("global-once = 模块级或一次性初始化的全局监听（只绑一次）；"
                 "若该函数会被反复调用，需人工确认。")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    if os.environ.get("GITHUB_ACTIONS", "").strip().lower() == "true":
        print("SKIP JS 事件绑定审计：GitHub Actions 无模型判断")
        return 0
    parser = argparse.ArgumentParser(description="本地 JS 事件绑定审计")
    parser.add_argument("--only", default="",
                        help="只看某几类，逗号分隔：" + ",".join(REVIEW_VERDICTS))
    parser.add_argument("--path", default="", help="只看路径含该子串的文件")
    args = parser.parse_args(list(argv) if argv is not None else None)

    files = list(iter_source_files())
    bindings, file_count = scan_files(files)
    only = [v.strip() for v in args.only.split(",") if v.strip()] or None
    if args.path:
        bindings = [b for b in bindings if args.path in b.path]
    print(render(bindings, file_count, only))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
