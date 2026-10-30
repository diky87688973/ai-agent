# -*- coding: utf-8 -*-
"""插件系统设置注册表：面板、条目、读取与保存回调。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from agent.core.error_report import report_error

Disposer = Callable[[], None]
SaveCallback = Callable[[Any], Mapping[str, Any]]
LoadCallback = Callable[[], Any]

DEFAULT_SETTINGS_PANELS = (
    ("settings/agent", "Agent"),
    ("settings/context", "上下文"),
    ("settings/interface", "界面"),
)

SETTINGS_ITEM_KINDS = frozenset({
    "text", "search", "number", "select", "checkbox", "textarea", "password",
})


class SettingsRegistryError(ValueError):
    """设置贡献不符合契约。"""


def _segment(raw: Any, what: str) -> str:
    value = str(raw or "").strip()
    if not value or "/" in value or "\\" in value or ".." in value:
        raise SettingsRegistryError(f"{what} 非法：{raw!r}")
    return value


def _panel_id(raw: Any) -> str:
    value = str(raw or "").strip()
    if value == "settings":
        return value
    if not value.startswith("settings/"):
        raise SettingsRegistryError(f"设置面板 ID 必须以 settings/ 开头：{raw!r}")
    if value.count("/") != 1:
        raise SettingsRegistryError(f"设置面板 ID 只能有一级：{raw!r}")
    _segment(value.split("/", 1)[1], "设置面板段")
    return value


def _item_id(parent: str, item: Any) -> str:
    part = _segment(item, "设置条目段")
    return f"{parent}/{part}"


@dataclass(slots=True)
class SettingsPanel:
    owner: str
    panel_id: str
    title: str
    order: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {"id": self.panel_id, "title": self.title,
                "owner": self.owner, "order": self.order}


@dataclass(slots=True)
class SettingsItem:
    owner: str
    parent: str
    item_id: str
    kind: str
    label: str
    default: Any = ""
    options: Tuple[Dict[str, str], ...] = ()
    hint: str = ""
    order: int = 0
    save: Optional[SaveCallback] = None
    load: Optional[LoadCallback] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.item_id,
            "parent": self.parent,
            "owner": self.owner,
            "kind": self.kind,
            "label": self.label,
            "default": self.default,
            "options": [dict(option) for option in self.options],
            "hint": self.hint,
            "order": self.order,
        }


@dataclass
class SettingsRegistry:
    """插件设置注册表；保存由条目所有者提供的回调执行。"""

    panels: Dict[str, SettingsPanel] = field(default_factory=dict)
    items: Dict[str, SettingsItem] = field(default_factory=dict)

    def add_panel(self, owner: str, panel_id: str, title: str, *, order: int = 0) -> Disposer:
        name = _segment(owner, "插件名")
        pid = _panel_id(panel_id)
        if pid in self.panels:
            raise SettingsRegistryError(f"设置面板已注册：{pid}")
        panel = SettingsPanel(owner=name, panel_id=pid, title=str(title or pid), order=int(order))
        self.panels[pid] = panel
        return lambda: self.panels.pop(pid, None)

    def add_item(
        self,
        owner: str,
        parent: str,
        item_id: str,
        *,
        kind: str,
        label: str,
        default: Any = "",
        options: Iterable[Mapping[str, Any]] = (),
        hint: str = "",
        order: int = 0,
        save: SaveCallback,
        load: Optional[LoadCallback] = None,
    ) -> Disposer:
        name = _segment(owner, "插件名")
        pid = _panel_id(parent)
        if pid not in self.panels:
            raise SettingsRegistryError(f"设置父面板不存在：{pid}")
        if not callable(save):
            raise SettingsRegistryError("设置条目必须提供保存回调")
        kind_value = str(kind or "").strip()
        if kind_value not in SETTINGS_ITEM_KINDS:
            raise SettingsRegistryError(f"设置条目类型不支持：{kind!r}")
        normalized = tuple(
            {"value": str(opt.get("value", "")), "label": str(opt.get("label", opt.get("value", "")))}
            for opt in options
        )
        if kind_value == "select" and not normalized:
            raise SettingsRegistryError("select 设置条目必须提供 options")
        full = _item_id(pid, item_id)
        if full in self.items:
            raise SettingsRegistryError(f"设置条目已注册：{full}")
        item = SettingsItem(
            owner=name, parent=pid, item_id=full, kind=kind_value,
            label=str(label or full), default=default, options=normalized,
            hint=str(hint or ""), order=int(order), save=save, load=load,
        )
        self.items[full] = item
        return lambda: self.items.pop(full, None)

    def panels_in_order(self) -> List[SettingsPanel]:
        return sorted(self.panels.values(), key=lambda item: (item.order, item.panel_id))

    def items_of(self, panel_id: str) -> List[SettingsItem]:
        return sorted(
            (item for item in self.items.values() if item.parent == panel_id),
            key=lambda item: (item.order, item.item_id),
        )

    def item(self, item_id: str) -> SettingsItem:
        item = self.items.get(str(item_id or ""))
        if item is None:
            raise SettingsRegistryError(f"设置条目不存在：{item_id!r}")
        return item

    def values(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for item_id, item in self.items.items():
            if item.load is None:
                result[item_id] = item.default
                continue
            try:
                result[item_id] = item.load()
            except Exception as exc:
                raise SettingsRegistryError(f"读取设置失败：{item_id}") from exc
        return result

    def save(self, values: Mapping[str, Any]) -> Dict[str, Any]:
        """先完整校验，再逐项调用所有者回调；失败不掩盖。"""
        if not isinstance(values, Mapping):
            raise SettingsRegistryError("设置提交必须是对象")
        normalized = {str(key): value for key, value in values.items()}
        for item_id, value in normalized.items():
            item = self.item(item_id)
            if item.kind == "select":
                allowed = {option["value"] for option in item.options}
                if str(value) not in allowed:
                    raise SettingsRegistryError(f"设置值不在选项中：{item_id}")
            if item.kind == "checkbox":
                if isinstance(value, str) and value in ("0", "1"):
                    normalized[item_id] = value == "1"
                elif not isinstance(value, bool):
                    raise SettingsRegistryError(f"勾选项必须是布尔值：{item_id}")
        previous: Dict[str, Any] = {}
        for item_id in normalized:
            item = self.item(item_id)
            if item.save is None:
                raise SettingsRegistryError(f"设置条目没有保存回调：{item_id}")
            if item.load is not None:
                try:
                    previous[item_id] = item.load()
                except Exception as exc:
                    raise SettingsRegistryError(f"读取旧设置失败：{item_id}") from exc
        results: Dict[str, Any] = {}
        attempted: List[str] = []
        try:
            for item_id, value in normalized.items():
                item = self.item(item_id)
                attempted.append(item_id)
                result = item.save(value)
                if not isinstance(result, Mapping) or not result.get("ok"):
                    error = str(result.get("error") if isinstance(result, Mapping) else "保存失败")
                    raise SettingsRegistryError(f"{item_id} 保存失败：{error}")
                results[item_id] = {"ok": True}
        except Exception as exc:
            rollback_errors: List[str] = []
            for item_id in reversed(attempted):
                item = self.item(item_id)
                if item.load is None or item.save is None:
                    continue
                try:
                    result = item.save(previous[item_id])
                    if not isinstance(result, Mapping) or not result.get("ok"):
                        rollback_errors.append(item_id)
                except Exception as exc:
                    report_error("agent.capabilities.settings_registry.rollback", exc,
                                 item=item_id)
                    rollback_errors.append(f"{item_id}: {exc}")
            detail = f"；回滚失败：{', '.join(rollback_errors)}" if rollback_errors else ""
            raise SettingsRegistryError(f"{exc}{detail}") from exc
        return {"ok": True, "items": results}

    def drop_plugin(self, owner: str) -> int:
        name = str(owner or "")
        removed = 0
        for item_id in [key for key, item in self.items.items() if item.owner == name]:
            self.items.pop(item_id, None)
            removed += 1
        for panel_id in [key for key, panel in self.panels.items() if panel.owner == name]:
            if any(item.parent == panel_id for item in self.items.values()):
                continue
            self.panels.pop(panel_id, None)
            removed += 1
        return removed


def seed_default_panels(registry: SettingsRegistry) -> None:
    """注册宿主内置设置面板；条目仍由各所有者注册。"""
    for panel_id, title in DEFAULT_SETTINGS_PANELS:
        if panel_id not in registry.panels:
            registry.add_panel("__host__", panel_id, title)


__all__ = [
    "DEFAULT_SETTINGS_PANELS", "SETTINGS_ITEM_KINDS", "SettingsItem",
    "SettingsPanel", "SettingsRegistry", "SettingsRegistryError",
    "seed_default_panels",
]
