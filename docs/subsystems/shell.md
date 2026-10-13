# 壳层

`agent/shell/` 是 L3 层，把内核包成可运行的服务与界面。

| 文件 | 职责 |
|---|---|
| `web.py` | HTTP + SSE 服务，路由分发，服务启动 |
| `sse.py` | SSE 传输层 |
| `session_runner.py` | 回合调度与心跳，消费 inbox 队列 |
| `prompts.py` | 系统提示词 |
| `ui_bundle.py` | 界面资源内联打包 |
| `chat.py` | 交互式对话壳（命令行） |
| `headless.py` | 无 UI 跑一轮并打印事件流 |
| `fspaths.py` | 可见范围的来源、路径判界与展示形态 |
| `classic_adapter/` | 事件翻译、历史回读、用户作答 |

## 启动

```bash
python -m agent.shell.web --host 127.0.0.1 --port 8765
```

`main()` 做的事：读配置 → 建 `App` → `create_server()` → 打印地址 → `serve_forever()`。

`create_server()` 返回 `(server, shell)`，不启动；测试可以直接拿到实例。`build_shell_app()` 是壳层的装配函数（同在 `web.py`），按配置建真实 provider 与会话存储。

启动时如果缺少模型配置，会打印说明并以退出码 2 结束。

## HTTP 路由

### GET

| 路径 | 作用 |
|---|---|
| `/` | 单页界面 |
| `/health` | 健康检查：工具数、模型、内核、允许的模型列表 |
| `/favicon.ico` | 站点图标 |
| `/assets/*` | 静态资源 |
| `/workspace/*` | 工作区文件（界面里图片视频的重写目标） |
| `/api/events/stream` | **SSE 事件流** |
| `/api/chat/history` | 会话历史 |
| `/api/chat/sessions` | 会话列表（带日期分组） |
| `/api/chat/ui-state` | 会话运行态：哪些会话在跑（**不存客户端布局**） |
| `/api/chat/attachment` | 附件读取 |
| `/api/fs/list` `/api/fs/read` | 右栏文件查看器 |
| `/api/dir-browse` | 目录浏览（补全用） |
| `/api/panels` `/api/actions` | 插件贡献的右栏面板与输入区动作清单 |
| `/api/plugin/<插件>/<路径>` | 插件自己的端点命名空间（精确匹配，无通配） |
| `/api/model-pricing` | 计价表 |
| `/api/reasoning-effort` | 推理档位 |
| `/api/usage-accumulator` | 用量累计 |
| `/api/media` | 媒体代理，根由 `--media-root` 指定 |

### POST

| 路径 | 作用 |
|---|---|
| `/api/chat/send` | 发起一轮对话。同会话已在跑时返回 **409** |
| `/api/chat/stop` | 停止当前回合 |
| `/api/chat/user-confirm` | 提交用户确认（写盘确认与 `user_confirm` 作答共用此端点） |
| `/api/chat/title` | 生成或读取会话标题 |
| `/api/chat/autonomous` | 自主模式开关 |
| `/api/chat/goal` | 目标文案读写 |
| `/api/chat/command-input` | 交互式命令的 stdin 输入 |

### PUT

`/api/chat/ui-state`、`/api/reasoning-effort`、`/api/usage-accumulator`，以及插件端点（`/api/plugin/<插件>/…`）。

写操作走 body、读操作走 query，全工程统一。

## SSE 事件流

`/api/events/stream` 是界面看到的事实投影。每一帧带 `conversation_id`，界面按会话分派。

帧里带**序号**，断线重连时用它续传：客户端带上最后收到的序号，服务端只补发其后的帧。这解决的是"没有游标就不回放"的问题 —— 否则新开的页面收不到 `run_started`，既显示不出停止键也判不出忙。

SSE 连接表由 `WebShell` 持有，断开时从表里移除。

## 运行态与并发保护

`WebShell` 持两张表：SSE 连接表与活跃回合表。

`/api/chat/ui-state` 的"在跑"来自运行态登记（见 [session.md](session.md)），与 `session_send` 判定目标忙闲用的是同一事实源。这样中途打开的页面能问出"这条会话在不在跑"，进而正确显示停止键。

