# -*- coding: utf-8 -*-
"""插口节点的声明层：字段、解析、字面量判据。

一个节点由路径、类型、实现引用、依赖边、归属与顺序组成；本模块只管声明本身，
不涉及配置容器、装配与覆盖。两条判据在此给出唯一实现：
`holds_children`（能否持有子级）与 `has_descendants`（是否存在后代）。
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Callable, Dict, FrozenSet, Mapping, Optional, Tuple

from agent.core import event_name

#: 已登记的事件名全集：由 `agent.core.event_name` 一级常量的值构成。
#: 事件名是对外契约，片段里写的事件名必须命中此集，不允许自造字串。
EVENT_NAMES = frozenset(
    value for name, value in vars(event_name).items()
    if name.isupper() and isinstance(value, str))

#: 十六种插口类型；新增类型必须同时给出 factory 调用约定。
KINDS = frozenset({
    "container", "module", "service", "provider", "tool", "route",
    "http-route", "event", "assembly-hook", "executor", "setting",
    "ui-slot", "ui-action", "ui-control", "ui-tool-shell",
    "runtime",
})

#: 覆盖模式；`base` 只用于标记默认实现自身，不是可写的 mode。
MODES = frozenset({"replace", "extend", "wrap", "disable", "replace_subtree"})
BASE_MODE = "base"
SCOPE_APP = "app"
SCOPE_SESSION = "session"
HOST_OWNER = "__host__"
#: 插件节点路径根。单片段配置没有 origins，据此判该节点是否归插件。
PLUGIN_SLOT_ROOT = "app/plugins/"

#: 这两类的 factory 额外接收已构造的直接子节点；`ui-slot` 可被 UI 控件填，同样持有子级。
CONTAINER_KINDS = frozenset({"container", "module", "ui-slot"})
#: 子级策略：`none` 不接受贡献，`keyed` 接受任意子名，`fixed` 只接受固定子名。
CHILDREN_NONE = "none"
CHILDREN_KEYED = "keyed"
CHILDREN_FIXED = "fixed"
CHILDREN_MODES = frozenset({CHILDREN_NONE, CHILDREN_KEYED, CHILDREN_FIXED})
#: 纯声明类型：没有 factory，声明本身即产物。
DECLARATIVE_KINDS = frozenset({"ui-slot", "ui-action", "ui-control", "ui-tool-shell"})
#: 缺省作用域为会话级的类型。
SESSION_BY_DEFAULT = frozenset({"module"})

#: `route` 节点允许的 HTTP 方法。
HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})

#: 已取消的字段：曾用来给节点挂任意载荷，现由独立节点字段承担。
#: 出现即报错并指出该写哪个字段，避免「换回旧写法也不知道错在哪」。
RETIRED_FIELDS = {
    "metadata": "metadata 已取消：方法写 method，顺序写 order，作用域写 scope，"
                "载荷写 props",
}

Resolver = Callable[[str], Callable[..., Any]]


class SlotConfigError(ValueError):
    """配置非法：路径重复、依赖缺失、类型或顺序冲突。"""


class SlotAssemblyError(RuntimeError):
    """节点构造失败或依赖未就绪。"""


@dataclass(frozen=True)
class SlotSpec:
    """一个插口节点的声明。"""

    path: str
    kind: str
    factory: str = ""
    requires: Mapping[str, str] = field(default_factory=dict)
    owner: str = HOST_OWNER
    order: Optional[int] = None
    scope: str = SCOPE_APP
    frozen: bool = False
    children: str = CHILDREN_NONE
    fixed: Tuple[str, ...] = ()
    props: Mapping[str, Any] = field(default_factory=dict)
    method: str = ""


#: 节点允许出现的键。其余键一律拒绝：静默丢弃会让「写了但没生效」伪装成「正确」。
#: 从字段表现算，不另写一份：声明是唯一事实源，字段名字面量全仓只存在下面的类定义里。
SPEC_FIELDS = frozenset(item.name for item in fields(SlotSpec))
#: 覆盖声明（插件侧）额外允许 `mode`：它描述「这份实现与默认实现的关系」，
#: 不属于节点本身，所以节点里写 mode 仍然报错。
OVERRIDE_FIELDS = SPEC_FIELDS | {"mode"}

#: 覆盖不得修改的结构字段：换实现不等于换形状。
#: `fixed` 与 `children` 同属子级策略，单独改它同样是在改形状，故一并归入。
STRUCTURAL_FIELDS = ("kind", "scope", "children", "fixed")


@dataclass(frozen=True)
class SettingDecl:
    """`setting` 节点的产物：面板或条目声明。

    面板与条目带 `save` / `load` 回调，函数写不进 JSON，故 setting 必须有
    factory；factory 把这些回调连同展示属性一起交回声明物。
    """

    kind: str = "panel"
    label: str = ""
    default: Any = ""
    options: Tuple[Mapping[str, Any], ...] = ()
    hint: str = ""
    save: Optional[Callable[[Any], Any]] = None
    load: Optional[Callable[[], Any]] = None


def holds_children(spec: SlotSpec) -> bool:
    """该节点能否有子节点：容器类或显式声明了 children≠none。

    只看 kind 会把设置面板这种「声明型父插口」误判成叶子，所以两条任一成立即算。
    这是「能持有子级」的唯一判据：不再另设布尔字段声明同一件事，
    否则同一事实有了第二份来源。
    """
    return spec.kind in CONTAINER_KINDS or spec.children != CHILDREN_NONE


def has_descendants(specs: Mapping[str, SlotSpec], path: str) -> bool:
    """该路径是否存在后代（即它是自己那棵子树的根）。

    「主插口」的唯一判据。有后代 ⇒ 是；无后代 ⇒ 不是，没有第三种。
    中间节点（父本身也是别人的子）也算：它自己就是那棵子树的根。

    装配、校验、绑定、注册表都需要判这件事，各处就地写前缀比较就是多份事实；
    一律调本函数，前缀规则只有这里一份。
    """
    prefix = path.rstrip("/") + "/"
    return any(candidate.startswith(prefix) for candidate in specs)


def _flag_of(value: Any, base: bool) -> bool:
    if value is None:
        return base
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _mapping_field(row: Mapping, key: str, base: Optional[SlotSpec],
                   fallback: Mapping[str, Any]) -> Dict[str, Any]:
    """解析一个「必须是对象」的字段（metadata / props），支持 base 继承。"""
    raw = row.get(key)
    if raw is None:
        return dict(fallback)
    if not isinstance(raw, Mapping):
        raise SlotConfigError(f"{key} 必须是对象：{row.get('path') or ''}")
    return dict(raw)


def _children_field(row: Mapping, base: Optional[SlotSpec], path: str,
                    ) -> Tuple[str, Tuple[str, ...]]:
    """解析 `children` / `fixed` 两个成对字段，返回 (children, fixed)。"""
    raw_children = row.get("children")
    if raw_children is None:
        children = base.children if base else CHILDREN_NONE
    else:
        children = str(raw_children).strip()
    if children not in CHILDREN_MODES:
        raise SlotConfigError(
            f"children 非法：{path} / {children or '空'}（只接受 none / keyed / fixed）")
    raw_fixed = row.get("fixed")
    if raw_fixed is None:
        fixed: Tuple[str, ...] = tuple(base.fixed) if base else ()
    elif isinstance(raw_fixed, (list, tuple)):
        fixed = tuple(str(item) for item in raw_fixed)
    else:
        raise SlotConfigError(f"fixed 必须是数组：{path}")
    if fixed and children != CHILDREN_FIXED:
        raise SlotConfigError(f"fixed 只用于 children=fixed：{path}")
    return children, fixed


def parse_spec(row: Any, base: Optional[SlotSpec] = None,
                allowed: FrozenSet[str] = SPEC_FIELDS) -> SlotSpec:
    """解析单条节点声明；给出 `base` 时缺省字段沿用它的值。

    `allowed` 是允许出现的键集合：节点用 SPEC_FIELDS，覆盖声明用 OVERRIDE_FIELDS。
    """
    if not isinstance(row, Mapping):
        raise SlotConfigError("节点声明必须是对象")
    for retired, hint in RETIRED_FIELDS.items():
        if retired in row:
            raise SlotConfigError(
                f"节点出现已取消的字段：{row.get('path') or '（无 path）'} -> {retired}"
                f"（{hint}）")
    unknown = sorted(str(key) for key in row if key not in allowed)
    if unknown:
        raise SlotConfigError(
            f"节点出现未知字段：{row.get('path') or '（无 path）'} -> "
            f"{', '.join(unknown)}（允许的键：{'、'.join(sorted(allowed))}）")
    path = str(row.get("path") or "").strip().strip("/")
    if not path:
        raise SlotConfigError("节点声明缺少 path")
    kind = str(row.get("kind") or (base.kind if base else "")).strip()
    if kind not in KINDS:
        raise SlotConfigError(f"kind 非法：{path} / {kind or '空'}")
    factory = str(row.get("factory") or (base.factory if base else "")).strip()
    raw_requires = row.get("requires")
    if raw_requires is None:
        requires: Dict[str, str] = dict(base.requires) if base else {}
    elif isinstance(raw_requires, Mapping):
        requires = {str(k): str(v) for k, v in raw_requires.items()}
    else:
        raise SlotConfigError(f"requires 必须是对象：{path}")
    scope = str(row.get("scope") or (base.scope if base else "")).strip()
    if not scope:
        scope = SCOPE_SESSION if kind in SESSION_BY_DEFAULT else SCOPE_APP
    if scope not in (SCOPE_APP, SCOPE_SESSION):
        raise SlotConfigError(f"scope 非法：{path} / {scope}")
    raw_order = row.get("order", base.order if base else None)
    if raw_order is None or raw_order == "":
        order: Optional[int] = None
    elif isinstance(raw_order, bool):
        raise SlotConfigError(f"order 非法：{path}")
    else:
        try:
            order = int(raw_order)
        except (TypeError, ValueError) as exc:
            raise SlotConfigError(f"order 非法：{path}") from exc
    props = _mapping_field(row, "props", base, base.props if base else {})
    raw_method = row.get("method")
    if raw_method is None:
        method = base.method if base else ""
    else:
        method = str(raw_method).strip().upper()
    if method and kind != "route" and kind != "http-route":
        raise SlotConfigError(f"method 只用于 route 节点：{path} / {kind}")
    if kind in ("route", "http-route") and not method:
        raise SlotConfigError(f"route 节点缺少 method：{path}")
    if method and method not in HTTP_METHODS:
        raise SlotConfigError(
            f"method 非法：{path} / {method}（只接受 {' / '.join(sorted(HTTP_METHODS))}）")
    children, fixed = _children_field(row, base, path)
    return SlotSpec(
        path=path, kind=kind, factory=factory, requires=requires, order=order,
        owner=str(row.get("owner") or (base.owner if base else HOST_OWNER)).strip()
        or HOST_OWNER,
        scope=scope, props=props, method=method, children=children, fixed=fixed,
        frozen=_flag_of(row.get("frozen"), base.frozen if base else False))


def parent_path(path: str, root: str) -> str:
    head, sep, _tail = path.rpartition("/")
    return head if sep else root


def sort_key(spec: SlotSpec) -> Tuple[int, int, str]:
    """同层排序键：声明了 order 的按 order 在前，其余按路径。"""
    if spec.order is None:
        return (1, 0, spec.path)
    return (0, spec.order, spec.path)


def label_of(origin: str) -> str:
    """声明方 → 人读来源标签（只用于报错文案）。

    `origin` 是插件名或 `__host__`。标签属于展示，不存字段；
    与 `origins` 同处 core 是因为片段加载器与配置双向都要用它。
    """
    if origin == HOST_OWNER:
        return "静态片段（仓库根 plugin-slots.json）"
    return f"插件片段 {origin}（plugins/{origin}/plugin-slots.json）"


def is_plugin_factory(spec: str) -> bool:
    """factory 的 module 段是否写成插件相对名（非 `agent.*`）。"""
    module_name = str(spec or "").partition(":")[0]
    return bool(module_name) and not module_name.startswith("agent.")
