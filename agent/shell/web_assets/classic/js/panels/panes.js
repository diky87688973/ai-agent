/* panels/panes.js —— 右栏通用面板容器：标签、面板创建/关闭、显隐同步。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
function selectSidePane(name){
document.querySelectorAll(".side-tab").forEach(function(el){el.classList.toggle("active",el.dataset.pane===name);});
document.querySelectorAll(".side-pane").forEach(function(el){el.classList.toggle("active",el.dataset.pane===name);});
}
/* 通用面板容器：标签与面板都由 `data-pane` 驱动，新增面板不必改这里。
   插件注入的面板同样只有 `data-pane` 这一条身份线索，所以遍历必须按数据走；
   按名字写死会让插件面板永远打不开。

   `opts.pinned` 的面板不显示关闭按钮（步骤栏就是这种）。
   `opts.onOpen` 在每次激活时调用，供面板刷新自己的内容。 */
function bindSideTabDelegation(){
if(!sideTabbar||sideTabbar._paneClickDelegated)return;
sideTabbar._paneClickDelegated=true;
sideTabbar.addEventListener("click",function(ev){
var target=ev.target;
var tab=target&&target.closest?target.closest(".side-tab"):null;
if(!tab||!sideTabbar.contains(tab))return;
var id=String(tab.getAttribute("data-pane")||"");
if(!id)return;
if(target.closest(".tab-x")){closePane(id);return;}
selectSidePane(id);
});
}
function openPane(opts){
var id=String(opts&&opts.id||"").trim();
if(!id||!sideTabbar||!sidePaneWrap)return null;
bindSideTabDelegation();
var title=String(opts.title||id);
var ex=document.getElementById("pane-"+id);
if(!ex){
ex=document.createElement("div");
ex.className="side-pane";
ex.id="pane-"+id;
ex.dataset.pane=id;
ex.dataset.plugin=String((opts&&opts.plugin)||"");
/* `openPane` 建的面板不建标题行：标题已经在标签上（同一个 `title`），再写一行是重复。
   固定面板（步骤栏）不同 —— 它不参与开/关，自带标题行是有意的。
   正文容器始终建：面板可以只给 `onOpen` 自己填内容（文件查看器就是这样），
   只在传了 `html` 时才建会让 `onOpen` 找不到容器、静默什么都不渲染。 */
var bodyEl=document.createElement("div");
bodyEl.className="pane-body";
if(opts.html!=null)bodyEl.innerHTML=String(opts.html);
ex.appendChild(bodyEl);
sidePaneWrap.appendChild(ex);
}
if(!document.getElementById("tab-"+id)){
var w=document.createElement("button");
w.type="button";
w.className="side-tab";
w.id="tab-"+id;
w.dataset.pane=id;
w.dataset.plugin=String((opts&&opts.plugin)||"");
w.setAttribute("role","tab");
w.tabIndex=0;
var sp=document.createElement("span");
sp.textContent=title;
sp.style.flex="1";
w.appendChild(sp);
if(!opts.pinned){
var x=document.createElement("button");
x.type="button";
x.className="tab-x";
x.textContent="×";
x.title="关闭";
w.appendChild(x);
}
sideTabbar.appendChild(w);
}
selectSidePane(id);
/* 广播"面板已打开"：插件脚本在开屏就被预载（段色注册要赶在第一次渲染前），
   那时面板 DOM 还不存在，脚本里的首次渲染必然是空跑。而脚本只载一次
   （`_pluginScriptsLoaded` 去重），开面板时不会再执行一遍 ——
   不广播这一下，面板就永远停在初始占位（"加载知识库…"）。
   插件自己监听这个事件决定渲染什么，壳层不点名任何插件。 */
try{
document.dispatchEvent(new CustomEvent("ai-agent:panel-opened",{detail:{
plugin:String((opts&&opts.plugin)||""),
/* DOM id（可能带 `插件__` 前缀）；逻辑面板 id 另给 panelId */
panel:id,
panelId:String((opts&&opts.panelId)||id)
}}));
}catch(e){}
if(typeof opts.onOpen==="function")opts.onOpen(ex);
syncClassicSide();
return ex;
}
/* 步骤开关关闭时，步骤标签藏在样式里，不占右栏。其余标签都算打开。 */
function countOpenSideTabs(){
var tabs=document.querySelectorAll("#sideTabbar .side-tab");
var n=0;
for(var i=0;i<tabs.length;i++){
if(tabs[i].id==="tabSteps"&&typeof showToolSteps==="function"&&!showToolSteps())continue;
n++;
}
return n;
}
function syncClassicSide(){
if(typeof window._setClassicSideOpen==="function")window._setClassicSideOpen(countOpenSideTabs()>0);
}
function closePane(id){
var t=document.getElementById("tab-"+id);
if(t)t.remove();
var p=document.getElementById("pane-"+id);
if(p)p.remove();
var tabs=document.querySelectorAll(".side-tab");
var next=null;
for(var i=0;i<tabs.length;i++){
if(!showToolSteps()&&tabs[i].id==="tabSteps")continue;
next=tabs[i];
break;
}
if(next)selectSidePane(next.dataset.pane);
else if(showToolSteps())selectSidePane("steps");
else selectSidePane("");
syncClassicSide();
}
/* 插件 API 客户端：面板脚本经它调自己插件的端点，不必知道 URL 前缀。
   插件改名、端点挪位置都不影响脚本 —— 前缀由壳层拼。

   用法（面板脚本里）：
     const api = window.aiAgentPlugins.for(window.aiAgentPluginCurrent);
     await api.get("files");
     await api.post("generate", { prompt: "..." });
     await api.put("checked", { conversation_id, checked });
     await api.del("tasks/t-1");
*/
