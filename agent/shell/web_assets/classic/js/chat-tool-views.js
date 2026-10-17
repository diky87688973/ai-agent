function chatToolName(script){
var s=String(script||"").toLowerCase();
var parts=s.match(/[a-z0-9_]+/g);
return parts&&parts.length?parts[parts.length-1]:s;
}
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
return (dr!==false&&dr!==0)?"修改预览":"提交修改";
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
var label=chatThinkElapsedLabel(Date.now()-lastLlm.chatThinkStartedAt);
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
function chatPaintDiffPane(pane, o, ev){
if(!pane)return "";
pane.innerHTML="";
var parsed=chatToolParsePreview(ev);
var dt=diffTextFromToolData(parsed&&parsed.data);
var html=dt&&dt.trim()?renderUnifiedDiffBodyAsCardsHtml(dt):"";
if(html)pane.innerHTML=html;
else if(dt&&dt.trim()){
var box=document.createElement("div");
box.className="diff-unified diff-surface-adaptive";
renderUnifiedDiffRows(box, dt.split(/\r?\n/));
pane.appendChild(box);
}else addChatToolText(pane, chatToolResponseText(o, ev));
return dt||"";
}
function chatSkillName(o){
return String(argGet(o&&o.args,"name")||"").trim();
}
function chatSkillContent(ev){
var j=chatToolParsePreview(ev);
if(!j)return null;
var d=j.data&&typeof j.data==="object"?j.data:j;
return typeof d.content==="string"?d.content:null;
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
/* 工具标题是后画进对话区的。点击从标题冒泡上来，这里收一次再展开，不为每一行再绑。 */
document.addEventListener("click",function(ev){
var t=ev.target;
if(!t||!t.closest)return;
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
function chatToolResponseText(o, ev){
if(!ev.ok&&ev.error&&!ev.user_confirm_required&&!ev.approval_required)return String(ev.error);
var t=o.resPb?String(o.resPb.textContent||""):"";
if(t.trim())return t;
if(ev.preview)return String(ev.preview);
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
var cur=String(o.chatRunOutPre.textContent||"");
if(cur.trim()&&cur!=="（等待输出…）")return;
var err=!ev.ok&&ev.error?String(ev.error):"";
o.chatRunOutPre.textContent=err||(ev.ok?"（无输出）":"（无结果）");
}
});
var chatToolViewPreview=registerChatToolView({
match:function(script, args){return isPreviewEditTool(script, args);},
title:function(){return "修改预览";},
summary:function(o){return chatEditPath(o.script, o.args)||"（未指定文件）";},
mount:function(row, o){
o.chatToolDiffPane=addChatToolLayer(row._body,"","diff");
},
fill:function(row, o, ev){
var dt=chatPaintDiffPane(o.chatToolDiffPane, o, ev);
var parsed=chatToolParsePreview(ev);
var path=chatEditPath(o.script, o.args);
if(!path&&parsed&&parsed.data){
var d=parsed.data;
path=String(d.path||d.dest_path||d.source_path||d.file_name||"").trim();
}
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
var dt=chatPaintDiffPane(o.chatToolDiffPane, o, ev);
var label=chatVersionCompareLabel(chatVersionComparePath(o, ev), chatVersionCompareStamp(o, ev));
if(label||dt)paintPreviewSummary(row, label, dt);
}
});
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
if(!ev.ok&&ev.error&&!ev.user_confirm_required){pane.textContent=String(ev.error);return;}
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
pane.appendChild(img);
shown=true;
}
}
if(!shown){
var miss=document.createElement("div");
miss.className="chat-tool-shot-miss";
miss.textContent=(!ev.ok&&ev.error)?String(ev.error):"（没有可显示的图片）";
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
registerChatToolView({
match:function(script, args){
return chatToolName(script)==="skill_manage"&&String(argGet(args,"action")||"").toLowerCase()==="read";
},
title:function(){return "加载 Skills";},
summary:function(o){return chatSkillName(o)||"（未指定 Skills）";},
mount:function(row, o){
var pane=addChatToolLayer(row._body,"","skill");
var box=document.createElement("div");
box.className="b a chat-tool-md";
box.textContent="（等待内容…）";
pane.appendChild(box);
o.chatToolSkill=box;
},
fill:function(row, o, ev){
var name=chatSkillName(o);
if(!name){
var j=chatToolParsePreview(ev);
var d=j&&j.data||{};
name=String(d.name||"").trim();
}
if(name)chatToolSetSummary(row, name);
var box=o.chatToolSkill;
if(!box)return;
if(!ev.ok&&ev.error&&!ev.user_confirm_required){box.textContent=String(ev.error);return;}
var text=chatSkillContent(ev);
if(text==null){box.textContent=ev.ok?"（无内容）":"（无结果）";return;}
if(!text){box.textContent="（空内容）";return;}
try{box.innerHTML=renderMarkdown(text);}catch(e){box.textContent=text;}
}
});
window.aiAgentChatTools={register:registerChatToolView};
function appendChatToolRow(row, opts){
if(!msgs||!row)return;
opts=opts||{};
if(opts.beforeStream&&streamAssistantEl&&streamAssistantEl.parentNode)streamAssistantEl.before(row);
else if(streamAssistantEl&&streamAssistantEl.parentNode){streamAssistantEl.after(row);streamAssistantEl=null;streamAssistantText="";}
else msgs.appendChild(row);
scrollMsgsToBottom();
}
function mountChatToolItem(o){
if(!showToolItems()||!o||o.chatToolRow)return;
var view=chatToolViewFor(o.script, o.args);
o.chatToolView=view;
var title=view.title?view.title(o):chatToolViewDefault.title(o);
var summary=view.summary?view.summary(o):"";
var row=makeChatToolRow(title, summary);
row.classList.add("is-running");
chatToolSyncStatusTitle(row);
o.chatToolRow=row;
if(view.mount)view.mount(row, o);
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
function fillChatToolResult(o, ev){
if(!o||!o.chatToolRow)return;
var view=o.chatToolView||chatToolViewDefault;
if(view.fill)view.fill(o.chatToolRow, o, ev);
o.chatToolRow.classList.remove("is-running");
o.chatToolRow.classList.remove("is-bad");
o.chatToolRow.classList.remove("is-canceled");
if(chatToolWasCanceled(ev))o.chatToolRow.classList.add("is-canceled");
/* 等人作答还没结束，标题继续跑马灯。 */
else if(ev.user_confirm_required||ev.approval_required)o.chatToolRow.classList.add("is-running");
else if(!ev.ok)o.chatToolRow.classList.add("is-bad");
chatToolSyncStatusTitle(o.chatToolRow);
}
