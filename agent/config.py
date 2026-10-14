# -*- coding: utf-8 -*-
"""配置读取：项目根 config.ini（按需取用，未使用的项留空）。

[model_reasoning] 节字段：api_base_url / api_key / model（model 可缺省，取 DEFAULT_MODEL）。
读取策略：文件缺失或节缺失 → 空值/缺省返回（调用方决定报错策略）。
本模块只认内核设置；插件设置在插件自己目录的 plugin-config.ini 里，由插件自己读。
"""
from __future__ import annotations

import configparser
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.ini"
DEFAULT_MODEL = "deepseek-v4-flash-vision-exp"


def _clean(value: object) -> str:
    """去空白与包裹引号（容忍 ini 值带单/双引号）。"""
    return str(value or "").strip().strip("'\"")


def load_ini(path: Optional[Path] = None) -> configparser.ConfigParser:
    """读取 config.ini；文件缺失返回空配置（不抛错）。

    ## 编码取 `utf-8-sig`

    配置文件由用户手工编辑，**Windows 记事本另存默认会写 UTF-8 BOM**（`\\ufeff`）。
    用 `utf-8` 读时，BOM 会粘在第一个节名上 → `configparser` 抛
    `MissingSectionHeaderError: File contains no section headers`，
    **服务直接起不来**，而错误信息完全指不到"配置被加了 BOM"。

    `utf-8-sig` 会**吞掉可选的 BOM**，对无 BOM 文件行为完全一致 —— 两种都能读。
    """
    parser = configparser.ConfigParser()
    target = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if target.is_file():
        parser.read(str(target), encoding="utf-8-sig")
    return parser


def get_model_reasoning(path: Optional[Path] = None) -> Dict[str, Any]:
    """读取 [model_reasoning] 节。

    返回 `{api_base_url, api_key, model, models}`：
    前两个缺失为空串，`model` 缺省取 DEFAULT_MODEL，
    `models` 是同一网关下的可选模型名（逗号分隔；留空 = 只能用 `model`）。
    """
    parser = load_ini(path)
    values: Dict[str, str] = {}
    if parser.has_section("model_reasoning"):
        values = {k: _clean(v) for k, v in parser.items("model_reasoning")}
    raw_models = str(values.get("models") or "")
    models = [x.strip() for x in raw_models.split(",") if x.strip()]
    return {
        "api_base_url": values.get("api_base_url") or "",
        "api_key": values.get("api_key") or "",
        "model": values.get("model") or DEFAULT_MODEL,
        "models": models,
    }


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
        "summary_token_threshold": _int("summary_token_threshold", 700000),
        # 压缩时遮盖的末尾用户轮数（压不出空间时连它们一起压）。
        "full_user_rounds": _int("full_user_rounds", 1),
        "summary_output_max_chars": _int("summary_output_max_chars", 5000),
        # 只把最近这么多轮用户发言里的图带进请求（负数 = 不限）。
        # 这两项由装配根取走交给模型模块，不进 `ContextPipeline` 的构造参数。
        "image_turns": _int("image_turns", 3),
        "image_max": _int("image_max", 10),
        # 摘要那一次调用复用平常请求的前缀（吃 KV 缓存）。.ini 无布尔类型，1/0 表示。
        "summary_prefix_reuse": _int("summary_prefix_reuse", 1) != 0,
        # 已结束轮次的思维链是否回传。默认 0：思维链是模型的中间产物，
        # 回传等于每轮都往输入里多塞几万 token，而这段必然未命中缓存（按未命中计费）。
        "replay_history_reasoning": _int("replay_history_reasoning", 0) != 0,
    }


#: 插件清单文件（工程根）。列出要装载的插件，未列出的不加载。
DEFAULT_PLUGINS_PATH = PROJECT_ROOT / "plugins.ini"

#: 插件清单的节名前缀：`[plugin:名字]`。
PLUGIN_SECTION_PREFIX = "plugin:"


