/* panels/file-viewer.js —— 右栏文件查看器：按需建面板、表格/文本预览、大小格式化。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
/* 右栏文件查看器：按需建面板，同一个文件复用同一个面板。
   数据来自 `/api/fs/read`（内核早就为右栏准备好了）：`kind=text` 给 `content`/`lang`，
   `kind=table` 给 `sheets[{name,rows}]`，`kind=binary` 给 `message`。 */
/* 文件大小：按量级给 KB / MB / GB，字节数不再直接示人（`1921 字节` 读不出量级）。
   小于 1 KB 仍是字节。
   先四舍五入再定单位：反过来（先定单位再舍入）在边界上会给出 `1024 KB`
   —— 1023.999 KB 舍入成 1024 却没升到 MB。 */
function formatFileSize(n){
/* 一律 KB 起：文件面板是给人扫一眼量级的，混杂"字节"会让同一列里两种单位并存。
   小于 1 KB 的显示成小数 KB（`288 字节` → `0.3 KB`）。 */
var v=Number(n);
if(n==null||!isFinite(v)||v<0)return"";
var units=["KB","MB","GB","TB"];
var i=-1;
do{v/=1024;i++;}while(v>=1023.95&&i<units.length-1);
return (v>=100?Math.round(v):Math.round(v*10)/10)+" "+units[i];
}
function renderTableSheets(sheets){
var out="";
for(var i=0;i<sheets.length;i++){
var sh=sheets[i]||{};
var rows=Array.isArray(sh.rows)?sh.rows:[];
out+='<div class="pane-sheet"><div class="pane-sheet-name">'+escapeHtml(String(sh.name||("Sheet"+(i+1))))+"</div>";
out+='<table class="pane-sheet-tb">';
for(var r=0;r<rows.length;r++){
var cells=Array.isArray(rows[r])?rows[r]:[];
var tag=(r===0&&rows.length>1)?"th":"td";
out+="<tr>";
for(var c=0;c<cells.length;c++)out+="<"+tag+">"+escapeHtml(String(cells[c]))+"</"+tag+">";
out+="</tr>";
}
out+="</table></div>";
}
return out||'<div class="pane-empty">（空表）</div>';
}
function renderFilePane(body,path){
/* 文件查看器的内容自带边距：面板容器不给内边距（边距归内容），
   所以这里给自己打个类让样式表能定位到。 */
if(body)body.className="pane-body pane-file";
body.innerHTML='<div class="pane-empty">读取中…</div>';
fetch("/api/fs/read?path="+encodeURIComponent(path)).then(function(r){return r.json();}).then(function(d){
if(!d||d.error){
body.innerHTML='<div class="pane-empty">打开失败：'+escapeHtml(String((d&&d.error)||"未知错误"))+"</div>";
return;
}
/* 元信息行只放属性（大小 / 截断 / 刷新），不再放路径 ——
   路径在面板标题里，同一句话写两遍是冗余。 */
var meta='<div class="pane-meta">';
if(d.size!=null){var _sz=formatFileSize(d.size);if(_sz)meta+="<span>"+_sz+"</span>";}
if(d.truncated)meta+="<span>已截断</span>";
meta+='<button type="button" class="pane-btn" data-pane-refresh>刷新</button></div>';
var kind=String(d.kind||"text");
var inner;
if(kind==="binary"){
inner='<div class="pane-empty">'+escapeHtml(String(d.message||"二进制文件不在此处预览"))+"</div>";
}else if(kind==="table"){
inner=(d.message?'<div class="pane-empty">'+escapeHtml(String(d.message))+"</div>":"")
+renderTableSheets(Array.isArray(d.sheets)?d.sheets:[]);
}else{
inner='<pre class="file-view">'+highlightCode(String(d.content!=null?d.content:""),String(d.lang||""))+"</pre>";
}
body.innerHTML=meta+inner;
var btn=body.querySelector("[data-pane-refresh]");
if(btn)btn.addEventListener("click",function(){renderFilePane(body,path);});
}).catch(function(){body.innerHTML='<div class="pane-empty">读取失败</div>';});
}
function openFileTab(path){
var p=String(path||"").trim();
if(!p)return null;
var id=filePaneId(p);
return openPane({
id:id,
/* 标题用文件名：完整路径由面板里的元信息行给出，两处都写路径就是重复。 */
title:baseNameOnly(p)||p,
pinned:false,
onOpen:function(pane){
var body=pane.querySelector(".pane-body");
if(body)renderFilePane(body,p);
}
});
}
/* 知识库面板的渲染逻辑属于 knowledge 插件（`plugins/knowledge/ui/panel.js`），
   面板打开时由壳层按 `_asset` 路由加载并执行。壳层不掺和它的取数与勾选。 */
