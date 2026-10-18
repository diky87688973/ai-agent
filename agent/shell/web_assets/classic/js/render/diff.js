/* render/diff.js —— diff 渲染与滚动辅助：行级 diff、统一 diff 行样式。
 *
 * 经典界面的**同作用域模块**：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
function linesDiff(oldT,newT){
const A=String(oldT??"").split("\n");
const B=String(newT??"").split("\n");
const out=[];
let i=0,j=0;
while(i<A.length||j<B.length){
if(i<A.length&&j<B.length&&A[i]===B[j]){out.push({t:" ",l:A[i]});i++;j++;}
else if(j<B.length&&(i>=A.length||A[i]!==B[j])){out.push({t:"+",l:B[j]});j++;}
else if(i<A.length){out.push({t:"-",l:A[i]});i++;}
else{out.push({t:"+",l:B[j]});j++;}
}
return out;}
function renderDiffRows(container,oldT,newT){
container.innerHTML="";
for(const r of linesDiff(oldT,newT)){
const d=document.createElement("div");
if(r.t==="-")d.className="d-del";
else if(r.t==="+")d.className="d-add";
else d.className="d-eq";
d.innerHTML=diffRowInnerHtml(r);
container.appendChild(d);
}}
function unifiedDiffRowClass(raw){
var s=String(raw||"");
if(s.startsWith("---"))return "d-meta";
if(s.startsWith("+++"))return "d-meta";
if(s.indexOf("@@")===0)return "d-meta";
if(s.startsWith("+"))return "d-add";
if(s.startsWith("-"))return "d-del";
return "d-eq";}
function renderUnifiedDiffRows(container,lines){
container.innerHTML="";
if(!Array.isArray(lines))return;
for(var i=0;i<lines.length;i++){
var L=lines[i]==null?"":String(lines[i]);var cls=unifiedDiffRowClass(L);
var el=document.createElement("div");
el.className=cls;
if(cls==="d-meta"){el.textContent=L;}
else if(L.charAt(0)==="-"){el.innerHTML=diffRowInnerHtml({t:"-",l:L.substring(1)});}
else if(L.charAt(0)==="+"){el.innerHTML=diffRowInnerHtml({t:"+",l:L.substring(1)});}
else{el.innerHTML=diffRowInnerHtml({t:" ",l:L.replace(/^\s/,"")});}
container.appendChild(el);}}
// 全局滚动代理 — document 捕获阶段统一处理所有 scroll，无需对元素逐个注册
(function(){
  document.addEventListener("scroll",function(e){
    var el=e.target;
    if(!el||el.nodeType!==1)return;
    // 程序化滚动（scrollToBottom发起的）→ 不设免疫期
    if(el._ascrollPG){el._ascrollPG=false;return;}
    // 用户手动滚动 → 刷新免疫期，同时根据当前位置设跟随开关
    el._ascrollTM=Date.now();
    if(el.scrollHeight-el.scrollTop-el.clientHeight>60){
      el._ascrollStop=true;
    }else{
      el._ascrollStop=false;
    }
  },true);
})();

function scrollToBottom(el,force){
  if(!el)return;
  // force：初始化强制滚动，跳过所有检查
  if(force){
    el.scrollTop=el.scrollHeight;
    return;
  }
  // 200ms免疫期：避免与用户主动滚动竞争控制权
  if(el._ascrollTM&&Date.now()-el._ascrollTM<200)return;
  // _ascrollStop===true表示已取消跟随；false/undefined均表示跟随
  if(el._ascrollStop===true)return;
  // 设程序化滚动标记，scroll事件处理器跳过免疫期
  el._ascrollPG=true;
  el.scrollTop=el.scrollHeight;
}
function isNearBottom(el,threshold=60){
  if(!el) return true;
  return el.scrollHeight-el.scrollTop-el.clientHeight<threshold;
}
function scrollMsgsToBottom(){scrollToBottom(msgs);}
function scrollMsgsToBottomAfterLayout(){scrollToBottomAfterLayout(msgs,true);}
function calcDiffStats(oldT,newT){var A=String(oldT??'').split('\n'),B=String(newT??'').split('\n');var a=0,d=0,i=0,j=0;while(i<A.length||j<B.length){if(i<A.length&&j<B.length&&A[i]===B[j]){i++;j++;}else if(j<B.length&&(i>=A.length||A[i]!==B[j])){a++;j++;}else if(i<A.length){d++;i++;}else{a++;j++;}}return {add:a,del:d};}
function diffLabel(s){return(s.del>0?' <span style="color:#f48771">-'+s.del+'</span>':'')+(s.add>0?' <span style="color:#89d185">+'+s.add+'</span>':'');}
function diffLabelPlain(s){return(s.del>0?' -'+s.del:'')+(s.add>0?' +'+s.add:'');}
