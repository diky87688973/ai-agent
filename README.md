# AI Agent

本地运行的智能助手 <kbd>v0.1</kbd>

## 特点

- **三步写盘防错** —— 预览改动 → 提交审阅 → 确认落盘，随时可退回任意版本。
- **模块化内核** —— 输入 → 待发送队列插入 → 压缩 → 模型 → 工具，各段可替换。
- **插件式扩展** —— 替换界面、改上下文、扩展门控与 HTTP 端点。
- **多会话与协同** —— 多任务互不干扰，多 Agent 协同工作。
- **目标自动续跑** —— 设定目标，长任务自动跟进至完结。
- **上下文自动管理** —— 分段预算、超预算自动摘要，占用可查。
- **会话即事实** —— 事件事实落盘，断线重连从断点续传。
- **无头可跑** —— 内核不绑界面，可只跑 API 或换自己的前端。

## 快速开始

### Windows

双击 `start.bat`

### Linux / macOS

```bash
./start.sh
```

脚本自动查找 Python 3.10+，用当前 Python 的 `-m pip` 安装缺失依赖；不需要先在命令行配 key，也不生成配置样例。

启动后访问 <http://127.0.0.1:8765/>。未配置模型时主页面保留，模型下拉为空；从「设置 → 插件 → 多模型」添加网关后立即生效，不需要重启。

### 手动启动

```bash
python3 -m pip install -e ".[tts]" -c constraints.txt
python3 -m agent.entry.web --host 127.0.0.1 --port 8765 --open
```

## 配置

配置文件为仓库根目录的 `config.ini`，随仓库入库，只保留非敏感的宿主配置。模型不在此文件配置，全部由 `plugins/multi_model/plugin-config.ini` 和多模型设置页维护；没有模型时服务仍能启动，主页面模型下拉为空。

装载哪些插件由仓库根目录的 `plugins.ini` 决定（节在就进入候选）。开关写在 `plugins.ini` 的插件节；名字、描述、图标、版本由 `plugin-meta.json` 声明。插件自己的键在 `[config]`，见 [插件](docs/subsystems/plugins.md)。

页面右上角「设置」改的是同一批文件。密钥框留空不覆盖，接口也不回明文。

```ini
[agent]
reasoning_effort = max       # 全局推理档位：max（深度推理）/ high（标准推理）
backup_retention_days = 7    # 版本化备份保留天数；0 = 永久保留

[context]
summary_token_fallback   = 64000
summary_output_max_chars = 5000
full_user_rounds         = 5
```

`[context]` 的三个主要默认值：

| 键 | 默认 | 含义 |
|---|---|---|
| `summary_token_fallback` | `64000` | 模型没有声明上下文窗口时的回退压缩阈值；仅配置文件 |
| `summary_output_max_chars` | `5000` | 摘要篇幅上限（字） |
| `full_user_rounds` | `5` | 压缩时保留最近对话轮数，始终按原文发送 |

模型有 `context_window` 时，压缩阈值为该窗口 × 模型自己的 `compression_percent`；
窗口缺失才使用 `summary_token_fallback`。模型条目见 [多模型](docs/subsystems/multi-model.md)。

末尾 `full_user_rounds` 个用户轮保持原文发送；更早的轮次压缩成摘要。

全部配置项、启动参数与环境变量见 [配置](docs/guide/config.md)。

## 文档

