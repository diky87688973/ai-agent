[English](shell.md) | **中文**

# 壳层

`agent/shell/` 是 L3 层，把内核包成可运行的服务与界面。

| 文件 | 职责 |
|---|---|
| `web/server.py` | HTTP + SSE 服务装配与启动；鉴权运行时注入 |
| `web/web_routes.py` | HTTP 动词与路径分派 |
| `web/web_auth.py` | 鉴权中间层：Host、身份与 CSRF 校验 |
| `web/auth/` | 密码、登录会话、API Token、CSRF、限流、审计与路由策略 |
| `web/web_static.py` | 静态资源、路径与协议常量 |
| `web/web_classic.py` | 经典页面与经典 SSE |
| `web/web_plugin.py` | 插件端点与插件资产转发 |
| `web/web_api.py` | WebShell 入口、SSE 连接与运行态 |
| `web/web_chat.py` / `web/web_sessions.py` / `web/web_files.py` / `web/web_contributions.py` / `web/web_subagents.py` / `web/web_state.py` | WebShell 的聊天、会话、文件、贡献、子智能体与 UI 状态动作 |
| `sse.py` | SSE 传输层 |
| `session/runner.py` | 回合调度、取消、队列抽干与生命周期 |
| `session/queue.py` | 队列领取、释放与落盘补投 |
| `session/goal.py` | 目标与自主续跑判定 |
| `session/prompt.py` | 系统提示与运行态尾部 |
| `session/resume.py` | 外部工具结果恢复 |
| `session/heartbeat.py` | 运行态心跳 |
| `prompts.py` | 系统提示词 |
| `environment_info.py` | 系统提示词的 `## 环境信息` 章节 |
| `web/ui_bundle.py` | 界面资源内联打包 |
| `web/web_ui_config.py` | `web-ui-config.ini` 的界面展示开关 |
| `settings_panel.py` / `settings_io.py` / `plugin_settings.py` / `plugin_editor.py` | 设置页宿主配置、INI 原语、插件配置与编辑视图 |
| `cli/interactive.py` | 交互式对话壳（命令行） |
| `cli/headless.py` | 无 UI 跑一个回合并打印事件流 |
| `fspaths.py` | 可见范围的来源、路径判界与展示形态 |
| `classic_adapter/` | 事件翻译、入站请求、历史回读、确认回路 |
| `web/web_assets/` | 壳层页面、样式与前端脚本 |

API Token 的 issue/revoke 使用进程内线程锁与 `tokens.json.lock` 跨进程文件锁；同名签发被拒绝，锁不可用时命令返回可读错误而不是堆栈。

## 用量与命中率的口径

**命中率只用官方返回值算**：每次模型调用后 API 在 `usage` 里给出
`prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`，内核原样落成 `usage` 事实、
适配层原样转发（字段名见 `classic_adapter/contract.py` 的 `SSE_USAGE_FIELDS`），
界面显示的命中率就是「命中 /（命中 + 未命中）」这两个官方值之比，不掺任何估算。

**上下文占用率的分母是模型窗口**（读模型条目的 `context_window`；适配层在下发的
`context_layout` 里带上 `model_max_context_tokens`），不是压缩阈值：阈值是触发压缩的预算，
窗口是物理上限。
窗口跟着会话当前模型走，换模型后下一回合的分母就换。目录没有给出该模型的窗口时，
界面回落到预算。

**分段浮层里的 token 是估算**：对装配后的消息求和，CJK 每字 1 token，其余每 4 字符 1 token，
图片按每图固定额度计。它与用量条里的官方 `prompt_tokens` 不是同一个数：
前者是「这一段大概多少」，后者是「这次实际花了多少」。

## 启动

```bash
python -m agent.entry.web --host 127.0.0.1 --port 8765
```

