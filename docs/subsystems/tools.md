# 工具

工具是模型能对外界做的事。实现在 `agent/capabilities/`，执行管道与写盘门控在 `agent/core/tool_call.py` 与 `agent/mechanisms/quality_gate.py`。

## 注册

```python
class ToolPlugin:
    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {}   # 参数名 → JSON Schema 片段
    parallel_safe: bool = False

    def execute(self, arguments: Dict[str, Any]) -> Any: ...
```

注册进 `ToolRegistry`：

```python
registry.register(plugin)   # 返回 disposer（注销句柄）
registry.get(name)          # 未注册返回 None
registry.names()            # 已注册的工具名（排序后）
registry.schemas()          # 导出模型可见的工具声明
```

三条纪律：

- **注册表只存不跑**。执行调度与门控由管道这个唯一入口统一承载。
- `name` 唯一，重复注册被拒。
- `execute` 返回任意可序列化值；**异常由管道捕获**成失败结果结构化回灌，单步失败不终止回合。

注册与注销都返回句柄，这是插件热装卸的地基。

## 执行管道

循环本体**永不直接调用工具函数**，一切调用经 `ToolPipeline`。没有第二条路径。

管道分三段：

| 段 | 时机 | 能做什么 |
|---|---|---|
| `pre_tool` | 执行前 | 决策（放行 / 拒绝）+ **原地改写参数** |
| 执行 | — | 调用 `plugin.execute(arguments)` |
| `post_tool` | 执行后 | **原地改写结果** + 观察 |

判定结果是 `GateDecision`：放行 / 拒绝，附结构化原因。执行期需要外部输入由工具侧抛错（异常上的 `await_user`）表达，落到 `ToolResult.await_user` / `deferred`，回合据此挂起。

## 写盘四步协议

对写类工具的最强规则，住在 `pre_tool` 段：

```
预览  →  确认  →  凭 confirm_id 提交  →  重读
```

1. **预览**：`write_file` / `replace_in_file` / `apply_patch` / `read_write` / `delete_file` / `file_ops` / `file_undo` / `archive` / `skill_manage` 都先预览，把写参数快照登记入库，返回 `confirm_id`，**不落盘**。预览类工具可用 `review_conclusion(cancel_preview=true)` 丢弃未提交的快照。
2. **确认**：宿主侧 `QualityGate.confirm(confirm_id)`。
3. **提交**：`commit_write` 只凭 `confirm_id`。写参数由门控**从快照恢复**，模型不重传。
4. **重读**：提交后重读落盘结果并记入报告。

预览与提交是**两个独立的工具入口**，不共用函数。

### 写盘前必须先 review

`review_conclusion` 是写盘的前置：模型要给出基于实际审阅的结论与验证证据，才能解锁预览。未 review 就提交会被拒。

### 门控守的其余规则

| 规则 | 内容 |
|---|---|
| 路径解析 | 写路径必须落在可见根内，防越权 |
| 红灯限面 | 同一文件连续改写要重读 |
| 跨文件 review | 一次改动涉及多文件时的 review 语义 |
| 大删除检测 | 写中记账，检测异常大的删除量（删除 ≥30 行且新增不足删除量 35%） |
| 空口已修复 | 声称修好但无证据时拒绝 |
| 模式门控 | Plan 模式禁止写盘；Execute 模式须先有非空执行清单 |

## 内置工具（41 个）

工具清单的权威来源是 `catalog/tools.json`，它与装配集的一致性由 `scripts/check_catalog.py` 守着。

**界面展示信息归工具自己**：`ToolPlugin` 上的 `label`（中文短名）与 `icon`（一个字符）
由工具声明，经 `registry.display_list()` 与壳层的 `/api/tool-labels` 送到页面 ——
加一个插件工具不必改界面；缺声明时界面退回显示工具名与中性图标。

### 文件读写

| 工具 | 做什么 |
|---|---|
| `read_file` | 读取文本文件，支持行区间与截断 |
| `write_file` | 预览写入（不落盘），返回 `confirm_id` |
| `replace_in_file` | 预览文本替换：字面替换或按 region / 行列的区间替换 |
| `apply_patch` | 预览应用 unified diff |
| `read_write` | 预览管道写：从源文件取片段写入目标 |
| `delete_file` | 预览删除，文件移入回收目录（可恢复） |
| `file_ops` | 预览 copy / move / rename / delete |
| `file_undo` | 版本回滚：列历史 / 比对 / 回滚 |
| `commit_write` | 凭 `confirm_id` 提交写预览 |
| `review_conclusion` | 提交 review 结论并解锁预览 |