**客户端布局（打开过哪些标签、激活哪一个）存在浏览器 `localStorage`**：布局属于某一个浏览器，服务端不提供也不接收。多个客户端各自激活不同会话时，服务端的一个全局字段会被后写者覆盖，先写的刷新后被带到别人的会话。

`/api/chat/send` 对同会话并发返回 409，依据同一个登记。

## 回合调度

`session_runner.py` 的 `SessionRunner` 在后台执行回合：从 inbox 取输入、通过 `Engine` 跑模块链、把事件推给 SSE、续心跳。

心跳让运行态登记在长任务期间不被判为过期。任务结束或取消时释放登记。

## 系统提示词

`prompts.py` 的 `build_system_prompt()` 组装基础提示词：术语表、工具纪律、编码准则、模式尾注。`tool_summary()` 从工具注册表摘一份"名字 — 一句话"速查，避免把完整 schema 塞两遍。

`resolve_system_prompt()` 处理会话级覆盖。

## 界面打包

`ui_bundle.py` 把界面资源内联成单页 HTML，运行时页面零额外请求。

```python
build_inline_css()      # reset + 主样式 + 两份代码高亮主题
build_inline_js()       # 主题 / markdown 解析器 / 高亮 / 图片灯箱 / 主脚本
scope_hljs_css()        # 把 .hljs 选择器限定到浅色主题下
inline_ui_html()        # 拼成完整单页
```

浅色代码高亮主题的作用域隔离在**运行时**做：`scope_hljs_css()` 给 `.hljs` 选择器加 `html[data-ui-theme="light"]` 前缀，两套配色同页共存而不互相覆盖。不另存一份改过的 CSS。

## 对话区 Markdown

散文块由 `marked`（`web_assets/classic/js/vendor/marked.min.js`）渲染 —— markdown 的块级规则细节多（松散列表的段距、表格、任务清单、嵌套列表），自研实现容易在边角处丢样式。

`agent-ui.js` 的 `renderMarkdown()` 先按代码围栏切段，围栏交既有逻辑（`diff` / `patch` 走 diff 卡片，其余走 hljs 高亮），只把散文块交给 `renderMarkdownBlocks()`。

两项配置是必须的：

- `breaks: true` —— 服务端按段落推送，CommonMark 会把正文里的单个换行折成空格，边收边看就会文字粘成一行；
- 图片 / 媒体链接的 `src` 重写（`markedImageHref()`）—— 落在工作区里的走 `/workspace/<rel>` 静态路由，其余本地绝对路径走 `/api/media?path=`。裸本地路径不能当 `src`，浏览器不认。

流式渲染每个动画帧最多渲染一次（`scheduleStreamRender()`）：`marked` 每次都是全量重解析，delta 密集时逐条渲染会把同一段文本反复解析几十遍。

结果被 `@lru_cache` 缓存，所以改界面资源后需要重启服务。

## 适配层

`classic_adapter/` 把内核事件翻译成经典界面认得的形状，以及把界面的请求翻译成内核调用。

| 文件 | 方向 |
|---|---|
| `outbound.py` | 内核事件 → 界面事件 |
| `inbound.py` | 界面请求 → 内核调用 → 界面期望的返回体 |
| `contract.py` | 事件与字段常量，适配层的单一事实源 |
| `adapter.py` | 门面 `ClassicAdapter`、SSE 通道 `ClassicSseChannel` |

适配层是**行为差异的落点**：界面与内核各自保持自己的形状，差异在中间抹平。

## 命令行壳

```bash
python -m agent.shell.chat --session <cid>   # 交互式，真实模型 + 工具 + 写盘门控
python -m agent.shell.headless               # 跑一轮并打印事件流
```

`chat.py` 的 `build_session()` 装配一个可用的会话，`run_one()` 跑一轮。这两个在测试里被大量复用。

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

- [architecture.md](../architecture.md)：四层结构与装配
- [tools.md](tools.md)：写盘门控
- [guide/config.md](../guide/config.md)：参数与环境变量
