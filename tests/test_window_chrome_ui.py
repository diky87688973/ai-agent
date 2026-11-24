"""标题栏拖动贴顶、移动请求顺序与旧手势失效的前端回归。"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path


def run_window_ui(case, body):
    node = shutil.which("node")
    if node is None:
        case.skipTest("需要 Node 执行前端交互")
    path = Path(__file__).resolve().parents[1] / "plugins/web_ui/ui/classic/js/shell/window-chrome.js"
    harness = r"""
const vm=require('vm'),fs=require('fs'),assert=require('assert');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return{promise,resolve,reject};};
class Element{
 constructor(){this.events={};this.style={};this.classList={add(){},remove(){}};this.parentElement=null;}
 addEventListener(name,fn){(this.events[name]??=[]).push(fn);}
 emit(name,e){for(const fn of this.events[name]||[])fn(e);}
 closest(){return null;}
 setAttribute(key,value){this[key]=value;}
 appendChild(){}
}
function boot(){
 const header=new Element(),actions=new Element(),controls=new Element(),button=new Element();
 header.querySelector=()=>actions;controls.querySelector=()=>button;
 const doc=new Element();doc.documentElement=new Element();doc.body=new Element();
 doc.querySelector=selector=>selector==='header'?header:null;doc.createElement=()=>controls;
 const calls=[],errors=[],frames=new Map();let next=0;
 const api={window_position:async()=>[100,100],window_size:async()=>[1000,700],
  move_window:async(x,y)=>{calls.push(['move',x,y]);},
  cursor_at_work_area_top:async()=>true,toggle_maximize:value=>{calls.push(['maximize',value]);return Promise.resolve(true);}};
 const win={pywebview:{api},innerWidth:1000,innerHeight:700,outerWidth:1000,outerHeight:700,
  addEventListener(){}};
 const context={window:win,document:doc,HTMLElement:Element,Promise,
  requestAnimationFrame:fn=>{frames.set(++next,fn);return next;},
  cancelAnimationFrame:id=>frames.delete(id),setInterval(){},clearInterval(){},
  console:{error:(...args)=>errors.push(args)},
  getComputedStyle:()=>({overflowX:'visible',overflowY:'visible'})};
 vm.runInNewContext(fs.readFileSync(PATH,'utf8'),context);
 const event=(x=300,y=100)=>({button:0,target:header,screenX:x,screenY:y,clientX:100,clientY:30,preventDefault(){}});
 return{api,calls,errors,button,frames,
  down:()=>header.emit('mousedown',event()),
  move:(x=320,y=0)=>doc.emit('mousemove',event(x,y)),
  up:()=>doc.emit('mouseup',event()),
  double:()=>header.emit('dblclick',event()),
  frame:()=>{const batch=[...frames.values()];frames.clear();for(const fn of batch)fn();}};
}
""".replace("PATH", json.dumps(str(path)))
    result = subprocess.run([node, "-"], input=harness + "\n(async()=>{\n" + body
                            + "\n})().catch(e=>{console.error(e);process.exitCode=1;});",
                            text=True, encoding="utf-8", capture_output=True, timeout=15)
    case.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class WindowChromeUITest(unittest.TestCase):
    def test_release_flushes_final_move_before_maximize_and_drag_restores(self):
        run_window_ui(self, r"""
const h=boot(),first=deferred();
h.api.move_window=(x,y)=>{h.calls.push(['move',x,y]);return h.calls.length===1?first.promise:Promise.resolve();};
h.down();await tick();h.move();h.frame();
h.move(340,0);h.up();await tick();
assert.deepStrictEqual(h.calls,[['move',120,0]]);
first.resolve();await tick();
assert.deepStrictEqual(h.calls,[['move',120,0],['move',140,0],['maximize',true]]);
assert.strictEqual(h.button.title,'还原');assert.strictEqual(h.frames.size,0);
h.api.cursor_at_work_area_top=async()=>false;
const restored=deferred();h.api.toggle_maximize=value=>{h.calls.push(['maximize',value]);return restored.promise;};
h.down();await tick();h.move(350,300);h.up();await tick();
assert.deepStrictEqual(h.calls.at(-1),['maximize',false]);
restored.resolve(true);await tick();
assert.deepStrictEqual(h.calls.slice(-2).map(x=>x[0]),['maximize','move']);
assert.strictEqual(h.calls[h.calls.length-2][1],false);assert.strictEqual(h.button.title,'最大化');
const quick=boot();quick.down();await tick();quick.move();quick.up();await tick();
assert.deepStrictEqual(quick.calls.map(x=>x[0]),['move','maximize']);
""")

    def test_click_non_top_stale_gesture_and_failed_move_never_snap(self):
        run_window_ui(self, r"""
const click=boot();click.down();await tick();click.up();await tick();assert.deepStrictEqual(click.calls,[]);
const normal=boot();normal.api.cursor_at_work_area_top=async()=>false;
normal.down();await tick();normal.move(320,200);normal.up();await tick();
assert.deepStrictEqual(normal.calls.map(x=>x[0]),['move']);
const stale=boot(),top=deferred();stale.api.cursor_at_work_area_top=()=>top.promise;
stale.down();await tick();stale.move();stale.up();await tick();stale.down();
top.resolve(true);await tick();assert.deepStrictEqual(stale.calls.map(x=>x[0]),['move']);
const dbl=boot(),late=deferred();dbl.api.cursor_at_work_area_top=()=>late.promise;
dbl.down();await tick();dbl.move();dbl.up();await tick();dbl.double();late.resolve(true);await tick();
assert.deepStrictEqual(dbl.calls.filter(x=>x[0]==='maximize'),[['maximize',true]]);
dbl.double();assert.strictEqual(dbl.calls.at(-1)[1],false);
const fail=boot();fail.api.move_window=()=>Promise.reject(new Error('move failed'));
fail.down();await tick();fail.move();fail.up();await tick();
assert.deepStrictEqual(fail.calls,[]);assert.ok(fail.errors.length);
fail.api.move_window=async()=>{fail.calls.push(['move']);};
fail.down();await tick();fail.move();fail.up();await tick();
assert.deepStrictEqual(fail.calls,[['move'],['maximize',true]]);
""")


if __name__ == "__main__":
    unittest.main()
