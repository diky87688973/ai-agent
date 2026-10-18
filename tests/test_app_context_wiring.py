# -*- coding: utf-8 -*-
"""进程级上下文（AppContext）装配集成测试。

覆盖进程级服务登记、App 属性即上下文快捷方式（无双份状态）、进程停机释放。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.app import build_app  # noqa: E402
from agent.core.context import (  # noqa: E402
    SERVICE_COMPACTOR_FACTORY,
    SERVICE_CONTEXT_SOURCES,
    SERVICE_ERROR_LOG,
    SERVICE_EVENT_BUS,
    SERVICE_LIVE_STATE,
    SERVICE_MESH,
    SERVICE_PIPELINE,
    SERVICE_PLUGIN_HOST,
    SERVICE_PROVIDER,
    SERVICE_REGISTRY,
    SERVICE_SESSION_CONTEXTS,
    SERVICE_SESSION_FACTORY,
    SERVICE_STORE,
    AppContext,
)
from agent.shell.service_keys import SERVICE_RUNNER  # noqa: E402

REQUIRED_SERVICES = (
    SERVICE_REGISTRY,
    SERVICE_PIPELINE,
    SERVICE_PROVIDER,
    SERVICE_EVENT_BUS,
    SERVICE_PLUGIN_HOST,
    SERVICE_CONTEXT_SOURCES,
    SERVICE_LIVE_STATE,
    SERVICE_MESH,
    SERVICE_SESSION_CONTEXTS,
    SERVICE_ERROR_LOG,
    SERVICE_RUNNER,
)

# App 属性名 → 服务登记名的对照表
ATTR_TO_SERVICE = {
    "registry": SERVICE_REGISTRY,
    "pipeline": SERVICE_PIPELINE,
    "provider": SERVICE_PROVIDER,
    "event_bus": SERVICE_EVENT_BUS,
    "plugin_host": SERVICE_PLUGIN_HOST,
    "context_sources": SERVICE_CONTEXT_SOURCES,
    "live_state": SERVICE_LIVE_STATE,
    "mesh": SERVICE_MESH,
    "session_contexts": SERVICE_SESSION_CONTEXTS,
    "runner": SERVICE_RUNNER,
}

class _AppFixture(unittest.TestCase):
    """共用装配夹具：临时 data 根，避免写进工程 data/。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.app = build_app(
            backup_root=self.root / "bk",
            recycle_root=self.root / "rc",
        )

class ProcessServiceRegistryTest(_AppFixture):
    """进程级服务登记。"""

    def test_build_app_is_context_backed(self) -> None:

        self.assertIsInstance(self.app.context, AppContext)

    def test_all_required_services_registered(self) -> None:

        names = self.app.context.names()
        for name in REQUIRED_SERVICES:
            self.assertIn(name, names, msg=name)

    def test_store_absent_when_not_injected(self) -> None:
        """store 未注入时不登记（会话持久化是可选面）。"""

        self.assertFalse(self.app.context.has(SERVICE_STORE))
        self.assertIsNone(self.app.store)

    def test_context_and_compactor_factories_default_on(self) -> None:
        """上下文管线与压缩器默认装配。"""

        self.assertTrue(self.app.context.has(SERVICE_SESSION_FACTORY))
        self.assertTrue(self.app.context.has(SERVICE_COMPACTOR_FACTORY))
        self.assertIsNotNone(self.app.context_factory)
        self.assertIsNotNone(self.app.compactor_factory)
        pipeline = self.app.context_factory("cid-probe")
        self.assertIsNotNone(pipeline)
        self.assertTrue(hasattr(pipeline, "layout_payload"))

    def test_optional_services_registered_when_injected(self) -> None:

        from agent.mechanisms.session_store import SessionStore

        store = SessionStore(self.root / "sessions")
        app = build_app(
            store=store,
            backup_root=self.root / "bk2",
            recycle_root=self.root / "rc2",
        )
        self.addCleanup(app.dispose)
        self.assertTrue(app.context.has(SERVICE_STORE))
        self.assertIs(app.store, store)

    def test_compactor_factory_registered_by_default(self) -> None:
        """压缩器在装配期就位。"""

        self.assertTrue(self.app.context.has(SERVICE_COMPACTOR_FACTORY))
        self.assertTrue(callable(self.app.compactor_factory))

    def test_duplicate_registration_still_rejected(self) -> None:

        with self.assertRaises(ValueError):
            self.app.context.register(SERVICE_REGISTRY, object())

class AppAttributeDelegationTest(_AppFixture):
    """App 属性即上下文快捷方式（无双份状态）。"""

    def test_every_attribute_resolves_to_context_service(self) -> None:

        for attr, service in ATTR_TO_SERVICE.items():
            with self.subTest(attr=attr):
                self.assertIs(
                    getattr(self.app, attr),
                    self.app.context.get(service),
                    msg=f"{attr} 应直接解析自上下文，而非另存一份",
                )

    def test_app_holds_no_duplicate_service_state(self) -> None:

        # 实例字典里不应出现服务引用（只有 context 与装配默认值）
        leaked = set(self.app.__dict__) & set(ATTR_TO_SERVICE)
        self.assertEqual(leaked, set(), msg=f"App 重复持有服务：{sorted(leaked)}")

    def test_service_attributes_are_read_only(self) -> None:

        for attr in ATTR_TO_SERVICE:
            with self.subTest(attr=attr):
                with self.assertRaises(AttributeError):
                    setattr(self.app, attr, object())

    def test_gate_still_resolves_through_session_registry(self) -> None:

        self.assertIs(self.app.gate, self.app.gate_for(""))
        self.assertIsNot(self.app.gate_for("conv-x"), self.app.gate)

class DisposeTest(_AppFixture):
    """进程停机释放。"""

    def test_dispose_clears_services_and_sessions(self) -> None:

        # 先造出会话运行态（含默认桶门控）
        contexts = self.app.session_contexts
        self.app.gate_for("conv-dispose")
        self.assertIsNotNone(self.app.gate)  # 惰性造出默认桶
        self.assertGreaterEqual(contexts.active_count(), 2)

        self.app.dispose()

        self.assertEqual(self.app.context.names(), [])
        self.assertEqual(contexts.active_count(), 0)

    def test_dispose_releases_default_bucket_gate(self) -> None:
        """顺序保证：默认桶门控是惰性造的，若先清容器则永远漏释放。"""

        contexts = self.app.session_contexts
        self.assertIsNotNone(self.app.gate)
        self.assertEqual(contexts.active_count(), 1)
        self.app.dispose()
        self.assertEqual(contexts.active_count(), 0)
        self.assertEqual(self.app.context.names(), [])

    def test_dispose_is_idempotent(self) -> None:

        self.app.dispose()
        self.app.dispose()
        self.assertEqual(self.app.context.names(), [])

    def test_runner_registered_and_mesh_activator_wired(self) -> None:

        self.assertIs(self.app.runner, self.app.context.get(SERVICE_RUNNER))
        self.assertIsNotNone(self.app.mesh)

if __name__ == "__main__":
    unittest.main()
