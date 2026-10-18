# -*- coding: utf-8 -*-
"""模型目录单元测试：替换语义、默认值、无效条目、热读与 provider 缓存。

重点覆盖"会悄悄错"的几处：

- 来源从 3 条改成 0 条后，`authoritative` 必须跟着变假；
- 重复 id 必须**整批拒绝**并保留旧目录，不能半新半旧；
- 未知 provider 只跳过该条，不能连累同批其它模型；
- 热读回调抛异常时沿用上一份好配置，模型列表不能瞬间清零。
"""
from __future__ import annotations

import unittest
from unittest import mock

from agent.capabilities.model_catalog import CatalogSnapshot, ModelCatalog, ModelEntry
from agent.capabilities.plugins import PluginContext
from agent.capabilities.registry import ToolRegistry
from agent.mechanisms.model_provider import OpenAICompatibleProvider

_OPENAI = {
    "base_url": "https://example.invalid/v1",
    "api_key": "k-test",
    "model": "m-test",
}


def _entry(model_id: str, *, provider: str = "openai", default: bool = False,
           label: str = "") -> ModelEntry:
    return ModelEntry.from_options(
        id=model_id, provider=provider, label=label,
        options=_OPENAI if provider == "openai" else {}, is_default=default,
    )


class ModelEntryTest(unittest.TestCase):
    def test_options_are_canonical_and_isolated(self) -> None:
        entry = ModelEntry.from_options(
            id="a", provider="OpenAI", options={"b": 2, "a": 1},
        )
        self.assertEqual(entry.provider, "openai", msg="厂商名必须归一化为小写")
        self.assertEqual(entry.options_json, '{"a": 1, "b": 2}')
        got = entry.options
        got["a"] = 99
        self.assertEqual(entry.options["a"], 1, msg="调用方改副本不得影响目录")

    def test_bad_options_json_degrades_to_empty(self) -> None:
        entry = ModelEntry(id="a", provider="openai", options_json="{not json")
        self.assertEqual(entry.options, {})


class ModelCatalogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = ModelCatalog()

    def test_unconfigured_catalog_is_empty_and_not_authoritative(self) -> None:
        snap = self.catalog.snapshot()
        self.assertEqual(snap.entries, ())
        self.assertEqual(snap.default_id, "")
        self.assertFalse(snap.authoritative)
        self.assertIsNone(self.catalog.provider_for("anything"))

    def test_default_prefers_flag_then_first(self) -> None:
        self.catalog.set_source("static", [_entry("a"), _entry("b", default=True)])
        snap = self.catalog.snapshot()
        self.assertEqual(snap.default_id, "b")
        self.assertTrue(snap.authoritative)
        self.assertEqual(self.catalog.ids(), ("a", "b"))

        self.catalog.set_source("static", [_entry("x"), _entry("y")])
        self.assertEqual(self.catalog.default_id(), "x", msg="无标记时取第一条")

    def test_replacing_source_drops_removed_models(self) -> None:
        self.catalog.set_source("static", [_entry("a"), _entry("b")])
        self.catalog.set_source("static", [_entry("c")])
        self.assertEqual(self.catalog.ids(), ("c",))
        self.assertIsNone(self.catalog.provider_for("a"))

    def test_empty_replacement_flips_authoritative(self) -> None:
        self.catalog.set_source("static", [_entry("a")])
        self.assertTrue(self.catalog.snapshot().authoritative)
        self.catalog.set_source("static", [])
        snap = self.catalog.snapshot()
        self.assertEqual(snap.entries, ())
        self.assertFalse(snap.authoritative, msg="权威必须由当前条目数算出，不能沿用旧值")

    def test_second_distinct_source_is_rejected_without_clobbering(self) -> None:
        self.catalog.set_source("first", [_entry("a")])
        with self.assertRaises(RuntimeError):
            self.catalog.set_source("second", [_entry("b")])
        self.assertEqual(self.catalog.ids(), ("a",))
        self.assertEqual(self.catalog.snapshot().source, "first")

    def test_duplicate_ids_reject_the_whole_batch(self) -> None:
        self.catalog.set_source("static", [_entry("a")])
        with self.assertRaises(ValueError):
            self.catalog.set_source("static", [_entry("b"), _entry("b")])
        self.assertEqual(self.catalog.ids(), ("a",), msg="坏批次不得替换掉旧目录")

    def test_unknown_provider_skips_only_that_entry(self) -> None:
        self.catalog.set_source("static", [
            _entry("bad", provider="telepathy"),
            _entry("good"),
        ])
        self.assertEqual(self.catalog.ids(), ("good",))
        self.assertTrue(self.catalog.snapshot().authoritative)

    def test_unknown_provider_only_means_not_authoritative(self) -> None:
        self.catalog.set_source("static", [_entry("bad", provider="telepathy")])
        snap = self.catalog.snapshot()
        self.assertEqual(snap.entries, ())
        self.assertFalse(snap.authoritative)

    def test_disposer_is_scoped_to_its_own_registration(self) -> None:
        stale = self.catalog.set_source("static", [_entry("a")])
        self.catalog.set_source("static", [_entry("b")])
        stale()
        self.assertEqual(self.catalog.ids(), ("b",),
                         msg="重新登记后旧 disposer 不得清空新目录")
        fresh = self.catalog.set_source("static", [_entry("c")])
        fresh()
        self.assertEqual(self.catalog.ids(), ())
        fresh()  # 幂等
        self.assertEqual(self.catalog.ids(), ())

    def test_hot_read_is_re_evaluated_each_snapshot(self) -> None:
        state = {"entries": [_entry("a")]}
        self.catalog.set_source("plugin", lambda: state["entries"])
        self.assertEqual(self.catalog.ids(), ("a",))
        state["entries"] = [_entry("b")]
        self.assertEqual(self.catalog.ids(), ("b",))

    def test_hot_read_failure_keeps_last_good_entries(self) -> None:
        calls = {"n": 0}

        def reader():
            calls["n"] += 1
            if calls["n"] > 1:
                raise OSError("config unreadable")
            return [_entry("a")]

        self.catalog.set_source("plugin", reader)
        self.assertEqual(self.catalog.ids(), ("a",))
        self.assertEqual(self.catalog.ids(), ("a",), msg="读配置失败应沿用上一份好配置")
        self.assertIsNotNone(self.catalog.provider_for("a"))

    def test_hot_read_duplicate_ids_fall_back_to_last_good(self) -> None:
        state = {"entries": [_entry("a")]}
        self.catalog.set_source("plugin", lambda: state["entries"])
        self.catalog.snapshot()
        state["entries"] = [_entry("b"), _entry("b")]
        self.assertEqual(self.catalog.ids(), ("a",),
                         msg="热读出现重复 id 时保留旧目录并留痕")


class ProviderCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = ModelCatalog()
        self.catalog.set_source("static", [_entry("a")])

    def test_provider_is_built_once_per_entry(self) -> None:
        first = self.catalog.provider_for("a")
        second = self.catalog.provider_for("a")
        self.assertIsInstance(first, OpenAICompatibleProvider)
        self.assertIs(first, second, msg="同一批次必须复用实例，不能每次请求新建")

    def test_option_change_invalidates_the_cached_provider(self) -> None:
        before = self.catalog.provider_for("a")
        self.catalog.set_source("static", [ModelEntry.from_options(
            id="a", provider="openai",
            options={**_OPENAI, "api_key": "rotated"},
        )])
        after = self.catalog.provider_for("a")
        self.assertIsNot(before, after, msg="选项变了就必须重新构造")

    def test_unknown_model_id_returns_none(self) -> None:
        self.assertIsNone(self.catalog.provider_for("missing"))
        self.assertIsNone(self.catalog.provider_for(""))


class PluginContextCatalogTest(unittest.TestCase):
    """插件注册口：来源名取插件名、冲突不抛、disposer 随 ctx 回收。"""

    def setUp(self) -> None:
        self.catalog = ModelCatalog()
        self.registry = ToolRegistry()

    def _ctx(self, name: str) -> PluginContext:
        return PluginContext(name, self.registry, model_catalog=self.catalog)

    def test_missing_catalog_is_a_wiring_error(self) -> None:
        bare = PluginContext("x", self.registry)
        with self.assertRaises(RuntimeError):
            bare.add_model_catalog([_entry("a")])

    def test_plugin_name_becomes_the_catalog_source(self) -> None:
        ctx = self._ctx("multi_model")
        ctx.add_model_catalog([_entry("a")])
        snap = self.catalog.snapshot()
        self.assertEqual(snap.source, "multi_model")
        self.assertEqual(snap.default_id, "a")

    def test_disposer_removes_only_its_own_source(self) -> None:
        ctx = self._ctx("multi_model")
        dispose = ctx.add_model_catalog([_entry("a")])
        self.assertEqual(self.catalog.ids(), ("a",))
        dispose()
        self.assertEqual(self.catalog.ids(), ())
        dispose()
        self.assertEqual(self.catalog.ids(), (), msg="disposer 必须幂等")

    def test_second_plugin_source_is_reported_not_raised(self) -> None:
        self._ctx("first").add_model_catalog([_entry("a")])
        second = self._ctx("second")
        with mock.patch("agent.capabilities.plugins.report_error") as report:
            dispose = second.add_model_catalog([_entry("b")])
        self.assertTrue(report.called, msg="来源冲突必须留痕")
        self.assertEqual(self.catalog.ids(), ("a",), msg="先登记的来源保持不变")
        dispose()
        self.assertEqual(self.catalog.ids(), ("a",), msg="冲突方拿到的必须是空 disposer")

    def test_hot_read_callback_is_accepted(self) -> None:
        state = {"entries": [_entry("a")]}
        self._ctx("multi_model").add_model_catalog(lambda: state["entries"])
        state["entries"] = [_entry("b")]
        self.assertEqual(self.catalog.ids(), ("b",))


class SnapshotShapeTest(unittest.TestCase):
    def test_entry_lookup_ignores_surrounding_whitespace(self) -> None:
        snap = CatalogSnapshot(entries=(_entry("a"),), default_id="a",
                               authoritative=True, source="s")
        self.assertIsNotNone(snap.entry(" a "))
        self.assertIsNone(snap.entry("b"))


if __name__ == "__main__":
    unittest.main()
