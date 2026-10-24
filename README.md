# AI Agent <kbd>v0.1</kbd>

<p align="center">
  <strong>灵活扩展、按需定制，组装属于你自己的本地 Agent</strong>
  <br>
  工具、插件、提示词、门控与入口按需组合，满足不同场景的诉求。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-v0.1-blue" alt="version">
  <img src="https://img.shields.io/badge/Python-3.10%2B-brightgreen" alt="Python">
  <img src="https://img.shields.io/badge/License-Apache%202.0-green" alt="License">
</p>

## 下载

打开 [Releases](https://github.com/diky87688973/ai-agent/releases) 页面，选择版本，在 **Assets** 中下载。

### Windows

- `ai-agent-<version>-full-pack-windows.zip`  
  首次使用，下载后解压，运行 `agent-gui.exe`。

- `ai-agent-<version>-update-pack-windows.zip`  
  仅用于已安装版本的自动更新，不能单独运行。

### macOS

- `ai-agent-<version>-full-pack-macos.zip`
- `ai-agent-<version>-update-pack-macos.zip`

macOS 安装包暂未构建，当前 Release 只提供 Windows 包。

## 特点

- **本地运行** —— 会话、文件与工具在本机执行；模型端点与推理档自行配置。
- **模块化内核** —— 输入 → 待发送队列 → 压缩 → 模型 → 工具，各段可替换。
- **写盘四步** —— 预览、确认、提交、重读，支持备份与回滚。
- **插件式扩展** —— 插件增加工具、执行器、上下文、提示词、门控、模型目录、HTTP 端点与界面资产，不修改内核。
- **内置插件** —— Skills、Rules、知识库、多模型、Visual Operator、AI 说话，可独立装卸。
- **多会话与协作** —— 多任务互不干扰，支持 Agent 消息、队列与运行态管理。
- **上下文管理** —— 分段预算、超预算自动摘要、占用可查，并可导出真实请求上下文。
- **会话即事实** —— 事件事实落盘，断线重连从断点续传。
- **目标自动续跑** —— 设定目标后自动推进到结束。
- **一套内核，三种入口** —— Web 控制台、交互终端与无头执行共用同一内核和门控规则，切换入口不改变行为。
  - `agent-web`：浏览器控制台，提供多会话、插件面板与实时事件。
  - `agent-cli`：终端交互，适合本机排查、连续对话与写盘确认。
  - `agent-headless`：无头执行，适用于工单流转、客服支持、故障排查等服务化场景，也可接入 CI、脚本或嵌入业务流程。

## 快速开始

### 桌面方式

保持项目目录完整，双击根目录 `agent-gui.exe`。

需要本机 Python 3.10+ 和系统 WebView2；首次运行会联网准备 pywebview。桌面壳使用固定端口 `3156`。

<img src="docs/assets/desktop.png" alt="桌面窗口" width="960">

### 命令行方式

安装：

```bash
python3 -m pip install -e ".[gui,tts]" -c constraints.txt
```

#### Web 控制台

```bash
agent-web --host 127.0.0.1 --port 8765
```

打开 <http://127.0.0.1:8765/>。Windows 也可双击 `start.bat`，Linux/macOS 可运行 `./start.sh`。

#### 交互终端

```bash
agent-cli
agent-cli --session <会话ID>
```

#### 无头执行

```bash
agent-headless "问题"
agent-headless --session <会话ID> "问题"
```

输出事件流与会话 ID；适合工单、排障、CI 和脚本集成。

#### 桌面窗口

```bash
python3 -m agent.gui.launcher
```

端口 `3156`；与 `agent-web` 的 `8765` 相互独立。

## 文档

### 用户文档

| 文档 | 内容 |
|---|---|
| [配置](docs/guide/config.md) | 配置项、启动参数与环境变量 |
| [桌面入口](docs/guide/desktop.md) | `agent-gui.exe`、Python 桌面壳与运行前提 |

### 开发者文档

| 文档 | 内容 |
|---|---|
| [架构](docs/architecture.md) | 五层结构、模块链、端口、事件协议、状态生命周期 |
| [工程标准](docs/engineering-standards.md) | 模块结构、单一职责、资产归属、扩展路径与门禁 |
| [术语](docs/glossary.md) | 项目自定义词的定义 |
| [内核](docs/subsystems/core.md) | 模块契约、链执行器、宿主循环 |
| [上下文管理](docs/subsystems/context.md) | 三拼接装、分段统计、压缩与摘要 |
| [模型调用](docs/subsystems/llm.md) | 请求体、流式解析、工具调用归并、错误映射 |
| [工具](docs/subsystems/tools.md) | 注册、执行管道、写盘四步协议、43 个内置工具 |
| [插件](docs/subsystems/plugins.md) | 插件包形态、可贡献的能力、界面资产、生命周期与边界 |
| [知识库](docs/subsystems/knowledge.md) | `knowledge` 的文件收录、勾选状态、注入与端点 |
| [多模型](docs/subsystems/multi-model.md) | `multi_model` 的目录条目、设置页表单与模型下拉 |
| [Skills](docs/subsystems/skills.md) | `skills` 插件的三层披露、内置/外置来源与 `skills` 工具 |
| [Rules](docs/subsystems/rules.md) | `rules` 插件：`rules/` 下的 `.md` 全量注入与热开关 |
| [Visual Operator](docs/subsystems/visual-operator.md) | `visual_operator` 的截屏、坐标网格与鼠标键盘工具 |
| [AI说话](docs/subsystems/ai-speak.md) | `ai_speak` 的文本规范、语音合成、插件事件与播放器 |
| [会话与协作](docs/subsystems/session.md) | 事实日志、跨进程锁、运行态登记、协作网格 |
| [壳层](docs/subsystems/shell.md) | HTTP 路由、SSE、界面打包、适配层 |

### 设计文档（内部）

以下为设计记录与取舍，不是用户手册。

<details>
<summary>展开设计文档</summary>

| 文档 | 内容 |
|---|---|
| [后台任务](docs/plan/background-tasks.md) | per-cid 队列、并发上限、超时、取消、输出与聚合通知 |
| [软件更新](docs/plan/software-update.md) | 版本检查、哈希校验、版本化目录、原子切换与回滚 |
| [会话消息队列](docs/plan/conversation-queue.md) | 忙时入队、回合结束投递、安全插入与修改恢复 |
| [标准对齐](docs/plan/standards-alignment.md) | 依赖环、门禁可信度、覆盖率口径与预算 |
| [结构整改](docs/plan/structural-remediation.md) | Provider、上下文、壳层与门禁的职责拆分 |
| [历史分页](docs/plan/history-paging.md) | 轮次分页、游标、前插与超长报文延迟渲染 |
| [多模型](docs/plan/multi-model.md) | 模型目录、Provider 路由与协议适配 |
| [AI说话](docs/plan/ai-speak.md) | 文本切片、SSE 与播放器设计 |
| [Visual Operator 交互](docs/plan/visual-operator-interaction.md) | 截屏、UIA 与坐标控制的设计判断 |
| [Visual Operator](docs/plan/visual-operator.md) | 视觉操作子系统的设计记录 |
| [ADR：插件子进程隔离](docs/adr/plugin-subprocess-isolation.md) | 隔离方案的决策记录 |

</details>

## 开发帮助

### 环境

依赖安装带锁文件，与 CI 同源：

```bash
pip install -e . -c constraints.txt
```

### CI

`scripts/ci.py` 的流水线 29 步：17 项门禁 → 单测 → 10 个验收脚本 → 分包覆盖率。

17 项门禁覆盖依赖方向、架构约束、配置漂移、生成文档一致性、静态检查、UI/文案、复杂度、适用性与并发争用；完整清单用 `--list` 查看。

门禁清单的唯一事实源是 `scripts/ci_steps.py`，由 `check_ci_workflow` 与 GitHub Actions 对齐。

```bash
python scripts/ci.py           # 全部检查
python scripts/ci.py --fast    # 跳过验收
python scripts/ci.py --list    # 列出检查项
```

### 测试

`docs/unit-tests.md` 是生成的可读测试目录，事实源是 `tests/`。

单元测试（1833 个用例）：

```bash
python -m unittest discover -s tests -p "test_*.py" -t tests
```

### 调试工具

导出某个会话的真实请求上下文：

```bash
python scripts/dump_context.py --cid <会话ID> --format json --out context.json
```

检视会话的上下文分段与压缩判定：

```bash
python scripts/inspect_compact.py                 # 列出有日志的会话
python scripts/inspect_compact.py <会话 id>        # 检视其中一个
python scripts/inspect_compact.py <会话 id> --digest
```

审计本地 JS 事件绑定：

```bash
python scripts/scan_js_events.py
```

## 作者

- 作者：Fan
- 邮箱：diky87@qq.com

## 许可

[Apache License 2.0](LICENSE)。第三方组件署名见 [NOTICE](NOTICE)。
