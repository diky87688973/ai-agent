# 插件系统迁移方案

## 1. 目标

把现有宿主硬编码 UI、插件贡献 API、设置入口，迁移为统一的路径注册系统。

迁移不改变：

```text
会话数据
用户配置
插件私有配置
现有 localStorage 键
现有插件业务行为
```

迁移只改变：

```text
注册方式
路径身份
宿主渲染方式
动作分发方式
生命周期清理
```

## 2. 迁移原则

```text
先建立路径协议，再迁移注册
先保留旧入口，再逐项替换
一个区域迁移完成后再删旧代码
注册失败必须回滚
不允许双路径长期并存
不允许最后统一大改
```

## 3. 基线

当前实际扩展点：

```text
agent-ui.html 中的导航、输入区、左右栏、运行时区
settings_panel.py 中的静态设置字段和保存逻辑
PluginContext 的 add_ui_item / add_ui_item / add_ui_item
PluginContext 的 register_tool / add_route / add_context_source
PluginContext 的 add_model_catalog / add_settings_panel / add_settings_item
各插件 boot script 直接操作宿主 DOM
```

迁移后统一为：

```text
web-ui/...        前端路径
backend/...       后端能力路径
settings/...      设置路径
```

## 4. 阶段总表

| 阶段 | 内容 | 完成后状态 |
|---|---|---|
| 0 | 基线冻结与路径协议 | 旧行为不变，路径校验可测试 |
| 1 | 注册表基础设施 | 前后端注册表、catalog、动作分发 |
| 2 | 宿主通用渲染器 | 区域节点和通用控件可挂载 |
| 3 | 插件清单与 API | 插件可声明路径和白名单 |
| 4 | 基础区域迁移 | 导航、输入、消息、左右栏、运行时 |
| 5 | 设置迁移 | 设置唯一路径，宿主静态字段移除 |
| 6 | 后端能力迁移 | 工具、上下文、提示词、事件、HTTP、模型 |
| 7 | 插件迁移 | 每个插件从 boot/DOM 改为路径注册 |
| 8 | 删除旧入口 | add_ui_item/action/boot 和宿主硬编码退场 |
| 9 | 验收 | 契约测试、区域截图、全量回归 |

## 5. 逐项改造点

### M01 路径语法与插口协议

- 目标：路径、参数、owner、kind、children 协议统一。
- 新增：
  - `agent/capabilities/plugin_paths.py`
- 内容：
  - 路径解析
  - 参数段校验
  - 插口协议模型
  - owner/kind 校验
  - 冲突拒绝
  - 路径树快照
- 验收：
  - `aaaa/bbbb/cccc` 拒绝
  - 未注册父路径拒绝
  - `children=none` 子路径拒绝
  - 重复路径拒绝
- 回滚：删除新模块，旧注册路径不变。

### M02 后端路径注册表

- 目标：所有后端扩展点按路径登记和撤销。
- 新增：
  - `agent/capabilities/backend_registry.py`
- 覆盖：
  - 工具、执行器、门控、观察器
  - 上下文源、拼装钩子
  - 提示词章节、请求尾部
  - 事件订阅、HTTP 路由
  - 模型目录、Provider
- 验收：
  - 路径和 handler 一一对应
  - 卸载后 handler 不可见
  - 冲突路径拒绝
- 回滚：注册表不参与旧调用，旧 API 继续工作。

### M03 UI 路径注册表

- 目标：前端区域和控件按路径登记。
- 新增：
  - `agent/capabilities/ui_registry.py`
- 内容：
  - 区域树
  - kind 白名单
  - props schema
  - 前端 extension 子槽
  - 区域 extension 声明表
  - catalog 输出
- 验收：
  - 区域路径可见
  - 子项只能挂协议允许的父路径
  - 前端 extension 仅允许 `children=extension`
  - 未声明 extension 的区域拒绝自定义路径
- 回滚：catalog 返回空，旧 UI 继续由宿主渲染。

### M04 动作分发器

- 目标：按钮和控件动作统一路由。
- 新增：
  - `agent/capabilities/action_dispatch.py`
- 请求：

```json
{
  "path": "web-ui/nav/buttons/update",
  "action": "auto_update.check",
  "payload": {},
  "request_id": "uuid"
}
```

- 响应：

