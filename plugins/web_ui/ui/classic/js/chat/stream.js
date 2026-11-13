/* chat/stream.js —— SSE 流：读 `/api/chat/stream` 帧、分发事件、开屏订阅全局事件流。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
function escapeHtml(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
function _finishSseStopped(_ctxTab, cid, message){
if(streamAssistantEl)chatProcessAssistant("",false);
finishLiveEdits(_ctxTab);markCurrentTurnStoped();resetTurnState();hideChatLoading();if(message)add("a",message);_ctxTab.abortController=null;_ctxTab.activeRunId="";_clearServerRunning(cid);updateTaskControls();if(typeof renderChatTabs==="function")renderChatTabs();
}
function _finishSseError(_ctxTab, cid, detail){
hideChatLoading();abortPendingToolTags();if(lastLlm){finishLlmTitle(false);lastLlm.tag.className="tag bad";lastLlm.tag.textContent="Fail";lastLlm=null;}if(!anyToolThisTurn){discardPendingSteps();}else{pendingStepEls=[];}add("a","错误: "+JSON.stringify(detail||{}));_ctxTab.abortController=null;_ctxTab.activeRunId="";_clearServerRunning(cid);updateTaskControls();if(typeof renderChatTabs==="function")renderChatTabs();
}
function _finishSseDone(_ctxTab, cid, status){
finalizeAssistantStream("");finishLiveEdits(_ctxTab);_ctxTab.abortController=null;_ctxTab.activeRunId="";_clearServerRunning(cid);hideChatLoading();updateTaskControls();if(typeof renderChatTabs==="function")renderChatTabs();if(status==="done")void refreshConversationTitle(cid);
if(!_ctxTab.subagent)sessionRailActivity(cid);
}
function applySseEvent(ev,_ctxTab,packetCid,onConfirmPause){
if(ev.seq!=null){
  var received=_ctxTab.sseFrames||(_ctxTab.sseFrames=new Set());
  var identity=ev.seq+":"+ev.type+":"+(ev.tool_call_id||"");
  if(received.has(identity))return;
  received.add(identity);
  if(received.size>1024)received.delete(received.values().next().value);
}
if(ev.turn_key!=null){
  var latest=msgs._latestTurnKey;
  if(latest!=null&&ev.turn_key<latest)return;
  if(msgs._lastFinishedTurnKey===ev.turn_key&&ev.type!=="context_layout")return;
  if(ev.type!=="done")chatProcessState(ev.turn_key);
}

if(ev.type==="conversation"){ensureConversationTab(packetCid);if(ev.mode)_ctxTab.selectedMode=normalizeMode(ev.mode);if(renderingContextVisible&&ev.mode)applyMode(ev.mode,false);}
else if(ev.type==="run_started"){chatProcessState(ev.turn_key??ev.seq??(ev.run_id||null));resetSteps();_ctxTab.activeRunId=String(ev.run_id||"");_ctxTab.abortController=_ctxTab.abortController||{global:true};showChatLoading();updateTaskControls();}
else if(ev.type==="mode_changed"&&ev.mode){_ctxTab.selectedMode=normalizeMode(ev.mode);if(renderingContextVisible)applyMode(normalizeMode(ev.mode),false);}
else if(ev.type==="dispatch_title")addDispatchTitle(ev.title||"");
else if(ev.type==="llm_round")addLlmRound(ev.round);
else if(ev.type==="llm_request")onLlmRequest(ev);
else if(ev.type==="llm_response")onLlmResponse(ev);
else if(ev.type==="llm_done"){flushPendingToolTags();if(lastLlm){finishLlmTitle(true);lastLlm.tag.className="tag ok";lastLlm.tag.textContent="Done";}}
else if(ev.type==="usage"){const u=ev.usage||{};const inTok=Number(u.prompt_tokens??0)||0;const outTok=Number(u.completion_tokens??0)||0;const hitTok=Number(u.prompt_cache_hit_tokens??0)||0;const missTok=Number(u.prompt_cache_miss_tokens??0)||0;sessionTokenUsed+=Math.max(0,inTok+outTok);totalPromptTokens+=inTok;totalCompletionTokens+=outTok;totalCacheHitTokens+=hitTok;totalCacheMissTokens+=missTok;if(packetCid===normalizeConversationId(activeConversationId))_updateUsageBottom();void persistUsageAccumulator(packetCid);}
else if(ev.type==="context_compacted"){renderCompactionEvent(ev,_ctxTab);}
else if(ev.type==="context_layout"){applyContextLayoutFromHistory(_ctxTab,{context_layout:ev});}
else if(ev.type==="tool_start"){chatProcessToolStarted();onToolStart(ev);}
else if(ev.type==="tool_progress")onToolProgress(ev);
else if(ev.type==="tool_end"){noteLiveEdit(ev,_ctxTab);onToolEnd(ev);if(ev.todo_list&&ev.todo_list_data){var _td=ev.todo_list_data;renderTodoListFromEvent({items:_td.items||[],all_done:Array.isArray(_td.items)&&_td.items.every(function(it){return !!it.done;}),collapsed:!!_td.collapsed,close:!!_td.close},packetCid);scrollToBottomAfterLayout(msgs,true);}}
else if(ev.type==="open_session"){var sid=normalizeConversationId(ev.session_id);if(sid){ensureConversationTab(sid);var _ot=findConversationTab(sid);if(_ot)_ot.title=ev.name||("会话 "+sid.slice(0,8));}}
else if(ev.type==="tool_preview_update"){var tid2=String(ev.tool_call_id||"").trim();if(tid2){var card=findStepCardForToolCall(tid2);if(card){var pb2=card.querySelector("pre.tool-res");if(pb2){try{var _pj2=JSON.parse(ev.preview||"{}");pb2.textContent=JSON.stringify(_pj2,null,2);}catch(e2){pb2.textContent=String(ev.preview||"");}var lb2=pb2.previousElementSibling;if(lb2&&lb2.classList&&lb2.classList.contains("lbl"))lb2.style.display="block";pb2.style.display="block";}}}}
else if(ev.type==="assistant_delta"){if(anyToolThisTurn){flushPendingSteps();}appendAssistantDelta(ev.delta||"");}
else if(ev.type==="reasoning_delta")appendReasoningDelta(ev);
else if(ev.type==="reasoning_sync")applyReasoningSync(ev);
else if(ev.type==="assistant_markdown"){if(anyToolThisTurn){flushPendingSteps();}var md=ev.markdown;if(typeof md==="string"&&md.trim()){var e=ensureAssistantStreamBubble();if(e){if(streamAssistantText&&!streamAssistantText.endsWith("\n"))streamAssistantText+="\n";streamAssistantText+=md.trim()+"\n";e.innerHTML=renderMarkdown(streamAssistantText);scrollMsgsToBottom();}}}
else if(ev.type==="assistant"){if(anyToolThisTurn){flushPendingSteps();}chatProcessAssistant(ev.content||"",ev.tool_phase);}
else if(ev.type==="peer_message"||ev.type==="queued_user")renderConversationInput(ev,packetCid,false);
else if(ev.type==="confirmation_closed"){closeMatchingConfirmation(ev);}
else if(ev.type==="queue_updated"){if(typeof onQueueUpdated==="function")onQueueUpdated(ev);}
else if(ev.type==="done"){
  if(msgs._chatProcess&&ev.turn_key!=null&&msgs._chatProcess.key!==ev.turn_key)return;
  if(streamAssistantEl)chatProcessAssistant("",false);
  if(ev.turn_key!=null)msgs._lastFinishedTurnKey=ev.turn_key;
  chatProcessFinish(ev.turn_key,ev.turn_status||"done",ev.turn_elapsed_ms);
  _finishSseDone(_ctxTab,packetCid,ev.turn_status||"done");
}
else if(ev.type==="stopped"){_finishSseStopped(_ctxTab,packetCid,ev.message);}
else if(ev.type==="paused_for_user_confirm"){_ctxTab.editedHold=true;hideChatLoading();if(typeof onConfirmPause==="function")onConfirmPause();}
else if(ev.type==="todo_list"){renderTodoListFromEvent(ev,packetCid);scrollToBottomAfterLayout(msgs,true);}
else if(ev.type==="error"){_finishSseError(_ctxTab,packetCid,ev.detail||ev);}
}

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
const packetCid=normalizeConversationId(ev.conversation_id);if(!packetCid){if(window.DEBUG){console.warn("[SSE recv] 已丢弃（conversation_id 缺失或非法）",{streamCid:String(streamCid||""),type:ev&&ev.type,conversation_id:ev&&ev.conversation_id,ev:ev});console.error("[SSE] 数据包缺少或非法 conversation_id，已跳过渲染（不写入任何会话）",{type:ev&&ev.type,conversation_id:ev&&ev.conversation_id});}continue;}withConversationContext(packetCid,function(_ctxTab){applySseEvent(ev,_ctxTab,packetCid,function(){endedAwaitingUserConfirm=true;});});
_routeEventBySource(ev);
}
}
}
}
function handleGlobalSseEvent(ev){
if(!ev||ev.type==="heartbeat"||ev.type==="global_sse_ready")return;
if(ev.type==="plugins_changed"){applyPluginsChanged(ev);return;}
if(ev.type==="settings_changed"){try{document.dispatchEvent(new CustomEvent("ai-agent:settings-changed",{detail:ev.settings||{}}));}catch(_e){}return;}
if(ev.type==="plugin_config_changed"){try{document.dispatchEvent(new CustomEvent("ai-agent:plugin-config-saved",{detail:{plugin:String(ev.plugin||"")}}));}catch(_e){}return;}
if(ev.type==="plugin_event"){try{document.dispatchEvent(new CustomEvent("ai-agent:plugin-event",{detail:ev}));}catch(_e){}return;}
const packetCid=normalizeConversationId(ev.conversation_id);if(!packetCid)return;
withConversationContext(packetCid,function(_ctxTab){applySseEvent(ev,_ctxTab,packetCid,null);});
_routeEventBySource(ev);
}
function startGlobalSse(){
if(window.__aiAgentGlobalSse)return;
try{
var es=new EventSource("/api/events/stream");
window.__aiAgentGlobalSse=es;
es.onmessage=function(e){if(!e||!e.data)return;var ev;try{ev=JSON.parse(e.data);}catch(_err){return;}handleGlobalSseEvent(ev);};
es.onopen=function(){void reconcileConfirmationCards();};
es.onerror=function(){};
}catch(_e){}
}
