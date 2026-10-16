# -*- coding: utf-8 -*-
"""技能管理工具：skill_manage——list / read 只读直通；copy 走预览 + 提交执行器。

copy 预览（不落盘，返回 confirm_id；冲突时明示 would_overwrite，是否覆盖由确认环节决定）；
提交执行器由 commit_write 统一分派（app.py 装配）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List

from agent.capabilities.registry import ToolPlugin
from plugins.skills.library import SkillManager


class SkillLookupError(RuntimeError):
    """技能查找失败：可用清单随 data 透传。"""

    def __init__(self, message: str, available: List[str]) -> None:
        super().__init__(message)
        self.data = {"available": available}


def _resolve_copy_source(library: SkillManager, arguments: Dict[str, Any]) -> Path:
    """解析 copy 源：name → 技能文件路径；否则 source 路径；失败抛异常。"""
    name_key = str(arguments.get("name") or "").strip()
    src = str(arguments.get("source") or "").strip()
    if name_key:
        meta = library.get_skill_meta(name_key)
        if meta is None:
            raise SkillLookupError(
                f"未找到名为 '{name_key}' 的 skill。当前可用: " + ", ".join(library.list_skill_names()),
                library.list_skill_names(),
            )
        return Path(meta.file_path).expanduser().resolve()
    if src:
        return Path(src).expanduser().resolve()
    raise ValueError("action=copy 需要指定 source（路径）或 name（skill 名称）")


class SkillManageTool(ToolPlugin):
    """技能工具：list / read 直通；copy 预览。"""

    name = "skill_manage"
    label = "技能管理"
    icon = ""
    description = "技能管理：`action=list` 列出可用技能；`action=read` 读取技能全文；`action=copy` 预览复制（不落盘，返回 confirm_id，凭 commit_write 提交）。"
    parameters = {
        "action": {"type": "string", "description": "list / read / copy"},
        "name": {"type": "string", "description": "技能名称（read 必填；copy 可作源）"},
        "source": {"type": "string", "description": "copy 源路径（文件或目录；与 name 二选一）"},
        "subdir": {"type": "string", "description": "copy 子目录名（源子目录与目标子目录一致）"},
    }

    def __init__(self, library: SkillManager) -> None:
        self._library = library

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        action = str(arguments.get("action") or "").strip().lower()
        if not action:
            raise ValueError("缺少 action 参数。可选: list / read / copy")
        if action == "list":
            skills = self._library.list_skills()
            return {"skills": skills, "count": len(skills), "needs_commit": False}
        if action == "read":
            key = str(arguments.get("name") or "").strip()
            if not key:
                raise SkillLookupError(
                    "请指定 name 参数。当前可用: " + ", ".join(self._library.list_skill_names()),
                    self._library.list_skill_names(),
                )
            content = self._library.get_skill(key)
            if content is None:
                raise SkillLookupError(
                    f"未找到名为 '{key}' 的 skill。当前可用: " + ", ".join(self._library.list_skill_names()),
                    self._library.list_skill_names(),
                )
            return {"name": key, "content": content, "needs_commit": False}
        if action == "copy":
            src_path = _resolve_copy_source(self._library, arguments)
            subdir = str(arguments.get("subdir") or "").strip()
            plan = self._library.plan_copy(src_path, subdir)
            return {
                "action": "copy",
                "preview": True,
                "source": plan["source"],
                "target_dir": plan["target_dir"],
                "files": plan["files"],
                "conflicts": plan["conflicts"],
                "would_copy": len(plan["files"]),
                "would_overwrite": bool(plan["conflicts"]),
                "hint": "提交请用 commit_write(confirm_id=...)",
            }
        raise ValueError(f"未知 action: {action}。可选: list / read / copy")


# ── 提交执行器（由 commit_write 统一分派）──────────────


def _execute_skill_copy(library: SkillManager, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """提交：执行技能复制（真实落盘）。"""
    action = str(arguments.get("action") or "").strip().lower()
    if action != "copy":
        raise ValueError("预览快照不完整：请重新预览（skill_manage）")
    src_path = _resolve_copy_source(library, arguments)
    subdir = str(arguments.get("subdir") or "").strip()
    result = library.execute_copy(src_path, subdir)
    return {
        "action": "copy",
        "path": result["path"],
        "written": True,
        "copied": result["copied"],
        "skipped": result["skipped"],
        "errors": result["errors"],
    }


def build(library: SkillManager) -> SkillManageTool:
    """构造 skill_manage 插件（需技能库引用）。"""
    return SkillManageTool(library)


def build_executors(library: SkillManager) -> Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]]:
    """构造本工具提交执行器表。"""
    return {"skill_manage": lambda args: _execute_skill_copy(library, args)}
