# 软件更新方案

状态：核心链路已实现，待真实安装包升级演练。

## 1. 边界

采用软件更新，不做运行中覆盖，不做无感强制更新，不做首版增量更新。

更新目标：

```text
远端版本高于本地版本时显示按钮
用户点击后才下载
完整安装包 zip 更新
下载包校验大小与哈希；签名作为后续增强
暂存、校验、原子切换
启动失败自动回滚
更新成功后清理 zip
保留上一版本作为回滚点
用户数据不覆盖；更新包内配置全部覆盖
```

暂不处理：

```text
二进制 delta
多平台自动更新
源码 checkout 自动更新
首版采用哈希校验并预留签名字段
```

## 2. 当前约束

```text
入口：根目录 agent-gui.exe
运行方式：启动器寻找同目录 agent/entry/web.py
版本：当前只有界面徽章 v0.1，没有唯一版本源
配置：config.ini、plugins.ini、web-ui-config.ini 在根目录
用户数据：data/
构建：远端 CI 只构建 agent-gui.exe
```

以下动作不可接受：

```text
运行中覆盖 exe
运行中覆盖 Python 源文件
覆盖 data/
在源码 checkout 中自动更新
```

## 3. 版本契约

新增唯一版本源：

```text
VERSION
```

格式：

```text
主版本.次版本.修订号
```

示例：

```text
0.1.0
0.2.0
```

比较规则：

```text
只在 stable 通道比较
远端版本 > 本地版本才显示更新按钮
不比较界面徽章、文件时间或依赖版本
```

## 4. 发布契约

每次发布至少包含：

```text
ai-agent-<version>-update-pack-windows.zip
ai-agent-<version>-full-pack-windows.zip
manifest.json
```

macOS 包名预留：

```text
ai-agent-<version>-update-pack-macos.zip
ai-agent-<version>-full-pack-macos.zip
```

当前只构建 Windows 包。更新包按平台隔离，manifest 不声明支持平台。

`manifest.json`：

```json
{
  "schema": 1,
  "app": "ai-agent",
  "version": "0.2.0",
  "channel": "stable",
  "published_at": "2026-10-24T00:00:00Z",
  "min_launcher": "1.0.0",
  "asset": {
    "name": "ai-agent-0.2.0-update-pack-windows.zip",
    "size": 12345678,
    "sha256": "...."
  },
  "notes": [
    "新增后台任务管理",
    "修复系统通知展示"
  ]
}
```

首版采用哈希校验：

```text
manifest.sha256 = SHA-256(manifest.json)
asset.sha256    = SHA-256(zip)
```

`manifest.sig` 字段预留，首版可以为空。后续启用签名时：

```text
manifest.sig = Ed25519(manifest.json 原始字节)
公钥内置在启动器
私钥只存在远端 CI secret
```

哈希校验能发现下载损坏，但不能防止发布资产被替换；签名是后续的安全增强。

发布资产由代码托管平台的 Release 承载；客户端只把 manifest 作为版本与校验来源。平台由包名隔离，manifest 不含平台字段。

## 5. 安装布局

根目录是唯一运行目录，不创建版本子目录。

```text
install_root/
  agent-gui.exe
  agent/
  plugins/
  assets/
  VERSION
  config.ini
  plugins.ini
  web-ui-config.ini
  data/
  updates/
    download/
    staging/
    backup/
    state.json
    update.log
```

启动器固定从根目录启动，不读取版本指针。

更新时：

```text
staging 是临时解压目录
备份根目录程序文件到 updates/backup/<old_version>
覆盖根目录程序文件
成功后删除 staging 和旧备份
失败后从备份还原根目录
```

## 6. 更新状态机

```text
idle
  ↓ 检查
checking
  ↓ 远端更新
available
  ↓ 用户点击
downloading
  ↓ 下载完成
verifying
  ↓ 校验通过
staged
  ↓ 用户确认重启
applying
  ↓ 更新 helper 接管
restarting
  ↓ 健康检查通过
healthy
```

失败状态：

```text
download_failed
verify_failed
apply_failed
health_failed
```

失败后保持当前版本可用，不删除 zip 与日志。

## 7. 界面交互

在“白天模式”按钮左侧增加：

```text
[icon] 更新 0.2.0
```

只在以下条件全部成立时展示：

```text
远端版本 > 当前版本
channel 匹配
manifest 哈希通过；若提供签名则校验签名
当前不是源码开发模式
```

