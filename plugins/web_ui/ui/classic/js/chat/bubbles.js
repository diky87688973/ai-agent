/* chat/bubbles.js —— 对话气泡：用户/助手/其它 Agent 消息创建与流式气泡。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
function _systemNoticeBatch(text){
var m=String(text||"").match(/任务批次[:：]\s*([^\n]+?)\s*已完结/);
return m?m[1].trim():"";
}
function addSystemNotice(t,meta,host){
if(!msgs)return null;
var text=String(t||"");
var meta=meta&&typeof meta==="object"?meta:{};
var batch=String(meta.batch||"").trim()||_systemNoticeBatch(text);
var e=document.createElement("div");
e.className="sys-notice";
var head=document.createElement("button");
head.type="button";
head.className="sys-notice-head";
head.setAttribute("aria-expanded","false");
var title=document.createElement("span");
title.className="sys-notice-title";
title.textContent=meta.kind==="wake"?"定时提醒":
  (batch?"系统通知 · 任务 "+batch+" 已完结":"系统通知");
var chevron=document.createElement("span");
chevron.className="sys-notice-chevron";
chevron.setAttribute("aria-hidden","true");
chevron.innerHTML='<svg viewBox="0 0 16 16" width="12" height="12"><path d="M3.5 6.5 8 11l4.5-4.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>';
head.appendChild(title);
head.appendChild(chevron);
var detail=document.createElement("div");
detail.className="sys-notice-detail";
detail.textContent=stripSystemPrefix(text).trim();
e.appendChild(head);
e.appendChild(detail);
e.setAttribute("role","status");
(host||msgs).appendChild(e);
scrollMsgsToBottom();
return e;
}
function _toggleSystemNotice(head){
var card=head&&head.closest?head.closest(".sys-notice"):null;
if(!card)return;
var detail=card.querySelector(".sys-notice-detail");
var open=head.getAttribute("aria-expanded")==="true";
head.setAttribute("aria-expanded",open?"false":"true");
if(detail)detail.classList.toggle("is-open",!open);
}
if(!window._sysNoticeDelegated){
window._sysNoticeDelegated=true;
document.addEventListener("click",function(ev){
var head=ev.target&&ev.target.closest?ev.target.closest(".sys-notice-head"):null;
if(head)_toggleSystemNotice(head);
});
}
function addGoalFollowup(t, meta, host) {
  if (!msgs) return null;
  var data = meta && typeof meta === "object" ? meta : {};
  var text = stripSystemPrefix(t).trim();
  var round = Number(data.goal_round || 0);
  var limit = Number(data.goal_limit || 0);
  var card = document.createElement("div");
  card.className = "goal-followup";
  var head = document.createElement("button");
  head.type = "button";
  head.className = "goal-followup-head";
  head.setAttribute("aria-expanded", "false");
  var icon = document.createElement("span");
  icon.className = "goal-followup-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8"></circle><circle cx="12" cy="12" r="3.2"></circle><path d="M12 2v3M12 19v3M2 12h3M19 12h3"></path></svg>';
  var main = document.createElement("span");
  main.className = "goal-followup-main";
  var titleline = document.createElement("span");
  titleline.className = "goal-followup-titleline";
  var title = document.createElement("span");
  title.className = "goal-followup-title";
  title.textContent = "目标跟进";
  titleline.appendChild(title);
  if (round > 0) {
    var badge = document.createElement("span");
    badge.className = "goal-followup-badge";
    badge.textContent = "第 " + round + (limit > 0 ? "/" + limit : "") + " 轮";
    titleline.appendChild(badge);
  }
  var summary = document.createElement("span");
  summary.className = "goal-followup-summary";
  summary.textContent = text ? text.replace(/\s+/g, " ").trim() : "（无目标内容）";
  main.appendChild(titleline);
  main.appendChild(summary);
  var chevron = document.createElement("span");
  chevron.className = "goal-followup-chevron";
  chevron.setAttribute("aria-hidden", "true");
  chevron.innerHTML = '<svg viewBox="0 0 16 16" width="14" height="14"><path d="M3.5 6.5 8 11l4.5-4.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"></path></svg>';
  head.appendChild(icon);
  head.appendChild(main);
  head.appendChild(chevron);
  var detail = document.createElement("div");
  detail.className = "goal-followup-detail";
  var detailLabel = document.createElement("div");
  detailLabel.className = "goal-followup-detail-label";
  detailLabel.textContent = "本轮目标";
  var detailText = document.createElement("div");
  detailText.className = "goal-followup-text";
  detailText.textContent = text || "（无目标内容）";
  detail.appendChild(detailLabel);
  detail.appendChild(detailText);
  card.appendChild(head);
  card.appendChild(detail);
  (host || msgs).appendChild(card);
  scrollMsgsToBottom();
  return card;
}
function _toggleGoalFollowup(head) {
  var card = head && head.closest ? head.closest(".goal-followup") : null;
  if (!card) return;
  var detail = card.querySelector(".goal-followup-detail");
  var open = head.getAttribute("aria-expanded") === "true";
  head.setAttribute("aria-expanded", open ? "false" : "true");
  if (detail) detail.classList.toggle("is-open", !open);
}
if (!window._goalFollowupDelegated) {
  window._goalFollowupDelegated = true;
  document.addEventListener("click", function (ev) {
    var head = ev.target && ev.target.closest ? ev.target.closest(".goal-followup-head") : null;
    if (head) _toggleGoalFollowup(head);
  });
}
function stripSystemPrefix(t){
return String(t==null?"":t).replace(/^【系统消息-[^】]*?】\n\n/,"");
}
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
function addPeerMessage(t,name,cid,host){
if(!msgs)return;
var label=String(name||cid||"Agent");
var content=stripSystemPrefix(t);
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
(host||msgs).appendChild(e);
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
return bodyEl;
}

function renderConversationInput(item, cid, replay) {
  var sender = item.sender || item._sender;
  var peer = sender && sender !== "boss";
  var notice = item.kind === "wake" || item.kind === "system_notice";
  var goal = item.kind === "goal_followup";
  var inside = replay ? item.in_turn : item.turn_key != null;
  var host = (peer || notice || goal) && inside ? chatProcessBody() : msgs;
  var text = String(item.content || "");
  var bubble;
  if (peer) bubble = addPeerMessage(text, item.sender_name || item._sender_name, sender, host);
  else if (notice) bubble = addSystemNotice(text, item, host);
  else if (goal) bubble = addGoalFollowup(text, item, host);
  else bubble = add("u", text || (replay ? "" : "（截图）"));
  if (!bubble) return;
  var attachments = Array.isArray(item.attachments) ? item.attachments : [];
  if (attachments.length && window.AIA && AIA.buildMsgAttachStrip) {
    bubble.appendChild(AIA.buildMsgAttachStrip(cid, replay ? attachments : null, replay ? null : attachments));
  } else if (replay && item.had_images) {
    if (window.AIA && AIA.appendHadImagesLostTip) AIA.appendHadImagesLostTip(bubble);
    else appendHadImagesLostTip(bubble);
  }
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
function scheduleStreamRender(){
var node=streamAssistantEl;
var conversation=msgs;
if(!node||node._streamRenderPending)return;
node._streamRenderPending=true;
node._streamRenderText=streamAssistantText;
requestAnimationFrame(function(){
node._streamRenderPending=false;
if(node._streamRenderText==null)return;
node.innerHTML=renderMarkdown(node._streamRenderText);
if(conversation===msgs)scrollMsgsToBottom();
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
e._streamRenderText=streamAssistantText;
scheduleStreamRender();
}
function finalizeAssistantStream(content){
if(streamAssistantEl){
streamAssistantEl._streamRenderText=null;
if(typeof content==='string'&&content){
streamAssistantText=String(content);
/* 终态必须同步渲染完，不能留给节流：随后就把元素引用清掉了 */
streamAssistantEl.innerHTML=renderMarkdown(streamAssistantText);
}else if(streamAssistantText){
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
