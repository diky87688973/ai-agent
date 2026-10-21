# -*- coding: utf-8 -*-
"""定位族工具：find_in_file / regex_locate / file_search。

- find_in_file：单文件字面（| 为 OR）或正则定位，region 与行列可直接传 replace_in_file；
- regex_locate：单文件/目录正则检索（MULTILINE 恒开，可选 DOTALL/IGNORECASE）；
- file_search：大目录内容搜索（gitignore 过滤 / 编码嗅探 / 上下文行 / max_scanned 保护）；
- 不提供进度上报与中止；无进度参数时可独立运行。
"""
from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from agent.capabilities.builtin.scan_scope import relative_parts, skip_set
from agent.capabilities.registry import ToolPlugin


def _read_text(fp: Path, encoding: str) -> str:
    """整文件读取：显式编码 errors=replace；auto 按 utf-8→gb18030→gbk 尝试。"""
    if encoding and encoding != "auto":
        return fp.read_text(encoding=encoding, errors="replace")
    for enc in ("utf-8", "gb18030", "gbk"):
        try:
            return fp.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return fp.read_text(encoding="utf-8", errors="replace")


def _span_to_rowcols(full: str, s: int, e: int) -> Tuple[int, int, int, int]:
    """字符偏移 → 1-based 行列（end 开区间：end_column 指向尾后一列）。"""
    sl = full.count("\n", 0, s) + 1
    sc = s - (full.rfind("\n", 0, s) + 1) + 1
    el = full.count("\n", 0, e) + 1
    ec = e - (full.rfind("\n", 0, e) + 1) + 1
    return sl, sc, el, ec


def _collect_spans(full: str, pattern: str, *, regex: bool, ignore_case: bool) -> List[Tuple[int, int, str]]:
    """命中收集：字面 | 为 OR（逐段转义）；正则恒含 MULTILINE。"""
    spans: List[Tuple[int, int, str]] = []
    if not regex:
        if not pattern:
            raise ValueError(
                "pattern 不能为空（字面模式）：给一个非空 pattern；"
                "要按正则匹配传 regex=true。"
            )
        flags = re.IGNORECASE if ignore_case else 0
        parts = [re.escape(p) for p in pattern.split("|") if p]
        rx = re.compile("|".join(parts), flags) if parts else re.compile(re.escape(pattern), flags)
        for m in rx.finditer(full):
            s, e = m.span()
            spans.append((s, e, full[s:e]))
        return spans
    flags = re.MULTILINE
    if ignore_case:
        flags |= re.IGNORECASE
    try:
        rx = re.compile(pattern, flags)
    except re.error as ex:
        raise ValueError(f"正则无效: {ex}")
    for m in rx.finditer(full):
        s, e = m.span()
        spans.append((s, e, full[s:e]))
    return spans


def _collect_source_files(root: Path, glob_pattern: str, recursive: bool) -> List[Path]:
    """目录文件收集：glob 过滤；**/ 前缀自动开递归；排序确定。"""
    pattern = str(glob_pattern or "").strip()
    if pattern.startswith("**/"):
        pattern = pattern[3:]
        recursive = True
    if pattern:
        it = root.rglob(pattern) if recursive else root.glob(pattern)
    else:
        it = root.rglob("*") if recursive else root.glob("*")
    return sorted(p for p in it if p.is_file())