`agent/entry/web.py` 的 `main()` 解析参数、走鉴权命令行分支、装配 app，再调用 `serve()`；
`serve()` 启动鉴权、应用 TLS、打印地址并阻塞在 `serve_forever()`。

`create_server()` 返回 `(server, shell)`，不启动；`auth` 必须显式传入，缺 `AuthRuntime` 抛 `TypeError`。

`serve()` 接收已装配的 app，决定可见根、标题目录与工作目录的落点，然后阻塞运行。
`build_shell_app()` 是入口层的装配函数：未注入 provider 时建 `MissingProvider`，并建会话存储；
壳层不导入装配根。

缺少模型配置不阻断启动：服务以 `MissingProvider` 起来，页面可以打开，模型下拉为空。
保存插件配置会重载插件并调用 `app.refresh_model_config()`，按目录重算模型路由与清单；
多模型目录给出模型后即成为权威来源。

## HTTP 路由

### GET

| 路径 | 作用 |
|---|---|
| `/` | 单页界面 |
| `/health` | 健康检查：工具数、模型与允许清单、全局默认推理档位、SSE 连接数、暂停与待确认会话、内核名 |
| `/favicon.ico` | 站点图标 |
| `/assets/*` | 静态资源 |
| `/workspace/*` | 工作区文件（界面里图片视频的重写目标） |
| `/api/events/stream` | **SSE 事件流**（默认经典格式；`format=kernel` 透传内核事件） |
| `/api/chat/history` | 会话历史 |
| `/api/chat/sessions` | 会话列表（带日期分组） |
| `/api/chat/ui-state` | 会话状态：模式 / 模型与可选清单 / 推理档位 / 清单 / 目标 / 自主 / 在跑（带 `conversation_id`）；不带 id 时只回哪些会话在跑（不存客户端布局） |
| `/api/chat/attachment` | 附件内联读取 |
| `/api/fs/list` `/api/fs/read` | 右栏文件查看器 |
| `/api/dir-browse` | 目录浏览（`@` 补全用） |
| `/api/panels` `/api/actions` | 插件贡献的右栏面板与输入区动作清单 |
| `/api/ctx-segment-styles` `/api/boot-scripts` `/api/tool-labels` | 插件贡献的上下文段外观、开屏脚本、工具展示名与图标 |
| `/api/plugin/<插件>/<路径>` | 插件端点命名空间（按注册形状匹配，`:名字` 段按位置取参；`_asset/<相对路径>` 转发插件文件） |
| `/api/settings` | 设置页目录。密钥字段 `value` 恒为空，另给 `configured` 与 `placeholder` |
| `/api/settings/plugins` | 插件卡片：名字、描述、图标、版本、是否装载、是否可配置 |
| `/api/settings/plugin-file` | 某个插件的 `plugin-config.ini` 编辑视图；结构化表单的密钥字段只回是否已配置 |
| `/api/reasoning-effort` | 会话推理档位与全局默认 |
| `/api/chat/queue` | 当前会话的待发送队列快照 |
| `/api/usage-accumulator` | 用量累计 |
| `/api/media` | 媒体代理，路径限在显式媒体根内；未配置时用全部可见根 |
| `/api/subagents` `/api/subagents/history` | 子智能体清单与子会话历史 |
| `/api/background/tasks` | 后台任务快照或筛选清单 |
| `/api/update/status` `/api/update/logs` | 更新状态与日志尾部 |

### POST

