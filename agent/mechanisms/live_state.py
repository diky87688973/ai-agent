# -*- coding: utf-8 -*-
"""会话实时状态：模式 / 推理档位 / 模型选择 / todo 清单 / 自主与休眠请求。

- 线程安全：实例级锁保护全部会话字典；
- 会话状态可持久化：存储目录由装配注入（缺省纯内存）；变更即时落盘，
  一个会话一份 JSON（模型 / 模式 / 档位 / 清单同住）；
- cid 白名单（[A-Za-z0-9_-]{8,128}）才可拼路径（防穿越）；
- 读取容错：坏 JSON / 缺字段忽略，读不出就当没有（`None` / 默认值）。
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from agent.core.error_report import report_error

_CID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_MODES = ("auto", "plan", "execute")
#: 目标状态：active=到点自动触发；paused=保留但不触发；done=已达成。
_GOAL_STATUSES = ("active", "paused", "done")


class ModeConflict(Exception):
    """模式冲突：Plan 禁止执行 / Execute 缺清单等被拒场景。"""


class GoalError(Exception):
    """目标操作的参数错误（工具层翻成结果里的 error，不抛到回合外）。"""


class LiveState:
    """会话级实时状态容器（装配时单例注入）。

    内存态覆盖：模式 / 推理档位 / 模型选择 / 清单 / 自主 / 目标。
    前四项随会话落盘，其余是回合内的临时事实。
    """

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        default_effort: str = "high",
        default_model: str = "",
    ) -> None:
        self._lock = threading.Lock()
        self._modes: Dict[str, str] = {}
        self._todos: Dict[str, Dict[str, Any]] = {}
        self._state_loaded: set = set()
        self._autonomy: Dict[str, Dict[str, Any]] = {}
        #: 目标表 `{cid: {text, status, note, created_at, updated_at, rounds}}`。
        self._goals: Dict[str, Dict[str, Any]] = {}
        self._efforts: Dict[str, str] = {}
        self._models: Dict[str, str] = {}
        #: 全局默认模型（配置面）；会话级选择优先。空串 = 由 provider 决定。
        self.default_model = str(default_model or "")
        # 全局默认档位（配置面）；会话级覆盖优先
        self.default_effort = default_effort if default_effort in ("high", "max") else "high"
        self._storage_dir = Path(storage_dir) if storage_dir else None

    # ── 模式──────────────────────────────────────

    def get_mode(self, conversation_id: str) -> str:
        """当前模式；无覆盖时默认 auto（显式选择会落盘，刷新后仍在）。"""
        cid = str(conversation_id or "")
        with self._lock:
            self._ensure_loaded(cid)
            return self._modes.get(cid, "auto")

    def set_mode(self, conversation_id: str, run_type: str) -> str:
        """切换模式：auto 清除覆盖（回默认），plan / execute 落状态；返回生效值。"""
        cid = str(conversation_id or "")
        rt = str(run_type or "").strip().lower()
        if rt not in _MODES:
            raise ValueError(f"run_type 必须是 auto / plan / execute 之一，收到 {run_type}")
        with self._lock:
            # 写盘前必须先读回同文件的其余分量，否则这次写入会抹掉模型 / 清单。
            self._ensure_loaded(cid)
            if rt == "auto":
                self._modes.pop(cid, None)
            else:
                self._modes[cid] = rt
            self._persist(cid)
        return rt

    # ── todo 清单─────────────────────────

    def get_todo(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """当前会话清单（副本）；无则 None（首次访问懒加载持久化文件）。"""
        cid = str(conversation_id or "")
        with self._lock:
            self._ensure_loaded(cid)
            lst = self._todos.get(cid)
            if lst is None:
                return None
            return {
                "list_id": str(lst.get("list_id") or ""),
                "items": [dict(it) for it in lst.get("items") or []],
                "collapsed": bool(lst.get("collapsed", False)),
            }

    def set_todo(self, conversation_id: str, todo: Optional[Dict[str, Any]]) -> None:
        """写入 / 清除清单并落盘（None = close：内存清除 + 从状态文件里摘掉清单）。"""
        cid = str(conversation_id or "")
        with self._lock:
            # 先读回同文件的模型 / 模式 / 档位：close 只该删清单，不应清空其它分量。
            self._ensure_loaded(cid)
            if todo is None:
                self._todos.pop(cid, None)
            else:
                self._todos[cid] = dict(todo)
            self._persist(cid)

    def has_active_todo(self, conversation_id: str) -> bool:
        """是否存在非空清单。"""
        todo = self.get_todo(conversation_id)
        return bool(todo and todo.get("items"))

    # ── 自主与休眠────────────────────────

    def set_autonomy(self, conversation_id: str, enabled: bool, summary: str = "") -> None:
        """记录自主开关（enabled + 结束摘要）。"""
        with self._lock:
            self._autonomy[str(conversation_id or "")] = {
                "enabled": bool(enabled),
                "summary": str(summary or ""),
            }

    def get_autonomy(self, conversation_id: str) -> Dict[str, Any]:
        """读取自主开关；无记录默认关闭。"""
        with self._lock:
            val = self._autonomy.get(str(conversation_id or ""))
            return dict(val) if val else {"enabled": False, "summary": ""}

    # ── 目标（Goal：可编辑的任务对象）──────────────────────
    #
    # 触发机制与"自主模式"一致：回合结束后自动再发一条 user 输入；
    # 区别是那条输入取这份目标文案 —— 于是自动续跑有了方向，
    # 也能被用户和模型随时改写、暂停、结束。

    def set_goal(self, conversation_id: str, text: str, *, note: str = "") -> Dict[str, Any]:
        """创建或整体覆盖目标（新建时 `status=active`、`rounds=0`）。"""
        cid = str(conversation_id or "")
        body = str(text or "").strip()
        if not cid:
            raise GoalError("缺少 conversation_id")
        if not body:
            raise GoalError("目标文案不能为空")
        now = time.time()
        with self._lock:
            old = self._goals.get(cid)
            created = float(old.get("created_at") or now) if isinstance(old, dict) else now
            row = {
                "text": body,
                "status": "active",
                "note": str(note or ""),
                "created_at": created,
                "updated_at": now,
                "rounds": int(old.get("rounds") or 0) if isinstance(old, dict) else 0,
            }
            self._goals[cid] = row
        return dict(row)

    def get_goal(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """读取目标；没有则 None。"""
        with self._lock:
            val = self._goals.get(str(conversation_id or ""))
            return dict(val) if isinstance(val, dict) else None

    def update_goal(self, conversation_id: str, *, text: str = "", status: str = "",
                    note: str = "") -> Dict[str, Any]:
        """局部修改目标：只改显式给出的字段（文案 / 状态 / 备注）。"""
        cid = str(conversation_id or "")
        with self._lock:
            row = self._goals.get(cid)
            if not isinstance(row, dict):
                raise GoalError("当前会话没有目标可修改")
            want = str(status or "").strip()
            if want:
                if want not in _GOAL_STATUSES:
                    raise GoalError(f"状态只能是 {'/'.join(_GOAL_STATUSES)}，收到 {want!r}")
                row["status"] = want
            body = str(text or "").strip()
            if body:
                row["text"] = body
            if note:
                row["note"] = str(note)
            row["updated_at"] = time.time()
            return dict(row)

    def delete_goal(self, conversation_id: str) -> bool:
        """删除目标；返回是否确实删掉了（没有目标时为 False）。"""
        with self._lock:
            return self._goals.pop(str(conversation_id or ""), None) is not None

    def note_goal_round(self, conversation_id: str) -> int:
        """记一次"因目标而起的自动回合"，返回累计回合数（供 UI 显示推进程度）。"""
        with self._lock:
            row = self._goals.get(str(conversation_id or ""))
            if not isinstance(row, dict):
                return 0
            row["rounds"] = int(row.get("rounds") or 0) + 1
            row["updated_at"] = time.time()
            return row["rounds"]

    def goal_trigger_text(self, conversation_id: str) -> str:
        """回合结束后该自动发的那条 user 输入；`active` 且文案非空时才有值。

        返回空串 = 不触发（没有目标 / 已暂停 / 已达成 / 文案为空）。
        """
        row = self.get_goal(conversation_id)
        if not isinstance(row, dict) or row.get("status") != "active":
            return ""
        return str(row.get("text") or "").strip()

    # ── 推理档位（按会话）────────────────────────────

    def get_reasoning_effort(self, conversation_id: str) -> str:
        """会话级推理档位；未设置时回落全局默认（`default_effort`，缺省 high）。"""
        cid = str(conversation_id or "")
        with self._lock:
            self._ensure_loaded(cid)
            val = self._efforts.get(cid)
        if val in ("high", "max"):
            return val
        return self.default_effort

    def set_reasoning_effort(self, conversation_id: str, effort: str) -> bool:
        """设置会话级推理档位；非法值拒绝（返回 False），合法值生效并落盘（True）。"""
        cid = str(conversation_id or "").strip()
        value = str(effort or "").strip().lower()
        if not cid or value not in ("high", "max"):
            return False
        with self._lock:
            self._ensure_loaded(cid)
            self._efforts[cid] = value
            self._persist(cid)
        return True

    # ── 模型选择（按会话）────────────────────────────

    def get_model(self, conversation_id: str) -> str:
        """会话级模型；未选择时回落全局默认（空串 = 由 provider 的默认决定）。

        落盘持久化（与清单 / 模式 / 档位同一份会话状态文件）：刷新页面、
        乃至换一个进程，同一个会话选的都是同一个模型 —— 选择不能只活在内存里。
        """
        cid = str(conversation_id or "")
        with self._lock:
            self._ensure_loaded(cid)
            val = self._models.get(cid)
        return str(val or "").strip() or self.default_model

    def set_model(self, conversation_id: str, model: str) -> str:
        """设置会话级模型（空串 = 清除选择、回默认）；返回生效值。"""
        cid = str(conversation_id or "").strip()
        want = str(model or "").strip()
        if not cid:
            return self.default_model
        with self._lock:
            self._ensure_loaded(cid)
            if want:
                self._models[cid] = want
            else:
                self._models.pop(cid, None)
            self._persist(cid)
        return want or self.default_model

    # ── 内部：持久化──────────────────────────────
    #
    # 一个会话一份 JSON：`<state_dir>/<cid>.json`。模型 / 模式 / 档位 / 清单
    # 同住是因为生命周期完全一致（都按 cid、都随会话走），而不是因为它们同类。
    # 任一分量为空就不写这个键 —— 缺键即"回到默认"，不存空值；四项全空就删文件。
    #
    #   {"model": "...", "mode": "plan", "effort": "max",
    #    "todo": {"list_id": "...", "items": [...], "collapsed": false}}

    def _state_file(self, cid: str) -> Optional[Path]:
        if self._storage_dir is None or not _CID_RE.match(cid):
            return None
        return self._storage_dir / f"{cid}.json"

    def _ensure_loaded(self, cid: str) -> None:
        """懒加载会话状态（调用方持锁）；坏文件 / 缺字段忽略。

        `_state_loaded` 只跑一次：之后所有分量都在内存里，写盘可以直接整份重建。
        否则每次 `_persist` 都得先合并磁盘，反而更容易丢字段。

        读不出来就当"这个会话没有状态"：状态文件是选择的缓存，不是事实源，
        让它阻塞会话打开（或抛到回合里）比退回默认值更坏。因此这里只捕
        文件与解析两类异常，其余（例如内存分配失败）照常冒泡。
        """
        if cid in self._state_loaded:
            return
        self._state_loaded.add(cid)
        fp = self._state_file(cid)
        if fp is None or not fp.is_file():
            return
        raw: Any = None
        try:
            raw = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            # 判据见 docstring：坏文件按默认处理，不在这里伪装成成功读取。
            report_error("agent.mechanisms.live_state.LiveState._ensure_loaded", exc)
        if not isinstance(raw, dict):
            return
        todo = raw.get("todo")
        if isinstance(todo, dict) and "items" in todo:
            self._todos[cid] = dict(todo)
        model = str(raw.get("model") or "").strip()
        if model:
            self._models[cid] = model
        mode = str(raw.get("mode") or "").strip()
        if mode in _MODES and mode != "auto":
            self._modes[cid] = mode
        effort = str(raw.get("effort") or "").strip()
        if effort in ("high", "max"):
            self._efforts[cid] = effort

    def _persist(self, cid: str) -> None:
        """落盘（调用方持锁）；非法 cid / 无目录直接跳过，写失败留痕。

        写失败不冒泡：调用点在回合发包、工具调用与接口处理上，让磁盘错误
        打断一次对话得不偿失。但必须留痕 —— 否则用户以为"选上了"、重启后却
        回到默认，是最难查的一类缺陷。
        """
        fp = self._state_file(cid)
        if fp is None or self._storage_dir is None:
            return
        try:
            body: Dict[str, Any] = {}
            todo = self._todos.get(cid)
            if isinstance(todo, dict) and todo:
                body["todo"] = dict(todo)
            model = self._models.get(cid)
            if model:
                body["model"] = model
            mode = self._modes.get(cid)
            if mode:
                body["mode"] = mode
            effort = self._efforts.get(cid)
            if effort:
                body["effort"] = effort
            if not body:
                # 四个分量都空 = 这个会话没有状态了：删文件，不留空壳。
                if fp.exists():
                    fp.unlink()
                return
            self._storage_dir.mkdir(parents=True, exist_ok=True)
            fp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        except (OSError, TypeError, ValueError) as exc:
            report_error("live_state.persist", exc, conversation_id=cid)


# ── 交互式命令的 stdin 通道─────────────
#
# 场景：`run_command` 跑 winget / npm init 这类会停下来问话的命令时，
# 子进程在等 stdin。模型和宿主都推不动它 —— 只有人能回答。
#
# 数据流向（逐字段一致）：
#   前端输入 → `/api/chat/command-input` → `submit_command_input(key, text)`
#   → 把文本写进工具正在轮询的那个 `progress` dict 的 `_user_input`
#   → `run_command` 的轮询循环取出并写进子进程 stdin。
#
# 键是 `"{conversation_id}:{tool_call_id}"`：同一会话可能有多次命令调用，
# 用 tool_call_id 才能把输入投递给正在等的那一个。
_COMMAND_INPUT_LOCK = threading.Lock()
_COMMAND_INPUT_TARGETS: Dict[str, Dict[str, Any]] = {}


def register_command_input_target(key: str, progress: Dict[str, Any]) -> None:
    """登记一个"可以接受 stdin"的进度对象（命令开始执行时调用）。"""
    k = str(key or "").strip()
    if not k or not isinstance(progress, dict):
        return
    with _COMMAND_INPUT_LOCK:
        _COMMAND_INPUT_TARGETS[k] = progress


def unregister_command_input_target(key: str) -> None:
    """注销（命令结束时调用，避免把输入投给已经结束的调用）。"""
    k = str(key or "").strip()
    if not k:
        return
    with _COMMAND_INPUT_LOCK:
        _COMMAND_INPUT_TARGETS.pop(k, None)


def submit_command_input(key: str, text: str) -> bool:
    """向正在执行的 `run_command` 写入 stdin；没有在等输入的目标则返回 False。"""
    k = str(key or "").strip()
    if not k:
        return False
    with _COMMAND_INPUT_LOCK:
        progress = _COMMAND_INPUT_TARGETS.get(k)
    if not isinstance(progress, dict):
        return False
    progress["_user_input"] = str(text or "")
    return True


# ── 目标状态语义（`status`）─────────────────────────────────
#
#   - `active`：回合结束后自动用 `text` 触发新回合；
#   - `paused`：保留目标、停止自动触发（可 resume）；
#   - `done`：已达成，不再触发（终态，但保留记录以便查询）。
