# -*- coding: utf-8 -*-
"""经典界面适配层契约测试 —— 逐字段钉住内核 ↔ 经典界面的双向翻译。

适配层的风险全部集中在"字段名差一个字"。经典界面大量代码写成
`window.AIA && …` 或"取不到就静默 return"，形状对不上时一行错误都不报，只是功能
默默消失（例如 `tool_call_id` 为空 → `tool_end` 永远配不上 → 步骤卡停在"进行中"）。

断言对象是经典界面源码真正读的那些名字（每条断言旁边标出对应的界面模块），
不测"大致像"。

三组：
1. `OutboundContractTest`：内核事件 → 老事件（服务端 → 前端）；
2. `InboundContractTest`：老入参 → 内核调用 → 老返回体（前端 → 服务端）；
3. `WireHygieneTest`：帧格式、`conversation_id` 合法性、广播语义等传输层铁律。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.shell.classic_adapter import contract as C  # noqa: E402
from agent.shell.classic_adapter.adapter import ClassicAdapter  # noqa: E402
from agent.shell.classic_adapter.outbound import ClassicStream  # noqa: E402
from agent.shell.web.ui_bundle import read_ui_css, read_ui_js  # noqa: E402
from tests.testkit import no_plugins  # noqa: E402

try:                                    # 服务名常量（装配层用）
    from agent.shell.service_keys import SERVICE_CLASSIC_ADAPTER
except ImportError:                     # pragma: no cover - 常量缺失时用字面量兜底
    SERVICE_CLASSIC_ADAPTER = "classic_adapter"

CID = "4a4edf45-4fcb-43d7-aa48-05451a89ed5f"

#: 素材改动登记册（与代码耦合：`check_ui_js.py` 也核对它）。
#: 正常情况下它随仓库公开（见 `.gitignore` 的 B3 节显式取反）；
#: 万一不在本地（例如只拷了部分文件），相关用例跳过而不是失败 ——
#: 否则"克隆不全"会被误报成"代码坏了"。
_UI_CHANGES_MD = (Path(__file__).resolve().parent.parent
                / "agent" / "shell" / "web_assets" / "classic" / "UI-CHANGES.md")

class _FakeApp:
    """只为装配用的壳：适配层的入站侧大多走"拿不到就回落"的路径。

    `store` 给一个带 `data_root` 的最小实现——布局（`ui-state`）落盘需要它。
    """

    class _Provider:
        model = "fake-model"
        allowed_models = ["fake-model"]

    provider = _Provider()
    live_state = None

    # 待确认状态记在会话级 `SessionContext`；适配层只读它。
    # 没有它时适配层取不到挂起调用、静默退化成"无待确认"，
    # 所以测试壳给真的注册表。
    from agent.core.session_context import SessionContexts as _SCs
    session_contexts = _SCs(lambda cid: None)

    class _PluginHost:
        """最小插件宿主：只提供 `runtime(name)`（勾选端点按名字取插件运行时）。"""

        def __init__(self) -> None:
            self._runtimes: Dict[str, Any] = {}

        def register_runtime(self, name: str, runtime: Any) -> None:
            self._runtimes[str(name)] = runtime

        def runtime(self, name: str, default: Any = None) -> Any:
            return self._runtimes.get(str(name), default)

    def __init__(self, data_root: Path) -> None:
        # 这里挂真存储：待确认回填要往会话日志写一条事实（`store.append` /
        # `allocate_seq`）。空壳 store 写不进去，回填会静默退化成"没回填"。
        from agent.mechanisms.session_store import SessionStore

        self.store = SessionStore(data_root)
        # 每个壳一份：实例属性，测试之间互不串（类属性会共享状态）
        self.plugin_host = _FakeApp._PluginHost()
        # 真注册表：上下文布局 / 系统提示词必须能从 registry 拼出来；
        # health 契约还要求 tools>40，用最小 ToolPlugin 填满。
        from agent.capabilities.registry import ToolPlugin, ToolRegistry

        self.registry = ToolRegistry()

        class _Stub(ToolPlugin):
            parameters: dict = {}

            def __init__(self, name: str) -> None:
                self.name = name
                self.description = "stub"

            def execute(self, arguments):
                return {}

        for i in range(45):
            self.registry.register(_Stub(f"t{i}"))

def _stream(**kwargs) -> ClassicStream:
    return ClassicStream(
        CID,
        mode_resolver=kwargs.pop("mode_resolver", lambda c: "auto"),
        model_resolver=kwargs.pop("model_resolver", lambda cid="": "fake-model"),
    )

def _types(frames):
    return [f["type"] for f in frames]

class PluginEventTest(unittest.TestCase):
    """插件事件出口：帧头固定、保留键拒绝、广播计数准确。"""

    def test_frame_shape_and_copy(self) -> None:
        payload = {"conversation_id": CID, "index": 0}
        frame = C.plugin_event_frame("ai_speak", "segment", payload)
        self.assertEqual(frame["type"], C.EV_PLUGIN_EVENT)
        self.assertEqual(frame["plugin"], "ai_speak")
        self.assertEqual(frame["event"], "segment")
        self.assertEqual(frame["conversation_id"], CID)
        payload["index"] = 9
        self.assertEqual(frame["index"], 0)
        self.assertNotIn("seq", frame)

    def test_frame_rejects_reserved_and_bad_names(self) -> None:
        for payload in ({"type": "x"}, {"plugin": "x"}, {"event": "x"}, {"seq": 1}):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    C.plugin_event_frame("ai_speak", "segment", payload)
        with self.assertRaises(ValueError):
            C.plugin_event_frame("../bad", "segment", {})
        with self.assertRaises(ValueError):
            C.plugin_event_frame("ai_speak", "", {})
        with self.assertRaises(ValueError):
            C.plugin_event_frame("ai_speak", "segment", [])

    def test_announce_broadcasts_to_channels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            adapter = ClassicAdapter(_FakeApp(Path(tmp)))
            self.addCleanup(adapter.dispose)
            first = adapter.attach()
            second = adapter.attach()
            self.assertEqual(adapter.announce_plugin_event("ai_speak", "stop", {}), 2)
            self.assertEqual(first.get_nowait()["type"], C.EV_PLUGIN_EVENT)
            self.assertEqual(second.get_nowait()["event"], "stop")
            adapter.detach(first)
            self.assertEqual(adapter.announce_plugin_event("ai_speak", "stop", {}), 1)
            second.get_nowait()

class UsageSemanticsTest(unittest.TestCase):
    """`/api/usage-accumulator` 的 PUT 必须是覆盖语义。

    前端上报的是会话累计值（字段名 `total_prompt_tokens`），不是本轮增量。
    按累加处理会让每次上报都翻一倍：`PUT 1000 → 1000；涨到 1500 再 PUT → 2500`，
    真实会话前端 37.6K 而服务端 159K（4.2×）。
    `_save_usage_accumulator(body)` 也是覆盖 —— 这里同样按覆盖处理。
    """

    def test_put_overwrites_instead_of_accumulating(self) -> None:
        """覆盖语义：连报两次累计值，第二次必须替换而不是相加。"""
        from agent.shell.classic_adapter.inbound import ClassicState, Inbound

        state = ClassicState()          # 用量活在入站状态对象里（不是 LiveState）
        app = type("A", (), {"store": None, "live_state": state})()
        inbound = Inbound(app, state)  # 构造器建立内部状态；手工拼属性得不到这些状态
        cid = "usage-n2-0001"

        inbound.usage_put(cid, {"total_prompt_tokens": 1000})
        self.assertEqual(state.get_usage(cid)["total_prompt_tokens"], 1000)

        # 客户端涨到 1500 再上报 —— 必须是 1500，不能是 2500
        inbound.usage_put(cid, {"total_prompt_tokens": 1500})
        self.assertEqual(state.get_usage(cid)["total_prompt_tokens"], 1500,
                         msg="累加了：PUT 是覆盖语义，不是累加")

        # 回落到更小的值也要如实覆盖（会话重置/新开时会发生）
        inbound.usage_put(cid, {"total_prompt_tokens": 20})
        self.assertEqual(state.get_usage(cid)["total_prompt_tokens"], 20)

        # `reset` 能力保留
        inbound.usage_put(cid, {"reset": True})
        self.assertEqual(state.get_usage(cid)["total_prompt_tokens"], 0)

class OutboundContractTest(unittest.TestCase):
    """内核事件 → 老事件。每条断言都对应经典界面真正读的字段。"""

    def test_turn_started_emits_conversation_first(self) -> None:
        """`conversation` 必须发，且要带头。

        它建立会话上下文（`ensureConversationTab`）并同步模式；缺了它，
        后续 `usage` / `context_layout` 的渲染守卫不过，用量底栏永远不更新。

        帧里不带 `model`：模型不由服务端推送。前端照单接收并覆盖
        `selectedModel` 的话，就是"发一条消息、模型下拉自己跳回默认"。
        现行规则：首次打开页面拉一次当前模型，此后以发送消息那一刻前端带来的
        `model` 为准。
        """
        frames = _stream(mode_resolver=lambda c: "execute").translate("turn_started", {"run_id": "r1"})
        self.assertEqual(frames[0]["type"], C.EV_CONVERSATION)
        self.assertEqual(frames[0]["mode"], "execute")
        self.assertNotIn("model", frames[0],
                         msg="服务端不得把模型推给前端（会把用户当场的选择覆盖回默认）")
        self.assertIn("run_started", _types(frames))
        self.assertEqual(frames[1]["run_id"], "r1")          # 经典界面

    def test_step_started_emits_llm_round_then_request(self) -> None:
        """`llm_round` 是 `reasoning_*` / `llm_request` 的前置（`classic/js/chat/llm-rounds.js` 的 `addLlmRound`）。"""
        frames = _stream().translate("step_started", {"messages_count": 3, "tools_count": 41})
        self.assertEqual(_types(frames), [C.EV_LLM_ROUND, C.EV_LLM_REQUEST])
        self.assertEqual(frames[0]["round"], 1)              # `classic/js/chat/llm-rounds.js` 的 `addLlmRound`
        self.assertEqual(frames[1]["round"], 1)              # 经典界面
        params = frames[1]["params"]                          # 经典界面
        self.assertEqual(params["messagesCount"], 3)
        self.assertEqual(params["toolsCount"], 41)

    def test_llm_request_model_is_never_empty(self) -> None:
        """请求快照里的 `params.model` 不能是空串。"""
        frames = _stream().translate("step_started", {"model": "kern-model"})
        self.assertTrue(frames[1]["params"]["model"], msg="model 不得为空")

    def test_reasoning_delta_requires_round(self) -> None:
        """`round` 必须与 `lastLlm.round` 相等，否则经典界面丢弃（`classic/js/chat/llm-rounds.js` 的 `appendReasoningDelta`）。"""
        stream = _stream()
        # 没有前置 llm_round → 丢弃
        self.assertEqual(stream.translate("reasoning_delta", {"text": "想"}), [])
        stream.translate("step_started", {})
        frames = stream.translate("reasoning_delta", {"text": "想"})
        self.assertEqual(frames[0]["delta"], "想")            # 字段名是 delta
        self.assertEqual(frames[0]["round"], 1)

    def test_assistant_delta_uses_delta_field(self) -> None:
        frames = _stream().translate("assistant_delta", {"text": "正文"})
        self.assertEqual(frames[0]["delta"], "正文")          # 经典界面

    def test_tool_call_becomes_tool_start_with_call_id(self) -> None:
        """`tool_call_id` 是配对的唯一键；空则后续 `tool_end` 被整个忽略（`classic/js/chat/llm-rounds.js` 的 `onToolStart`）。"""
        frames = _stream().translate(
            "tool_call", {"call_id": "c1", "name": "read_file", "arguments": {"path": "a.md"}}
        )
        self.assertEqual(frames[0]["type"], C.EV_TOOL_START)
        self.assertEqual(frames[0]["tool_call_id"], "c1")     # 经典界面
        self.assertEqual(frames[0]["script"], "read_file")    # 经典界面
        self.assertEqual(frames[0]["args"], {"path": "a.md"})

    def test_tool_call_without_id_is_skipped(self) -> None:

        """没有 id 就配不上 tool_end，宁可一条都不发（发了就是永远转圈的卡）。"""
        self.assertEqual(_stream().translate("tool_call", {"name": "read_file"}), [])

    def test_tool_result_preview_is_json_string(self) -> None:

        """`preview` 必须是 JSON 字符串（经典界面会 `JSON.parse`，`classic/js/tools/previews.js` 的 `fillToolPreview`）。"""
        stream = _stream()
        stream.translate("tool_call", {"call_id": "c1", "name": "run_command", "arguments": {}})
        frames = stream.translate(
            "tool_result", {"call_id": "c1", "ok": True, "data": {"stdout": "hi"}}
        )
        end = frames[0]
        self.assertEqual(end["type"], C.EV_TOOL_END)
        self.assertTrue(end["ok"])
        parsed = json.loads(end["preview"])                   # 必须能 parse
        self.assertEqual(parsed.get("ok"), True)
        self.assertEqual(parsed["data"]["stdout"], "hi")      # 经典界面 读 data.stdout

    def test_tool_done_images_ride_beside_preview(self) -> None:
        """看图的像素走 `images`，不写进 `preview` 文本。"""
        stream = _stream()
        stream.translate("tool_call", {
            "call_id": "c1", "name": "read_image",
            "arguments": {"path": r"C:\Temp\qq5.png"},
        })
        frames = stream.translate("tool_done", {
            "call_id": "c1",
            "data": {"path": r"C:\Temp\qq5.png", "width": 10, "height": 8},
            "attachments": [
                {"mime": "image/png", "data_base64": "abcd"},
                {"mime": "text/plain", "data_base64": "nope"},
            ],
        })
        end = frames[0]
        self.assertEqual(end["images"], [{"mime": "image/png", "data_base64": "abcd"}])
        self.assertNotIn("data_base64", end["preview"])

    def test_tool_result_without_start_is_skipped(self) -> None:

        self.assertEqual(_stream().translate("tool_result", {"call_id": "nope", "ok": True}), [])

    def test_confirm_card_comes_from_the_kernel_fact(self) -> None:
        """待确认卡由内核专用事实 `turn_awaiting_user` 驱动。

        两段式首段不产生 `tool_result`（那次调用还没返回），所以没有结果事件
        可以挂载卡片。内核为此产出这条事实，携带 `call_id` / 标题 / 选项——
        选项以工具声明的为准。

        经典界面的卡片靠 `tool_end` 上的 `user_confirm_required` 渲染，所以适配层
        在这里发一个 `tool_end`（`ok=True`：停下来等用户是协议的一环，不是失败）。
        """

        stream = _stream()
        stream.translate("tool_call", {"call_id": "c1", "name": "user_confirm",
                                       "arguments": {"title": "选一个", "confirms": ["甲", "乙"]}})
        frames = stream.translate("turn_awaiting_user", {
            "call_id": "c1", "title": "选一个", "confirms": ["甲", "乙"], "multi": False,
        })
        self.assertEqual(len(frames), 1)
        end = frames[0]
        self.assertEqual(end["type"], C.EV_TOOL_END)
        self.assertTrue(end["user_confirm_required"])
        self.assertEqual(end["user_confirm_title"], "选一个")
        self.assertFalse(end["user_confirm_multi"])
        # 选项必须给：模态只读 `user_confirm_options`，不看 preview
        self.assertEqual(end["user_confirm_options"], ["甲", "乙"],
                         msg="模态靠它渲染选项行，不给就只剩一个空的自定义输入框")

    def test_tool_call_does_not_pre_empt_the_confirm_card(self) -> None:
        """`tool_call` 期不发待确认卡——卡片由内核事实驱动，避免重复发两张。

        卡片只由内核 `turn_awaiting_user` 驱动；模型原始入参里的选项不构成触发依据。
        """

        stream = _stream()
        frames = stream.translate("tool_call", {
            "call_id": "c1", "name": "user_confirm",
            "arguments": {"title": "选一个", "confirms": ["甲", "乙"]},
        })
        self.assertEqual(frames[0]["type"], C.EV_TOOL_START)
        self.assertNotIn("user_confirm_required", frames[0])

    def test_incomplete_awaiting_fact_is_ignored(self) -> None:
        """缺 `call_id` 或缺选项的事实不发卡（残缺数据不猜、不半渲染）。"""

        for payload in (
            {"title": "只有标题", "confirms": ["甲"]},                    # 缺 call_id
            {"call_id": "c1", "title": "选一个"},                        # 缺 confirms
            {"call_id": "c1", "title": "选一个", "confirms": []},        # 空选项
        ):
            stream = _stream()
            self.assertEqual(stream.translate("turn_awaiting_user", payload), [],
                             msg=f"残缺事实不该发卡: {payload}")

    def test_user_confirm_multi_flag_passes_through(self) -> None:

        stream = _stream()
        frames = stream.translate("turn_awaiting_user", {
            "call_id": "c1", "title": "多选", "confirms": ["甲"], "multi": True,
        })
        self.assertTrue(frames[0]["user_confirm_multi"])

    def test_plain_failure_is_not_mistaken_for_confirm(self) -> None:
        """普通失败不得被判成待确认——否则每个报错都会弹出确认框。"""

        stream = _stream()
        stream.translate("tool_call", {"call_id": "c1", "name": "read_file", "arguments": {}})
        end = stream.translate("tool_result", {
            "call_id": "c1", "ok": False, "data": None, "error": "文件不存在",
        })[0]
        self.assertFalse(end["ok"])
        self.assertNotIn("user_confirm_required", end)
        fail_preview = json.loads(end["preview"])
        self.assertEqual(fail_preview.get("ok"), False)
        self.assertEqual(fail_preview.get("error"), "文件不存在")
        self.assertNotIn("data", fail_preview)
        # 缺 title / confirms 的残缺 data 也不算信封
        stream2 = _stream()
        stream2.translate("tool_call", {"call_id": "c2", "name": "user_confirm", "arguments": {}})
        end2 = stream2.translate("tool_result", {
            "call_id": "c2", "ok": False, "data": {"title": "有标题但没选项"},
        })[0]
        self.assertNotIn("user_confirm_required", end2)

    def test_write_gate_confirm_id_does_not_fake_a_confirmation(self) -> None:
        """`confirm_id` 是写盘门控的二阶提交锁：门控给预览类工具的
        成功结果挂上它，意思是"锁已建好，模型接着调提交工具并把 `confirm_id` 传回来"。
        用户交互不发生在这一步（解锁入口是 `review_conclusion`）。

        据此发 `user_confirm_required` 会同时产生两个后果（同一个根因）：
        ① 对话区冒出一张没人触发的内嵌卡，用户还得手动点 ✅；
        ② 模型完全不知道有这个交互——`tool_done` 已正常返回，它以为流程在跑。
        （卡片文案"写盘需要确认 / 允许提交"并不存在于任何实现里。）
        """

        stream = _stream()
        stream.translate("tool_call", {"call_id": "c1", "name": "commit_write", "arguments": {}})
        end = stream.translate("tool_result", {
            "call_id": "c1", "ok": True, "data": {"confirm_id": "cf-9"},
        })[0]
        self.assertTrue(end["ok"], msg="预览是成功结果，不是挂起")
        self.assertNotIn("user_confirm_required", end,
                         msg="confirm_id 不该伪装成用户确认（会冒出无人触发的卡片）")
        # 但锁必须仍可见：它在 preview 里，模型据此拿到 confirm_id 去提交
        self.assertIn("cf-9", end["preview"])

    def test_only_a_real_suspension_asks_the_user(self) -> None:
        """只有工具真挂起才发 `user_confirm_required`——经典界面收到它就弹模态。

        `classic/js/chat/confirm.js` 里这条是 100% 走弹窗的（`openUserConfirmModalFromToolEnd`
        会 `userConfirmBlocking=true` + `goBtn.disabled=true`）。所以这个字段的
        语义是"整个运行被阻塞、必须用户作答"；"顺便选一下"不属于这个字段。
        """
        stream = _stream()
        frames = stream.translate("tool_suspended", {
            "call_id": "c9", "name": "user_confirm",
            "envelope": {"title": "选一个", "confirms": ["甲", "乙"]},
        })
        end = [f for f in frames if f["type"] == C.EV_TOOL_END][0]
        self.assertTrue(end["user_confirm_required"])
        self.assertEqual(end["user_confirm_options"], ["甲", "乙"])
        self.assertEqual(end["user_confirm_title"], "选一个")

    def test_approval_suspension_is_not_a_choice_card(self) -> None:
        """审批挂起发 `approval_required`，不发选项卡。"""

        stream = _stream()
        frames = stream.translate("tool_suspended", {
            "call_id": "c9", "name": "approval_confirm",
            "envelope": {
                "kind": "approval",
                "title": "审批",
                "option_id": "video-1",
                "option_desc": "是否准许生成视频？",
            },
        })
        end = [f for f in frames if f["type"] == C.EV_TOOL_END][0]
        self.assertTrue(end["approval_required"])
        self.assertEqual(end["approval_title"], "审批")
        self.assertEqual(end["approval_desc"], "是否准许生成视频？")
        self.assertNotIn("user_confirm_required", end)

    def test_cancel_on_confirm_modal_records_a_declined_result(self) -> None:
        """模态点「取消」（空 `confirm`）当作拒绝作答、记成工具结果，
        与在端点里就地 `return 200 {"confirmed": False}` 行为不同。

        就地返回的后果：
          · 挂起继续保持（用户以为取消了，其实还在等作答）；
          · 那次调用的 `tool_result` 永不出现 → 悬空的 `assistant(tool_calls)`
            留在历史里 → 该会话之后每条消息都 400，且不可自愈；
          · 顺带 `abortController` 永不复位 → 正在思考中永久转圈、
            发送按钮消失，用户只能点停止逃生。

        约束：空文本也要交给 `submit_user_choice`，由它把拒绝作为结果经运行器
        交回内核 —— 于是挂起闭合、模型知情、会话可继续。
        """
        calls: list = []

        class _Mesh:
            def submit(self, cid, payload):
                calls.append((cid, payload))
                return {"queued": False, "run_id": "r-1"}

        class _App:
            mesh = _Mesh()

        adapter = ClassicAdapter.__new__(ClassicAdapter)
        adapter._app = _App()  # type: ignore[attr-defined]
        adapter._shell = None  # type: ignore[attr-defined]
        adapter.pending_confirm = lambda cid: {"call_id": "c-suspended"}  # type: ignore[attr-defined]
        adapter._clear_pending = lambda cid: None  # type: ignore[attr-defined]

        status, payload = adapter.user_confirm(CID, {"confirm": ""})

        self.assertEqual(status, 200)
        self.assertTrue(payload.get("declined"), msg="空 confirm 应标为 declined")
        self.assertFalse(payload.get("confirmed"))
        self.assertEqual(len(calls), 1, msg="必须真的提交一次，让挂起闭合")
        resume = (calls[0][1] or {}).get("resume") or {}
        self.assertEqual(resume.get("call_id"), "c-suspended")
        self.assertFalse(resume.get("ok"), msg="拒绝要以失败结果交回，模型才知道用户不答")
        self.assertIn("取消", str(resume.get("error") or ""))

    def test_cancel_without_pending_does_not_start_an_empty_turn(self) -> None:
        """没有挂起调用时的取消不得起新回合。

        那正是永久转圈的来源：内核那一轮没有输入 → 不产出任何事实
        → 永远不发 `done` → 前端的 loading 状态没人复位。
        """
        calls: list = []

        class _Mesh:
            def submit(self, cid, payload):
                calls.append((cid, payload))
                return {"queued": False, "run_id": "r-1"}

        class _App:
            mesh = _Mesh()

        adapter = ClassicAdapter.__new__(ClassicAdapter)
        adapter._app = _App()  # type: ignore[attr-defined]
        adapter._shell = None  # type: ignore[attr-defined]
        adapter.pending_confirm = lambda cid: None  # type: ignore[attr-defined]
        adapter._clear_pending = lambda cid: None  # type: ignore[attr-defined]

        status, payload = adapter.user_confirm(CID, {"confirm": ""})
        self.assertEqual(status, 200)
        self.assertFalse(payload.get("confirmed"))
        self.assertEqual(calls, [], msg="无挂起时不该起空回合")

    def test_chat_bubble_layout_puts_image_above_text(self) -> None:
        """图文气泡：图片在上、文字在下。

        做法：用户气泡是纵向 flex，文字包在 `.b-text` 里，附件条用 CSS `order`
        排到它前面（`.b.u > .msg-attach-strip{order:1}` / `.b.u > .b-text{order:2}`）。
        """
        css = read_ui_css()
        flat = "".join(css.split())
        self.assertIn(".b.u>.msg-attach-strip{order:1", flat,
                      msg="附件条缺少 order:1，图片会掉到文字下面")
        self.assertIn(".b.u>.b-text{order:2", flat,
                      msg="文字缺少 order:2")

    def test_reasoning_is_not_promoted_into_chat_area(self) -> None:
        """思考内容不经对话区填充（它属于右侧步骤卡）。

        `promoteReasoningToChatIfNeeded` 的函数体保留但不得被调用：
        一旦调用，思考会混进对话正文。
        """
        js = read_ui_js()
        self.assertIn("function promoteReasoningToChatIfNeeded", js,
                      msg="函数被删了；本项只约束它不被调用")
        # 定义之后的正文里不得出现调用（注释里的提及不算）
        body = js.split("function promoteReasoningToChatIfNeeded", 1)[1]
        callers = [ln for ln in body.splitlines()
                   if "promoteReasoningToChatIfNeeded(" in ln
                   and not ln.lstrip().startswith(("//", "/*", "*"))]
        self.assertEqual(callers, [],
                         msg=f"思考内容又被填进对话区了：{callers[:2]}")

    def test_run_type_switch_emits_mode_changed(self) -> None:
        """`run_type` 切模式后必须补 `mode_changed`，否则经典界面的模式按钮停在旧值。

        该工具直接写 `live_state.set_mode()`、不发 `mode_changed`，
        而经典界面的模式按钮只在 `mode_changed` / `conversation` 时刷新。
        （`goal` 不需要补：经典界面自己在 `onToolEnd` 里刷新「目标」按钮。）
        """
        stream = _stream()
        stream.translate("tool_call", {"call_id": "c1", "name": "run_type",
                                       "arguments": {"run_type": "plan"}})
        frames = stream.translate("tool_result", {
            "call_id": "c1", "ok": True,
            "data": {"run_type": "plan", "action": "switch"},
        })
        kinds = _types(frames)
        self.assertEqual(kinds[0], C.EV_TOOL_END)
        self.assertIn(C.EV_MODE_CHANGED, kinds)
        mode_frame = frames[kinds.index(C.EV_MODE_CHANGED)]
        self.assertEqual(mode_frame["mode"], "plan")

    def test_run_type_query_does_not_emit_mode_changed(self) -> None:
        """查询模式不该发 `mode_changed`（会把按钮刷成同一个值，纯噪声）。"""
        stream = _stream()
        stream.translate("tool_call", {"call_id": "c1", "name": "run_type", "arguments": {}})
        frames = stream.translate("tool_result", {
            "call_id": "c1", "ok": True, "data": {"run_type": "execute", "action": "query"},
        })
        self.assertNotIn(C.EV_MODE_CHANGED, _types(frames))

    def test_failed_run_type_switch_does_not_emit_mode_changed(self) -> None:
        """失败时不能报"模式已切换"——那会让按钮显示一个并未生效的模式。"""
        stream = _stream()
        stream.translate("tool_call", {"call_id": "c1", "name": "run_type",
                                       "arguments": {"run_type": "bogus"}})
        frames = stream.translate("tool_result", {
            "call_id": "c1", "ok": False, "data": {"run_type": "bogus", "action": "switch"},
            "error": "ValueError: 未知模式",
        })
        self.assertNotIn(C.EV_MODE_CHANGED, _types(frames))

    def test_todo_list_rides_on_tool_end(self) -> None:

        """清单没有独立事件，挂在 `tool_end.todo_list_data` 上（`classic/js/chat/stream.js` 的 `handleGlobalSseEvent`）。"""
        stream = _stream()
        stream.translate("tool_call", {"call_id": "c9", "name": "todo_list", "arguments": {}})
        frames = stream.translate("tool_result", {
            "call_id": "c9", "ok": True,
            "data": {"items": [{"text": "甲", "done": False}], "collapsed": False, "close": False},
        })
        end = frames[0]
        self.assertTrue(end["todo_list"])
        self.assertEqual(end["todo_list_data"]["items"][0]["text"], "甲")

        stream.translate("tool_call", {"call_id": "c10", "name": "todo_list", "arguments": {}})
        frames = stream.translate("tool_result", {
            "call_id": "c10", "ok": True, "data": {"close": True},
        })
        end = frames[0]
        self.assertTrue(end["todo_list"])
        self.assertEqual(end["todo_list_data"]["items"], [])
        self.assertTrue(end["todo_list_data"]["close"])

    def test_usage_must_be_nested(self) -> None:
        """用量嵌套在 `usage` 键下：经典界面读 `ev.usage.prompt_tokens`（`classic/js/chat/stream.js` 的 `handleGlobalSseEvent`）。

        平铺到顶层时经典界面读不到，表现是"用量永远是 0"。
        """
        frames = _stream().translate("usage", {
            "prompt_tokens": 9300, "completion_tokens": 2,
            "prompt_cache_hit_tokens": 9088, "prompt_cache_miss_tokens": 212,
        })
        frame = frames[0]
        self.assertEqual(frame["type"], C.EV_USAGE)
        self.assertIn("usage", frame)
        self.assertEqual(frame["usage"]["prompt_tokens"], 9300)
        # 不得平铺到顶层（否则经典界面读不到）
        self.assertNotIn("prompt_tokens", frame)

    def test_context_layout_is_flat_with_segments(self) -> None:
        """`lastContextLayout = ev` 整包存下，所以 segments 在顶层（`classic/js/chat/stream.js` 的 `handleGlobalSseEvent`）。"""
        frames = _stream().translate("context_layout", {
            "segments": [{"key": "system", "tokens": 100}], "total_tokens": 100,
        })
        self.assertEqual(frames[0]["segments"][0]["key"], "system")

    def test_assistant_only_on_final_message_with_content(self) -> None:
        """工具调用轮没有正文，发空 `assistant` 会让经典界面渲染一个空气泡。

        （其余帧照发——`llm_response`/`llm_done` 是经典界面收 LLM 卡片所必需的。）
        """
        stream = _stream()
        stream.translate("step_started", {})
        frames = stream.translate("model_message", {"content": "", "tool_calls": [{"id": "c1"}]})
        self.assertNotIn(C.EV_ASSISTANT, _types(frames))
        self.assertIn(C.EV_LLM_DONE, _types(frames))

    def test_model_message_with_content_emits_response_done_and_assistant(self) -> None:
        stream = _stream()
        stream.translate("step_started", {})
        frames = stream.translate("model_message", {"content": "答"})
        self.assertEqual(_types(frames), [C.EV_LLM_RESPONSE, C.EV_LLM_DONE, C.EV_ASSISTANT])
        self.assertEqual(frames[2]["content"], "答")          # 经典界面

    def test_turn_ended_emits_done(self) -> None:
        frames = _stream().translate("turn_ended", {})
        self.assertEqual(_types(frames), [C.EV_DONE])
        self.assertTrue(frames[0]["ok"])

    def test_unknown_kernel_event_is_ignored_not_raised(self) -> None:
        """观察面纪律：翻译不认识的事件不能把事件流打断。"""
        self.assertEqual(_stream().translate("some_future_event", {"x": 1}), [])

    def test_malformed_arguments_do_not_break_the_stream(self) -> None:
        """`arguments` 不是对象时按空对象处理（经典界面只把它 JSON 化显示，不校验）。

        关键是不能抛异常——观察面纪律：一帧翻不出来只能丢那一帧，
        不能把后面的事件一起带走。
        """
        stream = _stream()
        frames = stream.translate("tool_call", {"call_id": "c1", "name": "read_file",
                                                "arguments": "not-a-dict"})
        self.assertEqual(_types(frames), [C.EV_TOOL_START])
        self.assertEqual(frames[0]["args"], {})
        # 后续事件仍能正常翻译
        self.assertEqual(_types(stream.translate("turn_ended", {})), [C.EV_DONE])

class InboundContractTest(unittest.TestCase):
    """老入参 → 内核 → 老返回体。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = _FakeApp(Path(self._tmp.name))
        self.adapter = ClassicAdapter(self.app)
        self.state = self.adapter.state

    def test_sessions_read_id_not_conversation_id(self) -> None:
        """经典界面读 `s.id`（`classic/js/chat/conversation.js` 的 `loadSessionRailList`）；`conversation_id` 不是它要的名字。"""
        payload = self.adapter.sessions()
        self.assertTrue(payload["ok"])
        self.assertIn("items", payload)
        for row in payload["items"]:
            self.assertIn("id", row)
            self.assertIn("date_group", row)

    def test_ui_state_get_returns_only_client_independent_state(self) -> None:
        """GET 只回与客户端无关的那部分：哪些会话在跑。

        布局（打开过哪些标签、激活哪一个）是客户端本地状态，服务端不存也不回 ——
        两个客户端各自激活不同会话时，一个全局字段表示不了，只会互相覆盖。
        """
        payload = self.adapter.ui_state_get()
        self.assertIn("state", payload)
        self.assertIn("running", payload["state"])
        self.assertNotIn("tabs", payload["state"])
        self.assertNotIn("active_conversation_id", payload["state"])

    def test_ui_state_put_stores_nothing(self) -> None:
        """PUT 收到布局也不落盘；旧前端不会因此报错。"""
        result = self.adapter.ui_state_put({
            "tabs": [{"id": CID, "title": "甲"}], "active_conversation_id": CID,
        })
        self.assertTrue(result["ok"])
        back = self.adapter.ui_state_get()
        self.assertNotIn("tabs", back["state"])
        self.assertNotIn("active_conversation_id", back["state"])

    def test_ui_state_put_writes_no_layout_file(self) -> None:
        """确认没有留下布局文件（服务端不该有客户端状态的副本）。"""
        root = Path(self.app.store.data_root)
        self.adapter.ui_state_put({"tabs": [{"id": CID}], "active_conversation_id": CID})
        self.assertFalse((root / "ui_layout.json").is_file())

    def test_usage_accumulator_uses_different_field_names(self) -> None:
        """累计端点用 `total_*`，与 SSE 的 `prompt_tokens` 不是一套（`classic/js/chat/context-usage.js` 的 `loadUsageAccumulator`）。"""
        self.state.add_usage(CID, {"prompt_tokens": 10, "completion_tokens": 2,
                                   "prompt_cache_hit_tokens": 8, "prompt_cache_miss_tokens": 2})
        payload = self.adapter.usage_get(CID)
        for field in C.ACCUMULATOR_USAGE_FIELDS:
            self.assertIn(field, payload, msg=field)
        self.assertEqual(payload["total_prompt_tokens"], 10)
        self.assertEqual(payload["total_completion_tokens"], 2)
        self.assertEqual(payload["total_tokens"], 12)

    def test_usage_hydrates_from_facts_after_state_reset(self) -> None:
        from agent.core.events import Event
        from agent.shell.classic_adapter.inbound import ClassicState, Inbound

        class _Store:
            def load(self, cid):
                return [Event("usage", {"prompt_tokens": 10, "completion_tokens": 2,
                                        "prompt_cache_hit_tokens": 8,
                                        "prompt_cache_miss_tokens": 2})]

        state = ClassicState()
        app = type("A", (), {"store": _Store(), "live_state": state})()
        inbound = Inbound(app, state)
        got = inbound.usage_get("usage-hydrate-01")
        self.assertEqual(got["total_prompt_tokens"], 10)
        self.assertEqual(got["total_completion_tokens"], 2)
        self.assertEqual(got["total_tokens"], 12)

    def test_usage_accumulates_across_events(self) -> None:
        for _ in range(3):
            self.state.add_usage(CID, {"prompt_tokens": 10, "completion_tokens": 1})
        self.assertEqual(self.adapter.usage_get(CID)["total_prompt_tokens"], 30)

    def test_attachment_returns_image_bytes_not_json(self) -> None:
        """经典界面用 `<img src>` 直接引用（il.js:7），所以必须返回字节而不是 JSON。"""
        import base64
        raw = base64.b64encode(b"\x89PNG\r\n\x1a\n fake").decode()
        items = self.adapter.inbound.remember_attachments(
            CID, [{"data_base64": raw, "mime": "image/png", "name": "x.png"}])
        self.assertEqual(len(items), 1)
        status, body, ctype = self.adapter.attachment(CID, items[0]["id"])
        self.assertEqual(status, 200)
        self.assertEqual(ctype, "image/png")
        self.assertTrue(body.startswith(b"\x89PNG"))

    def test_attachment_missing_is_404(self) -> None:
        status, _, _ = self.adapter.attachment(CID, "nope")
        self.assertEqual(status, 404)

    def test_attachment_ignores_invalid_images(self) -> None:
        """`images` 里没有可用 base64 时不登记（经典界面只在数组非空时才重建附件条）。"""
        self.assertEqual(self.adapter.inbound.remember_attachments(CID, [{"mime": "image/png"}]), [])

    def test_invalid_conversation_id_rejected_on_write(self) -> None:
        self.assertFalse(self.adapter.usage_put("bad id!", {})["ok"])

    def test_health_model_is_in_allowed_list(self) -> None:
        """`model` 必须在 `allowed_models` 里，否则经典界面白名单校验丢弃它 → 顶栏永远加载中。"""
        payload = self.adapter.health()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["service"], "agent.web")
        self.assertIn(payload["model"], payload["allowed_models"])
        self.assertGreater(payload["tools"], 40)

    def test_history_returns_ok_true(self) -> None:
        """回显必须带 `ok:true`，否则经典界面直接 return、整段历史不渲染。"""
        payload = self.adapter.history(CID)
        self.assertTrue(payload["ok"])

    def test_history_returns_items_for_bubbles(self) -> None:
        """`items` 是刷新页面渲染气泡与工具卡的唯一来源（`renderHistoryItems`）。

        `items` 必须由内核事件折出——经典界面的 30 种事件里没有"用户消息"这一种，
        用户侧只能从 `input_claimed` 取。
        """
        from agent.core.events import Event

        events = [
            Event("turn_started", {"run_id": "r"}),
            Event("input_claimed", {"content": "你好"}),
            Event("step_started", {"step": "1"}),
            Event("model_message", {"content": "", "tool_calls": [{"id": "c1"}]}),
            Event("model_message", {"content": "在的"}),
            Event("turn_ended", {"steps": "1"}),
        ]

        class _Store:
            data_root = Path(r"D:\nonexistent-never-used")

            def load(self, cid):
                return events

        class _App(_FakeApp):
            def __init__(self):
                super().__init__(Path(r"D:\nonexistent-never-used"))
                self.store = _Store()

        adapter = ClassicAdapter(_App())
        items = adapter.history(CID)["items"]
        self.assertEqual([i["role"] for i in items], ["user", "assistant"])
        self.assertEqual(items[0]["content"], "你好")
        self.assertEqual(items[1]["content"], "在的")   # 空气泡被跳过

    def test_history_cancels_suspended_tool_after_new_input(self) -> None:
        from agent.core.events import Event

        events = [
            Event("tool_started", {"call_id": "c1", "name": "user_confirm",
                                   "arguments": {}}),
            Event("tool_suspended", {"call_id": "c1", "name": "user_confirm",
                                     "envelope": {"title": "选一个",
                                                  "confirms": ["甲", "乙"]}}),
            Event("input_claimed", {"content": "用户发了新消息"}),
            Event("turn_ended", {"paused": False}),
        ]

        class _Store:
            data_root = Path(r"D:\nonexistent-never-used")

            def load(self, cid):
                return events

        class _App(_FakeApp):
            def __init__(self):
                super().__init__(Path(r"D:\nonexistent-never-used"))
                self.store = _Store()

        items = ClassicAdapter(_App()).history(CID)["items"]
        tool = [item for item in items if item["role"] == "tool"][0]
        self.assertEqual(tool["status"], "canceled")
        self.assertIn("取消", tool["error"])

    def test_history_carries_context_layout_at_top_level(self) -> None:
        """`context_layout` 在顶层，`applyContextLayoutFromHistory` 读那里。"""
        from agent.core.events import Event

        layout = {"segments": [{"key": "system", "tokens": 100}], "total_tokens": 100}

        class _Store:
            data_root = Path(r"D:\nonexistent-never-used")

            def load(self, cid):
                return [Event("context_layout", layout), Event("turn_ended", {})]

        class _App(_FakeApp):
            def __init__(self):
                super().__init__(Path(r"D:\nonexistent-never-used"))
                self.store = _Store()

        payload = ClassicAdapter(_App()).history(CID)
        self.assertEqual(payload["context_layout"]["total_tokens"], 100)
        self.assertIsInstance(payload["todo_list"], list)

    def test_history_todo_ignores_other_tools_items(self) -> None:
        """检索结果的 `items`（`file` / `match`）不能进清单。

        `find_in_file` / `file_search` 与 `todo_list` 一样返回 `{"items": [...]}`。
        从事件里按形状取最后一个，清单就会变成搜索结果，界面渲染出没有文字的复选框。
        清单的唯一事实源是 `live_state`。
        """
        from agent.core.events import Event

        events = [Event("tool_done", {"call_id": "t2", "name": "file_search", "data": {
            "count": 2, "items": [
                {"file": "a.py", "line": 1, "match": "def check"},
                {"file": "a.py", "line": 9, "match": "def cycles"},
            ]}})]

        class _Live:
            def get_todo(self, cid):
                return {"list_id": "l1", "items": [{"text": "读代码", "done": False}],
                        "collapsed": False}

        class _Store:
            data_root = Path(r"D:\nonexistent-never-used")

            def load(self, cid):
                return events

        class _App(_FakeApp):
            def __init__(self):
                super().__init__(Path(r"D:\nonexistent-never-used"))
                self.store = _Store()
                self.live_state = _Live()

        todo = ClassicAdapter(_App()).history(CID)["todo_list"]
        self.assertEqual([it["text"] for it in todo], ["读代码"])

    def test_history_todo_empty_when_none_active(self) -> None:
        """没有清单（或已 `close`）时返回空数组，界面据此 `hideTodoList`。"""
        from agent.core.events import Event

        events = [Event("tool_done", {"call_id": "t1", "name": "todo_list", "data": {
            "list_id": "l1", "items": [{"text": "旧的", "done": False}],
            "collapsed": False, "close": True}})]

        class _Live:
            def get_todo(self, cid):
                return None

        class _Store:
            data_root = Path(r"D:\nonexistent-never-used")

            def load(self, cid):
                return events

        class _App(_FakeApp):
            def __init__(self):
                super().__init__(Path(r"D:\nonexistent-never-used"))
                self.store = _Store()
                self.live_state = _Live()

        self.assertEqual(ClassicAdapter(_App()).history(CID)["todo_list"], [])

    def test_history_rejects_bad_id(self) -> None:
        payload = self.adapter.history("x")
        self.assertFalse(payload["ok"])

    def test_title_never_raises(self) -> None:
        self.assertTrue(self.adapter.title(CID)["ok"])

