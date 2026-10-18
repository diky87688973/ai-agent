# -*- coding: utf-8 -*-
"""任务与目标工具组：run_type / todo_list / user_confirm / task_sleep / goal。

`approval_confirm` 类在本文件，`build_plugins` 不返回它。

- run_type / todo_list：读写 LiveState（会话作用域经 core.session_scope 取 conversation_id）；
- user_confirm：两段式——首段抛 UserConfirmRequired（ok=False + data 信封），次段回填 confirm；
- approval_confirm：抛 ApprovalRequired 后停下，等用户同意或驳回；通行证由宿主签发；
- task_sleep / goal：校验 + 数据信封 + 会话状态记录（宿主循环按目标状态决定是否续跑）。
"""
from __future__ import annotations

import re
import sys
import uuid
from typing import Any, Dict, List, Optional

from agent.capabilities.registry import ToolPlugin
from agent.core.session_scope import current_session_id
from agent.mechanisms.live_state import GoalError, LiveState


class UserConfirmRequired(Exception):
    """待确认信封：结构化 data（title / confirms 等）随 ToolResult.data 透传。

    `await_user=True` 告诉回合循环："这一轮到此为止，等用户在宿主界面上作答"。
    没有这个标记，模型会把 `ok=False` 读成工具失败并反复重试，直到步数上限。
    """

    await_user = True

    def __init__(
        self,
        title: str,
        confirms: List[str],
        multi: bool = False,
        custom_option_index: Optional[int] = None,
    ) -> None:
        super().__init__("需由宿主展示选项并由用户确认；确认后携带 confirm 再次调用")
        self.data: Dict[str, Any] = {"title": title, "confirms": list(confirms)}
        if multi:
            self.data["multi"] = True
        if custom_option_index is not None:
            self.data["custom_option_index"] = int(custom_option_index)


class ApprovalRequired(Exception):
    """待审批信封。`option_id` 与 `option_desc` 在 ToolResult.data 里。

    `await_user=True`，回合在此停下，等宿主界面上的同意或驳回。
    """

    await_user = True

    def __init__(self, option_id: str, option_desc: str) -> None:
        super().__init__("需由宿主展示审批并由用户同意或驳回")
        self.data: Dict[str, Any] = {
            "kind": "approval",
            "title": "审批",
            "option_id": option_id,
            "option_desc": option_desc,
        }


def _approval_text(raw: Any, name: str, limit: int) -> str:
    """审批入参：非空字符串。超过上限时拒绝。"""
    if not isinstance(raw, str):
        raise ValueError(f"{name} 须为非空字符串")
    text = raw.strip()
    if not text:
        raise ValueError(f"{name} 须为非空字符串")
    if len(text) > limit:
        raise ValueError(f"{name} 最长 {limit} 字符")
    return text


def _normalize_confirms(raw: Any) -> List[str]:
    """confirms 校验：非空字符串数组、逐项非空白。"""
    if not isinstance(raw, list) or len(raw) < 1:
        raise ValueError("confirms 须为非空字符串数组")
    out: List[str] = []
    for i, x in enumerate(raw):
        if not isinstance(x, str) or not x.strip():
            raise ValueError(f"confirms[{i}] 须为非空字符串")
        out.append(x)
    return out


def _interactive_resolve(title: str, confirms: List[str]) -> str:
    """TTY 交互解析：编号取对应项，否则自由输入原样返回。"""
    print(title, file=sys.stderr)
    for i, c in enumerate(confirms, start=1):
        print(f"  [{i}] {c}", file=sys.stderr)
    print("输入编号或自由输入：", file=sys.stderr)
    line = sys.stdin.readline()
    if not line:
        raise ValueError("未读取到用户输入")
    s = line.strip()
    if not s:
        raise ValueError("输入为空")
    if re.fullmatch(r"\d+", s):
        idx = int(s)
        if 1 <= idx <= len(confirms):
            return confirms[idx - 1]
    return s


