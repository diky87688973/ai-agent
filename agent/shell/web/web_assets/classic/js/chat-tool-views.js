function chatToolName(script){
var s=String(script||"").toLowerCase();
var parts=s.match(/[a-z0-9_]+/g);
return parts&&parts.length?parts[parts.length-1]:s;
}
/* 工具壳详情里的图片交给统一预览。
   不自己再写一层弹层：缩放、居中、关闭与键盘响应已经有 `image-lightbox.js`，
   两套实现必然漂。`AIA` 缺失时只降级为不可点击，不报错 ——
   预览是附加能力，拿不到就不该把整个工具卡弄坏。 */
function bindToolShotPreview(img){
if(!img)return;
if(window.AIA&&typeof AIA.openImageLightbox==="function"){
img.classList.add("chat-tool-shot-clickable");
img.title=img.title||"点击查看大图（默认 1:1）";
img.style.cursor="zoom-in";
}
}
/* 事件收在 document 上，与缩略图同一条思路：
   卡片是流式重画出来的，每次重画都重新绑监听既浪费也会漏。 */
document.addEventListener("click",function(ev){
var t=ev.target;
if(!t||!t.closest)return;
var img=t.closest(".chat-tool-shot-clickable");
if(!img)return;
if(!window.AIA||typeof AIA.openImageLightbox!=="function")return;
ev.preventDefault();
ev.stopPropagation();
AIA.openImageLightbox(img.currentSrc||img.src);
});
function isPreviewEditTool(script, args){
var n=chatToolName(script);
if(n!=="write_file"&&n!=="replace_in_file"&&n!=="read_write"&&n!=="apply_patch")return false;
var dr=argGet(args,"dry_run");
return dr!==false&&dr!==0;
}
function isEditFamilyTool(script){
var n=chatToolName(script);
return n==="write_file"||n==="replace_in_file"||n==="read_write"||n==="apply_patch"||n==="commit_write"||n==="review_conclusion";
}
function editFamilyTitle(script, args){
var n=chatToolName(script);
if(n==="review_conclusion")return "Review";
if(n==="commit_write")return "提交修改";
var dr=argGet(args,"dry_run");
return (dr!==false&&dr!==0)?"预览修改":"提交修改";
}
function chatCachedConfirmPath(args){
var cid=String(argGet(args,"confirm_id")||"").trim();
if(!cid||!window.confirmPathCache)return "";
return String(window.confirmPathCache[cid]||"").trim();
}
function chatReviewPath(args){
var fn=String(argGet(args,"file_name")||argGet(args,"path")||"").trim();
var cached=chatCachedConfirmPath(args);
if(!cached)return fn;
if(!fn)return cached;
var leaf=baseNameOnly(cached);
var parts=fn.split(/[,，]/).map(function(s){return String(s||"").trim();}).filter(Boolean);
if(!parts.length)return cached;
return parts.map(function(p){
if(p===cached||p===leaf||baseNameOnly(p)===leaf)return cached;
if(parts.length===1&&p.indexOf("/")<0&&p.indexOf("\\")<0)return cached;
return p;
}).join(", ");
}
function chatEditPath(script, args){
var n=chatToolName(script);
if(n==="review_conclusion")return chatReviewPath(args);
if(n==="commit_write"){
var cid=String(argGet(args,"confirm_id")||"").trim();
var cached=(window.confirmPathCache&&cid&&window.confirmPathCache[cid])||"";
return String(cached||argGet(args,"path")||argGet(args,"dest_path")||argGet(args,"source_path")||"").trim();
}
var src=String(argGet(args,"source_path")||"").trim();
var dst=String(argGet(args,"dest_path")||argGet(args,"path")||"").trim();
if(src&&dst&&src!==dst)return src+" → "+dst;
return dst||src||String(argGet(args,"file_name")||"").trim();
}
function commandSummaryLine(cmd){
return String(cmd||"").replace(/\s+/g," ").trim();
}
function chatExecSource(o){
var n=chatToolName(o&&o.script);
if(n==="python_inline")return String((o&&o.args&&o.args.code)||"");
return String((o&&o.args&&o.args.command)||"");
}
function chatExecLang(script){
return chatToolName(script)==="python_inline"?"python":"bash";
}
function chatThinkTail(full){
var raw=String(full||"");
var slice=raw.length>100?raw.slice(-100):raw;
return slice.replace(/\s+/g," ").trim();
}
function chatThinkElapsedLabel(ms){
var total=Math.max(0, Math.round((Number(ms)||0)/1000));
if(total<60)return "用时 "+total+" 秒";
var h=Math.floor(total/3600);
var m=Math.floor((total%3600)/60);
var s=total%60;
if(h>0)return "用时 "+h+" 小时 "+m+" 分 "+s+" 秒";
return "用时 "+m+" 分 "+s+" 秒";
}
function sealChatThinkElapsed(){
if(!lastLlm||!lastLlm.chatThink||!lastLlm.chatThinkStartedAt)return;
var endedAt=lastLlm.chatThinkLastAt||Date.now();
var label=chatThinkElapsedLabel(Math.max(0, endedAt-lastLlm.chatThinkStartedAt));
var sum=lastLlm.chatThink._sum;
if(sum)sum.textContent=label;
lastLlm.chatThinkSealed=true;
}
var chatToolPathKeys=["path","source_path","dest_path","source","dest","file_name","old_path","new_path","patch_file","left_file","right_file","file","cwd","request_file","payload_file"];
function chatToolArgPaths(args){
var out=[], seen={};
for(var i=0;i<chatToolPathKeys.length;i++){
var v=argGet(args, chatToolPathKeys[i]);
if(typeof v!=="string")continue;
v=v.trim();
if(!v||seen[v])continue;
if(v.indexOf("/")<0&&v.indexOf("\\")<0&&!/^[A-Za-z]:/.test(v))continue;
seen[v]=1;
out.push(v);
}
return out;
}
function chatToolReplaceToken(text, needle, full){
if(!needle||needle===full||text.indexOf(needle)<0)return text;
var edge=function(ch){return !ch||/[\s·→↔|/\\:：,，()（）]/.test(ch);};
var out="", i=0;
while(i<text.length){
var at=text.indexOf(needle, i);
if(at<0){out+=text.slice(i);break;}
var before=at>0?text.charAt(at-1):"";
var after=text.charAt(at+needle.length)||"";
if(edge(before)&&edge(after)){out+=text.slice(i,at)+full;i=at+needle.length;}
else{out+=text.slice(i,at+needle.length);i=at+needle.length;}
}
return out;
}
/* 标题栏里出现的文件名换成参数里的完整路径。步骤卡仍用短名。 */
function chatToolExpandPaths(text, args){
var out=String(text||"");
var paths=chatToolArgPaths(args);
if(!out||!paths.length)return out;
var reps=[];
for(var i=0;i<paths.length;i++){
var full=paths[i];
var leaf=pathLeaf(full);
var base=baseNameOnly(full);
if(leaf&&leaf!==full)reps.push({n:leaf, full:full, w:leaf.length+1000});
if(base&&base!==full&&base!==leaf)reps.push({n:base, full:full, w:base.length});
}
reps.sort(function(a,b){return b.w-a.w;});
for(var j=0;j<reps.length;j++){
var full=reps[j].full, needle=reps[j].n;
if(out.indexOf(full)>=0){
var parts=out.split(full);
for(var k=0;k<parts.length;k++)parts[k]=chatToolReplaceToken(parts[k], needle, full);
out=parts.join(full);
}else out=chatToolReplaceToken(out, needle, full);
}
return out;
}
function chatDiffCounts(text){
var del=0, add=0;
var lines=String(text||"").replace(/\r/g,"").split("\n");
for(var i=0;i<lines.length;i++){
var L=lines[i];
if(L.indexOf("--- ")===0||L.indexOf("+++ ")===0)continue;
var c=L.charAt(0);
if(c==="-")del++;
else if(c==="+")add++;
}
return {del:del, add:add};
}
function paintPreviewSummary(row, path, text){
if(!row||!row._sum)return;
var stat=chatDiffCounts(text);
var parts=[];
if(path)parts.push({text:path});
if(stat.del)parts.push({text:"-"+stat.del, cls:"chat-diff-neg"});
if(stat.add)parts.push({text:"+"+stat.add, cls:"chat-diff-pos"});
var sum=row._sum;
sum.textContent="";
for(var i=0;i<parts.length;i++){
if(i)sum.appendChild(document.createTextNode(" "));
if(parts[i].cls){
var s=document.createElement("span");
s.className=parts[i].cls;
s.textContent=parts[i].text;
sum.appendChild(s);
}else sum.appendChild(document.createTextNode(parts[i].text));
}
}
/* 版本目录名形状：`YYYYMMDD_HHMMSS_mmm_序号_随机`。取中间的 HHMMSS，与回滚标题同一条规则。 */
function chatVersionStamp(modId){
var mid=String(modId||"").trim();
if(!mid)return "";
var mv=/_(\d{6})_\d{3}_\d{4}_[0-9a-z]+$/.exec(mid);
if(!mv)return "";
return mv[1].slice(0,2)+":"+mv[1].slice(2,4)+":"+mv[1].slice(4,6);
}
function chatVersionComparePath(o, ev){
var fromArgs=String(argGet(o&&o.args,"path")||"").trim();
var j=ev?chatToolParsePreview(ev):null;
var d=j&&j.data&&typeof j.data==="object"?j.data:null;
var fromData=d?String(d.path||"").trim():"";
return fromData||fromArgs;
}
function chatVersionCompareStamp(o, ev){
var fromArgs=chatVersionStamp(argGet(o&&o.args,"mod_id"));
if(fromArgs)return fromArgs;
var j=ev?chatToolParsePreview(ev):null;
var d=j&&j.data&&typeof j.data==="object"?j.data:null;
return d?chatVersionStamp(d.mod_id):"";
}
function chatVersionCompareLabel(path, stamp){
path=String(path||"").trim();
stamp=String(stamp||"").trim();
if(path&&stamp)return path+" to "+stamp;
if(path)return path;
if(stamp)return "to "+stamp;
return "";
}
function chatToolResultData(ev){
/* 从 tool_end.preview 取工具结果：信封用 `.data`，旧帧/裸结果则用对象本身。 */
var parsed=chatToolParsePreview(ev);
if(!parsed||typeof parsed!=="object")return null;
if(parsed.data!==undefined&&typeof parsed.data==="object"&&parsed.data!==null)return parsed.data;
if(parsed._change||parsed.path||parsed.files||parsed.diff||parsed.diffText||parsed.diff_text||parsed._diff)return parsed;
return null;
}
function chatPaintDiffPane(pane, o, ev){
if(!pane)return "";
pane.innerHTML="";
var data=chatToolResultData(ev);
var dt=typeof diffTextFromToolData==="function"?diffTextFromToolData(data):"";
var html=dt&&dt.trim()?renderUnifiedDiffBodyAsCardsHtml(dt):"";
if(html)pane.innerHTML=html;
else if(dt&&dt.trim()){
var box=document.createElement("div");
box.className="diff-unified diff-surface-adaptive";
renderUnifiedDiffRows(box, dt.split(/\r?\n/));
pane.appendChild(box);
}else{
/* 预览区只画 diff；完整信封在「查看报文」。无差异时不落整段 JSON。 */
addChatToolText(pane, "（无文本差异）");
}
return dt||"";
}
function chatReadFileContent(ev){
var j=chatToolParsePreview(ev);
if(!j)return null;
var d=j.data&&typeof j.data==="object"?j.data:j;
return typeof d.content==="string"?d.content:null;
}
function chatImageData(o, ev){
var j=ev?chatToolParsePreview(ev):null;
return j&&j.data&&typeof j.data==="object"?j.data:{};
}
function chatImagePath(o, ev){
var fromArgs=String(argGet(o&&o.args,"path")||"").trim();
var fromData=String(chatImageData(o, ev).path||"").trim();
return fromData||fromArgs;
}
function chatImageSize(o, ev){
var d=chatImageData(o, ev);
var w=Number(d.width), h=Number(d.height);
if(!(w>0)||!(h>0))return "";
return Math.round(w)+" × "+Math.round(h)+" px";
}
function makeChatToolRow(title, summary){
var row=document.createElement("div");
row.className="chat-tool-row";
var head=document.createElement("button");
head.type="button";
head.className="chat-tool-head";
head.setAttribute("aria-expanded","false");
var t=document.createElement("span");t.className="chat-tool-title";t.textContent=title;
var sum=document.createElement("span");sum.className="chat-tool-sum";sum.textContent=summary||"";
var chev=document.createElement("span");chev.className="chat-tool-chev";chev.setAttribute("aria-hidden","true");
head.appendChild(chev);head.appendChild(t);head.appendChild(sum);
var body=document.createElement("div");body.className="chat-tool-body";
row.appendChild(head);row.appendChild(body);
row._title=t;row._sum=sum;row._body=body;
return row;
}
/* 后画进对话区的控件统一委托：工具标题展开、查看报文，不为每个按钮再绑。 */
document.addEventListener("click",function(ev){
var t=ev.target;
if(!t||!t.closest)return;
var pkt=t.closest(".chat-tool-packet-btn");
if(pkt){
ev.preventDefault();
var body=pkt.closest(".chat-tool-body");
var raw=body?body.querySelector(":scope > .chat-tool-raw"):null;
if(!raw)return;
var open=!!raw.hidden;
raw.hidden=!open;
pkt.setAttribute("aria-expanded",open?"true":"false");
pkt.classList.toggle("is-open",open);
return;
}
var head=t.closest(".chat-tool-head");
if(!head)return;
var row=head.closest(".chat-tool-row");
if(!row)return;
var open=row.classList.toggle("is-open");
head.setAttribute("aria-expanded",open?"true":"false");
});
function addChatToolLayer(body, cap, kind){
var layer=document.createElement("div");
layer.className="chat-tool-layer"+(kind?" chat-tool-layer--"+kind:"");
if(cap){
var c=document.createElement("div");c.className="chat-tool-pane-cap";c.textContent=cap;
layer.appendChild(c);
}
var pane=document.createElement("div");
pane.className="chat-tool-pane"+(kind?" chat-tool-pane--"+kind:"");
layer.appendChild(pane);
body.appendChild(layer);
return pane;
}
function addChatToolText(pane, text){
var pre=document.createElement("pre");pre.className="chat-run-pre";
var code=document.createElement("code");code.textContent=text||"";
pre.appendChild(code);pane.appendChild(pre);
return code;
}
function addChatToolPane(body, cap, text, kind){
return addChatToolText(addChatToolLayer(body, cap, kind), text);
}
var chatToolViews=[];
function registerChatToolView(view){
if(view&&typeof view.match==="function")chatToolViews.push(view);
return view;
}
function chatToolViewFor(script, args){
for(var i=chatToolViews.length-1;i>=0;i--){
if(chatToolViews[i].match(script, args))return chatToolViews[i];
}
return chatToolViewDefault;
}
function chatToolHead(o){
var tp=buildToolTitleParts(o.script, o.args||{}, true);
var st=String(o.stepTitle||"").trim();
return {title:st||tp.main||toolZh(o.script), summary:String(tp.fname||"").trim()};
}
function chatToolSetSummary(row, text){
if(!row||!row._sum)return;
var shown=String(text||"");
if(!shown)return;
row._sum.textContent=shown;
}
function chatToolParsePreview(ev){
try{
var j=typeof ev.preview==="string"?JSON.parse(ev.preview||""):ev.preview;
return j&&typeof j==="object"?j:null;
}catch(e){return null;}
}
function chatToolPrettyJson(value){
if(value==null||value==="")return "";
if(typeof value==="object"){
try{return JSON.stringify(value,null,2);}catch(e){return "";}
}
var raw=String(value);
try{
var j=JSON.parse(raw);
if(j&&typeof j==="object")return JSON.stringify(j,null,2);
}catch(e){}
return raw;
}
function chatToolPayloadUseful(text){
var s=String(text||"").trim();
if(!s||s==="{}"||s==="null")return false;
try{
var j=JSON.parse(s);
if(j&&typeof j==="object"&&!Array.isArray(j)){
if(!Object.keys(j).length)return false;
var d=j.data;
if(d&&typeof d==="object"&&!Array.isArray(d)&&!Object.keys(d).length&&j.error==null)return false;
}
}catch(e){}
return true;
}
function chatToolFailPreview(error){
return JSON.stringify({ok:false,error:String(error||"执行失败")},null,2);
}
/* tool_end 的失败详情在 preview JSON 里，帧上常常没有顶层 error。
   自定义明细只认失败态，文案统一为红色「<执行失败>」，细节留在「查看报文」。 */
