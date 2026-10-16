(function () {
  var state = {sections: [], values: {}, tab: "", mode: "host", plugin: null, text: ""};

  function bootSettingsPanel() {
    var btn = document.getElementById("hdrSettingsBtn");
    if (!btn || btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", openSettings);
  }

  function request(method, url, body) {
    var opt = {method: method, headers: {"Accept": "application/json"}};
    if (body !== undefined) {
      opt.headers["Content-Type"] = "application/json";
      opt.body = JSON.stringify(body);
    }
    return fetch(url, opt).then(function (res) {
      return res.json().catch(function () {
        return {ok: false, error: "响应不是 JSON"};
      }).then(function (data) {
        if (!data || typeof data !== "object") return {ok: false, error: "响应不是 JSON"};
        if (!res.ok && !data.error) data.error = "请求失败";
        return data;
      });
    });
  }

  function mask() {
    var node = document.getElementById("stMask");
    if (node) return node;
    node = document.createElement("div");
    node.id = "stMask";
    node.className = "st-mask";
    node.innerHTML =
      '<div class="st-modal" role="dialog" aria-modal="true" aria-label="设置">' +
      '<div class="st-top"><button type="button" class="st-x" id="stClose" aria-label="关闭">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>' +
      "</button></div>" +
      '<div class="st-body"><nav class="st-nav" id="stNav"></nav><div class="st-main">' +
      '<div class="st-form" id="stForm"></div>' +
      '<div class="st-foot"><span class="st-status" id="stStatus"></span>' +
      '<button type="button" class="st-save" id="stSave">保存</button></div>' +
      "</div></div></div>";
    document.body.appendChild(node);
    node.addEventListener("click", function (ev) {
      if (ev.target === node) closeSettings();
    });
    document.getElementById("stClose").addEventListener("click", closeSettings);
    document.getElementById("stSave").addEventListener("click", onSave);
    return node;
  }

  function setStatus(text, bad) {
    var node = document.getElementById("stStatus");
    if (!node) return;
    node.textContent = text || "";
    node.classList.toggle("is-bad", !!bad);
    syncFoot();
  }

  function syncFoot() {
    var foot = document.querySelector(".st-foot");
    var save = document.getElementById("stSave");
    var node = document.getElementById("stStatus");
    if (!foot) return;
    var hasText = !!(node && node.textContent);
    var showSave = !!(save && !save.hidden);
    foot.hidden = !hasText && !showSave;
  }

  function closeSettings() {
    var node = document.getElementById("stMask");
    if (node) node.remove();
    document.removeEventListener("keydown", onKey);
  }

  function onKey(ev) {
    if (ev.key === "Escape") closeSettings();
  }

  function openSettings() {
    if (document.getElementById("stMask")) return;
    mask();
    document.addEventListener("keydown", onKey);
    setStatus("");
    request("GET", "/api/settings").then(function (data) {
      if (!data.ok) {
        setStatus(data.error || "读取设置失败", true);
        return;
      }
      state.sections = data.sections || [];
      state.values = {};
      state.sections.forEach(function (sec) {
        state.values[sec.id] = {};
        (sec.fields || []).forEach(function (field) {
          state.values[sec.id][field.key] = field.value == null ? "" : String(field.value);
        });
      });
      state.mode = "host";
      state.tab = state.sections.length ? state.sections[0].id : "";
      state.plugin = null;
      renderNav();
      renderHost();
    }).catch(function () {
      setStatus("读取设置失败", true);
    });
  }

  function renderNav() {
    var nav = document.getElementById("stNav");
    if (!nav) return;
    nav.textContent = "";
    state.sections.forEach(function (sec) {
      nav.appendChild(navButton(sec.title, state.mode === "host" && state.tab === sec.id, function () {
        state.mode = "host";
        state.tab = sec.id;
        state.plugin = null;
        setStatus("");
        renderNav();
        renderHost();
      }));
    });
    var gap = document.createElement("div");
    gap.className = "st-nav-gap";
    nav.appendChild(gap);
    nav.appendChild(navButton("插件", state.mode !== "host", function () {
      state.mode = "plugins";
      state.plugin = null;
      setStatus("");
      renderNav();
      renderPlugins();
    }));
  }

  function navButton(label, on, click) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = label;
    if (on) btn.className = "is-on";
    btn.addEventListener("click", click);
    return btn;
  }

  function currentSection() {
    for (var i = 0; i < state.sections.length; i++) {
      if (state.sections[i].id === state.tab) return state.sections[i];
    }
    return null;
  }

  function renderHost() {
    var form = document.getElementById("stForm");
    var save = document.getElementById("stSave");
    if (!form) return;
    form.textContent = "";
    if (save) save.hidden = false;
    syncFoot();
    var sec = currentSection();
    if (!sec) return;
    (sec.fields || []).forEach(function (field) {
      form.appendChild(fieldRow(sec.id, field));
    });
  }

  function fieldRow(sectionId, field) {
    var row = document.createElement("div");
    row.className = "st-row";
    var label = document.createElement("label");
    label.textContent = field.label;
    var box = document.createElement("div");
    box.appendChild(fieldControl(sectionId, field));
    if (field.hint) {
      var hint = document.createElement("div");
      hint.className = "st-hint";
      hint.textContent = field.hint;
    }
    if (field.hint) box.appendChild(hint);
    row.appendChild(label);
    row.appendChild(box);
    return row;
  }

  function fieldControl(sectionId, field) {
    var value = state.values[sectionId][field.key] || "";
    if (field.kind === "bool") return boolControl(sectionId, field, value);
    if (field.kind === "enum") return enumControl(sectionId, field, value);
    if (field.kind === "dir") return dirControl(sectionId, field, value);
    var input = document.createElement("input");
    input.type = field.kind === "secret" ? "password" : (field.kind === "number" ? "number" : "text");
    if (field.kind === "number") input.step = "1";
    if (field.kind === "secret") {
      input.value = "";
      input.autocomplete = "off";
      input.placeholder = field.placeholder || (field.configured ? "已设置秘钥,可重新设置并替换" : "未配置秘钥");
      state.values[sectionId][field.key] = "";
    } else {
      input.value = value;
    }
    input.addEventListener("input", function () {
      state.values[sectionId][field.key] = input.value;
    });
    return input;
  }

  function boolControl(sectionId, field, value) {
    var wrap = document.createElement("label");
    wrap.className = "st-switch";
    var input = document.createElement("input");
    input.type = "checkbox";
    input.checked = value === "1";
    input.addEventListener("change", function () {
      state.values[sectionId][field.key] = input.checked ? "1" : "0";
    });
    var knob = document.createElement("i");
    wrap.appendChild(input);
    wrap.appendChild(knob);
    return wrap;
  }

  function enumControl(sectionId, field, value) {
    var select = document.createElement("select");
    (field.options || []).forEach(function (opt) {
      var option = document.createElement("option");
      option.value = opt.value;
      option.textContent = opt.label || opt.value;
      if (opt.value === value) option.selected = true;
      select.appendChild(option);
    });
    state.values[sectionId][field.key] = select.value;
    select.addEventListener("change", function () {
      state.values[sectionId][field.key] = select.value;
    });
    return select;
  }

  function dirControl(sectionId, field, value) {
    var wrap = document.createElement("div");
    wrap.className = "st-dir";
    var input = document.createElement("input");
    input.type = "text";
    input.value = value;
    input.addEventListener("input", function () {
      state.values[sectionId][field.key] = input.value;
    });
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "st-mini";
    btn.textContent = "选择目录";
    btn.addEventListener("click", function () {
      pickDir(btn, function (path) {
        input.value = path;
        state.values[sectionId][field.key] = path;
      });
    });
    wrap.appendChild(input);
    wrap.appendChild(btn);
    return wrap;
  }

  function pickDir(btn, done) {
    btn.disabled = true;
    var prev = btn.textContent;
    btn.textContent = "选择中…";
    request("POST", "/api/settings/pick-dir", {}).then(function (data) {
      btn.disabled = false;
      btn.textContent = prev;
      if (data.cancelled) return;
      if (!data.ok) {
        setStatus(data.error || "没有选到目录", true);
        return;
      }
      done(data.path || "");
    }).catch(function () {
      btn.disabled = false;
      btn.textContent = prev;
      setStatus("目录选择失败", true);
    });
  }

  function onSave() {
    if (state.mode === "plugin-file") savePluginFile();
    else if (state.mode === "host") saveHost();
  }

  function saveHost() {
    var save = document.getElementById("stSave");
    if (save) save.disabled = true;
    setStatus("保存中…");
    request("POST", "/api/settings", {values: state.values}).then(function (data) {
      if (save) save.disabled = false;
      if (!data.ok) {
        setStatus(data.error || "保存失败", true);
        return;
      }
      applyWebUi(data.web_ui);
      clearSavedSecrets();
      setStatus(data.reload_error ? ("已写入，但生效失败：" + data.reload_error) : "已保存", !!data.reload_error);
    }).catch(function () {
      if (save) save.disabled = false;
      setStatus("保存失败", true);
    });
  }

  function clearSavedSecrets() {
    state.sections.forEach(function (sec) {
      (sec.fields || []).forEach(function (field) {
        if (field.kind !== "secret") return;
        if (state.values[sec.id][field.key]) {
          field.configured = true;
          field.placeholder = "已设置秘钥,可重新设置并替换";
        }
        state.values[sec.id][field.key] = "";
      });
    });
    if (state.mode === "host") renderHost();
  }

  function applyWebUi(flags) {
    if (!flags) return;
    window.__webUi = flags;
    if (flags.display_tool_steps) {
      document.documentElement.removeAttribute("data-tool-steps");
      if (typeof setClassicSideOpen === "function") setClassicSideOpen(true);
    } else {
      document.documentElement.setAttribute("data-tool-steps", "off");
    }
  }

  function renderPlugins() {
    var form = document.getElementById("stForm");
    var save = document.getElementById("stSave");
    if (!form) return;
    form.textContent = "加载插件…";
    if (save) save.hidden = true;
    syncFoot();
    request("GET", "/api/settings/plugins").then(function (data) {
      form.textContent = "";
      if (!data.ok) {
        setStatus(data.error || "读取插件失败", true);
        return;
      }
      var cards = data.plugins || [];
      if (!cards.length) {
        var empty = document.createElement("div");
        empty.className = "st-empty";
        empty.textContent = "plugins 目录里没有插件";
        form.appendChild(empty);
        return;
      }
      cards.forEach(function (card) { form.appendChild(pluginCard(card)); });
    }).catch(function () {
      form.textContent = "";
      setStatus("读取插件失败", true);
    });
  }

  function pluginCard(card) {
    var row = document.createElement("div");
    row.className = "st-card";
    var info = document.createElement("div");
    info.className = "st-card-main";
    var name = document.createElement("div");
    name.className = "st-card-name";
    if (card.icon) {
      var ico = document.createElement("span");
      ico.className = "st-ico";
      ico.textContent = card.icon;
      name.appendChild(ico);
    }
    var title = document.createElement("b");
    title.textContent = card.title || card.name;
    name.appendChild(title);
    if (card.version) {
      var ver = document.createElement("sub");
      ver.className = "st-ver";
      ver.textContent = card.version;
      name.appendChild(ver);
    }
    info.appendChild(name);
    if (card.description) {
      var meta = document.createElement("div");
      meta.className = "st-meta";
      meta.textContent = card.description;
      info.appendChild(meta);
    }
    var actions = document.createElement("div");
    actions.className = "st-card-actions";
    var setting = document.createElement("button");
    setting.type = "button";
    setting.className = "st-mini";
    setting.textContent = "设置";
    setting.disabled = !card.configurable;
    setting.addEventListener("click", function () { openPlugin(card); });
    actions.appendChild(setting);
    actions.appendChild(pluginSwitch(card));
    row.appendChild(info);
    row.appendChild(actions);
    return row;
  }

  function pluginSwitch(card) {
    var wrap = document.createElement("label");
    wrap.className = "st-switch";
    var input = document.createElement("input");
    input.type = "checkbox";
    input.checked = !!card.enabled;
    input.addEventListener("change", function () {
      var want = input.checked;
      request("POST", "/api/settings/plugins", {name: card.name, enabled: want}).then(function (data) {
        if (!data.ok) {
          input.checked = !want;
          setStatus(data.error || "没有改成", true);
          return;
        }
        var bad = (data.reports || []).filter(function (item) { return item.status === "error"; });
        setStatus(bad.length ? bad[0].message : "", bad.length > 0);
      }).catch(function () {
        input.checked = !want;
        setStatus("请求失败", true);
      });
    });
    var knob = document.createElement("i");
    wrap.appendChild(input);
    wrap.appendChild(knob);
    return wrap;
  }

  function openPlugin(card) {
    state.mode = "plugin-file";
    state.plugin = card;
    renderNav();
    var form = document.getElementById("stForm");
    var save = document.getElementById("stSave");
    if (!form) return;
    form.textContent = "加载配置…";
    if (save) save.hidden = false;
    syncFoot();
    request("GET", "/api/settings/plugin-file?name=" + encodeURIComponent(card.name)).then(function (data) {
      form.textContent = "";
      if (!data.ok) {
        setStatus(data.error || "读取插件配置失败", true);
        return;
      }
      state.text = data.text || "";
      form.appendChild(pluginEditor(card));
    }).catch(function () {
      form.textContent = "";
      setStatus("读取插件配置失败", true);
    });
  }

  function pluginEditor(card) {
    var wrap = document.createElement("div");
    var bar = document.createElement("div");
    bar.className = "st-editor-bar";
    var back = document.createElement("button");
    back.type = "button";
    back.className = "st-back";
    back.textContent = "返回";
    back.addEventListener("click", function () {
      state.mode = "plugins";
      state.plugin = null;
      setStatus("");
      renderNav();
      renderPlugins();
    });
    var title = document.createElement("b");
    title.textContent = (card.title || card.name) + "配置";
    var area = document.createElement("textarea");
    area.id = "stPluginText";
    area.value = state.text;
    area.spellcheck = false;
    if (!state.text) area.placeholder = "这里编辑 plugin-config.ini。还没有这个文件时，保存会创建它。";
    area.addEventListener("input", function () { state.text = area.value; });
    bar.appendChild(back);
    bar.appendChild(title);
    wrap.appendChild(bar);
    wrap.appendChild(area);
    return wrap;
  }

  function savePluginFile() {
    if (!state.plugin) return;
    var save = document.getElementById("stSave");
    if (save) save.disabled = true;
    setStatus("保存中…");
    request("POST", "/api/settings/plugin-file", {
      name: state.plugin.name,
      text: state.text,
    }).then(function (data) {
      if (save) save.disabled = false;
      if (!data.ok) {
        setStatus(data.error || "保存失败", true);
        return;
      }
      var bad = (data.reports || []).filter(function (item) { return item.status === "error"; });
      setStatus(bad.length ? bad[0].message : "已保存", bad.length > 0);
    }).catch(function () {
      if (save) save.disabled = false;
      setStatus("保存失败", true);
    });
  }

  bootSettingsPanel();
})();
