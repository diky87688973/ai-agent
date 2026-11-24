"""真实网络阻塞、传输进程终止、请求保真与错误映射。"""
from __future__ import annotations

import json
import socketserver
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from agent.core.error_report import report_error
from agent.core.ports import LogicalRequest
from agent.core.stream_control import interruptible_stream
from agent.mechanisms.model_http import process as worker_process
from agent.mechanisms.model_http import transport
from agent.mechanisms.model_http.client import pool_scope
from agent.mechanisms.model_http.pool import ModelHTTPPool
from agent.mechanisms.providers.anthropic import AnthropicProvider
from agent.mechanisms.providers.base import ModelRequestError
from agent.mechanisms.providers.openai import OpenAICompatibleProvider
from agent.mechanisms.providers.sse import stream_with_timeout


class HTTPTransportTest(unittest.TestCase):
    def setUp(self):
        self.pool = ModelHTTPPool()
        self.addCleanup(self.pool.dispose)

    def _server(self, handler, *, http=False):
        cls = ThreadingHTTPServer if http else socketserver.ThreadingTCPServer
        server = cls(("127.0.0.1", 0), handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def _cancel_source(self, source, ready):
        stopped, exited = threading.Event(), threading.Event()
        processes, received, failures = [], [], []
        spawn = worker_process.subprocess.Popen

        def tracked_spawn(*args, **kwargs):
            process = spawn(*args, **kwargs)
            processes.append(process)
            return process

        def read():
            try:
                with pool_scope(self.pool):
                    received.extend(interruptible_stream(source, stopped.is_set))
            except Exception as exc:
                report_error("test.http_transport", exc)
                failures.append(exc)
            finally:
                exited.set()

        with mock.patch.object(worker_process.subprocess, "Popen", side_effect=tracked_spawn):
            consumer = threading.Thread(target=read)
            consumer.start()
            try:
                self.assertTrue(ready.wait(4))
                stopped.set()
                self.assertTrue(exited.wait(1), "取消不能等待网络超时")
                for process in processes:
                    process.wait(timeout=1)
                    self.assertIsNotNone(process.poll(), "传输进程必须真正退出")
                    self.assertTrue(process.stdin.closed)
                    self.assertTrue(process.stdout.closed)
                self.assertTrue(processes)
                self.assertEqual(received, [])
                self.assertEqual(failures, [])
            finally:
                stopped.set()
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=2)
                consumer.join(2)

    def test_stop_before_http_headers_for_both_providers(self):
        for provider_type in (OpenAICompatibleProvider, AnthropicProvider):
            with self.subTest(provider=provider_type.__name__):
                ready, release = threading.Event(), threading.Event()

                class Handler(socketserver.BaseRequestHandler):
                    def handle(self, ready=ready, release=release):
                        self.request.recv(8192)
                        ready.set()
                        release.wait(10)

                server = self._server(Handler)
                self.addCleanup(release.set)
                provider = provider_type(base_url="http://127.0.0.1", api_key="local-only",
                                         model="test", timeout=300)
                url = f"http://127.0.0.1:{server.server_address[1]}"
                self._cancel_source(lambda p=provider, u=url: p._post_stream(u, {}), ready)
                release.set()

    def test_stop_during_tls_handshake(self):
        ready, release = threading.Event(), threading.Event()

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.recv(8192)
                ready.set()
                release.wait(10)

        server = self._server(Handler)
        self.addCleanup(release.set)
        provider = OpenAICompatibleProvider(base_url="https://127.0.0.1", api_key="local-only", model="m")
        url = f"https://127.0.0.1:{server.server_address[1]}"
        self._cancel_source(lambda: provider._post_stream(url, {}), ready)

    def test_stop_during_dns_and_tcp_connect(self):
        for target in ("getaddrinfo", "create_connection"):
            with self.subTest(stage=target), tempfile.TemporaryDirectory() as folder:
                marker = Path(folder) / "entered"
                code = (
                    "import socket,time; from pathlib import Path; "
                    "from agent.mechanisms.model_http.worker import main; "
                    f"marker=Path({str(marker)!r}); "
                    "socket." + target + "=lambda *a,**k:(marker.write_text('entered'),time.sleep(60))[1]; "
                    "main()")
                ready = threading.Event()

                def check_marker(marker=marker, ready=ready):
                    deadline = time.monotonic() + 4
                    while time.monotonic() < deadline and not marker.exists():
                        time.sleep(0.01)
                    if marker.exists():
                        ready.set()

                watcher = threading.Thread(target=check_marker, daemon=True)
                watcher.start()
                provider = OpenAICompatibleProvider(base_url="https://127.0.0.1:9", api_key="local-only", model="m")
                with mock.patch.object(worker_process, "worker_command", return_value=[sys.executable, "-c", code]):
                    self._cancel_source(lambda p=provider: p._post_stream("https://127.0.0.1:9", {}), ready)
                watcher.join(1)

    def test_request_bytes_headers_sse_and_process_cleanup(self):
        captured = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                captured["headers"] = dict(self.headers)
                captured["body"] = self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.end_headers()
                self.wfile.write('data: {"text":"你好"}\n\ndata: [DONE]\n'.encode())

            def log_message(self, *_args):
                pass

        server = self._server(Handler, http=True)
        body = json.dumps({"text": "原样传递" * 200000}, ensure_ascii=False).encode()
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/model", data=body,
                                         headers={"Authorization": "Bearer local-test-only"})
        response = transport.open_model_response(request, timeout=3, pool=self.pool)
        try:
            self.assertIn('"你好"'.encode(), b"".join(response))
            self.assertEqual(captured["body"], body)
            self.assertEqual(captured["headers"]["Authorization"], "Bearer local-test-only")
            self.assertNotIn("local-test-only", " ".join(response._worker.process.args))
        finally:
            response.close()
        self.assertIsNone(response._worker.process.poll())

    def test_stop_while_request_pipe_is_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / "entered"
            code = f"import time; from pathlib import Path; Path({str(marker)!r}).write_text('ready'); time.sleep(60)"
            ready = threading.Event()

            def check_marker():
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline and not marker.exists():
                    time.sleep(0.01)
                if marker.exists():
                    ready.set()

            watcher = threading.Thread(target=check_marker, daemon=True)
            watcher.start()
            provider = OpenAICompatibleProvider(base_url="http://127.0.0.1:9", api_key="local-only", model="m")
            with mock.patch.object(worker_process, "worker_command", return_value=[sys.executable, "-c", code]):
                self._cancel_source(lambda: provider._post_stream("http://127.0.0.1:9", {"large": "x" * 2_000_000}), ready)
            watcher.join(1)

    def test_http_error_keeps_status_headers_and_body(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(429)
                self.send_header("Retry-After", "3")
                self.end_headers()
                self.wfile.write(b'{"error":{"message":"rate limited"}}')

            def log_message(self, *_args):
                pass

        server = self._server(Handler, http=True)
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            transport.open_model_response(request, timeout=3, pool=self.pool)
        with caught.exception as error:
            self.assertEqual(error.code, 429)
            self.assertEqual(error.headers["Retry-After"], "3")
            self.assertIn(b"rate limited", error.read())

    def test_stream_total_timeout_kills_transport_process(self):
        release = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.flush()
                release.wait(5)

            def log_message(self, *_args):
                pass

        server = self._server(Handler, http=True)
        self.addCleanup(release.set)
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}")
        response = transport.open_model_response(request, timeout=3, pool=self.pool)
        with self.assertRaisesRegex(ModelRequestError, "模型流超时"):
            list(stream_with_timeout(response, 0.05, abort=response.abort))
        self.assertIsNotNone(response._worker.process.poll())

    def test_stopping_one_transport_does_not_close_another(self):
        first_ready, second_ready, release = (threading.Event() for _ in range(3))

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.flush()
                (first_ready if self.path == "/first" else second_ready).set()
                release.wait(5)
                if self.path == "/second":
                    self.wfile.write(b'data: {"value":2}\n')

            def log_message(self, *_args):
                pass

        server = self._server(Handler, http=True)
        self.addCleanup(release.set)
        base = f"http://127.0.0.1:{server.server_port}"
        first = transport.open_model_response(urllib.request.Request(base + "/first"), timeout=3, pool=self.pool)
        second = transport.open_model_response(urllib.request.Request(base + "/second"), timeout=3, pool=self.pool)
        try:
            first.abort()
            first.close()
            self.assertIsNone(second._worker.process.poll())
            release.set()
            self.assertIn(b'"value":2', b"".join(second))
        finally:
            release.set()
            first.close()
            second.close()

    def test_both_provider_streams_reuse_worker_even_when_server_stays_open(self):
        release = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                if "anthropic" in self.path:
                    chunks = [
                        {"type": "message_start", "message": {"usage": {}}},
                        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "hello"}},
                        {"type": "content_block_stop", "index": 0},
                        {"type": "message_delta", "delta": {"stop_reason": "end_turn"}},
                        {"type": "message_stop"},
                    ]
                    data = b"".join(("data: " + json.dumps(chunk) + "\n\n").encode() for chunk in chunks)
                else:
                    data = b'data: {"choices":[{"delta":{"content":"hello"}}]}\n\ndata: [DONE]\n\n'
                self.send_response(200)
                self.end_headers()
                self.wfile.write(data)
                self.wfile.flush()
                release.wait(5)

            def log_message(self, *_args):
                pass

        server = self._server(Handler, http=True)
        self.addCleanup(release.set)
        base = f"http://127.0.0.1:{server.server_port}"
        providers = [OpenAICompatibleProvider(base_url=base + "/openai", api_key="local-only", model="m"),
                     AnthropicProvider(base_url=base + "/anthropic", api_key="local-only", model="m")]
        pids = []
        with pool_scope(self.pool):
            for provider in providers * 3:
                result = list(provider.stream(LogicalRequest(messages=[], tools=[])))
                self.assertEqual("".join(delta.text for delta in result if delta.kind == "text"), "hello")
                self.assertEqual(self.pool.snapshot()["idle"], 1)
                pids.append(self.pool.snapshot()["pids"][0])
        self.assertEqual(len(set(pids)), 1)
        release.set()

    def test_reused_worker_does_not_carry_credentials_or_cookies_between_requests(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append((dict(self.headers), self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.send_header("Set-Cookie", "session=must-not-leak")
                self.end_headers()
                self.wfile.write(b'data: {"ok":true}\n')

            def log_message(self, *_args):
                pass

        server = self._server(Handler, http=True)
        url = f"http://127.0.0.1:{server.server_port}"
        pids, request_ids = [], []
        for number, headers in enumerate(({"Authorization": "Bearer first-only"}, {})):
            request = urllib.request.Request(url, data=str(number).encode(), headers=headers)
            response = transport.open_model_response(request, timeout=3, pool=self.pool)
            try:
                list(response)
                pids.append(response._worker.process.pid)
                request_ids.append(response._request.request_id)
            finally:
                response.close()
        self.assertEqual(pids[0], pids[1])
        self.assertNotEqual(request_ids[0], request_ids[1])
        self.assertIn("Authorization", received[0][0])
        self.assertNotIn("Authorization", received[1][0])
        self.assertNotIn("Cookie", received[1][0])
        self.assertEqual([body for _, body in received], [b"0", b"1"])

    def test_late_abort_cannot_kill_reused_worker_serving_next_request(self):
        release = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.flush()
                if self.path == "/second":
                    release.wait(5)
                self.wfile.write(b'data: {"ok":true}\n')

            def log_message(self, *_args):
                pass

        server = self._server(Handler, http=True)
        self.addCleanup(release.set)
        base = f"http://127.0.0.1:{server.server_port}"
        first = transport.open_model_response(urllib.request.Request(base + "/first"), timeout=3, pool=self.pool)
        list(first)
        first.close()
        second = transport.open_model_response(urllib.request.Request(base + "/second"), timeout=3, pool=self.pool)
        try:
            self.assertIs(first._worker, second._worker)
            with self.assertRaisesRegex(ModelRequestError, "已关闭"):
                list(first)
            first.abort()
            first.close()
            self.assertIsNone(second._worker.process.poll())
            release.set()
            self.assertIn(b'"ok":true', b"".join(second))
        finally:
            release.set()
            second.close()

    def test_oversized_frame_evicts_worker_before_payload_read_without_replay(self):
        code = (
            "import sys,time,struct; from agent.mechanisms.model_http.wire import read_frame; "
            "_,_,rid=read_frame(sys.stdin.buffer);read_frame(sys.stdin.buffer); "
            "sys.stdout.buffer.write(struct.pack('!c16sQ',b'D',rid,10**12));"
            "sys.stdout.buffer.flush();time.sleep(30)")
        request = urllib.request.Request("http://127.0.0.1:9", data=b"{}")
        with mock.patch.object(worker_process, "worker_command", return_value=[sys.executable, "-c", code]) as command:
            with self.assertRaisesRegex(ModelRequestError, "长度上限"):
                transport.open_model_response(request, timeout=3, pool=self.pool)
        self.assertEqual(command.call_count, 1)
        self.assertEqual(self.pool.snapshot()["workers"], 0)

    def test_mismatched_response_is_evicted_without_automatic_replay(self):
        code = (
            "import sys,time; from agent.mechanisms.model_http.wire import read_frame,write_frame; "
            "read_frame(sys.stdin.buffer);read_frame(sys.stdin.buffer); "
            "write_frame(sys.stdout.buffer,b'R',request_id=b'0'*16);time.sleep(30)")
        request = urllib.request.Request("http://127.0.0.1:9", data=b"{}")
        with mock.patch.object(worker_process, "worker_command", return_value=[sys.executable, "-c", code]) as command:
            with self.assertRaisesRegex(ModelRequestError, "不匹配"):
                transport.open_model_response(request, timeout=3, pool=self.pool)
        self.assertEqual(command.call_count, 1)
        self.assertEqual(self.pool.snapshot()["workers"], 0)
