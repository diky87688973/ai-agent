/* chat/conversation.js —— 多会话标签：运行时状态存取、会话清单、历史回放与恢复。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
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
const stepsRoot=document.getElementById("steps");let msgs=null,msgsRoot=null;let steps=stepsRoot;cid=document.getElementById("cid"),ta=document.getElementById("t"),slashPop=document.getElementById("slashPop"),sideTabbar=document.getElementById("sideTabbar"),sidePaneWrap=document.getElementById("sidePaneWrap"),hdrModel=document.getElementById("hdrModel"),chatTabs=document.getElementById("chatTabs");var _tBoot=getActiveTab();if(conversationMount&&_tBoot&&_tBoot.conversationPane){conversationMount.appendChild(_tBoot.conversationPane);msgsRoot=_tBoot.msgsHost;msgs=msgsRoot;todoListArea=_tBoot.todoArea;todoListBody=todoListArea?todoListArea.querySelector(".todo-list-body"):null;todoListCount=todoListArea?todoListArea.querySelector(".todo-list-count"):null;}if(cid)cid.textContent=getActiveConversationId().slice(0,8);
function moveChildrenToArray(el){var arr=[];if(!el)return arr;while(el.firstChild){arr.push(el.firstChild);el.removeChild(el.firstChild);}return arr;}
function restoreChildrenFromArray(el,arr){if(!el)return;el.innerHTML="";arr=Array.isArray(arr)?arr:[];for(var i=0;i<arr.length;i++){el.appendChild(arr[i]);}}
function isConversationBusy(){var t=getActiveTab();return !!(userConfirmBlocking||toolOpen.size||pendingToolTags.length||(t&&t.abortController));}
function isTabBusy(t){return !!(t&&(t.abortController||t.userConfirmBlocking||(t.toolOpen&&t.toolOpen.size)||((t.pendingToolTags||[]).length)));}
function saveRuntimeStateToTab(t){t.selectedMode=selectedMode;t.selectedModel=selectedModel;t.reasoningEffort=reasoningEffort;t.stepSeq=stepSeq;t.lastLlm=lastLlm;t.llmStreamBuffer=llmStreamBuffer;t.pendingToolTags=pendingToolTags;t.anyToolThisTurn=anyToolThisTurn;t.pendingStepEls=pendingStepEls;t.streamAssistantEl=streamAssistantEl;t.streamAssistantText=streamAssistantText;t.pendingDeltaSeparator=pendingDeltaSeparator;t.seenDispatchTitle=seenDispatchTitle;t.toolOpen=toolOpen;t.lastAnalysisTail=lastAnalysisTail;t.chatLoadingEl=chatLoadingEl;t.userConfirmCardHost=userConfirmCardHost;t.userConfirmBlocking=userConfirmBlocking;t.sessionTokenUsed=sessionTokenUsed;t.totalPromptTokens=totalPromptTokens;t.totalCompletionTokens=totalCompletionTokens;t.totalCacheHitTokens=totalCacheHitTokens;t.totalCacheMissTokens=totalCacheMissTokens;}
function loadRuntimeStateFromTab(t){selectedMode=t.selectedMode||selectedMode||"auto";selectedModel=t.selectedModel||selectedModel||"";reasoningEffort=t.reasoningEffort||reasoningEffort||"high";stepSeq=Number(t.stepSeq||0);lastLlm=t.lastLlm||null;llmStreamBuffer=t.llmStreamBuffer||{round:null,reqHtml:"",resHtml:"",consumed:false};pendingToolTags=t.pendingToolTags||[];anyToolThisTurn=!!t.anyToolThisTurn;pendingStepEls=t.pendingStepEls||[];streamAssistantEl=t.streamAssistantEl||null;streamAssistantText=String(t.streamAssistantText||"");pendingDeltaSeparator=!!t.pendingDeltaSeparator;seenDispatchTitle=String(t.seenDispatchTitle||"");toolOpen=t.toolOpen instanceof Map?t.toolOpen:new Map();lastAnalysisTail=String(t.lastAnalysisTail||"");chatLoadingEl=t.chatLoadingEl||null;userConfirmCardHost=t.userConfirmCardHost||null;userConfirmBlocking=!!t.userConfirmBlocking;sessionTokenUsed=Number(t.sessionTokenUsed||0);totalPromptTokens=Number(t.totalPromptTokens||0);totalCompletionTokens=Number(t.totalCompletionTokens||0);totalCacheHitTokens=Number(t.totalCacheHitTokens||0);totalCacheMissTokens=Number(t.totalCacheMissTokens||0);}
function moveVisibleToTab(t){while(stepsRoot.firstChild)t.stepsHost.appendChild(stepsRoot.firstChild);if(t.conversationPane&&conversationMount&&t.conversationPane.parentNode===conversationMount){conversationMount.removeChild(t.conversationPane);}saveRuntimeStateToTab(t);}
function moveTabToVisible(t){while(t.stepsHost.firstChild)stepsRoot.appendChild(t.stepsHost.firstChild);if(conversationMount&&t.conversationPane){while(conversationMount.firstChild){conversationMount.removeChild(conversationMount.firstChild);}conversationMount.appendChild(t.conversationPane);}msgsRoot=t.msgsHost;msgs=msgsRoot;trackMsgsBottom(msgs);todoListArea=t.todoArea;observeTodoResize(todoListArea);todoListBody=todoListArea?todoListArea.querySelector(".todo-list-body"):null;todoListCount=todoListArea?todoListArea.querySelector(".todo-list-count"):null;steps=stepsRoot;loadRuntimeStateFromTab(t);}
function saveActiveConversationView(){moveVisibleToTab(getActiveTab());}
/* 当前会话变了就广播一个事件：插件面板里带会话级状态的（勾选之类）要跟着重取。
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
function restoreConversationView(t){moveTabToVisible(t);if(cid)cid.textContent=t.id.slice(0,8);applyMode(selectedMode,false);applyModel(selectedModel,true);applyReasoningEffort(reasoningEffort,false);if(typeof syncConversationSettings==="function")void syncConversationSettings(t,true);if(typeof updateTaskControls==="function")updateTaskControls();if(typeof loadUsageAccumulator==="function")void loadUsageAccumulator();_updateUsageBottom();scrollToBottom(stepsRoot,true);notifyConversationChanged();if(t&&t.historyLoaded){scrollToBottomAfterLayout(msgs,true);}if(typeof updateHistoryJumpButton==="function")updateHistoryJumpButton(msgs);}
function withConversationContext(conversationId,fn){var target=findConversationTab(conversationId);if(!target)return;var prevTab=getActiveTab(),prevMsgs=msgs,prevSteps=steps,prevTodo=todoListArea,prevTodoBody=todoListBody,prevTodoCount=todoListCount,prevRenderingVisible=renderingContextVisible;saveRuntimeStateToTab(prevTab);renderingContextVisible=target.id===activeConversationId;if(target.id===activeConversationId){msgsRoot=target.msgsHost;msgs=msgsRoot;steps=stepsRoot;todoListArea=target.todoArea;todoListBody=todoListArea?todoListArea.querySelector(".todo-list-body"):null;todoListCount=todoListArea?todoListArea.querySelector(".todo-list-count"):null;}else{msgs=target.msgsHost;steps=target.stepsHost;todoListArea=target.todoArea;todoListBody=todoListArea?todoListArea.querySelector(".todo-list-body"):null;todoListCount=todoListArea?todoListArea.querySelector(".todo-list-count"):null;}loadRuntimeStateFromTab(target);try{return fn(target);}finally{saveRuntimeStateToTab(target);renderingContextVisible=prevRenderingVisible;msgs=prevMsgs;steps=prevSteps;todoListArea=prevTodo;todoListBody=prevTodoBody;todoListCount=prevTodoCount;loadRuntimeStateFromTab(prevTab);if(cid)cid.textContent=(prevTab?prevTab.id:activeConversationId).slice(0,8);if(typeof _updateUsageBottom==="function")_updateUsageBottom();}}
/* 布局（打开过哪些标签、激活哪一个）只存本地，不发服务端。
   「激活的是哪个会话」是本浏览器的选择，不是服务器的事实 —— 两个浏览器各自
   激活不同会话时，服务端一个全局字段表示不了，只会谁后写谁覆盖。 */
