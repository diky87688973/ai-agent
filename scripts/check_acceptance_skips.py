# -*- coding: utf-8 -*-
"""汇总验收 skip 名单；非白名单或超上限则失败。

跳过名单由 CI 各验收步追加一行脚本名；路径见环境变量 ACC_SKIP_FILE。
未设置 ACC_SKIP_FILE 时不读共享临时文件（避免本地残留假失败），直接通过并提示。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ci_steps import (  # type: ignore
    ALLOWED_ACCEPTANCE_SKIPS,
    MAX_ACCEPTANCE_SKIPS,
    acceptance_skip_problems,
)


def main() -> int:
    raw = (os.environ.get("ACC_SKIP_FILE") or "").strip()
    if not raw:
        print(
            "未设置 ACC_SKIP_FILE：跳过汇总"
            f"（白名单 {sorted(ALLOWED_ACCEPTANCE_SKIPS)}，上限 {MAX_ACCEPTANCE_SKIPS}）"
        )
        return 0
    path = Path(raw)
    names: list[str] = []
    if path.is_file():
        text = path.read_text(encoding="utf-8-sig")  # 吞 BOM
        names = [ln.strip() for ln in text.splitlines() if ln.strip()]
    problems = acceptance_skip_problems(names)
    allowed = ", ".join(sorted(ALLOWED_ACCEPTANCE_SKIPS)) or "（无）"
    print(
        f"验收跳过 {len(set(names))} 项（白名单 {allowed}，上限 {MAX_ACCEPTANCE_SKIPS}）："
        f"{', '.join(names) if names else '（无）'}"
    )
    if problems:
        for p in problems:
            print(f"[FAIL] {p}")
        return 1
    print("✅ 验收 skip 均在白名单内且未超限")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
