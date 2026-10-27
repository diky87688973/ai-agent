# -*- coding: utf-8 -*-
"""工具调用与工具结果事实。"""
from __future__ import annotations

from typing import Any, Dict, List

from agent.core.event_name import (
    INPUT_CLAIMED,
    MODEL_MESSAGE,
    TOOL_ENDED,
    TOOL_PROGRESS,
    TOOL_SUSPENDED,
)
from agent.core.ports import Ports
from agent.core.session_log import SessionLog
from agent.core.tool_call import ToolCallRequest

_TOOL_ENDED = TOOL_ENDED

def tail_expects_model(log: SessionLog) -> bool:
    """上下文末端是否在等模型说话。

    倒着扫事实，先撞到这两个之一就是要跑模型：
      - `input_claimed`：新用户发言；
      - `tool_result`：工具结果回来了，模型得看。
    撞到 `model_message` 说明模型已经答过、且其后没有新东西 → 不用跑。

    只看末端即可判定：一回合里模型与工具交替推进，每次推进都会把新事实追加到
    末端，所以不需要额外的记账。
    """
    for event in reversed(list(getattr(log, "events", ()))):
        kind = str(getattr(event, "type", "") or "")
        if kind in (INPUT_CLAIMED, _TOOL_ENDED):
            return True
        if kind == MODEL_MESSAGE:
            return False
    return False


def pending_tool_calls(log: SessionLog) -> List[ToolCallRequest]:
    """最新一条模型消息要求、但还没有任何结果的调用（保持原顺序）。

    判据只看事实：模型消息里要求了，且没有对应的 `tool_result`。
    已被挂起的调用不再重复执行——它等的是外部输入，不是再来一次。
    """
    events = list(getattr(log, "events", ()))
    newest: List[Dict[str, Any]] = []
    for event in reversed(events):
        if str(getattr(event, "type", "")) == MODEL_MESSAGE:
            newest = list((event.data or {}).get("tool_calls") or [])
            break
    if not newest:
        return []
    done = {str((e.data or {}).get("call_id") or "")
            for e in events if str(getattr(e, "type", "")) == _TOOL_ENDED}
    suspended = {str((e.data or {}).get("call_id") or "")
                 for e in events if str(getattr(e, "type", "")) == TOOL_SUSPENDED}
    out: List[ToolCallRequest] = []
    for raw in newest:
        call_id = str(raw.get("id") or "")
        if not call_id or call_id in done or call_id in suspended:
            continue
        args = raw.get("arguments")
        out.append(ToolCallRequest(
            call_id=call_id,
            name=str(raw.get("name") or ""),
            arguments=dict(args) if isinstance(args, dict) else {},
        ))
    return out


def serialize_call(call: ToolCallRequest) -> Dict[str, Any]:
    """工具调用 → 事实里的形状（保证历史事实可混装）。"""
    return {"id": call.call_id, "name": call.name, "arguments": dict(call.arguments)}

def safe_value(value: Any) -> Any:
    """落事实前把不可序列化的东西换成可读文本（事实必须能写进 JSONL）。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): safe_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_value(v) for v in value]
    return str(value)


#: 一条工具结果进上下文的字符上限。超过就只保留头部并标注截断 ——
#: 结果本身仍然完整落事实（`data/sessions/*.raw`），模型要看全文可以再调工具读区间。
#: 没有这道闸时，一次 `read_file`（默认 20 万字符）就能让这一回合的请求体翻倍，
#: 而且它此后永久留在上下文里（事实 append-only，只有压缩才动）。
TOOL_RESULT_MAX_CHARS = 40000

def clip_tool_result(value: Any, limit: int = TOOL_RESULT_MAX_CHARS) -> Any:
    """把过长的工具结果裁到上限（递归处理 dict/list 里的长字符串）。

    dict 里最长的那个字符串是正文（`stdout` / `content` / `text`），裁它即可；
    裁过的字段留下显式标记，模型据此知道"还有更多，要看就再读"。
    """
    if isinstance(value, str):
        if len(value) <= limit:
            return value
        return value[:limit] + f"\n…（结果已截断，原文 {len(value)} 字符）"
    if isinstance(value, dict):
        out: Dict[str, Any] = {str(k): clip_tool_result(v, limit) for k, v in value.items()}
        if out != value:
            out.setdefault("_truncated", True)
        return out
    if isinstance(value, list):
        return [clip_tool_result(v, limit) for v in value]
    return value

def progress_emitter(ports: Ports):
    """把工具的进度上报转成 `tool_progress` 事实（进度是副作用，不是内核特办）。"""
    def _report(call_id: str, name: str, payload: Dict[str, Any]) -> None:
        event_payload: Dict[str, Any] = {
            "call_id": str(call_id),
            "name": str(name),
            "stream": str(payload.get("stream") or "stdout"),
            "text": str(payload.get("text") or ""),
            "done": bool(payload.get("done")),
        }
        # 交互式命令在问人时，把提示一并带出去：UI 靠它弹输入条，
        # 人答完经 `/api/chat/command-input` 回到命令的 stdin。
        awaiting = payload.get("awaiting_input")
        if isinstance(awaiting, dict) and awaiting:
            event_payload["awaiting_input"] = awaiting
        ports.emit(TOOL_PROGRESS, **event_payload)

    return _report
