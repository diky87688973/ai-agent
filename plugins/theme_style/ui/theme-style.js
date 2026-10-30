/* 主题风格：界面风格选择器与风格资源热加载。 */
(function () {
  "use strict";
  var PLUGIN = "theme_style";
  var DEFAULT_STYLE = "dsh";
  var BASE = "/api/plugin/" + PLUGIN + "/_asset/";
  var existing = window.__themeStyle;
  if (existing) {
    existing.start();
    return;
  }

  var state = {
    catalog: null,
    selected: DEFAULT_STYLE,
    loadedStyle: "",
    started: false
  };

  function fetchStyle() {
    return fetch("/api/plugin/" + PLUGIN + "/style").then(function (r) { return r.json(); }).then(function (data) {
      var value = data && data.ok ? String(data.style || DEFAULT_STYLE) : DEFAULT_STYLE;
      return value === "minimal" ? "minimal" : DEFAULT_STYLE;
    }).catch(function () { return DEFAULT_STYLE; });
  }

  function currentTheme() {
    return document.documentElement.getAttribute("data-ui-theme") === "light" ? "light" : "dark";
  }

  function assetUrl(path) {
    return BASE + String(path || "").split("/").map(encodeURIComponent).join("/");
  }

  function styleById(id) {
    var list = state.catalog && state.catalog.styles;
    if (!Array.isArray(list)) return null;
    for (var i = 0; i < list.length; i++) {
      if (String(list[i].id || "") === String(id || "")) return list[i];
    }
    return null;
  }

  function clearAssets() {
    var nodes = document.querySelectorAll("[data-theme-style]");
    for (var i = nodes.length - 1; i >= 0; i--) nodes[i].remove();
    document.documentElement.removeAttribute("data-ui-style");
    state.loadedStyle = "";
  }

  function apply(id) {
    var style = styleById(id);
    if (!style) style = styleById(DEFAULT_STYLE);
    if (!style || !style.themes) {
      clearAssets();
      return;
    }
    clearAssets();
    document.documentElement.setAttribute("data-ui-style", String(style.id || DEFAULT_STYLE));
    state.loadedStyle = String(style.id || DEFAULT_STYLE);
    var spec = style.themes[currentTheme()] || {};
    (spec.css || []).forEach(function (path) {
      var link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = assetUrl(path);
      link.setAttribute("data-theme-style", state.loadedStyle);
      document.head.appendChild(link);
    });
    (spec.js || []).forEach(function (path) {
      var script = document.createElement("script");
      script.src = assetUrl(path);
      script.setAttribute("data-theme-style", state.loadedStyle);
      document.head.appendChild(script);
    });
  }

  function loadCatalog() {
    return fetch(BASE + "styles/catalog.json").then(function (r) { return r.json(); }).then(function (data) {
      state.catalog = data && typeof data === "object" ? data : null;
      var styles = state.catalog && Array.isArray(state.catalog.styles) ? state.catalog.styles : [];
      return Promise.all(styles.map(function (style) {
        if (!style.manifest) return Promise.resolve(style);
        return fetch(assetUrl(style.manifest)).then(function (r) { return r.json(); }).then(function (manifest) {
          style.themes = (manifest && manifest.themes) || {};
          return style;
        }).catch(function () { style.themes = {}; return style; });
      })).then(function () { return state.catalog; });
    }).catch(function () {
      state.catalog = null;
      return null;
    });
  }

  function onSettingsChanged() {
    fetchStyle().then(function (value) {
      state.selected = value;
      apply(value);
    });
  }

  function onPluginsChanged(ev) {
    var loaded = (ev && ev.detail && Array.isArray(ev.detail.loaded)) ? ev.detail.loaded : null;
    if (!loaded) return;
    if (loaded.indexOf(PLUGIN) < 0) {
      clearAssets();
      return;
    }
    start();
  }

  function bindOnce() {
    if (document._themeStyleBound) return;
    document._themeStyleBound = true;
    document.addEventListener("ai-agent:settings-changed", onSettingsChanged);
    document.addEventListener("ai-agent:plugins-changed", onPluginsChanged);
    window.addEventListener("error", function (ev) {
      var node = ev && ev.target;
      if (node && node.tagName === "SCRIPT" && node.hasAttribute("data-theme-style")) node.remove();
    }, true);
    var themeObserver = new MutationObserver(function () {
      if (state.selected && state.selected !== DEFAULT_STYLE) apply(state.selected);
    });
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["data-ui-theme"] });
  }

  function start() {
    bindOnce();
    Promise.all([loadCatalog(), fetchStyle()]).then(function (result) {
      state.selected = result[1] || DEFAULT_STYLE;
      apply(state.selected);
    });
  }

  window.__themeStyle = {
    start: start,
    apply: apply,
    current: function () { return state.selected; }
  };
  start();
})();
