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
window.aiAgentPlugins={for:pluginApi};

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
load:function(relPath, owner){
var plugin=String(owner||window.aiAgentPluginCurrent||"").trim();
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
s.onerror=function(){delete _pluginScriptsLoaded[u];resolve(false);};
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
l.onerror=function(){delete _pluginStylesLoaded[u];resolve(false);};
document.head.appendChild(l);
});
}
/* 已装载插件名单：catalog 刷新与卸载清理共用同一份状态。 */
var loadedPlugins=null;
function rememberLoadedPlugins(names){
if(!Array.isArray(names))return;
var set={};
for(var i=0;i<names.length;i++){
var name=String(names[i]||"").trim();
if(name)set[name]=true;
}
loadedPlugins=set;
window.__dshLoadedPlugins=names.slice();
}
function loadLoadedPlugins(){
return fetch("/api/plugins/loaded").then(function(r){return r.json();}).then(function(d){
var names=(d&&Array.isArray(d.loaded))?d.loaded:[];
rememberLoadedPlugins(names);
return names;
}).catch(function(){return [];});
}
function panePluginName(id){
var pane=document.getElementById("pane-"+id);
var marked=pane&&pane.getAttribute("data-plugin");
if(marked)return marked;
var tab=document.getElementById("tab-"+id);
return tab&&tab.getAttribute("data-plugin")?tab.getAttribute("data-plugin"):"";
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
   脚本加载闸门会认为"已经加载过"，脚本不再跑，挂载点也就空着。
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
void loadLoadedPlugins();
if(typeof _updateUsageBottom==="function")_updateUsageBottom();
}
