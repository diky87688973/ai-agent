# 复杂度登记

> 阈值：单文件 > 800 行、单函数 > 80 行。
> 本文件由 `python scripts/gen_complexity_md.py` 生成；`scripts/check_complexity.py` 比对实际集合与本表。

## 超阈值文件

| 文件 | 行数 | 函数数 | 保留理由 |
|---|---|---|---|
| `agent/mechanisms/context_pipeline.py` | 1186 | 67 | 拼装、分段统计与缓存版本共用同一状态机；待拆 segments 与 cache 子模块。承担者：架构维护 |
| `agent/shell/classic_adapter/inbound.py` | 1060 | 46 | HTTP 事件投影与折叠规则同文件；折叠外移到 history_page 后净减。承担者：壳层维护 |
| `agent/mechanisms/session_store.py` | 936 | 39 | 事件日志读写、行索引与压缩同文件；待拆索引层。承担者：机制维护 |
| `agent/shell/web_api.py` | 924 | 40 | SSE 连接表、会话运行表、附件与设置读取同文件；待拆 sse 与 attachments。承担者：壳层维护 |
| `agent/app.py` | 829 | 36 | 装配顺序、会话生命周期与模型解析共用同一份状态；拆分要先抽 AppState。承担者：内核维护 |

## 超阈值函数

| 文件::函数 | 行数 | 保留理由 |
|---|---|---|
| `agent/app.py::build_app` | 291 | 装配顺序是依赖方向的唯一事实源，拆散会让同一条决定出现在多处 |
| `scripts/check_ui_js.py::main` | 162 | 扫描与报告同流程；待拆扫描/报告两段 |
| `scripts/acceptance_mvp3.py::main` | 159 | 验收脚本按线性步骤写，拆函数会切断断言与步骤的对应 |
| `agent/core/modules/model_mod.py::ModelModule.execute` | 154 | 模块执行四步同函数；待抽执行协议对象 |
| `agent/shell/classic_adapter/inbound.py::_history_items` | 152 | 历史投影边界条件集中一处；折叠外移后回收 |
| `agent/shell/web_routes.py::_Handler.do_GET` | 146 | 路由分派按前缀线性展开；待拆路由表 + 处理器 |
| `agent/mechanisms/session_store.py::SessionStore._write_rows` | 139 | 行写入与截断/刷新策略同函数；待拆写入器 |
| `agent/capabilities/builtin/geo_weather_tools.py::OpenMeteoWeatherTool._run_core` | 134 | 参数清洗、调用与错误映射同函数 |
| `scripts/inspect_compact.py::inspect` | 130 | 诊断脚本一次产出多组统计，拆开收益低 |
| `agent/core/session_log.py::SessionLog.derive_messages` | 127 | 消息派生规则集中；拆分风险高于收益 |
| `agent/capabilities/builtin/command_tools.py::_pump` | 121 | 输出泵与超时/编码处理同函数 |
| `agent/mechanisms/context_pipeline.py::layout_from_messages` | 121 | 布局统计与渲染同函数；待拆统计器 |
| `agent/shell/web_routes.py::_Handler.do_POST` | 111 | POST 分派与请求体校验线性展开；待拆路由表 |
| `scripts/acceptance_batch_e.py::Acceptance.scenario_2` | 108 | 验收脚本线性断言 |
| `scripts/check_silent_except.py::main` | 106 | 扫描与汇总同流程；待拆报告器 |
| `agent/mechanisms/quality/checks.py::check_write` | 104 | 检查项顺序即语义，拆开会让判定顺序变得可改 |
| `agent/core/host.py::Host.run_iter` | 101 | 单轮的四条终止路径集中，拆开会让终止语义分散 |
| `scripts/acceptance_batch_f.py::Acceptance.scenario_1` | 101 | 验收脚本线性断言 |
| `agent/app.py::App.session` | 100 | 会话生命周期与事件转发在同一生成器；待拆中间对象 |
| `agent/mechanisms/context_compactor.py::ContextCompactor.ensure_before_append` | 98 | 触发判定与执行同函数；待拆判定器 |
| `agent/mechanisms/quality/pipeline_bridge.py::build_pipeline_gate` | 97 | 门控对象图在一处，拆开需引入 builder 类型 |
| `agent/core/image_embed.py::strip_old_images` | 96 | 剥离游标推进与保留策略同函数 |
| `scripts/acceptance_web.py::Acceptance.scenario_5` | 96 | 验收脚本线性断言 |
| `agent/core/modules/tool_mod.py::ToolModule.execute` | 90 | 工具执行四步同函数；待抽协议对象 |
| `scripts/acceptance_batch_e.py::Acceptance.scenario_1` | 89 | 验收脚本线性断言 |
| `agent/core/tool_call.py::ToolPipeline.execute` | 88 | 调用管道顺序即语义，拆开会让确认与执行脱节 |
| `agent/capabilities/builtin/fs_tools.py::_plan_ops` | 83 | 路径规划与冲突检测同函数 |

## 采集范围

- 目录：`agent/`、`scripts/`
- 排除：`__pycache__/`、`retired/`
- 文件 144 个、函数 1517 个；超阈值文件 5 个、函数 27 个。
