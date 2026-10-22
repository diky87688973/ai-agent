# -*- coding: utf-8 -*-
"""执行模式是请求尾部的临时后缀：不进系统提示词、不进历史、不发事件。

理由：模式一变就改动系统提示词的话，从系统提示词那一位起整段上下文的前缀缓存
全部作废（切一次 plan 就等于把整个上下文按原价重发一遍）。把它放到请求最末尾，
切换时只有最后那一条变化，前面的前缀照旧命中缓存。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.capabilities.registry import ToolRegistry  # noqa: E402
from agent.core.modules import _with_mode_note  # noqa: E402
from agent.shell.prompts import (  # noqa: E402
    build_system_prompt,
    resolve_mode_note,
    resolve_system_prompt,
    split_mode_section,
)
from tests.testkit import no_plugins  # noqa: E402

MODES = ("auto", "plan", "execute")


def _empty_reg() -> ToolRegistry:
    return ToolRegistry()


class SystemPromptHasNoModeTest(unittest.TestCase):
    """模式段必须从系统提示词里出去。"""

    def test_resolved_system_prompt_has_no_mode(self) -> None:
        reg = _empty_reg()
        for mode in MODES:
            text = resolve_system_prompt(mode=mode, registry=reg)
            self.assertNotIn("## 当前模式", text, msg=f"{mode} 的模式段漏在系统提示词里")

    def test_switching_mode_keeps_system_prompt_byte_identical(self) -> None:
        reg = _empty_reg()
        base = resolve_system_prompt(mode="auto", registry=reg)
        for mode in MODES[1:]:
            self.assertEqual(
                resolve_system_prompt(mode=mode, registry=reg),
                base,
                msg=f"切到 {mode} 改动了系统提示词 —— 前缀缓存会整段作废",
            )

    def test_mode_note_still_differs_per_mode(self) -> None:
        notes = {m: resolve_mode_note(mode=m) for m in MODES}
        self.assertEqual(len(set(notes.values())), len(MODES), msg="三种模式应当给出不同说明")
        for mode, note in notes.items():
            self.assertIn("当前模式", note, msg=f"{mode} 的说明缺少模式标题")

    def test_split_helper_drops_the_mode_section(self) -> None:
        full = build_system_prompt(
            registry=_empty_reg(),
            mode="plan",
            extra_sections=["## 资源目录\n系统skills: /system"],
            tool_summary="- `a` — b",
        )
        self.assertIn("## 当前模式", full, msg="构造函数本身仍应产出模式段（供拆分用）")
        cut = split_mode_section(full)
        self.assertNotIn("## 当前模式", cut)
        self.assertIn("## 资源目录", cut, msg="拆分不能连带吃掉插件章节")
        self.assertIn("`a`", cut, msg="拆分不能连带吃掉工具速查")

    def test_explicit_system_prompt_gets_no_note(self) -> None:
        """调用方自己给的系统提示：模式怎么表达由他决定，不另加。"""
        self.assertEqual(resolve_mode_note(mode="plan", explicit="他给的提示"), "")
        self.assertEqual(resolve_system_prompt(mode="plan", explicit="他给的提示"), "他给的提示")


class ModeTailShapeTest(unittest.TestCase):
    """模式说明是请求的最后一条，且不改动别处。"""

    def _base(self):
        return [
            {"role": "system", "content": "系统提示词"},
            {"role": "user", "content": "第一轮"},
            {"role": "assistant", "content": "回答"},
            {"role": "user", "content": "同一句新输入"},
        ]

    def test_note_is_appended_last(self) -> None:
        base = self._base()
        out = _with_mode_note(base, resolve_mode_note(mode="auto"))
        self.assertEqual(len(out), len(base) + 1)
        self.assertEqual(out[-1]["role"], "system",
                         msg="非用户发起的指令一律 system")
        self.assertIn("当前模式", str(out[-1]["content"]))
        self.assertEqual(out[:-1], base, msg="除尾条外必须与输入逐字节相同")

    def test_switching_mode_changes_only_the_tail(self) -> None:
        base = self._base()
        auto = _with_mode_note(base, resolve_mode_note(mode="auto"))
        for mode in ("plan", "execute"):
            other = _with_mode_note(base, resolve_mode_note(mode=mode))
            self.assertEqual(len(auto), len(other))
            self.assertEqual(auto[:-1], other[:-1],
                             msg=f"切到 {mode} 改动了尾条之外的内容")
            self.assertNotEqual(auto[-1], other[-1])

    def test_input_list_is_not_mutated(self) -> None:
        base = self._base()
        before = list(base)
        _with_mode_note(base, "## 当前模式：Plan")
        self.assertEqual(base, before, msg="不得就地修改传入的消息列表")

    def test_empty_note_changes_nothing(self) -> None:
        base = self._base()
        self.assertEqual(_with_mode_note(base, ""), base)
        self.assertEqual(_with_mode_note(base, "   "), base)

    def test_existing_runtime_tail_is_replaced_not_duplicated(self) -> None:
        """同一上下文再次装配时，旧临时尾条要被替换，不能叠成两条。"""
        base = self._base() + [
            {"role": "system", "content": "## 当前模式：Plan\n旧进度：1 已完成"},
        ]
        out = _with_mode_note(base, "## 当前模式：Auto\n当前进度：2 已完成")
        self.assertEqual(len(out), len(self._base()) + 1)
        self.assertIn("当前进度：2 已完成", out[-1]["content"])
        self.assertNotIn("旧进度", "\n".join(str(m.get("content") or "") for m in out))

    def test_note_works_after_multimodal_tail(self) -> None:
        """最后一条是多模态数组时也必须能附加（不能拼坏它的结构）。"""
        base = [{"role": "user", "content": [
            {"type": "text", "text": "看图"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AA"}},
        ]}]
        out = _with_mode_note(base, resolve_mode_note(mode="plan"))
        self.assertEqual(len(out), 2)
        self.assertIsInstance(out[0]["content"], list, msg="原数组结构必须不变")
        self.assertEqual(len(out[0]["content"]), 2)


class ModeIsNotPersistedTest(unittest.TestCase):
    """模式说明只存在于发给模型的那一份：不落记录、不发事件。"""

    def test_mode_note_is_system_role(self) -> None:
        """模式说明不是用户发言：控制台里它不该被当成用户消息。"""
        base = [{"role": "user", "content": "第一轮"}]
        out = _with_mode_note(base, resolve_mode_note(mode="plan"))
        self.assertEqual(out[-1]["role"], "system")
        self.assertTrue(all(m["role"] == "system"
                            for m in out if "当前模式" in str(m.get("content"))))

    def test_no_event_carries_the_mode_note(self) -> None:
        import tempfile

        from agent.app import build_app
        from agent.core.model_call import StreamDelta
        from agent.mechanisms.session_store import SessionStore

        # 不装插件：本用例断言的是"模式说明不进事实流"，与插件贡献无关。
        # 不隔离的话，开发者本机的插件配置（目录权威 / 注入源）会改变这一轮的请求。
        no_plugins(self)
        class _Spy:
            def __init__(self):
                self.reqs = []

            def stream(self, request):
                self.reqs.append(request)
                yield StreamDelta(kind="text", text="好")
                yield StreamDelta(kind="done")

        tmp = Path(tempfile.mkdtemp(prefix="modenot_"))
        spy = _Spy()
        store = SessionStore(tmp / "data")
        app = build_app(provider=spy, store=store,
                        backup_root=tmp / "bk", recycle_root=tmp / "rc")
        cid = "mode-not-persisted"
        engine = app.session(
            cid,
            system_prompt=resolve_system_prompt(mode="plan", registry=app.registry),
            mode_note=resolve_mode_note(mode="plan"),
            cancel=lambda: False,
        )
        for _ev in engine.start_turn("做点什么"):
            pass

        # 请求尾条有模式段标记（工具描述里也可能出现「当前模式」字样，故钉段头）
        self.assertIn("## 当前模式", str(spy.reqs[-1].messages[-1].get("content")))
        # 事实里没有
        dump = "\n".join(
            f"{getattr(e, 'type', '')}:{getattr(e, 'data', {})}" for e in store.load(cid)
        )
        self.assertNotIn("## 当前模式", dump, msg="模式说明不得写进会话记录")
        # 系统提示词字段里也没有（不含尾条 mode_note）
        self.assertNotIn(
            "## 当前模式",
            str([
                m.get("content") for m in (spy.reqs[-1].messages or [])
                if str(m.get("role")) == "system"
            ][:-1]),
        )

if __name__ == "__main__":
    unittest.main()
