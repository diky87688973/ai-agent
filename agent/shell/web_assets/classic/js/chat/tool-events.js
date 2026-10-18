/* chat/tool-events.js —— 本轮结束收尾：重置步骤与运行态。
 *
 * 经典界面的**同作用域模块**：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
function resetSteps(){resetTurnState();stepSeq=0;}

function onToolEnd(ev){const tid=String(ev.tool_call_id!=null?ev.tool_call_id:"").trim();
const o=tid&&toolOpen.get(tid);if(!o)return;
if(o.fileSpan&&o.fileSpan.parentNode){try{o.fileSpan.parentNode.removeChild(o.fileSpan);}catch(_e2){}}o.fileSpan=null;
if(o.spinWrap&&o.spinWrap.parentNode){o.spinWrap.parentNode.removeChild(o.spinWrap);}o.spinWrap=null;
lastAnalysisTail=analysisFollowupPhrase(o.script,o.args||{});
const ok=!!ev.ok;o.tag.innerHTML="";
o.tag.textContent="进行中";
o.tag.className="tag tag-run";
/* **立即写终态标签**。
   若把标签 push 进 `pendingToolTags`、等 `llm_done` 才 flush，
   一轮里多个工具时，已结束的工具会一直显示「进行中」直到整轮结束。
   `ok` 来自真实的工具结果（`tool_end.ok`），此刻就能定终态。 */
o.tag.textContent=(!!ok||!!ev.user_confirm_required||!!ev.approval_required)?"Done":"Fail";
o.tag.className="tag "+((!!ok||!!ev.user_confirm_required||!!ev.approval_required)?"ok":"bad");
if(ev.user_confirm_required||ev.approval_required){o.tag.textContent="待确认";o.tag.className="tag tag-run";}
o.resLb.style.display="block";o.resPb.style.display="block";if(ev.user_confirm_required){try{var _pj=JSON.parse(ev.preview||"{}");var _em=_pj&&_pj.error&&_pj.error.message?String(_pj.error.message):"";var _em2=_em.indexOf("\n\n--help:")>=0?_em.split("\n\n--help:")[0].trim():_em;var slim={ok:_pj.ok,data:_pj.data,error:_pj.error?{code:_pj.error.code,type:_pj.error.type,message:_em2,hint:_pj.error.hint,retryable:_pj.error.retryable}:null};o.resPb.textContent=JSON.stringify(slim,null,2);}catch(e){o.resPb.textContent=ev.preview||"";}}else{var _rawPrev=String(ev.preview||"").trim();if(!_rawPrev&&!ok&&ev.error){o.resPb.textContent=typeof chatToolFailPreview==="function"?chatToolFailPreview(ev.error):JSON.stringify({ok:false,error:String(ev.error)},null,2);}else{try{var _pj2=JSON.parse(_rawPrev||"{}");o.resPb.textContent=JSON.stringify(_pj2,null,2);}catch(e){o.resPb.textContent=_rawPrev||"";}}}
fillToolPreview(o,ev);
/* diff 预览画到**对话区**（步骤卡的预览槽放不下、默认也收起）。
   放在这里而不是调用方：实时（tool_end 帧）与刷新重放（走 renderHistoryToolItem）
   都经过 onToolEnd，所以两条路必然一致，也不会重复画。 */
