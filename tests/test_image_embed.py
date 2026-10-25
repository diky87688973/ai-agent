# -*- coding: utf-8 -*-
"""视觉嵌图：本地缩放与请求体预算。

图片以原样内联进请求体，单图尺寸与请求体总量由本模块负责：
不缩，请求体体积明显偏大（随后仍会被缩小）；不设预算，多张截图会把
48 MiB 请求体顶爆，症状是整轮请求被拒而不是"这张图看不到"。
"""
from __future__ import annotations

import base64
import struct
import sys
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.core.image_embed import (  # noqa: E402
    build_embed_parts,
    placeholder_text,
    shrink_image,
)


def _png(w: int, h: int, rgb=(200, 60, 60)) -> bytes:
    rows = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(
            ">I", zlib.crc32(body) & 0xFFFFFFFF
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, 6))
        + chunk(b"IEND", b"")
    )

def _dims(data: bytes):
    return struct.unpack(">II", data[16:24]) if data[:4] == b"\x89PNG" else None

class ShrinkImageTest(unittest.TestCase):

    def test_small_image_is_left_alone(self) -> None:
        """本来就小的图不该被重编码 —— 白白损失质量。"""
        raw = _png(120, 40)
        out, mime = shrink_image(raw)
        self.assertEqual(out, raw)
        self.assertEqual(mime, "image/png")

    def test_large_image_is_shrunk_to_max_side(self) -> None:
        out, _mime = shrink_image(_png(2000, 1200))
        self.assertEqual(_dims(out), (800, 480),
                         msg="长边应缩到 800，且保持宽高比")

    def test_extreme_aspect_ratio_survives(self) -> None:
        """横幅截图（本仓的真实用例：492×42 的工具条）不该被搞坏。"""
        out, _mime = shrink_image(_png(492, 42))
        self.assertEqual(_dims(out), (492, 42))

    def test_garbage_bytes_are_returned_as_is(self) -> None:
        """判据：缩放是优化，解不开就原样发，不能让图片发不出去。"""
        out, _mime = shrink_image(b"not an image at all")
        self.assertEqual(out, b"not an image at all")

    def test_mime_is_detected_from_content(self) -> None:
        """网关以文件实际内容判格式，本模块同样按内容判。"""
        _out, mime = shrink_image(_png(10, 10), declared_mime="image/jpeg")
        self.assertEqual(mime, "image/png")

class EmbedBudgetTest(unittest.TestCase):

    def test_over_budget_becomes_skipped_not_dropped(self) -> None:
        """超预算必须可察觉：进 skipped，由调用方转占位。"""
        big = base64.b64encode(_png(900, 900)).decode()
        parts, skipped = build_embed_parts(
            [{"mime": "image/png", "data_base64": big}], max_bytes=100
        )
        self.assertEqual(parts, [])
        self.assertEqual(skipped, ["0"])
        self.assertIn("图片", placeholder_text(skipped))

    def test_within_budget_is_embedded(self) -> None:
        big = base64.b64encode(_png(300, 300)).decode()
        parts, skipped = build_embed_parts([{"mime": "image/png", "data_base64": big}])
        self.assertEqual(len(parts), 1)
        self.assertEqual(skipped, [])
        self.assertEqual(parts[0]["type"], "image_url")
        self.assertTrue(parts[0]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_broken_base64_is_skipped(self) -> None:
        parts, skipped = build_embed_parts([{"mime": "image/png", "data_base64": "!!!!"}])
        self.assertEqual(parts, [])
        self.assertEqual(len(skipped), 1)

class DerivedMessageShrinksTest(unittest.TestCase):

    def test_derived_message_carries_a_shrunk_image(self) -> None:
        """端到端：进事实的是原图，派生给模型的是缩过的。"""
        from agent.core.events import Event
        from agent.core.session_log import SessionLog

        log = SessionLog()
        log.append([Event("input_claimed", {
            "content": "看图",
            "attachments": [{"mime": "image/png",
                             "data_base64": base64.b64encode(_png(2000, 1200)).decode()}],
        })])
        msgs = log.derive_request_messages()
        url = msgs[0]["content"][1]["image_url"]["url"]
        raw = base64.b64decode(url.split(";base64,", 1)[1])
        self.assertEqual(_dims(raw), (800, 480))

    def test_derived_message_keeps_plain_text_shape_when_no_attachment(self) -> None:
        from agent.core.events import Event
        from agent.core.session_log import SessionLog

        log = SessionLog()
        log.append([Event("input_claimed", {"content": "只有文字"})])
        msgs = log.derive_request_messages()
        self.assertEqual(msgs[0]["content"], "只有文字",
                         msg="无附件时不该把 content 包成数组")

if __name__ == "__main__":
    unittest.main()
