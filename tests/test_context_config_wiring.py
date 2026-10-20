# -*- coding: utf-8 -*-
"""守住"配置项必须真的传到管线"：生产装配路径逐项核对。

漏传的症状很隐蔽：配置能读出来、界面也显示，只有行为不对。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from tests.testkit import no_plugins  # noqa: E402


class ContextFactoryCarriesEveryContextSettingTest(unittest.TestCase):
    """`_default_context_factory` 必须把 [context] 的每一项都传给管线。"""

    def setUp(self) -> None:
        no_plugins(self)

    def test_factory_passes_every_pipeline_setting(self) -> None:
        import inspect

        from agent.app import build_app
        from agent.config import get_context
        from agent.mechanisms.context_pipeline import ContextPipeline

        app = build_app(provider=None)
        factory = app.context_factory
        self.assertIsNotNone(factory)
        src = inspect.getsource(factory)
        cfg = get_context()
        sig = inspect.signature(ContextPipeline.__init__).parameters
        # 管线构造参数里凡是 [context] 有的项，工厂都必须传。
        # `model_context_window` 不在其中：窗口是模型的属性，由 `App.session`
        # 按会话当前模型回填（见 `App.context_window_for`），不属于上下文预算。
        for name in sig:
            if name in ("self", "conversation_id", "sources", "model_context_window"):
                continue
            self.assertIn(name, cfg, msg=f"管线参数 {name} 在配置里没有对应项")
            self.assertIn(f"{name}=", src,
                          msg=f"工厂没把 {name} 传给管线（配置写了也不生效）")

    def test_pipeline_gets_the_configured_values(self) -> None:
        from agent.app import build_app
        from agent.config import get_context

        app = build_app(provider=None)
        pipe = app.context_factory("probe-cid")
        cfg = get_context()
        self.assertEqual(pipe.summary_token_threshold, cfg["summary_token_threshold"])
        self.assertEqual(pipe.reasoning_replay_tokens, cfg["reasoning_replay_tokens"])
        self.assertEqual(pipe.full_user_rounds, cfg["full_user_rounds"])
        # 工厂不猜窗口；会话装配时按模型回填。
        self.assertEqual(pipe.model_context_window, 0)
        self.assertEqual(app.context_window_for("probe-cid"), 0)


class SegmentEventCarriesTheWindowTest(unittest.TestCase):
    """分段快照必须带上模型窗口：界面按它算占用率。"""

    def setUp(self) -> None:
        no_plugins(self)

    def test_event_has_window_and_budget(self) -> None:
        from typing import Iterator

        from agent.app import build_app
        from agent.core.model_call import StreamDelta

        class _Fake:
            name = "fake"

            def name_for(self, request=None) -> str:
                return "fake"

            def stream(self, request) -> Iterator[StreamDelta]:
                yield StreamDelta(kind="text", text="ok")

        app = build_app(provider=_Fake())
        events = list(app.session("win-cid", system_prompt="你是助手。").start_turn("你好"))
        segs = [e for e in events if str(getattr(e, "type", "")) == "context_segments"]
        self.assertTrue(segs, msg="没有分段快照事件")
        data = dict(segs[-1].data)
        self.assertEqual(int(data.get("model_max_context_tokens") or 0), 0)
        self.assertGreater(int(data.get("budget_tokens") or 0), 0)
        self.assertEqual(int(data.get("model_max_context_tokens")),
                         app.context_window_for("win-cid"),
                         msg="事件里的分母必须就是该会话当前模型的窗口")
        self.assertNotEqual(data.get("model_max_context_tokens"),
                            data.get("budget_tokens"),
                            msg="窗口与预算不是一回事，不该相等（相等说明有人拿预算当窗口）")


if __name__ == "__main__":
    unittest.main()