function chatToolIsFailed(ev){
if(!ev||ev.user_confirm_required||ev.approval_required)return false;
if(typeof chatToolWasCanceled==="function"&&chatToolWasCanceled(ev))return false;
if(ev.ok===false||ev.ok===0||ev.ok==="false")return true;
var j=chatToolParsePreview(ev);
if(j&&(j.ok===false||j.ok===0||j.ok==="false"))return true;
var d=j&&j.data;
return !!(d&&typeof d==="object"&&(d.ok===false||d.ok===0));
}
function chatToolPaintFailText(el){
if(!el)return;
el.classList.add("chat-tool-fail");
if(el.tagName==="CODE"||el.tagName==="PRE"||el.classList.contains("b")||el.classList.contains("chat-tool-md")){
el.textContent="<执行失败>";
return;
}
el.textContent="";
var line=document.createElement("div");
line.className="chat-tool-fail";
line.textContent="<执行失败>";
el.appendChild(line);
}
function chatToolClearFailMark(el){
if(!el)return;
el.classList.remove("chat-tool-fail");
}
function chatToolFrameOk(ev){
if(!ev)return true;
if(ev.user_confirm_required||ev.approval_required)return true;
if(ev.ok===false||ev.ok===0||ev.ok==="false")return false;
return true;
}
function chatToolEnvelopePayload(ok, data, error){
if(ok)return {ok:true,data:data};
var payload={ok:false,error:String(error||"执行失败")};
if(data!==undefined)payload.data=data;
return payload;
}
/* 报文「响应」= 工具输出信封（与回灌模型同形）：顶层 ok + data/error。
   preview 已是信封则原样展示；旧帧只有 `{data:工具结果}` 时按帧 ok 补齐，不改内层字段。 */
