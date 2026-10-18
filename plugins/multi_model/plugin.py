# -*- coding: utf-8 -*-
"""多模型插件：把每条模型的网关与厂商声明交给内核的模型目录。

配置在本插件目录下的 `plugin-config.ini`：`[base]` 是身份与开关，
`[model:<id>]` 每条模型一节。插件**只声明**（id / 厂商 / 选项 / 标签），
不构造 provider、不接触路由 —— 厂商分发在 `provider_registry` 里，
请求路由在 `provider_router` 里，模型目录负责给每个条目缓存实例。

`register(ctx)` 贡献模型目录回调、只读 `/catalog` 端点与开屏下拉脚本；
卸载时三者的 disposer 一起回收（`ctx` 已记账）。解析纪律：任一条目坏掉
只影响它自己；每条诊断都带文件路径与节名，只说"配置有误"等于没留痕。
"""
from __future__ import annotations

import configparser
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from agent.capabilities.model_catalog import ModelEntry
from agent.capabilities.plugins import plugin_config_fields
from agent.mechanisms.provider_registry import known_kinds

CONFIG_FILE = "plugin-config.ini"
SECTION_PREFIX = "model:"
DEFAULT_PROVIDER = "openai"
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}
#: 最近一次打印过的诊断（按文件签名去重）：目录每次请求都重读配置。
_LAST_DIAG: Dict[str, Tuple[str, ...]] = {}


def _config_path() -> Path:
    """本插件的配置文件：`plugins/multi_model/plugin-config.ini`。"""
    return Path(__file__).resolve().parent / CONFIG_FILE


def _clean(value: object) -> str:
    """去空白与包裹引号（容忍 ini 值带单/双引号）。"""
    return str(value or "").strip().strip("'\"")


def _section_id(section: str) -> str:
    return section[len(SECTION_PREFIX):].strip()


def _diag(path: Path, section: str, key: str, reason: str) -> str:
    """一条可定位的诊断：文件 → 节 → 键 → 原因。"""
    label = f"[{section}] " if section else ""
    return f"[plugin:multi_model] {path} {label}{key + ' ' if key else ''}无效：{reason}"


def _emit(lines: Sequence[str], path: Path) -> None:
    """诊断按文件签名去重后写 stderr；配置没再变化就不重复刷。"""
    signature = tuple(lines)
    if not signature:
        _LAST_DIAG.pop(str(path), None)
        return
    if _LAST_DIAG.get(str(path)) == signature:
        return
    _LAST_DIAG[str(path)] = signature
    for line in signature:
        print(line, file=sys.stderr, flush=True)

def _as_bool(raw: str, path: Path, section: str, key: str,
             lines: List[str]) -> Optional[bool]:
    """严格布尔解析：空值返回 None，未知写法留诊断并返回 None。"""
    text = _clean(raw).lower()
    if not text:
        return None
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    lines.append(_diag(path, section, key, f"应为 0/1，实际为 {raw!r}"))
    return None


def _positive_int(raw: str, path: Path, section: str, key: str,
                  lines: List[str]) -> Optional[int]:
    """严格正整数解析；坏值留诊断并让条目无效。"""
    text = _clean(raw)
    if not text:
        return None
    try:
        value = int(text)
    except (TypeError, ValueError):
        value = 0
    if value <= 0:
        lines.append(_diag(path, section, key, f"应为正整数，实际为 {raw!r}"))
        return None
    return value


def _parse_entry(path: Path, section: str, parser: configparser.ConfigParser,
                 lines: List[str]) -> Optional[ModelEntry]:
    """解析单个 `[model:<id>]`；坏条目返回 None 并追加诊断。"""
    model_id = _section_id(section)
    if not model_id:
        lines.append(_diag(path, section, "", "模型 id 为空"))
        return None

    def get(key: str) -> str:
        return _clean(parser.get(section, key, fallback=""))

    provider = (get("provider") or DEFAULT_PROVIDER).lower()
    if provider not in known_kinds():
        lines.append(_diag(
            path, section, "provider",
            f"未知厂商 {provider!r}（可用：{', '.join(known_kinds())}）",
        ))
        return None
    base_url = get("base_url")
    if not base_url:
        lines.append(_diag(path, section, "base_url", "缺少网关地址"))
        return None
    api_key = get("api_key")
    if not api_key:
        lines.append(_diag(path, section, "api_key", "缺少密钥"))
        return None

    options: Dict[str, Any] = {
        "base_url": base_url,
        "api_key": api_key,
        "model": get("model") or model_id,
    }
    if provider == "anthropic":
        # 这些键只对 Anthropic 有意义；写在 openai 条目上就忽略，避免把
        # 不属于该厂商的参数塞进构造器。
        max_tokens = _positive_int(get("max_tokens"), path, section, "max_tokens", lines)
        if _clean(get("max_tokens")) and max_tokens is None:
            return None
        thinking_raw = get("thinking")
        thinking = _as_bool(thinking_raw, path, section, "thinking", lines)
        if thinking_raw and thinking is None:
            return None
        budget = _positive_int(
            get("thinking_budget_tokens"), path, section, "thinking_budget_tokens", lines)
        if _clean(get("thinking_budget_tokens")) and budget is None:
            return None
        if max_tokens is not None:
            options["max_tokens"] = max_tokens
        if thinking is not None:
            options["thinking"] = thinking
        if budget is not None:
            options["thinking_budget_tokens"] = budget

    default_raw = get("default")
    is_default = False
    if default_raw:
        parsed = _as_bool(default_raw, path, section, "default", lines)
        if parsed is None:
            # `default` 写坏不影响这条模型能不能用；按非默认处理并留痕。
            parsed = False
        is_default = parsed
    return ModelEntry.from_options(
        id=model_id,
        provider=provider,
        label=get("label") or model_id,
        options=options,
        is_default=is_default,
    )


