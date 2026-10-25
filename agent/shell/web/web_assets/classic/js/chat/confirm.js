/* chat/confirm.js —— 用户确认卡与审批弹窗（user_confirm / approval）。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
var pendingConfirmToolRow=null;

function cancelUserConfirmForNewMessage(){
if(!userConfirmCardHost)return false;
var row=pendingConfirmToolRow;
pendingConfirmToolRow=null;
closeUserConfirmCardHost();
if(row){
if(typeof chatToolSetRowStatus==="function")chatToolSetRowStatus(row,"canceled");
if(typeof chatToolSetResultText==="function")chatToolSetResultText(row,"用户取消了这次确认（未作答）");
}
updateTaskControls();
return true;
}

function openUserConfirmModalFromToolEnd(ev, toolRow){
if(userConfirmCardHost||!ev.user_confirm_required)return;
pendingConfirmToolRow=toolRow||null;
userConfirmBlocking=true;
if(goBtn)goBtn.disabled=false;
hideChatLoading();
var opts=Array.isArray(ev.user_confirm_options)?ev.user_confirm_options:[];
var title=String(ev.user_confirm_title||"请确认");
var multi=!!ev.user_confirm_multi;
var tailIdx=opts.length;
var wrap=document.createElement("div");wrap.className="b a user-confirm-card-outer";
var card=document.createElement("div");card.className="chat-diff-card user-confirm-card";
var cap=document.createElement("div");cap.className="chat-diff-cap user-confirm-cap";
var capLine=document.createElement("div");capLine.className="user-confirm-cap-line";
var h=document.createElement("span");h.className="uc-title";h.textContent=title;
var badge=document.createElement("span");badge.className="user-confirm-badge";
badge.textContent=multi?"待确认·多选":"待确认·单选";
capLine.appendChild(h);capLine.appendChild(badge);cap.appendChild(capLine);card.appendChild(cap);
var body=document.createElement("div");body.className="user-confirm-body";
var btns=document.createElement("div");btns.className="user-confirm-opts";
var pickSingle=-1;
var pickMulti={};
var rows=[];
var customInputEl=null;
function syncRows(){
for(var si=0;si<rows.length;si++){
var R=rows[si];
var on=multi?!!pickMulti[R.idx]:pickSingle===R.idx;
R.icon.classList.toggle("uc-on",on);
R.row.classList.toggle("uc-row-picked",on);
}}
function toggleIdx(idx){
if(multi){if(pickMulti[idx]){delete pickMulti[idx];}else{pickMulti[idx]=1;}syncRows();}
else{pickSingle=(pickSingle===idx)?-1:idx;syncRows();}}
function buildFinal(){
var pref="自定义说明：";
if(multi){
var keys=Object.keys(pickMulti).map(function(x){return parseInt(x,10);}).filter(function(x){return !isNaN(x)&&x>=0&&x<=tailIdx;});
keys.sort(function(a,b){return a-b;});
if(!keys.length)return "";
var parts=[];
for(var ki=0;ki<keys.length;ki++){
var j=keys[ki];
if(j===tailIdx){var ex2=customInputEl?String(customInputEl.value||"").trim():"";if(ex2)parts.push(pref+ex2);}
else{parts.push(String(opts[j]||""));}
}
return parts.join("\n");
}
if(pickSingle<0||pickSingle>tailIdx)return "";
if(pickSingle===tailIdx){var ex=customInputEl?String(customInputEl.value||"").trim():"";return ex?pref+ex:"";}
return String(opts[pickSingle]||"");
}
function addRow(idx,label,isTail){
var row=document.createElement("div");
row.className="uc-opt-row"+(multi?" uc-multi":" uc-single")+(isTail?" uc-has-custom":"");
var icon=document.createElement("span");icon.className=multi?"uc-check":"uc-radio";icon.setAttribute("aria-hidden","true");
row.appendChild(icon);
if(isTail){
var inp=document.createElement("input");inp.type="text";inp.className="uc-opt-input";inp.placeholder="自定义说明";inp.autocomplete="off";customInputEl=inp;
inp.addEventListener("focus",function(){if(multi){pickMulti[idx]=1;}else{pickSingle=idx;}syncRows();});
row.appendChild(inp);
}else{
var lab=document.createElement("span");lab.className="uc-opt-label";lab.textContent=label;
row.appendChild(lab);
}
row.dataset.ucIdx=String(idx);
btns.appendChild(row);rows.push({row:row,icon:icon,idx:idx});
}
for(var oi=0;oi<opts.length;oi++){addRow(oi,String(opts[oi]),false);}
addRow(tailIdx,"",true);
syncRows();
body.appendChild(btns);
var act=document.createElement("div");act.className="user-confirm-actions";
var cancel=document.createElement("button");cancel.type="button";cancel.className="mode-plus uc-cancel";cancel.textContent="取消";
var ok=document.createElement("button");ok.type="button";ok.className="mode-plus uc-ok";ok.textContent="确认";
act.appendChild(cancel);act.appendChild(ok);body.appendChild(act);
card.appendChild(body);wrap.appendChild(card);msgs.appendChild(wrap);userConfirmCardHost=wrap;scrollMsgsToBottom();
function cleanup(){pendingConfirmToolRow=null;closeUserConfirmCardHost();updateTaskControls();}
var submitUserConfirm=async function(finalTxt){
var confirmCid=getActiveConversationId();cleanup();showChatLoading();var gb=goBtn;if(gb)gb.disabled=true;var tab=findConversationTab(confirmCid);if(tab){tab.abortController={global:true};tab.stopRequested=false;}updateTaskControls();
try{
var r=await fetch("/api/chat/user-confirm",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:confirmCid,confirm:finalTxt,mode:selectedMode,model:selectedModel})});
if(!r.ok){var _bc="";try{_bc=await r.text();}catch(e){}if(window.DEBUG)console.error("[ai-agent] /api/chat/user-confirm 非 OK",{status:r.status,bodyHead:String(_bc||"").slice(0,500)});withConversationContext(confirmCid,function(){hideChatLoading();add("a",formatHttpError(r.status,_bc,"确认请求"));});if(tab){tab.abortController=null;tab.activeRunId="";}return;}
var _jr=await r.json();if(tab&&_jr&&_jr.run_id)tab.activeRunId=String(_jr.run_id||"");if(_jr&&_jr.ok!==false&&toolRow){var picked=String(finalTxt||"").trim();if(typeof chatToolSetRowStatus==="function")chatToolSetRowStatus(toolRow, picked?"done":"bad");if(typeof chatToolSetResultText==="function")chatToolSetResultText(toolRow, picked||"用户取消了这次确认（未作答）");}
}catch(err){if(err&&err.name==="AbortError"){return;}withConversationContext(confirmCid,function(){hideChatLoading();add("a","确认请求失败: "+(err&&err.message?err.message:String(err)));});}
finally{updateTaskControls();}
};
card._confirmClick=function(e){
var hit=e.target;
if(!hit||!hit.closest)return;
if(hit.closest(".uc-opt-input"))return;
if(hit.closest(".uc-cancel")){void submitUserConfirm("");return;}
if(hit.closest(".uc-ok")){void submitUserConfirm(buildFinal());return;}
var rowHit=hit.closest(".uc-opt-row");
if(!rowHit||!card.contains(rowHit))return;
var picked=parseInt(rowHit.dataset.ucIdx,10);
if(!isNaN(picked))toggleIdx(picked);
};
}
function openApprovalModalFromToolEnd(ev, toolRow){
if(userConfirmCardHost||!ev.approval_required)return;
pendingConfirmToolRow=toolRow||null;
userConfirmBlocking=true;
if(goBtn)goBtn.disabled=false;
hideChatLoading();
var desc=String(ev.approval_desc||"").trim()||"（无描述）";
var wrap=document.createElement("div");wrap.className="b a user-confirm-card-outer";
var card=document.createElement("div");card.className="chat-diff-card user-confirm-card";
var cap=document.createElement("div");cap.className="chat-diff-cap user-confirm-cap";
var capLine=document.createElement("div");capLine.className="user-confirm-cap-line";
var h=document.createElement("span");h.className="uc-title";h.textContent="审批";
capLine.appendChild(h);cap.appendChild(capLine);card.appendChild(cap);
var body=document.createElement("div");body.className="user-confirm-body";
var p=document.createElement("div");p.className="approval-desc";p.textContent=desc;
body.appendChild(p);
var act=document.createElement("div");act.className="user-confirm-actions";
var reject=document.createElement("button");reject.type="button";reject.className="mode-plus approval-reject";reject.textContent="驳回";
var agree=document.createElement("button");agree.type="button";agree.className="mode-plus approval-agree";agree.textContent="同意";
act.appendChild(reject);act.appendChild(agree);body.appendChild(act);
card.appendChild(body);wrap.appendChild(card);msgs.appendChild(wrap);userConfirmCardHost=wrap;scrollMsgsToBottom();
function cleanup(){pendingConfirmToolRow=null;closeUserConfirmCardHost();updateTaskControls();}
var submitApproval=async function(agreed){
var confirmCid=getActiveConversationId();cleanup();showChatLoading();var gb=goBtn;if(gb)gb.disabled=true;var tab=findConversationTab(confirmCid);if(tab){tab.abortController={global:true};tab.stopRequested=false;}updateTaskControls();
try{
var r=await fetch("/api/chat/user-confirm",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({conversation_id:confirmCid,approval:agreed?"agree":"reject",mode:selectedMode,model:selectedModel})});
if(!r.ok){var _bc="";try{_bc=await r.text();}catch(e){}if(window.DEBUG)console.error("[ai-agent] /api/chat/user-confirm 非 OK",{status:r.status,bodyHead:String(_bc||"").slice(0,500)});withConversationContext(confirmCid,function(){hideChatLoading();add("a",formatHttpError(r.status,_bc,"审批请求"));});if(tab){tab.abortController=null;tab.activeRunId="";}return;}
var _jr=await r.json();if(tab&&_jr&&_jr.run_id)tab.activeRunId=String(_jr.run_id||"");if(_jr&&_jr.ok!==false&&toolRow){var decision=agreed?"同意":"不同意";var aid=String(_jr.approval_id||"").trim();if(typeof chatToolSetRowStatus==="function")chatToolSetRowStatus(toolRow,"done");if(typeof chatToolSetResultText==="function")chatToolSetResultText(toolRow,agreed&&aid?(decision+"\n"+aid):decision);}
}catch(err){if(err&&err.name==="AbortError"){return;}withConversationContext(confirmCid,function(){hideChatLoading();add("a","审批请求失败: "+(err&&err.message?err.message:String(err)));});}
finally{updateTaskControls();}
};
card._confirmClick=function(e){
var hit=e.target;
if(!hit||!hit.closest)return;
if(hit.closest(".approval-reject"))void submitApproval(false);
else if(hit.closest(".approval-agree"))void submitApproval(true);
};
}
document.addEventListener("click",function(ev){
var card=ev.target&&ev.target.closest?ev.target.closest(".user-confirm-card"):null;
if(!card||typeof card._confirmClick!=="function")return;
card._confirmClick(ev);
});
