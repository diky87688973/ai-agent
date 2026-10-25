/* background-tasks.js —— 输入框上方常驻后台任务面板。 */
(function () {
  "use strict";

  var STATUS_LABEL = {
    queued: "待执行",
    running: "进行中",
    completed: "已完成",
    failed: "失败",
    timed_out: "超时",
    cancelled: "已取消"
  };

  function byId(id) {
    return document.getElementById(id);
  }

  function currentCid() {
    try {
      if (typeof getActiveConversationId === "function") {
        var cid = String(getActiveConversationId() || "").trim();
        if (cid) return cid;
      }
      if (typeof getActiveTab === "function") {
        var tab = getActiveTab();
        if (tab && tab.id) return String(tab.id);
      }
    } catch (_e) {
      return "";
    }
    return "";
  }

  function request(method, path, body) {
    var options = { method: method, headers: { "Content-Type": "application/json" }, cache: "no-store" };
    if (body) options.body = JSON.stringify(body);
    return fetch(path, options).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) throw new Error(String(data && (data.error || data.message) || ("HTTP " + response.status)));
        return data;
      });
    });
  }

  function boot() {
    var panel = byId("bgTaskPanel");
    var toggle = byId("bgTaskToggle");
    var pop = byId("bgTaskPop");
    var list = byId("bgTaskList");
    var detail = byId("bgTaskDetail");
    var refreshBtn = byId("bgTaskRefresh");
    if (!panel || !toggle || !pop || !list || !detail) return;

    var open = false;
    var selected = "";
    var lastTasks = [];
    var loading = false;
    var timer = 0;

    function setCounts(tasks, summary) {
      var counts = { completed: 0, running: 0, queued: 0, failed: 0, cancelled: 0 };
      if (summary && typeof summary === "object") {
        counts.completed = Number(summary.completed || 0);
        counts.running = Number(summary.running || 0);
        counts.queued = Number(summary.queued || 0);
        counts.failed = Number(summary.failed || 0) + Number(summary.timed_out || 0);
        counts.cancelled = Number(summary.cancelled || 0);
      } else {
        tasks.forEach(function (task) {
          var status = String(task.status || "");
          if (status === "timed_out") status = "failed";
          if (counts[status] !== undefined) counts[status] += 1;
        });
      }
      Array.prototype.forEach.call(panel.querySelectorAll("[data-bg-status]"), function (node) {
        var status = node.getAttribute("data-bg-status");
        if (counts[status] !== undefined) node.textContent = counts[status] + " " + STATUS_LABEL[status];
      });
    }

    function sortTasks(tasks) {
      var rank = { running: 0, queued: 1, failed: 2, timed_out: 2, cancelled: 3, completed: 4 };
      return tasks.slice().sort(function (a, b) {
        var ra = rank[a.status] === undefined ? 5 : rank[a.status];
        var rb = rank[b.status] === undefined ? 5 : rank[b.status];
        if (ra !== rb) return ra - rb;
        return Number(b.created_at || 0) - Number(a.created_at || 0);
      });
    }

    function isActive(task) {
      return task && (task.status === "running" || task.status === "queued");
    }

    function renderList() {
      list.innerHTML = "";
      if (!lastTasks.length) {
        var empty = document.createElement("div");
        empty.className = "bg-task-empty";
        empty.textContent = "暂无后台任务";
        list.appendChild(empty);
        return;
      }
      sortTasks(lastTasks).forEach(function (task) {
        var row = document.createElement("div");
        row.className = "bg-task-row" + (String(task.task_id) === selected ? " is-active" : "");
        row.setAttribute("data-task-id", String(task.task_id || ""));
        row.setAttribute("data-status", String(task.status || ""));

        var dot = document.createElement("span");
        dot.className = "bg-task-dot";
        dot.setAttribute("data-bg-status", String(task.status || ""));
        row.appendChild(dot);

        var id = document.createElement("span");
        id.className = "bg-task-id";
        id.textContent = String(task.task_id || "").slice(0, 10);
        row.appendChild(id);

        var label = document.createElement("span");
        label.className = "bg-task-label";
        label.textContent = String(task.label || (Array.isArray(task.argv) ? task.argv.join(" ") : ""));
        row.appendChild(label);

        var meta = document.createElement("span");
        meta.className = "bg-task-meta";
        meta.textContent = STATUS_LABEL[task.status] || String(task.status || "");
        row.appendChild(meta);

        if (isActive(task)) {
          var cancel = document.createElement("button");
          cancel.type = "button";
          cancel.className = "bg-task-cancel";
          cancel.setAttribute("data-bg-cancel", String(task.task_id || ""));
          cancel.textContent = "取消";
          row.appendChild(cancel);
        }
        list.appendChild(row);
      });
    }

    function renderDetail(data) {
      var task = data && data.task ? data.task : data;
      if (!task) {
        detail.classList.add("hidden");
        return;
      }
      var output = data && data.output !== undefined ? data.output : "";
      var stderr = data && data.stderr !== undefined ? data.stderr : "";
      detail.innerHTML = "";
      detail.classList.remove("hidden");

      var head = document.createElement("div");
      head.className = "bg-task-detail-head";
      var title = document.createElement("span");
      title.className = "bg-task-detail-title";
      title.textContent = "任务 " + String(task.task_id || "");
      head.appendChild(title);
      var close = document.createElement("button");
      close.type = "button";
      close.className = "bg-task-detail-close";
      close.setAttribute("data-bg-close", "1");
      close.textContent = "×";
      head.appendChild(close);
      detail.appendChild(head);

      var dl = document.createElement("dl");
      dl.className = "bg-task-kv";
      function add(k, v) {
        var dt = document.createElement("dt");
        dt.textContent = k;
        var dd = document.createElement("dd");
        dd.textContent = v === null || v === undefined || v === "" ? "—" : String(v);
        dl.appendChild(dt);
        dl.appendChild(dd);
      }
      add("状态", STATUS_LABEL[task.status] || task.status);
      add("批次", task.batch);
      add("参数", Array.isArray(task.argv) ? task.argv.join(" ") : "");
      add("目录", task.cwd);
      add("PID", task.pid);
      add("超时", task.timeout_sec ? task.timeout_sec + "s" : "—");
      add("退出码", task.exit_code);
      add("说明", task.detail);
      detail.appendChild(dl);

      if (output) {
        var out = document.createElement("pre");
        out.className = "bg-task-pre";
        out.textContent = output;
        detail.appendChild(out);
      }
      if (stderr) {
        var err = document.createElement("pre");
        err.className = "bg-task-pre";
        err.textContent = stderr;
        detail.appendChild(err);
      }
      var actions = document.createElement("div");
      actions.className = "bg-task-detail-actions";
      if (isActive(task)) {
        var cancel = document.createElement("button");
        cancel.type = "button";
        cancel.className = "bg-task-cancel";
        cancel.setAttribute("data-bg-cancel", String(task.task_id || ""));
        cancel.textContent = "取消任务";
        actions.appendChild(cancel);
      }
      detail.appendChild(actions);
    }

    function showDetail(taskId) {
      var cid = currentCid();
      if (!cid || !taskId) return;
      selected = String(taskId);
      renderList();
      var base = lastTasks.filter(function (task) { return String(task.task_id) === selected; })[0] || {};
      request("POST", "/api/background/tasks/output", {
        conversation_id: cid,
        task_id: selected,
        wait: false
      }).then(function (data) {
        renderDetail({
          task: Object.assign({}, base, { status: String(data.status || base.status || "") }),
          output: data.output,
          stderr: data.stderr
        });
      }).catch(function (error) {
        renderDetail({ task: Object.assign({}, base, { detail: String(error) }) });
      });
    }

    function refresh() {
      var cid = currentCid();
      if (!cid || loading) return Promise.resolve();
      loading = true;
      return request("GET", "/api/background/tasks?conversation_id=" + encodeURIComponent(cid))
        .then(function (data) {
          lastTasks = Array.isArray(data.tasks) ? data.tasks : [];
          panel.classList.toggle("hidden", !lastTasks.length);
          syncComposerColumns();
          if (!lastTasks.length && open) setOpen(false);
          setCounts(lastTasks, data.counts);
          if (open) renderList();
          if (selected) {
            var current = lastTasks.filter(function (task) { return String(task.task_id) === selected; })[0];
            if (current && open) showDetail(selected);
          }
        })
        .catch(function () {
          if (open) {
            list.innerHTML = "";
            var error = document.createElement("div");
            error.className = "bg-task-empty";
            error.textContent = "后台任务暂不可用";
            list.appendChild(error);
          }
        })
        .finally(function () { loading = false; });
    }

    function setOpen(next) {
      open = !!next;
      pop.classList.toggle("hidden", !open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) {
        refresh().then(renderList);
      } else {
        selected = "";
        detail.classList.add("hidden");
      }
    }

    function syncComposerColumns() {
      var left = byId("composerLeft");
      var parent = left ? left.closest(".composer-above") : null;
      if (!left || !parent) return;
      var queue = byId("chatQueue");
      var draft = byId("queueDraft");
      var speak = byId("aiSpeakSlot");
      var leftVisible = !!(
        (queue && !queue.classList.contains("hidden")) ||
        (draft && !draft.classList.contains("hidden")) ||
        (speak && speak.querySelector(".ai-speak-player:not([hidden])"))
      );
      var taskVisible = !panel.classList.contains("hidden");
      left.classList.toggle("is-empty", !leftVisible);
      parent.classList.toggle("has-empty-left", !leftVisible);
      parent.classList.toggle("has-no-task", !taskVisible);
    }

    if (window.MutationObserver) {
      var observer = new MutationObserver(syncComposerColumns);
      [byId("chatQueue"), byId("queueDraft"), byId("aiSpeakSlot"), panel].forEach(function (node) {
        if (node) observer.observe(node, { attributes: true, childList: true, subtree: true, attributeFilter: ["class", "hidden", "style"] });
      });
      window.addEventListener("beforeunload", function () { observer.disconnect(); });
    }

    toggle.addEventListener("click", function (event) {
      event.stopPropagation();
      setOpen(!open);
    });
    refreshBtn.addEventListener("click", function (event) {
      event.stopPropagation();
      refresh();
    });
    pop.addEventListener("click", function (event) { event.stopPropagation(); });
    list.addEventListener("click", function (event) {
      var cancel = event.target.closest("[data-bg-cancel]");
      if (cancel) {
        event.stopPropagation();
        var id = cancel.getAttribute("data-bg-cancel");
        var cid = currentCid();
        if (id && cid) {
          request("POST", "/api/background/tasks/cancel", {
            conversation_id: cid,
            task_id: id,
            reason: "ui cancel"
          }).then(refresh).catch(function () {});
        }
        return;
      }
      var row = event.target.closest("[data-task-id]");
      if (row) showDetail(row.getAttribute("data-task-id"));
    });
    detail.addEventListener("click", function (event) {
      if (event.target.closest("[data-bg-close]")) {
        selected = "";
        detail.classList.add("hidden");
        renderList();
        return;
      }
      var cancel = event.target.closest("[data-bg-cancel]");
      if (!cancel) return;
      var cid = currentCid();
      if (!cid) return;
      request("POST", "/api/background/tasks/cancel", {
        conversation_id: cid,
        task_id: cancel.getAttribute("data-bg-cancel"),
        reason: "ui cancel"
      }).then(refresh).catch(function () {});
    });
    document.addEventListener("pointerdown", function (event) {
      if (!open || panel.contains(event.target)) return;
      setOpen(false);
    }, true);
    document.addEventListener("click", function (event) {
      if (!open || panel.contains(event.target)) return;
      setOpen(false);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && open) setOpen(false);
    });

    syncComposerColumns();
    timer = window.setInterval(refresh, 1500);
    window.addEventListener("beforeunload", function () { window.clearInterval(timer); });
    refresh();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
