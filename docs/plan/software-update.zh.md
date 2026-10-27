[English](software-update.md) | **中文**

# 软件更新

状态：已实现。

## 1. 边界

更新器替换安装根目录中的程序文件。它不修改运行中的进程，不强制更新，不发布二进制增量包。

目标：

```text
检查 stable 通道，发现更高版本后自动暂存
用户点击更新按钮后才应用
使用完整 zip 包
校验包大小与 SHA-256
用持久化的切换状态标记和备份完成暂存与切换
健康检查失败或切换中断时回滚
暂存完成后删除下载的 zip
保留一份上一版本作为回滚点
不写 data/；*.ini 配置按键合并
```

范围外：

```text
二进制增量
Windows 之外平台的自动更新
源码 checkout 更新
签名校验
```

## 2. 运行约束

```text
入口：安装根目录的 agent-gui.exe
启动器：从安装根目录启动 agent.gui.launcher
版本源：安装根目录的 VERSION
配置：config.ini、plugins.ini、plugins.cli.ini、
      plugins.headless.ini、web-ui-config.ini
用户数据：data/
构建：发布工作流构建 agent-gui.exe、更新包与完整包
```

启动器不读取版本指针，始终从安装根目录启动程序。

禁止的操作：

```text
运行中直接覆盖被其他进程占用的 agent-gui.exe
GUI 运行期间覆盖程序文件
写 data/
更新源码 checkout
```

## 3. 版本契约

`VERSION` 是唯一版本源。界面徽章与更新器都读取它。

格式：

```text
主版本.次版本.修订号
```

解析器还接受可选的预发布后缀；发布版本使用三段式。

比较：

```text
只考虑 channel=stable 的 manifest
远端版本必须高于本地版本
不比较界面徽章、文件时间或依赖版本
```

## 4. 发布契约

每次发布包含：

```text
ai-agent-<version>-update-pack-windows.zip
ai-agent-<version>-full-pack-windows.zip
manifest.json
```

只构建 Windows 包。包名带平台后缀；manifest 不含平台字段。

`manifest.json`：

```json
{
  "schema": 1,
  "app": "ai-agent",
  "version": "0.2.0",
  "channel": "stable",
  "published_at": "",
  "asset": {
    "name": "ai-agent-0.2.0-update-pack-windows.zip",
    "size": 12345678,
    "sha256": "0000000000000000000000000000000000000000000000000000000000000000"
  },
  "notes": []
}
```

`parse_manifest` 要求 `schema=1`、`version`、`channel` 与 `asset`。`asset.name` 只保留文件名；`asset.size` 必须在 1 字节到 1 GiB 之间；`asset.sha256` 必须是 64 位十六进制。`manifest.json` 上限为 256 KiB。`published_at` 与 `notes` 是元数据，界面不展示。

完整性：

```text
asset.size   = zip 字节数
asset.sha256 = zip 的 SHA-256
```

客户端校验 zip 的这两个值。它不校验独立的 manifest 摘要，也不校验签名；manifest 通过 HTTPS 获取。

两个 zip 与 `manifest.json` 作为 Release 资产发布。客户端只把 `manifest.json` 作为版本与校验来源。

## 5. 安装布局

安装根目录是唯一运行目录，不创建版本子目录。

```text
install_root/
  agent-gui.exe
  agent/
  plugins/
  assets/
  catalog/
  launcher/
  scripts/
  rules/
  skills/
  VERSION
  config.ini
  plugins.ini
  plugins.cli.ini
  plugins.headless.ini
  web-ui-config.ini
  data/
  updates/
    apply.json          待执行请求
    download/           下载的 zip，暂存后删除
    staging/<version>/  解压后的 payload 与 .ready 标记
    backup/<version>/   上一版本程序文件
    launcher/           归档的 agent-gui.exe
    state.json          持久化切换状态
    update.log
```

启动器每次启动前运行 `python -m agent.update.recover`。GUI 退出且 `updates/apply.json` 存在时，启动器运行 `python -m agent.update.apply`，然后重复。

更新过程：

```text
staging 保存解压后的 payload
helper 把非运行态程序文件备份到 updates/backup/<old_version>
helper 把 payload 写入安装根目录
*.ini 文件按键合并，其他文件直接替换
成功后删除 staging 与 download
失败后从备份还原
```

