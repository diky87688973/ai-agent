// 调试：控制台执行 window.DEBUG=1（或 DEBUG=1）后输出 SSE / 预览等 console 日志
// 主题与全页只读选区的实现在 theme-ui.js（经典页内联包首部已包含该脚本）
const CONVERSATION_STORAGE_KEY="aiAgent.activeConversationId";
const CONVERSATION_TABS_STORAGE_KEY="aiAgent.openConversationTabs";
function newConversationId(){return crypto.randomUUID?crypto.randomUUID():'xxxxxxxxxxxx4xxxyxxxxxxxxxxxxxxx'.replace(/[xy]/g,function(c){const r=Math.random()*16|0;return(c==='x'?r:(r&0x3|0x8)).toString(16);});}
function readCookieValue(name){const m=document.cookie.match(new RegExp("(?:^|;\\s*)"+name.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")+"=([^;]+)"));return m?decodeURIComponent(m[1]):"";}
function clearCookie(name){document.cookie=name+"=; path=/; max-age=0; SameSite=Lax";}
function normalizeConversationId(id){id=String(id||"").trim();return /^[A-Za-z0-9_-]{8,128}$/.test(id)?id:"";}
function getUrlConversationId(){try{const p=new URLSearchParams(window.location.search);return normalizeConversationId(p.get("conversation_id")||p.get("cid")||"");}catch(e){return "";}}
function getStoredConversationId(){try{return normalizeConversationId(sessionStorage.getItem(CONVERSATION_STORAGE_KEY)||"");}catch(e){return "";}}
function storeConversationId(id){try{sessionStorage.setItem(CONVERSATION_STORAGE_KEY,id);}catch(e){}}
function getStoredConversationLayout(){try{var raw=localStorage.getItem(CONVERSATION_TABS_STORAGE_KEY)||"";var o=raw?JSON.parse(raw):null;if(!o||typeof o!=="object")return null;var tabs=Array.isArray(o.tabs)?o.tabs:[];tabs=tabs.map(function(t){return {id:normalizeConversationId(t&&t.id),title:String(t&&t.title||"").slice(0,80)};}).filter(function(t){return !!t.id;});var active=normalizeConversationId(o.active_conversation_id||o.activeConversationId||"");return tabs.length?{active_conversation_id:active||tabs[0].id,tabs:tabs}:null;}catch(e){return null;}}
function storeConversationLayoutLocal(){try{localStorage.setItem(CONVERSATION_TABS_STORAGE_KEY,JSON.stringify({active_conversation_id:activeConversationId,tabs:conversationTabs.map(function(t){return {id:t.id,title:t.title||("会话 "+t.id.slice(0,8))};})}));}catch(e){}}
/* 开局激活哪个会话，**只看本地**（服务端不参与）：
   `?conversation_id=` > 本地布局记着的激活会话 > 本地会话记忆 > cookie > 新会话。
   本地空空如也就是新会话 —— 不去服务端拉一个来激活。 */
function getOrCreateConversationId(){let id=getUrlConversationId();if(id){storeConversationId(id);return id;}var layout=getStoredConversationLayout();if(layout&&layout.active_conversation_id){storeConversationId(layout.active_conversation_id);return layout.active_conversation_id;}id=getStoredConversationId();if(id)return id;id=normalizeConversationId(readCookieValue("sessionId"));if(id){storeConversationId(id);clearCookie("sessionId");return id;}id=newConversationId();storeConversationId(id);return id;}
function createDetachedHost(className){var d=document.createElement("div");d.className=className||"";return d;}
function buildTodoArea(){var n=document.createElement("div");n.className="todo-list-area hidden";n.style.display="";var hdr=document.createElement("div");hdr.className="todo-list-header";var ttl=document.createElement("span");ttl.className="todo-list-title";ttl.textContent="📋 Todo List";var cnt=document.createElement("span");cnt.className="todo-list-count";cnt.textContent="0/0";var ic=document.createElement("span");ic.className="todo-collapse-icon";ic.textContent="▼";hdr.appendChild(ttl);hdr.appendChild(cnt);hdr.appendChild(ic);hdr.addEventListener("click",function(e){if(e.target.closest&&e.target.closest(".todo-list-count"))return;n.classList.toggle("collapsed");});var bd=document.createElement("div");bd.className="todo-list-body";var sc=document.createElement("div");sc.className="todo-list-scroll";bd.appendChild(sc);n.appendChild(hdr);n.appendChild(bd);return n;}
function makeConversationTab(id){id=normalizeConversationId(id)||newConversationId();var pane=document.createElement("div");pane.className="chat-conversation-pane";var mh=createDetachedHost("msgs");var td=buildTodoArea();pane.appendChild(mh);pane.appendChild(td);return {id:id,title:"会话 "+id.slice(0,8),conversationPane:pane,msgsHost:mh,stepsHost:createDetachedHost("steps"),todoArea:td,selectedMode:"auto",selectedModel:"",abortController:null,activeRunId:"",stopRequested:false,stepSeq:0,lastLlm:null,llmStreamBuffer:{round:null,reqHtml:"",resHtml:"",consumed:false},pendingToolTags:[],anyToolThisTurn:false,pendingStepEls:[],streamAssistantEl:null,streamAssistantText:"",pendingDeltaSeparator:false,seenDispatchTitle:"",toolOpen:new Map(),lastAnalysisTail:"",chatLoadingEl:null,userConfirmCardHost:null,userConfirmBlocking:false,todoUnread:false,sessionTokenUsed:0,totalPromptTokens:0,totalCompletionTokens:0,totalCacheHitTokens:0,totalCacheMissTokens:0,pricingCacheKey:"",pricingRates:null,pricingFailed:false,pricingLoading:false,pricingInflight:false,pricingFetchGen:0,lastContextLayout:null};}
const initialConversationId=getOrCreateConversationId();
let _initialLayout=getStoredConversationLayout();
let conversationTabs=(_initialLayout&&_initialLayout.tabs.length?_initialLayout.tabs.map(function(t){var tab=makeConversationTab(t.id);tab.title=t.title||tab.title;return tab;}):[makeConversationTab(initialConversationId)]);
let activeConversationId=initialConversationId;
if(_initialLayout&&findConversationTab(_initialLayout.active_conversation_id))activeConversationId=_initialLayout.active_conversation_id;
try{var _fromImm=normalizeConversationId(sessionStorage.getItem(CONVERSATION_STORAGE_KEY)||"");if(_fromImm){ensureConversationTab(_fromImm);activeConversationId=_fromImm;storeConversationId(_fromImm);}}catch(_eI){}
function getActiveTab(){for(var i=0;i<conversationTabs.length;i++){if(conversationTabs[i].id===activeConversationId)return conversationTabs[i];}var t=makeConversationTab(activeConversationId||newConversationId());conversationTabs.push(t);return t;}
function findConversationTab(id){id=normalizeConversationId(id);for(var i=0;i<conversationTabs.length;i++){if(conversationTabs[i].id===id)return conversationTabs[i];}return null;}
function ensureConversationTab(id){id=normalizeConversationId(id)||newConversationId();var t=findConversationTab(id);if(!t){t=makeConversationTab(id);conversationTabs.push(t);if(typeof renderChatTabs==="function")renderChatTabs();}return t;}
function getActiveConversationId(){return activeConversationId;}
function setActiveConversationId(id,opts){id=normalizeConversationId(id)||newConversationId();var t=ensureConversationTab(id);activeConversationId=id;sessionId=id;conv=id;storeConversationId(id);t.id=id;t.title=t.title||("会话 "+id.slice(0,8));if(typeof cid!=="undefined"&&cid)cid.textContent=id.slice(0,8);if(!opts||opts.resetPricing!==false){pricingRates=null;pricingFailed=false;pricingCacheKey="";pricingLoading=false;pricingInflight=false;pricingFetchGen++;}if(typeof renderChatTabs==="function")renderChatTabs();if(typeof _updateUsageBottom==="function")_updateUsageBottom();}
let sessionId=activeConversationId;let conv=sessionId,stepSeq=0,lastLlm=null;let llmStreamBuffer={round:null,reqHtml:"",resHtml:"",consumed:false};let pendingToolTags=[];let anyToolThisTurn=false;let pendingStepEls=[];let streamAssistantEl=null,streamAssistantText="";let pendingDeltaSeparator=false;let seenDispatchTitle="";/* 上下文占用率的分母 = **模型窗口**（内核在 context_layout 里给）。
   没给时退回下面这个兜底值，界面会标明口径。 */
var SESSION_TOKEN_LIMIT=1000000;
function setModelContextWindow(n){var v=Number(n??0)||0;if(v>0)SESSION_TOKEN_LIMIT=v;}let sessionTokenUsed=0;
let totalPromptTokens=0,totalCompletionTokens=0,totalCacheHitTokens=0,totalCacheMissTokens=0;
let pricingCacheKey="";let pricingRates=null;let pricingFailed=false;let pricingLoading=false;let pricingInflight=false;let pricingFetchGen=0;
var ctxLayoutTooltipEl=null;var ctxLayoutTooltipInited=false;var ctxLayoutTipHideTimer=null;
let renderingContextVisible=true;
let toolOpen=new Map();let lastAnalysisTail="";
let chatLoadingEl=null;
var userConfirmCardHost=null;
var userConfirmBlocking=false;
var todoListArea=null,todoListBody=null,todoListCount=null;
function showChatLoading(){if(chatLoadingEl||!msgs)return;chatLoadingEl=document.createElement("div");chatLoadingEl.className="b a";chatLoadingEl.style.textAlign="center";chatLoadingEl.style.padding="16px 0";chatLoadingEl.innerHTML="<span class=\"chat-spinner\"></span> <span style=\"color:#888;font-size:12px\">正在思考中…</span>";msgs.appendChild(chatLoadingEl);scrollMsgsToBottom();}
function hideChatLoading(){if(chatLoadingEl){try{chatLoadingEl.remove();}catch(e){}chatLoadingEl=null;}}
function closeUserConfirmCardHost(){if(userConfirmCardHost){try{userConfirmCardHost.remove();}catch(e){}userConfirmCardHost=null;}userConfirmBlocking=false;}

/* ===== Todo-List ===== */
function initTodoListElements(){
if(!todoListArea)return;
todoListBody=todoListArea.querySelector(".todo-list-body");
todoListCount=todoListArea.querySelector(".todo-list-count");
}
function showTodoList(){initTodoListElements();if(todoListArea){todoListArea.classList.remove("hidden");}}
function hideTodoList(){initTodoListElements();if(todoListArea){todoListArea.classList.add("hidden");}}
function renderTodoListFromEvent(ev,ownerCid){
initTodoListElements();
if(todoListArea&&todoListArea.style.display==="none"){todoListArea.style.display="";}
var items=Array.isArray(ev.items)?ev.items:[];
if(!items.length){if(ev.close&&todoListArea){todoListArea.style.display="none";todoListArea.classList.add("hidden");}hideTodoList();var _ocDn=normalizeConversationId(ownerCid||"");if(_ocDn){var _tDn=findConversationTab(_ocDn);if(_tDn){_tDn.todoUnread=false;if(typeof syncTodoUnreadBadgeForConversation==="function")syncTodoUnreadBadgeForConversation(_ocDn);}}return;}
showTodoList();
var doneCount=0;
var html="";
for(var i=0;i<items.length;i++){
var it=items[i];
var done=!!it.done;
if(done)doneCount++;
var cbClass="todo-cb"+(done?" done":"");
var txtClass="todo-text"+(done?" done":"");
html+='<div class="todo-item"><span class="'+cbClass+'"></span><span class="'+txtClass+'">'+escapeHtml(String(it.text||""))+'</span></div>';
}
if(todoListBody){var sc=todoListBody.querySelector(".todo-list-scroll");if(sc)sc.innerHTML=html;else todoListBody.innerHTML=html;}
if(todoListCount)todoListCount.textContent=doneCount+"/"+items.length;
if(ev.all_done&&todoListArea){todoListArea.style.borderLeft="3px solid #3daf3f";if(!todoListArea.querySelector(".todo-close-btn")){var cb=document.createElement("button");cb.className="todo-close-btn";cb.textContent="✕";cb.title="关闭清单";cb.onclick=function(){todoListArea.style.display="none";};var hd=todoListArea.querySelector(".todo-list-header");if(hd)hd.appendChild(cb);}}
else if(todoListArea){todoListArea.style.borderLeft="3px solid #a68b4a";var oldBtn=todoListArea.querySelector(".todo-close-btn");if(oldBtn)oldBtn.remove();}
if(ev.collapsed&&todoListArea){todoListArea.classList.add("collapsed");}
else if(ev.collapsed===false&&todoListArea){todoListArea.classList.remove("collapsed");}
if(ev.close&&todoListArea){todoListArea.style.display="none";}
var _owUr=normalizeConversationId(ownerCid||"");if(_owUr){if(ev.close){var _txUr=findConversationTab(_owUr);if(_txUr){_txUr.todoUnread=false;if(typeof syncTodoUnreadBadgeForConversation==="function")syncTodoUnreadBadgeForConversation(_owUr);}}else if(items.length&&_owUr!==normalizeConversationId(activeConversationId)){var _tyUr=findConversationTab(_owUr);if(_tyUr){_tyUr.todoUnread=true;if(typeof syncTodoUnreadBadgeForConversation==="function")syncTodoUnreadBadgeForConversation(_owUr);}}}
}
function escapeHtml(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
async function drainChatSseFromResponse(r,streamCid){
if(window.DEBUG){try{console.log("[SSE] 开始读流",{streamCid:String(streamCid||""),ok:r.ok,status:r.status,hasBody:!!(r&&r.body)});}catch(e){}}
if(!r||!r.body){if(window.DEBUG)console.error("[SSE] 响应无 body，无法读取流",{ok:r&&r.ok,status:r&&r.status});return;}
const rd=r.body.getReader(),de=new TextDecoder();let buf="";
let endedAwaitingUserConfirm=false;
for(;;){
const x=await rd.read();if(x.done){
if(window.DEBUG){try{console.log("[SSE] 流结束 EOF",{streamCid:String(streamCid||""),bufRemain:buf.length});}catch(e){}}
const sseCloseCid=normalizeConversationId(streamCid||"");if(!sseCloseCid){if(window.DEBUG)console.error("[SSE] 流结束：stream 绑定缺少有效 conversation_id，已跳过收尾渲染",{streamCid:String(streamCid||"")});break;}withConversationContext(sseCloseCid,function(){
if(endedAwaitingUserConfirm){hideChatLoading();return;}
if(!anyToolThisTurn&&!streamAssistantEl&&!lastLlm){hideChatLoading();}else if(toolOpen.size>0||pendingToolTags.length>0){
add("a","⚠️ **系统检测到意外断开连接。** 可能原因：网络波动、服务器繁忙、调用工具次数达到上限。部分工具已运行完毕（见右侧步骤面板），你可重新发起对话尝试恢复，或将复杂任务拆分为多步逐步执行。");
abortPendingToolTags();resetTurnState();hideChatLoading();if(lastLlm){finishLlmTitle(false);lastLlm.tag.className="tag bad";lastLlm.tag.textContent="截断";lastLlm=null;}
}
});
break;}
buf+=de.decode(x.value,{stream:true});
let i;while((i=buf.indexOf("\n\n"))>=0){
const blk=buf.slice(0,i);buf=buf.slice(i+2);
for(const line of blk.split("\n")){
if(line.indexOf("data:")!==0)continue;
const raw=line.slice(5).trim();let ev;try{ev=JSON.parse(raw);}catch(_jsonErr){if(window.DEBUG){console.warn("[SSE recv] JSON 解析失败",{error:String(_jsonErr&&_jsonErr.message||_jsonErr),sample:String(raw||"").slice(0,400)});console.error("[SSE] JSON 解析失败，已跳过本行（不渲染）",{error:String(_jsonErr&&_jsonErr.message||_jsonErr),sample:String(raw||"").slice(0,240)});}continue;}
if(window.DEBUG){try{console.log("[SSE recv]",{streamCid:String(streamCid||""),type:ev&&ev.type,conversation_id:ev&&ev.conversation_id,ev:ev});}catch(e){}}
const packetCid=normalizeConversationId(ev.conversation_id);if(!packetCid){if(window.DEBUG){console.warn("[SSE recv] 已丢弃（conversation_id 缺失或非法）",{streamCid:String(streamCid||""),type:ev&&ev.type,conversation_id:ev&&ev.conversation_id,ev:ev});console.error("[SSE] 数据包缺少或非法 conversation_id，已跳过渲染（不写入任何会话）",{type:ev&&ev.type,conversation_id:ev&&ev.conversation_id});}continue;}withConversationContext(packetCid,function(_ctxTab){if(ev.type==="conversation"){ensureConversationTab(packetCid);if(ev.mode)_ctxTab.selectedMode=normalizeMode(ev.mode);/* 服务端不推送 model（outbound 的 conversation 帧不含该字段）；
       此处不覆盖用户当场的选择。*/if(renderingContextVisible){if(ev.mode)applyMode(ev.mode);void ensureModelPricing();}}
else if(ev.type==="run_started"){_ctxTab.activeRunId=String(ev.run_id||"");}
else if(ev.type==="mode_changed"&&ev.mode){_ctxTab.selectedMode=normalizeMode(ev.mode);if(renderingContextVisible)applyMode(normalizeMode(ev.mode));}
else if(ev.type==="dispatch_title")addDispatchTitle(ev.title||"");
else if(ev.type==="llm_round")addLlmRound(ev.round);
else if(ev.type==="llm_request")onLlmRequest(ev);
else if(ev.type==="llm_response")onLlmResponse(ev);
else if(ev.type==="llm_done"){flushPendingToolTags();if(lastLlm){finishLlmTitle(true);lastLlm.tag.className="tag ok";lastLlm.tag.textContent="Done";}}
else if(ev.type==="usage"){const u=ev.usage||{};const inTok=Number(u.prompt_tokens??0)||0;const outTok=Number(u.completion_tokens??0)||0;const hitTok=Number(u.prompt_cache_hit_tokens??0)||0;const missTok=Number(u.prompt_cache_miss_tokens??0)||0;sessionTokenUsed+=Math.max(0,inTok+outTok);totalPromptTokens+=inTok;totalCompletionTokens+=outTok;totalCacheHitTokens+=hitTok;totalCacheMissTokens+=missTok;void ensureModelPricing();_updateUsageBottom();void persistUsageAccumulator();}
else if(ev.type==="context_layout"){_ctxTab.lastContextLayout=ev;setModelContextWindow(ev.model_max_context_tokens);if(renderingContextVisible&&packetCid===normalizeConversationId(activeConversationId))_updateUsageBottom();}
else if(ev.type==="tool_start")onToolStart(ev);
else if(ev.type==="tool_progress")onToolProgress(ev);
else if(ev.type==="tool_end"){onToolEnd(ev);if(ev.todo_list&&ev.todo_list_data){var _td=ev.todo_list_data;renderTodoListFromEvent({items:_td.items||[],all_done:Array.isArray(_td.items)&&_td.items.every(function(it){return !!it.done;}),collapsed:!!_td.collapsed,close:!!_td.close},packetCid);scrollToBottomAfterLayout(msgs,true);}}
else if(ev.type==="open_session"){var sid=normalizeConversationId(ev.session_id);if(sid){ensureConversationTab(sid);var _ot=findConversationTab(sid);if(_ot)_ot.title=ev.name||("会话 "+sid.slice(0,8));}}
else if(ev.type==="tool_preview_update"){var tid2=String(ev.tool_call_id||"").trim();if(tid2){var card=findStepCardForToolCall(tid2);if(card){var pb2=card.querySelector("pre.tool-res");if(pb2){try{var _pj2=JSON.parse(ev.preview||"{}");pb2.textContent=JSON.stringify(_pj2,null,2);}catch(e2){pb2.textContent=String(ev.preview||"");}var lb2=pb2.previousElementSibling;if(lb2&&lb2.classList&&lb2.classList.contains("lbl"))lb2.style.display="block";pb2.style.display="block";}var tag2=card.querySelector(".ch .tag");if(tag2){try{var _pj3=JSON.parse(ev.preview||"{}");if(_pj3&&_pj3.ok){tag2.textContent="Done";tag2.className="tag ok";}else{tag2.textContent="Fail";tag2.className="tag bad";}}catch(e3){}}}}}
else if(ev.type==="audio"){playAudio(packetCid||ev.conversation_id,ev.audio,ev.voice||"",ev._dbg||"");}
else if(ev.type==="assistant_delta"){if(anyToolThisTurn){flushPendingSteps();}appendAssistantDelta(ev.delta||"");}
else if(ev.type==="reasoning_delta")appendReasoningDelta(ev);
else if(ev.type==="reasoning_sync")applyReasoningSync(ev);
else if(ev.type==="assistant_markdown"){
if(anyToolThisTurn){flushPendingSteps();}
(function(){
var md=ev.markdown;if(typeof md!=="string"||!md.trim())return;
var e=ensureAssistantStreamBubble();if(!e)return;
if(streamAssistantText&&!streamAssistantText.endsWith("\n"))streamAssistantText+="\n";
streamAssistantText+=md.trim()+"\n";
e.innerHTML=renderMarkdown(streamAssistantText);
scrollMsgsToBottom();
})();
}
else if(ev.type==="assistant"){if(anyToolThisTurn){flushPendingSteps();}if(!finalizeAssistantStream(ev.content||"")){add("a",ev.content||"");}}
else if(ev.type==="done"){finalizeAssistantStream("");_clearServerRunning(packetCid);void refreshConversationTitle(packetCid);}
else if(ev.type==="stopped"){markCurrentTurnStoped();resetTurnState();hideChatLoading();if(ev.message)add("a",ev.message);_clearServerRunning(packetCid);}
else if(ev.type==="paused_for_user_confirm"){hideChatLoading();endedAwaitingUserConfirm=true;}
else if(ev.type==="todo_list"){renderTodoListFromEvent(ev,packetCid);scrollToBottomAfterLayout(msgs,true);}
else if(ev.type==="error"){hideChatLoading();abortPendingToolTags();if(lastLlm){finishLlmTitle(false);lastLlm.tag.className="tag bad";lastLlm.tag.textContent="Fail";lastLlm=null;}
if(!anyToolThisTurn){discardPendingSteps();}else{pendingStepEls=[];}
add("a","错误: "+JSON.stringify(ev.detail||ev));_clearServerRunning(packetCid);}
});
_routeEventBySource(ev);
}
}
}
}
function handleGlobalSseEvent(ev){
if(!ev||ev.type==="heartbeat"||ev.type==="global_sse_ready")return;
const packetCid=normalizeConversationId(ev.conversation_id);if(!packetCid)return;
withConversationContext(packetCid,function(_ctxTab){
if(ev.type==="conversation"){ensureConversationTab(packetCid);if(ev.mode)_ctxTab.selectedMode=normalizeMode(ev.mode);if(ev.model)_ctxTab.selectedModel=String(ev.model||"");if(renderingContextVisible){if(ev.mode)applyMode(ev.mode);if(ev.model)applyModel(ev.model);void ensureModelPricing();}}
else if(ev.type==="run_started"){_ctxTab.activeRunId=String(ev.run_id||"");_ctxTab.abortController=_ctxTab.abortController||{global:true};showChatLoading();}
else if(ev.type==="mode_changed"&&ev.mode){_ctxTab.selectedMode=normalizeMode(ev.mode);if(renderingContextVisible)applyMode(normalizeMode(ev.mode));}
else if(ev.type==="dispatch_title")addDispatchTitle(ev.title||"");
else if(ev.type==="llm_round")addLlmRound(ev.round);
else if(ev.type==="llm_request")onLlmRequest(ev);
else if(ev.type==="llm_response")onLlmResponse(ev);
else if(ev.type==="llm_done"){flushPendingToolTags();if(lastLlm){finishLlmTitle(true);lastLlm.tag.className="tag ok";lastLlm.tag.textContent="Done";}}
else if(ev.type==="usage"){const u=ev.usage||{};const inTok=Number(u.prompt_tokens??0)||0;const outTok=Number(u.completion_tokens??0)||0;const hitTok=Number(u.prompt_cache_hit_tokens??0)||0;const missTok=Number(u.prompt_cache_miss_tokens??0)||0;sessionTokenUsed+=Math.max(0,inTok+outTok);totalPromptTokens+=inTok;totalCompletionTokens+=outTok;totalCacheHitTokens+=hitTok;totalCacheMissTokens+=missTok;void ensureModelPricing();_updateUsageBottom();void persistUsageAccumulator();}
else if(ev.type==="context_layout"){_ctxTab.lastContextLayout=ev;setModelContextWindow(ev.model_max_context_tokens);if(renderingContextVisible&&packetCid===normalizeConversationId(activeConversationId))_updateUsageBottom();}
else if(ev.type==="tool_start")onToolStart(ev);
else if(ev.type==="tool_progress")onToolProgress(ev);
else if(ev.type==="tool_end"){onToolEnd(ev);if(ev.todo_list&&ev.todo_list_data){var _td=ev.todo_list_data;renderTodoListFromEvent({items:_td.items||[],all_done:Array.isArray(_td.items)&&_td.items.every(function(it){return !!it.done;}),collapsed:!!_td.collapsed,close:!!_td.close},packetCid);scrollToBottomAfterLayout(msgs,true);}}
else if(ev.type==="open_session"){var sid=normalizeConversationId(ev.session_id);if(sid){ensureConversationTab(sid);var _ot=findConversationTab(sid);if(_ot)_ot.title=ev.name||("会话 "+sid.slice(0,8));}}
else if(ev.type==="tool_preview_update"){var tid2=String(ev.tool_call_id||"").trim();if(tid2){var card=findStepCardForToolCall(tid2);if(card){var pb2=card.querySelector("pre.tool-res");if(pb2){try{var _pj2=JSON.parse(ev.preview||"{}");pb2.textContent=JSON.stringify(_pj2,null,2);}catch(e2){pb2.textContent=String(ev.preview||"");}var lb2=pb2.previousElementSibling;if(lb2&&lb2.classList&&lb2.classList.contains("lbl"))lb2.style.display="block";pb2.style.display="block";}}}}
else if(ev.type==="assistant_delta"){if(anyToolThisTurn){flushPendingSteps();}appendAssistantDelta(ev.delta||"");}
else if(ev.type==="reasoning_delta")appendReasoningDelta(ev);
else if(ev.type==="reasoning_sync")applyReasoningSync(ev);
else if(ev.type==="assistant_markdown"){if(anyToolThisTurn){flushPendingSteps();}var md=ev.markdown;if(typeof md==="string"&&md.trim()){var e=ensureAssistantStreamBubble();if(e){if(streamAssistantText&&!streamAssistantText.endsWith("\n"))streamAssistantText+="\n";streamAssistantText+=md.trim()+"\n";e.innerHTML=renderMarkdown(streamAssistantText);scrollMsgsToBottom();}}}
else if(ev.type==="assistant"){if(anyToolThisTurn){flushPendingSteps();}if(!finalizeAssistantStream(ev.content||"")){add("a",ev.content||"");}}
else if(ev.type==="peer_message"){addPeerMessage(ev.content||"",ev.sender_name||"",ev.sender||"");}
else if(ev.type==="inbox_queued"){add("a","已收到来自 "+(ev.from_name||ev.from||"其他 Agent")+" 的排队消息。");}
else if(ev.type==="audio"){playAudio(packetCid||ev.conversation_id,ev.audio,ev.voice||"",ev._dbg||"");}
else if(ev.type==="done"){finalizeAssistantStream("");_ctxTab.abortController=null;_ctxTab.activeRunId="";hideChatLoading();updateTaskControls();if(typeof renderChatTabs==="function")renderChatTabs();void refreshConversationTitle(packetCid);}
else if(ev.type==="stopped"){markCurrentTurnStoped();resetTurnState();hideChatLoading();if(ev.message)add("a",ev.message);_ctxTab.abortController=null;_ctxTab.activeRunId="";updateTaskControls();if(typeof renderChatTabs==="function")renderChatTabs();}
else if(ev.type==="paused_for_user_confirm"){hideChatLoading();}
else if(ev.type==="todo_list"){renderTodoListFromEvent(ev,packetCid);scrollToBottomAfterLayout(msgs,true);}
else if(ev.type==="error"){hideChatLoading();abortPendingToolTags();if(lastLlm){finishLlmTitle(false);lastLlm.tag.className="tag bad";lastLlm.tag.textContent="Fail";lastLlm=null;}if(!anyToolThisTurn){discardPendingSteps();}else{pendingStepEls=[];}add("a","错误: "+JSON.stringify(ev.detail||ev));_ctxTab.abortController=null;_ctxTab.activeRunId="";updateTaskControls();if(typeof renderChatTabs==="function")renderChatTabs();}
});
_routeEventBySource(ev);
}
function startGlobalSse(){
if(window.__aiAgentGlobalSse)return;
try{
var es=new EventSource("/api/events/stream");
window.__aiAgentGlobalSse=es;
es.onmessage=function(e){if(!e||!e.data)return;var ev;try{ev=JSON.parse(e.data);}catch(_err){return;}handleGlobalSseEvent(ev);};
es.onerror=function(){};
}catch(_e){}
}
function openUserConfirmModalFromToolEnd(ev, toolRow){
if(userConfirmCardHost||!ev.user_confirm_required)return;
userConfirmBlocking=true;
if(goBtn)goBtn.disabled=true;
hideChatLoading();
var opts=Array.isArray(ev.user_confirm_options)?ev.user_confirm_options:[];
var title=String(ev.user_confirm_title||"请确认");
var multi=!!ev.user_confirm_multi;
var tailIdx=opts.length;
var wrap=document.createElement("div");wrap.className="b a user-confirm-card-outer";
var card=document.createElement("div");card.className="chat-diff-card user-confirm-card";
var cap=document.createElement("div");cap.className="chat-diff-cap user-confirm-cap";
var capLine=document.createElement("div");capLine.className="user-confirm-cap-line";
var h=document.createElement("span");h.className="uc-title";h.textContent=title;
var badge=document.createElement("span");badge.className="user-confirm-badge";
badge.textContent=multi?"待确认·多选":"待确认·单选";
capLine.appendChild(h);capLine.appendChild(badge);cap.appendChild(capLine);card.appendChild(cap);
var body=document.createElement("div");body.className="user-confirm-body";
var btns=document.createElement("div");btns.className="user-confirm-opts";
var pickSingle=-1;
var pickMulti={};
var rows=[];
var customInputEl=null;
function syncRows(){
for(var si=0;si<rows.length;si++){
var R=rows[si];
var on=multi?!!pickMulti[R.idx]:pickSingle===R.idx;
R.icon.classList.toggle("uc-on",on);
R.row.classList.toggle("uc-row-picked",on);
}}
function toggleIdx(idx){
if(multi){if(pickMulti[idx]){delete pickMulti[idx];}else{pickMulti[idx]=1;}syncRows();}
else{pickSingle=(pickSingle===idx)?-1:idx;syncRows();}}
function buildFinal(){
var pref="自定义说明：";
if(multi){
var keys=Object.keys(pickMulti).map(function(x){return parseInt(x,10);}).filter(function(x){return !isNaN(x)&&x>=0&&x<=tailIdx;});
keys.sort(function(a,b){return a-b;});
if(!keys.length)return "";
var parts=[];
for(var ki=0;ki<keys.length;ki++){
var j=keys[ki];
if(j===tailIdx){var ex2=customInputEl?String(customInputEl.value||"").trim():"";if(ex2)parts.push(pref+ex2);}
else{parts.push(String(opts[j]||""));}
}
return parts.join("\n");
}
if(pickSingle<0||pickSingle>tailIdx)return "";
if(pickSingle===tailIdx){var ex=customInputEl?String(customInputEl.value||"").trim():"";return ex?pref+ex:"";}
return String(opts[pickSingle]||"");
}
function addRow(idx,label,isTail){
var row=document.createElement("div");
row.className="uc-opt-row"+(multi?" uc-multi":" uc-single")+(isTail?" uc-has-custom":"");
var icon=document.createElement("span");icon.className=multi?"uc-check":"uc-radio";icon.setAttribute("aria-hidden","true");
row.appendChild(icon);
if(isTail){
var inp=document.createElement("input");inp.type="text";inp.className="uc-opt-input";inp.placeholder="自定义说明";inp.autocomplete="off";customInputEl=inp;
inp.addEventListener("focus",function(){if(multi){pickMulti[idx]=1;}else{pickSingle=idx;}syncRows();});
row.appendChild(inp);
}else{
var lab=document.createElement("span");lab.className="uc-opt-label";lab.textContent=label;
row.appendChild(lab);
}
row.onclick=function(e){if(e.target&&e.target.closest&&e.target.closest(".uc-opt-input"))return;toggleIdx(idx);};
btns.appendChild(row);rows.push({row:row,icon:icon,idx:idx});
}
for(var oi=0;oi<opts.length;oi++){addRow(oi,String(opts[oi]),false);}
addRow(tailIdx,"",true);
syncRows();
body.appendChild(btns);
var act=document.createElement("div");act.className="user-confirm-actions";
var cancel=document.createElement("button");cancel.type="button";cancel.className="mode-plus";cancel.textContent="取消";
var ok=document.createElement("button");ok.type="button";ok.className="mode-plus";ok.textContent="确认";
act.appendChild(cancel);act.appendChild(ok);body.appendChild(act);
card.appendChild(body);wrap.appendChild(card);msgs.appendChild(wrap);userConfirmCardHost=wrap;scrollMsgsToBottom();
function cleanup(){closeUserConfirmCardHost();updateTaskControls();}
var submitUserConfirm=async function(finalTxt){
var confirmCid=getActiveConversationId();cleanup();showChatLoading();var gb=goBtn;if(gb)gb.disabled=true;var tab=findConversationTab(confirmCid);if(tab){tab.abortController={global:true};tab.stopRequested=false;}updateTaskControls();
try{
var r=await fetch("/api/chat/user-confirm",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:confirmCid,confirm:finalTxt,mode:selectedMode,model:selectedModel})});
if(!r.ok){var _bc="";try{_bc=await r.text();}catch(e){}if(window.DEBUG)console.error("[ai-agent] /api/chat/user-confirm 非 OK",{status:r.status,bodyHead:String(_bc||"").slice(0,500)});withConversationContext(confirmCid,function(){hideChatLoading();add("a","确认请求 HTTP "+r.status);});if(tab){tab.abortController=null;tab.activeRunId="";}return;}
var _jr=await r.json();if(tab&&_jr&&_jr.run_id)tab.activeRunId=String(_jr.run_id||"");if(_jr&&_jr.ok!==false&&toolRow){var picked=String(finalTxt||"").trim();if(typeof chatToolSetRowStatus==="function")chatToolSetRowStatus(toolRow, picked?"done":"bad");if(typeof chatToolSetResultText==="function")chatToolSetResultText(toolRow, picked||"用户取消了这次确认（未作答）");}
}catch(err){if(err&&err.name==="AbortError"){return;}withConversationContext(confirmCid,function(){hideChatLoading();add("a","确认请求失败: "+(err&&err.message?err.message:String(err)));});}
finally{updateTaskControls();}
};
cancel.onclick=function(){void submitUserConfirm("");};
ok.onclick=function(){void submitUserConfirm(buildFinal());};
}
function openApprovalModalFromToolEnd(ev, toolRow){
if(userConfirmCardHost||!ev.approval_required)return;
userConfirmBlocking=true;
if(goBtn)goBtn.disabled=true;
hideChatLoading();
var desc=String(ev.approval_desc||"").trim()||"（无描述）";
var wrap=document.createElement("div");wrap.className="b a user-confirm-card-outer";
var card=document.createElement("div");card.className="chat-diff-card user-confirm-card";
var cap=document.createElement("div");cap.className="chat-diff-cap user-confirm-cap";
var capLine=document.createElement("div");capLine.className="user-confirm-cap-line";
var h=document.createElement("span");h.className="uc-title";h.textContent="审批";
capLine.appendChild(h);cap.appendChild(capLine);card.appendChild(cap);
var body=document.createElement("div");body.className="user-confirm-body";
var p=document.createElement("div");p.className="approval-desc";p.textContent=desc;
body.appendChild(p);
var act=document.createElement("div");act.className="user-confirm-actions";
var reject=document.createElement("button");reject.type="button";reject.className="mode-plus";reject.textContent="驳回";
var agree=document.createElement("button");agree.type="button";agree.className="mode-plus approval-agree";agree.textContent="同意";
act.appendChild(reject);act.appendChild(agree);body.appendChild(act);
card.appendChild(body);wrap.appendChild(card);msgs.appendChild(wrap);userConfirmCardHost=wrap;scrollMsgsToBottom();
function cleanup(){closeUserConfirmCardHost();updateTaskControls();}
var submitApproval=async function(agreed){
var confirmCid=getActiveConversationId();cleanup();showChatLoading();var gb=goBtn;if(gb)gb.disabled=true;var tab=findConversationTab(confirmCid);if(tab){tab.abortController={global:true};tab.stopRequested=false;}updateTaskControls();
try{
var r=await fetch("/api/chat/user-confirm",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:confirmCid,approval:agreed?"agree":"reject",mode:selectedMode,model:selectedModel})});
if(!r.ok){var _bc="";try{_bc=await r.text();}catch(e){}if(window.DEBUG)console.error("[ai-agent] /api/chat/user-confirm 非 OK",{status:r.status,bodyHead:String(_bc||"").slice(0,500)});withConversationContext(confirmCid,function(){hideChatLoading();add("a","审批请求 HTTP "+r.status);});if(tab){tab.abortController=null;tab.activeRunId="";}return;}
var _jr=await r.json();if(tab&&_jr&&_jr.run_id)tab.activeRunId=String(_jr.run_id||"");if(_jr&&_jr.ok!==false&&toolRow){var decision=agreed?"同意":"不同意";var aid=String(_jr.approval_id||"").trim();if(typeof chatToolSetRowStatus==="function")chatToolSetRowStatus(toolRow,"done");if(typeof chatToolSetResultText==="function")chatToolSetResultText(toolRow,agreed&&aid?(decision+"\n"+aid):decision);}
}catch(err){if(err&&err.name==="AbortError"){return;}withConversationContext(confirmCid,function(){hideChatLoading();add("a","审批请求失败: "+(err&&err.message?err.message:String(err)));});}
finally{updateTaskControls();}
};
reject.onclick=function(){void submitApproval(false);};
agree.onclick=function(){void submitApproval(true);};
}
var conversationMount=document.getElementById("chatConversationMount");
if(!conversationMount){
var sec=document.querySelector("section.chat");
if(sec){
conversationMount=document.createElement("div");
conversationMount.id="chatConversationMount";
conversationMount.className="chat-conversation-mount";
var rowBlk=sec.querySelector(".row");
var tr=sec.querySelector(".chat-title-row");
if(tr&&rowBlk)sec.insertBefore(conversationMount,rowBlk);
else if(tr&&tr.nextSibling)sec.insertBefore(conversationMount,tr.nextSibling);
else sec.appendChild(conversationMount);
}
}
conversationMount&&conversationMount.classList.add("chat-conversation-mount");
const stepsRoot=document.getElementById("steps");let msgs=null,msgsRoot=null;let steps=stepsRoot;cid=document.getElementById("cid"),ta=document.getElementById("t"),slashPop=document.getElementById("slashPop"),sideTabbar=document.getElementById("sideTabbar"),sidePaneWrap=document.getElementById("sidePaneWrap"),hdrModel=document.getElementById("hdrModel"),modelPickerBtn=document.getElementById("modelPickerBtn"),modelPickerMenu=document.getElementById("modelPickerMenu"),modelPickerLabel=document.getElementById("modelPickerLabel"),chatTabs=document.getElementById("chatTabs");var _tBoot=getActiveTab();if(conversationMount&&_tBoot&&_tBoot.conversationPane){conversationMount.appendChild(_tBoot.conversationPane);msgsRoot=_tBoot.msgsHost;msgs=msgsRoot;todoListArea=_tBoot.todoArea;todoListBody=todoListArea?todoListArea.querySelector(".todo-list-body"):null;todoListCount=todoListArea?todoListArea.querySelector(".todo-list-count"):null;}if(cid)cid.textContent=getActiveConversationId().slice(0,8);
function moveChildrenToArray(el){var arr=[];if(!el)return arr;while(el.firstChild){arr.push(el.firstChild);el.removeChild(el.firstChild);}return arr;}
function restoreChildrenFromArray(el,arr){if(!el)return;el.innerHTML="";arr=Array.isArray(arr)?arr:[];for(var i=0;i<arr.length;i++){el.appendChild(arr[i]);}}
function isConversationBusy(){var t=getActiveTab();return !!(userConfirmBlocking||toolOpen.size||pendingToolTags.length||(t&&t.abortController));}
function isTabBusy(t){return !!(t&&(t.abortController||t.userConfirmBlocking||(t.toolOpen&&t.toolOpen.size)||((t.pendingToolTags||[]).length)));}
function saveRuntimeStateToTab(t){t.selectedMode=selectedMode;t.selectedModel=selectedModel;t.stepSeq=stepSeq;t.lastLlm=lastLlm;t.llmStreamBuffer=llmStreamBuffer;t.pendingToolTags=pendingToolTags;t.anyToolThisTurn=anyToolThisTurn;t.pendingStepEls=pendingStepEls;t.streamAssistantEl=streamAssistantEl;t.streamAssistantText=streamAssistantText;t.pendingDeltaSeparator=pendingDeltaSeparator;t.seenDispatchTitle=seenDispatchTitle;t.toolOpen=toolOpen;t.lastAnalysisTail=lastAnalysisTail;t.chatLoadingEl=chatLoadingEl;t.userConfirmCardHost=userConfirmCardHost;t.userConfirmBlocking=userConfirmBlocking;t.sessionTokenUsed=sessionTokenUsed;t.totalPromptTokens=totalPromptTokens;t.totalCompletionTokens=totalCompletionTokens;t.totalCacheHitTokens=totalCacheHitTokens;t.totalCacheMissTokens=totalCacheMissTokens;t.pricingCacheKey=pricingCacheKey;t.pricingRates=pricingRates;t.pricingFailed=pricingFailed;t.pricingLoading=pricingLoading;t.pricingInflight=pricingInflight;t.pricingFetchGen=pricingFetchGen;}
function loadRuntimeStateFromTab(t){selectedMode=t.selectedMode||selectedMode||"auto";selectedModel=t.selectedModel||selectedModel||"";stepSeq=Number(t.stepSeq||0);lastLlm=t.lastLlm||null;llmStreamBuffer=t.llmStreamBuffer||{round:null,reqHtml:"",resHtml:"",consumed:false};pendingToolTags=t.pendingToolTags||[];anyToolThisTurn=!!t.anyToolThisTurn;pendingStepEls=t.pendingStepEls||[];streamAssistantEl=t.streamAssistantEl||null;streamAssistantText=String(t.streamAssistantText||"");pendingDeltaSeparator=!!t.pendingDeltaSeparator;seenDispatchTitle=String(t.seenDispatchTitle||"");toolOpen=t.toolOpen instanceof Map?t.toolOpen:new Map();lastAnalysisTail=String(t.lastAnalysisTail||"");chatLoadingEl=t.chatLoadingEl||null;userConfirmCardHost=t.userConfirmCardHost||null;userConfirmBlocking=!!t.userConfirmBlocking;sessionTokenUsed=Number(t.sessionTokenUsed||0);totalPromptTokens=Number(t.totalPromptTokens||0);totalCompletionTokens=Number(t.totalCompletionTokens||0);totalCacheHitTokens=Number(t.totalCacheHitTokens||0);totalCacheMissTokens=Number(t.totalCacheMissTokens||0);pricingCacheKey=String(t.pricingCacheKey||"");pricingRates=t.pricingRates||null;pricingFailed=!!t.pricingFailed;pricingLoading=!!t.pricingLoading;pricingInflight=!!t.pricingInflight;pricingFetchGen=Number(t.pricingFetchGen||0);}
function moveVisibleToTab(t){while(stepsRoot.firstChild)t.stepsHost.appendChild(stepsRoot.firstChild);if(t.conversationPane&&conversationMount&&t.conversationPane.parentNode===conversationMount){conversationMount.removeChild(t.conversationPane);}saveRuntimeStateToTab(t);}
function moveTabToVisible(t){while(t.stepsHost.firstChild)stepsRoot.appendChild(t.stepsHost.firstChild);if(conversationMount&&t.conversationPane){while(conversationMount.firstChild){conversationMount.removeChild(conversationMount.firstChild);}conversationMount.appendChild(t.conversationPane);}msgsRoot=t.msgsHost;msgs=msgsRoot;todoListArea=t.todoArea;todoListBody=todoListArea?todoListArea.querySelector(".todo-list-body"):null;todoListCount=todoListArea?todoListArea.querySelector(".todo-list-count"):null;steps=stepsRoot;loadRuntimeStateFromTab(t);}
function saveActiveConversationView(){moveVisibleToTab(getActiveTab());}
/* 当前会话变了就广播一个事件：插件面板里带**会话级状态**的（勾选之类）要跟着重取。
   壳层不点名任何插件 —— 谁需要谁订阅，不知道这个事件的插件什么也不受影响。 */
