# -*- coding: utf-8 -*-
"""入站适配：经典 UI 的请求 → 内核调用 → 经典 UI 期望的返回体（前端 → 服务端）。

这里只做形状翻译，不实现业务：
业务一律落到内核既有面（`app.runner` / `app.store` / `app.live_state` / …）。

三个不对称（任一命中都会静默失效）：
  1. `/api/chat/history` 必须返回 `ok:true`，否则经典界面直接 return、整段历史不渲染
     （agent-ui.js:339）；而 `/api/chat/sessions` 完全不看 `ok`（agent-ui.js:309）。
  2. 用量字段名有两套：contract.SSE_USAGE_FIELDS（SSE）与 ACCUMULATOR_USAGE_FIELDS（累计接口），互不通用。
  3. `ui-state` 的 PUT 直接收布局对象、GET 返 `{state:{...}}`（不是平铺）。
"""
from __future__ import annotations

import base64
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import agent.shell.classic_adapter.contract as C
from agent.common.status import RUN_MODE_AUTO
from agent.core.error_report import report_error
from agent.core.events import Event
from agent.core.state_values import TOOL_CANCELED, TOOL_SUSPENDED
from agent.mechanisms.session_title import UNKNOWN_TITLE
from agent.shell.classic_adapter.history import (
    ATTACH_REGISTER_MAX_BYTES,
    ATTACH_REGISTER_MAX_COUNT,
    attachment_id,
    last_payload,
)
from agent.shell.classic_adapter.history import (
    history_items as history_items,
)
from agent.shell.classic_adapter.history_page import HISTORY_PAGE_CHARS, fold_rounds, select_page
from agent.shell.classic_adapter.layout import compute_context_layout, current_todo
from agent.shell.classic_adapter.sessions import session_date_group
from agent.shell.classic_adapter.state import ClassicState
from agent.shell.session.resume import confirmation_store, read_pending


