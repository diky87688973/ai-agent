[English](config.md) | **中文**

# 配置

配置文件是仓库根目录的 `config.ini`，随仓库入库，只保留非敏感的宿主配置；文件不存在时使用代码默认值。模型不在此文件配置，由 `plugins/multi_model/plugin-config.ini` 和多模型设置页维护。缺省值与全部键见下。

插件清单是另一份文件 `plugins.ini`（工程根），它**入库**——里面没有密钥，列的是装载哪些插件。见 [插件](../subsystems/plugins.md)。

## `[agent]`

```ini
[agent]
reasoning_effort = max
backup_retention_days = 7
max_passes = 64
plugin_tree_only = 0
```

| 键 | 默认 | 含义 |
|---|---|---|
| `reasoning_effort` | `max` | 全局推理档位。`max` = 深度推理，`high` = 标准推理。会话内可切换，**会话级选择优先**，且按会话落盘（`data/session_state/`） |
| `backup_retention_days` | `7` | 版本化备份保留天数。启动时清理更早的；`0` = 永久保留 |
| `max_passes` | `64` | 每回合模型往返上限；小于 1 按 1 处理。每次往返可调用 0 个或多个工具，不是工具调用次数上限 |
| `plugin_tree_only` | `0` | `1` 时只允许装载落在 `plugins/` 树内的插件目录；清单里的绝对/外置 `path` 会被拒。环境变量 `AI_AGENT_PLUGIN_TREE_ONLY` 优先 |

仓库的 `config.ini` 使用 `high`（`reasoning_effort`）与 `512`（`max_passes`）；上表默认值取自代码。

`reasoning_effort` 由支持该字段的 provider 写入请求体的 `reasoning_effort` 字段；不支持该字段的 provider 会忽略它。值非法时回落 `max`。

Rules 不在这里配：规则文件放在工程根的 `rules/` 目录，由 `plugins/rules` 插件全量注入，见 [Rules](../subsystems/rules.zh.md)。

`backup_retention_days` 在进程启动时读一次，改配置后需重启服务。

## 文件备份

写类工具覆盖文件前会留一份原内容，供 `file_undo` 回滚。**按被改文件绝对路径的哈希分组**，每个版本是一个自描述目录：

```text
<data-root>/temp/file_backup/
├── 40523ae2c2b5f07f/                    ← 绝对路径的 MD5 前 16 位
│   ├── 20261012_193315_269_0000_c00c/   ← 版本目录：YYYYMMDD_HHMMSS_mmm_序号_随机
│   │   ├── original                     原文件字节
│   │   └── metadata.json                mod_id / path / time / bytes / encoding / original_sha256 / mode / diff_text
│   └── 20261012_195719_270_033b/
└── c9e965b3ee74285f/
```

`mod_id` 形如 `<路径哈希>:<版本目录名>`，`file_undo` 的 `diff` / `undo` 都用它定位。

版本目录名带毫秒时间戳、零填充序号与随机短段，按名字排序即按创建先后排序。

`metadata.json` 记录**这一版是由什么改动产生的**：`mode` 是改动类型（`write` / `literal` / `edits` / `lines` / `patch` / `read_write` / `undo`），`diff_text` 是旧→新的 unified diff（截断到 2000 字符，并标记已截断）。目标文件原本不存在时不会记录版本：没有旧内容可保留。

- **版本按被改文件绝对路径的哈希分组**：文件名可能含中文、空格或超长，净化后会互相分不开；路径哈希互不冲突，同一文件的所有版本聚在一个目录下。
- **版本目录名最前面是日期**，按年龄清理只需解析它；文件路径、时间与校验和记在各版本自带的 `metadata.json` 里。
- 某个文件的版本全部过期后，它的哈希目录一并移除。

删除类操作（`delete_file` / `file_ops`）不真删，移入 `<data-root>/recycle/<YYYYMMDD>/`，可人工取回。

启动时按 `[agent] backup_retention_days` 清理过期版本。清理失败只留痕，不阻断启动。

## `[context]`

上下文压缩。会话的近期记忆按原文保留，更早的轮次压缩成摘要：末尾 `full_user_rounds` 个用户轮不压，只压它们前面的轮次；前面没有可压的轮次时，连这些轮次一起压。

```ini
[context]
summary_token_fallback   = 64000
full_user_rounds         = 5
summary_output_max_chars = 5000
image_turns              = 1
image_max                = 8
reasoning_replay_tokens  = 8000
```

