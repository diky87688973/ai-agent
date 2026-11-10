# -*- coding: utf-8 -*-
"""搜索范围：默认剪枝 + 调用方自定排除名单（glob/grep/regex_locate/file_search 共用）。

默认剪掉三处：`.git/` 与 `__pycache__/` 按目录名匹配，另加当前进程根目录下的
`data/`。

`data/` 按绝对路径精确匹配，不按名字：`data` 是个普通词，别的项目里它可能就是
源码目录，按名字排会误伤；只有进程根下那一个 `data/` 是本应用的运行态产物
（会话事实流、备份、回收站、队列），搜它只会让结果被几万条运行记录淹没。

搜索根落在 `data/` 里时不排除它：显式搜 `data/` 是明确意图，那时的 `data/`
就是要看的内容，不是要剪掉的产物。

默认剪枝必须可审计：调用方拿得到剪掉几个目录，也能用 `include_derived=true`
把默认名单一起搜回来。悄悄过滤等于让结果说谎。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from agent.config import PROJECT_ROOT

#: 默认剪掉的目录名。按路径段全等匹配，不是字符串前缀（`database/` 不受影响）。
DERIVED_DIR_NAMES = frozenset({".git", "__pycache__"})

#: 当前进程根目录下的运行态数据目录。按绝对路径排除，不按名字。
RUNTIME_DATA_DIR = PROJECT_ROOT / "data"


def _canonical(path: Any) -> str:
    """路径的比较形式：绝对、规范化、按平台折叠大小写。"""
    return os.path.normcase(os.path.normpath(os.path.abspath(str(path))))


def _within(child: str, parent: str) -> bool:
    """`child` 是否等于 `parent` 或在其之下（两者均须已规范化）。"""
    return child == parent or child.startswith(parent + os.sep)


def exclude_names(extra: Iterable[str] | None = None) -> frozenset[str]:
    """调用方补充的目录名（按路径段全等匹配）。"""
    names = set()
    for item in extra or ():
        text = str(item or "").strip().strip("/\\")
        if text:
            names.add(text)
    return frozenset(names)


def relative_parts(path: Path, root: Path) -> Sequence[str]:
    """path 相对 root 的路径段；不在 root 下时返回空（调用方按不排除处理）。"""
    try:
        return path.relative_to(root).parts
    except ValueError:
        return ()


@dataclass(frozen=True)
class ScanScope:
    """一趟搜索的排除范围：按目录名 + 按进程根 `data/` 的绝对路径。

    `runtime_data` 是规范化后的绝对路径，空串表示本趟不排除它（搜索根落在
    `data/` 里时），此时只剩按名字的规则。
    """

    names: frozenset[str]
    runtime_data: str = ""

    def skip_dir(self, dirpath: Path, name: str) -> bool:
        """遍历到 `dirpath/name` 这个目录时是否整枝剪掉。"""
        if name in self.names:
            return True
        if not self.runtime_data:
            return False
        return _canonical(Path(dirpath) / name) == self.runtime_data

    def skip_path(self, path: Path, root: Path) -> bool:
        """整路径判定：glob 带目录分隔符、无法逐层剪枝时用。"""
        if self.runtime_data and _within(_canonical(path), self.runtime_data):
            return True
        return any(str(part) in self.names for part in relative_parts(path, root))


def scope(root: Path, include_derived: bool = False,
          exclude: Iterable[str] | None = None) -> ScanScope:
    """按搜索根与开关算出一趟的排除范围。

    `include_derived=true` 放开默认名单（含 `data/`），`exclude` 里点名的仍排除 ——
    显式要排除的东西不该被一个「全都搜」的开关顺手带回来。
    """
    extra = exclude_names(exclude)
    if include_derived:
        return ScanScope(extra)
    names = DERIVED_DIR_NAMES | extra
    data_key = _canonical(RUNTIME_DATA_DIR)
    if _within(_canonical(root), data_key):
        return ScanScope(names)
    return ScanScope(names, data_key)


__all__ = [
    "DERIVED_DIR_NAMES",
    "RUNTIME_DATA_DIR",
    "ScanScope",
    "exclude_names",
    "relative_parts",
    "scope",
]