### 定位与检索

| 工具 | 做什么 |
|---|---|
| `glob_files` | 按 glob 模式列出路径 |
| `grep_files` | 目录内文本搜索（字面，`|` 为 OR；或正则） |
| `file_search` | 大范围内容搜索，支持 gitignore 过滤、编码嗅探、上下文行 |
| `find_in_file` | 单文件内定位第 N 处命中，返回 region 与行列 |
| `regex_locate` | 单文件或目录下正则检索，返回 region 与行列 |
| `text_diff` | 对左右两侧文本生成 unified diff（只读） |

### 命令执行

| 工具 | 做什么 |
|---|---|
| `run_command` | 执行单条 shell 命令，收集 stdout / stderr / exit_code |
| `python_inline` | `exec` 执行 Python 源码（不经 shell） |
| `env_probe` | 探测本机可用命令行环境并给出建议 |

命令执行先过安全防线：黑名单、内容级拦截、`safe_mode`、进程生命周期管理、输出净化。实现在 `agent/mechanisms/command_safety.py`。

### 网络

| 工具 | 做什么 |
|---|---|
| `web_fetch` | 抓取网页并提取纯文本 |
| `web_fetch_render` | Playwright 无头浏览器抓取 JS 渲染后的页面 |
| `ip_geolocate` | IP 地理查询（免费 API，无 Key） |
| `open_meteo_weather` | 天气预报（免费 API，无 Key），中文摘要输出 |
| `github_api` | GitHub 远程操作 + 设备流登录 |

### 数据与媒体

| 工具 | 做什么 |
|---|---|
| `data_table` | 表格文件预览、筛选、排序、统计与导出 |
| `archive` | 压缩包 list / extract / create |
| `image_ocr` | 图片 OCR，支持区域裁剪 |
| `git_workspace` | Git 工作区只读查询 |

### 会话与任务

| 工具 | 做什么 |
|---|---|
| `run_type` | 查询或切换会话运行模式 |
| `todo_list` | 会话待办清单 |
| `user_confirm` | 向用户发起分岔确认 |
| `task_sleep` | 暂停自主执行，N 秒后携提醒重新激活 |
| `goal` | 管理本会话的目标文案 |
| `session_send` | 向目标会话发消息并触发执行 |
| `session_multisend` | 向多个目标发同一条消息 |
| `session_broadcast` | 按 tag 向群组广播 |
| `session_create` | 创建自由会话 |
| `session_list` | 列出协作网络中的会话 |
| `skill_manage` | 技能管理：list / read / copy |

### 诊断

| 工具 | 做什么 |
|---|---|
| `unified_diagnose` | 对目录下 Python 文件做 AST 语法诊断，PATH 中有 ruff 时一并调用 |
| `echo` | 回显输入文本（样板） |

## 插件

`plugins/` 下的外部能力默认不加载，在工程根的 `plugins.ini` 里按名字列出。

```ini
[plugin:knowledge]
version = 1.0

[plugin:tts]
```

加载器在 `agent/capabilities/plugins.py`：按清单装载 `plugin.py`，调用其注册入口 `register(ctx)`，把工具挂进注册表。插件经 `agent.config.load_ini()` 读自己目录下的 `config.ini`。`PluginHost` 记录加载报告，单个插件装载失败只记报告，不阻断启动。

| 插件 | 能力 |
|---|---|
| `knowledge` | 知识库：配置判定、文件访问、表格解析、勾选状态、`add_context_source` 注入，加上右栏面板、输入区按钮与 `/api/plugin/knowledge/*` 端点 —— 全在插件里（只收文本类文件与表格，非文本不列也不可勾；`extra_suffixes` 可追加）|
| `tts` | 语音合成：只订阅事件（`assistant_delta` / `turn_ended` / `error`），不注册工具也不贡献界面 |

插件的完整说明见 [plugins.md](plugins.md)。

插件的运行时对象（需要被壳层操作的那些）用 `ctx.set_runtime(obj)` 登记到宿主，壳层经 `plugin_host.runtime(name)` 取**同一个实例**。插件是被 `importlib` 以动态模块名加载的，壳层 `import` 不到同一个模块对象，不登记就会各持一份状态。

## 延伸阅读

- [architecture.md](../architecture.md)：`ToolPort` 与模块链
- [guide/config.md](../guide/config.md)：插件与知识库配置
- [session.md](session.md)：跨会话协作工具背后的网格
