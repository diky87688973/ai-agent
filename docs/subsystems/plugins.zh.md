# 插件

## 声明与装配

插件是安装与启停单元，能力由 `plugin-slots.json` 声明。协议唯一正文见[插件2.0插口协议](../plan/plugin-slots-protocol.md)，生命周期与已支持边界见[实现与验证](../plan/plugin2-hotplug.md)。

发现身份 → 读取启用清单 → 合并片段 → 校验归属、依赖和覆盖 → 构造 → SlotBinder登记 → 发布只读快照。

插件目录中的 `plugin-meta.json` 提供身份；`plugin-slots.json` 提供能力声明；Python工厂与UI、配置、模板均归插件目录。纯声明插件不需要Python入口。工厂接收BuildContext及requires声明的依赖，返回当前节点的实现；不是能力注册函数。插件不调用旧式register(ctx)或ctx.add_*。

最小工具片段：

```json
{"slots":[{"path":"app/plugins/example/tools/example_tool","kind":"tool","factory":"plugin:make_tool"}]}
```

```python
def make_tool(ctx):
    return ExampleTool()
```

ExampleTool实现现有ToolPlugin协议；执行经ToolPipeline，不绕过权限和写盘门控。插件可声明runtime节点返回持有dispose()的资源对象；工厂构造失败必须释放自身尚未移交装配器的资源。

## 扩展入口

| 能力 | 声明入口 |
|---|---|
| 模型工具 | tool |
| 插件HTTP端点 | route及method；地址由绑定器派生，位于/api/plugin/<owner>/命名空间 |
| 宿主事件订阅 | event，路径包含唯一宿主事件常量 |
| 插件事件定义与订阅 | event-channel；event通过requires.event引用定义，事件类型为定义节点完整路径 |
| 上下文、提示段、请求尾部、模型目录 | provider及props.target |
| 组装钩子、写类执行器 | assembly-hook、executor |
| 设置 | setting及工厂返回的SettingDecl |
| UI挂载与内容 | ui-slot、ui-action、ui-control、ui-tool-shell |
| 消息面板实现 | ui-tool-shell.props.renderer及有效catalog约束下的前端绑定 |

静态与插件片段共用校验、覆盖和装配机制。注册表是装配代的消费投影，不是第二份能力声明；跨插件引用必须使用显式依赖，不得运行期偷偷查另一份清单。新增业务工具、端点或展示类型通过插件目录扩展；新增基础协议种类仍属于宿主架构变更。

## 启停与失败

plugins.ini决定启停；默认发现与独立清单的自动装载规则以实现文档为准，enabled=0优先。物理文件变动在显式重载后生效，不自动改动活跃轮次。

插件贡献可热插拔；活跃回合及插件HTTP请求持有读取租约，变更在读者退出后发布。构造或绑定失败撤销候选代并恢复旧代，设置页可查询延迟操作终态。关闭提供UI挂载点的插件时，其它插件对该挂载点的贡献休眠。强requires依赖不自动降级：缺失目标使候选配置失败，需一并关闭依赖方或恢复提供方。

内核和宿主服务替换需要重启，不属于插件资源在线迁移。extend/wrap组合构造尚未支持，会明确拒绝。

## 资产与信任

插件私有UI、配置、图标、第三方库与许可证在plugins/<name>/内；公共宿主资产在agent/shell/web/。静态文件可送达不代表能力已启用；前端只能绑定有效声明且owner匹配的类型。

插件代码与本机代码同等信任，不提供Python沙箱。plugin_tree_only限制装载来源路径，不阻止已信任代码访问系统。源码摘要只提供来源诊断，不是签名认证。密钥配置不得入库；插件数据归当前数据根下的插件专属目录，由BuildContext.data_dir注入。

## 配置与相关文档

### 插件自己的配置
插件自己的配置放**插件自己目录下的 `plugin-config.ini`**，只含插件自己的键。
插件用 `agent.config.load_ini()` 读取：

```
plugins/<插件名>/plugin-config.ini     ← 只放插件自己的设置
plugins/<插件名>/plugin-meta.json      ← 身份声明
```

**内核的 `config.ini` 只含内核设置，不放任何插件设置。** 插件的设置在插件自己
目录下，随插件一起装卸、一起删除。`plugin-config.ini` 是插件读取的唯一配置文件；
文件不存在时插件使用代码默认值。`plugin-config.ini.example` 这类格式样例不在运行期读取。
AI角色扮演 / 视觉操作 / 知识库 / Skills 的配置入库，`multi_model` 的配置由 `.gitignore` 排除。

文件名固定是 `plugin-config.ini`（不是 `config.ini`）——`config.ini` 这个名字专指
内核配置，同名两份文件会产生歧义。

**设置页只能改插件自己的节。** 身份与开关不在这份文件里：`name` / `desc` / `icon` /
`version` / `settings_tab` 由 `plugin-meta.json` 声明，`enabled` 由 `plugins.ini`
控制。`settings_tab` 非空且插件已启用、可配置时，设置页在左侧增加同名入口，点击
直接打开该插件的配置编辑器。编辑视图分三种：

