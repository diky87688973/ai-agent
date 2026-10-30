/* chat/bubbles.js —— 对话气泡：用户/助手/其它 Agent 消息创建与流式气泡。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
function _systemNoticeBatch(text){
var m=String(text||"").match(/任务批次[:：]\s*([^\n]+?)\s*已完结/);
return m?m[1].trim():"";
}
function _sysNoticeHost(){
var pane=msgs&&msgs.closest?msgs.closest(".chat-conversation-pane"):null;
if(!pane)return null;
var host=pane.querySelector(":scope > .sys-notice-host");
if(!host){host=document.createElement("div");host.className="sys-notice-host";pane.insertBefore(host,pane.firstChild);}
return host;
}
function _hideSystemNotice(target){
var card=target;
if(!card||!card.parentNode)return;
if(card._sysNoticeTimer){clearTimeout(card._sysNoticeTimer);card._sysNoticeTimer=null;}
card.classList.add("is-leaving");
setTimeout(function(){if(card.parentNode)card.parentNode.removeChild(card);},220);
}
function _clearSystemNoticeTimer(card){
if(card&&card._sysNoticeTimer){clearTimeout(card._sysNoticeTimer);card._sysNoticeTimer=null;}
}
function _armSystemNoticeTimer(target,delay){
var card=target;
if(!card)return;
_clearSystemNoticeTimer(card);
card._sysNoticeTimer=setTimeout(function(){_hideSystemNotice(card);},delay);
}
function _replaceSystemNotices(host,next){
if(!host)return;
var old=host.querySelectorAll(".sys-notice");
Array.prototype.forEach.call(old,function(card){
_clearSystemNoticeTimer(card);
card.classList.add("is-leaving");
setTimeout(function(){if(card.parentNode)card.parentNode.removeChild(card);},180);
});
host.appendChild(next);
}
function addSystemNotice(t,meta){
if(!msgs)return null;
var text=String(t||"");
var meta=meta&&typeof meta==="object"?meta:{};
var batch=String(meta.batch||"").trim()||_systemNoticeBatch(text);
var host=_sysNoticeHost();
var e=document.createElement("div");
e.className="sys-notice";
var head=document.createElement("button");
head.type="button";
head.className="sys-notice-head";
head.setAttribute("aria-expanded","false");
var title=document.createElement("span");
title.className="sys-notice-title";
title.textContent="系统通知"+(batch?": 任务 "+batch+" 已完结":": 任务已完结");
var chevron=document.createElement("span");
chevron.className="sys-notice-chevron";
chevron.setAttribute("aria-hidden","true");
chevron.innerHTML='<svg viewBox="0 0 16 16" width="12" height="12"><path d="M3.5 6.5 8 11l4.5-4.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>';
head.appendChild(title);
head.appendChild(chevron);
var detail=document.createElement("div");
detail.className="sys-notice-detail";
detail.textContent=text.replace(/^<<系统通知>>\s*/,"").trim();
e.appendChild(head);
e.appendChild(detail);
e.setAttribute("role","status");
if(host)_replaceSystemNotices(host,e);else msgs.appendChild(e);
_armSystemNoticeTimer(e,6000);
return e;
}
function _toggleSystemNotice(head){
var card=head&&head.closest?head.closest(".sys-notice"):null;
if(!card)return;
var detail=card.querySelector(".sys-notice-detail");
var open=head.getAttribute("aria-expanded")==="true";
head.setAttribute("aria-expanded",open?"false":"true");
if(detail)detail.classList.toggle("is-open",!open);
if(open){
_armSystemNoticeTimer(card,4000);
}else{
_clearSystemNoticeTimer(card);
}
}
if(!window._sysNoticeDelegated){
window._sysNoticeDelegated=true;
document.addEventListener("click",function(ev){
var head=ev.target&&ev.target.closest?ev.target.closest(".sys-notice-head"):null;
if(head)_toggleSystemNotice(head);
});
}
function add(role,t,meta){
if(!msgs)return null;
if(role==='u'&&meta&&meta.kind==="system_notice"&&meta.source==="background_tasks")return addSystemNotice(t,meta);
const e=document.createElement('div');
e.className='b '+(role==='u'?'u':'a');
if(role==='u'){/* 文字包一层 span —— 这样「文字」是独立子元素，附件条能用 CSS `order` 排到它前面（气泡是 flex 纵向布局，文字需要成为独立子元素才能用 `order` 调整顺序）。 */e.appendChild(Object.assign(document.createElement('span'),{className:'b-text',innerHTML:linkifyUserText(t)}));}else{e.innerHTML=renderMarkdown(t||'');}
msgs.appendChild(e);
scrollMsgsToBottom();
return e;
}
function _peerAvatarLetter(name){
var s=String(name||"A").trim();
return s?s.charAt(0).toUpperCase():"A";
}
function _buildPeerMetaHtml(metaRaw){
var line=String(metaRaw||"").trim().replace(/\|/g," ");
if(!line)return"";
return'<span class="peer-meta-tag">'+escapeHtml(line)+"</span>";
}
function addPeerMessage(t,name,cid){
if(!msgs)return;
var label=String(name||cid||"Agent");
var content=t||"";
var metaHtml="";
if(content.indexOf("[from=")===0){var ci=content.indexOf("]");if(ci>0){var metaRaw=content.slice(1,ci);content=content.slice(ci+1).trim();metaHtml=_buildPeerMetaHtml(metaRaw);}}
var e=document.createElement("div");
e.className="peer-chat-row is-collapsed";
var nameLine=escapeHtml(label);
if(cid&&cid!==label)nameLine+=' <span class="peer-agent-cid">'+escapeHtml(String(cid).slice(0,8))+'</span>';
e.innerHTML=
'<div class="peer-top">'+
'<div class="peer-avatar" title="'+escapeHtml(label)+'">'+escapeHtml(_peerAvatarLetter(label))+'</div>'+
'<div class="peer-top-text">'+
'<div class="peer-agent-name">'+nameLine+'</div>'+
(metaHtml||'')+
'<span class="peer-expand-hint">点击查看详情</span>'+
'</div></div>'+
'<div class="peer-bubble"><div class="peer-agent-body b a"></div></div>';
var bodyEl=e.querySelector(".peer-agent-body");
if(bodyEl){bodyEl.innerHTML=renderMarkdown(content||"");}
msgs.appendChild(e);
if(!window._peerToggleDelegated){
window._peerToggleDelegated=true;
function togglePeerRow(top){
if(!top)return;
var row=top.closest?top.closest(".peer-chat-row"):null;
if(!row)return;
row.classList.toggle("is-collapsed");
}
document.addEventListener("click",function(ev){
var top=ev.target&&ev.target.closest?ev.target.closest(".peer-top"):null;
if(top)togglePeerRow(top);
});
}
scrollMsgsToBottom();
}