function notifyConversationChanged(){
try{
document.dispatchEvent(new CustomEvent("ai-agent:conversation-changed",{detail:{conversation_id:getActiveConversationId()}}));
}catch(e){}
}
/* 标题写上标签时广播。侧边栏订阅后重拉会话名录。
   新会话的名录条目要等首次对话生成标题才出现，建标签当时拉不到。 */
function notifyConversationTitle(id){
try{
document.dispatchEvent(new CustomEvent("ai-agent:conversation-title",{detail:{conversation_id:id}}));
}catch(e){}
}
function restoreConversationView(t){moveTabToVisible(t);if(cid)cid.textContent=t.id.slice(0,8);applyMode(selectedMode);applyModel(selectedModel);if(typeof updateTaskControls==="function")updateTaskControls();_updateUsageBottom();scrollToBottom(stepsRoot,true);notifyConversationChanged();if(t&&t.historyLoaded){scrollToBottomAfterLayout(msgs,true);}}
function withConversationContext(conversationId,fn){var target=ensureConversationTab(conversationId);var prevTab=getActiveTab(),prevMsgs=msgs,prevSteps=steps,prevTodo=todoListArea,prevTodoBody=todoListBody,prevTodoCount=todoListCount,prevRenderingVisible=renderingContextVisible;saveRuntimeStateToTab(prevTab);renderingContextVisible=target.id===activeConversationId;if(target.id===activeConversationId){msgsRoot=target.msgsHost;msgs=msgsRoot;steps=stepsRoot;todoListArea=target.todoArea;todoListBody=todoListArea?todoListArea.querySelector(".todo-list-body"):null;todoListCount=todoListArea?todoListArea.querySelector(".todo-list-count"):null;}else{msgs=target.msgsHost;steps=target.stepsHost;todoListArea=target.todoArea;todoListBody=todoListArea?todoListArea.querySelector(".todo-list-body"):null;todoListCount=todoListArea?todoListArea.querySelector(".todo-list-count"):null;}loadRuntimeStateFromTab(target);try{return fn(target);}finally{saveRuntimeStateToTab(target);renderingContextVisible=prevRenderingVisible;msgs=prevMsgs;steps=prevSteps;todoListArea=prevTodo;todoListBody=prevTodoBody;todoListCount=prevTodoCount;loadRuntimeStateFromTab(prevTab);if(cid)cid.textContent=(prevTab?prevTab.id:activeConversationId).slice(0,8);if(typeof _updateUsageBottom==="function")_updateUsageBottom();}}
/* 布局（打开过哪些标签、激活哪一个）**只存本地**，不发服务端。
   「激活的是哪个会话」是**本浏览器的选择**，不是服务器的事实 —— 两个浏览器各自
   激活不同会话时，服务端一个全局字段表示不了，只会谁后写谁覆盖。 */
function persistConversationLayout(){storeConversationLayoutLocal();}
function repaintSessionRail(){var rail=document.getElementById("sessionRail");if(!chatSessionMenu||!rail||rail.classList.contains("is-collapsed")||!chatSessionMenu._sessions)return;renderSessionMenu(chatSessionMenu._sessions);}
function openConversationFromMenu(id,title){id=normalizeConversationId(id);if(!id)return;saveActiveConversationView();var t=ensureConversationTab(id);if(title)t.title=String(title).slice(0,80);t.todoUnread=false;activeConversationId=t.id;sessionId=t.id;conv=t.id;storeConversationId(t.id);restoreConversationView(t);renderChatTabs();persistConversationLayout();loadConversationHistory(t);repaintSessionRail();}
function renderSessionMenu(items){if(!chatSessionMenu)return;items=Array.isArray(items)?items:[];chatSessionMenu._sessions=items;chatSessionMenu.innerHTML="";if(!items.length){var emp=document.createElement("div");emp.className="chat-session-empty";emp.textContent="暂无历史会话";chatSessionMenu.appendChild(emp);return;}var lastGroup=null;items.forEach(function(s){var id=normalizeConversationId(s&&s.id);if(!id)return;var group=String(s.date_group||"");if(group&&group!==lastGroup){lastGroup=group;var gh=document.createElement("div");gh.className="chat-session-group";gh.textContent=group;chatSessionMenu.appendChild(gh);}else if(!group&&lastGroup!==null){lastGroup=null;}var opened=!!findConversationTab(id);var row=document.createElement("button");row.type="button";row.className="chat-session-row";row.title=id;var title=document.createElement("span");title.className="chat-session-title";title.textContent=String(s.title||("会话 "+id.slice(0,8)));row.appendChild(title);if(opened){var badge=document.createElement("span");badge.className="chat-session-badge";badge.textContent="已打开";row.appendChild(badge);}row.onclick=function(){openConversationFromMenu(id,title.textContent);};chatSessionMenu.appendChild(row);});}
var sessionRailListGen=0;
async function loadSessionRailList(quiet){if(!chatSessionMenu)return;var gen=++sessionRailListGen;if(!quiet)chatSessionMenu.innerHTML='<div class="chat-session-empty">加载中…</div>';try{var r=await fetch("/api/chat/sessions");var j=await r.json();if(gen!==sessionRailListGen)return;renderSessionMenu(j&&j.sessions||[]);}catch(e){if(gen!==sessionRailListGen)return;if(!quiet)chatSessionMenu.innerHTML='<div class="chat-session-empty">会话列表加载失败</div>';}}
async function toggleSessionMenu(){var rail=document.getElementById("sessionRail");if(!rail||!chatSessionMenu)return;if(!rail.classList.contains("is-collapsed")){if(typeof window._setSessionRailOpen==="function")window._setSessionRailOpen(false);return;}if(typeof window._setSessionRailOpen==="function")window._setSessionRailOpen(true);await loadSessionRailList();}
document.addEventListener("ai-agent:conversation-title",function(){var rail=document.getElementById("sessionRail");if(!rail||rail.classList.contains("is-collapsed"))return;void loadSessionRailList(true);});
function isDefaultConversationTitle(t){var s=String(t&&t.title||"");return !s||/^会话\s+[A-Za-z0-9_-]{8}$/.test(s)||s==="生成标题中…"||s==="新会话";}
async function refreshConversationTitle(id){var t=findConversationTab(id);if(!t||!isDefaultConversationTitle(t))return;t.title="生成标题中…";renderChatTabs();persistConversationLayout();try{var r=await fetch("/api/chat/title",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:id})});if(!r.ok)return;var j=await r.json();var title=String(j&&j.title||"").trim();if(title&&title!=="新会话"){var tt=findConversationTab(id);if(tt){tt.title=title.slice(0,18);renderChatTabs();persistConversationLayout();notifyConversationTitle(tt.id);}}else if(title==="新会话"){var t2=findConversationTab(id);if(t2&&t2.title==="生成标题中…"){t2.title="会话 "+id.slice(0,8);renderChatTabs();persistConversationLayout();notifyConversationTitle(t2.id);}}}catch(e){}}
function renderHistoryItems(items,conversationId){
items=Array.isArray(items)?items:[];
/* 必须用正在还原的会话 id，不能用当前激活 tab：多 tab 并行 loadHistory 时否则会把附件挂到错误 conversation_id → 404 */
var cid=normalizeConversationId(conversationId)||getActiveConversationId();
for(var i=0;i<items.length;i++){
var it=items[i]||{};
if(it.role==="user"){
var bubble=null;
if(it._sender&&it._sender!=="boss")addPeerMessage(String(it.content||""),String(it._sender_name||""),String(it._sender||""));
else bubble=add("u",String(it.content||""));
var atts=Array.isArray(it.attachments)?it.attachments:[];
if(atts.length&&window.AIA&&AIA.buildMsgAttachStrip&&bubble){
bubble.appendChild(AIA.buildMsgAttachStrip(cid,atts,null));
}else if(it.had_images&&bubble){
if(window.AIA&&AIA.appendHadImagesLostTip)AIA.appendHadImagesLostTip(bubble);
else appendHadImagesLostTip(bubble);
}
}else if(it.role==="think"){
renderHistoryThink(it);
}else if(it.role==="assistant"){
var ac=String(it.content||"").trim();
if(ac)add("a",ac);
}else if(it.role==="tool"){
/* 工具卡片回显：历史接口只返回 user/assistant 两种气泡，
   工具卡（尤其长跑的命令卡）不会随之重建。这里按同一份事实重建卡片，
   再把它在历史里累积的输出灌回去——与实时路径共用同一套渲染函数，
   避免"刷新前后长得不一样"。 */
renderHistoryToolItem(it);
}
}
}
/* 对话区的 diff 由工具展示自己画进展开面板，这里不另插卡片。 */
function renderDiffBubbleFromFacts(){
return false;
}
function renderHistoryThink(it){
if(!showToolItems())return;
var text=String(it&&it.content||"");
if(!text.trim())return;
var label="";
if(it.elapsed_ms!=null&&it.elapsed_ms!==""&&isFinite(Number(it.elapsed_ms)))label=chatThinkElapsedLabel(Number(it.elapsed_ms));
var row=makeChatToolRow("思考",label);
addChatToolPane(row._body,"",text,"think");
chatToolSyncStatusTitle(row);
appendChatToolRow(row);
}
function renderHistoryToolItem(it){
var ev={tool_call_id:String(it.tool_call_id||""),script:String(it.script||""),args:it.args||{}};
if(!ev.tool_call_id)return;
onToolStart(ev);
var o=toolOpen.get(ev.tool_call_id);
if(!o)return;
if(it.status==="canceled"){
onToolEnd({tool_call_id:ev.tool_call_id,ok:false,canceled:true,error:String(it.error||"已停止")});
}else if(it.status==="failed"){
onToolEnd({tool_call_id:ev.tool_call_id,ok:false,error:String(it.error||"执行失败")});
}else if(it.status==="suspended"){
/* 挂起（等用户在界面作答）：不标失败，保持"待确认"语义 */
var env=it.envelope||{};
if(env.kind==="approval"){
onToolEnd({tool_call_id:ev.tool_call_id,ok:true,approval_required:true,
approval_title:"审批",approval_desc:String(env.option_desc||""),
preview:it.envelope?JSON.stringify({data:it.envelope}):""});
}else{
onToolEnd({tool_call_id:ev.tool_call_id,ok:false,user_confirm_required:true,
preview:it.envelope?JSON.stringify({data:it.envelope}):""});
}
}else if(it.status==="done"){
/* `preview` 走实时帧**同一条**渲染路径（onToolEnd 内部就认它）：
   编辑类工具的 diff 卡片靠这一项重画 —— 不传它，刷新后 diff 整片消失。 */
onToolEnd({tool_call_id:ev.tool_call_id,ok:true,preview:String(it.preview||""),images:it.images||[]});
}
/* 输出放在状态之后：这样命令卡已经是"完成"态，输出仍然可见。 */
var out=String(it.output||"");
if(out&&o.liveOutPre&&o.liveOutPre.parentNode){o.liveOutPre.textContent=out;}
}
function appendHadImagesLostTip(mount){if(!mount)return;var tip=document.createElement("div");tip.className="attach-lost-tip";tip.textContent="图片预览已失效；若需再看请重新粘贴后发送。";mount.appendChild(tip);}
/* 从工具结果的 `data` 里取 unified diff 文本。
   编辑类工具返回 diff 的形状（逐个识别）：
     - `_change.diff`：replace_in_file / write_file / read_write 的改动信封（当前形态）
     - `diff`：file_undo(action="diff") 的版本比较结果
     - `_diff`：apply_patch 提交路径 / file_undo 的 undo 结果
     - `diffText` / `diff_text`：历史快照里的老名字
     - `files[]._change.diff`：apply_patch 预览把每文件 diff 放在数组里
   漏认一个的后果是：工具明明返回了 diff，界面却什么都不画
   （实时与刷新两条路径同时为空，而且不会有任何报错）。 */
function diffTextFromToolData(d){
if(!d||typeof d!=="object")return "";
if(d._change&&typeof d._change==="object"&&typeof d._change.diff==="string"&&d._change.diff.trim())return d._change.diff;
if(typeof d.diff==="string"&&d.diff.trim())return d.diff;
if(typeof d._diff==="string"&&d._diff.trim())return d._diff;
if(typeof d.diffText==="string"&&d.diffText.trim())return d.diffText;
if(typeof d.diff_text==="string"&&d.diff_text.trim())return d.diff_text;
/* apply_patch 预览：每个文件的改动在 `files[]` 里，拼成一份多段 unified diff。 */
if(Array.isArray(d.files)){
var parts=[];
for(var i=0;i<d.files.length;i++){var one=diffTextFromToolData(d.files[i]);if(one)parts.push(one);}
if(parts.length)return parts.join("\n");
}
return "";
}
function applyContextLayoutFromHistory(t,j){if(!t||!j)return;if(j.context_layout)t.lastContextLayout=j.context_layout;if(j.context_layout&&normalizeConversationId(t.id)===normalizeConversationId(activeConversationId))_updateUsageBottom();}
async function refreshConversationContextLayout(t){if(!t||!normalizeConversationId(t.id)||t.abortController)return;try{var r=await fetch("/api/chat/history?"+new URLSearchParams({conversation_id:t.id}));if(!r.ok)return;var j=await r.json();if(!j||j.ok!==true)return;applyContextLayoutFromHistory(t,j);}catch(e){}}
function scrollToBottomAfterLayout(el,force){if(!el)return;requestAnimationFrame(function(){requestAnimationFrame(function(){scrollToBottom(el,force);});});}
async function loadConversationHistory(t){if(!t||t.abortController)return;if(t.historyLoaded){void refreshConversationContextLayout(t);return;}t.historyLoaded=true;try{var r=await fetch("/api/chat/history?"+new URLSearchParams({conversation_id:t.id}));if(!r.ok)return;var j=await r.json();if(!j||j.ok!==true)return;var items=j.items||[];applyContextLayoutFromHistory(t,j);withConversationContext(t.id,function(){var isActive=normalizeConversationId(t.id)===normalizeConversationId(activeConversationId);if(j.todo_list&&j.todo_list.length){renderTodoListFromEvent({items:j.todo_list,all_done:j.todo_list.every(function(it){return !!it.done;}),collapsed:false},t.id);}else{hideTodoList();}if(items.length&&msgs.childNodes.length<=1){while(msgs.firstChild)msgs.removeChild(msgs.firstChild);renderHistoryItems(items,t.id);}else if(msgs.childNodes.length===0){renderHistoryItems(items,t.id);}if(isActive){scrollToBottomAfterLayout(msgs,true);}});}catch(e){}}
function _routeEventBySource(ev){var scid=ev&&ev._source_session;if(!scid)return;var cid=normalizeConversationId(scid);if(!cid)return;var tab=findConversationTab(cid);if(!tab)return;var t=ev.type;if(t==="assistant"){withConversationContext(cid,function(){var ac=String(ev.content||"").trim();if(ac){add("a",ac);scrollToBottomAfterLayout(msgs,true);}});}else if(t==="tool_start"){withConversationContext(cid,function(){onToolStart(ev);});}else if(t==="tool_end"){withConversationContext(cid,function(){onToolEnd(ev);if(ev.todo_list&&ev.todo_list_data){var _td=ev.todo_list_data;renderTodoListFromEvent({items:_td.items||[],all_done:Array.isArray(_td.items)&&_td.items.every(function(it){return !!it.done;}),collapsed:!!_td.collapsed,close:!!_td.close},cid);scrollToBottomAfterLayout(msgs,true);}});}else if(t==="todo_list"){if(ev.close){syncTodoUnreadBadgeForConversation(cid);}else if(ev.items){renderTodoListFromEvent({items:ev.items,all_done:Array.isArray(ev.items)&&ev.items.every(function(it){return !!it.done;}),collapsed:!!ev.collapsed,close:!!ev.close},cid);syncTodoUnreadBadgeForConversation(cid);}}else if(t==="context_layout"){var _t4=findConversationTab(cid);if(_t4)applyContextLayoutFromHistory(_t4,{context_layout:ev});}}
/* 开局只向服务端问一件事：**哪些会话在跑**（服务端权威，用于回填停止键）。
   标签列表与激活会话都来自本地 —— 本地没有就是新会话，不去服务端拉一个来激活。 */
