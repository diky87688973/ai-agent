# -*- coding: utf-8 -*-
"""压缩包工具：archive——list / extract / create（预览 + 统一提交执行器）。

- list：只读（标 needs_commit=False，不登记快照）；
- extract / create：预览（不落盘，结果由门控注入 confirm_id）；凭 commit_write 从快照恢复执行；
- 格式识别：扩展名 + 魔数（zip / tar / tar.gz / tar.bz2 / tar.xz）；rar 需 rarfile 可选依赖。
"""
from __future__ import annotations

import fnmatch
import io
import tarfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from agent.capabilities.registry import ToolPlugin


def _detect_format(source: Path) -> str:
    name = source.name.lower()
    if name.endswith(".tar.gz") or name.endswith(".tgz"):
        return "tar.gz"
    if name.endswith(".tar.bz2") or name.endswith(".tbz2"):
        return "tar.bz2"
    if name.endswith(".tar.xz") or name.endswith(".txz"):
        return "tar.xz"
    if name.endswith(".tar"):
        return "tar"
    if name.endswith(".zip"):
        return "zip"
    if name.endswith(".rar"):
        return "rar"
    try:
        with open(source, "rb") as f:
            magic = f.read(8)
        if magic[:2] == b"PK":
            return "zip"
        if magic[:4] == b"Rar!":
            return "rar"
        if magic[:2] == b"\x1f\x8b":
            return "tar.gz"
        if magic[:3] == b"BZh":
            return "tar.bz2"
        if magic[:6] == b"\xfd7zXZ":
            return "tar.xz"
        if magic[257:262] == b"ustar":
            return "tar"
    except OSError:
        pass
    return "unknown"


def _open_archive(source: Path, password: Optional[str] = None) -> Tuple[Any, str, Callable[[], None]]:
    """打开压缩包；返回 (arc, fmt, close_fn)。rar 需要可选依赖 rarfile。"""
    fmt = _detect_format(source)
    if not source.exists():
        raise FileNotFoundError(f"文件不存在: {source}")
    if fmt == "zip":
        arc = zipfile.ZipFile(source, "r")
        if password:
            arc.setpassword(password.encode("utf-8"))
        return arc, "zip", arc.close
    if fmt in ("tar.gz", "tar.bz2", "tar.xz", "tar"):
        mode_map = {"tar": "r", "tar.gz": "r:gz", "tar.bz2": "r:bz2", "tar.xz": "r:xz"}
        arc = tarfile.open(source, mode_map.get(fmt, "r"))
        return arc, fmt, arc.close
    if fmt == "rar":
        try:
            import rarfile
        except ImportError:
            raise ImportError("处理 .rar 需要可选依赖 rarfile：pip install rarfile")
        arc = rarfile.RarFile(source)
        if password:
            arc.setpassword(password)
        return arc, "rar", arc.close
    raise ValueError(f"无法识别的压缩格式: {source.name}（支持 ZIP / tar / tar.gz / tar.bz2 / tar.xz / rar）")


def _member_name(member: Any, fmt: str) -> str:
    return member.filename if fmt in ("zip", "rar") else member.name


def _iter_members(arc: Any, fmt: str, glob_pattern: Optional[str]) -> List[Any]:
    members = arc.infolist() if fmt in ("zip", "rar") else arc.getmembers()
    if glob_pattern:
        members = [m for m in members if fnmatch.fnmatch(_member_name(m, fmt), glob_pattern)]
    return members


def _list_archive(source: Path, password: Optional[str], glob_pattern: Optional[str]) -> Dict[str, Any]:
    arc, fmt, close_fn = _open_archive(source, password)
    try:
        entries = []
        for member in _iter_members(arc, fmt, glob_pattern):
            if fmt in ("zip", "rar"):
                name = member.filename
                entries.append(
                    {
                        "name": name,
                        "size": member.file_size,
                        "compressed_size": getattr(member, "compress_size", None),
                        "modified": datetime(*member.date_time).isoformat() if hasattr(member, "date_time") else None,
                        "is_dir": member.is_dir() if hasattr(member, "is_dir") else name.endswith("/"),
                    }
                )
            else:
                entries.append(
                    {
                        "name": member.name,
                        "size": member.size,
                        "compressed_size": None,
                        "modified": datetime.fromtimestamp(member.mtime).isoformat() if member.mtime else None,
                        "is_dir": member.isdir(),
                    }
                )
        return {
            "action": "list",
            "source": str(source),
            "format": fmt,
            "count": len(entries),
            "entries": entries,
        }
    finally:
        close_fn()


