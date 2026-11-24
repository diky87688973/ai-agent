"""真实 HTTP 并发突发：容量、进程复用、响应归属和取消后的补位。"""
import json
import threading
import unittest
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from agent.core.model_call import StreamDelta
from agent.core.stream_control import StreamControl, stream_control_scope
from agent.core.thread_context import thread_with_context
from agent.mechanisms.compaction.compactor import make_provider_summarizer
from agent.mechanisms.model_http import process as worker_process
from agent.mechanisms.model_http.client import pool_scope
from agent.mechanisms.model_http.pool import ModelHTTPPool, PoolLimits
from agent.mechanisms.model_http.transport import open_model_response
from agent.mechanisms.providers.base import ModelRequestCancelled
from agent.mechanisms.providers.openai import OpenAICompatibleProvider
from agent.mechanisms.providers.sse import stream_with_timeout
from agent.mechanisms.session_title import make_provider_title_generator


class HTTPPoolConcurrencyTest(unittest.TestCase):
    def test_cancelled_title_discards_partial_text_without_retry(self):
        calls = []

        class Provider:
            def stream(self, request):
                calls.append(request)
                yield StreamDelta(kind="text", text="unfinished title")
                raise ModelRequestCancelled("stopped")

        generate = make_provider_title_generator(Provider())
        self.assertEqual(generate([{"role": "user", "content": "question"}]), "")
        self.assertEqual(len(calls), 1)

    def test_cancelled_summary_discards_partial_streamed_text(self):
        seen, release = threading.Event(), threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'data: {"choices":[{"delta":{"content":"partial summary"}}]}\n\n')
                self.wfile.flush()
                release.wait(5)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.addCleanup(release.set)
        pool, control = ModelHTTPPool(), StreamControl()
        self.addCleanup(pool.dispose)
        provider = OpenAICompatibleProvider(base_url=f"http://127.0.0.1:{server.server_port}",
                                           api_key="local-only", model="m")

        class Observed:
            def stream(self, request):
                for delta in provider.stream(request):
                    yield delta
                    if delta.kind == "text":
                        seen.set()

        result = []
        summarize = make_provider_summarizer(Observed())
        with stream_control_scope(control), pool_scope(pool):
            thread = thread_with_context(target=lambda: result.append(summarize(prefix=[])), daemon=True)
            thread.start()
            self.assertTrue(seen.wait(3))
            control.set()
            thread.join(1)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, [""])
        self.assertEqual(pool.snapshot()["workers"], 0)

    def test_run_scope_cancels_synchronous_auxiliary_http(self):
        entered, released, exited = (threading.Event() for _ in range(3))

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                entered.set()
                released.wait(5)

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.addCleanup(released.set)
        pool, control = ModelHTTPPool(), StreamControl()
        self.addCleanup(pool.dispose)
        provider = OpenAICompatibleProvider(base_url="http://127.0.0.1", api_key="local-only", model="m")

        def call():
            try:
                list(provider._post_stream(f"http://127.0.0.1:{server.server_port}", {}))
            except ModelRequestCancelled:
                return
            finally:
                exited.set()

        with stream_control_scope(control), pool_scope(pool):
            thread = thread_with_context(target=call, daemon=True)
            thread.start()
            self.assertTrue(entered.wait(3))
            control.set()
            self.assertTrue(exited.wait(1))
        thread.join(1)
        self.assertEqual(pool.snapshot()["workers"], 0)

    def test_twenty_requests_use_only_two_processes_without_crossed_responses(self):
        barrier = threading.Barrier(2)
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(body["number"])
                barrier.wait(3)
                self.send_response(200)
                self.end_headers()
                data = "data: " + json.dumps(body) + "\n\ndata: [DONE]\n"
                self.wfile.write(data.encode())

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        pool = ModelHTTPPool(PoolLimits(max_workers=2, max_pending=32, wait_timeout=10))
        self.addCleanup(pool.dispose)
        processes = []
        spawn = worker_process.subprocess.Popen

        def tracked_spawn(*args, **kwargs):
            process = spawn(*args, **kwargs)
            processes.append(process)
            return process

        def call(number):
            request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}",
                                             data=json.dumps({"number": number}).encode())
            response = open_model_response(request, timeout=5, pool=pool, completion={"data": "[DONE]"})
            return list(stream_with_timeout(response, 5, abort=response.abort))[0]["number"]

        with mock.patch.object(worker_process.subprocess, "Popen", side_effect=tracked_spawn):
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(call, range(20)))
        self.assertEqual(results, list(range(20)))
        self.assertEqual(sorted(requests), list(range(20)))
        self.assertEqual(len(processes), 2)
        self.assertEqual(pool.snapshot()["idle"], 2)
        self.assertEqual(pool.snapshot()["waiting"], 0)
        pool.dispose()
        self.assertTrue(all(process.poll() is not None for process in processes))
        self.assertTrue(all(process.stdin.closed and process.stdout.closed for process in processes))
