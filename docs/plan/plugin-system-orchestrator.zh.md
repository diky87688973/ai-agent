# 插件系统编排设计
> 全路径替换契约见 [plugin-system-arbitrary-replacement.zh.md](plugin-system-arbitrary-replacement.zh.md)。任何已暴露路径都允许被替换。


## 1. 目标

插件系统不是“文件扫描器”，而是插件的注册、编排、设置、分发、广播与生命周期管理器。

它向上承接宿主，向下对接内核，插件只面对插件系统。

```text
Host
  ↕ 通用契约
Plugin System
  ↕ 通用契约
Kernel
```

宿主和内核都不认识具体插件。插件系统认识插件的声明、能力、依赖、设置与回调。

## 2. 三个契约

### 2.1 插件系统自身

插件系统提供：

```text
发现与清单校验
依赖解析与激活顺序
注册事务与失败回滚
能力注册与优先级
设置面板/条目注册
保存回调分发
UI 表面描述生成
HTTP 路由分发
资产路径解析
事件广播
启停与热重载
诊断与贡献清单
```

插件系统自己不实现业务能力。

### 2.2 插件系统 ↔ 宿主

宿主只提供通用运行面：

```text
进程/服务生命周期
HTTP 入口与鉴权
浏览器页面壳
静态资源发送
通用 UI 渲染器
通用设置页渲染器
通用错误展示
```

宿主从插件系统获取：

```text
UI 表面描述
设置面板/条目描述
HTTP 路由表
资产地址
广播事件
插件启停结果
```

宿主不得：

```text
按插件名写分支
读取插件私有配置
解释插件字段语义
直接拼接插件私有 DOM
直接调用插件内部函数
```

### 2.3 插件系统 ↔ 内核

内核只暴露稳定端口：

```text
ToolRegistry / ToolPipeline
ContextSources / PromptSections
ModelCatalog
SessionStore / EventBus
ExecutorRegistry
Gate/PostObserver
```

插件系统把插件贡献映射到这些端口。

内核不得：

```text
识别插件名
识别插件配置键
加载插件 UI
解析插件设置
为单个插件增加分支
```

## 3. 插件清单

```json
{
  "id": "theme_style",
  "name": "主题风格",
  "version": "1.0.0",
  "api_version": "1",
  "entry": "plugin.py",
  "requires": [],
  "optional": [],
  "provides": ["settings.provider", "ui.style"],
  "permissions": ["ui.register", "settings.register", "asset.read"],
  "activation": "startup"
}
```

硬约束：

```text
id 全局唯一，只允许稳定标识符
api_version 不匹配则拒绝加载
requires 未满足则拒绝激活
注册失败必须整体回滚
同一插件不能重复加载
```

## 3.1 设置面板归属

```text
settings              ← 宿主
settings/agent        ← 基础设置插件
settings/context      ← 基础设置插件
settings/interface    ← 基础设置插件
settings/plugin       ← 基础设置插件
settings/model        ← 多模型插件
```

基础设置插件只注册自己的面板和条目，不替多模型插件注册模型面板。多模型插件自行注册 `settings/model` 及其条目。宿主只提供 `settings` 根和通用渲染、保存、分发、广播。

## 4. 注册贡献

所有贡献有统一结构：

```text
owner      插件 id
id         全局贡献 id
kind       贡献类型
priority   数值，默认 0
payload    类型化配置
dispose    幂等撤销
```

### 4.1 HTTP

```python
ctx.add_http_route(
    route_id="download",
    method="GET",
    path="download/:id",
    handler=handler,
    scopes=("user",),
    public=False,
)
```

路径固定在：

```text
/api/plugin/<plugin-id>/
```

若插件需要替换整个 HTTP 服务，只能注册 `http.provider` 能力，不能改宿主路由分发器。

### 4.2 UI

UI 不是插件直接操作宿主 DOM，而是注册类型化表面：

```python
ctx.add_ui_panel(
    panel_id="settings/model",
    title="模型",
    surface="settings",
    items=[...],
)
```

```python
ctx.add_ui_item(
    parent="settings/interface",
    item_id="theme_style",
    kind="select",
    label="界面风格",
    options=[...],
)
```

支持的控件类型：

```text
text / search / number / select / checkbox / textarea
button / table / markdown / notice / custom-panel
```

宿主负责：

```text
渲染
布局
生命周期
保存入口
错误展示
```

插件负责：

```text
自己的业务语义
自己的面板内容
自己的保存/应用逻辑
```

禁止插件选择器：

```text
#stForm
#stNav
#stClose
.st-row
```

### 4.3 设置

设置是插件系统的一等能力，不是壳层字段表。

```python
ctx.add_settings_panel(
    panel_id="settings/interface",
    title="界面",
    priority=0,
)
```

```python
ctx.add_settings_item(
    parent="settings/interface",
    item_id="theme_style",
    kind="select",
    label="界面风格",
    default="dsh",
    options=[
        {"value": "dsh", "label": "DSH 风格"},
        {"value": "minimal", "label": "极简风格"},
    ],
    save=save_theme_style,
    load=load_theme_style,
)
```

设置 ID：

