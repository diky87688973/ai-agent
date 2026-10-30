# 插件 2.0：完整注册树与插口清单

> 替换协议与 contract_version 见 [plugin-system-arbitrary-replacement.zh.md](plugin-system-arbitrary-replacement.zh.md)。

## 标记

```text
[S]    当前注册表里已经存在的 slot，允许绑定
[S+]   目标设计中的 slot，代码尚未完成 replace
[N]    命名空间，只承载子路径，不是插口
[I]    原子实现，不暴露、不注册、不可替换
```

原则：

```text
S 节点必须可替换
N 节点没有实现，不能绑定
I 节点不存在于插口表
```

当前 `backend/*` 和 `web-ui/*` 的 `S` 节点已经注册，但只支持新增，尚未支持 `replace`；该能力由 `plugin-system-arbitrary-replacement.zh.md` 定义。

## 完整路径树

```text
app [N]
│
├─ host [N]
│  ├─ bootstrap [S+]
│  ├─ composition [S+]
│  ├─ lifecycle [I]
│  └─ services [N]
│     ├─ registry [S+]
│     ├─ pipeline [S+]
│     ├─ provider [S+]
│     ├─ model_catalog [S+]
│     ├─ store [S+]
│     ├─ event_bus [S+]
│     ├─ plugin_host [S+]
│     ├─ plugin_events [S+]
│     ├─ context_sources [S+]
│     ├─ prompt_tail [S+]
│     ├─ prompt_sections [S+]
│     ├─ context_hooks [S+]
│     ├─ conversation_queue [S+]
│     ├─ session_contexts [S+]
│     ├─ live_state [S+]
│     ├─ mesh [S+]
│     ├─ session_factory [S+]
│     ├─ compactor_factory [S+]
│     ├─ error_log [S+]
│     ├─ background_tasks [S+]
│     ├─ update [S+]
│     ├─ subagents [S+]
│     ├─ wake_scheduler [S+]
│     ├─ runner [S+]
│     └─ classic_adapter [S+]
│
├─ kernel [N]
│  ├─ modules [N]
│  │  ├─ compaction [N]
│  │  │  ├─ build-context [S+]
│  │  │  ├─ summarize [S+]
│  │  │  └─ policy [S+]
│  │  ├─ context [N]
│  │  │  ├─ assembly [S+]
│  │  │  └─ other [I]
│  │  ├─ prompt [N]
│  │  │  ├─ assemble [S+]
│  │  │  └─ render [I]
│  │  ├─ tools [S]
│  │  │  ├─ pipeline [S+]
│  │  │  └─ executor [S+]
│  │  ├─ models [N]
│  │  │  ├─ router [S+]
│  │  │  ├─ catalog [S+]
│  │  │  └─ stream [I]
│  │  ├─ events [N]
│  │  │  ├─ bus [S+]
│  │  │  └─ dispatch [I]
│  │  ├─ chain [I]
│  │  ├─ engine [I]
│  │  ├─ engine_factory [I]
│  │  ├─ host [I]
│  │  ├─ image_embed [I]
│  │  ├─ input_attachments [I]
│  │  ├─ model_call [I]
│  │  ├─ mode_marker [I]
│  │  ├─ module [I]
│  │  ├─ outcome [I]
│  │  ├─ pass_lifecycle [I]
│  │  ├─ ports [I]
│  │  ├─ session_context [I]
│  │  ├─ session_log [I]
│  │  ├─ session_scope [I]
│  │  ├─ stderr [I]
│  │  ├─ tool_call [I]
│  │  ├─ session [N]
│  │  │  └─ append [I]
│  │  ├─ background_tasks [I]
│  │  ├─ command_safety [I]
│  │  ├─ conversation_queue [I]
│  │  ├─ error_log [I]
│  │  ├─ executors [I]
│  │  ├─ file_safety [I]
│  │  ├─ live_state [I]
│  │  ├─ mesh [I]
│  │  ├─ prompt_sections [I]
│  │  ├─ prompt_tail [I]
│  │  ├─ provider_registry [I]
│  │  ├─ provider_router [I]
│  │  ├─ run_registry [I]
│  │  ├─ session_crypto [I]
│  │  ├─ session_lines [I]
│  │  ├─ session_locking [I]
│  │  ├─ session_store [I]
│  │  ├─ session_title [I]
│  │  └─ wake_scheduler [I]
│  │
│  └─ providers [N]
│     ├─ model.gateway/<id> [S+]
│     ├─ session.store/<id> [S+]
│     ├─ tool.executor/<id> [S+]
│     ├─ context.builder/<id> [S+]
│     ├─ http.provider/<id> [S+]
│     └─ ui.renderer/<id> [S+]
│
├─ gui [N]
│  ├─ bootstrap [S+]
│  ├─ launcher [S+]
│  └─ lifecycle [I]
│
├─ shell [N]
│  ├─ http [N]
│  │  ├─ routes [N]
│  │  │  ├─ chat/send [S+]
│  │  │  ├─ chat/stop [S+]
│  │  │  ├─ chat/history [S+]
│  │  │  ├─ chat/sessions [S+]
│  │  │  ├─ chat/attachment [S+]
│  │  │  ├─ chat/queue [S+]
│  │  │  ├─ chat/ui-state [S+]
│  │  │  ├─ chat/user-confirm [S+]
│  │  │  ├─ chat/title [S+]
│  │  │  ├─ chat/autonomous [S+]
│  │  │  ├─ chat/command-input [S+]
│  │  │  ├─ chat/goal [S+]
│  │  │  ├─ settings [S+]
│  │  │  ├─ settings/plugins [S+]
│  │  │  ├─ settings/plugin-file [S+]
│  │  │  ├─ ui/catalog [S+]
│  │  │  ├─ plugins/loaded [S+]
│  │  │  ├─ tool-labels [S+]
│  │  │  ├─ plugin/<plugin>/<path> [S+]
│  │  │  ├─ fs/list [S+]
│  │  │  ├─ fs/read [S+]
│  │  │  ├─ dir-browse [S+]
│  │  │  ├─ media [S+]
│  │  │  ├─ usage-accumulator [S+]
│  │  │  ├─ reasoning-effort [S+]
│  │  │  ├─ events/stream [S+]
│  │  │  ├─ backend/catalog [S+]
│  │  │  ├─ update/status [S+]
│  │  │  ├─ update/logs [S+]
│  │  │  ├─ subagents [S+]
│  │  │  ├─ subagents/history [S+]
│  │  │  ├─ subagents/send [S+]
│  │  │  ├─ background/tasks/create [S+]
│  │  │  ├─ background/tasks/cancel [S+]
│  │  │  ├─ background/tasks/<id> [S+]
│  │  │  ├─ assets/<path> [S+]
│  │  │  ├─ workspace/<path> [S+]
│  │  │  ├─ health [S+]
│  │  │  └─ favicon.ico [S+]
│  │  ├─ auth [I]
│  │  ├─ session [I]
│  │  └─ static [I]
│  ├─ server [I]
│  ├─ web-api [I]
│  ├─ web-chat [I]
│  ├─ web-classic [I]
│  ├─ web-plugin [I]
│  ├─ web-files [I]
│  ├─ ui-bundle [I]
│  └─ web-routes [I]
│
│  └─ web-ui [S]
│     ├─ nav [S]
│     │  └─ buttons [S]
│     │     ├─ settings [S]
│     │     ├─ update [S]
│     │     └─ style [S]
│     ├─ chat [S]
│     │  ├─ messages [S]
│     │  │  ├─ user_msg [S+]
│     │  │  ├─ ai_msg [S+]
│     │  │  └─ tools [S]
│     │  │     ├─ skill [S]
│     │  │     └─ diff [S+]
│     │  └─ actions [N]
│     │     ├─ settings.open [S+]
│     │     ├─ theme.toggle [S+]
│     │     ├─ auto_update.check [S+]
│     │     ├─ panel.open_file [S+]
│     │     ├─ knowledge.open [S+]
│     │     ├─ visual.toggle [S+]
│     │     ├─ input.mode [S+]
│     │     ├─ input.thinking [S+]
│     │     ├─ input.goal [S+]
│     │     ├─ input.send [S+]
│     │     └─ input.stop [S+]
│     ├─ input [S]
│     │  ├─ textarea [I]
│     │  ├─ buttons [S]
│     │  │  ├─ image_btn [S]
│     │  │  ├─ mode_btn [S]
│     │  │  ├─ thinking_btn [S]
│     │  │  ├─ kb_btn [S]
│     │  │  ├─ model_switch_btn [S]
│     │  │  └─ visual_btn [S]
│     │  └─ right-buttons [S]
│     │     ├─ goal_btn [S]
│     │     ├─ send_btn [S]
│     │     └─ stop_btn [S]
│     ├─ left-panel [S]
│     │  ├─ sessions [S]
│     │  │  ├─ new [S+]
│     │  │  └─ list [S+]
│     │  └─ context_usage [S]
│     │     ├─ kb [S]
│     │     ├─ rules [S]
│     │     └─ skills [S]
│     ├─ right-panel [S]
│     │  ├─ steps [S]
│     │  ├─ open_file [S]
│     │  └─ kb [S]
│     ├─ runtime [S]
│     │  ├─ left-panel [S]
│     │  │  ├─ inbox [S]
│     │  │  └─ ai_speak [S]
│     │  └─ right-panel [S]
│     │     ├─ background_task [S]
│     │     └─ subagent [S]
│     └─ settings [S]
│
├─ backend [N]
│  ├─ tools [S]
│  │  ├─ <tool> [S]
│  │  │  ├─ executor [S]
│  │  │  └─ post-write [S]
│  │  ├─ subagents/visibility [S]
│  │  │  └─ <plugin> [S]
│  │  └─ pipeline [S+]
│  │     ├─ pre-gates [N]
│  │     │  └─ <plugin>/<gate> [S]
│  │     └─ post-observers [N]
│  │        └─ <plugin>/<observer> [S]
│  ├─ context [N]
│  │  ├─ sources [S]
│  │  │  └─ <plugin>/<source> [S]
│  │  ├─ assembly-hooks [S]
│  │  │  └─ <plugin>/<hook> [S]
│  │  └─ usage-segments [S]
│  │     └─ <plugin>/<segment> [S]
│  ├─ prompt [N]
│  │  ├─ sections [S]
│  │  │  └─ <section>/<plugin> [S]
│  │  └─ mode-tails [S]
│  │     └─ <plugin>/<tail> [S]
│  ├─ events [N]
│  │  └─ subscriptions [S]
│  │     └─ <event>/<plugin> [S]
│  ├─ http [N]
│  │  └─ routes [S+]
│  │     └─ <route_id> [S]
│  ├─ models [N]
│  │  ├─ catalog [S]
│  │  │  └─ <plugin> [S]
│  │  ├─ providers [S]
│  │  │  └─ <provider> [S]
│  │  └─ routing [S]
│  │     └─ <route> [S]
│  └─ runtime [S]
│     └─ <plugin> [S]
│
├─ settings [S]
│  └─ <panel> [N]
│     └─ <item> [S]
│
└─ plugins [N]
   └─ <plugin> [N]
      ├─ manifest [I]
      ├─ config [I]
      ├─ assets [N]
      └─ registrations [S+]
```

