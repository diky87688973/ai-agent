var sessionRailPath = "app/shell/web-ui/left-panel/sessions/list";
classicComponents.define(sessionRailPath, ["render"]);
var sessionCatalogUrl = "/api/chat/session-catalog";
var sessionRailPages = new Map();
var sessionRailExpanded = new Set();
var sessionRailPending = false;
var sessionRailNotice = "";
var sessionRailRefresh = false;
var sessionRailMounted = null;
var sessionRailPopup = null;

function railElement(tag, className, text) {
  var node = document.createElement(tag);
  node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function railButton(text, action, key, label) {
  var button = railElement("button", "session-rail-action", text);
  button.type = "button";
  button.dataset.railAction = action;
  if (key != null) button.dataset.railKey = key;
  if (label) {
    button.title = label;
    button.setAttribute("aria-label", label);
  }
  if (action === "session-menu" || action === "project-menu") {
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-controls", "sessionRailPopup");
  }
  return button;
}

function railPage(key) {
  if (!sessionRailPages.has(key)) {
    sessionRailPages.set(key, {items: [], cursor: null, loaded: false, busy: false, error: ""});
  }
  return sessionRailPages.get(key);
}

function railRow(item) {
  var wrap = railElement("div", "session-rail-row");
  var row = railButton("", "open", item.id);
  row.className = "chat-session-row";
  row.title = item.title;
  if (getActiveConversationId() === item.id) row.setAttribute("aria-current", "true");
  row.appendChild(railElement("span", "chat-session-title", item.title));
  if (findConversationTab(item.id)) {
    row.appendChild(railElement("span", "chat-session-badge", "已打开"));
  }
  wrap.append(row, railButton("⋯", "session-menu", item.id, "整理会话"));
  return wrap;
}

function railAppendPage(host, key, empty) {
  var page = railPage(key);
  var date = null;
  page.items.forEach(function (item) {
    if (key === "recent" && date !== item.date_group) {
      date = item.date_group;
      host.appendChild(railElement("div", "chat-session-group", date));
    }
    host.appendChild(key === "projects" ? railProject(item) : railRow(item));
  });
  if (page.error) host.appendChild(railButton(page.error + " · 重试", "more", key));
  else if (page.busy) host.appendChild(railElement("div", "chat-session-empty", "加载中…"));
  else if (page.cursor) host.appendChild(railButton("加载更多", "more", key));
  else if (page.loaded && !page.items.length && empty) {
    host.appendChild(railElement("div", "chat-session-empty", empty));
  }
}

function railProject(project) {
  var section = railElement("div", "session-rail-project");
  var head = railElement("div", "session-rail-row");
  var expanded = sessionRailExpanded.has(project.id);
  var name = railButton("", "toggle", project.id);
  name.classList.add("session-rail-project-name");
  name.setAttribute("aria-expanded", String(expanded));
  name.title = project.name;
  var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("session-rail-folder");
  var shape = document.createElementNS(svg.namespaceURI, "path");
  shape.setAttribute("d", expanded
    ? "M3 19V6a2 2 0 0 1 2-2h4l2 3h7a2 2 0 0 1 2 2v2M3 19l3.5-8H22l-3.5 8Z"
    : "M3 7a2 2 0 0 1 2-2h4l2 3h8a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z");
  svg.appendChild(shape);
  name.append(svg, railElement("span", "chat-session-title", project.name));
  head.append(name, railButton("⋯", "project-menu", project.id, "管理项目"));
  section.appendChild(head);
  if (expanded) {
    var children = railElement("div", "session-rail-members");
    railAppendPage(children, project.id, "暂无项目会话");
    section.appendChild(children);
  }
  return section;
}

function railSection(label) {
  var section = railElement("section", "session-rail-section");
  var head = railElement("div", "session-rail-section-head");
  head.appendChild(railElement("h2", "", label));
  section.appendChild(head);
  return section;
}

function renderClassicSessionRail(host) {
  var scroll = host.scrollTop;
  var focused = sessionRailPopup && sessionRailPopup.panel.contains(document.activeElement)
    ? sessionRailPopup.anchor.dataset
    : (host.contains(document.activeElement) ? document.activeElement.dataset : null);
  closeRailPopup();
  var pinned = railSection("置顶");
  railAppendPage(pinned, "pinned", "暂无置顶会话");
  var projects = railSection("项目");
  projects.firstChild.appendChild(railButton("+", "create", null, "新建项目"));
  railAppendPage(projects, "projects", "暂无项目");
  var recent = railSection("最近");
  if (sessionRailRefresh) recent.appendChild(railButton("有新的会话活动 · 刷新", "refresh"));
  railAppendPage(recent, "recent", sessionRailPending ? "" : "暂无历史会话");
  if (sessionRailPending) recent.appendChild(railElement("div", "chat-session-empty", "正在整理会话列表"));
  host.replaceChildren(pinned, projects, recent);
  if (sessionRailNotice) {
    var notice = railElement("div", "chat-session-empty", sessionRailNotice);
    notice.setAttribute("role", "alert");
    host.prepend(notice);
  }
  host.scrollTop = scroll;
  if (focused && focused.railAction) {
    var controls = Array.from(host.querySelectorAll("[data-rail-action]"));
    var next = controls.find(function (node) {
      return node.dataset.railAction === focused.railAction && node.dataset.railKey === focused.railKey;
    });
    if (next) next.focus({preventScroll: true});
  }
}

var sessionRailDefaults = {render: renderClassicSessionRail, dispose: closeRailPopup};

function repaintSessionRail() {
  if (!chatSessionMenu) return;
  var renderer = classicComponents.select(sessionRailPath, sessionRailDefaults);
  if (sessionRailMounted !== renderer && sessionRailMounted && sessionRailMounted.dispose) {
    sessionRailMounted.dispose(chatSessionMenu);
  }
  if (sessionRailMounted !== renderer) chatSessionMenu.replaceChildren();
  sessionRailMounted = renderer;
  if (renderer) renderer.render(chatSessionMenu, {
    page: function (key) { return JSON.parse(JSON.stringify(railPage(key))); },
    load: loadRailPage,
    mutate: mutateSessionRail,
    open: openConversationFromMenu
  });
  else chatSessionMenu.replaceChildren();
}

async function railRequest(query, body) {
  var options = body ? {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body)} : {};
  var response = await fetch(sessionCatalogUrl + "?" + new URLSearchParams(query), options);
  var result = await response.json();
  if (!response.ok && !result.preparing) throw new Error(result.error || "会话目录请求失败");
  return result;
}