| 路径 | 作用 |
|---|---|
| `/api/chat/send` | 发起一个回合；同会话在跑时进入待发送队列；可带 `draft_id` 重发已召回草稿 |
| `/api/chat/queue/<id>/insert` | 把队列消息标记为下一个安全模型趟插入；会话空闲时直接起一个回合 |
| `/api/chat/queue/<id>/recall` | 撤回队列消息并返回文本、图片与来源 |
| `/api/chat/stop` | 停止当前回合（协作式取消） |
| `/api/chat/user-confirm` | 提交用户确认：写盘确认、`user_confirm` 作答与审批（agree/reject）共用此端点 |
| `/api/chat/title` | 生成或读取已缓存的会话标题 |
| `/api/chat/autonomous` | 自主模式开关 |
| `/api/chat/goal` | 目标读写与 pause/resume/done/delete 状态切换 |
| `/api/chat/command-input` | 交互式命令的 stdin 输入 |
| `/api/subagents/send` | 向 UI 子会话发送输入 |
| `/api/background/tasks/create` `/cancel` `/output` | 后台任务创建、取消、取输出 |
| `/api/update/check` `/download` `/apply` | 更新检查、下载、应用（应用前拒绝存在后台任务或待发送消息的状态） |
| `/api/settings` | 写回宿主配置。密钥字段为空不写，有内容才覆盖文件里的原值 |
| `/api/settings/plugins` | 插件开关，写 `plugins.ini` 的 `enabled` 并立即装卸 |
| `/api/settings/plugin-file` | 写回某个插件的可编辑节，其余内容保留 |
| `/api/settings/pick-dir` | 弹出系统目录选择窗口（Windows） |

### DELETE

| 路径 | 作用 |
|---|---|
| `/api/chat/sessions` | 关闭会话并释放进程内运行态（不删事实日志） |
| `/api/chat/queue/<id>` | 取消一条未发送队列消息 |
| `/api/plugin/<插件>/…` | 插件端点 |

### PUT

`/api/chat/ui-state`、`/api/reasoning-effort`、`/api/usage-accumulator`，以及插件端点（`/api/plugin/<插件>/…`）。

写操作走 body、读操作走 query。鉴权端点（`/login`、`/desktop-login`、`/healthz`、`/auth/*`）由鉴权层在这些路由之前处理。

设置页从界面右上角打开，读写的是 `config.ini`、`web-ui-config.ini` 和各插件的 `plugin-config.ini`。
宿主表单与插件结构化表单里的密钥字段只允许覆盖：留空则文件里的值不动，有内容才替换。
`GET /api/settings` 不回明文，只说明是否已填写：已填写时占位提示为
`已设置秘钥,可重新设置并替换`，未填写时为 `未配置秘钥`。按文本编辑的插件直接显示
节内原文，包含已存的密钥值。

「保存」是保存并关窗（只有失败才留在窗口里），「应用」是保存但不关窗。插件配置的
身份与开关不在插件配置里；编辑区只覆盖插件自己的节。声明 `settings-schema.json` 的插件
按结构化表单编辑（`sections` 为可增删条目，如多模型；`fields` 为字段表单）；
没有 schema 的插件显示 `[config]` 正文且不露出节头；没有 `[config]` 时全部节都可编辑，
节数多于一个时才显示节头。
结构化表单里的密钥字段只回显「是否已配置」，留空表示沿用原值。

模型配置只由多模型插件维护；宿主设置页不提供内核模型节，也不写模型凭据。
插件装卸时由插件宿主刷新模型路由与清单。

## SSE 事件流

`/api/events/stream` 是界面看到的事实投影。它有两种格式：不带 `format` 或 `format=classic` 时
送适配层翻译后的经典帧，`format=kernel` 原样透传内核事件，供探针与其它交互层使用；
页面使用经典格式。

经典帧带 `conversation_id`，页面按会话分派；`heartbeat`、`global_sse_ready`、`plugins_changed`、
`settings_changed`、`plugin_config_changed` 这类心跳与进程级公告帧不带会话号；
`plugin_event` 帧的字段由插件决定。

由事实翻译出的帧带存储坐标，以 `id: <seq>` + `data: <json>` 两行发出。浏览器断线重连时经
`Last-Event-ID` 带回最后收到的坐标（非浏览器客户端可用 `?last_event_id=`），服务端补发该坐标
之后的事实，一次续传最多 512 条事实。没有游标就不回放：页面经 `/api/chat/history` 渲染已有内容，
中途打开的页面再经 `/api/chat/ui-state` 取权威忙闲。

