/* chat/todo.js —— Todo 清单区域：创建、显示/隐藏、按事件渲染。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
/* ===== Todo-List ===== */
function initTodoListElements(){
if(!todoListArea)return;
todoListBody=todoListArea.querySelector(".todo-list-body");
todoListCount=todoListArea.querySelector(".todo-list-count");
}
function showTodoList(){initTodoListElements();if(todoListArea){todoListArea.classList.remove("hidden");}}
function hideTodoList(){initTodoListElements();if(todoListArea){todoListArea.classList.add("hidden");}}
function renderTodoListFromEvent(ev,ownerCid){
initTodoListElements();
if(todoListArea&&todoListArea.style.display==="none"){todoListArea.style.display="";}
var items=Array.isArray(ev.items)?ev.items:[];
if(!items.length){if(ev.close&&todoListArea){todoListArea.style.display="none";todoListArea.classList.add("hidden");}hideTodoList();var _ocDn=normalizeConversationId(ownerCid||"");if(_ocDn){var _tDn=findConversationTab(_ocDn);if(_tDn){_tDn.todoUnread=false;if(typeof syncTodoUnreadBadgeForConversation==="function")syncTodoUnreadBadgeForConversation(_ocDn);}}return;}
showTodoList();
var doneCount=0;
var activeMarked=false;
var html="";
for(var i=0;i<items.length;i++){
var it=items[i];
var done=!!it.done;
if(done)doneCount++;
var active=!done&&!activeMarked;
if(active)activeMarked=true;
var cbClass="todo-cb"+(done?" done":(active?" active":""));
var txtClass="todo-text"+(done?" done":"");
html+='<div class="todo-item'+(active?" active":"")+'"><span class="'+cbClass+'"></span><span class="'+txtClass+'">'+escapeHtml(String(it.text||""))+'</span></div>';
}
if(todoListBody){var sc=todoListBody.querySelector(".todo-list-scroll");if(sc)sc.innerHTML=html;else todoListBody.innerHTML=html;}
var totalCount=items.length;
var allDone=doneCount===totalCount;
var activeCount=allDone?0:1;
var pendingCount=Math.max(0,totalCount-doneCount-activeCount);
if(todoListCount){
var stats=[{n:doneCount,label:"已完成",cls:"done"}];
if(!allDone){stats.push({n:activeCount,label:"进行中",cls:"active"});stats.push({n:pendingCount,label:"待处理",cls:"pending"});}
todoListCount.innerHTML=stats.map(function(s){return '<span class="todo-stat todo-stat-'+s.cls+'"><b>'+s.n+'</b> '+s.label+'</span>';}).join("");
}
if(allDone&&todoListArea){if(!todoListArea.querySelector(".todo-close-btn")){var cb=document.createElement("button");cb.className="todo-close-btn";cb.textContent="✕";cb.title="关闭清单";var hd=todoListArea.querySelector(".todo-list-header");if(hd)hd.appendChild(cb);}}
else if(todoListArea){var oldBtn=todoListArea.querySelector(".todo-close-btn");if(oldBtn)oldBtn.remove();}
if(ev.collapsed&&todoListArea){todoListArea.classList.add("collapsed");}
else if(ev.collapsed===false&&todoListArea){todoListArea.classList.remove("collapsed");}
if(ev.close&&todoListArea){todoListArea.style.display="none";}
var _owUr=normalizeConversationId(ownerCid||"");if(_owUr){if(ev.close){var _txUr=findConversationTab(_owUr);if(_txUr){_txUr.todoUnread=false;if(typeof syncTodoUnreadBadgeForConversation==="function")syncTodoUnreadBadgeForConversation(_owUr);}}else if(items.length&&_owUr!==normalizeConversationId(activeConversationId)){var _tyUr=findConversationTab(_owUr);if(_tyUr){_tyUr.todoUnread=true;if(typeof syncTodoUnreadBadgeForConversation==="function")syncTodoUnreadBadgeForConversation(_owUr);}}}
}
