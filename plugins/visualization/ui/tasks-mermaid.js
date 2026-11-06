(function () {
  "use strict";
  var v = window.aiAgentVisualization, engine = null, enginePromise = null, queue = Promise.resolve(), sequence = 0;
  var cancelLoad = null, dependenciesDisposed = false;
  function loadEngine() {
    if (dependenciesDisposed) return Promise.reject(new Error("组件已卸载"));
    if (engine) return Promise.resolve(engine);
    if (enginePromise) return enginePromise;
    enginePromise = new Promise(function (resolve, reject) {
      var script = document.createElement("script");
      script.src = window.aiAgentPlugins.for("visualization").url("_asset/ui/vendor/mermaid.min.js");
      script.setAttribute("data-plugin-script", "visualization");
      script.onload = function () { engine = window.mermaid; if (engine) resolve(engine); else reject(new Error("离线渲染库未就绪")); };
      script.onerror = function () { script.remove(); enginePromise = null; reject(new Error("离线渲染库无法加载")); };
      cancelLoad = function () { script.onload = script.onerror = null; script.remove(); reject(new Error("组件已卸载")); };
      document.head.appendChild(script);
    });
    return enginePromise;
  }
  v.disposeDependencies = function () { dependenciesDisposed = true; if (cancelLoad) cancelLoad(); engine = null; enginePromise = null; window.mermaid = undefined; window.__esbuild_esm_mermaid_nm = undefined; };
  var labels = {queued: "等待", running: "运行", completed: "成功", failed: "失败", timed_out: "超时", cancelled: "取消"};
  var statusColors = {queued: "#b3bfd4", running: "#4562f5", completed: "#18b998", failed: "#f26d83", timed_out: "#ffae43", cancelled: "#9965f4"};
  function tasks(host, doc, state, context) {
    var controller = new AbortController(), timer = null, stopped = false, terminal = false;
    var status = v.el("p", "viz-task-status", "正在同步任务状态…"), list = v.el("div");
    var track = v.el("div", "viz-track viz-task-track"), fill = v.el("div", "viz-progress-fill");
    track.hidden = true; track.setAttribute("role", "progressbar"); track.setAttribute("aria-label", "任务完成进度");
    track.setAttribute("aria-valuemin", "0"); track.setAttribute("aria-valuemax", String(doc.data.task_ids.length));
    track.appendChild(fill); host.append(status, track, list);
    function show(rows) {
      var map = new Map(rows.map(function (row) { return [row.task_id, row]; }));
      var known = doc.data.task_ids.every(function (id) { return map.has(id) && Object.prototype.hasOwnProperty.call(labels, map.get(id).status); });
      var done = doc.data.task_ids.filter(function (id) { return map.has(id) && ["completed", "failed", "timed_out", "cancelled"].indexOf(map.get(id).status) >= 0; }).length;
      status.textContent = known ? "已结束 " + done + " / " + doc.data.task_ids.length + " · " + Math.round(done / doc.data.task_ids.length * 100) + "%" : "部分任务已不可用；当前服务不保留重启前的任务，无法计算可靠百分比";
      track.hidden = !known; track.setAttribute("aria-valuenow", String(done));
      fill.style.width = (done / doc.data.task_ids.length * 100) + "%";
      list.replaceChildren();
      doc.data.task_ids.forEach(function (id) {
        var task = map.get(id), label = task ? task.label || id : id;
        if (!label.toLocaleLowerCase().includes(state.query.toLocaleLowerCase())) return;
        var row = v.el("div", "viz-task-row");
        var badge = v.el("span", "", task ? labels[task.status] || "未知状态" : "不可用");
        if (task && statusColors[task.status]) badge.style.setProperty("--task-color", statusColors[task.status]);
        row.append(v.el("strong", "", label), badge);
        list.appendChild(v.pick(row, id, label + " · " + (task ? labels[task.status] || "未知状态" : "不可用")));
      });
      return known && done === doc.data.task_ids.length;
    }
    async function poll() {
      try {
        if (!context.active()) return;
        var query = new URLSearchParams({conversation_id: context.conversationId, batch: doc.data.batch});
        var response = await fetch("/api/background/tasks?" + query, {signal: controller.signal, cache: "no-store"});
        if (!response.ok) throw new Error("任务状态读取失败");
        var result = await response.json();
        if (stopped) return;
        if (!result.ok || !Array.isArray(result.tasks)) throw new Error("任务状态无效");
        terminal = show(result.tasks);
      } catch (error) {
        if (!stopped && error.name !== "AbortError") status.textContent = "连接中断，保留上次显示；正在重试同步";
      } finally { if (!stopped && !terminal) timer = setTimeout(poll, 1200); }
    }
    void poll();
    return {count: 1, dispose: function () { stopped = true; if (timer) clearTimeout(timer); controller.abort(); }};
  }
  function mermaid(host, doc) {
    var code = doc.data.code, work = v.el("div", "viz-mermaid-work");
    var structured = doc.kind === "flow";
    if (!structured && (typeof code !== "string" || code.length > 16000 || /%%\{|\b(?:click|classDef|linkStyle)\b|https?:|javascript:|data:|file:|url\s*\(/i.test(code))) throw new Error("图定义包含不允许的指令或链接");
    if (structured && code.length > 131072) throw new Error("流程定义过大");
    var style = getComputedStyle(host), light = document.documentElement.dataset.uiTheme === "light";
    var surface = style.getPropertyValue("--viz-surface").trim(), text = style.getPropertyValue("--viz-text").trim();
    var border = style.getPropertyValue("--viz-node-line").trim(), muted = style.getPropertyValue("--viz-muted").trim();
    var job = queue.then(async function () {
      await loadEngine();
      engine.initialize({startOnLoad: false, securityLevel: "strict", htmlLabels: structured, maxTextSize: structured ? 131072 : 16000, maxEdges: 120,
        suppressErrorRendering: true, look: "classic", theme: "base", flowchart: {htmlLabels: structured, nodeSpacing: 36, rankSpacing: 48, padding: 12, curve: "stepAfter"},
        themeCSS: "text.actor,.messageText,.labelText,.loopText,.noteText{font-size:13px!important}text.actor{font-weight:450}.node rect,rect.actor,.flowchart-link,.messageLine0,.messageLine1{stroke-width:1.2px}",
        sequence: {actorMargin: 36, width: 144, height: 40, actorFontSize: 13, messageFontSize: 13, noteFontSize: 13, messageMargin: 28, noteMargin: 12},
        themeVariables: {darkMode: !light, fontFamily: style.fontFamily, fontSize: "13px", primaryColor: surface,
          primaryTextColor: text, primaryBorderColor: border, lineColor: muted, secondaryColor: surface, tertiaryColor: surface,
          actorBkg: surface, actorBorder: border, actorTextColor: text, signalColor: muted, signalTextColor: text,
          sequenceNumberColor: light ? "#fff" : "#202b43",
          noteBkgColor: surface, noteBorderColor: border, noteTextColor: text, activationBkgColor: surface, activationBorderColor: border}});
      document.body.appendChild(work);
      try {
        var result = await engine.render("viz-mermaid-" + (++sequence), code, work);
        if (dependenciesDisposed) throw new Error("组件已卸载");
        if (result.svg.length > 524288) throw new Error("渲染图形过大");
        var parsed = new DOMParser().parseFromString(result.svg, "image/svg+xml");
        if (parsed.querySelector("parsererror,script,a,image,iframe,object,embed,link") || (!structured && parsed.querySelector("foreignObject"))) throw new Error("图形包含不允许的内容");
        if (structured) parsed.querySelectorAll("foreignObject *").forEach(function (node) {
          if (["div", "span", "p", "br"].indexOf(node.localName) < 0) throw new Error("节点标签包含不允许的内容");
        });
        parsed.querySelectorAll("rect.actor,.node rect").forEach(function (rect) { rect.setAttribute("rx", "8"); rect.setAttribute("ry", "8"); });
        parsed.querySelectorAll("*").forEach(function (node) {
          Array.from(node.attributes).forEach(function (attribute) {
            if (/^on|href$/i.test(attribute.name)) throw new Error("图形包含事件或链接");
          });
        });
        var svg = new XMLSerializer().serializeToString(parsed.documentElement);
        var frame = v.el("iframe", "viz-mermaid"); frame.title = doc.title; frame.setAttribute("sandbox", "");
        var box = (parsed.documentElement.getAttribute("viewBox") || "").trim().split(/[\s,]+/).map(Number);
        if (box.length !== 4 || !box.every(Number.isFinite) || box[2] <= 0 || box[3] <= 0) throw new Error("图形缺少有效尺寸");
        var aspect = box[3] / box[2];
        frame.style.height = Math.max(80, Math.min(400, Math.min(box[2], host.clientWidth - 16) * aspect + 16)) + "px";
        frame.srcdoc = '<!doctype html><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; img-src \'none\'"><style>html,body{margin:0;width:100%;height:100%;overflow:hidden}body{display:flex;align-items:center;justify-content:center;box-sizing:border-box;padding:8px;background:transparent}svg{display:block;width:100%!important;height:100%!important;max-width:' + box[2] + 'px!important;max-height:' + box[3] + 'px!important}</style>' + svg;
        host.appendChild(frame); host._exportSvg = svg;
        return 1;
      } finally { work.remove(); }
    });
    queue = job.catch(function () {});
    return job;
  }
  v.add("tasks", tasks); v.add("mermaid", mermaid);
})();
