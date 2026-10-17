# -*- coding: utf-8 -*-
"""校验 GitHub workflow 与 scripts/ci_steps 清单一致（单一事实源）。

用法：python scripts/check_ci_workflow.py（工程根）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:
        # 旧解释器 / 非 TTY：保持默认编码即可
        pass

# 允许出现在 yml 但不在 gate/acceptance 清单里的 run 片段（安装、单测循环、data 检查）
_ALLOWED_EXTRA = (
    "pip install",
    "unittest",
    "tests/test_",
    "git status",
    "data/",
    "run_acceptance_step",  # 封装本身
    "coverage",             # 覆盖率基线（post）
)


def _run_blocks(text: str) -> list[str]:
    """抽出 workflow 里所有 run: | 或多行/单行 run 内容。"""
    blocks: list[str] = []
    # run: | ... 缩进块
    for m in re.finditer(r"(?m)^([ \t]*)run:\s*\|\s*\n((?:\1[ \t].*\n?)*)", text):
        blocks.append(m.group(2))
    # run: > ...
    for m in re.finditer(r"(?m)^([ \t]*)run:\s*>\s*\n((?:\1[ \t].*\n?)*)", text):
        blocks.append(m.group(2))
    # run: 单行
    for m in re.finditer(r"(?m)^[ \t]*run:\s*([^|\n][^\n]*)\n", text):
        blocks.append(m.group(1))
    return blocks


def main() -> int:
    # 延迟导入，避免循环；清单在 ci_steps
    sys.path.insert(0, str(ROOT / "scripts"))
    from ci_steps import ACCEPTANCE, acceptance_steps, gate_steps  # type: ignore

    if not WORKFLOW.is_file():
        print(f"[FAIL] 缺少 {WORKFLOW.relative_to(ROOT)}")
        return 1
    text = WORKFLOW.read_text(encoding="utf-8")
    blob = "\n".join(_run_blocks(text))
    problems: list[str] = []

    for step in gate_steps():
        if step.script_key not in text and step.script_key not in blob:
            problems.append(f"yml 缺少门禁：{step.label}（应含 {step.script_key!r}）")

    for step in acceptance_steps():
        # 验收须经 run_acceptance_step，且点名脚本
        if "run_acceptance_step.py" not in text:
            problems.append("yml 验收步须使用 scripts/run_acceptance_step.py")
            break
        short = step.script_key.replace("scripts/", "").replace(".py", "")
        if short not in text and step.script_key not in text:
            problems.append(f"yml 缺少验收：{short}")

    # yml 里出现的 scripts/check_*.py / acceptance_*.py 不得超出清单
    found_checks = set(re.findall(r"scripts/(check_[a-z0-9_]+\.py)", text))
    allowed_checks = {s.script_key.replace("scripts/", "") for s in gate_steps()
                      if s.script_key.startswith("scripts/check_")}
    # 验收 skip 汇总属 post 步，不在 gate 清单
    allowed_checks.add("check_acceptance_skips.py")
    # ruff 不是 check_ 脚本
    extra = sorted(found_checks - allowed_checks)
    if extra:
        problems.append(f"yml 含清单外门禁脚本：{extra}")

    # 只认脚本名 / 参数位上的 acceptance_*，忽略 check_acceptance_skips 等辅助名
    found_acc = set(re.findall(r"run_acceptance_step\.py\s+(acceptance_[a-z0-9_]+)", text))
    found_acc |= set(re.findall(r"scripts/(acceptance_[a-z0-9_]+)\.py", text))
    allowed_acc = set(ACCEPTANCE)
    stray = sorted(found_acc - allowed_acc)
    if stray:
        problems.append(f"yml 含清单外验收名：{stray}")

    if "check_architecture_hygiene" not in text:
        problems.append("yml 必须包含 check_architecture_hygiene")
    if "check_ci_workflow" not in text:
        problems.append("yml 必须包含 check_ci_workflow（自举）")
    if "check_acceptance_skips" not in text:
        problems.append("yml 必须包含 check_acceptance_skips（skip 白名单汇总）")
    if "ACC_SKIP_FILE" not in text:
        problems.append("yml 必须设置 ACC_SKIP_FILE（验收 skip 汇总文件）")
    if "constraints.txt" not in text:
        problems.append("yml 安装须使用 constraints.txt")

    if problems:
        print("CI 工作流与 ci_steps 不一致：")
        for p in problems:
            print(f"  [FAIL] {p}")
        print("修法：改 .github/workflows/ci.yml 或 scripts/ci_steps.py，使两边同源。")
        return 1
    print(f"✅ CI 工作流与清单一致（门禁 {len(gate_steps())}、验收 {len(ACCEPTANCE)}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
