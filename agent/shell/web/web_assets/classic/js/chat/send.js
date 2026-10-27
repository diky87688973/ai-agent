/* chat/send.js —— 发送消息与附件：请求、错误文案、图片粘贴/选择。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
async function sendChatMessage(){
if(!ta)return;
var text=String(ta.value||"").trim();
var imgs=pendingChatImages.slice();
if(!text&&!imgs.length)return;
if(typeof cancelUserConfirmForNewMessage==="function")cancelUserConfirmForNewMessage();
var busy=typeof isConversationBusy==="function"&&isConversationBusy();
var draft=(window.chatDraft&&window.chatDraft.id)?window.chatDraft:null;
var defer=!!(busy||draft);
var sendCid=getActiveConversationId();
/* 有效新消息才清本回合编辑清单；/api/chat/user-confirm 不走这里。 */
if(typeof clearLiveEdits==="function")clearLiveEdits(findConversationTab(sendCid));
/* 气泡只显示文字：图片由下方的附件条（缩略图）表达，不再追加 `[图片 ×N]` 后缀。
   只发图不打字时给个占位，否则气泡是空的。 */
var display=text||"（截图）";
var bubble=null;
var stripEl=null;
if(!defer){
bubble=add("u",display);
if(imgs.length&&window.AIA&&AIA.buildMsgAttachStrip&&bubble){
try{
stripEl=AIA.buildMsgAttachStrip(sendCid,null,imgs);
bubble.appendChild(stripEl);
}catch(e){}
}
ta.value="";
clearPendingChatImages();
autoResizeTextarea();
resetSteps();
showChatLoading();
}
var tab=findConversationTab(sendCid);
var b=goBtn;if(b)b.disabled=true;
if(tab&&!defer){tab.abortController={global:true};tab.stopRequested=false;tab.activeRunId="";}
updateTaskControls();
try{
var body={message:text,conversation_id:sendCid,mode:selectedMode,model:selectedModel};
if(imgs.length)body.images=imgs.map(function(it){return{mime:it.mime,data_base64:it.data_base64};});
if(draft)body.draft_id=draft.id;
var _sendUrl="/api/chat/send";
if(tab&&tab.subagent){body={conversation_id:String(tab.parentCid||""),child_id:sendCid,msg:text};if(imgs.length)body.images=imgs.map(function(it){return{mime:it.mime,data_base64:it.data_base64};});_sendUrl="/api/subagents/send";}
var r=await fetch(_sendUrl,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
if(!r.ok){var _bt="";try{_bt=await r.text();}catch(e){}if(window.DEBUG)console.error("[ai-agent] /api/chat/send 非 OK",{status:r.status,bodyHead:String(_bt||"").slice(0,500)});withConversationContext(sendCid,function(){hideChatLoading();add("a",formatHttpError(r.status,_bt,"发送"));});if(tab){tab.abortController=null;tab.activeRunId="";}return;}
var _sj=await r.json();if(tab&&_sj&&_sj.run_id)tab.activeRunId=String(_sj.run_id||"");
if(defer){
  ta.value="";
  clearPendingChatImages();
  autoResizeTextarea();
  clearQueueDraft();
  if(!busy&&draft&&draft.origin!=="agent")add("u",display);
  if(_sj&&_sj.queued&&typeof loadChatQueue==="function")loadChatQueue(sendCid);
}else if(stripEl&&_sj&&Array.isArray(_sj.attachments)&&_sj.attachments.length&&window.AIA&&AIA.buildMsgAttachStrip){
try{
var neu=AIA.buildMsgAttachStrip(sendCid,_sj.attachments,null);
if(neu&&stripEl.parentNode)stripEl.parentNode.replaceChild(neu,stripEl);
}catch(e2){}
}
}catch(err){
if(!(err&&err.name==="AbortError")){withConversationContext(sendCid,function(){hideChatLoading();add("a","请求失败: "+(err&&err.message?err.message:String(err)));});}
}finally{
updateTaskControls();
if(typeof renderChatTabs==="function")renderChatTabs();
void persistUsageAccumulator();
}
}

