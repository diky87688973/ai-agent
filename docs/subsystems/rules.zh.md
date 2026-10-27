[English](rules.md) | **中文**

# Rules（`rules` 插件）

Rules 是**规则目录**：`<项目根>/rules/` 下的每个 `.md` 文件，一行一条地
以 `system` 身份进上下文，一个文件对应一条消息。插件机制本身见
[plugins.md](plugins.md)。

**名称约定**：Rules 是「规则」这一整体，用户规则只是其中一种（同样可以有系统规则），
因此插件、文档与界面统一叫 **Rules**，不称它「用户规则」。提示词里给模型看的
识别标记是 `- 规则rules:`（资源目录行）与 `【规则 Rules <路径>】`（正文抬头）。

## 两个 `rules`，别混

| 路径 | 是什么 |
|---|---|
| `plugins/rules/` | 插件代码（`plugin.py` + `plugin-meta.json`） |
| `<项目根>/rules/` | 规则文件目录，与 `skills/` 平级。**用户编辑规则就在这里** |

插件目录里没有 `plugin-config.ini`、没有 `settings-schema.json`、没有 `ui/` ——
本插件没有任何可编辑的设置，设置页因此不给它「设置」按钮（由
`plugin-meta.json` 的 `config: "false"` 声明，见
[plugins.md](plugins.md#插件自己的配置)）。

## 包结构

```
plugins/rules/
  plugin.py            入口：规则目录扫描、读取、注入与资源目录章节
  plugin-meta.json     身份元数据（name / desc / icon / version / config）
rules/                 规则文件目录（与 skills/ 平级）
  USER_RULES.md        系统自带的规则文件（初始为空，写进去就生效）
  <其它规则>.md
```

`USER_RULES.md` 是**约定的落点**：系统要把规则写给用户看、或用户口头交代一条规矩
需要留档时，写进这个文件即可；它和目录里其它 `.md` 完全同等对待，没有特殊逻辑。

## 收录规则

- 递归扫描 `<项目根>/rules/`，只收 `.md`；
- 任一段以 `.` 开头的隐藏路径、`__pycache__` 跳过；
- 按相对路径排序，注入次序稳定；
- 单文件上限 **200000 字节**（代码常量，不提供配置）；超限的跳过并留一条
  `rules.too_large` 错误留痕，不静默丢；
- 空文件（正文只有空白）不占条目 —— `USER_RULES.md` 初始为空，此时 Rules 段计数为 0；
- 目录不存在时插件仍在（段占位、计数 0），只是不注入任何正文。

## 注入

每个规则文件产出一条 `system` 消息，抬头是相对路径：

```
【规则 Rules project-audit.md】
<文件正文>
```

`label` 是 `Rules`、`count` 是实际注入的文件数，两者随注入源一起声明。
组装位次取 `plugins.ini` 里的位次（本插件排在 `skills` 之后），
见 [context.md](context.zh.md#组装顺序)。

正文读取按 `(路径, mtime_ns, 大小)` 缓存：同一趟装配多次收集只读一次磁盘，
文件改动后缓存自动失效。

规则段不参与摘要压缩：插件段每趟装配重新收集，规则不会因为压缩而消失，
代价是每轮都付这份 token。

## 系统提示词：资源目录

本插件向 `## 资源目录` 章节追加两行（与 Skills 插件同一标题，正文按清单位次
合并到同一个章节）：

```
- 规则rules: <项目根>/rules
  该目录中规则文件（*.md）会自动注入到上下文，为用户编辑规则时请在该目录下操作，USER_RULES.md 为默认用户规则文件
```

目录不存在时该行标成 `- 规则rules: <路径>（不存在）` —— 不假装正常。

## 上下文视图里的用量

上下文分层里的段 key 是 `plugin:rules`，段名 `Rules`（绿色）。
界面那一条显示「Rules | 占比 | N 个 | tokens」，即规则文件数与它占的 token。
见 [context.md](context.zh.md#分段统计)。

## 热开关

`plugins.ini` 的 `[plugin:rules]` 节控制装载。设置页拨开关会立即卸载/装载插件：

- 卸载：注入源、`## 资源目录` 那两行、段色一起撤销（三项都由 disposer 记账）；
- 装载：重新注册，注入立刻恢复。

不刷新页面时会话里的注入已经生效（它发生在服务端装配期）；界面上的段色要等
下一次开屏才刷新（与其它插件同一条已知限制）。

## 延伸阅读

- [plugins.md](plugins.md)：插件包形态、扩展点与生命周期
- [context.md](context.md)：注入源如何进入装配、分段统计与组装顺序
- [skills.md](skills.md)：同为 `## 资源目录` 的贡献者
