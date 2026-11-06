"""离线渲染依赖、文本隔离与实例释放的浏览器回归。"""

from tests.test_visualization import document
from tests.test_visualization_browser import VisualizationBrowserCase


class VisualizationRendererTest(VisualizationBrowserCase):
    def test_wheel_scrolls_conversation_over_charts_controls_and_diagrams(self):
        specs = [
            ("progress", {"items": [{"label": "进度", "value": 1, "total": 2}]}),
            ("bar", {"items": [{"label": "数量", "value": 3}]}),
            ("flow", {"nodes": [{"id": "a", "label": "提交"}, {"id": "b", "label": "保存"}], "edges": [{"source": "a", "target": "b"}]}),
            ("mermaid", {"code": "sequenceDiagram\n用户->>Agent: 请求\nAgent-->>用户: 回复"}),
            ("controls", {"fields": [
                {"id": "enabled", "label": "启用", "type": "toggle", "value": True},
                {"id": "count", "label": "数量", "type": "range", "min": 0, "max": 10, "step": 1, "value": 3},
                {"id": "scope", "label": "范围", "type": "select", "value": "a", "options": [{"value": "a", "label": "全部"}]},
                {"id": "mode", "label": "模式", "type": "tabs", "value": "a", "options": [{"value": "a", "label": "概览"}]},
            ]}),
            ("table", {"columns": [{"key": "name", "label": "名称"}], "rows": [{"name": f"行 {i}"} for i in range(40)]}),
        ]
        self.produce([document(kind, data) | {"panel_id": kind} for kind, data in specs])
        self.open_history()
        self.page.locator(".viz-echart svg").wait_for()
        self.page.wait_for_function("document.querySelectorAll('iframe.viz-mermaid').length===2")
        self.page.locator(".msgs").evaluate("node=>{let pad=document.createElement('div');pad.style.height='900px';node.appendChild(pad);}")
        for kind in ("progress", "bar", "flow", "mermaid", "controls"):
            panel = self.page.locator(f'.viz-card[data-kind="{kind}"] .viz-viewport')
            panel.scroll_into_view_if_needed()
            panel.hover()
            previous = self.page.locator(".msgs").evaluate("node=>node.scrollTop")
            self.page.mouse.wheel(0, 90)
            self.page.wait_for_function("old=>document.querySelector('.msgs').scrollTop>old", arg=previous)
        for selector in ("select", "input[type=checkbox]", "input[type=range]", "[data-viz-tab]"):
            self.page.locator(".viz-control " + selector).hover()
            previous = self.page.locator(".msgs").evaluate("node=>node.scrollTop")
            self.page.mouse.wheel(0, 90)
            self.page.wait_for_function("old=>document.querySelector('.msgs').scrollTop>old", arg=previous)
        viewport = self.page.locator('.viz-card[data-kind="table"] .viz-viewport')
        viewport.scroll_into_view_if_needed()
        viewport.hover()
        previous = self.page.locator(".msgs").evaluate("node=>node.scrollTop")
        self.page.mouse.wheel(0, 90)
        self.page.wait_for_function("document.querySelector('[data-kind=table] .viz-viewport').scrollTop>0")
        self.assertEqual(self.page.locator(".msgs").evaluate("node=>node.scrollTop"), previous)
        viewport.evaluate("node=>node.scrollTop=node.scrollHeight")
        self.page.mouse.wheel(0, 90)
        self.page.wait_for_function("old=>document.querySelector('.msgs').scrollTop>old", arg=previous)
        viewport.evaluate("node=>node.scrollTop=0")
        viewport.hover()
        previous = self.page.locator(".msgs").evaluate("node=>node.scrollTop")
        self.page.mouse.wheel(0, -90)
        self.page.wait_for_function("old=>document.querySelector('.msgs').scrollTop<old", arg=previous)
        self.assertEqual(self.errors, [])

    def test_failed_chart_dependency_is_local_and_reload_retries(self):
        self.produce([document(), document("progress", {"items": [{"label": "用例", "value": 1, "total": 2}]}) | {"panel_id": "progress"}])
        self.page.route("**/vendor/echarts/echarts.min.js", lambda route: route.abort())
        self.open_history()
        self.page.get_by_text("离线图表库无法加载", exact=False).wait_for()
        self.assertEqual(self.page.locator(".viz-progress").count(), 1)
        self.assertEqual(self.page.locator(".viz-content[role=alert]").count(), 1)
        self.page.unroute("**/vendor/echarts/echarts.min.js")
        self.page.reload()
        self.page.locator(".viz-echart svg").wait_for()
        self.assertEqual(self.page.locator(".viz-content[role=alert]").count(), 0)
        self.assertEqual(self.errors, [])

    def test_structured_flow_labels_cannot_inject_graph_or_active_content(self):
        label = '提交 "]-->evil[" <script> & #35;'
        self.produce([document("flow", {
            "nodes": [{"id": "a", "label": label}, {"id": "b", "label": "结束"}],
            "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}],
        })])
        self.open_history()
        frame = self.page.frame_locator("iframe.viz-mermaid")
        frame.locator("g.node").first.wait_for()
        self.assertEqual(frame.locator("g.node").count(), 2)
        self.assertEqual(frame.locator("path.flowchart-link").count(), 2)
        self.assertEqual(frame.locator("script,a,img,iframe").count(), 0)
        self.assertIn(label, frame.locator("g.node .nodeLabel").first.text_content())
        self.assertEqual(self.errors, [])
