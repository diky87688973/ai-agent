# -*- coding: utf-8 -*-
"""配置漂移门禁：真实配置只允许使用 schema 已登记的节与键。

配置样例文件已移除；内核配置与 Web UI 配置入库，多模型密钥配置被 `.gitignore` 忽略。
门禁只检查现有真实文件，缺文件表示使用代码默认值，不报错。
"""
from __future__ import annotations

import configparser
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# 在 GBK 控制台直接跑本脚本时，打印 ✅/中文会抛 UnicodeEncodeError ——
# 表现为「检查全过但退出码 1」（`ci.py` 用 PYTHONIOENCODING 掩盖了它）。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    # 旁路，刻意吞掉：不是所有 stdout 都支持 reconfigure（被重定向/被包装时会抛）。
    # 这只是"让打印别因编码失败"的尽力而为 —— 失败就按原编码走，不该阻断检查本身。
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.config_schema import MULTI_MODEL_SCHEMA, SCHEMA, WEB_UI_SCHEMA  # noqa: E402

CONFIG_REAL = ROOT / "config.ini"
WEB_UI_REAL = ROOT / "web-ui-config.ini"
MODEL_PLUGIN_REAL = ROOT / "plugins" / "multi_model" / "plugin-config.ini"


def parse_ini(text: str, name: str) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read_string(text, source=name)
    return parser


def _line_of_key(text: str, section: str, key: str) -> int:
    current = ""
    for lineno, raw in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip()
            continue
        if current == section and "=" in line:
            if line.split("=", 1)[0].strip() == key:
                return lineno
    return 0


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


def compare_plugin_model_real(
    text: str,
    name: str,
    schema: Dict[str, Dict[str, str]] = MULTI_MODEL_SCHEMA,
) -> List[str]:
    """多模型真实配置：`[model:*]` 的键必须是 schema 子集。"""
    problems: List[str] = []
    try:
        parser = parse_ini(text, name)
    except configparser.Error as exc:
        return [f"{name}: 无法解析（{exc}）"]
    model = set(schema.get("model", {}))
    for section in parser.sections():
        allowed = model if section.startswith("model:") else None
        if allowed is None:
            problems.append(f"{name}: 多出未登记的节 [{section}]")
            continue
        for key in sorted(set(parser[section].keys()) - allowed):
            problems.append(
                f"{name}:{_line_of_key(text, section, key)}: "
                f"[{section}] 未登记的键 `{key}`（拼写错误？）"
            )
    return problems


def check_files(
    real: Path = CONFIG_REAL,
    web_real: Path = WEB_UI_REAL,
    model_plugin_real: Path = MODEL_PLUGIN_REAL,
) -> Tuple[List[str], List[str]]:
    """返回 `(违规, 跳过说明)`；缺真实文件只跳过，不失败。"""
    problems: List[str] = []
    skipped: List[str] = []
    if real.is_file():
        problems.extend(compare_subset(real.read_text(encoding="utf-8-sig"), real.name, SCHEMA))
    else:
        skipped.append(f"{real.name} 不存在（代码默认值生效）")
    if web_real.is_file():
        problems.extend(compare_subset(
            web_real.read_text(encoding="utf-8-sig"), web_real.name, WEB_UI_SCHEMA))
    else:
        skipped.append(f"{web_real.name} 不存在（代码默认值生效）")
    if model_plugin_real.is_file():
        problems.extend(compare_plugin_model_real(
            model_plugin_real.read_text(encoding="utf-8-sig"), model_plugin_real.name))
    else:
        skipped.append(f"{model_plugin_real.name} 不存在（插件未配置）")
    return problems, skipped


def main() -> int:
    problems, skipped = check_files()
    for note in skipped:
        print(f"[SKIP] {note}")
    if problems:
        print("配置漂移：")
        for problem in problems:
            print(f"  [FAIL] {problem}")
        return 1
    print("配置一致性检查通过（真实配置文件 ⊆ schema）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
