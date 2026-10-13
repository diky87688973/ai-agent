# -*- coding: utf-8 -*-
"""catalog 生成器：扫描装配工具集 → 生成注册文件 catalog/tools.json。

单一来源：`agent.app.build_app()` 装配的工具注册表（工具即代码）；
本脚本将注册表渲染为确定性注册文件（UTF-8 直出 / 缩进 2 / 键排序 / LF 换行）。
漂移校验：scripts/check_catalog.py（注册文件与装配集不一致即红灯）。

用法：python scripts/gen_catalog.py（工程根运行）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.app import build_app  # noqa: E402

CATALOG_PATH = ROOT / "catalog" / "tools.json"


def collect_schemas() -> list[dict]:
    """扫描装配集：构建 app 并导出全部已注册工具声明（注册表已按名称排序）。"""
    return build_app().registry.schemas()


def render_catalog(schemas: list[dict]) -> str:
    """渲染注册文件文本：JSON（UTF-8 直出 / 缩进 2 / 键排序）+ 末尾换行（LF）。"""
    return json.dumps({"tools": schemas}, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_catalog(path: Path = CATALOG_PATH) -> int:
    """渲染并写出注册文件（固定 LF 换行）；返回工具数量。"""
    schemas = collect_schemas()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_catalog(schemas))
    return len(schemas)


def main() -> int:
    count = write_catalog()
    print(f"catalog 已生成：{CATALOG_PATH.relative_to(ROOT).as_posix()}（{count} 个工具）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