renderDiffBubbleFromFacts(o.script||ev.script,ev.preview);
// 预览结果含 confirm_id：记入缓存，供 confirm_id 提交时展示文件名（与预览/review 同策略，不依赖额外事件字段）
try{var _cp=typeof ev.preview==="string"?JSON.parse(ev.preview):ev.preview;_cp=_cp&&_cp.data;_cp=_cp&&_cp.confirm_id?_cp:null;}catch(_cpE){_cp=null;}
if(_cp){
var _cpPath=String((o.args&&(o.args.path||o.args.dest_path||o.args.source_path))||(_cp.path||_cp.dest_path||_cp.source_path)||"").trim();
if(_cpPath){window.confirmPathCache=window.confirmPathCache||{};window.confirmPathCache[String(_cp.confirm_id).trim()]=_cpPath;}}
try{var _pp=typeof ev.preview==="string"?JSON.parse(ev.preview):ev.preview;var _dd=_pp&&_pp.data||null;var _so=_dd&&typeof _dd.stdout==="string"?_dd.stdout:"";var _se=_dd&&typeof _dd.stderr==="string"?_dd.stderr:"";var _shown=_so;if(isStreamOutputToolScript(o.script)&&_se.trim()){_shown=_so.trim()?(_so.replace(/\s*$/,"")+"\n"+_se):_se;}if(_shown&&String(_shown).trim()){if(o.liveOutPre&&o.liveOutPre!==o.chatRunOutPre)o.liveOutPre.textContent=_shown;updateChatRunCardOutput(o,_shown);}}catch(_e3){}
// file_undo：从结果数据补充路径到标题
try{var _fuP=typeof ev.preview==="string"?JSON.parse(ev.preview):ev.preview;_fuP=_fuP&&_fuP.data;}catch(_fuE){_fuP=null;}
if(_fuP&&o.script&&o.script.toLowerCase().indexOf("file_undo")>=0){
var _fuAct=String(o.args&&o.args.action||_fuP.action||"").trim();
var _fuPath=_fuP.restored_path||_fuP.path||"";
if(_fuPath&&!_fuPath.endsWith("\\")&&!_fuPath.endsWith("/")){
var _fn=pathLeaf(_fuPath)||"";
if(_fn){var _card=findStepCardForToolCall(tid);if(_card){var _tx=_card.querySelector(".step-title-wrap");if(_tx){var _txM=_tx.querySelector(":scope > span:first-child");var _txF=_tx.querySelector(":scope > .step-fname");var _ts="";var _mid=String(o.args&&o.args.mod_id||"").trim();/* 版本目录名的形状由 file_safety._version_dir_name 产出；按形状取，不数段数 */if(_mid){var _mv=/_(\d{6})_\d{3}_\d{4}_[0-9a-z]+$/.exec(_mid);if(_mv)_ts=_mv[1].slice(0,2)+":"+_mv[1].slice(2,4)+":"+_mv[1].slice(4,6);}if(_txM&&!_txF){_txF=document.createElement("span");_txF.className="step-fname";_tx.appendChild(_txF);}if(_txF){_txF.textContent=_fn+(_ts?" to "+_ts:"");}}}}}}
if(isStreamOutputToolScript(o.script))finalizeChatRunCard(o,ok);
if(ev.approval_required)openApprovalModalFromToolEnd(ev, o.chatToolRow);
else if(ev.user_confirm_required)openUserConfirmModalFromToolEnd(ev, o.chatToolRow);
/* 模型改了目标（goal 工具）→ 立即同步按钮，不必等用户刷新 */
if(ok&&o.script==="goal"){var _gp=null;try{_gp=JSON.parse(ev.preview||"{}").data||null;}catch(_e){}
/* `delete` 返回的是 {deleted:true} 而不是 {goal:...}：只认 goal 键的话，
   删完目标按钮会停在"进行中"。两种形状都要处理。 */
if(_gp&&Object.prototype.hasOwnProperty.call(_gp,"goal")){_goalInfo=_gp.goal;updateAutoToggleUI();}
else if(_gp&&_gp.deleted){_goalInfo=null;updateAutoToggleUI();}}
fillChatToolResult(o,ev);
toolOpen.delete(tid);}

/* 把 HTTP 失败收成对话区可读文案。
   本服务：409（会话忙）。
   DeepSeek 模型侧：400/401/402/422/429/500/503（官方 Error Codes）。
   其余：优先响应 JSON 的 error，再兜底状态码。 */
