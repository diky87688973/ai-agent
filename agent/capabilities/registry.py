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
    """工具插件协议：子类声明 name / description / parameters / label / icon / parallel_safe。

    `label` 与 `icon` 是界面展示信息，由工具自己声明：界面不该为认出一个工具而在
    前端维护一张工具名表（那样每加一个插件工具都得改界面）。内核只把它们透出去，
    不做任何解释。
    """

    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {}
    #: 中文短名（界面上的工具标题）；留空时界面退回显示 `name`
    label: str = ""
    #: 一个字符的图标（emoji）；留空时界面用兜底图标
    icon: str = ""
    parallel_safe: bool = False  # 默认串行
    #: 为真时管道 post 登记预览快照并注入 confirm_id（写类预览入口）
    needs_preview: bool = False
    #: 写目标路径参数键序（供门控解析写路径）；空则无法解析路径（不默认猜 path）
    write_path_keys: Tuple[str, ...] = ()
    #: 为真时落盘后要求先 read_file 再改同一路径（内容写类）；结构性操作保持 False
    needs_reread: bool = False

    def execute(self, arguments: Dict[str, Any]) -> Any:
        """执行工具，返回结果（任意可序列化值）；子类必须覆写。"""
        raise NotImplementedError(f"工具未实现 execute：{type(self).__name__}")


class ToolRegistryView:
    """工具注册表的只读角色视图；不复制、不接受注册。"""

    def __init__(
        self,
        base: "ToolRegistry",
        excluded: set[str] | frozenset[str] = frozenset(),
        *,
        honor_subagent_hidden: bool = False,
    ) -> None:
        self._base = base
        self._excluded = frozenset(str(name) for name in excluded)
        self._honor_subagent_hidden = bool(honor_subagent_hidden)

    def _allowed(self, name: str) -> bool:
        key = str(name or "").strip()
        if key in self._excluded:
            return False
        return not (self._honor_subagent_hidden and key in self._base.subagent_hidden())

    def get(self, name: str) -> Optional[ToolPlugin]:
        return self._base.get(name) if self._allowed(name) else None

    def names(self) -> List[str]:
        return [name for name in self._base.names() if self._allowed(name)]

    def schemas(self) -> List[Dict[str, Any]]:
        return [item for item in self._base.schemas() if self._allowed(str(item.get("name") or ""))]


class ToolRegistry:
    """工具注册表：name → 插件实例；注册返回幂等 disposer。"""

    def __init__(self) -> None:
        self._plugins: Dict[str, ToolPlugin] = {}
        self._disposers: List[Tuple[str, Disposer]] = []
        self._owners: Dict[str, str] = {}
        self._owner_subagent_tools: Dict[str, frozenset[str]] = {}

    def subagent_hidden(self) -> set[str]:
        """按插件声明的子智能体工具清单计算不可见工具。"""
        hidden = set()
        for name, owner in self._owners.items():
            allowed = self._owner_subagent_tools.get(owner)
            if allowed is not None and name not in allowed:
                hidden.add(name)
        return hidden

    def set_subagent_tools(self, owner: str, tools: Any) -> Disposer:
        """声明某插件向子智能体暴露的工具清单；空清单表示全部不暴露。"""
        key = str(owner or "").strip()
        allowed = frozenset(str(item) for item in (tools or ()))
        previous = self._owner_subagent_tools.get(key)

        def _dispose() -> None:
            if previous is None:
                self._owner_subagent_tools.pop(key, None)
            else:
                self._owner_subagent_tools[key] = previous

        self._owner_subagent_tools[key] = allowed
        return _dispose

    def register(self, plugin: ToolPlugin, *, owner: str = "") -> Disposer:
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
        self._owners[name] = str(owner or "")

        def _dispose() -> None:
            if name not in self._plugins:
                return  # 幂等：已注销
            del self._plugins[name]
            self._owners.pop(name, None)
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

    def display_list(self) -> List[Dict[str, str]]:
        """导出界面展示清单：`[{name, label, icon}]`（按名称排序）。

        界面据此认识所有工具（含插件工具），不必在前端维护工具名表。
        `label` 留空时界面退回显示 `name`。
        """
        return [
            {
                "name": str(p.name),
                "label": str(getattr(p, "label", "") or ""),
                "icon": str(getattr(p, "icon", "") or ""),
            }
            for _, p in sorted(self._plugins.items())
        ]

    def dispose_all(self) -> None:
        """按注册逆序注销全部插件（后注册先清理）。"""
        while self._disposers:
            _key, disposer = self._disposers.pop()
            disposer()
