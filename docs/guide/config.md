# 配置

配置文件是仓库根目录的 `config.ini`，从 `config.ini.example` 复制后填写：

```bash
cp config.ini.example config.ini
```

`config.ini` 不入版本库（见 `.gitignore`），只提交无密钥的模板。缺省值与全部键见下。

插件清单是另一份文件 `plugins.ini`（工程根），它**入库**——里面没有密钥，列的是装载哪些插件。见 [插件](../subsystems/plugins.md)。

## `[model_reasoning]`

模型网关。`api_key` 与 `api_base_url` 都必须有值（缺任一项时服务启动即报错退出）；`model` 可缺省，取内置默认值。

```ini
[model_reasoning]
api_base_url = https://api.deepseek.com
api_key      = 你的 API Key
model        = deepseek-flash
models       = deepseek-flash, deepseek-v4-pro
```

| 键 | 内置缺省 | 含义 |
|---|---|---|
| `api_base_url` | `https://api.deepseek.com` | 网关地址。地址推导见 [llm.md](../subsystems/llm.md) |
| `api_key` | 空 | 鉴权密钥。**留空时服务启动失败**（壳层装配阶段报错退出，退出码 2） |
| `model` | `deepseek-v4-flash-vision-exp` | 默认模型名；配置里给了值就以它为准 |
| `models` | 空 | 会话内可选的模型名，逗号分隔。留空则只能用 `model` |

接口需兼容 OpenAI Chat Completions 格式。

## `[agent]`

```ini
[agent]
reasoning_effort = max
backup_retention_days = 7
user_rules_file =
```

| 键 | 默认 | 含义 |
|---|---|---|
| `reasoning_effort` | `max` | 全局推理档位。`max` = 深度推理，`high` = 标准推理。会话内可在界面上临时切换，**会话级选择优先** |
| `backup_retention_days` | `7` | 版本化备份保留天数。启动时清理更早的；`0` = 永久保留 |
| `user_rules_file` | 空 | 用户自定义规则文件（`.md` / `.txt`）。留空则不加规则段 |

`reasoning_effort` 的取值直接进请求体的 `reasoning_effort` 字段。值非法时回落 `max`。

规则文件是**纯文本**，正文会被拼进系统提示的「用户自定义规则」段，内容自定。

- 相对路径按项目根解析，也可以给绝对路径
- 文件不存在、不是文件或读失败 → **静默不加载**，不报错
- 长度上限 `20000` 字符，超出截断并附一句说明

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

上下文压缩。会话在内存中分三段：近期记忆、远期记忆、摘要。近期与远期按原文保留，超出保留窗口的远期轮次压缩成摘要。

```ini
[context]
summary_token_threshold  = 700000
full_user_rounds         = 10
pure_user_rounds         = 10
summary_output_max_chars = 5000
image_turns              = 3
image_max                = 10
```

| 键 | 缺省或留空时 | 含义 | 建议范围 |
|---|---|---|---|
| `summary_token_threshold` | `8000` | 上下文估算 token 数超过此值时触发压缩。调大保留更多原文、请求更贵；调小更省但更早丢失细节 | `60000`–`1000000` |
| `full_user_rounds` | `6` | 近期记忆保留的用户轮数，始终按原文发送 | `4`–`20` |
| `pure_user_rounds` | `2` | 远期记忆额外缓冲的轮数，超过 `full + pure` 的部分才压缩 | `1`–`20` |
| `summary_output_max_chars` | `2000` | 摘要的篇幅上限，单位为字。它作为约束写进摘要提示词，实际长度由模型遵守程度决定 | `2000`–`8000` |
| `image_turns` | `3` | 只把**最近这么多轮用户发言**里的图片带进模型请求，更早的转文本占位。`0` = 一张都不带，负数 = 不限 | `1`–`10` |
| `image_max` | `10` | 这几轮里最多带几张图；**最近一轮优先保**，超量的从最老的那一轮开始砍。`0` = 一张都不带，负数 = 不限 | `1`–`30` |

图片只从**发给模型的请求**里被裁掉，事实流里的字节不动 —— 历史回显与重新提问都还能拿到原图。

「缺省或留空时」是 `config.ini` 缺该节或缺该键时生效的值；`config.ini.example` 给出的是上例中的值。

机制细节见 [context.md](../subsystems/context.md)。

## 插件

插件的装载在**另一份文件** `plugins.ini`（工程根），不在 `config.ini` 里：列出即装载。

```ini
[plugin:knowledge]
version = 1.0

[plugin:tts]
```

| 名称 | 能力 | 自己的配置文件 |
|---|---|---|
| `knowledge` | 本地知识库检索 | `plugins/knowledge/config.ini` |
| `tts` | 语音合成 | `plugins/tts/config.ini` |

**插件自己的配置跟着插件走。**
每个插件目录下都有 `config.ini.example` 作为模板。
插件的目录形态、可贡献的能力与开发方式见 [插件](../subsystems/plugins.md)。

## `[skills]`

技能库目录。留空禁用。

```ini
[skills]
dir           =
max_file_size = 200000
```

相对路径按项目根解析；目录不存在时静默降级为"未启用"，不报错。

## `[model_pricing]`

覆盖内置费率表。值为内联 JSON，或指向一个 JSON 文件的路径。

```ini
[model_pricing]
rates = {"deepseek-flash": {"cache_hit_cny_per_m": 0.04, "cache_miss_cny_per_m": 2.0, "output_cny_per_m": 8.0}}
```

| 字段 | 含义 |
|---|---|
| 三项费率 | `cache_hit_cny_per_m` / `cache_miss_cny_per_m` / `output_cny_per_m`，单位为元 / 百万 tokens，分别对应缓存命中输入、缓存未命中输入、输出 |

键为模型名前缀，取最长匹配。一行必须三项齐全且为数字，缺项或非数字时该行不生效；整段无法解析时回落内置表。留空使用内置表。

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
| `AI_AGENT_LOCK_TIMEOUT` | 跨进程锁等待秒数，默认 30 |
| `AI_AGENT_LOG_REQUESTS` | 设为 `0` 关闭发送前的请求摘要，默认开启 |
| `AI_AGENT_LLM_LOG` | 模型收发日志落盘路径，缺省为 `%TEMP%\fan_agent_llm_requests.log` |

## 数据目录

运行时数据在 `data/` 下，不入版本库。用 `--data-root` 或 `AI_AGENT_DATA_ROOT` 指到别处。

| 目录 | 内容 |
|---|---|
| `data/sessions/` | 会话事实日志 |
| `data/titles/` | 会话标题 |
| `data/todo_lists/` | 执行清单状态 |
| `data/temp/` | 临时产物（写盘前备份见上节「文件备份」） |
| `data/mesh/` | 会话间消息（`agents.json` 注册表 + `inbox/<cid>.jsonl` 队列） |
| `data/mesh/runs/` | 运行态登记（`<cid>.json`） |
| `data/workspace/` | `/workspace/` 静态路由根 |
| `data/recycle/` | 删除操作的回收目录 |
| `data/plugin/<插件名>/` | 插件专属存储（插件只看到自己那一层） |
| `data/cache/` | 派生缓存，含会话加密密钥 |

目录都是按需惰性创建的：全新克隆下只有 `data/` 本身，跑过一轮才会出现用到的那几个。

## 延伸阅读

- [架构](../architecture.md)
- [术语](../glossary.md)
- [上下文管理](../subsystems/context.md)
