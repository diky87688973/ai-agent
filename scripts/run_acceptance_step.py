# -*- coding: utf-8 -*-
"""跑单个验收脚本，统一 OK / SKIP / FAIL 输出（供 GitHub CI 与本地使用）。

用法：python scripts/run_acceptance_step.py acceptance_batch_a

退出码：0=通过，1=失败，2=跳过（环境不满足）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIPPED = 2


def main(argv: list[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    if not args or args[0] in ("-h", "--help"):
        print("用法：python scripts/run_acceptance_step.py <acceptance_name>")
        return 1
    name = args[0].strip().removesuffix(".py")
    if name.startswith("scripts/"):
        name = name.split("/")[-1]
    script = ROOT / "scripts" / f"{name}.py"
    if not script.is_file():
        print(f"FAIL: {name}（脚本不存在：{script.relative_to(ROOT)}）")
        return 1

    env = {**dict(**{k: v for k, v in __import__("os").environ.items()}),
           "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        [sys.executable, "-u", str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if out.strip():
        print(out.rstrip())
    if proc.returncode == SKIPPED:
        reason = (out.strip().splitlines() or ["环境不满足"])[-1][:120]
        print(f"SKIP: {name} ({reason})")
        return SKIPPED
    if proc.returncode == 0:
        print(f"OK: {name}")
        return 0
    print(f"FAIL: {name}（退出码 {proc.returncode}）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
