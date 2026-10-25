# -*- coding: utf-8 -*-
"""文件系统工具组：delete_file / file_ops / file_undo——预览 + 统一提交执行器。

- delete_file：安全删除（移入回收目录，可恢复；目录请用 file_ops）；
  路径已不存在 → `status=already_absent`（`needs_commit=False`，ok=true；与「本次真删」区分）；
- file_ops：copy / move / rename / delete；
  `on_exists=error|overwrite|skip`；copy/move/rename 源缺失 → ok=false / source_missing
  （不得因目标已在而改判 already_applied）；目标冲突且 on_exists=error →
  ok=false / dest_exists_conflict；删除路径已不在 → already_absent；
- file_undo：list / diff 只读（结果标 needs_commit=False，门控不登记快照）；undo 预览 + 提交
  回滚（回滚前自动备份当前版本，可逆）。
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agent.capabilities.registry import ToolPlugin
from agent.mechanisms.file_safety import FileBackups, Recycle
from agent.mechanisms.quality import diff_text


def norm_path(value: Any) -> str:
    """路径规范化（统一斜杠、去首尾空白）。"""
    return str(value or "").replace("\\", "/").strip()


def _files_same(a: Path, b: Path) -> bool:
    """两路径是否同为文件且字节相同（目录不做深比较）。"""
    try:
        if not (a.is_file() and b.is_file()):
            return False
        return a.read_bytes() == b.read_bytes()
    except OSError:
        return False


def _remove_path(target: Path) -> None:
    """删除已存在的目标（覆盖前清理）。"""
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(str(target))
    elif target.exists() or target.is_symlink():
        target.unlink()


# ── delete_file ────────────────────────────────────────


class DeleteFileTool(ToolPlugin):
    """预览：安全删除（移入回收目录），不落盘。"""

    name = "delete_file"
    label = "删除文件"
    icon = "🗑️"
    description = (
        "预览安全删除（不落盘）：文件将移入回收目录（可恢复）；"
        "路径已不存在时返回 status=already_absent（needs_commit=false），不必再 commit；"
        "目录请用 `file_ops(action=delete, recursive=true)`；"
        "否则返回 confirm_id，凭 commit_write 提交。"
    )
    needs_preview = True
    write_path_keys = ("path",)
    parameters = {
        "path": {"type": "string", "description": "待删除文件路径"},
    }

    def __init__(self, recycle: Recycle | None = None) -> None:
        self._recycle = recycle

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw = str(arguments.get("path") or "").strip()
        if not raw:
            raise ValueError("缺少 path")
        target = Path(raw)
        if not target.exists():
            return {
                "path": str(target),
                "status": "already_absent",
                "applied": False,
                "needs_commit": False,
                "message": "路径已不存在，无需删除",
            }
        if target.is_dir():
            raise ValueError("delete_file 仅用于文件；目录请用 file_ops(action=delete, recursive=true)")
        info: Dict[str, Any] = {
            "path": str(target),
            "preview": True,
            "status": "pending",
            "bytes": target.stat().st_size,
        }
        if self._recycle is not None:
            info["recycle_dir"] = str(self._recycle.root)
        return info


# ── file_ops ───────────────────────────────────────────


_OPS_ACTIONS = ("copy", "move", "rename", "delete")
_ON_EXISTS = ("error", "overwrite", "skip")


def _parse_on_exists(arguments: Dict[str, Any]) -> str:
    raw = str(arguments.get("on_exists") or "error").strip().lower()
    if raw not in _ON_EXISTS:
        raise ValueError(f"on_exists 必须是 {' / '.join(_ON_EXISTS)} 之一")
    return raw


def _terminal(
    *,
    action: str,
    status: str,
    source: Path,
    dest: Optional[Path] = None,
    message: str,
    on_exists: str = "",
) -> Dict[str, Any]:
    """无需 commit 的终态（幂等 / 跳过 / 路径已不在）。"""
    out: Dict[str, Any] = {
        "action": action,
        "source": str(source),
        "status": status,
        "applied": False,
        "needs_commit": False,
        "message": message,
    }
    if dest is not None:
        out["dest"] = str(dest)
    if on_exists:
        out["on_exists"] = on_exists
    return out


def _ops_fail(
    *,
    status: str,
    action: str,
    source: Path,
    message: str,
    dest: Optional[Path] = None,
    on_exists: str = "",
    dest_exists: Optional[bool] = None,
) -> None:
    """业务失败：抛 ValueError，并挂结构化 data（与 replace 的 old_text_not_found 同形）。"""
    data: Dict[str, Any] = {
        "status": status,
        "needs_commit": False,
        "action": action,
        "source": str(source),
        "applied": False,
        "message": message,
    }
    if dest is not None:
        data["dest"] = str(dest)
        data["dest_exists"] = (
            bool(dest_exists) if dest_exists is not None else dest.exists()
        )
    if on_exists:
        data["on_exists"] = on_exists
    exc = ValueError(message)
    exc.data = data
    raise exc


def _plan_delete(action: str, source: Path, recursive: bool,
                 on_exists: str) -> Dict[str, Any]:
    if not source.exists():
        return _terminal(
            action=action, status="already_absent", source=source,
            message="源路径已不存在，无需删除")
    if source.is_dir() and not recursive:
        raise ValueError("删除目录须传 recursive=true")
    return {
        "action": action, "source": source, "dest": None,
        "recursive": recursive, "on_exists": on_exists, "overwrite": False,
    }


def _plan_destination(action: str, source: Path, dest: Path, recursive: bool,
                      on_exists: str) -> Dict[str, Any]:
    if not source.exists():
        dest_exists = dest.exists()
        verb = {"copy": "复制", "move": "移动", "rename": "重命名"}.get(action, action)
        msg = f"源路径不存在：{source}"
        msg += (f"；目标已存在：{dest}（本次未实际{verb}）" if dest_exists
                else f"（本次未实际{verb}）")
        _ops_fail(status="source_missing", action=action, source=source,
                  dest=dest, dest_exists=dest_exists, on_exists=on_exists,
                  message=msg)
    if dest.resolve() == source.resolve():
        raise ValueError("source 与 dest 不能相同")
    overwrite = False
    if dest.exists():
        if action == "copy" and _files_same(source, dest):
            return _terminal(
                action=action, status="already_applied", source=source,
                dest=dest, message="目标已存在且与源内容相同，无需复制",
                on_exists=on_exists)
        if on_exists == "skip":
            return _terminal(
                action=action, status="skipped", source=source, dest=dest,
                message=f"目标已存在，已按 on_exists=skip 跳过：{dest}",
                on_exists=on_exists)
        if on_exists == "error":
            _ops_fail(status="dest_exists_conflict", action=action,
                      source=source, dest=dest, dest_exists=True,
                      on_exists=on_exists, message=f"目标已存在，拒绝覆盖：{dest}")
        overwrite = True
    return {
        "action": action, "source": source, "dest": dest,
        "recursive": recursive, "on_exists": on_exists, "overwrite": overwrite,
    }


def _plan_ops(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """解析 file_ops：返回待提交 plan，或终态（含 needs_commit=False）。"""
    action = str(arguments.get("action") or "").strip().lower()
    if action not in _OPS_ACTIONS:
        raise ValueError(f"action 必须是 {' / '.join(_OPS_ACTIONS)} 之一")
    source_raw = str(arguments.get("source") or "").strip()
    if not source_raw:
        raise ValueError("缺少 source")
    source = Path(source_raw)
    recursive = bool(arguments.get("recursive", False))
    on_exists = _parse_on_exists(arguments)
    if action == "delete":
        return _plan_delete(action, source, recursive, on_exists)
    dest_raw = str(arguments.get("dest") or "").strip()
    if not dest_raw:
        raise ValueError(f"{action} 缺少 dest")
    return _plan_destination(action, source, Path(dest_raw), recursive, on_exists)

class FileOpsTool(ToolPlugin):
    """预览：copy / move / rename / delete（不落盘）。"""

    name = "file_ops"
    label = "执行文件复制/移动/删除"
    icon = "📋"
    description = (
        "预览文件操作（不落盘）：copy / move / rename / delete"
        "（delete 移入回收目录，可恢复；delete 目录须 `recursive=true`）。"
        "on_exists=error|overwrite|skip（默认 error）；"
        "copy/move/rename 源不存在 → ok=false / source_missing（可含 dest_exists）；"
        "目标已在且 on_exists=error → ok=false / dest_exists_conflict（结构化，非纯字符串）；"
        "同内容 copy → already_applied；on_exists=skip → skipped；"
        "delete 路径已不在 → already_absent；否则返回 confirm_id，凭 commit_write 提交。"
    )
    needs_preview = True
    write_path_keys = ("dest", "source")
    parameters = {
        "action": {"type": "string", "description": "copy / move / rename / delete"},
        "source": {"type": "string", "description": "源路径（必填）"},
        "dest": {"type": "string", "description": "目标路径（delete 时勿传）"},
        "recursive": {"type": "boolean", "description": "删除目录须传 true"},
        "on_exists": {
            "type": "string",
            "description": "目标已存在时：error（默认拒绝）/ overwrite（覆盖）/ skip（跳过，needs_commit=false）",
        },
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            plan = _plan_ops(arguments)
        except ValueError as exc:
            data = getattr(exc, "data", None)
            if isinstance(data, dict):
                exc.data = dict(data)
            raise
        if plan.get("needs_commit") is False:
            return plan
        info: Dict[str, Any] = {
            "action": plan["action"],
            "source": str(plan["source"]),
            "preview": True,
            "status": "pending",
            "on_exists": plan.get("on_exists") or "error",
        }
        if plan.get("dest") is not None:
            info["dest"] = str(plan["dest"])
        if plan.get("overwrite"):
            info["overwrite"] = True
        return info


# ── file_undo ──────────────────────────────────────────


class FileUndoTool(ToolPlugin):
    """版本回滚工具：list / diff 只读；undo 预览（提交后执行回滚）。"""

    name = "file_undo"
    label = "撤销文件改动"
    icon = "↩️"
    needs_preview = True
    needs_reread = True
    write_path_keys = ("path",)
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
            if norm_path(Path(path_raw).resolve()) != norm_path(record.get("path")):
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
    """提交：移入回收目录（可恢复）；已不存在则幂等成功。"""
    raw = str(arguments.get("path") or "").strip()
    if not raw:
        raise ValueError("预览快照不完整：请重新预览（delete_file）")
    target = Path(raw)
    if not target.exists():
        return {
            "path": str(target),
            "written": False,
            "status": "already_absent",
            "message": "路径已不存在，无需删除",
        }
    if target.is_dir():
        raise ValueError("delete_file 仅用于文件；目录请用 file_ops(action=delete, recursive=true)")
    bytes_size = target.stat().st_size
    moved = recycle.move(target)
    return {"path": str(target), "written": True, "bytes": bytes_size, "moved_to": str(moved)}


def _execute_ops(recycle: Recycle, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """提交：执行 copy / move / rename / delete。"""
    plan = _plan_ops(arguments)
    if plan.get("needs_commit") is False:
        # 预览后磁盘态变了：按终态返回，不报错
        return {
            "path": str(plan.get("dest") or plan.get("source") or ""),
            "written": False,
            "status": plan.get("status"),
            "message": plan.get("message"),
            "action": plan.get("action"),
            "source": plan.get("source"),
            "dest": plan.get("dest"),
        }
    action = str(plan["action"])
    source = plan["source"]
    dest = plan["dest"]
    if action == "delete":
        moved = recycle.move(source)
        return {"path": str(source), "written": True, "moved_to": str(moved)}
    if plan.get("overwrite") and dest is not None and dest.exists():
        _remove_path(dest)
    if action == "copy":
        if source.is_dir():
            shutil.copytree(str(source), str(dest))
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
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
    if norm_path(Path(path_raw).resolve()) != norm_path(record.get("path")):
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


def build_plugins(backups: FileBackups, recycle: Recycle | None = None) -> List[ToolPlugin]:
    """构造本组预览插件（delete_file / file_ops / file_undo）。"""
    return [DeleteFileTool(recycle), FileOpsTool(), FileUndoTool(backups)]


def build_executors(
    backups: FileBackups, recycle: Recycle
) -> Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]]:
    """构造本组提交执行器表。"""
    return {
        "delete_file": lambda args: _execute_delete(recycle, args),
        "file_ops": lambda args: _execute_ops(recycle, args),
        "file_undo": lambda args: _execute_undo(backups, args),
    }
