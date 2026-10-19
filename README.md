# AI Agent

本地运行的智能助手 <kbd>v0.1</kbd>

## 特点

- **三步写盘防错** —— 预览改动 → 提交审阅 → 确认落盘，随时可退回任意版本。
- **模块化内核** —— 输入 → 收件箱 → 压缩 → 模型 → 工具，各段可替换。
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

脚本依次检查 Python、依赖、配置文件。首次运行会从模板生成 `config.ini` 并打开编辑器，填写 `api_key` 后重新运行。

启动后访问 <http://127.0.0.1:8765/>

### 手动启动

```bash
pip install -e . -c constraints.txt
python -m agent.entry.web --host 127.0.0.1 --port 8765
```

## 配置

配置文件为仓库根目录的 `config.ini`，模板是 `config.ini.example`。模板里 `api_base_url` 已填好，通常只需补 `api_key`；两项缺任一，服务启动即报错退出。

装载哪些插件由仓库根目录的 `plugins.ini` 决定（节在就进入候选）。开关、名字、描述、图标、版本写在各插件 `plugin-config.ini` 的 `[base]`，自己的键在 `[ext]`，见 [插件](docs/subsystems/plugins.md)。

页面右上角「设置」改的是同一批文件。密钥框留空不覆盖，接口也不回明文。

```ini
[model_reasoning]
api_base_url = https://api.deepseek.com
api_key      = sk-请替换
model        = deepseek-flash

[agent]
reasoning_effort = max       # 全局推理档位：max（深度推理）/ high（标准推理）
backup_retention_days = 7    # 版本化备份保留天数；0 = 永久保留
user_rules_file =            # 可选：自定义规则文件（.md / .txt），留空不加规则段

[context]
summary_token_threshold  = 700000
summary_output_max_chars = 5000
full_user_rounds         = 1
```

`[context]` 的三个主要默认值：

| 键 | 默认 | 含义 |
|---|---|---|
| `summary_token_threshold` | `700000` | 估算 token 超过该值触发压缩 |
| `summary_output_max_chars` | `5000` | 摘要篇幅上限（字） |
| `full_user_rounds` | `1` | 近期记忆保留的用户轮数，始终按原文发送 |

末尾 `full_user_rounds` 个用户轮保持原文发送；更早的轮次压缩成摘要。

全部配置项、启动参数与环境变量见 [配置](docs/guide/config.md)。

## 文档

| 文档 | 内容 |
|---|---|
| [架构](docs/architecture.md) | 五层结构、模块链、端口、事件协议、状态生命周期 |
| [术语](docs/glossary.md) | 项目自定义词的定义 |
| [内核](docs/subsystems/core.md) | 模块契约、链执行器、宿主循环 |
| [上下文管理](docs/subsystems/context.md) | 三拼接装、分段统计、压缩与摘要 |
| [模型调用](docs/subsystems/llm.md) | 请求体、流式解析、工具调用归并、错误映射 |
| [工具](docs/subsystems/tools.md) | 注册、执行管道、写盘四步协议、41 个内置工具 |
| [插件](docs/subsystems/plugins.md) | 插件包形态、可贡献的能力、界面资产、生命周期与边界 |
| [知识库](docs/subsystems/knowledge.md) | `knowledge` 的文件收录、勾选状态、注入与端点 |
| [多模型](docs/subsystems/multi-model.md) | `multi_model` 的目录条目、设置页表单与模型下拉 |
| [Skills](docs/subsystems/skills.md) | `skills` 插件的三层披露与 `skill_manage` |
| [Visual Operator](docs/subsystems/visual-operator.md) | `visual_operator` 的截屏、坐标网格与鼠标键盘工具 |
| [AI说话](docs/subsystems/ai-speak.md) | `ai_speak` 的文本规范、语音合成、插件事件与播放器 |
| [会话与协作](docs/subsystems/session.md) | 事实日志、跨进程锁、运行态登记、协作网格 |
| [壳层](docs/subsystems/shell.md) | HTTP 路由、SSE、界面打包、适配层 |
| [标准对齐优化方案](docs/plan/standards-alignment.md) | 依赖环、门禁可信度、覆盖率口径、预算与登记表 |
| [会话历史分页方案](docs/plan/history-paging.md) | 轮次分页、游标、前插与超长报文延迟渲染 |
| [多模型配置方案](docs/plan/multi-model.md) | 模型目录、Provider 路由、Anthropic 适配、模型插件 |
| [AI说话方案](docs/plan/ai-speak.md) | `ai_speak` 的文本、切段、SSE 与播放器设计 |
| [配置](docs/guide/config.md) | 配置项全表、启动参数、环境变量 |

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
```

单元测试（1595 个用例）：

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
