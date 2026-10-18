# 架构

本文说明代码如何组织、一次请求如何流经系统。

## 五层结构

依赖只允许由内向外单向：反向引用与循环依赖由 `scripts/check_imports.py` 扫描 AST 强制，违规即失败。

```
entry  →  shell  →  capabilities  →  mechanisms  →  core
```

| 层 | 目录 | 职责 | 依赖 |
|---|---|---|---|
| L0 内核 | `agent/core/` | 模块链、宿主循环、事件与数据契约、端口 | 无 |
| L1 机制 | `agent/mechanisms/` | 模型调用、上下文管线与压缩、写盘门控、会话存储、协作网格 | core |
| L2 能力 | `agent/capabilities/` | 工具注册表、内置工具、插件加载 | core, mechanisms |
| L3 壳层 | `agent/shell/` | HTTP + SSE 服务、界面打包、系统提示词、经典界面适配 | 全部下层 |
| L4 入口 | `agent/entry/` | 进程入口：读配置 → 建 `App` → 交给壳跑 | 全部下层 |

`agent/app.py` 是**装配根**，不属于任何一层。它是唯一同时引用五层的文件，负责构建 `AppContext` 并登记服务。
装配根与入口层都不允许被任何层运行期导入（`if TYPE_CHECKING:` 的纯注解除外）；
这条规则和"层间单向"由同一道门禁检查，`--scc` 可打印全包强连通分量用于审计。

## 双轨：决策链与事件总线

系统同时跑两条互不干扰的轨道。

| 轨道 | 机制 | 职责 | 参与控制流 |
|---|---|---|---|
| 决策链 | 模块链 + 有序拦截器，带返回值 | 数据搬运、门控、拦截、改写 | 是 |
| 事件总线 | 广播订阅 | 界面推送、日志、统计、进度 | 否，纯通知 |

`EventBus` 在 `core/event_bus.py`。门控住在决策链上：订阅者无法阻止主流程，执行顺序也不确定。

## 模块链

内核的行为面就是一个方法：

```python
class ModuleBase:
    def execute(self, ports: Ports) -> Outcome: ...
```

宿主反复跑整条链，直到没有任何模块要求续行。链上五个模块按固定顺序执行：

```
输入 → 收件箱 → 压缩 → 模型 → 工具
```

| 模块 | 作用 |
|---|---|
| `InputModule` | 把本轮的新用户输入认领成事实；**无输入时不发任何事件** |
| `InboxModule` | 把别的会话投进来的消息收进上下文；排在压缩之前，让压缩看得见它们 |
| `CompressModule` | 拼入前做预算检查，超阈值则压缩历史；压缩失败一律放行，不阻断回合 |
| `ModelModule` | 按事实末端判定该不该跑；跑就发请求、消费流式增量，落成 `model_message` |
| `ToolModule` | 执行模型要求但尚无结果的工具调用；执行过就要求续行 |

全部实现在 `core/modules.py`，由 `build_default_chain()` 组装。

`chain.py` 负责"一趟怎么跑"（`run_chain_iter` / `run_chain`），`host.py` 负责"跑到什么时候停"和回合边界。

### 控制流与数据流分离

- **控制流走返回值**：`Outcome` 只带控制信号（`ok` / `next` / `halt` / `suspend` / `stopped`），不带数据。
- **数据流走事件**：正文、用量、进度经 `ports.emit(...)` 发出。

这个分离让模块之间没有共享可变状态：模块决定"接下来干什么"，数据由事件通道流出去。

## 端口

模块不能直接碰文件、网络、会话存储或工具实现，只能调 `Ports` 上声明过的接口。

```python
class Ports:
    model_port: ModelPort   # 发起模型请求
    tool_port: ToolPort     # 执行工具
    log: SessionLog         # 事实日志的只读视图
    def emit(type_, **data) # 产出一件事实：先入日志，再出事件
    def canceled()          # 宿主是否已请求停止
    def extras(key, default=None)
```

请求契约是 `LogicalRequest`：与具体模型无关的 `messages` / `tools` / `system` / `effort` / `model` / `conversation_id`。provider 负责把它翻译成某个网关的 wire 格式。

`Ports` 上可用的入口：`model_port`、`tool_port`、`log`（事实只读视图）、`conversation_id`、`emit`、`canceled`、`extras`。模块需要的一切外部能力都从这几个口走。

## 事件协议

模块的生命周期事件形状统一为 `<域>_started` → 结果 → `<域>_ended`。

| 模块 | 开始 | 结果 | 结束 |
|---|---|---|---|
| 输入 | `input_started` | `input_claimed` | `input_ended` |
| 压缩 | `compress_started` | `context_compacted` | `compress_ended` |
| 模型 | `llm_started` | `llm_done` / `llm_failed` | `llm_ended` |
| 工具 | `tool_started` | `tool_done` / `tool_failed` / `tool_canceled` / `tool_suspended` | `tool_ended` |

两条纪律：

- **`tool_ended` 不带结果**。结果在先发的 `tool_done` 里，消费方要按 `call_id` 回查。
- **`_ended` 是判定边界**。判断"这次调用结束没有"统一看它。

事件名常量集中在 `core/event_name.py`（25 个），事件信封在 `core/events.py`。

## 状态的三级生命周期

可变状态按生命周期分三级存放。混放会导致跨会话串状态这类难查的缺陷。

