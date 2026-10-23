# 复杂度登记

> 阈值：单文件 > 800 行、单函数 > 80 行、单文件 > 40 个函数。
> 本文件由 `python scripts/gen_complexity_md.py` 生成；`scripts/check_complexity.py` 比对实际集合与本表。

## 超阈值文件

| 文件 | 行数 | 函数数 | 保留理由 |
|---|---|---|---|
| （无） | - | - | - |

## 函数数超阈值文件

| 文件 | 函数数 | 保留理由 |
|---|---|---|
| （无） | - | - |

## 超阈值函数

| 文件::函数 | 行数 | 保留理由 |
|---|---|---|
| `agent/app.py::build_app` | 308 | 装配顺序是依赖方向的唯一事实源，拆散会让同一条决定出现在多处 |
| `plugins/visual_operator/tools/_capture.py::capture_payload` | 185 | 取图、窗口选择、渲染与回执共享同一组中间状态；拆分需引入截图事务上下文对象。承担者：插件维护 |
| `agent/shell/classic_adapter/history.py::history_items` | 164 | 历史投影边界条件集中一处；待拆事件类型 |
| `scripts/check_ui_js.py::main` | 163 | 扫描与报告同流程；待拆扫描/报告两段 |
| `agent/core/modules/model_mod.py::ModelModule.execute` | 161 | 模块执行四步同函数；待抽执行协议对象 |
| `scripts/acceptance_mvp3.py::main` | 156 | 验收脚本按线性步骤写，拆函数会切断断言与步骤的对应 |
| `agent/shell/web/web_routes.py::Handler.do_GET` | 151 | 路由分派按前缀线性展开；待拆路由表 + 处理器 |
| `agent/shell/web/web_routes.py::Handler.do_POST` | 141 | POST 分派与请求体校验线性展开；待拆路由表 |
| `agent/capabilities/builtin/geo_weather_tools.py::OpenMeteoWeatherTool._run_core` | 134 | 参数清洗、调用与错误映射同函数 |
| `scripts/inspect_compact.py::inspect` | 131 | 诊断脚本一次产出多组统计，拆开收益低 |
| `agent/mechanisms/session_store.py::SessionStore._write_rows` | 130 | 行写入与截断/刷新策略同函数；待拆写入器 |
| `agent/core/session_log.py::SessionLog.derive_messages` | 127 | 消息派生规则集中；拆分风险高于收益 |
| `agent/capabilities/builtin/command_tools.py::_pump` | 121 | 输出泵与超时/编码处理同函数 |
| `agent/mechanisms/context/layout.py::layout_from_messages` | 121 | 布局统计与渲染同函数；待拆统计器 |
| `agent/mechanisms/quality/checks.py::check_write` | 117 | 检查项顺序即语义，拆开会让判定顺序变得可改 |
| `scripts/acceptance_batch_e.py::Acceptance.scenario_2` | 108 | 验收脚本线性断言 |
| `agent/core/host.py::Host.run_iter` | 101 | 单轮的四条终止路径集中，拆开会让终止语义分散 |
| `agent/mechanisms/compaction/compactor.py::ContextCompactor.ensure_before_append` | 97 | 触发判定与执行同函数；待拆判定器 |
| `agent/mechanisms/quality/pipeline_bridge.py::build_pipeline_gate` | 97 | 门控对象图在一处，拆开需引入 builder 类型 |
| `scripts/acceptance_web.py::Acceptance.scenario_5` | 97 | 验收脚本线性断言 |
| `agent/core/image_embed.py::strip_old_images` | 96 | 剥离游标推进与保留策略同函数 |
| `agent/app.py::App.session` | 91 | 会话生命周期与事件转发在同一生成器；待拆中间对象 |
| `agent/core/modules/tool_mod.py::ToolModule.execute` | 90 | 工具执行四步同函数；待抽协议对象 |
| `scripts/acceptance_batch_e.py::Acceptance.scenario_1` | 89 | 验收脚本线性断言 |
| `agent/core/tool_call.py::ToolPipeline.execute` | 88 | 调用管道顺序即语义，拆开会让确认与执行脱节 |
| `agent/capabilities/builtin/fs_tools.py::_plan_ops` | 83 | 路径规划与冲突检测同函数 |

## 采集范围

- 目录：`agent/`、`scripts/`、`plugins/`
- 排除：`__pycache__/`、`retired/`
- 文件 252 个、函数 2109 个；超阈值文件 0 个、函数 26 个、函数数超阈值文件 0 个。
