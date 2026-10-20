/* 本轮编辑只记在会话页上：预览留下 confirm_id 对应的 diff，提交成功留下确认 id。
   真正收尾时取两者交集。同一路径的多次修改按顺序都留下。等用户确认时的 done 不出清单。
   有效新消息（/api/chat/send）发出时清掉旧清单卡与页内映射；用户确认走单独接口，不清。 */
function liveEditPieces(data, args, script){
var icon=toolIco(script, args);
var out=[];
var name=String(script||"").toLowerCase();
function push(path, diff, op, note){
path=String(path||"").trim();
if(!path)return;
diff=String(diff||"");
var stat=chatDiffCounts(diff);
op=op||"edit";
if(op==="edit"){
if(stat.add&&!stat.del)op="add";
else if(stat.del&&!stat.add)op="del";
}
out.push({path:path, diff:diff, added:stat.add, deleted:stat.del, op:op, note:String(note||""), icon:icon});
}
if(name.indexOf("file_ops")>=0){
var action=String((data&&data.action)||argGet(args,"action")||"").toLowerCase();
var source=String((data&&data.source)||argGet(args,"source")||"").trim();
var dest=String((data&&data.dest)||argGet(args,"dest")||"").trim();
if(action==="delete"){push(source, "", "del", "");return out;}
if(action==="copy"){push(dest, "", "add", source?("复制自 "+source):"");return out;}
if(action==="move"||action==="rename"){
push(source, "", "del", dest?("移到 "+dest):"");
push(dest, "", "add", source?("来自 "+source):"");
return out;
}
}
if(name.indexOf("delete_file")>=0){
push((data&&data.path)||argGet(args,"path"), "", "del", "");
return out;
}
if(data&&Array.isArray(data.files)&&data.files.length){
for(var i=0;i<data.files.length;i++){
var f=data.files[i];
if(!f||typeof f!=="object")continue;
if(f.path)push(f.path, diffTextFromToolData(f), "edit", "");
}
if(out.length)return out;
}
push((data&&data.path)||argGet(args,"path")||argGet(args,"dest_path")||argGet(args,"source_path")||argGet(args,"dest")||argGet(args,"source"), diffTextFromToolData(data), "edit", "");
return out;
}
function noteLiveEdit(ev, tab){
if(!tab||!ev||!ev.ok)return;
var tid=String(ev.tool_call_id!=null?ev.tool_call_id:"").trim();
var o=tid&&toolOpen.get(tid);
var script=String((ev.script||(o&&o.script)||"")).toLowerCase();
var args=(o&&o.args)||{};
if(script==="commit_write"){
var cid=String(argGet(args,"confirm_id")||"").trim();
if(!cid)return;
if(!tab.editedConfirmed)tab.editedConfirmed=[];
tab.editedConfirmed.push(cid);
return;
}
if(script==="review_conclusion")return;
var data=null;
try{var parsed=typeof ev.preview==="string"?JSON.parse(ev.preview||""):ev.preview;data=parsed&&parsed.data;}catch(_e){data=null;}
if(!data||typeof data!=="object"||!data.confirm_id)return;
var pieces=liveEditPieces(data, args, script);
if(!pieces.length)return;
if(!tab.editedPreview)tab.editedPreview={};
tab.editedPreview[String(data.confirm_id).trim()]=pieces;
}
function clearLiveEdits(tab){
if(tab){tab.editedPreview={};tab.editedConfirmed=[];tab.editedHold=false;}
if(!msgs)return;
var cards=msgs.querySelectorAll(".edited-files");
for(var i=0;i<cards.length;i++){if(cards[i]&&cards[i].parentNode)cards[i].parentNode.removeChild(cards[i]);}
}
function finishLiveEdits(tab){
if(!tab)return;
if(tab.editedHold){tab.editedHold=false;return;}
var confirmed=tab.editedConfirmed||[];
var map=tab.editedPreview||{};
var rows=[];
var seq=0;
for(var i=0;i<confirmed.length;i++){
var pieces=map[confirmed[i]];
if(!pieces)continue;
for(var j=0;j<pieces.length;j++){var row=pieces[j];row.seq=seq++;rows.push(row);}
delete map[confirmed[i]];
}
tab.editedConfirmed=[];
var grouped={};
var order=[];
for(var k=0;k<rows.length;k++){
var path=rows[k].path;
if(!Object.prototype.hasOwnProperty.call(grouped, path)){grouped[path]=[];order.push(path);}
grouped[path].push(rows[k]);
}
var files=[];
for(var n=0;n<order.length;n++){
var parts=grouped[order[n]];
var added=0, deleted=0, op="edit";
for(var p=0;p<parts.length;p++){
added+=Number(parts[p].added)||0;
deleted+=Number(parts[p].deleted)||0;
op=parts[p].op||op;
}
files.push({path:order[n], parts:parts, added:added, deleted:deleted, op:op});
}
if(files.length)showEditedFiles(files);
}
function editedFileLabel(path){
return String(path||"");
}
function editedFileIcon(path){
if(window.aiAgentFileIcons&&typeof window.aiAgentFileIcons.el==="function")
return window.aiAgentFileIcons.el(path);
var ico=document.createElement("span");
ico.className="file-type-ico file-type-ico--file";
ico.setAttribute("aria-hidden","true");
return ico;
}
function fillEditedStat(sum, file){
sum.textContent="";
var a=Number(file&&file.added)||0, d=Number(file&&file.deleted)||0;
var op=String(file&&file.op||"edit");
if(!a&&!d){
var tag=document.createElement("span");
if(op==="del"){tag.className="chat-diff-neg";tag.textContent="删除";}
else if(op==="add"){tag.className="chat-diff-pos";tag.textContent="新增";}
else tag.textContent="0";
sum.appendChild(tag);
return;
}
if(d){
var neg=document.createElement("span");
neg.className="chat-diff-neg";
neg.textContent="-"+d;
sum.appendChild(neg);
}
if(a){
if(d)sum.appendChild(document.createTextNode(" "));
var pos=document.createElement("span");
pos.className="chat-diff-pos";
pos.textContent="+"+a;
sum.appendChild(pos);
}
}
function paintEditedOp(pane, file, path){
var box=document.createElement("div");
box.className="edited-op";
var k=document.createElement("div");
var op=String(file&&file.op||"edit");
k.className="edited-op-k "+(op==="del"?"is-del":"is-add");
k.textContent=op==="del"?"已删除":"新增";
box.appendChild(k);
var line=document.createElement("div");
line.className="edited-op-path";
line.textContent=path;
box.appendChild(line);
var note=String(file&&file.note||"").trim();
if(note){
var extra=document.createElement("div");
extra.className="edited-op-path";
extra.textContent=note;
box.appendChild(extra);
}
pane.appendChild(box);
}
function showEditedFiles(files){
if(!msgs||!Array.isArray(files)||!files.length)return;
var e=document.createElement("div");
e.className="edited-files";
var head=document.createElement("div");
head.className="edited-files-head";
var title=document.createElement("div");
title.className="edited-files-title";
var review=document.createElement("button");
review.type="button";
review.className="edited-files-review";
review.setAttribute("data-edited-review","1");
review.textContent="查看";
head.appendChild(title);
head.appendChild(review);
e.appendChild(head);
var count=0;
for(var i=0;i<files.length;i++){
var file=files[i];
if(!file||typeof file!=="object")continue;
var path=String(file.path||"").trim();
if(!path)continue;
var row=makeChatToolRow(editedFileLabel(path),"");
var op=String(file.op||"edit");
if(op==="add"||op==="del")row.classList.add("is-"+op);
var btn=row.querySelector(".chat-tool-head");
if(btn)btn.title=path;
var ico=editedFileIcon(path);
row._title.parentNode.insertBefore(ico, row._title);
fillEditedStat(row._sum, file);
var parts=Array.isArray(file.parts)&&file.parts.length?file.parts:[file];
for(var s=0;s<parts.length;s++){
var part=parts[s];
var diff=String(part&&part.diff||"");
var pane=addChatToolLayer(row._body,"",diff.trim()?"diff":"");
if(pane.parentNode)pane.parentNode.classList.add("edited-sec");
if(diff.trim())chatPaintDiffPane(pane,{},{preview:JSON.stringify({data:{path:path,_diff:diff}})});
else paintEditedOp(pane, part, path);
}
e.appendChild(row);
count++;
}
if(!count)return;
title.textContent=count+" 个文件已更改";
if(!e._editedReviewDelegated){
e._editedReviewDelegated=true;
e.addEventListener("click",function(ev){
var hit=ev.target&&ev.target.closest?ev.target.closest("[data-edited-review]"):null;
if(!hit||!e.contains(hit))return;
var rows=e.querySelectorAll(".chat-tool-row");
var allOpen=rows.length>0;
for(var i=0;i<rows.length;i++){if(!rows[i].classList.contains("is-open"))allOpen=false;}
var open=!allOpen;
for(var j=0;j<rows.length;j++){
rows[j].classList.toggle("is-open", open);
var item=rows[j].querySelector(".chat-tool-head");
if(item)item.setAttribute("aria-expanded", open?"true":"false");
}
});
}
msgs.appendChild(e);
scrollMsgsToBottom();
}
