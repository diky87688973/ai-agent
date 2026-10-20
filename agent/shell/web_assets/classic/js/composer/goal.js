/* composer/goal.js —— 目标（Goal）按钮三态与设置弹窗。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
const modePlus=document.getElementById("modePlus"),modeMenu=document.getElementById("modeMenu"),modeChip=document.getElementById("modeChip"),modeChipText=document.getElementById("modeChipText"),modeChipClear=document.getElementById("modeChipClear"),goBtn=document.getElementById("go"),stopTaskBtn=document.getElementById("stopTask"),autoToggleBtn=document.getElementById("autoToggle"),chatMoreBtn=document.getElementById("chatMoreBtn"),chatSessionMenu=document.getElementById("chatSessionMenu");
var _autoEnabled=false;
function updateAutoToggleUI(){
if(!autoToggleBtn)return;
var g=_goalInfo||null;var st=g?String(g.status||""):"";var txt=g?String(g.text||"").trim():"";
/* 三态配色（与 CSS 里的 .goal-active / .goal-paused 对应）：
     进行中=暗金、已暂停=暗红、已达成或无目标=默认灰（不带类即回落基色）。
   按钮上不写状态字，靠颜色区分 —— 文字保持"目标"两字，宽度稳定不跳动。 */
autoToggleBtn.classList.toggle("goal-active",st==="active");
autoToggleBtn.classList.toggle("goal-paused",st==="paused");
autoToggleBtn.classList.toggle("active",st==="active"||(!g&&_autoEnabled));
if(txt){
var label=(st==="active"?"进行中":st==="paused"?"已暂停":st==="done"?"已达成":st);
autoToggleBtn.title="目标（"+label+"）"+(g&&g.rounds?(" · 已自动推进 "+g.rounds+" 轮"):"")+"：\n"+txt.slice(0,200)+"\n\n点击修改、暂停或删除";
}else{
autoToggleBtn.title="目标：设定后每轮结束自动用这段文案发起新一轮（点击设置）";
}}
/* 目标状态是服务端权威：页面打开时取一次，之后由 `goal` 工具的调用结果刷新。
   不在前端持久化 —— 目标属于会话，不属于这个浏览器标签页。 */
function renderGoalDialog(){
var cid=getActiveConversationId();if(!cid)return;
var g=_goalInfo||null;var st=g?String(g.status||""):"";
var label=(st==="active"?"进行中":st==="paused"?"已暂停":st==="done"?"已达成":"");
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}

var mask=el("div","goal-mask");
var box=el("div","goal-dialog");
/* 头部：标题 + 状态徽标 */
var head=el("div","goal-dialog-head");
head.appendChild(el("div","goal-dialog-title",g?"目标":"设定目标"));
if(g){
var badge=el("div","goal-badge "+st,label+(g.rounds?(" · 已推进 "+g.rounds+" 轮"):""));
head.appendChild(badge);
}
box.appendChild(head);
box.appendChild(el("div","goal-dialog-sub",
g?"每轮结束时会自动用这段文案发起新一轮；暂停或标记达成后停止。"
 :"设定一句持续推进的目标，之后每轮结束都会自动接着做。"));
var ta2=el("textarea");
ta2.value=g?String(g.text||""):"";
ta2.placeholder="例如：把登录页改成深色主题，并补一份改动说明";
box.appendChild(ta2);
box.appendChild(el("div","goal-dialog-hint","提示：可以随时在这里改文案；模型也能用 goal 工具自己创建或调整。"));

