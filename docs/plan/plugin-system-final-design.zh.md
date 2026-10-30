# 插件系统最终设计
> 全路径替换契约见 [plugin-system-arbitrary-replacement.zh.md](plugin-system-arbitrary-replacement.zh.md)。任何已暴露路径都允许被替换。


## 1. 结论

插件系统是编排层，位于宿主和内核之间。

```text
Host
  ↕ 通用宿主契约
Plugin System
  ↕ 通用内核端口
Kernel
```

宿主和内核都不识别插件名。插件通过路径注册扩展点；路径决定插槽、类型、owner、生命周期和允许的子扩展。

前端和后端使用同一套注册原则：

```text
path 必填
kind 必填
owner 由插件身份确定
父插口协议决定是否允许注册
未注册路径不渲染、不保存、不分发
```

## 2. 分层职责

### 2.1 宿主

```text
HTTP 入口、鉴权、进程生命周期
页面壳和基础区域
通用 UI 渲染器
通用设置页容器
静态资源发送
动作请求转发
```

宿主不解析插件业务字段，不按插件名写分支。

### 2.2 插件系统

```text
清单校验
依赖解析
路径注册表
插口协议
UI 注册表
后端能力注册表
设置注册表
HTTP 路由分发
动作分发
事件广播
生命周期与回滚
诊断
```

### 2.3 内核

```text
工具注册表与工具管道
上下文注入
提示词
模型目录
会话存储
事件总线
执行器
门控
Provider 端口
```

内核只认端口和契约，不认插件。

### 2.4 插件清单

```json
{
  "id": "theme_style",
  "version": "1.0.0",
  "api_version": "1",
  "entry": "plugin.py",
  "ui_extensions": ["web-ui/nav/buttons/style"],
  "backend_paths": ["settings/interface/theme_style"],
  "permissions": ["ui.register", "settings.register"]
}
```

约束：

```text
api_version 不匹配拒绝加载
ui_extensions 是前端 extension 白名单
backend_paths 是后端路径白名单
permissions 控制可注册的扩展类型
未声明的路径拒绝注册
```

## 3. 路径命名空间

```text
web-ui       前端 UI 区域
backend      后端运行时能力
settings     设置面板与设置条目
```

路径规则：

```text
只允许小写字母、数字、下划线、短横线
参数段只能是单段
禁止空格、点、反斜杠、..
父路径必须已注册
同一路径只能注册一次
owner 必须与注册插件一致
卸载插件删除其全部路径
```

## 4. 插口协议

每个父路径注册时声明协议：

```json
{
  "path": "web-ui/nav/buttons",
  "kind": "container",
  "children": "keyed",
  "allowed_kinds": ["button"],
  "allowed_owner": "*",
  "max_children": 32,
  "conflict": "reject"
}
```

`children` 取值：

```text
none       不允许子路径
fixed      只允许协议列出的固定名称
keyed      只允许一个 id 参数段
extension  允许 web-ui/<region>/extensions/<plugin>/<id>
```

注册前必须完成：

```text
解析父路径
→ 读取父插口协议
→ 校验 kind
→ 校验 owner
→ 校验子路径模式
→ 校验参数格式
→ 写入注册表
```

不符合任一条件直接拒绝。

非法路径示例：

```text
aaaa/bbbb/cccc
web-ui/foo
web-ui/chat/aaaa
web-ui/nav/buttons/a/b
backend/tools/read_file/custom
```

## 5. 前端 UI 路径

### 5.1 根与区域

```text
web-ui                            WEB-UI 基础插件
web-ui/nav                        WEB-UI 基础插件
web-ui/chat                       WEB-UI 基础插件
web-ui/input                      WEB-UI 基础插件
web-ui/left-panel                 WEB-UI 基础插件
web-ui/right-panel                WEB-UI 基础插件
web-ui/runtime                    WEB-UI 基础插件
web-ui/settings                   WEB-UI 基础插件
```

根和区域容器由 WEB-UI 基础插件提供默认实现；任何已暴露节点都可以被插件 replace、wrap 或 extend，默认实现保留为回退。

### 5.2 导航

```text
web-ui/nav/buttons/update         自动更新插件
web-ui/nav/buttons/style          风格插件
web-ui/nav/buttons/settings       基础设置插件
```

### 5.3 对话

```text
web-ui/chat/messages                         WEB-UI 基础插件
web-ui/chat/messages/user_msg                WEB-UI 基础插件
web-ui/chat/messages/ai_msg                  WEB-UI 基础插件
web-ui/chat/messages/tools                   WEB-UI 基础插件
web-ui/chat/messages/tools/<tool_name>       WEB-UI 基础插件
```

