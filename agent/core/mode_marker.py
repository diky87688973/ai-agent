# -*- coding: utf-8 -*-
"""执行模式段的固定起始标记。

正文形如 `## 当前模式：Auto`；用本常量做 `startswith` / 定位，避免各处手写漂移。
"""
from __future__ import annotations

#: 模式段正文的公共前缀（含「当前模式」四字；冒号及模式名接在后面）。
MODE_MARKER = "## 当前模式"