def _iter_source_files(root: Path, glob_pattern: str, recursive: bool,
                       skip_names: frozenset,
                       skipped: Optional[Dict[str, int]] = None
                       ) -> Iterator[Path]:
    """按搜索范围收集文件，产出 path（`skip_names` 里的目录默认整枝剪掉）。

    剪枝而不是收进来再过滤：这些目录下动辄上万文件，逐个过滤等于让
    「跳过」也付出全量遍历的代价。`skipped` 传入字典时累计跳过数量：
    剪枝时记 `dirs`（目录数），带目录分隔符的通配无法按名字剪枝，
    退回原收集器逐个判定并记 `files`（文件数）。
    """
    pattern = str(glob_pattern or "").strip()
    if pattern.startswith("**/"):
        pattern = pattern[3:]
        recursive = True
    if pattern and ("/" in pattern or "\\" in pattern):
        for path in _collect_source_files(root, pattern, recursive):
            if any(str(part) in skip_names for part in relative_parts(path, root)):
                if skipped is not None and path.is_file():
                    skipped["files"] = skipped.get("files", 0) + 1
                continue
            yield path
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        if not recursive:
            dirnames[:] = []
        if skip_names:
            kept = [name for name in dirnames if name not in skip_names]
            if skipped is not None:
                skipped["dirs"] = skipped.get("dirs", 0) + (len(dirnames) - len(kept))
            dirnames[:] = kept
        for name in sorted(filenames):
            if pattern and not fnmatch.fnmatch(name, pattern):
                continue
            yield Path(dirpath) / name


