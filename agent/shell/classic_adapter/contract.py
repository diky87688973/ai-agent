# -*- coding: utf-8 -*-
"""经典界面契约常量（适配层的单一事实源）。

适配层两端的字段名必须完全对齐，而这些名字散布在
163 KB 的老 `agent-ui.js` 里。把"谁读什么字段"集中到这里，任何一处对不上都能在
一处改，也能被契约测试逐条钉住。

经典界面的三条硬约束：
  1. 每帧必须带合法 `conversation_id`（`/^[A-Za-z0-9_-]{8,128}$/`），否则经典界面
     整包静默丢弃（agent-ui.js:100）；`heartbeat` / `global_sse_ready` /
     `plugins_changed` / `settings_changed` / `plugin_config_changed` 豁免。
  2. `tool_call_id` 是 tool_start / tool_end 的唯一配对键，为空或对不上 → `tool_end`
     被整个忽略（agent-ui.js:2013），卡片永远停在"进行中"。
  3. `reasoning_delta` 前置 `llm_round`，且 `round` 相等，否则丢弃（agent-ui.js:1674）。
"""
from __future__ import annotations

import re
from typing import Any, Dict, Final, List, Optional

# ── 会话 ID（经典界面的校验口径，agent-ui.js:8）────────────────
CID_PATTERN: Final = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


def normalize_cid(value: object) -> str:
    """按经典界面的 `normalizeConversationId` 归一化：不合法返回空串。"""
    text = str(value or "").strip()
    return text if CID_PATTERN.match(text) else ""


def safe_count(value: object) -> int:
    """事件计数转非负整数；缺失或坏值按 0。"""
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


# ── 事件名（服务端 → 前端）──────────────────────────────────
# 经典界面读的事件名；`plugin_event` 由 `stream.js` 转发给插件。
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
EV_CONTEXT_COMPACTED: Final = "context_compacted"
EV_CONTEXT_LAYOUT: Final = "context_layout"
EV_CONTEXT_SEGMENTS: Final = "context_segments"
EV_MODE_CHANGED: Final = "mode_changed"
EV_DISPATCH_TITLE: Final = "dispatch_title"
EV_DONE: Final = "done"
EV_ERROR: Final = "error"
EV_STOPPED: Final = "stopped"
EV_QUEUE_UPDATED: Final = "queue_updated"
EV_PEER_MESSAGE: Final = "peer_message"
EV_QUEUED_USER: Final = "queued_user"
EV_OPEN_SESSION: Final = "open_session"
EV_PAUSED_FOR_CONFIRM: Final = "paused_for_user_confirm"
EV_HEARTBEAT: Final = "heartbeat"
EV_GLOBAL_SSE_READY: Final = "global_sse_ready"
EV_PLUGINS_CHANGED: Final = "plugins_changed"
EV_PLUGIN_EVENT: Final = "plugin_event"
EV_SETTINGS_CHANGED: Final = "settings_changed"
EV_PLUGIN_CONFIG_CHANGED: Final = "plugin_config_changed"

#: 经典界面豁免 `conversation_id` 校验的事件。
#: `plugins_changed` / `settings_changed` / `plugin_config_changed` 是进程级的：
#: 插件开关与设置保存不属于某一个会话。
CID_EXEMPT_EVENTS: Final = frozenset({
    EV_HEARTBEAT, EV_GLOBAL_SSE_READY, EV_PLUGINS_CHANGED,
    EV_SETTINGS_CHANGED, EV_PLUGIN_CONFIG_CHANGED,
})

#: 插件事件帧的保留键；`seq` 是 SSE 续传游标，插件载荷不能占用。
_PLUGIN_EVENT_RESERVED: Final = frozenset({"type", "plugin", "event", "seq"})
_PLUGIN_NAME_RE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_PLUGIN_EVENT_RE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def plugin_event_frame(plugin: str, event: str,
                       payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """构造一条插件事件帧；不落盘，不参与断线续传。

    插件名与事件名只允许稳定标识符；`payload` 不能覆盖帧头，也不能带 `seq`。
    """
    name = str(plugin or "").strip()
    kind = str(event or "").strip()
    if not _PLUGIN_NAME_RE.match(name):
        raise ValueError(f"插件名非法：{plugin!r}")
    if not _PLUGIN_EVENT_RE.match(kind):
        raise ValueError(f"插件事件名非法：{event!r}")
    if payload is None:
        body: Dict[str, Any] = {}
    elif isinstance(payload, dict):
        body = dict(payload)
    else:
        raise ValueError("插件事件 payload 必须是 dict 或 None")
    reserved = _PLUGIN_EVENT_RESERVED.intersection(body)
    if reserved:
        raise ValueError(f"插件事件 payload 含保留键：{sorted(reserved)}")
    frame: Dict[str, Any] = {"type": EV_PLUGIN_EVENT, "plugin": name, "event": kind}
    frame.update(body)
    return frame


# ── 工具名映射：内核工具 → 经典界面的 `script` 标识 ─────────────
# 经典界面靠 `script` 决定图标（toolIco agent-ui.js:1179）、中文名（buildToolTitleParts
# agent-ui.js:1263）与是否"实时输出"。名字必须落在它认识的集合里，否则标题会退化。
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


# ── usage 字段名（两套，不可复用）────────────────────────
# SSE 的 `usage` 事件（agent-ui.js:156）与 `/api/usage-accumulator`（agent-ui.js:1176）
# 用完全不同的字段名，混用会导致其中一边永远为 0。
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
EP_USAGE_ACC: Final = "/api/usage-accumulator"
EP_HEALTH: Final = "/health"


# ── 模式取值（经典界面的 normalizeMode，agent-ui.js:372）───────
MODE_VALUES: Final = ("auto", "plan", "execute")


def normalize_mode(value: object) -> str:
    """经典界面的口径：不是三者之一一律回落 `auto`。"""
    text = str(value or "").strip().lower()
    return text if text in MODE_VALUES else "auto"


def public_tool_images(raw: Any) -> List[dict]:
    """工具结果上的图片附件，给经典界面直接显示。

    只留 `mime` 与 `data_base64`。缺字节、或 mime 不是 image/* 的条目丢掉。
    """
    if not isinstance(raw, list):
        return []
    out: List[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        data = str(item.get("data_base64") or "")
        if not data:
            continue
        mime = str(item.get("mime") or "image/png")
        if not mime.startswith("image/"):
            continue
        out.append({"mime": mime, "data_base64": data})
    return out


# ── 心跳间隔（经典界面靠它判断连接存活）──────────────────────
HEARTBEAT_SECONDS_DEFAULT: Final = 15.0
