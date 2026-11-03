/* AI扮演工具卡：标题显示工具名，摘要显示 msg，详情沿用默认请求/响应报文。 */
(function () {
  "use strict";

  if (window.__aiCosplayToolViewRegistered) return;
  var register = (window.aiAgentChatTools && window.aiAgentChatTools.register)
    || (typeof registerChatToolView === "function" ? registerChatToolView : null);
  if (!register) return;
  window.__aiCosplayToolViewRegistered = true;

  function message(o) {
    return String(argGet(o && o.args, "msg") || "").trim();
  }

  register({
    match: function (script) {
      var name = chatToolName(script);
      return name === "ai_speek" || name === "ai_cosplay";
    },
    title: function () { return "AI扮演"; },
    summary: function (o) { return message(o); },
    mount: function (row, o) {
      var request = addChatToolText(
        addChatToolLayer(row._body, "请求", "req"),
        JSON.stringify(o.args || {}, null, 2)
      );
      o.chatToolRes = addChatToolText(
        addChatToolLayer(row._body, "响应", "res"),
        "（等待结果…）"
      );
    },
    fill: function (row, o, ev) {
      if (o.chatToolRes) o.chatToolRes.textContent = chatToolResponseText(o, ev);
    }
  });

  if (window.aiAgentChatTools && window.aiAgentChatTools.refresh) {
    window.aiAgentChatTools.refresh();
  }
})();
