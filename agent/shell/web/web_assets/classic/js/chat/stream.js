/* chat/stream.js —— SSE 流：读 `/api/chat/stream` 帧、分发事件、开屏订阅全局事件流。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
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
add("a","⚠️ 系统检测到意外断开连接。可能原因：网络波动、服务器繁忙、调用工具次数达到上限。部分工具已运行完毕（见右侧步骤面板），可重新发起对话尝试恢复，或将复杂任务拆分为多步执行。");
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
       此处不覆盖用户当场的选择。*/if(renderingContextVisible){if(ev.mode)applyMode(ev.mode,false);}}
else if(ev.type==="run_started"){_ctxTab.activeRunId=String(ev.run_id||"");}
else if(ev.type==="mode_changed"&&ev.mode){_ctxTab.selectedMode=normalizeMode(ev.mode);if(renderingContextVisible)applyMode(normalizeMode(ev.mode),false);}
else if(ev.type==="dispatch_title")addDispatchTitle(ev.title||"");
else if(ev.type==="llm_round")addLlmRound(ev.round);
else if(ev.type==="llm_request")onLlmRequest(ev);
else if(ev.type==="llm_response")onLlmResponse(ev);
else if(ev.type==="llm_done"){flushPendingToolTags();if(lastLlm){finishLlmTitle(true);lastLlm.tag.className="tag ok";lastLlm.tag.textContent="Done";}}
else if(ev.type==="usage"){const u=ev.usage||{};const inTok=Number(u.prompt_tokens??0)||0;const outTok=Number(u.completion_tokens??0)||0;const hitTok=Number(u.prompt_cache_hit_tokens??0)||0;const missTok=Number(u.prompt_cache_miss_tokens??0)||0;sessionTokenUsed+=Math.max(0,inTok+outTok);totalPromptTokens+=inTok;totalCompletionTokens+=outTok;totalCacheHitTokens+=hitTok;totalCacheMissTokens+=missTok;_updateUsageBottom();void persistUsageAccumulator();}
else if(ev.type==="context_layout"){_ctxTab.lastContextLayout=ev;setModelContextWindow(ev.model_max_context_tokens);if(renderingContextVisible&&packetCid===normalizeConversationId(activeConversationId))_updateUsageBottom();}
else if(ev.type==="tool_start")onToolStart(ev);
else if(ev.type==="tool_progress")onToolProgress(ev);
else if(ev.type==="tool_end"){noteLiveEdit(ev,_ctxTab);onToolEnd(ev);if(ev.todo_list&&ev.todo_list_data){var _td=ev.todo_list_data;renderTodoListFromEvent({items:_td.items||[],all_done:Array.isArray(_td.items)&&_td.items.every(function(it){return !!it.done;}),collapsed:!!_td.collapsed,close:!!_td.close},packetCid);scrollToBottomAfterLayout(msgs,true);}}
else if(ev.type==="open_session"){var sid=normalizeConversationId(ev.session_id);if(sid){ensureConversationTab(sid);var _ot=findConversationTab(sid);if(_ot)_ot.title=ev.name||("会话 "+sid.slice(0,8));}}
else if(ev.type==="tool_preview_update"){var tid2=String(ev.tool_call_id||"").trim();if(tid2){var card=findStepCardForToolCall(tid2);if(card){var pb2=card.querySelector("pre.tool-res");if(pb2){try{var _pj2=JSON.parse(ev.preview||"{}");pb2.textContent=JSON.stringify(_pj2,null,2);}catch(e2){pb2.textContent=String(ev.preview||"");}var lb2=pb2.previousElementSibling;if(lb2&&lb2.classList&&lb2.classList.contains("lbl"))lb2.style.display="block";pb2.style.display="block";}var tag2=card.querySelector(".ch .tag");if(tag2){try{var _pj3=JSON.parse(ev.preview||"{}");if(_pj3&&_pj3.ok){tag2.textContent="Done";tag2.className="tag ok";}else{tag2.textContent="Fail";tag2.className="tag bad";}}catch(e3){}}}}}
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
else if(ev.type==="done"){finalizeAssistantStream("");finishLiveEdits(_ctxTab);_clearServerRunning(packetCid);void refreshConversationTitle(packetCid);}
else if(ev.type==="stopped"){finishLiveEdits(_ctxTab);markCurrentTurnStoped();resetTurnState();hideChatLoading();if(ev.message)add("a",ev.message);_clearServerRunning(packetCid);}
else if(ev.type==="paused_for_user_confirm"){_ctxTab.editedHold=true;hideChatLoading();endedAwaitingUserConfirm=true;}
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
if(ev.type==="plugins_changed"){applyPluginsChanged(ev);return;}
if(ev.type==="plugin_event"){try{document.dispatchEvent(new CustomEvent("ai-agent:plugin-event",{detail:ev}));}catch(_e){}return;}
const packetCid=normalizeConversationId(ev.conversation_id);if(!packetCid)return;
withConversationContext(packetCid,function(_ctxTab){
if(ev.type==="conversation"){ensureConversationTab(packetCid);if(ev.mode)_ctxTab.selectedMode=normalizeMode(ev.mode);if(ev.model)_ctxTab.selectedModel=String(ev.model||"");if(renderingContextVisible){if(ev.mode)applyMode(ev.mode,false);if(ev.model)applyModel(ev.model);}}
else if(ev.type==="run_started"){_ctxTab.activeRunId=String(ev.run_id||"");_ctxTab.abortController=_ctxTab.abortController||{global:true};showChatLoading();}
else if(ev.type==="mode_changed"&&ev.mode){_ctxTab.selectedMode=normalizeMode(ev.mode);if(renderingContextVisible)applyMode(normalizeMode(ev.mode),false);}
else if(ev.type==="dispatch_title")addDispatchTitle(ev.title||"");
else if(ev.type==="llm_round")addLlmRound(ev.round);
else if(ev.type==="llm_request")onLlmRequest(ev);
else if(ev.type==="llm_response")onLlmResponse(ev);
else if(ev.type==="llm_done"){flushPendingToolTags();if(lastLlm){finishLlmTitle(true);lastLlm.tag.className="tag ok";lastLlm.tag.textContent="Done";}}
else if(ev.type==="usage"){const u=ev.usage||{};const inTok=Number(u.prompt_tokens??0)||0;const outTok=Number(u.completion_tokens??0)||0;const hitTok=Number(u.prompt_cache_hit_tokens??0)||0;const missTok=Number(u.prompt_cache_miss_tokens??0)||0;sessionTokenUsed+=Math.max(0,inTok+outTok);totalPromptTokens+=inTok;totalCompletionTokens+=outTok;totalCacheHitTokens+=hitTok;totalCacheMissTokens+=missTok;_updateUsageBottom();void persistUsageAccumulator();}
else if(ev.type==="context_layout"){_ctxTab.lastContextLayout=ev;setModelContextWindow(ev.model_max_context_tokens);if(renderingContextVisible&&packetCid===normalizeConversationId(activeConversationId))_updateUsageBottom();}
else if(ev.type==="tool_start")onToolStart(ev);
else if(ev.type==="tool_progress")onToolProgress(ev);
else if(ev.type==="tool_end"){noteLiveEdit(ev,_ctxTab);onToolEnd(ev);if(ev.todo_list&&ev.todo_list_data){var _td=ev.todo_list_data;renderTodoListFromEvent({items:_td.items||[],all_done:Array.isArray(_td.items)&&_td.items.every(function(it){return !!it.done;}),collapsed:!!_td.collapsed,close:!!_td.close},packetCid);scrollToBottomAfterLayout(msgs,true);}}
else if(ev.type==="open_session"){var sid=normalizeConversationId(ev.session_id);if(sid){ensureConversationTab(sid);var _ot=findConversationTab(sid);if(_ot)_ot.title=ev.name||("会话 "+sid.slice(0,8));}}
else if(ev.type==="tool_preview_update"){var tid2=String(ev.tool_call_id||"").trim();if(tid2){var card=findStepCardForToolCall(tid2);if(card){var pb2=card.querySelector("pre.tool-res");if(pb2){try{var _pj2=JSON.parse(ev.preview||"{}");pb2.textContent=JSON.stringify(_pj2,null,2);}catch(e2){pb2.textContent=String(ev.preview||"");}var lb2=pb2.previousElementSibling;if(lb2&&lb2.classList&&lb2.classList.contains("lbl"))lb2.style.display="block";pb2.style.display="block";}}}}
else if(ev.type==="assistant_delta"){if(anyToolThisTurn){flushPendingSteps();}appendAssistantDelta(ev.delta||"");}
else if(ev.type==="reasoning_delta")appendReasoningDelta(ev);
else if(ev.type==="reasoning_sync")applyReasoningSync(ev);
else if(ev.type==="assistant_markdown"){if(anyToolThisTurn){flushPendingSteps();}var md=ev.markdown;if(typeof md==="string"&&md.trim()){var e=ensureAssistantStreamBubble();if(e){if(streamAssistantText&&!streamAssistantText.endsWith("\n"))streamAssistantText+="\n";streamAssistantText+=md.trim()+"\n";e.innerHTML=renderMarkdown(streamAssistantText);scrollMsgsToBottom();}}}
else if(ev.type==="assistant"){if(anyToolThisTurn){flushPendingSteps();}if(!finalizeAssistantStream(ev.content||"")){add("a",ev.content||"");}}
else if(ev.type==="peer_message"){addPeerMessage(ev.content||"",ev.sender_name||"",ev.sender||"");}
else if(ev.type==="queued_user"){var _qb=add("u",ev.content||"（截图）",ev);var _qa=Array.isArray(ev.attachments)?ev.attachments:[];if(_qa.length&&_qb&&window.AIA&&AIA.buildMsgAttachStrip){try{_qb.appendChild(AIA.buildMsgAttachStrip(packetCid,null,_qa));}catch(_qe){}}}
else if(ev.type==="queue_updated"){if(typeof onQueueUpdated==="function")onQueueUpdated(ev);}
else if(ev.type==="done"){finalizeAssistantStream("");finishLiveEdits(_ctxTab);_ctxTab.abortController=null;_ctxTab.activeRunId="";hideChatLoading();updateTaskControls();if(typeof renderChatTabs==="function")renderChatTabs();void refreshConversationTitle(packetCid);}
else if(ev.type==="stopped"){finishLiveEdits(_ctxTab);markCurrentTurnStoped();resetTurnState();hideChatLoading();if(ev.message)add("a",ev.message);_ctxTab.abortController=null;_ctxTab.activeRunId="";updateTaskControls();if(typeof renderChatTabs==="function")renderChatTabs();}
else if(ev.type==="paused_for_user_confirm"){_ctxTab.editedHold=true;hideChatLoading();}
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
