/* WebView 心跳：服务子进程被重启后刷新页面。 */
(function () {
  setInterval(function () {
    if (!window.pywebview || !window.pywebview.api) return;
    if (typeof window.pywebview.api.ensure_server !== "function") return;
    window.pywebview.api.ensure_server().then(function (restarted) {
      if (restarted) window.location.reload();
    }).catch(function () {});
  }, 1500);
})();
