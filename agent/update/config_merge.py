# -*- coding: utf-8 -*-
"""用户与默认配置的 key 级合并。"""
from __future__ import annotations

import configparser
import shutil
from pathlib import Path


def _read(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read(path, encoding="utf-8-sig")
    return parser


def merge_ini(existing: Path, template: Path, *, preserve_user_keys: bool = False) -> None:
    defaults = _read(template)
    if not existing.exists():
        shutil.copyfile(template, existing)
        return
    user = _read(existing)
    merged = configparser.ConfigParser(interpolation=None, strict=False)
    merged.optionxform = str
    for section in defaults.sections():
        merged.add_section(section)
        for key, value in defaults.items(section):
            merged.set(section, key, user.get(section, key, fallback=value))
        if preserve_user_keys and user.has_section(section):
            # 原地升级不能因为模板没有这个键就删用户配置；新版本新增的键仍会补上。
            for key, value in user.items(section):
                if not merged.has_option(section, key):
                    merged.set(section, key, value)
    # 模板只提供默认键；用户新增的“整节”必须保留。模板节内的未知键仍按模板淘汰，
    # 这样升级才能清掉已废弃的配置项。
    for section in user.sections():
        if merged.has_section(section):
            continue
        merged.add_section(section)
        for key, value in user.items(section):
            merged.set(section, key, value)
    temporary = existing.with_name(existing.name + ".merge.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        merged.write(handle)
    temporary.replace(existing)


