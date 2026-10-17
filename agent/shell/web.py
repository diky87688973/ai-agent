# -*- coding: utf-8 -*-
"""Web 壳——HTTP/SSE 服务装配入口。

业务实现拆到：
- `web_static` 静态路径与常量
- `web_api` WebShell 业务动作
- `web_routes` HTTP 路由
- `sse` SSE 传输层

对外导入约定保持：`from agent.shell.web import _Channel` / `WebShell` / `create_server` 等仍可用。
"""
from __future__ import annotations

import os
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional, Tuple

from agent.app import App, build_app
from agent.config import (
    default_data_root,
    get_context,
    get_model_reasoning,
)
from agent.mechanisms.model_provider import OpenAICompatibleProvider
from agent.mechanisms.session_store import SessionStore
from agent.mechanisms.session_title import make_provider_title_generator

# 路径安全：外部按 `agent.shell.web` 导入这些名字。
from agent.shell.fspaths import (  # noqa: F401
    _default_fs_roots,
    _env_path,
    _env_roots,
    _fs_rejection,
    _is_drive_root,
    _list_drives,
    _normalize_roots,
    _parse_roots,
    _within_any_root,
)
from agent.shell.sse import _Channel, _event_seq, _sse_payload  # noqa: F401
from agent.shell.web_api import WebShell, _date_group, _normalize_images  # noqa: F401
from agent.shell.web_routes import _Handler
from agent.shell.web_static import (  # noqa: F401
    _FS_ROOT_ENV,
    _IMAGE_MIMES,
    ASSETS_DIR,
    MAX_BODY_BYTES,
    MAX_IMAGES,
    MODE_VALUES,
    SSE_HEARTBEAT_SEC,
    _lang_from_path,
    _looks_binary,
    _plugin_asset_rel,
)


def create_server(
    app: App,
    host: str = "127.0.0.1",
    port: int = 8765,
    assets_dir: Optional[Path] = None,
    media_root: Optional[Path] = None,
    fs_root: Any = None,
    titles_dir: Optional[Path] = None,
    title_generator: Any = None,
    workspace_root: Optional[Path] = None,
) -> Tuple[ThreadingHTTPServer, WebShell]:
    """构造（不启动）Web 服务；返回 (server, shell)。调 server.serve_forever() 启动。"""
    if title_generator is None and app.provider is not None:
        title_generator = make_provider_title_generator(app.provider)
    roots = _normalize_roots(fs_root) or _default_fs_roots()
    shell = WebShell(
        app,
        media_root=media_root or (roots[0] if roots else Path.cwd()),
        fs_roots=roots,
        titles_dir=titles_dir,
        title_generator=title_generator,
        workspace_root=workspace_root,
    )
    bus = app.event_bus
    if bus is not None:
        bus.subscribe_all(shell.broadcast)

    handler = type(
        "_BoundHandler",
        (_Handler,),
        {"shell": shell, "assets_dir": Path(assets_dir) if assets_dir else ASSETS_DIR},
    )

    class _Server(ThreadingHTTPServer):
        allow_reuse_address = False

    try:
        server = _Server((host, int(port)), handler)
    except OSError as exc:
        print(f"[web] 无法绑定 {host}:{port} —— {exc}", file=sys.stderr, flush=True)
        print("[web] 端口已被占用。请换端口；并注意**改代码后必须重启服务**，"
              "否则连上的仍是旧代码（`ui_bundle.inline_ui_html` 还有 `lru_cache`，"
              "连 JS 都要重启才生效）。", file=sys.stderr, flush=True)
        raise
    server.daemon_threads = True
    return server, shell


def build_shell_app(
    *,
    provider: Any = None,
    store: Any = None,
    data_root: Optional[Path] = None,
) -> App:
    """装配供 Web 壳使用的底座：默认真实 provider（按 config）+ 会话存储。"""
    if provider is None:
        cfg = get_model_reasoning()
        if not cfg["api_key"] or not cfg["api_base_url"]:
            raise RuntimeError(
                "缺少配置：config.ini 的 [model_reasoning]（api_base_url / api_key / model）"
            )
        provider = OpenAICompatibleProvider(
            base_url=cfg["api_base_url"], api_key=cfg["api_key"], model=cfg["model"],
            replay_history_reasoning=bool(get_context().get("replay_history_reasoning")),
        )
    if store is None:
        store = SessionStore(Path(data_root) if data_root else default_data_root())
    return build_app(provider=provider, store=store)


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    provider: Any = None,
    store: Any = None,
    data_root: Optional[Path] = None,
    media_root: Optional[Path] = None,
    fs_root: Any = None,
) -> int:
    """启动 Web 壳（阻塞）；Ctrl+C 退出。"""
    root = Path(data_root) if data_root else default_data_root()
    try:
        app = build_shell_app(provider=provider, store=store, data_root=root)
    except RuntimeError as exc:
        print(str(exc))
        return 2
    roots = _normalize_roots(fs_root) or _env_roots("AI_AGENT_FS_ROOT") or _default_fs_roots()
    resolved_media = media_root or _env_path("AI_AGENT_MEDIA_ROOT") or (
        roots[0] if roots else Path.cwd()
    )
    server, _shell = create_server(
        app,
        host=host,
        port=port,
        media_root=resolved_media,
        fs_root=roots,
        titles_dir=root / "titles",
        workspace_root=root / "workspace",
    )
    print("=== AI Agent Web 壳 ===")
    print(f"主界面   http://{host}:{port}/")
    print(f"事件流   http://{host}:{port}/api/events/stream")
    shown = "；".join(str(r) for r in roots) if roots else "（不限根）"
    print(f"文件根   {shown}")
    print("         （右栏文件查看器 / @ 补全的可见范围；--fs-root 可改，多个用 ; 分隔）")
    print("（Ctrl+C 退出）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[已停止]")
    finally:
        server.shutdown()
        server.server_close()
        app.dispose()
    return 0


def main(argv: Optional[list] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="agent.shell.web", description="AI Agent Web 壳")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-root", default="")
    parser.add_argument(
        "--fs-root",
        action="append",
        default=[],
        metavar="PATH",
        help=(
            "右栏文件查看器 / @ 补全的可见根；可重复指定多个。"
            f"默认 = 本机各盘根（与 agent 的读写范围一致）。亦可用 {_FS_ROOT_ENV}（{os.pathsep} 分隔）"
        ),
    )
    parser.add_argument(
        "--media-root",
        default="",
        help="/api/media 可读根（默认与第一个 --fs-root 相同）",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    return serve(
        host=args.host,
        port=args.port,
        data_root=Path(args.data_root) if args.data_root else None,
        fs_root=[Path(p) for p in args.fs_root] if args.fs_root else None,
        media_root=Path(args.media_root) if args.media_root else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
