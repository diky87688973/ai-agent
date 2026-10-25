# -*- coding: utf-8 -*-
"""扫描版本库中的高置信度秘密模式。

只扫描 git 跟踪的文本文件；命中时输出 路径:行号:类别。
逐行 allowlist 标记：`pragma: allowlist secret`。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Iterable, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
ALLOW_MARKER = "pragma: allowlist secret"
MAX_BYTES = 2 * 1024 * 1024

PATTERNS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private key", re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    )),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("API key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("credential assignment", re.compile(
        r"(?i)\b(?:api[_-]?key|secret|password|access[_-]?token)\b"
        r"\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}['\"]"
    )),
)


def scan_text(text: str) -> List[Tuple[int, str]]:
    """返回文本中的 (行号, 类别)；allowlist 行跳过。"""
    findings: List[Tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if ALLOW_MARKER in line:
            continue
        for label, pattern in PATTERNS:
            if pattern.search(line):
                findings.append((lineno, label))
    return findings


def tracked_files() -> Iterable[Path]:
    try:
        raw = subprocess.run(
            ["git", "ls-files", "-z"], cwd=str(ROOT),
            check=True, capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"[check_secrets] git ls-files 失败：{type(exc).__name__}: {exc}")
        return
    for item in raw.decode("utf-8", "replace").split("\0"):
        if item:
            yield ROOT / item


def main() -> int:
    findings: List[Tuple[str, int, str]] = []
    for path in tracked_files():
        try:
            if not path.is_file() or path.stat().st_size > MAX_BYTES:
                continue
            data = path.read_bytes()
        except OSError as exc:
            print(f"[check_secrets] 读取失败：{path}: {type(exc).__name__}: {exc}")
            return 1
        if b"\0" in data:
            continue
        text = data.decode("utf-8", "replace")
        for lineno, label in scan_text(text):
            findings.append((path.relative_to(ROOT).as_posix(), lineno, label))
    if not findings:
        print("✅ 未发现高置信度秘密")
        return 0
    for rel, lineno, label in findings:
        print(f"[FAIL] {rel}:{lineno}: {label}")
    print(f"秘密扫描失败：{len(findings)} 处")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
