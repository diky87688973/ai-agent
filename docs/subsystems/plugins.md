# 插件

插件是内核之外的能力扩展点：工具、事件订阅、上下文注入、工具管道门控、写类工具的
执行器、HTTP 端点与界面，都由插件声明。**内核不认任何具体插件** —— 它只提供贡献
注册表与 HTTP 转发。

内置能力也走这条路：知识库与 Skills 都是插件，从 `plugins.ini` 里去掉对应节，
它们的注入源、工具、面板、按钮、端点一起消失，内核不受影响。

## 包

插件是 `plugins/` 下的一个目录，目录名即插件名，也是清单里写的名字：

```
plugins/<插件名>/
  plugin.py        必须。唯一入口，暴露 register(ctx)
  plugin-config.ini  可选。插件自己的配置（不入库，只入库 plugin-config.ini.example）
  ui/              可选。面板的样式与脚本
  <其它文件>        可选。插件自己的数据文件、库、模板
```

最小形态是只有一个 `plugin.py` 的目录。`plugins/tts` 就是这样：它只订阅事件，
不注册工具也不贡献界面。

`register(ctx)` 返回 disposer 或 disposer 列表。**每个 `ctx.add_*` 都会返回 disposer**，
且宿主在调用时已自动 `append` 进本插件清单（含 `add_panel` / `add_route` / `add_action` /
`add_boot_script` / `add_ctx_segment_style` 等）——返回值只为幂等记账；卸载时逆序调用。
`register` 抛错时经 `ctx` 完成的注册全部回滚，插件不会留半截状态。

插件可以把实现拆成同目录的多个模块（`plugins/skills/library.py`、`tools.py`），
用绝对包名导入自己那部分：

```python
from .library import SkillManager
```

## 清单：`plugins.ini`

工程根的 `plugins.ini` 列出插件。节在就进入装载候选。开或关、卡片上一句话写在该插件自己的 `plugin-config.ini`。

```ini
[plugin:skills]
version = 1.0

[plugin:knowledge]
version = 1.0

[plugin:local-lab]
path = D:/lab/my-plugin
```

| 字段 | 必填 | 说明 |
|---|---|---|
| 节名 | 是 | 固定 `[plugin:<名字>]`。名字即模块名后缀与默认目录名 |
| `version` | 否 | 插件版本。与该插件 `plugin-config.ini` 的 `[base] version` 核对，不一致记一条加载报告（**照常装载**） |
| `path` | 否 | 插件目录（可在 `plugins/` 外）。相对路径按插件根解析；空则 `plugins/<名字>`。装载后资产与配置一律经宿主的 `plugin_root(名字)`，不写死 `plugins/<名字>` |

