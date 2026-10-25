# -*- coding: utf-8 -*-
"""首次运行：确保 pywebview 可用；依赖只装到用户缓存，不写项目。"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_VERSION = "6.2.1"


def deps_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return base / "ai-agent" / "pydeps"


def main() -> int:
    target = deps_dir()
    if target.is_dir():
        sys.path.insert(0, str(target))
    if importlib.util.find_spec("webview") is not None:
        return 0
    target.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--target",
        str(target),
        f"pywebview=={DEFAULT_VERSION}",
    ]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        print("pywebview 安装失败", file=sys.stderr)
        return 1
    sys.path.insert(0, str(target))
    if importlib.util.find_spec("webview") is None:
        print("pywebview 安装后仍无法导入", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
