/* update.js —— 顶部更新入口。 */
(function () {
  "use strict";

  function boot() {
    var btn = document.querySelector('[data-ui-action="auto_update.check"]');
    if (!btn) {
      window.setTimeout(boot, 200);
      return;
    }
    if (btn._updateBound) return;
    btn._updateBound = true;
    var label = btn;
    var staged = false;
    var available = false;
    var busy = false;
    var failed = false;
    var timer = null;
    var intervalMinutes = 30;

    function set(text, title) {
      label.textContent = text;
      btn.title = title || text;
    }

    function request(method, path) {
      return fetch(path, { method: method, headers: { "Content-Type": "application/json" }, cache: "no-store" })
        .then(function (response) {
          return response.json().catch(function () { return {}; }).then(function (data) {
            if (!response.ok || data.ok === false) {
              throw new Error(String(data.error || "更新失败"));
            }
            return data;
          });
        });
    }

    function schedule() {
      if (timer) clearTimeout(timer);
      timer = setTimeout(check, Math.max(1, intervalMinutes) * 60 * 1000);
    }

    function applyStatus(data) {
      staged = !!data.staged;
      available = !!data.available;
      intervalMinutes = Number(data.interval_minutes || 30);
      failed = false;
      if (staged) { set("重启应用更新", "更新已下载"); btn.classList.remove("hidden"); return; }
      if (available) { set("发现新版本", "点击更新"); btn.classList.remove("hidden"); return; }
      btn.classList.add("hidden");
      set("版本更新", "检查更新");
      schedule();
    }

    function check() {
      if (busy) return;
      busy = true;
      btn.disabled = true;
      request("POST", "/api/update/check")
        .then(applyStatus)
        .catch(function () { failed = true; schedule(); })
        .then(function () { btn.disabled = false; busy = false; });
    }

    btn.addEventListener("click", function () {
      if (busy) return;
      if (failed) { failed = false; check(); return; }
      busy = true;
      btn.disabled = true;
      if (staged) {
        set("重启中…", "应用即将更新");
        request("POST", "/api/update/apply").catch(function () { check(); });
        return;
      }
      request("POST", "/api/update/apply")
        .catch(function (error) {
          set("检查更新", String(error));
          btn.disabled = false;
          busy = false;
          check();
        });
    });

    window.autoUpdateUi = { check: check };
    btn.classList.add("hidden");
    check();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
