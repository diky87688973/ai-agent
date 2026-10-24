# -*- coding: utf-8 -*-
"""构建首次运行完整包：程序、插件、默认配置与启动器。"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.update.assets import is_local_secret, is_sensitive_plugin_config  # noqa: E402

TOP_FILES = (
    "agent-gui.exe",
    "README.md",
    "LICENSE",
    "NOTICE",
    "start.bat",
    "config.ini",
    "plugins.ini",
    "web-ui-config.ini",
    "plugins.cli.ini",
    "plugins.headless.ini",
)
TOP_DIRS = ("agent", "plugins", "assets", "templates", "rules", "skills")
SKIP_NAMES = {".env", "_PRIVATE_RULE.md"}


def _allowed(path: Path) -> bool:
    if "__pycache__" in path.parts or path.suffix in (".pyc", ".raw", ".log"):
        return False
    if path.name in SKIP_NAMES or path.name.endswith((".local.ini", ".local.toml")):
        return False
    if is_local_secret(path) or is_sensitive_plugin_config(path):
        return False
    return True


def build(version: str, output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    name = f"ai-agent-{version}-full-pack-windows.zip"
    archive = output / name
    prefix = f"ai-agent-{version}-full-pack-windows"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(f"{prefix}/VERSION", version + "\n")
        for name in TOP_FILES:
            path = ROOT / name
            if path.is_file() and _allowed(path):
                bundle.write(path, f"{prefix}/{name}")
        for part in TOP_DIRS:
            base = ROOT / part
            if not base.is_dir():
                continue
            for path in base.rglob("*"):
                if path.is_file() and _allowed(path):
                    rel = path.relative_to(ROOT).as_posix()
                    bundle.write(path, f"{prefix}/{rel}")
    with zipfile.ZipFile(archive) as check:
        names = check.namelist()
        if f"{prefix}/agent-gui.exe" not in names:
            raise RuntimeError("完整包缺少 agent-gui.exe")
        if f"{prefix}/VERSION" not in names:
            raise RuntimeError("完整包缺少 VERSION")
        for forbidden in ("/.git/", "/data/", "/tests/", "/docs/", "/updates/", "/versions/"):
            if any(forbidden in f"/{name}" for name in names):
                raise RuntimeError(f"完整包包含非交付内容：{forbidden}")
    return archive


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", default="dist")
    args = parser.parse_args()
    print(build(args.version, Path(args.output)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
