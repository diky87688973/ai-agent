/* chat/confirm.js —— 用户确认卡与审批弹窗（user_confirm / approval）。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */

function _sendBtn(){return document.querySelector('[data-ui-action="input.send"]');}

function closeMatchingConfirmation(ev){
  var card=userConfirmCardHost;
  if(!card||card.dataset.callId!==String(ev.call_id||"")||
     card.dataset.requestId!==String(ev.request_id||""))return;
  if(ev.expired&&card.confirmToolRow){
    chatToolSetRowStatus(card.confirmToolRow,"canceled");
    chatToolSetResultText(card.confirmToolRow,"无结果：用户未作答");
  }
  var tab=findConversationTab(card.dataset.conversationId);
  if(tab)tab.confirmationVersion=(tab.confirmationVersion||0)+1;
  closeUserConfirmCardHost();
  updateTaskControls();
}

async function restoreCrossProcessConfirmation(tab,current,version){
  if(!tab.historyLoaded||tab.subagent)return;
  var response=await fetch("/api/chat/history?"+new URLSearchParams({conversation_id:tab.id}));
  if(!response.ok)return;
  var body=await response.json();
  var item=(body.items||[]).find(function(row){
    var envelope=row.envelope||{};
    return row.status==="suspended"&&row.tool_call_id===current.call_id&&
      String(envelope.request_id||row.tool_call_id)===current.request_id;
  });
  if(!item||findConversationTab(tab.id)!==tab||(tab.confirmationVersion||0)!==version)return;
  withConversationContext(tab.id,function(){
    if(!userConfirmCardHost)renderHistoryToolItem(item);
  });
}

async function reconcileConfirmationCards(){
  var selected=getActiveConversationId();
  var checks=conversationTabs.flatMap(function(tab){
    var card=tab.msgsHost&&tab.msgsHost.querySelector(".user-confirm-card-outer[data-call-id]");
    if(!card&&(tab.id!==selected||!tab.historyLoaded))return [];
    return [{tab:tab,version:tab.confirmationVersion||0,
             call_id:card&&card.dataset.callId,request_id:card&&card.dataset.requestId}];
  });
  if(!checks.length)return;
  try{
    var params=new URLSearchParams({confirmation_ids:checks.map(function(entry){return entry.tab.id;}).join(",")});
    var response=await fetch("/api/chat/ui-state?"+params);
    if(!response.ok)return;
    var body=await response.json();
    var active=body.state&&body.state.confirmations;
    if(!active)return;
    for(var entry of checks){
      var tab=entry.tab;
      if(findConversationTab(tab.id)!==tab||(tab.confirmationVersion||0)!==entry.version)continue;
      var current=active[tab.id];
      if(entry.call_id&&(!current||current.call_id!==entry.call_id||current.request_id!==entry.request_id)){
        withConversationContext(tab.id,function(){closeMatchingConfirmation({...entry,expired:true});});
      }
      if(current&&tab.id===selected&&(!entry.call_id||current.call_id!==entry.call_id||current.request_id!==entry.request_id)){
        await restoreCrossProcessConfirmation(tab,current,tab.confirmationVersion||0);
      }
    }
  }catch(error){
    console.debug("[confirm] state unavailable",error);
  }
}

window.addEventListener("focus",function(){void reconcileConfirmationCards();});
document.addEventListener("ai-agent:conversation-changed",function(){void reconcileConfirmationCards();});

function bindConfirmationCard(outer,ev,toolRow){
  outer.dataset.callId=String(ev.tool_call_id||"");
  outer.dataset.requestId=String(ev.user_confirm_request_id||ev.tool_call_id||"");
  outer.dataset.conversationId=String((msgs&&msgs.dataset.conversationId)||getActiveConversationId());
  outer.confirmToolRow=toolRow;
  var tab=findConversationTab(outer.dataset.conversationId);
  if(tab)tab.confirmationVersion=(tab.confirmationVersion||0)+1;
}

