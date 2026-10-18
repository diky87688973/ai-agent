# -*- coding: utf-8 -*-
"""Web 事件通道测试 —— `_Channel` 背压与生命周期（纯 Python，与用哪套 UI 无关）。

前端是经典界面单页。

Markdown 注入防线由 `scripts/acceptance_web.py` 的实时场景覆盖：
在真实页面上调经典 UI 自己的 `renderMarkdown`，把结果塞进真实 DOM，再问浏览器
"有没有生成危险元素 / 事件处理器属性 / javascript: 链接"，并额外断言脚本真的没被执行。

那边的判据取真实 DOM而不是 HTML 字符串——转义后的 `&lt;img onerror=…&gt;`
里仍然包含 `onerror=` 这几个字符，字符串包含判断会把"正确转义"误报成"注入面"。
"""
from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.shell.web import _Channel  # noqa: E402


class ChannelBackpressureTest(unittest.TestCase):
    """SSE 连接队列、心跳、慢消费者、关闭语义。"""

    def test_frames_arrive_in_order(self) -> None:

        channel = _Channel()
        for i in range(5):
            channel.push(f"data: {i}\n\n")
        got = [channel.next_frame(1.0) for _ in range(5)]
        self.assertEqual(got, [f"data: {i}\n\n" for i in range(5)])

    def test_idle_returns_heartbeat_not_none(self) -> None:

        channel = _Channel()
        frame = channel.next_frame(0.05)
        self.assertEqual(frame, ": keep-alive\n\n")

    def test_slow_consumer_drops_oldest_keeps_latest(self) -> None:
        """队列满时丢最旧一帧——保证流不断且最终状态可见。"""

        channel = _Channel(maxsize=3)
        for i in range(10):
            channel.push(f"data: {i}\n\n")
        got = []
        while True:
            frame = channel.next_frame(0.05)
            if frame is None or frame == ": keep-alive\n\n":
                break
            got.append(frame)
        self.assertEqual(len(got), 3, msg=str(got))
        self.assertIn("data: 9\n\n", got, msg="最新帧必须保留")

    def test_close_returns_none_and_stops_accepting(self) -> None:

        channel = _Channel()
        channel.close()
        self.assertIsNone(channel.next_frame(0.05))
        channel.push("data: late\n\n")  # 关闭后入队应被忽略
        self.assertIsNone(channel.next_frame(0.05))

    def test_concurrent_push_and_pop_is_safe(self) -> None:

        channel = _Channel(maxsize=500)
        received = []
        done = threading.Event()

        def consumer():
            while not done.is_set():
                frame = channel.next_frame(0.05)
                if frame is None:
                    break
                if frame != ": keep-alive\n\n":
                    received.append(frame)

        thread = threading.Thread(target=consumer, daemon=True)
        thread.start()
        for i in range(200):
            channel.push(f"data: {i}\n\n")
        time.sleep(0.3)
        done.set()
        channel.close()
        thread.join(timeout=3)
        self.assertEqual(len(received), 200, msg=f"收到 {len(received)} 帧")
        self.assertEqual(received[0], "data: 0\n\n")
