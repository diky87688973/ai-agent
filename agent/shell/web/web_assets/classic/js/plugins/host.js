/* plugins/host.js —— 插件宿主：插件 API 客户端、脚本/样式加载、面板与动作清单、上下文段注册。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
function pluginApi(plugin){
var name=String(plugin||"");
function call(method,path,payload){
var rel=String(path||"").replace(/^\/+/,"");
var url="/api/plugin/"+encodeURIComponent(name)+"/"+rel;
var opts={method:method,headers:{}};
if(payload!==undefined){
opts.headers["Content-Type"]="application/json";
opts.body=JSON.stringify(payload);
}
return fetch(url,opts).then(function(r){
return r.json().catch(function(){return {ok:r.ok,status:r.status};})
.then(function(data){return {status:r.status,ok:r.ok&&data&&data.ok!==false,data:data};});
});
}
return {
plugin:name,
url:function(path){return "/api/plugin/"+encodeURIComponent(name)+"/"+String(path||"").replace(/^\/+/,"");},
get:function(path,params){
var q="";
if(params&&typeof params==="object"){
var parts=[];
for(var k in params){if(Object.prototype.hasOwnProperty.call(params,k)&&params[k]!=null)parts.push(encodeURIComponent(k)+"="+encodeURIComponent(params[k]));}
if(parts.length)q="?"+parts.join("&");
}
return call("GET",path+q);
},
post:function(path,payload){return call("POST",path,payload===undefined?{}:payload);},
put:function(path,payload){return call("PUT",path,payload===undefined?{}:payload);},
del:function(path){return call("DELETE",path);}
};
}
/* 上下文分层的插件钩子：插件注册自己那一段的颜色/段名，宿主只按 key 取用。 */
var ctxSegmentHooks={};
var _ctxSegColors={};
var _ctxSegColorCache={};
function registerCtxSegment(plugin,opts){
var name=String(plugin||"").replace(/^plugin:/,"");
if(!name)return;
ctxSegmentHooks[name]=Object.assign({},ctxSegmentHooks[name]||{},opts||{});
}
function ctxSegmentLabel(key){
var m=/^plugin:(.+)$/.exec(String(key||""));
var h=m?ctxSegmentHooks[m[1]]:null;
return h&&h.label?String(h.label):"";
}
window.aiAgentPlugins={for:pluginApi,ctxSegments:{register:registerCtxSegment}};

/* ── 壳层公共桥 ────────────────────────────────────────────────────────────
   `aiAgentShell` 与 `aiAgentPlugins` 平级：前者给插件用壳层能力
   （当前模型、切换模型、载入插件样式），后者给插件用插件自己的端点。
   桥本身不持有"当前模型"——多份状态必然分叉；`current()` 每次读活动标签页。 */
