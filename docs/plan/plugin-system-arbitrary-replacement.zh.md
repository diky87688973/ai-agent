# 插件 2.0：全路径替换设计

> 只替换暴露的 slot；原子逻辑链不注册为插口。

状态：目标契约。当前实现是这份契约的迁移起点，不是最终形态。

## 核心原则

插件 2.0 不再把插件能力分成“可扩展”和“只读”两类。

```text
项目结构 = 路径命名空间树 + slot 绑定表
路径 = 地址，不等于插口
slot = 有契约、有默认实现、允许替换的节点
invariant = 原子逻辑链，不暴露、不注册、不参与绑定
默认绑定 = 宿主提供的初始实现
插件绑定 = 对默认实现或已有实现的替换、包装、增强
```

规则：

- 只有 `slot` 是暴露的注册点；`slot` 必须允许被替换或改写。
- 不允许出现“能注册但不能替换”的 slot。
- 原子逻辑链不作为 slot 暴露；它只能存在于某个 slot 实现的内部。破坏它没有意义，因为它根本不在插口表里。
- 纯分组节点是 `namespace`：只负责路径结构，没有默认实现，不可绑定，也不是注册点。
- 路径树本身负责维护 `slot → 实现` 的映射；消费方只从 slot 取当前实现，不直接 import 某个默认实现。
- 路径身份稳定，实现可以替换；替换不能改变路径身份、父子关系和动作契约。

## 节点分类

```text
namespace    纯结构节点：只承载子路径，没有实现，不可绑定
slot         有契约、有默认实现、可替换的注册点
invariant    原子逻辑链：不暴露、不注册、不参与替换
```

判定规则：

- 有对外行为、需要被替换 → 声明为 `slot`，写契约与默认绑定。
- 只有分组意义、没有行为 → `namespace`，不能注册实现。
- 内部原子逻辑、替换会破坏不变量 → `invariant`，不进入路径注册表。

“不可替换就不暴露”只针对 `slot`。`invariant` 不是“已暴露但禁止替换”，而是从一开始就不存在这个插口。

## 全量路径树

路径统一使用 `app/` 根：

```text
app
├─ host
│  ├─ bootstrap
│  ├─ composition
│  ├─ lifecycle
│  └─ services/<service>
│
├─ kernel
│  ├─ modules/<module>
│  │  ├─ build
│  │  ├─ process
│  │  └─ ...
│  ├─ modules/compaction/build-context
│  ├─ modules/compaction/summarize
│  ├─ modules/compaction/policy
│  ├─ context/assembly
│  ├─ prompts/assemble
│  ├─ tools/pipeline
│  ├─ models/router
│  └─ providers/<provider_id>
│
├─ gui
│  ├─ bootstrap
│  └─ launcher
│
├─ shell
│  ├─ http/routes/<route_id>
│  ├─ http/auth
│  ├─ http/session
│  └─ web-ui
│     ├─ nav/buttons/<id>
│     ├─ chat/messages/<id>
│     ├─ chat/messages/tools/<tool_name>
│     ├─ input/buttons/<id>
│     ├─ input/right-buttons/<id>
│     ├─ left-panel/<id>
│     ├─ right-panel/<id>
│     ├─ runtime/left-panel/<id>
│     ├─ runtime/right-panel/<id>
│     └─ actions/<id>
│
├─ backend
│  ├─ tools/<tool_name>
│  ├─ tools/<tool_name>/executor
│  ├─ tools/<tool_name>/post-write
│  ├─ tools/pipeline/pre-gates/<id>
│  ├─ tools/pipeline/post-observers/<id>
│  ├─ context/sources/<id>
│  ├─ context/assembly-hooks/<id>
│  ├─ context/usage-segments/<id>
│  ├─ prompt/sections/<id>
│  ├─ prompt/mode-tails/<id>
│  ├─ events/subscriptions/<id>
│  ├─ http/routes/<route_id>
│  ├─ models/catalog/<id>
│  ├─ models/providers/<id>
│  ├─ models/routing/<id>
│  └─ runtime/<id>
│
├─ plugins
│  └─ <plugin>
│     ├─ manifest
│     ├─ config
│     ├─ assets
│     └─ registrations
│
└─ settings
   └─ <panel>/<item>
```

