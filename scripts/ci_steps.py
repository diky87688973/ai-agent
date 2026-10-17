# -*- coding: utf-8 -*-
"""CI 步骤单一事实源（供 scripts/ci.py 与 check_ci_workflow 共用）。

GitHub Actions 逐步跑以便超时定位；本清单约束「跑哪些」不得与 yml 漂移。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Sequence

Kind = Literal["gate", "unittest", "acceptance", "post"]

#: 验收脚本「本机跑不了」退出码（与 ci.py / run_acceptance_step 一致）
SKIPPED = 2

#: 允许 skip 的验收脚本白名单（仅缺凭据等**预期**跳过）。
#: 其它验收一旦 skip / fail → CI 失败。mvp3 依赖真模型 config.ini，CI 无密钥故在名单内。
ALLOWED_ACCEPTANCE_SKIPS = frozenset({"acceptance_mvp3"})

#: 白名单长度上限（防名单膨胀时静默放宽）；与 ALLOWED 同步维护
MAX_ACCEPTANCE_SKIPS = len(ALLOWED_ACCEPTANCE_SKIPS)

ACCEPTANCE = [
    "acceptance_batch_a",
    "acceptance_batch_b",
    "acceptance_batch_c",
    "acceptance_batch_d",
    "acceptance_batch_e",
    "acceptance_batch_f",
    "acceptance_mvp2",
    "acceptance_mvp3",
    "acceptance_phase3",
    "acceptance_web",
]


@dataclass(frozen=True)
class CiStep:
    """一步校验：label 给人看，script_key 给 yml 对账，cmd 给本地跑。"""

    label: str
    kind: Kind
    #: 出现在 yml `run:` 里的稳定子串（脚本路径或 ruff 调用）
    script_key: str
    #: 相对工程根的命令参数（不含 python 解释器）；空则仅用于清单对账
    argv: Sequence[str]
    timeout_minutes: int = 3


def gate_steps() -> List[CiStep]:
    """门禁步（顺序固定）。"""
    return [
        CiStep("依赖方向", "gate", "scripts/check_imports.py",
               ["scripts/check_imports.py"], 3),
        CiStep("架构洁癖", "gate", "scripts/check_architecture_hygiene.py",
               ["scripts/check_architecture_hygiene.py"], 3),
        CiStep("CI 工作流一致", "gate", "scripts/check_ci_workflow.py",
               ["scripts/check_ci_workflow.py"], 3),
        CiStep("静态检查", "gate", "ruff check",
               ["-m", "ruff", "check", "agent", "tests", "scripts"], 5),
        CiStep("Python 下限", "gate", "scripts/check_python_floor.py",
               ["scripts/check_python_floor.py"], 3),
        CiStep("UI JS 自检", "gate", "scripts/check_ui_js.py",
               ["scripts/check_ui_js.py"], 3),
        CiStep("静默异常", "gate", "scripts/check_silent_except.py",
               ["scripts/check_silent_except.py", "--all-strict"], 5),
        CiStep("README 一致性", "gate", "scripts/check_readme.py",
               ["scripts/check_readme.py"], 3),
        CiStep("确认文案无歧义", "gate", "scripts/check_confirm_wording.py",
               ["scripts/check_confirm_wording.py"], 3),
        CiStep("注释文案", "gate", "scripts/check_comment_style.py",
               ["scripts/check_comment_style.py"], 5),
        CiStep("注册表一致性", "gate", "scripts/check_catalog.py",
               ["scripts/check_catalog.py"], 3),
    ]


def acceptance_steps() -> List[CiStep]:
    """验收步。"""
    out: List[CiStep] = []
    for name in ACCEPTANCE:
        # mvp3 / web 略慢
        timeout = 5 if name in ("acceptance_mvp3",) else 6 if name == "acceptance_web" else 4
        out.append(
            CiStep(
                name.replace("_", " "),
                "acceptance",
                f"scripts/{name}.py",
                ["scripts/run_acceptance_step.py", name],
                timeout,
            )
        )
    return out


def catalog(fast: bool = False) -> List[CiStep]:
    """完整清单（本地 ci.py 跑的顺序）。"""
    steps = list(gate_steps())
    steps.append(
        CiStep(
            "单元测试",
            "unittest",
            "unittest discover",
            ["-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-t", "tests"],
            15,
        )
    )
    if not fast:
        steps.extend(acceptance_steps())
    return steps


def acceptance_skip_problems(names: Sequence[str]) -> List[str]:
    """校验 skip 名单：非白名单、超上限、名单外膨胀 → 问题文案列表（空=通过）。"""
    # 去 BOM / 空白，去重保序
    uniq: list[str] = []
    seen: set[str] = set()
    for raw in names:
        n = str(raw or "").replace("\ufeff", "").strip()
        if not n or n in seen:
            continue
        seen.add(n)
        uniq.append(n)
    problems: list[str] = []
    stray = [n for n in uniq if n not in ALLOWED_ACCEPTANCE_SKIPS]
    if stray:
        problems.append(
            f"非预期 skip（仅允许 {sorted(ALLOWED_ACCEPTANCE_SKIPS)}）：{stray}"
        )
    if len(uniq) > MAX_ACCEPTANCE_SKIPS:
        problems.append(
            f"验收 skip 数 {len(uniq)} > 上限 {MAX_ACCEPTANCE_SKIPS}"
        )
    return problems
