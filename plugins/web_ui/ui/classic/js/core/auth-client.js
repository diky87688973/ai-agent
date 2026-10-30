/* core/auth-client.js —— 统一 Cookie 凭据与 CSRF 注入。 */
(function () {
  "use strict";
  if (window.__aiAgentAuthFetch) return;
  window.__aiAgentAuthFetch = true;

  var rawFetch = window.fetch.bind(window);
  var csrfToken = "";
  var csrfPending = null;

  function isUnsafe(method) {
    return ["POST", "PUT", "PATCH", "DELETE"].indexOf(String(method || "GET").toUpperCase()) >= 0;
  }

  function currentPath(input) {
    try {
      var raw = typeof input === "string" ? input : String(input && input.url || "");
      return new URL(raw, window.location.href).pathname;
    } catch (e) {
      return "";
    }
  }

  function needLogin(input) {
    var path = currentPath(input);
    return path !== "/login" && path !== "/auth/login" && path !== "/auth/status";
  }

  function redirectLogin() {
    if (window.location.pathname === "/login") return;
    var next = window.location.pathname + window.location.search;
    window.location.replace("/login?next=" + encodeURIComponent(next));
  }

  function readCsrf() {
    if (csrfToken) return Promise.resolve(csrfToken);
    if (csrfPending) return csrfPending;
    csrfPending = rawFetch("/auth/csrf", {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store"
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (body) {
        if (response.ok && body && body.csrf) csrfToken = String(body.csrf);
        return csrfToken;
      });
    }).catch(function () {
      return "";
    }).then(function (token) {
      csrfPending = null;
      return token;
    });
    return csrfPending;
  }

  window.fetch = function (input, init) {
    var options = init ? Object.assign({}, init) : {};
    options.credentials = options.credentials || "same-origin";
    var method = String(options.method || "GET").toUpperCase();
    var request = isUnsafe(method)
      ? readCsrf().then(function (token) {
          var headers = new Headers(options.headers || {});
          if (token) headers.set("X-CSRF-Token", token);
          options.headers = headers;
          return rawFetch(input, options);
        })
      : rawFetch(input, options);
    return request.then(function (response) {
      if (response.status === 401 && needLogin(input)) redirectLogin();
      return response;
    });
  };
})();
