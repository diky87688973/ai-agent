# -*- coding: utf-8 -*-
"""配置读取：项目根 config.ini（按需取用，未使用的项留空）。

本模块只认内核设置；插件设置在插件自己目录的 plugin-config.ini 里，由插件自己读。
"""
from __future__ import annotations

import configparser
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from agent.core.host import MAX_PASSES_DEFAULT

PROJECT_ROOT = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent.parent
)
APP_HOME = PROJECT_ROOT
DEFAULT_CONFIG_PATH = APP_HOME / "config.ini"
#: 模型上下文窗口缺省值（token）。未声明时为 0，压缩阈值改用回退值。
DEFAULT_CONTEXT_WINDOW = 0
#: 模型未声明窗口时的压缩阈值（token）。
DEFAULT_SUMMARY_TOKEN_FALLBACK = 64000
#: 模型压缩百分比的默认值与允许范围。
DEFAULT_COMPRESSION_PERCENT = 70
MIN_COMPRESSION_PERCENT = 10
MAX_COMPRESSION_PERCENT = 90


def _coerce_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
            return int(raw)
    return default


def compression_threshold(window: int, percent: int = DEFAULT_COMPRESSION_PERCENT,
                          fallback: int = DEFAULT_SUMMARY_TOKEN_FALLBACK) -> int:
    """按模型窗口计算压缩触发阈值；窗口不可用时回退绝对 token。"""
    win = max(0, _coerce_int(window, 0))
    if win <= 0:
        return max(1, _coerce_int(fallback, DEFAULT_SUMMARY_TOKEN_FALLBACK))
    pct = _coerce_int(percent, DEFAULT_COMPRESSION_PERCENT)
    if pct < MIN_COMPRESSION_PERCENT or pct > MAX_COMPRESSION_PERCENT:
        pct = DEFAULT_COMPRESSION_PERCENT
    return max(1, min(win, int(win * pct / 100)))


def _clean(value: object) -> str:
    """去空白与包裹引号（容忍 ini 值带单/双引号）。"""
    return str(value or "").strip().strip("'\"")


def load_ini(path: Optional[Path] = None) -> configparser.ConfigParser:
    """读取 config.ini；文件缺失返回空配置（不抛错）。

    ## 编码取 `utf-8-sig`

    配置文件由用户手工编辑，Windows 记事本另存默认会写 UTF-8 BOM（`\\ufeff`）。
    用 `utf-8` 读时，BOM 会粘在第一个节名上 → `configparser` 抛
    `MissingSectionHeaderError: File contains no section headers`，
    服务直接起不来，而错误信息完全指不到"配置被加了 BOM"。

    `utf-8-sig` 会吞掉可选的 BOM，对无 BOM 文件行为完全一致 —— 两种都能读。
    """
    parser = configparser.ConfigParser()
    target = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if target.is_file():
        parser.read(str(target), encoding="utf-8-sig")
    return parser


#: 思维链回传预算默认值（token）：超出取两头，中间省略。
DEFAULT_REASONING_REPLAY_TOKENS = 8000


def get_update(path: Optional[Path] = None) -> Dict[str, int]:
    """读取 [update] 节；检查间隔按 1..1440 分钟截断，缺省 30。"""
    parser = load_ini(path)
    values: Dict[str, str] = {}
    if parser.has_section("update"):
        values = {k: _clean(v) for k, v in parser.items("update")}
    try:
        interval = int(values.get("check_interval_minutes") or 30)
    except (TypeError, ValueError):
        interval = 30
    return {"check_interval_minutes": max(1, min(interval, 1440))}