| 级别 | 容器 | 内容 | 生命周期 |
|---|---|---|---|
| 进程级 | `AppContext`（`core/context.py`） | 工具注册表、执行管道、模型 provider、会话存储、事件总线、插件宿主、协作网格、各类工厂 | 进程全程 |
| 会话级 | `SessionContext` / `SessionContexts`（`core/session_context.py`） | 写盘门控、实时状态、收件队列 | 按 `conversation_id` 懒创建 |
| 回合级 | `ToolTurnContext`（`core/context.py`） | 单回合内的工具轮次状态 | 单回合 |

会话注册表 `SessionContexts` 是跨端访问的**唯一入口**：`sessions.resolve()`，或按 id 取 `sessions.get(cid)`。工具与管道钩子在执行期内经 `core/session_scope.py` 的 `current_session_id()` 取当前会话，不得把会话态塞进全局单例，也不得跨会话直读。

## 事实与投影

会话记录是 **append-only 的事实流**：每发生一件事就追加一条，不改写已有行。

- 落盘实现在 `mechanisms/session_store.py`（每会话一个 `.raw`，JSONL）。
- 界面看到的 SSE 流是这份事实的**实时投影**，不是另一份真相。
- 上下文管线要"历史"时，从事实流 **derive**，而不是另存一份。

由此得到一条结构性保证：**模型可见 ⟺ 已记录**。过滤、清理、格式化必须发生在落盘之前，落盘后的事实不可改写。

事件格式向前兼容：读取时**未知事件类型一律跳过**，所以旧会话在新代码下照常可读。

## 装配

`app.py` 的 `build_app()` 按顺序做四件事：

1. 读配置（`agent/config.py`），决定 provider、数据根、Skills 库与插件清单。
2. 建工具注册表与门控，装配工具管道、事件总线、插件宿主；清单里的插件在此加载。
3. 装配上下文管线工厂与压缩器工厂。
4. 构建 `AppContext`，按逆序即清理序登记全部进程级服务；返回 `App`，其属性是 `context.get(name)` 的快捷方式。

`build_shell_app()` 在 `agent/entry/web.py` 里包一层：按配置建真实 provider 与会话存储，再交给 `build_app()`。
装配根（`app.py`）与入口层（`entry/`）是最上面两层：任何层都不得运行期导入它们，
`entry/` 也不得被任何层导入。`python -m agent.entry.web` / `agent.entry.cli` / `agent.entry.headless` 是三个进程入口。

## 反苟且清单

下列纪律必须保持为零例外（由 `scripts/check_architecture_hygiene.py` 与单测共同钉住）：

- `ToolCallScope` 在执行期填入 `app` 与 `session`；工具读 `current_context().session.gate`，不另开全局门控旁路（无 `gate=` / `_fallback_gate` / `gate_resolver`）。
- 无 `session_contexts` 时 `gate_for` 报错；`build_pipeline_gate` 必填 `registry` 与 `sessions`，预览只认工具 `needs_preview`（无 `preview_tools=`）。
- 系统提示词写类名单由 `preview_write_tools_line(registry)` 从 `needs_preview` 动态生成，不手写内置枚举长串；生成失败必须报错，禁止静默空串。
- 写路径键只认工具声明的 `write_path_keys`（经注册表查找），无进程全局键表、无默认猜 `path`；落盘后是否强制重读认 `needs_reread`。
- 写盘门控只认 `agent.mechanisms.quality`；禁止 `quality_gate` 兼容模块或 `mechanisms.quality_gate` 回流。
- `agent/core` 与 `agent/mechanisms` 不出现具体插件名（含 `skill_manage` 与 `plugins/` 目录名）。
- 插件 `add_panel` / `add_route` / `add_action` 等贡献一律经 disposer 记账，卸载逆序清理。
- 外部 `path=` 插件的资产根走 `plugin_root`，不写死 `plugins/<名>`。
- 仅为段色登记时用 `add_ctx_segment_style`，不挂空面板。
- 壳层经典 JS 与 `prompts.py` 不含 `skill_manage`（工具名只在插件侧）。
- TTS 等插件不向界面承诺内核未提供的能力。
- 禁止跨层私有导入（`from agent.X import _priv`）；同层私有导入允许。
- `SERVICE_CLASSIC_ADAPTER` 只住在壳层键表，不进 `core`。
- 不保留死的 `changeset_mod_ids` 引用。
- 会话关闭时释放对应 `SessionContext` 桶。

## 延伸阅读

| 主题 | 文档 |
|---|---|
| 术语 | [glossary.md](glossary.md) |
| 内核模块链与事件 | [subsystems/core.md](subsystems/core.md) |
| 上下文管理 | [subsystems/context.md](subsystems/context.md) |
| 模型调用 | [subsystems/llm.md](subsystems/llm.md) |
| 工具与插件 | [subsystems/tools.md](subsystems/tools.md)、[subsystems/plugins.md](subsystems/plugins.md) |
| Skills | [subsystems/skills.md](subsystems/skills.md) |
| 会话存储与协作 | [subsystems/session.md](subsystems/session.md) |
| HTTP 服务与界面 | [subsystems/shell.md](subsystems/shell.md) |
| 配置项 | [guide/config.md](guide/config.md) |
| 写盘门控现状与优化 | [write-gate.md](write-gate.md) |