- 声明了 `kind: sections` 的插件：按 schema 渲染可增删条目；
- 声明了 `kind: fields` 的插件：按 schema 渲染字段表单，保存只更新声明字段；
- 其余插件：正文是插件自己的键，保存时替换对应节。

**没有可编辑设置的插件由它自己声明**：`plugin-meta.json` 里写 `"config": "false"`，
设置页就不再给它「设置」按钮（判据是插件声明，不是内核去猜有没有配置文件）。
`plugins/rules` 就是这样：只有开关，没有配置。

按 schema 渲染的表单里，密钥字段只回显“是否已配置”，留空表示沿用原值。

插件自己的键由插件自己读、自己解释：内核不解析插件配置，`agent/config.py` 里
没有任何插件节的读取口。`dir` 一类的相对路径按**工程根**解析（不是按插件目录），
与内核配置保持同一口径。插件的定位不依赖内核 API：`Path(__file__).resolve().parent`
就是插件目录。

权限边界：含密钥的插件配置不入库；同机能读到插件目录的进程就能读到它的配置。
这与「插件与本机代码同等信任」是同一条边界（见「插件信任模型」）。

## 6. 延伸阅读

| 主题 | 文档 |
|---|---|
| 注入源如何进入装配、组装顺序怎么定 | [context.zh.md](context.zh.md) |
| `knowledge` 的文件收录、勾选与注入 | [knowledge.zh.md](knowledge.zh.md) |
| `multi_model` 的目录条目与设置页表单 | [multi-model.zh.md](multi-model.zh.md) |
| `skills` 插件的三层披露与 `skills` 工具 | [skills.zh.md](skills.zh.md) |
| `visual_operator` 的截屏、坐标契约与平台后端 | [visual-operator.zh.md](visual-operator.zh.md) |
| 工具的注册、执行管道与写盘协议 | [tools.zh.md](tools.zh.md) |
| HTTP 路由与界面打包 | [shell.zh.md](shell.zh.md) |
| 配置项全表 | [config.zh.md](../guide/config.zh.md) |

#### 壳层公共桥

插件在**面板之外**（输入区、页头）放置 UI 时，用壳层桥而不是自己拼 URL、
不读壳层内部变量：

```js
// 模型：list() → Promise<[{id,label,provider}]>；current() → string；
// select(id) → Promise<boolean>；onChange(fn) → 取消订阅函数。
const models = window.aiAgentShell.models;
const stop = models.onChange((id) => renderLabel(id));
await models.select("target");
stop();

// 样式：relPath 是插件目录内相对路径；同一路径只注入一次。
window.aiAgentShell.styles.load("ui/model-picker.css");
```

`aiAgentShell` 与 `aiAgentPlugins` 平级：前者是壳层能力，后者是插件自己的端点。
桥本身**不持有当前模型** —— `current()` 每次读活动标签页，多份状态必然分叉。
`select()` 先乐观更新界面，再写 `/api/chat/ui-state` 并广播；写失败会回滚并返回
`false`。服务端下发的值（会话恢复 / SSE）不受本地清单限制。

`styles.load()` 复用面板样式的去重表与 `/api/plugin/<插件>/_asset/` 路由：
绝对路径、盘符、协议与 `..` 一律返回 `false`。插件停用后，`applyPluginsChanged`
会摘掉带 `data-plugin-style` 的 `<link>`，并清掉 `#modelPickerSlot` 里
`data-plugin` 已不在装载名单的子元素。

插件变更不需要刷新页面：壳层刷新 UI catalog 与已装载插件集合，关闭已卸载插件的面板，并清空脚本与样式缓存，使重新启用后脚本能重新执行。

#### 宿主设置面板与条目

设置通过插件设置注册表注册，不通过宿主 DOM。插件可用 `add_settings_panel(panel_id, title=...)` 增加面板，用 `add_settings_item(parent, item_id, kind=..., save=..., load=...)` 增加条目。

支持的条目类型为 `text`、`search`、`number`、`select`、`checkbox`、`textarea`、`password`；`select` 必须显式给出选项列表。条目 ID 的命名空间为 `settings/<panel>/<item>`。

条目所属插件提供 `save` 回调。宿主只渲染带类型的控件，把所有变更后的插件值提交给通用设置入口；插件系统再把每个条目分派给所属插件。回调负责持久化并应用本插件值，然后返回成功或失败。插件不得创建、修改或查询设置 DOM。

插件卸载后，其面板与条目立即消失；插件自己持久化的值保留到下次启用。

#### 会话切换通知

面板内容带会话级状态时（如勾选），会话一换就要重取。壳层广播一个通用事件，
**谁需要谁订阅**：

```js
document.addEventListener("ai-agent:conversation-changed", function () {
  if (document.getElementById("kbBody")) render();
});
```

壳层不点名任何插件，也不要求插件认识壳层。


<a id="插件信任模型"></a>

插件信任模型见上方“资产与信任”：同进程插件具有本机代码权限，路径限制不是代码沙箱。
