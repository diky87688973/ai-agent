# 插件系统路径注册设计（前端 + 后端）
> 全路径替换契约见 [plugin-system-arbitrary-replacement.zh.md](plugin-system-arbitrary-replacement.zh.md)。任何已暴露路径都允许被替换。


## 1. 结论

路径命名空间可行。前端和后端都只用路径注册，注册路径同时决定插槽和可扩展范围。必须满足：

```text
一个区域只有一个路径
一个路径只有一个 path owner；实现 owner 可以替换
父路径负责容器，子路径负责内容
注册时确定控件类型
插件不直接操作宿主 DOM
宿主只渲染，不理解插件业务
```

统一使用短路径：

```text
web-ui/nav
```

## 2. 路径规则

```text
web-ui
web-ui/<region>
web-ui/<region>/<slot>
web-ui/<region>/<slot>/<id>
```

约束：

```text
小写字母、数字、下划线、短横线
禁止空格、点、反斜杠、..
父路径必须已注册
路径不能重复
owner 必须与注册插件一致
kind 必须在注册时确定
卸载插件自动删除其全部路径
```

### 2.1 插口协议

路径不是“随便写一个就能挂”。父路径必须声明插口协议：

```text
path_pattern
children      none / fixed / keyed / extension
allowed_kinds
allowed_owner
order
dispose
```

示例：

```text
web-ui/nav              children=fixed   只允许 buttons
web-ui/nav/buttons      children=keyed   只允许一个 id 段
web-ui/input/textarea   children=none    不允许任何子路径
web-ui/chat/messages    children=fixed   只允许 user_msg / ai_msg / tools
web-ui/right-panel      children=keyed   只允许一个 panel id 段
settings/<panel>        children=keyed   只允许一个 item id 段
backend/tools/<tool>    children=fixed   只允许 executor / post-write
backend/http/routes     children=keyed   只允许一个 route id 段
```

只有父路径协议声明 `children=extension` 时，才允许插件注册自定义子路径：

```text
web-ui/<region>/extensions/<plugin>/<id>
```

未声明 `extension` 的区域，不允许注册自定义路径。

路径决定插槽，插槽决定允许的扩展：

```text
父路径                     允许的子项                      不允许
web-ui/nav                 buttons/*                       任意 HTML
web-ui/input/textarea      无                              子路径
web-ui/right-panel         <panel_id>                      替换父容器
web-ui/chat/messages       user_msg / ai_msg / tools       替换消息容器
settings/<panel>           <item>                          子面板
backend/tools/<tool>       executor / post-write           替换工具注册表
backend/http/routes        route_id                        宿主路由
backend/kernel/providers   port/provider_id                内核启动
```

## 3. 基础结构

### 3.1 根

```text
web-ui
```

归属：WEB-UI 基础插件。

职责：

```text
页面结构
区域容器
统一事件冒泡入口
基础布局
主题变量
```

根不开放任意 HTML 注册。

### 3.2 导航区

```text
web-ui/nav
```

归属：WEB-UI 基础插件。

按钮：

```text
web-ui/nav/buttons/update       自动更新插件       [版本更新]
web-ui/nav/buttons/style        风格插件           [黑白切换]
web-ui/nav/buttons/settings     基础设置插件       [设置]
```

按钮 props：

```text
icon
label
title
order
visible
action
```

## 4. 对话区

### 4.1 容器

```text
web-ui/chat
```

归属：WEB-UI 基础插件。

职责：

```text
消息列表
滚动
流式更新
空状态
错误状态
```

### 4.2 消息区

```text
web-ui/chat/messages              WEB-UI 基础插件     消息区容器
web-ui/chat/messages/user_msg     WEB-UI 基础插件     用户消息气泡
web-ui/chat/messages/ai_msg       WEB-UI 基础插件     AI 正文气泡
web-ui/chat/messages/tools        WEB-UI 基础插件     基础工具壳
web-ui/chat/messages/tools/<工具名> WEB-UI 基础插件   具体工具壳
```

规则：

```text
所有消息以卡片或气泡呈现
工具名必须是稳定工具标识，不含 / 和 ..
未注册的工具壳回退到基础工具壳
消息内容由 WEB-UI 基础插件统一转义和渲染
```

### 4.3 输入区

```text
web-ui/input
```

归属：WEB-UI 基础插件。

输入框：

```text
web-ui/input/textarea
```

归属：WEB-UI 基础插件。  
不开放扩展注册；输入、粘贴、快捷键、发送前处理由 WEB-UI 基础插件负责。

左侧按钮：

```text
web-ui/input/buttons/image_btn        WEB-UI 基础插件      [图片选择]
web-ui/input/buttons/mode_btn         WEB-UI 基础插件      [Auto+]
web-ui/input/buttons/thinking_btn     WEB-UI 基础插件      [思考深度]
web-ui/input/buttons/model_switch_btn 多模型插件            [模型选择]
web-ui/input/buttons/kb_btn           知识库插件            [知识库]
web-ui/input/buttons/visual_btn       视觉操作 2.0 插件      [眼睛]
```

