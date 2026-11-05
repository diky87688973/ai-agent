"""命令输出的字节分块不应拆坏多字节字符。"""
from __future__ import annotations

import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from agent.capabilities.builtin.command_tools import _pump_reader
from agent.mechanisms.background_tasks import MAX_OUTPUT_BYTES, BackgroundTaskManager
from agent.mechanisms.command_safety import CommandOutputDecoder


class CommandOutputEncodingTest(unittest.TestCase):
    def test_background_streams_normalize_legacy_and_utf8(self) -> None:
        import threading

        manager = BackgroundTaskManager.__new__(BackgroundTaskManager)
        manager._lock = threading.RLock()
        manager._changed = threading.Condition(manager._lock)
        for encoding in ("utf-8", "gb18030"):
            text = "中文路径：D:/文件/😀"
            record = SimpleNamespace(stdout=bytearray(), stderr=bytearray(), task_id="probe")
            manager._read_stream(record, BytesIO(text.encode(encoding)), "stdout")
            self.assertEqual(record.stdout.decode("utf-8"), text)

    def test_background_ring_trim_keeps_character_boundary(self) -> None:
        record = SimpleNamespace(stdout_cursor=0, truncated=False)
        target = bytearray(b"a" * MAX_OUTPUT_BYTES)
        BackgroundTaskManager._append_output(record, target, "stdout", "中文😀".encode("utf-8"))
        self.assertTrue(target.decode("utf-8").endswith("中文😀"))
        target = bytearray("中".encode("utf-8") * (MAX_OUTPUT_BYTES // 3))
        BackgroundTaskManager._append_output(record, target, "stdout", b"ab")
        self.assertTrue(target.decode("utf-8").endswith("ab"))

    def test_utf8_at_every_split_position(self) -> None:
        text = "开始：中文路径 D:/文件/✅/😀\n结束"
        data = text.encode("utf-8")
        for split in range(len(data) + 1):
            with self.subTest(split=split):
                decoder = CommandOutputDecoder()
                actual = decoder.decode(data[:split]) + decoder.decode(data[split:], final=True)
                self.assertEqual(actual, text)

    def test_gb18030_byte_at_a_time(self) -> None:
        text = "开始：中文输出 😀\n结束"
        decoder = CommandOutputDecoder()
        actual = "".join(decoder.decode(bytes([byte])) for byte in text.encode("gb18030"))
        self.assertEqual(actual + decoder.decode(b"", final=True), text)

    def test_stream_readers_keep_independent_decoders_and_raw_bytes(self) -> None:
        for name, encoding in (("stdout", "utf-8"), ("stderr", "gb18030")):
            with self.subTest(stream=name):
                data = "中文路径：D:/文件/😀".encode(encoding)
                raw, events = [], []
                with patch("agent.capabilities.builtin.command_tools._read_available",
                           side_effect=[bytes([byte]) for byte in data] + [b""]):
                    _pump_reader(object(), raw, name,
                                 lambda stream, text, events=events: events.append((stream, text)))
                self.assertEqual(b"".join(raw), data)
                self.assertEqual("".join(text for _, text in events), data.decode(encoding))
                self.assertTrue(all(stream == name for stream, _ in events))
