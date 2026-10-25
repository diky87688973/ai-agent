/* core/boot.js —— 经典界面启动引导：会话 id 存储键、初始标签、全局状态变量。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
// 调试：控制台执行 window.DEBUG=1（或 DEBUG=1）后输出 SSE / 预览等 console 日志
// 主题与全页只读选区的实现在 theme-ui.js（内联包首部已包含该脚本）
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
/* 开局激活哪个会话，只看本地（服务端不参与）：
   `?conversation_id=` > 本地布局记着的激活会话 > 本地会话记忆 > cookie > 新会话。
   本地空空如也就是新会话 —— 不去服务端拉一个来激活。 */
function getOrCreateConversationId(){let id=getUrlConversationId();if(id){storeConversationId(id);return id;}var layout=getStoredConversationLayout();if(layout&&layout.active_conversation_id){storeConversationId(layout.active_conversation_id);return layout.active_conversation_id;}id=getStoredConversationId();if(id)return id;id=normalizeConversationId(readCookieValue("sessionId"));if(id){storeConversationId(id);clearCookie("sessionId");return id;}id=newConversationId();storeConversationId(id);return id;}
function createDetachedHost(className){var d=document.createElement("div");d.className=className||"";return d;}
function buildTodoArea(){var n=document.createElement("div");n.className="todo-list-area hidden";n.style.display="";var hdr=document.createElement("div");hdr.className="todo-list-header";var ttl=document.createElement("span");ttl.className="todo-list-title";ttl.innerHTML='<svg class="todo-title-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><path d="M9 6h11M9 12h11M9 18h11"/><path d="M4 6h.01M4 12h.01M4 18h.01"/></svg><span>任务</span>';var cnt=document.createElement("span");cnt.className="todo-list-count";cnt.textContent="0 已完成";var ic=document.createElement("span");ic.className="todo-collapse-icon";ic.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';hdr.appendChild(ttl);hdr.appendChild(cnt);hdr.appendChild(ic);var bd=document.createElement("div");bd.className="todo-list-body";var sc=document.createElement("div");sc.className="todo-list-scroll";bd.appendChild(sc);n.appendChild(hdr);n.appendChild(bd);return n;}
function makeConversationTab(id){id=normalizeConversationId(id)||newConversationId();var pane=document.createElement("div");pane.className="chat-conversation-pane";var mh=createDetachedHost("msgs");var td=buildTodoArea();pane.appendChild(mh);pane.appendChild(td);return {id:id,title:"会话 "+id.slice(0,8),conversationPane:pane,msgsHost:mh,stepsHost:createDetachedHost("steps"),todoArea:td,selectedMode:"auto",selectedModel:"",reasoningEffort:"",abortController:null,activeRunId:"",stopRequested:false,stepSeq:0,lastLlm:null,llmStreamBuffer:{round:null,reqHtml:"",resHtml:"",consumed:false},pendingToolTags:[],anyToolThisTurn:false,pendingStepEls:[],streamAssistantEl:null,streamAssistantText:"",pendingDeltaSeparator:false,seenDispatchTitle:"",toolOpen:new Map(),lastAnalysisTail:"",chatLoadingEl:null,userConfirmCardHost:null,userConfirmBlocking:false,todoUnread:false,settingsLoaded:false,sessionTokenUsed:0,totalPromptTokens:0,totalCompletionTokens:0,totalCacheHitTokens:0,totalCacheMissTokens:0,lastContextLayout:null};}
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
function setActiveConversationId(id,opts){id=normalizeConversationId(id)||newConversationId();var t=ensureConversationTab(id);activeConversationId=id;sessionId=id;conv=id;storeConversationId(id);t.id=id;t.title=t.title||("会话 "+id.slice(0,8));if(typeof cid!=="undefined"&&cid)cid.textContent=id.slice(0,8);if(typeof renderChatTabs==="function")renderChatTabs();if(typeof _updateUsageBottom==="function")_updateUsageBottom();}
let sessionId=activeConversationId;let conv=sessionId,stepSeq=0,lastLlm=null;let llmStreamBuffer={round:null,reqHtml:"",resHtml:"",consumed:false};let pendingToolTags=[];let anyToolThisTurn=false;let pendingStepEls=[];let streamAssistantEl=null,streamAssistantText="";let pendingDeltaSeparator=false;let seenDispatchTitle="";/* 上下文占用率的分母 = 模型窗口（内核在 context_layout 里给）。
   没给时退回下面这个兜底值，界面会标明口径。 */
var SESSION_TOKEN_LIMIT=1000000;
function setModelContextWindow(n){var v=Number(n??0)||0;if(v>0)SESSION_TOKEN_LIMIT=v;}let sessionTokenUsed=0;
let totalPromptTokens=0,totalCompletionTokens=0,totalCacheHitTokens=0,totalCacheMissTokens=0;
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
