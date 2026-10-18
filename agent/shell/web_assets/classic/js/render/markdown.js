/* render/markdown.js —— Markdown 渲染：marked 扩展、代码围栏、diff 卡片、渲染入口。
 *
 * 经典界面的**同作用域模块**：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
var _mdParser=null;
function mdParser(){
if(_mdParser)return _mdParser;
if(typeof marked==="undefined"||!marked)return null;
_mdParser=(typeof marked.Marked==="function")?new marked.Marked():marked;
_mdParser.use({renderer:markedRenderer()});
_mdParser.use({extensions:[atFileExtension()]});
_mdParser.use({renderer:filePathCodespanExtension()});
return _mdParser;
}
/* 兼容旧调用点：注册动作现在由 `mdParser()` 一次装好，这里只确保实例已建。 */
function initMarkedExtensions(){
mdParser();
}
var _markedRenderer=null;
function markedRenderer(){
if(_markedRenderer)return _markedRenderer;
var r=new marked.Renderer();
/* 路径改写**只在渲染这一步做**，不改 token：`walkTokens` 改过 `href` 之后
   就取不回本地路径了，而悬停提示要显示文件在哪。
   视频用 `<video>` 而不是 `<img>`：`<img>` 对 mp4 只会显示成破图。 */
r.image=function(token){
var raw=String((token&&token.href)||"");
var href=markedImageHref(raw);
var alt=String((token&&token.text)||"");
var title=String((token&&token.title)||"")||raw;
var t=title?' title="'+escapeHtml(title)+'"':'';
if(markedIsVideo(href))return '<video src="'+escapeHtml(href)+'" controls'+t+' style="max-width:100%;border-radius:6px;margin:4px 0;max-height:480px;background:#000;"></video>';
return '<img src="'+escapeHtml(href)+'" alt="'+escapeHtml(alt)+'"'+t+' loading="lazy" style="max-width:300px;height:auto" />';
};
r.link=function(token){
var raw=String((token&&token.href)||"");
/* 媒体文件的本地路径 → `/api/media`；其余链接原样（外链带 `target=_blank`） */
var href=(markedIsMediaFile(raw)&&localAbsPath(raw))?markedImageHref(raw):raw;
var text=token&&token.tokens?this.parser.parseInline(token.tokens):escapeHtml((token&&token.text)||"");
var ext=/^https?:/i.test(href);
return '<a href="'+escapeHtml(href)+'"'+(ext?' target="_blank" rel="noopener noreferrer"':'')+'>'+text+'</a>';
};
_markedRenderer=r;
return r;
}
function renderMarkdownBlocks(seg){
var parser=mdParser();
if(!parser||typeof parser.parse!=="function"){
/* 解析器缺失时回落成纯文本：宁可少排版，也不要把 markdown 源码当 HTML 插进去 */
return '<p>'+escapeHtml(seg||"").replace(/\n/g,"<br/>")+'</p>';
}
return sanitizeRenderedHtml(parser.parse(String(seg||""),{gfm:true,breaks:false,html:false}));
}
function isUnifiedDiffLine(line){
var s=String(line||"");
if(!s)return false;
if(/^---\s/.test(s)||/^\+\+\+\s/.test(s)||/^@@\s/.test(s))return true;
if(/^[-+]/.test(s))return true;
return false;
}
function shouldStartUnifiedDiffBlock(lines,i){
if(i>=lines.length||!isUnifiedDiffLine(lines[i]))return false;
if(/^---\s/.test(lines[i])||/^@@\s/.test(lines[i]))return true;
if(i+1>=lines.length)return/^[-+]/.test(lines[i]);
return isUnifiedDiffLine(lines[i+1]);
}
function collectUnifiedDiffBlock(lines,start){
var block=[],i=start;
while(i<lines.length){
var line=lines[i];
if(isUnifiedDiffLine(line)){block.push(line);i++;continue;}
if(!String(line).trim()&&i+1<lines.length&&isUnifiedDiffLine(lines[i+1])){block.push(line);i++;continue;}
break;
}
return {lines:block,next:i};
}
function looksLikeUnifiedDiffBlock(block){
if(!block||block.length<2)return false;
var hasMarker=false,hasChange=false;
for(var j=0;j<block.length;j++){
var L=block[j];
if(/^---\s/.test(L)||/^\+\+\+\s/.test(L)||/^@@\s/.test(L))hasMarker=true;
if((/^-/.test(L)&&!/^---/.test(L))||(/^\+/.test(L)&&!/^\+\+\+/.test(L)))hasChange=true;
}
return hasMarker;
}
function renderUnifiedDiffBlockHtml(block){
var body=block.join("\n");
var cards=renderUnifiedDiffBodyAsCardsHtml(body);
if(cards)return cards;
return '<pre><code>'+escapeHtml(body)+'</code></pre>';
}
function isDevNullPath(p){
var s=String(p||"").trim().replace(/\\/g,"/").toLowerCase();
if(!s||s==="null")return true;
return s==="/dev/null"||s==="dev/null"||s.endsWith("/dev/null");
}
function parseDiffHeaderPath(line){
var m=/^(---|\+\+\+)\s+(.+)$/.exec(String(line||"").trim());
if(!m)return "";
return m[2].split("\t")[0].trim();
}
function diffFileNameFromBody(body){
var lines=String(body||'').replace(/\r/g,'').split('\n');
var fromRaw="",toRaw="";
for(var i=0;i<lines.length;i++){
var L=lines[i];
if(!fromRaw&&L.indexOf("--- ")===0)fromRaw=parseDiffHeaderPath(L);
if(!toRaw&&L.indexOf("+++ ")===0)toRaw=parseDiffHeaderPath(L);
}
if(toRaw&&!isDevNullPath(toRaw))return baseNameOnly(toRaw);
if(fromRaw&&!isDevNullPath(fromRaw))return baseNameOnly(fromRaw);
return "文件";
}
function findDiffFenceCloseIndex(rest){
var reLine=/^[ \t]*```[ \t]*$/gm,m;
while((m=reLine.exec(rest))!==null){
var after=rest.slice(m.index+m[0].length);
var trimmed=after.replace(/^\r?\n/,"");
if(!trimmed.trim())return m.index;
if(/^```(?:diff|patch)\b/i.test(trimmed))return m.index;
var lines=trimmed.split(/\r?\n/);
var line0=lines[0]||"";
var firstLine=line0.trim();
if(/^---\s/.test(firstLine)||/^\+\+\+\s/.test(firstLine)||/^@@\s/.test(firstLine))continue;
// 只有多行连续以 -/+ 开头才认为是 diff 内容，避免单行误判
if(/^[-+]/.test(firstLine)){
for(var di=1;di<Math.min(lines.length,4);di++){
var l=(lines[di]||"").trim();
if(!l)break;
if(l.charAt(0)==="-"||l.charAt(0)==="+")continue;
return m.index;
}
continue;
}
return m.index;
}
return -1;
}
function splitUnifiedDiffSections(body){
var lines=String(body||"").replace(/\r/g,"").split("\n");
var sections=[],cur=[];
for(var i=0;i<lines.length;i++){
var L=lines[i];
if(/^---\s/.test(L)&&cur.some(function(x){return /^---\s/.test(x);})){
sections.push(cur.join("\n"));
cur=[L];
continue;
}
cur.push(L);
}
if(cur.length)sections.push(cur.join("\n"));
return sections.filter(function(s){return String(s).trim();});
}
function renderUnifiedDiffBodyAsCardsHtml(body){
// 快速检查：没有任何 diff 标记行的内容不渲染为 diff 卡片
if(!/^---\s/m.test(body)&&!/^\+\+\+\s/m.test(body)&&!/^@@\s/m.test(body))return "";
var sections=splitUnifiedDiffSections(body);
if(!sections.length)return "";
var html="";
for(var si=0;si<sections.length;si++){
var sec=sections[si];
var lines=sec.replace(/\r/g,"").split("\n");
var fn=diffFileNameFromBody(sec);
for(var fi=0;fi<lines.length;fi++){
var L=lines[fi];
if(L.indexOf("--- ")===0||L.indexOf("+++ ")===0){
var mp=L.match(/[ab][\/](.+)/);
if(mp){fn=mp[1];break;}
}
}
var add=0,del=0;
for(var li=0;li<lines.length;li++){
var L=lines[li];
if(L.indexOf("--- ")===0||L.indexOf("+++ ")===0)continue;
var c=L.charAt(0);
if(c==="+")add++;else if(c==="-")del++;
}
var cap='<div class="chat-diff-cap">'+escapeHtml(fn)+' · diff'+(del>0?' <span class="chat-diff-neg">-'+del+'</span>':'')+(add>0?' <span class="chat-diff-pos">+'+add+'</span>':'')+'</div>';
var box='<div class="diff-unified diff-surface-adaptive">';
for(var li=0;li<lines.length;li++){
var L=lines[li];
var ch0=L.charAt(0);
if(ch0==="-"||ch0==="+"){
if(L.indexOf("--- ")===0||L.indexOf("+++ ")===0)continue;
box+='<div class="'+(ch0==="-"? 'd-del' : 'd-add')+'">'+diffRowInnerHtml({t:ch0,l:L.substring(1)})+'</div>';}
else if(/^@@/.test(L)){
box+='<div class="d-meta">'+escapeHtml(L)+'</div>';}
else if(ch0===" "){
box+='<div class="d-eq">'+diffRowInnerHtml({t:" ",l:L.replace(/^\s/,"")})+'</div>';}
else if(L.trim()){
box+='<div class="d-eq">'+diffRowInnerHtml({t:" ",l:L})+'</div>';}
}
box+='</div>';
html+='<div class="chat-diff-card">'+cap+box+'</div>';
}
return html;
}
/* 围栏缩进上限（空格数）。
   按 CommonMark，围栏可以缩进 0–3 个空格；**列表项里的围栏通常缩进 1–3 格**
   （`- 说明：\n  ```python\n  …\n  ```），只认行首会让这些围栏裸露成正文。
   缩进 4 格及以上是缩进式代码块，不是围栏，不在此处理。 */
