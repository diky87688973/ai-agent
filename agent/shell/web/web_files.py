# -*- coding: utf-8 -*-
"""右栏文件查看器与本地媒体代理。"""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent.config import PROJECT_ROOT
from agent.core.error_report import report_error
from agent.shell.fspaths import (
    default_fs_roots,
    fs_rejection,
    is_drive_root,
    list_drives,
    within_any_root,
)
from agent.shell.web.web_static import lang_from_path, looks_binary


class FileViewerActions:
    """列目录、读文件、`@` 补全用的目录浏览与媒体代理；路径限定在可见根内。"""

    def fs_list(self, path: str) -> Tuple[int, Dict[str, Any]]:
        """列目录（供右栏文件树 / @ 补全）；限定在可见根内。

        `rel` 是相对命中的那个根的路径；命不中根时退回文件名。
        """
        target, reason = self._resolve_fs(path or ".", must_exist=True)
        if target is None:
            return fs_rejection(reason)
        if not target.is_dir():
            return 400, {"error": "not a directory"}
        entries: List[Dict[str, Any]] = []
        try:
            for child in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
                if child.name.startswith("."):
                    continue
                try:
                    stat = child.stat()
                except OSError as exc:
                    report_error("agent.shell.web.web_files.FileViewerActions.fs_list", exc)
                    continue
                entries.append(
                    {
                        "name": child.name,
                        "path": str(child),
                        "rel": self._rel_to_root(child),
                        "type": "dir" if child.is_dir() else "file",
                        "size": int(stat.st_size),
                        "mtime": int(stat.st_mtime),
                    }
                )
        except OSError as exc:
            return 500, {"error": f"{type(exc).__name__}"}
        return 200, {"path": str(target), "entries": entries}

    def fs_read(self, path: str, max_chars: int = 400000) -> Tuple[int, Dict[str, Any]]:
        """读文件（供右栏标签页）；文本 / 代码直读，xlsx 转表格，二进制给结构化提示。"""
        target, reason = self._resolve_fs(path, must_exist=True)
        if target is None:
            return fs_rejection(reason)
        if not target.is_file():
            return 404, {"error": "not a file"}
        suffix = target.suffix.lower()
        if suffix in (".xlsx", ".xlsm", ".xls"):
            return self._read_table(target)
        if looks_binary(target):
            return 200, {
                "path": str(target),
                "kind": "binary",
                "size": target.stat().st_size,
                "message": "二进制文件不在此处预览（图片 / 音视频请用媒体代理 /api/media）",
            }
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return 500, {"error": f"{type(exc).__name__}"}
        full = max_chars <= 0
        truncated = not full and len(text) > max_chars
        if truncated:
            text = text[:max_chars]
        try:
            stat = target.stat()
        except OSError:
            stat = None
        return 200, {
            "path": str(target),
            "kind": "text",
            "lang": lang_from_path(target.name),
            "content": text,
            "truncated": truncated,
            "size": int(stat.st_size) if stat else len(text.encode("utf-8")),
            "mtime": int(stat.st_mtime) if stat else 0,
        }

    def _read_table(self, target: Path) -> Tuple[int, Dict[str, Any]]:
        """xlsx/xls → 表格数据（缺 openpyxl 时给结构化提示，不报错）。"""
        try:
            import openpyxl  # type: ignore
        except ImportError:
            return 200, {
                "path": str(target),
                "kind": "table",
                "message": "读取 xlsx 需要 openpyxl：pip install openpyxl",
                "sheets": [],
            }
        try:
            book = openpyxl.load_workbook(str(target), read_only=True, data_only=True)
        except Exception as exc:
            report_error("agent.shell.web.web_files.FileViewerActions._read_table", exc)
            return 200, {
                "path": str(target),
                "kind": "table",
                "message": f"工作簿读取失败：{type(exc).__name__}: {exc}",
                "sheets": [],
            }
        sheets: List[Dict[str, Any]] = []
        try:
            for name in book.sheetnames:
                sheet = book[name]
                rows: List[List[str]] = []
                for index, row in enumerate(sheet.iter_rows(values_only=True)):
                    if index >= 500:
                        break
                    rows.append(["" if cell is None else str(cell) for cell in row])
                sheets.append({"name": name, "rows": rows})
        finally:
            try:
                book.close()
            except Exception as exc:
                report_error("agent.shell.web.web_files.FileViewerActions._read_table", exc)
        return 200, {"path": str(target), "kind": "table", "sheets": sheets}

    def dir_browse(self, path: str) -> Tuple[int, Dict[str, Any]]:
        """列目录供 `@` 补全：`{current, parent, items:[{name,type,ext,path}]}`。

        语义：
          - `path="_drives_"` → 列出本机盘符（Windows「计算机」层）；
          - 盘符根（如 `D:/`）的 `parent` 也是 `_drives_`（可从盘根回到计算机层）；
          - 空 `path` → `_browse_base()` 给出的基准目录；
          - 目录排前、名称不区分大小写升序；
          - 访问不到就回落（不报错），免得上层补全卡死。
        """
        base = self._browse_base()
        raw = str(path or "").strip()

        if raw == "_drives_":
            return 200, {"current": "计算机", "parent": "", "items": list_drives()}

        if not raw:
            target = base
        else:
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = base / candidate
            try:
                resolved = candidate.resolve()
            except OSError:
                resolved = base
            target = resolved if resolved.is_dir() else base

        items: List[Dict[str, Any]] = []
        try:
            entries = sorted(
                (e for e in os.scandir(str(target)) if not e.name.startswith(".")),
                key=lambda e: (not e.is_dir(), e.name.lower()),
            )
        except OSError:
            entries = []
        for entry in entries[:1000]:
            try:
                is_dir = entry.is_dir()
            except OSError as exc:
                report_error("agent.shell.web.web_files.FileViewerActions.dir_browse", exc)
                continue
            items.append({
                "name": entry.name,
                "type": "dir" if is_dir else "file",
                "ext": os.path.splitext(entry.name)[1].lower(),
                "path": os.path.abspath(entry.path).replace("\\", "/"),
            })

        current = str(target).replace("\\", "/")
        stripped = current.rstrip("/")
        # 盘符根（"D:"）→ 上一级是「计算机」层
        if len(stripped) == 2 and stripped[1] == ":":
            parent = "_drives_"
        else:
            try:
                parent = str(Path(stripped).resolve().parent).replace("\\", "/")
            except OSError:
                parent = ""
        return 200, {"current": current, "parent": parent, "items": items}

    def _browse_base(self) -> Path:
        """`@` 补全 / 相对路径的基准目录。

        可见根可能是「本机各盘根」这种很宽的范围，直接拿第一个当基准会让相对路径落在
        盘根（`agent/core` 会变成 `C:/`）。所以按具体程度挑：
        项目根（若在可见范围内）→ 进程工作目录（若在范围内）→ 第一个可见根。
        """
        roots = self.fs_roots or default_fs_roots()
        if not roots:
            return Path.cwd()

        def inside(candidate: Path) -> bool:
            try:
                resolved = candidate.resolve()
            except OSError:
                return False
            for root in roots:
                if resolved.is_relative_to(root):
                    return True
            return False

        # 显式给出的第一个根通常就是用户有意指定的工作区（夹具 / --fs-root），优先它；
        # 只有它是"太宽的根"（盘根）时才往下找更具体的位置。
        first = roots[0]
        if not is_drive_root(first) and first.is_dir():
            return first
        for candidate in (PROJECT_ROOT, Path.cwd()):
            if candidate.is_dir() and inside(candidate):
                return candidate.resolve()
        return first

    def _rel_to_root(self, target: Path) -> str:
        """相对命中的那个可见根的路径；命不中根时退回文件名。"""
        try:
            resolved = target.resolve()
        except OSError:
            return target.name
        for root in self.fs_roots:
            if resolved.is_relative_to(root):
                return str(resolved.relative_to(root))
        return target.name

    def _resolve_fs(self, path: str, *, must_exist: bool) -> Tuple[Optional[Path], str]:
        """把请求路径解析到某个可见根内（防越权读盘）。

        返回 `(目标, 原因)`；原因为 `""` 表示成功，否则是拒绝理由：
          - `"outside"`：不在任何可见根内（403，安全边界）
          - `"missing"`：在可见根内但不存在（404，状态边界）
          - `"unknown"`：路径无法解析

        相对路径依次在每个根下试（命中即用）；绝对路径只有落在某个根内才接受——
        工具参数常带绝对路径（如 D:\\proj\\a.py、E:\\test.txt），查看器应能直接打开。
        越界与"不存在"必须分开报告：预览阶段尚未落盘的文件是 404，不是越权。
        """
        roots = self.fs_roots
        raw = str(path or "").strip()
        if not raw:
            return None, "unknown"

        def inside(candidate: Path) -> bool:
            if not roots:
                return True
            try:
                resolved = candidate.resolve()
            except OSError:
                return False
            for root in roots:
                if resolved.is_relative_to(root):
                    return True
            return False

        candidate = Path(raw)
        if not candidate.is_absolute():
            # 相对路径：逐个根试，取第一个"存在"的；都不存在则报 missing
            for root in roots or [Path.cwd()]:
                joined = root / candidate
                if inside(joined):
                    if joined.exists():
                        return joined.resolve(), ""
            return None, "missing"

        if not inside(candidate):
            return None, "outside"
        if must_exist and not candidate.exists():
            return None, "missing"
        try:
            return candidate.resolve(), ""
        except OSError:
            return None, "unknown"

    def media(self, path: str, root: Optional[Path]) -> Tuple[int, Any, str]:
        """解析本地媒体文件供浏览器预览；限定在 root 之内（防越权读取）。

        返回 (status, body_bytes | error_payload, content_type)。

        `root` 为 None 时优先用显式媒体根 `media_root`，未配置时用全部可见根：
        经典界面的 Markdown 会把正文里绝对路径指向的本地文件交给 `/api/media`，
        它可能不在第一个根所在的盘上——只认单根会让别的盘一律 403。
        """
        raw = str(path or "").strip()
        if not raw:
            return 400, {"error": "missing path"}, "application/json"
        target = Path(raw)
        if root is None:
            roots = [self.media_root] if self.media_root else (self.fs_roots or default_fs_roots())
            if not within_any_root(target, roots):
                return 403, {"error": "path outside media root"}, "application/json"
        else:
            try:
                target.resolve().relative_to(Path(root).resolve())
            except (ValueError, OSError):
                return 403, {"error": "path outside media root"}, "application/json"
        if not target.is_file():
            return 404, {"error": "not found"}, "application/json"
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        try:
            return 200, target.read_bytes(), ctype
        except OSError as exc:
            return 500, {"error": f"{type(exc).__name__}"}, "application/json"
