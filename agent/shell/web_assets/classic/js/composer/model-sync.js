/* composer/model-sync.js —— 会话级模型回填与健康检查模型同步。
 *
 * 经典界面的**同作用域模块**：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 *
 * 下拉本身由 `multi_model` 插件渲染（`#modelPickerSlot`），壳层只维护
 * 「可选清单缓存」与「当前模型」：清单用于**用户点击**时校验，
 * 服务端回填的值不再受本地清单限制（新模型可能比页面清单更新）。
 */
function setAllowedModels(list){
if(!Array.isArray(list))return;
allowedModels.splice(0,allowedModels.length);
list.forEach(function(m){
var id=String(m||"").trim();
if(id&&allowedModels.indexOf(id)<0)allowedModels.push(id);
});
}
/* **会话级模型回填**。
   `loadHealthModel()` 只给"全局默认模型"，而会话可能选过别的；
   它又跑在 `restoreConversationLayoutFromServer()` **之前**，此刻 `activeConversationId`
   还可能不是真正要显示的那个会话 —— 那样模型会被设成默认、刷新后选择丢失。
   所以必须**先恢复会话，再按那个会话取会话级设置**。 */
async function loadConversationModel(){
try{
var cidNow=normalizeConversationId(activeConversationId);if(!cidNow)return;
var r=await fetch("/api/chat/ui-state?conversation_id="+encodeURIComponent(cidNow));
if(!r.ok)return;var j=await r.json();
var st=(j&&j.state)||j||{};
if(Array.isArray(st.available_models))setAllowedModels(st.available_models);
if(st.model)applyModel(st.model);
/* 目标与模型同源：页面打开时按**当前会话**取一次（服务端权威）。
   与模型选择同一道理 —— 目标属于会话，不属于这个标签页。 */
if(Object.prototype.hasOwnProperty.call(st,"goal")){_goalInfo=st.goal||null;}
if(st.autonomy&&typeof st.autonomy.enabled==="boolean"){_autoEnabled=!!st.autonomy.enabled;}
updateAutoToggleUI();
}catch(e){}
}
async function loadHealthModel(){
try{var r=await fetch("/health");if(!r.ok)return;var j=await r.json();if(Array.isArray(j.allowed_models))setAllowedModels(j.allowed_models);if(j.model)applyModel(j.model);}catch(e){}
}