class FindInFileTool(ToolPlugin):
    """单文件定位。"""

    name = "find_in_file"
    label = "定位文件内文本"
    icon = "🎯"
    description = "在单个文件内定位字面（| 为 OR）或正则的第 N 处命中，返回 region 与行列（可直接传 replace_in_file）。"
    parameters = {
        "path": {"type": "string", "description": "目标文件路径"},
        "pattern": {"type": "string", "description": "查找模式（字面或正则）"},
        "regex": {"type": "boolean", "description": "按正则解析（默认 false 字面）"},
        "ignore_case": {"type": "boolean", "description": "忽略大小写"},
        "occurrence": {"type": "integer", "description": "取第几处命中（0-based，默认 0）"},
        "encoding": {"type": "string", "description": "文件编码（utf-8 / auto 等，默认 utf-8）"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw_path = str(arguments.get("path") or "").strip()
        if not raw_path:
            raise ValueError("缺少 path")
        fp = Path(raw_path)
        if not fp.exists():
            raise FileNotFoundError(f"文件不存在：{fp.resolve()}")
        if not fp.is_file():
            raise ValueError(
                "path 是目录，本工具只处理单个文件。在目录里搜内容用 grep_files；"
                "只列文件名用 glob_files。"
            )
        pattern = str(arguments.get("pattern") or "")
        regex = bool(arguments.get("regex", False))
        encoding = str(arguments.get("encoding") or "utf-8")
        try:
            occurrence = int(arguments.get("occurrence") or 0)
        except (TypeError, ValueError):
            raise ValueError("occurrence 须为整数")
        full = _read_text(fp, encoding)
        spans = _collect_spans(full, pattern, regex=regex, ignore_case=bool(arguments.get("ignore_case", False)))
        total = len(spans)
        if total == 0:
            return {
                "path": str(fp),
                "found": False,
                "pattern": pattern,
                "regex": regex,
                "total_matches": 0,
                "occurrence": occurrence,
                "region_start": None,
                "region_end": None,
                "matched_text": None,
                "hint": "未命中：缩小/调整 pattern，或先 grep 再改 occurrence；目录搜索请用 grep_files。",
            }
        if occurrence < 0 or occurrence >= total:
            raise ValueError(f"occurrence 越界: 请求 {occurrence}，当前共 {total} 处命中（0-based）")
        rs, re_, matched = spans[occurrence]
        sl, sc, el, ec = _span_to_rowcols(full, rs, re_)
        return {
            "path": str(fp),
            "found": True,
            "pattern": pattern,
            "regex": regex,
            "total_matches": total,
            "occurrence": occurrence,
            "region_start": rs,
            "region_end": re_,
            "matched_text": matched,
            "matched_length": re_ - rs,
            "start_line": sl,
            "start_column": sc,
            "end_line": el,
            "end_column": ec,
            "hint": "将 region_start、region_end 原样传入 replace_in_file；end_line/end_column 与行列矩形替换一致（end_column 为开区间）。",
        }


class RegexLocateTool(ToolPlugin):
    """单文件/目录正则定位。"""

    name = "regex_locate"
    label = "正则检索与定位"
    icon = "🔍"
    description = "在单文件或目录下用正则检索，每条命中返回 region 与行列（与 find_in_file / replace_in_file 语义一致）。"
    parameters = {
        "path": {"type": "string", "description": "文件或目录路径"},
        "pattern": {"type": "string", "description": "Python 正则表达式"},
        "ignore_case": {"type": "boolean", "description": "忽略大小写（re.IGNORECASE）"},
        "dotall": {"type": "boolean", "description": ". 匹配换行（re.DOTALL）"},
        "recursive": {"type": "boolean", "description": "目录下递归（默认 true）"},
        "glob_pattern": {"type": "string", "description": "文件名通配过滤（如 *.py）"},
        "encoding": {"type": "string", "description": "文件编码（默认 utf-8；auto 嗅探）"},
        "limit": {"type": "integer", "description": "命中上限（默认 200）"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw_path = str(arguments.get("path") or "").strip()
        if not raw_path:
            raise ValueError("缺少 path")
        pattern = str(arguments.get("pattern") or "")
        if not pattern:
            raise ValueError(
                "pattern 不能为空：regex_locate 按正则匹配，空正则会命中每个位置。"
                "给一个非空正则。"
            )
        raw_limit = arguments.get("limit")
        try:
            limit = int(raw_limit) if raw_limit is not None and str(raw_limit).strip() != "" else 200
        except (TypeError, ValueError):
            raise ValueError("limit 须为整数")
        if limit <= 0:
            raise ValueError("limit 必须 > 0")
        root = Path(raw_path).resolve()
        if not root.exists():
            raise FileNotFoundError(f"路径不存在：{root}")
        flags = re.MULTILINE
        if bool(arguments.get("ignore_case", False)):
            flags |= re.IGNORECASE
        if bool(arguments.get("dotall", False)):
            flags |= re.DOTALL
        try:
            rx = re.compile(pattern, flags)
        except re.error as ex:
            raise ValueError(f"正则无效: {ex}")
        encoding = str(arguments.get("encoding") or "utf-8")
        if root.is_file():
            files = [root]
        else:
            files = _collect_source_files(root, str(arguments.get("glob_pattern") or ""), bool(arguments.get("recursive", True)))
        items: List[Dict[str, Any]] = []
        for fp in files:
            if len(items) >= limit:
                break
            try:
                text = _read_text(fp, encoding)
            except OSError:
                continue
            for m in rx.finditer(text):
                if len(items) >= limit:
                    break
                s, e = m.span()
                sl, sc, el, ec = _span_to_rowcols(text, s, e)
                items.append(
                    {
                        "file": str(fp),
                        "region_start": s,
                        "region_end": e,
                        "line": sl,
                        "column": sc,
                        "end_line": el,
                        "end_column": ec,
                        "match": m.group(0),
                    }
                )
        return {
            "count": len(items),
            "items": items,
            "truncated": len(items) >= limit,
            "hint": "单文件改写给 replace_in_file 时复制对应条目的 region_start、region_end；与 find_in_file 语义一致。",
        }


class FileSearchTool(ToolPlugin):
    """大目录内容搜索。"""

    name = "file_search"
    label = "搜索文件内容"
    icon = "🔎"
    description = (
        "目录或单文件内容搜索（字面/正则）；支持 gitignore 过滤、编码嗅探与上下文行；"
        "适合大范围扫描。简单精确匹配用 grep_files。"
    )
    parameters = {
        "path": {"type": "string", "description": "目录或单文件路径"},
        "pattern": {"type": "string", "description": "查找模式（字面 | 为 OR，或正则）"},
        "regex": {"type": "boolean", "description": "按正则解析（默认 false 字面）"},
        "glob_pattern": {"type": "string", "description": "文件名通配过滤（如 *.py）"},
        "recursive": {"type": "boolean", "description": "目录下递归（默认 true）"},
        "context_lines": {"type": "integer", "description": "命中前后附带的上下文行数"},
        "ignore_case": {"type": "boolean", "description": "忽略大小写"},
        "no_gitignore": {"type": "boolean", "description": "true 时不按 .gitignore 过滤"},
        "exclude": {
            "type": "array",
            "description": "要排除的目录名列表（按路径段全等匹配，如 [\"data\", \"build\"]）",
        },
        "include_derived": {
            "type": "boolean",
            "description": "连 .git/、__pycache__/ 默认名单一起搜，默认 false",
        },
        "limit": {"type": "integer", "description": "命中上限（缺省不限）"},
    }

    MAX_SCANNED = 10000

    def _load_gitignore(self, root: Path) -> List[re.Pattern]:
        patterns: List[re.Pattern] = []
        fp = root / ".gitignore"
        if not fp.is_file():
            return patterns
        try:
            text = fp.read_text("utf-8")
        except OSError:
            return patterns
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("/"):
                line = line[1:]
            is_dir = line.endswith("/")
            if is_dir:
                line = line[:-1]
            regex = fnmatch.translate(line)
            if "/" not in line:
                regex = f"(?:.*[/\\\\])?{regex}"
            else:
                regex = f"^{regex}"
            if is_dir:
                regex += "(?:[/\\\\].*)?$"
            else:
                regex += "$"
            try:
                patterns.append(re.compile(regex, re.IGNORECASE))
            except re.error:
                pass
        return patterns

    @staticmethod
    def _is_ignored(rel_path: str, ignore_patterns: List[re.Pattern]) -> bool:
        rel = rel_path.replace("\\", "/")
        return any(p.search(rel) for p in ignore_patterns)

    @staticmethod
    def _detect_encoding(path: Path) -> str:
        try:
            with open(path, "rb") as f:
                raw = f.read(8192)
            if raw.startswith(b"\xef\xbb\xbf"):
                return "utf-8-sig"
            if raw.startswith(b"\xff\xfe"):
                return "utf-16-le"
            if raw.startswith(b"\xfe\xff"):
                return "utf-16-be"
            raw.decode("utf-8")
            return "utf-8"
        except (OSError, UnicodeDecodeError):
            pass
        return "gbk"

    def _search_file(self, path: Path, pattern: re.Pattern, context_lines: int, limit: Any) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        try:
            enc = self._detect_encoding(path)
            with open(path, "r", encoding=enc, errors="replace") as f:
                lines = f.readlines()
        except (OSError, UnicodeDecodeError) as e:
            return [{"file": str(path), "error": str(e)}]
        total = len(lines)
        starts: List[int] = []
        cur = 0
        for ln in lines:
            starts.append(cur)
            cur += len(ln)
        for lineno, line in enumerate(lines, 1):
            if limit is not None and len(results) >= int(limit):
                break
            m = pattern.search(line)
            if not m:
                continue
            ctx_before = [
                {"line": i + 1, "text": lines[i].rstrip("\n").rstrip("\r")}
                for i in range(max(0, lineno - 1 - context_lines), lineno - 1)
            ]
            ctx_after = [
                {"line": i + 1, "text": lines[i].rstrip("\n").rstrip("\r")}
                for i in range(lineno, min(total, lineno + context_lines))
            ]
            results.append(
                {
                    "file": str(path),
                    "line": lineno,
                    "column": m.start() + 1,
                    "text": line.rstrip("\n").rstrip("\r"),
                    "match": m.group(),
                    "region_start": starts[lineno - 1] + m.start(),
                    "region_end": starts[lineno - 1] + m.end(),
                    "context_before": ctx_before,
                    "context_after": ctx_after,
                }
            )
        return results

    def _search_tree(self, target: Path, compiled: re.Pattern, context_lines: int,
                     limit: Any, arguments: Dict[str, Any], exclude: List[str]
                     ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int, int, Dict[str, int]]:
        """目录分支：收集范围 + gitignore 过滤 + 逐文件搜索。

        返回 (命中, 错误, 扫描文件数, 命中文件数, 跳过统计)。抽出来是为了让
        `execute` 只负责参数解析与回执拼装 —— 两个分支的回执字段必须逐字对齐，
        逻辑混在一起时最容易漏改一边。

        `exclude` 由 `execute` 解析后传进来：回执要原样回显它，
        两处各解析一份必然漂移。
        """
        ignore_patterns = [] if bool(arguments.get("no_gitignore", False)) else self._load_gitignore(target)
        results: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        scanned = 0
        matched_files = 0
        skipped: Dict[str, int] = {}
        for entry in _iter_source_files(
            target,
            str(arguments.get("glob_pattern") or ""),
            bool(arguments.get("recursive", True)),
            skip_set(bool(arguments.get("include_derived", False)), exclude),
            skipped,
        ):
            if ignore_patterns:
                try:
                    rel = entry.relative_to(target)
                    if self._is_ignored(str(rel), ignore_patterns):
                        continue
                except ValueError:
                    pass
            file_results = self._search_file(entry, compiled, context_lines, limit)
            scanned += 1
            if self.MAX_SCANNED and scanned >= self.MAX_SCANNED:
                break
            if file_results:
                if any("error" in r for r in file_results):
                    errors.extend(r for r in file_results if "error" in r)
                else:
                    matched_files += 1
                    results.extend(file_results)
            if limit is not None and len(results) >= limit:
                results = results[:limit]
                break
        return results, errors, scanned, matched_files, skipped

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw_path = str(arguments.get("path") or "").strip()
        if not raw_path:
            raise ValueError("缺少 path")
        target = Path(raw_path).resolve()
        if not target.exists():
            raise FileNotFoundError(f"路径不存在：{target}")
        pattern = str(arguments.get("pattern") or "")
        if not pattern:
            raise ValueError(
                "pattern 不能为空：空 pattern 会把每个位置都算成命中。给一个非空 pattern。"
            )
        raw_exclude = arguments.get("exclude")
        exclude = (
            [str(x).strip() for x in raw_exclude if str(x).strip()]
            if isinstance(raw_exclude, list) else []
        )
        regex = bool(arguments.get("regex", False))
        flags = re.IGNORECASE if bool(arguments.get("ignore_case", False)) else 0
        if regex:
            try:
                compiled = re.compile(pattern, flags)
            except re.error as ex:
                raise ValueError(f"正则无效: {ex}")
        else:
            parts = [re.escape(p) for p in pattern.split("|") if p]
            compiled = re.compile("|".join(parts), flags) if parts else re.compile(re.escape(pattern), flags)
        try:
            context_lines = max(0, int(arguments.get("context_lines") or 0))
        except (TypeError, ValueError):
            raise ValueError("context_lines 须为整数")
        raw_limit = arguments.get("limit")
        limit: Any = None
        if raw_limit is not None and str(raw_limit).strip() != "":
            try:
                limit = int(raw_limit)
            except (TypeError, ValueError):
                raise ValueError("limit 须为整数")
            if limit <= 0:
                raise ValueError("limit 必须 > 0")
        hint = "matches 中的 region_start/region_end 可直接传给 replace_in_file；大范围只定位时优先 file_search，轻量搜索优先 grep_files。"
        if target.is_file():
            results = self._search_file(target, compiled, context_lines, limit)
            return {
                "path": str(target),
                "pattern": pattern,
                "scanned_files": 1,
                "matched_files": 1 if results else 0,
                "total_matches": len(results),
                "matches": results,
                "errors": None,
                "skipped_derived_dirs": 0,
                "skipped_derived_files": 0,
                "exclude": exclude,
                "include_derived": bool(arguments.get("include_derived", False)),
                "hint": hint,
            }
        results, errors, scanned, matched_files, skipped = self._search_tree(
            target, compiled, context_lines, limit, arguments, exclude)
        return {
            "path": str(target),
            "pattern": pattern,
            "scanned_files": scanned,
            "matched_files": matched_files,
            "total_matches": len(results),
            "matches": results,
            "errors": errors if errors else None,
            "skipped_derived_dirs": int(skipped.get("dirs", 0)),
            "skipped_derived_files": int(skipped.get("files", 0)),
            "exclude": exclude,
            "include_derived": bool(arguments.get("include_derived", False)),
            "hint": hint,
        }


def build_plugins() -> List[ToolPlugin]:
    """构造本组工具（find_in_file / regex_locate / file_search）。"""
    return [FindInFileTool(), RegexLocateTool(), FileSearchTool()]
