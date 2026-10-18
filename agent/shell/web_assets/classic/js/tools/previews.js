/* tools/previews.js —— 工具结果预览：stdout / 检索 / diff 预览卡填充。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
function fillToolPreview(o,ev){
const sc=(ev.script||"").toLowerCase();
if(!o.previewSlot)return;
if(sc.indexOf("run_command")>=0){
if(window.DEBUG)console.log("fillToolPreview: run_command entered, o=",o," ev.preview=",ev.preview);
o.previewSlot.innerHTML="";
o.previewSlot.style.display="none";
try{
var _raw=ev.preview||"{}";
if(window.DEBUG)console.log("fillToolPreview: _raw=",_raw);
const j=JSON.parse(_raw);
if(window.DEBUG)console.log("fillToolPreview: parsed=",j);
const out=(j&&j.data&&typeof j.data.stdout==="string")?j.data.stdout:"";
if(window.DEBUG)console.log("fillToolPreview: out=",out);
if(out){
o.previewSlot.style.display="block";
const cap=document.createElement("p");cap.textContent="stdout 预览";
const pr=document.createElement("pre");pr.className="sub";pr.innerHTML=out.length>12000?highlightCode(out.slice(0,12000),'bash')+"\n…":highlightCode(out,'bash');
o.previewSlot.appendChild(cap);o.previewSlot.appendChild(pr);
}
// 强制在对话区添加卡片
var testContent=out||"(空输出, raw="+_raw.slice(0,200)+")";
var cmdName=(o.args||{}).command||"命令行";
if(typeof cmdName==="string"&&cmdName.trim())cmdName=cmdName.trim().slice(0,60);
var cardHtml='<div class="chat-diff-card"><div class="chat-diff-cap">'+escapeHtml(cmdName)+'</div><div class="diff-unified diff-surface-adaptive"><pre style="margin:0;padding:4px 8px;font-size:11px">'+escapeHtml(testContent)+'</pre></div></div>';
var chatDiv=document.createElement("div");chatDiv.className="b a";chatDiv.innerHTML=cardHtml;
//
}catch(e){
if(window.DEBUG)console.error("fillToolPreview: error",e);
var errCard='<div class="chat-diff-card"><div class="chat-diff-cap">❌ 渲染异常</div><div class="diff-unified diff-surface-adaptive"><pre style="margin:0;padding:4px 8px;font-size:11px">'+escapeHtml(e.message)+'</pre></div></div>';
var errDiv=document.createElement("div");errDiv.className="b a";errDiv.innerHTML=errCard;
}
return;}
if(sc.indexOf("regex_locate")>=0){
o.previewSlot.innerHTML="";
o.previewSlot.style.display="none";
try{
var _rl=JSON.parse(ev.preview||"{}");
var _rlData=_rl&&_rl.data;
if(_rlData&&_rlData.type==="regex_locate"&&Array.isArray(_rlData.snippets)&&_rlData.snippets.length){
o.previewSlot.style.display="block";
var _rlCap=document.createElement("p");_rlCap.textContent="匹配结果 "+_rlData.count+" 处（预览 "+_rlData.snippets.length+" 条）";
var _rlPre=document.createElement("pre");_rlPre.className="sub";
_rlPre.innerHTML=_rlData.snippets.map(function(s){return escapeHtml(s);}).join("\n");
o.previewSlot.appendChild(_rlCap);o.previewSlot.appendChild(_rlPre);
}
}catch(e){if(window.DEBUG)console.error("regex_locate preview error",e);}
return;}
if(sc.indexOf("text_diff")>=0){
o.previewSlot.innerHTML="";
o.previewSlot.style.display="none";
try{
const _dj=JSON.parse(ev.preview||"{}");
const arr=(_dj&&_dj.data&&Array.isArray(_dj.data.diff))?_dj.data.diff:null;
if(arr&&arr.length){o.previewSlot.style.display="block";
const _cap=document.createElement("p");_cap.textContent="unified diff 预览";
const _box=document.createElement("div");_box.className="diff-unified diff-surface-adaptive";
renderUnifiedDiffRows(_box,arr);
o.previewSlot.appendChild(_cap);o.previewSlot.appendChild(_box);}
}catch(_e){}
return;}
if(sc.indexOf("file_undo")>=0){
o.previewSlot.innerHTML="";o.previewSlot.style.display="none";
try{
const _fu=JSON.parse(ev.preview||"{}");
const _fuAct=_fu&&_fu.data&&_fu.data.action;
const _fuDt=diffTextFromToolData(_fu&&_fu.data);
if(_fuAct==="diff"&&_fuDt.trim()){
o.previewSlot.style.display="block";
const cap=document.createElement("p");cap.textContent="版本比较 diff";
const wrap=document.createElement("div");
wrap.innerHTML=renderUnifiedDiffBodyAsCardsHtml(_fuDt);
if(!wrap.innerHTML.trim()){const box=document.createElement("div");box.className="diff-unified diff-surface-adaptive";renderUnifiedDiffRows(box,_fuDt.split(/\r?\n/));wrap.appendChild(box);}
o.previewSlot.appendChild(cap);o.previewSlot.appendChild(wrap);
}
}catch(_e){}
return;}
/* 编辑类工具的 diff 预览：write_file / replace_in_file / apply_patch / read_write
   共用一条渲染路径。
   四个工具（write_file / replace_in_file / apply_patch / read_write）走同一条路径：
   在界面上一点预览都没有（工具返回里明明带着 `_change.diff`）。
   判据只有一条 —— 结果里取得到 diff 就画，取不到就什么都不画（不画空卡片）。 */
if(sc.indexOf("write_file")>=0||sc.indexOf("replace_in_file")>=0
   ||sc.indexOf("apply_patch")>=0||sc.indexOf("read_write")>=0){
o.previewSlot.innerHTML="";
o.previewSlot.style.display="none";
try{
const j=JSON.parse(ev.preview||"{}");
const dt=diffTextFromToolData(j&&j.data);
const fp=(j&&j.data&&j.data.path)?String(j.data.path):"";
if(dt&&dt.trim()){
const capText=(sc.indexOf("apply_patch")>=0)?"补丁 diff 预览"
  :(sc.indexOf("replace_in_file")>=0)?"替换 diff 预览":"写入 diff 预览";
o.previewSlot.style.display="block";
const cap=document.createElement("p");
cap.textContent=(fp?baseNameOnly(fp)+" · ":"")+capText;
const wrap=document.createElement("div");
wrap.innerHTML=renderUnifiedDiffBodyAsCardsHtml(dt);
if(!wrap.innerHTML.trim()){
const box=document.createElement("div");
box.className="diff-unified diff-surface-adaptive";
renderUnifiedDiffRows(box,dt.split(/\r?\n/));
wrap.appendChild(box);
}
o.previewSlot.appendChild(cap);
o.previewSlot.appendChild(wrap);
}
}catch(_e2){}
return;}
}
