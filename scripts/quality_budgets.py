# -*- coding: utf-8 -*-
"""质量预算与复杂度阈值（单一事实源）。

门禁与生成文档都从这里取数：阈值、存量预算、登记理由只写一份，
避免"脚本里一个数、文档里另一个数"。
"""
from __future__ import annotations

from typing import Dict

#: 同层跨模块私有导入存量：只降不升；新增门禁先锁存量再分批清理。
SAME_LAYER_PRIVATE_BUDGET = 0

# ── 验收 skip（X7）───────────────────────────────────────────────────────
#: 允许跳过的验收脚本数上限。与白名单分开写，白名单扩容不会自动放宽上限。
ACCEPTANCE_SKIP_BUDGET = 1

# ── 覆盖率（X5 / X6）─────────────────────────────────────────────────────
#: 顶层包 → 语句覆盖率下限（百分点）。只许上调；下调必须在 PR 里写原因并补测试。
#: 空表等于"没有下限"，`check_coverage.py` 会把它当未接入。
COVERAGE_FLOORS: Dict[str, float] = {
    "agent/core": 85,
    "agent/mechanisms": 80,
    "agent/capabilities": 75,
    "agent/shell": 70,
    "agent/entry": 60,
    # 桌面壳依赖 Windows / WebView2，Linux CI 只能覆盖无平台分支。
    "agent/gui": 25,
    "agent/update": 60,
    "agent/subagent": 85,
    "agent (top-level)": 90,
    "plugins": 60,
}

# ── 复杂度（R1）──────────────────────────────────────────────────────────
#: 单文件行数阈值
MAX_FILE_LINES = 800
#: 单函数行数阈值
MAX_FUNCTION_LINES = 80
#: 单文件函数个数阈值
MAX_FILE_FUNCTIONS = 40
