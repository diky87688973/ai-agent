/* chat/composer-layout.js —— 输入框上方组件的公共布局。 */
(function () {
  "use strict";

  function byId(id) {
    return document.getElementById(id);
  }

  function syncComposerColumns() {
    var left = byId("composerLeft");
    var parent = left ? left.closest(".composer-above") : null;
    if (!left || !parent) return;
    var queue = byId("chatQueue");
    var draft = byId("queueDraft");
    var speak = byId("aiSpeakSlot");
    var leftVisible = !!(
      (queue && !queue.classList.contains("hidden")) ||
      (draft && !draft.classList.contains("hidden")) ||
      (speak && speak.querySelector(".ai-speak-player:not([hidden])"))
    );
    var subagent = byId("subagentPanel");
    var taskPanel = byId("bgTaskPanel");
    var taskVisible = !!(
      (taskPanel && !taskPanel.classList.contains("hidden")) ||
      (subagent && !subagent.classList.contains("hidden"))
    );
    left.classList.toggle("is-empty", !leftVisible);
    parent.classList.toggle("has-empty-left", !leftVisible);
    parent.classList.toggle("has-no-task", !taskVisible);
  }

  window.syncComposerColumns = syncComposerColumns;

  if (window.MutationObserver) {
    var observer = new MutationObserver(syncComposerColumns);
    ["chatQueue", "queueDraft", "aiSpeakSlot", "subagentPanel", "bgTaskPanel"].forEach(function (id) {
      var node = byId(id);
      if (node) {
        observer.observe(node, {
          attributes: true,
          childList: true,
          subtree: true,
          attributeFilter: ["class", "hidden", "style"]
        });
      }
    });
    window.addEventListener("beforeunload", function () { observer.disconnect(); });
  }

  syncComposerColumns();
})();
