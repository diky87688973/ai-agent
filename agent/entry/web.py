# -*- coding: utf-8 -*-
"""Web 进程入口：按配置装配 app，再交给 `agent.shell.web.server.serve`。

    python -m agent.entry.web --host 127.0.0.1 --port 8765

壳层（`agent.shell.*`）不导入装配根，所以"怎么建 app"只写在这里（A2）。
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path
from typing import Any, Optional

from agent.app import App, build_app
from agent.config import DEFAULT_CONFIG_PATH, default_data_root
from agent.mechanisms.providers.missing import MissingProvider
from agent.mechanisms.session_store import SessionStore
from agent.shell.fspaths import FS_ROOT_ENV
from agent.shell.web.auth import AuthRuntime
from agent.shell.web.auth.config import AuthConfigError
from agent.shell.web.auth.security import AuthSecurityError
from agent.shell.web.server import serve

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


def _load_auth(root: Path) -> Any:
    try:
        return AuthRuntime.load(
            root, config_path=DEFAULT_CONFIG_PATH, host="127.0.0.1")
    except (AuthConfigError, AuthSecurityError) as exc:
        print(f"[auth] {exc}")
        return None


def _auth_cli(root: Path, args: Any) -> Optional[int]:
    if args.set_password:
        password = getpass.getpass("访问密码（至少 12 位）：")
        confirm = getpass.getpass("再次输入：")
        if password != confirm:
            print("两次输入不一致")
            return 2
        if len(password) < 12:
            print("密码至少 12 位")
            return 2
        auth = _load_auth(root)
        if auth is None:
            return 2
        auth.set_password(password)
        print(f"已设置访问密码：{auth.auth_dir / 'credentials.json'}")
        return 0
    if args.issue_token:
        auth = _load_auth(root)
        if auth is None:
            return 2
        scopes = [item.strip() for item in args.scope.split(",") if item.strip()]
        try:
            token = auth.issue_token(args.issue_token, scopes)
        except (ValueError, RuntimeError) as exc:
            print(str(exc))
            return 2
        print(token)
        return 0
    if args.revoke_token:
        auth = _load_auth(root)
        if auth is None:
            return 2
        try:
            revoked = auth.revoke_token(args.revoke_token)
        except RuntimeError as exc:
            print(str(exc))
            return 2
        print("已撤销" if revoked else "Token 不存在")
        return 0
    return None


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
        help="/api/media 可读根（不设时用全部 --fs-root）",
    )
    parser.add_argument("--set-password", action="store_true",
                        help="交互式设置 Web 访问密码后退出")
    parser.add_argument("--issue-token", default="", metavar="NAME",
                        help="创建 API Token 后退出")
    parser.add_argument("--revoke-token", default="", metavar="NAME",
                        help="撤销 API Token 后退出")
    parser.add_argument("--scope", default="read",
                        help="API Token scope，逗号分隔（默认 read）")
    parser.add_argument("--tls-cert", default="",
                        help="TLS 证书路径；公网绑定必须提供")
    parser.add_argument("--tls-key", default="",
                        help="TLS 私钥路径；公网绑定必须提供")
    parser.add_argument("--allow-insecure-public", action="store_true",
                        help="显式允许无 TLS 的公网 HTTP")
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = Path(args.data_root) if args.data_root else default_data_root()
    auth_result = _auth_cli(root, args)
    if auth_result is not None:
        return auth_result
    try:
        app = build_shell_app(data_root=root)
    except RuntimeError as exc:
        print(str(exc))
        return 2
    open_url = None
    if args.open_browser:
        scheme = "https" if args.tls_cert and args.tls_key else "http"
        open_url = f"{scheme}://127.0.0.1:{args.port}/"
    return serve(
        app,
        host=args.host,
        port=args.port,
        data_root=root,
        fs_root=[Path(p) for p in args.fs_root] if args.fs_root else None,
        media_root=Path(args.media_root) if args.media_root else None,
        open_url=open_url,
        tls_cert=args.tls_cert or None,
        tls_key=args.tls_key or None,
        allow_insecure_public=args.allow_insecure_public,
    )


if __name__ == "__main__":
    sys.exit(main())
