# -*- coding: utf-8 -*-
"""多模型插件：配置解析、目录回调与 `/catalog` 响应。

覆盖：有效条目 / 缺省值 / BOM / 坏条目隔离 / 默认标记 / 数值与布尔校验 /
凭据不外泄 / register 的三个贡献 / 配置热读。
"""
from __future__ import annotations

import configparser
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.config_schema import MULTI_MODEL_SCHEMA  # noqa: E402

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


class _Ctx:
    """记录插件贡献的测试替身。"""

    def __init__(self) -> None:
        self.catalog = None
        self.routes = {}
        self.boot = []
        self.disposed = 0

    def _disposer(self):
        def _drop():
            self.disposed += 1
        return _drop

    def add_model_catalog(self, entries):
        self.catalog = entries
        return self._disposer()

    def add_route(self, method, path, handler):
        self.routes[(method, path)] = handler
        return self._disposer()

    def add_boot_script(self, rel_path):
        self.boot.append(rel_path)
        return self._disposer()


class _ConfigCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.path = self.root / "plugin-config.ini"

    def write(self, text: str, *, bom: bool = False) -> Path:
        encoding = "utf-8-sig" if bom else "utf-8"
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

    def test_bad_context_window_keeps_the_entry_usable(self) -> None:
        """窗口只服务展示；写坏了丢这一项，不该让整条模型消失。"""
        entries, invalid = self.parse(
            "[model:a]\n"
            "base_url = http://x\n"
            "api_key = k\n"
            "context_window = lots\n"
        )
        self.assertEqual(invalid, ())
        self.assertEqual(entries[0].context_window, 0)
        self.assertNotIn("context_window", entries[0].options)

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


class PluginTemplateTest(unittest.TestCase):
    """`.example` 的键集合必须与 schema/解析器一致（双向）。"""

    def test_example_covers_schema_keys(self) -> None:
        path = _ROOT / "plugins" / "multi_model" / "plugin-config.ini.example"
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(str(path), encoding="utf-8-sig")
        self.assertEqual(set(parser["base"]), set(MULTI_MODEL_SCHEMA["base"]))
        seen = set()
        for section in parser.sections():
            if section.startswith("model:"):
                seen |= set(parser[section])
        self.assertEqual(seen, set(MULTI_MODEL_SCHEMA["model"]))

    def test_example_is_a_template_until_keys_are_filled(self) -> None:
        """示例里的占位密钥不算已配置：照抄后仍回落到 config.ini，不会拿假密钥发包。"""
        path = _ROOT / "plugins" / "multi_model" / "plugin-config.ini.example"
        with contextlib.redirect_stderr(io.StringIO()):
            entries, invalid = _PLUGIN.parse_config(path)
        self.assertEqual(entries, ())
        self.assertEqual([item["id"] for item in invalid], ["deepseek", "claude"])
        for item in invalid:
            self.assertIn("占位符", item["reason"])



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
            "context_window": 0, "default": True,
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


class RegisterTest(_ConfigCase):
    def setUp(self) -> None:
        super().setUp()
        self._original_path = _PLUGIN._config_path
        _PLUGIN._config_path = lambda: self.path
        self.addCleanup(setattr, _PLUGIN, "_config_path", self._original_path)

    def test_register_contributes_catalog_route_and_boot_script(self) -> None:
        self.write(
            "[base]\nname = 多模型\n"
            "[model:a]\nbase_url = http://x\napi_key = k\n"
        )
        ctx = _Ctx()
        with contextlib.redirect_stderr(io.StringIO()):
            disposers = _PLUGIN.register(ctx)
        self.assertEqual(len(disposers), 3)
        self.assertTrue(callable(ctx.catalog))
        self.assertIn(("GET", "catalog"), ctx.routes)
        self.assertEqual(ctx.boot, ["ui/model-picker.js"])
        status, payload = ctx.routes[("GET", "catalog")]({})
        self.assertEqual(status, 200)
        self.assertEqual(payload["default"], "a")
        for disposer in disposers:
            disposer()
        self.assertEqual(ctx.disposed, 3)

    def test_catalog_callback_hot_reads_the_file(self) -> None:
        self.write("[model:a]\nbase_url = http://x\napi_key = k\n")
        ctx = _Ctx()
        with contextlib.redirect_stderr(io.StringIO()):
            _PLUGIN.register(ctx)
        self.assertEqual([item.id for item in ctx.catalog()], ["a"])
        self.write(
            "[model:a]\nbase_url = http://x\napi_key = k\n"
            "[model:b]\nbase_url = http://y\napi_key = k\n"
        )
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual([item.id for item in ctx.catalog()], ["a", "b"])

    def test_reregister_does_not_duplicate_defaults(self) -> None:
        self.write("[model:a]\nbase_url = http://x\napi_key = k\n")
        ctx = _Ctx()
        with contextlib.redirect_stderr(io.StringIO()):
            _PLUGIN.register(ctx)
        first = ctx.catalog()
        with contextlib.redirect_stderr(io.StringIO()):
            second = ctx.catalog()
        self.assertEqual([item.is_default for item in first], [True])
        self.assertEqual([item.is_default for item in second], [True])


if __name__ == "__main__":
    unittest.main()
