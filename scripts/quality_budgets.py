# -*- coding: utf-8 -*-
"""质量预算与复杂度登记（单一事实源）。

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

#: 单文件函数数超阈值 → 保留理由。实际集合必须与这里双向一致。
FILE_FUNCTION_COMPLEXITY: Dict[str, str] = {}

#: 超阈值文件 → 保留理由（拆分计划或承担者）。实际集合必须与这里双向一致。
FILE_COMPLEXITY: Dict[str, str] = {}

#: 超阈值函数 → 保留理由。键是 `相对路径::限定名`（含类名，避免同名方法覆盖）。
FUNCTION_COMPLEXITY: Dict[str, str] = {
    "agent/app.py::build_app": "装配顺序是依赖方向的唯一事实源，拆散会让同一条决定出现在多处",
    "agent/app.py::App.session": "会话生命周期与事件转发在同一生成器；待拆中间对象",
    "scripts/acceptance_mvp3.py::main": "验收脚本按线性步骤写，拆函数会切断断言与步骤的对应",
    "agent/shell/classic_adapter/history.py::history_items": "历史投影边界条件集中一处；待拆事件类型",
    "scripts/check_ui_js.py::main": "扫描与报告同流程；待拆扫描/报告两段",
    "agent/core/modules/model_mod.py::ModelModule.execute": "模块执行四步同函数；待抽执行协议对象",
    "agent/shell/web_routes.py::Handler.do_GET": "路由分派按前缀线性展开；待拆路由表 + 处理器",
    "agent/mechanisms/session_store.py::SessionStore._write_rows": "行写入与截断/刷新策略同函数；待拆写入器",
    "agent/capabilities/builtin/geo_weather_tools.py::OpenMeteoWeatherTool._run_core": "参数清洗、调用与错误映射同函数",
    "scripts/inspect_compact.py::inspect": "诊断脚本一次产出多组统计，拆开收益低",
    "agent/core/session_log.py::SessionLog.derive_messages": "消息派生规则集中；拆分风险高于收益",
    "agent/capabilities/builtin/command_tools.py::_pump": "输出泵与超时/编码处理同函数",
    "agent/mechanisms/context/layout.py::layout_from_messages": "布局统计与渲染同函数；待拆统计器",
    "agent/shell/web_routes.py::Handler.do_POST": "POST 分派与请求体校验线性展开；待拆路由表",
    "scripts/acceptance_batch_e.py::Acceptance.scenario_2": "验收脚本线性断言",
    "agent/mechanisms/quality/checks.py::check_write": "检查项顺序即语义，拆开会让判定顺序变得可改",
    "scripts/acceptance_batch_f.py::Acceptance.scenario_1": "验收脚本线性断言",
    "agent/mechanisms/compaction/compactor.py::ContextCompactor.ensure_before_append": "触发判定与执行同函数；待拆判定器",
    "agent/core/host.py::Host.run_iter": "单轮的四条终止路径集中，拆开会让终止语义分散",
    "agent/mechanisms/quality/pipeline_bridge.py::build_pipeline_gate": "门控对象图在一处，拆开需引入 builder 类型",
    "scripts/acceptance_web.py::Acceptance.scenario_5": "验收脚本线性断言",
    "agent/core/image_embed.py::strip_old_images": "剥离游标推进与保留策略同函数",
    "agent/core/modules/tool_mod.py::ToolModule.execute": "工具执行四步同函数；待抽协议对象",
    "scripts/acceptance_batch_e.py::Acceptance.scenario_1": "验收脚本线性断言",
    "agent/core/tool_call.py::ToolPipeline.execute": "调用管道顺序即语义，拆开会让确认与执行脱节",
    "agent/capabilities/builtin/fs_tools.py::_plan_ops": "路径规划与冲突检测同函数",
    "plugins/visual_operator/tools/_capture.py::capture_payload": (
        "取图、窗口选择、渲染与回执共享同一组中间状态；拆分需引入截图事务上下文对象。"
        "承担者：插件维护"
    ),
}
