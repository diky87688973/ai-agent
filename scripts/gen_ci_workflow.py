# -*- coding: utf-8 -*-
"""由 `scripts/ci_steps.py` 生成 `.github/workflows/ci.yml`。

    python scripts/gen_ci_workflow.py            # 重新生成
    python scripts/gen_ci_workflow.py --check    # 只校验（yml 与清单不一致即退出 1）

为什么生成而不是"再写一份"：`check_ci_workflow.py` 以前只比对步骤名，
命令参数改了、超时改了、少了一个 `--flag` 都发现不了。生成后是逐字节一致：
想改 CI 就改 `ci_steps.py`，再跑本脚本。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from ci_steps import ACCEPTANCE, acceptance_steps, gate_steps  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

_HEADER = """name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

# 本文件由 scripts/gen_ci_workflow.py 从 scripts/ci_steps.py 生成；直接改动会被下一次生成覆盖。
# `python scripts/gen_ci_workflow.py --check` 校验逐字节一致。

jobs:
  verify:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.10", "3.12"]
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip

      # 只装两个运行时依赖。可选依赖（playwright / pytesseract / easyocr /
      # rarfile / edge-tts）不装：不装时对应工具自行降级或明确报错；
      # 装了会让"缺依赖"那几个用例走 skip 分支、失去覆盖。
      - name: 安装依赖
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e . -c constraints.txt
          python -m pip install ruff coverage -c constraints.txt

"""

_UNITTEST = """      - name: 单测（按文件，各限时 150 秒）
        timeout-minutes: 15
        shell: bash
        run: |
          # `-e` 必须关掉：某个文件非零退出时，`-e` 会终止整个脚本，后面的文件再也
          # 跑不到，失败清单就只剩第一个。这里自己记状态、统一在末尾退出。
          set +e
          # 逐文件跑，输出先落盘再打印：超时被杀（137）时已产出的日志也不会丢。
          # 退出码 2 = 该文件在本平台按设计跳过，不算失败。
          fail=0; skip=0
          skip_names=()
          for f in tests/test_*.py; do
            mod=$(basename "$f" .py)
            echo "::group::$mod"
            timeout 150 python -u -m unittest "tests.$mod" > "/tmp/$mod.log" 2>&1
            code=$?
            cat "/tmp/$mod.log"
            echo "::endgroup::"
            if [ "$code" -eq 2 ]; then
              echo "   $mod 跳过"
              skip=$((skip+1))
              skip_names+=("$mod")
            elif [ "$code" -ne 0 ]; then
              echo "::error::$mod 退出码 $code"
              fail=$((fail+1))
            fi
          done
          echo "失败 $fail 个文件，跳过 $skip 个"
          if [ "$skip" -gt 0 ]; then
            echo "单测跳过名单：${skip_names[*]}"
          fi
          [ "$fail" -eq 0 ]

"""

_ACCEPT_PREP = """      # 验收经 run_acceptance_step：打印 SKIP/OK/FAIL；码 2 记入 ACC_SKIP_FILE。
      - name: 准备验收 skip 文件
        shell: bash
        run: |
          echo "ACC_SKIP_FILE=$RUNNER_TEMP/fan_acc_skips.txt" >> "$GITHUB_ENV"
          : > "$RUNNER_TEMP/fan_acc_skips.txt"

"""

_TAIL = """      - name: 验收 skip 预算
        timeout-minutes: 2
        run: python -u scripts/check_acceptance_skips.py

      # 覆盖率只在 3.12 矩阵跑一遍，避免双倍单测墙钟。
      # 下限按顶层包分开登记在 scripts/quality_budgets.py，缺数据/低于下限都会失败。
      # 数据由 scripts/run_coverage.py 先写独立文件、再原子发布，并行采集不会留下半份数据。
      - name: 覆盖率（分包下限）
        if: matrix.python-version == '3.12'
        timeout-minutes: 20
        run: |
          python -u scripts/run_coverage.py
          python -u scripts/check_coverage.py
          python -m coverage html -d coverage_html
      - name: 上传覆盖率报告
        if: matrix.python-version == '3.12' && always()
        uses: actions/upload-artifact@v4
        with:
          name: coverage-html-${{ matrix.python-version }}
          path: coverage_html
          if-no-files-found: ignore

      - name: 工程 data/ 检查
        run: >
          python -c "import subprocess,sys;
          r=subprocess.run(['git','status','--porcelain','data'],capture_output=True,text=True);
          sys.exit('CI 往工程 data/ 写了文件:\\n'+r.stdout) if r.stdout.strip() else print('data/ 干净')"
"""


def _gate_block() -> str:
    lines: List[str] = []
    for step in gate_steps():
        lines.append(f"      - name: 门禁 {step.label}")
        lines.append(f"        timeout-minutes: {step.timeout_minutes}")
        lines.append(f"        run: python -u {' '.join(step.argv)}")
    return "\n".join(lines) + "\n\n"


def _acceptance_block() -> str:
    lines: List[str] = []
    for step in acceptance_steps():
        short = step.script_key.replace("scripts/", "").replace(".py", "")
        lines.extend([
            f"      - name: {step.label}",
            f"        timeout-minutes: {step.timeout_minutes}",
            "        shell: bash",
            "        run: |",
            "          set +e",
            f"          python -u scripts/run_acceptance_step.py {short}",
            "          code=$?",
            f'          if [ "$code" -eq 2 ]; then echo "{short}" >> "$ACC_SKIP_FILE"; exit 0; fi',
            '          exit "$code"',
        ])
    return "\n".join(lines) + "\n\n"


def render() -> str:
    """渲染整份 workflow（末尾保留一个换行）。"""
    return (
        _HEADER
        + _gate_block()
        + _UNITTEST
        + _ACCEPT_PREP
        + _acceptance_block()
        + _TAIL
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    content = render()
    if "--check" in args:
        if not WORKFLOW.is_file():
            print(f"[FAIL] 缺少 {WORKFLOW.relative_to(ROOT)}")
            return 1
        current = WORKFLOW.read_text(encoding="utf-8")
        if current != content:
            print(
                f"[FAIL] {WORKFLOW.relative_to(ROOT)} 与 scripts/ci_steps.py 不一致"
                "（跑 python scripts/gen_ci_workflow.py 重新生成）"
            )
            return 1
        print(f"{WORKFLOW.relative_to(ROOT)} 与 ci_steps 逐字节一致")
        return 0
    WORKFLOW.parent.mkdir(parents=True, exist_ok=True)
    WORKFLOW.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {WORKFLOW} ({len(content)} chars, 门禁 {len(gate_steps())}、"
          f"验收 {len(ACCEPTANCE)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
