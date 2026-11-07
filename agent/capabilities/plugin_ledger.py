"""插件运行时资源按逆序释放，单项失败不阻断后续清理。"""
from __future__ import annotations

from typing import Callable, Iterable

from agent.core.error_report import report_error

Disposer = Callable[[], None]


def dispose_in_reverse(disposers: Iterable[Disposer], source: str) -> None:
    """逆序调用 disposer；单个失败上报（`source` 为上报标签）后继续。"""
    for disposer in reversed(list(disposers)):
        try:
            disposer()
        except Exception as exc:
            report_error(source, exc)
