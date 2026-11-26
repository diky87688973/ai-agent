# -*- coding: utf-8 -*-
"""Edge 多音字辅助的用例：从 ai_cosplay 迁到 tts 插件后仍须逐条成立。"""
from __future__ import annotations

import unittest

from plugins.tts import pinyin


class PolyphoneTest(unittest.TestCase):
    def test_hang_and_zhong(self) -> None:
        cases = {
            "36行。": "36 háng。",
            "第36行。": "第36 háng。",
            "行36。": "háng 36。",
            "36行代码。": "36 háng 代码。",
            "一行字。": "一 háng 字。",
            "一行人。": "一行人。",
            "一行人员。": "一行人员。",
            "一行3人。": "一行3人。",
            "一行 3 人。": "一行 3 人。",
            "一行数十人。": "一行数十人。",
            "一行三人。": "一行三人。",
            "一行几人。": "一行几人。",
            "一行几个人。": "一行几个人。",
            "一行十余人。": "一行十余人。",
            "一行N人。": "一行N人。",
            "银行。": "银行。",
            "执行。": "执行。",
            "请换行后重跑。": "请换 háng 后 chóng 跑。",
            "行内显示图片。": "háng 内显示图片。",
            "支持行内代码。": "支持 háng 内代码。",
            "数行代码。": "数 háng 代码。",
            "数行都超了。": "数 háng 都超了。",
            "函数行为不变。": "函数行为不变。",
            "这一段折行了。": "这一段折 háng 了。",
            "行内折行都影响阅读。": "háng 内折 háng 都影响阅读。",
            "这批数据需要去重。": "这批数据需要去 chóng。",
            "银行正在执行重要任务。": "银行正在执行重要任务。",
            "重绘一下界面。": "chóng 绘一下界面。",
            "双重校验。": "双 chóng 校验。",
            "重叠了。": "chóng 叠了。",
            "把这句话重新说一遍。": "把这句话 chóng 新说一遍。",
            "这个方案很重要。": "这个方案很重要。",
            "严重程度不同。": "严重程度不同。",
            "请尊重对方。": "请尊重对方。",
            "重量是多少。": "重量是多少。",
            "这个箱子很重。": "这个箱子很重。",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(pinyin.apply(raw), expected)

    def test_idempotent_on_plain_text(self) -> None:
        self.assertEqual(pinyin.apply("今天天气很好。"), "今天天气很好。")
        self.assertEqual(pinyin.apply(""), "")


if __name__ == "__main__":
    unittest.main()