```json
{
  "ok": true,
  "value": null,
  "error": ""
}
```

- 规则：
  - path 必须已注册
  - action 必须属于 owner
  - 失败返回逐项错误
  - 不改其他区域
- 回滚：旧 click handler 保持。

### M05 插件清单扩展

- 目标：清单声明 UI 扩展和权限。
- 修改：
  - `plugins/<name>/plugin-meta.json`
- 新增字段：

```json
{
  "api_version": "1",
  "ui_extensions": [
    "web-ui/chat/extensions/ai_speak"
  ],
  "backend_paths": [
    "backend/tools/ai_speak"
  ],
  "permissions": ["ui.register", "backend.register"]
}
```

- 验收：
  - 未声明白名单不能注册 extension
  - api_version 不匹配拒绝加载
- 回滚：旧清单字段兼容，路径注册不开启。

### M06 PluginContext 路径 API

- 目标：插件只通过路径 API 注册。
- 修改：
  - `agent/capabilities/plugin_context.py`
- 新增：

```text
ctx.add_ui(path, kind, props, action)
ctx.add_backend_path(path, kind, handler)
ctx.bind_ui_renderer(path, renderer)
```

- 旧 API 过渡：

```text
add_ui_item       → web-ui/right-panel/<panel>
add_ui_item      → web-ui/input/buttons/<id>
add_ui_item → 禁止新增；仅迁移期保留读取
```

- 验收：
  - 旧插件仍可加载
  - 新路径注册产生 catalog
  - 卸载清理路径
- 回滚：保留旧方法，路径 API 可停用。

### M07 宿主页面区域化

- 目标：宿主页面只提供稳定区域节点。
- 修改：
  - `plugins/web_ui/ui/classic/agent-ui.html`
  - `agent/shell/web/ui_bundle.py`
  - 新增 `js/core/ui-registry.js`
  - 新增 `js/core/ui-dispatcher.js`
- 区域：

```text
data-ui-region="web-ui/nav"
data-ui-region="web-ui/chat"
data-ui-region="web-ui/input"
data-ui-region="web-ui/left-panel"
data-ui-region="web-ui/right-panel"
data-ui-region="web-ui/runtime"
```

- 验收：
  - 所有区域有稳定节点
  - 事件只在区域根/document 绑一次
  - 插件不查询宿主 id
- 回滚：删除区域属性，旧 HTML 保持。

### M08 导航迁移

- 目标：导航按钮由注册表渲染。
- 修改：
  - 新增 `web-ui` 基础插件或内置 UI provider
  - `web-ui/nav` 容器
  - 迁移 `updateBtn`、`hdrThemeBtn`、`hdrSettingsBtn`
- 目标路径：

```text
web-ui/nav/buttons/update       自动更新插件
web-ui/nav/buttons/style        风格插件
web-ui/nav/buttons/settings     基础设置插件
```

- 验收：
  - 三个按钮由 catalog 生成
  - 顺序稳定
  - 插件卸载按钮消失
- 回滚：恢复旧按钮 id 和绑定。

### M09 输入区迁移

- 目标：输入区按钮和输入框按路径注册。
- 修改：
  - `web-ui` 基础插件注册 textarea、图片、模式、思考、目标、发送、停止
  - 多模型插件注册模型按钮
  - 知识库插件注册知识库按钮
  - 视觉插件注册眼睛按钮
- 目标路径：

```text
web-ui/input/textarea
web-ui/input/buttons/image_btn
web-ui/input/buttons/mode_btn
web-ui/input/buttons/thinking_btn
web-ui/input/buttons/model_switch_btn
web-ui/input/buttons/kb_btn
web-ui/input/buttons/visual_btn
web-ui/input/right-buttons/goal_btn
web-ui/input/right-buttons/send_btn
web-ui/input/right-buttons/stop_btn
```

- 验收：
  - 左右按钮分组
  - send/stop 互斥
  - textarea 不接受插件注册
- 回滚：保留旧按钮 DOM。

### M10 对话区迁移

- 目标：消息、用户气泡、AI 气泡、工具壳统一渲染。
- 修改：
  - `js/chat/bubbles.js`
  - `js/chat/tool-events.js`
  - `js/chat/conversation.js`
  - `js/chat/stream.js`
- 目标路径：