function showConfirmationResumeRetry(cid, ids){
  var notice=add("a","确认已保存，续跑待重试。");
  if(!notice)return;
  var retry=document.createElement("button");
  retry.type="button";
  retry.textContent="重试续跑";
  retry.className="user-confirm-btn";
  notice.appendChild(retry);
  retry.addEventListener("click",async function(){
    retry.disabled=true;
    try{
      var response=await fetch("/api/chat/user-confirm",{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({conversation_id:cid,...ids,retry_resume:true})
      });
      var result=await response.json();
      if(result.expired){
        notice.textContent=result.error||"这次确认无需再次续跑。";
        return;
      }
      if(!response.ok||result.ok===false||result.resume_pending)throw new Error(result.error||"续跑失败");
      notice.textContent="已提交续跑。";
    }catch(error){
      retry.title=error.message;
      retry.textContent="续跑失败，重试";
      retry.disabled=false;
    }
  });
}

async function submitConfirmation(outer,endpoint,choice){
  if(outer.dataset.sending==="1")return null;
  outer.dataset.sending="1";
  var cid=outer.dataset.conversationId;
  var ids={call_id:outer.dataset.callId,request_id:outer.dataset.requestId};
  try{
    var response=await fetch(endpoint,{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({conversation_id:cid,...ids,...choice})
    });
    var result=await response.json();
    if(result.expired){
      withConversationContext(cid,function(){
        closeMatchingConfirmation({...ids,expired:true});
        add("a","操作无效，该确认已过期");
      });
      return null;
    }
    if(!response.ok||result.ok===false)throw new Error(result.error||"确认失败");
    withConversationContext(cid,function(){
      closeMatchingConfirmation(ids);
      if(result.resume_pending)showConfirmationResumeRetry(cid,ids);
    });
    return result;
  }catch(error){
    withConversationContext(cid,function(){add("a","确认请求失败："+error.message);});
    return null;
  }finally{
    delete outer.dataset.sending;
  }
}

function openUserConfirmModalFromToolEnd(ev, toolRow){
if(userConfirmCardHost||!ev.user_confirm_required)return;
userConfirmBlocking=true;
if(_sendBtn())_sendBtn().disabled=false;
hideChatLoading();
var opts=Array.isArray(ev.user_confirm_options)?ev.user_confirm_options:[];
var title=String(ev.user_confirm_title||"请确认");
var multi=!!ev.user_confirm_multi;
var confirmEndpoint=String(ev.user_confirm_endpoint||"");
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
if(confirmEndpoint){
 if(pickSingle<0||pickSingle>=opts.length)return "";
 return String(opts[pickSingle]||"");
}
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
if(!confirmEndpoint)addRow(tailIdx,"",true);
syncRows();
body.appendChild(btns);
var act=document.createElement("div");act.className="user-confirm-actions";
var cancel=document.createElement("button");cancel.type="button";cancel.className="mode-plus uc-cancel";cancel.textContent="取消";
var ok=document.createElement("button");ok.type="button";ok.className="mode-plus uc-ok is-primary";ok.textContent="确认";
act.appendChild(cancel);act.appendChild(ok);body.appendChild(act);
card.appendChild(body);wrap.appendChild(card);msgs.appendChild(wrap);userConfirmCardHost=wrap;bindConfirmationCard(wrap,ev,toolRow);scrollMsgsToBottom();
var submitUserConfirm=async function(finalTxt){
  var choice=confirmEndpoint?{choice:finalTxt==="同意"?"agree":"reject"}:{confirm:finalTxt};
  var result=await submitConfirmation(wrap,confirmEndpoint||"/api/chat/user-confirm",choice);
  if(result&&toolRow){
    chatToolSetRowStatus(toolRow,finalTxt?"done":"bad");
    chatToolSetResultText(toolRow,finalTxt||"用户取消了这次确认（未作答）");
  }
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
userConfirmBlocking=true;
if(_sendBtn())_sendBtn().disabled=false;
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
card.appendChild(body);wrap.appendChild(card);msgs.appendChild(wrap);userConfirmCardHost=wrap;bindConfirmationCard(wrap,ev,toolRow);scrollMsgsToBottom();
var submitApproval=async function(agreed){
  var result=await submitConfirmation(wrap,"/api/chat/user-confirm",{approval:agreed?"agree":"reject"});
  if(result&&toolRow){
    var aid=String(result.approval_id||"").trim();
    chatToolSetRowStatus(toolRow,"done");
    chatToolSetResultText(toolRow,agreed?(aid?"同意\n"+aid:"同意"):"不同意");
  }
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