function ensureAssistantStreamBubble(){
if(streamAssistantEl)return streamAssistantEl;
if(!msgs)return null;
const e=document.createElement('div');
e.className='b a';
e.innerHTML='';
msgs.appendChild(e);
scrollMsgsToBottom();
streamAssistantEl=e;
streamAssistantText='';
return e;
}
/* 流式渲染节流：每个锚点最多渲染一次。
   marked 每次都是全量重解析（块级缓存对它无效），delta 密集时逐条渲染会把
   同一段文本反复解析几十遍 —— 内容越长越明显。合并到下一个锚点渲染，
   视觉上仍是连续增长。 */
var streamRenderPending=false;
function scheduleStreamRender(){
if(streamRenderPending)return;
streamRenderPending=true;
requestAnimationFrame(function(){
streamRenderPending=false;
if(!streamAssistantEl)return;
streamAssistantEl.innerHTML=renderMarkdown(streamAssistantText);
scrollMsgsToBottom();
});
}
function appendAssistantDelta(text){
if(typeof text!=='string'||!text)return;
const e=ensureAssistantStreamBubble();if(!e)return;
if(pendingDeltaSeparator&&streamAssistantText){
streamAssistantText+='\n\n';
}
pendingDeltaSeparator=false;
streamAssistantText+=text;
scheduleStreamRender();
}
function finalizeAssistantStream(content){
if(streamAssistantEl){
if(typeof content==='string'&&content){
streamAssistantText=String(content);
/* 终态必须同步渲染完，不能留给节流：随后就把元素引用清掉了 */
streamAssistantEl.innerHTML=renderMarkdown(streamAssistantText);
}
streamAssistantEl=null;
streamAssistantText='';
pendingDeltaSeparator=false;
scrollMsgsToBottom();
return true;
}
return false;
}
function webUiFlag(name, fallback){
var o=window.__webUi||{};
if(!Object.prototype.hasOwnProperty.call(o,name))return fallback;
var v=o[name];
if(v===true||v===1||v==="1")return true;
if(v===false||v===0||v==="0")return false;
return !!v;
}
function showToolSteps(){return webUiFlag("display_tool_steps", false);}
function showToolItems(){return webUiFlag("display_tool_items", true);}
if(!showToolSteps())document.documentElement.setAttribute("data-tool-steps","off");
else document.documentElement.removeAttribute("data-tool-steps");
