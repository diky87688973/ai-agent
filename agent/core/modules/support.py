# -*- coding: utf-8 -*-
"""模块共用的读规则与装配辅助（非模块间依赖）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent.core.error_report import report_error
from agent.core.event_name import (
    INPUT_CLAIMED,
    MODEL_MESSAGE,
    TOOL_ENDED,
    TOOL_PROGRESS,
    TOOL_SUSPENDED,
)
from agent.core.image_embed import strip_old_images
from agent.core.mode_marker import MODE_MARKER
from agent.core.ports import Ports
from agent.core.session_log import SessionLog
from agent.core.tool_call import ToolCallRequest

_TOOL_ENDED = TOOL_ENDED

def _prepare_dialogue(dialogue: Any, image_turns: int,
                      image_max: int) -> List[Dict[str, Any]]:
    """对话 → 请求用对话：按配置剥掉窗口外的图。

    默认保留最近 1 轮最多 8 张：截图工具每步一张大图，历史全带会先撞上游
    请求体上限。把两个上限都设成负数可关闭剥离，但请求体会随会话增长。

    压缩请求与模型请求走同一函数：压缩器声明前缀与随后请求逐字节相同，
    该声明只在两边用同一套剥图参数时成立。
    """
    prepared, _stripped = strip_old_images(dialogue, keep_turns=image_turns,
                                           max_images=image_max)
    return prepared


_RUNTIME_NOTE_PREFIXES = ("## 当前模式", "## Todo-List")


def _strip_runtime_note(messages: Any) -> List[Dict[str, Any]]:
    """去掉末尾遗留的临时运行态消息，避免重复拼接。"""
    out = list(messages or [])
    while out:
        last = out[-1]
        if not isinstance(last, dict) or str(last.get("role") or "") != "system":
            break
        content = str(last.get("content") or "")
        if not content.startswith(_RUNTIME_NOTE_PREFIXES):
            break
        out.pop()
    return out


def _resolve_runtime_note(value: Any) -> str:
    """把字符串或每次求值的回调解析成当前运行态文本。"""
    if callable(value):
        try:
            return str(value() or "").strip()
        except Exception as exc:
            report_error("core.runtime_note", exc)
            return ""
    return str(value or "").strip()


def _with_mode_note(messages: Any, mode_note: str) -> List[Dict[str, Any]]:
    """把执行模式说明附加到请求消息的最末尾（不动原列表、不动事实流）。

    模式说明是宿主附加的指令，不是用户发言 —— 用 `role=system`。
    非用户发起的请求一律走 system：用户消息的位置只放用户真正发的东西。

    追加一条独立消息而不是拼进最后一条的正文：最后一条可能是多模态数组
    或工具结果，拼接会改坏它的结构；独立成条也保证"改动只落在尾部"这件事一眼可见。
    """
    base = _strip_runtime_note(messages)
    note = str(mode_note or "").strip()
    if not note:
        return base
    if base and str(base[-1].get("content") or "") == note:
        return base
    return base + [{"role": "system", "content": note}]


def _assemble_with(context: Any, dialogue: Any, mode_note: str,
                   covered_end: int) -> Optional[List[Dict[str, Any]]]:
    """把对话装进上下文并装配出整份请求消息（头部 + 对话 + 尾部）。

    上下文缺能力（没实现 `set_dialogue` / `assembles`）时返回 None ——
    调用方据此退回"只有对话"的降级路径，而不是崩掉。
    """
    if context is None:
        return None
    if not (hasattr(context, "set_dialogue") and hasattr(context, "assembles")):
        return None
    context.set_dialogue(_strip_runtime_note(dialogue), covered_end=covered_end)
    note = str(mode_note or "").strip()
    tail = [{"role": "system", "content": note}] if note else []
    return list(context.assembles(tail))


def _segment_snapshot(context: Any, messages: Any,
                      budget_tokens: int = 0) -> Optional[Dict[str, Any]]:
    """把装配好的请求拆成分段快照（段名 + 各段估算 token）。

    口径与真正发出去的请求一致（同一份装配、同一个估算器）：
    头部各块（系统提示词 / 插件各段 / 记忆摘要）+ 对话
    + 尾部（本轮新输入 / 工具结果 / 执行模式）。

    `budget_tokens` 是各段 `pct` 的归一化基准（= 压缩阈值）。不传就只能拿"已用"
    当基准，剩余容量恒为 0 —— 界面那条永远显示 0%，所以调用方必须给。

    上下文缺分段能力（或算不出来）→ `None`，调用方不发这条事件。
    """
    if context is None or not hasattr(context, "layout_payload"):
        return None
    mode = _mode_tail(messages)
    payload = context.layout_payload(tail_messages=mode,
                                     budget_tokens=int(budget_tokens or 0))
    if not payload or not payload.get("segments"):
        return None
    return payload


def _mode_tail(messages: Any) -> List[Dict[str, Any]]:
    """请求尾部的执行模式说明（正文以 `MODE_MARKER` 开头）。

    位置不固定：用户输入轮末尾是 `[本轮新输入][执行模式]`，工具轮里是
    `[执行模式][工具结果]`。所以倒序按内容认，不按位置猜。
    """
    for m in reversed(list(messages or [])):
        if not isinstance(m, dict):
            continue
        if str(m.get("role") or "") == "system" \
                and str(m.get("content") or "").startswith(MODE_MARKER):
            return [m]
    return []


def _tail_expects_model(log: SessionLog) -> bool:
    """上下文末端是否在等模型说话。

    倒着扫事实，先撞到这两个之一就是要跑模型：
      - `input_claimed`：新用户发言；
      - `tool_result`：工具结果回来了，模型得看。
    撞到 `model_message` 说明模型已经答过、且其后没有新东西 → 不用跑。

    只看末端即可判定：一轮里模型与工具交替推进，每次推进都会把新事实追加到
    末端，所以不需要额外的记账。
    """
    for event in reversed(list(getattr(log, "events", ()))):
        kind = str(getattr(event, "type", "") or "")
        if kind in (INPUT_CLAIMED, _TOOL_ENDED):
            return True
        if kind == MODEL_MESSAGE:
            return False
    return False


def _pending_tool_calls(log: SessionLog) -> List[ToolCallRequest]:
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


def _serialize_call(call: ToolCallRequest) -> Dict[str, Any]:
    """工具调用 → 事实里的形状（保证历史事实可混装）。"""
    return {"id": call.call_id, "name": call.name, "arguments": dict(call.arguments)}


def _safe(value: Any) -> Any:
    """落事实前把不可序列化的东西换成可读文本（事实必须能写进 JSONL）。"""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    return str(value)


#: 一条工具结果进上下文的字符上限。超过就只保留头部并标注截断 ——
#: 结果本身仍然完整落事实（`data/sessions/*.raw`），模型要看全文可以再调工具读区间。
#: 没有这道闸时，一次 `read_file`（默认 20 万字符）就能让这一轮的请求体翻倍，
#: 而且它此后永久留在上下文里（事实 append-only，只有压缩才动）。
TOOL_RESULT_MAX_CHARS = 40000


def _clip_tool_result(value: Any, limit: int = TOOL_RESULT_MAX_CHARS) -> Any:
    """把过长的工具结果裁到上限（递归处理 dict/list 里的长字符串）。

    dict 里最长的那个字符串是正文（`stdout` / `content` / `text`），裁它即可；
    裁过的字段留下显式标记，模型据此知道"还有更多，要看就再读"。
    """
    if isinstance(value, str):
        if len(value) <= limit:
            return value
        return value[:limit] + f"\n…（结果已截断，原文 {len(value)} 字符）"
    if isinstance(value, dict):
        out: Dict[str, Any] = {str(k): _clip_tool_result(v, limit) for k, v in value.items()}
        if out != value:
            out.setdefault("_truncated", True)
        return out
    if isinstance(value, list):
        return [_clip_tool_result(v, limit) for v in value]
    return value


def _progress_emitter(ports: Ports):
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
