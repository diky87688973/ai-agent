# 壳层

`agent/shell/` 是 L3 层，把内核包成可运行的服务与界面。

| 文件 | 职责 |
|---|---|
| `web/server.py` | HTTP + SSE 服务装配与启动 |
| `web/web_routes.py` | HTTP 动词与路径分派 |
| `web/web_static.py` | 静态资源、路径与协议常量 |
| `web/web_classic.py` | 经典页面与经典 SSE |
| `web/web_plugin.py` | 插件端点与插件资产转发 |
| `web/web_api.py` | WebShell 入口、SSE 连接/运行态 |
| `web/web_chat.py` / `web/web_sessions.py` / `web/web_files.py` / `web/web_contributions.py` / `web/web_state.py` | WebShell 的聊天、会话、文件、贡献、UI 状态动作 |
| `sse.py` | SSE 传输层 |
| `session/runner.py` | 回合调度、取消、队列抽干与生命周期 |
| `session/queue.py` | 队列领取、释放、补投 |
| `session/goal.py` | 目标与自主续跑判定 |
| `session/prompt.py` | 系统提示与运行态尾部 |
| `session/resume.py` | 外部工具结果恢复 |
| `session/heartbeat.py` | 运行态心跳 |
| `prompts.py` | 系统提示词 |
| `web/ui_bundle.py` | 界面资源内联打包 |
| `settings_panel.py` / `settings_io.py` / `plugin_settings.py` | 设置页宿主配置、INI 原语、插件配置 |
| `cli/interactive.py` | 交互式对话壳（命令行） |
| `cli/headless.py` | 无 UI 跑一轮并打印事件流 |
| `fspaths.py` | 可见范围的来源、路径判界与展示形态 |
| `classic_adapter/` | 事件翻译、历史回读、用户作答 |
| `web/web_assets/` | 壳层页面、样式与前端脚本 |

## 用量与命中率的口径

**命中率只用官方返回值算**：每次模型调用后 API 在 `usage` 里给
`prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`，内核原样落成 `usage` 事实、
适配层原样转发（字段名见 `classic_adapter/contract.py` 的 `SSE_USAGE_FIELDS`），
界面显示的命中率就是"命中 / (命中 + 未命中)"这两个官方值之比 —— 不掺任何估算。

**上下文占用率的分母是模型窗口**（读模型条目的 `context_window`；内核随 `context_layout` 一起下发
`model_max_context_tokens`），不是压缩阈值：阈值是"留多少余量触发压缩"的预算，
窗口是物理上限，两者混用会让人以为"还剩 75%"。窗口跟着**会话当前模型**走，
换模型后下一回合的分母就换。

**分段浮层里的 token 是估算**（对装配后的消息求和，中文按每字 1 token），
与用量条里的官方 `prompt_tokens` 不是同一个数：前者是"这段大概多少"，
后者是"这次实际花了多少"。

## 启动

```bash
python -m agent.entry.web --host 127.0.0.1 --port 8765
```

`main()` 做的事：读配置 → 建 `App` → `serve()` → 打印地址 → `serve_forever()`。

`create_server()` 返回 `(server, shell)`，不启动；测试可以直接拿到实例。`serve()` 接收已装配的 app，
负责可见根/媒体根/标题与工作目录的落点并阻塞运行。`build_shell_app()` 是入口层的装配函数
（`agent/entry/web.py`）：按配置建真实 provider 与会话存储——壳层不导入装配根（A2）。

缺少模型配置不阻断启动：服务以 `MissingProvider` 起来，浏览器打开主页面，模型下拉为空；
设置页保存后调用 `app.reload_model_config()` 立即生效。已有插件模型时目录权威接管。

## HTTP 路由

### GET

