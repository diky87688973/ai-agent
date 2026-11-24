"""HTTP 子进程协议、终态与测试出网门禁。"""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from agent.mechanisms.model_http import worker
from agent.mechanisms.model_http.wire import WireProtocolError, read_frame, write_frame
from scripts.check_network_isolation import ROOT, _Guard, _worker_command


def request_frames(url="http://127.0.0.1:9", request_id=b"a" * 16):
    incoming = io.BytesIO()
    options = {"url": url, "has_body": True, "headers": {}, "method": "POST",
               "timeout": 1, "body_bytes": 2, "completion": {"data": "[DONE]"}}
    write_frame(incoming, b"C", json.dumps(options).encode(), request_id=request_id)
    write_frame(incoming, b"B", b"{}", request_id=request_id)
    incoming.seek(0)
    return incoming


class WorkerProtocolTest(unittest.TestCase):
    def test_success_closes_upstream_at_terminal_and_preserves_request_identity(self):
        response = io.BytesIO(b'data: hello\n\ndata: [DONE]\nDO NOT READ\n')
        outgoing = io.BytesIO()
        with patch.object(worker.urllib.request, "urlopen", return_value=response):
            worker.serve_one(request_frames(), outgoing)
        self.assertTrue(response.closed)
        outgoing.seek(0)
        frames = [read_frame(outgoing) for _ in range(5)]
        self.assertEqual([frame[0] for frame in frames], [b"R", b"D", b"D", b"T", b"E"])
        self.assertTrue(all(frame[2] == b"a" * 16 for frame in frames))
        self.assertEqual(outgoing.read(), b"")

    def test_error_has_terminal_ack_and_closes_http_error_body(self):
        for error in (TimeoutError("timeout"), urllib.error.HTTPError(
                "http://127.0.0.1:9", 429, "rate limited", {"Retry-After": "2"}, io.BytesIO(b"retry"))):
            with self.subTest(error=type(error).__name__):
                outgoing = io.BytesIO()
                with patch.object(worker.urllib.request, "urlopen", side_effect=error):
                    worker.serve_one(request_frames(), outgoing)
                outgoing.seek(0)
                kind, payload, _ = read_frame(outgoing)
                self.assertEqual(kind, b"X")
                self.assertEqual(json.loads(payload)["type"], type(error).__name__)
                self.assertEqual(read_frame(outgoing)[0], b"E")
                if isinstance(error, urllib.error.HTTPError):
                    self.assertTrue(error.fp.closed)

    def test_invalid_request_frame_never_opens_network(self):
        incoming = request_frames()
        data = bytearray(incoming.read())
        data[0] = ord("R")
        with patch.object(worker.urllib.request, "urlopen") as opener:
            with self.assertRaises(WireProtocolError):
                worker.serve_one(io.BytesIO(data), io.BytesIO())
        opener.assert_not_called()

    def test_completion_rules_only_match_declared_terminal(self):
        cases = [(b'data: {"type":"message_stop"}', {"json": {"type": "message_stop"}}, True),
                 (b'data: {"type":"message_delta"}', {"json": {"type": "message_stop"}}, False),
                 (b'data: invalid message_stop', {"json": {"type": "message_stop"}}, False),
                 (b'data: [DONE]', None, False), (b'event: [DONE]', {"data": "[DONE]"}, False)]
        for line, rule, expected in cases:
            with self.subTest(line=line, rule=rule):
                self.assertEqual(worker.completed(line, rule), expected)

    def test_test_worker_gate_blocks_before_dns_and_records_even_if_error_is_caught(self):
        guard = _Guard(None)
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(_worker_command(Path(temporary), guard), cwd=ROOT,
                                    input=request_frames("http://external.invalid").read(),
                                    capture_output=True, timeout=10, env={**os.environ, "no_proxy": "*", "NO_PROXY": "*"},
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            self.assertEqual(result.returncode, 0, result.stderr)
            frames = io.BytesIO(result.stdout)
            self.assertEqual(read_frame(frames)[0], b"X")
            self.assertEqual(read_frame(frames)[0], b"E")
            records = [json.loads(line) for file in Path(temporary).glob("*.jsonl")
                       for line in file.read_text(encoding="utf-8").splitlines()]
            self.assertTrue(records)
            self.assertEqual(records[0]["host"], "external.invalid")
