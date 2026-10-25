/* Skills 工具卡视图：skills action=read。
   经开屏脚本贡献预载；壳层不点名本工具。 */
(function () {
  "use strict";

  var register = (window.aiAgentChatTools && window.aiAgentChatTools.register)
    || (typeof registerChatToolView === "function" ? registerChatToolView : null);
  if (!register) return;

  function skillName(o) {
    return String(argGet(o && o.args, "name") || "").trim();
  }

  function skillContent(ev) {
    var j = chatToolParsePreview(ev);
    if (!j) return null;
    var d = j.data && typeof j.data === "object" ? j.data : j;
    return typeof d.content === "string" ? d.content : null;
  }

  register({
    match: function (script, args) {
      return chatToolName(script) === "skills"
        && String(argGet(args, "action") || "").toLowerCase() === "read";
    },
    title: function () { return "加载 Skills"; },
    summary: function (o) { return skillName(o) || "（未指定 Skills）"; },
    mount: function (row, o) {
      var pane = addChatToolLayer(row._body, "", "skill");
      var box = document.createElement("div");
      box.className = "b a chat-tool-md";
      box.textContent = "（等待内容…）";
      pane.appendChild(box);
      o.chatToolSkill = box;
    },
    fill: function (row, o, ev) {
      var name = skillName(o);
      if (!name) {
        var j = chatToolParsePreview(ev);
        var d = (j && j.data) || {};
        name = String(d.name || "").trim();
      }
      if (name) chatToolSetSummary(row, name);
      var box = o.chatToolSkill;
      if (!box) return;
      if (chatToolIsFailed(ev)) { chatToolPaintFailText(box); return; }
      chatToolClearFailMark(box);
      var text = skillContent(ev);
      if (text == null) { box.textContent = ev.ok ? "（无内容）" : "（无结果）"; return; }
      if (!text) { box.textContent = "（空内容）"; return; }
      try { box.innerHTML = renderMarkdown(text); } catch (e) { box.textContent = text; }
    }
  });
})();
