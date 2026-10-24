/* update.js —— 顶部更新入口。 */
(function () {
  "use strict";

  function boot() {
    var btn = document.getElementById("updateBtn");
    var label = document.getElementById("updateLabel");
    if (!btn || !label) return;
    var staged = false;
    var version = "";
    var busy = false;

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

    function applyStatus(data) {
      staged = !!data.staged;
      version = String(data.version || data.remote || "");
      if (data.available) {
        btn.classList.remove("hidden");
        set(staged ? "重启更新" + (version ? " " + version : "") : "更新" + (version ? " " + version : ""),
            staged ? "下载完成，重启应用完成更新" : "下载并验证新版本");
      } else {
        btn.classList.add("hidden");
      }
    }

    function check() {
      request("POST", "/api/update/check")
        .then(applyStatus)
        .catch(function () { btn.classList.add("hidden"); });
    }

    btn.addEventListener("click", function () {
      if (busy) return;
      busy = true;
      btn.disabled = true;
      set(staged ? "重启中…" : "下载中…");
      request("POST", staged ? "/api/update/apply" : "/api/update/download")
        .then(function (data) {
          if (staged) {
            set("重启中…", "应用即将重启");
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
