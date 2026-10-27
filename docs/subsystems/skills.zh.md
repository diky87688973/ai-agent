[English](skills.md) | **中文**

# Skills（`skills` 插件）

Skills 是**供模型按需读取的说明文档**：若干 `.md`，每条带名字与描述。
`plugins/skills` 插件提供 Skills 库、`skills` 工具、两段上下文注入，以及 `## 资源目录`
系统提示词章节；移除 `[plugin:skills]` 节后，这些能力一起消失，内核不受影响。
Skills 有两个来源：随仓库发布的内置目录，以及用户配置的外置目录。

插件怎么组织、扩展点怎么用见 [plugins.md](plugins.zh.md)。

## 渐进式披露

Skills 正文**不全量塞进请求**，按三层给：

| 层 | 内容 | 什么时候进上下文 |
|---|---|---|
| 第一层 | 普通 Skills 清单（名字 + 描述） | 每次请求常驻 |
| 第二层 | `auto_load/` 目录下 Skills 的正文 | 每次请求常驻 |
| 第三层 | 其余 Skills 的正文 | **不进上下文**，模型用 `skills action=read` 按需读取 |

空清单或空正文不注入。仅凭清单即可判断该用哪个 Skills，判断之后才去读正文。
清单是索引，正文是内容；两者分开是这套披露的核心。

## 目录形态

内置来源固定为 `<项目根>/skills`，目录形态示例：

```text
<项目根>/skills/
  auto_load/            这个子目录下的 Skills 正文始终随上下文携带
    python-coding.md
  engineering/
    code-review.md      子目录名进 Skills 名：`engineering/code-review`
  context-dump.md       根目录下的 Skills：上下文导出指导
  writing.md            根目录下的 Skills
```

外置来源由 `dir` 指定，目录形态与内置来源完全一致：

```text
<用户 dir>/
  auto_load/
  engineering/
  writing.md
```

两个来源都扫描；同名时外置覆盖内置。Skills 名取各自根下的相对路径去掉 `.md`；
`auto_load/` 里的 Skills 名仍带这个前缀（`auto_load/python-coding`）。

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
| `dir` | **用户外置** Skills 目录。相对路径按工程根解析；未配置或不存在时内置来源仍可使用 |
| `max_file_size` | 单个 Skills 文件的字节上限，超过则截断；留空取 200000 |

内置来源固定为 `<项目根>/skills`，不受 `dir` 影响。配置文件在插件自己目录下，
随插件目录一起部署、一起删除；内核的 `config.ini` 里没有这一节。
`AI_AGENT_SKILLS_DIR` 环境变量能覆盖 `dir`，为测试与 CI 提供独立的外部目录入口。

## 元数据

`library.SkillManager` 扫描两个来源。Skills 名取各自根下的相对路径去掉 `.md`；
`description` 取自 frontmatter。frontmatter 里的 `name` 不覆盖路径名。

```markdown
---
name: python-coding
description: 写 .py 前后要遵守的工程约定
---

正文……
```

缺 frontmatter 时描述留空（清单里显示 `（无描述）`），名字仍来自路径。
扫描结果按文件修改时间缓存，有变化就重扫。

## 注入的两段与抬头

插件注册**两条上下文注入源**，共用插件名 `skills` 作为段 key：

| 段名 | 内容 | 抬头 |
|---|---|---|
| `Skills 清单` | 一行读取提示，随后每条 Skills 一行（名字 + 描述） | `【Skills 清单】`，下分 `【内置 Skills 清单】` / `【用户 Skills 清单】`（有内容才出现） |
| `Skills 常驻` | 两个来源 `auto_load/` Skills 的正文，每个 Skills 一条消息 | `【内置 Skills <名字>】` / `【用户 Skills <名字>】` |

两条注入在分层视图里各占一行。

## 系统提示词：资源目录

插件向系统提示词注册 `## 资源目录` 章节；内置 Skills 根与用户 Skills 根由插件在运行时计算，
不写死绝对路径。

```text
## 资源目录
- 内置skills: <项目根>/skills
- 外置skills: <用户 dir>
```

未配置外置目录时，该章节为：

```text
## 资源目录
- 内置skills: <项目根>/skills
- 外置skills: 未配置
  外置skills目录为用户skills目录，当前未配置外置skills目录，必要时提醒用户在"Skills"插件中配置dir即可
```

`dir` 已配置但目录不存在时，该行变成 `- 外置skills: <路径>（不存在）`。

该章节是系统提示词的一部分，不占独立的上下文段。Rules 插件向同一章节追加
`- 规则rules:` 行与编辑提示；该字面是模型侧的识别标记。

来源抬头只给模型看，UI 层不显示来源，两个上下文段保持各自的段名与数量。抬头让模型
分清这是 Skills 说明，不是用户对话，也不是知识库素材。两条上下文注入都位于系统提示词
之后、知识库之前，顺序按 `plugins.ini` 里的插件位次；`## 资源目录` 属于系统提示词本身。
它们只会因为文件或配置改变而变化（见 [context.md](context.zh.md)）。

## 可用 Skills 数

分层视图里 `Skills 清单` 段显示形如 `N个` 的数量。这个数由 Skills 库给出，
即 `SkillManager.list_skills()` 的长度，只算普通 Skills，不含常驻的 `auto_load/` Skills；
它不是清单正文的行数。

## `skills` 工具

```json
{"action": "list"}
{"action": "read", "name": "engineering/code-review"}
```

| action | 行为 |
|---|---|
| `list` | 列出普通 Skills（名字 + 描述） |
| `read` | 读某个 Skills 的正文（超过上限时截断）；名字找不到时抛 `SkillLookupError` 并附可用清单 |

用户 Skills 根写在系统提示词的 `## 资源目录` 章节里；`skills` 工具描述保持固定，
不携带环境路径。未配置外置目录时，`资源目录` 会明确标出，模型据此在必要时提醒用户
在"Skills"插件中配置 `dir`；目录已配置但不存在时，该行标成 `（不存在）`。
`skills` 只做 list / read，不复制、不迁移、不落盘。

## 装载与配置

装载由 `plugins.ini` 的 `[plugin:skills]` 节控制：没有该节插件不装载；
`enabled = 0` 时保留在清单里但不装载。插件自己的设置文件是 `plugins/skills/plugin-config.ini`。

## 延伸阅读

- [plugins.md](plugins.zh.md)：插件系统契约、扩展点、界面资产
- [context.md](context.zh.md)：组装顺序与内核-插件协同
- [guide/config.md](../guide/config.zh.md)：内核配置项
