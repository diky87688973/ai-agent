#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Python 版本下限检查 —— 守住"写法下限 3.10"。

## 为什么需要它

Python 3.10+，写法下限 3.10。本机是 3.12，所以 3.11 / 3.12 才有的语法
在这里永远不会报错；把下限声明放宽（`requires-python`、ruff 的
`target-version`）会让 3.10 上直接 SyntaxError 的代码通过检查，
等交付到 3.10 环境才炸，那时定位成本极高。

这类"下限声明"必须可执行，否则就是纸面保证。

## 判据

按 AST 节点识别"3.11 / 3.12 才有的语法"，这些是语法级不兼容，
在 3.10 上直接 SyntaxError：

| 语法 | 引入版本 | AST 特征 |
|---|---|---|
| `except*`（异常组） | 3.11 | `TryStar` |
| `type X = ...`（类型别名语句） | 3.12 | `TypeAlias` |
| PEP 695 泛型 `def f[T]()` / `class C[T]` | 3.12 | 函数/类的 `type_params` 非空 |

`match`（3.10）、`X | Y` 类型联合（3.10，且工程内有
`from __future__ import annotations`）都是合法的，不报。

运行：python scripts/check_python_floor.py（通过退出码 0）
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

# 在 GBK 控制台直接跑本脚本时，打印 ✅/中文会抛 UnicodeEncodeError ——
# 表现为「检查全过但退出码 1」（`ci.py` 用 PYTHONIOENCODING 掩盖了它）。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception as exc:
    # 旁路，刻意吞掉：不是所有 stdout 都支持 reconfigure（被重定向/被包装时会抛）。
    # 这只是"让打印别因编码失败"的尽力而为 —— 失败就按原编码走，不该阻断检查本身。
    print(f"[scripts.check_python_floor.module] {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

ROOT = Path(__file__).resolve().parent.parent
#: 写法下限
FLOOR = (3, 10)
SCAN_DIRS = ("agent", "tests", "scripts")
SKIP_PARTS = ("__pycache__", "retired")

#: 高版本才有的节点类型。不能直接写 `ast.TryStar`：这两个属性分别到 3.11 / 3.12
#: 才存在，本脚本在 3.10 上取属性就 AttributeError —— 下限检查器自己越界。
_TRY_STAR = getattr(ast, "TryStar", None)
_TYPE_ALIAS = getattr(ast, "TypeAlias", None)


def _violations(tree: ast.AST) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if _TRY_STAR is not None and isinstance(node, _TRY_STAR):
            out.append((node.lineno, "`except*`（异常组）需要 Python 3.11+"))
        elif _TYPE_ALIAS is not None and isinstance(node, _TYPE_ALIAS):
            out.append((node.lineno, "`type X = ...`（类型别名语句）需要 Python 3.12+"))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if getattr(node, "type_params", None):
                out.append((node.lineno, "PEP 695 泛型参数 `[...]` 需要 Python 3.12+"))
    return out


def main() -> int:
    bad: list[str] = []
    files = 0
    for base in SCAN_DIRS:
        for f in (ROOT / base).rglob("*.py"):
            rel = f.relative_to(ROOT).as_posix()
            if any(p in rel for p in SKIP_PARTS):
                continue
            files += 1
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except SyntaxError as exc:                     # 本机 3.12 解析不了 = 更严重
                bad.append(f"{rel}:{exc.lineno} 语法错误：{exc.msg}")
                continue
            for lineno, why in _violations(tree):
                bad.append(f"{rel}:{lineno}  {why}")

    floor = "%d.%d" % FLOOR
    print(f"Python 写法下限检查：{files} 个文件，下限 {floor}+")
    for line in bad:
        print(f"  [FAIL] {line}")
    if bad:
        # 这里刻意不把转义写进 f-string 表达式：
        # f-string 表达式里出现反斜杠是 Python 3.12+ 才允许的，
        # 而本脚本自身就必须能在 3.10 上跑（否则"下限检查器"自己越界）。
        hint = "修法：改用 " + floor + " 可用的等价写法"
        print()
        print(hint + "（提高下限是一次决策，需单独确认）。")
        return 1
    print("✅ 无超出下限的语法")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