`old_version` 是切换前 `VERSION` 的值。

## 6. 更新状态

控制器返回这些字段：`available`、`staged`、`detail`、`current`、`remote`、`channel`、`version`、`interval_minutes`。

`detail` 取值：

```text
idle
disabled
dev_checkout
check_failed: <异常类型>
channel_mismatch
up_to_date
available
download_failed: <消息>
staged
restarting
```

`available` 在远端 stable 版本更高时为 true。`staged` 在 `updates/staging/<version>/.ready` 存在时为 true。自动下载失败后仍保持 `available=true`，新版本不会被标记为已暂存。

`updates/state.json` 持久化切换状态：

```text
switching    正在备份与复制
healthy      目标版本通过健康检查
rolled_back  已从备份还原
```

字段：

```text
phase
from_version
to_version
detail
```

`updates/apply.json` 只是待执行请求，包含 `version` 与 `staging`；helper 执行后删除。切换不是原子目录替换：切换状态标记与备份让逐文件复制在中断后可恢复。

## 7. 界面交互

更新按钮位于页头，主题切换按钮左侧，默认隐藏。

标签：

```text
有可用更新、已暂存     重启更新 v<version>
有可用更新、未暂存     更新 v<version>
检查失败               更新检查失败
其他情况               隐藏
```

点击行为：

```text
检查失败 立即重试 POST /api/update/check
已暂存   POST /api/update/apply；GUI 退出
未暂存   POST /api/update/download，随后在同一次点击中 POST /api/update/apply
```

正常流程中，页面发起的检查会暂存更高版本并显示 `重启更新 vX`；点击一次即应用并重启。自动下载失败时按钮变为下载动作；这次点击会下载并应用。

按钮是唯一的更新入口：不打开卡片，不展示包大小或更新说明，没有取消动作，也没有单独的重启确认。应用前，后端在存在运行中的后台任务或待发送消息时拒绝；页面把按钮标签改为 `更新失败`，错误放在按钮标题中。

页面加载后异步发起检查，不阻塞应用启动。

状态与按钮：

```text
idle、disabled、up_to_date、channel_mismatch、dev_checkout   隐藏
available                                                     显示
check_failed                                                  显示，带错误样式
```

### 7.1 检查时机

页面加载后调用 `POST /api/update/check`。每次响应后按 `interval_minutes` 安排下一次检查。

```ini
[update]
check_interval_minutes = 30
```

范围 1 到 1440 分钟，默认 30；越界值截断。

检查失败时显示错误按钮。点击立即重试；响应后重新计时。

## 8. 端到端流程

### 8.1 检查

```text
POST /api/update/check
读取 check_interval_minutes
安装根目录是开发版时跳过
通过 HTTPS 获取 manifest（45 秒超时）
解析 schema、version、channel 与 asset
拒绝 channel != stable
比较远端版本与 VERSION
更高且未暂存：下载、校验、解压
返回状态
```

发现更高版本时，同一请求完成下载与暂存。manifest 获取或解析失败会写入日志并作为状态返回，不向页面抛错，也不阻塞启动。

### 8.2 下载

```text
updates/download/<asset.name>
```

资源 URL 相对 manifest URL 解析。下载只走 HTTPS，超时 30 秒，直接写入最终文件名，不使用临时文件改名。超过 `asset.size` 的字节被拒绝。下载后由 `verify_asset` 校验大小与 SHA-256；不符时删除 staging 目录并失败。

zip 在 `finally` 中删除，暂存成功或失败都不保留。暂存目录为 `updates/staging/<version>/`；`.ready` 最后写入。已存在的暂存目录先清空。已暂存的版本不会停止检查计时：更高版本暂存成功后会替换它，只保留最新的 staging 目录。

### 8.3 校验与解压

```text
asset 大小
asset SHA-256
zip CRC
```

解压限制：

```text
20000 个条目
解压后总大小 1 GiB
```

路径检查拒绝空、绝对、盘符与 `..` 条目。每个解析后的目标必须位于 staging 版本目录下。条目一律写成普通文件，不重建符号链接。不使用逐文件哈希清单。

### 8.4 应用

`POST /api/update/apply` 先检查没有运行中的后台任务，也没有待发送消息。控制器随后写入 `updates/apply.json`，设置 `detail=restarting`，0.6 秒后退出 GUI 进程。GUI 退出后，启动器发现 `apply.json` 并运行 helper。

