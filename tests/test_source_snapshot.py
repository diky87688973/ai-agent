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

from agent.core.chain import run_chain  # noqa: E402
from agent.core.module import ModuleBase  # noqa: E402
from agent.core.outcome import Outcome  # noqa: E402
from agent.core.ports import Ports  # noqa: E402
from agent.core.session_log import SessionLog  # noqa: E402
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
        self.assertEqual(self.calls, 1, msg="同一趟里每次装配都重收集，会重复读盘且数字可能对不上")

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

    def test_pass_builds_at_start_and_drops_at_end(self) -> None:
        self.pipe.begin_pass()
        self.assertEqual(self.calls, 1, msg="一趟开始就要收集，不能拖到第一次装配")
        self.pipe.set_dialogue([{"role": "user", "content": "问"}])
        self.pipe.set_dialogue([{"role": "user", "content": "再问"}])
        self.assertEqual(self.calls, 1, msg="本趟内装配复用开始时建好的快照")
        self.assertIsNotNone(self.pipe._sources_snapshot)
        self.pipe.end_pass()
        self.assertIsNone(self.pipe._sources_snapshot, msg="一趟结束必须丢掉快照，下一趟不来也不能留着")
        self.assertEqual(
            [r for r in self.pipe.segment_tokens() if str(r["key"]).startswith("plugin:")],
            [],
            msg="从快照装上的插件段要随快照一起卸掉",
        )

    def test_disposing_a_source_bumps_version(self) -> None:
        self.pipe.set_dialogue([{"role": "user", "content": "问"}])
        before = self.calls
        dispose = self.sources.add(lambda cid: ["临时"], SourceMeta(key="tmp", label="临时"))
        dispose()
        self.pipe.set_dialogue([{"role": "user", "content": "问"}])
        self.assertGreater(self.calls, before, msg="卸下来源也是内容变化，快照不能继续带着它")


class _Touch(ModuleBase):
    """一趟里装一次对话。压缩模块和模型模块都是这个形状。"""

    name = "touch"

    def __init__(self, pipe: ContextPipeline) -> None:
        self.context_pass = pipe

    def execute(self, ports):
        self.context_pass.set_dialogue([{"role": "user", "content": "问"}])
        if False:
            yield None
        return Outcome.ok()


class _Halt(ModuleBase):
    """装配一次后立刻停掉本趟。"""

    name = "halt"

    def __init__(self, pipe: ContextPipeline) -> None:
        self.context_pass = pipe

    def execute(self, ports):
        self.context_pass.set_dialogue([{"role": "user", "content": "问"}])
        if False:
            yield None
        return Outcome.halt("停")


class ChainPassDropsSnapshotTest(unittest.TestCase):
    """一趟开始时收集，结束时丢掉；同一趟里多次装配只收集一次。"""

    def _pipe(self) -> tuple:
        calls = {"n": 0}
        sources = ContextSources()

        def _source(cid: str):
            calls["n"] += 1
            return ["正文"]

        sources.add(_source, SourceMeta(key="demo", label="示例段"))
        pipe = ContextPipeline("c", sources=sources)
        return pipe, calls

    def test_one_pass_collects_once_and_drops_when_the_pass_ends(self) -> None:
        pipe, calls = self._pipe()
        ports = Ports(emit=lambda event: None, log=SessionLog())
        modules = [_Touch(pipe), _Touch(pipe)]
        run_chain(modules, ports)
        self.assertEqual(calls["n"], 1, msg="同一趟里压缩和模型要共用开始时的那一份")
        self.assertIsNone(pipe._sources_snapshot, msg="趟结束快照必须已经丢掉")
        run_chain(modules, ports)
        self.assertEqual(calls["n"], 2, msg="下一趟开始重新收集")
        self.assertIsNone(pipe._sources_snapshot)

    def test_halted_pass_still_drops_the_snapshot(self) -> None:
        pipe, calls = self._pipe()
        ports = Ports(emit=lambda event: None, log=SessionLog())
        run_chain([_Halt(pipe), _Touch(pipe)], ports)
        self.assertEqual(calls["n"], 1)
        self.assertIsNone(pipe._sources_snapshot, msg="中途停掉也不能把快照留在会话上")


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
        self.assertEqual([r["label"] for r in rows], ["两条", "一条"])
        self.assertEqual([r["count"] for r in rows], [7, 1])

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
