/* chat/bubbles.js —— 对话气泡：用户/助手/其它 Agent 消息创建与流式气泡。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
function add(role,t){
if(!msgs)return null;
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
e.className="peer-chat-row";
var nameLine=escapeHtml(label);
if(cid&&cid!==label)nameLine+=' <span class="peer-agent-cid">'+escapeHtml(String(cid).slice(0,8))+'</span>';
e.innerHTML=
'<div class="peer-top">'+
'<div class="peer-avatar" title="'+escapeHtml(label)+'">'+escapeHtml(_peerAvatarLetter(label))+'</div>'+
'<div class="peer-top-text">'+
'<div class="peer-agent-name">'+nameLine+'</div>'+
(metaHtml||'')+
'</div></div>'+
'<div class="peer-bubble"><div class="peer-agent-body b a"></div></div>';
var bodyEl=e.querySelector(".peer-agent-body");
if(bodyEl){bodyEl.innerHTML=renderMarkdown(content||"");}
msgs.appendChild(e);
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
