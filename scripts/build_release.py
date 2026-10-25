# -*- coding: utf-8 -*-
"""构建软件更新包：全部项目文件 + manifest。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.pack_common import project_files  # noqa: E402


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(version: str, output: Path) -> tuple[Path, Path]:
    output.mkdir(parents=True, exist_ok=True)
    name = f"ai-agent-{version}-update-pack-windows.zip"
    archive = output / name
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in project_files(ROOT):
            relative = path.relative_to(ROOT).as_posix()
            if relative == "VERSION":
                continue
            bundle.write(path, f"payload/{relative}")
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
