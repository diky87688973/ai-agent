# 配置

配置文件是仓库根目录的 `config.ini`，随仓库入库，只保留非敏感的宿主配置；文件不存在时使用代码默认值。模型不在此文件配置，由 `plugins/multi_model/plugin-config.ini` 和多模型设置页维护。缺省值与全部键见下。

插件清单是另一份文件 `plugins.ini`（工程根），它**入库**——里面没有密钥，列的是装载哪些插件。见 [插件](../subsystems/plugins.md)。

## `[agent]`

```ini
[agent]
reasoning_effort = max
backup_retention_days = 7
max_passes = 512
plugin_tree_only = 0
```

| 键 | 默认 | 含义 |
|---|---|---|
| `reasoning_effort` | `max` | 全局推理档位。`max` = 深度推理，`high` = 标准推理。会话内可切换，**会话级选择优先**，且按会话落盘（`data/session_state/`） |
| `backup_retention_days` | `7` | 版本化备份保留天数。启动时清理更早的；`0` = 永久保留 |
| `max_passes` | `512` | 每回合模型往返上限；小于 1 按 1 处理。每次往返可调用 0 个或多个工具，不是工具调用次数上限 |
| `plugin_tree_only` | `0` | `1` 时只允许装载落在 `plugins/` 树内的插件目录；清单里的绝对/外置 `path` 会被拒。环境变量 `AI_AGENT_PLUGIN_TREE_ONLY` 优先 |

`reasoning_effort` 的取值直接进请求体的 `reasoning_effort` 字段。值非法时回落 `max`。

Rules 不在这里配：规则文件放在工程根的 `rules/` 目录，由 `plugins/rules`
插件全量注入，见 [Rules](../subsystems/rules.md)。

两项都在**进程启动时读一次**，改配置后需重启服务。

## 文件备份

写类工具覆盖文件前会留一份原内容，供 `file_undo` 回滚。**按被改文件的路径分组**，每个版本是一个自描述目录：

```
<工程根>/data/temp/file_backup/
├── 40523ae2c2b5f07f/                    ← 绝对路径的 MD5 前 16 位
│   ├── 20261012_193315_269_0000_c00c/   ← 版本目录：YYYYMMDD_HHMMSS_mmm_序号_随机
│   │   ├── original                     原文件字节
│   │   └── metadata.json                mod_id / path / time / bytes / sha256 / mode / diff
│   └── 20261012_195719_270_033b/
└── c9e965b3ee74285f/
```

`mod_id` 形如 `<路径哈希>:<版本目录名>`，`file_undo` 的 `diff` / `undo` 都用它定位。

版本目录名**精确到毫秒**：同一秒内的多次改动也要能排出先后 —— 只到秒时只能靠随机段排序，而随机段与先后无关，`file_undo list` 的顺序会错乱。

`metadata.json` 里的 `mode` 与 `diff_text` 记录**这一版是被什么改动产生的**：`mode` 取工具名或替换模式（`write` / `literal` / `lines` / `patch` / `read_write` / `undo`），`diff_text` 是旧→新的 unified diff（上限 2000 字符，超出时末尾标 `…（已截断）`）。目标文件原本不存在（没有旧内容可算）时 `diff_text` 为空。

- **版本按被改文件的路径哈希分组**：文件名可能含中文、空格、超长，净化后会互相分不开，也读不出是什么；路径哈希互不冲突，同一文件的所有版本聚在一个目录下，查历史就是读一个目录。
- **版本目录名最前面是日期**，按年龄清理只需解析它；归属、时间、校验和记在各版本自带的 `metadata.json` 里。
- 某个文件的版本全部过期后，它的哈希目录一并移除。

删除类操作（`delete_file` / `file_ops`）不真删，移入 `<工程根>/data/recycle/<YYYYMMDD>/`，可人工取回。

启动时按 `[agent] backup_retention_days` 清理过期版本。清理失败只留痕，不阻断启动。

## `[context]`

上下文压缩。会话在内存中分两段：近期记忆与摘要。末尾 `full_user_rounds` 个用户轮被遮盖、按原文保留，它们前面的轮次压缩成摘要。

```ini
[context]
summary_token_fallback   = 64000
full_user_rounds         = 1
summary_output_max_chars = 5000
image_turns              = 1
image_max                = 8
reasoning_replay_tokens = 8000
```

| 键 | 缺省或留空时 | 含义 | 建议范围 |
|---|---|---|---|
| `summary_token_fallback` | `64000` | 仅在当前模型没有声明 `context_window` 时使用的回退压缩阈值；不提供设置页入口 | 正整数 |
| `full_user_rounds` | `1` | 压缩时保留最近对话轮数：末尾这么多用户轮不压，只压它们前面的 | `1`–`10` |
| `summary_output_max_chars` | `5000` | 摘要的篇幅上限，单位为字。它作为约束写进摘要提示词，实际长度由模型遵守程度决定 | `2000`–`8000` |
| `image_turns` | `1` | 只把**最近这么多轮用户发言**里的图片带进模型请求，更早的转文本占位。`0` = 一张都不带，负数 = 不限 | 正整数 / 负数 |
| `image_max` | `8` | 这几轮里最多带几张图；**最近一轮优先保**，超量的从最老的那一轮开始砍。`0` = 一张都不带，负数 = 不限 | 正整数 / 负数 |
| `reasoning_replay_tokens` | `8000` | 思维链回传预算（token）。`-1` = 全量回传；`0` = 不回传；正数 = 超出就**取两头、中间以 `<此处省略 N token 的推理>` 代替**（模型可据前后文推断中间）。思维链是模型产生的中间稿，必然未命中缓存，全量回传等于每轮多背几万 token | `-1` / `0` / 正数 |

