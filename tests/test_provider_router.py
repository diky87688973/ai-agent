# -*- coding: utf-8 -*-
"""模型路由测试：按 id 分发、默认回落、非权威兜底、未知 id 报错、热换默认实例。"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from agent.core.model_call import StreamDelta
from agent.mechanisms.provider_router import ProviderRouter
from agent.mechanisms.providers.base import ModelRequestError


class _FakeProvider:
    """只实现 `stream`；路由对外只承诺这一件事，fake 也不该被迫多实现。"""

    def __init__(self, name: str) -> None:
        self.name = name
        self.model = f"{name}-model"
        self.requests = []

    def stream(self, request):
        self.requests.append(request)
        yield StreamDelta(kind="text", text=self.name)


def _request(model=""):
    return SimpleNamespace(model=model)


def _drain(router: ProviderRouter, model: str):
    return [delta.text for delta in router.stream(_request(model))]


class RoutedStreamTest(unittest.TestCase):
    def setUp(self) -> None:
        self.default = _FakeProvider("default")
        self.alpha = _FakeProvider("alpha")
        self.beta = _FakeProvider("beta")
        self.table = {"alpha": self.alpha, "beta": self.beta}
        self.seen: list[str] = []

    def _router(self, **kwargs) -> ProviderRouter:
        def resolve(mid: str):
            self.seen.append(mid)
            return self.table.get(mid)

        return ProviderRouter(default=self.default, resolve=resolve,
                              default_id="alpha", **kwargs)

    def test_routes_to_the_requested_model(self) -> None:
        router = self._router(allowed_ids=("alpha", "beta"))
        self.assertEqual(_drain(router, "beta"), ["beta"])
        self.assertEqual(_drain(router, "alpha"), ["alpha"])
        self.assertEqual(self.seen, ["beta", "alpha"])

    def test_empty_model_falls_back_to_default_id_resolution(self) -> None:
        router = self._router()
        self.assertEqual(_drain(router, ""), ["alpha"],
                         msg="空模型走 default_id 的解析结果，而不是裸 default 实例")
        self.assertEqual(self.default.requests, [])
        self.assertEqual(self.seen, ["alpha"])

    def test_router_without_default_id_uses_default_instance(self) -> None:
        router = ProviderRouter(default=self.default, resolve=lambda _mid: None)
        self.assertEqual(_drain(router, ""), ["default"])
        self.assertEqual(self.seen, [])
        self.assertEqual(router.model, "default-model")

    def test_unknown_model_raises_instead_of_silently_using_default(self) -> None:
        router = self._router(allowed_ids=("alpha", "beta"))
        with self.assertRaises(ModelRequestError) as caught:
            _drain(router, "gamma")
        self.assertIn("gamma", str(caught.exception))
        self.assertEqual(self.default.requests, [],
                         msg="未配置的 id 不得回退到默认模型")

    def test_fallback_applies_only_to_allowed_ids(self) -> None:
        router = self._router(allowed_ids=("alpha", "beta"), fallback_to_default=True)
        self.assertEqual(_drain(router, "beta"), ["beta"], msg="目录命中优先于兜底")
        self.table.pop("beta")
        self.assertEqual(_drain(router, "beta"), ["default"],
                         msg="非权威模式下白名单内的 id 都由默认网关服务")
        with self.assertRaises(ModelRequestError):
            _drain(router, "outside")

    def test_fallback_is_off_by_default(self) -> None:
        router = self._router(allowed_ids=("alpha",))
        with self.assertRaises(ModelRequestError):
            _drain(router, "alpha2")

    def test_catalog_id_is_rewritten_to_the_provider_model_name(self) -> None:
        router = self._router()
        request = _request("beta")
        request.messages = ["m"]
        request.tools = ["t"]
        list(router.stream(request))
        got = self.beta.requests[0]
        self.assertEqual(got.model, "beta-model",
                         msg="id 是路由键，线格式模型名归 provider")
        self.assertIs(got.messages, request.messages)
        self.assertIs(got.tools, request.tools)
        self.assertEqual(request.model, "beta", msg="原请求对象不得被改写")

    def test_provider_without_model_name_gets_the_request_unchanged(self) -> None:
        silent = _FakeProvider("silent")
        silent.model = ""
        router = ProviderRouter(default=self.default, resolve=lambda _mid: silent)
        request = _request("whatever")
        list(router.stream(request))
        self.assertIs(silent.requests[0], request)

    def test_allowed_models_is_an_immutable_record(self) -> None:
        router = self._router(allowed_ids=["alpha", "beta", ""])
        self.assertEqual(router.allowed_models, ("alpha", "beta"))
        self.assertIsInstance(router.allowed_models, tuple)

    def test_model_property_prefers_default_id(self) -> None:
        router = self._router()
        self.assertEqual(router.model, "alpha")

    def test_reload_default_takes_effect_on_the_next_request(self) -> None:
        router = ProviderRouter(default=self.default, resolve=lambda _mid: None)
        replacement = _FakeProvider("replacement")
        router.reload_default(replacement)
        self.assertEqual(_drain(router, ""), ["replacement"],
                         msg="空模型且无 default_id 时必须用新默认实例")

    def test_reload_policy_updates_model_and_allowed_models(self) -> None:
        router = self._router()
        router.reload_policy(allowed_ids=("beta",), default_id="beta",
                             fallback_to_default=False)
        self.assertEqual(router.model, "beta")
        self.assertEqual(router.allowed_models, ("beta",))

    def test_reload_policy_can_disable_fallback(self) -> None:
        router = self._router(allowed_ids=("alpha", "beta"), fallback_to_default=True)
        self.table.pop("beta")
        router.reload_policy(allowed_ids=("alpha", "beta"), default_id="alpha",
                             fallback_to_default=False)
        with self.assertRaises(ModelRequestError):
            _drain(router, "beta")

    def test_reload_default_is_visible_through_default_provider(self) -> None:
        router = self._router()
        replacement = _FakeProvider("replacement")
        router.reload_default(replacement)
        self.assertIs(router.default_provider, replacement)
        self.assertEqual(_drain(router, "beta"), ["beta"],
                         msg="换默认实例不得影响目录解析出的模型")


if __name__ == "__main__":
    unittest.main()
