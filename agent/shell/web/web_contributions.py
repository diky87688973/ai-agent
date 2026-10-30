# -*- coding: utf-8 -*-
"""插件贡献清单：右栏面板、输入区动作、上下文段外观、开屏脚本与工具展示名。"""
from __future__ import annotations

from typing import Any, Dict, List


class ContributionActions:
    """把插件声明的贡献投影成页面可直接渲染的清单。"""

    def loaded_plugin_names(self) -> List[str]:
        """当前已装载的插件名。页面用它决定上下文条里哪些插件段还在。"""
        host = getattr(self.app, "plugin_host", None)
        names = getattr(host, "loaded_names", None)
        if not callable(names):
            return []
        return [str(name) for name in names()]

    def tool_list(self) -> List[Dict[str, Any]]:
        """工具展示清单：`[{name, label, icon}]`（来自工具自己的声明）。

        界面据此认识所有工具（含插件工具），不必在前端维护工具名表 ——
        加一个插件工具不需要改界面。
        """
        registry = getattr(self.app, "registry", None)
        if registry is None or not hasattr(registry, "display_list"):
            return []
        return registry.display_list()
