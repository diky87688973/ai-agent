# -*- coding: utf-8 -*-
"""Web 壳——HTTP/SSE 服务装配入口。

业务实现拆到：
- `web_static` 静态路径与常量
- `web_api` WebShell 业务动作
- `web_routes` HTTP 路由
- `sse` SSE 传输层

本模块只负责装配壳对象（`create_server` 返回未启动的 server）：
进程入口与 `build_app()` 的调用在 `agent/entry/web.py`（A2：壳层不得反向依赖装配根）。
"""
from __future__ import annotations

import sys
import threading
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Tuple

if TYPE_CHECKING:  # 只为注解：运行期不导入装配根
    from agent.app import App


from agent.mechanisms.session_title import make_provider_title_generator
from agent.shell.fspaths import (
    default_fs_roots,
    normalize_roots,
    resolve_fs_roots,
    resolve_media_root,
)
from agent.shell.web.web_api import WebShell
from agent.shell.web.web_routes import Handler
from agent.shell.web.web_static import ASSETS_DIR


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
    roots = normalize_roots(fs_root) or default_fs_roots()
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
        (Handler,),
        {"shell": shell, "assets_dir": Path(assets_dir) if assets_dir else ASSETS_DIR},
    )

    class _Server(ThreadingHTTPServer):
        allow_reuse_address = False

    try:
        server = _Server((host, int(port)), handler)
    except OSError as exc:
        print(f"[web] 无法绑定 {host}:{port} —— {exc}", file=sys.stderr, flush=True)
        print("[web] 端口已被占用。请换端口；并注意改代码后必须重启服务，"
              "否则连上的仍是旧代码（`ui_bundle.inline_ui_html` 还有 `lru_cache`，"
              "连 JS 都要重启才生效）。", file=sys.stderr, flush=True)
        raise
    server.daemon_threads = True
    return server, shell


def serve(
    app: App,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    data_root: Optional[Path] = None,
    media_root: Any = None,
    fs_root: Any = None,
    open_url: Optional[str] = None,
) -> int:
    """在已装配的 app 上启动 Web 壳（阻塞）；Ctrl+C 退出。

    这里只做"壳怎么跑"：可见根、媒体根、标题与工作目录的落点都在壳内决定。
    app 从哪来由入口层负责（A2：shell 不导入装配根）。
    """
    root = Path(data_root) if data_root else Path.cwd()
    roots = resolve_fs_roots(fs_root)
    server, _shell = create_server(
        app,
        host=host,
        port=port,
        media_root=resolve_media_root(roots, media_root),
        fs_root=roots,
        titles_dir=root / "titles",
        workspace_root=root / "workspace",
    )
    print("=== AI Agent Web 壳 ===")
    print(f"主界面   http://{host}:{port}/")
    if getattr(app, "model_config_state", "") == "none":
        print("模型尚未配置：可在页面右上角「设置 → 插件 → 多模型」里添加。")
    print(f"事件流   http://{host}:{port}/api/events/stream")
    shown = "；".join(str(r) for r in roots) if roots else "（不限根）"
    print(f"文件根   {shown}")
    print("         （右栏文件查看器 / @ 补全的可见范围；--fs-root 可改，多个用 ; 分隔）")
    print("（Ctrl+C 退出）")
    if open_url:
        def _open() -> None:
            try:
                if not webbrowser.open(open_url):
                    print(f"[web] 未能自动打开浏览器，请访问 {open_url}", file=sys.stderr)
            except Exception as exc:
                print(f"[web] 打开浏览器失败：{type(exc).__name__}: {exc}；请访问 {open_url}",
                      file=sys.stderr)

        timer = threading.Timer(0.5, _open)
        timer.daemon = True
        timer.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[已停止]")
    finally:
        server.shutdown()
        server.server_close()
        app.dispose()
    return 0

