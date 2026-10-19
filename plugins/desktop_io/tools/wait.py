# -*- coding: utf-8 -*-
"""`desktop_wait`：等一个可观测的条件成立，而不是盲睡固定秒数。

盲睡的代价是双份的：睡短了要再来一轮，睡长了白等。更糟的是它把
"界面到底变了没有"变成了模型的猜测。这里把等待变成条件：
画面某块变了，或者某个窗口出现了 / 消失了，满足就立刻返回。
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from agent.capabilities.registry import ToolPlugin

from ..config import DesktopConfig
from ..coords import ScreenRect
from ..diff import change_ratio
from ..errors import DesktopUnavailable
from ..ports import Backend, WindowInfo
from ._capture import region_from_arguments
from ._params import as_int, as_text, choice, has, reject_unknown, require_range

_UNTIL = ("change", "window_appears", "window_disappears")

_FIELDS = ("until", "window", "hwnd", "x", "y", "width", "height",
           "timeout_ms", "interval_ms", "threshold")


class DesktopWaitTool(ToolPlugin):
    """等条件成立。"""

    name = "desktop_wait"
    label = "等待"
    icon = "⏳"
    description = (
        "等桌面出现可观测的变化，满足条件立即返回（不是盲睡）。"
        "until=change：等指定区域或指定窗口的画面变化超过 threshold；"
        "until=window_appears / window_disappears：等标题包含 window 的窗口出现或消失。"
        "超时不算错误：返回 satisfied=false，由你决定换动作还是延长等待。"
        "典型用法：等预告播完、等加载完成、等弹窗消失，不要用 task_sleep 猜秒数。"
        "Plan 模式下可用（只读）。"
    )
    parameters = {
        "until": {"type": "string", "enum": list(_UNTIL),
                  "description": "change 画面变化 / window_appears 窗口出现 / window_disappears 窗口消失"},
        "window": {"type": "string",
                   "description": "窗口标题片段；change 时用来限定取图范围，window_* 时是必填"},
        "hwnd": {"type": "integer", "description": "窗口句柄；与 window 二选一"},
        "x": {"type": "integer", "description": "区域左上角 x（屏幕坐标）；与 y/width/height 同时给出"},
        "y": {"type": "integer", "description": "区域左上角 y（屏幕坐标）"},
        "width": {"type": "integer", "description": "区域宽度（屏幕坐标）"},
        "height": {"type": "integer", "description": "区域高度（屏幕坐标）"},
        "timeout_ms": {"type": "integer", "description": "最长等待毫秒数 50–60000（默认 10000）"},
        "interval_ms": {"type": "integer", "description": "轮询间隔 50–2000 毫秒；缺省取插件配置"},
        "threshold": {"type": "number",
                      "description": "change 的判定阈值 0–1（默认 0.02）；越小越敏感"},
    }

    def __init__(self, backend: Backend, config: DesktopConfig) -> None:
        self._backend = backend
        self._config = config

    def execute(self, arguments: Dict[str, Any]) -> Any:
        reject_unknown(arguments, set(_FIELDS), action=self.name)
        until = choice(arguments, "until", _UNTIL)
        timeout_ms = require_range(
            as_int(arguments, "timeout_ms", 10000), "timeout_ms", 50, 60000)
        interval_ms = require_range(
            as_int(arguments, "interval_ms", self._config.wait_interval_ms),
            "interval_ms", 50, 2000)
        threshold = _threshold(arguments)

        if until == "change":
            return self._wait_change(arguments, timeout_ms, interval_ms, threshold)
        title = _title(arguments)
        return self._wait_window(arguments, until, title, timeout_ms, interval_ms)

    def _wait_change(self, arguments: Dict[str, Any], timeout_ms: int,
                     interval_ms: int, threshold: float) -> Dict[str, Any]:
        region = region_from_arguments(arguments, self._backend.screen.geometry().rect)
        if region is None:
            region = self._window_region(arguments)
        baseline = self._backend.screen.capture(region).png
        started = time.monotonic()
        deadline = started + timeout_ms / 1000.0
        latest = 0.0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(interval_ms / 1000.0, remaining))
            latest = change_ratio(baseline, self._backend.screen.capture(region).png) or 0.0
            if latest >= threshold:
                return {
                    "until": "change",
                    "satisfied": True,
                    "waited_ms": _elapsed_ms(started),
                    "changed": latest,
                    "threshold": threshold,
                    "capture": region.to_dict() if region else None,
                }
        return {
            "until": "change",
            "satisfied": False,
            "waited_ms": _elapsed_ms(started),
            "changed": latest,
            "threshold": threshold,
            "capture": region.to_dict() if region else None,
            "note": f"等待 {timeout_ms} 毫秒内画面变化没到阈值 {threshold}；"
                    "可以降低 threshold，或先确认目标区域是否真的会动",
        }

    def _wait_window(self, arguments: Dict[str, Any], until: str, title: str,
                     timeout_ms: int, interval_ms: int) -> Dict[str, Any]:
        port = self._backend.windows
        if port is None:
            raise DesktopUnavailable(
                "当前平台不支持按窗口操作；改用 until=change 等画面变化"
            )
        want = until == "window_appears"
        started = time.monotonic()
        deadline = started + timeout_ms / 1000.0
        while True:
            found = tuple(port.find(title))
            if bool(found) == want:
                result: Dict[str, Any] = {
                    "until": until,
                    "satisfied": True,
                    "waited_ms": _elapsed_ms(started),
                }
                if found:
                    result["window"] = found[0].to_dict()
                    if len(found) > 1:
                        result["window"]["matched"] = len(found)
                return result
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return {
                    "until": until,
                    "satisfied": False,
                    "waited_ms": _elapsed_ms(started),
                    "note": f"等待 {timeout_ms} 毫秒后标题包含「{title}」的窗口"
                            f"仍然{'不存在' if want else '存在'}",
                }
            time.sleep(min(interval_ms / 1000.0, remaining))

    def _window_region(self, arguments: Dict[str, Any]):
        """把窗口矩形当成取图区域：只比这块画面，不受别的窗口干扰。"""
        if not (has(arguments, "window") or has(arguments, "hwnd")):
            return None
        port = self._backend.windows
        if port is None:
            raise DesktopUnavailable(
                "当前平台不支持按窗口操作；改用 x / y / width / height 指定区域"
            )
        if has(arguments, "hwnd"):
            return self._usable_rect(port.get(as_int(arguments, "hwnd", 0)))
        found = tuple(port.find(_title(arguments)))
        if not found:
            raise ValueError(
                f"没有标题包含「{_title(arguments)}」的可见窗口；先确认应用已启动")
        return self._usable_rect(found[0])

    @staticmethod
    def _usable_rect(info: WindowInfo) -> ScreenRect:
        """最小化窗口的矩形是 (-32000,...)：等这块区域只会白等到超时。"""
        if info.minimized:
            raise ValueError(
                f"窗口 {info.hwnd} 已最小化，屏幕上没有它的画面；"
                "先用 desktop_eye(window=...) 恢复，"
                "或改用 x / y / width / height 指定区域")
        return info.rect


def _title(arguments: Dict[str, Any]) -> str:
    if not has(arguments, "window"):
        raise ValueError("until=window_appears / window_disappears 需要 window 标题片段")
    return as_text(arguments, "window").strip()


def _threshold(arguments: Dict[str, Any]) -> float:
    raw = arguments.get("threshold", 0.02)
    if isinstance(raw, bool):
        raise ValueError("threshold 必须是数字")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"threshold 必须是数字，实际 {raw!r}") from None
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"threshold 取值 0–1，实际 {value}")
    return value


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
