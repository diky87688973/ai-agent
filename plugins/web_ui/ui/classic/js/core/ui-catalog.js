(function () {
  "use strict";
  if (window.__dshUiCatalogBound) return;
  window.__dshUiCatalogBound = true;

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

  function propsOf(item) {
    var meta = item && item.metadata ? item.metadata : {};
    return meta.props || {};
  }

  function bindingOf(item) {
    var binding = propsOf(item).binding;
    return binding && typeof binding === "object" ? binding : {};
  }

  var customActions = Object.create(null);
  window.aiAgentUiActions = {
    register: function (action, handler) {
      var key = String(action || "").trim();
      if (!key || typeof handler !== "function") return function () {};
      customActions[key] = handler;
      return function () { if (customActions[key] === handler) delete customActions[key]; };
    },
    unregister: function (action) {
      delete customActions[String(action || "").trim()];
    }
  };

  function handle(action, node) {
    if (customActions[action]) {
      customActions[action](action);
      return;
    }
    if (action === "settings.open") {
      document.dispatchEvent(new CustomEvent("ai-agent:open-settings"));
      return;
    }
    if (action === "theme.toggle" && window.themeUi) {
      window.themeUi.toggle();
      return;
    }
    if (action === "panel.open_file") {
      if (typeof window.openFilePicker === "function") window.openFilePicker();
      return;
    }
    if (action === "panel.open") {
      var target = node ? node.getAttribute("data-ui-panel") : "";
      if (target) openCatalogPanel(target);
      return;
    }
    if (action === "input.mode" && window.composerActions) window.composerActions.toggleMode();
    if (action === "input.thinking" && window.composerActions) window.composerActions.toggleThinking();
    if (action === "input.goal" && window.composerActions) window.composerActions.openGoal();
    if (action === "input.image" && window.composerActions) window.composerActions.openImage();
    if (action === "input.send" && window.composerActions) window.composerActions.send();
    if (action === "input.stop" && window.composerActions) window.composerActions.stop();
  }

  function render(items) {
    var host = document.querySelector(".hdr-actions");
    if (!host || !Array.isArray(items)) return;
    var nav = items.filter(function (item) { return !!bindingOf(item).nav; });
    nav = sortByOrder(nav);
    var old = {};
    var persistent = {};
    nav.forEach(function (item) {
      var bind = bindingOf(item);
      var role = String(bind.nav || "");
      if (!bind.persistent || !role) return;
      var existing = host.querySelector('[data-ui-generated][data-ui-role="' + role + '"]');
      if (existing) persistent[role] = existing;
    });
    host.querySelectorAll("[data-ui-generated]").forEach(function (node) {
      var role = String(node.getAttribute("data-ui-role") || "");
      if (!persistent[role]) node.remove();
    });
    if (!nav.length) return;
    nav.forEach(function (item) {
      var path = String(item.path || "");
      var props = propsOf(item);
      var bind = bindingOf(item);
      var role = String(bind.nav || "");
      var button = persistent[role] || document.createElement("button");
      if (!persistent[role]) {
        if (bind.icon) {
          button.innerHTML = String(bind.icon);
          button.classList.add("ui-nav-icon");
          button.setAttribute("aria-label", String(props.label || role));
        } else {
          button.textContent = String(props.label || role);
        }
        button.type = "button";
        button.title = String(props.title || props.label || "");
        button.setAttribute("data-ui-generated", "1");
        button.setAttribute("data-ui-role", role);
        if (bind.persistent) button.setAttribute("data-ui-persistent", "1");
        button.setAttribute("data-ui-action", String(props.action || ""));
        button.setAttribute("data-ui-panel", String(bind.panel || ""));
        button.className = String(bind.className || (role === "settings"
          ? "hdr-settings-btn ui-nav-btn"
          : "hdr-theme-btn ui-nav-btn")) + (bind.icon ? " ui-nav-icon" : "");
        if (bind.hidden) button.classList.add("hidden");
      }
      var controls = host.querySelector(".window-controls");
      if (controls) host.insertBefore(button, controls);
      else host.appendChild(button);
      old[role] = true;
    });
  }

  function renderExisting(items) {
    if (!Array.isArray(items)) return;
    items.forEach(function (item) {
      var bind = bindingOf(item);
      var selectors = Array.isArray(bind.existing) ? bind.existing : [];
      selectors.forEach(function (selector) {
        var node = document.querySelector(String(selector || ""));
        if (!node) return;
        node.setAttribute("data-ui-path", String(item.path || ""));
        var props = propsOf(item);
        if (props.label && !node.textContent.trim()) node.textContent = String(props.label);
        if (props.title) node.title = String(props.title);
      });
    });
  }

  var inputEntries = [];
  var catalogEntries = [];
  var catalogLoadedPlugins = null;

  function renderInput(items) {
    if (!Array.isArray(items)) return;
    items = sortByOrder(items);
    var modelOrder = 1e9;
    items.forEach(function (item) {
      var bind = bindingOf(item);
      if (bind.model_slot) modelOrder = entryOrder(item);
    });
    document.querySelectorAll("[data-ui-input-generated]").forEach(function (node) { node.remove(); });
    items.forEach(function (item) {
      var path = String(item.path || "");
      var bind = bindingOf(item);
      var input = bind.input;
      if (!input || typeof input !== "object") return;
      var props = propsOf(item);
      var nativeSelector = String(input.native || "");
      if (nativeSelector) {
        var native = document.querySelector(nativeSelector);
        if (native) {
          native.setAttribute("data-ui-input-path", path);
          native.setAttribute("data-ui-input-native", "1");
        }
        return;
      }
      var targetId = String(input.target || "");
      var selector = String(input.selector || "");
      var standalone = input.standalone === true;
      var target = targetId ? document.getElementById(targetId)
        : (selector ? document.querySelector(selector) : null);
      if (!target && !standalone) return;
      var button = document.createElement("button");
      if (standalone) {
        button.className = String(input.className || "mode-plus") + " ui-input-generated";
        if (input.html) button.innerHTML = String(input.html);
        else button.textContent = String(input.text || props.label || "");
        button.title = String(props.title || props.label || input.text || "");
        button.setAttribute("data-ui-input-generated", "1");
        if (targetId && target) button.setAttribute("data-ui-target", targetId);
        if (input.action) button.setAttribute("data-ui-action", input.action);
        if (input.panel) button.setAttribute("data-ui-panel", input.panel);
        if (input.hidden) button.hidden = true;
        var host = document.querySelector(input.host || ".left-tools");
        if (host) {
          var order = entryOrder(item);
          var left = host.classList && host.classList.contains("left-tools");
          var modelSlot = left ? document.getElementById("modelPickerSlot") : null;
          var anchor = left ? (document.getElementById("pluginActions") ||
            document.getElementById("reasoningMenu") || null) : null;
          if (left && modelSlot && order < modelOrder) host.insertBefore(button, modelSlot);
          else if (left && anchor && input.anchor !== "model") host.insertBefore(button, anchor);
          else host.appendChild(button);
        }
        return;
      }
      button.type = "button";
      button.className = String(input.className || target.className || "") + " ui-input-generated";
      button.innerHTML = input.html || target.innerHTML;
      button.title = String(props.title || props.label || target.title || "");
      button.setAttribute("data-ui-input-generated", "1");
      if (targetId) button.setAttribute("data-ui-target", targetId);
      if (selector) button.setAttribute("data-ui-target-selector", selector);
      button.hidden = !!input.hidden;
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
      if (document.querySelector('link[data-plugin-src="' + url + '"]')) return;
      var link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = url;
      link.setAttribute("data-plugin-style", String(owner || ""));
      link.setAttribute("data-plugin-src", url);
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
        classicComponents.apply(inputEntries);
        if (window.aiAgentShell && window.aiAgentShell.displays) window.aiAgentShell.displays.setCatalog(inputEntries);
        var segments = {};
        inputEntries.forEach(function (item) {
          var p = (item.metadata && item.metadata.props) || {};
          loadPluginStyles(String(item.owner || ""), p.styles);
          var bind = p.binding && typeof p.binding === "object" ? p.binding : {};
          if (bind.context) {
            var key = String(bind.context_key || String(item.path || "").split("/").pop());
            segments[key] = {label: String(p.label || key), color: String(p.color || "")};
          }
        });
        window.__dshContextSegments = segments;
        document.dispatchEvent(new CustomEvent("ai-agent:context-segments", {detail: segments}));
        pruneCatalogScripts(inputEntries);
        render(data && data.entries);
        renderExisting(inputEntries);
        renderInput(inputEntries);
        return loadScripts(inputEntries).then(function () {
          render(data && data.entries);
          renderExisting(inputEntries);
            renderInput(inputEntries);
          try {
            document.dispatchEvent(new CustomEvent("ai-agent:ui-rendered"));
          } catch (e) {}
          setTimeout(refreshInputs, 800);
          setTimeout(refreshInputs, 1800);
        });
      })
      .catch(function (err) {
        if (window.console && console.error) console.error("ui-catalog", err && (err.stack || err));
      });
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
    handle(action, node);
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
