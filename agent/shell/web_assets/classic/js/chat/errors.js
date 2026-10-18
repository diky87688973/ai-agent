/* chat/errors.js —— 请求错误文案：HTTP 状态与网关错误的可读说明。
 *
 * 经典界面的**同作用域模块**：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 */
function formatHttpError(status, bodyText, kind){
var code=Number(status)||0;
var server="";
try{
var j=JSON.parse(String(bodyText||""));
if(j&&j.error!=null){
server=typeof j.error==="string"?String(j.error).trim():String((j.error&&j.error.message)||j.error).trim();
}
}catch(e){}
if(code===409)return "会话仍在执行中，请稍后再试。";
var deepseek={
400:"请求格式无效，请检查请求体后重试。",
401:"认证失败，请检查 API Key。",
402:"余额不足，请充值后重试。",
422:"请求参数无效，请检查参数后重试。",
429:"请求过于频繁，请稍后再试。",
500:"模型服务端错误，请稍后再试。",
503:"模型服务端繁忙，请稍后再试。"
};
if(deepseek[code])return deepseek[code];
var label=kind?String(kind):"请求";
if(server)return label+"失败："+server;
if(code===404)return label+"失败：资源不存在。";
return label+"失败（HTTP "+code+"）。";
}
