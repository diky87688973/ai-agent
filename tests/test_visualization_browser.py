"""可选 Chromium 回归：实际工具事实、历史、交互与热插拔。"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.app import build_app
from agent.core.event_name import TOOL_DONE
from agent.core.tool_call import ToolCallRequest
from agent.mechanisms.session_store import SessionStore
from agent.shell.plugin_settings import set_plugin_enabled, sync_plugins
from agent.shell.web.auth import AuthRuntime
from agent.shell.web.server import create_server
from tests.test_core import ScriptedProvider
from tests.test_visualization import document

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec("playwright"), "需安装 playwright 与 Chromium")
class VisualizationBrowserCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import Error, sync_playwright

        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except Error as exc:
            cls.playwright.stop()
            raise unittest.SkipTest("Chromium 不可用：" + str(exc).splitlines()[0]) from exc

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="visualization-browser-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        env = patch.dict(os.environ, {"AI_AGENT_DATA_ROOT": str(self.root / "data")})
        env.start()
        self.addCleanup(env.stop)
        manifest = self.root / "plugins.ini"
        manifest.write_text(
            "[plugin:web_ui]\nenabled=1\n[plugin:base_settings]\nenabled=1\n"
            "[plugin:visualization]\nenabled=1\n[plugin:theme_style]\nenabled=1\n",
            encoding="utf-8",
        )
        self.provider = ScriptedProvider([])
        self.app = build_app(
            provider=self.provider,
            store=SessionStore(self.root / "data"),
            data_root=self.root / "data",
            plugins_path=manifest,
            plugins_dir=ROOT / "plugins",
        )
        self.addCleanup(self.app.dispose)
        config = self.root / "config.ini"
        config.write_text("[auth]\nmode=local\n", encoding="utf-8")
        auth = AuthRuntime.load(self.root / "data", config_path=config, host="127.0.0.1")
        self.server, _ = create_server(
            self.app,
            port=0,
            auth=auth,
            fs_root=[self.root],
            titles_dir=self.root / "titles",
            title_generator=lambda *_: "可视化回归",
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.page = self.browser.new_page(viewport={"width": 1200, "height": 900})
        self.addCleanup(self.page.close)
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.cid = "visualization-session-01"

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def produce(self, documents):
        calls = [
            ToolCallRequest(f"viz-call-{len(self.app.store.load(self.cid))}-{i}", "visualize", doc)
            for i, doc in enumerate(documents)
        ]
        self.provider._steps.extend([{"calls": calls}, {"text": "图表已经展示。"}])
        events = list(self.app.run_turn("展示可视化", self.cid))
        self.assertEqual(sum(event.type == TOOL_DONE for event in events), len(documents))

    def open_history(self):
        self.page.goto(f"http://127.0.0.1:{self.server.server_port}/?cid={self.cid}")
        self.page.locator(".viz-card").first.wait_for()


class VisualizationBrowserTest(VisualizationBrowserCase):
    def test_progress_defaults_to_presentation_and_editing_has_inset_selection(self):
        self.produce([document("progress", {"items": [{"label": "接口回归", "value": 7, "total": 10}]})])
        self.open_history()
        self.assertEqual(self.page.locator(".aa-display").get_attribute("data-display-mode"), "view")
        self.assertTrue(self.page.locator(".viz-toolbar").is_hidden())
        self.assertTrue(self.page.locator(".viz-footer").is_hidden())
        self.page.locator(".viz-progress").click()
        self.assertEqual(self.page.locator(".viz-selected").count(), 0)
        self.page.get_by_role("button", name="编辑视图", exact=True).click()
        self.assertTrue(self.page.locator(".viz-toolbar").is_visible())
        self.assertEqual(self.page.get_by_role("button", name="放大", exact=True).count(), 0)
        self.page.locator(".viz-progress").click()
        self.assertTrue(self.page.locator(".viz-footer").is_visible())
        self.assertTrue(self.page.locator(".viz-progress").evaluate("""row=>{
            const box=row.getBoundingClientRect(), label=row.querySelector('.viz-item-name').getBoundingClientRect();
            return label.left-box.left>=13 && label.top-box.top>=11;
        }"""))
        self.page.get_by_role("button", name="完成编辑", exact=True).click()
        self.assertTrue(self.page.locator(".viz-footer").is_hidden())
        self.assertEqual(self.page.locator(".viz-selected").count(), 0)
        self.page.evaluate("_setSessionRailOpen(false)")
        self.page.set_viewport_size({"width": 320, "height": 740})
        self.page.wait_for_function("document.querySelector('.aa-display').getBoundingClientRect().width >= 240")
        self.assertGreaterEqual(self.page.locator(".aa-display").bounding_box()["width"], 240)
        self.assertLessEqual(self.page.locator(".aa-display").bounding_box()["width"], 320)
        self.assertEqual(self.page.locator(".viz-viewport").evaluate("e=>e.scrollWidth<=e.clientWidth"), True)
        self.page.reload()
        self.page.locator(".viz-card").wait_for()
        self.assertEqual(self.page.locator(".aa-display").get_attribute("data-display-mode"), "view")
        self.assertEqual(self.errors, [])

    def test_unknown_protocol_is_visible_and_does_not_break_valid_cards(self):
        self.produce([document()])
        self.open_history()
        self.page.evaluate("""() => {
          const doc={version:99,id:'bad',revision:1,operation:'upsert',type:'visualization.proportion',title:'bad',summary:'invalid',data:{items:[]}};
          const frame={ok:true,tool_call_id:'invalid-call',preview:JSON.stringify({ok:true,data:{display:doc}})};
          aiAgentShell.displays.consume({tid:'invalid-call'},frame,msgs);
          aiAgentShell.displays.consume({tid:'invalid-call'},frame,msgs);
        }""")
        self.assertEqual(self.page.locator('.aa-display[role="alert"]').count(), 1)
        self.assertEqual(self.page.locator(".viz-card").count(), 1)
        self.assertEqual(self.errors, [])

    def test_invalid_view_state_requires_visible_reset(self):
        self.produce([document()])
        self.open_history()
        self.page.evaluate(
            "cid=>localStorage.setItem('aiAgent.displayView.v1/'+cid+'/context-layout','{broken')",
            self.cid,
        )
        self.page.reload()
        self.page.get_by_text("显示设置无法恢复，可重置显示", exact=True).wait_for()
        self.page.get_by_role("button", name="重置显示", exact=True).click()
        self.assertNotIn("无法恢复", self.page.locator(".viz-detail").inner_text())
        self.page.evaluate(
            "cid=>localStorage.setItem('aiAgent.displayView.v1/'+cid+'/context-layout',JSON.stringify({version:1,revision:1,value:false}))",
            self.cid,
        )
        self.page.reload()
        self.page.get_by_text("显示设置无效，可重置显示", exact=True).wait_for()
        self.assertEqual(self.errors, [])

    def test_proportion_selection_filter_refresh_themes_and_narrow_view(self):
        self.produce([document()])
        self.open_history()
        self.page.locator(".viz-echart svg").wait_for()
        self.assertEqual(self.page.locator(".viz-legend-item[data-viz-pick]").count(), 2)
        self.assertTrue(self.page.locator(".viz-toolbar").is_hidden())
        self.assertTrue(self.page.locator(".viz-footer").is_hidden())
        self.page.get_by_role("button", name="编辑视图", exact=True).click()
        self.page.locator(".viz-legend-item[data-viz-pick]").first.focus()
        self.page.keyboard.press("Enter")
        self.assertIn("25", self.page.locator(".viz-detail").inner_text())
        selected = self.page.locator(".viz-legend-item.viz-selected")
        self.assertEqual(selected.evaluate("e=>getComputedStyle(e).outlineStyle"), "none")
        self.assertNotEqual(selected.evaluate("e=>getComputedStyle(e).backgroundColor"), "rgba(0, 0, 0, 0)")
        self.page.get_by_role("button", name="加入输入").click()
        self.assertIn("上下文分配", self.page.locator("#t").input_value())
        self.page.locator(".viz-filter").fill("历史")
        self.page.reload()
        self.page.locator(".viz-card").wait_for()
        self.assertEqual(self.page.locator(".viz-filter").input_value(), "历史")
        self.assertEqual(self.page.locator(".viz-legend-item[data-viz-pick]").count(), 1)
        for theme in ("light", "dark"):
            self.page.evaluate("themeUi.set", theme)
            self.page.wait_for_function("window.__themeStyle && window.__themeStyle.current()")
            self.page.evaluate("window.__themeStyle.apply('minimal')")
            self.assertNotEqual(
                self.page.locator(".viz-title").evaluate("e=>getComputedStyle(e).color"),
                self.page.locator(".aa-display").evaluate("e=>getComputedStyle(e).backgroundColor"),
            )
        self.page.evaluate("_setSessionRailOpen(false)")
        self.page.set_viewport_size({"width": 320, "height": 740})
        self.page.wait_for_function("document.querySelector('.aa-display').getBoundingClientRect().width >= 240")
        self.assertLessEqual(self.page.locator(".aa-display").bounding_box()["width"], 320)
        self.assertEqual(self.errors, [])

    def test_revision_order_duplicates_delete_and_unknown_version(self):
        self.produce([document()])
        second = document(revision=2)
        second["title"] = "新的分配"
        self.produce([second])
        self.open_history()
        self.assertEqual(self.page.locator(".viz-card").count(), 1)
        self.assertEqual(self.page.locator(".viz-title").inner_text(), "新的分配")
        self.assertIn("已由修订 2 替换", self.page.locator(".msgs").inner_text())
        removal = document(revision=3)
        removal.update(operation="remove", data={})
        self.produce([removal])
        self.page.reload()
        self.page.get_by_text("上下文分配 · 已移除", exact=True).wait_for()
        self.assertEqual(self.page.locator(".viz-card").count(), 0)
        self.assertEqual(self.errors, [])

    def test_plugin_unload_reenable_and_two_session_state_isolation(self):
        self.produce([document()])
        self.open_history()
        self.page.get_by_role("button", name="编辑视图", exact=True).click()
        self.page.locator(".viz-filter").fill("系统")
        set_plugin_enabled("visualization", False, app=self.app)
        sync_plugins(app=self.app)
        self.page.get_by_text(
            "上下文分配 · 此组件尚未启用。系统占 25%，历史占 75%。", exact=True
        ).wait_for()
        self.assertEqual(self.page.locator(".viz-card").count(), 0)
        set_plugin_enabled("visualization", True, app=self.app)
        sync_plugins(app=self.app)
        self.page.locator(".viz-card").wait_for()
        self.assertEqual(self.page.locator(".viz-filter").input_value(), "系统")
        self.cid = "visualization-session-02"
        self.produce([document()])
        self.page.evaluate("id=>openConversationFromMenu(id,'第二会话')", self.cid)
        self.page.locator(".viz-card").wait_for()
        self.assertEqual(self.page.locator(".viz-filter").input_value(), "")
        self.assertEqual(self.errors, [])

    def test_table_text_is_safe_sorting_and_exports(self):
        table = document(
            "table",
            {
                "columns": [{"key": "name", "label": "名称"}, {"key": "value", "label": "数值"}],
                "rows": [
                    {"name": "<img src=x onerror=alert(1)>", "value": 10},
                    {"name": "正常", "value": -2},
                ],
            },
        )
        table["data"]["rows"].extend({"name": f"条目 {i}", "value": i + 20} for i in range(30))
        self.produce([table])
        self.open_history()
        self.assertEqual(self.page.locator(".viz-table img").count(), 0)
        for theme in ("light", "dark"):
            self.page.evaluate("themeUi.set", theme)
            self.page.locator(".viz-viewport").evaluate("node=>node.scrollTop=70")
            self.page.wait_for_timeout(50)
            self.assertTrue(self.page.locator(".viz-viewport").evaluate("""node=>{
                const top=node.getBoundingClientRect().top;
                return Array.from(node.querySelectorAll('th')).every(th=>Math.abs(th.getBoundingClientRect().top-top)<1);
            }"""))
        self.page.get_by_role("button", name="数值", exact=True).click()
        self.assertIn("正常", self.page.locator("tbody tr").first.inner_text())
        self.page.get_by_role("button", name="编辑视图", exact=True).click()
        self.page.get_by_role("button", name="更多操作", exact=True).click()
        with self.page.expect_download() as download:
            self.page.get_by_role("button", name="导出 JSON", exact=True).click()
        exported = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
        self.assertEqual(exported["data"], table["data"])
        self.assertEqual(self.errors, [])
