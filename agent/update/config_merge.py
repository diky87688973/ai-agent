# -*- coding: utf-8 -*-
"""用户配置与新版本 templates 的结构化合并。"""
from __future__ import annotations

import configparser
import shutil
from pathlib import Path
from typing import Dict, List

from agent.update.assets import is_sensitive_plugin_config

CONFIG_MAP: Dict[str, str] = {
    "config.ini.example": "config.ini",
    "plugins.ini.example": "plugins.ini",
    "web-ui-config.ini.example": "web-ui-config.ini",
}


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


def _merge_plugin_file(defaults: Path, user: Path) -> None:
    default_parser = _read(defaults)
    user_parser = _read(user)
    merged = configparser.ConfigParser(interpolation=None, strict=False)
    merged.optionxform = str
    for section in default_parser.sections():
        merged.add_section(section)
        for key, value in default_parser.items(section):
            merged.set(section, key, user_parser.get(section, key, fallback=value))
    temporary = defaults.with_name(defaults.name + ".merge.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        merged.write(handle)
    temporary.replace(defaults)


def merge_plugin_configs(root: Path, target: Path) -> None:
    root = Path(root)
    for target_file in (Path(target) / "plugins").glob("*/plugin-config.ini"):
        root_file = root / "plugins" / target_file.parent.name / "plugin-config.ini"
        if root_file.is_file():
            _merge_plugin_file(target_file, root_file)
    for root_file in (root / "plugins").glob("*/plugin-config.ini"):
        if not is_sensitive_plugin_config(root_file):
            continue
        target_file = Path(target) / "plugins" / root_file.parent.name / "plugin-config.ini"
        if not target_file.exists():
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root_file, target_file)


def merge_templates(root: Path, templates: Path) -> List[str]:
    root = Path(root)
    templates = Path(templates)
    if not templates.is_dir():
        return []
    backup = root / "updates" / "backup" / "config"
    backup.mkdir(parents=True, exist_ok=True)
    changed: List[str] = []
    for template_name, target_name in CONFIG_MAP.items():
        template = templates / template_name
        if not template.is_file():
            continue
        target = root / target_name
        if target.exists():
            shutil.copy2(target, backup / f"{target_name}.bak")
        before = target.read_text(encoding="utf-8") if target.exists() else ""
        merge_ini(target, template)
        after = target.read_text(encoding="utf-8") if target.exists() else ""
        if before != after:
            changed.append(target_name)
    return changed
