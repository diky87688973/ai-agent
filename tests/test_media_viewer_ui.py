"""原生媒体查看器的异步切换、元信息与资源释放。"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path


def run_viewer(case, body):
    node = shutil.which("node")
    if node is None:
        case.skipTest("需要 Node 执行媒体查看器交互")
    root = Path(__file__).resolve().parents[1]
    files = [root / "plugins/web_ui/ui/classic/js/core/ui-components.js",
             root / "plugins/web_ui/ui/classic/js/panels/file-viewers.js",
             root / "plugins/media_viewer/ui/viewer.js"]
    harness = r"""
const vm=require('vm'),fs=require('fs'),assert=require('assert');
const tick=()=>new Promise(r=>setImmediate(r));
const deferred=()=>{let resolve;return{promise:new Promise(r=>{resolve=r;}),resolve};};
class CustomEvent extends Event{constructor(name,options){super(name);this.detail=options&&options.detail;}}
class Element extends EventTarget{
 constructor(tag){super();this.tagName=tag.toUpperCase();this.children=[];this.attributes={};this.hidden=false;this.textContent='';}
 append(...items){this.children.push(...items);}
 appendChild(item){this.children.push(item);}
 replaceChildren(...items){this.children=items;}
 setAttribute(key,value){this.attributes[key]=value;}
 removeAttribute(key){delete this.attributes[key];if(key==='src')this.src='';}
 pause(){this.pauses=(this.pauses||0)+1;}
 load(){this.loads=(this.loads||0)+1;}
}
function boot(initial=true){
 const document=new EventTarget(),calls=[],panes=new Map(),pending=[],titles=new Map();let activePath='',activePane='';
 document.createElement=tag=>new Element(tag);
 document.currentScript={src:'http://localhost/api/plugin/media_viewer/_asset/ui/viewer.js',isConnected:true};
 const context={window:{},document,Event,CustomEvent,AbortController,setTimeout,clearTimeout,console,
  formatFileSize:n=>n+' bytes',filePaneId:path=>path,baseNameOnly:path=>path.replace(/\\/g,'/').split('/').pop(),
  closePane:id=>{document.dispatchEvent(new CustomEvent('ai-agent:panel-closed',{detail:{panel:id}}));panes.delete(id);},
  openDefaultFileTab:path=>{calls.push(['default',path]);},
  openPane:opts=>{if(activePane&&activePane!==opts.id)document.dispatchEvent(new CustomEvent('ai-agent:panel-deactivated',{detail:{panel:activePane}}));activePane=opts.id;titles.set(opts.id,opts.title);if(!panes.has(opts.id))panes.set(opts.id,new Element('section'));document.dispatchEvent(new CustomEvent('ai-agent:panel-activated',{detail:{panel:opts.id}}));return{querySelector:()=>panes.get(opts.id)};},
  fetch:(url,options)=>{const d=deferred();pending.push({...d,url,options});return d.promise;}};
 vm.createContext(context);
 vm.runInContext(fs.readFileSync(FILES[0],'utf8'),context);
 vm.runInContext(fs.readFileSync(FILES[1],'utf8'),context);
 function load(){context.classicComponents.apply([{path:'app/shell/web-ui/file-viewers/media',owner:'media_viewer',kind:'ui-control',
  metadata:{order:10,props:{version:1,label:'媒体',extensions:['.png','.mp4','.wav'],scripts:['ui/viewer.js']}}}]);
 vm.runInContext(fs.readFileSync(FILES[2],'utf8'),context);
 }if(initial)load();
 const info=(index,kind,name='sample.mp4')=>pending[index].resolve({ok:true,json:async()=>({version:1,kind,name,path:name,size_bytes:123})});
 return{context,pending,panes,titles,calls,info,document,load,open:path=>{activePath=path;return context.classicFileViewers.open(path);},
  id:path=>'media_viewer__file-'+encodeURIComponent(path),body:path=>panes.get('media_viewer__file-'+encodeURIComponent(path||activePath)),emit:(name,detail)=>document.dispatchEvent(new CustomEvent(name,{detail}))};
}
""".replace("FILES", json.dumps([str(path) for path in files]))
    result = subprocess.run([node, "-"], input=harness + "\n(async()=>{\n" + body
                            + "\n})().catch(error=>{console.error(error);process.exitCode=1;});",
                            text=True, encoding="utf-8", capture_output=True, timeout=15)
    case.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class MediaViewerUITest(unittest.TestCase):
    def test_each_full_path_owns_a_named_tab_and_reopen_preserves_playback(self):
        run_viewer(self, r"""
const h=boot(),a='D:/one/movie.mp4',b='D:/two/movie.mp4';
h.open(a);h.info(0,'video','movie.mp4');await tick();
const videoA=h.body(a).children[0].children[0];videoA.currentTime=17;
h.open(b);h.info(1,'video','movie.mp4');await tick();
const videoB=h.body(b).children[0].children[0];
assert.strictEqual(h.panes.size,2);assert.ok(videoA.pauses);assert.notStrictEqual(videoA.src,'');
assert.strictEqual(h.titles.get(h.id(a)),'movie.mp4');assert.strictEqual(h.titles.get(h.id(b)),'movie.mp4');
h.open(a);assert.strictEqual(h.pending.length,2);assert.strictEqual(h.body(a).children[0].children[0],videoA);
assert.strictEqual(videoA.currentTime,17);assert.ok(videoB.pauses);
h.context.closePane(h.id(a));assert.strictEqual(videoA.src,'');assert.notStrictEqual(videoB.src,'');
assert.strictEqual(h.panes.size,1);assert.strictEqual(h.pending[1].options.signal.aborted,false);
h.open(a);assert.strictEqual(h.pending.length,3);h.info(2,'video','movie.mp4');await tick();
h.emit('ai-agent:plugin-ui-release',{plugin:'media_viewer'});
assert.strictEqual(videoB.src,'');assert.ok(h.pending.every(x=>x.options.signal.aborted));
""")

    def test_open_before_catalog_waits_and_closed_pending_panel_never_reopens(self):
        run_viewer(self, r"""
