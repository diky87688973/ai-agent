# -*- coding: utf-8 -*-
"""工具返回图片：read_image → ToolResult.attachments → 模型可见的 image_url 块。

链路有三段，测试也按段拆：

1. 工具侧 —— `read_image` 把文件读成附件，报出的摘要里不带 base64；
2. 管道侧 —— `ToolPipeline` 把返回值上的附件搬进结果信封；
3. 投影侧 —— `SessionLogView` 把附件翻成 `tool` 消息里的多模态 content。

第 3 段是关键：`tool` 消息的 content 曾经只能是字符串，模型因此永远看不到
工具给的图。测试锁的就是"它现在是数组、且图在里面"。
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

from agent.capabilities.builtin import image_tool  # noqa: E402
from agent.capabilities.registry import ToolRegistry  # noqa: E402
from agent.core.context import SERVICE_STORE  # noqa: E402
from agent.core.events import Event  # noqa: E402
from agent.core.image_embed import (  # noqa: E402
    build_tool_parts,
    describe_image,
    strip_attachment_meta,
    strip_old_images,
)
from agent.core.input_attachments import attachment_id  # noqa: E402
from agent.core.session_log import _tool_content  # noqa: E402
from agent.core.tool_call import ToolCallRequest, ToolPipeline, ToolResult  # noqa: E402


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


def _img_blocks(content) -> int:
    if not isinstance(content, list):
        return 0
    return sum(1 for p in content
               if isinstance(p, dict) and p.get("type") == "image_url")


class DescribeImageTest(unittest.TestCase):
    """尺寸解析不依赖 Pillow —— 它是可选依赖，报尺寸是基本功能。"""

    def test_png_size(self) -> None:
        mime, w, h = describe_image(_png(37, 23))
        self.assertEqual((mime, w, h), ("image/png", 37, 23))

    def test_gif_size(self) -> None:
        data = b"GIF89a" + struct.pack("<HH", 12, 34) + b"\x00" * 8
        mime, w, h = describe_image(data)
        self.assertEqual((mime, w, h), ("image/gif", 12, 34))

    def test_unknown_bytes_report_no_mime(self) -> None:
        """非图片内容：报空 mime、尺寸 0，不抛。

        空 mime 是"这不是图片"的信号 —— 调用方据此拒绝。
        若这里回落到声明的 MIME（例如文件名给的 image/png），
        一个改了扩展名的文本文件就会被当成图片发出去。
        """
        mime, w, h = describe_image(b"not an image at all", "image/png")
        self.assertEqual(mime, "")
        self.assertEqual((w, h), (0, 0))


class BuildToolPartsTest(unittest.TestCase):
    """工具附件 → 块 + 超限说明（工具侧的正文不该被占位文字污染）。"""

    def test_parts_and_no_note_within_budget(self) -> None:
        att = [{"mime": "image/png", "data_base64": base64.b64encode(_png(4, 4)).decode()}]
        parts, note = build_tool_parts(att)
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0]["type"], "image_url")
        self.assertTrue(parts[0]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(note, "")

    def test_over_budget_reports_note(self) -> None:
        """超预算不能静默丢 —— 工具得能告诉模型"有图但没带上"。"""
        att = [{"mime": "image/png", "data_base64": base64.b64encode(_png(40, 40)).decode()}]
        parts, note = build_tool_parts(att, max_bytes=16)
        self.assertEqual(parts, [])
        self.assertIn("体积超限", note)


class ToolContentTest(unittest.TestCase):
    """工具消息 content 的三态：无图 / 有图 / 只有图。"""

    def test_no_attachments_keeps_string(self) -> None:
        """没图时保持字符串：多模态数组会让请求体无谓变大，也改变既有形态。"""
        self.assertEqual(_tool_content("done", None), "done")
        self.assertEqual(_tool_content("done", []), "done")

    def test_with_image_becomes_array(self) -> None:
        att = [{"mime": "image/png", "data_base64": base64.b64encode(_png(4, 4)).decode()}]
        content = _tool_content('{"path": "a.png"}', att)
        self.assertIsInstance(content, list)
        self.assertEqual(content[0]["type"], "text")
        self.assertIn("a.png", content[0]["text"])
        self.assertEqual(_img_blocks(content), 1)

    def test_empty_text_with_image_gets_placeholder(self) -> None:
        """空正文 + 有图：补一句说明，而不是发一个只有图片的 content。"""
        att = [{"mime": "image/png", "data_base64": base64.b64encode(_png(4, 4)).decode()}]
        content = _tool_content("", att)
        self.assertIsInstance(content, list)
        self.assertTrue(content[0]["text"])


class PipelineCarriesAttachmentsTest(unittest.TestCase):
    """管道把返回值上的附件搬进结果信封，工具不必自己知道 call_id。"""

    def _pipeline_with(self, plugin) -> ToolPipeline:
        registry = ToolRegistry()
        registry.register(plugin)
        return ToolPipeline(), registry

    def test_attachments_survive_pipeline(self) -> None:
        class _Tool(image_tool.ImageReadTool):
            def execute(self, arguments):
                return ToolResult.attach({"ok": True}, [{"mime": "image/png", "data_base64": "AA"}])

        pipeline, registry = self._pipeline_with(_Tool())
        result = pipeline.execute(registry, ToolCallRequest(call_id="c1", name="read_image"), None)
        self.assertTrue(result.ok)
        self.assertEqual(len(result.attachments), 1)
        self.assertEqual(result.call_id, "c1", msg="管道负责填 call_id")

    def test_plain_return_has_no_attachments(self) -> None:
        """普通返回值（dict / 字符串）不该凭空多出附件字段。"""

        class _Plain(image_tool.ImageReadTool):
            def execute(self, arguments):
                return {"ok": True}

        pipeline, registry = self._pipeline_with(_Plain())
        result = pipeline.execute(registry, ToolCallRequest(call_id="c2", name="read_image"), None)
        self.assertTrue(result.ok)
        self.assertEqual(result.attachments, [])


class ReadImageToolTest(unittest.TestCase):
    """工具本体：成功给附件，失败给结构化错误。"""

    def setUp(self) -> None:
        self.tmp = Path(__file__).resolve().parent / "_tmp_image_tool"
        self.tmp.mkdir(exist_ok=True)
        self.tool = image_tool.ImageReadTool()

    def tearDown(self) -> None:
        for p in self.tmp.glob("*"):
            p.unlink()
        self.tmp.rmdir()

    def test_reads_png_and_summarizes(self) -> None:
        path = self.tmp / "shot.png"
        path.write_bytes(_png(120, 60))
        result = self.tool.execute({"path": str(path)})
        self.assertEqual(result.data["width"], 120)
        self.assertEqual(result.data["height"], 60)
        self.assertEqual(result.data["format"], "image/png")
        self.assertTrue(Path(result.data["path"]).is_absolute())
        self.assertEqual(len(result.attachments), 1)
        # 摘要里不能带 base64：它会进上下文，几十万字符只增加体积
        self.assertNotIn("data_base64", result.data)
        self.assertLess(len(str(result.data)), 500)

    def test_default_keeps_original_size(self) -> None:
        """默认不缩放：按图定位坐标的场景不能悄悄改尺寸。"""
        path = self.tmp / "full.png"
        path.write_bytes(_png(1200, 700))
        result = self.tool.execute({"path": str(path)})
        self.assertFalse(result.data["shrunk"])
        self.assertEqual((result.data["width"], result.data["height"]), (1200, 700))
        self.assertEqual((result.data["sent_width"], result.data["sent_height"]), (1200, 700))
        self.assertEqual(result.data["scale"], 1.0)

    def test_explicit_max_side_reports_scale(self) -> None:
        """显式缩放时必须回报换算比例 —— 否则模型按图上像素操作会全错。"""
        path = self.tmp / "big.png"
        path.write_bytes(_png(1200, 700))
        result = self.tool.execute({"path": str(path), "max_side": 600})
        self.assertTrue(result.data["shrunk"])
        self.assertEqual((result.data["width"], result.data["height"]), (1200, 700))
        self.assertEqual(result.data["sent_width"], 600)
        self.assertEqual(result.data["sent_height"], 350)
        self.assertAlmostEqual(result.data["scale"], 2.0, places=3)
        self.assertIn("缩到", result.data["note"])

    def test_projection_keeps_tool_chosen_size(self) -> None:
        """进模型的那一份不再二次缩放：摘要里的实发尺寸就是模型看到的尺寸。"""
        path = self.tmp / "full.png"
        path.write_bytes(_png(1200, 700))
        result = self.tool.execute({"path": str(path)})
        content = _tool_content("summary", result.attachments)
        url = content[1]["image_url"]["url"]
        raw = base64.b64decode(url.split(",", 1)[1])
        _mime, w, h = describe_image(raw)
        self.assertEqual((w, h), (result.data["sent_width"], result.data["sent_height"]))
        self.assertEqual((w, h), (1200, 700))

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            self.tool.execute({"path": str(self.tmp / "nope.png")})

    def test_non_image_raises(self) -> None:
        """按内容判定：改了扩展名的文本文件不该被当成图片发出去。"""
        path = self.tmp / "fake.png"
        path.write_bytes(b"this is plain text, not a png")
        with self.assertRaises(ValueError):
            self.tool.execute({"path": str(path)})

    def test_empty_path_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.tool.execute({"path": "   "})

    def test_empty_file_raises(self) -> None:
        path = self.tmp / "empty.png"
        path.write_bytes(b"")
        with self.assertRaises(ValueError):
            self.tool.execute({"path": str(path)})


class StripProtectsToolImagesTest(unittest.TestCase):
    """工具图受总量闸管，但不按"最近几轮"的窗口剥。

    这些用例都显式传窗口参数；不传时按默认 1 轮 / 8 张，旧图会被换成占位。
    """

    def _tool_msg(self, n_images: int = 1):
        content = [{"type": "text", "text": "图片"}]
        content += [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}}
                    for _ in range(n_images)]
        return {"role": "tool", "tool_call_id": "c1", "content": content}

    def _user_msg(self, text: str, n_images: int = 1):
        content = [{"type": "text", "text": text}]
        content += [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}}
                    for _ in range(n_images)]
        return {"role": "user", "content": content}

    def test_tool_image_with_no_user_images_survives(self) -> None:
        """纯工具图（用户没发图）必须留着 —— 否则模型永远看不到工具读的图。"""
        msgs = [{"role": "user", "content": "看看这张图"}, self._tool_msg()]
        out, stripped = strip_old_images(msgs, keep_turns=1, max_images=10)
        self.assertEqual(stripped, 0)
        self.assertEqual(_img_blocks(out[1]["content"]), 1)

    def test_tool_image_counts_toward_max(self) -> None:
        """工具图占总量配额：不限量会让请求体随会话线性膨胀。"""
        msgs = [self._user_msg("新轮"), self._tool_msg(2)]
        out, stripped = strip_old_images(msgs, keep_turns=3, max_images=1)
        self.assertEqual(stripped, 2)
        total = sum(_img_blocks(m.get("content")) for m in out)
        self.assertEqual(total, 1)

    def test_newest_user_image_wins_over_older_tool_image(self) -> None:
        """配额只够一张时按时间先进先出，较新的用户图保留。"""
        msgs = [self._tool_msg(), self._user_msg("刚发的图")]
        out, _ = strip_old_images(msgs, keep_turns=3, max_images=1)
        self.assertEqual(_img_blocks(out[0]["content"]), 0, msg="较老的工具图应先剥")
        self.assertEqual(_img_blocks(out[1]["content"]), 1)

    def test_newest_tool_image_wins_over_older_user_image(self) -> None:
        """较新的工具图同样按先进先出保留，不因是工具图就被压低优先级。"""
        msgs = [self._user_msg("老图"), self._tool_msg()]
        out, _ = strip_old_images(msgs, keep_turns=3, max_images=1)
        self.assertEqual(_img_blocks(out[0]["content"]), 0, msg="较老的用户图应先剥")
        self.assertEqual(_img_blocks(out[1]["content"]), 1, msg="较新的工具图应保留")

    def test_fifo_keeps_new_tool_image_and_drops_oldest_user_image(self) -> None:
        """9 张用户图 + 刚读的工具图：最新的工具图保留，最老的用户图被剥。"""
        first, _ = strip_old_images([self._user_msg("九张", 9)], keep_turns=1, max_images=8)
        out, stripped = strip_old_images(first + [self._tool_msg()],
                                         keep_turns=1, max_images=8)
        self.assertEqual(stripped, 1)
        self.assertEqual(_img_blocks(out[0]["content"]), 7)
        self.assertEqual(_img_blocks(out[1]["content"]), 1)
    def test_old_tool_image_survives_turn_window(self) -> None:
        """轮次窗口不剥工具图：老工具图不是"重复内联的老用户图"，
        它只由总量闸管。窗口只影响用户图。"""
        msgs = [self._tool_msg(), self._user_msg("新轮"), self._user_msg("更新轮")]
        out, _ = strip_old_images(msgs, keep_turns=1, max_images=10)
        self.assertEqual(_img_blocks(out[0]["content"]), 1, msg="配额够就该留着")

    def test_excess_tool_image_is_stripped(self) -> None:
        """超出总量闸的老工具图要被剥掉：不限量会随会话线性膨胀。"""
        msgs = [self._tool_msg(), self._user_msg("新轮"), self._user_msg("更新轮")]
        out, stripped = strip_old_images(msgs, keep_turns=3, max_images=2)
        self.assertEqual(stripped, 1)
        self.assertEqual(_img_blocks(out[0]["content"]), 0, msg="最老的工具图先让位")
        self.assertEqual(_img_blocks(out[1]["content"]), 1)
        self.assertEqual(_img_blocks(out[2]["content"]), 1)



class AttachmentReferenceTest(unittest.TestCase):
    def test_placeholder_has_attachment_reference_and_request_cleans_it(self) -> None:
        png = base64.b64encode(_png(2, 2)).decode()
        ident = attachment_id(png, 0)
        msgs = [
            {"role": "user", "content": [
                {"type": "text", "text": "旧图"},
                {"type": "image_url", "attachment_id": ident,
                 "image_url": {"url": f"data:image/png;base64,{png}"}}]},
            {"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{png}"}}]},
        ]
        out, stripped = strip_old_images(msgs, keep_turns=1)
        self.assertEqual(stripped, 1)
        text = " ".join(str(p.get("text") or "") for p in out[0]["content"]
                        if isinstance(p, dict) and p.get("type") == "text")
        self.assertIn(ident, text)
        self.assertIn("read_image", text)
        cleaned = strip_attachment_meta(out)
        for part in cleaned[0]["content"]:
            if isinstance(part, dict):
                self.assertNotIn("attachment_id", part)

    def test_read_image_rejects_repeated_attachment_in_same_turn(self) -> None:
        from agent.core.context import AppContext
        from agent.core.tool_call import ToolPipeline

        png = _png(3, 2)
        data = base64.b64encode(png).decode()
        ident = attachment_id(data, 0)
        events = [
            Event("turn_started", {}),
            Event("input_claimed", {"attachments": [{
                "attachment_id": ident, "mime": "image/png",
                "data_base64": data,
            }]}),
            Event("tool_done", {"name": "read_image",
                                "data": {"attachment_id": ident}}),
        ]

        class _Store:
            def load(self, _cid):
                return events

        class _App:
            def __init__(self):
                self.app = AppContext()
                self.app.register(SERVICE_STORE, _Store())

            def has(self, name):
                return name == SERVICE_STORE

            def get(self, name):
                return self.app.get(name)

        class _Ctx:
            conversation_id = "cid-12345678"
            app = _App()
            session = None

        registry = ToolRegistry()
        registry.register(image_tool.ImageReadTool())
        result = ToolPipeline().execute(
            registry,
            ToolCallRequest(call_id="c2", name="read_image",
                            arguments={"attachment_id": ident}),
            _Ctx(),
        )
        self.assertFalse(result.ok)
        self.assertIn("已读取", result.error)

    def test_read_image_accepts_attachment_id_from_current_store(self) -> None:
        from agent.core.context import AppContext
        from agent.core.tool_call import ToolPipeline

        png = _png(3, 2)
        ident = attachment_id(base64.b64encode(png).decode(), 0)
        event = Event("input_claimed", {"attachments": [{
            "attachment_id": ident, "mime": "image/png",
            "data_base64": base64.b64encode(png).decode(),
        }]})

        class _Store:
            def load(self, _cid):
                return [event]

        class _App:
            def __init__(self):
                self.app = AppContext()
                self.app.register(SERVICE_STORE, _Store())

            def has(self, name):
                return name == SERVICE_STORE

            def get(self, name):
                return self.app.get(name)

        class _Ctx:
            conversation_id = "cid-12345678"
            app = _App()
            session = None

        pipeline = ToolPipeline()
        registry = ToolRegistry()
        registry.register(image_tool.ImageReadTool())
        result = pipeline.execute(
            registry,
            ToolCallRequest(call_id="c1", name="read_image",
                            arguments={"attachment_id": ident}),
            _Ctx(),
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.data["attachment_id"], ident)
        self.assertEqual(len(result.attachments), 1)

if __name__ == "__main__":
    unittest.main()
