"""真实任务、隔离 Mermaid 与高级组件的浏览器回归。"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from agent.core.context import SERVICE_BACKGROUND_TASKS
from agent.shell.plugin_settings import set_plugin_enabled, sync_plugins
from tests.test_visualization import document
from tests.test_visualization_browser import VisualizationBrowserCase


class VisualizationExtraBrowserTest(VisualizationBrowserCase):
    def test_mermaid_flow_sequence_bad_graph_and_svg_export_are_isolated(self):
        diagrams = [
            "flowchart LR\nA[提交]-->B[校验]",
            "sequenceDiagram\nautonumber\n用户->>Agent: 请求\nAgent-->>用户: 结果",
            "flowchart TD\nA[broken",
        ]
        documents = []
        for i, code in enumerate(diagrams):
            doc = document("mermaid", {"code": code})
            doc.update(panel_id=f"diagram-{i}", title=f"图 {i}")
            documents.append(doc)
        self.produce(documents)
        self.open_history()
        self.page.locator("iframe.viz-mermaid").nth(1).wait_for()
        self.assertEqual(self.page.locator("iframe.viz-mermaid").count(), 2)
        actors = self.page.frame_locator("iframe.viz-mermaid").nth(1).locator("rect.actor")
        self.assertTrue(actors.evaluate_all("""nodes=>nodes.length>=3&&nodes.every(node=>{
            const box=node.getBoundingClientRect();
            return Number(node.getAttribute('height'))===40&&box.height<=41&&box.width/box.height>=3&&node.getAttribute('rx')==='8';
        })"""))
        self.assertEqual(self.page.frame_locator("iframe.viz-mermaid").nth(1).locator("text.actor").first.evaluate("node=>getComputedStyle(node).fontSize"), "13px")
        diagram = self.page.frame_locator("iframe.viz-mermaid").nth(1).locator("svg")
        diagram.wait_for()
        self.assertTrue(diagram.evaluate(
            "svg=>{const box=svg.getBoundingClientRect();return box.top>=0&&box.bottom<=innerHeight&&box.right<=innerWidth;}"
        ))
        self.assertTrue(self.page.locator(".aa-display").evaluate_all(
            "nodes=>nodes.every(node=>node.scrollHeight<=node.clientHeight+1)"
        ))
        self.page.get_by_text("无法绘制：", exact=False).wait_for()
        self.assertEqual(self.page.locator("iframe.viz-mermaid").first.get_attribute("sandbox"), "")
        previous = self.page.locator(".viz-content").first.evaluate("node=>node._exportSvg")
        self.page.evaluate("themeUi.set('light')")
        self.page.wait_for_function("old=>document.querySelector('.viz-content')._exportSvg && document.querySelector('.viz-content')._exportSvg!==old", arg=previous)
        self.page.locator("iframe.viz-mermaid").nth(1).wait_for()
        self.page.get_by_text("无法绘制：", exact=False).wait_for()
        self.assertEqual(self.page.frame_locator("iframe.viz-mermaid").nth(1).locator("text.sequenceNumber").first.evaluate("node=>getComputedStyle(node).fill"), "rgb(255, 255, 255)")
        first = self.page.locator(".viz-card").first
        self.page.locator(".aa-display").first.get_by_role("button", name="编辑视图", exact=True).click()
        first.get_by_role("button", name="更多操作", exact=True).click()
        with self.page.expect_download() as download:
            first.get_by_role("button", name="导出 SVG", exact=True).click()
        svg = Path(download.value.path()).read_text(encoding="utf-8")
        self.assertIn("<svg", svg)
        self.assertNotIn("<script", svg)
        self.assertTrue(ET.fromstring(svg).tag.endswith("svg"))
        self.page.evaluate("""()=>{
          mermaid.render=()=>new Promise(resolve=>{window.finishQueuedDiagram=resolve;});
          const draw=aiAgentVisualization.components.get('mermaid');
          const doc={title:'queued',data:{code:'flowchart LR\\nA-->B'}};
          const first=document.createElement('div'),second=document.createElement('div');
          document.querySelector('.viz-card').append(first,second);
          window.pendingDiagrams=Promise.allSettled([
            draw(first,doc),draw(second,doc)
          ]);
        }""")
        self.page.wait_for_function("typeof window.finishQueuedDiagram === 'function'")
        set_plugin_enabled("visualization", False, app=self.app)
        sync_plugins(app=self.app)
        self.page.wait_for_function("!window.aiAgentVisualization && !window.mermaid")
        settled = self.page.evaluate("""async()=>{
          finishQueuedDiagram({svg:'<svg xmlns="http://www.w3.org/2000/svg"/>'});
          return (await pendingDiagrams).map(item=>item.status);
        }""")
        self.assertEqual(settled, ["rejected", "rejected"])
        self.assertEqual(self.page.locator("iframe.viz-mermaid").count(), 0)
        self.assertEqual(self.page.locator(".viz-mermaid-work").count(), 0)
        set_plugin_enabled("visualization", True, app=self.app)
        sync_plugins(app=self.app)
        self.page.locator("iframe.viz-mermaid").nth(1).wait_for()
        self.assertEqual(self.page.locator("iframe.viz-mermaid").count(), 2)
        self.assertEqual(self.errors, [])

    def test_real_task_states_cancel_reconnect_and_terminal_refresh(self):
        manager = self.app.context.get(SERVICE_BACKGROUND_TASKS)
        manager.set_notice(None)
        first = manager.create(
            self.cid,
            [sys.executable, "-c", "import time; time.sleep(2)"],
            str(self.root / "data"),
            10,
            "资料整理",
        )
        task = first["task"]
        failed = manager.create(
            self.cid,
            [sys.executable, "-c", "raise SystemExit(1)"],
            str(self.root / "data"),
            10,
            "失败任务",
            task["batch"],
        )
        cancelled = manager.create(
            self.cid,
            [sys.executable, "-c", "import time; time.sleep(20)"],
            str(self.root / "data"),
            30,
            "取消任务",
            task["batch"],
        )
        manager.cancel(self.cid, cancelled["task"]["task_id"], "测试取消")
        ids = [task["task_id"], failed["task"]["task_id"], cancelled["task"]["task_id"]]
        self.produce([document("tasks", {"batch": task["batch"], "task_ids": ids})])
        self.page.route("**/api/background/tasks?*batch=*", lambda route: route.abort())
        self.open_history()
        self.page.get_by_text("连接中断，保留上次显示；正在重试同步", exact=True).wait_for()
        self.page.unroute("**/api/background/tasks?*batch=*")
        self.page.wait_for_function(
            "document.querySelector('.viz-task-status').textContent.includes('100%')"
        )
        self.assertIn("失败", self.page.locator(".viz-task-row").all_inner_texts()[1])
        self.assertIn("取消", " ".join(self.page.locator(".viz-task-row").all_inner_texts()))
        self.page.reload()
        self.page.wait_for_function(
            "document.querySelector('.viz-task-status')?.textContent.includes('100%')"
        )
        self.assertEqual(self.errors, [])

    def test_controls_persist_and_insert_only_once(self):
        fields = [
            {
                "id": "scope",
                "label": "范围",
                "type": "select",
                "value": "all",
                "options": [{"value": "all", "label": "全部"}, {"value": "code", "label": "代码"}],
            },
            {"id": "enabled", "label": "启用", "type": "toggle", "value": False},
            {
                "id": "count",
                "label": "数量",
                "type": "range",
                "min": 0,
                "max": 10,
                "step": 1,
                "value": 3,
            },
            {
                "id": "mode",
                "label": "模式",
                "type": "tabs",
                "value": "a",
                "options": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
            },
        ]
        self.produce([document("controls", {"fields": fields})])
        self.open_history()
        self.page.get_by_label("范围", exact=True).select_option("code")
        self.page.get_by_label("启用", exact=True).check()
        self.page.get_by_label("数量", exact=True).focus()
        self.page.keyboard.press("ArrowRight")
        self.page.keyboard.press("ArrowRight")
        self.page.get_by_role("tab", name="B", exact=True).click()
        self.page.reload()
        self.page.locator(".viz-control").first.wait_for()
        self.assertEqual(self.page.get_by_label("范围", exact=True).input_value(), "code")
        self.assertTrue(self.page.get_by_label("启用", exact=True).is_checked())
        self.assertEqual(self.page.get_by_label("数量", exact=True).input_value(), "5")
        self.assertEqual(
            self.page.get_by_role("tab", name="B", exact=True).get_attribute("aria-selected"),
            "true",
        )
        button = self.page.get_by_role("button", name="加入输入", exact=True)
        button.click()
        self.assertTrue(button.is_disabled())
        self.assertIn("范围：代码", self.page.locator("#t").input_value())
        self.assertEqual(self.errors, [])

    def test_bar_line_donut_flow_and_time_components_have_selectable_data(self):
        specs = {
            "bar": {"items": [{"label": "收入", "value": 3}, {"label": "成本", "value": -1}]},
            "line": {"labels": ["周一", "周二"], "series": [{"label": "用量", "values": [1, 4]}]},
            "flow": {
                "nodes": [{"id": "a", "label": "开始"}, {"id": "b", "label": "执行校验并确认全部输入数据完整"},
                          {"id": "c", "label": "保存"}, {"id": "d", "label": "失败"},
                          {"id": "e", "label": "审核"}, {"id": "f", "label": "输出"}, {"id": "g", "label": "完成"}],
                "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"},
                          {"source": "b", "target": "d"}, {"source": "d", "target": "a"},
                          {"source": "a", "target": "g"}, {"source": "a", "target": "c"}],
            },
            "donut": {"items": [{"label": "A", "value": 1}, {"label": "B", "value": 2}]},
            "progress": {"items": [{"label": "用例", "value": 7, "total": 10}]},
            "timeline": {"unit": "s", "events": [{"label": "创建", "at": 0, "detail": "任务创建"}]},
            "gantt": {
                "unit": "h",
                "tasks": [{"label": "开发", "start": 0, "end": 4, "status": "running"}],
            },
            "waterfall": {
                "unit": "ms",
                "items": [{"label": "请求", "start": 0, "end": 50, "status": "succeeded"}],
            },
        }
        documents = []
        for kind, data in specs.items():
            doc = document(kind, data)
            doc.update(panel_id=kind, title=kind)
            documents.append(doc)
        self.produce(documents)
        self.open_history()
        self.assertEqual(self.page.locator(".viz-card").count(), len(specs))
        self.assertGreaterEqual(self.page.locator("[data-viz-pick]").count(), len(specs))
        flow = self.page.locator('.viz-card[data-kind="flow"]')
        flow.locator("iframe.viz-mermaid").wait_for()
        frame = flow.frame_locator("iframe.viz-mermaid")
        self.assertEqual(frame.locator("g.node").count(), 7)
        self.assertEqual(frame.locator("path.flowchart-link").count(), 6)
        self.assertIn("执行校验并确认全部输入数据完整", frame.locator("svg").text_content())
        self.assertTrue(frame.locator("g.node rect").evaluate_all(
            "nodes=>nodes.every(node=>node.getAttribute('rx')==='8')"
        ))
        self.page.wait_for_function("document.querySelectorAll('.viz-echart svg').length===5")
        self.assertLessEqual(self.page.locator('.viz-card[data-kind="donut"] .viz-echart').bounding_box()["height"], 300)
        chart = self.page.locator('.viz-card[data-kind="bar"] .viz-echart')
        self.assertEqual(chart.evaluate("node=>echarts.getInstanceByDom(node).getOption().series[0].data.map(item=>item.value)"), [3, -1])
        chart.evaluate("node=>echarts.getInstanceByDom(node).trigger('click',{data:{detail:'收入：3'}})")
        self.assertTrue(self.page.locator('.viz-card[data-kind="bar"] .viz-footer').is_hidden())
        self.page.locator('.aa-display').filter(has=self.page.locator('.viz-card[data-kind="bar"]')).get_by_role("button", name="编辑视图", exact=True).click()
        chart.evaluate("node=>echarts.getInstanceByDom(node).trigger('click',{data:{detail:'收入：3'}})")
        self.assertEqual(self.page.locator('.viz-card[data-kind="bar"] .viz-detail').inner_text(), "收入：3")
        chart.evaluate("node=>window.oldChart=echarts.getInstanceByDom(node)")
        set_plugin_enabled("visualization", False, app=self.app)
        sync_plugins(app=self.app)
        self.page.wait_for_function("!window.aiAgentVisualization && !window.echarts")
        self.assertTrue(self.page.evaluate("oldChart.isDisposed()"))
        self.assertEqual(self.page.locator(".viz-echart").count(), 0)
        self.assertEqual(self.page.locator('.viz-content[role="alert"]').count(), 0)
        self.assertEqual(self.errors, [])