async function loadRailPage(key, reset) {
  var page = railPage(key);
  if (page.busy && !reset) return;
  if (reset) {
    page = {items: page.items, cursor: null, loaded: false, busy: false, error: ""};
    sessionRailPages.set(key, page);
  }
  page.busy = true;
  page.error = "";
  var project = !["recent", "pinned", "projects"].includes(key);
  var query = {section: project ? "project" : key};
  if (project) query.project = key;
  if (page.cursor) query.before = JSON.stringify(page.cursor);
  repaintSessionRail();
  try {
    var result = await railRequest(query);
    if (railPage(key) !== page) return;
    if (result.warning) page.error = result.warning;
    if (key === "recent" && result.preparing) {
      sessionRailPending = true;
      setTimeout(function () {
        if (sessionRailPending && railPage(key) === page) void loadRailPage(key, true);
      }, 700);
    } else if (key === "recent") {
      sessionRailPending = false;
    }
    if (!result.ok && result.preparing) {
      if (key !== "recent") setTimeout(function () {
        if (railPage(key) === page && !page.loaded) void loadRailPage(key);
      }, 700);
      return;
    }
    var merged = new Map((query.before ? page.items : []).map(function (item) { return [item.id, item]; }));
    result.items.forEach(function (item) { merged.set(item.id, item); });
    page.items = Array.from(merged.values());
    page.cursor = result.next_before;
    page.loaded = true;
  } catch (error) {
    page.error = error.message;
  } finally {
    page.busy = false;
    if (railPage(key) === page) repaintSessionRail();
  }
}

function loadSessionRailList() {
  var rail = document.getElementById("sessionRail");
  if (!chatSessionMenu || !rail || rail.classList.contains("is-collapsed") ||
      !classicComponents.select(sessionRailPath, sessionRailDefaults)) return;
  ["recent", "pinned", "projects"].forEach(function (key) {
    if (!railPage(key).loaded) void loadRailPage(key);
  });
}

async function mutateSessionRail(body) {
  sessionRailNotice = "";
  try {
    var result = await railRequest({}, body);
    if (!result.ok) throw new Error(result.error || "无法保存，请重试");
    if (body.operation === "delete") {
      sessionRailExpanded.delete(body.project);
      sessionRailPages.delete(body.project);
    }
    if (["create", "rename", "delete"].includes(body.operation)) void loadRailPage("projects", true);
    if (["move", "delete", "pin"].includes(body.operation)) {
      void loadRailPage("pinned", true);
      void loadRailPage("recent", true);
      sessionRailExpanded.forEach(function (key) { void loadRailPage(key, true); });
    }
    return result;
  } catch (error) {
    sessionRailNotice = error.message;
    repaintSessionRail();
    return null;
  }
}

