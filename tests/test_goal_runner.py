# -*- coding: utf-8 -*-
"""目标驱动的续跑：取消必须生效、轮数有上限、paused/done 不触发。

关键约束：续跑判定必须同时看目标状态和取消位——只看目标状态时，
用户点「停止」后运行器仍会以约 90 轮/秒空转（起一轮 → 开头被取消 → 又续跑），
CPU 打满且事实流被灌爆。用真实 `MeshState` + 假 app 构造，不依赖模型。
"""
from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.mechanisms.live_state import LiveState  # noqa: E402
from agent.mechanisms.mesh import MeshState  # noqa: E402
from agent.shell.session.goal import AUTO_CONTINUE_PROMPT  # noqa: E402
from agent.shell.session.runner import (  # noqa: E402
    _MAX_AUTO_ROUNDS,
    SessionRunner,
)


class _FakeApp:
    """只提供 runner 需要的两样东西：live_state 与 store。"""

    def __init__(self, state: LiveState) -> None:
        self.live_state = state
        self.store = None


class _RunnerBase(unittest.TestCase):
    def _make(self, cid: str):
        state = LiveState()
        mesh = MeshState()
        runner = SessionRunner(
            app=_FakeApp(state),
            mesh=mesh,
            auto_continue=lambda c: bool(state.get_autonomy(c).get("enabled")),
            goal_row=state.get_goal,
        )
        rounds = {"n": 0}

        def _execute(c, text, attachments=None, resume=None, sender=None, from_queue=False, meta=None):
            rounds["n"] += 1
            time.sleep(0.005)

        runner._execute = _execute  # type: ignore[method-assign]
        mesh.try_begin_run(cid)      # 模拟已占位（runner 由 mesh 激活）
        return state, runner, rounds

    @staticmethod
    def _drive(runner: SessionRunner, cid: str) -> threading.Thread:
        thread = threading.Thread(target=runner._run_loop, args=(cid, "开始"), daemon=True)
        thread.start()
        return thread


class ContinuationTextTest(_RunnerBase):
    """`_next_continuation_text` 的判定表（不启线程，直接问）。"""

    def test_goal_absent_falls_back_to_autonomy_switch(self) -> None:
        state, runner, _ = self._make("goal-text-0001")
        cid = "goal-text-0001"
        self.assertEqual(runner._next_continuation_text(cid), "")
        state.set_autonomy(cid, True)
        self.assertEqual(runner._next_continuation_text(cid), AUTO_CONTINUE_PROMPT)

    def test_active_goal_wins_over_hardcoded_prompt(self) -> None:
        state, runner, _ = self._make("goal-text-0002")
        cid = "goal-text-0002"
        state.set_autonomy(cid, True)          # 自主开关开着也不该用兜底文案
        state.set_goal(cid, "把登录页改成深色主题")
        self.assertEqual(runner._next_continuation_text(cid), "把登录页改成深色主题")

    def test_paused_and_done_stop_even_when_autonomy_on(self) -> None:
        """目标说了算：暂停/达成后不能再被自主开关顶回去。"""
        state, runner, _ = self._make("goal-text-0003")
        cid = "goal-text-0003"
        state.set_autonomy(cid, True)
        state.set_goal(cid, "目标X")
        state.update_goal(cid, status="paused")
        self.assertEqual(runner._next_continuation_text(cid), "")
        state.update_goal(cid, status="done")
        self.assertEqual(runner._next_continuation_text(cid), "")


class CancelTest(_RunnerBase):
    def test_cancel_stops_goal_continuation(self) -> None:
        """取消后必须停 —— 不判取消位就是死循环。"""
        cid = "goal-cancel-0001"
        state, runner, rounds = self._make(cid)
        state.set_goal(cid, "持续推进直到我说停")
        thread = self._drive(runner, cid)
        # 等它真的自动跑起来几轮
        deadline = time.time() + 3.0
        while rounds["n"] < 3 and time.time() < deadline:
            time.sleep(0.01)
        self.assertGreaterEqual(rounds["n"], 3, "目标未驱动续跑，用例前提不成立")
        runner.request_cancel(cid)
        thread.join(timeout=3.0)
        self.assertFalse(thread.is_alive(), "取消后运行器仍在续跑")
        n_after = rounds["n"]
        time.sleep(0.3)
        self.assertEqual(rounds["n"], n_after, "取消之后还在起新轮次")

    def test_auto_rounds_are_capped(self) -> None:
        """目标写歪时不能无限烧下去。"""
        cid = "goal-cap-0001"
        state, runner, rounds = self._make(cid)
        state.set_goal(cid, "持续推进")
        state.note_goal_round = lambda c: 0  # type: ignore[method-assign]
        thread = self._drive(runner, cid)
        thread.join(timeout=20.0)
        self.assertFalse(thread.is_alive(), "达到上限后 runner 未退出")
        self.assertLessEqual(rounds["n"], _MAX_AUTO_ROUNDS + 1)

    def test_goal_rounds_counter_advances(self) -> None:
        """界面要显示"已自动推进 N 轮"，计数必须真的在涨。"""
        cid = "goal-count-0001"
        state, runner, rounds = self._make(cid)
        state.set_goal(cid, "持续推进")
        thread = self._drive(runner, cid)
        deadline = time.time() + 3.0
        while rounds["n"] < 3 and time.time() < deadline:
            time.sleep(0.01)
        runner.request_cancel(cid)
        thread.join(timeout=3.0)
        self.assertGreaterEqual(state.get_goal(cid)["rounds"], 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
