(function () {
  "use strict";
  var v = window.aiAgentVisualization;
  function flow(host, doc, state) {
    var ids = new Map(), lines = ["flowchart LR"];
    doc.data.nodes.forEach(function (node, i) {
      if (typeof node.label !== "string" || node.label.length > 160) throw new Error("无效的节点标签");
      var id = "node" + i; ids.set(node.id, id);
      var label = Array.from(node.label).map(function (character) { return "#" + character.codePointAt(0) + ";"; }).join("");
      lines.push(id + '["' + label + '"]');
    });
    doc.data.edges.forEach(function (edge) {
      if (!ids.has(edge.source) || !ids.has(edge.target)) throw new Error("流程边引用不存在的节点");
      lines.push(ids.get(edge.source) + "-->" + ids.get(edge.target));
    });
    var render = v.components.get("mermaid");
    return render(host, {kind: "flow", title: doc.title, data: {code: lines.join("\n")}}).then(function () {
      var rows = v.filtered(doc.data.nodes, state, function (node) { return node.label; });
      v.chartLegend(host, rows.map(function (entry) { return {label: entry.item.label, key: entry.index,
        detail: entry.item.label + "（" + entry.item.id + "）"}; }), true);
      return doc.data.nodes.length;
    });
  }
  function table(host, doc, state) {
    var columns = doc.data.columns;
    var entries = v.filtered(doc.data.rows, state, function (row) { return columns.map(function (column) { return row[column.key]; }).join(" "); });
    if (state.sortKey) entries.sort(function (a, b) {
      var left = a.item[state.sortKey], right = b.item[state.sortKey];
      var result = typeof left === "number" && typeof right === "number"
        ? left - right : String(left == null ? "" : left).localeCompare(String(right == null ? "" : right), undefined, {numeric: true});
      return result * state.sortDirection;
    });
    var grid = v.el("table", "viz-table"), head = v.el("thead"), tr = v.el("tr");
    columns.forEach(function (column) {
      var th = v.el("th"), button = v.el("button", "viz-sort", column.label);
      button.type = "button"; button.dataset.vizSort = column.key;
      if (state.sortKey === column.key) { button.textContent += state.sortDirection === 1 ? " ↑" : " ↓"; th.setAttribute("aria-sort", state.sortDirection === 1 ? "ascending" : "descending"); }
      tr.appendChild(th); th.appendChild(button);
    });
    head.appendChild(tr); grid.appendChild(head);
    var body = v.el("tbody");
    entries.forEach(function (entry) {
      var row = v.el("tr");
      columns.forEach(function (column) { row.appendChild(v.el("td", "", entry.item[column.key] == null ? "—" : String(entry.item[column.key]))); });
      v.pick(row, entry.index, columns.map(function (column) { return column.label + "：" + String(entry.item[column.key] == null ? "—" : entry.item[column.key]); }).join("；"));
      body.appendChild(row);
    });
    grid.appendChild(body); host.appendChild(grid);
    return entries.length;
  }
  v.add("flow", flow); v.add("table", table);
})();