def _add_to_zip(zf: zipfile.ZipFile, root: Path, current: Path, glob_pattern: Optional[str]) -> int:
    count = 0
    if current.is_file():
        if glob_pattern is None or fnmatch.fnmatch(current.name, glob_pattern):
            name = str(current.relative_to(root.parent)) if root.is_dir() else root.name
            zf.write(current, name)
            count += 1
    else:
        for entry in sorted(current.iterdir()):
            if entry.is_file():
                if glob_pattern is None or fnmatch.fnmatch(entry.name, glob_pattern):
                    zf.write(entry, str(entry.relative_to(root.parent)))
                    count += 1
            elif entry.is_dir():
                count += _add_to_zip(zf, root, entry, glob_pattern)
    return count


def _add_to_tar(tf: tarfile.TarFile, root: Path, current: Path, glob_pattern: Optional[str]) -> int:
    count = 0
    if current.is_file():
        if glob_pattern is None or fnmatch.fnmatch(current.name, glob_pattern):
            name = str(current.relative_to(root.parent)) if root.is_dir() else root.name
            tf.add(current, name)
            count += 1
    else:
        for entry in sorted(current.iterdir()):
            if entry.is_file():
                if glob_pattern is None or fnmatch.fnmatch(entry.name, glob_pattern):
                    tf.add(entry, str(entry.relative_to(root.parent)))
                    count += 1
            elif entry.is_dir():
                count += _add_to_tar(tf, root, entry, glob_pattern)
    return count


def _count_archive_create(source: Path, fmt: str, glob_pattern: Optional[str]) -> int:
    """预览统计：内存缓冲区演练一遍，不写 dest。"""
    if fmt == "zip":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            return _add_to_zip(zf, source, source, glob_pattern)
    mode_map = {"tar.gz": "w:gz", "tar.bz2": "w:bz2", "tar.xz": "w:xz", "tar": "w"}
    mode = mode_map.get(fmt)
    if not mode:
        raise ValueError(f"不支持的输出格式: {fmt}（支持 zip / tar.gz / tar.bz2 / tar.xz / tar）")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode=mode) as tf:
        return _add_to_tar(tf, source, source, glob_pattern)


