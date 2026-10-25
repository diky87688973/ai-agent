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


def history_items(events: List[Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """内核事件 → `(经典界面的 items, 本次解析出的附件)`。

    回显条目：
      - `input_claimed.content` → `{role:"user", content[, attachments][, had_images]}`；
      - `model_message.reasoning_content` 非空 → `{role:"think", content[, elapsed_ms]}`，
        排在同条助手正文之前。用时优先取最近一次 `llm_ended.reasoning_ms`，
        没有该字段时回退 `elapsed_ms`；
      - `model_message.content` 非空 → `{role:"assistant", content}`。
        （工具调用轮的 `model_message` 正文为空，跳过——否则会渲染空气泡。）

    助手正文优先用 `model_message.content`（该轮定稿），不用 `assistant_delta`
    拼接：增量在历史里可能不完整（例如被中断），定稿更可信。

    附件的 id 与实时路径同源（`remember_attachments` 用同一函数算），
    否则刷新前后的 `<img src>` 指向不同 id，浏览器不会重试那张失败的图。
    实时路径按请求里的 `images[index]` 编号，而一个回合只发一次输入，
    所以那里的 index 就是事实序号 —— 两边自然对齐。
    """
    items: List[Dict[str, Any]] = []
    resolved: List[Dict[str, Any]] = []
    think_ms: Optional[int] = None
    think_reasoning_ms: Optional[int] = None
    for ev in events:
        kind = str(getattr(ev, "type", ""))
        data = dict(getattr(ev, "data", None) or {})
        if kind == "input_claimed":
            text, inline = _split_user_content(data.get("content"))
            # 附件的真实位置是 `data["attachments"]`（`InputModule` 在这里放
            # `[{mime, data_base64}]`（由 `core/modules/` 的 `InputModule` 写入）。
            # `content` 里的多模态数组只是历史/派生形态，作为兜底一并认。
            attachments = inline
            raw_atts = data.get("attachments")
            if isinstance(raw_atts, list) and raw_atts:
                attachments = [a for a in raw_atts if isinstance(a, dict)]
            if not text and not attachments:
                continue
            item: Dict[str, Any] = {"role": "user", "content": text}
            # 对等消息（别的会话投进来的）：带上发送者，刷新后走"对等气泡"，
            # 而不是被渲染成用户自己说的话。
            peer_sender = str(data.get("_sender") or "").strip()
            if peer_sender:
                item["_sender"] = peer_sender
                item["_sender_name"] = str(data.get("_sender_name") or peer_sender)
            for key in ("kind", "source", "notice_id", "batch"):
                if data.get(key):
                    item[key] = data[key]
            if attachments:
                pub: List[Dict[str, Any]] = []
                for index, att in enumerate(attachments):
                    raw = str(att.get("data_base64") or "")
                    ident = attachment_id(raw, index)
                    mime = str(att.get("mime") or "image/png")
                    name = f"image{index}.png"
                    pub.append({"id": ident, "name": name, "mime": mime})
                    resolved.append({"id": ident, "name": name, "mime": mime,
                                     "data_base64": raw})
                item["attachments"] = pub
                item["had_images"] = True
            items.append(item)
        elif kind == "llm_ended":
            raw_ms = data.get("elapsed_ms")
            try:
                think_ms = int(raw_ms) if raw_ms is not None else None
            except (TypeError, ValueError):
                think_ms = None
            raw_reasoning_ms = data.get("reasoning_ms")
            try:
                think_reasoning_ms = (int(raw_reasoning_ms)
                                      if raw_reasoning_ms is not None else None)
            except (TypeError, ValueError):
                think_reasoning_ms = None
        elif kind == "model_message":
            reasoning = str(data.get("reasoning_content") or "")
            if reasoning.strip():
                think_item: Dict[str, Any] = {"role": "think", "content": reasoning}
                elapsed = (think_reasoning_ms
                           if think_reasoning_ms is not None and think_reasoning_ms >= 0
                           else think_ms)
                if elapsed is not None and elapsed >= 0:
                    think_item["elapsed_ms"] = elapsed
                items.append(think_item)
            think_ms = None
            think_reasoning_ms = None
            content = str(data.get("content") or "")
            if content.strip():
                items.append({"role": "assistant", "content": content})
        elif kind == "tool_started":
            # 工具卡片也要能被刷新回显：经典界面的 `renderHistoryItems` 只认
            # user/assistant 两类，工具卡在刷新后整片消失（命令卡尤其明显 ——
            # 它是长跑任务，用户最需要回头看）。这里把工具生命周期补成条目。
            call_id = str(data.get("call_id") or "")
            if call_id:
                items.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "script": C.tool_script(str(data.get("name") or "")),
                    "args": (dict(data.get("arguments"))
                             if isinstance(data.get("arguments"), dict) else {}),
                    "status": "running",
                })
        elif kind in ("tool_done", "tool_failed", "tool_canceled", "tool_suspended",
                      "tool_ended"):
            call_id = str(data.get("call_id") or "")
            if not call_id:
                continue
            for item in reversed(items):
                if item.get("role") == "tool" and item.get("tool_call_id") == call_id:
                    if kind == "tool_done":
                        item["status"] = "done"
                    elif kind == "tool_failed":
                        item["status"] = "failed"
                        item["error"] = str(data.get("error") or data.get("detail") or "")
                    elif kind == "tool_canceled":
                        # 停止单独成终态：刷新后标题用银色，不和失败的红色混在一起。
                        # 留在 running 的话，这张卡会一直显示进行中。
                        item["status"] = "canceled"
                        item["error"] = str(data.get("error") or "已停止")
                    elif kind == "tool_suspended":
                        # 工具声明"要等人在界面作答" → 卡片状态置 suspended。
                        item["status"] = "suspended"
                        envelope = data.get("envelope")
                        if envelope is not None:
                            item["envelope"] = envelope
                    # `preview` 与实时帧同一形状（与模型信封同形的 JSON 串）：
                    # 成功 `{"ok":true,"data":…}` / 失败 `{"ok":false,"error":…}`。
                    # 编辑类工具的 `diffText` / `diff_text` 在 `data` 里，前端靠它重画 diff。
                    # 不补这一项，刷新后 diff 预览整片消失（实时看得见、回显看不见）。
                    result = data.get("result")
                    if result is None:
                        result = data.get("data")
                    if result is not None:
                        try:
                            if isinstance(result, dict) and "ok" in result and (
                                    "data" in result or "error" in result):
                                payload = result
                            else:
                                payload = {"ok": True, "data": result}
                            item["preview"] = json.dumps(
                                payload, ensure_ascii=False, default=str)
                        except (TypeError, ValueError) as exc:
                            report_error("agent.shell.classic_adapter.history.history_items", exc)
                    elif kind == "tool_failed" and item.get("error"):
                        # 门控拒绝等失败常只有 error、没有 data；也落成同形状 preview，
                        # 刷新后工具壳响应区才能画出 JSON，而不是空对象。
                        try:
                            item["preview"] = json.dumps(
                                {"ok": False, "error": str(item.get("error") or "")},
                                ensure_ascii=False,
                            )
                        except (TypeError, ValueError) as exc:
                            report_error("agent.shell.classic_adapter.history.history_items", exc)
                    images = C.public_tool_images(data.get("attachments"))
                    if images:
                        item["images"] = images
                    break
        elif kind == "tool_progress":
            # 流式输出（命令卡的正文）：历史里要把它拼回卡片，否则刷新后
            # 只剩一个空壳。只累积文本，不重复上报。
            call_id = str(data.get("call_id") or "")
            text = str(data.get("text") or "")
            if call_id and text:
                for item in reversed(items):
                    if item.get("role") == "tool" and item.get("tool_call_id") == call_id:
                        item["output"] = str(item.get("output") or "") + text
                        break
    return items, resolved


def last_payload(events: List[Any], kind: str) -> Optional[Dict[str, Any]]:
    """取最后一帧某类事件的载荷（`context_layout` 用——刷新后底部条要能立刻显示）。"""
    found: Optional[Dict[str, Any]] = None
    for ev in events:
        if str(getattr(ev, "type", "")) == kind:
            found = dict(getattr(ev, "data", None) or {})
    return found
