/* update.js —— 顶部更新入口。 */
(function () {
  "use strict";

  function boot() {
    var btn = document.getElementById("updateBtn");
    var label = document.getElementById("updateLabel");
    if (!btn || !label) return;
    var staged = false;
    var available = false;
    var failed = false;
    var version = "";
    var busy = false;
    var intervalMinutes = 30;
    var timer = null;

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
      timer = null;
      timer = setTimeout(check, Math.max(1, intervalMinutes) * 60 * 1000);
    }

    function applyStatus(data) {
      staged = !!data.staged;
      available = !!data.available;
      intervalMinutes = Number(data.interval_minutes || 30);
      failed = String(data.detail || "").indexOf("check_failed") === 0;
      version = String(data.version || data.remote || "");
      btn.classList.remove("update-btn-error");
      if (data.available) {
        btn.classList.remove("hidden");
        set(staged ? "重启更新" + (version ? " v" + version : "") : "更新" + (version ? " v" + version : ""),
            staged ? "下载完成，重启应用完成更新" : "下载并验证新版本");
      } else if (failed) {
        btn.classList.add("update-btn-error");
        btn.classList.remove("hidden");
        set("更新检查失败", String(data.detail || "检查失败，点击重试"));
      } else {
        btn.classList.add("hidden");
      }
      schedule();
    }

    function check() {
      request("POST", "/api/update/check")
        .then(applyStatus)
        .catch(function () { btn.classList.add("hidden"); schedule(); });
    }

    btn.addEventListener("click", function () {
      if (busy) return;
      if (failed) {
        if (timer) clearTimeout(timer);
        timer = null;
        set("检查中…");
        request("POST", "/api/update/check")
          .then(applyStatus)
          .catch(function (error) { set("更新检查失败", String(error)); schedule(); })
          .then(function () { btn.disabled = false; busy = false; });
        return;
      }
      busy = true;
      btn.disabled = true;
      set(staged ? "重启中…" : "下载中…");
      request("POST", staged ? "/api/update/apply" : "/api/update/download")
        .then(function (data) {
          if (staged) {
            set("重启中…", "应用即将重启");
            return;
          }
          if (data.staged) {
            set("重启中…", "应用即将重启");
            request("POST", "/api/update/apply").catch(function (error) {
              set("更新失败", String(error));
              btn.disabled = false;
              busy = false;
            });
            return;
          }
          applyStatus(data);
          btn.disabled = false;
          busy = false;
        })
        .catch(function (error) {
          set("更新失败", String(error));
          btn.disabled = false;
          busy = false;
        });
    });

    check();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