不展示：

```text
版本相同
远端版本更低
离线
检查失败
开发版
```

点击后打开更新卡片：

```text
版本：0.2.0
大小：12.3 MB
更新说明
[下载并校验] [取消]
```

下载完成后：

```text
[立即重启更新] [稍后]
```

应用更新前提示：

```text
更新会重启应用；正在运行的后台任务和未确认的操作会被中止。
```

检查更新异步执行，不阻塞启动。

## 7.0 一键更新

```text
检查到新版本
→ 自动下载并校验
→ 解压到 staging
→ 顶部显示“重启更新 vX”
→ 点击一次
→ 自动退出并安装
```

不再要求用户先点下载、再点重启。

如果自动下载失败，按钮可点击重试；重试成功后直接进入安装。

已经下载但用户没有点击安装时，仍按间隔检查更新。发现更高版本后，下载新版本并删除旧 staging，只保留最新一份。

## 7.1 检查时机

```text
启动后检查一次
之后按配置间隔检查
```

配置：

```ini
[update]
check_interval_minutes = 30
```

有效范围：1..1440 分钟，默认 30。

检查失败时显示“更新检查失败”，点击可立即重试；失败后仍按间隔重试。

## 8. 端到端流程

### 8.1 检查

```text
启动后异步检查
获取远端 manifest
验证 manifest 哈希；若提供签名则校验签名
比较版本
显示按钮
```

检查失败只记录状态，不弹错误，不阻塞应用。

### 8.2 下载

```text
updates/download/<asset>.zip
```

限制：

```text
HTTPS
超时
最大体积
完成后原子改名为 .zip
```

### 8.3 校验与解压

```text
manifest 哈希（可选签名）
zip SHA-256
zip 大小
zip 完整性
安全解压
文件哈希校验
```

解压到：

```text
updates/staging/<version>/
```

拒绝：

```text
绝对路径
盘符路径
.. 路径
符号链接
超出 payload 根
超限解压
清单外可执行文件
```

### 8.4 应用

用户确认后：

```text
停止后台任务
等待会话队列清空
关闭 Web 服务
启动更新 helper
主程序退出
```

更新 helper：

```text
根目录 helper 只负责引导
读取 apply.json
执行 staging/payload/agent/update/apply.py
新 helper 等待旧进程退出
确认 staging 完整
写入 updates/state.json，phase=switching；updates/apply.json 只作为待执行请求
记录旧版本与目标版本
备份根目录程序文件到 updates/backup/<old_version>
用 staging 覆盖根目录程序文件
执行健康检查
```

### 8.5 健康检查

新版本执行：

```text
agent-gui.exe --self-check
```

检查：

```text
版本正确
模块可导入
配置可读
data 可读写
插件清单可加载
工具注册表完整
端口可绑定
健康接口可访问
```

通过：

```text
phase=healthy
删除 staging 与 zip
保留唯一一份更新前备份
清理更旧备份
```

失败：

```text
从 updates/backup/<old_version> 还原根目录
恢复旧 VERSION
保留日志用于诊断
清理 staging
```

### 8.6 断电与崩溃恢复

`updates/state.json` 记录（`updates/apply.json` 只保存待执行请求）：

```text
phase
from_version
to_version
started_at
```

启动器发现 `phase=switching` 时：

```text
健康检查通过 → 标 healthy
否则 → 从备份还原根目录
```

## 9. 备份与清理

```text
备份根目录程序文件到 updates/backup/<old_version>
只保留一份更新前备份
成功后删除 staging、zip 和更旧备份
失败时保留备份供还原
```

不保留 versions 目录，不保留历史版本目录。

## 10. 数据与配置

更新包和完整包都打包项目全部文件：

```text
agent/
plugins/
assets/
scripts/
rules/
skills/
config.ini
plugins.ini
plugins.cli.ini
plugins.headless.ini
web-ui-config.ini
VERSION
README.md
LICENSE
NOTICE
VERSION
```

排除非项目资源：

```text
.git/
.github/
data/
tests/
docs/
updates/
versions/
dist/
build/
__pycache__/
*.pyc
*.raw
*.log
*.tmp
*.obj
*.res
*.example
.env / *.local.ini / *.local.toml
*.pem / *.key / *.p12 / *.pfx
plugins/multi_model/plugin-config.ini
```