## 允许暴露的 slot 汇总

| 类别 | slot | 状态 |
|---|---|---|
| 宿主 | `app/host/bootstrap`、`app/host/composition` | 目标 |
| 宿主 | `app/host/services/<service>` | 目标，25 个服务键 |
| 内核 | `app/kernel/modules/compaction/{build-context,summarize,policy}` | 目标 |
| 内核 | `app/kernel/modules/context/assembly`、`app/kernel/modules/prompt/assemble` | 目标 |
| 内核 | `app/kernel/modules/tools/{pipeline,executor}`、`models/{router,catalog}`、`events/bus` | 目标 |
| 内核 | `app/kernel/providers/{model.gateway,session.store,tool.executor,context.builder,http.provider,ui.renderer}/<id>` | 目标 |
| GUI | `app/gui/bootstrap`、`app/gui/launcher` | 目标 |
| 壳层 | `app/shell/http/routes/<route_id>` | 目标，当前路由表全部迁移 |
| 壳层 | `app/shell/web-ui/...` 的 17 个当前 slot | 当前 |
| 壳层 | `app/shell/web-ui/actions/<action_id>` | 目标，11 个当前动作 |
| 后端 | `app/backend/...` 的 23 个当前 slot | 当前 |
| 设置 | `app/settings/<panel>/<item>` | 当前 |
| 插件 | `app/plugins/<plugin>/registrations` | 目标 |

