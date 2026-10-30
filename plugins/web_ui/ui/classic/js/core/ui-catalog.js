(function () {
  "use strict";
  if (window.__dshUiCatalogBound) return;
  window.__dshUiCatalogBound = true;

  var NAV_ICONS = {
    "web-ui/nav/buttons/settings": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>'
  };

  function entryOrder(item) {
    var meta = item && item.metadata ? item.metadata : {};
    if (typeof meta.order === "number") return meta.order;
    var props = meta.props || {};
    return typeof props.order === "number" ? props.order : null;
  }

  function orderRegion(item) {
    var order = entryOrder(item);
    if (order === null) return 1;
    return order >= 0 ? 0 : 2;
  }

  function sortByOrder(items) {
    return (items || []).slice().sort(function (a, b) {
      var ra = orderRegion(a);
      var rb = orderRegion(b);
      if (ra !== rb) return ra - rb;
      var oa = entryOrder(a);
      var ob = entryOrder(b);
      if (oa !== null && ob !== null && oa !== ob) return oa - ob;
      if (oa === null && ob !== null) return -1;
      if (oa !== null && ob === null) return 1;
      return String(a.path || "").localeCompare(String(b.path || ""));
    });
  }

  function actionFor(path) {
    if (path === "web-ui/nav/buttons/settings") return "settings.open";
    if (path === "web-ui/nav/buttons/style") return "theme.toggle";
    if (path === "web-ui/nav/buttons/update") return "auto_update.check";
    return "";
  }

  function handle(action) {
    if (action === "settings.open") {
      document.dispatchEvent(new CustomEvent("ai-agent:open-settings"));
      return;
    }
    if (action === "theme.toggle" && window.themeUi) {
      window.themeUi.toggle();
      return;
    }
    if (action === "auto_update.check" && window.autoUpdateUi) {
      window.autoUpdateUi.check();
      return;
    }
    if (action === "panel.open_file") {
      if (typeof window.openFilePicker === "function") window.openFilePicker();
      return;
    }
    if (action === "knowledge.open") {
      openCatalogPanel("web-ui/right-panel/kb");
      return;
    }
    if (action === "visual.toggle") {
      fetch("/api/plugin/visual_operator_2/eye-consent/revoke", {
        method: "POST", headers: {"Content-Type": "application/json"}, body: "{}"
      }).catch(function () {});
      return;
    }
    if (action === "input.mode" && window.composerActions) window.composerActions.toggleMode();
    if (action === "input.thinking" && window.composerActions) window.composerActions.toggleThinking();
    if (action === "input.goal" && window.composerActions) window.composerActions.openGoal();
    if (action === "input.send" && window.composerActions) window.composerActions.send();
    if (action === "input.stop" && window.composerActions) window.composerActions.stop();
  }

  function render(items) {
    var host = document.querySelector(".hdr-actions");
    if (!host || !Array.isArray(items)) return;
    var nav = items.filter(function (item) {
      return String(item.path || "").indexOf("web-ui/nav/buttons/") === 0;
    });
    nav = sortByOrder(nav);
    var old = {};
    var keepUpdate = null;
    var updateVisible = nav.some(function (item) {
      return item.path === "web-ui/nav/buttons/update";
    });
    if (updateVisible) {
      keepUpdate = host.querySelector('[data-ui-action="auto_update.check"]');
    }
    var staleUpdate = host.querySelector('[data-ui-action="auto_update.check"]');
    if (!updateVisible && staleUpdate) staleUpdate.remove();
    host.querySelectorAll("[data-ui-generated]").forEach(function (node) {
      if (node !== keepUpdate) node.remove();
    });
    if (!nav.length) return;
    nav.forEach(function (item) {
      var path = String(item.path || "");
      var props = (item.metadata && item.metadata.props) || {};
      var reusedUpdate = path === "web-ui/nav/buttons/update" && keepUpdate;
      var button = reusedUpdate ? keepUpdate : document.createElement("button");
      if (!reusedUpdate) {
        if (NAV_ICONS[path]) {
          button.innerHTML = NAV_ICONS[path];
          button.classList.add("ui-nav-icon");
          button.setAttribute("aria-label", String(props.label || "设置"));
        } else {
          button.textContent = String(props.label || path.split("/").pop());
        }
        button.type = "button";
        button.title = String(props.title || props.label || "");
        button.setAttribute("data-ui-generated", "1");
        button.setAttribute("data-ui-action", actionFor(path) || String(props.action || ""));
        button.className = (path === "web-ui/nav/buttons/settings"
          ? "hdr-settings-btn ui-nav-btn"
          : "hdr-theme-btn ui-nav-btn") + (NAV_ICONS[path] ? " ui-nav-icon" : "");
        if (path === "web-ui/nav/buttons/update") button.classList.add("hidden");
      }
      var controls = host.querySelector(".window-controls");
      if (controls) host.insertBefore(button, controls);
      else host.appendChild(button);
      if (path === "web-ui/nav/buttons/settings") old.settings = true;
      if (path === "web-ui/nav/buttons/style") old.theme = true;
      if (path === "web-ui/nav/buttons/update") old.update = true;
    });
  }

  var INPUT_TARGETS = {
    "web-ui/input/buttons/mode_btn": "modePlus",
    "web-ui/input/buttons/thinking_btn": "reasoningBtn",
    "web-ui/input/right-buttons/goal_btn": "autoToggle",
    "web-ui/input/right-buttons/send_btn": "go",
    "web-ui/input/right-buttons/stop_btn": "stopTask"
  };

  var STANDALONE_INPUTS = {
    "web-ui/input/buttons/image_btn": {
      target: "attachFile", className: "mode-plus",
      html: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="15" height="14" rx="2"/><circle cx="7.5" cy="8.5" r="1.4"/><path d="m18 13-4.5-4L4 18"/><path d="M19 15v6M16 18h6"/></svg>'
    },
    "web-ui/input/buttons/kb_btn": {action: "knowledge.open", className: "mode-plus", text: "知识库"},
    "web-ui/input/buttons/visual_btn": {action: "visual.toggle", className: "mode-plus vision-eye-btn", text: "眼睛", hidden: true},
    "web-ui/input/buttons/mode_btn": {action: "input.mode", className: "mode-plus", text: "Auto +"},
    "web-ui/input/buttons/thinking_btn": {action: "input.thinking", className: "mode-plus", text: "思考 · High"},
    "web-ui/input/right-buttons/goal_btn": {action: "input.goal", className: "mode-plus", text: "目标"},
    "web-ui/input/right-buttons/send_btn": {action: "input.send", className: "mode-plus", text: "发送"},
    "web-ui/input/right-buttons/stop_btn": {action: "input.stop", className: "mode-plus stop-task", text: "停止", hidden: true}
  };

  var INPUT_SELECTORS = {};
  var NATIVE_INPUTS = {
    "web-ui/input/buttons/model_switch_btn": "#modelPickerSlot .mm-picker-btn",
  };

  var EXISTING_TARGETS = {
    "web-ui/right-panel/steps": ["#tabSteps", "#paneSteps"],
    "web-ui/runtime/left-panel/ai_speak": ["#aiSpeakSlot"],
    "web-ui/runtime/left-panel/inbox": ["#chatQueue"],
    "web-ui/runtime/right-panel/background_task": ["#bgTaskPanel"],
    "web-ui/runtime/right-panel/subagent": ["#subagentPanel"]
  };

  function renderExisting(items) {
    if (!Array.isArray(items)) return;
    Object.keys(EXISTING_TARGETS).forEach(function (path) {
      var entry = items.filter(function (item) { return item.path === path; })[0];
      EXISTING_TARGETS[path].forEach(function (selector) {
        var node = document.querySelector(selector);
        if (!node) return;
        if (entry) {
          node.setAttribute("data-ui-path", path);
          var props = (entry.metadata && entry.metadata.props) || {};
          if (props.label && !node.textContent.trim()) node.textContent = String(props.label);
          if (props.title) node.title = String(props.title);
        } else {
          node.removeAttribute("data-ui-path");
          node.style.display = "none";
        }
      });
    });
    var kbTab = document.getElementById("tab-knowledge__kb");
    if (kbTab) kbTab.setAttribute("data-ui-path", "web-ui/right-panel/kb");
  }

  var inputEntries = [];
  var catalogEntries = [];
  var catalogLoadedPlugins = null;

  function renderRightTabs(items) {
    var bar = document.getElementById("sideTabbar");
    if (!bar) return;
    bar.querySelectorAll("[data-ui-generated-tab]").forEach(function (node) { node.remove(); });
    var entries = (items || []).filter(function (item) {
      return String(item.path || "").indexOf("web-ui/right-panel/") === 0 &&
        item.kind === "button";
    });
    entries.forEach(function (item) {
      var path = String(item.path || "");
      if (path === "web-ui/right-panel/steps") return;
      var props = (item.metadata && item.metadata.props) || {};
      var button = document.createElement("button");
      button.type = "button";
      button.className = "side-tab";
      button.setAttribute("data-ui-generated-tab", "1");
      button.setAttribute("data-ui-path", path);
      button.setAttribute("data-ui-action", String(props.action || ""));
      button.textContent = String(props.label || path.split("/").pop());
      bar.appendChild(button);
    });
    if (typeof syncClassicSide === "function") syncClassicSide();
  }

  function renderInput(items) {
    if (!Array.isArray(items)) return;
    items = sortByOrder(items);
    var modelOrder = 1e9;
    items.forEach(function (item) {
      if (item.path === "web-ui/input/buttons/model_switch_btn") modelOrder = entryOrder(item);
    });
    document.querySelectorAll("[data-ui-input-generated]").forEach(function (node) { node.remove(); });
    items.forEach(function (item) {
      var path = String(item.path || "");
      var nativeSelector = NATIVE_INPUTS[path];
      if (nativeSelector) {
        var native = document.querySelector(nativeSelector);
        if (native) {
          native.setAttribute("data-ui-input-path", path);
          native.setAttribute("data-ui-input-native", "1");
        }
        return;
      }
      var targetId = INPUT_TARGETS[path];
      var selector = INPUT_SELECTORS[path];
      var standalone = STANDALONE_INPUTS[path];
      var target = targetId ? document.getElementById(targetId)
        : (selector ? document.querySelector(selector) : (standalone && standalone.target ? document.getElementById(standalone.target) : null));
      if (!target && !standalone) return;
      var props = (item.metadata && item.metadata.props) || {};
      var button = document.createElement("button");
      if (standalone) {
        button.className = standalone.className + " ui-input-generated";
        if (standalone.html) button.innerHTML = standalone.html;
        else button.textContent = String(props.label || standalone.text || "");
        button.title = String(props.title || props.label || standalone.text || "");
        button.setAttribute("data-ui-input-generated", "1");
        if (standalone.target) button.setAttribute("data-ui-target", standalone.target);
        if (standalone.action) button.setAttribute("data-ui-action", standalone.action);
        if (standalone.hidden) button.hidden = true;
        var host = document.querySelector(".left-tools");
        if (standalone.action === "input.goal" || standalone.action === "input.send" || standalone.action === "input.stop") {
          host = document.querySelector(".right-actions");
        }
        if (host) {
          var order = entryOrder(item);
          var left = host.classList && host.classList.contains("left-tools");
          var modelSlot = left ? document.getElementById("modelPickerSlot") : null;
          var anchor = left ? (document.getElementById("pluginActions") ||
            document.getElementById("reasoningMenu") || null) : null;
          if (left && modelSlot && order < modelOrder) host.insertBefore(button, modelSlot);
          else if (left && anchor) host.insertBefore(button, anchor);
          else host.appendChild(button);
        }
        return;
      }
      button.type = "button";
      button.className = String(target.className || "") + " ui-input-generated";
      button.innerHTML = target.innerHTML;
      button.title = String(props.title || props.label || target.title || "");
      button.setAttribute("data-ui-input-generated", "1");
      if (targetId) button.setAttribute("data-ui-target", targetId);
      if (selector) button.setAttribute("data-ui-target-selector", selector);
      button.hidden = !!target.hidden;
      target.style.display = "none";
      target.parentNode.insertBefore(button, target);
    });
  }

  function refreshInputs() {
    if (inputEntries.length) {
      renderExisting(inputEntries);
      renderInput(inputEntries);
    }
  }

  function loadPluginStyles(owner, styles) {
    (styles || []).forEach(function (rel) {
      var url = "/api/plugin/" + encodeURIComponent(owner) + "/_asset/" +
        String(rel || "").split("/").map(encodeURIComponent).join("/");
      if (document.querySelector('link[data-plugin-style="' + url + '"]')) return;
      var link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = url;
      link.setAttribute("data-plugin-style", url);
      document.head.appendChild(link);
    });
  }

  function openCatalogPanel(path) {
    var entry = catalogEntries.filter(function (item) { return item.path === path; })[0];
    if (!entry) return;
    var owner = String(entry.owner || "");
    var props = (entry.metadata && entry.metadata.props) || {};
    var paneId = owner + "__" + String(path.split("/").pop() || "panel");
    if (typeof openPane !== "function") return;
    loadPluginStyles(owner, props.styles);
    var pane = openPane({id: paneId, title: String(props.label || "面板"),
                         html: String(props.html || ""), plugin: owner});
    if (!pane) return;
    if (typeof selectSidePane === "function") selectSidePane(paneId);
    if (props.scripts && props.scripts.length) {
      loadScripts([{owner: owner, metadata: {props: {scripts: props.scripts}}}]);
    }
  }

  var scriptWaiters = Object.create(null);
  var scriptEventsBound = false;
  function onScriptEvent(event) {
    var node = event.target;
    if (!node || node.tagName !== "SCRIPT" || !node.hasAttribute("data-ui-plugin-script")) return;
    var url = node.getAttribute("data-ui-plugin-script");
    var resolve = scriptWaiters[url];
    if (!resolve) return;
    delete scriptWaiters[url];
    resolve(true);
  }
  function bindScriptEvents() {
    if (scriptEventsBound) return;
    scriptEventsBound = true;
    document.addEventListener("load", onScriptEvent, true);
    document.addEventListener("error", onScriptEvent, true);
  }
  function loadScripts(items) {
    var jobs = [];
    var seen = {};
    (items || []).forEach(function (item) {
      var props = (item.metadata && item.metadata.props) || {};
      var scripts = props.scripts;
      if (!Array.isArray(scripts)) scripts = props.script ? [props.script] : [];
      scripts.forEach(function (rel) {
        var owner = String(item.owner || "");
        var path = String(rel || "").replace(/^\/+/, "");
        if (!owner || !path || seen[owner + "|" + path]) return;
        seen[owner + "|" + path] = true;
        var url = "/api/plugin/" + encodeURIComponent(owner) + "/_asset/" + path.split("/").map(encodeURIComponent).join("/");
        if (document.querySelector('script[data-ui-plugin-script="' + url + '"]')) return;
        bindScriptEvents();
        jobs.push(new Promise(function (resolve) {
          var script = document.createElement("script");
          scriptWaiters[url] = resolve;
          script.src = url;
          script.async = false;
          script.setAttribute("data-ui-plugin-script", url);
          window.aiAgentPluginCurrent = owner;
          document.head.appendChild(script);
        }));
      });
    });
    return Promise.all(jobs);
  }

  function pruneCatalogScripts(entries) {
    var allowed = Object.create(null);
    (entries || []).forEach(function (item) {
      var props = (item.metadata && item.metadata.props) || {};
      var scripts = Array.isArray(props.scripts) ? props.scripts : (props.script ? [props.script] : []);
      var owner = String(item.owner || "");
      scripts.forEach(function (rel) {
        allowed["/api/plugin/" + encodeURIComponent(owner) + "/_asset/" +
          String(rel || "").split("/").map(encodeURIComponent).join("/")] = true;
      });
    });
    var nodes = document.querySelectorAll("script[data-ui-plugin-script]");
    for (var i = nodes.length - 1; i >= 0; i--) {
      var node = nodes[i];
      var url = String(node.getAttribute("data-ui-plugin-script") || "");
      if (allowed[url]) continue;
      if (node.parentNode) node.parentNode.removeChild(node);
      delete scriptWaiters[url];
    }
  }

  function boot() {
    fetch("/api/ui/catalog", { headers: { "Accept": "application/json" } })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        var rawEntries = (data && data.entries) || [];
        if (Array.isArray(catalogLoadedPlugins)) {
          var allowed = Object.create(null);
          catalogLoadedPlugins.forEach(function (name) { allowed[String(name)] = true; });
          rawEntries = rawEntries.filter(function (item) {
            return !item.owner || allowed[String(item.owner)];
          });
        }
        inputEntries = rawEntries;
        catalogEntries = inputEntries;
        var segments = {};
        inputEntries.forEach(function (item) {
          var p = (item.metadata && item.metadata.props) || {};
          loadPluginStyles(String(item.owner || ""), p.styles);
          if (String(item.path || "").indexOf("web-ui/left-panel/context_usage/") === 0) {
            var key = String(item.path).split("/").pop();
            segments[key] = {label: String(p.label || key), color: String(p.color || "")};
          }
        });
        window.__dshContextSegments = segments;
        document.dispatchEvent(new CustomEvent("ai-agent:context-segments", {detail: segments}));
        pruneCatalogScripts(inputEntries);
        return loadScripts(inputEntries).then(function () {
          render(data && data.entries);
          renderExisting(inputEntries);
          renderRightTabs(inputEntries);
          renderInput(inputEntries);
          function ensureModelPicker() {
            if (document.querySelector('#modelPickerSlot .mm-picker-btn')) return;
            var loaded = window.__dshLoadedPlugins || [];
            var hasModel = loaded.indexOf("multi_model") >= 0;
            if (hasModel && typeof window.__multiModelPickerBoot === "function") {
              try { window.__multiModelPickerBoot(); } catch (e) {}
            }
          }
          setTimeout(ensureModelPicker, 50);
          setTimeout(ensureModelPicker, 500);
          setTimeout(refreshInputs, 800);
          setTimeout(refreshInputs, 1800);
        });
      })
      .catch(function () {});
  }

  document.addEventListener("click", function (event) {
    var target = event.target && event.target.closest
      ? event.target.closest("[data-ui-target]") : null;
    if (target) {
      var original = target.getAttribute("data-ui-target")
        ? document.getElementById(target.getAttribute("data-ui-target"))
        : document.querySelector(target.getAttribute("data-ui-target-selector"));
      if (original) {
        event.preventDefault();
        original.click();
      }
      return;
    }
    var node = event.target && event.target.closest
      ? event.target.closest("[data-ui-action]") : null;
    if (!node) return;
    var action = node.getAttribute("data-ui-action");
    if (!action) return;
    event.preventDefault();
    handle(action);
  });

  document.addEventListener("ai-agent:plugin-event", function () {
    setTimeout(refreshInputs, 100);
  });

  document.addEventListener("ai-agent:plugins-changed", function (event) {
    var loaded = event && event.detail && Array.isArray(event.detail.loaded)
      ? event.detail.loaded : [];
    catalogLoadedPlugins = loaded.slice();
    var set = Object.create(null);
    loaded.forEach(function (name) { set[String(name)] = true; });
    var nodes = document.querySelectorAll("script[data-ui-plugin-script]");
    for (var i = nodes.length - 1; i >= 0; i--) {
      var src = String(nodes[i].getAttribute("data-ui-plugin-script") || "");
      var match = /\/api\/plugin\/([^/]+)\//.exec(src);
      if (match && !set[decodeURIComponent(match[1])] && nodes[i].parentNode) {
        nodes[i].parentNode.removeChild(nodes[i]);
        delete scriptWaiters[src];
      }
    }
    setTimeout(boot, 0);
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
