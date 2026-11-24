"""管道帧在读取前限长，大请求正文仍能无损分块。"""
import io
import struct
import unittest
from unittest.mock import patch

from agent.mechanisms.model_http.wire import (
    BODY_CHUNK_BYTES,
    WireProtocolError,
    read_body,
    read_frame,
    write_body,
    write_frame,
)
from tests.test_http_worker import request_frames


class HTTPWireTest(unittest.TestCase):
    def test_invalid_header_is_rejected_before_reading_payload(self):
        for kind, size in ((b"D", 10**12), (b"B", BODY_CHUNK_BYTES + 1),
                           (b"R", 1), (b"Z", 0), (b"C", 256 * 1024 + 1)):
            with self.subTest(kind=kind, size=size):
                stream = io.BytesIO(struct.pack("!c16sQ", kind, b"a" * 16, size))
                with patch.object(stream, "read", wraps=stream.read) as reader:
                    with self.assertRaises(WireProtocolError):
                        read_frame(stream)
                    reader.assert_called_once_with(25)

    def test_oversized_write_never_publishes_a_partial_frame(self):
        stream = io.BytesIO()
        with self.assertRaises(WireProtocolError):
            write_frame(stream, b"B", b"x" * (BODY_CHUNK_BYTES + 1), request_id=b"a" * 16)
        self.assertEqual(stream.getvalue(), b"")

    def test_large_and_empty_request_bodies_round_trip(self):
        for body in (b"", b"abc" * BODY_CHUNK_BYTES):
            with self.subTest(size=len(body)):
                stream = io.BytesIO()
                write_body(stream, body, request_id=b"a" * 16)
                stream.seek(0)
                self.assertEqual(read_body(stream, len(body), b"a" * 16), body)
                self.assertEqual(stream.read(), b"")

    def test_request_body_rejects_mismatch_empty_progress_and_overflow(self):
        for body, size, identity in ((b"x", 1, b"b" * 16), (b"", 1, b"a" * 16),
                                     (b"xx", 1, b"a" * 16)):
            stream = io.BytesIO()
            write_body(stream, body, request_id=identity)
            stream.seek(0)
            with self.assertRaises(WireProtocolError):
                read_body(stream, size, b"a" * 16)

    def test_upstream_oversized_line_is_bounded_closed_and_reported(self):
        from agent.mechanisms.model_http import worker

        response = io.BytesIO(b"data: " + b"x" * 100)
        outgoing = io.BytesIO()
        with patch.object(worker, "MAX_DATA_BYTES", 32), \
                patch.object(worker.urllib.request, "urlopen", return_value=response):
            worker.serve_one(request_frames(), outgoing)
        self.assertTrue(response.closed)
        outgoing.seek(0)
        self.assertEqual(read_frame(outgoing)[0], b"R")
        self.assertEqual(read_frame(outgoing)[0], b"X")
        self.assertEqual(read_frame(outgoing)[0], b"E")
