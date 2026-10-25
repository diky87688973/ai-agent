# -*- coding: utf-8 -*-
"""Web 静态资产路径与小工具（无业务状态）。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from agent.capabilities.contributions import ASSET_SEGMENT

ASSETS_DIR = Path(__file__).resolve().parent / "web_assets"
MAX_BODY_BYTES = 4 * 1024 * 1024  # 4 MB 请求体上限
SSE_HEARTBEAT_SEC = 15.0
MODE_VALUES = ("auto", "plan", "execute")
_BINARY_SNIFF_BYTES = 4096
TITLE_SCAN_LINES = 400

_LANG_BY_EXT = {
    "py": "python", "js": "javascript", "mjs": "javascript", "cjs": "javascript",
    "ts": "typescript", "tsx": "typescript", "jsx": "javascript", "json": "json",
    "yml": "yaml", "yaml": "yaml", "xml": "xml", "html": "html", "htm": "html",
    "css": "css", "scss": "scss", "md": "markdown", "java": "java", "go": "go",
    "rs": "rust", "sql": "sql", "sh": "bash", "bat": "batch", "cmd": "batch",
    "ps1": "powershell", "toml": "ini", "ini": "ini", "cfg": "ini", "c": "c",
    "h": "c", "cpp": "cpp", "hpp": "cpp", "cs": "csharp", "rb": "ruby",
    "php": "php", "kt": "kotlin", "swift": "swift", "lua": "lua", "r": "r",
}


def lang_from_path(name: str) -> str:
    """文件名 → 高亮语言标记（未知扩展名返回空串）。"""
    suffix = Path(str(name or "")).suffix.lower().lstrip(".")
    return _LANG_BY_EXT.get(suffix, "")


def plugin_asset_rel(path: str) -> Optional[Tuple[str, str]]:
    """`/api/plugin/<插件>/_asset/<相对路径>` → `(插件名, 相对路径)`；不是资产路径则 None。"""
    prefix = "/api/plugin/"
    marker = f"/{ASSET_SEGMENT}/"
    if not str(path or "").startswith(prefix):
        return None
    rest = path[len(prefix):]
    idx = rest.find(marker)
    if idx <= 0:
        return None
    plugin = rest[:idx]
    rel = rest[idx + len(marker):]
    if not plugin or not rel or ".." in rel.split("/"):
        return None
    return plugin, rel


def looks_binary(path: Path) -> bool:
    """粗判二进制（含 NUL 字节即视为二进制；读取失败按文本处理）。"""
    try:
        with path.open("rb") as handle:
            chunk = handle.read(_BINARY_SNIFF_BYTES)
    except OSError:
        # 读不到内容时按文本处理，交给浏览器/文本路径继续；不是静默丢业务错误。
        return False
    return b"\x00" in chunk
