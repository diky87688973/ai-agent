# -*- coding: utf-8 -*-
"""glob_files 工具：按模式列出路径。"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from agent.capabilities.registry import ToolPlugin

DEFAULT_LIMIT = 200
_ENTRY_TYPES = ("file", "dir", "all")


class GlobFilesTool(ToolPlugin):
    """按 glob 模式列出目录下路径（可选递归与条目类型过滤）。"""

    name = "glob_files"
    description = "按 glob 模式列出路径；可选递归与 file/dir/all 过滤。"
    parameters = {
        "path": {"type": "string", "description": "目录根，默认 ."},
        "glob_pattern": {"type": "string", "description": "glob 模式，默认 **/*"},
        "entry_type": {"type": "string", "description": "file / dir / all，默认 file"},
        "recursive": {"type": "boolean", "description": "是否递归，默认 true"},
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
        pat = pattern[3:] if pattern.startswith("**/") else pattern
        candidates = root.rglob(pat) if recursive else root.glob(pat)
        entries: List[str] = []
        truncated = False
        for p in sorted(candidates, key=lambda x: str(x)):
            if entry_type == "file" and not p.is_file():
                continue
            if entry_type == "dir" and not p.is_dir():
                continue
            if len(entries) >= limit:
                truncated = True
                break
            entries.append(str(p.relative_to(root)).replace("\\", "/"))
        return {
            "root": str(root),
            "entries": entries,
            "count": len(entries),
            "truncated": truncated,
        }


def build() -> GlobFilesTool:
    """构造 glob_files 插件。"""
    return GlobFilesTool()