const closed=boot(false);closed.open('early.mp4');assert.strictEqual(closed.pending.length,0);
closed.context.closePane('preparing-early.mp4');closed.load();await tick();
assert.strictEqual(closed.pending.length,0);assert.strictEqual(closed.panes.size,0);
const h=boot(false);h.open('early.mp4');h.load();await tick();
assert.strictEqual(h.pending.length,1);assert.strictEqual(h.panes.has('preparing-early.mp4'),false);
h.info(0,'video');await tick();assert.strictEqual(h.body().children[0].children[0].tagName,'VIDEO');
h.emit('ai-agent:panel-closed',{panel:h.id('early.mp4')});
const path='app/shell/web-ui/file-viewers/document';
h.context.classicComponents.apply([{path,owner:'doc_probe',kind:'ui-control',metadata:{order:20,
 props:{version:1,label:'文档',extensions:['.probe'],scripts:['ui/document.js']}}}]);
h.document.currentScript={src:'http://localhost/api/plugin/doc_probe/_asset/ui/document.js',isConnected:true};
let released=false;
h.context.window.aiAgentClassicComponents.register(path,{open(){return{activate(){},deactivate(){},dispose(){released=true;}};}});
h.open('file.probe');h.emit('ai-agent:panel-closed',{panel:'doc_probe__file-file.probe'});assert.strictEqual(released,true);
""")

    def test_original_controls_metadata_pause_and_close_release(self):
        run_viewer(self, r"""
const h=boot();h.open('video.mp4');h.info(0,'video');await tick();
h.open('video.mp4');assert.strictEqual(h.pending.length,1);
const video=h.body().children[0].children[0];
assert.strictEqual(video.tagName,'VIDEO');assert.strictEqual(video.controls,true);
assert.strictEqual(video.autoplay,undefined);assert.strictEqual(video.preload,'metadata');
video.videoWidth=1920;video.videoHeight=1080;video.duration=65;video.dispatchEvent(new Event('loadedmetadata'));
const details=h.body().children[2];
assert.ok(details.children.some(x=>x.children[1].textContent==='1920 × 1080 px'));
assert.ok(details.children.some(x=>x.children[1].textContent==='1 分 5 秒'));
assert.strictEqual(h.body().children[1].children[1].textContent,'sample.mp4');
assert.strictEqual(h.body().children[1].children[1].tagName,'DIV');
h.emit('ai-agent:panel-deactivated',{panel:h.id('video.mp4')});assert.ok(video.pauses);
h.emit('ai-agent:panel-closed',{panel:h.id('video.mp4')});
assert.strictEqual(video.src,'');assert.strictEqual(video.loads,1);assert.strictEqual(h.body().children.length,0);
assert.strictEqual(h.pending[0].options.signal.aborted,true);
""")

    def test_late_response_cannot_replace_new_file_and_unload_is_scoped(self):
        run_viewer(self, r"""
const h=boot();h.open('old.png');h.open('new.wav');
assert.strictEqual(h.pending[0].options.signal.aborted,false);
h.context.closePane(h.id('old.png'));assert.strictEqual(h.pending[0].options.signal.aborted,true);
h.info(1,'audio','new.wav');await tick();
const audio=h.body().children[0].children[0];assert.strictEqual(audio.tagName,'AUDIO');
h.info(0,'image','old.png');await tick();assert.strictEqual(h.body().children[0].children[0],audio);
h.emit('ai-agent:plugin-ui-release',{plugin:'other'});assert.notStrictEqual(audio.src,'');
h.emit('ai-agent:plugin-ui-release',{plugin:'media_viewer'});assert.strictEqual(audio.src,'');
assert.strictEqual(audio.loads,1);
assert.strictEqual(h.context.classicFileViewers.matches('text.txt'),false);
h.open('text.txt');assert.deepStrictEqual(h.calls,[['default','text.txt']]);
""")

    def test_image_dimensions_error_and_foreign_script_registration(self):
        run_viewer(self, r"""
const h=boot();h.open('picture.png');h.info(0,'image','<b>picture</b>.png');await tick();
const image=h.body().children[0].children[0];assert.strictEqual(image.tagName,'IMG');
image.naturalWidth=640;image.naturalHeight=480;image.dispatchEvent(new Event('load'));
assert.ok(h.body().children[2].children.some(x=>x.children[1].textContent==='640 × 480 px'));
assert.strictEqual(h.body().children[1].children[0].textContent,'<b>picture</b>.png');
image.dispatchEvent(new Event('error'));assert.strictEqual(h.body().children.at(-1).hidden,false);
h.open('picture.png');assert.strictEqual(h.pending.length,2);h.info(1,'image','retry.png');await tick();
h.document.currentScript.src='http://localhost/api/plugin/foreign/_asset/ui/viewer.js';
assert.throws(()=>h.context.window.aiAgentClassicComponents.register('app/shell/web-ui/file-viewers/media',{open(){}}));
h.document.currentScript.src='http://localhost/api/plugin/media_viewer/_asset/ui/viewer.js';
h.document.currentScript.isConnected=false;
assert.throws(()=>h.context.window.aiAgentClassicComponents.register('app/shell/web-ui/file-viewers/media',{open(){}}));
h.emit('ai-agent:panel-closed',{panel:h.id('picture.png')});
""")


if __name__ == "__main__":
    unittest.main()
