/* 音色工作台：维度拼装 → 试听 → 满意后存成音色 id。
   事件统一委托到面板根节点，动态生成的按钮不逐个绑定。 */
(function () {
  "use strict";

  var API = "/api/plugin/tts";
  var state = {
    options: null,
    dims: {},
    current: "",
    voices: [],
    lastUrl: "",
    busy: false
  };

  function text(value) {
    return value == null ? "" : String(value);
  }

  function node(tag, className, content) {
    var item = document.createElement(tag);
    if (className) item.className = className;
    if (content != null) item.textContent = text(content);
    return item;
  }

  function request(path, options) {
    var opts = options || {};
    var init = { method: opts.method || "GET", headers: {} };
    if (opts.body) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }
    return fetch(API + path, init).then(function (resp) {
      return resp.json().catch(function () { return {}; }).then(function (data) {
        if (!resp.ok || data.ok === false) {
          throw new Error(text(data.error) || ("HTTP " + resp.status));
        }
        return data;
      });
    });
  }

  function setStatus(root, message, isError) {
    var box = root.querySelector(".tts-lab-status");
    if (!box) return;
    box.textContent = text(message);
    box.className = "tts-lab-status" + (isError ? " is-error" : "");
  }

  function instructionText() {
    if (!state.options) return "";
    var parts = [];
    state.options.order.forEach(function (key) {
      var picked = state.dims[key];
      if (picked) parts.push(picked);
    });
    return parts.join("，");
  }

  function pickPreset(root, id) {
    var preset = (state.options.presets || []).filter(function (p) { return p.id === id; })[0];
    if (!preset) return;
    state.dims = Object.assign({}, preset.dims);
    render(root);
  }

  function pickDim(root, key, value) {
    state.dims[key] = value;
    render(root);
  }

  function playBase64(mime, base64) {
    try {
      var raw = atob(base64);
      var bytes = new Uint8Array(raw.length);
      for (var i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
      if (state.lastUrl) URL.revokeObjectURL(state.lastUrl);
      state.lastUrl = URL.createObjectURL(new Blob([bytes], { type: mime || "audio/wav" }));
      var audio = new Audio(state.lastUrl);
      audio.play().catch(function () {});
      return audio;
    } catch (err) {
      return null;
    }
  }

  function render(root) {
    if (!state.options) return;
    root.textContent = "";

    var head = node("div", "tts-lab-head");
    head.appendChild(node("h4", null, "音色工作台"));
    head.appendChild(node("p", "tts-lab-hint",
      "选好五个维度后试听，满意再存成 id；上游插件只认 id。"));
    root.appendChild(head);

    var presets = node("div", "tts-lab-group");
    presets.appendChild(node("div", "tts-lab-label", "预设"));
    var chips = node("div", "tts-lab-chips");
    (state.options.presets || []).forEach(function (preset) {
      var chip = node("button", "tts-lab-chip", preset.label);
      chip.type = "button";
      chip.dataset.preset = preset.id;
      chips.appendChild(chip);
    });
    presets.appendChild(chips);
    root.appendChild(presets);

    (state.options.dimensions || []).forEach(function (dim) {
      var group = node("div", "tts-lab-group");
      group.appendChild(node("div", "tts-lab-label", dim.label));
      var options = node("div", "tts-lab-chips");
      dim.options.forEach(function (opt) {
        var chip = node("button", "tts-lab-chip", opt.value);
        chip.type = "button";
        chip.dataset.dim = dim.key;
        chip.dataset.value = opt.value;
        if (state.dims[dim.key] === opt.value) chip.classList.add("is-active");
        options.appendChild(chip);
      });
      group.appendChild(options);
      root.appendChild(group);
    });

    var preview = node("div", "tts-lab-group");
    preview.appendChild(node("div", "tts-lab-label", "生成结果"));
    preview.appendChild(node("div", "tts-lab-sentence", instructionText() || "（尚未选全）"));
    root.appendChild(preview);

    var actions = node("div", "tts-lab-actions");
    var listen = node("button", "tts-lab-btn", "试听");
    listen.type = "button";
    listen.dataset.act = "preview";
    listen.disabled = state.busy;
    actions.appendChild(listen);

    var idInput = document.createElement("input");
    idInput.type = "text";
    idInput.className = "tts-lab-id";
    idInput.placeholder = "音色 id（小写英文）";
    idInput.dataset.role = "voice-id";
    actions.appendChild(idInput);

    var save = node("button", "tts-lab-btn", "保存音色");
    save.type = "button";
    save.dataset.act = "save";
    save.disabled = state.busy;
    actions.appendChild(save);
    root.appendChild(actions);

    root.appendChild(node("div", "tts-lab-status", state.busy ? "处理中…" : ""));

    var listBox = node("div", "tts-lab-group");
    listBox.appendChild(node("div", "tts-lab-label", "已有音色"));
    var rows = node("div", "tts-lab-voices");
    if (!state.voices.length) {
      rows.appendChild(node("div", "tts-lab-empty", "还没有音色"));
    }
    state.voices.forEach(function (voice) {
      var row = node("div", "tts-lab-voice");
      row.appendChild(node("span", "tts-lab-voice-id", voice.id));
      row.appendChild(node("span", "tts-lab-voice-desc", voice.description || "（无描述）"));
      if (voice.id === state.current) {
        row.appendChild(node("span", "tts-lab-tag", "当前"));
      }
      var use = node("button", "tts-lab-mini", "启用");
      use.type = "button";
      use.dataset.act = "current";
      use.dataset.id = voice.id;
      row.appendChild(use);
      var del = node("button", "tts-lab-mini is-danger", "删除");
      del.type = "button";
      del.dataset.act = "delete";
      del.dataset.id = voice.id;
      row.appendChild(del);
      rows.appendChild(row);
    });
    listBox.appendChild(rows);
    root.appendChild(listBox);
  }

  function loadVoices(root) {
    return request("/voice-list").then(function (data) {
      state.voices = data.voices || [];
      state.current = text(data.current);
      render(root);
    }).catch(function (err) {
      setStatus(root, err.message, true);
    });
  }

  function onPreview(root) {
    state.busy = true;
    render(root);
    setStatus(root, "合成中…");
    request("/voice-preview", { method: "POST", body: state.dims })
      .then(function (data) {
        state.busy = false;
        render(root);
        playBase64(data.mime, data.audio);
        setStatus(root, "已生成，听一听再决定");
      })
      .catch(function (err) {
        state.busy = false;
        render(root);
        setStatus(root, text(err && err.message) || "合成失败", true);
      });
  }

  function onSave(root) {
    var input = root.querySelector("[data-role='voice-id']");
    var id = text(input && input.value).trim();
    if (!id) {
      setStatus(root, "先填一个音色 id", true);
      return;
    }
    // 同名会覆盖已有音色（后端就是覆盖语义），不能默默换掉
    var exists = state.voices.some(function (v) { return v.id === id; });
    if (exists && !window.confirm("音色 " + id + " 已存在，覆盖它吗？")) {
      setStatus(root, "已取消，未保存");
      return;
    }
    state.busy = true;
    render(root);
    var again = root.querySelector("[data-role='voice-id']");
    if (again) again.value = id;
    setStatus(root, "保存中…");
    request("/voice-save", { method: "POST", body: Object.assign({ id: id }, state.dims) })
      .then(function () {
        state.busy = false;
        return loadVoices(root);
      })
      .then(function () {
        setStatus(root, "已保存：" + id);
      })
      .catch(function (err) {
        state.busy = false;
        render(root);
        setStatus(root, err.message, true);
      });
  }

  function onCurrent(root, id) {
    request("/voice-current", { method: "POST", body: { id: id } })
      .then(function (data) {
        state.current = text(data.voice_id);
        render(root);
        setStatus(root, "已设为当前，重载插件后生效");
      })
      .catch(function (err) { setStatus(root, text(err && err.message) || "切换失败", true); });
  }

  function onDelete(root, id) {
    // 删掉当前使用的音色会让合成直接失声（配置里还指着它），先拦住
    if (id === state.current) {
      setStatus(root, id + " 是当前使用的音色，先启用别的再删", true);
      return;
    }
    if (!window.confirm("删除音色 " + id + "？文件和内存都会清掉")) return;
    request("/voice-delete", { method: "POST", body: { id: id } })
      .then(function () { return loadVoices(root); })
      .then(function () { setStatus(root, "已删除：" + id); })
      .catch(function (err) { setStatus(root, text(err && err.message) || "删除失败", true); });
  }

  function bind(root) {
    root.addEventListener("click", function (event) {
      var target = event.target;
      if (!target || !target.dataset) return;
      var dataset = target.dataset;
      if (dataset.preset) { pickPreset(root, dataset.preset); return; }
      if (dataset.dim) { pickDim(root, dataset.dim, dataset.value); return; }
      if (dataset.act === "preview") { onPreview(root); return; }
      if (dataset.act === "save") { onSave(root); return; }
      if (dataset.act === "current" && dataset.id) { onCurrent(root, dataset.id); return; }
      if (dataset.act === "delete" && dataset.id) { onDelete(root, dataset.id); }
    });
  }

  function mount(container) {
    if (!container || container.dataset.mounted === "1") return;
    container.dataset.mounted = "1";
    var root = container;
    // 先佔位：能看到这行字就说明脚本已经跑起来了，否则是脚本没加载。
    root.textContent = "脚本已载入，正在读取选项…";
    bind(root);
    request("/voice-options")
      .then(function (data) {
        state.options = data;
        var first = (data.presets || [])[0];
        state.dims = first ? Object.assign({}, first.dims) : {};
        root.dataset.sample = text(data.sample_text);
        render(root);
        return loadVoices(root);
      })
      .catch(function (err) {
        root.textContent = "";
        root.appendChild(node("div", "tts-lab-status is-error",
          "工作台启动失败：" + (err && err.message ? err.message : "未知错误")));
      });
  }

  function watch() {
    window.__ttsLabBooted = true;
    var existing = document.getElementById("ttsLab");
    if (existing) { mount(existing); return; }
    var observer = new MutationObserver(function () {
      var found = document.getElementById("ttsLab");
      if (found) {
        observer.disconnect();
        mount(found);
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", watch);
  } else {
    watch();
  }
})();
