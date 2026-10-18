(function () {
  var state = {
    sections: [], values: {}, tab: "", mode: "host",
    plugin: null, editor: null, seeded: false, saving: false
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
    request("GET", "/api/settings").then(function (data) {
      if (!data.ok) {
        setStatus(data.error || "读取设置失败", true);
        return;
      }
      adoptSections(data.sections, true);
      state.mode = "host";
      state.tab = state.sections.length ? state.sections[0].id : "";
      state.plugin = null;
      state.editor = null;
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

  /* 目录权威态会隐藏「模型」节。插件开关切换后立即重取，标签的出现与消失
     属于面板状态，页面刷新不是前置条件。 */
  function refreshHostSections() {
    return request("GET", "/api/settings").then(function (data) {
      if (!data.ok) return;
      adoptSections(data.sections, false);
      if (state.mode === "host" && !currentSection()) {
        state.tab = state.sections.length ? state.sections[0].id : "";
      }
      renderNav();
      if (state.mode === "host") renderHost();
    }).catch(function () {
      // 目录刷新失败不影响当前面板：开关本身已经写盘了。
      return null;
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
      state.editor = null;
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
      input.placeholder = secretPlaceholder(!!field.configured);
      state.values[sectionId][field.key] = "";
    } else {
      input.value = value;
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
    btn.addEventListener("click", function () {
      pickDir(btn, function (path) {
        input.value = path;
        onChange(path);
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
        // 开关会改变"目录是否权威"，模型标签随之出现或消失 —— 立即重算。
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

  function openPlugin(card) {
    state.mode = "plugin-file";
    state.plugin = card;
    state.editor = null;
    state.seeded = false;
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
      state.seeded = !!data.seeded;
      try {
        renderPluginEditor(card);
      } catch (err) {
        form.textContent = "";
        setStatus("配置已读取，但编辑器渲染失败：" + ((err && err.message) || "未知错误"), true);
        return;
      }
      setStatus(state.seeded
        ? "还没有配置文件，已载入示例模板：把密钥占位符换成真实密钥后保存"
        : "");
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
    form.classList.add("st-form-editor");
    form.appendChild(textEditor(card, editor));
  }

  function editorBar(card) {
    var bar = document.createElement("div");
    bar.className = "st-editor-bar";
    var back = document.createElement("button");
    back.type = "button";
    back.className = "st-back";
    back.setAttribute("aria-label", "返回");
    back.title = "返回";
    back.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M14.5 5.5L8 12l6.5 6.5"/></svg>';
    back.addEventListener("click", function () {
      state.mode = "plugins";
      state.plugin = null;
      state.editor = null;
      setStatus("");
      renderNav();
      renderPlugins();
    });
    var title = document.createElement("b");
    title.textContent = (card.title || card.name) + "配置";
    bar.appendChild(back);
    bar.appendChild(title);
    return bar;
  }

  function textEditor(card, editor) {
    var wrap = document.createElement("div");
    wrap.className = "st-editor";
    var hint = document.createElement("div");
    hint.className = "st-editor-hint";
    hint.textContent = "只编辑插件自己的配置项；节头与插件元数据由系统维护。";
    var area = document.createElement("textarea");
    area.id = "stPluginText";
    area.value = editor.text || "";
    area.spellcheck = false;
    if (!area.value) area.placeholder = "这里编辑 plugin-config.ini。还没有这个文件时，保存会创建它。";
    area.addEventListener("input", function () { editor.text = area.value; });
    wrap.appendChild(editorBar(card));
    wrap.appendChild(hint);
    wrap.appendChild(area);
    return wrap;
  }

  function structuredEditor(card, editor) {
    var schema = editor.schema || {};
    var wrap = document.createElement("div");
    wrap.className = "st-editor st-editor-form";
    var hint = document.createElement("div");
    hint.className = "st-editor-hint";
    hint.textContent = state.seeded
      ? "这是示例模板：先把每条模型的密钥占位符换成真实密钥，再保存；保存后立即生效。"
      : "每条模型一节；密钥留空表示沿用已保存的值。";
    var list = document.createElement("div");
    list.className = "st-models";
    drawModels(list, schema, editor.groups || []);
    var add = document.createElement("button");
    add.type = "button";
    add.className = "st-add";
    add.textContent = "+ " + (schema.add_label || "添加");
    add.addEventListener("click", function () {
      editor.groups = editor.groups || [];
      editor.groups.push({id: "", notes: "", values: {}, configured: {}, extras: []});
      drawModels(list, schema, editor.groups);
    });
    wrap.appendChild(editorBar(card));
    wrap.appendChild(hint);
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
    var idInput = document.createElement("input");
    idInput.type = "text";
    idInput.className = "st-model-id";
    idInput.value = group.id || "";
    idInput.placeholder = (schema.identity && schema.identity.label) || "ID";
    if (schema.identity && schema.identity.hint) idInput.title = schema.identity.hint;
    idInput.addEventListener("input", function () { group.id = idInput.value; });
    var del = document.createElement("button");
    del.type = "button";
    del.className = "st-model-del";
    del.title = "删除这条配置";
    del.setAttribute("aria-label", "删除这条配置");
    del.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
      'stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';
    del.addEventListener("click", function () {
      var groups = state.editor.groups || [];
      groups.splice(index, 1);
      drawModels(list, schema, groups);
    });
    head.appendChild(badge);
    head.appendChild(idInput);
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
    }
    if (field.kind === "secret") {
      input.value = "";
      input.autocomplete = "off";
      var configured = !!(group.configured && group.configured[key]);
      input.placeholder = secretPlaceholder(configured);
      group.values[key] = "";
    } else {
      input.value = value == null ? "" : String(value);
    }
    if (field.placeholder) input.placeholder = field.placeholder;
    input.addEventListener("input", function () {
      group.values[key] = input.value;
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

  function savePluginFile(closeAfter) {
    if (!state.plugin || !state.editor) return;
    setBusy(true);
    setStatus("保存中…");
    var body = {name: state.plugin.name};
    if (state.editor.kind === "sections") {
      body.groups = state.editor.groups || [];
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
