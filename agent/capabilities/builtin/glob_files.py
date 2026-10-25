# -*- coding: utf-8 -*-
"""glob_files 工具：按模式列出路径。"""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any, Dict, List

from agent.capabilities.builtin.scan_scope import skip_set
from agent.capabilities.registry import ToolPlugin

DEFAULT_LIMIT = 200
_ENTRY_TYPES = ("file", "dir", "all")


def _matches(rel: Path, pattern: str) -> bool:
    """按 basename 或无斜杠模式匹配；带目录的模式按相对路径匹配。"""
    if pattern in ("*", "**/*"):
        return True
    if "/" not in pattern:
        return fnmatch.fnmatch(rel.name, pattern)
    return bool(rel.match(pattern)) or fnmatch.fnmatch(rel.as_posix(), pattern)


def _candidates(root: Path, pattern: str, recursive: bool,
                skip_names: frozenset, skipped: Dict[str, int]) -> List[Path]:
    """遍历候选路径；跳过目录整枝剪掉并计数。"""
    out: List[Path] = []
    if not recursive:
        for path in root.glob(pattern):
            if path.is_dir() and path.name in skip_names:
                skipped["dirs"] = skipped.get("dirs", 0) + 1
                continue
            out.append(path)
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        kept = []
        for name in dirnames:
            if name in skip_names:
                skipped["dirs"] = skipped.get("dirs", 0) + 1
                continue
            kept.append(name)
        dirnames[:] = kept
        base = Path(dirpath)
        for name in sorted(dirnames + filenames):
            path = base / name
            rel = path.relative_to(root)
            if _matches(rel, pattern):
                out.append(path)
    return out


class GlobFilesTool(ToolPlugin):
    """按 glob 模式列出目录下路径（可选递归与条目类型过滤）。"""

    name = "glob_files"
    label = "列出路径"
    icon = "📂"
    description = (
        "按 glob 模式列出路径；可选递归与 file/dir/all 过滤。"
        "默认只剪掉 .git/ 与 __pycache__/ 两类通用产物目录，"
        "剪掉的目录数在回执 skipped_derived_dirs 中报出；"
        "要用 include_derived=true 连默认名单一起列出。"
    )
    parameters = {
        "path": {"type": "string", "description": "目录根，默认 ."},
        "glob_pattern": {"type": "string", "description": "glob 模式，默认 **/*"},
        "entry_type": {"type": "string", "description": "file / dir / all，默认 file"},
        "recursive": {"type": "boolean", "description": "是否递归，默认 true"},
        "exclude": {
            "type": "array",
            "description": "额外排除的目录名（按路径段全等匹配）",
        },
        "include_derived": {
            "type": "boolean",
            "description": "连 .git/、__pycache__/ 默认名单一起列出，默认 false",
        },
        "limit": {"type": "integer", "description": "条数上限，默认 200"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        root = Path(str(arguments.get("path") or ".")).resolve()
        if not root.is_dir():
            raise ValueError(f"path 不是目录：{root}")
        pattern = str(arguments.get("glob_pattern") or "**/*").strip() or "**/*"
        recursive = bool(arguments.get("recursive", True))
        entry_type = str(arguments.get("entry_type") or "file").strip().lower()
        if entry_type not in _ENTRY_TYPES:
            raise ValueError(f"entry_type 需为 {_ENTRY_TYPES} 之一：{entry_type}")
        limit = int(arguments.get("limit") or DEFAULT_LIMIT)
        include_derived = bool(arguments.get("include_derived", False))
        raw_exclude = arguments.get("exclude")
        exclude = (
            [str(x).strip() for x in raw_exclude if str(x).strip()]
            if isinstance(raw_exclude, list) else []
        )
        skipped: Dict[str, int] = {}
        pat = pattern[3:] if pattern.startswith("**/") else pattern
        candidates = _candidates(
            root, pat, recursive, skip_set(include_derived, exclude), skipped
        )
        entries: List[str] = []
        truncated = False
        for path in sorted(candidates, key=lambda x: str(x)):
            if entry_type == "file" and not path.is_file():
                continue
            if entry_type == "dir" and not path.is_dir():
                continue
            if len(entries) >= limit:
                truncated = True
                break
            entries.append(str(path.relative_to(root)).replace("\\", "/"))
        return {
            "root": str(root),
            "entries": entries,
            "count": len(entries),
            "truncated": truncated,
            "skipped_derived_dirs": int(skipped.get("dirs", 0)),
            "exclude": exclude,
            "include_derived": include_derived,
        }


def build() -> GlobFilesTool:
    """构造 glob_files 插件。"""
    return GlobFilesTool()
