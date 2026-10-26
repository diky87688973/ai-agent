# -*- coding: utf-8 -*-
"""登录页与 /auth/* 的 HTTP 形状；不实现密码或会话存储细节。"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from agent.core.error_report import report_error
from agent.shell.web.auth.authenticator import is_loopback
from agent.shell.web.auth.models import COOKIE_NAME, AuthIdentity
from agent.shell.web.auth.password import verify_password
from agent.shell.web.auth.security import AuthSecurityError

LOGIN_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>登录 · AI Agent</title>
<style>
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
 background:#15171c;color:#e8ecf1;font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.card{width:min(360px,calc(100vw - 40px));background:#1e2229;border:1px solid #303641;
 border-radius:12px;padding:26px;box-shadow:0 18px 60px #0008}
h1{margin:0 0 6px;font-size:20px}
p{margin:0 0 20px;color:#9aa4b2;font-size:12px}
label{display:block;margin:12px 0 6px;color:#b9c2cf;font-size:12px}
input{width:100%;padding:10px 11px;border:1px solid #3b4452;border-radius:7px;
 background:#15181e;color:#e8ecf1;font:inherit;outline:none}
input:focus{border-color:#5686fe}
button{margin-top:18px;width:100%;padding:10px;border:0;border-radius:7px;
 background:#5686fe;color:#fff;font:inherit;cursor:pointer}
button:disabled{opacity:.6;cursor:default}
.error{min-height:18px;margin-top:10px;color:#ff8a87;font-size:12px}
</style>
</head>
<body>
<form class="card" id="f">
  <h1>AI Agent</h1>
  <p>请输入访问密码</p>
  <label for="p">密码</label>
  <input id="p" type="password" autocomplete="current-password" required autofocus>
  <button id="go" type="submit">登录</button>
  <div class="error" id="e"></div>
</form>
<script>
(function(){
  var f=document.getElementById("f"),p=document.getElementById("p"),
      e=document.getElementById("e"),go=document.getElementById("go");
  f.addEventListener("submit",function(event){
    event.preventDefault();e.textContent="";go.disabled=true;
    fetch("/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({password:p.value})}).then(function(r){
      return r.json().catch(function(){return {};}).then(function(j){
        if(r.ok&&j.ok){
          var next=new URLSearchParams(location.search).get("next")||"/";
          if(next.charAt(0)!=="/"||next.charAt(1)==="/")next="/";
          location.replace(next);return;
        }
        e.textContent=j.error==="rate_limited"?"尝试过多，请稍后再试":
          j.error==="setup_required"?"尚未设置访问密码":"密码错误";
        go.disabled=false;
      });
    }).catch(function(){e.textContent="登录请求失败";go.disabled=false;});
  });
})();
</script>
</body>
</html>"""


DESKTOP_LOGIN_PAGE = """<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Agent</title>
<style>
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
 background:#15171c;color:#e8ecf1;font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.card{width:min(360px,calc(100vw - 40px));background:#1e2229;border:1px solid #303641;
 border-radius:12px;padding:26px;box-shadow:0 18px 60px #0008}
h1{margin:0 0 8px;font-size:20px}p{margin:0;color:#9aa4b2;font-size:12px}
.error{min-height:18px;margin-top:12px;color:#ff8a87;font-size:12px}
</style></head>
<body><div class="card"><h1>AI Agent</h1><p>正在准备桌面会话…</p>
<div class="error" id="e"></div></div>
<script>
(function(){
 var token=location.hash ? location.hash.slice(1) : "";
 try{history.replaceState(null,"","/desktop-login");}catch(e){}
 if(!token){document.getElementById("e").textContent="缺少桌面引导令牌，请从桌面应用启动。";return;}
 fetch("/auth/desktop",{method:"POST",credentials:"same-origin",
   headers:{"Content-Type":"application/json"},body:JSON.stringify({token:token})})
 .then(function(r){return r.json().catch(function(){return {};}).then(function(j){
   if(r.ok&&j.ok){location.replace("/");return;}
   document.getElementById("e").textContent="桌面会话创建失败，请重新启动桌面应用。";
 });})
 .catch(function(){document.getElementById("e").textContent="桌面会话创建失败，请重新启动桌面应用。";});
})();
</script></body></html>"""


def _cookie(value: str, max_age: int, secure: bool) -> str:
    parts = [
        f"{COOKIE_NAME}={value}",
        "Path=/",
        "HttpOnly",
        "SameSite=Strict",
        f"Max-Age={int(max_age)}",
    ]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def _clear_cookie(secure: bool) -> str:
    return _cookie("", 0, secure)


