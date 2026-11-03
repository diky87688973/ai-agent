# -*- coding: utf-8 -*-
"""系统提示词的环境章节：操作系统、Python、Node（可用时）与会话 ID。"""
from __future__ import annotations

import platform
import shutil
import subprocess
from functools import lru_cache
from typing import List

ENVIRONMENT_HEAD = "## 环境信息"


def operating_system() -> str:
    """当前操作系统的人类可读名称。"""
    system = str(platform.system() or "").strip()
    release = str(platform.release() or "").strip()
    return " ".join(part for part in (system.lower(), release) if part) or "未知"


@lru_cache(maxsize=1)
def node_version() -> str:
    """本机 Node 版本；未安装时返回空字符串。"""
    executable = shutil.which("node")
    if not executable:
        return ""
    try:
        result = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=2, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    version = str(result.stdout or "").strip()
    return version if result.returncode == 0 and version else ""


def environment_lines(conversation_id: str) -> List[str]:
    """环境章节正文；所有环境项都在这里拼接。"""
    cid = str(conversation_id or "").strip() or "未指定"
    lines = [
        f"操作系统: {operating_system()}",
        f"Python: {platform.python_version()}",
    ]
    node = node_version()
    if node:
        lines.append(f"Node: {node}")
    lines.append(f"本会话ID: {cid}")
    return lines


def environment_section(conversation_id: str) -> str:
    """完整环境章节（含标题）。"""
    return ENVIRONMENT_HEAD + "\n" + "\n".join(environment_lines(conversation_id))
