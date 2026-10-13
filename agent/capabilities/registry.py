# -*- coding: utf-8 -*-
"""工具协议与注册表（ToolPlugin / ToolRegistry）— 能力层注册制地基。

协议（单一定义源 + disposer 可控装卸）：
- ToolPlugin：类属性 name / description / parameters（属性映射：参数名 → JSON Schema 片段）/
  parallel_safe（默认 False）+ execute(arguments)；
- ToolRegistry：register(plugin) 返回 disposer（注销句柄）；name 唯一；
- schemas()：导出模型可见的工具声明（名称 / 描述 / 参数 / parallel_safe）。

契约（与管道对齐，见 core/tool_call.py）：
- execute 返回执行结果（任意可序列化值）；异常由管道捕获为失败（ok=False
  结构化回灌，单步失败不终止回合）；
- get 未注册返回 None（管道将其转为"未知工具"错误回灌）。
纪律：注册表只存不跑 —— 执行调度与门控由管道唯一入口统一承载。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

Disposer = Callable[[], None]


class ToolPlugin:
    """工具插件协议：子类声明 name / description / parameters / parallel_safe 并实现 execute。"""

    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {}
    parallel_safe: bool = False  # 默认串行

    def execute(self, arguments: Dict[str, Any]) -> Any:
        """执行工具，返回结果（任意可序列化值）；子类必须覆写。"""
        raise NotImplementedError(f"工具未实现 execute：{type(self).__name__}")


class ToolRegistry:
    """工具注册表：name → 插件实例；注册返回幂等 disposer。"""

    def __init__(self) -> None:
        self._plugins: Dict[str, ToolPlugin] = {}
        self._disposers: List[Tuple[str, Disposer]] = []

    def register(self, plugin: ToolPlugin) -> Disposer:
        """注册插件；名称为空/重复/不可执行/参数非法时抛 ValueError；返回幂等 disposer。"""
        name = str(getattr(plugin, "name", "") or "").strip()
        if not name:
            raise ValueError("工具名不能为空")
        if name in self._plugins:
            raise ValueError(f"工具已注册：{name}（请先注销旧插件再替换）")
        if not callable(getattr(plugin, "execute", None)):
            raise ValueError(f"插件缺少可执行的 execute：{name}")
        if not isinstance(getattr(plugin, "parameters", None), dict):
            raise ValueError(f"插件 parameters 必须是 dict（属性映射）：{name}")
        self._plugins[name] = plugin

        def _dispose() -> None:
            if name not in self._plugins:
                return  # 幂等：已注销
            del self._plugins[name]
            for i, (k, _d) in enumerate(self._disposers):
                if k == name:
                    del self._disposers[i]
                    break

        self._disposers.append((name, _dispose))
        return _dispose

    def get(self, name: str) -> Optional[ToolPlugin]:
        """按名解析插件；未注册返回 None（管道将其转为"未知工具"回灌）。"""
        return self._plugins.get(str(name or "").strip())

    def names(self) -> List[str]:
        """已注册工具名（排序后；诊断与 catalog 校验用）。"""
        return sorted(self._plugins)

    def schemas(self) -> List[Dict[str, Any]]:
        """导出模型可见的工具声明（按名称排序；快照与插件实例解耦）。"""
        return [
            {
                "name": p.name,
                "description": str(getattr(p, "description", "") or ""),
                "parameters": dict(getattr(p, "parameters", {}) or {}),
                "parallel_safe": bool(getattr(p, "parallel_safe", False)),
            }
            for _, p in sorted(self._plugins.items())
        ]

    def dispose_all(self) -> None:
        """按注册逆序注销全部插件（后注册先清理）。"""
        while self._disposers:
            _key, disposer = self._disposers.pop()
            disposer()
