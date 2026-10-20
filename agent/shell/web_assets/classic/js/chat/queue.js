/* chat/queue.js —— 输入框上方的待发送消息队列。 */
var chatQueueItems = [];
var chatQueueRevision = -1;
var chatDraft = null;

var QUEUE_ICONS = {
  edit: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4l10-10-4-4L4 16v4Z"/><path d="m13.5 5.5 5 5"/></svg>',
  trash: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="m7 7 1 13h8l1-13"/><path d="M10 11v5M14 11v5"/></svg>',
  up: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5"/><path d="m6 11 6-6 6 6"/></svg>',
  image: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8.5" cy="10" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>'
};

function iconButton(className, label, icon, action) {
  var button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.title = label;
  button.setAttribute("aria-label", label);
  button.setAttribute("data-queue-action", action);
  button.innerHTML = QUEUE_ICONS[icon];
  return button;
}

function queueItemById(id) {
  for (var i = 0; i < chatQueueItems.length; i++) {
    if (String(chatQueueItems[i].id || "") === id) return chatQueueItems[i];
  }
  return null;
}

function bindQueueDelegation(panel) {
  if (panel._queueDelegated) return;
  panel._queueDelegated = true;
  panel.addEventListener("click", function (ev) {
    var button = ev.target && ev.target.closest
      ? ev.target.closest("[data-queue-action]") : null;
    if (!button || !panel.contains(button)) return;
    var row = button.closest(".chat-queue-row");
    var item = row ? queueItemById(String(row.getAttribute("data-queue-id") || "")) : null;
    if (!item || button.disabled) return;
    if (button.getAttribute("data-queue-action") === "insert") queueInsert(item);
    else if (button.getAttribute("data-queue-action") === "recall") queueRecall(item);
    else if (button.getAttribute("data-queue-action") === "cancel") queueCancel(item);
  });
}

function chatQueueCid() {
  return typeof getActiveConversationId === "function"
    ? String(getActiveConversationId() || "")
    : "";
}

function chatQueueApi(path, options) {
  return fetch(path, options).then(function (resp) {
    return resp.json().catch(function () { return {}; }).then(function (body) {
      if (!resp.ok || body.ok === false) {
        throw new Error(String(body.error || "队列操作失败"));
      }
      return body;
    });
  });
}

function renderChatQueue(snapshot) {
  var panel = document.getElementById("chatQueue");
  if (!panel) return;
  bindQueueDelegation(panel);
  if (!snapshot || String(snapshot.conversation_id || "") !== chatQueueCid()) {
    panel.classList.add("hidden");
    panel.innerHTML = "";
    return;
  }
  chatQueueItems = Array.isArray(snapshot.items) ? snapshot.items : [];
  chatQueueRevision = Number(snapshot.revision || 0);
  panel.innerHTML = "";
  if (!chatQueueItems.length) {
    panel.classList.add("hidden");
    return;
  }
  panel.classList.remove("hidden");
  var head = document.createElement("div");
  head.className = "chat-queue-head";
  var title = document.createElement("span");
  title.className = "chat-queue-title";
  title.textContent = "待发送";
  var count = document.createElement("span");
  count.className = "chat-queue-count";
  count.textContent = String(chatQueueItems.length);
  head.appendChild(title);
  head.appendChild(count);
  panel.appendChild(head);
  chatQueueItems.forEach(function (item) {
    panel.appendChild(chatQueueRow(item));
  });
}

function chatQueueRow(item) {
  var row = document.createElement("div");
  row.className = "chat-queue-row" + (item.state === "inserting" ? " is-inserting" : "");
  row.setAttribute("data-queue-id", String(item.id || ""));

  var index = document.createElement("span");
  index.className = "chat-queue-index";
  index.textContent = "[#" + String(item.position || "") + "]";
  row.appendChild(index);

  if (item.origin === "agent") {
    var badge = document.createElement("span");
    badge.className = "chat-queue-badge";
    var sender = item.sender || {};
    badge.textContent = "🤖 " + String(sender.name || sender.cid || "Agent");
    row.appendChild(badge);
  }

  var attachments = Array.isArray(item.attachments) ? item.attachments : [];
  if (attachments.length) {
    var attach = document.createElement("span");
    attach.className = "chat-queue-attach";
    attach.innerHTML = QUEUE_ICONS.image + "<span>图片 " + attachments.length + "</span>";
    attach.title = "包含 " + attachments.length + " 张图片";
    attach.setAttribute("aria-label", "包含 " + attachments.length + " 张图片");
    row.appendChild(attach);
  }

  var text = document.createElement("span");
  text.className = "chat-queue-text";
  text.textContent = String(item.content || "");
  text.title = text.textContent;
  row.appendChild(text);

  var inserting = item.state === "inserting";
  if (inserting) {
    var status = document.createElement("span");
    status.className = "chat-queue-status";
    status.textContent = "已插入";
    status.title = "已插入当前回合，等待发送";
    row.appendChild(status);
  }

  var actions = document.createElement("span");
  actions.className = "chat-queue-actions";
  var insert = iconButton("queue-insert", "插入发送", "up", "insert");
  var edit = iconButton("queue-edit", "修改", "edit", "recall");
  var cancel = iconButton("queue-cancel", "取消", "trash", "cancel");
  insert.disabled = inserting;
  edit.disabled = inserting;
  cancel.disabled = inserting;
  if (inserting) {
    edit.title = "已插入，不能修改";
    cancel.title = "已插入，不能删除";
    insert.title = "已插入，等待发送";
  }
  actions.appendChild(edit);
  actions.appendChild(cancel);
  actions.appendChild(insert);
  row.appendChild(actions);
  return row;
}

