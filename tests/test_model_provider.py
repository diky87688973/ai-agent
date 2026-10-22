# -*- coding: utf-8 -*-
"""模型 provider 的请求级模型选择。

为什么要能按请求选模型：一个 provider 实例绑定一个 `base_url` / `api_key`，
但同一个网关下往往有多个模型名可选。
把模型放进请求，provider 便可复用，不必按模型各建一个实例 ——
会话选择因此只影响装配时注入的请求参数，不影响链上的模块。
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.core.ports import LogicalRequest  # noqa: E402
from agent.mechanisms.providers.base import ModelRequestError  # noqa: E402
from agent.mechanisms.providers.openai import OpenAICompatibleProvider  # noqa: E402
from tests.testkit import no_plugins  # noqa: E402

_PNG_B64 = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
            "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def _img() -> dict:
    """附件形态与上传链路一致（`mime` + `data_base64`）。"""
    return {"mime": "image/png", "data_base64": _PNG_B64}


class _Capturing(OpenAICompatibleProvider):
    """把 `_post_stream` 换掉：不发网络请求，只记下 payload。"""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.payloads: list[dict] = []

    def _post_stream(self, url, payload):        # type: ignore[override]
        self.payloads.append(payload)
        return iter(())

def _provider(model: str = "default-model") -> _Capturing:
    return _Capturing(base_url="https://example.invalid", api_key="k", model=model)

class ProviderStreamTimeoutTest(unittest.TestCase):
    def test_openai_stream_timeout_is_bounded(self) -> None:
        class _StalledResponse:
            def __iter__(self):
                time.sleep(0.2)
                return iter(())

            def close(self) -> None:
                pass

        provider = OpenAICompatibleProvider(
            base_url="https://example.invalid", api_key="k", model="m", timeout=0.02,
        )
        request = LogicalRequest(messages=[{"role": "user", "content": "q"}], tools=[])
        with mock.patch(
            "agent.mechanisms.providers.openai.urllib.request.urlopen",
            return_value=_StalledResponse(),
        ):
            with self.assertRaises(ModelRequestError) as caught:
                list(provider.stream(request))
        self.assertIn("超时", caught.exception.detail)


class RequestLevelModelTest(unittest.TestCase):

    def test_request_model_wins_over_instance_default(self) -> None:
        p = _provider("default-model")
        list(p.stream(LogicalRequest(messages=[], tools=[], model="chosen-model")))
        self.assertEqual(p.payloads[0]["model"], "chosen-model",
                         msg="请求里指定了模型就必须用它（会话级选择靠这条生效）")

    def test_empty_request_model_falls_back_to_instance_default(self) -> None:
        """空串 = 不指定 ⇒ 用实例默认模型，既有调用方行为不变。"""
        p = _provider("default-model")
        list(p.stream(LogicalRequest(messages=[], tools=[])))
        self.assertEqual(p.payloads[0]["model"], "default-model")

    def test_whitespace_is_treated_as_unspecified(self) -> None:
        p = _provider("default-model")
        list(p.stream(LogicalRequest(messages=[], tools=[], model="   ")))
        self.assertEqual(p.payloads[0]["model"], "default-model")

    def test_local_model_check_is_per_requested_model(self) -> None:
        """本地模型的判定同理：默认是云端、本次选本地时不能照旧下发推理档位。"""
        p = _provider("plain-model")
        self.assertFalse(p._is_local_model())
        self.assertTrue(p._is_local_model("local-model"))

    def test_effort_still_reaches_the_wire(self) -> None:
        """推理档位照常透传到请求载荷。"""
        p = _provider()
        list(p.stream(LogicalRequest(messages=[], tools=[], effort="max")))
        self.assertEqual(p.payloads[0].get("reasoning_effort"), "max")
if __name__ == "__main__":
    unittest.main()

class ImagesAlwaysReachTheWireTest(unittest.TestCase):
    """图片一律原样发给模型 —— 不按模型名猜能力、不做降级剥图。

    "名字含 vision 才算视觉模型"是猜的判据：`deepseek-flash` 这类名字里没有
    `vision` 的模型其实支持图片，被剥图后模型只能看到一句占位说明，
    用户以为发了图、模型却什么也没看到。
    """

    def test_image_block_survives_into_the_payload(self) -> None:
        p = _provider("deepseek-flash")
        list(p.stream(LogicalRequest(messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "这张图什么颜色？"},
                {"type": "image_url",
                 "image_url": {"url": "data:image/png;base64,AA"}},
            ],
        }], tools=[])))
        sent = p.payloads[0]["messages"][0]["content"]
        self.assertIsInstance(sent, list, msg="多模态 content 必须原样下发")
        kinds = [part.get("type") for part in sent]
        self.assertIn("image_url", kinds, msg="图片块不能被剥掉")
        self.assertIn("text", kinds, msg="文字块要保留")

    def test_plain_text_message_is_untouched(self) -> None:
        p = _provider("deepseek-flash")
        list(p.stream(LogicalRequest(messages=[
            {"role": "user", "content": "只有文字"}], tools=[])))
        self.assertEqual(p.payloads[0]["messages"][0]["content"], "只有文字")

class SessionModelSelectionTest(unittest.TestCase):
    """会话级模型选择：选中即生效、可读回、跨进程仍在。

    选择必须落盘：只活在内存里的话，换个进程/换台机器打开同一会话就回默认，
    而"选了却没生效"比"没有这个功能"更坏 —— 用户以为换成了另一个模型。
    """

    def setUp(self) -> None:
        import tempfile
        from pathlib import Path as _P

        self._tmp = tempfile.TemporaryDirectory()
        self.dir = _P(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _state(self, default_model: str = "base-model"):
        from agent.mechanisms.live_state import LiveState

        return LiveState(storage_dir=self.dir, default_model=default_model)

    def test_select_then_read_back(self) -> None:
        st = self._state()
        self.assertEqual(st.get_model("cid-12345678"), "base-model",
                         msg="未选择时应回落到全局默认")
        st.set_model("cid-12345678", "chosen-model")
        self.assertEqual(st.get_model("cid-12345678"), "chosen-model")

    def test_choice_survives_a_new_process(self) -> None:
        """换一个 LiveState 实例（= 换进程）后选择仍在 —— 靠落盘，不靠内存。"""
        self._state().set_model("cid-12345678", "chosen-model")
        again = self._state()
        self.assertEqual(again.get_model("cid-12345678"), "chosen-model")

    def test_empty_clears_the_choice(self) -> None:
        st = self._state()
        st.set_model("cid-12345678", "chosen-model")
        st.set_model("cid-12345678", "")
        self.assertEqual(st.get_model("cid-12345678"), "base-model")

    def test_read_only_is_never_used(self) -> None:
        """只读会话（`is_read_only` 的 cid）不落盘 —— 同 todo 的白名单纪律。"""
        st = self._state()
        st.set_model("../../etc/passwd", "x")
        self.assertEqual(list(self.dir.iterdir()), [],
                         msg="非法 cid 不得拼出路径")

class SessionStateFileTest(unittest.TestCase):
    """会话状态文件：模型 / 模式 / 档位 / 清单同住一份，可跨进程读回。

    这些用例守的是存储契约，不是某个工具的行为：文件结构一旦变回
    "清单平铺、模型混在顶层"，读写两边就会互相覆盖。
    """

    CID = "cid-12345678"

    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.state_dir = Path(self._tmp.name) / "session_state"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _state(self, default_model: str = "base-model"):
        from agent.mechanisms.live_state import LiveState

        return LiveState(
            storage_dir=self.state_dir,
            default_model=default_model,
        )

    def _todo(self, items=None):
        return {
            "list_id": "list-1",
            "items": items or [{"id": "1", "text": "p1", "done": False}],
            "collapsed": False,
        }

    def _read(self) -> dict:
        return json.loads((self.state_dir / f"{self.CID}.json").read_text(encoding="utf-8"))

    def test_file_nests_todo_and_keeps_state_flat(self) -> None:
        st = self._state()
        st.set_model(self.CID, "chosen-model")
        st.set_todo(self.CID, self._todo())
        st.set_mode(self.CID, "plan")
        self.assertTrue(st.set_reasoning_effort(self.CID, "max"))

        raw = self._read()
        self.assertEqual(raw["model"], "chosen-model")
        self.assertEqual(raw["mode"], "plan")
        self.assertEqual(raw["effort"], "max")
        self.assertEqual(raw["todo"]["list_id"], "list-1")
        self.assertNotIn("items", raw, msg="清单字段不得再平铺在顶层")
        self.assertNotIn("list_id", raw)

    def test_every_component_survives_a_new_process(self) -> None:
        st = self._state()
        st.set_model(self.CID, "chosen-model")
        st.set_todo(self.CID, self._todo())
        st.set_mode(self.CID, "execute")
        st.set_reasoning_effort(self.CID, "max")

        again = self._state()
        self.assertEqual(again.get_model(self.CID), "chosen-model")
        self.assertEqual(again.get_mode(self.CID), "execute")
        self.assertEqual(again.get_reasoning_effort(self.CID), "max")
        self.assertEqual(again.get_todo(self.CID)["items"][0]["text"], "p1")

    def test_closing_todo_does_not_wipe_the_model(self) -> None:
        """`close` 只清清单：写盘前必须读回其余分量，否则会覆盖模型。"""
        first = self._state()
        first.set_model(self.CID, "chosen-model")
        first.set_todo(self.CID, self._todo())

        fresh = self._state()
        fresh.set_todo(self.CID, None)
        self.assertIsNone(fresh.get_todo(self.CID))
        self.assertEqual(fresh.get_model(self.CID), "chosen-model")
        raw = self._read()
        self.assertNotIn("todo", raw)
        self.assertEqual(raw["model"], "chosen-model")

    def test_stale_flat_file_is_ignored(self) -> None:
        """只认嵌套结构：平铺把清单字段写在顶层的文件不算会话状态。

        读路径一旦容忍第二种形状，每次改动都要同时证明两套都对。
        """
        self.state_dir.mkdir(parents=True)
        (self.state_dir / f"{self.CID}.json").write_text(
            json.dumps({**self._todo(), "model": "flat-model"}, ensure_ascii=False),
            encoding="utf-8",
        )

        st = self._state()
        self.assertIsNone(st.get_todo(self.CID))
        self.assertEqual(st.get_model(self.CID), "flat-model",
                         msg="顶层 model 仍是合法键，只有清单必须嵌套")

class AppModelConfigTest(unittest.TestCase):
    """装配层的模型来源状态：目录接管、回落与清空。"""

    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _app(self):
        from agent.app import App
        from agent.core.context import (
            SERVICE_LIVE_STATE,
            SERVICE_PROVIDER,
            AppContext,
        )
        from agent.mechanisms.live_state import LiveState

        ctx = AppContext()
        state = LiveState(storage_dir=self.dir / "state", default_model="base-model")
        router = _RecordingRouter()
        ctx.register(SERVICE_LIVE_STATE, state)
        ctx.register(SERVICE_PROVIDER, router)
        return App(ctx), state, router

    def test_model_catalog_is_optional(self) -> None:
        app, _state, _router = self._app()
        self.assertIsNone(app.model_catalog)

        from agent.core.context import SERVICE_MODEL_CATALOG

        catalog = object()
        app.context.register(SERVICE_MODEL_CATALOG, catalog)
        self.assertIs(app.model_catalog, catalog)

    def test_model_config_reports_source_and_degrade(self) -> None:
        from types import SimpleNamespace

        from agent.core.context import SERVICE_MODEL_CATALOG

        app, _state, _router = self._app()
        self.assertEqual(app.model_config(), {
            "source": "none", "authoritative": False, "degraded": True})
        catalog = SimpleNamespace(snapshot=lambda: SimpleNamespace(authoritative=True))
        app.context.register(SERVICE_MODEL_CATALOG, catalog)
        app.model_config_state = "catalog"
        self.assertEqual(app.model_config(), {
            "source": "catalog", "authoritative": True, "degraded": False})

    def test_unknown_session_model_falls_back_to_default(self) -> None:
        """旧标签页拿着已删除的模型 id 时，读取点收敛到默认值并写回。"""
        app, state, _router = self._app()
        app._available_models = ["m-one", "m-two"]
        state.set_model("cid-model-1", "gone-model")
        self.assertEqual(app.model_for("cid-model-1"), "base-model")
        self.assertEqual(state.get_model("cid-model-1"), "base-model")

    def test_known_session_model_is_kept(self) -> None:
        app, state, _router = self._app()
        app._available_models = ["m-one", "m-two"]
        state.set_model("cid-model-2", "m-two")
        self.assertEqual(app.model_for("cid-model-2"), "m-two")

    def test_reload_is_ignored_when_catalog_is_authoritative(self) -> None:
        app, _state, _router = self._app()
        app.model_config_state = "catalog"
        note = app.reload_model_config(config_path=self.dir / "missing.ini")
        self.assertIn("目录权威", note)
        self.assertEqual(app.model_config_state, "catalog")

    def test_refresh_switches_catalog_on_and_off(self) -> None:
        """插件装卸必须重算权威：目录接管时刷新路由，注销后回退且清空清单。"""
        from agent.capabilities.model_catalog import ModelCatalog, ModelEntry
        from agent.core.context import SERVICE_MODEL_CATALOG

        app, state, router = self._app()
        catalog = ModelCatalog()
        app.context.register(SERVICE_MODEL_CATALOG, catalog)
        drop = catalog.set_source("multi_model", [
            ModelEntry.from_options(id="a", provider="openai", is_default=True),
            ModelEntry.from_options(id="b", provider="openai"),
        ])
        self.assertEqual(app.refresh_model_config(config_path=self.dir / "missing.ini"), "")
        self.assertEqual(app.model_config_state, "catalog")
        self.assertEqual(app.available_models(), ["a", "b"])
        self.assertEqual(state.default_model, "a")
        self.assertEqual(router.policy, {
            "allowed_ids": ["a", "b"], "default_id": "a",
            "fallback_to_default": False})
        drop()
        note = app.refresh_model_config(config_path=self.dir / "missing.ini")
        self.assertIn("未配置可用模型", note)
        self.assertEqual(app.model_config_state, "none")
        self.assertEqual(app.available_models(), [])
        self.assertEqual(router.policy, {
            "allowed_ids": [], "default_id": "", "fallback_to_default": False})

class _RecordingRouter:
    """记录 reload 调用；不真正建 provider（重建逻辑由 provider_registry 测）。"""

    def __init__(self) -> None:
        self.provider = object()
        self.policy = None

    def reload_default(self, provider) -> None:
        self.provider = provider

    def reload_policy(self, **kwargs) -> None:
        self.policy = dict(kwargs)


class AvailableModelsWireTest(unittest.TestCase):
    """`/health` 的 `allowed_models` 必须给出完整清单。

    它是经典 UI 模型下拉的唯一数据来源，也是选择时的白名单。
    清单不得退化成"只有当前模型"——那样下拉只画一项，且选择被白名单校验拒掉。
    """

    def _app(self):
        from agent.app import build_app

        # 不装插件：本类钉的是 `/health` 与 `allowed_models` 的接线，
        # 插件目录（开发者本机的多模型配置）会把清单整体换掉，与本类无关。
        no_plugins(self)
        app = build_app()
        app._available_models = ["m-one", "m-two", "m-three"]
        return app

    def test_health_lists_all_configured_models(self) -> None:
        from agent.shell.classic_adapter.adapter import ClassicAdapter

        app = self._app()
        body = ClassicAdapter(app).health()
        self._assert_complete(body, str(getattr(app.provider, "model", "") or ""))

    def test_current_model_is_always_in_the_list(self) -> None:
        """`model` 必须在清单里，否则 UI 的白名单校验会丢弃它（顶栏永远"加载中"）。"""
        from agent.shell.classic_adapter.adapter import ClassicAdapter

        app = self._app()
        app._available_models = ["other-a", "other-b"]
        body = ClassicAdapter(app).health()
        provider_model = str(getattr(app.provider, "model", "") or "")
        if provider_model:
            self.assertIn(provider_model, body.get("allowed_models") or [])

    def test_shell_health_also_lists_all_models(self) -> None:
        from agent.shell.web import create_server

        app = self._app()
        _srv, shell = create_server(app, host="127.0.0.1", port=0)
        _status, body = shell.health()
        self.assertEqual(body.get("allowed_models"), ["m-one", "m-two", "m-three"])

    def test_health_does_not_invent_a_model_in_degraded_state(self) -> None:
        """`none` 时不能拿 provider 的占位模型充数：那个 id 实际选不了。"""
        from agent.shell.web import create_server

        app = self._app()
        app.model_config_state = "none"
        app._available_models = []
        app.live_state.default_model = ""
        _srv, shell = create_server(app, host="127.0.0.1", port=0)
        _status, body = shell.health()
        self.assertEqual(body.get("allowed_models"), [])
        self.assertEqual(body.get("model"), "")

    def _assert_complete(self, body, provider_model: str) -> None:
        """清单 = 装配面名单 + 当前模型（当前模型会被前置，不能按位置断言）。"""
        expected = {"m-one", "m-two", "m-three"}
        allowed = list(body.get("allowed_models") or [])
        self.assertTrue(expected <= set(allowed), allowed)
        extra = set(allowed) - expected
        self.assertEqual(extra, {provider_model} if provider_model else set(), allowed)


class CatalogAuthorityAtAssemblyTest(unittest.TestCase):
    """插件目录一旦权威，装配末尾就把模型清单与路由策略换成目录的。

    这条分支只在真的装了带目录来源的插件时走到。别的用例都用 `no_plugins`
    把开发机上的插件隔离掉了（否则结果取决于本机私有配置），所以这里自己造一个
    最小插件树来钉住这段装配逻辑。
    """

    _PLUGIN = '''\
from agent.capabilities.model_catalog import ModelEntry

def register(ctx):
    return ctx.add_model_catalog(lambda: (
        ModelEntry.from_options(id="cat-a", provider="openai", is_default=True),
        ModelEntry.from_options(id="cat-b", provider="openai"),
    ))
'''

    def test_catalog_entries_become_the_model_list(self) -> None:
        from agent.app import build_app
        from agent.mechanisms.live_state import LiveState
        from agent.mechanisms.mesh import MeshState
        from agent.mechanisms.session_store import SessionStore

        tmp = Path(tempfile.mkdtemp(prefix="catalogasm_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        plugins = tmp / "plugins" / "catalog_demo"
        plugins.mkdir(parents=True)
        (plugins / "plugin.py").write_text(self._PLUGIN, encoding="utf-8")
        manifest = tmp / "plugins.ini"
        manifest.write_text("[plugin:catalog_demo]\n", encoding="utf-8")

        app = build_app(
            plugins_dir=tmp / "plugins",
            plugins_path=manifest,
            store=SessionStore(tmp / "data"),
            live_state=LiveState(storage_dir=tmp / "state"),
            mesh=MeshState(storage_dir=tmp / "mesh"),
            backup_root=tmp / "bk",
            recycle_root=tmp / "rc",
        )
        self.addCleanup(app.dispose)
        self.assertEqual(app.model_config_state, "catalog")
        self.assertEqual(app.available_models(), ["cat-a", "cat-b"])
        self.assertEqual(app.live_state.default_model, "cat-a")
        self.assertEqual(app.provider.allowed_models, ("cat-a", "cat-b"))

class UserFacingTextTest(unittest.TestCase):
    """用户可见的文案不得混入内部术语。

    `_DEEPSEEK_HTTP_HINTS` 的取值会作为 `ModelRequestError.detail` 直接回给用户，
    所以它只能说清"哪一端出了问题"。

    只查这些字符串的取值，不查注释。
    """

    #: 不该出现在用户可见文案里的词
    INTERNAL_TERMS = ("上一版", "原项目", "重构", "移植")

    def test_http_hints_are_user_facing_and_history_free(self) -> None:
        from agent.mechanisms.providers.openai import _DEEPSEEK_HTTP_HINTS

        self.assertEqual(len(self.INTERNAL_TERMS), 4, "禁用词表不得被误改")
        self.assertEqual(len(set(self.INTERNAL_TERMS)), 4, "禁用词不得重复")
        self.assertTrue(_DEEPSEEK_HTTP_HINTS, "提示表不该为空")
        for status, text in _DEEPSEEK_HTTP_HINTS.items():
            for bad in self.INTERNAL_TERMS:
                self.assertNotIn(
                    bad, text,
                    f"HTTP {status} 的提示语含内部术语 {bad!r}：{text!r} —— "
                    "它直接显示给用户，应说清是「模型服务端」的问题")

    def test_500_and_503_name_the_model_server(self) -> None:
        from agent.mechanisms.providers.openai import _DEEPSEEK_HTTP_HINTS

        for status in (500, 503):
            self.assertIn("服务端", _DEEPSEEK_HTTP_HINTS[status],
                          f"HTTP {status} 的提示应指明是「服务端」的问题")

    def test_deepseek_official_error_codes_are_mapped(self) -> None:
        """与 https://api-docs.deepseek.com/quick_start/error_codes 七码对齐。"""
        from agent.mechanisms.providers.openai import _DEEPSEEK_HTTP_HINTS

        self.assertEqual(
            sorted(_DEEPSEEK_HTTP_HINTS),
            [400, 401, 402, 422, 429, 500, 503],
        )


