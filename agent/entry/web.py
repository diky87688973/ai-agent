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
from agent.config import default_data_root
from agent.mechanisms.providers.missing import MissingProvider
from agent.mechanisms.session_store import SessionStore
from agent.shell.fspaths import FS_ROOT_ENV
from agent.shell.web import serve

_DEFAULT_PORT = 8765

def build_shell_app(
    *,
    provider: Any = None,
    store: Any = None,
    data_root: Optional[Path] = None,
) -> App:
    """装配供 Web 壳使用的底座：默认没有模型，交给多模型插件接管。"""
    given_provider = provider is not None
    if provider is None:
        provider = MissingProvider()
    if store is None:
        store = SessionStore(Path(data_root) if data_root else default_data_root())
    return build_app(provider=provider, store=store, config_ready=given_provider, data_root=data_root)


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
    open_url = None
    if args.open_browser:
        open_url = f"http://127.0.0.1:{args.port}/"
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
