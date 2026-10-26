# 工程标准

本文件是模块结构、单一职责与资产归属的强制规范。实现与本文件冲突时，以本文件为判断依据；调整结构前先更新本文件与门禁。

## 1. 强制等级

| 等级 | 含义 |
|---|---|
| MUST | 不变量；违反即阻塞合并 |
| SHOULD | 默认做法；偏离需在评审中给出可验证理由 |
| MAY | 可选；同一模块内保持一致 |

## 2. 模块结构

### 2.1 分层

依赖方向固定为：

```text
entry → shell → capabilities → mechanisms → core
```

`agent/app.py` 是装配根，不属于五层；只有它可以同时引用五层并登记进程级服务。任何层不得运行期导入 `app.py` 或 `entry/`。

### 2.2 模块归属

| 路径 | 职责 | 不承担 |
|---|---|---|
| `agent/core/` | 模块链、宿主循环、端口、事件契约、会话事实契约 | provider、插件、UI、具体工具 |
| `agent/core/modules/` | 单步模块：输入、队列输入、压缩、模型、工具 | 服务装配、HTTP、插件加载 |
| `agent/mechanisms/providers/base.py` | `ModelProvider` 协议与 `ModelRequestError` | 具体网关请求、UI |
| `agent/mechanisms/providers/sse.py` | SSE 拆帧、流总超时、关闭诊断 | provider 请求体、业务消息 |
| `agent/mechanisms/providers/` | 兼容协议与原生协议的请求、流解析 | Echo、路由、装配 |
| `agent/mechanisms/providers/echo.py` | 无网络假模型 | 真实网关、路由 |
| `agent/mechanisms/providers/missing.py` | 缺少可用模型时的占位 | 真实网关、路由 |
| `agent/mechanisms/providers/debug.py` | 共享调试开关 | 请求转换、流解析 |
| `agent/mechanisms/providers/tool_schema.py` | 工具 schema 转换 | provider 装配、路由 |
| `agent/mechanisms/provider_registry.py` | 唯一具体 provider 装配点 | 路由规则、请求转换 |
| `agent/mechanisms/provider_router.py` | 按模型条目选择 provider | 具体 provider 实现 |
| `agent/mechanisms/context/rounds.py` | `Round`、`ContextChunk`、轮与工具链边界 | 布局、摘要、存储 |
| `agent/mechanisms/context/tokens.py` | token 估算与推理裁剪 | 装配、来源、策略 |
| `agent/mechanisms/context/layout.py` | 分段布局、压缩区间、渲染统计 | 来源注册、压缩器状态 |
| `agent/mechanisms/context/sources.py` | `ContextSources`、插件段与来源元数据 | 管线装配、provider |
| `agent/mechanisms/context/contract.py` | 压缩器依赖的窄接口 | 管线内部状态 |
| `agent/mechanisms/context/pipeline.py` | 三拼接装、分段装配 | 摘要生成、HTTP、插件加载 |
| `agent/mechanisms/compaction/compactor.py` | 压缩触发、覆盖前缀与摘要接入 | 管线内部函数、UI |
| `agent/mechanisms/quality/` | 写盘门控、检查、待确认状态 | 工具实现、HTTP |
| `agent/mechanisms/session_store.py` | 事实日志读写、seq、原子追加/回滚；行编解码、加密、锁分离在同包模块 | 会话展示、UI 字段 |
| `agent/capabilities/registry.py` | 工具注册表与工具协议 | 具体工具、服务装配 |
| `agent/capabilities/builtin/` | 内置工具，每个文件一个工具域 | 任务协议、插件加载 |
| `agent/capabilities/tasks/` | 任务工具：run_type、todo、confirm、sleep、goal | 内核链、HTTP |
| `agent/capabilities/plugins.py` | 插件装载与 Host；PluginContext / 贡献账本分离在 `plugin_context.py` / `plugin_ledger.py` | 内核业务、具体插件名 |
| `agent/shell/web/server.py` | HTTP 服务装配与启动 | 路由分派、静态资源、SSE 帧 |
| `agent/shell/web/web_routes.py` | HTTP 动词与路径分派、请求体/错误出口 | 具体业务动作、经典页面实现 |
| `agent/shell/web/web_static.py` | 壳层静态资源、路径与协议常量 | 插件私有资产 |
| `agent/shell/web/web_classic.py` | 经典页面与经典 SSE | JSON API 业务 |
| `agent/shell/web/web_plugin.py` | 插件端点与插件资产转发 | 插件内部业务 |
| `agent/shell/web/web_api.py` | `WebShell` 入口与连接/运行态；业务动作按 mixin 分在 `web_chat.py` / `web_sessions.py` / `web_files.py` / `web_contributions.py` / `web_state.py` | 路由分派 |
| `agent/shell/session/runner.py` | 回合线程、取消、队列抽干、生命周期 | 队列/目标/提示/恢复实现 |
| `agent/shell/session/queue.py` | 队列领取、释放、补投 | 回合循环 |
| `agent/shell/session/goal.py` | 目标与自主续跑判定 | 运行线程 |
| `agent/shell/session/prompt.py` | 系统提示与运行态尾部 | 模型调用 |
| `agent/shell/session/resume.py` | 外部工具结果恢复 | 回合循环 |
| `agent/shell/session/heartbeat.py` | 运行态心跳 | 回合终态 |
| `agent/shell/classic_adapter/inbound.py` | 入站门面与 API 形状 | 历史折叠、布局、状态 |
| `agent/shell/classic_adapter/outbound.py` | 内核事件到经典事件的翻译门面；工具/回合事件分在 `outbound_tools.py` / `outbound_turns.py` | 业务状态、HTTP 分发 |
| `agent/shell/classic_adapter/history.py` | 历史折叠、附件、工具回显 | 布局、会话列表 |
| `agent/shell/classic_adapter/layout.py` | 经典上下文布局、覆盖、缩放 | 历史存储 |
| `agent/shell/classic_adapter/state.py` | 经典会话级状态 | 事实日志 |
| `agent/shell/classic_adapter/sessions.py` | 会话标题、日期分组 | 会话运行 |
| `agent/shell/classic_adapter/contract.py` | 经典事件与字段常量 | 业务实现 |
| `agent/shell/context_dump.py` | 只读上下文快照 | 模型请求 |
| `agent/entry/` | 进程入口：读配置、建 App、启动壳 | 业务实现 |
| `plugins/<name>/` | 插件自有工具、配置、UI、主题资产 | 内核层、壳层公共资产 |

