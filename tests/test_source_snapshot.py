# -*- coding: utf-8 -*-
"""收集只做一次：一趟装配里压缩与模型请求必须共用同一份注入源快照。

翻倍类故障的土壤就是"同一批来源被收集两遍、两遍都被装上" ——
这条测试把"只收集一次"和"数据变了要打招呼"两件事钉住。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.mechanisms.context_pipeline import (  # noqa: E402
    ContextPipeline,
    ContextSources,
    SourceMeta,
)


class CollectOncePerPassTest(unittest.TestCase):
    """注入源在一趟装配里只被收集一次。"""

    def setUp(self) -> None:
        self.calls = 0
        self.sources = ContextSources()

        def _source(cid: str):
            self.calls += 1
            return ["正文"]

        self.sources.add(_source, SourceMeta(key="demo", label="示例段"))
        self.pipe = ContextPipeline("c", sources=self.sources)

    def test_repeated_assembly_shares_one_snapshot(self) -> None:
        for _ in range(3):
            self.pipe.set_dialogue([{"role": "user", "content": "问"}])
        self.assertEqual(self.calls, 1, msg="同一趟里每次装配都重收集，会白烧磁盘且数字可能对不上")

    def test_bump_forces_recollection(self) -> None:
        self.pipe.set_dialogue([{"role": "user", "content": "问"}])
        before = self.calls
        self.sources.bump()
        self.pipe.set_dialogue([{"role": "user", "content": "问"}])
        self.assertEqual(self.calls, before + 1, msg="来源声明内容变了，装配侧必须重收集")

    def test_registering_a_source_bumps_by_itself(self) -> None:
        self.pipe.set_dialogue([{"role": "user", "content": "问"}])
        before = self.calls
        self.sources.add(lambda cid: ["第二段"], SourceMeta(key="demo2", label="第二段"))
        self.pipe.set_dialogue([{"role": "user", "content": "问"}])
        self.assertGreater(self.calls, before, msg="注册新来源也是内容变化")

    def test_explicit_refresh_always_recollects(self) -> None:
        self.pipe.set_dialogue([{"role": "user", "content": "问"}])
        before = self.calls
        self.pipe.refresh_sources()
        self.assertEqual(self.calls, before + 1)


class SegmentsStayAlignedTest(unittest.TestCase):
    """段表与数量表必须逐条对齐（错位会让浮层显示别人的数字）。"""

    def test_alignment_after_repeated_assembly(self) -> None:
        sources = ContextSources()
        sources.add(lambda cid: ["a", "b"],
                    SourceMeta(key="two", label="两条", count=lambda cid: 7))
        sources.add(lambda cid: ["c"], SourceMeta(key="one", label="一条"))
        pipe = ContextPipeline("c", sources=sources)
        for _ in range(3):
            pipe.set_dialogue([{"role": "user", "content": "问"}])
        rows = [r for r in pipe.segment_tokens() if str(r["key"]).startswith("plugin:")]
        self.assertEqual([r["label"] for r in rows], ["两条", "两条", "一条"])
        self.assertEqual([r["count"] for r in rows], [7, 1, 1])

    def test_repeated_assembly_does_not_grow_rows(self) -> None:
        sources = ContextSources()
        sources.add(lambda cid: ["a"], SourceMeta(key="one", label="一条"))
        pipe = ContextPipeline("c", sources=sources)
        counts = []
        for _ in range(4):
            pipe.set_dialogue([{"role": "user", "content": "问"}])
            counts.append(len([r for r in pipe.segment_tokens()
                               if str(r["key"]).startswith("plugin:")]))
        self.assertEqual(counts, [1, 1, 1, 1], msg="重复装配把段落装了两遍（翻倍类故障）")


if __name__ == "__main__":
    unittest.main()
