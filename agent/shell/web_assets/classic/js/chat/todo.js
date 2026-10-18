/* chat/todo.js —— Todo 清单区域：创建、显示/隐藏、按事件渲染。
 *
 * 经典界面的**同作用域模块**：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
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
var html="";
for(var i=0;i<items.length;i++){
var it=items[i];
var done=!!it.done;
if(done)doneCount++;
var cbClass="todo-cb"+(done?" done":"");
var txtClass="todo-text"+(done?" done":"");
html+='<div class="todo-item"><span class="'+cbClass+'"></span><span class="'+txtClass+'">'+escapeHtml(String(it.text||""))+'</span></div>';
}
if(todoListBody){var sc=todoListBody.querySelector(".todo-list-scroll");if(sc)sc.innerHTML=html;else todoListBody.innerHTML=html;}
if(todoListCount)todoListCount.textContent=doneCount+"/"+items.length;
if(ev.all_done&&todoListArea){todoListArea.style.borderLeft="3px solid #3daf3f";if(!todoListArea.querySelector(".todo-close-btn")){var cb=document.createElement("button");cb.className="todo-close-btn";cb.textContent="✕";cb.title="关闭清单";var hd=todoListArea.querySelector(".todo-list-header");if(hd)hd.appendChild(cb);}}
else if(todoListArea){todoListArea.style.borderLeft="3px solid #a68b4a";var oldBtn=todoListArea.querySelector(".todo-close-btn");if(oldBtn)oldBtn.remove();}
if(ev.collapsed&&todoListArea){todoListArea.classList.add("collapsed");}
else if(ev.collapsed===false&&todoListArea){todoListArea.classList.remove("collapsed");}
if(ev.close&&todoListArea){todoListArea.style.display="none";}
var _owUr=normalizeConversationId(ownerCid||"");if(_owUr){if(ev.close){var _txUr=findConversationTab(_owUr);if(_txUr){_txUr.todoUnread=false;if(typeof syncTodoUnreadBadgeForConversation==="function")syncTodoUnreadBadgeForConversation(_owUr);}}else if(items.length&&_owUr!==normalizeConversationId(activeConversationId)){var _tyUr=findConversationTab(_owUr);if(_tyUr){_tyUr.todoUnread=true;if(typeof syncTodoUnreadBadgeForConversation==="function")syncTodoUnreadBadgeForConversation(_owUr);}}}
}
