# AGENTS.md

本项目是本地运行的 AI Agent：入口读取配置，壳层负责 Web/桌面/CLI，能力层注册工具与插件，机制层提供模型、上下文、存储与门控，内核层执行模块链并产出事实。

修改代码前先读：

- [`README.zh.md`](README.zh.md)：项目入口与命令
- [`docs/architecture.md`](docs/architecture.zh.md)：五层结构、模块链、事件与装配
- [`docs/engineering-standards.md`](docs/engineering-standards.zh.md)：模块职责与资产归属
- [`docs/quality-gates.md`](docs/quality-gates.zh.md)：门禁、预算与跳过规则
- [`docs/guide/config.md`](docs/guide/config.zh.md)：配置键与运行态目录

## 工程标准前置

任何方案、代码修改、修复和复核，都从工程标准开始，不等待用户再次提醒：

- 先读 `production-standards`、`skills/audit-procedure.md`、`docs/applicability.md` 和本文件。
- 方案阶段同时给出：目标、边界、资产归属、失败路径、测试、门禁与未验证项。
- 代码阶段同时落实：输入校验、错误留痕、权限边界、原子性、测试与生成物同步。
- 复核阶段按 `audit-procedure` 的模板输出，不以“全量 CI 通过”替代工程复核。
- 发现 `MUST` 违规、安全缺口或不可验证项时，明确标为阻塞或残余，不口头豁免。
- 平台相关实现对每个目标平台写明已验证、未验证与失败行为。

## 仓库布局

```text
agent/
  core/           内核：模块链、宿主、端口、事件与数据契约
  mechanisms/     模型、上下文、压缩、质量门控、会话存储、协作网格
  capabilities/   工具注册表、内置工具、插件加载
  shell/          Web、SSE、经典界面、系统提示词、会话运行
  shell/web/auth/ HTTP 鉴权：密码、会话、Token、CSRF、路由策略
  entry/          进程入口：读配置、建 App、启动壳
  app.py          唯一装配根
  subagent/       父子会话、批次、生命周期与消息投递
plugins/<name>/   插件自有工具、配置、UI、主题与图标
rules/            运行规则
skills/           技能与审计/生产标准
scripts/          门禁、生成器、验收、构建
docs/             架构、子系统、指南与设计记录
tests/            单元测试与验收夹具
data/             会话与运行态数据，不是源码
updates/          安装器暂存、备份与状态，不是源码
```

## 常用命令

```bash
python -m pip install -e . -c constraints.txt

# 单元测试
python -m unittest discover -s tests -p "test_*.py" -t tests
python -m unittest tests.<module>

# 全量门禁
python scripts/ci.py
python scripts/ci.py --fast        # 跳过验收
python scripts/ci.py --list        # 只列步骤

# 覆盖率
python scripts/run_coverage.py
python scripts/check_coverage.py

# 生成物
python scripts/gen_catalog.py
python scripts/gen_unit_tests_md.py
python scripts/gen_complexity_md.py
python scripts/gen_ci_workflow.py

# 单项检查
python scripts/check_ui_js.py
python scripts/check_catalog.py
python scripts/check_complexity.py
python scripts/check_readme.py
```

全量 CI 只在用户明确要求、提交准入或 CI 诊断时运行；日常改动先跑受影响测试和静态检查。

## 架构边界

依赖方向固定为：

```text
entry → shell → capabilities → mechanisms → core
```

- `agent/app.py` 是唯一装配根，不属于五层；只有它可以同时引用五层。
- 下层四层不得运行期导入 `agent/app.py` 或 `agent/entry/`；`if TYPE_CHECKING:` 的纯注解除外。入口层可以导入 `agent/app.py`。
- `agent/core/` 不得出现具体插件名或具体 provider 实现名。
- 模块之间通过既有端口、事件、注册表或窄接口通信；不得跨层导入私有名。
- 控制流走返回值，业务数据走事件；不得把业务数据塞进控制结果。
- 每份可变状态只有一个权威持有者：进程级在 `AppContext`，会话级在 `SessionContext`/`LiveState`，回合级在 `ToolTurnContext`。
- 模型可见必须已记录：事实流是唯一真相，界面与模型请求都从事实投影。
- 工具调用必须经 `ToolPipeline`；模型可见工具由角色视图过滤，提示词与工具 schema 必须使用同一视图。

## 资产归属

新增或移动资产前，先确认：

- 它属于哪个模块，为什么不能由相邻模块拥有
- 是否能由既有字段派生，因而不新增字段
- 唯一注册点在哪里
- 缺失、加载失败、卸载时影响谁
- 是否有重复副本

约束：

- 插件私有 UI、配置、图标与主题归插件自身；公共壳层资产归 `agent/shell/web/`。
- Provider 具体实现不互导；只有 `provider_registry.py` 装配具体 provider。
- `ContextCompactor` 只依赖 `context/contract.py`，不导入上下文管线内部实现。
- 生成物由脚本生成，不手工维护：
  `catalog/tools.json`、`docs/unit-tests.md`、`docs/complexity.md`、`.github/workflows/ci.yml`。
- README 中的用例数、步骤数、验收脚本数必须与代码一致。