function chatToolResponseText(o, ev){
var ok=chatToolFrameOk(ev);
var j=chatToolParsePreview(ev);
if(j&&Object.prototype.hasOwnProperty.call(j,"ok")){
var fromPreview=chatToolPrettyJson(j);
if(chatToolPayloadUseful(fromPreview))return fromPreview;
}
if(j&&Object.prototype.hasOwnProperty.call(j,"data")){
var packed=chatToolPrettyJson(chatToolEnvelopePayload(ok, j.data, (ev&&ev.error)||j.error));
if(chatToolPayloadUseful(packed))return packed;
}
if(ev&&!ok&&ev.error&&!ev.user_confirm_required&&!ev.approval_required){
return chatToolFailPreview(ev.error);
}
var t=o&&o.resPb?String(o.resPb.textContent||""):"";
if(chatToolPayloadUseful(t)){
try{
var rj=JSON.parse(t);
if(rj&&typeof rj==="object"){
if(Object.prototype.hasOwnProperty.call(rj,"ok"))return chatToolPrettyJson(rj);
if(Object.prototype.hasOwnProperty.call(rj,"data"))
return chatToolPrettyJson(chatToolEnvelopePayload(ok, rj.data, (ev&&ev.error)||rj.error));
return chatToolPrettyJson(chatToolEnvelopePayload(ok, rj, ev&&ev.error));
}
}catch(e){}
var fromRes=chatToolPrettyJson(t);
if(fromRes.trim())return fromRes;
}
return "（无结果）";
}
var chatToolViewDefault={
match:function(){return true;},
title:function(o){return chatToolExpandPaths(chatToolHead(o).title, o.args);},
summary:function(o){return chatToolExpandPaths(chatToolHead(o).summary, o.args);},
mount:function(row, o){
addChatToolText(addChatToolLayer(row._body,"请求","req"), JSON.stringify(o.args||{},null,2));
o.chatToolRes=addChatToolText(addChatToolLayer(row._body,"响应","res"), "（等待结果…）");
if(isStreamOutputToolScript(o.script)&&!isRunCommandToolScript(o.script)){
o.chatRunOutPre=o.chatToolRes;
if(!o.liveOutPre)o.liveOutPre=o.chatToolRes;
}
},
fill:function(row, o, ev){
if(o.chatToolRes)o.chatToolRes.textContent=chatToolResponseText(o, ev);
}
};
registerChatToolView({
match:function(script){return isEditFamilyTool(script);},
title:function(o){return editFamilyTitle(o.script, o.args);},
summary:function(o){return chatEditPath(o.script, o.args)||"（未指定文件）";},
mount:function(row, o){chatToolViewDefault.mount(row, o);},
fill:function(row, o, ev){
chatToolViewDefault.fill(row, o, ev);
var path=chatEditPath(o.script, o.args);
if(!path){
var j=chatToolParsePreview(ev);
var d=j&&j.data||{};
path=String(d.path||d.dest_path||d.source_path||d.file_name||"").trim();
}
chatToolSetSummary(row, path);
}
});
registerChatToolView({
match:function(script){
var n=chatToolName(script);
return n==="run_command"||n==="python_inline";
},
title:function(){return "执行命令";},
summary:function(o){
var src=commandSummaryLine(chatExecSource(o));
if(src)return src;
return chatToolName(o&&o.script)==="python_inline"?"（无代码）":"（空命令）";
},
mount:function(row, o){
var src=chatExecSource(o);
var lang=chatExecLang(o.script);
var code=addChatToolText(addChatToolLayer(row._body,"命令","cmd"), "");
try{code.className=hljsCodeClass(lang);code.innerHTML=highlightCode(src,lang);}catch(e){code.textContent=src;}
var out=addChatToolText(addChatToolLayer(row._body,"执行结果","out"), "（等待输出…）");
o.chatRunOutPre=out;
if(!o.liveOutPre)o.liveOutPre=out;
},
fill:function(row, o, ev){
if(!o.chatRunOutPre||ev.user_confirm_required)return;
if(chatToolIsFailed(ev)){
var curFail=String(o.chatRunOutPre.textContent||"");
if(!curFail.trim()||curFail==="（等待输出…）")chatToolPaintFailText(o.chatRunOutPre);
return;
}
chatToolClearFailMark(o.chatRunOutPre);
var cur=String(o.chatRunOutPre.textContent||"");
if(cur.trim()&&cur!=="（等待输出…）")return;
o.chatRunOutPre.textContent=ev.ok?"（无输出）":"（无结果）";
}
});
var chatToolViewPreview=registerChatToolView({
match:function(script, args){return isPreviewEditTool(script, args);},
title:function(){return "预览修改";},
summary:function(o){return chatEditPath(o.script, o.args)||"（未指定文件）";},
mount:function(row, o){
o.chatToolDiffPane=addChatToolLayer(row._body,"","diff");
},
fill:function(row, o, ev){
var path=chatEditPath(o.script, o.args);
var parsed=chatToolParsePreview(ev);
if(!path&&parsed&&parsed.data){
var d0=parsed.data;
path=String(d0.path||d0.dest_path||d0.source_path||d0.file_name||"").trim();
}
if(path)chatToolSetSummary(row, path);
if(chatToolIsFailed(ev)){chatToolPaintFailText(o.chatToolDiffPane);return;}
chatToolClearFailMark(o.chatToolDiffPane);
var dt=chatPaintDiffPane(o.chatToolDiffPane, o, ev);
paintPreviewSummary(row, path, dt);
}
});
registerChatToolView({
match:function(script, args){
return chatToolName(script)==="file_undo"&&String(argGet(args,"action")||"").toLowerCase()==="diff";
},
title:function(){return "版本比较";},
summary:function(o){
return chatVersionCompareLabel(chatVersionComparePath(o), chatVersionCompareStamp(o))||"（未指定文件）";
},
mount:function(row, o){
o.chatToolDiffPane=addChatToolLayer(row._body,"","diff");
},
fill:function(row, o, ev){
var label=chatVersionCompareLabel(chatVersionComparePath(o, ev), chatVersionCompareStamp(o, ev));
if(label)chatToolSetSummary(row, label);
if(chatToolIsFailed(ev)){chatToolPaintFailText(o.chatToolDiffPane);return;}
chatToolClearFailMark(o.chatToolDiffPane);
var dt=chatPaintDiffPane(o.chatToolDiffPane, o, ev);
if(label||dt)paintPreviewSummary(row, label, dt);
}
});
function chatReadFileRangeLabel(args, data){
var ls=argGet(args,"line_start"), le=argGet(args,"line_end");
var sc=argGet(args,"start_column"), ec=argGet(args,"end_column");
if((ls==null||le==null)&&data&&typeof data==="object"){
if(ls==null&&data.line_start!=null)ls=data.line_start;
if(le==null&&data.line_end!=null)le=data.line_end;
}
if(ls==null||le==null)return "";
if(sc!=null&&ec!=null)return " L"+ls+":"+sc+"-"+le+":"+ec;
return " L"+ls+"-"+le;
}
registerChatToolView({
match:function(script){return chatToolName(script)==="read_file";},
title:function(o){return chatToolExpandPaths(chatToolHead(o).title, o.args);},
summary:function(o){return chatToolExpandPaths(chatToolHead(o).summary, o.args);},
mount:function(row, o){
o.chatToolFile=addChatToolText(addChatToolLayer(row._body,"","file"), "（等待内容…）");
},
fill:function(row, o, ev){
var pane=o.chatToolFile;
if(!pane)return;
var j=chatToolParsePreview(ev);
var d=j&&j.data&&typeof j.data==="object"?j.data:null;
var path=String(argGet(o&&o.args,"path")||"").trim();
if(d&&!path)path=String(d.path||"").trim();
var sum=(path||"（未指定 path）")+chatReadFileRangeLabel(o&&o.args, d);
chatToolSetSummary(row, sum);
if(chatToolIsFailed(ev)){chatToolPaintFailText(pane);return;}
chatToolClearFailMark(pane);
var text=chatReadFileContent(ev);
if(text==null){pane.textContent=ev.ok?"（无内容）":"（无结果）";return;}
pane.textContent=text.length?text:"（空文件）";
}
});
registerChatToolView({
match:function(script){return chatToolName(script)==="read_image";},
title:function(){return "看图";},
summary:function(o){return chatImagePath(o)||"（未指定 path）";},
mount:function(row, o){
o.chatToolShot=addChatToolLayer(row._body,"","shot");
o.chatToolShot.textContent="（等待图片…）";
},
fill:function(row, o, ev){
var path=chatImagePath(o, ev);
chatToolSetSummary(row, path||"（未指定 path）");
var pane=o.chatToolShot;
if(!pane)return;
if(chatToolIsFailed(ev)){chatToolPaintFailText(pane);return;}
chatToolClearFailMark(pane);
pane.textContent="";
var images=ev&&ev.images;
var shown=false;
if(Array.isArray(images)){
for(var i=0;i<images.length;i++){
var im=images[i];
if(!im||!im.data_base64)continue;
var img=document.createElement("img");
img.className="chat-tool-shot";
img.alt=path||"图片";
var mime=String(im.mime||"image/png");
if(mime.indexOf("image/")!==0)mime="image/png";
img.src="data:"+mime+";base64,"+String(im.data_base64);
bindToolShotPreview(img);
pane.appendChild(img);
shown=true;
}
}
if(!shown){
var miss=document.createElement("div");
miss.className="chat-tool-shot-miss";
miss.textContent="（没有可显示的图片）";
pane.appendChild(miss);
}
var sizeText=chatImageSize(o, ev);
if(sizeText||path){
var meta=document.createElement("div");
meta.className="chat-tool-shot-meta";
if(sizeText){
var size=document.createElement("div");
size.className="chat-tool-shot-path";
size.textContent="尺寸: "+sizeText;
meta.appendChild(size);
}
if(path){
var cap=document.createElement("div");
cap.className="chat-tool-shot-path";
cap.textContent="地址: "+path;
meta.appendChild(cap);
}
pane.appendChild(meta);
}
}
});
function chatGlobSummary(args, data){
var root=String((data&&data.root)||argGet(args,"path")||".").trim()||".";
var glob=String(argGet(args,"glob_pattern")||"*");
var rec=argGet(args,"recursive");
var text=root+" · "+(glob||"*");
if(rec!==false)text+=" · 递归";
return text;
}
function chatJoinUnder(root, rel){
root=String(root||"").replace(/[\\/]+$/,"");
rel=String(rel||"").trim();
if(!rel)return root;
if(/^[A-Za-z]:[\\/]/.test(rel)||rel.charAt(0)==="/"||rel.charAt(0)==="\\")return rel;
if(!root)return rel;
var sep=root.indexOf("\\")>=0?"\\":"/";
rel=sep==="\\"?rel.replace(/\//g,"\\"):rel.replace(/\\/g,"/");
return root+sep+rel;
}
function chatGlobLines(ev, args){
var j=chatToolParsePreview(ev);
var d=j&&j.data&&typeof j.data==="object"?j.data:{};
var root=String(d.root||argGet(args,"path")||"");
var entries=Array.isArray(d.entries)?d.entries:[];
var lines=[];
for(var i=0;i<entries.length;i++){
var line=chatJoinUnder(root, entries[i]);
if(line)lines.push(line);
}
if(d.truncated)lines.push("（还有更多，已到条数上限）");
return lines;
}
registerChatToolView({
match:function(script){return chatToolName(script)==="delete_file";},
title:function(o){return chatToolHead(o).title;},
summary:function(o){return String(argGet(o&&o.args,"path")||"").trim()||"（未指定 path）";},
mount:function(row, o){
o.chatToolDelete=addChatToolText(addChatToolLayer(row._body,"",""), "（等待结果…）");
},
fill:function(row, o, ev){
var path=String(argGet(o&&o.args,"path")||"").trim();
var dir="";
var j=chatToolParsePreview(ev);
var d=j&&j.data&&typeof j.data==="object"?j.data:null;
if(d){
if(!path)path=String(d.path||"").trim();
dir=String(d.recycle_dir||d.moved_to||"").trim();
}
if(path)chatToolSetSummary(row, path);
if(chatToolIsFailed(ev)){chatToolPaintFailText(o.chatToolDelete);return;}
chatToolClearFailMark(o.chatToolDelete);
var text;
if(path&&dir)text=path+" 文件移入 "+dir+" 安全回收目录, 可在此找回原文件";
else if(path)text=path+" 文件移入安全回收目录, 可在此找回原文件";
else text="（无结果）";
if(o.chatToolDelete)o.chatToolDelete.textContent=text;
}
});
registerChatToolView({
match:function(script){return chatToolName(script)==="glob_files";},
title:function(o){
var et=String(argGet(o&&o.args,"entry_type")||"").toLowerCase();
var scope=et==="dir"?"仅目录":et==="all"?"全部":"文件";
return "列出路径（"+scope+"）";
},
summary:function(o){return chatGlobSummary(o&&o.args);},
mount:function(row, o){
o.chatToolPaths=addChatToolText(addChatToolLayer(row._body,"",""), "（等待结果…）");
},
fill:function(row, o, ev){
var parsed=chatToolParsePreview(ev);
chatToolSetSummary(row, chatGlobSummary(o&&o.args, parsed&&parsed.data));
var pane=o.chatToolPaths;
if(!pane)return;
if(chatToolIsFailed(ev)){chatToolPaintFailText(pane);return;}
chatToolClearFailMark(pane);
var lines=chatGlobLines(ev, o&&o.args);
pane.textContent=lines.length?lines.join("\n"):"（没有匹配的路径）";
}
});

/* ── Visual Operator 的详情区 ─────────────────────────────────────────────────────
   `看屏` 与带 `shot=true` 的手部动作，回执里带的是图片附件（`tool_end.images`），
   报文里只有尺寸与窗口信息 —— 不把图铺进详情，用户就只能看到一串坐标。
   与 `read_image` 完全同构：自定义视图里只有图片与尺寸/来源两行，
   请求与响应收进「查看报文」按钮后面（由 `attachChatToolPacket` 统一装箱）。
   这里绝不能自己挂 `请求` / `响应` 两层：一旦出现 `.chat-tool-layer--req/res`，
   `chatToolShowsRaw` 就为真，装箱逻辑会直接跳过，JSON 便会挤在图片上面。 */
function chatDesktopData(ev){
var j=chatToolParsePreview(ev);
if(!j||typeof j!=="object")return null;
if(j.data&&typeof j.data==="object")return j.data;
return j;}
function chatDesktopWantsShot(o){
if(chatToolName(o&&o.script)==="desktop_eye")return true;
var v=argGet(o&&o.args,"shot");
return v===true||v===1||v==="true"||v==="1";}
function chatDesktopFillShot(pane,ev){
if(!pane)return;
pane.textContent="";
if(chatToolIsFailed(ev)){chatToolPaintFailText(pane);return;}
chatToolClearFailMark(pane);
var images=ev&&ev.images,shown=false;
var data=chatDesktopData(ev)||{};
var order=Array.isArray(data.attachment_order)?data.attachment_order:[];
if(Array.isArray(images)){
for(var i=0;i<images.length;i++){
var im=images[i];
if(!im||!im.data_base64)continue;
var role=order[i]==="raw"?"原图":(order[i]==="annotated"?"标注图":"");
var item=document.createElement("div");
item.className="chat-tool-shot-item";
var img=document.createElement("img");
img.className="chat-tool-shot";
img.alt=role||"截图";
var mime=String(im.mime||"image/png");
if(mime.indexOf("image/")!==0)mime="image/png";
img.src="data:"+mime+";base64,"+String(im.data_base64);
bindToolShotPreview(img);
if(role){
var cap=document.createElement("div");
cap.className="chat-tool-shot-label";
cap.textContent=role;
item.appendChild(cap);
}
item.appendChild(img);
pane.appendChild(item);
shown=true;
}
}
if(!shown){
var miss=document.createElement("div");
miss.className="chat-tool-shot-miss";
miss.textContent="（没有可显示的图片）";
pane.appendChild(miss);
return;
}
var lines=chatDesktopShotMeta(ev);
if(!lines.length)return;
var meta=document.createElement("div");
meta.className="chat-tool-shot-meta";
for(var k=0;k<lines.length;k++){
var line=document.createElement("div");
line.className="chat-tool-shot-path";
line.textContent=lines[k];
meta.appendChild(line);
}
pane.appendChild(meta);
}
/* 图片下面两行，字段顺序照 `read_image`：先尺寸，再来源。 */
function chatDesktopShotMeta(ev){
var d=chatDesktopData(ev)||{};
var lines=[];
var im=d.image&&typeof d.image==="object"?d.image:null;
if(im&&im.width>0&&im.height>0){
lines.push("尺寸: "+Math.round(im.width)+" × "+Math.round(im.height)+" px");
if(im.sent_width>0&&im.sent_height>0&&
(im.sent_width!==im.width||im.sent_height!==im.height))
lines.push("发送: "+im.sent_width+" × "+im.sent_height+" px（缩放 "+
(Math.round(Number(im.scale||1)*100)/100)+"x）");
}
var win=d.window&&typeof d.window==="object"?d.window:null;
var cap=d.capture&&typeof d.capture==="object"?d.capture:null;
if(win&&win.hwnd!=null)lines.push("窗口: "+(win.title||"（无标题）")+" (hwnd="+win.hwnd+")");
else if(cap&&cap.width>0)lines.push("屏幕: ("+cap.x+", "+cap.y+", "+cap.width+"×"+cap.height+")");
return lines;
}
function chatDesktopMount(row,o){
if(!chatDesktopWantsShot(o))return;
/* 不挂请求/响应层：报文由 attachChatToolPacket 收进「查看报文」。 */
o.chatToolShot=addChatToolLayer(row._body,"","shot");
}
function chatDesktopFill(row,o,ev){
var summary=desktopToolSummary(o.script,o.args,chatDesktopData(ev));
if(summary)chatToolSetSummary(row,summary);
chatDesktopFillShot(o.chatToolShot,ev);
}
registerChatToolView({
match:function(script){return chatToolName(script)==="desktop_eye";},
summary:function(o){return desktopToolSummary(o.script,o.args,null);},
mount:function(row,o){chatDesktopMount(row,o);},
fill:function(row,o,ev){chatDesktopFill(row,o,ev);}
});
registerChatToolView({
match:function(script){return chatToolName(script)==="desktop_mouse";},
summary:function(o){return desktopToolSummary(o.script,o.args,null);},
mount:function(row,o){chatDesktopMount(row,o);},
fill:function(row,o,ev){chatDesktopFill(row,o,ev);}
});
registerChatToolView({
match:function(script){return chatToolName(script)==="desktop_keyboard";},
summary:function(o){return desktopToolSummary(o.script,o.args,null);},
mount:function(row,o){chatDesktopMount(row,o);},
fill:function(row,o,ev){chatDesktopFill(row,o,ev);}
});
/* 等待类工具没有图片区，但摘要必须能从参数描述刷新成回执描述：
   `desktop_wait` 的窗口标题来自回执，`task_sleep` 仍是请求时长。
   不登记这一条的话，`fill` 走默认视图，摘要停在停止那一刻的倒计时值。 */
registerChatToolView({
match:function(script){return desktopToolKind(script)==="wait"||desktopToolKind(script)==="sleep";},
summary:function(o){return desktopToolSummary(o.script,o.args,null);},
fill:function(row,o,ev){
var summary=desktopToolSummary(o.script,o.args,chatDesktopData(ev));
if(summary)chatToolSetSummary(row,summary);}
});
function refreshChatToolSummaries(){
/* 每个会话有独立消息宿主；非激活宿主不在 document 里。
   只查 document 会让未激活标签的摘要停留在空串或旧默认视图。 */
var roots=[document];
if(typeof conversationTabs!=="undefined"){
for(var ti=0;ti<conversationTabs.length;ti++){
var host=conversationTabs[ti]&&conversationTabs[ti].msgsHost;
if(host)roots.push(host);
}
}
var seen=[];
for(var ri=0;ri<roots.length;ri++){
var root=roots[ri];
if(!root||seen.indexOf(root)>=0)continue;
seen.push(root);
var rows=root.querySelectorAll(".chat-tool-row");
for(var i=0;i<rows.length;i++){
var row=rows[i];
var data=row._toolData;
if(!data||!row._sum)continue;
var view=chatToolViewFor(data.script,data.args);
if(!view||typeof view.summary!=="function")continue;
var text=String(view.summary({script:data.script,args:data.args})||"").trim();
if(text)row._sum.textContent=text;
}
}
}


function chatFileCardSize(n){
if(typeof formatFileSize==="function")return formatFileSize(n);
var v=Number(n);
return (v>=1024?(Math.round(v/1024*10)/10+" KB"):(Math.max(0,v)+" B"));
}
function chatFileCardKindLabel(kind){
var labels={image:"图片",video:"视频",audio:"音频",table:"表格",archive:"压缩包",pdf:"PDF",file:"文件"};
return labels[String(kind||"file")]||"文件";
}
function chatFileCardElement(file){
var path=String(file&&file.path||"").trim();
var name=String(file&&(file.title||file.name)||"").trim()||baseNameOnly(path);
var card=document.createElement("div");
card.className="chat-file-card";
card.setAttribute("role","button");
card.tabIndex=0;
card.title=path;
card.setAttribute("data-file-path",path);
var icon=document.createElement("span");
icon.className="chat-file-card-icon";
var kind=String(file&&file.kind||"file");
if(kind==="image"&&path){
var img=document.createElement("img");
img.alt="";
img.loading="lazy";
img.src="/api/media?path="+encodeURIComponent(path);
img.onerror=function(){icon.innerHTML="";if(window.aiAgentFileIcons)icon.appendChild(window.aiAgentFileIcons.el(path));};
icon.appendChild(img);
}else if(window.aiAgentFileIcons){
icon.appendChild(window.aiAgentFileIcons.el(path));
}else{
icon.textContent="📄";
}
var body=document.createElement("span");
body.className="chat-file-card-body";
var title=document.createElement("span");
title.className="chat-file-card-name";
title.textContent=name;
var meta=document.createElement("span");
meta.className="chat-file-card-meta";
var bits=[chatFileCardKindLabel(kind)];
if(file&&file.size!=null)bits.push(chatFileCardSize(file.size));
bits.push("在侧边栏预览");
meta.textContent=bits.join(" · ");
body.appendChild(title);
body.appendChild(meta);
var action=document.createElement("span");
action.className="chat-file-card-action";
action.textContent="预览";
card.appendChild(icon);
card.appendChild(body);
card.appendChild(action);
return card;
}
var chatToolViewPresent=registerChatToolView({
match:function(script){return chatToolName(script)==="present";},
title:function(){return "文件";},
summary:function(o){return "";},
mount:function(row, o){
row.classList.add("chat-file-card-row");
var host=document.createElement("div");
host.className="chat-file-card-stack";
row._body.appendChild(host);
o.chatFileCardHost=host;
},
fill:function(row, o, ev){
var host=o.chatFileCardHost;
if(!host)return;
host.textContent="";
var parsed=chatToolParsePreview(ev);
var data=parsed&&parsed.data&&typeof parsed.data==="object"?parsed.data:parsed;
var files=data&&Array.isArray(data.files)?data.files:[];
if(!ev||!ev.ok||!files.length){
var requested="";
try{
var rawArgs=Array.isArray(o.args&&o.args.files)?o.args.files:[];
if(rawArgs.length)requested=String(rawArgs[0]&&rawArgs[0].path||"");
}catch(_e){}
var fail=document.createElement("div");
fail.className="chat-file-card chat-file-card-error-card";
var failIcon=document.createElement("span");
failIcon.className="chat-file-card-icon chat-file-card-error-icon";
failIcon.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.3 3.9 2.4 17.4A1.8 1.8 0 0 0 4 20h16a1.8 1.8 0 0 0 1.6-2.6L13.7 3.9a1.8 1.8 0 0 0-3.4 0Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>';
var failBody=document.createElement("span");
failBody.className="chat-file-card-body";
var failName=document.createElement("span");
failName.className="chat-file-card-name chat-file-card-error-name";
failName.textContent="无法展示文件";
var failMeta=document.createElement("span");
failMeta.className="chat-file-card-meta";
failMeta.textContent=requested||"文件路径无效";
var failText=document.createElement("span");
failText.className="chat-file-card-error-text";
failText.textContent=String((parsed&&parsed.error)||"文件卡片无法展示");
failBody.appendChild(failName);
failBody.appendChild(failMeta);
failBody.appendChild(failText);
fail.appendChild(failIcon);
fail.appendChild(failBody);
host.appendChild(fail);
row.classList.add("is-open");
return;
}
for(var i=0;i<files.length;i++)host.appendChild(chatFileCardElement(files[i]||{}));
row.classList.add("is-open");
}
});

window.aiAgentChatTools={register:registerChatToolView,refresh:refreshChatToolSummaries};
function appendChatToolRow(row, opts){
if(!msgs||!row)return;
opts=opts||{};
if(opts.beforeStream&&streamAssistantEl&&streamAssistantEl.parentNode)streamAssistantEl.before(row);
else if(streamAssistantEl&&streamAssistantEl.parentNode){streamAssistantEl.after(row);streamAssistantEl=null;streamAssistantText="";}
else msgs.appendChild(row);
scrollMsgsToBottom();
}
function mountChatToolItem(o){
if(!o||o.chatToolRow)return;
var _always=chatToolName(o.script)==="present";
if(!_always&&!showToolItems())return;
var view=chatToolViewFor(o.script, o.args);
o.chatToolView=view;
var title=view.title?view.title(o):chatToolViewDefault.title(o);
var summary=view.summary?view.summary(o):"";
var row=makeChatToolRow(title, summary);
row.classList.add("is-running");
chatToolSyncStatusTitle(row);
o.chatToolRow=row;
row._toolData={script:o.script,args:o.args};
if(view.mount)view.mount(row, o);
/* 等待类工具：标题后的秒数逐秒减，与步骤卡同一份倒计时。
   回放历史时不重启倒计时 —— 那是已经发生过的等待，重新从总数往下数会像还在等。 */
if(!o.replay)desktopStartWaitTicker(o.tid,o.script,o.args,function(left,total,elapsed){row._sum.textContent=desktopWaitTickText(o.script,o.args,left,elapsed);});
attachChatToolPacket(row, o);
appendChatToolRow(row);
}
function paintChatThink(){
if(!showToolItems()||!lastLlm||lastLlm.chatThinkSealed)return;
var full=String(lastLlm.reasoningText||"");
if(!full)return;
if(!lastLlm.chatThinkStartedAt)lastLlm.chatThinkStartedAt=Date.now();
/* 标题后的摘要两次绘制至少隔 300ms。不够就丢掉这一次，不延期再画。 */
var now=Date.now();
var skipSum=!!(lastLlm.chatThinkPaintAt&&now-lastLlm.chatThinkPaintAt<300);
if(!lastLlm.chatThink)skipSum=false;
if(!skipSum)lastLlm.chatThinkPaintAt=now;
if(!lastLlm.chatThink){
var row=makeChatToolRow("思考","");
row.classList.add("is-running");
chatToolSyncStatusTitle(row);
var code=addChatToolPane(row._body,"","", "think");
lastLlm.chatThink=row;
lastLlm.chatThinkFull=code;
appendChatToolRow(row,{beforeStream:true});
}
if(!skipSum){
var tail=chatThinkTail(full);
var sum=lastLlm.chatThink._sum;
sum.textContent=tail;
}
if(lastLlm.chatThinkFull){
lastLlm.chatThinkFull.textContent=full;
var pane=lastLlm.chatThinkFull.closest?lastLlm.chatThinkFull.closest(".chat-tool-pane"):null;
if(pane&&lastLlm.chatThink.classList.contains("is-open"))pane.scrollTop=pane.scrollHeight;
}
}
function chatToolWasCanceled(ev){
if(!ev)return false;
if(ev.canceled===true||ev.canceled==="true")return true;
var j=chatToolParsePreview(ev);
var d=j&&j.data&&typeof j.data==="object"?j.data:j;
return !!(d&&d.canceled===true);
}
function chatToolSyncStatusTitle(row){
if(!row||!row._title)return;
var label="已完成";
if(row.classList.contains("is-canceled"))label="已取消";
else if(row.classList.contains("is-bad"))label="失败";
else if(row.classList.contains("is-running"))label="进行中";
row._title.title=label;
}
function chatToolSetResultText(row, text){
if(!row)return;
var code=row.querySelector(".chat-tool-pane--res code");
if(code)code.textContent=String(text||"");
}
function chatToolSetRowStatus(row, status){
if(!row)return;
row.classList.remove("is-running");
row.classList.remove("is-bad");
row.classList.remove("is-canceled");
if(status==="running")row.classList.add("is-running");
else if(status==="bad")row.classList.add("is-bad");
else if(status==="canceled")row.classList.add("is-canceled");
chatToolSyncStatusTitle(row);
}
function chatToolShowsRaw(row){
return !!(row&&row._body&&row._body.querySelector(".chat-tool-layer--req")&&row._body.querySelector(".chat-tool-layer--res"));
}
function attachChatToolPacket(row, o){
if(!row||!row._body||chatToolShowsRaw(row)||row.querySelector(".chat-tool-custom"))return;
var custom=document.createElement("div");
custom.className="chat-tool-custom";
var view=document.createElement("div");
view.className="chat-tool-custom-view";
while(row._body.firstChild)view.appendChild(row._body.firstChild);
var btn=document.createElement("button");
btn.type="button";
btn.className="chat-tool-packet-btn";
btn.setAttribute("aria-expanded","false");
var chev=document.createElement("span");
chev.className="chat-tool-chev";
chev.setAttribute("aria-hidden","true");
var label=document.createElement("span");
label.className="chat-tool-packet-label";
label.textContent="查看报文";
btn.appendChild(chev);
btn.appendChild(label);
var bar=document.createElement("div");
bar.className="chat-tool-packet";
bar.appendChild(btn);
custom.appendChild(view);
custom.appendChild(bar);
var raw=document.createElement("div");
raw.className="chat-tool-raw";
raw.hidden=true;
function pane(cap, kind, text){
var host=document.createElement("div");
var el=addChatToolLayer(host, cap, kind);
var pre=document.createElement("pre");
var code=document.createElement("code");
code.textContent=text;
pre.appendChild(code);
el.appendChild(pre);
raw.appendChild(host.firstChild);
return code;
}
pane("请求", "req", JSON.stringify((o&&o.args)||{},null,2));
var res=pane("响应", "res", "（等待结果…）");
row._body.appendChild(custom);
row._body.appendChild(raw);
if(o)o.chatToolPacketRes=res;
}
function fillChatToolPacket(o, ev){
if(!o||!o.chatToolPacketRes)return;
o.chatToolPacketRes.textContent=chatToolResponseText(o, ev);
}
function fillChatToolResult(o, ev){
if(!o||!o.chatToolRow)return;
var view=o.chatToolView||chatToolViewDefault;
if(view.fill)view.fill(o.chatToolRow, o, ev);
fillChatToolPacket(o, ev);
o.chatToolRow.classList.remove("is-running");
o.chatToolRow.classList.remove("is-bad");
o.chatToolRow.classList.remove("is-canceled");
if(chatToolWasCanceled(ev))o.chatToolRow.classList.add("is-canceled");
/* 等人作答还没结束，标题继续跑马灯。 */
else if(ev.user_confirm_required||ev.approval_required)o.chatToolRow.classList.add("is-running");
else if(!ev.ok)o.chatToolRow.classList.add("is-bad");
chatToolSyncStatusTitle(o.chatToolRow);
}
