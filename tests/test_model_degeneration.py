# -*- coding: utf-8 -*-
"""退化推理的判定与收口：无正文、无工具调用、推理高度自重复时停掉本回合。

判定放在模型模块收尾，用既有的 `Outcome.halt`，不新增控制状态。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.core.model_call import StreamDelta  # noqa: E402
from agent.core.modules import model_mod  # noqa: E402
from agent.core.modules.model_mod import (  # noqa: E402
    DEGENERATE_MIN_CHARS,
    ModelModule,
    _degenerate,
)
from agent.core.ports import LogicalRequest, Ports  # noqa: E402
from agent.core.session_log import SessionLog  # noqa: E402

#: 实测退化片段的结构：短周期短语在「（输出）」之间轮转。
CYCLE = "（输出）\n\n好。\n\n（输出）\n\n停。\n\n调用。\n\n执行。\n\n"


class _LoopModel:
    """只吐推理、不吐正文与工具调用。"""

    def name_for(self, _request) -> str:
        return "loop-model"

    def stream(self, _request):
        for _ in range(500):
            yield StreamDelta(kind="reasoning", text=CYCLE)
        yield StreamDelta(kind="usage", usage={"prompt_tokens": 900000,
                                               "completion_tokens": 16000})


class _NormalModel:
    def name_for(self, _request) -> str:
        return "normal-model"

    def stream(self, _request):
        yield StreamDelta(kind="reasoning", text="先读配置，再核对两个调用点。")
        yield StreamDelta(kind="text", text="结论：没有漂移。")


def _ports(events, model) -> Ports:
    return Ports(emit=events.append, log=SessionLog(),
                 conversation_id="degenerate-cid", model=model)


def _drain(generator):
    try:
        while True:
            next(generator)
    except StopIteration as exc:
        return exc.value
    raise AssertionError("generator did not finish")


def _run_execute(model):
    events = []
    module = ModelModule()
    request = LogicalRequest(messages=[], tools=[])
    with mock.patch.object(model_mod, "tail_expects_model", return_value=True), \
            mock.patch.object(ModelModule, "_build_request",
                              return_value=(request, [], None)):
        outcome = _drain(module.execute(_ports(events, model)))
    return outcome, events


class DegeneratePredicateTest(unittest.TestCase):
    def test_periodic_loop_is_detected(self) -> None:
        self.assertTrue(_degenerate(CYCLE * 800, [], []))

    def test_varied_reasoning_is_kept(self) -> None:
        """去重字符占比高的正常推理不得被误判。"""

        body = "".join(chr(0x4E00 + index % 800) for index in range(3000))
        self.assertFalse(_degenerate(body, [], []))

    def test_tool_call_clears_the_verdict(self) -> None:
        self.assertFalse(_degenerate(CYCLE * 800, [], [object()]))

    def test_visible_text_clears_the_verdict(self) -> None:
        self.assertFalse(_degenerate(CYCLE * 800, ["有结论"], []))

    def test_short_loop_stays_below_the_floor(self) -> None:
        body = (CYCLE * 800)[: DEGENERATE_MIN_CHARS - 1]
        self.assertFalse(_degenerate(body, [], []))


class DegenerateRoundTest(unittest.TestCase):
    def test_degenerate_round_halts_without_writing_message(self) -> None:
        outcome, events = _run_execute(_LoopModel())
        self.assertEqual(outcome.status, "halt")
        names = [getattr(event, "type", "") for event in events]
        self.assertIn("error", names)
        self.assertNotIn("model_message", names)

    def test_usage_travels_back_for_calibration(self) -> None:
        state = _drain(ModelModule()._stream(
            _ports([], _LoopModel()), _LoopModel(),
            LogicalRequest(messages=[], tools=[])))
        self.assertEqual(state["usage"]["prompt_tokens"], 900000)

    def test_normal_round_still_writes_message(self) -> None:
        outcome, events = _run_execute(_NormalModel())
        self.assertEqual(outcome.status, "ok")
        names = [getattr(event, "type", "") for event in events]
        self.assertIn("model_message", names)


if __name__ == "__main__":
    unittest.main()