| 键 | 缺省或留空时 | 含义 | 建议范围 |
|---|---|---|---|
| `summary_token_fallback` | `64000` | 仅在当前模型没有声明 `context_window` 时使用的回退压缩阈值；不提供设置页入口 | 正整数 |
| `full_user_rounds` | `5` | 压缩时保留最近对话轮数：末尾这么多用户轮不压，只压它们前面的；前面没有可压的轮次时，这些轮次也会被压缩 | `1`–`10` |
| `summary_output_max_chars` | `5000` | 摘要的篇幅上限，单位为字。它作为约束写进摘要提示词，实际长度由模型遵守程度决定 | `2000`–`8000` |
| `image_turns` | `1` | 只保留**最近这么多轮用户发言**里的图片，更早用户轮里的图片转文本占位。`0` = 不带用户轮图片，负数 = 不限；工具返回的图片不受此键限制 | `0` / 正整数 / 负数 |
| `image_max` | `8` | 进入模型请求的图片总数上限；**保留最新的图片**，超量时先丢弃最老的。`0` = 一张都不带，负数 = 不限 | `0` / 正整数 / 负数 |
| `reasoning_replay_tokens` | `8000` | 思维链回传预算（token）。`-1` = 全量回传；`0` = 不回传；正数 = 超出就**取两头、中间以 `…<此处省略约 N token 的推理>…` 代替**（模型可据前后文推断中间）。思维链是模型的中间输出，必然未命中缓存，全量回传会让每次请求多背这些 token | `-1` / `0` / 正数 |

有模型窗口时，实际压缩阈值 = `floor(context_window × compression_percent / 100)`；`compression_percent` 是模型条目字段，默认 70，范围 10–90，超出范围回落 70。没有模型窗口时使用 `summary_token_fallback`。

图片只从**发给模型的请求**里被裁掉，事实流里的字节不动——历史回显与重新提问都还能拿到原图。

「缺省或留空时」是 `config.ini` 缺该节或缺该键时生效的值。

机制细节见 [context.md](../subsystems/context.md)。

## `[update]`

```ini
[update]
check_interval_minutes = 30
```

| 键 | 默认 | 含义 |
|---|---|---|
| `check_interval_minutes` | `30` | 自动检查更新的间隔，单位为分钟；取值限制在 `1`–`1440` |

## 插件

插件的装载在**另一份文件** `plugins.ini`（工程根）。节在就进入装载候选；开关写在该节的 `enabled`（缺省为 `1`）。名字、描述、图标、版本由 `plugin-meta.json` 声明。插件自己的键写在 `plugin-config.ini` 里，通常位于 `[config]` 节；`multi_model` 使用 `[model:<id>]` 节。

```ini
[plugin:skills]

[plugin:knowledge]
enabled = 1
```

| 名称 | 能力 | 自己的配置文件 |
|---|---|---|
| `skills` | Skills 库（内置 + 外置）与 `skills` 工具 | `plugins/skills/plugin-config.ini` |
| `rules` | `rules/` 下的 `.md` 全量注入上下文 | 无配置（只有开关）；见 [Rules](../subsystems/rules.zh.md) |
| `knowledge` | 本地知识库检索 | `plugins/knowledge/plugin-config.ini` |
| `ai_speak` | 人类口语播报与语音播放 | `plugins/ai_speak/plugin-config.ini` |

**节的先后即上下文组装顺序**：越不容易变动的插件排在越前面。

**插件自己的配置跟着插件走。** `ai_speak` / `visual_operator` / `knowledge` / `skills` 的配置入库；`multi_model` 的密钥配置被 `.gitignore` 排除；**内核的 `config.ini` 里没有插件设置**。插件的目录形态、可贡献的能力与开发方式见 [插件](../subsystems/plugins.md)。

## HTTP 鉴权

Web 服务默认只绑定 `127.0.0.1`；绑定回环地址时，`auto` 与 `local` 模式免登录。`auto` 与 `required` 模式下，绑定非回环地址前必须有凭据；`local` 则直接拒绝。设置访问密码：

```bash
agent-web --set-password
```

`[auth]`：

```ini
[auth]
; auto / required / local
mode = required
session_hours = 12
max_failures = 5
lock_seconds = 300
trusted_proxies =
allowed_hosts = 127.0.0.1,localhost,::1
cookie_secure = auto
provider_module =
; GUI 一次性 bootstrap 自动登录；浏览器始终需要登录
desktop_auto_login = 1
```

```text
auto      回环绑定免登录；非回环强制登录；允许公网绑定
required  任何地址都必须登录
local     回环绑定免登录；非回环直接拒绝启动
```

`local` 与 `auto` 的回环行为相同；差别是 `local` 拒绝非回环绑定，`auto` 允许公网绑定但要求登录。

