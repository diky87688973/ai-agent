/* composer/pickers.js —— @ 文件选择器、模式菜单、推理档位。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 *
 * 模型下拉不在这里：它由 `multi_model` 插件渲染到 `#modelPickerSlot`，
 * 壳层只提供 `window.aiAgentShell.models` 桥与 `applyModel()`。
 */
/* ---- @ 文件选择器 ---- */
var atSelectedIndex=-1;var atRestoreSelectPath=null;function atNormPath(s){return String(s||"").replace(/\\/g,"/").toLowerCase();}function getAtPop(){return document.getElementById("atPop");}function getAtList(){return document.getElementById("atList");}function getAtCurPath(){return document.getElementById("atCurPath");}function getAtUpBtn(){return document.getElementById("atUpBtn");}
function hideAtPop(){if(window.DEBUG)console.log("hideAtPop");var p=getAtPop();if(p){p.style.visibility="hidden";p.style.top="-99999px";p.setAttribute("aria-hidden","true");}atSelectedIndex=-1;atRestoreSelectPath=null;}
function atMentionActiveAtCursor(){var v=ta.value,sel=ta.selectionStart||0,before=v.slice(0,sel);var re=/(?:^|\s)@/g,m,last=null;while((m=re.exec(before))!==null)last=m;if(!last)return false;var atIdx=last.index+last[0].length-1;if(sel<=atIdx)return false;var seg=before.slice(atIdx+1,sel);if(/\s/.test(seg))return false;return true;}
function atLastTriggerIndexIn(t){var re=/(?:^|\s)@/g,m,last=-1;while((m=re.exec(t))!==null)last=m.index+m[0].length-1;return last;}
var ICON_MAP={txt:"📄",json:"📋",py:"🐍",java:"☕",html:"🌐",js:"📜",css:"🎨",xml:"📰",yml:"⚙️",yaml:"⚙️",properties:"🔧",sql:"🗄️",md:"📝",jpg:"🖼️",jpeg:"🖼️",png:"🖼️",gif:"🖼️",svg:"🖼️",bmp:"🖼️",xlsx:"📊",xls:"📊",docx:"📃",doc:"📃",pdf:"📕",pptx:"📽️",ppt:"📽️",zip:"📦",rar:"📦",exe:"⚙️",dll:"⚙️",log:"📋",csv:"📊",ts:"📜",tsx:"📜",jsx:"📜",vue:"📜",c:"📄",cpp:"📄",h:"📄",go:"📄",rs:"📄",kt:"📄",swift:"📄"};
function iconFor(ext){return ICON_MAP[ext]||"📄";}
async function loadAtDir(path){try{var resp=await fetch("/api/dir-browse?path="+encodeURIComponent(path||""));var data=await resp.json();renderAtList(data);}catch(e){atRestoreSelectPath=null;getAtList().innerHTML='<div class="at-item" style="color:#f66">加载失败: '+e.message+"</div>";}}
function renderAtList(data){bindAtListDelegation();getAtCurPath().textContent=data.current;getAtCurPath().dataset.parent=data.parent||"";getAtUpBtn().style.display=(!data.parent||data.parent===data.current)?"none":"";getAtList().innerHTML="";atSelectedIndex=-1;data.items.forEach(function(item,idx){var div=document.createElement("div");div.className="at-item"+(item.type==="dir"?" dir":"");div.id="atPop_item_"+idx;div.dataset.idx=idx;div.dataset.type=item.type;div.dataset.path=item.path;if(item.type==="dir")div.title="单击进入子目录；回车插入该目录路径";var icon=item.type==="dir"?"📁":iconFor(item.ext.replace(".",""));div.innerHTML='<span class="at-icon">'+icon+'</span><span class="at-name">'+item.name+"</span>";div.addEventListener("mouseenter",function(){atSelectedIndex=idx;updateAtSelection();});getAtList().appendChild(div);});var pick=0;if(atRestoreSelectPath){var want=atRestoreSelectPath;atRestoreSelectPath=null;for(var rj=0;rj<data.items.length;rj++){if(data.items[rj].type==="dir"&&atNormPath(data.items[rj].path)===atNormPath(want)){pick=rj;break;}}}if(data.items&&data.items.length){atSelectedIndex=pick;updateAtSelection();}}
function bindAtListDelegation(){
var list=getAtList();
if(!list||list._atClickDelegated)return;
list._atClickDelegated=true;
list.addEventListener("click",function(ev){
var item=ev.target&&ev.target.closest?ev.target.closest(".at-item"):null;
if(!item||!list.contains(item))return;
var path=String(item.dataset.path||"");
if(!path)return;
if(item.dataset.type==="dir")loadAtDir(path);
else selectAtFile(path);
});
}
function updateAtSelection(){var items=getAtList().querySelectorAll(".at-item");items.forEach(function(it,idx){it.classList.toggle("selected",idx===atSelectedIndex);});}
function selectAtFile(fpath){var before=ta.value.slice(0,ta.selectionStart||0);var after=ta.value.slice(ta.selectionStart||0);var atIdx=atLastTriggerIndexIn(before);if(atIdx>=0){ta.value=before.slice(0,atIdx)+"@"+fpath+" "+after;}else{ta.value=before+"@"+fpath+" "+after;}hideAtPop();ta.focus();}
if(getAtUpBtn())getAtUpBtn().addEventListener("click",function(){var cur=getAtCurPath().textContent.trim();var parentStored=getAtCurPath().dataset.parent||"";if(!parentStored)return;var p=parentStored||cur.substring(0,cur.lastIndexOf("/"));if(!p||p.length<3){if(p&&p.length===2&&p.charAt(1)===":"){p=p+"/";}else{p=cur;}}if(p!==cur)atRestoreSelectPath=cur;loadAtDir(p);});
function showAtPop(){if(window.DEBUG)console.log("showAtPop");var p=getAtPop();if(!p)return;atSelectedIndex=-1;atRestoreSelectPath=null;loadAtDir("");p.style.visibility="visible";p.style.top="-306px";p.setAttribute("aria-hidden","false");}
/* ---- @ 文件选择器结束 ---- */
function hideSlashPop(){if(slashPop){slashPop.classList.add("hidden");slashPop.setAttribute("aria-hidden","true");}}
function positionSlashPop(){if(!ta||!slashPop)return;var rect=ta.getBoundingClientRect();var before=ta.value.slice(0,ta.selectionStart||0);var lineStart=before.lastIndexOf("\n")+1;var col=before.length-lineStart;var cs=getComputedStyle(ta);var fz=parseFloat(cs.fontSize)||13;var lh=parseFloat(cs.lineHeight);if(!isFinite(lh)||lh<=0)lh=fz*1.35;var padL=parseFloat(cs.paddingLeft)||4;var padT=parseFloat(cs.paddingTop)||2;var chW=fz*0.55*Math.max(col,0);var lines=(before.match(/\n/g)||[]).length;var x=rect.left+padL+chW+6;var y=rect.top+padT+lines*lh-slashPop.offsetHeight-6;if(y<8)y=rect.bottom+4;var maxx=window.innerWidth-slashPop.offsetWidth-8;x=Math.min(Math.max(8,x),maxx);slashPop.style.position="fixed";slashPop.style.left=x+"px";slashPop.style.top=y+"px";}
function autoResizeTextarea(){if(!ta)return;ta.style.height="auto";var maxH=parseInt(getComputedStyle(ta).maxHeight)||320;var newH=Math.min(ta.scrollHeight,maxH);ta.style.height=newH+"px";ta.style.overflowY=ta.scrollHeight>maxH?"auto":"hidden";}
function normalizeMode(v){const t=String(v||"auto").toLowerCase();return (t==="plan"||t==="execute"||t==="auto")?t:"auto";}
function applyMode(v,persist){hideSlashPop();selectedMode=normalizeMode(v);const label=(selectedMode==="auto"?"Auto":(selectedMode==="plan"?"Plan":"Execute"));if(modePlus){modePlus.textContent=label+" +";modePlus.classList.remove("plan","execute");if(selectedMode==="plan")modePlus.classList.add("plan");if(selectedMode==="execute")modePlus.classList.add("execute");}if(modeChip){modeChip.classList.add("hidden");}if(modeChipText){modeChipText.textContent="";}/* 模式属于会话：用户点击才回写，服务端回填 / SSE / 标签页切换都不写。
   否则开屏时 applyMode("auto") 会先把服务端刚恢复的 plan 覆盖掉。 */
if(persist!==false){var cid=activeConversationId;if(cid){fetch("/api/chat/ui-state",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:cid,mode:selectedMode})}).catch(function(){});}}}
function closeModeMenu(){modeMenu.classList.add("hidden");}
let reasoningEffort="max";let reasoningBtn=document.getElementById("reasoningBtn");let reasoningMenu=document.getElementById("reasoningMenu");let reasoningLabel=document.getElementById("reasoningLabel");
function applyReasoningEffort(effort,persist){if(effort!=="high"&&effort!=="max")return;reasoningEffort=effort;if(reasoningLabel){reasoningLabel.textContent=effort==="high"?"High":"Max";/* 颜色走类名，不写死值：写死的是深色主题的那一套，切到白天模式
   就会变成"暗金文字压在浅底上"（对比度极差）。
   `effort-max` 只是给 CSS 一个钩子，两套主题各自决定怎么画。 */
reasoningLabel.style.color="";
reasoningBtn.style.borderColor="";
reasoningBtn.classList.toggle("effort-max",effort==="max");
reasoningBtn.classList.toggle("effort-high",effort!=="max");}if(reasoningMenu){var cs=reasoningMenu.querySelectorAll(".reasoning-choice");cs.forEach(function(c){c.classList.remove("reasoning-current");if(c.dataset.effort===effort)c.classList.add("reasoning-current");});}
/* 只有用户点击才回写；服务端回填（同一次回填里已经在显示它）再写一次
   只是多余的 PUT，还会在会话切换的竞态里把旧值盖回去。 */
if(persist!==false){var cid=activeConversationId;if(cid){fetch("/api/reasoning-effort",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:cid,effort:effort})}).catch(function(){});}}}
function closeReasoningMenu(){if(reasoningMenu)reasoningMenu.classList.add("hidden");}
function initReasoningPicker(){if(!reasoningBtn||!reasoningMenu)return;
reasoningBtn.onclick=function(e){e.stopPropagation();closeModeMenu();reasoningMenu.classList.toggle("hidden");};
reasoningMenu.onclick=function(e){var t=e.target;if(!t||typeof t.closest!=="function")return;var btn=t.closest("[data-effort]");if(!btn||!btn.dataset)return;if(btn.dataset.effort){applyReasoningEffort(btn.dataset.effort);closeReasoningMenu();}};
document.addEventListener("click",function(e){if(reasoningMenu&&!reasoningMenu.classList.contains("hidden")&&!reasoningBtn.contains(e.target)&&!reasoningMenu.contains(e.target))closeReasoningMenu();});
/* 档位初值不在这里取：它属于会话，得等会话恢复后按 cid 一起取
   （`loadConversationModel` / `syncConversationSettings`），
   在这里按 `activeConversationId` 取会拿到还没定下来的那个会话。 */
}