工具消息壳的路径 owner 是 WEB-UI 基础插件；工具自己的数据由工具提供。工具专用渲染器只能在协议声明 `renderer=plugin` 时由工具插件提供，路径 owner 不变。

### 5.4 输入

```text
web-ui/input/textarea                        WEB-UI 基础插件，固定不可扩展
web-ui/input/buttons/image_btn               WEB-UI 基础插件
web-ui/input/buttons/mode_btn                WEB-UI 基础插件
web-ui/input/buttons/thinking_btn            WEB-UI 基础插件
web-ui/input/buttons/model_switch_btn        多模型插件
web-ui/input/buttons/kb_btn                  知识库插件
web-ui/input/buttons/visual_btn              视觉操作 2.0 插件
web-ui/input/right-buttons/goal_btn          WEB-UI 基础插件
web-ui/input/right-buttons/send_btn          WEB-UI 基础插件
web-ui/input/right-buttons/stop_btn          WEB-UI 基础插件
```

### 5.5 左侧栏

```text
web-ui/left-panel/sessions                   WEB-UI 基础插件
web-ui/left-panel/sessions/new               WEB-UI 基础插件
web-ui/left-panel/sessions/list              WEB-UI 基础插件
web-ui/left-panel/context_usage              WEB-UI 基础插件
```

基础段：

```text
context_usage/system         系统提示词    amber
context_usage/summary        记忆摘要      red
context_usage/full_recent    近期记忆      teal
context_usage/mode           模式          #f3ce0d
context_usage/remaining      剩余容量      轨道灰
```

插件段：

```text
context_usage/skills         Skills 插件
context_usage/kb             知识库插件
context_usage/rules          规则插件
```

段协议：

```json
{
  "path": "web-ui/left-panel/context_usage/<segment>",
  "kind": "segment",
  "props": ["title", "color", "used", "capacity", "order"]
}
```

### 5.6 右侧栏

```text
web-ui/right-panel/steps        WEB-UI 基础插件
web-ui/right-panel/open_file    WEB-UI 基础插件
web-ui/right-panel/kb           知识库插件
```

`steps` 面板归 WEB-UI 基础插件；“右侧栏展示步骤”开关归基础设置插件。面板内容属于面板 owner 的私域。

### 5.7 运行时

```text
web-ui/runtime/left-panel                    WEB-UI 基础插件
web-ui/runtime/left-panel/ai_speak           AI 说话插件
web-ui/runtime/left-panel/inbox              WEB-UI 基础插件
web-ui/runtime/right-panel                   WEB-UI 基础插件
web-ui/runtime/right-panel/background_task   WEB-UI 基础插件
web-ui/runtime/right-panel/subagent          WEB-UI 基础插件
```

### 5.8 设置

```text
settings                        宿主
settings/agent                  基础设置插件
settings/context                基础设置插件
settings/interface              基础设置插件
settings/plugin                 基础设置插件
settings/model                  多模型插件
settings/<panel>/<item>          注册条目的插件
```

`web-ui/settings` 只是设置页容器。设置路径同时承担控件位置、配置身份和 load/save 回调路由，不使用第二套 UI 路径。

## 6. 前端注册契约

### 6.1 绑定已声明路径

```text
后端声明 web-ui/nav/buttons/update
前端绑定 renderer / action
不能改路径
不能新增兄弟路径
```

### 6.2 自定义扩展路径

只有父区域协议 `children=extension` 时允许：

```text
web-ui/<region>/extensions/<plugin>/<id>
```

扩展槽位：

| 区域 | extension |
|---|---|
| `web-ui/nav` | 禁止 |
| `web-ui/chat` | 允许 |
| `web-ui/input` | 允许 |
| `web-ui/left-panel` | 禁止 |
| `web-ui/right-panel` | 允许 |
| `web-ui/runtime/left-panel` | 允许 |
| `web-ui/runtime/right-panel` | 允许 |
| `web-ui/settings` | 禁止 |

未列出的区域一律按禁止处理。

必须满足：

```text
manifest 声明 ui_extensions
owner 等于 <plugin>
id 只有一段
通过 /api/ui/register 登记
```

前端注册项：

```json
{
  "path": "web-ui/chat/extensions/ai_speak/bar",
  "kind": "overlay",
  "renderer": "ai_speak.bar",
  "action": "ai_speak.toggle",
  "order": 20
}
```

禁止：