```text
web-ui/chat/messages
web-ui/chat/messages/user_msg
web-ui/chat/messages/ai_msg
web-ui/chat/messages/tools
web-ui/chat/messages/tools/<tool_name>
```

- 验收：
  - 消息卡片渲染
  - 工具名稳定
  - 未知工具回退基础工具壳
  - 流式更新不重建整棵区域
- 回滚：保留旧消息构造函数。

### M11 左侧栏迁移

- 目标：会话列表和上下文用量由区域渲染。
- 修改：
  - `js/chat/context-usage.js`
  - `js/layout/splitters.js`
  - `agent-ui.html` 左侧栏
- 目标路径：

```text
web-ui/left-panel/sessions
web-ui/left-panel/sessions/new
web-ui/left-panel/sessions/list
web-ui/left-panel/context_usage
web-ui/left-panel/context_usage/system
web-ui/left-panel/context_usage/summary
web-ui/left-panel/context_usage/full_recent
web-ui/left-panel/context_usage/mode
web-ui/left-panel/context_usage/remaining
web-ui/left-panel/context_usage/skills
web-ui/left-panel/context_usage/kb
web-ui/left-panel/context_usage/rules
```

- 验收：
  - 基础段颜色固定
  - 插件段颜色可注册
  - 滚动、拖拽、收起不变
- 回滚：恢复旧 usage DOM 结构。

### M12 右侧栏与运行时迁移

- 目标：右栏面板、运行时控件独立注册。
- 修改：
  - `js/panels/panes.js`
  - `js/chat/subagents.js`
  - `js/chat/background-tasks.js`
  - `agent-ui.html` 右栏和运行时
- 目标路径：

```text
web-ui/right-panel/steps
web-ui/right-panel/open_file
web-ui/right-panel/kb

web-ui/runtime/left-panel
web-ui/runtime/left-panel/ai_speak
web-ui/runtime/left-panel/inbox
web-ui/runtime/right-panel
web-ui/runtime/right-panel/background_task
web-ui/runtime/right-panel/subagent
```

- 验收：
  - 开关控制步骤面板
  - 面板打开/关闭由父路径处理
  - 运行时控件按状态挂载
  - 私域内容不操作标签栏
- 回滚：保留旧 side pane 和 bg-task 面板。

### M13 设置迁移

- 目标：宿主静态设置完全移出。
- 修改：
  - `plugins/base_settings/plugin.py`
  - `plugins/multi_model/plugin.py`
  - `agent/shell/settings_panel.py`
  - `agent/shell/settings_port.py`（新增宿主设置端口）
  - `agent/capabilities/plugin_context.py`
  - `plugins/web_ui/ui/classic/js/settings-ui.js`
- 端口：
  - `read(section, key)`
  - `write(section, key, value)`
  - `apply()`
- 目标：
  - `settings/agent`
  - `settings/context`
  - `settings/interface`
  - `settings/plugin`
  - `settings/model`
  - 条目 `settings/<panel>/<item>`
- 验收：
  - 目录只来自设置注册表
  - 保存调用 owner 回调
  - 卸载面板消失
  - 设置值保留
- 回滚：旧 `_fields` 读取保留只读兼容。

### M14 后端能力迁移

- 目标：后端扩展从方法注册迁移到路径注册。
- 修改：
  - `agent/capabilities/plugin_context.py`
  - `agent/capabilities/plugins.py`
  - `agent/capabilities/backend_registry.py`
- 迁移表：

```text
register_tool                → backend/tools/<tool>
add_executor                 → backend/tools/<tool>/executor
add_pre_gate                 → backend/tools/pipeline/pre-gates/<plugin>/<id>
add_post_observer            → backend/tools/pipeline/post-observers/<plugin>/<id>
add_context_source           → backend/context/sources/<plugin>/<id>
add_context_assembly_hook    → backend/context/assembly-hooks/<plugin>/<id>
add_prompt_section           → backend/prompt/sections/<section>/<plugin>
add_mode_tail                → backend/prompt/mode-tails/<plugin>
subscribe                    → backend/events/subscriptions/<event>/<plugin>
add_route                    → backend/http/routes/<route_id>
add_model_catalog            → backend/models/catalog/<plugin>
add_settings_panel           → settings/<panel>
add_settings_item            → settings/<panel>/<item>
```