var _modelSubscribers=[];
function notifyModelSubscribers(model){
var id=String(model||"");
for(var i=0;i<_modelSubscribers.length;i++){
try{_modelSubscribers[i](id);}catch(_e){}
}
}
function pluginAssetUrl(plugin,relPath){
var pluginName=String(plugin||"").trim();
var raw=String(relPath||"").replace(/\\/g,"/").replace(/^\/+/,"").trim();
if(!pluginName||!raw)return "";
/* 不信任插件传进来的路径：绝对路径、盘符、协议、`..` 一律拒。
   服务端 `_asset` 还会在解析后比对插件目录（S2），这里是第一道闸。 */
if(/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(raw))return "";
var parts=raw.split("/");
for(var i=0;i<parts.length;i++){
if(!parts[i]||parts[i]==="."||parts[i]==="..")return "";
}
return "/api/plugin/"+encodeURIComponent(pluginName)+"/_asset/"+
parts.map(function(seg){return encodeURIComponent(seg);}).join("/");
}
window.aiAgentShell=window.aiAgentShell||{};
window.aiAgentShell.models={
/* → Promise<[{id,label,provider}]>：目录条目以 `/health` 的 id 清单为准；
   标签与厂商由插件自己的 `/catalog` 补充，壳层不认任何插件名。 */
list:function(){
return fetch("/health").then(function(r){return r.json();}).then(function(j){
var ids=(j&&Array.isArray(j.allowed_models))?j.allowed_models:[];
if(j&&j.model_labels)window.aiAgentShell.modelLabels=j.model_labels;
if(typeof setAllowedModels==="function")setAllowedModels(ids);
return ids.map(function(id){return {id:String(id),label:String(id),provider:""};});
}).catch(function(){
return (typeof allowedModels!=="undefined"?allowedModels:[]).map(function(id){
return {id:String(id),label:String(id),provider:""};
});
});
},
current:function(){
var tab=(typeof getActiveTab==="function")?getActiveTab():null;
if(tab&&typeof tab.selectedModel==="string")return tab.selectedModel;
return (typeof selectedModel!=="undefined")?String(selectedModel||""):"";
},
/* 本地点击 → 服务端 live_state + 广播。先乐观更新界面；写失败回滚并返回 false。
   服务端值不受本地清单限制：本函数只拦用户点击，不拦 SSE/回填。 */
select:function(id){
var want=String(id||"").trim();
if(!want)return Promise.resolve(false);
var before=window.aiAgentShell.models.current();
if(typeof applyModel==="function")applyModel(want);
var tab=(typeof getActiveTab==="function")?getActiveTab():null;
var cid=(tab&&tab.id)||(typeof getActiveConversationId==="function"?getActiveConversationId():"");
if(!cid)return Promise.resolve(true);
return fetch("/api/chat/ui-state",{
method:"PUT",headers:{"Content-Type":"application/json"},
body:JSON.stringify({conversation_id:cid,model:want})
}).then(function(r){
if(r&&r.ok)return true;
if(typeof applyModel==="function")applyModel(before);
return false;
}).catch(function(){
if(typeof applyModel==="function")applyModel(before);
return false;
});
},
onChange:function(fn){
if(typeof fn!=="function")return function(){};
_modelSubscribers.push(fn);
return function(){
for(var i=_modelSubscribers.length-1;i>=0;i--){
if(_modelSubscribers[i]===fn)_modelSubscribers.splice(i,1);
}
};
}
};
window.aiAgentShell.styles={
/* 插件开屏样式：`relPath` 是插件目录内相对路径（如 `ui/model-picker.css`）。
   插件不自己拼 URL、不碰 `document.head`；去重表与面板样式共用。 */
load:function(relPath){
var plugin=String(window.aiAgentPluginCurrent||"").trim();
var url=pluginAssetUrl(plugin,relPath);
if(!url)return Promise.resolve(false);
return loadPluginStyle(url,plugin);
}
};

/* 面板脚本只加载一次。脚本里读 `window.aiAgentPluginCurrent` 就知道自己属于哪个插件。 */
var _pluginScriptsLoaded={};
function loadPluginScript(url,plugin){
var u=String(url||"").trim();
if(!u||_pluginScriptsLoaded[u])return Promise.resolve(false);
_pluginScriptsLoaded[u]=true;
return new Promise(function(resolve){
var s=document.createElement("script");
s.src=u;
s.setAttribute("data-plugin-script",String(plugin||""));
/* 记下传入时的原样 URL：`src` 属性会被浏览器解析成绝对地址，
   卸载插件时按 `src` 删不到缓存表里的键，脚本就再也不会重新执行。 */
s.setAttribute("data-plugin-src",u);
s.onload=function(){resolve(true);};
s.onerror=function(){resolve(false);};
document.head.appendChild(s);
});
}
/* 面板样式表同样只注入一次，且在面板打开时才注入 ——
   插件的样式随面板按需注入：壳层公共样式表里没有它们，插件没打开时也不会被加载。 */
var _pluginStylesLoaded={};
function loadPluginStyle(url,plugin){
var u=String(url||"").trim();
if(!u||_pluginStylesLoaded[u])return Promise.resolve(false);
_pluginStylesLoaded[u]=true;
return new Promise(function(resolve){
var l=document.createElement("link");
l.rel="stylesheet";
l.href=u;
l.setAttribute("data-plugin-style",String(plugin||""));
l.setAttribute("data-plugin-src",u);
l.onload=function(){resolve(true);};
l.onerror=function(){resolve(false);};
document.head.appendChild(l);
});
}
/* 插件贡献的面板清单与动作清单（`/api/panels`、`/api/actions`）。
   页面只按数据建标签、面板与按钮，不为任何插件加分支 —— 加插件不必改前端。 */
var pluginPanels=[];
var pluginActions=[];
/* null：还没拿到已装载名单，上下文段按上次快照画。拿到之后只留名单里的插件段。 */
var loadedPlugins=null;
function pluginPanel(plugin,panelId){
var key=String(plugin||"")+":"+String(panelId||"");
for(var i=0;i<pluginPanels.length;i++){
var p=pluginPanels[i];
if(String(p.plugin)+":"+String(p.id)===key)return p;
}
return null;
}
/* 插件脚本在开屏就依次预载（面板内容 / 交互）；段色改由 `/api/ctx-segment-styles` 注册。
   面板样式仍旧按需（面板打开时才注入），内容渲染也仍在面板脚本里。
   开屏脚本（无面板也可）在面板脚本之后预载，见 `/api/boot-scripts`。 */