**节的先后有意义**：它就是插件的装载位次，也是**上下文里插件段的组装顺序**
（见 [context.md](context.md#组装顺序)）。越不容易变动的插件排在越前面。

`plugins.ini.example` 是模板，默认什么都不列（= 不装载任何插件）。

配置错了要看得见：名字非法、目录不存在、缺 `plugin.py` 都会记一条 `error` 报告，
不阻断启动，也不会静默当没写。

## 插件自己的配置

插件自己的配置放**插件自己目录下的 `plugin-config.ini`**。`[base]` 每个插件都有，
`[ext]` 只放这个插件自己的键。插件用 `agent.config.load_ini()` 读 `[ext]`：

```
plugins/knowledge/plugin-config.ini     ← 知识库自己的配置
plugins/skills/plugin-config.ini        ← Skills 自己的配置
plugins/tts/plugin-config.ini           ← 语音合成自己的配置
```

**内核的 `config.ini` 只含内核设置，不放任何插件设置。** 插件的设置在插件自己
目录下，随插件一起装卸、一起删除。
每个插件目录下配有 `plugin-config.ini.example` 作模板；配置文件本身不入库。

文件名固定是 `plugin-config.ini`（不是 `config.ini`）——`config.ini` 这个名字专指
内核配置，同名两份文件必然会有人改错那一份。`[base]` 固定，`[ext]` 由插件自己定。

| 插件 | 配置文件 | `[base]` | `[ext]` |
|---|---|---|---|
| `knowledge` | `plugins/knowledge/plugin-config.ini` | `id`、`name`、`desc`、`enable`、`icon`、`version` | `dir`、`max_file_size`、`extra_suffixes` |
| `skills` | `plugins/skills/plugin-config.ini` | 同上 | `dir`、`max_file_size` |
| `tts` | `plugins/tts/plugin-config.ini` | 同上 | `engine`、`voice`、`max_segment_chars` |

`enable`：`1` 装载，`0` 留在清单里但不装载。没写时按 `1`。设置页的开关写的就是这一项。
`name` / `desc` / `icon` 是设置页卡片上的展示名、一句话和图标。`version` 与 `plugins.ini` 里的 `version` 核对。

插件自己的键由插件自己读、自己解释：内核不解析插件配置，`agent/config.py` 里
没有任何插件节的读取口。`dir` 一类的相对路径按**工程根**解析（不是按插件目录），
与内核配置保持同一口径。
插件的定位不依赖内核 API：`Path(__file__).resolve().parent` 就是插件目录。

权限边界要说清：`plugin-config.ini` 存的是密钥这类敏感值，同机进程读得到它就能读插件配置。
这与「插件与本机代码同等信任」是同一条边界（见下文）。

## 扩展点全表

`PluginContext` 上所有 `add_*` 都返回幂等 disposer。

| 扩展点 | 注册什么 | 内核侧落到哪 |
|---|---|---|
| `register_tool(tool)` | 一个 `ToolPlugin` | 工具注册表（执行仍走同一条管道） |
| `add_executor(name, fn)` | 写类工具的提交执行器 | `ExecutorRegistry`（`commit_write` 提交时按名取） |
| `subscribe(event_type, handler)` | 事件处理 `handler(event)` | 事件总线 |
| `add_context_source(fn, meta?)` | 上下文注入源 | `ContextSources`（见下节） |
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

带描述时同时声明这一段在界面与顺序上的身份：

```python
ctx.add_context_source(
    runtime.build_system_messages,
    {"label": "知识库",                    # 段名，界面显示
     "prefix": "【知识库：a.md】\n",         # 注入前缀，告诉模型这段是什么
     "count": runtime.attached_count},     # fn(cid) -> int，主体数量
)
```

自报的 `count` 与返回的正文**逐条对齐**：一个来源返回多条正文时只有第一条带自报数，
其余按条数算；内核按位置取值，不会拿别的段的数字补位。
```

- `label` 缺省用插件名；
- `prefix` 由来源给，宿主在收集时统一拼上；
- `count` 是界面显示"几个主体"用的取数口；不给就按消息条数算；
- 段 key 一律是**插件名**（`plugin:<插件名>`），一个插件可以注册多个来源，
  它们共用这个 key、各占一行；
- 组装位次由宿主按清单位次写入，插件不需要声明。

一个插件注册两条以上的例子见 `plugins/skills`：清单一条、常驻正文一条。

### 工具

```python
class MyTool(ToolPlugin):
    name = "my_tool"
    description = "……"
    label = "我的工具"      # 界面上的中文短名
    icon = "🧰"            # 界面图标（一个字符）
    parameters = {...}
    def execute(self, arguments): ...

def register(ctx):
    return [ctx.register_tool(MyTool())]
```

`label` / `icon` 是**界面展示信息，由工具自己声明**：页面经 `/api/tool-labels`
认识所有工具（含插件工具），不必在前端维护一张工具名表 ——
否则每加一个插件工具都得去改界面。

工具进内核注册表，与内置工具走**同一条执行管道**：门控、确认流程、写盘四步协议
都照旧。插件不能绕过管道。

**工具只在插件装载时存在**：`skill_manage` 由 Skills 插件注册，把 `[plugin:skills]`
从清单里去掉，它就不在工具清单里。

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

事件名见 `agent/core/event_name.py`（`ev.*`）与 [architecture.md](../architecture.md)
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

`handler(args)` 返回 `(status, payload)`；`payload` 是 dict / list 时按 JSON 返回。
`args` 是**查询串 + 路径参数 + 请求体**（有体时在 `body` 键下）。

支持 `GET` / `POST` / `PUT` / `DELETE`。路径挂在 `/api/plugin/<插件名>/` 命名空间下，
除 `:名字` 参数段外**不做通配**：路径必须与声明的形状逐段相等，段数也要相等 ——
「某插件挂了哪些端点」因此永远可枚举、可审计。

### 界面

```python
ctx.add_panel("kb", title="知识库", html="<div id='kb'></div>",
              script_file="ui/panel.js", css_file="ui/panel.css", pinned=False)
ctx.add_action("kb", label="📚 知识库", title="知识库")   # 输入框下面一个按钮，点了开同名面板
```

面板进右栏的标签容器，与「步骤」栏并列。标题就是标签上的字，面板里不再有标题行。
`pinned=True` 的面板不显示关闭按钮。

角色分工：

| 谁 | 负责 |
|---|---|
| 插件 | 面板的 HTML 片段、脚本、样式；内容怎么渲染 |
| 壳层 | 标签容器、按数据枚举、把资产按路径送达、同源注入 |

#### 界面资产

面板可以带自己的样式与脚本，声明的是**插件目录内的相对路径**；
壳层按 `/api/plugin/<插件名>/_asset/<相对路径>` 送达，**目录根取自**
`plugin_host.plugin_root(插件名)`（清单 `path=` 指向的外部目录同样适用）。
路径不许绝对、不许含 `..`；只有文本类扩展名（`.js` `.mjs` `.css` `.html` `.json` `.svg`）
会送出去。类名要加自己的前缀 —— 样式是同源注入的，没有沙箱隔离。

面板脚本加载后，用壳层给的客户端调**自己的**端点，不必知道 URL 前缀：

```js
const api = window.aiAgentPlugins.for(window.aiAgentPluginCurrent);
const res = await api.get("files");                       // GET  /api/plugin/<插件名>/files
await api.post("generate", { prompt: "..." });            // POST 同上
await api.put("checked", { conversation_id, checked });
await api.del("tasks/t-1");                               // DELETE
```

`res` 形状是 `{ status, ok, data }`。`api.url(path)` 只拼地址、不发请求。

#### 脚本的加载时机

**上下文段外观**经 `add_ctx_segment_style` 登记，壳层开屏拉 `/api/ctx-segment-styles`
并调用 `ctxSegments.register` —— 不必为段色单独挂空面板脚本。

**面板脚本**在开屏时依次预载（`preloadPluginScripts()`），**样式在面板首次打开时注入**。
样式只在面板打开时才需要，提前注入等于给每个页面加载用不到的字节。

**开屏脚本**经 `add_boot_script(rel_path)` 登记（如工具卡视图），壳层开屏拉
`/api/boot-scripts`，在面板脚本之后预载 —— 无面板也能注入 JS。

预载是**串行**的：脚本读全局 `window.aiAgentPluginCurrent` 判断自己属于哪个插件，
并行加载会互相覆盖这个值。

#### 壳层公共桥

插件在**面板之外**（输入区、页头）放置 UI 时，用壳层桥而不是自己拼 URL、
不读壳层内部变量、不碰 `document.head`：

```js
// 模型：list() → Promise<[{id,label,provider}]>；current() → string；
// select(id) → Promise<boolean>；onChange(fn) → 取消订阅函数。
const models = window.aiAgentShell.models;
const stop = models.onChange((id) => renderLabel(id));
await models.select("claude");
stop();

// 样式：relPath 是插件目录内相对路径；同一路径只注入一次。
window.aiAgentShell.styles.load("ui/model-picker.css");
```

`aiAgentShell` 与 `aiAgentPlugins` 平级：前者是壳层能力，后者是插件自己的端点。
桥本身**不持有当前模型** —— `current()` 每次读活动标签页，多份状态必然分叉。
`select()` 先乐观更新界面，再写 `/api/chat/ui-state` 并广播；写失败会回滚并返回
`false`。服务端下发的值（会话恢复 / SSE）不受本地清单限制。

`styles.load()` 复用面板样式的去重表与 `/api/plugin/<插件>/_asset/` 路由：
绝对路径、盘符、协议与 `..` 一律返回 `false` 并 `console.error`；插件停用后，
`applyPluginsChanged` 会摘掉带 `data-plugin-style` 的 `<link>`，并清掉
`#modelPickerSlot` 里 `data-plugin` 已不在装载名单的子元素。

**已知限制**：`loadPluginScript` 按 URL 去重，所以"停用 → 再启用"在不刷新页面的
前提下开屏脚本不会重跑，输入区的下拉也不会自动回来。插件变更后刷新页面。

#### 会话切换通知

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
| 自己的运行时 | `ctx.set_runtime(obj)` | 登记出来供壳层按名字取同一份实例 |
| 清单位次 | 宿主自动写入 | 组装顺序用，插件看不到也不必管 |

`ctx.data_dir` 让插件**只看到自己那一层**，不必知道外层目录在哪。各插件的目录互相
隔离，同名文件不会撞。状态放这里而不是放插件目录里：插件目录是代码，数据根是数据。

`ctx.app` 与 `set_runtime` 都在**处理器内部**用，不在 `register` 里用：
插件在装配末尾加载，那时 App 还没交到宿主手上；而处理器是请求来了才被调用。

## 生命周期

```
discover     扫插件根目录，找 <名字>/plugin.py    —— 枚举磁盘上有哪些插件
load         按 plugins.ini 逐项装载：importlib 以动态模块名加载 → register(ctx)
             装配末尾调用 —— 那时内核服务都已注册，处理器才能取到 ctx.app
unload       逆序调用 disposer；再按插件名清一遍贡献、撤运行时、删模块缓存
```

`importlib` 的动态模块名意味着壳层 `import` 不到同一个模块对象。插件要把
自己持有的运行时交给壳层操作，必须 `ctx.set_runtime(obj)`，壳层用
`plugin_host.runtime("<插件名>")` 取**同一个实例**；不登记就会出现两边各持一份状态。

卸载兜底会按插件名把面板、动作、端点、订阅全部撤掉。

## 模型与厂商

`multi_model` 把模型条目声明成目录来源，内核每轮按请求里的 id 路由到对应实例：

```ini
[model:claude]
provider = anthropic
base_url = https://api.anthropic.com
api_key = sk-ant-…
model = claude-sonnet-4-5
label = Claude Sonnet 4.5
max_tokens = 16000
thinking = 1
thinking_budget_tokens = 4096
```

- 节名 `[model:<id>]`；`id` 是请求与界面里的唯一标识，`model` 缺省等于 `id`；
- `provider` 缺省 `openai`；未知厂商、缺 `api_key` / `base_url` 只会让该条目无效；
- `default = 1` 至多一个，没有时取第一条；重复 id 由目录整批拒绝；
- `thinking` / `max_tokens` / `thinking_budget_tokens` 只对 anthropic 条目生效；
- 配置用 `utf-8-sig` 读，Windows 记事本的 BOM 不会让服务起不来；
- 诊断格式：`[plugin:multi_model] <文件> [model:<id>] <键> 无效：<原因>`。

目录权威只在**存在有效条目**时成立：启用插件但一条都没配好，会回落到
`config.ini` 的 `[model_reasoning]`；两处都没有凭据时启动即失败。
`GET /api/plugin/multi_model/catalog` 返回 `{models, default, invalid}`，
**不含** `api_key` 与 `base_url`。设置页在目录权威时隐藏「模型」节，
条目改完下一次请求生效，不需要重启。



## 内置插件示例

| 插件 | 注册了什么 | 形态 |
|---|---|---|
| `plugins/skills` | `skill_manage` 工具 + 提交执行器 + 两条注入 + 开屏工具卡脚本 | 无面板；上下文段 + boot script；见 [skills.md](skills.md) |
| `plugins/knowledge` | 注入 + 面板 + 输入区按钮 + 三个端点 | 四件套齐全，状态落 `ctx.data_dir` |
| `plugins/multi_model` | 模型目录 + 只读 `/catalog` + 开屏下拉脚本 | 每条模型自带网关与厂商；见 [模型与厂商](#模型与厂商) |
| `plugins/tts` | 只订阅事件 | 最小形态 |

Skills 插件的实现拆在三个文件里，可作"插件怎么组织代码"的例子：

```
plugins/skills/plugin.py     入口：读配置、装配 Skills 库、注册工具与两条注入
plugins/skills/library.py    Skills 库：扫描 / 元数据 / 读取 / 复制计划
plugins/skills/tools.py      skill_manage 工具与其执行器
```

## 边界

### 插件信任模型

**插件与本机代码同等信任。** 装载后的 `plugin.py` 跑在同一进程、同一解释器里：
能读整个磁盘、能发网络请求、能注册工具与 HTTP 端点；
面板的 HTML 片段与脚本注入到页面同源上下文里。**没有沙箱。**

因此：

| 能指望 | 不能指望 |
|---|---|
| 约定与命名空间约束（端点前缀、资产路径校验） | 恶意/被篡改插件被运行时拦住 |
| 装载期记录来源路径与入口文件摘要（sha256 / mtime） | 子进程隔离或权限降级（见 [评估笔记](../adr/plugin-subprocess-isolation.md)） |
| 开关打开时拒绝对 `plugins/` 树外的路径装载 | 对「受信目录里的坏代码」自动免疫 |

运营建议：

- 只装载自己审查过的插件；`plugins.ini` 与各插件目录一并纳入版本控制或部署清单
- 需要收紧外置 `path` 时：配置 `[agent] plugin_tree_only = 1`，或环境变量 `AI_AGENT_PLUGIN_TREE_ONLY=1`
- 装载日志形如 `[plugin.load] <名> source=… sha256=… mtime=… bytes=…`，便于对照部署哈希

因此约束落在约定上：

- 界面资产的类名加自己的前缀，样式是同源注入的
- 端点注册限于 `/api/plugin/<插件名>/` 命名空间，内核路由不开放注册
- 面板的数据由插件自己的端点提供
- 渲染相关的信息（颜色、图标、布局）由插件的界面脚本自己注册，
  不经过服务端 —— 服务端只给数据（段 key / 段名 / 计数）

## 写一个插件

从 `plugins/knowledge` 抄起：它有完整的四件套 —— 注入源、面板、动作、端点，
并且状态落在 `ctx.data_dir`。`plugins/skills` 是另一半形态：只有工具与注入，
没有界面。`plugins/tts` 是最小形态：只订阅事件。

## 延伸阅读

- [上下文管理](context.md)：注入源怎么进上下文、组装顺序怎么定
- [Skills](skills.md)：`skills` 插件的三层披露与 `skill_manage`
- [工具](tools.md)：工具的注册、执行管道与写盘协议
- [壳层](shell.md)：HTTP 路由与界面打包
- [配置](../guide/config.md)：配置项全表