每条连接各有一条有界队列；消费者慢时丢最旧帧，不阻塞广播。经典适配层只在至少一条连接存在时
订阅事件总线，最后一条断开时退订。

经典流的连接表由适配层持有，内核透传流的连接表由 `WebShell` 持有；断开时都从对应表里移除。
内核透传流只送新事件，不做重连续传，并在每次取帧前复核连接身份；登录会话或 Token
被撤销时关闭该流。

## 运行态与并发保护

`WebShell` 持一张 SSE 连接表与一张按会话的活跃回合表（`conversation_id → run_id`）。权威忙闲
来自运行态登记（见 [session.md](session.zh.md)）；`session_send` 工具判定目标忙闲也用这一事实源。
中途打开的页面据此显示停止键。经典流下，不带 `conversation_id` 的 GET 只回 `state.running`。

**客户端布局（打开过哪些标签、激活哪一个）存在浏览器 `localStorage`**：布局属于某一个浏览器，
服务端不提供也不接收。多个客户端各自激活不同会话时，服务端的一个全局字段会被后写者覆盖，
先写的刷新后被带到别人的会话。经典流的 `PUT /api/chat/ui-state` 接收请求但不存任何东西。

`/api/chat/send` 对同会话并发依据同一个登记进入待发送队列。

## 回合调度

`session/runner.py` 的 `SessionRunner` 在后台执行回合：用收到的输入构建引擎、跑模块链，
把事件发到事件总线（再进 SSE）；回合结束后抽干待发送队列，有待插入消息时起一个插入回合，
否则按目标与自主开关决定是否续跑。自动续跑最多 50 个回合。外部工具结果在回合前拼成
`tool_done` / `tool_failed` 与 `tool_ended`，按 `call_id` 查重。

心跳旁路线程每 60 秒续一次运行态登记，长工具调用期间不会被判为过期。任务结束、被取消或
异常中止时释放登记。`/api/chat/stop` 置位取消信号，内核在检查点停止，运行线程自己释放登记。

## 系统提示词

`prompts.py` 的 `build_system_prompt(registry=…)` 按以下顺序组装基础提示词：身份、回复语言、
`## 动手指令`、附加章节（插件章节与 `## 环境信息`）、`## 编码准则`、术语、`## 工具使用纪律`、
模式段、工具速查。纪律第 2 条的预览写类名单由 `preview_write_tools_line(registry)`
按工具的 `needs_preview` 生成。

`resolve_system_prompt()` 处理会话级覆盖；无 `explicit` 时必须传 `registry`。它用
`split_mode_section()` 切掉模式段，只删模式段本身，保留其后的插件章节与工具速查。

插件章节经 `PromptSections` 追加（如 `## 资源目录`），会话运行器再追加 `## 环境信息`
（操作系统与本会话 ID）。工具速查按工具摘「名字 — 描述首行」，最多 40 个；
完整 schema 走请求的 `tools` 字段。

模式说明由 `resolve_mode_note()` 产出，作为请求尾部的临时后缀，只加在发给模型的那一份上。
运行器的尾部还带 Todo 进度与插件尾部；有显式系统提示时，模式说明与 Todo 行都不加。
见 [context.md](context.zh.md) 的「执行模式是请求尾部的临时后缀」。

## 界面打包

`web/ui_bundle.py` 把界面资源内联成单页 HTML，运行时页面不再单独请求 CSS 与 JS。

```python
build_inline_css()      # 清单顺序的 CSS + 代码高亮深色主题 + 作用域限定到浅色的代码高亮浅色主题
build_inline_js()       # 前置脚本（主题 / Markdown 解析器 / 语法高亮库 / 代码高亮 / 图片灯箱）-> 主脚本模块 -> 后置脚本（工具视图 / 文件图标 / 本回合编辑清单 / 设置页）
scope_hljs_css()        # 给 .hljs 选择器加作用域前缀，如 html[data-ui-theme="light"]
inline_ui_html()        # 拼成完整单页
```