class WireHygieneTest(unittest.TestCase):
    """传输层铁律：帧格式与 `conversation_id`。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.adapter = ClassicAdapter(_FakeApp(Path(self._tmp.name)))

    def test_every_frame_carries_valid_conversation_id(self) -> None:
        """没带合法 cid 的帧会被经典界面整包静默丢弃（`classic/js/chat/stream.js` 的 `drainChatSseFromResponse`）。"""
        # 必须先 attach 再 feed：事件是广播给当前已连接通道的，
        # 没有通道时没有"待收件箱"，事件不会被留到以后（这是有意的：
        # 重连补齐靠 /api/chat/history 回放，而不是靠无限积压）。
        box = self.adapter.attach()
        self.adapter.feed("turn_started", {"conversation_id": CID, "run_id": "r", "mode": "plan"})
        self.adapter.feed("step_started", {"conversation_id": CID})
        self.adapter.feed("tool_call", {"conversation_id": CID, "call_id": "c1",
                                        "name": "read_file", "arguments": {}})
        seen = 0
        while True:
            frame = self.adapter.next_frame(box, timeout=0.05)
            if frame is None:
                break
            seen += 1
            if frame["type"] in C.CID_EXEMPT_EVENTS:
                continue
            self.assertTrue(C.normalize_cid(frame.get("conversation_id")),
                            msg=f"{frame['type']} 缺合法 conversation_id")
        self.assertGreater(seen, 0, msg="一帧都没发出去，说明 feed 没接上")

    def test_frames_broadcast_to_every_channel(self) -> None:
        """广播而非共享队列：两个标签页必须各自收到完整事件流。

        共享队列时两个消费者会瓜分事件——表现是"步骤卡不出现、用量不动"。
        """
        first, second = self.adapter.attach(), self.adapter.attach()
        self.adapter.feed("turn_started", {"conversation_id": CID, "run_id": "r", "mode": "plan"})
        self.adapter.feed("tool_call", {"conversation_id": CID, "call_id": "c1",
                                        "name": "read_file", "arguments": {}})

        def drain(box):
            out = []
            while True:
                frame = self.adapter.next_frame(box, timeout=0.05)
                if frame is None:
                    return out
                out.append(frame["type"])

        first_types, second_types = drain(first), drain(second)
        self.assertEqual(first_types, second_types)
        self.assertIn(C.EV_TOOL_START, first_types)
        # 先消费的那个通道不能把事件"吃掉"
        self.assertIn(C.EV_RUN_STARTED, second_types)

    def test_detach_stops_delivery(self) -> None:
        box = self.adapter.attach()
        self.adapter.detach(box)
        self.adapter.feed("turn_ended", {"conversation_id": CID})
        self.assertIsNone(self.adapter.next_frame(box, timeout=0.05))

    def test_heartbeat_is_cid_exempt(self) -> None:
        beat = self.adapter.heartbeat()
        self.assertEqual(beat["type"], C.EV_HEARTBEAT)
        self.assertNotIn("conversation_id", beat)
        box = self.adapter.attach()
        self.adapter.announce_plugins(["skills", "knowledge", ""])
        frame = self.adapter.next_frame(box, timeout=0.05)
        self.assertEqual(frame["type"], C.EV_PLUGINS_CHANGED)
        self.assertEqual(frame["loaded"], ["knowledge", "skills"])
        self.assertNotIn("conversation_id", frame)
        self.adapter.detach(box)

    def test_frame_without_cid_is_dropped_silently(self) -> None:
        """入站事件没有 cid 时直接丢，不要造一个假 cid 塞给前端。"""
        self.assertEqual(self.adapter.feed("turn_started", {"run_id": "r"}), [])
        box = self.adapter.attach()
        self.assertIsNone(self.adapter.next_frame(box, timeout=0.05))

    def test_sse_payload_is_single_line_data_frame(self) -> None:
        """帧格式必须是 `data: <单行 json>\\n\\n`（`classic/js/chat/stream.js` 的 `drainChatSseFromResponse`）。"""
        from agent.shell.classic_adapter.adapter import ClassicSseChannel

        # 先建通道（连接）再喂事件——事件只广播给已连接的通道
        channel = ClassicSseChannel(self.adapter, heartbeat=999)
        self.adapter.feed("turn_started", {"conversation_id": CID, "run_id": "r", "mode": "plan"})
        self.adapter.feed("tool_call", {"conversation_id": CID, "call_id": "c1",
                                        "name": "read_file", "arguments": {}})
        payload = channel.next_payload()
        self.assertTrue(payload.startswith("data:"), msg=repr(payload[:40]))
        self.assertTrue(payload.endswith("\n\n"), msg=repr(payload[-4:]))
        lines = [l for l in payload.strip().split("\n") if l]
        self.assertEqual(len(lines), 1, msg="必须单行，否则经典界面只解析到第一行")
        json.loads(lines[0][5:].strip())          # 必须能 parse

    def test_channel_emits_heartbeat_when_idle(self) -> None:
        """空闲时发心跳（经典界面靠它判连接存活）；非 `data:` 行经典界面会安全忽略。"""
        from agent.shell.classic_adapter.adapter import ClassicSseChannel

        channel = ClassicSseChannel(self.adapter, heartbeat=0.0)
        payload = channel.next_payload()          # 空队列 → 立即到心跳窗口
        self.assertTrue(payload.startswith("data:") or payload.startswith(":"),
                        msg=repr(payload[:40]))
        if payload.startswith("data:"):
            frame = json.loads(payload.strip()[5:].strip())
            self.assertEqual(frame["type"], C.EV_HEARTBEAT)

    def test_normalize_cid_matches_ui_rule(self) -> None:
        """经典界面的规则是 `/^[A-Za-z0-9_-]{8,128}$/`（`classic/js/core/boot.js` 的 `normalizeConversationId`）。"""
        self.assertEqual(C.normalize_cid(CID), CID)
        for bad in ("", "short", "has space", "a" * 129, None, "带中文"):
            self.assertEqual(C.normalize_cid(bad), "", msg=repr(bad))

    def test_tool_script_mapping_covers_known_tools(self) -> None:
        """工具名要翻成经典界面认识的 `script`，否则图标与中文名退化成默认。"""
        self.assertEqual(C.tool_script("read_file"), "read_file")
        self.assertEqual(C.tool_script("grep_files"), "grep_files")
        # 未知工具原样透传（经典界面有兜底），不抛错
        self.assertEqual(C.tool_script("brand_new_tool"), "brand_new_tool")

    def test_cid_exempt_set_is_exactly_two(self) -> None:
        """契约豁免的事件必须在前端先接住，否则会被静默丢掉。"""
        self.assertEqual(
            C.CID_EXEMPT_EVENTS,
            {C.EV_HEARTBEAT, C.EV_GLOBAL_SSE_READY, C.EV_PLUGINS_CHANGED},
        )

class ResumeContractTest(unittest.TestCase):
    """续传：存储坐标 `seq` 从落盘一路走到 SSE 的 `id:` 行，再用于断线续传。

    没有坐标时只有两个坏选择：重放全部（重复内容）或丢掉中间那段（静默缺口）。
    """

    def setUp(self) -> None:
        from agent.mechanisms.session_store import SessionStore

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.app = _FakeApp(self.root)
        # 续传要走真正的存储（`line_count` / `tail_from` 是它的能力）；
        # `_FakeApp` 里那个空壳 store 只够入站侧的形状测试用。
        self.store = SessionStore(self.root)
        self.app.store = self.store
        self.adapter = ClassicAdapter(self.app)

    def _seed(self, count: int = 4) -> str:
        """写一段带 `_seq` 的载荷（模拟 `App.session` 的落盘旁路）。"""
        from agent.core.events import Event

        kinds = ["turn_started", "input_claimed", "model_message", "turn_ended",
                 "assistant_delta", "tool_call"]
        events = []
        start = self.store.line_count(CID)
        for i in range(count):
            kind = kinds[i % len(kinds)]
            data: Dict[str, Any] = {"_seq": start + i}
            if kind == "input_claimed":
                data["content"] = f"用户{i}"
            elif kind == "model_message":
                data["content"] = f"助手{i}"
            elif kind == "tool_call":
                data.update({"call_id": f"c{i}", "name": "read_file", "arguments": {}})
            elif kind == "turn_started":
                data["run_id"] = f"run-{i}"
            events.append(Event(kind, data))
        self.store.append(CID, events)
        return CID

    def test_replay_frames_carry_seq(self) -> None:
        """回放的帧必须带坐标，否则浏览器重连时没有游标可用。"""
        self._seed()
        box = self.adapter.attach()
        self.adapter.replay_after(-1, only=box)
        seqs = []
        while True:
            frame = self.adapter.next_frame(box, timeout=0.05)
            if frame is None:
                break
            seqs.append(frame.get("seq"))
        self.assertTrue(seqs)
        self.assertTrue(all(isinstance(s, int) for s in seqs), msg=str(seqs))

    def test_replay_respects_cursor(self) -> None:
        """`seq > after` 且不重复补游标那一帧。"""
        self._seed(4)
        box = self.adapter.attach()
        self.adapter.replay_after(1, only=box)
        seqs = []
        while True:
            frame = self.adapter.next_frame(box, timeout=0.05)
            if frame is None:
                break
            if frame.get("seq") is not None:
                seqs.append(frame["seq"])
        self.assertTrue(seqs)
        self.assertTrue(all(s > 1 for s in seqs), msg=str(seqs))

    def test_replay_only_targets_given_channel(self) -> None:
        """续传只补这一条连接：别的连接的队列不能被塞进历史。"""
        self._seed()
        target = self.adapter.attach()
        other = self.adapter.attach()
        self.adapter.replay_after(-1, only=target)
        self.assertGreater(self._drain(target), 0)
        self.assertEqual(self._drain(other), 0)

    @staticmethod
    def _drain(box) -> int:
        count = 0
        while box.get_nowait() if not box.empty() else None:
            count += 1
        return count

    def test_sse_id_line_is_emitted_for_seq_frames(self) -> None:
        """SSE 的 `id:` 行是浏览器重连带 `Last-Event-ID` 的唯一来源。"""
        from agent.shell.classic_adapter.adapter import ClassicSseChannel

        self._seed()
        channel = ClassicSseChannel(self.adapter, heartbeat=999)
        self.adapter.replay_after(-1, only=channel._box)
        payload = channel.next_payload()
        self.assertTrue(payload.startswith("id: "), msg=repr(payload[:60]))
        head, _, rest = payload.partition("\n")
        self.assertTrue(head[4:].strip().isdigit(), msg=head)
        self.assertTrue(rest.startswith("data: "), msg=repr(rest[:40]))
        self.assertTrue(payload.endswith("\n\n"))

    def test_cursor_prefers_header_then_query(self) -> None:
        """`Last-Event-ID`（浏览器自动带）优先于 `?last_event_id=`；非法值回落 -1。"""
        class _Headers:
            def __init__(self, value):
                self.value = value

            def get(self, key):
                return self.value if key == "Last-Event-ID" else None

        self.assertEqual(self.adapter.cursor_of(_Headers("7"), {}), 7)
        self.assertEqual(self.adapter.cursor_of(_Headers("7"), {"last_event_id": "9"}), 9)
        self.assertEqual(self.adapter.cursor_of(_Headers(None), {"last_event_id": "9"}), 9)
        self.assertEqual(self.adapter.cursor_of(_Headers(None), {}), -1)
        # 不可信游标 → 从头（重放全部比断在半路安全）
        self.assertEqual(self.adapter.cursor_of(_Headers("abc"), {}), -1)
        self.assertEqual(self.adapter.cursor_of(_Headers("-5"), {}), -5)

    def test_latest_seq_reports_global_log_end(self) -> None:
        """`latest_seq` 是全局最大坐标；空仓库返回 -1。"""
        self.assertEqual(self.adapter.latest_seq(), -1)
        self._seed(3)
        self.assertEqual(self.adapter.latest_seq(), 2)

    def test_replay_never_leaks_seq_into_frame_payloads(self) -> None:
        """`_seq` 是位置元数据，不该以原名出现在给前端的帧里（会污染契约）。"""
        self._seed()
        box = self.adapter.attach()
        self.adapter.replay_after(-1, only=box)
        while True:
            frame = self.adapter.next_frame(box, timeout=0.05)
            if frame is None:
                break
            self.assertNotIn("_seq", frame)

class SubscriptionLifecycleTest(unittest.TestCase):
    """适配层对事件总线的订阅必须按需，不能是常驻观察者。

    常驻订阅的后果：`plugin_host.unload_all()` 之后再数总线订阅会多出 1 条——
    `unload_all()` 收不回别人的订阅，那条就成了谁都回收不掉的泄漏。
    而且没有客户端连着时做翻译本来就是白做功。
    """

    def setUp(self) -> None:
        from agent.app import build_app

        # 本类数的是总线订阅总数，所以必须排除插件贡献的订阅：
        # 插件可注册任意数量的订阅，混进来就分不清"适配层的订阅"与"插件的订阅"。
        no_plugins(self)
        self.app = build_app()
        self.addCleanup(self.app.dispose)
        self.classic = self.app.context.get(SERVICE_CLASSIC_ADAPTER)
        self.assertIsNotNone(self.classic, msg="适配层未装配")

    @staticmethod
    def _subs(app) -> int:
        return sum(len(v) for v in app.event_bus._subs.values())

    def test_no_subscription_without_clients(self) -> None:
        self.assertEqual(self._subs(self.app), 0, msg="没有 SSE 连接时不该占订阅")
        self.assertFalse(self.classic.subscribed)

    def test_subscribe_on_first_client_and_release_on_last(self) -> None:
        first = self.classic.attach()
        self.assertEqual(self._subs(self.app), 1)
        self.assertTrue(self.classic.subscribed)
        second = self.classic.attach()
        self.assertEqual(self._subs(self.app), 1, msg="第二条连接不该重复订阅")
        # 还有一条连着就不能退订
        self.classic.detach(first)
        self.assertEqual(self._subs(self.app), 1)
        self.assertTrue(self.classic.subscribed)
        # 最后一条断开 → 退订
        self.classic.detach(second)
        self.assertEqual(self._subs(self.app), 0)
        self.assertFalse(self.classic.subscribed)

    def test_bus_subscription_reaches_channels(self) -> None:
        """端到端：事件经真总线发布 → 翻译 → 到达连接队列。"""
        from agent.core.events import Event

        box = self.classic.attach()
        self.app.event_bus.publish(Event("turn_started", {
            "conversation_id": CID, "run_id": "r", "mode": "auto",
        }))
        types = []
        while True:
            frame = self.classic.next_frame(box, timeout=0.05)
            if frame is None:
                break
            types.append(frame["type"])
        self.assertIn(C.EV_CONVERSATION, types)
        self.assertIn(C.EV_RUN_STARTED, types)

    def test_dispose_is_idempotent(self) -> None:
        self.classic.attach()
        self.classic.dispose()
        self.classic.dispose()          # 再调一次不能抛
        self.assertEqual(self._subs(self.app), 0)

class UserConfirmRoundTripTest(unittest.TestCase):
    """确认的回路：用户在模态里选完，选择必须真的送到模型。

    经典界面的模态在「确认」后 POST `{conversation_id, confirm: <选择>, mode, model}`
    并读返回体的 `run_id`（见 `classic/js/chat/confirm.js` 的 `submitUserConfirm`）——
    也就是说它期待服务端把选择投回会话。只回一个 `{ok:true}` 会让模型永远
    等不到第二段，工具回路就断在"待确认"。
    """

    def setUp(self) -> None:
        from agent.mechanisms.session_store import SessionStore

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.app = _FakeApp(Path(self._tmp.name))
        # 直通回填要往会话日志里补一条事实，所以这里必须用真存储
        # （`_FakeApp` 的空壳 store 只够形状测试）
        self.app.store = SessionStore(Path(self._tmp.name))
        self.submitted: list = []
        app = self.app

        class _Mesh:
            def submit(self, cid, message):
                app.submitted.append((cid, dict(message)))
                return {"queued": False, "queued_count": 0, "run_id": "run-xyz"}

        self.app.mesh = _Mesh()
        self.app.submitted = self.submitted
        self.adapter = ClassicAdapter(self.app)

    def test_choice_is_filled_back_as_the_tool_result(self) -> None:
        """直通：用户的选择被写成那次 `user_confirm` 调用的返回值，不是新用户发言。

        把选择当新消息投回去的话，模型要重新理解「左」是什么、还得自己判断
        该不该再问一次，它会重复提问。直通后模型看到的是「工具返回了答案」。
        所以这里的断言：新回合的消息体是空的（没有新用户发言），
        答案是日志里那条合成 `tool_result`（`call_id` 与原调用配对）。
        """

        # 挂起状态由内核记在 SessionContext（管道后置观察者写），测试里手工置上
        session = self.adapter._session(CID)
        self.assertIsNotNone(session, msg="SessionContexts 应可用")
        session.pending_confirm = {"call_id": "call-77", "title": "选一个",
                                   "confirms": ["甲", "乙"], "multi": False}

        status, payload = self.adapter.user_confirm(CID, {"confirm": "甲"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["confirmed"])
        self.assertEqual(payload["run_id"], "run-xyz")          # 经典界面读它
        self.assertEqual(payload["resumed_call"], "call-77")    # 结果交回给了内核
        self.assertEqual(len(self.submitted), 1)
        cid, message = self.submitted[0]
        self.assertEqual(cid, CID)
        self.assertEqual(message["content"], "", msg="结果回灌不该伪装成一条用户发言")
        self.assertIn("attachments", message)
        # 结果走 `resume` 交给运行器：由它拼成 `tool_result` 事实。
        # 适配层不再自己往 store 写——那会变成第二个事实写点，也会绕开"写前查重"。
        resume = message.get("resume") or {}
        self.assertEqual(resume.get("call_id"), "call-77")
        self.assertEqual((resume.get("data") or {}).get("confirm"), "甲")
        # 作答已消费，挂起状态清掉（留着会让下次作答回到旧调用上）
        self.assertIsNone(self.adapter._session(CID).pending_confirm)

    def test_cancel_posts_empty_confirm_and_submits_nothing(self) -> None:
        """模态的「取消」发空 `confirm`：不能把它当成一次用户发言送出去。"""

        status, payload = self.adapter.user_confirm(CID, {"confirm": ""})
        self.assertEqual(status, 200)
        self.assertFalse(payload["confirmed"])
        self.assertEqual(self.submitted, [])

    def test_write_gate_confirm_id_still_works(self) -> None:
        """带 `confirm_id` 的写盘确认走内核既有的门控解锁，不经 mesh。"""

        calls: list = []

        class _Shell:
            def confirm(self, cid, confirm_id):
                calls.append((cid, confirm_id))
                return 200, {"confirmed": True, "conversation_id": cid, "confirm_id": confirm_id}

        self.adapter.adopt_shell(_Shell())
        status, payload = self.adapter.user_confirm(CID, {"confirm_id": "cf-1"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["confirmed"])
        self.assertEqual(calls, [(CID, "cf-1")])
        self.assertEqual(self.submitted, [], msg="门控解锁不该额外发消息")

    def test_confirm_id_and_text_together_do_both(self) -> None:
        """两者同时给：门控解锁 + 选择回填（同一个端点的两类语义）。"""

        class _Shell:
            def confirm(self, cid, confirm_id):
                return 200, {"confirmed": True}

        self.adapter.adopt_shell(_Shell())
        status, payload = self.adapter.user_confirm(CID, {"confirm_id": "cf-1", "confirm": "甲"})
        self.assertEqual(status, 200)
        self.assertEqual(len(self.submitted), 1)

    def test_invalid_conversation_id_rejected(self) -> None:

        status, payload = self.adapter.user_confirm("bad id!", {"confirm": "甲"})
        self.assertEqual(status, 400)
        self.assertEqual(self.submitted, [])

    def test_mesh_failure_reports_error_without_raising(self) -> None:
        """`mesh` 不可用时给结构化错误，不要抛——确认端点是 UI 的关键路径。"""

        self.app.mesh = None
        status, payload = self.adapter.user_confirm(CID, {"confirm": "甲"})
        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])

    def test_agree_mints_approval_id_for_the_option(self) -> None:
        """同意：结果是「同意」加宿主签发的 approval_id，并记下 option_id。"""

        session = self.adapter._session(CID)
        session.pending_confirm = {
            "call_id": "call-ap",
            "kind": "approval",
            "option_id": "video-1",
            "option_desc": "是否准许生成视频？",
        }
        status, payload = self.adapter.user_confirm(CID, {"approval": "agree"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["decision"], "同意")
        aid = payload["approval_id"]
        self.assertTrue(str(aid).startswith("apv_"))
        self.assertEqual(session.approvals[aid], "video-1")
        resume = self.submitted[0][1]["resume"]
        self.assertEqual(resume["call_id"], "call-ap")
        self.assertTrue(resume["ok"])
        self.assertEqual(resume["data"], {"decision": "同意", "approval_id": aid})
        self.assertIsNone(self.adapter._session(CID).pending_confirm)

    def test_reject_returns_disagree_and_stores_nothing(self) -> None:
        """驳回：结果是「不同意」，不签发通行证。"""

        session = self.adapter._session(CID)
        session.approvals.clear()
        session.pending_confirm = {
            "call_id": "call-ap",
            "kind": "approval",
            "option_id": "video-1",
            "option_desc": "是否准许生成视频？",
        }
        status, payload = self.adapter.user_confirm(CID, {"approval": "reject"})
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["confirmed"])
        self.assertEqual(payload["decision"], "不同意")
        self.assertEqual(payload["approval_id"], "")
        self.assertEqual(session.approvals, {})
        resume = self.submitted[0][1]["resume"]
        self.assertEqual(resume["data"], {"decision": "不同意"})

    def test_confirm_text_does_not_answer_an_approval(self) -> None:
        """选项文本不能冒充审批结果，待审批保持原样。"""

        session = self.adapter._session(CID)
        session.approvals.clear()
        session.pending_confirm = {
            "call_id": "call-ap",
            "kind": "approval",
            "option_id": "video-1",
        }
        status, payload = self.adapter.user_confirm(CID, {"confirm": "同意"})
        self.assertEqual(status, 200)
        self.assertFalse(payload["ok"])
        self.assertEqual(self.submitted, [])
        self.assertEqual(session.pending_confirm["call_id"], "call-ap")
        self.assertEqual(session.approvals, {})

class UiBundleTest(unittest.TestCase):
    """素材与内联打包。"""

    def test_tool_tag_shows_final_state_immediately(self) -> None:
        """工具结束时立刻写标签终态。

        若把标签挂到 `llm_done` 才刷新，一轮里多个工具会同时停在「进行中」
        直到整轮结束；取消场景还会把已完成的工具刷成失败。
        所以 `tool_end` 分支里必须当场定标签。
        """
        js = read_ui_js()
        start = js.find("function onToolEnd(ev){")
        self.assertNotEqual(start, -1, msg="onToolEnd 不见了")
        body = js[start:start + 1100]
        self.assertIn(
            'o.tag.textContent=(!!ok||!!ev.user_confirm_required||!!ev.approval_required)?"Done":"Fail"',
            body,
            msg="工具结束没有立刻写终态标签")
        self.assertIn(
            'o.tag.className="tag "+((!!ok||!!ev.user_confirm_required||!!ev.approval_required)?"ok":"bad")',
            body,
            msg="终态标签的样式没有一起写")

    def test_reasoning_stays_out_of_the_chat_area(self) -> None:
        """思考内容不能出现在对话区（它属于右侧步骤卡）。

        `promoteReasoningToChatIfNeeded()` 是实时渲染的容错：怕「模型只产出了思考、
        没有正文」时对话区一片空白，于是在 `done` 时把 `lastLlm.reasoningText`
        兜底追加成回答。它必须不被调用：

        ① 它不是数据：刷新后走 `loadConversationHistory()`，那段内容会消失，
           说明它本来就不该是「回答」；
        ② 思考已有正当归宿：`reasoning_delta` → `appendReasoningDelta()` → 右侧面板；
        ③ `done` 时 `streamAssistantText` 已被 `assistant` 分支
           （`finalizeAssistantStream()` 清空它）清掉，守卫必然放行 →
           思考被追加成对话区的第二个回答气泡（一轮 3 个气泡）。

        断言：`done` 分支里不得出现这个调用。
        """
        from agent.shell.web.ui_bundle import inline_ui_html

        html = inline_ui_html()
        self.assertIn("function promoteReasoningToChatIfNeeded(){", html,
                      msg="函数名变了：需重新确认思考提升的处理位置")
        self.assertNotIn("promoteReasoningToChatIfNeeded();", html,
                         msg="仍有地方在调用思考提升，思考会被填进对话区")
        self.assertIn("finalizeAssistantSt", html, msg="助手消息终态填充丢失")

    def test_llm_call_start_opens_a_step_card(self) -> None:
        """步骤卡必须起得来。

        经典界面的步骤卡由 `llm_round` 起卡。内核 不发"步"（"趟"是宿主的实现细节），
        所以适配层必须吸收两种词汇：历史记录用"步开始"、当前用
        "模型调用开始"（`llm_call_start`），对经典界面是同一件事。
        不起卡时步骤面板是空的（表现："步骤面板空空如也，但对话区一直持续输出"）。

        这条同时守住一个隐蔽依赖：`reasoning_delta` / `llm_response` / `llm_done`
        都以 `_step_had_llm` 为守卫——不在这里置位，那些帧会被静默丢弃。
        """
        stream = _stream()
        stream.translate("turn_started", {"conversation_id": CID})
        frames = stream.translate("llm_call_start", {
            "model": "m-x", "effort": "high", "messages": 3, "tools": 41,
        })
        kinds = [f["type"] for f in frames]
        self.assertIn(C.EV_LLM_ROUND, kinds, msg="不起卡则步骤面板为空")
        self.assertIn(C.EV_LLM_REQUEST, kinds)
        params = [f for f in frames if f["type"] == C.EV_LLM_REQUEST][0]["params"]
        self.assertEqual(params["model"], "m-x", msg="请求快照里的 model 不能是空串")
        self.assertEqual(params["messagesCount"], 3)
        self.assertEqual(params["toolsCount"], 41)
        # 守卫已置位：推理增量不再是空
        self.assertTrue(stream.translate("reasoning_delta", {"text": "想想"}),
                        msg="_step_had_llm 未置位会让推理增量被静默丢弃")

    def test_each_model_call_opens_its_own_card(self) -> None:
        """多趟往返时每轮各起一卡（工具前后各一张）。"""
        stream = _stream()
        stream.translate("turn_started", {"conversation_id": CID})
        first = stream.translate("llm_call_start", {"model": "m", "messages": 3, "tools": 5})
        stream.translate("model_message", {"content": "", "tool_calls": [
            {"id": "c1", "name": "echo", "arguments": {}}]})
        stream.translate("tool_call", {"call_id": "c1", "name": "echo", "arguments": {}})
        stream.translate("tool_result", {"call_id": "c1", "ok": True, "data": {}})
        second = stream.translate("llm_call_start", {"model": "m", "messages": 5, "tools": 5})
        r1 = [f for f in first if f["type"] == C.EV_LLM_ROUND][0]["round"]
        r2 = [f for f in second if f["type"] == C.EV_LLM_ROUND][0]["round"]
        self.assertEqual((r1, r2), (1, 2), msg="轮次必须递增（经典界面靠它分卡）")

    def test_plugin_event_bridges(self) -> None:
        """插件事件经 DOM 事件交给插件；插件开关也派发 DOM 事件。"""
        js = read_ui_js()
        self.assertIn('ai-agent:plugin-event', js)
        self.assertIn('ai-agent:plugins-changed', js)

    def test_inline_html_has_no_placeholders_left(self) -> None:
        from agent.shell.web.ui_bundle import inline_ui_html

        html = inline_ui_html()
        for token in ("{{CSS}}", "{{agent-ui.js}}", "{{APP_VERSION}}"):
            self.assertNotIn(token, html, msg=token)

    def test_inline_html_contains_all_five_scripts(self) -> None:
        """漏注入 `image-lightbox.js` 会让 `window.AIA` 缺失 → 附件四条链路静默失效。

        它们全都写成 `window.AIA && …`，所以没有报错、只是功能不见。
        """
        from agent.shell.web.ui_bundle import inline_ui_html

        html = inline_ui_html()
        # window.AIA 的唯一来源
        self.assertIn("global.AIA", html)
        self.assertIn("buildMsgAttachStrip", html)
        self.assertIn("openImageLightbox", html)
        # 高亮库与其封装
        self.assertIn("hljs", html)
        # 主题切换
        self.assertIn("toggle", html)
        # 主脚本（取一个只属于它的内部函数名做指纹）
        self.assertIn("normalizeConversationId", html)

    def test_light_hljs_sheet_is_scoped(self) -> None:
        """两套高亮配色同页共存，浅色那套必须限定在 `[data-ui-theme="light"]` 下。"""
        from agent.shell.web.ui_bundle import scope_hljs_css

        self.assertEqual(scope_hljs_css(".hljs{color:red}", "P"), "P .hljs{color:red}")
        # 不能误伤 `xxx.hljs` 这类复合选择器
        self.assertEqual(scope_hljs_css("a.hljs{color:red}", "P"), "a.hljs{color:red}")

if __name__ == "__main__":
    unittest.main()

class HistoryAttachmentReplayTest(unittest.TestCase):
    """带附件的会话刷新后必须能再看图。

    事实里图片以 `data:<mime>;base64,<数据>` 内联在多模态 content 数组里，
    所以回显不需要另找来源 —— 但 `history_items` 得真的把它们解出来，
    否则前端只会显示「图片预览已失效」。
    """

    PNG_B64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGMAAQAABQAB"
        "DQottAAAAABJRU5ErkJggg=="
    )

    def _events(self):
        """真实事实形状：附件在 `input_claimed.data["attachments"]`。

        （容易搞错：`content` 里的多模态数组是 `session_log` 为模型请求派生的，
        事实里 `content` 就是纯文本。按多模态数组造数据会得到"测试通过、真实链路
        仍然失败"的假绿。）
        """
        from agent.core.events import Event

        return [
            Event("turn_started", {"text": "看这张图"}),
            Event("input_claimed", {"content": "看这张图",
                                    "attachments": [{"mime": "image/png",
                                                     "data_base64": self.PNG_B64}]}),
            Event("model_message", {"content": "我看到一张图。"}),
        ]

    def _events_inline_multimodal(self):
        """兜底形态：历史记录里可能出现内联多模态 content（也要认）。"""
        from agent.core.events import Event

        return [
            Event("input_claimed", {"content": [
                {"type": "text", "text": "看这张图"},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/png;base64,{self.PNG_B64}"}},
            ]}),
        ]

    def test_history_items_carry_attachments_and_had_images(self) -> None:
        from agent.shell.classic_adapter.inbound import history_items

        items, resolved = history_items(self._events())
        user = items[0]
        self.assertEqual(user["role"], "user")
        self.assertEqual(user["content"], "看这张图",
                         msg="正文要从多模态数组里取出来，不能把数组 JSON 化")
        self.assertTrue(user.get("had_images"), msg="必须给出 had_images")
        atts = user.get("attachments") or []
        self.assertEqual(len(atts), 1, msg="必须产出 attachments（前端据此渲染截图条）")
        self.assertEqual(atts[0]["mime"], "image/png")
        self.assertEqual(len(resolved), 1, msg="同时要把字节交给调用方登记")
        self.assertEqual(resolved[0]["data_base64"], self.PNG_B64)

    def test_history_tool_done_keeps_images(self) -> None:
        """刷新后看图条目仍带着像素，展开面板才能把图画出来。"""
        from agent.core.events import Event
        from agent.shell.classic_adapter.inbound import history_items

        items, _resolved = history_items([
            Event("tool_started", {
                "call_id": "c1", "name": "read_image",
                "arguments": {"path": r"C:\Temp\qq5.png"},
            }),
            Event("tool_done", {
                "call_id": "c1",
                "data": {"path": r"C:\Temp\qq5.png"},
                "attachments": [{"mime": "image/png", "data_base64": self.PNG_B64}],
            }),
        ])
        tool = items[0]
        self.assertEqual(tool["status"], "done")
        self.assertEqual(tool["images"], [{"mime": "image/png", "data_base64": self.PNG_B64}])
        self.assertNotIn("data_base64", tool.get("preview") or "")

    def test_history_tool_canceled_stays_distinct_from_failed(self) -> None:
        """停止是独立终态，刷新后标题才能和失败分开上色。"""
        from agent.core.events import Event
        from agent.shell.classic_adapter.inbound import history_items

        items, _resolved = history_items([
            Event("tool_started", {"call_id": "c1", "name": "run_command", "arguments": {}}),
            Event("tool_canceled", {"call_id": "c1", "reason": "user_stop"}),
        ])
        self.assertEqual(items[0]["status"], "canceled")

    def test_history_replays_each_reasoning_before_its_tools(self) -> None:
        """思考定稿在 `model_message.reasoning_content`，刷新后按轮插回工具卡前面。"""
        from agent.core.events import Event
        from agent.shell.classic_adapter.inbound import history_items

        items, _resolved = history_items([
            Event("llm_ended", {"status": "done", "elapsed_ms": 3200}),
            Event("model_message", {
                "content": "",
                "reasoning_content": "先看窗口",
                "tool_calls": [{"id": "c1"}],
            }),
            Event("tool_started", {"call_id": "c1", "name": "run_command", "arguments": {}}),
            Event("tool_done", {"call_id": "c1", "data": {"ok": True}}),
            Event("llm_ended", {"status": "done", "elapsed_ms": "4100"}),
            Event("model_message", {
                "content": "播好了",
                "reasoning_content": "再等一下",
            }),
            Event("model_message", {"content": "只有正文", "reasoning_content": "  \n"}),
        ])
        self.assertEqual([i["role"] for i in items],
                         ["think", "tool", "think", "assistant", "assistant"])
        self.assertEqual(items[0]["content"], "先看窗口")
        self.assertEqual(items[0]["elapsed_ms"], 3200)
        self.assertEqual(items[2]["content"], "再等一下")
        self.assertEqual(items[2]["elapsed_ms"], 4100)
        self.assertEqual(items[4]["content"], "只有正文")

    def test_history_prefers_reasoning_time(self) -> None:
        """思考卡只显示推理时长，不再用整次模型调用时长。"""
        from agent.core.events import Event
        from agent.shell.classic_adapter.inbound import history_items

        items, _resolved = history_items([
            Event("llm_ended", {"status": "done", "elapsed_ms": 3200,
                                "reasoning_ms": 1200}),
            Event("model_message", {"content": "正文", "reasoning_content": "想"}),
        ])
        self.assertEqual(items[0]["role"], "think")
        self.assertEqual(items[0]["elapsed_ms"], 1200)
        self.assertEqual(items[1], {"role": "assistant", "content": "正文"})

    def test_attachment_id_is_recomputable(self) -> None:
        """id 必须从事实派生：刷新前后一致，否则浏览器不会重试那张失败的图。"""
        from agent.shell.classic_adapter.inbound import history_items

        first = history_items(self._events())[0][0]["attachments"][0]["id"]
        again = history_items(self._events())[0][0]["attachments"][0]["id"]
        self.assertEqual(first, again)

    def test_inline_multimodal_content_is_also_accepted(self) -> None:
        """兜底形态：content 直接是多模态数组时也要解出附件。"""
        from agent.shell.classic_adapter.inbound import history_items

        items, resolved = history_items(self._events_inline_multimodal())
        self.assertEqual(items[0]["content"], "看这张图")
        self.assertEqual(len(items[0].get("attachments") or []), 1)
        self.assertEqual(len(resolved), 1)

    def test_plain_text_message_is_unaffected(self) -> None:
        from agent.core.events import Event
        from agent.shell.classic_adapter.inbound import history_items

        items, resolved = history_items([Event("input_claimed", {"content": "只有文字"})])
        self.assertEqual(items, [{"role": "user", "content": "只有文字"}])
        self.assertEqual(resolved, [])
