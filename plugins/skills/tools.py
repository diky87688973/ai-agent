# -*- coding: utf-8 -*-
"""Skills 工具：list / read 只读直通。"""
from __future__ import annotations

from typing import Any, Dict, List

from agent.capabilities.registry import ToolPlugin

from .library import SkillManager


class SkillLookupError(RuntimeError):
    """Skills 查找失败：可用清单随 data 透传。"""

    def __init__(self, message: str, available: List[str]) -> None:
        super().__init__(message)
        self.data = {"available": available}


class SkillsTool(ToolPlugin):
    """Skills 工具：列清单与读取正文，不写盘。"""

    name = "skills"
    label = "Skills 管理"
    icon = "🧩"
    description = ("Skills：`action=list` 列出可用 Skills；`action=read` 读取 Skills 全文。"
                   "不负责复制或迁移文件。")

    parameters = {
        "action": {"type": "string", "enum": ["list", "read"],
                   "description": "list / read"},
        "name": {"type": "string", "description": "Skills 名称（read 必填）"},
    }

    def __init__(self, library: SkillManager) -> None:
        self._library = library

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        action = str(arguments.get("action") or "").strip().lower()
        if not action:
            raise ValueError("缺少 action 参数。可选: list / read")
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
        raise ValueError(f"未知 action: {action}。可选: list / read")


def build(library: SkillManager) -> SkillsTool:
    """构造 skills 工具（只需要 Skills 库引用）。"""
    return SkillsTool(library)