function initModePicker(){
if(!modePlus||!modeMenu||!modeChip||!modeChipClear)return;
modePlus.onclick=function(e){e.stopPropagation();closeReasoningMenu();modeMenu.classList.toggle("hidden");};
modeMenu.onclick=function(e){
var t=e.target;if(!t||typeof t.closest!=="function")return;
var btn=t.closest("[data-mode],[data-action]");
if(!btn||!btn.dataset)return;
if(btn.dataset.mode){applyMode(btn.dataset.mode);closeModeMenu();return;}

};
modeChipClear.onclick=function(e){e.stopPropagation();applyMode("auto");};
document.addEventListener("click",function(e){
if(!modeMenu.contains(e.target)&&e.target!==modePlus)closeModeMenu();
if(slashPop&&!slashPop.classList.contains("hidden")&&!slashPop.contains(e.target)&&e.target!==ta)hideSlashPop();
});
/* 开屏先显示默认值；此时 `activeConversationId` 可能还没恢复，绝不能回写。 */
applyMode("auto",false);
}
/* 模型显示的唯一写入点：当前标签页字段 + 页头 + 壳层订阅者。
   用户点击的校验在 `aiAgentShell.models.select()`；服务端下发的值（回填 / SSE）
   不受本地清单限制 —— 清单可能比页面新。
   `force`：切标签页时全局值已被 `loadRuntimeStateFromTab` 先写好，
   这时"值没变"也是错的显示（模型按钮由插件订阅刷新），必须照发一次。 */
function applyModel(m,force){
var x=String(m||"").trim();
var changed=x!==selectedModel;
selectedModel=x;
var tab=(typeof getActiveTab==="function")?getActiveTab():null;
if(tab)tab.selectedModel=x;
var hm=document.getElementById("hdrModel");
if(hm)hm.textContent=x?("模型: "+x):"模型加载中…";
if((changed||force===true)&&typeof notifyModelSubscribers==="function")notifyModelSubscribers(x);
}
bindAtListDelegation();
