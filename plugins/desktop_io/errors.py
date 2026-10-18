# -*- coding: utf-8 -*-
"""桌面能力异常：不可用、缺权限、截屏失败、输入被占用。

四类都属于「这一次调用做不了」，由工具管道捕获成 `ok=false` 回灌。
文案带可执行的下一步：缺什么权限、哪个平台有实现、该用哪个 action。
"""
from __future__ import annotations


class DesktopError(RuntimeError):
    """桌面能力相关失败的基类。"""


class DesktopUnavailable(DesktopError):
    """平台没有实现、没有图形会话，或缺少必需依赖。"""


class DesktopPermissionDenied(DesktopUnavailable):
    """系统权限未授予（macOS 的屏幕录制与辅助功能）。"""


class ScreenCaptureFailed(DesktopUnavailable):
    """截屏 API 返回失败，或截图数据无法解码。"""


class DesktopBusy(DesktopError):
    """另一个输入动作持锁未结束。"""
