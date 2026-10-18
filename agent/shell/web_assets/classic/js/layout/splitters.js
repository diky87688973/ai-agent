/* layout/splitters.js —— 布局：左右分栏拖拽、会话栏宽度、尺寸持久化与开屏初始化。
 *
 * 经典界面的**同作用域模块**：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
var STORAGE_KEY="aiAgent.classicMainSplit";
/* 对话区最小宽度（与样式表 `.chat{min-width}` 同值）。
   实测口径：把对话区逐步压窄，量输入区那一行**最右侧控件**何时越过容器右边界 ——
   669px 时"发送"越界 1px，670px 起为 0。写死一个数而不是每次运行时量：
   布局是跟着拖拽连续变的，运行时量会一路抖动；插件按钮让这一行变长时，
   把两个数字一起往上调。 */
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
initModePicker();
initReasoningPicker();
initKbAndSlashUi();
initMarkedExtensions();
/* 面板清单与动作清单先取回（渲染各入口都按数据来）；
   段色经 `/api/ctx-segment-styles` 注册；面板脚本仍预载（内容/交互）；
   开屏脚本（`/api/boot-scripts`）排在面板脚本之后。
   注册与预载赶在第一次画上下文条之前，否则那一段只能先按兜底色画。 */
void loadCtxSegmentStyles().then(function(){
void loadPluginPanels().then(function(){
void preloadPluginScripts().then(function(){
void preloadBootScripts().then(function(){
if(typeof _updateUsageBottom==="function")_updateUsageBottom();
});
});
});
});
void loadPluginActions();
/* 工具展示清单（中文名 + 图标）与面板/动作清单一样，都是**数据驱动**的入口：
   工具自己声明自己长什么样，界面不维护工具名表。 */
void loadToolLabels();
if(goBtn)goBtn.addEventListener("click",function(){void sendChatMessage();});
if(stopTaskBtn)stopTaskBtn.addEventListener("click",function(){_autoEnabled=false;updateAutoToggleUI();stopCurrentTask();});
if(autoToggleBtn)autoToggleBtn.addEventListener("click",function(){renderGoalDialog();});
var railNewEl=document.getElementById("sessionRailNew");
if(railNewEl)railNewEl.addEventListener("click",function(){createConversationTab();});
if(chatMoreBtn)chatMoreBtn.addEventListener("click",function(){void toggleSessionMenu();});
if(ta){ta.addEventListener("keydown",function(e){if(e.isComposing)return;var sh=slashPop&&!slashPop.classList.contains("hidden");var atp2=getAtPop();var ah=atp2&&atp2.style.visibility!=="hidden";var k=e.key,kl=k.toLowerCase(),ci=(slashPop&&slashPop.children)?slashPop.children:[];if(ah){if(k==="Escape"){e.preventDefault();hideAtPop();return;}if(k==="ArrowDown"||k==="ArrowUp"){e.preventDefault();var ai=getAtList().querySelectorAll(".at-item");var vi=[];for(var i2=0;i2<ai.length;i2++){if(ai[i2].style.display!=="none")vi.push(i2);}if(!vi.length)return;var idx=vi.indexOf(atSelectedIndex);if(idx<0)idx=(k==="ArrowDown"?0:vi.length-1);else if(k==="ArrowDown"){if(idx<vi.length-1)idx++;}else{if(idx>0)idx--;}atSelectedIndex=vi[idx];updateAtSelection();var row=ai[atSelectedIndex];if(row&&row.scrollIntoView)try{row.scrollIntoView({block:"nearest"});}catch(_){}return;}if(k==="ArrowRight"){e.preventDefault();var aiR=getAtList().querySelectorAll(".at-item");var pR=atSelectedIndex;if(pR<0||pR>=aiR.length)pR=0;if(aiR.length&&aiR[pR]&&aiR[pR].dataset.type==="dir")loadAtDir(aiR[pR].dataset.path);return;}if(k==="ArrowLeft"){e.preventDefault();var curL=getAtCurPath().textContent.trim();var parentStored=getAtCurPath().dataset.parent||"";if(!parentStored)return;var pU=parentStored||curL.substring(0,curL.lastIndexOf("/"));if(!pU||pU.length<3){if(pU&&pU.length===2&&pU.charAt(1)===":"){pU=pU+"/";}else{pU=curL;}}if(pU!==curL)atRestoreSelectPath=curL;loadAtDir(pU);return;}if(k==="Enter"||e.code==="Enter"||e.code==="NumpadEnter"){e.preventDefault();var ai2=getAtList().querySelectorAll(".at-item");var pick=atSelectedIndex;if(pick<0||pick>=ai2.length)pick=0;if(ai2.length&&ai2[pick]){var sel=ai2[pick];selectAtFile(sel.dataset.path);}return;}if(atMentionActiveAtCursor()){return;}hideSlashPop();hideAtPop();return;}if(!sh&&!ah){if(!e.shiftKey&&(e.key==="Enter"||e.code==="Enter"||e.code==="NumpadEnter")){e.preventDefault();if(goBtn)goBtn.click();else void sendChatMessage();}return;}if(sh&&k==="Escape"){e.preventDefault();hideSlashPop();return;}if(sh&&(k==="ArrowDown"||k==="ArrowUp")){e.preventDefault();var vi3=[];for(var i3=0;i3<ci.length;i3++){if(ci[i3].style.display!=="none")vi3.push(i3);}if(!vi3.length)return;var idx3=vi3.indexOf(slashSelectedIndex);if(idx3<0)idx3=(k==="ArrowDown"?-1:0);else if(k==="ArrowDown"){if(idx3<vi3.length-1)idx3++;}else{if(idx3>0)idx3--;}var cur3=ci[slashSelectedIndex];if(cur3)cur3.classList.remove("selected");slashSelectedIndex=vi3[idx3];var nxt3=ci[slashSelectedIndex];if(nxt3)nxt3.classList.add("selected");updateSlashPopHints();return;}if(sh&&(k==="Enter"||e.code==="Enter"||e.code==="NumpadEnter")){e.preventDefault();var sel4=ci[slashSelectedIndex];if(sel4&&sel4.dataset&&sel4.dataset.slash){applyMode(sel4.dataset.slash);ta.value="";}else hideSlashPop();return;}if(kl==="a"||kl==="p"||kl==="e"){e.preventDefault();hideSlashPop();ta.value="";if(kl==="a")applyMode("auto");else if(kl==="p")applyMode("plan");else applyMode("execute");return;}hideSlashPop();});ta.addEventListener("blur",function(){if(slashPop&&!slashPop.classList.contains("hidden"))hideSlashPop();});ta.addEventListener("mouseup",function(){if(slashPop&&!slashPop.classList.contains("hidden"))hideSlashPop();});}
document.getElementById("tabSteps")?.addEventListener("click",function(){selectSidePane("steps");});
window.addEventListener("beforeunload",function(){try{saveActiveConversationView();storeConversationLayoutLocal();}catch(e){}});
/* **先恢复会话，再取用量**。
   `loadUsageAccumulator()` 若排在 `restoreConversationLayoutFromServer()` 之前：
   `activeConversationId` 初始值来自本地（URL/sessionStorage），**可能为空**，
   用量 GET 于是打到空槽、取回全 0；随后 UI 才切到服务端恢复的真正会话
   → 刷新后用量显示 0。服务端数据本身是好的，问题只在取值时机。 */