当前内核模块根（每个根下的阶段才注册为路径）：

```text
agent/core:
  chain context engine engine_factory error_report events event_bus
  event_name host image_embed input_attachments model_call mode_marker
  module outcome pass_lifecycle ports session_context session_log
  session_scope stderr tool_call

agent/mechanisms:
  background_tasks command_safety conversation_queue error_log executors
  file_safety live_state mesh prompt_sections prompt_tail provider_registry
  provider_router run_registry session_crypto session_lines session_locking
  session_store session_title wake_scheduler compaction
```

当前 GUI 根：

```text
agent/gui/bootstrap.py
agent/gui/launcher.py
```

当前壳层根：

```text
agent/shell/web/server.py
agent/shell/web/web_routes.py
agent/shell/web/web_api.py
agent/shell/web/web_chat.py
agent/shell/web/web_classic.py
agent/shell/web/web_static.py
agent/shell/web/web_plugin.py
agent/shell/web/web_files.py
agent/shell/web/web_auth.py
agent/shell/web/ui_bundle.py
```

这些模块的每个可替换阶段都投影为 `app/...` 下的路径；没有投影的模块只是内部实现，不作为插口暴露。

树中每个 `slot` 节点都有契约：

```text
path
kind
contract            输入、输出、异常、副作用
children_policy     none / fixed / keyed / extension / tree
default_binding    宿主默认实现
bindings            当前候选实现
active_binding      当前解析到的实现
owner               当前实现归属
```

`children_policy` 描述子路径，不限制当前节点自身的替换。父节点和子节点是两层独立契约：替换父节点不会删除子节点绑定，除非显式使用 `replace_subtree`。

## 当前注册点清单

### 分类总表

| 层 | 当前注册面 | 数量 | 来源 |
|---|---|---|---|
| 宿主 | ServiceContext 服务键、插件宿主、组合根 | 25 个服务键 | `agent/core/context.py`、`agent/shell/service_keys.py` |
| 内核 | `app/kernel/modules/<module>/<stage>` 目标投影；当前压缩器直接调用 | 模块根见下；当前无路径 | `agent/core/`、`agent/mechanisms/` |
| 后端 | `backend/*` PathRegistry slot | 23 个 slot | `agent/capabilities/backend_paths.py` |
| 后端 | `PluginContext.add_*` 注册方法 | 16 个方法 | `agent/capabilities/plugin_context.py` |
| 后端 | 设置面板/条目 | `settings/<panel>/<item>` | `agent/capabilities/settings_registry.py` |
| 宿主 | 壳层 HTTP 路由 | 当前条件分支，目标为 route 路径 | `agent/shell/web/web_routes.py` |
| 前端 | UI PathRegistry slot | 17 个 slot | `plugins/web_ui/plugin.py` |
| 前端 | UI 条目 + action | 23 个当前条目 | UI catalog / 插件 `add_ui_item` |
| GUI | bootstrap / launcher | 2 个目标路径；当前无注册树 | `agent/gui/` |
| 插件 | 插件根、manifest、config、assets | 每插件一组 | `plugins/<name>` |

### 宿主与内核

当前宿主服务注册点来自 `agent/core/context.py` 的服务键，以及壳层服务键：

