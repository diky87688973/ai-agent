# -*- coding: utf-8 -*-
"""交互式对话进程入口。

    python -m agent.entry.cli                  # 交互模式（新建会话）
    python -m agent.entry.cli --session <ID>    # 恢复并继续指定会话
    python -m agent.entry.cli "一句话问题"       # 单回合模式

装配（provider / store / app）只在这里发生；`agent.shell.cli.interactive` 只认现成 app（A2）。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from agent.app import build_app
from agent.config import APP_HOME, default_data_root
from agent.mechanisms.session_store import SessionStore
from agent.shell.cli import interactive as chat

CLI_PLUGINS_PATH = APP_HOME / "plugins.cli.ini"


def build_app_from_config() -> Optional[Any]:
    """装配 app；模型由 multi_model 插件提供，未配置时返回 None（不抛）。"""
    data_root = Path(default_data_root())
    store = SessionStore(data_root)
    app = build_app(
        provider=None,
        store=store,
        data_root=data_root,
        plugins_path=CLI_PLUGINS_PATH,
    )
    if app.model_config_state == "none":
        print("未配置任何可用模型。请在 plugins/multi_model/plugin-config.ini 中配置至少一个 [model:<id>] 节。")
        app.dispose()
        return None
    return app


def main(argv: Optional[list] = None) -> int:
    return chat.main(argv, app_factory=build_app_from_config)


if __name__ == "__main__":
    sys.exit(main())
