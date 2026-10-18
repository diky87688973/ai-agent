# -*- coding: utf-8 -*-
"""入站适配：经典 UI 的请求 → 内核调用 → 经典 UI 期望的返回体（前端 → 服务端）。

这里只做**形状翻译**，不实现业务：
业务一律落到内核既有面（`app.runner` / `app.store` / `app.live_state` / …）。

三个不对称（任一踩中都是静默失效）：
  1. `/api/chat/history` **必须返回 `ok:true`**，否则经典界面直接 return、整段历史不渲染
     （agent-ui.js:339）；而 `/api/chat/sessions` **完全不看** `ok`（agent-ui.js:309）。
  2. 用量字段名有两套：contract.SSE_USAGE_FIELDS（SSE）与 ACCUMULATOR_USAGE_FIELDS（累计接口），互不通用。
  3. `ui-state` 的 PUT 直接收布局对象、GET 返 `{state:{...}}`（不是平铺）。
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import agent.shell.classic_adapter.contract as C
from agent.mechanisms.session_store import KEY_DATA, KEY_TYPE
from agent.shell.classic_adapter.contract import EV_CONTEXT_SEGMENTS
from agent.shell.timefmt import date_group


def _scan_title(path: Path) -> str:
    """回落实现：从 .raw 前若干行找首条用户输入派生标题。

    只读文件前 400 行——一个会话可能有上万条事件，为标题读全文件不值得。
    行的键名取自 store 的 `KEY_TYPE` / `KEY_DATA`：硬编码字符串会随键名改动静默失配，
    硬编码字符串就会静默失配，标题悄悄退化成空。
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for _ in range(400):
                line = handle.readline()
                if not line:
                    break
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                if payload.get(KEY_TYPE) != "input_claimed":
                    continue
                data = payload.get(KEY_DATA) if isinstance(payload.get(KEY_DATA), dict) else payload
                content = str(data.get("content") or "").strip()
                if content:
                    return " ".join(content.split())[:40]
    except OSError:
        pass
    return ""


#: 单张图超过它就**不登记字节**（只置 `had_images` 给"预览已失效"提示），
#: 免得一次刷新把几十 MB 拉进内存。前端仍会显示提示条，不会静默消失。
_ATTACH_REGISTER_MAX_BYTES = 2 * 1024 * 1024
#: 每次 history 最多登记多少张（只影响"这次刷新能不能立刻看图"，不影响提示）
_ATTACH_REGISTER_MAX_COUNT = 24


def _attachment_id(data_base64: Any, index: int) -> str:
    """附件的稳定 id —— **从图片字节派生**，两端都能算出同一个。

    不能用"事实序号 + 下标"：那个序号是**文件行数**，而发出请求的那一刻
    与刷新时读到的行数不同（发图时那一行还没落盘），同一个附件会算出两个 id，
    `<img src>` 因此指向不存在的 id（`/api/chat/attachment` 返回 404）。

    用字节的摘要就没有这个时间依赖：请求里的 `data_base64` 与事实里存下的
    逐字节相同，所以两边算出的 id 必然一致。
    """
    digest = hashlib.sha1(str(data_base64 or "").encode("utf-8")).hexdigest()[:12]
    return f"att-{digest}-{int(index)}"


