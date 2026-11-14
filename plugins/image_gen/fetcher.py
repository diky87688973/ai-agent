"""按清单下载模型权重；支持断点续传与体积校验，失败即非零退出。"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

import models


def download(repo: str, name: str, dest_dir: Path, mirror: str) -> None:
    dest = dest_dir / Path(name).name
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = f"{mirror}/{repo}/resolve/main/{name}"
    head = requests.head(url, allow_redirects=True, timeout=30)
    total = int(head.headers.get("content-length") or 0)
    if dest.is_file() and total and dest.stat().st_size == total:
        print("skip", dest.name, flush=True)
        return
    done = dest.stat().st_size if dest.is_file() else 0
    headers = {"Range": f"bytes={done}-"} if done else {}
    mode = "ab" if done else "wb"
    t0 = time.time()
    with requests.get(url, stream=True, timeout=(30, 120), headers=headers) as resp:
        resp.raise_for_status()
        with dest.open(mode) as handle:
            for chunk in resp.iter_content(1024 * 1024 * 4):
                if chunk:
                    handle.write(chunk)
                    done += len(chunk)
    print("ok %s %.2f GB %.1fs" % (
        dest.name, dest.stat().st_size / 2 ** 30, time.time() - t0), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--model-dir", required=True)
    args = ap.parse_args()

    spec = models.find(args.model)
    if spec["auth_required"]:
        print("该模型所在仓库需要授权，无法匿名下载：", args.model, flush=True)
        return 2
    root = Path(args.model_dir)
    for repo, name, sub in spec["files"]:
        try:
            download(repo, name, root / sub, models.MIRROR)
        except Exception as exc:
            print("FAIL", repo, name, type(exc).__name__, exc, file=sys.stderr, flush=True)
            return 1
    print("DONE", args.model, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