```text
注册宿主区域路径
替换父容器
嵌套未声明层级
操作宿主 DOM
使用任意 HTML/selector/script/onclick
```

注册项必须区分三个 owner：

```text
path_owner       路径和插槽所有者
renderer_owner   控件内容渲染者
action_owner     动作处理者
```

默认三者相同。插口协议允许分离时才可不同，例如工具消息壳由 WEB-UI 拥有路径，工具插件提供专用渲染器。

### 6.3 事件

区域根或 document 只绑一次事件：

```text
click / keydown
→ closest("[data-ui-path]")
→ 读取 data-ui-action
→ UiDispatcher
→ Plugin System
→ owner handler
```

动态列表和按钮禁止逐项绑定事件。

### 6.4 控件类型

注册时确定：

```text
button
panel
segment
message-card
tool-shell
settings-item
overlay
```

不同插口只接受协议声明的 kind。

控件 props：

| kind | 必填 props | 可选 props |
|---|---|---|
| `button` | `icon` 或 `label`、`action` | `title`、`disabled`、`order` |
| `panel` | `title` | `icon`、`order`、`open_action` |
| `segment` | `title`、`color`、`used`、`capacity` | `order` |
| `message-card` | `role`、`content` | `status`、`attachments` |
| `tool-shell` | `tool_name` | `status`、`args`、`result` |
| `settings-item` | `kind`、`label`、`save` | `default`、`options`、`load` |
| `overlay` | `renderer` | `order`、`visible` |

所有 props 在注册时校验；未声明字段拒绝。

## 7. 后端注册契约

后端路径根：

```text
backend
```

### 7.1 工具与管道

```text
backend/tools/<tool_name>
backend/tools/<tool_name>/executor
backend/tools/<tool_name>/post-write
backend/tools/subagents/visibility/<plugin>
backend/tools/pipeline/pre-gates/<plugin>/<gate_id>
backend/tools/pipeline/post-observers/<plugin>/<observer_id>
```

### 7.2 上下文与提示词

```text
backend/context/sources/<plugin>/<source_id>
backend/context/assembly-hooks/<plugin>/<hook_id>
backend/context/usage-segments/<plugin>/<segment_id>
backend/prompt/sections/<section>/<plugin>
backend/prompt/mode-tails/<plugin>
```

### 7.3 事件与 HTTP

```text
backend/events/subscriptions/<event_type>/<plugin>
backend/http/routes/<route_id>
```

事件发布是运行时动作，不是持久注册，不进入路径表。

### 7.4 模型

```text
backend/models/catalog/<plugin>
backend/models/providers/<provider_id>
backend/models/routing/<plugin>
```

### 7.5 运行时对象

```text
backend/runtime/<plugin>
```

只供插件系统和宿主按插件身份取用，不暴露为公共全局。

### 7.6 Provider

```text
backend/kernel/providers/model.gateway/<provider_id>
backend/kernel/providers/session.store/<provider_id>
backend/kernel/providers/tool.executor/<provider_id>
backend/kernel/providers/context.builder/<provider_id>
backend/kernel/providers/http.provider/<provider_id>
backend/kernel/providers/ui.renderer/<provider_id>
```

Provider 必须有：

```text
port
protocol_version
factory
priority
replaces
validate
```

约束：

```text
同 port 只能有一个 active provider
默认 provider 永久保留
新 provider 失败回退默认
冲突显式报错
内核启动、鉴权、持久化等节点只要暴露为路径就可替换；替换必须通过契约测试与事务回滚
```

## 8. 后端注册判定

```text
path 必填
kind 必填
owner 由插件身份决定
handler / callback 必填
protocol version 必填
priority 可选
```

回调签名：

```text
HTTP handler(request) -> (status, payload)
tool executor(args) -> result
context source(conversation_id) -> list[str]
prompt section(conversation_id) -> str
event handler(event) -> None
settings load() -> value
settings save(value) -> {ok, error}
provider factory(config) -> provider
```

返回值必须符合契约；异常必须转成插件加载/动作/保存错误，不得静默吞掉。

同一个路径重复注册：

```text
直接拒绝
未声明 replace 时拒绝重复；显式 replace 允许覆盖
不静默选择
```

插件注册失败：

```text
该插件已注册贡献全部回滚
不影响其他插件
错误进入插件加载报告
```

## 9. 设置契约

设置条目：

```json
{
  "path": "settings/interface/theme_style",
  "kind": "select",
  "label": "界面风格",
  "default": "dsh",
  "options": [],
  "save": "plugin callback",
  "load": "plugin callback"
}
```

