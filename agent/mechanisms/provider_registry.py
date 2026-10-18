# -*- coding: utf-8 -*-
"""模型提供者注册表：厂商名 → 构造器。

唯一知道"怎么 new 一个 provider"的地方。目录只存厂商名与选项字典，
路由只按 id 取实例，插件只声明配置 —— 三者都不 import 具体适配器。

扩展方式（`A4`：扩展只加文件）：

1. 新增一个适配器文件（实现 `stream()`）；
2. 在本文件的映射里加一行。

不改路由、不改目录、不改插件。选项键由各构造器自己解释，注册表只做分发与
键过滤：配置文件里多写一个键不该让构造器因 `unexpected keyword` 直接炸。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, Tuple

from agent.mechanisms.anthropic_provider import AnthropicProvider
from agent.mechanisms.model_provider import ModelProvider, OpenAICompatibleProvider

#: 各厂商接受的构造参数。白名单而不是透传：配置文件是外部输入，
#: 多一个键就让构造器抛 TypeError 属于"配置笔误升级成启动失败"。
_OPTIONS: Dict[str, Tuple[str, ...]] = {
    "openai": (
        "base_url", "api_key", "model", "timeout",
        "replay_history_reasoning", "extra_headers",
    ),
    "anthropic": (
        "base_url", "api_key", "model", "max_tokens", "thinking",
        "thinking_budget_tokens", "anthropic_version", "timeout", "extra_headers",
    ),
}


def _pick(options: Mapping[str, Any], allowed: Tuple[str, ...]) -> Dict[str, Any]:
    """按白名单取选项；值为 None 的键丢掉（让构造器用自己的默认）。"""
    return {
        key: options[key]
        for key in allowed
        if key in options and options[key] is not None
    }


def _build_openai(options: Mapping[str, Any]) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(**_pick(options, _OPTIONS["openai"]))


def _build_anthropic(options: Mapping[str, Any]) -> AnthropicProvider:
    return AnthropicProvider(**_pick(options, _OPTIONS["anthropic"]))


_BUILDERS: Dict[str, Callable[[Mapping[str, Any]], ModelProvider]] = {
    "openai": _build_openai,
    "anthropic": _build_anthropic,
}


def known_kinds() -> Tuple[str, ...]:
    """已注册的厂商名（排序固定，便于配置校验与诊断输出）。"""
    return tuple(sorted(_BUILDERS))


def build_provider(kind: str, options: Mapping[str, Any]) -> ModelProvider:
    """按厂商名构造 provider；未知厂商抛 `ValueError(kind)`。

    调用方决定未知厂商的后果：目录在快照期跳过该条目并留痕，启动装配则直接失败。
    """
    key = str(kind or "").strip().lower()
    builder = _BUILDERS.get(key)
    if builder is None:
        raise ValueError(key)
    return builder(dict(options or {}))
