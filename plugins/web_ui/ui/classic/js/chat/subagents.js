/* subagents.js —— 右侧子智能体列表与子会话标签入口。 */
(function () {
  "use strict";

  function byId(id) {
    return document.getElementById(id);
  }

  function currentCid() {
    try {
      if (typeof getActiveTab === "function") {
        var tab = getActiveTab();
        if (tab && tab.subagent && tab.parentCid) return String(tab.parentCid).trim();
      }
      if (typeof getActiveConversationId === "function") {
        return String(getActiveConversationId() || "").trim();
      }
    } catch (_e) {
      return "";
    }
    return "";
  }

  function request(method, path) {
    return fetch(path, { method: method, headers: { "Content-Type": "application/json" }, cache: "no-store" })
      .then(function (response) {
        return response.json().catch(function () { return {}; }).then(function (data) {
          if (!response.ok) throw new Error(String(data && (data.error || data.message) || ("HTTP " + response.status)));
          return data;
        });
      });
  }

  function openChild(child, label, batch, parent) {
    if (!child || typeof openConversationFromMenu !== "function") return;
    var existing = typeof findConversationTab === "function" ? findConversationTab(child) : null;
    if (existing) {
      if (typeof switchConversationTab === "function") switchConversationTab(child);
      return;
    }
    if (typeof openSubagentConversation === "function") {
      openSubagentConversation(child, label || ("子智能体 " + String(child).slice(0, 8)), parent, batch);
      return;
    }
    openConversationFromMenu(child, label || ("子智能体 " + String(child).slice(0, 8)));
  }

  function boot() {
    var panel = byId("subagentPanel");
    var toggle = byId("subagentToggle");
    var pop = byId("subagentPop");
    var list = byId("subagentList");
    if (!panel || !toggle || !pop || !list) return;

    var open = false;
    var loading = false;
    var timer = 0;
    var rows = [];
    var refreshSeq = 0;

    function setOpen(next) {
      open = !!next;
      pop.classList.toggle("hidden", !open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) refresh();
    }

    function setCounts(busy, idle) {
      Array.prototype.forEach.call(panel.querySelectorAll("[data-sub-status]"), function (node) {
        var key = node.getAttribute("data-sub-status");
        if (key === "busy") node.textContent = busy + " 进行中";
        if (key === "idle") node.textContent = idle + " 已完成";
      });
    }

    function render() {
      list.innerHTML = "";
      if (!rows.length) {
        var empty = document.createElement("div");
        empty.className = "subagent-empty";
        empty.textContent = "暂无子智能体";
        list.appendChild(empty);
        return;
      }
      rows.forEach(function (row) {
        var item = document.createElement("div");
        item.className = "subagent-row";
        item.setAttribute("data-child-id", row.child_id);
        item.setAttribute("data-parent-cid", row.parent_cid);
        item.setAttribute("data-batch", row.batch);

        var dot = document.createElement("span");
        dot.className = "subagent-dot";
        dot.setAttribute("data-sub-status", row.status);
        item.appendChild(dot);

        var batch = document.createElement("span");
        batch.className = "subagent-batch";
        batch.textContent = String(row.batch || "");
        item.appendChild(batch);

        var label = document.createElement("span");
        label.className = "subagent-label";
        label.textContent = String(row.label || "");
        item.appendChild(label);

        var button = document.createElement("button");
        button.type = "button";
        button.className = "subagent-open";
        button.setAttribute("data-open-child", row.child_id);
        button.title = "打开会话";
        button.setAttribute("aria-label", "打开会话");
        button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h6"/><path d="m21 3-9 9"/><path d="M15 3h6v6"/></svg>';
        item.appendChild(button);
        list.appendChild(item);
      });
    }

    function refresh() {
      var active = typeof getActiveTab === "function" ? getActiveTab() : null;
      if (active && active.subagent) {
        refreshSeq += 1;
        rows = [];
        open = false;
        pop.classList.add("hidden");
        toggle.setAttribute("aria-expanded", "false");
        panel.classList.add("hidden");
        setCounts(0, 0);
        if (typeof syncComposerColumns === "function") syncComposerColumns();
        return Promise.resolve();
      }
      var parent = currentCid();
      if (!parent || loading) return Promise.resolve();
      var seq = ++refreshSeq;
      loading = true;
      return request("GET", "/api/subagents?conversation_id=" + encodeURIComponent(parent))
        .then(function (data) {
          if (seq !== refreshSeq) return;
          var batches = Array.isArray(data.batches) ? data.batches : [];
          rows = [];
          batches.forEach(function (batch) {
            (batch.children || []).forEach(function (child) {
              rows.push({
                child_id: String(child.child_id || ""),
                parent_cid: parent,
                batch: String(batch.batch || ""),
                label: String(child.label || ""),
                status: String(child.status || "idle")
              });
            });
          });
          panel.classList.toggle("hidden", !rows.length);
          setCounts(Number(data.counts && data.counts.busy || 0), Number(data.counts && data.counts.idle || 0));
          if (open) render();
          if (!rows.length && open) setOpen(false);
          if (typeof syncComposerColumns === "function") syncComposerColumns();
        })
        .catch(function () {
          if (open) {
            list.innerHTML = "";
            var error = document.createElement("div");
            error.className = "subagent-empty";
            error.textContent = "子智能体暂不可用";
            list.appendChild(error);
          }
        })
        .finally(function () { loading = false; });
    }

    toggle.addEventListener("click", function (event) {
      event.stopPropagation();
      setOpen(!open);
    });
    pop.addEventListener("click", function (event) { event.stopPropagation(); });
    list.addEventListener("click", function (event) {
      var button = event.target.closest("[data-open-child]");
      if (button) {
        event.stopPropagation();
        var row = button.closest("[data-child-id]");
        if (row) openChild(row.getAttribute("data-child-id"),
          row.querySelector(".subagent-label") ? row.querySelector(".subagent-label").textContent : "",
          row.getAttribute("data-batch"), row.getAttribute("data-parent-cid"));
        return;
      }
      var line = event.target.closest("[data-child-id]");
      if (line) {
        var label = line.querySelector(".subagent-label");
        openChild(line.getAttribute("data-child-id"),
          label ? label.textContent : "",
          line.getAttribute("data-batch"), line.getAttribute("data-parent-cid"));
      }
    });
    document.addEventListener("pointerdown", function (event) {
      if (!open || panel.contains(event.target)) return;
      setOpen(false);
    }, true);
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && open) setOpen(false);
    });

    document.addEventListener("ai-agent:conversation-changed", refresh);
    timer = window.setInterval(refresh, 3000);
    window.addEventListener("beforeunload", function () { window.clearInterval(timer); });
    refresh();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
