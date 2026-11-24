"""HTTP 池的容量、排队、取消身份、故障与资源所有权。"""
from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from agent.app import build_app
from agent.config import get_model_http
from agent.core.context import SERVICE_MODEL_HTTP_POOL
from agent.core.model_call import StreamDelta
from agent.core.ports import LogicalRequest
from agent.mechanisms.model_http.client import ModelHTTPClient, pool_scope
from agent.mechanisms.model_http.pool import ModelHTTPPool, PoolLimits, PoolRequest
from agent.mechanisms.providers.base import ModelRequestError
from agent.mechanisms.session_store import SessionStore
from tests.testkit import no_plugins


class FakeWorker:
    process = None

    def __init__(self, fail=False):
        self.running = False
        self.fail = fail

    def start(self):
        if self.fail:
            raise OSError("spawn failed")
        self.running = True

    def alive(self):
        return self.running

    def abort(self):
        self.running = False

    def close(self):
        self.running = False


class HTTPPoolTest(unittest.TestCase):
    def make_pool(self, **kwargs):
        workers = []

        def create():
            worker = FakeWorker()
            workers.append(worker)
            return worker

        pool = ModelHTTPPool(PoolLimits(max_workers=1, max_pending=2, **kwargs), worker_factory=create)
        self.addCleanup(pool.dispose)
        return pool, workers

    def wait_for(self, predicate):
        deadline = time.monotonic() + 2
        while not predicate() and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertTrue(predicate())

    def start_waiter(self, pool, request, results):
        def run():
            try:
                worker = pool.acquire(request)
                results.append(worker)
                pool.release(request, worker, healthy=True)
            except (ModelRequestError, OSError) as exc:
                results.append(exc)

        thread = threading.Thread(target=run)
        thread.start()
        self.addCleanup(lambda: thread.join(2))
        self.addCleanup(lambda: pool.cancel(request))
        return thread

    def test_sequential_requests_reuse_worker(self):
        pool, workers = self.make_pool()
        for _ in range(10):
            request = PoolRequest()
            worker = pool.acquire(request)
            pool.release(request, worker, healthy=True)
        self.assertEqual(len(workers), 1)
        self.assertEqual(pool.snapshot()["idle"], 1)

    def test_waiters_receive_worker_in_fifo_order(self):
        pool, workers = self.make_pool()
        held = PoolRequest()
        worker = pool.acquire(held)
        order = []
        gates = [threading.Event(), threading.Event()]
        for gate in gates:
            self.addCleanup(gate.set)
        threads = []

        def run(request, label, gate):
            borrowed = pool.acquire(request)
            order.append(label)
            gate.wait(2)
            pool.release(request, borrowed, healthy=True)

        for index in range(2):
            thread = threading.Thread(target=run, args=(PoolRequest(), index, gates[index]))
            thread.start()
            threads.append(thread)
            self.wait_for(lambda expected=index + 1: pool.snapshot()["waiting"] == expected)
        pool.release(held, worker, healthy=True)
        self.wait_for(lambda: len(order) == 1)
        self.assertEqual(order, [0])
        gates[0].set()
        self.wait_for(lambda: len(order) == 2)
        gates[1].set()
        for thread in threads:
            thread.join(2)
            self.assertFalse(thread.is_alive())
        self.assertEqual(order, [0, 1])
        self.assertEqual(len(workers), 1)

    def test_cancel_waiter_does_not_kill_active_request(self):
        pool, workers = self.make_pool()
        active, waiting = PoolRequest(), PoolRequest()
        worker = pool.acquire(active)
        results = []
        thread = self.start_waiter(pool, waiting, results)
        self.wait_for(lambda: pool.snapshot()["waiting"] == 1)
        pool.cancel(waiting)
        thread.join(1)
        self.assertIsInstance(results[0], ModelRequestError)
        self.assertTrue(worker.alive())
        self.assertEqual(len(workers), 1)
        pool.release(active, worker, healthy=True)

    def test_full_queue_fails_without_spawning_more_workers(self):
        pool = ModelHTTPPool(PoolLimits(max_workers=1, max_pending=1), worker_factory=FakeWorker)
        self.addCleanup(pool.dispose)
        held = PoolRequest()
        worker = pool.acquire(held)
        pending, results = PoolRequest(), []
        self.start_waiter(pool, pending, results)
        self.wait_for(lambda: pool.snapshot()["waiting"] == 1)
        with self.assertRaisesRegex(ModelRequestError, "已满"):
            pool.acquire(PoolRequest())
        self.assertEqual(pool.snapshot()["workers"], 1)
        pool.release(held, worker, healthy=True)

    def test_zero_pending_budget_still_admits_all_available_worker_slots(self):
        gate = threading.Event()

        class DelayedPool(ModelHTTPPool):
            def _wait_for_worker(self, request, deadline):
                if not gate.wait(2):
                    raise TimeoutError("test scheduler stalled")
                return super()._wait_for_worker(request, deadline)

        pool = DelayedPool(PoolLimits(max_workers=2, max_pending=0), worker_factory=FakeWorker)
        self.addCleanup(pool.dispose)
        self.addCleanup(gate.set)
        results = []
        threads = [self.start_waiter(pool, PoolRequest(), results) for _ in range(2)]
        try:
            self.wait_for(lambda: pool.snapshot()["waiting"] == 2 or bool(results))
            self.assertEqual(results, [], "有空闲容量时不得因等待预算为零拒绝请求")
            with self.assertRaisesRegex(ModelRequestError, "已满"):
                pool.acquire(PoolRequest())
        finally:
            gate.set()
            for thread in threads:
                thread.join(2)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(result, FakeWorker) for result in results))

    def test_wait_timeout_does_not_consume_another_slot(self):
        pool, workers = self.make_pool(wait_timeout=0.04)
        request = PoolRequest()
        worker = pool.acquire(request)
        with self.assertRaisesRegex(ModelRequestError, "超时"):
            pool.acquire(PoolRequest())
        self.assertEqual(pool.snapshot()["waiting"], 0)
        self.assertEqual(len(workers), 1)
        pool.release(request, worker, healthy=True)

    def test_late_cancel_and_release_cannot_affect_new_lease(self):
        pool, _ = self.make_pool()
        old, new = PoolRequest(), PoolRequest()
        worker = pool.acquire(old)
        pool.release(old, worker, healthy=True)
        self.assertIs(pool.acquire(new), worker)
        pool.cancel(old)
        pool.release(old, worker, healthy=False)
        self.assertTrue(worker.alive())
        self.assertEqual(pool.snapshot()["busy"], 1)
        pool.release(new, worker, healthy=True)

    def test_unhealthy_and_dead_idle_workers_are_replaced(self):
        pool, workers = self.make_pool()
        request = PoolRequest()
        first = pool.acquire(request)
        pool.release(request, first, healthy=False)
        request = PoolRequest()
        second = pool.acquire(request)
        self.assertIsNot(first, second)
        pool.release(request, second, healthy=True)
        second.abort()
        request = PoolRequest()
        third = pool.acquire(request)
        self.assertIsNot(second, third)
        self.assertEqual(len(workers), 3)
        pool.release(request, third, healthy=True)

    def test_spawn_failure_releases_capacity_without_replaying(self):
        calls = []

        def create():
            worker = FakeWorker(fail=not calls)
            calls.append(worker)
            return worker

        pool = ModelHTTPPool(PoolLimits(max_workers=1), worker_factory=create)
        self.addCleanup(pool.dispose)
        with self.assertRaisesRegex(OSError, "spawn failed"):
            pool.acquire(PoolRequest())
        self.assertEqual(len(calls), 1)
        self.assertEqual(pool.snapshot()["workers"], 0)
        request = PoolRequest()
        worker = pool.acquire(request)
        pool.release(request, worker, healthy=True)

    def test_idle_timeout_reclaims_worker(self):
        pool, workers = self.make_pool(idle_timeout=0.04)
        request = PoolRequest()
        worker = pool.acquire(request)
        pool.release(request, worker, healthy=True)
        self.wait_for(lambda: pool.snapshot()["workers"] == 0)
        self.assertFalse(workers[0].alive())

    def test_shutdown_wakes_waiters_and_refuses_new_requests(self):
        pool, _ = self.make_pool()
        request = PoolRequest()
        worker = pool.acquire(request)
        results = []
        self.start_waiter(pool, PoolRequest(), results)
        self.wait_for(lambda: pool.snapshot()["waiting"] == 1)
        pool.dispose()
        self.wait_for(lambda: bool(results))
        self.assertIsInstance(results[0], ModelRequestError)
        self.assertFalse(worker.alive())
        with self.assertRaisesRegex(ModelRequestError, "已关闭"):
            pool.acquire(PoolRequest())


