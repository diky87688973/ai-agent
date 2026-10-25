# 知识库（`knowledge` 插件）

知识库把本地目录里被勾选的文本与表格作为会话的随附资料注入上下文。
配置判定、路径安全、文件读取、勾选状态、注入与界面全部由本插件提供；
内核只提供通用扩展点。插件机制本身见 [plugins.md](plugins.md)。

## 包结构

```
plugins/knowledge/
  plugin.py                  入口：配置读取、文件层、勾选状态、注入与端点
  plugin-config.ini          真实配置（入库）
  plugin-meta.json           身份元数据
  ui/panel.js                右栏面板脚本
  ui/panel.css               面板样式
```

## 配置

```ini
; plugins/knowledge/plugin-config.ini
[config]
dir =
max_file_size = 200000
extra_suffixes =
```

身份在 `plugin-meta.json`，开关在 `plugins.ini`。

| 键 | 缺省 | 说明 |
|---|---|---|
| `dir` | 空 | 知识库根目录。相对路径按**工程根**解析；留空、不存在或不是目录时插件不提供任何文件，所有操作返回空 |
| `max_file_size` | `200000` | 单文件字节上限，超过则不读取；`0` 表示不限 |
| `extra_suffixes` | 空 | 追加收录的扩展名，英文逗号分隔，`txt` 与 `.txt` 等价；写错只忽略该项 |

`plugins.ini` 的 `enabled` 为 `0` 时插件留在清单里但不装载。`name` / `icon` 来自 `plugin-meta.json`，
面板标题与输入区按钮文案。

## 可收录的文件

- 文本类扩展名见 `TEXT_SUFFIXES`（`.md` `.txt` `.csv` `.json` `.yaml` `.ini`
  `.py` `.js` `.html` `.css` 等），以及配置追加的 `extra_suffixes`；
- `.xlsx` / `.xls` / `.xlsm` 按表格解析，需要 `openpyxl`；缺库时该文件不可勾选，
  并在校验结果里给出安装提示；
- 无扩展名的文件按文本对待（`Dockerfile` / `Makefile` / `README` 等）；
- 隐藏路径（任一段以 `.` 开头）、`__pycache__` 与非文本文件不列出，也不可勾选。

`list_files()` 只列通过同一套校验的文件，界面因此不会出现「能看见但勾不了」的条目。

## 路径安全

`safe_resolve(rel)` 把相对路径解析到根目录下的真实文件，任一条件不满足即返回 `None`：

- 空值、绝对路径、含 `..` 的路径；
- 任一段以 `.` 开头的隐藏路径；
- 解析后的真实路径不在根目录内；
- 目标不是文件或不存在。

文件的字节上限、可收录类型与表格依赖在 `file_allowed()` 里二次校验；勾选写入前、
每次注入前都会重新走一遍，磁盘上的文件被替换后不会绕过规则。

## 勾选状态

勾选**按会话**记录，键是会话 id，值是相对路径集合：

- 状态落在 `<数据根>/plugin/knowledge/checked_state.json`，启动时全量读入；
- 文件缺失或损坏时保持空集，不报错；
- 写盘失败静默：勾选是界面偏好，不阻断当前会话的注入；
- 写入采用全量替换：列表为空时清除该会话的勾选；
- 不通过校验的路径直接丢弃，返回值是实际接受的路径。

勾选变化会调用宿主注册表的 `bump_context_sources`，使装配侧丢掉缓存的收集结果；
取不到该钩子时退化为下一轮生效。

## 注入

`build_system_messages(cid)` 为每个勾选文件产出一条系统消息：

```
【知识库：docs/guide.md】
<文件正文>
```

正文读取按 `(路径, mtime, 大小)` 缓存，同一趟装配多次收集只读一次磁盘，文件改动后
缓存自动失效。表格转成「`[Sheet: 名称]` + 制表符分隔的行」，单表解析失败只产出
一行说明，不影响同批其它文件。空文件不注入。

注入源声明 `label` 与 `count`：段名用于界面与分层，`count` 是实际可注入的文件数。
组装位次由 `plugins.ini` 里的插件顺序决定，见 [context.md](context.md#组装顺序)。

## 端点

前缀 `/api/plugin/knowledge/`：

| 方法与路径 | 请求 | 响应 |
|---|---|---|
| `GET files` | — | `{ok, enabled, files: [{path, name, mtime}]}`；未启用时 `files` 为空 |
| `GET checked` | 查询串 `conversation_id` | `{ok, checked: [相对路径]}` |
| `PUT checked` | 体 `{conversation_id, checked: [...]}` | `{ok, checked: [实际接受的路径]}`；缺会话 id 返回 400 |

`path` 一律是相对根的 POSIX 风格路径，界面回传同一形状。

## 面板

右栏面板加载 `ui/panel.js` 与 `ui/panel.css`，脚本经 `window.aiAgentPlugins`
调本插件端点。面板按会话取勾选，会话切换时重新取数；小标题右侧的刷新按钮重新读取
知识库目录。目录未配置、为空或加载失败时，面板分别显示对应状态，不隐藏面板本身。

插件登记了上下文段外观（`add_ctx_segment_style`，颜色 `blue`）与输入区动作按钮，
点击按钮打开同名面板。

## 延伸阅读

- [plugins.md](plugins.md)：插件包形态、扩展点与生命周期
- [context.md](context.md)：注入源如何进入装配与分段统计
- [tools.md](tools.md)：写盘协议（知识库本身只读）
- [../guide/config.md](../guide/config.md)：配置项总表