void loadUsageAccumulator();
initTodoListElements();
startGlobalSse();
void restoreConversationLayoutFromServer().then(function(){
  /* 会话恢复后 `activeConversationId` 才是真正的当前会话 —— 此刻重取一次，覆盖空槽结果 */
  void loadUsageAccumulator();
  /* 同理：会话级模型也要等会话定下来再取（否则取到的是默认会话的模型） */
  void loadConversationModel();
});
void loadHealthModel();
if(typeof renderChatTabs==="function")renderChatTabs();
_updateUsageBottom();
autoResizeTextarea();

window.testScrollFollow=function(n){
if(!steps){if(window.DEBUG)console.warn("steps 容器未找到");return;}
n=n||25;
if(window.DEBUG)console.log("===== 滚动跟随测试开始: 插入"+n+"个步骤卡片 =====");
var seq=steps.querySelectorAll(".step.card").length+1;
for(var i=0;i<n;i++){
(function(idx){
setTimeout(function(){
var c=document.createElement("div");c.className="step card open";
var h=document.createElement("div");h.className="ch";
var t=document.createElement("span");t.className="tit";
t.textContent="测试步骤 "+(seq+idx)+"：验证滚动跟随 #"+(idx+1);
h.appendChild(t);
var body=document.createElement("div");body.className="card-body";
var inner=document.createElement("div");inner.className="card-body-inner";
var pre=document.createElement("pre");
var _long="";for(var _j=0;_j<40;_j++){_long+="  这是填充行 #"+_j+" 用来撑高卡片，让滚动条出现。步骤 "+(seq+idx)+"\n";}pre.textContent=_long;
inner.appendChild(pre);body.appendChild(inner);c.appendChild(h);c.appendChild(body);
appendStep(c);
if(idx===n-1){if(window.DEBUG)console.log("===== 测试结束 =====");}
},(idx+1)*300);
})(i);
}
};
if(typeof themeUi!=="undefined"){
themeUi.apply();
var _ht=document.getElementById("hdrThemeBtn");
if(_ht)_ht.addEventListener("click",function(){
themeUi.toggle();
/* 段色在渲染时从主题令牌取，所以切主题要重画一次上下文条。 */
if(typeof _updateUsageBottom==="function")_updateUsageBottom();
});
}