```text
settings
settings/agent
settings/context
settings/interface
settings/model
settings/plugin
settings/<panel-id>
settings/<panel-id>/<item-id>
```

`save` 回调由注册者提供：

```python
def save_theme_style(values):
    # 1. 校验
    # 2. 写入插件自己的配置
    # 3. 应用新配置
    # 4. 返回 {ok, error}
    return {"ok": True}
```

保存流程：

```text
UI 收集全部变更
→ POST settings
→ 插件系统按 item owner 分组
→ 逐一调用 save 回调
→ 单体失败则该 item 失败
→ 插件系统汇总
→ 成功后广播 settings_changed
→ UI 刷新
```

插件系统不解释字段，只负责路由、校验类型、汇总结果、广播。

### 4.4 工具与执行器

```python
ctx.add_tool(tool)
ctx.add_executor(name, fn)
ctx.add_pre_gate(gate)
ctx.add_post_observer(observer)
```

工具仍然经过同一工具管道。

### 4.5 上下文与提示词

```python
ctx.add_context_source(fn, meta)
ctx.add_mode_tail(fn)
ctx.add_prompt_section(section, fn)
```

### 4.6 事件

```python
ctx.subscribe("session_started", handler)
ctx.publish("theme_changed", payload)
```

插件系统统一管理订阅、取消、广播与异常隔离。

### 4.7 能力替换

内核能力通过“端口 + Provider”扩展。

```python
ctx.add_provider(
    port="model.gateway",
    provider_id="my-gateway",
    factory=build_gateway,
    priority=100,
    replaces="default",
)
```

可替换的是有契约的 Provider：

```text
model.gateway
session.store
tool.executor
context.builder
ui.renderer
http.provider
```

内核启动、鉴权、持久化不变量和进程生命周期也通过路径绑定提供默认实现；替换必须显式、可回滚。

替换规则：

```text
同端口按 priority 排序
requires 必须满足
replaces 必须指向已注册 provider
默认 provider 永远保留
失败时回退默认 provider
冲突必须报告，不静默选择
```

## 5. 插件系统内部组件

```text
PluginCatalog        发现清单
ManifestValidator    清单与版本校验
DependencyResolver   依赖图与循环检测
ActivationManager    加载、激活、回滚、卸载
ContributionRegistry 类型化贡献表
CapabilityBroker     Provider 注册与选择
SettingsManager      面板/条目、保存分发
UiRegistry           UI 表面描述
HttpDispatcher       插件命名空间路由
AssetResolver        插件资产路径与类型
EventBroadcaster     插件事件广播
PermissionBroker     权限声明与检查
Diagnostics          贡献清单、加载报告、失败记录
```

## 6. 生命周期

```text
discover
→ validate
→ resolve
→ prepare
→ activate
→ ready
→ disable
→ unload
→ reload
```

规则：

```text
激活失败 → 回滚已注册贡献
卸载 → 逆序撤销
热重载 → 重新解析并恢复设置
插件关闭 → 移除 UI/路由/设置条目，保留用户配置
重新启用 → 恢复设置，不要求用户重选
```

## 7. 设置与 UI 的宿主契约

宿主只实现通用适配器：

```text
settings.catalog()   返回插件系统生成的 panels/items
settings.commit(payload) 交给插件系统分发
ui.mount(descriptor) 按类型渲染通用控件
http.dispatch(request) 转发插件命名空间
events.subscribe(fn) 接收插件系统广播
```

宿主不读取：

```text
插件 private 配置
插件 settings callback 源码
插件业务状态
```

插件不读取：

```text
宿主设置 DOM
宿主路由内部表
宿主页面状态
```

## 8. 兼容与迁移

第一阶段：

```text
建立 SettingsManager 和 ContributionRegistry
把现有 Agent/Context/Interface/Model/Plugin 设置注册为内置 Provider
迁移 add_settings_field 为 settings item
```

第二阶段：

```text
建立 UI surface registry
把设置页、面板、输入区动作、状态栏迁移为类型化 UI
```

第三阶段：

```text
建立 HTTP 插件命名空间分发
把插件自己的 route 迁移到 HttpDispatcher
```

第四阶段：

```text
建立 Provider 替换机制
迁移 model catalog、session store、tool executor、theme style
```

迁移期间禁止：

```text
插件直接改宿主 DOM
插件直接写宿主配置文件
壳层按插件名分支
设置入口分裂
```

## 9. 验收标准

```text
一个插件只声明清单和贡献，不改壳层/内核
设置面板和条目全部来自注册表
设置保存统一走 settings 入口
保存回调由注册者执行并返回结果
插件关闭后 UI/路由/设置立即消失
插件重新启用后保留用户设置
HTTP 路由、UI、设置、Provider 都可枚举
没有插件名出现在 kernel/shell 分支中
宿主不解析插件字段语义
```

## 10. 结论

插件系统是编排层，不是插件目录的附属物。

它应拥有：

```text
插件注册
依赖解析
能力编排
设置分发
UI 描述
HTTP 分发
事件广播
生命周期
诊断
```

宿主只提供运行面和通用渲染器；内核只提供稳定端口。

插件的所有扩展都应通过这套编排层完成，而不是通过修改公共 DOM、写宿主配置或让壳层识别插件名。
