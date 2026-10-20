/* AI说话工具卡：标题「AI说话」，摘要显示 msg，详情沿用默认请求/响应报文。 */
(function () {
  "use strict";

  if (window.__aiSpeakToolViewRegistered) return;
  var register = (window.aiAgentChatTools && window.aiAgentChatTools.register)
    || (typeof registerChatToolView === "function" ? registerChatToolView : null);
  if (!register) return;
  window.__aiSpeakToolViewRegistered = true;

  function message(o) {
    return String(argGet(o && o.args, "msg") || "").trim();
  }

  register({
    match: function (script) {
      return chatToolName(script) === "ai_speak";
    },
    title: function () { return "AI说话"; },
    summary: function (o) { return message(o); },
    mount: function (row, o) {
      var request = addChatToolText(
        addChatToolLayer(row._body, "请求", "req"),
        JSON.stringify(o.args || {}, null, 2)
      );
      request.title = message(o);
      o.chatToolRes = addChatToolText(
        addChatToolLayer(row._body, "响应", "res"),
        "（等待结果…）"
      );
      if (row._sum) row._sum.title = message(o);
    },
    fill: function (row, o, ev) {
      if (o.chatToolRes) o.chatToolRes.textContent = chatToolResponseText(o, ev);
    }
  });

  if (window.aiAgentChatTools && window.aiAgentChatTools.refresh) {
    window.aiAgentChatTools.refresh();
  }
})();
