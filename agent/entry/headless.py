# -*- coding: utf-8 -*-
"""无 UI 单回合入口：装配 app，跑一轮并打印事件流。

    python -m agent.entry.headless ["一句话问题"]
"""
from __future__ import annotations

import sys
from typing import Any

from agent.app import build_app
from agent.shell import headless


def main(argv: list[str] | None = None, *, app_factory: Any = build_app) -> int:
    return headless.main(argv, app_factory=app_factory)


if __name__ == "__main__":
    sys.exit(main())