| 文档 | 内容 |
|---|---|
| [架构](docs/architecture.md) | 五层结构、模块链、端口、事件协议、状态生命周期 |
| [工程标准](docs/engineering-standards.md) | 模块结构、单一职责、资产归属、扩展路径与门禁 |
| [术语](docs/glossary.md) | 项目自定义词的定义 |
| [内核](docs/subsystems/core.md) | 模块契约、链执行器、宿主循环 |
| [上下文管理](docs/subsystems/context.md) | 三拼接装、分段统计、压缩与摘要 |
| [模型调用](docs/subsystems/llm.md) | 请求体、流式解析、工具调用归并、错误映射 |
| [工具](docs/subsystems/tools.md) | 注册、执行管道、写盘四步协议、42 个内置工具 |
| [插件](docs/subsystems/plugins.md) | 插件包形态、可贡献的能力、界面资产、生命周期与边界 |
| [知识库](docs/subsystems/knowledge.md) | `knowledge` 的文件收录、勾选状态、注入与端点 |
| [多模型](docs/subsystems/multi-model.md) | `multi_model` 的目录条目、设置页表单与模型下拉 |
| [Skills](docs/subsystems/skills.md) | `skills` 插件的三层披露、内置/外置来源与 `skills` 工具 |
| [Rules](docs/subsystems/rules.md) | `rules` 插件：`rules/` 下的 `.md` 全量注入与热开关 |
| [Visual Operator](docs/subsystems/visual-operator.md) | `visual_operator` 的截屏、坐标网格与鼠标键盘工具 |
| [AI说话](docs/subsystems/ai-speak.md) | `ai_speak` 的文本规范、语音合成、插件事件与播放器 |
| [会话与协作](docs/subsystems/session.md) | 事实日志、跨进程锁、运行态登记、协作网格 |
| [壳层](docs/subsystems/shell.md) | HTTP 路由、SSE、界面打包、适配层 |
| [会话消息队列方案](docs/plan/conversation-queue.md) | 忙时入队、回合结束投递、安全插入、修改恢复与 Agent 来源 |
| [标准对齐优化方案](docs/plan/standards-alignment.md) | 依赖环、门禁可信度、覆盖率口径、预算与登记表 |
| [结构整改方案](docs/plan/structural-remediation.md) | Provider、上下文、壳层与门禁的职责拆分、依赖规则与实施顺序 |
| [会话历史分页方案](docs/plan/history-paging.md) | 轮次分页、游标、前插与超长报文延迟渲染 |
| [多模型配置方案](docs/plan/multi-model.md) | 模型目录、Provider 路由、Messages 协议适配、模型插件 |
| [AI说话方案](docs/plan/ai-speak.md) | `ai_speak` 的文本、切段、SSE 与播放器设计 |
| [配置](docs/guide/config.md) | 配置项全表、启动参数、环境变量 |
| [上下文导出](docs/guide/context-dump.md) | 开发者用会话上下文导出 CLI |

## 开发

依赖安装带锁文件，与 CI 同源：`pip install -e . -c constraints.txt`。

`scripts/ci.py` 的流水线 29 步（清单唯一事实源是 `scripts/ci_steps.py`，由
`check_ci_workflow` 与 GitHub Actions 对齐）：17 项门禁（依赖方向、架构约束、
CI 工作流一致、配置一致性、生成文档一致、ruff、Python 下限、UI JS 自检、
静默异常、README 一致性、确认文案、注释文案、注册表一致性、复杂度登记、
适用性登记、并发争用等，完整清单用 `--list` 查看）→ 单测 → 10 个验收脚本 → 分包覆盖率。

```bash
python scripts/ci.py           # 全部检查
python scripts/ci.py --fast    # 跳过验收
python scripts/ci.py --list    # 列出检查项
python scripts/scan_js_events.py  # 本地 JS 事件绑定审计
```

导出某个会话的真实请求上下文（开发者只读工具）：

```bash
python scripts/dump_context.py --cid <会话ID> --format json --out context.json
```

单元测试（1772 个用例）：

```bash
python -m unittest discover -s tests -p "test_*.py" -t tests
```

检视某个会话的上下文分段与压缩判定（只读）：

```bash
python scripts/inspect_compact.py                 # 列出有日志的会话
python scripts/inspect_compact.py <会话 id>        # 检视其中一个
python scripts/inspect_compact.py <会话 id> --digest
```

## 许可

[Apache License 2.0](LICENSE)。第三方组件署名见 [NOTICE](NOTICE)。
