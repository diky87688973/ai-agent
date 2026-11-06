"""独立展示插件只新增目录，不依赖具体可视化插件。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

from agent.app import build_app
from agent.core.tool_call import ToolCallRequest
from agent.mechanisms.session_store import SessionStore
from agent.shell.web.auth import AuthRuntime
from agent.shell.web.server import create_server
from tests.test_core import ScriptedProvider
from tests.test_visualization_browser import ROOT, VisualizationBrowserCase


class IndependentDisplayPluginTest(VisualizationBrowserCase):
    def test_read_only_declaration_and_mode_failure_are_isolated(self):
        list(self.app.run_turn("展示独立插件", self.cid))
        self.page.goto(f"http://127.0.0.1:{self.server.server_port}/?cid={self.cid}")
        self.page.locator(".proof-card").wait_for()
        self.page.evaluate("""()=>aiAgentShell.displays.setCatalog([
          {kind:'ui-tool-shell',owner:'proof',path:'app/shell/web-ui/chat/messages/tools/proof_view',metadata:{props:{renderer:'proof.card',editable:false}}}
        ])""")
        self.assertEqual(self.page.locator(".aa-display-mode").count(), 0)
        self.assertTrue(self.page.evaluate("()=>{try{proofContext.mode.set('edit');return false;}catch(e){return true;}}"))
        facts = len(self.app.store.load(self.cid))
        self.page.evaluate("""()=>aiAgentShell.displays.setCatalog([
          {kind:'ui-tool-shell',owner:'proof',path:'app/shell/web-ui/chat/messages/tools/proof_view',metadata:{props:{renderer:'proof.card',editable:true}}}
        ])""")
        errors = []
        self.page.on("pageerror", lambda error: errors.append(str(error)))
        self.page.evaluate("()=>proofContext.mode.subscribe(()=>{throw new Error('broken editor');})")
        self.page.get_by_role("button", name="编辑视图", exact=True).click()
        self.page.get_by_text("无法切换展示模式：broken editor", exact=True).wait_for()
        self.assertEqual(errors, [])
        self.assertEqual(len(self.app.store.load(self.cid)), facts)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="display-extension-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        env = patch.dict(os.environ, {"AI_AGENT_DATA_ROOT": str(self.root / "data")})
        env.start()
        self.addCleanup(env.stop)
        plugins = self.root / "plugins"
        shutil.copytree(ROOT / "plugins" / "web_ui", plugins / "web_ui")
        self.fixture_plugin(plugins / "proof")
        manifest = self.root / "plugins.ini"
        manifest.write_text("[plugin:web_ui]\nenabled=1\n", encoding="utf-8")
        self.app = build_app(
            provider=ScriptedProvider(
                [
                    {"calls": [ToolCallRequest("proof-call", "proof_view", {})]},
                    {"text": "独立面板已展示。"},
                ]
            ),
            store=SessionStore(self.root / "data"),
            data_root=self.root / "data",
            plugins_path=manifest,
            plugins_dir=plugins,
        )
        self.addCleanup(self.app.dispose)
        config = self.root / "config.ini"
        config.write_text("[auth]\nmode=local\n", encoding="utf-8")
        auth = AuthRuntime.load(self.root / "data", config_path=config, host="127.0.0.1")
        self.server, _ = create_server(self.app, port=0, auth=auth, fs_root=[self.root])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.page = self.browser.new_page()
        self.addCleanup(self.page.close)
        self.cid = "independent-display-01"

    def fixture_plugin(self, folder):
        (folder / "ui").mkdir(parents=True)
        (folder / "plugin-meta.json").write_text(
            json.dumps({"name": "独立展示", "auto_load": True}), encoding="utf-8"
        )
        (folder / "plugin-slots.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "root": "app",
                    "slots": [
                        {
                            "path": "app/plugins/proof/tools/view",
                            "kind": "tool",
                            "factory": "plugin:make",
                        }
                    ],
                    "provides": [
                        {
                            "path": "app/shell/web-ui/chat/messages/tools/proof_view",
                            "kind": "ui-tool-shell",
                            "props": {"renderer": "proof.card", "editable": True, "scripts": ["ui/proof.js"]},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (folder / "plugin.py").write_text(
            """from agent.capabilities.registry import ToolPlugin
class Proof(ToolPlugin):
    name="proof_view"
    description="Display an independent card"
    parameters={}
    def execute(self, arguments):
        return {"display":{"version":1,"id":"proof","revision":1,"operation":"upsert","type":"proof.card","title":"独立插件","summary":"只增加目录即可展示","data":{}}}
def make(ctx): return Proof()
""",
            encoding="utf-8",
        )
        (folder / "ui" / "proof.js").write_text(
            """(function(){
aiAgentShell.displays.register("proof.card",function(host,doc,context){
var p=document.createElement("p");p.className="proof-card";p.textContent=doc.summary;host.appendChild(p);
p.dataset.mode=context.mode.get();
var stop=context.mode.subscribe(function(mode){p.dataset.mode=mode;});
window.proofContext=context;
return function(){stop();p.remove();};},"proof");})();""",
            encoding="utf-8",
        )

    def test_directory_only_extension_uses_declared_renderer_and_no_specific_plugin(self):
        paths = [
            ROOT / "agent" / "shell" / "web" / "ui" / "displays.js",
            ROOT / "agent" / "shell" / "web" / "ui_bundle.py",
            ROOT / "agent" / "capabilities" / "ui_registry.py",
        ]
        before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
        self.assertNotIn("visualization", self.app.plugin_host.loaded_names())
        self.assertIsNone(self.app.registry.get("visualize"))
        list(self.app.run_turn("展示独立插件", self.cid))
        self.page.goto(f"http://127.0.0.1:{self.server.server_port}/?cid={self.cid}")
        self.page.get_by_text("只增加目录即可展示", exact=True).wait_for()
        self.assertEqual(self.page.locator(".proof-card").count(), 1)
        self.assertEqual(self.page.locator(".proof-card").get_attribute("data-mode"), "view")
        self.page.get_by_role("button", name="编辑视图", exact=True).click()
        self.assertEqual(self.page.locator(".proof-card").get_attribute("data-mode"), "edit")
        self.page.get_by_role("button", name="完成编辑", exact=True).click()
        self.assertEqual(self.page.locator(".proof-card").get_attribute("data-mode"), "view")
        rejected = self.page.evaluate("""()=>{
try{aiAgentShell.displays.register("undeclared.type",function(){},"proof");return false;}catch(e){return true;}
}""")
        self.assertTrue(rejected)
        self.assertTrue(self.page.evaluate("()=>{try{proofContext.mode.set('invalid');return false;}catch(e){return true;}}"))
        self.assertEqual(before, [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths])
