# -*- coding: utf-8 -*-
"""CI 步骤单一事实源（供 scripts/ci.py 与 check_ci_workflow 共用）。

GitHub Actions 逐步跑以便超时定位；本清单约束「跑哪些」不得与 yml 漂移。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Literal, Sequence

from quality_budgets import ACCEPTANCE_SKIP_BUDGET

Kind = Literal["gate", "unittest", "acceptance", "post"]

#: 验收脚本「本机跑不了」退出码（与 ci.py / run_acceptance_step 一致）
SKIPPED = 2

#: 允许 skip 的验收脚本白名单（仅缺凭据等预期跳过）。
#: 其它验收一旦 skip / fail → CI 失败。mvp3 需要显式启用真实模型验收，CI 默认跳过。
ALLOWED_ACCEPTANCE_SKIPS = frozenset({"acceptance_mvp3"})

#: 白名单长度上限（防名单膨胀时静默放宽）。与白名单分开设置：
#: 写成 `len(白名单)` 会让上限永远不可触发（X7）。
MAX_ACCEPTANCE_SKIPS = ACCEPTANCE_SKIP_BUDGET

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
        CiStep("架构约束", "gate", "scripts/check_architecture_hygiene.py",
               ["scripts/check_architecture_hygiene.py"], 3),
        CiStep("CI 工作流一致", "gate", "scripts/check_ci_workflow.py",
               ["scripts/check_ci_workflow.py"], 3),
        CiStep("配置一致性", "gate", "scripts/check_config_drift.py",
               ["scripts/check_config_drift.py"], 3),
        CiStep("单测文档一致", "gate", "scripts/gen_unit_tests_md.py --check",
               ["scripts/gen_unit_tests_md.py", "--check"], 5),
        CiStep("静态检查", "gate", "ruff check",
               ["-m", "ruff", "check", "agent", "tests", "scripts"], 5),
        CiStep("Python 下限", "gate", "scripts/check_python_floor.py",
               ["scripts/check_python_floor.py"], 3),
        CiStep("UI JS 自检", "gate", "scripts/check_ui_js.py",
               ["scripts/check_ui_js.py"], 3),
        CiStep("静默异常", "gate", "scripts/check_silent_except.py",
               ["scripts/check_silent_except.py"], 5),
        CiStep("README 一致性", "gate", "scripts/check_readme.py",
               ["scripts/check_readme.py"], 3),
        CiStep("确认文案无歧义", "gate", "scripts/check_confirm_wording.py",
               ["scripts/check_confirm_wording.py"], 3),
        CiStep("注释文案", "gate", "scripts/check_comment_style.py",
               ["scripts/check_comment_style.py"], 5),
        CiStep("注册表一致性", "gate", "scripts/check_catalog.py",
               ["scripts/check_catalog.py"], 3),
        CiStep("复杂度登记", "gate", "scripts/check_complexity.py",
               ["scripts/check_complexity.py"], 5),
        CiStep("复杂度文档一致", "gate", "scripts/gen_complexity_md.py --check",
               ["scripts/gen_complexity_md.py", "--check"], 5),
        CiStep("适用性登记", "gate", "scripts/check_applicability.py",
               ["scripts/check_applicability.py"], 3),
        # K4：并发争用单独一步，开 `-X dev`（等价 PYTHONDEVMODE=1）让
        # ResourceWarning / 线程未回收等问题暴露出来，而不是被普通单测吞掉。
        CiStep("并发争用", "gate", "tests.test_concurrency",
               ["-X", "dev", "-m", "unittest", "tests.test_concurrency"], 3),
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
        steps.append(
            CiStep(
                "分包覆盖率",
                "post",
                "scripts/check_coverage.py",
                ["scripts/check_coverage.py"],
                3,
            )
        )
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
    # 先比预算再验白名单：白名单扩容时预算仍是硬约束，上限不会被同步放宽
    if len(uniq) > MAX_ACCEPTANCE_SKIPS:
        problems.append(
            f"验收 skip 数 {len(uniq)} > 上限 {MAX_ACCEPTANCE_SKIPS}"
        )
    stray = [n for n in uniq if n not in ALLOWED_ACCEPTANCE_SKIPS]
    if stray:
        problems.append(
            f"非预期 skip（仅允许 {sorted(ALLOWED_ACCEPTANCE_SKIPS)}）：{stray}"
        )
    return problems
