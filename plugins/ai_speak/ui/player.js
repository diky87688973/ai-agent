/* AI说话播放器：接住插件事件，按到达顺序串行播放。
   每个标签页独立一份；不跨页同步，也不读写 localStorage。 */
(function () {
  "use strict";

  var PLUGIN = "ai_speak";
  var MAX_QUEUE = 512;
  var current = null;
  var items = [];
  var paused = false;
  var blocked = false;
  var timer = null;
  var destroyed = false;
  var gapMs = 0;
  var dropped = 0;
  var errorText = "";
  var api = window.aiAgentPlugins && window.aiAgentPlugins.for
    ? window.aiAgentPlugins.for(window.aiAgentPluginCurrent || PLUGIN)
    : null;

  function text(value) {
    return value == null ? "" : String(value);
  }

  function short(value, limit) {
    var s = text(value);
    return s.length > limit ? s.slice(0, limit) + "…" : s;
  }

  function element(tag, className, content) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (content != null) node.textContent = content;
    return node;
  }

  var bar = element("div", "ai-speak-player");
  bar.id = "aiSpeakPlayer";
  bar.hidden = true;
  var icon = element("span", "ai-speak-icon", "🔊");
  var main = element("div", "ai-speak-main");
  var titleEl = element("div", "ai-speak-title", "AI说话");
  var textEl = element("div", "ai-speak-text", "");
  main.appendChild(titleEl);
  main.appendChild(textEl);
  var countEl = element("span", "ai-speak-count", "");
  var toggleBtn = element("button", "ai-speak-btn", "暂停");
  toggleBtn.type = "button";
  toggleBtn.setAttribute("aria-label", "暂停或继续");
  var stopBtn = element("button", "ai-speak-btn", "停止");
  stopBtn.type = "button";
  stopBtn.title = "停止并清空语音";
  stopBtn.setAttribute("aria-label", "停止并清空语音");
  toggleBtn.title = "暂停或继续";
  bar.appendChild(icon);
  bar.appendChild(main);
  bar.appendChild(countEl);
  bar.appendChild(toggleBtn);
  bar.appendChild(stopBtn);

  var audio = document.createElement("audio");
  audio.className = "ai-speak-audio";
  audio.preload = "auto";

  function render() {
    if (destroyed) return;
    var active = !!(current || items.length || blocked || errorText);
    bar.hidden = !active;
    textEl.textContent = current
      ? short(current.text, 60)
      : (blocked ? "点击播放" : errorText);
    textEl.title = current ? current.text : errorText;
    countEl.textContent = items.length ? ("队列 " + items.length) : "";
    countEl.title = dropped ? ("已丢弃 " + dropped + " 条待播") : "";
    toggleBtn.textContent = blocked ? "点击播放" : (paused ? "继续" : "暂停");
  }

  function revoke(item) {
    if (item && item.url) {
      try { URL.revokeObjectURL(item.url); } catch (e) {}
      item.url = "";
    }
  }

  function clearTimer() {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function finishCurrent() {
    if (!current) return;
    revoke(current);
    current = null;
    playing = false;
  }

  var playing = false;

  function playCurrent() {
    if (destroyed || paused || blocked || !current) return;
    if (!current.url) return;
    if (audio.src !== current.url) audio.src = current.url;
    playing = true;
    var result = audio.play();
    if (result && typeof result.catch === "function") {
      result.catch(function (err) {
        playing = false;
        if (err && err.name === "NotAllowedError") {
          blocked = true;
          paused = false;
          render();
          return;
        }
        showError(err && err.message ? err.message : "播放失败");
        finishCurrent();
        playNext();
      });
    }
  }

  function playNext() {
    if (destroyed || paused || blocked || current || !items.length) {
      render();
      return;
    }
    current = items.shift();
    render();
    playCurrent();
  }

  function afterItem() {
    if (destroyed) return;
    finishCurrent();
    render();
    var wait = Math.max(0, Number(gapMs) || 0);
    clearTimer();
    timer = setTimeout(function () {
      timer = null;
      playNext();
    }, wait);
  }

  function showError(message) {
    errorText = short(message, 80);
    render();
  }

  function enqueue(frame) {
    if (destroyed || !frame || !frame.audio) return;
    var mime = text(frame.mime) || "audio/mpeg";
    var item;
    try {
      var raw = atob(text(frame.audio));
      var bytes = new Uint8Array(raw.length);
      for (var i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
      item = {
        cid: text(frame.conversation_id),
        callId: text(frame.call_id),
        index: Number(frame.index) || 0,
        total: Number(frame.total) || 0,
        text: text(frame.text),
        mime: mime,
        url: URL.createObjectURL(new Blob([bytes], { type: mime }))
      };
    } catch (err) {
      showError("音频解码失败");
      render();
      return;
    }
    if (Number(frame.gap_ms) >= 0) gapMs = Number(frame.gap_ms) || 0;
    var duplicate = !!(current && item.callId
      && current.callId === item.callId && current.index === item.index);
    if (!duplicate && item.callId) {
      for (var j = 0; j < items.length; j++) {
        if (items[j].callId === item.callId && items[j].index === item.index) {
          duplicate = true;
          break;
        }
      }
    }
    if (duplicate) {
      revoke(item);
      return;
    }
    items.push(item);
    if (items.length > MAX_QUEUE) {
      revoke(items.shift());
      dropped += 1;
    }
    errorText = "";
    blocked = false;
    render();
    if (!current && !paused) playNext();
  }

  function matches(item, frame) {
    if (!item) return false;
    var cid = text(frame.conversation_id);
    var callId = text(frame.call_id);
    if (cid && item.cid !== cid) return false;
    if (callId && item.callId !== callId) return false;
    return true;
  }

  function stop(frame) {
    clearTimer();
    paused = false;
    blocked = false;
    errorText = "";
    if (current && matches(current, frame)) {
      audio.pause();
      finishCurrent();
    }
    var kept = [];
    for (var i = 0; i < items.length; i++) {
      if (matches(items[i], frame)) revoke(items[i]);
      else kept.push(items[i]);
    }
    items = kept;
    if (!frame || (!text(frame.conversation_id) && !text(frame.call_id))) {
      audio.pause();
      finishCurrent();
      for (var j = 0; j < items.length; j++) revoke(items[j]);
      items = [];
    }
    render();
    if (!current && items.length) playNext();
  }

  function toggle() {
    if (blocked) {
      blocked = false;
      paused = false;
      render();
      playCurrent();
      return;
    }
    if (paused) {
      paused = false;
      render();
      if (current) playCurrent();
      else playNext();
      return;
    }
    paused = true;
    if (audio && !audio.paused) audio.pause();
    clearTimer();
    render();
  }

  function onPlayerEvent(ev) {
    var data = ev && ev.detail ? ev.detail : null;
    if (!data || text(data.plugin) !== PLUGIN) return;
    if (data.event === "segment") enqueue(data);
    else if (data.event === "error") {
      showError(data.message || "语音合成失败");
      render();
    } else if (data.event === "stop") stop(data);
  }

  function onPluginsChanged(ev) {
    var data = ev && ev.detail ? ev.detail : null;
    var loaded = data && Array.isArray(data.loaded) ? data.loaded : [];
    var present = false;
    for (var i = 0; i < loaded.length; i++) {
      if (text(loaded[i]) === PLUGIN) { present = true; break; }
    }
    if (!present) destroy();
  }

  function onStopClick() {
    stop({});
  }

  function destroy() {
    if (destroyed) return;
    destroyed = true;
    clearTimer();
    try { audio.pause(); } catch (e) {}
    audio.removeAttribute("src");
    finishCurrent();
    for (var i = 0; i < items.length; i++) revoke(items[i]);
    items = [];
    document.removeEventListener("ai-agent:plugin-event", onPlayerEvent);
    document.removeEventListener("ai-agent:plugins-changed", onPluginsChanged);
    toggleBtn.removeEventListener("click", toggle);
    stopBtn.removeEventListener("click", onStopClick);
    if (bar.parentNode) bar.parentNode.removeChild(bar);
    if (audio.parentNode) audio.parentNode.removeChild(audio);
    if (window.aiAgentAISpeak === player) window.aiAgentAISpeak = null;
  }

  function stopAll() {
    stop({});
  }

  var player = {
    enqueue: enqueue,
    stop: stopAll,
    toggle: toggle,
    destroy: destroy,
    state: function () {
      return { queued: items.length, current: current ? current.text : "",
               paused: paused, blocked: blocked };
    }
  };

  if (window.aiAgentAISpeak && typeof window.aiAgentAISpeak.destroy === "function") {
    try { window.aiAgentAISpeak.destroy(); } catch (e) {}
  }
  window.aiAgentAISpeak = player;

  audio.addEventListener("ended", afterItem);
  audio.addEventListener("error", function () {
    showError("播放失败");
    afterItem();
  });
  document.addEventListener("ai-agent:plugin-event", onPlayerEvent);
  document.addEventListener("ai-agent:plugins-changed", onPluginsChanged);
  toggleBtn.addEventListener("click", toggle);
  stopBtn.addEventListener("click", onStopClick);
  (document.body || document.documentElement).appendChild(bar);
  (document.body || document.documentElement).appendChild(audio);

  if (window.aiAgentShell && window.aiAgentShell.styles && window.aiAgentShell.styles.load) {
    try { window.aiAgentShell.styles.load("ui/player.css"); } catch (e) {}
  }
  if (api && typeof api.get === "function") {
    api.get("config").then(function (res) {
      var data = res && res.data ? res.data : {};
      if (data && data.ok && Number(data.play_interval_ms) >= 0) {
        gapMs = Number(data.play_interval_ms) || 0;
      }
    }).catch(function () {});
  }
  render();
})();
