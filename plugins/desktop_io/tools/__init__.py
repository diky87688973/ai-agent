# -*- coding: utf-8 -*-
"""三个工具类的统一出口。"""
from .eye import DesktopEyeTool
from .keyboard import DesktopKeyboardTool
from .mouse import DesktopMouseTool

__all__ = ["DesktopEyeTool", "DesktopKeyboardTool", "DesktopMouseTool"]
