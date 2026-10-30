# 插件系统资产拆分与整合

## 1. 结论

页面 CSS/JS、插件 CSS/JS、宿主启动资源必须按 owner 拆开。

```text
宿主只保留：
  鉴权
  HTTP 和静态资源传输
  进程生命周期
  启动引导

插件系统只保留：
  路径注册
  catalog
  动作分发
  生命周期
  资产清单

页面和业务 UI：
  由 WEB-UI 基础插件拥有

业务界面：
  由对应插件拥有
```

宿主不再保存页面结构、聊天 UI、输入区 UI、设置 UI、主题 UI、更新 UI。

## 2. 当前资产问题

```text
agent-ui.html 包含导航、聊天、输入、左右栏、运行时、设置入口
classic/css 同时包含基础布局、聊天、设置、主题、更新、后台任务
classic/js 同时包含宿主启动、页面区域、插件宿主、设置、主题、更新
ui_bundle.py 维护一份硬编码 CSS/JS 清单
settings_panel.py 保留宿主设置字段和保存逻辑
插件通过 boot script 查询宿主 DOM
插件 CSS/JS 与宿主 CSS/JS 混在同一目录
```

这些资产在代码上分属不同 owner，物理上却混在一起，最终会让宿主继续做插件逻辑的粘合剂。

## 3. 新资产分层

```text
Host Runtime
  鉴权、HTTP、静态传输、进程
Plugin System Runtime
  路径注册、catalog、动作、生命周期
Base UI Plugin
  页面壳、区域容器、基础聊天/输入/左右栏
Base Settings Plugin
  设置页 UI 和设置字段
Feature Plugins
  各业务控件和面板
```

依赖方向：

```text
Host Runtime
  → Plugin System Runtime
  → Base UI / Base Settings / Feature Plugins
```

插件不能反向依赖宿主页面实现。

## 4. 目录结构

```text
agent/shell/web/
  web_assets/
    bootstrap/
      auth-client.js
      boot.js
      vendor/
    plugin-system/
      ui-host.js
      ui-registry.js
      ui-dispatcher.js
  ui_bundle.py              仅做通用装载，不保存业务模块清单
  web_routes.py             通用 API 和静态传输

plugins/web_ui/
  plugin.py
  plugin-meta.json
  ui/
    shell.html
    css/
      base/reset.css
      base/tokens.css
      regions/layout.css
      regions/nav.css
      regions/chat.css
      regions/input.css
      regions/left-panel.css
      regions/right-panel.css
      regions/runtime.css
      chat/messages.css
      chat/markdown.css
      chat/tools.css
      files/file-cards.css
      files/edited-files.css
    js/
      main.js
      regions/nav.js
      regions/chat.js
      regions/input.js
      regions/left-panel.js
      regions/right-panel.js
      regions/runtime.js
      chat/messages.js
      chat/composer.js
      chat/tools.js
      files/viewer.js
      layout/splitters.js
    components/

plugins/base_settings/
  ui/
    settings.js
    settings.css
  plugin.py
  plugin-meta.json

plugins/theme_style/
  ui/
    theme.js
    theme.css
  styles/
  plugin.py

plugins/multi_model/
  ui/model-picker.js
  ui/model-picker.css

plugins/knowledge/
  ui/kb-button.js
  ui/kb-panel.js
  ui/kb-usage.js

plugins/ai_speak/
  ui/runtime.js
  ui/player.css

plugins/visual_operator_2/
  ui/eye-button.js
  ui/vision.css

plugins/auto_update/
  ui/update-button.js
  ui/update.css
  plugin.py
  plugin-meta.json
```

`plugins/web_ui/ui/classic` 不再出现 `chat/`、`composer/`、`settings-ui`、`theme-ui`、`update.css`。

## 5. 文件归属映射

### 5.1 HTML

| 原资产 | 新归属 |
|---|---|
| `agent-ui.html` | `plugins/web_ui/ui/shell.html` |
| 页面模板渲染 | Host 只调用 base UI 插件 manifest 获取模板 |

