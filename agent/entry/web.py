# -*- coding: utf-8 -*-
"""Web 进程入口：按配置装配 app，再交给 `agent.shell.web.serve`。

    python -m agent.entry.web --host 127.0.0.1 --port 8765

壳层（`agent.shell.*`）不导入装配根，所以"怎么建 app"只写在这里（A2）。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Optional

from agent.app import App, build_app
from agent.config import (
    default_data_root,
    get_context,
    get_model_reasoning,
    is_placeholder_api_key,
)
from agent.mechanisms.model_provider import MissingProvider, OpenAICompatibleProvider
from agent.mechanisms.session_store import SessionStore
from agent.shell.fspaths import FS_ROOT_ENV
from agent.shell.web import serve

_DEFAULT_PORT = 8765

_SETUP_HINT = (
    "尚未配置模型。服务已启动，浏览器会打开设置向导；"
    "也可以访问 /setup 填写网关和密钥，保存后立即生效。"
)


def build_shell_app(
    *,
    provider: Any = None,
    store: Any = None,
    data_root: Optional[Path] = None,
) -> App:
    """装配供 Web 壳使用的底座：默认真实 provider（按 config）+ 会话存储。

    没有 `config.ini` 凭据时以 `MissingProvider` 启动，页面进入设置向导；
    插件模型可以在启动后接管，不需要先有内核密钥。
    """
    given_provider = provider is not None
    if provider is None:
        cfg = get_model_reasoning()
        if (cfg["api_key"] and cfg["api_base_url"]
                and not is_placeholder_api_key(cfg["api_key"])):
            provider = OpenAICompatibleProvider(
                base_url=cfg["api_base_url"], api_key=cfg["api_key"], model=cfg["model"],
                replay_history_reasoning=bool(get_context().get("replay_history_reasoning")),
            )
        else:
            provider = MissingProvider()
    if store is None:
        store = SessionStore(Path(data_root) if data_root else default_data_root())
    config_ready = given_provider and not isinstance(provider, MissingProvider)
    return build_app(provider=provider, store=store, config_ready=config_ready)


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="agent.entry.web", description="AI Agent Web 壳")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=_DEFAULT_PORT)
    parser.add_argument("--data-root", default="")
    parser.add_argument("--open", action="store_true", dest="open_browser",
                        help="启动后自动打开浏览器")
    parser.add_argument(
        "--fs-root",
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "右栏文件查看器 / @ 补全的可见根；可重复指定多个。"
            f"默认 = 本机各盘根（与 agent 的读写范围一致）。亦可用 {FS_ROOT_ENV}（{os.pathsep} 分隔）"
        ),
    )
    parser.add_argument(
        "--media-root",
        default="",
        help="/api/media 可读根（默认与第一个 --fs-root 相同）",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(args.data_root) if args.data_root else default_data_root()
    try:
        app = build_shell_app(data_root=root)
    except RuntimeError as exc:
        print(str(exc))
        return 2
    setup = app.model_config_state == "none"
    if setup:
        print(_SETUP_HINT)
    open_url = None
    if args.open_browser:
        path = "/setup" if setup else "/"
        open_url = f"http://127.0.0.1:{args.port}{path}"
    return serve(
        app,
        host=args.host,
        port=args.port,
        data_root=root,
        fs_root=[Path(p) for p in args.fs_root] if args.fs_root else None,
        media_root=Path(args.media_root) if args.media_root else None,
        open_url=open_url,
    )


if __name__ == "__main__":
    sys.exit(main())
