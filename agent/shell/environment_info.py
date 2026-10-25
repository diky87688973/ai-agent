# -*- coding: utf-8 -*-
"""系统提示词的环境章节：当前只列操作系统与会话 ID。"""
from __future__ import annotations

import platform
from typing import List

ENVIRONMENT_HEAD = "## 环境信息"


def operating_system() -> str:
    """当前操作系统的人类可读名称。"""
    system = str(platform.system() or "").strip()
    release = str(platform.release() or "").strip()
    return " ".join(part for part in (system.lower(), release) if part) or "未知"


def environment_lines(conversation_id: str) -> List[str]:
    """环境章节正文；后续新增环境项只扩展这里。"""
    cid = str(conversation_id or "").strip() or "未指定"
    return [
        f"操作系统: {operating_system()}",
        f"本会话ID: {cid}",
    ]


def environment_section(conversation_id: str) -> str:
    """完整环境章节（含标题）。"""
    return ENVIRONMENT_HEAD + "\n" + "\n".join(environment_lines(conversation_id))