右侧按钮：

```text
web-ui/input/right-buttons/goal_btn   WEB-UI 基础插件      [目标]
web-ui/input/right-buttons/send_btn   WEB-UI 基础插件      [发送]
web-ui/input/right-buttons/stop_btn   WEB-UI 基础插件      [停止]
```

按钮规则：

```text
stop_btn 显示“停止”
send_btn 显示“发送”
左右按钮分别使用 buttons / right-buttons
按钮只发动作，不持有输入框 DOM
```

## 5. 左侧栏

```text
web-ui/left-panel
```

归属：WEB-UI 基础插件。

职责：

```text
会话列表
新开会话
分栏拖拽
收起/展开
```

### 5.1 会话

```text
web-ui/left-panel/sessions          WEB-UI 基础插件
web-ui/left-panel/sessions/new      WEB-UI 基础插件
web-ui/left-panel/sessions/list     WEB-UI 基础插件
```

### 5.2 上下文用量

```text
web-ui/left-panel/context_usage     WEB-UI 基础插件
```

基础段：

| 路径 | 标题 | 颜色 | 归属 |
|---|---|---|---|
| `.../context_usage/system` | 系统提示词 | amber | WEB-UI |
| `.../context_usage/summary` | 记忆摘要 | red | WEB-UI |
| `.../context_usage/full_recent` | 近期记忆 | teal | WEB-UI |
| `.../context_usage/mode` | 模式 | #f3ce0d | WEB-UI |
| `.../context_usage/remaining` | 剩余容量 | 轨道灰 | WEB-UI |

插件段：

```text
.../context_usage/skills    Skills 插件
.../context_usage/kb        知识库插件
.../context_usage/rules     规则插件
```

段注册 props：

```text
title
color
used
capacity
order
```

规则：

```text
基础段由 WEB-UI 插件注册
插件段只提供自己的用量展示
用量面板负责总布局和悬停明细
```

## 6. 右侧栏

```text
web-ui/right-panel
```

归属：WEB-UI 基础插件。

职责：

```text
标签栏
打开/关闭
分栏拖拽
面板容器
面板私域边界
```

面板：

```text
web-ui/right-panel/steps        WEB-UI 基础插件      [步骤面板]
web-ui/right-panel/open_file   WEB-UI 基础插件      [打开文件]
web-ui/right-panel/kb          知识库插件           [打开知识库]
```

归属说明：

```text
steps 面板属于右侧栏，由 WEB-UI 基础插件注册和渲染。
“右侧栏展示步骤”开关属于 settings/interface，由基础设置插件注册。
面板路径和开关设置项不是同一个资产，不应强行归到同一插件。
```

面板内部：

```text
标题、标签、关闭、排序、拖拽由父路径管理
面板内容属于插件私域
插件只操作自己的面板容器
插件不得操作标签栏和宿主动作
```

## 7. 运行时控件区

```text
web-ui/runtime
```

归属：WEB-UI 基础插件。

左侧运行时：

```text
web-ui/runtime/left-panel                WEB-UI 基础插件
web-ui/runtime/left-panel/ai_speak       AI 说话插件       [AI 说话]
web-ui/runtime/left-panel/inbox          WEB-UI 基础插件   [消息队列]
```

右侧运行时：

```text
web-ui/runtime/right-panel               WEB-UI 基础插件
web-ui/runtime/right-panel/background_task WEB-UI 基础插件 [后台任务]
web-ui/runtime/right-panel/subagent      WEB-UI 基础插件   [子智能体]
```

说明：

```text
运行时区与左侧栏/右侧栏是不同区域
运行时控件按状态出现和消失
background_task 在右侧运行时，不在输入区
subagent 在右侧运行时，不在输入区
```

## 8. 设置页

### 8.1 页面容器

```text
web-ui/settings
```

归属：WEB-UI 基础插件。

职责：

```text
设置页容器
通用控件渲染
保存入口
错误展示
```

### 8.2 设置面板和条目

设置注册使用一个路径：

```text
settings/<panel>                 设置面板
settings/<panel>/<item>          设置条目
```

设置面板归属：

```text
settings                        宿主
settings/agent                  基础设置插件
settings/context                基础设置插件
settings/interface              基础设置插件
settings/plugin                 基础设置插件
settings/model                  多模型插件
```

设置条目归属：

```text
settings/agent/reasoning_effort          基础设置插件
settings/agent/max_passes                基础设置插件
settings/agent/backup_retention_days     基础设置插件
settings/context/*                       基础设置插件
settings/interface/*                     基础设置插件
settings/interface/theme_style           主题风格插件
settings/model/*                         多模型插件
```

