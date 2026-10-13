# -*- coding: utf-8 -*-
"""catalog 校验：对比注册文件 catalog/tools.json 与装配集实况（漂移即红灯）。

漂移 = 注册文件与代码装配不一致（生成物与单一来源失同步）。
判定：先做字节级全等（含格式/换行），不一致再给数据级定位（缺 / 多 / 变更）。

用法：python scripts/check_catalog.py（工程根运行）
退出码：0 = 零漂移；1 = 漂移 / 文件缺失或损坏。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen_catalog import CATALOG_PATH, collect_schemas, render_catalog


def diff_tools(actual: list[dict], expected: list[dict]) -> list[str]:
    """按名称对比两侧工具声明；返回漂移描述列表（空 = 一致）。"""

    def _by_name(items: list[dict]) -> dict[str, dict]:
        return {str(t.get("name") or ""): t for t in items if isinstance(t, dict)}

    a, e = _by_name(actual), _by_name(expected)
    lines: list[str] = []
    for name in sorted(set(e) - set(a)):
        lines.append(f"注册文件缺少工具：{name}")
    for name in sorted(set(a) - set(e)):
        lines.append(f"注册文件多余工具：{name}")
    for name in sorted(set(a) & set(e)):
        if a[name] != e[name]:
            lines.append(f"工具声明不一致：{name}")
    return lines


def check(catalog_path: Path = CATALOG_PATH) -> list[str]:
    """对比注册文件与装配集实况；返回问题列表（空 = 零漂移）。"""
    if not catalog_path.is_file():
        return [f"注册文件不存在：{catalog_path}（运行 python scripts/gen_catalog.py 生成）"]
    raw = catalog_path.read_bytes()
    schemas = collect_schemas()
    if raw == render_catalog(schemas).encode("utf-8"):
        return []
    try:
        payload = json.loads(raw.decode("utf-8"))
        actual = payload["tools"]
        if not isinstance(actual, list):
            raise TypeError("tools 字段不是列表")
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return [f"注册文件损坏或结构非法：{exc}"]
    return diff_tools(actual, schemas) or ["渲染格式与装配集不一致（请重新生成）"]


def main() -> int:
    problems = check()
    if problems:
        print("catalog 校验未通过：")
        for line in problems:
            print(" - " + line)
        return 1
    print("catalog 无漂移：注册文件与装配集一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
