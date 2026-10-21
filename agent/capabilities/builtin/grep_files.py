# -*- coding: utf-8 -*-
"""grep_files 工具：目录内文本内容搜索（字面含 | 分隔 / 正则）。"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from agent.capabilities.builtin.scan_scope import skip_set
from agent.capabilities.registry import ToolPlugin

DEFAULT_LIMIT = 200
_BINARY_SNIFF = "\x00"


def _iter_text_files(root: Path, skip_names: frozenset, skipped: Optional[Dict[str, int]] = None
                     ) -> Iterator[Tuple[Path, str]]:
    """遍历 root 下文本文件，产出 (path, text)；坏文件与二进制不出现在结果里。

    `skip_names` 里的目录整枝剪掉：不进入、不读、不逐文件产出 ——
    这些目录下动辄成千上万文件，逐个过滤等于让「跳过」也付出全量遍历的代价。
    `skipped` 传入字典时累计剪掉的目录数，供回执如实说明。
    """
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        if skip_names:
            kept = [name for name in dirnames if name not in skip_names]
            if skipped is not None:
                skipped["dirs"] = skipped.get("dirs", 0) + (len(dirnames) - len(kept))
            dirnames[:] = kept
        for name in sorted(filenames):
            p = Path(dirpath) / name
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if _BINARY_SNIFF in text:
                continue
            yield p, text


def _compile_pattern(pattern: str, regex: bool, ignore_case: bool):
    """构建匹配器：正则，或字面（| 为 OR 分隔）；无效返回 None。"""
    flags = re.IGNORECASE if ignore_case else 0
    if regex:
        return re.compile(pattern, flags)
    parts = [re.escape(x.strip()) for x in pattern.split("|") if x.strip()]
    if not parts:
        return None
    return re.compile("|".join(parts), flags)


class GrepFilesTool(ToolPlugin):
    """在目录内搜索文本内容。"""

    name = "grep_files"
    label = "搜索文件内容"
    icon = "🔎"
    description = (
        "按字面（| 为 OR 分隔）或正则搜索目录内文本文件内容。"
        "默认只剪掉 .git/ 与 __pycache__/ 这两类通用产物目录，"
        "剪掉了几个会在回执 skipped_derived_dirs 里如实报出；"
        "要排除别的目录（如本项目自己的临时目录）用 exclude 指定；"
        "连默认名单一起搜时传 include_derived=true。"
        "需要 gitignore 过滤 / 上下文行 / 编码嗅探时用 file_search。"
    )
    parameters = {
        "pattern": {"type": "string", "description": "搜索模式（字面或正则）"},
        "path": {"type": "string", "description": "搜索根目录，默认 ."},
        "regex": {"type": "boolean", "description": "true 时按 Python 正则解析，默认 false"},
        "ignore_case": {"type": "boolean", "description": "忽略大小写，默认 false"},
        "exclude": {
            "type": "array",
            "description": "要排除的目录名列表（按路径段全等匹配，如 [\"data\", \"build\"]）",
        },
        "include_derived": {
            "type": "boolean",
            "description": "连 .git/、__pycache__/ 默认名单一起搜，默认 false",
        },
        "limit": {"type": "integer", "description": "结果上限，默认 200"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        pattern = str(arguments.get("pattern") or "")
        if not pattern:
            raise ValueError("缺少 pattern")
        raw_path = str(arguments.get("path") or ".")
        root = Path(raw_path).resolve()
        if not root.exists():
            # 报已解析的绝对路径就够：它既指出看到了哪里，也隐式说明了相对路径怎么解析。
            raise ValueError(f"path 不存在：{root}")
        if not root.is_dir():
            # 不回显绝对路径：模型刚传的 path 还在它自己的上下文里，再贴一遍只是重复。
            raise ValueError(
                "path 是文件，本工具只搜目录。搜单个文件用 find_in_file；"
                "要取正则的每一处命中用 regex_locate。"
            )
        matcher = _compile_pattern(
            pattern, bool(arguments.get("regex")), bool(arguments.get("ignore_case"))
        )
        if matcher is None:
            raise ValueError(
                "pattern 无效：字面模式下 | 分隔后没有非空段。"
                "给一个非空 pattern；搜正则时传 regex=true。"
            )
        limit = int(arguments.get("limit") or DEFAULT_LIMIT)
        include_derived = bool(arguments.get("include_derived", False))
        raw_exclude = arguments.get("exclude")
        exclude = (
            [str(x).strip() for x in raw_exclude if str(x).strip()]
            if isinstance(raw_exclude, list) else []
        )
        skipped: Dict[str, int] = {}
        matches: List[Dict[str, Any]] = []
        truncated = False
        for file_path, text in _iter_text_files(
                root, skip_set(include_derived, exclude), skipped):
            rel = str(file_path.relative_to(root)).replace("\\", "/")
            for lineno, line in enumerate(text.splitlines(), 1):
                if not matcher.search(line):
                    continue
                if len(matches) >= limit:
                    truncated = True
                    break
                matches.append({"file": rel, "line": lineno, "text": line})
            if truncated:
                break
        return {
            "pattern": pattern,
            "root": str(root),
            "matches": matches,
            "count": len(matches),
            "truncated": truncated,
            "skipped_derived_dirs": int(skipped.get("dirs", 0)),
            "exclude": exclude,
            "include_derived": include_derived,
        }


def build() -> GrepFilesTool:
    """构造 grep_files 插件。"""
    return GrepFilesTool()
