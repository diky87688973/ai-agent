# -*- coding: utf-8 -*-
"""并发 / 争用测试（K4）。

这些对象都被多个会话线程共享：Web 壳每个会话一个线程，工具执行又可能开线程。
单线程用例测不出"上限被击穿""同一个 confirm_id 被消费两次""注册表丢条目"，
所以这里用真线程 + 屏障反复争用，断言不变量而不是"大概没崩"。
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
import threading
import time
import types
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.capabilities.model_catalog import ModelCatalog, ModelEntry  # noqa: E402
from agent.mechanisms.context_pipeline import ContextSources, SourceMeta  # noqa: E402
from agent.mechanisms.live_state import LiveState  # noqa: E402
from agent.mechanisms.quality.pending import MAX_PENDING_PREVIEWS, PendingStore  # noqa: E402

THREADS = 8
ROUNDS = 120


def _run_threads(target, count: int = THREADS) -> None:
    """让 `count` 个线程在同一个屏障后同时开跑。"""
    barrier = threading.Barrier(count)
    errors: list[BaseException] = []

    def _wrap():
        try:
            barrier.wait()
            target()
        except BaseException as exc:  # 线程里的异常必须带回主线程，否则测试假绿
            errors.append(exc)

    threads = [threading.Thread(target=_wrap) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    if errors:
        raise errors[0]


class PendingStoreContentionTest(unittest.TestCase):
    """预览快照仓库：上限、同路径去重、一次性消费在并发下仍成立。"""

    def test_capacity_is_never_exceeded(self) -> None:
        store = PendingStore()

        def worker() -> None:
            for i in range(ROUNDS):
                store.register_preview("write_file", {"path": f"f-{threading.get_ident()}-{i}.txt"},
                                       path_keys=("path",))

        _run_threads(worker)
        self.assertLessEqual(len(store.records), MAX_PENDING_PREVIEWS)
        self.assertGreater(len(store.records), 0)

    def test_same_path_keeps_exactly_one_latest(self) -> None:
        store = PendingStore()
        ids: list[str] = []

        def worker() -> None:
            for _ in range(ROUNDS):
                ids.append(store.register_preview(
                    "write_file", {"path": "same.txt"}, path_keys=("path",)
                ))

        _run_threads(worker)
        same = [rec for rec in store.records.values() if rec.get("path") == "same.txt"]
        self.assertEqual(len(same), 1)
        self.assertEqual(len(ids), THREADS * ROUNDS)

    def test_take_is_exactly_once(self) -> None:
        store = PendingStore()
        confirm_id = store.register_preview("write_file", {"path": "once.txt"},
                                            path_keys=("path",))
        results: list[object] = []
        lock = threading.Lock()

        def worker() -> None:
            got = store.take(confirm_id)
            with lock:
                results.append(got)

        _run_threads(worker)
        self.assertEqual(sum(1 for item in results if item is not None), 1)
        self.assertLessEqual(len(store.records), 1)

    def test_confirm_is_visible_to_concurrent_peek(self) -> None:
        store = PendingStore()
        confirm_id = store.register_preview("write_file", {"path": "x.txt"},
                                            path_keys=("path",))

        def worker() -> None:
            store.confirm(confirm_id)
            self.assertTrue(store.peek(confirm_id)["confirmed"])

        _run_threads(worker)


class ContextSourcesContentionTest(unittest.TestCase):
    """注入源注册表：并发注册/卸载后条目数与版本号仍然自洽。"""

    def test_register_and_dispose_are_balanced(self) -> None:
        sources = ContextSources()
        caught: list[list] = []
        lock = threading.Lock()

        def worker() -> None:
            disposes = [
                sources.add(lambda _cid, n=i: [f"text-{n}"],
                            SourceMeta(key=f"k{threading.get_ident()}-{i}", label="L"))
                for i in range(ROUNDS)
            ]
            for dispose in disposes:
                dispose()
            with lock:
                caught.append(disposes)

        _run_threads(worker)
        segments = sources.collect_segments("cid")
        self.assertEqual(segments.items, ())
        self.assertEqual(segments.counts, ())
        self.assertGreater(sources.version, 0)

    def test_collect_sees_a_consistent_snapshot(self) -> None:
        sources = ContextSources()
        baseline = sources.add(lambda _cid: ["base"], SourceMeta(key="base", label="Base"))
        self.addCleanup(baseline)
        stop = threading.Event()

        def churn() -> None:
            for i in range(ROUNDS):
                dispose = sources.add(lambda _cid, n=i: [f"x{n}"])
                dispose()

        def reader() -> None:
            while not stop.is_set():
                segments = sources.collect_segments("cid")
                # 不变量：每一段的 counts 长度与 items 对齐，且 base 永远在
                self.assertEqual(len(segments.counts), len(segments.items))
                self.assertIn("base", [key for key, _label, _text in segments.items])

        churn_threads = [threading.Thread(target=churn) for _ in range(THREADS // 2)]
        readers = [threading.Thread(target=reader) for _ in range(2)]
        for thread in readers + churn_threads:
            thread.start()
        for thread in churn_threads:
            thread.join()
        stop.set()
        for thread in readers:
            thread.join()


class LiveStateContentionTest(unittest.TestCase):
    """实时状态：不同会话互不串写；同一会话的并发写不丢结构。"""

    def test_distinct_conversations_do_not_interfere(self) -> None:
        state = LiveState()

        def worker() -> None:
            cid = f"cid-{threading.get_ident()}"
            for i in range(ROUNDS):
                state.set_mode(cid, "plan" if i % 2 else "execute")
                state.set_todo(cid, {"list_id": f"{cid}-{i}", "items": []})
                self.assertEqual(state.get_mode(cid), "plan" if i % 2 else "execute")

        _run_threads(worker)

    def test_same_conversation_writes_stay_well_formed(self) -> None:
        state = LiveState()
        cid = "shared-cid"
        allowed = {"auto", "plan", "execute"}

        def worker() -> None:
            for i in range(ROUNDS):
                state.set_mode(cid, ("plan", "execute", "auto")[i % 3])
                todo = state.get_todo(cid)
                if todo is not None:
                    self.assertIn("items", todo)
                state.set_reasoning_effort(cid, "max" if i % 2 else "high")

        _run_threads(worker)
        self.assertIn(state.get_mode(cid), allowed)
        self.assertIn(state.get_reasoning_effort(cid), ("high", "max"))


class ModelCatalogContentionTest(unittest.TestCase):
    """模型目录：热替换期间快照不得混批，provider 缓存不得把旧实例交给新条目。"""

    _OPTIONS = {
        "base_url": "https://example.invalid/v1",
        "api_key": "k-test",
        "model": "m-test",
    }

    @classmethod
    def _batch(cls, prefix: str, count: int = 3):
        return tuple(
            ModelEntry.from_options(
                id=f"{prefix}{i}", provider="openai", options=cls._OPTIONS,
                is_default=(i == 0),
            )
            for i in range(count)
        )

    def test_snapshot_is_never_mixed_during_replacement(self) -> None:
        catalog = ModelCatalog()
        batches = {"a": self._batch("a"), "b": self._batch("b")}
        catalog.set_source("churn", batches["a"])
        stop = threading.Event()

        def churn() -> None:
            for i in range(ROUNDS):
                key = "a" if i % 2 else "b"
                catalog.set_source("churn", batches[key])

        def reader() -> None:
            valid = {frozenset(item.id for item in batch) for batch in batches.values()}
            while not stop.is_set():
                snap = catalog.snapshot()
                ids = frozenset(item.id for item in snap.entries)
                self.assertIn(ids, valid, msg="快照必须整批来自同一次登记")
                self.assertEqual(snap.authoritative, bool(snap.entries))
                if snap.entries:
                    self.assertIn(snap.default_id, ids)

        churn_threads = [threading.Thread(target=churn) for _ in range(THREADS // 2)]
        readers = [threading.Thread(target=reader) for _ in range(3)]
        for thread in readers + churn_threads:
            thread.start()
        for thread in churn_threads:
            thread.join()
        stop.set()
        for thread in readers:
            thread.join()

    def test_provider_cache_is_keyed_by_entry_fingerprint(self) -> None:
        catalog = ModelCatalog()
        catalog.set_source("churn", self._batch("a"))
        rotated = tuple(
            ModelEntry.from_options(
                id=f"a{i}", provider="openai",
                options={**self._OPTIONS, "api_key": "rotated"},
            )
            for i in range(3)
        )

        def worker() -> None:
            for _ in range(ROUNDS):
                provider = catalog.provider_for("a1")
                self.assertIsNotNone(provider)
                self.assertEqual(provider.model, self._OPTIONS["model"])

        def churn() -> None:
            for i in range(ROUNDS):
                catalog.set_source("churn", rotated if i % 2 else self._batch("a"))

        threads = [threading.Thread(target=worker) for _ in range(THREADS // 2)]
        threads.append(threading.Thread(target=churn))
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()


def _load_ai_speak_modules():
    plugin_dir = _ROOT / "plugins" / "ai_speak"
    package = "fan_agent_plugins.ai_speak_concurrency"
    parent = sys.modules.get("fan_agent_plugins")
    if parent is None:
        parent = types.ModuleType("fan_agent_plugins")
        parent.__path__ = [str(plugin_dir)]
        sys.modules["fan_agent_plugins"] = parent
    spec = importlib.util.spec_from_file_location(
        package,
        str(plugin_dir / "plugin.py"),
        submodule_search_locations=[str(plugin_dir)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[package] = module
    spec.loader.exec_module(module)
    return (
        importlib.import_module(package + ".config"),
        importlib.import_module(package + ".provider"),
        importlib.import_module(package + ".runtime"),
    )


class AISpeakRuntimeContentionTest(unittest.TestCase):
    """AI说话运行时：多线程向同一会话入队不丢段、不重复、顺序可核。"""

    def test_many_threads_keep_every_segment(self) -> None:
        config_mod, provider_mod, runtime_mod = _load_ai_speak_modules()

        class _Provider:
            name = "concurrency"

            def available(self) -> bool:
                return True

            def synthesize(self, text, *, voice, timeout_s, speed=1.0):
                return provider_mod.SpeechAudio(
                    data=text.encode("utf-8"), mime="audio/mpeg", voice=voice
                )

        class _Publisher:
            def __init__(self) -> None:
                self.frames = []
                self._lock = threading.Lock()

            def __call__(self, plugin, event, payload):
                with self._lock:
                    self.frames.append((plugin, event, dict(payload)))
                return 1

            def connected(self) -> bool:
                return True

        runtime = runtime_mod.AISpeakRuntime(
            config_mod.AISpeakConfig(voice="v", max_segment_chars=128), _Provider()
        )
        self.addCleanup(runtime.dispose)
        publisher = _Publisher()
        per_thread = 10

        def worker() -> None:
            call_id = f"call-{threading.get_ident()}"
            segments = tuple(f"第{index}步。" for index in range(per_thread))
            runtime.enqueue(
                "cid-12345678",
                call_id,
                segments,
                "v",
                publisher,
            )

        _run_threads(worker)
        expected = THREADS * per_thread
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and len(publisher.frames) < expected:
            time.sleep(0.01)
        self.assertEqual(len(publisher.frames), expected)
        keys = {
            (frame[2]["call_id"], frame[2]["index"])
            for frame in publisher.frames
            if frame[1] == "segment"
        }
        self.assertEqual(len(keys), expected)
        self.assertEqual(runtime.status()["totals"]["spoken"], expected)


if __name__ == "__main__":
    unittest.main()
