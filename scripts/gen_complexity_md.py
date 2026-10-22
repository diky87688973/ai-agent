# -*- coding: utf-8 -*-
"""生成 `docs/complexity.md`（--check 只比对，不写盘）。

用法：
    python scripts/gen_complexity_md.py            # 重写文档
    python scripts/gen_complexity_md.py --check    # 与磁盘比对，漂移则退出 1
"""
from __future__ import annotations

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
sys.path.insert(0, str(ROOT / "scripts"))

from complexity_scan import collect, render  # noqa: E402
from quality_budgets import (  # noqa: E402
    FILE_COMPLEXITY,
    FILE_FUNCTION_COMPLEXITY,
    FUNCTION_COMPLEXITY,
    MAX_FILE_FUNCTIONS,
    MAX_FILE_LINES,
    MAX_FUNCTION_LINES,
)

DOCS = ROOT / "docs" / "complexity.md"


def build(root: Path = ROOT) -> str:
    """按当前代码与登记表渲染全文。"""
    files, funcs, per_file = collect(root)
    return render(
        files,
        funcs,
        per_file,
        FILE_COMPLEXITY,
        FUNCTION_COMPLEXITY,
        MAX_FILE_LINES,
        MAX_FUNCTION_LINES,
        FILE_FUNCTION_COMPLEXITY,
        MAX_FILE_FUNCTIONS,
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    text = build()
    if "--check" in args:
        current = DOCS.read_text(encoding="utf-8") if DOCS.is_file() else ""
        if current.replace("\r\n", "\n") == text:
            print(f"✅ {DOCS.relative_to(ROOT)} 与代码一致")
            return 0
        print(f"[FAIL] {DOCS.relative_to(ROOT)} 已漂移，运行 python scripts/gen_complexity_md.py")
        return 1
    DOCS.write_text(text, encoding="utf-8", newline="\n")
    print(f"已生成 {DOCS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
