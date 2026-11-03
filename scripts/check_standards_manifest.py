# -*- coding: utf-8 -*-
"""校验 `skills/production-standards.md` 与 `standards_rules.py` 的编号集合一致。

skills 插件未启用或手册不存在时跳过；只有启用且存在时才做双向比对。
"""
from __future__ import annotations

import configparser
import re
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
MANUAL = ROOT / "skills" / "production-standards.md"
PLUGINS = ROOT / "plugins.ini"

sys.path.insert(0, str(ROOT / "scripts"))
from standards_rules import RULE_IDS, UPDATED, VERSION  # noqa: E402

_ID_RE = re.compile(r"(?m)^\*\*([A-Z][0-9]*[a-z]?)｜")
_FIELD_RE = re.compile(r"(?m)^(version|updated):\s*(\S+)\s*$")


def skills_enabled(path: Path = PLUGINS) -> bool:
    """只读取插件清单；不存在或 enabled=0 都视为未启用。"""
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            parser.read_file(handle)
    except OSError:
        return False
    if not parser.has_section("plugin:skills"):
        return False
    value = str(parser.get("plugin:skills", "enabled", fallback="1")).strip().lower()
    return value not in {"", "0", "false", "no", "off"}


def read_manifest(path: Path = MANUAL) -> tuple[str, str, frozenset[str]]:
    """读取手册 front-matter 与 `**编号｜...` 条目。"""
    text = path.read_text(encoding="utf-8")
    fields = {key: value for key, value in _FIELD_RE.findall(text)}
    return fields.get("version", ""), fields.get("updated", ""), frozenset(_ID_RE.findall(text))


def compare(version: str, updated: str, ids: Iterable[str]) -> list[str]:
    """返回与常量集合的差异；纯函数，便于负向用例。"""
    current = set(ids)
    problems: list[str] = []
    missing = sorted(set(RULE_IDS) - current)
    extra = sorted(current - set(RULE_IDS))
    if missing:
        problems.append(f"手册缺少编号：{', '.join(missing)}")
    if extra:
        problems.append(f"手册多出编号：{', '.join(extra)}")
    if version != VERSION:
        problems.append(f"版本不一致：手册 {version!r}，常量 {VERSION!r}")
    if updated != UPDATED:
        problems.append(f"更新时间不一致：手册 {updated!r}，常量 {UPDATED!r}")
    return problems


def main() -> int:
    if not skills_enabled():
        print("[SKIP] skills 插件未启用")
        return 0
    if not MANUAL.is_file():
        print(f"[SKIP] 缺少 {MANUAL.relative_to(ROOT)}")
        return 0
    version, updated, ids = read_manifest()
    problems = compare(version, updated, ids)
    print(f"准则清单：手册 {len(ids)} 条 / 常量 {len(RULE_IDS)} 条（v{version}）")
    if problems:
        print("准则清单不一致：")
        for problem in problems:
            print(f"  [FAIL] {problem}")
        return 1
    print("✅ 准则编号、版本与更新时间一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