function persistConversationLayout(){storeConversationLayoutLocal();}
function repaintSessionRail(){var rail=document.getElementById("sessionRail");if(!chatSessionMenu||!rail||rail.classList.contains("is-collapsed")||!chatSessionMenu._sessions)return;renderSessionMenu(chatSessionMenu._sessions);}
function openConversationFromMenu(id,title){id=normalizeConversationId(id);if(!id)return;saveActiveConversationView();var t=ensureConversationTab(id);if(title)t.title=String(title).slice(0,80);t.todoUnread=false;activeConversationId=t.id;sessionId=t.id;conv=t.id;storeConversationId(t.id);restoreConversationView(t);renderChatTabs();persistConversationLayout();loadConversationHistory(t);repaintSessionRail();}
function openSubagentConversation(id,title,parentCid,batch){id=normalizeConversationId(id);if(!id)return;saveActiveConversationView();var t=ensureConversationTab(id);t.subagent=true;t.parentCid=String(parentCid||"");t.batch=String(batch||"");if(title)t.title=String(title).slice(0,80);t.todoUnread=false;t.historyLoaded=false;activeConversationId=t.id;sessionId=t.id;conv=t.id;storeConversationId(t.id);restoreConversationView(t);renderChatTabs();persistConversationLayout();loadConversationHistory(t);repaintSessionRail();}
function renderSessionMenu(items){if(!chatSessionMenu)return;items=Array.isArray(items)?items:[];chatSessionMenu._sessions=items;chatSessionMenu.innerHTML="";if(!items.length){var emp=document.createElement("div");emp.className="chat-session-empty";emp.textContent="暂无历史会话";chatSessionMenu.appendChild(emp);return;}var lastGroup=null;items.forEach(function(s){var id=normalizeConversationId(s&&s.id);if(!id)return;var group=String(s.date_group||"");if(group&&group!==lastGroup){lastGroup=group;var gh=document.createElement("div");gh.className="chat-session-group";gh.textContent=group;chatSessionMenu.appendChild(gh);}else if(!group&&lastGroup!==null){lastGroup=null;}var opened=!!findConversationTab(id);var row=document.createElement("button");row.type="button";row.className="chat-session-row";row.title=id;row.setAttribute("data-session-id",id);var title=document.createElement("span");title.className="chat-session-title";title.textContent=String(s.title||("会话 "+id.slice(0,8)));row.appendChild(title);if(opened){var badge=document.createElement("span");badge.className="chat-session-badge";badge.textContent="已打开";row.appendChild(badge);}chatSessionMenu.appendChild(row);});}
var sessionRailListGen=0;
async function loadSessionRailList(quiet){if(!chatSessionMenu)return;var gen=++sessionRailListGen;if(!quiet)chatSessionMenu.innerHTML='<div class="chat-session-empty">加载中…</div>';try{var r=await fetch("/api/chat/sessions");var j=await r.json();if(gen!==sessionRailListGen)return;renderSessionMenu(j&&j.sessions||[]);}catch(e){if(gen!==sessionRailListGen)return;if(!quiet)chatSessionMenu.innerHTML='<div class="chat-session-empty">会话列表加载失败</div>';}}
async function toggleSessionMenu(){var rail=document.getElementById("sessionRail");if(!rail||!chatSessionMenu)return;if(!rail.classList.contains("is-collapsed")){if(typeof window._setSessionRailOpen==="function")window._setSessionRailOpen(false);return;}if(typeof window._setSessionRailOpen==="function")window._setSessionRailOpen(true);await loadSessionRailList();}
document.addEventListener("ai-agent:conversation-title",function(){var rail=document.getElementById("sessionRail");if(!rail||rail.classList.contains("is-collapsed"))return;void loadSessionRailList(true);});
function isDefaultConversationTitle(t){var s=String(t&&t.title||"");return !s||/^会话\s+[A-Za-z0-9_-]{8}$/.test(s)||s==="生成标题中…"||s==="新会话";}
async function refreshConversationTitle(id){var t=findConversationTab(id);if(!t||t.subagent||!isDefaultConversationTitle(t))return;t.title="生成标题中…";renderChatTabs();persistConversationLayout();try{var r=await fetch("/api/chat/title",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:id})});if(!r.ok)return;var j=await r.json();var title=String(j&&j.title||"").trim();if(title&&title!=="新会话"){var tt=findConversationTab(id);if(tt){tt.title=title.slice(0,18);renderChatTabs();persistConversationLayout();notifyConversationTitle(tt.id);}}else if(title==="新会话"){var t2=findConversationTab(id);if(t2&&t2.title==="生成标题中…"){t2.title="会话 "+id.slice(0,8);renderChatTabs();persistConversationLayout();notifyConversationTitle(t2.id);}}}catch(e){}}
function renderHistoryItems(items,conversationId){
items=Array.isArray(items)?items:[];
/* 必须用正在还原的会话 id，不能用当前激活 tab：多 tab 并行 loadHistory 时否则会把附件挂到错误 conversation_id → 404 */
var cid=normalizeConversationId(conversationId)||getActiveConversationId();
for(var i=0;i<items.length;i++){
var it=items[i]||{};
if(it.kind==="system_notice")continue;
if(it.role==="user"){
var bubble=null;
if(it._sender&&it._sender!=="boss")addPeerMessage(String(it.content||""),String(it._sender_name||""),String(it._sender||""));
else bubble=add("u",String(it.content||""),it);
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
}else if(it.role==="compaction"){
renderHistoryCompactionItem(it);
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
/* `_replay`：这条来自历史回放，不是正在发生。等待类工具据此不启动倒计时 ——
   否则刷新页面会把早已结束的等待重新数一遍。 */
var ev={tool_call_id:String(it.tool_call_id||""),script:String(it.script||""),args:it.args||{},_replay:true,elapsed_s:it.elapsed_s};
if(!ev.tool_call_id)return;
onToolStart(ev);
var o=toolOpen.get(ev.tool_call_id);
if(!o)return;
if(it.status==="canceled"){
onToolEnd({tool_call_id:ev.tool_call_id,ok:false,canceled:true,error:String(it.error||"已停止"),elapsed_s:it.elapsed_s});
}else if(it.status==="failed"){
onToolEnd({tool_call_id:ev.tool_call_id,ok:false,error:String(it.error||"执行失败"),preview:String(it.preview||""),elapsed_s:it.elapsed_s});
}else if(it.status==="suspended"){
/* 挂起（等用户在界面作答）：不标失败，保持"待确认"语义 */
var env=it.envelope||{};
if(env.kind==="approval"){
onToolEnd({tool_call_id:ev.tool_call_id,ok:true,approval_required:true,
approval_title:"审批",approval_desc:String(env.option_desc||""),
preview:it.envelope?JSON.stringify({data:it.envelope}):"",elapsed_s:it.elapsed_s});
}else{
var confirms=Array.isArray(env.confirms)?env.confirms.map(String):[];
onToolEnd({tool_call_id:ev.tool_call_id,ok:false,user_confirm_required:true,
user_confirm_title:String(env.title||""),
user_confirm_options:confirms,
user_confirm_multi:!!env.multi,
preview:it.envelope?JSON.stringify({data:it.envelope}):"",elapsed_s:it.elapsed_s});
}
}else if(it.status==="done"){
/* `preview` 走实时帧同一条渲染路径（onToolEnd 内部就认它）：
   编辑类工具的 diff 卡片靠这一项重画 —— 不传它，刷新后 diff 整片消失。 */
onToolEnd({tool_call_id:ev.tool_call_id,ok:true,preview:String(it.preview||""),images:it.images||[],elapsed_s:it.elapsed_s});
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
async function refreshConversationContextLayout(t){if(!t||!normalizeConversationId(t.id)||t.abortController)return;try{var r=await fetch("/api/chat/history?"+new URLSearchParams({conversation_id:t.id,meta:"1"}));if(!r.ok)return;var j=await r.json();if(!j||j.ok!==true)return;applyContextLayoutFromHistory(t,j);}catch(e){}}
var composerResizeObserver=null;
function trackMsgsBottom(el){
if(!el||el._queueBottomTracked)return;
el._queueBottomTracked=true;
el._atBottom=true;
el.addEventListener("scroll",function(){
el._atBottom=(el.scrollHeight-el.scrollTop-el.clientHeight)<16;
if(typeof updateHistoryJumpButton==="function")updateHistoryJumpButton(el);
if(typeof onHistoryScroll==="function")onHistoryScroll(el);
},{passive:true});
}
function initComposerResizeSync(){
if(composerResizeObserver||!window.ResizeObserver)return;
var above=document.querySelector(".composer-above");
if(!above)return;
trackMsgsBottom(msgs);
composerResizeObserver=new ResizeObserver(function(){
var el=msgs;
if(!el)return;
var keepBottom=!!el._atBottom;
requestAnimationFrame(function(){
requestAnimationFrame(function(){
if(!el)return;
if(keepBottom){if(typeof scrollToBottom==="function")scrollToBottom(el,true);}
else{el.scrollTop=Math.min(el.scrollTop,Math.max(0,el.scrollHeight-el.clientHeight));}
});
});
});
composerResizeObserver.observe(above);
var composer=document.querySelector(".composer");
if(composer)composerResizeObserver.observe(composer);
if(typeof todoListArea!=="undefined")observeTodoResize(todoListArea);
}
function observeTodoResize(el){
if(!el||!composerResizeObserver)return;
try{composerResizeObserver.observe(el);}catch(e){}
}
function scrollToBottomAfterLayout(el,force){if(!el)return;requestAnimationFrame(function(){requestAnimationFrame(function(){scrollToBottom(el,force);});});}
async function loadConversationHistory(t){if(!t)return;if(t.historyLoaded){void refreshConversationContextLayout(t);return;}if(t.historyState==="loading")return;t.historyState="loading";try{var _hp=t.subagent?"/api/subagents/history?":"/api/chat/history?";var _hq=t.subagent?new URLSearchParams({conversation_id:String(t.parentCid||""),child_id:t.id}):new URLSearchParams({conversation_id:t.id});var r=await fetch(_hp+_hq);if(!r.ok)throw new Error("history HTTP "+r.status);var j=await r.json();if(!j||j.ok!==true)throw new Error("history not ok");var items=j.items||[];applyContextLayoutFromHistory(t,j);withConversationContext(t.id,function(){var isActive=normalizeConversationId(t.id)===normalizeConversationId(activeConversationId);if(j.todo_list&&j.todo_list.length){renderTodoListFromEvent({items:j.todo_list,all_done:j.todo_list.every(function(it){return !!it.done;}),collapsed:false},t.id);}else{hideTodoList();}if(items.length&&msgs.childNodes.length<=1){while(msgs.firstChild)msgs.removeChild(msgs.firstChild);renderHistoryItems(items,t.id);}else if(msgs.childNodes.length===0){renderHistoryItems(items,t.id);}if(isActive){scrollToBottomAfterLayout(msgs,true);}});t.historyLoaded=true;if(j.page&&typeof j.page.has_more==="boolean"){t.historyBefore=j.page.has_more?j.page.next_before:null;t.historyState=j.page.has_more?"idle":"exhausted";}else{t.historyBefore=null;t.historyState="exhausted";}}catch(e){console.error("[history] load failed",t.id,e);t.historyLoaded=false;t.historyBefore=null;t.historyState="error";}}
function _routeEventBySource(ev){var scid=ev&&ev._source_session;if(!scid)return;var cid=normalizeConversationId(scid);if(!cid)return;var tab=findConversationTab(cid);if(!tab)return;var t=ev.type;if(t==="assistant"){withConversationContext(cid,function(){var ac=String(ev.content||"").trim();if(ac){add("a",ac);scrollToBottomAfterLayout(msgs,true);}});}else if(t==="tool_start"){withConversationContext(cid,function(){onToolStart(ev);});}else if(t==="tool_end"){withConversationContext(cid,function(){onToolEnd(ev);if(ev.todo_list&&ev.todo_list_data){var _td=ev.todo_list_data;renderTodoListFromEvent({items:_td.items||[],all_done:Array.isArray(_td.items)&&_td.items.every(function(it){return !!it.done;}),collapsed:!!_td.collapsed,close:!!_td.close},cid);scrollToBottomAfterLayout(msgs,true);}});}else if(t==="todo_list"){if(ev.close){syncTodoUnreadBadgeForConversation(cid);}else if(ev.items){renderTodoListFromEvent({items:ev.items,all_done:Array.isArray(ev.items)&&ev.items.every(function(it){return !!it.done;}),collapsed:!!ev.collapsed,close:!!ev.close},cid);syncTodoUnreadBadgeForConversation(cid);}}else if(t==="context_compacted"){withConversationContext(cid,function(){renderCompactionEvent(ev,findConversationTab(cid));});}else if(t==="context_layout"){var _t4=findConversationTab(cid);if(_t4)applyContextLayoutFromHistory(_t4,{context_layout:ev});}}
/* 开局只向服务端问一件事：哪些会话在跑（服务端权威，用于回填停止键）。
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
function renderChatTabs(){if(!chatTabs)return;var sig=conversationTabs.map(function(t){return String(t.id)+"\t"+String(t.title||"")+"\t"+(t.id===activeConversationId?1:0)+"\t"+(t.todoUnread?1:0);}).join("|");if(renderChatTabs._sig===sig&&chatTabs.children.length===conversationTabs.length){var mz=conversationTabs.length;for(var zp=0;zp<mz;zp++){var el=chatTabs.children[zp];if(!el||el.getAttribute("data-tab-id")!==conversationTabs[zp].id)break;}if(zp===mz)return;}renderChatTabs._sig=sig;var wc=conversationTabs.length>1;var pi,tid,t,btn,lab,labT,cn,ft,cur,kj,nel,xc;for(pi=0;pi<conversationTabs.length;pi++){t=conversationTabs[pi];tid=t.id;cur=chatTabs.children[pi];if(cur&&cur.getAttribute("data-tab-id")===tid)continue;btn=null;if(cur){for(kj=pi;kj<chatTabs.children.length;kj++){if(chatTabs.children[kj]&&chatTabs.children[kj].getAttribute("data-tab-id")===tid){btn=chatTabs.children[kj];break;}}}if(!btn){for(kj=0;kj<chatTabs.children.length;kj++){if(chatTabs.children[kj]&&chatTabs.children[kj].getAttribute("data-tab-id")===tid){btn=chatTabs.children[kj];break;}}}if(!btn){nel=document.createElement("button");nel.type="button";nel.setAttribute("role","tab");nel.setAttribute("data-tab-id",tid);lab=document.createElement("span");lab.className="chat-tab-label";nel.appendChild(lab);btn=nel;}chatTabs.insertBefore(btn,cur||null);}while(chatTabs.children.length>conversationTabs.length){chatTabs.removeChild(chatTabs.lastChild);}for(pi=0;pi<conversationTabs.length;pi++){t=conversationTabs[pi];tid=t.id;btn=chatTabs.children[pi];if(!btn)continue;labT=t.title||("会话 "+t.id.slice(0,8));cn="chat-tab"+((t.id===activeConversationId)?" active":"")+(t.todoUnread?" chat-tab-todo-unread":"");ft="标题: "+labT+"\n会话ID: "+t.id;lab=btn.querySelector(".chat-tab-label");if(lab&&lab.textContent!==labT)lab.textContent=labT;if(btn.className!==cn)btn.className=cn;if(btn.title!==ft)btn.title=ft;xc=btn.querySelector(".chat-tab-close");if(wc){if(!xc){xc=document.createElement("button");xc.type="button";xc.className="chat-tab-close";xc.textContent="×";xc.title="关闭会话";btn.appendChild(xc);}}else{if(xc)xc.remove();}}}
function switchConversationTab(id){id=normalizeConversationId(id);if(!id)return;saveActiveConversationView();var t=findConversationTab(id);if(!t)return;t.todoUnread=false;activeConversationId=id;sessionId=id;conv=id;storeConversationId(id);restoreConversationView(t);renderChatTabs();persistConversationLayout();loadConversationHistory(t);}
function createConversationTab(){saveActiveConversationView();var t=makeConversationTab(newConversationId());conversationTabs.push(t);activeConversationId=t.id;sessionId=t.id;conv=t.id;storeConversationId(t.id);restoreConversationView(t);renderChatTabs();persistConversationLayout();repaintSessionRail();}
function closeConversationTab(id){id=normalizeConversationId(id);if(conversationTabs.length<=1)return;var idx=-1;for(var i=0;i<conversationTabs.length;i++){if(conversationTabs[i].id===id){idx=i;break;}}if(idx<0)return;if(isTabBusy(conversationTabs[idx])){alert("该会话正在响应或等待确认，请完成后再关闭。");return;}var wasActive=id===activeConversationId;var _closedT=conversationTabs[idx];conversationTabs.splice(idx,1);if(_closedT&&_closedT.conversationPane&&conversationMount&&_closedT.conversationPane.parentNode===conversationMount){try{conversationMount.removeChild(_closedT.conversationPane);}catch(_eM){}}if(wasActive){var next=conversationTabs[Math.max(0,idx-1)]||conversationTabs[0];activeConversationId=next.id;sessionId=next.id;conv=next.id;storeConversationId(next.id);restoreConversationView(next);}renderChatTabs();persistConversationLayout();repaintSessionRail();try{fetch("/api/chat/sessions?"+new URLSearchParams({conversation_id:id}),{method:"DELETE"}).catch(function(){});}catch(_eRel){}}
initComposerResizeSync();
function initConversationClickDelegation(){
var sessionMenu=document.getElementById("chatSessionMenu");
if(sessionMenu&&!sessionMenu._sessionClickDelegated){
sessionMenu._sessionClickDelegated=true;
sessionMenu.addEventListener("click",function(ev){
var row=ev.target&&ev.target.closest?ev.target.closest(".chat-session-row"):null;
if(!row||!sessionMenu.contains(row))return;
var id=normalizeConversationId(row.getAttribute("data-session-id")||"");
if(!id)return;
var title=row.querySelector(".chat-session-title");
openConversationFromMenu(id,title?title.textContent:"");
});
}
if(chatTabs&&!chatTabs._tabClickDelegated){
chatTabs._tabClickDelegated=true;
chatTabs.addEventListener("click",function(ev){
var target=ev.target;
var tab=target&&target.closest?target.closest(".chat-tab"):null;
if(!tab||!chatTabs.contains(tab))return;
var id=normalizeConversationId(tab.getAttribute("data-tab-id")||"");
if(!id)return;
if(target.closest(".chat-tab-close")){closeConversationTab(id);return;}
switchConversationTab(id);
});
}
}
initConversationClickDelegation();