更新包内所有文件都按原路径处理；没有路径白名单。普通文件覆盖，`*.ini` 走 key 级合并，保留用户已有值。

```text
payload/ 下普通文件 → 安装根对应路径覆盖
payload/ 下 *.ini     → key 级合并，用户值优先
覆盖前全量备份到 updates/backup/<old_version>/
健康检查失败 → 全量恢复备份
更新默认不删除本地文件
```

删除只允许由后续版本显式列出的删除清单执行，不扫描目录推断，不做白名单/黑名单。

运行中的 `agent-gui.exe` 会被 Windows 锁定：先把旧 exe 改名为 `updates/launcher/agent-gui.exe.old-<时间戳>`，再写入新 exe。健康检查通过后等待 3 秒，旧 GUI 仍存在则终止并启动新 GUI，随后清理归档。

唯一不覆盖的运行态目录：

```text
data/
updates/
```

发布包本身排除敏感配置（`.env`、`*.local.ini`、`*.pem`、`*.key`、`plugins/multi_model/plugin-config.ini`）；这些文件不在包里，因此不会被覆盖。

## 10.2 发布包校验

发布包必须通过以下检查才允许上传：

```text
plugins.ini 中每个启用的插件都有配置
新插件配置已包含在 payload
manifest 中配置文件清单完整
配置 schema 可解析
```

新插件配置缺失属于发布缺陷，不得由 updater 在用户机器上补建；敏感配置例外，保留本地现状。
## 11. 开发模式

以下情况禁用更新：

```text
存在 .git 目录
AI_AGENT_DEV=1
检测为源码 checkout
```

界面不显示更新按钮，或显示：

```text
开发版不参与自动更新
```

## 11.1 平台范围

```text
Windows：完整自动更新，当前唯一构建平台
macOS：未实现，未构建安装包
Linux：未实现，未构建安装包
```

平台之间不共享更新包，包名必须带平台后缀。

macOS 如果没有签名与公证，更新包可能被系统拦截或标记隔离；这属于发布前置条件，不在更新器内部绕过。

## 12. 安全要求

首版：

```text
HTTPS 下载
manifest SHA-256
zip SHA-256
安全解压
路径穿越防护
包内文件全部覆盖；仅 data/ 与 updates/ 保持运行态
```

后续启用签名后增加：

```text
manifest Ed25519 签名
公钥内置
私钥只存在远端 CI secret
```

哈希能发现下载损坏；签名用于抵抗发布资产被替换，首版先不假装已经具备签名安全。

## 13. 模块落点

```text
agent/update/
  __init__.py
  version.py          # 版本读取与比较
  manifest.py         # manifest 解析与签名校验
  checker.py          # 远端检查
  downloader.py       # 下载、哈希、超时
  archive.py          # 安全解压与文件校验
  controller.py       # 状态机与 UI API

agent/capabilities/builtin/update_status.py
  # 可选：让模型查询更新状态，不给模型直接更新权限

agent/shell/web/web_update.py
  # GET  /api/update/status
  # POST /api/update/download
  # POST /api/update/apply

launcher/launcher.cpp  # 固定根目录启动 app 与 updater
```

## 14. 发布与 CI

发布流程：

```text
打 tag
→ 构建 agent-gui.exe
→ 构建 Windows 更新包
→ 构建 Windows 完整包
→ 生成 manifest.json
→ 计算 zip 与 manifest 的 sha256
→ 上传 Release 资产
```

首版不执行签名；未来签名步骤：

```text
→ 用 CI secret 对 manifest 签名
→ 上传 manifest.sig
```

未来签名 key：

```text
openssl genpkey -algorithm ED25519 -out update-private.pem
openssl pkey -in update-private.pem -pubout -out update-public.pem
```

```text
公钥提交到仓库
私钥只存在远端 CI secret
没有 secret 时不得发布带签名的生产更新包
```

密钥生成一次后离线保存；泄露时更换公钥并发布新启动器。

## 15. 测试矩阵

```text
版本比较：旧 / 同 / 新 / 预发布
开发模式：不显示按钮
远端不可达：静默失败
manifest 签名错误：拒绝
zip 哈希错误：拒绝
zip 路径穿越：拒绝
zip 超限：拒绝
下载中断：清理临时文件，重新下载
更新时后台任务运行：阻止并提示
更新时确认挂起：阻止并提示
健康检查失败：回滚
更新包内配置被覆盖
更新包内新文件被安装
更新后 data 保留
断电恢复：回滚或完成
旧版本回滚可启动
zip 成功后清理
备份保留一版
```