### 8.3 设置路径与回调

```text
settings/<panel>/<item> 同时作为注册路径、配置身份和回调路由
web-ui/settings 只作为设置页容器
```

设置路径直接决定控件位置和保存回调，不维护额外映射表。

## 9. 注册协议

```json
{
  "path": "web-ui/nav/buttons/update",
  "kind": "button",
  "owner": "auto_update",
  "order": 10,
  "props": {"icon": "download", "label": "版本更新"},
  "action": "auto_update.check"
}
```

字段：

```text
path
kind
owner
order
props
action
visible
permission
```

禁止：

```text
html
selector
script
onclick 字符串
直接查询宿主 DOM
```

## 10. 后端契约

```text
UiRegistry
  paths
  regions
  owners
  kinds
  actions
```

能力：

```text
add_ui(path, kind, owner, spec)
remove_ui(path)
catalog()
dispatch(path, action, payload)
```

校验：

```text
父路径存在
路径唯一
owner 匹配
kind 匹配
action 能路由到 owner
插件卸载清理全部子路径
```

插件系统负责注册、保存、分发、广播；宿主只渲染通用控件。

## 11. 前端契约

区域节点：

```html
data-ui-region="web-ui/nav"
data-ui-slot="buttons"
```

事件：

```text
区域根或 document 只绑一次
closest("[data-ui-path]")
读取 data-ui-action
交给 UiDispatcher
```

禁止：

```text
每个按钮 addEventListener
每个列表项 onclick
插件直接改宿主区域 HTML
```

插件私域：

```text
只允许在宿主分配的面板容器内渲染自己的内容
允许容器内自己的事件
禁止操作标签栏、拖拽条、关闭按钮
```

## 12. 后端路径注册

后端和前端使用同一套规则：

```text
path 必填
kind 必填
owner 由注册时的插件身份决定
path 决定插槽和允许的扩展
未注册父路径不能挂子项
父容器归宿主或对应基础插件
```

后端根：

```text
backend
```

### 12.1 工具与管道

| 注册路径 | 扩展能力 | 必填参数 |
|---|---|---|
| `backend/tools/<tool_name>` | 注册工具 | tool 对象、名称、schema、权限 |
| `backend/tools/<tool_name>/executor` | 注册写工具执行器 | 工具名、执行回调 |
| `backend/tools/<tool_name>/post-write` | 写后重读/校验挂点 | 工具名、回调 |
| `backend/tools/subagents/visibility/<plugin>` | 子智能体工具可见性 | 工具名列表 |
| `backend/tools/pipeline/pre-gates/<plugin>/<gate_id>` | 工具前置门控 | 回调、order |
| `backend/tools/pipeline/post-observers/<plugin>/<observer_id>` | 工具后置观察 | 回调 |

约束：

```text
工具名必须是稳定标识
执行器只能绑定已注册工具
门控只能增加检查，不能删除内核保证
```

### 12.2 上下文

| 注册路径 | 扩展能力 | 必填参数 |
|---|---|---|
| `backend/context/sources/<plugin>/<source_id>` | 上下文注入源 | 回调、SourceMeta |
| `backend/context/assembly-hooks/<plugin>/<hook_id>` | 完整上下文拼装钩子 | 回调 |
| `backend/context/usage-segments/<plugin>/<segment_id>` | 上下文用量段数据 | 标题、颜色、用量回调 |

### 12.3 提示词

| 注册路径 | 扩展能力 | 必填参数 |
|---|---|---|
| `backend/prompt/sections/<section>/<plugin>` | 系统提示词章节 | 章节名、内容回调 |
| `backend/prompt/mode-tails/<plugin>` | 请求尾部片段 | 内容回调、子智能体可见性 |

### 12.4 事件与 HTTP

| 注册路径 | 扩展能力 | 必填参数 |
|---|---|---|
| `backend/events/subscriptions/<event_type>/<plugin>` | 订阅事件 | event_type、handler |
| `backend/events/publish/<plugin>` | 发布插件事件 | 事件名、payload |
| `backend/http/routes/<route_id>` | 插件 HTTP 端点 | method、path、handler、scope |

HTTP 约束：

```text
实际地址固定在 /api/plugin/<plugin>/
route_id 只是注册身份
method 和 path 作为参数校验
宿主路由也是路径绑定，允许显式 replace 并回退
```

### 12.5 模型

| 注册路径 | 扩展能力 | 必填参数 |
|---|---|---|
| `backend/models/catalog/<plugin>` | 模型目录来源 | 条目或重读回调 |
| `backend/models/providers/<provider_id>` | 模型网关 provider | factory、能力声明 |
| `backend/models/routing/<plugin>` | 模型路由策略 | 选择回调 |

模型目录来源名固定为插件名，避免多个目录抢同一个来源。

