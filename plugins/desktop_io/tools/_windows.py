# -*- coding: utf-8 -*-
"""`window` / `hwnd` 参数的解析与前置激活。

eye 用它决定"看哪个窗口"，手部动作用它决定"先把谁叫到前台"，
截图与回执也共用同一份候选清单：同名窗口不止一个时，
「选了哪个、还有哪些」必须由一处产出，不能各写一套。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence, Tuple

from ..errors import DesktopError, DesktopUnavailable
from ..ports import Backend, WindowInfo
from ._params import as_int, has

WINDOW_FIELDS = ("window", "hwnd")

#: 回执里最多列几个同名候选：只列够模型做判断的数量，不把整串窗口塞进上下文。
MAX_CANDIDATES = 4


def window_candidates(backend: Backend,
                      arguments: Dict[str, Any]) -> Tuple[Sequence[WindowInfo], int]:
    """解析 `window` / `hwnd`，返回 (候选窗口, 命中数)；都没给返回 ((), 0)。

    `hwnd` 只有精确一个；`window` 返回后端排好序的全部候选
    （前台 → Z 序 → 面积），调用侧永远用第 0 个，其余只用于回执说明。
    """
    wants_hwnd = has(arguments, "hwnd")
    wants_title = has(arguments, "window")
    if not wants_hwnd and not wants_title:
        return (), 0
    if wants_hwnd and wants_title:
        raise ValueError("window 与 hwnd 二选一，不要同时给")
    port = backend.windows
    if port is None:
        raise DesktopUnavailable(
            "当前平台不支持按窗口操作；改用 x / y / width / height 的屏幕坐标"
        )
    if wants_hwnd:
        hwnd = as_int(arguments, "hwnd", 0)
        if hwnd <= 0:
            raise ValueError("hwnd 必须是正整数")
        return (port.get(hwnd),), 1
    title = str(arguments.get("window") or "").strip()
    if not title:
        raise ValueError("window 需要非空的标题片段")
    candidates = tuple(port.find(title))
    if not candidates:
        raise ValueError(f"没有标题包含「{title}」的可见窗口；先确认应用已启动")
    return candidates, len(candidates)


def window_target(backend: Backend,
                  arguments: Dict[str, Any]) -> Tuple[Optional[WindowInfo], int]:
    """解析 `window` / `hwnd`，返回 (目标窗口, 命中数)；都没给返回 (None, 0)。"""
    candidates, matched = window_candidates(backend, arguments)
    return (candidates[0] if candidates else None), matched


def alternatives(candidates: Sequence[WindowInfo]) -> list:
    """同名候选里除第 0 个之外的其余窗口：给模型一个改指定 `hwnd` 的入口。"""
    return [
        {
            "hwnd": info.hwnd,
            "rect": info.rect.to_dict(),
            "foreground": info.foreground,
        }
        for info in tuple(candidates)[1:1 + MAX_CANDIDATES]
    ]


def focus_target(backend: Backend, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """给了窗口参数就先置前，等价于人点任务栏；没给返回 None。

    抢不到前台不在这里抛错：先把回执交出去，由调用侧决定是继续还是换路径。
    """
    candidates, matched = window_candidates(backend, arguments)
    if not candidates:
        return None
    target = candidates[0]
    activation = backend.windows.activate(target.hwnd)
    receipt = activation.to_dict()
    if matched > 1:
        receipt["matched"] = matched
        receipt["alternatives"] = alternatives(candidates)
    return receipt


def require_active(receipt: Optional[Dict[str, Any]], action: str) -> None:
    """输入类动作的前置断言：目标必须真的拿到了前台。

    输入是"打给当前前台"的：前台没换过去，字就会落进别的窗口。
    这里宁可当场报错，也不让一次盲打把宿主聊天框写脏。
    """
    if receipt is None or receipt.get("active"):
        return
    foreground = receipt.get("foreground") or "未知窗口"
    raise DesktopError(
        f"{action} 的目标「{receipt.get('title')}」没有拿到前台，当前前台是「{foreground}」；"
        "本次输入没有投递，避免打进别的窗口。先确认该窗口未被系统禁止置前，再重试"
    )
