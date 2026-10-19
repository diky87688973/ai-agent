# -*- coding: utf-8 -*-
"""AI说话运行时、工具与装配测试。"""
from __future__ import annotations

import asyncio
import base64
import importlib
import importlib.util
import sys
import threading
import time
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
_PLUGIN_DIR = _ROOT / "plugins" / "ai_speak"
_PACKAGE = "fan_agent_plugins.ai_speak_test"

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agent.capabilities.registry import ToolRegistry  # noqa: E402
from agent.core.context import (  # noqa: E402
    SERVICE_PLUGIN_EVENTS,
    AppContext,
    ToolTurnContext,
)
from agent.core.session_scope import (  # noqa: E402
    reset_tool_turn_context,
    set_tool_turn_context,
)
from agent.core.tool_call import ToolCallRequest, ToolPipeline  # noqa: E402


def _load_package() -> Any:
    parent = sys.modules.get("fan_agent_plugins")
    if parent is None:
        parent = types.ModuleType("fan_agent_plugins")
        parent.__path__ = [str(_PLUGIN_DIR)]
        sys.modules["fan_agent_plugins"] = parent
    spec = importlib.util.spec_from_file_location(
        _PACKAGE,
        str(_PLUGIN_DIR / "plugin.py"),
        submodule_search_locations=[str(_PLUGIN_DIR)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PACKAGE] = module
    spec.loader.exec_module(module)
    return module


_PLUGIN = _load_package()
_CONFIG = importlib.import_module(_PACKAGE + ".config")
_PROVIDER = importlib.import_module(_PACKAGE + ".provider")
_RUNTIME = importlib.import_module(_PACKAGE + ".runtime")
_TEXT = importlib.import_module(_PACKAGE + ".text")
_TOOL = importlib.import_module(_PACKAGE + ".tool")


def _config(**kwargs: Any):
    base = {
        "engine": "edge",
        "voice": "test-voice",
        "max_segment_chars": 128,
        "play_interval_ms": 0,
        "sync_playback": False,
    }
    base.update(kwargs)
    return _CONFIG.AISpeakConfig(**base)


class RecordingProvider:
    name = "recording"

    def __init__(self, fail_texts: Optional[List[str]] = None) -> None:
        self.calls: List[tuple] = []
        self.fail_texts = set(fail_texts or [])

    def available(self) -> bool:
        return True

    def synthesize(self, text: str, *, voice: str, timeout_s: float):
        self.calls.append((text, voice, timeout_s))
        if any(marker in text for marker in self.fail_texts):
            raise _PROVIDER.SpeechSynthesisError("simulated failure")
        return _PROVIDER.SpeechAudio(
            data=("audio:" + text).encode("utf-8"),
            mime="audio/mpeg",
            voice=voice,
        )


class MissingProvider(RecordingProvider):
    def available(self) -> bool:
        return False

    def synthesize(self, text: str, *, voice: str, timeout_s: float):
        raise _PROVIDER.SpeechEngineUnavailable("edge-tts missing")


class BlockingProvider(RecordingProvider):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def synthesize(self, text: str, *, voice: str, timeout_s: float):
        self.started.set()
        self.release.wait(2.0)
        return super().synthesize(text, voice=voice, timeout_s=timeout_s)


class FakePublisher:
    def __init__(self, delivered: int = 1) -> None:
        self.delivered = int(delivered)
        self.frames: List[tuple] = []
        self._lock = threading.Lock()

    def __call__(self, plugin: str, event: str, payload: Dict[str, Any]) -> int:
        with self._lock:
            self.frames.append((plugin, event, dict(payload)))
        return self.delivered

    def connected(self) -> bool:
        return self.delivered > 0

    def snapshot(self) -> List[tuple]:
        with self._lock:
            return list(self.frames)


def _wait(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class ProviderTest(unittest.TestCase):
    def _fake_edge(self, *, delay: float = 0.0, audio: bytes = b"audio"):
        module = types.ModuleType("edge_tts")

        class Communicate:
            def __init__(self, text: str, voice: str) -> None:
                self.text = text
                self.voice = voice

            async def stream(self):
                if delay:
                    await asyncio.sleep(delay)
                if audio:
                    yield {"type": "audio", "data": audio}

        module.Communicate = Communicate
        return module

    def test_available_and_synthesize(self) -> None:
        fake = self._fake_edge()
        provider = _PROVIDER.EdgeTTSProvider()
        with mock.patch.dict(sys.modules, {"edge_tts": fake}):
            self.assertTrue(provider.available())
            audio = provider.synthesize("你好", voice="v", timeout_s=1.0)
        self.assertEqual(audio.data, b"audio")
        self.assertEqual(audio.mime, "audio/mpeg")
        self.assertEqual(audio.voice, "v")

    def test_missing_dependency(self) -> None:
        provider = _PROVIDER.EdgeTTSProvider()
        with mock.patch.dict(sys.modules, {"edge_tts": None}):
            self.assertFalse(provider.available())
            with self.assertRaises(_PROVIDER.SpeechEngineUnavailable):
                provider.synthesize("你好", voice="v", timeout_s=1.0)

    def test_empty_audio(self) -> None:
        provider = _PROVIDER.EdgeTTSProvider()
        with mock.patch.dict(sys.modules, {"edge_tts": self._fake_edge(audio=b"")}):
            with self.assertRaises(_PROVIDER.SpeechSynthesisError):
                provider.synthesize("你好", voice="v", timeout_s=1.0)

    def test_timeout(self) -> None:
        provider = _PROVIDER.EdgeTTSProvider()
        with mock.patch.dict(sys.modules, {"edge_tts": self._fake_edge(delay=0.2)}):
            with self.assertRaises(_PROVIDER.SpeechSynthesisError) as ctx:
                provider.synthesize("你好", voice="v", timeout_s=0.01)
        self.assertIn("超时", str(ctx.exception))


class RuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = _RUNTIME.AISpeakRuntime(_config(), RecordingProvider())
        self.addCleanup(self.runtime.dispose)

    def test_publish_in_order_and_base64(self) -> None:
        publisher = FakePublisher()
        queued = self.runtime.enqueue(
            "cid-12345678", "call-1", ("第一段。", "第二段。"), "test-voice", publisher
        )
        self.assertEqual(queued, 2)
        self.assertTrue(_wait(lambda: len(publisher.snapshot()) >= 2))
        frames = [frame for frame in publisher.snapshot() if frame[1] == "segment"]
        self.assertEqual([frame[2]["index"] for frame in frames], [0, 1])
        self.assertEqual([frame[2]["total"] for frame in frames], [2, 2])
        self.assertEqual(base64.b64decode(frames[0][2]["audio"]),
                         "audio:第一段。".encode("utf-8"))
        self.assertEqual(frames[0][2]["text"], "第一段。")
        self.assertTrue(_wait(lambda: self.runtime.status()["totals"]["spoken"] == 2))

    def test_playback_wait_timeout_and_cancel(self) -> None:
        waiter = self.runtime.begin_playback("cid-12345678", "call-timeout")
        self.assertEqual(waiter.wait(0.01), "timeout")
        self.runtime.forget_playback("cid-12345678", "call-timeout")

        waiter = self.runtime.begin_playback("cid-12345678", "call-cancel")
        self.assertEqual(waiter.wait(1.0, canceled=lambda: True), "stopped")
        self.runtime.forget_playback("cid-12345678", "call-cancel")

    def test_synthesis_failure_is_isolated(self) -> None:
        self.runtime = _RUNTIME.AISpeakRuntime(
            _config(), RecordingProvider(fail_texts=["坏"])
        )
        self.addCleanup(self.runtime.dispose)
        publisher = FakePublisher()
        self.runtime.enqueue(
            "cid-12345678", "call-1", ("坏的。", "好的。"), "test-voice", publisher
        )
        self.assertTrue(_wait(lambda: len(publisher.snapshot()) >= 2))
        events = [frame[1] for frame in publisher.snapshot()]
        self.assertIn("error", events)
        self.assertIn("segment", events)
        status = self.runtime.status()
        self.assertEqual(status["totals"]["failed"], 1)
        self.assertEqual(status["totals"]["spoken"], 1)

    def test_no_sse_stops_worker(self) -> None:
        publisher = FakePublisher(delivered=0)
        self.runtime.enqueue(
            "cid-12345678", "call-1", ("第一段。", "第二段。"), "test-voice", publisher
        )
        self.assertTrue(_wait(lambda: self.runtime.status()["totals"]["dropped"] == 1))
        self.assertEqual(len(publisher.snapshot()), 1)
        self.assertEqual(self.runtime.status()["totals"]["spoken"], 0)

    def test_stop_clears_queue_and_publishes_stop(self) -> None:
        provider = BlockingProvider()
        self.runtime = _RUNTIME.AISpeakRuntime(_config(), provider)
        self.addCleanup(self.runtime.dispose)
        publisher = FakePublisher()
        self.runtime.enqueue(
            "cid-12345678", "call-1", ("一。", "二。", "三。"), "test-voice", publisher
        )
        self.assertTrue(provider.started.wait(1.0))
        self.runtime.stop_cid("cid-12345678", "turn_stopped")
        provider.release.set()
        self.assertTrue(_wait(lambda: any(f[1] == "stop" for f in publisher.snapshot())))
        self.assertTrue(_wait(lambda: self.runtime.status()["totals"]["spoken"] == 0))
        stop = [f for f in publisher.snapshot() if f[1] == "stop"][0]
        self.assertEqual(stop[2]["reason"], "turn_stopped")

    def test_queue_full_rejects_whole_batch(self) -> None:
        provider = BlockingProvider()
        self.runtime = _RUNTIME.AISpeakRuntime(_config(), provider)
        self.addCleanup(self.runtime.dispose)
        publisher = FakePublisher()
        self.runtime.enqueue(
            "cid-12345678", "call-1", tuple("一。" for _ in range(1024)),
            "test-voice", publisher,
        )
        self.assertTrue(provider.started.wait(1.0))
        with self.assertRaises(_RUNTIME.SpeechBusy):
            self.runtime.enqueue(
                "cid-12345678", "call-2", ("多。", "多。"), "test-voice", publisher
            )
        provider.release.set()

    def test_dispose_publishes_stop_and_blocks_enqueue(self) -> None:
        publisher = FakePublisher()
        self.runtime.enqueue(
            "cid-12345678", "call-1", ("一。",), "test-voice", publisher
        )
        self.assertTrue(_wait(lambda: self.runtime.status()["totals"]["spoken"] == 1))
        self.runtime.dispose()
        self.assertTrue(any(f[1] == "stop" for f in publisher.snapshot()))
        with self.assertRaises(_PROVIDER.SpeechEngineUnavailable):
            self.runtime.enqueue(
                "cid-12345678", "call-2", ("二。",), "test-voice", publisher
            )


class ToolTest(unittest.TestCase):
    def _runtime(self, provider: Any = None) -> Any:
        runtime = _RUNTIME.AISpeakRuntime(_config(), provider or RecordingProvider())
        self.addCleanup(runtime.dispose)
        return runtime

    def _context(self, publisher: Any) -> ToolTurnContext:
        app = AppContext()
        app.register(SERVICE_PLUGIN_EVENTS, publisher)
        return ToolTurnContext(
            app=app,
            session=SimpleNamespace(conversation_id="cid-12345678"),
            call=SimpleNamespace(call_id="call-1", name="ai_speak", arguments={}),
        )

    def _call(self, runtime: Any, msg: Any, publisher: Any) -> Any:
        tool = _TOOL.AISpeakTool(runtime)
        token = set_tool_turn_context(self._context(publisher))
        try:
            return tool.execute({"msg": msg})
        finally:
            reset_tool_turn_context(token)

    def test_success_enqueues_segments(self) -> None:
        runtime = self._runtime()
        publisher = FakePublisher()
        result = self._call(runtime, "主子，文件写好了。", publisher)
        self.assertEqual(result["accepted"], True)
        self.assertEqual(result["segments"], 1)
        self.assertTrue(_wait(lambda: len(publisher.snapshot()) == 1))
        self.assertEqual(publisher.snapshot()[0][1], "segment")

    def test_sync_playback_waits_for_frontend_ack(self) -> None:
        runtime = _RUNTIME.AISpeakRuntime(
            _config(sync_playback=True), RecordingProvider()
        )
        self.addCleanup(runtime.dispose)
        publisher = FakePublisher()
        result: Dict[str, Any] = {}

        def _run() -> None:
            try:
                result["value"] = self._call(runtime, "主子，文件写好了。", publisher)
            except BaseException as exc:  # 线程里的异常要带回主线程
                result["error"] = exc

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        self.assertTrue(_wait(lambda: any(
            frame[1] == "segment" for frame in publisher.snapshot())))
        self.assertTrue(thread.is_alive())
        self.assertTrue(runtime.ack_playback("cid-12345678", "call-1", "played"))
        thread.join(2.0)
        self.assertFalse(thread.is_alive())
        self.assertNotIn("error", result)
        self.assertTrue(result["value"]["played"])
        self.assertGreaterEqual(result["value"]["waited_ms"], 0)

    def test_sync_playback_times_out_without_ack(self) -> None:
        runtime = _RUNTIME.AISpeakRuntime(
            _config(sync_playback=True), RecordingProvider()
        )
        self.addCleanup(runtime.dispose)
        publisher = FakePublisher()
        result: Dict[str, Any] = {}

        def _run() -> None:
            try:
                self._call(runtime, "主子，文件写好了。", publisher)
            except BaseException as exc:
                result["error"] = exc

        with mock.patch.object(_TOOL, "_playback_timeout_s", return_value=0.05):
            thread = threading.Thread(target=_run, daemon=True)
            thread.start()
            self.assertTrue(_wait(lambda: any(
                frame[1] == "segment" for frame in publisher.snapshot())))
            thread.join(2.0)
        self.assertFalse(thread.is_alive())
        self.assertIsInstance(result.get("error"), _RUNTIME.SpeechPlaybackFailed)
        self.assertEqual(result["error"].status, "timeout")

    def test_sync_playback_releases_on_stop(self) -> None:
        runtime = _RUNTIME.AISpeakRuntime(
            _config(sync_playback=True), RecordingProvider()
        )
        self.addCleanup(runtime.dispose)
        publisher = FakePublisher()
        result: Dict[str, Any] = {}

        def _run() -> None:
            try:
                self._call(runtime, "主子，文件写好了。", publisher)
            except BaseException as exc:
                result["error"] = exc

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        self.assertTrue(_wait(lambda: any(
            frame[1] == "segment" for frame in publisher.snapshot())))
        runtime.stop_cid("cid-12345678", "turn_stopped")
        thread.join(2.0)
        self.assertFalse(thread.is_alive())
        self.assertIsInstance(result.get("error"), _RUNTIME.SpeechPlaybackFailed)
        self.assertEqual(result["error"].status, "stopped")

    def test_invalid_message_fails_before_enqueue(self) -> None:
        runtime = self._runtime()
        publisher = FakePublisher()
        with self.assertRaises(_TEXT.MessageValidationError):
            self._call(runtime, "abc", publisher)
        self.assertEqual(publisher.snapshot(), [])

    def test_missing_publisher_fails(self) -> None:
        runtime = self._runtime()
        tool = _TOOL.AISpeakTool(runtime)
        token = set_tool_turn_context(
            ToolTurnContext(
                app=AppContext(),
                session=SimpleNamespace(conversation_id="cid-12345678"),
                call=SimpleNamespace(call_id="call-1", name="ai_speak", arguments={}),
            )
        )
        try:
            with self.assertRaises(_PROVIDER.SpeechEngineUnavailable):
                tool.execute({"msg": "你好。"})
        finally:
            reset_tool_turn_context(token)

    def test_disconnected_publisher_fails(self) -> None:
        runtime = self._runtime()
        with self.assertRaises(_PROVIDER.SpeechEngineUnavailable):
            self._call(runtime, "你好。", FakePublisher(delivered=0))

    def test_missing_provider_fails(self) -> None:
        runtime = self._runtime(MissingProvider())
        with self.assertRaises(_PROVIDER.SpeechEngineUnavailable):
            self._call(runtime, "你好。", FakePublisher())

    def test_tool_contract(self) -> None:
        tool = _TOOL.AISpeakTool(self._runtime())
        self.assertEqual(tool.name, "ai_speak")
        self.assertEqual(tool.label, "AI说话")
        self.assertEqual(set(tool.parameters), {"msg"})
        self.assertFalse(tool.parallel_safe)
        self.assertFalse(tool.needs_preview)

    def test_pipeline_envelope(self) -> None:
        runtime = self._runtime()
        publisher = FakePublisher()
        registry = ToolRegistry()
        registry.register(_TOOL.AISpeakTool(runtime))
        app = AppContext()
        app.register(SERVICE_PLUGIN_EVENTS, publisher)
        ctx = SimpleNamespace(
            conversation_id="cid-12345678",
            app=app,
            session=SimpleNamespace(conversation_id="cid-12345678"),
            progress_sink=None,
        )
        pipeline = ToolPipeline()
        ok = pipeline.execute(
            registry,
            ToolCallRequest(call_id="c1", name="ai_speak", arguments={"msg": "你好。"}),
            ctx,
        )
        self.assertTrue(ok.ok)
        self.assertEqual(ok.data["accepted"], True)
        failed = pipeline.execute(
            registry,
            ToolCallRequest(call_id="c2", name="ai_speak", arguments={"msg": "abc"}),
            ctx,
        )
        self.assertFalse(failed.ok)
        self.assertIn("MessageValidationError", failed.error)


class _FakeCtx:
    def __init__(self) -> None:
        self.tools: List[Any] = []
        self.boot_scripts: List[str] = []
        self.routes: List[tuple] = []
        self.subscriptions: List[str] = []
        self.runtime: Any = None
        self.disposed = 0

    def register_tool(self, tool: Any):
        self.tools.append(tool)
        return lambda: self.tools.remove(tool)

    def add_boot_script(self, path: str):
        self.boot_scripts.append(path)
        return lambda: self.boot_scripts.remove(path)

    def add_route(self, method: str, path: str, handler: Any):
        self.routes.append((method, path, handler))
        return lambda: self.routes.remove((method, path, handler))

    def subscribe(self, event_type: str, handler: Any):
        self.subscriptions.append(event_type)
        return lambda: self.subscriptions.remove(event_type)

    def set_runtime(self, runtime: Any) -> None:
        self.runtime = runtime


class RegistrationTest(unittest.TestCase):
    def test_register_and_dispose(self) -> None:
        ctx = _FakeCtx()
        disposers = _PLUGIN.register(ctx)
        self.assertEqual([tool.name for tool in ctx.tools], ["ai_speak"])
        self.assertEqual(ctx.boot_scripts, ["ui/player.js", "ui/tool-view.js"])
        self.assertEqual([(m, p) for m, p, _h in ctx.routes],
                         [("GET", "config"), ("GET", "status"), ("POST", "played")])
        self.assertEqual(sorted(ctx.subscriptions), ["error", "turn_ended"])
        self.assertEqual(ctx.runtime.config.engine, "edge")
        for disposer in reversed(disposers):
            disposer()

    def test_config_and_status_routes(self) -> None:
        ctx = _FakeCtx()
        _PLUGIN.register(ctx)
        handlers = {path: handler for _m, path, handler in ctx.routes}
        status, config = handlers["config"]({})
        self.assertEqual(status, 200)
        self.assertEqual(config["max_segment_chars"], 128)
        self.assertFalse(config["sync_playback"])
        played, ack = handlers["played"]({
            "body": {"conversation_id": "cid", "call_id": "missing",
                     "status": "played"}})
        self.assertEqual(played, 200)
        self.assertFalse(ack["matched"])
        status, report = handlers["status"]({})
        self.assertEqual(status, 200)
        self.assertTrue(report["ok"])
        self.assertEqual(report["engine"], "edge")


if __name__ == "__main__":
    unittest.main()
