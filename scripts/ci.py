#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一条命令跑完全部校验（CI 入口）。

步骤清单的**唯一事实源**是 `scripts/ci_steps.py`；GitHub Actions 逐步跑同一集合，
并由 `scripts/check_ci_workflow.py` 防止 yml 漂移。

## 用法

    python scripts/ci.py                 # 全跑，遇错即停
    python scripts/ci.py --keep-going    # 全跑，最后汇总
    python scripts/ci.py --fast          # 跳过验收脚本
    python scripts/ci.py --list          # 只列出会跑什么
"""
from __future__ import annotations

import argparse
import atexit
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        # 旧解释器 / 非 TTY：保持默认编码即可
        pass

sys.path.insert(0, str(ROOT / "scripts"))
from ci_steps import SKIPPED, acceptance_skip_problems, catalog  # noqa: E402


def _data_files() -> set:
    d = ROOT / "data"
    if not d.is_dir():
        return set()
    return {str(p.relative_to(ROOT)) for p in d.rglob("*") if p.is_file()}


def _prepare_data_root() -> None:
    _tmp_data = tempfile.mkdtemp(prefix="fan_ci_data_")
    os.environ["AI_AGENT_DATA_ROOT"] = _tmp_data
    atexit.register(shutil.rmtree, _tmp_data, True)


def _run(label: str, cmd: list[str]) -> tuple[str, str]:
    t0 = time.perf_counter()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        cmd, cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env,
    )
    dt = time.perf_counter() - t0
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == SKIPPED:
        reason = (out.strip().splitlines() or [""])[-1][:80]
        return "skipped", f"{dt:6.2f}s  SKIP  {label}（{reason}）"
    ok = proc.returncode == 0
    tail = ""
    if not ok:
        lines = [x for x in out.splitlines()
                 if "FAIL" in x or "ERROR" in x or "Error" in x or "Traceback" in x]
        tail = "\n".join((lines or out.splitlines())[-12:])
    return ("ok" if ok else "failed"), (
        f"{dt:6.2f}s  {'OK  ' if ok else 'FAIL'}  {label}" + (f"\n{tail}" if tail else "")
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="跑完全部校验")
    ap.add_argument("--keep-going", action="store_true", help="出错也继续，最后汇总")
    ap.add_argument("--fast", action="store_true", help="跳过验收脚本")
    ap.add_argument("--list", action="store_true", help="只列出会跑什么")
    args = ap.parse_args(argv)

    steps = catalog(fast=args.fast)
    if args.list:
        for step in steps:
            print(f"  {step.label:16} {step.kind:11} {step.script_key}")
        return 0

    _prepare_data_root()
    print(f"=== 校验开始（{len(steps)} 步）===")
    data_before = _data_files()
    failed: list[str] = []
    skipped: list[str] = []
    skipped_post: list[str] = []
    for step in steps:
        cmd = [PY, *step.argv]
        status, line = _run(step.label, cmd)
        print("  " + line)
        if status == "skipped":
            if step.kind == "acceptance":
                # 用脚本名对白名单（与 ACC_SKIP_FILE / ALLOWED_ACCEPTANCE_SKIPS 同源）
                key = ""
                if step.argv and str(step.argv[0]).endswith("run_acceptance_step.py"):
                    key = str(step.argv[-1]).removesuffix(".py")
                skipped.append(key or step.label)
            else:
                # 覆盖率等 post 步在本地可能没有 .coverage：可见但不计入验收 skip 预算
                skipped_post.append(step.label)
        elif status == "failed":
            failed.append(step.label)
            if not args.keep_going:
                print(f"\n❌ 在「{step.label}」失败，已停止（--keep-going 可跑完）")
                return 1

    if failed:
        print(f"\n❌ 失败 {len(failed)} 项：{', '.join(failed)}")
        return 1
    if skipped:
        print(f"\n⚠️ 跳过 {len(skipped)} 项（本机环境不满足，非产品问题）："
              f"{', '.join(skipped)}")
        problems = acceptance_skip_problems(skipped)
        if problems:
            for p in problems:
                print(f"\n❌ {p}")
            return 1
    if skipped_post:
        print(f"\nℹ️ 本地跳过后置校验：{', '.join(skipped_post)}"
              "（覆盖率需要先跑 coverage，CI 里由 3.12 矩阵执行）")
    if not args.fast:
        left = sorted(_data_files() - data_before)
        if left:
            print(f"\n⚠️ 工程 `data/` 多了 {len(left)} 个文件"
                  f"（不是运行期数据，删掉即可）：")
            for p in left[:10]:
                print(f"     {p}")
            if len(left) > 10:
                print(f"     …还有 {len(left) - 10} 个")
        else:
            print("\n✅ 工程 `data/` 无新增文件")

    passed = len(steps) - len(skipped) - len(skipped_post)
    print(f"\n✅ 通过 {passed} 步"
          + (f"，跳过 {len(skipped) + len(skipped_post)} 步"
             if (skipped or skipped_post) else "（全部）"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