class RunTypeTool(ToolPlugin):
    """查询 / 切换会话运行模式。"""

    name = "run_type"
    label = "切换运行模式"
    icon = "🎛️"
    description = "查询或切换会话运行模式（auto / plan / execute）；不传 `run_type` 为查询当前模式。"
    parameters = {
        "run_type": {"type": "string", "description": "auto / plan / execute；缺省为查询"},
    }

    def __init__(self, live_state: LiveState) -> None:
        self._state = live_state

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        cid = current_session_id()
        if not cid:
            raise ValueError("run_type 须由宿主注入 conversation_id 后执行；禁止无会话上下文直调")
        rt = str(arguments.get("run_type") or "").strip().lower()
        if not rt or rt not in ("auto", "plan", "execute"):
            return {"run_type": self._state.get_mode(cid), "action": "query"}
        return {"run_type": self._state.set_mode(cid, rt), "action": "switch"}


class TodoListTool(ToolPlugin):
    """会话执行清单。"""

    name = "todo_list"
    label = "待办清单"
    icon = "☑️"
    description = "会话待办清单：`action=create / check / uncheck / add_item / remove_item / replace_item / collapse / close / query`。"
    parameters = {
        "action": {
            "type": "string",
            "description": "create / check / uncheck / add_item / remove_item / replace_item / collapse / close / query",
        },
        "items": {"type": "array", "description": "create：非空数组（字符串或 {text, done} 对象）"},
        "indices": {"type": "array", "description": "check / uncheck：下标（int 或非空 int 数组）"},
        "item_index": {"type": "integer", "description": "add_item / remove_item / replace_item 的下标"},
        "text": {"type": "string", "description": "add_item / replace_item 的文本"},
    }

    def __init__(self, live_state: LiveState) -> None:
        self._state = live_state

    @staticmethod
    def _progress(items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """清单进度：done 计数 + 是否全部完成。

        全部完成时清单左边框转绿并给一个关闭键——那是"可以收工了"的信号，
        所以这个字段必须由服务端给出，而不是让每个前端各算一遍。
        """
        total = len(items)
        done = sum(1 for item in items if item.get("done"))
        return {"done_count": done, "total_count": total,
                "all_done": bool(total) and done == total}

    @staticmethod
    def _normalize_items(parsed: Any) -> List[Dict[str, Any]]:
        if not isinstance(parsed, list) or not parsed:
            raise ValueError("items 必须为非空数组")
        items: List[Dict[str, Any]] = []
        for i, it in enumerate(parsed):
            if isinstance(it, dict) and "text" in it:
                items.append({"text": str(it["text"]).strip(), "done": bool(it.get("done", False))})
            elif isinstance(it, str) and it.strip():
                items.append({"text": it.strip(), "done": False})
            else:
                raise ValueError(f"items[{i}] 须为非空字符串或 {{text, done}} 对象")
        return items

    @staticmethod
    def _as_int_list(value: Any, label: str) -> List[int]:
        if value is None:
            raise ValueError(f"缺少 {label}")
        if isinstance(value, int):
            return [value]
        if isinstance(value, list):
            if not value:
                raise ValueError(f"{label} 须为非空整数数组")
            out: List[int] = []
            for x in value:
                try:
                    out.append(int(x))
                except (TypeError, ValueError):
                    raise ValueError(f"{label} 须为 int 或非空 int 数组")
            return out
        raise ValueError(f"{label} 须为 int 或非空 int 数组")

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        cid = current_session_id()
        if not cid:
            raise RuntimeError("todo_list 须由宿主传入 conversation_id")
        action = str(arguments.get("action") or "").strip().lower()
        if not action:
            raise ValueError("缺少 action")
        if action == "create":
            raw = arguments.get("items")
            if not isinstance(raw, list):
                raise ValueError("create 需要 items（字符串数组或对象数组）")
            items = self._normalize_items(raw)
            lid = uuid.uuid4().hex[:12]
            data: Dict[str, Any] = {"list_id": lid, "items": items, "collapsed": False,
                                    **self._progress(items)}
            self._state.set_todo(cid, data)
            return data
        if action == "query":
            todo = self._state.get_todo(cid)
            return list(todo["items"]) if todo else None
        todo = self._state.get_todo(cid)
        if todo is None:
            raise ValueError("当前对话无活跃清单，请先用 create")
        if action in ("check", "uncheck"):
            indices = self._as_int_list(arguments.get("indices"), "indices")
            for idx in indices:
                if idx < 0 or idx >= len(todo["items"]):
                    raise IndexError(f"indices 含越界下标 {idx}，共 {len(todo['items'])} 项")
            for idx in indices:
                todo["items"][idx]["done"] = action == "check"
            self._state.set_todo(cid, todo)
            key = "checked" if action == "check" else "unchecked"
            return {
                "list_id": todo["list_id"],
                "items": todo["items"],
                key: indices,
                **self._progress(todo["items"]),
            }
        if action == "add_item":
            text = str(arguments.get("text") or "").strip()
            if not text:
                raise ValueError("add_item 需要 text")
            item = {"text": text, "done": False}
            ins = arguments.get("item_index")
            if ins is not None and isinstance(ins, int) and 0 <= ins <= len(todo["items"]):
                todo["items"].insert(ins, item)
            else:
                todo["items"].append(item)
            self._state.set_todo(cid, todo)
            return {"list_id": todo["list_id"], "items": todo["items"]}
        if action in ("remove_item", "replace_item"):
            raw_ix = arguments.get("item_index")
            if raw_ix is None:
                raise ValueError(f"{action} 需要 item_index（int）")
            try:
                ix = int(raw_ix)
            except (TypeError, ValueError):
                raise ValueError(f"{action} 需要 item_index（int）")
            if ix < 0 or ix >= len(todo["items"]):
                raise IndexError(f"item_index {ix} 越界，共 {len(todo['items'])} 项")
            if action == "remove_item":
                todo["items"].pop(ix)
            else:
                text = str(arguments.get("text") or "").strip()
                if not text:
                    raise ValueError("replace_item 需要 text")
                todo["items"][ix]["text"] = text
            self._state.set_todo(cid, todo)
            return {"list_id": todo["list_id"], "items": todo["items"],
                    **self._progress(todo["items"])}
        if action == "collapse":
            todo["collapsed"] = not todo.get("collapsed", False)
            self._state.set_todo(cid, todo)
            return {"list_id": todo["list_id"], "items": todo["items"],
                    "collapsed": todo["collapsed"], **self._progress(todo["items"])}
        if action == "close":
            self._state.set_todo(cid, None)
            return {"close": True}
        raise ValueError(f"未知 action: {action}")


class UserConfirmTool(ToolPlugin):
    """用户分岔确认：两段式信封。"""

    name = "user_confirm"
    label = "等待确认"
    icon = "⚠️"
    description = "向用户发起分岔确认：首段提交 title + confirms 选项（返回待确认信封）；用户确认后携带 confirm 再次调用回填。"
    parameters = {
        "title": {"type": "string", "description": "标题（首段必填）"},
        "confirms": {"type": "array", "description": "候选项（首段必填；非空字符串数组）"},
        "confirm": {"type": "string", "description": "用户确认结果（次段传入）"},
        "multi": {"type": "boolean", "description": "是否支持多选（透传给宿主）"},
        "custom_option_index": {"type": "integer", "description": "自由输入绑定的选项下标（可选）"},
        "interactive": {"type": "boolean", "description": "TTY 下直接交互解析（默认 false）"},
        "confirm_id": {"type": "string", "description": "宿主确认单 ID（次段回显）"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        confirm = arguments.get("confirm")
        if confirm is not None:
            confirm_id = str(arguments.get("confirm_id") or "")
            result: Dict[str, Any] = {"confirm": str(confirm)}
            if confirm_id:
                result["confirm_id"] = confirm_id
            return result
        if arguments.get("confirms") is None:
            raise ValueError("须提供 confirms（非空字符串数组）")
        confirms = _normalize_confirms(arguments.get("confirms"))
        custom_index = arguments.get("custom_option_index")
        if custom_index is not None:
            cix = int(custom_index)
            if cix < 0 or cix >= len(confirms):
                raise ValueError("custom_option_index 须满足 0 <= i < len(confirms)")
        title = str(arguments.get("title") or "").strip()
        if not title:
            raise ValueError("首次发起须提供 title")
        if bool(arguments.get("interactive", False)):
            # interactive 只在真 TTY 下有意义。Web / 无头环境下 stdin 不是 TTY，
            # 若继续走交互分支会以"未读取到用户输入"失败——那是照做不了的错。
            # 这里给模型一条可执行的指引：改用两段式信封，交互由宿主 UI 完成。
            if not sys.stdin.isatty():
                raise ValueError(
                    "当前环境没有 TTY，interactive 模式不可用；"
                    "请去掉 interactive，改用两段式信封（首段只传 title + confirms，"
                    "宿主会把候选项呈现给用户，用户在界面上选择后你会在下一轮拿到结果）"
                )
            return {"confirm": _interactive_resolve(title, confirms)}
        raise UserConfirmRequired(
            title,
            confirms,
            multi=bool(arguments.get("multi", False)),
            custom_option_index=custom_index,
        )


class ApprovalConfirmTool(ToolPlugin):
    """操作审批。调用后挂起，等用户同意或驳回。

    同意时宿主把 `approval_id` 写入这次调用的结果，并在会话上下文记下
    `approval_id` → `option_id`。本工具没有回填入参。
    """

    name = "approval_confirm"
    label = "审批"
    icon = "🛂"
    description = (
        "向用户发起审批。入参为 option_id（需要放行的工具给出的操作 ID）"
        "和 option_desc（弹窗正文）。调用后挂起，等用户点同意或驳回。"
        "驳回的结果是「不同意」。同意的结果是「同意」，并带有宿主签发的 approval_id。"
        "approval_id 写在这次调用的结果里。再次调用本工具不会回填。"
    )
    parameters = {
        "option_id": {"type": "string", "description": "操作 ID，由需要审批的工具给出"},
        "option_desc": {"type": "string", "description": "弹窗正文，一句简短问话"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if str(arguments.get("approval_id") or "").strip():
            raise ValueError(
                "approval_id 由宿主在用户同意后写入这次调用的结果。"
                "本工具不接收 approval_id。"
            )
        option_id = _approval_text(arguments.get("option_id"), "option_id", 200)
        option_desc = _approval_text(arguments.get("option_desc"), "option_desc", 500)
        raise ApprovalRequired(option_id, option_desc)


class TaskSleepTool(ToolPlugin):
    """自主休眠指令：校验 + 信封 + 会话状态记录。"""

    name = "task_sleep"
    label = "等待一段时间"
    icon = "⏱️"
    description = "暂停自主执行：宿主停止自动激活，N 秒后携提醒重新激活（1~86400 秒）。"
    parameters = {
        "seconds": {"type": "integer", "description": "休眠秒数（1~86400）"},
        "reminder": {"type": "string", "description": "唤醒提醒（≤500 字符，超出截断）"},
    }

    def __init__(self, live_state: LiveState) -> None:
        self._state = live_state

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw = arguments.get("seconds")
        seconds = 0
        if isinstance(raw, (int, float, str)):
            try:
                seconds = int(raw)
            except (TypeError, ValueError):
                seconds = 0
            if seconds <= 0:
                seconds = 0
        if seconds < 1 or seconds > 86400:
            raise ValueError(f"seconds 必须在 1~86400 之间，收到 {seconds}")
        reminder = arguments.get("reminder", "")
        if not isinstance(reminder, str):
            reminder = str(reminder)
        if len(reminder) > 500:
            reminder = reminder[:500]
        cid = current_session_id()
        if cid:
            self._state.set_sleep(cid, seconds, reminder)
        return {"action": "sleep", "seconds": seconds, "reminder": reminder}


class GoalTool(ToolPlugin):
    """目标（Goal）：可编辑的自主续跑任务对象。

    与"自主模式"同一机制 —— 回合结束后自动再发一条 user 输入；
    区别是那条输入就是这里的目标文案，所以自动续跑有了方向，也能随时改写。

    `active` 的目标会在每轮结束后持续触发；`paused` 保留但不触发；
    `done` 是终态。触发文案由用户或模型任一方设定。
    """

    name = "goal"
    label = "目标"
    icon = "🎯"
    description = (
        "管理本会话的目标文案。目标处于 active 时，每轮结束后系统会自动用该文案"
        "发起新一轮，直到你用 action=pause/done 停下。"
        "action: create=新建或整体改写；get=查询；update=局部改（文案/状态/备注）；"
        "pause=暂停触发；resume=恢复触发；done=标记达成；delete=删除。"
        "不要每轮都调 get 自查：自动触发的那一轮里，目标文案本身就是发来的消息，"
        "你不需要再查一次；只在用户问起目标状态、或你要动手改它之前查一次。"
    )
    parameters = {
        "action": {"type": "string",
                   "description": "create / get / update / pause / resume / done / delete"},
        "text": {"type": "string", "description": "目标文案（create 必填；update 可改）"},
        "note": {"type": "string", "description": "备注（可选，给人看）"},
        "status": {"type": "string", "description": "update 时的状态：active / paused / done"},
    }

    def __init__(self, live_state: LiveState) -> None:
        self._state = live_state

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """按 `action` 管理目标；返回扁平 dict（与 todo_list 等同约定）。

        参数错误一律 `raise ValueError` —— 管线会把它翻成 `ok=False` 的结果回灌给模型，
        比返回 `{"ok": False, ...}` 更直接：后者会被裹成 `data`，模型看到的是嵌套信封。
        """
        action = str(arguments.get("action") or "get").strip().lower()
        text = str(arguments.get("text") or "").strip()
        note = str(arguments.get("note") or "").strip()
        status = str(arguments.get("status") or "").strip().lower()
        cid = current_session_id()
        if not cid:
            raise RuntimeError("goal 须由宿主传入 conversation_id")
        try:
            if action == "create":
                return {"goal": self._state.set_goal(cid, text, note=note)}
            if action == "get":
                return {"goal": self._state.get_goal(cid)}
            if action == "update":
                return {"goal": self._state.update_goal(cid, text=text, status=status, note=note)}
            if action == "pause":
                return {"goal": self._state.update_goal(cid, status="paused")}
            if action == "resume":
                return {"goal": self._state.update_goal(cid, status="active")}
            if action == "done":
                return {"goal": self._state.update_goal(cid, status="done")}
            if action == "delete":
                return {"deleted": bool(self._state.delete_goal(cid))}
        except GoalError as exc:
            # 目标的语义错误（没有目标 / 空文案 / 非法状态）是可纠正的参数问题，
            # 交给管线回灌成 ok=False，模型看得到原因并自己改。
            raise ValueError(str(exc)) from exc
        raise ValueError(f"未知 action：{action}")


def build_plugins(live_state: LiveState) -> List[ToolPlugin]:
    """构造本组工具（run_type / todo_list / user_confirm / task_sleep / goal）。"""
    return [
        RunTypeTool(live_state),
        TodoListTool(live_state),
        UserConfirmTool(),
        TaskSleepTool(live_state),
        GoalTool(live_state),
    ]