有模型窗口时，实际压缩阈值 = `context_window × compression_percent / 100`；
`compression_percent` 是模型条目字段，默认 70，范围 10–90。

图片只从**发给模型的请求**里被裁掉，事实流里的字节不动 —— 历史回显与重新提问都还能拿到原图。

「缺省或留空时」是 `config.ini` 缺该节或缺该键时生效的值。

机制细节见 [context.md](../subsystems/context.md)。

## 插件

插件的装载在**另一份文件** `plugins.ini`（工程根）。节在就进入装载候选；开关写在该节的 `enabled`。名字、描述、图标、版本由 `plugin-meta.json` 声明。插件自己的键在 `[config]`。

```ini
[plugin:skills]

[plugin:knowledge]
enabled = 1
```

| 名称 | 能力 | 自己的配置文件 |
|---|---|---|
| `skills` | Skills 库（内置 + 外置）与 `skills` 工具 | `plugins/skills/plugin-config.ini` |
| `rules` | `rules/` 下的 `.md` 全量注入上下文 | 无配置（只有开关）；见 [Rules](../subsystems/rules.md) |
| `knowledge` | 本地知识库检索 | `plugins/knowledge/plugin-config.ini` |
| `ai_speak` | 人类口语播报与语音播放 | `plugins/ai_speak/plugin-config.ini` |

**节的先后即上下文组装顺序**：越不容易变动的插件排在越前面。

**插件自己的配置跟着插件走。** AI说话 / 视觉操作 / 知识库 / Skills 的配置入库；`multi_model` 的密钥配置被 `.gitignore` 排除；**内核的 `config.ini` 里没有插件设置**。
插件的目录形态、可贡献的能力与开发方式见 [插件](../subsystems/plugins.md)。


## 启动参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--host` | `127.0.0.1` | 绑定地址 |
| `--port` | `8765` | 端口 |
| `--data-root` | `<工程根>/data` | 数据目录 |
| `--fs-root` | 本机各盘根 | 文件可见范围。**可重复传** |
| `--media-root` | 空；取第一个 `--fs-root` | `/api/media` 可读根 |

`--fs-root` 重复传参写作 `--fs-root D:\ --fs-root E:\`。

`/workspace/*` 的根固定为 `<data-root>/workspace`，不受 `--media-root` 影响。

## 环境变量

全部可选。

| 变量 | 说明 |
|---|---|
| `AI_AGENT_DATA_ROOT` | 数据根目录 |
| `AI_AGENT_FS_ROOT` | 文件可见根，多个用系统路径分隔符连接（Windows 为 `;`） |
| `AI_AGENT_MEDIA_ROOT` | `/api/media` 可读根 |
| `AI_AGENT_PLUGIN_TREE_ONLY` | `1` 只允许从 `plugins/` 树内装载；覆盖 `[agent] plugin_tree_only` |
| `AI_AGENT_LOCK_TIMEOUT` | 跨进程锁等待秒数，默认 30 |
| `AI_AGENT_LOG_REQUESTS` | 设为 `0` 关闭发送前的请求摘要，默认开启 |
| `AI_AGENT_LLM_LOG` | 模型收发日志落盘路径，缺省为 `%TEMP%\fan_agent_llm_requests.log` |

## 数据目录

运行时数据在 `data/` 下，不入版本库。用 `--data-root` 或 `AI_AGENT_DATA_ROOT` 指到别处。

| 目录 | 内容 |
|---|---|
| `data/sessions/` | 会话事实日志 |
| `data/titles/` | 会话标题（纯文本派生缓存） |
| `data/session_state/` | 会话状态（模型 / 模式 / 推理档位 / 清单，一个会话一份 JSON） |
| `data/temp/` | 临时产物（写盘前备份见上节「文件备份」） |
| `data/mesh/` | 会话间协作（`agents.json` 注册表 + 运行态） |
| `data/queues/` | 会话待发送消息队列（用户与 Agent 消息、附件） |
| `data/mesh/runs/` | 运行态登记（`<cid>.json`） |
| `data/workspace/` | `/workspace/` 静态路由根 |
| `data/recycle/` | 删除操作的回收目录 |
| `data/plugin/<插件名>/` | 插件专属存储（插件只看到自己那一层） |
| `data/cache/` | 派生缓存，含会话加密密钥 |
| `data/logs/errors.log` | 进程错误日志（JSONL；内核/插件装配与宿主运行异常；工具业务失败收成 `ToolResult` 后不记此处；超约 2MB 轮转为 `errors.log.1`） |

目录都是按需惰性创建的：全新克隆下只有 `data/` 本身，跑过一轮才会出现用到的那几个。

## 延伸阅读

- [架构](../architecture.md)
- [术语](../glossary.md)
- [上下文管理](../subsystems/context.md)
