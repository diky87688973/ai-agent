# AI Agent

本地运行的智能助手 <kbd>v0.1</kbd>

## 特点

- **三步写盘防错** —— 预览改动 → 提交审阅 → 确认落盘，随时可退回任意版本。
- **模块化内核** —— 输入 → 收件箱 → 压缩 → 模型 → 工具，各段可替换。
- **插件式扩展** —— 换UI、改上下文、门控、HTTP 端点与界面。
- **多会话与协同** —— 多任务处互不干扰，多Agent协同工作。
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
pip install -e .
python -m agent.shell.web --host 127.0.0.1 --port 8765
```

## 配置

配置文件为仓库根目录的 `config.ini`，从 `config.ini.example` 复制后填写。**必填项只有 `api_key`**。

装载哪些插件由仓库根目录的 `plugins.ini` 决定（`.ini` 里列出即装载），见 [插件](docs/subsystems/plugins.md)。

```ini
[model_reasoning]
api_base_url = https://api.deepseek.com
api_key      = 你的 API Key
model        = deepseek-flash

[agent]
reasoning_effort = max       # 全局推理档位：max（深度推理）/ high（标准推理）
backup_retention_days = 7    # 版本化备份保留天数；0 = 永久保留
user_rules_file =            # 可选：自定义规则文件（.md / .txt），留空不加规则段

[context]
summary_token_threshold  = 700000
summary_output_max_chars = 5000
full_user_rounds         = 10
```

`[context]` 的四个默认值：

| 键 | 默认 | 含义 |
|---|---|---|
| `summary_token_threshold` | `700000` | 估算 token 超过该值触发压缩 |
| `summary_output_max_chars` | `5000` | 摘要篇幅上限（字） |
| `full_user_rounds` | `10` | 近期记忆保留的用户轮数，始终按原文发送 |

末尾 `full_user_rounds` 个用户轮被遮盖、按原文保留，它们前面的轮次压缩成摘要。

全部配置项、启动参数与环境变量见 [配置](docs/guide/config.md)。

## 文档

| 文档 | 内容 |
|---|---|
| [架构](docs/architecture.md) | 四层结构、模块链、端口、事件协议、状态生命周期 |
| [术语](docs/glossary.md) | 项目自定义词的定义 |
| [内核](docs/subsystems/core.md) | 模块契约、链执行器、宿主循环 |
| [上下文管理](docs/subsystems/context.md) | 三拼接装、分段统计、压缩与摘要 |
| [模型调用](docs/subsystems/llm.md) | 请求体、流式解析、工具调用归并、错误映射 |
| [工具](docs/subsystems/tools.md) | 注册、执行管道、写盘四步协议、41 个内置工具 |
| [插件](docs/subsystems/plugins.md) | 插件包形态、可贡献的能力、界面资产、生命周期与边界 |
| [技能](docs/subsystems/skills.md) | `skills` 插件的三层披露与 `skill_manage` |
| [会话与协作](docs/subsystems/session.md) | 事实日志、跨进程锁、运行态登记、协作网格 |
| [壳层](docs/subsystems/shell.md) | HTTP 路由、SSE、界面打包、适配层 |
| [配置](docs/guide/config.md) | 配置项全表、启动参数、环境变量 |

## 开发

`scripts/ci.py` 的流水线 20 步：九项门禁（依赖方向、ruff、Python 下限、UI JS 自检、
静默异常、README 一致性、确认文案、注释文案、注册表一致性）→ 单测 → 10 个验收脚本。

```bash
python scripts/ci.py           # 全部检查
python scripts/ci.py --fast    # 跳过验收
python scripts/ci.py --list    # 列出检查项
```

单元测试（1117 个用例）：

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