class ArchiveTool(ToolPlugin):
    """压缩包：list 只读；extract / create 预览（不落盘）。"""

    name = "archive"
    label = "压缩包操作"
    icon = "🗜️"
    description = "压缩包 list / extract / create：list 只读；extract / create 先预览（不落盘，返回 confirm_id），凭 commit_write 提交执行。"
    needs_preview = True
    write_path_keys = ("dest", "source")
    parameters = {
        "action": {"type": "string", "description": "list / extract / create"},
        "source": {"type": "string", "description": "包路径（list/extract）或待打包源路径（create）"},
        "dest": {"type": "string", "description": "extract 解压目标目录 / create 输出包路径"},
        "output_format": {"type": "string", "description": "create 输出格式（zip / tar.gz / tar.bz2 / tar.xz / tar；缺省按 dest 后缀）"},
        "password": {"type": "string", "description": "读加密包密码（zip/rar）"},
        "glob_pattern": {"type": "string", "description": "成员/文件通配过滤"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        act = str(arguments.get("action") or "").strip().lower()
        source_raw = str(arguments.get("source") or "").strip()
        if not source_raw:
            raise ValueError("缺少 source")
        src = Path(source_raw)
        password = str(arguments.get("password") or "").strip() or None
        glob_pattern = str(arguments.get("glob_pattern") or "").strip() or None

        if act == "list":
            data = _list_archive(src, password, glob_pattern)
            data["needs_commit"] = False
            return data
        if act == "extract":
            dest_raw = str(arguments.get("dest") or "").strip()
            if not dest_raw:
                raise ValueError("extract 需要 dest")
            dst = Path(dest_raw)
            arc, fmt, close_fn = _open_archive(src, password)
            try:
                count = len(_iter_members(arc, fmt, glob_pattern))
            finally:
                close_fn()
            return {
                "action": "extract",
                "source": str(src),
                "dest": str(dst),
                "format": fmt,
                "preview": True,
                "would_extract_count": count,
                "hint": "提交请用 commit_write(confirm_id=...)",
            }
        if act == "create":
            if not src.exists():
                raise FileNotFoundError(f"源不存在: {src}")
            dest_raw = str(arguments.get("dest") or "").strip()
            if not dest_raw:
                raise ValueError("create 需要 dest")
            dst = Path(dest_raw)
            fmt = str(arguments.get("output_format") or "").strip() or None
            if fmt:
                out_fmt = fmt
            else:
                out_fmt = _detect_format(dst)
                if out_fmt == "unknown":
                    out_fmt = "zip"
            count = _count_archive_create(src, out_fmt, glob_pattern)
            return {
                "action": "create",
                "source": str(src),
                "dest": str(dst),
                "format": out_fmt,
                "preview": True,
                "would_add_count": count,
                "hint": "提交请用 commit_write(confirm_id=...)",
            }
        raise ValueError(f"未知 action: {act}（须为 list / extract / create）")


# ── 提交执行器（由 commit_write 统一分派）──────────────


def _execute_archive(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """提交：执行 extract / create（真实写盘）。"""
    act = str(arguments.get("action") or "").strip().lower()
    source_raw = str(arguments.get("source") or "").strip()
    dest_raw = str(arguments.get("dest") or "").strip()
    if not source_raw or not dest_raw or act not in ("extract", "create"):
        raise ValueError("预览快照不完整：请重新预览（archive）")
    src = Path(source_raw)
    dst = Path(dest_raw)
    password = str(arguments.get("password") or "").strip() or None
    glob_pattern = str(arguments.get("glob_pattern") or "").strip() or None

    if act == "extract":
        if not src.exists():
            raise FileNotFoundError(f"文件不存在（可能已被移动）：{src}")
        arc, fmt, close_fn = _open_archive(src, password)
        try:
            members = _iter_members(arc, fmt, glob_pattern)
            dst.mkdir(parents=True, exist_ok=True)
            if fmt == "zip":
                for m in members:
                    arc.extract(m, path=dst)
            else:
                arc.extractall(dst, members=members)
            count = len(members)
        finally:
            close_fn()
        return {
            "action": "extract",
            "path": str(dst),
            "source": str(src),
            "format": fmt,
            "written": True,
            "extracted_count": count,
        }

    if not src.exists():
        raise FileNotFoundError(f"源不存在: {src}")
    fmt = str(arguments.get("output_format") or "").strip() or None
    if not fmt:
        fmt = _detect_format(dst)
        if fmt == "unknown":
            fmt = "zip"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "zip":
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
            count = _add_to_zip(zf, src, src, glob_pattern)
    elif fmt in ("tar.gz", "tar.bz2", "tar.xz", "tar"):
        mode_map = {"tar.gz": "w:gz", "tar.bz2": "w:bz2", "tar.xz": "w:xz", "tar": "w"}
        with tarfile.open(dst, mode_map[fmt]) as tf:
            count = _add_to_tar(tf, src, src, glob_pattern)
    else:
        raise ValueError(f"不支持的输出格式: {fmt}（支持 zip / tar.gz / tar.bz2 / tar.xz / tar）")
    return {
        "action": "create",
        "path": str(dst),
        "source": str(src),
        "format": fmt,
        "written": True,
        "added_count": count,
    }


def build_plugins() -> List[ToolPlugin]:
    """构造本组预览插件（archive）。"""
    return [ArchiveTool()]


def build_executors() -> Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]]:
    """构造本组提交执行器表。"""
    return {"archive": _execute_archive}
