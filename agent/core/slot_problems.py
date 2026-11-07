# -*- coding: utf-8 -*-
"""配置校验：六类问题各自一个函数，合并后由 `validate_problems` 收口。

每个函数只读它判据真正需要的数据（节点表、根、声明方），不接收整个配置对象，
所以本模块位于配置容器之下，装配与覆盖都在它之上。
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List, Mapping, Optional

from agent.core.slot_events import channel_problem, event_type
from agent.core.slot_spec import (
    CONTAINER_KINDS,
    DECLARATIVE_KINDS,
    HOST_OWNER,
    PLUGIN_SLOT_ROOT,
    SlotSpec,
    has_descendants,
    holds_children,
    is_plugin_factory,
    parent_path,
)


def requires_problems(specs: Mapping[str, SlotSpec],
                      sources: Optional[Mapping[str, str]] = None,
                      synthesized: Optional[FrozenSet[str]] = None,
                      ) -> List[str]:
    """requires 指向不存在的路径；给出来源时附上来源与补齐标注。"""
    problems: List[str] = []
    for spec in specs.values():
        for port, dep in spec.requires.items():
            if dep not in specs:
                note = str((sources or {}).get(spec.path, "")).strip()
                if spec.path in (synthesized or frozenset()):
                    note = f"{note}，补齐" if note else "补齐"
                problems.append(
                    f"依赖不存在：{spec.path} 的 {port} -> {dep}"
                    + (f"（来源：{note}）" if note else ""))
    return problems


def order_problems(specs: Mapping[str, SlotSpec], root: str,
                   sources: Optional[Mapping[str, str]] = None,
                   synthesized: Optional[FrozenSet[str]] = None,
                   ) -> List[str]:
    """同一父节点下 order 被两个节点同时占用。"""
    problems: List[str] = []
    siblings: Dict[str, Dict[int, str]] = {}
    marks = synthesized or frozenset()
    for spec in sorted(specs.values(), key=lambda item: item.path):
        if spec.order is None:
            continue
        parent = parent_path(spec.path, root)
        bucket = siblings.setdefault(parent, {})
        first = bucket.get(spec.order)
        if first is not None:
            own = str((sources or {}).get(first, "")).strip()
            if first in marks:
                own = f"{own}，补齐" if own else "补齐"
            here = str((sources or {}).get(spec.path, "")).strip()
            if spec.path in marks:
                here = f"{here}，补齐" if here else "补齐"
            left = first + (f"（来源：{own}）" if own else "")
            right = spec.path + (f"（来源：{here}）" if here else "")
            problems.append(
                f"同层 order 重复：{parent} 下 order={spec.order} 被 {left} 与 {right} 同时占用")
            continue
        bucket[spec.order] = spec.path
    return problems


def event_problems(specs: Mapping[str, SlotSpec]) -> List[str]:
    """宿主事件按常量校验，插件事件按声明依赖校验。"""
    problems: List[str] = []
    for spec in specs.values():
        if spec.kind == "event-channel":
            problem = channel_problem(spec)
            if problem:
                problems.append(problem)
        elif spec.kind == "event":
            try:
                event_type(spec, specs)
            except ValueError as exc:
                problems.append(str(exc))
    return problems



def spec_problems(specs: Mapping[str, SlotSpec], root: str) -> List[str]:
    """节点级校验：root 前缀、factory 有无与形状、子级资格。

    合并后的配置不能走 `SlotConfig.parse` （那里吃的是原始声明与单片段），
    但同一套判据必须对已建好的配置再跑一遍，否则空壳节点会一路绿灯。
    """
    problems: List[str] = []
    for spec in specs.values():
        if not spec.path.startswith(root + "/"):
            problems.append(f"节点不在 root 下：{spec.path}")
            continue
        if not spec.factory and spec.kind not in CONTAINER_KINDS | DECLARATIVE_KINDS:
            problems.append(f"节点缺少 factory：{spec.path}")
        elif spec.factory and ":" not in spec.factory:
            problems.append(f"factory 必须是 module:attr：{spec.path}")
    for spec in specs.values():
        # 能否持有子级由 kind 与 children 回答；不靠额外布尔声明。
        if not holds_children(spec) and has_descendants(specs, spec.path):
            problems.append(
                f"节点不能持有子级却声明了子节点：{spec.path}"
                f"（kind={spec.kind}，children={spec.children}）")
    return problems


def ownership_problems(specs: Mapping[str, SlotSpec],
                       origins: Mapping[str, str]) -> List[str]:
    """factory 写法必须与声明方一致：插件相对名只能出现在插件声明的节点上。

    声明方优先看 `origins`（合并后的配置才有）。单片段配置（`SlotConfig.parse`
    读一份文件）没有 origins，此时只能按路径判：落在 `app/plugins/` 下算插件自有，
    其余算宿主。否则插件的片段自己就过不了自己的片段，等于把插件全部判非法。

    反向不报：插件节点也可以写 `agent.*`（复用宿主实现）。
    """
    declared = bool(origins)
    problems: List[str] = []
    for spec in specs.values():
        if not spec.factory or not is_plugin_factory(spec.factory):
            continue
        if declared:
            mine = origins.get(spec.path, HOST_OWNER) != HOST_OWNER
        else:
            mine = spec.path.startswith(PLUGIN_SLOT_ROOT)
        if not mine:
            problems.append(
                f"宿主节点不得引用插件实现：{spec.path}（factory={spec.factory}）")
    return problems


def validate_problems(specs: Mapping[str, SlotSpec], root: str,
                      origins: Mapping[str, str],
                      sources: Optional[Mapping[str, str]] = None,
                      synthesized: Optional[FrozenSet[str]] = None,
                      ) -> List[str]:
    """对已建好的节点表跑完整校验，返回全部问题。"""
    return (spec_problems(specs, root) + requires_problems(specs, sources, synthesized)
            + event_problems(specs) + order_problems(specs, root, sources, synthesized)
            + ownership_problems(specs, origins))
