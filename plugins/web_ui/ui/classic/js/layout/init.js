/* 开屏初始化：模块加载完成后装配选择器、面板、SSE 与用量。 */
initModePicker();
initReasoningPicker();
initKbAndSlashUi();
initMarkedExtensions();
/* 面板清单与动作清单先取回（渲染各入口都按数据来）；
   面板脚本预载，赶在第一次画上下文条之前。 */
void loadLoadedPlugins().then(function(){
if(typeof _updateUsageBottom==="function")_updateUsageBottom();
});
void loadToolLabels();

var railNewEl=document.getElementById("sessionRailNew");
if(railNewEl)railNewEl.addEventListener("click",function(){createConversationTab();});
if(chatMoreBtn)chatMoreBtn.addEventListener("click",function(){void toggleSessionMenu();});
if(ta){ta.addEventListener("keydown",function(e){if(e.isComposing)return;var sh=slashPop&&!slashPop.classList.contains("hidden");var atp2=getAtPop();var ah=atp2&&atp2.style.visibility!=="hidden";var k=e.key,kl=k.toLowerCase(),ci=(slashPop&&slashPop.children)?slashPop.children:[];if(ah){if(k==="Escape"){e.preventDefault();hideAtPop();return;}if(k==="ArrowDown"||k==="ArrowUp"){e.preventDefault();var ai=getAtList().querySelectorAll(".at-item");var vi=[];for(var i2=0;i2<ai.length;i2++){if(ai[i2].style.display!=="none")vi.push(i2);}if(!vi.length)return;var idx=vi.indexOf(atSelectedIndex);if(idx<0)idx=(k==="ArrowDown"?0:vi.length-1);else if(k==="ArrowDown"){if(idx<vi.length-1)idx++;}else{if(idx>0)idx--;}atSelectedIndex=vi[idx];updateAtSelection();var row=ai[atSelectedIndex];if(row&&row.scrollIntoView)try{row.scrollIntoView({block:"nearest"});}catch(_){}return;}if(k==="ArrowRight"){e.preventDefault();var aiR=getAtList().querySelectorAll(".at-item");var pR=atSelectedIndex;if(pR<0||pR>=aiR.length)pR=0;if(aiR.length&&aiR[pR]&&aiR[pR].dataset.type==="dir")loadAtDir(aiR[pR].dataset.path);return;}if(k==="ArrowLeft"){e.preventDefault();var curL=getAtCurPath().textContent.trim();var parentStored=getAtCurPath().dataset.parent||"";if(!parentStored)return;var pU=parentStored||curL.substring(0,curL.lastIndexOf("/"));if(!pU||pU.length<3){if(pU&&pU.length===2&&pU.charAt(1)===":"){pU=pU+"/";}else{pU=curL;}}if(pU!==curL)atRestoreSelectPath=curL;loadAtDir(pU);return;}if(k==="Enter"||e.code==="Enter"||e.code==="NumpadEnter"){e.preventDefault();var ai2=getAtList().querySelectorAll(".at-item");var pick=atSelectedIndex;if(pick<0||pick>=ai2.length)pick=0;if(ai2.length&&ai2[pick]){var sel=ai2[pick];selectAtFile(sel.dataset.path);}return;}if(atMentionActiveAtCursor()){return;}hideSlashPop();hideAtPop();return;}if(!sh&&!ah){if(!e.shiftKey&&(e.key==="Enter"||e.code==="Enter"||e.code==="NumpadEnter")){e.preventDefault();var _sendBtn=document.querySelector('[data-ui-action="input.send"]');if(_sendBtn)_sendBtn.click();else void sendChatMessage();}return;}if(sh&&k==="Escape"){e.preventDefault();hideSlashPop();return;}if(sh&&(k==="ArrowDown"||k==="ArrowUp")){e.preventDefault();var vi3=[];for(var i3=0;i3<ci.length;i3++){if(ci[i3].style.display!=="none")vi3.push(i3);}if(!vi3.length)return;var idx3=vi3.indexOf(slashSelectedIndex);if(idx3<0)idx3=(k==="ArrowDown"?-1:0);else if(k==="ArrowDown"){if(idx3<vi3.length-1)idx3++;}else{if(idx3>0)idx3--;}var cur3=ci[slashSelectedIndex];if(cur3)cur3.classList.remove("selected");slashSelectedIndex=vi3[idx3];var nxt3=ci[slashSelectedIndex];if(nxt3)nxt3.classList.add("selected");updateSlashPopHints();return;}if(sh&&(k==="Enter"||e.code==="Enter"||e.code==="NumpadEnter")){e.preventDefault();var sel4=ci[slashSelectedIndex];if(sel4&&sel4.dataset&&sel4.dataset.slash){applyMode(sel4.dataset.slash);ta.value="";}else hideSlashPop();return;}if(kl==="a"||kl==="p"||kl==="e"){e.preventDefault();hideSlashPop();ta.value="";if(kl==="a")applyMode("auto");else if(kl==="p")applyMode("plan");else applyMode("execute");return;}hideSlashPop();});ta.addEventListener("blur",function(){if(slashPop&&!slashPop.classList.contains("hidden"))hideSlashPop();});ta.addEventListener("mouseup",function(){if(slashPop&&!slashPop.classList.contains("hidden"))hideSlashPop();});}
document.getElementById("tabSteps")?.addEventListener("click",function(){selectSidePane("steps");});
window.addEventListener("beforeunload",function(){try{saveActiveConversationView();storeConversationLayoutLocal();}catch(e){}});
/* 先恢复会话，再取用量。
   `loadUsageAccumulator()` 若排在 `restoreConversationLayoutFromServer()` 之前：
   `activeConversationId` 初始值来自本地（URL/sessionStorage），可能为空，
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