function preloadPluginScriptList(list){
list=Array.isArray(list)?list.slice():[];
function next(){
if(!list.length)return Promise.resolve(false);
var def=list.shift();
if(!def||!def.script)return next();
var owner=String(def.plugin||"");
/* 脚本读全局知道自己属于哪个插件，所以串行加载：并行会互相覆盖这个值。 */
window.aiAgentPluginCurrent=owner;
return loadPluginScript(def.script,owner).then(next);
}
return next();
}
function preloadPluginScripts(){
return preloadPluginScriptList(pluginPanels);
}
function preloadBootScripts(){
return fetch("/api/boot-scripts").then(function(r){return r.json();}).then(function(d){
return preloadPluginScriptList((d&&Array.isArray(d.scripts))?d.scripts:[]);
}).catch(function(){return false;});
}
/* 开屏拉取上下文段外观并注册，不必靠空面板脚本。 */
function loadCtxSegmentStyles(){
return fetch("/api/ctx-segment-styles").then(function(r){return r.json();}).then(function(d){
var list=(d&&Array.isArray(d.styles))?d.styles:[];
for(var i=0;i<list.length;i++){
var st=list[i]||{};
var name=String(st.plugin||"").trim();
if(!name)continue;
registerCtxSegment(name,{color:String(st.color||""),label:String(st.label||"")});
}
return list;
}).catch(function(){return [];});
}
function rememberLoadedPlugins(names){
if(!Array.isArray(names))return;
var set={};
for(var i=0;i<names.length;i++){
var name=String(names[i]||"").trim();
if(name)set[name]=true;
}
loadedPlugins=set;
}
function loadPluginPanels(){
return fetch("/api/panels").then(function(r){return r.json();}).then(function(d){
pluginPanels=(d&&Array.isArray(d.panels))?d.panels:[];
if(d&&Array.isArray(d.loaded))rememberLoadedPlugins(d.loaded);
return pluginPanels;
}).catch(function(){pluginPanels=[];return pluginPanels;});
}
/* 按插件声明的动作清单渲染输入区按钮：没有声明就没有按钮，
   插件入口由声明决定，页面里没有写死的入口。 */
function renderPluginActions(){
var host=document.getElementById("pluginActions");
if(!host)return;
if(!host._pluginActionDelegated){
host._pluginActionDelegated=true;
host.addEventListener("click",function(ev){
var btn=ev.target&&ev.target.closest?ev.target.closest("[data-plugin-action]"):null;
if(!btn||!host.contains(btn))return;
var plugin=String(btn.getAttribute("data-plugin")||"");
var action=String(btn.getAttribute("data-plugin-action")||"");
var panel=String(btn.getAttribute("data-panel")||"")||action;
if(plugin)openPluginPanel(plugin,panel);
});
}
host.innerHTML="";
for(var i=0;i<pluginActions.length;i++){
(function(act){
var b=document.createElement("button");
b.type="button";
b.className="mode-plus plugin-action";
b.setAttribute("data-plugin",String(act.plugin||""));
b.setAttribute("data-plugin-action",String(act.id||""));
b.setAttribute("data-panel",String(act.panel||act.id||""));
if(act.title)b.title=String(act.title);
b.textContent=String(act.label||act.id||"");
host.appendChild(b);
})(pluginActions[i]);
}
}
function panePluginName(id){
var pane=document.getElementById("pane-"+id);
var marked=pane&&pane.getAttribute("data-plugin");
if(marked)return marked;
var tab=document.getElementById("tab-"+id);
marked=tab&&tab.getAttribute("data-plugin");
if(marked)return marked;
for(var i=0;i<pluginPanels.length;i++){
if(String(pluginPanels[i].id)===String(id))return String(pluginPanels[i].plugin||"");
}
return "";
}
function closeUnloadedPluginPanes(){
if(!loadedPlugins)return;
var tabs=document.querySelectorAll("#sideTabbar .side-tab");
var ids=[];
for(var i=0;i<tabs.length;i++){
var id=tabs[i].dataset.pane||"";
if(!id||id==="steps")continue;
var name=panePluginName(id);
if(name&&!loadedPlugins[name])ids.push(id);
}
for(var j=0;j<ids.length;j++)closePane(ids[j]);
}
function prunePluginStyles(){
if(!loadedPlugins)return;
var links=document.querySelectorAll("link[data-plugin-style]");
for(var i=links.length-1;i>=0;i--){
var link=links[i];
var owner=String(link.getAttribute("data-plugin-style")||"");
if(owner&&loadedPlugins[owner])continue;
var src=String(link.getAttribute("data-plugin-src")||"");
try{link.parentNode.removeChild(link);}catch(_e){}
try{delete _pluginStylesLoaded[link.href];}catch(_e2){}
try{if(src)delete _pluginStylesLoaded[src];}catch(_e3){}
}
}
/* 插件停用后，它的开屏脚本必须能再次执行：
   `_pluginScriptsLoaded` 是一次性闸门，只卸 DOM 不销账的话，插件重新启用时
   `preloadBootScripts` 会认为"已经加载过"，脚本不再跑，挂载点也就空着。
   `prunePluginMounts` 清掉的是停用那一刻的残留；这里清的是"下次还愿不愿意跑"。 */
