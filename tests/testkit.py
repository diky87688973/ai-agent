# -*- coding: utf-8 -*-
"""测试共用的小工具。"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any
from unittest import mock


def no_plugins(case: Any) -> None:
    """让本测试用例装配的 App 不装载任何插件。

    装载清单默认取工程根的 `plugins.ini`，那是部署配置：它一变，
    数总线订阅、数注入源、数面板的测试就会跟着变。测试要断言的是内核行为，
    所以先把插件这一层清空。

    在 `setUp` 里调用；补丁与临时目录都挂到 `case` 的 cleanup 上。
    """
    tmp = tempfile.mkdtemp(prefix="ai_agent_noplugins_")
    case.addCleanup(shutil.rmtree, tmp, True)
    empty = Path(tmp) / "plugins.ini"
    empty.write_text("; 空清单：本测试不需要任何插件\n", encoding="utf-8")
    patcher = mock.patch("agent.config.DEFAULT_PLUGINS_PATH", empty)
    patcher.start()
    case.addCleanup(patcher.stop)