async function restoreConversationLayoutFromServer(){
try{
var r=await fetch("/api/chat/ui-state");if(!r.ok)return;
var j=await r.json();var st=(j&&j.state)||{};
/* 把服务端权威的「在跑」落到各 tab 上（只在这一刻读一次） */
try{var _run=Array.isArray(st.running)?st.running:[];for(var _ri=0;_ri<_run.length;_ri++)_markServerRunning(_run[_ri]);if(_run.length)updateTaskControls();}catch(_e5){}
}catch(e){}
for(var i=0;i<conversationTabs.length;i++)loadConversationHistory(conversationTabs[i]);
}
function syncTodoUnreadBadgeForConversation(cid){cid=normalizeConversationId(cid||"");if(!cid)return;var tb=findConversationTab(cid);if(!tb||!chatTabs)return;var want=!!tb.todoUnread;var b;var ch=chatTabs.children;var ui=0;for(;ui<ch.length;ui++){if(ch[ui]&&ch[ui].getAttribute("data-tab-id")===cid){b=ch[ui];break;}}if(!b){if(typeof renderChatTabs==="function")renderChatTabs();return;}if(b.classList.contains("chat-tab-todo-unread")===want)return;b.classList.toggle("chat-tab-todo-unread",want);renderChatTabs._sig=null;}
function renderChatTabs(){if(!chatTabs)return;var sig=conversationTabs.map(function(t){return String(t.id)+"\t"+String(t.title||"")+"\t"+(t.id===activeConversationId?1:0)+"\t"+(t.todoUnread?1:0);}).join("|");if(renderChatTabs._sig===sig&&chatTabs.children.length===conversationTabs.length){var mz=conversationTabs.length;for(var zp=0;zp<mz;zp++){var el=chatTabs.children[zp];if(!el||el.getAttribute("data-tab-id")!==conversationTabs[zp].id)break;}if(zp===mz)return;}renderChatTabs._sig=sig;var wc=conversationTabs.length>1;var pi,tid,t,btn,lab,labT,cn,ft,cur,kj,nel,xc;for(pi=0;pi<conversationTabs.length;pi++){t=conversationTabs[pi];tid=t.id;cur=chatTabs.children[pi];if(cur&&cur.getAttribute("data-tab-id")===tid)continue;btn=null;if(cur){for(kj=pi;kj<chatTabs.children.length;kj++){if(chatTabs.children[kj]&&chatTabs.children[kj].getAttribute("data-tab-id")===tid){btn=chatTabs.children[kj];break;}}}if(!btn){for(kj=0;kj<chatTabs.children.length;kj++){if(chatTabs.children[kj]&&chatTabs.children[kj].getAttribute("data-tab-id")===tid){btn=chatTabs.children[kj];break;}}}if(!btn){nel=document.createElement("button");nel.type="button";nel.setAttribute("role","tab");nel.setAttribute("data-tab-id",tid);(function(cid){nel.onclick=function(){switchConversationTab(cid);};})(tid);lab=document.createElement("span");lab.className="chat-tab-label";nel.appendChild(lab);btn=nel;}chatTabs.insertBefore(btn,cur||null);}while(chatTabs.children.length>conversationTabs.length){chatTabs.removeChild(chatTabs.lastChild);}for(pi=0;pi<conversationTabs.length;pi++){t=conversationTabs[pi];tid=t.id;btn=chatTabs.children[pi];if(!btn)continue;labT=t.title||("会话 "+t.id.slice(0,8));cn="chat-tab"+((t.id===activeConversationId)?" active":"")+(t.todoUnread?" chat-tab-todo-unread":"");ft="标题: "+labT+"\n会话ID: "+t.id;lab=btn.querySelector(".chat-tab-label");if(lab&&lab.textContent!==labT)lab.textContent=labT;if(btn.className!==cn)btn.className=cn;if(btn.title!==ft)btn.title=ft;xc=btn.querySelector(".chat-tab-close");if(wc){if(!xc){xc=document.createElement("button");xc.type="button";xc.className="chat-tab-close";xc.textContent="×";xc.title="关闭会话";btn.appendChild(xc);}(function(cid2){xc.onclick=function(ev){ev.stopPropagation();closeConversationTab(cid2);};})(tid);}else{if(xc)xc.remove();}}}
function switchConversationTab(id){id=normalizeConversationId(id);if(!id)return;saveActiveConversationView();var t=findConversationTab(id);if(!t)return;t.todoUnread=false;activeConversationId=id;sessionId=id;conv=id;storeConversationId(id);restoreConversationView(t);renderChatTabs();persistConversationLayout();loadConversationHistory(t);}
function createConversationTab(){saveActiveConversationView();var t=makeConversationTab(newConversationId());conversationTabs.push(t);activeConversationId=t.id;sessionId=t.id;conv=t.id;storeConversationId(t.id);restoreConversationView(t);renderChatTabs();persistConversationLayout();repaintSessionRail();}
function closeConversationTab(id){id=normalizeConversationId(id);if(conversationTabs.length<=1)return;var idx=-1;for(var i=0;i<conversationTabs.length;i++){if(conversationTabs[i].id===id){idx=i;break;}}if(idx<0)return;if(isTabBusy(conversationTabs[idx])){alert("该会话正在响应或等待确认，请完成后再关闭。");return;}var wasActive=id===activeConversationId;var _closedT=conversationTabs[idx];conversationTabs.splice(idx,1);if(_closedT&&_closedT.conversationPane&&conversationMount&&_closedT.conversationPane.parentNode===conversationMount){try{conversationMount.removeChild(_closedT.conversationPane);}catch(_eM){}}if(wasActive){var next=conversationTabs[Math.max(0,idx-1)]||conversationTabs[0];activeConversationId=next.id;sessionId=next.id;conv=next.id;storeConversationId(next.id);restoreConversationView(next);}renderChatTabs();persistConversationLayout();repaintSessionRail();}
const modePlus=document.getElementById("modePlus"),modeMenu=document.getElementById("modeMenu"),modeChip=document.getElementById("modeChip"),modeChipText=document.getElementById("modeChipText"),modeChipClear=document.getElementById("modeChipClear"),goBtn=document.getElementById("go"),stopTaskBtn=document.getElementById("stopTask"),autoToggleBtn=document.getElementById("autoToggle"),chatMoreBtn=document.getElementById("chatMoreBtn"),chatSessionMenu=document.getElementById("chatSessionMenu");
var _autoEnabled=false;
function updateAutoToggleUI(){
if(!autoToggleBtn)return;
var g=_goalInfo||null;var st=g?String(g.status||""):"";var txt=g?String(g.text||"").trim():"";
/* 三态配色（与 CSS 里的 .goal-active / .goal-paused 对应）：
     进行中=暗金、已暂停=暗红、已达成或无目标=默认灰（不带类即回落基色）。
   按钮上不写状态字，靠颜色区分 —— 文字保持"目标"两字，宽度稳定不跳动。 */
autoToggleBtn.classList.toggle("goal-active",st==="active");
autoToggleBtn.classList.toggle("goal-paused",st==="paused");
autoToggleBtn.classList.toggle("active",st==="active"||(!g&&_autoEnabled));
if(txt){
var label=(st==="active"?"进行中":st==="paused"?"已暂停":st==="done"?"已达成":st);
autoToggleBtn.title="目标（"+label+"）"+(g&&g.rounds?(" · 已自动推进 "+g.rounds+" 轮"):"")+"：\n"+txt.slice(0,200)+"\n\n点击修改、暂停或删除";
}else{
autoToggleBtn.title="目标：设定后每轮结束自动用这段文案发起新一轮（点击设置）";
}}
/* 目标状态是**服务端权威**：页面打开时取一次，之后由 `goal` 工具的调用结果刷新。
   不在前端持久化 —— 目标属于会话，不属于这个浏览器标签页。 */
function renderGoalDialog(){
var cid=getActiveConversationId();if(!cid)return;
var g=_goalInfo||null;var st=g?String(g.status||""):"";
var label=(st==="active"?"进行中":st==="paused"?"已暂停":st==="done"?"已达成":"");
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}

var mask=el("div","goal-mask");
var box=el("div","goal-dialog");
/* 头部：标题 + 状态徽标 */
var head=el("div","goal-dialog-head");
head.appendChild(el("div","goal-dialog-title",g?"目标":"设定目标"));
if(g){
var badge=el("div","goal-badge "+st,label+(g.rounds?(" · 已推进 "+g.rounds+" 轮"):""));
head.appendChild(badge);
}
box.appendChild(head);
box.appendChild(el("div","goal-dialog-sub",
g?"每轮结束时会自动用这段文案发起新一轮；暂停或标记达成后停止。"
 :"写一句你想让它持续推进的事，之后每轮结束都会自动接着做。"));

var ta2=el("textarea");
ta2.value=g?String(g.text||""):"";
ta2.placeholder="例如：把登录页改成深色主题，并补一份改动说明";
box.appendChild(ta2);
box.appendChild(el("div","goal-dialog-hint","提示：可以随时在这里改文案；模型也能用 goal 工具自己创建或调整。"));

var row=el("div","goal-dialog-actions");
var onEsc=null;
function close(){
/* 监听必须在这里摘：只在"按 Escape"那条分支里摘的话，
   每次用按钮关掉弹窗都会留下一个监听（直到下次按 Escape 才清），
   开几次就积几个 —— 之后任何一次 Escape 会同时触发多个回调。 */
if(onEsc){try{document.removeEventListener("keydown",onEsc);}catch(e){}onEsc=null;}
try{mask.remove();}catch(e){}
try{box.remove();}catch(e){}
}
function post(body){return fetch("/api/chat/goal",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}).then(function(r){return r.json();}).catch(function(){return null;});}
function act(action,extra){
var body={conversation_id:cid,action:action};
if(extra)for(var k in extra)body[k]=extra[k];
post(body).then(function(j){
if(j&&j.goal){_goalInfo=j.goal;}else if(action==="delete"){_goalInfo=null;}
updateAutoToggleUI();close();
});
}
function addBtn(text,cls,fn){var b=el("button","goal-btn"+(cls?(" "+cls):""),text);b.type="button";b.onclick=fn;row.appendChild(b);return b;}

if(g&&st==="active")addBtn("暂停","",function(){act("pause");});
if(g&&st==="paused")addBtn("恢复","",function(){act("resume");});
if(g&&st!=="done")addBtn("标记达成","",function(){act("done");});
if(g)addBtn("删除","danger",function(){act("delete");});
addBtn("取消","",close);
var saveBtn=addBtn("保存","primary",function(){
var v=String(ta2.value||"").trim();
if(!v){ta2.focus();return;}
act("save",{text:v});
});
/* 空文案时禁用保存：让它自己说明"不能为空"，而不是点了没反应 */
function syncSave(){saveBtn.disabled=!String(ta2.value||"").trim();}
ta2.addEventListener("input",syncSave);syncSave();

box.appendChild(row);
document.body.appendChild(mask);document.body.appendChild(box);
/* 定位必须**在挂载之后**：`getBoundingClientRect()` 只有元素进了文档才有真实几何，
   提前量到的是 0，算出来的 left 全是错的（弹窗会跑到视口最左）。
   对齐的是**触发它的那个「目标」按钮**：
     - 竖直：贴着输入区上沿（按输入区实际高度算），输入框换行变高时自动抬高；
     - 水平：弹窗中线对齐按钮中线，再夹在视口内（按钮靠右时不顶出屏幕）。
   不用固定 right 值：按钮位置随输入区布局变化（有/无停止键都会挪）。 */
try{
var anchorBtn=(typeof autoToggleBtn!=="undefined"&&autoToggleBtn)?autoToggleBtn:null;
var aRect=anchorBtn&&anchorBtn.getBoundingClientRect?anchorBtn.getBoundingClientRect():null;
var composerEl=document.querySelector(".composer");
var cHeight=composerEl&&composerEl.getBoundingClientRect?composerEl.getBoundingClientRect().height:0;
if(cHeight>0)box.style.bottom=Math.round(cHeight+16)+"px";
if(aRect&&aRect.width){
box.style.transform="none";
box.style.left="0px";                        /* 先归零，量到真实宽度再定位 */
var boxW=box.getBoundingClientRect().width||560;
var vWidth=window.innerWidth||document.documentElement.clientWidth||0;
var wantLeft=aRect.left+(aRect.width/2)-(boxW/2);
var maxLeft=Math.max(8,vWidth-boxW-12);
box.style.left=Math.round(Math.min(Math.max(8,wantLeft),maxLeft))+"px";
}
}catch(e){}
mask.onclick=close;
try{ta2.focus();ta2.setSelectionRange(ta2.value.length,ta2.value.length);}catch(e){}
/* Ctrl/Cmd+Enter 直接保存 */
ta2.addEventListener("keydown",function(e){if((e.ctrlKey||e.metaKey)&&e.key==="Enter"){e.preventDefault();if(!saveBtn.disabled)saveBtn.click();}});
onEsc=function(e){if(e.key==="Escape"){close();}};document.addEventListener("keydown",onEsc);
}
/* 本会话的目标快照（服务端权威，页面打开取一次；此后由 goal 工具结果刷新） */
let _goalInfo=null;
let selectedMode="auto";let selectedModel="";let allowedModels=["deepseek-v4-pro","deepseek-v4-flash","deepseek-v4-flash-vision-exp","glm-5.2","glm-5v-turbo","local-model"];
let slashSelectedIndex=0;
/* **读服务端权威的"在跑"**。
   SSE 没有游标就**不回放**，所以"page1 先开跑、page2 才打开"或"跟跑中 F5"
   时，新页面收不到 `run_started` → 判不出忙、停止键永不出现 ——
   那个页面既发不出消息（点了必 409）也停不掉任务。
   数据来源：`/api/chat/ui-state` 的 `state.running`（服务端权威，来自 `RunRegistry`）。
   这里**只读一次**（页面首次打开那次布局恢复的响应里就带着它），
   **不轮询、不新增状态变量**；之后仍由 SSE 驱动。
   不维护"忙/闲"镜像，只复用既有的 `abortController` 槽位打一个**只读标记** `{server:true}`。 */
function _serverRunningCid(cid){var t=cid?findConversationTab(cid):null;return !!(t&&t.abortController&&t.abortController.server===true);}
/* 清掉「服务端说它在跑」的标记。
   `done`/`stopped`/`error` 三个分支清的是 `_ctxTab.abortController` ——
   那是**派发上下文**对应的 tab；而这个标记是页面首次打开时按 `/api/chat/ui-state`
   打在**当时那个 tab** 上的。中途接入的页面里两者不一定是同一个 tab
   （`_routeEventBySource` 会按来源改派），于是标记漏清 →
   **停止键永远挂着、发送键永远隐藏**。
   这里改用**帧自带的会话 id** 精确清，不依赖 `_ctxTab` 是谁。 */
function _clearServerRunning(id){var cid=normalizeConversationId(id);if(!cid)return;var t=findConversationTab(cid);if(t&&t.abortController&&t.abortController.server===true){t.abortController=null;t.activeRunId="";}}
function _markServerRunning(id){var cid=normalizeConversationId(id);if(!cid)return;var t=findConversationTab(cid);if(!t||t.abortController)return;t.abortController={server:true};}
function _stopServerRunningTab(t){if(!t)return;var cid=t.id;try{t.stopRequested=true;fetch("/api/chat/stop",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:cid,run_id:String(t.activeRunId||"")})}).catch(function(){});}catch(_e){}try{fetch("/api/chat/autonomous",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:cid,enabled:false})}).catch(function(){});}catch(_e2){}_autoEnabled=false;if(typeof updateAutoToggleUI==="function")updateAutoToggleUI();t.stopRequested=true;try{updateTaskControls();}catch(_e3){}try{renderChatTabs();}catch(_e4){}}
function updateTaskControls(){var t=getActiveTab();var canStop=!!(t&&t.abortController)||_autoEnabled;if(goBtn){goBtn.classList.toggle("hidden",canStop);goBtn.disabled=!canStop&&isConversationBusy();}if(stopTaskBtn){stopTaskBtn.classList.toggle("hidden",!canStop);stopTaskBtn.disabled=!canStop;}}
function stopCurrentTask(){var t=getActiveTab();var cid=t?t.id:getActiveConversationId();if(!t||!t.abortController){/* 服务端说这条会话在跑、但本页没有本地控制器（中途接入）→ 仍要**把停止请求发给服务端**，
   不能直接 return：否则点了停止什么都不发生。
   这里**不做** markCurrentTurnStoped：服务端才是权威，本地标记会与实际状态不符。 */
if(_serverRunningCid(t&&t.id)){_stopServerRunningTab(t);return;}
if(_autoEnabled&&cid){_autoEnabled=false;updateAutoToggleUI();fetch("/api/chat/autonomous",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:cid,enabled:false})}).catch(function(){});withConversationContext(cid,function(){markCurrentTurnStoped();resetTurnState();hideChatLoading();add("a","自主模式已停止。");});updateTaskControls();}return;}t.stopRequested=true;var rid=String(t.activeRunId||"");try{fetch("/api/chat/stop",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:t.id,run_id:rid})}).catch(function(){});}catch(_e){}/* 只有**真控制器**才 abort。`{server:true}` 是"服务端说它在跑"
       的标记（中途接入的页面没有本地控制器），对它调 abort 只会抛错被吞。 */
try{if(t.abortController&&typeof t.abortController.abort==="function")t.abortController.abort();}catch(_e2){}_autoEnabled=false;updateAutoToggleUI();try{fetch("/api/chat/autonomous",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:t.id,enabled:false})}).catch(function(){});}catch(_e3){}withConversationContext(t.id,function(){markCurrentTurnStoped();resetTurnState();hideChatLoading();add("a","任务已停止。");});t.abortController=null;t.activeRunId="";updateTaskControls();renderChatTabs();}

/* ---- @ 文件选择器 ---- */
var atSelectedIndex=-1;var atRestoreSelectPath=null;function atNormPath(s){return String(s||"").replace(/\\/g,"/").toLowerCase();}function getAtPop(){return document.getElementById("atPop");}function getAtList(){return document.getElementById("atList");}function getAtCurPath(){return document.getElementById("atCurPath");}function getAtUpBtn(){return document.getElementById("atUpBtn");}
function hideAtPop(){if(window.DEBUG)console.log("hideAtPop");var p=getAtPop();if(p){p.style.visibility="hidden";p.style.top="-99999px";p.setAttribute("aria-hidden","true");}atSelectedIndex=-1;atRestoreSelectPath=null;}
function atMentionActiveAtCursor(){var v=ta.value,sel=ta.selectionStart||0,before=v.slice(0,sel);var re=/(?:^|\s)@/g,m,last=null;while((m=re.exec(before))!==null)last=m;if(!last)return false;var atIdx=last.index+last[0].length-1;if(sel<=atIdx)return false;var seg=before.slice(atIdx+1,sel);if(/\s/.test(seg))return false;return true;}
function atLastTriggerIndexIn(t){var re=/(?:^|\s)@/g,m,last=-1;while((m=re.exec(t))!==null)last=m.index+m[0].length-1;return last;}
var ICON_MAP={txt:"📄",json:"📋",py:"🐍",java:"☕",html:"🌐",js:"📜",css:"🎨",xml:"📰",yml:"⚙️",yaml:"⚙️",properties:"🔧",sql:"🗄️",md:"📝",jpg:"🖼️",jpeg:"🖼️",png:"🖼️",gif:"🖼️",svg:"🖼️",bmp:"🖼️",xlsx:"📊",xls:"📊",docx:"📃",doc:"📃",pdf:"📕",pptx:"📽️",ppt:"📽️",zip:"📦",rar:"📦",exe:"⚙️",dll:"⚙️",log:"📋",csv:"📊",ts:"📜",tsx:"📜",jsx:"📜",vue:"📜",c:"📄",cpp:"📄",h:"📄",go:"📄",rs:"📄",kt:"📄",swift:"📄"};
function iconFor(ext){return ICON_MAP[ext]||"📄";}
async function loadAtDir(path){try{var resp=await fetch("/api/dir-browse?path="+encodeURIComponent(path||""));var data=await resp.json();renderAtList(data);}catch(e){atRestoreSelectPath=null;getAtList().innerHTML='<div class="at-item" style="color:#f66">加载失败: '+e.message+"</div>";}}
function renderAtList(data){getAtCurPath().textContent=data.current;getAtCurPath().dataset.parent=data.parent||"";getAtUpBtn().style.display=(!data.parent||data.parent===data.current)?"none":"";getAtList().innerHTML="";atSelectedIndex=-1;data.items.forEach(function(item,idx){var div=document.createElement("div");div.className="at-item"+(item.type==="dir"?" dir":"");div.id="atPop_item_"+idx;div.dataset.idx=idx;div.dataset.type=item.type;div.dataset.path=item.path;if(item.type==="dir")div.title="单击进入子目录；回车插入该目录路径";var icon=item.type==="dir"?"📁":iconFor(item.ext.replace(".",""));div.innerHTML='<span class="at-icon">'+icon+'</span><span class="at-name">'+item.name+"</span>";div.addEventListener("click",function(){if(item.type==="dir"){loadAtDir(item.path);}else{selectAtFile(item.path);}});div.addEventListener("mouseenter",function(){atSelectedIndex=idx;updateAtSelection();});getAtList().appendChild(div);});var pick=0;if(atRestoreSelectPath){var want=atRestoreSelectPath;atRestoreSelectPath=null;for(var rj=0;rj<data.items.length;rj++){if(data.items[rj].type==="dir"&&atNormPath(data.items[rj].path)===atNormPath(want)){pick=rj;break;}}}if(data.items&&data.items.length){atSelectedIndex=pick;updateAtSelection();}}
function updateAtSelection(){var items=getAtList().querySelectorAll(".at-item");items.forEach(function(it,idx){it.classList.toggle("selected",idx===atSelectedIndex);});}
function selectAtFile(fpath){var before=ta.value.slice(0,ta.selectionStart||0);var after=ta.value.slice(ta.selectionStart||0);var atIdx=atLastTriggerIndexIn(before);if(atIdx>=0){ta.value=before.slice(0,atIdx)+"@"+fpath+" "+after;}else{ta.value=before+"@"+fpath+" "+after;}hideAtPop();ta.focus();}
if(getAtUpBtn())getAtUpBtn().addEventListener("click",function(){var cur=getAtCurPath().textContent.trim();var parentStored=getAtCurPath().dataset.parent||"";if(!parentStored)return;var p=parentStored||cur.substring(0,cur.lastIndexOf("/"));if(!p||p.length<3){if(p&&p.length===2&&p.charAt(1)===":"){p=p+"/";}else{p=cur;}}if(p!==cur)atRestoreSelectPath=cur;loadAtDir(p);});
function showAtPop(){if(window.DEBUG)console.log("showAtPop");var p=getAtPop();if(!p)return;atSelectedIndex=-1;atRestoreSelectPath=null;loadAtDir("");p.style.visibility="visible";p.style.top="-306px";p.setAttribute("aria-hidden","false");}
/* ---- @ 文件选择器结束 ---- */
function hideSlashPop(){if(slashPop){slashPop.classList.add("hidden");slashPop.setAttribute("aria-hidden","true");}}
function positionSlashPop(){if(!ta||!slashPop)return;var rect=ta.getBoundingClientRect();var before=ta.value.slice(0,ta.selectionStart||0);var lineStart=before.lastIndexOf("\n")+1;var col=before.length-lineStart;var cs=getComputedStyle(ta);var fz=parseFloat(cs.fontSize)||13;var lh=parseFloat(cs.lineHeight);if(!isFinite(lh)||lh<=0)lh=fz*1.35;var padL=parseFloat(cs.paddingLeft)||4;var padT=parseFloat(cs.paddingTop)||2;var chW=fz*0.55*Math.max(col,0);var lines=(before.match(/\n/g)||[]).length;var x=rect.left+padL+chW+6;var y=rect.top+padT+lines*lh-slashPop.offsetHeight-6;if(y<8)y=rect.bottom+4;var maxx=window.innerWidth-slashPop.offsetWidth-8;x=Math.min(Math.max(8,x),maxx);slashPop.style.position="fixed";slashPop.style.left=x+"px";slashPop.style.top=y+"px";}
function autoResizeTextarea(){if(!ta)return;ta.style.height="auto";var maxH=parseInt(getComputedStyle(ta).maxHeight)||320;var newH=Math.min(ta.scrollHeight,maxH);ta.style.height=newH+"px";ta.style.overflowY=ta.scrollHeight>maxH?"auto":"hidden";}
function normalizeMode(v){const t=String(v||"auto").toLowerCase();return (t==="plan"||t==="execute"||t==="auto")?t:"auto";}
function applyMode(v){hideSlashPop();selectedMode=normalizeMode(v);const label=(selectedMode==="auto"?"Auto":(selectedMode==="plan"?"Plan":"Execute"));if(modePlus){modePlus.textContent=label+" +";modePlus.classList.remove("plan","execute");if(selectedMode==="plan")modePlus.classList.add("plan");if(selectedMode==="execute")modePlus.classList.add("execute");}if(modeChip){modeChip.classList.add("hidden");}if(modeChipText){modeChipText.textContent="";}}
function closeModeMenu(){modeMenu.classList.add("hidden");}
let reasoningEffort="max";let reasoningBtn=document.getElementById("reasoningBtn");let reasoningMenu=document.getElementById("reasoningMenu");let reasoningLabel=document.getElementById("reasoningLabel");
function applyReasoningEffort(effort){if(effort!=="high"&&effort!=="max")return;reasoningEffort=effort;if(reasoningLabel){reasoningLabel.textContent=effort==="high"?"High":"Max";/* 颜色走类名，**不写死值**：写死的是深色主题的那一套，切到白天模式
   就会变成"暗金文字压在浅底上"（对比度极差）。
   `effort-max` 只是给 CSS 一个钩子，两套主题各自决定怎么画。 */
reasoningLabel.style.color="";
reasoningBtn.style.borderColor="";
reasoningBtn.classList.toggle("effort-max",effort==="max");
reasoningBtn.classList.toggle("effort-high",effort!=="max");}if(reasoningMenu){var cs=reasoningMenu.querySelectorAll(".reasoning-choice");cs.forEach(function(c){c.classList.remove("reasoning-current");if(c.dataset.effort===effort)c.classList.add("reasoning-current");});}
var cid=activeConversationId;if(cid){fetch("/api/reasoning-effort",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:cid,effort:effort})}).catch(function(){});}}
function closeReasoningMenu(){if(reasoningMenu)reasoningMenu.classList.add("hidden");}
function initReasoningPicker(){if(!reasoningBtn||!reasoningMenu)return;
reasoningBtn.onclick=function(e){e.stopPropagation();closeModeMenu();closeModelPicker();reasoningMenu.classList.toggle("hidden");};
if(modelPickerBtn)modelPickerBtn.onclick=function(e){e.stopPropagation();closeModeMenu();closeReasoningMenu();toggleModelPicker();};
reasoningMenu.onclick=function(e){var t=e.target;if(!t||typeof t.closest!=="function")return;var btn=t.closest("[data-effort]");if(!btn||!btn.dataset)return;if(btn.dataset.effort){applyReasoningEffort(btn.dataset.effort);closeReasoningMenu();}};
document.addEventListener("click",function(e){if(reasoningMenu&&!reasoningMenu.classList.contains("hidden")&&!reasoningBtn.contains(e.target)&&!reasoningMenu.contains(e.target))closeReasoningMenu();});
fetch("/api/reasoning-effort?conversation_id="+encodeURIComponent(activeConversationId||"")).then(function(r){return r.json();}).then(function(d){if(d&&d.reasoning_effort)applyReasoningEffort(d.reasoning_effort);}).catch(function(){});}

function initModePicker(){
if(!modePlus||!modeMenu||!modeChip||!modeChipClear)return;
modePlus.onclick=function(e){e.stopPropagation();closeReasoningMenu();closeModelPicker();modeMenu.classList.toggle("hidden");};
modeMenu.onclick=function(e){
var t=e.target;if(!t||typeof t.closest!=="function")return;
var btn=t.closest("[data-mode],[data-action],[data-model]");
if(!btn||!btn.dataset)return;
if(btn.dataset.mode){applyMode(btn.dataset.mode);closeModeMenu();closeModelPicker();return;}

};
/* 模型选项的委派处理器 —— 选项在独立的 `#modelPickerMenu` 里。
   处理器必须挂在容器上而不是模式菜单上，
   否则点选项没有任何反应（`modeMenu.onclick` 收不到那些点击）。 */
if(modelPickerMenu){
modelPickerMenu.onclick=function(e){
var t=e.target;if(!t||typeof t.closest!=="function")return;
var btn=t.closest("[data-model]");
if(!btn||!btn.dataset||!btn.dataset.model)return;
applyModel(btn.dataset.model);closeModelPicker();
};
}
modeChipClear.onclick=function(e){e.stopPropagation();applyMode("auto");};
document.addEventListener("click",function(e){
if(!modeMenu.contains(e.target)&&e.target!==modePlus)closeModeMenu();
closeModelPicker();
if(slashPop&&!slashPop.classList.contains("hidden")&&!slashPop.contains(e.target)&&e.target!==ta)hideSlashPop();
});
applyMode("auto");
}
/* 模型选择是 composer 里的**独立下拉**（`#modelPicker`），与模式菜单平级、开合互不依赖。 */
function openModelPicker(){
if(!modelPickerMenu||!modelPickerBtn)return;
modelPickerMenu.classList.remove("hidden");
modelPickerBtn.setAttribute("aria-expanded","true");
}
function closeModelPicker(){
if(!modelPickerMenu||!modelPickerBtn)return;
modelPickerMenu.classList.add("hidden");
modelPickerBtn.setAttribute("aria-expanded","false");
}
function toggleModelPicker(){
if(!modelPickerMenu)return;
if(modelPickerMenu.classList.contains("hidden"))openModelPicker();else closeModelPicker();
}
function applyModel(m){
var x=String(m||"").trim();if(allowedModels.indexOf(x)<0)return;
if(selectedModel!==x){pricingRates=null;pricingFailed=false;pricingCacheKey="";}
selectedModel=x;
var hm=document.getElementById("hdrModel");if(hm)hm.textContent="模型: "+selectedModel;
if(modelPickerLabel)modelPickerLabel.textContent=selectedModel||"默认";
/* 选择**只活在前端**：不写服务端、也不由服务端推送覆盖。
   每轮请求把当时的 `selectedModel` 随消息带给后端，后端只认那一刻的值。 */
document.querySelectorAll(".model-choice").forEach(function(b){if(b&&b.dataset&&b.dataset.model)b.classList.toggle("model-current",b.dataset.model===selectedModel);});
if(conv)void ensureModelPricing();
}
function selectSidePane(name){
document.querySelectorAll(".side-tab").forEach(function(el){el.classList.toggle("active",el.dataset.pane===name);});
document.querySelectorAll(".side-pane").forEach(function(el){el.classList.toggle("active",el.dataset.pane===name);});
}
/* 通用面板容器：标签与面板都按 `data-pane` 驱动，新增面板不必改这里。
   面板要能被插件注入，所以标签与面板都按 `data-pane` 数据驱动，加面板不必改这里。
   就必须是**按数据**遍历而不是按名字写死。

   `opts.pinned` 的面板不显示关闭按钮（步骤栏就是这种）。
   `opts.onOpen` 在每次激活时调用，供面板刷新自己的内容。 */
