# -*- coding: utf-8 -*-
"""经典界面契约常量（适配层的单一事实源）。

适配层两端的字段名必须完全对齐，而这些名字散布在
163 KB 的老 `agent-ui.js` 里。把"谁读什么字段"集中到这里，任何一处对不上都能在
一处改，也能被契约测试逐条钉住。

经典界面的三条硬约束：
  1. **每帧必须带合法 `conversation_id`**（`/^[A-Za-z0-9_-]{8,128}$/`），否则经典界面
     **整包静默丢弃**（agent-ui.js:100）；只有 `heartbeat` / `global_sse_ready` 豁免。
  2. **`tool_call_id` 是 tool_start / tool_end 的唯一配对键**，为空或对不上 → `tool_end`
     被整个忽略（agent-ui.js:2013），卡片永远停在"进行中"。
  3. **`reasoning_delta` 前置 `llm_round`**，且 `round` 相等，否则丢弃（agent-ui.js:1674）。
"""
from __future__ import annotations

import re
from typing import Final

# ── 会话 ID（经典界面的校验口径，agent-ui.js:8）────────────────
CID_PATTERN: Final = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


def normalize_cid(value: object) -> str:
    """按经典界面的 `normalizeConversationId` 归一化：不合法返回空串。"""
    text = str(value or "").strip()
    return text if CID_PATTERN.match(text) else ""


# ── 事件名（服务端 → 前端）──────────────────────────────────
# 经典界面读的 30 种；`handleGlobalSseEvent`（agent-ui.js:144-178）是超集口径。
EV_CONVERSATION: Final = "conversation"
EV_RUN_STARTED: Final = "run_started"
EV_ASSISTANT: Final = "assistant"
EV_ASSISTANT_DELTA: Final = "assistant_delta"
EV_ASSISTANT_MARKDOWN: Final = "assistant_markdown"
EV_REASONING_DELTA: Final = "reasoning_delta"
EV_REASONING_SYNC: Final = "reasoning_sync"
EV_LLM_ROUND: Final = "llm_round"
EV_LLM_REQUEST: Final = "llm_request"
EV_LLM_RESPONSE: Final = "llm_response"
EV_LLM_DONE: Final = "llm_done"
EV_TOOL_START: Final = "tool_start"
EV_TOOL_END: Final = "tool_end"
EV_TOOL_PROGRESS: Final = "tool_progress"
EV_TOOL_PREVIEW_UPDATE: Final = "tool_preview_update"
EV_TODO_LIST: Final = "todo_list"
EV_USAGE: Final = "usage"
EV_CONTEXT_LAYOUT: Final = "context_layout"
EV_CONTEXT_SEGMENTS: Final = "context_segments"
EV_MODE_CHANGED: Final = "mode_changed"
EV_DISPATCH_TITLE: Final = "dispatch_title"
EV_DONE: Final = "done"
EV_ERROR: Final = "error"
EV_STOPPED: Final = "stopped"
EV_INBOX_QUEUED: Final = "inbox_queued"
EV_PEER_MESSAGE: Final = "peer_message"
EV_AUDIO: Final = "audio"                      # 保留常量以便自检"不发它"
EV_OPEN_SESSION: Final = "open_session"
EV_PAUSED_FOR_CONFIRM: Final = "paused_for_user_confirm"
EV_HEARTBEAT: Final = "heartbeat"
EV_GLOBAL_SSE_READY: Final = "global_sse_ready"

#: 经典界面**豁免** `conversation_id` 校验的两个事件（agent-ui.js:145 第一行就 return）
CID_EXEMPT_EVENTS: Final = frozenset({EV_HEARTBEAT, EV_GLOBAL_SSE_READY})

#: 适配层明确**不发**的事件（当前没有对应能力）
NEVER_EMIT: Final = frozenset({EV_AUDIO})


# ── 工具名映射：内核工具 → 经典界面的 `script` 标识 ─────────────
# 经典界面靠 `script` 决定图标（toolIco agent-ui.js:1179）、中文名（buildToolTitleParts
# agent-ui.js:1263）与是否"实时输出"。**名字必须落在它认识的集合里**，否则标题会退化。
# 来源：经典界面的 ICONS / LABELS 表（agent-ui.js 内 `toolIco` / `toolZh`）。
TOOL_SCRIPT_MAP: Final = {
    # 读
    "read_file": "read_file",
    "find_in_file": "find_in_file",
    "grep_files": "grep_files",
    "glob_files": "glob_files",
    "file_search": "file_search",
    "regex_locate": "regex_locate",
    "list_dir": "glob_files",
    "fs_list": "glob_files",
    # 写
    "write_file": "write_file",
    "replace_in_file": "replace_in_file",
    "apply_patch": "apply_patch",
    "commit_write": "commit_write",
    # 命令
    "run_command": "run_command",
    "python_inline": "python_inline",
    # 任务
    "todo_list": "todo_list",
    "run_type": "run_type",
    "user_confirm": "user_confirm",
    "task_sleep": "task_sleep",
    "goal": "goal",
}


def tool_script(kernel_tool_name: str) -> str:
    """内核工具名 → 经典界面的 `script`。未知工具原样透传（经典界面有兜底图标）。"""
    name = str(kernel_tool_name or "").strip()
    return TOOL_SCRIPT_MAP.get(name, name)


# ── usage 字段名（**两套，不可复用**）────────────────────────
# SSE 的 `usage` 事件（agent-ui.js:156）与 `/api/usage-accumulator`（agent-ui.js:1176）
# 用**完全不同的字段名**，混用会导致其中一边永远为 0。
SSE_USAGE_FIELDS: Final = (
    "prompt_tokens", "completion_tokens",
    "prompt_cache_hit_tokens", "prompt_cache_miss_tokens",
)
ACCUMULATOR_USAGE_FIELDS: Final = (
    "total_prompt_tokens", "total_completion_tokens",
    "total_cache_hit_tokens", "total_cache_miss_tokens",
    "total_tokens",
)


# ── HTTP 端点（经典界面会调的）────────────────────────────────
EP_SEND: Final = "/api/chat/send"
EP_STOP: Final = "/api/chat/stop"
EP_HISTORY: Final = "/api/chat/history"
EP_SESSIONS: Final = "/api/chat/sessions"
EP_UI_STATE: Final = "/api/chat/ui-state"
EP_USER_CONFIRM: Final = "/api/chat/user-confirm"
EP_TITLE: Final = "/api/chat/title"
EP_AUTONOMOUS: Final = "/api/chat/autonomous"
EP_COMMAND_INPUT: Final = "/api/chat/command-input"
EP_ATTACHMENT: Final = "/api/chat/attachment"
EP_EVENTS: Final = "/api/events/stream"
EP_DIR_BROWSE: Final = "/api/dir-browse"
EP_REASONING: Final = "/api/reasoning-effort"
EP_PRICING: Final = "/api/model-pricing"
EP_USAGE_ACC: Final = "/api/usage-accumulator"
EP_HEALTH: Final = "/health"


# ── 模式取值（经典界面的 normalizeMode，agent-ui.js:372）───────
MODE_VALUES: Final = ("auto", "plan", "execute")


def normalize_mode(value: object) -> str:
    """经典界面的口径：不是三者之一一律回落 `auto`。"""
    text = str(value or "").strip().lower()
    return text if text in MODE_VALUES else "auto"


# ── 心跳间隔（经典界面靠它判断连接存活）──────────────────────
HEARTBEAT_SECONDS_DEFAULT: Final = 15.0