class AuthRoutes:
    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    def page(self) -> str:
        return LOGIN_PAGE

    def desktop_page(self) -> str:
        return DESKTOP_LOGIN_PAGE

    def desktop_login(self, token: str, remote_ip: str,
                      secure: Optional[bool] = None) -> Tuple[int, Dict[str, Any], Dict[str, str]]:
        if not is_loopback(remote_ip):
            self.runtime.audit.write("desktop_failed", remote_ip=remote_ip,
                                     reason="loopback_required")
            return 403, {"ok": False, "error": "loopback_required"}, {}
        key = f"desktop:{remote_ip}"
        if not self.runtime.limiter.allowed(key):
            self.runtime.audit.write("desktop_failed", remote_ip=remote_ip,
                                     reason="rate_limited")
            return 429, {"ok": False, "error": "rate_limited"}, {
                "Retry-After": str(self.runtime.config.lock_seconds)}
        if not self.runtime.bootstrap.consume(token):
            self.runtime.limiter.fail(key)
            self.runtime.audit.write("desktop_failed", remote_ip=remote_ip,
                                     reason="token_invalid")
            return 403, {"ok": False, "error": "desktop_token_invalid"}, {}
        self.runtime.limiter.success(key)
        raw, session = self.runtime.sessions.create()
        self.runtime.audit.write("desktop_success", remote_ip=remote_ip)
        return 200, {"ok": True, "csrf": session.csrf}, {
            "Set-Cookie": _cookie(
                raw, self.runtime.config.session_seconds,
                self.runtime.secure_cookie if secure is None else secure,
            ),
            "Cache-Control": "no-store",
        }

    def login(self, password: str, remote_ip: str,
              secure: Optional[bool] = None) -> Tuple[int, Dict[str, Any], Dict[str, str]]:
        credentials = self.runtime.credentials
        if not credentials.exists():
            self.runtime.audit.write("login_failed", remote_ip=remote_ip,
                                     reason="setup_required")
            return 503, {"ok": False, "error": "setup_required"}, {}
        key = f"ip:{remote_ip}"
        if not self.runtime.limiter.allowed(key):
            self.runtime.audit.write("login_failed", remote_ip=remote_ip,
                                     reason="rate_limited")
            return 429, {"ok": False, "error": "rate_limited"}, {
                "Retry-After": str(self.runtime.config.lock_seconds)}
        try:
            record = credentials.password_record()
        except AuthSecurityError as exc:
            report_error("agent.shell.web.auth.routes.credentials", exc)
            return 503, {"ok": False, "error": "auth_unavailable"}, {}
        if not verify_password(password, record):
            self.runtime.limiter.fail(key)
            self.runtime.audit.write("login_failed", remote_ip=remote_ip,
                                     reason="invalid_credentials")
            return 401, {"ok": False, "error": "invalid_credentials"}, {}
        self.runtime.limiter.success(key)
        token, session = self.runtime.sessions.create()
        self.runtime.audit.write("login_success", remote_ip=remote_ip)
        headers = {
            "Set-Cookie": _cookie(
                token, self.runtime.config.session_seconds,
                self.runtime.secure_cookie if secure is None else secure,
            ),
            "Cache-Control": "no-store",
        }
        return 200, {"ok": True, "csrf": session.csrf}, headers

    def status(self, identity: Optional[AuthIdentity], raw_cookie: str = "") -> Tuple[int, Dict[str, Any], Dict[str, str]]:
        if identity is None:
            return 200, {"ok": True, "authenticated": False}, {"Cache-Control": "no-store"}
        payload = {
            "ok": True,
            "authenticated": True,
            "subject": identity.principal.subject,
            "kind": identity.principal.kind,
            "scopes": sorted(identity.principal.scopes),
        }
        if identity.session is not None:
            payload["expires_at"] = int(identity.session.expires_at)
        return 200, payload, {"Cache-Control": "no-store"}

    def csrf(self, identity: Optional[AuthIdentity]) -> Tuple[int, Dict[str, Any], Dict[str, str]]:
        if identity is None or identity.session is None:
            return 401, {"ok": False, "error": "unauthorized"}, {}
        return 200, {"ok": True, "csrf": identity.session.csrf}, {"Cache-Control": "no-store"}

    def logout(self, identity: Optional[AuthIdentity], raw_cookie: str,
               secure: Optional[bool] = None) -> Tuple[int, Dict[str, Any], Dict[str, str]]:
        if raw_cookie:
            self.runtime.sessions.revoke(raw_cookie)
        return 200, {"ok": True}, {
            "Set-Cookie": _clear_cookie(
                self.runtime.secure_cookie if secure is None else secure),
            "Cache-Control": "no-store",
        }
