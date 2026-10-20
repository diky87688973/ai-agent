/* multi_model/ui/model-picker.js —— 输入区的模型下拉（插件资产）。
 *
 * 壳层只提供挂载点 `#modelPickerSlot` 与公共桥
 * `window.aiAgentShell.models`；按钮、菜单、选中态都由本插件渲染。
 * 样式走壳层的样式桥按需注入，插件不拼 URL、不碰 `document.head`。
 *
 * 条目未取到之前按钮显示"模型加载中…"；目录为空时显示"无可用模型"，
 * 但不阻塞输入 —— 发送仍由服务端按会话状态决定用哪个模型。
 */
(function () {
  "use strict";

  var PLUGIN = String(window.aiAgentPluginCurrent || "").trim();
  var shell = window.aiAgentShell;
  if (!PLUGIN || !shell || !shell.models || !shell.styles) return;

  shell.styles.load("ui/model-picker.css");

  function boot() {
    var slot = document.getElementById("modelPickerSlot");
    if (!slot) return;
    /* 插件被停用再启用时，壳层会重新执行这段开屏脚本。
       先拆掉上一次挂上去的 DOM 与监听，再按最新目录重建 ——
       只靠"已经启动过"的全局开关的话，重新启用后挂载点会一直空着。 */
    if (typeof window.__multiModelPickerTeardown === "function") {
      try { window.__multiModelPickerTeardown(); } catch (e) {}
      window.__multiModelPickerTeardown = null;
    }

    var api = window.aiAgentPlugins && window.aiAgentPlugins.for
      ? window.aiAgentPlugins.for(PLUGIN)
      : null;

    var root = document.createElement("div");
    root.className = "mm-picker";
    root.setAttribute("data-plugin", PLUGIN);

    var button = document.createElement("button");
    button.type = "button";
    button.className = "mode-plus mm-picker-btn";
    button.title = "选择模型";
    button.setAttribute("aria-haspopup", "listbox");
    button.setAttribute("aria-expanded", "false");

    var caption = document.createElement("span");
    caption.className = "mm-picker-label";
    caption.textContent = "模型加载中…";
    var caret = document.createElement("span");
    caret.className = "mm-picker-caret";
    caret.textContent = "▾";
    caret.setAttribute("aria-hidden", "true");
    button.appendChild(caption);
    button.appendChild(caret);

    var menu = document.createElement("div");
    menu.className = "mm-picker-menu hidden";
    menu.setAttribute("role", "listbox");
    menu.setAttribute("aria-label", "模型");

    root.appendChild(button);
    root.appendChild(menu);
    slot.innerHTML = "";
    slot.appendChild(root);

    var state = {
      models: [],
      current: String(shell.models.current() || ""),
      defaultId: "",
      invalid: [],
      open: false,
      busy: false,
      loading: true
    };

    function labelFor(id) {
      for (var i = 0; i < state.models.length; i++) {
        if (state.models[i].id === id) return state.models[i].label || id;
      }
      return id;
    }

    function close() {
      state.open = false;
      menu.classList.add("hidden");
      button.setAttribute("aria-expanded", "false");
    }

    function open() {
      state.open = true;
      menu.classList.remove("hidden");
      button.setAttribute("aria-expanded", "true");
      var current = null;
      for (var i = 0; i < menu.children.length; i++) {
        var node = menu.children[i];
        if (node.getAttribute && node.getAttribute("data-model") === state.current) {
          current = node;
          break;
        }
      }
      if (current && typeof current.focus === "function") current.focus();
    }

    function render() {
      menu.innerHTML = "";
      if (!state.models.length) {
        var empty = document.createElement("div");
        empty.className = "mm-picker-empty";
        empty.textContent = state.loading
          ? "模型加载中…"
          : "未配置模型。打开设置 → 插件 → 多模型，添加网关。";
        menu.appendChild(empty);
        if (!state.loading) {
          var configure = document.createElement("button");
          configure.type = "button";
          configure.className = "mm-picker-item";
          configure.textContent = "打开设置";
          configure.setAttribute("data-mm-settings", "1");
          menu.appendChild(configure);
        }
      } else {
        state.models.forEach(function (item) {
          var choice = document.createElement("button");
          choice.type = "button";
          choice.className = "mm-picker-item";
          choice.setAttribute("role", "option");
          choice.setAttribute("data-model", item.id);
          choice.setAttribute("aria-selected", item.id === state.current ? "true" : "false");
          if (item.id === state.current) choice.classList.add("mm-picker-current");
          var name = document.createElement("span");
          name.className = "mm-picker-name";
          name.textContent = item.label || item.id;
          choice.appendChild(name);
          if (item.provider) {
            var badge = document.createElement("span");
            badge.className = "mm-picker-provider";
            badge.textContent = item.provider === "openai"
              ? "OpenAI" : item.provider === "anthropic"
                ? "Anthropic" : item.provider;
            choice.appendChild(badge);
          }
          menu.appendChild(choice);
        });
      }
      if (state.invalid.length) {
        var bad = document.createElement("div");
        bad.className = "mm-picker-invalid";
        bad.textContent = "⚠ " + state.invalid.length + " 条配置无效";
        bad.title = state.invalid.map(function (item) {
          return (item.id ? "[" + item.id + "] " : "") + (item.reason || "");
        }).join("\n");
        menu.appendChild(bad);
      }
      var shown = state.current || state.defaultId
        || (state.models.length ? state.models[0].id : "");
      caption.textContent = labelFor(shown) || (state.loading ? "模型加载中…" : "未配置模型");
      button.disabled = false;
      button.title = state.models.length ? "选择模型" : "未配置模型，打开设置 → 插件 → 多模型";
    }

    function select(id) {
      var want = String(id || "").trim();
      if (!want || state.busy || want === state.current) {
        close();
        return;
      }
      state.busy = true;
      close();
      shell.models.select(want).then(function (ok) {
        state.busy = false;
        if (ok) {
          state.current = want;
          render();
        }
      });
    }

    function applyCatalog(data) {
      if (!data || typeof data !== "object") return false;
      state.invalid = Array.isArray(data.invalid) ? data.invalid : [];
      state.defaultId = String(data.default || "");
      var models = Array.isArray(data.models) ? data.models : [];
      if (!models.length) return false;
      state.models = models.map(function (item) {
        return {
          id: String(item.id || ""),
          label: String(item.label || item.id || ""),
          provider: String(item.provider || "")
        };
      }).filter(function (item) { return !!item.id; });
      return state.models.length > 0;
    }

    function loadCatalog() {
      var request = api
        ? api.get("catalog").then(function (res) {
            return res && res.ok ? res.data : null;
          })
        : Promise.resolve(null);
      return request.catch(function () { return null; }).then(function (data) {
        if (applyCatalog(data)) {
          state.loading = false;
          render();
          return;
        }
        /* 目录端点不可用（插件未装载完整）时退回壳层清单：至少能显示 id。 */
        return shell.models.list().then(function (list) {
          state.models = (Array.isArray(list) ? list : []).map(function (item) {
            return {
              id: String(item.id || ""),
              label: String(item.label || item.id || ""),
              provider: String(item.provider || "")
            };
          }).filter(function (item) { return !!item.id; });
          state.loading = false;
          render();
        });
      });
    }

    button.addEventListener("click", function (event) {
      event.stopPropagation();
      if (state.open) close();
      else open();
    });
    function onMenuClick(event) {
      event.stopPropagation();
      var target = event.target;
      var choice = target && target.closest ? target.closest("[data-model]") : null;
      if (choice) {
        select(choice.getAttribute("data-model"));
        return;
      }
      if (target && target.closest && target.closest("[data-mm-settings]")) {
        close();
        var settings = document.getElementById("hdrSettingsBtn");
        if (settings) settings.click();
      }
    }
    function onDocClick(event) {
      if (state.open && !root.contains(event.target)) close();
    }
    function onDocKeydown(event) {
      if (event.key === "Escape" && state.open) close();
    }
    var offModelChange = shell.models.onChange(function (id) {
      state.current = String(id || "");
      render();
    });
    menu.addEventListener("click", onMenuClick);
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onDocKeydown);
    /* 重新启用时旧实例必须把这三样一起还回去：DOM、文档级监听、模型订阅。
       漏一样就会在新实例之外留一份仍会响应事件的幽灵下拉。 */
    window.__multiModelPickerTeardown = function () {
      menu.removeEventListener("click", onMenuClick);
      document.removeEventListener("click", onDocClick);
      document.removeEventListener("keydown", onDocKeydown);
      if (typeof offModelChange === "function") offModelChange();
      if (root.parentNode) root.parentNode.removeChild(root);
    };

    render();
    loadCatalog();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