function loadChatQueue(cid) {
  var target = String(cid || chatQueueCid() || "");
  if (!target) return Promise.resolve();
  return chatQueueApi("/api/chat/queue?conversation_id=" + encodeURIComponent(target))
    .then(function (body) { renderChatQueue(body); })
    .catch(function () {});
}

function queueInsert(item) {
  var cid = chatQueueCid();
  if (!cid || !item || item.state === "inserting") return;
  item.state = "inserting";
  renderChatQueue({
    conversation_id: cid,
    revision: chatQueueRevision,
    items: chatQueueItems,
  });
  chatQueueApi(
    "/api/chat/queue/" + encodeURIComponent(item.id) + "/insert",
    {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({conversation_id: cid}),
    }
  ).then(function () { return loadChatQueue(cid); }).catch(function (err) {
    if (window.DEBUG) console.error("[queue] insert failed", err);
    loadChatQueue(cid);
  });
}

function queueCancel(item) {
  var cid = chatQueueCid();
  if (!cid || !item) return;
  chatQueueApi(
    "/api/chat/queue/" + encodeURIComponent(item.id)
      + "?conversation_id=" + encodeURIComponent(cid),
    {method: "DELETE"}
  ).then(function () { return loadChatQueue(cid); }).catch(function (err) {
    if (window.DEBUG) console.error("[queue] cancel failed", err);
  });
}

function queueRecall(item) {
  var cid = chatQueueCid();
  if (!cid || !item) return;
  chatQueueApi(
    "/api/chat/queue/" + encodeURIComponent(item.id) + "/recall",
    {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({conversation_id: cid}),
    }
  ).then(function (body) {
    var restored = body.item || {};
    if (typeof ta !== "undefined" && ta) {
      ta.value = String(restored.content || "");
      if (typeof autoResizeTextarea === "function") autoResizeTextarea();
      ta.focus();
    }
    if (typeof clearPendingChatImages === "function") clearPendingChatImages();
    var atts = Array.isArray(restored.attachments) ? restored.attachments : [];
    atts.forEach(function (att) {
      var raw = String(att.data_base64 || "");
      if (!raw) return;
      try {
        var bin = atob(raw);
        var bytes = new Uint8Array(bin.length);
        for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        var blob = new Blob([bytes], {type: String(att.mime || "image/png")});
        pendingChatImages.push({
          mime: String(att.mime || "image/png"),
          data_base64: raw,
          previewUrl: URL.createObjectURL(blob),
          name: "queue.png",
        });
      } catch (_e) {}
    });
    if (typeof renderAttachStrip === "function") renderAttachStrip();
    chatDraft = {
      id: String(restored.id || body.draft_queue_id || ""),
      origin: String(restored.origin || "user"),
      sender: restored.sender || null,
    };
    renderQueueDraft();
    return loadChatQueue(cid);
  }).catch(function (err) {
    if (window.DEBUG) console.error("[queue] recall failed", err);
  });
}

function renderQueueDraft() {
  var mount = document.getElementById("queueDraft");
  if (!mount) return;
  if (!chatDraft || chatDraft.origin !== "agent") {
    mount.classList.add("hidden");
    mount.textContent = "";
    return;
  }
  var sender = chatDraft.sender || {};
  mount.textContent = "来自 " + String(sender.name || sender.cid || "Agent")
    + " 的草稿";
  mount.classList.remove("hidden");
}

function clearQueueDraft() {
  chatDraft = null;
  renderQueueDraft();
}

function onQueueUpdated(event) {
  if (!event || String(event.conversation_id || "") !== chatQueueCid()) return;
  renderChatQueue({
    conversation_id: event.conversation_id,
    revision: event.revision,
    items: event.items,
  });
}

setTimeout(function () { void loadChatQueue(); }, 0);
