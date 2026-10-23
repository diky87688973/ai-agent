---
name: context-dump
description: 导出当前会话的真实请求上下文：重建 system prompt、模式尾部、消息与工具 schema，输出 JSON 和纯文本。
---

# 导出会话上下文

## 何时使用

用户要求“导出上下文”“查看当前请求上下文”“检查 system prompt / 工具 schema / 压缩后的消息”时使用。

导出是只读操作：不调用模型，不修改会话事实，不落盘任何配置。

## 真实链路

必须使用项目脚本：

```text
scripts/dump_context.py
```

该脚本内部执行：

```text
build_app()
  → 真实 data root / plugins / SessionStore
  → build_snapshot()
  → 读取真实会话事实并重建请求
```

不要用临时脚本或 mock 替代；不要手工拼接 system prompt / messages。

## 确定会话

使用当前会话 ID。若上下文中没有当前会话 ID，先向用户确认，不要猜。

## 输出目录

统一输出到：

```text
data/temp/qa-context/
```

文件名包含会话短 ID 与时间戳，禁止覆盖已有导出：

```text
<短ID>-context-<yyyyMMdd_HHmmss>.json
<短ID>-context-<yyyyMMdd_HHmmss>.txt
```

## 命令

JSON（含完整工具 schema）：

```powershell
python scripts/dump_context.py `
  --cid <当前会话ID> `
  --format json --include-tools `
  --out data/temp/qa-context/<短ID>-context-<yyyyMMdd_HHmmss>.json
```

纯文本：

```powershell
python scripts/dump_context.py `
  --cid <当前会话ID> `
  --format text `
  --out data/temp/qa-context/<短ID>-context-<yyyyMMdd_HHmmss>.txt
```

非默认数据根或插件配置时，再按需追加：

```text
--data-root <数据根>
--plugins-dir <插件根>
--plugins-path <插件清单>
```

## 验收

导出后必须核对：

```text
JSON 可解析
conversation_id 与目标一致
event_count > 0
messages 非空
tools_count 与当前工具数一致（当前 47）
system_prompt 非空
mode_note 符合当前模式
输出文件非空
```

汇报只给摘要：

```text
会话 ID
event_count / messages / tools_count
covered_end
system_prompt / mode_note 字符数
JSON / TXT 文件路径
```

不要把完整上下文粘进回复；其中可能包含用户会话内容。

## 失败处理

- 会话不存在：报告脚本原文，不创建空文件。
- 导出文件为空：报告失败，不继续分析。
- 目录不存在：只创建 `data/temp/qa-context/`，不触碰其他 data 目录。
- 不删除已有导出文件。
