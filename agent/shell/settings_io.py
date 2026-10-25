# -*- coding: utf-8 -*-
"""设置页的文件与 ini 文本原语：原子读写、节内改键、增删节。

同一份 ini 的两处写法必须共用同一组匹配规则，否则注释行与节边界的处理会分叉。
"""
from __future__ import annotations

import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Dict, Iterable, Tuple

from agent.config import PROJECT_ROOT
from agent.core.error_report import report_error
from agent.shell.ini_sections import newline, section_span

#: 配置文件的写者串行化：两个保存请求同时进来时不能交错写。
LOCK = threading.Lock()

#: 插件目录缺省值（清单里没写 `path` 时用它）。
PLUGINS_DIR = PROJECT_ROOT / "plugins"

_KEY_RE = re.compile(r"^(\s*)([A-Za-z0-9_-]+)(\s*=\s*)(.*)$")


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
        os.replace(name, path)
    except Exception:
        try:
            os.unlink(name)
        except OSError as exc:
            report_error("agent.shell.settings_io.write_text", exc)
        raise


def update_ini_keys(text: str, section: str, updates: Dict[str, str]) -> str:
    """在指定节里改键。已有的键换掉那一行，没有的键补在节尾。其它行不动。"""
    if not updates:
        return text
    pending = {str(key): str(value) for key, value in updates.items()}
    for value in pending.values():
        if "\n" in value or "\r" in value:
            raise ValueError("配置值不能换行")
    lines = text.splitlines(keepends=True)
    nl = newline(text) if text else "\n"
    span = section_span(lines, section)
    if span is None:
        block = [f"[{section}]{nl}"]
        for key, value in pending.items():
            block.append(f"{key} = {value}{nl}")
        if text and not text.endswith(("\n", "\r")):
            text += nl
        if text and not text.endswith(nl + nl):
            text += nl
        return text + "".join(block)
    start, end = span
    for index in range(start + 1, end):
        body = lines[index].rstrip("\r\n")
        matched = _KEY_RE.match(body)
        if matched is None:
            continue
        key = matched.group(2)
        found = None
        for want in pending:
            if want.lower() == key.lower():
                found = want
                break
        if found is None:
            continue
        ending = lines[index][len(body):] or nl
        lines[index] = f"{matched.group(1)}{key}{matched.group(3)}{pending.pop(found)}{ending}"
    if pending:
        insert_at = end
        while insert_at > start + 1 and lines[insert_at - 1].strip() == "":
            insert_at -= 1
        extra = [f"{key} = {value}{nl}" for key, value in pending.items()]
        lines[insert_at:insert_at] = extra
    return "".join(lines)


def remove_ini_section(text: str, section: str) -> str:
    """删掉一整个节（节头和节内的键）。注释行不是节头，不会被删。"""
    lines = text.splitlines(keepends=True)
    span = section_span(lines, section)
    if span is None:
        return text
    start, end = span
    del lines[start:end]
    return "".join(lines)


def append_ini_section(text: str, section: str, items: Iterable[Tuple[str, str]]) -> str:
    """文件末尾加一节。节已经存在时不重复加。"""
    if section_span(text.splitlines(keepends=True), section) is not None:
        return text
    nl = newline(text) if text else "\n"
    pairs = list(items)
    for _key, value in pairs:
        if "\n" in value or "\r" in value:
            raise ValueError("配置值不能换行")
    block = f"[{section}]{nl}" + "".join(f"{key} = {value}{nl}" for key, value in pairs)
    if text and not text.endswith(("\n", "\r")):
        text += nl
    if text and not text.endswith(nl + nl):
        text += nl
    return text + block
