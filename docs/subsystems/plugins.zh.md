[English](plugins.md) | **中文**

# 插件

插件是内核之外的能力扩展点：工具、事件订阅、上下文注入、工具管道门控、写类工具的
执行器、HTTP 端点与界面，都由插件声明。**内核不认任何具体插件** —— 它只提供贡献
注册表与 HTTP 转发。

内置能力也走这条路：知识库与 Skills 都是插件。移除某个插件的清单节后，它的注入源、
工具、面板、按钮与端点一并撤销，内核不受影响。

## 包

插件是 `plugins/` 下的一个目录，目录名即插件名，也是清单里用的名字：

```
plugins/<插件名>/
  plugin.py             必须。唯一入口，暴露 register(ctx)
  plugin-meta.json      身份元数据：name / desc / icon / version / settings_tab（设置页读取）
  plugin-config.ini     可选。插件自己的真实配置；无敏感信息时入库，含密钥时（如 multi_model）不入库
  settings-schema.json  可选。设置页的结构化表单声明
  ui/                   可选。面板的样式与脚本
  <其它文件>            可选。插件自己的数据文件、库、模板
```

最小形态是只有一个 `plugin.py` 的目录：只订阅事件，不注册工具，也不贡献界面。

`register(ctx)` 返回 disposer、disposer 列表或不返回（`None`）。**每个 `ctx.add_*`
都返回 disposer**，宿主在调用时把它记入本插件的贡献账本（含 `add_panel` / `add_route` /
`add_action` / `add_boot_script` / `add_ctx_segment_style` 等）。`register` 返回的
disposer 与账本合并、按对象身份去重；卸载时逆序调用。`register` 抛错时，经 `ctx`
完成的注册全部回滚，插件不会留下半截状态。

插件可以把实现拆成同目录的多个模块，用相对导入引用：

```python
from .library import Thing
```

子包同样适用（`from .tools.eye import DesktopEyeTool`）：加载器补上 `fan_agent_plugins`
父包，插件目录内的相对导入按包内解析。

## 清单：`plugins.ini`

工程根的 `plugins.ini` 列出插件。节在即进入装载候选；开关是该节的 `enabled`。

```ini
[plugin:skills]

[plugin:knowledge]

[plugin:local-lab]
path = /opt/local/my-plugin
enabled = 1
```

| 字段 | 必填 | 说明 |
|---|---|---|
| 节名 | 是 | 固定 `[plugin:<名字>]`。名字即模块名后缀与默认目录名，必须匹配 `[A-Za-z0-9][A-Za-z0-9_-]*` |
| `path` | 否 | 插件目录（可在 `plugins/` 外）。相对路径按插件根解析；空则 `plugins/<名字>`。装载后，资产与设置编辑器经宿主的 `plugin_root(名字)` 解析，不写死 `plugins/<名字>` |
| `enabled` | 否 | `0` 不装载；缺省按 `1`。设置页开关写这一项 |

