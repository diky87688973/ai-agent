/* 文件查看器由有效 UI 插口目录选择，实例资源随面板生命周期释放。 */
var classicFileViewers = (function () {
  var prefix = "app/shell/web-ui/file-viewers";
  var instances = new Map();
  classicComponents.defineFamily(prefix, ["open"]);
  function viewerProps(entry) { return entry.metadata && entry.metadata.props || {}; }
  function match(path) {
    var suffix = /\.[^./\\]+$/.exec(path);
    if (!suffix) return null;
    var found = classicComponents.entries(prefix).filter(function (entry) {
      return (viewerProps(entry).extensions || []).indexOf(suffix[0].toLowerCase()) >= 0;
    }).sort(function (a, b) {
      return (a.metadata.order || 0) - (b.metadata.order || 0);
    });
    if (found.length > 1 && (found[0].metadata.order || 0) === (found[1].metadata.order || 0)) {
      throw new Error("文件查看器声明优先级冲突");
    }
    return found[0] || null;
  }
  function dispose(id, reason) {
    var value = instances.get(id);
    if (!value) return;
    instances.delete(id);
    value.abort.abort();
    if (value.instance) value.instance.dispose(reason);
  }
  function mount(record, entry, body, path) {
    var implementation = classicComponents.select(entry.path, null);
    if (!implementation) return false;
    var instance = implementation.open({version: 1, path: path, body: body,
      signal: record.abort.signal, source: "file-open", paneId: record.id, formatSize: formatFileSize});
    if (!instance || !["activate", "deactivate", "dispose"].every(function (key) {
      return typeof instance[key] === "function";
    })) throw new Error("文件查看器缺少生命周期方法");
    record.instance = instance;
    record.instance.activate();
    return true;
  }
  function open(path) {
    if (!classicComponents.ready()) return prepare(path);
    var entry = match(path);
    if (!entry) return openDefaultFileTab(path);
    var id = entry.owner + "__file-" + encodeURIComponent(path);
    var title = baseNameOnly(path) || path;
    var current = instances.get(id);
    if (current && current.path === path && !current.abort.signal.aborted &&
        (!current.instance || !current.instance.canReuse || current.instance.canReuse())) {
      return openPane({id: id, title: title, plugin: entry.owner});
    }
    dispose(id, "replace");
    var pane = openPane({id: id, title: title, plugin: entry.owner});
    if (!pane) return null;
    var body = pane.querySelector(".pane-body");
    var record = {id: id, path: path, owner: entry.owner, abort: new AbortController(), instance: null};
    instances.set(id, record);
    body.textContent = "正在加载查看器…";
    function attempt() {
      if (record.abort.signal.aborted || record.instance) return;
      try {
        if (mount(record, entry, body, path)) {
          clearTimeout(timer); document.removeEventListener("ai-agent:components-changed", attempt);
        }
      }
      catch (error) { dispose(id, "failed"); body.textContent = "打开失败：" + error.message; console.error("file-viewer", error); }
    }
    attempt();
    if (!record.instance) {
      document.addEventListener("ai-agent:components-changed", attempt);
      var timer = setTimeout(function () {
        document.removeEventListener("ai-agent:components-changed", attempt);
        if (!record.instance && !record.abort.signal.aborted) body.textContent = "查看器加载失败，请重新打开文件";
      }, 5000);
      record.abort.signal.addEventListener("abort", function () {
        clearTimeout(timer); document.removeEventListener("ai-agent:components-changed", attempt);
      }, {once: true});
    }
    return pane;
  }
  function prepare(path) {
    var id = "preparing-" + filePaneId(path);
    dispose(id, "replace");
    var pane = openPane({id: id, title: baseNameOnly(path) || path});
    if (!pane) return null;
    var record = {id: id, owner: "", abort: new AbortController(), instance: null};
    instances.set(id, record);
    pane.querySelector(".pane-body").textContent = "正在准备文件查看器…";
    function ready() {
      if (!classicComponents.ready() || record.abort.signal.aborted) return;
      dispose(id, "ready"); closePane(id); open(path);
    }
    document.addEventListener("ai-agent:components-changed", ready);
    var timer = setTimeout(function () {
      document.removeEventListener("ai-agent:components-changed", ready);
      if (!record.abort.signal.aborted) pane.querySelector(".pane-body").textContent = "查看器目录加载失败，请重新打开文件";
    }, 5000);
    record.abort.signal.addEventListener("abort", function () {
      clearTimeout(timer); document.removeEventListener("ai-agent:components-changed", ready);
    }, {once: true});
    return pane;
  }
  function release(event) {
    var owner = event.detail && event.detail.plugin;
    instances.forEach(function (record, id) { if (!owner || owner === record.owner) dispose(id, "plugin-change"); });
    classicComponents.clearFamily(prefix, owner);
  }
  document.addEventListener("ai-agent:panel-closed", function (event) { dispose(event.detail.panel, "close"); });
  document.addEventListener("ai-agent:panel-deactivated", function (event) {
    var value = instances.get(event.detail.panel); if (value && value.instance) value.instance.deactivate();
  });
  document.addEventListener("ai-agent:panel-activated", function (event) {
    var value = instances.get(event.detail.panel); if (value && value.instance) value.instance.activate();
  });
  document.addEventListener("ai-agent:conversation-changed", function () {
    instances.forEach(function (value) { if (value.instance) value.instance.deactivate(); });
  });
  document.addEventListener("ai-agent:plugin-ui-release", release);
  document.addEventListener("ai-agent:plugins-changed", release);
  return {matches: function (path) { return !!match(path); }, open: open};
})();