安装后的目录中，根目录的 `agent/update/apply.py` 只做引导：读取 `apply.json`，运行 `staging/<version>/payload/agent/update/apply.py`。payload helper 缺失时，继续使用根目录副本。

helper：

```text
要求 staging/.ready 与 payload 下的 agent/ 目录
写入 state，phase=switching，记录 from_version 与 to_version
把非运行态文件备份到 updates/backup/<from_version>
复制 payload 文件；合并 *.ini；锁定的 agent-gui.exe 先归档
写入 VERSION
执行健康检查
```

GUI 已经退出；helper 不自行停止后台任务。apply 路由在后台任务运行时拒绝启动。

### 8.5 健康检查

```text
python -m agent.update.health
```

helper 以安装根目录为工作目录，并把 `AI_AGENT_HEALTH_ROOT` 指向它，超时 30 秒。

检查：

```text
导入 agent.app 与 agent.entry.web
解析 VERSION
在存在时解析 config.ini
解析每个 plugins/*/plugin-config.ini
绑定回环 TCP 端口
```

检查不测试 data 读写、工具注册表或 HTTP 健康接口。

通过：

```text
phase=healthy
删除 staging 与 download
保留备份
```

失败：

```text
还原 updates/backup/<from_version>
写入 phase=rolled_back
删除 staging
保留 update.log
```

成功完成健康检查后，如果旧启动器仍在运行，helper 等待 3 秒后终止它，删除归档的 exe，并启动新 GUI。

### 8.6 崩溃恢复

启动器每次启动前运行 `python -m agent.update.recover`。

`phase=switching` 时：

```text
健康检查通过 -> phase=healthy
健康检查失败 -> 还原备份，phase=rolled_back，删除 staging
```

`phase=healthy` 与 `phase=rolled_back` 在恢复时清除。恢复同时删除 launcher 归档。

切换没有原子目录替换。复制期间崩溃可能留下新旧文件混合；切换状态标记与备份让这个状态可恢复，健康检查决定复制后的目录是否可用。

## 9. 备份与清理

备份包含除运行态目录外的全部文件；`data/` 与 `updates/` 不备份。只保留一份备份：创建新备份时删除 `updates/backup/` 下的其他条目。

```text
成功：删除 staging 与 download；保留备份；删除 launcher 归档
失败：保留备份用于还原；删除 staging；保留 update.log
```

zip 在暂存结束时删除，不等到更新成功。不保留 `versions/` 目录。

## 10. 数据与配置

### 10.1 包内容

两个包都枚举项目树，包含 `scripts/pack_common.py` 未排除的全部文件。更新包把文件放在 `payload/` 下；完整包放在 `ai-agent-<version>-full-pack-windows/` 下。`VERSION` 由构建参数写入，不直接复制。

排除路径：

```text
仅根目录：data/ updates/ versions/ dist/ build/ archive/ tmp/ artifacts/
          screenshots/ logs/ docs/ tests/
任意层级：.git/ .github/ .venv/ venv/ env/ __pycache__/ .ruff_cache/
          .pytest_cache/ .mypy_cache/ .locks/ coverage_html/ htmlcov/
          *.egg-info/
文件：    .coverage .DS_Store Thumbs.db _PRIVATE_RULE.md
后缀：    .pyc .pyo .raw .log .tmp .bak .orig .rej .obj .res .o .pdb .example
敏感项：  .env *.local.ini *.local.toml *.pem *.key *.p12 *.pfx
          plugins/multi_model/plugin-config.ini
```

仅根目录的条目只匹配第一段路径；`plugins/<name>/data/` 这类目录会被打包。更新包没有路径白名单；每个打包文件按原路径应用。

### 10.2 应用规则

普通文件替换同路径文件。`*.ini` 按键合并。

合并规则：

```text
以包内模板为起点
模板中的每个节与键，存在用户值时保留用户值
模板中不存在的节与键删除
通过临时文件写入后替换
```

文件不存在时直接复制模板。这不是全量覆盖：同名键保留用户值，用户额外的节与键不会保留。合并已有文件时，注释不保留；合并后的文件按模板的节与键重写。

`data/` 与 `updates/` 是运行态目录，既不备份也不写入。包不能表达删除；apply 只写入与合并。敏感配置不进入包，保持原状。

