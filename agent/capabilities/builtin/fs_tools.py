# -*- coding: utf-8 -*-
"""文件系统工具组：delete_file / file_ops / file_undo——预览 + 统一提交执行器。

- delete_file：安全删除（移入回收目录，可恢复；目录请用 file_ops）；
- file_ops：copy / move / rename / delete（拒绝覆盖既有目标；delete 目录须 recursive=true）；
- file_undo：list / diff 只读（结果标 needs_commit=False，门控不登记快照）；undo 预览 + 提交
  回滚（回滚前自动备份当前版本，可逆）。
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List

from agent.capabilities.registry import ToolPlugin
from agent.mechanisms.file_safety import FileBackups, Recycle
from agent.mechanisms.quality_gate import diff_text


def _norm_path(value: Any) -> str:
    """路径规范化（统一斜杠、去首尾空白）。"""
    return str(value or "").replace("\\", "/").strip()


# ── delete_file ────────────────────────────────────────


class DeleteFileTool(ToolPlugin):
    """预览：安全删除（移入回收目录），不落盘。"""

    name = "delete_file"
    description = "预览安全删除（不落盘）：文件将移入回收目录（可恢复）；目录请用 `file_ops(action=delete, recursive=true)`；返回 confirm_id，凭 commit_write 提交。"
    parameters = {
        "path": {"type": "string", "description": "待删除文件路径"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw = str(arguments.get("path") or "").strip()
        if not raw:
            raise ValueError("缺少 path")
        target = Path(raw)
        if not target.exists():
            raise FileNotFoundError(f"路径不存在：{target}")
        if target.is_dir():
            raise ValueError("delete_file 仅用于文件；目录请用 file_ops(action=delete, recursive=true)")
        return {"path": str(target), "preview": True, "bytes": target.stat().st_size}


# ── file_ops ───────────────────────────────────────────


_OPS_ACTIONS = ("copy", "move", "rename", "delete")


def _validate_ops(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """校验 file_ops 参数；返回 {action, source, dest, recursive}；失败抛 ValueError。"""
    action = str(arguments.get("action") or "").strip().lower()
    if action not in _OPS_ACTIONS:
        raise ValueError(f"action 必须是 {' / '.join(_OPS_ACTIONS)} 之一")
    source_raw = str(arguments.get("source") or "").strip()
    if not source_raw:
        raise ValueError("缺少 source")
    source = Path(source_raw)
    if not source.exists():
        raise FileNotFoundError(f"源路径不存在：{source}")
    recursive = bool(arguments.get("recursive", False))
    if action == "delete":
        if source.is_dir() and not recursive:
            raise ValueError("删除目录须传 recursive=true")
        return {"action": action, "source": source, "dest": None, "recursive": recursive}
    dest_raw = str(arguments.get("dest") or "").strip()
    if not dest_raw:
        raise ValueError(f"{action} 缺少 dest")
    dest = Path(dest_raw)
    if dest.exists():
        raise ValueError(f"目标已存在，拒绝覆盖：{dest}")
    if dest.resolve() == source.resolve():
        raise ValueError("source 与 dest 不能相同")
    return {"action": action, "source": source, "dest": dest, "recursive": recursive}


class FileOpsTool(ToolPlugin):
    """预览：copy / move / rename / delete（不落盘）。"""

    name = "file_ops"
    description = "预览文件操作（不落盘）：copy / move / rename / delete（delete 移入回收目录，可恢复；delete 目录须 `recursive=true`）；返回 confirm_id，凭 commit_write 提交。"
    parameters = {
        "action": {"type": "string", "description": "copy / move / rename / delete"},
        "source": {"type": "string", "description": "源路径（必填）"},
        "dest": {"type": "string", "description": "目标路径（delete 时勿传）"},
        "recursive": {"type": "boolean", "description": "删除目录须传 true"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        plan = _validate_ops(arguments)
        info: Dict[str, Any] = {
            "action": plan["action"],
            "source": str(plan["source"]),
            "preview": True,
        }
        if plan["dest"] is not None:
            info["dest"] = str(plan["dest"])
        return info


# ── file_undo ──────────────────────────────────────────


class FileUndoTool(ToolPlugin):
    """版本回滚工具：list / diff 只读；undo 预览（提交后执行回滚）。"""

    name = "file_undo"
    description = "版本回滚：`action=list` 列某文件历史备份（只读）；`action=diff` 比对备份与当前（只读）；`action=undo` + `mod_id` + `path` 预览回滚（不落盘，返回 confirm_id，凭 commit_write 提交；回滚前自动备份当前版本）。"
    parameters = {
        "action": {"type": "string", "description": "list / diff / undo"},
        "path": {"type": "string", "description": "文件路径（list / undo 必填；diff 可选）"},
        "mod_id": {"type": "string", "description": "备份版本 ID（diff / undo 必填，来自 list 或写盘结果）"},
    }

    def __init__(self, backups: FileBackups) -> None:
        self._backups = backups

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        action = str(arguments.get("action") or "").strip().lower()
        if action == "list":
            raw = str(arguments.get("path") or "").strip()
            if not raw:
                raise ValueError("list 需要 path")
            versions = [
                {"mod_id": v.get("mod_id"), "time": v.get("time"), "bytes": v.get("bytes")}
                for v in self._backups.list_for(Path(raw))
            ]
            return {"action": "list", "path": raw, "versions": versions, "count": len(versions), "needs_commit": False}
        if action == "diff":
            mid = str(arguments.get("mod_id") or "").strip()
            if not mid:
                raise ValueError("diff 需要 mod_id")
            record = self._backups.meta(mid)
            if record is None:
                raise ValueError(f"mod_id 不存在或已过期：{mid}")
            old = self._backups.read(mid)
            if old is None:
                raise ValueError(f"备份内容缺失：{mid}")
            target = Path(str(arguments.get("path") or record.get("path") or ""))
            current = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
            diff = diff_text(current, old.decode("utf-8", errors="replace"), str(target))
            limit = 4000
            return {
                "action": "diff",
                "path": str(target),
                "mod_id": mid,
                "diff": diff[:limit],
                "truncated": len(diff) > limit,
                "needs_commit": False,
            }
        if action == "undo":
            mid = str(arguments.get("mod_id") or "").strip()
            path_raw = str(arguments.get("path") or "").strip()
            if not mid or not path_raw:
                raise ValueError("undo 需要 mod_id 与 path")
            record = self._backups.meta(mid)
            if record is None:
                raise ValueError(f"mod_id 不存在或已过期：{mid}")
            if _norm_path(Path(path_raw).resolve()) != _norm_path(record.get("path")):
                raise ValueError(f"mod_id 与 path 不匹配（该备份属于：{record.get('path')}）")
            old = self._backups.read(mid)
            if old is None:
                raise ValueError(f"备份内容缺失：{mid}")
            return {
                "action": "undo",
                "path": path_raw,
                "mod_id": mid,
                "preview": True,
                "bytes": len(old),
                "current_exists": Path(path_raw).is_file(),
            }
        raise ValueError("action 必须是 list / diff / undo")


# ── 提交执行器（由 commit_write 统一分派）──────────────


def _execute_delete(recycle: Recycle, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """提交：移入回收目录（可恢复）。"""
    raw = str(arguments.get("path") or "").strip()
    if not raw:
        raise ValueError("预览快照不完整：请重新预览（delete_file）")
    target = Path(raw)
    if not target.exists():
        raise FileNotFoundError(f"路径不存在（可能已被移动或删除）：{target}")
    if target.is_dir():
        raise ValueError("delete_file 仅用于文件；目录请用 file_ops(action=delete, recursive=true)")
    bytes_size = target.stat().st_size
    moved = recycle.move(target)
    return {"path": str(target), "written": True, "bytes": bytes_size, "moved_to": str(moved)}


def _execute_ops(recycle: Recycle, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """提交：执行 copy / move / rename / delete。"""
    plan = _validate_ops(arguments)
    action = str(plan["action"])
    source = plan["source"]
    dest = plan["dest"]
    if action == "delete":
        moved = recycle.move(source)
        return {"path": str(source), "written": True, "moved_to": str(moved)}
    if action == "copy":
        if source.is_dir():
            shutil.copytree(str(source), str(dest))
        else:
            shutil.copy2(str(source), str(dest))
        return {"path": str(dest), "written": True, "bytes": dest.stat().st_size if dest.is_file() else 0}
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(dest))
    return {"path": str(dest), "written": True, "moved_from": str(source)}


def _execute_undo(backups: FileBackups, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """提交：回滚到指定备份（回滚前备份当前版本，可逆）。"""
    mid = str(arguments.get("mod_id") or "").strip()
    path_raw = str(arguments.get("path") or "").strip()
    if not mid or not path_raw:
        raise ValueError("预览快照不完整：请重新预览（file_undo）")
    record = backups.meta(mid)
    if record is None:
        raise ValueError(f"mod_id 不存在或已过期：{mid}")
    if _norm_path(Path(path_raw).resolve()) != _norm_path(record.get("path")):
        raise ValueError(f"mod_id 与 path 不匹配（该备份属于：{record.get('path')}）")
    old = backups.read(mid)
    if old is None:
        raise ValueError(f"备份内容缺失：{mid}")
    target = Path(path_raw)
    current = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
    restored = old.decode("utf-8", errors="replace")
    changed = diff_text(current, restored, str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    # 回滚前的当前版本也留档，于是"回滚"本身可逆；改动内容一并记进这一版
    new_mod_id = backups.create(target, mode="undo", diff_text=changed) or ""
    target.write_bytes(old)
    return {
        "path": str(target),
        "written": True,
        "bytes": len(old),
        "mod_id": new_mod_id,
        "restored_from": mid,
        "_diff": changed,
    }


def build_plugins(backups: FileBackups) -> List[ToolPlugin]:
    """构造本组预览插件（delete_file / file_ops / file_undo）。"""
    return [DeleteFileTool(), FileOpsTool(), FileUndoTool(backups)]


def build_executors(
    backups: FileBackups, recycle: Recycle
) -> Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]]:
    """构造本组提交执行器表。"""
    return {
        "delete_file": lambda args: _execute_delete(recycle, args),
        "file_ops": lambda args: _execute_ops(recycle, args),
        "file_undo": lambda args: _execute_undo(backups, args),
    }