class HTTPPoolConfigurationTest(unittest.TestCase):
    def test_invalid_limits_are_rejected(self):
        for values in ({"max_workers": 0}, {"max_workers": True}, {"max_pending": -1},
                       {"wait_timeout": float("nan")}, {"idle_timeout": 0}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                PoolLimits(**values)

    def test_host_configuration_and_unknown_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.ini"
            path.write_text("[model_http]\nmax_workers=3\nmax_pending=7\nwait_timeout=4\nidle_timeout=5\n")
            self.assertEqual(PoolLimits(**get_model_http(path)), PoolLimits(3, 7, 4, 5))
            path.write_text("[model_http]\nmax_workres=3\n")
            with self.assertRaisesRegex(ValueError, "未知"):
                get_model_http(path)

    def test_client_scope_borrows_but_does_not_dispose_shared_pool(self):
        shared = ModelHTTPPool(worker_factory=FakeWorker)
        self.addCleanup(shared.dispose)
        first, second = ModelHTTPClient(), ModelHTTPClient()
        self.addCleanup(first.dispose)
        self.addCleanup(second.dispose)
        with pool_scope(shared):
            self.assertIs(first.pool(), shared)
            self.assertIs(second.pool(), shared)
        first.dispose()
        request = PoolRequest()
        worker = shared.acquire(request)
        shared.release(request, worker, healthy=True)

    def test_boot_registers_one_pool_and_router_supplies_it(self):
        class Provider:
            model = "fake"

            def __init__(self):
                self.client = ModelHTTPClient()
                self.seen = []

            def stream(self, _request):
                self.seen.append(self.client.pool())
                yield StreamDelta(kind="text", text="ok")

        no_plugins(self)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            provider = Provider()
            app = build_app(provider=provider, store=SessionStore(root), data_root=root)
            try:
                pool = app.context.get(SERVICE_MODEL_HTTP_POOL)
                list(app.provider.stream(LogicalRequest(messages=[], tools=[])))
                self.assertEqual(provider.seen, [pool])
                self.assertIsNone(provider.client._owned)
                lease = PoolRequest()
                worker = pool.acquire(lease)
                pool.release(lease, worker, healthy=True)
                app.reload_plugins()
                self.assertIs(app.context.get(SERVICE_MODEL_HTTP_POOL), pool)
                self.assertTrue(worker.alive())
            finally:
                app.dispose()
            with self.assertRaisesRegex(ModelRequestError, "已关闭"):
                pool.acquire(PoolRequest())