class Inbound:
    """把经典界面的入参翻成内核调用，再把结果翻回界面形状。"""

    def __init__(self, app: Any, state: ClassicState) -> None:
        self._app = app
        self.state = state
        # 由 `ClassicAdapter` 注入 WebShell（用于复用内核的标题派生）
        self._shell: Any = None
        self._usage_hydrated: set[str] = set()
        # 历史页按“文件指纹”缓存折叠结果：翻上一页不再重读/解密 50MB 会话。
        self._history_cache: "OrderedDict[tuple, tuple]" = OrderedDict()

    def _mode_of(self, cid: str) -> str:
        live = getattr(self._app, "live_state", None)
        if live is None:
            return RUN_MODE_AUTO
        return str(live.get_mode(cid))

    def _model(self, cid: str = "") -> str:
        """当前会话用哪个模型（`conversation` 帧据此同步前端下拉）。

        与 `adapter._model` 同一条纪律：按会话取，不能恒取全局默认 ——
        否则每回合开场都把用户的模型选择覆盖回默认。
        """
        live = getattr(self._app, "live_state", None)
        if live is not None:
            try:
                want = live.get_model(cid)
                if want:
                    return str(want)
            except Exception as exc:
                # 读会话状态失败不打断事件翻译（这里只是给前端一个展示名）。
                # 取不到就落到下面的 provider 默认名 —— 退化结果仍然可用，
                # 而抛出去会让整条 SSE 帧丢失，代价远大于"显示的是默认模型名"。
                report_error("agent.shell.classic_adapter.inbound.Inbound._model", exc)
        provider = getattr(self._app, "provider", None)
        return str(getattr(provider, "model", "") or "")

    # ── /api/chat/sessions ────────────────────────────────
    def sessions(self) -> Dict[str, Any]:
        """会话名录：经典界面读 `s.id` + `s.date_group`（不是 `conversation_id`）。

        经典界面不看 `ok`（agent-ui.js:309），所以这里返回体只求字段齐。
        数据源与内核 `/api/chat/sessions` 一致：`<store>/sessions/*.raw` 的 mtime 倒序。
        """

        store = getattr(self._app, "store", None)
        root = getattr(store, "data_root", None) if store is not None else None
        rows: List[Dict[str, Any]] = []
        directory = getattr(store, "sessions_dir", None)
        if directory is None and root is not None:
            directory = Path(root) / "session" / "raw"
        if directory is not None:
            directory = Path(directory)
            if directory.is_dir():
                entries = []
                for path in directory.glob("*.raw"):
                    cid = path.stem
                    if not C.CID_PATTERN.match(cid):
                        continue
                    try:
                        entries.append((path.stat().st_mtime, cid, path))
                    except OSError as exc:
                        report_error("agent.shell.classic_adapter.inbound.Inbound.sessions", exc)
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
                        "date_group": session_date_group(mtime, now),
                        "mtime": int(mtime),
                    })
        return {
            "ok": True,
            "items": rows,
            "sessions": rows,
            "conversation_ids": [r["id"] for r in rows],
        }

    def _derived_title(self, path: Path) -> str:
        """派生标题：优先复用内核的实现，保证两侧口径一致（截断长度、省略号）。

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
            except Exception as exc:
                # 标题推导是可选的增强（读索引文件），失败即跳过。
                # 推导器坏了 / 索引缺失时直接返回未知标题，不回读会话日志。
                report_error("agent.shell.classic_adapter.inbound.Inbound._derived_title", exc)
        return UNKNOWN_TITLE

    # ── /api/chat/history ─────────────────────────────────
    def _history_rounds(self, cid: str, store: Any, before: Optional[int]) -> tuple:
        """返回 (rounds, context_layout)；按文件 mtime/size 缓存，避免每页全量读盘。"""
        target = store if store is not None else getattr(self._app, "store", None)
        path = None
        if target is not None:
            raw_path = getattr(target, "raw_path", None)
            if callable(raw_path):
                try:
                    path = raw_path(cid)
                except (ValueError, OSError):
                    path = None
        key = None
        if path is not None:
            try:
                st = path.stat()
                key = (cid, before, int(st.st_mtime_ns), int(st.st_size))
            except OSError:
                key = None
        if key is not None:
            hit = self._history_cache.get(key)
            if hit is not None:
                self._history_cache.move_to_end(key)
                return hit
        window = getattr(target, "history_window", None)
        if callable(window):
            pairs, older = window(cid, before)
            events = self._history_events(pairs)
        else:
            events, older = self._load_events(cid, target), False
        context_layout = (last_payload(events, "context_layout")
                          or compute_context_layout(self._app, events, cid))
        rounds = fold_rounds(events)
        if key is not None:
            self._history_cache[key] = (rounds, context_layout, older)
            while len(self._history_cache) > 3:
                self._history_cache.popitem(last=False)
        return rounds, context_layout, older

    def history(self, cid: str, store: Any = None, *,
                before: Optional[int] = None, meta: bool = False) -> Dict[str, Any]:
        """会话历史。经典界面从这个返回体里读三样不同的东西：

        1. `j.items` —— `{role:"user"|"assistant"|"tool", content, attachments}`，
           由 `renderHistoryItems` 渲染成气泡与工具卡（agent-ui.js 内）；
        2. `j.context_layout` —— 顶部级别（不是埋在 events 里），
           由 `applyContextLayoutFromHistory` 读（agent-ui.js 内）；
        3. `j.todo_list` —— 清单数组。

        必须带 `ok:true`：`if(!j||j.ok!==true)return;` —— 少了就整段静默不渲染
        （对比 `/api/chat/sessions` 完全不看 ok，两者判据不对称）。

        这里不给逐条老事件：刷新页面一个字段都不读它，而它按事件条数增长
        （一次真实刷新里 events 曾占响应体 99.6%，items 只占 0.3%），
        要逐条事件的是 SSE 流（实时帧与重连重放，走 `adapter.replay_after`）。

        `items` 必须由内核事件折出来：经典界面的 30 种事件里没有"用户消息"这一种
        （用户气泡在实时路径由前端乐观渲染），所以用户侧只能从 `input_claimed` 取。
        """
        cid = C.normalize_cid(cid)
        if not cid:
            return {"ok": False, "error": "invalid conversation_id", "items": []}
        rounds, context_layout, older = self._history_rounds(cid, store, before)
        todo_list = current_todo(self._app, cid)
        if meta:
            return {
                "ok": True,
                "conversation_id": cid,
                "items": [],
                "context_layout": context_layout,
                "todo_list": todo_list,
            }
        page = select_page(rounds, before=before)
        items = list(page.items)
        self._mark_stale_suspends(cid, items, store)
        # 把本页解出的字节合并进内存，供 `/api/chat/attachment?id=…` 取用。
        # 不能整体替换：旧页已经渲染的附件仍可能被浏览器请求。
        if page.attachments:
            register = []
            for item in page.attachments[-ATTACH_REGISTER_MAX_COUNT:]:
                raw = item.get("data_base64") if isinstance(item, dict) else None
                size = len(raw or "") if isinstance(raw, str) else 0
                if size and size <= ATTACH_REGISTER_MAX_BYTES:
                    register.append(item)
            if register:
                self.state.merge_attachments(cid, register)
        return {
            "ok": True,
            "conversation_id": cid,
            "items": items,
            "page": {
                "budget_chars": HISTORY_PAGE_CHARS,
                "chars": page.chars,
                "has_more": page.has_more or older,
                "next_before": (page.next_before if page.has_more else
                                rounds[page.start].anchor if older and page.start < page.end else None),
            },
            "context_layout": context_layout,
            "todo_list": todo_list,
        }

    def _mark_stale_suspends(self, cid: str, items: List[Dict[str, Any]], store: Any) -> None:
        if not any(item.get("status") == TOOL_SUSPENDED for item in items):
            return
        contexts = getattr(self._app, "session_contexts", None)
        session = contexts.get(cid) if contexts is not None else None
        pending = read_pending(session, store if store is not None else confirmation_store(self._app, cid), cid)
        pending_call = str((pending or {}).get("call_id") or "").strip()
        for item in items:
            if (item.get("role") == "tool"
                    and item.get("status") == TOOL_SUSPENDED
                    and str(item.get("tool_call_id") or "") != pending_call):
                item["status"] = TOOL_CANCELED
                item["error"] = "用户取消了这次确认（未作答）"

    def _load_events(self, cid: str, store: Any = None) -> List[Any]:
        target = store if store is not None else getattr(self._app, "store", None)
        if target is None:
            return []
        loader = getattr(target, "load_with_seq", None)
        if loader is not None:
            pairs = list(loader(cid))
        else:
            pairs = list(enumerate(target.load(cid), 1))
        return self._history_events(pairs)

    @staticmethod
    def _history_events(pairs: Any) -> List[Any]:
        out: List[Any] = []
        for seq, event in pairs:
            data = dict(getattr(event, "data", None) or {})
            data.setdefault("_seq", int(seq))
            out.append(Event(str(getattr(event, "type", "")), data))
        return out

    # ── /api/chat/ui-state ────────────────────────────────
    #
    # ⚠️ 语义冲突：内核的 `/api/chat/ui-state` 存的是
    # 「模式 / todo / 自主」（按会话），而经典界面 GET 不带 `conversation_id`。
    # 不带 id 的那种请求，适配层只回与客户端无关的那部分：哪些会话在跑。
    #
    # 布局（打开过哪些标签、激活哪一个）存在浏览器本地：
    # 「激活的是哪个会话」是某个客户端的选择，不是服务器的事实 —— 两个浏览器各自
    # 激活不同会话时，一个全局字段无法表示，谁后写谁覆盖，另一个刷新就跳到别人的会话。
    # 所以这两个都在浏览器本地（`localStorage`）；服务端不提供、也不接收。
    def ui_state_get(self, confirmation_ids: str = "") -> Dict[str, Any]:
        """经典界面不带 `conversation_id` 的 GET：只回在跑的会话。

        ## `running` 字段的作用

        中途接入的跟跑页面点不到「停止」。
        时序是"page1 先开跑 → page2 才打开 `?conversation_id=<cid>`"或"跟跑中 F5" ——
        此时 page2 拿不到 `run_started`（SSE 没有游标就不回放），
        于是 `serverBusy` 恒为 false、停止键永不出现，而任务其实正在跑。

        所以这里透出服务端的权威忙闲（运行态登记），前端在切会话/F5 后
        拉一次本端点把 `serverBusy` 回填。

        这项是按会话的事实，与"哪个客户端激活了哪个会话"无关。
        """
        contexts = getattr(self._app, "session_contexts", None)
        pending = {}
        buckets = contexts.buckets() if contexts is not None else {}
        requested = dict.fromkeys(filter(None, map(C.normalize_cid, confirmation_ids.split(","))))
        for cid in requested or buckets:
            session = buckets.get(cid)
            current = read_pending(session, confirmation_store(self._app, cid) if requested else None, cid)
            if current:
                call_id = current["call_id"]
                pending[cid] = {"call_id": call_id, "request_id": current.get("request_id") or call_id}
        return self._with_running({"ok": True, "state": {"confirmations": pending}})

    def _with_running(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """给返回体补上"哪些会话正在跑"（服务端权威）。

        读不出来就当都没有在跑（前端退回仅靠 SSE 推断），不抛。
        `running` 键总在：客户端按固定形状取字段，缺键会把"没在跑"和"字段没给"
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
            report_error("agent.shell.classic_adapter.inbound.Inbound.ui_state", exc)
            state["running"] = []
        return payload

    def ui_state_put(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """经典界面不带 `conversation_id` 的 PUT：不存任何东西。

        布局（标签列表 / 激活会话）在浏览器本地，服务端不做记录：一个全局字段
        表示不了"两个客户端各自激活不同会话"，只会互相覆盖。
        端点为兼容既有客户端保留，收到就丢弃。
        """
        return {"ok": True}

    # ── /api/chat/title ───────────────────────────────────
    def title(self, cid: str) -> Dict[str, Any]:
        """会话标题：直接复用内核 `WebShell.title()`。

        它已经处理了"有缓存就返回 / 否则调一次模型 / 失败返回未知标题"的完整逻辑；
        适配层自己重写一遍只会让两处口径漂移。

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
                report_error("agent.shell.classic_adapter.inbound.Inbound.title", exc)
            else:
                # 内核口径是 `(status, payload)`
                if isinstance(result, tuple) and len(result) == 2:
                    payload = result[1] if isinstance(result[1], dict) else {}
                    if payload.get("title"):
                        return {"ok": True, "conversation_id": cid,
                                "title": str(payload["title"])}
        return {"ok": True, "conversation_id": cid, "title": self._fallback_title(cid)}

    def _fallback_title(self, cid: str) -> str:
        """没有已生成的标题文件时返回明确的未知标题，不再回读会话日志。"""
        return UNKNOWN_TITLE

    # ── /api/usage-accumulator ───────────────────────────
    def _hydrate_usage(self, cid: str) -> None:
        store = getattr(self._app, "store", None)
        loader = getattr(store, "load", None)
        if not cid or not callable(loader):
            return
        for event in loader(cid):
            if str(getattr(event, "type", "") or "") != "usage":
                continue
            data = getattr(event, "data", None)
            if isinstance(data, dict):
                self.state.add_usage(cid, data)

    def usage_get(self, cid: str) -> Dict[str, Any]:
        """返回累计量，字段名是 accumulator 那套（与 SSE 不同）。

        进程重启后内存状态为空，但 `.raw` 里的 `usage` 事实仍在；
        首次读取时从事实回填，刷新或重启不会把累计用量清零。
        """
        cid = C.normalize_cid(cid)
        if cid and not self.state.has_usage(cid) and cid not in self._usage_hydrated:
            self._usage_hydrated.add(cid)
            self._hydrate_usage(cid)
        acc = self.state.get_usage(cid)
        return {"ok": True, **acc}

    def usage_put(self, cid: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """写入累计用量 —— 覆盖语义，不是累加。

        ⚠️ 写入走 `set_usage`（覆盖语义），`add_usage`（累加语义）在此会重复计数：
        前端 PUT 的字段名是 `total_prompt_tokens` 等 —— 会话累计值，
        不是"本回合的增量"。用累加语义等于每上报一次就翻一倍。

        覆盖语义也是 `/api/usage-accumulator` 这一路自己的口径：上报的是当前总量。

        需要清空仍可用 `body["reset"]`。
        """
        cid = C.normalize_cid(cid)
        if not cid:
            return {"ok": False, "error": "invalid conversation_id"}
        self._usage_hydrated.add(cid)
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

    # ── /api/chat/command-input ───────────────────────────
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
        所以这里必须返回图片字节，不能返回 JSON。
        """
        cid = C.normalize_cid(cid)
        item = self.state.get_attachment(cid, ident) if cid else None
        if not item and cid:
            # 服务重启后内存表为空；历史是附件的唯一事实源，按会话重新登记。
            try:
                self.history(cid)
            except Exception as exc:
                report_error("agent.shell.classic_adapter.inbound.Inbound.attachment", exc)
            item = self.state.get_attachment(cid, ident)
        if not item:
            return 404, b"not found", "text/plain; charset=utf-8"
        data = str(item.get("data_base64") or "")
        mime = str(item.get("mime") or "image/png")
        try:
            return 200, base64.b64decode(data), mime
        except Exception as exc:
            report_error("agent.shell.classic_adapter.inbound.Inbound.attachment", exc)
            return 500, b"bad attachment", "text/plain; charset=utf-8"

    def remember_attachments(self, cid: str, images: Any) -> List[Dict[str, Any]]:
        """把本回合 `images` 存进来并编上 id，供 `send` 的返回体回给经典界面。

        id 由图片字节派生（与 `history_items` 同一函数），所以这个 id 与
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
                "id": attachment_id(data, index),
                "name": str(raw.get("name") or f"image{index}.png"),
                "mime": str(raw.get("mime") or "image/png"),
                "data_base64": data,
            })
        if items:
            self.state.merge_attachments(cid, items)
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
