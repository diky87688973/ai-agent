# -*- coding: utf-8 -*-
"""门控单测辅助：path_keys_for 从真实工具类属性读取（不手写键序字面量）。"""
from __future__ import annotations

from typing import Sequence, Tuple

from agent.capabilities.builtin.archive_tool import ArchiveTool
from agent.capabilities.builtin.edit_tools import (
    ApplyPatchTool,
    ReadWriteTool,
    ReplaceInFileTool,
)
from agent.capabilities.builtin.fs_tools import DeleteFileTool, FileOpsTool, FileUndoTool
from agent.capabilities.builtin.write_file import WriteFileTool
from agent.mechanisms.quality import QualityGate

_BUILTIN_PATH_KEYS = {
    WriteFileTool.name: WriteFileTool.write_path_keys,
    ReplaceInFileTool.name: ReplaceInFileTool.write_path_keys,
    ApplyPatchTool.name: ApplyPatchTool.write_path_keys,
    ReadWriteTool.name: ReadWriteTool.write_path_keys,
    DeleteFileTool.name: DeleteFileTool.write_path_keys,
    FileOpsTool.name: FileOpsTool.write_path_keys,
    FileUndoTool.name: FileUndoTool.write_path_keys,
    ArchiveTool.name: ArchiveTool.write_path_keys,
}


def builtin_path_keys(name: str) -> Tuple[str, ...]:
    """内置写类工具的 write_path_keys（读类属性，非手写旁路表）。"""
    keys: Sequence[str] = _BUILTIN_PATH_KEYS.get(str(name or ""), ())
    return tuple(keys)


def make_gate() -> QualityGate:
    """带内置 path_keys_for 的 QualityGate（直连门控单测用）。"""
    return QualityGate(path_keys_for=builtin_path_keys)