## 更新与数据

- `data/` 是用户会话与运行态数据：不删除、不移动、不覆盖，不放入源码树。
- `updates/` 是安装器状态与备份：不接受源码或测试写入。
- 更新包默认只增加和覆盖文件，不删除本地文件；删除必须由后续版本显式列出。
- 普通更新文件按包内路径覆盖；`*.ini` 按 key 合并，保留用户已有配置值。
- 更新包构建使用黑名单排除运行态、缓存、构建产物与敏感配置；不得改用允许清单。
- `VERSION` 与 `pyproject.toml` 的版本必须一致。

## HTTP 鉴权与密码维护

鉴权属于 `agent/shell/web/auth/`，不进 core，不登记进 `AppContext`。HTTP 请求在 Handler 入口经过 `Authenticator → RoutePolicy → Authorizer → CsrfGuard`；插件路由与内置路由走同一闸门。

模式：

```ini
[auth]
mode = required
desktop_auto_login = 1
allowed_hosts = 127.0.0.1,localhost,::1
trusted_proxies =
```

```text
auto      回环请求免登录；非回环请求必须登录
local     只允许回环地址；非回环地址拒绝启动
required  所有请求必须登录；浏览器访问回环地址也一样
```

反代与公网：

- `required` 是反向代理和公网暴露的唯一推荐模式。
- 非回环绑定必须有 TLS；无 TLS 只能显式 `--allow-insecure-public`。
- 不得用“请求来自 127.0.0.1”作为免登录依据。
- `/healthz` 公开且只返回服务存活信息；`/health` 必须认证。
- `allowed_hosts` 是 Host 白名单；公网域名或反向代理域名必须显式加入。
- 只有 `trusted_proxies` 内的来源可提供 `X-Forwarded-For` 与 `X-Forwarded-Proto`。
- 鉴权失败、限流、桌面 bootstrap、CSRF 拒绝写入 `data/auth/auth.log`，不得记录密码、Cookie 或 Token。

GUI：

- GUI 启动器生成一次性 bootstrap token，通过环境变量传给 `agent-web`。
- WebView 打开 `/desktop-login#<token>`，服务端只接受回环来源且只消费一次。
- GUI 免登录；浏览器仍然需要登录。
- `required` 下 GUI 使用 `/healthz` 做健康检查。
- GUI 启动失败必须显示可见错误，不得静默退出。

密码：

```bash
python -m agent.entry.web --set-password
```

- 密码只保存 scrypt 哈希，位置为 `data/auth/credentials.json`。
- 不得把明文密码写入 `config.ini`、源码、日志、提交或 Release。
- `required` 且没有凭据时，GUI 首次启动自动生成随机密码并写 `data/auth/initial-password.txt`；已有手动密码时不会生成该文件。
- GUI 首次启动自动生成的密码以 `initial-password.txt` 为准；浏览器登录使用该密码。
- 手动设置密码后，已有内存会话不会因写文件自动撤销；需要撤销会话时重启服务。
- 丢失密码时停止服务后重新执行 `--set-password`；不要在运行中直接改写凭据文件。

API Token：

```bash
python -m agent.entry.web --issue-token NAME --scope read,chat
python -m agent.entry.web --revoke-token NAME
```

- Token 只存 SHA-256，位置为 `data/auth/tokens.json`。
- `issue` / `revoke` 同时持有进程内线程锁和 `tokens.json.lock` 跨进程文件锁；同名 Token 拒绝重复签发，锁不可用时拒绝写入。
- Token 只通过 `Authorization: Bearer` 传递，不放进 URL、Cookie、日志或截图。
- Token scope 与 cookie 会话分开校验；高风险配置/更新路由要求 admin。
- `data/auth/` 是运行态敏感目录：不删除、不移动、不提交、不打进发布包、不进入普通数据备份。
- 鉴权文件默认写入 `data/auth/`；启动无法使用该目录时，自动回退到 `data/auth2`、`auth3` 等，仍留在 `data` 内。
- 鉴权文件通过 `auth/security.py` 写入：Windows 使用 DACL，POSIX 使用 0700/0600，macOS 同时清理 ACL。
- 目录和文件在创建时立即收紧，写入后复核；无法保证权限时拒绝启动。
- ACL 被外部改宽时，启动清理会先 `icacls /reset` 再重新收紧；如果 deny ACE 让 `/reset` 也失败，启动自动切换到 `data/auth2` 等新目录。GUI 会生成新密码继续运行；非 GUI 的 `required` 模式仍需先 `agent-web --set-password`，否则拒绝启动。旧 `data/auth` 保留但不再读取，需人工清理。
- 鉴权测试使用临时 `AI_AGENT_DATA_ROOT`，不得污染工程 `data/`。

## 版本升级

只在用户明确要求升级或发版时执行。当前版本必须同步到：

```text
VERSION
pyproject.toml [project].version
README.md 徽章 version-vX.Y.Z-blue
agent/shell/web/ui_bundle.py 版本兜底 vX.Y.Z
docs/assets/desktop.png（截图包含版本号时必须同步）
```

步骤：

