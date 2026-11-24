"""文件句柄权限、固定缓冲、断开与容量不足时的资源归属。"""
from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from agent.common.http_contract import FileAccessError, FileResponse, HttpRequest, OpenedFile
from agent.shell.web.file_access import LocalFileAccess
from agent.shell.web.http_responses import CHUNK_BYTES, FileTransfers, byte_range


class FileResponsesTest(unittest.TestCase):
    def test_real_handle_path_and_replacement_check(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "file.bin"
            path.write_bytes(b"data")
            access = LocalFileAccess([root], root)
            opened = access.open("file.bin")
            self.assertEqual(opened.stream.read(), b"data")
            opened.close()
            if os.name == "nt":
                with mock.patch("agent.shell.web.file_access._windows_path", return_value=root.parent / "outside.bin"):
                    with self.assertRaises(FileAccessError):
                        access.open(str(path))
            with mock.patch("agent.shell.web.file_access.os.path.samestat", return_value=False):
                with self.assertRaises(FileAccessError) as raised:
                    access.open(str(path))
                self.assertEqual(raised.exception.status, 409)
            for name in [str(root), "../outside", "\\\\.\\NUL", "https://example.com/file"]:
                with self.subTest(name=name), self.assertRaises((FileAccessError, FileNotFoundError)):
                    access.open(name)

    def _handler(self):
        return SimpleNamespace(command="GET", headers={}, connection=mock.Mock(),
                               wfile=io.BytesIO(), send_response=mock.Mock(),
                               send_header=mock.Mock(), end_headers=mock.Mock(), close_connection=False)

    def _file(self, stream, size):
        return FileResponse(OpenedFile(Path("sample.bin"), stream,
                                      SimpleNamespace(st_size=size, st_mtime=1000)), "application/octet-stream")

    def test_bounded_reads_disconnect_and_capacity_always_close(self):
        class Source(io.BytesIO):
            def read(self, size=-1):
                if size < 0 or size > CHUNK_BYTES:
                    raise AssertionError("unbounded read")
                return super().read(size)
        source = Source(b"a" * (CHUNK_BYTES * 3 + 1))
        handler = self._handler()
        transfers = FileTransfers(limit=1)
        transfers.send(handler, self._file(source, CHUNK_BYTES * 3 + 1))
        self.assertEqual(len(handler.wfile.getvalue()), CHUNK_BYTES * 3 + 1)
        self.assertTrue(source.closed)
        broken = self._handler()
        broken.wfile = mock.Mock()
        broken.wfile.write.side_effect = BrokenPipeError()
        source = Source(b"a" * (CHUNK_BYTES * 2))
        transfers.send(broken, self._file(source, CHUNK_BYTES * 2))
        self.assertTrue(source.closed)
        self.assertTrue(broken.close_connection)
        transfers._capacity.acquire()
        try:
            source = Source(b"a")
            handler = self._handler()
            transfers.send(handler, self._file(source, 1))
            handler.send_response.assert_called_once_with(503)
            self.assertTrue(source.closed)
        finally:
            transfers._capacity.release()

        failing_close = mock.Mock()
        failing_close.close.side_effect = OSError("simulated close failure")
        handler = self._handler()
        handler.command = "HEAD"
        with mock.patch("agent.shell.web.http_responses.report_error") as report:
            transfers.send(handler, self._file(failing_close, 1))
        report.assert_called_once()
        self.assertTrue(transfers._capacity.acquire(blocking=False))
        transfers._capacity.release()

    def test_large_head_and_range_only_touch_requested_bytes(self):
        source = mock.Mock()
        source.read.side_effect = lambda size: b"x" * size
        handler = self._handler()
        handler.command = "HEAD"
        FileTransfers().send(handler, self._file(source, 8 * 1024**3))
        source.read.assert_not_called()
        source.close.assert_called_once()
        source.reset_mock()
        handler = self._handler()
        handler.headers = {"Range": "bytes=8589934500-8589934591"}
        FileTransfers().send(handler, self._file(source, 8 * 1024**3))
        source.seek.assert_called_once_with(8589934500)
        source.read.assert_called_once_with(92)
        self.assertEqual(len(handler.wfile.getvalue()), 92)

    def test_request_maps_are_copied_read_only_and_range_limits(self):
        source = {"path": "original"}
        request = HttpRequest("GET", "/api/file", source, {}, mock.Mock())
        source["path"] = "changed"
        self.assertEqual(request.query["path"], "original")
        with self.assertRaises(TypeError):
            request.query["path"] = "illegal"
        self.assertEqual(byte_range("bytes=-99", 3), (0, 3))
        with self.assertRaises(ValueError):
            byte_range("bytes=" + "9" * 200 + "-", 5)


if __name__ == "__main__":
    unittest.main()