- 验收：
  - 每个 handler 可按路径查询
  - 卸载删路径
  - 冲突拒绝
- 回滚：旧方法代理到路径注册表。

### M15 基础 WEB-UI 插件

- 目标：提供页面壳和宿主专属区域。
- 新增：
  - `plugins/web_ui/plugin.py`
  - `plugins/web_ui/plugin-meta.json`
- 注册：

```text
web-ui
web-ui/nav
web-ui/chat
web-ui/input
web-ui/left-panel
web-ui/right-panel
web-ui/runtime
web-ui/settings
```

- 宿主专属内容：

```text
textarea
图片按钮
模式按钮
思考按钮
目标按钮
发送按钮
停止按钮
会话基础列表
上下文用量基础段
消息气泡基础壳
```

- 验收：
  - 基础区域由插件注册
  - 宿主只做通用挂载
  - 不允许其他插件注册这些固定子路径
- 回滚：宿主直接渲染区域。

### M16 自动更新插件

- 目标：版本更新按钮归属自动更新插件。
- 当前状态：
  - `updateBtn` 在 `agent-ui.html` 中由宿主渲染。
- 新增或迁移：
  - `plugins/auto_update/`
- 注册：

```text
web-ui/nav/buttons/update
```

- 验收：
  - 插件卸载后按钮消失
  - 检查更新动作走 action dispatch
- 回滚：保留宿主按钮。

## 6. 逐插件迁移

| 插件 | 目标路径 | 迁移内容 |
|---|---|---|
| `web_ui` | `web-ui/*` 基础区域和宿主按钮 | 新建基础 UI 插件 |
| `base_settings` | `settings/agent`、`settings/context`、`settings/interface`、`settings/plugin` | 设置项保留，删除宿主静态字段 |
| `theme_style` | `settings/interface/theme_style`、`web-ui/nav/buttons/style` | 风格设置、黑白按钮、主题资源 |
| `multi_model` | `settings/model`、`web-ui/input/buttons/model_switch_btn` | 模型目录、模型设置、模型选择按钮 |
| `knowledge` | `web-ui/input/buttons/kb_btn`、`web-ui/right-panel/kb`、`web-ui/left-panel/context_usage/kb` | 知识库按钮、面板、用量段、注入源 |
| `ai_speak` | `web-ui/runtime/left-panel/ai_speak` | 播放条从 boot DOM 改为运行时控件 |
| `visual_operator_2` | `web-ui/input/buttons/visual_btn` | 眼睛按钮从 boot DOM 改为输入区注册 |
| `skills` | `web-ui/left-panel/context_usage/skills`、工具壳渲染器 | 用量段、工具视图、上下文源 |
| `rules` | `web-ui/left-panel/context_usage/rules` | 用量段、上下文源、提示词 |
| `auto_update` | `web-ui/nav/buttons/update` | 新建插件或从宿主迁移 |

## 7. 删除旧入口

删除条件：

```text
新路径已注册
新渲染器已经接管
旧 DOM 不再被引用
验收截图通过
```

删除：

```text
agent-ui.html 中对应硬编码按钮和面板
settings_panel.py 中静态 _fields
PluginContext 的 add_ui_item
PluginContext 的 add_ui_item
PluginContext 的 add_ui_item
插件中直接 document.querySelector / 宿主 id 操作
```

保留：

```text
旧插件配置数据
localStorage 主题键
会话数据
插件路由兼容期
```

## 8. 测试矩阵

```text
路径语法
插口协议
owner/kind 冲突
重复注册
卸载清理
前端 extension
动作分发
设置保存/失败
UI catalog
导航按钮
输入区按钮
消息气泡
上下文用量
右侧面板
运行时控件
插件启停
```

## 9. 验收标准

```text
所有扩展点都有路径
所有路径都有父插口协议
没有路径外的 UI 注入
没有插件直接操作宿主 DOM
设置只走 settings/<panel>/<item>
动作只走 action dispatch
插件卸载后路径和节点消失
重新启用恢复
全量验收通过
```

## 10. 回滚策略

```text
每个阶段独立提交
路径注册表可停用，旧入口保留
设置静态字段只读兼容
宿主旧按钮保留到区域迁移完成
插件数据不迁移、不删除
失败时回退该阶段代码，不碰用户数据
```