**节的先后有意义**：它就是插件的装载位次，也是**上下文里插件段的组装顺序**
（见 [context.md](context.zh.md#assembly-order)）。越不容易变动的插件排在越前面。

清单错误可见：名字非法、目录不存在、缺 `plugin.py` 都会记一条 `error` 报告，
不阻断启动，也不会静默当没写。

### 模式覆盖层

运行模式只覆盖差异，不复制完整清单：

```ini
# plugins.headless.ini
[profile]
base = plugins.ini

[plugin:ai_speak]
enabled = 0
```

`[profile] base` 先读基底清单，再按插件名覆盖显式字段；未出现的插件继承基底，
新增插件追加在末尾。`agent.entry.headless` 默认加载 `plugins.headless.ini`，
`agent.entry.cli` 默认加载 `plugins.cli.ini`，Web 入口继续使用 `plugins.ini`。
覆盖层只写 `path` / `enabled` 差异。

## 插件自己的配置

插件自己的配置放**插件自己目录下的 `plugin-config.ini`**，只含插件自己的键。
插件用 `agent.config.load_ini()` 读取：

```
plugins/<插件名>/plugin-config.ini     ← 只放插件自己的设置
plugins/<插件名>/plugin-meta.json      ← 身份声明
```

**内核的 `config.ini` 只含内核设置，不放任何插件设置。** 插件的设置在插件自己
目录下，随插件一起装卸、一起删除。`plugin-config.ini` 是插件读取的唯一配置文件；
文件不存在时插件使用代码默认值。`plugin-config.ini.example` 这类格式样例不在运行期读取。
AI说话 / 视觉操作 / 知识库 / Skills 的配置入库，`multi_model` 的配置由 `.gitignore` 排除。

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
这与「插件与本机代码同等信任」是同一条边界（见下文）。

## 扩展点全表

`PluginContext` 上所有 `add_*` 都返回 disposer。

| 扩展点 | 注册什么 | 内核侧落到哪 |
|---|---|---|
| `register_tool(tool)` | 一个 `ToolPlugin` | 工具注册表（执行仍走同一条管道） |
| `set_subagent_tools(tools)` | 本插件向子智能体暴露的工具名清单 | 子智能体模型工具视图；空清单表示全部不暴露 |
| `add_executor(name, fn)` | 写类工具的提交执行器 | `ExecutorRegistry`（`commit_write` 提交时按名取） |
| `subscribe(event_type, handler)` | 事件处理 `handler(event)` | 事件总线 |
| `add_context_source(fn, meta?)` | 上下文注入源 | `ContextSources`（见下节） |
| `add_mode_tail(fn)` | 执行模式与 Todo 之后的请求尾部文本 | `PromptTail`（见「请求尾部」） |
| `add_prompt_section(section, fn)` | 系统提示词章节正文 | `PromptSections`（同章节合并） |
| `add_pre_gate(gate)` | 工具执行前门控 | 工具管道 |
| `add_post_observer(obs)` | 工具执行后观察 | 工具管道 |
| `add_route(method, path, handler)` | HTTP 端点 | `/api/plugin/<插件名>/…` |
| `add_panel(id, ...)` / `add_action(id, ...)` | 面板 / 输入区按钮 | 贡献注册表（壳层按数据枚举） |
| `add_ctx_segment_style(label=..., color=...)` | 上下文段外观 | 贡献注册表 → `/api/ctx-segment-styles` |
| `add_boot_script(rel_path)` | 开屏预载脚本（无面板也可） | 贡献注册表 → `/api/boot-scripts` |
| `add_model_catalog(entries)` | 模型清单（静态序列或热读回调） | `ModelCatalog`（唯一权威来源） |
| `set_runtime(obj)` | 自己的运行时实例 | `plugin_host.runtime(名字)` 取同一份 |

### 上下文注入

```python
ctx.add_context_source(fn)   # fn(conversation_id: str) -> list[str]
```

管线每一步组装请求时调用，产出的文本刷进上下文的插件段。**按会话**给内容 ——
同一个插件对不同会话可以注入不同东西。

带描述时同时声明这一段在界面上的身份与主体数量：

```python
ctx.add_context_source(
    runtime.build_system_messages,
    {"label": "示例来源",                   # 段名，界面显示
     "prefix": "【示例：a.md】\n",           # 注入前缀，标明这段是什么
     "count": runtime.attached_count},     # fn(cid) -> int，主体数量
)
```

自报的 `count` 与返回的正文**逐条对齐**：一个来源返回多条正文时只有第一条带自报数，
其余按条数算；内核按位置取值，不会拿别的段的数字补位。

- `label` 缺省用插件名；
- `prefix` 由来源给，宿主在收集时统一拼上；
- `count` 是界面显示“几个主体”用的取数口；不给时，有正文的段按 1 计，空段按 0 计；
- 段 key 一律是**插件名**（`plugin:<插件名>`），一个插件可以注册多个来源，
  它们共用这个 key、各占一行（key 与段名都相同的行会合并）；
- 组装位次由宿主按清单位次写入，插件不需要声明。

一个插件注册多条注入源的例子见 `plugins/skills`：清单一条、常驻正文一条；
资源目录走系统提示词章节，不占独立上下文段。

### 系统提示词章节

```python
ctx.add_prompt_section("## 资源目录", fn)
```

`fn(conversation_id) -> str | list[str]` 返回章节正文；`section` 是完整标题（含 `## `）。
同一标题可由多个插件注册，正文按插件清单位次合并，标题只出现一次。章节进入系统提示词，
不产生 `CHUNK_PLUGIN` 段；来源异常或空正文跳过。

### 工具

```python
class MyTool(ToolPlugin):
    name = "my_tool"
    description = "……"
    label = "示例工具"      # 界面上的短名
    icon = "🧰"            # 界面图标（一个字符）
    parameters = {...}
    def execute(self, arguments): ...

def register(ctx):
    return [ctx.register_tool(MyTool())]
```

`label` / `icon` 是**界面展示信息，由工具自己声明**：页面经 `/api/tool-labels`
认识所有工具（含插件工具），不必在前端维护一张工具名表 —— 否则每加一个插件工具
都得去改界面。

工具进内核注册表，与内置工具走**同一条执行管道**：门控、确认流程、写盘四步协议
都照旧。插件不能绕过管道。

**工具只在插件装载时存在**：插件注册的工具随 `[plugin:<名字>]` 节移除而消失。

### 写类工具的提交执行器

走 `confirm_id` 制预览的写类工具，提交那一刻由 `commit_write` 按工具名取执行器：

```python
ctx.add_executor("my_tool", my_executor)   # my_executor(arguments) -> dict
```

用注册表而不是装配期传入的静态表：**登记发生在插件装载时，取用发生在工具调用时**，
两者顺序无关；插件多装一个，不需要改内核装配代码。

### 事件订阅

```python
ctx.subscribe(ev.TURN_ENDED, handler)   # handler(event) -> None
```

事件名见 `agent/core/event_name.py`（`ev.*`）与 [architecture.zh.md](../architecture.zh.md)
的事件协议。订阅是观察，不改控制流。

### 工具管道门控与观察

```python
ctx.add_pre_gate(gate)       # gate(call, ctx) -> GateDecision | None
ctx.add_post_observer(obs)   # obs(call, result, ctx) -> None
```

`pre` 在工具执行前跑，返回 `GateDecision(allow=False, reason=...)` 即拒绝；
`post` 在执行后跑。**门控只可加检查，不可减保证** —— 插件能拦下更多，
不能把内核原有的检查放过去。

### HTTP 端点

```python
ctx.add_route("GET", "tasks", list_tasks)          # -> /api/plugin/<插件名>/tasks
ctx.add_route("GET", "tasks/:sid", get_task)       # 路径参数按位置取值
ctx.add_route("PUT", "checked", put_checked)
ctx.add_route("DELETE", "tasks/:sid", drop_task)
```

`handler(args)` 返回 `(status, payload)`；`payload` 是 dict / list 时按 JSON 返回
（list 会包成 `{"ok": true, "items": [...]}`）。`args` 是**查询串 + 路径参数 + 请求体**
（有体时在 `body` 键下）。

支持 `GET` / `POST` / `PUT` / `DELETE`。路径挂在 `/api/plugin/<插件名>/` 命名空间下，
除 `:名字` 参数段外**不做通配**：路径必须与声明的形状逐段相等，段数也要相等 ——
「某插件挂了哪些端点」因此永远可枚举、可审计。

### 界面

```python
ctx.add_panel("notes", title="便签", html="<div id='notes'></div>",
              script_file="ui/panel.js", css_file="ui/panel.css", pinned=False)
ctx.add_action("notes", label="🗒 便签", title="便签")   # 输入框下面一个按钮，点了开同名面板
```

面板进右栏的标签容器，与「步骤」栏并列。标题就是标签上的字，面板里不再有标题行。
`pinned=True` 的面板不显示关闭按钮。

角色分工：

| 谁 | 负责 |
|---|---|
| 插件 | 面板的 HTML 片段、脚本、样式；内容怎么渲染 |
| 壳层 | 标签容器、按数据枚举、把资产按路径送达、同源注入 |

## 子智能体工具可见性

插件通过 `ctx.set_subagent_tools([...])` 声明自己的工具清单：

```text
不调用：本插件工具对子智能体全部可见
传空列表：本插件工具对子智能体全部不可见
传工具名列表：只有列表中的工具对子智能体可见
```

内核只按清单过滤子智能体的模型工具视图，不复制注册表，也不按插件名写分支。
父会话视图不受影响。工具仍保留在注册表里；重新声明清单即可再次改变可见性。

插件还可以用 `ctx.is_subagent(cid)` 判断当前会话角色，决定是否注入请求尾部文本。
`ai_speak` 声明空清单，并以 `subagent_visible=False` 注册语音提示尾部，
该尾部不会渲染进子智能体请求。

## 请求尾部

`ctx.add_mode_tail(fn, *, subagent_visible=True)` 注册 `fn(conversation_id) -> str`。
文本拼在执行模式与 Todo 进度之后，只进入当前请求尾部，不进入系统提示词前缀；
插件装卸只改变尾部，系统提示词前缀不变。空串不占位，异常来源被隔离。

## 界面资产

面板可以带自己的样式与脚本，声明的是**插件目录内的相对路径**；壳层按
`/api/plugin/<插件名>/_asset/<相对路径>` 送达，**目录根取自**
`plugin_host.plugin_root(插件名)`（清单 `path=` 指向的外部目录同样适用）。
路径是相对的、不含 `..`；只有文本类扩展名（`.js` `.mjs` `.css` `.html` `.json` `.svg`）
会送出去。类名带自己的前缀；样式是同源注入的，没有沙箱隔离。

面板脚本加载后，用壳层给的客户端调**自己的**端点，不必知道 URL 前缀：

```js
const api = window.aiAgentPlugins.for(window.aiAgentPluginCurrent);
const res = await api.get("files");                       // GET  /api/plugin/<插件名>/files
await api.post("generate", { prompt: "..." });            // POST 同上
await api.put("checked", { conversation_id, checked });
await api.del("tasks/t-1");                               // DELETE
```

`res` 形状是 `{ status, ok, data }`。`api.url(path)` 只拼地址、不发请求。

### 脚本的加载时机

**上下文段外观**经 `add_ctx_segment_style` 登记，壳层开屏拉
`/api/ctx-segment-styles` 并调用 `ctxSegments.register` —— 不必为段色单独挂空面板脚本。

**面板脚本**在开屏时依次预载（`preloadPluginScripts()`），**样式在面板首次打开时注入**。
样式只在面板打开时才需要，提前注入等于给每个页面加载用不到的字节。

**开屏脚本**经 `add_boot_script(rel_path)` 登记（如工具卡视图），壳层开屏拉
`/api/boot-scripts`，在面板脚本之后预载 —— 无面板也能注入 JS。

预载是**串行**的：脚本读全局 `window.aiAgentPluginCurrent` 判断自己属于哪个插件，
并行加载会互相覆盖这个值。

面板脚本在面板 DOM 存在之前就已预载，因此壳层每次打开面板都会派发
`ai-agent:panel-opened`；面板脚本在该事件里渲染。

### 壳层公共桥

插件在**面板之外**（输入区、页头）放置 UI 时，用壳层桥而不是自己拼 URL、
不读壳层内部变量、不碰 `document.head`：

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

插件变更不需要刷新页面：壳层重新加载面板、动作、段色与开屏脚本，关闭已卸载插件的
面板，并清掉脚本与样式缓存，使重新启用的插件再次执行脚本。

### 会话切换通知

面板内容带会话级状态时（如勾选），会话一换就要重取。壳层广播一个通用事件，
**谁需要谁订阅**：

```js
document.addEventListener("ai-agent:conversation-changed", function () {
  if (document.getElementById("kbBody")) render();
});
```

壳层不点名任何插件，也不要求插件认识壳层。

## 插件拥有的资源

| 资源 | 怎么拿 | 说明 |
|---|---|---|
| 专属数据目录 | `ctx.data_dir` | `<数据根>/plugin/<插件名>/`，首次访问自动创建 |
| 内核 App | `ctx.app` | 取内核已注册的服务，如 `ctx.app.registry` / `ctx.app.mesh`；装配完成前为 `None` |
| 自己的运行时 | `ctx.set_runtime(obj)` | 登记出来，供壳层按名字取同一份实例 |
| 清单位次 | 宿主自动写入 | 组装顺序用，插件看不到也不必管 |

`ctx.data_dir` 让插件**只看到自己那一层**，不必知道外层目录在哪。各插件的目录互相
隔离，同名文件不会撞。状态放这里而不是放插件目录里：插件目录是代码，数据根是数据。

`ctx.app` 只在**处理器内部**用，不在 `register` 里用：插件在装配末尾加载，那时 App
还没交到宿主手上；而处理器是请求来了才被调用。`ctx.set_runtime` 在 `register` 中调用。

## 生命周期

```
discover     扫插件根目录，找 <名字>/plugin.py    —— 枚举磁盘上有哪些插件
load         按 plugins.ini 逐项装载：importlib 以动态模块名加载 → register(ctx)
             装配末尾调用 —— 那时内核服务都已注册，处理器才能取到 ctx.app
unload       逆序调用 disposer；再按插件名清一遍贡献、撤运行时、删模块缓存
```

发现阶段跳过以 `_` / `.` 开头的目录。

`importlib` 的动态模块名意味着壳层 `import` 不到同一个模块对象。插件要把自己持有的
运行时交给壳层操作，必须 `ctx.set_runtime(obj)`，壳层用 `plugin_host.runtime("<插件名>")`
取**同一个实例**；不登记就会出现两边各持一份状态。

卸载兜底会按插件名把面板、动作、端点、段色与开屏脚本全部撤掉。事件订阅由
`ctx.subscribe` 登记的 disposer 撤销。

## 模型目录来源

`add_model_catalog(entries)` 把一组模型条目交给内核的 `ModelCatalog`。条目是
`ModelEntry`（`id` / `provider` / `label` / `options` / `is_default`），
`base_url` / `api_key` / `model` 这类厂商相关键放在 `options` 里。内核按请求里的
id 取对应实例；未命中的 id 直接报错，不会静默路由到别的模型。

目录是模型路由的唯一权威来源（在其插件装载期间）；没有有效条目时模型清单为空。
条目构造由插件负责，内核负责规范化、校验与消费快照。只允许一个来源：第二个来源
被拒绝并留痕，插件仍可装载。

`multi_model` 是该扩展点的实现，配置与行为见 [multi-model.md](multi-model.zh.md)。

## 内置插件示例

| 插件 | 注册了什么 | 形态 |
|---|---|---|
| `plugins/skills` | `skills` 工具 + 两条注入 + 系统提示词章节 + 段色 + 开屏工具卡脚本 | 无面板；上下文段 + boot script；见 [skills.md](skills.zh.md) |
| `plugins/rules` | 一条注入（`.md` 一文件一条）+ 系统提示词章节 + 段色 | 无面板、无配置、无端点；见 [rules.zh.md](rules.zh.md) |
| `plugins/knowledge` | 注入 + 面板 + 输入区按钮 + 段色 + 三个端点 | 注入、面板、动作、端点四类都有，状态落 `ctx.data_dir`；见 [knowledge.md](knowledge.zh.md) |
| `plugins/multi_model` | 模型目录 + 只读 `/catalog` + 开屏下拉脚本 | 每条模型自带网关与厂商；见 [multi-model.md](multi-model.zh.md) |
| `plugins/visual_operator` | 四个工具（截屏 / 鼠标 / 键盘 / 等待）+ 平台后端 + 输入锁 | 按平台装配后端，不可用时在执行时报错而不是消失；见 [visual-operator.md](visual-operator.zh.md) |
| `plugins/ai_speak` | `ai_speak` 工具 + 两个只读端点 + 播放确认端点 + 两个开屏脚本 + 两个事件订阅 + 语音尾部 | 后端合成、前端播放条；见 [ai-speak.md](ai-speak.zh.md) |

各插件的配置与行为写在各自的子系统文档里，这里只描述它们用到的扩展点。

## 边界

### 插件信任模型

**插件与本机代码同等信任。** 装载后的 `plugin.py` 跑在同一进程、同一解释器里：
能读整个磁盘、能发网络请求、能注册工具与 HTTP 端点；面板的 HTML 片段与脚本注入到
页面同源上下文里。**没有沙箱。**

因此：

| 能指望 | 不能指望 |
|---|---|
| 约定与命名空间约束（端点前缀、资产路径校验） | 恶意/被篡改插件被运行时拦住 |
| 装载期在日志里记录来源路径与入口文件摘要（sha256 前缀 / mtime / bytes） | 子进程隔离或权限降级（见 [评估笔记](../adr/plugin-subprocess-isolation.zh.md)） |
| 开关打开时拒绝对 `plugins/` 树外的路径装载 | 对「受信目录里的坏代码」自动免疫 |

信任边界由三项约束维持：

- `plugins.ini` 与各插件目录一并纳入版本控制或部署清单；
- `[agent] plugin_tree_only = 1`（或环境变量 `AI_AGENT_PLUGIN_TREE_ONLY=1`）把装载范围
  限制在 `plugins/` 树内；
- 装载日志形如 `[plugin.load] <名> source=… sha256=… mtime=… bytes=…`，可与部署哈希对照。

界面与端点侧的约定：

- 界面资产的类名带自己的前缀，样式同源注入；
- 端点注册限于 `/api/plugin/<插件名>/` 命名空间，内核路由不开放注册；
- 面板的数据由插件自己的端点提供；
- 渲染相关信息（段名与段色、工具名与图标）由插件声明并由壳层下发，
  布局归壳层。服务端只给数据（段 key / 段名 / 计数）；插件界面脚本负责自己的
  面板与注入内容的渲染。

## 接入新插件

1. **建目录**：`plugins/<名字>/`，目录名即插件名，也是 `plugins.ini` 里的节名后缀。
   名字必须匹配 `[A-Za-z0-9][A-Za-z0-9_-]*`。
2. **写入口**：`plugin.py` 暴露 `register(ctx)`。最小实现只注册一项能力：

   ```python
   def ping(args):
       return 200, {"ok": True}

   def register(ctx):
       ctx.add_route("GET", "ping", ping)
   ```

   需要拆文件时用同目录模块，以相对导入引用（`from .library import Thing`）。
3. **建元数据与表单**：`plugin-meta.json` 声明 `name` / `desc` / `icon` / `version`；
   需要结构化表单时加 `settings-schema.json`，声明 `kind` 与 `fields`（`sections`
   还要 `section_prefix` / `identity`）。无敏感信息的 `plugin-config.ini` 入库；
   含密钥的插件配置由 `.gitignore` 排除。
4. **登记界面**（可选）：面板、输入区动作、开屏脚本、段色分别用
   `add_panel` / `add_action` / `add_boot_script` / `add_ctx_segment_style` 注册；
   资产放插件目录内，经 `/api/plugin/<名字>/_asset/<相对路径>` 送达。
5. **加清单**：在 `plugins.ini` 写一节 `[plugin:<名字>]`，可带 `path` / `enabled`。
   节在即进入装载候选，实际是否装载看 `enabled`。
6. **校验**：`python scripts/ci.py` 覆盖依赖方向、架构约束、注释文案与单测；
   插件的端点与界面由 `scripts/acceptance_web.py` 一类的验收脚本覆盖。

## 延伸阅读

- [上下文管理](context.zh.md)：注入源如何进入装配、组装顺序怎么定
- [知识库](knowledge.zh.md)：`knowledge` 的文件收录、勾选与注入
- [多模型](multi-model.zh.md)：`multi_model` 的目录条目与设置页表单
- [Skills](skills.zh.md)：`skills` 插件的三层披露与 `skills` 工具
- [Visual Operator](visual-operator.zh.md)：`visual_operator` 的截屏、坐标契约与平台后端
- [工具](tools.zh.md)：工具的注册、执行管道与写盘协议
- [壳层](shell.zh.md)：HTTP 路由与界面打包
- [配置](../guide/config.zh.md)：配置项全表
