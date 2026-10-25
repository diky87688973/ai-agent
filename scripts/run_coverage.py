# -*- coding: utf-8 -*-
"""跑单测并发布覆盖率数据：写入独立文件，再持锁原子替换终点的 `.coverage`。

`coverage run` 直接写 `.coverage` 时，两个进程叠着跑（CI 与本地采集同时启动）
会互相覆盖出一份不完整的数据，读侧拿到的是错误数字而不是报错。这里把写入拆开：
唯一临时文件 → 持锁 `os.replace` 发布，读侧只会看到完整的旧文件或完整的新文件。

用法：

    python scripts/run_coverage.py            # 跑全量单测并发布 .coverage
    python scripts/run_coverage.py --html     # 另外生成 coverage_html/
    python scripts/run_coverage.py --print    # 发布后打印分包覆盖率（不判下限）
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from artifact_lock import ArtifactLock  # noqa: E402

DATA = ROOT / ".coverage"

#: 统计口径（与 `scripts/check_coverage.py` 的分包下限同源）
SOURCE_ARGS = (
    "--branch",
    "--source=agent,plugins",
    "--omit=*/web_assets/*",
)

#: Windows 上目标被读句柄占用时 `os.replace` 会失败，重试等待读侧放句柄
PUBLISH_ATTEMPTS = 30
PUBLISH_INTERVAL_S = 0.1


def build_command(data_file: Path) -> list[str]:
    """`coverage run` 的完整命令行。"""
    return [
        sys.executable, "-m", "coverage", "run", *SOURCE_ARGS,
        f"--data-file={data_file}",
        "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-t", "tests",
    ]


def publish(tmp: Path, target: Path = DATA, root: Path = ROOT) -> None:
    """持锁把临时数据文件替换成正式 `.coverage`。"""
    with ArtifactLock(root, "coverage", purpose="run_coverage"):
        last: OSError | None = None
        for _ in range(PUBLISH_ATTEMPTS):
            try:
                os.replace(tmp, target)
                return
            except PermissionError as exc:
                # 目标仍被 reader 打开：等一个间隔再试，最后一次仍失败才抛出
                last = exc
                time.sleep(PUBLISH_INTERVAL_S)
        raise RuntimeError(f"发布 .coverage 失败（目标被长期占用）：{last}")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    tmp = DATA.with_name(f".coverage.tmp.{os.getpid()}")
    cmd = build_command(tmp)
    print("$ " + " ".join(cmd), flush=True)
    code = subprocess.call(cmd, cwd=str(ROOT))
    try:
        if code != 0:
            print(f"[FAIL] 单测退出码 {code}，未发布覆盖率数据", flush=True)
            return code
        publish(tmp)
        print(f"已发布 {DATA.relative_to(ROOT)}", flush=True)
    finally:
        if tmp.exists():
            tmp.unlink()
    if "--html" in args:
        html = [sys.executable, "-m", "coverage", "html", "-d", "coverage_html"]
        code = subprocess.call(html, cwd=str(ROOT))
        if code != 0:
            print(f"[FAIL] coverage html 退出码 {code}", flush=True)
            return code
    if "--print" in args:
        check = [sys.executable, "-u", "scripts/check_coverage.py", "--print"]
        return subprocess.call(check, cwd=str(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