| 路径 | 作用 |
|---|---|
| `/` | 单页界面 |
| `/health` | 健康检查：工具数、模型、全局默认推理档位、内核、允许的模型列表 |
| `/favicon.ico` | 站点图标 |
| `/assets/*` | 静态资源 |
| `/workspace/*` | 工作区文件（界面里图片视频的重写目标） |
| `/api/events/stream` | **SSE 事件流** |
| `/api/chat/history` | 会话历史 |
| `/api/chat/sessions` | 会话列表（带日期分组） |
| `/api/chat/ui-state` | 会话状态：模式 / 模型 / 推理档位 / 清单 / 目标（带 `conversation_id`）；不带 id 时只回**哪些会话在跑**（**不存客户端布局**） |
| `/api/chat/attachment` | 附件读取 |
| `/api/fs/list` `/api/fs/read` | 右栏文件查看器 |
| `/api/dir-browse` | 目录浏览（补全用） |
| `/api/panels` `/api/actions` | 插件贡献的右栏面板与输入区动作清单 |
| `/api/plugin/<插件>/<路径>` | 插件自己的端点命名空间（精确匹配，无通配） |
| `/api/settings` | 设置页目录。密钥字段 `value` 恒为空，另给 `configured`（是否已填写）和 `placeholder` |
| `/api/settings/plugins` | 插件卡片：名字、描述、图标、是否装载 |
| `/api/settings/plugin-file` | 某个插件的 `plugin-config.ini` 编辑视图（密钥已掩码） |
| `/api/reasoning-effort` | 推理档位 |
| `/api/chat/queue` | 当前会话的待发送队列快照 |
| `/api/usage-accumulator` | 用量累计 |
| `/api/media` | 媒体代理，根由 `--media-root` 指定 |

### POST

| 路径 | 作用 |
|---|---|
| `/api/chat/send` | 发起一轮对话。同会话已在跑时进入待发送队列 |
| `/api/chat/queue/<id>/insert` | 把队列消息标记为下一个安全轮次插入 |
| `/api/chat/queue/<id>/recall` | 撤回队列消息并返回文本、图片与来源 |
| `/api/chat/stop` | 停止当前回合 |
| `/api/chat/user-confirm` | 提交用户确认（写盘确认与 `user_confirm` 作答共用此端点） |
| `/api/chat/title` | 生成或读取会话标题 |
| `/api/chat/autonomous` | 自主模式开关 |
| `/api/chat/goal` | 目标文案读写 |
| `/api/chat/command-input` | 交互式命令的 stdin 输入 |
| `/api/chat/queue/<id>` | 取消一条未发送队列消息（DELETE） |
| `/api/settings` | 写回宿主配置。密钥字段为空不写，有内容才覆盖文件里的原值 |
| `/api/settings/plugins` | 插件开关，写 `plugins.ini` 的 `enabled` |
| `/api/settings/plugin-file` | 写回某个插件的**可编辑节**，其它节逐字节保留 |
| `/api/settings/pick-dir` | 弹出系统目录选择窗口 |

### PUT

`/api/chat/ui-state`、`/api/reasoning-effort`、`/api/usage-accumulator`，以及插件端点（`/api/plugin/<插件>/…`）。

写操作走 body、读操作走 query，全工程统一。

设置页在界面右上角，读写的就是 `config.ini`、`web-ui-config.ini` 和各插件的 `plugin-config.ini`。密钥只允许覆盖：密码框留空则文件里的值不动；有内容才替换。`GET /api/settings` 不回明文，只说明是否已填写。已填写时密码框提示「已设置秘钥,可重新设置并替换」，未填写时提示「未配置秘钥」。

「保存」是保存并关窗（只有失败才留在窗口里），「应用」是保存但不关窗。插件配置的
身份与开关不在插件配置里；编辑区只覆盖插件自己的节 —— 有
`settings-schema.json` 的插件（多模型）按结构化表单逐条编辑，其余插件只显示
`[config]` 的正文，节头不露出。密钥字段在结构化表单里同样只回显"是否已配置"，
留空表示沿用原值。

模型配置只由多模型插件维护；宿主设置页不提供内核模型节，也不写模型凭据。
插件目录变化时由插件宿主刷新模型路由与清单。

## SSE 事件流

`/api/events/stream` 是界面看到的事实投影。每一帧带 `conversation_id`，界面按会话分派。

帧里带**序号**，断线重连时用它续传：客户端带上最后收到的序号，服务端只补发其后的帧。这解决的是"没有游标就不回放"的问题 —— 否则新开的页面收不到 `run_started`，既显示不出停止键也判不出忙。

SSE 连接表由 `WebShell` 持有，断开时从表里移除。

## 运行态与并发保护

`WebShell` 持两张表：SSE 连接表与活跃回合表。

`/api/chat/ui-state` 的"在跑"来自运行态登记（见 [session.md](session.md)），与 `session_send` 判定目标忙闲用的是同一事实源。这样中途打开的页面能问出"这条会话在不在跑"，进而正确显示停止键。

