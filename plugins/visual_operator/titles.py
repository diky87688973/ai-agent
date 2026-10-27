# -*- coding: utf-8 -*-
"""窗口标题匹配：忽略不可见格式字符与空白差异。"""
from __future__ import annotations

import re

_INVISIBLE = re.compile("[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
_SPACES = re.compile(r"\s+")


def normalize_title(text: str) -> str:
    """去掉零宽/方向控制字符，折叠空白并 casefold。"""
    return _SPACES.sub(" ", _INVISIBLE.sub("", str(text or ""))).strip().casefold()


def title_matches(title: str, needle: str) -> bool:
    """标题片段匹配；空片段不匹配任何窗口。"""
    wanted = normalize_title(needle)
    return bool(wanted) and wanted in normalize_title(title)
