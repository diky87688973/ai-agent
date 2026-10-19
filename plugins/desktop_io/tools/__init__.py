# -*- coding: utf-8 -*-
"""四个工具类的统一出口。"""
from .eye import DesktopEyeTool
from .keyboard import DesktopKeyboardTool
from .mouse import DesktopMouseTool
from .wait import DesktopWaitTool

__all__ = ["DesktopEyeTool", "DesktopKeyboardTool", "DesktopMouseTool",
           "DesktopWaitTool"]