1. 先读上述文件当前内容。
2. 同步版本号；只改当前版本引用，不改 `docs/plan/` 里的历史版本示例。
3. 按「README 截图」重新生成截图。
4. 运行受影响检查：`check_readme.py`、`check_ui_js.py`、受影响单测。
5. 核对 `VERSION`、`pyproject.toml`、README 徽章、UI 兜底版本完全一致，截图中的版本与当前版本一致。
6. 提交、打 tag、创建 Release 必须等用户明确要求；不得升版本后自动发布。
7. Release 正文必须写明本版内容，不能空白，也不能只有 Full Changelog。

## 发版说明

Release 正文至少包含：

```text
本版版本号
本版变更
修复与兼容性影响
升级注意事项
实际执行的验证结果
```

发布命令必须使用明确的正文来源，例如：

```bash
gh release create vX.Y.Z <assets> \
  --title vX.Y.Z \
  --notes-file release-notes.md
```

禁止：

```text
--generate-notes 后正文只有 Full Changelog
空正文
只写“常规更新”
```

`.github/workflows/release.yml` 必须从本版提交说明生成本版正文；正文为空时让 Release 失败，不得创建空 Release。

## README 截图

截图使用隔离运行实例，禁止使用、改动或清理工程 `data/`。

```powershell
$root = Join-Path $env:TEMP ("ai-agent-readme-shot-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $root | Out-Null
$env:AI_AGENT_DATA_ROOT=$root
python -m agent.entry.web --host 127.0.0.1 --port 3176
```

截图规格：

```text
视口：1440 × 1000
左侧：3 个正常会话
当前会话：有正常对话内容
消息队列：有 1 条待发送消息
AI说话：播放控件可见
子智能体：只显示折叠状态
后台任务：只显示折叠状态
知识库：不打开
会话标签：只保留当前会话，不保留空的新会话标签
版本：右上角或徽标显示当前版本
```

操作：

1. 备份 `docs/assets/desktop.png`。
2. 用真实 UI 创建 3 个正常会话，标题分别为「整理接口文档」「排查构建失败原因」「补充测试用例」。
3. 在「补充测试用例」中发送正常任务：

```text
创建两个子智能体：资料整理、代码审查，然后汇报当前安排。
```

不要写「请用语音」「请调用 ai_speak」之类指令，AI说话应由插件提示自然触发。

4. 为当前会话创建后台任务：

```text
POST /api/background/tasks/create

{
  "conversation_id": "<当前会话ID>",
  "label": "构建检查",
  "argv": ["python", "-c", "import time; time.sleep(120)"],
  "timeout_sec": 180
}
```

5. 等待播放条出现：

```text
.ai-speak-player:not([hidden])
```

6. 播放控件可见时，再发送一条普通补充消息，让消息队列出现：

```text
补充：先给出结论。
```

7. 关闭自动创建的空会话标签；不要打开知识库，不要展开子智能体或后台任务列表。
8. 截图保存到 `docs/assets/desktop.png`。
9. 停止临时服务，只删除自己创建的 `$root` 和临时截图；工程 `data/` 一律不动。
10. 核对截图：3 个会话、播放控件、消息队列、两个折叠面板、无知识库、无空标签、版本正确。

## 测试与清理

- 测试数据必须指向临时 `AI_AGENT_DATA_ROOT`，测试结束当场清理。
- 不得为让测试通过修改工程 `data/`、真实配置或运行中的会话。
- 失败路径、取消路径、边界条件与并发行为必须有测试；只测正常路径不算完成。
- 新增或修改门禁必须同时提供负向用例，证明坏输入会失败。
- 前端动态列表使用事件委托，不在每个动态节点上逐个绑监听器。

## 变更纪律

- 修改前读取文件当前内容；修改后复核落盘状态。
- 不引入项目外 Skills、外部配置、模拟开关或临时旁路。
- 不为当前用例在生产代码中留测试分支。
- 不提交密钥、真实配置、运行态数据、截图、缓存或临时文件。
- 未经明确要求不 commit、不 push、不重启进程、不改远端配置。
- 生成物变更后运行对应生成器，并重新运行受影响门禁。

## 注释与文档

- 注释只解释代码为什么这样做、约束、边界与失败后果，不复述代码在做什么。
- 不写过程叙述、轮次、历史原因、版本/阶段口吻、对读者叮嘱或设计辩护。
- 文档写当前事实与契约；生成文档以脚本为准。
- 用户可见文案与错误信息必须具体、可执行，不使用含糊措辞。

## 冲突处理

按以下顺序判断，不凭记忆或历史对话：

1. `skills/production-standards.md`
2. `skills/audit-procedure.md`
3. `docs/architecture.md`、`docs/engineering-standards.md`、`docs/quality-gates.md`
4. `rules/`
5. 当前代码与可执行门禁

标准与项目规则冲突时，先修正规则或文档，再改实现。

## 维护本文件

保持本文件是仓库操作手册，不是过程记录：

- 规则必须能落到目录、命令、文档或门禁。
- 路径使用相对路径，不写死本机目录。
- 新增约束时同步更新对应门禁或负向测试。
- 内容变长时先合并重复规则，再考虑增加章节。