var pendingChatImages=[];
function renderAttachStrip(){
var strip=document.getElementById("attachStrip");
if(!strip)return;
strip.innerHTML="";
if(!pendingChatImages.length){strip.classList.add("hidden");return;}
strip.classList.remove("hidden");
pendingChatImages.forEach(function(it,idx){
var d=document.createElement("div");d.className="attach-thumb";
var img=document.createElement("img");img.src=it.previewUrl;img.alt="attach";
if(window.AIA&&AIA.bindThumbClick)AIA.bindThumbClick(img);
var btn=document.createElement("button");btn.type="button";btn.textContent="×";btn.title="移除";btn.setAttribute("data-attach-remove",String(idx));
d.appendChild(img);d.appendChild(btn);strip.appendChild(d);
});
}
function initAttachStripDelegation(){
var strip=document.getElementById("attachStrip");
if(!strip||strip._attachClickDelegated)return;
strip._attachClickDelegated=true;
strip.addEventListener("click",function(ev){
var btn=ev.target&&ev.target.closest?ev.target.closest("[data-attach-remove]"):null;
if(!btn||!strip.contains(btn))return;
ev.preventDefault();
ev.stopPropagation();
var idx=Number(btn.getAttribute("data-attach-remove"));
if(!Number.isFinite(idx)||idx<0||idx>=pendingChatImages.length)return;
pendingChatImages.splice(idx,1);
renderAttachStrip();
});
}
function clearPendingChatImages(){
pendingChatImages.forEach(function(it){try{URL.revokeObjectURL(it.previewUrl);}catch(e){}});
pendingChatImages=[];
renderAttachStrip();
}
function fileToPendingImage(file){
return new Promise(function(resolve,reject){
if(!file||!String(file.type||"").startsWith("image/")){reject(new Error("not image"));return;}
var reader=new FileReader();
reader.onload=function(){
var dataUrl=String(reader.result||"");
var b64=dataUrl.indexOf(",")>=0?dataUrl.split(",")[1]:dataUrl;
resolve({mime:file.type||"image/png",data_base64:b64,previewUrl:URL.createObjectURL(file),name:file.name||"paste.png"});
};
reader.onerror=function(){reject(reader.error||new Error("read fail"));};
reader.readAsDataURL(file);
});
}
async function addPendingImageFiles(fileList){
var files=Array.prototype.slice.call(fileList||[]);
for(var i=0;i<files.length;i++){
if(pendingChatImages.length>=(Number(window.AI_AGENT_MAX_IMAGES)||4))break;
try{
var it=await fileToPendingImage(files[i]);
pendingChatImages.push(it);
}catch(e){}
}
renderAttachStrip();
}
(function initChatAttach(){
initAttachStripDelegation();
var attachBtn=document.getElementById("attachBtn");
var attachFile=document.getElementById("attachFile");
if(attachBtn&&attachFile){
attachBtn.addEventListener("click",function(){attachFile.click();});
attachFile.addEventListener("change",function(){void addPendingImageFiles(attachFile.files);attachFile.value="";});
}
if(ta){
ta.addEventListener("paste",function(ev){
var cd=ev.clipboardData;
var hasImg=false;
if(cd&&cd.items){
for(var i=0;i<cd.items.length;i++){
if(cd.items[i].type&&cd.items[i].type.indexOf("image/")===0){hasImg=true;break;}
}
}
if(!hasImg)return;
ev.preventDefault();
var collect=window.AIA&&AIA.collectPasteImageFiles?AIA.collectPasteImageFiles(cd):Promise.resolve([]);
void collect.then(function(files){
if(files&&files.length)void addPendingImageFiles(files);
});
});
}
})();

(function initClassicMainSplit(){
