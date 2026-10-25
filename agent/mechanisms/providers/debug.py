# -*- coding: utf-8 -*-
"""Provider 调试开关。"""
from __future__ import annotations

import os

#: 发送前打印请求摘要（`AI_AGENT_LOG_REQUESTS=0` 可关）。
LOG_REQUESTS = str(os.environ.get("AI_AGENT_LOG_REQUESTS", "1")).strip().lower() \
    not in ("0", "false", "no", "off")
