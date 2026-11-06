# -*- coding: utf-8 -*-
"""出网门禁：全量跑测试时不得发起非环回网络请求。

判据不是「stderr 里有没有警告」——纯单测（`_assemble_deltas` 吃内存假 SSE 帧）
也会经 `report_error` 打出 RuntimeWarning，那是日志噪音。真正的判据是请求本身：
把 `urllib.request.urlopen` 换成记录并抛错的桩，跑全量，非环回目标必须为 0 次。

环回目标（127.0.0.1 / localhost / ::1）放行：`test_web_shell`、`test_plugin_http`
起本地 HTTP 服务并真的连它，那是本机连接，不构成出网。

用法：
    python scripts/check_network_isolation.py            # 门禁，非环回请求数必须为 0
    python scripts/check_network_isolation.py --verbose  # 逐条打印被拦截的目标
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from contextlib import suppress
from functools import partial
from pathlib import Path
from typing import Any
from unittest.mock import patch

with suppress(AttributeError, OSError, ValueError):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent

#: 本机连接：测试自带 HTTP 服务会连这些地址。
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "0.0.0.0", ""})


class NetworkBlocked(urllib.error.URLError):
    """非环回请求被门禁拦截。"""


def _url_of(target: Any) -> str:
    return target.full_url if isinstance(target, urllib.request.Request) else str(target)


def _host_of(target: Any) -> str:
    with suppress(ValueError):
        return (urllib.parse.urlsplit(_url_of(target)).hostname or "").lower()
    return ""


class _Guard:
    """替换 `urlopen`：环回放行，其余记录后抛错。"""

    def __init__(self, real: Any) -> None:
        self._real = real
        self.current = "<用例外>"
        self.blocked: list[str] = []

    def urlopen(self, target: Any, *args: Any, **kwargs: Any) -> Any:
        host = _host_of(target)
        if host in LOOPBACK_HOSTS or host.endswith(".localhost"):
            return self._real(target, *args, **kwargs)
        url = _url_of(target)
        self.blocked.append(f"{self.current} → {url}")
        raise NetworkBlocked(f"出网被门禁拦截：{url}")


class _TrackingResult(unittest.TextTestResult):
    """把当前用例名写进 guard，便于把拦截记录归到用例。"""

    def __init__(self, *args: Any, guard: _Guard, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._guard = guard

    def startTest(self, test: unittest.TestCase) -> None:
        self._guard.current = str(test)
        super().startTest(test)


def run_suite(guard: _Guard, module: str = "") -> unittest.TestResult:
    """在工程根下全量跑一遍，返回结果。"""
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    loader = unittest.TestLoader()
    suite = (loader.loadTestsFromName(module) if module else
             loader.discover("tests", pattern="test_*.py", top_level_dir="tests"))
    runner = unittest.TextTestRunner(
        stream=sys.stdout, verbosity=0,
        resultclass=partial(_TrackingResult, guard=guard),
    )
    return runner.run(suite)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="检查测试是否发起真实出网请求")
    ap.add_argument("--verbose", action="store_true", help="逐条打印被拦截的目标")
    ap.add_argument("--module", default="", help="只运行指定测试模块")
    args = ap.parse_args(argv)

    real = urllib.request.urlopen
    guard = _Guard(real)
    urllib.request.urlopen = guard.urlopen
    try:
        with tempfile.TemporaryDirectory(prefix="agent_network_tests_") as temporary:
            with patch.dict(os.environ, {"AI_AGENT_DATA_ROOT": temporary}):
                result = run_suite(guard, args.module)
    finally:
        urllib.request.urlopen = real

    print(f"用例：{result.testsRun}  失败：{len(result.failures)}  "
          f"错误：{len(result.errors)}  跳过：{len(result.skipped)}")
    print(f"非环回 urlopen 请求：{len(guard.blocked)} 次")
    if args.verbose:
        for line in guard.blocked:
            print(f"  [BLOCK] {line}")
    if not result.wasSuccessful():
        print("[FAIL] 单元测试失败，网络检查不能计为通过")
        return 1
    if guard.blocked:
        for line in guard.blocked[:20]:
            print(f"  [FAIL] {line}")
        return 1
    print("✅ 测试未发起任何非环回网络请求")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
