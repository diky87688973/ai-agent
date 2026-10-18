#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""静默异常检查 —— 把"失败要大声"变成可执行判据。

## ruff BLE001 覆盖不到的部分

BLE001 抓的是"`except Exception` **本身**"（全仓 112 处），
**无法区分"吞掉"与"吞掉但留痕"**：全开会在全仓产生 112 个 `# noqa`，
而静默吞仍不可见。

所以这个检查器做**语义判断**：

1. `except Exception`（或裸 except）后 `return` 常量/空集合（`[]` / `None` / `""` / `"auto"` …）  
   → **一律禁止**，注释与惯用法都不可豁免（失败必须冒泡）。
2. `except Exception`（或裸 except）后**整段只有一条**赋值为常量/空集合/`None`/`"auto"`  
   → **一律禁止**（与 return 兜底同级；失败装成默认值）。
3. `except` 后紧跟 `pass` / `continue`（或空体）  
   → 静默吞；内核路径须留痕或写明判据；旁路须注释或命中惯用法。

## 规则（按目录分层）

| 目录 | 规则 | 是否让 CI 失败 |
|---|---|---|
| 全仓 | `except Exception` + `return` / 赋常量兜底 | **是**（`--all-strict`） |
| `core/`（**内核路径**） | `pass`/`continue` 不得无说明 | **是** |
| 其它（旁路） | `pass`/`continue` 须注释或惯用法 | **是**（`--all-strict`） |

"写明判据"的判定：`except` 行到 `pass` 行之间、或 `except` 上方 3 行内
出现注释即视为已说明（行内注释也算）。这样一条注释就能解释一个块。

## "已说明"的两种形式

当前全仓 `except` 后紧跟 `pass`/`continue` 的绝大多数属于已说明
（内核路径未说明必须为 0；确切条数以本脚本输出为准，改代码后自然会变）：

| 形式 | 含义 |
|---|---|
| **写了注释** | 在该处解释"为什么可以吞"（判据随代码走） |
| **命中已知惯用法** | 属于 `IDIOMS` 里登记的可识别写法（知识放一处） |

### 惯用法表：同类写法只登记一处

这些位置集中在十来个**反复出现的写法**上（资源关闭、路径包含判定、编码试探、
遍历跳过坏条目、格式探测、SSE 拆帧、进度上报旁路…）。登记在一处使同一判据
只有一份，且能识别整类写法。

**判据严格**：命中 `IDIOMS` 正则的静默放行；未命中且无注释的静默全部报出。

### 内核路径是硬约束

`core/` **一律不得静默**：要么留痕（`print(..., file=sys.stderr)`），
要么写明判据。`--strict` 会守住这条。

## 运行方式

    python scripts/check_silent_except.py                 # 报告
    python scripts/check_silent_except.py --strict        # 内核路径静默即失败
    python scripts/check_silent_except.py --all-strict    # 任何未说明都失败（CI 用这个）
    python scripts/check_silent_except.py --show-idioms   # 列出命中的惯用法
