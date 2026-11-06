(function () {
  "use strict";
  var v = window.aiAgentVisualization;
  function shares(host, doc, state, context) {
    var entries = v.filtered(doc.data.items, state, function (item) { return item.label; });
    if (!entries.length) return 0;
    var total = entries.reduce(function (sum, entry) { return sum + entry.item.value; }, 0);
    if (!(total > 0)) { host.appendChild(v.el("p", "viz-empty", "筛选结果的总量为零")); return entries.length; }
    var rows = entries.map(function (entry) {
      var item = entry.item, value = v.format(item.value) + " · " + v.percent(item.value / total * 100);
      return {label: item.label, detail: item.label + "：" + value, value: value, key: entry.index, color: v.colors[entry.index % 8]};
    });
    var data = entries.map(function (entry, i) {
      return {name: entry.item.label, value: entry.item.value, detail: rows[i].detail, itemStyle: {color: rows[i].color}};
    });
    var option, height, text = getComputedStyle(host).getPropertyValue("--viz-text").trim();
    if (doc.kind === "donut") {
      height = 260;
      option = {title: {text: v.format(total), subtext: "合计", left: "center", top: "40%", itemGap: 8,
        textStyle: {fontSize: 26, fontWeight: 600, color: text}, subtextStyle: {fontSize: 12}},
        series: [{type: "pie", radius: ["60%", "80%"], label: {show: false},
          emphasis: {scale: false}, selectedMode: false, data: data}]};
    } else {
      height = 56;
      var visible = data.filter(function (item) { return item.value > 0; });
      visible.forEach(function (item, i) {
        item.itemStyle.borderRadius = [i === 0 ? 4 : 0, i === visible.length - 1 ? 4 : 0,
          i === visible.length - 1 ? 4 : 0, i === 0 ? 4 : 0];
      });
      option = {grid: {left: 0, right: 0, top: 4, bottom: 30}, xAxis: {type: "value", show: false, max: total},
        yAxis: {type: "category", show: false, data: [""]},
        series: data.map(function (item) { return {name: item.name, type: "bar", stack: "total", barWidth: 16,
          emphasis: {disabled: true}, data: [item]}; }),
        title: {text: "总计 " + v.format(total), right: 0, bottom: 0, textStyle: {fontSize: 12, fontWeight: 400, color: text}}};
    }
    v.chartLegend(host, rows, false);
    return v.chart(host, doc, context, option, height, entries.length);
  }
  function bar(host, doc, state, context) {
    var entries = v.filtered(doc.data.items, state, function (item) { return item.label; });
    if (!entries.length) return 0;
    var rows = entries.map(function (entry) { return {label: entry.item.label, key: entry.index,
      detail: entry.item.label + "：" + v.format(entry.item.value), color: v.colors[entry.index % 8]}; });
    var option = {grid: {left: 0, right: 50, top: 12, bottom: 8, containLabel: true},
      xAxis: {type: "value"}, yAxis: {type: "category", inverse: true, data: rows.map(function (row) { return row.label; }),
        axisLabel: {width: 130, overflow: "truncate"}},
      series: [{type: "bar", barWidth: 18, label: {show: true, position: "right", formatter: function (p) { return v.format(p.value); }},
        emphasis: {disabled: true}, data: entries.map(function (entry, i) {
          return {value: entry.item.value, detail: rows[i].detail, itemStyle: {color: rows[i].color, borderRadius: 4}};
        })}]};
    v.chartLegend(host, rows, true);
    return v.chart(host, doc, context, option, Math.max(130, entries.length * 40 + 40), entries.length);
  }
  function line(host, doc, state, context) {
    var entries = v.filtered(doc.data.series, state, function (item) { return item.label; });
    if (!entries.length) return 0;
    var rows = [], option = {grid: {left: 0, right: 16, top: 20, bottom: 12, containLabel: true},
      xAxis: {type: "category", boundaryGap: false, data: doc.data.labels}, yAxis: {type: "value", scale: true},
      series: entries.map(function (entry) {
        return {name: entry.item.label, type: "line", symbolSize: 7, lineStyle: {width: 2.5},
          itemStyle: {color: v.colors[entry.index % 8]}, emphasis: {disabled: true},
          data: entry.item.values.map(function (value, i) {
            var detail = entry.item.label + " · " + doc.data.labels[i] + "：" + v.format(value);
            rows.push({label: entry.item.label + " · " + doc.data.labels[i], detail: detail, value: v.format(value),
              color: v.colors[entry.index % 8], key: entry.index + ":" + i});
            return {value: value, detail: detail};
          })};
      })};
    v.chartLegend(host, entries.map(function (entry) { return {label: entry.item.label, detail: entry.item.label,
      color: v.colors[entry.index % 8], key: "series-" + entry.index}; }), false);
    v.chartLegend(host, rows, true);
    return v.chart(host, doc, context, option, 300, entries.length);
  }
  v.add("proportion", shares); v.add("donut", shares); v.add("bar", bar); v.add("line", line);
})();