def get_context(path: Optional[Path] = None) -> Dict[str, Any]:
    """读取 [context] 节：上下文预算保护参数；缺失或坏值一律回默认。"""
    parser = load_ini(path)
    values: Dict[str, str] = {}
    if parser.has_section("context"):
        values = {k: _clean(v) for k, v in parser.items("context")}

    def _int(name: str, default: int) -> int:
        try:
            return int(values.get(name) or default)
        except (TypeError, ValueError):
            return default

    return {
        "summary_token_fallback": _int("summary_token_fallback", 64000),
        # 压缩时遮盖的末尾用户轮数（压不出空间时连它们一起压）。
        "full_user_rounds": _int("full_user_rounds", 5),
        "summary_output_max_chars": _int("summary_output_max_chars", 5000),
        # 只把最近这么多轮带图的用户发言里的图带进请求（负数 = 不限）。
        # 缺省 1 轮 / 8 张：截图工具很占字节，历史全带会先撞上游请求体上限。
        # 这两项由装配根取走交给模型模块，不进 `ContextPipeline` 的构造参数。
        "image_turns": _int("image_turns", 1),
        "image_max": _int("image_max", 8),
        # 思维链回传预算（token）：-1 = 全量回传，0 = 不回传，
        # 正数 = 超出就取两头、中间以省略标记代替（模型按前后文推断）。
        # 思维链必然未命中缓存，全量回传等于每轮多背几万 token。
        "reasoning_replay_tokens": _int("reasoning_replay_tokens", DEFAULT_REASONING_REPLAY_TOKENS),
    }


#: 插件清单文件（工程根）。节在就进入装载候选；开关在插件自己的 plugin-config.ini。
DEFAULT_PLUGINS_PATH = APP_HOME / "plugins.ini"

#: 插件清单的节名前缀：`[plugin:名字]`。
PLUGIN_SECTION_PREFIX = "plugin:"


def _plugin_entries(parser, *, defaults: bool) -> List[Dict[str, str]]:
    """把清单节读成条目；overlay 只保留显式字段，避免覆盖基底 path。"""
    out: List[Dict[str, str]] = []
    for section in parser.sections():
        if not section.startswith(PLUGIN_SECTION_PREFIX):
            continue
        name = section[len(PLUGIN_SECTION_PREFIX):].strip()
        entry = {"name": name}
        if defaults or parser.has_option(section, "path"):
            entry["path"] = str(parser.get(section, "path", fallback="") or "").strip()
        if defaults or parser.has_option(section, "enabled"):
            entry["enabled"] = str(parser.get(section, "enabled", fallback="1") or "1").strip()
        out.append(entry)
    return out


def get_plugins(path: Optional[Path] = None) -> List[Dict[str, str]]:
    """读取插件清单，返回 `[{name, path, enabled}, ...]`。

    每个插件一个节 `[plugin:<名字>]`。节在就进入装载候选。
    开或关写在清单节：`enabled = 1` 装载，`0` 不装载；缺省按 1。
    `path` 留空时本函数不填，由装载方按插件根解析。插件版本只在 `plugin-meta.json` 声明。
    名字非法、目录不存在归装载方判断。

    带 `[profile] base = <清单>` 的文件是覆盖层：先读基底，再按插件名覆盖显式字段；
    未出现在覆盖层的插件继承基底。覆盖层只适合模式差异，不复制完整清单。
    """
    target = Path(path if path is not None else DEFAULT_PLUGINS_PATH)
    parser = load_ini(target)
    base_raw = ""
    if parser.has_section("profile"):
        base_raw = str(parser.get("profile", "base", fallback="") or "").strip()
    if not base_raw:
        return _plugin_entries(parser, defaults=True)

    base = Path(base_raw)
    if not base.is_absolute():
        base = target.parent / base
    base = base.resolve()
    if base == target.resolve():
        raise ValueError(f"插件 profile 不能引用自身: {target}")
    if not base.is_file():
        raise ValueError(f"插件 profile 基底不存在: {base}")
    merged = get_plugins(base)
    by_name = {item["name"]: item for item in merged}
    for item in _plugin_entries(parser, defaults=False):
        name = item["name"]
        if name in by_name:
            by_name[name].update(item)
        else:
            by_name[name] = {"path": "", "enabled": "1", **item}
    return [by_name[item["name"]] for item in merged] + [
        item for name, item in by_name.items() if name not in {x["name"] for x in merged}
    ]


#: 推理档位的合法取值与默认值。
REASONING_EFFORTS = ("high", "max")
DEFAULT_REASONING_EFFORT = "max"


def get_reasoning_effort(path: Optional[Path] = None) -> str:
    """读取全局推理档位（`[agent] reasoning_effort`）：`high` 或 `max`。

    取不到或值非法时回落 `DEFAULT_REASONING_EFFORT`。会话级选择会覆盖它。
    """
    parser = load_ini(path)
    raw = ""
    if parser.has_section("agent"):
        raw = _clean(parser.get("agent", "reasoning_effort", fallback="")).lower()
    return raw if raw in REASONING_EFFORTS else DEFAULT_REASONING_EFFORT