```text
registry                工具注册表
pipeline                工具执行管道
provider                模型提供者路由
model_catalog           模型目录
store                   会话存储
event_bus               事件总线
plugin_host             插件宿主
plugin_events           插件事件出口
context_sources         上下文注入源
prompt_tail             请求尾部
prompt_sections         系统提示词章节
context_hooks           完整上下文拼装钩子
conversation_queue      会话队列
session_contexts        会话上下文注册表
live_state              实时状态
mesh                    协作网格
session_factory         上下文管线工厂
compactor_factory       压缩器工厂
error_log               错误日志
background_tasks        后台任务
update                  更新控制器
subagents               子智能体管理器
wake_scheduler          唤醒调度器
runner                  会话运行器
classic_adapter         经典界面适配器
```

当前这些服务由组合根直接写入 ServiceContext，不在 PathRegistry 中，因此还不具备插件替换能力。目标契约要求每一个服务键都有对应的 `app/host/services/<service>` 路径。

当前 GUI 入口：

```text
agent/gui/bootstrap.py
agent/gui/launcher.py
```

目标路径：

```text
app/gui/bootstrap
app/gui/launcher
```

当前内核模块位于 `agent/core/`、`agent/mechanisms/`；压缩模块位于 `agent/mechanisms/compaction/`。目标契约将模块的每个可替换阶段投影为路径：

```text
app/kernel/modules/<module>/<stage>
```

压缩模块的示例：

```text
app/kernel/modules/compaction/build-context
app/kernel/modules/compaction/summarize
app/kernel/modules/compaction/policy
```

`build-context` 的默认实现是当前 `ContextCompactor` 的构建上下文阶段；替换绑定后，压缩模块在调用时从插口树解析新的 `build-context`，不再直接调用默认类。

### 后端路径插口

当前 `agent/capabilities/backend_paths.py` 已声明 22 个路径：

```text
backend/tools                                  keyed
backend/tools/<tool>                           fixed: executor, post-write
backend/tools/subagents/visibility             keyed
backend/tools/pipeline/pre-gates               keyed
backend/tools/pipeline/pre-gates/<plugin>      keyed
backend/tools/pipeline/post-observers          keyed
backend/tools/pipeline/post-observers/<plugin> keyed
backend/context/sources                        keyed
backend/context/sources/<plugin>               keyed
backend/context/assembly-hooks                 keyed
backend/context/assembly-hooks/<plugin>        keyed
backend/context/usage-segments                 keyed
backend/context/usage-segments/<plugin>        keyed
backend/prompt/sections                        keyed
backend/prompt/sections/<section>              keyed
backend/prompt/mode-tails                      keyed
backend/events/subscriptions                   keyed
backend/events/subscriptions/<event>           keyed
backend/http/routes                            keyed
backend/models/catalog                         keyed
backend/models/providers                       keyed
backend/models/routing                         keyed
backend/runtime                                keyed
```

它们在目标树中的位置是 `app/backend/...`。当前实现只把这些路径当审计记录，消费方仍直接调用对象；替换必须改为从路径树解析。

### 前端路径插口

当前 `plugins/web_ui/plugin.py` 声明 16 个 UI 插口：

```text
web-ui                         fixed
web-ui/nav                     fixed
web-ui/nav/buttons             keyed
web-ui/chat                    fixed
web-ui/chat/messages           fixed
web-ui/chat/messages/tools     keyed
web-ui/input                   fixed
web-ui/input/buttons           keyed
web-ui/input/right-buttons     keyed
web-ui/left-panel              fixed
web-ui/left-panel/sessions     fixed
web-ui/left-panel/context_usage keyed
web-ui/right-panel             keyed
web-ui/runtime                 fixed
web-ui/runtime/left-panel      keyed
web-ui/runtime/right-panel     keyed
web-ui/settings                none
```

目标树中的位置是 `app/shell/web-ui/...`。

当前 UI 条目：

