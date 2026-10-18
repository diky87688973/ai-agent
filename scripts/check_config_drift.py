# -*- coding: utf-8 -*-
"""配置漂移门禁：`.example`、schema、真实配置文件三者必须一致。

规则（双向，任何一条不满足都退出 1）：

1. `config.ini.example` 的节/键 必须精确等于 `agent.config_schema.SCHEMA`：
   模板缺键 → 用户照抄后功能静默失效；模板多键 → 模板在承诺不存在的功能。
2. `web-ui-config.ini.example` 必须存在且精确等于 `WEB_UI_SCHEMA`
   （真实 `web-ui-config.ini` 不入库，见 `.gitignore`）。
3. 真实的 `config.ini` / `web-ui-config.ini` 若存在，只允许是 schema 的子集：
   多出来的键通常是拼写错误，必须报出来（报行号）。

用法：python scripts/check_config_drift.py
"""
from __future__ import annotations

import configparser
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.config_schema import MULTI_MODEL_SCHEMA, SCHEMA, WEB_UI_SCHEMA  # noqa: E402

CONFIG_TEMPLATE = ROOT / "config.ini.example"
CONFIG_REAL = ROOT / "config.ini"
WEB_UI_TEMPLATE = ROOT / "web-ui-config.ini.example"
WEB_UI_REAL = ROOT / "web-ui-config.ini"
MODEL_PLUGIN_TEMPLATE = ROOT / "plugins" / "multi_model" / "plugin-config.ini.example"
MODEL_PLUGIN_REAL = ROOT / "plugins" / "multi_model" / "plugin-config.ini"


def parse_ini(text: str, name: str) -> configparser.ConfigParser:
    """按与 `agent.config.load_ini` 相同的编码口径解析（吞 BOM）。"""
    parser = configparser.ConfigParser()
    parser.read_string(text, source=name)
    return parser


def _line_of_key(text: str, section: str, key: str) -> int:
    """给报错找行号；找不到时退回 0（错误本身仍然报）。"""
    current = ""
    for lineno, raw in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip()
            continue
        if current == section and "=" in line:
            name = line.split("=", 1)[0].strip()
            if name == key:
                return lineno
    return 0


def compare_exact(text: str, name: str, schema: Dict[str, Dict[str, str]]) -> List[str]:
    """模板必须与 schema 精确相等（节与键都双向比对）。"""
    problems: List[str] = []
    try:
        parser = parse_ini(text, name)
    except configparser.Error as exc:
        return [f"{name}: 无法解析（{exc}）"]
    expected_sections = set(schema)
    actual_sections = set(parser.sections())
    for section in sorted(expected_sections - actual_sections):
        problems.append(f"{name}: 缺节 [{section}]（schema 已登记）")
    for section in sorted(actual_sections - expected_sections):
        problems.append(f"{name}: 多出未登记的节 [{section}]")
    for section in sorted(expected_sections & actual_sections):
        expected = set(schema[section])
        actual = set(parser[section].keys())
        lineno_section = _line_of_key(text, section, next(iter(expected), "")) if expected else 0
        for key in sorted(expected - actual):
            problems.append(f"{name}: [{section}] 缺键 `{key}`（schema 已登记）")
        for key in sorted(actual - expected):
            problems.append(
                f"{name}:{_line_of_key(text, section, key) or lineno_section}: "
                f"[{section}] 未登记的键 `{key}`"
            )
    return problems


def compare_subset(text: str, name: str, schema: Dict[str, Dict[str, str]]) -> List[str]:
    """真实配置只允许是 schema 的子集（缺键合法，多键非法）。"""
    problems: List[str] = []
    try:
        parser = parse_ini(text, name)
    except configparser.Error as exc:
        return [f"{name}: 无法解析（{exc}）"]
    for section in parser.sections():
        if section not in schema:
            problems.append(f"{name}: 多出未登记的节 [{section}]")
            continue
        for key in sorted(set(parser[section].keys()) - set(schema[section])):
            problems.append(
                f"{name}:{_line_of_key(text, section, key)}: "
                f"[{section}] 未登记的键 `{key}`（拼写错误？）"
            )
    return problems


