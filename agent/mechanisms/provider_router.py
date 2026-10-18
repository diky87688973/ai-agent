# -*- coding: utf-8 -*-
"""模型路由：把 `request.model` 解析成一个 provider 实例。

它是 `ModelProvider` 的唯一外壳：内核只看见"一个提供者"，路由内部才有多厂商。
三条硬约束：

1. 不静默回退：未配置的 id 直接抛 `ModelRequestError`。悄悄换个模型回答，
   用户会以为自己在问 A，实际答的是 B —— 这比报错更难发现。
2. 不认识厂商名：厂商分发在 `provider_registry`，路由只拿注入的 `resolve` 回调。
   在这里写 `if kind == "anthropic"` 就等于把扩展点挪回了路由。
3. 默认实例可热替换：设置页保存后调 `reload_default()`；换实例必须进锁，
   否则并发请求可能拿到构造到一半的对象。
"""
from __future__ import annotations

import copy
import dataclasses
import threading
from typing import Callable, Iterator, Optional, Sequence, Tuple

from agent.core.model_call import StreamDelta
from agent.mechanisms.model_provider import ModelProvider, ModelRequestError


class ProviderRouter(ModelProvider):
    """按请求里的模型 id 分发；`resolve` 由装配根接到模型目录。"""

    def __init__(
        self,
        *,
        default: ModelProvider,
        resolve: Callable[[str], Optional[ModelProvider]],
        allowed_ids: Sequence[str] = (),
        default_id: str = "",
        fallback_to_default: bool = False,
    ) -> None:
        self._lock = threading.Lock()
        self._default = default
        self._resolve = resolve
        self._allowed = tuple(str(item) for item in allowed_ids if str(item))
        self._default_id = str(default_id or "")
        self._fallback = bool(fallback_to_default)

    # ── 只读视图 ──

    @property
    def model(self) -> str:
        """当前默认模型名；日志、`ModelPort.name()` 用它，不参与路由判定。"""
        with self._lock:
            if self._default_id:
                return self._default_id
            return str(getattr(self._default, "model", "") or "")

    @property
    def allowed_models(self) -> Tuple[str, ...]:
        """可供界面展示的 id；权威来源变化时由装配根重新注入新策略。"""
        with self._lock:
            return self._allowed

    @property
    def default_provider(self) -> ModelProvider:
        with self._lock:
            return self._default

    def reload_policy(
        self,
        *,
        allowed_ids: Sequence[str],
        default_id: str,
        fallback_to_default: bool,
    ) -> None:
        """装配末尾按权威来源刷新路由策略（目录 load 完成前算不出清单）。"""
        with self._lock:
            self._allowed = tuple(str(item) for item in allowed_ids if str(item))
            self._default_id = str(default_id or "")
            self._fallback = bool(fallback_to_default)

    # ── 热更新 ──

    def reload_default(self, provider: ModelProvider) -> None:
        """替换默认实例（设置页保存后调用）；这是唯一允许改 default 的入口。"""
        with self._lock:
            self._default = provider

    # ── 路由 ──

    def stream(self, request) -> Iterator[StreamDelta]:
        with self._lock:
            default_id = self._default_id
            allowed = self._allowed
            fallback = self._fallback
        mid = str(getattr(request, "model", "") or "").strip() or default_id
        if not mid:
            yield from self._default_snapshot().stream(request)
            return
        provider = self._resolve(mid)
        if provider is not None:
            # 目录条目的 id 是路由键，线格式模型名归 provider 自己（`options.model`）。
            # 两者可能不同（`[model:claude]` + `model = claude-sonnet-4-5`），
            # 因此命中目录时必须把请求里的 id 换成实例的模型名。
            yield from provider.stream(_with_wire_model(request, provider))
            return
        if fallback and mid in allowed:
            # 非权威模式：config.ini 里的 models 都由同一个网关服务。
            yield from self._default_snapshot().stream(request)
            return
        raise ModelRequestError(f"未配置的模型：{mid}")

    def _default_snapshot(self) -> ModelProvider:
        with self._lock:
            return self._default


def _with_wire_model(request, provider: ModelProvider):
    """把请求里的目录 id 换成 provider 的线格式模型名；换不了就原样返回。"""
    wire = str(getattr(provider, "model", "") or "").strip()
    current = str(getattr(request, "model", "") or "").strip()
    if not wire or wire == current:
        return request
    if dataclasses.is_dataclass(request) and not isinstance(request, type):
        try:
            return dataclasses.replace(request, model=wire)
        except TypeError:
            # 不可变/自定义请求对象不支持 replace：下面退回浅拷贝。
            pass
    try:
        clone = copy.copy(request)
        clone.model = wire
        return clone
    except Exception:
        # 请求对象不可复制：宁可让 provider 自己决定，也不要因为适配层限制打断请求。
        return request