```text
web-ui/nav/buttons/settings                    base_settings
web-ui/nav/buttons/update                      auto_update
web-ui/nav/buttons/style                       theme_style
web-ui/right-panel/steps                       web_ui
web-ui/right-panel/open_file                   web_ui
web-ui/right-panel/kb                          knowledge
web-ui/input/buttons/image_btn                 web_ui
web-ui/input/buttons/mode_btn                  web_ui
web-ui/input/buttons/thinking_btn              web_ui
web-ui/input/buttons/kb_btn                    knowledge
web-ui/input/buttons/model_switch_btn          multi_model
web-ui/input/buttons/visual_btn                visual_operator_2
web-ui/input/right-buttons/goal_btn            web_ui
web-ui/input/right-buttons/send_btn            web_ui
web-ui/input/right-buttons/stop_btn            web_ui
web-ui/left-panel/context_usage/skills         skills
web-ui/left-panel/context_usage/rules          rules
web-ui/left-panel/context_usage/kb             knowledge
web-ui/chat/messages/tools/skill               skills
web-ui/runtime/left-panel/ai_speak             ai_speak
web-ui/runtime/left-panel/inbox                web_ui
web-ui/runtime/right-panel/background_task     web_ui
web-ui/runtime/right-panel/subagent            web_ui
```

当前这些条目都由 `add_ui_item` 注册，重复路径直接拒绝；没有 replace API。目标契约要求同名路径可以被新绑定替换，旧绑定作为回退链。

### PluginContext 注册方法

```text
register_tool               -> app/backend/tools/<tool>
add_executor                -> app/backend/tools/<tool>/executor
set_subagent_tools          -> app/backend/tools/subagents/visibility/<plugin>
subscribe                   -> app/backend/events/subscriptions/<event>/<id>
add_context_source          -> app/backend/context/sources/<id>
add_context_assembly_hook   -> app/backend/context/assembly-hooks/<id>
add_mode_tail               -> app/backend/prompt/mode-tails/<id>
add_prompt_section          -> app/backend/prompt/sections/<id>
add_pre_gate                -> app/backend/tools/pipeline/pre-gates/<id>
add_post_observer           -> app/backend/tools/pipeline/post-observers/<id>
add_route                   -> app/backend/http/routes/<route_id>
add_settings_panel          -> app/settings/<panel>
add_settings_item           -> app/settings/<panel>/<item>
add_ui_slot                 -> app/shell/web-ui/...
add_ui_item                 -> app/shell/web-ui/...
add_model_catalog           -> app/backend/models/catalog/<id>
set_runtime                 -> app/backend/runtime/<id>
```

### 宿主 HTTP 路由

当前壳层路由表包含：

```text
/api/update/*              /api/subagents/*
/api/backend/catalog       /api/ui/catalog
/api/settings*             /api/chat/queue
/api/events/stream         /api/usage-accumulator
/api/chat/attachment       /api/chat/history
/api/chat/sessions         /api/chat/ui-state
/api/fs/list               /api/fs/read
/api/plugins/loaded        /api/tool-labels
/api/plugin/*              /api/dir-browse
/api/reasoning-effort      /api/media
/workspace/*               /assets/*
/health                    /favicon.ico
/api/chat/send             /api/chat/user-confirm
/api/chat/title            /api/chat/autonomous
/api/chat/stop             /api/chat/command-input
/api/chat/goal             /api/chat/queue/*
/api/background/tasks/*    /api/subagents/send
```

当前这些路由由 `web_routes.py` 的条件分支直接分派，不是路径树节点。目标契约把每条路由变成：

```text
app/shell/http/routes/<route_id>
```

绑定字段：

```text
method
path
handler
auth_scope
status
```

路由路径身份不随 handler 替换而改变；替换后仍走同一路由入口。

### 前端动作

当前 UI catalog 的动作分发在 `ui-catalog.js` 中：

```text
settings.open
theme.toggle
auto_update.check
panel.open_file
knowledge.open
visual.toggle
input.mode
input.thinking
input.goal
input.send
input.stop
```

目标契约把动作也作为路径：

```text
app/shell/web-ui/actions/<action_id>
```

动作 owner 和 renderer owner 分离；UI 条目的 `action` 只引用路径，不直接写死函数名。

### 插件根

