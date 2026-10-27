# -*- coding: utf-8 -*-
"""经典 UI 上下文布局。"""
from __future__ import annotations

import sys
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

from agent.core.error_report import report_error
from agent.mechanisms.context import ContextPipeline
from agent.mechanisms.context.tokens import default_message_tokens
from agent.shell.classic_adapter.contract import EV_CONTEXT_SEGMENTS

#: 上下文布局的小缓存：`{cid: ((事实条数, 注入源版本), 布局)}`。
#
# 本函数在每一步都会被调（实时帧一路），每次都做
# 一次全量 `store.load` + 折叠，一回合几十步就是几百毫秒的纯浪费
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
    （模式说明与工具调用的内部 system 注入不落记录，只有那份快照里有）。
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

    items = list(getattr(packed, "items", None) or [])
    counts = list(getattr(packed, "counts", None) or [])
    fresh: List[Dict[str, Any]] = []
    index_by_group: Dict[Tuple[str, str], int] = {}
    for index, item in enumerate(items):
        key, label, text = item[0], item[1], item[2]
        reported = counts[index] if index < len(counts) else 1
        group = (f"plugin:{key}", str(label or key))
        tokens = int(default_message_tokens(
            {"role": "system", "content": str(text or "")}))
        pos = index_by_group.get(group)
        if pos is not None:
            fresh[pos]["tokens"] = int(fresh[pos]["tokens"]) + tokens
            continue
        index_by_group[group] = len(fresh)
        fresh.append({
            "key": group[0],
            "label": group[1],
            "tokens": tokens,
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
    """本次会话的上下文预算 = 当前模型的压缩阈值。

    取不到就给 0，调用方各自退回自己的兜底口径。
    """
    resolver = getattr(app, "compression_threshold_for", None)
    if callable(resolver):
        return int(resolver(cid) or 0)
    factory = getattr(app, "compactor_factory", None)
    if not callable(factory):
        return 0
    return int(getattr(factory(cid), "summary_token_threshold", 0) or 0)


def _last_segments(events: List[Any],
                   budget_tokens: int = 0) -> Optional[Dict[str, Any]]:
    """最后一条 `context_segments`（内核发的装配快照）。

    快照里的 `pct` 是产出那一刻按当时预算算好的，会随配置与版本漂移
    （早先的装配点没把预算传下来，快照里 `budget_tokens` 等于"已用"，
    于是界面那条「剩余容量」永远是 0%）。所以这里按当前预算把各段 pct 重算一遍 ——
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

    倒序扫描：模式在请求里位置不固定（工具调用里它后面还跟着工具结果）。
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
    """兜底：没有装配快照的旧会话（快照是后加的，老记录里没有）也分层。

    Skills 清单、知识库、摘要都不在事实记录里 —— 它们是每回合装配时注入的，
    所以只从事实折叠不出来。这里真装一次上下文（与内核同一套注入源），
    读它的头部来切段；事实只提供对话与覆盖点。
    """
    from agent.core.session_log import SessionLog
    from agent.mechanisms.context import layout_from_messages

    messages = SessionLog(events=list(events)).derive_request_messages()
    if not messages:
        return None
    budget = 0
    compactor_factory = getattr(app, "compactor_factory", None)
    if callable(compactor_factory):
        budget = int(getattr(compactor_factory(cid), "summary_token_threshold", 0) or 0)
    from agent.shell.prompts import resolve_system_prompt

    registry = getattr(app, "registry", None)
    from agent.shell.service_keys import SERVICE_RUNNER
    context = getattr(app, "context", None)
    if context is not None and context.has(SERVICE_RUNNER):
        registry = context.get(SERVICE_RUNNER).registry_for(cid)
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
        # 旧会话没有装配快照，但终点仍是界面：分母按当前模型窗口给，
        # 否则这条分支永远回 0，界面只好拿预算冒充窗口。
        model_max_context_tokens=_context_window(app, cid),
    )
    return payload if payload.get("segments") else None


def _context_window(app: Any, cid: str) -> int:
    """当前模型窗口；app 未提供解析能力时返回 0（界面按预算兜底）。"""
    resolver = getattr(app, "context_window_for", None)
    if not callable(resolver):
        return 0
    return int(resolver(str(cid or "")))


def _covered_end_of(events: List[Any]) -> int:
    """末次压缩的覆盖点（事实里的 `context_compacted`）。"""
    covered = 0
    for event in events or []:
        if str(getattr(event, "type", "") or "") != "context_compacted":
            continue
        data = getattr(event, "data", None) or {}
        try:
            covered = max(covered, int(data.get("covered_end") or 0))
        except (TypeError, ValueError) as exc:
            report_error("agent.shell.classic_adapter.layout._covered_end_of", exc)
            continue
    return covered


def current_todo(app: Any, cid: str) -> List[Dict[str, Any]]:
    """当前会话的清单条目：只读 `live_state`，不从历史事件里猜。

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
