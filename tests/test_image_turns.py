# -*- coding: utf-8 -*-
"""图片按「最近几轮用户发言」进请求：轮数由配置控制，事实流不受影响。

判定口径是**轮**而不是**张**：一轮里发三张图算一轮。
被剥掉的图只从**发给模型的这一份**里消失，`.raw` 里的字节一个都不动 ——
所以历史回显、重新提问都还能拿到原图。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.core.image_embed import (  # noqa: E402
    KEEP_IMAGE_TURNS,
    MAX_EMBED_IMAGES,
    strip_old_images,
)


def _img_msg(text: str, n_images: int = 1):
    content = [{"type": "text", "text": text}]
    content += [{"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}}
                for _ in range(n_images)]
    return {"role": "user", "content": content}


def _count_images(messages) -> int:
    return sum(
        1 for m in messages
        if isinstance(m.get("content"), list)
        for p in m["content"]
        if isinstance(p, dict) and p.get("type") == "image_url"
    )


class StripByTurnTest(unittest.TestCase):
    """按轮保留，不是按张。"""

    def test_keeps_only_recent_turns(self) -> None:
        msgs = [_img_msg(f"第 {i} 轮") for i in range(1, 6)]      # 5 轮，每轮 1 张
        out, stripped = strip_old_images(msgs, keep_turns=3)
        self.assertEqual(stripped, 2, msg="前两轮的图应当被剥掉")
        self.assertEqual(_count_images(out), 3)
        texts = [p.get("text") for p in out[0]["content"]
                 if isinstance(p, dict) and p.get("type") == "text"]
        self.assertIn("第 1 轮", texts)
        self.assertTrue(any("原有 1 张" in str(t) for t in texts), msg=str(texts))

    def test_one_turn_with_three_images_counts_as_one_turn(self) -> None:
        """一轮三张 = 一轮；不该因为张数多就把这一轮挤掉。"""
        msgs = [_img_msg("老轮", 3), _img_msg("新轮", 3)]
        out, stripped = strip_old_images(msgs, keep_turns=1)
        self.assertEqual(stripped, 3, msg="只剥老轮那三张")
        self.assertEqual(_count_images(out), 3, msg="最近一轮的三张都要留着")

    def test_within_limit_is_untouched(self) -> None:
        msgs = [_img_msg("一"), _img_msg("二")]
        out, stripped = strip_old_images(msgs, keep_turns=3)
        self.assertEqual(stripped, 0)
        self.assertIs(out[0], msgs[0], msg="没超限时不该重建消息")

    def test_zero_turns_drops_every_image(self) -> None:
        msgs = [_img_msg("一"), _img_msg("二")]
        out, stripped = strip_old_images(msgs, keep_turns=0)
        self.assertEqual(stripped, 2)
        self.assertEqual(_count_images(out), 0)

    def test_negative_means_no_limit(self) -> None:
        msgs = [_img_msg(f"第 {i} 轮") for i in range(6)]
        out, stripped = strip_old_images(msgs, keep_turns=-1)
        self.assertEqual(stripped, 0)
        self.assertEqual(_count_images(out), 6)

    def test_text_only_messages_are_untouched(self) -> None:
        msgs = [{"role": "user", "content": "只有文字"},
                {"role": "assistant", "content": "回答"}]
        out, stripped = strip_old_images(msgs, keep_turns=0)
        self.assertEqual(stripped, 0)
        self.assertEqual(out, msgs)

    def test_default_is_three_turns(self) -> None:
        self.assertEqual(KEEP_IMAGE_TURNS, 3)

    def test_image_only_turn_keeps_a_placeholder(self) -> None:
        """被剥的那轮如果只有图没有字，占位不能是空串（空 content 会被 API 拒）。"""
        msgs = [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}}]},
            _img_msg("新轮")]
        out, stripped = strip_old_images(msgs, keep_turns=1)
        self.assertEqual(stripped, 1)
        self.assertTrue(str(out[0]["content"]).strip(), msg="不得留空 content")


class StripByTotalCapTest(unittest.TestCase):
    """轮数之外的第二道闸：总数上限，**最近一轮优先**。"""

    def test_cap_keeps_the_most_recent_turn_first(self) -> None:
        """五张的额度：最近一轮三张全保，剩两张给倒数第二轮，最老的一轮全舍。"""
        msgs = [_img_msg("第 1 轮", 3), _img_msg("第 2 轮", 3), _img_msg("第 3 轮", 3)]
        out, stripped = strip_old_images(msgs, keep_turns=3, max_images=5)
        self.assertEqual(stripped, 4)
        kept = [_count_images([m]) for m in out]
        self.assertEqual(kept, [0, 2, 3], msg="最后一轮全保、倒数第二轮保 2、最老的一轮全舍")

    def test_oldest_turn_is_dropped_whole_before_touching_newer(self) -> None:
        msgs = [_img_msg("第 1 轮", 2), _img_msg("第 2 轮", 2)]
        out, stripped = strip_old_images(msgs, keep_turns=3, max_images=2)
        self.assertEqual(stripped, 2)
        self.assertEqual([_count_images([m]) for m in out], [0, 2])

    def test_within_cap_touches_nothing(self) -> None:
        msgs = [_img_msg("一", 2), _img_msg("二", 2)]
        out, stripped = strip_old_images(msgs, keep_turns=3, max_images=10)
        self.assertEqual(stripped, 0)
        self.assertIs(out[0], msgs[0])

    def test_one_turn_over_the_cap_keeps_the_tail_of_that_turn(self) -> None:
        """一轮本身就超上限：留靠后的那几张（同一轮内后发的更可能是"这张图"）。"""
        msgs = [_img_msg("超量轮", 5)]
        out, stripped = strip_old_images(msgs, keep_turns=3, max_images=2)
        self.assertEqual(stripped, 3)
        self.assertEqual(_count_images([out[0]]), 2)

    def test_zero_cap_drops_everything(self) -> None:
        msgs = [_img_msg("一", 3)]
        out, stripped = strip_old_images(msgs, keep_turns=3, max_images=0)
        self.assertEqual(stripped, 3)
        self.assertEqual(_count_images(out), 0)

    def test_negative_cap_means_no_limit(self) -> None:
        msgs = [_img_msg("一", 4), _img_msg("二", 4)]
        out, stripped = strip_old_images(msgs, keep_turns=3, max_images=-1)
        self.assertEqual(stripped, 0)
        self.assertEqual(_count_images(out), 8)

    def test_cap_and_turns_apply_together(self) -> None:
        """轮数先裁掉窗口外，窗口内再按总量裁。"""
        msgs = [_img_msg("窗外", 2), _img_msg("第 2", 2), _img_msg("第 3", 2)]
        out, stripped = strip_old_images(msgs, keep_turns=2, max_images=3)
        self.assertEqual(_count_images(out), 3)
        self.assertEqual([_count_images([m]) for m in out], [0, 1, 2])

    def test_placeholder_counts_the_dropped_blocks(self) -> None:
        msgs = [_img_msg("老轮", 3)]
        out, _ = strip_old_images(msgs, keep_turns=3, max_images=1)
        text = " ".join(str(p.get("text") or "") for p in out[0]["content"]
                        if isinstance(p, dict))
        self.assertIn("原有 2 张", text)

    def test_default_cap_is_ten(self) -> None:
        self.assertEqual(MAX_EMBED_IMAGES, 10)

    def test_default_call_applies_both_limits(self) -> None:
        """默认调用（不传参）两道闸都生效。"""
        msgs = [_img_msg(f"第 {i} 轮", 4) for i in range(5)]
        out, _ = strip_old_images(msgs)
        self.assertEqual(_count_images(out), MAX_EMBED_IMAGES)
        self.assertEqual([_count_images([m]) for m in out], [0, 0, 2, 4, 4])


class ConfigWiringTest(unittest.TestCase):
    """配置项 `[context] image_turns` / `image_max` 一路到模型模块。"""

    def test_default_config_value(self) -> None:
        from agent.config import get_context

        cfg = get_context()
        self.assertEqual(cfg["image_turns"], 3)
        self.assertEqual(cfg["image_max"], 10)

    def test_module_receives_the_value(self) -> None:
        from agent.core.modules import ModelModule

        self.assertEqual(ModelModule()._image_turns, KEEP_IMAGE_TURNS)
        self.assertEqual(ModelModule(image_turns=7)._image_turns, 7)
        self.assertEqual(ModelModule(image_turns=-1)._image_turns, -1)
        self.assertEqual(ModelModule()._image_max, MAX_EMBED_IMAGES)
        self.assertEqual(ModelModule(image_max=4)._image_max, 4)
        self.assertEqual(ModelModule(image_max=-1)._image_max, -1)

    def test_app_carries_the_value(self) -> None:
        from agent.app import build_app

        app = build_app()
        self.assertEqual(app.image_turns, KEEP_IMAGE_TURNS)
        self.assertEqual(app.image_max, MAX_EMBED_IMAGES)
        self.assertIsInstance(app.image_turns, int)
        self.assertIsInstance(app.image_max, int)


if __name__ == "__main__":
    unittest.main()
