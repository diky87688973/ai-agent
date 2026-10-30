/* render/paths.js —— 路径与文本工具：转义、高亮、Windows 路径归一、链接化、HTML 白名单清洗。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
function localAbsPath(p){
var s=String(p||"").trim().replace(/\\/g,"/");
s=s.replace(/^file:\/+/i,"");
return /^[a-zA-Z]:\//.test(s)?s:"";
}
function workspaceRelPath(p){
var s=localAbsPath(p);
if(!s)return "";
var m=s.match(/^(?:.*\/)?workspace\/(.+)$/i);
return m?m[1]:"";
}
function markedImageHref(href){
var raw=String(href||"");
var rel=workspaceRelPath(raw);
if(rel)return "/workspace/"+rel;
var abs=localAbsPath(raw);
if(abs)return "/api/media?path="+encodeURIComponent(abs);
return raw;
}
function markedIsVideo(url){
return /\.(mp4|mov|webm|avi)(\?|$)/i.test(String(url||""));
}
/* 音频/视频扩展名。这类本地路径当链接给出时（如 `[播放音频](D:\...\a.mp3)`），
   也要转成 `/api/media`，否则点开是死链。
   只认媒体扩展名：文本文件（.md/.py 等）的本地路径链接另有文件查看路由，
   不能在这里一并改掉。 */
function markedIsMediaFile(url){
return /\.(mp4|mov|webm|avi|mp3|wav|m4a|aac|flac|ogg|png|jpe?g|gif|webp|bmp)(\?|$)/i.test(String(url||""));
}
/* 正文里的 `@<绝对路径>` → 可点击引用，点了在右栏打开该文件。
   这是展示层的事：composer 里插入的仍是 `@<路径>` 纯文本（模型认这个格式），
   这里只把它渲染成一个 chip。 */
