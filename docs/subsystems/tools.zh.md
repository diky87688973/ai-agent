[English](tools.md) | **中文**

# 工具

工具是模型能对外界做的事。实现在 `agent/capabilities/`，执行管道与写盘门控在 `agent/core/tool_call.py` 与 `agent/mechanisms/quality/`。

## 注册

```python
class ToolPlugin:
    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {}          # 参数名 → JSON Schema 片段
    label: str = ""                          # 界面短名
    icon: str = ""                           # 单字符图标
    parallel_safe: bool = False
    needs_preview: bool = False              # 写类预览：插件工具走同一门控
    write_path_keys: Tuple[str, ...] = ()    # 写目标路径的参数键序
    needs_reread: bool = False               # 内容写：落盘后再改须先重读

    def execute(self, arguments: Dict[str, Any]) -> Any: ...
```

注册进 `ToolRegistry`：

```python
registry.register(plugin)   # 返回 disposer（注销句柄）
registry.get(name)          # 未注册返回 None
registry.names()            # 已注册的工具名（排序后）
registry.schemas()          # 导出模型可见的工具声明
```

三条约束：

- **注册表只存不跑**。执行调度与门控由管道这个唯一入口统一承载。
- `name` 唯一。空名、重名、`execute` 不可调用、`parameters` 不是 dict，注册时都会被拒。
- `execute` 返回任意可序列化值。**异常由管道捕获**成失败结果结构化回灌，单步失败不终止回合。

注册返回幂等 disposer；调用它即注销插件。这是插件热装卸的地基。

## 条件注册与生命周期

有些工具依赖运行时服务，不能在无依赖的装配中注册：

| 工具 | 注册条件 | 生命周期 | 依赖边界 |
|---|---|---|---|
| `subagent` | `build_app(store=...)` 注入持久化存储 | 父会话工具；随 `SubagentManager` 创建、`App.dispose()` 关闭 | `agent/subagent` 持有批次与会话；壳层只经服务调用 |
| `subagent_send` | 同上，仅子会话工具视图 | 子会话工具；随父管理器生命周期 | 只允许发给直属父会话 |

无 store 的默认装配不注册这两个工具，因此 `catalog/tools.json` 不列出它们；这是条件注册，不是漏注册。

## 执行管道

循环本体**永不直接调用工具函数**，一切调用经 `ToolPipeline`。没有第二条路径。

管道分三段：

| 段 | 时机 | 能做什么 |
|---|---|---|
| `pre_tool` | 执行前 | 决策（放行 / 拒绝）+ **原地改写参数** |
| 执行 | — | 调用 `plugin.execute(arguments)` |
| `post_tool` | 执行后 | **原地改写结果** + 观察 |

判定结果是 `GateDecision`：放行 / 拒绝，附原因。执行期需要外部输入由工具侧抛错（异常上的 `await_user`）表达，落到 `ToolResult.await_user` / `deferred`，回合据此挂起。

## 写盘四步协议

提交时的检查住在 `pre_tool` 段：

```
预览  →  确认  →  凭 confirm_id 提交  →  重读
```

1. **预览**：凡工具声明 `needs_preview=True`（内置写类与插件写类同一规则）都先返回预览。成功后由管道把写参数快照登记入库并注入 `confirm_id`，**不落盘**。若结果带 `needs_commit=false`（如 `already_applied` / `already_absent` / `skipped`），门控**不登记**快照，也就不必再走确认与提交。`copy`/`move`/`rename` 源不存在为 `ok=false` / `source_missing`；目标冲突且 `on_exists=error` 为 `ok=false` / `dest_exists_conflict`——二者均带结构化 `data`，同样不登记、不视为已完成。管道与系统提示词的写类名单都只认注册表上的该元数据，无静态 `preview_tools` 旁路。带 `confirm_id` 时，`review_conclusion(cancel_preview=true)` 丢弃未提交的快照。同一写目标路径只保留最新一条未提交快照；会话内未提交条数上限为 `MAX_PENDING_PREVIEWS`（100），满额时按登记顺序挤掉最旧的。写目标路径参数键序只认工具的 `write_path_keys`（经注册表查找，不猜默认 `path`）；落盘后是否要求先 `read_file` 认 `needs_reread`。
2. **确认**：`QualityGate.confirm(confirm_id)` 把快照标为已审；`review_conclusion` 在模型工作流中执行这次解锁。
3. **提交**：`commit_write` 只凭 `confirm_id`。写参数由门控**从快照恢复**，模型不重传。
4. **重读**：同一文件刚落盘后又要改时，须先 `read_file` 复核当前内容与行号；
   复核不使已解锁的 `confirm_id` 失效，确认无误后用原 ID 继续提交。

预览与提交是**两个独立的工具入口**，不共用函数。

### 回灌模型的结果信封

