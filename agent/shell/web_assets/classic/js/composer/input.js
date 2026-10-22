/* composer/input.js —— 输入区交互：斜杠菜单、命令输入条、事件委托、快捷键提示。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
function initKbAndSlashUi(){
if(ta&&slashPop){
slashPop.addEventListener("click",function(e){
var b=e.target.closest(".slash-item");if(!b)return;e.stopPropagation();hideSlashPop();ta.value="";
var s=b.getAttribute("data-slash");if(s==="auto")applyMode("auto");else if(s==="plan")applyMode("plan");else if(s==="execute")applyMode("execute");
});
ta.addEventListener("keyup",function(e){if(e.isComposing)return;if(e.key==="Escape"){hideSlashPop();hideAtPop();return;}
if(e.key==="/"&&document.activeElement===ta&&ta.value==="/"){var ci=slashPop.children;for(var i=0;i<ci.length;i++){ci[i].classList.remove("selected");ci[i].style.display=(ci[i].dataset.slash===selectedMode?"none":"");}for(var i=0;i<ci.length;i++){if(ci[i].style.display!=="none"){ci[i].classList.add("selected");slashSelectedIndex=i;break;}}updateSlashPopHints();positionSlashPop();slashPop.classList.remove("hidden");slashPop.setAttribute("aria-hidden","false");}
});
ta.addEventListener("input",function(){autoResizeTextarea();var ap=getAtPop();var vis=ap&&ap.style.visibility!=="hidden";if(atMentionActiveAtCursor()&&(!ap||!vis)){showAtPop();}else if(vis&&!atMentionActiveAtCursor()){hideAtPop();}if(ta.value!=="/")hideSlashPop();});
document.addEventListener("mousedown",function(ev){var ap2=getAtPop();if(!ap2||ap2.style.visibility==="hidden")return;if(ap2.contains(ev.target))return;hideAtPop();},true);
}
/* 输入区按钮全部来自插件声明，页面不再有写死的插件入口 */
/* `@文件` 引用的点击：从 document 收一次冒泡，避免给每个 chip 单独绑事件。
   链接默认行为要拦掉 —— 否则浏览器会把它当普通 `<a>` 去跳转。
   待办标题、命令确认按钮也走这一条：它们都是后画进对话区的。 */
document.addEventListener("click",function(ev){
var el=ev.target;
if(!el||!el.closest)return;
var optBtn=el.closest(".cmd-input-btn[data-cmd-opt]");
var sendBtn=optBtn?null:el.closest(".cmd-input-btn[data-cmd-send]");
if(optBtn||sendBtn){
var bar=(optBtn||sendBtn).closest(".cmd-input-bar");
if(!bar)return;
var value=optBtn?String(optBtn.getAttribute("data-cmd-opt")||""):String((bar.querySelector(".cmd-input-field")||{}).value||"").trim();
if(sendBtn&&!value)return;
ev.preventDefault();
var cid=normalizeConversationId(bar.getAttribute("data-cmd-cid")||activeConversationId);
var tid=String(bar.getAttribute("data-cmd-tid")||"").trim();
submitCommandInputToServer(cid,tid,value);
var opened=tid&&toolOpen.get(tid);
if(opened&&opened.tag&&optBtn){opened.tag.textContent="已发送 "+value;opened.tag.className="tag tag-run";}
try{bar.remove();}catch(eCmd){}
if(opened)opened.cmdInputBar=null;
return;
}
var todoClose=el.closest(".todo-close-btn");
if(todoClose){
var todoArea=todoClose.closest(".todo-list-area");
if(todoArea)todoArea.style.display="none";
ev.preventDefault();
return;
}
var todoHead=el.closest(".todo-list-header");
if(todoHead){
var todoBox=todoHead.closest(".todo-list-area");
if(todoBox)todoBox.classList.toggle("collapsed");
return;
}
while(el&&el!==document){
if(el.classList&&el.classList.contains("chat-file-card")){
var fp=el.getAttribute("data-file-path")||"";
if(fp){ev.preventDefault();openFileTab(fp);}
return;
}
if(el.classList&&el.classList.contains("file-ref")){
var p=el.getAttribute("data-file-path")||"";
if(p){ev.preventDefault();openFileTab(p);}
return;
}
if(el.tagName==="A"){
var fp=filePathFromHref(el.getAttribute("href")||"");
if(fp){
if(ev.button===0&&!ev.metaKey&&!ev.ctrlKey&&!ev.shiftKey&&!ev.altKey){ev.preventDefault();openFileTab(fp);}
return;
}
}
el=el.parentNode;
}
});
}
if(!document._fileCardKeydownBound){
document._fileCardKeydownBound=true;
document.addEventListener("keydown",function(ev){
if(ev.key!=="Enter"&&ev.key!==" ")return;
var t=ev.target;
if(!t||!t.closest)return;
var card=t.closest(".chat-file-card");
if(!card)return;
var p=card.getAttribute("data-file-path")||"";
if(!p)return;
ev.preventDefault();openFileTab(p);
});
}
function updateSlashPopHints(){
var items=slashPop.querySelectorAll(".slash-item");var visibles=[];
for(var i=0;i<items.length;i++){if(items[i].style.display!=="none")visibles.push(items[i]);}
if(!visibles.length)return;var selIdx=-1;
for(var i=0;i<visibles.length;i++){if(visibles[i].classList.contains("selected")){selIdx=i;break;}}
if(selIdx<0){visibles[0].classList.add("selected");selIdx=0;}
for(var i=0;i<visibles.length;i++){
var sh=visibles[i].querySelector(".sh");if(!sh)continue;
var sk=(visibles[i].dataset.slash||"").charAt(0).toUpperCase();
var hint;
if(i===selIdx)hint="Enter";
else if(i<selIdx)hint="↑ + Enter";
else hint="↓ + Enter";
sh.textContent=sk+"  "+hint;
}
}

