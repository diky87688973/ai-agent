# -*- coding: utf-8 -*-
"""构建完整包：全部项目文件，排除非项目资源。"""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.pack_common import project_files  # noqa: E402


def build(version: str, output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    name = f"ai-agent-{version}-full-pack-windows.zip"
    archive = output / name
    prefix = f"ai-agent-{version}-full-pack-windows"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in project_files(ROOT):
            relative = path.relative_to(ROOT).as_posix()
            if relative == "VERSION":
                continue
            bundle.write(path, f"{prefix}/{relative}")
        bundle.writestr(f"{prefix}/VERSION", version + "\n")
    with zipfile.ZipFile(archive) as check:
        names = check.namelist()
        for required in (f"{prefix}/agent-gui.exe", f"{prefix}/VERSION"):
            if required not in names:
                raise RuntimeError(f"完整包缺少 {required}")
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