派生进模型上下文的 tool 消息（`SessionLog.derive_messages`）成功/失败**同形**：

- 成功：`{"ok": true, "data": <工具返回>}`
- 失败：`{"ok": false, "error": "<类型与信息>"}`（可选附带 `data`）

管道内部仍是 `ToolResult(ok/data/error)`；事件流仍是 `tool_done` / `tool_failed`。信封作用在「给模型看的那一层」；经典界面 `tool_end.preview` 用同一顶层 `ok`/`error`/`data` 形状。

### review 与解锁

`review_conclusion` 是模型工作流中的解锁入口：它提交基于本次改动审阅的结论与验证证据，并解锁预览。结论至少 30 字，`file_name` 必填；带 `confirm_id` 取消预览时结论可省略。带 `confirm_id` 且 `cancel_preview=true` 时改为丢弃该预览。未确认的预览不能提交。

### 门控守的其余规则

| 规则 | 内容 |
|---|---|
| 路径解析 | 写目标由快照经工具的 `write_path_keys` 解析；解析不到即拒绝提交 |
| 同路径重读 | 内容类工具落盘后，同一路径再改前须先 `read_file` |
| 跨文件 review | 一次真写后，提交其他文件前须先 review，除非该预览在最近一次真写前已解锁 |
| 红灯限面 | 写后诊断红灯未解除时，只允许改 `fixable_paths` 内的路径（列表为空则退回 `pending_review`） |
| 大删除检测 | 删除 ≥30 行，且无新增或新增不足删除量的 35% 时亮红灯 |
| 模式门控 | Plan 模式禁止写盘；Execute 模式提交前须有非空执行清单 |

## 内置工具

`catalog/tools.json` 是仓库中的工具清单，由 `scripts/gen_catalog.py` 从装配后的注册表生成；`scripts/check_catalog.py` 在它与装配集不一致时报错。

**界面展示信息归工具自己**：`ToolPlugin` 上的 `label`（界面短名）与 `icon`（一个字符）
由工具声明，经 `registry.display_list()` 与壳层的 `/api/tool-labels` 送到页面 ——
加一个插件工具不必改界面；缺声明时界面退回显示工具名与中性图标。

### 文件读写

| 工具 | 做什么 |
|---|---|
| `read_file` | 读取文本文件，支持行区间与截断 |
| `write_file` | 预览写入（不落盘），返回 `confirm_id`；内容已一致则 `status=already_applied`（不必 commit） |
| `replace_in_file` | 预览文本替换：字面替换（单条或 `edits` 批量）或按 `line_start`/`line_end` 的行区间替换 |
| `apply_patch` | 预览应用 unified diff；只作用于根目录下已有文件，不支持新增 / 删除文件 |
| `read_write` | 预览管道写：从源文件取片段写入目标 |
| `delete_file` | 预览删除；路径已不存在则 `already_absent`；提交时移入回收目录 |
| `file_ops` | 预览 copy / move / rename / delete；`on_exists` = error / overwrite / skip；源缺失 `source_missing`、目标冲突 `dest_exists_conflict`、已目标态 / 跳过有明确 `status` |
| `file_undo` | 版本回滚：列历史 / 比对 / 回滚；回滚先预览，凭 `confirm_id` 提交 |
| `commit_write` | 凭 `confirm_id` 提交写预览 |
| `review_conclusion` | 提交 review 结论并解锁预览 |
| `present` | 展示文件卡片；校验路径并返回元信息，不读取正文 |

### 文件卡片

`present` 接收文件路径列表或 `{path, title}` 对象，返回名称、大小、类型与 MIME，不读取正文。壳层把结果渲染成对话区文件卡片；点击卡片打开右栏文件查看器。卡片只由工具成功结果驱动，不从模型正文猜路径。

Markdown 的本地文本文件路径链接同样进入右栏；本地媒体路径走媒体预览。正文里的行内代码路径（如 `` `E:\test.txt` ``）也按本地文件引用处理。

### 定位与检索

| 工具 | 做什么 |
|---|---|
| `glob_files` | 按 glob 模式列出路径；默认剪 `.git/`、`__pycache__/`，回执在 `skipped_derived_dirs` 报跳过的目录数 |
| `grep_files` | 目录快速搜索：`path` 必须是目录，返回路径、行号和命中；不支持上下文、gitignore 过滤与编码嗅探 |
| `file_search` | 通用内容搜索：文件或目录，支持字面/正则、上下文、gitignore 过滤与编码嗅探 |
| `find_in_file` | 单文件单点定位：按 0-based 序号取一处命中，返回 region 与行列 |
| `regex_locate` | 正则定位：文件或目录，返回至多 `limit` 条命中的 region、行号和内容 |
| `text_diff` | 对左右两侧文本生成 unified diff（只读） |