/* 正文里的本地文件链接：盘符路径进右栏，外链与站内地址留给浏览器。 */
function filePathFromHref(href){
var s=String(href||"").trim();
if(!s||/^(?:https?:|mailto:|#|\/)/i.test(s))return "";
s=s.replace(/^file:\/+/i,"");
try{s=decodeURIComponent(s);}catch(e){}
if(/^[A-Za-z]:[\\/]/.test(s))return s;
return "";
}
function filePaneId(path){
/* 用路径哈希做面板 id：文件名可能含中文/空格/超长，直接进 id 会有麻烦 */
var s=String(path||"").replace(/\\/g,"/").toLowerCase();
var h=0;
for(var i=0;i<s.length;i++){h=(h*31+s.charCodeAt(i))|0;}
return "file-"+Math.abs(h).toString(36)+"-"+s.length.toString(36);
}
function shortFilePath(path){
var s=String(path||"").replace(/\\/g,"/");
var parts=s.split("/").filter(Boolean);
return parts.length<=2?s:(parts[parts.length-2]+"/"+parts[parts.length-1]);
}
/* 识别「文件路径」写法。模型经常把路径写成行内代码（`` `E:\test.txt` ``），
   那种没有 `@` 前缀，靠 atFileExtension 认不出来。

   判据要严：`agent/mechanisms/quality_gate.py` 这类相对路径也可能是行内代码里的
   代码引用，一律变成 chip 会把正文里的普通代码引用也点成文件面板。
   所以只认盘符开头的绝对路径（`E:\…` / `E:/…`），且必须带扩展名。 */
var _WIN_PATH_RE=/^@?([A-Za-z]:[\\/][^\s`<>"|?*]*\.[A-Za-z0-9]{1,8})$/;
function absoluteFilePathOf(s){
var t=String(s||"").trim();
var m=_WIN_PATH_RE.exec(t);
return m?m[1]:"";
}
function fileRefHtml(path,keepAt){
var p=String(path||"");
var label=(keepAt?"@":"")+shortFilePath(p);
return '<a class="file-ref" data-file-path="'+escapeHtml(p)+'" title="'+escapeHtml(p)+'">'+escapeHtml(label)+"</a>";
}
var _atFileExt=null;
/* 用户输入里的 `@<路径>` 也要能点开。
   用户消息走 `textContent`（纯文本，不过 markdown），所以这里做一次只认文件引用的
   轻量转换：先把整段转义，再把 `@<盘符路径>` 换成 chip。
   不整段跑 markdown —— 用户输入里的 `*`、`_`、`#` 是字面内容，不该被解释。 */
function linkifyUserText(s){
var t=String(s==null?"":s);
var esc=escapeHtml(t);
return esc.replace(/@([A-Za-z]:[\\/][^\s`<>"|?*]+)/g,function(_all,p){
return fileRefHtml(p,true);
});
}
function atFileExtension(){
if(_atFileExt)return _atFileExt;
_atFileExt={
name:"atFileRef",
level:"inline",
/* 只认 `@` 后紧跟盘符路径（`E:/x` `E:\x`）：相对路径与邮箱（`a@b.com`）都不碰。
   `start` 把解析位置前移到 `@`，否则 marked 会先把 `@` 当普通文本吃掉。 */
start:function(src){
var m=/(^|\s)@[A-Za-z]:[\\/]/.exec(src);
if(!m)return undefined;
return m.index+(m[1]?m[1].length:0);
},
tokenizer:function(src){
var m=/^@([A-Za-z]:[\\/][^\s`<>"|?*]+)/.exec(src);
if(!m)return undefined;
return {type:"atFileRef",raw:m[0],path:m[1],tokens:[]};
},
renderer:function(token){
var p=String(token.path||"");
return fileRefHtml(p,true);
}
};
return _atFileExt;
}
/* 行内代码里的绝对路径也变成可点 chip。
   `marked.use({renderer})` 收的是对象（键为渲染方法名），不是函数 ——
   传函数会静默什么都不注册。返回 `false` 时回落默认渲染。 */
var _codespanExt=null;
function filePathCodespanExtension(){
if(_codespanExt)return _codespanExt;
_codespanExt={
codespan:function(token){
var p=absoluteFilePathOf(token&&token.text);
if(!p)return false;
return fileRefHtml(p,/^@/.test(String(token.text||"").trim()));
}
};
return _codespanExt;
}
/* markdown 输出的消毒。
   解析器对原始 HTML 直通，而且它的 `html:false` 选项不生效（三种配置都直通），
   所以防线只能做在渲染之后。

   做法是元素级白名单，不是字符串黑名单：逐个标签过，白名单外的标签转义成文本。
   黑名单挡不住 `<ScRiPt>`、`<script/x>`、`<svg/onload=…>` 这类变体 —— 漏一个就是执行。
   白名单只收渲染器自己会产出的标签（含 `markedRenderer` 产出的 `<video>`），
   正文里的原始 HTML 全被转义，想放新标签必须显式加进来。 */
var _SAFE_TAGS={
a:1,p:1,br:1,hr:1,em:1,strong:1,del:1,s:1,code:1,pre:1,blockquote:1,
ul:1,ol:1,li:1,table:1,thead:1,tbody:1,tr:1,th:1,td:1,
h1:1,h2:1,h3:1,h4:1,h5:1,h6:1,img:1,video:1,source:1,span:1,input:1
};
/*: 这些属性名一出现就拆掉（`on*` 之外的危险项） */
/*: 白名单内的属性名（原样保留）。任务清单的复选框要 `type`/`checked`/`disabled`。 */
var _SAFE_ATTR_EXACT={href:1,src:1,alt:1,title:1,class:1,id:1,colspan:1,rowspan:1,
type:1,checked:1,disabled:1,value:1,name:1,width:1,height:1,controls:1,loop:1,muted:1,poster:1,preload:1};
var _SAFE_ATTR_PREFIX=["data-","aria-"];
var _UNSAFE_HREF=/^\s*(?:javascript|vbscript|data|file)\s*:/i;
/*: 属性名以 `on` 开头即事件处理器 */
var _EVENT_ATTR=/^on/i;

function _safeUrlValue(raw){
var v=String(raw==null?"":raw);
/* 实体写法绕行（`java&#115;cript:`）：去掉实体与控制字符后再判 */
var plain=v.replace(/&#x?[0-9a-f]+;?/gi,"").replace(/[\s\u0000-\u0020]/g,"");
return !_UNSAFE_HREF.test(plain);
}
function _cleanTagAttrs(attrs){
var out=[];
/* 先归一化空白：解析器会把属性拆到多行（`<input checked=""\n  type="checkbox">`），
   带换行的属性串会让下面的逐属性识别漏掉它们。 */
var flat=String(attrs||"").replace(/\s+/g," ");
/* 值可以是空串（`checked=""`）—— 用 `*` 而不是 `+`，否则空值配不上、
   引号被当成裸值，后面整串属性跟着错位。 */
flat.replace(/([a-zA-Z_:][-a-zA-Z0-9_:.]*)\s*(?:=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g,
function(all,name,dq,sq,bare){
var lower=String(name||"").toLowerCase();
if(!lower)return "";
var allowed=_SAFE_ATTR_EXACT[lower]===1;
if(!allowed){
for(var i=0;i<_SAFE_ATTR_PREFIX.length;i++){if(lower.indexOf(_SAFE_ATTR_PREFIX[i])===0){allowed=true;break;}}
}
if(!allowed)return "";
if(_EVENT_ATTR.test(lower))return "";
var value=dq!=null?dq:(sq!=null?sq:(bare!=null?bare:""));
if(lower==="href"||lower==="src"){
if(!_safeUrlValue(value))return "";
}
if(value===""){out.push(lower);return "";}
out.push(lower+'="'+escapeHtml(value)+'"');
return "";
});
return out.length?(" "+out.join(" ")):"";
}
function sanitizeRenderedHtml(html){
var src=String(html==null?"":html);
var out="";
var i=0;
while(i<src.length){
var lt=src.indexOf("<",i);
if(lt<0){out+=src.slice(i);break;}
out+=src.slice(i,lt);
if(src.slice(lt,lt+4)==="<!--"){
var end=src.indexOf("-->",lt+4);
i=end<0?src.length:end+3;
continue;
}
var m=/^<\s*(\/?)\s*([a-zA-Z][a-zA-Z0-9-]*)((?:[^>"']|"[^"]*"|'[^']*')*)>/.exec(src.slice(lt));
if(!m||m[0].indexOf("\n")>=0){
/* 不是完整标签（正文里的裸 `<`）：转义它，后面的内容继续扫。
   标签必须同行闭合 —— 跨行匹配会把正文里的 `<` 一路吃到后面的 `>`，
   把本该显示的文本当成标签吞掉。 */
out+="&lt;";i=lt+1;continue;
}
var closing=m[1]==="/";
var rawName=m[2];
var name=rawName.toLowerCase();
if(_SAFE_TAGS[name]!==1){
/* 白名单外：整段转义成文本，不留在 DOM 里 */
out+=escapeHtml(m[0]);
i=lt+m[0].length;
continue;
}
if(closing){
out+="</"+name+">";
}else{
var selfClose=/\/\s*$/.test(m[3]||"");
out+="<"+name+_cleanTagAttrs(m[3]||"")+(selfClose?" /":"")+">";
}
i=lt+m[0].length;
}
return out;
}
/* markdown 解析器实例。
   在 `parse` 选项里再传 `renderer` 会整体替换渲染器链，
   把 `use()` 注册的渲染方法覆盖（`codespan` 那类）整个丢掉。
   所以所有渲染定制都在 `mdParser()` 里经 `use()` 装好，parse 只传解析选项。
   注入防线在 `sanitizeRenderedHtml`（解析器的 `html:false` 不起作用，见上）。 */
