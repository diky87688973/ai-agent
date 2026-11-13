/* chat/history-paging.js —— 会话历史向上翻页：页状态、前插与视口锚定。
 *
 * 同作用域模块：依赖 conversation.js 的 tab / 渲染函数；不引入 import/export。
 * 旧页先在游离容器渲染，再整体前插，避免改动实时流式节点。
 */
var HISTORY_TOP_TRIGGER_PX=4;
var _historyPagingInited=false;

function findHistoryTabByMsgs(el){
for(var i=0;i<conversationTabs.length;i++){
if(conversationTabs[i].msgsHost===el)return conversationTabs[i];
}
return null;
}

function updateHistoryJumpButton(el){
var t=findHistoryTabByMsgs(el);
var b=document.getElementById("chatJumpBottom");
if(!t||!b)return;
var scrollable=el.scrollHeight>el.clientHeight+40;
b.classList.toggle("is-visible",!!(scrollable&&!el._atBottom&&normalizeConversationId(t.id)===normalizeConversationId(activeConversationId)));
}

function withRenderContext(msgsEl,stepsEl,fn){
var prevMsgs=msgs,prevSteps=steps,prevStream=streamAssistantEl,prevText=streamAssistantText;
var prevToolOpen=toolOpen,prevPending=pendingToolTags,prevStepsPending=pendingStepEls;
var prevAnyTool=anyToolThisTurn,prevLoading=chatLoadingEl,prevConfirm=userConfirmCardHost,prevBlocking=userConfirmBlocking;
msgs=msgsEl;steps=stepsEl;streamAssistantEl=null;streamAssistantText="";
toolOpen=new Map();pendingToolTags=[];pendingStepEls=[];anyToolThisTurn=false;
chatLoadingEl=null;userConfirmCardHost=null;userConfirmBlocking=false;
try{return fn();}
finally{
msgs=prevMsgs;steps=prevSteps;streamAssistantEl=prevStream;streamAssistantText=prevText;
toolOpen=prevToolOpen;pendingToolTags=prevPending;pendingStepEls=prevStepsPending;
anyToolThisTurn=prevAnyTool;chatLoadingEl=prevLoading;
userConfirmCardHost=prevConfirm;userConfirmBlocking=prevBlocking;
}
}

function _historyStatus(t,text,retry){
var el=t._historyStatusEl;
if(!el){el=document.createElement("div");el.className="history-load-more";t._historyStatusEl=el;}
el.textContent=text;
if(retry)el.setAttribute("data-history-retry","1");else el.removeAttribute("data-history-retry");
if(!el.parentNode)t.msgsHost.insertBefore(el,t.msgsHost.firstChild);
return el;
}

function _removeHistoryStatus(t){
var el=t._historyStatusEl;
if(el&&el.parentNode)el.parentNode.removeChild(el);
t._historyStatusEl=null;
}

async function fetchHistoryPage(t,url){
var delay=500;
for(;;){
  var response=await fetch(url);
  var body=await response.json();
  if(response.ok&&body&&body.ok===true)return body;
  if(response.status!==503||!body||body.code!=="history_index_pending"){
    throw new Error((body&&body.error)||"history HTTP "+response.status);
  }
  if(findConversationTab(t.id)!==t||getActiveConversationId()!==t.id)return null;
  _historyStatus(t,"正在准备会话历史",false);
  await new Promise(function(resolve){setTimeout(resolve,delay);});
  if(findConversationTab(t.id)!==t||getActiveConversationId()!==t.id)return null;
  delay=Math.min(delay*2,5000);
}
}

function mergeHistoryProcess(t,msgsEl){
var partial=Array.from(msgsEl.querySelectorAll("[data-turn-process]")).pop();
if(partial){
  var existing=t.msgsHost.querySelector("[data-turn-process='"+partial.dataset.turnProcess+"']");
  if(existing&&partial._turnProcessRecord&&existing._turnProcessRecord){
    var source=partial._turnProcessRecord;
    var destination=existing._turnProcessRecord;
    destination.view.body.prepend.apply(destination.view.body,Array.from(source.view.body.childNodes));
    destination.count+=source.count;
    destination.renderer.finish(destination.view,destination.status||"running",destination.count,destination.elapsedMs);
    if(source.renderer.dispose)source.renderer.dispose(source.view);
    partial.remove();
  }
}
}