def get_plugins(path: Optional[Path] = None) -> List[Dict[str, str]]:
    """读取插件清单 `plugins.ini`，返回 `[{name, version, path}, ...]`。

    每个插件一个节，节名是 `[plugin:<名字>]`：

    ```ini
    [plugin:knowledge]
    version = 1.0
    path    = D:/lab/knowledge

    [plugin:tts]
    ```
    节里没有字段也合法 —— 名字即默认目录名，其余可为空。

    **列在文件里就是装载**，没有单独的开关键：`.ini` 里没有布尔值这种类型，
    再塞一个 `enabled = true` 只是把同一件事写两遍。

    `path` 留空时本函数不填，由装载方按自己的插件根解析。
    名字非法、目录不存在这类判断也不在这里做：本函数只负责解析，
    判断与报告归装载方，免得同一件事有两处口径。
    """
    parser = load_ini(path if path is not None else DEFAULT_PLUGINS_PATH)
    out: List[Dict[str, str]] = []
    for section in parser.sections():
        if not section.startswith(PLUGIN_SECTION_PREFIX):
            continue
        name = section[len(PLUGIN_SECTION_PREFIX):].strip()
        out.append({
            "name": name,
            "version": str(parser.get(section, "version", fallback="") or "").strip(),
            "path": str(parser.get(section, "path", fallback="") or "").strip(),
        })
    return out


#: 用户规则文件的大小上限（字符）。超限只取前这么多，避免一份巨型文件顶爆系统提示。
USER_RULES_MAX_CHARS = 20000

#: 推理档位的合法取值与默认值。
REASONING_EFFORTS = ("high", "max")
DEFAULT_REASONING_EFFORT = "max"


def get_user_rules(path: Optional[Path] = None) -> str:
    """读取用户自定义规则文件，返回其正文；未配置或读不到时返回空串。

    取 `[agent]` 节的 `user_rules_file`：相对路径按 `PROJECT_ROOT` 解析，
    也可以给绝对路径。指向的文件不存在、不是文件或读失败都返回空串 ——
    规则是**增强项**，缺了不该让服务起不来。

    超长只取前 `USER_RULES_MAX_CHARS` 个字符并附一句截断说明：
    系统提示越长越贵，而一份失控的文件会把预算全吃掉。
    """
    parser = load_ini(path)
    raw = ""
    if parser.has_section("agent"):
        raw = _clean(parser.get("agent", "user_rules_file", fallback=""))
    if not raw:
        return ""
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    try:
        if not candidate.is_file():
            return ""
        text = candidate.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if len(text) > USER_RULES_MAX_CHARS:
        text = text[:USER_RULES_MAX_CHARS] + "\n\n（规则文件超出长度上限，已截断）"
    return text


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


def get_model_pricing(path: Optional[Path] = None) -> Dict[str, Any]:
    """读取 [model_pricing] 节：`rates` 覆盖内置官方费率表。

    `rates` 为 JSON 字符串或 JSON 文件路径；坏数据一律忽略（回落内置默认表）——
    计价是展示增强项，配置写错不该让服务起不来。
    """
    parser = load_ini(path)
    values: Dict[str, str] = {}
    if parser.has_section("model_pricing"):
        values = {k: _clean(v) for k, v in parser.items("model_pricing")}

    raw = values.get("rates") or ""
    if not raw:
        return {}
    # 先当文件路径试；不是文件就当内联 JSON
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    try:
        if candidate.is_file():
            raw = candidate.read_text(encoding="utf-8")
    except OSError:
        pass
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def default_data_root():
    """默认数据根：`AI_AGENT_DATA_ROOT` 优先，否则 `PROJECT_ROOT/data`。

    **默认数据根只能有这一个来源**：多一处自己拼接，落盘隔离口就漏一处
    （单测的文件会落进工程 `data/`）。

    这个环境变量**只给测试与 CI 用**：不设它时行为是 `PROJECT_ROOT/data`；
    CI (`scripts/ci.py`) 会把它指到临时目录，跑完工程目录保持干净。
    """
    import os

    env_root = os.environ.get("AI_AGENT_DATA_ROOT", "").strip()
    return Path(env_root) if env_root else PROJECT_ROOT / "data"
