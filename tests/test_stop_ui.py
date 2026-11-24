"""停止状态的有界观察、网络超时、原操作续查与失败重试。"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path


def run_ui(case, body):
    node = shutil.which("node")
    if node is None:
        case.skipTest("需要 Node 执行前端交互")
    path = Path(__file__).resolve().parents[1] / "plugins/web_ui/ui/classic/js/composer/state.js"
    harness = r"""
const vm=require("vm"),fs=require("fs"),assert=require("assert");
class Element{
 constructor(tag){this.tag=tag;this.children=[];this.textContent="";this.events={};this.removed=false;}
 appendChild(child){this.children.push(child);}
 replaceChildren(){this.children=[];this.textContent="";}
 setAttribute(key,value){this[key]=value;}
 addEventListener(key,fn){this.events[key]=fn;}
 remove(){this.removed=true;}
}
function boot(fetch,timing={}){
 const notices=[],contexts=[];
 const context={window:{},AbortController,performance,
  setTimeout:(fn,ms)=>setTimeout(fn,ms===500?0:ms),clearTimeout,
  document:{createElement:tag=>new Element(tag)},fetch,
  withConversationContext:(cid,fn)=>{contexts.push(cid);fn();},
  add:()=>{const n=new Element("div");notices.push(n);return n;},...timing};
 vm.createContext(context);
 vm.runInContext(fs.readFileSync(PATH,"utf8"),context);
 return {context,notices,contexts};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
""".replace("PATH", json.dumps(str(path)))
    script = harness + "\n(async()=>{\n" + body + "\n})().catch(error=>{console.error(error);process.exitCode=1;});"
    result = subprocess.run([node, "-"], input=script, text=True, encoding="utf-8",
                            capture_output=True, timeout=15)
    case.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class StopUITest(unittest.TestCase):
    def test_failure_retry_and_pending_queries_keep_conversation(self):
        run_ui(self, r"""
const calls=[];let fail=true,pending=false;
const {context,notices}=boot(async(url,options)=>{
 const body=JSON.parse(options.body);calls.push(body);
 if(pending)return{ok:true,status:body.stop_id?200:202,
  json:async()=>({stop_id:"stop-B",state:body.stop_id?"completed":"stopping"})};
 return{ok:!fail,status:fail?503:200,json:async()=>({state:fail?"failed":"completed",error:"部分后台进程未能终止"})};
});
assert.strictEqual(await context._requestConversationStop("original-cid","run-A"),false);
assert.strictEqual(notices[0].role,"alert");
assert.ok(notices[0].children[0].textContent.includes("未能终止"));
const retry=notices[0].children[1];assert.strictEqual(retry.textContent,"重试停止");
fail=false;retry.events.click();await tick();
assert.strictEqual(notices[0].removed,true);
assert.deepStrictEqual(calls.map(x=>x.conversation_id),["original-cid","original-cid"]);
assert.deepStrictEqual(calls.map(x=>x.run_id),["run-A","run-A"]);
pending=true;assert.strictEqual(await context._requestConversationStop("other-cid","run-B"),true);
assert.strictEqual(calls[2].stop_id,"");assert.strictEqual(calls[3].stop_id,"stop-B");
assert.strictEqual(notices[1].removed,true);
""")

    def test_observation_deadline_stops_polling_and_continue_reuses_original_id(self):
        run_ui(self, r"""
let now=0,done=false;const calls=[];
const {context,notices}=boot(async(url,options)=>{
 calls.push(JSON.parse(options.body));
 return{ok:true,status:done?200:202,json:async()=>({stop_id:"original-stop",state:done?"completed":"stopping"})};
},{performance:{now:()=>now},setTimeout:(fn,ms)=>{
 if(ms>500)return null;
 return setImmediate(()=>{now+=ms;fn();});
},clearTimeout:handle=>{if(handle)clearImmediate(handle);}});
assert.strictEqual(await context._requestConversationStop("cid-A","run-A"),false);
assert.strictEqual(now,30000);assert.strictEqual(calls.length,60);
assert.strictEqual(calls.filter(x=>!x.stop_id).length,1);
assert.ok(notices[0].children[0].textContent.includes("30 秒"));
const again=notices[0].children[1];assert.strictEqual(again.textContent,"继续查询");
done=true;again.events.click();await tick();
assert.strictEqual(calls[calls.length-1].stop_id,"original-stop");
assert.strictEqual(calls.filter(x=>!x.stop_id).length,1);
assert.strictEqual(notices[0].removed,true);
""")

    def test_hung_fetch_and_hung_response_body_abort_without_polling_forever(self):
        run_ui(self, r"""
for(const stage of ["fetch","body"]){
 let signal,count=0;
 const {context,notices}=boot(async(url,options)=>{
  signal=options.signal;count++;
  if(stage==="fetch")return new Promise(()=>{});
  return{ok:true,status:202,json:()=>new Promise(()=>{})};
 },{setTimeout:(fn)=>setImmediate(fn),clearTimeout:clearImmediate});
 assert.strictEqual(await context._requestConversationStop("cid-A","run-A",null,"known-stop"),false);
 assert.strictEqual(count,1);assert.strictEqual(signal.aborted,true);
 assert.ok(notices[0].children[0].textContent.includes("超时"));
 assert.strictEqual(notices[0].children[1].textContent,"继续查询");
}
""")

    def test_definite_cleanup_failure_retries_stop_instead_of_querying_failed_operation(self):
        run_ui(self, r"""
const calls=[];
const {context,notices}=boot(async(url,options)=>{
 const body=JSON.parse(options.body);calls.push(body);
 if(calls.length===1)return{ok:true,status:202,json:async()=>({stop_id:"failed-stop",state:"stopping"})};
 if(calls.length===2)return{ok:false,status:503,json:async()=>({stop_id:"failed-stop",state:"failed",error:"清理失败"})};
 return{ok:true,status:200,json:async()=>({stop_id:"retry-stop",state:"completed"})};
});
assert.strictEqual(await context._requestConversationStop("cid-A","run-A"),false);
assert.strictEqual(calls[1].stop_id,"failed-stop");
assert.strictEqual(notices[0].children[1].textContent,"重试停止");
notices[0].children[1].events.click();await tick();
assert.strictEqual(calls[2].stop_id,"");assert.strictEqual(notices[0].removed,true);
""")
