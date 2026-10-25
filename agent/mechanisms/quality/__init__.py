# -*- coding: utf-8 -*-
"""写盘门控与质量管线包 — id 制四步协议（预览 → 确认 → 凭 ID 提交 → 重读）+ 三段检查。

四步协议（id 制，所有提交统一走 confirm_id）：
- 预览：凡 `needs_preview` 的工具写参数快照入库，返回 confirm_id（不落盘）；
  同路径只留最新快照；未提交条数上限 `MAX_PENDING_PREVIEWS`，满则按登记顺序挤掉最旧的；
- 确认（宿主）：confirm(confirm_id)；
- 提交（commit_write）：仅凭 confirm_id —— content 等写参数由本包从快照恢复。

写路径键序只认工具声明的 `write_path_keys`（经 `QualityGate.path_keys_for` 查注册表），
无进程全局键表、无默认猜 `path`。
"""
from __future__ import annotations

from agent.mechanisms.quality.checks import (
    MAX_DIFF_LINES,
    PREVIEW_DIFF_MAX_LINES,
    WriteContext,
    change_payload,
    check_write,
    diff_text,
)
from agent.mechanisms.quality.diagnose import (
    LARGE_DELETE_ADD_RATIO,
    LARGE_DELETE_MIN_LINES,
)
from agent.mechanisms.quality.gate import QualityGate
from agent.mechanisms.quality.path_keys import norm_path, resolve_write_path
from agent.mechanisms.quality.pending import MAX_PENDING_PREVIEWS, PendingStore
from agent.mechanisms.quality.pipeline_bridge import build_pipeline_gate

__all__ = [
    "LARGE_DELETE_ADD_RATIO",
    "LARGE_DELETE_MIN_LINES",
    "MAX_DIFF_LINES",
    "MAX_PENDING_PREVIEWS",
    "PREVIEW_DIFF_MAX_LINES",
    "PendingStore",
    "QualityGate",
    "WriteContext",
    "norm_path",
    "build_pipeline_gate",
    "change_payload",
    "check_write",
    "diff_text",
    "resolve_write_path",
]
