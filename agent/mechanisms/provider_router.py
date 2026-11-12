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
from typing import Any, Callable, Iterator, Optional, Sequence, Tuple

from agent.core.app_path import app_path
from agent.core.error_report import report_error
from agent.core.model_call import StreamDelta
from agent.mechanisms.providers.base import ModelProvider, ModelRequestError

ROUTER_PATH = app_path("kernel", "modules", "model", "router")


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
        slots: Any = None,
    ) -> None:
        self._lock = threading.Lock()
        self._default = default
        self._resolve = resolve
        self._allowed = tuple(str(item) for item in allowed_ids if str(item))
        self._default_id = str(default_id or "")
        self._fallback = bool(fallback_to_default)
        self._slots = slots
        if self._slots is not None and ROUTER_PATH not in self._slots.nodes:
            self._slots.register_slot(
                ROUTER_PATH, kind="kernel-stage",
                default=self._select_provider, default_owner="__host__")

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

    def _route(self, request) -> tuple[str, Optional[ModelProvider]]:
        with self._lock:
            default_id = self._default_id
            allowed = self._allowed
            fallback = self._fallback
        mid = str(getattr(request, "model", "") or "").strip() or default_id
        return mid, self._select_for_request(request, mid, allowed, fallback)

    def requires_full_reasoning(self, request) -> bool:
        _, provider = self._route(request)
        check = getattr(provider, "requires_full_reasoning", None)
        return bool(check(_with_wire_model(request, provider))) if callable(check) else False

    def stream(self, request) -> Iterator[StreamDelta]:
        mid, provider = self._route(request)
        if provider is None:
            raise ModelRequestError(f"未配置的模型：{mid}")
        # 目录条目的 id 是路由键，线格式模型名归 provider 自己（`options.model`）。
        # 两者可能不同（`[model:claude]` + `model = claude-sonnet-4-5`），
        # 因此命中目录时必须把请求里的 id 换成实例的模型名。
        yield from provider.stream(_with_wire_model(request, provider))

    def _select_for_request(self, request, mid: str, allowed: Any,
                            fallback: bool) -> Optional[ModelProvider]:
        if self._slots is not None and ROUTER_PATH in self._slots.nodes:
            impl = self._slots.resolve(ROUTER_PATH)
            if impl is not self._select_provider:
                return impl(request, mid, allowed, fallback, self._resolve)
        return self._select_provider(request, mid, allowed, fallback, self._resolve)

    def _select_provider(self, request, mid: str, allowed: Any, fallback: bool,
                         resolve: Callable[[str], Optional[ModelProvider]]) -> Optional[ModelProvider]:
        if not mid:
            return self._default_snapshot()
        provider = resolve(mid)
        if provider is not None:
            return provider
        if fallback and mid in allowed:
            return self._default_snapshot()
        return None

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
        except TypeError as exc:
            # 不可变/自定义请求对象不支持 replace：下面退回浅拷贝。
            report_error("agent.mechanisms.provider_router._with_wire_model", exc)
    try:
        clone = copy.copy(request)
        clone.model = wire
        return clone
    except Exception as exc:
        # 请求对象不可复制：宁可让 provider 自己决定，也不要因为适配层限制打断请求。
        report_error("agent.mechanisms.provider_router._with_wire_model", exc)
        return request
