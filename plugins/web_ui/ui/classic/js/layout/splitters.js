(function initClassicMainSplit(){
/* layout/splitters.js —— 布局：左右分栏拖拽、会话栏宽度、尺寸持久化与开屏初始化。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
var STORAGE_KEY="aiAgent.classicMainSplit";
/* 拖拽分栏时为对话区保留的目标宽度。
   不约束浏览器窗口缩窄；窗口变窄时输入区按钮组换行。 */
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