### 2.3 单一职责

MUST：

1. 一个模块只有一个主要变更轴；模块名必须能说明它为什么存在。
2. 门面只做组合与形状转换；业务规则、状态机、压缩策略不得藏在门面里。
3. provider 具体实现之间不得互导；只有 `provider_registry.py` 可以导入具体实现。
4. `provider_router.py` 只能依赖 `providers/base.py`。
5. `ContextCompactor` 只能通过 `context/contract.py` 使用上下文能力，不得导入 `pipeline.py`、`layout.py`、`rounds.py`、`sources.py`、`tokens.py` 的内部实现。
6. SessionRunner 只编排；队列、目标、提示词、恢复、心跳分别由 `session/` 下的模块承担。
7. classic `inbound.py` 只做入站门面；历史、布局、状态、会话列表分别落在 `history.py`、`layout.py`、`state.py`、`sessions.py`。
8. 每个内置任务工具一个文件；共享异常与参数校验只放在 `tasks/common.py`。
9. HTTP 路由只做分派；静态资源、经典页面、插件端点归 `web_static.py`、`web_classic.py`、`web_plugin.py`，JSON 业务归 `web_api.py` 及其动作 mixin。
10. 单文件超过 800 行或单函数超过 80 行必须进入 `docs/complexity.md` 的登记与拆分计划；不得以注释豁免。

禁止：

```text
provider 具体实现互导
router 导入具体 provider
compactor 导入 context 内部实现
web_routes 执行业务逻辑
inbound 直接持有历史/布局/状态实现
同一职责在门面与子模块各实现一份
为旧导入路径保留再导出
```

### 2.4 契约与状态

