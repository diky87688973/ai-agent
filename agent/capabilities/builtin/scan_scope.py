# -*- coding: utf-8 -*-
"""搜索范围：默认剪枝目录 + 调用方自定的排除名单（grep_files / file_search 共用）。

只把业界共识的产物目录放进默认名单：`.git/` 是版本库内部结构，
`__pycache__/` 是 Python 字节码缓存。除此以外一概不替调用方做主——
某个目录是不是「没用的临时产物」取决于具体项目，工具不知道，
所以不猜：要排除什么，用 `exclude` 明说。

默认剪枝必须可审计：调用方拿得到剪掉了几个目录，也能用
`include_derived=true` 把默认名单一起搜回来。悄悄过滤等于让结果说谎。
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

#: 默认剪掉的目录名。只收跨项目通用的产物目录，不含任何业务目录名。
DERIVED_DIR_NAMES = frozenset({".git", "__pycache__"})


def exclude_names(extra: Iterable[str] | None = None) -> frozenset[str]:
    """默认名单 + 调用方补充的目录名（按路径段全等匹配，不是字符串前缀）。"""
    names = set(DERIVED_DIR_NAMES)
    for item in extra or ():
        text = str(item or "").strip().strip("/\\")
        if text:
            names.add(text)
    return frozenset(names)


def skip_set(include_derived: bool, exclude: Iterable[str] | None = None) -> frozenset[str]:
    """这一趟要剪掉的目录名集合。

    `include_derived=true` 只放开默认名单，`exclude` 里点名的仍然排除 ——
    显式要排除的东西不该被一个「全都搜」的开关顺手带回来。
    """
    if include_derived:
        return exclude_names(exclude) - DERIVED_DIR_NAMES
    return exclude_names(exclude)


def relative_parts(path: Path, root: Path) -> Sequence[str]:
    """path 相对 root 的路径段；不在 root 下时返回空（调用方按不排除处理）。"""
    try:
        return path.relative_to(root).parts
    except ValueError:
        return ()


def should_skip(path: Path, root: Path, include_derived: bool,
                exclude: Iterable[str] | None = None) -> bool:
    """是否该跳过这个文件（用于 glob 含分隔符、无法按目录名剪枝的场合）。"""
    names = skip_set(include_derived, exclude)
    return any(str(part) in names for part in relative_parts(path, root))