**客户端布局（打开过哪些标签、激活哪一个）存在浏览器 `localStorage`**：布局属于某一个浏览器，服务端不提供也不接收。多个客户端各自激活不同会话时，服务端的一个全局字段会被后写者覆盖，先写的刷新后被带到别人的会话。

`/api/chat/send` 对同会话并发进入待发送队列，依据同一个登记。

## 回合调度

`session/runner.py` 的 `SessionRunner` 在后台执行回合：从待发送队列取输入、通过 `Engine` 跑模块链、把事件推给 SSE、续心跳。

心跳让运行态登记在长任务期间不被判为过期。任务结束或取消时释放登记。

## 系统提示词

`prompts.py` 的 `build_system_prompt(registry=…)` 组装基础提示词：身份、回复语言、动手指令、术语表、工具纪律、编码准则、模式段。纪律第 2 条的预览写类名单由 `preview_write_tools_line(registry)` 按 `needs_preview` 动态生成。`resolve_system_prompt()` 切掉模式段后，插件通过 `PromptSections` 追加章节（如 `## 资源目录`），会话运行器再追加 `## 环境信息`（操作系统与本会话 ID），最后接工具速查；工具速查只摘"名字 — 一句话"，完整 schema 走请求的 `tools` 字段。

`resolve_system_prompt()` 处理会话级覆盖，并**把模式段切掉**（`split_mode_section()`）：无 `explicit` 时必须传 `registry`。模式改由 `resolve_mode_note()` 产出，作为请求尾部的临时后缀附加，只加在发给模型的那一份上。理由见 [context.md](context.md) 的「执行模式是请求尾部的临时后缀」。

## 界面打包

`web/ui_bundle.py` 把界面资源内联成单页 HTML，运行时页面零额外请求。

```python
build_inline_css()      # reset + 主样式 + 工具视图 + 本轮编辑清单 + 两份代码高亮主题
build_inline_js()       # 主题 / markdown 解析器 / 高亮 / 图片灯箱 / 主脚本 / 工具视图 / 本轮编辑清单 / 设置页
scope_hljs_css()        # 把 .hljs 选择器限定到浅色主题下
inline_ui_html()        # 拼成完整单页
```

浅色代码高亮主题的作用域隔离在**运行时**做：`scope_hljs_css()` 给 `.hljs` 选择器加 `html[data-ui-theme="light"]` 前缀，两套配色同页共存而不互相覆盖。不另存一份改过的 CSS。

### 本轮编辑清单

`edited-files.js` 只在页面内存拼装：预览留下 `confirm_id → diff`，`commit_write` 留下已确认 id，回合 `done` 时取交集渲染 `.edited-files`。清单不进内核、刷新不回放。`POST /api/chat/send` 发出有效新消息时 `clearLiveEdits` 清掉当前会话的旧清单卡与页内映射；`POST /api/chat/user-confirm` 不清。

## 对话区最小宽度

对话区与右栏之间是可拖拽的分割条（`initClassicMainSplit`，宽度记在 `localStorage`）。
对话区有**硬下界 `670px`**（样式表 `.chat{min-width}` 与脚本里的 `MIN_CHAT_PX` 同值）：

- 分割条拖到极限、或窗口缩到很窄时，右栏先被压到自己的下界 `300px`，对话区不再被压；
- 到这个数是因为输入区那一行控件（附件 / 模式 / 思考 / 模型 / 插件按钮 + 发送提示 +
  目标 / 发送）在更窄时会顶出面板右边界：669px 时「发送」越界 1px，670px 起不越界。

插件按钮会让这一行变长：加了一个按钮之后要重量一次，把样式表与脚本里两个数字一起往上调。

## 对话区 Markdown

散文块由 `marked`（`web/web_assets/classic/js/vendor/marked.min.js`）渲染 —— markdown 的块级规则细节多（松散列表的段距、表格、任务清单、嵌套列表），自研实现容易在边角处丢样式。

`classic/js/render/markdown.js` 的 `renderMarkdown()` 先按代码围栏切段，围栏交既有逻辑（`diff` / `patch` 走 diff 卡片，其余走 hljs 高亮），只把散文块交给 `renderMarkdownBlocks()`。

两项配置是必须的：

- `breaks: true` —— 服务端按段落推送，CommonMark 会把正文里的单个换行折成空格，边收边看就会文字粘成一行；
- 图片 / 媒体链接的 `src` 重写（`markedImageHref()`）—— 落在工作区里的走 `/workspace/<rel>` 静态路由，其余本地绝对路径走 `/api/media?path=`。裸本地路径不能当 `src`，浏览器不认。

