/* composer/state.js —— 输入区共享状态：模式/模型选择、服务端在跑标记、停止控制。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
let _goalInfo=null;
let selectedMode="auto";let selectedModel="";let allowedModels=[];
let slashSelectedIndex=0;
/* 读服务端权威的"在跑"。
   SSE 没有游标就不回放，所以"page1 先开跑、page2 才打开"或"跟跑中 F5"
   时，新页面收不到 `run_started` → 判不出忙、停止键永不出现 ——
   那个页面既发不出消息（点了必 409）也停不掉任务。
   数据来源：`/api/chat/ui-state` 的 `state.running`（服务端权威，来自 `RunRegistry`）。
   这里只读一次（页面首次打开那次布局恢复的响应里就带着它），
   不轮询、不新增状态变量；之后仍由 SSE 驱动。
   不维护"忙/闲"镜像，只复用既有的 `abortController` 槽位打一个只读标记 `{server:true}`。 */
function _serverRunningCid(cid){var t=cid?findConversationTab(cid):null;return !!(t&&t.abortController&&t.abortController.server===true);}
/* 清掉「服务端说它在跑」的标记。
   `done`/`stopped`/`error` 三个分支清的是 `_ctxTab.abortController` ——
   那是派发上下文对应的 tab；而这个标记是页面首次打开时按 `/api/chat/ui-state`
   打在当时那个 tab 上的。中途接入的页面里两者不一定是同一个 tab
   （`_routeEventBySource` 会按来源改派），于是标记漏清 →
   停止键永远挂着、发送键永远隐藏。
   这里改用帧自带的会话 id 精确清，不依赖 `_ctxTab` 是谁。 */
function _clearServerRunning(id){var cid=normalizeConversationId(id);if(!cid)return;var t=findConversationTab(cid);if(t&&t.abortController&&t.abortController.server===true){t.abortController=null;t.activeRunId="";}}
function _markServerRunning(id){var cid=normalizeConversationId(id);if(!cid)return;var t=findConversationTab(cid);if(!t||t.abortController)return;t.abortController={server:true};}
function _stopServerRunningTab(t){if(!t)return;var cid=t.id;try{t.stopRequested=true;fetch("/api/chat/stop",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:cid,run_id:String(t.activeRunId||"")})}).catch(function(){});}catch(_e){}try{fetch("/api/chat/autonomous",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:cid,enabled:false})}).catch(function(){});}catch(_e2){}_autoEnabled=false;if(typeof updateAutoToggleUI==="function")updateAutoToggleUI();t.stopRequested=true;try{updateTaskControls();}catch(_e3){}try{renderChatTabs();}catch(_e4){}}
function updateTaskControls(){var t=getActiveTab();var canStop=!!(t&&t.abortController)||_autoEnabled;if(goBtn){goBtn.classList.toggle("hidden",canStop);goBtn.disabled=!canStop&&isConversationBusy();}if(stopTaskBtn){stopTaskBtn.classList.toggle("hidden",!canStop);stopTaskBtn.disabled=!canStop;}}
function stopCurrentTask(){var t=getActiveTab();var cid=t?t.id:getActiveConversationId();if(!t||!t.abortController){/* 服务端说这条会话在跑、但本页没有本地控制器（中途接入）→ 仍要把停止请求发给服务端，
   不能直接 return：否则点了停止什么都不发生。
   这里不做 markCurrentTurnStoped：服务端才是权威，本地标记会与实际状态不符。 */
if(_serverRunningCid(t&&t.id)){_stopServerRunningTab(t);return;}
if(_autoEnabled&&cid){_autoEnabled=false;updateAutoToggleUI();fetch("/api/chat/autonomous",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:cid,enabled:false})}).catch(function(){});withConversationContext(cid,function(){markCurrentTurnStoped();resetTurnState();hideChatLoading();add("a","自主模式已停止。");});updateTaskControls();}return;}t.stopRequested=true;var rid=String(t.activeRunId||"");try{fetch("/api/chat/stop",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:t.id,run_id:rid})}).catch(function(){});}catch(_e){}/* 只有真控制器才 abort。`{server:true}` 是"服务端说它在跑"
       的标记（中途接入的页面没有本地控制器），对它调 abort 只会抛错被吞。 */
try{if(t.abortController&&typeof t.abortController.abort==="function")t.abortController.abort();}catch(_e2){}_autoEnabled=false;updateAutoToggleUI();try{fetch("/api/chat/autonomous",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:t.id,enabled:false})}).catch(function(){});}catch(_e3){}withConversationContext(t.id,function(){markCurrentTurnStoped();resetTurnState();hideChatLoading();add("a","任务已停止。");});t.abortController=null;t.activeRunId="";updateTaskControls();renderChatTabs();}