function openPane(opts){
var id=String(opts&&opts.id||"").trim();
if(!id||!sideTabbar||!sidePaneWrap)return null;
var title=String(opts.title||id);
var ex=document.getElementById("pane-"+id);
if(!ex){
ex=document.createElement("div");
ex.className="side-pane";
ex.id="pane-"+id;
ex.dataset.pane=id;
/* `openPane` 建的面板**不建标题行**：标题已经在标签上（同一个 `title`），再写一行是重复。
   固定面板（步骤栏）不同 —— 它不参与开/关，自带标题行是有意的。
   正文容器**始终建**：面板可以只给 `onOpen` 自己填内容（文件查看器就是这样），
   只在传了 `html` 时才建会让 `onOpen` 找不到容器、静默什么都不渲染。 */
var bodyEl=document.createElement("div");
bodyEl.className="pane-body";
if(opts.html!=null)bodyEl.innerHTML=String(opts.html);
ex.appendChild(bodyEl);
sidePaneWrap.appendChild(ex);
}
if(!document.getElementById("tab-"+id)){
var w=document.createElement("button");
w.type="button";
w.className="side-tab";
w.id="tab-"+id;
w.dataset.pane=id;
w.setAttribute("role","tab");
w.tabIndex=0;
var sp=document.createElement("span");
sp.textContent=title;
sp.style.flex="1";
w.appendChild(sp);
if(!opts.pinned){
var x=document.createElement("button");
x.type="button";
x.className="tab-x";
x.textContent="×";
x.title="关闭";
x.addEventListener("click",function(ev){ev.stopPropagation();closePane(id);});
w.appendChild(x);
}
w.addEventListener("click",function(ev){if(ev.target&&ev.target.classList&&ev.target.classList.contains("tab-x"))return;selectSidePane(id);});
sideTabbar.appendChild(w);
}
selectSidePane(id);
/* 广播"面板已打开"：插件脚本在开屏就被预载（段色注册要赶在第一次渲染前），
   那时面板 DOM 还不存在，脚本里的首次渲染必然是空跑。而脚本**只载一次**
   （`_pluginScriptsLoaded` 去重），开面板时不会再执行一遍 ——
   不广播这一下，面板就永远停在初始占位（"加载知识库…"）。
   插件自己监听这个事件决定渲染什么，壳层不点名任何插件。 */
try{
document.dispatchEvent(new CustomEvent("ai-agent:panel-opened",{detail:{
plugin:String((opts&&opts.plugin)||""),
panel:id
}}));
}catch(e){}
if(typeof opts.onOpen==="function")opts.onOpen(ex);
syncClassicSide();
return ex;
}
/* 步骤开关关闭时，步骤标签藏在样式里，不占右栏。其余标签都算打开。 */
function countOpenSideTabs(){
var tabs=document.querySelectorAll("#sideTabbar .side-tab");
var n=0;
for(var i=0;i<tabs.length;i++){
if(tabs[i].id==="tabSteps"&&typeof showToolSteps==="function"&&!showToolSteps())continue;
n++;
}
return n;
}
function syncClassicSide(){
if(typeof window._setClassicSideOpen==="function")window._setClassicSideOpen(countOpenSideTabs()>0);
}
function closePane(id){
var t=document.getElementById("tab-"+id);
if(t)t.remove();
var p=document.getElementById("pane-"+id);
if(p)p.remove();
var tabs=document.querySelectorAll(".side-tab");
var next=null;
for(var i=0;i<tabs.length;i++){
if(!showToolSteps()&&tabs[i].id==="tabSteps")continue;
next=tabs[i];
break;
}
if(next)selectSidePane(next.dataset.pane);
else if(showToolSteps())selectSidePane("steps");
else selectSidePane("");
syncClassicSide();
}
/* 插件 API 客户端：面板脚本经它调**自己插件的端点**，不必知道 URL 前缀。
   插件改名、端点挪位置都不影响脚本 —— 前缀由壳层拼。

   用法（面板脚本里）：
     const api = window.aiAgentPlugins.for(window.aiAgentPluginCurrent);
     await api.get("files");
     await api.post("generate", { prompt: "..." });
     await api.put("checked", { conversation_id, checked });
     await api.del("tasks/t-1");
*/
function pluginApi(plugin){
var name=String(plugin||"");
function call(method,path,payload){
var rel=String(path||"").replace(/^\/+/,"");
var url="/api/plugin/"+encodeURIComponent(name)+"/"+rel;
var opts={method:method,headers:{}};
if(payload!==undefined){
opts.headers["Content-Type"]="application/json";
opts.body=JSON.stringify(payload);
}
return fetch(url,opts).then(function(r){
return r.json().catch(function(){return {ok:r.ok,status:r.status};})
.then(function(data){return {status:r.status,ok:r.ok&&data&&data.ok!==false,data:data};});
});
}
return {
plugin:name,
url:function(path){return "/api/plugin/"+encodeURIComponent(name)+"/"+String(path||"").replace(/^\/+/,"");},
get:function(path,params){
var q="";
if(params&&typeof params==="object"){
var parts=[];
for(var k in params){if(Object.prototype.hasOwnProperty.call(params,k)&&params[k]!=null)parts.push(encodeURIComponent(k)+"="+encodeURIComponent(params[k]));}
if(parts.length)q="?"+parts.join("&");
}
return call("GET",path+q);
},
post:function(path,payload){return call("POST",path,payload===undefined?{}:payload);},
put:function(path,payload){return call("PUT",path,payload===undefined?{}:payload);},
del:function(path){return call("DELETE",path);}
};
}
/* 上下文分层的插件钩子：插件注册自己那一段的颜色/段名，宿主只按 key 取用。 */
var ctxSegmentHooks={};
var _ctxSegColors={};
var _ctxSegColorCache={};
function registerCtxSegment(plugin,opts){
var name=String(plugin||"").replace(/^plugin:/,"");
if(!name)return;
ctxSegmentHooks[name]=Object.assign({},ctxSegmentHooks[name]||{},opts||{});
}
function ctxSegmentLabel(key){
var m=/^plugin:(.+)$/.exec(String(key||""));
var h=m?ctxSegmentHooks[m[1]]:null;
return h&&h.label?String(h.label):"";
}
window.aiAgentPlugins={for:pluginApi,ctxSegments:{register:registerCtxSegment}};
/* 面板脚本只加载一次。脚本里读 `window.aiAgentPluginCurrent` 就知道自己属于哪个插件。 */
var _pluginScriptsLoaded={};
function loadPluginScript(url,plugin){
var u=String(url||"").trim();
if(!u||_pluginScriptsLoaded[u])return Promise.resolve(false);
_pluginScriptsLoaded[u]=true;
return new Promise(function(resolve){
var s=document.createElement("script");
s.src=u;
s.setAttribute("data-plugin-script",String(plugin||""));
s.onload=function(){resolve(true);};
s.onerror=function(){resolve(false);};
document.head.appendChild(s);
});
}
/* 面板样式表同样只注入一次，且**在面板打开时才注入** ——
   插件的样式随面板按需注入：壳层公共样式表里没有它们，插件没打开时也不会被加载。 */
var _pluginStylesLoaded={};
function loadPluginStyle(url,plugin){
var u=String(url||"").trim();
if(!u||_pluginStylesLoaded[u])return Promise.resolve(false);
_pluginStylesLoaded[u]=true;
return new Promise(function(resolve){
var l=document.createElement("link");
l.rel="stylesheet";
l.href=u;
l.setAttribute("data-plugin-style",String(plugin||""));
l.onload=function(){resolve(true);};
l.onerror=function(){resolve(false);};
document.head.appendChild(l);
});
}
/* 插件贡献的面板清单与动作清单（`/api/panels`、`/api/actions`）。
   页面只按数据建标签、面板与按钮，不为任何插件加分支 —— 加插件不必改前端。 */
var pluginPanels=[];
var pluginActions=[];
function pluginPanel(plugin,panelId){
var key=String(plugin||"")+":"+String(panelId||"");
for(var i=0;i<pluginPanels.length;i++){
var p=pluginPanels[i];
if(String(p.plugin)+":"+String(p.id)===key)return p;
}
return null;
}
/* 插件脚本在开屏就依次预载：脚本里的段色注册必须赶在上下文条渲染之前 ——
   注册晚于渲染时那一段只能先按兜底色画，用户会看到"颜色对不上"。
   面板**样式**仍旧按需（面板打开时才注入），内容渲染也仍在面板脚本里。 */
function preloadPluginScripts(){
var list=pluginPanels.slice();
function next(){
if(!list.length)return Promise.resolve(false);
var def=list.shift();
if(!def||!def.script)return next();
var owner=String(def.plugin||"");
/* 脚本读全局知道自己属于哪个插件，所以**串行**加载：并行会互相覆盖这个值。 */
window.aiAgentPluginCurrent=owner;
return loadPluginScript(def.script,owner).then(next);
}
return next();
}
function loadPluginPanels(){
return fetch("/api/panels").then(function(r){return r.json();}).then(function(d){
pluginPanels=(d&&Array.isArray(d.panels))?d.panels:[];
return pluginPanels;
}).catch(function(){pluginPanels=[];return pluginPanels;});
}
/* 按插件声明的动作清单渲染输入区按钮：没有声明就没有按钮，
   插件入口由声明决定，页面里没有写死的入口。 */
function renderPluginActions(){
var host=document.getElementById("pluginActions");
if(!host)return;
host.innerHTML="";
for(var i=0;i<pluginActions.length;i++){
(function(act){
var b=document.createElement("button");
b.type="button";
b.className="mode-plus plugin-action";
b.setAttribute("data-plugin",String(act.plugin||""));
b.setAttribute("data-action",String(act.id||""));
if(act.title)b.title=String(act.title);
b.textContent=String(act.label||act.id||"");
b.addEventListener("click",function(){openPluginPanel(act.plugin,act.panel||act.id);});
host.appendChild(b);
})(pluginActions[i]);
}
}
function loadPluginActions(){
return fetch("/api/actions").then(function(r){return r.json();}).then(function(d){
pluginActions=(d&&Array.isArray(d.actions))?d.actions:[];
renderPluginActions();
return pluginActions;
}).catch(function(){pluginActions=[];renderPluginActions();return pluginActions;});
}
/* 打开插件声明的面板：HTML 片段与标题都取自清单。 */
function openPluginPanel(plugin,panelId){
var def=pluginPanel(plugin,panelId);
var id=String(panelId||"").trim();
if(!id)return null;
return openPane({
id:id,
title:(def&&def.title)||id,
html:def?def.html:"",
pinned:!!(def&&def.pinned),
plugin:String(plugin||""),
onOpen:function(pane){
/* 面板脚本与样式按需加载各一次；`aiAgentPluginCurrent` 让脚本知道自己的插件名，
   从而用 `window.aiAgentPlugins.for(...)` 拿到带前缀的 API，不必自己拼 URL。
   面板内容的渲染**全在插件脚本里** —— 壳层不认任何插件的面板 id。 */
window.aiAgentPluginCurrent=String(plugin||"");
if(def&&def.style)void loadPluginStyle(def.style,plugin);
if(def&&def.script)void loadPluginScript(def.script,plugin);
}
});
}
/* 右栏文件查看器：按需建面板，同一个文件复用同一个面板。
   数据来自 `/api/fs/read`（内核早就为右栏准备好了）：`kind=text` 给 `content`/`lang`，
   `kind=table` 给 `sheets[{name,rows}]`，`kind=binary` 给 `message`。 */
/* 文件大小：按量级给 KB / MB / GB，字节数不再直接示人（`1921 字节` 读不出量级）。
   小于 1 KB 仍是字节。
   **先四舍五入再定单位**：反过来（先定单位再舍入）在边界上会给出 `1024 KB`
   —— 1023.999 KB 舍入成 1024 却没升到 MB。 */
function formatFileSize(n){
/* 一律 KB 起：文件面板是给人扫一眼量级的，混杂"字节"会让同一列里两种单位并存。
   小于 1 KB 的显示成小数 KB（`288 字节` → `0.3 KB`）。 */
var v=Number(n);
if(n==null||!isFinite(v)||v<0)return"";
var units=["KB","MB","GB","TB"];
var i=-1;
do{v/=1024;i++;}while(v>=1023.95&&i<units.length-1);
return (v>=100?Math.round(v):Math.round(v*10)/10)+" "+units[i];
}
function renderTableSheets(sheets){
var out="";
for(var i=0;i<sheets.length;i++){
var sh=sheets[i]||{};
var rows=Array.isArray(sh.rows)?sh.rows:[];
out+='<div class="pane-sheet"><div class="pane-sheet-name">'+escapeHtml(String(sh.name||("Sheet"+(i+1))))+"</div>";
out+='<table class="pane-sheet-tb">';
for(var r=0;r<rows.length;r++){
var cells=Array.isArray(rows[r])?rows[r]:[];
var tag=(r===0&&rows.length>1)?"th":"td";
out+="<tr>";
for(var c=0;c<cells.length;c++)out+="<"+tag+">"+escapeHtml(String(cells[c]))+"</"+tag+">";
out+="</tr>";
}
out+="</table></div>";
}
return out||'<div class="pane-empty">（空表）</div>';
}
function renderFilePane(body,path){
/* 文件查看器的内容自带边距：面板容器**不给内边距**（边距归内容），
   所以这里给自己打个类让样式表能定位到。 */
if(body)body.className="pane-body pane-file";
body.innerHTML='<div class="pane-empty">读取中…</div>';
fetch("/api/fs/read?path="+encodeURIComponent(path)).then(function(r){return r.json();}).then(function(d){
if(!d||d.error){
body.innerHTML='<div class="pane-empty">打开失败：'+escapeHtml(String((d&&d.error)||"未知错误"))+"</div>";
return;
}
/* 元信息行只放**属性**（大小 / 截断 / 刷新），不再放路径 ——
   路径在面板标题里，同一句话写两遍是冗余。 */
var meta='<div class="pane-meta">';
if(d.size!=null){var _sz=formatFileSize(d.size);if(_sz)meta+="<span>"+_sz+"</span>";}
if(d.truncated)meta+="<span>已截断</span>";
meta+='<button type="button" class="pane-btn" data-pane-refresh>刷新</button></div>';
var kind=String(d.kind||"text");
var inner;
if(kind==="binary"){
inner='<div class="pane-empty">'+escapeHtml(String(d.message||"二进制文件不在此处预览"))+"</div>";
}else if(kind==="table"){
inner=(d.message?'<div class="pane-empty">'+escapeHtml(String(d.message))+"</div>":"")
+renderTableSheets(Array.isArray(d.sheets)?d.sheets:[]);
}else{
inner='<pre class="file-view">'+highlightCode(String(d.content!=null?d.content:""),String(d.lang||""))+"</pre>";
}
body.innerHTML=meta+inner;
var btn=body.querySelector("[data-pane-refresh]");
if(btn)btn.addEventListener("click",function(){renderFilePane(body,path);});
}).catch(function(){body.innerHTML='<div class="pane-empty">读取失败</div>';});
}
function openFileTab(path){
var p=String(path||"").trim();
if(!p)return null;
var id=filePaneId(p);
return openPane({
id:id,
/* 标题用**文件名**：完整路径由面板里的元信息行给出，两处都写路径就是重复。 */
title:baseNameOnly(p)||p,
pinned:false,
onOpen:function(pane){
var body=pane.querySelector(".pane-body");
if(body)renderFilePane(body,p);
}
});
}
/* 知识库面板的渲染逻辑**属于 knowledge 插件**（`plugins/knowledge/ui/panel.js`），
   面板打开时由壳层按 `_asset` 路由加载并执行。壳层不掺和它的取数与勾选。 */
/* **会话级模型回填**。
   `loadHealthModel()` 只给"全局默认模型"，而会话可能选过别的；
   它又跑在 `restoreConversationLayoutFromServer()` **之前**，此刻 `activeConversationId`
   还可能不是真正要显示的那个会话 —— 那样模型会被设成默认、刷新后选择丢失。
   所以必须**先恢复会话，再按那个会话取会话级设置**。 */
async function loadConversationModel(){
try{
var cidNow=normalizeConversationId(activeConversationId);if(!cidNow)return;
var r=await fetch("/api/chat/ui-state?conversation_id="+encodeURIComponent(cidNow));
if(!r.ok)return;var j=await r.json();
var st=(j&&j.state)||j||{};
if(Array.isArray(st.available_models)&&st.available_models.length){
allowedModels.splice(0,allowedModels.length);
st.available_models.forEach(function(m){if(allowedModels.indexOf(m)<0)allowedModels.push(m);});
}
if(typeof renderModelChoices==="function")renderModelChoices();
if(st.model)applyModel(st.model);
/* 目标与模型同源：页面打开时按**当前会话**取一次（服务端权威）。
   与模型选择同一道理 —— 目标属于会话，不属于这个标签页。 */
if(Object.prototype.hasOwnProperty.call(st,"goal")){_goalInfo=st.goal||null;}
if(st.autonomy&&typeof st.autonomy.enabled==="boolean"){_autoEnabled=!!st.autonomy.enabled;}
updateAutoToggleUI();
}catch(e){}
}
async function loadHealthModel(){
try{var r=await fetch("/health");if(!r.ok)return;var j=await r.json();if(Array.isArray(j.allowed_models)&&j.allowed_models.length){allowedModels.splice(0,allowedModels.length);j.allowed_models.forEach(function(m){if(allowedModels.indexOf(m)<0)allowedModels.push(m);});}if(j.model)applyModel(j.model);if(typeof renderModelChoices==="function")renderModelChoices();}catch(e){}
}
function renderModelChoices(){
if(!modelPickerMenu)return;modelPickerMenu.innerHTML="";allowedModels.forEach(function(m){var b=document.createElement("button");b.type="button";b.className="mode-item model-choice";b.dataset.model=m;b.setAttribute("role","option");b.textContent=(m==="local-model"?"🌐 ":"")+m;modelPickerMenu.appendChild(b);});if(modelPickerLabel&&selectedModel)modelPickerLabel.textContent=selectedModel;document.querySelectorAll(".model-choice").forEach(function(b){if(b&&b.dataset&&b.dataset.model)b.classList.toggle("model-current",b.dataset.model===selectedModel);});
}
function initKbAndSlashUi(){
if(ta&&slashPop){
slashPop.addEventListener("click",function(e){
var b=e.target.closest(".slash-item");if(!b)return;e.stopPropagation();hideSlashPop();ta.value="";
var s=b.getAttribute("data-slash");if(s==="auto")applyMode("auto");else if(s==="plan")applyMode("plan");else if(s==="execute")applyMode("execute");
});
ta.addEventListener("keyup",function(e){if(e.isComposing)return;if(e.key==="Escape"){hideSlashPop();hideAtPop();return;}
if(e.key==="/"&&document.activeElement===ta&&ta.value==="/"){var ci=slashPop.children;for(var i=0;i<ci.length;i++){ci[i].classList.remove("selected");ci[i].style.display=(ci[i].dataset.slash===selectedMode?"none":"");}for(var i=0;i<ci.length;i++){if(ci[i].style.display!=="none"){ci[i].classList.add("selected");slashSelectedIndex=i;break;}}updateSlashPopHints();positionSlashPop();slashPop.classList.remove("hidden");slashPop.setAttribute("aria-hidden","false");}
});
ta.addEventListener("input",function(){autoResizeTextarea();var ap=getAtPop();var vis=ap&&ap.style.visibility!=="hidden";if(atMentionActiveAtCursor()&&(!ap||!vis)){showAtPop();}else if(vis&&!atMentionActiveAtCursor()){hideAtPop();}if(ta.value!=="/")hideSlashPop();});
document.addEventListener("mousedown",function(ev){var ap2=getAtPop();if(!ap2||ap2.style.visibility==="hidden")return;if(ap2.contains(ev.target))return;hideAtPop();},true);
}
/* 输入区按钮全部来自插件声明，页面不再有写死的插件入口 */
/* `@文件` 引用的点击：从 `.msgs` 委托，避免给每个 chip 单独绑事件。
   链接默认行为要拦掉 —— 否则浏览器会把它当普通 `<a>` 去跳转。 */
document.addEventListener("click",function(ev){
var el=ev.target;
while(el&&el!==document){
if(el.classList&&el.classList.contains("file-ref")){
var p=el.getAttribute("data-file-path")||"";
if(p){ev.preventDefault();openFileTab(p);}
return;
}
if(el.tagName==="A"){
var fp=filePathFromHref(el.getAttribute("href")||"");
if(fp){
if(ev.button===0&&!ev.metaKey&&!ev.ctrlKey&&!ev.shiftKey&&!ev.altKey){ev.preventDefault();openFileTab(fp);}
return;
}
}
el=el.parentNode;
}
});
}
function updateSlashPopHints(){
var items=slashPop.querySelectorAll(".slash-item");var visibles=[];
for(var i=0;i<items.length;i++){if(items[i].style.display!=="none")visibles.push(items[i]);}
if(!visibles.length)return;var selIdx=-1;
for(var i=0;i<visibles.length;i++){if(visibles[i].classList.contains("selected")){selIdx=i;break;}}
if(selIdx<0){visibles[0].classList.add("selected");selIdx=0;}
for(var i=0;i<visibles.length;i++){
var sh=visibles[i].querySelector(".sh");if(!sh)continue;
var sk=(visibles[i].dataset.slash||"").charAt(0).toUpperCase();
var hint;
if(i===selIdx)hint="Enter";
else if(i<selIdx)hint="↑ + Enter";
else hint="↓ + Enter";
sh.textContent=sk+"  "+hint;
}
}