function prunePluginScripts(){
if(!loadedPlugins)return;
var nodes=document.querySelectorAll("script[data-plugin-script]");
for(var i=nodes.length-1;i>=0;i--){
var node=nodes[i];
var owner=String(node.getAttribute("data-plugin-script")||"");
if(owner&&loadedPlugins[owner])continue;
var src=String(node.getAttribute("data-plugin-src")||"");
try{delete _pluginScriptsLoaded[src];}catch(_e){}
try{if(node.parentNode)node.parentNode.removeChild(node);}catch(_e2){}
}
}
/* 插件停用后，它塞进通用挂载点的内容也必须消失：
   按钮还在、端点已经注销，点下去只会得到一个 404。挂载点不认插件名，
   只看子元素自己声明的 `data-plugin`。 */
function prunePluginMounts(){
if(!loadedPlugins)return;
var slots=document.querySelectorAll("#modelPickerSlot [data-plugin]");
for(var i=slots.length-1;i>=0;i--){
var owner=String(slots[i].getAttribute("data-plugin")||"");
if(owner&&!loadedPlugins[owner])slots[i].parentNode.removeChild(slots[i]);
}
}
/* 插件开关的广播：重画按钮，关掉卸下插件的面板。上下文条重画一次，画的时候跳过未装载的插件。 */
function applyPluginsChanged(ev){
rememberLoadedPlugins(ev&&ev.loaded);
try{document.dispatchEvent(new CustomEvent("ai-agent:plugins-changed",{detail:{loaded:(ev&&Array.isArray(ev.loaded))?ev.loaded.slice():[]}}));}catch(_e){}
prunePluginStyles();
prunePluginScripts();
prunePluginMounts();
closeUnloadedPluginPanes();
void loadPluginActions();
void loadCtxSegmentStyles();
void loadPluginPanels().then(function(){
return preloadPluginScripts().then(function(){return preloadBootScripts();});
});
if(typeof _updateUsageBottom==="function")_updateUsageBottom();
}
function loadPluginActions(){
return fetch("/api/actions").then(function(r){return r.json();}).then(function(d){
pluginActions=(d&&Array.isArray(d.actions))?d.actions:[];
renderPluginActions();
return pluginActions;
}).catch(function(){pluginActions=[];renderPluginActions();return pluginActions;});
}
/* 打开插件声明的面板：HTML 片段与标题都取自清单。
   DOM id 用 `插件名__面板id`，避免不同插件同名面板撞 id。 */
function openPluginPanel(plugin,panelId){
var def=pluginPanel(plugin,panelId);
var panelKey=String(panelId||"").trim();
var pluginKey=String(plugin||"").trim();
if(!panelKey)return null;
var id=pluginKey?pluginKey+"__"+panelKey:panelKey;
return openPane({
id:id,
title:(def&&def.title)||panelKey,
html:def?def.html:"",
pinned:!!(def&&def.pinned),
plugin:pluginKey,
panelId:panelKey,
onOpen:function(pane){
/* 面板脚本与样式按需加载各一次；`aiAgentPluginCurrent` 让脚本知道自己的插件名，
   从而用 `window.aiAgentPlugins.for(...)` 拿到带前缀的 API，不必自己拼 URL。
   面板内容的渲染全在插件脚本里 —— 壳层不认任何插件的面板 id。 */
window.aiAgentPluginCurrent=String(plugin||"");
if(def&&def.style)void loadPluginStyle(def.style,plugin);
if(def&&def.script)void loadPluginScript(def.script,plugin);
}
});
}
