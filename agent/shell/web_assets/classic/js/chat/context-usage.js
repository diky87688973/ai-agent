/* chat/context-usage.js —— 上下文分层：段配色、悬浮明细、用量环与底部用量条。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
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
if(k==="mode")return "#f3ce0d";
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
function bindCtxLayoutTooltip(barHost, segs, colors, markerPct){
var tt=ensureCtxLayoutTooltip();
var filtered=[];
for(var i=0;i<segs.length;i++){var s=segs[i];if(!s)continue;filtered.push(s);}
function showTip(){
if(ctxLayoutTipHideTimer){clearTimeout(ctxLayoutTipHideTimer);ctxLayoutTipHideTimer=null;}
if(!filtered.length){if(tt){tt.style.display="none";tt.innerHTML="";}return;}
tt.innerHTML=buildCtxLayoutTooltipHtml(filtered,colors,markerPct);
tt.style.display="block";
positionCtxLayoutTooltip(tt,barHost);
}
barHost.addEventListener("mouseenter",showTip);
barHost.addEventListener("mouseleave",function(){scheduleHideCtxLayoutTooltip();});
}
function formatCompactTokens(n){var x=Math.max(0,Math.floor(Number(n)||0));if(x>=1e9){var v=x/1e9;return (v>=100?v.toFixed(0):v>=10?v.toFixed(1):v.toFixed(2)).replace(/\.?0+$/,"")+"B";}if(x>=1e6){var v2=x/1e6;return (v2>=100?v2.toFixed(0):v2>=10?v2.toFixed(1):v2.toFixed(2)).replace(/\.?0+$/,"")+"M";}if(x>=1e3){var v3=x/1e3;return (v3>=100?v3.toFixed(0):v3.toFixed(1)).replace(/\.0+$/,"")+"K";}return String(x);}
function buildUsageRing(){const million=Math.floor(sessionTokenUsed/SESSION_TOKEN_LIMIT);const p=tokenPercent();const used=Math.max(0,Math.floor(sessionTokenUsed));const ring=document.createElement("span");ring.className="usage-ring";ring.style.setProperty("--p",String(p));const totalCache=totalCacheHitTokens+totalCacheMissTokens;const hitPct=totalCache>0?Math.round(totalCacheHitTokens/totalCache*100):0;ring.title="已用: "+used.toLocaleString()+"\n输入: "+totalPromptTokens.toLocaleString()+" (显示 "+formatCompactTokens(totalPromptTokens)+")\n输出: "+totalCompletionTokens.toLocaleString()+" (显示 "+formatCompactTokens(totalCompletionTokens)+")\nKV缓存命中: "+totalCacheHitTokens.toLocaleString()+" ("+hitPct+"%)\n未命中: "+totalCacheMissTokens.toLocaleString();const num=document.createElement("span");num.className="usage-num";num.textContent=million;ring.appendChild(num);return ring;}
function ctxDisplaySegments(lay){
var raw=lay&&Array.isArray(lay.segments)?lay.segments:[];
var total=0;
for(var i=0;i<raw.length;i++){
var key=String(raw[i]&&raw[i].key||"");
if(key!=="remaining")total+=Math.max(0,Math.floor(Number(raw[i]&&raw[i].tokens)||0));
}
var limit=Math.max(0,Math.floor(Number(lay&&lay.model_max_context_tokens)||0));
var budget=Math.max(0,Math.floor(Number(lay&&lay.budget_tokens)||0));
var denom=limit>0?Math.max(limit,total,1):Math.max(budget,total,1);
var out=[];
for(var j=0;j<raw.length;j++){
var seg=raw[j];
if(!seg)continue;
var key2=String(seg.key||"");
if(key2==="remaining")continue;
var copy={};
for(var k in seg)copy[k]=seg[k];
copy.pct=roundPct(100*Math.max(0,Math.floor(Number(seg.tokens)||0))/denom);
out.push(copy);
}
var rest=Math.max(0,denom-total);
out.push({key:"remaining",label:"剩余容量",tokens:rest,pct:roundPct(100*rest/denom)});
return out;
}
function roundPct(v){return Math.round((Number(v)||0)*1000000)/1000000;}
function compactMarkerPct(lay){
var windowTokens=Math.max(0,Math.floor(Number(lay&&lay.model_max_context_tokens)||0));
var budget=Math.max(0,Math.floor(Number(lay&&lay.budget_tokens)||0));
if(!windowTokens||!budget||budget>=windowTokens)return -1;
return Math.max(0,Math.min(100,(windowTokens-budget)*100/windowTokens));
}

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
var row3=document.createElement("div");row3.className="ub-row ub-row-ctx";
var t3=document.createElement("span");t3.className="ub-title";t3.textContent="上下文视图";
var barHost=document.createElement("div");barHost.className="ctx-bar-host";
var tabCtx=typeof getActiveTab==="function"?getActiveTab():null;
var lay=tabCtx&&tabCtx.lastContextLayout;
var segs=ctxDisplaySegments(lay);
/* 快照里还留着上一次的插件段。未装载的不画。 */
if(loadedPlugins){
segs=segs.filter(function(sg){
var m=/^plugin:(.+)$/.exec(String(sg&&sg.key||""));
if(!m)return true;
return !!loadedPlugins[m[1]];
});
}