var row=el("div","goal-dialog-actions");
var onEsc=null;
function close(){
/* 监听必须在这里摘：只在"按 Escape"那条分支里摘的话，
   每次用按钮关掉弹窗都会留下一个监听（直到下次按 Escape 才清），
   开几次就积几个 —— 之后任何一次 Escape 会同时触发多个回调。 */
if(onEsc){try{document.removeEventListener("keydown",onEsc);}catch(e){}onEsc=null;}
try{mask.remove();}catch(e){}
try{box.remove();}catch(e){}
}
function post(body){return fetch("/api/chat/goal",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}).then(function(r){return r.json();}).catch(function(){return null;});}
function act(action,extra){
var body={conversation_id:cid,action:action};
if(extra)for(var k in extra)body[k]=extra[k];
post(body).then(function(j){
if(j&&j.goal){_goalInfo=j.goal;}else if(action==="delete"){_goalInfo=null;}
updateAutoToggleUI();close();
});
}
function addBtn(text,cls,fn){var b=el("button","goal-btn"+(cls?(" "+cls):""),text);b.type="button";b._goalClick=fn;row.appendChild(b);return b;}
row.addEventListener("click",function(ev){var b=ev.target&&ev.target.closest?ev.target.closest(".goal-btn"):null;if(b&&row.contains(b)&&typeof b._goalClick==="function")b._goalClick();});

if(g&&st==="active")addBtn("暂停","",function(){act("pause");});
if(g&&st==="paused")addBtn("恢复","",function(){act("resume");});
if(g&&st!=="done")addBtn("标记达成","",function(){act("done");});
if(g)addBtn("删除","danger",function(){act("delete");});
addBtn("取消","",close);
var saveBtn=addBtn("保存","primary",function(){
var v=String(ta2.value||"").trim();
if(!v){ta2.focus();return;}
act("save",{text:v});
});
/* 空文案时禁用保存：让它自己说明"不能为空"，而不是点了没反应 */
function syncSave(){saveBtn.disabled=!String(ta2.value||"").trim();}
ta2.addEventListener("input",syncSave);syncSave();

box.appendChild(row);
document.body.appendChild(mask);document.body.appendChild(box);
/* 定位必须在挂载之后：`getBoundingClientRect()` 只有元素进了文档才有真实几何，
   提前量到的是 0，算出来的 left 全是错的（弹窗会跑到视口最左）。
   对齐的是触发它的那个「目标」按钮：
     - 竖直：贴着输入区上沿（按输入区实际高度算），输入框换行变高时自动抬高；
     - 水平：弹窗中线对齐按钮中线，再夹在视口内（按钮靠右时不顶出屏幕）。
   不用固定 right 值：按钮位置随输入区布局变化（有/无停止键都会挪）。 */
try{
var anchorBtn=(typeof autoToggleBtn!=="undefined"&&autoToggleBtn)?autoToggleBtn:null;
var aRect=anchorBtn&&anchorBtn.getBoundingClientRect?anchorBtn.getBoundingClientRect():null;
var composerEl=document.querySelector(".composer");
var cHeight=composerEl&&composerEl.getBoundingClientRect?composerEl.getBoundingClientRect().height:0;
if(cHeight>0)box.style.bottom=Math.round(cHeight+16)+"px";
if(aRect&&aRect.width){
box.style.transform="none";
box.style.left="0px";                        /* 先归零，量到真实宽度再定位 */
var boxW=box.getBoundingClientRect().width||560;
var vWidth=window.innerWidth||document.documentElement.clientWidth||0;
var wantLeft=aRect.left+(aRect.width/2)-(boxW/2);
var maxLeft=Math.max(8,vWidth-boxW-12);
box.style.left=Math.round(Math.min(Math.max(8,wantLeft),maxLeft))+"px";
}
}catch(e){}
mask.onclick=close;
try{ta2.focus();ta2.setSelectionRange(ta2.value.length,ta2.value.length);}catch(e){}
/* Ctrl/Cmd+Enter 直接保存 */
ta2.addEventListener("keydown",function(e){if((e.ctrlKey||e.metaKey)&&e.key==="Enter"){e.preventDefault();if(!saveBtn.disabled)saveBtn.click();}});
onEsc=function(e){if(e.key==="Escape"){close();}};document.addEventListener("keydown",onEsc);
}
/* 本会话的目标快照（服务端权威，页面打开取一次；此后由 goal 工具结果刷新） */
