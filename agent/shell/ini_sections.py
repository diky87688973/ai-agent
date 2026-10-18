# -*- coding: utf-8 -*-
"""INI 文本的节定位与节级改写。

设置页要按节读写配置：宿主配置按节回显，插件配置只动插件自己的节，
`[base]` 这类元数据节必须逐字节保留。这里只做行级定位与节内容替换，
不解析键值语义 —— 键的校验属于调用方。
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Tuple


def newline(text: str) -> str:
    """文件换行风格：出现过 CRLF 就用 CRLF，否则用 LF。"""
    return "\r\n" if "\r\n" in text else "\n"


def section_at(line: str) -> Optional[str]:
    """该行是不是节头；是则返回节名（去空白），否则 None。

    注释行与不完整的方括号都不算节头 —— `; [plugin:tts]` 是注释示例，
    不能当成真实节参与查找。
    """
    raw = line.strip()
    if not raw or raw[0] in ";#":
        return None
    if len(raw) < 3 or raw[0] != "[" or raw[-1] != "]":
        return None
    name = raw[1:-1].strip()
    if not name or "[" in name or "]" in name:
        return None
    return name


def section_span(lines: List[str], section: str) -> Optional[Tuple[int, int]]:
    """节头到下一节头（不含）的行号区间；找不到返回 None。"""
    want = str(section or "").strip().lower()
    if not want:
        return None
    start = None
    for index, line in enumerate(lines):
        name = section_at(line)
        if name is None:
            continue
        if start is not None:
            return start, index
        if name.lower() == want:
            start = index
    if start is None:
        return None
    return start, len(lines)


def section_names(text: str) -> List[str]:
    """按出现顺序列出所有真实节名（不重复、大小写按原文）。"""
    out: List[str] = []
    seen: set = set()
    for line in text.splitlines():
        name = section_at(line)
        if name is None or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append(name)
    return out


def section_body(lines: List[str], section: str) -> Optional[List[str]]:
    """节头之后、下一节头之前的原始行（含注释与空行）。"""
    span = section_span(lines, section)
    if span is None:
        return None
    start, end = span
    return list(lines[start + 1:end])


def replace_sections(
    text: str,
    bodies: Iterable[Tuple[str, List[str]]],
    *,
    remove: Iterable[str] = (),
) -> str:
    """替换若干节的正文、删除若干节；其余行（含注释与 `[base]`）原样保留。

    `bodies` 的节必须已存在；正文按原文换行风格补齐。删除与替换都按当前
    行号重新定位，避免前一次改动让后面的区间错位。
    """
    lines = text.splitlines(keepends=True)
    nl = newline(text) if text else "\n"
    for section, body in bodies:
        span = section_span(lines, section)
        if span is None:
            continue
        start, end = span
        header = lines[start]
        clean = [_with_newline(line, nl) for line in body]
        lines[start:end] = [header, *clean]
    for section in remove:
        span = section_span(lines, section)
        if span is None:
            continue
        start, end = span
        del lines[start:end]
    return "".join(lines)


def append_section(text: str, section: str, body: Iterable[str]) -> str:
    """在文件末尾追加一节（同名节已存在时原样返回）。"""
    if section_span(text.splitlines(keepends=True), section) is not None:
        return text
    nl = newline(text) if text else "\n"
    lines = [_with_newline(line, nl) for line in body]
    block = f"[{section}]{nl}" + "".join(line for line in lines if line.strip())
    if text and not text.endswith(("\n", "\r")):
        text += nl
    if text and not text.endswith(nl + nl):
        text += nl
    return text + block


def _with_newline(line: str, nl: str) -> str:
    """去掉原有行尾并按目标换行风格补一个；空行保留为空行。"""
    raw = str(line).rstrip("\r\n")
    return raw + nl
