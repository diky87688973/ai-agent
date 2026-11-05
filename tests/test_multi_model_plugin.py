# -*- coding: utf-8 -*-
"""多模型插件：配置解析、目录回调与 `/catalog` 响应。

覆盖：有效条目 / 缺省值 / BOM / 坏条目隔离 / 默认标记 / 数值与布尔校验 /
凭据不外泄 / 片段声明的节点 / 配置热读。
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.core.slot_fragments import load_merged  # noqa: E402

_MOD = "fan_agent_plugins.multi_model"
_PLUGIN_PATH = _ROOT / "plugins" / "multi_model" / "plugin.py"


def _load_plugin_module():
    spec = importlib.util.spec_from_file_location(_MOD, str(_PLUGIN_PATH))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MOD] = module
    spec.loader.exec_module(module)
    return module


_PLUGIN = _load_plugin_module()


class _ConfigCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.path = self.root / "plugin-config.ini"

    def write(self, text: str, *, bom: bool = False, raw: bool = False) -> Path:
        encoding = "utf-8-sig" if bom else "utf-8"
        if not raw:
            parts = re.split(r"(?m)(?=^\[model:)", text)
            out = []
            for part in parts:
                match = re.match(r"(?s)(\[model:[^\]]+\]\n)", part)
                if match and "context_window" not in part.lower():
                    part = match.group(1) + "context_window = 1000000\n" + part[match.end():]
                out.append(part)
            text = "".join(out)
        self.path.write_text(text, encoding=encoding)
        return self.path

    def parse(self, text: str, *, bom: bool = False):
        with contextlib.redirect_stderr(io.StringIO()):
            return _PLUGIN.parse_config(self.write(text, bom=bom))


class ParseTest(_ConfigCase):
    def test_missing_file_is_empty_not_an_error(self) -> None:
        entries, invalid = _PLUGIN.parse_config(self.path)
        self.assertEqual(entries, ())
        self.assertEqual(invalid, ())

    def test_openai_defaults_and_first_entry_is_default(self) -> None:
        entries, invalid = self.parse(
            "[model:deepseek]\n"
            "base_url = https://api.deepseek.com\n"
            "api_key = sk-test\n"
        )
        self.assertEqual(invalid, ())
        self.assertEqual(len(entries), 1)
        item = entries[0]
        self.assertEqual(item.id, "deepseek")
        self.assertEqual(item.provider, "openai")
        self.assertEqual(item.label, "deepseek")
        self.assertTrue(item.is_default)
        self.assertEqual(item.options["model"], "deepseek")
        self.assertEqual(item.options["base_url"], "https://api.deepseek.com")

    def test_utf8_bom_is_accepted(self) -> None:
        entries, invalid = self.parse(
            "[model:claude]\n"
            "provider = anthropic\n"
            "base_url = https://api.anthropic.com\n"
            "api_key = sk-ant-test\n"
            "model = claude-sonnet-4-5\n"
            "label = Claude Sonnet 4.5\n",
            bom=True,
        )
        self.assertEqual(invalid, ())
        self.assertEqual(entries[0].id, "claude")
        self.assertEqual(entries[0].label, "Claude Sonnet 4.5")

    def test_context_window_is_carried_as_entry_metadata(self) -> None:
        entries, invalid = self.parse(
            "[model:a]\n"
            "base_url = http://x\n"
            "api_key = k\n"
            "context_window = 128000\n"
        )
        self.assertEqual(invalid, ())
        self.assertEqual(entries[0].context_window, 128000)
        self.assertEqual(entries[0].options["context_window"], 128000)

    def test_bad_context_window_invalidates_the_entry(self) -> None:
        entries, invalid = self.parse(
            "[model:a]\n"
            "base_url = http://x\n"
            "api_key = k\n"
            "context_window = lots\n"
        )
        self.assertEqual(entries, ())
        self.assertIn("context_window", invalid[0]["reason"])

    def test_missing_context_window_invalidates_the_entry(self) -> None:
        self.write(
            "[model:a]\nbase_url = http://x\napi_key = k\n",
            raw=True,
        )
        with contextlib.redirect_stderr(io.StringIO()):
            entries, invalid = _PLUGIN.parse_config(self.path)
        self.assertEqual(entries, ())
        self.assertIn("context_window", invalid[0]["reason"])

    def test_compression_percent_defaults_to_70(self) -> None:
        entries, invalid = self.parse(
            "[model:a]\nbase_url = http://x\napi_key = k\n"
        )
        self.assertEqual(invalid, ())
        self.assertEqual(entries[0].compression_percent, 70)
        self.assertEqual(entries[0].options["compression_percent"], 70)

    def test_compression_percent_rejects_out_of_range(self) -> None:
        entries, invalid = self.parse(
            "[model:a]\nbase_url = http://x\napi_key = k\n"
            "compression_percent = 95\n"
        )
        self.assertEqual(entries, ())
        self.assertIn("compression_percent", invalid[0]["reason"])

    def test_anthropic_options_are_typed(self) -> None:
        entries, _ = self.parse(
            "[model:claude]\n"
            "provider = anthropic\n"
            "base_url = https://api.anthropic.com\n"
            "api_key = sk-ant-test\n"
            "max_tokens = 16000\n"
            "thinking = 1\n"
            "thinking_budget_tokens = 4096\n"
        )
        options = entries[0].options
        self.assertEqual(options["max_tokens"], 16000)
        self.assertIs(options["thinking"], True)
        self.assertEqual(options["thinking_budget_tokens"], 4096)

    def test_anthropic_options_are_ignored_for_openai(self) -> None:
        entries, _ = self.parse(
            "[model:deepseek]\n"
            "base_url = https://api.deepseek.com\n"
            "api_key = sk-test\n"
            "max_tokens = 16000\n"
            "thinking = 1\n"
            "thinking_budget_tokens = 4096\n"
        )
        options = entries[0].options
        self.assertNotIn("max_tokens", options)
        self.assertNotIn("thinking", options)
        self.assertNotIn("thinking_budget_tokens", options)

    def test_bad_entry_does_not_hide_good_ones(self) -> None:
        entries, invalid = self.parse(
            "[model:broken]\nprovider = unknown\nbase_url = http://x\napi_key = k\n"
            "[model:good]\nbase_url = http://x\napi_key = k\n"
        )
        self.assertEqual([item.id for item in entries], ["good"])
        self.assertEqual(len(invalid), 1)
        self.assertEqual(invalid[0]["id"], "broken")
        self.assertIn("provider", invalid[0]["reason"])
        self.assertIn("未知厂商", invalid[0]["reason"])

    def test_missing_credentials_invalidates_only_that_entry(self) -> None:
        entries, invalid = self.parse(
            "[model:no-key]\nbase_url = http://x\n"
            "[model:no-url]\napi_key = k\n"
            "[model:ok]\nbase_url = http://x\napi_key = k\n"
        )
        self.assertEqual([item.id for item in entries], ["ok"])
        self.assertEqual({item["id"] for item in invalid}, {"no-key", "no-url"})

    def test_bad_numbers_invalidate_the_entry(self) -> None:
        entries, invalid = self.parse(
            "[model:claude]\n"
            "provider = anthropic\nbase_url = http://x\napi_key = k\n"
            "max_tokens = many\n"
            "[model:ok]\nbase_url = http://x\napi_key = k\n"
        )
        self.assertEqual([item.id for item in entries], ["ok"])
        self.assertIn("max_tokens", invalid[0]["reason"])

    def test_bad_thinking_flag_invalidates_the_entry(self) -> None:
        _, invalid = self.parse(
            "[model:claude]\n"
            "provider = anthropic\nbase_url = http://x\napi_key = k\n"
            "thinking = maybe\n"
        )
        self.assertIn("thinking", invalid[0]["reason"])

    def test_multiple_defaults_keep_the_first(self) -> None:
        entries, _ = self.parse(
            "[model:a]\nbase_url = http://x\napi_key = k\ndefault = 1\n"
            "[model:b]\nbase_url = http://x\napi_key = k\ndefault = 1\n"
        )
        self.assertEqual([item.is_default for item in entries], [True, False])

    def test_no_default_marks_the_first_entry(self) -> None:
        entries, _ = self.parse(
            "[model:a]\nbase_url = http://x\napi_key = k\n"
            "[model:b]\nbase_url = http://x\napi_key = k\n"
        )
        self.assertEqual([item.is_default for item in entries], [True, False])

    def test_duplicate_section_is_a_file_level_error(self) -> None:
        """INI 不允许同名节：重复 id 会让整份文件解析失败，所以只能用不同 id。"""
        self.write(
            "[model:dup]\nbase_url = http://x\napi_key = k\n"
            "[model:dup]\nprovider = anthropic\nbase_url = http://x\napi_key = k\n"
        )
        with contextlib.redirect_stderr(io.StringIO()):
            entries, invalid = _PLUGIN.parse_config(self.path)
        self.assertEqual(entries, ())
        self.assertEqual(len(invalid), 1)
        self.assertIn("DuplicateSectionError", invalid[0]["reason"])

    def test_placeholder_keys_are_rejected(self) -> None:
        """照抄示例留下的占位符不算已配置，插件继续走回落路径。"""
        entries, invalid = self.parse(
            "[model:a]\nbase_url = http://x\napi_key = sk-请替换\n"
            "[model:b]\nbase_url = http://x\napi_key = sk-ant-请替换\n"
            "[model:ok]\nbase_url = http://x\napi_key = sk-real-key\n"
        )
        self.assertEqual([item.id for item in entries], ["ok"])
        self.assertEqual([item["id"] for item in invalid], ["a", "b"])
        self.assertIn("占位符", invalid[0]["reason"])

    def test_same_vendor_twice_with_distinct_ids(self) -> None:
        """同一家厂商同时走两套协议：id 必须唯一，`provider` 决定各走哪套。"""
        entries, invalid = self.parse(
            "[model:ds-openai]\n"
            "provider = openai\nbase_url = http://x\napi_key = k\nmodel = deepseek-chat\n"
            "[model:ds-anthropic]\n"
            "provider = anthropic\nbase_url = http://x\napi_key = k\n"
            "model = deepseek-chat\nmax_tokens = 16000\n"
        )
        self.assertEqual(invalid, ())
        self.assertEqual([item.id for item in entries], ["ds-openai", "ds-anthropic"])
        self.assertEqual([item.provider for item in entries], ["openai", "anthropic"])
        self.assertEqual(entries[0].options["model"], "deepseek-chat")
        self.assertEqual(entries[1].options["model"], "deepseek-chat")
        self.assertNotIn("max_tokens", entries[0].options)
        self.assertIn("max_tokens", entries[1].options)

    def test_bad_default_flag_keeps_entry_non_default(self) -> None:
        entries, invalid = self.parse(
            "[model:a]\nbase_url = http://x\napi_key = k\ndefault = 2\n"
            "[model:b]\nbase_url = http://x\napi_key = k\ndefault = 1\n"
        )
        self.assertEqual(invalid, ())
        self.assertEqual([item.is_default for item in entries], [False, True])

    def test_diagnostic_points_at_file_section_and_key(self) -> None:
        buffer = io.StringIO()
        self.write("[model:broken]\nprovider = nope\nbase_url = http://x\napi_key = k\n")
        with contextlib.redirect_stderr(buffer):
            _PLUGIN.parse_config(self.path)
        text = buffer.getvalue()
        self.assertIn(str(self.path), text)
        self.assertIn("[model:broken]", text)
        self.assertIn("provider", text)
        self.assertIn("无效", text)

    def test_malformed_file_is_reported_not_raised(self) -> None:
        self.write("[model:broken\nbase_url = http://x\n")
        with contextlib.redirect_stderr(io.StringIO()):
            entries, invalid = _PLUGIN.parse_config(self.path)
        self.assertEqual(entries, ())
        self.assertEqual(len(invalid), 1)
        self.assertIn(str(self.path), invalid[0]["reason"])


class CatalogPayloadTest(_ConfigCase):
    def test_payload_carries_no_credentials(self) -> None:
        self.write(
            "[model:claude]\n"
            "provider = anthropic\n"
            "base_url = https://secret.example/path\n"
            "api_key = sk-ant-super-secret\n"
            "label = Claude\n"
        )
        with contextlib.redirect_stderr(io.StringIO()):
            payload = _PLUGIN._catalog_payload(self.path)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["default"], "claude")
        self.assertEqual(payload["models"], [{
            "id": "claude", "label": "Claude", "provider": "anthropic",
            "context_window": 1000000, "default": True,
        }])
        dumped = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("super-secret", dumped)
        self.assertNotIn("secret.example", dumped)

    def test_invalid_entries_are_exposed_for_ops(self) -> None:
        self.write("[model:broken]\nbase_url = http://x\napi_key = k\nprovider = nope\n")
        with contextlib.redirect_stderr(io.StringIO()):
            payload = _PLUGIN._catalog_payload(self.path)
        self.assertEqual(payload["models"], [])
        self.assertEqual(payload["default"], "")
        self.assertEqual(payload["invalid"][0]["id"], "broken")


class SlotFactoryTest(_ConfigCase):
    """旧 `register` 已删：口径改为「工厂产出的东西 + 片段声明的节点」。"""

    def setUp(self) -> None:
        super().setUp()
        self._original_path = _PLUGIN._config_path
        _PLUGIN._config_path = lambda: self.path
        self.addCleanup(setattr, _PLUGIN, "_config_path", self._original_path)

    def _runtime(self):
        with contextlib.redirect_stderr(io.StringIO()):
            return _PLUGIN.make_runtime(None)

    def test_factories_produce_catalog_route_and_panel(self) -> None:
        self.write("[model:a]\nbase_url = http://x\napi_key = k\n")
        runtime = self._runtime()
        handler = _PLUGIN.make_catalog_route(None, runtime)
        status, payload = handler({})
        self.assertEqual(status, 200)
        self.assertEqual(payload["default"], "a")
        self.assertEqual([item.id for item in _PLUGIN.make_catalog(None, runtime)()], ["a"])
        panel = _PLUGIN.make_panel(None, runtime)
        self.assertEqual(panel.kind, "panel")
        self.assertEqual(panel.label, "模型设置")

    def test_catalog_callback_hot_reads_the_file(self) -> None:
        self.write("[model:a]\nbase_url = http://x\napi_key = k\n")
        catalog = _PLUGIN.make_catalog(None, self._runtime())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual([item.id for item in catalog()], ["a"])
        self.write(
            "[model:a]\nbase_url = http://x\napi_key = k\n"
            "[model:b]\nbase_url = http://y\napi_key = k\n"
        )
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual([item.id for item in catalog()], ["a", "b"])

    def test_catalog_provider_declared_once(self) -> None:
        """目录源重读不会多出一份默认标记。"""
        self.write("[model:a]\nbase_url = http://x\napi_key = k\n")
        catalog = _PLUGIN.make_catalog(None, self._runtime())
        with contextlib.redirect_stderr(io.StringIO()):
            first = catalog()
            second = catalog()
        self.assertEqual([item.is_default for item in first], [True])
        self.assertEqual([item.is_default for item in second], [True])

    def test_fragment_declares_four_own_nodes_and_button(self) -> None:
        config = load_merged(_ROOT)
        own = {path: spec for path, spec in config.specs.items()
               if (path.startswith("app/plugins/multi_model/")
                   or path == "app/settings/model") and spec.kind != "container"}
        self.assertEqual(sorted(own), [
            "app/plugins/multi_model/models/catalog",
            "app/plugins/multi_model/routes/catalog",
            "app/plugins/multi_model/runtime",
            "app/settings/model",
        ])
        self.assertEqual(own["app/settings/model"].factory, "plugin:make_panel")
        self.assertEqual(own["app/plugins/multi_model/models/catalog"].factory,
                         "plugin:make_catalog")
        self.assertEqual(own["app/plugins/multi_model/routes/catalog"].factory,
                         "plugin:make_catalog_route")
        self.assertEqual(own["app/plugins/multi_model/routes/catalog"].method, "GET")

        button = "app/shell/web-ui/input/buttons/model_switch_btn"
        self.assertIn(button, config.specs)
        self.assertEqual(config.origin_of(button), "multi_model")
        self.assertEqual(config.specs[button].props.get("label"), "模型选择")


class PickerStyleTest(unittest.TestCase):
    """模型名是唯一辨识依据：下拉与按钮都不许截断它。

    同前缀的模型（`deepseek-flash-openai` / `deepseek-flash-anthropic`）
    一旦被 `max-width` + `ellipsis` 截成同一个 `deepseek-flash-ant...`，
    菜单就退化成"看不出选的是哪个版本"。宽度只能由内容决定。
    """

    def setUp(self) -> None:
        self.css = (_ROOT / "plugins" / "multi_model" / "ui" / "model-picker.css"
                    ).read_text(encoding="utf-8")

    def _rule(self, selector: str) -> str:
        start = self.css.index(selector + "{")
        return self.css[start:self.css.index("}", start) + 1]

    def test_button_has_no_width_cap(self) -> None:
        rule = self._rule(".mm-picker-btn")
        self.assertNotIn("max-width", rule)
        self.assertNotIn("text-overflow", self._rule(".mm-picker-label"))

    def test_menu_grows_with_its_items(self) -> None:
        rule = self._rule(".mm-picker-menu")
        self.assertIn("width:max-content", rule)
        self.assertIn("max-width:calc(100vw - 24px)", rule)
        self.assertNotIn("360px", rule)

    def test_names_and_ids_are_not_ellipsized(self) -> None:
        for selector in (".mm-picker-name",):
            rule = self._rule(selector)
            self.assertIn("white-space:nowrap", rule)
            self.assertNotIn("text-overflow", rule)
            self.assertNotIn("max-width", rule)


if __name__ == "__main__":
    unittest.main()
