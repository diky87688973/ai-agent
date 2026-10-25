# -*- coding: utf-8 -*-
"""事件总线测试。

覆盖：订阅/分发、类型过滤、异常隔离、幂等 disposer、快照遍历、dispose_all、
参数校验、引擎 event_sink 旁路接线（回合事件流同步发布、sink 异常不影响回合）。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.app import build_app  # noqa: E402
from agent.core import event_name as ev  # noqa: E402
from agent.core.error_report import bind_error_sink  # noqa: E402
from agent.core.event_bus import EventBus  # noqa: E402
from agent.core.events import make_event  # noqa: E402
from agent.mechanisms.providers.echo import EchoProvider  # noqa: E402


class EventBusTest(unittest.TestCase):
    """总线本体：分发 / 过滤 / 隔离 / 生命周期。"""

    def test_publish_dispatches_in_order(self):

        bus = EventBus()
        got = []
        bus.subscribe("alpha", lambda e: got.append(e.data.get("n")))
        bus.publish(make_event("alpha", n=1))
        bus.publish(make_event("alpha", n=2))
        self.assertEqual(got, [1, 2])

    def test_type_filter(self):

        bus = EventBus()
        got = []
        bus.subscribe("alpha", lambda e: got.append("a"))
        bus.publish(make_event("beta"))
        self.assertEqual(got, [])

    def test_subscribe_validation(self):

        bus = EventBus()
        with self.assertRaises(ValueError):
            bus.subscribe("", lambda e: None)
        with self.assertRaises(ValueError):
            bus.subscribe("x", None)

    def test_subscriber_exception_isolated(self):

        bus = EventBus()
        got = []

        def bad(e):
            raise RuntimeError("boom")

        bus.subscribe("x", bad)
        bus.subscribe("x", lambda e: got.append("ok"))
        bus.publish(make_event("x"))  # 不向外抛
        self.assertEqual(got, ["ok"])

    def test_disposer_idempotent(self):

        bus = EventBus()
        got = []
        dispose = bus.subscribe("x", lambda e: got.append(1))
        dispose()
        dispose()
        bus.publish(make_event("x"))
        self.assertEqual(got, [])

    def test_snapshot_iteration(self):

        bus = EventBus()
        got = []
        holder = {}

        def handler_a(e):
            got.append("a")
            dispose_b = holder.get("dispose_b")
            if dispose_b is not None:
                dispose_b()

        def handler_b(e):
            got.append("b")

        bus.subscribe("x", handler_a)
        holder["dispose_b"] = bus.subscribe("x", handler_b)
        bus.publish(make_event("x"))
        self.assertEqual(got, ["a", "b"])  # 快照：本次分发不受退订影响
        bus.publish(make_event("x"))
        self.assertEqual(got, ["a", "b", "a"])  # 下次分发只剩 a

    def test_dispose_all(self):

        bus = EventBus()
        got = []
        bus.subscribe("x", lambda e: got.append(1))
        bus.subscribe("y", lambda e: got.append(2))
        bus.dispose_all()
        bus.publish(make_event("x"))
        bus.publish(make_event("y"))
        self.assertEqual(got, [])

class EngineEventSinkTest(unittest.TestCase):
    """引擎侧接线：回合事件流同步旁路发布。"""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory(prefix="event-bus-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        manifest = root / "plugins.ini"
        manifest.write_text("", encoding="utf-8")
        self.app = build_app(
            provider=EchoProvider(),
            plugins_path=manifest,
            data_root=root / "data",
        )
        self.addCleanup(self.app.dispose)

    def test_turn_events_published_to_bus(self):

        app = self.app
        deltas, ends = [], []
        app.event_bus.subscribe(ev.ASSISTANT_DELTA, lambda e: deltas.append(e))
        app.event_bus.subscribe(ev.TURN_ENDED, lambda e: ends.append(e))
        events = list(app.session("conv-bus-1").start_turn("你好"))
        self.assertTrue(deltas)
        self.assertEqual(len(ends), 1)
        self.assertIs(ends[0], events[-1])
        self.assertEqual(ends[0].data.get("conversation_id"), "conv-bus-1")

    def test_sink_exception_does_not_break_turn(self):

        app = self.app
        reported: list = []

        def _sink(tag, exc, **kw):
            reported.append((tag, exc, kw))

        bind_error_sink(_sink)
        self.addCleanup(lambda: bind_error_sink(None))

        def broken(event):
            raise RuntimeError("sink boom")

        app.event_bus.publish = broken  # 模拟旁路实现故障
        events = list(app.session("conv-bus-2").start_turn("你好"))
        self.assertTrue(any(e.type == ev.TURN_ENDED for e in events))
        self.assertTrue(
            any(tag == "core.event_sink" for tag, _exc, _kw in reported),
            msg=f"应 report_error(core.event_sink)，实际 {reported!r}",
        )
        self.assertTrue(
            any(isinstance(exc, RuntimeError) for _tag, exc, _kw in reported),
        )

if __name__ == "__main__":
    unittest.main()
