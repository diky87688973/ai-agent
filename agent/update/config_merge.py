# -*- coding: utf-8 -*-
"""用户与默认配置的 key 级合并。"""
from __future__ import annotations

import configparser
import shutil
from pathlib import Path


def _read(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read(path, encoding="utf-8")
    return parser


def merge_ini(existing: Path, template: Path) -> None:
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
    temporary = existing.with_name(existing.name + ".merge.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        merged.write(handle)
    temporary.replace(existing)