流式渲染每个动画帧最多渲染一次（`scheduleStreamRender()`）：`marked` 每次都是全量重解析，delta 密集时逐条渲染会把同一段文本反复解析几十遍。

结果被 `@lru_cache` 缓存，所以改界面资源后需要重启服务。

资源按功能拆成 `classic/js/**`、`classic/css/**` 的多个模块，由 `web/ui_bundle.py` 的
清单按顺序内联；**没有**动辄几千行的 `agent-ui.js` / `agent-ui.css`。模型下拉不是
壳层内建 UI：壳层只留 `#modelPickerSlot`，按钮与菜单由 `plugins/multi_model/ui/`
渲染，样式经 `window.aiAgentShell.styles.load()` 注入，壳层公共样式里没有它。
两条公共桥与停用清理见 [plugins.md](plugins.md#壳层公共桥)。

## 适配层

`classic_adapter/` 把内核事件翻译成经典界面认得的形状，以及把界面的请求翻译成内核调用。

| 文件 | 方向 |
|---|---|
| `outbound.py` / `outbound_tools.py` / `outbound_turns.py` | 内核事件 → 界面事件（门面与工具/回合分组） |
| `inbound.py` | 界面请求 → 内核调用 → 界面期望的返回体 |
| `history.py` | 历史折叠、附件、工具回显 |
| `layout.py` | 上下文布局、覆盖、缩放 |
| `state.py` | 经典会话级状态 |
| `sessions.py` | 会话标题与日期分组 |
| `contract.py` | 事件与字段常量，适配层的单一事实源 |
| `channel.py` | SSE 连接、广播、心跳与断线续传 |
| `confirm.py` | 会话暂停态与用户确认回路 |
| `adapter.py` | 门面 `ClassicAdapter`（会话翻译流、健康与环境快照） |

适配层是**行为差异的落点**：界面与内核各自保持自己的形状，差异在中间抹平。

## 命令行壳

```bash
agent-cli --session <cid>                      # 交互式，真实模型 + 工具 + 写盘门控
agent-headless "问题"                          # 单轮，打印事件流与会话 ID
agent-headless --session <cid> --timeout 300 "问题"
agent-web                                     # Web 服务
agent-gui                                     # 原生启动器 + Python 桌面壳
```

`headless` 使用与 Web 相同的完整系统提示词、插件提示词段、压缩与会话存储，
默认加载 `plugins.headless.ini` 覆盖层（当前关闭 `ai_speak`）。单轮结束会打印：

```text
[session] <cid>
```

退出码：`0` 正常，`1` 失败/停止/取消，`2` 等待用户确认，`3` 超时。

`cli/interactive.py` 的 `build_session()` 使用 `SessionRunner.build_engine()`，与 Web、headless 共用完整系统提示词、插件章节与动态尾部；`run_one()` 只负责终端 I/O 与写盘确认。CLI 默认加载 `plugins.cli.ini`，关闭依赖浏览器播放的 `ai_speak`。

## 路径可见范围

`fspaths.py` 管"哪些路径能被看见和读写"：`--fs-root` 指定可见根（可重复），`/api/fs/*` 与 `@` 补全都在这个范围内；缺省取本机各盘根，也可用 `AI_AGENT_FS_ROOT` 指定。

`/api/media` 与 `/workspace/*` 各有独立的根，见 [guide/config.md](../guide/config.md)。

## 诊断脚本

`scripts/inspect_compact.py` 对某个会话打印上下文分段与压缩判定，**只读不写**：

```bash
python scripts/inspect_compact.py                 # 列出有日志的会话
python scripts/inspect_compact.py <会话 id>        # 检视其中一个
python scripts/inspect_compact.py <会话 id> --digest
```

输出包含：事实条数、派生消息条数、用户轮数、全量估算 token 与阈值的关系、保留窗口宽度、
哪几轮会被压成摘要（半开区间）、已落盘的摘要、分块 token 估算。

`--digest` 追加压缩器视角：视图消息条数、已落盘摘要条数、本次是否会产出压缩事件。

## 延伸阅读

- [architecture.md](../architecture.md)：五层结构与装配
- [tools.md](tools.md)：写盘门控
- [guide/config.md](../guide/config.md)：参数与环境变量