"""
from __future__ import annotations

import argparse
import ast
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
#: 惯用法命中上限：与登记表同源，只降不升（E2a）
from quality_budgets import SILENT_EXCEPT_IDIOM_BUDGET  # noqa: E402

#: 内核路径：这些目录里不允许无法解释的静默吞
KERNEL_DIRS = ("agent/core",)
SCAN_DIRS = ("agent", "tests", "scripts")
SKIP_PARTS = ("__pycache__", "retired")


def _catches_broad(node: ast.ExceptHandler) -> bool:
    """是否为裸 except / except Exception（宽捕才禁 return 兜底）。"""
    if node.type is None:
        return True
    if isinstance(node.type, ast.Name) and node.type.id == "Exception":
        return True
    if isinstance(node.type, ast.Tuple):
        return any(
            isinstance(elt, ast.Name) and elt.id == "Exception"
            for elt in node.type.elts
        )
    return False


def _is_fallback_constant(node: ast.AST | None) -> bool:
    """表达式是否为「装没事」用的常量 / 空集合 / None。"""
    if node is None:
        return True  # bare `return`
    if isinstance(node, ast.Constant):
        return True  # None / "" / 0 / -1 / "auto" / False …
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return len(getattr(node, "elts", []) or []) == 0
    if isinstance(node, ast.Dict):
        return len(getattr(node, "keys", []) or []) == 0
    if isinstance(node, ast.Name) and node.id == "None":
        return True
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "set"
        and not node.args
        and not node.keywords
    ):
        return True  # set()
    return False


def _is_fallback_return(body: list[ast.stmt]) -> bool:
    """except 体是否为「失败装没事」的 return 兜底（一律禁止，注释不可豁免）。"""
    if not body or len(body) != 1:
        return False
    only = body[0]
    if not isinstance(only, ast.Return):
        return False
    return _is_fallback_constant(only.value)


def _is_fallback_assign(body: list[ast.stmt]) -> bool:
    """except 体是否为「失败装没事」的赋常量（一律禁止，注释不可豁免）。"""
    if not body or len(body) != 1:
        return False
    only = body[0]
    if not isinstance(only, ast.Assign):
        return False
    return _is_fallback_constant(only.value)


def _is_fallback_mask(body: list[ast.stmt]) -> bool:
    """return 常量或赋常量：失败装成默认值。"""
    return _is_fallback_return(body) or _is_fallback_assign(body)


def _is_silent(body: list[ast.stmt]) -> bool:
    """except 体是否等价于静默吞：pass / continue / return 常量。

    赋常量不走这里——只在宽捕 `Exception` 时由 `_is_fallback_assign` 一律禁止；
    窄捕（如 `EOFError` / `ImportError`）赋默认值不属本检查范围。
    """
    if not body:
        return True
    if len(body) > 1:
        return False
    only = body[0]
    if isinstance(only, ast.Pass):
        return True
    if isinstance(only, ast.Continue):
        return True
    return _is_fallback_return(body)


def _explained(node: ast.ExceptHandler, lines: list[str]) -> bool:
    """这条静默吞是否**已说明原因**。

    两种写法都算已说明（都自然）：
      · 注释写在 `except` **体内**（解释"为什么可以吞"）；
      · 注释写在 `except` **上方**（解释"为什么这里要 try"）。

    扫描范围是 `[except 行, pass 行]`，**两端都含**：体内注释常在
    **行内**写在 `pass` 那一行上（`pass  # 分配失败不阻断回合`），
    跳过 `pass` 行本身就会把最常见的写法漏成"未说明"。
    """
    body_line = node.body[0].lineno if node.body else node.lineno
    for i in range(node.lineno - 1, min(body_line, len(lines))):
        if "#" in lines[i]:
            return True
    # 上方 3 行内的注释
    for i in range(max(0, node.lineno - 4), node.lineno - 1):
        if lines[i].lstrip().startswith("#"):
            return True
    return False


# ── 惯用法识别层 ────────────────────────────────────────────────────────────
#
# 惯用法层：反复出现的旁路写法登记在一处，同一判据只有一份。原委——
# （资源关闭、路径包含判定、编码试探、遍历跳过坏条目…）。逐个地方塞近乎
# 相同的注释，等于把噪声换个地方堆；**把知识放一处**（这里）更好维护，
# 而且更能表达"这是一类可识别的写法，不是随手吞掉"。
#
# 判据严格：**必须真正命中惯用法**才放行。任何未命中的静默仍会报出来。
#: (标签, 说明, try 体里应出现的模式)
IDIOMS: list[tuple[str, str, tuple[str, ...]]] = [
    ("资源关闭", "关闭/清理失败不该影响结果（对象已不再使用）",
     (r"\.close\(\)", r"\bdispose\(\)", r"\bdisposer\(\)", r"book\.close")),
    ("路径包含判定", "`relative_to` 抛异常**就是**\"不在根内\"的判定结果，不是错误",
     (r"\.relative_to\(",)),
    ("编码试探", "逐个编码试到能解码为止——试探失败是算法的一部分",
     (r"\.decode\(", r"read_text\(encoding=enc\)", r"encode\(\"ascii\"\)")),
    ("遍历跳过坏条目", "批量处理对**单条**失败的语义就是跳过，不该中断整批",
     (r"continue", r"for .* in ", r"read_text\(", r"json\.loads\(", r"\.stat\(\)",
      r"\.is_dir\(\)", r"is_file\(\)")),
    ("静默解析失败", "尽力解析，坏了就当没有（不阻断主流程）",
     (r"json\.loads\(", r"json\.dumps\(", r"int\(", r"float\(")),
    ("状态持久化尽力而为", "写状态失败只是这次不持久；内存态仍正确，重启后重建",
     (r"write_text\(", r"mkdir\(", r"unlink\(", r"chmod\(", r"open\(")),
    ("平台能力尽力而为", "外部命令/浏览器等平台能力不可用时应降级，而非失败",
     (r"subprocess\.run\(", r"os\.kill\(", r"webbrowser\.open\(")),
    ("格式探测", "按魔数/内容猜格式，猜不出就走默认",
     (r"f\.read\(", r"raw\s*=\s*f\.read", r"magic\[")),
    ("流帧解析", "SSE 拆帧时坏行直接丢弃；队列满时丢最旧帧（背压设计）",
     (r"line\[5:\]", r"get_nowait\(\)", r"put_nowait\(")),
    ("输入项不可用则跳过", "配置/路径/正则等**外部输入**可能非法，跳过该项继续处理其余",
     (r"\.resolve\(\)", r"re\.compile\(", r"realpath\(")),
    ("进度上报旁路", "进度是观察面：上报失败只丢过程显示，不影响结果",
     (r"reporter\(", r"on_progress\(", r"progress\(")),
    ("清理阶段尽力而为", "服务/应用收尾：已经要退出了，清理失败不该再抛",
     (r"shutdown\(\)", r"server_close\(\)", r"\.dispose\(\)")),
]


def _idiom(try_src: str) -> tuple[str, str] | None:
    """识别 try 体是否命中已知惯用法。返回 (标签, 说明)。"""
    for label, why, patterns in IDIOMS:
        if any(re.search(p, try_src) for p in patterns):
            return label, why
    return None


def _try_body(node: ast.ExceptHandler, lines: list[str]) -> str:
    """取该 except 所属 try 的体（向上找最近的 `try:`）。"""
    for i in range(node.lineno - 2, max(0, node.lineno - 30), -1):
        if lines[i].lstrip().startswith("try:"):
            return "\n".join(lines[i + 1:node.lineno - 1])
    return ""


def budget_problems(count: int, budget: int) -> list[str]:
    """惯用法命中数与预算比对（纯函数，供负向用例直接调用）。"""
    if count > budget:
        return [f"惯用法命中 {count} 处 > 预算 {budget}"]
    return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="检查静默吞异常")
    ap.add_argument("--strict", action="store_true",
                    help="内核路径静默即失败（CI 用；旁路仍只报告）")
    ap.add_argument("--show-idioms", action="store_true",
                    help="列出命中已知惯用法（已说明）的位置")
    ap.add_argument("--all-strict", action="store_true",
                    help="旁路未说明也失败（清完存量后切到这个模式）")
    args = ap.parse_args(argv)

    idiom_hits: list[str] = []
    kernel_bad: list[str] = []
    bypass_bad: list[str] = []
    syntax_bad: list[str] = []
    checked = 0

    for base in SCAN_DIRS:
        for f in (ROOT / base).rglob("*.py"):
            rel = f.relative_to(ROOT).as_posix()
            if any(p in rel for p in SKIP_PARTS):
                continue
            src = f.read_text(encoding="utf-8")
            try:
                tree = ast.parse(src)
            except SyntaxError as exc:
                syntax_bad.append(f"{rel}:{exc.lineno} {exc.msg}")
                continue

            lines = src.splitlines()
            is_kernel = any(rel.startswith(d + "/") for d in KERNEL_DIRS)

            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                where = f"{rel}:{node.lineno}"

                # except Exception + return/赋常量：一律禁止（注释/惯用法不可豁免）
                # 先于 `_is_silent` 判定，否则「仅赋常量」进不了静默分支会被漏掉。
                if _catches_broad(node) and _is_fallback_mask(node.body):
                    checked += 1
                    kind = "return" if _is_fallback_return(node.body) else "赋常量"
                    msg = (
                        f"{where}  ← 禁止 except Exception 后 {kind} 兜底"
                        "（失败必须冒泡，不可装成空/默认值）"
                    )
                    if is_kernel:
                        kernel_bad.append(msg)
                    else:
                        bypass_bad.append(msg)
                    continue

                if not _is_silent(node.body):
                    continue
                checked += 1

                # pass / continue / return 常量（窄捕）："已说明" = 注释或命中惯用法
                # 宽捕的 return 常量已在上一段禁掉；此处 return 只会是窄捕。
                if _explained(node, lines):
                    continue
                idiom = _idiom(_try_body(node, lines))
                if idiom is not None:
                    idiom_hits.append(f"{where}  [{idiom[0]}]")
                    continue

                if is_kernel:
                    kernel_bad.append(f"{where}  ← 内核路径静默吞异常且未说明原因")
                else:
                    bypass_bad.append(
                        f"{where}  ← 旁路静默吞未注明判据，且不属已知惯用法"
                    )

    print(f"静默 except 共 {checked} 处")
    print(f"  · 已说明（惯用法）：{len(idiom_hits)}/{SILENT_EXCEPT_IDIOM_BUDGET} 处"
          "（预算只降不升）")
    print(f"  · 内核路径未说明：{len(kernel_bad)} 处（必须为 0）")
    print(f"  · 旁路未说明：    {len(bypass_bad)} 处（存量债，见本文件顶部说明）")
    over_budget = budget_problems(len(idiom_hits), SILENT_EXCEPT_IDIOM_BUDGET)
    for problem in over_budget:
        print(f"  [FAIL] {problem}；新增惯用法必须逐点说明，不得扩表")
    if idiom_hits and args.show_idioms:
        print()
        print("  命中的惯用法：")
        for line in idiom_hits:
            print(f"    {line}")
    for line in syntax_bad:
        print(f"  [FAIL] 语法错误 {line}")
    for line in kernel_bad:
        print(f"  [FAIL] {line}")

    if args.all_strict:
        for line in bypass_bad:
            print(f"  [FAIL] {line}")

    if syntax_bad or kernel_bad or over_budget or (args.all_strict and bypass_bad):
        print()
        print("修法（二选一）：")
        print("  · 留痕：`except Exception as exc: print(f'[...] {exc}', file=sys.stderr, flush=True)`")
        print("  · 说明：在 `except` 体里或上方加注释写明为什么可以吞")
        return 1

    if kernel_bad:
        return 1
    print("✅ 内核路径零静默吞（每条要么留痕、要么写明判据）")
    if bypass_bad:
        print(f"   （另有 {len(bypass_bad)} 处旁路静默待补判据——不影响本次通过）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
