# -*- coding: utf-8 -*-
"""模型计价。

费率以「元 / 百万 tokens」计，三项：缓存命中输入、缓存未命中输入、输出。
从配置文件读取；不抓网页
（页面结构会变，静默抓失败比没有更糟）——所以内置一份**官方默认表**兜底。

官方表区分高峰 / 空闲时段（同一模型的空闲价是高峰价的一半）。为避免"同一份用量
算出两个数"，这里默认统一按**高峰价**给上界，并在返回里标明时段来源。
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

# 官方默认费率（元 / 百万 tokens）：
#   https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
# 键为模型名前缀（最长匹配优先），便于 `deepseek-v4-flash-vision-exp` 这类变体命中主表。
DEFAULT_RATES: Dict[str, Dict[str, float]] = {
    "deepseek-v4-pro": {
        "cache_hit_cny_per_m": 0.30,
        "cache_miss_cny_per_m": 9.0,
        "output_cny_per_m": 27.0,
    },
    "deepseek-v4-flash": {
        "cache_hit_cny_per_m": 0.04,
        "cache_miss_cny_per_m": 2.0,
        "output_cny_per_m": 8.0,
    },
    "deepseek-flash": {
        "cache_hit_cny_per_m": 0.04,
        "cache_miss_cny_per_m": 2.0,
        "output_cny_per_m": 8.0,
    },
}

# 空闲时段相对高峰的折扣（官方：空闲价 = 高峰价的一半）
IDLE_DISCOUNT = 0.5

_RATE_KEYS = ("cache_hit_cny_per_m", "cache_miss_cny_per_m", "output_cny_per_m")


def _valid_row(obj: Any) -> Optional[Dict[str, float]]:
    """一行费率必须三项齐全且为数字；缺项视为无效（宁可不给价，不给错价）。"""
    if not isinstance(obj, dict):
        return None
    out: Dict[str, float] = {}
    for key in _RATE_KEYS:
        if key not in obj:
            return None
        try:
            out[key] = float(obj[key])
        except (TypeError, ValueError):
            return None
    return out


def parse_rates(raw: Any) -> Dict[str, Dict[str, float]]:
    """解析配置里的费率 JSON（字符串或已解析对象）；坏数据一律忽略。"""
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            return {}
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict[str, float]] = {}
    for name, row in raw.items():
        if str(name).startswith("__"):
            continue        # `__default__` 之类的元键单独处理
        valid = _valid_row(row)
        if valid:
            out[str(name)] = valid
    return out


def lookup(model: str, table: Optional[Dict[str, Dict[str, float]]] = None) -> Optional[Dict[str, float]]:
    """按模型名查费率：精确命中 → 最长前缀命中 → `__default__` → None。

    前缀匹配是为了让 `deepseek-v4-flash-vision-exp` 这类带后缀的变体也能命中主表。
    """
    name = str(model or "").strip().lower()
    if not name:
        return None
    merged: Dict[str, Dict[str, float]] = dict(DEFAULT_RATES)
    merged.update(table or {})
    if name in merged:
        return dict(merged[name])
    best = ""
    for key in merged:
        key_lower = str(key).lower()
        if key_lower and name.startswith(key_lower) and len(key_lower) > len(best):
            best = key_lower
    if best:
        return dict(merged[best])
    default_row = _valid_row((table or {}).get("__default__"))
    return default_row


def estimate_cny(
    rates: Optional[Dict[str, float]],
    *,
    cache_hit_tokens: float = 0.0,
    cache_miss_tokens: float = 0.0,
    completion_tokens: float = 0.0,
) -> Optional[float]:
    """按费率估算费用（元）。无费率 → None（UI 据此显示"未查到计价信息"）。"""
    if not rates:
        return None
    hit = float(cache_hit_tokens or 0) / 1e6 * float(rates.get("cache_hit_cny_per_m") or 0)
    miss = float(cache_miss_tokens or 0) / 1e6 * float(rates.get("cache_miss_cny_per_m") or 0)
    out = float(completion_tokens or 0) / 1e6 * float(rates.get("output_cny_per_m") or 0)
    return hit + miss + out


def cost_label(cny: Optional[float], *, loading: bool = False) -> str:
    """费用文案。"""
    if loading:
        return "计价查询中…"
    if cny is None:
        return "未查到模型计价信息"
    return f"￥{cny:.2f}"


class ModelPricing:
    """计价查询门面：配置覆盖官方默认表；查不到就给 None（不编数）。"""

    def __init__(self, rates: Any = None) -> None:
        self._table = parse_rates(rates)

    @property
    def table(self) -> Dict[str, Dict[str, float]]:
        """生效费率表（配置覆盖后的并集）。"""
        merged: Dict[str, Dict[str, float]] = dict(DEFAULT_RATES)
        merged.update(self._table)
        return merged

    def rates_for(self, model: str) -> Optional[Dict[str, float]]:
        return lookup(model, self._table)

    def payload(self, model: str) -> Dict[str, Any]:
        """`GET /api/model-pricing` 的响应体。"""
        rates = self.rates_for(model)
        if rates is None:
            return {"ok": False, "model": str(model or ""), "error": "no rates"}
        return {
            "ok": True,
            "model": str(model or ""),
            "cache_hit_cny_per_m": rates["cache_hit_cny_per_m"],
            "cache_miss_cny_per_m": rates["cache_miss_cny_per_m"],
            "output_cny_per_m": rates["output_cny_per_m"],
            "source": "config" if str(model or "").lower() in self._table else "default",
        }