function railFindSession(id) {
  for (var page of sessionRailPages.values()) {
    var row = page.items.find(function (item) { return item.id === id; });
    if (row) return row;
  }
  return null;
}

function railProjectById(id) {
  return railPage("projects").items.find(function (item) { return item.id === id; });
}

function closeRailPopup(restoreFocus) {
  if (!sessionRailPopup) return;
  var popup = sessionRailPopup;
  sessionRailPopup = null;
  popup.panel.remove();
  popup.anchor.setAttribute("aria-expanded", "false");
  if (restoreFocus === true && popup.anchor.isConnected) popup.anchor.focus({preventScroll: true});
}

function positionRailPopup(popup) {
  var bounds = popup.anchor.getBoundingClientRect();
  var rail = chatSessionMenu.getBoundingClientRect();
  if (bounds.bottom <= rail.top || bounds.top >= rail.bottom || !bounds.width) {
    closeRailPopup();
    return;
  }
  var panel = popup.panel;
  var gap = 5;
  var edge = 8;
  var viewport = document.documentElement;
  var below = viewport.clientHeight - bounds.bottom - gap - edge;
  var above = bounds.top - gap - edge;
  panel.style.maxHeight = "";
  var openAbove = panel.offsetHeight > below && above > below;
  panel.style.maxHeight = Math.max(0, openAbove ? above : below) + "px";
  panel.style.left = Math.max(edge, Math.min(bounds.right - panel.offsetWidth,
    viewport.clientWidth - panel.offsetWidth - edge)) + "px";
  panel.style.top = (openAbove ? bounds.top - gap - panel.offsetHeight : bounds.bottom + gap) + "px";
}

function railMenu(button, controls) {
  var previous = sessionRailPopup;
  var fromPopup = previous && previous.panel.contains(button);
  var anchor = fromPopup ? previous.anchor : button;
  closeRailPopup();
  if (previous && previous.anchor === button) return;
  var panel = railElement("div", "session-rail-menu");
  if (fromPopup) panel.classList.add("session-rail-menu-move");
  panel.id = "sessionRailPopup";
  panel.setAttribute("role", "group");
  panel.setAttribute("aria-label", fromPopup ? "移动到项目" : (anchor.getAttribute("aria-label") || "操作"));
  panel.append.apply(panel, controls);
  document.body.appendChild(panel);
  sessionRailPopup = {anchor: anchor, panel: panel};
  anchor.setAttribute("aria-expanded", "true");
  positionRailPopup(sessionRailPopup);
  var first = panel.querySelector("button,select");
  if (first && panel.isConnected) first.focus({preventScroll: true});
}

async function railMoveDialog(button, item) {
  var controls = [];
  var before = null;
  var select = railElement("select", "session-rail-project-select");
  select.setAttribute("aria-label", "选择项目");
  select.appendChild(new Option("不归入项目", ""));
  do {
    var result = await railRequest({section: "projects", before: before ? JSON.stringify(before) : ""});
    if (!result.ok) throw new Error(result.error);
    result.items.forEach(function (project) { select.appendChild(new Option(project.name, project.id)); });
    before = result.next_before;
  } while (before && button.isConnected);
  if (!button.isConnected) return;
  select.value = item.project || "";
  controls.push(select, railButton("移动", "move", item.id));
  railMenu(button, controls);
}

function railProjectDialog(button, action, key) {
  var dialog = railElement("dialog", "session-rail-dialog");
  var form = railElement("form", "session-rail-dialog-form");
  form.method = "dialog";
  var project = key && railProjectById(key);
  var title = {create: "新建项目", rename: "重命名项目", delete: "删除项目"}[action];
  dialog.setAttribute("aria-label", title);
  form.appendChild(railElement("h2", "", title));
  var input = null;
  if (action === "delete") {
    form.appendChild(railElement("p", "", "项目内的会话会保留，并继续显示在最近。"));
  } else {
    var label = railElement("label", "", "项目名称");
    input = railElement("input", "session-rail-project-select");
    input.required = true;
    input.maxLength = 60;
    input.value = project ? project.name : "";
    label.appendChild(input);
    form.appendChild(label);
  }
  var actions = railElement("div", "session-rail-dialog-actions");
  var cancel = railElement("button", "mode-plus", "取消");
  cancel.value = "cancel";
  cancel.formNoValidate = true;
  var save = railElement("button", "mode-plus", action === "delete" ? "删除项目" : "保存");
  save.value = "save";
  actions.append(cancel, save);
  form.appendChild(actions);
  dialog.appendChild(form);
  document.body.appendChild(dialog);
  dialog.addEventListener("close", function () {
    dialog.remove();
    if (button.isConnected) button.focus();
    if (dialog.returnValue === "save") void mutateSessionRail({
      operation: action, project: key, name: input ? input.value : undefined
    });
  }, {once: true});
  dialog.showModal();
  if (input) input.select();
}

