/* 插件内部的组件目录与安全 DOM 原语。 */
(function () {
  "use strict";
  var colors = ["#4562f5", "#06b6d4", "#ffae43", "#9965f4", "#ff6e88", "#27a9f4", "#24bf91", "#e875c5"];
  function el(tag, cls, value) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (value !== undefined) node.textContent = String(value);
    return node;
  }
  function pick(node, index, detail) {
    node.dataset.vizPick = String(index);
    node.dataset.vizDetail = detail;
    node.setAttribute("tabindex", "0");
    node.setAttribute("role", "button");
    node.setAttribute("aria-label", detail);
    node.title = detail;
    return node;
  }
  function filtered(items, state, label) {
    var query = state.query.trim().toLocaleLowerCase();
    return items.map(function (item, index) { return {item: item, index: index}; })
      .filter(function (entry) { return String(label(entry.item)).toLocaleLowerCase().includes(query); });
  }
  window.aiAgentVisualization = {
    components: new Map(), el: el, pick: pick, filtered: filtered,
    colors: colors,
    format: function (value) { return Number(value).toLocaleString(undefined, {maximumFractionDigits: 3}); },
    percent: function (value) { return Number(value).toLocaleString(undefined, {maximumFractionDigits: 1}) + "%"; },
    add: function (kind, draw) {
      if (this.components.has(kind)) throw new Error("重复组件：" + kind);
      this.components.set(kind, draw);
    }
  };
})();
