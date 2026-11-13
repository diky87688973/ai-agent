/* Replaceable UI components are selected by the effective slot catalog. */
var classicComponents = (function () {
  var catalog = null;
  var implementations = new Map();
  var contracts = new Map();
  function scripts(entry) {
    var props = entry && entry.metadata && entry.metadata.props || {};
    return Array.isArray(props.scripts) ? props.scripts : (props.script ? [props.script] : []);
  }
  function apply(entries) {
    catalog = new Map(entries.map(function (entry) { return [entry.path, entry]; }));
    implementations.forEach(function (registered, path) {
      var entry = catalog.get(path);
      if (!entry || entry.owner !== registered.entry.owner ||
          JSON.stringify(scripts(entry)) !== JSON.stringify(scripts(registered.entry))) {
        implementations.delete(path);
      }
    });
    document.dispatchEvent(new Event("ai-agent:components-changed"));
  }
  function register(path, implementation) {
    var script = document.currentScript;
    var asset = script && /\/api\/plugin\/([^/]+)\//.exec(script.src);
    var entry = catalog && catalog.get(path);
    var contract = contracts.get(path);
    if (!asset || !entry || !contract || entry.kind !== "ui-control" ||
        entry.owner !== decodeURIComponent(asset[1]) ||
        !scripts(entry).some(function (relative) {
          return relative && script.src.endsWith("/_asset/" +
            String(relative).split("/").map(encodeURIComponent).join("/"));
        })) {
      throw new Error("UI 组件与有效插口的归属不匹配");
    }
    if (!implementation || !contract.every(function (name) {
      return typeof implementation[name] === "function";
    })) throw new Error("UI 组件缺少必需方法");
    implementations.set(path, {entry: entry, renderer: implementation});
    document.dispatchEvent(new Event("ai-agent:components-changed"));
  }
  function select(path, defaults) {
    if (!catalog) return defaults;
    var entry = catalog.get(path);
    if (!entry) return null;
    var registered = implementations.get(path);
    if (entry.owner === "web_ui") return defaults;
    return registered && registered.entry.owner === entry.owner ? registered.renderer : defaults;
  }
  function define(path, methods) { contracts.set(path, methods); }
  return {apply: apply, register: register, select: select, define: define};
})();
window.aiAgentClassicComponents = {register: classicComponents.register};
