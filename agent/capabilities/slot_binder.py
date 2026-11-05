# -*- coding: utf-8 -*-
"""插口绑定点：把装配结果登记进既有注册表。

装配器只负责构造；「构造出来的东西进哪张表」由本模块回答。它不做第二套
账本：每条登记都调既有注册表的既有入口，并原样收下它们返回的 disposer。

登记信息全部来自装配结果与声明：`assembly.values`（节点路径 → 构造物）、
`SlotSpec` 的 `kind` / `order` / `props` / `method`，以及 `config.origin_of`
给出的声明方。本模块不解析片段、不复制节点、不缓存结构。

三类约定写在声明里，不靠路径猜：

```text
provider  props.target   落点：context-source / prompt-section / mode-tail /
                        assembly-hook / model-catalog
prompt-section props.section / props.after_tools
mode-tail      props.subagent_visible
route          props.path（HTTP 路径段）+ spec.method；路径身份由 Contributions 拼
event          事件名取路径里那个命中 `event_name` 常量的段
```

单条登记失败不中断整体：插件资产缺一条不该让内核起不来。失败带节点路径、
注册表名与异常类型上报；其余节点继续登记。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from agent.core.error_report import report_error
from agent.core.slot_config import SlotConfig
from agent.core.slot_spec import (
    EVENT_NAMES,
    HOST_OWNER,
    SCOPE_APP,
    SlotSpec,
)

Disposer = Callable[[], None]

#: 只负责装配、不进任何注册表的类型。
STRUCTURAL_KINDS = frozenset({"container", "module", "service"})
#: UI 控件类：经 `UiRegistry.add_item` 登记。
UI_ITEM_KINDS = frozenset({"ui-action", "ui-control", "ui-tool-shell"})
#: `provider` 的落点，取自节点 `props.target`。
PROVIDER_TARGETS = frozenset({
    "context-source", "prompt-section", "mode-tail", "assembly-hook",
    "model-catalog",
})
#: `order` 缺省时的排序位（排在同层末尾。
NO_ORDER = 1 << 30


class SlotBinder:
    """把一次装配的结果逐节点登记进既有注册表，并保留逆序撤销能力。

    构造时注入的目标对象全是既有注册表实例（由装配结果取出），本类不新建表。
    `ranks` 是插件在装载清单里的位次：系统提示词章节与上下文来源要按它排序。
    """

    def __init__(self, *, plugin_host: Any, registry: Any, event_bus: Any,
                 contributions: Any, prompt_sections: Any, prompt_tail: Any,
                 context_sources: Any, context_hooks: Any, model_catalog: Any,
                 executors: Any, ranks: Optional[Mapping[str, int]] = None) -> None:
        self.plugin_host = plugin_host
        self.registry = registry
        self.event_bus = event_bus
        self.contributions = contributions
        self.prompt_sections = prompt_sections
        self.prompt_tail = prompt_tail
        self.context_sources = context_sources
        self.context_hooks = context_hooks
        self.model_catalog = model_catalog
        self.executors = executors
        self.ranks: Dict[str, int] = dict(ranks or {})
        self.failures: List[str] = []
        self._ledger: List[Tuple[str, Disposer]] = []
        self._disposed = False

    # ── 对外 ──

    def bind(self, assembly: Any) -> "SlotBinder":
        """按登记顺序逐节点登记；单条失败留痕后继续。"""
        config = assembly.config
        values = assembly.values
        for spec in self._order(config, values):
            if spec.scope != SCOPE_APP:
                continue
            try:
                disposer = self._register(config, spec, values[spec.path])
            except Exception as exc:
                self.failures.append(self._describe(spec, exc))
                report_error("slot_binder.bind", exc, path=spec.path,
                             kind=spec.kind, registry=self._table_of(spec))
                continue
            if disposer is not None:
                self._ledger.append((spec.path, disposer))
        for owner, tools in getattr(config, "subagent_tools", {}).items():
            disposer = self.registry.set_subagent_tools(owner, tools)
            self._ledger.append((f"app/plugins/{owner}/tools", disposer))
        return self

    def dispose(self) -> None:
        """按登记逆序撤销；单条失败留痕后继续。"""
        if self._disposed:
            return
        self._disposed = True
        for path, disposer in reversed(self._ledger):
            try:
                disposer()
            except Exception as exc:
                report_error("slot_binder.dispose", exc, path=path)
        self._ledger.clear()

    def bound_paths(self) -> Tuple[str, ...]:
        """已登记成功的节点路径（登记顺序）。"""
        return tuple(path for path, _ in self._ledger)

    def fork(self) -> "SlotBinder":
        """对同一批宿主服务创建一次独立登记事务。"""
        return SlotBinder(
            plugin_host=self.plugin_host, registry=self.registry,
            event_bus=self.event_bus, contributions=self.contributions,
            prompt_sections=self.prompt_sections, prompt_tail=self.prompt_tail,
            context_sources=self.context_sources, context_hooks=self.context_hooks,
            model_catalog=self.model_catalog, executors=self.executors,
            ranks=self.plugin_host.ranks())

    # ── 顺序 ──

    def _order(self, config: SlotConfig, values: Mapping[str, Any]
               ) -> List[SlotSpec]:
        """两级顺序：先立挂载点，再按 order 填内容。

        UI 插口与设置面板是子项的挂载点，必须先于子项登记，否则子项会被
        `父插口未注册` 拒掉 —— 那不是配置错，是顺序错。
        """
        present = [config.spec(path) for path in config.paths()
                   if path in values]
        structural: List[SlotSpec] = []
        rest: List[SlotSpec] = []
        for spec in present:
            if self._is_structural(spec, values[spec.path]):
                structural.append(spec)
            elif not self._host_delivered(config, spec):
                rest.append(spec)
        structural.sort(key=lambda item: (item.path.count("/"), item.path))
        rest.sort(key=lambda item: (
            NO_ORDER if item.order is None else int(item.order), item.path))
        return structural + rest

    @staticmethod
    def _host_delivered(config: SlotConfig, spec: SlotSpec) -> bool:
        """宿主工具已由自己的容器交付，绑定器不再重复登记。

        `app/boot/tools` 容器（`tool_group`）拿子节点统一登记工具 —— 那是宿主资产的
        交付点，与插件的片段声明是两条路。绑定器只补插件资产与宿主 UI 节点；
        两边都登一次，就会在注册表里撞「工具已注册」。
        """
        return spec.kind == "tool" and config.origin_of(spec.path) == HOST_OWNER

    @staticmethod
    def _is_structural(spec: SlotSpec, value: Any) -> bool:
        if spec.kind == "ui-slot":
            return True
        return spec.kind == "setting" and str(getattr(value, "kind", "")) == "panel"

    # ── 分派 ──

    def _register(self, config: SlotConfig, spec: SlotSpec, value: Any
                  ) -> Optional[Disposer]:
        owner = config.origin_of(spec.path)
        kind = spec.kind
        if kind in STRUCTURAL_KINDS:
            return None
        if kind == "ui-slot":
            return self.ui.add_slot(
                spec.path, kind=kind, children=spec.children,
                fixed_children=tuple(spec.fixed), owner="*")
        if kind in UI_ITEM_KINDS:
            return self.ui.add_item(
                spec.path, kind=kind, owner=owner,
                props=dict(spec.props), order=spec.order)
        if kind == "setting":
            return self._bind_setting(config, spec, value, owner)
        if kind == "tool":
            return self.registry.register(value, owner=owner)
        if kind == "route":
            return self.contributions.add_route(
                owner, spec.method, self._url_of(spec), value)
        if kind == "event":
            return self.event_bus.subscribe(self._event_of(spec), value)
        if kind == "assembly-hook":
            return self.context_hooks.add(value)
        if kind == "provider":
            return self._bind_provider(spec, value, owner)
        if kind == "runtime":
            return self.plugin_host.register_runtime(owner, value)
        if kind == "executor":
            return self.executors.add(spec.path.rsplit("/", 1)[-1], value, owner)
        raise ValueError(f"未登记的插口类型：{kind}")

    @property
    def ui(self) -> Any:
        """UI 注册表：插件宿主持有，与壳层读的是同一份。"""
        return self.plugin_host.ui

    @property
    def settings(self) -> Any:
        """设置注册表：同上。"""
        return self.plugin_host.settings

    def _bind_setting(self, config: SlotConfig, spec: SlotSpec, decl: Any,
                      owner: str) -> Optional[Disposer]:
        """设置面板与条目：父面板与条目 id 都从节点路径取。

        节点路径本身就是设置路径（`app/settings/<面板>/<条目>`）：父面板 = 去掉末段，
        条目 id = 末段。不再重复读 `props.panel` / `props.key`，避免同一事实两处存。
        """
        if str(getattr(decl, "kind", "")) == "panel":
            return self.settings.add_panel(
                owner, spec.path, str(getattr(decl, "label", "") or ""),
                order=0 if spec.order is None else int(spec.order))
        parent, _, item_id = spec.path.rpartition("/")
        return self.settings.add_item(
            owner, parent, item_id,
            kind=str(getattr(decl, "kind", "") or ""),
            label=str(getattr(decl, "label", "") or ""),
            default=getattr(decl, "default", ""),
            options=tuple(getattr(decl, "options", ()) or ()),
            hint=str(getattr(decl, "hint", "") or ""),
            order=0 if spec.order is None else int(spec.order),
            save=getattr(decl, "save", None),
            load=getattr(decl, "load", None))

    def _bind_provider(self, spec: SlotSpec, value: Any, owner: str
                       ) -> Optional[Disposer]:
        target = str(spec.props.get("target") or "").strip()
        if target not in PROVIDER_TARGETS:
            raise ValueError(
                f"provider 节点未声明合法 props.target：{target!r}"
                f"（可选：{', '.join(sorted(PROVIDER_TARGETS))}）")
        if target == "context-source":
            return self.context_sources.add(
                value, self._source_meta(spec, owner), path=spec.path,
                owner=owner)
        if target == "prompt-section":
            section = str(spec.props.get("section") or "").strip()
            if not section:
                raise ValueError("prompt-section 节点未声明 props.section")
            return self.prompt_sections.add(
                section, value, rank=self.ranks.get(owner),
                after_tools=bool(spec.props.get("after_tools")))
        if target == "mode-tail":
            return self.prompt_tail.add(
                value, subagent_visible=bool(
                    spec.props.get("subagent_visible", True)))
        if target == "assembly-hook":
            return self.context_hooks.add(value)
        try:
            return self.model_catalog.set_source(owner, value)
        except RuntimeError as exc:
            # 目录只认一个权威：第二个来源被拒是既定行为，留痕后继续。
            report_error("slot_binder.model_catalog", exc,
                         path=spec.path, plugin=owner)
            self.failures.append(self._describe(spec, exc))
            return None

    def _source_meta(self, spec: SlotSpec, owner: str) -> Any:
        """注入源的段描述：段 key 恒为插件名，段名与前缀来自声明。"""
        from agent.mechanisms.context import SourceMeta, slug

        return SourceMeta(
            key=slug(owner), label=str(spec.props.get("label") or "") or owner,
            plugin=owner, prefix=str(spec.props.get("prefix") or ""),
            plugin_rank=self.ranks.get(owner))

    @staticmethod
    def _url_of(spec: SlotSpec) -> str:
        """HTTP 路径段：显式声明在 props.path；缺声明即配置错，不按路径末段猜。"""
        url = str(spec.props.get("path") or "").strip()
        if not url:
            raise ValueError("route 节点未声明 props.path（HTTP 路径段）")
        return url

    @staticmethod
    def _event_of(spec: SlotSpec) -> str:
        """事件名：路径里命中 `event_name` 常量的那一段。"""
        for segment in spec.path.split("/"):
            if segment in EVENT_NAMES:
                return segment
        raise ValueError(
            f"event 节点的事件名不在 event_name 常量里：{spec.path}")

    def _describe(self, spec: SlotSpec, exc: Exception) -> str:
        """失败条目：节点路径 + 注册表名 + 异常类型，供报告与断言使用。"""
        return (f"{spec.path}（kind={spec.kind}，注册表={self._table_of(spec)}）"
                f"：{type(exc).__name__}: {exc}")

    @staticmethod
    def _table_of(spec: SlotSpec) -> str:
        if spec.kind in STRUCTURAL_KINDS:
            return "-"
        if spec.kind == "ui-slot" or spec.kind in UI_ITEM_KINDS:
            return "ui"
        if spec.kind == "setting":
            return "settings"
        if spec.kind == "tool":
            return "registry"
        if spec.kind == "route":
            return "contributions"
        if spec.kind == "event":
            return "event_bus"
        if spec.kind == "runtime":
            return "plugin_host.runtimes"
        if spec.kind == "executor":
            return "executors"
        if spec.kind == "provider":
            return f"provider:{spec.props.get('target') or '?'}"
        return "?"


__all__ = ["SlotBinder"]
