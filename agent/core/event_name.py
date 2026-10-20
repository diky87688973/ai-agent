# -*- coding: utf-8 -*-
"""事实词汇：内核产出的全部事件名。

## 集中定义

这些名字是对外契约：监控、UI 适配层、测试都按名字订阅，改动即破坏兼容。
散在各模块顶部会让契约看起来像实现细节，也看不出到底有哪些事件。

- 模块发事件时从这里导入常量；
- 新增事件只动这里，改动面一眼可查。

## 三层归属（谁发什么）

| 层 | 事件 | 说明 |
|---|---|---|
| 宿主 | `turn_started` / `turn_ended` | 回合边界归宿主——控制循环的是它 |
| 模块 | 各自的生命周期（见下） | 各模块内部管理自己的事件 |
| 共享 | `input_claimed` / `model_message` / `tool_progress` | 数据事实与副作用 |

## 模块生命周期：统一的 `<域>_started` → 结果 → `<域>_ended`

| 模块 | 开始 | 结果（视情况） | 终态 |
|---|---|---|---|
| 输入 | `input_started` | `input_claimed`（认领到内容时） | `input_ended` |
| 压缩 | `compress_started` | `context_compacted`（真压了才发） | `compress_ended` |
| 模型 | `llm_started` | `llm_done` / `llm_failed` | `llm_ended` |
| 工具 | `tool_started` | `tool_done` / `tool_failed` / `tool_canceled` / `tool_suspended` | `tool_ended` |

成对的作用：① 监听者据此算该环节 RT，不必猜"哪两个事件之间算一次"；
② `_ended` 把所有终止路径（成功 / 失败 / 跳过 / 挂起 / 取消）收成一个出口——
将来新增终止方式时，配对关系不用改。

## 两条读规则

1. `tool_ended` 不带结果：它只标"这次调用结束了"（`status` / `elapsed_ms`）。
   结果在同一次调用先发的 `tool_done{data}` / `tool_failed{error}` 里，
   派生模型消息时必须按 `call_id` 回查（否则模型看到一片 `null`）。
2. `_ended` 是判定边界：是否结束以 `_ended` 为唯一判据，
   不在多处分别判断。
"""
from __future__ import annotations

# ── 宿主：回合边界 ─────────────────────────────────────────
TURN_STARTED = "turn_started"
TURN_ENDED = "turn_ended"

# ── 共享数据事实 ───────────────────────────────────────────
INPUT_CLAIMED = "input_claimed"
MODEL_MESSAGE = "model_message"
USAGE = "usage"
ERROR = "error"
TOOL_PROGRESS = "tool_progress"
#: 会话待发送队列发生变化（只推 UI，不落事实）。
QUEUE_UPDATED = "queue_updated"
CONTEXT_COMPACTED = "context_compacted"
#: 请求装配完成时的分段快照（上下文示意图用）：段名与各段估算 token。
#: 模式说明与工具轮的内部 system 注入都不落记录，只有这条快照留着它们。
CONTEXT_SEGMENTS = "context_segments"

# ── 模型模块的流式增量 ─────────────────────────────────────
ASSISTANT_DELTA = "assistant_delta"
REASONING_DELTA = "reasoning_delta"

# ── 输入模块生命周期 ───────────────────────────────────────
INPUT_STARTED = "input_started"
INPUT_ENDED = "input_ended"

# ── 压缩模块生命周期 ───────────────────────────────────────
COMPRESS_STARTED = "compress_started"
COMPRESS_ENDED = "compress_ended"

# ── 模型模块生命周期 ───────────────────────────────────────
LLM_STARTED = "llm_started"
LLM_DONE = "llm_done"
LLM_FAILED = "llm_failed"
LLM_ENDED = "llm_ended"

# ── 工具模块生命周期 ───────────────────────────────────────
TOOL_STARTED = "tool_started"
TOOL_DONE = "tool_done"
TOOL_FAILED = "tool_failed"
TOOL_CANCELED = "tool_canceled"
TOOL_SUSPENDED = "tool_suspended"
TOOL_ENDED = "tool_ended"

#: 工具生命周期的事实名（供测试与适配层遍历，避免各写一份清单）
TOOL_EVENTS = (TOOL_STARTED, TOOL_DONE, TOOL_FAILED, TOOL_CANCELED,
               TOOL_SUSPENDED, TOOL_ENDED)
