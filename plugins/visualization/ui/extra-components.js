(function () {
  "use strict";
  var v = window.aiAgentVisualization, serial = 0;
  var labels = {waiting: "等待", running: "运行", succeeded: "成功", failed: "失败", cancelled: "取消"};
  var colors = {waiting: "#b3bfd4", running: "#4562f5", succeeded: "#18b998", failed: "#f26d83", cancelled: "#9965f4"};
  function progress(host, doc, state) {
    var entries = v.filtered(doc.data.items, state, function (item) { return item.label; });
    entries.forEach(function (entry) {
      var item = entry.item, percent = 100 * item.value / item.total, row = v.el("div", "viz-progress");
      var label = v.el("div", "viz-progress-label"), meta = v.el("div", "viz-progress-meta");
      meta.append(v.el("span", "", v.format(item.value) + " / " + v.format(item.total)), v.el("strong", "", v.percent(percent)));
      label.append(v.el("span", "viz-item-name", item.label), meta);
      var track = v.el("div", "viz-track"), fill = v.el("div", "viz-progress-fill");
      track.setAttribute("role", "progressbar"); track.setAttribute("aria-label", item.label);
      track.setAttribute("aria-valuemin", "0"); track.setAttribute("aria-valuemax", String(item.total));
      track.setAttribute("aria-valuenow", String(item.value)); fill.style.width = percent + "%";
      track.appendChild(fill); row.append(label, track);
      host.appendChild(v.pick(row, entry.index, item.label + "：" + v.format(item.value) + "/" + v.format(item.total)));
    });
    return entries.length;
  }
  function period(host, doc, state, context) {
    var source = doc.kind === "gantt" ? doc.data.tasks : doc.data.items;
    var entries = v.filtered(source, state, function (item) { return item.label; });
    if (!entries.length) return 0;
    var low = Math.min(...entries.map(function (entry) { return entry.item.start; }));
    var high = Math.max(...entries.map(function (entry) { return entry.item.end; }));
    var rows = entries.map(function (entry) {
      var item = entry.item, value = v.format(item.start) + "–" + v.format(item.end) + " " + doc.data.unit + " · " + labels[item.status];
      return {label: item.label, detail: item.label + "：" + value, value: value, key: entry.index, color: colors[item.status]};
    });
    var option = {grid: {left: 0, right: 52, top: 12, bottom: 36, containLabel: true},
      xAxis: {type: "value", min: 0, max: high - low || 1, name: doc.data.unit, nameLocation: "middle", nameGap: 28,
        axisLabel: {formatter: function (value) { return v.format(value + low); }}},
      yAxis: {type: "category", inverse: true, data: rows.map(function (row) { return row.label; }), axisLabel: {width: 130, overflow: "truncate"}},
      series: [{type: "bar", stack: "period", silent: true, itemStyle: {color: "transparent"}, emphasis: {disabled: true},
        data: entries.map(function (entry) { return entry.item.start - low; })},
        {type: "bar", stack: "period", barWidth: 18, barMinHeight: 2, emphasis: {disabled: true},
          label: {show: true, position: "right", formatter: function (params) { return labels[entries[params.dataIndex].item.status]; }},
          data: entries.map(function (entry, i) { return {value: entry.item.end - entry.item.start,
            detail: rows[i].detail, itemStyle: {color: rows[i].color, borderRadius: 4}}; })}]};
    v.chartLegend(host, rows, true);
    return v.chart(host, doc, context, option, Math.max(150, entries.length * 40 + 65), entries.length);
  }
  function timeline(host, doc, state) {
    var entries = v.filtered(doc.data.events, state, function (item) { return item.label + " " + item.detail; });
    entries.sort(function (a, b) { return a.item.at - b.item.at; });
    var list = v.el("ol", "viz-timeline");
    entries.forEach(function (entry) {
      var item = entry.item, row = v.el("li");
      row.append(v.el("span", "viz-time", v.format(item.at) + " " + doc.data.unit), v.el("strong", "", item.label), v.el("p", "", item.detail));
      list.appendChild(v.pick(row, entry.index, item.label + " · " + v.format(item.at) + " " + doc.data.unit + " · " + item.detail));
    });
    host.appendChild(list); return entries.length;
  }
  function controls(host, doc, state) {
    state.controls = state.controls || {};
    var entries = v.filtered(doc.data.fields, state, function (field) { return field.label; });
    entries.forEach(function (entry) {
      var field = entry.item, row = v.el("div", "viz-control"), value = Object.prototype.hasOwnProperty.call(state.controls, field.id) ? state.controls[field.id] : field.value;
      var label = v.el("label", "viz-control-label", field.label), inputId = "viz-control-" + (++serial);
      row.appendChild(label);
      if (field.type === "tabs") {
        var group = v.el("div", "viz-tabs"); group.setAttribute("role", "tablist"); group.setAttribute("aria-label", field.label);
        label.id = inputId; group.setAttribute("aria-labelledby", inputId);
        field.options.forEach(function (option) {
          var button = v.el("button", "viz-button", option.label); button.type = "button";
          button.dataset.vizTab = field.id; button.dataset.vizValue = option.value;
          button.setAttribute("role", "tab"); button.setAttribute("aria-selected", String(value === option.value));
          button.tabIndex = value === option.value ? 0 : -1; group.appendChild(button);
        });
        row.appendChild(group);
      } else {
        var input = v.el(field.type === "select" ? "select" : "input");
        input.id = inputId; label.htmlFor = inputId;
        input.dataset.vizControl = field.id; input.setAttribute("aria-label", field.label);
        if (field.type === "select") field.options.forEach(function (option) { var item = v.el("option", "", option.label); item.value = option.value; input.appendChild(item); });
        else input.type = field.type === "toggle" ? "checkbox" : "range";
        if (field.type === "range") {
          input.min = field.min; input.max = field.max; input.step = field.step;
          input.style.setProperty("--range-progress", ((value - field.min) / (field.max - field.min) * 100) + "%");
          var output = v.el("output", "", v.format(value)); output.htmlFor = inputId; row.appendChild(output);
        }
        if (field.type === "toggle") input.checked = Boolean(value);
        else input.value = String(value);
        if (field.type === "toggle") input.setAttribute("role", "switch");
        if (field.type === "select") { var wrap = v.el("div", "viz-select"); wrap.appendChild(input); row.appendChild(wrap); }
        else row.appendChild(input);
      }
      host.appendChild(row);
    });
    return entries.length;
  }
  v.add("progress", progress); v.add("gantt", period); v.add("waterfall", period); v.add("timeline", timeline); v.add("controls", controls);
})();
