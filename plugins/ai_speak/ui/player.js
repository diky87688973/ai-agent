/* AI说话播放器：按会话维护独立播放状态，同一会话只有一个实例。 */
(function () {
  "use strict";

  if (window.__aiSpeakPlayerMounted) {
    return;
  }
  var previousPlayer = window.aiAgentAISpeak;
  if (previousPlayer && typeof previousPlayer.destroy === "function") {
    try { previousPlayer.destroy(); } catch (e) {}
  }
  window.__aiSpeakPlayerMounted = true;

  var PLUGIN = "ai_speak";
  var MAX_QUEUE = 512;
  var states = Object.create(null);
  var destroyed = false;
  var defaultGapMs = 0;
  var defaultSyncPlayback = false;
  var textScrollAnim = null;
  var textScrollKey = "";
  var textScrollFrame = 0;
  var tabId = "p" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  var PLAYER_ICONS = {
    pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5v14M15 5v14"/></svg>',
    play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5l11 7-11 7Z"/></svg>',
    stop: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>'
  };
  var api = window.aiAgentPlugins && window.aiAgentPlugins.for
    ? window.aiAgentPlugins.for(window.aiAgentPluginCurrent || PLUGIN)
    : null;

  function setPlayerIcon(button, name) {
    if (button) button.innerHTML = PLAYER_ICONS[name] || "";
  }

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

  function activeCid() {
    if (typeof getActiveConversationId === "function") {
      return text(getActiveConversationId());
    }
    return "";
  }

  function stateFor(cid) {
    return states[text(cid)] || null;
  }

  function currentState() {
    return stateFor(activeCid());
  }

  var staleAudios = document.querySelectorAll("audio.ai-speak-audio");
  for (var staleIndex = 0; staleIndex < staleAudios.length; staleIndex++) {
    try { staleAudios[staleIndex].pause(); } catch (e) {}
    if (staleAudios[staleIndex].parentNode) {
      staleAudios[staleIndex].parentNode.removeChild(staleAudios[staleIndex]);
    }
  }

  var bar = element("div", "ai-speak-player");
  bar.id = "aiSpeakPlayer";
  bar.hidden = true;
  var icon = element("span", "ai-speak-icon", "🔊");
  var main = element("div", "ai-speak-main");
  var textEl = element("div", "ai-speak-text", "");
  var textInner = element("span", "ai-speak-text-inner", "");
  textEl.appendChild(textInner);
  main.appendChild(textEl);
  var countEl = element("span", "ai-speak-count", "");
  var toggleBtn = element("button", "ai-speak-btn", "");
  toggleBtn.type = "button";
  toggleBtn.title = "暂停";
  toggleBtn.setAttribute("aria-label", "暂停");
  var stopBtn = element("button", "ai-speak-btn", "");
  stopBtn.type = "button";
  stopBtn.title = "停止并清空语音";
  stopBtn.setAttribute("aria-label", "停止并清空语音");
  setPlayerIcon(stopBtn, "stop");
  bar.appendChild(icon);
  bar.appendChild(main);
  bar.appendChild(countEl);
  bar.appendChild(toggleBtn);
  bar.appendChild(stopBtn);

  function stopTextScroll() {
    if (textScrollFrame) {
      cancelAnimationFrame(textScrollFrame);
      textScrollFrame = 0;
    }
    if (textScrollAnim) {
      try { textScrollAnim.cancel(); } catch (e) {}
      textScrollAnim = null;
    }
    textScrollKey = "";
    textInner.style.transform = "";
  }

  function updateTextScroll() {
    var st = currentState();
    if (!st || st.blocked || destroyed) {
      stopTextScroll();
      return;
    }
    if (st.paused) {
      if (textScrollAnim && textScrollAnim.playState === "running") {
        textScrollAnim.pause();
      }
      return;
    }
    var duration = Number(st.audio.duration);
    if (!isFinite(duration) || duration <= 0) {
      stopTextScroll();
      return;
    }
    var viewport = textEl.clientWidth;
    var content = textInner.scrollWidth;
    if (!viewport || content <= viewport) {
      stopTextScroll();
      return;
    }
    var key = st.cid + "|" + (st.current ? st.current.callId : "") + "|" +
      (st.current ? st.current.index : "") + "|" + textInner.textContent;
    if (textScrollKey === key && textScrollAnim) return;
    stopTextScroll();
    textScrollKey = key;
    if (typeof textInner.animate !== "function") return;
    var distance = content - viewport;
    var scrollDuration = Math.max(500, Math.round(duration * 1000));
    textScrollAnim = textInner.animate([
      { transform: "translateX(0)" },
      { transform: "translateX(-" + distance + "px)" }
    ], {
      duration: scrollDuration,
      iterations: 1,
      fill: "forwards",
      easing: "linear"
    });
    var elapsed = Math.max(0, Number(st.audio.currentTime) * 1000);
    if (elapsed > 0) {
      textScrollAnim.currentTime = Math.min(elapsed, scrollDuration);
    }
  }

  function scheduleTextScroll() {
    if (textScrollFrame) return;
    textScrollFrame = requestAnimationFrame(function () {
      textScrollFrame = 0;
      updateTextScroll();
    });
  }

  function render() {
    if (destroyed) return;
    var st = currentState();
    var active = !!(st && (st.current || st.items.length || st.blocked || st.errorText));
    bar.hidden = !active;
    if (!st) {
      textInner.textContent = "";
      textEl.title = "";
      countEl.textContent = "";
      countEl.title = "";
      setPlayerIcon(toggleBtn, "pause");
      toggleBtn.title = "暂停";
      toggleBtn.setAttribute("aria-label", "暂停");
      stopTextScroll();
      return;
    }
    var label = st.current ? String(st.current.text || "") : (st.blocked ? "点击播放" : st.errorText);
    textInner.textContent = label;
    textEl.title = label;
    countEl.textContent = st.items.length ? ("队列 " + st.items.length) : "";
    countEl.title = st.dropped ? ("已丢弃 " + st.dropped + " 条待播") : "";
    var toggleName = st.blocked || st.paused ? "play" : "pause";
    setPlayerIcon(toggleBtn, toggleName);
    var toggleLabel = st.blocked ? "点击播放" : (st.paused ? "继续" : "暂停");
    toggleBtn.title = toggleLabel;
    toggleBtn.setAttribute("aria-label", toggleLabel);
    scheduleTextScroll();
  }

  function revoke(item) {
    if (item && item.url) {
      try { URL.revokeObjectURL(item.url); } catch (e) {}
      item.url = "";
    }
  }

  function clearTimer(st) {
    if (st.timer) {
      clearTimeout(st.timer);
      st.timer = null;
    }
  }

  function releasePlaybackLock(st) {
    if (!st.lockRelease) return;
    var release = st.lockRelease;
    st.lockRelease = null;
    try { release(); } catch (e) {}
  }

  function finishCurrent(st) {
    if (!st.current) return;
    st.ignorePauseUntil = Date.now() + 150;
    try { st.audio.pause(); } catch (e) {}
    revoke(st.current);
    st.current = null;
  }

  function startCurrentAudio(st) {
    if (destroyed || st.paused || st.blocked || !st.current || !st.current.url) return;
    if (st.audio.src !== st.current.url) {
      st.ignorePauseUntil = Date.now() + 150;
      st.audio.src = st.current.url;
    }
    var result = st.audio.play();
    if (result && typeof result.catch === "function") {
      result.catch(function (err) {
        if (err && err.name === "NotAllowedError") {
          releasePlaybackLock(st);
          st.blocked = true;
          st.paused = false;
          if (st === currentState()) render();
          return;
        }
        releasePlaybackLock(st);
        st.errorText = short(err && err.message ? err.message : "播放失败", 80);
        var failed = st.current;
        finishCurrent(st);
        if (failed) ackPlayback(st, failed, "error",
          err && err.message ? err.message : "播放失败");
        if (st === currentState()) render();
        playNext(st);
      });
    }
  }

  function playCurrent(st) {
    if (destroyed || st.paused || st.blocked || !st.current || !st.current.url) return;
    if (st.lockRelease) {
      startCurrentAudio(st);
      return;
    }
    if (!navigator.locks || typeof navigator.locks.request !== "function") {
      startCurrentAudio(st);
      return;
    }
    navigator.locks.request("ai-speak-playback:" + st.cid, { ifAvailable: true }, function (lock) {
      if (!lock) {
        st.paused = true;
        if (st === currentState()) render();
        return;
      }
      return new Promise(function (resolve) {
        st.lockRelease = function () {
          st.lockRelease = null;
          resolve();
        };
        if (destroyed || st.paused || !st.current) {
          releasePlaybackLock(st);
          return;
        }
        startCurrentAudio(st);
      });
    }).catch(function () {
      startCurrentAudio(st);
    });
  }

  function playNext(st) {
    if (destroyed || st.paused || st.blocked || st.current || !st.items.length) {
      if (st === currentState()) render();
      return;
    }
    st.current = st.items.shift();
    if (st === currentState()) render();
    playCurrent(st);
  }

  function afterItem(st) {
    if (destroyed) return;
    var item = st.current;
    finishCurrent(st);
    if (item) markPlayed(st, item);
    if (!st.items.length) releasePlaybackLock(st);
    if (st === currentState()) render();
    var wait = Math.max(0, Number(st.gapMs) || 0);
    clearTimer(st);
    st.timer = setTimeout(function () {
      st.timer = null;
      playNext(st);
    }, wait);
  }

  function callState(st, item) {
    if (!item || !item.callId) return null;
    var state = st.callProgress[item.callId];
    if (!state) {
      state = {
        cid: text(st.cid),
        total: Math.max(1, Number(item.total) || 1),
        done: Object.create(null),
        acked: false
      };
      st.callProgress[item.callId] = state;
    } else {
      if (!state.cid && st.cid) state.cid = text(st.cid);
      state.total = Math.max(state.total, Number(item.total) || 1);
    }
    return state;
  }

  function ackPlayback(st, item, status, detail) {
    var state = callState(st, item);
    if (!state || state.acked) return;
    if (!api || typeof api.post !== "function") return;
    state.acked = true;
    var cid = state.cid || text(st.cid);
    if (!cid && typeof getActiveConversationId === "function") {
      cid = text(getActiveConversationId());
    }
    api.post("played", {
      conversation_id: cid,
      call_id: item.callId,
      status: status,
      detail: detail || ""
    }).catch(function () {
      state.acked = false;
    });
  }

  function markPlayed(st, item) {
    var state = callState(st, item);
    if (!state || state.acked) return;
    state.done[String(item.index)] = true;
    var done = 0;
    for (var key in state.done) {
      if (Object.prototype.hasOwnProperty.call(state.done, key)) done += 1;
    }
    if (done >= state.total) ackPlayback(st, item, "played");
  }

  function requestChatStop(st) {
    try {
      var cid = text(st.cid);
      if (!cid && typeof getActiveConversationId === "function") {
        cid = text(getActiveConversationId());
      }
      if (!cid) return;
      var runId = "";
      var tab = typeof findConversationTab === "function" ? findConversationTab(cid) : null;
      if (!tab && typeof getActiveTab === "function") tab = getActiveTab();
      if (tab) runId = String(tab.activeRunId || "");
      fetch("/api/chat/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conversation_id: cid, run_id: runId })
      }).catch(function () {});
    } catch (e) {}
  }

  function broadcast(st, message) {
    if (!st.channel) return;
    try { st.channel.postMessage(Object.assign({ id: tabId }, message)); } catch (e) {}
  }

  function enqueueInto(st, frame) {
    if (destroyed || !frame || !frame.audio) return;
    var mime = text(frame.mime) || "audio/mpeg";
    var item;
    try {
      var raw = atob(text(frame.audio));
      var bytes = new Uint8Array(raw.length);
      for (var i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
      item = {
        cid: st.cid,
        callId: text(frame.call_id),
        index: Number(frame.index) || 0,
        total: Number(frame.total) || 0,
        text: text(frame.text),
        mime: mime,
        url: URL.createObjectURL(new Blob([bytes], { type: mime }))
      };
    } catch (err) {
      st.errorText = "音频解码失败";
      if (st === currentState()) render();
      return;
    }
    if (Number(frame.gap_ms) >= 0) st.gapMs = Number(frame.gap_ms) || 0;
    var duplicate = !!(st.current && item.callId &&
      st.current.callId === item.callId && st.current.index === item.index);
    if (!duplicate && item.callId) {
      for (var j = 0; j < st.items.length; j++) {
        if (st.items[j].callId === item.callId && st.items[j].index === item.index) {
          duplicate = true;
          break;
        }
      }
    }
    if (duplicate) {
      revoke(item);
      return;
    }
    st.items.push(item);
    if (st.items.length > MAX_QUEUE) {
      var droppedItem = st.items.shift();
      revoke(droppedItem);
      st.dropped += 1;
      if (droppedItem) {
        ackPlayback(st, droppedItem, "incomplete");
        if (droppedItem.callId) stopState(st, { call_id: droppedItem.callId });
      }
    }
    st.errorText = "";
    st.blocked = false;
    if (st === currentState()) render();
    if (!st.current && !st.paused) playNext(st);
  }

  function matches(st, frame) {
    if (!frame) return true;
    var cid = text(frame.conversation_id);
    var callId = text(frame.call_id);
    if (cid && st.cid !== cid) return false;
    if (callId && st.current && st.current.callId !== callId && !st.items.length) return false;
    return true;
  }

  function stopState(st, frame) {
    clearTimer(st);
    releasePlaybackLock(st);
    st.ignorePauseUntil = Date.now() + 150;
    try { st.audio.pause(); } catch (e) {}
    st.paused = false;
    st.blocked = false;
    st.errorText = "";
    if (st.current && matches(st, frame)) {
      var stoppedCurrent = st.current;
      finishCurrent(st);
      ackPlayback(st, stoppedCurrent, "stopped");
    }
    var kept = [];
    for (var i = 0; i < st.items.length; i++) {
      if (matches(st, frame)) {
        revoke(st.items[i]);
        ackPlayback(st, st.items[i], "stopped");
      } else {
        kept.push(st.items[i]);
      }
    }
    st.items = kept;
    if (!frame || (!text(frame.conversation_id) && !text(frame.call_id))) {
      if (st.current) {
        var stoppedAll = st.current;
        finishCurrent(st);
        ackPlayback(st, stoppedAll, "stopped");
      }
      for (var j = 0; j < st.items.length; j++) {
        revoke(st.items[j]);
        ackPlayback(st, st.items[j], "stopped");
      }
      st.items = [];
    }
    if (st === currentState()) render();
    if (!st.current && st.items.length) playNext(st);
  }

  function toggleState(st) {
    if (!st) return;
    if (st.blocked) {
      st.blocked = false;
      st.paused = false;
      if (st === currentState()) render();
      playCurrent(st);
      return;
    }
    if (st.paused) {
      st.paused = false;
      if (st === currentState()) render();
      if (st.current) playCurrent(st);
      else playNext(st);
      return;
    }
    st.paused = true;
    releasePlaybackLock(st);
    try { st.audio.pause(); } catch (e) {}
    broadcast(st, { type: "pause" });
    clearTimer(st);
    if (st === currentState()) render();
  }

  function stopActive() {
    var st = currentState();
    if (!st) return;
    if (st.syncPlayback) requestChatStop(st);
    broadcast(st, { type: "stop" });
    stopState(st, {});
  }

  function onStopClick() {
    stopActive();
  }

  function onToggleClick() {
    var st = currentState();
    if (st) toggleState(st);
  }

  function onBroadcast(st, ev) {
    if (destroyed) return;
    var data = ev && ev.data ? ev.data : null;
    if (!data || data.id === tabId) return;
    if (data.type === "pause") {
      st.paused = true;
      releasePlaybackLock(st);
      try { st.audio.pause(); } catch (e) {}
      clearTimer(st);
      if (st === currentState()) render();
      return;
    }
    if (data.type === "stop") stopState(st, {});
  }

  function stateForEvent(frame) {
    var cid = text(frame && frame.conversation_id) || activeCid();
    if (!cid) cid = "__default";
    return getState(cid);
  }

  function getState(cid) {
    cid = text(cid);
    if (!cid) cid = "__default";
    var st = states[cid];
    if (st) return st;
    var audio = document.createElement("audio");
    audio.className = "ai-speak-audio";
    audio.preload = "auto";
    st = {
      cid: cid,
      audio: audio,
      items: [],
      current: null,
      paused: false,
      blocked: false,
      errorText: "",
      dropped: 0,
      gapMs: defaultGapMs,
      ignorePauseUntil: 0,
      syncPlayback: defaultSyncPlayback,
      timer: null,
      callProgress: Object.create(null),
      lockRelease: null,
      channel: null
    };
    states[cid] = st;
    audio.addEventListener("ended", function () { afterItem(st); });
    audio.addEventListener("loadedmetadata", function () {
      if (st === currentState()) scheduleTextScroll();
    });
    audio.addEventListener("durationchange", function () {
      if (st === currentState()) scheduleTextScroll();
    });
    audio.addEventListener("play", function () {
      st.paused = false;
      st.blocked = false;
      st.ignorePauseUntil = 0;
      if (st === currentState()) render();
      if (st !== currentState()) return;
      if (textScrollAnim && textScrollAnim.playState === "paused") {
        textScrollAnim.play();
        return;
      }
      scheduleTextScroll();
    });
    audio.addEventListener("pause", function () {
      if (st === currentState() && textScrollAnim && textScrollAnim.playState === "running") {
        textScrollAnim.pause();
      }
      if (st.audio.ended || !st.current) return;
      var mediaDuration = Number(st.audio.duration);
      if (isFinite(mediaDuration) && mediaDuration > 0 &&
          st.audio.currentTime >= mediaDuration - 0.05) return;
      if (Date.now() < (st.ignorePauseUntil || 0)) return;
      if (st.paused) return;
      st.paused = true;
      releasePlaybackLock(st);
      broadcast(st, { type: "pause" });
      clearTimer(st);
      if (st === currentState()) render();
    });
    audio.addEventListener("error", function () {
      st.errorText = "播放失败";
      var failed = st.current;
      var mediaError = st.audio.error;
      finishCurrent(st);
      if (failed) ackPlayback(st, failed, "error",
        mediaError && mediaError.message ? mediaError.message : "播放失败");
      if (st === currentState()) render();
      playNext(st);
    });
    try {
      st.channel = new BroadcastChannel("ai-speak-player:" + cid);
      st.channel.addEventListener("message", function (ev) { onBroadcast(st, ev); });
    } catch (e) {}
    (document.body || document.documentElement).appendChild(audio);
    console.log("[ai_speak] create player cid=" + cid);
    return st;
  }

  function onPlayerEvent(ev) {
    var data = ev && ev.detail ? ev.detail : null;
    if (!data || text(data.plugin) !== PLUGIN) return;
    var st = stateForEvent(data);
    if (data.event === "segment") enqueueInto(st, data);
    else if (data.event === "error") {
      st.errorText = short(data.message || "语音合成失败", 80);
      ackPlayback(st, {
        cid: st.cid,
        callId: text(data.call_id),
        index: Number(data.index) || 0,
        total: 1
      }, "error", data.message || "合成失败");
      if (st === currentState()) render();
    } else if (data.event === "stop") stopState(st, data);
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

  function onConversationChanged() {
    stopTextScroll();
    render();
  }

  function destroyState(st) {
    if (!st) return;
    stopState(st, {});
    clearTimer(st);
    releasePlaybackLock(st);
    if (st.channel) {
      try { st.channel.close(); } catch (e) {}
      st.channel = null;
    }
    try { st.audio.pause(); } catch (e) {}
    st.audio.removeAttribute("src");
    if (st.audio.parentNode) st.audio.parentNode.removeChild(st.audio);
  }

  function destroy() {
    if (destroyed) return;
    destroyed = true;
    for (var cid in states) {
      if (Object.prototype.hasOwnProperty.call(states, cid)) destroyState(states[cid]);
    }
    states = Object.create(null);
    stopTextScroll();
    document.removeEventListener("ai-agent:plugin-event", onPlayerEvent);
    document.removeEventListener("ai-agent:plugins-changed", onPluginsChanged);
    document.removeEventListener("ai-agent:conversation-changed", onConversationChanged);
      toggleBtn.removeEventListener("click", onToggleClick);
    stopBtn.removeEventListener("click", onStopClick);
    if (bar.parentNode) bar.parentNode.removeChild(bar);
    if (window.aiAgentAISpeak === player) window.aiAgentAISpeak = null;
    if (window.__aiSpeakPlayerMounted) window.__aiSpeakPlayerMounted = false;
  }

  var player = {
    enqueue: function (frame) { enqueueInto(stateForEvent(frame), frame); },
    stop: function () { stopActive(); },
    toggle: function () { var st = currentState(); if (st) toggleState(st); },
    destroy: destroy,
    state: function () {
      var st = currentState();
      if (!st) return { queued: 0, current: "", paused: false, blocked: false };
      return {
        queued: st.items.length,
        current: st.current ? st.current.text : "",
        paused: st.paused,
        blocked: st.blocked
      };
    },
states: function () {
      var out = {};
      for (var cid in states) {
        if (Object.prototype.hasOwnProperty.call(states, cid)) {
          out[cid] = {
            queued: states[cid].items.length,
            current: states[cid].current ? states[cid].current.text : "",
            paused: states[cid].paused,
            blocked: states[cid].blocked
          };
        }
      }
      return out;
    }
  };

  window.aiAgentAISpeak = player;
  document.addEventListener("ai-agent:plugin-event", onPlayerEvent);
  document.addEventListener("ai-agent:plugins-changed", onPluginsChanged);
  document.addEventListener("ai-agent:conversation-changed", onConversationChanged);
  toggleBtn.addEventListener("click", onToggleClick);
  stopBtn.addEventListener("click", onStopClick);
  var slot = document.getElementById("aiSpeakSlot");
  (slot || document.body || document.documentElement).appendChild(bar);
  render();

  if (api && typeof api.get === "function") {
    api.get("config").then(function (res) {
      var data = res && res.data ? res.data : {};
      if (data && data.ok) {
        if (Number(data.play_interval_ms) >= 0) {
          defaultGapMs = Number(data.play_interval_ms) || 0;
          for (var cid in states) {
            if (Object.prototype.hasOwnProperty.call(states, cid)) states[cid].gapMs = defaultGapMs;
          }
        }
        defaultSyncPlayback = !!data.sync_playback;
        for (var cid2 in states) {
          if (Object.prototype.hasOwnProperty.call(states, cid2)) {
            states[cid2].syncPlayback = defaultSyncPlayback;
          }
        }
        render();
      }
    }).catch(function () {});
  }
  if (window.aiAgentShell && window.aiAgentShell.styles && window.aiAgentShell.styles.load) {
    try { window.aiAgentShell.styles.load("ui/player.css"); } catch (e) {}
  }
})();