def parse_config(path: Optional[Path] = None) -> Tuple[Tuple[ModelEntry, ...], Tuple[Dict[str, str], ...]]:
    """读配置并返回 `(有效条目, 坏条目)`。

    - 文件不存在是正常状态（插件启用但还没配置）：返回空表，不刷诊断；
    - 整个文件读不了：坏条目里给一条 `id=""`，路径仍可定位；
    - 单节解析失败只丢该节，其余照常；
    - `default = 1` 至多一个：第一个生效，后面的留痕并按非默认处理。
    """
    target = Path(path) if path is not None else _config_path()
    parser = configparser.ConfigParser(interpolation=None)
    if not target.is_file():
        return (), ()
    try:
        # 必须 `utf-8-sig`：Windows 记事本保存 UTF-8 会带 BOM，用 utf-8 读
        # 只会得到一句指不到根因的 MissingSectionHeaderError。
        parser.read(str(target), encoding="utf-8-sig")
    except (OSError, configparser.Error) as exc:
        lines = [_diag(target, "", "", f"{type(exc).__name__}: {exc}")]
        _emit(lines, target)
        return (), ({"id": "", "reason": lines[0]},)

    lines: List[str] = []
    entries: List[ModelEntry] = []
    invalid: List[Dict[str, str]] = []
    chosen_default = ""
    for section in parser.sections():
        if not section.startswith(SECTION_PREFIX):
            continue
        item = _parse_entry(target, section, parser, lines)
        if item is None:
            reason = lines[-1] if lines else "条目无效"
            invalid.append({"id": _section_id(section), "reason": reason})
            continue
        if item.is_default and chosen_default:
            lines.append(_diag(
                target, section, "default",
                f"已由 [model:{chosen_default}] 声明默认，本条按非默认处理",
            ))
            item = replace(item, is_default=False)
        elif item.is_default:
            chosen_default = item.id
        entries.append(item)

    if entries and not chosen_default:
        # 没有显式 default：目录按第一条兜底，这里把标记补齐，两处 default 才一致。
        entries[0] = replace(entries[0], is_default=True)
    _emit(lines, target)
    return tuple(entries), tuple(invalid)


def _catalog_payload(path: Optional[Path] = None) -> Dict[str, Any]:
    """给 `/catalog` 的响应：有效条目 + 默认 + 坏条目；不含任何凭据。"""
    entries, invalid = parse_config(path)
    default_id = next((item.id for item in entries if item.is_default), "")
    return {
        "ok": True,
        "models": [
            {"id": item.id, "label": item.label, "provider": item.provider,
             "default": bool(item.is_default)}
            for item in entries
        ],
        "default": default_id,
        "invalid": list(invalid),
    }


def register(ctx: Any) -> List[Callable[[], None]]:
    """插件入口：目录来源 + 只读目录端点 + 开屏下拉脚本。"""
    path = _config_path()
    # 启动时解析一次：坏配置在日志里留痕，而不是等用户点开下拉才发现。
    parse_config(path)

    def _catalog(_query: Dict[str, Any]) -> Any:
        return 200, _catalog_payload(path)

    base = plugin_config_fields(path.parent)
    if not base["name"] and path.is_file():
        # 身份只影响设置页展示，不阻断装载；没有配置文件时不算错误。
        print(f"[plugin:multi_model] {path.parent} [base] name 缺失", file=sys.stderr)

    return [
        ctx.add_model_catalog(lambda: parse_config(path)[0]),
        ctx.add_route("GET", "catalog", _catalog),
        ctx.add_boot_script("ui/model-picker.js"),
    ]