浅色代码高亮主题的作用域隔离在**运行时**做：`scope_hljs_css()` 给 `.hljs` 选择器加
`html[data-ui-theme="light"]` 前缀，两套配色同页共存而不互相覆盖；不另存一份改过的 CSS。

模块清单是顺序的唯一来源：JS 共用一个 `<script>` 作用域，CSS 按清单顺序层叠。
资源按功能拆成 `classic/js/**`、`classic/css/**` 的多个模块，由清单按顺序内联。
`inline_ui_html()` 带 `@lru_cache`，改界面资源后需重启服务。

模型下拉不是壳层内建 UI：壳层只留 `#modelPickerSlot` 挂载点，按钮与菜单由
`plugins/multi_model/ui/` 渲染，样式经 `window.aiAgentShell.styles.load()` 注入，
壳层公共样式里没有它。两条公共桥与停用清理见 [plugins.md](plugins.zh.md#壳层公共桥)。

### 本回合编辑清单

`edited-files.js` 只在页面内存拼装：预览留下 `confirm_id → diff`，`commit_write` 留下已确认 id，
回合 `done` 或 `stopped` 时取交集渲染 `.edited-files`；因等待用户确认而暂停时，
那一次 `done` 不出清单。清单不进内核，刷新不回放。`POST /api/chat/send` 发出有效新消息时 `clearLiveEdits`
清掉当前会话的旧清单卡与页内映射；`POST /api/chat/user-confirm` 不清。

## 对话区最小宽度

对话区与右栏之间是可拖拽的分割条（`classic/js/layout/splitters.js`，宽度记在 `localStorage`
的 `aiAgent.classicMainSplit`）。拖动时对话区的目标下界是 `670px`（`MIN_CHAT_PX`），
右栏下界是 `300px`（`MIN_STEPS_PX`，样式表 `.side{min-width:300px}`）。拖到极限时
右栏停在 `300px`，对话区不再被继续压窄。

670 是当前输入区控件行仍不越界的宽度：低于它时附件 / 模式 / 思考 / 模型 / 插件按钮 / 发送提示 /
目标 / 发送这一行会越出面板右边界。插件动作按钮会加宽这一行，因此该常量与当前控件行绑定。

窗口本身缩窄不受这组下界约束：`.chat` 是 `min-width:0`，对话区可以继续缩窄，输入区按钮组换行。

## 对话区 Markdown

散文块由内置 Markdown 解析器（`web/web_assets/classic/js/vendor/marked.min.js`）渲染：
松散列表的段距、表格、任务清单、嵌套列表等块级规则由它处理。

`classic/js/render/markdown.js` 的 `renderMarkdown()` 先按代码围栏切段：围栏交既有逻辑
（`diff` / `patch` 走 diff 卡片，其余走语法高亮），只把散文块交给 `renderMarkdownBlocks()`。

`renderMarkdownBlocks()` 用 `gfm:true`、`breaks:false`、`html:false` 解析，再经
`sanitizeRenderedHtml()` 清洗：GFM 提供表格与任务清单，`breaks:false` 保持 CommonMark
的换行语义，原始 HTML 不进入输出。

图片 / 媒体链接的 `src` 经 `markedImageHref()` 重写：工作区内的走 `/workspace/<rel>`，
其余本地绝对路径走 `/api/media?path=`。裸本地路径不能当 `src`，浏览器不解析它。

流式渲染合并到每个动画帧最多一次（`scheduleStreamRender()`）：解析器每次全量重解析，
逐条 delta 渲染会把同一段文本反复解析几十遍。

## 适配层

`classic_adapter/` 把内核事件翻译成经典界面认得的形状，以及把界面的请求翻译成内核调用。

| 文件 | 方向 |
|---|---|
| `outbound.py` / `outbound_tools.py` / `outbound_turns.py` | 内核事件 → 界面事件（流门面与工具/回合帧族） |
| `inbound.py` | 界面请求 → 内核调用 → 界面期望的返回体 |
| `history.py` | 历史折叠、附件、工具回显 |
| `layout.py` | 上下文分段布局、插件段覆盖、预算缩放 |
| `state.py` | 经典会话级状态（用量、命令输入、附件） |
| `sessions.py` | 会话标题与日期分组 |
| `contract.py` | 事件与字段常量，适配层的单一事实源 |
| `channel.py` | SSE 连接、广播、心跳与断线续传 |
| `confirm.py` | 会话暂停态与用户确认回路 |
| `plugin_events.py` | 插件事件帧 |
| `adapter.py` | 门面 `ClassicAdapter`：按会话的翻译流、健康快照、会话释放 |

适配层是**行为差异的落点**：界面与内核各自保持自己的形状，差异在中间抹平。

## 命令行壳

```bash
agent-cli --session <cid>                      # 交互式，真实模型 + 工具 + 写盘门控
agent-headless "问题"                          # 单轮，打印事件流与会话 ID
agent-headless --session <cid> --timeout 300 "问题"
agent-web                                     # Web 服务
agent-gui                                     # 原生启动器 + Python 桌面壳
```

`headless` 使用与 Web 相同的完整系统提示词、插件提示词章节、压缩与会话存储，加载
`plugins.headless.ini` 覆盖层，停用 `ai_speak`。单轮结束会打印：

```text
[session] <cid>
```

退出码：`0` 正常，`1` 失败/停止/取消，`2` 等待用户确认，`3` 超时。

`cli/interactive.py` 的 `build_session()` 在有 runner 时使用 `SessionRunner.build_engine()`，
与 Web、headless 共用完整系统提示词、插件章节与动态尾部；`run_one()` 只负责终端 I/O 与写盘确认。
CLI 加载 `plugins.cli.ini`，停用 `ai_speak`。

## 路径可见范围

`fspaths.py` 管哪些路径可见可读写：`--fs-root` 指定可见根（可重复），`/api/fs/list` 与
`/api/fs/read` 都在这个范围内；Windows 上缺省取本机各盘根，其它平台取项目根，也可用
`AI_AGENT_FS_ROOT` 指定（分隔符为 `os.pathsep`）。路径先解析再判界，判界用 `relative_to`，
不用字符串前缀比较。`/api/dir-browse`（`@` 补全用）从基准目录出发，但可以继续导航到别的
目录；查看器端点受可见根限制，补全浏览器不受。

`/workspace/*` 的根是 `<data_root>/workspace`。`/api/media` 只提供显式媒体根内的路径（未配置时用全部可见根），
不按工作区根判界。见 [guide/config.md](../guide/config.zh.md)。

## 诊断脚本

`scripts/inspect_compact.py` 对某个会话打印上下文分段与压缩判定，只读不写：

```bash
python scripts/inspect_compact.py                 # 列出有日志的会话
python scripts/inspect_compact.py <会话 id>        # 检视其中一个
python scripts/inspect_compact.py <会话 id> --digest
```

输出包含：事实条数、派生消息条数、用户轮数、全量估算 token 与阈值的关系及判定结果、
按原文保留的轮数、将被摘要的轮数、摘要取段的半开区间、分块 token 估算。

`--digest` 追加压缩器视角：视图消息条数、已落盘摘要条数与正文、装配后估算、
本次是否会产出压缩事件。

## 延伸阅读

- [architecture.zh.md](../architecture.zh.md)：五层结构与装配
- [tools.md](tools.zh.md)：写盘门控
- [guide/config.md](../guide/config.zh.md)：参数与环境变量