function escapeHtml(s){
return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function highlightJson(s){
if(window.codeHighlight)return window.codeHighlight.highlightCode(s,'json');
var t=String(s||'');try{var o=JSON.parse(t);t=JSON.stringify(o,null,2);}catch(e){}
return t.replace(/("(?:\\.|[^"\\])*")\s*:/g,'<span style="color:#ce9178;">$1</span>:')
.replace(/:\s*("(?:\\.|[^"\\])*")/g,':<span style="color:#ce9178;">$1</span>')
.replace(/:\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g,':<span style="color:#b5cea8;">$1</span>')
.replace(/:\s*(true|false|null)/g,':<span style="color:#569cd6;">$1</span>');}
function highlightCode(s,lang){
if(window.codeHighlight)return window.codeHighlight.highlightCode(s,lang);
var t=String(s||'');
if(String(lang||'').toLowerCase()==='json'||(!lang&&/^\s*[\[{]/.test(t)))return highlightJson(t);
return escapeHtml(t);
}
function detectScriptLang(code,hint){
if(window.codeHighlight)return window.codeHighlight.detectScriptLang(code,hint);
return 'python';
}
function hljsCodeClass(lang){
if(window.codeHighlight)return window.codeHighlight.hljsCodeClass(lang);
return '';
}
/* markdown 渲染用 `marked`（`js/vendor/marked.min.js`，内联在共用脚本里）。
   自研块渲染器的问题在块级语义：`<li>` 里不产出 `<p>`，松散列表的段距整段丢失；
   表格 / 任务清单 / 嵌套列表也各有偏差。markdown 的块级规则细节多，交给成熟实现。

   `breaks` 保持 CommonMark 默认（false）：模型输出的长段在源里是软换行，
   按硬换行渲染会把整段切成一行一断的碎片。段落靠空行（`\n\n`）分隔。

   代码围栏不走 marked：`renderMarkdown()` 先把围栏切出去交给既有逻辑
   （diff 卡片 / hljs 高亮），只把散文块交到这里。 */

/* 本地媒体文件的绝对路径 → 浏览器能取的 URL。
   两条路由，按路径落在哪选：
     · 工作区内（路径里有 `workspace` 段）→ `/workspace/<rel>`
       静态路由根是 `data/workspace`（web.py 的 `/workspace/` 路由）。
       取最后一个 `workspace` 段之后的部分：更靠前的目录也可能同名。
     · 其余本地绝对路径（正文里任意位置的本地图片 / 音频 / 视频）→ `/api/media?path=`
       它的根是各盘根，按 `mimetypes` 出类型，不做扩展名白名单。
   裸本地路径不能直接当 `src`：浏览器不认，图会破。
   `file://` 前缀先剥掉 —— 它对 `<img src>` 同样没用。 */
