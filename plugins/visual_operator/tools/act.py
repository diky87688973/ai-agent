# -*- coding: utf-8 -*-
"""`desktop_act`：带断言的多步桌面管线。"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from agent.capabilities.registry import ToolPlugin
from agent.core.error_report import report_error
from agent.core.tool_call import ToolResult

from ..capture_store import CaptureStore
from ..config import DesktopConfig
from ..coords import ScreenRect
from ..guard import reject_in_plan
from ..input_lock import input_guard
from ..pipeline import destructive_hit, is_read_only, normalize_steps, run, sanitize
from ..ports import Backend
from ._params import as_int, choice, reject_unknown, require_range
from ._windows import window_target
from .app import DesktopAppTool
from .click_region import DesktopClickRegionTool
from .click_text import DesktopClickTextTool
from .eye import DesktopEyeTool
from .find import DesktopFindTool
from .keyboard import DesktopKeyboardTool
from .mouse import DesktopMouseTool
from .open import DesktopOpenTool
from .type_into import DesktopTypeIntoTool
from .wait import DesktopWaitTool
from .window import DesktopWindowTool

_FIELDS = ("steps", "on_error", "capture", "timeout_ms")
_ACTIONS = (
    "window", "app", "open", "find", "click_text", "type_into",
    "eye", "wait", "click", "click_region", "type", "key", "hotkey", "scroll",
)

class DesktopActTool(ToolPlugin):
    name = "desktop_act"
    label = "批量操作"
    icon = "🧩"
    description = (
        "按顺序执行多步桌面操作，每步可带 expect 断言；失败即停并返回步日志。"
        "步骤是 `{动词: 参数, expect: {...}}`，一次最多 12 步、60 秒。"
        "自绘控件优先 click_region / type_into；click / type 只用于已验证的坐标/输入控件。"
        "量外框必须用 eye annotated + grid_step=20，矩形带 capture_id + space=image。"
        "可用动词：window / app / open / find / click_text / click_region / type_into / eye / wait / "
        "click / type / key / hotkey / scroll。"
        "expect 支持 window / text / rect_contains / changed；命中关闭、删除、支付、购买、"
        "退订等目标文字时整体拒绝，要求逐条执行。"
        "Plan 模式只允许只读步骤。"
    )
    parameters = {
        "steps": {"type": "array", "items": {"type": "object"},
                  "description": "步骤数组，每步一个动作加可选 expect"},
        "on_error": {"type": "string", "enum": ["stop", "continue"],
                     "description": "失败策略；continue 只允许只读步骤"},
        "capture": {"type": "string", "enum": ["none", "failure", "final"],
                    "description": "回图策略：不回 / 失败帧 / 末帧"},
        "timeout_ms": {"type": "integer",
                       "description": "总超时 100–60000 毫秒（默认 30000）"},
    }

    def __init__(self, backend: Backend, config: DesktopConfig,
                 live_state: Any = None, captures: Any = None) -> None:
        self._backend = backend
        self._config = config
        self._live_state = live_state
        self._captures = captures if captures is not None else CaptureStore()
        self._history: List[Any] = []
        self._tools: Dict[str, Any] = {
            "window": DesktopWindowTool(backend, live_state),
            "app": DesktopAppTool(backend, live_state),
            "open": DesktopOpenTool(backend, live_state),
            "find": DesktopFindTool(backend),
            "click_text": DesktopClickTextTool(backend, live_state),
            "click_region": DesktopClickRegionTool(backend, live_state, self._captures),
            "type_into": DesktopTypeIntoTool(backend, config, live_state, self._captures),
            "eye": DesktopEyeTool(backend, config, live_state, self._captures),
            "wait": DesktopWaitTool(backend, config),
            "click": DesktopMouseTool(backend, config, live_state, self._captures),
            "type": DesktopKeyboardTool(backend, config, live_state, self._captures),
            "key": DesktopKeyboardTool(backend, config, live_state, self._captures),
            "hotkey": DesktopKeyboardTool(backend, config, live_state, self._captures),
            "scroll": DesktopMouseTool(backend, config, live_state, self._captures),
        }

    def execute(self, arguments: Dict[str, Any]) -> Any:
        reject_unknown(arguments, set(_FIELDS), action=self.name)
        self._history = []
        steps = normalize_steps(arguments.get("steps"))
        on_error = choice(arguments, "on_error", ("stop", "continue"), "stop")
        capture = choice(arguments, "capture", ("none", "failure", "final"), "none")
        timeout = require_range(as_int(arguments, "timeout_ms", 30000),
                                "timeout_ms", 100, 60000)
        if destructive_hit(steps):
            raise ValueError("批量命中破坏性目标文字；请逐条执行并让用户确认")
        read_only = all(is_read_only(verb, args) for verb, args, _expect in steps)
        if not read_only:
            reject_in_plan(self._live_state, "桌面批量操作")
        if on_error == "continue" and not read_only:
            raise ValueError("on_error=continue 只允许只读步骤")
        with input_guard():
            result = run(steps, self._execute, self._assert_step,
                         timeout_ms=timeout, on_error=on_error)
        data = {
            "ok": result.ok,
            "steps": result.steps,
            "failed_step": result.failed_step,
            "error": result.error,
            "count": len(result.steps),
        }
        if result.data is not None:
            data["last"] = sanitize(result.data)
        if capture != "none" and (capture == "final" and result.ok or
                                  capture == "failure" and not result.ok):
            shot = self._capture()
            if shot is not None:
                data, attachments = shot
                data.update({"ok": result.ok, "steps": result.steps,
                             "failed_step": result.failed_step, "error": result.error,
                             "count": len(result.steps), "capture": capture})
                return ToolResult.attach(data, attachments)
        return data

    def _execute(self, verb: str, arguments: Dict[str, Any]) -> Any:
        if verb not in self._tools:
            raise ValueError(f"未知动作 {verb}；可用 {', '.join(_ACTIONS)}")
        tool = self._tools[verb]
        args = self._resolve(dict(arguments))
        if verb == "wait":
            if "ms" in args and "timeout_ms" not in args:
                args["timeout_ms"] = args.pop("ms")
            args.setdefault("until", "change")
        elif verb == "click":
            args["action"] = "click"
        elif verb in ("type", "key", "hotkey"):
            args["action"] = verb
        elif verb == "scroll":
            args["action"] = "scroll"
        result = tool.execute(args)
        payload = result.data if isinstance(result, ToolResult) else result
        self._history.append(payload)
        return result

    def _resolve(self, value: Any) -> Any:
        """解析 `$<step>.<field>` 引用；只读前一步的返回值，不抄坐标。"""
        if isinstance(value, dict):
            return {key: self._resolve(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._resolve(item) for item in value]
        if not isinstance(value, str) or not value.startswith("$"):
            return value
        parts = value[1:].split(".")
        try:
            index = int(parts[0])
            current: Any = self._history[index - 1]
        except (ValueError, IndexError):
            raise ValueError(f"变量引用无效：{value}")
        for part in parts[1:]:
            if isinstance(current, list):
                try:
                    current = current[int(part)]
                except (ValueError, IndexError):
                    raise ValueError(f"变量引用越界：{value}") from None
            elif isinstance(current, dict):
                if part not in current:
                    raise ValueError(f"变量字段不存在：{value}")
                current = current[part]
            else:
                raise ValueError(f"变量路径不可读：{value}")
        return current

    def _assert_step(self, expect: Dict[str, Any],
                     data: Any) -> Tuple[bool, Dict[str, Any]]:
        timeout = 3000
        if "timeout_ms" in expect:
            timeout = require_range(as_int(expect, "timeout_ms", 3000),
                                    "timeout_ms", 100, 60000)
        started = time.monotonic()
        detail: Dict[str, Any] = {}
        while True:
            passed, detail = self._check_once(expect, data)
            if passed or (time.monotonic() - started) * 1000 >= timeout:
                return passed, detail
            time.sleep(0.1)

    def _check_once(self, expect: Dict[str, Any], data: Any) -> Tuple[bool, Dict[str, Any]]:
        unknown = set(expect) - {"window", "text", "rect_contains", "changed",
                                 "timeout_ms", "match"}
        if unknown:
            return False, {"error": f"未知 expect 字段：{', '.join(sorted(unknown))}"}
        detail: Dict[str, Any] = {}
        window = str(expect.get("window") or "").strip()
        title = window or None
        if window:
            try:
                _target, _matched = window_target(self._backend, {"window": window})
                detail["window"] = window
            except ValueError as exc:
                return False, {"error": str(exc), "window": window}
        if "text" in expect:
            locator = self._backend.locator
            if locator is None:
                return False, {"error": "当前平台没有 UIA 文本定位"}
            hwnd = None
            if title:
                try:
                    target, _ = window_target(self._backend, {"window": title})
                    hwnd = target.hwnd if target is not None else None
                except ValueError as exc:
                    report_error("plugin.visual_operator.act.expect_window", exc)
                    hwnd = None
            text = str(expect.get("text") or "")
            match = str(expect.get("match") or "contains")
            rows = list(locator.find(hwnd, text, match, 50))
            detail["text"] = text
            detail["count"] = len(rows)
            if not rows:
                return False, detail
        if "rect_contains" in expect:
            point = expect.get("rect_contains") or {}
            try:
                from ..coords import ScreenPoint
                want = ScreenPoint(int(point["x"]), int(point["y"]))
            except (KeyError, TypeError, ValueError):
                return False, {"error": "rect_contains 需要 {x, y}"}
            detail["rect_contains"] = want.to_dict()
            rows = []
            if isinstance(data, dict):
                rows = data.get("matches") or []
            if not any(isinstance(row, dict) and
                       ScreenRect(int(row["rect"]["x"]), int(row["rect"]["y"]),
                                  int(row["rect"]["width"]), int(row["rect"]["height"])).contains(want)
                       for row in rows):
                return False, detail
        if "changed" in expect:
            actual = data.get("changed") if isinstance(data, dict) else None
            detail["changed"] = actual
            if actual is None:
                return False, {"error": "该动作没有 changed 证据"}
            if bool(expect.get("changed")) and not float(actual) > 0:
                return False, detail
        return True, detail

    def _capture(self) -> Optional[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
        try:
            result = self._tools["eye"].execute({"grid": True})
        except Exception as exc:
            report_error("plugin.visual_operator.act.capture", exc)
            return None
        if isinstance(result, ToolResult):
            return dict(result.data or {}), list(result.attachments or [])
        return dict(result or {}), []
