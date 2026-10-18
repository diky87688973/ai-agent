# -*- coding: utf-8 -*-
"""交互式对话进程入口。

    python -m agent.entry.cli                  # 交互模式（新建会话）
    python -m agent.entry.cli --session <ID>    # 恢复并继续指定会话
    python -m agent.entry.cli "一句话问题"       # 单回合模式

装配（provider / store / app）只在这里发生；`agent.shell.chat` 只认现成 app（A2）。
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from agent.app import build_app
from agent.config import default_data_root, get_context, get_model_reasoning
from agent.mechanisms.model_provider import OpenAICompatibleProvider
from agent.mechanisms.session_store import SessionStore
from agent.shell import chat


def build_app_from_config() -> Optional[Any]:
    """按 config.ini 装配 app；缺配置时打印原因并返回 None（不抛）。"""
    cfg = get_model_reasoning()
    if not cfg["api_key"] or not cfg["api_base_url"]:
        print("缺少配置：agent/config.ini 的 [model_reasoning]（api_base_url / api_key / model）")
        return None
    provider = OpenAICompatibleProvider(
        base_url=cfg["api_base_url"], api_key=cfg["api_key"], model=cfg["model"],
        # 与 Web 壳同一口径：历史轮次的思维链默认不回传。
        replay_history_reasoning=bool(get_context().get("replay_history_reasoning")),
    )
    store = SessionStore(Path(default_data_root()))
    return build_app(provider=provider, store=store)


def main(argv: Optional[list] = None) -> int:
    return chat.main(argv, app_factory=build_app_from_config)


if __name__ == "__main__":
    sys.exit(main())
