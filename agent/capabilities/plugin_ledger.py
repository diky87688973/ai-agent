# -*- coding: utf-8 -*-
"""插件贡献账本——一次装载期间登记的可撤销动作。

`PluginContext` 的每个 `add_*` 都产生一个 disposer；插件 `register` 也可以直接
返回 disposer（或它们的嵌套列表）。本模块负责合并两份来源、按对象去重，
并在卸载 / 回滚时逆序执行：后登记的贡献先撤，先登记贡献的依赖才不会先断。
单个 disposer 失败只上报、不阻断其余撤销。
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, List

from agent.core.error_report import report_error

Disposer = Callable[[], None]


def flatten_disposers(returned: Any) -> List[Disposer]:
    """把 `None | 可调用 | 列表（可嵌套）` 拍平成 disposer 列表。"""
    if returned is None:
        return []
    if callable(returned):
        return [returned]
    if isinstance(returned, (list, tuple)):
        out: List[Disposer] = []
        for item in returned:
            out.extend(flatten_disposers(item))
        return out
    return []


def merge_disposers(owned: Iterable[Disposer], returned: Any) -> List[Disposer]:
    """合并 ctx 记账与 register 返回值，按对象身份去重（保序）。

    同一插件可能把已经登记的 disposer 再从 register 返回一次；按身份去重，
    撤销清单里就只会出现一次。
    """
    merged: List[Disposer] = list(owned)
    merged.extend(flatten_disposers(returned))
    seen = set()
    unique: List[Disposer] = []
    for disposer in merged:
        if callable(disposer) and id(disposer) not in seen:
            seen.add(id(disposer))
            unique.append(disposer)
    return unique


def dispose_in_reverse(disposers: Iterable[Disposer], source: str) -> None:
    """逆序调用 disposer；单个失败上报（`source` 为上报标签）后继续。"""
    for disposer in reversed(list(disposers)):
        try:
            disposer()
        except Exception as exc:
            report_error(source, exc)
