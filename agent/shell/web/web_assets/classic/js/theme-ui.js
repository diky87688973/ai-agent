/* 明暗主题。 */
(function (w) {
  "use strict";
  var KEY = "aiAgent.uiTheme";
  function get() {
    try {
      return localStorage.getItem(KEY) === "light" ? "light" : "dark";
    } catch (e) {
      return "dark";
    }
  }
  function set(t) {
    t = t === "light" ? "light" : "dark";
    try {
      localStorage.setItem(KEY, t);
    } catch (e) {}
    document.documentElement.setAttribute("data-ui-theme", t);
    syncButtons();
  }
  function toggle() {
    set(get() === "light" ? "dark" : "light");
  }
  function apply() {
    document.documentElement.setAttribute("data-ui-theme", get());
    syncButtons();
  }
  function syncButtons() {
    var dark = get() === "dark";
    var label = dark ? "白天模式" : "夜间模式";
    var title = dark ? "切换为白天界面" : "切换为夜间界面";
    ["hdrThemeBtn", "immThemeBtn"].forEach(function (id) {
      var b = document.getElementById(id);
      if (b) {
        b.textContent = label;
        b.title = title;
      }
    });
  }
  w.themeUi = { get: get, set: set, toggle: toggle, apply: apply, syncButtons: syncButtons };
})(window);

/* 全页：消幽灵插入符，但保留拖选复制。 */
(function () {
  "use strict";

  function nodeEl(node) {
    if (!node) return null;
    return node.nodeType === 3 ? node.parentElement : node;
  }

  function isEditableNode(node) {
    var el = nodeEl(node);
    if (!el || !el.closest) return false;
    if (el.closest('textarea, select, [contenteditable="true"], [contenteditable=""]')) return true;
    var inp = el.closest("input");
    if (!inp) return false;
    var t = String(inp.type || "text").toLowerCase();
    return (
      t === "text" ||
      t === "search" ||
      t === "password" ||
      t === "email" ||
      t === "url" ||
      t === "tel" ||
      t === "number" ||
      t === ""
    );
  }

  document.addEventListener(
    "mousedown",
    function (ev) {
      if (isEditableNode(ev.target)) return;
      var ae = document.activeElement;
      if (ae && isEditableNode(ae)) ae.blur();
    },
    true
  );

  document.addEventListener(
    "mouseup",
    function (ev) {
      if (isEditableNode(ev.target)) return;
      if (document.activeElement && isEditableNode(document.activeElement)) return;
      var sel = window.getSelection && window.getSelection();
      if (!sel || !sel.isCollapsed || !sel.anchorNode) return;
      if (isEditableNode(sel.anchorNode)) return;
      sel.removeAllRanges();
    },
    false
  );
})();
