var turnProcessPath = "app/shell/web-ui/chat/messages/process";
classicComponents.define(turnProcessPath, ["mount", "finish"]);
var turnProcessDefaults = {
  mount: function (host) {
    var node = document.createElement("details");
    var title = document.createElement("summary");
    var body = document.createElement("div");
    node.className = "chat-turn-process";
    node.open = true;
    title.textContent = "执行过程";
    body.className = "chat-turn-process-body";
    node.append(title, body);
    host.appendChild(node);
    return {node: node, body: body, title: title};
  },
  finish: function (view, status, count, elapsedMs) {
    var labels = {paused: "待确认", stopped: "已停止", interrupted: "已打断",
      abandoned: "已中止", halted: "未完成"};
    view.title.textContent = "执行过程" + (count ? " · " + count + " 次工具调用" : "") +
      (labels[status] ? " · " + labels[status] : "") +
      (Number.isFinite(elapsedMs) ? " · 总" + chatThinkElapsedLabel(elapsedMs) : "");
    if (status !== "running" && !view.body.contains(document.activeElement)) view.node.open = false;
  }
};

function chatProcessState(key) {
  if (!msgs || key == null || key === "") return null;
  var existing = msgs._chatProcess;
  if (existing && existing.key === key) return existing;
  if (existing) chatProcessFinish(existing.key, "abandoned");
  var renderer = classicComponents.select(turnProcessPath, turnProcessDefaults);
  if (typeof key === "number") msgs._latestTurnKey = key;
  msgs._chatProcess = {key: key, renderer: renderer, view: null, candidate: null, count: 0};
  return msgs._chatProcess;
}

function chatProcessBody() {
  var state = msgs && msgs._chatProcess;
  if (!state || !state.renderer) return msgs;
  if (!state.view) {
    var next = streamAssistantEl || (state.candidate && state.candidate.nextSibling);
    state.view = state.renderer.mount(msgs);
    state.view.node.dataset.turnProcess = String(state.key);
    state.view.node._turnProcessRecord = state;
    if (next && next.parentNode === msgs) msgs.insertBefore(state.view.node, next);
  }
  return state.view.body;
}

function chatProcessCommitText() {
  var state = msgs && msgs._chatProcess;
  if (!state || !state.candidate) return;
  var node = state.candidate;
  chatProcessBody().appendChild(node);
  state.candidate = null;
}

function chatProcessToolStarted() {
  var state = msgs && msgs._chatProcess;
  if (!state) return;
  if (streamAssistantEl) chatProcessAssistant("", true);
  chatProcessCommitText();
  state.count += 1;
}

function chatProcessAssistant(text, toolPhase) {
  var node = streamAssistantEl;
  if (!finalizeAssistantStream(text) && text) node = add("a", text);
  var state = msgs && msgs._chatProcess;
  if (!state || !node) return;
  state.candidate = node;
  if (toolPhase) chatProcessCommitText();
}

function chatProcessRestore(key, status, elapsedMs) {
  if (key == null) return;
  if (status !== "running") msgs._lastFinishedTurnKey = key;
  chatProcessFinish(key, status, elapsedMs);
}

function chatProcessFinish(key, status, elapsedMs) {
  var state = msgs && msgs._chatProcess;
  if (!state || (key != null && state.key !== key)) return;
  var anchor = msgs._ascrollStop && Array.from(msgs.children).find(function (node) {
    return node.getBoundingClientRect().bottom >= msgs.getBoundingClientRect().top;
  });
  var top = anchor && anchor.getBoundingClientRect().top;
  state.status = status;
  state.elapsedMs = elapsedMs;
  if (state.view) state.renderer.finish(state.view, status, state.count, state.elapsedMs);
  if (anchor) msgs.scrollTop += anchor.getBoundingClientRect().top - top;
  if (status !== "running") msgs._chatProcess = null;
  scrollMsgsToBottom();
}

document.addEventListener("ai-agent:components-changed", function () {
  var renderer = classicComponents.select(turnProcessPath, turnProcessDefaults);
  conversationTabs.forEach(function (tab) {
    var host = tab.msgsHost;
    Array.from(host.querySelectorAll("[data-turn-process]")).forEach(function (node) {
      var record = node._turnProcessRecord;
      if (!record || record.renderer === renderer) return;
      var old = record.view;
      var children = Array.from(old.body.childNodes);
      if (record.renderer.dispose) record.renderer.dispose(old);
      if (!renderer) {
        node.replaceWith.apply(node, children);
        record.view = null;
      } else {
        var view = renderer.mount(host);
        view.node.dataset.turnProcess = node.dataset.turnProcess;
        view.node._turnProcessRecord = record;
        view.body.append.apply(view.body, children);
        node.replaceWith(view.node);
        record.view = view;
        renderer.finish(view, record.status || "running", record.count, record.elapsedMs);
      }
      record.renderer = renderer;
    });
    if (host._chatProcess && !host._chatProcess.view) host._chatProcess.renderer = renderer;
  });
});
