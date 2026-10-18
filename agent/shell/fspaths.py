# -*- coding: utf-8 -*-
"""路径安全与可见范围。

## 这个文件负责三件事（同一条边界）

1. 可见范围从哪来：`_normalize_roots` / `_parse_roots` / `_env_roots` /
   `_env_path` / `_default_fs_roots` —— 命令行、环境变量、默认值。
2. 一个请求的路径允不允许访问：`_resolve_fs` / `_fs_rejection`
   —— 这是安全边界；越界判定的改动面限于本文件。
3. 人看的展示形态：`_rel_to_root` / `_is_drive_root` / `_list_drives`。

## 安全语义

`_resolve_fs` 做两件事：解析（`resolve()` 展开 `..` 与符号链接）
与判界（`relative_to` 落在某个允许的根内）。任何"先拼路径再检查"的写法
都会被 `..` 绕过 —— 所以顺序是先 resolve 再判界，且判界用 `relative_to`
抛异常与否来定，不用字符串前缀比较（前缀比较会被 `/root2` 骗过 `/root`）。

导入路径：`web.py` 再导出这些名字。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agent.config import PROJECT_ROOT


def _is_drive_root(path: Path) -> bool:
    """是否盘符根（如 `C:\\`）——这种根太宽，不适合作相对路径基准。"""
    text = str(path).replace("\\", "/").rstrip("/")
    return len(text) == 2 and text[1] == ":"


def _list_drives() -> List[Dict[str, Any]]:
    """本机可用盘符（Windows「计算机」层）；非 Windows 返回空列表。"""
    items: List[Dict[str, Any]] = []
    if os.name != "nt":
        return items
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        drive = f"{letter}:\\"
        if not os.path.exists(drive):
            continue
        try:
            ready = os.path.isdir(drive)
        except OSError:
            ready = False
        name = f"{letter}:"
        name += " (本地磁盘)" if ready else " (未就绪)"
        items.append({
            "name": name,
            "type": "dir",
            "ext": "",
            "path": f"{letter}:/" if ready else drive.replace("\\", "/"),
        })
    return items


def _fs_rejection(reason: str) -> Tuple[int, Dict[str, Any]]:
    """文件查看器的拒绝响应：越界 403（安全），不存在 404（状态）。"""
    if reason == "outside":
        return 403, {"error": "path outside workspace"}
    if reason == "missing":
        return 404, {"error": "file not found"}
    return 400, {"error": "invalid path"}


def _normalize_roots(value: Any) -> List[Path]:
    """把 fs_roots 的多种入参（None / Path / str / 列表）统一成解析后的 Path 列表。"""
    if value is None:
        return []
    items = value if isinstance(value, (list, tuple, set)) else [value]
    roots: List[Path] = []
    for item in items:
        if item is None:
            continue
        try:
            roots.append(Path(item).resolve())
        except (OSError, TypeError, ValueError):
            continue
    return roots


def _within_any_root(target: Path, roots: List[Path]) -> bool:
    """目标是否落在任一可见根之内。

    可见根是多个盘根时不能只看第一个 —— 那会让别的盘上一律判越界，
    而生成物（下载的图片/视频）常常不在第一个根所在的盘上。
    """
    try:
        resolved = Path(target).resolve()
    except (OSError, ValueError):
        return False
    for root in roots or []:
        try:
            resolved.relative_to(Path(root).resolve())
            return True
        except (OSError, ValueError):
            continue
    return False


def _default_fs_roots() -> List[Path]:
    """文件查看器的默认可见根（可多个）。

    取本机存在的盘根而不是项目目录：agent 的文件工具能读写整个磁盘（无沙箱），
    查看器若只看项目目录，就会出现"agent 刚写的文件打不开"——项目盘之外的文件
    一律 403。可见范围要与 agent 的实际读写范围对齐，才谈得上"看得见它做的事"。
    越界（`..` 穿越）依然禁止，且全程只读。
    环境变量 / `--fs-root` 可显式收窄或改指。
    """
    if os.name == "nt":
        roots: List[Path] = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            drive = Path(f"{letter}:\\")
            if drive.exists():
                roots.append(drive)
        if roots:
            return roots
    return [PROJECT_ROOT.resolve()]


def _parse_roots(raw: str) -> List[Path]:
    """把 `--fs-root` / 环境变量解析成根列表；Windows 上用 `;` 分隔，其余平台用 `:`。"""
    parts = [p.strip() for p in str(raw or "").split(os.pathsep) if p.strip()]
    return [Path(p) for p in parts]


def _env_roots(name: str) -> List[Path]:
    value = os.environ.get(name, "").strip()
    return _parse_roots(value) if value else []


def _env_path(name: str) -> Optional[Path]:
    """读环境变量里的路径；空值视为未设置。"""
    value = os.environ.get(name, "").strip()
    return Path(value) if value else None


# ── 公开入口（entry 层用）─────────────────────────────────────
# 入口层不该知道 `_normalize_roots` 的优先级细节，只需"给我要用的根"。
# 这两个函数把 `--fs-root` / 环境变量 / 默认盘根的三级优先写成一处。

#: `--fs-root` 的环境变量名（帮助文案与解析共用，避免两处写死）。
FS_ROOT_ENV = "AI_AGENT_FS_ROOT"
#: `/api/media` 可读根的环境变量名。
MEDIA_ROOT_ENV = "AI_AGENT_MEDIA_ROOT"


def resolve_fs_roots(spec: Any = None) -> List[Path]:
    """解析文件可见根：显式参数 > 环境变量 > 本机盘根。"""
    return _normalize_roots(spec) or _env_roots(FS_ROOT_ENV) or _default_fs_roots()


def resolve_media_root(roots: List[Path], spec: Any = None) -> Path:
    """/api/media 可读根：显式参数 > 环境变量 > 第一个可见根。"""
    return spec or _env_path(MEDIA_ROOT_ENV) or (roots[0] if roots else Path.cwd())