### 5.2 CSS

| 原资产 | 新归属 |
|---|---|
| `reset.css` | `web_ui/ui/css/base/reset.css` |
| `layout.css` | `web_ui/ui/css/regions/layout.css` |
| `frame.css` | `web_ui/ui/css/base/frame.css` |
| `theme-tokens.css` | `theme_style/ui/theme.css` |
| `theme-light.css` | `theme_style/ui/theme.css` |
| `theme-light-cursor.css` | `theme_style/ui/theme.css` |
| `chat-messages.css` | `web_ui/ui/css/chat/messages.css` |
| `markdown.css` | `web_ui/ui/css/chat/markdown.css` |
| `chat-tool-views.css` | `web_ui/ui/css/chat/tools.css` |
| `chat-file-cards.css` | `web_ui/ui/css/files/file-cards.css` |
| `file-icons.css` | `web_ui/ui/css/files/file-icons.css` |
| `edited-files.css` | `web_ui/ui/css/files/edited-files.css` |
| `composer.css` | `web_ui/ui/css/regions/input.css` |
| `chat-queue.css` | `web_ui/ui/css/chat/queue.css` |
| `system-notice.css` | `web_ui/ui/css/chat/notice.css` |
| `background-tasks.css` | `web_ui/ui/css/regions/runtime.css` |
| `subagents.css` | `web_ui/ui/css/regions/runtime.css` |
| `side-tabs.css` | `web_ui/ui/css/regions/right-panel.css` |
| `todo.css` | `web_ui/ui/css/chat/todo.css` |
| `todo-card.css` | `web_ui/ui/css/chat/todo.css` |
| `window-chrome.css` | `web_ui/ui/css/base/window-chrome.css` |
| `update.css` | `auto_update/ui/update.css` |
| `settings-ui.css` | `base_settings/ui/settings.css` |
| `vendor/*.css` | `bootstrap/vendor/` |

### 5.3 JS

| 原资产 | 新归属 |
|---|---|
| `core/auth-client.js` | `bootstrap/auth-client.js` |
| `core/boot.js` | `bootstrap/boot.js` |
| `plugins/host.js` | `plugin-system/ui-host.js` |
| `shell/supervisor.js` | `bootstrap/supervisor.js` |
| `shell/window-chrome.js` | `web_ui/ui/js/base/window-chrome.js` |
| `shell/update.js` | `auto_update/ui/update-button.js` |
| `theme-ui.js` | `theme_style/ui/theme.js` |
| `settings-ui.js` | `base_settings/ui/settings.js` |
| `chat/*` | `web_ui/ui/js/chat/` |
| `composer/*` | `web_ui/ui/js/input/` |
| `layout/splitters.js` | `web_ui/ui/js/layout/splitters.js` |
| `panels/*` | `web_ui/ui/js/panels/` |
| `render/*` | `web_ui/ui/js/render/` |
| `tools/*` | `web_ui/ui/js/tools/` |
| `chat-tool-views.js` | `web_ui/ui/js/chat/tools.js` |
| `file-icons.js` | `web_ui/ui/js/files/icons.js` |
| `edited-files.js` | `web_ui/ui/js/files/edited.js` |
| `image-lightbox.js` | `web_ui/ui/js/files/lightbox.js` |
| `code-highlight.js` | `web_ui/ui/js/chat/highlight.js` |
| `vendor/*.js` | `bootstrap/vendor/` |

## 6. CSS 契约

```text
每个插件 CSS 根节点带 data-ui-plugin="<plugin>"
所有选择器以该根节点或 data-ui-region 开头
禁止 body/html/:root 全局选择器（主题插件按显式 token 协议例外）
通过路径绑定替换其他插件的实现，不直接覆盖 DOM 区域
基础变量使用 --ui-* 前缀
主题插件只能设置 token 和自己的根属性
```

加载顺序：

```text
bootstrap vendor
→ base UI tokens/reset
→ base UI regions
→ base settings
→ feature plugins
```

主题切换只替换 token 值，不重写其他插件 CSS。