function _prependHistoryNodes(t,msgsEl,stepsEl){
_removeHistoryStatus(t);
var anchor=t.msgsHost.scrollHeight-t.msgsHost.scrollTop;
mergeHistoryProcess(t,msgsEl);
var mfrag=document.createDocumentFragment();
while(msgsEl.firstChild)mfrag.appendChild(msgsEl.firstChild);
t.msgsHost.insertBefore(mfrag,t.msgsHost.firstChild);
var sfrag=document.createDocumentFragment();
while(stepsEl.firstChild)sfrag.appendChild(stepsEl.firstChild);
t.stepsHost.insertBefore(sfrag,t.stepsHost.firstChild);
t.msgsHost.scrollTop=t.msgsHost.scrollHeight-anchor;
}

async function loadOlderHistory(t){
if(!t)return;
if(t.historyState!=="idle"||t.historyBefore==null)return;
var before=t.historyBefore;
t.historyState="loading";
_historyStatus(t,"加载更早的对话…",false);
try{
var query=t.subagent?{conversation_id:t.parentCid,child_id:t.id}:{conversation_id:t.id};
query.before=String(before);
if(t.historySlice)query.slice="1";
var j=await fetchHistoryPage(t,(t.subagent?"/api/subagents/history?":"/api/chat/history?")+new URLSearchParams(query));
if(!j){_removeHistoryStatus(t);t.historyState="idle";return;}
var items=Array.isArray(j.items)?j.items:[];
var page=j.page||null;
if(!page){_removeHistoryStatus(t);t.historyBefore=null;t.historyState="exhausted";return;}
var detachedMsgs=createDetachedHost("msgs");
var detachedSteps=createDetachedHost("steps");
withRenderContext(detachedMsgs,detachedSteps,function(){
  if(page.omitted)add("a","这段历史有 "+page.omitted+" 条记录超过单条读取上限，已跳过展示。");
  renderHistoryItems(items,t.id);
});
_prependHistoryNodes(t,detachedMsgs,detachedSteps);
var next=page.next_before;
var more=!!(page.has_more&&next!=null&&String(next)!==String(before));
t.historySlice=!!page.slice;
t.historyBefore=more?next:null;
t.historyState=more?"idle":"exhausted";
}catch(e){
t.historyState="error";
_historyStatus(t,"加载更早的对话失败 · 点击重试",true);
console.error("[history-paging] load older failed",t.id,before,e);
}
}

function onHistoryScroll(el){
var t=findHistoryTabByMsgs(el);
if(!t||t.historyState!=="idle"||t.historyBefore==null)return;
if(el.scrollTop<=HISTORY_TOP_TRIGGER_PX)void loadOlderHistory(t);
}

function initHistoryPaging(){
if(_historyPagingInited)return;_historyPagingInited=true;
document.addEventListener("wheel",function(ev){
if(ev.deltaY>=0)return;
var host=ev.target&&ev.target.closest?ev.target.closest(".msgs"):null;
if(!host)return;
var t=findHistoryTabByMsgs(host);
if(t&&t.historyState==="idle"&&host.scrollTop<=HISTORY_TOP_TRIGGER_PX)void loadOlderHistory(t);
},{passive:true});
document.addEventListener("click",function(ev){
var jump=ev.target&&ev.target.closest?ev.target.closest("[data-chat-jump-bottom]"):null;
if(jump){
var jt=findHistoryTabByMsgs(msgs);
if(jt){scrollToBottom(jt.msgsHost,true);updateHistoryJumpButton(jt.msgsHost);}
return;
}
var el=ev.target&&ev.target.closest?ev.target.closest("[data-history-retry]"):null;
if(!el)return;
var t=null;
for(var i=0;i<conversationTabs.length;i++){
if(conversationTabs[i]._historyStatusEl===el){t=conversationTabs[i];break;}
}
if(!t)return;
t.historyState="idle";
el.removeAttribute("data-history-retry");
if(t.historyLoaded)void loadOlderHistory(t);else void loadConversationHistory(t);
});
}

initHistoryPaging();
