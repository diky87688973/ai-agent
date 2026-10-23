# -*- coding: utf-8 -*-
"""设置页：写回原文件时留下注释，保存后当前进程对象换成新值。"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent.shell.settings_panel import (
    append_ini_section,
    apply_host,
    handle_get,
    handle_post,
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
            "; [plugin:ai_speak]\n"
            "\n"
            "[plugin:knowledge]\n"
            "path = D:/plugins/knowledge\n"
        )
        updated = remove_ini_section(text, "plugin:knowledge")
        self.assertIn("; [plugin:ai_speak]\n", updated)
        self.assertNotIn("[plugin:knowledge]", updated)
        self.assertNotIn("path = D:/plugins/knowledge", updated)

    def test_append_does_not_duplicate_a_section(self) -> None:
        text = "[plugin:skills]\nenabled = 1\n"
        self.assertEqual(
            append_ini_section(text, "plugin:skills", [("enabled", "0")]),
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

class ApplyHostTest(unittest.TestCase):
    def test_apply_updates_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.ini"
            config.write_text(
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
            (folder / "plugin-meta.json").write_text(
                '{"name":"Skills","desc":"清单常驻。","version":"2.0","icon":"🧩"}\n',
                encoding="utf-8",
            )
            plugins.write_text(
                "; 插件清单\n; [plugin:ai_speak]\n\n"
                "[plugin:oldplug]\n",
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
            self.assertNotIn("version =", text)
            self.assertIn("enabled = 1\n", text)
            cfg = folder / "plugin-config.ini"
            self.assertFalse(cfg.exists())
            self.assertIn("; [plugin:ai_speak]\n", text)
            self.assertEqual(host.loaded, ["oldplug", "skills"])
            self.assertEqual([item["name"] for item in host.seen], ["oldplug", "skills"])
            cards = list_plugins(plugins_path=plugins, plugins_dir=root / "plugins")["plugins"]
            skill = next(item for item in cards if item["name"] == "skills")
            self.assertEqual(skill["title"], "Skills")
            self.assertEqual(skill["description"], "清单常驻。")
            self.assertEqual(skill["version"], "v2.0")
            self.assertEqual(skill["icon"], "🧩")
            self.assertTrue(skill["enabled"])
            disabled = set_plugin_enabled(
                "skills", False, app, plugins_path=plugins, plugins_dir=root / "plugins")
            self.assertTrue(disabled["ok"])
            text = plugins.read_text(encoding="utf-8")
            self.assertIn("[plugin:skills]", text)
            self.assertIn("enabled = 0\n", text)
            self.assertFalse((folder / "plugin-config.ini").exists())
            self.assertIn("; [plugin:ai_speak]\n", text)
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
                "knowledge", "dir = D:/kb\n", plugins_dir=root)
            self.assertTrue(written["ok"])
            loaded = read_plugin_config("knowledge", plugins_dir=root)
            self.assertEqual(loaded["editor"]["text"], "dir = D:/kb\n")
            rejected = write_plugin_config("..", "x", plugins_dir=root)
            self.assertFalse(rejected["ok"])

    def test_missing_plugin_config_returns_empty_editor(self) -> None:
        """没有真实配置时返回空编辑器；不伪造示例、不落盘。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugins"
            folder = root / "multi_model"
            folder.mkdir(parents=True)
            (folder / "plugin.py").write_text("PLUGIN_VERSION = '1.0'\n", encoding="utf-8")
            payload = read_plugin_config("multi_model", plugins_dir=root)
            self.assertTrue(payload["ok"])
            self.assertFalse(payload["exists"])
            self.assertNotIn("seeded", payload)
            self.assertEqual(payload["editor"]["kind"], "text")
            self.assertEqual(payload["editor"]["text"], "")
            self.assertFalse((folder / "plugin-config.ini").exists())

    def test_fields_schema_creates_real_config_from_form(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugins"
            folder = root / "skills"
            folder.mkdir(parents=True)
            (folder / "plugin.py").write_text("PLUGIN_VERSION = '1.0'\n", encoding="utf-8")
            (folder / "plugin-meta.json").write_text(
                '{"name":"Skills","version":"1.0"}\n', encoding="utf-8")
            (folder / "settings-schema.json").write_text(
                json.dumps({"kind": "fields", "section": "config", "fields": [
                    {"key": "dir", "kind": "text", "label": "目录"},
                    {"key": "max_file_size", "kind": "number", "label": "上限",
                     "default": "200000", "min": 1},
                ]}), encoding="utf-8")
            payload = read_plugin_config("skills", plugins_dir=root)
            self.assertTrue(payload["ok"])
            self.assertFalse(payload["exists"])
            editor = payload["editor"]
            self.assertEqual(editor["kind"], "fields")
            self.assertEqual(editor["values"]["max_file_size"], "200000")
            written = write_plugin_config(
                "skills", fields={"dir": "D:/skills", "max_file_size": "123"},
                plugins_dir=root)
            self.assertTrue(written["ok"], written.get("error"))
            text = (folder / "plugin-config.ini").read_text(encoding="utf-8")
            self.assertIn("[config]", text)
            self.assertIn("dir = D:/skills", text)
            self.assertIn("max_file_size = 123", text)
            self.assertNotIn("[base]", text)
            bad = write_plugin_config(
                "skills", fields={"max_file_size": "not-a-number"},
                plugins_dir=root)
            self.assertFalse(bad["ok"])
            self.assertIn("整数", bad["error"])

    def test_kernel_model_tab_is_absent(self) -> None:
        status, payload = handle_get("/api/settings", {}, None)
        self.assertEqual(status, 200)
        self.assertNotIn("model_reasoning", [item["id"] for item in payload["sections"]])

    def test_unknown_route(self) -> None:
        status, payload = handle_post("/api/settings/nope", {}, None)
        self.assertEqual(status, 404)
        self.assertFalse(payload["ok"])


class StructuredPluginConfigTest(unittest.TestCase):
    """声明了 `settings-schema.json` 的插件：按组编辑，密钥不出接口。"""

    SCHEMA = {
        "kind": "sections",
        "title": "模型",
        "section_prefix": "model:",
        "identity": {"key": "id", "label": "模型 ID"},
        "fields": [
            {"key": "provider", "kind": "enum", "label": "协议", "default": "openai",
             "options": [{"value": "openai", "label": "OpenAI"},
                         {"value": "anthropic", "label": "Anthropic"}]},
            {"key": "base_url", "kind": "text", "label": "网关"},
            {"key": "api_key", "kind": "secret", "label": "密钥"},
            {"key": "context_window", "kind": "number", "label": "窗口",
             "min": 1, "required": True},
            {"key": "max_tokens", "kind": "number", "label": "回复上限", "min": 1,
             "show_if": {"key": "provider", "equals": "anthropic"}},
        ],
    }

    def _setup(self, tmp: str, config_text: str):
        root = Path(tmp) / "plugins"
        folder = root / "demo"
        folder.mkdir(parents=True)
        (folder / "plugin.py").write_text("PLUGIN_VERSION = '1.0'\n", encoding="utf-8")
        (folder / "settings-schema.json").write_text(
            json.dumps(self.SCHEMA, ensure_ascii=False), encoding="utf-8")
        (folder / "plugin-config.ini").write_text(config_text, encoding="utf-8")
        return root, folder

    def test_read_masks_the_secret(self) -> None:
        config = (
            "[model:a]\nprovider = openai\nbase_url = http://x\napi_key = sk-secret\n"
            "; 窗口说明\ncontext_window = 128000\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root, _folder = self._setup(tmp, config)
            payload = read_plugin_config("demo", plugins_dir=root)
            self.assertTrue(payload["ok"])
            editor = payload["editor"]
            self.assertEqual(editor["kind"], "sections")
            self.assertEqual([g["id"] for g in editor["groups"]], ["a"])
            group = editor["groups"][0]
            self.assertEqual(group["values"]["api_key"], "")
            self.assertTrue(group["configured"]["api_key"])
            self.assertEqual(group["values"]["context_window"], "128000")
            self.assertNotIn("sk-secret", json.dumps(payload))

    def test_required_field_rejects_an_empty_value(self) -> None:
        config = (
            "[model:a]\nprovider = openai\nbase_url = http://x\napi_key = sk-secret\n"
            "context_window = 128000\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root, folder = self._setup(tmp, config)
            payload = read_plugin_config("demo", plugins_dir=root)
            group = payload["editor"]["groups"][0]
            group["values"]["context_window"] = ""
            written = write_plugin_config("demo", groups=[group], plugins_dir=root)
            self.assertFalse(written["ok"])
            self.assertIn("不能为空", written["error"])
            text = (folder / "plugin-config.ini").read_text(encoding="utf-8")
            self.assertIn("context_window = 128000", text)

    def test_save_keeps_other_sections_and_an_untouched_secret(self) -> None:
        config = (
            "[custom]\nkeep = 1\n\n"
            "[model:a]\nprovider = openai\nbase_url = http://x\napi_key = sk-secret\n"
            "context_window = 128000\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root, folder = self._setup(tmp, config)
            payload = read_plugin_config("demo", plugins_dir=root)
            group = payload["editor"]["groups"][0]
            group["values"]["context_window"] = "256000"
            written = write_plugin_config(
                "demo", groups=[group], plugins_dir=root)
            self.assertTrue(written["ok"], written.get("error"))
            text = (folder / "plugin-config.ini").read_text(encoding="utf-8")
            self.assertIn("[custom]\nkeep = 1\n", text)
            self.assertIn("api_key = sk-secret", text)
            self.assertIn("context_window = 256000", text)

    def test_new_model_group_gets_a_generated_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root, folder = self._setup(
                tmp, "[model:a]\nprovider = openai\nmodel = first\n"
                "context_window = 128000\n")
            groups = read_plugin_config("demo", plugins_dir=root)["editor"]["groups"]
            groups.append({"id": "", "values": {"provider": "openai", "base_url": "http://x",
                                                "context_window": "128000"}})
            written = write_plugin_config(
                "demo", groups=groups, plugins_dir=root)
            self.assertTrue(written["ok"], written.get("error"))
            text = (folder / "plugin-config.ini").read_text(encoding="utf-8")
            self.assertIn("[model:a]", text)
            self.assertIn("[model:openai]", text)

    def test_save_rejects_an_unknown_key(self) -> None:
        config = "[model:a]\napi_key = sk-secret\n"
        with tempfile.TemporaryDirectory() as tmp:
            root, _folder = self._setup(tmp, config)
            bad = {"id": "a", "values": {"nope": "1"}, "configured": {}}
            result = write_plugin_config("demo", groups=[bad], plugins_dir=root)
            self.assertFalse(result["ok"])


class SettingsPageAssetsTest(unittest.TestCase):
    def test_gear_and_settings_script_are_inlined(self) -> None:
        from agent.shell.web.ui_bundle import inline_ui_html

        html = inline_ui_html()
        self.assertIn('id="hdrSettingsBtn"', html)
        self.assertIn("function bootSettingsPanel", html)
        self.assertIn(".st-modal{", html.replace(" ", "").replace("\n", ""))