### 命令执行

| 工具 | 做什么 |
|---|---|
| `run_command` | 前台同步执行命令：等待结束并返回 stdout/stderr/exit_code；短命令、交互、安装构建使用 |
| `background_task` | 后台异步执行命令：立即返回 task_id，用 create/list/output/cancel 管理；argv 不经 shell |
| `python_inline` | 前台同步执行 Python：Agent 进程内执行，不经 shell，不创建子进程，不可硬中断；无 timeout 参数，超时需求改用 `background_task` |
| `env_probe` | 探测本机可用命令行环境并给出建议 |

后台任务的子进程只继承 PATH、系统目录、TEMP、HOME、Windows 用户路径（LOCALAPPDATA、APPDATA、USERPROFILE 等）和 locale；不继承 API Key、Token 等凭据。该白名单只降低环境泄漏与路径缺失，不提供文件系统、网络或权限隔离，不能当作安全沙箱。

`run_command` 先过安全防线：黑名单、内容级拦截、`safe_mode`、进程生命周期管理、输出净化；它继承完整父进程环境。
`background_task` 使用 argv 直接启动进程，不套用 `safe_mode`，但仍受允许 cwd、超时与进程终止管理；它只继承上述最小环境白名单，不继承 API Key、Token 等凭据。
`run_command`、`python_inline` 与 `background_task` 的 create 动作在 Plan 模式下被拒绝。

### 网络

| 工具 | 做什么 |
|---|---|
| `web_fetch` | 抓取网页并提取纯文本；支持超时、长度限制、验收与落盘 |
| `web_fetch_render` | 用无头浏览器抓取 JS 渲染后的页面（可选依赖） |
| `ip_geolocate` | IP 地理查询（免费 API，无 Key） |
| `open_meteo_weather` | 天气预报（免费 API，无 Key），支持地名 / 经纬度 / IP 定位，中文摘要输出 |

### 数据与媒体

| 工具 | 做什么 |
|---|---|
| `data_table` | 表格文件（csv/tsv/xlsx）预览、筛选、排序、统计与导出 |
| `archive` | 压缩包 list / extract / create |
| `read_image` | 读取本地图片或历史 `attachment_id`，把图片交给模型；同一回合拒绝重复读取同一附件 |
| `image_ocr` | 图片 OCR，支持区域裁剪；需可选 OCR 引擎 |
| `git_workspace` | Git 工作区只读查询：worktree / log / blame / show；不执行写入型命令 |

### 会话与任务

| 工具 | 做什么 |
|---|---|
| `run_type` | 查询或切换会话运行模式 |
| `todo_list` | 会话待办清单 |
| `user_confirm` | 首段挂起等待宿主人工作答；`confirm` / `confirm_id` 为宿主回填字段，不暴露给模型 |
| `goal` | 管理本会话的目标文案 |
| `session_send` | 向目标会话发消息并触发执行 |
| `session_multisend` | 向多个目标发同一条消息 |
| `session_broadcast` | 按 tag 向群组广播 |
| `session_create` | 创建自由 Agent 会话 |
| `session_list` | 列出协作网络中的自由 Agent 会话 |

### 诊断

| 工具 | 做什么 |
|---|---|
| `unified_diagnose` | 对目录下 Python 文件做 AST 语法诊断，PATH 中有 ruff 时一并调用 |
| `echo` | 回显输入文本 |

## 插件工具

插件可以通过 `ctx.register_tool(tool)` 向注册表贡献工具，执行仍走同一条管道。
工具声明 `needs_preview=True` 时同样受写盘四步协议约束。

`plugins/visual_operator` 贡献 `desktop_eye` / `desktop_mouse` / `desktop_keyboard` / `desktop_wait`：
截屏结果作为图片附件回灌模型，鼠标与键盘动作按会话做 Plan 门控；坐标契约与平台后端见 [visual-operator.md](visual-operator.md)。

`plugins/ai_speak` 贡献 `ai_speak`：模型把当前步骤用人类口语说出来，后端合成语音经插件事件送到前端播放条；文本规范与配置见 [ai-speak.md](ai-speak.md)。

`plugins/skills` 贡献 `skills`（list / read）；见 [skills.md](skills.md)。

插件包形态、清单、扩展点与生命周期见 [plugins.md](plugins.md)；运行时实例的登记（`ctx.set_runtime` / `plugin_host.runtime`）也在那里说明。

## 延伸阅读

- [architecture.zh.md](../architecture.zh.md)：`ToolPort` 与模块链
- [plugins.md](plugins.md)：插件系统与工具扩展点
- [visual-operator.md](visual-operator.md)：插件工具的图片附件与输入门控示例
- [guide/config.md](../guide/config.md)：配置项
- [session.md](session.md)：跨会话协作工具背后的网格
