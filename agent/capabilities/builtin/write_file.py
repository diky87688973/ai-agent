# -*- coding: utf-8 -*-
"""写文件工具组（预览与提交为两个独立入口）。

- WriteFileTool（预览入口，name=write_file）：登记待提交写请求（不落盘）；
  由门控在结果中注入 confirm_id，供确认与后续提交引用；
- build_executors（提交执行器）：由统一提交入口 commit_write 凭 confirm_id 分派——
  path/content 由门控从预览快照恢复（模型不重传：省 token、防重写漂移）；
  覆盖既有文件前留版本化备份（file_undo 回滚依据），并随 "_diff" 返回旧→新 diff。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict

from agent.capabilities.registry import ToolPlugin
from agent.mechanisms.file_safety import FileBackups
from agent.mechanisms.quality_gate import change_payload, diff_text


class WriteFileTool(ToolPlugin):
    """预览：校验写参数并返回预览信息（不落盘）。"""

    name = "write_file"
    description = (
        "预览写入文本文件（不落盘），返回 confirm_id。"
        "落盘前必须先 review：用 review_conclusion 提交结论与证据解锁，"
        "再用该 confirm_id 调 commit_write。"
    )
    parameters = {
        "path": {"type": "string", "description": "目标文件路径"},
        "content": {"type": "string", "description": "写入内容（UTF-8；仅预览入口）"},
    }

    def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw = str(arguments.get("path") or "").strip()
        if not raw:
            raise ValueError("缺少 path")
        if "content" not in arguments:
            raise ValueError("缺少 content")
        content = str(arguments.get("content") or "")
        payload = content.encode("utf-8")
        target = Path(raw)
        old_text = ""
        if target.is_file():
            try:
                old_text = target.read_text(encoding="utf-8", errors="replace")
            except OSError:
                old_text = ""
        return {
            "path": str(target),
            "preview": True,
            "bytes": len(payload),
            "exists": target.is_file(),
            # 变更预览（Web 壳文件编辑 / diff 卡片用；不落盘，仅供展示）
            "_change": change_payload(old_text, content, str(target)),
        }


def build() -> WriteFileTool:
    """构造 write_file 插件（预览入口）。"""
    return WriteFileTool()


def build_executors(backups: FileBackups) -> Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]]:
    """构造提交执行器表：{"write_file": 执行函数}；覆盖前留版本化备份并返回 "_diff"。"""

    def execute(arguments: Dict[str, Any]) -> Dict[str, Any]:
        raw = str(arguments.get("path") or "").strip()
        if not raw or "content" not in arguments:
            raise ValueError("预览快照不完整：请重新预览（write_file）")
        content = str(arguments.get("content") or "")
        target = Path(raw)
        old_text = ""
        if target.is_file():
            old_text = target.read_text(encoding="utf-8", errors="replace")
        payload = content.encode("utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        changed = diff_text(old_text, content, str(target))
        # 旧内容与新内容都在手边，把这一版改了什么一并留档
        mod_id = backups.create(target, mode="write", diff_text=changed) or ""
        target.write_bytes(payload)
        return {
            "path": str(target),
            "written": True,
            "bytes": len(payload),
            "mod_id": mod_id,
            "_diff": changed,
        }

    return {"write_file": execute}

