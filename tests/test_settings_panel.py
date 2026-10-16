# -*- coding: utf-8 -*-
"""设置页：写回原文件时留下注释，保存后当前进程对象换成新值。"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.shell.settings_panel import (
    append_ini_section,
    apply_host,
    handle_post,
    host_catalog,
    list_plugins,
    read_plugin_config,
    remove_ini_section,
    save_host,
    set_plugin_enabled,
    update_ini_keys,
    write_plugin_config,
)


class _Provider:
    def __init__(self) -> None:
        self.base_url = ""
        self.api_key = ""
        self.model = ""


class _State:
    def __init__(self) -> None:
        self.default_effort = "high"
        self.default_model = ""


class _App:
    def __init__(self) -> None:
        self.provider = _Provider()
        self.live_state = _State()
        self.context_defaults: dict = {}
        self.image_turns = 1
        self.image_max = 1
        self.max_passes = 1
        self._available_models: list = []
        self.plugin_host = None


class _Host:
    def __init__(self) -> None:
        self.loaded = ["oldplug"]
        self.seen = None

    def loaded_names(self):
        return list(self.loaded)

    def unload(self, name: str) -> None:
        if name in self.loaded:
            self.loaded.remove(name)

    def load_manifest(self, entries):
        self.seen = list(entries)
        for entry in entries:
            if entry["name"] not in self.loaded:
                self.loaded.append(entry["name"])
        return []


class IniEditTest(unittest.TestCase):
    def test_update_keeps_comments_and_other_sections(self) -> None:
        text = (
            "; 头\n"
            "[model_reasoning]\n"
            "; 密钥\n"
            "api_key = old\n"
            "api_base_url = http://a\n"
            "\n"
            "[agent]\n"
            "max_passes = 4\n"
        )
        updated = update_ini_keys(text, "model_reasoning", {
            "api_base_url": "http://b",
            "model": "demo",
        })
        self.assertIn("; 头\n", updated)
        self.assertIn("; 密钥\n", updated)
        self.assertIn("api_key = old\n", updated)
        self.assertIn("api_base_url = http://b\n", updated)
        self.assertIn("model = demo\n", updated)
        self.assertIn("[agent]\n", updated)
        self.assertIn("max_passes = 4\n", updated)

    def test_remove_section_leaves_commented_header(self) -> None:
        text = (
            "; 插件清单\n"
            "; [plugin:tts]\n"
            "; version = 1.0\n"
            "\n"
            "[plugin:knowledge]\n"
            "version = 1.0\n"
        )
        updated = remove_ini_section(text, "plugin:knowledge")
        self.assertIn("; [plugin:tts]\n", updated)
        self.assertIn("; version = 1.0\n", updated)
        self.assertNotIn("[plugin:knowledge]", updated)
        self.assertNotIn("\nversion = 1.0\n", "\n" + updated)

    def test_append_does_not_duplicate_a_section(self) -> None:
        text = "[plugin:skills]\nversion = 1.0\n"
        self.assertEqual(
            append_ini_section(text, "plugin:skills", [("version", "9.9")]),
            text,
        )


class SaveHostTest(unittest.TestCase):
    def test_invalid_number_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config.ini"
            web = root / "web-ui-config.ini"
            config.write_text("; keep\n[agent]\nmax_passes = 4\n", encoding="utf-8")
            web.write_text("[web-ui]\ndisplay_tool_steps = 0\n", encoding="utf-8")
            before = config.read_text(encoding="utf-8")
            result = save_host(
                {"agent": {"max_passes": "0"}},
                config_path=config,
                web_ui_path=web,
            )
            self.assertFalse(result["ok"])
            self.assertEqual(config.read_text(encoding="utf-8"), before)

    def test_save_rewrites_the_key_and_keeps_the_comment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config.ini"
            web = root / "web-ui-config.ini"
            config.write_text("; keep\n[agent]\nmax_passes = 4\n", encoding="utf-8")
            web.write_text("[web-ui]\ndisplay_tool_steps = 0\n", encoding="utf-8")
            result = save_host(
                {"agent": {"max_passes": 6}, "web-ui": {"display_tool_steps": "1"}},
                config_path=config,
                web_ui_path=web,
            )
            self.assertTrue(result["ok"])
            self.assertTrue(result["web_ui"]["display_tool_steps"])
            text = config.read_text(encoding="utf-8")
            self.assertIn("; keep\n", text)
            self.assertIn("max_passes = 6\n", text)
            self.assertIn("display_tool_steps = 1\n", web.read_text(encoding="utf-8"))

    def test_catalog_echoes_the_key_from_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.ini"
            web = Path(tmp) / "web-ui-config.ini"
            config.write_text(
                "[model_reasoning]\napi_key = unit-test-key\nmodel = demo\n",
                encoding="utf-8",
            )
            web.write_text("", encoding="utf-8")
            catalog = host_catalog(config, web)
            dumped = str(catalog)
            self.assertNotIn("unit-test-key", dumped)
            model = next(sec for sec in catalog["sections"] if sec["id"] == "model_reasoning")
            key = next(field for field in model["fields"] if field["key"] == "api_key")
            self.assertEqual(key["kind"], "secret")
            self.assertEqual(key["value"], "")
            self.assertTrue(key["configured"])
            self.assertEqual(key["placeholder"], "已设置秘钥,可重新设置并替换")
            config.write_text("[model_reasoning]\nmodel = demo\n", encoding="utf-8")
            bare = host_catalog(config, web)
            bare_key = next(
                field for field in next(
                    sec["fields"] for sec in bare["sections"] if sec["id"] == "model_reasoning"
                ) if field["key"] == "api_key"
            )
            self.assertFalse(bare_key["configured"])
            self.assertEqual(bare_key["placeholder"], "未配置秘钥")
            kept = save_host(
                {"model_reasoning": {"api_key": "", "model": "other"}},
                config_path=config,
                web_ui_path=web,
            )
            self.assertTrue(kept["ok"])
            config.write_text(
                "[model_reasoning]\napi_key = unit-test-key\nmodel = demo\n",
                encoding="utf-8",
            )
            kept = save_host(
                {"model_reasoning": {"api_key": "  ", "model": "other"}},
                config_path=config,
                web_ui_path=web,
            )
            self.assertTrue(kept["ok"])
            text = config.read_text(encoding="utf-8")
            self.assertIn("api_key = unit-test-key\n", text)
            self.assertIn("model = other\n", text)
            replaced = save_host(
                {"model_reasoning": {"api_key": "unit-test-new"}},
                config_path=config,
                web_ui_path=web,
            )
            self.assertTrue(replaced["ok"])
            self.assertIn("api_key = unit-test-new\n", config.read_text(encoding="utf-8"))


class ApplyHostTest(unittest.TestCase):
    def test_apply_updates_provider_and_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.ini"
            config.write_text(
                "[model_reasoning]\n"
                "api_base_url = http://example.test/v1\n"
                "api_key = unit-test-key\n"
                "model = demo-model\n"
                "models = demo-model, other\n"
                "[agent]\n"
                "reasoning_effort = high\n"
                "max_passes = 3\n"
                "[context]\n"
                "summary_token_threshold = 1000\n"
                "full_user_rounds = 2\n"
                "image_turns = 4\n"
                "image_max = 2\n",
                encoding="utf-8",
            )
            app = _App()
            self.assertEqual(apply_host(app, config_path=config), {})
            self.assertEqual(app.provider.base_url, "http://example.test/v1")
            self.assertEqual(app.provider.api_key, "unit-test-key")
            self.assertEqual(app.provider.model, "demo-model")
            self.assertEqual(app._available_models, ["demo-model", "other"])
            self.assertEqual(app.live_state.default_effort, "high")
            self.assertEqual(app.max_passes, 3)
            self.assertEqual(app.image_turns, 4)
            self.assertEqual(app.image_max, 2)
            self.assertEqual(app.context_defaults["full_user_rounds"], 2)


class PluginSettingsTest(unittest.TestCase):
    def test_enable_and_disable_edit_the_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugins = root / "plugins.ini"
            folder = root / "plugins" / "skills"
            folder.mkdir(parents=True)
            (folder / "plugin.py").write_text(
                "def register(ctx):\n    return []\n",
                encoding="utf-8",
            )
            (folder / "plugin-config.ini").write_text(
                "[base]\nname = 技能\ndesc = 清单常驻。\nversion = 2.0\nicon = 🧩\n",
                encoding="utf-8",
            )
            plugins.write_text(
                "; 插件清单\n; [plugin:tts]\n; version = 1.0\n\n"
                "[plugin:oldplug]\nversion = 1.0\n",
                encoding="utf-8",
            )
            host = _Host()
            app = _App()
            app.plugin_host = host
            enabled = set_plugin_enabled(
                "skills", True, app, plugins_path=plugins, plugins_dir=root / "plugins")
            self.assertTrue(enabled["ok"])
            text = plugins.read_text(encoding="utf-8")
            self.assertIn("[plugin:skills]\n", text)
            self.assertIn("version = 2.0\n", text)
            self.assertNotIn("enabled =", text)
            cfg = (folder / "plugin-config.ini").read_text(encoding="utf-8")
            self.assertIn("enable = 1\n", cfg)
            self.assertIn("desc = 清单常驻。\n", cfg)
            self.assertIn("; [plugin:tts]\n", text)
            self.assertEqual(host.loaded, ["oldplug", "skills"])
            self.assertEqual([item["name"] for item in host.seen], ["oldplug", "skills"])
            cards = list_plugins(plugins_path=plugins, plugins_dir=root / "plugins")["plugins"]
            skill = next(item for item in cards if item["name"] == "skills")
            self.assertEqual(skill["title"], "技能")
            self.assertEqual(skill["description"], "清单常驻。")
            self.assertEqual(skill["version"], "v2.0")
            self.assertEqual(skill["icon"], "🧩")
            self.assertTrue(skill["enabled"])
            disabled = set_plugin_enabled(
                "skills", False, app, plugins_path=plugins, plugins_dir=root / "plugins")
            self.assertTrue(disabled["ok"])
            text = plugins.read_text(encoding="utf-8")
            self.assertIn("[plugin:skills]", text)
            cfg = (folder / "plugin-config.ini").read_text(encoding="utf-8")
            self.assertIn("enable = 0\n", cfg)
            self.assertIn("; [plugin:tts]\n", text)
            self.assertEqual(host.loaded, ["oldplug"])
            skill = next(
                item for item in list_plugins(
                    plugins_path=plugins, plugins_dir=root / "plugins")["plugins"]
                if item["name"] == "skills"
            )
            self.assertFalse(skill["enabled"])

    def test_missing_plugin_is_not_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugins = root / "plugins.ini"
            plugins.write_text("", encoding="utf-8")
            result = set_plugin_enabled(
                "skills", True, plugins_path=plugins, plugins_dir=root / "plugins")
            self.assertFalse(result["ok"])
            self.assertEqual(plugins.read_text(encoding="utf-8"), "")

    def test_plugin_config_roundtrip_rejects_a_bad_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugins"
            folder = root / "knowledge"
            folder.mkdir(parents=True)
            (folder / "plugin.py").write_text("PLUGIN_VERSION = '1.0'\n", encoding="utf-8")
            written = write_plugin_config(
                "knowledge", "[knowledge]\ndir = D:/kb\n", plugins_dir=root)
            self.assertTrue(written["ok"])
            loaded = read_plugin_config("knowledge", plugins_dir=root)
            self.assertEqual(loaded["text"], "[knowledge]\ndir = D:/kb\n")
            rejected = write_plugin_config("..", "x", plugins_dir=root)
            self.assertFalse(rejected["ok"])

    def test_unknown_route(self) -> None:
        status, payload = handle_post("/api/settings/nope", {}, None)
        self.assertEqual(status, 404)
        self.assertFalse(payload["ok"])


class SettingsPageAssetsTest(unittest.TestCase):
    def test_gear_and_settings_script_are_inlined(self) -> None:
        from agent.shell.ui_bundle import inline_ui_html

        html = inline_ui_html()
        self.assertIn('id="hdrSettingsBtn"', html)
        self.assertIn("function bootSettingsPanel", html)
        self.assertIn(".st-modal{", html.replace(" ", "").replace("\n", ""))