def compare_plugin_model_template(
    text: str,
    name: str,
    schema: Dict[str, Dict[str, str]] = MULTI_MODEL_SCHEMA,
) -> List[str]:
    """插件模型配置模板：`[base]` 精确、动态的 `[model:*]` 取键并集双向比对。

    单条目允许省略不适用于自己的键（openai 条目不写 thinking），所以不能
    逐节精确比对；但模板整体必须把所有合法键示范出来，且不能多出 schema
    未登记的键 —— 少一个键，用户照抄后功能静默失效；多一个键，模板在承诺
    解析器不认的功能。
    """
    problems: List[str] = []
    try:
        parser = parse_ini(text, name)
    except configparser.Error as exc:
        return [f"{name}: 无法解析（{exc}）"]
    base = schema.get("base", {})
    model = schema.get("model", {})
    seen_model: set = set()
    has_model_section = False
    for section in parser.sections():
        if section == "base":
            actual = set(parser[section].keys())
            problems.extend(
                f"{name}: [base] 缺键 `{key}`" for key in sorted(set(base) - actual))
            problems.extend(
                f"{name}:{_line_of_key(text, section, key)}: [base] 未登记的键 `{key}`"
                for key in sorted(actual - set(base)))
        elif section.startswith("model:"):
            has_model_section = True
            actual = set(parser[section].keys())
            seen_model |= actual
            problems.extend(
                f"{name}:{_line_of_key(text, section, key)}: "
                f"[{section}] 未登记的键 `{key}`"
                for key in sorted(actual - set(model)))
        else:
            problems.append(f"{name}: 多出未登记的节 [{section}]")
    if "base" not in parser.sections():
        problems.append(f"{name}: 缺节 [base]")
    if not has_model_section:
        problems.append(f"{name}: 缺 [model:<id>] 示例节")
    problems.extend(
        f"{name}: [model:*] 模板缺键 `{key}`（schema 已登记）"
        for key in sorted(set(model) - seen_model))
    return problems


def compare_plugin_model_real(
    text: str,
    name: str,
    schema: Dict[str, Dict[str, str]] = MULTI_MODEL_SCHEMA,
) -> List[str]:
    """真实插件配置只允许是 schema 的子集：多节、多键都失败，缺键合法。"""
    problems: List[str] = []
    try:
        parser = parse_ini(text, name)
    except configparser.Error as exc:
        return [f"{name}: 无法解析（{exc}）"]
    base = set(schema.get("base", {}))
    model = set(schema.get("model", {}))
    for section in parser.sections():
        if section == "base":
            allowed = base
        elif section.startswith("model:"):
            allowed = model
        else:
            problems.append(f"{name}: 多出未登记的节 [{section}]")
            continue
        for key in sorted(set(parser[section].keys()) - allowed):
            problems.append(
                f"{name}:{_line_of_key(text, section, key)}: "
                f"[{section}] 未登记的键 `{key}`（拼写错误？）"
            )
    return problems


def check_files(
    template: Path = CONFIG_TEMPLATE,
    real: Path = CONFIG_REAL,
    web_template: Path = WEB_UI_TEMPLATE,
    web_real: Path = WEB_UI_REAL,
    model_plugin_template: Path = MODEL_PLUGIN_TEMPLATE,
    model_plugin_real: Path = MODEL_PLUGIN_REAL,
) -> Tuple[List[str], List[str]]:
    """返回 `(违规, 跳过说明)`：违规非空即失败；跳过说明只打印。"""
    problems: List[str] = []
    skipped: List[str] = []
    if not template.is_file():
        problems.append(f"{template.name}: 模板不存在")
    else:
        problems.extend(compare_exact(template.read_text(encoding="utf-8-sig"),
                                     template.name, SCHEMA))
    if real.is_file():
        problems.extend(compare_subset(real.read_text(encoding="utf-8-sig"),
                                      real.name, SCHEMA))
    else:
        skipped.append(f"{real.name} 不存在（用户未创建，跳过子集检查）")

    if not web_template.is_file():
        problems.append(f"{web_template.name}: 模板不存在")
    else:
        problems.extend(compare_exact(web_template.read_text(encoding="utf-8-sig"),
                                      web_template.name, WEB_UI_SCHEMA))
    if web_real.is_file():
        problems.extend(compare_subset(web_real.read_text(encoding="utf-8-sig"),
                                      web_real.name, WEB_UI_SCHEMA))
    else:
        skipped.append(f"{web_real.name} 不存在（默认值生效，跳过子集检查）")

    if not model_plugin_template.is_file():
        problems.append(f"{model_plugin_template.name}: 模板不存在")
    else:
        problems.extend(compare_plugin_model_template(
            model_plugin_template.read_text(encoding="utf-8-sig"),
            model_plugin_template.name,
        ))
    if model_plugin_real.is_file():
        problems.extend(compare_plugin_model_real(
            model_plugin_real.read_text(encoding="utf-8-sig"),
            model_plugin_real.name,
        ))
    else:
        skipped.append(f"{model_plugin_real.name} 不存在（插件未配置，跳过子集检查）")
    return problems, skipped


def main() -> int:
    problems, skipped = check_files()
    for note in skipped:
        print(f"[SKIP] {note}")
    if problems:
        print("配置漂移：")
        for problem in problems:
            print(f"  [FAIL] {problem}")
        print("修法：改模板/schema/真实文件之一，三者保持一致；真实文件里的多余键删掉。")
        return 1
    print("配置一致性检查通过（模板 = schema，真实文件 ⊆ schema）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