## 7. JS 契约

```text
bootstrap 只加载插件系统和 base UI
base UI 只负责页面容器和基础区域
插件模块只注册路径、渲染器和动作
插件模块不查询宿主 id
插件模块不直接拼接宿主 HTML
事件由 plugin-system/ui-dispatcher 统一处理
插件卸载删除自己的注册和 DOM 子树
```

全局变量只允许：

```text
window.DshPluginSystem
window.DshUi
```

其他状态全部封装在模块内。

## 8. 资产清单

每个插件 `plugin-meta.json` 增加：

```json
{
  "ui": {
    "entry": "ui/main.js",
    "styles": ["ui/theme.css"],
    "html": "ui/shell.html",
    "regions": ["web-ui/chat", "web-ui/input"]
  },
  "assets": {
    "root": "ui"
  }
}
```

`ui_bundle.py` 不再维护 `UI_CSS_MODULES` / `UI_JS_MODULES` 硬编码列表。

改为：

```text
读取 base UI manifest
→ 读取插件 catalog
→ 按注册顺序输出资源的 hash
→ 浏览器按 manifest 加载
```

## 9. 后端拆分

```text
agent/shell/settings_panel.py
  保留：通用 settings API 适配、HostSettingsPort 调用
  移除：字段定义、保存逻辑、页面 UI

agent/shell/web/ui_bundle.py
  保留：通用模板装配、资源清单、缓存
  移除：业务 CSS/JS 模块列表

agent/shell/web/web_routes.py
  保留：通用 /api/ui、/api/settings、/api/action
  移除：具体插件的页面分支

plugins/web_ui/
  拥有页面壳、基础区域、基础控件

plugins/base_settings/
  拥有设置页 UI、字段、保存回调

plugins/theme_style/
  拥有主题 token、主题切换按钮、主题 CSS/JS

plugins/auto_update/
  拥有更新按钮和更新 UI

其他插件
  拥有自己的按钮、面板、控件和资源
```

## 10. 禁止的粘合

```text
宿主 HTML 里写插件按钮
宿主 CSS 里写插件控件样式
宿主 JS 里写插件业务分支
插件 boot script 查询宿主 DOM
插件注册代码散落在 shell
ui_bundle 维护业务资源清单
settings_panel 维护插件字段
插件 CSS 覆盖全局
插件 JS 修改宿主状态
```

## 11. 迁移步骤

### A. 建立装载层

```text
新增 bootstrap/plugin-system 资源
新增 plugin-meta ui/assets 字段
ui_bundle 改为 manifest 驱动
```

### B. 迁移基础页面

```text
agent-ui.html → web_ui/ui/shell.html
classic base CSS → web_ui
classic base JS → web_ui
宿主只保留 bootstrap
```

### C. 迁移设置

```text
settings-ui.js/css → base_settings
settings_panel 字段 → base_settings 插件
HostSettingsPort 接入
```

### D. 迁移主题和更新

```text
theme-ui.js + theme CSS → theme_style
update.js/css → auto_update
hdrThemeBtn/updateBtn → nav 注册
```

### E. 迁移业务插件

```text
multi_model/model-picker
knowledge/kb
ai_speak/runtime
visual_operator_2/eye
skills/rules/usage
```

### F. 删除旧资产

```text
删除 classic 中已迁移的 CSS/JS/HTML
删除 UI_CSS_MODULES / UI_JS_MODULES
删除 settings_panel 静态字段
删除插件 boot script 中的宿主 DOM 操作
```

### G. 验收

```text
页面截图对比
资源 404 检查
CSS 作用域检查
JS 全局变量检查
插件启停检查
设置保存检查
```

## 12. 验收标准

```text
每个 CSS/JS/HTML 文件有唯一 owner
宿主目录不再包含页面业务资源
插件目录包含自己的全部 UI 资产
ui_bundle 没有业务模块清单
settings_panel 没有字段定义
插件不直接查询宿主 id
主题切换只改 token
插件卸载资源立即失效
全量验收通过
```