## 16. 实施顺序

```text
阶段 1：版本源、manifest、发布打包与哈希
阶段 2：更新检查 API、顶部按钮、下载与校验
阶段 3：根目录原地更新、备份与启动器
阶段 4：更新 helper、健康检查、回滚
阶段 5：清理策略、发布流程、故障演练
阶段 6：增量文件 manifest
```

## 17. 升级演练

演练使用独立安装目录与独立数据根，不读写当前工程的 data/。

### 17.1 基线发布

```text
确认工作区干净
确认 VERSION 与 pyproject.toml 都是 0.1.0
提交到 main
打 tag v0.1.0
push main 与 tag
```

```bash
git status
git tag v0.1.0
git push origin main
git push origin v0.1.0
```

等待 Release 工作流完成，确认：

```text
releases/latest/download/manifest.json 可访问
manifest.asset.sha256 与 zip 一致
```

### 17.2 建立演练安装

```text
复制当前工程到独立目录
删除 .git
删除 data/、tests/、docs/、.github/、dist/、updates/
删除 .coverage、缓存目录
保留 agent-gui.exe、agent/、plugins/、assets/、VERSION、config.ini、plugins.ini、web-ui-config.ini
```

启动演练 GUI，使用独立数据根：

```powershell
$env:AI_AGENT_DATA_ROOT = "$env:TEMP\update-rehearsal-data"
```

冒烟检查：

```text
会话可创建
模型可调用
工具可执行
队列可发送
后台任务可创建
无更新按钮
```

### 17.3 发布新版

在当前工程修改页面顶部，增加红色文字：

```text
升级演练
```

同时修改版本：

```text
VERSION = 0.1.1
pyproject.toml version = 0.1.1
```

提交并发布：

```bash
git add .
git commit -m "feat: 增加升级演练标识"
git push origin main
git tag v0.1.1
git push origin v0.1.1
```

等待 Release 工作流完成。

### 17.4 执行升级

```text
演练 GUI 刷新或重启
顶部出现“更新 0.1.1”
点击更新
下载完成
点击重启更新
应用退出
updater 覆盖根目录
新版本启动
```

检查：

```text
顶部红色“升级演练”
根目录 VERSION = 0.1.1
updates/backup/0.1.0 存在一份备份
config.ini 与更新包一致
插件配置与更新包一致
data/ 保留
更新按钮消失
```

### 17.5 失败路径

```text
篡改 zip 或 manifest 哈希 → 拒绝下载
删除新版本模块 → 健康检查失败 → 回滚
更新时运行后台任务 → 拒绝
更新时存在待发送队列 → 拒绝
切换期间强杀进程 → 下次启动 recover 回滚
```

### 17.6 截图证据

```text
演练版本无更新按钮
新版 Release 资产
更新按钮出现
下载完成
重启后的红色“升级演练”
根目录 VERSION 与 updates/backup 目录
```

## 17.7 更新日志

每次检查和升级写入：

```text
updates/update.log
```

JSON Lines，记录：

```text
check_start
check_skip
check_result
download_start
download_staged
apply_requested
apply_start
apply_success
apply_failed
apply_health_failed
stage_start
stage_ready
stage_failed
recover_start
recover_rolled_back
```

查看接口：

```text
GET /api/update/logs
```

错误日志仍在数据根：

```text
<data_root>/logs/errors.log
```

更新按钮检查失败时显示“更新检查失败”，点击可重新检查；日志用于定位原因。

## 18. 已确认决策

1. 根目录是唯一运行目录，不使用 versions 子目录。
2. 首版只做哈希校验；manifest 预留签名字段，后续支持 Ed25519。
3. 当前只实现 Windows；macOS 与 Linux 尚未实现。
4. 更新包内所有文件按路径全量覆盖；只有 data/ 与 updates/ 保持运行态。
5. 首版只发布 stable；beta 通过 `channel` 字段预留。
6. 启动后自动检查并显示更新按钮；下载与安装都由用户点击确认。
7. `defaults/` 改名为 配置文件，只作为默认配置模板来源。

## 19. 后续决策

```text
macOS 应用包形态与签名/公证流程
beta 通道开关的 UI 形态
更新检查的缓存周期与失败重试策略
是否对更新 helper 做独立签名
```
