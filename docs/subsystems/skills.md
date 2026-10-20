# Skills（`skills` 插件）

Skills 是**给模型按需读取的说明文档**：一个目录下的若干 `.md`，每条带名字与描述。
Skills 库、`skill_manage` 工具、以及它在上下文里的两段注入，全部由 `plugins/skills`
这个插件提供 —— 移除 `[plugin:skills]` 节后，这些能力一起消失，
内核不受影响。

插件怎么组织、扩展点怎么用见 [plugins.md](plugins.md)；这里只讲这个插件本身。

## 渐进式披露

Skills 正文**不全量塞进请求**，按三层给：

| 层 | 内容 | 什么时候进上下文 |
|---|---|---|
| 第一层 | 可用 Skills 清单（名字 + 描述） | 每次请求常驻 |
| 第二层 | `auto_load/` 目录下 Skills 的正文 | 每次请求常驻 |
| 第三层 | 其余 Skills 的正文 | **不进上下文**，模型用 `skill_manage action=read` 按需读取 |

仅凭清单即可判断该用哪个 Skills，判断之后才去读正文。
清单是目录，正文才是内容 —— 两者分开，是这套披露的全部意思。

## 目录形态

```
<Skills 目录>/
  auto_load/            这个子目录下的 Skills 正文**始终随上下文携带**
    python-coding.md
  engineering/
    code-review.md      子目录名进 Skills 名：`engineering/code-review`
  writing.md            根目录下的 Skills
```

Skills 名取相对路径去掉 `.md`；`auto_load/` 里的 Skills 名仍带这个前缀
（`auto_load/python-coding`），便于在清单与常驻正文之间对上。

## 配置

```ini
; plugins/skills/plugin-config.ini
[config]
dir =
max_file_size = 200000
```

身份在 `plugin-meta.json`，开关在 `plugins.ini`。

| 键 | 说明 |
|---|---|
| `plugin-meta.json` | 身份：`name`、`desc`、`icon`、`version` |
| `dir` | Skills 目录。相对路径按**工程根**解析；留空或目录不存在则 Skills 库为空、注入为空，不报错 |
| `max_file_size` | 单个 Skills 文件的字节上限，超过则截断；留空取 200000 |

配置在插件自己目录下，随插件一起装卸、一起删除；内核的 `config.ini` 里没有这一节。
`AI_AGENT_SKILLS_DIR` 环境变量能覆盖 `dir`，为测试与 CI 提供独立的数据目录入口。

## 元数据

`library.SkillManager` 扫描目录，从 frontmatter 取 `name` 与 `description`：

```markdown
---
name: python-coding
description: 写 .py 前后要遵守的工程约定
---

正文……
```

缺 frontmatter 时用文件名当名字、描述留空（清单里显示"（无描述）"）。
扫描结果带修改时间缓存，目录一变自动重扫。

## 注入的两段与抬头

插件注册**两条**注入源，都挂它自己那一段（段 key 是插件名 `skills`）：

| 段名 | 内容 | 抬头 |
|---|---|---|
| `Skills 清单` | 名字 + 描述的行列表 | `【Skills 清单】` |
| `Skills 常驻` | `auto_load/` Skills 的正文，一条一段 | `【Skills <名字>】` |

抬头让模型一眼分清这是 Skills 说明，不是用户对话、也不是知识库素材。
两者都固定在"系统提示词之后、知识库之前"，因为它们只会因为改文件而变
（见 [context.md](context.md)）。

## 可用 Skills 数

分层视图里 `Skills 清单` 段显示"31 个"，这个数由 Skills 库给出
（`SkillManager.list_skills()` 的长度），**不从清单正文数行数** ——
描述里带换行会把行数算错。

## `skill_manage` 工具

```json
{"action": "list"}
{"action": "read", "name": "engineering/code-review"}
{"action": "copy", "source": "/srv/inbox/review.md", "name": "review"}
```

| action | 行为 |
|---|---|
| `list` | 列出可用 Skills（名字 + 描述） |
| `read` | 读某个 Skills 的正文（超过上限时截断）；找不到时抛 `SkillLookupError` 并附可用清单 |
| `copy` | **两段式**：先返回预览（`confirm_id`、`would_overwrite`），确认后才落盘 |

`copy` 的提交走内核的 `commit_write`：插件用 `ctx.add_executor("skill_manage", fn)`
登记执行器，提交那一刻按工具名取。落盘受写盘四步协议与门控约束，与内置写类工具
走同一条路。

## 一起改的地方

- `plugins.ini` 里的 `[plugin:skills]` 节 —— 没有它插件不装载；
- `plugins/skills/plugin-config.ini` —— 插件自己的设置，只有这一处。

## 延伸阅读

- [plugins.md](plugins.md)：插件系统契约、扩展点、界面资产
- [context.md](context.md)：组装顺序与内核-插件协同
- [guide/config.md](../guide/config.md)：内核配置项
