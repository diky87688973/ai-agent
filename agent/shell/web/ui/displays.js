/* 消息面板：事实修订投影、组件登记和资源生命周期。 */
(function () {
  "use strict";
  var renderers = new Map(), declarations = new Map(), records = new Set();
  var shell = window.aiAgentShell = window.aiAgentShell || {};
  function retained(host) {
    return host.isConnected || (typeof conversationTabs !== "undefined" && conversationTabs.some(function (tab) {
      return tab.msgsHost && tab.msgsHost.contains(host);
    }));
  }
  function release(record) {
    record.renderEpoch = (record.renderEpoch || 0) + 1;
    if (record.modeController) record.modeController.abort();
    if (record.modeListeners) record.modeListeners.clear();
    if (record.dispose) {
      try { record.dispose(); } catch (error) { console.error("display.dispose", error); }
      record.dispose = null;
    }
    record.host.replaceChildren();
  }
  function context(record) {
    var epoch = record.renderEpoch;
    return {
      conversationId: record.conversationId, panelId: record.document.id,
      mode: {
        get: function () { return record.mode; },
        set: function (value) {
          if (record.renderEpoch !== epoch || !records.has(record) || latest(record) !== record) throw new Error("此面板已失效");
          return setMode(record, value);
        },
        subscribe: function (listener) {
          if (typeof listener !== "function" || record.renderEpoch !== epoch) throw new Error("无效的模式监听器");
          record.modeListeners.add(listener);
          return function () { record.modeListeners.delete(listener); };
        }
      },
      active: function () { return records.has(record) && latest(record) === record && getActiveConversationId() === record.conversationId; },
      state: {
        load: function () { return shell.displays.state.load(record.conversationId, record.document); },
        save: function (value) { return shell.displays.state.save(record.conversationId, record.document, value); }
      },
      insert: function (text) {
        if (!records.has(record) || latest(record) !== record) return {ok: false, error: "此面板已失效"};
        var owner = typeof conversationTabs !== "undefined" && conversationTabs.find(function (tab) {
          return tab.msgsHost && tab.msgsHost.contains(record.host);
        });
        if (!owner || getActiveConversationId() !== owner.id || owner.id !== record.conversationId) return {ok: false, error: "请切换到面板所属会话"};
        var input = document.getElementById("t");
        if (!input || record.document.operation !== "upsert") return {ok: false, error: "当前面板没有可用的输入入口"};
        if (typeof text !== "string" || !text.trim() || text.length > 8000) return {ok: false, error: "选择内容必须是1–8000字的文本"};
        input.value += (input.value ? "\n" : "") + text;
        input.dispatchEvent(new Event("input", {bubbles: true})); input.focus();
        return {ok: true};
      }
    };
  }
  function setMode(record, value) {
    var declaration = declarations.get(record.document.type);
    if (["view", "edit"].indexOf(value) < 0 || (value === "edit" && (!declaration || !declaration.editable))) throw new Error("展示类型不支持此模式");
    if (record.mode === value) return {ok: true};
    record.mode = value;
    updateModeButton(record);
    try {
      record.modeListeners.forEach(function (listener) { listener(value); });
      var toggle = record.host.querySelector(".aa-display-mode");
      if (toggle && value === "view" && record.host.contains(document.activeElement)) toggle.focus({preventScroll: true});
      if (toggle && value === "edit" && toggle === document.activeElement && toggle.matches(":focus-visible")) {
        var first = record.host.querySelector('.aa-display-body input:not([disabled]),.aa-display-body select:not([disabled]),.aa-display-body button:not([disabled]),.aa-display-body [tabindex="0"]');
        if (first) first.focus({preventScroll: true});
      }
      return {ok: true};
    } catch (error) {
      release(record); record.host.setAttribute("role", "alert");
      record.host.textContent = "无法切换展示模式：" + String(error.message || error);
      console.error("display.mode", error); return {ok: false, error: String(error.message || error)};
    }
  }
  function updateModeButton(record) {
    record.host.dataset.displayMode = record.mode;
    var button = record.host.querySelector(".aa-display-mode"); if (!button) return;
    var editing = record.mode === "edit", label = editing ? "完成编辑" : "编辑视图";
    button.setAttribute("aria-label", label); button.title = label;
    button.setAttribute("aria-pressed", String(editing));
    button.querySelector("span").textContent = editing ? "完成" : "";
  }
  function mountModeButton(record, declaration) {
    if (!declaration.editable) return;
    var button = document.createElement("button");
    button.type = "button"; button.className = "aa-display-mode";
    button.innerHTML = '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="m12.5 3.5 4 4M3.5 16.5l4.2-.8L16 7.4a2.8 2.8 0 0 0-4-4l-8 8.9z"/></svg><span></span>';
    record.host.appendChild(button); record.modeController = new AbortController();
    record.host.addEventListener("click", function (event) {
      if (event.target.closest(".aa-display-mode") === button) setMode(record, record.mode === "edit" ? "view" : "edit");
    }, {signal: record.modeController.signal});
    record.host.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && record.mode === "edit") setMode(record, "view");
    }, {signal: record.modeController.signal});
    updateModeButton(record);
  }
  function latest(record) {
    var winner = null;
    records.forEach(function (other) {
      if (other.conversationId === record.conversationId && other.document.id === record.document.id &&
          (!winner || other.document.revision > winner.document.revision)) winner = other;
    });
    return winner || record;
  }
  function paint(record) {
    release(record);
    var doc = record.document, newest = latest(record), declaration = declarations.get(doc.type);
    var entry = declaration && renderers.get(doc.type);
    if (entry && entry.owner !== declaration.owner) entry = null;
    record.host.hidden = false; record.host.setAttribute("role", "status");
    if (newest !== record && newest.document.revision > doc.revision) {
      record.host.textContent = doc.title + " · 已由修订 " + newest.document.revision + " 替换"; return;
    }
    if (newest !== record) { record.host.hidden = true; return; }
    if (doc.operation === "remove") { record.host.textContent = doc.title + " · 已移除"; return; }
    if (!entry) { record.host.textContent = doc.title + " · 此组件尚未启用。" + doc.summary; return; }
    record.host.removeAttribute("role");
    try {
      if (!declaration.editable) record.mode = "view";
      record.host.dataset.displayMode = record.mode;
      var body = document.createElement("div"); body.className = "aa-display-body"; record.host.appendChild(body);
      record.dispose = entry.render(body, doc, context(record)) || null;
      if (record.dispose && typeof record.dispose !== "function") throw new Error("组件未返回销毁函数");
      mountModeButton(record, declaration);
    } catch (error) {
      release(record); record.host.textContent = "无法展示组件：" + String(error.message || error) + "。" + doc.summary;
      record.host.setAttribute("role", "alert"); console.error("display.render", error);
    }
  }
  function validate(doc) {
    if (!doc || doc.version !== 1 || !/^[a-z][a-z0-9_.-]{0,79}$/.test(doc.type || "") ||
        !/^[A-Za-z0-9_-]{1,64}$/.test(doc.id || "") || !Number.isSafeInteger(doc.revision) || doc.revision < 1 ||
        ["upsert", "remove"].indexOf(doc.operation) < 0 || typeof doc.title !== "string" ||
        typeof doc.summary !== "string" || JSON.stringify(doc).length > 98304) throw new Error("不支持的面板协议或载荷");
  }
  function mount(host, doc, conversationId) {
    validate(doc);
    if (!conversationId) throw new Error("面板缺少所属会话");
    var record = Array.from(records).find(function (item) { return item.host === host; });
    if (record && record.document.revision === doc.revision && JSON.stringify(record.document) === JSON.stringify(doc)) return;
    if (record && record.document.revision >= doc.revision) throw new Error("过期或冲突的面板修订");
    record = record || {host: host, dispose: null, mode: "view", modeListeners: new Set()};
    if (record.document && record.document.revision !== doc.revision) record.mode = "view";
    record.document = JSON.parse(JSON.stringify(doc)); record.conversationId = conversationId;
    records.add(record); host.classList.add("aa-display"); paint(record);
    records.forEach(function (other) {
      if (other !== record && other.conversationId === conversationId && other.document.id === doc.id && other.document.revision < doc.revision) paint(other);
    });
    return function () { release(record); records.delete(record); };
  }
  function consume(call, frame, messages) {
    if (!call || !frame || !frame.ok || !messages || !frame.preview) return;
    var envelope;
    try { envelope = JSON.parse(frame.preview); } catch (_error) { return; }
    var doc = envelope && envelope.ok && envelope.data && envelope.data.display;
    if (!doc) return;
    var key = String(frame.tool_call_id || call.tid || ""); if (!key) return;
    var host = Array.from(messages.querySelectorAll(".aa-display[data-display-call]")).find(function (node) { return node.dataset.displayCall === key; });
    if (!host) { host = document.createElement("section"); host.className = "aa-display"; host.dataset.displayCall = key; messages.appendChild(host); }
    try { mount(host, doc, messages.dataset.conversationId); }
    catch (error) { host.textContent = "无法展示组件：" + error.message; host.setAttribute("role", "alert"); }
  }
  shell.displays = {
    mount: mount, consume: consume,
    declared: function (type, owner) { var entry = declarations.get(type); return !!(entry && entry.owner === owner); },
    setCatalog: function (entries) {
      var next = new Map();
      entries.forEach(function (entry) {
        var type = entry.metadata && entry.metadata.props && entry.metadata.props.renderer;
        if (entry.kind !== "ui-tool-shell" || !type) return;
        if (next.has(type)) throw new Error("展示类型重复声明：" + type);
        next.set(type, {owner: entry.owner, path: entry.path, editable: entry.metadata.props.editable === true});
      });
      declarations = next;
      records.forEach(paint);
    },
    register: function (type, render, owner) {
      if (!owner || typeof render !== "function" || renderers.has(type) || !shell.displays.declared(type, owner)) throw new Error("未声明、归属不符或重复的组件实现：" + type);
      var entry = {render: render, owner: owner}; renderers.set(type, entry);
      records.forEach(function (record) { if (record.document.type === type) paint(record); });
      return function () {
        if (renderers.get(type) !== entry) return;
        renderers.delete(type);
        records.forEach(function (record) { if (record.document.type === type) paint(record); });
      };
    }
  };
  new MutationObserver(function () {
    var removed = [];
    records.forEach(function (record) {
      if (!retained(record.host)) { release(record); records.delete(record); removed.push(record); }
    });
    records.forEach(function (record) {
      if (removed.some(function (other) { return other.conversationId === record.conversationId && other.document.id === record.document.id; })) paint(record);
    });
  }).observe(document.documentElement, {childList: true, subtree: true});
  document.addEventListener("ai-agent:plugins-changed", function (event) {
    var loaded = event.detail && event.detail.loaded || [], removed = new Set();
    declarations.forEach(function (entry, type) { if (loaded.indexOf(entry.owner) < 0) declarations.delete(type); });
    renderers.forEach(function (entry, type) { if (loaded.indexOf(entry.owner) < 0) { renderers.delete(type); removed.add(type); } });
    records.forEach(function (record) { if (removed.has(record.document.type)) paint(record); });
  });
})();
