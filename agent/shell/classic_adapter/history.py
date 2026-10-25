# -*- coding: utf-8 -*-
"""经典 UI 历史事件折叠。"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional, Tuple

import agent.shell.classic_adapter.contract as C
from agent.core.error_report import report_error

ATTACH_REGISTER_MAX_BYTES = 2 * 1024 * 1024
ATTACH_REGISTER_MAX_COUNT = 24

def attachment_id(data_base64: Any, index: int) -> str:
    """附件的稳定 id —— 从图片字节派生，两端都能算出同一个。

    不能用"事实序号 + 下标"：那个序号是文件行数，而发出请求的那一刻
    与刷新时读到的行数不同（发图时那一行还没落盘），同一个附件会算出两个 id，
    `<img src>` 因此指向不存在的 id（`/api/chat/attachment` 返回 404）。

    用字节的摘要就没有这个时间依赖：请求里的 `data_base64` 与事实里存下的
    逐字节相同，所以两边算出的 id 必然一致。
    """
    digest = hashlib.sha1(str(data_base64 or "").encode("utf-8")).hexdigest()[:12]
    return f"att-{digest}-{int(index)}"


def _split_user_content(content: Any) -> Tuple[str, List[Dict[str, Any]]]:
    """用户消息 content → `(正文, 内联附件列表)`。

    兼容两种形态（历史记录里都出现过）：

    1. `str` —— 当前事实的形态（附件在 `data["attachments"]` 里）；
    2. 多模态数组 —— `[{type:text}, {type:image_url, ...}]`，
       由 `core/session_log._user_content` 为模型请求派生；这种形态也可能
       直接以它落盘，所以这里一并认。

    图片字节就在事实里，所以回显不需要另找来源 —— 事实是唯一事实源。
    """
    if not isinstance(content, list):
        return (str(content or ""), [])
    text_parts: List[str] = []
    attachments: List[Dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        kind = str(part.get("type") or "")
        if kind == "text":
            text_parts.append(str(part.get("text") or ""))
        elif kind == "image_url":
            url = part.get("image_url")
            url = str(url.get("url") if isinstance(url, dict) else url or "")
            if not url.startswith("data:") or ";base64," not in url:
                continue
            head, _, data = url.partition(";base64,")
            mime = head[len("data:"):].strip() or "image/png"
            if data:
                attachments.append({"mime": mime, "data_base64": data})
    return ("".join(text_parts), attachments)


def _user_item(data: Dict[str, Any], resolved: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    text, inline = _split_user_content(data.get("content"))
    attachments = inline
    raw = data.get("attachments")
    if isinstance(raw, list) and raw:
        attachments = [a for a in raw if isinstance(a, dict)]
    if not text and not attachments:
        return None
    item: Dict[str, Any] = {"role": "user", "content": text}
    sender = str(data.get("_sender") or "").strip()
    if sender:
        item["_sender"] = sender
        item["_sender_name"] = str(data.get("_sender_name") or sender)
    for key in ("kind", "source", "notice_id", "batch"):
        if data.get(key):
            item[key] = data[key]
    if attachments:
        pub: List[Dict[str, Any]] = []
        for index, att in enumerate(attachments):
            raw_data = str(att.get("data_base64") or "")
            ident = attachment_id(raw_data, index)
            mime = str(att.get("mime") or "image/png")
            name = f"image{index}.png"
            pub.append({"id": ident, "name": name, "mime": mime})
            resolved.append({"id": ident, "name": name, "mime": mime,
                             "data_base64": raw_data})
        item["attachments"] = pub
        item["had_images"] = True
    return item


def _model_items(data: Dict[str, Any], elapsed: Optional[int],
                 reasoning_elapsed: Optional[int]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    reasoning = str(data.get("reasoning_content") or "")
    if reasoning.strip():
        think: Dict[str, Any] = {"role": "think", "content": reasoning}
        value = (reasoning_elapsed
                 if reasoning_elapsed is not None and reasoning_elapsed >= 0
                 else elapsed)
        if value is not None and value >= 0:
            think["elapsed_ms"] = value
        out.append(think)
    content = str(data.get("content") or "")
    if content.strip():
        out.append({"role": "assistant", "content": content})
    return out


def _tool_started_item(data: Dict[str, Any]) -> Dict[str, Any] | None:
    call_id = str(data.get("call_id") or "")
    if not call_id:
        return None
    return {
        "role": "tool", "tool_call_id": call_id,
        "script": C.tool_script(str(data.get("name") or "")),
        "args": (dict(data.get("arguments"))
                 if isinstance(data.get("arguments"), dict) else {}),
        "status": "running",
    }


def _tool_preview(item: Dict[str, Any], kind: str, data: Dict[str, Any]) -> None:
    result = data.get("result")
    if result is None:
        result = data.get("data")
    if result is not None:
        try:
            payload = (result if isinstance(result, dict) and "ok" in result
                       and ("data" in result or "error" in result)
                       else {"ok": True, "data": result})
            item["preview"] = json.dumps(payload, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as exc:
            report_error("agent.shell.classic_adapter.history.history_items", exc)
    elif kind == "tool_failed" and item.get("error"):
        try:
            item["preview"] = json.dumps(
                {"ok": False, "error": str(item.get("error") or "")},
                ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            report_error("agent.shell.classic_adapter.history.history_items", exc)
    images = C.public_tool_images(data.get("attachments"))
    if images:
        item["images"] = images


def _apply_tool_event(items: List[Dict[str, Any]], kind: str,
                      data: Dict[str, Any]) -> None:
    call_id = str(data.get("call_id") or "")
    if not call_id:
        return
    for item in reversed(items):
        if item.get("role") != "tool" or item.get("tool_call_id") != call_id:
            continue
        if kind == "tool_done":
            item["status"] = "done"
        elif kind == "tool_failed":
            item["status"] = "failed"
            item["error"] = str(data.get("error") or data.get("detail") or "")
        elif kind == "tool_canceled":
            item["status"] = "canceled"
            item["error"] = str(data.get("error") or "已停止")
        elif kind == "tool_suspended":
            item["status"] = "suspended"
            if data.get("envelope") is not None:
                item["envelope"] = data.get("envelope")
        _tool_preview(item, kind, data)
        return


def _apply_progress(items: List[Dict[str, Any]], data: Dict[str, Any]) -> None:
    call_id = str(data.get("call_id") or "")
    text = str(data.get("text") or "")
    if not call_id or not text:
        return
    for item in reversed(items):
        if item.get("role") == "tool" and item.get("tool_call_id") == call_id:
            item["output"] = str(item.get("output") or "") + text
            return


def history_items(events: List[Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """内核事件 → `(经典界面的 items, 本次解析出的附件)`。"""
    items: List[Dict[str, Any]] = []
    resolved: List[Dict[str, Any]] = []
    think_ms: Optional[int] = None
    think_reasoning_ms: Optional[int] = None
    for ev in events:
        kind = str(getattr(ev, "type", ""))
        data = dict(getattr(ev, "data", None) or {})
        if kind == "input_claimed":
            item = _user_item(data, resolved)
            if item is not None:
                items.append(item)
        elif kind == "llm_ended":
            try:
                think_ms = int(data["elapsed_ms"]) if data.get("elapsed_ms") is not None else None
            except (TypeError, ValueError):
                think_ms = None
            try:
                think_reasoning_ms = (int(data["reasoning_ms"])
                                      if data.get("reasoning_ms") is not None else None)
            except (TypeError, ValueError):
                think_reasoning_ms = None
        elif kind == "model_message":
            items.extend(_model_items(data, think_ms, think_reasoning_ms))
            think_ms = think_reasoning_ms = None
        elif kind == "tool_started":
            item = _tool_started_item(data)
            if item is not None:
                items.append(item)
        elif kind in ("tool_done", "tool_failed", "tool_canceled",
                      "tool_suspended", "tool_ended"):
            _apply_tool_event(items, kind, data)
        elif kind == "tool_progress":
            _apply_progress(items, data)
    return items, resolved

def last_payload(events: List[Any], kind: str) -> Optional[Dict[str, Any]]:
    """取最后一帧某类事件的载荷（`context_layout` 用——刷新后底部条要能立刻显示）。"""
    found: Optional[Dict[str, Any]] = None
    for ev in events:
        if str(getattr(ev, "type", "")) == kind:
            found = dict(getattr(ev, "data", None) or {})
    return found
