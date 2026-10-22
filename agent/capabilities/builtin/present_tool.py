# -*- coding: utf-8 -*-
"""present 工具：把已有文件展示为对话区文件卡片。"""
from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Dict, List

from agent.capabilities.registry import ToolPlugin

MAX_FILES = 20

_KIND_BY_SUFFIX = {
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
    ".webp": "image", ".bmp": "image", ".svg": "image",
    ".mp4": "video", ".mov": "video", ".webm": "video", ".avi": "video", ".mkv": "video",
    ".mp3": "audio", ".wav": "audio", ".flac": "audio", ".ogg": "audio", ".m4a": "audio",
    ".csv": "table", ".tsv": "table", ".xlsx": "table", ".xls": "table",
    ".zip": "archive", ".7z": "archive", ".rar": "archive", ".tar": "archive",
    ".gz": "archive", ".tgz": "archive",
    ".pdf": "pdf",
}


def _kind(path: Path) -> str:
    return _KIND_BY_SUFFIX.get(path.suffix.lower(), "file")


def _file_entry(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, str):
        raw = {"path": raw}
    if not isinstance(raw, dict):
        raise ValueError("files 中每一项必须是 path 或 {path, title}")
    value = str(raw.get("path") or "").strip()
    if not value:
        raise ValueError("files 中的 path 不能为空")
    target = Path(value)
    if not target.is_file():
        raise FileNotFoundError(f"文件不存在或不是文件：{target}")
    target = target.resolve()
    stat = target.stat()
    mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    title = str(raw.get("title") or "").strip() or target.name
    return {
        "path": str(target),
        "name": target.name,
        "title": title,
        "size": int(stat.st_size),
        "mime": mime,
        "kind": _kind(target),
    }


class PresentTool(ToolPlugin):
    """展示文件卡片；只返回元信息，不读取文件正文。"""

    name = "present"
    label = "展示文件"
    icon = "📎"
    description = (
        "在对话区展示一个或多个文件的卡片，用户可点击在右侧查看。"
        "只校验路径并返回文件元信息，不读取正文；适合展示刚生成或修改的文件。"
    )
    parameters = {
        "files": {
            "type": "array",
            "description": "要展示的文件列表",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "title": {"type": "string", "description": "卡片标题；缺省用文件名"},
                },
                "required": ["path"],
            },
        },
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw = arguments.get("files")
        if not isinstance(raw, list) or not raw:
            raise ValueError("缺少 files 列表")
        if len(raw) > MAX_FILES:
            raise ValueError(f"files 最多 {MAX_FILES} 个")
        files: List[Dict[str, Any]] = [_file_entry(item) for item in raw]
        return {"files": files, "count": len(files)}


def build() -> PresentTool:
    """构造 present 插件。"""
    return PresentTool()