def _split_user_content(content: Any) -> Tuple[str, List[Dict[str, Any]]]:
    """用户消息 content → `(正文, 内联附件列表)`。

    兼容**两种形态**（历史记录里都出现过）：

    1. `str` —— 当前事实的形态（附件在 `data["attachments"]` 里）；
    2. 多模态数组 —— `[{type:text}, {type:image_url, ...}]`，
       由 `core/session_log._user_content` 为**模型请求**派生；这种形态也可能
       直接以它落盘，所以这里一并认。

    图片字节**就在事实里**，所以回显不需要另找来源 —— 事实是唯一事实源。
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


def _history_items(events: List[Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """内核事件 → `(经典界面的 items, 本次解析出的附件)`。

    回显条目：
      - `input_claimed.content` → `{role:"user", content[, attachments][, had_images]}`；
      - `model_message.reasoning_content` **非空** → `{role:"think", content[, elapsed_ms]}`，
        排在同条助手正文之前。用时取这条消息之前最近一次 `llm_ended.elapsed_ms`；
      - `model_message.content` **非空** → `{role:"assistant", content}`。
        （工具调用轮的 `model_message` 正文为空，跳过——否则会渲染空气泡。）

    助手正文优先用 `model_message.content`（该轮定稿），不用 `assistant_delta`
    拼接：增量在历史里可能不完整（例如被中断），定稿更可信。

    **附件的 id 与实时路径同源**（`remember_attachments` 用同一函数算），
    否则刷新前后的 `<img src>` 指向不同 id，浏览器不会重试那张失败的图。
    实时路径按请求里的 `images[index]` 编号，而一个回合只发一次输入，
    所以那里的 index 就是事实序号 —— 两边自然对齐。
    """
    items: List[Dict[str, Any]] = []
    resolved: List[Dict[str, Any]] = []
    think_ms: Optional[int] = None
    for ev in events:
        kind = str(getattr(ev, "type", ""))
        data = dict(getattr(ev, "data", None) or {})
        if kind == "input_claimed":
            text, inline = _split_user_content(data.get("content"))
            # 附件的**真实位置**是 `data["attachments"]`（`InputModule` 在这里放
            # `[{mime, data_base64}]`（由 `core/modules.py` 的 `InputModule` 写入）。
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
            if attachments:
                pub: List[Dict[str, Any]] = []
                for index, att in enumerate(attachments):
                    raw = str(att.get("data_base64") or "")
                    ident = _attachment_id(raw, index)
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
        elif kind == "model_message":
            reasoning = str(data.get("reasoning_content") or "")
            if reasoning.strip():
                think_item: Dict[str, Any] = {"role": "think", "content": reasoning}
                if think_ms is not None and think_ms >= 0:
                    think_item["elapsed_ms"] = think_ms
                items.append(think_item)
            think_ms = None
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
                    # `preview` 与实时帧**同一形状**（与模型信封同形的 JSON 串）：
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
                        except (TypeError, ValueError):
                            pass
                    elif kind == "tool_failed" and item.get("error"):
                        # 门控拒绝等失败常只有 error、没有 data；也落成同形状 preview，
                        # 刷新后工具壳响应区才能画出 JSON，而不是空对象。
                        try:
                            item["preview"] = json.dumps(
                                {"ok": False, "error": str(item.get("error") or "")},
                                ensure_ascii=False,
                            )
                        except (TypeError, ValueError):
                            pass
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


def _last_payload(events: List[Any], kind: str) -> Optional[Dict[str, Any]]:
    """取最后一帧某类事件的载荷（`context_layout` 用——刷新后底部条要能立刻显示）。"""
    found: Optional[Dict[str, Any]] = None
    for ev in events:
        if str(getattr(ev, "type", "")) == kind:
            found = dict(getattr(ev, "data", None) or {})
    return found


#: 上下文布局的小缓存：`{cid: ((事实条数, 注入源版本), 布局)}`。
#
# 本函数在**每一步**都会被调（实时帧一路），每次都做
# 一次全量 `store.load` + 折叠，一轮几十步就是几百毫秒的纯浪费
# （同一步内事实没变，算出来必然一样）。
#
# 缓存键是事实条数加上注入源版本。事实只追加、不修改。
# 勾选文件和插件开关不追加事实，但会抬高注入源版本，插件段得重算。
# 有界（只留最近 32 个会话），不会随会话数无限增长。
_LAYOUT_CACHE: "OrderedDict[str, tuple]" = OrderedDict()
_LAYOUT_CACHE_MAX = 32


def compute_context_layout(app: Any, events: List[Any], cid: str) -> Optional[Dict[str, Any]]:
    """上下文分段快照（实时与刷新两条路径共用同一口径）。

    对话、系统提示词、模式用内核最后一条 `context_segments`
    （模式说明与工具轮的内部 system 注入不落记录，只有那份快照里有）。
    插件段按当前注入源重算：勾选和插件开关发生在两次请求之间，
    快照里的插件段对不上此刻会注入的内容。

    内核这条事件还没发出来时，退回按当前注入源重装的兜底。
    算不出来返回 `None`，调用方不发/不填。
    """
    if not events:
        return None
    stamp = (len(events), _sources_version(app))
    hit = _LAYOUT_CACHE.get(cid)
    if hit is not None and hit[0] == stamp:
        _LAYOUT_CACHE.move_to_end(cid)
        return hit[1]
    budget = _budget_of(app, cid)
    payload = _last_segments(events, budget)
    if payload is None:
        payload = _fallback_layout(app, events, cid)
    else:
        payload = _overlay_plugin_segments(app, cid, payload)
    if payload is None:
        return None
    _LAYOUT_CACHE[cid] = (stamp, payload)
    _LAYOUT_CACHE.move_to_end(cid)
    while len(_LAYOUT_CACHE) > _LAYOUT_CACHE_MAX:
        _LAYOUT_CACHE.popitem(last=False)
    return payload


def _sources_version(app: Any) -> int:
    """注入源版本。没有注册表时为 0。"""
    sources = getattr(app, "context_sources", None)
    try:
        return int(getattr(sources, "version", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _overlay_plugin_segments(app: Any, cid: str,
                             payload: Dict[str, Any]) -> Dict[str, Any]:
    """用当前注入源替换快照里的插件段，再按预算重算百分比。

    没有注入源注册表时原样返回（测试夹具与未装插件的进程走这里）。
    """
    sources = getattr(app, "context_sources", None)
    collect = getattr(sources, "collect_segments", None)
    if not callable(collect):
        return payload
    try:
        packed = collect(str(cid or ""))
    except Exception as exc:
        # 可选增强：失败不砸 SSE，但必须留痕，不得静默沿用旧快照。
        print(
            f"[inbound] 注入源 collect 失败 cid={cid}: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr, flush=True,
        )
        return payload
    from agent.mechanisms.context_tokens import default_message_tokens

    items = list(getattr(packed, "items", None) or [])
    counts = list(getattr(packed, "counts", None) or [])
    fresh: List[Dict[str, Any]] = []
    for index, item in enumerate(items):
        key, label, text = item[0], item[1], item[2]
        reported = counts[index] if index < len(counts) else 1
        fresh.append({
            "key": f"plugin:{key}",
            "label": str(label or key),
            "tokens": int(default_message_tokens(
                {"role": "system", "content": str(text or "")})),
            "count": int(reported),
        })
    tail_keys = {"summary", "full_recent", "mode"}
    head: List[Dict[str, Any]] = []
    tail: List[Dict[str, Any]] = []
    for segment in payload.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        key = str(segment.get("key") or "")
        if key == "remaining" or key.startswith("plugin:"):
            continue
        if key in tail_keys or tail:
            tail.append(segment)
        else:
            head.append(segment)
    merged = dict(payload)
    merged["segments"] = head + fresh + tail
    return _rescale(merged, _budget_of(app, cid) or int(payload.get("budget_tokens") or 0))


def _budget_of(app: Any, cid: str) -> int:
    """本次会话的上下文预算 = 压缩阈值（`[context] summary_token_threshold`）。

    取不到就给 0，调用方各自退回自己的兜底口径。
    """
    factory = getattr(app, "compactor_factory", None)
    if not callable(factory):
        return 0
    return int(getattr(factory(cid), "summary_token_threshold", 0) or 0)


def _last_segments(events: List[Any],
                   budget_tokens: int = 0) -> Optional[Dict[str, Any]]:
    """最后一条 `context_segments`（内核发的装配快照）。

    快照里的 `pct` 是**产出那一刻**按当时预算算好的，会随配置与版本漂移
    （早先的装配点没把预算传下来，快照里 `budget_tokens` 等于"已用"，
    于是界面那条「剩余容量」永远是 0%）。所以这里按**当前**预算把各段 pct 重算一遍 ——
    渲染时点一下算术，比留一条永远为 0 的段强。
    """
    for event in reversed(list(events or [])):
        if str(getattr(event, "type", "") or "") != EV_CONTEXT_SEGMENTS:
            continue
        data = getattr(event, "data", None) or {}
        if not data.get("segments"):
            continue
        return _rescale(dict(data), budget_tokens)
    return None


def _rescale(payload: Dict[str, Any], budget_tokens: int) -> Dict[str, Any]:
    """按给定预算重算各段 `pct` 与「剩余容量」。预算不可用时原样返回。"""
    segments = [s for s in (payload.get("segments") or []) if isinstance(s, dict)]
    total = sum(int(s.get("tokens") or 0) for s in segments
                if str(s.get("key") or "") != "remaining")
    budget = max(int(budget_tokens or 0), total, 1)
    rows: List[Dict[str, Any]] = []
    for s in segments:
        if str(s.get("key") or "") == "remaining":
            continue
        row = dict(s)
        row["pct"] = round(100.0 * int(row.get("tokens") or 0) / budget, 6)
        rows.append(row)
    remainder = max(0, budget - total)
    rows.append({
        "key": "remaining",
        "label": (next((str(s.get("label")) for s in segments
                        if str(s.get("key") or "") == "remaining"), "") or "剩余容量"),
        "tokens": remainder,
        "pct": round(100.0 * remainder / budget, 6),
    })
    out = dict(payload)
    out["segments"] = rows
    out["total_tokens"] = sum(int(r.get("tokens") or 0) for r in rows
                              if str(r.get("key") or "") != "remaining")
    out["budget_tokens"] = budget
    return out


def _mode_of(events: List[Any]) -> str:
    """末次请求里的执行模式（`## 当前模式：<mode>`）；取不到给 auto。

    倒序扫描：模式在请求里位置不固定（工具轮里它后面还跟着工具结果）。
    """
    msgs: List[Any] = []
    if events:
        from agent.core.session_log import SessionLog

        msgs = SessionLog(events=list(events)).derive_request_messages() or []
    marker = "## 当前模式："
    for m in reversed(msgs):
        if not isinstance(m, dict) or str(m.get("role") or "") != "system":
            continue
        text = str(m.get("content") or "")
        if text.startswith(marker):
            return text[len(marker):].splitlines()[0].strip() or "auto"
    return "auto"


def _fallback_layout(app: Any, events: List[Any], cid: str) -> Optional[Dict[str, Any]]:
    """兜底：**没有装配快照的旧会话**（快照是后加的，老记录里没有）也分层。

    Skills 清单、知识库、摘要都**不在事实记录里** —— 它们是每回合装配时注入的，
    所以只从事实折叠不出来。这里真装一次上下文（与内核同一套注入源），
    读它的头部来切段；事实只提供对话与覆盖点。
    """
    from agent.core.session_log import SessionLog
    from agent.mechanisms.context_pipeline import layout_from_messages

    messages = SessionLog(events=list(events)).derive_request_messages()
    if not messages:
        return None
    budget = 0
    compactor_factory = getattr(app, "compactor_factory", None)
    if callable(compactor_factory):
        budget = int(getattr(compactor_factory(cid), "summary_token_threshold", 0) or 0)
    from agent.shell.prompts import resolve_system_prompt

    registry = getattr(app, "registry", None)
    if registry is None:
        raise RuntimeError("上下文布局需要 app.registry：未装配工具注册表，无法生成系统提示词")
    mesh = getattr(app, "mesh", None)
    meta = mesh.get_agent(cid) if mesh is not None and hasattr(mesh, "get_agent") else {}
    system_text = resolve_system_prompt(
        mode=_mode_of(events),
        registry=registry,
        explicit=str((meta or {}).get("system") or "") or None,
    )
    if not str(system_text or "").strip():
        raise RuntimeError("系统提示词为空：装配异常，拒绝静默继续")
    # 真装一次：头部（系统提示 / Skills / 知识库 / 摘要）由管线按注入源产出。
    from agent.mechanisms.context_pipeline import ContextPipeline

    pipeline = ContextPipeline(
        str(cid or ""),
        sources=getattr(app, "context_sources", None),
        **(dict(getattr(app, "context_defaults", None) or {})),
    )
    pipeline.append_system(system_text)
    pipeline.set_dialogue(messages, covered_end=_covered_end_of(events))
    head = pipeline.host_messages()
    plugin_segments = pipeline.plugin_segments()
    payload = layout_from_messages(
        messages,
        system_text=system_text,
        head=head,
        plugin_segments=plugin_segments,
        budget_tokens=budget,
    )
    return payload if payload.get("segments") else None


def _covered_end_of(events: List[Any]) -> int:
    """末次压缩的覆盖点（事实里的 `context_compacted`）。"""
    covered = 0
    for event in events or []:
        if str(getattr(event, "type", "") or "") != "context_compacted":
            continue
        data = getattr(event, "data", None) or {}
        try:
            covered = max(covered, int(data.get("covered_end") or 0))
        except (TypeError, ValueError):
            continue
    return covered


def _current_todo(app: Any, cid: str) -> List[Dict[str, Any]]:
    """当前会话的清单条目：**只读 `live_state`**，不从历史事件里猜。

    历史事件里按 `items` 形状找会抓错：`find_in_file` / `file_search` /
    `python_inline` 的结果同样是 `{"items": [...]}`，取最后一个就把搜索结果
    当成清单，前端读 `it.text` 得到空串、渲染出没有文字的复选框。

    `live_state` 也是 `close` 生效的地方（清除清单即删文件），从它读不会在刷新后
    复活已关闭的清单；`todo_list` 的每次增删都经它落盘，事实流只是它的派生物。
    """
    live = getattr(app, "live_state", None)
    if live is None:
        return []
    todo = live.get_todo(cid)
    if not isinstance(todo, dict):
        return []
    items = todo.get("items")
    return [dict(it) for it in items] if isinstance(items, list) else []


def _date_group(mtime: float, now: Optional[float] = None) -> str:
    """修改时间 → 中文日期分组（口径直接取 `agent.shell.timefmt`，避免两处漂移）。"""
    return date_group(mtime, now)


# ── 内存态：经典界面需要、但内核不持有的三样东西 ─────────────────
class ClassicState:
    """按会话的内存态（进程重启即丢，符合"UI 偏好"的语义）。

    - `usage`：用量累计（经典界面的 `/api/usage-accumulator`）
    - `command_input`：命令确认时的回灌通道（只存不注入，内核暂不消费）
    - `attachments`：本轮附件（供 `/api/chat/attachment` 内联返回）

    知识库勾选由 knowledge 插件的运行时持有（带落盘与注入），
    界面经插件自己的端点 `/api/plugin/knowledge/checked` 读写。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.usage: Dict[str, Dict[str, int]] = {}
        self.command_input: Dict[str, Dict[str, Any]] = {}
        self.attachments: Dict[str, List[Dict[str, Any]]] = {}

    # 用量 ──
    def add_usage(self, cid: str, data: Dict[str, Any]) -> None:
        """按 SSE 那套字段名累加，输出时再翻成 accumulator 那套。"""
        if not cid:
            return
        with self._lock:
            acc = self.usage.setdefault(cid, {
                "total_prompt_tokens": 0, "total_completion_tokens": 0,
                "total_cache_hit_tokens": 0, "total_cache_miss_tokens": 0,
                "total_tokens": 0,
            })
            prompt = int(data.get("prompt_tokens") or 0)
            completion = int(data.get("completion_tokens") or 0)
            hit = int(data.get("prompt_cache_hit_tokens") or 0)
            miss = int(data.get("prompt_cache_miss_tokens") or max(0, prompt - hit))
            acc["total_prompt_tokens"] += prompt
            acc["total_completion_tokens"] += completion
            acc["total_cache_hit_tokens"] += hit
            acc["total_cache_miss_tokens"] += miss
            acc["total_tokens"] += int(data.get("total_tokens") or (prompt + completion))

    def set_usage(self, cid: str, data: Dict[str, Any]) -> None:
        """**覆盖**该会话的累计用量（`accumulator` 那套字段名）。

        与 `add_usage` 的区别就是这个方法的全部意义：`/api/usage-accumulator` 的
        PUT 上报的是**会话累计值**，不是本轮增量 —— 用累加就等于每上报一次翻一倍。
        """
        if not cid:
            return
        prompt = int(data.get("prompt_tokens") or 0)
        completion = int(data.get("completion_tokens") or 0)
        hit = int(data.get("prompt_cache_hit_tokens") or 0)
        miss = int(data.get("prompt_cache_miss_tokens") or max(0, prompt - hit))
        with self._lock:
            self.usage[cid] = {
                "total_prompt_tokens": prompt,
                "total_completion_tokens": completion,
                "total_cache_hit_tokens": hit,
                "total_cache_miss_tokens": miss,
                "total_tokens": int(data.get("total_tokens") or (prompt + completion)),
            }

    def get_usage(self, cid: str) -> Dict[str, int]:
        """返回累计量（`accumulator` 那套字段名）。

        **`session_token_used` 是派生值**（输入 + 输出），不是独立计数器：
        经典界面的圆环用它显示「已用」，而 PUT 上来的字段里就有它 ——
        不从 `total_*` 推导就会出现"圆环显示 0、同一提示里却写着
        `输入: 18,631 输出: 8`"这种自相矛盾。由 `total_*` 推导，只有一个权威。
        """
        with self._lock:
            acc = dict(self.usage.get(cid) or {
                "total_prompt_tokens": 0, "total_completion_tokens": 0,
                "total_cache_hit_tokens": 0, "total_cache_miss_tokens": 0,
                "total_tokens": 0,
            })
        acc["session_token_used"] = (
            int(acc.get("total_prompt_tokens") or 0)
            + int(acc.get("total_completion_tokens") or 0)
        )
        return acc

    def reset_usage(self, cid: str) -> None:
        with self._lock:
            self.usage.pop(cid, None)

    # 命令输入回灌（预留）──
    def set_command_input(self, cid: str, payload: Dict[str, Any]) -> None:
        with self._lock:
            self.command_input[cid] = {"payload": dict(payload or {}), "at": time.time()}

    def take_command_input(self, cid: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            item = self.command_input.pop(cid, None)
        return item["payload"] if item else None

    # 附件（内联）──
    def put_attachments(self, cid: str, items: List[Dict[str, Any]]) -> None:
        with self._lock:
            self.attachments[cid] = list(items or [])

    def get_attachment(self, cid: str, ident: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            for item in self.attachments.get(cid) or []:
                if str(item.get("id")) == str(ident):
                    return dict(item)
        return None

    def clear_attachments(self, cid: str) -> None:
        with self._lock:
            self.attachments.pop(cid, None)


# ── 端点实现 ────────────────────────────────────────────────
class Inbound:
    """把经典界面的入参翻成内核调用，再把结果翻回界面形状。"""

    def __init__(self, app: Any, state: ClassicState) -> None:
        self._app = app
        self.state = state
        # 由 `ClassicAdapter` 注入 WebShell（用于复用内核的标题派生）
        self._shell: Any = None

    def _mode_of(self, cid: str) -> str:
        live = getattr(self._app, "live_state", None)
        if live is None:
            return "auto"
        return str(live.get_mode(cid))

    def _model(self, cid: str = "") -> str:
        """当前会话用哪个模型（`conversation` 帧据此同步前端下拉）。

        与 `adapter._model` 同一条纪律：**按会话取**，不能恒取全局默认 ——
        否则每轮开场都把用户的模型选择覆盖回默认。
        """
        live = getattr(self._app, "live_state", None)
        if live is not None:
            try:
                want = live.get_model(cid)
                if want:
                    return str(want)
            except Exception:
                # 读会话状态失败不打断事件翻译（这里只是给前端一个展示名）。
                # 取不到就落到下面的 provider 默认名 —— 退化结果仍然可用，
                # 而抛出去会让整条 SSE 帧丢失，代价远大于"显示的是默认模型名"。
                pass
        provider = getattr(self._app, "provider", None)
        return str(getattr(provider, "model", "") or "")

    # ── /api/chat/sessions ────────────────────────────────
    def sessions(self) -> Dict[str, Any]:
        """会话名录：经典界面读 `s.id` + `s.date_group`（不是 `conversation_id`）。

        经典界面**不看 `ok`**（agent-ui.js:309），所以这里返回体只求字段齐。
        数据源与内核 `/api/chat/sessions` 一致：`<store>/sessions/*.raw` 的 mtime 倒序。
        """

        store = getattr(self._app, "store", None)
        root = getattr(store, "data_root", None) if store is not None else None
        rows: List[Dict[str, Any]] = []
        if root is not None:
            directory = Path(root) / "sessions"
            if directory.is_dir():
                entries = []
                for path in directory.glob("*.raw"):
                    cid = path.stem
                    if not C.CID_PATTERN.match(cid):
                        continue
                    try:
                        entries.append((path.stat().st_mtime, cid, path))
                    except OSError:
                        continue
                entries.sort(reverse=True)
                now = time.time()
                for mtime, cid, path in entries:
                    title = self._derived_title(path)
                    rows.append({
                        "id": cid,                                  # ← 经典界面读这个名
                        "conversation_id": cid,                     # 内核口径，一并给（超集）
                        "short_id": cid[:8],                        # 无标题时前端回落显示
                        "title": title,
                        "date_group": _date_group(mtime, now),
                        "mtime": int(mtime),
                    })
        return {
            "ok": True,
            "items": rows,
            "sessions": rows,
            "conversation_ids": [r["id"] for r in rows],
        }

    def _derived_title(self, path: Path) -> str:
        """派生标题：**优先复用内核的实现**，保证两侧口径一致（截断长度、省略号）。

        内核 `/api/chat/sessions` 用 `WebShell._derive_title(cid)` 并截到 40 字 + `…`。
        这里如果自己写一套，两边迟早会漂移；所以先问内核要，拿不到才回落本地读文件。
        """
        cid = path.stem
        shell = getattr(self, "_shell", None)
        derive = getattr(shell, "_derive_title", None) if shell is not None else None
        if callable(derive):
            try:
                title = str(derive(cid) or "")
                if title:
                    return title
            except Exception:
                # 标题推导是可选的**增强**（读索引文件），失败即跳过。
                # 推导器坏了 / 索引缺失就走下面的 `_scan_title`（扫事实日志）兜底
                # ——那才是权威来源。这里失败只影响"少一次快速命中"。
                pass
        return _scan_title(path)

    # ── /api/chat/history ─────────────────────────────────
    def history(self, cid: str) -> Dict[str, Any]:
        """会话历史。经典界面从这个返回体里读**三样不同的东西**：

        1. `j.items` —— `{role:"user"|"assistant"|"tool", content, attachments}`，
           由 `renderHistoryItems` 渲染成气泡与工具卡（agent-ui.js 内）；
        2. `j.context_layout` —— 顶部级别（**不是**埋在 events 里），
           由 `applyContextLayoutFromHistory` 读（agent-ui.js 内）；
        3. `j.todo_list` —— 清单数组。

        **必须带 `ok:true`**：`if(!j||j.ok!==true)return;` —— 少了就整段静默不渲染
        （对比 `/api/chat/sessions` 完全不看 ok，两者判据不对称）。

        这里**不给**逐条老事件：刷新页面一个字段都不读它，而它按事件条数增长
        （一次真实刷新里 events 曾占响应体 99.6%，items 只占 0.3%），
        要逐条事件的是 SSE 流（实时帧与重连重放，走 `adapter.replay_after`）。

        `items` **必须由内核事件折出来**：经典界面的 30 种事件里没有"用户消息"这一种
        （用户气泡在实时路径由前端乐观渲染），所以用户侧只能从 `input_claimed` 取。
        """
        cid = C.normalize_cid(cid)
        if not cid:
            return {"ok": False, "error": "invalid conversation_id", "items": []}
        events = self._load_events(cid)
        items, resolved = _history_items(events)
        # 把解出的**字节**登记进内存，供 `/api/chat/attachment?id=…` 取用。
        # 这个 dict 是从事实派生的缓存，内容一律来自 `.raw`，
        # 因此刷新、重启、两个标签页看到的都一致（id 也是可重算的）。
        if resolved:
            register = []
            for item in resolved[-_ATTACH_REGISTER_MAX_COUNT:]:
                raw = item.get("data_base64") if isinstance(item, dict) else None
                size = len(raw or "") if isinstance(raw, str) else 0
                if size and size <= _ATTACH_REGISTER_MAX_BYTES:
                    register.append(item)
            if register:
                self.state.put_attachments(cid, register)
        return {
            "ok": True,
            "conversation_id": cid,
            "items": items,
            # 事实里没有就**按同一口径重算**（`context_layout` 是派生数据、从不落盘，
            # 不兜底的话刷新后右栏分段条会回落「—」）。
            "context_layout": (_last_payload(events, "context_layout")
                               or compute_context_layout(self._app, events, cid)),
            "todo_list": _current_todo(self._app, cid),
        }

    def _load_events(self, cid: str) -> List[Any]:
        store = getattr(self._app, "store", None)
        if store is None:
            return []
        return list(store.load(cid))

    # ── /api/chat/ui-state ────────────────────────────────
    #
    # ⚠️ **语义冲突**：内核的 `/api/chat/ui-state` 存的是
    # 「模式 / todo / 自主」（**按会话**），而经典界面 GET 不带 `conversation_id`。
    # 不带 id 的那种请求，适配层只回**与客户端无关**的那部分：哪些会话在跑。
    #
    # **布局（打开过哪些标签、激活哪一个）存在浏览器本地**：
    # 「激活的是哪个会话」是某个客户端的选择，不是服务器的事实 —— 两个浏览器各自
    # 激活不同会话时，一个全局字段无法表示，谁后写谁覆盖，另一个刷新就跳到别人的会话。
    # 所以这两个都在浏览器本地（`localStorage`）；服务端不提供、也不接收。
    def ui_state_get(self) -> Dict[str, Any]:
        """经典界面不带 `conversation_id` 的 GET：只回**在跑的会话**。

        ## `running` 字段的作用

        **中途接入的跟跑页面点不到「停止」**。
        时序是"page1 先开跑 → page2 才打开 `?conversation_id=<cid>`"或"跟跑中 F5" ——
        此时 page2 拿不到 `run_started`（SSE 没有游标就不回放），
        于是 `serverBusy` 恒为 false、停止键永不出现，而**任务其实正在跑**。

        所以这里透出服务端的权威忙闲（运行态登记），前端在切会话/F5 后
        拉一次本端点把 `serverBusy` 回填。

        这项是**按会话**的事实，与"哪个客户端激活了哪个会话"无关。
        """
        return self._with_running({"ok": True, "state": {}})

    def _with_running(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """给返回体补上"哪些会话正在跑"（**服务端权威**）。

        读不出来就当都没有在跑（前端退回"靠 SSE 推断"的老行为），**不抛**。
        `running` 键**总在**：客户端按固定形状取字段，缺键会把"没在跑"和"字段没给"
        混成同一种情况。
        """
        state = payload.get("state")
        if not isinstance(state, dict):
            return payload
        state["running"] = []
        mesh = getattr(self._app, "mesh", None)
        if mesh is None:
            return payload
        lister = getattr(mesh, "running_cids", None)
        if not callable(lister):
            return payload
        try:
            state["running"] = [str(c) for c in lister()]
        except Exception as exc:
            # 忙闲只用来决定"停止"键显不显示；问不出来就当没在跑，但必须留痕。
            print(
                f"[inbound] 列举 running 失败: {type(exc).__name__}: {exc}",
                file=sys.stderr, flush=True,
            )
            state["running"] = []
        return payload

    def ui_state_put(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """经典界面不带 `conversation_id` 的 PUT：**不存任何东西**。

        布局（标签列表 / 激活会话）在浏览器本地，服务端不做记录：一个全局字段
        表示不了"两个客户端各自激活不同会话"，只会互相覆盖。
        端点为兼容旧前端保留，收到就丢弃。
        """
        return {"ok": True}

    # ── /api/chat/title ───────────────────────────────────
    def title(self, cid: str) -> Dict[str, Any]:
        """会话标题：**直接复用内核 `WebShell.title()`**。

        它已经处理了"有缓存就返回 / 否则调一次模型 / 失败回落派生标题"的完整逻辑；
        适配层自己重写一遍只会让两处口径漂移（而且 `fallback_title` 收的是**消息列表**，
        不是事件列表——传错类型就会抛异常）。

        经典界面只读 `j.title`（agent-ui.js:255 附近），所以把内核返回体里的 `title` 取出来即可。
        """
        cid = C.normalize_cid(cid)
        if not cid:
            return {"ok": False, "title": ""}
        shell = self._shell
        getter = getattr(shell, "title", None) if shell is not None else None
        if callable(getter):
            try:
                result = getter(cid)
            except Exception as exc:
                print(
                    f"[inbound] 取标题失败 cid={cid}: "
                    f"{type(exc).__name__}: {exc}",
                    file=sys.stderr, flush=True,
                )
            else:
                # 内核口径是 `(status, payload)`
                if isinstance(result, tuple) and len(result) == 2:
                    payload = result[1] if isinstance(result[1], dict) else {}
                    if payload.get("title"):
                        return {"ok": True, "conversation_id": cid,
                                "title": str(payload["title"])}
        return {"ok": True, "conversation_id": cid, "title": self._fallback_title(cid)}

    def _fallback_title(self, cid: str) -> str:
        """回落：从该会话的首条用户输入派生（不调模型、不抛异常）。"""
        path = self._session_path(cid)
        if path is None or not path.is_file():
            return ""
        return _scan_title(path)

    def _session_path(self, cid: str) -> Optional[Path]:
        store = getattr(self._app, "store", None)
        root = getattr(store, "data_root", None) if store is not None else None
        if root is None:
            return None
        return Path(root) / "sessions" / f"{cid}.raw"

    # ── /api/usage-accumulator ───────────────────────────
    def usage_get(self, cid: str) -> Dict[str, Any]:
        """返回**累计**量，字段名是 accumulator 那套（与 SSE 不同）。"""
        cid = C.normalize_cid(cid)
        acc = self.state.get_usage(cid)
        return {"ok": True, **acc}

    def usage_put(self, cid: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """写入累计用量 —— **覆盖语义**，不是累加。

        ⚠️ 写入走 `set_usage`（覆盖语义），`add_usage`（累加语义）在此会重复计数：
        前端 PUT 的字段名是 `total_prompt_tokens` 等 —— **会话累计值**，
        不是"本轮的增量"。用累加语义等于每上报一次就翻一倍。

        覆盖语义也是 `/api/usage-accumulator` 这一路自己的口径：上报的是当前总量。

        需要清空仍可用 `body["reset"]`。
        """
        cid = C.normalize_cid(cid)
        if not cid:
            return {"ok": False, "error": "invalid conversation_id"}
        if body.get("reset"):
            self.state.reset_usage(cid)
            return {"ok": True, **self.state.get_usage(cid)}
        payload = {
            "prompt_tokens": body.get("total_prompt_tokens") or body.get("prompt_tokens"),
            "completion_tokens": (body.get("total_completion_tokens")
                                  or body.get("completion_tokens")),
            "prompt_cache_hit_tokens": body.get("total_cache_hit_tokens"),
            "prompt_cache_miss_tokens": body.get("total_cache_miss_tokens"),
            "total_tokens": body.get("total_tokens"),
        }
        # 覆盖：优先用 `set_usage`；没有就"先清零再写入"（语义等价）。
        setter = getattr(self.state, "set_usage", None)
        if callable(setter):
            setter(cid, payload)
        else:
            self.state.reset_usage(cid)
            self.state.add_usage(cid, payload)
        return {"ok": True, **self.state.get_usage(cid)}

    # ── /api/chat/title ───────────────────────────────────

    # ── /api/chat/command-input（预留）────────────────────
    def command_input(self, cid: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """把人的回答送进正在等 stdin 的 `run_command` 子进程。

        这条通道必须有真实出口：只把 body 存进 state 的话，界面上弹了输入条、
        点了发送，命令那边却永远收不到 —— 看起来"没反应"，实际是输入被吞了。
        """
        cid = C.normalize_cid(cid)
        if not cid:
            return {"ok": False, "error": "invalid conversation_id"}
        tid = str(body.get("tool_call_id") or "").strip()
        text = str(body.get("input") or "").strip()
        if not tid:
            return {"ok": False, "error": "tool_call_id required"}
        if not text:
            return {"ok": False, "error": "empty input"}
        from agent.mechanisms.live_state import submit_command_input
        if not submit_command_input(f"{cid}:{tid}", text):
            return {"ok": False, "error": "no active run_command awaiting input"}
        return {"ok": True, "conversation_id": cid, "tool_call_id": tid}

    # ── /api/chat/attachment（内联 base64）────────────────
    def attachment(self, cid: str, ident: str) -> Tuple[int, bytes, str]:
        """返回 `(status, body, content_type)`；找不到给 404。

        经典界面用 `<img src="/api/chat/attachment?...">` 直接引用（il.js:7），
        所以这里必须返回**图片字节**，不能返回 JSON。
        """
        cid = C.normalize_cid(cid)
        item = self.state.get_attachment(cid, ident) if cid else None
        if not item:
            return 404, b"not found", "text/plain; charset=utf-8"
        data = str(item.get("data_base64") or "")
        mime = str(item.get("mime") or "image/png")
        try:
            return 200, base64.b64decode(data), mime
        except Exception:
            return 500, b"bad attachment", "text/plain; charset=utf-8"

    def remember_attachments(self, cid: str, images: Any) -> List[Dict[str, Any]]:
        """把本轮 `images` 存进来并编上 id，供 `send` 的返回体回给经典界面。

        id 由**图片字节**派生（与 `_history_items` 同一函数），所以这个 id 与
        刷新后历史里的 id 相同 —— 前端不必知道是刚发的还是从历史读的。
        """
        items: List[Dict[str, Any]] = []
        if not isinstance(images, list):
            return items
        for index, raw in enumerate(images):
            if not isinstance(raw, dict):
                continue
            data = raw.get("data_base64")
            if not isinstance(data, str) or not data:
                continue
            items.append({
                "id": _attachment_id(data, index),
                "name": str(raw.get("name") or f"image{index}.png"),
                "mime": str(raw.get("mime") or "image/png"),
                "data_base64": data,
            })
        if items:
            self.state.put_attachments(cid, items)
        return items

    # ── /health 的 model 白名单自检 ────────────────────────
    def model_in_allowed(self, model: str, allowed: List[str]) -> bool:
        """经典界面的 `applyModel` 会做白名单校验；`/health` 给的 model 取自名单，
        否则顶栏永远停在"模型加载中…"（agent-ui.js:496 vs 407）。"""
        name = str(model or "").strip()
        if not name:
            return False
        if not allowed:
            return True          # 名单为空 = 不设白名单
        return name in allowed
