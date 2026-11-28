/* AI扮演工具卡：标题显示工具名，摘要与详情显示 msg；请求/响应由框架收进「查看报文」。 */
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
      o.chatSpeakPre = addChatToolText(
        addChatToolLayer(row._body, "", "out"),
        message(o) || "（无播报内容）"
      );
    },
    fill: function (row, o, ev) {
      if (!o.chatSpeakPre || ev.user_confirm_required) return;
      if (chatToolIsFailed(ev)) {
        var cur = String(o.chatSpeakPre.textContent || "");
        if (!cur.trim() || cur === "（无播报内容）") chatToolPaintFailText(o.chatSpeakPre);
        return;
      }
      chatToolClearFailMark(o.chatSpeakPre);
    }
  });

  if (window.aiAgentChatTools && window.aiAgentChatTools.refresh) {
    window.aiAgentChatTools.refresh();
  }
})();
