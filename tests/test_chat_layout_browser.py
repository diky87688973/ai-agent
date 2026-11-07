"""底部浮层、消息留白和滚动命中的布局回归。"""
from tests.test_visualization import document
from tests.test_visualization_browser import VisualizationBrowserCase


class ChatLayoutBrowserTest(VisualizationBrowserCase):
    def prepare_history(self):
        self.produce([document("progress", {"items": [{"label": "进度", "value": 1, "total": 2}]})])
        self.provider._steps.append({"text": "\n\n".join(f"历史消息段落 {i}" for i in range(60))})
        list(self.app.run_turn("布局回归", self.cid))
        self.open_history()
        self.page.wait_for_function("getActiveTab().historyLoaded===true")
        self.page.evaluate("""renderTodoListFromEvent({items:[
            {text:'任务一',done:false},{text:'任务二',done:true}
        ],all_done:false,collapsed:false},getActiveConversationId())""")
        self.page.wait_for_function("parseFloat(getComputedStyle(document.querySelector('.chat')).getPropertyValue('--todo-inset'))>0")
        self.page.wait_for_timeout(400)

    def test_bottom_blank_space_scrolls_messages_without_covering_last_message(self):
        self.prepare_history()
        for theme, width in (("light", 1200), ("dark", 1200), ("light", 520)):
            self.page.evaluate("themeUi.set", theme)
            self.page.evaluate("_setSessionRailOpen(false)")
            self.page.set_viewport_size({"width": width, "height": 900})
            self.page.wait_for_timeout(250)
            self.page.locator(".msgs").evaluate("node=>node.scrollTop=100")
            chat = self.page.locator("section.chat").bounding_box()
            row = self.page.locator("section.chat>.row").bounding_box()
            messages = self.page.locator(".msgs").bounding_box()
            self.assertGreaterEqual(row["x"] - messages["x"], 10)
            self.assertLessEqual(row["x"] + row["width"], messages["x"] + messages["width"] - 10)
            x, y = chat["x"] + 5, row["y"] + row["height"] / 2
            self.assertTrue(self.page.evaluate("([x,y])=>!!document.elementFromPoint(x,y).closest('.msgs')", [x, y]))
            self.page.mouse.move(x, y)
            self.page.mouse.wheel(0, 120)
            self.page.wait_for_function("document.querySelector('.msgs').scrollTop>100")
            self.page.locator(".msgs").evaluate("node=>node.scrollTop=node.scrollHeight")
            self.page.wait_for_timeout(100)
            self.assertTrue(self.page.evaluate("""()=>{
                const messages=document.querySelector('.msgs'),todo=document.querySelector('.todo-list-area');
                return messages.lastElementChild.getBoundingClientRect().bottom<=todo.getBoundingClientRect().top+1;
            }"""))
        self.assertEqual(self.errors, [])

    def test_dynamic_composer_height_preserves_reading_and_bottom_follow(self):
        self.prepare_history()
        self.page.locator(".msgs").evaluate("node=>node.scrollTop=100")
        self.page.wait_for_timeout(100)
        old = self.page.locator(".chat").evaluate("node=>parseFloat(getComputedStyle(node).getPropertyValue('--composer-inset'))")
        self.page.locator("#t").evaluate("node=>node.style.height='200px'")
        self.page.wait_for_function("old=>parseFloat(getComputedStyle(document.querySelector('.chat')).getPropertyValue('--composer-inset'))>old", arg=old)
        self.assertAlmostEqual(self.page.locator(".msgs").evaluate("node=>node.scrollTop"), 100, delta=1)
        self.page.locator(".msgs").evaluate("node=>node.scrollTop=node.scrollHeight")
        self.page.wait_for_function("document.querySelector('.msgs')._atBottom===true")
        self.page.locator(".todo-list-area").evaluate("node=>node.classList.add('collapsed')")
        self.page.wait_for_function("parseFloat(getComputedStyle(document.querySelector('.chat')).getPropertyValue('--todo-inset'))<50")
        self.page.wait_for_function("(()=>{const n=document.querySelector('.msgs');return n.scrollHeight-n.scrollTop-n.clientHeight<16})()")
        self.page.evaluate("()=>createConversationTab()")
        self.page.wait_for_function("parseFloat(getComputedStyle(document.querySelector('.chat')).getPropertyValue('--todo-inset'))===0")
        self.page.evaluate("id=>switchConversationTab(id)", self.cid)
        self.page.wait_for_function("parseFloat(getComputedStyle(document.querySelector('.chat')).getPropertyValue('--todo-inset'))>0")
        self.assertEqual(self.errors, [])