async function handleRailClick(event) {
  var button = event.target.closest("[data-rail-action]");
  if (!button || sessionRailMounted !== sessionRailDefaults) return;
  var inPopup = sessionRailPopup && sessionRailPopup.panel.contains(button);
  if (!inPopup && !chatSessionMenu.contains(button)) return;
  var action = button.dataset.railAction;
  var key = button.dataset.railKey;
  var item = railFindSession(key);
  if (action === "open" && item) openConversationFromMenu(key, item.title);
  if (action === "more") void loadRailPage(key);
  if (action === "refresh") {
    sessionRailRefresh = false;
    void loadRailPage("recent", true);
  }
  if (action === "toggle") {
    if (sessionRailExpanded.has(key)) sessionRailExpanded.delete(key);
    else {
      sessionRailExpanded.add(key);
      if (!railPage(key).loaded) void loadRailPage(key);
    }
    repaintSessionRail();
  }
  if (action === "session-menu" && item) railMenu(button, [
    railButton(item.pinned ? "取消置顶" : "置顶", "pin", key),
    railButton("移动到项目…", "choose", key)
  ]);
  if (action === "project-menu") railMenu(button, [
    railButton("重命名", "rename", key), railButton("删除项目", "delete", key)
  ]);
  if (action === "pin" && item) {
    closeRailPopup(true);
    await mutateSessionRail({operation: action, conversation_id: key, pinned: !item.pinned});
  }
  if (action === "choose" && item) {
    try {
      await railMoveDialog(button, item);
    } catch (error) {
      sessionRailNotice = error.message;
      repaintSessionRail();
    }
  }
  if (action === "move") {
    var destination = button.parentNode.querySelector("select").value;
    closeRailPopup(true);
    await mutateSessionRail({operation: action, conversation_id: key, project: destination});
  }
  if (["create", "rename", "delete"].includes(action)) {
    var anchor = inPopup ? sessionRailPopup.anchor : button;
    closeRailPopup();
    railProjectDialog(anchor, action, key);
  }
}

function sessionRailActivity(id, title) {
  if (!chatSessionMenu || !railPage("recent").loaded) return;
  if (title) sessionRailPages.forEach(function (page) {
    page.items.forEach(function (item) { if (item.id === id) item.title = title; });
  });
  if (title && railFindSession(id)) {
    repaintSessionRail();
    return;
  }
  if (chatSessionMenu.scrollTop > 60) {
    sessionRailRefresh = true;
    repaintSessionRail();
  } else {
    repaintSessionRail();
    clearTimeout(sessionRailActivity.timer);
    sessionRailActivity.timer = setTimeout(function () { void loadRailPage("recent", true); }, 250);
  }
}

if (chatSessionMenu) {
  document.addEventListener("click", handleRailClick);
  document.addEventListener("pointerdown", function (event) {
    if (!sessionRailPopup || sessionRailPopup.panel.contains(event.target) ||
        sessionRailPopup.anchor.contains(event.target)) return;
    closeRailPopup();
  });
  document.addEventListener("keydown", function (event) {
    if (!sessionRailPopup || event.key !== "Escape" || event.defaultPrevented) return;
    event.preventDefault();
    closeRailPopup(true);
  });
  window.addEventListener("resize", function () {
    if (sessionRailPopup) positionRailPopup(sessionRailPopup);
  });
  chatSessionMenu.addEventListener("scroll", function () {
    if (sessionRailPopup) positionRailPopup(sessionRailPopup);
    if (sessionRailMounted !== sessionRailDefaults) return;
    if (chatSessionMenu.scrollHeight - chatSessionMenu.clientHeight - chatSessionMenu.scrollTop < 56) {
      var page = railPage("recent");
      if (page.cursor && !page.error) void loadRailPage("recent");
    }
  }, {passive: true});
}
document.addEventListener("ai-agent:components-changed", function () {
  repaintSessionRail();
  loadSessionRailList();
});
document.addEventListener("ai-agent:conversation-title", function (event) {
  var tab = findConversationTab(event.detail.conversation_id);
  if (tab) sessionRailActivity(tab.id, tab.title);
});