- 控制流走返回值，业务数据走事件；模块不得共享可变业务状态。
- 每份可变状态只有一个权威持有者：进程级在 `AppContext`，会话级在 `LiveState`/`SessionContext`，回合计在 `ToolTurnContext`。
- 跨模块只通过既有端口、事件、注册表或窄接口访问；不得跨层导入私有名。
- 追加写必须整批原子；失败由同一重试队列负责，上层不得重复补偿。

## 3. 资产归属

资产必须归到能对其生命周期、失败行为与契约负责的模块。新增或移动资产前必须回答：为什么属于这里、其他模块为什么不能拥有、能否由既有字段派生、唯一注册点、是否有重复副本、缺失/卸载影响谁。

| 资产 | 权威归属 | 注册/加载点 | 约束 |
|---|---|---|---|
| 内核模块与端口 | `agent/core/` | `core/modules/__init__.py`、`core/engine_factory.py` | 不出现具体插件名、具体 provider |
| Provider 协议与实现 | `agent/mechanisms/providers/` | `provider_registry.py` | 具体实现不互导；router 只认 base |
| 模型选择规则 | `provider_router.py` | `app.py` 装配 | 不持有具体网关逻辑 |
| 上下文模型、布局、来源 | `agent/mechanisms/context/` | `app.py` 构建 `ContextPipeline` | 每模块单一变更轴 |
| 压缩策略与摘要接入 | `agent/mechanisms/compaction/` | `app.py` 构建压缩器工厂 | 只通过 `context/contract.py` |
| 工具协议与注册表 | `agent/capabilities/registry.py` | `app.py` 构建 `ToolRegistry` | 工具只能注册一次 |
| 内置工具 | `agent/capabilities/builtin/` | `app.py` 的 `build_plugins` 调用 | 工具参数/schema 归工具自身 |
| 任务工具与确认协议 | `agent/capabilities/tasks/` | `tasks.build_plugins` → `app.py` | 共享异常只放 `common.py` |
| 插件工具/端点/面板 | `plugins/<name>/` | `PluginHost` + `ContributionRegistry` | 插件私有资产不进壳层 |
| 插件开关与配置 | `plugins.ini`、插件 `plugin-config.ini` | `PluginHost`、设置页 API | 插件键归插件；宿主键归 `config.ini` |
| 宿主配置键/默认值 | `agent/config.py`、`config.ini` | 装配根读取 | 新增键必须同步 `.example` 与配置文档 |
| 模型目录 | `capabilities/model_catalog.py` + 多模型插件 | 插件运行时刷新 | 模型配置不由宿主页写凭据 |
| 事件名与事件载荷 | `agent/core/event_name.py`、`agent/core/events.py` | 模块 `ports.emit` | 未知事件跳过；字段变更须声明兼容 |
| 经典事件/字段投影 | `classic_adapter/contract.py` | `outbound*.py` / `inbound.py` | 适配层只做形状翻译 |
| HTTP 鉴权 | `shell/web/auth/`、`shell/web/web_auth.py` | `server.create_server` 注入 `AuthRuntime` | 密码/会话/Token/CSRF/策略归壳层；不进 core |
| HTTP 路由 | `shell/web/web_routes.py` | `web.py` 绑定 `_Handler` | 业务动作在 `web_api.py` 及动作 mixin |
| 经典页面/SSE | `shell/web/web_classic.py` | `_Handler` 混入 | 不复制 JSON API |
| 插件 HTTP 端点 | `shell/web/web_plugin.py` | `PluginHost.add_route` | 精确匹配，不做通配 |
| 壳层公共 UI/CSS/JS | `shell/web/web_assets/`、`shell/web/ui_bundle.py` | `ui_bundle` 内联清单 | 公共资产归壳层 |
| 插件 UI/主题/图标 | `plugins/<name>/ui/` | 插件 `add_panel`/`add_ctx_segment_style` | 用 `plugin_root`，不写死 `plugins/<name>` |
| 界面配置 | `web-ui-config.ini` | 壳层读取 | 非插件私有配置 |
| 会话事实 | `data/sessions/*.raw` | `mechanisms/session_store.py` | append-only；不得直接改写 |
| 运行态数据 | `data/{queues,mesh,plugin,session_state,recycle,logs,auth,auth2..auth9}` | 对应 mechanisms/shell 持有者 | 只经各自服务访问；不得复制权威状态 |
| 规则资产 | `rules/*.md` | `rules` 插件，经 `ContextSources` 注入 | 用户/项目规则归插件，不进壳层 |
| 技能资产 | `skills/**` | `skills` 插件，经 `ContextSources` 注入 | 技能正文归技能库，不进内核 |
| 工具目录 | `catalog/tools.json` | `scripts/gen_catalog.py` 生成，`check_catalog.py` 校验 | 生成物；不得手改 |
| 标题/工作区 | `data/titles/`、`data/workspace/` | 壳层/存储各归属 | 不进源码树；路径按 data root |
| 运行态登记 | `mechanisms/live_state.py`、`mesh.py`、`run_registry.py` | 装配根 | 单一权威；不得双份缓存 |
| 测试 | `tests/` | unittest 发现 | 不得写入 `data/`；用临时数据根 |
| 生成文档 | `docs/complexity.md`、`docs/unit-tests.md` | 生成器 + `--check` | 必须由门禁重生成比对 |
| 临时证据 | `data/temp/` | 人工/验收 | 不进入源码或发布包 |