var FENCE_MAX_INDENT=3;
function iterMarkdownCodeFences(text,visit){
var src=String(text||"").replace(/\r\n/g,"\n");
var i=0;
while(i<src.length){
var open=src.indexOf("```",i);
if(open<0){visit("text",src.slice(i));break;}
// 只认行首（可带 0–3 空格缩进）的 ```，行内的 ``` 当作普通文本跳过
var lineStart=src.lastIndexOf("\n",open)+1;
var indent=open-lineStart;
if(indent>FENCE_MAX_INDENT||!/^[ \t]*$/.test(src.slice(lineStart,open))){
visit("text",src.slice(i,open+3));i=open+3;continue;
}
if(open>i)visit("text",src.slice(i,open));
var langEnd=src.indexOf("\n",open+3);
if(langEnd<0){visit("text",src.slice(open));break;}
var lang=src.slice(open+3,langEnd);
var langLow=lang.trim().toLowerCase();
var pos=langEnd+1;
var closed=false;
if(langLow==="diff"||langLow==="patch"){
var rest=src.slice(pos);
var closeAt=findDiffFenceCloseIndex(rest);
if(closeAt>=0){
var closeMatch=rest.slice(closeAt).match(/^[ \t]*```/);
visit("fence",lang,rest.slice(0,closeAt).replace(/\n$/,""));
i=pos+closeAt+closeMatch[0].length;
var nl=src.indexOf("\n",i);
i=nl<0?src.length:nl+1;
closed=true;
}
}else{
while(pos<src.length){
var idx=src.indexOf("```",pos);
if(idx<0)break;
var closeLineStart=src.lastIndexOf("\n",idx-1)+1;
// 闭合围栏同样允许 0–3 空格缩进，但行内不能有别的内容
var closeIndent=idx-closeLineStart;
if(closeIndent>FENCE_MAX_INDENT||!/^[ \t]*$/.test(src.slice(closeLineStart,idx))){pos=idx+3;continue;}
var lineEnd=src.indexOf("\n",idx);
if(lineEnd<0)lineEnd=src.length;
var line=src.slice(closeLineStart,lineEnd);
if(/^[ \t]*```[ \t]*$/.test(line)){
/* 围栏内容去掉与开栏相同的缩进量：markdown 里缩进是列表层级的产物，
   不属于代码本身，留着会让每行都多个前导空格甚至被 marked 当成嵌套代码块。 */
var body=src.slice(langEnd+1,closeLineStart).replace(/\n$/,"");
if(indent>0){
var pad=new RegExp("^[ \\t]{0,"+indent+"}");
body=body.split("\n").map(function(l){return l.replace(pad,"");}).join("\n");
}
visit("fence",lang,body);
i=lineEnd<src.length?lineEnd+1:src.length;
closed=true;
break;
}
pos=idx+3;
}
}
if(!closed){visit("text",src.slice(open));break;}
}
}
function parseUnifiedDiffBodyForRows(body){
var lines=String(body||'').replace(/\r/g,'').split('\n');
var oldL=[],newL=[];
for(var i=0;i<lines.length;i++){
var L=lines[i];
if(/^---/.test(L)||/^\+\+\+/.test(L))continue;
if(/^@@/.test(L))continue;
if(/^\s*#/.test(L))continue;
if(/^-/.test(L)&&!/^---/.test(L))oldL.push(L.slice(1));
else if(/^\+/.test(L)&&!/^\+\+\+/.test(L))newL.push(L.slice(1));
else if(/^ /.test(L)){var c=L.slice(1);oldL.push(c);newL.push(c);}
}
return {oldT:oldL.join('\n'),newT:newL.join('\n')};
}
function diffRowInnerHtml(r){
var g=r.t==='-'?'−':(r.t==='+'?'+':' ');
var gs=r.t==='-'?'d-gutter-del':(r.t==='+'?'d-gutter-add':'d-gutter-eq');
return '<span class="d-gutter '+gs+'">'+escapeHtml(g)+'</span><span class="d-code">'+escapeHtml(r.l)+'</span>';
}
function buildDiffRowsHtml(oldT,newT){
var rows=linesDiff(oldT,newT);
var html='';
for(var ri=0;ri<rows.length;ri++){
var r=rows[ri];
var cls=r.t==='-'?'d-del':(r.t==='+'?'d-add':'d-eq');
html+='<div class="'+cls+'">'+diffRowInnerHtml(r)+'</div>';
}
return html;
}
function buildChatDiffCardHtml(oldT,newT,nameHint){
var st=calcDiffStats(oldT,newT);
var fn=String(nameHint||'').trim()||'文件';
var cap='<div class="chat-diff-cap">'+escapeHtml(fn)+' · diff';
if(st.del>0)cap+=' <span class="chat-diff-neg">-'+st.del+'</span>';
if(st.add>0)cap+=' <span class="chat-diff-pos">+'+st.add+'</span>';
cap+='</div>';
var box='<div class="diff-unified diff-surface-adaptive">'+buildDiffRowsHtml(oldT,newT)+'</div>';
return '<div class="chat-diff-card">'+cap+box+'</div>';
}
function renderSimpleDiffCard(inner,lang){
// 无 unified diff 头的简化 diff 代码块 → 渲染为 diff 卡片
var lines=String(inner||'').split('\n');
var add=0,del=0;
for(var _i=0;_i<lines.length;_i++){var _c=lines[_i].charAt(0);if(_c==='+')add++;else if(_c==='-')del++;}
var cap='<div class="chat-diff-cap">'+escapeHtml(lang||'diff')+(del?' <span class="chat-diff-neg">-'+del+'</span>':'')+(add?' <span class="chat-diff-pos">+'+add+'</span>':'')+'</div>';
var box='<div class="diff-unified diff-surface-adaptive">';
for(var _i=0;_i<lines.length;_i++){var L=lines[_i];var ch0=L.charAt(0);
if(ch0==='-'){box+='<div class="d-del">'+diffRowInnerHtml({t:'-',l:L.substring(1)})+'</div>';}
else if(ch0==='+'){box+='<div class="d-add">'+diffRowInnerHtml({t:'+',l:L.substring(1)})+'</div>';}
else if(ch0===' '){box+='<div class="d-eq">'+diffRowInnerHtml({t:' ',l:L.replace(/^ /,'')})+'</div>';}
else if(L.trim()){box+='<div class="d-eq">'+diffRowInnerHtml({t:' ',l:L})+'</div>';}}
box+='</div>';
return '<div class="chat-diff-card">'+cap+box+'</div>';
}
function renderMarkdown(md){
const text=String(md||'').replace(/\r\n/g,'\n');
let html='';
iterMarkdownCodeFences(text,function(kind,a,b){
if(kind==='text'){html+=renderMarkdownBlocks(a);return;}
const lang=String(a||'').trim();
const inner=b;
const langLow=lang.toLowerCase();
if((langLow==='diff'||langLow==='patch')&&inner){
var cards=renderUnifiedDiffBodyAsCardsHtml(inner);
if(cards){
html+=cards;
}else{
html+=renderSimpleDiffCard(inner,lang);
}
}else{
var _hc2=hljsCodeClass(lang);html+='<pre><code'+(_hc2?' class="'+_hc2+'"':'')+(lang?' data-lang="'+escapeHtml(lang)+'"':'')+'>'+highlightCode(inner,lang)+'</code></pre>';
}
});
return html||'<p></p>';
}
