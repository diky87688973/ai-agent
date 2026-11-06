[English](README.md) | **中文**

# AI Agent

<p align="center">
  <strong>可扩展、可组合的 AI Agent 底座</strong>
  <br>
  支持本地运行与服务化接入，过程可查，写盘可控。<br>
  从模型、工具、插件到业务接入，按需扩展与组合。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-v0.2.0-blue" alt="version">
  <img src="https://img.shields.io/badge/Python-3.10%2B-brightgreen" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
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

- **本地优先，模型端点自选** —— 会话、文件、工具与写盘门控在本机执行；模型端点和推理档位按需配置。
- **四种入口，一套内核** —— 桌面 GUI、Web 界面、交互终端与无头执行共用会话、工具和门控规则，切换入口不改变行为。
- **可服务化接入** —— 内核不绑定 UI，Web 入口提供本地 HTTP/SSE 与健康检查，无头入口面向脚本、CI、工单和外部系统调用，插件可追加自己的 HTTP 端点。
- **访问鉴权** —— 浏览器登录，GUI 一次性免登录；scrypt 密码、HttpOnly 会话、CSRF、scope Token、登录限流、公网 TLS。
- **插件化扩展** —— 工具、执行器、上下文、提示词、门控、模型目录、HTTP 端点与界面资产均可由插件加入，不修改内核；内置 Skills、Rules、知识库、多模型、视觉操作与 AI 说话。
- **视觉操作** —— 持续视觉能力，授权后流畅操作系统，用户随时接管，过程可追溯。(目前仅支持 Windows)
- **多智能体协作** —— 子智能体按批次创建，拥有独立会话与角色工具视图；支持父子双向通信、消息队列、工作汇报。
- **长任务可管理** —— 后台任务按会话隔离，支持并发上限、超时、取消与输出读取；目标、Todo 和消息队列支持多回合推进。
- **定时唤醒** —— 可注册相对或绝对时间的唤醒任务；宿主在回合结束后投递，目标空闲即启动，忙碌则排队。
- **四步写盘** —— 预览 → 审查 → 提交 → 重读，先确认再落盘；改前自动备份，写入失败或结果不对可回滚，删除进入回收目录。
- **上下文管理** —— 分段预算、超预算摘要、上下文用量与请求快照；事实流落盘，SSE 断线可按事件坐标续传。
- **安全更新** —— 更新包哈希校验、暂存、健康检查与失败回滚；普通文件覆盖，`*.ini` 合并用户配置。

## 插件骨架

插件是安装与启停单元；插件树是贡献视图，插口树（SlotTree）是装配结果。整个 `app` 由启动装配树递归装配，不是在固定 `app` 上留扩展口。内核、宿主、工具、壳层都是启动插口；插件在装配前覆盖或新增节点。`App` 只是门面，`boot_app()` 读树、合并覆盖、递归装配。

```text
启动流程（全 App）
App 启动
  │
  ├─ 读取 agent/boot/slot_tree.json
  │     └─ 基础装配树：kernel / host / tools / shell / facade
  │
  ├─ 扫描 plugins/
  │     ├─ plugins.ini           启停 + 顺序
  │     └─ plugin-assembly.json  额外插件的装配声明
  │
  ├─ 合并
  │     ├─ replace / 新增 app/... 子树
  │     └─ 鉴权：宿主持有，不是 SlotTree 可替换子树
  │
  └─ SlotTree 递归装配
        │
        ▼
     App 门面完成（不含组件清单）

App 运行期
  plugin.py ── register(ctx) ──▶ 后端插口 / UI 插口 / 设置 / 路由
                                └─ 动态节点挂回同一棵 SlotTree
```

插件目录：

```text
plugins/<插件名>/
  plugin.py             register(ctx)
  plugin-ui.json        UI 插口
  plugin-assembly.json  启动插口覆盖；存在即自动装载
  plugin-meta.json      身份 / auto_load
  plugin-config.ini     插件配置
  ui/                   面板资产
```

启动插口可替换，也可新增 `app/...` 子树；鉴权由宿主持有，不是可替换的 SlotTree 子树。无需改 `slot_tree.json` 或 `plugins.ini`；`enabled = 0` 仍可禁用。

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

#### Web 界面

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
| [配置](docs/guide/config.zh.md) | 配置项、启动参数与环境变量 |
| [桌面入口](docs/guide/desktop.zh.md) | `agent-gui.exe`、Python 桌面壳与运行前提 |

### 开发者文档

