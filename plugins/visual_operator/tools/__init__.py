# -*- coding: utf-8 -*-
"""视觉操作工具类的统一出口。"""
from .act import DesktopActTool
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

__all__ = ["DesktopActTool", "DesktopAppTool", "DesktopClickRegionTool", "DesktopClickTextTool", "DesktopEyeTool",
           "DesktopFindTool", "DesktopKeyboardTool", "DesktopMouseTool",
           "DesktopOpenTool", "DesktopTypeIntoTool", "DesktopWaitTool",
           "DesktopWindowTool"]