当前 slot 只支持新增；目标 slot 统一支持 `replace`、`wrap`、`extend`、`replace_subtree`。

## 当前已实现的 slot

当前实际注册的路径，不包含 `[S+]` 目标项。

### 后端路径

```text
backend/tools
backend/tools/<tool>
backend/tools/<tool>/executor
backend/tools/<tool>/post-write
backend/tools/subagents/visibility
backend/tools/subagents/visibility/<plugin>
backend/tools/pipeline/pre-gates
backend/tools/pipeline/pre-gates/<plugin>
backend/tools/pipeline/post-observers
backend/tools/pipeline/post-observers/<plugin>
backend/context/sources
backend/context/sources/<plugin>
backend/context/assembly-hooks
backend/context/assembly-hooks/<plugin>
backend/context/usage-segments
backend/context/usage-segments/<plugin>
backend/prompt/sections
backend/prompt/sections/<section>
backend/prompt/mode-tails
backend/events/subscriptions
backend/events/subscriptions/<event>
backend/http/routes
backend/models/catalog
backend/models/providers
backend/models/routing
backend/runtime
```

来源：[backend_paths.py](agent/capabilities/backend_paths.py#L8)。

### 前端 UI slot

```text
web-ui
web-ui/nav
web-ui/nav/buttons
web-ui/chat
web-ui/chat/messages
web-ui/chat/messages/tools
web-ui/input
web-ui/input/buttons
web-ui/input/right-buttons
web-ui/left-panel
web-ui/left-panel/sessions
web-ui/left-panel/context_usage
web-ui/right-panel
web-ui/runtime
web-ui/runtime/left-panel
web-ui/runtime/right-panel
web-ui/settings
```

来源：[web_ui/plugin.py](plugins/web_ui/plugin.py#L7)。

### 设置路径

```text
settings/<panel>
settings/<panel>/<item>
```

来源：[settings_registry.py](agent/capabilities/settings_registry.py#L100)。

### 当前 UI 条目

```text
web-ui/nav/buttons/settings                 base_settings
web-ui/nav/buttons/update                   auto_update
web-ui/nav/buttons/style                    theme_style
web-ui/right-panel/steps                    web_ui
web-ui/right-panel/open_file                web_ui
web-ui/right-panel/kb                       knowledge
web-ui/input/buttons/image_btn              web_ui
web-ui/input/buttons/mode_btn               web_ui
web-ui/input/buttons/thinking_btn           web_ui
web-ui/input/buttons/kb_btn                 knowledge
web-ui/input/buttons/model_switch_btn       multi_model
web-ui/input/buttons/visual_btn             visual_operator_2
web-ui/input/right-buttons/goal_btn         web_ui
web-ui/input/right-buttons/send_btn         web_ui
web-ui/input/right-buttons/stop_btn         web_ui
web-ui/left-panel/context_usage/skills      skills
web-ui/left-panel/context_usage/rules       rules
web-ui/left-panel/context_usage/kb          knowledge
web-ui/chat/messages/tools/skill            skills
web-ui/runtime/left-panel/ai_speak          ai_speak
web-ui/runtime/left-panel/inbox             web_ui
web-ui/runtime/right-panel/background_task  web_ui
web-ui/runtime/right-panel/subagent         web_ui
```

### PluginContext API

```text
register_tool
add_executor
set_subagent_tools
subscribe
add_context_source
add_context_assembly_hook
add_mode_tail
add_prompt_section
add_pre_gate
add_post_observer
add_route
add_settings_panel
add_settings_item
add_ui_slot
add_ui_item
add_model_catalog
set_runtime
```

来源：[plugin_context.py](agent/capabilities/plugin_context.py#L100)。

## 允许暴露但要新增的 slot

### 宿主

```text
app/host/bootstrap
app/host/composition
app/host/services/<service>         25 个服务键全部
```

### 内核

```text
app/kernel/modules/compaction/build-context
app/kernel/modules/compaction/summarize
app/kernel/modules/compaction/policy
app/kernel/modules/context/assembly
app/kernel/modules/prompt/assemble
app/kernel/modules/tools/pipeline
app/kernel/modules/tools/executor
app/kernel/modules/models/router
app/kernel/modules/models/catalog
app/kernel/modules/events/bus
app/kernel/providers/model.gateway/<id>
app/kernel/providers/session.store/<id>
app/kernel/providers/tool.executor/<id>
app/kernel/providers/context.builder/<id>
app/kernel/providers/http.provider/<id>
app/kernel/providers/ui.renderer/<id>
```

### GUI

```text
app/gui/bootstrap
app/gui/launcher
```

### 壳层 HTTP 与前端动作

```text
app/shell/http/routes/<route_id>
app/shell/web-ui/actions/<action_id>
```

`<route_id>` 与 `<action_id>` 的当前集合见上方路径树。

## 不暴露的原子实现

这些节点只存在于实现内部，不进入路径注册表：

```text
app/kernel/chain
app/kernel/engine
app/kernel/engine_factory
app/kernel/host
app/kernel/image_embed
app/kernel/input_attachments
app/kernel/model_call
app/kernel/mode_marker
app/kernel/module
app/kernel/outcome
app/kernel/pass_lifecycle
app/kernel/ports
app/kernel/session_context
app/kernel/session_log
app/kernel/session_scope
app/kernel/stderr
app/kernel/tool_call

app/kernel/modules/compaction/compactor     内部压缩循环
app/kernel/modules/context/other            解析、分组、token 估算
app/kernel/modules/tools/validate           参数校验与安全检查
app/kernel/modules/tools/commit             写盘提交协议
app/kernel/modules/session/append           追加写入与锁定
app/kernel/modules/events/dispatch          事件分发顺序
app/kernel/modules/models/stream            流式响应解析
app/kernel/modules/prompt/render            提示词模板渲染

app/shell/http/auth                         鉴权、会话、CSRF
app/shell/http/session                      会话读写边界
app/shell/http/static                       静态资源与缓存
app/shell/web-ui/input/textarea             输入框内部
app/shell/web-ui/render/*                   diff/markdown/工具卡内部渲染
app/shell/web-ui/dom/*                      DOM 生命周期
app/shell/web-ui/scripts/*                  脚本加载器
app/gui/lifecycle                           进程生命周期

app/plugins/<plugin>/manifest               身份元数据
app/plugins/<plugin>/config                 插件配置
app/plugins/<plugin>/assets                 插件资源目录
```

原子实现可以被其所属 slot 调用，但不单独绑定。替换 slot 时，可以整体替换 slot 内部的原子实现；不能从外部直接改原子链。

## 当前实现与目标的差距

```text
当前 registry:
  只支持新增
  重复路径直接拒绝
  没有 replace/wrap/extend
  没有优先级链
  没有卸载回退
  backend/http routes 不是树节点
  UI action 不是路径
  host services 不在路径树
  GUI 没有路径
  kernel module 没有路径

目标 registry:
  每个 S 节点可 replace
  replace_subtree / wrap / extend
  priority + conflict + rollback
  contract_version
  解析快照
  host/kernel/gui/shell 全部投影为路径
```

当前 `S` 节点已可被消费，但消费方仍直接调用默认实现；迁移时必须先改消费方从路径树解析，否则 `replace` 只会改注册表，不会改行为。

## 统计

```text
当前后端路径 slot        23 条
当前 UI slot             17 条
当前 UI 条目             23 条
PluginContext 注册 API   17 个
宿主服务目标 slot        25 个
目标 kernel slot         10 个（另 provider 6 个）
目标 GUI slot            2 个
目标 HTTP route slot     当前路由表全部迁移
目标 action slot         11 个
```

数字以本文件列出的路径为准；新增路径必须同时更新本文件、目标契约和验收测试。