复制 `agent-gui.exe` 因文件被锁而失败时，helper 把它改名为 `updates/launcher/agent-gui.exe.old-<时间戳>` 后写入新文件；复制失败时改回原名。健康检查失败时，`restore_backup` 还原备份，并删除备份中不存在的非运行态文件。

非敏感插件配置由包携带。本地缺失的 INI 文件由包内模板创建；更新器不会生成包内没有的配置。

## 11. 开发模式

满足任一条件时禁用更新：

```text
安装根目录存在 .git
AI_AGENT_DEV 为 1、true、yes 或 on
```

检查返回 `dev_checkout`，不下载，按钮保持隐藏。发布包排除 `.git`。

## 12. 平台范围

```text
Windows  已实现；构建更新包与完整包
macOS    未实现
Linux    未实现
```

包名带平台后缀。发布工作流只产出 Windows 包。其他平台没有启动器或更新包。

## 13. 安全

已实现的防护：

```text
manifest 与资产都走 HTTPS
asset 大小与 SHA-256
带路径、文件数与大小限制的安全解压
不重建符号链接
data/ 与 updates/ 不进入 payload
*.ini 按键合并；敏感配置排除
```

限制：

```text
没有签名
没有独立 manifest 摘要
```

HTTPS 保护传输。SHA-256 能发现下载损坏，但不能阻止发布资产被替换；能替换 Release 的一方可以同时替换 manifest 与 zip。更新端点要求 admin scope，没有面向模型的更新能力。

## 14. 模块落点

```text
agent/update/
  __init__.py
  version.py        版本读取与比较
  manifest.py       manifest 解析与资产校验
  checker.py        远端检查
  stage.py          下载、哈希与安全解压
  install.py        备份、复制、还原与清理
  apply.py          helper 入口
  config_merge.py   INI 按键合并
  health.py         切换后自检
  logs.py           JSON Lines 更新日志
  processes.py      旧启动器发现、停止与重启
  recover.py        启动恢复
  state.py          updates/state.json
  assets.py         敏感与本地文件判定

agent/shell/web/web_routes.py
  GET  /api/update/status
  GET  /api/update/logs
  POST /api/update/check
  POST /api/update/download
  POST /api/update/apply

agent/shell/web/web_assets/classic/js/shell/update.js
launcher/launcher.cpp
scripts/pack_common.py
scripts/build_release.py
scripts/build_full_pack.py
```

没有注册面向模型的更新能力。

## 15. 发布与 CI

推送 `v*` 标签启动发布工作流：

```text
校验 VERSION 等于去掉前导 v 的标签
用 launcher/build.ps1 构建 agent-gui.exe
用 scripts/build_release.py 构建更新包与 manifest
manifest 记录 zip 大小与 SHA-256
用 scripts/build_full_pack.py 构建完整包
把两个 zip 与 manifest.json 上传到 Release
```

生成的 manifest 中 `published_at` 为空字符串，`notes` 为空列表。不生成签名、独立 manifest 摘要或校验和文件。只产出 Windows 资产。

## 16. 验证

```text
版本比较：旧 / 同 / 新 / 预发布
开发版：不显示更新按钮
远端不可达：check_failed 状态；显式重试
manifest schema 非法：拒绝
asset 大小或 SHA-256 不符：拒绝
zip 路径穿越：拒绝
zip 文件数或解压体积超限：拒绝
下载中断：删除 staging 与 zip；重试成功
应用时存在后台任务：拒绝
应用时存在待发送消息：拒绝
健康检查失败：还原备份
*.ini 合并保留用户值并删除已移除的键
payload 新文件被安装
data/ 在更新与回滚后保留
切换期间崩溃：recover 完成或回滚
回滚后的版本可启动
暂存后清理 staging 与 zip
保留一份备份
```

## 17. 更新日志

`updates/update.log` 是 JSON Lines。每行包含 `ts`、`event`、`level` 与事件字段。文件超过 1 MiB 时轮转为 `update.log.1`，只保留一代。

事件包括：

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

失败与清理错误也以 `level=error` 写入。`GET /api/update/logs` 默认返回最后 100 行，最多 500 行。错误同时写入 `<data_root>/logs/errors.log`。失败时不删除 `update.log`。