### 3.1 资产所有权规则

- 同一资产只能有一个权威副本；缓存只能由权威源派生并可失效。
- 配置键、事件字段、工具参数、API 字段必须由归属模块定义；调用方不得自行拼字符串。
- 新增模型工具必须同时提供参数 schema、注册点、失败测试；不得只加 handler。
- 新增前端资产必须在 `ui_bundle` 清单或插件贡献中登记；孤儿文件不得留在仓库。
- 新增静态资源必须说明加载路径、缓存策略、缺失时行为。
- 插件资产不得放进 `agent/shell/web/web_assets/`；壳层公共资产不得放进插件目录。
- 测试夹具、截图、上下文导出、缓存和备份不得进入源码树或发布包。

## 4. 扩展路径

| 新增能力 | 只应新增/修改 |
|---|---|
| Provider | `providers/<name>.py` + `provider_registry.py` 装配；router 不改 |
| 上下文来源 | `context/sources.py` 的公开注册点 + 插件贡献；不改 pipeline 分支 |
| 压缩策略 | `context/contract.py` + `compaction/`；不改 model/tool |
| 内置工具 | `capabilities/builtin/<tool>.py` + 注册点；不改内核 |
| 任务工具 | `capabilities/tasks/<tool>.py` + `build_plugins`；不改 shell |
| 插件 | `plugins/<name>/` + `plugins.ini`；不改内核/壳层具体名字 |
| 壳层页面/API | `web_routes.py` 分派 + `web_api.py` 动作 mixin；不把业务塞进路由 |
| UI 资产 | 壳层公共资产走 `ui_bundle`；插件私有资产走插件贡献 |

## 5. 门禁

| 约束 | 门禁 |
|---|---|
| 层间方向、同层环 | `scripts/check_imports.py` |
| 跨层私有名、内核插件名、门控旁路 | `scripts/check_architecture_hygiene.py` |
| Provider 互导、router 具体依赖 | `scripts/check_architecture_hygiene.py` |
| 压缩器直依赖 context 内部 | `scripts/check_architecture_hygiene.py` |
| 静默吞错 | `scripts/check_silent_except.py` |
| 复杂度阈值/生成文档 | `scripts/check_complexity.py`、`gen_complexity_md.py` |
| 配置漂移 | `scripts/check_config_drift.py` |
| 测试文档一致 | `scripts/gen_unit_tests_md.py --check` |
| 资产/README 计数 | `scripts/check_readme.py` |
| 全量验收 | `python scripts/ci.py` |

新增约束必须同时补门禁与负向测试；无法机器判定的规则进入评审清单。

## 6. 变更规则

1. 先确定资产归属，再改代码。
2. 结构移动只改归属与导入，不夹带行为变化。
3. 改契约字段前先查生产者、消费者、持久化读取方与文档。
4. 删除旧入口时删除再导出、别名与兼容转发；不保留双份实现。
5. 新增模块必须补职责说明、测试与必要的复杂度/资产文档。
6. 修改后运行受影响测试、静态检查、架构与复杂度门禁；用户要求时运行全量 CI。
