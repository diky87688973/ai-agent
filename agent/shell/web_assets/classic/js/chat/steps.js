/* chat/steps.js —— 步骤区骨架：工具步骤挂载、token 占比、未定义变量的静默兜底。
 *
 * 经典界面的**同作用域模块**：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
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
/* 数量一律按段显示"几个主体"：插件段的数量由插件自报（勾选文件数、Skills 数…），
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
"amber":  {dark:"#ffb020",light:"#f59e0b"},
"blue":   {dark:"#4c8dff",light:"#2563eb"},
"teal":   {dark:"#2ee6a6",light:"#12b981"},
"violet": {dark:"#a78bfa",light:"#7c3aed"},
"slate":  {dark:"#9aa6b2",light:"#64748b"},
"purple": {dark:"#e879f9",light:"#c026d3"},
"red":    {dark:"#ff5a5a",light:"#ef4444"},
"plum":   {dark:"#ff4f9a",light:"#e11d74"}};
