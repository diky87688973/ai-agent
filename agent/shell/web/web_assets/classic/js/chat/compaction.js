/* chat/compaction.js —— 上下文压缩的工具壳。 */
function compactionSummaryText(ev){
return String((ev&&(ev.summary_text||ev.summary))||"").trim();
}
function compactionCount(ev){
var n=Number(ev&&ev.compressed_count);
return isFinite(n)&&n>0?Math.floor(n):0;
}
function compactionTokens(ev){
var n=Number(ev&&ev.compressed_tokens);
return isFinite(n)&&n>0?Math.floor(n):0;
}
function compactionEventKey(ev){
if(!ev)return "";
if(ev.seq!=null&&String(ev.seq)!=="")return "seq:"+String(ev.seq);
if(ev.covered_end!=null&&String(ev.covered_end)!=="")return "covered:"+String(ev.covered_end);
return "";
}
function renderCompactionCard(ev,opts){
if(typeof showToolItems==="function"&&!showToolItems())return null;
var count=compactionCount(ev);
var tokens=compactionTokens(ev);
var summary=compactionSummaryText(ev);
var row=makeChatToolRow("上下文压缩","已压缩消息 "+count+" 条 · 约 "+tokens.toLocaleString()+" tokens");
var pane=document.createElement("div");
pane.className="chat-tool-pane chat-tool-pane--compaction";
var body=document.createElement("div");
body.className="chat-tool-md";
if(summary)body.innerHTML=renderMarkdown(summary);
else body.textContent="（无摘要正文）";
pane.appendChild(body);
row._body.appendChild(pane);
appendChatToolRow(row,opts||{});
return row;
}
function renderCompactionEvent(ev,tab){
var key=compactionEventKey(ev);
if(tab&&key){
tab.compactionSeqs=tab.compactionSeqs||Object.create(null);
if(tab.compactionSeqs[key])return null;
tab.compactionSeqs[key]=1;
}
return renderCompactionCard(ev);
}
function renderHistoryCompactionItem(it){
return renderCompactionCard(it);
}