function escapeHtml(s){
return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function highlightJson(s){
if(window.codeHighlight)return window.codeHighlight.highlightCode(s,'json');
var t=String(s||'');try{var o=JSON.parse(t);t=JSON.stringify(o,null,2);}catch(e){}
return t.replace(/("(?:\\.|[^"\\])*")\s*:/g,'<span style="color:#ce9178;">$1</span>:')
.replace(/:\s*("(?:\\.|[^"\\])*")/g,':<span style="color:#ce9178;">$1</span>')
.replace(/:\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g,':<span style="color:#b5cea8;">$1</span>')
.replace(/:\s*(true|false|null)/g,':<span style="color:#569cd6;">$1</span>');}
function highlightCode(s,lang){
if(window.codeHighlight)return window.codeHighlight.highlightCode(s,lang);
var t=String(s||'');
if(String(lang||'').toLowerCase()==='json'||(!lang&&/^\s*[\[{]/.test(t)))return highlightJson(t);
return escapeHtml(t);
}
function detectScriptLang(code,hint){
if(window.codeHighlight)return window.codeHighlight.detectScriptLang(code,hint);
return 'python';
}
function hljsCodeClass(lang){
if(window.codeHighlight)return window.codeHighlight.hljsCodeClass(lang);
return '';
}
/* markdown 渲染用 `marked`（`js/vendor/marked.min.js`，内联在共用脚本里）。
   自研块渲染器的问题在**块级语义**：`<li>` 里不产出 `<p>`，松散列表的段距整段丢失；
   表格 / 任务清单 / 嵌套列表也各有偏差。markdown 的块级规则细节多，交给成熟实现。

   `breaks` 保持 CommonMark 默认（false）：模型输出的长段在源里是**软换行**，
   按硬换行渲染会把整段切成一行一断的碎片。段落靠空行（`\n\n`）分隔。

   代码围栏**不走 marked**：`renderMarkdown()` 先把围栏切出去交给既有逻辑
   （diff 卡片 / hljs 高亮），只把散文块交到这里。 */

/* 本地媒体文件的绝对路径 → 浏览器能取的 URL。
   两条路由，按路径落在哪选：
     · 工作区内（路径里有 `workspace` 段）→ `/workspace/<rel>`
       静态路由根是 `data/workspace`（web.py 的 `/workspace/` 路由）。
       取**最后**一个 `workspace` 段之后的部分：更靠前的目录也可能同名。
     · 其余本地绝对路径（正文里任意位置的本地图片 / 音频 / 视频）→ `/api/media?path=`
       它的根是各盘根，按 `mimetypes` 出类型，不做扩展名白名单。
   裸本地路径不能直接当 `src`：浏览器不认，图会破。
   `file://` 前缀先剥掉 —— 它对 `<img src>` 同样没用。 */
function localAbsPath(p){
var s=String(p||"").trim().replace(/\\/g,"/");
s=s.replace(/^file:\/+/i,"");
return /^[a-zA-Z]:\//.test(s)?s:"";
}
function workspaceRelPath(p){
var s=localAbsPath(p);
if(!s)return "";
var m=s.match(/^(?:.*\/)?workspace\/(.+)$/i);
return m?m[1]:"";
}
function markedImageHref(href){
var raw=String(href||"");
var rel=workspaceRelPath(raw);
if(rel)return "/workspace/"+rel;
var abs=localAbsPath(raw);
if(abs)return "/api/media?path="+encodeURIComponent(abs);
return raw;
}
function markedIsVideo(url){
return /\.(mp4|mov|webm|avi)(\?|$)/i.test(String(url||""));
}
/* 音频/视频扩展名。这类本地路径当**链接**给出时（如 `[播放音频](D:\...\a.mp3)`），
   也要转成 `/api/media`，否则点开是死链。
   只认媒体扩展名：文本文件（.md/.py 等）的本地路径链接另有文件查看路由，
   不能在这里一并改掉。 */
function markedIsMediaFile(url){
return /\.(mp4|mov|webm|avi|mp3|wav|m4a|aac|flac|ogg|png|jpe?g|gif|webp|bmp)(\?|$)/i.test(String(url||""));
}
/* 正文里的 `@<绝对路径>` → 可点击引用，点了在右栏打开该文件。
   这是**展示层**的事：composer 里插入的仍是 `@<路径>` 纯文本（模型认这个格式），
   这里只把它渲染成一个 chip。 */
/* 正文里的本地文件链接：盘符路径进右栏，外链与站内地址留给浏览器。 */
function filePathFromHref(href){
var s=String(href||"").trim();
if(!s||/^(?:https?:|mailto:|#|\/)/i.test(s))return "";
s=s.replace(/^file:\/+/i,"");
try{s=decodeURIComponent(s);}catch(e){}
if(/^[A-Za-z]:[\\/]/.test(s))return s;
return "";
}
function filePaneId(path){
/* 用路径哈希做面板 id：文件名可能含中文/空格/超长，直接进 id 会有麻烦 */
var s=String(path||"").replace(/\\/g,"/").toLowerCase();
var h=0;
for(var i=0;i<s.length;i++){h=(h*31+s.charCodeAt(i))|0;}
return "file-"+Math.abs(h).toString(36)+"-"+s.length.toString(36);
}
function shortFilePath(path){
var s=String(path||"").replace(/\\/g,"/");
var parts=s.split("/").filter(Boolean);
return parts.length<=2?s:(parts[parts.length-2]+"/"+parts[parts.length-1]);
}
/* 识别「文件路径」写法。模型经常把路径写成行内代码（`` `E:\test.txt` ``），
   那种没有 `@` 前缀，靠 atFileExtension 认不出来。

   判据要严：`agent/mechanisms/quality_gate.py` 这类相对路径也可能是**行内代码里的
   代码引用**，一律变成 chip 会把正文里的普通代码引用也点成文件面板。
   所以只认**盘符开头的绝对路径**（`E:\…` / `E:/…`），且必须带扩展名。 */
var _WIN_PATH_RE=/^@?([A-Za-z]:[\\/][^\s`<>"|?*]*\.[A-Za-z0-9]{1,8})$/;
function absoluteFilePathOf(s){
var t=String(s||"").trim();
var m=_WIN_PATH_RE.exec(t);
return m?m[1]:"";
}
function fileRefHtml(path,keepAt){
var p=String(path||"");
var label=(keepAt?"@":"")+shortFilePath(p);
return '<a class="file-ref" data-file-path="'+escapeHtml(p)+'" title="'+escapeHtml(p)+'">'+escapeHtml(label)+"</a>";
}
var _atFileExt=null;
/* 用户输入里的 `@<路径>` 也要能点开。
   用户消息走 `textContent`（纯文本，不过 markdown），所以这里做一次**只认文件引用**的
   轻量转换：先把整段转义，再把 `@<盘符路径>` 换成 chip。
   不整段跑 markdown —— 用户输入里的 `*`、`_`、`#` 是字面内容，不该被解释。 */
function linkifyUserText(s){
var t=String(s==null?"":s);
var esc=escapeHtml(t);
return esc.replace(/@([A-Za-z]:[\\/][^\s`<>"|?*]+)/g,function(_all,p){
return fileRefHtml(p,true);
});
}
function atFileExtension(){
if(_atFileExt)return _atFileExt;
_atFileExt={
name:"atFileRef",
level:"inline",
/* 只认 `@` 后紧跟盘符路径（`E:/x` `E:\x`）：相对路径与邮箱（`a@b.com`）都不碰。
   `start` 把解析位置前移到 `@`，否则 marked 会先把 `@` 当普通文本吃掉。 */
start:function(src){
var m=/(^|\s)@[A-Za-z]:[\\/]/.exec(src);
if(!m)return undefined;
return m.index+(m[1]?m[1].length:0);
},
tokenizer:function(src){
var m=/^@([A-Za-z]:[\\/][^\s`<>"|?*]+)/.exec(src);
if(!m)return undefined;
return {type:"atFileRef",raw:m[0],path:m[1],tokens:[]};
},
renderer:function(token){
var p=String(token.path||"");
return fileRefHtml(p,true);
}
};
return _atFileExt;
}
/* 行内代码里的绝对路径也变成可点 chip。
   `marked.use({renderer})` 收的是**对象**（键为渲染方法名），不是函数 ——
   传函数会静默什么都不注册。返回 `false` 时回落默认渲染。 */
var _codespanExt=null;
function filePathCodespanExtension(){
if(_codespanExt)return _codespanExt;
_codespanExt={
codespan:function(token){
var p=absoluteFilePathOf(token&&token.text);
if(!p)return false;
return fileRefHtml(p,/^@/.test(String(token.text||"").trim()));
}
};
return _codespanExt;
}
/* markdown 输出的消毒。
   解析器对**原始 HTML 直通**，而且它的 `html:false` 选项实测不起作用（三种配置都直通），
   所以防线只能做在渲染之后。

   做法是**元素级白名单**，不是字符串黑名单：逐个标签过，白名单外的标签**转义成文本**。
   黑名单挡不住 `<ScRiPt>`、`<script/x>`、`<svg/onload=…>` 这类变体 —— 漏一个就是执行。
   白名单只收渲染器自己会产出的标签（含 `markedRenderer` 产出的 `<video>`），
   正文里的原始 HTML 全被转义，想放新标签必须显式加进来。 */
var _SAFE_TAGS={
a:1,p:1,br:1,hr:1,em:1,strong:1,del:1,s:1,code:1,pre:1,blockquote:1,
ul:1,ol:1,li:1,table:1,thead:1,tbody:1,tr:1,th:1,td:1,
h1:1,h2:1,h3:1,h4:1,h5:1,h6:1,img:1,video:1,source:1,span:1,input:1
};
/*: 这些属性名一出现就拆掉（`on*` 之外的危险项） */
/*: 白名单内的属性名（原样保留）。任务清单的复选框要 `type`/`checked`/`disabled`。 */
var _SAFE_ATTR_EXACT={href:1,src:1,alt:1,title:1,class:1,id:1,colspan:1,rowspan:1,
type:1,checked:1,disabled:1,value:1,name:1,width:1,height:1,controls:1,loop:1,muted:1,poster:1,preload:1};
var _SAFE_ATTR_PREFIX=["data-","aria-"];
var _UNSAFE_HREF=/^\s*(?:javascript|vbscript|data|file)\s*:/i;
/*: 属性名以 `on` 开头即事件处理器 */
var _EVENT_ATTR=/^on/i;

function _safeUrlValue(raw){
var v=String(raw==null?"":raw);
/* 实体写法绕行（`java&#115;cript:`）：去掉实体与控制字符后再判 */
var plain=v.replace(/&#x?[0-9a-f]+;?/gi,"").replace(/[\s\u0000-\u0020]/g,"");
return !_UNSAFE_HREF.test(plain);
}
function _cleanTagAttrs(attrs){
var out=[];
/* 先归一化空白：解析器会把属性拆到多行（`<input checked=""\n  type="checkbox">`），
   带换行的属性串会让下面的逐属性识别漏掉它们。 */
var flat=String(attrs||"").replace(/\s+/g," ");
/* 值可以是空串（`checked=""`）—— 用 `*` 而不是 `+`，否则空值配不上、
   引号被当成裸值，后面整串属性跟着错位。 */
flat.replace(/([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*(?:=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g,
function(all,name,dq,sq,bare){
var lower=String(name||"").toLowerCase();
if(!lower)return "";
var allowed=_SAFE_ATTR_EXACT[lower]===1;
if(!allowed){
for(var i=0;i<_SAFE_ATTR_PREFIX.length;i++){if(lower.indexOf(_SAFE_ATTR_PREFIX[i])===0){allowed=true;break;}}
}
if(!allowed)return "";
if(_EVENT_ATTR.test(lower))return "";
var value=dq!=null?dq:(sq!=null?sq:(bare!=null?bare:""));
if(lower==="href"||lower==="src"){
if(!_safeUrlValue(value))return "";
}
if(value===""){out.push(lower);return "";}
out.push(lower+'="'+escapeHtml(value)+'"');
return "";
});
return out.length?(" "+out.join(" ")):"";
}
function sanitizeRenderedHtml(html){
var src=String(html==null?"":html);
var out="";
var i=0;
while(i<src.length){
var lt=src.indexOf("<",i);
if(lt<0){out+=src.slice(i);break;}
out+=src.slice(i,lt);
if(src.slice(lt,lt+4)==="<!--"){
var end=src.indexOf("-->",lt+4);
i=end<0?src.length:end+3;
continue;
}
var m=/^<\s*(\/?)\s*([a-zA-Z][a-zA-Z0-9-]*)((?:[^>"']|"[^"]*"|'[^']*')*)>/.exec(src.slice(lt));
if(!m||m[0].indexOf("\n")>=0){
/* 不是完整标签（正文里的裸 `<`）：转义它，后面的内容继续扫。
   标签**必须同行闭合** —— 跨行匹配会把正文里的 `<` 一路吃到后面的 `>`，
   把本该显示的文本当成标签吞掉。 */
out+="&lt;";i=lt+1;continue;
}
var closing=m[1]==="/";
var rawName=m[2];
var name=rawName.toLowerCase();
if(_SAFE_TAGS[name]!==1){
/* 白名单外：**整段转义成文本**，不留在 DOM 里 */
out+=escapeHtml(m[0]);
i=lt+m[0].length;
continue;
}
if(closing){
out+="</"+name+">";
}else{
var selfClose=/\/\s*$/.test(m[3]||"");
out+="<"+name+_cleanTagAttrs(m[3]||"")+(selfClose?" /":"")+">";
}
i=lt+m[0].length;
}
return out;
}
/* markdown 解析器实例。
   **不要**在 `parse` 选项里再传 `renderer`：那会整体替换渲染器链，
   把 `use()` 注册的渲染方法覆盖（`codespan` 那类）整个丢掉。
   所以所有渲染定制都在 `mdParser()` 里经 `use()` 装好，parse 只传解析选项。
   注入防线在 `sanitizeRenderedHtml`（解析器的 `html:false` 不起作用，见上）。 */
var _mdParser=null;
function mdParser(){
if(_mdParser)return _mdParser;
if(typeof marked==="undefined"||!marked)return null;
_mdParser=(typeof marked.Marked==="function")?new marked.Marked():marked;
_mdParser.use({renderer:markedRenderer()});
_mdParser.use({extensions:[atFileExtension()]});
_mdParser.use({renderer:filePathCodespanExtension()});
return _mdParser;
}
/* 兼容旧调用点：注册动作现在由 `mdParser()` 一次装好，这里只确保实例已建。 */
function initMarkedExtensions(){
mdParser();
}
var _markedRenderer=null;
function markedRenderer(){
if(_markedRenderer)return _markedRenderer;
var r=new marked.Renderer();
/* 路径改写**只在渲染这一步做**，不改 token：`walkTokens` 改过 `href` 之后
   就取不回本地路径了，而悬停提示要显示文件在哪。
   视频用 `<video>` 而不是 `<img>`：`<img>` 对 mp4 只会显示成破图。 */
r.image=function(token){
var raw=String((token&&token.href)||"");
var href=markedImageHref(raw);
var alt=String((token&&token.text)||"");
var title=String((token&&token.title)||"")||raw;
var t=title?' title="'+escapeHtml(title)+'"':'';
if(markedIsVideo(href))return '<video src="'+escapeHtml(href)+'" controls'+t+' style="max-width:100%;border-radius:6px;margin:4px 0;max-height:480px;background:#000;"></video>';
return '<img src="'+escapeHtml(href)+'" alt="'+escapeHtml(alt)+'"'+t+' loading="lazy" style="max-width:300px;height:auto" />';
};
r.link=function(token){
var raw=String((token&&token.href)||"");
/* 媒体文件的本地路径 → `/api/media`；其余链接原样（外链带 `target=_blank`） */
var href=(markedIsMediaFile(raw)&&localAbsPath(raw))?markedImageHref(raw):raw;
var text=token&&token.tokens?this.parser.parseInline(token.tokens):escapeHtml((token&&token.text)||"");
var ext=/^https?:/i.test(href);
return '<a href="'+escapeHtml(href)+'"'+(ext?' target="_blank" rel="noopener noreferrer"':'')+'>'+text+'</a>';
};
_markedRenderer=r;
return r;
}
function renderMarkdownBlocks(seg){
var parser=mdParser();
if(!parser||typeof parser.parse!=="function"){
/* 解析器缺失时回落成纯文本：宁可少排版，也不要把 markdown 源码当 HTML 插进去 */
return '<p>'+escapeHtml(seg||"").replace(/\n/g,"<br/>")+'</p>';
}
return sanitizeRenderedHtml(parser.parse(String(seg||""),{gfm:true,breaks:false,html:false}));
}
function isUnifiedDiffLine(line){
var s=String(line||"");
if(!s)return false;
if(/^---\s/.test(s)||/^\+\+\+\s/.test(s)||/^@@\s/.test(s))return true;
if(/^[-+]/.test(s))return true;
return false;
}
function shouldStartUnifiedDiffBlock(lines,i){
if(i>=lines.length||!isUnifiedDiffLine(lines[i]))return false;
if(/^---\s/.test(lines[i])||/^@@\s/.test(lines[i]))return true;
if(i+1>=lines.length)return/^[-+]/.test(lines[i]);
return isUnifiedDiffLine(lines[i+1]);
}
function collectUnifiedDiffBlock(lines,start){
var block=[],i=start;
while(i<lines.length){
var line=lines[i];
if(isUnifiedDiffLine(line)){block.push(line);i++;continue;}
if(!String(line).trim()&&i+1<lines.length&&isUnifiedDiffLine(lines[i+1])){block.push(line);i++;continue;}
break;
}
return {lines:block,next:i};
}
function looksLikeUnifiedDiffBlock(block){
if(!block||block.length<2)return false;
var hasMarker=false,hasChange=false;
for(var j=0;j<block.length;j++){
var L=block[j];
if(/^---\s/.test(L)||/^\+\+\+\s/.test(L)||/^@@\s/.test(L))hasMarker=true;
if((/^-/.test(L)&&!/^---/.test(L))||(/^\+/.test(L)&&!/^\+\+\+/.test(L)))hasChange=true;
}
return hasMarker;
}
function renderUnifiedDiffBlockHtml(block){
var body=block.join("\n");
var cards=renderUnifiedDiffBodyAsCardsHtml(body);
if(cards)return cards;
return '<pre><code>'+escapeHtml(body)+'</code></pre>';
}
function isDevNullPath(p){
var s=String(p||"").trim().replace(/\\/g,"/").toLowerCase();
if(!s||s==="null")return true;
return s==="/dev/null"||s==="dev/null"||s.endsWith("/dev/null");
}
function parseDiffHeaderPath(line){
var m=/^(---|\+\+\+)\s+(.+)$/.exec(String(line||"").trim());
if(!m)return "";
return m[2].split("\t")[0].trim();
}
function diffFileNameFromBody(body){
var lines=String(body||'').replace(/\r/g,'').split('\n');
var fromRaw="",toRaw="";
for(var i=0;i<lines.length;i++){
var L=lines[i];
if(!fromRaw&&L.indexOf("--- ")===0)fromRaw=parseDiffHeaderPath(L);
if(!toRaw&&L.indexOf("+++ ")===0)toRaw=parseDiffHeaderPath(L);
}
if(toRaw&&!isDevNullPath(toRaw))return baseNameOnly(toRaw);
if(fromRaw&&!isDevNullPath(fromRaw))return baseNameOnly(fromRaw);
return "文件";
}
function findDiffFenceCloseIndex(rest){
var reLine=/^[ \t]*```[ \t]*$/gm,m;
while((m=reLine.exec(rest))!==null){
var after=rest.slice(m.index+m[0].length);
var trimmed=after.replace(/^\r?\n/,"");
if(!trimmed.trim())return m.index;
if(/^```(?:diff|patch)\b/i.test(trimmed))return m.index;
var lines=trimmed.split(/\r?\n/);
var line0=lines[0]||"";
var firstLine=line0.trim();
if(/^---\s/.test(firstLine)||/^\+\+\+\s/.test(firstLine)||/^@@\s/.test(firstLine))continue;
// 只有多行连续以 -/+ 开头才认为是 diff 内容，避免单行误判
if(/^[-+]/.test(firstLine)){
for(var di=1;di<Math.min(lines.length,4);di++){
var l=(lines[di]||"").trim();
if(!l)break;
if(l.charAt(0)==="-"||l.charAt(0)==="+")continue;
return m.index;
}
continue;
}
return m.index;
}
return -1;
}
function splitUnifiedDiffSections(body){
var lines=String(body||"").replace(/\r/g,"").split("\n");
var sections=[],cur=[];
for(var i=0;i<lines.length;i++){
var L=lines[i];
if(/^---\s/.test(L)&&cur.some(function(x){return /^---\s/.test(x);})){
sections.push(cur.join("\n"));
cur=[L];
continue;
}
cur.push(L);
}
if(cur.length)sections.push(cur.join("\n"));
return sections.filter(function(s){return String(s).trim();});
}
function renderUnifiedDiffBodyAsCardsHtml(body){
// 快速检查：没有任何 diff 标记行的内容不渲染为 diff 卡片
if(!/^---\s/m.test(body)&&!/^\+\+\+\s/m.test(body)&&!/^@@\s/m.test(body))return "";
var sections=splitUnifiedDiffSections(body);
if(!sections.length)return "";
var html="";
for(var si=0;si<sections.length;si++){
var sec=sections[si];
var lines=sec.replace(/\r/g,"").split("\n");
var fn=diffFileNameFromBody(sec);
for(var fi=0;fi<lines.length;fi++){
var L=lines[fi];
if(L.indexOf("--- ")===0||L.indexOf("+++ ")===0){
var mp=L.match(/[ab][\/](.+)/);
if(mp){fn=mp[1];break;}
}
}
var add=0,del=0;
for(var li=0;li<lines.length;li++){
var L=lines[li];
if(L.indexOf("--- ")===0||L.indexOf("+++ ")===0)continue;
var c=L.charAt(0);
if(c==="+")add++;else if(c==="-")del++;
}
var cap='<div class="chat-diff-cap">'+escapeHtml(fn)+' · diff'+(del>0?' <span class="chat-diff-neg">-'+del+'</span>':'')+(add>0?' <span class="chat-diff-pos">+'+add+'</span>':'')+'</div>';
var box='<div class="diff-unified diff-surface-adaptive">';
for(var li=0;li<lines.length;li++){
var L=lines[li];
var ch0=L.charAt(0);
if(ch0==="-"||ch0==="+"){
if(L.indexOf("--- ")===0||L.indexOf("+++ ")===0)continue;
box+='<div class="'+(ch0==="-"? 'd-del' : 'd-add')+'">'+diffRowInnerHtml({t:ch0,l:L.substring(1)})+'</div>';}
else if(/^@@/.test(L)){
box+='<div class="d-meta">'+escapeHtml(L)+'</div>';}
else if(ch0===" "){
box+='<div class="d-eq">'+diffRowInnerHtml({t:" ",l:L.replace(/^\s/,"")})+'</div>';}
else if(L.trim()){
box+='<div class="d-eq">'+diffRowInnerHtml({t:" ",l:L})+'</div>';}
}
box+='</div>';
html+='<div class="chat-diff-card">'+cap+box+'</div>';
}
return html;
}
/* 围栏缩进上限（空格数）。
   按 CommonMark，围栏可以缩进 0–3 个空格；**列表项里的围栏通常缩进 1–3 格**
   （`- 说明：\n  ```python\n  …\n  ```），只认行首会让这些围栏裸露成正文。
   缩进 4 格及以上是缩进式代码块，不是围栏，不在此处理。 */
var FENCE_MAX_INDENT=3;
function iterMarkdownCodeFences(text,visit){
var src=String(text||"").replace(/\r\n/g,"\n");
var i=0;
while(i<src.length){
var open=src.indexOf("```",i);
if(open<0){visit("text",src.slice(i));break;}
// 只认行首（可带 0–3 空格缩进）的 ```，行内的 ``` 当作普通文本跳过
var lineStart=src.lastIndexOf("\n",open)+1;
var indent=open-lineStart;
if(indent>FENCE_MAX_INDENT||!/^[ \t]*$/.test(src.slice(lineStart,open))){
visit("text",src.slice(i,open+3));i=open+3;continue;
}
if(open>i)visit("text",src.slice(i,open));
var langEnd=src.indexOf("\n",open+3);
if(langEnd<0){visit("text",src.slice(open));break;}
var lang=src.slice(open+3,langEnd);
var langLow=lang.trim().toLowerCase();
var pos=langEnd+1;
var closed=false;
if(langLow==="diff"||langLow==="patch"){
var rest=src.slice(pos);
var closeAt=findDiffFenceCloseIndex(rest);
if(closeAt>=0){
var closeMatch=rest.slice(closeAt).match(/^[ \t]*```/);
visit("fence",lang,rest.slice(0,closeAt).replace(/\n$/,""));
i=pos+closeAt+closeMatch[0].length;
var nl=src.indexOf("\n",i);
i=nl<0?src.length:nl+1;
closed=true;
}
}else{
while(pos<src.length){
var idx=src.indexOf("```",pos);
if(idx<0)break;
var closeLineStart=src.lastIndexOf("\n",idx-1)+1;
// 闭合围栏同样允许 0–3 空格缩进，但行内不能有别的内容
var closeIndent=idx-closeLineStart;
if(closeIndent>FENCE_MAX_INDENT||!/^[ \t]*$/.test(src.slice(closeLineStart,idx))){pos=idx+3;continue;}
var lineEnd=src.indexOf("\n",idx);
if(lineEnd<0)lineEnd=src.length;
var line=src.slice(closeLineStart,lineEnd);
if(/^[ \t]*```[ \t]*$/.test(line)){
/* 围栏内容去掉与开栏相同的缩进量：markdown 里缩进是列表层级的产物，
   不属于代码本身，留着会让每行都多个前导空格甚至被 marked 当成嵌套代码块。 */
var body=src.slice(langEnd+1,closeLineStart).replace(/\n$/,"");
if(indent>0){
var pad=new RegExp("^[ \\t]{0,"+indent+"}");
body=body.split("\n").map(function(l){return l.replace(pad,"");}).join("\n");
}
visit("fence",lang,body);
i=lineEnd<src.length?lineEnd+1:src.length;
closed=true;
break;
}
pos=idx+3;
}
}
if(!closed){visit("text",src.slice(open));break;}
}
}
function parseUnifiedDiffBodyForRows(body){
var lines=String(body||'').replace(/\r/g,'').split('\n');
var oldL=[],newL=[];
for(var i=0;i<lines.length;i++){
var L=lines[i];
if(/^---/.test(L)||/^\+\+\+/.test(L))continue;
if(/^@@/.test(L))continue;
if(/^\s*#/.test(L))continue;
if(/^-/.test(L)&&!/^---/.test(L))oldL.push(L.slice(1));
else if(/^\+/.test(L)&&!/^\+\+\+/.test(L))newL.push(L.slice(1));
else if(/^ /.test(L)){var c=L.slice(1);oldL.push(c);newL.push(c);}
}
return {oldT:oldL.join('\n'),newT:newL.join('\n')};
}
function diffRowInnerHtml(r){
var g=r.t==='-'?'−':(r.t==='+'?'+':' ');
var gs=r.t==='-'?'d-gutter-del':(r.t==='+'?'d-gutter-add':'d-gutter-eq');
return '<span class="d-gutter '+gs+'">'+escapeHtml(g)+'</span><span class="d-code">'+escapeHtml(r.l)+'</span>';
}
function buildDiffRowsHtml(oldT,newT){
var rows=linesDiff(oldT,newT);
var html='';
for(var ri=0;ri<rows.length;ri++){
var r=rows[ri];
var cls=r.t==='-'?'d-del':(r.t==='+'?'d-add':'d-eq');
html+='<div class="'+cls+'">'+diffRowInnerHtml(r)+'</div>';
}
return html;
}
function buildChatDiffCardHtml(oldT,newT,nameHint){
var st=calcDiffStats(oldT,newT);
var fn=String(nameHint||'').trim()||'文件';
var cap='<div class="chat-diff-cap">'+escapeHtml(fn)+' · diff';
if(st.del>0)cap+=' <span class="chat-diff-neg">-'+st.del+'</span>';
if(st.add>0)cap+=' <span class="chat-diff-pos">+'+st.add+'</span>';
cap+='</div>';
var box='<div class="diff-unified diff-surface-adaptive">'+buildDiffRowsHtml(oldT,newT)+'</div>';
return '<div class="chat-diff-card">'+cap+box+'</div>';
}
function renderSimpleDiffCard(inner,lang){
// 无 unified diff 头的简化 diff 代码块 → 渲染为 diff 卡片
var lines=String(inner||'').split('\n');
var add=0,del=0;
for(var _i=0;_i<lines.length;_i++){var _c=lines[_i].charAt(0);if(_c==='+')add++;else if(_c==='-')del++;}
var cap='<div class="chat-diff-cap">'+escapeHtml(lang||'diff')+(del?' <span class="chat-diff-neg">-'+del+'</span>':'')+(add?' <span class="chat-diff-pos">+'+add+'</span>':'')+'</div>';
var box='<div class="diff-unified diff-surface-adaptive">';
for(var _i=0;_i<lines.length;_i++){var L=lines[_i];var ch0=L.charAt(0);
if(ch0==='-'){box+='<div class="d-del">'+diffRowInnerHtml({t:'-',l:L.substring(1)})+'</div>';}
else if(ch0==='+'){box+='<div class="d-add">'+diffRowInnerHtml({t:'+',l:L.substring(1)})+'</div>';}
else if(ch0===' '){box+='<div class="d-eq">'+diffRowInnerHtml({t:' ',l:L.replace(/^ /,'')})+'</div>';}
else if(L.trim()){box+='<div class="d-eq">'+diffRowInnerHtml({t:' ',l:L})+'</div>';}}
box+='</div>';
return '<div class="chat-diff-card">'+cap+box+'</div>';
}
function renderMarkdown(md){
const text=String(md||'').replace(/\r\n/g,'\n');
let html='';
iterMarkdownCodeFences(text,function(kind,a,b){
if(kind==='text'){html+=renderMarkdownBlocks(a);return;}
const lang=String(a||'').trim();
const inner=b;
const langLow=lang.toLowerCase();
if((langLow==='diff'||langLow==='patch')&&inner){
var cards=renderUnifiedDiffBodyAsCardsHtml(inner);
if(cards){
html+=cards;
}else{
html+=renderSimpleDiffCard(inner,lang);
}
}else{
var _hc2=hljsCodeClass(lang);html+='<pre><code'+(_hc2?' class="'+_hc2+'"':'')+(lang?' data-lang="'+escapeHtml(lang)+'"':'')+'>'+highlightCode(inner,lang)+'</code></pre>';
}
});
return html||'<p></p>';
}
function add(role,t){
if(!msgs)return null;
const e=document.createElement('div');
e.className='b '+(role==='u'?'u':'a');
if(role==='u'){/* 文字包一层 span —— 这样「文字」是**独立子元素**，附件条能用 CSS `order` 排到它前面（气泡是 flex 纵向布局，文字需要成为独立子元素才能用 `order` 调整顺序）。 */e.appendChild(Object.assign(document.createElement('span'),{className:'b-text',innerHTML:linkifyUserText(t)}));}else{e.innerHTML=renderMarkdown(t||'');}
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
   marked 每次都是**全量重解析**（块级缓存对它无效），delta 密集时逐条渲染会把
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
function _muteEl(){return document.createElement("span");}
function beginChatToolOnly(ev){
var tid=ev.tool_call_id!=null&&String(ev.tool_call_id).trim()!==""?String(ev.tool_call_id).trim():String(Math.random());
var o={tag:_muteEl(),resLb:_muteEl(),resPb:_muteEl(),previewSlot:_muteEl(),args:ev.args||{},script:ev.script||"",spinWrap:null,stepTitle:String(ev.step_title||"").trim(),fileSpan:null,progressBadge:null,liveOutPre:null,cmdInputBar:null,chatRunCard:null,chatRunOutPre:null,chatToolRow:null,chatToolRes:null};
toolOpen.set(tid,o);
if(showToolItems())mountChatToolItem(o);
if(showToolItems()&&isStreamOutputToolScript(ev.script)&&!o.chatToolRow)ensureChatRunCard(o);
}
function appendStep(el){if(!showToolSteps()||!steps||!el)return;steps.appendChild(el);scrollToBottom(steps);}
function findStepCardForToolCall(tid){
var id=String(tid!=null?tid:"").trim();
if(!id)return null;
var _q=id.replace(/\\/g,"\\\\").replace(/"/g,'\\"');
var sel='.step.card[data-tool-call-id="'+_q+'"]';
if(steps){var c0=steps.querySelector(sel);if(c0)return c0;}
if(typeof stepsRoot!=="undefined"&&stepsRoot){var c1=stepsRoot.querySelector(sel);if(c1)return c1;}
if(typeof conversationTabs!=="undefined"&&conversationTabs&&conversationTabs.length){
for(var i=0;i<conversationTabs.length;i++){var sh=conversationTabs[i]&&conversationTabs[i].stepsHost;if(sh){var c2=sh.querySelector(sel);if(c2)return c2;}}
}
try{var c3=document.querySelector(sel);if(c3)return c3;}catch(_e){}
return null;
}
function flushPendingSteps(){while(pendingStepEls.length){appendStep(pendingStepEls.shift());}}function discardPendingSteps(){clearLlmAnim();pendingStepEls=[];lastLlm=null;}
function addDispatchTitle(title){
const t=String(title||"").trim();
if(!t)return;
if(seenDispatchTitle===t)return;
seenDispatchTitle=t;
if(!showToolSteps())return;
const d=document.createElement("div");d.className="dispatch-title";
d.textContent="本轮调度："+t;
appendStep(d);
}
function tokenPercent(){if(SESSION_TOKEN_LIMIT<=0)return 0;const p=Math.ceil(((sessionTokenUsed%SESSION_TOKEN_LIMIT)/SESSION_TOKEN_LIMIT)*100);if(!isFinite(p)||p<0)return 0;return p>100?100:p;}
/** 上下文占比展示：百分数向上取到 2 位小数再格式化（如 0.001% → 0.01%） */
function formatContextPct(p){var x=Number(p)||0;if(x<=0)return"0.00";var v=Math.ceil(x*100)/100;return v.toFixed(2);}
function ensureCtxLayoutTooltip(){if(ctxLayoutTooltipEl)return ctxLayoutTooltipEl;ctxLayoutTooltipEl=document.createElement("div");ctxLayoutTooltipEl.id="ctx-layout-tooltip";ctxLayoutTooltipEl.className="ctx-layout-tooltip";ctxLayoutTooltipEl.style.display="none";ctxLayoutTooltipEl.setAttribute("role","tooltip");document.body.appendChild(ctxLayoutTooltipEl);if(!ctxLayoutTooltipInited){ctxLayoutTooltipInited=true;ctxLayoutTooltipEl.addEventListener("mouseenter",function(){if(ctxLayoutTipHideTimer){clearTimeout(ctxLayoutTipHideTimer);ctxLayoutTipHideTimer=null;}});ctxLayoutTooltipEl.addEventListener("mouseleave",function(){scheduleHideCtxLayoutTooltip();});}return ctxLayoutTooltipEl;}
function scheduleHideCtxLayoutTooltip(){var tt=ctxLayoutTooltipEl;if(!tt)return;if(ctxLayoutTipHideTimer)clearTimeout(ctxLayoutTipHideTimer);ctxLayoutTipHideTimer=setTimeout(function(){ctxLayoutTipHideTimer=null;tt.style.display="none";},160);}
function positionCtxLayoutTooltip(tt, anchorEl){
if(!tt||!anchorEl)return;
tt.style.position="fixed";
tt.style.transform="";
tt.style.bottom="auto";
var r=anchorEl.getBoundingClientRect();
var left=r.left;
var gap=10;
tt.style.left=left+"px";
tt.style.zIndex="10050";
requestAnimationFrame(function(){
void tt.offsetHeight;
var h=tt.offsetHeight||0;
var top=r.top-h-gap;
if(top<8)top=8;
tt.style.top=top+"px";
var vw=document.documentElement.clientWidth||window.innerWidth;
var tw=tt.offsetWidth||0;
if(left+tw>vw-8)tt.style.left=Math.max(8,vw-tw-8)+"px";
});
}
function buildCtxLayoutTooltipHtml(segs, colors){
var rows=[];
for(var i=0;i<segs.length;i++){var s=segs[i];if(!s)continue;rows.push(s);}
var maxTok=0;
for(var j=0;j<rows.length;j++)maxTok=Math.max(maxTok,Math.max(0,Math.floor(Number(rows[j].tokens)||0)));
if(maxTok<1)maxTok=1;
var trackW=120;
var parts=[];
for(var m=0;m<rows.length;m++){
var sg=rows[m];
var key=String(sg.key||"");
var lab=String(sg.label||ctxSegmentLabel(key)||key);
var tok=Math.max(0,Math.floor(Number(sg.tokens)||0));
var pct=formatContextPct(sg.pct);
var col=ctxSegmentColor(key);
var csafe=String(col).replace(/[^#0-9a-fA-F]/g,"").slice(0,9)||"#5c5c5c";
var wpx=tok<=0?0:Math.max(2,Math.round(trackW*tok/maxTok));
var mid="—";
/* 数量一律按段显示"几个主体"：插件段的数量由插件自报（勾选文件数、技能数…），
   内核与壳层都不解释它的含义。 */
if(sg.count!==undefined&&sg.count!==null){
var cnt=Math.max(0,Math.floor(Number(sg.count)||0));
mid=String(cnt)+"个";
}
var meta=pct+"% | "+mid+" | "+tok.toLocaleString()+" tokens";
parts.push(
'<div class="ctx-tip-line">'+
'<span class="ctx-tip-br">'+escapeHtml(lab)+'</span>'+
'<span class="ctx-tip-track">'+
'<span class="ctx-tip-track-fill" style="width:'+wpx+"px;background-color:"+csafe+'"></span>'+
"</span>"+
'<span class="ctx-tip-rest">'+escapeHtml(meta)+"</span>"+
"</div>"
);
}
return parts.join("");
}
/* 插件段的取色：注册过就用注册的，没注册按段 key 稳定取一个 ——
   同一插件每回合同色、换插件不串色（插件没有界面脚本时走这里）。 */
function _segVar(name,fallback){
var v=getComputedStyle(document.documentElement).getPropertyValue(name);
v=String(v||"").trim();
return v||fallback;
}
/* 两套主题各一组段色：色名 → {dark, light}。插件注册色名就自动跟着主题走；
   兜底也按同一张色名表取，所以**分段条与弹窗永远同色**。 */
var CTX_SEG_NAMED={
"amber":  {dark:"#c8a44a",light:"#9a7f22"},
"blue":   {dark:"#4f86d6",light:"#17456f"},
"teal":   {dark:"#3f9e86",light:"#15604a"},
"violet": {dark:"#9b6bd6",light:"#5b3d9a"},
"slate":  {dark:"#7d8b99",light:"#3f5560"},
"purple": {dark:"#b06fd0",light:"#8e24aa"},
"red":    {dark:"#c86a6a",light:"#8a2a2a"},
"plum":   {dark:"#c8779f",light:"#8e3a63"}};
/* 已知段显式配色：段名固定，就不该让哈希决定颜色（哈希会撞色）。 */
var CTX_SEG_FIXED={system:"amber",summary:"red",full_recent:"teal",
mode:"slate"};
/* 只有完全没见过的插件段才走哈希兜底。 */
var CTX_SEG_FALLBACK=["blue","teal","amber","violet","slate","red","purple"];
function _ctxIsLight(){
return document.documentElement.getAttribute("data-ui-theme")==="light";
}
function ctxSegmentResolve(color){
var c=String(color||"");
if(/^#|^rgb/.test(c))return c;
return _ctxNamedColor(c)||c;
}
function _ctxNamedColor(name){
var e=CTX_SEG_NAMED[String(name||"")];
if(!e)return "";
return _ctxIsLight()?e.light:e.dark;
}
function ctxSegmentColor(key){
var k=String(key||"");
var theme=_ctxIsLight()?"light":"dark";
var cacheKey=theme+"|"+k;
if(_ctxSegColorCache[cacheKey])return _ctxSegColorCache[cacheKey];
var col="";
var hook=/^plugin:(.+)$/.exec(k);
if(hook&&ctxSegmentHooks[hook[1]]&&ctxSegmentHooks[hook[1]].color){
col=String(ctxSegmentHooks[hook[1]].color);
if(!/^#|^rgb/.test(col))col=_ctxNamedColor(col);
}else if(hook){
col=_ctxNamedColor("violet");
}
if(!col&&CTX_SEG_FIXED[k])col=_ctxNamedColor(CTX_SEG_FIXED[k]);
if(!col&&k==="remaining")col=_segVar("--c-seg-idle","#4a4e55");
if(!col){
var h=0;
for(var i=0;i<k.length;i++){h=(h*31+k.charCodeAt(i))>>>0;}
col=_ctxNamedColor(CTX_SEG_FALLBACK[h%CTX_SEG_FALLBACK.length]);
}
_ctxSegColorCache[cacheKey]=col;
return col;
}
function bindCtxLayoutTooltip(barHost, segs, colors){
var tt=ensureCtxLayoutTooltip();
var filtered=[];
for(var i=0;i<segs.length;i++){var s=segs[i];if(!s)continue;filtered.push(s);}
function showTip(){
if(ctxLayoutTipHideTimer){clearTimeout(ctxLayoutTipHideTimer);ctxLayoutTipHideTimer=null;}
if(!filtered.length){if(tt){tt.style.display="none";tt.innerHTML="";}return;}
tt.innerHTML=buildCtxLayoutTooltipHtml(filtered,colors);
tt.style.display="block";
positionCtxLayoutTooltip(tt,barHost);
}
barHost.addEventListener("mouseenter",showTip);
barHost.addEventListener("mouseleave",function(){scheduleHideCtxLayoutTooltip();});
}
function formatCompactTokens(n){var x=Math.max(0,Math.floor(Number(n)||0));if(x>=1e9){var v=x/1e9;return (v>=100?v.toFixed(0):v>=10?v.toFixed(1):v.toFixed(2)).replace(/\.?0+$/,"")+"B";}if(x>=1e6){var v2=x/1e6;return (v2>=100?v2.toFixed(0):v2>=10?v2.toFixed(1):v2.toFixed(2)).replace(/\.?0+$/,"")+"M";}if(x>=1e3){var v3=x/1e3;return (v3>=100?v3.toFixed(0):v3.toFixed(1)).replace(/\.0+$/,"")+"K";}return String(x);}
function estimateCnyFromRates(){if(!pricingRates||pricingRates.ok!==true)return null;var hit=totalCacheHitTokens/1e6*Number(pricingRates.cache_hit_cny_per_m||0);var miss=totalCacheMissTokens/1e6*Number(pricingRates.cache_miss_cny_per_m||0);var out=totalCompletionTokens/1e6*Number(pricingRates.output_cny_per_m||0);return hit+miss+out;}
function costTitleSuffix(){if(!conv)return "—";if(pricingLoading)return "计价查询中…";if(pricingFailed)return "未查到模型计价信息";var x=estimateCnyFromRates();return x===null?"未查到模型计价信息":"￥"+x.toFixed(2);}
async function ensureModelPricing(){var cid=conv,mid=selectedModel;if(!cid||!mid)return;if(pricingCacheKey===cid+"\0"+mid&&(pricingRates!==null||pricingFailed))return;if(pricingInflight)return;pricingInflight=true;pricingLoading=true;queueMicrotask(_updateUsageBottom);var g=++pricingFetchGen;try{var r=await fetch("/api/model-pricing?"+new URLSearchParams({conversation_id:cid,model:mid}));var j=await r.json();if(g!==pricingFetchGen)return;pricingCacheKey=cid+"\0"+mid;if(j&&j.ok===true){pricingRates=j;pricingFailed=false;}else{pricingRates=null;pricingFailed=true;}}catch(e){if(g!==pricingFetchGen)return;pricingCacheKey=cid+"\0"+mid;pricingRates=null;pricingFailed=true;}finally{if(g===pricingFetchGen){pricingLoading=false;pricingInflight=false;queueMicrotask(_updateUsageBottom);}}}
function buildUsageRing(){const million=Math.floor(sessionTokenUsed/SESSION_TOKEN_LIMIT);const p=tokenPercent();const used=Math.max(0,Math.floor(sessionTokenUsed));const ring=document.createElement("span");ring.className="usage-ring";ring.style.setProperty("--p",String(p));const totalCache=totalCacheHitTokens+totalCacheMissTokens;const hitPct=totalCache>0?Math.round(totalCacheHitTokens/totalCache*100):0;var cts=costTitleSuffix();var costD="";if(pricingRates&&pricingRates.ok===true){var _hC=totalCacheHitTokens/1e6*Number(pricingRates.cache_hit_cny_per_m||0);var _mC=totalCacheMissTokens/1e6*Number(pricingRates.cache_miss_cny_per_m||0);var _oC=totalCompletionTokens/1e6*Number(pricingRates.output_cny_per_m||0);var _pm=Number(pricingRates.cache_miss_cny_per_m||0);costD="1m=￥"+_pm.toFixed(2)+" | 总费用: ￥"+(_hC+_mC+_oC).toFixed(2)+" 输入: ￥"+(_hC+_mC).toFixed(2)+" 输出: ￥"+_oC.toFixed(2)+" 缓存命中: ￥"+_hC.toFixed(2)+" 未命中: ￥"+_mC.toFixed(2);}ring.title="已用: "+used.toLocaleString()+"\n输入: "+totalPromptTokens.toLocaleString()+" (显示 "+formatCompactTokens(totalPromptTokens)+")\n输出: "+totalCompletionTokens.toLocaleString()+" (显示 "+formatCompactTokens(totalCompletionTokens)+")\nKV缓存命中: "+totalCacheHitTokens.toLocaleString()+" ("+hitPct+"%)\n未命中: "+totalCacheMissTokens.toLocaleString()+"\n费用预估: "+cts+(costD?"\n"+costD:"");const num=document.createElement("span");num.className="usage-num";num.textContent=million;ring.appendChild(num);return ring;}
function _updateUsageBottom(){
const el=document.getElementById("usage-bottom");if(!el)return;
if(ctxLayoutTooltipEl){ctxLayoutTooltipEl.style.display="none";}
if(ctxLayoutTipHideTimer){clearTimeout(ctxLayoutTipHideTimer);ctxLayoutTipHideTimer=null;}
const ring=buildUsageRing();
function ubCells(label, value){var k=document.createElement("span");k.className="ub-k";k.textContent=label;var v=document.createElement("span");v.className="ub-v";v.textContent=value;return [k,v];}
function ubPush(sheet, cells){for(var i=0;i<cells.length;i++)sheet.appendChild(cells[i]);}
const totalCache=totalCacheHitTokens+totalCacheMissTokens;const hitPct=totalCache>0?Math.round(totalCacheHitTokens/totalCache*100):0;
const sheet=document.createElement("div");sheet.className="ub-sheet";
const head1=document.createElement("div");head1.className="ub-head";
const title=document.createElement("span");title.className="ub-title";title.textContent="模型用量";
const ringWrap=document.createElement("span");ringWrap.className="ub-ring";ringWrap.appendChild(ring);
head1.appendChild(title);head1.appendChild(ringWrap);
sheet.appendChild(head1);
ubPush(sheet,[].concat(
ubCells("输入", formatCompactTokens(totalPromptTokens)),
ubCells("输出", formatCompactTokens(totalCompletionTokens)),
ubCells("缓存命中", formatCompactTokens(totalCacheHitTokens)+" ("+hitPct+"%)"),
ubCells("未命中", formatCompactTokens(totalCacheMissTokens))
));
var head2=document.createElement("div");head2.className="ub-head";
var t2=document.createElement("span");t2.className="ub-title";t2.textContent="费用预估";head2.appendChild(t2);sheet.appendChild(head2);
if(pricingRates&&pricingRates.ok===true){var hC=totalCacheHitTokens/1e6*Number(pricingRates.cache_hit_cny_per_m||0);var mC=totalCacheMissTokens/1e6*Number(pricingRates.cache_miss_cny_per_m||0);var oC=totalCompletionTokens/1e6*Number(pricingRates.output_cny_per_m||0);var tC=hC+mC+oC;var pm=Number(pricingRates.cache_miss_cny_per_m||0);
ubPush(sheet,[].concat(
ubCells("1m", "￥"+pm.toFixed(2)),
ubCells("总费用", "￥"+tC.toFixed(2)),
ubCells("输入", "￥"+(hC+mC).toFixed(2)),
ubCells("输出", "￥"+oC.toFixed(2)),
ubCells("缓存命中", "￥"+hC.toFixed(2)),
ubCells("未命中", "￥"+mC.toFixed(2))
));}else if(pricingLoading){var lI=document.createElement("span");lI.className="ub-note";lI.textContent="计价查询中…";sheet.appendChild(lI);}else if(!conv){var dI=document.createElement("span");dI.className="ub-note";dI.textContent="—";sheet.appendChild(dI);}else{var eI=document.createElement("span");eI.className="ub-note";eI.textContent="未查到模型计价信息";sheet.appendChild(eI);}
var row3=document.createElement("div");row3.className="ub-row ub-row-ctx";
var t3=document.createElement("span");t3.className="ub-title";t3.textContent="上下文视图";
var barHost=document.createElement("div");barHost.className="ctx-bar-host";
var tabCtx=typeof getActiveTab==="function"?getActiveTab():null;
var lay=tabCtx&&tabCtx.lastContextLayout;
var segs=lay&&Array.isArray(lay.segments)?lay.segments:[];

/* 段色取自主题令牌（两套主题各一组），JS 不写死颜色。 */
/* 非插件段的色名：弹窗与分段条共用同一个取色函数，两处必然同色。 */
/* 弹窗与分段条共用 ctxSegmentColor，两处必然同色。 */
var colors={system:ctxSegmentColor("system"),summary:ctxSegmentColor("summary"),skill:ctxSegmentColor("skill"),resident:ctxSegmentColor("resident"),full_recent:ctxSegmentColor("full_recent"),mode:ctxSegmentColor("mode"),remaining:ctxSegmentColor("remaining")};
/* 插件段的颜色与渲染由插件自己注册：段 key 是 `plugin:<插件名>`。
   插件脚本里调 ctxSegments.register("<插件名>", {color:"blue", label:"知识库"})：
   color 给色名（壳层按当前主题取深/浅两套）或 `#rrggbb` 定值。 */
if(!segs.length){var empty=document.createElement("span");empty.className="ctx-bar-empty";empty.textContent="—";barHost.appendChild(empty);}
else{var bar=document.createElement("div");bar.className="ctx-bar";
for(var si=0;si<segs.length;si++){var sg=segs[si];if(!sg)continue;
var tok=Math.max(0,Math.floor(Number(sg.tokens)||0));
var col=ctxSegmentColor(String(sg.key));
var colEl=document.createElement("span");colEl.className="ctx-seg-col"+(tok>0?"":" ctx-seg-col-zero");
if(tok>0){colEl.style.flex=String(tok)+" 1 0";colEl.style.minWidth="2px";}else{colEl.style.flex="0 0 2px";colEl.style.minWidth="2px";colEl.style.maxWidth="2px";}
var fill=document.createElement("span");fill.className="ctx-seg ctx-seg-"+String(sg.key||"").replace(/[^a-z0-9_-]/gi,"");fill.style.background=col;fill.style.height="10px";fill.style.borderRadius="2px";fill.style.flexShrink="0";fill.style.width="100%";fill.style.display="block";fill.style.boxSizing="border-box";
colEl.appendChild(fill);bar.appendChild(colEl);}
barHost.appendChild(bar);bindCtxLayoutTooltip(barHost,segs,colors);}
row3.appendChild(t3);row3.appendChild(barHost);
el.innerHTML='';el.appendChild(sheet);el.appendChild(row3);
}

function applyUsageAccumulatorPayload(j){if(!j||typeof j!=="object")return;sessionTokenUsed=Number(j.session_token_used??0)||0;totalPromptTokens=Number(j.total_prompt_tokens??0)||0;totalCompletionTokens=Number(j.total_completion_tokens??0)||0;totalCacheHitTokens=Number(j.total_cache_hit_tokens??0)||0;totalCacheMissTokens=Number(j.total_cache_miss_tokens??0)||0;if(conv)void ensureModelPricing();_updateUsageBottom();}
async function loadUsageAccumulator(){try{/* 带上 conversation_id。
   后端用**单个全局文件**存用量，不带参数也能取到；
   适配层**按会话存**，缺参数会取到空槽 → 刷新后用量归零。
   位置遵循统一约定：**读=query，写=body**。 */
const r=await fetch("/api/usage-accumulator?conversation_id="+encodeURIComponent(activeConversationId||""));if(!r.ok)return;const j=await r.json();applyUsageAccumulatorPayload(j);}catch(e){}}
async function persistUsageAccumulator(){try{/* cid 为空时**不发**写请求 —— 空 cid 必被后端拒（invalid conversation_id），纯噪音。 */
if(!String(activeConversationId||""))return;/* **写操作走 body**（约定：写=body，读=query）。
         缺 conversation_id 时后端返回 `invalid conversation_id`，
         会话用量永不落盘（刷新即归零）。 */
await fetch("/api/usage-accumulator",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:String(activeConversationId||""),session_token_used:sessionTokenUsed,total_prompt_tokens:totalPromptTokens,total_completion_tokens:totalCompletionTokens,total_cache_hit_tokens:totalCacheHitTokens,total_cache_miss_tokens:totalCacheMissTokens})});}catch(e){}}
/* 工具展示清单（`/api/tool-labels`）：中文名与图标由**工具自己**声明。
   界面据此认识所有工具（含插件工具）—— 加一个插件工具不必改这里。
   下面的旧表只作兜底：清单还没到时至少不是空白。 */
var toolLabels={};
function toolDisplayOf(script){
var s=String(script||"").toLowerCase();
if(!s)return null;
if(toolLabels[s])return toolLabels[s];
var keys=Object.keys(toolLabels);
for(var i=0;i<keys.length;i++){
var k=keys[i];
if(s===k||s.indexOf(k+" ")>0||s.indexOf(k+"(")>0)return toolLabels[k];
}
return null;
}
function loadToolLabels(){
return fetch("/api/tool-labels").then(function(r){return r.json();}).then(function(d){
var list=(d&&Array.isArray(d.tools))?d.tools:[];
for(var i=0;i<list.length;i++){
var row=list[i]||{};
var n=String(row.name||"").toLowerCase();
if(n)toolLabels[n]={label:String(row.label||""),icon:String(row.icon||"")};
}
return toolLabels;
}).catch(function(){return toolLabels;});
}
function toolIco(script,args){
const s=(script||"").toLowerCase();
const a=(!args||typeof args!=="object")?{}:args;
var _d=toolDisplayOf(s);
if(_d&&_d.icon)return _d.icon;
/* 展示信息由工具自己声明（`/api/tool-labels`）。清单还没到时给一个中性图标，
   不再在壳层维护工具名表 —— 那样每加一个插件工具都得改这里。 */
return "⚙️";}
function toolZh(script){const s=(script||"").toLowerCase();
var _d=toolDisplayOf(s);
if(_d&&_d.label)return _d.label;
/* 同上：没有中文名就用工具自己的 name（后端清单里带 label）。 */
return s||"工具";}
function pickFileHint(args){if(!args||typeof args!=="object")return "";
const keys=["file","request_file","payload_file","path","old_path","new_path","source_path","dest_path","source","patch_file"];
for(let k of keys){let v=args[k];if(v===undefined&&args["--"+k]!==undefined)v=args["--"+k];
if(typeof v==="string"&&v){const parts=v.replace(/\\/g,"/").split("/");return parts[parts.length-1]||v;}}
return "";}
function parseToolPayload(args){
if(!args||typeof args!=="object")return null;
let p=args.payload;
if(typeof p==="string"){try{return JSON.parse(p);}catch(e){return null;}}
if(p&&typeof p==="object")return p;
let pj=args["--payload"];
if(typeof pj==="string"){try{return JSON.parse(pj);}catch(e){return null;}}
return null;}
function argGet(args,name){
if(!args||typeof args!=="object")return undefined;
const k=name.indexOf("--")===0?name:"--"+name;
if(args[k]!==undefined)return args[k];
if(args[name]!==undefined)return args[name];
return undefined;}
function baseNameOnly(p){
if(!p||typeof p!=="string")return "";
const parts=p.replace(/\\/g,"/").split("/");
return parts[parts.length-1]||p;}
/** 步骤标题用：优先末两段路径，避免过长 */
function pathLeaf(p){
/* 先统一成 `/` 便于切段，切完再按本机习惯还原成 `\`。
   不还原的话，同一个路径在走 pathLeaf 的标题里显示 `E:/test.txt`、
   在直接用原样的标题里显示 `E:\test.txt`，看起来像两个不同的路径。 */
const s=String(p||"").trim().replace(/\\/g,"/");
if(!s)return "";
const parts=s.split("/").filter(Boolean);
if(parts.length<=2)return (parts.join("/")||s).replace(/\//g,"\\");
return parts.slice(-2).join("/").replace(/\//g,"\\");}
function inferLangFromPath(path){
const n=baseNameOnly(String(path||"")).toLowerCase();
const m=n.match(/\.([a-z0-9_+-]+)$/i);
if(!m)return "";
const ext=m[1];
const mp={py:'python',js:'javascript',ts:'typescript',tsx:'typescript',jsx:'javascript',json:'json',yml:'yaml',yaml:'yaml',xml:'xml',html:'html',css:'css',md:'markdown',java:'java',go:'go',rs:'rust',sql:'sql',sh:'bash',bat:'batch',ps1:'powershell',txt:''};
return mp[ext]!==undefined?mp[ext]:"";}
function renderPreviewText(text,lang){
const t=String(text||"");
if(lang)return highlightCode(t,lang);
return escapeHtml(t);
}
function buildToolTitleParts(script,args,full){
function take(text,n){
var s=String(text==null?"":text);
if(full)return s;
return s.length>n?s.slice(0,n):s;
}
function takeDots(text,n){
var s=String(text==null?"":text);
if(full||s.length<=n)return s;
return s.slice(0,n)+"…";
}
const s=(script+"").toLowerCase();
// confirm_id 提交时请求参数纯净（无 path），但预览已把 confirm_id→path 记入缓存；
// 此处仅构造展示视图（副本），不修改原始 args，展示策略与预览/ review 一致（从 args 取路径）
const cid=argGet(args,"confirm_id");
if(cid&&!argGet(args,"path")&&!argGet(args,"source_path")&&!argGet(args,"dest_path")){
const dp=(window.confirmPathCache&&window.confirmPathCache[String(cid).trim()])||"";
if(dp){const merged=Object.assign({},args);merged.path=dp;args=merged;}}
if(s.indexOf("read_file")>=0){
const path=String(argGet(args,"path")||"").trim();
const leaf=pathLeaf(path)||"（未指定 path）";
const ls=argGet(args,"line_start"), le=argGet(args,"line_end");
const sc=argGet(args,"start_column"), ec=argGet(args,"end_column");
const chs=argGet(args,"char_start"), che=argGet(args,"char_end");
let rng="";
if(ls!=null&&le!=null){
if(sc!=null&&ec!=null)rng=" L"+ls+":"+sc+"–"+le+":"+ec;
else rng=" L"+ls+"–"+le;
}else if(chs!=null||che!=null){
rng=" §"+(chs!=null?chs:0)+"–"+(che!=null?che:"EOF");
}
return {main:"读取文件",fname:leaf+rng};}
if(s.indexOf("write_file")>=0){
const path=String(argGet(args,"path")||"").trim();
const leaf=pathLeaf(path)||"（未指定 path）";
const dr=argGet(args,"dry_run");
const dry=dr!==false&&dr!==0;
const co=!!argGet(args,"create_only");
const cx=co?" · create_only":"";
return {main:dry?"预览修改":"提交修改",fname:leaf+cx};}
if(s.indexOf("replace_in_file")>=0){
const path=String(argGet(args,"path")||"").trim();
const leaf=pathLeaf(path)||"（未指定 path）";
const rs=argGet(args,"region_start"), re=argGet(args,"region_end");
const ls=argGet(args,"line_start"), le=argGet(args,"line_end");
const sc=argGet(args,"start_column"), ec=argGet(args,"end_column");
const dr=argGet(args,"dry_run");
const dry=dr!==false&&dr!==0;
const rules=argGet(args,"rules");
let mode="字面替换",extra="";
if(rs!=null&&re!=null){mode="区间";extra=" §"+rs+"–"+re;}
else if(ls!=null&&le!=null&&sc!=null&&ec!=null){mode="矩形";extra=" L"+ls+":"+sc+"–"+le+":"+ec;}
else if(Array.isArray(rules)&&rules.length)mode="规则×"+rules.length;
return {main:dry?"预览修改":"提交修改",fname:leaf+" · "+mode+extra};}
if(s.indexOf("grep_files")>=0){
const root=String(argGet(args,"path")||"").trim();
const leaf=pathLeaf(root)||takeDots(root,36);
const pat=take(argGet(args,"pattern"),40);
const re=!!argGet(args,"regex");
return {main:"搜索"+(re?"（正则）":"（字面）"),fname:leaf+(pat?" · /"+pat+"/":"")};}
if(s.indexOf("find_in_file")>=0){
const path=String(argGet(args,"path")||"").trim();
const leaf=pathLeaf(path)||"（未指定 path）";
const occ=argGet(args,"occurrence");
const re=!!argGet(args,"regex");
const o=occ!=null&&occ!==0?" · 第"+(Number(occ)+1)+"处":"";
return {main:"定位"+(re?"（正则）":"（字面）"),fname:leaf+o};}
if(s.indexOf("read_write")>=0){
const src=pathLeaf(String(argGet(args,"source_path")||""));
const dst=pathLeaf(String(argGet(args,"dest_path")||""));
const ls=argGet(args,"line_start"), le=argGet(args,"line_end");
const chs=argGet(args,"char_start"), che=argGet(args,"char_end");
let rng="";
if(ls!=null&&le!=null)rng=" L"+ls+"–"+le;
else if(chs!=null||che!=null)rng=" §"+(chs!=null?chs:0)+"–"+(che!=null?che:"");
const dr=argGet(args,"dry_run");
const dry=dr!==false&&dr!==0;
return {main:dry?"预览修改":"提交修改",fname:(src||"?")+(dst?" → "+dst:"")+rng};}
if(s.indexOf("delete_file")>=0){
const leaf=pathLeaf(String(argGet(args,"path")||""))||"（未指定 path）";
const dr=argGet(args,"dry_run");
const dry=dr!==false&&dr!==0;
return {main:dry?"预览删除":"删除文件",fname:leaf};}
if(s.indexOf("apply_patch")>=0){
const root=pathLeaf(String(argGet(args,"path")||""))||".";
const dr=argGet(args,"dry_run");
const dry=dr!==false&&dr!==0;
const pf=baseNameOnly(String(argGet(args,"patch_file")||""));
const pt=String(argGet(args,"patch_text")||"");
const hint=pf|| (pt?"内联补丁":"补丁");
return {main:dry?"预览修改":"提交修改",fname:root+" · "+hint};}
if(s.indexOf("run_command")>=0){
const cwd=pathLeaf(String(argGet(args,"cwd")||""));
const cmd=String(argGet(args,"command")||"").replace(/\s+/g," ").trim().slice(0,72);
return {main:"执行命令",fname:(cwd?cwd+" · ":"")+(cmd||"（空命令）")};}
if(s.indexOf("python_inline")>=0){
const cwd=pathLeaf(String(argGet(args,"cwd")||""));
const c0=String(argGet(args,"code")||"").replace(/\s+/g," ").trim();
const c=take(c0,48);
return {main:"执行命令",fname:(cwd?cwd+" · ":"")+(c+(!full&&c0.length>48?"…":"")||"（无 code）")};}
if(s.indexOf("archive")>=0){
const act=String(argGet(args,"action")||"").toLowerCase();
const src=pathLeaf(String(argGet(args,"source")||""))||"（未指定 source）";
const dst=pathLeaf(String(argGet(args,"dest")||""));
return {main:"正在"+(act==="list"?"列出":act==="extract"?"解压":"打包")+"压缩包",fname:src+(dst?" · → "+dst:"")};}
if(s.indexOf("data_table")>=0){
const act=String(argGet(args,"action")||"");
const src=pathLeaf(String(argGet(args,"source")||""))||"表格";
const sh=take(argGet(args,"sheet"),16);
return {main:"处理表格 · "+(act||"?"),fname:src+(sh?" · "+sh:"")};}
if(s.indexOf("todo_list")>=0){
const act=String(argGet(args,"action")||"");
return {main:"Todo-List",fname:act||"query"};}
if(s.indexOf("approval_confirm")>=0){
const d=take(argGet(args,"option_desc"),40);
return {main:"审批",fname:d||"（无描述）"};}
if(s.indexOf("user_confirm")>=0){
const t=take(argGet(args,"title"),40);
return {main:"等待用户确认",fname:t||"（无标题）"};}
if(s.indexOf("run_type")>=0){
const rt=String(argGet(args,"run_type")||"").trim().toLowerCase();
return {main:rt?"切换运行模式":"查询运行模式",fname:rt||"auto/plan/execute"};}
if(s.indexOf("glob_files")>=0){
const root=String(argGet(args,"path")||"");
const glob=String(argGet(args,"glob_pattern")||"*");
const leaf=pathLeaf(root)||takeDots(root,28);
const rec=argGet(args,"recursive");
const et=String(argGet(args,"entry_type")||"").toLowerCase();
const scope=(et==="dir"?"仅目录":et==="all"?"全部":"")+(et==="file"||!et?"文件":"");
return {main:"列出路径"+(scope?"（"+scope+"）":""),fname:leaf+(glob&&glob!=="*"&&glob!=="**/*"?" · "+glob:"")+(rec===false?"":" · 递归")};}
if(s.indexOf("web_fetch")>=0){
const url=String(argGet(args,"url")||"").trim();
return {main:"网页",fname:url};}
if(s.indexOf("file_search")>=0){
const pat=take(argGet(args,"pattern"),40);
const root=String(argGet(args,"path")||"").trim();
const leaf=pathLeaf(root)||takeDots(root,28);
return {main:"全文搜索"+(argGet(args,"regex")?"（正则）":"（字面）"),fname:leaf+(pat?" · /"+pat+"/":"")};}
if(s.indexOf("ip_geolocate")>=0){
const ip=String(argGet(args,"ip")||"").trim();
return {main:"定位公网地区"+(ip?" · "+ip:""),fname:""};}
if(s.indexOf("open_meteo")>=0){
const loc=String(argGet(args,"location")||"").slice(0,20);
const la=String(argGet(args,"latitude")||"").trim();
const lo=String(argGet(args,"longitude")||"").trim();
if(la&&lo)return {main:"查询天气 · "+la+","+lo,fname:""};
return {main:"查询天气"+(loc?" · "+loc:""),fname:""};}
if(s.indexOf("regex_locate")>=0){
const pat=take(argGet(args,"pattern"),48);
const tgt=pathLeaf(String(argGet(args,"path")||""));
const glob=String(argGet(args,"glob_pattern")||"");
return {main:"正则检索",fname:(tgt||"?")+(pat?" · /"+pat+"/":"")+(glob&&glob!=="*"?" · "+glob:"")};}
if(s.indexOf("file_ops")>=0){
const act=String(argGet(args,"action")||"").toLowerCase();
const src=baseNameOnly(String(argGet(args,"source")||""));
const dst=baseNameOnly(String(argGet(args,"dest")||""));
if(act==="delete")return {main:"移入回收站 · "+(src||"见参数"),fname:""};
if(act==="copy")return {main:"复制 · "+src+(dst?" → "+dst:""),fname:""};
if(act==="move")return {main:"移动 · "+src+(dst?" → "+dst:""),fname:""};
if(act==="rename")return {main:"重命名 · "+src+(dst?" → "+dst:""),fname:""};
return {main:(src?"文件操作 · "+src:"文件操作"),fname:""};}
if(s.indexOf("text_diff")>=0){
const lf=baseNameOnly(String(argGet(args,"left_file")||""));
const rf=baseNameOnly(String(argGet(args,"right_file")||""));
if(lf||rf)return {main:"对比 · "+(lf||"?")+" ↔ "+(rf||"?"),fname:""};
return {main:"对比文本",fname:""};}
if(s.indexOf("git_workspace")>=0){
const root=pathLeaf(String(argGet(args,"path")||""))||".";
const mode=String(argGet(args,"mode")||"worktree");
return {main:"查看 Git",fname:root+" · "+mode};}
if(s.indexOf("image_ocr")>=0){
const src=pathLeaf(String(argGet(args,"source")||""))||"（未指定 source）";
const eng=String(argGet(args,"engine")||"auto").toLowerCase();
const reg=String(argGet(args,"region")||"").trim();
const extra=(eng&&eng!=="auto")?" · "+eng:"";
const rg=reg?" · 区域 "+reg:"";
return {main:"识别图片文字",fname:src+extra+rg};}
if(s.indexOf("env_probe")>=0)return {main:"探测运行环境",fname:""};
if(s.indexOf("diagnos")>=0){
const root=pathLeaf(String(argGet(args,"path")||""))||".";
return {main:"统一诊断",fname:root};}
if(s.indexOf("review_conclusion")>=0){
const fn=String(argGet(args,"file_name")||"").trim();
const full=String(argGet(args,"path")||"").trim();
var shown=fn;
if(full&&(!fn||fn===baseNameOnly(full)||(fn.indexOf("/")<0&&fn.indexOf("\\")<0)))shown=full;
return {main:"Review",fname:shown||full};}
if(s.indexOf("file_undo")>=0){
const ac=String(argGet(args,"action")||"").trim();
const fp=pathLeaf(String(argGet(args,"path")||""))||"";
let ts="";
const mid=String(argGet(args,"mod_id")||"").trim();
/* 版本目录名的形状由 file_safety._version_dir_name 产出：`YYYYMMDD_HHMMSS_mmm_序号_随机`。
   按固定形状取，**不靠数段数** —— 名字里增删一段（例如加同毫秒序号）就会取错位置，
   卡片标题上显示的就不再是时刻。 */
if(mid){const mv=/_(\d{6})_\d{3}_\d{4}_[0-9a-z]+$/.exec(mid);if(mv)ts=mv[1].slice(0,2)+":"+mv[1].slice(2,4)+":"+mv[1].slice(4,6);}
const label=ac==="list"?"检查可回滚清单":ac==="diff"?"版本比较":ac==="undo"?"回滚文件":"回滚文件";
// list 与 diff 是只读查询，标题不该像"正在回滚"；时间戳只在挑定某个版本（undo）时才加，
// 否则会读成"回滚到某时刻"
const showTs=(ac==="undo");
return {main:label,fname:fp?fp+(showTs&&ts?" to "+ts:""):(showTs&&ts?"to "+ts:"")};}
if(s.indexOf("session_send")>=0){
const tid=String(argGet(args,"target_id")||"").trim().slice(0,12);
return {main:"多Agent协作"+(tid?" · to "+tid:""),fname:""};}
if(s.indexOf("session_multisend")>=0){
const ch=String(argGet(args,"channel")||"").trim();
const tids=argGet(args,"target_ids");
let grp=ch||"";
if(!grp&&Array.isArray(tids)&&tids.length)grp="组"+(tids.length>1?tids.length+"个":"1个");
return {main:"多Agent协作"+(grp?" · to "+grp:""),fname:""};}
const unk='(unknown)';
if(s===unk)return {main:"无法识别的工具（见下方参数）",fname:""};
/* 兜底：拿得到路径就带上文件名。
   提交类工具（`commit_write`）的请求参数里只有 confirm_id，路径靠上面从
   `confirmPathCache` 合并进来；若各工具分支没接管，这里补上，否则标题只有
   工具名、看不出改的是哪个文件。 */
{const p=String(argGet(args,"path")||argGet(args,"dest_path")||argGet(args,"source_path")||"").trim();
if(p){const leaf=pathLeaf(p);if(leaf)return {main:toolZh(script),fname:leaf};}}
return {main:toolZh(script),fname:""};}
function linesDiff(oldT,newT){
const A=String(oldT??"").split("\n");
const B=String(newT??"").split("\n");
const out=[];
let i=0,j=0;
while(i<A.length||j<B.length){
if(i<A.length&&j<B.length&&A[i]===B[j]){out.push({t:" ",l:A[i]});i++;j++;}
else if(j<B.length&&(i>=A.length||A[i]!==B[j])){out.push({t:"+",l:B[j]});j++;}
else if(i<A.length){out.push({t:"-",l:A[i]});i++;}
else{out.push({t:"+",l:B[j]});j++;}
}
return out;}
function renderDiffRows(container,oldT,newT){
container.innerHTML="";
for(const r of linesDiff(oldT,newT)){
const d=document.createElement("div");
if(r.t==="-")d.className="d-del";
else if(r.t==="+")d.className="d-add";
else d.className="d-eq";
d.innerHTML=diffRowInnerHtml(r);
container.appendChild(d);
}}
function unifiedDiffRowClass(raw){
var s=String(raw||"");
if(s.startsWith("---"))return "d-meta";
if(s.startsWith("+++"))return "d-meta";
if(s.indexOf("@@")===0)return "d-meta";
if(s.startsWith("+"))return "d-add";
if(s.startsWith("-"))return "d-del";
return "d-eq";}
function renderUnifiedDiffRows(container,lines){
container.innerHTML="";
if(!Array.isArray(lines))return;
for(var i=0;i<lines.length;i++){
var L=lines[i]==null?"":String(lines[i]);var cls=unifiedDiffRowClass(L);
var el=document.createElement("div");
el.className=cls;
if(cls==="d-meta"){el.textContent=L;}
else if(L.charAt(0)==="-"){el.innerHTML=diffRowInnerHtml({t:"-",l:L.substring(1)});}
else if(L.charAt(0)==="+"){el.innerHTML=diffRowInnerHtml({t:"+",l:L.substring(1)});}
else{el.innerHTML=diffRowInnerHtml({t:" ",l:L.replace(/^\s/,"")});}
container.appendChild(el);}}
// 全局滚动代理 — document 捕获阶段统一处理所有 scroll，无需对元素逐个注册
(function(){
  document.addEventListener("scroll",function(e){
    var el=e.target;
    if(!el||el.nodeType!==1)return;
    // 程序化滚动（scrollToBottom发起的）→ 不设免疫期
    if(el._ascrollPG){el._ascrollPG=false;return;}
    // 用户手动滚动 → 刷新免疫期，同时根据当前位置设跟随开关
    el._ascrollTM=Date.now();
    if(el.scrollHeight-el.scrollTop-el.clientHeight>60){
      el._ascrollStop=true;
    }else{
      el._ascrollStop=false;
    }
  },true);
})();

function scrollToBottom(el,force){
  if(!el)return;
  // force：初始化强制滚动，跳过所有检查
  if(force){
    el.scrollTop=el.scrollHeight;
    return;
  }
  // 200ms免疫期：避免与用户主动滚动竞争控制权
  if(el._ascrollTM&&Date.now()-el._ascrollTM<200)return;
  // _ascrollStop===true表示已取消跟随；false/undefined均表示跟随
  if(el._ascrollStop===true)return;
  // 设程序化滚动标记，scroll事件处理器跳过免疫期
  el._ascrollPG=true;
  el.scrollTop=el.scrollHeight;
}
function isNearBottom(el,threshold=60){
  if(!el) return true;
  return el.scrollHeight-el.scrollTop-el.clientHeight<threshold;
}
function scrollMsgsToBottom(){scrollToBottom(msgs);}
function scrollMsgsToBottomAfterLayout(){scrollToBottomAfterLayout(msgs,true);}
function calcDiffStats(oldT,newT){var A=String(oldT??'').split('\n'),B=String(newT??'').split('\n');var a=0,d=0,i=0,j=0;while(i<A.length||j<B.length){if(i<A.length&&j<B.length&&A[i]===B[j]){i++;j++;}else if(j<B.length&&(i>=A.length||A[i]!==B[j])){a++;j++;}else if(i<A.length){d++;i++;}else{a++;j++;}}return {add:a,del:d};}
function diffLabel(s){return(s.del>0?' <span style="color:#f48771">-'+s.del+'</span>':'')+(s.add>0?' <span style="color:#89d185">+'+s.add+'</span>':'');}
function diffLabelPlain(s){return(s.del>0?' -'+s.del:'')+(s.add>0?' +'+s.add:'');}

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
   在界面上**一点预览都没有**（工具返回里明明带着 `_change.diff`）。
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
function analysisFollowupPhrase(script,args){
const s=(script+"").toLowerCase();
if(s.indexOf("web_fetch")>=0)return "抓取内容";
if(s.indexOf("file_search")>=0)return "搜索结果";
if(s.indexOf("grep_files")>=0)return "检索结果";
if(s.indexOf("image_ocr")>=0)return "识别结果";
if(s.indexOf("ip_geolocate")>=0)return "地理定位";
if(s.indexOf("open_meteo")>=0)return "天气数据";
if(s.indexOf("replace_in_file")>=0)return "预览修改";
if(s.indexOf("glob_files")>=0)return "目录结果";
if(s.indexOf("regex_locate")>=0)return "检索结果";
if(s.indexOf("file_ops")>=0)return "文件操作结果";
if(s.indexOf("apply_patch")>=0)return "补丁结果";
if(s.indexOf("text_diff")>=0)return "对比结果";
if(s.indexOf("git_workspace")>=0)return "工作区状态";
if(s.indexOf("diagnos")>=0)return "诊断结果";
if(s.indexOf("run_command")>=0)return "命令输出";
if(s.indexOf("python_inline")>=0)return "内联代码输出";
return "工具调度";}
function clearLlmAnim(){
if(lastLlm&&lastLlm.dotsTimer){clearInterval(lastLlm.dotsTimer);lastLlm.dotsTimer=null;}}
/* **当前无调用方**：它把「模型只产出了思考、没有正文」时的
   `lastLlm.reasoningText` 在 `done` 时刻兜底追加成回答。
   追加的内容是**实时渲染的产物、不是数据** —— 刷新后走 `loadConversationHistory()`，
   那段内容**会消失**，因此它不构成一条「回答」。
   思考**另有归宿**：`reasoning_delta` → `appendReasoningDelta()` →
   右侧步骤面板的思考区（`lastLlm.thPb`）。
   追加还有一处副作用：`done` 时 `streamAssistantText` 已被此前的 `assistant` 分支
   （`finalizeAssistantStream()` 会清空它）清掉，守卫会放行，
   思考于是成为**对话区里的又一个回答气泡**。
   **函数体保留**：`lastLlm.reasoningText` 仍被工具卡合并思考面板（`onToolStart`）读取。 */
function promoteReasoningToChatIfNeeded(){
var rt=(lastLlm&&lastLlm.reasoningText||"").trim();
if(!rt)return;
if((streamAssistantText||"").trim())return;
appendAssistantDelta(rt);}
function appendReasoningDelta(ev){
var d=String(ev.delta||"");if(!d)return;if(!lastLlm)return;if(ev.round!=null&&lastLlm.round!=null&&ev.round!==lastLlm.round)return;
lastLlm.reasoningText=(lastLlm.reasoningText||"")+d;if(lastLlm.thLb&&lastLlm.thPb){lastLlm.thLb.style.display="block";lastLlm.thPb.style.display="block";lastLlm.thPb.textContent=lastLlm.reasoningText;scrollToBottom(lastLlm.thPb);}paintChatThink();}
function applyReasoningSync(ev){
var t=String(ev.text||"");if(!lastLlm)return;if(ev.round!=null&&lastLlm.round!=null&&ev.round!==lastLlm.round)return;
lastLlm.reasoningText=t;if(lastLlm.thLb&&lastLlm.thPb){lastLlm.thLb.style.display="block";lastLlm.thPb.style.display="block";lastLlm.thPb.textContent=lastLlm.reasoningText;scrollToBottom(lastLlm.thPb);}paintChatThink();}
function finishLlmTitle(ok){
if(!lastLlm||!lastLlm.msgSpan)return;
if(lastLlm.dotsTimer){clearInterval(lastLlm.dotsTimer);lastLlm.dotsTimer=null;}
lastLlm.dotsSpan.textContent="";
if(ok){lastLlm.msgSpan.textContent="思考完毕";}
else{lastLlm.msgSpan.textContent="思考异常";}
sealChatThinkElapsed();
if(lastLlm.chatThink){lastLlm.chatThink.classList.remove("is-running");if(!ok)lastLlm.chatThink.classList.add("is-bad");chatToolSyncStatusTitle(lastLlm.chatThink);}}
function addLlmRound(r){
hideChatLoading();
stepSeq++;
const n=r||1;
llmStreamBuffer.round=n;llmStreamBuffer.reqHtml="";llmStreamBuffer.resHtml="";llmStreamBuffer.consumed=false;
if(n>1&&streamAssistantEl){pendingDeltaSeparator=true;}
let baseMsg="正在思考中";
if(n>1){const tail=lastAnalysisTail||"工具调度";baseMsg="分析"+tail;lastAnalysisTail="";}
if(!showToolSteps()){
lastLlm={tag:_muteEl(),msgSpan:_muteEl(),dotsSpan:_muteEl(),dotsTimer:null,round:n,thLb:null,thPb:null,reasoningText:"",reqLb:null,reqPb:null,resLb:null,resPb:null,cardEl:null,stepNum:stepSeq,chatThink:null,chatThinkFull:null,chatThinkStartedAt:Date.now()};
return;
}
const c=document.createElement("div");c.className="step card";
const h=document.createElement("div");h.className="ch ch-toggle";h.setAttribute("role","button");
const left=document.createElement("div");left.className="tit tit-row";
const ic=document.createElement("span");ic.className="step-ico";ic.textContent="🧠";ic.title="思考推理";
const sn=document.createElement("span");sn.className="step-num";sn.textContent="步骤 "+stepSeq+"：";
const msgSpan=document.createElement("span");msgSpan.className="step-llm-msg";msgSpan.textContent=baseMsg;
const dotsSpan=document.createElement("span");dotsSpan.className="step-dots";dotsSpan.textContent="";
left.appendChild(ic);left.appendChild(sn);left.appendChild(msgSpan);left.appendChild(dotsSpan);
const tag=document.createElement("span");tag.className="tag tag-run";tag.textContent="进行中";
h.appendChild(left);h.appendChild(tag);
const body=document.createElement("div");body.className="card-body";
const inner=document.createElement("div");inner.className="card-body-inner";
const thLb=document.createElement("p");thLb.className="lbl reasoning-section-lbl";thLb.textContent="思考过程";thLb.style.display="none";
const thPb=document.createElement("pre");thPb.className="sub reasoning-pre";thPb.style.display="none";thPb.textContent="";
const rqLb=document.createElement("p");rqLb.className="lbl";rqLb.textContent="请求";rqLb.style.display="none";
const rqPb=document.createElement("pre");rqPb.className="sub";rqPb.style.display="none";rqPb.textContent="";
const rsLb=document.createElement("p");rsLb.className="lbl";rsLb.textContent="响应";rsLb.style.display="none";
const rsPb=document.createElement("pre");rsPb.className="sub";rsPb.style.display="none";rsPb.textContent="";
inner.appendChild(thLb);inner.appendChild(thPb);inner.appendChild(rqLb);inner.appendChild(rqPb);inner.appendChild(rsLb);inner.appendChild(rsPb);body.appendChild(inner);
c.appendChild(h);c.appendChild(body);
h.onclick=function(){c.classList.toggle("open");};
appendStep(c);
let d=0;
const timer=setInterval(function(){d=(d+1)%4;dotsSpan.textContent=".".repeat(d);},400);
lastLlm={tag:tag,msgSpan:msgSpan,dotsSpan:dotsSpan,dotsTimer:timer,round:n,thLb:thLb,thPb:thPb,reasoningText:"",reqLb:rqLb,reqPb:rqPb,resLb:rsLb,resPb:rsPb,cardEl:c,stepNum:stepSeq,chatThink:null,chatThinkFull:null,chatThinkStartedAt:Date.now()};
}
function onLlmRequest(ev){
if(!lastLlm)return;
if(ev&&ev.round!=null&&lastLlm.round!=null&&ev.round!==lastLlm.round)return;
var j=JSON.stringify(ev.params||{},null,2);
var h=highlightJson(j);
llmStreamBuffer.reqHtml=h;
if(lastLlm.reqLb&&lastLlm.reqPb){lastLlm.reqLb.style.display="block";lastLlm.reqPb.style.display="block";lastLlm.reqPb.textContent=j;
llmStreamBuffer.reqHtml=j;}
}
function onLlmResponse(ev){
if(!lastLlm)return;
if(ev&&ev.round!=null&&lastLlm.round!=null&&ev.round!==lastLlm.round)return;
var j=JSON.stringify(ev.params||{},null,2);
var h=highlightJson(j);
llmStreamBuffer.resHtml=j;
if(lastLlm.resLb&&lastLlm.resPb){lastLlm.resLb.style.display="block";lastLlm.resPb.style.display="block";lastLlm.resPb.textContent=j;}
}
function createToolAnalysisBlock(){
var wrap=document.createElement("div");
wrap.className="llm-merge-block";
var rqLb=document.createElement("p");rqLb.className="lbl";rqLb.textContent="分析的请求";rqLb.style.display="none";
var rqPb=document.createElement("pre");rqPb.className="sub";rqPb.style.display="none";rqPb.textContent="";
var rsLb=document.createElement("p");rsLb.className="lbl";rsLb.textContent="分析的响应";rsLb.style.display="none";
var rsPb=document.createElement("pre");rsPb.className="sub";rsPb.style.display="none";rsPb.textContent="";
wrap.appendChild(rqLb);wrap.appendChild(rqPb);wrap.appendChild(rsLb);wrap.appendChild(rsPb);
return wrap;
}
function fillAnalysisBlockFromBuffer(wrap){
if(!wrap)return;
var rqLb=wrap.children[0],rqPb=wrap.children[1],rsLb=wrap.children[2],rsPb=wrap.children[3];
if(llmStreamBuffer.reqHtml&&rqLb&&rqPb){rqLb.style.display="block";rqPb.style.display="block";rqPb.textContent=llmStreamBuffer.reqHtml;}
if(llmStreamBuffer.resHtml&&rsLb&&rsPb){rsLb.style.display="block";rsPb.style.display="block";rsPb.textContent=llmStreamBuffer.resHtml;}
}
function removeMergedLlmCard(){
if(!lastLlm||!lastLlm.cardEl)return;
clearLlmAnim();
var el=lastLlm.cardEl;
var ix=pendingStepEls.indexOf(el);
if(ix>=0)pendingStepEls.splice(ix,1);
else if(el.parentNode)el.parentNode.removeChild(el);
try{el.remove();}catch(e){}
lastLlm=null;
}
function flushPendingToolTags(){
for(var i=0;i<pendingToolTags.length;i++){
var o=pendingToolTags[i];
if(o&&o.tag){
o.tag.textContent=o.ok?"Done":"Fail";
o.tag.className="tag "+(o.ok?"ok":"bad");
}
}
pendingToolTags=[];
}
function abortPendingToolTags(){
for(var j=0;j<pendingToolTags.length;j++){
var p=pendingToolTags[j];
if(p&&p.tag){p.tag.innerHTML="";p.tag.textContent="Fail";p.tag.className="tag bad";}
}
pendingToolTags=[];
}
function stopPendingToolTags(){
for(var j=0;j<pendingToolTags.length;j++){
var p=pendingToolTags[j];
if(p&&p.tag){p.tag.innerHTML="";p.tag.textContent="Stoped";p.tag.className="tag stoped";}
}
pendingToolTags=[];
}
function stopOpenToolTags(){
try{toolOpen.forEach(function(o){if(!o)return;if(o.progressBadge&&o.progressBadge.parentNode)o.progressBadge.parentNode.removeChild(o.progressBadge);if(o.fileSpan&&o.fileSpan.parentNode)o.fileSpan.parentNode.removeChild(o.fileSpan);if(o.spinWrap&&o.spinWrap.parentNode)o.spinWrap.parentNode.removeChild(o.spinWrap);if(o.tag){o.tag.innerHTML="";o.tag.textContent="Stoped";o.tag.className="tag stoped";}});}catch(e){}
toolOpen.clear();
}
function markCurrentTurnStoped(){
stopPendingToolTags();stopOpenToolTags();if(lastLlm&&lastLlm.tag){finishLlmTitle(false);lastLlm.tag.innerHTML="";lastLlm.tag.textContent="Stoped";lastLlm.tag.className="tag stoped";lastLlm=null;}pendingStepEls=[];
}
function isHostProgressToolScript(script){
var s=String(script||"").toLowerCase();
return s.indexOf("file_search")>=0||s.indexOf("grep_files")>=0||s.indexOf("regex_locate")>=0||s.indexOf("run_command")>=0||s.indexOf("python_inline")>=0;
}
function isStreamOutputToolScript(script){
var s=String(script||"").toLowerCase();
return s.indexOf("run_command")>=0||s.indexOf("python_inline")>=0;
}
function isRunCommandToolScript(script){
return String(script||"").toLowerCase().indexOf("run_command")>=0;
}
async function submitCommandInputToServer(cid,tid,input){
try{
var r=await fetch("/api/chat/command-input",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:cid,tool_call_id:tid,input:input})});
return r.ok;
}catch(e){return false;}
}
function ensureRunCommandLivePanel(o){
if(!o||o.liveOutPre)return;
if(!o.resPb)return;
o.resLb.style.display="block";
o.resPb.style.display="block";
o.resLb.textContent="实时输出";
o.resPb.className="sub chat-run-live-out";
o.liveOutPre=o.resPb;
}
// 在左侧对话区创建/获取“执行命令脚本 + 执行结果”卡片；执行结果区随 stdout 增量刷新
function ensureChatRunCard(o){
if(!showToolItems())return null;
if(!o)return null;
if(o.chatToolRow)return o.chatToolRow;
if(o.chatRunCard&&o.chatRunCard.parentNode)return o.chatRunCard;
var _cardDiv=document.createElement("div");_cardDiv.className="b a";
var _cardTitle=(o.stepTitle&&o.stepTitle.trim())?escapeHtml(o.stepTitle.trim()):"执行命令脚本";
var _cmdRaw=(o.args&&(o.args.command||o.args.code))||"";
var _cmdLang=detectScriptLang(_cmdRaw,(o.args&&(o.args.language||o.args.lang))||"");
var _cmdCls=hljsCodeClass(_cmdLang);
_cardDiv.innerHTML='<div class="chat-diff-card"><div class="chat-diff-cap">'+_cardTitle+'<span class="chat-run-status" style="margin-left:8px;font-size:12px;font-weight:normal;color:#e0a300"></span></div><div class="diff-unified chat-run-wrap chat-run-cmd-block"><pre class="chat-run-pre chat-run-pre--cmd"><code'+(_cmdCls?' class="'+_cmdCls+'"':'')+'>'+highlightCode(_cmdRaw,_cmdLang)+'</code></pre></div><div class="chat-diff-cap chat-diff-cap--sect">执行结果</div><pre class="chat-run-pre chat-run-pre--out"><code></code></pre></div>';
if(streamAssistantEl){streamAssistantEl.after(_cardDiv);streamAssistantEl=null;streamAssistantText="";}else{msgs.appendChild(_cardDiv);}
o.chatRunCard=_cardDiv;
o.chatRunOutPre=_cardDiv.querySelector(".chat-run-pre--out code");
o.chatRunStatus=_cardDiv.querySelector(".chat-run-status");
startChatRunCountdown(o);
scrollMsgsToBottom();
return _cardDiv;
}
// 标题后状态注记 + 基于 timeout_sec 的倒计时（等待执行结果中…剩余 Ns）
function startChatRunCountdown(o){
if(!o||o._chatRunTimer)return;
var _to=0;try{_to=parseInt((o.args&&o.args.timeout_sec)||0,10)||0;}catch(e){_to=0;}
var _start=Date.now();
function _tick(){
if(!o.chatRunStatus||!o.chatRunCard||!o.chatRunCard.parentNode){stopChatRunCountdown(o);return;}
var _elapsed=Math.floor((Date.now()-_start)/1000);
if(_to>0){
var _left=_to-_elapsed;
if(_left<0)_left=0;
o.chatRunStatus.textContent="⏳ 等待执行结果中…（剩余 "+_left+"s / 超时 "+_to+"s）";
}else{
o.chatRunStatus.textContent="⏳ 等待执行结果中…（已用时 "+_elapsed+"s）";
}
}
_tick();
o._chatRunTimer=setInterval(_tick,1000);
}
function stopChatRunCountdown(o){
if(o&&o._chatRunTimer){try{clearInterval(o._chatRunTimer);}catch(e){}o._chatRunTimer=null;}
}
// 增量刷新对话区卡片的执行结果文本
function updateChatRunCardOutput(o,text){
if(!o)return;
var s=text!=null?String(text):"";
if(o.chatToolRow){
if(o.chatRunOutPre){o.chatRunOutPre.textContent=s;var pane=o.chatRunOutPre.closest&&o.chatRunOutPre.closest(".chat-tool-pane");if(pane)pane.scrollTop=pane.scrollHeight;}
return;
}
if(!showToolItems())return;
if(!o.chatRunCard||!o.chatRunCard.parentNode)ensureChatRunCard(o);
if(o.chatRunOutPre){o.chatRunOutPre.textContent=s;scrollMsgsToBottom();}
}
// 命令结束：停止倒计时，标题状态置为完成/失败
function finalizeChatRunCard(o,ok){
if(!o)return;
stopChatRunCountdown(o);
if(o.chatRunStatus){o.chatRunStatus.textContent=ok?"✓ 执行完成":"✗ 执行结束（失败）";
/* 颜色走类名：写死 #3fb950/#f85149 是深色主题的值，浅底上绿/红对比不足 */
o.chatRunStatus.classList.toggle("run-ok",!!ok);o.chatRunStatus.classList.toggle("run-bad",!ok);}
}
function renderRunCommandInputBar(o,ev){
var card=findStepCardForToolCall(String(ev.tool_call_id||"").trim());
var host=card||(o&&o.chatToolRow)||null;
if(!host||o.cmdInputBar)return;
var ai=ev.awaiting_input||{};
var title=String(ai.title||"命令需要确认").trim();
var opts=Array.isArray(ai.options)&&ai.options.length?ai.options:["Y","N"];
var bar=document.createElement("div");
bar.className="cmd-input-bar";
/* 样式全在 CSS 的 .cmd-input-bar 里（两套主题各一份），JS 不再写死深色 */
var cap=document.createElement("div");
cap.className="cmd-input-cap";
cap.textContent=title;
bar.appendChild(cap);
var row=document.createElement("div");
row.style.cssText="display:flex;flex-wrap:wrap;gap:8px;align-items:center";
opts.forEach(function(opt){
var btn=document.createElement("button");
btn.type="button";
btn.textContent=opt;
btn.className="cmd-input-btn";
btn.onclick=function(){
var cid=normalizeConversationId(ev.conversation_id||activeConversationId);
var tid=String(ev.tool_call_id||"").trim();
submitCommandInputToServer(cid,tid,opt);
if(o.tag){o.tag.textContent="已发送 "+opt;o.tag.className="tag tag-run";}
try{bar.remove();}catch(e){}o.cmdInputBar=null;
};
row.appendChild(btn);
});
var hint=document.createElement("span");
hint.className="cmd-input-hint";
hint.textContent="（也可在下方输入框自定义后发送）";
row.appendChild(hint);
var custom=document.createElement("input");
custom.type="text";
custom.placeholder="自定义输入，如 Y";
custom.className="cmd-input-field";
var sendBtn=document.createElement("button");
sendBtn.type="button";
sendBtn.textContent="发送";
sendBtn.onclick=function(){
var v=String(custom.value||"").trim();
if(!v)return;
var cid=normalizeConversationId(ev.conversation_id||activeConversationId);
var tid=String(ev.tool_call_id||"").trim();
submitCommandInputToServer(cid,tid,v);
try{bar.remove();}catch(e){}o.cmdInputBar=null;
};
row.appendChild(custom);
row.appendChild(sendBtn);
bar.appendChild(row);
var body=host.querySelector(".card-body-inner")||host.querySelector(".card-body")||host.querySelector(".chat-tool-body");
if(body)body.appendChild(bar);
else host.appendChild(bar);
if(o.chatToolRow&&host===o.chatToolRow){
o.chatToolRow.classList.add("is-open");
var head=o.chatToolRow.querySelector(".chat-tool-head");
if(head)head.setAttribute("aria-expanded","true");
}
o.cmdInputBar=bar;
}
function onToolStart(ev){
/* 目标工具的**查询类调用不进步骤区**。
   模型为了判断"目标还在不在、要不要继续"会每轮问一次，
   这类调用会刷出大量同名的「目标 Done」卡，把真正的执行步骤挤下去。
   这类调用是模型的自查，不是对外动作，用户不需要逐条看。
   判据只看 action：`get`（默认）是只读查询；create/update/pause/resume/done/delete
   是真实状态变更，仍然建卡 —— 那是用户该知道的。 */
var _gs=String(ev.script||"").toLowerCase();
if(_gs==="goal"){
var _ga=String((ev.args&&ev.args.action)||"get").trim().toLowerCase();
if(_ga==="get"||_ga==="")return;
}
if(!anyToolThisTurn){anyToolThisTurn=true;}
if(!showToolSteps()){beginChatToolOnly(ev);return;}
var merged=!!(lastLlm&&lastLlm.cardEl&&!llmStreamBuffer.consumed);
var mergeKeepOpen=merged&&lastLlm.cardEl?lastLlm.cardEl.classList.contains("open"):false;
var dispStep;
if(merged){dispStep=lastLlm.stepNum!=null?lastLlm.stepNum:stepSeq;}
else{stepSeq++;dispStep=stepSeq;}
if(!merged){flushPendingSteps();}
const tid=ev.tool_call_id!=null&&String(ev.tool_call_id).trim()!==""?String(ev.tool_call_id).trim():String(Math.random());
const tp=buildToolTitleParts(ev.script,ev.args||{});
const _stt=String(ev.step_title||"").trim();
if(_stt){
const _det=String(tp.fname||"").trim();
tp.main=_stt;
tp.fname=_det;}
const c=document.createElement("div");c.className="step card";c.setAttribute("data-tool-call-id", tid);
const h=document.createElement("div");h.className="ch ch-toggle";h.setAttribute("role","button");
const left=document.createElement("div");left.className="tit tit-row";
const ic=document.createElement("span");ic.className="step-ico";ic.textContent=toolIco(ev.script,ev.args||{});
const num=document.createElement("span");num.className="step-num";num.textContent="步骤 "+dispStep+"：";
const tx=document.createElement("span");tx.className="step-title-wrap";
const txM=document.createElement("span");txM.textContent=tp.main;tx.appendChild(txM);
if(tp.fname){const txDot=document.createElement("span");txDot.textContent=" · ";tx.appendChild(txDot);const txF=document.createElement("span");txF.className="step-fname";txF.textContent=tp.fname;tx.appendChild(txF);}
let spinWrap=null;
if((ev.script||"").toLowerCase().indexOf("web_fetch")>=0){spinWrap=document.createElement("span");spinWrap.className="step-inline-spin";spinWrap.innerHTML="<span class=\"step-spinner\" title=\"加载中\"></span>";tx.appendChild(spinWrap);}
if(isHostProgressToolScript(ev.script)){spinWrap=document.createElement("span");spinWrap.className="step-inline-spin";spinWrap.innerHTML="<span class=\"step-spinner\" title=\"加载中\"></span>";tx.appendChild(spinWrap);}
left.appendChild(ic);left.appendChild(num);left.appendChild(tx);
const tag=document.createElement("span");tag.className="tag tag-run";tag.textContent="运行中";
h.appendChild(left);h.appendChild(tag);
const body=document.createElement("div");body.className="card-body";
const inner=document.createElement("div");inner.className="card-body-inner";
const la=document.createElement("p");la.className="lbl";la.textContent="请求";
const pa=document.createElement("pre");pa.className="sub";pa.textContent=JSON.stringify(ev.args||{},null,2);
const pv=document.createElement("div");pv.className="preview-slot";pv.style.display="none";
const lb=document.createElement("p");lb.className="lbl";lb.textContent="响应";lb.style.display="none";
const pb=document.createElement("pre");pb.className="sub tool-res";pb.style.display="none";pb.textContent="";
if(isStreamOutputToolScript(ev.script)){lb.textContent="实时输出";lb.style.display="block";pb.style.display="block";pb.className="sub tool-res chat-run-live-out";pb.textContent="（等待输出…）";}
inner.appendChild(la);inner.appendChild(pa);inner.appendChild(pv);inner.appendChild(lb);inner.appendChild(pb);
if(merged){if(lastLlm&&(lastLlm.reasoningText||"").length>0){var rw=document.createElement("div");rw.className="reasoning-block";var rl=document.createElement("p");rl.className="lbl reasoning-section-lbl";rl.textContent="思考过程";var rp=document.createElement("pre");rp.className="sub reasoning-pre";rp.textContent=lastLlm.reasoningText;rw.appendChild(rl);rw.appendChild(rp);inner.insertBefore(rw,inner.firstChild);}var aw=createToolAnalysisBlock();fillAnalysisBlockFromBuffer(aw);inner.appendChild(aw);removeMergedLlmCard();llmStreamBuffer.consumed=true;}
flushPendingSteps();
body.appendChild(inner);
c.appendChild(h);c.appendChild(body);
h.onclick=function(){c.classList.toggle("open");};
appendStep(c);if(mergeKeepOpen)c.classList.add("open");toolOpen.set(tid,{tag:tag,resLb:lb,resPb:pb,previewSlot:pv,args:ev.args||{},script:ev.script||"",spinWrap:spinWrap,stepTitle:_stt,fileSpan:null,progressBadge:null,liveOutPre:isStreamOutputToolScript(ev.script)?pb:null,cmdInputBar:null,chatRunCard:null,chatRunOutPre:null,chatToolRow:null,chatToolRes:null});
if(showToolItems())mountChatToolItem(toolOpen.get(tid));
if(isStreamOutputToolScript(ev.script)){var _opened=toolOpen.get(tid);if(!_opened||!_opened.chatToolRow)ensureChatRunCard(_opened);}}

function onToolProgress(ev){
var tid=String(ev.tool_call_id!=null?ev.tool_call_id:"").trim();
var o=tid&&toolOpen.get(tid);
if(!o)return;
if(isStreamOutputToolScript(o.script)){
ensureRunCommandLivePanel(o);
if(o.tag&&o.tag.parentNode)o.tag.textContent="进行中 "+(ev.elapsed_sec!=null?ev.elapsed_sec+"s":"");
/* 进度帧的正文是增量 `text`（stdout/stderr 各一块）。
   旧字段 `stdout_tail` 若还在，则它已是拼好的全文，直接换上。 */
var tail=ev.stdout_tail!=null?String(ev.stdout_tail):(ev.stdoutTail!=null?String(ev.stdoutTail):"");
var shown=tail;
if(!shown){
var chunk=String(ev.text!=null?ev.text:"");
if(chunk){
var el=o.chatRunOutPre||o.liveOutPre;
var cur=el?String(el.textContent||""):"";
if(cur==="（等待输出…）"||cur==="（等待结果…）")cur="";
shown=cur+chunk;
}
}
if(shown){
if(o.liveOutPre){o.liveOutPre.textContent=shown;scrollMsgsToBottom();}
updateChatRunCardOutput(o,shown);
}
if(isRunCommandToolScript(o.script)&&ev.awaiting_input)renderRunCommandInputBar(o,ev);
return;
}
if(!isHostProgressToolScript(o.script))return;
var sc=ev.scanned;
var te=ev.totalEstimated;
var _rawCf=ev.currentFile;if(_rawCf==null||_rawCf==="")_rawCf=ev.current_file;var _cfOnly=String(_rawCf!=null?_rawCf:"").trim();
if(sc==null&&!_cfOnly)return;
if(o.tag&&o.tag.parentNode)o.tag.textContent="进行中";
var card=findStepCardForToolCall(tid);
if(!card)return;
var titleWrap=card.querySelector(".step-title-wrap");
if(!titleWrap)return;
if(sc!=null){
var progSpan=titleWrap.querySelector(".progress-badge");
if(!progSpan){progSpan=document.createElement("span");progSpan.className="progress-badge";progSpan.style.cssText="margin-left:8px;font-size:12px;color:#888;vertical-align:middle";var _spin=o.spinWrap;if(_spin&&_spin.parentNode===titleWrap)titleWrap.insertBefore(progSpan,_spin);else titleWrap.appendChild(progSpan);}
o.progressBadge=progSpan;
var _badgeTxt="已检查 "+sc+" 个文件";
if(te!=null&&Number(te)>0)_badgeTxt+=" / ~"+te;
progSpan.textContent=_badgeTxt;
}
if(!o.spinWrap){var _sp=document.createElement("span");_sp.className="step-inline-spin";_sp.style.cssText="margin-left:4px;vertical-align:middle";_sp.innerHTML="<span class=\"step-spinner\"></span>";titleWrap.appendChild(_sp);o.spinWrap=_sp;}
if(!o.fileSpan){var _fs=document.createElement("span");_fs.className="step-current-file";_fs.style.cssText="display:inline-block;margin-left:6px;font-size:12px;color:#aaa;max-width:min(360px,55vw);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:middle";titleWrap.appendChild(_fs);o.fileSpan=_fs;}
if(o.fileSpan){o.fileSpan.textContent=_cfOnly;if(_cfOnly)o.fileSpan.title=_cfOnly;else{try{o.fileSpan.removeAttribute("title");}catch(e){o.fileSpan.title="";}}}
}

function resetTurnState(){closeUserConfirmCardHost();clearLlmAnim();hideChatLoading();lastLlm=null;llmStreamBuffer={round:null,reqHtml:"",resHtml:"",consumed:false};pendingToolTags=[];lastAnalysisTail="";try{toolOpen.forEach(function(o){stopChatRunCountdown(o);});}catch(e){}toolOpen.clear();anyToolThisTurn=false;pendingStepEls=[];streamAssistantEl=null;streamAssistantText="";pendingDeltaSeparator=false;seenDispatchTitle="";endedAwaitingUserConfirm=false;}
function resetSteps(){resetTurnState();stepSeq=0;}

function onToolEnd(ev){const tid=String(ev.tool_call_id!=null?ev.tool_call_id:"").trim();
const o=tid&&toolOpen.get(tid);if(!o)return;
if(o.fileSpan&&o.fileSpan.parentNode){try{o.fileSpan.parentNode.removeChild(o.fileSpan);}catch(_e2){}}o.fileSpan=null;
if(o.spinWrap&&o.spinWrap.parentNode){o.spinWrap.parentNode.removeChild(o.spinWrap);}o.spinWrap=null;
lastAnalysisTail=analysisFollowupPhrase(o.script,o.args||{});
const ok=!!ev.ok;o.tag.innerHTML="";
o.tag.textContent="进行中";
o.tag.className="tag tag-run";
/* **立即写终态标签**。
   若把标签 push 进 `pendingToolTags`、等 `llm_done` 才 flush，
   一轮里多个工具时，已结束的工具会一直显示「进行中」直到整轮结束。
   `ok` 来自真实的工具结果（`tool_end.ok`），此刻就能定终态。 */
o.tag.textContent=(!!ok||!!ev.user_confirm_required||!!ev.approval_required)?"Done":"Fail";
o.tag.className="tag "+((!!ok||!!ev.user_confirm_required||!!ev.approval_required)?"ok":"bad");
if(ev.user_confirm_required||ev.approval_required){o.tag.textContent="待确认";o.tag.className="tag tag-run";}
o.resLb.style.display="block";o.resPb.style.display="block";if(ev.user_confirm_required){try{var _pj=JSON.parse(ev.preview||"{}");var _em=_pj&&_pj.error&&_pj.error.message?String(_pj.error.message):"";var _em2=_em.indexOf("\n\n--help:")>=0?_em.split("\n\n--help:")[0].trim():_em;var slim={ok:_pj.ok,data:_pj.data,error:_pj.error?{code:_pj.error.code,type:_pj.error.type,message:_em2,hint:_pj.error.hint,retryable:_pj.error.retryable}:null};o.resPb.textContent=JSON.stringify(slim,null,2);}catch(e){o.resPb.textContent=ev.preview||"";}}else{try{var _pj2=JSON.parse(ev.preview||"{}");o.resPb.textContent=JSON.stringify(_pj2,null,2);}catch(e){o.resPb.textContent=ev.preview||"";}}
fillToolPreview(o,ev);
/* diff 预览画到**对话区**（步骤卡的预览槽放不下、默认也收起）。
   放在这里而不是调用方：实时（tool_end 帧）与刷新重放（走 renderHistoryToolItem）
   都经过 onToolEnd，所以两条路必然一致，也不会重复画。 */
renderDiffBubbleFromFacts(o.script||ev.script,ev.preview);
// 预览结果含 confirm_id：记入缓存，供 confirm_id 提交时展示文件名（与预览/review 同策略，不依赖额外事件字段）
try{var _cp=typeof ev.preview==="string"?JSON.parse(ev.preview):ev.preview;_cp=_cp&&_cp.data;_cp=_cp&&_cp.confirm_id?_cp:null;}catch(_cpE){_cp=null;}
if(_cp){
var _cpPath=String((o.args&&(o.args.path||o.args.dest_path||o.args.source_path))||(_cp.path||_cp.dest_path||_cp.source_path)||"").trim();
if(_cpPath){window.confirmPathCache=window.confirmPathCache||{};window.confirmPathCache[String(_cp.confirm_id).trim()]=_cpPath;}}
try{var _pp=typeof ev.preview==="string"?JSON.parse(ev.preview):ev.preview;var _dd=_pp&&_pp.data||null;var _so=_dd&&typeof _dd.stdout==="string"?_dd.stdout:"";var _se=_dd&&typeof _dd.stderr==="string"?_dd.stderr:"";var _shown=_so;if(isStreamOutputToolScript(o.script)&&_se.trim()){_shown=_so.trim()?(_so.replace(/\s*$/,"")+"\n"+_se):_se;}if(_shown&&String(_shown).trim()){if(o.liveOutPre&&o.liveOutPre!==o.chatRunOutPre)o.liveOutPre.textContent=_shown;updateChatRunCardOutput(o,_shown);}}catch(_e3){}
// file_undo：从结果数据补充路径到标题
try{var _fuP=typeof ev.preview==="string"?JSON.parse(ev.preview):ev.preview;_fuP=_fuP&&_fuP.data;}catch(_fuE){_fuP=null;}
if(_fuP&&o.script&&o.script.toLowerCase().indexOf("file_undo")>=0){
var _fuAct=String(o.args&&o.args.action||_fuP.action||"").trim();
var _fuPath=_fuP.restored_path||_fuP.path||"";
if(_fuPath&&!_fuPath.endsWith("\\")&&!_fuPath.endsWith("/")){
var _fn=pathLeaf(_fuPath)||"";
if(_fn){var _card=findStepCardForToolCall(tid);if(_card){var _tx=_card.querySelector(".step-title-wrap");if(_tx){var _txM=_tx.querySelector(":scope > span:first-child");var _txF=_tx.querySelector(":scope > .step-fname");var _ts="";var _mid=String(o.args&&o.args.mod_id||"").trim();/* 版本目录名的形状由 file_safety._version_dir_name 产出；按形状取，不数段数 */if(_mid){var _mv=/_(\d{6})_\d{3}_\d{4}_[0-9a-z]+$/.exec(_mid);if(_mv)_ts=_mv[1].slice(0,2)+":"+_mv[1].slice(2,4)+":"+_mv[1].slice(4,6);}if(_txM&&!_txF){_txF=document.createElement("span");_txF.className="step-fname";_tx.appendChild(_txF);}if(_txF){_txF.textContent=_fn+(_ts?" to "+_ts:"");}}}}}}
if(isStreamOutputToolScript(o.script))finalizeChatRunCard(o,ok);
if(ev.approval_required)openApprovalModalFromToolEnd(ev, o.chatToolRow);
else if(ev.user_confirm_required)openUserConfirmModalFromToolEnd(ev, o.chatToolRow);
/* 模型改了目标（goal 工具）→ 立即同步按钮，不必等用户刷新 */
if(ok&&o.script==="goal"){var _gp=null;try{_gp=JSON.parse(ev.preview||"{}").data||null;}catch(_e){}
/* `delete` 返回的是 {deleted:true} 而不是 {goal:...}：只认 goal 键的话，
   删完目标按钮会停在"进行中"。两种形状都要处理。 */
if(_gp&&Object.prototype.hasOwnProperty.call(_gp,"goal")){_goalInfo=_gp.goal;updateAutoToggleUI();}
else if(_gp&&_gp.deleted){_goalInfo=null;updateAutoToggleUI();}}
fillChatToolResult(o,ev);
toolOpen.delete(tid);}

async function sendChatMessage(){
if(!ta)return;
var text=String(ta.value||"").trim();
var imgs=pendingChatImages.slice();
if(!text&&!imgs.length)return;
if(isConversationBusy()){alert("当前会话仍在执行中，请等待模型响应、工具执行或确认流程完成后再发送。");return;}
var sendCid=getActiveConversationId();
/* 气泡只显示文字：图片由下方的附件条（缩略图）表达，不再追加 `[图片 ×N]` 尾巴。
   只发图不打字时给个占位，否则气泡是空的。 */
var display=text||"（截图）";
var bubble=add("u",display);
var stripEl=null;
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
var tab=findConversationTab(sendCid);
var b=goBtn;if(b)b.disabled=true;
if(tab){tab.abortController={global:true};tab.stopRequested=false;tab.activeRunId="";}
updateTaskControls();
try{
var body={message:text,conversation_id:sendCid,mode:selectedMode,model:selectedModel};
if(imgs.length)body.images=imgs.map(function(it){return{mime:it.mime,data_base64:it.data_base64};});
var r=await fetch("/api/chat/send",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
if(!r.ok){var _bt="";try{_bt=await r.text();}catch(e){}if(window.DEBUG)console.error("[ai-agent] /api/chat/send 非 OK",{status:r.status,bodyHead:String(_bt||"").slice(0,500)});withConversationContext(sendCid,function(){hideChatLoading();add("a","HTTP "+r.status);});if(tab){tab.abortController=null;tab.activeRunId="";}return;}
var _sj=await r.json();if(tab&&_sj&&_sj.run_id)tab.activeRunId=String(_sj.run_id||"");
if(stripEl&&_sj&&Array.isArray(_sj.attachments)&&_sj.attachments.length&&window.AIA&&AIA.buildMsgAttachStrip){
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
var btn=document.createElement("button");btn.type="button";btn.textContent="×";btn.title="移除";
btn.onclick=function(ev){if(ev){ev.preventDefault();ev.stopPropagation();}pendingChatImages.splice(idx,1);renderAttachStrip();};
d.appendChild(img);d.appendChild(btn);strip.appendChild(d);
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
if(pendingChatImages.length>=4)break;
try{
var it=await fileToPendingImage(files[i]);
pendingChatImages.push(it);
}catch(e){}
}
renderAttachStrip();
}
(function initChatAttach(){
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
var STORAGE_KEY="aiAgent.classicMainSplit";
/* 对话区最小宽度（与样式表 `.chat{min-width}` 同值）。
   实测口径：把对话区逐步压窄，量输入区那一行**最右侧控件**何时越过容器右边界 ——
   669px 时"发送"越界 1px，670px 起为 0。写死一个数而不是每次运行时量：
   布局是跟着拖拽连续变的，运行时量会一路抖动；插件按钮让这一行变长时，
   把两个数字一起往上调。 */
var MIN_CHAT_PX=670,MIN_STEPS_PX=300,RESIZER_PX=3;
/* 会话清单宽度：上限 500。下限要能放下标题和「已打开」，再窄就只剩省略号。 */
var MAX_RAIL_PX=500,MIN_RAIL_PX=180,DEFAULT_RAIL_PX=240;
var RAIL_KEY="aiAgent.sessionRailPx";
var RAIL_OPEN_KEY="aiAgent.sessionRailOpen";
var mainEl=document.querySelector("main");
var chatEl=mainEl?mainEl.querySelector(".chat"):null;
var sideEl=document.getElementById("classicSidePane")||(mainEl?mainEl.querySelector(".side"):null);
var resizerEl=document.getElementById("classicSplitResizer");
var railEl=document.getElementById("sessionRail");
var railResizer=document.getElementById("sessionRailResizer");
if(!mainEl||!chatEl||!sideEl||!resizerEl)return;
function mainInnerWidth(){var w=mainEl.getBoundingClientRect().width;return w>0?w:window.innerWidth;}
function railOpen(){return !!(railEl&&!railEl.classList.contains("is-collapsed"));}
/* 左侧清单展开时占掉的宽度（含它自己的分割条）也要扣掉。
   不扣的话，清单一展开，对话区会被挤过最小宽度，输入区控件出界。 */
function railTake(){return railOpen()?(railPx+RESIZER_PX):0;}
/* 右侧面板能占到的最大宽度 = 主区宽度 - 分割条 - 对话区最小宽度 - 已展开的会话清单。
   窗口不够宽时这里会小于 `MIN_STEPS_PX`，`clampSteps` 仍把面板钉在 `MIN_STEPS_PX` ——
   宁可整行出现横向滚动，也不让对话区被压到控件出界。 */
function maxStepsPx(){return Math.max(MIN_STEPS_PX,mainInnerWidth()-RESIZER_PX-MIN_CHAT_PX-railTake());}
function defaultStepsPx(){return Math.min(600,Math.round(window.innerWidth*0.46));}
function clampSteps(px){var maxPx=maxStepsPx();if(maxPx<MIN_STEPS_PX)return MIN_STEPS_PX;return Math.max(MIN_STEPS_PX,Math.min(maxPx,Math.round(px)));}
function loadStepsPx(){try{var raw=localStorage.getItem(STORAGE_KEY);if(!raw)return null;var o=JSON.parse(raw);var n=Number(o&&o.stepsPx);return isFinite(n)&&n>0?n:null;}catch(e){return null;}}
function saveStepsPx(px){try{localStorage.setItem(STORAGE_KEY,JSON.stringify({stepsPx:Math.round(px)}));}catch(e){}}
var _savedSteps=loadStepsPx();
var stepsPx=clampSteps(_savedSteps!=null?_savedSteps:defaultStepsPx());
function sideEmpty(){return document.documentElement.getAttribute("data-side-empty")==="1";}
function applyLayout(px){stepsPx=clampSteps(px);if(sideEmpty()){sideEl.style.flex="0 0 0px";sideEl.style.width="0px";sideEl.style.maxWidth="0px";sideEl.style.minWidth="0px";return;}sideEl.style.minWidth="";sideEl.style.flex="0 0 "+stepsPx+"px";sideEl.style.width=stepsPx+"px";sideEl.style.maxWidth=stepsPx+"px";}
function setClassicSideOpen(open){if(open)document.documentElement.removeAttribute("data-side-empty");else document.documentElement.setAttribute("data-side-empty","1");if(resizerEl){resizerEl.setAttribute("aria-hidden",open?"false":"true");resizerEl.tabIndex=open?0:-1;}applyLayout(stepsPx);}
setClassicSideOpen(countOpenSideTabs()>0);
window._setClassicSideOpen=setClassicSideOpen;
function railRoom(){return mainInnerWidth()-RESIZER_PX-RESIZER_PX-MIN_CHAT_PX-MIN_STEPS_PX;}
function clampRail(px){var room=railRoom();var maxPx=Math.min(MAX_RAIL_PX,room>=MIN_RAIL_PX?room:MIN_RAIL_PX);return Math.max(MIN_RAIL_PX,Math.min(maxPx,Math.round(px)));}
function loadRailPx(){try{var n=Number(localStorage.getItem(RAIL_KEY));return isFinite(n)&&n>0?n:null;}catch(e){return null;}}
function saveRailPx(px){try{localStorage.setItem(RAIL_KEY,String(Math.round(px)));}catch(e){}}
function loadRailOpen(){try{return localStorage.getItem(RAIL_OPEN_KEY)!=="0";}catch(e){return true;}}
function saveRailOpen(open){try{localStorage.setItem(RAIL_OPEN_KEY,open?"1":"0");}catch(e){}}
var _savedRail=loadRailPx();
var railPx=clampRail(_savedRail!=null?_savedRail:DEFAULT_RAIL_PX);
function applyRail(px){if(!railEl)return;railPx=clampRail(px);if(!railOpen()){railEl.style.flex="0 0 0px";railEl.style.width="0px";railEl.style.maxWidth="0px";return;}railEl.style.flex="0 0 "+railPx+"px";railEl.style.width=railPx+"px";railEl.style.maxWidth=Math.min(MAX_RAIL_PX,railPx)+"px";}
/* 先读一次布局，过渡才从当前宽度滑到目标宽度。
   同一帧里刚加上过渡就改宽度，浏览器会直接跳过去。拖动时关掉过渡，否则分隔线会跟着鼠标拖泥带水。 */
function armRailSlide(){if(!railEl)return;railEl.classList.add("is-animating");if(railResizer)railResizer.classList.add("is-animating");void railEl.offsetWidth;}
function railToggleSlot(){return document.getElementById("chatMoreSlot");}
function placeRailToggle(open){var head=document.getElementById("sessionRailHead");var slot=railToggleSlot();if(!chatMoreBtn||!head||!slot)return;if(open)head.appendChild(chatMoreBtn);else slot.appendChild(chatMoreBtn);}
/* 收起时按钮先留在栏里跟着滑走，标签栏左侧的空位同步加宽。
   动画结束再把按钮放进空位，标题不会被突然挤开。 */
function setRailToggleSlot(open, animate){var row=chatTabs&&chatTabs.parentElement;var slot=railToggleSlot();if(!row||!slot)return;if(animate){row.classList.add("is-rail-sliding");void slot.offsetWidth;}else row.classList.remove("is-rail-sliding");row.classList.toggle("is-rail-open",!!open);}
function setSessionRailOpen(open, animate){if(!railEl)return;try{document.documentElement.removeAttribute("data-session-rail");}catch(e){}var reduce=false;try{reduce=window.matchMedia("(prefers-reduced-motion: reduce)").matches;}catch(e){}var slide=!!animate&&!reduce;if(open)placeRailToggle(true);if(slide)armRailSlide();setRailToggleSlot(open,slide);railEl.classList.toggle("is-collapsed",!open);if(railResizer){railResizer.classList.toggle("is-collapsed",!open);railResizer.setAttribute("aria-hidden",open?"false":"true");railResizer.tabIndex=open?0:-1;}if(chatMoreBtn){var label=open?"收起会话清单":"展开会话清单";chatMoreBtn.setAttribute("aria-expanded",open?"true":"false");chatMoreBtn.title=label;chatMoreBtn.setAttribute("aria-label",label);}applyRail(railPx);applyLayout(stepsPx);saveRailOpen(open);var row=chatTabs&&chatTabs.parentElement;var clearSlide=function(){if(row)row.classList.remove("is-rail-sliding");};if(!slide){clearSlide();if(!open)placeRailToggle(false);return;}var finished=false;var finish=function(){if(finished)return;finished=true;railEl.removeEventListener("transitionend",onEnd);clearSlide();if(!open&&!railOpen())placeRailToggle(false);};var onEnd=function(ev){if(ev.target!==railEl||ev.propertyName!=="width")return;finish();};railEl.addEventListener("transitionend",onEnd);setTimeout(finish,400);}
window._setSessionRailOpen=function(open){setSessionRailOpen(!!open,true);};
var _railWasOpen=loadRailOpen();
setSessionRailOpen(_railWasOpen,false);
if(_railWasOpen)void loadSessionRailList();
if(railResizer){
railResizer.addEventListener("mousedown",function(ev){
if(!railOpen())return;
ev.preventDefault();
railEl.classList.add("is-dragging");
railResizer.classList.add("is-dragging");
var railDrag={startX:ev.clientX,startRail:railPx};
function onRailMove(e){applyRail(railDrag.startRail+(e.clientX-railDrag.startX));applyLayout(stepsPx);}
function onRailUp(){railEl.classList.remove("is-dragging");railResizer.classList.remove("is-dragging");document.removeEventListener("mousemove",onRailMove);document.removeEventListener("mouseup",onRailUp);saveRailPx(railPx);saveStepsPx(stepsPx);}
document.addEventListener("mousemove",onRailMove);
document.addEventListener("mouseup",onRailUp);
});
}
var drag=null;
resizerEl.addEventListener("mousedown",function(ev){
if(sideEmpty())return;
ev.preventDefault();
drag={startX:ev.clientX,startSteps:stepsPx};
function onMove(e){
if(!drag)return;
applyLayout(drag.startSteps-(e.clientX-drag.startX));
}
function onUp(){
drag=null;
document.removeEventListener("mousemove",onMove);
document.removeEventListener("mouseup",onUp);
saveStepsPx(stepsPx);
}
document.addEventListener("mousemove",onMove);
document.addEventListener("mouseup",onUp);
});
var resizeTimer=null;
window.addEventListener("resize",function(){
if(resizeTimer)clearTimeout(resizeTimer);
resizeTimer=setTimeout(function(){
resizeTimer=null;
var prevSteps=stepsPx,prevRail=railPx;
if(railOpen())applyRail(railPx);
applyLayout(stepsPx);
if(stepsPx!==prevSteps)saveStepsPx(stepsPx);
if(railPx!==prevRail)saveRailPx(railPx);
},120);
});
})();
initModePicker();
initReasoningPicker();
initKbAndSlashUi();
initMarkedExtensions();
/* 面板清单与动作清单先取回（渲染各入口都按数据来）；
   随后预载插件脚本 —— 段色注册必须早于第一次画上下文条，否则那一段
   只能先按兜底色画出来，用户看到的颜色就和浮层对不上。预载完再重画一次。 */
void loadPluginPanels().then(function(){
void preloadPluginScripts().then(function(){
if(typeof _updateUsageBottom==="function")_updateUsageBottom();
});
});
void loadPluginActions();
/* 工具展示清单（中文名 + 图标）与面板/动作清单一样，都是**数据驱动**的入口：
   工具自己声明自己长什么样，界面不维护工具名表。 */
void loadToolLabels();
if(goBtn)goBtn.addEventListener("click",function(){void sendChatMessage();});
if(stopTaskBtn)stopTaskBtn.addEventListener("click",function(){_autoEnabled=false;updateAutoToggleUI();stopCurrentTask();});
if(autoToggleBtn)autoToggleBtn.addEventListener("click",function(){renderGoalDialog();});
var railNewEl=document.getElementById("sessionRailNew");
if(railNewEl)railNewEl.addEventListener("click",function(){createConversationTab();});
if(chatMoreBtn)chatMoreBtn.addEventListener("click",function(){void toggleSessionMenu();});
if(ta){ta.addEventListener("keydown",function(e){if(e.isComposing)return;var sh=slashPop&&!slashPop.classList.contains("hidden");var atp2=getAtPop();var ah=atp2&&atp2.style.visibility!=="hidden";var k=e.key,kl=k.toLowerCase(),ci=(slashPop&&slashPop.children)?slashPop.children:[];if(ah){if(k==="Escape"){e.preventDefault();hideAtPop();return;}if(k==="ArrowDown"||k==="ArrowUp"){e.preventDefault();var ai=getAtList().querySelectorAll(".at-item");var vi=[];for(var i2=0;i2<ai.length;i2++){if(ai[i2].style.display!=="none")vi.push(i2);}if(!vi.length)return;var idx=vi.indexOf(atSelectedIndex);if(idx<0)idx=(k==="ArrowDown"?0:vi.length-1);else if(k==="ArrowDown"){if(idx<vi.length-1)idx++;}else{if(idx>0)idx--;}atSelectedIndex=vi[idx];updateAtSelection();var row=ai[atSelectedIndex];if(row&&row.scrollIntoView)try{row.scrollIntoView({block:"nearest"});}catch(_){}return;}if(k==="ArrowRight"){e.preventDefault();var aiR=getAtList().querySelectorAll(".at-item");var pR=atSelectedIndex;if(pR<0||pR>=aiR.length)pR=0;if(aiR.length&&aiR[pR]&&aiR[pR].dataset.type==="dir")loadAtDir(aiR[pR].dataset.path);return;}if(k==="ArrowLeft"){e.preventDefault();var curL=getAtCurPath().textContent.trim();var parentStored=getAtCurPath().dataset.parent||"";if(!parentStored)return;var pU=parentStored||curL.substring(0,curL.lastIndexOf("/"));if(!pU||pU.length<3){if(pU&&pU.length===2&&pU.charAt(1)===":"){pU=pU+"/";}else{pU=curL;}}if(pU!==curL)atRestoreSelectPath=curL;loadAtDir(pU);return;}if(k==="Enter"||e.code==="Enter"||e.code==="NumpadEnter"){e.preventDefault();var ai2=getAtList().querySelectorAll(".at-item");var pick=atSelectedIndex;if(pick<0||pick>=ai2.length)pick=0;if(ai2.length&&ai2[pick]){var sel=ai2[pick];selectAtFile(sel.dataset.path);}return;}if(atMentionActiveAtCursor()){return;}hideSlashPop();hideAtPop();return;}if(!sh&&!ah){if(!e.shiftKey&&(e.key==="Enter"||e.code==="Enter"||e.code==="NumpadEnter")){e.preventDefault();if(goBtn)goBtn.click();else void sendChatMessage();}return;}if(sh&&k==="Escape"){e.preventDefault();hideSlashPop();return;}if(sh&&(k==="ArrowDown"||k==="ArrowUp")){e.preventDefault();var vi3=[];for(var i3=0;i3<ci.length;i3++){if(ci[i3].style.display!=="none")vi3.push(i3);}if(!vi3.length)return;var idx3=vi3.indexOf(slashSelectedIndex);if(idx3<0)idx3=(k==="ArrowDown"?-1:0);else if(k==="ArrowDown"){if(idx3<vi3.length-1)idx3++;}else{if(idx3>0)idx3--;}var cur3=ci[slashSelectedIndex];if(cur3)cur3.classList.remove("selected");slashSelectedIndex=vi3[idx3];var nxt3=ci[slashSelectedIndex];if(nxt3)nxt3.classList.add("selected");updateSlashPopHints();return;}if(sh&&(k==="Enter"||e.code==="Enter"||e.code==="NumpadEnter")){e.preventDefault();var sel4=ci[slashSelectedIndex];if(sel4&&sel4.dataset&&sel4.dataset.slash){applyMode(sel4.dataset.slash);ta.value="";}else hideSlashPop();return;}if(kl==="a"||kl==="p"||kl==="e"){e.preventDefault();hideSlashPop();ta.value="";if(kl==="a")applyMode("auto");else if(kl==="p")applyMode("plan");else applyMode("execute");return;}hideSlashPop();});ta.addEventListener("blur",function(){if(slashPop&&!slashPop.classList.contains("hidden"))hideSlashPop();});ta.addEventListener("mouseup",function(){if(slashPop&&!slashPop.classList.contains("hidden"))hideSlashPop();});}
document.getElementById("tabSteps")?.addEventListener("click",function(){selectSidePane("steps");});
window.addEventListener("beforeunload",function(){try{saveActiveConversationView();storeConversationLayoutLocal();}catch(e){}});
/* **先恢复会话，再取用量**。
   `loadUsageAccumulator()` 若排在 `restoreConversationLayoutFromServer()` 之前：
   `activeConversationId` 初始值来自本地（URL/sessionStorage），**可能为空**，
   用量 GET 于是打到空槽、取回全 0；随后 UI 才切到服务端恢复的真正会话
   → 刷新后用量显示 0。服务端数据本身是好的，问题只在取值时机。 */
void loadUsageAccumulator();
initTodoListElements();
startGlobalSse();
void restoreConversationLayoutFromServer().then(function(){
  /* 会话恢复后 `activeConversationId` 才是真正的当前会话 —— 此刻重取一次，覆盖空槽结果 */
  void loadUsageAccumulator();
  /* 同理：会话级模型也要等会话定下来再取（否则取到的是默认会话的模型） */
  void loadConversationModel();
});
void loadHealthModel();
if(typeof renderChatTabs==="function")renderChatTabs();
_updateUsageBottom();
autoResizeTextarea();

window.testScrollFollow=function(n){
if(!steps){if(window.DEBUG)console.warn("steps 容器未找到");return;}
n=n||25;
if(window.DEBUG)console.log("===== 滚动跟随测试开始: 插入"+n+"个步骤卡片 =====");
var seq=steps.querySelectorAll(".step.card").length+1;
for(var i=0;i<n;i++){
(function(idx){
setTimeout(function(){
var c=document.createElement("div");c.className="step card open";
var h=document.createElement("div");h.className="ch";
var t=document.createElement("span");t.className="tit";
t.textContent="测试步骤 "+(seq+idx)+"：验证滚动跟随 #"+(idx+1);
h.appendChild(t);
var body=document.createElement("div");body.className="card-body";
var inner=document.createElement("div");inner.className="card-body-inner";
var pre=document.createElement("pre");
var _long="";for(var _j=0;_j<40;_j++){_long+="  这是填充行 #"+_j+" 用来撑高卡片，让滚动条出现。步骤 "+(seq+idx)+"\n";}pre.textContent=_long;
inner.appendChild(pre);body.appendChild(inner);c.appendChild(h);c.appendChild(body);
appendStep(c);
if(idx===n-1){if(window.DEBUG)console.log("===== 测试结束 =====");}
},(idx+1)*300);
})(i);
}
};
if(typeof themeUi!=="undefined"){
themeUi.apply();
var _ht=document.getElementById("hdrThemeBtn");
if(_ht)_ht.addEventListener("click",function(){
themeUi.toggle();
/* 段色在渲染时从主题令牌取，所以切主题要重画一次上下文条。 */
if(typeof _updateUsageBottom==="function")_updateUsageBottom();
});
}