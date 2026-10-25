# -*- coding: utf-8 -*-
"""无 UI 单回合入口：装配 app，跑一轮并打印事件流。

    python -m agent.entry.headless ["一句话问题"]
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from agent.app import build_app
from agent.config import APP_HOME, default_data_root
from agent.mechanisms.session_store import SessionStore
from agent.shell.cli import headless

HEADLESS_PLUGINS_PATH = APP_HOME / "plugins.headless.ini"


def _default_app_factory() -> Any:
    data_root = Path(default_data_root())
    app = build_app(
        store=SessionStore(data_root),
        data_root=data_root,
        plugins_path=HEADLESS_PLUGINS_PATH,
    )
    if getattr(app, "model_config_state", "catalog") == "none":
        app.dispose()
        print(
            "未配置任何可用模型。请在 plugins/multi_model/plugin-config.ini "
            "中配置至少一个 [model:<id>] 节。",
            file=sys.stderr,
        )
        return None
    return app


def main(argv: list[str] | None = None, *, app_factory: Any = None) -> int:
    return headless.main(argv, app_factory=app_factory or _default_app_factory)


if __name__ == "__main__":
    sys.exit(main())
