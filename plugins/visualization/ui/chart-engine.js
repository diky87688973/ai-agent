(function () {
  "use strict";
  var v = window.aiAgentVisualization, loading = null, cancel = null, disposed = false;
  var instances = new Set();
  function load() {
    if (disposed) return Promise.reject(new Error("组件已卸载"));
    if (loading) return loading;
    loading = new Promise(function (resolve, reject) {
      var script = document.createElement("script");
      script.src = window.aiAgentPlugins.for("visualization").url("_asset/ui/vendor/echarts/echarts.min.js");
      script.setAttribute("data-plugin-script", "visualization");
      script.onload = function () {
        cancel = null;
        if (window.echarts) resolve(window.echarts);
        else { loading = null; reject(new Error("离线图表库未就绪")); }
      };
      script.onerror = function () { cancel = null; script.remove(); loading = null; reject(new Error("离线图表库无法加载")); };
      cancel = function () { script.onload = script.onerror = null; script.remove(); reject(new Error("组件已卸载")); };
      document.head.appendChild(script);
    });
    return loading;
  }
  v.disposeCharts = function () {
    disposed = true;
    if (cancel) cancel();
    Array.from(instances).forEach(function (dispose) { dispose(); });
    loading = null; window.echarts = undefined;
  };
  v.chartLegend = function (host, rows, editingOnly) {
    var legend = v.el("div", "viz-legend" + (editingOnly ? " viz-edit-data" : ""));
    rows.forEach(function (row, i) {
      var item = v.el("div", "viz-legend-item"), dot = v.el("span", "viz-dot");
      dot.style.backgroundColor = row.color || v.colors[i % 8];
      item.append(dot, v.el("span", "", row.label));
      if (row.value) item.appendChild(v.el("b", "", row.value));
      legend.appendChild(v.pick(item, row.key === undefined ? i : row.key, row.detail));
    });
    host.appendChild(legend);
  };
  v.chart = async function (host, doc, context, option, height, count) {
    var lib = await load();
    if (disposed) throw new Error("组件已卸载");
    var node = v.el("div", "viz-echart");
    node.dataset.renderer = "echarts"; node.style.height = height + "px";
    node.setAttribute("role", "img"); node.setAttribute("aria-label", doc.title + "。" + doc.summary);
    host.prepend(node);
    var style = getComputedStyle(host), text = style.getPropertyValue("--viz-text").trim();
    var muted = style.getPropertyValue("--viz-muted").trim(), line = style.getPropertyValue("--viz-line").trim();
    option.animation = false; option.color = v.colors;
    option.textStyle = {fontFamily: style.fontFamily, fontSize: 13, color: text};
    option.tooltip = {trigger: "item", renderMode: "richText", confine: true,
      backgroundColor: style.getPropertyValue("--viz-raised").trim(), borderColor: line, textStyle: {fontSize: 12, color: text},
      formatter: function (params) { return params.data && params.data.detail || params.seriesName || ""; }};
    if (option.title) option.title.subtextStyle = Object.assign({color: muted}, option.title.subtextStyle);
    option.series.forEach(function (series) {
      if (series.label) series.label = Object.assign({color: text, fontSize: 12, textBorderWidth: 0}, series.label);
    });
    [option.xAxis, option.yAxis].forEach(function (axis) {
      if (!axis) return;
      axis.axisLabel = Object.assign({color: muted, fontSize: 12, hideOverlap: true}, axis.axisLabel);
      axis.axisLine = {show: false}; axis.axisTick = {show: false};
      axis.splitLine = {show: axis.type === "value", lineStyle: {color: line}};
    });
    var chart = lib.init(node, null, {renderer: "svg", width: Math.max(240, node.clientWidth), height: height});
    var stopped = false, frame = null, observer;
    function dispose() {
      if (stopped) return;
      stopped = true;
      if (observer) observer.disconnect();
      if (frame !== null) cancelAnimationFrame(frame);
      instances.delete(dispose); chart.dispose();
    }
    try {
      chart.setOption(option);
      chart.on("click", function (params) {
        if (stopped || context.mode.get() !== "edit" || !params.data || typeof params.data.detail !== "string") return;
        node.dispatchEvent(new CustomEvent("visualization:select", {bubbles: true, detail: params.data.detail}));
      });
      observer = new ResizeObserver(function () {
        if (frame !== null) cancelAnimationFrame(frame);
        frame = requestAnimationFrame(function () {
          frame = null;
          if (!stopped && node.clientWidth > 0) chart.resize({width: node.clientWidth});
        });
      });
      observer.observe(node); instances.add(dispose);
      return {count: count, dispose: dispose};
    } catch (error) { dispose(); throw error; }
  };
})();