#: 版本化备份的默认保留天数（启动时清理更早的）。
DEFAULT_BACKUP_RETENTION_DAYS = 7


def get_backup_retention_days(path: Optional[Path] = None) -> int:
    """读取版本化备份的保留天数（`[agent] backup_retention_days`）。

    取不到或值非法时回落 `DEFAULT_BACKUP_RETENTION_DAYS`。
    小于 0 视为 0（即不清理）；0 表示永久保留。
    """
    parser = load_ini(path)
    raw = ""
    if parser.has_section("agent"):
        raw = _clean(parser.get("agent", "backup_retention_days", fallback=""))
    try:
        return max(0, int(raw)) if raw else DEFAULT_BACKUP_RETENTION_DAYS
    except (TypeError, ValueError):
        return DEFAULT_BACKUP_RETENTION_DAYS


#: 一个回合最多跑多少趟（模型往返）的默认值。
#: 权威值在内核的 `MAX_PASSES_DEFAULT`，这里只做转出，避免同一个数写两遍。
#: 一趟 = 模型说一次话（可带多个工具调用）+ 这些工具全部执行完。
#: 超过说明有模块永远要求续行，或这轮任务确实很长（GUI 自动化常见）。
DEFAULT_MAX_PASSES = MAX_PASSES_DEFAULT


def get_max_passes(path: Optional[Path] = None) -> int:
    """读取一回合的趟数上限（`[agent] max_passes`）。

    取不到或值非法时回落 `DEFAULT_MAX_PASSES`。小于 1 视为 1
    —— 0 或负数会让回合一开始就撞上限，那不是"更严格"而是"跑不起来"。
    """
    parser = load_ini(path)
    raw = ""
    if parser.has_section("agent"):
        raw = _clean(parser.get("agent", "max_passes", fallback=""))
    try:
        return max(1, int(raw)) if raw else DEFAULT_MAX_PASSES
    except (TypeError, ValueError):
        return DEFAULT_MAX_PASSES


def is_frozen() -> bool:
    """当前是否运行在 PyInstaller 等冻结程序中。"""
    return bool(getattr(sys, "frozen", False))


def prepare_user_home() -> Path:
    """冻结的 onedir 程序使用安装目录作为可写应用根。"""
    global APP_HOME, DEFAULT_CONFIG_PATH, DEFAULT_PLUGINS_PATH
    APP_HOME = PROJECT_ROOT
    DEFAULT_CONFIG_PATH = APP_HOME / "config.ini"
    DEFAULT_PLUGINS_PATH = APP_HOME / "plugins.ini"
    return APP_HOME


def default_plugins_root() -> Path:
    """插件根：冻结程序使用用户目录中的可写副本。"""
    return APP_HOME / "plugins"


def user_data_root() -> Path:
    """冻结程序的用户数据目录（不写安装目录）。"""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "ai-agent"


def default_data_root():
    """默认数据根：`AI_AGENT_DATA_ROOT` 优先。

    源码运行落到 `PROJECT_ROOT/data`；冻结程序落到用户数据目录，
    避免写入只读安装目录或 PyInstaller 临时解包目录。
    """
    env_root = os.environ.get("AI_AGENT_DATA_ROOT", "").strip()
    if env_root:
        return Path(env_root)
    if is_frozen():
        return user_data_root()
    return PROJECT_ROOT / "data"


def get_plugin_tree_only(path: Optional[Path] = None) -> bool:
    """是否只允许从 `plugins/` 树内装载插件（`[agent] plugin_tree_only`）。

    环境变量 `AI_AGENT_PLUGIN_TREE_ONLY` 优先：`1`/`true`/`on` 开，`0`/`false`/`off` 关。
    未设环境变量时读配置；缺省关闭（兼容清单里的绝对/外置 path）。
    """
    import os

    env = os.environ.get("AI_AGENT_PLUGIN_TREE_ONLY", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if env in ("0", "false", "no", "off"):
        return False
    parser = load_ini(path)
    raw = ""
    if parser.has_section("agent"):
        raw = _clean(parser.get("agent", "plugin_tree_only", fallback=""))
    return raw.lower() in ("1", "true", "yes", "on")
