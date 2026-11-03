# 插件 2.0 插口协议配置

状态：待审查。本文只定义协议、路径、依赖和配置，不包含运行时代码实现。

## 1. 协议约定

| 字段 | 含义 |
| --- | --- |
| `path` | 插口稳定身份；替换、依赖、排序都以它为准 |
| `kind` | `container` / `module` / `provider` / `tool` / `ui` / `route` / `event` / `setting` / `service` |
| `contract` | 返回类型：`text` / `messages` / `tool` / `json` / `ui` / `route` |
| `owner` | 默认实现归属；插件卸载时按 owner 回滚 |
| `implementation` | 默认实现引用，格式为 `module:function`；插件内为 `plugin:module:function` |
| `requires` | 依赖的插口路径；容器和提供者都必须显式列出 |
| `order` | 同层执行顺序；数字小的先执行，相同 order 按 path 排序 |
| `cache` | `stable` / `dynamic`；影响提示词缓存和每轮重算 |
| `phase` | `base` / `system` / `tail`；尾部注入必须带 `tail` 路径标记 |
| `exposed` | 是否允许替换默认实现 |
| `mode` | `replace` / `extend` / `wrap` / `disable` |

容器规则：

```text
children = slot_tree.children(container_path)
按 (order, path) 排序
text = child.implementation(conversation_id)
空文本跳过
```

不允许靠插件清单顺序、注册顺序或路径字典序决定业务顺序。

## 2. 全工程插口树

```text
app
├─ entry
│  ├─ cli
│  │  ├─ app-factory
│  │  └─ interactive
│  ├─ headless
│  │  ├─ app-factory
│  │  └─ runner
│  └─ web
│     ├─ app-factory
│     ├─ auth-cli
│     ├─ server
│     └─ tls
├─ config
│  └─ plugin-manifests
│     ├─ base
│     ├─ cli
│     ├─ headless
│     └─ web
├─ plugins
│  ├─ ai_cosplay
│  │  ├─ tools/ai_speek
│  │  ├─ ui/panel
│  │  ├─ prompt/tail/ai-speek
│  │  └─ routes / events / runtime
│  ├─ visual_operator_2
│  │  ├─ tools/vision_*
│  │  ├─ prompt/visual-frame-description
│  │  ├─ user-messages/visual-frame-images
│  │  ├─ ui/button
│  │  └─ runtime
│  ├─ skills
│  ├─ rules
│  ├─ knowledge
│  ├─ multi_model
│  ├─ theme_style
│  ├─ auto_update
│  └─ ai_writing
├─ tools
│  └─ <builtin-tool>
├─ runtime
│  ├─ kernel
│  │  └─ agent-loop
│  │     ├─ modules
│  │     │  ├─ input
│  │     │  ├─ queued-input
│  │     │  ├─ context
│  │     │  │  ├─ prompt
│  │     │  │  │  ├─ base-system
│  │     │  │  │  ├─ system-appends
│  │     │  │  │  ├─ system-messages
│  │     │  │  │  └─ tail
│  │     │  │  │     ├─ appends
│  │     │  │  │     │  ├─ run-mode
│  │     │  │  │     │  ├─ todo-list
│  │     │  │  │     │  ├─ ai-speek
│  │     │  │  │     │  └─ ai-writing
│  │     │  │  │     └─ user-messages
│  │     │  │  │        └─ visual-frame-images
│  │     │  │  └─ extract
│  │     │  ├─ compress
│  │     │  ├─ model
│  │     │  └─ tool
│  │     └─ ...
│  ├─ host
│  │  ├─ services
│  │  │  ├─ event-bus
│  │  │  ├─ error-log
│  │  │  ├─ live-state
│  │  │  ├─ queue
│  │  │  ├─ mesh
│  │  │  ├─ registry
│  │  │  ├─ background-tasks
│  │  │  ├─ context-sources
│  │  │  ├─ context-hooks
│  │  │  ├─ prompt-tail
│  │  │  ├─ prompt-sections
│  │  │  ├─ contributions
│  │  │  ├─ model-catalog
│  │  │  ├─ update
│  │  │  ├─ session-factory
│  │  │  ├─ compactor-factory
│  │  │  ├─ provider
│  │  │  ├─ contexts
│  │  │  ├─ pipeline
│  │  │  ├─ plugin-host
│  │  │  ├─ store
│  │  │  └─ subagents
│  │  ├─ boot
│  │  │  ├─ files
│  │  │  ├─ facade
│  │  │  └─ plugins
│  │  ├─ tools
│  │  │  ├─ <builtin-tool>
│  │  │  └─ <plugin-tool>
│  │  └─ models
│  │     └─ catalog
│  │        └─ <plugin-model>
├─ shell
│  ├─ web-ui
│  │  ├─ nav
│  │  ├─ composer
│  │  │  ├─ above
│  │  │  │  ├─ left
│  │  │  │  └─ right
│  │  │  └─ input
│  │  ├─ chat
│  │  │  └─ messages
│  │  │     └─ tools
│  │  ├─ context
│  │  │  └─ usage
│  │  ├─ sidebar
│  │  │  ├─ left
│  │  │  │  ├─ new-conversation
│  │  │  │  ├─ conversation-list
│  │  │  │  └─ usage
│  │  │  └─ right
│  │  │     └─ knowledge
│  │  ├─ runtime
│  │  └─ settings
│  ├─ cli
│  │  ├─ interactive
│  │  └─ headless
│  ├─ web
│  │  ├─ server
│  │  ├─ auth
│  │  └─ static
│  ├─ http
│  │  └─ routes
│  ├─ events
│  │  └─ subscriptions
│  └─ adapters
│     ├─ classic
│     ├─ plugin-events
│     ├─ runner
│     ├─ wake-scheduler
│     └─ finalizer
├─ auth
└─ settings
   ├─ model
   ├─ interface
   └─ plugins
```

`tail/appends` 和 `tail/user-messages` 都带 `tail` 路径标记，并且只能出现在请求尾部。

## 3. Kernel / Agent Loop

| path | kind | contract | requires | order | cache | exposed | implementation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `app/runtime/kernel/agent-loop` | module | `agent.loop` | — | 0 | stable | yes | `agent.runtime.kernel:agent_loop` |
| `app/runtime/kernel/agent-loop/modules` | container | `agent.modules` | `.../agent-loop` | 0 | stable | yes | `agent.runtime.kernel:modules` |
| `.../modules/input` | module | `agent.stage` | `.../modules` | 10 | dynamic | yes | `agent.core.modules:input` |
| `.../modules/queued-input` | module | `agent.stage` | `.../modules` | 20 | dynamic | yes | `agent.core.modules:queued_input` |
| `.../modules/context` | module | `agent.stage` | `.../modules` | 30 | dynamic | yes | `agent.core.modules:context` |
| `.../modules/compress` | module | `agent.stage` | `.../modules` | 40 | dynamic | yes | `agent.core.modules:compress` |
| `.../modules/model` | module | `agent.stage` | `.../modules` | 50 | dynamic | yes | `agent.core.modules:model` |
| `.../modules/tool` | module | `agent.stage` | `.../modules` | 60 | dynamic | yes | `agent.core.modules:tool` |

`context` 和 `compress` 拆开：`context` 负责组装，`compress` 负责提取和替换上下文。

## 4. Context / Prompt

### 4.1 基础与容器

| path | kind | contract | requires | order | cache | exposed | implementation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `.../modules/context/prompt` | container | `prompt.text` | `.../modules/context` | 0 | dynamic | yes | `agent.context.prompt:assemble` |
| `.../prompt/base-system` | provider | `prompt.text` | `.../prompt` | 0 | stable | yes | `agent.shell.prompts:base_system` |
| `.../prompt/system-appends` | container | `prompt.text` | `.../prompt/base-system` | 10 | stable | yes | `agent.context.prompt:system_appends` |
| `.../prompt/system-messages` | container | `messages` | `.../prompt/system-appends` | 20 | dynamic | yes | `agent.context.prompt:system_messages` |
| `.../prompt/tail` | container | `messages` | `.../prompt/system-messages` | 90 | dynamic | yes | `agent.context.prompt:tail` |
| `.../prompt/tail/appends` | container | `prompt.text` | `.../prompt/tail` | 10 | dynamic | yes | `agent.context.prompt:tail_appends` |
| `.../prompt/tail/user-messages` | container | `messages` | `.../prompt/tail` | 20 | dynamic | yes | `agent.context.prompt:tail_user_messages` |
| `.../modules/context/extract` | provider | `prompt.context` | `.../prompt` | 100 | dynamic | yes | `agent.context.compress:extract` |

### 4.2 system-appends 子插口

| path | kind | contract | requires | order | cache | exposed |
| --- | --- | --- | --- | --- | --- | --- |
| `.../system-appends/reply-language` | provider | `prompt.text` | `.../system-appends` | 10 | stable | yes |
| `.../system-appends/action-discipline` | provider | `prompt.text` | `.../system-appends` | 20 | stable | yes |
| `.../system-appends/resource-directory` | provider | `prompt.text` | `.../system-appends` | 30 | dynamic | yes |
| `.../system-appends/environment-info` | provider | `prompt.text` | `.../system-appends` | 40 | dynamic | yes |
| `.../system-appends/coding-discipline` | provider | `prompt.text` | `.../system-appends` | 50 | stable | yes |
| `.../system-appends/terminology` | provider | `prompt.text` | `.../system-appends` | 60 | stable | yes |
| `.../system-appends/tooling-discipline` | provider | `prompt.text` | `.../system-appends` | 70 | stable | yes |
| `.../system-appends/tool-summary` | provider | `prompt.text` | `.../system-appends` | 80 | stable | yes |
| `.../system-appends/visual-frame-description` | provider | `prompt.text` | `.../system-appends` | 90 | dynamic | yes |

### 4.3 system-messages 子插口

| path | kind | contract | requires | order | cache | exposed |
| --- | --- | --- | --- | --- | --- | --- |
| `.../system-messages/skills` | provider | `messages` | `.../system-messages` | 10 | dynamic | yes |
| `.../system-messages/rules` | provider | `messages` | `.../system-messages` | 20 | dynamic | yes |
| `.../system-messages/knowledge` | provider | `messages` | `.../system-messages` | 30 | dynamic | yes |
| `.../system-messages/memory-summary` | provider | `messages` | `.../system-messages` | 40 | dynamic | yes |

### 4.4 tail 子插口

| path | kind | contract | requires | order | cache | exposed |
| --- | --- | --- | --- | --- | --- | --- |
| `.../tail/appends/run-mode` | provider | `prompt.text` | `.../tail/appends` | 10 | dynamic | yes |
| `.../tail/appends/todo-list` | provider | `prompt.text` | `.../tail/appends` | 20 | dynamic | yes |
| `.../tail/appends/ai-speek` | provider | `prompt.text` | `.../tail/appends` | 30 | dynamic | yes |
| `.../tail/appends/ai-writing` | provider | `prompt.text` | `.../tail/appends` | 40 | dynamic | no |
| `.../tail/user-messages/visual-frame-images` | provider | `messages` | `.../tail/user-messages` | 10 | dynamic | yes |

视觉帧描述在 `system-appends`，图片在 `tail/user-messages`，两者不混用容器。

## 5. Host / Boot / Tool / Shell

### 5.1 Host services

| path | kind | requires |
| --- | --- | --- |
| `app/runtime/host` | container | — |
| `app/runtime/host/services` | container | host |
| `.../event-bus` | service | — |
| `.../error-log` | service | event-bus |
| `.../live-state` | service | — |
| `.../queue` | service | event-bus |
| `.../mesh` | service | queue |
| `.../registry` | service | — |
| `.../background-tasks` | service | — |
| `.../context-sources` | service | — |
| `.../context-hooks` | service | — |
| `.../prompt-tail` | service | — |
| `.../prompt-sections` | service | — |
| `.../contributions` | service | — |
| `.../model-catalog` | service | — |
| `.../update` | service | — |
| `.../session-factory` | service | context-sources |
| `.../compactor-factory` | service | provider |
| `.../provider` | service | model-catalog |
| `.../contexts` | service | registry, live-state |
| `.../pipeline` | service | registry, contexts, live-state |
| `.../plugin-host` | service | registry, event-bus, context-sources, pipeline, contributions, context-hooks, model-catalog, prompt-tail, prompt-sections |
| `.../store` | service | — |
| `.../subagents` | service | store, mesh, queue, event-bus |

`prompt-tail` / `prompt-sections` 只保留为宿主内部服务，不再作为插件的常规注册接口。

### 5.2 Boot / kernel

| path | kind | requires |
| --- | --- | --- |
| `app/runtime/boot` | container | — |
| `app/runtime/boot/files` | service | — |
| `app/runtime/boot/facade` | service | 全部 host services |
| `app/runtime/boot/plugins` | service | facade |
| `app/runtime/kernel` | container | — |
| `app/runtime/kernel/agent-loop` | module | kernel |
| `app/runtime/kernel/agent-loop/modules` | container | agent-loop |

### 5.3 Tools

容器：

```text
app/runtime/tools
依赖：app/runtime/kernel/agent-loop/modules/tool
```

内置工具统一：

```text
app/runtime/tools/<tool-name>
依赖：app/runtime/tools
契约：tool.schema + tool.execute
```

特殊依赖：

```text
app/runtime/tools/fs                 依赖 tools + boot/files
app/runtime/tools/executors          依赖 tools + boot/files
app/runtime/tools/commit-write       依赖 tools + executors
app/runtime/tools/<tool>/executor    依赖 tool
```

工具清单：

```text
background-task, echo, read-file, grep-files, glob-files, write-file,
edit, fs, command, tasks, session, subagent, locate, text-data,
system, web, ocr, image, archive, geo, review-conclusion, present,
executors, commit-write
```

### 5.4 Shell

| path | kind | requires |
| --- | --- | --- |
| `app/shell` | container | — |
| `app/shell/web-ui` | container | shell |
| `app/shell/web-ui/sidebar` | container | web-ui |
| `app/shell/web-ui/sidebar/left` | container | sidebar |
| `app/shell/web-ui/sidebar/left/new-conversation` | ui | sidebar/left |
| `app/shell/web-ui/sidebar/left/conversation-list` | ui | sidebar/left |
| `app/shell/web-ui/sidebar/left/usage` | ui | sidebar/left |
| `app/shell/web-ui/sidebar/right` | container | sidebar |
| `app/shell/web-ui/sidebar/right/knowledge` | ui | sidebar/right |
| `app/shell/web-ui/composer` | container | web-ui |
| `app/shell/web-ui/composer/above` | container | composer |
| `app/shell/web-ui/composer/above/left` | container | composer/above |
| `app/shell/web-ui/composer/above/right` | container | composer/above |
| `app/shell/web-ui/composer/above/right/subagents` | ui | composer/above/right |
| `app/shell/web-ui/composer/above/right/background-tasks` | ui | composer/above/right |
| `app/shell/web-ui/composer/above/left/inbox` | ui | composer/above/left |
| `app/shell/web-ui/composer/above/left/ai-speek` | ui | composer/above/left |
| `app/shell/web-ui/input/buttons` | container | web-ui |
| `app/shell/web-ui/nav/buttons` | container | web-ui |
| `app/shell/http` | container | shell |
| `app/shell/http/routes` | container | http |
| `app/shell/events` | container | shell |
| `app/shell/events/subscriptions` | container | events |
| `app/shell/adapters/classic` | service | shell |
| `app/shell/adapters/plugin-events` | service | classic |
| `app/shell/adapters/runner` | service | shell |
| `app/shell/adapters/wake-scheduler` | service | shell |
| `app/shell/adapters/finalizer` | service | classic, plugin-events, runner, wake-scheduler |
| `app/settings` | container | shell |
| `app/auth` | service | — |

### 5.5 Entry / CLI / Headless / Web

Entry 不属于 runtime，也不属于 UI；它只负责选择运行方式、装配 app、把控制权交给对应 shell。

| path | kind | requires | implementation |
|---|---|---|---|
| `app/entry` | container | — | entry 分发 |
| `app/entry/cli` | provider | `app/runtime/boot/facade`, `app/config/plugin-manifests/cli` | `agent.entry.cli:main` |
| `app/entry/cli/app-factory` | provider | `app/entry/cli`, `app/runtime/boot/plugins` | `agent.entry.cli:build_app_from_config` |
| `app/entry/cli/interactive` | container | `app/entry/cli`, `app/shell/cli/interactive` | CLI 交互循环 |
| `app/entry/headless` | provider | `app/runtime/boot/facade`, `app/config/plugin-manifests/headless` | `agent.entry.headless:main` |
| `app/entry/headless/app-factory` | provider | `app/entry/headless`, `app/runtime/boot/plugins` | `agent.entry.headless:_default_app_factory` |
| `app/entry/headless/runner` | provider | `app/entry/headless`, `app/shell/cli/headless` | 单回合运行 |
| `app/entry/web` | provider | `app/runtime/boot/facade`, `app/config/plugin-manifests/web` | `agent.entry.web:main` |
| `app/entry/web/app-factory` | provider | `app/entry/web`, `app/runtime/boot/plugins` | `agent.entry.web:build_shell_app` |
| `app/entry/web/auth-cli` | provider | `app/entry/web`, `app/shell/web/auth` | 设置密码/签发/撤销 token |
| `app/entry/web/server` | provider | `app/entry/web`, `app/shell/web/server` | Web server |
| `app/entry/web/tls` | provider | `app/entry/web`, `app/shell/web/server` | TLS 配置 |

CLI / headless shell 的插口：

| path | kind | requires | implementation |
|---|---|---|---|
| `app/shell/cli` | container | — | CLI shell |
| `app/shell/cli/interactive` | container | `app/shell/cli` | 交互式会话 |
| `app/shell/cli/interactive/args` | provider | `app/shell/cli/interactive` | 参数解析 |
| `app/shell/cli/interactive/session` | provider | `app/shell/cli/interactive` | 会话创建/恢复 |
| `app/shell/cli/interactive/system-prompt` | provider | `app/shell/cli/interactive` | CLI 专用系统提示词 |
| `app/shell/cli/interactive/renderer` | provider | `app/shell/cli/interactive` | 流式文本/工具渲染 |
| `app/shell/cli/interactive/preview-confirmation` | provider | `app/shell/cli/interactive` | [y/N] 预览确认 |
| `app/shell/cli/interactive/loop` | container | `app/shell/cli/interactive` | 输入循环/退出码 |
| `app/shell/cli/headless` | container | `app/shell/cli` | 无 UI 单回合 |
| `app/shell/cli/headless/args` | provider | `app/shell/cli/headless` | 参数解析 |
| `app/shell/cli/headless/runner` | provider | `app/shell/cli/headless` | 事件流运行 |
| `app/shell/cli/headless/renderer` | provider | `app/shell/cli/headless` | 事件格式化 |
| `app/shell/cli/headless/timeout` | provider | `app/shell/cli/headless` | 超时/取消 |
| `app/shell/cli/headless/exit-code` | provider | `app/shell/cli/headless` | 0/1/2/3 退出码 |

Web shell 的入口插口：

| path | kind | requires | implementation |
|---|---|---|---|
| `app/shell/web` | container | — | Web shell |
| `app/shell/web/server` | provider | `app/shell/web` | HTTP server |
| `app/shell/web/auth` | provider | `app/shell/web` | 认证运行时 |
| `app/shell/web/static` | provider | `app/shell/web` | 静态资源 |
| `app/shell/web/events` | provider | `app/shell/web` | SSE/事件流 |

Manifest 覆盖插口：

| path | kind | requires | implementation |
|---|---|---|---|
| `app/config/plugin-manifests` | container | — | manifest 合集 |
| `app/config/plugin-manifests/base` | config | — | `plugins.ini` |
| `app/config/plugin-manifests/cli` | config | base | `plugins.cli.ini` |
| `app/config/plugin-manifests/headless` | config | base | `plugins.headless.ini` |
| `app/config/plugin-manifests/web` | config | base | `plugins.ini` |

CLI/headless 模式必须通过 manifest 禁用会说话插件：

```text
app/config/plugin-manifests/cli        → [plugin:ai_cosplay] enabled=0
app/config/plugin-manifests/headless   → [plugin:ai_cosplay] enabled=0
```

当前 `plugins.cli.ini` 和 `plugins.headless.ini` 仍写的是旧名：

```ini
[plugin:ai_speak]
enabled = 0
```

这两处是迁移缺陷，必须改为 `ai_cosplay`，否则 CLI/headless 仍会加载会说话插件。

### 5.6 主插口与工具壳

主插口规则：

```text
一个独立模块 = 一个主插口
一个插件 = 一个主插口
一个工具 = 一个主插口
所有子插口路径必须以主插口路径为前缀
主插口禁用/卸载 = 整个子树不可用
替换主插口 = 整个子树替换
```

主插口（全量模块）：

### 入口模块

| owner | 主插口 | 说明 |
|---|---|---|
| entry | `app/entry` | entry 容器 |
| entry | `app/entry/cli` | CLI 入口 |
| entry | `app/entry/headless` | headless 入口 |
| entry | `app/entry/web` | Web 入口 |

### 内核模块

| owner | 主插口 | 说明 |
|---|---|---|
| kernel | `app/runtime/kernel` | 内核容器 |
| kernel | `app/runtime/kernel/agent-loop` | 主循环 |
| kernel | `app/runtime/kernel/agent-loop/modules` | 模块容器 |
| kernel | `app/runtime/kernel/agent-loop/modules/input` | 输入 |
| kernel | `app/runtime/kernel/agent-loop/modules/queued-input` | 排队输入 |
| kernel | `app/runtime/kernel/agent-loop/modules/context` | 上下文 |
| kernel | `app/runtime/kernel/agent-loop/modules/context/prompt` | 提示词组装 |
| kernel | `app/runtime/kernel/agent-loop/modules/context/extract` | 上下文提取 |
| kernel | `app/runtime/kernel/agent-loop/modules/compress` | 压缩 |
| kernel | `app/runtime/kernel/agent-loop/modules/model` | 模型 |
| kernel | `app/runtime/kernel/agent-loop/modules/tool` | 工具 |

### Host / Boot 模块

| owner | 主插口 | 说明 |
|---|---|---|
| host | `app/runtime/host` | Host 容器 |
| host | `app/runtime/host/services` | 服务容器 |
| host | `app/runtime/host/services/event-bus` | 事件总线 |
| host | `app/runtime/host/services/error-log` | 错误日志 |
| host | `app/runtime/host/services/live-state` | 会话状态 |
| host | `app/runtime/host/services/queue` | 会话队列 |
| host | `app/runtime/host/services/mesh` | 会话网格 |
| host | `app/runtime/host/services/registry` | 工具注册表 |
| host | `app/runtime/host/services/background-tasks` | 后台任务 |
| host | `app/runtime/host/services/context-sources` | 上下文源 |
| host | `app/runtime/host/services/context-hooks` | 上下文钩子 |
| host | `app/runtime/host/services/prompt-tail` | 尾部注册表 |
| host | `app/runtime/host/services/prompt-sections` | 章节注册表 |
| host | `app/runtime/host/services/contributions` | 贡献登记 |
| host | `app/runtime/host/services/model-catalog` | 模型目录 |
| host | `app/runtime/host/services/update` | 更新 |
| host | `app/runtime/host/services/session-factory` | 会话工厂 |
| host | `app/runtime/host/services/compactor-factory` | 压缩器工厂 |
| host | `app/runtime/host/services/provider` | Provider |
| host | `app/runtime/host/services/contexts` | 会话上下文 |
| host | `app/runtime/host/services/pipeline` | 工具管道 |
| host | `app/runtime/host/services/plugin-host` | 插件宿主 |
| host | `app/runtime/host/services/store` | 会话存储 |
| host | `app/runtime/host/services/subagents` | 子智能体 |
| boot | `app/runtime/boot` | 启动容器 |
| boot | `app/runtime/boot/files` | 文件根 |
| boot | `app/runtime/boot/facade` | 启动门面 |
| boot | `app/runtime/boot/plugins` | 插件装配 |
| auth | `app/auth` | 认证运行时 |

### Shell / UI 模块

| owner | 主插口 | 说明 |
|---|---|---|
| shell | `app/shell` | Shell 容器 |
| shell | `app/shell/web-ui` | Web UI |
| shell | `app/shell/web-ui/nav` | 导航 |
| shell | `app/shell/web-ui/composer` | 输入区 |
| shell | `app/shell/web-ui/composer/above` | 输入区上方 |
| shell | `app/shell/web-ui/composer/above/left` | 输入区左栏 |
| shell | `app/shell/web-ui/composer/above/right` | 输入区右栏 |
| shell | `app/shell/web-ui/chat` | 对话区 |
| shell | `app/shell/web-ui/chat/messages` | 消息区 |
| shell | `app/shell/web-ui/chat/messages/tools` | 工具壳解析器 |
| shell | `app/shell/web-ui/context` | 上下文区 |
| shell | `app/shell/web-ui/context/usage` | 上下文用量 |
| shell | `app/shell/web-ui/sidebar` | 侧栏容器 |
| shell | `app/shell/web-ui/sidebar/left` | 左侧栏 |
| shell | `app/shell/web-ui/sidebar/right` | 右侧栏 |
| shell | `app/shell/web-ui/runtime` | UI 运行时 |
| shell | `app/shell/web-ui/settings` | 界面设置 |
| shell | `app/shell/cli` | CLI Shell |
| shell | `app/shell/cli/interactive` | CLI 交互 |
| shell | `app/shell/cli/headless` | CLI headless |
| shell | `app/shell/web` | Web Shell |
| shell | `app/shell/web/server` | HTTP server |
| shell | `app/shell/web/auth` | 认证 |
| shell | `app/shell/web/static` | 静态资源 |
| shell | `app/shell/http` | HTTP |
| shell | `app/shell/http/routes` | 路由容器 |
| shell | `app/shell/events` | 事件 |
| shell | `app/shell/events/subscriptions` | 订阅容器 |
| shell | `app/shell/adapters` | 适配器容器 |
| shell | `app/shell/adapters/classic` | 经典适配器 |
| shell | `app/shell/adapters/plugin-events` | 插件事件 |
| shell | `app/shell/adapters/runner` | Runner |
| shell | `app/shell/adapters/wake-scheduler` | 唤醒调度 |
| shell | `app/shell/adapters/finalizer` | 收尾 |
| config | `app/config` | 配置容器 |
| config | `app/config/plugin-manifests` | 插件清单容器 |
| config | `app/config/plugin-manifests/base` | 基础清单 |
| config | `app/config/plugin-manifests/cli` | CLI 覆盖 |
| config | `app/config/plugin-manifests/headless` | Headless 覆盖 |
| config | `app/config/plugin-manifests/web` | Web 清单 |

### 插件主插口

| owner | 主插口 | 说明 |
|---|---|---|
| plugin | `app/plugins/ai_cosplay` | AI说话 |
| plugin | `app/plugins/visual_operator_2` | 视觉操作 |
| plugin | `app/plugins/skills` | Skills |
| plugin | `app/plugins/rules` | Rules |
| plugin | `app/plugins/knowledge` | 知识库 |
| plugin | `app/plugins/multi_model` | 多模型 |
| plugin | `app/plugins/theme_style` | 主题 |
| plugin | `app/plugins/auto_update` | 更新 |
| plugin | `app/plugins/ai_writing` | AI写字 |

### 内置工具主插口

```text
app/tools/<builtin-tool>
```

共 46 个，逐项见 5.6.1。

### 插件工具主插口

```text
app/plugins/ai_cosplay/tools/ai_speek
app/plugins/skills/tools/skills
app/plugins/visual_operator_2/tools/vision_*  （20 个）
```

工具主插口：

```text
内置工具：
app/tools/<tool-name>

插件工具：
app/plugins/<plugin>/tools/<tool-name>
```

工具自己的子插口：

```text
app/tools/<tool-name>/schema
app/tools/<tool-name>/executor
app/tools/<tool-name>/ui/tool-shell

app/plugins/<plugin>/tools/<tool-name>/schema
app/plugins/<plugin>/tools/<tool-name>/executor
app/plugins/<plugin>/tools/<tool-name>/ui/tool-shell
```

工具壳统一契约：

```text
title / summary / mount / fill
```

### 5.6.1 内置工具主插口

```text
app/tools/apply_patch
app/tools/approval_confirm
app/tools/archive
app/tools/background_task
app/tools/commit_write
app/tools/data_table
app/tools/delete_file
app/tools/echo
app/tools/env_probe
app/tools/file_ops
app/tools/file_search
app/tools/file_undo
app/tools/find_in_file
app/tools/git_workspace
app/tools/glob_files
app/tools/goal
app/tools/grep_files
app/tools/image_ocr
app/tools/ip_geolocate
app/tools/open_meteo_weather
app/tools/present
app/tools/python_inline
app/tools/read_file
app/tools/read_image
app/tools/read_write
app/tools/regex_locate
app/tools/replace_in_file
app/tools/review_conclusion
app/tools/run_command
app/tools/run_type
app/tools/session_broadcast
app/tools/session_create
app/tools/session_list
app/tools/session_multisend
app/tools/session_send
app/tools/task_schedule
app/tools/task_sleep
app/tools/task_wake_cancel
app/tools/task_wake_list
app/tools/text_diff
app/tools/todo_list
app/tools/unified_diagnose
app/tools/user_confirm
app/tools/web_fetch
app/tools/web_fetch_render
app/tools/write_file
```

工具主插口归属：

```text
内置工具：46 个 → app/tools/<tool>
视觉工具：20 个 → app/plugins/visual_operator_2/tools/<tool>
AI说话：1 个  → app/plugins/ai_cosplay/tools/ai_speek
Skills：1 个   → app/plugins/skills/tools/skills
合计：68 个
```

`vision_*` 不放在 `app/tools` 下。

### 5.6.2 视觉插件主插口

```text
app/plugins/visual_operator_2
├─ tools
│  ├─ vision_app
│  ├─ vision_click
│  ├─ vision_click_sequence
│  ├─ vision_click_text
│  ├─ vision_eye
│  ├─ vision_find
│  ├─ vision_focus
│  ├─ vision_key
│  ├─ vision_keyboard
│  ├─ vision_mouse
│  ├─ vision_move
│  ├─ vision_move_focus
│  ├─ vision_move_point
│  ├─ vision_open
│  ├─ vision_request_open
│  ├─ vision_start
│  ├─ vision_stop
│  ├─ vision_type_into
│  ├─ vision_wait
│  └─ vision_window
├─ prompt
│  └─ visual-frame-description
├─ user-messages
│  └─ visual-frame-images
├─ ui
│  ├─ button
│  └─ tool-shell/<tool-name>
└─ runtime
```

替换整个视觉操作：

```text
绑定 app/plugins/visual_operator_2
mode = replace_subtree
```

一次替换全部视觉工具、提示词、图片注入和 UI，不需要逐个替换 `vision_*` 工具壳。

### 5.6.3 AI说话主插口

```text
app/plugins/ai_cosplay
├─ tools
│  └─ ai_speek
│     ├─ description
│     ├─ schema
│     └─ ui/tool-shell
├─ ui
│  └─ panel
├─ prompt
│  └─ tail/ai-speek
├─ routes
│  ├─ config
│  ├─ status
│  └─ played
├─ events
│  ├─ turn-ended
│  └─ error
└─ runtime
```

UI 面板通过 `target` 挂到：

```text
target = app/shell/web-ui/composer/above/left/ai-speek
```

工具壳路径：

```text
app/plugins/ai_cosplay/tools/ai_speek/ui/tool-shell
```

### 5.6.4 其他插件主插口

```text
app/plugins/skills
  tools/skills
  ui/tool-shell
  prompt/system-messages
  ui/segment

app/plugins/rules
  prompt/system-messages
  ui/segment

app/plugins/knowledge
  prompt/system-messages
  ui/button
  ui/panel
  ui/segment

app/plugins/multi_model
  models/catalog
  settings/model
  ui/button

app/plugins/theme_style
  settings/interface
  ui/panel
  ui/button

app/plugins/auto_update
  ui/button
```

### 5.6.5 Shell 只做挂载，不拥有插件子树

```text
app/shell/web-ui/composer/above/left
app/shell/web-ui/composer/above/right
app/shell/web-ui/chat/messages/tools
app/shell/web-ui/sidebar/left
app/shell/web-ui/sidebar/right
```

这些是挂载容器。

```text
app/shell/web-ui/chat/messages/tools
```

不是 68 个工具壳的父插口；它只是解析器，按工具主插口查找：

```text
tool main slot + "/ui/tool-shell"
```

禁止再写：

```text
app/shell/web-ui/chat/messages/tools/vision_*
```

视觉工具壳应在：

```text
app/plugins/visual_operator_2/tools/<tool-name>/ui/tool-shell
```

### 5.6.6 定制工具壳

定制壳仍挂在工具主插口下：

| tool | 路径 | 定制行为 |
|---|---|---|
| `goal` | `app/tools/goal/ui/tool-shell` | 目标卡 |
| `write_file` | `app/tools/write_file/ui/tool-shell` | 编辑族/预览 |
| `replace_in_file` | `app/tools/replace_in_file/ui/tool-shell` | 编辑族/预览 |
| `read_write` | `app/tools/read_write/ui/tool-shell` | 编辑族/预览 |
| `apply_patch` | `app/tools/apply_patch/ui/tool-shell` | 编辑族/预览 |
| `commit_write` | `app/tools/commit_write/ui/tool-shell` | 提交 |
| `review_conclusion` | `app/tools/review_conclusion/ui/tool-shell` | Review |
| `run_command` | `app/tools/run_command/ui/tool-shell` | 命令执行 |
| `python_inline` | `app/tools/python_inline/ui/tool-shell` | 代码执行 |
| `file_undo` | `app/tools/file_undo/ui/tool-shell` | diff |
| `read_file` | `app/tools/read_file/ui/tool-shell` | 文件读取 |
| `read_image` | `app/tools/read_image/ui/tool-shell` | 看图 |
| `delete_file` | `app/tools/delete_file/ui/tool-shell` | 删除预览 |
| `glob_files` | `app/tools/glob_files/ui/tool-shell` | 文件枚举 |
| `present` | `app/tools/present/ui/tool-shell` | 文件交付 |
| `skills` | `app/plugins/skills/tools/skills/ui/tool-shell` | Skills 加载 |
| `ai_speek` | `app/plugins/ai_cosplay/tools/ai_speek/ui/tool-shell` | AI说话 |

`desktop_eye / desktop_mouse / desktop_keyboard / wait / sleep` 是旧工具壳匹配名；若工具不再注册，这些壳不进入新树。

### 5.7 主模块结构

每个主模块按同一格式展示。主模块下的所有子模块都以主模块路径为前缀。

#### 5.7.1 `app/runtime/kernel/agent-loop`

```text
app/runtime/kernel/agent-loop
├─ modules
│  ├─ input
│  ├─ queued-input
│  ├─ context
│  │  ├─ prompt
│  │  │  ├─ base-system
│  │  │  ├─ system-appends
│  │  │  ├─ system-messages
│  │  │  └─ tail
│  │  │     ├─ appends
│  │  │     │  ├─ run-mode
│  │  │     │  ├─ todo-list
│  │  │     │  ├─ ai-speek
│  │  │     │  └─ ai-writing
│  │  │     └─ user-messages
│  │  │        └─ visual-frame-images
│  │  └─ extract
│  ├─ compress
│  ├─ model
│  └─ tool
└─ kernel stages
   ├─ tool/pipeline
   ├─ prompt/assemble
   ├─ model/router
   ├─ context/assembly
   └─ compaction/{build-context,summarize,policy}
```

#### 5.7.2 `app/runtime/kernel/agent-loop/modules/context`

```text
app/runtime/kernel/agent-loop/modules/context
├─ prompt
│  ├─ base-system
│  ├─ system-appends
│  ├─ system-messages
│  └─ tail
│     ├─ appends
│     └─ user-messages
└─ extract
```

#### 5.7.3 `app/runtime/kernel/agent-loop/modules/compress`

```text
app/runtime/kernel/agent-loop/modules/compress
├─ context
│  ├─ prompt
│  └─ extract
└─ summarize
```

#### 5.7.4 `app/runtime/kernel/agent-loop/modules/tool`

```text
app/runtime/kernel/agent-loop/modules/tool
├─ registry
├─ pipeline
└─ executors
```

#### 5.7.5 `app/runtime/host`

```text
app/runtime/host
├─ services
│  ├─ event-bus
│  ├─ error-log
│  ├─ live-state
│  ├─ queue
│  ├─ mesh
│  ├─ registry
│  ├─ background-tasks
│  ├─ context-sources
│  ├─ context-hooks
│  ├─ prompt-tail
│  ├─ prompt-sections
│  ├─ contributions
│  ├─ model-catalog
│  ├─ update
│  ├─ session-factory
│  ├─ compactor-factory
│  ├─ provider
│  ├─ contexts
│  ├─ pipeline
│  ├─ plugin-host
│  ├─ store
│  └─ subagents
└─ boot
   ├─ files
   ├─ facade
   └─ plugins
```

#### 5.7.6 `app/entry`

```text
app/entry
├─ cli
│  ├─ app-factory
│  └─ interactive
├─ headless
│  ├─ app-factory
│  └─ runner
└─ web
   ├─ app-factory
   ├─ auth-cli
   ├─ server
   └─ tls
```

#### 5.7.7 `app/shell`

```text
app/shell
├─ web-ui
│  ├─ nav
│  ├─ composer
│  │  ├─ above
│  │  │  ├─ left
│  │  │  └─ right
│  │  └─ input
│  ├─ chat
│  │  └─ messages
│  │     └─ tools
│  ├─ context
│  │  └─ usage
│  ├─ sidebar
│  │  ├─ left
│  │  │  ├─ new-conversation
│  │  │  ├─ conversation-list
│  │  │  └─ usage
│  │  └─ right
│  │     └─ knowledge
│  ├─ runtime
│  └─ settings
├─ cli
│  ├─ interactive
│  │  ├─ args
│  │  ├─ session
│  │  ├─ system-prompt
│  │  ├─ renderer
│  │  ├─ preview-confirmation
│  │  └─ loop
│  └─ headless
│     ├─ args
│     ├─ runner
│     ├─ renderer
│     ├─ timeout
│     └─ exit-code
├─ web
│  ├─ server
│  ├─ auth
│  └─ static
├─ http
│  └─ routes
├─ events
│  └─ subscriptions
└─ adapters
   ├─ classic
   ├─ plugin-events
   ├─ runner
   ├─ wake-scheduler
   └─ finalizer
```

#### 5.7.8 `app/tools`

```text
app/tools
└─ <builtin-tool>
   ├─ schema
   ├─ executor
   └─ ui/tool-shell
```

内置工具 46 个；每个工具的 `<builtin-tool>` 是一个主插口。

#### 5.7.9 `app/plugins/ai_cosplay`

```text
app/plugins/ai_cosplay
├─ tools
│  └─ ai_speek
│     ├─ description
│     ├─ schema
│     └─ ui/tool-shell
├─ ui
│  └─ panel
├─ prompt
│  └─ tail/ai-speek
├─ routes
│  ├─ config
│  ├─ status
│  └─ played
├─ events
│  ├─ turn-ended
│  └─ error
└─ runtime
```

#### 5.7.10 `app/plugins/visual_operator_2`

```text
app/plugins/visual_operator_2
├─ tools
│  ├─ vision_app
│  │  ├─ schema
│  │  ├─ executor
│  │  └─ ui/tool-shell
│  ├─ vision_click
│  ├─ vision_click_sequence
│  ├─ vision_click_text
│  ├─ vision_eye
│  ├─ vision_find
│  ├─ vision_focus
│  ├─ vision_key
│  ├─ vision_keyboard
│  ├─ vision_mouse
│  ├─ vision_move
│  ├─ vision_move_focus
│  ├─ vision_move_point
│  ├─ vision_open
│  ├─ vision_request_open
│  ├─ vision_start
│  ├─ vision_stop
│  ├─ vision_type_into
│  ├─ vision_wait
│  └─ vision_window
├─ prompt
│  └─ visual-frame-description
├─ user-messages
│  └─ visual-frame-images
├─ ui
│  ├─ button
│  └─ tool-shell/<tool>
└─ runtime
```

替换整个视觉操作：

```text
app/plugins/visual_operator_2
mode = replace_subtree
```

#### 5.7.11 `app/plugins/skills`

```text
app/plugins/skills
├─ tools
│  └─ skills
│     ├─ schema
│     └─ ui/tool-shell
├─ prompt
│  └─ system-messages
├─ ui
│  └─ segment
└─ runtime
```

#### 5.7.12 `app/plugins/rules`

```text
app/plugins/rules
├─ prompt
│  └─ system-messages
├─ ui
│  └─ segment
└─ runtime
```

#### 5.7.13 `app/plugins/knowledge`

```text
app/plugins/knowledge
├─ prompt
│  └─ system-messages
├─ routes
│  ├─ files
│  └─ checked
├─ ui
│  ├─ button
│  ├─ panel
│  └─ segment
└─ runtime
```

#### 5.7.14 `app/plugins/multi_model`

```text
app/plugins/multi_model
├─ models
│  └─ catalog
├─ settings
│  └─ model
├─ routes
│  └─ catalog
└─ ui
   └─ button
```

#### 5.7.15 `app/plugins/theme_style`

```text
app/plugins/theme_style
├─ settings
│  └─ interface
├─ routes
│  └─ style
├─ ui
│  ├─ panel
│  └─ button
└─ runtime
```

#### 5.7.16 `app/plugins/auto_update`

```text
app/plugins/auto_update
└─ ui
   └─ button
```

#### 5.7.17 `app/plugins/visual_operator`

```text
app/plugins/visual_operator
└─ tools
   └─ visual_operator
      ├─ schema
      └─ ui/tool-shell
```

#### 5.7.18 `app/plugins/base_settings`

```text
app/plugins/base_settings
└─ settings
   └─ base
```

#### 5.7.19 `app/plugins/web_ui`

```text
app/plugins/web_ui
└─ ui
   └─ shell
```

#### 5.7.20 `app/plugins/ai_writing`

```text
app/plugins/ai_writing
├─ prompt
│  └─ tail/ai-writing
└─ runtime
```

#### 5.7.21 `app/config`

```text
app/config
└─ plugin-manifests
   ├─ base
   ├─ cli
   ├─ headless
   └─ web
```

## 6. 插件协议

### 6.1 ai_cosplay

主插口：

```text
app/plugins/ai_cosplay
```

| path | kind | requires | exposed | 说明 |
|---|---|---|---|---|
| `app/plugins/ai_cosplay` | plugin | host services | yes | 插件主插口，替换即替换整个 AI说话插件 |
| `app/plugins/ai_cosplay/tools/ai_speek` | tool | `.../ai_cosplay` | yes | 工具主插口 |
| `.../tools/ai_speek/schema` | provider | `.../tools/ai_speek` | yes | 工具 schema |
| `.../tools/ai_speek/description` | provider | `.../tools/ai_speek` | yes | 工具 description + persona |
| `.../tools/ai_speek/ui/tool-shell` | ui | `.../tools/ai_speek` | yes | AI扮演工具壳 |
| `.../ui/panel` | ui | `.../ai_cosplay` | yes | 面板实现 |
| `.../prompt/tail/ai-speek` | provider | `.../ai_cosplay` | yes | 尾部文本 |
| `.../routes/config` | route | `.../ai_cosplay` | no | GET config |
| `.../routes/status` | route | `.../ai_cosplay` | no | GET status |
| `.../routes/played` | route | `.../ai_cosplay` | no | POST played |
| `.../events/turn-ended` | event | `.../ai_cosplay` | no | turn ended |
| `.../events/error` | event | `.../ai_cosplay` | no | error |
| `.../runtime` | service | `.../ai_cosplay` | no | 插件运行时 |

挂载目标：

```text
app/shell/web-ui/composer/above/left/ai-speek
```

`.../ui/panel` 通过 `target` 挂载，不改变它属于 `app/plugins/ai_cosplay` 前缀。

```text
.../prompt/tail/ai-speek 的 target =
app/runtime/kernel/agent-loop/modules/context/prompt/tail/appends/ai-speek
```

### 6.2 visual_operator_2

主插口：

```text
app/plugins/visual_operator_2
```

| path | kind | requires | exposed | 说明 |
|---|---|---|---|---|
| `app/plugins/visual_operator_2` | plugin | host services | yes | 替换此插口即替换整个视觉操作 |
| `.../tools/vision_app` | tool | `.../visual_operator_2` | yes | 工具主插口 |
| `.../tools/vision_click` | tool | 同上 | yes | |
| `.../tools/vision_click_sequence` | tool | 同上 | yes | |
| `.../tools/vision_click_text` | tool | 同上 | yes | |
| `.../tools/vision_eye` | tool | 同上 | yes | |
| `.../tools/vision_find` | tool | 同上 | yes | |
| `.../tools/vision_focus` | tool | 同上 | yes | |
| `.../tools/vision_key` | tool | 同上 | yes | |
| `.../tools/vision_keyboard` | tool | 同上 | yes | |
| `.../tools/vision_mouse` | tool | 同上 | yes | |
| `.../tools/vision_move` | tool | 同上 | yes | |
| `.../tools/vision_move_focus` | tool | 同上 | yes | |
| `.../tools/vision_move_point` | tool | 同上 | yes | |
| `.../tools/vision_open` | tool | 同上 | yes | |
| `.../tools/vision_request_open` | tool | 同上 | yes | |
| `.../tools/vision_start` | tool | 同上 | yes | |
| `.../tools/vision_stop` | tool | 同上 | yes | |
| `.../tools/vision_type_into` | tool | 同上 | yes | |
| `.../tools/vision_wait` | tool | 同上 | yes | |
| `.../tools/vision_window` | tool | 同上 | yes | |
| `.../prompt/visual-frame-description` | provider | `.../visual_operator_2` | yes | target = system-appends/visual-frame-description |
| `.../user-messages/visual-frame-images` | provider | `.../visual_operator_2` | yes | target = tail/user-messages/visual-frame-images |
| `.../ui/button` | ui | `.../visual_operator_2` | yes | target = composer/above/right 或 input buttons |
| `.../ui/tool-shell/<tool>` | ui | `.../tools/<tool>` | yes | 每个工具自己的壳 |
| `.../runtime` | service | `.../visual_operator_2` | no | 插件运行时 |

替换整个视觉操作：

```text
slot: app/plugins/visual_operator_2
mode: replace_subtree
```

替换后所有 `tools/*`、`prompt/*`、`user-messages/*`、`ui/*`、`runtime` 一起替换。

### 6.3 skills / rules / knowledge

每个插件一个主插口：

```text
app/plugins/skills
app/plugins/rules
app/plugins/knowledge
```

| 插件 | 主插口 | 子插口 | target |
|---|---|---|---|
| skills | `app/plugins/skills` | `tools/skills` | 工具注册表 |
| skills | 同上 | `prompt/system-messages` | `.../prompt/system-messages/skills` |
| skills | 同上 | `ui/segment` | `sidebar/left/context-usage` |
| rules | `app/plugins/rules` | `prompt/system-messages` | `.../prompt/system-messages/rules` |
| rules | 同上 | `ui/segment` | `sidebar/left/context-usage` |
| knowledge | `app/plugins/knowledge` | `prompt/system-messages` | `.../prompt/system-messages/knowledge` |
| knowledge | 同上 | `ui/button` | `input/buttons` |
| knowledge | 同上 | `ui/panel` | `sidebar/right` |

### 6.4 multi_model / theme_style / auto_update

| 插件 | 主插口 | 子插口 |
|---|---|---|
| multi_model | `app/plugins/multi_model` | `models/catalog`、`settings/model`、`ui/button` |
| theme_style | `app/plugins/theme_style` | `settings/interface`、`ui/panel`、`ui/button` |
| auto_update | `app/plugins/auto_update` | `ui/button` |

### 6.5 ai_writing

```text
主插口：app/plugins/ai_writing
子插口：app/plugins/ai_writing/prompt/tail/ai-writing
target：.../context/prompt/tail/appends/ai-writing
order：40
exposed：false
```

不暴露主插口时，外部不能替换 AI写字；插件卸载时整棵子树不可用。

## 7. 从当前实现迁移

| 当前路径 | 目标路径 |
| --- | --- |
| `agent/entry/cli.py` | `app/entry/cli` |
| `plugins/skills/plugin-ui.json` `.../tools/skill` | `.../tools/skills` |
| `plugins/ai_cosplay/ui/tool-view.js` | `.../tools/ai_speek` |
| `app/backend/tools/vision_*` | `app/plugins/visual_operator_2/tools/vision_*` |
| `app/shell/web-ui/chat/messages/tools/<plugin-tool>` | `<plugin-root>/tools/<tool>/ui/tool-shell` |
| `app/backend/runtime/<plugin>` | `app/plugins/<plugin>/runtime` |
| `agent/entry/headless.py` | `app/entry/headless` |
| `agent/entry/web.py` | `app/entry/web` |
| `agent/shell/cli/interactive.py` | `app/shell/cli/interactive` |
| `agent/shell/cli/headless.py` | `app/shell/cli/headless` |
| `agent/shell/web/*` | `app/shell/web/*` |
| `plugins.cli.ini` | `app/config/plugin-manifests/cli` |
| `plugins.headless.ini` | `app/config/plugin-manifests/headless` |
| `plugins.ini` | `app/config/plugin-manifests/base` |
| `app/kernel/...` | `app/runtime/kernel/...` |
| `app/host/services/...` | `app/runtime/host/services/...` |
| `app/boot/...` | `app/runtime/boot/...` |
| `app/boot/tools/...` | `app/runtime/tools/...` |
| `app/backend/tools/...` | `app/runtime/tools/...` |
| `app/backend/prompt/mode-tails/...` | `.../context/prompt/tail/appends/...` |
| `app/backend/prompt/sections/...` | `.../context/prompt/system-appends/...` |
| `app/backend/context/sources/...` | `.../system-messages/...` 或 `.../tail/user-messages/...` |
| `app/backend/context/assembly-hooks/...` | `.../tail/user-messages/...` |
| `app/backend/runtime/...` | `app/runtime/plugins/...` |
| `app/backend/http/routes/...` | `app/shell/http/routes/...` |
| `app/backend/events/...` | `app/shell/events/...` |
| `app/backend/models/...` | `app/runtime/models/...` |

## 8. 要删除的常规 API

```text
register_tool
set_subagent_tools
add_executor
subscribe
add_context_source
add_mode_tail
add_prompt_section
add_pre_gate
add_post_observer
add_route
add_ui_item
add_settings_panel
add_settings_item
add_model_catalog
add_context_assembly_hook
```

这些能力改为 `plugin-slots.json` 声明。

只保留特殊 API：

```text
set_runtime        仅宿主持有运行时对象的桥接
add_pre_gate       只有需要进程内安全门控的特殊插件
```

`PromptTail`、`PromptSections`、`ContextSources` 不再是插件注册入口，只保留为容器默认实现。

## 9. 审查清单

```text
[ ] 每个子插口的父路径存在
[ ] 每个 requires 指向真实插口
[ ] 同一容器内 order 不冲突
[ ] tail/appends 与 tail/user-messages 都带 tail 标记
[ ] visual-frame-description 在 tool-summary 之后
[ ] visual-frame-images 只在 tail/user-messages
[ ] ai-speek 只在 tail/appends
[ ] system-messages 不混入 tail
[ ] 所有稳定段 cache=stable
[ ] 所有请求期动态段 cache=dynamic
[ ] 所有默认实现只有一个 owner
[ ] 每个 regular 能力都有 plugin-slots.json 声明
[ ] plugin.py 不再调用常规 add_*
[ ] CLI / headless manifest 已禁用 ai_cosplay
[ ] 每个插件、工具、独立模块都有唯一主插口
[ ] 所有子插口路径都以主插口路径为前缀
[ ] 禁用/卸载主插口时整个子树不可用
[ ] 替换视觉操作只绑定 app/plugins/visual_operator_2
[ ] 所有 68 个工具都有默认工具壳
[ ] skills 工具壳路径是 .../tools/skills
[ ] ai-speek 工具壳路径已声明
[ ] CLI / headless 没有 UI、ai-speek 尾部注入
[ ] 旧路径没有残留
[ ] 插件卸载后子插口、路由、UI、设置全部回滚
```

---

# 附录 A：全部代码文件清单

统计口径：项目内 `.py` / `.js` / `.mjs` / `.ts` / `.tsx` / `.jsx`，排除 `data/`、`.git/`、`__pycache__/`、`.venv/`、`node_modules/`、`catalog/`。

```text
文件总数：550
代码总行数：111282
Python：496
JavaScript：54
```

本附录按文件维度列出：路径、行数、所属主模块、文件角色、导入、顶层符号和类成员。测试和脚本也列出，但标记为非运行期插口实现。

### A.1 `agent/app.py`

- 类型：Python
- 行数：351
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：应用门面：会话入口与上下文服务访问。
- 导入：`__future__`, `sys`, `pathlib`, `typing`, `agent.app_model_policy`, `agent.app_services`, `agent.boot.bootstrap`, `agent.common.status`, `agent.core.context`, `agent.core.engine_factory`, `agent.core.error_report`, `agent.core.events`, `agent.core.modules.slot_chain`, `agent.core.session_log`, `agent.mechanisms.quality`, `agent.shell.service_keys`
- 顶层符号：
  - L31: `def get_plugins(plugins_path)`
  - L37: `class App(AppModelPolicy, AppServices)`
  - L326: `def build_app()`
- 类成员：
  - L49: `App.__init__(self, context)`
  - L63: `App.apply_agent_loop(self)`
  - L72: `App.dispose(self)`
  - L127: `App.gate(self)`
  - L131: `App.gate_for(self, conversation_id)`
  - L142: `App._prepare_session(self, conversation_id, session_store, system_prompt)`
  - L169: `App._session_bindings(self, conversation_id, session_store)`
  - L183: `App.session(self, conversation_id)`
  - L238: `App.run_turn(self, user_text, conversation_id)`
  - L242: `App.execute_tool(self, name, arguments)`
  - L267: `App.resume_suspended(self, conversation_id, call_id, data)`

### A.2 `agent/app_model_policy.py`

- 类型：Python
- 行数：163
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：`App` 的模型策略面：可用清单、会话模型收敛、窗口与压缩阈值。
- 导入：`__future__`, `pathlib`, `typing`, `agent.common.status`, `agent.config`, `agent.core.context`, `agent.core.error_report`, `agent.mechanisms.providers.missing`
- 顶层符号：
  - L27: `class AppModelPolicy()`
- 类成员：
  - L30: `AppModelPolicy.available_models(self)`
  - L41: `AppModelPolicy._catalog_snapshot(self)`
  - L55: `AppModelPolicy.model_catalog(self)`
  - L60: `AppModelPolicy.model_config(self)`
  - L69: `AppModelPolicy.model_for(self, conversation_id)`
  - L99: `AppModelPolicy.context_window_for(self, conversation_id)`
  - L112: `AppModelPolicy.compression_percent_for(self, conversation_id)`
  - L121: `AppModelPolicy.compression_threshold_for(self, conversation_id)`
  - L131: `AppModelPolicy.reload_model_config(self, config_path)`
  - L137: `AppModelPolicy.refresh_model_config(self, config_path)`
  - L148: `AppModelPolicy._reload_policy(self, allowed_ids, default_id, fallback)`
  - L154: `AppModelPolicy._mark_model_config_none(self)`

### A.3 `agent/app_services.py`

- 类型：Python
- 行数：136
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：`App` 的服务解析面：属性即进程级 `AppContext` 中登记实例的快捷方式。
- 导入：`__future__`, `typing`, `agent.capabilities.registry`, `agent.core.context`, `agent.core.session_context`, `agent.core.tool_call`, `agent.shell.service_keys`
- 顶层符号：
  - L33: `class AppServices()`
- 类成员：
  - L36: `AppServices._svc(self, name)`
  - L46: `AppServices.registry(self)`
  - L50: `AppServices.pipeline(self)`
  - L54: `AppServices.provider(self)`
  - L58: `AppServices.store(self)`
  - L62: `AppServices.context_factory(self)`
  - L70: `AppServices.live_state(self)`
  - L74: `AppServices.mesh(self)`
  - L78: `AppServices.plugin_host(self)`
  - L82: `AppServices.event_bus(self)`
  - L86: `AppServices.context_sources(self)`
  - L94: `AppServices.context_hooks(self)`
  - L102: `AppServices.conversation_queue(self)`
  - L110: `AppServices.prompt_tail(self)`
  - L118: `AppServices.compactor_factory(self)`
  - L126: `AppServices.session_contexts(self)`
  - L134: `AppServices.runner(self)`

### A.4 `agent/boot/bootstrap.py`

- 类型：Python
- 行数：97
- 所属主模块：`app/runtime/boot`
- 文件角色：runtime/implementation
- 文件说明：自装配启动器：读取唯一树，递归装配，返回 App。
- 导入：`__future__`, `pathlib`, `typing`, `agent.boot.config`, `agent.boot.plugin_assembly`, `agent.capabilities.slot_registry`, `agent.config`, `agent.core.slot_tree`, `agent.mechanisms.executors`, `agent.mechanisms.providers.missing`, `agent.session_paths`
- 顶层符号：
  - L24: `def boot_app()`

### A.5 `agent/boot/components.py`

- 类型：Python
- 行数：221
- 所属主模块：`app/runtime/boot`
- 文件角色：runtime/implementation
- 文件说明：自装配组件工厂：容器、服务叶子、运行时门面。
- 导入：`__future__`, `typing`, `agent.common.status`, `agent.config`, `agent.core.context`, `agent.core.slot`, `agent.mechanisms.file_safety`
- 顶层符号：
  - L19: `class SlotResult(SlotLeaf)`
  - L30: `class KernelModuleGroup(SlotContainer)`
  - L82: `def kernel_group(ctx)`
  - L92: `class KernelModulePlugin(SlotLeaf)`
  - L103: `def kernel_module(ctx)`
  - L113: `def append_context(ctx)`
  - L124: `def service_component(ctx)`
  - L139: `def container(ctx)`
  - L143: `def files(ctx)`
  - L161: `def facade(ctx)`
  - L187: `def plugins(ctx)`
- 类成员：
  - L22: `SlotResult.__init__(self, path, ok)`
  - L26: `SlotResult.assembly(self, tree)`
  - L33: `KernelModuleGroup.__init__(self, path)`
  - L39: `KernelModuleGroup.assembly(self, tree)`
  - L46: `KernelModuleGroup.configure_loop(self)`
  - L53: `KernelModuleGroup.build_modules(self, context)`
  - L95: `KernelModulePlugin.__init__(self, path, builder)`
  - L99: `KernelModulePlugin.build(self, context, children)`

### A.6 `agent/boot/config.py`

- 类型：Python
- 行数：49
- 所属主模块：`app/runtime/boot`
- 文件角色：runtime/implementation
- 文件说明：启动配置：自装配树运行期所需的全部外部输入。
- 导入：`__future__`, `dataclasses`, `typing`, `agent.config`
- 顶层符号：
  - L12: `class HostBootConfig()`
  - L32: `class BootConfig()`

### A.7 `agent/boot/host_factories.py`

- 类型：Python
- 行数：222
- 所属主模块：`app/runtime/boot`
- 文件角色：runtime/implementation
- 文件说明：宿主服务组件工厂；路径与依赖由插口树声明。
- 导入：`__future__`, `typing`, `agent.capabilities.contributions`, `agent.capabilities.model_catalog`, `agent.capabilities.plugins`, `agent.capabilities.registry`, `agent.config`, `agent.core`, `agent.core.event_bus`, `agent.core.events`, `agent.core.session_context`, `agent.mechanisms.background_tasks`, `agent.mechanisms.context`, `agent.mechanisms.context.hooks`, `agent.mechanisms.context.sources`, `agent.mechanisms.conversation_queue`, `agent.mechanisms.error_log`, `agent.mechanisms.live_state`, `agent.mechanisms.mesh`, `agent.mechanisms.prompt_sections`
- 顶层符号：
  - L33: `def _config(ctx)`
  - L37: `def make_event_bus(ctx)`
  - L41: `def make_error_log(ctx)`
  - L45: `def make_live_state(ctx)`
  - L52: `def make_queue(ctx)`
  - L66: `def make_mesh(ctx)`
  - L73: `def make_registry(ctx)`
  - L77: `def make_background_tasks(ctx)`
  - L82: `def make_context_sources(ctx)`
  - L86: `def make_context_hooks(ctx)`
  - L90: `def make_prompt_tail(ctx)`
  - L94: `def make_prompt_sections(ctx)`
  - L98: `def make_contributions(ctx)`
  - L102: `def make_model_catalog(ctx)`
  - L106: `def make_update(ctx)`
  - L110: `def make_session_factory(ctx)`
  - L128: `def make_compactor_factory(ctx)`
  - L149: `def make_provider(ctx)`
  - L160: `def make_contexts(ctx)`
  - L172: `def make_pipeline(ctx)`
  - L185: `def make_plugin_host(ctx)`
  - L199: `def make_store(ctx)`
  - L203: `def make_subagents(ctx)`

### A.8 `agent/boot/plugin_assembly.py`

- 类型：Python
- 行数：184
- 所属主模块：`app/runtime/boot`
- 文件角色：runtime/implementation
- 文件说明：插件目录内的启动期装配声明。
- 导入：`__future__`, `importlib.util`, `json`, `re`, `sys`, `dataclasses`, `pathlib`, `types`, `typing`
- 顶层符号：
  - L24: `class PluginAssemblyError(RuntimeError)`
  - L29: `class AssemblyOverlay()`
  - L36: `def _truthy(value)`
  - L40: `def _name(value)`
  - L47: `def _json(path)`
  - L57: `def _disabled(entry)`
  - L61: `def _package(name, path)`
  - L72: `def _factory(root, name, spec)`
  - L107: `def _nodes(root, name)`
  - L134: `def discover(plugins_dir, manifest)`

### A.9 `agent/boot/shell_components.py`

- 类型：Python
- 行数：151
- 所属主模块：`app/runtime/boot`
- 文件角色：runtime/implementation
- 文件说明：壳层组件：运行器、唤醒调度、经典适配与插件事件出口。
- 导入：`__future__`, `typing`, `agent.core.context`, `agent.core.slot`, `agent.shell.service_keys`
- 顶层符号：
  - L18: `def _app(ctx)`
  - L22: `def _leaf(ctx)`
  - L26: `def runner(ctx)`
  - L53: `def wake_scheduler(ctx)`
  - L99: `def classic_adapter(ctx)`
  - L108: `def plugin_events(ctx)`
  - L115: `def finalizer(ctx)`
  - L132: `def _notice_handler(app, runner)`

### A.10 `agent/boot/tool_components.py`

- 类型：Python
- 行数：184
- 所属主模块：`app/runtime/boot`
- 文件角色：runtime/implementation
- 文件说明：内置工具节点工厂：每个节点只注册自己的工具，不枚举其他工具。
- 导入：`__future__`, `typing`, `agent.core.context`, `agent.core.slot`
- 顶层符号：
  - L11: `def _app(ctx)`
  - L15: `def _leaf(ctx)`
  - L19: `def _register(ctx, plugins)`
  - L25: `def make_background_task(ctx)`
  - L33: `def make_echo(ctx)`
  - L39: `def make_read_file(ctx)`
  - L45: `def make_grep_files(ctx)`
  - L51: `def make_glob_files(ctx)`
  - L57: `def make_write_file(ctx)`
  - L63: `def make_edit_tools(ctx)`
  - L68: `def make_fs_tools(ctx)`
  - L75: `def make_command_tools(ctx)`
  - L80: `def make_tasks(ctx)`
  - L85: `def make_session_tools(ctx)`
  - L90: `def make_subagent_tools(ctx)`
  - L99: `def make_locate_tools(ctx)`
  - L104: `def make_text_data_tools(ctx)`
  - L109: `def make_system_tools(ctx)`
  - L114: `def make_web_tools(ctx)`
  - L119: `def make_ocr_tool(ctx)`
  - L124: `def make_image_tool(ctx)`
  - L129: `def make_archive_tool(ctx)`
  - L134: `def make_geo_weather_tools(ctx)`
  - L139: `def make_review_conclusion(ctx)`
  - L145: `def make_present_tool(ctx)`
  - L151: `def make_executors(ctx)`
  - L175: `def make_commit_write(ctx)`

### A.11 `agent/capabilities/backend_paths.py`

- 类型：Python
- 行数：46
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：后端扩展路径插口。
- 导入：`__future__`, `typing`, `agent.capabilities.slot_registry`
- 顶层符号：
  - L37: `def seed_backend_slots(paths, backend)`

### A.12 `agent/capabilities/builtin/archive_tool.py`

- 类型：Python
- 行数：362
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：压缩包工具：archive——list / extract / create（预览 + 统一提交执行器）。
- 导入：`__future__`, `fnmatch`, `io`, `re`, `tarfile`, `zipfile`, `datetime`, `pathlib`, `typing`, `agent.capabilities.registry`, `agent.core.error_report`
- 顶层符号：
  - L23: `def _detect_format(source)`
  - L57: `def _open_archive(source, password)`
  - L83: `def _member_name(member, fmt)`
  - L87: `def _iter_members(arc, fmt, glob_pattern)`
  - L94: `def _list_archive(source, password, glob_pattern)`
  - L131: `def _add_to_zip(zf, root, current, glob_pattern)`
  - L149: `def _add_to_tar(tf, root, current, glob_pattern)`
  - L167: `def _count_archive_create(source, fmt, glob_pattern)`
  - L182: `class ArchiveTool(ToolPlugin)`
  - L259: `def _safe_extract_name(name, dst)`
  - L273: `def _validate_members(members, fmt, dst)`
  - L286: `def _execute_archive(arguments)`
  - L354: `def build_plugins()`
  - L359: `def build_executors()`
- 类成员：
  - L200: `ArchiveTool.execute(self, arguments)`

### A.13 `agent/capabilities/builtin/background_task.py`

- 类型：Python
- 行数：96
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：background_task：按会话管理后台进程。
- 导入：`__future__`, `typing`, `agent.capabilities.builtin.command_tools`, `agent.capabilities.registry`, `agent.core.session_scope`, `agent.mechanisms.background_tasks`
- 顶层符号：
  - L13: `class BackgroundTaskTool(ToolPlugin)`
  - L94: `def build(manager, live_state)`
- 类成员：
  - L52: `BackgroundTaskTool.__init__(self, manager, live_state)`
  - L56: `BackgroundTaskTool.execute(self, arguments)`

### A.14 `agent/capabilities/builtin/command_tools.py`

- 类型：Python
- 行数：461
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：命令执行工具组：run_command / python_inline。
- 导入：`__future__`, `io`, `os`, `re`, `subprocess`, `threading`, `time`, `traceback`, `contextlib`, `pathlib`, `typing`, `agent.capabilities.registry`, `agent.core.error_report`, `agent.core.session_scope`, `agent.core.thread_context`, `agent.mechanisms.command_safety`, `agent.mechanisms.live_state`
- 顶层符号：
  - L79: `def _detect_awaiting_input(text_tail)`
  - L89: `def _resolve_cwd(arguments)`
  - L100: `def reject_in_plan_mode(live_state, action)`
  - L109: `def _close_streams(proc)`
  - L121: `def _read_available(stream, chunk)`
  - L149: `def _pump_report(reporter, progress, tail, lock, name, chunk)`
  - L169: `def _pump_reader(stream, chunks, name, report)`
  - L180: `def _pump_stdin(proc, progress, tail, lock, start_ts, state)`
  - L211: `def _pump(proc, out_chunks, err_chunks, timeout, progress, readers)`
  - L253: `class RunCommandTool(ToolPlugin)`
  - L370: `class _ProgressText(io.TextIOBase)`
  - L389: `class PythonInlineTool(ToolPlugin)`
  - L458: `def build_plugins(live_state)`
- 类成员：
  - L271: `RunCommandTool.__init__(self, live_state)`
  - L274: `RunCommandTool.execute(self, arguments)`
  - L294: `RunCommandTool._run(self, command, cwd, arguments)`
  - L373: `_ProgressText.__init__(self, sink, stream)`
  - L377: `_ProgressText.write(self, s)`
  - L385: `_ProgressText.flush(self)`
  - L405: `PythonInlineTool.__init__(self, live_state)`
  - L408: `PythonInlineTool.execute(self, arguments)`

### A.15 `agent/capabilities/builtin/commit_write.py`

- 类型：Python
- 行数：74
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：commit_write：统一提交入口——凭 confirm_id 从预览快照分派执行。
- 导入：`__future__`, `typing`, `agent.capabilities.registry`, `agent.capabilities.session_gate`
- 顶层符号：
  - L17: `class CommitWriteTool(ToolPlugin)`
  - L68: `def build(executors, dynamic)`
- 类成员：
  - L36: `CommitWriteTool.__init__(self, executors, dynamic)`
  - L45: `CommitWriteTool.execute(self, arguments)`

### A.16 `agent/capabilities/builtin/echo.py`

- 类型：Python
- 行数：26
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：echo 工具：回显输入文本。
- 导入：`__future__`, `typing`, `agent.capabilities.registry`
- 顶层符号：
  - L10: `class EchoTool(ToolPlugin)`
  - L23: `def build()`
- 类成员：
  - L19: `EchoTool.execute(self, arguments)`

### A.17 `agent/capabilities/builtin/edit_tools.py`

- 类型：Python
- 行数：604
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：文本编辑工具组：replace_in_file / apply_patch / read_write——预览 + 统一提交执行器。
- 导入：`__future__`, `re`, `pathlib`, `typing`, `agent.capabilities.registry`, `agent.mechanisms.file_safety`, `agent.mechanisms.quality`
- 顶层符号：
  - L34: `def _read_text(target)`
  - L39: `def _required_file(arguments, key)`
  - L50: `def _required_dir(arguments, key)`
  - L64: `def _apply_one_literal(text, old_text, new_text, replace_all, expected, index)`
  - L104: `def _apply_edits(text, edits)`
  - L149: `def _reject_conflicting_edits_keys(arguments)`
  - L164: `def _apply_replace(text, arguments)`
  - L243: `class ReplaceInFileTool(ToolPlugin)`
  - L320: `def _hunk_usage(hunk)`
  - L328: `def _parse_patch(patch_text)`
  - L391: `def _resolve_patch_target(root, patch_path)`
  - L408: `def _apply_hunks(text, hunks)`
  - L425: `class ApplyPatchTool(ToolPlugin)`
  - L465: `def _slice_lines(text, arguments)`
  - L482: `class ReadWriteTool(ToolPlugin)`
  - L528: `def _execute_replace(backups, arguments)`
  - L546: `def _execute_patch(backups, arguments)`
  - L567: `def _execute_read_write(backups, arguments)`
  - L592: `def build_plugins()`
  - L597: `def build_executors(backups)`
- 类成员：
  - L277: `ReplaceInFileTool.execute(self, arguments)`
  - L440: `ApplyPatchTool.execute(self, arguments)`
  - L500: `ReadWriteTool.execute(self, arguments)`

### A.18 `agent/capabilities/builtin/fs_tools.py`

- 类型：Python
- 行数：481
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：文件系统工具组：delete_file / file_ops / file_undo——预览 + 统一提交执行器。
- 导入：`__future__`, `shutil`, `pathlib`, `typing`, `agent.capabilities.registry`, `agent.common.status`, `agent.mechanisms.file_safety`, `agent.mechanisms.quality`
- 顶层符号：
  - L36: `def norm_path(value)`
  - L41: `def _files_same(a, b)`
  - L51: `def _remove_path(target)`
  - L62: `class DeleteFileTool(ToolPlugin)`
  - L116: `def _parse_on_exists(arguments)`
  - L123: `def _terminal()`
  - L148: `def _ops_fail()`
  - L179: `def _plan_delete(action, source, recursive, on_exists)`
  - L193: `def _plan_destination(action, source, dest, recursive, on_exists)`
  - L229: `def _plan_ops(arguments)`
  - L247: `class FileOpsTool(ToolPlugin)`
  - L302: `class FileUndoTool(ToolPlugin)`
  - L381: `def _execute_delete(recycle, arguments)`
  - L401: `def _execute_ops(recycle, arguments)`
  - L435: `def _execute_undo(backups, arguments)`
  - L467: `def build_plugins(backups, recycle)`
  - L472: `def build_executors(backups, recycle)`
- 类成员：
  - L80: `DeleteFileTool.__init__(self, recycle)`
  - L83: `DeleteFileTool.execute(self, arguments)`
  - L275: `FileOpsTool.execute(self, arguments)`
  - L318: `FileUndoTool.__init__(self, backups)`
  - L321: `FileUndoTool.execute(self, arguments)`

### A.19 `agent/capabilities/builtin/geo_weather_tools.py`

- 类型：Python
- 行数：410
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：网络查询族工具：ip_geolocate / open_meteo_weather。
- 导入：`__future__`, `ipaddress`, `json`, `re`, `urllib.error`, `urllib.parse`, `urllib.request`, `typing`, `agent.capabilities.registry`, `agent.core.error_report`
- 顶层符号：
  - L46: `class GeoServiceError(RuntimeError)`
  - L54: `def _http_json(url, timeout_sec, user_agent)`
  - L61: `def _normalize_ip_for_lookup(ip_raw)`
  - L79: `def _resolve_timeout(raw, default)`
  - L87: `def _normalize_name(s)`
  - L91: `def _has_cjk(s)`
  - L95: `def _score_geo_result(query, hit)`
  - L127: `def _pick_geo_result(query, js)`
  - L138: `def _lookup_ip_region(ip_for_lookup, timeout_sec)`
  - L148: `def _wmo_zh(code)`
  - L177: `class IpGeolocateTool(ToolPlugin)`
  - L246: `class OpenMeteoWeatherTool(ToolPlugin)`
  - L407: `def build_plugins()`
- 类成员：
  - L49: `GeoServiceError.__init__(self, message)`
  - L189: `IpGeolocateTool.execute(self, arguments)`
  - L262: `OpenMeteoWeatherTool._forecast_days(self, value)`
  - L269: `OpenMeteoWeatherTool._resolve_location(self, location, latitude, longitude, ip, tsec)`
  - L326: `OpenMeteoWeatherTool._summary(name_used, admin1, country, note, lat, lon, cur, daily, days)`
  - L356: `OpenMeteoWeatherTool._run_core(self)`
  - L386: `OpenMeteoWeatherTool.execute(self, arguments)`

### A.20 `agent/capabilities/builtin/glob_files.py`

- 类型：Python
- 行数：129
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：glob_files 工具：按模式列出路径。
- 导入：`__future__`, `fnmatch`, `os`, `pathlib`, `typing`, `agent.capabilities.builtin.scan_scope`, `agent.capabilities.registry`
- 顶层符号：
  - L17: `def _matches(rel, pattern)`
  - L26: `def _candidates(root, pattern, recursive, skip_names, skipped)`
  - L55: `class GlobFilesTool(ToolPlugin)`
  - L126: `def build()`
- 类成员：
  - L83: `GlobFilesTool.execute(self, arguments)`

### A.21 `agent/capabilities/builtin/grep_files.py`

- 类型：Python
- 行数：142
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：grep_files 工具：目录内文本内容搜索（字面含 | 分隔 / 正则）。
- 导入：`__future__`, `os`, `re`, `pathlib`, `typing`, `agent.capabilities.builtin.scan_scope`, `agent.capabilities.registry`, `agent.core.error_report`
- 顶层符号：
  - L18: `def _iter_text_files(root, skip_names, skipped)`
  - L45: `def _compile_pattern(pattern, regex, ignore_case)`
  - L56: `class GrepFilesTool(ToolPlugin)`
  - L139: `def build()`
- 类成员：
  - L82: `GrepFilesTool.execute(self, arguments)`

### A.22 `agent/capabilities/builtin/image_tool.py`

- 类型：Python
- 行数：199
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：读图工具：read_image —— 把本地图片作为图片附件回灌给模型。
- 导入：`__future__`, `base64`, `pathlib`, `typing`, `agent.capabilities.registry`, `agent.core.context`, `agent.core.event_name`, `agent.core.image_embed`, `agent.core.input_attachments`, `agent.core.session_scope`, `agent.core.tool_call`
- 顶层符号：
  - L46: `class ImageReadTool(ToolPlugin)`
  - L196: `def build_plugins()`
- 类成员：
  - L69: `ImageReadTool._session_events(self)`
  - L88: `ImageReadTool._already_read(self, ident)`
  - L105: `ImageReadTool._bytes_from_attachment(self, ident)`
  - L131: `ImageReadTool._load_source(self, arguments)`
  - L148: `ImageReadTool._payload(self, raw, declared_mime, shown_path, label, max_side)`
  - L185: `ImageReadTool.execute(self, arguments)`

### A.23 `agent/capabilities/builtin/locate_tools.py`

- 类型：Python
- 行数：549
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：定位族工具：find_in_file / regex_locate / file_search。
- 导入：`__future__`, `fnmatch`, `os`, `re`, `pathlib`, `typing`, `agent.capabilities.builtin.scan_scope`, `agent.capabilities.registry`, `agent.core.error_report`
- 顶层符号：
  - L22: `def _read_text(fp, encoding)`
  - L35: `def _span_to_rowcols(full, s, e)`
  - L44: `def _collect_spans(full, pattern)`
  - L73: `def _collect_source_files(root, glob_pattern, recursive)`
  - L86: `def _iter_source_files(root, glob_pattern, recursive, skip_names, skipped)`
  - L124: `class FindInFileTool(ToolPlugin)`
  - L201: `class RegexLocateTool(ToolPlugin)`
  - L294: `class FileSearchTool(ToolPlugin)`
  - L546: `def build_plugins()`
- 类成员：
  - L143: `FindInFileTool.execute(self, arguments)`
  - L222: `RegexLocateTool.execute(self, arguments)`
  - L326: `FileSearchTool._load_gitignore(self, root)`
  - L360: `FileSearchTool._is_ignored(rel_path, ignore_patterns)`
  - L365: `FileSearchTool._detect_encoding(path)`
  - L381: `FileSearchTool._search_file(self, path, pattern, context_lines, limit)`
  - L424: `FileSearchTool._search_tree(self, target, compiled, context_lines, limit, arguments, exclude)`
  - L471: `FileSearchTool.execute(self, arguments)`

### A.24 `agent/capabilities/builtin/ocr_tool.py`

- 类型：Python
- 行数：219
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：OCR 工具：image_ocr——pytesseract / easyocr（可选依赖，缺依赖结构化降级）。
- 导入：`__future__`, `importlib.util`, `pathlib`, `typing`, `agent.capabilities.registry`, `agent.core.error_report`
- 顶层符号：
  - L17: `class MissingDependency(RuntimeError)`
  - L39: `class OcrError(RuntimeError)`
  - L43: `def _available(module)`
  - L48: `class ImageOcrTool(ToolPlugin)`
  - L216: `def build_plugins()`
- 类成员：
  - L20: `MissingDependency.__init__(self, message, install_command, estimated_time, security_notes)`
  - L63: `ImageOcrTool._detect_engine(prefer)`
  - L76: `ImageOcrTool._ocr_pytesseract(image_path, lang, region)`
  - L123: `ImageOcrTool._ocr_easyocr(image_path, lang, region)`
  - L174: `ImageOcrTool.execute(self, arguments)`

### A.25 `agent/capabilities/builtin/present_tool.py`

- 类型：Python
- 行数：92
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：present 工具：把已有文件展示为对话区文件卡片。
- 导入：`__future__`, `mimetypes`, `pathlib`, `typing`, `agent.capabilities.registry`
- 顶层符号：
  - L25: `def _kind(path)`
  - L29: `def _file_entry(raw)`
  - L54: `class PresentTool(ToolPlugin)`
  - L89: `def build()`
- 类成员：
  - L79: `PresentTool.execute(self, arguments)`

### A.26 `agent/capabilities/builtin/read_file.py`

- 类型：Python
- 行数：74
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：read_file 工具：读取文本文件（支持行区间与截断）。
- 导入：`__future__`, `pathlib`, `typing`, `agent.capabilities.registry`
- 顶层符号：
  - L13: `class ReadFileTool(ToolPlugin)`
  - L71: `def build()`
- 类成员：
  - L31: `ReadFileTool.execute(self, arguments)`

### A.27 `agent/capabilities/builtin/review_conclusion.py`

- 类型：Python
- 行数：86
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：review_conclusion：写盘后 review 提交 / 预览解锁 / 预览取消。
- 导入：`__future__`, `typing`, `agent.capabilities.registry`, `agent.capabilities.session_gate`
- 顶层符号：
  - L16: `class ReviewConclusionTool(ToolPlugin)`
  - L83: `def build()`
- 类成员：
  - L38: `ReviewConclusionTool.execute(self, arguments)`

### A.28 `agent/capabilities/builtin/scan_scope.py`

- 类型：Python
- 行数：56
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：搜索范围：默认剪枝目录 + 调用方自定的排除名单（grep_files / file_search 共用）。
- 导入：`__future__`, `pathlib`, `typing`
- 顶层符号：
  - L21: `def exclude_names(extra)`
  - L31: `def skip_set(include_derived, exclude)`
  - L43: `def relative_parts(path, root)`
  - L51: `def should_skip(path, root, include_derived, exclude)`

### A.29 `agent/capabilities/builtin/session_tools.py`

- 类型：Python
- 行数：493
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：会话协作工具组：Agent 间互发消息、群发、创建与列表。
- 导入：`__future__`, `time`, `typing`, `agent.capabilities.registry`, `agent.common.status`, `agent.core.error_report`, `agent.core.session_scope`, `agent.mechanisms.mesh`, `agent.mechanisms.session_store`
- 顶层符号：
  - L43: `def _parse_bool(value)`
  - L54: `def _normalize_role(role)`
  - L66: `def _normalize_target_ids(raw)`
  - L76: `def _normalize_tags(raw)`
  - L85: `def _sender_fields(mesh, src_cid)`
  - L97: `def _build_peer_message(mesh, src_cid, message)`
  - L137: `def _deliver(mesh, src_cid, target_id, message)`
  - L186: `class SessionSendTool(ToolPlugin)`
  - L218: `class SessionMultisendTool(ToolPlugin)`
  - L288: `class SessionBroadcastTool(ToolPlugin)`
  - L357: `class SessionCreateTool(ToolPlugin)`
  - L455: `class SessionListTool(ToolPlugin)`
  - L484: `def build_plugins(mesh)`
- 类成员：
  - L202: `SessionSendTool.__init__(self, mesh)`
  - L205: `SessionSendTool.execute(self, arguments)`
  - L234: `SessionMultisendTool.__init__(self, mesh)`
  - L237: `SessionMultisendTool.execute(self, arguments)`
  - L305: `SessionBroadcastTool.__init__(self, mesh)`
  - L308: `SessionBroadcastTool.execute(self, arguments)`
  - L373: `SessionCreateTool.__init__(self, mesh)`
  - L376: `SessionCreateTool._pick_name(self, scope_tags)`
  - L398: `SessionCreateTool.execute(self, arguments)`
  - L464: `SessionListTool.__init__(self, mesh)`
  - L467: `SessionListTool.execute(self, arguments)`

### A.30 `agent/capabilities/builtin/subagent_tools.py`

- 类型：Python
- 行数：129
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：父子智能体工具：创建、列表、状态、发送与子会话回父。
- 导入：`__future__`, `typing`, `agent.capabilities.registry`, `agent.core.session_scope`, `agent.subagent.manager`, `agent.subagent.models`
- 顶层符号：
  - L25: `class SubagentTool(ToolPlugin)`
  - L95: `class SubagentSendTool(ToolPlugin)`
  - L127: `def build(manager)`
- 类成员：
  - L55: `SubagentTool.__init__(self, manager)`
  - L58: `SubagentTool.execute(self, arguments)`
  - L110: `SubagentSendTool.__init__(self, manager)`
  - L113: `SubagentSendTool.execute(self, arguments)`

### A.31 `agent/capabilities/builtin/system_tools.py`

- 类型：Python
- 行数：581
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：系统与环境工具：env_probe / unified_diagnose / git_workspace。
- 导入：`__future__`, `ast`, `json`, `re`, `shutil`, `subprocess`, `sys`, `pathlib`, `typing`, `agent.capabilities.registry`, `agent.core.error_report`
- 顶层符号：
  - L32: `class DiagnosticsFailed(RuntimeError)`
  - L40: `class GitWorkspaceError(RuntimeError)`
  - L55: `def _read_text_any(path, encoding)`
  - L68: `class EnvProbeTool(ToolPlugin)`
  - L113: `class UnifiedDiagnoseTool(ToolPlugin)`
  - L328: `class GitWorkspaceTool(ToolPlugin)`
  - L578: `def build_plugins()`
- 类成员：
  - L35: `DiagnosticsFailed.__init__(self, message, data)`
  - L43: `GitWorkspaceError.__init__(self, message)`
  - L77: `EnvProbeTool.execute(self, arguments)`
  - L130: `UnifiedDiagnoseTool._collect_py_files(root, glob_pattern, limit)`
  - L147: `UnifiedDiagnoseTool._severity_for_ruff(code, message)`
  - L156: `UnifiedDiagnoseTool._syntax_diagnostics(self, files, encoding)`
  - L195: `UnifiedDiagnoseTool._run_ruff_json(self, root, timeout)`
  - L260: `UnifiedDiagnoseTool._dedupe(items)`
  - L274: `UnifiedDiagnoseTool.execute(self, arguments)`
  - L347: `GitWorkspaceTool._run_git(cwd)`
  - L364: `GitWorkspaceTool._truncate(s, max_chars)`
  - L370: `GitWorkspaceTool._ensure_repo(root)`
  - L377: `GitWorkspaceTool._resolve_under_root(root, rel)`
  - L386: `GitWorkspaceTool._mode_worktree(self, root, max_chars)`
  - L420: `GitWorkspaceTool._mode_log(self, root, max_n)`
  - L440: `GitWorkspaceTool._mode_blame(self, root, rel_path, start_line, end_line)`
  - L488: `GitWorkspaceTool._mode_show(self, root, ref, max_chars)`
  - L529: `GitWorkspaceTool.execute(self, arguments)`

### A.32 `agent/capabilities/builtin/text_data_tools.py`

- 类型：Python
- 行数：316
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：文本与数据工具：text_diff / data_table。
- 导入：`__future__`, `csv`, `difflib`, `io`, `json`, `re`, `pathlib`, `typing`, `agent.capabilities.registry`, `agent.core.error_report`
- 顶层符号：
  - L21: `def _read_text_auto(fp, encoding)`
  - L34: `class TextDiffTool(ToolPlugin)`
  - L120: `class DataTableTool(ToolPlugin)`
  - L313: `def build_plugins()`
- 类成员：
  - L50: `TextDiffTool._side_from_file_or_text(self, file_arg, text_arg)`
  - L69: `TextDiffTool._label_for_side(file_arg, kind)`
  - L77: `TextDiffTool.execute(self, arguments)`
  - L141: `DataTableTool._load_csv(path)`
  - L147: `DataTableTool._load_excel(path, sheet)`
  - L171: `DataTableTool._detect_format(path)`
  - L181: `DataTableTool._load_table(self, path, sheet)`
  - L191: `DataTableTool._do_preview(rows, limit)`
  - L198: `DataTableTool._do_filter(rows, col, val, regex)`
  - L205: `DataTableTool._do_sort(rows, col, desc)`
  - L218: `DataTableTool._do_stats(rows, col)`
  - L235: `DataTableTool.execute(self, arguments)`

### A.33 `agent/capabilities/builtin/web_tools.py`

- 类型：Python
- 行数：352
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：网络工具：web_fetch / web_fetch_render。
- 导入：`__future__`, `html`, `re`, `time`, `urllib.error`, `urllib.parse`, `urllib.request`, `pathlib`, `typing`, `agent.capabilities.registry`, `agent.core.error_report`
- 顶层符号：
  - L32: `class WebFetchError(RuntimeError)`
  - L50: `def _strip_html_to_text(raw_html)`
  - L65: `def _parse_keywords(raw)`
  - L76: `def _ascii_safe_url(url)`
  - L103: `def _fetch_url(url, timeout_sec, max_chars, user_agent)`
  - L145: `def _run_hard_checks(text)`
  - L163: `class WebFetchTool(ToolPlugin)`
  - L261: `class WebFetchRenderTool(ToolPlugin)`
  - L329: `def build_plugins()`
  - L334: `def build_executors()`
- 类成员：
  - L35: `WebFetchError.__init__(self, message)`
  - L184: `WebFetchTool.execute(self, arguments)`
  - L274: `WebFetchRenderTool.execute(self, arguments)`

### A.34 `agent/capabilities/builtin/write_file.py`

- 类型：Python
- 行数：125
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：写文件工具组（预览与提交为两个独立入口）。
- 导入：`__future__`, `pathlib`, `typing`, `agent.capabilities.registry`, `agent.common.status`, `agent.mechanisms.file_safety`, `agent.mechanisms.quality`
- 顶层符号：
  - L21: `class WriteFileTool(ToolPlugin)`
  - L92: `def build()`
  - L97: `def build_executors(backups)`
- 类成员：
  - L41: `WriteFileTool.execute(self, arguments)`

### A.35 `agent/capabilities/contributions.py`

- 类型：Python
- 行数：197
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：插件贡献注册表：插件向壳层暴露 HTTP 端点的落点。
- 导入：`__future__`, `re`, `dataclasses`, `typing`
- 顶层符号：
  - L19: `class ContributionError(ValueError)`
  - L24: `class Route()`
  - L69: `def _reject_absolute(raw, what)`
  - L83: `def _clean_segment(raw, what)`
  - L96: `def _clean_path_segments(raw)`
  - L126: `class ContributionRegistry()`
- 类成员：
  - L37: `Route.full_path(self)`
  - L41: `Route.segments(self)`
  - L45: `Route.match_segments(self, segments)`
  - L65: `Route.as_dict(self)`
  - L134: `ContributionRegistry.add_route(self, plugin, method, path, handler)`
  - L159: `ContributionRegistry.match(self, method, url_path)`
  - L181: `ContributionRegistry.routes_of(self, plugin)`
  - L184: `ContributionRegistry.all_routes(self)`
  - L189: `ContributionRegistry.drop_plugin(self, plugin)`

### A.36 `agent/capabilities/model_catalog.py`

- 类型：Python
- 行数：283
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：模型目录：跨厂商的模型描述注册表 + provider 缓存。
- 导入：`__future__`, `json`, `sys`, `threading`, `dataclasses`, `typing`, `agent.capabilities.contributions`, `agent.core.error_report`, `agent.mechanisms.provider_registry`, `agent.mechanisms.providers.base`
- 顶层符号：
  - L34: `class ModelEntry()`
  - L106: `class CatalogSnapshot()`
  - L122: `def _warn(message)`
  - L126: `class ModelCatalog()`
- 类成员：
  - L48: `ModelEntry.from_options(cls)`
  - L73: `ModelEntry.options(self)`
  - L83: `ModelEntry.context_window(self)`
  - L91: `ModelEntry.compression_percent(self)`
  - L114: `CatalogSnapshot.entry(self, model_id)`
  - L129: `ModelCatalog.__init__(self)`
  - L144: `ModelCatalog.set_source(self, source, entries)`
  - L168: `ModelCatalog._drop_source(self, source, generation)`
  - L179: `ModelCatalog._normalize(self, source, entries)`
  - L213: `ModelCatalog.snapshot(self)`
  - L262: `ModelCatalog.ids(self)`
  - L265: `ModelCatalog.default_id(self)`
  - L268: `ModelCatalog.provider_for(self, model_id)`

### A.37 `agent/capabilities/path_registry.py`

- 类型：Python
- 行数：179
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：插件路径注册表：插口协议、注册项和生命周期清理。
- 导入：`__future__`, `re`, `dataclasses`, `typing`
- 顶层符号：
  - L14: `class PathRegistryError(ValueError)`
  - L18: `def split_path(path)`
  - L31: `def match_pattern(pattern, path)`
  - L50: `class PathSlot()`
  - L70: `class PathEntry()`
  - L87: `class PathRegistry()`
- 类成员：
  - L58: `PathSlot.as_dict(self)`
  - L77: `PathEntry.as_dict(self)`
  - L91: `PathRegistry.add_slot(self, pattern)`
  - L115: `PathRegistry._parent_slot(self, path)`
  - L125: `PathRegistry.validate(self, path)`
  - L141: `PathRegistry.register(self, path)`
  - L157: `PathRegistry.get(self, path)`
  - L163: `PathRegistry.catalog(self)`
  - L169: `PathRegistry.drop_owner(self, owner)`

### A.38 `agent/capabilities/plugin_context.py`

- 类型：Python
- 行数：395
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：插件注册面——插件 `register(ctx)` 拿到的那个对象。
- 导入：`__future__`, `re`, `pathlib`, `typing`, `agent.capabilities.plugin_ledger`, `agent.capabilities.plugin_ui_context`, `agent.capabilities.registry`, `agent.capabilities.slot_registry`, `agent.core.app_path`, `agent.core.context`, `agent.core.error_report`, `agent.core.slot`
- 顶层符号：
  - L28: `def _safe_dir_name(name)`
  - L37: `class PluginContext(PluginUiContextMixin)`
- 类成员：
  - L40: `PluginContext.__init__(self, name, registry, event_bus, context_sources, pipeline, host, contributions, executors, model_catalog, settings, ui, backend, prompt_tail, prompt_sections, context_hooks, tree)`
  - L79: `PluginContext.set_rank(self, rank)`
  - L83: `PluginContext.owned_disposers(self)`
  - L87: `PluginContext.own_disposer(self, disposer)`
  - L92: `PluginContext._contribute(self, path, register)`
  - L131: `PluginContext._backend_path(self, path, kind, handler, metadata)`
  - L144: `PluginContext.set_subagent_tools(self, tools)`
  - L158: `PluginContext.subscribe(self, event_type, handler)`
  - L176: `PluginContext.add_context_source(self, fn, meta)`
  - L201: `PluginContext.add_mode_tail(self, fn)`
  - L220: `PluginContext.add_prompt_section(self, section, fn)`
  - L240: `PluginContext.bump_context_sources(self)`
  - L252: `PluginContext._source_meta(self, meta)`
  - L281: `PluginContext.add_pre_gate(self, fn)`
  - L298: `PluginContext.add_post_observer(self, fn)`
  - L317: `PluginContext.is_subagent(self, conversation_id)`
  - L328: `PluginContext.app(self)`
  - L337: `PluginContext.data_dir(self)`
  - L358: `PluginContext._contrib(self)`
  - L365: `PluginContext.publish_event(self, event, payload)`
  - L378: `PluginContext.resume_suspended(self, conversation_id, call_id, data)`

### A.39 `agent/capabilities/plugin_ledger.py`

- 类型：Python
- 行数：56
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：插件贡献账本——一次装载期间登记的可撤销动作。
- 导入：`__future__`, `typing`, `agent.core.error_report`
- 顶层符号：
  - L18: `def flatten_disposers(returned)`
  - L32: `def merge_disposers(owned, returned)`
  - L49: `def dispose_in_reverse(disposers, source)`

### A.40 `agent/capabilities/plugin_paths.py`

- 类型：Python
- 行数：18
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：插件 UI/设置路径清单：只保存路径，不保存实现。
- 导入：`__future__`, `json`, `pathlib`, `typing`
- 顶层符号：
  - L10: `def load_plugin_paths(plugin_file)`

### A.41 `agent/capabilities/plugin_settings_tree.py`

- 类型：Python
- 行数：37
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：插件设置子树：面板、条目与 UI 按钮由 JSON 描述。
- 导入：`__future__`, `json`, `pathlib`, `typing`
- 顶层符号：
  - L10: `def register_settings_tree(ctx, path, load, save)`

### A.42 `agent/capabilities/plugin_ui_context.py`

- 类型：Python
- 行数：228
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：插件 UI、设置、路由与执行器贡献方法。
- 导入：`__future__`, `typing`, `agent.capabilities.plugin_ledger`, `agent.capabilities.registry`, `agent.capabilities.slot_registry`, `agent.core.app_path`, `agent.core.error_report`
- 顶层符号：
  - L18: `class PluginUiContextMixin()`
- 类成员：
  - L21: `PluginUiContextMixin.add_executor(self, name, fn)`
  - L41: `PluginUiContextMixin.register_tool(self, plugin)`
  - L57: `PluginUiContextMixin.set_runtime(self, runtime)`
  - L73: `PluginUiContextMixin.add_route(self, method, path, handler)`
  - L100: `PluginUiContextMixin.add_context_assembly_hook(self, fn)`
  - L121: `PluginUiContextMixin.add_settings_panel(self, panel_id, title)`
  - L136: `PluginUiContextMixin.add_settings_item(self, parent, item_id)`
  - L155: `PluginUiContextMixin.add_ui_slot(self, path)`
  - L171: `PluginUiContextMixin.bind(self, path, implementation)`
  - L185: `PluginUiContextMixin.bind_route(self, method, path, implementation)`
  - L197: `PluginUiContextMixin.add_ui_item(self, path)`
  - L211: `PluginUiContextMixin.add_model_catalog(self, entries)`

### A.43 `agent/capabilities/plugin_ui_tree.py`

- 类型：Python
- 行数：38
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：插件 UI 子树：把 JSON 节点注册到 UI PathRegistry。
- 导入：`__future__`, `json`, `pathlib`, `typing`, `agent.core.app_path`
- 顶层符号：
  - L12: `def register_ui_tree(ctx, path)`

### A.44 `agent/capabilities/plugins.py`

- 类型：Python
- 行数：476
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：插件加载器与宿主——插件装卸的落点。
- 导入：`__future__`, `hashlib`, `importlib.util`, `json`, `re`, `sys`, `dataclasses`, `pathlib`, `types`, `typing`, `agent.capabilities.backend_paths`, `agent.capabilities.path_registry`, `agent.capabilities.plugin_context`, `agent.capabilities.plugin_ledger`, `agent.capabilities.registry`, `agent.capabilities.settings_registry`, `agent.capabilities.ui_registry`, `agent.common.status`, `agent.config`, `agent.core.error_report`
- 顶层符号：
  - L52: `def resolve_plugin_root(plugins_dir, name, path_raw)`
  - L83: `def plugin_config_fields(plugin_root)`
  - L113: `def _plugin_meta(root)`
  - L127: `def _valid_plugin_name(name)`
  - L135: `def _within_plugins_tree(plugins_dir, root)`
  - L144: `def _entry_integrity(entry)`
  - L168: `class PluginInfo()`
  - L176: `class LoadReport()`
  - L187: `class PluginHost()`
  - L454: `def _drop_plugin_modules(mod_name)`
  - L462: `def _ensure_parent_package(plugins_dir)`
- 类成员：
  - L183: `LoadReport.__post_init__(self)`
  - L190: `PluginHost.__init__(self, plugins_dir, registry, event_bus, context_sources, pipeline, contributions, plugin_data_root, executors, model_catalog, prompt_tail, prompt_sections, context_hooks, slots, tree, backend_slots)`
  - L231: `PluginHost.plugins_dir(self)`
  - L235: `PluginHost.plugin_root(self, name)`
  - L239: `PluginHost.resolve_plugin_root(self, name, path_raw)`
  - L244: `PluginHost.contributions(self)`
  - L250: `PluginHost.register_runtime(self, name, runtime)`
  - L256: `PluginHost.runtime(self, name, default)`
  - L266: `PluginHost.discover(self)`
  - L285: `PluginHost.load_manifest(self, entries)`
  - L327: `PluginHost.load_enabled(self, enabled)`
  - L350: `PluginHost._load_one(self, info, rank, root)`
  - L414: `PluginHost.unload(self, name)`
  - L438: `PluginHost.unload_all(self)`
  - L445: `PluginHost.loaded_names(self)`
  - L449: `PluginHost.reports(self)`

### A.45 `agent/capabilities/registry.py`

- 类型：Python
- 行数：204
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：工具协议与注册表（ToolPlugin / ToolRegistry）— 能力层注册制地基。
- 导入：`__future__`, `typing`
- 顶层符号：
  - L23: `class ToolPlugin()`
  - L53: `class ToolRegistryView()`
  - L83: `class ToolRegistry()`
- 类成员：
  - L48: `ToolPlugin.execute(self, arguments)`
  - L56: `ToolRegistryView.__init__(self, base, excluded)`
  - L67: `ToolRegistryView._allowed(self, name)`
  - L73: `ToolRegistryView.get(self, name)`
  - L76: `ToolRegistryView.names(self)`
  - L79: `ToolRegistryView.schemas(self)`
  - L86: `ToolRegistry.__init__(self)`
  - L92: `ToolRegistry.subagent_hidden(self)`
  - L101: `ToolRegistry.set_subagent_tools(self, owner, tools)`
  - L118: `ToolRegistry.register(self, plugin)`
  - L146: `ToolRegistry.drop_owner(self, owner)`
  - L164: `ToolRegistry.get(self, name)`
  - L168: `ToolRegistry.names(self)`
  - L172: `ToolRegistry.schemas(self)`
  - L184: `ToolRegistry.display_list(self)`
  - L199: `ToolRegistry.dispose_all(self)`

### A.46 `agent/capabilities/session_gate.py`

- 类型：Python
- 行数：20
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：工具侧读取当前会话门控的唯一入口。
- 导入：`__future__`, `agent.mechanisms.quality`
- 顶层符号：
  - L8: `def session_gate()`

### A.47 `agent/capabilities/settings_registry.py`

- 类型：Python
- 行数：316
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：插件系统设置注册表：面板、条目、读取与保存回调。
- 导入：`__future__`, `dataclasses`, `typing`, `agent.capabilities.slot_registry`, `agent.core.error_report`
- 顶层符号：
  - L30: `class SettingsRegistryError(ValueError)`
  - L34: `def _segment(raw, what)`
  - L41: `def _panel_id(raw)`
  - L53: `def _item_id(parent, item)`
  - L59: `class SettingsPanel()`
  - L71: `class SettingsItem()`
  - L99: `class SettingsRegistry()`
  - L304: `def seed_default_panels(registry)`
- 类成员：
  - L65: `SettingsPanel.as_dict(self)`
  - L84: `SettingsItem.as_dict(self)`
  - L106: `SettingsRegistry.add_panel(self, owner, panel_id, title)`
  - L127: `SettingsRegistry._active_item(self, path)`
  - L134: `SettingsRegistry.add_item(self, owner, parent, item_id)`
  - L200: `SettingsRegistry.panels_in_order(self)`
  - L203: `SettingsRegistry.items_of(self, panel_id)`
  - L209: `SettingsRegistry.item(self, item_id)`
  - L215: `SettingsRegistry.values(self)`
  - L227: `SettingsRegistry.save(self, values)`
  - L282: `SettingsRegistry.drop_plugin(self, owner)`

### A.48 `agent/capabilities/slot_registry.py`

- 类型：Python
- 行数：495
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：插口树：路径节点、绑定、解析和回退。
- 导入：`__future__`, `threading`, `contextlib`, `contextvars`, `dataclasses`, `functools`, `typing`, `agent.capabilities.path_registry`, `agent.core.app_path`
- 顶层符号：
  - L16: `class SlotRegistryError(ValueError)`
  - L26: `def _locked(method)`
  - L38: `def canonical_slot_path(path)`
  - L56: `def route_slot_path(method, path)`
  - L62: `def normalize_slot_path(path)`
  - L67: `def _normalize_path(path)`
  - L71: `def _mode(value)`
  - L79: `class SlotSpec()`
  - L141: `class Binding()`
  - L165: `def _binding_dict(binding)`
  - L179: `def _implementation_name(value)`
  - L189: `class SlotSnapshot()`
  - L215: `class SlotRegistry()`
- 类成员：
  - L96: `SlotSpec.clone(self)`
  - L115: `SlotSpec.as_dict(self)`
  - L154: `Binding.dispose(self)`
  - L158: `Binding.__call__(self)`
  - L161: `Binding.as_dict(self)`
  - L197: `SlotSnapshot.contains(self, path)`
  - L200: `SlotSnapshot.resolve(self, path)`
  - L206: `SlotSnapshot.resolve_items(self, path)`
  - L223: `SlotRegistry.register_slot(self, path)`
  - L275: `SlotRegistry.bind(self, path, implementation)`
  - L329: `SlotRegistry.unbind(self, binding)`
  - L339: `SlotRegistry.drop_owner(self, owner)`
  - L349: `SlotRegistry.node(self, path)`
  - L357: `SlotRegistry.bindings_of(self, path)`
  - L360: `SlotRegistry._ordered(self, node)`
  - L364: `SlotRegistry.active_binding(self, path)`
  - L370: `SlotRegistry.resolve_base(self, path)`
  - L398: `SlotRegistry.resolve(self, path)`
  - L405: `SlotRegistry.resolve_items(self, path)`
  - L425: `SlotRegistry._subtree_override(self, path)`
  - L444: `SlotRegistry.freeze(self)`
  - L457: `SlotRegistry.execution_snapshot(self)`
  - L465: `SlotRegistry._current_snapshot(self)`
  - L471: `SlotRegistry.snapshot_contains(self, path)`
  - L477: `SlotRegistry.describe(self)`
  - L485: `SlotRegistry.transaction(self)`

### A.49 `agent/capabilities/tasks/__init__.py`

- 类型：Python
- 行数：26
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：任务与目标工具。
- 导入：`__future__`, `typing`, `agent.capabilities.registry`, `agent.capabilities.tasks.confirm`, `agent.capabilities.tasks.goal`, `agent.capabilities.tasks.run_type`, `agent.capabilities.tasks.todo`, `agent.capabilities.tasks.wake`, `agent.mechanisms.live_state`
- 顶层符号：
  - L16: `def build_plugins(live_state)`

### A.50 `agent/capabilities/tasks/common.py`

- 类型：Python
- 行数：72
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：任务工具共享异常与参数校验。
- 导入：`__future__`, `typing`
- 顶层符号：
  - L8: `class UserConfirmRequired(Exception)`
  - L32: `class ApprovalRequired(Exception)`
  - L50: `def approval_text(raw, name, limit)`
  - L62: `def normalize_confirms(raw)`
- 类成员：
  - L17: `UserConfirmRequired.__init__(self, title, confirms, multi, custom_option_index)`
  - L40: `ApprovalRequired.__init__(self, option_id, option_desc)`

### A.51 `agent/capabilities/tasks/confirm.py`

- 类型：Python
- 行数：78
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：用户确认与审批工具。
- 导入：`__future__`, `typing`, `agent.capabilities.registry`, `agent.capabilities.tasks.common`
- 顶层符号：
  - L16: `class UserConfirmTool(ToolPlugin)`
  - L53: `class ApprovalConfirmTool(ToolPlugin)`
- 类成员：
  - L33: `UserConfirmTool.execute(self, arguments)`
  - L74: `ApprovalConfirmTool.execute(self, arguments)`

### A.52 `agent/capabilities/tasks/goal.py`

- 类型：Python
- 行数：90
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：goal 工具。
- 导入：`__future__`, `typing`, `agent.capabilities.registry`, `agent.common.status`, `agent.core.session_scope`, `agent.mechanisms.live_state`
- 顶层符号：
  - L13: `class GoalTool(ToolPlugin)`
- 类成员：
  - L45: `GoalTool.__init__(self, live_state)`
  - L48: `GoalTool.execute(self, arguments)`

### A.53 `agent/capabilities/tasks/run_type.py`

- 类型：Python
- 行数：37
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：run_type 工具。
- 导入：`__future__`, `typing`, `agent.capabilities.registry`, `agent.common.status`, `agent.core.session_scope`, `agent.mechanisms.live_state`
- 顶层符号：
  - L13: `class RunTypeTool(ToolPlugin)`
- 类成员：
  - L24: `RunTypeTool.__init__(self, live_state)`
  - L27: `RunTypeTool.execute(self, arguments)`

### A.54 `agent/capabilities/tasks/todo.py`

- 类型：Python
- 行数：179
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：Todo 清单工具。
- 导入：`__future__`, `uuid`, `typing`, `agent.capabilities.registry`, `agent.core.session_scope`, `agent.mechanisms.live_state`
- 顶层符号：
  - L13: `class TodoListTool(ToolPlugin)`
- 类成员：
  - L31: `TodoListTool.__init__(self, live_state)`
  - L35: `TodoListTool._progress(items)`
  - L47: `TodoListTool._normalize_items(parsed)`
  - L61: `TodoListTool._as_int_list(value, label)`
  - L80: `TodoListTool._execute_check(self, cid, todo, action, arguments)`
  - L96: `TodoListTool._execute_add_item(self, cid, todo, arguments)`
  - L116: `TodoListTool._execute_remove_replace(self, cid, todo, action, arguments)`
  - L137: `TodoListTool.execute(self, arguments)`

### A.55 `agent/capabilities/tasks/wake.py`

- 类型：Python
- 行数：117
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：唤醒调度工具：注册、取消、查询，不在工具内等待。
- 导入：`__future__`, `typing`, `agent.capabilities.registry`, `agent.core.context`, `agent.core.session_scope`
- 顶层符号：
  - L12: `def _scheduler()`
  - L22: `def _owner()`
  - L29: `def _target(arguments)`
  - L33: `class TaskSleepTool(ToolPlugin)`
  - L58: `class TaskScheduleTool(ToolPlugin)`
  - L84: `class TaskWakeCancelTool(ToolPlugin)`
  - L98: `class TaskWakeListTool(ToolPlugin)`
  - L114: `def build_plugins()`
- 类成员：
  - L49: `TaskSleepTool.execute(self, arguments)`
  - L75: `TaskScheduleTool.execute(self, arguments)`
  - L93: `TaskWakeCancelTool.execute(self, arguments)`
  - L108: `TaskWakeListTool.execute(self, arguments)`

### A.56 `agent/capabilities/ui_registry.py`

- 类型：Python
- 行数：206
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：插件 UI 路径注册表：区域插口、控件和 catalog。
- 导入：`__future__`, `dataclasses`, `typing`, `agent.capabilities.path_registry`, `agent.capabilities.slot_registry`, `agent.core.error_report`
- 顶层符号：
  - L18: `class UiRegistry()`
- 类成员：
  - L23: `UiRegistry.add_slot(self, path)`
  - L64: `UiRegistry._item(self, path, kind, owner, handler, props, order)`
  - L77: `UiRegistry._install(self, item)`
  - L98: `UiRegistry._flush_pending(self)`
  - L128: `UiRegistry.finalize(self)`
  - L134: `UiRegistry.add_item(self, path)`
  - L164: `UiRegistry._active_entry(self, node)`
  - L171: `UiRegistry.catalog(self)`
  - L196: `UiRegistry.drop_owner(self, owner)`

### A.57 `agent/common/__init__.py`

- 类型：Python
- 行数：3
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：公共状态词汇。
- 顶层符号：无

### A.58 `agent/common/status.py`

- 类型：Python
- 行数：105
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：子系统状态值：插件 / 更新 / 协作 / 目标 / 预览 / 运行模式的唯一来源。
- 导入：`__future__`, `typing`
- 顶层符号：
  - L76: `def require(value, allowed, what)`

### A.59 `agent/config.py`

- 类型：Python
- 行数：311
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：配置读取：项目根 config.ini（按需取用，未使用的项留空）。
- 导入：`__future__`, `configparser`, `os`, `sys`, `pathlib`, `typing`, `agent.core.host`
- 顶层符号：
  - L33: `def _coerce_int(value, default)`
  - L45: `def compression_threshold(window, percent, fallback)`
  - L57: `def _clean(value)`
  - L62: `def load_ini(path)`
  - L85: `def get_update(path)`
  - L98: `def get_context(path)`
  - L135: `def _plugin_entries(parser)`
  - L151: `def get_plugins(path)`
  - L196: `def get_reasoning_effort(path)`
  - L212: `def get_backup_retention_days(path)`
  - L235: `def get_max_passes(path)`
  - L251: `def is_frozen()`
  - L256: `def prepare_user_home()`
  - L265: `def default_plugins_root()`
  - L270: `def user_data_root()`
  - L281: `def default_data_root()`
  - L295: `def get_plugin_tree_only(path)`

### A.60 `agent/config_schema.py`

- 类型：Python
- 行数：84
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：配置 schema：内核配置文件里允许出现的节与键（唯一事实源）。
- 导入：`__future__`, `typing`
- 顶层符号：
  - L80: `def schema_keys(section, schema)`

### A.61 `agent/core/__init__.py`

- 类型：Python
- 行数：87
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：内核：模块链 + 宿主循环 + 数据契约。
- 导入：`__future__`, `agent.core`, `agent.core.chain`, `agent.core.context`, `agent.core.engine`, `agent.core.event_bus`, `agent.core.events`, `agent.core.host`, `agent.core.model_call`, `agent.core.module`, `agent.core.modules`, `agent.core.outcome`, `agent.core.ports`, `agent.core.session_context`, `agent.core.session_log`, `agent.core.tool_call`
- 顶层符号：无

### A.62 `agent/core/app_path.py`

- 类型：Python
- 行数：21
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：插口树路径的唯一根与拼接。
- 导入：`__future__`, `typing`
- 顶层符号：
  - L10: `def app_path()`

### A.63 `agent/core/chain.py`

- 类型：Python
- 行数：166
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：模块链执行器（`run_chain` / `_Pass`）：一趟怎么跑。
- 导入：`__future__`, `dataclasses`, `typing`, `agent.core.module`, `agent.core.outcome`, `agent.core.pass_lifecycle`, `agent.core.ports`
- 顶层符号：
  - L32: `class PassResult()`
  - L49: `def _require_outcome(module, outcome)`
  - L60: `class _Pass()`
  - L137: `def run_chain_iter(modules, ports)`
  - L142: `def run_chain(modules, ports)`
  - L147: `def step(module, ports)`
- 类成员：
  - L45: `PassResult.stopped(self)`
  - L63: `_Pass.__init__(self, modules, ports)`
  - L68: `_Pass.__iter__(self)`
  - L104: `_Pass._source_contexts(self)`
  - L119: `_Pass._begin_source_pass(self)`
  - L124: `_Pass._end_source_pass(self)`
  - L128: `_Pass.drain(self)`

### A.64 `agent/core/context.py`

- 类型：Python
- 行数：201
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：上下文数据结构：进程级 `AppContext` + 工具往返 `ToolTurnContext`。
- 导入：`__future__`, `dataclasses`, `typing`, `agent.core.app_path`, `agent.core.error_report`
- 顶层符号：
  - L53: `class AppContext()`
  - L133: `class ToolTurnContext()`
- 类成员：
  - L56: `AppContext.__init__(self, slots)`
  - L61: `AppContext.register(self, name, service)`
  - L96: `AppContext.get(self, name)`
  - L108: `AppContext.has(self, name)`
  - L115: `AppContext.names(self)`
  - L125: `AppContext.dispose_all(self)`
  - L163: `ToolTurnContext.conversation_id(self)`
  - L168: `ToolTurnContext.call_id(self)`
  - L173: `ToolTurnContext.tool_name(self)`
  - L178: `ToolTurnContext.arguments(self)`
  - L183: `ToolTurnContext.service(self, name)`
  - L190: `ToolTurnContext.report(self, payload)`

### A.65 `agent/core/engine.py`

- 类型：Python
- 行数：279
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：引擎外观（`Engine`）：把模块链包成壳层要的"开始回合 / 事件流"两面。
- 导入：`__future__`, `typing`, `agent.core.error_report`, `agent.core.event_name`, `agent.core.events`, `agent.core.host`, `agent.core.image_embed`, `agent.core.module`, `agent.core.modules`, `agent.core.ports`, `agent.core.session_log`
- 顶层符号：
  - L33: `class Engine()`
- 类成员：
  - L36: `Engine.__init__(self)`
  - L118: `Engine._build_tool_port(registry, pipeline, app_context, session_contexts)`
  - L126: `Engine._select_input(input_module, modules)`
  - L136: `Engine._on_event(self, event)`
  - L153: `Engine._remember_suspend(self, event)`
  - L190: `Engine._flush_facts(self)`
  - L230: `Engine.start_turn(self, user_text, attachments, sender, from_queue, meta)`
  - L267: `Engine.paused(self)`
  - L271: `Engine.describe(self)`

### A.66 `agent/core/engine_factory.py`

- 类型：Python
- 行数：79
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：引擎工厂：把装配参数原样翻成模块链引擎。
- 导入：`__future__`, `typing`, `agent.core.engine`, `agent.core.host`, `agent.core.image_embed`
- 顶层符号：
  - L16: `def build_engine()`

### A.67 `agent/core/error_report.py`

- 类型：Python
- 行数：63
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：错误上报门面：core / 机制经此回调，不直接写盘。
- 导入：`__future__`, `threading`, `typing`, `agent.core.stderr`
- 顶层符号：
  - L20: `def bind_error_sink(sink)`
  - L35: `def report_error(tag, exc)`

### A.68 `agent/core/event_bus.py`

- 类型：Python
- 行数：81
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：事件总线（旁路）— 双轨机制之一，只做通知不参与控制流。
- 导入：`__future__`, `threading`, `typing`, `agent.core.error_report`, `agent.core.events`
- 顶层符号：
  - L22: `class EventBus()`
- 类成员：
  - L25: `EventBus.__init__(self)`
  - L29: `EventBus.subscribe(self, event_type, handler)`
  - L55: `EventBus.subscribe_all(self, handler)`
  - L63: `EventBus.publish(self, event)`
  - L77: `EventBus.dispose_all(self)`

### A.69 `agent/core/event_name.py`

- 类型：Python
- 行数：89
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：事实词汇：内核产出的全部事件名。
- 导入：`__future__`
- 顶层符号：无

### A.70 `agent/core/events.py`

- 类型：Python
- 行数：24
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：事件信封：一件事实的数据形状（类型 + 载荷）。
- 导入：`__future__`, `dataclasses`, `typing`
- 顶层符号：
  - L14: `class Event()`
  - L21: `def make_event(type_)`

### A.71 `agent/core/host.py`

- 类型：Python
- 行数：280
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：宿主（`Host`）：循环在这里，回合边界也在这里。
- 导入：`__future__`, `dataclasses`, `typing`, `agent.common.status`, `agent.core.chain`, `agent.core.error_report`, `agent.core.event_name`, `agent.core.events`, `agent.core.module`, `agent.core.outcome`, `agent.core.ports`, `agent.core.session_log`, `agent.core.state_values`
- 顶层符号：
  - L60: `def _asked_to_stop(cancel)`
  - L66: `class TurnResult()`
  - L86: `class Host()`
- 类成员：
  - L73: `TurnResult.__post_init__(self)`
  - L77: `TurnResult.ok(self)`
  - L81: `TurnResult.paused(self)`
  - L89: `Host.__init__(self, modules)`
  - L117: `Host.modules(self)`
  - L120: `Host.describe(self)`
  - L126: `Host.run_iter(self)`
  - L194: `Host._cancel_event(self, log, cid, passes)`
  - L201: `Host._terminal_event(self, result, log, cid, passes)`
  - L215: `Host._max_passes_event(self, log, cid, passes)`
  - L228: `Host.run(self)`
  - L252: `Host._report_pass_end(self)`
  - L263: `Host._emit(self, log, type_)`
  - L275: `Host._append(self, log, type_)`

### A.72 `agent/core/image_embed.py`

- 类型：Python
- 行数：444
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：视觉嵌图：附件 → OpenAI `image_url` 块（本地缩放 + base64 + 预算）。
- 导入：`__future__`, `base64`, `io`, `struct`, `pathlib`, `typing`, `agent.core.error_report`
- 顶层符号：
  - L35: `def _load_pillow()`
  - L49: `def _sniff_mime(data)`
  - L65: `def _mime_of(data, declared)`
  - L70: `def shrink_image(data)`
  - L114: `def build_embed_parts(attachments)`
  - L162: `def placeholder_text(indexes, attachments)`
  - L184: `def build_tool_parts(attachments)`
  - L207: `def _png_size(data)`
  - L214: `def _gif_size(data)`
  - L221: `def _jpeg_size(data)`
  - L244: `def _webp_size(data)`
  - L270: `def describe_image(data, declared_mime)`
  - L298: `def shrink_path(path)`
  - L320: `def _image_positions(messages, role)`
  - L326: `def _select_images(messages, positions, tool_positions, keep_turns, max_images)`
  - L347: `def _strip_unselected(messages, keep_ids)`
  - L368: `def strip_old_images(messages)`
  - L385: `def _image_block_indexes(message)`
  - L394: `def _image_block_count(message)`
  - L398: `def _drop_selected_blocks(content, drop)`
  - L419: `def strip_attachment_meta(messages)`

### A.73 `agent/core/input_attachments.py`

- 类型：Python
- 行数：67
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：输入附件规则：图片 MIME、数量上限与归一化。
- 导入：`__future__`, `base64`, `binascii`, `hashlib`, `typing`
- 顶层符号：
  - L15: `def attachment_id(data_base64, index)`
  - L21: `def with_attachment_ids(attachments)`
  - L34: `def normalize_images(raw)`
  - L54: `def decode_attachment(item)`
  - L65: `def encode_attachment(data)`

### A.74 `agent/core/mode_marker.py`

- 类型：Python
- 行数：10
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：执行模式段的固定起始标记。
- 导入：`__future__`
- 顶层符号：无

### A.75 `agent/core/model_call.py`

- 类型：Python
- 行数：31
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：模型调用协议：流帧契约。
- 导入：`__future__`, `dataclasses`, `typing`, `agent.core.tool_call`
- 顶层符号：
  - L16: `class StreamDelta()`

### A.76 `agent/core/module.py`

- 类型：Python
- 行数：68
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：模块抽象父类（`ModuleBase`）：行为面只有 `execute`。
- 导入：`__future__`, `typing`, `agent.core.ports`
- 顶层符号：
  - L33: `class ModuleBase()`
- 类成员：
  - L50: `ModuleBase.execute(self, ports)`
  - L61: `ModuleBase.describe(self)`
  - L66: `ModuleBase.__repr__(self)`

### A.77 `agent/core/modules/__init__.py`

- 类型：Python
- 行数：88
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：五个真实模块：输入 / 队列插入 / 压缩 / 模型 / 工具。
- 导入：`__future__`, `typing`, `agent.core.image_embed`, `agent.core.module`, `agent.core.modules.assemble`, `agent.core.modules.compress_mod`, `agent.core.modules.dialogue`, `agent.core.modules.input_mod`, `agent.core.modules.mode_note`, `agent.core.modules.model_mod`, `agent.core.modules.queued_input_mod`, `agent.core.modules.tool_facts`, `agent.core.modules.tool_mod`
- 顶层符号：
  - L57: `def build_default_chain()`

### A.78 `agent/core/modules/assemble.py`

- 类型：Python
- 行数：48
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：上下文装配与分段快照。
- 导入：`__future__`, `typing`, `agent.core.modules.mode_note`
- 顶层符号：
  - L10: `def assemble_with(context, dialogue, mode_note, covered_end)`
  - L27: `def segment_snapshot(context, messages, budget_tokens)`

### A.79 `agent/core/modules/compress_mod.py`

- 类型：Python
- 行数：101
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：压缩模块：上下文预算与压缩。
- 导入：`__future__`, `typing`, `agent.core.error_report`, `agent.core.event_name`, `agent.core.image_embed`, `agent.core.module`, `agent.core.modules.assemble`, `agent.core.modules.dialogue`, `agent.core.modules.mode_note`, `agent.core.outcome`, `agent.core.ports`
- 顶层符号：
  - L18: `class CompressModule(ModuleBase)`
- 类成员：
  - L28: `CompressModule.__init__(self)`
  - L44: `CompressModule._covered_end(self)`
  - L52: `CompressModule.execute(self, ports)`

### A.80 `agent/core/modules/dialogue.py`

- 类型：Python
- 行数：23
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：模型请求的对话与图片准备。
- 导入：`__future__`, `typing`, `agent.core.image_embed`
- 顶层符号：
  - L10: `def prepare_dialogue(dialogue, image_turns, image_max)`

### A.81 `agent/core/modules/input_mod.py`

- 类型：Python
- 行数：83
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：输入模块：认领本回合用户输入。
- 导入：`__future__`, `typing`, `agent.core.event_name`, `agent.core.input_attachments`, `agent.core.module`, `agent.core.outcome`, `agent.core.ports`
- 顶层符号：
  - L14: `class InputModule(ModuleBase)`
- 类成员：
  - L30: `InputModule.__init__(self, text, attachments)`
  - L38: `InputModule.feed(self, text, attachments, sender, from_queue, meta)`
  - L48: `InputModule.execute(self, ports)`

### A.82 `agent/core/modules/mode_note.py`

- 类型：Python
- 行数：96
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：运行态与模式尾部。
- 导入：`__future__`, `typing`, `agent.core.error_report`, `agent.core.mode_marker`
- 顶层符号：
  - L13: `def strip_mode_tail(messages, mode_note)`
  - L40: `def strip_runtime_note(messages)`
  - L54: `def resolve_runtime_note(value)`
  - L65: `def with_mode_note(messages, mode_note)`
  - L83: `def mode_tail(messages)`

### A.83 `agent/core/modules/model_mod.py`

- 类型：Python
- 行数：247
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：模型模块：流式调用模型并落 model_message。
- 导入：`__future__`, `time`, `typing`, `agent.core.error_report`, `agent.core.event_name`, `agent.core.image_embed`, `agent.core.model_call`, `agent.core.module`, `agent.core.modules.assemble`, `agent.core.modules.dialogue`, `agent.core.modules.mode_note`, `agent.core.modules.tool_facts`, `agent.core.outcome`, `agent.core.ports`, `agent.core.state_values`, `agent.core.state_values`, `agent.core.state_values`, `agent.core.tool_call`
- 顶层符号：
  - L46: `def _reasoning_ms(started, last_at)`
  - L53: `class ModelModule(ModuleBase)`
- 类成员：
  - L71: `ModelModule.__init__(self)`
  - L93: `ModelModule._covered_end(self)`
  - L101: `ModelModule._build_request(self, ports)`
  - L142: `ModelModule._cancel_events(self, ports, model, request, started, reasoning_last_at, chunks)`
  - L154: `ModelModule._stream(self, ports, model, request)`
  - L216: `ModelModule.execute(self, ports)`

### A.84 `agent/core/modules/queued_input_mod.py`

- 类型：Python
- 行数：80
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：安全插入点：把队列中积压的 Agent 消息一次性写成输入事实。
- 导入：`__future__`, `typing`, `agent.core.error_report`, `agent.core.event_name`, `agent.core.input_attachments`, `agent.core.module`, `agent.core.outcome`, `agent.core.ports`
- 顶层符号：
  - L15: `class QueuedInputModule(ModuleBase)`
- 类成员：
  - L21: `QueuedInputModule.__init__(self)`
  - L24: `QueuedInputModule.execute(self, ports)`

### A.85 `agent/core/modules/slot_chain.py`

- 类型：Python
- 行数：71
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：内核模块链的插口节点与逐会话构建。
- 导入：`__future__`, `dataclasses`, `typing`, `agent.core.host`, `agent.core.image_embed`, `agent.core.modules.compress_mod`, `agent.core.modules.input_mod`, `agent.core.modules.model_mod`, `agent.core.modules.queued_input_mod`, `agent.core.modules.tool_mod`
- 顶层符号：
  - L17: `def input_module(ctx, children)`
  - L21: `def queued_input_module(ctx, children)`
  - L25: `def compress_module(ctx, children)`
  - L32: `def model_module(ctx, children)`
  - L40: `def tool_module(ctx, children)`
  - L45: `class AgentLoopConfig()`
  - L54: `class ModuleBuildContext()`

### A.86 `agent/core/modules/tool_facts.py`

- 类型：Python
- 行数：146
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：工具调用与工具结果事实。
- 导入：`__future__`, `typing`, `agent.core.event_name`, `agent.core.ports`, `agent.core.session_log`, `agent.core.tool_call`
- 顶层符号：
  - L26: `def tail_expects_model(log)`
  - L51: `def pending_tool_calls(log)`
  - L88: `def serialize_call(call)`
  - L92: `def safe_value(value)`
  - L109: `def clip_tool_result(value, limit)`
  - L128: `def progress_emitter(ports)`

### A.87 `agent/core/modules/tool_mod.py`

- 类型：Python
- 行数：157
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：工具模块（收尾）：执行未消费的工具调用。
- 导入：`__future__`, `time`, `typing`, `agent.core.event_name`, `agent.core.module`, `agent.core.modules.tool_facts`, `agent.core.outcome`, `agent.core.ports`, `agent.core.state_values`, `agent.core.state_values`, `agent.core.state_values`, `agent.core.state_values`
- 顶层符号：
  - L65: `def _elapsed_s(elapsed_ms)`
  - L70: `class ToolModule(ModuleBase)`
- 类成员：
  - L89: `ToolModule._cancel_rest(self, ports, pending, start, reason)`
  - L97: `ToolModule._result_events(self, ports, call, result, elapsed, ok)`
  - L119: `ToolModule.execute(self, ports)`

### A.88 `agent/core/outcome.py`

- 类型：Python
- 行数：89
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：控制信号（`Outcome`）：模块执行结果的唯一形状。
- 导入：`__future__`, `dataclasses`
- 顶层符号：
  - L38: `class Outcome()`
- 类成员：
  - L47: `Outcome.__post_init__(self)`
  - L54: `Outcome.ok()`
  - L59: `Outcome.next()`
  - L64: `Outcome.halt(reason)`
  - L69: `Outcome.suspend(reason)`
  - L74: `Outcome.stopped(reason)`
  - L81: `Outcome.is_terminal(self)`
  - L86: `Outcome.wants_another_pass(self)`

### A.89 `agent/core/pass_lifecycle.py`

- 类型：Python
- 行数：23
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：一趟模块链的上下文生命周期协议。
- 导入：`__future__`, `typing`
- 顶层符号：
  - L13: `class PassLifecycle(Protocol)`
- 类成员：
  - L16: `PassLifecycle.begin_pass(self)`
  - L20: `PassLifecycle.end_pass(self)`

### A.90 `agent/core/ports.py`

- 类型：Python
- 行数：313
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：端口（`Ports`）：模块操作外界的唯一通路。
- 导入：`__future__`, `dataclasses`, `typing`, `agent.core.error_report`, `agent.core.events`, `agent.core.model_call`, `agent.core.session_log`, `agent.core.tool_call`
- 顶层符号：
  - L39: `class ProviderPort(Protocol)`
  - L51: `class RegistryPort(Protocol)`
  - L58: `class PipelinePort(Protocol)`
  - L66: `class SessionsPort(Protocol)`
  - L74: `class ModelPort()`
  - L103: `class ToolPort()`
  - L162: `class _ToolCallScope()`
  - L196: `class Ports()`
  - L288: `class LogicalRequest()`
- 类成员：
  - L47: `ProviderPort.stream(self, request)`
  - L54: `RegistryPort.schemas(self)`
  - L61: `PipelinePort.execute(self, registry, call, ctx)`
  - L69: `SessionsPort.resolve_sync(self, conversation_id)`
  - L81: `ModelPort.__init__(self, provider)`
  - L85: `ModelPort.provider(self)`
  - L89: `ModelPort.name(self)`
  - L93: `ModelPort.name_for(self, request)`
  - L98: `ModelPort.stream(self, request)`
  - L111: `ToolPort.__init__(self)`
  - L125: `ToolPort.registry(self)`
  - L128: `ToolPort.schemas(self)`
  - L134: `ToolPort.execute(self, call)`
  - L171: `_ToolCallScope.__init__(self)`
  - L189: `_ToolCallScope.canceled(self)`
  - L202: `Ports.__init__(self)`
  - L229: `Ports.log(self)`
  - L238: `Ports.conversation_id(self)`
  - L241: `Ports.emit(self, type_)`
  - L256: `Ports._stamp_seq(self, payload)`
  - L269: `Ports.model_port(self)`
  - L273: `Ports.tool_port(self)`
  - L276: `Ports.canceled(self)`

### A.91 `agent/core/session_context.py`

- 类型：Python
- 行数：197
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：会话上下文（SessionContext / SessionContexts）——会话级状态的载体。
- 导入：`__future__`, `threading`, `dataclasses`, `typing`, `uuid`, `agent.core.session_scope`
- 顶层符号：
  - L53: `class SessionContext()`
  - L82: `class SessionContexts()`
  - L194: `def _bucket(conversation_id)`
- 类成员：
  - L72: `SessionContext.grant_approval(self, option_id)`
  - L92: `SessionContexts.__init__(self, gate_factory)`
  - L110: `SessionContexts.live(self)`
  - L116: `SessionContexts.resolve_sync(self, conversation_id)`
  - L157: `SessionContexts.resolve(self)`
  - L161: `SessionContexts.get(self, conversation_id)`
  - L166: `SessionContexts.buckets(self)`
  - L171: `SessionContexts.release(self, conversation_id)`
  - L181: `SessionContexts.close_all(self)`
  - L188: `SessionContexts.active_count(self)`

### A.92 `agent/core/session_log.py`

- 类型：Python
- 行数：357
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：会话记录：事实 append + 模型历史 derive。
- 导入：`__future__`, `json`, `copy`, `dataclasses`, `typing`, `agent.core.error_report`, `agent.core.event_name`, `agent.core.events`, `agent.core.model_call`, `agent.core.state_values`
- 顶层符号：
  - L21: `def _user_content(text, attachments)`
  - L50: `def _tool_content(text, attachments)`
  - L71: `def _tool_envelope()`
  - L101: `def _render_tool_message(call_id, done, name)`
  - L119: `class SessionLogView()`
  - L161: `def _closed_tool_calls(events)`
  - L172: `def _input_message(ev)`
  - L180: `def _model_message(ev)`
  - L195: `def _tool_ended_message(ev, results, emitted)`
  - L207: `def _tool_result_message(ev, closed, results, emitted)`
  - L223: `def _tool_fact_message(ev, results, emitted)`
  - L246: `class SessionLog()`
  - L324: `def ensure_tool_pairs(messages)`
- 类成员：
  - L127: `SessionLogView.__init__(self, log)`
  - L131: `SessionLogView.events(self)`
  - L140: `SessionLogView.__getitem__(self, index)`
  - L144: `SessionLogView.derive_messages(self)`
  - L147: `SessionLogView.derive_request_messages(self)`
  - L150: `SessionLogView.__len__(self)`
  - L153: `SessionLogView.__iter__(self)`
  - L156: `SessionLogView.__repr__(self)`
  - L251: `SessionLog.append(self, events)`
  - L255: `SessionLog.readonly(self)`
  - L270: `SessionLog.derive_messages(self)`
  - L293: `SessionLog.derive_request_messages(self)`

### A.93 `agent/core/session_scope.py`

- 类型：Python
- 行数：111
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：会话 / 工具调用作用域 — 工具取上下文的唯一通路，以及进度上报通道。
- 导入：`__future__`, `contextvars`, `typing`, `agent.core.error_report`
- 顶层符号：
  - L32: `def set_session_scope(conversation_id)`
  - L37: `def reset_session_scope(token)`
  - L42: `def current_session_id()`
  - L47: `def set_tool_turn_context(ctx)`
  - L52: `def reset_tool_turn_context(token)`
  - L57: `def current_context()`
  - L68: `def set_progress_reporter(reporter)`
  - L73: `def reset_progress_reporter(token)`
  - L78: `def current_progress_reporter()`
  - L88: `def emit_progress()`

### A.94 `agent/core/slot.py`

- 类型：Python
- 行数：158
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：自装配组件契约：所有运行期组件继承 SlotComponent。
- 导入：`__future__`, `abc`, `typing`, `agent.core.error_report`
- 顶层符号：
  - L11: `class SlotComponent(ABC)`
  - L30: `class SlotLeaf(SlotComponent)`
  - L41: `class SlotContainer(SlotComponent)`
  - L101: `class SlotContribution(SlotLeaf)`
  - L134: `class SlotValue(SlotLeaf)`
- 类成员：
  - L18: `SlotComponent.assembly(self, tree)`
  - L21: `SlotComponent.port_value(self)`
  - L25: `SlotComponent.dispose(self)`
  - L33: `SlotLeaf.__init__(self, path)`
  - L37: `SlotLeaf.assembly(self, tree)`
  - L44: `SlotContainer.__init__(self, path)`
  - L51: `SlotContainer.assembly(self, tree)`
  - L78: `SlotContainer._rollback(self, added, tree)`
  - L92: `SlotContainer.dispose(self)`
  - L104: `SlotContribution.__init__(self, path, register)`
  - L111: `SlotContribution.assembly(self, tree)`
  - L118: `SlotContribution.deactivate(self)`
  - L127: `SlotContribution.dispose(self)`
  - L137: `SlotValue.__init__(self, path, value)`
  - L142: `SlotValue.port_value(self)`
  - L145: `SlotValue.dispose(self)`

### A.95 `agent/core/slot_tree.py`

- 类型：Python
- 行数：380
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：插口树：唯一清单、节点索引、递归装配与失败回滚。
- 导入：`__future__`, `importlib`, `json`, `dataclasses`, `pathlib`, `typing`, `agent.core.app_path`, `agent.core.error_report`, `agent.core.slot`
- 顶层符号：
  - L16: `def _apply_overrides(nodes, overrides)`
  - L59: `class SlotTreeError(RuntimeError)`
  - L64: `class SlotNode()`
  - L79: `class SlotRuntime()`
  - L95: `class BuildContext()`
  - L116: `class SlotTree()`
  - L363: `def _resolve(spec)`
- 类成员：
  - L87: `SlotRuntime.service(self, path)`
  - L102: `BuildContext.config(self)`
  - L105: `BuildContext.resolve(self, path)`
  - L119: `SlotTree.__init__(self, nodes)`
  - L138: `SlotTree.load(cls, path)`
  - L160: `SlotTree._validate(self)`
  - L170: `SlotTree.children(self, path)`
  - L178: `SlotTree.roots(self)`
  - L181: `SlotTree.node(self, path)`
  - L187: `SlotTree.release_component(self, component)`
  - L195: `SlotTree._frozen_ancestor(self, path)`
  - L203: `SlotTree.materialize(self, node)`
  - L239: `SlotTree.assemble(self, plugin)`
  - L261: `SlotTree.add_dynamic(self, path, factory)`
  - L337: `SlotTree.dispose_all(self)`
  - L356: `SlotTree.assert_no_pending(self)`

### A.96 `agent/core/state_values.py`

- 类型：Python
- 行数：38
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：内核状态值：回合 / 工具 / 模型调用的唯一来源。
- 导入：`__future__`
- 顶层符号：无

### A.97 `agent/core/stderr.py`

- 类型：Python
- 行数：14
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：stderr 兜底：日志系统自身失败时使用。
- 导入：`__future__`, `os`
- 顶层符号：
  - L8: `def write_stderr(message)`

### A.98 `agent/core/thread_context.py`

- 类型：Python
- 行数：29
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：线程启动时的执行上下文传播。
- 导入：`__future__`, `contextvars`, `threading`, `typing`
- 顶层符号：
  - L10: `def thread_with_context()`

### A.99 `agent/core/tool_call.py`

- 类型：Python
- 行数：232
- 所属主模块：`app/runtime/kernel`
- 文件角色：runtime/implementation
- 文件说明：工具调用协议：数据结构 + 唯一执行管道。
- 导入：`__future__`, `dataclasses`, `typing`, `agent.core.app_path`, `agent.core.context`, `agent.core.session_scope`
- 顶层符号：
  - L25: `class ToolCallRequest()`
  - L35: `class ToolResult()`
  - L78: `class GateDecision()`
  - L92: `class ToolPipeline()`
- 类成员：
  - L52: `ToolResult.attach(data, attachments)`
  - L95: `ToolPipeline.__init__(self, slots)`
  - L104: `ToolPipeline.add_pre(self, gate)`
  - L116: `ToolPipeline.add_post(self, observer)`
  - L128: `ToolPipeline._pre_result(self, call, ctx)`
  - L137: `ToolPipeline._invalid_arguments(self, registry, call)`
  - L155: `ToolPipeline._binding_result(self, registry, call)`
  - L191: `ToolPipeline._post_observe(self, call, result, ctx)`
  - L195: `ToolPipeline.execute(self, registry, call, ctx)`
  - L203: `ToolPipeline._execute(self, registry, call, ctx)`

### A.100 `agent/entry/__init__.py`

- 类型：Python
- 行数：8
- 所属主模块：`app/entry/__init__.py`
- 文件角色：runtime/implementation
- 文件说明：进程入口层（entry）：唯一知道"如何把 app 装配起来再交给壳"的地方。
- 顶层符号：无

### A.101 `agent/entry/cli.py`

- 类型：Python
- 行数：48
- 所属主模块：`app/entry/cli.py`
- 文件角色：runtime/implementation
- 文件说明：交互式对话进程入口。
- 导入：`__future__`, `sys`, `pathlib`, `typing`, `agent.app`, `agent.common.status`, `agent.config`, `agent.mechanisms.session_store`, `agent.shell.cli`
- 顶层符号：
  - L25: `def build_app_from_config()`
  - L42: `def main(argv)`

### A.102 `agent/entry/headless.py`

- 类型：Python
- 行数：45
- 所属主模块：`app/entry/headless.py`
- 文件角色：runtime/implementation
- 文件说明：无 UI 单回合入口：装配 app，跑一个回合并打印事件流。
- 导入：`__future__`, `sys`, `pathlib`, `typing`, `agent.app`, `agent.common.status`, `agent.config`, `agent.mechanisms.session_store`, `agent.shell.cli`
- 顶层符号：
  - L21: `def _default_app_factory()`
  - L39: `def main(argv)`

### A.103 `agent/entry/web.py`

- 类型：Python
- 行数：161
- 所属主模块：`app/entry/web.py`
- 文件角色：runtime/implementation
- 文件说明：Web 进程入口：按配置装配 app，再交给 `agent.shell.web.server.serve`。
- 导入：`__future__`, `argparse`, `getpass`, `os`, `sys`, `pathlib`, `typing`, `agent.app`, `agent.config`, `agent.mechanisms.providers.missing`, `agent.mechanisms.session_store`, `agent.shell.fspaths`, `agent.shell.web.auth`, `agent.shell.web.auth.config`, `agent.shell.web.auth.security`, `agent.shell.web.server`
- 顶层符号：
  - L29: `def build_shell_app()`
  - L44: `def _load_auth(root)`
  - L53: `def _auth_cli(root, args)`
  - L95: `def main(argv)`

### A.104 `agent/gui/__init__.py`

- 类型：Python
- 行数：1
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 顶层符号：无

### A.105 `agent/gui/bootstrap.py`

- 类型：Python
- 行数：49
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：首次运行：确保 pywebview 可用；依赖只装到用户缓存，不写项目。
- 导入：`__future__`, `importlib.util`, `os`, `subprocess`, `sys`, `pathlib`
- 顶层符号：
  - L14: `def deps_dir()`
  - L19: `def main()`

### A.106 `agent/gui/launcher.py`

- 类型：Python
- 行数：588
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：GUI 启动器：启动并维护自己的 Web 服务子进程，然后在嵌入式 WebView 中打开 Web UI。
- 导入：`__future__`, `argparse`, `ctypes`, `json`, `os`, `secrets`, `shutil`, `socket`, `subprocess`, `sys`, `threading`, `time`, `urllib.error`, `urllib.request`, `pathlib`, `typing`, `agent.core.error_report`
- 顶层符号：
  - L32: `def _show_startup_error(message)`
  - L43: `def _health_url(host, port)`
  - L47: `def _is_agent_health(host, port, timeout)`
  - L59: `def _app_root()`
  - L65: `def _python_command()`
  - L90: `def _web_command()`
  - L104: `def _spawn_server(host, port, bootstrap)`
  - L137: `def _wait_health(host, port, timeout)`
  - L146: `def _pointer_int(value)`
  - L155: `def _apply_maximized_bounds(window)`
  - L169: `class _WindowApi()`
  - L226: `def _pick_port(host)`
  - L232: `def _stop_server(proc)`
  - L243: `class _WindowsJob()`
  - L321: `class _ServerSupervisor()`
  - L364: `def _storage_path()`
  - L376: `def _apply_dark_titlebar(window)`
  - L392: `def _window_handle(window)`
  - L397: `def _activate_window(window)`
  - L429: `def _apply_window_icon(window)`
  - L455: `def _centered_geometry(width, height)`
  - L485: `def _open_window(url, supervisor)`
  - L543: `def launch(host, port)`
  - L571: `def main(argv)`
- 类成员：
  - L172: `_WindowApi.__init__(self, supervisor)`
  - L176: `_WindowApi.minimize(self)`
  - L181: `_WindowApi.toggle_maximize(self, maximized)`
  - L191: `_WindowApi.close(self)`
  - L196: `_WindowApi.ensure_server(self)`
  - L201: `_WindowApi.window_position(self)`
  - L206: `_WindowApi.move_window(self, x, y)`
  - L211: `_WindowApi.window_size(self)`
  - L216: `_WindowApi.resize_window(self, width, height, x, y)`
  - L246: `_WindowsJob.__init__(self)`
  - L302: `_WindowsJob.assign(self, proc)`
  - L312: `_WindowsJob.close(self)`
  - L324: `_ServerSupervisor.__init__(self, host, port, timeout)`
  - L332: `_ServerSupervisor.start(self)`
  - L336: `_ServerSupervisor._spawn(self)`
  - L343: `_ServerSupervisor.wait_ready(self)`
  - L346: `_ServerSupervisor.ensure_alive(self)`
  - L359: `_ServerSupervisor.stop(self)`

### A.107 `agent/mechanisms/background_tasks.py`

- 类型：Python
- 行数：553
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：按 cid 隔离的后台任务队列与进程执行器。
- 导入：`__future__`, `os`, `signal`, `subprocess`, `threading`, `time`, `uuid`, `collections`, `dataclasses`, `pathlib`, `typing`, `agent.core.error_report`, `agent.core.thread_context`
- 顶层符号：
  - L42: `class BackgroundTaskRecord()`
  - L87: `class BackgroundTaskExecutor()`
  - L173: `class _CidQueue()`
  - L179: `class BackgroundTaskManager()`
- 类成员：
  - L67: `BackgroundTaskRecord.public(self)`
  - L91: `BackgroundTaskExecutor.spawn(argv, cwd, env)`
  - L114: `BackgroundTaskExecutor.kill_tree(pid, process)`
  - L182: `BackgroundTaskManager.__init__(self, allowed_roots)`
  - L200: `BackgroundTaskManager.active_total(self)`
  - L204: `BackgroundTaskManager.set_notice(self, notice)`
  - L208: `BackgroundTaskManager._queue(self, cid)`
  - L214: `BackgroundTaskManager._active_locked(self, q)`
  - L217: `BackgroundTaskManager.create(self, cid, argv, cwd, timeout_sec, label, batch)`
  - L266: `BackgroundTaskManager.list_tasks(self, cid, batch, task_id, status)`
  - L293: `BackgroundTaskManager.snapshot(self, cid)`
  - L303: `BackgroundTaskManager.cancel(self, cid, task_id, reason)`
  - L332: `BackgroundTaskManager.output(self, cid, task_id, wait, timeout_ms)`
  - L352: `BackgroundTaskManager.shutdown(self)`
  - L363: `BackgroundTaskManager._schedule_loop(self)`
  - L371: `BackgroundTaskManager._schedule_locked(self, q, notices)`
  - L382: `BackgroundTaskManager._start_locked(self, q, record, notices)`
  - L402: `BackgroundTaskManager._read_stream(self, record, stream, channel)`
  - L423: `BackgroundTaskManager._append_output(record, target, channel, chunk)`
  - L436: `BackgroundTaskManager._watch(self, q, record)`
  - L467: `BackgroundTaskManager._settle_locked(self, q, record, status, detail, notices)`
  - L488: `BackgroundTaskManager._emit_notices(self, notices)`
  - L509: `BackgroundTaskManager._read_locked(self, record)`
  - L523: `BackgroundTaskManager._resolve_cwd(self, cwd)`
  - L537: `BackgroundTaskManager._env()`

### A.108 `agent/mechanisms/command_safety.py`

- 类型：Python
- 行数：332
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：命令执行安全机制：黑名单 / 内容级拦截 / safe_mode / 进程生命周期 / 输出净化 / shell 选择。
- 导入：`__future__`, `atexit`, `os`, `re`, `signal`, `subprocess`, `threading`, `pathlib`, `typing`, `agent.core.error_report`
- 顶层符号：
  - L37: `class CommandBlacklisted(Exception)`
  - L95: `def _extract_base_command(command)`
  - L120: `def _strip_shell_wrapper(segment)`
  - L130: `def _check_segment(segment)`
  - L143: `def check_command_blacklist(command)`
  - L153: `def _advice_message(entry, advice)`
  - L158: `def check_text_content(text)`
  - L176: `def _extract_py_candidates(command)`
  - L186: `def check_script_content(command, cwd)`
  - L208: `def validate_safe_command(command)`
  - L221: `def register_shell_process(pid, scope)`
  - L227: `def unregister_shell_process(pid, scope)`
  - L235: `def kill_shell_process_tree(pid)`
  - L258: `def force_kill_active_shell_process(scope)`
  - L279: `def decode_output(data)`
  - L293: `def sanitize_output_for_display(text)`
  - L317: `def resolve_shell(shell, command)`

### A.109 `agent/mechanisms/compaction/__init__.py`

- 类型：Python
- 行数：2
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 顶层符号：无

### A.110 `agent/mechanisms/compaction/compactor.py`

- 类型：Python
- 行数：501
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：上下文压缩器 — 拼入前预算检查 + 同步摘要压缩。
- 导入：`__future__`, `copy`, `json`, `typing`, `agent.core.app_path`, `agent.core.error_report`, `agent.core.modules.mode_note`, `agent.core.ports`, `agent.core.session_log`, `agent.mechanisms.context.contract`
- 顶层符号：
  - L101: `def _summary_display_text(body)`
  - L106: `def _is_degenerate_summary_body(body)`
  - L120: `def count_images(content)`
  - L130: `def _schemas_tokens(tools, policy)`
  - L140: `def _mode_note_tokens(mode_note, policy)`
  - L145: `def _material_messages(prefix, material)`
  - L179: `def make_provider_summarizer(provider)`
  - L240: `class ContextCompactor()`
- 类成员：
  - L243: `ContextCompactor.__init__(self, summarize_fn)`
  - L279: `ContextCompactor._slot_bound(self, path)`
  - L289: `ContextCompactor._build_context_default(messages, mode_note)`
  - L293: `ContextCompactor.build_context(self, messages, mode_note)`
  - L299: `ContextCompactor._message_tokens(self, message)`
  - L302: `ContextCompactor._policy_view(self)`
  - L307: `ContextCompactor._summarize_text(self, base, tools, system, material)`
  - L317: `ContextCompactor.restore_from_events(self, events)`
  - L341: `ContextCompactor.view_messages(self, messages)`
  - L345: `ContextCompactor.summary_messages(self)`
  - L357: `ContextCompactor.remember_sent_request(self, messages, cache_prefix, tools)`
  - L364: `ContextCompactor.sent_prefix(self)`
  - L369: `ContextCompactor.sent_tools(self)`
  - L376: `ContextCompactor._excerpt_range(self, view, context)`
  - L389: `ContextCompactor._summary_body(self, base, material, context, tools)`
  - L400: `ContextCompactor.ensure_before_append(self, context, messages, pending, tools, mode_note, assembled)`
  - L459: `ContextCompactor._context_without_new_input(messages)`

### A.111 `agent/mechanisms/context/__init__.py`

- 类型：Python
- 行数：56
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：上下文模型、布局、来源与管线。
- 导入：`__future__`, `agent.mechanisms.context.contract`, `agent.mechanisms.context.layout`, `agent.mechanisms.context.pipeline`, `agent.mechanisms.context.rounds`, `agent.mechanisms.context.sources`, `agent.mechanisms.context.tokens`
- 顶层符号：无

### A.112 `agent/mechanisms/context/constants.py`

- 类型：Python
- 行数：11
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：上下文分段标签。
- 导入：`__future__`
- 顶层符号：无

### A.113 `agent/mechanisms/context/contract.py`

- 类型：Python
- 行数：50
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：压缩器依赖的窄上下文接口。
- 导入：`__future__`, `dataclasses`, `typing`, `agent.mechanisms.context.layout`, `agent.mechanisms.context.rounds`, `agent.mechanisms.context.tokens`
- 顶层符号：
  - L16: `class ContextCompactionPolicy()`
- 类成员：
  - L21: `ContextCompactionPolicy.excerpt(self, messages)`
  - L32: `ContextCompactionPolicy.clip(messages, budget_tokens)`
  - L36: `ContextCompactionPolicy.approx_tokens(text)`
  - L40: `ContextCompactionPolicy.message_tokens(message)`
  - L44: `ContextCompactionPolicy.balanced(messages, start, end)`
  - L48: `ContextCompactionPolicy.floor(messages, index)`

### A.114 `agent/mechanisms/context/hooks.py`

- 类型：Python
- 行数：75
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：上下文拼装钩子。
- 导入：`__future__`, `typing`, `agent.core.error_report`
- 顶层符号：
  - L21: `class ContextAssemblyHooks()`
  - L64: `def _valid_messages(value)`
- 类成员：
  - L24: `ContextAssemblyHooks.__init__(self)`
  - L27: `ContextAssemblyHooks.add(self, hook)`
  - L44: `ContextAssemblyHooks.apply(self, messages, conversation_id)`

### A.115 `agent/mechanisms/context/layout.py`

- 类型：Python
- 行数：324
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：上下文 token 裁剪、分段布局与压缩区间。
- 导入：`__future__`, `typing`, `agent.mechanisms.context.constants`, `agent.mechanisms.context.rounds`, `agent.mechanisms.context.tokens`
- 顶层符号：
  - L13: `def clip_reasoning_text(text, budget_tokens)`
  - L43: `def _prefix_within_budget(text, budget_tokens)`
  - L55: `def _suffix_within_budget(text, budget_tokens)`
  - L67: `def clip_reasoning(messages, budget_tokens)`
  - L97: `def as_text_parts(text)`
  - L115: `def merge_segment_rows(rows)`
  - L130: `def _partition_head(messages, head, system_text)`
  - L150: `def _partition_plugins(rest_head, plan)`
  - L165: `def _split_mode(body)`
  - L175: `def _layout_rows(prompt, head_msgs, plan, plugin, summary, dialogue, mode, counter)`
  - L205: `def layout_from_messages(messages)`
  - L240: `def excerpt_by_target_tokens(messages, keep_turns, token_fn)`
  - L282: `def adjust_excerpt_range_half_open(messages, start, end)`

### A.116 `agent/mechanisms/context/pipeline.py`

- 类型：Python
- 行数：513
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：上下文管线装配。
- 导入：`__future__`, `copy`, `typing`, `agent.config`, `agent.mechanisms.context.constants`, `agent.mechanisms.context.contract`, `agent.mechanisms.context.layout`, `agent.mechanisms.context.rounds`, `agent.mechanisms.context.sources`, `agent.mechanisms.context.tokens`
- 顶层符号：
  - L41: `class ContextPipeline()`
- 类成员：
  - L44: `ContextPipeline.__init__(self, conversation_id)`
  - L91: `ContextPipeline.segment_tokens(self)`
  - L135: `ContextPipeline._plugin_rows(self, counter)`
  - L170: `ContextPipeline.layout_payload(self)`
  - L222: `ContextPipeline.add(self, chunk)`
  - L243: `ContextPipeline.message_tokens(self, msg)`
  - L247: `ContextPipeline.set_dialogue(self, messages)`
  - L272: `ContextPipeline.set_summary_messages(self, summaries)`
  - L283: `ContextPipeline.plugin_segments(self)`
  - L300: `ContextPipeline.host_messages(self)`
  - L315: `ContextPipeline.dialogue_messages(self)`
  - L322: `ContextPipeline.assembles(self, tail)`
  - L332: `ContextPipeline.append_system(self, text)`
  - L336: `ContextPipeline.system_text(self)`
  - L354: `ContextPipeline.append_plugin(self, text, key, label)`
  - L368: `ContextPipeline.set_plugin_segments(self, segments)`
  - L396: `ContextPipeline.append_new_msg(self, role, content)`
  - L400: `ContextPipeline.append_msg(self, role, content)`
  - L404: `ContextPipeline.rebuild_from_messages(self, flat_messages)`
  - L412: `ContextPipeline.begin_pass(self)`
  - L417: `ContextPipeline.end_pass(self)`
  - L427: `ContextPipeline._drop_source_snapshot(self)`
  - L431: `ContextPipeline.refresh_sources(self)`
  - L436: `ContextPipeline._refresh_sources(self)`
  - L463: `ContextPipeline.flatten_to_messages(self, sanitize_fn)`
  - L481: `ContextPipeline.put_new_mem_file(self, path, over_rounds)`
  - L486: `ContextPipeline.try_load_pending_mem_file(self, messages, merge_fn)`
  - L498: `ContextPipeline.total_token_estimate(self, approx_msg_fn)`
  - L504: `ContextPipeline.calculate_tokens(self, approx_msg_fn)`
  - L510: `ContextPipeline.calculate_round_count(self)`

### A.117 `agent/mechanisms/context/rounds.py`

- 类型：Python
- 行数：168
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：上下文轮次与工具链边界。
- 导入：`__future__`, `copy`, `typing`
- 顶层符号：
  - L9: `class Round()`
  - L30: `class ContextChunk()`
  - L58: `def flat_messages_to_user_rounds(msgs)`
  - L80: `def copy_round_list(src, start, count)`
  - L92: `def find_first_user_index(messages)`
  - L100: `def user_turn_starts(messages)`
  - L110: `def turn_boundary_floor(messages, index)`
  - L130: `def is_turn_boundary(messages, index)`
  - L138: `def turn_spans(messages)`
  - L149: `def tool_chain_balanced(messages, start, end)`
- 类成员：
  - L14: `Round.__init__(self, round_id)`
  - L18: `Round.append_message_dict(self, msg)`
  - L21: `Round.append(self, role, content)`
  - L26: `Round.calculate_tokens(self, approx_msg_fn)`
  - L35: `ContextChunk.__init__(self, name)`
  - L39: `ContextChunk.append(self, role, content, is_new_msg)`
  - L45: `ContextChunk.get_count(self)`
  - L48: `ContextChunk.calculate_tokens(self, approx_msg_fn)`

### A.118 `agent/mechanisms/context/sources.py`

- 类型：Python
- 行数：247
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：上下文注入源与插件段落。
- 导入：`__future__`, `threading`, `dataclasses`, `typing`, `agent.core.app_path`, `agent.core.error_report`
- 顶层符号：
  - L16: `class SourceMeta()`
  - L38: `class PluginSegments()`
  - L67: `def slug(text)`
  - L73: `class ContextSources()`
- 类成员：
  - L48: `PluginSegments.__post_init__(self)`
  - L84: `ContextSources.__init__(self, slots)`
  - L98: `ContextSources.version(self)`
  - L101: `ContextSources.bump(self)`
  - L106: `ContextSources.add(self, fn, meta)`
  - L151: `ContextSources._register(self, bucket, item)`
  - L171: `ContextSources.collect_segments(self, conversation_id)`
  - L179: `ContextSources._collect_segments(self, conversation_id)`
  - L228: `ContextSources._gather(fn, conversation_id)`

### A.119 `agent/mechanisms/context/tokens.py`

- 类型：Python
- 行数：92
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：上下文 token 粗略估算（纯函数，无装配副作用）。
- 导入：`__future__`, `json`, `typing`
- 顶层符号：
  - L27: `def _is_cjk(ch)`
  - L32: `def approx_tokens_text(text)`
  - L53: `def default_message_tokens(msg)`

### A.120 `agent/mechanisms/conversation_queue.py`

- 类型：Python
- 行数：582
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：会话待发送消息队列：用户输入与 Agent 投递的统一暂存区。
- 导入：`__future__`, `json`, `re`, `shutil`, `threading`, `time`, `uuid`, `pathlib`, `typing`, `agent.core.error_report`, `agent.core.image_embed`, `agent.core.input_attachments`
- 顶层符号：
  - L29: `class QueueError(Exception)`
  - L37: `class ConversationQueue()`
- 类成员：
  - L32: `QueueError.__init__(self, message, code)`
  - L40: `ConversationQueue.__init__(self, storage_dir)`
  - L52: `ConversationQueue.set_change_listener(self, fn)`
  - L58: `ConversationQueue.revision(self, cid)`
  - L64: `ConversationQueue.size(self, cid)`
  - L70: `ConversationQueue.pending_total(self)`
  - L84: `ConversationQueue.list(self, cid)`
  - L96: `ConversationQueue.enqueue(self, cid)`
  - L176: `ConversationQueue.set_insert(self, cid, item_id)`
  - L193: `ConversationQueue.recall(self, cid, item_id)`
  - L209: `ConversationQueue.cancel(self, cid, item_id)`
  - L224: `ConversationQueue.claim_item(self, cid, item_id)`
  - L240: `ConversationQueue.claim_after_turn(self, cid)`
  - L243: `ConversationQueue.claim_insert(self, cid)`
  - L246: `ConversationQueue.has_inserting(self, cid)`
  - L256: `ConversationQueue.claim_insert_batch(self, cid)`
  - L282: `ConversationQueue._claim(self, cid, state)`
  - L309: `ConversationQueue.release(self, cid, item_id)`
  - L323: `ConversationQueue.complete(self, cid, item_id)`
  - L335: `ConversationQueue.resubmit_draft(self, cid, draft_id)`
  - L369: `ConversationQueue._key(self, cid)`
  - L375: `ConversationQueue._queue_dir(self, cid)`
  - L378: `ConversationQueue._ensure_locked(self, cid)`
  - L416: `ConversationQueue._ordered_locked(self, cid)`
  - L420: `ConversationQueue._find_locked(self, cid, item_id)`
  - L427: `ConversationQueue._visible(self, item)`
  - L430: `ConversationQueue._position_locked(self, cid, item_id)`
  - L440: `ConversationQueue._write_item(self, item, blobs)`
  - L478: `ConversationQueue._write_revision(self, cid)`
  - L489: `ConversationQueue._remove_locked(self, cid, item)`
  - L502: `ConversationQueue._remove_empty_queue_dir(base)`
  - L517: `ConversationQueue._bump_locked(self, cid)`
  - L526: `ConversationQueue._snapshot_locked(self, cid)`
  - L537: `ConversationQueue._public(self, item)`
  - L563: `ConversationQueue._read_blob(self, item, attachment_id)`
  - L574: `ConversationQueue._notify(self, cid, snapshot)`

### A.121 `agent/mechanisms/error_log.py`

- 类型：Python
- 行数：122
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：进程级错误日志：JSONL 落盘 + stderr 双写。
- 导入：`__future__`, `json`, `threading`, `traceback`, `datetime`, `pathlib`, `typing`, `agent.core.stderr`
- 顶层符号：
  - L23: `def _iso_now()`
  - L27: `def _exc_parts(exc)`
  - L38: `def _clip(text, limit)`
  - L45: `class ErrorLog()`
- 类成员：
  - L48: `ErrorLog.__init__(self, data_root)`
  - L55: `ErrorLog.path(self)`
  - L58: `ErrorLog.report(self, tag, exc)`
  - L109: `ErrorLog._rotate_if_needed(self)`

### A.122 `agent/mechanisms/executors.py`

- 类型：Python
- 行数：96
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：执行器注册表：工具预览（confirm_id 制）之后谁来真正落盘。
- 导入：`__future__`, `typing`, `agent.core.app_path`
- 顶层符号：
  - L16: `class ExecutorRegistry()`
- 类成员：
  - L19: `ExecutorRegistry.__init__(self, slots)`
  - L25: `ExecutorRegistry._slot_path(name)`
  - L28: `ExecutorRegistry._ensure_slot(self, name, owner)`
  - L37: `ExecutorRegistry.add(self, name, fn, owner)`
  - L56: `ExecutorRegistry.replace(self, name, fn, owner)`
  - L71: `ExecutorRegistry._drop(self, key, fn)`
  - L76: `ExecutorRegistry.get(self, name)`
  - L87: `ExecutorRegistry.names(self)`

### A.123 `agent/mechanisms/file_safety.py`

- 类型：Python
- 行数：331
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：文件安全设施（写路径配套）：版本化备份 + 回收目录。
- 导入：`__future__`, `hashlib`, `json`, `re`, `shutil`, `threading`, `time`, `pathlib`, `typing`, `uuid`, `agent.core.error_report`
- 顶层符号：
  - L61: `def _clip_diff(text)`
  - L70: `def path_hash(path)`
  - L79: `def _stamp()`
  - L94: `def _next_seq(stamp)`
  - L111: `def _version_dir_name()`
  - L120: `def _version_time_text(name)`
  - L128: `def _sha256(data)`
  - L132: `class FileBackups()`
  - L300: `class Recycle()`
  - L322: `def build_file_safety(data_root, backup_root, recycle_root)`
- 类成员：
  - L135: `FileBackups.__init__(self, root)`
  - L140: `FileBackups.group_dir(self, path)`
  - L144: `FileBackups._version_dirs(self, path)`
  - L152: `FileBackups._meta_of(self, version_dir)`
  - L165: `FileBackups.create(self, path)`
  - L210: `FileBackups.list_for(self, path)`
  - L223: `FileBackups.meta(self, mod_id)`
  - L230: `FileBackups.read(self, mod_id)`
  - L242: `FileBackups.prune(self, retention_days)`
  - L303: `Recycle.__init__(self, root)`
  - L306: `Recycle.target_for(self, path)`
  - L312: `Recycle.move(self, path)`

### A.124 `agent/mechanisms/live_state.py`

- 类型：Python
- 行数：478
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：会话实时状态：模式 / 推理档位 / 模型选择 / todo 清单 / 自主与休眠请求。
- 导入：`__future__`, `copy`, `json`, `re`, `threading`, `time`, `pathlib`, `typing`, `agent.common.status`, `agent.core.error_report`
- 顶层符号：
  - L36: `def resolve_goal_max_rounds(value, fallback)`
  - L52: `class ModeConflict(Exception)`
  - L56: `class GoalError(Exception)`
  - L60: `class LiveState()`
  - L442: `def register_command_input_target(key, progress)`
  - L451: `def unregister_command_input_target(key)`
  - L460: `def submit_command_input(key, text)`
- 类成员：
  - L67: `LiveState.__init__(self, storage_dir, default_effort, default_model)`
  - L90: `LiveState.get_mode(self, conversation_id)`
  - L97: `LiveState.set_mode(self, conversation_id, run_type)`
  - L115: `LiveState.get_todo(self, conversation_id)`
  - L129: `LiveState.set_todo(self, conversation_id, todo)`
  - L143: `LiveState.has_active_todo(self, conversation_id)`
  - L150: `LiveState.set_autonomy(self, conversation_id, enabled, summary)`
  - L158: `LiveState.get_autonomy(self, conversation_id)`
  - L170: `LiveState.set_goal(self, conversation_id, text)`
  - L199: `LiveState.get_goal(self, conversation_id)`
  - L207: `LiveState.update_goal(self, conversation_id)`
  - L233: `LiveState.delete_goal(self, conversation_id)`
  - L243: `LiveState.note_goal_round(self, conversation_id)`
  - L256: `LiveState.goal_trigger_text(self, conversation_id)`
  - L268: `LiveState.get_reasoning_effort(self, conversation_id)`
  - L278: `LiveState.set_reasoning_effort(self, conversation_id, effort)`
  - L292: `LiveState.get_model(self, conversation_id)`
  - L304: `LiveState.set_model(self, conversation_id, model)`
  - L328: `LiveState._state_file(self, cid)`
  - L333: `LiveState._ensure_loaded(self, cid)`
  - L388: `LiveState._persist(self, cid)`

### A.125 `agent/mechanisms/mesh.py`

- 类型：Python
- 行数：244
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：会话协作网格：Agent 注册表、运行占位与原子投递。
- 导入：`__future__`, `json`, `threading`, `time`, `uuid`, `pathlib`, `typing`, `agent.common.status`, `agent.core.error_report`, `agent.mechanisms.conversation_queue`, `agent.mechanisms.run_registry`
- 顶层符号：
  - L18: `class MeshState()`
- 类成员：
  - L21: `MeshState.__init__(self, storage_dir)`
  - L42: `MeshState.set_activator(self, activator)`
  - L46: `MeshState.set_session_exists(self, fn)`
  - L50: `MeshState.session_exists(self, cid)`
  - L64: `MeshState.upsert_agent(self, cid)`
  - L84: `MeshState.get_agent(self, cid)`
  - L88: `MeshState.list_agents(self)`
  - L92: `MeshState.remove_agent(self, cid)`
  - L107: `MeshState.queue(self)`
  - L110: `MeshState.queue_size(self, cid)`
  - L115: `MeshState.is_running(self, cid)`
  - L118: `MeshState.running_cids(self)`
  - L121: `MeshState.active_run_id(self, cid)`
  - L124: `MeshState.touch_run(self, cid)`
  - L127: `MeshState.try_begin_run(self, cid)`
  - L135: `MeshState.renew_run(self, cid)`
  - L142: `MeshState.end_run(self, cid)`
  - L146: `MeshState.abort_run(self, cid)`
  - L150: `MeshState._enqueue_message(self, key, message)`
  - L185: `MeshState.submit(self, cid, message)`
  - L215: `MeshState._agents_file(self)`
  - L218: `MeshState._save_agents_locked(self)`
  - L231: `MeshState._load(self)`

### A.126 `agent/mechanisms/prompt_sections.py`

- 类型：Python
- 行数：107
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：系统提示词章节注册表：插件按章节名追加文本，同一章节合并为一个。
- 导入：`__future__`, `re`, `threading`, `typing`, `agent.core.app_path`, `agent.core.error_report`
- 顶层符号：
  - L16: `def _compact_heading_spacing(text)`
  - L23: `class PromptSections()`
- 类成员：
  - L26: `PromptSections.__init__(self, slots)`
  - L36: `PromptSections.add(self, section, fn)`
  - L57: `PromptSections._texts(raw)`
  - L64: `PromptSections.render(self, conversation_id)`
  - L72: `PromptSections._render_sources(self, sources, conversation_id)`
  - L97: `PromptSections._render(self, conversation_id)`
  - L102: `PromptSections.render_after_tools(self, conversation_id)`

### A.127 `agent/mechanisms/prompt_tail.py`

- 类型：Python
- 行数：54
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：请求尾部片段注册表：执行模式之后追加的临时文本，不进系统提示词。
- 导入：`__future__`, `threading`, `typing`, `agent.core.error_report`
- 顶层符号：
  - L11: `class PromptTail()`
- 类成员：
  - L14: `PromptTail.__init__(self)`
  - L18: `PromptTail.add(self, fn)`
  - L37: `PromptTail.render(self, conversation_id)`

### A.128 `agent/mechanisms/provider_registry.py`

- 类型：Python
- 行数：75
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：模型提供者注册表：厂商名 → 构造器。
- 导入：`__future__`, `typing`, `agent.mechanisms.providers.anthropic`, `agent.mechanisms.providers.base`, `agent.mechanisms.providers.openai`
- 顶层符号：
  - L37: `def _pick(options, allowed)`
  - L46: `def _build_openai(options)`
  - L50: `def _build_anthropic(options)`
  - L60: `def known_kinds()`
  - L65: `def build_provider(kind, options)`

### A.129 `agent/mechanisms/provider_router.py`

- 类型：Python
- 行数：156
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：模型路由：把 `request.model` 解析成一个 provider 实例。
- 导入：`__future__`, `copy`, `dataclasses`, `threading`, `typing`, `agent.core.app_path`, `agent.core.error_report`, `agent.core.model_call`, `agent.mechanisms.providers.base`
- 顶层符号：
  - L29: `class ProviderRouter(ModelProvider)`
  - L136: `def _with_wire_model(request, provider)`
- 类成员：
  - L32: `ProviderRouter.__init__(self)`
  - L57: `ProviderRouter.model(self)`
  - L65: `ProviderRouter.allowed_models(self)`
  - L71: `ProviderRouter.default_provider(self)`
  - L75: `ProviderRouter.reload_policy(self)`
  - L90: `ProviderRouter.reload_default(self, provider)`
  - L97: `ProviderRouter.stream(self, request)`
  - L112: `ProviderRouter._select_for_request(self, request, mid, allowed, fallback)`
  - L120: `ProviderRouter._select_provider(self, request, mid, allowed, fallback, resolve)`
  - L131: `ProviderRouter._default_snapshot(self)`

### A.130 `agent/mechanisms/providers/__init__.py`

- 类型：Python
- 行数：3
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：模型提供者适配。
- 顶层符号：无

### A.131 `agent/mechanisms/providers/anthropic.py`

- 类型：Python
- 行数：713
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：Anthropic 原生 Messages API 适配。
- 导入：`__future__`, `json`, `urllib.error`, `urllib.request`, `typing`, `agent.core.error_report`, `agent.core.model_call`, `agent.core.tool_call`, `agent.mechanisms.providers.base`, `agent.mechanisms.providers.debug`, `agent.mechanisms.providers.sse`, `agent.mechanisms.providers.tool_schema`
- 顶层符号：
  - L61: `def messages_url(base_url)`
  - L77: `def _upstream_message(body)`
  - L91: `def _warn(message)`
  - L99: `def _system_text(messages)`
  - L110: `def _meta_blocks(m)`
  - L130: `def strip_stale_thinking(messages, turn_start)`
  - L164: `def _assistant_tool_ids(messages)`
  - L196: `def drop_dangling_tool_results(messages)`
  - L221: `def _image_block(url)`
  - L242: `def _user_blocks(content)`
  - L266: `def _tool_result_content(content)`
  - L280: `def _to_anthropic_messages(messages, turn_start)`
  - L357: `def _tools_payload(tools)`
  - L380: `def _stop_reason_note(reason)`
  - L384: `def _tool_turn_missing_thinking(messages, turn_start)`
  - L406: `class AnthropicProvider(ModelProvider)`
  - L543: `def _positive_int(value, fallback)`
  - L552: `def _empty_block()`
  - L558: `def _consume_block_start(data, blocks)`
  - L579: `def _consume_block_delta(data, blocks)`
  - L605: `def _consume_block_stop(data, blocks, calls, thinking)`
  - L626: `def _assemble_deltas(chunks)`
  - L676: `def _tool_call(raw_id, raw_name, arguments_json)`
  - L688: `def _usage_payload(usage)`
  - L701: `def _int(value)`
  - L709: `def _random_suffix()`
- 类成员：
  - L409: `AnthropicProvider.__init__(self)`
  - L434: `AnthropicProvider._thinking_enabled(self)`
  - L454: `AnthropicProvider.build_payload(self, request)`
  - L495: `AnthropicProvider._headers(self)`
  - L504: `AnthropicProvider._http_error(self, status, body)`
  - L513: `AnthropicProvider._post_stream(self, url, payload)`
  - L533: `AnthropicProvider.stream(self, request)`

### A.132 `agent/mechanisms/providers/base.py`

- 类型：Python
- 行数：24
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：模型提供者协议与错误类型。
- 导入：`__future__`, `typing`, `agent.core.model_call`
- 顶层符号：
  - L10: `class ModelRequestError(Exception)`
  - L19: `class ModelProvider()`
- 类成员：
  - L13: `ModelRequestError.__init__(self, detail)`
  - L22: `ModelProvider.stream(self, request)`

### A.133 `agent/mechanisms/providers/debug.py`

- 类型：Python
- 行数：10
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：Provider 调试开关。
- 导入：`__future__`, `os`
- 顶层符号：无

### A.134 `agent/mechanisms/providers/echo.py`

- 类型：Python
- 行数：33
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：Echo 假模型。
- 导入：`__future__`, `typing`, `uuid`, `agent.core.model_call`, `agent.core.tool_call`, `agent.mechanisms.providers.base`
- 顶层符号：
  - L13: `class EchoProvider(ModelProvider)`
- 类成员：
  - L19: `EchoProvider.stream(self, request)`

### A.135 `agent/mechanisms/providers/missing.py`

- 类型：Python
- 行数：19
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：未配置模型时的占位 provider。
- 导入：`__future__`, `typing`, `agent.core.model_call`, `agent.mechanisms.providers.base`
- 顶层符号：
  - L11: `class MissingProvider(ModelProvider)`
- 类成员：
  - L16: `MissingProvider.stream(self, request)`

### A.136 `agent/mechanisms/providers/openai.py`

- 类型：Python
- 行数：525
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：OpenAI 兼容模型适配。
- 导入：`__future__`, `json`, `os`, `re`, `urllib.error`, `urllib.request`, `pathlib`, `typing`, `uuid`, `agent.core.error_report`, `agent.core.model_call`, `agent.core.tool_call`, `agent.mechanisms.providers.base`, `agent.mechanisms.providers.debug`, `agent.mechanisms.providers.sse`, `agent.mechanisms.providers.tool_schema`
- 顶层符号：
  - L41: `def _chat_completions_url(base_url)`
  - L58: `def _best_reasoning_field(message)`
  - L68: `def _tool_call_request(raw_id, name, arguments_json)`
  - L81: `def _merge_tool_call_fragments(fragments)`
  - L109: `def _tool_calls_from_snapshot_message(message)`
  - L136: `def _assemble_stream_deltas(chunks)`
  - L202: `def _upstream_error_message(body)`
  - L226: `def _to_wire_tool(tool)`
  - L244: `def _to_wire_messages(messages)`
  - L320: `def _append_request_log(line)`
  - L333: `def describe_request(model, url, payload)`
  - L375: `class OpenAICompatibleProvider(ModelProvider)`
- 类成员：
  - L385: `OpenAICompatibleProvider.__init__(self)`
  - L405: `OpenAICompatibleProvider.stream(self, request)`
  - L473: `OpenAICompatibleProvider._is_local_model(self, model)`
  - L484: `OpenAICompatibleProvider._headers(self)`
  - L492: `OpenAICompatibleProvider._post_stream(self, url, payload)`
  - L512: `OpenAICompatibleProvider._http_error(self, status, body)`
  - L523: `OpenAICompatibleProvider._is_deepseek(self)`

### A.137 `agent/mechanisms/providers/sse.py`

- 类型：Python
- 行数：74
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：SSE 行解析与流总超时。
- 导入：`__future__`, `json`, `threading`, `typing`, `agent.core.error_report`, `agent.mechanisms.providers.base`
- 顶层符号：
  - L13: `def parse_sse_lines(lines)`
  - L37: `def stream_with_timeout(resp, timeout)`

### A.138 `agent/mechanisms/providers/tool_schema.py`

- 类型：Python
- 行数：40
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：Provider 共用的工具 schema 规范化。
- 导入：`__future__`, `typing`
- 顶层符号：
  - L8: `def _object_schema(raw)`
  - L18: `def tool_parameters(tool)`

### A.139 `agent/mechanisms/quality/__init__.py`

- 类型：Python
- 行数：48
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：写盘门控与质量管线包 — id 制四步协议（预览 → 确认 → 凭 ID 提交 → 重读）+ 三段检查。
- 导入：`__future__`, `agent.mechanisms.quality.checks`, `agent.mechanisms.quality.diagnose`, `agent.mechanisms.quality.gate`, `agent.mechanisms.quality.path_keys`, `agent.mechanisms.quality.pending`, `agent.mechanisms.quality.pipeline_bridge`
- 顶层符号：无

### A.140 `agent/mechanisms/quality/checks.py`

- 类型：Python
- 行数：306
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：写前检查：WriteContext、路径命中、大 diff 边界与 check_write 判定。
- 导入：`__future__`, `difflib`, `os`, `dataclasses`, `pathlib`, `typing`, `agent.core.tool_call`, `agent.mechanisms.quality.path_keys`
- 顶层符号：
  - L27: `class WriteContext()`
  - L33: `def _same_path(a, b)`
  - L51: `def _in_paths(path, paths)`
  - L63: `def _clip_line(text, limit)`
  - L71: `def _line_no_at(text, index)`
  - L76: `def reread_anchors(tool, arguments, path)`
  - L126: `def _join_unified_diff(lines)`
  - L143: `def diff_text(old, new, path)`
  - L166: `def change_payload(old_text, new_text, path)`
  - L203: `def _unlock_decision(rec)`
  - L217: `def _scope_decision(gate, rec, tool, args, path)`
  - L251: `def _size_decision(tool, args)`
  - L287: `def check_write(gate, wc)`

### A.141 `agent/mechanisms/quality/diagnose.py`

- 类型：Python
- 行数：115
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：写后诊断：大删除检测、本地 py/json 检查与质量报告。
- 导入：`__future__`, `ast`, `json`, `py_compile`, `tempfile`, `pathlib`, `typing`, `agent.common.status`, `agent.core.error_report`, `agent.mechanisms.quality.path_keys`
- 顶层符号：
  - L27: `def flag_diag_fail(gate, summary)`
  - L34: `def maybe_flag_large_delete(gate, path, diff_text)`
  - L52: `def run_post_write_checks(gate, path)`
  - L90: `def build_quality_report(gate, path)`

### A.142 `agent/mechanisms/quality/gate.py`

- 类型：Python
- 行数：167
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：QualityGate：组合预览仓库、写前检查与写后诊断。
- 导入：`__future__`, `re`, `dataclasses`, `typing`, `agent.mechanisms.quality.checks`, `agent.mechanisms.quality.diagnose`, `agent.common.status`, `agent.core.tool_call`, `agent.mechanisms.quality.checks`, `agent.mechanisms.quality.path_keys`, `agent.mechanisms.quality.pending`
- 顶层符号：
  - L26: `class QualityGate()`
- 类成员：
  - L51: `QualityGate._pending(self)`
  - L55: `QualityGate.path_keys(self, tool)`
  - L66: `QualityGate.register_preview(self, tool, arguments)`
  - L72: `QualityGate.peek(self, confirm_id)`
  - L76: `QualityGate.take_record(self, confirm_id)`
  - L80: `QualityGate.take(self, confirm_id)`
  - L84: `QualityGate.discard(self, confirm_id)`
  - L89: `QualityGate.confirm(self, confirm_id)`
  - L94: `QualityGate.check_write(self, wc)`
  - L99: `QualityGate.note_committed(self, path)`
  - L123: `QualityGate._unlocked_before_latest_write(self, rec)`
  - L132: `QualityGate.note_read(self, path)`
  - L136: `QualityGate.review_done(self)`
  - L151: `QualityGate.set_intent(self, intent)`
  - L156: `QualityGate.note_evidence(self)`
  - L160: `QualityGate.note_assistant_text(self, text)`

### A.143 `agent/mechanisms/quality/path_keys.py`

- 类型：Python
- 行数：27
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：写目标路径解析：只认调用方传入的参数键序，不维护进程全局键表。
- 导入：`__future__`, `typing`
- 顶层符号：
  - L8: `def norm_path(p)`
  - L13: `def resolve_write_path(args, keys)`

### A.144 `agent/mechanisms/quality/pending.py`

- 类型：Python
- 行数：120
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：未提交预览快照仓库（confirm_id → tool / arguments / confirmed / path）。
- 导入：`__future__`, `copy`, `threading`, `typing`, `uuid`, `agent.mechanisms.quality.path_keys`
- 顶层符号：
  - L19: `class PendingStore()`
- 类成员：
  - L22: `PendingStore.__init__(self)`
  - L31: `PendingStore.records(self)`
  - L40: `PendingStore.register_preview(self, tool, arguments)`
  - L78: `PendingStore.peek(self, confirm_id)`
  - L87: `PendingStore.take_record(self, confirm_id)`
  - L93: `PendingStore.take(self, confirm_id)`
  - L100: `PendingStore.discard(self, confirm_id)`
  - L109: `PendingStore.confirm(self, confirm_id)`

### A.145 `agent/mechanisms/quality/pipeline_bridge.py`

- 类型：Python
- 行数：136
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：工具管道桥接（id 制）：把 gate 挂到 ToolPipeline 的 pre / post 钩子。
- 导入：`__future__`, `typing`, `agent.common.status`, `agent.core.session_scope`, `agent.core.tool_call`, `agent.mechanisms.quality.checks`, `agent.mechanisms.quality.diagnose`, `agent.mechanisms.quality.gate`
- 顶层符号：
  - L25: `def _mode_decision(live_state)`
  - L41: `def _post_preview(call, result, session_gate)`
  - L52: `def _post_commit(call, result, session_gate, info, needs_reread)`
  - L66: `def build_pipeline_gate()`

### A.146 `agent/mechanisms/run_registry.py`

- 类型：Python
- 行数：444
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：运行态登记（可替换实现）：回答"某个会话的回合是不是正在跑"。
- 导入：`__future__`, `json`, `os`, `sys`, `threading`, `time`, `pathlib`, `typing`, `agent.core.error_report`
- 顶层符号：
  - L68: `class RunRegistry(Protocol)`
  - L109: `class InMemoryRunRegistry()`
  - L154: `class FileRunRegistry()`
  - L431: `def build_run_registry(directory)`
- 类成员：
  - L74: `RunRegistry.claim(self, cid, run_id)`
  - L78: `RunRegistry.release(self, cid)`
  - L82: `RunRegistry.renew(self, cid, run_id)`
  - L92: `RunRegistry.touch(self, cid)`
  - L96: `RunRegistry.running(self, cid)`
  - L100: `RunRegistry.running_cids(self)`
  - L104: `RunRegistry.active_run_id(self, cid)`
  - L112: `InMemoryRunRegistry.__init__(self)`
  - L116: `InMemoryRunRegistry.claim(self, cid, run_id)`
  - L126: `InMemoryRunRegistry.release(self, cid)`
  - L130: `InMemoryRunRegistry.renew(self, cid, run_id)`
  - L138: `InMemoryRunRegistry.touch(self, cid)`
  - L141: `InMemoryRunRegistry.running(self, cid)`
  - L145: `InMemoryRunRegistry.running_cids(self)`
  - L149: `InMemoryRunRegistry.active_run_id(self, cid)`
  - L163: `FileRunRegistry.__init__(self, directory)`
  - L176: `FileRunRegistry._file(self, cid)`
  - L181: `FileRunRegistry._read(self, fp)`
  - L189: `FileRunRegistry._pid_alive(pid)`
  - L254: `FileRunRegistry._fresh(self, rec)`
  - L274: `FileRunRegistry._write(self, fp, rec)`
  - L285: `FileRunRegistry._drop(self, fp)`
  - L295: `FileRunRegistry._create(self, fp, rec)`
  - L316: `FileRunRegistry.claim(self, cid, run_id)`
  - L346: `FileRunRegistry.release(self, cid)`
  - L355: `FileRunRegistry.renew(self, cid, run_id)`
  - L372: `FileRunRegistry.touch(self, cid)`
  - L393: `FileRunRegistry.running(self, cid)`
  - L409: `FileRunRegistry.running_cids(self)`
  - L419: `FileRunRegistry.active_run_id(self, cid)`

### A.147 `agent/mechanisms/session_crypto.py`

- 类型：Python
- 行数：143
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：会话日志的行级加密与密钥管理。
- 导入：`__future__`, `base64`, `hashlib`, `hmac`, `json`, `os`, `threading`, `pathlib`, `typing`, `agent.core.error_report`, `agent.mechanisms.session_locking`
- 顶层符号：
  - L33: `def _xor_stream(data, key, nonce)`
  - L44: `class SessionCipher()`
- 类成员：
  - L47: `SessionCipher.__init__(self, data_root, mode, key_path)`
  - L56: `SessionCipher.encrypt_line(self, plain)`
  - L73: `SessionCipher.decrypt_line(self, line)`
  - L102: `SessionCipher._session_key(self)`
  - L111: `SessionCipher._load_or_create_key_material(self)`
  - L139: `SessionCipher._app_entropy()`

### A.148 `agent/mechanisms/session_lines.py`

- 类型：Python
- 行数：103
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：会话日志的行编解码：短键、存储坐标与事件对象的互转。
- 导入：`__future__`, `json`, `typing`, `agent.core.events`
- 顶层符号：
  - L38: `def valid_seq(raw)`
  - L43: `def seq_from_obj(obj)`
  - L51: `def event_seq(event)`
  - L59: `def event_to_json(event)`
  - L83: `def event_from_obj(obj, conversation_id)`

### A.149 `agent/mechanisms/session_locking.py`

- 类型：Python
- 行数：132
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：跨进程排它锁：按目标文件加锁，争用超时就失败。
- 导入：`__future__`, `os`, `time`, `contextlib`, `pathlib`, `typing`, `agent.core.error_report`
- 顶层符号：
  - L31: `def cross_process_lock(path)`
  - L101: `def _acquire_lock(fh)`
  - L126: `def _lock_timeout()`

### A.150 `agent/mechanisms/session_store.py`

- 类型：Python
- 行数：681
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：会话持久化：加密 append-only 事件日志。
- 导入：`__future__`, `json`, `os`, `re`, `threading`, `uuid`, `pathlib`, `typing`, `agent.core.error_report`, `agent.core.events`, `agent.mechanisms.session_crypto`, `agent.mechanisms.session_lines`, `agent.mechanisms.session_locking`
- 顶层符号：
  - L56: `def new_conversation_id()`
  - L61: `def is_valid_conversation_id(conversation_id)`
  - L71: `class SessionStore()`
- 类成员：
  - L74: `SessionStore.__init__(self, data_root)`
  - L124: `SessionStore._append_lock(self, path)`
  - L144: `SessionStore.add_scan_dir(self, path)`
  - L153: `SessionStore.allocate_seq(self, count)`
  - L178: `SessionStore._observe(self, seq)`
  - L183: `SessionStore._scan_max_seq(self)`
  - L219: `SessionStore.raw_path(self, conversation_id)`
  - L228: `SessionStore.append(self, conversation_id, events)`
  - L270: `SessionStore.append_if_absent(self, conversation_id, should_skip, events)`
  - L310: `SessionStore.flush_pending(self, conversation_id)`
  - L321: `SessionStore.flush_all(self)`
  - L341: `SessionStore._pending_only_new(self, conversation_id, batch)`
  - L362: `SessionStore._written_seqs(self, conversation_id)`
  - L384: `SessionStore._file_fp(path)`
  - L398: `SessionStore._last_good_end(path)`
  - L435: `SessionStore._disk_seqs(self, conversation_id)`
  - L457: `SessionStore._take_pending(self, conversation_id)`
  - L468: `SessionStore._put_pending(self, conversation_id, batch)`
  - L492: `SessionStore._render_rows(self, conversation_id, rows_events)`
  - L510: `SessionStore._append_rows(self, path, rows)`
  - L514: `SessionStore._append_rows_locked(self, path, rows)`
  - L542: `SessionStore._pending_write(self, conversation_id, rows_events, exc)`
  - L550: `SessionStore._write_rows(self, conversation_id, rows_events, requested)`
  - L570: `SessionStore.line_count(self, conversation_id)`
  - L587: `SessionStore.load(self, conversation_id)`
  - L591: `SessionStore.load_with_seq(self, conversation_id)`
  - L604: `SessionStore._load_path(self, path, conversation_id)`
  - L624: `SessionStore.tail_from(self, conversation_id, after_seq)`
  - L634: `SessionStore.tail_across(self, after_seq, limit)`
  - L657: `SessionStore._encrypt_line(self, plain)`
  - L664: `SessionStore._decrypt_line(self, line)`
  - L668: `SessionStore._parse_obj(self, line)`

### A.151 `agent/mechanisms/session_title.py`

- 类型：Python
- 行数：168
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：会话标题生成。
- 导入：`__future__`, `re`, `pathlib`, `typing`, `agent.core.error_report`, `agent.core.ports`
- 顶层符号：
  - L38: `def is_placeholder_title(title)`
  - L43: `def clean_title(raw)`
  - L61: `def _is_system_notice(text)`
  - L65: `def fallback_title(messages)`
  - L78: `def make_provider_title_generator(provider)`
  - L109: `def _material_from_messages(messages)`
  - L134: `class TitleStore()`
- 类成员：
  - L137: `TitleStore.__init__(self, titles_dir)`
  - L140: `TitleStore._path(self, cid)`
  - L146: `TitleStore.load(self, cid)`
  - L156: `TitleStore.save(self, cid, title)`

### A.152 `agent/mechanisms/wake_scheduler.py`

- 类型：Python
- 行数：499
- 所属主模块：`app/runtime/host`
- 文件角色：runtime/implementation
- 文件说明：会话唤醒调度：单线程定时器、持久化任务与队列投递。
- 导入：`__future__`, `json`, `math`, `os`, `shutil`, `sys`, `threading`, `time`, `uuid`, `dataclasses`, `datetime`, `pathlib`, `typing`, `agent.core.error_report`, `agent.core.thread_context`
- 顶层符号：
  - L44: `class WakeJob()`
  - L59: `class WakeJobStore()`
  - L123: `class _SchedulerProcessLock()`
  - L179: `def _pid_alive(pid)`
  - L193: `def _windows_pid_alive(pid)`
  - L220: `class WakeScheduler()`
  - L482: `def parse_due_at(value, now)`
- 类成员：
  - L55: `WakeJob.public(self)`
  - L62: `WakeJobStore.__init__(self, storage_dir)`
  - L66: `WakeJobStore.load(self)`
  - L98: `WakeJobStore.save(self, jobs)`
  - L114: `WakeJobStore._quarantine(self)`
  - L126: `_SchedulerProcessLock.__init__(self, storage_dir)`
  - L130: `_SchedulerProcessLock.acquire(self)`
  - L162: `_SchedulerProcessLock.release(self)`
  - L171: `_SchedulerProcessLock._read_holder(self)`
  - L223: `WakeScheduler.__init__(self, storage_dir)`
  - L250: `WakeScheduler.start(self)`
  - L269: `WakeScheduler.stop(self)`
  - L282: `WakeScheduler.schedule(self)`
  - L317: `WakeScheduler.schedule_seconds(self, seconds)`
  - L328: `WakeScheduler.schedule_at(self, at)`
  - L333: `WakeScheduler.cancel(self, job_id)`
  - L353: `WakeScheduler.list_jobs(self)`
  - L365: `WakeScheduler.run_due(self, now)`
  - L390: `WakeScheduler._loop(self)`
  - L408: `WakeScheduler._deliver(self, job, now)`
  - L439: `WakeScheduler._is_delivered(self, job)`
  - L449: `WakeScheduler._settle(self, job, status, error, now)`
  - L462: `WakeScheduler._prune_locked(self)`
  - L471: `WakeScheduler._save_locked(self)`

### A.153 `agent/session_paths.py`

- 类型：Python
- 行数：29
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：会话运行态的目录布局。
- 导入：`__future__`, `pathlib`
- 顶层符号：
  - L8: `def session_root(data_root)`
  - L12: `def state_dir(data_root)`
  - L16: `def raw_dir(data_root)`
  - L20: `def titles_dir(data_root)`
  - L24: `def ensure_layout(data_root)`

### A.154 `agent/shell/classic_adapter/__init__.py`

- 类型：Python
- 行数：28
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：经典界面适配层（内核 ↔ 浏览器界面之间的双向翻译）。
- 导入：`__future__`, `agent.shell.classic_adapter.adapter`
- 顶层符号：无

### A.155 `agent/shell/classic_adapter/adapter.py`

- 类型：Python
- 行数：263
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：适配层门面：`ClassicAdapter`。
- 导入：`__future__`, `typing`, `agent.shell.classic_adapter.contract`, `agent.common.status`, `agent.core.error_report`, `agent.core.input_attachments`, `agent.shell.classic_adapter.channel`, `agent.shell.classic_adapter.confirm`, `agent.shell.classic_adapter.inbound`, `agent.shell.classic_adapter.outbound`
- 顶层符号：
  - L36: `class ClassicAdapter(ChannelMixin, ConfirmMixin, Inbound)`
- 类成员：
  - L39: `ClassicAdapter.__init__(self, app)`
  - L54: `ClassicAdapter.inbound(self)`
  - L60: `ClassicAdapter._stream(self, cid)`
  - L72: `ClassicAdapter._layout_for(self, cid)`
  - L93: `ClassicAdapter._mode_of(self, cid)`
  - L99: `ClassicAdapter._model(self, cid)`
  - L129: `ClassicAdapter.adopt_shell(self, shell)`
  - L133: `ClassicAdapter.drop_session(self, cid)`
  - L148: `ClassicAdapter.dispose(self)`
  - L157: `ClassicAdapter.feed(self, ev_type, data)`
  - L189: `ClassicAdapter.conversation_frame(self, cid)`
  - L209: `ClassicAdapter.health(self)`
  - L260: `ClassicAdapter._kernel_name(self)`

### A.156 `agent/shell/classic_adapter/channel.py`

- 类型：Python
- 行数：318
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：SSE 通道：连接队列、广播、心跳与断线续传。
- 导入：`__future__`, `json`, `queue`, `threading`, `time`, `typing`, `agent.shell.classic_adapter.contract`, `agent.core.error_report`
- 顶层符号：
  - L30: `class ChannelMixin()`
  - L273: `class ClassicSseChannel()`
- 类成员：
  - L39: `ChannelMixin._init_channels(self)`
  - L48: `ChannelMixin.bind_bus(self, event_bus)`
  - L59: `ChannelMixin._ensure_subscribed(self)`
  - L67: `ChannelMixin._drop_subscription(self)`
  - L80: `ChannelMixin.channel_count(self)`
  - L86: `ChannelMixin.subscribed(self)`
  - L90: `ChannelMixin.attach(self)`
  - L104: `ChannelMixin.detach(self, box)`
  - L113: `ChannelMixin.next_frame(self, box, timeout)`
  - L125: `ChannelMixin.heartbeat(self)`
  - L130: `ChannelMixin.announce_plugins(self, loaded)`
  - L138: `ChannelMixin.announce_model(self, cid, model)`
  - L153: `ChannelMixin.announce_settings(self)`
  - L157: `ChannelMixin.announce_plugin_config(self, plugin)`
  - L164: `ChannelMixin.announce_plugin_event(self, plugin, event, payload)`
  - L169: `ChannelMixin._broadcast(self, frame)`
  - L176: `ChannelMixin._push_frames(self, channels, frames)`
  - L204: `ChannelMixin.replay_after(self, after_seq, only, limit)`
  - L233: `ChannelMixin.latest_seq(self)`
  - L244: `ChannelMixin.cursor_of(self, request_headers, query)`
  - L276: `ClassicSseChannel.__init__(self, adapter, heartbeat)`
  - L283: `ClassicSseChannel.close(self)`
  - L286: `ClassicSseChannel.resume(self, after_seq)`
  - L293: `ClassicSseChannel.next_payload(self)`

### A.157 `agent/shell/classic_adapter/confirm.py`

- 类型：Python
- 行数：291
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：会话暂停态与用户确认回路。
- 导入：`__future__`, `typing`, `agent.shell.classic_adapter.contract`, `agent.core.error_report`
- 顶层符号：
  - L18: `class ConfirmMixin()`
- 类成员：
  - L21: `ConfirmMixin.is_paused(self, cid)`
  - L34: `ConfirmMixin.pause_state(self)`
  - L45: `ConfirmMixin.pending_confirms(self)`
  - L73: `ConfirmMixin.user_confirm(self, cid, body)`
  - L115: `ConfirmMixin.submit_user_choice(self, cid, text)`
  - L195: `ConfirmMixin.submit_approval(self, cid, agreed)`
  - L263: `ConfirmMixin._session(self, cid)`
  - L270: `ConfirmMixin.pending_confirm(self, cid)`
  - L283: `ConfirmMixin._clear_pending(self, cid)`

### A.158 `agent/shell/classic_adapter/contract.py`

- 类型：Python
- 行数：220
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：经典界面契约常量（适配层的单一事实源）。
- 导入：`__future__`, `re`, `typing`
- 顶层符号：
  - L25: `def normalize_cid(value)`
  - L31: `def safe_count(value)`
  - L92: `def plugin_event_frame(plugin, event, payload)`
  - L149: `def tool_script(kernel_tool_name)`
  - L191: `def normalize_mode(value)`
  - L197: `def public_tool_images(raw)`

### A.159 `agent/shell/classic_adapter/history.py`

- 类型：Python
- 行数：259
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：经典 UI 历史事件折叠。
- 导入：`__future__`, `hashlib`, `json`, `typing`, `agent.shell.classic_adapter.contract`, `agent.core.error_report`, `agent.core.state_values`
- 顶层符号：
  - L22: `def attachment_id(data_base64, index)`
  - L36: `def _split_user_content(content)`
  - L70: `def _user_item(data, resolved)`
  - L101: `def _model_items(data, elapsed, reasoning_elapsed)`
  - L119: `def _compaction_item(data)`
  - L134: `def _tool_started_item(data)`
  - L147: `def _tool_preview(item, kind, data)`
  - L174: `def _apply_tool_event(items, kind, data)`
  - L200: `def _apply_progress(items, data)`
  - L211: `def history_items(events)`
  - L252: `def last_payload(events, kind)`

### A.160 `agent/shell/classic_adapter/history_page.py`

- 类型：Python
- 行数：148
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：会话历史分页：轮次折叠、字符成本与页选择。
- 导入：`__future__`, `copy`, `json`, `dataclasses`, `typing`, `agent.shell.classic_adapter.history`
- 顶层符号：
  - L19: `class Round()`
  - L29: `class Page()`
  - L41: `def item_cost(item)`
  - L67: `def _seq(event)`
  - L76: `def _copy_items(items)`
  - L80: `def fold_rounds(events)`
  - L111: `def _flatten(rounds)`
  - L115: `def _attachments(rounds)`
  - L119: `def select_page(rounds)`

### A.161 `agent/shell/classic_adapter/inbound.py`

- 类型：Python
- 行数：506
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：入站适配：经典 UI 的请求 → 内核调用 → 经典 UI 期望的返回体（前端 → 服务端）。
- 导入：`__future__`, `base64`, `time`, `collections`, `pathlib`, `typing`, `agent.shell.classic_adapter.contract`, `agent.common.status`, `agent.core.error_report`, `agent.core.events`, `agent.core.state_values`, `agent.mechanisms.session_title`, `agent.shell.classic_adapter.history`, `agent.shell.classic_adapter.history`, `agent.shell.classic_adapter.history_page`, `agent.shell.classic_adapter.layout`, `agent.shell.classic_adapter.sessions`, `agent.shell.classic_adapter.state`
- 顶层符号：
  - L42: `class Inbound()`
- 类成员：
  - L45: `Inbound.__init__(self, app, state)`
  - L54: `Inbound._mode_of(self, cid)`
  - L60: `Inbound._model(self, cid)`
  - L81: `Inbound.sessions(self)`
  - L126: `Inbound._derived_title(self, path)`
  - L147: `Inbound._history_rounds(self, cid, store)`
  - L180: `Inbound.history(self, cid, store)`
  - L241: `Inbound._mark_stale_suspends(self, cid, items)`
  - L254: `Inbound._load_events(self, cid, store)`
  - L280: `Inbound.ui_state_get(self)`
  - L297: `Inbound._with_running(self, payload)`
  - L322: `Inbound.ui_state_put(self, body)`
  - L332: `Inbound.title(self, cid)`
  - L359: `Inbound._fallback_title(self, cid)`
  - L364: `Inbound._hydrate_usage(self, cid)`
  - L376: `Inbound.usage_get(self, cid)`
  - L389: `Inbound.usage_put(self, cid, body)`
  - L425: `Inbound.command_input(self, cid, body)`
  - L446: `Inbound.attachment(self, cid, ident)`
  - L471: `Inbound.remember_attachments(self, cid, images)`
  - L497: `Inbound.model_in_allowed(self, model, allowed)`

### A.162 `agent/shell/classic_adapter/layout.py`

- 类型：Python
- 行数：310
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：经典 UI 上下文布局。
- 导入：`__future__`, `threading`, `collections`, `typing`, `agent.core.error_report`, `agent.mechanisms.context`, `agent.mechanisms.context.tokens`, `agent.shell.classic_adapter.contract`
- 顶层符号：
  - L28: `def compute_context_layout(app, events, cid)`
  - L63: `def _sources_version(app)`
  - L72: `def _overlay_plugin_segments(app, cid, payload)`
  - L128: `def _budget_of(app, cid)`
  - L142: `def _last_segments(events, budget_tokens)`
  - L161: `def _rescale(payload, budget_tokens)`
  - L190: `def _mode_of(events)`
  - L210: `def _fallback_layout(app, events, cid)`
  - L269: `def _context_window(app, cid)`
  - L277: `def _covered_end_of(events)`
  - L292: `def current_todo(app, cid)`

### A.163 `agent/shell/classic_adapter/outbound.py`

- 类型：Python
- 行数：104
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：出站适配：内核事件 → 经典 UI 认得的事件（服务端 → 前端）。
- 导入：`__future__`, `typing`, `agent.shell.classic_adapter.contract`, `agent.shell.classic_adapter.outbound_tools`, `agent.shell.classic_adapter.outbound_turns`
- 顶层符号：
  - L27: `class ClassicStream(ToolFrames, TurnFrames)`
- 类成员：
  - L34: `ClassicStream.__init__(self, conversation_id)`
  - L71: `ClassicStream._ev(self, type_)`
  - L86: `ClassicStream.translate(self, ev_type, data)`

### A.164 `agent/shell/classic_adapter/outbound_tools.py`

- 类型：Python
- 行数：335
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：出站适配的工具事件族：`tool_*` 内核事实 → 经典界面的工具卡帧。
- 导入：`__future__`, `dataclasses`, `typing`, `agent.shell.classic_adapter.contract`, `agent.core.state_values`
- 顶层符号：
  - L16: `class PendingToolCall()`
  - L24: `class ToolFrames()`
  - L308: `def _preview_json(script, data, error, ok, elapsed_s)`
- 类成员：
  - L27: `ToolFrames._on_tool_call(self, d)`
  - L41: `ToolFrames._on_tool_progress(self, d)`
  - L60: `ToolFrames._on_tool_suspended(self, d)`
  - L141: `ToolFrames._on_turn_awaiting_user(self, d)`
  - L174: `ToolFrames._on_tool_started(self, d)`
  - L190: `ToolFrames._on_tool_done(self, d)`
  - L194: `ToolFrames._on_tool_failed(self, d)`
  - L198: `ToolFrames._on_tool_canceled(self, d)`
  - L208: `ToolFrames._on_tool_result(self, d)`
  - L216: `ToolFrames._on_tool_ended(self, d)`
  - L229: `ToolFrames._finish_tool(self, d)`

### A.165 `agent/shell/classic_adapter/outbound_turns.py`

- 类型：Python
- 行数：343
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：出站适配的回合与模型事件族：回合边界、LLM 卡片、用量与上下文布局。
- 导入：`__future__`, `typing`, `agent.shell.classic_adapter.contract`, `agent.core.error_report`
- 顶层符号：
  - L14: `class TurnFrames()`
- 类成员：
  - L17: `TurnFrames._on_turn_started(self, d)`
  - L41: `TurnFrames._resolve_mode(self)`
  - L47: `TurnFrames._resolve_model(self)`
  - L52: `TurnFrames._on_queue_updated(self, d)`
  - L59: `TurnFrames._on_input_claimed(self, d)`
  - L106: `TurnFrames._on_step_started(self, d)`
  - L110: `TurnFrames._on_llm_call_start(self, d)`
  - L119: `TurnFrames._on_llm_started(self, d)`
  - L138: `TurnFrames._begin_llm_round(self, d)`
  - L152: `TurnFrames._request_params(self, d)`
  - L171: `TurnFrames._on_reasoning_delta(self, d)`
  - L177: `TurnFrames._on_assistant_delta(self, d)`
  - L183: `TurnFrames._on_model_message(self, d)`
  - L220: `TurnFrames._on_usage(self, d)`
  - L231: `TurnFrames._on_context_layout(self, d)`
  - L240: `TurnFrames._on_error(self, d)`
  - L248: `TurnFrames._on_turn_ended(self, d)`
  - L299: `TurnFrames._on_context_compacted(self, d)`
  - L325: `TurnFrames._emit_layout(self)`

### A.166 `agent/shell/classic_adapter/plugin_events.py`

- 类型：Python
- 行数：31
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：插件事件发布器：把插件产生的非事实帧送到经典界面 SSE。
- 导入：`__future__`, `typing`
- 顶层符号：
  - L16: `class PluginEventPublisher()`
- 类成员：
  - L19: `PluginEventPublisher.__init__(self, adapter)`
  - L22: `PluginEventPublisher.__call__(self, plugin, event, payload)`
  - L26: `PluginEventPublisher.connected(self)`

### A.167 `agent/shell/classic_adapter/sessions.py`

- 类型：Python
- 行数：16
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：经典 UI 会话日期分组。
- 导入：`__future__`, `typing`, `agent.shell.timefmt`
- 顶层符号：
  - L10: `def session_date_group(mtime, now)`

### A.168 `agent/shell/classic_adapter/state.py`

- 类型：Python
- 行数：151
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：经典 UI 会话级状态。
- 导入：`__future__`, `threading`, `time`, `typing`
- 顶层符号：
  - L10: `class ClassicState()`
- 类成员：
  - L21: `ClassicState.__init__(self)`
  - L28: `ClassicState.add_usage(self, cid, data)`
  - L48: `ClassicState.set_usage(self, cid, data)`
  - L69: `ClassicState.get_usage(self, cid)`
  - L89: `ClassicState.has_usage(self, cid)`
  - L93: `ClassicState.reset_usage(self, cid)`
  - L98: `ClassicState.set_command_input(self, cid, payload)`
  - L102: `ClassicState.take_command_input(self, cid)`
  - L108: `ClassicState.put_attachments(self, cid, items)`
  - L112: `ClassicState.merge_attachments(self, cid, items)`
  - L131: `ClassicState.get_attachment(self, cid, ident)`
  - L138: `ClassicState.clear_attachments(self, cid)`
  - L142: `ClassicState.drop_session(self, cid)`

### A.169 `agent/shell/cli/__init__.py`

- 类型：Python
- 行数：1
- 所属主模块：`app/shell/cli`
- 文件角色：runtime/implementation
- 顶层符号：无

### A.170 `agent/shell/cli/headless.py`

- 类型：Python
- 行数：153
- 所属主模块：`app/shell/cli`
- 文件角色：runtime/implementation
- 文件说明：headless 壳：无 UI 运行一个回合，使用与 Web 相同的提示词与上下文装配。
- 导入：`__future__`, `argparse`, `queue`, `sys`, `threading`, `time`, `typing`, `agent.core.error_report`, `agent.core.event_name`, `agent.mechanisms.session_store`
- 顶层符号：
  - L30: `def _format(event)`
  - L35: `def _prepare(app, text, conversation_id, cancel)`
  - L48: `def run_session(app, text)`
  - L123: `def run(app, text)`
  - L129: `def _parse_args(argv)`
  - L138: `def main(argv)`

### A.171 `agent/shell/cli/interactive.py`

- 类型：Python
- 行数：233
- 所属主模块：`app/shell/cli`
- 文件角色：runtime/implementation
- 文件说明：交互式真实对话壳：真实模型 + 工具 + id 制四步门控 + 会话持久化。
- 导入：`__future__`, `argparse`, `json`, `sys`, `pathlib`, `typing`, `agent.core`, `agent.core.error_report`, `agent.mechanisms.session_store`
- 顶层符号：
  - L35: `def _brief_args(args)`
  - L47: `def _ask_confirm(gate, name, confirm_id, args)`
  - L72: `def run_one(engine, gate, text)`
  - L131: `def parse_args(argv)`
  - L146: `def build_session(argv)`
  - L182: `def main(argv)`

### A.172 `agent/shell/context_dump.py`

- 类型：Python
- 行数：119
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：开发者上下文导出：按生产装配重建某个会话的完整请求，不调用模型。
- 导入：`__future__`, `datetime`, `typing`, `agent.core.session_log`, `agent.mechanisms.context`, `agent.shell.service_keys`
- 顶层符号：
  - L13: `def build_snapshot(app, conversation_id)`
  - L78: `def render_text(snapshot)`
  - L99: `def _append_messages(lines, messages)`
  - L108: `def _content_blocks(blocks)`

### A.173 `agent/shell/environment_info.py`

- 类型：Python
- 行数：30
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：系统提示词的环境章节：当前只列操作系统与会话 ID。
- 导入：`__future__`, `platform`, `typing`
- 顶层符号：
  - L11: `def operating_system()`
  - L18: `def environment_lines(conversation_id)`
  - L27: `def environment_section(conversation_id)`

### A.174 `agent/shell/fspaths.py`

- 类型：Python
- 行数：157
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：路径安全与可见范围。
- 导入：`__future__`, `os`, `pathlib`, `typing`, `agent.config`, `agent.core.error_report`
- 顶层符号：
  - L30: `def is_drive_root(path)`
  - L36: `def list_drives()`
  - L60: `def fs_rejection(reason)`
  - L69: `def normalize_roots(value)`
  - L86: `def within_any_root(target, roots)`
  - L102: `def default_fs_roots()`
  - L122: `def _parse_roots(raw)`
  - L128: `def _env_roots(name)`
  - L133: `def _env_path(name)`
  - L149: `def resolve_fs_roots(spec)`
  - L154: `def resolve_media_root(roots, spec)`

### A.175 `agent/shell/ini_sections.py`

- 类型：Python
- 行数：183
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：INI 文本的节定位与节级改写。
- 导入：`__future__`, `re`, `typing`
- 顶层符号：
  - L16: `def newline(text)`
  - L21: `def section_at(line)`
  - L38: `def section_span(lines, section)`
  - L57: `def section_names(text)`
  - L70: `def section_body(lines, section)`
  - L79: `def replace_sections(text, bodies)`
  - L109: `def append_section(text, section, body)`
  - L123: `def update_ini_keys(text, section, updates)`
  - L179: `def _with_newline(line, nl)`

### A.176 `agent/shell/plugin_editor.py`

- 类型：Python
- 行数：612
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：插件配置的可编辑区域：只读写插件自己的节。
- 导入：`__future__`, `json`, `re`, `pathlib`, `typing`, `agent.core.error_report`, `agent.shell.ini_sections`
- 顶层符号：
  - L43: `def is_placeholder_api_key(value)`
  - L49: `def _parse_fields(raw_fields)`
  - L101: `def load_schema(folder)`
  - L157: `def build_editor(text, folder)`
  - L193: `def _section_values(text, section)`
  - L211: `def merge_fields(text, values, schema)`
  - L233: `def text_sections(text)`
  - L240: `def render_text(text, sections)`
  - L258: `def _mask_secrets(groups, schema)`
  - L283: `def parse_groups(text, schema)`
  - L343: `def merge_text(text, submitted, sections)`
  - L357: `def _auto_group_id(schema, group, reserved)`
  - L375: `def merge_groups(text, groups, schema)`
  - L426: `def _group_body(group, schema, submitted, extras, previous)`
  - L487: `def _comment_lines(lines)`
  - L494: `def _bool_text(value, field)`
  - L501: `def _visible(field, values)`
  - L508: `def _scan_section(body, schema)`
  - L535: `def _parse_submitted(submitted, allowed, single)`
  - L577: `def _merge_parsed(text, parsed, allowed)`
  - L601: `def _trim_blank(lines)`
  - L610: `def _lf(line)`

### A.177 `agent/shell/plugin_settings.py`

- 类型：Python
- 行数：305
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：插件设置：清单开关、目录解析、插件配置读写与重装。
- 导入：`__future__`, `re`, `pathlib`, `typing`, `agent.capabilities.plugins`, `agent.common.status`, `agent.config`, `agent.core.error_report`, `agent.shell.ini_sections`, `agent.shell.plugin_editor`, `agent.shell.service_keys`, `agent.shell.settings_io`
- 顶层符号：
  - L33: `def _valid_name(name)`
  - L37: `def _version_label(raw)`
  - L46: `def _plugin_folder(name)`
  - L77: `def list_plugins(plugins_path, plugins_dir, app)`
  - L128: `def set_plugin_enabled(name, enabled, app)`
  - L157: `def sync_plugins(app)`
  - L188: `def _announce_plugin_config(app, plugin)`
  - L206: `def _announce_plugins(app, loaded)`
  - L218: `def _config_file(plugin_root)`
  - L225: `def read_plugin_config(name)`
  - L252: `def write_plugin_config(name, text, groups, fields, app)`
  - L302: `def _plugin_config_source(path)`

### A.178 `agent/shell/prompts.py`

- 类型：Python
- 行数：305
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：基础系统提示词。
- 导入：`__future__`, `re`, `typing`, `agent.core.error_report`, `agent.core.mode_marker`
- 顶层符号：
  - L49: `def preview_write_tools_line(registry)`
  - L70: `def tooling_discipline(registry)`
  - L152: `def compact_heading_spacing(text)`
  - L157: `def build_system_prompt()`
  - L208: `def mode_section(mode)`
  - L213: `def mode_note(mode)`
  - L223: `def split_mode_section(system_prompt)`
  - L241: `def tool_summary(registry)`
  - L266: `def resolve_system_prompt()`
  - L292: `def resolve_mode_note()`

### A.179 `agent/shell/service_keys.py`

- 类型：Python
- 行数：10
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：壳层服务登记名（装配点 register / 使用方 get）。
- 导入：`__future__`
- 顶层符号：无

### A.180 `agent/shell/session/__init__.py`

- 类型：Python
- 行数：2
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 顶层符号：无

### A.181 `agent/shell/session/goal.py`

- 类型：Python
- 行数：41
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：目标与自主续跑判定。
- 导入：`__future__`, `typing`, `agent.common.status`, `agent.core.error_report`
- 顶层符号：
  - L16: `def next_continuation_text()`
  - L31: `def note_round(app, cid)`

### A.182 `agent/shell/session/heartbeat.py`

- 类型：Python
- 行数：20
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：会话运行态心跳。
- 导入：`__future__`, `threading`, `typing`, `agent.core.error_report`
- 顶层符号：
  - L11: `def heartbeat_until()`

### A.183 `agent/shell/session/prompt.py`

- 类型：Python
- 行数：65
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：系统提示词与运行态尾部。
- 导入：`__future__`, `typing`, `agent.shell.environment_info`, `agent.shell.prompts`
- 顶层符号：
  - L11: `def system_prompt()`
  - L38: `def mode_note()`

### A.184 `agent/shell/session/queue.py`

- 类型：Python
- 行数：65
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：会话待发送队列访问。
- 导入：`__future__`, `sys`, `typing`, `agent.core.error_report`
- 顶层符号：
  - L11: `def queue_of(app)`
  - L15: `def claim(cid, app)`
  - L20: `def release(cid, item, app)`
  - L26: `def complete(cid, item, app)`
  - L32: `def input_of(item)`
  - L46: `def has_inserting(app, cid)`
  - L52: `def flush_pending(cid, app)`

### A.185 `agent/shell/session/resume.py`

- 类型：Python
- 行数：66
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：外部工具结果回灌。
- 导入：`__future__`, `typing`, `agent.core.error_report`, `agent.core.event_name`, `agent.core.events`, `agent.core.state_values`, `agent.core.state_values`
- 顶层符号：
  - L14: `def splice_resume()`

### A.186 `agent/shell/session/runner.py`

- 类型：Python
- 行数：537
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：会话运行器：后台执行会话回合，消费会话待发送队列。
- 导入：`__future__`, `threading`, `time`, `typing`, `agent.core.error_report`, `agent.core.thread_context`, `agent.mechanisms.live_state`, `agent.shell.session`
- 顶层符号：
  - L34: `class SessionRunner()`
- 类成员：
  - L46: `SessionRunner.__init__(self)`
  - L69: `SessionRunner.set_store_for(self, store_for)`
  - L72: `SessionRunner.set_registry_for(self, registry_for)`
  - L77: `SessionRunner.start(self, cid, message)`
  - L138: `SessionRunner.request_cancel(self, cid)`
  - L148: `SessionRunner._cancel_check(self, cid)`
  - L160: `SessionRunner._heartbeat_until(self, cid, stop)`
  - L166: `SessionRunner._run_loop(self, cid, text, attachments, resume, sender, meta)`
  - L244: `SessionRunner._finish_run_loop(self, cid, stop_beat)`
  - L256: `SessionRunner._start_heartbeat(self, cid)`
  - L265: `SessionRunner._insert_turn_state(self, cid)`
  - L276: `SessionRunner._claim_goal_turn(self, cid, auto_rounds)`
  - L294: `SessionRunner._cancel_pending_for_new_input(self, cid)`
  - L308: `SessionRunner._is_paused(self, cid)`
  - L315: `SessionRunner._queue(self)`
  - L318: `SessionRunner._claim_queued(self, cid)`
  - L321: `SessionRunner._release_queued(self, cid, item)`
  - L324: `SessionRunner._complete_queued(self, cid, item)`
  - L327: `SessionRunner._queued_input(self, item)`
  - L330: `SessionRunner._flush_pending(self, cid)`
  - L333: `SessionRunner._is_canceled(self, cid)`
  - L340: `SessionRunner._goal_round_note(meta)`
  - L350: `SessionRunner._queue_goal_followup(self, cid, text)`
  - L367: `SessionRunner._goal_limit(self, cid)`
  - L383: `SessionRunner._goal_followup_meta(self, cid)`
  - L397: `SessionRunner._note_goal_round(self, cid)`
  - L400: `SessionRunner._next_continuation_text(self, cid)`
  - L405: `SessionRunner._should_auto_continue(self, cid)`
  - L408: `SessionRunner.build_engine(self, cid)`
  - L429: `SessionRunner._execute(self, cid, text, attachments, resume, sender, from_queue, meta)`
  - L448: `SessionRunner._execute_round(self, cid, text, attachments, sender, from_queue, meta, engine)`
  - L472: `SessionRunner._splice_resume(self, cid, resume_data)`
  - L475: `SessionRunner.registry_for(self, cid)`
  - L479: `SessionRunner.system_prompt(self, cid)`
  - L483: `SessionRunner.mode_note(self, cid)`
  - L487: `SessionRunner._system_prompt(self, cid)`
  - L494: `SessionRunner._mode_note(self, cid)`
  - L497: `SessionRunner.shutdown(self, timeout)`
  - L521: `SessionRunner.wait_idle(self, cid, timeout)`

### A.187 `agent/shell/settings_io.py`

- 类型：Python
- 行数：72
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：设置页的文件与 ini 文本原语：原子读写、节内改键、增删节。
- 导入：`__future__`, `os`, `tempfile`, `threading`, `time`, `pathlib`, `typing`, `agent.config`, `agent.core.error_report`, `agent.shell.ini_sections`, `agent.shell.ini_sections`
- 顶层符号：
  - L28: `def read_text(path)`
  - L34: `def write_text(path, text)`
  - L59: `def update_ini_keys(text, section, updates)`
  - L64: `def remove_ini_section(text, section)`
  - L69: `def append_ini_section(text, section, items)`

### A.188 `agent/shell/settings_panel.py`

- 类型：Python
- 行数：226
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：设置页的宿主配置：回显、校验、写回与进程内生效，以及页面路由分派。
- 导入：`__future__`, `os`, `subprocess`, `pathlib`, `typing`, `agent.config`, `agent.core.error_report`, `agent.shell.plugin_settings`, `agent.shell.settings_io`, `agent.shell.web.web_ui_config`
- 顶层符号：
  - L49: `def read_host_value(section, key)`
  - L66: `def save_host_value(section, key, value, app)`
  - L86: `def host_catalog(config_path, web_ui_path, app)`
  - L112: `def _as_text(value)`
  - L118: `def apply_host(app)`
  - L154: `def pick_directory()`
  - L185: `def handle_get(path, query, app)`
  - L197: `def handle_post(path, body, app)`

### A.189 `agent/shell/sse.py`

- 类型：Python
- 行数：96
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：SSE 传输层。
- 导入：`__future__`, `json`, `queue`, `typing`, `agent.core`
- 顶层符号：
  - L27: `def _event_seq(event)`
  - L39: `def sse_payload(event)`
  - L61: `class Channel()`
- 类成员：
  - L64: `Channel.__init__(self, maxsize)`
  - L68: `Channel.push(self, frame)`
  - L81: `Channel.close(self)`
  - L88: `Channel.next_frame(self, timeout)`

### A.190 `agent/shell/timefmt.py`

- 类型：Python
- 行数：38
- 所属主模块：`app/shell`
- 文件角色：runtime/implementation
- 文件说明：时间显示口径（壳层共享的纯函数）。
- 导入：`__future__`, `time`
- 顶层符号：
  - L13: `def date_group(mtime, now)`

### A.191 `agent/shell/web/__init__.py`

- 类型：Python
- 行数：1
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 顶层符号：无

### A.192 `agent/shell/web/auth/__init__.py`

- 类型：Python
- 行数：15
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：HTTP 鉴权（壳层）：密码、会话、Token、策略与登录页。
- 导入：`__future__`, `importlib`, `typing`
- 顶层符号：
  - L11: `def __getattr__(name)`

### A.193 `agent/shell/web/auth/audit.py`

- 类型：Python
- 行数：29
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：鉴权审计日志：只记录事件与来源，不记录密码、Cookie 或 Token。
- 导入：`__future__`, `json`, `threading`, `time`, `pathlib`, `typing`, `agent.core.error_report`, `agent.shell.web.auth.security`
- 顶层符号：
  - L15: `class AuthAudit()`
- 类成员：
  - L16: `AuthAudit.__init__(self, path)`
  - L20: `AuthAudit.write(self, event)`

### A.194 `agent/shell/web/auth/authenticator.py`

- 类型：Python
- 行数：76
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：请求认证：Cookie 会话、Bearer Token、可选外部 Provider。
- 导入：`__future__`, `ipaddress`, `http.cookies`, `typing`, `agent.core.error_report`, `agent.shell.web.auth.models`, `agent.shell.web.auth.sessions`, `agent.shell.web.auth.tokens`
- 顶层符号：
  - L15: `def is_loopback(remote_ip)`
  - L22: `def cookie_token(headers, name)`
  - L36: `class Authenticator()`
- 类成员：
  - L37: `Authenticator.__init__(self, sessions, tokens)`
  - L50: `Authenticator.authenticate(self, headers, remote_ip)`

### A.195 `agent/shell/web/auth/authorizer.py`

- 类型：Python
- 行数：28
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：授权判断：只接收 Principal、路径和方法，不解析 HTTP。
- 导入：`__future__`, `typing`, `agent.shell.web.auth`, `agent.shell.web.auth.models`
- 顶层符号：
  - L11: `class Authorizer()`
- 类成员：
  - L12: `Authorizer.decide(self, identity, method, path)`
  - L23: `Authorizer.scope_for(self, method, path)`
  - L26: `Authorizer.allows(self, principal, scope)`

### A.196 `agent/shell/web/auth/bootstrap.py`

- 类型：Python
- 行数：33
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：GUI 桌面会话一次性引导令牌；只保存进程内状态。
- 导入：`__future__`, `hmac`, `os`, `threading`
- 顶层符号：
  - L10: `class DesktopBootstrap()`
- 类成员：
  - L11: `DesktopBootstrap.__init__(self, token)`
  - L17: `DesktopBootstrap.from_env(cls, enabled)`
  - L23: `DesktopBootstrap.consume(self, token)`

### A.197 `agent/shell/web/auth/config.py`

- 类型：Python
- 行数：99
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：鉴权配置：只读取 [auth] 节，不把 auth 键带进 core。
- 导入：`__future__`, `configparser`, `dataclasses`, `pathlib`, `typing`, `agent.config_schema`, `agent.core.error_report`
- 顶层符号：
  - L16: `class AuthConfigError(ValueError)`
  - L21: `class AuthConfig()`
  - L42: `def load_config(path)`
- 类成员：
  - L34: `AuthConfig.session_seconds(self)`
  - L38: `AuthConfig.secure_cookie(self)`

### A.198 `agent/shell/web/auth/credentials.py`

- 类型：Python
- 行数：44
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：密码凭据文件：唯一权威是 data/auth/credentials.json。
- 导入：`__future__`, `json`, `pathlib`, `typing`, `agent.core.error_report`, `agent.shell.web.auth.password`, `agent.shell.web.auth.security`
- 顶层符号：
  - L14: `class CredentialStore()`
- 类成员：
  - L15: `CredentialStore.__init__(self, path)`
  - L18: `CredentialStore.exists(self)`
  - L21: `CredentialStore.read(self)`
  - L31: `CredentialStore.set_password(self, password)`
  - L41: `CredentialStore.password_record(self)`

### A.199 `agent/shell/web/auth/csrf.py`

- 类型：Python
- 行数：22
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：CSRF：只对 Cookie 会话的写请求校验会话绑定的 token。
- 导入：`__future__`, `hmac`, `typing`, `agent.shell.web.auth.models`
- 顶层符号：
  - L14: `def required(method, session)`
  - L18: `def verify(session, token)`

### A.200 `agent/shell/web/auth/models.py`

- 类型：Python
- 行数：44
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：HTTP 鉴权的数据形状与常量。
- 导入：`__future__`, `dataclasses`, `typing`
- 顶层符号：
  - L13: `class Principal()`
  - L22: `class Session()`
  - L31: `class AuthIdentity()`
  - L40: `class AuthDecision()`

### A.201 `agent/shell/web/auth/password.py`

- 类型：Python
- 行数：59
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：密码哈希与校验：仅使用标准库 scrypt。
- 导入：`__future__`, `base64`, `hashlib`, `hmac`, `secrets`, `typing`, `agent.core.error_report`
- 顶层符号：
  - L20: `def _b64(raw)`
  - L24: `def _raw(value)`
  - L28: `def hash_password(password)`
  - L43: `def verify_password(password, record)`

### A.202 `agent/shell/web/auth/policy.py`

- 类型：Python
- 行数：49
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：鉴权路由策略：唯一决定公开路径与所需 scope。
- 导入：`__future__`, `typing`
- 顶层符号：
  - L21: `def is_public(method, path)`
  - L29: `def required_scope(method, path)`
  - L45: `def allows(principal_scopes, scope)`

### A.203 `agent/shell/web/auth/providers.py`

- 类型：Python
- 行数：39
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：认证方式扩展点：Provider 只负责把外部身份翻译成 Principal。
- 导入：`__future__`, `importlib`, `pathlib`, `typing`, `agent.core.error_report`, `agent.shell.web.auth.models`
- 顶层符号：
  - L13: `class AuthProvider(Protocol)`
  - L20: `def load_provider(module_path, data_root, config)`
- 类成员：
  - L16: `AuthProvider.authenticate(self, headers, remote_ip)`

### A.204 `agent/shell/web/auth/rate_limit.py`

- 类型：Python
- 行数：83
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：登录失败限流：按来源与账户做短时指数退避。
- 导入：`__future__`, `threading`, `time`, `dataclasses`, `typing`
- 顶层符号：
  - L12: `class _Bucket()`
  - L19: `class LoginLimiter()`
- 类成员：
  - L28: `LoginLimiter._prune_locked(self, now)`
  - L43: `LoginLimiter._overflow_fail_locked(self, now)`
  - L52: `LoginLimiter.allowed(self, key)`
  - L63: `LoginLimiter.fail(self, key)`
  - L78: `LoginLimiter.success(self, key)`

### A.205 `agent/shell/web/auth/request.py`

- 类型：Python
- 行数：76
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：HTTP 可信边界：代理后的来源地址、HTTPS 判定与 Host 校验。
- 导入：`__future__`, `ipaddress`, `typing`, `urllib.parse`, `agent.core.error_report`
- 顶层符号：
  - L12: `def _ip(value)`
  - L19: `def _networks(values)`
  - L30: `def _trusted(remote_ip, trusted_proxies)`
  - L37: `def client_ip(headers, remote_ip, trusted_proxies)`
  - L49: `def secure_request(headers, remote_ip, trusted_proxies, is_tls)`
  - L58: `def _host_name(value)`
  - L69: `def host_allowed(host_header, allowed_hosts)`

### A.206 `agent/shell/web/auth/routes.py`

- 类型：Python
- 行数：285
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：登录页与 /auth/* 的 HTTP 形状；不实现密码或会话存储细节。
- 导入：`__future__`, `typing`, `agent.core.error_report`, `agent.shell.web.auth.authenticator`, `agent.shell.web.auth.models`, `agent.shell.web.auth.password`, `agent.shell.web.auth.security`
- 顶层符号：
  - L167: `def _cookie(value, max_age, secure)`
  - L180: `def _clear_cookie(secure)`
  - L184: `class AuthRoutes()`
- 类成员：
  - L185: `AuthRoutes.__init__(self, runtime)`
  - L188: `AuthRoutes.page(self)`
  - L191: `AuthRoutes.desktop_page(self)`
  - L194: `AuthRoutes.desktop_login(self, token, remote_ip, secure)`
  - L222: `AuthRoutes.login(self, password, remote_ip, secure)`
  - L257: `AuthRoutes.status(self, identity)`
  - L271: `AuthRoutes.csrf(self, identity)`
  - L276: `AuthRoutes.logout(self, identity, raw_cookie, secure)`

### A.207 `agent/shell/web/auth/runtime.py`

- 类型：Python
- 行数：139
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：鉴权组合根：装配密码、会话、Token、策略与审计依赖。
- 导入：`__future__`, `ipaddress`, `sys`, `pathlib`, `typing`, `agent.core.error_report`, `agent.shell.web.auth`, `agent.shell.web.auth.audit`, `agent.shell.web.auth.authenticator`, `agent.shell.web.auth.authorizer`, `agent.shell.web.auth.bootstrap`, `agent.shell.web.auth.credentials`, `agent.shell.web.auth.providers`, `agent.shell.web.auth.rate_limit`, `agent.shell.web.auth.routes`, `agent.shell.web.auth.security`, `agent.shell.web.auth.sessions`, `agent.shell.web.auth.tokens`
- 顶层符号：
  - L29: `def _resolve_auth_dir(root, value)`
  - L43: `def _auth_dir_usable(path)`
  - L51: `def _select_auth_dir(root)`
  - L66: `def is_loopback_address(host)`
  - L73: `class AuthRuntime()`
- 类成员：
  - L74: `AuthRuntime.__init__(self)`
  - L113: `AuthRuntime.load(cls, root)`
  - L131: `AuthRuntime.set_password(self, password)`
  - L134: `AuthRuntime.issue_token(self, name, scopes)`
  - L137: `AuthRuntime.revoke_token(self, name)`

### A.208 `agent/shell/web/auth/security.py`

- 类型：Python
- 行数：347
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：鉴权文件安全：目录/文件权限、原子写入与平台校验。
- 导入：`__future__`, `ctypes`, `os`, `shutil`, `stat`, `subprocess`, `sys`, `tempfile`, `threading`, `ctypes`, `pathlib`, `agent.core.error_report`
- 顶层符号：
  - L23: `class AuthSecurityError(RuntimeError)`
  - L36: `class _AclSizeInformation(ctypes.Structure)`
  - L44: `class _AceHeader(ctypes.Structure)`
  - L56: `def _advapi32()`
  - L97: `def _powershell()`
  - L104: `def _windows_sid()`
  - L127: `def _icacls(path, args)`
  - L144: `def _windows_verify_native(path)`
  - L201: `def _windows_secure(path)`
  - L211: `def _run_macos(command, path, action)`
  - L224: `def _remove_macos_acl(path)`
  - L233: `def _verify_macos_acl(path)`
  - L243: `def _posix_verify(path)`
  - L254: `def secure_path(path)`
  - L267: `def verify_path(path)`
  - L277: `def ensure_auth_dir(path)`
  - L289: `def read_text(path)`
  - L298: `def atomic_write_text(path, text)`
  - L332: `def append_line(path, line)`

### A.209 `agent/shell/web/auth/sessions.py`

- 类型：Python
- 行数：71
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：进程内会话：Cookie 只保存随机 token，服务端只保存 hash。
- 导入：`__future__`, `hashlib`, `secrets`, `threading`, `time`, `typing`, `agent.shell.web.auth.models`
- 顶层符号：
  - L14: `def _hash(token)`
  - L18: `class LoginSessionStore()`
- 类成员：
  - L19: `LoginSessionStore.__init__(self, ttl_seconds, max_sessions)`
  - L25: `LoginSessionStore.create(self)`
  - L41: `LoginSessionStore.get(self, token)`
  - L60: `LoginSessionStore.revoke(self, token)`
  - L66: `LoginSessionStore._prune_locked(self)`

### A.210 `agent/shell/web/auth/startup.py`

- 类型：Python
- 行数：17
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：鉴权启动策略：判断当前配置是否允许对外启动。
- 导入：`__future__`, `typing`
- 顶层符号：
  - L8: `def can_start_public(auth)`

### A.211 `agent/shell/web/auth/tokens.py`

- 类型：Python
- 行数：115
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：API Token：只保存 hash、名称与 scope，支持撤销。
- 导入：`__future__`, `hashlib`, `json`, `secrets`, `threading`, `time`, `pathlib`, `typing`, `agent.core.error_report`, `agent.mechanisms.session_locking`, `agent.shell.web.auth.models`, `agent.shell.web.auth.security`
- 顶层符号：
  - L29: `def _hash(token)`
  - L33: `class TokenStore()`
- 类成员：
  - L34: `TokenStore.__init__(self, path)`
  - L38: `TokenStore._read(self)`
  - L50: `TokenStore._write(self, rows)`
  - L56: `TokenStore._secure_lock(self)`
  - L64: `TokenStore.issue(self, name, scopes)`
  - L91: `TokenStore.revoke(self, name)`
  - L106: `TokenStore.verify(self, token)`

### A.212 `agent/shell/web/server.py`

- 类型：Python
- 行数：229
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：Web 壳——HTTP/SSE 服务装配入口。
- 导入：`__future__`, `os`, `secrets`, `ssl`, `sys`, `threading`, `webbrowser`, `http.server`, `pathlib`, `typing`, `agent.common.status`, `agent.config`, `agent.core.error_report`, `agent.mechanisms.session_title`, `agent.shell.fspaths`, `agent.shell.web.auth`, `agent.shell.web.auth.config`, `agent.shell.web.auth.runtime`, `agent.shell.web.auth.security`, `agent.shell.web.auth.startup`
- 顶层符号：
  - L50: `def create_server(app, host, port, assets_dir, media_root, fs_root, titles_dir, title_generator, workspace_root, auth)`
  - L102: `def _startup_auth(root, host, tls_cert, tls_key, allow_insecure_public)`
  - L136: `def _apply_tls(server, tls_cert, tls_key)`
  - L150: `def serve(app)`

### A.213 `agent/shell/web/ui_bundle.py`

- 类型：Python
- 行数：197
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：经典界面内联打包。
- 导入：`__future__`, `re`, `functools`, `pathlib`, `typing`, `agent.core.error_report`
- 顶层符号：
  - L117: `def _app_version()`
  - L130: `def _read(path)`
  - L139: `def read_ui_js()`
  - L146: `def read_ui_css()`
  - L153: `def scope_hljs_css(css, prefix)`
  - L161: `def build_inline_css()`
  - L171: `def build_inline_js()`
  - L183: `def inline_ui_html(version)`

### A.214 `agent/shell/web/web_api.py`

- 类型：Python
- 行数：215
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：Web JSON API：SSE 连接表、运行态与模型可用性（WebShell）。
- 导入：`__future__`, `threading`, `pathlib`, `typing`, `agent.common.status`, `agent.core`, `agent.core.error_report`, `agent.core.input_attachments`, `agent.mechanisms.session_title`, `agent.shell.fspaths`, `agent.shell.service_keys`, `agent.shell.sse`, `agent.shell.web.web_chat`, `agent.shell.web.web_contributions`, `agent.shell.web.web_files`, `agent.shell.web.web_route_slots`, `agent.shell.web.web_sessions`, `agent.shell.web.web_state`, `agent.shell.web.web_subagents`
- 顶层符号：
  - L34: `class WebShell(ChatActions, SessionActions, SubagentActions, FileViewerActions, ContributionActions, UiStateActions)`
- 类成员：
  - L44: `WebShell.__init__(self, app, media_root)`
  - L83: `WebShell._classic_adapter(self)`
  - L90: `WebShell.attach(self)`
  - L96: `WebShell.detach(self, channel)`
  - L102: `WebShell.broadcast(self, event)`
  - L120: `WebShell._announce_model(self, cid, model)`
  - L131: `WebShell._remember_run(self, cid, run_id)`
  - L143: `WebShell.active_run(self, cid)`
  - L148: `WebShell.channel_count(self)`
  - L152: `WebShell.available_models(self)`
  - L163: `WebShell.model_labels(self)`
  - L174: `WebShell.health(self)`

### A.215 `agent/shell/web/web_auth.py`

- 类型：Python
- 行数：155
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：Web 鉴权中间层：Handler 与 auth 运行时之间的 HTTP 边界。
- 导入：`__future__`, `ssl`, `typing`, `urllib.parse`, `agent.core.error_report`, `agent.shell.web.auth`, `agent.shell.web.auth.authenticator`, `agent.shell.web.auth.request`
- 顶层符号：
  - L15: `class AuthMiddleware()`
- 类成员：
  - L18: `AuthMiddleware._client_ip(self)`
  - L25: `AuthMiddleware._secure_request(self)`
  - L37: `AuthMiddleware._host_guard(self)`
  - L50: `AuthMiddleware._identity(self)`
  - L60: `AuthMiddleware._html(self, body)`
  - L69: `AuthMiddleware._redirect_login(self)`
  - L76: `AuthMiddleware._auth_gate(self, method, path)`
  - L103: `AuthMiddleware._auth_public_get(self, path)`
  - L126: `AuthMiddleware._auth_post_login(self, path)`
  - L146: `AuthMiddleware._auth_logout(self, path)`

### A.216 `agent/shell/web/web_chat.py`

- 类型：Python
- 行数：224
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：聊天输入、待发送队列与停止 / 确认动作。
- 导入：`__future__`, `typing`, `agent.core.input_attachments`, `agent.mechanisms.conversation_queue`, `agent.mechanisms.session_store`, `agent.shell.web.web_static`
- 顶层符号：
  - L13: `class ChatActions()`
- 类成员：
  - L16: `ChatActions._send_draft(self, cid, text, attachments, draft_id)`
  - L50: `ChatActions.send(self, cid, text, mode, images, model, draft_id)`
  - L122: `ChatActions.queue(self, cid)`
  - L128: `ChatActions.queue_insert(self, cid, item_id)`
  - L158: `ChatActions.queue_recall(self, cid, item_id)`
  - L169: `ChatActions.queue_cancel(self, cid, item_id)`
  - L179: `ChatActions.confirm(self, cid, confirm_id)`
  - L206: `ChatActions.stop(self, cid)`

### A.217 `agent/shell/web/web_classic.py`

- 类型：Python
- 行数：95
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：经典页面与 SSE 路由。
- 导入：`__future__`, `json`, `typing`, `agent.capabilities.slot_registry`, `agent.shell.service_keys`, `agent.shell.web.web_ui_config`
- 顶层符号：
  - L13: `class ClassicRoutes()`
- 类成员：
  - L17: `ClassicRoutes._classic(self)`
  - L27: `ClassicRoutes._classic_page(self)`
  - L47: `ClassicRoutes._classic_sse(self, query)`

### A.218 `agent/shell/web/web_contributions.py`

- 类型：Python
- 行数：29
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：插件贡献清单：右栏面板、输入区动作、上下文段外观与工具展示名。
- 导入：`__future__`, `typing`
- 顶层符号：
  - L8: `class ContributionActions()`
- 类成员：
  - L11: `ContributionActions.loaded_plugin_names(self)`
  - L19: `ContributionActions.tool_list(self)`

### A.219 `agent/shell/web/web_files.py`

- 类型：Python
- 行数：321
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：右栏文件查看器与本地媒体代理。
- 导入：`__future__`, `mimetypes`, `os`, `pathlib`, `typing`, `agent.config`, `agent.core.error_report`, `agent.shell.fspaths`, `agent.shell.web.web_static`
- 顶层符号：
  - L22: `class FileViewerActions()`
- 类成员：
  - L25: `FileViewerActions.fs_list(self, path)`
  - L61: `FileViewerActions.fs_read(self, path, max_chars)`
  - L102: `FileViewerActions._read_table(self, target)`
  - L140: `FileViewerActions.dir_browse(self, path)`
  - L201: `FileViewerActions._browse_base(self)`
  - L232: `FileViewerActions._rel_to_root(self, target)`
  - L243: `FileViewerActions._resolve_fs(self, path)`
  - L291: `FileViewerActions.media(self, path, root)`

### A.220 `agent/shell/web/web_plugin.py`

- 类型：Python
- 行数：107
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：插件 HTTP 路由。
- 导入：`__future__`, `pathlib`, `typing`, `agent.core.error_report`, `agent.shell.web.web_static`
- 顶层符号：
  - L12: `class PluginRoutes()`
- 类成员：
  - L17: `PluginRoutes._plugin_route(self, method, body)`
  - L65: `PluginRoutes._plugin_asset(self, plugin, rel)`

### A.221 `agent/shell/web/web_route_slots.py`

- 类型：Python
- 行数：59
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：HTTP 路由 slot：宿主路由的实现绑定与替换。
- 导入：`__future__`, `typing`, `agent.capabilities.slot_registry`, `agent.core.app_path`
- 顶层符号：
  - L13: `class HttpRouteSlots()`
- 类成员：
  - L16: `HttpRouteSlots.__init__(self, slots)`
  - L19: `HttpRouteSlots.path(self, method, path)`
  - L22: `HttpRouteSlots.ensure_default(self, method, path, handler, owner)`
  - L33: `HttpRouteSlots.bind(self, method, path, handler, owner)`
  - L44: `HttpRouteSlots.resolve(self, method, path)`

### A.222 `agent/shell/web/web_routes.py`

- 类型：Python
- 行数：752
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：Web HTTP 路由分发（Handler）。
- 导入：`__future__`, `json`, `mimetypes`, `re`, `sys`, `http.server`, `pathlib`, `typing`, `urllib.parse`, `agent.common.status`, `agent.core.context`, `agent.core.error_report`, `agent.mechanisms.background_tasks`, `agent.shell.web.web_api`, `agent.shell.web.web_auth`, `agent.shell.web.web_classic`, `agent.shell.web.web_plugin`, `agent.shell.web.web_static`
- 顶层符号：
  - L28: `class Handler(AuthMiddleware, PluginRoutes, ClassicRoutes, BaseHTTPRequestHandler)`
- 类成员：
  - L41: `Handler.handle_one_request(self)`
  - L58: `Handler.log_message(self, fmt)`
  - L61: `Handler._json(self, status, payload, headers)`
  - L72: `Handler._bytes(self, status, body, content_type)`
  - L83: `Handler._read_body(self)`
  - L99: `Handler._query(self)`
  - L103: `Handler._path(self)`
  - L105: `Handler._slot_http(self, method, path, query, body)`
  - L119: `Handler._asset(self, rel, content_type)`
  - L142: `Handler._stream_session_valid(self, identity)`
  - L154: `Handler._events_stream(self)`
  - L183: `Handler._background_tasks(self)`
  - L192: `Handler._update_controller(self)`
  - L201: `Handler._get_update(self, path, query)`
  - L219: `Handler._get_subagents(self, path, query)`
  - L234: `Handler._get_background(self, path, query)`
  - L258: `Handler._catalog(self, attr)`
  - L265: `Handler._get_page(self, path, query)`
  - L342: `Handler._get_misc(self, path, query)`
  - L398: `Handler.do_GET(self)`
  - L434: `Handler._post_chat_send(self, body)`
  - L449: `Handler._post_update(self, path, body)`
  - L482: `Handler._post_background(self, path, body)`
  - L517: `Handler._post_chat_misc(self, path, body)`
  - L544: `Handler._post_goal(self, body)`
  - L582: `Handler._post_queue(self, path, body)`
  - L594: `Handler.do_POST(self)`
  - L643: `Handler.do_PUT(self)`
  - L683: `Handler.do_DELETE(self)`
  - L718: `Handler.do_HEAD(self)`
  - L729: `Handler.do_OPTIONS(self)`
  - L740: `Handler._safe_error(self, exc)`

### A.223 `agent/shell/web/web_sessions.py`

- 类型：Python
- 行数：145
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：会话历史、名录、标题与运行态释放。
- 导入：`__future__`, `pathlib`, `typing`, `agent.core.error_report`, `agent.mechanisms.session_store`, `agent.mechanisms.session_title`, `agent.shell.timefmt`
- 顶层符号：
  - L18: `class SessionActions()`
- 类成员：
  - L21: `SessionActions.history(self, cid)`
  - L35: `SessionActions.sessions(self)`
  - L73: `SessionActions.release_conversation(self, conversation_id)`
  - L87: `SessionActions._derive_title(self, cid)`
  - L94: `SessionActions.title(self, cid)`
  - L127: `SessionActions._conversation_messages(self, cid)`

### A.224 `agent/shell/web/web_state.py`

- 类型：Python
- 行数：99
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：会话设置与 UI 状态：推理档位、自主模式、状态快照。
- 导入：`__future__`, `typing`, `agent.config`, `agent.shell.web.web_static`
- 顶层符号：
  - L11: `class UiStateActions()`
- 类成员：
  - L14: `UiStateActions.reasoning_effort_get(self, cid)`
  - L27: `UiStateActions.reasoning_effort_set(self, cid, effort)`
  - L41: `UiStateActions.autonomous(self, cid, enabled)`
  - L52: `UiStateActions.ui_state(self, cid)`
  - L79: `UiStateActions.ui_state_put(self, cid, payload)`

### A.225 `agent/shell/web/web_static.py`

- 类型：Python
- 行数：60
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：Web 静态资产路径与小工具（无业务状态）。
- 导入：`__future__`, `pathlib`, `typing`, `agent.capabilities.contributions`
- 顶层符号：
  - L28: `def lang_from_path(name)`
  - L34: `def plugin_asset_rel(path)`
  - L51: `def looks_binary(path)`

### A.226 `agent/shell/web/web_subagents.py`

- 类型：Python
- 行数：76
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：子智能体 Web 动作：列表、历史、发送。
- 导入：`__future__`, `typing`, `agent.core.context`, `agent.subagent.models`
- 顶层符号：
  - L11: `class SubagentActions()`
- 类成员：
  - L14: `SubagentActions._subagent_manager(self)`
  - L20: `SubagentActions.subagents(self, parent_cid, batch)`
  - L31: `SubagentActions.subagent_history(self, parent_cid, child_id)`
  - L55: `SubagentActions.subagent_send(self, parent_cid, child_id, msg)`

### A.227 `agent/shell/web/web_ui_config.py`

- 类型：Python
- 行数：44
- 所属主模块：`app/shell/web`
- 文件角色：runtime/implementation
- 文件说明：经典界面展示开关：项目根 web-ui-config.ini 的 [web-ui] 节。
- 导入：`__future__`, `configparser`, `pathlib`, `typing`, `agent.config`
- 顶层符号：
  - L19: `def _flag(raw, default)`
  - L27: `def get_web_ui(path)`

### A.228 `agent/subagent/__init__.py`

- 类型：Python
- 行数：9
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：子智能体运行时与持久化。
- 导入：`__future__`, `agent.subagent.batches`, `agent.subagent.models`
- 顶层符号：无

### A.229 `agent/subagent/batches.py`

- 类型：Python
- 行数：220
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：按父会话、批次分文件的子智能体元数据存储。
- 导入：`__future__`, `json`, `os`, `re`, `threading`, `time`, `uuid`, `pathlib`, `typing`, `agent.core.error_report`, `agent.mechanisms.session_store`, `agent.subagent.models`
- 顶层符号：
  - L22: `class BatchError(Exception)`
  - L30: `class BatchStore()`
- 类成员：
  - L25: `BatchError.__init__(self, message, code)`
  - L33: `BatchStore.__init__(self, data_root)`
  - L38: `BatchStore.new_batch_id(self)`
  - L41: `BatchStore._parent_dir(self, parent_cid)`
  - L47: `BatchStore._path(self, parent_cid, batch)`
  - L53: `BatchStore.create(self, parent_cid)`
  - L60: `BatchStore.get(self, parent_cid, batch)`
  - L66: `BatchStore.list_for_parent(self, parent_cid)`
  - L80: `BatchStore.add_child(self, parent_cid, batch)`
  - L105: `BatchStore.remove_child(self, parent_cid, batch, child_id)`
  - L127: `BatchStore.remove_empty(self, parent_cid, batch)`
  - L144: `BatchStore._read(self, path)`
  - L180: `BatchStore._write(self, record)`
  - L211: `BatchStore.iter_batches(self)`

### A.230 `agent/subagent/lifecycle.py`

- 类型：Python
- 行数：149
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：子智能体创建、状态与列表；不直接持久化文件，不拼装消息。
- 导入：`__future__`, `typing`, `agent.common.status`, `agent.core.error_report`, `agent.core.input_attachments`, `agent.mechanisms.mesh`, `agent.subagent.messaging`, `agent.subagent.models`, `agent.subagent.repository`
- 顶层符号：
  - L16: `class SubagentLifecycle()`
- 类成员：
  - L19: `SubagentLifecycle.__init__(self)`
  - L32: `SubagentLifecycle._validate(self, parent_cid, prompt, label, context, images)`
  - L58: `SubagentLifecycle.create(self, parent_cid)`
  - L112: `SubagentLifecycle.list(self, parent_cid, batch)`
  - L127: `SubagentLifecycle.result(self, parent_cid, child_id)`
  - L136: `SubagentLifecycle.status(self, parent_cid, child_id)`

### A.231 `agent/subagent/manager.py`

- 类型：Python
- 行数：161
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：子智能体门面：组合持久化、生命周期与消息三个边界。
- 导入：`__future__`, `pathlib`, `threading`, `typing`, `agent.core`, `agent.core.error_report`, `agent.mechanisms.mesh`, `agent.mechanisms.session_store`, `agent.subagent.lifecycle`, `agent.subagent.messaging`, `agent.subagent.models`, `agent.subagent.repository`
- 顶层符号：
  - L19: `class SubagentManager()`
- 类成员：
  - L22: `SubagentManager.__init__(self)`
  - L53: `SubagentManager._on_turn_started(self, event)`
  - L60: `SubagentManager._on_turn_ended(self, event)`
  - L79: `SubagentManager.is_child(self, child_id)`
  - L82: `SubagentManager.store_for(self, cid)`
  - L85: `SubagentManager.record(self, child_id)`
  - L88: `SubagentManager.create(self, parent_cid)`
  - L107: `SubagentManager.list(self, parent_cid, batch)`
  - L110: `SubagentManager.status(self, parent_cid, child_id)`
  - L113: `SubagentManager.result(self, parent_cid, child_id)`
  - L116: `SubagentManager.send(self, parent_cid, child_id)`
  - L128: `SubagentManager.send_to_parent(self, child_id)`
  - L141: `SubagentManager.history(self, parent_cid, child_id)`
  - L144: `SubagentManager.shutdown(self)`

### A.232 `agent/subagent/messaging.py`

- 类型：Python
- 行数：116
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：子智能体父子消息投递；不持有会话或批次持久化职责。
- 导入：`__future__`, `typing`, `agent.core.input_attachments`, `agent.mechanisms.conversation_queue`, `agent.mechanisms.mesh`, `agent.subagent.models`, `agent.subagent.repository`
- 顶层符号：
  - L14: `class SubagentMessenger()`
- 类成员：
  - L17: `SubagentMessenger.__init__(self)`
  - L23: `SubagentMessenger._record_for_parent(self, parent_cid, child_id)`
  - L29: `SubagentMessenger._parent_name(self, parent_cid)`
  - L33: `SubagentMessenger._child_name(self, child)`
  - L36: `SubagentMessenger.send_to_child(self, parent_cid, child_id)`
  - L54: `SubagentMessenger.send_to_parent(self, child_id)`
  - L71: `SubagentMessenger._submit(self, target_cid, sender_cid, msg, images)`

### A.233 `agent/subagent/models.py`

- 类型：Python
- 行数：60
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：子智能体的持久化元数据形状。
- 导入：`__future__`, `dataclasses`, `typing`, `agent.common.status`
- 顶层符号：
  - L11: `class SubagentError(Exception)`
  - L20: `class SubagentRecord()`
  - L40: `class BatchRecord()`
- 类成员：
  - L14: `SubagentError.__init__(self, message, code)`
  - L28: `SubagentRecord.public(self)`
  - L46: `BatchRecord.public(self)`

### A.234 `agent/subagent/repository.py`

- 类型：Python
- 行数：180
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：子智能体持久化仓库：会话路径、批次记录、fork 初始化。
- 导入：`__future__`, `pathlib`, `threading`, `typing`, `agent.core.error_report`, `agent.mechanisms.session_store`, `agent.subagent.batches`, `agent.subagent.models`, `agent.subagent.seed`
- 顶层符号：
  - L18: `class SubagentRepository()`
- 类成员：
  - L21: `SubagentRepository.__init__(self)`
  - L39: `SubagentRepository._restore(self)`
  - L44: `SubagentRepository.is_child(self, child_id)`
  - L48: `SubagentRepository.store_for(self, cid)`
  - L51: `SubagentRepository.record(self, child_id)`
  - L58: `SubagentRepository.prepare(self)`
  - L105: `SubagentRepository._batch_for(self, parent, batch)`
  - L114: `SubagentRepository.discard(self, child_id)`
  - L122: `SubagentRepository.abort(self, child_id)`
  - L135: `SubagentRepository.list_batches(self, parent_cid, batch)`
  - L143: `SubagentRepository.latest_result(self, parent_cid, child_id)`
  - L160: `SubagentRepository.history(self, parent_cid, child_id)`
  - L175: `SubagentRepository.shutdown(self)`

### A.235 `agent/subagent/seed.py`

- 类型：Python
- 行数：61
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：子会话初始化：fresh 空历史与 fork 已完成回合前缀。
- 导入：`__future__`, `typing`, `agent.core.events`, `agent.mechanisms.session_store`
- 顶层符号：
  - L11: `def completed_turn_prefix(events)`
  - L23: `def _copy_event(event)`
  - L32: `def seed_child(parent_store, child_store)`

### A.236 `agent/update/__init__.py`

- 类型：Python
- 行数：3
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：软件更新。
- 顶层符号：无

### A.237 `agent/update/apply.py`

- 类型：Python
- 行数：130
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：更新 helper：在应用退出后切换版本并做健康检查。
- 导入：`__future__`, `json`, `os`, `subprocess`, `sys`, `pathlib`, `agent.common.status`, `agent.core.error_report`, `agent.update.install`, `agent.update.logs`, `agent.update.processes`, `agent.update.state`
- 顶层符号：
  - L29: `def _run_new_updater(root, state_path, staging)`
  - L49: `def main()`

### A.238 `agent/update/assets.py`

- 类型：Python
- 行数：33
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：更新资产归属：哪些插件配置不进入发布包。
- 导入：`__future__`, `pathlib`
- 顶层符号：
  - L16: `def is_sensitive_plugin_config(path)`
  - L22: `def is_local_secret(path)`

### A.239 `agent/update/checker.py`

- 类型：Python
- 行数：74
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：远端 manifest 检查。
- 导入：`__future__`, `os`, `urllib.request`, `dataclasses`, `typing`, `agent.common.status`, `agent.core.error_report`, `agent.update.manifest`, `agent.update.version`
- 顶层符号：
  - L29: `class UpdateStatus()`
  - L38: `def manifest_url()`
  - L42: `def fetch_manifest(url, timeout)`
  - L51: `def check(root, url)`

### A.240 `agent/update/config_merge.py`

- 类型：Python
- 行数：48
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：用户与默认配置的 key 级合并。
- 导入：`__future__`, `configparser`, `shutil`, `pathlib`
- 顶层符号：
  - L10: `def _read(path)`
  - L17: `def merge_ini(existing, template)`

### A.241 `agent/update/controller.py`

- 类型：Python
- 行数：159
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：更新检查、下载暂存与重启请求。
- 导入：`__future__`, `json`, `os`, `shutil`, `signal`, `threading`, `pathlib`, `typing`, `agent.common.status`, `agent.config`, `agent.core.error_report`, `agent.update.checker`, `agent.update.install`, `agent.update.logs`, `agent.update.stage`, `agent.update.version`
- 顶层符号：
  - L31: `class UpdateController()`
- 类成员：
  - L32: `UpdateController.__init__(self, root)`
  - L48: `UpdateController.status(self)`
  - L52: `UpdateController.check(self)`
  - L105: `UpdateController.download(self)`
  - L120: `UpdateController.apply(self)`

### A.242 `agent/update/health.py`

- 类型：Python
- 行数：48
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：更新后自检：导入、版本、配置、插件与端口。
- 导入：`__future__`, `configparser`, `os`, `socket`, `sys`, `pathlib`, `agent.core.error_report`, `agent.update.logs`, `agent.update.version`
- 顶层符号：
  - L16: `def _check_config(root)`
  - L24: `def main()`

### A.243 `agent/update/install.py`

- 类型：Python
- 行数：176
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：根目录原地更新：备份、覆盖、回滚与清理。
- 导入：`__future__`, `os`, `shutil`, `subprocess`, `sys`, `time`, `pathlib`, `typing`, `agent.common.status`, `agent.core.error_report`, `agent.update.config_merge`, `agent.update.state`
- 顶层符号：
  - L23: `def install_root()`
  - L30: `def payload_root(root)`
  - L34: `def _backup_root(root, previous)`
  - L63: `def restore_backup(root, previous)`
  - L87: `def _replace_locked_file(incoming, target, root)`
  - L107: `def _copy_program(source, root)`
  - L129: `def _cleanup_staging(root, version)`
  - L139: `def apply_staged(root, staging, version)`
  - L155: `def health_check(payload)`
  - L174: `def cleanup_after_success(root, version)`

### A.244 `agent/update/logs.py`

- 类型：Python
- 行数：52
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：更新链路日志：检查、下载、校验、切换、恢复。
- 导入：`__future__`, `json`, `time`, `pathlib`, `typing`, `agent.core.error_report`
- 顶层符号：
  - L16: `def log_event(root, event)`
  - L35: `def tail(root, limit)`

### A.245 `agent/update/manifest.py`

- 类型：Python
- 行数：96
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：更新 manifest 解析与哈希校验。
- 导入：`__future__`, `hashlib`, `json`, `dataclasses`, `pathlib`, `typing`, `agent.update.version`
- 顶层符号：
  - L18: `class UpdateManifest()`
  - L29: `def _text(value, name)`
  - L36: `def _hash(value)`
  - L43: `def parse_manifest(raw)`
  - L74: `def sha256_file(path, chunk_size)`
  - L85: `def manifest_digest(raw)`
  - L89: `def verify_asset(path, manifest)`

### A.246 `agent/update/processes.py`

- 类型：Python
- 行数：187
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：更新器的进程边界：按安装路径查找并停止旧 GUI 进程。
- 导入：`__future__`, `ctypes`, `os`, `subprocess`, `sys`, `time`, `pathlib`, `typing`, `agent.update.logs`
- 顶层符号：
  - L21: `class _PROCESSENTRY32W(ctypes.Structure)`
  - L36: `def _same_path(left, right)`
  - L43: `def _kernel32()`
  - L64: `def _process_image_path(pid)`
  - L80: `def find_pids(executable)`
  - L106: `def stop_old_launcher(root, wait_seconds)`
  - L140: `def cleanup_launcher_archives(root, attempts, delay)`
  - L164: `def launch_after_update(root)`
  - L184: `def runtime_available()`

### A.247 `agent/update/recover.py`

- 类型：Python
- 行数：51
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：启动恢复：未完成切换时校验并回滚。
- 导入：`__future__`, `agent.common.status`, `agent.core.error_report`, `agent.update.install`, `agent.update.logs`, `agent.update.processes`, `agent.update.state`
- 顶层符号：
  - L18: `def main()`

### A.248 `agent/update/stage.py`

- 类型：Python
- 行数：100
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：更新包下载、哈希校验与安全解压。
- 导入：`__future__`, `shutil`, `urllib.parse`, `urllib.request`, `zipfile`, `pathlib`, `agent.update.logs`, `agent.update.manifest`
- 顶层符号：
  - L18: `class UpdateArchiveError(ValueError)`
  - L22: `def _safe_name(name)`
  - L31: `def _download(url, target, expected_size)`
  - L48: `def stage_package(manifest)`

### A.249 `agent/update/state.py`

- 类型：Python
- 行数：47
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：更新切换状态。
- 导入：`__future__`, `json`, `pathlib`, `typing`, `agent.common.status`
- 顶层符号：
  - L14: `def state_path(root)`
  - L18: `def read_state(root)`
  - L26: `def write_state(root, phase, from_version, to_version, detail)`
  - L42: `def clear_state(root)`

### A.250 `agent/update/version.py`

- 类型：Python
- 行数：108
- 所属主模块：`app/runtime`
- 文件角色：runtime/implementation
- 文件说明：版本读取与 SemVer 比较。
- 导入：`__future__`, `os`, `re`, `dataclasses`, `functools`, `pathlib`, `typing`
- 顶层符号：
  - L15: `def _compare_prerelease(left, right)`
  - L42: `class Version()`
  - L76: `def current_version(root)`
  - L92: `def is_dev_checkout(root)`
  - L99: `def is_newer(remote, local)`
- 类成员：
  - L49: `Version.parse(cls, raw)`
  - L61: `Version._core(self)`
  - L64: `Version.__lt__(self, other)`
  - L71: `Version.__str__(self)`

### A.251 `archive/expired/tasks/sleep.py`

- 类型：Python
- 行数：48
- 所属主模块：`archive`
- 文件角色：runtime/implementation
- 文件说明：task_sleep 工具。
- 导入：`__future__`, `typing`, `agent.capabilities.registry`, `agent.core.session_scope`, `agent.mechanisms.live_state`
- 顶层符号：
  - L12: `class TaskSleepTool(ToolPlugin)`
- 类成员：
  - L24: `TaskSleepTool.__init__(self, live_state)`
  - L27: `TaskSleepTool.execute(self, arguments)`

### A.252 `plugins/ai_cosplay/config.py`

- 类型：Python
- 行数：203
- 所属主模块：`app/plugins/ai_cosplay`
- 文件角色：runtime/implementation
- 文件说明：AI角色扮演插件的配置读取。
- 导入：`__future__`, `configparser`, `dataclasses`, `pathlib`, `typing`, `agent.config`
- 顶层符号：
  - L36: `class ConfigError(ValueError)`
  - L45: `class AICosplayConfig()`
  - L65: `def config_path()`
  - L70: `def _clean(value)`
  - L74: `def _int_value(raw, default)`
  - L84: `def _float_value(raw, default)`
  - L94: `def _bool_value(raw, default)`
  - L106: `def _parse_numeric(values, warnings)`
  - L146: `def load_config(path)`
- 类成员：
  - L39: `ConfigError.__init__(self, message)`
  - L61: `AICosplayConfig.enabled(self)`

### A.253 `plugins/ai_cosplay/plugin.py`

- 类型：Python
- 行数：158
- 所属主模块：`app/plugins/ai_cosplay`
- 文件角色：runtime/implementation
- 文件说明：AI角色扮演插件入口。
- 导入：`__future__`, `pathlib`, `typing`, `agent.capabilities.plugin_paths`, `agent.core`, `agent.core.error_report`, `.config`, `.provider`, `.runtime`, `.runtime_worker`, `.tool`
- 顶层符号：
  - L28: `def _voice_directive(user_salutation, assistant_salutation, tone)`
  - L40: `def _config_path()`
  - L45: `def _log_warnings(config)`
  - L50: `def _turn_handler(runtime)`
  - L62: `def _error_handler(runtime)`
  - L72: `def _config_payload(runtime)`
  - L88: `def _status_payload(runtime)`
  - L92: `def _played_handler(runtime)`
  - L111: `def register(ctx)`

### A.254 `plugins/ai_cosplay/provider.py`

- 类型：Python
- 行数：121
- 所属主模块：`app/plugins/ai_cosplay`
- 文件角色：runtime/implementation
- 文件说明：AI角色扮演的语音合成端口与 edge-tts 适配。
- 导入：`__future__`, `asyncio`, `dataclasses`, `typing`
- 顶层符号：
  - L17: `class SpeechError(Exception)`
  - L21: `class SpeechEngineUnavailable(SpeechError)`
  - L25: `class SpeechSynthesisError(SpeechError)`
  - L30: `class SpeechAudio()`
  - L38: `class TTSProvider(Protocol)`
  - L49: `def _import_edge_tts()`
  - L59: `class EdgeTTSProvider()`
  - L115: `def create_provider(engine)`
- 类成员：
  - L43: `TTSProvider.available(self)`
  - L45: `TTSProvider.synthesize(self, text)`
  - L64: `EdgeTTSProvider.available(self)`
  - L71: `EdgeTTSProvider.synthesize(self, text)`

### A.255 `plugins/ai_cosplay/runtime.py`

- 类型：Python
- 行数：319
- 所属主模块：`app/plugins/ai_cosplay`
- 文件角色：runtime/implementation
- 文件说明：AI角色扮演运行时：配置、每会话 worker、发布器与统计。
- 导入：`__future__`, `threading`, `time`, `typing`, `agent.core.error_report`, `.config`, `.provider`, `.runtime_worker`
- 顶层符号：
  - L33: `class AICosplayRuntime()`
- 类成员：
  - L36: `AICosplayRuntime.__init__(self, config, provider)`
  - L59: `AICosplayRuntime.config(self)`
  - L63: `AICosplayRuntime.synthesis_timeout_s(self)`
  - L66: `AICosplayRuntime.speech_text(self, text)`
  - L71: `AICosplayRuntime.provider_ready(self)`
  - L76: `AICosplayRuntime.enqueue(self, conversation_id, call_id, segments, voice, publisher)`
  - L136: `AICosplayRuntime.begin_playback(self, conversation_id, call_id)`
  - L159: `AICosplayRuntime.ack_playback(self, conversation_id, call_id, status, detail)`
  - L181: `AICosplayRuntime.forget_playback(self, conversation_id, call_id)`
  - L186: `AICosplayRuntime._finish_playback(self, conversation_id, call_id, status, detail)`
  - L196: `AICosplayRuntime._resolve_playback_cid(self, conversation_id, status)`
  - L204: `AICosplayRuntime._resolve_all_playback(self, status)`
  - L213: `AICosplayRuntime.stop_cid(self, conversation_id, reason)`
  - L226: `AICosplayRuntime.dispose(self)`
  - L250: `AICosplayRuntime._drop_worker(self, cid, worker)`
  - L255: `AICosplayRuntime._mark_dequeued(self, cid)`
  - L265: `AICosplayRuntime._mark_spoken(self, cid)`
  - L273: `AICosplayRuntime._mark_failed(self, cid, exc)`
  - L286: `AICosplayRuntime._mark_dropped(self, cid)`
  - L296: `AICosplayRuntime.status(self)`

### A.256 `plugins/ai_cosplay/runtime_worker.py`

- 类型：Python
- 行数：330
- 所属主模块：`app/plugins/ai_cosplay`
- 文件角色：runtime/implementation
- 文件说明：AI角色扮演 worker：播放等待、每会话串行合成与 SSE 发布。
- 导入：`__future__`, `base64`, `queue`, `threading`, `time`, `dataclasses`, `typing`, `agent.core.error_report`, `agent.core.thread_context`, `.config`, `.provider`
- 顶层符号：
  - L49: `class SpeechBusy(SpeechError)`
  - L58: `class SpeechSynthesisFailed(SpeechError)`
  - L69: `class SpeechPlaybackFailed(SpeechError)`
  - L87: `class PlaybackWaiter()`
  - L143: `class _SegmentJob()`
  - L153: `class _SessionWorker()`
- 类成员：
  - L52: `SpeechBusy.__init__(self, queued, limit)`
  - L61: `SpeechSynthesisFailed.__init__(self, detail)`
  - L72: `SpeechPlaybackFailed.__init__(self, status, waited_ms, detail)`
  - L90: `PlaybackWaiter.__init__(self, conversation_id, call_id)`
  - L100: `PlaybackWaiter.status(self)`
  - L105: `PlaybackWaiter.waited_ms(self)`
  - L109: `PlaybackWaiter.detail(self)`
  - L113: `PlaybackWaiter.resolve(self, status, detail)`
  - L123: `PlaybackWaiter.wait(self, timeout_s, canceled)`
  - L156: `_SessionWorker.__init__(self, runtime, conversation_id, provider, config)`
  - L182: `_SessionWorker.conversation_id(self)`
  - L185: `_SessionWorker.enqueue(self, jobs, publisher)`
  - L195: `_SessionWorker.stop(self, reason)`
  - L206: `_SessionWorker._drain(self)`
  - L216: `_SessionWorker.join(self, timeout)`
  - L221: `_SessionWorker.current_publisher(self)`
  - L224: `_SessionWorker._publish_raw(self, publisher, event, payload)`
  - L234: `_SessionWorker._segment_payload(self, job, audio)`
  - L250: `_SessionWorker._error_payload(self, job, exc)`
  - L259: `_SessionWorker._run(self)`
  - L322: `_SessionWorker._stop_payload(self)`
  - L328: `_SessionWorker.publish_stop(self)`

### A.257 `plugins/ai_cosplay/text.py`

- 类型：Python
- 行数：531
- 所属主模块：`app/plugins/ai_cosplay`
- 文件角色：runtime/implementation
- 文件说明：AI角色扮演的文本规范、切分与合成前净化。
- 导入：`__future__`, `re`, `unicodedata`, `typing`
- 顶层符号：
  - L52: `class MessageValidationError(ValueError)`
  - L62: `def _fail(message, position, code)`
  - L67: `def _is_cjk(ch)`
  - L72: `def _is_ascii_letter(ch)`
  - L76: `def _is_ascii_digit(ch)`
  - L80: `def _is_ascii_alnum(ch)`
  - L84: `def _is_space(ch)`
  - L88: `def _is_boundary(ch)`
  - L92: `def _is_operand(ch)`
  - L101: `def _prev_nonspace(text, index)`
  - L108: `def _next_nonspace(text, index)`
  - L115: `def _numeric_separator(text, index)`
  - L125: `def _path_char(ch)`
  - L130: `def _extension_dot(text, index)`
  - L150: `def _allowed_char(ch)`
  - L173: `def _describe_char(ch)`
  - L184: `def _scan_structure(text)`
  - L252: `def _validate_structure_edges(text, boundaries)`
  - L275: `def _check_math_and_percent(text)`
  - L312: `def split_message(msg, max_chars)`
  - L365: `def _join(current, piece)`
  - L373: `def _chinese_integer(value)`
  - L413: `def _chinese_number(raw)`
  - L423: `def _percent_replacement(match)`
  - L455: `def _hang_speech_text(text)`
  - L474: `def _math_replacement(match)`
  - L481: `def _negative_replacement(match)`
  - L490: `def _is_speakable(ch)`
  - L497: `def split_speech_text(text)`
  - L503: `def to_speech_text(text)`
- 类成员：
  - L55: `MessageValidationError.__init__(self, message)`

### A.258 `plugins/ai_cosplay/tool.py`

- 类型：Python
- 行数：146
- 所属主模块：`app/plugins/ai_cosplay`
- 文件角色：runtime/implementation
- 文件说明：`ai_speek` 工具：校验 `msg`、取发布器、交给运行时入队。
- 导入：`__future__`, `typing`, `agent.capabilities.registry`, `agent.core.context`, `agent.core.session_scope`, `.provider`, `.runtime`, `.runtime_worker`, `.text`
- 顶层符号：
  - L19: `def _tool_description(persona)`
  - L25: `class AICosplayTool(ToolPlugin)`
  - L126: `def _turn_canceled(turn)`
  - L135: `def _playback_timeout_s(characters)`
  - L140: `def build(runtime)`
- 类成员：
  - L43: `AICosplayTool.__init__(self, runtime)`
  - L47: `AICosplayTool.execute(self, arguments)`

### A.259 `plugins/ai_cosplay/ui/player.js`

- 类型：JavaScript
- 行数：806
- 所属主模块：`app/plugins/ai_cosplay`
- 文件角色：runtime/implementation
- addEventListener：12
- 顶层符号：
  - L33: `function setPlayerIcon()`
  - L37: `function text()`
  - L41: `function short()`
  - L46: `function element()`
  - L53: `function activeCid()`
  - L60: `function stateFor()`
  - L64: `function currentState()`
  - L101: `function stopTextScroll()`
  - L114: `function updateTextScroll()`
  - L161: `function scheduleTextScroll()`
  - L169: `function render()`
  - L200: `function revoke()`
  - L207: `function clearTimer()`
  - L214: `function releasePlaybackLock()`
  - L221: `function finishCurrent()`
  - L229: `function startCurrentAudio()`
  - L257: `function playCurrent()`
  - L289: `function playNext()`
  - L300: `function afterItem()`
  - L315: `function callState()`
  - L333: `function ackPlayback()`
  - L352: `function markPlayed()`
  - L363: `function requestChatStop()`
  - L382: `function broadcast()`
  - L387: `function enqueueInto()`
  - L444: `function matches()`
  - L453: `function stopState()`
  - L494: `function toggleState()`
  - L518: `function stopActive()`
  - L526: `function onStopClick()`
  - L530: `function onToggleClick()`
  - L535: `function onBroadcast()`
  - L550: `function stateForEvent()`
  - L556: `function getState()`
  - L650: `function onPlayerEvent()`
  - L673: `function onPluginsChanged()`
  - L683: `function onConversationChanged()`
  - L709: `function destroyState()`
  - L723: `function destroy()`

### A.260 `plugins/ai_cosplay/ui/tool-view.js`

- 类型：JavaScript
- 行数：41
- 所属主模块：`app/plugins/ai_cosplay`
- 文件角色：runtime/implementation
- addEventListener：0
- 顶层符号：
  - L11: `function message()`

### A.261 `plugins/auto_update/plugin.py`

- 类型：Python
- 行数：25
- 所属主模块：`app/plugins/auto_update`
- 文件角色：runtime/implementation
- 文件说明：自动更新插件：版本更新按钮。
- 导入：`__future__`, `typing`, `agent.capabilities.plugin_paths`
- 顶层符号：
  - L16: `def register(ctx)`

### A.262 `plugins/auto_update/ui/update.js`

- 类型：JavaScript
- 行数：97
- 所属主模块：`app/plugins/auto_update`
- 文件角色：runtime/implementation
- addEventListener：2
- 顶层符号：
  - L5: `function boot()`
  - L23: `function set()`
  - L28: `function request()`
  - L40: `function schedule()`
  - L45: `function applyStatus()`
  - L57: `function check()`

### A.263 `plugins/base_settings/plugin.py`

- 类型：Python
- 行数：57
- 所属主模块：`app/plugins/base_settings`
- 文件角色：runtime/implementation
- 文件说明：基础设置插件：从 plugin-ui.json 注册面板与条目。
- 导入：`__future__`, `pathlib`, `typing`, `agent.capabilities.plugin_settings_tree`, `agent.shell.settings_panel`
- 顶层符号：
  - L12: `def _section(field)`
  - L16: `def _load(field)`
  - L20: `def _save(field, ctx, value)`
  - L50: `def register(ctx)`

### A.264 `plugins/knowledge/plugin.py`

- 类型：Python
- 行数：564
- 所属主模块：`app/plugins/knowledge`
- 文件角色：runtime/implementation
- 文件说明：知识库插件。
- 导入：`__future__`, `json`, `os`, `threading`, `pathlib`, `typing`, `agent.capabilities.plugin_paths`, `agent.capabilities.plugins`, `agent.config`, `agent.core.error_report`
- 顶层符号：
  - L70: `def parse_extra_suffixes(raw)`
  - L87: `def is_text_like(name, extra)`
  - L101: `def _has_hidden_segment(rel)`
  - L110: `def _config_path()`
  - L119: `def _load_kb_config(path)`
  - L151: `class _KnowledgeFiles()`
  - L336: `class KBRuntime(_KnowledgeFiles)`
  - L449: `def resource_directory_lines(runtime)`
  - L461: `def _read_kb_file_text(fpath)`
  - L475: `def _register_routes(ctx, runtime)`
  - L505: `def register(ctx)`
- 类成员：
  - L158: `_KnowledgeFiles.__init__(self, root, max_file_size, extra_suffixes)`
  - L171: `_KnowledgeFiles.from_config(cls, path, data_dir)`
  - L179: `_KnowledgeFiles.enabled(self)`
  - L184: `_KnowledgeFiles.safe_resolve(self, rel)`
  - L215: `_KnowledgeFiles.file_allowed(self, target)`
  - L240: `_KnowledgeFiles.read_text(self, target)`
  - L270: `_KnowledgeFiles._read_table(self, target)`
  - L299: `_KnowledgeFiles.list_files(self)`
  - L339: `KBRuntime.__init__(self, root, max_file_size, data_dir, extra_suffixes)`
  - L351: `KBRuntime._state_file(self)`
  - L356: `KBRuntime.load_checked(self)`
  - L372: `KBRuntime._persist(self)`
  - L386: `KBRuntime.get_checked(self, cid)`
  - L390: `KBRuntime.set_checked(self, cid, rels)`
  - L420: `KBRuntime.build_system_messages(self, cid)`
  - L439: `KBRuntime.attached_count(self, cid)`

### A.265 `plugins/knowledge/ui/panel.js`

- 类型：JavaScript
- 行数：172
- 所属主模块：`app/plugins/knowledge`
- 文件角色：runtime/implementation
- addEventListener：3
- 顶层符号：
  - L11: `function esc()`
  - L22: `function currentCid()`
  - L30: `function persist()`
  - L54: `function renderList()`
  - L104: `function render()`
  - L140: `function visible()`

### A.266 `plugins/multi_model/plugin.py`

- 类型：Python
- 行数：310
- 所属主模块：`app/plugins/multi_model`
- 文件角色：runtime/implementation
- 文件说明：多模型插件：模型目录、只读端点与开屏下拉脚本。
- 导入：`__future__`, `configparser`, `sys`, `dataclasses`, `pathlib`, `typing`, `agent.capabilities.model_catalog`, `agent.capabilities.plugin_paths`, `agent.capabilities.plugins`, `agent.core.error_report`, `agent.mechanisms.provider_registry`
- 顶层符号：
  - L34: `def _config_path()`
  - L39: `def _clean(value)`
  - L44: `def _section_id(section)`
  - L48: `def _is_placeholder_key(value)`
  - L54: `def _diag(path, section, key, reason)`
  - L60: `def _emit(lines, path)`
  - L73: `def _as_bool(raw, path, section, key, lines)`
  - L87: `def _positive_int(raw, path, section, key, lines)`
  - L103: `def _entry_identity(path, section, get, lines)`
  - L134: `def _parse_entry(path, section, parser, lines)`
  - L216: `def parse_config(path)`
  - L266: `def _catalog_payload(path)`
  - L283: `def register(ctx)`

### A.267 `plugins/multi_model/ui/model-picker.js`

- 类型：JavaScript
- 行数：317
- 所属主模块：`app/plugins/multi_model`
- 文件角色：runtime/implementation
- addEventListener：9
- 顶层符号：
  - L19: `function pluginApi()`
  - L25: `function boot()`
  - L78: `function labelFor()`
  - L85: `function close()`
  - L91: `function open()`
  - L109: `function render()`
  - L165: `function select()`
  - L182: `function applyCatalog()`
  - L198: `function loadCatalog()`
  - L237: `function onMenuClick()`
  - L250: `function onDocClick()`
  - L253: `function onDocKeydown()`
  - L260: `function onPluginsChanged()`
  - L273: `function onConfigSaved()`
  - L279: `function onComposerPopupOpen()`

### A.268 `plugins/rules/plugin.py`

- 类型：Python
- 行数：221
- 所属主模块：`app/plugins/rules`
- 文件角色：runtime/implementation
- 文件说明：Rules 插件：`<项目根>/rules` 下的每个 `.md` 作为一条系统消息注入。
- 导入：`__future__`, `pathlib`, `typing`, `agent.capabilities.plugin_paths`, `agent.config`, `agent.core.error_report`
- 顶层符号：
  - L60: `def _hidden(rel)`
  - L65: `class RulesRuntime()`
  - L186: `def resource_directory_lines(runtime)`
  - L195: `def register(ctx)`
- 类成员：
  - L72: `RulesRuntime.__init__(self, root, max_bytes)`
  - L83: `RulesRuntime.enabled(self)`
  - L89: `RulesRuntime.rule_files(self)`
  - L115: `RulesRuntime.rel_of(self, path)`
  - L126: `RulesRuntime.read_text(self, path)`
  - L158: `RulesRuntime.payloads(self)`
  - L171: `RulesRuntime.build_system_messages(self, conversation_id)`
  - L181: `RulesRuntime.attached_count(self, conversation_id)`

### A.269 `plugins/skills/library.py`

- 类型：Python
- 行数：361
- 所属主模块：`app/plugins/skills`
- 文件角色：runtime/implementation
- 文件说明：Skills 库：扫描内置与外置来源 / 元数据解析 / 读取 / 复制计划（Skills 插件内部）。
- 导入：`__future__`, `os`, `threading`, `pathlib`, `typing`, `agent.core.error_report`
- 顶层符号：
  - L18: `def _canonical_key(path)`
  - L32: `class SkillMeta()`
  - L46: `class SkillManager()`
- 类成员：
  - L37: `SkillMeta.__init__(self, name, description, file_path, is_auto_load, source)`
  - L49: `SkillManager.__init__(self, skills_dir, max_file_size)`
  - L66: `SkillManager._root_specs(self)`
  - L78: `SkillManager._should_skip(file_path)`
  - L86: `SkillManager.auto_load_count(self)`
  - L92: `SkillManager._current_mtimes(self)`
  - L106: `SkillManager._check_rescan(self)`
  - L126: `SkillManager._scan(self)`
  - L133: `SkillManager._collect_skills(self)`
  - L177: `SkillManager._strip_frontmatter(text)`
  - L200: `SkillManager._parse_meta(self, file_path)`
  - L212: `SkillManager._deduped(self)`
  - L231: `SkillManager.list_skills(self)`
  - L249: `SkillManager.list_skill_names(self)`
  - L254: `SkillManager.get_skill_meta(self, name)`
  - L270: `SkillManager.get_skill(self, name)`
  - L296: `SkillManager.build_registry_message(self)`
  - L306: `SkillManager.build_registry_message_parts(self)`
  - L329: `SkillManager.build_auto_load_messages(self)`
  - L347: `SkillManager._read_content(self, meta)`

### A.270 `plugins/skills/plugin.py`

- 类型：Python
- 行数：152
- 所属主模块：`app/plugins/skills`
- 文件角色：runtime/implementation
- 文件说明：Skills 插件：Skills 库（扫描 / 读取）+ `skills` 工具 + 上下文注入。
- 导入：`__future__`, `os`, `pathlib`, `typing`, `agent.capabilities.plugin_paths`, `agent.capabilities.plugins`, `agent.config`, `.library`, `.tools`
- 顶层符号：
  - L43: `def _config_path()`
  - L51: `def _load_config(path)`
  - L82: `def register(ctx)`
  - L128: `def _resource_directory_lines(library)`
  - L145: `def _catalog_parts(library)`

### A.271 `plugins/skills/tools.py`

- 类型：Python
- 行数：65
- 所属主模块：`app/plugins/skills`
- 文件角色：runtime/implementation
- 文件说明：Skills 工具：list / read 只读直通。
- 导入：`__future__`, `typing`, `agent.capabilities.registry`, `.library`
- 顶层符号：
  - L12: `class SkillLookupError(RuntimeError)`
  - L20: `class SkillsTool(ToolPlugin)`
  - L62: `def build(library)`
- 类成员：
  - L15: `SkillLookupError.__init__(self, message, available)`
  - L35: `SkillsTool.__init__(self, library)`
  - L38: `SkillsTool.execute(self, arguments)`

### A.272 `plugins/skills/ui/tool-view.js`

- 类型：JavaScript
- 行数：55
- 所属主模块：`app/plugins/skills`
- 文件角色：runtime/implementation
- addEventListener：0
- 顶层符号：
  - L10: `function skillName()`
  - L14: `function skillContent()`

### A.273 `plugins/theme_style/plugin.py`

- 类型：Python
- 行数：82
- 所属主模块：`app/plugins/theme_style`
- 文件角色：runtime/implementation
- 文件说明：主题风格插件：界面风格设置与风格资源加载。
- 导入：`__future__`, `json`, `pathlib`, `typing`, `agent.capabilities.plugin_paths`, `agent.core.error_report`
- 顶层符号：
  - L21: `def _state_path(ctx)`
  - L26: `def _load_style(ctx)`
  - L39: `def _save_style(ctx, value)`
  - L55: `def register(ctx)`

### A.274 `plugins/theme_style/ui/theme-style.js`

- 类型：JavaScript
- 行数：141
- 所属主模块：`app/plugins/theme_style`
- 文件角色：runtime/implementation
- addEventListener：3
- 顶层符号：
  - L20: `function fetchStyle()`
  - L27: `function currentTheme()`
  - L31: `function assetUrl()`
  - L35: `function styleById()`
  - L44: `function clearAssets()`
  - L51: `function apply()`
  - L77: `function loadCatalog()`
  - L94: `function onSettingsChanged()`
  - L101: `function onPluginsChanged()`
  - L111: `function bindOnce()`
  - L126: `function start()`

### A.275 `plugins/visual_operator/backends/__init__.py`

- 类型：Python
- 行数：31
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：按平台选择后端。
- 导入：`__future__`, `sys`, `..ports`, `._unavailable`
- 顶层符号：
  - L16: `def load_backend()`

### A.276 `plugins/visual_operator/backends/_unavailable.py`

- 类型：Python
- 行数：60
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：不可用平台的后端：三个端口都只在调用时报错。
- 导入：`__future__`, `sys`, `typing`, `..coords`, `..errors`, `..ports`
- 顶层符号：
  - L19: `class UnavailableScreen()`
  - L27: `class UnavailableMouse()`
  - L46: `class UnavailableKeyboard()`
  - L57: `def unavailable_backend()`
- 类成员：
  - L20: `UnavailableScreen.geometry(self)`
  - L23: `UnavailableScreen.capture(self, region)`
  - L28: `UnavailableMouse.cursor(self)`
  - L31: `UnavailableMouse.move(self, point, duration_ms)`
  - L34: `UnavailableMouse.click(self, point, button, count)`
  - L37: `UnavailableMouse.drag(self, start, end, button, duration_ms)`
  - L41: `UnavailableMouse.scroll(self, point, amount, horizontal)`
  - L47: `UnavailableKeyboard.type_text(self, text, interval_ms)`
  - L50: `UnavailableKeyboard.press(self, key, repeat)`
  - L53: `UnavailableKeyboard.hotkey(self, keys, repeat)`

### A.277 `plugins/visual_operator/backends/macos.py`

- 类型：Python
- 行数：415
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：macOS 后端：screencapture 截屏 + CoreGraphics 输入。
- 导入：`__future__`, `ctypes`, `os`, `subprocess`, `tempfile`, `time`, `contextlib`, `typing`, `..coords`, `..errors`, `..ports`
- 顶层符号：
  - L95: `class CGPoint(ctypes.Structure)`
  - L99: `class CGSize(ctypes.Structure)`
  - L103: `class CGRect(ctypes.Structure)`
  - L142: `def _require_trusted()`
  - L154: `def _require_screen_access()`
  - L166: `def _displays()`
  - L186: `class MacScreen()`
  - L234: `class MacMouse()`
  - L314: `class MacKeyboard()`
  - L349: `def _keycode(key)`
  - L356: `def _point(point)`
  - L360: `def _warp(point)`
  - L364: `def _post_mouse(kind, point, button, click_state)`
  - L377: `def _post_key(code, down, flags)`
  - L389: `def _post_unicode(char)`
  - L405: `class MacOSBackend(Backend)`
- 类成员：
  - L189: `MacScreen.geometry(self)`
  - L206: `MacScreen.capture(self, region)`
  - L237: `MacMouse.cursor(self)`
  - L247: `MacMouse.move(self, point, duration_ms)`
  - L265: `MacMouse.click(self, point, button, count)`
  - L276: `MacMouse.drag(self, start, end, button, duration_ms)`
  - L296: `MacMouse.scroll(self, point, amount, horizontal)`
  - L317: `MacKeyboard.type_text(self, text, interval_ms)`
  - L329: `MacKeyboard.press(self, key, repeat)`
  - L336: `MacKeyboard.hotkey(self, keys, repeat)`
  - L412: `MacOSBackend.__init__(self)`

### A.278 `plugins/visual_operator/backends/win32.py`

- 类型：Python
- 行数：658
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：Windows 后端：GDI 截屏 + SendInput 输入。
- 导入：`__future__`, `io`, `time`, `ctypes`, `typing`, `..coords`, `..errors`, `..ports`, `..titles`, `.win32_common`, `.win32_uia`
- 顶层符号：
  - L71: `class Win32Screen()`
  - L107: `def _grab(rect)`
  - L146: `def _window_rect(hwnd)`
  - L156: `def _window_title(hwnd)`
  - L165: `def _window_class(hwnd)`
  - L172: `def _is_foreground(hwnd)`
  - L182: `def _bring_to_front(hwnd)`
  - L203: `def _restore_without_activation(hwnd)`
  - L215: `def _is_uniform(data)`
  - L232: `def _crop_bgra(data, width, height, x, y, crop_width, crop_height)`
  - L246: `def _print_window(hwnd, rect)`
  - L283: `class _GUITHREADINFO(ctypes.Structure)`
  - L293: `class Win32Focus()`
  - L315: `class Win32Windows()`
  - L489: `def _encode_bgra(data, width, height)`
  - L500: `class Win32Mouse()`
  - L552: `def _set_cursor(point)`
  - L562: `def _send_mouse(flags, data)`
  - L569: `class Win32Keyboard()`
  - L598: `def _virtual_key(key)`
  - L605: `def _send_key(vk, flags, scan)`
  - L612: `def _utf16_units(char)`
  - L620: `def _send_unicode(char)`
  - L626: `class Win32Hit()`
  - L650: `class Win32Backend(Backend)`
- 类成员：
  - L74: `Win32Screen.geometry(self)`
  - L101: `Win32Screen.capture(self, region)`
  - L296: `Win32Focus.focused(self)`
  - L326: `Win32Windows.get(self, hwnd)`
  - L337: `Win32Windows.find(self, title_contains)`
  - L386: `Win32Windows.list_visible(self)`
  - L417: `Win32Windows.activate(self, hwnd)`
  - L425: `Win32Windows.capture(self, hwnd, region)`
  - L503: `Win32Mouse.cursor(self)`
  - L509: `Win32Mouse.move(self, point, duration_ms)`
  - L523: `Win32Mouse.click(self, point, button, count)`
  - L533: `Win32Mouse.drag(self, start, end, button, duration_ms)`
  - L543: `Win32Mouse.scroll(self, point, amount, horizontal)`
  - L572: `Win32Keyboard.type_text(self, text, interval_ms)`
  - L583: `Win32Keyboard.press(self, key, repeat)`
  - L589: `Win32Keyboard.hotkey(self, keys, repeat)`
  - L633: `Win32Hit.probe(self, point)`
  - L653: `Win32Backend.__init__(self)`

### A.279 `plugins/visual_operator/backends/win32_common.py`

- 类型：Python
- 行数：276
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：Windows 后端：GDI 截屏 + SendInput 输入。
- 导入：`__future__`, `ctypes`, `contextlib`, `ctypes`, `typing`, `..coords`, `..keys`
- 顶层符号：
  - L70: `class BITMAPINFOHEADER(ctypes.Structure)`
  - L86: `class BITMAPINFO(ctypes.Structure)`
  - L90: `class POINT(ctypes.Structure)`
  - L94: `class MOUSEINPUT(ctypes.Structure)`
  - L105: `class KEYBDINPUT(ctypes.Structure)`
  - L115: `class HARDWAREINPUT(ctypes.Structure)`
  - L123: `class INPUT_UNION(ctypes.Union)`
  - L127: `class INPUT(ctypes.Structure)`
  - L224: `def _enable_dpi_awareness()`
  - L237: `def _last_error(message)`
  - L242: `def _system_metric(index)`
  - L246: `def _monitor_rects()`
  - L262: `def _monitor_dpis(rects)`

### A.280 `plugins/visual_operator/backends/win32_uia.py`

- 类型：Python
- 行数：151
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：Windows UIA 文本定位：通过系统 PowerShell 的 UIAutomationClient 查询控件树。
- 导入：`__future__`, `base64`, `json`, `os`, `subprocess`, `typing`, `..coords`, `..errors`, `..locate`
- 顶层符号：
  - L70: `class WindowsUiaLocator()`
- 类成员：
  - L73: `WindowsUiaLocator.__init__(self, executable, timeout_ms)`
  - L77: `WindowsUiaLocator.find(self, hwnd, text, match, limit)`
  - L113: `WindowsUiaLocator._parse(output)`
  - L128: `WindowsUiaLocator._match(row)`

### A.281 `plugins/visual_operator/canvas.py`

- 类型：Python
- 行数：325
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：截图加工：缩放、坐标网格、光标十字与 PNG 编码。
- 导入：`__future__`, `io`, `dataclasses`, `typing`, `.coords`, `.errors`
- 顶层符号：
  - L42: `class Rendered()`
  - L58: `def _pillow()`
  - L66: `def _is_blank(image)`
  - L71: `def _font(image_font, size)`
  - L79: `def cursor_label_visible(width, height)`
  - L84: `def cursor_font_size(width, height, scale)`
  - L93: `def _text_size(draw, text, font)`
  - L98: `def _draw_label(draw, position, text, font, text_height, width, height, color)`
  - L109: `def _draw_cursor_badge(draw, cursor_x, cursor_y, radius, title, coords, font, width, height)`
  - L147: `def _offset(origin, value, extent, pixels)`
  - L152: `def _label_value(value, origin, extent, pixels, grid_unit)`
  - L160: `def _draw_cursor(draw, image_font)`
  - L210: `def _draw_overlay(image, image_module, image_draw, image_font)`
  - L280: `def render(png)`
- 类成员：
  - L54: `Rendered.shrunk(self)`

### A.282 `plugins/visual_operator/capture_store.py`

- 类型：Python
- 行数：149
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：截图登记：只存坐标映射元数据，不存图片。
- 导入：`__future__`, `math`, `secrets`, `threading`, `time`, `dataclasses`, `typing`, `.coords`
- 顶层符号：
  - L26: `class CaptureRef()`
  - L75: `class CaptureStore()`
- 类成员：
  - L38: `CaptureRef.to_screen(self, image_x, image_y)`
  - L58: `CaptureRef.to_dict(self)`
  - L78: `CaptureStore.__init__(self, max_items, ttl_seconds, clock)`
  - L87: `CaptureStore.__len__(self)`
  - L91: `CaptureStore.clear(self)`
  - L95: `CaptureStore.put(self, session_id, rect, image_width, image_height)`
  - L123: `CaptureStore.resolve(self, session_id, capture_id)`
  - L136: `CaptureStore._new_id_locked(self)`
  - L142: `CaptureStore._purge_locked(self, now)`

### A.283 `plugins/visual_operator/config.py`

- 类型：Python
- 行数：102
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：插件配置：`[config]` 的读取、回退与夹取。
- 导入：`__future__`, `dataclasses`, `pathlib`, `typing`, `agent.config`
- 顶层符号：
  - L35: `class DesktopConfig()`
  - L60: `def _as_bool(raw, default)`
  - L69: `def _as_int(raw, key)`
  - L79: `def load_config(plugin_root)`

### A.284 `plugins/visual_operator/coords.py`

- 类型：Python
- 行数：80
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：屏幕几何：矩形、点、裁剪与比例换算。
- 导入：`__future__`, `dataclasses`, `typing`
- 顶层符号：
  - L14: `class ScreenPoint()`
  - L25: `class ScreenRect()`
  - L63: `class ScreenGeometry()`
- 类成员：
  - L20: `ScreenPoint.to_dict(self)`
  - L33: `ScreenRect.__post_init__(self)`
  - L38: `ScreenRect.right(self)`
  - L42: `ScreenRect.bottom(self)`
  - L45: `ScreenRect.contains(self, point)`
  - L48: `ScreenRect.intersect(self, other)`
  - L58: `ScreenRect.to_dict(self)`
  - L74: `ScreenGeometry.to_dict(self)`

### A.285 `plugins/visual_operator/diff.py`

- 类型：Python
- 行数：72
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：动作前后的画面差异：给"这一下到底有没有生效"一个可读的数字。
- 导入：`__future__`, `io`, `typing`, `agent.core.error_report`, `.coords`, `.errors`
- 顶层符号：
  - L27: `def probe_region(point, bounds, side)`
  - L40: `def change_ratio(before, after)`
  - L67: `def _thumb(image_module, png)`

### A.286 `plugins/visual_operator/errors.py`

- 类型：Python
- 行数：28
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：桌面能力异常：不可用、缺权限、截屏失败、输入被占用。
- 导入：`__future__`
- 顶层符号：
  - L10: `class DesktopError(RuntimeError)`
  - L14: `class DesktopUnavailable(DesktopError)`
  - L18: `class DesktopPermissionDenied(DesktopUnavailable)`
  - L22: `class ScreenCaptureFailed(DesktopUnavailable)`
  - L26: `class DesktopBusy(DesktopError)`

### A.287 `plugins/visual_operator/guard.py`

- 类型：Python
- 行数：28
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：Plan 模式门控：会改变桌面的动作在 Plan 模式下拒绝。
- 导入：`__future__`, `typing`, `agent.common.status`, `agent.core.session_scope`, `agent.mechanisms.live_state`
- 顶层符号：
  - L15: `def reject_in_plan(live_state, action)`

### A.288 `plugins/visual_operator/input_lock.py`

- 类型：Python
- 行数：32
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：输入动作串行锁。
- 导入：`__future__`, `threading`, `contextlib`, `typing`, `.errors`
- 顶层符号：
  - L21: `def input_guard(timeout)`

### A.289 `plugins/visual_operator/keys.py`

- 类型：Python
- 行数：107
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：跨平台键名：规范名、别名归一与组合键校验。
- 导入：`__future__`, `typing`
- 顶层符号：
  - L66: `def canonical(name)`
  - L82: `def split_hotkey(raw)`
  - L99: `def normalize_hotkey(raw)`

### A.290 `plugins/visual_operator/locate.py`

- 类型：Python
- 行数：43
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：文本定位端口：把「按文字找控件」从坐标原语里分出来。
- 导入：`__future__`, `dataclasses`, `typing`, `.coords`
- 顶层符号：
  - L16: `class LocatorMatch()`
  - L37: `class LocatorPort(Protocol)`
- 类成员：
  - L26: `LocatorMatch.to_dict(self)`
  - L40: `LocatorPort.find(self, hwnd, text, match, limit)`

### A.291 `plugins/visual_operator/pipeline.py`

- 类型：Python
- 行数：148
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：`desktop_act` 的批量执行骨架：校验、超时、步日志与失败即停。
- 导入：`__future__`, `time`, `dataclasses`, `typing`, `agent.core.error_report`
- 顶层符号：
  - L21: `class BatchResult()`
  - L29: `def normalize_steps(raw)`
  - L62: `def is_read_only(verb, args)`
  - L74: `def destructive_hit(steps)`
  - L85: `def sanitize(value)`
  - L99: `def run(steps, execute, assert_step)`

### A.292 `plugins/visual_operator/plugin.py`

- 类型：Python
- 行数：76
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：Visual Operator 插件：眼（截屏）、手（鼠标 / 键盘）、等待与窗口/应用/打开工具。
- 导入：`__future__`, `typing`, `agent.capabilities.registry`, `.backends`, `.capture_store`, `.config`, `.ports`, `.tools`
- 顶层符号：
  - L37: `def build_tools(config, backend, live_state, captures)`
  - L62: `def register(ctx)`

### A.293 `plugins/visual_operator/ports.py`

- 类型：Python
- 行数：231
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：桌面后端的三条端口与数据结构。
- 导入：`__future__`, `dataclasses`, `typing`, `.coords`, `.locate`
- 顶层符号：
  - L23: `class Screenshot()`
  - L47: `class WindowInfo()`
  - L73: `class WindowActivation()`
  - L99: `class FocusInfo()`
  - L112: `class FocusPort(Protocol)`
  - L119: `class ScreenPort(Protocol)`
  - L131: `class WindowPort(Protocol)`
  - L170: `class MousePort(Protocol)`
  - L190: `class KeyboardPort(Protocol)`
  - L203: `class HitPort(Protocol)`
  - L216: `class Backend()`
- 类成员：
  - L61: `WindowInfo.to_dict(self)`
  - L85: `WindowActivation.to_dict(self)`
  - L107: `FocusInfo.to_dict(self)`
  - L115: `FocusPort.focused(self)`
  - L122: `ScreenPort.geometry(self)`
  - L126: `ScreenPort.capture(self, region)`
  - L138: `WindowPort.get(self, hwnd)`
  - L142: `WindowPort.find(self, title_contains)`
  - L150: `WindowPort.activate(self, hwnd)`
  - L157: `WindowPort.capture(self, hwnd, region)`
  - L173: `MousePort.cursor(self)`
  - L176: `MousePort.move(self, point, duration_ms)`
  - L179: `MousePort.click(self, point, button, count)`
  - L182: `MousePort.drag(self, start, end, button, duration_ms)`
  - L186: `MousePort.scroll(self, point, amount, horizontal)`
  - L193: `KeyboardPort.type_text(self, text, interval_ms)`
  - L196: `KeyboardPort.press(self, key, repeat)`
  - L199: `KeyboardPort.hotkey(self, keys, repeat)`
  - L210: `HitPort.probe(self, point)`

### A.294 `plugins/visual_operator/titles.py`

- 类型：Python
- 行数：20
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：窗口标题匹配：忽略不可见格式字符与空白差异。
- 导入：`__future__`, `re`
- 顶层符号：
  - L11: `def normalize_title(text)`
  - L16: `def title_matches(title, needle)`

### A.295 `plugins/visual_operator/tools/__init__.py`

- 类型：Python
- 行数：20
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：视觉操作工具类的统一出口。
- 导入：`.act`, `.app`, `.click_region`, `.click_text`, `.eye`, `.find`, `.keyboard`, `.mouse`, `.open`, `.type_into`, `.wait`, `.window`
- 顶层符号：无

### A.296 `plugins/visual_operator/tools/_capture.py`

- 类型：Python
- 行数：453
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：截图取图与加工的唯一入口。
- 导入：`__future__`, `base64`, `time`, `dataclasses`, `typing`, `agent.core.error_report`, `agent.core.session_scope`, `..`, `..capture_store`, `..config`, `..coords`, `..errors`, `..ports`, `._params`, `._windows`
- 顶层符号：
  - L35: `class CaptureRequest()`
  - L63: `def request_from_arguments(backend, config, arguments)`
  - L85: `def _annotate(arguments)`
  - L95: `def _grid_unit(arguments)`
  - L103: `def region_from_arguments(arguments, bounds)`
  - L125: `def _select_target(backend, request, region, initial_probe)`
  - L144: `def _capture(backend, request, target, region, geometry)`
  - L162: `def _render(screenshot, request, config, cursor, step)`
  - L180: `def _image_info(item)`
  - L186: `def _window_summary(summary, request, target, matched, candidates, auto_target, screenshot)`
  - L203: `def _hover_summary(summary, request, backend)`
  - L221: `def capture_payload(backend, config, request)`
  - L290: `def build_note(rendered, mixed_scale, step)`
  - L344: `def _ambiguity_note(matched, candidates, target)`
  - L360: `def _hover(request, backend)`
  - L383: `def _return_to(point, backend)`
  - L397: `def _wiggle(point, backend)`
  - L408: `def _hover_mismatch(hover_hit, target)`
  - L434: `def _check_area(pixels)`
  - L442: `def _text(arguments, key)`
  - L449: `def _hwnd(arguments)`

### A.297 `plugins/visual_operator/tools/_evidence.py`

- 类型：Python
- 行数：49
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：动作前后的落点区域像素证据。
- 导入：`__future__`, `typing`, `agent.core.error_report`, `..coords`, `..diff`
- 顶层符号：
  - L13: `def begin(backend, point, side)`
  - L28: `def begin_rect(backend, region)`
  - L38: `def finish(backend, before)`

### A.298 `plugins/visual_operator/tools/_params.py`

- 类型：Python
- 行数：120
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：工具参数读取：类型校验、取值范围与动作矩阵检查。
- 导入：`__future__`, `typing`, `..coords`
- 顶层符号：
  - L19: `def has(arguments, key)`
  - L25: `def _raw(arguments, key)`
  - L32: `def as_int(arguments, key, default)`
  - L50: `def as_text(arguments, key)`
  - L60: `def as_bool(arguments, key, default)`
  - L74: `def choice(arguments, key, allowed, default)`
  - L89: `def require_range(value, key, low, high)`
  - L98: `def reject_unknown(arguments, allowed)`
  - L109: `def point_argument(arguments, x_key, y_key)`

### A.299 `plugins/visual_operator/tools/_windows.py`

- 类型：Python
- 行数：110
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：`window` / `hwnd` 参数的解析与前置激活。
- 导入：`__future__`, `typing`, `..errors`, `..ports`, `._params`
- 顶层符号：
  - L22: `def window_candidates(backend, arguments)`
  - L54: `def window_target(backend, arguments)`
  - L61: `def alternatives(candidates)`
  - L73: `def focus_target(backend, arguments)`
  - L97: `def require_active(receipt, action)`

### A.300 `plugins/visual_operator/tools/act.py`

- 类型：Python
- 行数：256
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：`desktop_act`：带断言的多步桌面管线。
- 导入：`__future__`, `time`, `typing`, `agent.capabilities.registry`, `agent.core.error_report`, `agent.core.tool_call`, `..capture_store`, `..config`, `..coords`, `..guard`, `..input_lock`, `..pipeline`, `..ports`, `._params`, `._windows`, `.app`, `.click_region`, `.click_text`, `.eye`, `.find`
- 顶层符号：
  - L39: `class DesktopActTool(ToolPlugin)`
- 类成员：
  - L65: `DesktopActTool.__init__(self, backend, config, live_state, captures)`
  - L89: `DesktopActTool.execute(self, arguments)`
  - L127: `DesktopActTool._execute(self, verb, arguments)`
  - L147: `DesktopActTool._resolve(self, value)`
  - L175: `DesktopActTool._assert_step(self, expect, data)`
  - L189: `DesktopActTool._check_once(self, expect, data)`
  - L247: `DesktopActTool._capture(self)`

### A.301 `plugins/visual_operator/tools/app.py`

- 类型：Python
- 行数：171
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：`desktop_app`：启动本地程序并等待主窗口。
- 导入：`__future__`, `os`, `subprocess`, `sys`, `time`, `pathlib`, `typing`, `agent.capabilities.registry`, `..errors`, `..guard`, `..ports`, `..titles`, `._params`
- 顶层符号：
  - L21: `class DesktopAppTool(ToolPlugin)`
  - L115: `def _start_menu_roots(roots)`
  - L128: `def _find_start_menu(name, roots)`
  - L156: `def _start_shortcut(path)`
  - L162: `def _pick_window(matches, title)`
- 类成员：
  - L47: `DesktopAppTool.__init__(self, backend, live_state)`
  - L51: `DesktopAppTool.execute(self, arguments)`

### A.302 `plugins/visual_operator/tools/click_region.py`

- 类型：Python
- 行数：118
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：`desktop_click_region`：用视觉矩形中心点击，避免模型估中心点。
- 导入：`__future__`, `time`, `typing`, `agent.capabilities.registry`, `agent.core.error_report`, `agent.core.session_scope`, `..capture_store`, `..coords`, `..guard`, `..input_lock`, `..ports`, `._evidence`, `._params`, `._windows`
- 顶层符号：
  - L22: `class DesktopClickRegionTool(ToolPlugin)`
  - L108: `def _title_changed(backend, focus)`
- 类成员：
  - L50: `DesktopClickRegionTool.__init__(self, backend, live_state, captures)`
  - L56: `DesktopClickRegionTool.execute(self, arguments)`

### A.303 `plugins/visual_operator/tools/click_text.py`

- 类型：Python
- 行数：92
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：`desktop_click_text`：定位文字控件并点击。
- 导入：`__future__`, `time`, `typing`, `agent.capabilities.registry`, `..errors`, `..guard`, `..input_lock`, `..ports`, `._evidence`, `._params`, `._windows`
- 顶层符号：
  - L21: `class DesktopClickTextTool(ToolPlugin)`
  - L89: `def _center(rect)`
- 类成员：
  - L43: `DesktopClickTextTool.__init__(self, backend, live_state)`
  - L47: `DesktopClickTextTool.execute(self, arguments)`

### A.304 `plugins/visual_operator/tools/eye.py`

- 类型：Python
- 行数：186
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：`desktop_eye`：截屏、叠网格、把图片作为附件交给模型。
- 导入：`__future__`, `dataclasses`, `typing`, `agent.capabilities.registry`, `agent.core.tool_call`, `..capture_store`, `..config`, `..coords`, `..guard`, `..ports`, `._capture`, `._params`
- 顶层符号：
  - L24: `class DesktopEyeTool(ToolPlugin)`
  - L160: `def _hover_point(arguments)`
  - L168: `def _hover_path(arguments)`
  - L178: `def _as_point(value, name)`
- 类成员：
  - L111: `DesktopEyeTool.__init__(self, backend, config, live_state, captures)`
  - L119: `DesktopEyeTool.execute(self, arguments)`

### A.305 `plugins/visual_operator/tools/find.py`

- 类型：Python
- 行数：96
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：`desktop_find`：用 UIA 文本定位控件，不做 OCR。
- 导入：`__future__`, `typing`, `agent.capabilities.registry`, `..coords`, `..errors`, `..ports`, `..titles`, `._params`, `._windows`
- 顶层符号：
  - L20: `class DesktopFindTool(ToolPlugin)`
  - L85: `def _region(arguments)`
- 类成员：
  - L43: `DesktopFindTool.__init__(self, backend)`
  - L46: `DesktopFindTool.execute(self, arguments)`

### A.306 `plugins/visual_operator/tools/keyboard.py`

- 类型：Python
- 行数：136
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：`desktop_keyboard`：输入文本、按键与组合键。
- 导入：`__future__`, `time`, `typing`, `agent.capabilities.registry`, `agent.core.tool_call`, `..capture_store`, `..config`, `..guard`, `..input_lock`, `..keys`, `..keys`, `..ports`, `._capture`, `._evidence`, `._params`, `._windows`
- 顶层符号：
  - L32: `class DesktopKeyboardTool(ToolPlugin)`
  - L133: `def _optional_text(arguments, key)`
- 类成员：
  - L67: `DesktopKeyboardTool.__init__(self, backend, config, live_state, captures)`
  - L75: `DesktopKeyboardTool.execute(self, arguments)`

### A.307 `plugins/visual_operator/tools/mouse.py`

- 类型：Python
- 行数：464
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：`desktop_mouse`：移动、点击、拖拽、滚动与光标查询。
- 导入：`__future__`, `time`, `typing`, `agent.capabilities.registry`, `agent.core.error_report`, `agent.core.session_scope`, `agent.core.tool_call`, `..capture_store`, `..config`, `..coords`, `..diff`, `..guard`, `..input_lock`, `..ports`, `._capture`, `._params`, `._windows`
- 顶层符号：
  - L55: `class DesktopMouseTool(ToolPlugin)`
  - L390: `def _coordinate_space(arguments)`
  - L404: `def _mapped_point(point, capture)`
  - L412: `def _require_point(point, message)`
  - L418: `def _optional_text(arguments, key)`
  - L423: `def _root_hwnd(hit)`
  - L434: `def _hit_brief(hit)`
  - L448: `def _shot_region(arguments, bounds)`
- 类成员：
  - L116: `DesktopMouseTool.__init__(self, backend, config, live_state, captures)`
  - L124: `DesktopMouseTool._perform(self, action, arguments, point, capture, port)`
  - L158: `DesktopMouseTool.execute(self, arguments)`
  - L228: `DesktopMouseTool._resolve_capture(self, arguments, space)`
  - L243: `DesktopMouseTool._shot_request(self, arguments, point, performed)`
  - L283: `DesktopMouseTool._window_digest(self)`
  - L298: `DesktopMouseTool._window_delta(self, before_hit, after_hit, before_windows, after_windows, local_ratio)`
  - L345: `DesktopMouseTool._change_after(self, before, point)`
  - L350: `DesktopMouseTool._probe(self, point)`
  - L356: `DesktopMouseTool._sample(self, point)`
  - L363: `DesktopMouseTool._change(self, before, point)`
  - L369: `DesktopMouseTool._settle(self)`
  - L373: `DesktopMouseTool._ensure_inside(self)`
  - L381: `DesktopMouseTool._snapshot(self, action)`

### A.308 `plugins/visual_operator/tools/open.py`

- 类型：Python
- 行数：168
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：`desktop_open`：用系统默认程序打开 URL / scheme / 文件。
- 导入：`__future__`, `os`, `subprocess`, `sys`, `time`, `pathlib`, `typing`, `agent.capabilities.registry`, `..errors`, `..guard`, `..ports`, `._params`
- 顶层符号：
  - L20: `class DesktopOpenTool(ToolPlugin)`
  - L164: `def _looks_browser(title)`
- 类成员：
  - L44: `DesktopOpenTool.__init__(self, backend, live_state)`
  - L48: `DesktopOpenTool.execute(self, arguments)`
  - L94: `DesktopOpenTool._opened(self, target, method, window, windows, before, title, started, arguments, reused)`
  - L121: `DesktopOpenTool._title_ok(title, needle)`
  - L126: `DesktopOpenTool._choose(cls, windows, title)`
  - L138: `DesktopOpenTool._valid_target(target)`
  - L150: `DesktopOpenTool._launch(target)`

### A.309 `plugins/visual_operator/tools/type_into.py`

- 类型：Python
- 行数：158
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：`desktop_type_into`：按文字定位输入框并输入。
- 导入：`__future__`, `sys`, `time`, `typing`, `agent.capabilities.registry`, `agent.core.error_report`, `agent.core.session_scope`, `..capture_store`, `..config`, `..coords`, `..errors`, `..guard`, `..input_lock`, `..ports`, `._evidence`, `._params`, `._windows`
- 顶层符号：
  - L25: `class DesktopTypeIntoTool(ToolPlugin)`
  - L143: `def _center(rect)`
  - L148: `def _title_changed(backend, focus)`
- 类成员：
  - L59: `DesktopTypeIntoTool.__init__(self, backend, config, live_state, captures)`
  - L66: `DesktopTypeIntoTool.execute(self, arguments)`

### A.310 `plugins/visual_operator/tools/wait.py`

- 类型：Python
- 行数：246
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：`desktop_wait`：等一个可观测的条件成立，而不是盲睡固定秒数。
- 导入：`__future__`, `time`, `typing`, `agent.capabilities.registry`, `agent.core.error_report`, `..config`, `..coords`, `..diff`, `..errors`, `..ports`, `._capture`, `._params`
- 顶层符号：
  - L30: `class DesktopWaitTool(ToolPlugin)`
  - L225: `def _title(arguments)`
  - L231: `def _threshold(arguments)`
  - L244: `def _elapsed_ms(started)`
- 类成员：
  - L61: `DesktopWaitTool.__init__(self, backend, config)`
  - L65: `DesktopWaitTool.execute(self, arguments)`
  - L80: `DesktopWaitTool._wait_change(self, arguments, timeout_ms, interval_ms, threshold)`
  - L133: `DesktopWaitTool._wait_window(self, arguments, until, title, timeout_ms, interval_ms)`
  - L182: `DesktopWaitTool._target_window(self, arguments)`
  - L197: `DesktopWaitTool._window_region(self, arguments)`
  - L215: `DesktopWaitTool._usable_rect(info)`

### A.311 `plugins/visual_operator/tools/window.py`

- 类型：Python
- 行数：117
- 所属主模块：`app/plugins/visual_operator`
- 文件角色：runtime/implementation
- 文件说明：`desktop_window`：列出、激活、等待和读取窗口。
- 导入：`__future__`, `time`, `typing`, `agent.capabilities.registry`, `..errors`, `..guard`, `..ports`, `..titles`, `._params`, `._windows`
- 顶层符号：
  - L18: `class DesktopWindowTool(ToolPlugin)`
- 类成员：
  - L45: `DesktopWindowTool.__init__(self, backend, live_state)`
  - L49: `DesktopWindowTool.execute(self, arguments)`
  - L63: `DesktopWindowTool._list(self, arguments)`
  - L81: `DesktopWindowTool._wait(self, arguments)`

### A.312 `plugins/visual_operator_2/__init__.py`

- 类型：Python
- 行数：1
- 所属主模块：`app/plugins/visual_operator_2`
- 文件角色：runtime/implementation
- 顶层符号：无

### A.313 `plugins/visual_operator_2/backend.py`

- 类型：Python
- 行数：720
- 所属主模块：`app/plugins/visual_operator_2`
- 文件角色：runtime/implementation
- 文件说明：视觉操作 2.0 的 Windows 采集与 HID 原语。
- 导入：`__future__`, `ctypes`, `ctypes.wintypes`, `sys`, `threading`, `time`, `contextlib`, `typing`, `PIL`, `agent.core.error_report`, `agent.core.thread_context`, `.step_log`
- 顶层符号：
  - L31: `def _enable_dpi_awareness()`
  - L58: `class _MOUSEINPUT(ctypes.Structure)`
  - L69: `class _KEYBDINPUT(ctypes.Structure)`
  - L79: `class _INPUTUNION(ctypes.Union)`
  - L83: `class _INPUT(ctypes.Structure)`
  - L270: `class HumanInputMonitor()`
  - L442: `class ControlBadge()`
  - L575: `def capture_screen()`
  - L582: `def cursor_position()`
  - L591: `def set_cursor(x, y)`
  - L603: `def move_by(dx, dy)`
  - L612: `def move_cursor(x, y, duration_ms, should_stop)`
  - L636: `def click(button, count)`
  - L669: `def _key_code(name)`
  - L678: `def press_keys(keys)`
- 类成员：
  - L273: `HumanInputMonitor.__init__(self, takeover_distance)`
  - L293: `HumanInputMonitor.register_inject_tag(self, tag)`
  - L300: `HumanInputMonitor._is_injected_tag(self, extra)`
  - L304: `HumanInputMonitor.bind(self, callback)`
  - L307: `HumanInputMonitor.start(self)`
  - L322: `HumanInputMonitor.stop(self)`
  - L337: `HumanInputMonitor._run(self)`
  - L373: `HumanInputMonitor._reset_mouse(self)`
  - L378: `HumanInputMonitor.record_human_move(self, x, y)`
  - L394: `HumanInputMonitor._on_mouse(self, code, wparam, lparam)`
  - L410: `HumanInputMonitor._on_keyboard(self, code, wparam, lparam)`
  - L421: `HumanInputMonitor._fire(self)`
  - L430: `HumanInputMonitor._fire_worker(self)`
  - L448: `ControlBadge.__init__(self)`
  - L457: `ControlBadge.show(self)`
  - L482: `ControlBadge.hide(self)`
  - L489: `ControlBadge.close(self)`
  - L495: `ControlBadge._run(self)`
  - L535: `ControlBadge._on_message(self, hwnd, message, wparam, lparam)`

### A.314 `plugins/visual_operator_2/calibration.py`

- 类型：Python
- 行数：165
- 所属主模块：`app/plugins/visual_operator_2`
- 文件角色：runtime/implementation
- 文件说明：随机校准点：模型图坐标到屏幕坐标的 32px 复核。
- 导入：`__future__`, `random`, `typing`, `.`
- 顶层符号：
  - L14: `def new_points(width, height, cursor)`
  - L29: `def challenge_error(points, expected, center_x, center_y, image_width, image_height, tolerance)`
  - L51: `def model_error(points, expected, tolerance)`
  - L67: `class ChallengeStore()`
  - L162: `def public_points(points)`
- 类成员：
  - L70: `ChallengeStore.__init__(self, tolerance, enabled)`
  - L75: `ChallengeStore.clear(self)`
  - L78: `ChallengeStore.__contains__(self, frame_id)`
  - L81: `ChallengeStore.__getitem__(self, frame_id)`
  - L84: `ChallengeStore.get(self, frame, full)`
  - L102: `ChallengeStore.consume(self, frame_id)`
  - L105: `ChallengeStore.error(self, points, frame_id, center_x, center_y, image_width, image_height, model_only, challenge)`
  - L121: `ChallengeStore.report(self, points, frame_id, center_x, center_y, image_width, image_height, model_only, challenge)`

### A.315 `plugins/visual_operator_2/config.py`

- 类型：Python
- 行数：87
- 所属主模块：`app/plugins/visual_operator_2`
- 文件角色：runtime/implementation
- 文件说明：视觉操作 2.0 插件配置。
- 导入：`__future__`, `configparser`, `dataclasses`, `pathlib`
- 顶层符号：
  - L11: `class VisionConfig()`
  - L30: `def _int(section, key, default, low, high)`
  - L39: `def _float(section, key, default, low, high)`
  - L48: `def _bool(section, key, default)`
  - L57: `def load_config(path)`

### A.316 `plugins/visual_operator_2/consent.py`

- 类型：Python
- 行数：39
- 所属主模块：`app/plugins/visual_operator_2`
- 文件角色：runtime/implementation
- 文件说明：视觉授权异常与固定文案。
- 导入：`__future__`, `typing`
- 顶层符号：
  - L14: `class VisionConsentRequired(Exception)`
  - L32: `def options()`
- 类成员：
  - L19: `VisionConsentRequired.__init__(self, request_id, conversation_id)`

### A.317 `plugins/visual_operator_2/desktop.py`

- 类型：Python
- 行数：129
- 所属主模块：`app/plugins/visual_operator_2`
- 文件角色：runtime/implementation
- 文件说明：2.0 授权下的桌面辅助工具：窗口、应用、单次看屏、文本输入、滚动/拖拽。
- 导入：`__future__`, `pathlib`, `typing`, `agent.capabilities.registry`, `plugins.visual_operator.backends`, `plugins.visual_operator.capture_store`, `plugins.visual_operator.config`, `plugins.visual_operator.tools.app`, `plugins.visual_operator.tools.click_text`, `plugins.visual_operator.tools.eye`, `plugins.visual_operator.tools.find`, `plugins.visual_operator.tools.keyboard`, `plugins.visual_operator.tools.mouse`, `plugins.visual_operator.tools.open`, `plugins.visual_operator.tools.type_into`, `plugins.visual_operator.tools.wait`, `plugins.visual_operator.tools.window`, `.`, `.state`
- 顶层符号：
  - L32: `def _cid()`
  - L37: `class _AuthorizedDesktopTool(ToolPlugin)`
  - L104: `def build_tools(runtime)`
- 类成员：
  - L38: `_AuthorizedDesktopTool.__init__(self, tool, runtime, name, label, description)`
  - L47: `_AuthorizedDesktopTool.name(self)`
  - L51: `_AuthorizedDesktopTool.label(self)`
  - L55: `_AuthorizedDesktopTool.icon(self)`
  - L59: `_AuthorizedDesktopTool.description(self)`
  - L63: `_AuthorizedDesktopTool.description(self, value)`
  - L67: `_AuthorizedDesktopTool.parameters(self)`
  - L82: `_AuthorizedDesktopTool.parallel_safe(self)`
  - L85: `_AuthorizedDesktopTool.__getattr__(self, key)`
  - L88: `_AuthorizedDesktopTool.execute(self, arguments)`

### A.318 `plugins/visual_operator_2/observation.py`

- 类型：Python
- 行数：145
- 所属主模块：`app/plugins/visual_operator_2`
- 文件角色：runtime/implementation
- 文件说明：视觉观察载荷：把最近帧渲染成模型可读的完整图、标签与校准点。
- 导入：`__future__`, `time`, `typing`, `.`, `.config`
- 顶层符号：
  - L12: `def render_full(frame, max_side, config, challenges)`
  - L37: `def render_focus(frame, focus, config)`
  - L49: `def _history_views(history, config, challenges)`
  - L79: `def build_observation(history, focus, config, challenges, owner, last_calibration)`
  - L142: `def calibration_points(challenge)`

### A.319 `plugins/visual_operator_2/plugin.py`

- 类型：Python
- 行数：133
- 所属主模块：`app/plugins/visual_operator_2`
- 文件角色：runtime/implementation
- 文件说明：视觉操作 2.0：持续视觉、全局独占、用户授权与键鼠动作。
- 导入：`__future__`, `pathlib`, `typing`, `agent.capabilities.plugin_paths`, `agent.core.error_report`, `.`, `.config`, `.routes`, `.state`, `.tools`
- 顶层符号：
  - L22: `def _observation_hook(runtime)`
  - L54: `def _vision_prompt(_cid)`
  - L77: `def _step_log_path(ctx)`
  - L89: `def register(ctx)`

### A.320 `plugins/visual_operator_2/render.py`

- 类型：Python
- 行数：199
- 所属主模块：`app/plugins/visual_operator_2`
- 文件角色：runtime/implementation
- 文件说明：视觉操作 2.0 的图像加工：缩放、屏幕坐标辅助线、鼠标标记与编码。
- 导入：`__future__`, `base64`, `io`, `typing`, `PIL`, `.config`
- 顶层符号：
  - L14: `def fit(image, max_side)`
  - L25: `def clip_focus(region, screen_size)`
  - L44: `def focus_screen_from_model(screen_width, screen_height, x, y, width, height, center_x, center_y, image_width, image_height)`
  - L65: `def focus_point_screen(focus, x, y, width, height)`
  - L79: `def full_point_screen(screen_width, screen_height, x, y, center_x, center_y, image_width, image_height)`
  - L99: `def targets_for_points(frame, points, center_x, center_y, image_width, image_height)`
  - L113: `def draw_marker(image, point)`
  - L140: `def draw_calibration(image, points, screen_width, screen_height)`
  - L161: `def focus_view(image, focus, cursor, config)`
  - L184: `def data_url(image, config)`

### A.321 `plugins/visual_operator_2/routes.py`

- 类型：Python
- 行数：97
- 所属主模块：`app/plugins/visual_operator_2`
- 文件角色：runtime/implementation
- 文件说明：视觉授权 HTTP 端点。
- 导入：`__future__`, `typing`, `.consent`, `.state`
- 顶层符号：
  - L11: `def _body(args)`
  - L18: `def _cid(args)`
  - L23: `def build_routes(ctx, runtime)`

### A.322 `plugins/visual_operator_2/state.py`

- 类型：Python
- 行数：760
- 所属主模块：`app/plugins/visual_operator_2`
- 文件角色：runtime/implementation
- 文件说明：视觉操作 2.0 全局运行态。
- 导入：`__future__`, `threading`, `time`, `uuid`, `collections`, `dataclasses`, `typing`, `PIL`, `agent.core.error_report`, `agent.core.thread_context`, `.`, `.config`, `.consent`
- 顶层符号：
  - L36: `class Frame()`
  - L45: `class PendingConsent()`
  - L49: `class VisionRuntime()`
- 类成员：
  - L51: `VisionRuntime.__init__(self, config)`
  - L88: `VisionRuntime.request_open(self, conversation_id, call_id)`
  - L122: `VisionRuntime.pending(self, conversation_id)`
  - L134: `VisionRuntime.confirm(self, conversation_id, request_id, choice)`
  - L164: `VisionRuntime.start(self, conversation_id, consent_id)`
  - L213: `VisionRuntime._stop_monitor(self)`
  - L221: `VisionRuntime.user_takeover(self)`
  - L248: `VisionRuntime.stop(self, conversation_id)`
  - L274: `VisionRuntime.revoke(self, conversation_id)`
  - L276: `VisionRuntime.status(self, conversation_id)`
  - L287: `VisionRuntime._calibration_error(self, points, frame_id, conversation_id, center_x, center_y, image_width, image_height, model_only)`
  - L304: `VisionRuntime._observed_calibration(self, frame_id)`
  - L310: `VisionRuntime._drop_frames_locked(self)`
  - L319: `VisionRuntime._granted_locked(self, conversation_id)`
  - L323: `VisionRuntime.observe(self, conversation_id)`
  - L341: `VisionRuntime.publish_observation(self, observation)`
  - L365: `VisionRuntime.focus(self, conversation_id, x, y, width, height, center_x, center_y, image_width, image_height)`
  - L391: `VisionRuntime.move(self, conversation_id, dx, dy)`
  - L417: `VisionRuntime.move_point(self, conversation_id, x, y, center_x, center_y, image_width, image_height, check_points)`
  - L466: `VisionRuntime.move_focus(self, conversation_id, x, y, width, height)`
  - L503: `VisionRuntime.click(self, conversation_id, button, count, interval_ms)`
  - L541: `VisionRuntime.click_sequence(self, conversation_id, points, center_x, center_y, image_width, image_height, interval_ms, count, check_points)`
  - L617: `VisionRuntime.key(self, conversation_id, keys)`
  - L632: `VisionRuntime._start_capture_locked(self)`
  - L639: `VisionRuntime._capture_loop(self)`
  - L666: `VisionRuntime._capture_after_action(self, conversation_id, delay_ms)`
  - L690: `VisionRuntime._remember_frame(self, image, cursor, generation)`
  - L726: `VisionRuntime._wake_owner(self, conversation_id)`
  - L734: `VisionRuntime._emit(self, event, payload)`
  - L742: `VisionRuntime.close(self)`

### A.323 `plugins/visual_operator_2/step_log.py`

- 类型：Python
- 行数：50
- 所属主模块：`app/plugins/visual_operator_2`
- 文件角色：runtime/implementation
- 文件说明：视觉操作步骤日志：JSONL，追加写，失败只忽略。
- 导入：`__future__`, `json`, `threading`, `datetime`, `pathlib`, `typing`, `agent.core.error_report`
- 顶层符号：
  - L18: `def configure(path)`
  - L23: `def write(event)`

### A.324 `plugins/visual_operator_2/tools.py`

- 类型：Python
- 行数：404
- 所属主模块：`app/plugins/visual_operator_2`
- 文件角色：runtime/implementation
- 文件说明：视觉操作 2.0 工具面。
- 导入：`__future__`, `typing`, `agent.capabilities.registry`, `agent.core.session_scope`, `.consent`, `.desktop`, `.state`, `.step_log`
- 顶层符号：
  - L19: `def _cid()`
  - L24: `def _call_id()`
  - L29: `def _int_arg(arguments, key)`
  - L50: `class VisionRequestOpenTool(ToolPlugin)`
  - L76: `class VisionStartTool(ToolPlugin)`
  - L96: `class VisionFocusTool(ToolPlugin)`
  - L131: `class VisionMoveTool(ToolPlugin)`
  - L149: `class VisionMovePointTool(ToolPlugin)`
  - L182: `class VisionMoveFocusTool(ToolPlugin)`
  - L210: `class VisionClickTool(ToolPlugin)`
  - L234: `class VisionClickSequenceTool(ToolPlugin)`
  - L290: `class VisionKeyTool(ToolPlugin)`
  - L315: `class VisionStopTool(ToolPlugin)`
  - L339: `class _LoggedTool(ToolPlugin)`
  - L385: `def build_tools(runtime)`
- 类成员：
  - L63: `VisionRequestOpenTool.__init__(self, runtime)`
  - L66: `VisionRequestOpenTool.execute(self, arguments)`
  - L89: `VisionStartTool.__init__(self, runtime)`
  - L92: `VisionStartTool.execute(self, arguments)`
  - L118: `VisionFocusTool.__init__(self, runtime)`
  - L121: `VisionFocusTool.execute(self, arguments)`
  - L142: `VisionMoveTool.__init__(self, runtime)`
  - L145: `VisionMoveTool.execute(self, arguments)`
  - L169: `VisionMovePointTool.__init__(self, runtime)`
  - L172: `VisionMovePointTool.execute(self, arguments)`
  - L199: `VisionMoveFocusTool.__init__(self, runtime)`
  - L202: `VisionMoveFocusTool.execute(self, arguments)`
  - L223: `VisionClickTool.__init__(self, runtime)`
  - L226: `VisionClickTool.execute(self, arguments)`
  - L267: `VisionClickSequenceTool.__init__(self, runtime)`
  - L270: `VisionClickSequenceTool.execute(self, arguments)`
  - L305: `VisionKeyTool.__init__(self, runtime)`
  - L308: `VisionKeyTool.execute(self, arguments)`
  - L323: `VisionStopTool.__init__(self, runtime)`
  - L326: `VisionStopTool.execute(self, arguments)`
  - L340: `_LoggedTool.__init__(self, tool)`
  - L344: `_LoggedTool.name(self)`
  - L348: `_LoggedTool.description(self)`
  - L352: `_LoggedTool.parameters(self)`
  - L356: `_LoggedTool.parallel_safe(self)`
  - L360: `_LoggedTool.label(self)`
  - L364: `_LoggedTool.icon(self)`
  - L367: `_LoggedTool.__getattr__(self, name)`
  - L370: `_LoggedTool.execute(self, arguments)`

### A.325 `plugins/visual_operator_2/ui/eye-toggle.js`

- 类型：JavaScript
- 行数：56
- 所属主模块：`app/plugins/visual_operator_2`
- 文件角色：runtime/implementation
- addEventListener：4
- 顶层符号：
  - L7: `function paint()`
  - L13: `function cid()`
  - L17: `function button()`
  - L18: `function setState()`
  - L25: `function refresh()`
  - L33: `function bind()`
  - L51: `function init()`

### A.326 `plugins/visual_operator_2/ui/vision-frame.js`

- 类型：JavaScript
- 行数：242
- 所属主模块：`app/plugins/visual_operator_2`
- 文件角色：runtime/implementation
- addEventListener：4
- 顶层符号：
  - L8: `function currentConversationID()`
  - L14: `function frameSummary()`
  - L23: `function calibrationText()`
  - L31: `function lastCalibrationText()`
  - L50: `function modelSize()`
  - L56: `function makeThumb()`
  - L73: `function renderControlReturned()`
  - L89: `function renderFrame()`
  - L134: `function closeModal()`
  - L139: `function openModal()`
  - L207: `function bind()`

### A.327 `plugins/web_ui/plugin.py`

- 类型：Python
- 行数：16
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- 文件说明：基础 WEB-UI 插件：从 plugin-ui.json 注册页面区域。
- 导入：`__future__`, `pathlib`, `typing`, `agent.capabilities.plugin_ui_tree`
- 顶层符号：
  - L11: `def register(ctx)`

### A.328 `plugins/web_ui/ui/classic/js/chat-tool-views.js`

- 类型：JavaScript
- 行数：1304
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：5
- 顶层符号：
  - L1: `function chatToolName()`
  - L10: `function bindToolShotPreview()`
  - L30: `function isPreviewEditTool()`
  - L36: `function isEditFamilyTool()`
  - L40: `function editFamilyTitle()`
  - L47: `function chatCachedConfirmPath()`
  - L52: `function chatReviewPath()`
  - L66: `function chatEditPath()`
  - L79: `function commandSummaryLine()`
  - L82: `function chatExecSource()`
  - L87: `function chatThinkTail()`
  - L92: `function chatThinkElapsedLabel()`
  - L101: `function sealChatThinkElapsed()`
  - L110: `function chatToolArgPaths()`
  - L123: `function chatToolReplaceToken()`
  - L138: `function chatToolExpandPaths()`
  - L161: `function chatDiffCounts()`
  - L173: `function paintPreviewSummary()`
  - L193: `function chatVersionStamp()`
  - L200: `function chatVersionComparePath()`
  - L207: `function chatVersionCompareStamp()`
  - L214: `function chatVersionCompareLabel()`
  - L222: `function chatToolResultData()`
  - L230: `function chatPaintDiffPane()`
  - L248: `function chatReadFileContent()`
  - L254: `function chatImageData()`
  - L258: `function chatImagePath()`
  - L263: `function chatImageSize()`
  - L269: `function makeChatToolRow()`
  - L309: `function addChatToolLayer()`
  - L323: `function setLazyText()`
  - L330: `function materializeLazy()`
  - L334: `function materializeLazyIn()`
  - L339: `function addChatToolText()`
  - L345: `function addChatToolPane()`
  - L349: `function registerChatToolView()`
  - L353: `function uiRoot()`
  - L357: `function chatToolViewPath()`
  - L361: `function chatToolViewFor()`
  - L371: `function unregisterChatToolView()`
  - L376: `function replaceChatToolView()`
  - L385: `function restore()`
  - L403: `function chatToolHead()`
  - L408: `function chatToolSetSummary()`
  - L414: `function chatToolParsePreview()`
  - L420: `function chatToolPrettyJson()`
  - L432: `function chatToolPayloadUseful()`
  - L445: `function chatToolFailPreview()`
  - L450: `function chatToolIsFailed()`
  - L459: `function chatToolPaintFailText()`
  - L472: `function chatToolClearFailMark()`
  - L476: `function chatToolFrameOk()`
  - L482: `function chatToolEnvelopePayload()`
  - L490: `function chatToolResponseText()`
  - L520: `function goalToolSummary()`
  - L641: `function chatReadFileRangeLabel()`
  - L734: `function chatGlobSummary()`
  - L742: `function chatJoinUnder()`
  - L752: `function chatGlobLines()`
  - L821: `function chatDesktopData()`
  - L826: `function chatDesktopWantsShot()`
  - L830: `function chatDesktopFillShot()`
  - L883: `function chatDesktopShotMeta()`
  - L900: `function chatDesktopMount()`
  - L905: `function chatDesktopFill()`
  - L938: `function refreshChatToolSummaries()`
  - L967: `function chatFileCardSize()`
  - L972: `function chatFileCardKindLabel()`
  - L976: `function chatFileCardElement()`
  - L1085: `function appendChatToolRow()`
  - L1093: `function mountChatToolItem()`
  - L1116: `function registerPathRenderer()`
  - L1128: `function replacePathRenderer()`
  - L1144: `function resolvePathRenderer()`
  - L1161: `function paintChatThink()`
  - L1209: `function chatToolWasCanceled()`
  - L1216: `function chatToolSyncStatusTitle()`
  - L1224: `function chatToolSetResultText()`
  - L1229: `function chatToolSetRowStatus()`
  - L1239: `function chatToolShowsRaw()`
  - L1242: `function attachChatToolPacket()`
  - L1269: `function pane()`
  - L1286: `function fillChatToolPacket()`
  - L1290: `function fillChatToolResult()`

### A.329 `plugins/web_ui/ui/classic/js/chat/background-tasks.js`

- 类型：JavaScript
- 行数：359
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：11
- 顶层符号：
  - L14: `function byId()`
  - L18: `function currentCid()`
  - L34: `function request()`
  - L45: `function boot()`
  - L61: `function setCounts()`
  - L82: `function sortTasks()`
  - L92: `function isActive()`
  - L96: `function renderList()`
  - L143: `function renderDetail()`
  - L170: `function add()`
  - L213: `function showDetail()`
  - L234: `function applyTasks()`
  - L244: `function refreshComposerLayout()`
  - L248: `function refresh()`
  - L269: `function onConversationChanged()`
  - L279: `function setOpen()`

### A.330 `plugins/web_ui/ui/classic/js/chat/bubbles.js`

- 类型：JavaScript
- 行数：289
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：3
- 顶层符号：
  - L6: `function _systemNoticeBatch()`
  - L10: `function _sysNoticeHost()`
  - L17: `function _hideSystemNotice()`
  - L24: `function _clearSystemNoticeTimer()`
  - L27: `function _armSystemNoticeTimer()`
  - L33: `function _replaceSystemNotices()`
  - L43: `function addSystemNotice()`
  - L74: `function _toggleSystemNotice()`
  - L94: `function addGoalFollowup()`
  - L152: `function _toggleGoalFollowup()`
  - L167: `function add()`
  - L178: `function _peerAvatarLetter()`
  - L182: `function _buildPeerMetaHtml()`
  - L187: `function addPeerMessage()`
  - L211: `function togglePeerRow()`
  - L225: `function ensureAssistantStreamBubble()`
  - L242: `function scheduleStreamRender()`
  - L252: `function appendAssistantDelta()`
  - L262: `function finalizeAssistantStream()`
  - L277: `function webUiFlag()`
  - L285: `function showToolSteps()`
  - L286: `function showToolItems()`

### A.331 `plugins/web_ui/ui/classic/js/chat/compaction.js`

- 类型：JavaScript
- 行数：48
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：0
- 顶层符号：
  - L2: `function compactionSummaryText()`
  - L5: `function compactionCount()`
  - L9: `function compactionTokens()`
  - L13: `function compactionEventKey()`
  - L19: `function renderCompactionCard()`
  - L36: `function renderCompactionEvent()`
  - L45: `function renderHistoryCompactionItem()`

### A.332 `plugins/web_ui/ui/classic/js/chat/composer-layout.js`

- 类型：JavaScript
- 行数：52
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：1
- 顶层符号：
  - L5: `function byId()`
  - L9: `function syncComposerColumns()`

### A.333 `plugins/web_ui/ui/classic/js/chat/confirm.js`

- 类型：JavaScript
- 行数：185
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：2
- 顶层符号：
  - L8: `function _sendBtn()`
  - L10: `function cancelUserConfirmForNewMessage()`
  - L23: `function openUserConfirmModalFromToolEnd()`
  - L49: `function syncRows()`
  - L56: `function toggleIdx()`
  - L59: `function buildFinal()`
  - L81: `function addRow()`
  - L106: `function cleanup()`
  - L142: `function openApprovalModalFromToolEnd()`
  - L163: `function cleanup()`

### A.334 `plugins/web_ui/ui/classic/js/chat/context-usage.js`

- 类型：JavaScript
- 行数：216
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：3
- 顶层符号：
  - L12: `function _ctxIsLight()`
  - L15: `function ctxSegmentResolve()`
  - L20: `function _ctxNamedColor()`
  - L25: `function ctxSegmentColor()`
  - L50: `function bindCtxLayoutTooltip()`
  - L54: `function showTip()`
  - L64: `function formatCompactTokens()`
  - L65: `function buildUsageRing()`
  - L66: `function ctxDisplaySegments()`
  - L91: `function roundPct()`
  - L92: `function compactMarkerPct()`
  - L99: `function _updateUsageBottom()`
  - L104: `function ubCells()`
  - L105: `function ubPush()`
  - L155: `function applyUsageAccumulatorPayload()`
  - L157: `function loadUsageAccumulator()`
  - L165: `function resetUsageAccumulator()`
  - L169: `function persistUsageAccumulator()`
  - L176: `function toolDisplayOf()`
  - L187: `function loadToolLabels()`
  - L198: `function toolIco()`
  - L206: `function toolZh()`

### A.335 `plugins/web_ui/ui/classic/js/chat/conversation.js`

- 类型：JavaScript
- 行数：256
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：4
- 顶层符号：
  - L22: `function isConversationBusy()`
  - L23: `function isTabBusy()`
  - L24: `function saveRuntimeStateToTab()`
  - L25: `function loadRuntimeStateFromTab()`
  - L26: `function moveVisibleToTab()`
  - L27: `function moveTabToVisible()`
  - L28: `function saveActiveConversationView()`
  - L31: `function notifyConversationChanged()`
  - L38: `function notifyConversationTitle()`
  - L43: `function restoreConversationView()`
  - L44: `function withConversationContext()`
  - L48: `function persistConversationLayout()`
  - L49: `function repaintSessionRail()`
  - L50: `function openConversationFromMenu()`
  - L51: `function openSubagentConversation()`
  - L52: `function renderSessionMenu()`
  - L54: `function loadSessionRailList()`
  - L55: `function toggleSessionMenu()`
  - L57: `function isDefaultConversationTitle()`
  - L58: `function refreshConversationTitle()`
  - L59: `function renderHistoryItems()`
  - L95: `function renderDiffBubbleFromFacts()`
  - L98: `function renderHistoryThink()`
  - L109: `function renderHistoryToolItem()`
  - L145: `function appendHadImagesLostTip()`
  - L155: `function diffTextFromToolData()`
  - L170: `function applyContextLayoutFromHistory()`
  - L171: `function refreshConversationContextLayout()`
  - L173: `function trackMsgsBottom()`
  - L183: `function initComposerResizeSync()`
  - L205: `function observeTodoResize()`
  - L209: `function scrollToBottomAfterLayout()`
  - L210: `function loadConversationHistory()`
  - L211: `function _routeEventBySource()`
  - L214: `function restoreConversationLayoutFromServer()`
  - L223: `function syncTodoUnreadBadgeForConversation()`
  - L224: `function renderChatTabs()`
  - L225: `function switchConversationTab()`
  - L226: `function createConversationTab()`
  - L227: `function closeConversationTab()`
  - L229: `function initConversationClickDelegation()`

### A.336 `plugins/web_ui/ui/classic/js/chat/errors.js`

- 类型：JavaScript
- 行数：22
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：0
- 顶层符号：
  - L6: `function formatHttpError()`

### A.337 `plugins/web_ui/ui/classic/js/chat/history-paging.js`

- 类型：JavaScript
- 行数：133
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：2
- 顶层符号：
  - L9: `function findHistoryTabByMsgs()`
  - L16: `function updateHistoryJumpButton()`
  - L24: `function withRenderContext()`
  - L40: `function _historyStatus()`
  - L49: `function _removeHistoryStatus()`
  - L55: `function _prependHistoryNodes()`
  - L68: `function loadOlderHistory()`
  - L97: `function onHistoryScroll()`
  - L103: `function initHistoryPaging()`

### A.338 `plugins/web_ui/ui/classic/js/chat/llm-rounds.js`

- 类型：JavaScript
- 行数：427
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：1
- 顶层符号：
  - L6: `function analysisFollowupPhrase()`
  - L25: `function clearLlmAnim()`
  - L38: `function appendReasoningDelta()`
  - L41: `function applyReasoningSync()`
  - L44: `function finishLlmTitle()`
  - L52: `function addLlmRound()`
  - L90: `function onLlmRequest()`
  - L99: `function onLlmResponse()`
  - L107: `function createToolAnalysisBlock()`
  - L117: `function fillAnalysisBlockFromBuffer()`
  - L123: `function removeMergedLlmCard()`
  - L133: `function flushPendingToolTags()`
  - L143: `function abortPendingToolTags()`
  - L150: `function stopPendingToolTags()`
  - L157: `function stopOpenToolTags()`
  - L161: `function markCurrentTurnStoped()`
  - L164: `function isHostProgressToolScript()`
  - L168: `function isStreamOutputToolScript()`
  - L172: `function isRunCommandToolScript()`
  - L175: `function submitCommandInputToServer()`
  - L181: `function ensureRunCommandLivePanel()`
  - L191: `function ensureChatRunCard()`
  - L208: `function startChatRunCountdown()`
  - L212: `function _tick()`
  - L226: `function stopChatRunCountdown()`
  - L230: `function updateChatRunCardOutput()`
  - L242: `function finalizeChatRunCard()`
  - L249: `function renderRunCommandInputBar()`
  - L301: `function onToolStart()`
  - L364: `function onToolProgress()`
  - L414: `function resetTurnState()`
  - L415: `function initLlmRoundsDelegation()`

### A.339 `plugins/web_ui/ui/classic/js/chat/queue.js`

- 类型：JavaScript
- 行数：316
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：2
- 顶层符号：
  - L15: `function iconButton()`
  - L26: `function queueItemById()`
  - L33: `function bindQueueDelegation()`
  - L49: `function chatQueueCid()`
  - L55: `function chatQueueApi()`
  - L66: `function renderChatQueue()`
  - L110: `function chatQueueRow()`
  - L173: `function loadChatQueue()`
  - L200: `function queueInsert()`
  - L222: `function queueCancel()`
  - L234: `function queueRecall()`
  - L283: `function renderQueueDraft()`
  - L297: `function clearQueueDraft()`
  - L302: `function onQueueUpdated()`

### A.340 `plugins/web_ui/ui/classic/js/chat/send.js`

- 类型：JavaScript
- 行数：157
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：3
- 顶层符号：
  - L6: `function sendChatMessage()`
  - L73: `function renderAttachStrip()`
  - L87: `function initAttachStripDelegation()`
  - L102: `function clearPendingChatImages()`
  - L107: `function fileToPendingImage()`
  - L120: `function addPendingImageFiles()`
  - L131: `function initChatAttach()`

### A.341 `plugins/web_ui/ui/classic/js/chat/steps.js`

- 类型：JavaScript
- 行数：124
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：2
- 顶层符号：
  - L6: `function _muteEl()`
  - L7: `function beginChatToolOnly()`
  - L15: `function appendStep()`
  - L16: `function findStepCardForToolCall()`
  - L29: `function flushPendingSteps()`
  - L30: `function addDispatchTitle()`
  - L40: `function tokenPercent()`
  - L42: `function formatContextPct()`
  - L43: `function ensureCtxLayoutTooltip()`
  - L44: `function scheduleHideCtxLayoutTooltip()`
  - L45: `function positionCtxLayoutTooltip()`
  - L66: `function buildCtxLayoutTooltipHtml()`
  - L108: `function _segVar()`

### A.342 `plugins/web_ui/ui/classic/js/chat/stream.js`

- 类型：JavaScript
- 行数：97
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：0
- 顶层符号：
  - L6: `function escapeHtml()`
  - L7: `function _finishSseStopped()`
  - L10: `function _finishSseError()`
  - L13: `function _finishSseDone()`
  - L16: `function applySseEvent()`
  - L49: `function drainChatSseFromResponse()`
  - L78: `function handleGlobalSseEvent()`
  - L88: `function startGlobalSse()`

### A.343 `plugins/web_ui/ui/classic/js/chat/subagents.js`

- 类型：JavaScript
- 行数：213
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：8
- 顶层符号：
  - L5: `function byId()`
  - L9: `function currentCid()`
  - L24: `function request()`
  - L34: `function openChild()`
  - L48: `function boot()`
  - L61: `function setOpen()`
  - L68: `function setCounts()`
  - L76: `function render()`
  - L119: `function refresh()`

### A.344 `plugins/web_ui/ui/classic/js/chat/todo.js`

- 类型：JavaScript
- 行数：50
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：0
- 顶层符号：
  - L7: `function initTodoListElements()`
  - L12: `function showTodoList()`
  - L13: `function hideTodoList()`
  - L14: `function renderTodoListFromEvent()`

### A.345 `plugins/web_ui/ui/classic/js/chat/tool-events.js`

- 类型：JavaScript
- 行数：64
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：0
- 顶层符号：
  - L6: `function resetSteps()`
  - L8: `function onToolEnd()`

### A.346 `plugins/web_ui/ui/classic/js/code-highlight.js`

- 类型：JavaScript
- 行数：122
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：0
- 顶层符号：
  - L33: `function escapeHtml()`
  - L41: `function normalizeLang()`
  - L46: `function highlightJson()`
  - L63: `function highlightDiff()`
  - L77: `function highlightCode()`
  - L96: `function detectScriptLang()`
  - L108: `function hljsCodeClass()`

### A.347 `plugins/web_ui/ui/classic/js/composer/goal.js`

- 类型：JavaScript
- 行数：121
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：4
- 顶层符号：
  - L7: `function _goalButton()`
  - L8: `function updateAutoToggleUI()`
  - L26: `function renderGoalDialog()`
  - L30: `function el()`
  - L53: `function close()`
  - L61: `function post()`
  - L62: `function act()`
  - L70: `function addBtn()`
  - L84: `function syncSave()`

### A.348 `plugins/web_ui/ui/classic/js/composer/input.js`

- 类型：JavaScript
- 行数：147
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：6
- 顶层符号：
  - L6: `function initKbAndSlashUi()`
  - L90: `function updateSlashPopHints()`
  - L107: `function escapeHtml()`
  - L110: `function highlightJson()`
  - L114: `function highlightCode()`
  - L120: `function detectScriptLang()`
  - L124: `function hljsCodeClass()`

### A.349 `plugins/web_ui/ui/classic/js/composer/model-sync.js`

- 类型：JavaScript
- 行数：88
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：1
- 顶层符号：
  - L10: `function setAllowedModels()`
  - L23: `function loadConversationModel()`
  - L49: `function syncConversationSettings()`
  - L67: `function loadHealthModel()`
  - L73: `function refreshGlobalSettingsLimits()`
  - L79: `function onSettingsChanged()`

### A.350 `plugins/web_ui/ui/classic/js/composer/pickers.js`

- 类型：JavaScript
- 行数：118
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：6
- 顶层符号：
  - L10: `function atNormPath()`
  - L11: `function hideAtPop()`
  - L12: `function atMentionActiveAtCursor()`
  - L13: `function atLastTriggerIndexIn()`
  - L15: `function iconFor()`
  - L16: `function loadAtDir()`
  - L17: `function renderAtList()`
  - L18: `function bindAtListDelegation()`
  - L40: `function updateAtSelection()`
  - L41: `function selectAtFile()`
  - L43: `function showAtPop()`
  - L45: `function hideSlashPop()`
  - L46: `function positionSlashPop()`
  - L47: `function autoResizeTextarea()`
  - L48: `function normalizeMode()`
  - L49: `function applyMode()`
  - L52: `function closeModeMenu()`
  - L54: `function applyReasoningEffort()`
  - L63: `function closeReasoningMenu()`
  - L64: `function toggleReasoningMenu()`
  - L65: `function initReasoningPicker()`
  - L74: `function toggleModeMenu()`
  - L75: `function initModePicker()`
  - L98: `function applyModel()`
  - L112: `function notifyComposerPopup()`
  - L113: `function onComposerPopupOpen()`

### A.351 `plugins/web_ui/ui/classic/js/composer/state.js`

- 类型：JavaScript
- 行数：38
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：0
- 顶层符号：
  - L17: `function _serverRunningCid()`
  - L25: `function _clearServerRunning()`
  - L26: `function _markServerRunning()`
  - L27: `function _stopServerRunningTab()`
  - L28: `function updateTaskControls()`
  - L29: `function stopCurrentTask()`

### A.352 `plugins/web_ui/ui/classic/js/core/auth-client.js`

- 类型：JavaScript
- 行数：74
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：0
- 顶层符号：
  - L11: `function isUnsafe()`
  - L15: `function currentPath()`
  - L24: `function needLogin()`
  - L29: `function redirectLogin()`
  - L35: `function readCsrf()`

### A.353 `plugins/web_ui/ui/classic/js/core/boot.js`

- 类型：JavaScript
- 行数：52
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：0
- 顶层符号：
  - L10: `function newConversationId()`
  - L11: `function readCookieValue()`
  - L12: `function clearCookie()`
  - L13: `function normalizeConversationId()`
  - L14: `function getUrlConversationId()`
  - L15: `function getStoredConversationId()`
  - L16: `function storeConversationId()`
  - L17: `function getStoredConversationLayout()`
  - L18: `function storeConversationLayoutLocal()`
  - L22: `function getOrCreateConversationId()`
  - L23: `function createDetachedHost()`
  - L24: `function buildTodoArea()`
  - L25: `function makeConversationTab()`
  - L32: `function getActiveTab()`
  - L33: `function findConversationTab()`
  - L34: `function ensureConversationTab()`
  - L35: `function getActiveConversationId()`
  - L36: `function setActiveConversationId()`
  - L40: `function setModelContextWindow()`
  - L49: `function showChatLoading()`
  - L50: `function hideChatLoading()`
  - L51: `function closeUserConfirmCardHost()`

### A.354 `plugins/web_ui/ui/classic/js/core/ui-catalog.js`

- 类型：JavaScript
- 行数：426
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：6
- 顶层符号：
  - L6: `function entryOrder()`
  - L13: `function orderRegion()`
  - L19: `function sortByOrder()`
  - L33: `function propsOf()`
  - L38: `function bindingOf()`
  - L56: `function handle()`
  - L86: `function render()`
  - L138: `function renderExisting()`
  - L158: `function renderInput()`
  - L225: `function refreshInputs()`
  - L232: `function loadPluginStyles()`
  - L246: `function openCatalogPanel()`
  - L265: `function onScriptEvent()`
  - L274: `function bindScriptEvents()`
  - L280: `function loadScripts()`
  - L309: `function pruneCatalogScripts()`
  - L330: `function boot()`

### A.355 `plugins/web_ui/ui/classic/js/edited-files.js`

- 类型：JavaScript
- 行数：230
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：1
- 顶层符号：
  - L4: `function liveEditPieces()`
  - L8: `function push()`
  - L47: `function noteLiveEdit()`
  - L69: `function clearLiveEdits()`
  - L75: `function finishLiveEdits()`
  - L109: `function editedFileLabel()`
  - L112: `function editedFileIcon()`
  - L120: `function fillEditedStat()`
  - L146: `function paintEditedOp()`
  - L167: `function showEditedFiles()`

### A.356 `plugins/web_ui/ui/classic/js/file-icons.js`

- 类型：JavaScript
- 行数：104
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：0
- 顶层符号：
  - L24: `function baseName()`
  - L29: `function fileIconKind()`
  - L85: `function makeFileIconEl()`
  - L98: `function fileIconHtml()`

### A.357 `plugins/web_ui/ui/classic/js/image-lightbox.js`

- 类型：JavaScript
- 行数：338
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：4
- 顶层符号：
  - L5: `function attachmentUrl()`
  - L15: `function ensureLightbox()`
  - L41: `function close()`
  - L74: `function onKeydown()`
  - L77: `function onResize()`
  - L90: `function syncModeButtons()`
  - L97: `function applyLightboxSize()`
  - L147: `function centerLightboxStage()`
  - L154: `function openImageLightbox()`
  - L179: `function bindThumbClick()`
  - L197: `function buildMsgAttachStrip()`
  - L228: `function appendHadImagesLostTip()`
  - L236: `function measureImageFile()`
  - L258: `function preferLargestImageFiles()`
  - L269: `function filesFromPasteEvent()`
  - L287: `function readClipboardImagesAsync()`
  - L321: `function collectPasteImageFiles()`

### A.358 `plugins/web_ui/ui/classic/js/layout/init.js`

- 类型：JavaScript
- 行数：71
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：8
- 顶层符号：无

### A.359 `plugins/web_ui/ui/classic/js/layout/splitters.js`

- 类型：JavaScript
- 行数：108
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：8
- 顶层符号：
  - L1: `function initClassicMainSplit()`
  - L22: `function mainInnerWidth()`
  - L23: `function railOpen()`
  - L26: `function railTake()`
  - L30: `function maxStepsPx()`
  - L31: `function defaultStepsPx()`
  - L32: `function clampSteps()`
  - L33: `function loadStepsPx()`
  - L34: `function saveStepsPx()`
  - L37: `function sideEmpty()`
  - L38: `function applyLayout()`
  - L39: `function setClassicSideOpen()`
  - L42: `function railRoom()`
  - L43: `function clampRail()`
  - L44: `function loadRailPx()`
  - L45: `function saveRailPx()`
  - L46: `function loadRailOpen()`
  - L47: `function saveRailOpen()`
  - L50: `function applyRail()`
  - L53: `function armRailSlide()`
  - L54: `function railToggleSlot()`
  - L55: `function placeRailToggle()`
  - L58: `function setRailToggleSlot()`
  - L59: `function setSessionRailOpen()`
  - L71: `function onRailMove()`
  - L72: `function onRailUp()`
  - L82: `function onMove()`
  - L86: `function onUp()`

### A.360 `plugins/web_ui/ui/classic/js/panels/file-viewer.js`

- 类型：JavaScript
- 行数：114
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：5
- 顶层符号：
  - L10: `function formatFileSize()`
  - L20: `function renderTableSheets()`
  - L38: `function renderFilePane()`
  - L78: `function openFileTab()`
  - L96: `function openFilePicker()`
  - L106: `function close()`
  - L107: `function submit()`

### A.361 `plugins/web_ui/ui/classic/js/panels/panes.js`

- 类型：JavaScript
- 行数：157
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：2
- 顶层符号：
  - L6: `function selectSidePane()`
  - L16: `function bindSideTabDelegation()`
  - L29: `function openPane()`
  - L93: `function countOpenSideTabs()`
  - L102: `function syncClassicSide()`
  - L105: `function closePane()`
  - L135: `function syncSideTabbarGap()`
  - L143: `function bindSideTabbarGap()`

### A.362 `plugins/web_ui/ui/classic/js/plugins/host.js`

- 类型：JavaScript
- 行数：255
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：0
- 顶层符号：
  - L6: `function pluginApi()`
  - L8: `function call()`
  - L46: `function notifyModelSubscribers()`
  - L52: `function pluginAssetUrl()`
  - L132: `function loadPluginScript()`
  - L151: `function loadPluginStyle()`
  - L168: `function rememberLoadedPlugins()`
  - L178: `function loadLoadedPlugins()`
  - L185: `function panePluginName()`
  - L192: `function closeUnloadedPluginPanes()`
  - L204: `function prunePluginStyles()`
  - L221: `function prunePluginScripts()`
  - L236: `function prunePluginMounts()`
  - L245: `function applyPluginsChanged()`

### A.363 `plugins/web_ui/ui/classic/js/render/diff.js`

- 类型：JavaScript
- 行数：89
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：1
- 顶层符号：
  - L6: `function linesDiff()`
  - L18: `function renderDiffRows()`
  - L28: `function unifiedDiffRowClass()`
  - L36: `function renderUnifiedDiffRows()`
  - L65: `function scrollToBottom()`
  - L80: `function isNearBottom()`
  - L84: `function scrollMsgsToBottom()`
  - L85: `function scrollMsgsToBottomAfterLayout()`
  - L86: `function calcDiffStats()`
  - L87: `function diffLabel()`
  - L88: `function diffLabelPlain()`

### A.364 `plugins/web_ui/ui/classic/js/render/markdown.js`

- 类型：JavaScript
- 行数：345
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：0
- 顶层符号：
  - L7: `function mdParser()`
  - L17: `function initMarkedExtensions()`
  - L21: `function markedRenderer()`
  - L52: `function renderMarkdownBlocks()`
  - L60: `function isUnifiedDiffLine()`
  - L67: `function shouldStartUnifiedDiffBlock()`
  - L73: `function collectUnifiedDiffBlock()`
  - L83: `function looksLikeUnifiedDiffBlock()`
  - L93: `function renderUnifiedDiffBlockHtml()`
  - L99: `function isDevNullPath()`
  - L104: `function parseDiffHeaderPath()`
  - L109: `function diffFileNameFromBody()`
  - L121: `function findDiffFenceCloseIndex()`
  - L146: `function splitUnifiedDiffSections()`
  - L161: `function renderUnifiedDiffBodyAsCardsHtml()`
  - L210: `function iterMarkdownCodeFences()`
  - L270: `function parseUnifiedDiffBodyForRows()`
  - L284: `function diffRowInnerHtml()`
  - L289: `function buildDiffRowsHtml()`
  - L299: `function buildChatDiffCardHtml()`
  - L309: `function renderSimpleDiffCard()`
  - L324: `function renderMarkdown()`

### A.365 `plugins/web_ui/ui/classic/js/render/paths.js`

- 类型：JavaScript
- 行数：230
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：0
- 顶层符号：
  - L6: `function localAbsPath()`
  - L11: `function workspaceRelPath()`
  - L17: `function markedImageHref()`
  - L25: `function markedIsVideo()`
  - L32: `function markedIsMediaFile()`
  - L39: `function filePathFromHref()`
  - L47: `function filePaneId()`
  - L54: `function shortFilePath()`
  - L66: `function absoluteFilePathOf()`
  - L71: `function fileRefHtml()`
  - L81: `function linkifyUserText()`
  - L88: `function atFileExtension()`
  - L116: `function filePathCodespanExtension()`
  - L149: `function _safeUrlValue()`
  - L159: `function _cleanTagAttrs()`
  - L186: `function sanitizeRenderedHtml()`

### A.366 `plugins/web_ui/ui/classic/js/settings-ui.js`

- 类型：JavaScript
- 行数：1144
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：24
- 顶层符号：
  - L7: `function bootSettingsPanel()`
  - L13: `function request()`
  - L30: `function mask()`
  - L70: `function setStatus()`
  - L78: `function showApply()`
  - L83: `function setBusy()`
  - L91: `function syncFoot()`
  - L103: `function closeSettings()`
  - L110: `function onKey()`
  - L114: `function openSettings()`
  - L144: `function adoptSections()`
  - L181: `function refreshHostSections()`
  - L212: `function directCards()`
  - L218: `function renderNav()`
  - L257: `function navButton()`
  - L269: `function currentSection()`
  - L276: `function renderHost()`
  - L292: `function fieldRow()`
  - L315: `function fieldControl()`
  - L359: `function clientControl()`
  - L365: `function remember()`
  - L403: `function pluginControl()`
  - L409: `function remember()`
  - L449: `function persistClientValues()`
  - L471: `function secretPlaceholder()`
  - L475: `function boolControl()`
  - L490: `function enumControl()`
  - L508: `function dirControl()`
  - L532: `function pickDir()`
  - L552: `function onSave()`
  - L558: `function saveHost()`
  - L604: `function clearSavedSecrets()`
  - L618: `function applyWebUi()`
  - L632: `function refreshWebUiFlags()`
  - L648: `function renderPlugins()`
  - L679: `function pluginCard()`
  - L726: `function pluginSwitch()`
  - L758: `function openPlugin()`
  - L791: `function renderPluginEditor()`
  - L810: `function editorBar()`
  - L840: `function textEditor()`
  - L854: `function fieldsEditor()`
  - L867: `function structuredEditor()`
  - L889: `function drawModels()`
  - L903: `function modelCard()`
  - L938: `function structuredRow()`
  - L962: `function structuredControl()`
  - L1017: `function groupValue()`
  - L1024: `function fieldVisible()`
  - L1032: `function schemaDefault()`
  - L1042: `function syncCardVisibility()`
  - L1051: `function findField()`
  - L1059: `function validateStructuredEditor()`
  - L1091: `function savePluginFile()`

### A.367 `plugins/web_ui/ui/classic/js/shell/window-chrome.js`

- 类型：JavaScript
- 行数：221
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：10
- 顶层符号：
  - L3: `function init()`
  - L21: `function toggleMaximize()`
  - L42: `function edgeAt()`
  - L55: `function setEdgeCursor()`
  - L141: `function pumpMove()`
  - L202: `function boot()`

### A.368 `plugins/web_ui/ui/classic/js/theme-ui.js`

- 类型：JavaScript
- 行数：93
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：2
- 顶层符号：
  - L5: `function get()`
  - L12: `function set()`
  - L20: `function toggle()`
  - L23: `function apply()`
  - L27: `function syncButtons()`
  - L46: `function nodeEl()`
  - L51: `function isEditableNode()`

### A.369 `plugins/web_ui/ui/classic/js/tools/previews.js`

- 类型：JavaScript
- 行数：107
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：0
- 顶层符号：
  - L6: `function fillToolPreview()`

### A.370 `plugins/web_ui/ui/classic/js/tools/titles.js`

- 类型：JavaScript
- 行数：482
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：0
- 顶层符号：
  - L6: `function argGet()`
  - L12: `function baseNameOnly()`
  - L17: `function pathLeaf()`
  - L26: `function buildToolTitleParts()`
  - L27: `function take()`
  - L32: `function takeDots()`
  - L309: `function desktopToolKind()`
  - L317: `function desktopPointText()`
  - L321: `function desktopRegionText()`
  - L325: `function desktopClipText()`
  - L329: `function desktopDurationText()`
  - L342: `function _desktopData()`
  - L345: `function desktopTargetTitle()`
  - L352: `function desktopToolTitle()`
  - L357: `function cut()`
  - L404: `function desktopToolSummary()`
  - L408: `function desktopSetStepSummary()`
  - L419: `function desktopUpdateStepSummary()`
  - L429: `function desktopWaitSeconds()`
  - L438: `function desktopWaitTickText()`
  - L447: `function desktopStopWaitTicker()`
  - L454: `function desktopStartWaitTicker()`
  - L459: `function paint()`

### A.371 `plugins/web_ui/ui/classic/js/vendor/highlight.min.js`

- 类型：JavaScript
- 行数：1244
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- 导入：`,`, `,`, `].map((e=>e+`, `,`, `,`, `,`, `,`, `,relevance:2
},e.C_LINE_COMMENT_MODE,e.C_BLOCK_COMMENT_MODE,{begin:/`, `,`, `,`, `,`, `,`, `,end:/$/,
contains:[...a],relevance:0},A,...c,...g,...p,f,k,...C,...T,R,I]}},
grmr_typescript:e=>{
const n=e.regex,t=ve(e`, `,`
- addEventListener：1
- 顶层符号：
  - L6: `function e()`
  - L12: `class n`
  - L14: `function t()`
  - L16: `function a()`
  - L18: `class r`
  - L27: `class o`
  - L38: `class l`
  - L43: `function c()`
  - L44: `function d()`
  - L45: `function g()`
  - L46: `function b()`
  - L50: `function p()`
  - L52: `function h()`
  - L84: `function T()`
  - L85: `function R()`
  - L86: `function D()`
  - L89: `function I()`
  - L90: `function L()`
  - L93: `function B()`
  - L101: `function z()`
  - L103: `function i()`
  - L105: `function j()`
  - L109: `function G()`
  - L111: `function Z()`
  - L124: `function W()`
  - L125: `function n()`
  - L127: `class t`
  - L136: `class i`
  - L152: `function t()`
  - L171: `function Q()`
  - L172: `class X`
  - L180: `function _()`
  - L181: `function h()`
  - L187: `function f()`
  - L188: `function c()`
  - L196: `function d()`
  - L202: `function g()`
  - L203: `function u()`
  - L206: `function b()`
  - L210: `function m()`
  - L214: `function _()`
  - L215: `function h()`
  - L223: `function w()`
  - L251: `function E()`
  - L258: `function y()`
  - L276: `function v()`
  - L279: `function N()`
  - L280: `function k()`
  - L281: `function x()`
  - L282: `function O()`
  - L325: `function be()`
  - L327: `function ve()`
  - L460: `class struct`
  - L461: `class struct`
  - L535: `class interface`
  - L651: `class object`
  - L679: `class interface`
  - L792: `class close`
  - L878: `class interface`
  - L938: `class Conj`
  - L1060: `function o()`
  - L1162: `class compare`

### A.372 `plugins/web_ui/ui/classic/js/vendor/marked.min.js`

- 类型：JavaScript
- 行数：81
- 所属主模块：`app/shell/web-ui`
- 文件角色：runtime/implementation
- addEventListener：0
- 顶层符号：
  - L13: `function M()`
  - L14: `function P()`
  - L16: `function v()`
  - L18: `function $e()`
  - L44: `class a`
  - L76: `function I()`
  - L77: `function g()`

### A.373 `scripts/acceptance_batch_a.py`

- 类型：Python
- 行数：282
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：验收：写路径 6 件（replace_in_file / apply_patch / read_write / delete_file / file_ops / file_undo）headless 演示。
- 导入：`__future__`, `sys`, `tempfile`, `pathlib`, `agent.app`, `agent.core.tool_call`
- 顶层符号：
  - L22: `def _patch(old, new)`
  - L37: `class Acceptance()`
  - L275: `def main()`
- 类成员：
  - L40: `Acceptance.__init__(self, root)`
  - L51: `Acceptance.call(self, name, arguments)`
  - L57: `Acceptance.ready(self, name, arguments)`
  - L65: `Acceptance.commit(self, confirm_id)`
  - L68: `Acceptance.check(self, label, cond, detail)`
  - L79: `Acceptance.scenario_1(self)`
  - L149: `Acceptance.scenario_2(self)`
  - L206: `Acceptance.scenario_3(self)`
  - L260: `Acceptance.run(self)`

### A.374 `scripts/acceptance_batch_b.py`

- 类型：Python
- 行数：142
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：验收：命令执行两件（run_command / python_inline）headless 演示。
- 导入：`__future__`, `os`, `sys`, `tempfile`, `pathlib`, `agent.app`, `agent.core.tool_call`, `agent.mechanisms`
- 顶层符号：
  - L25: `def _norm(path_text)`
  - L30: `class Acceptance()`
  - L135: `def main()`
- 类成员：
  - L33: `Acceptance.__init__(self, root)`
  - L39: `Acceptance.call(self, name, arguments)`
  - L45: `Acceptance.check(self, label, cond, detail)`
  - L56: `Acceptance.scenario_1(self)`
  - L77: `Acceptance.scenario_2(self)`
  - L104: `Acceptance.scenario_3(self)`
  - L120: `Acceptance.run(self)`

### A.375 `scripts/acceptance_batch_c.py`

- 类型：Python
- 行数：194
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：验收：任务与目标四工具（run_type / todo_list / user_confirm / goal）headless 演示。
- 导入：`__future__`, `sys`, `tempfile`, `pathlib`, `agent.app`, `agent.core.tool_call`, `agent.mechanisms.live_state`
- 顶层符号：
  - L26: `class Acceptance()`
  - L187: `def main()`
- 类成员：
  - L29: `Acceptance.__init__(self, root)`
  - L41: `Acceptance.gate(self)`
  - L47: `Acceptance.call(self, name, arguments, cid)`
  - L53: `Acceptance.ready(self, name, arguments)`
  - L61: `Acceptance.commit(self, confirm_id)`
  - L64: `Acceptance.check(self, label, cond, detail)`
  - L75: `Acceptance.scenario_1(self)`
  - L117: `Acceptance.scenario_2(self)`
  - L146: `Acceptance.scenario_3(self)`
  - L172: `Acceptance.run(self)`

### A.376 `scripts/acceptance_batch_d.py`

- 类型：Python
- 行数：210
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：验收：会话协作五工具（session_send / session_multisend / session_broadcast / session_create / session_list）headless 演示。
- 导入：`__future__`, `sys`, `tempfile`, `threading`, `time`, `pathlib`, `agent.app`, `agent.core.model_call`, `agent.core.tool_call`, `agent.mechanisms.mesh`
- 顶层符号：
  - L28: `class _GatedProbe()`
  - L47: `class Acceptance()`
  - L199: `def main()`
- 类成员：
  - L31: `_GatedProbe.__init__(self)`
  - L37: `_GatedProbe.stream(self, request)`
  - L50: `Acceptance.__init__(self, root)`
  - L68: `Acceptance.call(self, name, arguments, cid)`
  - L74: `Acceptance.check(self, label, cond, detail)`
  - L83: `Acceptance.wait_until(self, cond, timeout, interval)`
  - L94: `Acceptance.scenario_1(self)`
  - L122: `Acceptance.scenario_2(self)`
  - L161: `Acceptance.scenario_3(self)`
  - L184: `Acceptance.run(self)`

### A.377 `scripts/acceptance_batch_e.py`

- 类型：Python
- 行数：336
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：验收：调查与工具 12 件（find_in_file / regex_locate / file_search / text_diff /
- 导入：`__future__`, `http.server`, `importlib.util`, `json`, `shutil`, `subprocess`, `sys`, `tempfile`, `threading`, `pathlib`, `agent.app`, `agent.core.tool_call`, `agent.mechanisms.live_state`, `agent.mechanisms.mesh`
- 顶层符号：
  - L51: `def _available(module)`
  - L55: `class _HtmlHandler(http.server.BaseHTTPRequestHandler)`
  - L71: `class Acceptance()`
  - L314: `def main()`
- 类成员：
  - L56: `_HtmlHandler.do_GET(self)`
  - L67: `_HtmlHandler.log_message(self)`
  - L74: `Acceptance.__init__(self, root)`
  - L87: `Acceptance.start_server(self)`
  - L92: `Acceptance.stop_server(self)`
  - L96: `Acceptance.call(self, name, arguments, cid)`
  - L103: `Acceptance.gate(self)`
  - L107: `Acceptance.check(self, label, cond, detail)`
  - L118: `Acceptance._scenario1_preview(self, src, zip_path)`
  - L126: `Acceptance._scenario1_commit(self, cid, zip_path)`
  - L157: `Acceptance._scenario1_extract(self, zip_path)`
  - L178: `Acceptance.scenario_1(self)`
  - L189: `Acceptance._scenario2_text(self, note)`
  - L205: `Acceptance._scenario2_data(self, csv)`
  - L215: `Acceptance._scenario2_diagnose(self)`
  - L232: `Acceptance._scenario2_git(self)`
  - L254: `Acceptance._scenario2_web(self)`
  - L270: `Acceptance._scenario2_ocr(self)`
  - L281: `Acceptance.scenario_2(self)`
  - L294: `Acceptance.scenario_3(self)`

### A.378 `scripts/acceptance_batch_f.py`

- 类型：Python
- 行数：160
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：验收：集成与外围 4 件（ip_geolocate / open_meteo_weather / review_conclusion /
- 导入：`__future__`, `json`, `os`, `sys`, `tempfile`, `pathlib`, `unittest`, `agent.app`, `agent.capabilities.builtin`, `agent.core.tool_call`, `agent.mechanisms.live_state`, `agent.mechanisms.mesh`
- 顶层符号：
  - L34: `class Acceptance()`
  - L136: `def main()`
- 类成员：
  - L37: `Acceptance.__init__(self, root)`
  - L54: `Acceptance.call(self, name, arguments, cid)`
  - L61: `Acceptance.gate(self)`
  - L65: `Acceptance.check(self, label, cond, detail)`
  - L76: `Acceptance.scenario_1(self)`
  - L116: `Acceptance.scenario_2(self)`

### A.379 `scripts/acceptance_mvp2.py`

- 类型：Python
- 行数：158
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：验收：质量门控闭环 headless 演示（三场景 / id 制）。
- 导入：`__future__`, `sys`, `tempfile`, `pathlib`, `agent.app`, `agent.core.tool_call`
- 顶层符号：
  - L23: `class Acceptance()`
  - L151: `def main()`
- 类成员：
  - L26: `Acceptance.__init__(self, root)`
  - L35: `Acceptance.call(self, name, arguments)`
  - L41: `Acceptance.preview(self, path, content)`
  - L44: `Acceptance.commit(self, confirm_id)`
  - L47: `Acceptance.ready(self, path, content)`
  - L55: `Acceptance.norm(self, path)`
  - L58: `Acceptance.check(self, label, cond, detail)`
  - L69: `Acceptance.scenario_1(self)`
  - L87: `Acceptance.scenario_2(self)`
  - L120: `Acceptance.scenario_3(self)`
  - L136: `Acceptance.run(self)`

### A.380 `scripts/acceptance_mvp3.py`

- 类型：Python
- 行数：197
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：验收：真实模型端到端（headless）。
- 导入：`__future__`, `os`, `sys`, `tempfile`, `pathlib`, `typing`, `uuid`, `agent.app`, `agent.core`, `agent.mechanisms.session_store`
- 顶层符号：
  - L49: `def _short(text, limit)`
  - L54: `def _is_target(path)`
  - L58: `def _record_started(data, seq, previews, session_gate)`
  - L77: `def _record_done(data, results, previews, session_gate, confirms, rejects)`
  - L95: `def _run_events(engine, session_gate, text)`
  - L129: `def _check_results(target, store, cid, engine, seq, results, ended, errors)`
  - L160: `def main()`

### A.381 `scripts/acceptance_phase3.py`

- 类型：Python
- 行数：184
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：插件回归验收：插件开 / 关两态均可运行。
- 导入：`__future__`, `sys`, `tempfile`, `pathlib`, `unittest`, `agent.app`, `agent.mechanisms.live_state`, `agent.mechanisms.mesh`
- 顶层符号：
  - L34: `class Acceptance()`
  - L171: `def main()`
- 类成员：
  - L37: `Acceptance.__init__(self, root)`
  - L41: `Acceptance.check(self, label, cond, detail)`
  - L50: `Acceptance.build(self, enabled)`
  - L71: `Acceptance.smoke(self, app, cid)`
  - L76: `Acceptance.subs_total(self, app)`
  - L79: `Acceptance.sources_total(self, app)`
  - L84: `Acceptance.scenario_a(self)`
  - L133: `Acceptance.scenario_b(self)`
  - L145: `Acceptance.scenario_c(self)`

### A.382 `scripts/acceptance_web.py`

- 类型：Python
- 行数：801
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：Web 壳验收：端到端（真实 HTTP 服务 + 真实 SSE 流）。
- 导入：`__future__`, `json`, `sys`, `tempfile`, `threading`, `time`, `urllib.error`, `urllib.parse`, `urllib.request`, `pathlib`, `typing`, `agent.app`, `agent.config`, `agent.core.model_call`, `agent.core.tool_call`, `agent.mechanisms.live_state`, `agent.mechanisms.mesh`, `agent.mechanisms.session_store`, `agent.shell.web.auth`, `agent.shell.web.server`
- 顶层符号：
  - L88: `class ScriptedProvider()`
  - L176: `class EchoProvider()`
  - L180: `class Acceptance()`
  - L774: `def main()`
- 类成员：
  - L94: `ScriptedProvider.__init__(self, target)`
  - L102: `ScriptedProvider._confirm_from(request)`
  - L119: `ScriptedProvider.stream(self, request)`
  - L177: `EchoProvider.stream(self, request)`
  - L183: `Acceptance.__init__(self, root)`
  - L214: `Acceptance._manifest(root)`
  - L230: `Acceptance.check(self, label, cond, detail)`
  - L241: `Acceptance.start(self)`
  - L248: `Acceptance.close(self)`
  - L260: `Acceptance._read_sse(self)`
  - L285: `Acceptance.get(self, path, timeout)`
  - L292: `Acceptance.get_json(self, path)`
  - L300: `Acceptance.post(self, path, payload)`
  - L303: `Acceptance.put_json(self, path, payload)`
  - L307: `Acceptance._send(self, method, path, payload)`
  - L325: `Acceptance.wait_turn(self, cid)`
  - L329: `Acceptance.confirm_id_of(self, cid)`
  - L347: `Acceptance.scenario_1(self)`
  - L389: `Acceptance.scenario_2(self)`
  - L464: `Acceptance.scenario_3(self)`
  - L523: `Acceptance.scenario_4(self)`
  - L552: `Acceptance._scenario5_page(self, pw)`
  - L567: `Acceptance._scenario5_vectors(self, page)`
  - L600: `Acceptance._scenario5_execution(self, page)`
  - L618: `Acceptance._scenario5_normal(self, page)`
  - L625: `Acceptance.scenario_5(self)`
  - L645: `Acceptance._wait_visible(self, page, selector, label, timeout)`
  - L656: `Acceptance.scenario_6(self)`
  - L682: `Acceptance._panel_real_plugins(self, browser)`
  - L713: `Acceptance._panel_structured(self, browser)`
  - L765: `Acceptance.scenario_7(self)`

### A.383 `scripts/acceptance_web_player.py`

- 类型：Python
- 行数：62
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：AI角色扮演播放器的浏览器验收：注入、插件事件送达、关闭后撤销。
- 导入：`__future__`, `sys`, `typing`
- 顶层符号：
  - L12: `def run(acc)`

### A.384 `scripts/acceptance_web_todo.py`

- 类型：Python
- 行数：58
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：Web 验收：Todo 清单 close 的浏览器 DOM 回归。
- 导入：`__future__`, `sys`
- 顶层符号：
  - L8: `def run(acc)`

### A.385 `scripts/artifact_lock.py`

- 类型：Python
- 行数：253
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：跨进程产物锁：同一份共享产物同时只允许一个进程写。
- 导入：`__future__`, `json`, `os`, `shutil`, `time`, `uuid`, `dataclasses`, `pathlib`, `typing`
- 顶层符号：
  - L39: `class Holder()`
  - L55: `class LockBusy(RuntimeError)`
  - L66: `def parse_holder(text)`
  - L91: `def pid_alive(pid)`
  - L108: `def _windows_pid_alive(pid)`
  - L138: `class ArtifactLock()`
  - L247: `def _age_of(path)`
- 类成员：
  - L47: `Holder.age_s(self)`
  - L50: `Holder.describe(self)`
  - L58: `LockBusy.__init__(self, name, holder, waited_s)`
  - L141: `ArtifactLock.__init__(self, root, name, purpose, lock_root)`
  - L151: `ArtifactLock.held(self)`
  - L155: `ArtifactLock.holder(self)`
  - L158: `ArtifactLock.acquire(self, wait_s, poll_s, force)`
  - L176: `ArtifactLock.release(self)`
  - L186: `ArtifactLock.__enter__(self)`
  - L190: `ArtifactLock.__exit__(self)`
  - L193: `ArtifactLock._try_create(self)`
  - L216: `ArtifactLock._read(self)`
  - L227: `ArtifactLock._reclaimable(self, holder)`
  - L232: `ArtifactLock._reclaim(self, expected)`

### A.386 `scripts/build_full_pack.py`

- 类型：Python
- 行数：53
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：构建完整包：全部项目文件，排除非项目资源。
- 导入：`__future__`, `argparse`, `sys`, `zipfile`, `pathlib`, `scripts.pack_common`
- 顶层符号：
  - L16: `def build(version, output)`
  - L42: `def main()`

### A.387 `scripts/build_release.py`

- 类型：Python
- 行数：69
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：构建软件更新包：全部项目文件 + manifest。
- 导入：`__future__`, `argparse`, `hashlib`, `json`, `sys`, `zipfile`, `pathlib`, `scripts.pack_common`
- 顶层符号：
  - L18: `def _digest(path)`
  - L26: `def build(version, output)`
  - L56: `def main()`

### A.388 `scripts/check_acceptance_skips.py`

- 类型：Python
- 行数：60
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：汇总验收 skip 名单；非白名单或超上限则失败。
- 导入：`__future__`, `os`, `sys`, `pathlib`, `ci_steps`
- 顶层符号：
  - L31: `def main()`

### A.389 `scripts/check_applicability.py`

- 类型：Python
- 行数：127
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：`docs/applicability.md` 校验：申报结构 + 与准则编号集合的双向比对。
- 导入：`__future__`, `re`, `sys`, `pathlib`, `typing`, `standards_rules`
- 顶层符号：
  - L41: `def _cells(line)`
  - L45: `def _rows(text)`
  - L63: `def check(text, known_ids)`
  - L95: `def _rel(path)`
  - L102: `def run(docs)`
  - L121: `def main()`

### A.390 `scripts/check_architecture_hygiene.py`

- 类型：Python
- 行数：496
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：架构约束检查：跨层私有导入、内核插件名、壳层 skill_manage 硬编码。
- 导入：`__future__`, `ast`, `re`, `pathlib`, `quality_budgets`
- 顶层符号：
  - L25: `def _layer_of(path, root)`
  - L33: `def _plugin_dir_names(plugins_dir)`
  - L42: `def _word_hits(text, name)`
  - L46: `def check_cross_layer_private_imports(package_root)`
  - L95: `def check_same_layer_private_imports(package_root)`
  - L125: `def check_test_method_names(tests_dir)`
  - L144: `def check_kernel_plugin_names(package_root, plugins_dir)`
  - L166: `def check_shell_js_skill_manage(js_root)`
  - L179: `def check_shell_prompts_skill_manage(prompts)`
  - L209: `def _rel_to_root(path)`
  - L216: `def _iter_assign_target_ids(target)`
  - L229: `def _gate_bypass_hits(tree)`
  - L260: `def check_gate_single_path(package_root)`
  - L282: `def check_prompts_preview_from_registry(prompts)`
  - L296: `def _assigns_empty_system_text(node)`
  - L310: `def check_no_silent_system_prompt(package_root)`
  - L337: `def _quality_gate_import_hits(tree)`
  - L362: `def check_provider_module_boundary(package_root)`
  - L390: `def check_compactor_contract_boundary(package_root)`
  - L419: `def check_no_quality_gate_shim(package_root, plugins_dir, tests_dir)`
  - L450: `def check(package_root, plugins_dir, js_root, prompts, tests_dir)`
  - L479: `def main()`

### A.391 `scripts/check_catalog.py`

- 类型：Python
- 行数：74
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：catalog 校验：对比注册文件 catalog/tools.json 与装配集实况（漂移即红灯）。
- 导入：`__future__`, `json`, `sys`, `pathlib`, `gen_catalog`
- 顶层符号：
  - L21: `def diff_tools(actual, expected)`
  - L42: `def check(catalog_path)`
  - L61: `def main()`

### A.392 `scripts/check_ci_workflow.py`

- 类型：Python
- 行数：82
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：校验 GitHub workflow 与 `scripts/ci_steps.py` 逐字节一致。
- 导入：`__future__`, `sys`, `pathlib`, `ci_steps`
- 顶层符号：
  - L30: `def _display(path)`
  - L38: `def check()`
  - L68: `def main()`

### A.393 `scripts/check_comment_style.py`

- 类型：Python
- 行数：343
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：注释文案检查：注释只解释代码，不留"工程过程"文案与对读者的叮嘱。
- 导入：`__future__`, `ast`, `io`, `re`, `sys`, `tokenize`, `pathlib`
- 顶层符号：
  - L187: `def _docstring_spans(tree)`
  - L209: `def scan_text(text, suffix, patterns)`
  - L263: `def _scan(path, patterns)`
  - L273: `def main()`

### A.394 `scripts/check_complexity.py`

- 类型：Python
- 行数：114
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：复杂度门禁：实际超阈值集合 ↔ 阈值常量 ↔ 生成文档。
- 导入：`__future__`, `sys`, `pathlib`, `complexity_scan`, `quality_budgets`
- 顶层符号：
  - L45: `def _render(root)`
  - L51: `def _normalized(text)`
  - L55: `def check(root, docs, max_file_lines, max_function_lines, max_file_functions)`
  - L80: `def _print_list()`
  - L95: `def main(argv)`

### A.395 `scripts/check_config_drift.py`

- 类型：Python
- 行数：168
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：配置漂移门禁：真实配置只允许使用 schema 已登记的节与键。
- 导入：`__future__`, `configparser`, `sys`, `pathlib`, `typing`, `agent.config_schema`
- 顶层符号：
  - L35: `def parse_ini(text, name)`
  - L41: `def _line_of_key(text, section, key)`
  - L54: `def compare_subset(text, name, schema)`
  - L73: `def compare_model_example(text, name, schema)`
  - L98: `def compare_plugin_model_real(text, name, schema)`
  - L123: `def check_files(real, web_real, model_plugin_real)`
  - L153: `def main()`

### A.396 `scripts/check_confirm_wording.py`

- 类型：Python
- 行数：191
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：「确认」歧义自检：写盘链路涉及 confirm_id / 确认 的文案必须无歧义。
- 导入：`__future__`, `ast`, `sys`, `pathlib`
- 顶层符号：
  - L70: `def _read(p)`
  - L77: `def _confirm_block(gate)`
  - L100: `def check_texts(texts)`
  - L166: `def check()`
  - L173: `def main()`

### A.397 `scripts/check_coverage.py`

- 类型：Python
- 行数：182
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：分包覆盖率下限校验。
- 导入：`__future__`, `sys`, `pathlib`, `typing`, `artifact_lock`, `quality_budgets`
- 顶层符号：
  - L57: `def _group_of(filename)`
  - L67: `def measure(data_file)`
  - L87: `def percent(statements, missing)`
  - L93: `def check(measured, floors)`
  - L112: `def stamp(data_file)`
  - L122: `def report(measured)`
  - L133: `def main()`
  - L147: `def _check_locked(data_file)`

### A.398 `scripts/check_imports.py`

- 类型：Python
- 行数：285
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：依赖方向检查：shell → capabilities → mechanisms → core 单向。
- 导入：`__future__`, `ast`, `sys`, `pathlib`
- 顶层符号：
  - L44: `def _layer_of(path, root)`
  - L52: `def _iter_imports(tree)`
  - L62: `def check(package_root)`
  - L107: `def _from_base(node, module, is_pkg)`
  - L122: `def _module_of(path, package_root)`
  - L133: `def _imported_modules(node, path, package_root)`
  - L142: `def _is_type_checking(test)`
  - L151: `def _iter_imports_without_typing_guard(tree)`
  - L164: `def _module_table(package_root)`
  - L180: `def _import_targets(node, module, is_pkg, known)`
  - L206: `def _graph(package_root)`
  - L224: `def cycles(package_root)`
  - L263: `def main()`

### A.399 `scripts/check_python_floor.py`

- 类型：Python
- 行数：106
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：Python 版本下限检查 —— 守住"写法下限 3.10"。
- 导入：`__future__`, `ast`, `sys`, `pathlib`
- 顶层符号：
  - L58: `def _violations(tree)`
  - L71: `def main()`

### A.400 `scripts/check_readme.py`

- 类型：Python
- 行数：210
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：核对 README 里的事实性数字（防漂移）。
- 导入：`__future__`, `ast`, `re`, `sys`, `pathlib`, `ci_steps`
- 顶层符号：
  - L33: `def _ci_acceptance_scripts()`
  - L38: `def _test_method_count()`
  - L47: `def _path_segments(node)`
  - L56: `def _data_dirs()`
  - L115: `def _public_docs()`
  - L130: `def check(readme, acceptance, tests, data_dirs, steps, gates)`
  - L186: `def main()`

### A.401 `scripts/check_secrets.py`

- 类型：Python
- 行数：85
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：扫描版本库中的高置信度秘密模式。
- 导入：`__future__`, `re`, `subprocess`, `pathlib`, `typing`
- 顶层符号：
  - L33: `def scan_text(text)`
  - L45: `def tracked_files()`
  - L59: `def main()`

### A.402 `scripts/check_silent_except.py`

- 类型：Python
- 行数：159
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：静默异常门禁：禁止以任何形式吞掉异常。
- 导入：`__future__`, `argparse`, `ast`, `sys`, `contextlib`, `pathlib`
- 顶层符号：
  - L33: `def _broad(node)`
  - L44: `def _has_pass(node)`
  - L48: `def _only_pass_continue(node)`
  - L55: `def _call_name(call)`
  - L64: `def _is_stderr(call)`
  - L71: `def _transforms(node)`
  - L82: `def _reports(node)`
  - L97: `def _broad_suppress(tree)`
  - L112: `def main(argv)`

### A.403 `scripts/check_standards_manifest.py`

- 类型：Python
- 行数：84
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：校验 `skills/production-standards.md` 与 `standards_rules.py` 的编号集合一致。
- 导入：`__future__`, `configparser`, `re`, `sys`, `pathlib`, `typing`, `standards_rules`
- 顶层符号：
  - L25: `def skills_enabled(path)`
  - L39: `def read_manifest(path)`
  - L46: `def compare(version, updated, ids)`
  - L63: `def main()`

### A.404 `scripts/check_ui_js.py`

- 类型：Python
- 行数：386
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：经典 UI 的 JS 静态自检 —— 抓 `node --check` 抓不到的那类回归。
- 导入：`__future__`, `re`, `shutil`, `subprocess`, `sys`, `pathlib`, `agent.shell.web.ui_bundle`
- 顶层符号：
  - L94: `def model_id_literals(text)`
  - L138: `def _defined_names(text)`
  - L158: `def _undefined_called(text, also_defined)`
  - L172: `def _load_shared()`
  - L194: `def _where(owner, lineno)`
  - L199: `def _js_path(rel)`
  - L206: `def _watch_var_problems(lines, owner)`
  - L221: `def _required_problems(text)`
  - L231: `def _scrub(s)`
  - L237: `def _function_spans(lines)`
  - L254: `def _enclosing(spans, lineno)`
  - L262: `def _inner_function_problems(lines, owner)`
  - L297: `def _asset_problems()`
  - L306: `def _syntax_problems()`
  - L337: `def _model_problems()`
  - L354: `def main()`

### A.405 `scripts/ci.py`

- 类型：Python
- 行数：245
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：一条命令跑完全部校验（CI 入口）。
- 导入：`__future__`, `argparse`, `atexit`, `os`, `shutil`, `subprocess`, `sys`, `tempfile`, `time`, `pathlib`, `artifact_lock`, `ci_steps`
- 顶层符号：
  - L45: `def _data_files()`
  - L84: `def _data_rel(rel)`
  - L88: `def _is_runtime_data(rel)`
  - L93: `def _is_user_data(rel)`
  - L98: `def _prepare_data_root()`
  - L104: `def _run(label, cmd)`
  - L127: `def main(argv)`
  - L158: `def _run_local_js_event_audit()`
  - L173: `def _run_steps(args, steps)`

### A.406 `scripts/ci_steps.py`

- 类型：Python
- 行数：176
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：CI 步骤单一事实源（供 scripts/ci.py 与 check_ci_workflow 共用）。
- 导入：`__future__`, `dataclasses`, `typing`, `quality_budgets`
- 顶层符号：
  - L41: `class CiStep()`
  - L53: `def gate_steps()`
  - L99: `def acceptance_steps()`
  - L117: `def catalog(fast)`
  - L153: `def acceptance_skip_problems(names)`

### A.407 `scripts/complexity_scan.py`

- 类型：Python
- 行数：149
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：复杂度采集与渲染（`check_complexity` 与 `gen_complexity_md` 共用）。
- 导入：`__future__`, `ast`, `sys`, `pathlib`, `typing`
- 顶层符号：
  - L21: `def _iter_files(root)`
  - L33: `def _walk_functions(node, prefix, out)`
  - L51: `def collect(root)`
  - L77: `def over_threshold(files, funcs, max_file_lines, max_function_lines)`
  - L89: `def over_file_functions(per_file, max_file_functions)`
  - L96: `def _sorted_rows(values)`
  - L100: `def render(files, funcs, per_file, max_file_lines, max_function_lines, max_file_functions)`

### A.408 `scripts/dump_context.py`

- 类型：Python
- 行数：66
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：开发者工具：导出某个会话的真实请求上下文；不注册为模型工具。
- 导入：`__future__`, `argparse`, `json`, `os`, `sys`, `pathlib`, `agent.app`, `agent.config`, `agent.mechanisms.session_store`, `agent.shell.context_dump`
- 顶层符号：
  - L21: `def _parse_args(argv)`
  - L36: `def main(argv)`

### A.409 `scripts/gen_catalog.py`

- 类型：Python
- 行数：69
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：catalog 生成器：扫描装配工具集 → 生成注册文件 catalog/tools.json。
- 导入：`__future__`, `json`, `sys`, `pathlib`, `agent.app`
- 顶层符号：
  - L27: `def collect_schemas()`
  - L32: `def collect_display()`
  - L38: `def render_catalog(schemas, display)`
  - L52: `def write_catalog(path)`
  - L61: `def main()`

### A.410 `scripts/gen_ci_workflow.py`

- 类型：Python
- 行数：208
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：由 `scripts/ci_steps.py` 生成 `.github/workflows/ci.yml`。
- 导入：`__future__`, `sys`, `pathlib`, `typing`, `ci_steps`
- 顶层符号：
  - L144: `def _gate_block()`
  - L153: `def _acceptance_block()`
  - L171: `def render()`
  - L183: `def main(argv)`

### A.411 `scripts/gen_complexity_md.py`

- 类型：Python
- 行数：65
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：生成 `docs/complexity.md`（--check 只比对，不写盘）。
- 导入：`__future__`, `sys`, `pathlib`, `complexity_scan`, `quality_budgets`
- 顶层符号：
  - L36: `def build(root)`
  - L42: `def main(argv)`

### A.412 `scripts/gen_unit_tests_md.py`

- 类型：Python
- 行数：158
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：生成 / 校验 `docs/unit-tests.md`（单元测试用例清单）。
- 导入：`__future__`, `inspect`, `re`, `sys`, `unittest`, `collections`, `pathlib`
- 顶层符号：
  - L29: `def _walk(suite, out)`
  - L37: `def _one_line(text)`
  - L41: `def _method_label(name)`
  - L47: `def _objective(case)`
  - L66: `def collect()`
  - L79: `def render()`
  - L124: `def _display(path)`
  - L132: `def main(argv)`

### A.413 `scripts/inspect_compact.py`

- 类型：Python
- 行数：299
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：压缩检视：对某个会话打印上下文分段与压缩判定，只读不写。
- 导入：`__future__`, `argparse`, `sys`, `pathlib`, `typing`, `agent.config`, `agent.mechanisms.context.tokens`
- 顶层符号：
  - L44: `def _fmt_tokens(n)`
  - L48: `def _load_store(data_root, cid)`
  - L55: `def _list_conversations(data_root)`
  - L73: `def _round_labels(rounds)`
  - L96: `def _chunk_report(pipeline)`
  - L124: `def _prepare(cid, data_root)`
  - L155: `def _print_overview(cid, data_root, ctx)`
  - L176: `def _print_rounds(ctx)`
  - L204: `def _print_chunks(ctx)`
  - L216: `def _print_digest(ctx, digest)`
  - L250: `def inspect(cid, data_root, digest)`
  - L263: `def main(argv)`

### A.414 `scripts/pack_common.py`

- 类型：Python
- 行数：97
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：项目文件枚举：穷举非项目目录与文件，其余全部打包。
- 导入：`__future__`, `pathlib`, `typing`, `agent.update.assets`
- 顶层符号：
  - L60: `def _fold(value)`
  - L64: `def blacklist_reason(relative)`
  - L88: `def project_files(root)`

### A.415 `scripts/quality_budgets.py`

- 类型：Python
- 行数：42
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：质量预算与复杂度阈值（单一事实源）。
- 导入：`__future__`, `typing`
- 顶层符号：无

### A.416 `scripts/retired/acceptance_ui.py`

- 类型：Python
- 行数：1622
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：【已退役】旧 UI（自研三栏骨架）的浏览器端验收 —— **被测界面已不存在，勿再运行**。
- 导入：`__future__`, `base64`, `json`, `sys`, `tempfile`, `threading`, `time`, `urllib.request`, `pathlib`, `agent.app`, `agent.core.tool_call`, `agent.mechanisms.model_provider`, `agent.mechanisms.session_store`, `agent.shell.web.server`
- 顶层符号：
  - L52: `class DemoProvider()`
  - L114: `class Acceptance()`
  - L1602: `def main()`
- 类成员：
  - L65: `DemoProvider.__init__(self, workspace)`
  - L70: `DemoProvider._usage(self)`
  - L80: `DemoProvider.stream(self, request)`
  - L115: `Acceptance.__init__(self, root)`
  - L133: `Acceptance.check(self, label, cond, detail)`
  - L138: `Acceptance.close(self)`
  - L151: `Acceptance._cid(self)`
  - L161: `Acceptance._preview_result(self)`
  - L169: `Acceptance._history(self)`
  - L177: `Acceptance._pending_confirms(self)`
  - L185: `Acceptance._gate_confirmed(self, confirm_id)`
  - L192: `Acceptance._wait_turn(self, page, tries)`
  - L201: `Acceptance.run(self)`

### A.417 `scripts/run_acceptance_step.py`

- 类型：Python
- 行数：58
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：跑单个验收脚本，统一 OK / SKIP / FAIL 输出（供 GitHub CI 与本地使用）。
- 导入：`__future__`, `os`, `subprocess`, `sys`, `pathlib`
- 顶层符号：
  - L19: `def main(argv)`

### A.418 `scripts/run_coverage.py`

- 类型：Python
- 行数：94
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：跑单测并发布覆盖率数据：写入独立文件，再持锁原子替换终点的 `.coverage`。
- 导入：`__future__`, `os`, `subprocess`, `sys`, `time`, `pathlib`, `artifact_lock`
- 顶层符号：
  - L41: `def build_command(data_file)`
  - L50: `def publish(tmp, target, root)`
  - L65: `def main(argv)`

### A.419 `scripts/scan_js_events.py`

- 类型：Python
- 行数：634
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：本地 JS 事件绑定审计：为重渲染列表是否逐项绑事件提供可判定的线索。
- 导入：`__future__`, `argparse`, `os`, `re`, `sys`, `dataclasses`, `pathlib`, `typing`
- 顶层符号：
  - L94: `class Binding()`
  - L115: `def _line_of(text, offset)`
  - L119: `def _code_line(text, offset)`
  - L127: `def _block_comment_mask(text)`
  - L144: `def _in_line_comment(text, offset)`
  - L165: `def _is_comment_position(text, offset, block)`
  - L174: `def _skip_literal(text, idx)`
  - L211: `def _match_close(text, open_idx)`
  - L239: `def _body_end(text, start)`
  - L265: `def _loop_spans(text)`
  - L282: `def _func_spans(text)`
  - L315: `def _scope_of(target, callback)`
  - L335: `def _ephemeral_names(text)`
  - L351: `def _is_ephemeral(fresh, target)`
  - L362: `def _listener_callback(callback)`
  - L375: `def _has_paired_remove(text, target, event, callback)`
  - L401: `def _verdict(kind, scope, in_loop, render_fn, guarded, ephemeral, paired_remove)`
  - L429: `def scan_text(text, path)`
  - L509: `def iter_source_files()`
  - L533: `def scan_files(files)`
  - L558: `def read_guide()`
  - L564: `def render(bindings, file_count, only)`
  - L613: `def main(argv)`

### A.420 `scripts/standards_rules.py`

- 类型：Python
- 行数：35
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：`production-standards` 手册里可申报的准则编号（版本与日期见下方常量）。
- 导入：`__future__`, `typing`
- 顶层符号：无

### A.421 `scripts/ui_shot.py`

- 类型：Python
- 行数：225
- 所属主模块：`scripts`
- 文件角色：script
- 文件说明：界面自测：开无头 Chrome → 打开指定会话 → 报告关键样式 → 截图。
- 导入：`__future__`, `argparse`, `base64`, `hashlib`, `json`, `os`, `shutil`, `socket`, `struct`, `subprocess`, `sys`, `tempfile`, `time`, `urllib.request`, `pathlib`
- 顶层符号：
  - L49: `def find_chrome()`
  - L56: `class Ws()`
  - L141: `def main(argv)`
- 类成员：
  - L59: `Ws.__init__(self, url)`
  - L77: `Ws.send(self, obj)`
  - L90: `Ws._pump(self)`
  - L118: `Ws.call(self, method, params, timeout)`
  - L134: `Ws.close(self)`

### A.422 `tests/gate_fixtures.py`

- 类型：Python
- 行数：38
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：门控单测辅助：path_keys_for 从真实工具类属性读取（不手写键序字面量）。
- 导入：`__future__`, `typing`, `agent.capabilities.builtin.archive_tool`, `agent.capabilities.builtin.edit_tools`, `agent.capabilities.builtin.fs_tools`, `agent.capabilities.builtin.write_file`, `agent.mechanisms.quality`
- 顶层符号：
  - L29: `def builtin_path_keys(name)`
  - L35: `def make_gate()`

### A.423 `tests/test_ai_cosplay_plugin.py`

- 类型：Python
- 行数：107
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：AI角色扮演插件装配测试：临时清单、工具/端点/启动脚本、卸载与事件出口。
- 导入：`__future__`, `os`, `sys`, `tempfile`, `unittest`, `pathlib`, `unittest`, `agent.app`, `agent.core.context`, `agent.shell.classic_adapter.plugin_events`, `agent.shell.service_keys`
- 顶层符号：
  - L22: `class AICosplayAppTest(unittest.TestCase)`
- 类成员：
  - L23: `AICosplayAppTest.setUp(self)`
  - L35: `AICosplayAppTest.test_loaded_wiring(self)`
  - L65: `AICosplayAppTest.test_voice_directive_is_in_request_tail(self)`
  - L81: `AICosplayAppTest.test_publisher_tracks_connections(self)`
  - L96: `AICosplayAppTest.test_unload_clears_everything(self)`

### A.424 `tests/test_ai_cosplay_runtime.py`

- 类型：Python
- 行数：581
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：AI角色扮演运行时、工具与装配测试。
- 导入：`__future__`, `asyncio`, `base64`, `importlib`, `importlib.util`, `sys`, `threading`, `time`, `types`, `unittest`, `pathlib`, `types`, `typing`, `unittest`, `agent.capabilities.registry`, `agent.core.context`, `agent.core.session_scope`, `agent.core.tool_call`
- 顶层符号：
  - L39: `def _load_package()`
  - L65: `def _config()`
  - L77: `class RecordingProvider()`
  - L98: `class MissingProvider(RecordingProvider)`
  - L106: `class BlockingProvider(RecordingProvider)`
  - L118: `class FakePublisher()`
  - L137: `def _wait(predicate, timeout)`
  - L146: `class ProviderTest(unittest.TestCase)`
  - L196: `class RuntimeTest(unittest.TestCase)`
  - L298: `class ToolTest(unittest.TestCase)`
  - L504: `class _FakeCtx()`
  - L541: `class RegistrationTest(unittest.TestCase)`
- 类成员：
  - L80: `RecordingProvider.__init__(self, fail_texts)`
  - L84: `RecordingProvider.available(self)`
  - L87: `RecordingProvider.synthesize(self, text)`
  - L99: `MissingProvider.available(self)`
  - L102: `MissingProvider.synthesize(self, text)`
  - L107: `BlockingProvider.__init__(self)`
  - L112: `BlockingProvider.synthesize(self, text)`
  - L119: `FakePublisher.__init__(self, delivered)`
  - L124: `FakePublisher.__call__(self, plugin, event, payload)`
  - L129: `FakePublisher.connected(self)`
  - L132: `FakePublisher.snapshot(self)`
  - L147: `ProviderTest._fake_edge(self)`
  - L165: `ProviderTest.test_available_and_synthesize(self)`
  - L175: `ProviderTest.test_missing_dependency(self)`
  - L182: `ProviderTest.test_empty_audio(self)`
  - L188: `ProviderTest.test_timeout(self)`
  - L197: `RuntimeTest.setUp(self)`
  - L201: `RuntimeTest.test_publish_in_order_and_base64(self)`
  - L216: `RuntimeTest.test_playback_wait_timeout_and_cancel(self)`
  - L225: `RuntimeTest.test_synthesis_failure_is_isolated(self)`
  - L242: `RuntimeTest.test_no_sse_stops_worker(self)`
  - L252: `RuntimeTest.test_stop_clears_queue_and_publishes_stop(self)`
  - L268: `RuntimeTest.test_queue_full_rejects_whole_batch(self)`
  - L284: `RuntimeTest.test_dispose_publishes_stop_and_blocks_enqueue(self)`
  - L299: `ToolTest._runtime(self, provider)`
  - L304: `ToolTest._context(self, publisher)`
  - L313: `ToolTest._call(self, runtime, msg, publisher)`
  - L321: `ToolTest.test_plain_text_is_sent_without_annotation(self)`
  - L331: `ToolTest.test_success_enqueues_segments(self)`
  - L340: `ToolTest.test_sync_playback_waits_for_frontend_ack(self)`
  - L367: `ToolTest.test_sync_playback_times_out_without_ack(self)`
  - L392: `ToolTest.test_sync_synthesis_failure_is_not_reported_as_playback_failure(self)`
  - L403: `ToolTest.test_sync_playback_releases_on_stop(self)`
  - L428: `ToolTest.test_invalid_message_fails_before_enqueue(self)`
  - L435: `ToolTest.test_missing_publisher_fails(self)`
  - L451: `ToolTest.test_disconnected_publisher_fails(self)`
  - L456: `ToolTest.test_missing_provider_fails(self)`
  - L461: `ToolTest.test_tool_contract(self)`
  - L474: `ToolTest.test_pipeline_envelope(self)`
  - L505: `_FakeCtx.__init__(self)`
  - L514: `_FakeCtx.register_tool(self, tool)`
  - L518: `_FakeCtx.set_subagent_tools(self, tools)`
  - L521: `_FakeCtx.add_ui_item(self, path, kind, props, order)`
  - L525: `_FakeCtx.add_route(self, method, path, handler)`
  - L529: `_FakeCtx.subscribe(self, event_type, handler)`
  - L533: `_FakeCtx.add_mode_tail(self, fn)`
  - L537: `_FakeCtx.set_runtime(self, runtime)`
  - L542: `RegistrationTest.test_register_and_dispose(self)`
  - L557: `RegistrationTest.test_config_and_status_routes(self)`

### A.425 `tests/test_ai_cosplay_text.py`

- 类型：Python
- 行数：339
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：AI角色扮演文本规范、切分、合成净化与配置测试。
- 导入：`__future__`, `importlib.util`, `sys`, `tempfile`, `unittest`, `pathlib`
- 顶层符号：
  - L15: `def _load(name, filename)`
  - L29: `class SplitTest(unittest.TestCase)`
  - L96: `class ValidationTest(unittest.TestCase)`
  - L194: `class SpeechTextTest(unittest.TestCase)`
  - L278: `class ConfigTest(unittest.TestCase)`
- 类成员：
  - L30: `SplitTest.test_chinese_and_english_sentences(self)`
  - L48: `SplitTest.test_packing_respects_limit(self)`
  - L62: `SplitTest.test_configured_limit_is_not_capped(self)`
  - L67: `SplitTest.test_message_limit(self)`
  - L74: `SplitTest.test_single_piece_over_limit(self)`
  - L80: `SplitTest.test_quoted_end_is_a_boundary(self)`
  - L90: `SplitTest.test_numeric_separators_are_not_boundaries(self)`
  - L97: `ValidationTest.assert_code(self, msg, code)`
  - L102: `ValidationTest.test_rejects_empty_and_missing_end(self)`
  - L108: `ValidationTest.test_rejects_control_characters(self)`
  - L115: `ValidationTest.test_non_speakable_symbols_are_accepted(self)`
  - L126: `ValidationTest.test_reports_rule_in_error(self)`
  - L135: `ValidationTest.test_invisible_character_named_in_error(self)`
  - L142: `ValidationTest.test_path_and_book_title_chars_allowed(self)`
  - L152: `ValidationTest.test_rejects_unmatched_book_title(self)`
  - L158: `ValidationTest.test_rejects_empty_pairs(self)`
  - L163: `ValidationTest.test_rejects_unmatched_pairs(self)`
  - L168: `ValidationTest.test_bracket_quotes_pair_and_do_not_split(self)`
  - L177: `ValidationTest.test_rejects_math_context(self)`
  - L183: `ValidationTest.test_rejects_percent_without_number(self)`
  - L188: `ValidationTest.test_rejects_leading_boundary(self)`
  - L195: `SpeechTextTest.test_quotes_and_apostrophes(self)`
  - L200: `SpeechTextTest.test_bracket_and_book_title_quotes_are_dropped(self)`
  - L209: `SpeechTextTest.test_non_speakable_symbols_are_dropped(self)`
  - L213: `SpeechTextTest.test_hang_after_number_uses_homophone(self)`
  - L237: `SpeechTextTest.test_percent(self)`
  - L250: `SpeechTextTest.test_math(self)`
  - L268: `SpeechTextTest.test_dates_and_identifiers_are_not_math(self)`
  - L273: `SpeechTextTest.test_thousands_separator_removed(self)`
  - L279: `ConfigTest.test_missing_file_uses_defaults(self)`
  - L293: `ConfigTest.test_values_and_limits(self)`
  - L326: `ConfigTest.test_invalid_engine_and_voice_fail(self)`

### A.426 `tests/test_anthropic_provider.py`

- 类型：Python
- 行数：507
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：Anthropic 适配测试：SSE 归并、消息折叠与修补、请求体、错误映射。
- 导入：`__future__`, `io`, `json`, `time`, `unittest`, `urllib.error`, `unittest`, `agent.core.model_call`, `agent.core.ports`, `agent.mechanisms.providers`, `agent.mechanisms.providers.anthropic`, `agent.mechanisms.providers.base`
- 顶层符号：
  - L32: `def _sse(event_type, payload)`
  - L37: `def _text_stream(texts)`
  - L55: `def _tool_stream(with_thinking)`
  - L84: `class StreamAssemblyTest(unittest.TestCase)`
  - L168: `class MessageConversionTest(unittest.TestCase)`
  - L404: `def thinking_blocks(message)`
  - L410: `class EndpointAndErrorTest(unittest.TestCase)`
- 类成员：
  - L85: `StreamAssemblyTest.test_text_deltas_stream_through_and_usage_is_mapped(self)`
  - L97: `StreamAssemblyTest.test_cache_fields_default_to_zero_when_absent(self)`
  - L104: `StreamAssemblyTest.test_thinking_and_tool_use_are_reassembled(self)`
  - L114: `StreamAssemblyTest.test_meta_is_emitted_only_when_thinking_and_tools_coexist(self)`
  - L123: `StreamAssemblyTest.test_thinking_without_signature_is_skipped_with_a_warning(self)`
  - L134: `StreamAssemblyTest.test_invalid_tool_json_degrades_to_empty_arguments(self)`
  - L143: `StreamAssemblyTest.test_missing_tool_id_gets_a_generated_one(self)`
  - L152: `StreamAssemblyTest.test_error_event_becomes_model_request_error(self)`
  - L159: `StreamAssemblyTest.test_ping_and_unknown_events_are_ignored(self)`
  - L169: `MessageConversionTest.test_system_is_hoisted_and_user_text_becomes_a_block(self)`
  - L184: `MessageConversionTest.test_image_urls_are_split_into_image_blocks(self)`
  - L205: `MessageConversionTest.test_assistant_tool_calls_become_tool_use_blocks(self)`
  - L217: `MessageConversionTest.test_consecutive_tool_results_merge_into_one_user_message(self)`
  - L233: `MessageConversionTest.test_duplicate_tool_ids_are_suffixed_and_results_follow(self)`
  - L254: `MessageConversionTest.test_leading_assistant_is_dropped(self)`
  - L261: `MessageConversionTest.test_dangling_tool_result_is_dropped(self)`
  - L270: `MessageConversionTest.test_thinking_blocks_replay_only_within_the_current_turn(self)`
  - L283: `MessageConversionTest.test_tools_payload_accepts_both_declaration_shapes(self)`
  - L299: `MessageConversionTest.test_logic_shaped_tool_becomes_a_valid_object_schema(self)`
  - L326: `MessageConversionTest.test_thinking_is_enabled_only_when_the_budget_fits(self)`
  - L344: `MessageConversionTest.test_thinking_off_is_sent_as_disabled_not_omitted(self)`
  - L350: `MessageConversionTest.test_tool_turn_without_thinking_blocks_disables_thinking(self)`
  - L371: `MessageConversionTest.test_disabled_thinking_does_not_replay_stored_blocks(self)`
  - L384: `MessageConversionTest.test_thinking_block_with_empty_text_is_still_replayed(self)`
  - L411: `EndpointAndErrorTest.test_messages_url_variants(self)`
  - L417: `EndpointAndErrorTest.test_http_errors_use_the_anthropic_table_and_keep_upstream_detail(self)`
  - L426: `EndpointAndErrorTest.test_missing_credentials_fail_before_any_network_call(self)`
  - L434: `EndpointAndErrorTest.test_stream_posts_headers_and_payload_then_parses_sse(self)`
  - L471: `EndpointAndErrorTest.test_stream_watchdog_stops_a_stalled_upstream(self)`
  - L491: `EndpointAndErrorTest.test_http_error_response_is_mapped(self)`

### A.427 `tests/test_app_context.py`

- 类型：Python
- 行数：125
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：AppContext 测试：注册 / 解析 / disposer / 逆序清理。
- 导入：`__future__`, `sys`, `unittest`, `pathlib`, `agent.core.context`
- 顶层符号：
  - L15: `class AppContextTest(unittest.TestCase)`
- 类成员：
  - L18: `AppContextTest.test_register_and_get(self)`
  - L25: `AppContextTest.test_get_missing_raises(self)`
  - L31: `AppContextTest.test_register_duplicate_rejected(self)`
  - L38: `AppContextTest.test_register_empty_name_rejected(self)`
  - L44: `AppContextTest.test_disposer_removes_service(self)`
  - L52: `AppContextTest.test_disposer_idempotent(self)`
  - L61: `AppContextTest.test_none_value_service_fully_disposed(self)`
  - L74: `AppContextTest.test_dispose_all_clears_everything(self)`
  - L86: `AppContextTest.test_dispose_all_empty_ok(self)`
  - L91: `AppContextTest.test_dispose_then_dispose_all_consistent(self)`
  - L102: `AppContextTest.test_dispose_all_runs_in_reverse_registration_order(self)`

### A.428 `tests/test_app_context_wiring.py`

- 类型：Python
- 行数：200
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：进程级上下文（AppContext）装配集成测试。
- 导入：`__future__`, `sys`, `tempfile`, `unittest`, `pathlib`, `agent.app`, `agent.core.context`, `agent.shell.service_keys`
- 顶层符号：
  - L63: `class _AppFixture(unittest.TestCase)`
  - L75: `class ProcessServiceRegistryTest(_AppFixture)`
  - L130: `class AppAttributeDelegationTest(_AppFixture)`
  - L161: `class DisposeTest(_AppFixture)`
- 类成员：
  - L66: `_AppFixture.setUp(self)`
  - L78: `ProcessServiceRegistryTest.test_build_app_is_context_backed(self)`
  - L82: `ProcessServiceRegistryTest.test_all_required_services_registered(self)`
  - L88: `ProcessServiceRegistryTest.test_store_absent_when_not_injected(self)`
  - L94: `ProcessServiceRegistryTest.test_context_and_compactor_factories_default_on(self)`
  - L105: `ProcessServiceRegistryTest.test_optional_services_registered_when_injected(self)`
  - L119: `ProcessServiceRegistryTest.test_compactor_factory_registered_by_default(self)`
  - L125: `ProcessServiceRegistryTest.test_duplicate_registration_still_rejected(self)`
  - L133: `AppAttributeDelegationTest.test_every_attribute_resolves_to_context_service(self)`
  - L143: `AppAttributeDelegationTest.test_app_holds_no_duplicate_service_state(self)`
  - L149: `AppAttributeDelegationTest.test_service_attributes_are_read_only(self)`
  - L156: `AppAttributeDelegationTest.test_gate_still_resolves_through_session_registry(self)`
  - L164: `DisposeTest.test_dispose_clears_services_and_sessions(self)`
  - L177: `DisposeTest.test_dispose_releases_default_bucket_gate(self)`
  - L187: `DisposeTest.test_dispose_is_idempotent(self)`
  - L193: `DisposeTest.test_runner_registered_and_mesh_activator_wired(self)`

### A.429 `tests/test_architecture_hygiene.py`

- 类型：Python
- 行数：299
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：架构约束：门控旁路 AST 检测（负例伪装 + 正例放行）。
- 导入：`__future__`, `sys`, `tempfile`, `textwrap`, `unittest`, `pathlib`, `check_architecture_hygiene`
- 顶层符号：
  - L26: `def _agent_tree(tmp)`
  - L34: `def _write(pkg, rel, src)`
  - L41: `class GateSinglePathAstTest(unittest.TestCase)`
  - L149: `class QualityGateShimAstTest(unittest.TestCase)`
  - L189: `class ModuleBoundaryAstTest(unittest.TestCase)`
  - L234: `class SameLayerPrivateImportTest(unittest.TestCase)`
  - L251: `class TestMethodNameGateTest(unittest.TestCase)`
  - L265: `class SilentSystemPromptCheckTest(unittest.TestCase)`
- 类成员：
  - L44: `GateSinglePathAstTest._assert_catches(self, src, symbol)`
  - L55: `GateSinglePathAstTest.test_fallback_gate_attribute(self)`
  - L65: `GateSinglePathAstTest.test_gate_resolver_call_attr(self)`
  - L74: `GateSinglePathAstTest.test_tool_path_keys_name(self)`
  - L83: `GateSinglePathAstTest.test_register_write_path_keys_call(self)`
  - L92: `GateSinglePathAstTest.test_unregister_write_path_keys_import_alias(self)`
  - L101: `GateSinglePathAstTest.test_preview_tools_keyword(self)`
  - L112: `GateSinglePathAstTest.test_content_tools_assign_attr(self)`
  - L124: `GateSinglePathAstTest.test_preview_tools_tuple_unpack(self)`
  - L132: `GateSinglePathAstTest.test_innocuous_code_passes(self)`
  - L150: `QualityGateShimAstTest.test_import_quality_gate_caught(self)`
  - L169: `QualityGateShimAstTest.test_comment_mention_passes(self)`
  - L190: `ModuleBoundaryAstTest.test_provider_concrete_sibling_caught(self)`
  - L201: `ModuleBoundaryAstTest.test_provider_neutral_imports_pass(self)`
  - L212: `ModuleBoundaryAstTest.test_compactor_pipeline_import_caught(self)`
  - L223: `ModuleBoundaryAstTest.test_compactor_contract_import_passes(self)`
  - L235: `SameLayerPrivateImportTest.test_private_same_layer_caught(self)`
  - L243: `SameLayerPrivateImportTest.test_public_same_layer_passes(self)`
  - L252: `TestMethodNameGateTest.test_bad_test_prefix_caught(self)`
  - L258: `TestMethodNameGateTest.test_public_test_prefix_passes(self)`
  - L266: `SilentSystemPromptCheckTest.test_nonstandard_indent_and_as_clause_caught(self)`
  - L285: `SilentSystemPromptCheckTest.test_external_package_root_does_not_crash(self)`

### A.430 `tests/test_artifact_lock.py`

- 类型：Python
- 行数：200
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：产物锁与覆盖率发布：同一份共享文件被并行写时必须串行或明确跳过。
- 导入：`__future__`, `json`, `os`, `sys`, `tempfile`, `threading`, `time`, `unittest`, `contextlib`, `io`, `pathlib`, `unittest`, `artifact_lock`, `check_coverage`, `run_coverage`
- 顶层符号：
  - L28: `def _write_holder(lock, pid, token, purpose)`
  - L36: `class ArtifactLockTest(unittest.TestCase)`
  - L140: `class CoveragePublishTest(unittest.TestCase)`
  - L165: `class CoverageBusyTest(unittest.TestCase)`
- 类成员：
  - L39: `ArtifactLockTest.setUp(self)`
  - L44: `ArtifactLockTest._lock(self, name, purpose)`
  - L49: `ArtifactLockTest.test_acquire_records_holder(self)`
  - L57: `ArtifactLockTest.test_second_owner_is_rejected_with_holder_info(self)`
  - L65: `ArtifactLockTest.test_release_frees_lock_for_next_owner(self)`
  - L74: `ArtifactLockTest.test_release_is_idempotent(self)`
  - L81: `ArtifactLockTest.test_holder_with_dead_pid_is_reclaimed(self)`
  - L87: `ArtifactLockTest.test_half_written_lock_holds_until_grace_period(self)`
  - L93: `ArtifactLockTest.test_half_written_lock_is_reclaimed_after_grace_period(self)`
  - L101: `ArtifactLockTest.test_force_breaks_live_holder(self)`
  - L111: `ArtifactLockTest.test_wait_succeeds_after_holder_releases(self)`
  - L126: `ArtifactLockTest.test_release_keeps_foreign_lock(self)`
  - L133: `ArtifactLockTest.test_parse_holder_rejects_garbage(self)`
  - L143: `CoveragePublishTest.setUp(self)`
  - L148: `CoveragePublishTest.test_build_command_writes_unique_data_file(self)`
  - L155: `CoveragePublishTest.test_publish_replaces_target(self)`
  - L168: `CoverageBusyTest.setUp(self)`
  - L173: `CoverageBusyTest.test_check_locked_skips_when_data_changes_during_measure(self)`
  - L185: `CoverageBusyTest.test_main_skips_when_writer_holds_lock(self)`
  - L194: `CoverageBusyTest.test_stamp_is_none_for_missing_file(self)`

### A.431 `tests/test_attachments_autonomy.py`

- 类型：Python
- 行数：230
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：截图附件与自主模式。
- 导入：`__future__`, `base64`, `io`, `json`, `sys`, `unittest`, `pathlib`, `agent.core.events`, `agent.core.input_attachments`, `agent.core.modules.input_mod`, `agent.core.ports`, `agent.core.session_log`, `agent.mechanisms.live_state`
- 顶层符号：
  - L36: `def _img(mime, data)`
  - L39: `class NormalizeImagesTest(unittest.TestCase)`
  - L81: `class UserContentTest(unittest.TestCase)`
  - L143: `class VisionDegradeTest(unittest.TestCase)`
  - L188: `class AutonomyTest(unittest.TestCase)`
- 类成员：
  - L42: `NormalizeImagesTest.test_accepts_valid_image(self)`
  - L49: `NormalizeImagesTest.test_mime_is_lowercased(self)`
  - L54: `NormalizeImagesTest.test_drops_non_image_mime(self)`
  - L59: `NormalizeImagesTest.test_drops_empty_or_missing_data(self)`
  - L64: `NormalizeImagesTest.test_drops_non_dict_and_non_list(self)`
  - L70: `NormalizeImagesTest.test_caps_at_max_images(self)`
  - L75: `NormalizeImagesTest.test_keeps_valid_when_mixed_with_invalid(self)`
  - L84: `UserContentTest.test_no_attachments_is_plain_string(self)`
  - L89: `UserContentTest.test_text_and_image_parts(self)`
  - L97: `UserContentTest.test_user_content_keeps_attachment_reference(self)`
  - L104: `UserContentTest.test_image_only_has_no_empty_text_part(self)`
  - L110: `UserContentTest.test_invalid_attachment_ignored(self)`
  - L114: `UserContentTest.test_input_module_emits_attachment_reference(self)`
  - L124: `UserContentTest.test_derive_messages_builds_multimodal_user_message(self)`
  - L135: `UserContentTest.test_derive_messages_without_attachments_stays_string(self)`
  - L146: `VisionDegradeTest.setUp(self)`
  - L163: `VisionDegradeTest._provider(self, model)`
  - L167: `VisionDegradeTest.test_any_model_keeps_image_parts(self)`
  - L179: `VisionDegradeTest.test_image_only_message_is_not_empty(self)`
  - L191: `AutonomyTest.test_live_state_roundtrip(self)`
  - L200: `AutonomyTest.test_per_conversation(self)`
  - L206: `AutonomyTest.test_runner_auto_continue_check_used(self)`
  - L222: `AutonomyTest.test_no_auto_continue_means_no_continue(self)`

### A.432 `tests/test_auth_security.py`

- 类型：Python
- 行数：97
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：鉴权文件安全：目录、原子写入与平台权限校验。
- 导入：`__future__`, `os`, `subprocess`, `tempfile`, `unittest`, `pathlib`, `unittest`, `agent.shell.web.auth`, `agent.shell.web.auth.audit`, `agent.shell.web.auth.security`
- 顶层符号：
  - L23: `class AuthSecurityTest(unittest.TestCase)`
- 类成员：
  - L24: `AuthSecurityTest.test_directory_and_atomic_secret(self)`
  - L37: `AuthSecurityTest.test_missing_path_is_rejected(self)`
  - L42: `AuthSecurityTest.test_atomic_failure_leaves_no_target(self)`
  - L54: `AuthSecurityTest.test_audit_hot_path_does_not_spawn(self)`
  - L63: `AuthSecurityTest.test_widened_acl_is_rejected_immediately(self)`
  - L76: `AuthSecurityTest.test_widened_directory_is_repaired(self)`
  - L87: `AuthSecurityTest.test_windows_timeout_is_security_error(self)`

### A.433 `tests/test_background_tasks.py`

- 类型：Python
- 行数：316
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：后台任务管理器：队列、执行、输出、取消与 cid 隔离。
- 导入：`__future__`, `os`, `sys`, `tempfile`, `time`, `unittest`, `pathlib`, `unittest`, `agent.app`, `agent.capabilities.builtin.background_task`, `agent.core.events`, `agent.mechanisms.background_tasks`
- 顶层符号：
  - L27: `def _py(code)`
  - L31: `class BackgroundTaskManagerTest(unittest.TestCase)`
- 类成员：
  - L32: `BackgroundTaskManagerTest.setUp(self)`
  - L40: `BackgroundTaskManagerTest.tearDown(self)`
  - L44: `BackgroundTaskManagerTest.test_env_allowlist_keeps_user_paths_excludes_secrets(self)`
  - L56: `BackgroundTaskManagerTest.test_background_process_sees_user_paths(self)`
  - L71: `BackgroundTaskManagerTest.test_output_cursor_rebases_after_buffer_trim(self)`
  - L89: `BackgroundTaskManagerTest.test_completed_output_and_history(self)`
  - L108: `BackgroundTaskManagerTest.test_cancel_queued_task(self)`
  - L126: `BackgroundTaskManagerTest.test_queue_capacity_and_cid_isolation(self)`
  - L141: `BackgroundTaskManagerTest.test_app_wires_manager_and_tool(self)`
  - L150: `BackgroundTaskManagerTest.test_label_required_but_not_unique(self)`
  - L159: `BackgroundTaskManagerTest.test_batch_groups_tasks_and_filters_exact_id(self)`
  - L178: `BackgroundTaskManagerTest.test_batch_returns_all_tasks_without_pagination(self)`
  - L193: `BackgroundTaskManagerTest.test_execution_timeout_and_running_cancel(self)`
  - L214: `BackgroundTaskManagerTest.test_argv_is_not_shell_interpreted(self)`
  - L222: `BackgroundTaskManagerTest.test_plan_mode_rejects_create(self)`
  - L235: `BackgroundTaskManagerTest.test_tool_dispatch_create_list_output_cancel(self)`
  - L265: `BackgroundTaskManagerTest.test_system_notice_metadata_survives_queue_and_history(self)`
  - L309: `BackgroundTaskManagerTest.test_cwd_outside_root_rejected(self)`

### A.434 `tests/test_base_settings_plugin.py`

- 类型：Python
- 行数：46
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：基础设置插件的面板与条目契约。
- 导入：`__future__`, `unittest`, `plugins.base_settings.plugin`
- 顶层符号：
  - L10: `class _Ctx()`
  - L27: `class BaseSettingsPluginTest(unittest.TestCase)`
- 类成员：
  - L11: `_Ctx.__init__(self)`
  - L15: `_Ctx.add_settings_panel(self, panel_id, title)`
  - L19: `_Ctx.add_settings_item(self, parent, item_id)`
  - L23: `_Ctx.add_ui_item(self, path, kind, props, order)`
  - L28: `BaseSettingsPluginTest.test_registers_host_panels_and_items(self)`
  - L38: `BaseSettingsPluginTest.test_does_not_register_model_panel(self)`

### A.435 `tests/test_batch_f_tools.py`

- 类型：Python
- 行数：401
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：集成与外围测试：ip 定位 / 天气 / review 提交 / Skills 库与工具。
- 导入：`__future__`, `sys`, `tempfile`, `threading`, `unittest`, `pathlib`, `unittest`, `agent.capabilities.builtin`, `plugins.skills`, `plugins.skills.library`
- 顶层符号：
  - L26: `def _ipwho_payload()`
  - L40: `def _forecast_payload()`
  - L52: `class IpGeolocateTest(unittest.TestCase)`
  - L91: `class WeatherTest(unittest.TestCase)`
  - L154: `class ReviewConclusionTest(unittest.TestCase)`
  - L202: `class SkillsLibraryTest(unittest.TestCase)`
  - L239: `class SkillsToolTest(unittest.TestCase)`
  - L266: `class SkillsSourceTest(unittest.TestCase)`
  - L325: `class SkillsListNeverDoublesTest(unittest.TestCase)`
- 类成员：
  - L55: `IpGeolocateTest.setUp(self)`
  - L58: `IpGeolocateTest.test_private_ip_normalized_to_export_lookup(self)`
  - L71: `IpGeolocateTest.test_public_ip_path_with_loopback_variants(self)`
  - L84: `IpGeolocateTest.test_success_false_structured_error(self)`
  - L94: `WeatherTest.setUp(self)`
  - L97: `WeatherTest.test_cn_alias_direct_resolution(self)`
  - L113: `WeatherTest.test_coordinates_and_days_clamp(self)`
  - L126: `WeatherTest.test_location_not_found(self)`
  - L132: `WeatherTest.test_scoring_prefers_exact_and_major(self)`
  - L157: `ReviewConclusionTest.setUp(self)`
  - L172: `ReviewConclusionTest.test_short_conclusion_and_missing_file_name_rejected(self)`
  - L178: `ReviewConclusionTest.test_call_is_submit_not_format_check(self)`
  - L184: `ReviewConclusionTest.test_confirm_unlock_and_review_done(self)`
  - L194: `ReviewConclusionTest.test_cancel_preview_and_invalid(self)`
  - L205: `SkillsLibraryTest.setUp(self)`
  - L222: `SkillsLibraryTest.test_scan_list_and_matching(self)`
  - L232: `SkillsLibraryTest.test_truncation_and_incremental_rescan(self)`
  - L242: `SkillsToolTest.setUp(self)`
  - L252: `SkillsToolTest.test_list_read_and_lookup_error(self)`
  - L269: `SkillsSourceTest.setUp(self)`
  - L292: `SkillsSourceTest.test_external_overrides_builtin_and_both_auto_loads(self)`
  - L303: `SkillsSourceTest.test_catalog_separates_builtin_and_external(self)`
  - L311: `SkillsSourceTest.test_tool_description_does_not_embed_external_dir(self)`
  - L317: `SkillsSourceTest.test_resource_directory_section_has_both_sources(self)`
  - L328: `SkillsListNeverDoublesTest.setUp(self)`
  - L338: `SkillsListNeverDoublesTest.tearDown(self)`
  - L341: `SkillsListNeverDoublesTest.test_duplicate_entries_do_not_double_the_catalog(self)`
  - L354: `SkillsListNeverDoublesTest.test_rescan_does_not_append_twice(self)`
  - L360: `SkillsListNeverDoublesTest.test_different_path_spelling_counts_once(self)`
  - L371: `SkillsListNeverDoublesTest.test_auto_load_count_ignores_duplicate_entries(self)`
  - L385: `SkillsListNeverDoublesTest.test_concurrent_rescan_replaces_the_list(self)`

### A.436 `tests/test_catalog.py`

- 类型：Python
- 行数：120
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：catalog 生成与校验测试：渲染确定性 / 漂移检出 / 仓库零漂移锚点。
- 导入：`__future__`, `json`, `sys`, `tempfile`, `unittest`, `pathlib`, `check_catalog`, `gen_catalog`
- 顶层符号：
  - L24: `class RenderCatalogTest(unittest.TestCase)`
  - L59: `class CheckCatalogTest(unittest.TestCase)`
  - L98: `class CatalogDisplayTest(unittest.TestCase)`
- 类成员：
  - L27: `RenderCatalogTest.test_render_deterministic(self)`
  - L35: `RenderCatalogTest.test_render_sorted_and_complete(self)`
  - L46: `RenderCatalogTest.test_write_catalog_roundtrip(self)`
  - L62: `CheckCatalogTest.test_missing_file_detected(self)`
  - L68: `CheckCatalogTest.test_corrupt_file_detected(self)`
  - L76: `CheckCatalogTest.test_drift_detected(self)`
  - L101: `CatalogDisplayTest.test_every_tool_has_display(self)`
  - L110: `CatalogDisplayTest.test_render_includes_display(self)`

### A.437 `tests/test_classic_adapter.py`

- 类型：Python
- 行数：1821
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：经典界面适配层契约测试 —— 逐字段钉住内核 ↔ 经典界面的双向翻译。
- 导入：`__future__`, `json`, `sys`, `tempfile`, `unittest`, `pathlib`, `typing`, `agent.shell.classic_adapter`, `agent.shell.classic_adapter.adapter`, `agent.shell.classic_adapter.outbound`, `agent.shell.web.ui_bundle`, `tests.testkit`
- 顶层符号：
  - L41: `class _FakeApp()`
  - L99: `def _stream()`
  - L106: `def _types(frames)`
  - L109: `class PluginEventTest(unittest.TestCase)`
  - L148: `class UsageSemanticsTest(unittest.TestCase)`
  - L182: `class OutboundContractTest(unittest.TestCase)`
  - L687: `class InboundContractTest(unittest.TestCase)`
  - L999: `class WireHygieneTest(unittest.TestCase)`
  - L1131: `class ResumeContractTest(unittest.TestCase)`
  - L1266: `class SubscriptionLifecycleTest(unittest.TestCase)`
  - L1331: `class UserConfirmRoundTripTest(unittest.TestCase)`
  - L1506: `class UiBundleTest(unittest.TestCase)`
  - L1633: `class HistoryAttachmentReplayTest(unittest.TestCase)`
- 类成员：
  - L72: `_FakeApp.__init__(self, data_root)`
  - L112: `PluginEventTest.test_frame_shape_and_copy(self)`
  - L123: `PluginEventTest.test_frame_rejects_reserved_and_bad_names(self)`
  - L135: `PluginEventTest.test_announce_broadcasts_to_channels(self)`
  - L157: `UsageSemanticsTest.test_put_overwrites_instead_of_accumulating(self)`
  - L185: `OutboundContractTest.test_turn_started_emits_conversation_first(self)`
  - L204: `OutboundContractTest.test_step_started_emits_llm_round_then_request(self)`
  - L214: `OutboundContractTest.test_llm_request_model_is_never_empty(self)`
  - L219: `OutboundContractTest.test_reasoning_delta_requires_round(self)`
  - L229: `OutboundContractTest.test_assistant_delta_uses_delta_field(self)`
  - L233: `OutboundContractTest.test_tool_call_becomes_tool_start_with_call_id(self)`
  - L243: `OutboundContractTest.test_tool_call_without_id_is_skipped(self)`
  - L248: `OutboundContractTest.test_tool_result_preview_is_json_string(self)`
  - L263: `OutboundContractTest.test_tool_done_images_ride_beside_preview(self)`
  - L282: `OutboundContractTest.test_tool_result_without_start_is_skipped(self)`
  - L286: `OutboundContractTest.test_confirm_card_comes_from_the_kernel_fact(self)`
  - L313: `OutboundContractTest.test_tool_call_does_not_pre_empt_the_confirm_card(self)`
  - L327: `OutboundContractTest.test_incomplete_awaiting_fact_is_ignored(self)`
  - L339: `OutboundContractTest.test_user_confirm_multi_flag_passes_through(self)`
  - L347: `OutboundContractTest.test_plain_failure_is_not_mistaken_for_confirm(self)`
  - L369: `OutboundContractTest.test_write_gate_confirm_id_does_not_fake_a_confirmation(self)`
  - L391: `OutboundContractTest.test_only_a_real_suspension_asks_the_user(self)`
  - L408: `OutboundContractTest.test_vision_consent_keeps_plugin_confirmation_endpoint(self)`
  - L428: `OutboundContractTest.test_approval_suspension_is_not_a_choice_card(self)`
  - L447: `OutboundContractTest.test_cancel_on_confirm_modal_records_a_declined_result(self)`
  - L488: `OutboundContractTest.test_cancel_without_pending_does_not_start_an_empty_turn(self)`
  - L515: `OutboundContractTest.test_chat_bubble_layout_puts_image_above_text(self)`
  - L528: `OutboundContractTest.test_reasoning_is_not_promoted_into_chat_area(self)`
  - L538: `OutboundContractTest.test_run_type_switch_emits_mode_changed(self)`
  - L558: `OutboundContractTest.test_run_type_query_does_not_emit_mode_changed(self)`
  - L567: `OutboundContractTest.test_failed_run_type_switch_does_not_emit_mode_changed(self)`
  - L578: `OutboundContractTest.test_todo_list_rides_on_tool_end(self)`
  - L600: `OutboundContractTest.test_usage_must_be_nested(self)`
  - L616: `OutboundContractTest.test_context_layout_is_flat_with_segments(self)`
  - L623: `OutboundContractTest.test_context_compacted_emits_card_payload(self)`
  - L637: `OutboundContractTest.test_tool_end_carries_elapsed_seconds(self)`
  - L646: `OutboundContractTest.test_assistant_only_on_final_message_with_content(self)`
  - L657: `OutboundContractTest.test_model_message_with_content_emits_response_done_and_assistant(self)`
  - L664: `OutboundContractTest.test_turn_ended_emits_done(self)`
  - L669: `OutboundContractTest.test_unknown_kernel_event_is_ignored_not_raised(self)`
  - L673: `OutboundContractTest.test_malformed_arguments_do_not_break_the_stream(self)`
  - L690: `InboundContractTest.setUp(self)`
  - L697: `InboundContractTest.test_sessions_read_id_not_conversation_id(self)`
  - L706: `InboundContractTest.test_ui_state_get_returns_only_client_independent_state(self)`
  - L718: `InboundContractTest.test_ui_state_put_stores_nothing(self)`
  - L728: `InboundContractTest.test_ui_state_put_writes_no_layout_file(self)`
  - L734: `InboundContractTest.test_usage_accumulator_uses_different_field_names(self)`
  - L745: `InboundContractTest.test_usage_hydrates_from_facts_after_state_reset(self)`
  - L763: `InboundContractTest.test_usage_accumulates_across_events(self)`
  - L768: `InboundContractTest.test_attachment_returns_image_bytes_not_json(self)`
  - L780: `InboundContractTest.test_attachment_missing_is_404(self)`
  - L784: `InboundContractTest.test_attachment_ignores_invalid_images(self)`
  - L788: `InboundContractTest.test_invalid_conversation_id_rejected_on_write(self)`
  - L791: `InboundContractTest.test_health_model_is_in_allowed_list(self)`
  - L799: `InboundContractTest.test_history_page_before_and_meta(self)`
  - L830: `InboundContractTest.test_remember_attachments_merges_previous_pages(self)`
  - L842: `InboundContractTest.test_history_returns_ok_true(self)`
  - L847: `InboundContractTest.test_history_returns_items_for_bubbles(self)`
  - L881: `InboundContractTest.test_history_cancels_suspended_tool_after_new_input(self)`
  - L910: `InboundContractTest.test_history_carries_context_layout_at_top_level(self)`
  - L931: `InboundContractTest.test_history_todo_ignores_other_tools_items(self)`
  - L966: `InboundContractTest.test_history_todo_empty_when_none_active(self)`
  - L992: `InboundContractTest.test_history_rejects_bad_id(self)`
  - L996: `InboundContractTest.test_title_never_raises(self)`
  - L1002: `WireHygieneTest.setUp(self)`
  - L1007: `WireHygieneTest.test_every_frame_carries_valid_conversation_id(self)`
  - L1029: `WireHygieneTest.test_frames_broadcast_to_every_channel(self)`
  - L1053: `WireHygieneTest.test_detach_stops_delivery(self)`
  - L1059: `WireHygieneTest.test_heartbeat_is_cid_exempt(self)`
  - L1071: `WireHygieneTest.test_frame_without_cid_is_dropped_silently(self)`
  - L1077: `WireHygieneTest.test_sse_payload_is_single_line_data_frame(self)`
  - L1093: `WireHygieneTest.test_channel_emits_heartbeat_when_idle(self)`
  - L1105: `WireHygieneTest.test_normalize_cid_matches_ui_rule(self)`
  - L1111: `WireHygieneTest.test_tool_script_mapping_covers_known_tools(self)`
  - L1118: `WireHygieneTest.test_cid_exempt_set_matches_contract(self)`
  - L1137: `ResumeContractTest.setUp(self)`
  - L1150: `ResumeContractTest._seed(self, count)`
  - L1173: `ResumeContractTest.test_replay_frames_carry_seq(self)`
  - L1187: `ResumeContractTest.test_replay_respects_cursor(self)`
  - L1202: `ResumeContractTest.test_replay_only_targets_given_channel(self)`
  - L1212: `ResumeContractTest._drain(box)`
  - L1218: `ResumeContractTest.test_sse_id_line_is_emitted_for_seq_frames(self)`
  - L1232: `ResumeContractTest.test_cursor_prefers_header_then_query(self)`
  - L1249: `ResumeContractTest.test_latest_seq_reports_global_log_end(self)`
  - L1255: `ResumeContractTest.test_replay_never_leaks_seq_into_frame_payloads(self)`
  - L1274: `SubscriptionLifecycleTest.setUp(self)`
  - L1286: `SubscriptionLifecycleTest._subs(app)`
  - L1289: `SubscriptionLifecycleTest.test_no_subscription_without_clients(self)`
  - L1293: `SubscriptionLifecycleTest.test_subscribe_on_first_client_and_release_on_last(self)`
  - L1308: `SubscriptionLifecycleTest.test_bus_subscription_reaches_channels(self)`
  - L1325: `SubscriptionLifecycleTest.test_dispose_is_idempotent(self)`
  - L1340: `UserConfirmRoundTripTest.setUp(self)`
  - L1361: `UserConfirmRoundTripTest.test_choice_is_filled_back_as_the_tool_result(self)`
  - L1394: `UserConfirmRoundTripTest.test_cancel_posts_empty_confirm_and_submits_nothing(self)`
  - L1402: `UserConfirmRoundTripTest.test_write_gate_confirm_id_still_works(self)`
  - L1419: `UserConfirmRoundTripTest.test_confirm_id_and_text_together_do_both(self)`
  - L1431: `UserConfirmRoundTripTest.test_invalid_conversation_id_rejected(self)`
  - L1437: `UserConfirmRoundTripTest.test_mesh_failure_reports_error_without_raising(self)`
  - L1445: `UserConfirmRoundTripTest.test_agree_mints_approval_id_for_the_option(self)`
  - L1468: `UserConfirmRoundTripTest.test_reject_returns_disagree_and_stores_nothing(self)`
  - L1489: `UserConfirmRoundTripTest.test_confirm_text_does_not_answer_an_approval(self)`
  - L1509: `UiBundleTest.test_tool_tag_shows_final_state_immediately(self)`
  - L1530: `UiBundleTest.test_reasoning_stays_out_of_the_chat_area(self)`
  - L1551: `UiBundleTest.test_llm_call_start_opens_a_step_card(self)`
  - L1578: `UiBundleTest.test_each_model_call_opens_its_own_card(self)`
  - L1592: `UiBundleTest.test_plugin_event_bridges(self)`
  - L1598: `UiBundleTest.test_inline_html_has_no_placeholders_left(self)`
  - L1605: `UiBundleTest.test_inline_html_contains_all_five_scripts(self)`
  - L1624: `UiBundleTest.test_light_hljs_sheet_is_scoped(self)`
  - L1646: `HistoryAttachmentReplayTest._events(self)`
  - L1663: `HistoryAttachmentReplayTest._events_inline_multimodal(self)`
  - L1675: `HistoryAttachmentReplayTest.test_history_items_carry_compaction_record(self)`
  - L1692: `HistoryAttachmentReplayTest.test_history_tool_item_carries_elapsed_seconds(self)`
  - L1704: `HistoryAttachmentReplayTest.test_history_items_carry_attachments_and_had_images(self)`
  - L1719: `HistoryAttachmentReplayTest.test_history_tool_done_keeps_images(self)`
  - L1740: `HistoryAttachmentReplayTest.test_history_tool_canceled_stays_distinct_from_failed(self)`
  - L1751: `HistoryAttachmentReplayTest.test_history_replays_each_reasoning_before_its_tools(self)`
  - L1780: `HistoryAttachmentReplayTest.test_history_prefers_reasoning_time(self)`
  - L1794: `HistoryAttachmentReplayTest.test_attachment_id_is_recomputable(self)`
  - L1802: `HistoryAttachmentReplayTest.test_inline_multimodal_content_is_also_accepted(self)`
  - L1811: `HistoryAttachmentReplayTest.test_plain_text_message_is_unaffected(self)`

### A.438 `tests/test_cli_shell.py`

- 类型：Python
- 行数：358
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：交互壳（shell/chat.py）装配测试 —— 会话门控解析。
- 导入：`__future__`, `builtins`, `io`, `sys`, `tempfile`, `unittest`, `contextlib`, `pathlib`, `unittest`, `agent.app`, `agent.core.events`, `agent.core.session_context`, `agent.core.tool_call`, `agent.shell.cli`, `agent.shell.cli.interactive`
- 顶层符号：
  - L31: `class ChatGateWiringTest(unittest.TestCase)`
  - L66: `class ChatConfirmRoundTripTest(unittest.TestCase)`
  - L143: `class ChatExitReleaseTest(unittest.TestCase)`
  - L207: `class InvalidSessionCliTest(unittest.TestCase)`
  - L229: `class ExplicitReleaseTest(unittest.TestCase)`
  - L302: `class ChatArgParsingTest(unittest.TestCase)`
  - L338: `class ChatToolEventTest(unittest.TestCase)`
- 类成员：
  - L34: `ChatGateWiringTest.setUp(self)`
  - L41: `ChatGateWiringTest.test_build_session_returns_named_conversation(self)`
  - L46: `ChatGateWiringTest.test_gate_is_the_conversation_gate_not_default_bucket(self)`
  - L52: `ChatGateWiringTest.test_engine_runs_on_same_conversation_id(self)`
  - L56: `ChatGateWiringTest.test_build_session_uses_shared_runner_engine(self)`
  - L69: `ChatConfirmRoundTripTest.setUp(self)`
  - L77: `ChatConfirmRoundTripTest._call(self, name, arguments, cid)`
  - L90: `ChatConfirmRoundTripTest._confirm_yes(self, gate, name, confirm_id, args)`
  - L99: `ChatConfirmRoundTripTest.test_shell_confirm_releases_preview_and_commit_lands(self)`
  - L119: `ChatConfirmRoundTripTest.test_default_bucket_gate_cannot_confirm_named_session(self)`
  - L137: `ChatConfirmRoundTripTest.test_preview_tool_names_include_write_path_tools(self)`
  - L145: `ChatExitReleaseTest.setUp(self)`
  - L159: `ChatExitReleaseTest._run_main_with_stubbed_build(self)`
  - L175: `ChatExitReleaseTest.test_main_releases_session_on_exit(self)`
  - L182: `ChatExitReleaseTest.test_main_prints_session_on_exit(self)`
  - L188: `ChatExitReleaseTest.test_released_session_reparses_clean(self)`
  - L208: `InvalidSessionCliTest.test_invalid_session_returns_clean_error(self)`
  - L232: `ExplicitReleaseTest.test_release_drops_only_that_conversation(self)`
  - L245: `ExplicitReleaseTest.test_web_release_conversation_reduces_active_count(self)`
  - L267: `ExplicitReleaseTest.test_release_unknown_and_blank_are_safe(self)`
  - L276: `ExplicitReleaseTest.test_close_all_clears_registry(self)`
  - L285: `ExplicitReleaseTest.test_release_does_not_touch_persisted_records(self)`
  - L305: `ChatArgParsingTest.test_help_exits_before_building_app(self)`
  - L319: `ChatArgParsingTest.test_session_and_text_are_parsed(self)`
  - L326: `ChatArgParsingTest.test_build_session_accepts_parsed_args(self)`
  - L341: `ChatToolEventTest.test_success_is_not_reported_as_failure(self)`

### A.439 `tests/test_command_tools.py`

- 类型：Python
- 行数：394
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：命令工具测试：run_command / python_inline + command_safety 机制。
- 导入：`__future__`, `os`, `subprocess`, `sys`, `tempfile`, `unittest`, `pathlib`, `agent.app`, `agent.capabilities.builtin.command_tools`, `agent.core.session_scope`, `agent.core.tool_call`, `agent.mechanisms`
- 顶层符号：
  - L26: `def _norm(path_text)`
  - L30: `class CommandSafetyUnitTest(unittest.TestCase)`
  - L135: `class CommandToolsTest(unittest.TestCase)`
  - L218: `class PythonInlineTest(unittest.TestCase)`
  - L275: `class CancelKillsProcessTest(unittest.TestCase)`
  - L342: `class CancelWiringTest(unittest.TestCase)`
- 类成员：
  - L33: `CommandSafetyUnitTest.test_blacklist_del_with_advice(self)`
  - L39: `CommandSafetyUnitTest.test_blacklist_path_and_exe(self)`
  - L43: `CommandSafetyUnitTest.test_blacklist_multiword(self)`
  - L47: `CommandSafetyUnitTest.test_blacklist_nested_shell_wrappers(self)`
  - L62: `CommandSafetyUnitTest.test_blacklist_disk_and_acl(self)`
  - L66: `CommandSafetyUnitTest.test_content_base64(self)`
  - L70: `CommandSafetyUnitTest.test_content_redirect_source(self)`
  - L75: `CommandSafetyUnitTest.test_content_sed_i(self)`
  - L79: `CommandSafetyUnitTest.test_safe_mode_chars(self)`
  - L86: `CommandSafetyUnitTest.test_decode_output_gbk(self)`
  - L91: `CommandSafetyUnitTest.test_sanitize_ansi_and_cr(self)`
  - L97: `CommandSafetyUnitTest.test_sanitize_blank_collapse_and_truncate(self)`
  - L104: `CommandSafetyUnitTest.test_resolve_shell(self)`
  - L115: `CommandSafetyUnitTest.test_process_registry_and_kill(self)`
  - L138: `CommandToolsTest.setUp(self)`
  - L146: `CommandToolsTest._call(self, name, arguments)`
  - L151: `CommandToolsTest.test_run_echo(self)`
  - L158: `CommandToolsTest.test_run_blacklisted(self)`
  - L165: `CommandToolsTest.test_run_blacklisted_even_safe_mode_off(self)`
  - L171: `CommandToolsTest.test_run_safe_mode_blocks_chars(self)`
  - L177: `CommandToolsTest.test_run_safe_mode_off_allows_chain(self)`
  - L184: `CommandToolsTest.test_run_script_content_check(self)`
  - L193: `CommandToolsTest.test_run_exit_code(self)`
  - L201: `CommandToolsTest.test_run_timeout_kills(self)`
  - L211: `CommandToolsTest.test_run_cwd(self)`
  - L221: `PythonInlineTest.setUp(self)`
  - L229: `PythonInlineTest._call(self, name, arguments)`
  - L234: `PythonInlineTest.test_inline_prints(self)`
  - L240: `PythonInlineTest.test_inline_prints_push_progress(self)`
  - L251: `PythonInlineTest.test_inline_exception_captured(self)`
  - L257: `PythonInlineTest.test_inline_system_exit(self)`
  - L262: `PythonInlineTest.test_inline_cwd_and_restore(self)`
  - L283: `CancelKillsProcessTest.test_cancel_kills_the_child_process_and_returns_quickly(self)`
  - L349: `CancelWiringTest.test_tool_port_passes_the_cancel_check_into_the_scope(self)`
  - L387: `CancelWiringTest.test_scope_without_cancel_check_is_safe(self)`

### A.440 `tests/test_compaction_prefix.py`

- 类型：Python
- 行数：115
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：压缩请求必须复用上一次正常请求的精确前缀。
- 导入：`__future__`, `unittest`, `types`, `agent.core.model_call`, `agent.core.modules.model_mod`, `agent.mechanisms.compaction.compactor`, `agent.mechanisms.context`, `agent.mechanisms.context.hooks`
- 顶层符号：
  - L15: `class _Log()`
  - L20: `class _Tools()`
  - L25: `class _Spy()`
  - L36: `class _SnapshotSink()`
  - L52: `class CompactionPrefixTest(unittest.TestCase)`
- 类成员：
  - L16: `_Log.derive_request_messages(self)`
  - L21: `_Tools.schemas(self)`
  - L26: `_Spy.__init__(self, text)`
  - L30: `_Spy.stream(self, request)`
  - L37: `_SnapshotSink.__init__(self)`
  - L42: `_SnapshotSink.remember_sent_request(self, messages, prefix, tools)`
  - L48: `_SnapshotSink.summary_token_threshold(self)`
  - L53: `CompactionPrefixTest.test_model_module_records_prefix_before_hook_tail(self)`
  - L67: `CompactionPrefixTest.test_compaction_request_is_prefix_plus_user_instruction(self)`
  - L95: `CompactionPrefixTest.test_no_snapshot_falls_back_without_claiming_hit(self)`

### A.441 `tests/test_compaction_slots.py`

- 类型：Python
- 行数：76
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：压缩 build-context 插口的替换与回退测试。
- 导入：`__future__`, `unittest`, `agent.capabilities.slot_registry`, `agent.mechanisms.compaction.compactor`
- 顶层符号：
  - L16: `class CompactionSlotTest(unittest.TestCase)`
- 类成员：
  - L17: `CompactionSlotTest.test_replace_build_context_and_restore(self)`
  - L35: `CompactionSlotTest.test_instances_do_not_share_default_policy_or_summarizer(self)`
  - L58: `CompactionSlotTest.test_replace_summarize_and_policy(self)`

### A.442 `tests/test_concurrency.py`

- 类型：Python
- 行数：378
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：并发 / 争用测试。
- 导入：`__future__`, `importlib`, `importlib.util`, `sys`, `threading`, `time`, `types`, `unittest`, `pathlib`, `agent.capabilities.model_catalog`, `agent.mechanisms.context`, `agent.mechanisms.live_state`, `agent.mechanisms.quality.pending`
- 顶层符号：
  - L31: `def _run_threads(target, count)`
  - L53: `class PendingStoreContentionTest(unittest.TestCase)`
  - L123: `class ContextSourcesContentionTest(unittest.TestCase)`
  - L177: `class LiveStateContentionTest(unittest.TestCase)`
  - L210: `class ModelCatalogContentionTest(unittest.TestCase)`
  - L289: `def _load_ai_cosplay_modules()`
  - L313: `class AICosplayRuntimeContentionTest(unittest.TestCase)`
- 类成员：
  - L56: `PendingStoreContentionTest.test_capacity_is_never_exceeded(self)`
  - L68: `PendingStoreContentionTest.test_same_path_keeps_exactly_one_latest(self)`
  - L83: `PendingStoreContentionTest.test_take_is_exactly_once(self)`
  - L99: `PendingStoreContentionTest.test_records_snapshot_cannot_mutate_confirmed(self)`
  - L111: `PendingStoreContentionTest.test_confirm_is_visible_to_concurrent_peek(self)`
  - L126: `ContextSourcesContentionTest.test_register_and_dispose_are_balanced(self)`
  - L148: `ContextSourcesContentionTest.test_collect_sees_a_consistent_snapshot(self)`
  - L180: `LiveStateContentionTest.test_distinct_conversations_do_not_interfere(self)`
  - L192: `LiveStateContentionTest.test_same_conversation_writes_stay_well_formed(self)`
  - L220: `ModelCatalogContentionTest._batch(cls, prefix, count)`
  - L229: `ModelCatalogContentionTest.test_snapshot_is_never_mixed_during_replacement(self)`
  - L260: `ModelCatalogContentionTest.test_provider_cache_is_keyed_by_entry_fingerprint(self)`
  - L316: `AICosplayRuntimeContentionTest.test_many_threads_keep_every_segment(self)`

### A.443 `tests/test_config_values.py`

- 类型：Python
- 行数：33
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：配置读取的数值回退与压缩阈值边界。
- 导入：`__future__`, `tempfile`, `unittest`, `pathlib`, `agent.config`
- 顶层符号：
  - L12: `class ConfigValueFallbackTest(unittest.TestCase)`
- 类成员：
  - L13: `ConfigValueFallbackTest._ini(self, text)`
  - L21: `ConfigValueFallbackTest.test_compression_threshold_coerces_bool_and_strings(self)`
  - L26: `ConfigValueFallbackTest.test_bad_numeric_values_fall_back_to_defaults(self)`

### A.444 `tests/test_context_assembly.py`

- 类型：Python
- 行数：2118
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：上下文组装与压缩：逐条穷举验收。
- 导入：`__future__`, `os`, `sys`, `unittest`, `pathlib`, `agent.core.model_call`, `agent.core.modules.mode_note`, `agent.mechanisms.compaction.compactor`, `agent.mechanisms.context`, `random`, `agent.mechanisms.context`, `agent.core.model_call`, `agent.mechanisms.context`, `shutil`, `tempfile`, `plugins.skills.library`, `agent.mechanisms.context`
- 顶层符号：
  - L56: `def short(m)`
  - L93: `def shape(messages)`
  - L98: `class _Spy()`
  - L112: `class _Case(unittest.TestCase)`
  - L132: `def make_pipe()`
  - L149: `def dlg(n)`
  - L162: `class AssemblyShape(_Case)`
  - L297: `class TailShape(_Case)`
  - L373: `class CompactionContext(_Case)`
  - L501: `class StripRules(_Case)`
  - L598: `class CompactionLoop(_Case)`
  - L769: `class Invariants(_Case)`
  - L880: `def conv(turns)`
  - L893: `class TurnAtomicity(_Case)`
  - L941: `def _random_conv(rng)`
  - L957: `class RandomShapeInvariants(_Case)`
  - L1010: `class _Spy2()`
  - L1020: `def _fat_turn(tools, pad, turns)`
  - L1034: `def _run_compaction(msgs)`
  - L1067: `class MaskIsHard(_Case)`
  - L1108: `class MaskSurvivesOverflow(_Case)`
  - L1220: `def _skill_tree()`
  - L1237: `class SkillProgressiveDisclosure(_Case)`
  - L1291: `class SkillInjectionIntoRequest(_Case)`
  - L1384: `class SegmentTokens(_Case)`
  - L1429: `class LayoutPayload(_Case)`
  - L1486: `class LayoutFromMessages(_Case)`
  - L1553: `class LayoutWithHead(_Case)`
  - L1626: `class SegmentKeysAndCounts(_Case)`
  - L1652: `class SegmentCountSemantics(_Case)`
  - L1680: `class SegmentOrderMatchesAssembly(_Case)`
  - L1718: `class SourceOrderDeclaration(_Case)`
  - L1760: `class OrdinaryRequestNeverRewritesHistory(unittest.TestCase)`
  - L1816: `class SegmentFieldParity(unittest.TestCase)`
  - L1853: `class RemainingCapacityTest(unittest.TestCase)`
  - L1964: `class PluginSegmentCountAlignmentTest(unittest.TestCase)`
  - L2010: `class PluginSegmentsImmutableTest(unittest.TestCase)`
  - L2058: `class ReasoningReplayBudgetTest(unittest.TestCase)`
- 类成员：
  - L99: `_Spy.__init__(self, text)`
  - L103: `_Spy.stream(self, request)`
  - L115: `_Case.check(self, label, expected, actual)`
  - L122: `_Case.check_true(self, label, actual)`
  - L165: `AssemblyShape.test_full_headers_come_first_in_order(self)`
  - L170: `AssemblyShape.test_headers_include_summaries_after_kb(self)`
  - L176: `AssemblyShape.test_summary_order_follows_input_order(self)`
  - L182: `AssemblyShape.test_dialogue_keeps_fact_order(self)`
  - L187: `AssemblyShape.test_assembles_appends_tail(self)`
  - L196: `AssemblyShape.test_assembles_without_tail(self)`
  - L202: `AssemblyShape.test_assembles_ignores_non_dict_tail(self)`
  - L208: `AssemblyShape.test_less_headers_still_ordered(self)`
  - L214: `AssemblyShape.test_empty_everything(self)`
  - L218: `AssemblyShape.test_assembles_is_detached_from_pipeline(self)`
  - L226: `AssemblyShape.test_header_change_is_visible_immediately(self)`
  - L233: `AssemblyShape.test_summary_replacement_takes_effect(self)`
  - L240: `AssemblyShape.test_summary_can_be_cleared(self)`
  - L246: `AssemblyShape.test_two_summaries_both_kept(self)`
  - L252: `AssemblyShape.test_dialogue_with_tool_pair(self)`
  - L261: `AssemblyShape.test_set_dialogue_replaces_previous(self)`
  - L267: `AssemblyShape.test_covered_end_drops_prefix(self)`
  - L274: `AssemblyShape.test_covered_end_zero_keeps_all(self)`
  - L281: `AssemblyShape.test_covered_end_beyond_length(self)`
  - L286: `AssemblyShape.test_mode_chunk_never_in_assembly(self)`
  - L300: `TailShape._msgs(self, mode, new_input)`
  - L309: `TailShape.test_mode_is_last(self)`
  - L315: `TailShape.test_mode_is_system_role(self)`
  - L319: `TailShape.test_new_input_is_user_role(self)`
  - L323: `TailShape.test_no_mode_means_input_is_last(self)`
  - L329: `TailShape.test_no_new_input_means_mode_follows_dialogue(self)`
  - L335: `TailShape.test_neither(self)`
  - L340: `TailShape.test_tool_result_tail(self)`
  - L351: `TailShape.test_mode_text_is_exact(self)`
  - L355: `TailShape.test_plan_mode_text_is_exact(self)`
  - L361: `TailShape.test_mode_swap_changes_only_the_last_entry(self)`
  - L376: `CompactionContext._request(self)`
  - L408: `CompactionContext.test_user_path_request_shape(self)`
  - L414: `CompactionContext.test_user_path_drops_new_input(self)`
  - L420: `CompactionContext.test_user_path_drops_mode(self)`
  - L426: `CompactionContext.test_instruction_is_last_and_user(self)`
  - L431: `CompactionContext.test_instruction_appears_once(self)`
  - L436: `CompactionContext.test_prefix_equals_normal_request_minus_last_two(self)`
  - L440: `CompactionContext.test_tool_path_request_shape(self)`
  - L446: `CompactionContext.test_tool_path_prefix_equals_normal_minus_last_one(self)`
  - L451: `CompactionContext.test_mode_change_does_not_affect_request(self)`
  - L457: `CompactionContext.test_summary_present_in_head(self)`
  - L463: `CompactionContext.test_no_new_input_path(self)`
  - L470: `CompactionContext.test_system_field_is_carried(self)`
  - L483: `CompactionContext.test_tools_are_forwarded(self)`
  - L504: `StripRules._strip_new(self, msgs)`
  - L507: `StripRules._strip_mode(self, msgs, note)`
  - L510: `StripRules.test_new_input_removed_when_last(self)`
  - L515: `StripRules.test_new_input_removed_before_mode(self)`
  - L522: `StripRules.test_previous_reply_is_kept(self)`
  - L529: `StripRules.test_tool_result_is_kept(self)`
  - L539: `StripRules.test_only_last_user_removed(self)`
  - L544: `StripRules.test_empty(self)`
  - L547: `StripRules.test_non_dict_entry(self)`
  - L553: `StripRules.test_mode_removed_by_exact_text(self)`
  - L558: `StripRules.test_mode_removed_by_marker_fallback(self)`
  - L564: `StripRules.test_system_prompt_never_stripped(self)`
  - L568: `StripRules.test_summary_never_stripped(self)`
  - L572: `StripRules.test_kb_never_stripped(self)`
  - L576: `StripRules.test_mode_in_the_middle_untouched(self)`
  - L581: `StripRules.test_two_trailing_systems_both_stripped(self)`
  - L587: `StripRules.test_empty_mode_note_and_no_marker(self)`
  - L601: `CompactionLoop._run(self)`
  - L620: `CompactionLoop.test_report_keys(self)`
  - L627: `CompactionLoop.test_covered_end_advances(self)`
  - L632: `CompactionLoop.test_compressed_count_matches_step(self)`
  - L638: `CompactionLoop.test_summary_text_is_current_body(self)`
  - L642: `CompactionLoop.test_summary_is_single_current_body(self)`
  - L646: `CompactionLoop.test_summary_text_comes_from_model(self)`
  - L649: `CompactionLoop.test_second_compaction_replaces_summary(self)`
  - L654: `CompactionLoop.test_summary_messages_are_user_checkpoint(self)`
  - L661: `CompactionLoop.test_reassembled_request_shape(self)`
  - L673: `CompactionLoop.test_below_threshold_no_request(self)`
  - L677: `CompactionLoop.test_no_context_returns_none(self)`
  - L682: `CompactionLoop.test_empty_dialogue_returns_none(self)`
  - L688: `CompactionLoop.test_degenerate_summary_is_rejected(self)`
  - L697: `CompactionLoop.test_provider_failure_is_released(self)`
  - L711: `CompactionLoop.test_no_summarize_fn_returns_none(self)`
  - L719: `CompactionLoop.test_restore_from_events_rebuilds_state(self)`
  - L729: `CompactionLoop.test_restore_ignores_backwards_covered_end(self)`
  - L738: `CompactionLoop.test_restore_ignores_other_events(self)`
  - L745: `CompactionLoop.test_view_messages_drops_covered(self)`
  - L751: `CompactionLoop.test_pending_does_not_enter_range(self)`
  - L772: `Invariants._all_requests(self)`
  - L803: `Invariants.test_every_request_has_system_prompt(self)`
  - L809: `Invariants.test_every_request_has_all_skills(self)`
  - L816: `Invariants.test_every_request_has_all_kb(self)`
  - L822: `Invariants.test_no_request_has_mode(self)`
  - L828: `Invariants.test_every_request_ends_with_instruction(self)`
  - L833: `Invariants.test_head_prefix_is_identical_across_requests(self)`
  - L843: `Invariants.test_summaries_survive_every_request(self)`
  - L850: `Invariants.test_instruction_text_is_stable(self)`
  - L896: `TurnAtomicity.test_turn_starts(self)`
  - L900: `TurnAtomicity.test_turn_spans(self)`
  - L904: `TurnAtomicity.test_floor_on_boundary_is_identity(self)`
  - L909: `TurnAtomicity.test_floor_inside_turn_goes_back(self)`
  - L914: `TurnAtomicity.test_floor_before_first_user(self)`
  - L918: `TurnAtomicity.test_floor_beyond_end(self)`
  - L922: `TurnAtomicity.test_is_boundary(self)`
  - L927: `TurnAtomicity.test_tool_chain_balanced_ok(self)`
  - L931: `TurnAtomicity.test_tool_chain_balanced_missing_result(self)`
  - L935: `TurnAtomicity.test_tool_chain_balanced_orphan_result(self)`
  - L966: `RandomShapeInvariants.test_compaction_range_never_splits_a_turn(self)`
  - L985: `RandomShapeInvariants.test_compaction_range_tool_chain_always_closed(self)`
  - L1011: `_Spy2.__init__(self)`
  - L1014: `_Spy2.stream(self, request)`
  - L1070: `MaskIsHard.test_excerpt_never_touches_the_masked_tail(self)`
  - L1082: `MaskIsHard.test_excerpt_starts_at_zero(self)`
  - L1086: `MaskIsHard.test_single_turn_is_compressed_when_nothing_else_can_be(self)`
  - L1094: `MaskIsHard.test_region_excludes_every_system_message(self)`
  - L1102: `MaskIsHard.test_region_tool_chain_closed(self)`
  - L1111: `MaskSurvivesOverflow._msgs(self)`
  - L1124: `MaskSurvivesOverflow.test_masked_last_turn_stays_when_it_is_huge(self)`
  - L1143: `MaskSurvivesOverflow.test_reserve_two_keeps_two_turns(self)`
  - L1156: `MaskSurvivesOverflow.test_reserve_zero_is_lifted_to_one(self)`
  - L1161: `MaskSurvivesOverflow.test_only_masked_turns_still_get_compressed(self)`
  - L1176: `MaskSurvivesOverflow.test_mask_invariant_over_random_shapes(self)`
  - L1240: `SkillProgressiveDisclosure.setUp(self)`
  - L1245: `SkillProgressiveDisclosure.test_registry_lists_names_and_descriptions(self)`
  - L1251: `SkillProgressiveDisclosure.test_registry_excludes_auto_load_skill(self)`
  - L1255: `SkillProgressiveDisclosure.test_registry_excludes_skill_bodies(self)`
  - L1260: `SkillProgressiveDisclosure.test_registry_is_absent_when_no_skills(self)`
  - L1267: `SkillProgressiveDisclosure.test_auto_load_messages_carry_bodies(self)`
  - L1274: `SkillProgressiveDisclosure.test_auto_load_excludes_normal_skills(self)`
  - L1278: `SkillProgressiveDisclosure.test_auto_load_empty_when_no_auto_load_dir(self)`
  - L1286: `SkillProgressiveDisclosure.test_skillsr_lists_normal_skills_only(self)`
  - L1294: `SkillInjectionIntoRequest.setUp(self)`
  - L1299: `SkillInjectionIntoRequest._segments(self)`
  - L1303: `SkillInjectionIntoRequest._pipeline(self)`
  - L1309: `SkillInjectionIntoRequest.test_plugin_segments_sit_after_system_prompt(self)`
  - L1319: `SkillInjectionIntoRequest.test_summary_sits_after_plugin_segments(self)`
  - L1327: `SkillInjectionIntoRequest.test_plugin_segments_used_by_compaction_request(self)`
  - L1341: `SkillInjectionIntoRequest.test_plugin_segments_are_not_duplicated_across_passes(self)`
  - L1351: `SkillInjectionIntoRequest.test_empty_segments_leave_head_empty(self)`
  - L1359: `SkillInjectionIntoRequest.test_segment_stats_follow_the_plugin(self)`
  - L1387: `SegmentTokens._pipe(self)`
  - L1399: `SegmentTokens.test_system_segment_matches_its_message(self)`
  - L1408: `SegmentTokens.test_summary_segment_counts_both_summaries(self)`
  - L1413: `SegmentTokens.test_dialogue_split_into_two_segments(self)`
  - L1418: `SegmentTokens.test_segments_sum_equals_assembled_total(self)`
  - L1432: `LayoutPayload._pipe(self)`
  - L1438: `LayoutPayload.test_payload_shape(self)`
  - L1445: `LayoutPayload.test_last_segment_is_remaining(self)`
  - L1450: `LayoutPayload.test_tail_becomes_mode_segment(self)`
  - L1459: `LayoutPayload.test_no_tail_means_no_mode_segment(self)`
  - L1465: `LayoutPayload.test_pct_sums_to_100(self)`
  - L1472: `LayoutPayload.test_budget_never_below_used(self)`
  - L1479: `LayoutPayload.test_total_matches_segments_minus_remaining(self)`
  - L1489: `LayoutFromMessages._msgs(self)`
  - L1498: `LayoutFromMessages.test_head_first_message_is_the_system_prompt(self)`
  - L1504: `LayoutFromMessages.test_given_system_text_is_used_and_not_double_counted(self)`
  - L1513: `LayoutFromMessages.test_last_head_message_is_the_summary(self)`
  - L1521: `LayoutFromMessages.test_dialogue_starts_at_the_first_user(self)`
  - L1525: `LayoutFromMessages.test_mode_is_split_out(self)`
  - L1529: `LayoutFromMessages.test_no_mode_means_no_mode_segment(self)`
  - L1534: `LayoutFromMessages.test_remaining_is_last(self)`
  - L1538: `LayoutFromMessages.test_total_equals_segments_sum(self)`
  - L1543: `LayoutFromMessages.test_mode_not_counted_as_dialogue(self)`
  - L1548: `LayoutFromMessages.test_empty_input(self)`
  - L1556: `LayoutWithHead._head(self)`
  - L1565: `LayoutWithHead._segments(self)`
  - L1569: `LayoutWithHead._layout(self, messages)`
  - L1573: `LayoutWithHead.test_plugin_segments_are_one_row_each(self)`
  - L1587: `LayoutWithHead.test_same_key_and_label_are_merged_in_layout(self)`
  - L1602: `LayoutWithHead.test_dialogue_does_not_include_head(self)`
  - L1606: `LayoutWithHead.test_mode_splits_from_dialogue(self)`
  - L1612: `LayoutWithHead.test_without_head_falls_back_to_position(self)`
  - L1621: `LayoutWithHead.test_total_equals_sum_without_remaining(self)`
  - L1629: `SegmentKeysAndCounts.test_keys_and_labels(self)`
  - L1641: `SegmentKeysAndCounts.test_plugin_may_declare_more_than_one_segment(self)`
  - L1655: `SegmentCountSemantics.test_system_prompt_counts_messages(self)`
  - L1663: `SegmentCountSemantics.test_dialogue_counts_user_turns_not_messages(self)`
  - L1675: `SegmentCountSemantics.test_layout_from_messages_counts_turns_too(self)`
  - L1683: `SegmentOrderMatchesAssembly._pipe(self)`
  - L1692: `SegmentOrderMatchesAssembly.test_header_order_is_system_plugins_summary(self)`
  - L1698: `SegmentOrderMatchesAssembly.test_segment_order_matches_header_order(self)`
  - L1705: `SegmentOrderMatchesAssembly.test_summary_sits_before_dialogue(self)`
  - L1709: `SegmentOrderMatchesAssembly.test_layout_payload_keeps_the_same_order(self)`
  - L1721: `SourceOrderDeclaration._sources(self, pairs)`
  - L1729: `SourceOrderDeclaration.test_rank_beats_registration(self)`
  - L1735: `SourceOrderDeclaration.test_same_rank_keeps_registration_order(self)`
  - L1740: `SourceOrderDeclaration.test_no_rank_sorts_last(self)`
  - L1746: `SourceOrderDeclaration.test_kernel_pipeline_follows_the_same_order(self)`
  - L1763: `OrdinaryRequestNeverRewritesHistory._conv(self, turns)`
  - L1775: `OrdinaryRequestNeverRewritesHistory.test_tool_traffic_survives_set_dialogue(self)`
  - L1787: `OrdinaryRequestNeverRewritesHistory.test_adding_a_turn_does_not_touch_earlier_messages(self)`
  - L1801: `OrdinaryRequestNeverRewritesHistory.test_compression_only_drops_a_prefix(self)`
  - L1822: `SegmentFieldParity.test_both_paths_expose_the_same_fields(self)`
  - L1845: `SegmentFieldParity.test_layout_event_forwards_every_field(self)`
  - L1856: `RemainingCapacityTest.test_snapshot_carries_the_budget(self)`
  - L1870: `RemainingCapacityTest.test_budget_zero_would_make_remaining_zero(self)`
  - L1880: `RemainingCapacityTest.test_old_snapshot_is_rescaled_on_read(self)`
  - L1920: `RemainingCapacityTest.test_overlay_merges_same_key_and_label(self)`
  - L1950: `RemainingCapacityTest.test_rescale_falls_back_when_budget_unknown(self)`
  - L1967: `PluginSegmentCountAlignmentTest.test_collect_segments_counts_match_items(self)`
  - L1985: `PluginSegmentCountAlignmentTest.test_missing_reported_count_falls_back_to_one(self)`
  - L1994: `PluginSegmentCountAlignmentTest.test_short_count_table_does_not_borrow_neighbours(self)`
  - L2013: `PluginSegmentsImmutableTest._segments(self)`
  - L2020: `PluginSegmentsImmutableTest.test_source_lists_are_copied(self)`
  - L2027: `PluginSegmentsImmutableTest.test_containers_are_tuples(self)`
  - L2033: `PluginSegmentsImmutableTest.test_assignment_is_rejected(self)`
  - L2040: `PluginSegmentsImmutableTest.test_tuple_containers_reject_mutation(self)`
  - L2047: `PluginSegmentsImmutableTest.test_wrong_arity_is_rejected_loudly(self)`
  - L2061: `ReasoningReplayBudgetTest._long(self, steps)`
  - L2064: `ReasoningReplayBudgetTest.test_negative_keeps_everything(self)`
  - L2070: `ReasoningReplayBudgetTest.test_zero_drops_everything(self)`
  - L2075: `ReasoningReplayBudgetTest.test_positive_keeps_both_ends_and_marks_the_gap(self)`
  - L2086: `ReasoningReplayBudgetTest.test_short_text_untouched(self)`
  - L2091: `ReasoningReplayBudgetTest.test_messages_clip_does_not_mutate_input(self)`
  - L2100: `ReasoningReplayBudgetTest.test_dialogue_segment_uses_the_budget(self)`
  - L2112: `ReasoningReplayBudgetTest.test_config_default_matches_constant(self)`

### A.445 `tests/test_context_config_wiring.py`

- 类型：Python
- 行数：104
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：守住"配置项必须真的传到管线"：生产装配路径逐项核对。
- 导入：`__future__`, `sys`, `unittest`, `pathlib`, `tests.testkit`
- 顶层符号：
  - L18: `class ContextFactoryCarriesEveryContextSettingTest(unittest.TestCase)`
  - L65: `class SegmentEventCarriesTheWindowTest(unittest.TestCase)`
- 类成员：
  - L21: `ContextFactoryCarriesEveryContextSettingTest.setUp(self)`
  - L24: `ContextFactoryCarriesEveryContextSettingTest.test_factory_passes_every_pipeline_setting(self)`
  - L49: `ContextFactoryCarriesEveryContextSettingTest.test_pipeline_gets_the_configured_values(self)`
  - L68: `SegmentEventCarriesTheWindowTest.setUp(self)`
  - L71: `SegmentEventCarriesTheWindowTest.test_event_has_window_and_budget(self)`

### A.446 `tests/test_context_dump.py`

- 类型：Python
- 行数：111
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：开发者上下文导出：复用真实装配，不调用模型。
- 导入：`__future__`, `sys`, `tempfile`, `unittest`, `pathlib`, `agent.app`, `agent.core.model_call`, `agent.mechanisms.session_store`, `agent.shell.context_dump`, `agent.shell.service_keys`
- 顶层符号：
  - L20: `class _Provider()`
  - L32: `class ContextDumpTest(unittest.TestCase)`
- 类成员：
  - L23: `_Provider.__init__(self)`
  - L26: `_Provider.stream(self, request)`
  - L33: `ContextDumpTest.test_snapshot_uses_real_assembly_and_does_not_call_model(self)`
  - L61: `ContextDumpTest.test_snapshot_reports_todo_progress_when_list_exists(self)`
  - L93: `ContextDumpTest.test_missing_conversation_is_an_error(self)`

### A.447 `tests/test_context_dump_skill.py`

- 类型：Python
- 行数：28
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：内置 Skills：上下文导出指导。
- 导入：`__future__`, `unittest`, `pathlib`, `plugins.skills.library`
- 顶层符号：
  - L13: `class ContextDumpSkillTest(unittest.TestCase)`
- 类成员：
  - L14: `ContextDumpSkillTest.setUp(self)`
  - L17: `ContextDumpSkillTest.test_skill_is_listed_and_readable(self)`

### A.448 `tests/test_context_hooks.py`

- 类型：Python
- 行数：45
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：完整上下文拼装钩子。
- 导入：`__future__`, `unittest`, `agent.mechanisms.context.hooks`
- 顶层符号：
  - L10: `class ContextAssemblyHooksTest(unittest.TestCase)`
- 类成员：
  - L11: `ContextAssemblyHooksTest.test_hook_receives_full_context_and_can_replace_it(self)`
  - L29: `ContextAssemblyHooksTest.test_invalid_result_is_ignored(self)`
  - L35: `ContextAssemblyHooksTest.test_hooks_run_in_order(self)`

### A.449 `tests/test_context_pipeline.py`

- 类型：Python
- 行数：281
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：ContextPipeline 测试。
- 导入：`__future__`, `sys`, `unittest`, `pathlib`, `typing`, `agent.mechanisms.context`
- 顶层符号：
  - L29: `def _msg(role, content)`
  - L32: `def _round()`
  - L38: `def _tool_call_msg(tc_id)`
  - L47: `class ChunksAndFlattenTest(unittest.TestCase)`
  - L90: `class ExcerptTest(unittest.TestCase)`
  - L124: `class MemoryAndEstimateTest(unittest.TestCase)`
  - L182: `class RebuildTest(unittest.TestCase)`
  - L194: `class DefaultConfigValues(unittest.TestCase)`
  - L224: `class MaxPassesConfigTest(unittest.TestCase)`
- 类成员：
  - L50: `ChunksAndFlattenTest.test_seven_chunks_order_and_add(self)`
  - L62: `ChunksAndFlattenTest.test_round_and_chunk_append_semantics(self)`
  - L75: `ChunksAndFlattenTest.test_flat_messages_to_user_rounds(self)`
  - L93: `ExcerptTest.test_adjust_back_extends_over_tool_chain(self)`
  - L114: `ExcerptTest.test_adjust_extends_end_for_open_results(self)`
  - L127: `MemoryAndEstimateTest.test_pending_mem_flow(self)`
  - L144: `MemoryAndEstimateTest.test_token_estimates(self)`
  - L161: `MemoryAndEstimateTest.test_round_count(self)`
  - L172: `MemoryAndEstimateTest.test_append_new_msg_and_append_msg(self)`
  - L185: `RebuildTest.test_rebuild_from_messages(self)`
  - L197: `DefaultConfigValues.test_summary_token_threshold_default(self)`
  - L204: `DefaultConfigValues.test_compactor_signature_matches_config(self)`
  - L216: `DefaultConfigValues.test_other_context_defaults(self)`
  - L227: `MaxPassesConfigTest.test_default_is_64(self)`
  - L238: `MaxPassesConfigTest.test_config_value_wins(self)`
  - L248: `MaxPassesConfigTest.test_bad_value_falls_back(self)`
  - L264: `MaxPassesConfigTest.test_app_carries_the_value(self)`
  - L271: `MaxPassesConfigTest.test_engine_carries_the_value(self)`

### A.450 `tests/test_context_plumbing.py`

- 类型：Python
- 行数：119
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：上下文贯通冒烟测试：工具往返内工具拿得到三级上下文。
- 导入：`__future__`, `unittest`, `typing`, `agent.core.context`, `agent.core.session_context`, `agent.core.session_scope`, `agent.core.tool_call`
- 顶层符号：
  - L18: `class _ProbeTool()`
  - L32: `class _Registry()`
  - L44: `class _FakeTurn()`
  - L53: `class ContextPlumbingTest(unittest.TestCase)`
- 类成员：
  - L25: `_ProbeTool.__init__(self)`
  - L28: `_ProbeTool.execute(self, arguments)`
  - L33: `_Registry.__init__(self, tool)`
  - L36: `_Registry.get(self, name)`
  - L39: `_Registry.names(self)`
  - L47: `_FakeTurn.__init__(self, app, session, cid)`
  - L56: `ContextPlumbingTest.setUp(self)`
  - L70: `ContextPlumbingTest.test_tool_sees_all_three_contexts(self)`
  - L85: `ContextPlumbingTest.test_service_lookup_from_tool_round(self)`
  - L92: `ContextPlumbingTest.test_live_state_reachable_from_tool_round(self)`
  - L102: `ContextPlumbingTest.test_context_does_not_leak_outside_the_call(self)`
  - L107: `ContextPlumbingTest.test_missing_contexts_degrade_instead_of_failing(self)`

### A.451 `tests/test_context_source_slots.py`

- 类型：Python
- 行数：89
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：上下文注入源的 slot 替换与回退测试。
- 导入：`__future__`, `unittest`, `agent.capabilities.plugin_context`, `agent.capabilities.registry`, `agent.capabilities.slot_registry`, `agent.mechanisms.context.sources`
- 顶层符号：
  - L18: `class ContextSourceSlotTest(unittest.TestCase)`
- 类成员：
  - L19: `ContextSourceSlotTest.setUp(self)`
  - L29: `ContextSourceSlotTest.test_replace_and_restore(self)`
  - L42: `ContextSourceSlotTest.test_duplicate_without_replace_rejected(self)`
  - L51: `ContextSourceSlotTest.test_source_can_be_added_again_after_dispose(self)`
  - L61: `ContextSourceSlotTest.test_replace_context_assembly(self)`
  - L72: `ContextSourceSlotTest.test_plugin_context_replace_does_not_duplicate_backend_path(self)`

### A.452 `tests/test_context_splice.py`

- 类型：Python
- 行数：223
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：恢复 = 往上下文末尾拼接工具结果。
- 导入：`__future__`, `json`, `tempfile`, `unittest`, `pathlib`, `typing`, `agent.core.events`, `agent.core.session_log`
- 顶层符号：
  - L26: `class ContextSpliceTest(unittest.TestCase)`
  - L154: `class ResumeSpliceNamingTest(unittest.TestCase)`
- 类成员：
  - L29: `ContextSpliceTest._suspended_rows(self)`
  - L39: `ContextSpliceTest.test_spliced_result_lands_exactly_after_the_tool_call(self)`
  - L63: `ContextSpliceTest.test_no_user_message_is_inserted_on_resume(self)`
  - L74: `ContextSpliceTest.test_stale_empty_input_in_old_records_is_tolerated(self)`
  - L93: `ContextSpliceTest.test_real_store_carries_the_splice(self)`
  - L119: `ContextSpliceTest.test_repeated_terminal_folds_to_one_tool_message(self)`
  - L163: `ResumeSpliceNamingTest.test_written_fact_name_is_the_one_kernel_consumes(self)`

### A.453 `tests/test_conversation_queue.py`

- 类型：Python
- 行数：100
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：会话待发送队列：状态机、附件与持久化。
- 导入：`__future__`, `base64`, `sys`, `tempfile`, `unittest`, `pathlib`, `agent.mechanisms.conversation_queue`
- 顶层符号：
  - L25: `class ConversationQueueTest(unittest.TestCase)`
- 类成员：
  - L28: `ConversationQueueTest.setUp(self)`
  - L33: `ConversationQueueTest.test_fifo_and_state(self)`
  - L44: `ConversationQueueTest.test_image_roundtrip_and_recall(self)`
  - L55: `ConversationQueueTest.test_draft_resubmit_preserves_agent_origin(self)`
  - L70: `ConversationQueueTest.test_claimed_cannot_be_recalled_or_cancelled(self)`
  - L78: `ConversationQueueTest.test_persistence_and_claimed_recovery(self)`
  - L87: `ConversationQueueTest.test_system_item_hidden_but_claimable(self)`

### A.454 `tests/test_core.py`

- 类型：Python
- 行数：1448
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：内核（`agent.core`）的端到端验证。
- 导入：`__future__`, `json`, `sys`, `tempfile`, `unittest`, `pathlib`, `typing`, `agent.core`, `agent.core.events`, `agent.core.model_call`, `agent.core.module`, `agent.core.session_log`, `agent.core.tool_call`, `agent.mechanisms.session_store`
- 顶层符号：
  - L39: `class ScriptedProvider()`
  - L72: `def _chunks(text, size)`
  - L75: `class _AskTool()`
  - L95: `class _EchoTool()`
  - L103: `class _Registry()`
  - L121: `class SessionLogViewIsolationTest(unittest.TestCase)`
  - L142: `class CoreHarness(unittest.TestCase)`
  - L214: `class BasicTurnTest(CoreHarness)`
  - L340: `class ToolLoopTest(CoreHarness)`
  - L383: `class SuspendResumeTest(CoreHarness)`
  - L482: `class SuspendBatchTest(CoreHarness)`
  - L580: `class InfrastructureTest(CoreHarness)`
  - L696: `class _FlakyStore(SessionStore)`
  - L714: `class DurableRetryTest(unittest.TestCase)`
  - L789: `class PortConflictTest(unittest.TestCase)`
  - L819: `class DedupOnFailureTest(unittest.TestCase)`
  - L931: `class WiringTest(unittest.TestCase)`
  - L1026: `class CancelTest(CoreHarness)`
  - L1141: `class ArchitectureTest(CoreHarness)`
  - L1339: `class StoreIntegrationTest(unittest.TestCase)`
  - L1371: `class ContextSegmentsEventTest(CoreHarness)`
- 类成员：
  - L49: `ScriptedProvider.__init__(self, steps)`
  - L54: `ScriptedProvider.stream(self, request)`
  - L82: `_AskTool.__init__(self)`
  - L85: `_AskTool.execute(self, arguments)`
  - L100: `_EchoTool.execute(self, arguments)`
  - L104: `_Registry.__init__(self, tools)`
  - L107: `_Registry.get(self, name)`
  - L110: `_Registry.names(self)`
  - L113: `_Registry.schemas(self)`
  - L124: `SessionLogViewIsolationTest.test_events_are_deep_copies(self)`
  - L147: `CoreHarness.setUp(self)`
  - L156: `CoreHarness._host(self, steps)`
  - L167: `CoreHarness._run(self, steps)`
  - L175: `CoreHarness._kinds(self)`
  - L178: `CoreHarness._clear(self)`
  - L191: `CoreHarness._last(self, type_)`
  - L200: `CoreHarness._splice(self, call_id, answer)`
  - L217: `BasicTurnTest.test_simple_answer_completes_in_one_pass(self)`
  - L243: `BasicTurnTest.test_model_sees_the_real_tool_result_not_null(self)`
  - L271: `BasicTurnTest.test_failed_tool_result_reaches_the_model_as_error(self)`
  - L295: `BasicTurnTest.test_failed_tool_with_data_keeps_envelope(self)`
  - L319: `BasicTurnTest.test_message_sequence_is_valid_for_the_model(self)`
  - L324: `BasicTurnTest.test_usage_is_emitted_when_provided(self)`
  - L331: `BasicTurnTest.test_no_input_means_no_user_message(self)`
  - L343: `ToolLoopTest.test_tool_call_then_model_continues(self)`
  - L358: `ToolLoopTest.test_two_round_trips(self)`
  - L368: `ToolLoopTest.test_tool_is_not_executed_twice(self)`
  - L375: `ToolLoopTest.echo_calls(self)`
  - L386: `SuspendResumeTest._suspend(self)`
  - L392: `SuspendResumeTest.test_real_user_confirm_records_pending_confirm(self)`
  - L417: `SuspendResumeTest.test_suspend_is_terminal_and_writes_no_tool_result(self)`
  - L429: `SuspendResumeTest.test_suspended_call_is_not_retried_within_the_turn(self)`
  - L434: `SuspendResumeTest.test_resume_splices_result_and_model_continues(self)`
  - L447: `SuspendResumeTest.test_resume_needs_no_memory_state(self)`
  - L464: `SuspendResumeTest.test_second_splice_would_duplicate_so_delivery_is_once(self)`
  - L492: `SuspendBatchTest._gaps(messages)`
  - L500: `SuspendBatchTest.test_suspend_mid_batch_gives_the_rest_a_terminal_fact(self)`
  - L524: `SuspendBatchTest.test_request_sequence_stays_valid_when_user_talks_instead_of_answering(self)`
  - L557: `SuspendBatchTest.test_placeholder_says_why_not_just_null(self)`
  - L583: `InfrastructureTest.test_facts_are_flushed_incrementally_not_only_at_turn_end(self)`
  - L609: `InfrastructureTest.test_events_carry_a_storage_coordinate(self)`
  - L632: `InfrastructureTest.test_ports_log_is_readonly(self)`
  - L650: `InfrastructureTest.test_seq_does_not_stick_after_a_replay(self)`
  - L668: `InfrastructureTest.test_suspend_emits_exactly_one_tool_end(self)`
  - L703: `_FlakyStore.__init__(self, root, fail_times)`
  - L708: `_FlakyStore._encrypt_line(self, line)`
  - L726: `DurableRetryTest._run_turns(self, fail_times, turns, cid)`
  - L754: `DurableRetryTest.test_failed_flush_survives_new_engine_each_turn(self)`
  - L769: `DurableRetryTest.test_retry_does_not_duplicate_rows_or_coordinates(self)`
  - L781: `DurableRetryTest.test_no_failure_path_stays_clean(self)`
  - L798: `PortConflictTest.test_second_bind_on_same_port_raises(self)`
  - L833: `DedupOnFailureTest.test_retry_after_failure_never_duplicates_rows(self)`
  - L859: `DedupOnFailureTest.test_pending_queue_deduplicates_by_seq(self)`
  - L880: `DedupOnFailureTest.test_failure_then_success_keeps_each_fact_once(self)`
  - L942: `WiringTest.setUp(self)`
  - L962: `WiringTest.tearDown(self)`
  - L977: `WiringTest.test_live_events_carry_a_storage_coordinate_through_app_session(self)`
  - L994: `WiringTest.test_factory_receives_every_dependency_it_is_given(self)`
  - L1036: `CancelTest._stop_after_first_tool(self)`
  - L1048: `CancelTest._stop_immediately(self)`
  - L1052: `CancelTest.test_stop_before_any_tool_marks_all_as_canceled(self)`
  - L1076: `CancelTest.test_stop_mid_batch_pads_the_remaining(self)`
  - L1093: `CancelTest.test_canceled_batch_keeps_the_model_history_valid(self)`
  - L1110: `CancelTest.test_stop_is_recorded_as_stopped_not_paused(self)`
  - L1122: `CancelTest.test_cancel_check_error_propagates(self)`
  - L1132: `CancelTest.test_no_cancel_check_means_no_stop(self)`
  - L1144: `ArchitectureTest.test_swap_a_module_without_touching_others(self)`
  - L1171: `ArchitectureTest.test_host_knows_nothing_about_module_semantics(self)`
  - L1195: `ArchitectureTest.test_halt_stops_the_chain_immediately(self)`
  - L1219: `ArchitectureTest.test_runaway_chain_hits_the_guard(self)`
  - L1234: `ArchitectureTest.test_data_never_rides_on_the_return_value(self)`
  - L1241: `ArchitectureTest.test_ports_expose_no_writable_public_fields(self)`
  - L1248: `ArchitectureTest.test_events_stream_out_incrementally(self)`
  - L1273: `ArchitectureTest.test_abandoned_consumer_is_reported(self)`
  - L1287: `ArchitectureTest.test_every_module_returns_an_outcome_on_every_path(self)`
  - L1324: `ArchitectureTest.test_unknown_module_return_is_a_loud_error(self)`
  - L1342: `StoreIntegrationTest.test_facts_persist_and_reload(self)`
  - L1378: `ContextSegmentsEventTest._segs(self)`
  - L1383: `ContextSegmentsEventTest._run_with_context(self, steps)`
  - L1399: `ContextSegmentsEventTest.test_event_is_emitted_once_per_model_call(self)`
  - L1403: `ContextSegmentsEventTest.test_payload_has_segments_and_total(self)`
  - L1410: `ContextSegmentsEventTest.test_last_segment_is_remaining(self)`
  - L1415: `ContextSegmentsEventTest.test_total_is_the_sum_of_segments_without_remaining(self)`
  - L1421: `ContextSegmentsEventTest.test_every_segment_has_label_and_pct(self)`
  - L1428: `ContextSegmentsEventTest.test_tool_round_emits_a_fresh_snapshot(self)`
  - L1435: `ContextSegmentsEventTest.test_dialogue_segment_grows_with_the_turn(self)`

### A.455 `tests/test_coverage_edges.py`

- 类型：Python
- 行数：430
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：覆盖率补齐：边界分支与公开行为，不依赖外部服务。
- 导入：`__future__`, `base64`, `tempfile`, `unittest`, `unittest.mock`, `pathlib`, `agent.app`, `agent.core.context`, `agent.core.events`, `agent.core.image_embed`, `agent.core.session_context`, `agent.core.session_log`, `agent.core.slot_tree`, `agent.mechanisms.command_safety`, `agent.mechanisms.error_log`, `agent.mechanisms.executors`, `agent.mechanisms.live_state`, `agent.mechanisms.session_title`, `agent.session_paths`, `agent.subagent.lifecycle`
- 顶层符号：
  - L67: `class ImageEmbedEdgeTest(unittest.TestCase)`
  - L123: `class SlotTreeValidationEdgeTest(unittest.TestCase)`
  - L136: `class SessionContextEdgeTest(unittest.TestCase)`
  - L152: `class SessionLogEdgeTest(unittest.TestCase)`
  - L175: `class TitleEdgeTest(unittest.TestCase)`
  - L206: `class LiveStateEdgeTest(unittest.TestCase)`
  - L279: `class CommandSafetyEdgeTest(unittest.TestCase)`
  - L294: `class SessionPathsEdgeTest(unittest.TestCase)`
  - L319: `class AppFacadeEdgeTest(unittest.TestCase)`
  - L332: `class ExecutorErrorLogTest(unittest.TestCase)`
  - L362: `class CommandSafetyMoreTest(unittest.TestCase)`
  - L376: `class SubagentLifecycleEdgeTest(unittest.TestCase)`
  - L394: `class SubagentSeedEdgeTest(unittest.TestCase)`
- 类成员：
  - L68: `ImageEmbedEdgeTest.test_unknown_bytes_are_not_images(self)`
  - L71: `ImageEmbedEdgeTest.test_png_dimensions(self)`
  - L76: `ImageEmbedEdgeTest.test_invalid_attachments_are_ignored(self)`
  - L83: `ImageEmbedEdgeTest.test_budget_skip_is_reported(self)`
  - L92: `ImageEmbedEdgeTest.test_placeholder_with_attachment_id(self)`
  - L97: `ImageEmbedEdgeTest.test_shrink_zero_side_is_identity(self)`
  - L100: `ImageEmbedEdgeTest.test_strip_old_images_and_attachment_meta(self)`
  - L124: `SlotTreeValidationEdgeTest.test_rejects_duplicate_missing_factory_and_dependency(self)`
  - L137: `SessionContextEdgeTest.test_approval_and_registry(self)`
  - L153: `SessionLogEdgeTest.test_user_content_invalid_and_budget(self)`
  - L157: `SessionLogEdgeTest.test_tool_envelope_errors_and_elapsed(self)`
  - L161: `SessionLogEdgeTest.test_session_log_append_and_derive(self)`
  - L176: `TitleEdgeTest.test_clean_title_strips_wrapping_and_clips(self)`
  - L181: `TitleEdgeTest.test_placeholder_title(self)`
  - L186: `TitleEdgeTest.test_provider_generator_and_failure(self)`
  - L197: `TitleEdgeTest.test_title_store_round_trip_and_invalid_id(self)`
  - L207: `LiveStateEdgeTest.test_mode_todo_and_autonomy(self)`
  - L224: `LiveStateEdgeTest.test_goal_mutation_and_trigger(self)`
  - L246: `LiveStateEdgeTest.test_command_input_targets(self)`
  - L256: `LiveStateEdgeTest.test_invalid_mode_rejected(self)`
  - L261: `LiveStateEdgeTest.test_goal_effort_model_persist(self)`
  - L280: `CommandSafetyEdgeTest.test_blacklist_and_safe_validation(self)`
  - L286: `CommandSafetyEdgeTest.test_shell_and_output(self)`
  - L295: `SessionPathsEdgeTest.test_layout_creates_directories(self)`
  - L308: `SessionPathsEdgeTest.test_layout_preserves_existing_files(self)`
  - L320: `AppFacadeEdgeTest.test_app_init_and_loop_config(self)`
  - L333: `ExecutorErrorLogTest.test_executor_registry_without_slots(self)`
  - L351: `ExecutorErrorLogTest.test_error_log_report_and_rotate(self)`
  - L363: `CommandSafetyMoreTest.test_wrapper_and_more_branches(self)`
  - L377: `SubagentLifecycleEdgeTest.test_validate_guards(self)`
  - L395: `SubagentSeedEdgeTest.test_seed_child_fresh(self)`
  - L419: `SubagentSeedEdgeTest.test_completed_turn_prefix(self)`

### A.456 `tests/test_coverage_gaps.py`

- 类型：Python
- 行数：196
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：拆分后 helper 的回归：终止事件、模型流、工具取消、图片配额。
- 导入：`__future__`, `sys`, `unittest`, `pathlib`, `types`, `agent.core.host`, `agent.core.image_embed`, `agent.core.model_call`, `agent.core.modules.model_mod`, `agent.core.modules.tool_mod`, `agent.core.ports`, `agent.core.session_log`, `agent.core.tool_call`
- 顶层符号：
  - L29: `class HostEventHelperTest(unittest.TestCase)`
  - L58: `class _Model()`
  - L72: `class _Tool()`
  - L77: `def _ports(events, cancel)`
  - L84: `def _drain(generator)`
  - L93: `class ModelHelperTest(unittest.TestCase)`
  - L144: `class ToolHelperTest(unittest.TestCase)`
  - L167: `class ImageHelperTest(unittest.TestCase)`
- 类成员：
  - L30: `HostEventHelperTest.setUp(self)`
  - L34: `HostEventHelperTest.test_cancel_and_max_pass_events(self)`
  - L44: `HostEventHelperTest.test_terminal_event_covers_all_three_states(self)`
  - L59: `_Model.__init__(self, deltas, error)`
  - L63: `_Model.name_for(self, _request)`
  - L66: `_Model.stream(self, _request)`
  - L73: `_Tool.schemas(self)`
  - L94: `ModelHelperTest._module(self)`
  - L97: `ModelHelperTest.test_build_request_without_context(self)`
  - L105: `ModelHelperTest.test_stream_parts_usage_and_tool_calls(self)`
  - L124: `ModelHelperTest.test_stream_failure_returns_state(self)`
  - L133: `ModelHelperTest.test_stream_cancel_returns_stopped(self)`
  - L145: `ToolHelperTest.test_cancel_rest_emits_pair_for_every_call(self)`
  - L153: `ToolHelperTest.test_result_events_cover_success_and_failure(self)`
  - L168: `ImageHelperTest._image(self, data)`
  - L171: `ImageHelperTest.test_positions_select_and_strip(self)`
  - L187: `ImageHelperTest.test_strip_old_images_negative_limits(self)`

### A.457 `tests/test_edited_files.py`

- 类型：Python
- 行数：46
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：本回合编辑清单：会话页内存拼装，不进内核，刷新不回放。
- 导入：`__future__`, `sys`, `unittest`, `pathlib`, `agent.shell.web.ui_bundle`
- 顶层符号：
  - L16: `class EditedFilesPageTest(unittest.TestCase)`
- 类成员：
  - L17: `EditedFilesPageTest.test_list_is_assembled_on_the_live_stream_only(self)`

### A.458 `tests/test_entry_layer.py`

- 类型：Python
- 行数：335
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：入口层（`agent/entry/`）：装配与参数解析的契约。
- 导入：`__future__`, `io`, `os`, `sys`, `tempfile`, `time`, `unittest`, `contextlib`, `pathlib`, `unittest`, `agent.config`, `agent.core.events`, `agent.entry`, `agent.entry`, `agent.entry`, `agent.mechanisms.session_store`, `tests.testkit`
- 顶层符号：
  - L31: `class _TempDataRoot(unittest.TestCase)`
  - L57: `class BuildShellAppTest(_TempDataRoot)`
  - L83: `class WebMainTest(_TempDataRoot)`
  - L146: `class CliEntryTest(_TempDataRoot)`
  - L170: `class HeadlessEntryTest(unittest.TestCase)`
- 类成员：
  - L38: `_TempDataRoot.setUp(self)`
  - L47: `_TempDataRoot._restore_env(self)`
  - L53: `_TempDataRoot._store(self)`
  - L60: `BuildShellAppTest.test_given_provider_and_store_are_used(self)`
  - L69: `BuildShellAppTest.test_default_starts_without_model(self)`
  - L74: `BuildShellAppTest.test_repository_config_has_no_model_section(self)`
  - L79: `BuildShellAppTest.test_default_data_root_is_used_when_omitted(self)`
  - L86: `WebMainTest.test_unexpected_build_error_returns_2(self)`
  - L95: `WebMainTest.test_open_flag_uses_main_page_without_model(self)`
  - L110: `WebMainTest.test_args_are_forwarded_to_shell_serve(self)`
  - L132: `WebMainTest.test_empty_fs_root_passes_none(self)`
  - L149: `CliEntryTest.test_no_models_returns_none(self)`
  - L155: `CliEntryTest.test_main_delegates_to_chat_main(self)`
  - L173: `HeadlessEntryTest.test_run_prints_one_line_per_event(self)`
  - L189: `HeadlessEntryTest.test_main_passes_first_argument_and_uses_factory(self)`
  - L203: `HeadlessEntryTest.test_main_defaults_to_smoke_text(self)`
  - L215: `HeadlessEntryTest.test_headless_prefers_runner_engine_over_app_run_turn(self)`
  - L242: `HeadlessEntryTest.test_default_factory_wires_session_store(self)`
  - L257: `HeadlessEntryTest.test_run_session_returns_generated_cid(self)`
  - L277: `HeadlessEntryTest.test_run_session_maps_terminal_states(self)`
  - L306: `HeadlessEntryTest.test_run_session_timeout_cancels(self)`
  - L326: `HeadlessEntryTest.test_main_fails_when_model_is_missing(self)`

### A.459 `tests/test_environment_info.py`

- 类型：Python
- 行数：33
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：环境章节：资源目录之后、编码准则之前，带本会话 ID。
- 导入：`__future__`, `sys`, `unittest`, `pathlib`, `agent.capabilities.registry`, `agent.shell.environment_info`, `agent.shell.prompts`
- 顶层符号：
  - L17: `class EnvironmentSectionTest(unittest.TestCase)`
- 类成员：
  - L18: `EnvironmentSectionTest.test_section_is_after_resource_and_before_coding(self)`

### A.460 `tests/test_error_log.py`

- 类型：Python
- 行数：164
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：错误日志：落盘、容错、工具管道挂钩。
- 导入：`__future__`, `json`, `os`, `sys`, `tempfile`, `unittest`, `pathlib`, `unittest.mock`, `agent.app`, `agent.core.context`, `agent.core.error_report`, `agent.core.tool_call`, `agent.mechanisms.error_log`
- 顶层符号：
  - L23: `class ErrorLogWriteTest(unittest.TestCase)`
  - L60: `class ErrorReportFacadeTest(unittest.TestCase)`
  - L84: `class ToolPipelineErrorLogTest(unittest.TestCase)`
  - L131: `class BuildAppErrorLogTest(unittest.TestCase)`
- 类成员：
  - L24: `ErrorLogWriteTest.setUp(self)`
  - L30: `ErrorLogWriteTest.test_report_writes_jsonl(self)`
  - L43: `ErrorLogWriteTest.test_report_string_without_exc_type(self)`
  - L50: `ErrorLogWriteTest.test_write_failure_does_not_raise(self)`
  - L61: `ErrorReportFacadeTest.tearDown(self)`
  - L64: `ErrorReportFacadeTest.test_bound_sink_receives_call(self)`
  - L76: `ErrorReportFacadeTest.test_sink_exception_does_not_raise(self)`
  - L85: `ToolPipelineErrorLogTest.tearDown(self)`
  - L88: `ToolPipelineErrorLogTest.test_tool_exception_not_reported(self)`
  - L108: `ToolPipelineErrorLogTest.test_await_user_not_reported(self)`
  - L132: `BuildAppErrorLogTest.setUp(self)`
  - L139: `BuildAppErrorLogTest.tearDown(self)`
  - L146: `BuildAppErrorLogTest.test_build_app_registers_and_binds(self)`

### A.461 `tests/test_event_bus.py`

- 类型：Python
- 行数：164
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：事件总线测试。
- 导入：`__future__`, `sys`, `tempfile`, `unittest`, `pathlib`, `agent.app`, `agent.core`, `agent.core.error_report`, `agent.core.event_bus`, `agent.core.events`, `agent.mechanisms.providers.echo`
- 顶层符号：
  - L25: `class EventBusTest(unittest.TestCase)`
  - L109: `class EngineEventSinkTest(unittest.TestCase)`
- 类成员：
  - L28: `EventBusTest.test_publish_dispatches_in_order(self)`
  - L37: `EventBusTest.test_type_filter(self)`
  - L45: `EventBusTest.test_subscribe_validation(self)`
  - L53: `EventBusTest.test_subscriber_exception_isolated(self)`
  - L66: `EventBusTest.test_disposer_idempotent(self)`
  - L76: `EventBusTest.test_snapshot_iteration(self)`
  - L98: `EventBusTest.test_dispose_all(self)`
  - L112: `EngineEventSinkTest.setUp(self)`
  - L125: `EngineEventSinkTest.test_turn_events_published_to_bus(self)`
  - L137: `EngineEventSinkTest.test_sink_exception_does_not_break_turn(self)`

### A.462 `tests/test_executor_registry.py`

- 类型：Python
- 行数：53
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：执行器 leaf 的插口绑定与回退测试。
- 导入：`__future__`, `unittest`, `unittest`, `agent.capabilities.builtin`, `agent.capabilities.slot_registry`, `agent.mechanisms.executors`
- 顶层符号：
  - L13: `def _executor(tag)`
  - L17: `class ExecutorSlotTest(unittest.TestCase)`
- 类成员：
  - L18: `ExecutorSlotTest.setUp(self)`
  - L23: `ExecutorSlotTest.test_replace_and_restore(self)`
  - L29: `ExecutorSlotTest.test_add_with_replace_option(self)`
  - L33: `ExecutorSlotTest.test_names_lists_replaced_executor_slots(self)`
  - L38: `ExecutorSlotTest.test_commit_write_prefers_replaced_executor(self)`

### A.463 `tests/test_fact_compat.py`

- 类型：Python
- 行数：152
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：历史事实形态在当前内核里仍被消费。
- 导入：`__future__`, `json`, `unittest`, `agent.core.events`
- 顶层符号：
  - L16: `class ClassicToolResultTest(unittest.TestCase)`
  - L115: `class LegacyResultDoesNotReplayTest(unittest.TestCase)`
- 类成员：
  - L24: `ClassicToolResultTest._events(self)`
  - L43: `ClassicToolResultTest.test_user_answer_survives_in_the_tool_message(self)`
  - L57: `ClassicToolResultTest.test_new_format_result_is_not_duplicated(self)`
  - L77: `ClassicToolResultTest.test_await_user_intermediate_result_does_not_reach_the_model(self)`
  - L93: `ClassicToolResultTest.test_cancel_without_a_closing_terminal_still_reaches_the_model(self)`
  - L118: `LegacyResultDoesNotReplayTest.test_legacy_result_closes_the_call(self)`
  - L129: `LegacyResultDoesNotReplayTest.test_legacy_result_at_tail_expects_model(self)`
  - L140: `LegacyResultDoesNotReplayTest.test_intermediate_legacy_result_is_not_terminal(self)`

### A.464 `tests/test_file_safety.py`

- 类型：Python
- 行数：272
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：版本化备份与回收目录：按路径哈希分组、每版本自描述、按年龄清理。
- 导入：`__future__`, `json`, `re`, `sys`, `tempfile`, `time`, `unittest`, `pathlib`, `agent.mechanisms.file_safety`
- 顶层符号：
  - L26: `class LayoutTest(unittest.TestCase)`
  - L156: `class PathHashTest(unittest.TestCase)`
  - L170: `class PruneTest(unittest.TestCase)`
  - L238: `class VersionTimeTextTest(unittest.TestCase)`
  - L250: `class RecycleTest(unittest.TestCase)`
- 类成员：
  - L29: `LayoutTest.setUp(self)`
  - L38: `LayoutTest.test_files_are_grouped_by_path_hash(self)`
  - L52: `LayoutTest.test_same_second_versions_keep_chronological_order(self)`
  - L71: `LayoutTest.test_versions_are_self_describing(self)`
  - L88: `LayoutTest.test_long_diff_is_clipped_and_marked(self)`
  - L98: `LayoutTest.test_directory_names_carry_no_filename(self)`
  - L112: `LayoutTest.test_two_different_files_never_share_a_group(self)`
  - L123: `LayoutTest.test_list_for_is_newest_first(self)`
  - L130: `LayoutTest.test_broken_metadata_only_affects_its_own_version(self)`
  - L140: `LayoutTest.test_read_returns_the_bytes_that_were_backed_up(self)`
  - L147: `LayoutTest.test_unknown_mod_id_is_none(self)`
  - L152: `LayoutTest.test_create_returns_none_for_missing_file(self)`
  - L157: `PathHashTest.test_same_path_same_hash(self)`
  - L161: `PathHashTest.test_different_paths_differ(self)`
  - L164: `PathHashTest.test_hash_is_short_hex(self)`
  - L173: `PruneTest.setUp(self)`
  - L181: `PruneTest._plant(self, days_ago, rand, path)`
  - L195: `PruneTest.test_prune_removes_older_than_retention(self)`
  - L205: `PruneTest.test_prune_removes_the_group_once_all_versions_are_gone(self)`
  - L211: `PruneTest.test_prune_keeps_the_group_while_any_version_survives(self)`
  - L217: `PruneTest.test_prune_leaves_unparseable_version_names(self)`
  - L226: `PruneTest.test_prune_on_missing_root_is_noop(self)`
  - L229: `PruneTest.test_prune_ignores_stray_files_at_the_root(self)`
  - L239: `VersionTimeTextTest.test_reverse_parses_the_timestamp(self)`
  - L243: `VersionTimeTextTest.test_returns_empty_when_format_does_not_match(self)`
  - L251: `RecycleTest.test_move_puts_the_file_under_a_day_directory(self)`
  - L263: `RecycleTest.test_target_for_sanitizes_the_name(self)`

### A.465 `tests/test_file_size_format.py`

- 类型：Python
- 行数：85
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：文件面板的大小显示：一律 KB 起，不出现"字节"。
- 导入：`__future__`, `json`, `shutil`, `subprocess`, `sys`, `tempfile`, `unittest`, `pathlib`, `agent.shell.web.ui_bundle`
- 顶层符号：
  - L26: `def _function_source(name)`
  - L34: `def _run(cases)`
  - L54: `class FileSizeFormatTest(unittest.TestCase)`
- 类成员：
  - L55: `FileSizeFormatTest.test_never_uses_byte_unit(self)`
  - L63: `FileSizeFormatTest.test_sub_kilobyte_becomes_decimal_kb(self)`
  - L70: `FileSizeFormatTest.test_rounds_before_choosing_the_unit(self)`
  - L78: `FileSizeFormatTest.test_bad_values_are_empty(self)`

### A.466 `tests/test_four_step_gate.py`

- 类型：Python
- 行数：193
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：写盘四步协议门控测试（id 制）：预览登记 → 确认 → 凭 ID 提交 → 重读。
- 导入：`__future__`, `sys`, `tempfile`, `unittest`, `pathlib`, `agent.core.tool_call`, `agent.mechanisms.quality`, `tests.gate_fixtures`
- 顶层符号：
  - L26: `class FourStepGateTest(unittest.TestCase)`
  - L163: `class ChangePayloadTest(unittest.TestCase)`
- 类成员：
  - L29: `FourStepGateTest.setUp(self)`
  - L35: `FourStepGateTest._ready(self, path, content)`
  - L41: `FourStepGateTest._commit(self, cid)`
  - L53: `FourStepGateTest.test_no_preview_denied(self)`
  - L61: `FourStepGateTest.test_relative_suffix_does_not_bypass_pending_review(self)`
  - L70: `FourStepGateTest.test_unconfirmed_preview_denied(self)`
  - L83: `FourStepGateTest.test_snapshot_binding_and_single_use(self)`
  - L95: `FourStepGateTest.test_happy_path_four_steps(self)`
  - L112: `FourStepGateTest.test_reread_required_for_next_edit(self)`
  - L126: `FourStepGateTest.test_same_path_keeps_only_latest_preview(self)`
  - L140: `FourStepGateTest.test_pending_cap_evicts_oldest(self)`
  - L166: `ChangePayloadTest.test_payload_has_only_diff_not_full_text(self)`
  - L183: `ChangePayloadTest.test_new_file_flag_for_empty_old(self)`

### A.467 `tests/test_frame_shape_align.py`

- 类型：Python
- 行数：134
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：两条前端路径各自的返回契约。
- 导入：`__future__`, `json`, `sys`, `tempfile`, `unittest`, `pathlib`, `typing`, `agent.core.events`, `agent.mechanisms.session_store`, `agent.shell.classic_adapter.adapter`
- 顶层符号：
  - L31: `class _FakeApp()`
  - L42: `def _events()`
  - L60: `class HistoryContractTest(unittest.TestCase)`
  - L91: `class SseFrameContractTest(unittest.TestCase)`
- 类成员：
  - L34: `_FakeApp.__init__(self, store)`
  - L63: `HistoryContractTest.setUp(self)`
  - L70: `HistoryContractTest.test_payload_carries_only_what_the_page_reads(self)`
  - L79: `HistoryContractTest.test_no_events_field(self)`
  - L83: `HistoryContractTest.test_items_carry_tool_role_for_cards(self)`
  - L94: `SseFrameContractTest.setUp(self)`
  - L100: `SseFrameContractTest._frames(self)`
  - L112: `SseFrameContractTest.test_every_frame_carries_cid(self)`
  - L121: `SseFrameContractTest.test_seq_never_leaks_into_frame_payloads(self)`
  - L126: `SseFrameContractTest.test_frames_are_single_line_json(self)`

### A.468 `tests/test_frozen_data_root.py`

- 类型：Python
- 行数：42
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：配置：冻结程序的数据根落到用户目录。
- 导入：`__future__`, `os`, `sys`, `tempfile`, `unittest`, `pathlib`, `unittest`, `agent`
- 顶层符号：
  - L18: `class FrozenDataRootTest(unittest.TestCase)`
- 类成员：
  - L19: `FrozenDataRootTest.test_frozen_uses_user_data_root(self)`
  - L26: `FrozenDataRootTest.test_env_override_wins_over_frozen(self)`
  - L33: `FrozenDataRootTest.test_windows_user_data_root(self)`

### A.469 `tests/test_gate_negative.py`

- 类型：Python
- 行数：607
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：门禁负向用例：每条门禁都要能真的红。
- 导入：`__future__`, `ast`, `io`, `sys`, `tempfile`, `textwrap`, `unittest`, `pathlib`, `unittest`, `check_applicability`, `check_architecture_hygiene`, `check_comment_style`, `check_complexity`, `check_config_drift`, `check_confirm_wording`, `check_coverage`, `check_imports`, `check_python_floor`, `check_readme`, `check_ui_js`
- 顶层符号：
  - L38: `def _write(path, text)`
  - L44: `class ImportDirectionGateTest(unittest.TestCase)`
  - L117: `class ArchitectureHygieneGateTest(unittest.TestCase)`
  - L152: `class PythonFloorGateTest(unittest.TestCase)`
  - L165: `class ApplicabilityGateTest(unittest.TestCase)`
  - L235: `class ComplexityGateTest(unittest.TestCase)`
  - L260: `class ConfigDriftGateTest(unittest.TestCase)`
  - L293: `class CoverageGateTest(unittest.TestCase)`
  - L310: `class GeneratedArtifactDriftTest(unittest.TestCase)`
  - L340: `class UiJsGateTest(unittest.TestCase)`
  - L361: `class ReadmeGateTest(unittest.TestCase)`
  - L404: `class CommentStyleGateTest(unittest.TestCase)`
  - L452: `class ConfirmWordingGateTest(unittest.TestCase)`
  - L501: `class AcceptanceSkipGateTest(unittest.TestCase)`
  - L526: `class DataCleanlinessGateTest(unittest.TestCase)`
  - L550: `class GeneratedComplexityDocGateTest(unittest.TestCase)`
  - L579: `class ConfigModelExampleGateTest(unittest.TestCase)`
- 类成员：
  - L47: `ImportDirectionGateTest._package(self, files)`
  - L55: `ImportDirectionGateTest.test_upward_import_fails(self)`
  - L62: `ImportDirectionGateTest.test_composition_root_import_fails(self)`
  - L68: `ImportDirectionGateTest.test_unknown_top_level_package_fails(self)`
  - L73: `ImportDirectionGateTest.test_common_cannot_import_core(self)`
  - L81: `ImportDirectionGateTest.test_update_health_exception_is_narrow(self)`
  - L91: `ImportDirectionGateTest.test_boot_may_import_layers(self)`
  - L98: `ImportDirectionGateTest.test_type_checking_annotation_is_allowed(self)`
  - L108: `ImportDirectionGateTest.test_downward_import_passes(self)`
  - L120: `ArchitectureHygieneGateTest._package(self, files)`
  - L131: `ArchitectureHygieneGateTest.test_cross_layer_private_import_fails(self)`
  - L135: `ArchitectureHygieneGateTest.test_same_layer_private_import_passes(self)`
  - L139: `ArchitectureHygieneGateTest.test_plugin_name_in_core_fails(self)`
  - L143: `ArchitectureHygieneGateTest.test_quality_gate_shim_import_fails(self)`
  - L147: `ArchitectureHygieneGateTest.test_quality_gate_real_module_passes(self)`
  - L155: `PythonFloorGateTest.test_ordinary_function_passes(self)`
  - L160: `PythonFloorGateTest.test_pep695_generic_fails(self)`
  - L171: `ApplicabilityGateTest._docs(self, text)`
  - L176: `ApplicabilityGateTest._run(self, docs)`
  - L183: `ApplicabilityGateTest.test_unknown_rule_id_fails(self)`
  - L188: `ApplicabilityGateTest.test_short_reason_fails(self)`
  - L193: `ApplicabilityGateTest.test_english_header_and_value_pass(self)`
  - L201: `ApplicabilityGateTest.test_well_formed_row_passes(self)`
  - L205: `ApplicabilityGateTest.test_rule_ids_are_wellformed(self)`
  - L215: `ApplicabilityGateTest.test_stale_id_fails_through_main(self)`
  - L222: `ApplicabilityGateTest.test_counts_and_ratio_visible(self)`
  - L228: `ApplicabilityGateTest.test_missing_table_fails(self)`
  - L238: `ComplexityGateTest._root(self)`
  - L245: `ComplexityGateTest._check(self, root)`
  - L251: `ComplexityGateTest.test_big_file_fails_without_registry(self)`
  - L255: `ComplexityGateTest.test_generated_doc_drift_is_reported(self)`
  - L263: `ConfigDriftGateTest.test_real_file_extra_key_reports_line_number(self)`
  - L270: `ConfigDriftGateTest.test_real_file_subset_passes(self)`
  - L277: `ConfigDriftGateTest.test_unknown_section_fails(self)`
  - L283: `ConfigDriftGateTest.test_model_plugin_rejects_unknown_key(self)`
  - L296: `CoverageGateTest.test_below_floor_fails(self)`
  - L301: `CoverageGateTest.test_missing_group_fails(self)`
  - L305: `CoverageGateTest.test_at_or_above_floor_passes(self)`
  - L313: `GeneratedArtifactDriftTest.test_ci_workflow_byte_drift_fails(self)`
  - L320: `GeneratedArtifactDriftTest.test_ci_workflow_current_is_clean(self)`
  - L323: `GeneratedArtifactDriftTest.test_unit_tests_md_drift_fails(self)`
  - L332: `GeneratedArtifactDriftTest.test_render_contains_every_gate_and_acceptance(self)`
  - L343: `UiJsGateTest.test_undefined_helper_call_fails(self)`
  - L347: `UiJsGateTest.test_defined_helper_passes(self)`
  - L352: `UiJsGateTest.test_model_id_literal_is_rejected(self)`
  - L357: `UiJsGateTest.test_plain_words_are_not_model_ids(self)`
  - L369: `ReadmeGateTest.test_step_count_drift_fails(self)`
  - L374: `ReadmeGateTest.test_gate_count_drift_fails(self)`
  - L379: `ReadmeGateTest.test_acceptance_count_drift_fails(self)`
  - L384: `ReadmeGateTest.test_test_count_drift_fails(self)`
  - L389: `ReadmeGateTest.test_missing_marker_fails(self)`
  - L393: `ReadmeGateTest.test_unknown_data_dir_fails(self)`
  - L398: `ReadmeGateTest.test_consistent_readme_passes(self)`
  - L407: `CommentStyleGateTest.test_todo_comment_fails(self)`
  - L413: `CommentStyleGateTest.test_command_to_reader_fails(self)`
  - L420: `CommentStyleGateTest.test_string_literal_is_not_comment(self)`
  - L426: `CommentStyleGateTest.test_clean_comment_passes(self)`
  - L432: `CommentStyleGateTest.test_markdown_emphasis_comment_fails(self)`
  - L438: `CommentStyleGateTest.test_markdown_emphasis_across_lines_fails(self)`
  - L445: `CommentStyleGateTest.test_code_unpacking_is_not_emphasis(self)`
  - L455: `ConfirmWordingGateTest._texts(self)`
  - L472: `ConfirmWordingGateTest.test_missing_unlock_tool_fails(self)`
  - L477: `ConfirmWordingGateTest.test_vague_wording_fails(self)`
  - L482: `ConfirmWordingGateTest.test_explanatory_wording_fails(self)`
  - L488: `ConfirmWordingGateTest.test_gate_without_next_step_fails(self)`
  - L497: `ConfirmWordingGateTest.test_compliant_wording_passes(self)`
  - L504: `AcceptanceSkipGateTest.test_over_budget_fails(self)`
  - L508: `AcceptanceSkipGateTest.test_non_whitelisted_fails(self)`
  - L512: `AcceptanceSkipGateTest.test_whitelisted_within_budget_passes(self)`
  - L515: `AcceptanceSkipGateTest.test_duplicates_do_not_count_twice(self)`
  - L527: `DataCleanlinessGateTest.test_windows_runtime_paths_are_normalized(self)`
  - L538: `DataCleanlinessGateTest.test_user_review_artifacts_are_not_test_pollution(self)`
  - L544: `DataCleanlinessGateTest.test_unknown_data_path_is_neither_runtime_nor_user_data(self)`
  - L551: `GeneratedComplexityDocGateTest.test_check_detects_drift(self)`
  - L558: `GeneratedComplexityDocGateTest.test_check_detects_missing_file(self)`
  - L564: `GeneratedComplexityDocGateTest.test_check_detects_extra_content(self)`
  - L571: `GeneratedComplexityDocGateTest.test_check_accepts_generated_text(self)`
  - L580: `ConfigModelExampleGateTest._model_example(self, extra)`
  - L585: `ConfigModelExampleGateTest.test_compare_model_example_detects_extra_key(self)`
  - L590: `ConfigModelExampleGateTest.test_compare_model_example_detects_changed_section(self)`
  - L595: `ConfigModelExampleGateTest.test_compare_model_example_positive(self)`
  - L599: `ConfigModelExampleGateTest.test_compare_model_example_requires_keys(self)`

### A.470 `tests/test_goal_runner.py`

- 类型：Python
- 行数：172
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：目标驱动的续跑：取消必须生效、回合数有上限、paused/done 不触发。
- 导入：`__future__`, `sys`, `threading`, `time`, `unittest`, `pathlib`, `unittest`, `agent.mechanisms.live_state`, `agent.mechanisms.mesh`, `agent.shell.session.goal`, `agent.shell.session.runner`
- 顶层符号：
  - L29: `class _FakeApp()`
  - L37: `class _RunnerBase(unittest.TestCase)`
  - L64: `class ContinuationTextTest(_RunnerBase)`
  - L93: `class GoalQueueFallbackTest(_RunnerBase)`
  - L112: `class CancelTest(_RunnerBase)`
  - L156: `class StartFailureTest(_RunnerBase)`
- 类成员：
  - L32: `_FakeApp.__init__(self, state)`
  - L38: `_RunnerBase._make(self, cid)`
  - L58: `_RunnerBase._drive(runner, cid)`
  - L67: `ContinuationTextTest.test_goal_absent_falls_back_to_autonomy_switch(self)`
  - L74: `ContinuationTextTest.test_active_goal_wins_over_hardcoded_prompt(self)`
  - L81: `ContinuationTextTest.test_paused_and_done_stop_even_when_autonomy_on(self)`
  - L94: `GoalQueueFallbackTest.test_goal_turn_is_queued_when_run_slot_is_taken(self)`
  - L113: `CancelTest.test_cancel_stops_goal_continuation(self)`
  - L131: `CancelTest.test_auto_rounds_are_capped(self)`
  - L142: `CancelTest.test_goal_rounds_counter_advances(self)`
  - L157: `StartFailureTest.test_start_failure_releases_placeholder(self)`

### A.471 `tests/test_gui_launcher.py`

- 类型：Python
- 行数：99
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：GUI 启动器：服务子进程必须随窗口启动，并在窗口关闭后终止。
- 导入：`__future__`, `sys`, `unittest`, `pathlib`, `unittest`, `agent.gui`
- 顶层符号：
  - L16: `class GuiLauncherTest(unittest.TestCase)`
- 类成员：
  - L17: `GuiLauncherTest.test_launch_owns_child_and_stops_it(self)`
  - L32: `GuiLauncherTest.test_failed_window_still_stops_child(self)`
  - L42: `GuiLauncherTest.test_occupied_explicit_port_does_not_spawn(self)`
  - L49: `GuiLauncherTest.test_missing_entry_returns_nonzero(self)`
  - L55: `GuiLauncherTest.test_activate_window_uses_windows_api(self)`
  - L70: `GuiLauncherTest.test_activate_window_without_handle(self)`
  - L74: `GuiLauncherTest.test_open_window_enables_text_selection(self)`
  - L91: `GuiLauncherTest.test_pick_port_and_storage_path(self)`

### A.472 `tests/test_history_page.py`

- 类型：Python
- 行数：164
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：历史分页纯函数：轮次、字符预算、页边界与不可变出参。
- 导入：`__future__`, `unittest`, `agent.core.events`, `agent.shell.classic_adapter.history_page`
- 顶层符号：
  - L16: `def _input(seq, text)`
  - L20: `def _model(seq, text)`
  - L24: `class ItemCostTest(unittest.TestCase)`
  - L42: `class FoldRoundsTest(unittest.TestCase)`
  - L81: `class SelectPageTest(unittest.TestCase)`
- 类成员：
  - L25: `ItemCostTest.test_user_and_attachments(self)`
  - L32: `ItemCostTest.test_tool_uses_script_args_preview_and_images(self)`
  - L43: `FoldRoundsTest.test_empty(self)`
  - L50: `FoldRoundsTest.test_round_anchor_and_order(self)`
  - L56: `FoldRoundsTest.test_residual_events_before_first_input(self)`
  - L63: `FoldRoundsTest.test_tool_lifecycle_stays_in_round(self)`
  - L76: `FoldRoundsTest.test_chars_equal_sum_items(self)`
  - L82: `SelectPageTest._rounds(self, sizes)`
  - L90: `SelectPageTest.test_budget_reaches_threshold_and_includes_whole_round(self)`
  - L98: `SelectPageTest.test_single_round_over_budget_is_returned_whole(self)`
  - L105: `SelectPageTest.test_before_is_exclusive(self)`
  - L111: `SelectPageTest.test_before_older_than_everything_returns_empty(self)`
  - L118: `SelectPageTest.test_exact_before_does_not_return_that_round(self)`
  - L124: `SelectPageTest.test_page_values_are_copies(self)`
  - L131: `SelectPageTest.test_next_before_only_when_has_more(self)`
  - L137: `SelectPageTest.test_full_traversal_has_no_missing_or_duplicate_rounds(self)`
  - L158: `SelectPageTest.test_budget_constant(self)`

### A.473 `tests/test_host_service_slots.py`

- 类型：Python
- 行数：36
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：宿主服务路径的替换与恢复测试。
- 导入：`__future__`, `unittest`, `agent.capabilities.slot_registry`, `agent.core.context`
- 顶层符号：
  - L11: `class HostServiceSlotTest(unittest.TestCase)`
- 类成员：
  - L12: `HostServiceSlotTest.test_replace_service_and_restore(self)`
  - L24: `HostServiceSlotTest.test_dispose_removes_default_slot(self)`

### A.474 `tests/test_http_route_slots.py`

- 类型：Python
- 行数：75
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：HTTP route slot 的绑定、替换和回退。
- 导入：`__future__`, `unittest`, `agent.capabilities.slot_registry`, `agent.shell.web.web_route_slots`, `agent.shell.web.web_routes`
- 顶层符号：
  - L12: `class HttpRouteSlotsTest(unittest.TestCase)`
- 类成员：
  - L13: `HttpRouteSlotsTest.setUp(self)`
  - L17: `HttpRouteSlotsTest.test_default_bind_and_replace(self)`
  - L29: `HttpRouteSlotsTest.test_handler_dispatches_bound_route(self)`
  - L41: `HttpRouteSlotsTest.test_post_slot_can_be_bound(self)`
  - L51: `HttpRouteSlotsTest.test_slot_can_be_bound(self)`
  - L62: `HttpRouteSlotsTest.test_path_is_injective(self)`

### A.475 `tests/test_image_embed.py`

- 类型：Python
- 行数：130
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：视觉嵌图：本地缩放与请求体预算。
- 导入：`__future__`, `base64`, `struct`, `sys`, `unittest`, `zlib`, `pathlib`, `agent.core.image_embed`
- 顶层符号：
  - L27: `def _png(w, h, rgb)`
  - L43: `def _dims(data)`
  - L46: `class ShrinkImageTest(unittest.TestCase)`
  - L75: `class EmbedBudgetTest(unittest.TestCase)`
  - L100: `class DerivedMessageShrinksTest(unittest.TestCase)`
- 类成员：
  - L48: `ShrinkImageTest.test_small_image_is_left_alone(self)`
  - L55: `ShrinkImageTest.test_large_image_is_shrunk_to_max_side(self)`
  - L60: `ShrinkImageTest.test_extreme_aspect_ratio_survives(self)`
  - L65: `ShrinkImageTest.test_garbage_bytes_are_returned_as_is(self)`
  - L70: `ShrinkImageTest.test_mime_is_detected_from_content(self)`
  - L77: `EmbedBudgetTest.test_over_budget_becomes_skipped_not_dropped(self)`
  - L87: `EmbedBudgetTest.test_within_budget_is_embedded(self)`
  - L95: `EmbedBudgetTest.test_broken_base64_is_skipped(self)`
  - L102: `DerivedMessageShrinksTest.test_derived_message_carries_a_shrunk_image(self)`
  - L118: `DerivedMessageShrinksTest.test_derived_message_keeps_plain_text_shape_when_no_attachment(self)`

### A.476 `tests/test_image_tool.py`

- 类型：Python
- 行数：436
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：工具返回图片：read_image → ToolResult.attachments → 模型可见的 image_url 块。
- 导入：`__future__`, `base64`, `struct`, `sys`, `unittest`, `zlib`, `pathlib`, `agent.capabilities.builtin`, `agent.capabilities.registry`, `agent.core.context`, `agent.core.events`, `agent.core.image_embed`, `agent.core.input_attachments`, `agent.core.session_log`, `agent.core.tool_call`
- 顶层符号：
  - L40: `def _png(w, h, rgb)`
  - L57: `def _img_blocks(content)`
  - L64: `class DescribeImageTest(unittest.TestCase)`
  - L88: `class BuildToolPartsTest(unittest.TestCase)`
  - L107: `class ToolContentTest(unittest.TestCase)`
  - L131: `class PipelineCarriesAttachmentsTest(unittest.TestCase)`
  - L163: `class ReadImageToolTest(unittest.TestCase)`
  - L245: `class StripProtectsToolImagesTest(unittest.TestCase)`
  - L318: `class AttachmentReferenceTest(unittest.TestCase)`
- 类成员：
  - L67: `DescribeImageTest.test_png_size(self)`
  - L71: `DescribeImageTest.test_gif_size(self)`
  - L76: `DescribeImageTest.test_unknown_bytes_report_no_mime(self)`
  - L91: `BuildToolPartsTest.test_parts_and_no_note_within_budget(self)`
  - L99: `BuildToolPartsTest.test_over_budget_reports_note(self)`
  - L110: `ToolContentTest.test_no_attachments_keeps_string(self)`
  - L115: `ToolContentTest.test_with_image_becomes_array(self)`
  - L123: `ToolContentTest.test_empty_text_with_image_gets_placeholder(self)`
  - L134: `PipelineCarriesAttachmentsTest._pipeline_with(self, plugin)`
  - L139: `PipelineCarriesAttachmentsTest.test_attachments_survive_pipeline(self)`
  - L150: `PipelineCarriesAttachmentsTest.test_plain_return_has_no_attachments(self)`
  - L166: `ReadImageToolTest.setUp(self)`
  - L171: `ReadImageToolTest.tearDown(self)`
  - L176: `ReadImageToolTest.test_reads_png_and_summarizes(self)`
  - L189: `ReadImageToolTest.test_default_keeps_original_size(self)`
  - L199: `ReadImageToolTest.test_explicit_max_side_reports_scale(self)`
  - L211: `ReadImageToolTest.test_projection_keeps_tool_chosen_size(self)`
  - L223: `ReadImageToolTest.test_missing_file_raises(self)`
  - L227: `ReadImageToolTest.test_non_image_raises(self)`
  - L234: `ReadImageToolTest.test_empty_path_raises(self)`
  - L238: `ReadImageToolTest.test_empty_file_raises(self)`
  - L251: `StripProtectsToolImagesTest._tool_msg(self, n_images)`
  - L257: `StripProtectsToolImagesTest._user_msg(self, text, n_images)`
  - L263: `StripProtectsToolImagesTest.test_tool_image_with_no_user_images_survives(self)`
  - L270: `StripProtectsToolImagesTest.test_tool_image_counts_toward_max(self)`
  - L278: `StripProtectsToolImagesTest.test_newest_user_image_wins_over_older_tool_image(self)`
  - L285: `StripProtectsToolImagesTest.test_newest_tool_image_wins_over_older_user_image(self)`
  - L292: `StripProtectsToolImagesTest.test_fifo_keeps_new_tool_image_and_drops_oldest_user_image(self)`
  - L300: `StripProtectsToolImagesTest.test_old_tool_image_survives_turn_window(self)`
  - L307: `StripProtectsToolImagesTest.test_excess_tool_image_is_stripped(self)`
  - L319: `AttachmentReferenceTest.test_placeholder_has_attachment_reference_and_request_cleans_it(self)`
  - L342: `AttachmentReferenceTest.test_read_image_rejects_repeated_attachment_in_same_turn(self)`
  - L390: `AttachmentReferenceTest.test_read_image_accepts_attachment_id_from_current_store(self)`

### A.477 `tests/test_image_turns.py`

- 类型：Python
- 行数：219
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：图片按「最近几轮用户发言」进请求：轮数由配置控制，事实流不受影响。
- 导入：`__future__`, `sys`, `unittest`, `pathlib`, `agent.core.image_embed`
- 顶层符号：
  - L24: `def _img_msg(text, n_images)`
  - L31: `def _count_images(messages)`
  - L40: `class StripByTurnTest(unittest.TestCase)`
  - L100: `class StripByTotalCapTest(unittest.TestCase)`
  - L167: `class DefaultBoundedTest(unittest.TestCase)`
  - L185: `class ConfigWiringTest(unittest.TestCase)`
- 类成员：
  - L43: `StripByTurnTest.test_keeps_only_recent_turns(self)`
  - L53: `StripByTurnTest.test_one_turn_with_three_images_counts_as_one_turn(self)`
  - L60: `StripByTurnTest.test_within_limit_is_untouched(self)`
  - L66: `StripByTurnTest.test_zero_turns_drops_every_image(self)`
  - L72: `StripByTurnTest.test_negative_means_no_limit(self)`
  - L78: `StripByTurnTest.test_text_only_messages_are_untouched(self)`
  - L85: `StripByTurnTest.test_defaults_are_bounded(self)`
  - L90: `StripByTurnTest.test_image_only_turn_keeps_a_placeholder(self)`
  - L103: `StripByTotalCapTest.test_cap_keeps_the_most_recent_turn_first(self)`
  - L111: `StripByTotalCapTest.test_oldest_turn_is_dropped_whole_before_touching_newer(self)`
  - L117: `StripByTotalCapTest.test_within_cap_touches_nothing(self)`
  - L123: `StripByTotalCapTest.test_one_turn_over_the_cap_keeps_the_tail_of_that_turn(self)`
  - L130: `StripByTotalCapTest.test_zero_cap_drops_everything(self)`
  - L136: `StripByTotalCapTest.test_negative_cap_means_no_limit(self)`
  - L142: `StripByTotalCapTest.test_cap_and_turns_apply_together(self)`
  - L149: `StripByTotalCapTest.test_placeholder_counts_the_dropped_blocks(self)`
  - L156: `StripByTotalCapTest.test_default_cap_is_eight(self)`
  - L159: `StripByTotalCapTest.test_default_call_applies_bounded_defaults(self)`
  - L170: `DefaultBoundedTest.test_default_is_bounded(self)`
  - L177: `DefaultBoundedTest.test_narrow_window_strips(self)`
  - L188: `ConfigWiringTest.test_default_config_value(self)`
  - L195: `ConfigWiringTest.test_module_receives_the_value(self)`
  - L205: `ConfigWiringTest.test_app_carries_the_value(self)`

### A.478 `tests/test_import_graph.py`

- 类型：Python
- 行数：68
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：依赖图不变量：环为零、装配根不被反向依赖、层序可机检。
- 导入：`__future__`, `subprocess`, `sys`, `unittest`, `pathlib`, `check_imports`
- 顶层符号：
  - L21: `class DependencyGraphTest(unittest.TestCase)`
- 类成员：
  - L24: `DependencyGraphTest.test_no_direction_violations(self)`
  - L27: `DependencyGraphTest.test_no_cycles(self)`
  - L30: `DependencyGraphTest.test_entry_is_the_top_layer(self)`
  - L36: `DependencyGraphTest.test_shell_does_not_import_the_composition_root(self)`
  - L51: `DependencyGraphTest.test_entry_may_import_the_composition_root(self)`

### A.479 `tests/test_invest_tools.py`

- 类型：Python
- 行数：450
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：调查与工具测试：定位族 / 文本数据 / 系统 / OCR / 网络 / 打包。
- 导入：`__future__`, `http.server`, `shutil`, `subprocess`, `sys`, `tempfile`, `threading`, `unittest`, `pathlib`, `agent.capabilities.builtin`, `agent.capabilities.registry`
- 顶层符号：
  - L33: `class FindInFileTest(unittest.TestCase)`
  - L96: `class RegexLocateTest(unittest.TestCase)`
  - L134: `class FileSearchTest(unittest.TestCase)`
  - L168: `class TextDataToolsTest(unittest.TestCase)`
  - L222: `class SystemToolsTest(unittest.TestCase)`
  - L283: `class _HtmlHandler(http.server.BaseHTTPRequestHandler)`
  - L298: `class WebToolsTest(unittest.TestCase)`
  - L353: `class OcrAndArchiveTest(unittest.TestCase)`
  - L409: `class BatchERegistrationTest(unittest.TestCase)`
- 类成员：
  - L36: `FindInFileTest.setUp(self)`
  - L43: `FindInFileTest.test_literal_or_and_occurrence(self)`
  - L51: `FindInFileTest.test_region_and_rowcols(self)`
  - L58: `FindInFileTest.test_not_found_and_out_of_range(self)`
  - L64: `FindInFileTest.test_blank_pattern_says_what_to_fix(self)`
  - L74: `FindInFileTest.test_path_is_dir_points_to_directory_tools(self)`
  - L83: `FindInFileTest.test_missing_file_is_not_reported_as_dir(self)`
  - L92: `FindInFileTest.test_regex_invalid(self)`
  - L99: `RegexLocateTest.setUp(self)`
  - L109: `RegexLocateTest.test_directory_recursive_and_glob(self)`
  - L115: `RegexLocateTest.test_limit_truncation(self)`
  - L120: `RegexLocateTest.test_blank_pattern_raises(self)`
  - L128: `RegexLocateTest.test_invalid_regex_and_limit(self)`
  - L137: `FileSearchTest.setUp(self)`
  - L146: `FileSearchTest.test_context_and_gitignore(self)`
  - L156: `FileSearchTest.test_blank_pattern_raises(self)`
  - L164: `FileSearchTest.test_limit(self)`
  - L171: `TextDataToolsTest.setUp(self)`
  - L176: `TextDataToolsTest.test_text_diff_file_vs_text(self)`
  - L190: `TextDataToolsTest.test_data_table_csv_actions(self)`
  - L211: `TextDataToolsTest.test_data_table_xlsx_dependency_path(self)`
  - L225: `SystemToolsTest.setUp(self)`
  - L230: `SystemToolsTest.test_env_probe_shape(self)`
  - L237: `SystemToolsTest.test_unified_diagnose_red_green(self)`
  - L253: `SystemToolsTest.test_git_workspace_modes(self)`
  - L284: `_HtmlHandler.do_GET(self)`
  - L295: `_HtmlHandler.log_message(self)`
  - L302: `WebToolsTest.setUpClass(cls)`
  - L309: `WebToolsTest.tearDownClass(cls)`
  - L312: `WebToolsTest.test_fetch_ok_and_checks(self)`
  - L327: `WebToolsTest.test_fetch_acceptance_failure_keeps_data(self)`
  - L336: `WebToolsTest.test_fetch_invalid_scheme(self)`
  - L342: `WebToolsTest.test_render_dependency_path(self)`
  - L356: `OcrAndArchiveTest.setUp(self)`
  - L361: `OcrAndArchiveTest.test_ocr_region_validation_and_dependency(self)`
  - L374: `OcrAndArchiveTest.test_archive_list_create_extract(self)`
  - L402: `OcrAndArchiveTest.test_archive_unknown_format(self)`
  - L412: `BatchERegistrationTest.test_batch_e_plugins_register(self)`
  - L437: `BatchERegistrationTest.test_archive_declares_write_path_keys(self)`

### A.480 `tests/test_kb_plugin.py`

- 类型：Python
- 行数：785
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：知识库插件测试。
- 导入：`__future__`, `importlib.util`, `json`, `shutil`, `sys`, `tempfile`, `types`, `unittest`, `pathlib`, `agent.app`, `agent.core.model_call`, `agent.mechanisms.context`, `agent.mechanisms.session_store`, `tests.testkit`
- 顶层符号：
  - L32: `def _load_plugin_module()`
  - L44: `def _make_tree(root)`
  - L55: `class KBRuntimeTest(unittest.TestCase)`
  - L226: `class KBConfigTest(unittest.TestCase)`
  - L295: `class ContextSourcesTest(unittest.TestCase)`
  - L325: `class _RecordingProvider()`
  - L335: `class InjectionTest(unittest.TestCase)`
  - L380: `class PluginSourceContractTest(unittest.TestCase)`
  - L494: `class PluginConfigIsolationTest(unittest.TestCase)`
  - L556: `class KnowledgeTextOnlyTest(unittest.TestCase)`
  - L611: `class KnowledgeExtraSuffixesTest(unittest.TestCase)`
  - L665: `class PluginPanelRenderContractTest(unittest.TestCase)`
  - L729: `class SkillsConfigSourceTest(unittest.TestCase)`
- 类成员：
  - L56: `KBRuntimeTest.setUp(self)`
  - L63: `KBRuntimeTest.test_resource_directory_lines_unconfigured(self)`
  - L69: `KBRuntimeTest.test_resource_directory_lines_configured(self)`
  - L74: `KBRuntimeTest.test_disabled_when_root_missing(self)`
  - L82: `KBRuntimeTest.test_safe_resolve_boundaries(self)`
  - L94: `KBRuntimeTest.test_file_allowed_size_and_hidden(self)`
  - L104: `KBRuntimeTest.test_read_text_plain_and_bad_bytes(self)`
  - L111: `KBRuntimeTest.test_read_text_xlsx_missing_lib(self)`
  - L125: `KBRuntimeTest.test_read_text_xlsx_fake_lib(self)`
  - L160: `KBRuntimeTest.test_set_checked_replace_filter_clear(self)`
  - L171: `KBRuntimeTest.test_persist_and_reload(self)`
  - L182: `KBRuntimeTest.test_get_checked_single_cid_recovery(self)`
  - L195: `KBRuntimeTest.test_build_system_messages_and_count(self)`
  - L207: `KBRuntimeTest.test_build_skips_over_limit_after_check(self)`
  - L215: `KBRuntimeTest.test_list_files_excludes_hidden_and_pycache(self)`
  - L232: `KBConfigTest.test_config_lives_in_the_plugin_directory(self)`
  - L240: `KBConfigTest.test_missing_section_disables(self)`
  - L247: `KBConfigTest.test_missing_file_disables(self)`
  - L253: `KBConfigTest.test_nonexistent_dir_disables_without_error(self)`
  - L264: `KBConfigTest.test_existing_dir_enables(self)`
  - L274: `KBConfigTest.test_values_tolerate_quotes_and_blank_lines(self)`
  - L288: `KBConfigTest.test_disabled_kb_returns_empty(self)`
  - L296: `ContextSourcesTest.test_order_and_disposer(self)`
  - L306: `ContextSourcesTest.test_exception_isolated(self)`
  - L317: `ContextSourcesTest.test_validation_and_empty_filter(self)`
  - L328: `_RecordingProvider.__init__(self)`
  - L331: `_RecordingProvider.stream(self, request)`
  - L336: `InjectionTest.setUp(self)`
  - L343: `InjectionTest.test_pipeline_refresh_and_replace(self)`
  - L364: `InjectionTest.test_turn_end_to_end_injection(self)`
  - L387: `PluginSourceContractTest._run(self, app, spy, cid)`
  - L393: `PluginSourceContractTest._app(self, root)`
  - L402: `PluginSourceContractTest.test_source_text_lands_in_the_knowledge_block(self)`
  - L421: `PluginSourceContractTest.test_source_is_refreshed_every_turn(self)`
  - L443: `PluginSourceContractTest.test_disposer_removes_the_source(self)`
  - L460: `PluginSourceContractTest.test_plugin_sources_do_not_touch_the_kernel(self)`
  - L471: `PluginSourceContractTest.test_segments_carry_their_own_name_and_prefix(self)`
  - L481: `PluginSourceContractTest.test_two_sources_of_one_plugin_stay_separate(self)`
  - L500: `PluginConfigIsolationTest.test_kernel_templates_have_no_plugin_section(self)`
  - L507: `PluginConfigIsolationTest.test_each_plugin_reads_its_own_config_file(self)`
  - L527: `PluginConfigIsolationTest.test_skills_dir_comes_from_its_own_config(self)`
  - L559: `KnowledgeTextOnlyTest._files(self, tmp)`
  - L569: `KnowledgeTextOnlyTest.test_text_suffix_rules(self)`
  - L580: `KnowledgeTextOnlyTest.test_binary_is_neither_listed_nor_selectable(self)`
  - L597: `KnowledgeTextOnlyTest.test_runtime_rejects_binary_check(self)`
  - L614: `KnowledgeExtraSuffixesTest._mod(self)`
  - L624: `KnowledgeExtraSuffixesTest.test_parse_forms(self)`
  - L633: `KnowledgeExtraSuffixesTest.test_extra_extends_the_whitelist(self)`
  - L639: `KnowledgeExtraSuffixesTest.test_config_key_is_read_and_used(self)`
  - L659: `KnowledgeExtraSuffixesTest.test_missing_key_keeps_default_whitelist(self)`
  - L672: `PluginPanelRenderContractTest._shell_js(self)`
  - L676: `PluginPanelRenderContractTest.test_open_pane_broadcasts_panel_opened(self)`
  - L683: `PluginPanelRenderContractTest.test_panel_has_a_refresh_button_on_the_subtitle(self)`
  - L696: `PluginPanelRenderContractTest.test_refresh_handler_re_renders(self)`
  - L703: `PluginPanelRenderContractTest.test_panels_render_on_the_event(self)`
  - L714: `PluginPanelRenderContractTest.test_knowledge_panel_matches_composite_dom_id(self)`
  - L732: `SkillsConfigSourceTest.test_plugin_dir_has_no_own_config(self)`
  - L738: `SkillsConfigSourceTest.test_reader_reads_the_project_config(self)`
  - L757: `SkillsConfigSourceTest.test_reader_takes_a_given_ini(self)`

### A.481 `tests/test_layout_min_width.py`

- 类型：Python
- 行数：33
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：对话区窄宽守卫：不锁固定最小宽度，输入区按钮组允许换行。
- 导入：`__future__`, `re`, `sys`, `unittest`, `pathlib`, `agent.shell.web.ui_bundle`
- 顶层符号：
  - L16: `class ChatMinWidthTest(unittest.TestCase)`
- 类成员：
  - L19: `ChatMinWidthTest._css(self)`
  - L22: `ChatMinWidthTest.test_chat_allows_narrow_layout(self)`
  - L26: `ChatMinWidthTest.test_composer_footer_wraps(self)`

### A.482 `tests/test_mode_note.py`

- 类型：Python
- 行数：207
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：执行模式是请求尾部的临时后缀：不进系统提示词、不进历史、不发事件。
- 导入：`__future__`, `sys`, `unittest`, `pathlib`, `agent.capabilities.registry`, `agent.core.modules`, `agent.shell.prompts`, `tests.testkit`
- 顶层符号：
  - L30: `def _empty_reg()`
  - L34: `class SystemPromptHasNoModeTest(unittest.TestCase)`
  - L78: `class ModeTailShapeTest(unittest.TestCase)`
  - L141: `class ModeIsNotPersistedTest(unittest.TestCase)`
- 类成员：
  - L37: `SystemPromptHasNoModeTest.test_resolved_system_prompt_has_no_mode(self)`
  - L43: `SystemPromptHasNoModeTest.test_switching_mode_keeps_system_prompt_byte_identical(self)`
  - L53: `SystemPromptHasNoModeTest.test_mode_note_still_differs_per_mode(self)`
  - L59: `SystemPromptHasNoModeTest.test_split_helper_drops_the_mode_section(self)`
  - L72: `SystemPromptHasNoModeTest.test_explicit_system_prompt_gets_no_note(self)`
  - L81: `ModeTailShapeTest._base(self)`
  - L89: `ModeTailShapeTest.test_note_is_appended_last(self)`
  - L98: `ModeTailShapeTest.test_switching_mode_changes_only_the_tail(self)`
  - L108: `ModeTailShapeTest.test_input_list_is_not_mutated(self)`
  - L114: `ModeTailShapeTest.test_empty_note_changes_nothing(self)`
  - L119: `ModeTailShapeTest.test_existing_runtime_tail_is_replaced_not_duplicated(self)`
  - L129: `ModeTailShapeTest.test_note_works_after_multimodal_tail(self)`
  - L144: `ModeIsNotPersistedTest.test_mode_note_is_system_role(self)`
  - L152: `ModeIsNotPersistedTest.test_no_event_carries_the_mode_note(self)`

### A.483 `tests/test_model_catalog.py`

- 类型：Python
- 行数：239
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：模型目录单元测试：替换语义、默认值、无效条目、热读与 provider 缓存。
- 导入：`__future__`, `unittest`, `unittest`, `agent.capabilities.model_catalog`, `agent.capabilities.plugins`, `agent.capabilities.registry`, `agent.mechanisms.providers.openai`
- 顶层符号：
  - L28: `def _entry(model_id)`
  - L36: `class ModelEntryTest(unittest.TestCase)`
  - L52: `class ModelCatalogTest(unittest.TestCase)`
  - L156: `class ProviderCacheTest(unittest.TestCase)`
  - L181: `class PluginContextCatalogTest(unittest.TestCase)`
  - L229: `class SnapshotShapeTest(unittest.TestCase)`
- 类成员：
  - L37: `ModelEntryTest.test_options_are_canonical_and_isolated(self)`
  - L47: `ModelEntryTest.test_bad_options_json_degrades_to_empty(self)`
  - L53: `ModelCatalogTest.setUp(self)`
  - L56: `ModelCatalogTest.test_unconfigured_catalog_is_empty_and_not_authoritative(self)`
  - L63: `ModelCatalogTest.test_default_prefers_flag_then_first(self)`
  - L73: `ModelCatalogTest.test_replacing_source_drops_removed_models(self)`
  - L79: `ModelCatalogTest.test_empty_replacement_flips_authoritative(self)`
  - L87: `ModelCatalogTest.test_second_distinct_source_is_rejected_without_clobbering(self)`
  - L94: `ModelCatalogTest.test_duplicate_ids_reject_the_whole_batch(self)`
  - L100: `ModelCatalogTest.test_unknown_provider_skips_only_that_entry(self)`
  - L108: `ModelCatalogTest.test_unknown_provider_only_means_not_authoritative(self)`
  - L114: `ModelCatalogTest.test_disposer_is_scoped_to_its_own_registration(self)`
  - L126: `ModelCatalogTest.test_hot_read_is_re_evaluated_each_snapshot(self)`
  - L133: `ModelCatalogTest.test_hot_read_failure_keeps_last_good_entries(self)`
  - L147: `ModelCatalogTest.test_hot_read_duplicate_ids_fall_back_to_last_good(self)`
  - L157: `ProviderCacheTest.setUp(self)`
  - L161: `ProviderCacheTest.test_provider_is_built_once_per_entry(self)`
  - L167: `ProviderCacheTest.test_option_change_invalidates_the_cached_provider(self)`
  - L176: `ProviderCacheTest.test_unknown_model_id_returns_none(self)`
  - L184: `PluginContextCatalogTest.setUp(self)`
  - L188: `PluginContextCatalogTest._ctx(self, name)`
  - L191: `PluginContextCatalogTest.test_missing_catalog_is_a_wiring_error(self)`
  - L196: `PluginContextCatalogTest.test_plugin_name_becomes_the_catalog_source(self)`
  - L203: `PluginContextCatalogTest.test_disposer_removes_only_its_own_source(self)`
  - L212: `PluginContextCatalogTest.test_second_plugin_source_is_reported_not_raised(self)`
  - L222: `PluginContextCatalogTest.test_hot_read_callback_is_accepted(self)`
  - L230: `SnapshotShapeTest.test_entry_lookup_ignores_surrounding_whitespace(self)`

### A.484 `tests/test_model_provider.py`

- 类型：Python
- 行数：661
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：模型 provider 的请求级模型选择。
- 导入：`__future__`, `json`, `shutil`, `sys`, `tempfile`, `time`, `unittest`, `pathlib`, `unittest`, `agent.core.ports`, `agent.mechanisms.providers.base`, `agent.mechanisms.providers.openai`, `tests.testkit`
- 顶层符号：
  - L32: `def _img()`
  - L37: `class _Capturing(OpenAICompatibleProvider)`
  - L48: `def _provider(model)`
  - L51: `class ProviderStreamTimeoutTest(unittest.TestCase)`
  - L74: `class RequestLevelModelTest(unittest.TestCase)`
  - L107: `class ImagesAlwaysReachTheWireTest(unittest.TestCase)`
  - L137: `class SessionModelSelectionTest(unittest.TestCase)`
  - L185: `class SessionStateFileTest(unittest.TestCase)`
  - L279: `class AppModelConfigTest(unittest.TestCase)`
  - L399: `class _RecordingRouter()`
  - L413: `class AvailableModelsWireTest(unittest.TestCase)`
  - L478: `class CatalogAuthorityAtAssemblyTest(unittest.TestCase)`
  - L525: `class UserFacingTextTest(unittest.TestCase)`
  - L567: `class ReasonNotReplayedTest(unittest.TestCase)`
  - L649: `class TurnStartAssemblyTest(unittest.TestCase)`
- 类成员：
  - L40: `_Capturing.__init__(self)`
  - L44: `_Capturing._post_stream(self, url, payload)`
  - L52: `ProviderStreamTimeoutTest.test_openai_stream_timeout_is_bounded(self)`
  - L76: `RequestLevelModelTest.test_request_model_wins_over_instance_default(self)`
  - L82: `RequestLevelModelTest.test_empty_request_model_falls_back_to_instance_default(self)`
  - L88: `RequestLevelModelTest.test_whitespace_is_treated_as_unspecified(self)`
  - L93: `RequestLevelModelTest.test_local_model_check_is_per_requested_model(self)`
  - L99: `RequestLevelModelTest.test_effort_still_reaches_the_wire(self)`
  - L115: `ImagesAlwaysReachTheWireTest.test_image_block_survives_into_the_payload(self)`
  - L131: `ImagesAlwaysReachTheWireTest.test_plain_text_message_is_untouched(self)`
  - L144: `SessionModelSelectionTest.setUp(self)`
  - L151: `SessionModelSelectionTest.tearDown(self)`
  - L154: `SessionModelSelectionTest._state(self, default_model)`
  - L159: `SessionModelSelectionTest.test_select_then_read_back(self)`
  - L166: `SessionModelSelectionTest.test_choice_survives_a_new_process(self)`
  - L172: `SessionModelSelectionTest.test_empty_clears_the_choice(self)`
  - L178: `SessionModelSelectionTest.test_read_only_is_never_used(self)`
  - L194: `SessionStateFileTest.setUp(self)`
  - L200: `SessionStateFileTest.tearDown(self)`
  - L203: `SessionStateFileTest._state(self, default_model)`
  - L211: `SessionStateFileTest._todo(self, items)`
  - L218: `SessionStateFileTest._read(self)`
  - L221: `SessionStateFileTest.test_file_nests_todo_and_keeps_state_flat(self)`
  - L236: `SessionStateFileTest.test_every_component_survives_a_new_process(self)`
  - L249: `SessionStateFileTest.test_closing_todo_does_not_wipe_the_model(self)`
  - L263: `SessionStateFileTest.test_stale_flat_file_is_ignored(self)`
  - L282: `AppModelConfigTest.setUp(self)`
  - L288: `AppModelConfigTest.tearDown(self)`
  - L291: `AppModelConfigTest._app(self)`
  - L307: `AppModelConfigTest.test_model_catalog_is_optional(self)`
  - L317: `AppModelConfigTest.test_model_config_reports_source_and_degrade(self)`
  - L331: `AppModelConfigTest.test_unknown_session_model_falls_back_to_default(self)`
  - L339: `AppModelConfigTest.test_known_session_model_is_kept(self)`
  - L345: `AppModelConfigTest.test_reload_is_ignored_when_catalog_is_authoritative(self)`
  - L352: `AppModelConfigTest.test_catalog_snapshot_failure_is_non_authoritative(self)`
  - L367: `AppModelConfigTest.test_reload_without_catalog_returns_plugin_managed_note(self)`
  - L372: `AppModelConfigTest.test_refresh_switches_catalog_on_and_off(self)`
  - L402: `_RecordingRouter.__init__(self)`
  - L406: `_RecordingRouter.reload_default(self, provider)`
  - L409: `_RecordingRouter.reload_policy(self)`
  - L420: `AvailableModelsWireTest._app(self)`
  - L430: `AvailableModelsWireTest.test_health_lists_all_configured_models(self)`
  - L437: `AvailableModelsWireTest.test_current_model_is_always_in_the_list(self)`
  - L448: `AvailableModelsWireTest.test_shell_health_also_lists_all_models(self)`
  - L456: `AvailableModelsWireTest.test_health_does_not_invent_a_model_in_degraded_state(self)`
  - L469: `AvailableModelsWireTest._assert_complete(self, body, provider_model)`
  - L496: `CatalogAuthorityAtAssemblyTest.test_catalog_entries_become_the_model_list(self)`
  - L537: `UserFacingTextTest.test_http_hints_are_user_facing_and_history_free(self)`
  - L550: `UserFacingTextTest.test_500_and_503_name_the_model_server(self)`
  - L557: `UserFacingTextTest.test_deepseek_official_error_codes_are_mapped(self)`
  - L574: `ReasonNotReplayedTest._sample(self)`
  - L585: `ReasonNotReplayedTest.test_cut_clears_the_content_but_keeps_the_key_for_tool_messages(self)`
  - L593: `ReasonNotReplayedTest.test_plain_assistant_before_the_cut_drops_the_key(self)`
  - L604: `ReasonNotReplayedTest.test_tool_message_without_reasoning_gets_an_empty_key(self)`
  - L616: `ReasonNotReplayedTest.test_cut_none_keeps_everything(self)`
  - L622: `ReasonNotReplayedTest.test_tool_calls_survive_the_cut(self)`
  - L630: `ReasonNotReplayedTest.test_original_messages_are_not_mutated(self)`
  - L637: `ReasonNotReplayedTest.test_provider_passes_the_boundary_and_defaults_to_stripping(self)`
  - L652: `TurnStartAssemblyTest.test_model_module_marks_turn_start(self)`
  - L656: `TurnStartAssemblyTest.test_port_default_keeps_everything(self)`

### A.485 `tests/test_model_window.py`

- 类型：Python
- 行数：147
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：上下文窗口属于模型：配置读取、目录条目与按会话解析。
- 导入：`__future__`, `sys`, `unittest`, `pathlib`, `agent.capabilities.model_catalog`, `agent.config`
- 顶层符号：
  - L24: `class _AppWindowTest(unittest.TestCase)`
  - L110: `class CompressionThresholdTest(unittest.TestCase)`
  - L126: `class EntryWindowTest(unittest.TestCase)`
- 类成员：
  - L25: `_AppWindowTest._app(self, entries, default_model)`
  - L42: `_AppWindowTest.test_catalog_entry_window_wins(self)`
  - L56: `_AppWindowTest.test_entry_without_window_uses_the_shared_default(self)`
  - L62: `_AppWindowTest.test_stale_model_converges_to_the_default_window(self)`
  - L71: `_AppWindowTest.test_compression_percent_comes_from_the_current_model(self)`
  - L79: `_AppWindowTest.test_compression_percent_defaults_to_70(self)`
  - L86: `_AppWindowTest.test_compression_threshold_uses_the_model_percent(self)`
  - L94: `_AppWindowTest.test_compression_threshold_falls_back_without_a_window(self)`
  - L100: `_AppWindowTest.test_context_layout_budget_uses_the_model_threshold(self)`
  - L111: `CompressionThresholdTest.test_window_percent(self)`
  - L117: `CompressionThresholdTest.test_missing_window_uses_fallback(self)`
  - L121: `CompressionThresholdTest.test_bad_percent_uses_70(self)`
  - L127: `EntryWindowTest.test_entry_exposes_the_window(self)`
  - L132: `EntryWindowTest.test_bad_metadata_is_zero_not_an_exception(self)`
  - L137: `EntryWindowTest.test_compression_percent_defaults_and_clamps(self)`

### A.486 `tests/test_multi_model_plugin.py`

- 类型：Python
- 行数：443
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：多模型插件：配置解析、目录回调与 `/catalog` 响应。
- 导入：`__future__`, `contextlib`, `importlib.util`, `io`, `json`, `re`, `sys`, `tempfile`, `unittest`, `pathlib`
- 顶层符号：
  - L27: `def _load_plugin_module()`
  - L39: `class _Ctx()`
  - L68: `class _ConfigCase(unittest.TestCase)`
  - L94: `class ParseTest(_ConfigCase)`
  - L326: `class CatalogPayloadTest(_ConfigCase)`
  - L356: `class RegisterTest(_ConfigCase)`
  - L406: `class PickerStyleTest(unittest.TestCase)`
- 类成员：
  - L42: `_Ctx.__init__(self)`
  - L48: `_Ctx._disposer(self)`
  - L53: `_Ctx.add_model_catalog(self, entries)`
  - L57: `_Ctx.add_route(self, method, path, handler)`
  - L61: `_Ctx.add_settings_panel(self, panel_id, title)`
  - L64: `_Ctx.add_ui_item(self, path, kind, props, order)`
  - L69: `_ConfigCase.setUp(self)`
  - L75: `_ConfigCase.write(self, text)`
  - L89: `_ConfigCase.parse(self, text)`
  - L95: `ParseTest.test_missing_file_is_empty_not_an_error(self)`
  - L100: `ParseTest.test_openai_defaults_and_first_entry_is_default(self)`
  - L116: `ParseTest.test_utf8_bom_is_accepted(self)`
  - L130: `ParseTest.test_context_window_is_carried_as_entry_metadata(self)`
  - L141: `ParseTest.test_bad_context_window_invalidates_the_entry(self)`
  - L151: `ParseTest.test_missing_context_window_invalidates_the_entry(self)`
  - L161: `ParseTest.test_compression_percent_defaults_to_70(self)`
  - L169: `ParseTest.test_compression_percent_rejects_out_of_range(self)`
  - L177: `ParseTest.test_anthropic_options_are_typed(self)`
  - L192: `ParseTest.test_anthropic_options_are_ignored_for_openai(self)`
  - L206: `ParseTest.test_bad_entry_does_not_hide_good_ones(self)`
  - L217: `ParseTest.test_missing_credentials_invalidates_only_that_entry(self)`
  - L226: `ParseTest.test_bad_numbers_invalidate_the_entry(self)`
  - L236: `ParseTest.test_bad_thinking_flag_invalidates_the_entry(self)`
  - L244: `ParseTest.test_multiple_defaults_keep_the_first(self)`
  - L251: `ParseTest.test_no_default_marks_the_first_entry(self)`
  - L258: `ParseTest.test_duplicate_section_is_a_file_level_error(self)`
  - L270: `ParseTest.test_placeholder_keys_are_rejected(self)`
  - L281: `ParseTest.test_same_vendor_twice_with_distinct_ids(self)`
  - L298: `ParseTest.test_bad_default_flag_keeps_entry_non_default(self)`
  - L306: `ParseTest.test_diagnostic_points_at_file_section_and_key(self)`
  - L317: `ParseTest.test_malformed_file_is_reported_not_raised(self)`
  - L327: `CatalogPayloadTest.test_payload_carries_no_credentials(self)`
  - L347: `CatalogPayloadTest.test_invalid_entries_are_exposed_for_ops(self)`
  - L357: `RegisterTest.setUp(self)`
  - L363: `RegisterTest.test_register_contributes_catalog_route_and_boot_script(self)`
  - L381: `RegisterTest.test_catalog_callback_hot_reads_the_file(self)`
  - L394: `RegisterTest.test_reregister_does_not_duplicate_defaults(self)`
  - L414: `PickerStyleTest.setUp(self)`
  - L418: `PickerStyleTest._rule(self, selector)`
  - L422: `PickerStyleTest.test_button_has_no_width_cap(self)`
  - L427: `PickerStyleTest.test_menu_grows_with_its_items(self)`
  - L433: `PickerStyleTest.test_names_and_ids_are_not_ellipsized(self)`

### A.487 `tests/test_path_registry.py`

- 类型：Python
- 行数：46
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：插件路径注册表与插口协议。
- 导入：`__future__`, `unittest`, `agent.capabilities.path_registry`
- 顶层符号：
  - L10: `class PathRegistryTest(unittest.TestCase)`
- 类成员：
  - L11: `PathRegistryTest.setUp(self)`
  - L21: `PathRegistryTest.test_registers_path_and_cleans_owner(self)`
  - L31: `PathRegistryTest.test_rejects_arbitrary_child_and_kind(self)`

### A.488 `tests/test_plugin_assembly.py`

- 类型：Python
- 行数：186
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：插件目录自包含的启动期装配覆盖。
- 导入：`__future__`, `json`, `tempfile`, `unittest`, `pathlib`, `agent.boot.plugin_assembly`, `agent.core.slot`, `agent.core.slot_tree`
- 顶层符号：
  - L15: `def make_base(ctx)`
  - L19: `def make_group(ctx)`
  - L23: `class PluginAssemblyTest(unittest.TestCase)`
- 类成员：
  - L24: `PluginAssemblyTest.setUp(self)`
  - L48: `PluginAssemblyTest.tearDown(self)`
  - L51: `PluginAssemblyTest._plugin(self, name)`
  - L65: `PluginAssemblyTest.test_assembly_file_replaces_startup_node(self)`
  - L87: `PluginAssemblyTest.test_metadata_patch_keeps_base_factory(self)`
  - L98: `PluginAssemblyTest.test_manifest_disable_wins(self)`
  - L107: `PluginAssemblyTest.test_auto_load_without_assembly_only_adds_manifest(self)`
  - L113: `PluginAssemblyTest.test_auto_loaded_plugin_registers_without_manifest_entry(self)`
  - L123: `PluginAssemblyTest.test_boot_app_loads_auto_plugin_with_empty_manifest(self)`
  - L141: `PluginAssemblyTest.test_factory_cannot_escape_plugin_root(self)`
  - L149: `PluginAssemblyTest.test_frozen_subtree_cannot_be_replaced(self)`
  - L159: `PluginAssemblyTest.test_new_node_can_be_appended(self)`
  - L173: `PluginAssemblyTest.test_duplicate_override_requires_replace(self)`

### A.489 `tests/test_plugin_bind.py`

- 类型：Python
- 行数：43
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：插件通过公开 API 绑定任意暴露 slot。
- 导入：`__future__`, `unittest`, `types`, `agent.capabilities.plugin_context`, `agent.capabilities.registry`, `agent.capabilities.slot_registry`
- 顶层符号：
  - L13: `class PluginBindTest(unittest.TestCase)`
- 类成员：
  - L14: `PluginBindTest.test_bind_route_slot(self)`
  - L25: `PluginBindTest.test_bind_route_uses_canonical_key(self)`
  - L34: `PluginBindTest.test_bind_unknown_path_rejected(self)`

### A.490 `tests/test_plugin_context_replace.py`

- 类型：Python
- 行数：53
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：插件 UI 贡献替换：同路径替换、旧实现回退、disposer 顺序。
- 导入：`__future__`, `unittest`, `agent.capabilities.plugin_context`, `agent.core.slot_tree`
- 顶层符号：
  - L11: `class _FakeUi()`
  - L29: `class PluginContextReplaceTest(unittest.TestCase)`
- 类成员：
  - L12: `_FakeUi.__init__(self)`
  - L16: `_FakeUi.add_item(self, path)`
  - L30: `PluginContextReplaceTest.test_ui_item_replace_restores_previous_owner(self)`

### A.491 `tests/test_plugin_contributions.py`

- 类型：Python
- 行数：331
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：插件贡献面测试。
- 导入：`__future__`, `inspect`, `sys`, `tempfile`, `unittest`, `pathlib`, `types`, `typing`, `agent.capabilities.contributions`, `agent.capabilities.plugins`, `agent.capabilities.registry`, `agent.mechanisms.context`
- 顶层符号：
  - L30: `def _host(tmp)`
  - L40: `class ContributionRegistryTest(unittest.TestCase)`
  - L124: `class PluginContextContributionTest(unittest.TestCase)`
  - L259: `class PluginAssetUrlTest(unittest.TestCase)`
  - L276: `class ExternalPluginRootAssetTest(unittest.TestCase)`
- 类成员：
  - L41: `ContributionRegistryTest.setUp(self)`
  - L49: `ContributionRegistryTest.test_route_exact_match(self)`
  - L58: `ContributionRegistryTest.test_route_path_parameter(self)`
  - L64: `ContributionRegistryTest.test_route_multi_segment_parameter(self)`
  - L70: `ContributionRegistryTest.test_route_segment_count_must_match(self)`
  - L75: `ContributionRegistryTest.test_route_exact_wins_over_parameter(self)`
  - L83: `ContributionRegistryTest.test_route_methods_supported(self)`
  - L89: `ContributionRegistryTest.test_route_rejects_bad_paths(self)`
  - L95: `ContributionRegistryTest.test_route_rejects_bad_parameter_name(self)`
  - L101: `ContributionRegistryTest.test_route_rejects_bad_plugin_and_method(self)`
  - L109: `ContributionRegistryTest.test_route_duplicate_rejected(self)`
  - L118: `ContributionRegistryTest.test_drop_plugin_removes_routes(self)`
  - L125: `PluginContextContributionTest.setUp(self)`
  - L132: `PluginContextContributionTest._ctx(self, name)`
  - L136: `PluginContextContributionTest.test_ctx_namespaces_routes_by_plugin(self)`
  - L144: `PluginContextContributionTest.test_register_fail_after_add_route_rolls_back(self)`
  - L159: `PluginContextContributionTest.test_ctx_add_context_source_returns_disposer(self)`
  - L168: `PluginContextContributionTest.test_context_path_parameters_are_required(self)`
  - L175: `PluginContextContributionTest.test_runtime_contributions_default_non_master(self)`
  - L189: `PluginContextContributionTest.test_invalid_runtime_contribution_does_not_kill_plugin(self)`
  - L201: `PluginContextContributionTest.test_direct_contribution_honors_master(self)`
  - L213: `PluginContextContributionTest.test_ctx_add_context_source_requires_path(self)`
  - L218: `PluginContextContributionTest.test_plugin_missing_path_rejects_load(self)`
  - L233: `PluginContextContributionTest.test_data_dir_is_per_plugin_and_created(self)`
  - L243: `PluginContextContributionTest.test_data_dir_sanitizes_plugin_name(self)`
  - L251: `PluginContextContributionTest.test_data_dir_none_without_host_root(self)`
  - L255: `PluginContextContributionTest.test_data_dir_path_is_absolute(self)`
  - L262: `PluginAssetUrlTest.test_asset_rel_parsing(self)`
  - L279: `ExternalPluginRootAssetTest.test_plugin_asset_uses_tracked_root(self)`

### A.492 `tests/test_plugin_http.py`

- 类型：Python
- 行数：372
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：插件 web 接口的 HTTP 层测试。
- 导入：`__future__`, `json`, `os`, `socket`, `sys`, `tempfile`, `threading`, `unittest`, `urllib.error`, `urllib.request`, `pathlib`, `typing`, `unittest`, `agent.app`, `agent.shell.web`, `agent.shell.web.ui_bundle`, `tests.testkit`
- 顶层符号：
  - L97: `def _free_port()`
  - L103: `class PluginHttpTest(unittest.TestCase)`
- 类成员：
  - L107: `PluginHttpTest.setUpClass(cls)`
  - L137: `PluginHttpTest.tearDownClass(cls)`
  - L148: `PluginHttpTest.req(self, method, path, payload)`
  - L171: `PluginHttpTest.test_panel_style_served_as_css(self)`
  - L178: `PluginHttpTest.test_shell_public_stylesheet_does_not_carry_plugin_styles(self)`
  - L191: `PluginHttpTest.test_plugin_style_source_declares_its_own_classes(self)`
  - L197: `PluginHttpTest.test_checked_files_reach_the_context(self)`
  - L236: `PluginHttpTest.test_plugin_panel_logic_lives_in_the_plugin(self)`
  - L255: `PluginHttpTest.test_panel_script_served_as_javascript(self)`
  - L263: `PluginHttpTest.test_post_creates_and_receives_body_and_query(self)`
  - L271: `PluginHttpTest.test_get_list_and_path_parameter(self)`
  - L284: `PluginHttpTest.test_put_updates_via_path_parameter(self)`
  - L293: `PluginHttpTest.test_delete_removes(self)`
  - L305: `PluginHttpTest.test_asset_served_as_javascript(self)`
  - L311: `PluginHttpTest.test_asset_rejects_non_whitelisted_type(self)`
  - L315: `PluginHttpTest.test_asset_rejects_escape(self)`
  - L325: `PluginHttpTest.test_unknown_path_and_plugin_are_404(self)`
  - L333: `PluginHttpTest.test_404_lists_available_endpoints(self)`
  - L340: `PluginHttpTest.test_parameter_route_does_not_capture_wrong_method(self)`
  - L348: `PluginHttpTest.test_handler_exception_does_not_kill_shell(self)`

### A.493 `tests/test_plugin_ui_files.py`

- 类型：Python
- 行数：32
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：插件 UI 声明的命名与顶层 kind 约定。
- 导入：`__future__`, `json`, `unittest`, `pathlib`
- 顶层符号：
  - L14: `class PluginUiFileTest(unittest.TestCase)`
- 类成员：
  - L15: `PluginUiFileTest.test_every_plugin_has_one_ui_fragment(self)`
  - L25: `PluginUiFileTest.test_no_stale_ui_filenames(self)`

### A.494 `tests/test_plugins.py`

- 类型：Python
- 行数：540
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：插件加载器测试。
- 导入：`__future__`, `sys`, `tempfile`, `unittest`, `pathlib`, `types`, `unittest`, `agent.capabilities.plugins`, `agent.capabilities.registry`, `agent.config`, `agent.core.tool_call`, `agent.shell.settings_panel`
- 顶层符号：
  - L44: `class PluginHostTest(unittest.TestCase)`
  - L254: `class PluginGateTest(unittest.TestCase)`
  - L317: `class PluginIdentityFallbackTest(unittest.TestCase)`
  - L381: `class ConfigParseTest(unittest.TestCase)`
  - L513: `class AppWiringTest(unittest.TestCase)`
- 类成员：
  - L47: `PluginHostTest.setUp(self)`
  - L55: `PluginHostTest._write_plugin(self, name, source)`
  - L62: `PluginHostTest.test_discover_filters(self)`
  - L73: `PluginHostTest.test_discover_missing_dir(self)`
  - L80: `PluginHostTest.test_load_enabled_filters_by_whitelist(self)`
  - L90: `PluginHostTest.test_unknown_name_reports_error(self)`
  - L95: `PluginHostTest.test_reload_skips_loaded(self)`
  - L103: `PluginHostTest.test_register_via_ctx_returns_none(self)`
  - L116: `PluginHostTest.test_returned_disposer_list_reverse_order(self)`
  - L134: `PluginHostTest.test_register_raises_rolls_back(self)`
  - L157: `PluginHostTest.test_broken_import_isolated(self)`
  - L167: `PluginHostTest.test_missing_register_reports_error(self)`
  - L174: `PluginHostTest.test_module_namespace_and_unload(self)`
  - L182: `PluginHostTest.test_relative_submodule_import(self)`
  - L200: `PluginHostTest.test_unload_all_idempotent(self)`
  - L210: `PluginHostTest.test_reports_accumulate(self)`
  - L219: `PluginHostTest.test_plugin_tool_runs_via_pipeline(self)`
  - L257: `PluginGateTest.setUp(self)`
  - L265: `PluginGateTest._write_plugin(self, name, source)`
  - L270: `PluginGateTest.test_pre_gate_blocks_then_unload_releases(self)`
  - L284: `PluginGateTest.test_missing_pipeline_guards_and_post_observer(self)`
  - L307: `PluginGateTest.test_gate_rollback_on_register_error(self)`
  - L321: `PluginIdentityFallbackTest._plugin(root, name)`
  - L327: `PluginIdentityFallbackTest.test_meta_supplies_identity_when_config_is_absent(self)`
  - L341: `PluginIdentityFallbackTest.test_identity_ignores_plugin_config(self)`
  - L355: `PluginIdentityFallbackTest.test_no_files_falls_back_to_folder_name(self)`
  - L363: `PluginIdentityFallbackTest.test_list_plugins_shows_declared_name_without_a_config(self)`
  - L382: `ConfigParseTest.test_get_plugins_parse(self)`
  - L409: `ConfigParseTest.test_profile_overlay_overrides_named_fields(self)`
  - L431: `ConfigParseTest.test_tree_only_rejects_external_path(self)`
  - L460: `ConfigParseTest.test_load_logs_source_integrity(self)`
  - L482: `ConfigParseTest.test_load_manifest_resolves_paths_and_reports_errors(self)`
  - L514: `AppWiringTest.test_build_app_loads_whitelisted_plugin(self)`
  - L529: `AppWiringTest.test_build_app_empty_whitelist_noop(self)`

### A.495 `tests/test_present_tool.py`

- 类型：Python
- 行数：46
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：present 工具：只返回文件元信息，不读取正文。
- 导入：`__future__`, `sys`, `tempfile`, `unittest`, `pathlib`, `agent.capabilities.builtin.present_tool`
- 顶层符号：
  - L16: `class PresentToolTest(unittest.TestCase)`
- 类成员：
  - L17: `PresentToolTest.test_returns_metadata_without_reading_content(self)`
  - L35: `PresentToolTest.test_rejects_missing_and_empty_lists(self)`

### A.496 `tests/test_prompt_sections.py`

- 类型：Python
- 行数：39
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：系统提示词章节：同章节合并，注入位置在工具速查之前。
- 导入：`__future__`, `sys`, `unittest`, `pathlib`, `agent.capabilities.registry`, `agent.mechanisms.prompt_sections`, `agent.shell.prompts`
- 顶层符号：
  - L17: `class PromptSectionsTest(unittest.TestCase)`
- 类成员：
  - L20: `PromptSectionsTest.test_same_heading_is_merged_once(self)`
  - L27: `PromptSectionsTest.test_extra_sections_sit_inside_the_system_prompt(self)`

### A.497 `tests/test_prompt_slot.py`

- 类型：Python
- 行数：26
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：系统提示词 assemble 插口替换测试。
- 导入：`__future__`, `unittest`, `agent.capabilities.slot_registry`, `agent.mechanisms.prompt_sections`
- 顶层符号：
  - L11: `class PromptSlotTest(unittest.TestCase)`
- 类成员：
  - L12: `PromptSlotTest.test_replace_prompt_assembly(self)`

### A.498 `tests/test_prompt_tail.py`

- 类型：Python
- 行数：54
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：请求尾部注册表：顺序、幂等撤销、来源异常隔离。
- 导入：`__future__`, `sys`, `unittest`, `pathlib`, `agent.mechanisms.prompt_tail`
- 顶层符号：
  - L16: `class PromptTailTest(unittest.TestCase)`
- 类成员：
  - L17: `PromptTailTest.test_renders_in_registration_order_and_disposes_idempotently(self)`
  - L26: `PromptTailTest.test_failing_source_does_not_block_other_sources(self)`
  - L34: `PromptTailTest.test_subagent_hidden_source_is_not_rendered(self)`
  - L41: `PromptTailTest.test_empty_source_does_not_add_separator(self)`
  - L47: `PromptTailTest.test_non_callable_source_is_rejected(self)`

### A.499 `tests/test_protocol_contract.py`

- 类型：Python
- 行数：299
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：HTTP/SSE 协议契约测试。
- 导入：`__future__`, `atexit`, `inspect`, `shutil`, `sys`, `tempfile`, `unittest`, `pathlib`, `agent.app`, `agent.core`, `agent.mechanisms.providers.echo`, `agent.shell.web.ui_bundle`
- 顶层符号：
  - L29: `def _isolation_root()`
  - L42: `def _isolated_app()`
  - L114: `class EventVocabularyTest(unittest.TestCase)`
  - L141: `class KernelEventEmissionTest(unittest.TestCase)`
  - L194: `class AssetReusePolicyTest(unittest.TestCase)`
  - L225: `class UiStateContractTest(unittest.TestCase)`
  - L258: `class SessionIsolationContractTest(unittest.TestCase)`
- 类成员：
  - L117: `EventVocabularyTest.test_frontend_consumed_set_is_fully_mapped(self)`
  - L123: `EventVocabularyTest.test_no_source_type_mapped_to_unknown_new_event(self)`
  - L136: `EventVocabularyTest.test_ignored_source_types_are_explicitly_dropped(self)`
  - L145: `KernelEventEmissionTest.setUpClass(cls)`
  - L152: `KernelEventEmissionTest.test_core_structural_events_emitted(self)`
  - L165: `KernelEventEmissionTest.test_tool_and_message_events_emitted(self)`
  - L171: `KernelEventEmissionTest.test_every_event_carries_conversation_id(self)`
  - L184: `KernelEventEmissionTest.test_event_envelope_is_type_plus_data(self)`
  - L197: `AssetReusePolicyTest.test_media_and_markdown_rendering_is_frontend_side(self)`
  - L211: `AssetReusePolicyTest.test_media_embedding_uses_markdown_syntax(self)`
  - L228: `UiStateContractTest.test_transient_ui_state_is_per_session(self)`
  - L241: `UiStateContractTest.test_usage_and_reasoning_are_provider_side(self)`
  - L260: `SessionIsolationContractTest.setUp(self)`
  - L265: `SessionIsolationContractTest.test_events_of_two_sessions_carry_distinct_cids(self)`
  - L272: `SessionIsolationContractTest.test_confirm_id_is_session_scoped(self)`

### A.500 `tests/test_provider_meta.py`

- 类型：Python
- 行数：132
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：`provider_meta` 透传契约。
- 导入：`__future__`, `unittest`, `agent.core.event_name`, `agent.core.events`, `agent.core.model_call`, `agent.core.modules.model_mod`, `agent.core.ports`, `agent.core.session_log`
- 顶层符号：
  - L24: `class _ScriptedProvider()`
  - L36: `class _ModelMessageCase(unittest.TestCase)`
  - L47: `class LlmEventModelTest(unittest.TestCase)`
  - L64: `class ModelMessageMetaTest(_ModelMessageCase)`
  - L90: `class DeriveMessagesMetaTest(unittest.TestCase)`
  - L117: `class OpenAiWireNeverSeesMetaTest(unittest.TestCase)`
- 类成员：
  - L29: `_ScriptedProvider.__init__(self, deltas)`
  - L32: `_ScriptedProvider.stream(self, request)`
  - L37: `_ModelMessageCase._model_message(self, deltas)`
  - L50: `LlmEventModelTest.test_done_reports_request_model(self)`
  - L65: `ModelMessageMetaTest.test_meta_delta_is_collected_verbatim(self)`
  - L77: `ModelMessageMetaTest.test_no_meta_delta_leaves_the_key_absent(self)`
  - L82: `ModelMessageMetaTest.test_later_meta_wins_on_shared_keys(self)`
  - L91: `DeriveMessagesMetaTest.test_provider_meta_survives_replay(self)`
  - L101: `DeriveMessagesMetaTest.test_old_logs_without_the_key_still_derive(self)`
  - L107: `DeriveMessagesMetaTest.test_unknown_subkeys_are_carried_not_validated(self)`
  - L118: `OpenAiWireNeverSeesMetaTest.test_wire_messages_strip_provider_meta(self)`

### A.501 `tests/test_provider_router.py`

- 类型：Python
- 行数：154
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：模型路由测试：按 id 分发、默认回落、非权威兜底、未知 id 报错、热换默认实例。
- 导入：`__future__`, `unittest`, `types`, `agent.core.model_call`, `agent.mechanisms.provider_router`, `agent.mechanisms.providers.base`
- 顶层符号：
  - L13: `class _FakeProvider()`
  - L26: `def _request(model)`
  - L30: `def _drain(router, model)`
  - L34: `class RoutedStreamTest(unittest.TestCase)`
- 类成员：
  - L16: `_FakeProvider.__init__(self, name)`
  - L21: `_FakeProvider.stream(self, request)`
  - L35: `RoutedStreamTest.setUp(self)`
  - L42: `RoutedStreamTest._router(self)`
  - L50: `RoutedStreamTest.test_routes_to_the_requested_model(self)`
  - L56: `RoutedStreamTest.test_empty_model_falls_back_to_default_id_resolution(self)`
  - L63: `RoutedStreamTest.test_router_without_default_id_uses_default_instance(self)`
  - L69: `RoutedStreamTest.test_unknown_model_raises_instead_of_silently_using_default(self)`
  - L77: `RoutedStreamTest.test_fallback_applies_only_to_allowed_ids(self)`
  - L86: `RoutedStreamTest.test_fallback_is_off_by_default(self)`
  - L91: `RoutedStreamTest.test_catalog_id_is_rewritten_to_the_provider_model_name(self)`
  - L104: `RoutedStreamTest.test_provider_without_model_name_gets_the_request_unchanged(self)`
  - L112: `RoutedStreamTest.test_allowed_models_is_an_immutable_record(self)`
  - L117: `RoutedStreamTest.test_model_property_prefers_default_id(self)`
  - L121: `RoutedStreamTest.test_reload_default_takes_effect_on_the_next_request(self)`
  - L128: `RoutedStreamTest.test_reload_policy_updates_model_and_allowed_models(self)`
  - L135: `RoutedStreamTest.test_reload_policy_can_disable_fallback(self)`
  - L143: `RoutedStreamTest.test_reload_default_is_visible_through_default_provider(self)`

### A.502 `tests/test_quality_pipeline.py`

- 类型：Python
- 行数：288
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：质量管线测试：写前 gate / 写中 inspect / 写后 feedback 三段。
- 导入：`__future__`, `sys`, `tempfile`, `unittest`, `pathlib`, `typing`, `agent.mechanisms.quality`, `tests.gate_fixtures`
- 顶层符号：
  - L24: `class QualityPipelineTest(unittest.TestCase)`
  - L204: `class RereadAnchorTest(unittest.TestCase)`
- 类成员：
  - L27: `QualityPipelineTest.setUp(self)`
  - L33: `QualityPipelineTest._ready(self, path, content)`
  - L39: `QualityPipelineTest._wc(self, cid)`
  - L44: `QualityPipelineTest.test_path_required(self)`
  - L52: `QualityPipelineTest.test_path_format_equivalent(self)`
  - L62: `QualityPipelineTest.test_intent_evidence_gate(self)`
  - L72: `QualityPipelineTest.test_intent_switch_resets_evidence(self)`
  - L85: `QualityPipelineTest.test_apply_patch_channel(self)`
  - L103: `QualityPipelineTest.test_large_diff_blocked(self)`
  - L120: `QualityPipelineTest.test_large_delete_flag(self)`
  - L131: `QualityPipelineTest.test_review_clears_large_delete_not_diag(self)`
  - L145: `QualityPipelineTest.test_post_write_checks_py(self)`
  - L162: `QualityPipelineTest.test_post_write_checks_json(self)`
  - L174: `QualityPipelineTest.test_report_structure(self)`
  - L192: `QualityPipelineTest.test_assistant_claim_fixed(self)`
  - L207: `RereadAnchorTest.setUp(self)`
  - L213: `RereadAnchorTest._commit_after_write(self, path, args, tool)`
  - L220: `RereadAnchorTest.test_literal_anchor_shows_current_line(self)`
  - L234: `RereadAnchorTest.test_anchor_follows_file_not_stale_number(self)`
  - L244: `RereadAnchorTest.test_anchor_reports_missing_old_text(self)`
  - L256: `RereadAnchorTest.test_anchor_reports_stale_line_range(self)`
  - L268: `RereadAnchorTest.test_anchor_for_whole_file_write(self)`
  - L277: `RereadAnchorTest.test_anchor_when_file_missing(self)`

### A.503 `tests/test_queue_runner.py`

- 类型：Python
- 行数：105
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：挂起回合不得消费待发送队列。
- 导入：`__future__`, `sys`, `unittest`, `pathlib`, `agent.mechanisms.conversation_queue`, `agent.mechanisms.mesh`, `agent.shell.session.runner`
- 顶层符号：
  - L18: `class _Session()`
  - L22: `class _Contexts()`
  - L30: `class _IdleSession()`
  - L34: `class _IdleContexts()`
  - L39: `class _App()`
  - L48: `class PausedQueueTest(unittest.TestCase)`
- 类成员：
  - L23: `_Contexts.__init__(self)`
  - L26: `_Contexts.resolve_sync(self, cid)`
  - L35: `_IdleContexts.resolve_sync(self, cid)`
  - L43: `_App.__init__(self, queue)`
  - L49: `PausedQueueTest.test_paused_turn_keeps_queue(self)`
  - L69: `PausedQueueTest.test_host_paused_flag_keeps_queue(self)`
  - L92: `PausedQueueTest.test_new_input_cancels_pending_confirm(self)`

### A.504 `tests/test_queued_input.py`

- 类型：Python
- 行数：102
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：安全插入点：队列消息转成输入事实。
- 导入：`__future__`, `sys`, `tempfile`, `unittest`, `pathlib`, `agent.core.modules.queued_input_mod`, `agent.mechanisms.conversation_queue`
- 顶层符号：
  - L18: `class _Queue()`
  - L38: `class _Ports()`
  - L45: `class QueuedInputModuleTest(unittest.TestCase)`
- 类成员：
  - L19: `_Queue.__init__(self)`
  - L23: `_Queue.claim_insert(self, cid)`
  - L31: `_Queue.complete(self, cid, item_id)`
  - L34: `_Queue.release(self, cid, item_id)`
  - L41: `_Ports.emit(self, type_)`
  - L46: `QueuedInputModuleTest.test_claims_one_insert_item_and_emits_input_fact(self)`
  - L56: `QueuedInputModuleTest.test_batch_contains_system_agent_and_user_inserts_only(self)`
  - L75: `QueuedInputModuleTest.test_batch_emits_each_input_as_a_separate_fact(self)`
  - L90: `QueuedInputModuleTest.test_no_insert_item_is_noop(self)`

### A.505 `tests/test_readonly_tools.py`

- 类型：Python
- 行数：379
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：只读工具测试：read_file / grep_files / glob_files + 注册制链路。
- 导入：`__future__`, `sys`, `tempfile`, `unittest`, `pathlib`, `agent.capabilities.builtin`, `agent.capabilities.builtin.locate_tools`, `agent.capabilities.registry`, `agent.core.tool_call`
- 顶层符号：
  - L19: `class ReadFileToolTest(unittest.TestCase)`
  - L87: `class GrepFilesToolTest(unittest.TestCase)`
  - L174: `class ScopeTest(unittest.TestCase)`
  - L245: `class GlobFilesToolTest(unittest.TestCase)`
  - L321: `class RegistryPipelineIntegrationTest(unittest.TestCase)`
- 类成员：
  - L22: `ReadFileToolTest.setUp(self)`
  - L28: `ReadFileToolTest.test_read_full_text(self)`
  - L36: `ReadFileToolTest.test_read_line_range(self)`
  - L44: `ReadFileToolTest.test_range_clamped_to_end(self)`
  - L52: `ReadFileToolTest.test_invalid_range_raises(self)`
  - L59: `ReadFileToolTest.test_max_chars_truncation(self)`
  - L67: `ReadFileToolTest.test_missing_file_raises(self)`
  - L72: `ReadFileToolTest.test_missing_path_raises(self)`
  - L77: `ReadFileToolTest.test_empty_file(self)`
  - L90: `GrepFilesToolTest.setUp(self)`
  - L101: `GrepFilesToolTest.test_literal_hits(self)`
  - L107: `GrepFilesToolTest.test_or_separator(self)`
  - L112: `GrepFilesToolTest.test_regex_and_ignore_case(self)`
  - L120: `GrepFilesToolTest.test_limit_truncation(self)`
  - L126: `GrepFilesToolTest.test_no_match(self)`
  - L132: `GrepFilesToolTest.test_missing_pattern_raises(self)`
  - L137: `GrepFilesToolTest.test_blank_pattern_says_what_to_fix(self)`
  - L148: `GrepFilesToolTest.test_binary_file_skipped(self)`
  - L155: `GrepFilesToolTest.test_path_not_dir_raises(self)`
  - L163: `GrepFilesToolTest.test_missing_path_is_not_reported_as_wrong_type(self)`
  - L177: `ScopeTest.setUp(self)`
  - L186: `ScopeTest._grep(self)`
  - L191: `ScopeTest._search(self)`
  - L196: `ScopeTest._grep_tops(self)`
  - L199: `ScopeTest._search_tops(self)`
  - L203: `ScopeTest.test_data_is_searched_by_default(self)`
  - L213: `ScopeTest.test_default_only_prunes_git_and_bytecode(self)`
  - L220: `ScopeTest.test_exclude_names_are_honoured(self)`
  - L227: `ScopeTest.test_include_derived_does_not_undo_exclude(self)`
  - L235: `ScopeTest.test_exclude_echoes_what_was_asked(self)`
  - L248: `GlobFilesToolTest.setUp(self)`
  - L259: `GlobFilesToolTest.test_recursive_default(self)`
  - L264: `GlobFilesToolTest.test_non_recursive(self)`
  - L271: `GlobFilesToolTest.test_entry_type_dir(self)`
  - L278: `GlobFilesToolTest.test_limit_truncation(self)`
  - L286: `GlobFilesToolTest.test_invalid_entry_type_raises(self)`
  - L291: `GlobFilesToolTest.test_derived_dirs_skipped_and_reported(self)`
  - L315: `GlobFilesToolTest.test_path_not_dir_raises(self)`
  - L324: `RegistryPipelineIntegrationTest.setUp(self)`
  - L329: `RegistryPipelineIntegrationTest.test_register_and_execute_via_pipeline(self)`
  - L348: `RegistryPipelineIntegrationTest.test_unknown_tool_via_pipeline(self)`
  - L361: `RegistryPipelineIntegrationTest.test_tool_error_structured(self)`

### A.506 `tests/test_renderer_path_contract.py`

- 类型：Python
- 行数：63
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：工具 renderer 路径绑定契约。
- 导入：`__future__`, `unittest`, `pathlib`
- 顶层符号：
  - L11: `class RendererPathContractTest(unittest.TestCase)`
- 类成员：
  - L12: `RendererPathContractTest.test_diff_path_is_exposed(self)`
  - L17: `RendererPathContractTest.test_action_registry_is_exposed(self)`
  - L33: `RendererPathContractTest.test_renderer_replacement_restores_previous(self)`
  - L40: `RendererPathContractTest.test_thinking_renderer_is_path_replaceable(self)`
  - L48: `RendererPathContractTest.test_ui_catalog_has_no_hardcoded_tree_paths(self)`
  - L53: `RendererPathContractTest.test_tool_view_prefers_path_override(self)`

### A.507 `tests/test_router_slot.py`

- 类型：Python
- 行数：45
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：模型路由 slot 的替换与回退。
- 导入：`__future__`, `unittest`, `types`, `agent.capabilities.slot_registry`, `agent.mechanisms.provider_router`
- 顶层符号：
  - L12: `class _Provider()`
  - L21: `class RouterSlotTest(unittest.TestCase)`
- 类成员：
  - L13: `_Provider.__init__(self, tag)`
  - L17: `_Provider.stream(self, request)`
  - L22: `RouterSlotTest.test_replace_router_selection(self)`

### A.508 `tests/test_rules_plugin.py`

- 类型：Python
- 行数：209
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：Rules 插件测试。
- 导入：`__future__`, `importlib.util`, `sys`, `tempfile`, `unittest`, `pathlib`, `agent.mechanisms.context`
- 顶层符号：
  - L24: `def _load_plugin_module()`
  - L38: `class _FakeCtx()`
  - L79: `def _make_tree(root)`
  - L93: `class RulesRuntimeTest(unittest.TestCase)`
  - L144: `class RulesRegisterTest(unittest.TestCase)`
- 类成员：
  - L41: `_FakeCtx.__init__(self)`
  - L49: `_FakeCtx.set_runtime(self, runtime)`
  - L52: `_FakeCtx.add_context_source(self, fn, meta)`
  - L57: `_FakeCtx._meta(self, meta)`
  - L64: `_FakeCtx.add_prompt_section(self, section, fn)`
  - L74: `_FakeCtx.add_ui_item(self, path, kind, props, order)`
  - L94: `RulesRuntimeTest.setUp(self)`
  - L100: `RulesRuntimeTest.test_missing_dir_stays_quiet(self)`
  - L107: `RulesRuntimeTest.test_only_markdown_recursive_and_skips_hidden(self)`
  - L114: `RulesRuntimeTest.test_one_message_per_file_with_prefix(self)`
  - L122: `RulesRuntimeTest.test_count_matches_messages(self)`
  - L126: `RulesRuntimeTest.test_oversized_file_is_skipped(self)`
  - L132: `RulesRuntimeTest.test_cache_reuses_content_until_file_changes(self)`
  - L139: `RulesRuntimeTest.test_missing_file_read_returns_empty(self)`
  - L145: `RulesRegisterTest.setUp(self)`
  - L151: `RulesRegisterTest._register(self, root)`
  - L157: `RulesRegisterTest.test_segment_key_label_and_count(self)`
  - L175: `RulesRegisterTest.test_resource_section_lines(self)`
  - L185: `RulesRegisterTest.test_resource_section_marks_missing_dir(self)`
  - L190: `RulesRegisterTest.test_segment_style_registered(self)`
  - L197: `RulesRegisterTest.test_dispose_removes_injection(self)`

### A.509 `tests/test_run_registry.py`

- 类型：Python
- 行数：204
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：`RunRegistry` 的回归测试：运行态登记必须"可跨进程查、崩溃自愈、抽干不留空窗"。
- 导入：`__future__`, `os`, `tempfile`, `threading`, `time`, `unittest`, `pathlib`, `agent.mechanisms.mesh`, `agent.mechanisms.run_registry`
- 顶层符号：
  - L29: `class InMemoryRunRegistryTest(unittest.TestCase)`
  - L55: `class FileRunRegistryTest(unittest.TestCase)`
  - L128: `class DrainWindowTest(unittest.TestCase)`
  - L165: `class PidAliveTest(unittest.TestCase)`
- 类成员：
  - L32: `InMemoryRunRegistryTest.test_claim_release_renew(self)`
  - L48: `InMemoryRunRegistryTest.test_running_cids_snapshot(self)`
  - L58: `FileRunRegistryTest.setUp(self)`
  - L63: `FileRunRegistryTest.test_two_instances_cannot_both_claim(self)`
  - L84: `FileRunRegistryTest.test_state_is_visible_across_instances(self)`
  - L96: `FileRunRegistryTest.test_stale_entry_self_heals(self)`
  - L106: `FileRunRegistryTest.test_touch_keeps_long_run_alive(self)`
  - L115: `FileRunRegistryTest.test_broken_file_is_treated_as_not_running(self)`
  - L123: `FileRunRegistryTest.test_build_switches_implementation_by_directory(self)`
  - L131: `DrainWindowTest.setUp(self)`
  - L136: `DrainWindowTest.test_renew_never_exposes_idle_window(self)`
  - L157: `DrainWindowTest.test_end_run_releases_when_idle(self)`
  - L178: `PidAliveTest.test_live_pid_is_alive(self)`
  - L182: `PidAliveTest.test_nonexistent_pid_is_dead(self)`
  - L186: `PidAliveTest.test_invalid_pid_forms_are_dead(self)`
  - L191: `PidAliveTest.test_claim_then_running_is_true_in_this_process(self)`

### A.510 `tests/test_scan_js_events.py`

- 类型：Python
- 行数：539
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：JS 事件绑定审计：分级判准与输出格式。
- 导入：`__future__`, `sys`, `unittest`, `pathlib`, `scripts.scan_js_events`
- 顶层符号：
  - L26: `class CollectTest(unittest.TestCase)`
  - L56: `class CommentTest(unittest.TestCase)`
  - L75: `class ScopeVerdictTest(unittest.TestCase)`
  - L93: `class LoopVerdictTest(unittest.TestCase)`
  - L118: `class LeakRiskTest(unittest.TestCase)`
  - L182: `class EphemeralTest(unittest.TestCase)`
  - L216: `class GuardTest(unittest.TestCase)`
  - L247: `class RenderOutputTest(unittest.TestCase)`
  - L266: `class LoopBodyTest(unittest.TestCase)`
  - L304: `class ArrowAnonymousTest(unittest.TestCase)`
  - L331: `class ArrowRenderFnTest(unittest.TestCase)`
  - L361: `class StringBracketTest(unittest.TestCase)`
  - L384: `class DelegateScopeTest(unittest.TestCase)`
  - L406: `class PairedRemoveTest(unittest.TestCase)`
  - L438: `class NestedRenderContextTest(unittest.TestCase)`
  - L466: `class ObjectMethodRenderTest(unittest.TestCase)`
  - L499: `class NamedGlobalListenerTest(unittest.TestCase)`
  - L526: `class ReadGuideTest(unittest.TestCase)`
- 类成员：
  - L27: `CollectTest.test_collects_add_listener_property_and_delegation(self)`
  - L41: `CollectTest.test_collects_inline_html_and_renders_report(self)`
  - L49: `CollectTest.test_property_assignment_matches_camel_case(self)`
  - L57: `CommentTest.test_bindings_inside_comments_are_ignored(self)`
  - L68: `CommentTest.test_double_slash_inside_string_is_not_a_comment(self)`
  - L76: `ScopeVerdictTest.test_global_container_element_are_distinguished(self)`
  - L94: `LoopVerdictTest.test_binding_inside_loop_is_per_item(self)`
  - L108: `LoopVerdictTest.test_binding_after_loop_is_not_per_item(self)`
  - L119: `LeakRiskTest.test_anonymous_global_listener_in_render_fn_is_leak_risk(self)`
  - L129: `LeakRiskTest.test_module_level_global_listener_is_not_leak_risk(self)`
  - L135: `LeakRiskTest.test_paired_remove_clears_leak_risk(self)`
  - L148: `LeakRiskTest.test_different_callback_is_not_paired(self)`
  - L159: `LeakRiskTest.test_capture_mismatch_is_not_paired(self)`
  - L170: `LeakRiskTest.test_anonymous_callback_is_not_paired(self)`
  - L183: `EphemeralTest.test_create_element_and_factory_count_as_new_node(self)`
  - L195: `EphemeralTest.test_lookup_wins_over_create(self)`
  - L199: `EphemeralTest.test_bare_assignment_is_recognised(self)`
  - L203: `EphemeralTest.test_new_node_binding_is_excluded_as_ephemeral(self)`
  - L217: `GuardTest.test_container_delegation_in_render_fn_is_not_render_path(self)`
  - L233: `GuardTest.test_existing_guard_marker_is_recognised(self)`
  - L248: `RenderOutputTest.test_report_states_intent_and_read_guide(self)`
  - L261: `RenderOutputTest.test_clean_input_reports_nothing_to_review(self)`
  - L269: `LoopBodyTest._in_loop(self, src)`
  - L272: `LoopBodyTest.test_for_loop_body_counts_as_loop(self)`
  - L278: `LoopBodyTest.test_while_loop_body_counts_as_loop(self)`
  - L282: `LoopBodyTest.test_for_of_body_counts_as_loop(self)`
  - L286: `LoopBodyTest.test_for_in_body_counts_as_loop(self)`
  - L290: `LoopBodyTest.test_binding_after_for_header_is_not_loop(self)`
  - L295: `LoopBodyTest.test_create_element_inside_for_is_per_item(self)`
  - L307: `ArrowAnonymousTest.test_arrow_callback_is_anonymous(self)`
  - L311: `ArrowAnonymousTest.test_paren_arrow_callback_is_anonymous(self)`
  - L315: `ArrowAnonymousTest.test_async_arrow_callback_is_anonymous(self)`
  - L319: `ArrowAnonymousTest.test_named_handler_reference_is_not_anonymous(self)`
  - L324: `ArrowAnonymousTest.test_arrow_global_listener_in_render_fn_is_leak_risk(self)`
  - L334: `ArrowRenderFnTest.test_arrow_assigned_render_fn_is_named(self)`
  - L344: `ArrowRenderFnTest.test_arrow_assigned_non_render_fn_is_not_render(self)`
  - L354: `ArrowRenderFnTest.test_expression_body_arrow_has_no_span(self)`
  - L364: `StringBracketTest.test_string_with_paren_does_not_truncate_callback(self)`
  - L371: `StringBracketTest.test_template_literal_with_braces_is_skipped(self)`
  - L378: `StringBracketTest.test_string_with_paren_keeps_handler_detection(self)`
  - L387: `DelegateScopeTest.test_unrelated_contains_is_not_delegation(self)`
  - L393: `DelegateScopeTest.test_event_target_closest_is_delegation(self)`
  - L399: `DelegateScopeTest.test_current_target_contains_is_delegation(self)`
  - L409: `PairedRemoveTest.test_other_element_remove_keeps_leak_risk(self)`
  - L420: `PairedRemoveTest.test_same_target_remove_clears_leak_risk(self)`
  - L429: `PairedRemoveTest.test_different_event_remove_keeps_leak_risk(self)`
  - L441: `NestedRenderContextTest.test_binding_in_nested_fn_inside_render_is_render_path(self)`
  - L453: `NestedRenderContextTest.test_binding_in_nested_fn_outside_render_is_not_render_path(self)`
  - L469: `ObjectMethodRenderTest.test_shorthand_object_method_is_named(self)`
  - L480: `ObjectMethodRenderTest.test_function_valued_object_method_is_named(self)`
  - L491: `ObjectMethodRenderTest.test_control_flow_header_is_not_a_method(self)`
  - L502: `NamedGlobalListenerTest.test_named_global_listener_in_render_fn_is_leak_risk(self)`
  - L510: `NamedGlobalListenerTest.test_named_global_listener_with_remove_is_global_once(self)`
  - L518: `NamedGlobalListenerTest.test_named_global_listener_at_module_level_is_global_once(self)`
  - L529: `ReadGuideTest.test_read_guide_counts_match_constants(self)`

### A.511 `tests/test_session_context.py`

- 类型：Python
- 行数：278
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：会话上下文（SessionContext / SessionContexts）测试。
- 导入：`__future__`, `sys`, `tempfile`, `threading`, `unittest`, `pathlib`, `agent.app`, `agent.core.session_context`, `agent.core.session_scope`, `agent.core.tool_call`, `agent.mechanisms.live_state`, `agent.mechanisms.quality`, `tests.gate_fixtures`
- 顶层符号：
  - L31: `def _contexts()`
  - L35: `class IsolationKeyTest(unittest.TestCase)`
  - L58: `class LazyLifecycleTest(unittest.TestCase)`
  - L90: `class ThreadSafetyTest(unittest.TestCase)`
  - L112: `class ExclusiveGateTest(unittest.TestCase)`
  - L156: `class SharedContainerTest(unittest.TestCase)`
  - L181: `class ResolutionPathTest(unittest.TestCase)`
  - L190: `class LevelSeparationTest(unittest.TestCase)`
  - L203: `class AppWiringTest(unittest.TestCase)`
- 类成员：
  - L38: `IsolationKeyTest.test_bucket_key_rules(self)`
  - L44: `IsolationKeyTest.test_empty_and_blank_share_default_bucket(self)`
  - L52: `IsolationKeyTest.test_whitespace_normalised_but_case_preserved(self)`
  - L61: `LazyLifecycleTest.test_no_context_until_resolved(self)`
  - L68: `LazyLifecycleTest.test_get_is_readonly_no_side_effect(self)`
  - L76: `LazyLifecycleTest.test_gate_factory_called_once_per_conversation(self)`
  - L93: `ThreadSafetyTest.test_concurrent_first_use_yields_single_context(self)`
  - L115: `ExclusiveGateTest.test_gates_are_distinct_instances(self)`
  - L123: `ExclusiveGateTest.test_preview_snapshot_not_visible_across_sessions(self)`
  - L135: `ExclusiveGateTest.test_review_and_reread_state_not_shared(self)`
  - L146: `ExclusiveGateTest.test_intent_and_red_light_not_shared(self)`
  - L159: `SharedContainerTest.test_live_shared_by_reference(self)`
  - L168: `SharedContainerTest.test_shared_live_is_still_partitioned_by_cid(self)`
  - L176: `SharedContainerTest.test_gate_factory_required(self)`
  - L184: `ResolutionPathTest.test_resolve_uses_current_session_scope(self)`
  - L193: `LevelSeparationTest.test_session_context_holds_only_session_level_state(self)`
  - L206: `AppWiringTest.setUp(self)`
  - L213: `AppWiringTest._call(self, name, arguments, cid)`
  - L225: `AppWiringTest.test_default_bucket_gate_is_canonical(self)`
  - L230: `AppWiringTest.test_gate_for_is_per_conversation(self)`
  - L235: `AppWiringTest.test_app_exposes_session_contexts(self)`
  - L240: `AppWiringTest.test_preview_and_confirm_land_in_same_session_gate(self)`
  - L255: `AppWiringTest.test_commit_rejected_when_confirm_lands_in_other_session(self)`
  - L269: `AppWiringTest.test_engine_session_runs_on_its_own_gate(self)`

### A.512 `tests/test_session_seq.py`

- 类型：Python
- 行数：286
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：会话日志存储坐标（`seq`）测试。
- 导入：`__future__`, `json`, `sys`, `tempfile`, `unittest`, `pathlib`, `agent.core.events`, `agent.mechanisms.session_store`
- 顶层符号：
  - L29: `class SeqAssignmentTest(unittest.TestCase)`
  - L107: `class SeqMissingTest(unittest.TestCase)`
  - L159: `class SeqTailTest(unittest.TestCase)`
  - L189: `class SeqEmptyAndErrorTest(unittest.TestCase)`
- 类成员：
  - L32: `SeqAssignmentTest.setUp(self)`
  - L37: `SeqAssignmentTest.test_seq_is_written_to_each_line(self)`
  - L43: `SeqAssignmentTest.test_seq_continues_across_appends(self)`
  - L50: `SeqAssignmentTest.test_line_count_matches_next_seq(self)`
  - L58: `SeqAssignmentTest.test_blank_lines_do_not_shift_positions(self)`
  - L68: `SeqAssignmentTest.test_load_still_returns_plain_events(self)`
  - L75: `SeqAssignmentTest.test_seq_lives_in_payload_and_top_level_only(self)`
  - L93: `SeqAssignmentTest.test_conversation_id_is_not_persisted(self)`
  - L110: `SeqMissingTest.setUp(self)`
  - L115: `SeqMissingTest._write_without_seq(self)`
  - L129: `SeqMissingTest.test_missing_seq_falls_back_to_line_position(self)`
  - L137: `SeqMissingTest.test_appended_rows_use_global_seq(self)`
  - L151: `SeqMissingTest.test_coordinates_stay_unique_and_monotonic(self)`
  - L162: `SeqTailTest.setUp(self)`
  - L168: `SeqTailTest.test_tail_from_is_exclusive(self)`
  - L173: `SeqTailTest.test_tail_from_negative_returns_everything(self)`
  - L177: `SeqTailTest.test_tail_from_beyond_end_is_empty(self)`
  - L180: `SeqTailTest.test_missing_conversation_is_empty_not_error(self)`
  - L184: `SeqTailTest.test_bad_conversation_id_raises_like_load(self)`
  - L190: `SeqEmptyAndErrorTest.setUp(self)`
  - L195: `SeqEmptyAndErrorTest.test_append_empty_batch_writes_nothing(self)`
  - L200: `SeqEmptyAndErrorTest.test_unparseable_line_is_skipped(self)`
  - L215: `SeqEmptyAndErrorTest.test_non_object_json_lines_do_not_produce_events(self)`
  - L226: `SeqEmptyAndErrorTest.test_append_after_external_edit_does_not_collide(self)`
  - L245: `SeqEmptyAndErrorTest.test_coordinates_are_global_across_conversations(self)`
  - L254: `SeqEmptyAndErrorTest.test_tail_across_uses_one_cursor_for_all_conversations(self)`
  - L264: `SeqEmptyAndErrorTest.test_allocate_seq_survives_restart_without_collision(self)`
  - L274: `SeqEmptyAndErrorTest.test_encrypted_mode_round_trips_seq(self)`

### A.513 `tests/test_session_store.py`

- 类型：Python
- 行数：325
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：SessionStore 加密持久化测试。
- 导入：`__future__`, `json`, `sys`, `tempfile`, `threading`, `unittest`, `pathlib`, `agent.core.events`, `agent.mechanisms.session_store`
- 顶层符号：
  - L24: `class ConversationIdTest(unittest.TestCase)`
  - L40: `class _StoreTest(unittest.TestCase)`
  - L49: `class LayoutTest(_StoreTest)`
  - L62: `class WriteReadTest(_StoreTest)`
  - L121: `class CryptoTest(_StoreTest)`
  - L206: `class CrossProcessAppendTest(_StoreTest)`
- 类成员：
  - L27: `ConversationIdTest.test_valid_and_invalid(self)`
  - L34: `ConversationIdTest.test_new_id_is_valid(self)`
  - L43: `_StoreTest.setUp(self)`
  - L52: `LayoutTest.test_layout_single_file_per_session(self)`
  - L65: `WriteReadTest.test_roundtrip_plaintext(self)`
  - L80: `WriteReadTest.test_append_empty_noop(self)`
  - L86: `WriteReadTest.test_corrupt_line_skipped(self)`
  - L98: `WriteReadTest.test_missing_file_returns_empty(self)`
  - L103: `WriteReadTest.test_invalid_utf8_bytes_tolerated(self)`
  - L114: `WriteReadTest.test_invalid_cid_rejected(self)`
  - L124: `CryptoTest.test_roundtrip_local_encrypted(self)`
  - L135: `CryptoTest.test_mixed_plain_and_encrypted(self)`
  - L144: `CryptoTest.test_tamper_detected(self)`
  - L155: `CryptoTest.test_unknown_mode_falls_back_none(self)`
  - L163: `CryptoTest.test_key_reuse_across_instances(self)`
  - L173: `CryptoTest.test_concurrent_key_init(self)`
  - L222: `CrossProcessAppendTest._run_workers(self, script, n)`
  - L256: `CrossProcessAppendTest.test_concurrent_appends_lose_nothing(self)`
  - L289: `CrossProcessAppendTest.test_concurrent_appends_all_visible_after_load(self)`

### A.514 `tests/test_session_tools.py`

- 类型：Python
- 行数：347
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：会话协作工具测试。
- 导入：`__future__`, `sys`, `tempfile`, `threading`, `time`, `unittest`, `pathlib`, `types`, `agent.app`, `agent.core.model_call`, `agent.core.tool_call`, `agent.mechanisms.mesh`, `tests.testkit`
- 顶层符号：
  - L30: `class _ProbeProvider()`
  - L49: `class _MeshBase(unittest.TestCase)`
  - L71: `class MeshCoreTest(_MeshBase)`
  - L142: `class CreateListTest(_MeshBase)`
  - L192: `class SendTest(_MeshBase)`
  - L252: `class MultisendBroadcastTest(_MeshBase)`
  - L297: `class RunnerE2ETest(unittest.TestCase)`
- 类成员：
  - L33: `_ProbeProvider.__init__(self, gate_first)`
  - L40: `_ProbeProvider.stream(self, request)`
  - L52: `_MeshBase.setUp(self)`
  - L62: `_MeshBase._call(self, name, arguments, cid)`
  - L68: `_MeshBase._register(self, cid, name, role, tags)`
  - L72: `MeshCoreTest.test_upsert_get_list_roundtrip(self)`
  - L82: `MeshCoreTest.test_queue_fifo_and_size(self)`
  - L96: `MeshCoreTest.test_submit_paths(self)`
  - L114: `MeshCoreTest.test_renew_run_keeps_claim(self)`
  - L123: `MeshCoreTest.test_agents_persistence_roundtrip(self)`
  - L133: `MeshCoreTest.test_session_exists_registry_and_callback(self)`
  - L143: `CreateListTest.test_create_single_and_meta(self)`
  - L155: `CreateListTest.test_create_alias_name_persona_tags(self)`
  - L166: `CreateListTest.test_create_batch_count_and_prefix(self)`
  - L176: `CreateListTest.test_list_status_and_sort(self)`
  - L193: `SendTest.test_send_queued_envelope_and_wrap(self)`
  - L214: `SendTest.test_send_sender_identity_from_registry(self)`
  - L226: `SendTest.test_send_custom_thread_and_channel(self)`
  - L235: `SendTest.test_send_validations(self)`
  - L253: `MultisendBroadcastTest.test_multisend_partial_and_all_failed(self)`
  - L276: `MultisendBroadcastTest.test_broadcast_filters_and_envelope(self)`
  - L300: `RunnerE2ETest.setUp(self)`
  - L313: `RunnerE2ETest._call(self, name, arguments, cid)`
  - L319: `RunnerE2ETest.test_trigger_and_drain(self)`

### A.515 `tests/test_settings_panel.py`

- 类型：Python
- 行数：424
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：设置页：写回原文件时留下注释，保存后当前进程对象换成新值。
- 导入：`__future__`, `json`, `tempfile`, `unittest`, `pathlib`, `agent.shell.settings_io`, `agent.shell.settings_panel`
- 顶层符号：
  - L22: `class _Provider()`
  - L29: `class _State()`
  - L35: `class _App()`
  - L47: `class _Host()`
  - L67: `class IniEditTest(unittest.TestCase)`
  - L112: `class ApplyHostTest(unittest.TestCase)`
  - L136: `class PluginSettingsTest(unittest.TestCase)`
  - L279: `class StructuredPluginConfigTest(unittest.TestCase)`
  - L416: `class SettingsPageAssetsTest(unittest.TestCase)`
- 类成员：
  - L23: `_Provider.__init__(self)`
  - L30: `_State.__init__(self)`
  - L36: `_App.__init__(self)`
  - L48: `_Host.__init__(self)`
  - L52: `_Host.loaded_names(self)`
  - L55: `_Host.unload(self, name)`
  - L59: `_Host.load_manifest(self, entries)`
  - L68: `IniEditTest.test_update_keeps_comments_and_other_sections(self)`
  - L91: `IniEditTest.test_remove_section_leaves_commented_header(self)`
  - L104: `IniEditTest.test_append_does_not_duplicate_a_section(self)`
  - L113: `ApplyHostTest.test_apply_updates_limits(self)`
  - L137: `PluginSettingsTest.test_enable_and_disable_edit_the_manifest(self)`
  - L194: `PluginSettingsTest.test_missing_plugin_is_not_enabled(self)`
  - L204: `PluginSettingsTest.test_plugin_config_roundtrip_rejects_a_bad_name(self)`
  - L218: `PluginSettingsTest.test_missing_plugin_config_returns_empty_editor(self)`
  - L233: `PluginSettingsTest.test_fields_schema_creates_real_config_from_form(self)`
  - L268: `PluginSettingsTest.test_kernel_model_tab_is_absent(self)`
  - L273: `PluginSettingsTest.test_unknown_route(self)`
  - L300: `StructuredPluginConfigTest._setup(self, tmp, config_text)`
  - L310: `StructuredPluginConfigTest.test_textarea_field_roundtrips_multiline(self)`
  - L339: `StructuredPluginConfigTest.test_read_masks_the_secret(self)`
  - L357: `StructuredPluginConfigTest.test_required_field_rejects_an_empty_value(self)`
  - L373: `StructuredPluginConfigTest.test_save_keeps_other_sections_and_an_untouched_secret(self)`
  - L392: `StructuredPluginConfigTest.test_new_model_group_gets_a_generated_id(self)`
  - L407: `StructuredPluginConfigTest.test_save_rejects_an_unknown_key(self)`
  - L417: `SettingsPageAssetsTest.test_gear_and_settings_script_are_inlined(self)`

### A.516 `tests/test_settings_registry.py`

- 类型：Python
- 行数：87
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：插件系统设置注册表契约。
- 导入：`__future__`, `unittest`, `agent.capabilities.settings_registry`
- 顶层符号：
  - L10: `class SettingsRegistryTest(unittest.TestCase)`
- 类成员：
  - L11: `SettingsRegistryTest.test_panel_item_and_save_callback(self)`
  - L27: `SettingsRegistryTest.test_invalid_select_and_missing_parent(self)`
  - L39: `SettingsRegistryTest.test_failed_save_rolls_back_committed_items(self)`
  - L60: `SettingsRegistryTest.test_replace_item_and_restore(self)`
  - L75: `SettingsRegistryTest.test_drop_plugin_removes_items_and_panels(self)`

### A.517 `tests/test_silent_except_gate.py`

- 类型：Python
- 行数：95
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：静默异常门禁：结构判据的正负例。
- 导入：`__future__`, `ast`, `sys`, `tempfile`, `unittest`, `pathlib`, `unittest`, `check_silent_except`
- 顶层符号：
  - L18: `def _handler(source)`
  - L23: `class SilentExceptStructureTest(unittest.TestCase)`
  - L69: `class SilentExceptGateRunTest(unittest.TestCase)`
- 类成员：
  - L24: `SilentExceptStructureTest.test_broad_pass_is_rejected(self)`
  - L29: `SilentExceptStructureTest.test_pass_in_multi_statement_is_rejected(self)`
  - L35: `SilentExceptStructureTest.test_narrow_return_is_allowed(self)`
  - L40: `SilentExceptStructureTest.test_explicit_result_is_recognized(self)`
  - L46: `SilentExceptStructureTest.test_report_error_is_recognized(self)`
  - L52: `SilentExceptStructureTest.test_arbitrary_call_is_not_a_transform(self)`
  - L58: `SilentExceptStructureTest.test_report_error_needs_payload(self)`
  - L64: `SilentExceptStructureTest.test_suppress_exception_is_rejected(self)`
  - L70: `SilentExceptGateRunTest.test_main_fails_on_broad_pass(self)`
  - L81: `SilentExceptGateRunTest.test_main_passes_on_narrow_fallback(self)`

### A.518 `tests/test_slot_registry.py`

- 类型：Python
- 行数：122
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：插口树的绑定、解析、回退和事务测试。
- 导入：`__future__`, `unittest`, `agent.capabilities.slot_registry`
- 顶层符号：
  - L13: `class SlotRegistryTest(unittest.TestCase)`
- 类成员：
  - L14: `SlotRegistryTest.setUp(self)`
  - L25: `SlotRegistryTest.test_slot_duplicate_rejected(self)`
  - L29: `SlotRegistryTest.test_replace_and_unbind_restores_default(self)`
  - L38: `SlotRegistryTest.test_priority_and_active_binding(self)`
  - L49: `SlotRegistryTest.test_same_priority_conflict_rejected(self)`
  - L54: `SlotRegistryTest.test_contract_version_mismatch_rejected(self)`
  - L60: `SlotRegistryTest.test_wrap_receives_base(self)`
  - L71: `SlotRegistryTest.test_extend_collection(self)`
  - L78: `SlotRegistryTest.test_replace_subtree_applies_to_children(self)`
  - L89: `SlotRegistryTest.test_drop_owner_removes_bindings(self)`
  - L95: `SlotRegistryTest.test_transaction_rolls_back_new_slot(self)`
  - L104: `SlotRegistryTest.test_execution_snapshot_freezes_bindings(self)`
  - L112: `SlotRegistryTest.test_describe_does_not_expose_implementation_objects(self)`

### A.519 `tests/test_slot_tree.py`

- 类型：Python
- 行数：153
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：自装配树：清单、子节点、失败与回滚。
- 导入：`__future__`, `json`, `tempfile`, `unittest`, `pathlib`, `agent.core.slot`, `agent.core.slot_tree`
- 顶层符号：
  - L14: `def make_leaf(ctx)`
  - L18: `def make_fail(ctx)`
  - L22: `class SlotTreeTest(unittest.TestCase)`
  - L120: `class _Container(SlotContainer)`
  - L125: `def make_container(ctx)`
  - L129: `class _Value(SlotLeaf)`
  - L138: `def make_value(ctx)`
  - L142: `class _Consumer(_Value)`
  - L147: `def make_consumer(ctx)`
- 类成员：
  - L23: `SlotTreeTest._tree(self, nodes)`
  - L31: `SlotTreeTest.test_container_assembles_direct_children(self)`
  - L40: `SlotTreeTest.test_repeated_assembly_is_idempotent(self)`
  - L57: `SlotTreeTest.test_dynamic_replacement_restores_previous(self)`
  - L75: `SlotTreeTest.test_static_session_node_can_be_replaced_and_restored(self)`
  - L88: `SlotTreeTest.test_disabled_child_is_not_materialized(self)`
  - L98: `SlotTreeTest.test_factory_failure_blocks_master(self)`
  - L108: `SlotTreeTest.test_requires_injects_value(self)`
  - L121: `_Container.__init__(self, path)`
  - L130: `_Value.__init__(self, path, value)`
  - L134: `_Value.port_value(self)`
  - L143: `_Consumer.__init__(self, path, ports)`

### A.520 `tests/test_source_snapshot.py`

- 类型：Python
- 行数：184
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：收集只做一次：一趟装配里压缩与模型请求必须共用同一份注入源快照。
- 导入：`__future__`, `sys`, `unittest`, `pathlib`, `agent.core.chain`, `agent.core.module`, `agent.core.outcome`, `agent.core.ports`, `agent.core.session_log`, `agent.mechanisms.context`
- 顶层符号：
  - L28: `class CollectOncePerPassTest(unittest.TestCase)`
  - L91: `class _Touch(ModuleBase)`
  - L106: `class _Halt(ModuleBase)`
  - L121: `class ChainPassDropsSnapshotTest(unittest.TestCase)`
  - L155: `class SegmentsStayAlignedTest(unittest.TestCase)`
- 类成员：
  - L31: `CollectOncePerPassTest.setUp(self)`
  - L42: `CollectOncePerPassTest.test_repeated_assembly_shares_one_snapshot(self)`
  - L47: `CollectOncePerPassTest.test_bump_forces_recollection(self)`
  - L54: `CollectOncePerPassTest.test_registering_a_source_bumps_by_itself(self)`
  - L61: `CollectOncePerPassTest.test_explicit_refresh_always_recollects(self)`
  - L67: `CollectOncePerPassTest.test_pass_builds_at_start_and_drops_at_end(self)`
  - L82: `CollectOncePerPassTest.test_disposing_a_source_bumps_version(self)`
  - L96: `_Touch.__init__(self, pipe)`
  - L99: `_Touch.execute(self, ports)`
  - L111: `_Halt.__init__(self, pipe)`
  - L114: `_Halt.execute(self, ports)`
  - L124: `ChainPassDropsSnapshotTest._pipe(self)`
  - L136: `ChainPassDropsSnapshotTest.test_one_pass_collects_once_and_drops_when_the_pass_ends(self)`
  - L147: `ChainPassDropsSnapshotTest.test_halted_pass_still_drops_the_snapshot(self)`
  - L158: `SegmentsStayAlignedTest.test_alignment_after_repeated_assembly(self)`
  - L170: `SegmentsStayAlignedTest.test_repeated_assembly_does_not_grow_rows(self)`

### A.521 `tests/test_standards_manifest.py`

- 类型：Python
- 行数：42
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：准则清单门禁：手册编号/版本与 standards_rules 常量双向一致。
- 导入：`__future__`, `sys`, `tempfile`, `unittest`, `pathlib`, `check_standards_manifest`
- 顶层符号：
  - L17: `class StandardsManifestGateTest(unittest.TestCase)`
- 类成员：
  - L18: `StandardsManifestGateTest.test_current_manifest_matches_constants(self)`
  - L22: `StandardsManifestGateTest.test_missing_extra_and_version_are_reported(self)`
  - L33: `StandardsManifestGateTest.test_skills_disabled_is_skipped(self)`

### A.522 `tests/test_subagent.py`

- 类型：Python
- 行数：377
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：子智能体：批次、fork、生命周期、存储隔离与工具入口。
- 导入：`__future__`, `tempfile`, `unittest`, `pathlib`, `unittest`, `agent.app`, `agent.capabilities.registry`, `agent.core.context`, `agent.core.events`, `agent.core.model_call`, `agent.mechanisms.live_state`, `agent.mechanisms.session_store`, `agent.subagent.batches`, `agent.subagent.manager`, `agent.subagent.repository`, `agent.subagent.seed`, `tests.testkit`
- 顶层符号：
  - L24: `class _Provider()`
  - L32: `class _BlockingProvider()`
  - L46: `class _ManagerCase(unittest.TestCase)`
  - L69: `class SessionStorePathTest(unittest.TestCase)`
  - L91: `class BatchStoreTest(unittest.TestCase)`
  - L117: `class RegistryVisibilityTest(unittest.TestCase)`
  - L138: `class RepositoryBoundaryTest(unittest.TestCase)`
  - L196: `class SeedTest(unittest.TestCase)`
  - L256: `class ManagerTest(_ManagerCase)`
- 类成员：
  - L28: `_Provider.stream(self, request)`
  - L36: `_BlockingProvider.__init__(self)`
  - L40: `_BlockingProvider.stream(self, request)`
  - L47: `_ManagerCase.setUp(self)`
  - L64: `_ManagerCase._wait(self, child_id)`
  - L70: `SessionStorePathTest.test_child_store_shares_sequence_and_separate_path(self)`
  - L92: `BatchStoreTest.test_batch_file_is_capped_and_isolated_by_parent(self)`
  - L118: `RegistryVisibilityTest.test_plugin_can_hide_tool_from_subagent(self)`
  - L139: `RepositoryBoundaryTest.test_failed_seed_removes_new_empty_batch(self)`
  - L153: `RepositoryBoundaryTest.test_explicit_batch_history_and_invalid_boundaries(self)`
  - L180: `RepositoryBoundaryTest.test_batch_files_reject_invalid_ids_and_corrupt_entries(self)`
  - L197: `SeedTest.test_fork_keeps_only_completed_turn(self)`
  - L234: `SeedTest.test_fresh_seed_has_only_created_marker(self)`
  - L257: `ManagerTest.test_create_starts_turn_and_uses_child_store(self)`
  - L273: `ManagerTest.test_label_required_and_batch_scope(self)`
  - L279: `ManagerTest.test_restart_restores_idle_children(self)`
  - L292: `ManagerTest.test_parent_send_and_permissions(self)`
  - L305: `ManagerTest.test_child_turn_end_notifies_parent(self)`
  - L315: `ManagerTest.test_child_can_send_to_parent_with_source(self)`
  - L326: `ManagerTest.test_insert_send_marks_queue_item(self)`
  - L349: `ManagerTest.test_system_prompt_uses_role_tool_view(self)`
  - L363: `ManagerTest.test_tool_schema_and_list(self)`

### A.523 `tests/test_task_tools.py`

- 类型：Python
- 行数：380
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：任务与自主工具测试。
- 导入：`__future__`, `sys`, `tempfile`, `unittest`, `pathlib`, `agent.app`, `agent.core`, `agent.core.tool_call`, `agent.mechanisms.live_state`
- 顶层符号：
  - L24: `class _TaskToolsBase(unittest.TestCase)`
  - L49: `class RunTypeTest(_TaskToolsBase)`
  - L85: `class TodoListTest(_TaskToolsBase)`
  - L167: `class UserConfirmTest(_TaskToolsBase)`
  - L215: `class ApprovalConfirmTest(_TaskToolsBase)`
  - L272: `class TaskGoalTest(_TaskToolsBase)`
  - L327: `class ModeGateTest(_TaskToolsBase)`
  - L368: `class SessionScopeTest(_TaskToolsBase)`
- 类成员：
  - L27: `_TaskToolsBase.setUp(self)`
  - L36: `_TaskToolsBase._call(self, name, arguments, cid)`
  - L50: `RunTypeTest.test_query_default_auto(self)`
  - L56: `RunTypeTest.test_switch_and_query(self)`
  - L65: `RunTypeTest.test_auto_clears_override(self)`
  - L73: `RunTypeTest.test_invalid_value_is_rejected(self)`
  - L79: `RunTypeTest.test_requires_session_scope(self)`
  - L86: `TodoListTest._create(self, items)`
  - L89: `TodoListTest.test_create_and_shape(self)`
  - L97: `TodoListTest.test_create_replaces_and_validates(self)`
  - L106: `TodoListTest.test_check_uncheck_and_bounds(self)`
  - L119: `TodoListTest.test_add_remove_replace(self)`
  - L133: `TodoListTest.test_no_list_unknown_and_query_close(self)`
  - L147: `TodoListTest.test_persistence_reload(self)`
  - L156: `TodoListTest.test_persistence_tolerance_and_cid_defense(self)`
  - L168: `UserConfirmTest.test_pending_envelope(self)`
  - L177: `UserConfirmTest.test_confirm_backfill_is_not_a_tool_parameter(self)`
  - L185: `UserConfirmTest.test_validations(self)`
  - L197: `UserConfirmTest.test_interactive_flag_is_rejected(self)`
  - L207: `UserConfirmTest.test_envelope_still_works_without_tty(self)`
  - L216: `ApprovalConfirmTest.setUp(self)`
  - L220: `ApprovalConfirmTest.test_suspends_with_approval_envelope(self)`
  - L234: `ApprovalConfirmTest.test_rejects_blank_or_forged_id(self)`
  - L247: `ApprovalConfirmTest.test_suspend_is_remembered_on_the_session(self)`
  - L273: `TaskGoalTest.test_goal_shapes(self)`
  - L303: `TaskGoalTest.test_goal_round_limit_default_and_cap(self)`
  - L311: `TaskGoalTest.test_resume_creates_missing_goal_from_text(self)`
  - L318: `TaskGoalTest.test_resume_replaces_existing_goal_text(self)`
  - L328: `ModeGateTest._preview_ready(self, name)`
  - L336: `ModeGateTest.test_plan_blocks_commit(self)`
  - L347: `ModeGateTest.test_execute_requires_todo(self)`
  - L358: `ModeGateTest.test_plan_blocks_commands(self)`
  - L369: `SessionScopeTest.test_scope_set_and_restored(self)`

### A.524 `tests/test_theme_style_plugin.py`

- 类型：Python
- 行数：68
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：主题风格插件：注册点与风格资源清单。
- 导入：`__future__`, `json`, `unittest`, `pathlib`, `types`, `agent.capabilities.settings_registry`, `agent.shell.settings_panel`, `plugins.theme_style.plugin`
- 顶层符号：
  - L17: `class ThemeStylePluginTest(unittest.TestCase)`
- 类成员：
  - L18: `ThemeStylePluginTest.test_register_adds_settings_item_route_and_boot_script(self)`
  - L32: `ThemeStylePluginTest.test_style_assets_and_theme_lists(self)`
  - L44: `ThemeStylePluginTest.test_host_catalog_includes_plugin_item(self)`
  - L60: `ThemeStylePluginTest.test_boot_script_separate_from_core(self)`

### A.525 `tests/test_thread_context.py`

- 类型：Python
- 行数：27
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：线程启动时继承当前执行快照。
- 导入：`__future__`, `unittest`, `agent.capabilities.slot_registry`, `agent.core.thread_context`
- 顶层符号：
  - L11: `class ThreadContextTest(unittest.TestCase)`
- 类成员：
  - L12: `ThreadContextTest.test_thread_inherits_execution_snapshot(self)`

### A.526 `tests/test_todo_context_prompt.py`

- 类型：Python
- 行数：328
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：执行清单、上下文分段与系统提示词。
- 导入：`__future__`, `sys`, `unittest`, `pathlib`, `agent.capabilities.registry`, `agent.mechanisms.context`, `agent.shell.prompts`
- 顶层符号：
  - L28: `class _PreviewTool(ToolPlugin)`
  - L38: `def _reg_with_preview()`
  - L45: `class TodoProgressTest(unittest.TestCase)`
  - L114: `class RuntimeTailTodoProgressTest(unittest.TestCase)`
  - L165: `class ContextLayoutTest(unittest.TestCase)`
  - L230: `class SystemPromptTest(unittest.TestCase)`
- 类成员：
  - L34: `_PreviewTool.execute(self, arguments)`
  - L48: `TodoProgressTest._tool(self)`
  - L54: `TodoProgressTest.test_create_reports_progress(self)`
  - L67: `TodoProgressTest.test_check_then_all_done(self)`
  - L84: `TodoProgressTest.test_uncheck_revokes_all_done(self)`
  - L99: `TodoProgressTest.test_close_has_no_items(self)`
  - L117: `RuntimeTailTodoProgressTest.test_mode_note_contains_latest_progress(self)`
  - L143: `RuntimeTailTodoProgressTest.test_no_todo_omits_todo_note(self)`
  - L168: `ContextLayoutTest._pipeline(self)`
  - L178: `ContextLayoutTest.test_chunks_plus_remainder(self)`
  - L188: `ContextLayoutTest.test_pct_sums_to_100(self)`
  - L194: `ContextLayoutTest.test_budget_is_used_for_pct(self)`
  - L205: `ContextLayoutTest.test_budget_never_below_used(self)`
  - L212: `ContextLayoutTest.test_counts_present(self)`
  - L222: `ContextLayoutTest.test_labels_are_chinese_names(self)`
  - L233: `SystemPromptTest.test_non_empty_by_default(self)`
  - L240: `SystemPromptTest.test_mode_section_differs(self)`
  - L250: `SystemPromptTest.test_unknown_mode_falls_back_to_auto(self)`
  - L257: `SystemPromptTest.test_coding_and_tooling_disciplines_present(self)`
  - L272: `SystemPromptTest.test_preview_write_tools_line_tracks_registry(self)`
  - L284: `SystemPromptTest.test_explicit_prompt_wins(self)`
  - L288: `SystemPromptTest.test_blank_explicit_falls_back(self)`
  - L299: `SystemPromptTest.test_tool_summary_shape(self)`
  - L316: `SystemPromptTest.test_tool_summary_propagates_registry_errors(self)`

### A.527 `tests/test_tool_arguments.py`

- 类型：Python
- 行数：103
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：工具参数契约：未声明的参数必须在进入工具前拒绝。
- 导入：`__future__`, `tempfile`, `unittest`, `pathlib`, `agent.capabilities.builtin.read_file`, `agent.capabilities.registry`, `agent.core.tool_call`
- 顶层符号：
  - L14: `class ToolArgumentContractTest(unittest.TestCase)`
- 类成员：
  - L15: `ToolArgumentContractTest.setUp(self)`
  - L24: `ToolArgumentContractTest.test_unknown_aliases_are_rejected_before_execution(self)`
  - L40: `ToolArgumentContractTest.test_session_create_has_one_name_parameter(self)`
  - L46: `ToolArgumentContractTest.test_empty_schema_rejects_every_argument(self)`
  - L65: `ToolArgumentContractTest.test_business_failure_does_not_double_wrap_ok(self)`
  - L87: `ToolArgumentContractTest.test_declared_arguments_still_work(self)`

### A.528 `tests/test_tool_pipeline_slot.py`

- 类型：Python
- 行数：39
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：工具管道 slot 的替换与回退。
- 导入：`__future__`, `unittest`, `types`, `agent.capabilities.slot_registry`, `agent.core.tool_call`
- 顶层符号：
  - L12: `class _Registry()`
  - L17: `class ToolPipelineSlotTest(unittest.TestCase)`
- 类成员：
  - L13: `_Registry.get(self, name)`
  - L18: `ToolPipelineSlotTest.test_replace_pipeline(self)`

### A.529 `tests/test_tool_registry.py`

- 类型：Python
- 行数：202
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：工具注册表测试：插件协议 / 注册 / 解析 / 注销 / 声明导出。
- 导入：`__future__`, `sys`, `unittest`, `pathlib`, `agent.capabilities.builtin`, `agent.capabilities.registry`
- 顶层符号：
  - L16: `class _EchoForTest(ToolPlugin)`
  - L27: `class _AlphaTool(ToolPlugin)`
  - L36: `class _ParallelTool(ToolPlugin)`
  - L46: `class _NoExec()`
  - L54: `class ToolRegistryTest(unittest.TestCase)`
  - L153: `class ToolDisplayDeclarationTest(unittest.TestCase)`
- 类成员：
  - L23: `_EchoForTest.execute(self, arguments)`
  - L32: `_AlphaTool.execute(self, arguments)`
  - L42: `_ParallelTool.execute(self, arguments)`
  - L57: `ToolRegistryTest.setUp(self)`
  - L60: `ToolRegistryTest.test_register_and_get(self)`
  - L66: `ToolRegistryTest.test_get_missing_returns_none(self)`
  - L70: `ToolRegistryTest.test_register_duplicate_rejected(self)`
  - L76: `ToolRegistryTest.test_register_empty_name_rejected(self)`
  - L83: `ToolRegistryTest.test_register_non_dict_parameters_rejected(self)`
  - L91: `ToolRegistryTest.test_register_non_callable_execute_rejected(self)`
  - L96: `ToolRegistryTest.test_disposer_removes_plugin(self)`
  - L102: `ToolRegistryTest.test_disposer_idempotent_and_reregister(self)`
  - L111: `ToolRegistryTest.test_schemas_sorted_and_snapshot(self)`
  - L122: `ToolRegistryTest.test_parallel_safe_predeclared(self)`
  - L127: `ToolRegistryTest.test_execute_contract(self)`
  - L133: `ToolRegistryTest.test_builtin_echo_integrates(self)`
  - L139: `ToolRegistryTest.test_dispose_all_clears_everything(self)`
  - L148: `ToolRegistryTest.test_dispose_all_empty_ok(self)`
  - L156: `ToolDisplayDeclarationTest.test_plugin_carries_display_fields(self)`
  - L171: `ToolDisplayDeclarationTest.test_defaults_are_empty(self)`
  - L183: `ToolDisplayDeclarationTest.test_display_list_shape(self)`

### A.530 `tests/test_tool_resume.py`

- 类型：Python
- 行数：68
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：内核挂起调用恢复入口。
- 导入：`__future__`, `unittest`, `types`, `agent.app`
- 顶层符号：
  - L11: `class _Contexts()`
  - L19: `class _Mesh()`
  - L28: `class ToolResumeTest(unittest.TestCase)`
- 类成员：
  - L12: `_Contexts.__init__(self, session)`
  - L15: `_Contexts.resolve_sync(self, _cid)`
  - L20: `_Mesh.__init__(self)`
  - L23: `_Mesh.submit(self, cid, payload)`
  - L29: `ToolResumeTest._app(self, pending)`
  - L35: `ToolResumeTest.test_rejects_missing_or_mismatched_pending(self)`
  - L42: `ToolResumeTest.test_submits_resume_and_clears_pending(self)`
  - L53: `ToolResumeTest.test_submit_failure_restores_pending(self)`

### A.531 `tests/test_tool_session_gate.py`

- 类型：Python
- 行数：62
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：ToolPort.execute 把会话桶填进管道：current_context().session.gate 即 resolve_sync 的门控。
- 导入：`__future__`, `sys`, `tempfile`, `unittest`, `pathlib`, `agent.app`, `agent.capabilities.registry`, `agent.core.ports`, `agent.core.session_scope`, `agent.core.tool_call`
- 顶层符号：
  - L20: `class _GateProbe(ToolPlugin)`
  - L32: `class ToolSessionGateTest(unittest.TestCase)`
- 类成员：
  - L26: `_GateProbe.execute(self, arguments)`
  - L35: `ToolSessionGateTest.setUp(self)`
  - L48: `ToolSessionGateTest.tearDown(self)`
  - L51: `ToolSessionGateTest.test_execute_fills_session_gate(self)`

### A.532 `tests/test_top_level_services.py`

- 类型：Python
- 行数：30
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：顶层服务解析与配置 schema 的边界测试。
- 导入：`__future__`, `unittest`, `agent.app_services`, `agent.config_schema`
- 顶层符号：
  - L11: `class AppServicesTest(unittest.TestCase)`
  - L23: `class ConfigSchemaTest(unittest.TestCase)`
- 类成员：
  - L12: `AppServicesTest.test_missing_service_reports_assembly_hint(self)`
  - L24: `ConfigSchemaTest.test_unknown_section_is_empty(self)`

### A.533 `tests/test_ui_registry.py`

- 类型：Python
- 行数：55
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：UI 路径的 pending、替换和 catalog 测试。
- 导入：`__future__`, `unittest`, `agent.capabilities.ui_registry`
- 顶层符号：
  - L10: `class UiRegistryTest(unittest.TestCase)`
- 类成员：
  - L11: `UiRegistryTest.setUp(self)`
  - L19: `UiRegistryTest.test_item_replace_and_restore(self)`
  - L33: `UiRegistryTest.test_duplicate_without_replace_rejected(self)`
  - L38: `UiRegistryTest.test_pending_item_flushes_when_parent_registered(self)`
  - L46: `UiRegistryTest.test_drop_owner_removes_item(self)`

### A.534 `tests/test_update.py`

- 类型：Python
- 行数：389
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：更新核心：版本、manifest、安全解压。
- 导入：`__future__`, `json`, `tempfile`, `unittest`, `zipfile`, `pathlib`, `unittest.mock`, `agent.update`, `agent.update.assets`, `agent.update.checker`, `agent.update.config_merge`, `agent.update.install`, `agent.update.manifest`, `agent.update.stage`, `agent.update.state`, `agent.update.version`, `scripts.pack_common`
- 顶层符号：
  - L24: `class PackagingBlacklistTest(unittest.TestCase)`
  - L60: `class VersionTest(unittest.TestCase)`
  - L84: `class ManifestTest(unittest.TestCase)`
  - L141: `class InstallLayoutTest(unittest.TestCase)`
  - L260: `class ControllerTest(unittest.TestCase)`
  - L299: `class PluginConfigTest(unittest.TestCase)`
  - L340: `class CoverageRootTest(unittest.TestCase)`
  - L383: `class FileHashTest(unittest.TestCase)`
- 类成员：
  - L25: `PackagingBlacklistTest.test_blacklist_keeps_nested_plugin_data_but_drops_root_runtime(self)`
  - L61: `VersionTest.test_semver_compare(self)`
  - L67: `VersionTest.test_invalid_version(self)`
  - L71: `VersionTest.test_prerelease_uses_semver_precedence(self)`
  - L85: `ManifestTest._raw(self)`
  - L95: `ManifestTest.test_parse_and_digest(self)`
  - L102: `ManifestTest.test_bad_schema(self)`
  - L106: `ManifestTest.test_check_disabled_without_url(self)`
  - L111: `ManifestTest.test_stage_package_from_local_asset(self)`
  - L134: `ManifestTest.test_zip_paths(self)`
  - L142: `InstallLayoutTest.test_apply_staged_updates_root_and_keeps_backup(self)`
  - L175: `InstallLayoutTest.test_nested_runtime_named_dir_is_backed_up(self)`
  - L204: `InstallLayoutTest.test_locked_launcher_is_archived_then_replaced(self)`
  - L233: `InstallLayoutTest.test_merge_removes_deleted_key(self)`
  - L246: `InstallLayoutTest.test_restore_backup(self)`
  - L261: `ControllerTest.test_controller_disabled_and_guards(self)`
  - L274: `ControllerTest.test_controller_uses_root_version(self)`
  - L283: `ControllerTest.test_dev_checkout_disables_update(self)`
  - L292: `ControllerTest.test_apply_without_state(self)`
  - L300: `PluginConfigTest.test_sensitive_config_is_not_default_distribution(self)`
  - L304: `PluginConfigTest.test_update_log_tail(self)`
  - L313: `PluginConfigTest.test_state_read_write(self)`
  - L319: `PluginConfigTest.test_local_secret_filter(self)`
  - L324: `PluginConfigTest.test_recover_rolls_back_unhealthy_target(self)`
  - L341: `CoverageRootTest.test_install_helpers(self)`
  - L355: `CoverageRootTest.test_apply_success_and_failure(self)`
  - L384: `FileHashTest.test_sha256_file(self)`

### A.535 `tests/test_update_processes.py`

- 类型：Python
- 行数：63
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：更新器进程边界：按安装路径停止旧 GUI。
- 导入：`__future__`, `os`, `shutil`, `subprocess`, `tempfile`, `time`, `unittest`, `pathlib`, `agent.update.processes`
- 顶层符号：
  - L21: `class ProcessStopTest(unittest.TestCase)`
- 类成员：
  - L22: `ProcessStopTest.test_removes_old_launcher_archives(self)`
  - L33: `ProcessStopTest.test_stops_matching_running_executable(self)`

### A.536 `tests/test_usage_metrics.py`

- 类型：Python
- 行数：118
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：命中率口径测试：只用官方 usage 的三个值，不自己造。
- 导入：`__future__`, `re`, `sys`, `unittest`, `pathlib`, `agent.shell.classic_adapter`, `agent.shell.classic_adapter.outbound`, `agent.shell.web.ui_bundle`
- 顶层符号：
  - L34: `class UsageFieldsAreOfficialTest(unittest.TestCase)`
  - L68: `class UiReadsTheOfficialFieldsTest(unittest.TestCase)`
  - L100: `class WindowComesFromKernelTest(unittest.TestCase)`
- 类成员：
  - L37: `UsageFieldsAreOfficialTest.test_contract_lists_the_official_fields(self)`
  - L42: `UsageFieldsAreOfficialTest._stream(self)`
  - L49: `UsageFieldsAreOfficialTest.test_outbound_forwards_them_unchanged(self)`
  - L60: `UsageFieldsAreOfficialTest.test_unknown_extra_fields_are_dropped_not_invented(self)`
  - L71: `UiReadsTheOfficialFieldsTest._src(self)`
  - L74: `UiReadsTheOfficialFieldsTest.test_ui_reads_the_official_names(self)`
  - L81: `UiReadsTheOfficialFieldsTest.test_hit_rate_uses_only_the_official_pair(self)`
  - L92: `UiReadsTheOfficialFieldsTest.test_accumulators_only_add_official_values(self)`
  - L103: `WindowComesFromKernelTest.test_pipeline_reports_the_configured_window(self)`

### A.537 `tests/test_version_stamp.py`

- 类型：Python
- 行数：103
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：步卡标题里的版本时刻：`file_undo` 卡片显示"文件 to HH:MM:SS"。
- 导入：`__future__`, `json`, `re`, `shutil`, `subprocess`, `sys`, `tempfile`, `unittest`, `pathlib`, `agent.mechanisms.file_safety`, `agent.shell.web.ui_bundle`
- 顶层符号：
  - L32: `def _extract_ts(mid)`
  - L40: `class VersionStampTest(unittest.TestCase)`
- 类成员：
  - L41: `VersionStampTest.test_frontend_regex_matches_backend_directory_names(self)`
  - L53: `VersionStampTest.test_frontend_has_two_unescaped_stamp_regexes(self)`
  - L71: `VersionStampTest.test_node_agrees_with_python(self)`
  - L95: `VersionStampTest.test_unparseable_ids_are_empty(self)`

### A.538 `tests/test_visual_app_integration.py`

- 类型：Python
- 行数：41
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：视觉操作 2.0 的宿主装配面。
- 导入：`__future__`, `tempfile`, `unittest`, `pathlib`, `agent.app`, `agent.mechanisms.session_store`
- 顶层符号：
  - L13: `class VisualAppAssemblyTest(unittest.TestCase)`
- 类成员：
  - L14: `VisualAppAssemblyTest.test_visual_plugin_is_loaded_with_kernel_hooks(self)`

### A.539 `tests/test_visual_context_integration.py`

- 类型：Python
- 行数：57
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：内核上下文钩子在模型请求组装阶段的接入。
- 导入：`__future__`, `unittest`, `types`, `agent.core.engine`, `agent.core.events`, `agent.core.modules.model_mod`, `agent.mechanisms.context.hooks`
- 顶层符号：
  - L14: `class _Log()`
  - L19: `class _Tools()`
  - L24: `class ModelHookIntegrationTest(unittest.TestCase)`
- 类成员：
  - L15: `_Log.derive_request_messages(self)`
  - L20: `_Tools.schemas(self)`
  - L25: `ModelHookIntegrationTest.test_hook_output_enters_request_messages(self)`
  - L36: `ModelHookIntegrationTest.test_engine_keeps_plugin_request_id_in_pending(self)`

### A.540 `tests/test_visual_operator.py`

- 类型：Python
- 行数：1978
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：Visual Operator 插件测试。
- 导入：`__future__`, `dataclasses`, `importlib.util`, `io`, `json`, `sys`, `tempfile`, `threading`, `time`, `types`, `unittest`, `pathlib`, `types`, `unittest`, `agent.core.session_scope`, `agent.mechanisms.live_state`, `fan_agent_plugins.visual_operator.tools.app`, `fan_agent_plugins.visual_operator`, `fan_agent_plugins.visual_operator.backends._unavailable`, `fan_agent_plugins.visual_operator.backends.win32_uia`
- 顶层符号：
  - L32: `def _load_plugin_module()`
  - L100: `def _png(width, height, color)`
  - L107: `class Recorder()`
  - L122: `class TrackingMouse()`
  - L137: `class WarpingMouse(TrackingMouse)`
  - L152: `class LiveState()`
  - L160: `def _backend(rect, png, cursor, mixed_scale, windows, hit)`
  - L172: `def _window_info(hwnd, rect, foreground)`
  - L179: `class CoordsTest(unittest.TestCase)`
  - L199: `class CaptureStoreTest(unittest.TestCase)`
  - L232: `class KeysTest(unittest.TestCase)`
  - L261: `class ConfigTest(unittest.TestCase)`
  - L297: `class CanvasTest(unittest.TestCase)`
  - L383: `class EyeToolTest(unittest.TestCase)`
  - L495: `class WindowCaptureTest(unittest.TestCase)`
  - L608: `class WindowActivationTest(unittest.TestCase)`
  - L668: `class MouseToolTest(unittest.TestCase)`
  - L752: `class KeyboardToolTest(unittest.TestCase)`
  - L787: `class HoverCaptureTest(unittest.TestCase)`
  - L885: `class WindowHoverTest(unittest.TestCase)`
  - L1001: `class ShotTest(unittest.TestCase)`
  - L1058: `class ClickEvidenceTest(unittest.TestCase)`
  - L1143: `class DiffTest(unittest.TestCase)`
  - L1160: `class _Scripted()`
  - L1174: `class WaitToolTest(unittest.TestCase)`
  - L1313: `class AmbiguityNoteTest(unittest.TestCase)`
  - L1358: `class ScaleHintTest(unittest.TestCase)`
  - L1371: `def _try_lock(result)`
  - L1379: `class IsolationTest(unittest.TestCase)`
  - L1403: `class LocatorToolsTest(unittest.TestCase)`
  - L1514: `class WindowAppOpenTest(unittest.TestCase)`
  - L1610: `class PipelineTest(unittest.TestCase)`
  - L1667: `class ActToolTest(unittest.TestCase)`
  - L1721: `class PluginTest(unittest.TestCase)`
  - L1764: `def _load_macos_module()`
  - L1778: `class Win32TableTest(unittest.TestCase)`
  - L1949: `class MacOSTableTest(unittest.TestCase)`
- 类成员：
  - L110: `Recorder.__init__(self)`
  - L114: `Recorder.__getattr__(self, name)`
  - L125: `TrackingMouse.__init__(self, cursor)`
  - L129: `TrackingMouse.cursor(self)`
  - L132: `TrackingMouse.move(self, point, duration_ms)`
  - L140: `WarpingMouse.__init__(self, cursor, target)`
  - L145: `WarpingMouse.move(self, point, duration_ms)`
  - L153: `LiveState.__init__(self, mode)`
  - L156: `LiveState.get_mode(self, _cid)`
  - L180: `CoordsTest.test_rect_bounds_and_intersection(self)`
  - L187: `CoordsTest.test_rect_rejects_empty(self)`
  - L191: `CoordsTest.test_geometry_reports_ratio(self)`
  - L200: `CaptureStoreTest.test_image_coordinates_map_with_origin_and_scale(self)`
  - L207: `CaptureStoreTest.test_out_of_image_and_wrong_session_are_rejected(self)`
  - L217: `CaptureStoreTest.test_ttl_and_capacity_evict_old_entries(self)`
  - L233: `KeysTest.test_aliases_normalize(self)`
  - L239: `KeysTest.test_unknown_key_names_hint(self)`
  - L246: `KeysTest.test_hotkey_forms(self)`
  - L251: `KeysTest.test_hotkey_rejects_bad_shapes(self)`
  - L256: `KeysTest.test_canonical_set_is_coverable(self)`
  - L262: `ConfigTest.setUp(self)`
  - L267: `ConfigTest._write(self, text)`
  - L270: `ConfigTest.test_missing_file_uses_defaults(self)`
  - L273: `ConfigTest.test_values_are_read_and_clamped(self)`
  - L290: `ConfigTest.test_bad_values_fall_back(self)`
  - L298: `CanvasTest.test_scales_and_reports(self)`
  - L308: `CanvasTest.test_offset_maps_screen_units_to_sent_pixels(self)`
  - L313: `CanvasTest.test_cursor_mark_follows_screen_extent(self)`
  - L325: `CanvasTest.test_cursor_crosshair_is_wide_and_labelled(self)`
  - L338: `CanvasTest.test_tiny_area_hides_cursor_label(self)`
  - L343: `CanvasTest.test_cursor_font_screen_size_is_scale_consistent(self)`
  - L348: `CanvasTest.test_cursor_center_pixel_stays_visible(self)`
  - L358: `CanvasTest.test_grid_and_cursor_change_pixels(self)`
  - L367: `CanvasTest.test_blank_and_tiny_images(self)`
  - L377: `CanvasTest.test_bad_png_raises(self)`
  - L384: `EyeToolTest.setUp(self)`
  - L387: `EyeToolTest.test_description_names_the_guide_lines(self)`
  - L391: `EyeToolTest.test_annotate_both_returns_annotated_then_raw(self)`
  - L401: `EyeToolTest.test_annotate_raw_skips_grid_and_overlay(self)`
  - L410: `EyeToolTest.test_annotate_unknown_value_is_rejected(self)`
  - L415: `EyeToolTest.test_returns_image_attachment(self)`
  - L428: `EyeToolTest.test_region_is_clipped_to_screen(self)`
  - L435: `EyeToolTest.test_region_needs_four_numbers(self)`
  - L443: `EyeToolTest.test_oversized_region_rejected(self)`
  - L450: `EyeToolTest.test_notes_report_shrinking_and_blank(self)`
  - L459: `EyeToolTest.test_note_reports_mixed_scale(self)`
  - L464: `EyeToolTest.test_grid_switch_is_reported(self)`
  - L474: `EyeToolTest.test_capture_id_and_image_mapping_are_returned(self)`
  - L489: `EyeToolTest.test_unknown_argument_rejected(self)`
  - L498: `WindowCaptureTest.setUp(self)`
  - L508: `WindowCaptureTest.test_window_title_routes_to_window_port(self)`
  - L516: `WindowCaptureTest.test_hwnd_skips_title_lookup(self)`
  - L522: `WindowCaptureTest.test_region_is_passed_through(self)`
  - L529: `WindowCaptureTest.test_window_and_hwnd_are_exclusive(self)`
  - L534: `WindowCaptureTest.test_missing_window_port_reports_clearly(self)`
  - L540: `WindowCaptureTest.test_no_matching_window(self)`
  - L547: `WindowCaptureTest.test_screen_fallback_is_reported(self)`
  - L557: `WindowCaptureTest.test_window_content_has_no_fallback_note(self)`
  - L562: `WindowCaptureTest.test_restore_only_does_not_steal_foreground(self)`
  - L576: `WindowCaptureTest.test_activate_requested_reports_success(self)`
  - L589: `WindowCaptureTest.test_activate_failure_is_reported(self)`
  - L601: `WindowCaptureTest.test_activate_rejected_for_plain_screen(self)`
  - L611: `WindowActivationTest.setUp(self)`
  - L616: `WindowActivationTest.test_mouse_activates_before_click(self)`
  - L626: `WindowActivationTest.test_keyboard_activates_before_typing(self)`
  - L636: `WindowActivationTest.test_failed_activation_blocks_input(self)`
  - L652: `WindowActivationTest.test_cursor_query_does_not_activate(self)`
  - L659: `WindowActivationTest.test_activation_reports_matched_when_titles_collide(self)`
  - L669: `MouseToolTest.setUp(self)`
  - L674: `MouseToolTest.test_move_and_click(self)`
  - L682: `MouseToolTest.test_drag_scroll_and_cursor(self)`
  - L692: `MouseToolTest.test_out_of_screen_point_rejected(self)`
  - L696: `MouseToolTest.test_image_coordinates_are_converted_by_the_tool(self)`
  - L711: `MouseToolTest.test_image_coordinates_need_a_valid_capture(self)`
  - L727: `MouseToolTest.test_parameter_matrix(self)`
  - L741: `MouseToolTest.test_plan_gate(self)`
  - L753: `KeyboardToolTest.setUp(self)`
  - L758: `KeyboardToolTest.test_type_key_and_hotkey(self)`
  - L769: `KeyboardToolTest.test_bad_parameters(self)`
  - L778: `KeyboardToolTest.test_plan_gate_blocks(self)`
  - L790: `HoverCaptureTest.setUp(self)`
  - L800: `HoverCaptureTest.test_hover_moves_cursor_before_capture(self)`
  - L807: `HoverCaptureTest.test_hover_wiggle_moves_around_and_returns(self)`
  - L819: `HoverCaptureTest.test_hover_wiggle_recovers_if_target_warps_cursor(self)`
  - L830: `HoverCaptureTest.test_hover_path_is_walked_before_the_endpoint(self)`
  - L841: `HoverCaptureTest.test_hover_path_requires_hover(self)`
  - L845: `HoverCaptureTest.test_hover_path_length_is_limited(self)`
  - L852: `HoverCaptureTest.test_grid_step_can_be_tightened_for_small_targets(self)`
  - L858: `HoverCaptureTest.test_hover_requires_two_integers(self)`
  - L863: `HoverCaptureTest.test_hover_settle_is_reported_and_clamped(self)`
  - L869: `HoverCaptureTest.test_hover_outside_the_screen_is_rejected(self)`
  - L874: `HoverCaptureTest.test_hover_is_blocked_in_plan_mode(self)`
  - L888: `WindowHoverTest.test_hover_runs_after_activation_and_before_capture(self)`
  - L931: `WindowHoverTest.test_plain_window_capture_does_not_pass_a_prepare_hook(self)`
  - L954: `WindowHoverTest.test_cursor_layer_different_from_capture_window_is_reported(self)`
  - L978: `WindowHoverTest.test_hover_without_window_captures_the_cursor_layer(self)`
  - L1004: `ShotTest.setUp(self)`
  - L1013: `ShotTest.test_mouse_shot_returns_image_and_receipt(self)`
  - L1023: `ShotTest.test_mouse_without_shot_returns_plain_dict(self)`
  - L1030: `ShotTest.test_keyboard_shot_returns_image(self)`
  - L1037: `ShotTest.test_shot_region_is_clipped(self)`
  - L1044: `ShotTest.test_shot_region_shape_is_validated(self)`
  - L1051: `ShotTest.test_shot_rejected_for_cursor_query(self)`
  - L1061: `ClickEvidenceTest.setUp(self)`
  - L1064: `ClickEvidenceTest.test_hit_report_is_included(self)`
  - L1073: `ClickEvidenceTest.test_hit_is_omitted_without_a_hit_port(self)`
  - L1079: `ClickEvidenceTest.test_changed_is_zero_when_nothing_moves(self)`
  - L1085: `ClickEvidenceTest.test_changed_is_not_measured_for_move(self)`
  - L1092: `ClickEvidenceTest.test_navigation_is_reported_when_local_pixels_do_not_move(self)`
  - L1114: `ClickEvidenceTest.test_shot_follows_the_landed_window_not_the_title(self)`
  - L1135: `ClickEvidenceTest.test_local_still_is_resampled_once(self)`
  - L1144: `DiffTest.test_same_image_has_no_change(self)`
  - L1148: `DiffTest.test_different_image_changes(self)`
  - L1153: `DiffTest.test_probe_region_follows_the_point_and_clips(self)`
  - L1163: `_Scripted.__init__(self)`
  - L1167: `_Scripted.__getattr__(self, name)`
  - L1175: `WaitToolTest.setUp(self)`
  - L1178: `WaitToolTest._screen(self, pngs)`
  - L1190: `WaitToolTest.test_change_satisfies_immediately(self)`
  - L1198: `WaitToolTest.test_title_change_satisfies_change_without_pixel_motion(self)`
  - L1216: `WaitToolTest.test_change_times_out_without_raising(self)`
  - L1224: `WaitToolTest.test_window_appears(self)`
  - L1243: `WaitToolTest.test_window_that_already_exists_is_flagged_as_already(self)`
  - L1256: `WaitToolTest.test_window_disappeared_before_waiting_is_flagged_as_already(self)`
  - L1267: `WaitToolTest.test_window_disappears_times_out(self)`
  - L1277: `WaitToolTest.test_window_condition_needs_a_title(self)`
  - L1282: `WaitToolTest.test_change_on_a_minimized_window_is_rejected(self)`
  - L1294: `WaitToolTest.test_bad_parameters(self)`
  - L1306: `WaitToolTest.test_unknown_argument_rejected(self)`
  - L1316: `AmbiguityNoteTest.test_matched_windows_are_spelled_out(self)`
  - L1334: `AmbiguityNoteTest.test_single_window_has_no_ambiguity_note(self)`
  - L1345: `AmbiguityNoteTest.test_hover_on_a_background_window_asks_for_activation(self)`
  - L1361: `ScaleHintTest.test_shrunk_image_reports_the_multiplier(self)`
  - L1380: `IsolationTest.test_input_lock_times_out_for_another_thread(self)`
  - L1388: `IsolationTest.test_input_guard_is_reentrant_in_one_thread(self)`
  - L1393: `IsolationTest.test_unavailable_backend_reports(self)`
  - L1404: `LocatorToolsTest.setUp(self)`
  - L1417: `LocatorToolsTest.test_find_returns_uia_matches(self)`
  - L1422: `LocatorToolsTest.test_find_without_locator_reports_unavailable(self)`
  - L1428: `LocatorToolsTest.test_find_empty_result_tells_model_not_to_repeat(self)`
  - L1436: `LocatorToolsTest.test_click_text_uses_clickable_point(self)`
  - L1444: `LocatorToolsTest.test_type_into_clears_types_and_submits(self)`
  - L1456: `LocatorToolsTest.test_click_region_maps_image_rect_to_screen(self)`
  - L1466: `LocatorToolsTest.test_click_region_clicks_the_rectangle_center(self)`
  - L1474: `LocatorToolsTest.test_type_into_accepts_a_visual_rect_without_uia(self)`
  - L1485: `LocatorToolsTest.test_keyboard_type_reports_focused_control(self)`
  - L1497: `LocatorToolsTest.test_uia_locator_parses_powershell_json(self)`
  - L1515: `WindowAppOpenTest.test_title_matching_ignores_invisible_format_chars(self)`
  - L1519: `WindowAppOpenTest.setUp(self)`
  - L1533: `WindowAppOpenTest.test_window_list_and_activate(self)`
  - L1540: `WindowAppOpenTest.test_window_waits_until_visible(self)`
  - L1556: `WindowAppOpenTest.test_app_launches_and_returns_hwnd(self)`
  - L1568: `WindowAppOpenTest.test_open_binds_a_new_window_instead_of_stale_title_match(self)`
  - L1589: `WindowAppOpenTest.test_app_name_resolves_start_menu_shortcut(self)`
  - L1602: `WindowAppOpenTest.test_open_url_uses_default_handler(self)`
  - L1611: `PipelineTest.test_scalar_app_and_step_limits(self)`
  - L1619: `PipelineTest.test_window_string_and_wait_ms_are_accepted(self)`
  - L1627: `PipelineTest.test_destructive_and_read_only_checks(self)`
  - L1634: `PipelineTest.test_run_stops_on_failure_and_logs_steps(self)`
  - L1647: `PipelineTest.test_run_enforces_total_timeout_after_a_step(self)`
  - L1658: `PipelineTest.test_run_honours_expect_failure(self)`
  - L1668: `ActToolTest.setUp(self)`
  - L1681: `ActToolTest.test_batch_find_and_click(self)`
  - L1691: `ActToolTest.test_batch_resolves_prior_step_fields(self)`
  - L1701: `ActToolTest.test_changed_expectation_uses_action_evidence(self)`
  - L1709: `ActToolTest.test_batch_rejects_destructive_target(self)`
  - L1714: `ActToolTest.test_continue_requires_read_only_steps(self)`
  - L1722: `PluginTest.test_build_tools_honours_switches(self)`
  - L1737: `PluginTest.test_register_returns_disposers(self)`
  - L1779: `Win32TableTest.test_key_table_covers_canonical_names(self)`
  - L1784: `Win32TableTest.test_utf16_units_and_unknown_key(self)`
  - L1791: `Win32TableTest.test_scroll_delta_matches_contract(self)`
  - L1802: `Win32TableTest.test_uniform_detection_catches_black_frames(self)`
  - L1809: `Win32TableTest.test_crop_bgra_uses_top_down_rows(self)`
  - L1817: `Win32TableTest.test_window_capture_does_not_touch_screen_grab(self)`
  - L1831: `Win32TableTest._capture(self, iconic, activate)`
  - L1846: `Win32TableTest.test_minimized_capture_restores_without_stealing_focus(self)`
  - L1853: `Win32TableTest.test_activate_uses_foreground_path(self)`
  - L1860: `Win32TableTest.test_visible_window_is_left_alone(self)`
  - L1867: `Win32TableTest.test_visible_window_activates_only_when_asked(self)`
  - L1874: `Win32TableTest.test_find_prefers_foreground_then_z_order(self)`
  - L1907: `Win32TableTest.test_find_without_foreground_falls_back_to_z_order(self)`
  - L1927: `Win32TableTest.test_hit_probe_reports_class_and_root_title(self)`
  - L1942: `Win32TableTest.test_hit_probe_returns_empty_when_nothing_is_there(self)`
  - L1952: `MacOSTableTest.test_keycodes_cover_canonical_names(self)`
  - L1958: `MacOSTableTest.test_point_and_unknown_key(self)`
  - L1965: `MacOSTableTest.test_scroll_delta_matches_contract(self)`

### A.541 `tests/test_visual_operator_2.py`

- 类型：Python
- 行数：900
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：视觉操作 2.0 全局授权与上下文钩子。
- 导入：`__future__`, `ctypes`, `json`, `sys`, `tempfile`, `threading`, `time`, `unittest`, `pathlib`, `types`, `unittest.mock`, `PIL`, `agent.core.context`, `agent.core.session_scope`, `plugins.visual_operator_2.config`, `plugins.visual_operator_2.plugin`, `plugins.visual_operator_2.routes`, `plugins.visual_operator_2.state`, `plugins.visual_operator_2.tools`
- 顶层符号：
  - L27: `class InjectedInputTagTest(unittest.TestCase)`
  - L69: `class VisionRuntimeTest(unittest.TestCase)`
- 类成员：
  - L28: `InjectedInputTagTest.test_injected_inputs_carry_foreign_tag(self)`
  - L49: `InjectedInputTagTest.test_registered_tag_filters_keyboard_even_with_injected_bit(self)`
  - L70: `VisionRuntimeTest._runtime(self)`
  - L78: `VisionRuntimeTest.test_consent_owner_and_observation(self)`
  - L107: `VisionRuntimeTest.test_observation_includes_multiple_frames(self)`
  - L129: `VisionRuntimeTest.test_on_demand_capture_replaces_background_sampling(self)`
  - L153: `VisionRuntimeTest.test_new_consent_call_supersedes_pending_request(self)`
  - L167: `VisionRuntimeTest.test_reject_does_not_open(self)`
  - L178: `VisionRuntimeTest.test_context_hook_appends_full_frame(self)`
  - L197: `VisionRuntimeTest.test_context_hook_publishes_exact_model_frame(self)`
  - L226: `VisionRuntimeTest.test_confirm_route_resumes_pending_call(self)`
  - L257: `VisionRuntimeTest.test_tools_require_consent_and_close_cleanly(self)`
  - L281: `VisionRuntimeTest.test_model_point_uses_both_image_sizes(self)`
  - L310: `VisionRuntimeTest.test_user_takeover_closes_eyes_and_blocks_actions(self)`
  - L326: `VisionRuntimeTest.test_model_point_matches_user_example(self)`
  - L348: `VisionRuntimeTest.test_native_full_image_is_screen_identity(self)`
  - L375: `VisionRuntimeTest.test_model_stretched_image_uses_independent_axes(self)`
  - L395: `VisionRuntimeTest.test_single_click_count_and_interval(self)`
  - L414: `VisionRuntimeTest.test_click_sequence_uses_same_point_conversion(self)`
  - L441: `VisionRuntimeTest.test_zero_move_is_not_reported_as_moved(self)`
  - L460: `VisionRuntimeTest.test_trajectory_duration_and_same_point_skip(self)`
  - L486: `VisionRuntimeTest.test_focus_region_maps_compressed_image_center(self)`
  - L503: `VisionRuntimeTest.test_focus_region_and_move_focus(self)`
  - L533: `VisionRuntimeTest.test_focus_accepts_10px_region(self)`
  - L546: `VisionRuntimeTest.test_move_focus_tool_executes_without_check_points(self)`
  - L571: `VisionRuntimeTest.test_click_tools_and_sequence_contract(self)`
  - L591: `VisionRuntimeTest.test_calibration_can_be_disabled(self)`
  - L613: `VisionRuntimeTest.test_random_calibration_points(self)`
  - L652: `VisionRuntimeTest.test_check_error_comes_after_eye_state(self)`
  - L667: `VisionRuntimeTest.test_five_calibration_failures_close_eyes(self)`
  - L685: `VisionRuntimeTest.test_coordinate_tools_require_check_points(self)`
  - L695: `VisionRuntimeTest.test_step_log_writes_jsonl_and_reports_failure(self)`
  - L714: `VisionRuntimeTest.test_calibration_report_rejects_wrong_point_count(self)`
  - L725: `VisionRuntimeTest.test_built_tools_keep_tool_plugin_type(self)`
  - L732: `VisionRuntimeTest.test_step_log_path_uses_error_log_root(self)`
  - L742: `VisionRuntimeTest.test_key_shortcut_uses_sendinput_batch(self)`
  - L754: `VisionRuntimeTest.test_desktop_tools_are_registered_and_authorized(self)`
  - L773: `VisionRuntimeTest.test_desktop_tool_requires_authorization_and_blocks_core_overlap(self)`
  - L803: `VisionRuntimeTest.test_key_fallback_reports_alt_tab_success_and_win_failure(self)`
  - L811: `VisionRuntimeTest.test_visual_skill_is_registered(self)`
  - L828: `VisionRuntimeTest.test_human_mouse_takeover_after_100px(self)`
  - L840: `VisionRuntimeTest.test_input_monitor_fires_once_in_worker(self)`
  - L861: `VisionRuntimeTest.test_actions_use_fake_backend_and_wake_on_change(self)`

### A.542 `tests/test_wake_scheduler.py`

- 类型：Python
- 行数：287
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：唤醒调度器：注册、到期、恢复、取消与重复投递。
- 导入：`__future__`, `tempfile`, `unittest`, `pathlib`, `typing`, `agent.app`, `agent.core.context`, `agent.core.events`, `agent.core.ports`, `agent.core.tool_call`, `agent.mechanisms.conversation_queue`, `agent.mechanisms.live_state`, `agent.mechanisms.mesh`, `agent.mechanisms.session_store`, `agent.mechanisms.wake_scheduler`
- 顶层符号：
  - L26: `class _Clock()`
  - L34: `class WakeSchedulerTest(unittest.TestCase)`
  - L148: `class RealMeshDispatcherTest(unittest.TestCase)`
  - L211: `class WakeToolTest(unittest.TestCase)`
  - L272: `class QueueDedupeTest(unittest.TestCase)`
- 类成员：
  - L27: `_Clock.__init__(self, value)`
  - L30: `_Clock.__call__(self)`
  - L35: `WakeSchedulerTest.setUp(self)`
  - L42: `WakeSchedulerTest._submit(self, cid, message)`
  - L46: `WakeSchedulerTest._scheduler(self)`
  - L54: `WakeSchedulerTest.test_sleep_registers_and_delivers_once(self)`
  - L71: `WakeSchedulerTest.test_cancel_prevents_delivery(self)`
  - L82: `WakeSchedulerTest.test_restart_recovers_pending_job(self)`
  - L93: `WakeSchedulerTest.test_restart_does_not_repeat_delivered_job(self)`
  - L104: `WakeSchedulerTest.test_list_filters_by_target_and_owner(self)`
  - L115: `WakeSchedulerTest.test_target_must_exist_for_other_session(self)`
  - L127: `WakeSchedulerTest.test_invalid_schedules_are_rejected(self)`
  - L141: `WakeSchedulerTest.test_parse_due_at_normalizes_z(self)`
  - L149: `RealMeshDispatcherTest.setUp(self)`
  - L160: `RealMeshDispatcherTest._scheduler(self)`
  - L164: `RealMeshDispatcherTest.test_idle_dispatch_goes_through_mesh_activator(self)`
  - L176: `RealMeshDispatcherTest.test_busy_target_is_queued_with_dedupe_key(self)`
  - L190: `RealMeshDispatcherTest.test_process_lock_allows_one_scheduler(self)`
  - L199: `RealMeshDispatcherTest.test_terminal_jobs_are_pruned(self)`
  - L212: `WakeToolTest.setUp(self)`
  - L221: `WakeToolTest._call(self, name, arguments)`
  - L235: `WakeToolTest.test_sleep_list_cancel(self)`
  - L250: `WakeToolTest.test_app_wake_state_helpers(self)`
  - L263: `WakeToolTest.test_schedule_rejects_past(self)`
  - L273: `QueueDedupeTest.test_dedupe_key_does_not_create_second_item(self)`

### A.543 `tests/test_web_auth.py`

- 类型：Python
- 行数：551
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：HTTP 鉴权：密码、会话、Token、策略与来源判定。
- 导入：`__future__`, `http.client`, `json`, `os`, `subprocess`, `sys`, `tempfile`, `threading`, `time`, `unittest`, `concurrent.futures`, `http.server`, `pathlib`, `types`, `typing`, `unittest`, `agent.config_schema`, `agent.shell.web`, `agent.shell.web.auth`, `agent.shell.web.auth`
- 顶层符号：
  - L35: `class PasswordTest(unittest.TestCase)`
  - L42: `class CredentialTest(unittest.TestCase)`
  - L53: `class SessionTest(unittest.TestCase)`
  - L69: `class TokenTest(unittest.TestCase)`
  - L146: `class TokenCliTest(unittest.TestCase)`
  - L175: `class PolicyTest(unittest.TestCase)`
  - L196: `class RuntimeTest(unittest.TestCase)`
  - L278: `class DesktopBootstrapTest(unittest.TestCase)`
  - L320: `class GuiAutoProvisionTest(unittest.TestCase)`
  - L337: `class SchemaDefaultTest(unittest.TestCase)`
  - L343: `class ProviderExtensionTest(unittest.TestCase)`
  - L377: `class WebAuthHttpTest(unittest.TestCase)`
  - L466: `class RequestBoundaryTest(unittest.TestCase)`
  - L490: `class TlsGuardTest(unittest.TestCase)`
  - L502: `class CreateServerAuthTest(unittest.TestCase)`
  - L528: `class StreamSessionTest(unittest.TestCase)`
- 类成员：
  - L36: `PasswordTest.test_hash_roundtrip_and_wrong_password(self)`
  - L43: `CredentialTest.test_store_and_verify(self)`
  - L54: `SessionTest.test_create_validate_and_revoke(self)`
  - L62: `SessionTest.test_expiry(self)`
  - L70: `TokenTest.test_duplicate_token_name_is_rejected(self)`
  - L78: `TokenTest.test_cross_process_issue_keeps_all_tokens(self)`
  - L99: `TokenTest.test_threaded_issue_keeps_all_tokens(self)`
  - L114: `TokenTest.test_issue_does_not_resurrect_revoked(self)`
  - L133: `TokenTest.test_issue_verify_and_revoke(self)`
  - L147: `TokenCliTest.test_lock_failure_is_reported_without_traceback(self)`
  - L176: `PolicyTest.test_public_and_scope(self)`
  - L197: `RuntimeTest.test_public_without_password_is_blocked(self)`
  - L207: `RuntimeTest.test_config_reads_auth_section(self)`
  - L220: `RuntimeTest.test_unusable_auth_dir_falls_back(self)`
  - L246: `RuntimeTest.test_login_issues_session_and_csrf(self)`
  - L279: `DesktopBootstrapTest.test_one_time_loopback_bootstrap_session(self)`
  - L321: `GuiAutoProvisionTest.test_gui_startup_creates_initial_password(self)`
  - L338: `SchemaDefaultTest.test_schema_uses_copy_not_alias(self)`
  - L344: `ProviderExtensionTest.test_provider_module_can_supply_principal(self)`
  - L378: `WebAuthHttpTest.setUp(self)`
  - L397: `WebAuthHttpTest.request(self, method, path, body, headers)`
  - L407: `WebAuthHttpTest.test_healthz_reports_fallback_target(self)`
  - L417: `WebAuthHttpTest.test_login_page_has_window_close(self)`
  - L424: `WebAuthHttpTest.test_guard_login_csrf_and_logout(self)`
  - L467: `RequestBoundaryTest.test_trusted_proxy_and_host(self)`
  - L491: `TlsGuardTest.test_tls_wraps_socket_and_reports_failure(self)`
  - L503: `CreateServerAuthTest.test_required_mode_has_no_embedded_bypass(self)`
  - L529: `StreamSessionTest.test_stream_drops_revoked_session(self)`

### A.544 `tests/test_web_frontend.py`

- 类型：Python
- 行数：91
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：Web 事件通道测试 —— `Channel` 背压与生命周期（纯 Python，与用哪套 UI 无关）。
- 导入：`__future__`, `sys`, `threading`, `time`, `unittest`, `pathlib`, `agent.shell.sse`
- 顶层符号：
  - L27: `class ChannelBackpressureTest(unittest.TestCase)`
- 类成员：
  - L30: `ChannelBackpressureTest.test_frames_arrive_in_order(self)`
  - L38: `ChannelBackpressureTest.test_idle_returns_heartbeat_not_none(self)`
  - L44: `ChannelBackpressureTest.test_slow_consumer_drops_oldest_keeps_latest(self)`
  - L59: `ChannelBackpressureTest.test_close_returns_none_and_stops_accepting(self)`
  - L67: `ChannelBackpressureTest.test_concurrent_push_and_pop_is_safe(self)`

### A.545 `tests/test_web_shell.py`

- 类型：Python
- 行数：1040
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：Web 壳测试——HTTP/SSE 端点、写盘门控闭环、多会话隔离。
- 导入：`__future__`, `json`, `os`, `sys`, `tempfile`, `threading`, `time`, `unittest`, `urllib.error`, `urllib.request`, `pathlib`, `agent.app`, `agent.core.model_call`, `agent.core.tool_call`, `agent.mechanisms.live_state`, `agent.mechanisms.session_store`, `agent.shell.web.server`, `tests.testkit`
- 顶层符号：
  - L37: `class ScriptedProvider()`
  - L99: `class EchoProvider()`
  - L105: `class _ServerFixture(unittest.TestCase)`
  - L262: `class EndpointTest(_ServerFixture)`
  - L339: `class DateGroupTest(unittest.TestCase)`
  - L364: `class FileViewerContractTest(_ServerFixture)`
  - L494: `class MultiRootFileViewerTest(unittest.TestCase)`
  - L598: `class SseContractTest(_ServerFixture)`
  - L854: `def is_drive_root_text(path_text)`
  - L859: `class DirBrowseDriveRootTest(_ServerFixture)`
  - L894: `class DirBrowseQueryTest(_ServerFixture)`
  - L916: `class ConcurrencyTest(_ServerFixture)`
  - L971: `def _pending_confirm_ids(gate)`
  - L981: `class WriteGateOverWebTest(_ServerFixture)`
- 类成员：
  - L47: `ScriptedProvider.__init__(self, target)`
  - L52: `ScriptedProvider._extract_confirm_id(request)`
  - L74: `ScriptedProvider.stream(self, request)`
  - L102: `EchoProvider.stream(self, request)`
  - L112: `_ServerFixture.setUp(self)`
  - L154: `_ServerFixture._teardown(self)`
  - L166: `_ServerFixture._read_sse(self)`
  - L191: `_ServerFixture._wait_channels(self, count, timeout)`
  - L200: `_ServerFixture.get(self, path, timeout)`
  - L207: `_ServerFixture.get_json(self, path)`
  - L215: `_ServerFixture.put_json(self, path, payload)`
  - L234: `_ServerFixture.post(self, path, payload)`
  - L251: `_ServerFixture.wait_turn(self, cid, timeout)`
  - L255: `_ServerFixture.types_of(self, cid)`
  - L265: `EndpointTest.test_pages_and_assets_served(self)`
  - L287: `EndpointTest.test_health_endpoint(self)`
  - L295: `EndpointTest.test_setup_route_is_removed(self)`
  - L299: `EndpointTest.test_unknown_path_404(self)`
  - L305: `EndpointTest.test_send_rejects_bad_input(self)`
  - L318: `EndpointTest.test_media_endpoint_guards_root(self)`
  - L331: `EndpointTest.test_media_missing_file_404(self)`
  - L342: `DateGroupTest.test_groups_by_natural_day(self)`
  - L351: `DateGroupTest.test_older_is_grouped_by_date(self)`
  - L367: `FileViewerContractTest._write(self, rel, text)`
  - L373: `FileViewerContractTest.test_relative_path_reads_text(self)`
  - L384: `FileViewerContractTest.test_absolute_path_inside_root_is_accepted(self)`
  - L394: `FileViewerContractTest.test_absolute_path_outside_root_is_forbidden(self)`
  - L402: `FileViewerContractTest.test_traversal_cannot_escape_roots(self)`
  - L429: `FileViewerContractTest.test_missing_file_inside_root_is_404_not_403(self)`
  - L437: `FileViewerContractTest.test_max_chars_zero_returns_full_file(self)`
  - L454: `FileViewerContractTest.test_binary_is_reported_not_dumped(self)`
  - L465: `FileViewerContractTest.test_list_returns_entries_with_rel_and_type(self)`
  - L478: `FileViewerContractTest.test_list_absolute_path_inside_root(self)`
  - L487: `FileViewerContractTest.test_list_outside_root_is_forbidden(self)`
  - L497: `MultiRootFileViewerTest.setUp(self)`
  - L524: `MultiRootFileViewerTest._teardown(self)`
  - L535: `MultiRootFileViewerTest._get(self, path)`
  - L543: `MultiRootFileViewerTest.test_absolute_path_in_first_root(self)`
  - L550: `MultiRootFileViewerTest.test_absolute_path_in_second_root(self)`
  - L558: `MultiRootFileViewerTest.test_relative_path_resolves_against_each_root(self)`
  - L566: `MultiRootFileViewerTest.test_outside_all_roots_is_forbidden(self)`
  - L572: `MultiRootFileViewerTest.test_missing_in_a_root_is_404_not_403(self)`
  - L578: `MultiRootFileViewerTest.test_list_reports_rel_against_matched_root(self)`
  - L587: `MultiRootFileViewerTest.test_roots_are_resolved_and_deduplicated_by_normalize(self)`
  - L601: `SseContractTest.test_turn_events_reach_the_stream(self)`
  - L629: `SseContractTest.test_every_frame_carries_conversation_id(self)`
  - L639: `SseContractTest.test_two_sessions_do_not_cross(self)`
  - L650: `SseContractTest.test_history_and_sessions_endpoints(self)`
  - L677: `SseContractTest.test_sessions_without_title_file_return_unknown(self)`
  - L693: `SseContractTest.test_title_falls_back_to_user_message_when_generation_fails(self)`
  - L707: `SseContractTest.test_sessions_prefer_the_persisted_title(self)`
  - L719: `SseContractTest.test_sessions_sorted_by_recent_activity(self)`
  - L730: `SseContractTest.test_sessions_carry_date_group(self)`
  - L739: `SseContractTest.test_health_reports_model_for_header(self)`
  - L750: `SseContractTest.test_reasoning_effort_roundtrip(self)`
  - L774: `SseContractTest.test_reasoning_effort_rejects_invalid(self)`
  - L789: `SseContractTest.test_reasoning_effort_is_per_conversation(self)`
  - L800: `SseContractTest.test_dir_browse_drives_layer(self)`
  - L809: `SseContractTest.test_dir_browse_root_parent_is_drives(self)`
  - L820: `SseContractTest.test_dir_browse_item_shape_and_ordering(self)`
  - L836: `SseContractTest.test_dir_browse_missing_path_falls_back(self)`
  - L844: `SseContractTest.test_dir_browse_relative_path_uses_workspace_base(self)`
  - L872: `DirBrowseDriveRootTest.setUpClass(cls)`
  - L876: `DirBrowseDriveRootTest.test_relative_path_prefers_concrete_workspace_root(self)`
  - L885: `DirBrowseDriveRootTest.test_drive_root_parent_is_drives_layer(self)`
  - L897: `DirBrowseQueryTest.test_dir_browse_single_char_path_not_truncated(self)`
  - L904: `DirBrowseQueryTest.test_ui_state_roundtrip(self)`
  - L919: `ConcurrencyTest.test_concurrent_send_queues(self)`
  - L950: `ConcurrencyTest.test_stop_endpoint_shape(self)`
  - L958: `ConcurrencyTest.test_stop_cancels_a_running_turn(self)`
  - L986: `WriteGateOverWebTest._gate(self)`
  - L991: `WriteGateOverWebTest.test_unconfirmed_commit_rejected_then_review_unlocks(self)`
  - L1027: `WriteGateOverWebTest.test_confirm_is_session_scoped(self)`

### A.546 `tests/test_web_ui_config.py`

- 类型：Python
- 行数：281
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：web-ui-config.ini：对话区工具条目与步骤面板的展示开关。
- 导入：`__future__`, `tempfile`, `unittest`, `pathlib`, `agent.shell.web.ui_bundle`, `agent.shell.web.web_ui_config`
- 顶层符号：
  - L15: `class WebUiConfigTest(unittest.TestCase)`
  - L68: `class ToolDetailLayoutTest(unittest.TestCase)`
  - L101: `class ImageLightboxDefaultModeTest(unittest.TestCase)`
  - L155: `class ToolShotPreviewClickTest(unittest.TestCase)`
  - L181: `class WaitTitleFormatTest(unittest.TestCase)`
  - L244: `class CompactionUiContractTest(unittest.TestCase)`
- 类成员：
  - L16: `WebUiConfigTest.test_missing_file_defaults_items_on_steps_off(self)`
  - L21: `WebUiConfigTest.test_only_digit_one_turns_a_flag_on(self)`
  - L34: `WebUiConfigTest.test_blank_value_keeps_the_default(self)`
  - L47: `WebUiConfigTest.test_classic_page_wires_the_placeholder(self)`
  - L76: `ToolDetailLayoutTest.setUp(self)`
  - L81: `ToolDetailLayoutTest.test_desktop_views_do_not_mount_raw_panels(self)`
  - L92: `ToolDetailLayoutTest.test_desktop_shot_reuses_the_read_image_meta_block(self)`
  - L108: `ImageLightboxDefaultModeTest.setUp(self)`
  - L116: `ImageLightboxDefaultModeTest.test_default_mode_is_pixel_not_fit(self)`
  - L122: `ImageLightboxDefaultModeTest.test_pixel_mode_centers_both_axes(self)`
  - L130: `ImageLightboxDefaultModeTest.test_stage_scroll_is_centered_not_left_top(self)`
  - L137: `ImageLightboxDefaultModeTest.test_css_does_not_pin_pixel_mode_to_a_corner(self)`
  - L143: `ImageLightboxDefaultModeTest.test_pixel_padding_is_small_enough_to_still_center(self)`
  - L158: `ToolShotPreviewClickTest.setUp(self)`
  - L163: `ToolShotPreviewClickTest.test_both_image_views_are_clickable(self)`
  - L167: `ToolShotPreviewClickTest.test_click_delegates_to_the_shared_lightbox(self)`
  - L173: `ToolShotPreviewClickTest.test_missing_aia_degrades_without_breaking_the_card(self)`
  - L184: `WaitTitleFormatTest.setUp(self)`
  - L188: `WaitTitleFormatTest.test_short_durations_keep_one_decimal_of_seconds(self)`
  - L195: `WaitTitleFormatTest.test_wait_title_prints_the_waited_time(self)`
  - L203: `WaitTitleFormatTest.test_countdown_uses_the_timeout_as_its_duration(self)`
  - L209: `WaitTitleFormatTest.test_countdown_says_timeout_once_the_deadline_passes(self)`
  - L218: `WaitTitleFormatTest.test_ticker_keeps_counting_overtime_until_the_result_arrives(self)`
  - L228: `WaitTitleFormatTest.test_nothing_is_reported_from_the_server_while_waiting(self)`
  - L237: `WaitTitleFormatTest.test_long_durations_are_written_in_units(self)`
  - L247: `CompactionUiContractTest.setUp(self)`
  - L254: `CompactionUiContractTest.test_module_is_bundled_and_uses_tool_shell(self)`
  - L265: `CompactionUiContractTest.test_compaction_pane_can_show_the_full_summary(self)`
  - L270: `CompactionUiContractTest.test_card_contract_has_count_tokens_and_clean_summary(self)`

### A.547 `tests/test_write_gate.py`

- 类型：Python
- 行数：287
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：写盘门控桥接测试：四步写盘协议 + 门控在注册制管道下不丢失。
- 导入：`__future__`, `sys`, `tempfile`, `unittest`, `pathlib`, `unittest`, `agent.app`, `agent.core.ports`, `agent.core.tool_call`
- 顶层符号：
  - L19: `class WriteGateTest(unittest.TestCase)`
- 类成员：
  - L22: `WriteGateTest.setUp(self)`
  - L38: `WriteGateTest._call(self, name, arguments)`
  - L44: `WriteGateTest._preview(self, path, content)`
  - L47: `WriteGateTest._commit(self, confirm_id)`
  - L50: `WriteGateTest._ready(self, path, content)`
  - L59: `WriteGateTest._norm(self, path)`
  - L64: `WriteGateTest.test_web_fetch_out_file_goes_through_preview(self)`
  - L90: `WriteGateTest.test_preview_does_not_write(self)`
  - L100: `WriteGateTest.test_full_four_steps(self)`
  - L112: `WriteGateTest.test_commit_consumes_id_once(self)`
  - L123: `WriteGateTest.test_commit_without_preview_rejected(self)`
  - L132: `WriteGateTest.test_commit_without_confirm_rejected(self)`
  - L148: `WriteGateTest.test_already_reviewed_previews_commit_together(self)`
  - L164: `WriteGateTest.test_consecutive_reviews_then_consecutive_commits(self)`
  - L189: `WriteGateTest.test_cross_file_review_gate(self)`
  - L202: `WriteGateTest.test_reread_required_before_second_edit(self)`
  - L219: `WriteGateTest.test_diagnose_red_and_recovery(self)`
  - L234: `WriteGateTest.test_red_light_limits_scope(self)`
  - L248: `WriteGateTest.test_write_missing_path_rejected(self)`
  - L254: `WriteGateTest.test_write_missing_content_rejected(self)`
  - L260: `WriteGateTest.test_commit_missing_id_rejected(self)`
  - L266: `WriteGateTest.test_commit_creates_parent_dirs(self)`
  - L274: `WriteGateTest.test_large_overwrite_flags_red(self)`

### A.548 `tests/test_write_path_keys_lifecycle.py`

- 类型：Python
- 行数：104
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：write_path_keys：只认工具声明 + 注册表查找；卸工具后解析不到路径。
- 导入：`__future__`, `sys`, `tempfile`, `unittest`, `pathlib`, `agent.capabilities.contributions`, `agent.capabilities.plugins`, `agent.capabilities.registry`, `agent.mechanisms.context`, `agent.mechanisms.executors`, `agent.mechanisms.quality`
- 顶层符号：
  - L21: `class _KeyedTool(ToolPlugin)`
  - L32: `class WritePathKeysLifecycleTest(unittest.TestCase)`
- 类成员：
  - L28: `_KeyedTool.execute(self, arguments)`
  - L33: `WritePathKeysLifecycleTest.test_resolve_uses_declared_keys_not_default_path(self)`
  - L39: `WritePathKeysLifecycleTest.test_gate_lookup_tracks_registry(self)`
  - L58: `WritePathKeysLifecycleTest.test_plugin_context_rollback_drops_tool_from_registry(self)`
  - L76: `WritePathKeysLifecycleTest.test_drop_plugin_removes_skills_from_registry(self)`

### A.549 `tests/test_write_path_tools.py`

- 类型：Python
- 行数：624
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：写路径工具测试：replace_in_file / apply_patch / read_write / delete_file / file_ops / file_undo。
- 导入：`__future__`, `sys`, `tempfile`, `unittest`, `pathlib`, `agent.app`, `agent.core.ports`, `agent.core.tool_call`, `agent.mechanisms.file_safety`
- 顶层符号：
  - L22: `def _patch(old, new, header_old, header_new)`
  - L36: `class WritePathToolsTest(unittest.TestCase)`
- 类成员：
  - L39: `WritePathToolsTest.setUp(self)`
  - L58: `WritePathToolsTest._call(self, name, arguments)`
  - L63: `WritePathToolsTest._ready(self, name, arguments)`
  - L71: `WritePathToolsTest._commit(self, cid)`
  - L74: `WritePathToolsTest._norm(self, path)`
  - L77: `WritePathToolsTest._write_file(self, f, content)`
  - L81: `WritePathToolsTest._backup_meta(self, f, index)`
  - L94: `WritePathToolsTest.test_backup_records_what_the_write_changed(self)`
  - L110: `WritePathToolsTest.test_backup_mode_reflects_the_replace_mode(self)`
  - L119: `WritePathToolsTest.test_backup_of_a_patch_records_the_patch_diff(self)`
  - L131: `WritePathToolsTest.test_undo_backup_records_what_the_rollback_undid(self)`
  - L158: `WritePathToolsTest.test_replace_preview_no_write(self)`
  - L167: `WritePathToolsTest.test_replace_commit_applies(self)`
  - L178: `WritePathToolsTest.test_replace_expected_mismatch_rejected(self)`
  - L188: `WritePathToolsTest.test_replace_old_text_not_found(self)`
  - L198: `WritePathToolsTest.test_replace_old_absent_never_already_applied(self)`
  - L219: `WritePathToolsTest.test_replace_same_text_already_applied(self)`
  - L233: `WritePathToolsTest.test_replace_line_mode(self)`
  - L241: `WritePathToolsTest.test_replace_stale_file_rejected(self)`
  - L253: `WritePathToolsTest.test_edits_applies_all_in_order(self)`
  - L269: `WritePathToolsTest.test_edits_are_sequential_not_parallel(self)`
  - L285: `WritePathToolsTest.test_edits_rejects_whole_batch_when_one_misses(self)`
  - L303: `WritePathToolsTest.test_edits_rejects_mixing_with_literal_or_line_params(self)`
  - L315: `WritePathToolsTest.test_edits_empty_list_rejected(self)`
  - L323: `WritePathToolsTest.test_edits_rejects_top_level_replace_all(self)`
  - L343: `WritePathToolsTest.test_patch_preview_stats_no_write(self)`
  - L352: `WritePathToolsTest.test_patch_commit_applies(self)`
  - L360: `WritePathToolsTest.test_patch_context_mismatch_rejected(self)`
  - L367: `WritePathToolsTest.test_patch_outside_root_rejected(self)`
  - L379: `WritePathToolsTest.test_patch_missing_target_rejected(self)`
  - L384: `WritePathToolsTest.test_patch_second_needs_review(self)`
  - L403: `WritePathToolsTest.test_read_write_slice_and_backup(self)`
  - L426: `WritePathToolsTest.test_delete_file_to_recycle(self)`
  - L441: `WritePathToolsTest.test_delete_file_dir_rejected(self)`
  - L448: `WritePathToolsTest.test_file_ops_copy_and_overwrite_refused(self)`
  - L489: `WritePathToolsTest.test_delete_file_missing_is_already_absent(self)`
  - L501: `WritePathToolsTest.test_file_ops_source_missing_is_not_already_applied(self)`
  - L535: `WritePathToolsTest.test_write_file_same_content_already_applied(self)`
  - L544: `WritePathToolsTest.test_write_file_trailing_newline_only_shows_diff(self)`
  - L566: `WritePathToolsTest.test_file_undo_restore_and_list(self)`
  - L584: `WritePathToolsTest.test_file_undo_requires_path(self)`
  - L591: `WritePathToolsTest.test_cross_file_review_block(self)`
  - L606: `WritePathToolsTest.test_reread_block_before_second_write(self)`

### A.550 `tests/testkit.py`

- 类型：Python
- 行数：47
- 所属主模块：`tests`
- 文件角色：test
- 文件说明：测试共用的小工具。
- 导入：`__future__`, `shutil`, `tempfile`, `pathlib`, `typing`, `unittest`
- 顶层符号：
  - L15: `def local_auth(app)`
  - L31: `def no_plugins(case)`