```text
app/plugins/<plugin>
```

子节点：

```text
app/plugins/<plugin>/manifest
app/plugins/<plugin>/config
app/plugins/<plugin>/assets
app/plugins/<plugin>/registrations
```

插件自身也是树节点；插件根允许替换、包装、子树替换。

## 替换协议

### 绑定

统一绑定入口：

```python
ctx.bind(
    path,
    implementation,
    *,
    mode="replace",     # replace / wrap / extend / replace_subtree
    priority=0,
    order=None,
    contract=None,
    requires=(),
    owner=None,
)
```

模式：

```text
replace          替换当前节点实现，保留子节点
replace_subtree  替换当前节点及子节点解析结果
wrap             包装当前实现，调用 base
extend           向集合节点追加一项，不删除默认项
```

现有 API 映射：

```text
add_ui_item(path, ..., replace=True)      -> bind(path, renderer, mode="replace")
add_route(..., replace=True)              -> bind(route_path, handler, mode="replace")
add_context_source(..., replace=True)     -> bind(source_path, fn, mode="replace")
add_settings_item(..., replace=True)      -> bind(settings_path, item, mode="replace")
```

没有 `replace=True` 时仍按新增处理；已有路径重复注册报错。`replace=True` 是显式替换，不静默覆盖。

### 解析

```text
resolve(path):
  1. 在路径树中定位节点
  2. 取该节点所有可用绑定
  3. 按 priority、order、注册时间排序
  4. 取最高优先级绑定
  5. 若是 wrap，递归解析 base
  6. 若无绑定，使用 default_binding
  7. 若 default 也没有，路径不存在，调用失败
```

约束：

- 同优先级同 order 的多个 replace 绑定必须报冲突，不能猜。
- `unbind` 移除当前绑定后，自动回退到下一个绑定或 default。
- 替换是事务：注册失败回滚所有已写入的绑定。
- 路径树快照必须可审计：路径、绑定 owner、模式、优先级、状态。
- 绑定必须声明 `contract_version`；与 path 当前契约不兼容时拒绝替换。
- 一次请求、一次渲染、一次压缩过程使用同一解析快照；树版本变化只影响下一轮。

### 父子节点

- 替换父节点默认不删除子节点；子节点继续按自己的绑定解析。
- 父节点可以声明 `children_policy=tree`，表示父实现负责子树的调用顺序。
- `replace_subtree` 才会让父绑定接管子节点解析；此时必须显式声明子路径白名单。
- 路径树不允许“未注册路径注入”；任何节点必须先在树中声明。

### 生命周期

```text
加载插件
→ 校验 manifest 的 replaces
→ 事务写入绑定
→ 解析当前实现
→ 通知消费者刷新
→ 运行期从路径树取实现

卸载插件
→ 撤销该 owner 的绑定
→ 逐路径回退到上一实现或 default
→ 通知消费者刷新
→ 清空缓存
```

前端和后端使用同一路径身份：后端绑定变化产生 catalog 版本；前端按版本重建对应节点，不重建整页。

## 关键场景

### 替换路由

```python
ctx.bind(
    "app/shell/http/routes/chat_send",
    handler,
    mode="replace",
    priority=100,
)
```

`app/shell/http/routes/chat_send` 的路径、URL 和 method 不变，只替换 handler。路由分发器不再直接调用 `web_chat.send`，而是从插口树解析 `chat_send` 的当前绑定。

### 替换导航按钮

```python
ctx.bind(
    "app/shell/web-ui/nav/buttons/style",
    renderer,
    mode="replace",
    priority=100,
)
```

`style` 路径 identity 不变；默认绑定是主题插件的按钮，替换后新插件接管渲染和动作。卸载后回退到主题插件的默认绑定。

### 替换 diff 工具渲染器

```python
ctx.bind(
    "app/shell/web-ui/chat/messages/tools/diff",
    DiffRenderer(),
    mode="replace",
    renderer_owner="my_plugin",
    priority=100,
)
```

