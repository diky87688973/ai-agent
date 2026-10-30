/* 视觉操作 2.0：输入区眼睛按钮状态。
   只在页面加载/刷新时读一次状态；后续由插件 SSE 事件更新，不轮询。 */
(function(){
"use strict";
var PLUGIN="visual_operator_2";
var SELECTOR='[data-plugin="'+PLUGIN+'"][data-plugin-action="eye_toggle"]';
function paint(b,open){
 b.classList.add("vision-eye-btn");
 b.setAttribute("data-eye-closed",open?"0":"1");
 b.setAttribute("aria-label",open?"视觉已开启，点击闭眼":"视觉已关闭");
 b.title=open?"视觉已开启，点击闭眼":"视觉已关闭";
}
function cid(){
 var tab=(typeof getActiveTab==="function")?getActiveTab():null;
 return String((tab&&tab.id)||(typeof getActiveConversationId==="function"?getActiveConversationId():"")||"");
}
function button(){return document.querySelector(SELECTOR);}
function setState(open){
 var b=button();
 if(!b)return;
 paint(b,open);
 b.hidden=!open;
 b.setAttribute("aria-hidden",open?"false":"true");
}
function refresh(){
 var id=cid();
 if(!id){setState(false);return;}
 var url="/api/plugin/"+PLUGIN+"/eye-consent/status?conversation_id="+encodeURIComponent(id);
 fetch(url).then(function(r){return r.json();}).then(function(data){
  setState(!!(data&&data.ok&&data.eyes_open&&String(data.owner_conversation_id||"")===id));
 }).catch(function(){setState(false);});
}
function bind(){
 if(document._visionEyeBound)return;
 document._visionEyeBound=true;
 document.addEventListener("ai-agent:plugin-event",function(ev){
  var d=ev&&ev.detail||{};
  if(String(d.plugin||"")!==PLUGIN)return;
  if(d.event==="eye_opened"){setState(String(d.conversation_id||"")===cid());}
  else if(d.event==="eye_closed"){setState(false);}
 });
 var host=document.getElementById("pluginActions");
 if(host&&!host._visionEyeObserver){
  host._visionEyeObserver=new MutationObserver(function(){
   var b=button();
   if(b&&!b.hasAttribute("data-vision-eye-ready")){
    b.setAttribute("data-vision-eye-ready","1");
    b.hidden=true;
    refresh();
   }
  });
  host._visionEyeObserver.observe(host,{childList:true});
 }
}
function init(){bind();var b=button();if(b){b.hidden=true;refresh();}}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);
else init();
})();