保存：

```text
UI 收集变更
→ POST settings
→ Plugin System 按 path 找到 owner
→ 调用 save
→ 所有者保存并应用
→ 返回 ok/error
→ 汇总后广播
```

设置项回调属于注册插件，不属于宿主和内核。

保存事务：

```text
1. 全量 validate
2. 按 owner 分组
3. 逐 owner commit
4. 任一失败，对已提交 owner 执行 rollback
5. 返回逐项结果
6. 全部成功才广播
```

内置设置插件通过宿主设置端口读写，不直接 import shell：

```text
HostSettingsPort
  read(section, key)
  write(section, key, value)
  apply()
```

## 10. 生命周期

```text
discover
→ validate manifest
→ resolve dependencies
→ activate
→ register paths
→ catalog
→ render
→ ready
→ disable
→ remove owner paths
→ cleanup
→ reload
```

规则：

```text
激活失败回滚全部注册
卸载逆序撤销
UI 路径立即消失
后端路由立即失效
设置值保留在插件自己的存储
重新启用恢复
```

## 11. 资产归属

| 资产 | owner |
|---|---|
| 页面壳、区域容器、基础消息和输入 | WEB-UI 基础插件 |
| 设置页容器、面板、基础设置项 | 基础设置插件 |
| 模型目录、模型选择按钮、模型设置 | 多模型插件 |
| 风格选择、主题资源和黑白切换 | 风格插件 |
| 知识库按钮、右栏面板、用量段、上下文注入 | 知识库插件 |
| AI 说话运行时控件 | AI 说话插件 |
| 眼睛按钮、视觉上下文钩子 | 视觉操作 2.0 插件 |
| Skills 用量段、上下文注入 | Skills 插件 |
| Rules 用量段、上下文注入 | 规则插件 |
| 自动更新按钮 | 自动更新插件 |
| 步骤面板路径 | WEB-UI 基础插件 |
| 步骤显示开关 | 基础设置插件 |

路径 owner 和渲染器 owner 分开记录时，必须在注册项字段中显式声明，不能由宿主猜。

## 12. 宿主接口

```text
GET  /api/ui/catalog          获取区域、控件、插件面板
POST /api/ui/register         前端登记 extension 路径
POST /api/ui/action           分发控件动作
GET  /api/settings            获取设置面板和值
POST /api/settings            提交设置
GET  /api/plugins/status      插件及注册路径状态
```

Catalog 返回：

```json
{
  "ok": true,
  "version": "1",
  "regions": [],
  "items": [],
  "settings": []
}
```

注册请求：

```json
{
  "path": "web-ui/chat/extensions/ai_speak/bar",
  "kind": "overlay",
  "renderer": "ai_speak.bar",
  "action": "ai_speak.toggle",
  "order": 20
}
```

注册成功返回最新 catalog；失败返回：

```json
{
  "ok": false,
  "error": "path or slot rejected",
  "path": "web-ui/chat/extensions/ai_speak/bar"
}
```

动作请求：

```json
{
  "path": "web-ui/nav/buttons/update",
  "action": "auto_update.check",
  "payload": {},
  "request_id": "uuid"
}
```

动作响应：

```json
{
  "ok": true,
  "value": null,
  "error": "",
  "effects": []
}
```

动作约束：

```text
path 必须已注册
action 必须属于 action_owner
同一 request_id 不重复执行
失败只影响该动作
```

## 13. 架构复核结论

通过条件：

```text
所有扩展点都有路径
所有路径都有父插口协议
所有注册项都有 owner 和 kind
前端/后端注册使用同一路径身份
设置只有一套路径
路径卸载可追踪
宿主没有插件名分支
内核没有插件业务分支
```

已落实的设计约束：

```text
插口协议序列化和校验算法
动作请求/响应协议
前端自定义路径的登记与撤销
Provider 协议版本和冲突规则
UI 组件 props schema
manifest 的 ui_extensions / backend_paths 白名单
注册失败回滚和诊断
```

实现前必须补契约测试，不改变设计。

设计判定：

```text
路径命名空间方案成立
插口协议方案成立
前端注册必须受插口协议限制
后端路径注册必须统一走注册表
设置单路径方案成立
Provider 替换只能通过端口
```

## 14. 不做的事

```text
不允许插件直接修改宿主 DOM
不允许插件按路径外任意命名空间注册
不允许路径别名和重复路径
不允许宿主解释插件业务字段
不允许内核出现插件名分支
不允许用临时旁路替代注册表
```