路径 owner 仍是基础 WEB-UI；renderer owner 是新插件。工具消息壳从路径树取 `diff` 的当前 renderer，不直接 import `render/diff.js`。

### 替换压缩上下文实现

```python
ctx.bind(
    "app/kernel/modules/compaction/build-context",
    BuildContext(),
    mode="replace",
    priority=100,
)
```

压缩模块在每次需要构建上下文时调用：

```python
impl = slots.resolve("app/kernel/modules/compaction/build-context")
context = impl.build(messages, policy)
```

默认实现是当前压缩器逻辑；替换后压缩模块使用新实现，不需要改压缩器源码。

### 替换 GUI 启动

```python
ctx.bind(
    "app/gui/bootstrap",
    Bootstrap(),
    mode="replace",
    priority=100,
)
```

启动器只从 `app/gui/bootstrap` 取当前绑定。替换失败必须回滚到默认绑定，启动失败不能留下半初始化进程。

## 注册树管理

新增 `SlotRegistry` 作为唯一权威：

```text
register_slot(path, contract, children_policy, default_binding)
bind(path, binding)
resolve(path, context)
unbind(binding_id)
snapshot()
subscribe(path, listener)
```

数据模型：

```text
SlotNode
  path
  kind
  contract
  children_policy
  default_binding
  bindings[]
  active_binding
  version

Binding
  id
  path
  owner
  implementation
  mode
  priority
  order
  contract_version
  requires[]
  status
```

所有现有 Registry 都改为 `SlotRegistry` 的消费者：

- `ContributionRegistry` 退化为路由绑定适配器。
- `UiRegistry` 退化为 UI 绑定适配器。
- `SettingsRegistry` 退化为 settings 路径适配器。
- `PluginContext` 的 `add_*` 变成 `bind` 的语义化包装。
- ServiceContext 的服务键改成 `app/host/services/<service>` 的默认绑定。

## 迁移顺序

不按模块边界迁移，按“路径树成为唯一权威”的顺序迁移：

1. 建立 `SlotRegistry`、绑定事务、回退链、catalog 快照。
2. 把现有 backend/UI/settings 注册写入新树，保留现有 API 作为兼容包装。
3. 把消费方从直接 import/直接查旧 Registry 改为 `resolve(path)`。
4. 把宿主服务、HTTP 路由、GUI bootstrap/launcher 投影为路径。
5. 把默认实现改成默认绑定。
6. 删除旧 Registry 的重复状态，确保路径树是唯一权威。
7. 用替换测试证明每个插口可以替换、回滚、热更新。

迁移期间禁止：

```text
路径树和旧 Registry 长期双写
只给 UI 做替换，后端仍直接 import
替换只改显示，不改变消费方取实现的来源
未声明的路径注入
```

## 验收

必须覆盖：

```text
replace nav style          默认主题按钮被替换，卸载后恢复
replace diff renderer      工具消息使用新渲染器，卸载后恢复
replace route handler      同一 URL 命中新 handler，卸载后恢复
replace build-context      压缩模块调用新实现，卸载后恢复
replace gui bootstrap      启动使用新实现，失败回滚默认
invariant                   原子逻辑链没有被注册成 slot，插件无法替换
contract_version           契约版本不匹配时拒绝绑定
snapshot                    单次执行中不因热更新切换实现
replace_subtree            父节点替换后子节点按声明解析
priority / conflict        高优先级生效，同优先级冲突显式报错
wrap / extend              包装与追加不破坏默认实现
missing contract           契约不匹配拒绝绑定
transaction                绑定失败不留下半截状态
hot refresh                前端只重建受影响路径节点
```

通过标准不是“能注册新按钮”，而是：

```text
任意已暴露路径，都能在不改宿主源码的前提下替换实现
替换后可解析、可回退、可审计、可热更新
所有消费方只从路径树取实现
```