非回环地址没有凭据时拒绝启动。

`required` 模式下浏览器始终需要登录。桌面 GUI 使用一次性 bootstrap token 自动建立会话；token 由启动器生成，只通过 WebView URL fragment 传递，浏览器无法获得。

`allowed_hosts` 是 Host 白名单，默认只接受 `127.0.0.1`、`localhost`、`::1`；公网域名或反向代理域名必须显式加入。`trusted_proxies` 接受 IP 或 CIDR，且只对列表内的代理读取 `X-Forwarded-For` 与 `X-Forwarded-Proto`。

缺少 `[auth]` 节时 `mode` 回落 `auto`；仓库的 `config.ini` 使用 `required`。`required` 模式下，没有凭据的非 GUI 服务拒绝启动，需先执行 `agent-web --set-password`。

鉴权文件写入 `data/auth/`。Windows 使用 DACL；Linux/macOS 使用 `0700` 目录与 `0600` 文件。所有鉴权目录都无法收紧权限时拒绝启动。权限被外部改宽时，启动会先重置并重新收紧；如果仍无法收紧（例如 Windows 上 deny ACE 让 `icacls /reset` 失败），启动回退到 `data/auth2` 至 `data/auth9`。旧目录保留但不再读取；新目录不复制旧密码或 Token。`required` 模式下且 `desktop_auto_login = 1` 时，没有凭据的 GUI 启动会生成新密码继续运行；没有凭据的非 GUI 启动则拒绝，需先执行 `agent-web --set-password`。

此时生成的密码写入当前鉴权目录的 `initial-password.txt`（默认 `data/auth/`）；GUI 仍通过一次性引导令牌直接打开，浏览器登录使用该文件中的密码。

公网绑定必须提供 TLS：

```bash
agent-web --host 0.0.0.0 --tls-cert cert.pem --tls-key key.pem
```

或显式允许无 TLS：

```bash
agent-web --host 0.0.0.0 --allow-insecure-public
```

反向代理必须使用 `mode = required`，不能依赖回环地址免登录。

密码、会话和 API Token：

```bash
agent-web --set-password
agent-web --issue-token ci --scope chat,read
agent-web --revoke-token ci
```

凭据写入 `data/auth/`，不进入发布包。

## 启动参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--host` | `127.0.0.1` | 绑定地址 |
| `--port` | `8765` | 端口 |
| `--data-root` | `<工程根>/data` | 数据目录 |
| `--fs-root` | 本机各盘根（非 Windows 平台为工程根） | 文件可见范围。**可重复传** |
| `--media-root` | 空；全部 `--fs-root` | `/api/media` 显式可读根；为空时使用全部可见根 |
| `--open` | 关闭 | 启动后打开浏览器 |
| `--set-password` | 无 | 交互式设置访问密码后退出（至少 12 位） |
| `--issue-token NAME` | 无 | 创建 API Token 后退出；同名已存在时拒绝 |
| `--revoke-token NAME` | 无 | 撤销 API Token 后退出 |
| `--scope` | `read` | API Token scope，逗号分隔；可取 `read` / `chat` / `write` / `admin` |
| `--tls-cert` | 空 | TLS 证书；公网绑定必须提供（`--allow-insecure-public` 除外） |
| `--tls-key` | 空 | TLS 私钥；公网绑定必须提供（`--allow-insecure-public` 除外） |
| `--allow-insecure-public` | 关闭 | 显式允许无 TLS 公网 HTTP |

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
| `AI_AGENT_LLM_LOG` | 模型请求日志落盘路径，缺省为 `%TEMP%\fan_agent_llm_requests.log` |

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
| `data/wake/` | 唤醒任务及其投递状态 |
| `data/mesh/runs/` | 运行态登记（`<cid>.json`） |
| `data/workspace/` | `/workspace/` 静态路由根 |
| `data/recycle/` | 删除操作的回收目录 |
| `data/plugin/<插件名>/` | 插件专属存储（插件只看到自己那一层） |
| `data/cache/` | 派生缓存，含会话加密密钥 |
| `data/auth/` | 密码凭据、API Token、鉴权日志；不进入发布包 |
| `data/logs/errors.log` | 进程错误日志（JSONL；内核/插件装配与宿主运行异常；工具业务失败收成 `ToolResult` 后不记此处；超约 2MB 轮转为 `errors.log.1`） |

目录都是按需惰性创建的：全新克隆没有 `data/`，跑过一次才会出现用到的那几个。

## 延伸阅读

- [架构](../architecture.zh.md)
- [术语](../glossary.zh.md)
- [上下文管理](../subsystems/context.md)
