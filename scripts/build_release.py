# -*- coding: utf-8 -*-
"""构建软件更新包：payload/zip + manifest。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.update.assets import is_local_secret, is_sensitive_plugin_config  # noqa: E402

PAYLOAD_PARTS = ("agent", "plugins", "assets", "templates")


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_plugins() -> None:
    for plugin in (ROOT / "plugins").iterdir():
        if not plugin.is_dir() or not (plugin / "plugin.py").is_file():
            continue
        config = plugin / "plugin-config.ini"
        example = plugin / "plugin-config.ini.example"
        if not config.is_file() and not example.is_file():
            continue
        if config.is_file() and not is_sensitive_plugin_config(config):
            continue
        if not config.is_file() and not is_sensitive_plugin_config(config):
            raise RuntimeError(f"插件缺少配置：{plugin.name}")
        # 敏感配置允许本地保留，不进入发布包。
        if config.is_file() and is_sensitive_plugin_config(config):
            continue


def build(version: str, output: Path) -> tuple[Path, Path]:
    validate_plugins()
    output.mkdir(parents=True, exist_ok=True)
    name = f"ai-agent-{version}.zip"
    archive = output / name
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for part in PAYLOAD_PARTS:
            base = ROOT / part
            if not base.is_dir():
                continue
            for path in base.rglob("*"):
                if not path.is_file() or "__pycache__" in path.parts:
                    continue
                if is_local_secret(path) or is_sensitive_plugin_config(path):
                    continue
                bundle.write(path, f"payload/{path.relative_to(ROOT).as_posix()}")
        bundle.writestr("payload/VERSION", version + "\n")
    manifest = {
        "schema": 1,
        "app": "ai-agent",
        "version": version,
        "channel": "stable",
        "published_at": "",
        "asset": {
            "name": name,
            "size": archive.stat().st_size,
            "sha256": _digest(archive),
        },
        "notes": [],
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    return archive, manifest_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", default="dist")
    args = parser.parse_args()
    archive, manifest = build(args.version, Path(args.output))
    print(archive)
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
