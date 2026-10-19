/* chat/llm-rounds.js —— LLM 轮次与工具生命周期：思考卡、工具开始/进度/结束、回合状态复位。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
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
/* 当前无调用方：它把「模型只产出了思考、没有正文」时的
   `lastLlm.reasoningText` 在 `done` 时刻兜底追加成回答。
   追加的内容是实时渲染的产物、不是数据 —— 刷新后走 `loadConversationHistory()`，
   那段内容会消失，因此它不构成一条「回答」。
   思考另有归宿：`reasoning_delta` → `appendReasoningDelta()` →
   右侧步骤面板的思考区（`lastLlm.thPb`）。
   追加还有一处副作用：`done` 时 `streamAssistantText` 已被此前的 `assistant` 分支
   （`finalizeAssistantStream()` 会清空它）清掉，守卫会放行，
   思考于是成为对话区里的又一个回答气泡。
   函数体保留：`lastLlm.reasoningText` 仍被工具卡合并思考面板（`onToolStart`）读取。 */
function promoteReasoningToChatIfNeeded(){
var rt=(lastLlm&&lastLlm.reasoningText||"").trim();
if(!rt)return;
if((streamAssistantText||"").trim())return;
appendAssistantDelta(rt);}
function appendReasoningDelta(ev){
var d=String(ev.delta||"");if(!d)return;if(!lastLlm)return;if(ev.round!=null&&lastLlm.round!=null&&ev.round!==lastLlm.round)return;
lastLlm.reasoningText=(lastLlm.reasoningText||"")+d;lastLlm.chatThinkLastAt=Date.now();if(lastLlm.thLb&&lastLlm.thPb){lastLlm.thLb.style.display="block";lastLlm.thPb.style.display="block";lastLlm.thPb.textContent=lastLlm.reasoningText;scrollToBottom(lastLlm.thPb);}paintChatThink();}
function applyReasoningSync(ev){
var t=String(ev.text||"");if(!lastLlm)return;if(ev.round!=null&&lastLlm.round!=null&&ev.round!==lastLlm.round)return;
lastLlm.reasoningText=t;lastLlm.chatThinkLastAt=Date.now();if(lastLlm.thLb&&lastLlm.thPb){lastLlm.thLb.style.display="block";lastLlm.thPb.style.display="block";lastLlm.thPb.textContent=lastLlm.reasoningText;scrollToBottom(lastLlm.thPb);}paintChatThink();}
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
lastLlm={tag:_muteEl(),msgSpan:_muteEl(),dotsSpan:_muteEl(),dotsTimer:null,round:n,thLb:null,thPb:null,reasoningText:"",reqLb:null,reqPb:null,resLb:null,resPb:null,cardEl:null,stepNum:stepSeq,chatThink:null,chatThinkFull:null,chatThinkStartedAt:Date.now(),chatThinkLastAt:0};
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
lastLlm={tag:tag,msgSpan:msgSpan,dotsSpan:dotsSpan,dotsTimer:timer,round:n,thLb:thLb,thPb:thPb,reasoningText:"",reqLb:rqLb,reqPb:rqPb,resLb:rsLb,resPb:rsPb,cardEl:c,stepNum:stepSeq,chatThink:null,chatThinkFull:null,chatThinkStartedAt:Date.now(),chatThinkLastAt:0};
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
btn.setAttribute("data-cmd-opt",opt);
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
sendBtn.className="cmd-input-btn";
sendBtn.setAttribute("data-cmd-send","1");
row.appendChild(custom);
row.appendChild(sendBtn);
bar.appendChild(row);
bar.setAttribute("data-cmd-cid",normalizeConversationId(ev.conversation_id||activeConversationId));
bar.setAttribute("data-cmd-tid",String(ev.tool_call_id||"").trim());
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
/* 目标工具的查询类调用不进步骤区。
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
appendStep(c);if(mergeKeepOpen)c.classList.add("open");toolOpen.set(tid,{tid:tid,tag:tag,resLb:lb,resPb:pb,previewSlot:pv,args:ev.args||{},script:ev.script||"",spinWrap:spinWrap,stepTitle:_stt,fileSpan:null,progressBadge:null,liveOutPre:isStreamOutputToolScript(ev.script)?pb:null,cmdInputBar:null,chatRunCard:null,chatRunOutPre:null,chatToolRow:null,chatToolRes:null,replay:!!ev._replay});
/* 等待类工具：标题后的秒数逐秒减，用户不用猜模型在睡还是在跑。
   历史回放不启动（见 `renderHistoryToolItem` 的 `_replay`）。 */
if(!ev._replay)desktopStartWaitTicker(tid,ev.script,ev.args||{},function(left,total,elapsed){desktopSetStepSummary(tx,desktopWaitTickText(ev.script,ev.args||{},left,elapsed),true);});
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