### 12.6 设置

| 注册路径 | 扩展能力 | 必填参数 |
|---|---|---|
| `settings/<panel>` | 设置面板 | 标题、order |
| `settings/<panel>/<item>` | 设置条目 | kind、label、save/load、options |

设置路径同时承担 UI 容器下的条目路由，没有第二套 UI 路径。

### 12.7 UI 动作与面板

| 注册路径 | 扩展能力 | 必填参数 |
|---|---|---|
| `web-ui/nav/buttons/<id>` | 导航按钮 | icon、label、action |
| `web-ui/input/buttons/<id>` | 输入区左侧按钮 | icon、label、action |
| `web-ui/input/right-buttons/<id>` | 输入区右侧按钮 | label、action |
| `web-ui/chat/messages/tools/<tool_name>` | 工具消息壳 | renderer |
| `web-ui/right-panel/<panel_id>` | 右栏面板 | title、open action、私域挂载 |
| `web-ui/runtime/left-panel/<id>` | 运行时左栏控件 | renderer、visible |
| `web-ui/runtime/right-panel/<id>` | 运行时右栏控件 | renderer、visible |

### 12.8 运行时对象

| 注册路径 | 扩展能力 | 必填参数 |
|---|---|---|
| `backend/runtime/<plugin>` | 插件运行时对象 | runtime 对象 |

运行时对象只供插件系统/宿主按插件身份取用，不是公共全局变量。

### 12.9 内核 Provider

以下路径是替换/增强内核能力的入口：

| 注册路径 | 替换的端口 | 必填参数 |
|---|---|---|
| `backend/kernel/providers/model.gateway/<provider_id>` | 模型网关 | factory、协议版本、priority |
| `backend/kernel/providers/session.store/<provider_id>` | 会话存储 | factory、协议版本 |
| `backend/kernel/providers/tool.executor/<provider_id>` | 工具执行器 | factory、协议版本 |
| `backend/kernel/providers/context.builder/<provider_id>` | 上下文构建 | factory、协议版本 |
| `backend/kernel/providers/http.provider/<provider_id>` | HTTP 服务适配 | factory、协议版本 |
| `backend/kernel/providers/ui.renderer/<provider_id>` | UI 渲染器 | factory、协议版本 |

约束：

```text
所有暴露路径都有契约，按契约替换
内核启动、鉴权、持久化等路径同样允许 replace，需事务回滚
同端口按 priority 选择
失败回退默认 provider
冲突必须显式报告
```

## 13. 前端注册与后端注册

### 13.1 后端注册

后端注册负责：

```text
声明路径存在
声明 kind
声明允许的子路径
声明 handler / save / load
声明排序、权限、生命周期
```

后端注册完成后，路径才进入 catalog。

### 13.2 前端注册

前端注册分两类。

第一类：绑定已声明路径。

```text
后端已注册 web-ui/nav/buttons/update
前端只能为该路径绑定渲染器和动作
不能改路径、不能新增兄弟路径
```

第二类：在协议允许的 extension 子槽内新增路径。

```text
web-ui/<region>/extensions/<plugin>/<id>
```

第二类必须同时满足：

```text
父区域协议 children=extension
manifest 声明 ui_extensions
owner 等于 <plugin>
id 只有一段
向 /api/ui/register 登记通过
```

示例：

```text
web-ui/chat/extensions/ai_speak/bar
web-ui/input/extensions/visual_operator_2/eye
```

前端注册参数：

```text
path
kind
renderer
action schema
order
private mount
```

约束：

```text
可以注册协议明确开放的 extension 子槽，也可以显式 replace 已有宿主路径
宿主区域或宿主条目路径可替换；必须声明 replace、优先级和回退
父容器默认保留子绑定；replace_subtree 才整体替换
不能嵌套未声明层级（声明过的路径可替换）
不能操作宿主 DOM
动作可以是前端本地动作，也可以调用后端已注册动作
```

拒绝示例：

```text
aaaa/bbbb/cccc
web-ui/foo
web-ui/chat/aaaa
web-ui/nav/buttons/extra/child
backend/tools/read_file/custom
```

这些路径没有父插口、kind 不匹配或父协议不允许子路径。

后端登记：

```text
前端新增路径通过 /api/ui/register 登记
后端按 manifest 的 ui_extensions 白名单校验
登记成功才进入 catalog
插件卸载或页面销毁时撤销
```

前端新增路径不能绕过插口协议和 manifest 白名单；没有 extension 插口只能绑定已声明路径。

### 13.3 注册顺序

```text
后端注册路径
→ catalog 下发
→ 前端绑定渲染器
→ 前端可在协议允许的 extension 子槽登记自己的路径
→ 宿主挂载
→ 动作分发
→ 卸载清理
```

路径是前端、后端、宿主、插件系统之间的唯一共同标识。