class ReasonNotReplayedTest(unittest.TestCase):
    """历史推理不回传内容：它必然未命中缓存，回传等于每轮多算几万 token。

    但键必须留着：DeepSeek 思考模式下带 `tool_calls` 的 assistant 消息要回传
    `reasoning_content`（空串可接受），缺键会 400。
    """

    def _sample(self):
        return [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1", "reasoning_content": "旧推理",
             "tool_calls": [{"id": "c1", "name": "t", "arguments": {}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "结果"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2", "reasoning_content": "本轮推理"},
        ]

    def test_cut_clears_the_content_but_keeps_the_key_for_tool_messages(self) -> None:
        from agent.mechanisms.providers.openai import _to_wire_messages

        wire = _to_wire_messages(self._sample(), keep_reasoning_from=5)
        self.assertEqual(wire[2].get("reasoning_content"), "",
                         msg="历史轮的工具消息必须保留键，只清空内容")
        self.assertEqual(wire[5].get("reasoning_content"), "本轮推理")

    def test_plain_assistant_before_the_cut_drops_the_key(self) -> None:
        from agent.mechanisms.providers.openai import _to_wire_messages

        wire = _to_wire_messages([
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1", "reasoning_content": "旧推理"},
            {"role": "user", "content": "u2"},
        ], keep_reasoning_from=2)
        self.assertNotIn("reasoning_content", wire[1],
                         msg="纯文本 assistant 没有回传要求，历史轮直接摘键")

    def test_tool_message_without_reasoning_gets_an_empty_key(self) -> None:
        """没有思维链记录的工具消息也要补空串：缺键与空串在 API 侧不等价。"""
        from agent.mechanisms.providers.openai import _to_wire_messages

        wire = _to_wire_messages([
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "", "tool_calls": [
                {"id": "c1", "name": "t", "arguments": {}}]},
            {"role": "tool", "tool_call_id": "c1", "content": "r"},
        ], keep_reasoning_from=1)
        self.assertEqual(wire[1].get("reasoning_content"), "")

    def test_cut_none_keeps_everything(self) -> None:
        from agent.mechanisms.providers.openai import _to_wire_messages

        wire = _to_wire_messages(self._sample(), keep_reasoning_from=None)
        self.assertEqual(wire[2].get("reasoning_content"), "旧推理")

    def test_tool_calls_survive_the_cut(self) -> None:
        from agent.mechanisms.providers.openai import _to_wire_messages

        wire = _to_wire_messages(self._sample(), keep_reasoning_from=5)
        calls = wire[2].get("tool_calls") or []
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["function"]["name"], "t")

    def test_original_messages_are_not_mutated(self) -> None:
        from agent.mechanisms.providers.openai import _to_wire_messages

        sample = self._sample()
        _to_wire_messages(sample, keep_reasoning_from=5)
        self.assertEqual(sample[2].get("reasoning_content"), "旧推理")

    def test_provider_passes_the_boundary_and_defaults_to_stripping(self) -> None:
        from agent.mechanisms.providers.openai import OpenAICompatibleProvider

        src = (ROOT / "agent/mechanisms/providers/openai.py").read_text(encoding="utf-8")
        self.assertIn('getattr(request, "turn_start", None)', src)
        provider = OpenAICompatibleProvider(base_url="http://x/v1", api_key="k", model="m")
        self.assertFalse(provider.replay_history_reasoning)
        self.assertTrue(OpenAICompatibleProvider(
            base_url="http://x/v1", api_key="k", model="m",
            replay_history_reasoning=True).replay_history_reasoning)


class TurnStartAssemblyTest(unittest.TestCase):
    """装配时把"本轮起点"标出来，provider 才有裁的依据。"""

    def test_model_module_marks_turn_start(self) -> None:
        src = (ROOT / "agent/core/modules/model_mod.py").read_text(encoding="utf-8")
        self.assertIn("turn_start=len(messages) - len(dialogue) + turn_start", src)

    def test_port_default_keeps_everything(self) -> None:
        from agent.core.ports import LogicalRequest

        req = LogicalRequest(messages=[{"role": "user", "content": "x"}], tools=[])
        self.assertIsNone(req.turn_start)
