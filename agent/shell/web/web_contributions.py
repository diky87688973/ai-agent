# -*- coding: utf-8 -*-
"""插件贡献清单：右栏面板、输入区动作、上下文段外观、开屏脚本与工具展示名。"""
from __future__ import annotations

from typing import Any, Dict, List


class ContributionActions:
    """把插件声明的贡献投影成页面可直接渲染的清单。"""

    def panel_list(self) -> List[Dict[str, Any]]:
        """插件贡献的面板清单；界面按它动态建标签，不为每个插件加分支。

        内置步骤栏由页面静态声明（常驻、内核自有），不由本端点返回。
        """
        host = getattr(self.app, "plugin_host", None)
        contribs = getattr(host, "contributions", None) if host is not None else None
        if contribs is None:
            return []
        return [p.as_dict() for p in contribs.all_panels()]

    def loaded_plugin_names(self) -> List[str]:
        """当前已装载的插件名。页面用它决定上下文条里哪些插件段还在。"""
        host = getattr(self.app, "plugin_host", None)
        names = getattr(host, "loaded_names", None)
        if not callable(names):
            return []
        return [str(name) for name in names()]

    def action_list(self) -> List[Dict[str, Any]]:
        """插件贡献的输入区动作（输入框下面的按钮）。

        界面按它渲染按钮，点开哪个面板由贡献里的 `panel` 指定 ——
        内核与页面都不写死任何插件入口。
        """
        host = getattr(self.app, "plugin_host", None)
        contribs = getattr(host, "contributions", None) if host is not None else None
        if contribs is None:
            return []
        return [a.as_dict() for a in contribs.all_actions()]

    def ctx_segment_style_list(self) -> List[Dict[str, Any]]:
        """插件贡献的上下文段外观（段名 / 色名）；界面开屏按它注册，不必靠空面板脚本。"""
        host = getattr(self.app, "plugin_host", None)
        contribs = getattr(host, "contributions", None) if host is not None else None
        if contribs is None:
            return []
        listing = getattr(contribs, "all_ctx_segment_styles", None)
        if not callable(listing):
            return []
        return [s.as_dict() for s in listing()]

    def boot_script_list(self) -> List[Dict[str, Any]]:
        """插件贡献的开屏脚本；界面在面板脚本之后预载，无面板也能注入。"""
        host = getattr(self.app, "plugin_host", None)
        contribs = getattr(host, "contributions", None) if host is not None else None
        if contribs is None:
            return []
        listing = getattr(contribs, "all_boot_scripts", None)
        if not callable(listing):
            return []
        return [s.as_dict() for s in listing()]

    def tool_list(self) -> List[Dict[str, Any]]:
        """工具展示清单：`[{name, label, icon}]`（来自工具自己的声明）。

        界面据此认识所有工具（含插件工具），不必在前端维护工具名表 ——
        加一个插件工具不需要改界面。
        """
        registry = getattr(self.app, "registry", None)
        if registry is None or not hasattr(registry, "display_list"):
            return []
        return registry.display_list()
