(function () {
  var state = {
    sections: [], values: {}, tab: "", mode: "host",
    pluginCards: [], plugin: null, editor: null, direct: false, saving: false
  };

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
      '<div class="st-foot-actions">' +
      '<button type="button" class="st-apply" id="stApply" hidden>应用</button>' +
      '<button type="button" class="st-save" id="stSave">保存</button>' +
      "</div></div></div></div></div>";
    document.body.appendChild(node);
    node.addEventListener("click", function (ev) {
      if (ev.target === node) closeSettings();
    });
    var delegateSettingsButton = function (ev) {
      var btn = ev.target && ev.target.closest ? ev.target.closest("button") : null;
      if (btn && typeof btn._settingsClick === "function") btn._settingsClick();
    };
    var nav = document.getElementById("stNav");
    var form = document.getElementById("stForm");
    if (nav) nav.addEventListener("click", delegateSettingsButton);
    if (form) form.addEventListener("click", delegateSettingsButton);
    document.getElementById("stClose").addEventListener("click", closeSettings);
    document.getElementById("stSave").addEventListener("click", function () {
      onSave(true);
    });
    document.getElementById("stApply").addEventListener("click", function () {
      onSave(false);
    });
    return node;
  }

  function setStatus(text, bad) {
    var node = document.getElementById("stStatus");
    if (!node) return;
    node.textContent = text || "";
    node.classList.toggle("is-bad", !!bad);
    syncFoot();
  }

  function showApply(show) {
    var apply = document.getElementById("stApply");
    if (apply) apply.hidden = !show;
  }

  function setBusy(busy) {
    state.saving = !!busy;
    ["stSave", "stApply"].forEach(function (id) {
      var node = document.getElementById(id);
      if (node) node.disabled = !!busy;
    });
  }

  function syncFoot() {
    var foot = document.querySelector(".st-foot");
    var save = document.getElementById("stSave");
    var apply = document.getElementById("stApply");
    var node = document.getElementById("stStatus");
    if (!foot) return;
    var hasText = !!(node && node.textContent);
    var showSave = !!(save && !save.hidden);
    var showAny = showSave || !!(apply && !apply.hidden);
    foot.hidden = !hasText && !showAny;
  }

  function closeSettings() {
    var node = document.getElementById("stMask");
    if (node) node.remove();
    document.removeEventListener("keydown", onKey);
    setBusy(false);
  }

  function onKey(ev) {
    if (ev.key === "Escape") closeSettings();
  }

  function openSettings() {
    if (document.getElementById("stMask")) return;
    mask();
    document.addEventListener("keydown", onKey);
    setStatus("");
    Promise.all([
      request("GET", "/api/settings"),
      request("GET", "/api/settings/plugins")
    ]).then(function (result) {
      var data = result[0] || {};
      var plugins = result[1] || {};
      if (!data.ok) {
        setStatus(data.error || "读取设置失败", true);
        return;
      }
      adoptSections(data.sections, true);
      state.pluginCards = plugins.ok && Array.isArray(plugins.plugins)
        ? plugins.plugins : [];
      state.mode = "host";
      state.tab = state.sections.length ? state.sections[0].id : "";
      state.plugin = null;
      state.editor = null;
      state.direct = false;
      renderNav();
      renderHost();
    }).catch(function () {
      setStatus("读取设置失败", true);
    });
  }

  function adoptSections(sections, reset) {
    var old = state.values || {};
    state.sections = Array.isArray(sections) ? sections : [];
    var values = {};
    state.sections.forEach(function (sec) {
      values[sec.id] = {};
      (sec.fields || []).forEach(function (field) {
        var kept = !reset && old[sec.id]
          && Object.prototype.hasOwnProperty.call(old[sec.id], field.key);
        values[sec.id][field.key] = kept
          ? old[sec.id][field.key]
          : (field.value == null ? "" : String(field.value));
      });
    });
    state.values = values;
  }

  /* 插件开关会改变可用入口；重取目录与插件卡片后重绘导航。 */
  function refreshHostSections() {
    return Promise.all([
      request("GET", "/api/settings"),
      request("GET", "/api/settings/plugins")
    ]).then(function (result) {
      var data = result[0] || {};
      var plugins = result[1] || {};
      if (!data.ok) return;
      adoptSections(data.sections, false);
      state.pluginCards = plugins.ok && Array.isArray(plugins.plugins)
        ? plugins.plugins : [];
      if (state.mode === "host" && !currentSection()) {
        state.tab = state.sections.length ? state.sections[0].id : "";
      }
      if (state.mode === "plugin-file" && state.direct && !directCards().some(function (card) {
        return state.plugin && card.name === state.plugin.name;
      })) {
        state.mode = "host";
        state.plugin = null;
        state.editor = null;
        state.direct = false;
        state.tab = state.sections.length ? state.sections[0].id : "";
      }
      renderNav();
      if (state.mode === "host") renderHost();
    }).catch(function () {
      setStatus("设置入口刷新失败", true);
      return null;
    });
  }

  function directCards() {
    return (state.pluginCards || []).filter(function (card) {
      return card.settings_tab && card.enabled && card.configurable;
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
        state.editor = null;
        state.direct = false;
        setStatus("");
        renderNav();
        renderHost();
      }));
    });
    directCards().forEach(function (card) {
      var on = state.mode === "plugin-file" && state.direct
        && state.plugin && state.plugin.name === card.name;
      nav.appendChild(navButton(card.settings_tab, !!on, function () {
        openPlugin(card, true);
      }));
    });
    var gap = document.createElement("div");
    gap.className = "st-nav-gap";
    nav.appendChild(gap);
    var pluginTabOn = state.mode === "plugins"
      || (state.mode === "plugin-file" && !state.direct);
    nav.appendChild(navButton("插件", pluginTabOn, function () {
      state.mode = "plugins";
      state.plugin = null;
      state.editor = null;
      state.direct = false;
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
    btn._settingsClick = click;
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
    form.classList.remove("st-form-editor");
    form.textContent = "";
    if (save) save.hidden = false;
    showApply(true);
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
      box.appendChild(hint);
    }
    row.appendChild(label);
    row.appendChild(box);
    return row;
  }

  function fieldControl(sectionId, field) {
    var value = state.values[sectionId][field.key] || "";
    if (field.kind === "bool") return boolControl(value, function (next) {
      state.values[sectionId][field.key] = next;
    });
    if (field.kind === "enum") return enumControl(field, value, function (next) {
      state.values[sectionId][field.key] = next;
    });
    if (field.kind === "dir") return dirControl(value, function (next) {
      state.values[sectionId][field.key] = next;
    });
    var input = document.createElement("input");
    input.type = field.kind === "secret" ? "password" : (field.kind === "number" ? "number" : "text");
    if (field.kind === "number") input.step = "1";
    if (field.kind === "secret") {
      input.value = "";
      input.autocomplete = "off";
      input.placeholder = field.configured
        ? secretPlaceholder(true)
        : (field.placeholder || secretPlaceholder(false));
      state.values[sectionId][field.key] = "";
    } else {
      input.value = value;
      if (field.placeholder) input.placeholder = field.placeholder;
    }
    input.addEventListener("input", function () {
      state.values[sectionId][field.key] = input.value;
    });
    return input;
  }

  function secretPlaceholder(configured) {
    return configured ? "已设置秘钥,可重新设置并替换" : "未配置秘钥";
  }

  function boolControl(value, onChange) {
    var wrap = document.createElement("label");
    wrap.className = "st-switch";
    var input = document.createElement("input");
    input.type = "checkbox";
    input.checked = value === "1";
    input.addEventListener("change", function () {
      onChange(input.checked ? "1" : "0");
    });
    var knob = document.createElement("i");
    wrap.appendChild(input);
    wrap.appendChild(knob);
    return wrap;
  }

  function enumControl(field, value, onChange) {
    var select = document.createElement("select");
    if (field.required) select.required = true;
    (field.options || []).forEach(function (opt) {
      var option = document.createElement("option");
      option.value = opt.value;
      option.textContent = opt.label || opt.value;
      if (opt.value === value) option.selected = true;
      select.appendChild(option);
    });
    onChange(select.value);
    select.addEventListener("change", function () {
      onChange(select.value);
      setStatus("");
    });
    return select;
  }

  function dirControl(value, onChange) {
    var wrap = document.createElement("div");
    wrap.className = "st-dir";
    var input = document.createElement("input");
    input.type = "text";
    input.value = value;
    input.addEventListener("input", function () {
      onChange(input.value);
    });
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "st-mini";
    btn.textContent = "选择目录";
    btn._settingsClick = function () {
      pickDir(btn, function (path) {
        input.value = path;
        onChange(path);
      });
    };
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

  function onSave(closeAfter) {
    if (state.saving) return;
    if (state.mode === "plugin-file") savePluginFile(closeAfter);
    else if (state.mode === "host") saveHost(closeAfter);
  }

  function saveHost(closeAfter) {
    setBusy(true);
    setStatus("保存中…");
    request("POST", "/api/settings", {values: state.values}).then(function (data) {
      setBusy(false);
      if (!data.ok) {
        setStatus(data.error || "保存失败", true);
        return;
      }
      applyWebUi(data.web_ui);
      clearSavedSecrets();
      if (data.reload_error) {
        // 写盘成功但没生效：按失败处理，窗口保持打开并显示原因。
        setStatus("已写入，但生效失败：" + data.reload_error, true);
        return;
      }
      if (closeAfter) {
        closeSettings();
        return;
      }
      setStatus(data.reload_note ? ("已应用；" + data.reload_note) : "已应用");
    }).catch(function () {
      setBusy(false);
      setStatus("保存失败", true);
    });
  }

  function clearSavedSecrets() {
    state.sections.forEach(function (sec) {
      (sec.fields || []).forEach(function (field) {
        if (field.kind !== "secret") return;
        if (state.values[sec.id][field.key]) {
          field.configured = true;
          field.placeholder = secretPlaceholder(true);
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
    form.classList.remove("st-form-editor");
    form.textContent = "";
    if (save) save.hidden = true;
    showApply(false);
    syncFoot();
    request("GET", "/api/settings/plugins").then(function (data) {
      form.textContent = "";
      if (!data.ok) {
        setStatus(data.error || "读取插件失败", true);
        return;
      }
      var cards = data.plugins || [];
      state.pluginCards = cards;
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
    /* 编辑入口由插件声明决定：configurable 为假就是没有可改的东西，
       不渲染一个点不动的按钮占位。 */
    if (card.configurable) {
      var setting = document.createElement("button");
      setting.type = "button";
      setting.className = "st-mini";
      setting.textContent = "设置";
      setting._settingsClick = function () { openPlugin(card); };
      actions.appendChild(setting);
    }
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
      input.disabled = true;
      request("POST", "/api/settings/plugins", {name: card.name, enabled: want}).then(function (data) {
        input.disabled = false;
        if (!data.ok) {
          input.checked = !want;
          setStatus(data.error || "没有改成", true);
          return;
        }
        var bad = (data.reports || []).filter(function (item) { return item.status === "error"; });
        setStatus(bad.length ? bad[0].message : "", bad.length > 0);
        // 开关会改变可用插件入口；立即重取并重绘。
        refreshHostSections();
      }).catch(function () {
        input.disabled = false;
        input.checked = !want;
        setStatus("请求失败", true);
      });
    });
    var knob = document.createElement("i");
    wrap.appendChild(input);
    wrap.appendChild(knob);
    return wrap;
  }

  function openPlugin(card, direct) {
    state.mode = "plugin-file";
    state.plugin = card;
    state.editor = null;
    state.direct = !!direct;
    renderNav();
    var form = document.getElementById("stForm");
    var save = document.getElementById("stSave");
    if (!form) return;
    form.classList.remove("st-form-editor");
    form.textContent = "";
    if (save) save.hidden = false;
    showApply(true);
    syncFoot();
    request("GET", "/api/settings/plugin-file?name=" + encodeURIComponent(card.name)).then(function (data) {
      if (!data.ok) {
        setStatus(data.error || "读取插件配置失败", true);
        return;
      }
      state.editor = data.editor || {kind: "text", text: ""};
      try {
        renderPluginEditor(card);
      } catch (err) {
        form.textContent = "";
        setStatus("配置已读取，但编辑器渲染失败：" + ((err && err.message) || "未知错误"), true);
        return;
      }
      setStatus("");
    }).catch(function (err) {
      setStatus("读取插件配置失败" + (err && err.message ? "：" + err.message : ""), true);
    });
  }

  function renderPluginEditor(card) {
    var form = document.getElementById("stForm");
    if (!form) return;
    var editor = state.editor || {};
    form.textContent = "";
    if (editor.kind === "sections") {
      form.classList.remove("st-form-editor");
      form.appendChild(structuredEditor(card, editor));
      return;
    }
    if (editor.kind === "fields") {
      form.classList.remove("st-form-editor");
      form.appendChild(fieldsEditor(card, editor));
      return;
    }
    form.classList.add("st-form-editor");
    form.appendChild(textEditor(card, editor));
  }

  function editorBar(card) {
    var bar = document.createElement("div");
    bar.className = "st-editor-bar";
    if (!state.direct) {
      var back = document.createElement("button");
      back.type = "button";
      back.className = "st-back";
      back.setAttribute("aria-label", "返回");
      back.title = "返回";
      back.innerHTML =
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
        '<path d="M14.5 5.5L8 12l6.5 6.5"/></svg>';
      back._settingsClick = function () {
        state.mode = "plugins";
        state.plugin = null;
        state.editor = null;
        state.direct = false;
        setStatus("");
        renderNav();
        renderPlugins();
      };
      bar.appendChild(back);
    }
    var title = document.createElement("b");
    title.textContent = (card.title || card.name) + "配置";
    bar.appendChild(title);
    return bar;
  }

  function textEditor(card, editor) {
    var wrap = document.createElement("div");
    wrap.className = "st-editor";
    var area = document.createElement("textarea");
    area.id = "stPluginText";
    area.placeholder = "plugin-config.ini";
    area.value = editor.text || "";
    area.spellcheck = false;
    area.addEventListener("input", function () { editor.text = area.value; });
    wrap.appendChild(editorBar(card));
    wrap.appendChild(area);
    return wrap;
  }

  function fieldsEditor(card, editor) {
    var schema = editor.schema || {};
    var values = editor.values || {};
    var wrap = document.createElement("div");
    wrap.className = "st-editor st-editor-form";
    wrap.appendChild(editorBar(card));
    var group = {values: values, configured: editor.configured || {}};
    (schema.fields || []).forEach(function (field) {
      wrap.appendChild(structuredRow(schema, group, field));
    });
    return wrap;
  }

  function structuredEditor(card, editor) {
    var schema = editor.schema || {};
    var wrap = document.createElement("div");
    wrap.className = "st-editor st-editor-form";
    var list = document.createElement("div");
    list.className = "st-models";
    drawModels(list, schema, editor.groups || []);
    var add = document.createElement("button");
    add.type = "button";
    add.className = "st-add";
    add.textContent = "+ " + (schema.add_label || "添加");
    add._settingsClick = function () {
      editor.groups = editor.groups || [];
      editor.groups.push({id: "", notes: "", values: {}, configured: {}, extras: []});
      drawModels(list, schema, editor.groups);
    };
    wrap.appendChild(editorBar(card));
    wrap.appendChild(list);
    wrap.appendChild(add);
    return wrap;
  }

  function drawModels(list, schema, groups) {
    list.textContent = "";
    if (!groups.length) {
      var empty = document.createElement("div");
      empty.className = "st-empty";
      empty.textContent = schema.empty_text || "还没有配置项。";
      list.appendChild(empty);
      return;
    }
    groups.forEach(function (group, index) {
      list.appendChild(modelCard(schema, group, index, list));
    });
  }

  function modelCard(schema, group, index, list) {
    var card = document.createElement("div");
    card.className = "st-model";
    var head = document.createElement("div");
    head.className = "st-model-head";
    var badge = document.createElement("span");
    badge.className = "st-model-index";
    badge.textContent = "#" + (index + 1);
    var del = document.createElement("button");
    del.type = "button";
    del.className = "st-model-del";
    del.title = "删除这条配置";
    del.setAttribute("aria-label", "删除这条配置");
    del.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
      'stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';
    del._settingsClick = function () {
      var groups = state.editor.groups || [];
      groups.splice(index, 1);
      drawModels(list, schema, groups);
    };
    head.appendChild(badge);
    head.appendChild(del);
    card.appendChild(head);
    var body = document.createElement("div");
    body.className = "st-model-body";
    (schema.fields || []).forEach(function (field) {
      var row = structuredRow(schema, group, field);
      row.hidden = !fieldVisible(schema, group, field);
      body.appendChild(row);
    });
    card.appendChild(body);
    return card;
  }

  function structuredRow(schema, group, field) {
    var row = document.createElement("div");
    row.className = "st-row";
    row.dataset.field = field.key;
    var label = document.createElement("label");
    label.textContent = field.label;
    var box = document.createElement("div");
    box.appendChild(structuredControl(schema, group, field, row));
    if (field.hint) {
      var hint = document.createElement("div");
      hint.className = "st-hint";
      hint.textContent = field.hint;
      box.appendChild(hint);
    }
    row.appendChild(label);
    row.appendChild(box);
    return row;
  }

  function structuredControl(schema, group, field, row) {
    var key = field.key;
    var value = groupValue(schema, group, field);
    if (field.kind === "bool") {
      return boolControl(value, function (next) {
        group.values[key] = next;
      });
    }
    if (field.kind === "enum") {
      return enumControl(field, value, function (next) {
        group.values[key] = next;
        // 首次回调发生在 row 挂进 DOM 之前，parentNode 还是空的。
        // 初值可见性由 modelCard 逐行判定，这里只处理用户改选后的联动。
        var card = row.parentNode && row.parentNode.parentNode;
        syncCardVisibility(schema, group, card);
      });
    }
    var input = document.createElement("input");
    input.type = field.kind === "secret" ? "password" : (field.kind === "number" ? "number" : "text");
    if (field.kind === "number") {
      input.step = "1";
      if (field.min != null) input.min = String(field.min);
      if (field.max != null) input.max = String(field.max);
    }
    if (field.required) input.required = true;
    if (field.kind === "secret") {
      input.value = "";
      input.autocomplete = "off";
      var configured = !!(group.configured && group.configured[key]);
      input.placeholder = configured
        ? secretPlaceholder(true)
        : (field.placeholder || secretPlaceholder(false));
      group.values[key] = "";
    } else {
      input.value = value == null ? "" : String(value);
      if (field.placeholder) input.placeholder = field.placeholder;
    }
    input.addEventListener("input", function () {
      group.values[key] = input.value;
      setStatus("");
    });
    return input;
  }

  function groupValue(schema, group, field) {
    var key = field.key;
    var values = group.values || {};
    if (Object.prototype.hasOwnProperty.call(values, key)) return values[key];
    return field.default == null ? "" : String(field.default);
  }

  function fieldVisible(schema, group, field) {
    var cond = field.show_if;
    if (!cond) return true;
    var got = group.values ? group.values[cond.key] : "";
    if (got == null || got === "") got = schemaDefault(schema, cond.key);
    return String(got) === String(cond.equals);
  }

  function schemaDefault(schema, key) {
    var fields = schema.fields || [];
    for (var i = 0; i < fields.length; i++) {
      if (fields[i].key === key) return fields[i].default == null ? "" : String(fields[i].default);
    }
    return "";
  }

  /* 协议切换只影响"哪些字段适用"：就地显隐，不重建 DOM，
     否则用户刚输入的内容会随着一次下拉选择丢焦点。 */
  function syncCardVisibility(schema, group, card) {
    if (!card || !card.querySelectorAll) return;
    var rows = card.querySelectorAll(".st-row[data-field]");
    Array.prototype.forEach.call(rows, function (row) {
      var field = findField(schema, row.dataset.field);
      if (field) row.hidden = !fieldVisible(schema, group, field);
    });
  }

  function findField(schema, key) {
    var fields = schema.fields || [];
    for (var i = 0; i < fields.length; i++) {
      if (fields[i].key === key) return fields[i];
    }
    return null;
  }

  function validateStructuredEditor() {
    var editor = state.editor;
    if (!editor || editor.kind !== "sections") return "";
    var schema = editor.schema || {};
    var groups = editor.groups || [];
    for (var g = 0; g < groups.length; g++) {
      var group = groups[g] || {};
      for (var i = 0; i < (schema.fields || []).length; i++) {
        var field = schema.fields[i];
        if (!fieldVisible(schema, group, field)) continue;
        var value = String(groupValue(schema, group, field) == null
          ? "" : groupValue(schema, group, field)).trim();
        if (field.required && !value) {
          return (field.label || field.key) + "不能为空";
        }
        if (field.kind === "number" && value) {
          var n = Number(value);
          if (!isFinite(n) || Math.floor(n) !== n) {
            return (field.label || field.key) + "要填整数";
          }
          if (field.min != null && n < field.min) {
            return (field.label || field.key) + "不能小于 " + field.min;
          }
          if (field.max != null && n > field.max) {
            return (field.label || field.key) + "不能大于 " + field.max;
          }
        }
      }
    }
    return "";
  }

  function savePluginFile(closeAfter) {
    if (!state.plugin || !state.editor) return;
    var invalid = validateStructuredEditor();
    if (invalid) {
      setStatus(invalid, true);
      return;
    }
    setBusy(true);
    setStatus("保存中…");
    var body = {name: state.plugin.name};
    if (state.editor.kind === "sections") {
      body.groups = state.editor.groups || [];
    } else if (state.editor.kind === "fields") {
      body.fields = state.editor.values || {};
    } else {
      body.text = state.editor.text || "";
    }
    request("POST", "/api/settings/plugin-file", body).then(function (data) {
      setBusy(false);
      if (!data.ok) {
        setStatus(data.error || "保存失败", true);
        return;
      }
      var bad = (data.reports || []).filter(function (item) { return item.status === "error"; });
      if (bad.length) {
        setStatus(bad[0].message, true);
        return;
      }
      try {
        document.dispatchEvent(new CustomEvent("ai-agent:plugin-config-saved", {
          detail: { plugin: state.plugin.name }
        }));
      } catch (e) {}
      if (closeAfter) {
        closeSettings();
        return;
      }
      setStatus("已应用");
    }).catch(function () {
      setBusy(false);
      setStatus("保存失败", true);
    });
  }

  bootSettingsPanel();
})();
