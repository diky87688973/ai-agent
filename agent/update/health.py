# -*- coding: utf-8 -*-
"""更新后自检：导入、版本、配置、插件与端口。"""
from __future__ import annotations

import configparser
import os
import socket
import sys
from pathlib import Path

from agent.core.error_report import report_error
from agent.update.version import Version


def _check_config(root: Path) -> None:
    path = root / "config.ini"
    if not path.is_file():
        return
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.read(path, encoding="utf-8-sig")


def main() -> int:
    payload = Path.cwd()
    root = Path(os.environ.get("AI_AGENT_HEALTH_ROOT") or payload)
    try:
        import agent.app
        import agent.entry.web  # noqa: F401
        Version.parse((payload / "VERSION").read_text(encoding="utf-8").strip())
        _check_config(root)
        for config in (payload / "plugins").glob("*/plugin-config.ini"):
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            parser.read(config, encoding="utf-8-sig")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
    except Exception as exc:
        report_error("agent.update.health", exc, payload=str(payload))
        print(f"health check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
