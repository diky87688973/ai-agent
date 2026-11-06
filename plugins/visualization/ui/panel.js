(function () {
  "use strict";
  var v = window.aiAgentVisualization, shell = window.aiAgentShell, serial = 0;
  if (!v || !shell || !shell.displays) throw new Error("可视化宿主尚未装载");
  function check(doc) {
    if (!doc || !v.components.has(doc.kind) || typeof doc.title !== "string" ||
        !doc.title.trim() || doc.title.length > 120 || !doc.data || JSON.stringify(doc).length > 65536) throw new Error("无效的组件文档");
    var data = doc.data;
    function list(value, max, min) {
      if (!Array.isArray(value) || value.length < min || value.length > max) throw new Error("组件数据数量超出边界");
    }
    if (doc.kind === "flow") { list(data.nodes, 60, 1); list(data.edges, 120, 0); }
    else if (doc.kind === "line") {
      list(data.labels, 200, 1); list(data.series, 8, 1);
      data.series.forEach(function (series) { list(series.values, data.labels.length, data.labels.length); });
    } else if (doc.kind === "table") { list(data.columns, 20, 1); list(data.rows, 500, 0); }
    else if (doc.kind === "mermaid") { if (typeof data.code !== "string" || data.code.length > 16000) throw new Error("图定义过大"); }
    else if (doc.kind === "tasks") list(data.task_ids, 100, 1);
    else if (doc.kind === "controls") list(data.fields, 12, 1);
    else if (doc.kind === "timeline") list(data.events, 100, 0);
    else if (doc.kind === "gantt") list(data.tasks, 100, 0);
    else list(data.items, 100, 0);
  }
  function save(value, mime, name) {
    var url = URL.createObjectURL(new Blob([value], {type: mime}));
    var link = v.el("a"); link.href = url; link.download = name;
    link.click(); setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }
  function validState(state, doc) {
    if (!state || typeof state !== "object" || Array.isArray(state) ||
        typeof state.query !== "string" || state.query.length > 1000 || !Number.isFinite(state.zoom) ||
        state.zoom < 0.5 || state.zoom > 3 || typeof state.sortKey !== "string" ||
        [1, -1].indexOf(state.sortDirection) < 0 || typeof state.selected !== "string" || state.selected.length > 8000) return false;
    if (!Object.prototype.hasOwnProperty.call(state, "controls")) return true;
    if (doc.kind !== "controls" || !state.controls || typeof state.controls !== "object" || Array.isArray(state.controls)) return false;
    return Object.keys(state.controls).every(function (key) {
      var field = doc.data.fields.find(function (item) { return item.id === key; }), value = state.controls[key];
      if (!field) return false;
      if (field.type === "toggle") return typeof value === "boolean";
      if (field.type === "range") return Number.isFinite(value) && value >= field.min && value <= field.max &&
        Math.abs((value - field.min) / field.step - Math.round((value - field.min) / field.step)) <= 1e-8;
      return field.options.some(function (option) { return option.value === value; });
    });
  }
  function exportSvg(svg) {
    var clone = svg.cloneNode(true), source = [svg].concat(Array.from(svg.querySelectorAll("*")));
    var target = [clone].concat(Array.from(clone.querySelectorAll("*")));
    source.forEach(function (node, i) {
      var style = getComputedStyle(node);
      ["fill", "stroke", "stroke-width", "font-size", "font-family", "opacity"].forEach(function (key) { target[i].style.setProperty(key, style.getPropertyValue(key)); });
    });
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    save(new XMLSerializer().serializeToString(clone), "image/svg+xml", "visualization.svg");
  }
  function controlSelection(doc, state) {
    return doc.data.fields.map(function (item) {
      var values = state.controls || {}, selected = Object.prototype.hasOwnProperty.call(values, item.id) ? values[item.id] : item.value;
      var option = item.options && item.options.find(function (entry) { return entry.value === selected; });
      return item.label + "：" + (option ? option.label : typeof selected === "boolean" ? selected ? "开启" : "关闭" : v.format(selected));
    }).join("；");
  }
  function render(host, doc, context) {
    check(doc);
    var controller = new AbortController(), state = {query: "", zoom: 1, sortKey: "", sortDirection: 1, selected: ""};
    var saved = context.state.load();
    if (saved.value !== null && saved.value !== undefined) {
      var stored = saved.value;
      if (validState(stored, doc)) state = stored;
      else saved.error = "显示设置无效，可重置显示";
    }
    if (doc.kind === "controls") state.selected = controlSelection(doc, state);
    var card = v.el("div", "viz-card"), header = v.el("div", "viz-header");
    card.dataset.kind = doc.kind;
    var name = v.el("h3", "viz-title", doc.title), summary = v.el("p", "viz-summary", doc.summary);
    name.id = "viz-title-" + (++serial); summary.id = "viz-summary-" + serial;
    card.setAttribute("role", "group"); card.setAttribute("aria-labelledby", name.id); card.setAttribute("aria-describedby", summary.id);
    header.append(name);
    var toolbar = v.el("div", "viz-toolbar"), search = v.el("input", "viz-filter");
    search.type = "search"; search.placeholder = "筛选内容"; search.setAttribute("aria-label", "筛选 " + doc.title);
    search.value = state.query;
    if (doc.kind !== "mermaid" && (doc.kind !== "controls" || doc.data.fields.length > 1)) toolbar.appendChild(search);
    var zoomable = ["proportion", "donut", "bar", "line", "gantt", "waterfall"].indexOf(doc.kind) >= 0;
    var zoom = v.el("div", "viz-zoom");
    [["out", "−", "缩小"], ["reset", "100%", "重置缩放"], ["in", "+", "放大"]].forEach(function (item) {
      var button = v.el("button", "viz-button", item[1]); button.type = "button";
      button.dataset.vizAction = item[0]; button.setAttribute("aria-label", item[2]); zoom.appendChild(button);
    });
    if (zoomable) toolbar.appendChild(zoom);
    var more = v.el("button", "viz-button viz-more", "⋯"); more.type = "button"; more.dataset.vizAction = "more";
    more.setAttribute("aria-label", "更多操作"); more.setAttribute("aria-expanded", "false");
    var menu = v.el("div", "viz-menu"); menu.hidden = true;
    menu.id = "viz-menu-" + serial; more.setAttribute("aria-controls", menu.id);
    [["clear", "恢复默认", "重置显示"], ["json", "下载数据", "导出 JSON"], ["svg", "下载图形", "导出 SVG"]].forEach(function (item) {
      var button = v.el("button", "viz-button", item[1]); button.type = "button";
      button.dataset.vizAction = item[0]; button.setAttribute("aria-label", item[2]); menu.appendChild(button);
    });
    toolbar.append(more, menu);
    var viewport = v.el("div", "viz-viewport"), content = v.el("div", "viz-content");
    viewport.appendChild(content);
    var footer = v.el("div", "viz-footer"), detail = v.el("output", "viz-detail");
    detail.setAttribute("aria-live", "polite");
    var insert = v.el("button", "viz-button viz-primary", "添加到消息"); insert.type = "button"; insert.dataset.vizAction = "insert"; insert.setAttribute("aria-label", "加入输入");
    var notice = v.el("div", "viz-notice"), noticeText = v.el("span", "", saved.error || ""), noticeReset = v.el("button", "viz-button", "重置显示");
    notice.setAttribute("role", "status"); noticeReset.type = "button"; noticeReset.dataset.vizAction = "clear";
    notice.append(noticeText, noticeReset); notice.hidden = !saved.error;
    footer.append(detail, insert); card.append(header, summary, toolbar, notice, viewport, footer); host.appendChild(card);
    var generation = 0, disposed = false, resource = null;
    function syncPresentation() {
      var editing = context.mode.get() === "edit";
      card.dataset.mode = editing ? "edit" : "view"; toolbar.hidden = !editing;
      if (!editing) { menu.hidden = true; more.setAttribute("aria-expanded", "false"); }
      footer.hidden = !state.selected || (!editing && doc.kind !== "controls");
      content.querySelectorAll("[data-viz-pick]").forEach(function (node) {
        node.tabIndex = editing ? 0 : -1;
        if (editing) node.setAttribute("role", "button"); else { node.removeAttribute("role"); node.classList.remove("viz-selected"); node.removeAttribute("aria-pressed"); }
        if (node.tagName === "BUTTON") node.disabled = !editing;
      });
    }
    var stopMode = context.mode.subscribe(syncPresentation);
    var theme = document.documentElement.dataset.uiTheme, themeObserver = null;
    if (["mermaid", "flow", "proportion", "donut", "bar", "line", "gantt", "waterfall"].indexOf(doc.kind) >= 0) {
      themeObserver = new MutationObserver(function () {
        var next = document.documentElement.dataset.uiTheme;
        if (!disposed && next !== theme) { theme = next; draw(); }
      });
      themeObserver.observe(document.documentElement, {attributes: true, attributeFilter: ["data-ui-theme"]});
    }
    function draw() {
      var current = ++generation;
      if (resource) { resource(); resource = null; }
      content = v.el("div", "viz-content"); viewport.replaceChildren(content);
      var target = content;
      target.style.width = (state.zoom * 100) + "%";
      zoom.querySelector('[data-viz-action="reset"]').textContent = Math.round(state.zoom * 100) + "%";
      menu.querySelector('[data-viz-action="svg"]').hidden = true;
      insert.disabled = !state.selected; detail.textContent = doc.kind === "controls" ? "" : state.selected;
      syncPresentation();
      Promise.resolve().then(function () {
        if (disposed || current !== generation) return null;
        return v.components.get(doc.kind)(target, doc, state, context);
      }).then(function (result) {
        if (disposed || current !== generation) { if (result && result.dispose) result.dispose(); return; }
        if (result && result.dispose) resource = result.dispose;
        var count = typeof result === "number" ? result : result && result.count;
        if (!count) target.appendChild(v.el("p", "viz-empty", state.query ? "没有符合条件的数据" : "暂无数据"));
        menu.querySelector('[data-viz-action="svg"]').hidden = !target.querySelector("svg") && !target._exportSvg;
        syncPresentation();
      }).catch(function (error) {
        if (disposed || current !== generation) return;
        target.replaceChildren(v.el("p", "viz-empty", "无法绘制：" + error.message + "。" + doc.summary));
        target.setAttribute("role", "alert");
        if (doc.kind === "mermaid") target.appendChild(v.el("pre", "viz-source", doc.data.code));
      });
    }
    function persist() {
      try { context.state.save(state); saved.error = ""; notice.hidden = true; }
      catch (_error) { noticeText.textContent = "显示设置未能保存，刷新后可能丢失"; noticeReset.hidden = true; notice.hidden = false; }
    }
    function changeControl(id, value, preview) {
      var field = doc.data.fields.find(function (item) { return item.id === id; });
      if (!field) return;
      if (field.type === "range") value = Number(value);
      if (field.type === "range" && (!Number.isFinite(value) || value < field.min || value > field.max)) return;
      if ((field.type === "select" || field.type === "tabs") && !field.options.some(function (option) { return option.value === value; })) return;
      state.controls = state.controls || Object.create(null); state.controls[id] = value;
      state.selected = controlSelection(doc, state);
      if (preview) {
        var active = Array.from(content.querySelectorAll("[data-viz-control]")).find(function (node) { return node.dataset.vizControl === id; });
        if (active && field.type === "range") {
          active.style.setProperty("--range-progress", ((value - field.min) / (field.max - field.min) * 100) + "%");
          active.closest(".viz-control").querySelector("output").textContent = v.format(value);
        }
        detail.textContent = ""; insert.disabled = false; syncPresentation(); return;
      }
      var focused = document.activeElement && document.activeElement.dataset.vizControl === id;
      draw(); persist();
      if (focused) queueMicrotask(function () {
        var next = Array.from(content.querySelectorAll("[data-viz-control]")).find(function (node) { return node.dataset.vizControl === id; });
        if (next) next.focus({preventScroll: true});
      });
    }
    function select(node) {
      if (context.mode.get() !== "edit") return;
      content.querySelectorAll(".viz-selected").forEach(function (item) { item.classList.remove("viz-selected"); item.setAttribute("aria-pressed", "false"); });
      node.classList.add("viz-selected"); node.setAttribute("aria-pressed", "true");
      state.selected = node.dataset.vizDetail; detail.textContent = state.selected; insert.disabled = false;
      syncPresentation();
      persist();
    }
    function click(event) {
      if (!event.target.closest(".viz-menu") && !event.target.closest('[data-viz-action="more"]')) {
        menu.hidden = true; more.setAttribute("aria-expanded", "false");
      }
      var tab = event.target.closest("[data-viz-tab]");
      if (tab) { changeControl(tab.dataset.vizTab, tab.dataset.vizValue); return; }
      var node = event.target.closest("[data-viz-pick]");
      if (node && content.contains(node)) { select(node); return; }
      var sorter = event.target.closest("[data-viz-sort]");
      if (sorter) { state.sortDirection = state.sortKey === sorter.dataset.vizSort ? -state.sortDirection : 1; state.sortKey = sorter.dataset.vizSort; draw(); persist(); return; }
      var button = event.target.closest("[data-viz-action]"); if (!button) return;
      var action = button.dataset.vizAction;
      if (action === "more") { menu.hidden = !menu.hidden; more.setAttribute("aria-expanded", String(!menu.hidden)); return; }
      if (action === "insert") {
        var result = context.insert(doc.title + " — " + state.selected);
        if (!result.ok) detail.textContent = result.error;
        else { detail.textContent = "已加入输入，发送后才会交给模型"; insert.disabled = true; }
      } else if (action === "json") save(JSON.stringify(doc, null, 2), "application/json", "visualization.json");
      else if (action === "svg") { var svg = content.querySelector("svg"); if (svg) exportSvg(svg); else if (content._exportSvg) save(content._exportSvg, "image/svg+xml", "visualization.svg"); }
      else if (action === "clear") { state = {query: "", zoom: 1, sortKey: "", sortDirection: 1, selected: ""}; search.value = ""; saved.error = ""; draw(); persist(); }
      else { state.zoom = action === "reset" ? 1 : Math.max(0.5, Math.min(3, state.zoom + (action === "in" ? 0.25 : -0.25))); draw(); persist(); }
      menu.hidden = true; more.setAttribute("aria-expanded", "false");
    }
    try {
      draw();
      card.addEventListener("click", click, {signal: controller.signal});
      card.addEventListener("visualization:select", function (event) {
        if (context.mode.get() !== "edit" || !content.contains(event.target) || typeof event.detail !== "string" || event.detail.length > 8000) return;
        state.selected = event.detail; detail.textContent = state.selected; insert.disabled = false;
        syncPresentation(); persist();
      }, {signal: controller.signal});
      card.addEventListener("input", function (event) {
        if (event.target === search) { state.query = search.value; state.selected = ""; draw(); persist(); }
        else if (event.target.dataset.vizControl && event.target.type === "range") changeControl(event.target.dataset.vizControl, event.target.value, true);
      }, {signal: controller.signal});
      card.addEventListener("change", function (event) {
        var node = event.target;
        if (node.dataset.vizControl) changeControl(node.dataset.vizControl, node.type === "checkbox" ? node.checked : node.value);
      }, {signal: controller.signal});
      card.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
          if (!menu.hidden) { event.stopPropagation(); menu.hidden = true; more.setAttribute("aria-expanded", "false"); more.focus(); }
          else if (context.mode.get() === "edit") context.mode.set("view");
          return;
        }
        var tab = event.target.closest("[data-viz-tab]");
        if (tab && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
          event.preventDefault();
          var field = doc.data.fields.find(function (item) { return item.id === tab.dataset.vizTab; });
          var index = field.options.findIndex(function (item) { return item.value === tab.dataset.vizValue; });
          var value = field.options[(index + (event.key === "ArrowRight" ? 1 : -1) + field.options.length) % field.options.length].value;
          changeControl(field.id, value);
          queueMicrotask(function () { var next = Array.from(content.querySelectorAll("[data-viz-tab]")).find(function (item) { return item.dataset.vizTab === field.id && item.dataset.vizValue === value; }); if (next) next.focus(); });
          return;
        }
        var node = event.target.closest("[data-viz-pick]");
        if (node && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); select(node); }
      }, {signal: controller.signal});
    } catch (error) { controller.abort(); throw error; }
    return function () { disposed = true; generation++; if (resource) resource(); if (themeObserver) themeObserver.disconnect(); stopMode(); controller.abort(); card.remove(); };
  }
  var disposers = new Map();
  function bindDeclared() {
    v.components.forEach(function (_draw, kind) {
      var type = "visualization." + kind;
      if (!shell.displays.declared(type, "visualization") || disposers.has(type)) return;
      disposers.set(type, shell.displays.register(type, function (host, doc, context) {
        return render(host, Object.assign({kind: kind}, doc), context);
      }, "visualization"));
    });
  }
  bindDeclared();
  document.addEventListener("ai-agent:ui-rendered", bindDeclared);
  function changed(event) {
    if ((event.detail && event.detail.loaded || []).indexOf("visualization") >= 0) return;
    disposers.forEach(function (dispose) { dispose(); });
    document.removeEventListener("ai-agent:ui-rendered", bindDeclared);
    if (v.disposeCharts) v.disposeCharts();
    if (v.disposeDependencies) v.disposeDependencies();
    document.removeEventListener("ai-agent:plugins-changed", changed);
    if (window.aiAgentVisualization === v) delete window.aiAgentVisualization;
  }
  document.addEventListener("ai-agent:plugins-changed", changed);
})();