/* 段色取自主题令牌（两套主题各一组），JS 不写死颜色。 */
/* 非插件段的色名：弹窗与分段条共用同一个取色函数，两处必然同色。 */
/* 弹窗与分段条共用 ctxSegmentColor，两处必然同色。 */
var colors={system:ctxSegmentColor("system"),summary:ctxSegmentColor("summary"),skill:ctxSegmentColor("skill"),resident:ctxSegmentColor("resident"),full_recent:ctxSegmentColor("full_recent"),mode:ctxSegmentColor("mode"),remaining:ctxSegmentColor("remaining")};
/* 插件段的颜色与渲染由贡献表注册：段 key 是 `plugin:<插件名>`。
   开屏拉 `/api/ctx-segment-styles` 后调用 ctxSegments.register；
   color 给色名（壳层按当前主题取深/浅两套）或 `#rrggbb` 定值。 */
if(!segs.length){var empty=document.createElement("span");empty.className="ctx-bar-empty";empty.textContent="—";barHost.appendChild(empty);}
else{var bar=document.createElement("div");bar.className="ctx-bar";
for(var si=0;si<segs.length;si++){var sg=segs[si];if(!sg)continue;
var tok=Math.max(0,Math.floor(Number(sg.tokens)||0));
var segKey=String(sg.key||"");
var col=segKey==="remaining"?_segVar("--c-track","#2a2d32"):ctxSegmentColor(segKey);
var colEl=document.createElement("span");colEl.className="ctx-seg-col"+(tok>0?"":" ctx-seg-col-zero");
if(tok>0){colEl.style.flex=String(tok)+" 1 0";colEl.style.minWidth="2px";}else{colEl.style.flex="0 0 2px";colEl.style.minWidth="2px";colEl.style.maxWidth="2px";}
var fill=document.createElement("span");fill.className="ctx-seg ctx-seg-"+String(sg.key||"").replace(/[^a-z0-9_-]/gi,"");fill.style.background=col;fill.style.height="10px";fill.style.borderRadius="0";fill.style.flexShrink="0";fill.style.width="100%";fill.style.display="block";fill.style.boxSizing="border-box";
colEl.appendChild(fill);bar.appendChild(colEl);}
barHost.appendChild(bar);bindCtxLayoutTooltip(barHost,segs,colors,compactMarkerPct(lay));}
row3.appendChild(t3);row3.appendChild(barHost);
el.innerHTML='';el.appendChild(sheet);el.appendChild(row3);
}

function applyUsageAccumulatorPayload(j){if(!j||typeof j!=="object")return;sessionTokenUsed=Number(j.session_token_used??0)||0;totalPromptTokens=Number(j.total_prompt_tokens??0)||0;totalCompletionTokens=Number(j.total_completion_tokens??0)||0;totalCacheHitTokens=Number(j.total_cache_hit_tokens??0)||0;totalCacheMissTokens=Number(j.total_cache_miss_tokens??0)||0;if(conv)_updateUsageBottom();}
var usageAccumulatorSeq=0;
async function loadUsageAccumulator(){try{
const cid=String(activeConversationId||"");if(!cid)return;
const seq=++usageAccumulatorSeq;
const r=await fetch("/api/usage-accumulator?conversation_id="+encodeURIComponent(cid));if(!r.ok)return;
const j=await r.json();
if(seq!==usageAccumulatorSeq||String(activeConversationId||"")!==cid)return;
applyUsageAccumulatorPayload(j);
}catch(e){}}
async function persistUsageAccumulator(){try{/* cid 为空时不发写请求 —— 空 cid 必被后端拒（invalid conversation_id），纯噪音。 */
if(!String(activeConversationId||""))return;/* 写操作走 body（约定：写=body，读=query）。
         缺 conversation_id 时后端返回 `invalid conversation_id`，
         会话用量永不落盘（刷新即归零）。 */
await fetch("/api/usage-accumulator",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:String(activeConversationId||""),session_token_used:sessionTokenUsed,total_prompt_tokens:totalPromptTokens,total_completion_tokens:totalCompletionTokens,total_cache_hit_tokens:totalCacheHitTokens,total_cache_miss_tokens:totalCacheMissTokens})});}catch(e){}}
/* 工具展示清单（`/api/tool-labels`）：中文名与图标由工具自己声明。
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
