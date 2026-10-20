/* composer/model-sync.js —— 会话级模型回填与健康检查模型同步。
 *
 * 经典界面的同作用域模块：由 `agent/shell/ui_bundle.py` 按清单顺序与其他脚本
 * 拼进同一个 `<script>`。因此这里不写 import/export，函数与变量直接对同作用域可见。
 *
 * 下拉本身由 `multi_model` 插件渲染（`#modelPickerSlot`），壳层只维护
 * 「可选清单缓存」与「当前模型」：清单用于用户点击时校验，
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
/* 会话级模型回填。
   `loadHealthModel()` 只给"全局默认模型"，而会话可能选过别的；
   它又跑在 `restoreConversationLayoutFromServer()` 之前，此刻 `activeConversationId`
   还可能不是真正要显示的那个会话 —— 那样模型会被设成默认、刷新后选择丢失。
   所以必须先恢复会话，再按那个会话取会话级设置。 */
async function loadConversationModel(){
try{
var cidNow=normalizeConversationId(activeConversationId);if(!cidNow)return;
var r=await fetch("/api/chat/ui-state?conversation_id="+encodeURIComponent(cidNow));
if(!r.ok)return;var j=await r.json();
var st=(j&&j.state)||j||{};
if(Array.isArray(st.available_models))setAllowedModels(st.available_models);
if(st.model)applyModel(st.model);
/* 模式与档位也属于会话：服务端已落盘，页面打开时按当前会话回填。
   档位回填传 `false`：这只是"把服务端的值显示出来"，不该反过来再写一次。 */
if(st.mode)applyMode(st.mode,false);
var activeTab=getActiveTab();
if(st.reasoning_effort&&typeof applyReasoningEffort==="function")applyReasoningEffort(st.reasoning_effort,false);
if(activeTab){if(st.reasoning_effort)activeTab.reasoningEffort=st.reasoning_effort;activeTab.settingsLoaded=true;}
/* 目标与模型同源：页面打开时按当前会话取一次（服务端权威）。
   与模型选择同一道理 —— 目标属于会话，不属于这个标签页。 */
if(Object.prototype.hasOwnProperty.call(st,"goal")){_goalInfo=st.goal||null;}
if(st.autonomy&&typeof st.autonomy.enabled==="boolean"){_autoEnabled=!!st.autonomy.enabled;}
updateAutoToggleUI();
}catch(e){}
}
/* 切换标签页时按目标会话回填。
   刷新后非激活标签页只剩 cid + 标题（本地布局只存这两样），`selectedModel` /
   `reasoningEffort` 是空串、`selectedMode` 是默认 auto；不看服务端的话，切过去
   会显示上一个标签页的模型与档位。`settingsLoaded` 保证每个标签页只问一次；
   请求回来时若已切走，只写回 tab 字段、不碰界面（否则会把新标签页的设置盖掉）。 */
async function syncConversationSettings(tab){
try{
var cidNow=normalizeConversationId(tab&&tab.id);if(!cidNow||tab.settingsLoaded)return;
var r=await fetch("/api/chat/ui-state?conversation_id="+encodeURIComponent(cidNow));
if(!r.ok)return;var j=await r.json();var st=(j&&j.state)||j||{};
tab.settingsLoaded=true;
if(st.model)tab.selectedModel=String(st.model);
if(st.mode)tab.selectedMode=normalizeMode(st.mode);
if(st.reasoning_effort)tab.reasoningEffort=st.reasoning_effort;
if(normalizeConversationId(activeConversationId)!==cidNow)return;
if(st.model)applyModel(tab.selectedModel);
if(st.mode)applyMode(tab.selectedMode,false);
if(st.reasoning_effort&&typeof applyReasoningEffort==="function")applyReasoningEffort(st.reasoning_effort,false);
}catch(e){}
}
/* `/health` 给的是全局默认（模型 + 档位），只用来填"会话还没回填前"的初始显示。
   会话已回填（`settingsLoaded`）时不能再拿全局默认盖它 —— 两个请求都是异步的，
   谁后到就谁生效会让切换会话偶尔退回默认值。 */
async function loadHealthModel(){
try{var r=await fetch("/health");if(!r.ok)return;var j=await r.json();if(Array.isArray(j.allowed_models))setAllowedModels(j.allowed_models);var ht=getActiveTab();var hydrated=!!(ht&&ht.settingsLoaded);if(j.max_images)window.AI_AGENT_MAX_IMAGES=Number(j.max_images)||window.AI_AGENT_MAX_IMAGES;if(j.model&&!hydrated)applyModel(j.model);if(j.reasoning_effort&&!hydrated&&typeof applyReasoningEffort==="function")applyReasoningEffort(j.reasoning_effort,false);}catch(e){}
}
