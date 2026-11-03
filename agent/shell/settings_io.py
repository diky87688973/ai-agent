# -*- coding: utf-8 -*-
"""设置页的文件与 ini 文本原语：原子读写、节内改键、增删节。

同一份 ini 的两处写法必须共用同一组匹配规则，否则注释行与节边界的处理会分叉。
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, Iterable, Tuple

from agent.config import PROJECT_ROOT
from agent.core.error_report import report_error
from agent.shell.ini_sections import append_section, replace_sections
from agent.shell.ini_sections import update_ini_keys as _update_ini_keys

#: 配置文件的写者串行化：两个保存请求同时进来时不能交错写。
LOCK = threading.Lock()

#: 插件目录缺省值（清单里没写 `path` 时用它）。
PLUGINS_DIR = PROJECT_ROOT / "plugins"



def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=str(path.parent), prefix=".settings-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        last_error = None
        for attempt in range(6):
            try:
                os.replace(name, path)
                return
            except PermissionError as exc:
                last_error = exc
                if attempt == 5:
                    raise
                time.sleep(0.05 * (attempt + 1))
        raise last_error
    except Exception:
        try:
            os.unlink(name)
        except OSError as exc:
            report_error("agent.shell.settings_io.write_text", exc)
        raise


def update_ini_keys(text: str, section: str, updates: Dict[str, str]) -> str:
    """在指定节里改键；实现由 ini_sections 统一维护。"""
    return _update_ini_keys(text, section, updates)


def remove_ini_section(text: str, section: str) -> str:
    """删掉一整节；实现由 ini_sections.replace_sections 统一维护。"""
    return replace_sections(text, (), remove=[section])


def append_ini_section(text: str, section: str, items: Iterable[Tuple[str, str]]) -> str:
    """文件末尾加一节；实现由 ini_sections.append_section 统一维护。"""
    return append_section(text, section, [f"{key} = {value}" for key, value in items])
