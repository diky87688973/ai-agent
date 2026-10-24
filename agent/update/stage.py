# -*- coding: utf-8 -*-
"""更新包下载、哈希校验与安全解压。"""
from __future__ import annotations

import shutil
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from agent.update.manifest import UpdateManifest, verify_asset

MAX_EXTRACT_BYTES = 1024 * 1024 * 1024
MAX_FILES = 20000


class UpdateArchiveError(ValueError):
    pass


def _safe_name(name: str) -> str:
    raw = str(name or "").replace("\\", "/")
    if not raw or raw.startswith("/") or raw.startswith("../") or "/../" in raw:
        raise UpdateArchiveError(f"非法压缩包路径：{name}")
    if len(raw) > 1 and raw[1] == ":":
        raise UpdateArchiveError(f"非法压缩包路径：{name}")
    return raw


def _download(url: str, target: Path, expected_size: int) -> None:
    if not url.lower().startswith("https://"):
        raise ValueError("更新包地址必须是 HTTPS")
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=30) as response, target.open("wb") as out:
        total = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > expected_size:
                raise ValueError("更新包超过 manifest 声明大小")
            out.write(chunk)


def stage_package(
    manifest: UpdateManifest,
    *,
    manifest_url: str,
    updates_dir: Path,
) -> Path:
    version = str(manifest.version)
    download_dir = Path(updates_dir) / "download"
    staging_dir = Path(updates_dir) / "staging" / version
    archive = download_dir / manifest.asset_name
    asset_url = urllib.parse.urljoin(manifest_url, manifest.asset_name)
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    try:
        _download(asset_url, archive, manifest.asset_size)
        verify_asset(archive, manifest)
        with zipfile.ZipFile(archive) as bundle:
            members = bundle.infolist()
            if len(members) > MAX_FILES:
                raise UpdateArchiveError("压缩包文件数超限")
            total = 0
            for member in members:
                name = _safe_name(member.filename)
                if member.is_dir():
                    continue
                target = (staging_dir / name).resolve()
                if staging_dir.resolve() not in target.parents:
                    raise UpdateArchiveError(f"压缩包越界：{name}")
                total += int(member.file_size)
                if total > MAX_EXTRACT_BYTES:
                    raise UpdateArchiveError("压缩包解压后体积超限")
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as src, target.open("wb") as out:
                    shutil.copyfileobj(src, out, 1024 * 1024)
        (staging_dir / ".ready").write_text(version, encoding="utf-8")
        return staging_dir
    except Exception:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    finally:
        if archive.exists():
            archive.unlink()