| 文档 | 内容 |
|---|---|
| [架构](docs/architecture.zh.md) | 插件树、五层底座、模块链、端口、事件协议、状态生命周期 |
| [工程标准](docs/engineering-standards.zh.md) | 模块结构、单一职责、资产归属、扩展路径与门禁 |
| [术语](docs/glossary.zh.md) | 项目自定义词的定义 |
| [内核](docs/subsystems/core.zh.md) | 模块契约、链执行器、宿主循环 |
| [上下文管理](docs/subsystems/context.zh.md) | 三拼接装、分段统计、压缩与摘要 |
| [模型调用](docs/subsystems/llm.zh.md) | 请求体、流式解析、工具调用归并、错误映射 |
| [工具](docs/subsystems/tools.zh.md) | 注册、执行管道、写盘四步协议、内置工具 |
| [插件](docs/subsystems/plugins.zh.md) | 插件包形态、可贡献的能力、界面资产、生命周期与边界 |
| [知识库](docs/subsystems/knowledge.zh.md) | `knowledge` 的文件收录、勾选状态、注入与端点 |
| [多模型](docs/subsystems/multi-model.zh.md) | `multi_model` 的目录条目、设置页表单与模型下拉 |
| [Skills](docs/subsystems/skills.zh.md) | `skills` 插件的三层披露、内置/外置来源与 `skills` 工具 |
| [Rules](docs/subsystems/rules.zh.md) | `rules` 插件：`rules/` 下的 `.md` 全量注入与热开关 |
| [AI角色扮演](docs/subsystems/ai-cosplay.zh.md) | `ai_cosplay` 的文本规范、语音合成、插件事件与播放器 |
| [会话与协作](docs/subsystems/session.zh.md) | 事实日志、跨进程锁、运行态登记、协作网格 |
| [子智能体](docs/subsystems/subagent.zh.md) | 父子会话、批次、工具可见性、消息与最终回复投递 |
| [壳层](docs/subsystems/shell.zh.md) | HTTP 路由、SSE、界面打包、适配层 |

### 设计文档（内部）

以下为设计记录与取舍，不是用户手册。

<details>
<summary>展开设计文档</summary>

| 文档 | 内容 |
|---|---|
| [后台任务](docs/plan/background-tasks.zh.md) | per-cid 队列、并发上限、超时、取消、输出与聚合通知 |
| [软件更新](docs/plan/software-update.zh.md) | 版本检查、哈希校验、逐文件切换、备份与回滚 |
| [会话消息队列](docs/plan/conversation-queue.zh.md) | 忙时入队、回合结束投递、安全插入与修改恢复 |
| [历史分页](docs/plan/history-paging.zh.md) | 轮次分页、游标、前插与超长报文延迟渲染 |
| [会话存储重构](docs/plan/session-storage-refactor.zh.md) | 增量追加、10K 字符窗口、轮区间、禁止全量读取、并发边界 |
| [多模型](docs/plan/multi-model.zh.md) | 模型目录、Provider 路由与协议适配 |
| [AI角色扮演](docs/plan/ai-cosplay.zh.md) | 文本切片、SSE 与播放器设计 |
| [视觉操作交互](docs/plan/visual-operator-interaction.zh.md) | 截屏、UIA 与坐标控制的设计判断 |
| [视觉操作](docs/plan/visual-operator.zh.md) | 视觉操作子系统的设计记录 |
| [CLI 两阶段确认](docs/plan/cli-confirm-backlog.zh.md) | CLI 两阶段确认缺口 |
| [ADR：插件子进程隔离](docs/adr/plugin-subprocess-isolation.zh.md) | 隔离方案的决策记录 |

| [视觉操作 2.0 子系统](docs/subsystems/visual-operator-2.0.zh.md) | 持续视觉帧、聚焦、授权与键鼠工具 |
</details>

<details>
<summary>补充文档</summary>

| 文档 | 内容 |
|---|---|
| [标准适用性申报](docs/applicability.zh.md) | N/A 申报与风险承担者 |
| [上下文导出](docs/guide/context-dump.zh.md) | 上下文请求视图与导出 |
| [上下文压缩工具](docs/plan/context-compression-tool.zh.md) | 压缩上下文工具 |
| [HTTP 鉴权](docs/plan/http-auth.zh.md) | 登录、Token、Cookie、CSRF 与路由策略 |
| [子智能体](docs/plan/subagent.zh.md) | 父子会话、批次与消息投递 |
| [唤醒调度](docs/plan/wake-scheduler.zh.md) | 定时唤醒与重试 |
| [质量门禁](docs/quality-gates.zh.md) | 门禁、预算与跳过规则 |
| [静默异常](docs/silent-exceptions.zh.md) | 静默异常判据与留痕 |
| [写入门禁](docs/write-gate.zh.md) | 写类工具的四步门禁 |
| [视觉操作子系统](docs/subsystems/visual-operator.zh.md) | 截屏、坐标契约与平台后端 |
| [复杂度清单](docs/complexity.md) | 超阈值文件与拆分理由 |
| [单元测试目录](docs/unit-tests.md) | 测试名称、数量与分层 |

</details>
## 开发帮助

### 环境

依赖安装带锁文件，与 CI 同源：

```bash
pip install -e . -c constraints.txt
```

### CI

`scripts/ci.py` 的流水线 37 步：24 项门禁 → 单测 → 10 个验收脚本 → 覆盖率采集 → 分包覆盖率。

24 项门禁覆盖依赖方向、架构约束、配置漂移、生成文档一致性、静态检查、UI/文案、复杂度、适用性、插口配置、插口字段白名单、有效视图、插口可替换（注桩）、字段回潮清扫与并发争用；完整清单用 `--list` 查看。

门禁清单的唯一事实源是 `scripts/ci_steps.py`，由 `check_ci_workflow` 与 GitHub Actions 对齐。

```bash
python scripts/ci.py           # 全部检查
python scripts/ci.py --fast    # 跳过验收
python scripts/ci.py --list    # 列出检查项
```

### 测试

`docs/unit-tests.md` 是生成的可读测试目录，事实源是 `tests/`。

单元测试（2473 个用例）：

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

[MIT License](LICENSE)。第三方组件署名见 [NOTICE](NOTICE)。
