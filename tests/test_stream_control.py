"""阻塞模型流的取消、迟到结果和传输资源隔离。"""
import threading
import unittest
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from agent.core.stream_control import (
    StreamControl,
    interruptible_stream,
    register_stream_abort,
    stream_control_scope,
)
from agent.mechanisms.model_http.pool import ModelHTTPPool
from agent.mechanisms.model_http.transport import open_model_response
from agent.mechanisms.providers.sse import stream_with_timeout


class StreamControlTest(unittest.TestCase):
    def test_child_completion_keeps_parent_running_and_detaches(self):
        parent = StreamControl()
        with stream_control_scope(parent):
            self.assertEqual(list(interruptible_stream(lambda: iter(["ok"]), parent.is_set)), ["ok"])
        self.assertFalse(parent.is_set())
        self.assertFalse(parent._callbacks)

    def test_reader_start_failure_detaches_from_parent(self):
        parent = StreamControl()
        thread = mock.Mock(ident=None)
        thread.start.side_effect = RuntimeError("thread unavailable")
        with stream_control_scope(parent), mock.patch(
                "agent.core.stream_control.thread_with_context", return_value=thread):
            with self.assertRaisesRegex(RuntimeError, "thread unavailable"):
                list(interruptible_stream(lambda: iter(()), parent.is_set))
        self.assertFalse(parent._callbacks)
        thread.join.assert_not_called()

    def test_real_http_stream_without_data_is_closed_on_stop(self):
        pool = ModelHTTPPool()
        self.addCleanup(pool.dispose)
        headers_sent, release, exited, stopped = (threading.Event() for _ in range(4))

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.flush()
                headers_sent.set()
                release.wait(5)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.addCleanup(release.set)

        def provider():
            response = open_model_response(urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}"), timeout=5, pool=pool)
            try:
                yield from stream_with_timeout(response, 5, abort=response.abort)
            finally:
                exited.set()

        consumer = threading.Thread(target=lambda: list(interruptible_stream(provider, stopped.is_set)))
        consumer.start()
        self.assertTrue(headers_sent.wait(3))
        stopped.set()
        consumer.join(1)
        self.assertFalse(consumer.is_alive())
        self.assertTrue(exited.wait(1), "真实网络读取线程也必须退出")

    def test_blocked_abort_cannot_block_turn_or_other_abort_actions(self):
        release, blocked, closed = (threading.Event() for _ in range(3))
        control = StreamControl()

        def slow_abort():
            blocked.set()
            release.wait(5)

        control.register(slow_abort)
        control.register(closed.set)
        try:
            control.stop()
            self.assertTrue(blocked.wait(1))
            self.assertTrue(closed.wait(1))
        finally:
            release.set()

    def test_cancel_blocked_read_aborts_transport_and_exits(self):
        entered, release, exited, stopped = (threading.Event() for _ in range(4))
        received = []

        def provider():
            remove = register_stream_abort(release.set)
            entered.set()
            try:
                release.wait(5)
                yield "late result"
            finally:
                remove()
                exited.set()

        consumer = threading.Thread(target=lambda: received.extend(
            interruptible_stream(provider, stopped.is_set)))
        consumer.start()
        self.addCleanup(release.set)
        self.assertTrue(entered.wait(2))
        stopped.set()
        consumer.join(1)
        self.assertFalse(consumer.is_alive())
        self.assertTrue(exited.wait(1))
        self.assertEqual(received, [])

    def test_cancel_before_connection_returns_closes_late_transport(self):
        entered, connected, closed, stopped = (threading.Event() for _ in range(4))
        received = []

        def provider():
            entered.set()
            connected.wait(5)
            remove = register_stream_abort(closed.set)
            try:
                yield "late connection"
            finally:
                remove()

        consumer = threading.Thread(target=lambda: received.extend(
            interruptible_stream(provider, stopped.is_set)))
        self.addCleanup(connected.set)
        consumer.start()
        self.assertTrue(entered.wait(2))
        stopped.set()
        consumer.join(1)
        self.assertFalse(consumer.is_alive())
        connected.set()
        self.assertTrue(closed.wait(1))
        self.assertEqual(received, [])

    def test_failure_and_order_are_preserved(self):
        def provider():
            yield "first"
            yield "second"
            raise ValueError("upstream failed")

        stream = interruptible_stream(provider, lambda: False)
        self.assertEqual(next(stream), "first")
        self.assertEqual(next(stream), "second")
        with self.assertRaisesRegex(ValueError, "upstream failed"):
            next(stream)

    def test_stopped_call_never_opens_provider(self):
        def provider():
            self.fail("已终止不能发起请求")

        self.assertEqual(list(interruptible_stream(provider, lambda: True)), [])

    def test_independent_call_survives_another_stream_cancel(self):
        entered, release, stopped = (threading.Event() for _ in range(3))

        def blocked():
            remove = register_stream_abort(release.set)
            entered.set()
            try:
                release.wait(5)
                yield "discard"
            finally:
                remove()

        consumer = threading.Thread(target=lambda: list(interruptible_stream(blocked, stopped.is_set)))
        consumer.start()
        self.addCleanup(release.set)
        self.assertTrue(entered.wait(2))
        stopped.set()
        self.assertEqual(list(interruptible_stream(lambda: iter(["other session"]), lambda: False)),
                         ["other session"])
        consumer.join(1)
        self.assertFalse(consumer.is_alive())
