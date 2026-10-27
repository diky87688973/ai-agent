**English** | [中文](http-auth.zh.md)

# HTTP authentication

The web shell authenticates every handled HTTP request at the Handler entry, before route dispatch. Built-in routes and plugin routes pass the same guard; a plugin cannot opt out.

## 1. Scope

Authentication is single-operator, not multi-tenant. An unauthenticated network client cannot:

```text
send messages
execute tools
read files
change settings
trigger updates
open an SSE stream
```

The service binds `127.0.0.1` by default. `--host` can bind another address; a non-loopback bind requires credentials and, unless explicitly waived, TLS.

## 2. Threat model

Handled:

```text
arbitrary calls from a public network
CSRF
password brute force
session theft
token leakage into URLs or logs
plugin routes bypassing authentication
static assets or SSE bypassing authentication
a reverse proxy making public requests look local
```

Not handled:

```text
an attacker who already has administrator rights on the host
an attacker who controls the browser or the operating system
keyloggers
an authorized operator acting maliciously
```

## 3. Authentication modes

```ini
[auth]
mode = auto
```

```text
auto       loopback requests bypass on a loopback bind; other requests authenticate
required   every request authenticates
local      only loopback binds are accepted
```

### auto

The loopback bypass applies only when both conditions hold:

```text
the server is bound to a loopback address
the request peer address is loopback
```

Such a request is treated as the local operator with all scopes. Requests from any other peer need a session cookie or a Bearer token.

### required

The loopback bypass is disabled, including when the server is bound to a loopback address. Every request needs a session cookie or a Bearer token. This is the mode for reverse proxies, public mappings, and remote access.

### local

Only a loopback bind address starts. A non-loopback bind exits with code 2. With a loopback bind, loopback requests bypass authentication as in `auto`.

### Startup checks

```text
non-loopback bind without a password and without a loaded provider
  → exit code 2
  → message points to agent-web --set-password

non-loopback bind without TLS and without --allow-insecure-public
  → exit code 2
  → message names the TLS or reverse proxy options

mode = local with a non-loopback bind
  → exit code 2
```

A public bind never starts without authentication. A configured provider that fails to load also blocks a public bind, even when a password exists.

## 4. Password credentials

Create or replace the password:

```bash
agent-web --set-password
```

Input rules:

```text
interactive, no echo
entered twice and compared
at least 12 characters
never accepted as a command-line argument
never stored in plaintext in config.ini
```

Storage: `data/auth/credentials.json`

```json
{
  "version": 1,
  "password": {
    "algo": "scrypt",
    "salt": "base64",
    "hash": "base64",
    "n": 16384,
    "r": 8,
    "p": 1
  }
}
```

Hashing uses only the standard library:

```text
hashlib.scrypt
hmac.compare_digest
secrets.token_bytes
```

No password library is added.

File permissions:

```text
Windows: DACL limited to the current user, SYSTEM, Administrators, and OWNER RIGHTS;
         inheritance removed; an additional allowed ACE fails verification
POSIX:   directory 0700, files 0600; the owner is the current user;
         group and other permission bits are zero
macOS:   extended ACLs are removed and verified empty
```

Existing credential, token, initial-password, and audit files are re-secured at startup. A file whose permissions cannot be enforced stops startup. If the auth directory itself cannot be secured, the runtime falls back to `data/auth2`, `data/auth3`, ... `data/auth9`; the first usable directory is used and the previous one is left in place. The fallback is reported on stderr, through `report_error`, and in the `/healthz` payload.

GUI provisioning:

```text
mode = required
desktop_auto_login = 1
process started by the GUI
no credentials file
→ random password generated
→ data/auth/credentials.json written
→ data/auth/initial-password.txt written with the plaintext password
```

Browser login uses the password from `initial-password.txt`. A password written with `--set-password` does not revoke existing sessions or API tokens; sessions live in process memory and clear on restart.

## 5. Sessions

### Login

```http
POST /auth/login
Content-Type: application/json

{"password": "..."}
```

Success:

```http
200 OK
Set-Cookie: ai_agent_session=<random>; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200; Secure
Cache-Control: no-store

{"ok": true, "csrf": "<token>"}
```

`Secure` is present when the request is HTTPS or `cookie_secure = true`. `Max-Age` is `session_hours × 3600`.

Failure:

```text
401 invalid_credentials   password mismatch
429 rate_limited          source locked; Retry-After is lock_seconds
503 setup_required        no credentials file
503 auth_unavailable      credentials file unreadable
```

The 401 response carries no `WWW-Authenticate` header.

### Session rules

```text
256-bit random session token
the server stores only the SHA-256 of the token
every successful login creates a new session and CSRF token
expiry after session_hours of inactivity (default 12 hours)
at most 128 live sessions; the entry with the earliest expiry is evicted
logout revokes the session immediately
expired sessions are pruned on access and on create
```

The cookie's `Max-Age` is fixed at login; the server-side expiry is refreshed by each authenticated request.

### Cookie

```text
HttpOnly
SameSite=Strict
Path=/
Max-Age = session_hours × 3600
Secure on HTTPS requests, and always when cookie_secure = true
```

`POST /auth/logout` requires an authenticated session and a valid CSRF token; it revokes the session and clears the cookie.

### Desktop bootstrap

The GUI launcher generates a one-time token and opens `/desktop-login#<token>` in its WebView. The page reads the token from the URL fragment, removes it from the address bar, and posts it to `/auth/desktop`.

```text
peer must be loopback
token must match and is consumed once
the shared login limiter applies with a desktop-specific key
success creates a normal session cookie and returns the CSRF token
```

The fragment is not sent in the HTTP request, so the token does not appear in request lines or logs.

## 6. Request guard

### Pipeline

```text
Handler
  → Host guard (allowed_hosts)
  → public route handlers (/login, /desktop-login, /healthz, /auth/status,
    /auth/login, /auth/desktop)
  → Authenticator (local bypass / provider / Bearer token / cookie session → AuthIdentity)
  → RoutePolicy (public path and required scope)
  → Authorizer (Principal + Policy → Allow / Deny)
  → CsrfGuard (unsafe method with a cookie session)
  → business route or plugin route
```

### Responsibilities

```text
Authenticator
  parses credentials and returns an AuthIdentity
  does not inspect paths or write HTTP responses

RoutePolicy
  answers whether a path is public and which scope it needs
  does not parse cookies or verify passwords

Authorizer
  decides allow or deny from a principal and a path
  performs no I/O

CsrfGuard
  compares the request token with the session token
  does not handle login or business logic

AuthRoutes
  handles /auth/login, /auth/logout, /auth/csrf, /auth/status, /auth/desktop
  does not handle business APIs

Handler
  maps Allow / Deny to 200 / 302 / 401 / 403 / 429
  does not verify passwords or store sessions
```

### Public routes

```text
GET  /login
GET  /desktop-login
GET  /healthz
GET  /auth/status
POST /auth/login
POST /auth/desktop
```

`/auth/csrf` is not public: it requires an authenticated cookie session and returns 401 otherwise.

### Protected routes

```text
GET  /
GET  /assets/*
GET  /favicon.ico
GET  /health
GET  /api/events/stream
GET  /api/chat/*
GET  /api/settings/*
GET  /api/subagents/*
GET  /api/update/*
GET  /api/media
GET  /workspace/*
POST /api/*
PUT  /api/*
DELETE /api/*
plugin routes
```

Every other path also requires authentication, including all plugin routes.

### Health endpoints

`/health` returns model configuration, tool counts, and the model list; it requires authentication.

`/healthz` is public and returns:

```json
{"ok": true, "service": "agent.web"}
```

After an auth directory fallback, the payload also carries `auth_fallback` and `auth_fallback_to`.

## 7. Unauthenticated and denied responses

API:

```http
401 Unauthorized

{"ok": false, "error": "unauthorized"}
```

No `WWW-Authenticate` header is sent.

Page requests outside `/api/`, `/auth/`, and `/assets/`:

```http
302 Location: /login?next=<percent-encoded path>
```

Static assets:

```text
401 application/json
```

Forbidden:

```http
403 Forbidden

{"ok": false, "error": "forbidden"}
```

CSRF failure:

```http
403 Forbidden

{"ok": false, "error": "csrf_failed"}
```

Rate limited:

```http
429 Too Many Requests
Retry-After: <lock_seconds>
```

Invalid Host:

```http
400 Bad Request

{"ok": false, "error": "invalid_host"}
```

`HEAD` and `OPTIONS` pass the guard and then return 405 with `Allow: GET, POST, PUT, DELETE`.

## 8. CSRF

Cookie sessions protect unsafe requests with a session-bound token:

```text
SameSite=Strict
X-CSRF-Token: <session csrf token>
```

Flow:

```text
successful login returns the CSRF token in the JSON body
GET /auth/csrf returns the token for the current cookie session
POST / PUT / PATCH / DELETE must send X-CSRF-Token
```

Rules:

```text
GET, HEAD, OPTIONS: no token required
Bearer token requests: no CSRF check
missing or mismatched token: 403 csrf_failed
comparison uses hmac.compare_digest
```

The guard does not check `Origin` or `Referer`.

### Frontend

The page installs one wrapper over `window.fetch`:

```text
sets credentials: same-origin
for POST / PUT / PATCH / DELETE, fetches /auth/csrf once and sets X-CSRF-Token
redirects to /login on a 401 response
```

Callers use `fetch` as usual; CSRF handling is not repeated per module.

## 9. SSE

`EventSource` cannot set an Authorization header, so browser SSE authenticates with the session cookie. Non-browser clients can send a Bearer token.

Rules:

```text
the handshake passes the same guard; an unauthenticated request receives 401
a token in the URL is never accepted
the kernel-format stream re-authenticates on each loop iteration and closes
  when the session is revoked, the session expires, or the token is revoked
the classic-format stream is authenticated at handshake
```

Startup order:

```text
GET /auth/status
  authenticated → open the event stream
  unauthenticated → redirect to /login
```

`/auth/status` answers 200 with `authenticated: false` for an unauthenticated request. The client does not infer HTTP status from `EventSource` error events.

## 10. Rate limiting and audit

### Login limiting

```text
key: client IP
max_failures failures (default 5) → locked for lock_seconds (default 300)
a successful login clears the counter
```

The check runs before password verification; a failed password increments the counter. A locked source receives 429 with `Retry-After: <lock_seconds>`.

Desktop bootstrap uses the same limiter with a separate per-IP key.

### Client address

```text
default: TCP peer address
X-Forwarded-For: first valid IP, read only when the peer is in trusted_proxies
X-Forwarded-Proto: read only from trusted_proxies
trusted_proxies accepts exact addresses and CIDR networks
```

### Audit log

`data/auth/auth.log`, one JSON object per line:

```json
{"ts": "2026-10-27T08:00:00+0800", "event": "login_failed", "level": "info", "remote_ip": "203.0.113.9", "reason": "invalid_credentials"}
```

Events: `login_success`, `login_failed`, `desktop_success`, `desktop_failed`, `csrf_failed`, `host_rejected`.

Fields: `ts`, `event`, `level`, `remote_ip`, `path`, `method`, `reason`.

Never written: password, Cookie, Authorization, plaintext token, request body.

An append failure goes through `report_error` and does not change the authentication result.

## 11. API tokens

For scripts, CI, and external systems:

```bash
agent-web --issue-token NAME --scope chat,read
agent-web --revoke-token NAME
```

`--scope` defaults to `read`.

Request:

```http
Authorization: Bearer <token>
```

Tokens are accepted only from the `Authorization` header; URL parameters and cookies are not token transports.

Storage: `data/auth/tokens.json`

Only these fields are stored:

```text
SHA-256 of the token
name
scopes
created_at
```

No last-used timestamp is stored. Tokens have the form `ai_<random>`.

Issue and revoke hold both an in-process thread lock and a cross-process lock file `tokens.json.lock`. A duplicate name is rejected; an unavailable lock blocks the write and the CLI exits non-zero.

### Scopes

```text
read   GET and HEAD: status, history, files, plugin assets
chat   unsafe requests under /api/chat/*, except admin endpoints
write  other unsafe requests outside admin paths
admin  settings, updates, plugin management, confirmations, command input
```

`admin` satisfies every scope.

Admin endpoints:

```text
/api/settings/*
/api/update/*
/api/plugin/*            except GET .../_asset/*
/api/chat/user-confirm
/api/chat/command-input
```

`GET /api/plugin/<name>/_asset/<path>` requires `read`. Bearer requests are exempt from CSRF.

## 12. TLS and reverse proxy

Plain HTTP on a public interface exposes passwords and session cookies.

```text
non-loopback bind
  → TLS certificate and key, or
  → --allow-insecure-public
  → otherwise exit code 2
```

TLS:

```bash
agent-web --host 0.0.0.0 --tls-cert cert.pem --tls-key key.pem
```

The server wraps its socket in TLS and forces `Secure` on session cookies. `--allow-insecure-public` permits HTTP on a non-loopback address; the process warns when the cookie is not forced secure.

Reverse proxy:

```ini
[auth]
mode = required
trusted_proxies = 127.0.0.1
```

```text
X-Forwarded-For and X-Forwarded-Proto are read only from a peer
  listed in trusted_proxies
when TLS terminates at the proxy, the proxy is in trusted_proxies so the
  forwarded scheme marks the cookie Secure
Host must match allowed_hosts
mode = auto behind a same-host proxy keeps the loopback bypass and authenticates nobody
```

`allowed_hosts` defaults to `127.0.0.1,localhost,::1`. A public or proxy hostname is added to this list; otherwise every request returns 400 `invalid_host`.

## 13. Configuration

```ini
[auth]
; auto / required / local
mode = auto

; session lifetime in hours
session_hours = 12

; login failure limiting
max_failures = 5
lock_seconds = 300

; reverse proxy and Host allowlist
trusted_proxies =
allowed_hosts = 127.0.0.1,localhost,::1
cookie_secure = auto

; optional external authentication provider module
; the module exposes build_provider(data_root, config) -> AuthProvider
provider_module =

; GUI one-time bootstrap login; browsers still authenticate
desktop_auto_login = 1
```

CLI:

```bash
agent-web --set-password
agent-web --issue-token NAME --scope chat,read
agent-web --revoke-token NAME
agent-web --host 127.0.0.1
agent-web --host 0.0.0.0 --tls-cert cert.pem --tls-key key.pem
agent-web --host 0.0.0.0 --allow-insecure-public
```

## 14. Architecture

HTTP authentication belongs to the shell layer. It is not part of core, capabilities, or mechanisms, and no auth state is registered in `AppContext`.

```text
agent/entry/web.py
  CLI flags and process start
  --set-password / --issue-token / --revoke-token call the auth public entry points
  no password, session, or guard logic

agent/shell/web/server.py
  binds the address, applies TLS, constructs AuthRuntime
  enforces startup policy (credentials, TLS, loopback-only mode)
  no password verification

agent/shell/web/auth/
  authentication primitives, policy, and enforcement
  no business routes

agent/shell/web/web_auth.py
  maps auth decisions to HTTP status codes and redirects
  enforces CSRF on Handler requests

agent/shell/web/web_routes.py
  calls the guard once per request method before dispatch
  does not read credentials.json or compare passwords
```

Prohibited:

```text
authentication in core
the session store in AppContext
CSRF checks spread across business routes
plugins deciding whether authentication applies
one guard owning passwords, rate limits, CSRF, and HTTP responses
auth configuration keys in core modules
```

### 14.1 Module responsibilities

```text
config.py          reads [auth]; defaults come from agent/config_schema.py
models.py          Principal, Session, AuthIdentity, AuthDecision, cookie name, scopes
password.py        scrypt hash and verify
credentials.py     credentials.json read/write; no HTTP
sessions.py        in-memory session create, lookup, revoke, expiry; no HTTP
tokens.py          token issue, verify, revoke; hashes, scopes, file lock
rate_limit.py      per-key failure counter and lockout; login and desktop only
csrf.py            CSRF requirement and constant-time token check
providers.py       AuthProvider protocol and module loading
policy.py          public paths, protected paths, required scopes
authenticator.py   headers and Cookie → AuthIdentity; no response
authorizer.py      Principal + policy → AuthDecision; no response
request.py         client IP, HTTPS detection, Host allowlist
security.py        DACL/POSIX permissions, verified atomic writes, log append
audit.py           auth.log JSON lines
bootstrap.py       one-time GUI bootstrap token
startup.py         whether the configured bind may start
runtime.py         composition root; wires the components
routes.py          login and desktop pages, /auth/* responses
```

Dependency constraints:

```text
policy does not depend on sessions or tokens
password does not depend on sessions or tokens
sessions and tokens do not depend on HTTP
tokens uses mechanisms.session_locking for the cross-process lock
config owns the [auth] keys
runtime resolves the auth data directory; security enforces its permissions
runtime wires the components and exposes no aggregate authenticate-and-respond method
```

### 14.2 Code locations

```text
agent/shell/web/auth/
  __init__.py
  models.py
  password.py
  credentials.py
  sessions.py
  tokens.py
  rate_limit.py
  csrf.py
  providers.py
  policy.py
  authenticator.py
  authorizer.py
  request.py
  security.py
  audit.py
  bootstrap.py
  startup.py
  runtime.py
  routes.py
```

The Handler uses the runtime's authenticator, authorizer, routes, configuration, audit, and cookie settings. It does not import the internals of `password.py`, `sessions.py`, or `tokens.py`.

## 15. Verification

```text
unauthenticated GET /                          → 302 /login
unauthenticated GET /api/*                     → 401
unauthenticated GET /healthz                   → 200
unauthenticated GET /auth/status               → 200, authenticated=false
unauthenticated SSE                            → 401
wrong password                                 → 401
repeated wrong password                        → 429
correct password                               → session cookie and CSRF token
missing CSRF on a cookie-session POST          → 403
valid CSRF                                     → 200
authenticated SSE                              → event stream
static assets                                  → 401
token with the required scope                  → 200
token with an insufficient scope               → 403
logout                                         → session revoked
bind 0.0.0.0 without a password                → startup failure
bind 0.0.0.0 without TLS                       → startup failure
spoofed X-Forwarded-For from an untrusted peer → ignored
expired session                                → 401
invalid Host                                   → 400
duplicate token name                           → rejected
unusable auth directory                        → data/auth2 fallback
```

## 16. Residual risks

### 16.1 Reverse proxy loopback bypass

`auto` disables authentication when the bind address and the peer address are both loopback. A reverse proxy on the same host connects from a loopback address, so an `auto` server behind a proxy accepts requests without authentication.

```text
required disables the loopback bypass for every bind address
startup does not inspect X-Forwarded-* to detect this configuration
```

### 16.2 Host header and DNS rebinding

The Host guard compares the Host header with `allowed_hosts` and returns 400 on a mismatch. Only exact hostnames are accepted; a port is ignored. DNS rebinding to a loopback address is blocked when the attacker cannot produce an allowed Host value.

`Origin` and `Referer` are not checked.

### 16.3 CSRF coverage and XSS

The server rejects cookie-session unsafe requests without a matching `X-CSRF-Token`. The login and desktop-login POST endpoints are public and unauthenticated; they rely on the password, the one-time desktop token, and rate limiting.

Same-origin XSS can read `/auth/csrf` and issue valid requests. The login page and the application UI use inline scripts; no Content Security Policy is sent.

### 16.4 SSE connection limits

SSE requires authentication at handshake. There is no per-IP or global connection limit. The kernel-format stream revalidates identity on each loop iteration; the classic-format stream validates only at handshake, so a revoked session can keep receiving events until that connection closes.

### 16.5 Authenticated file and command scope

On Windows, the default file roots are the local drive roots; other platforms default to the project root. Authentication decides who enters, not which paths are reachable.

A `read` token can read files under the configured roots. A `write` token can create background tasks, which run arbitrary commands as the service user. A `chat` token can start turns but cannot approve write confirmations, because `/api/chat/user-confirm` and `/api/chat/command-input` require `admin`.

### 16.6 Session sharing across ports

The cookie name and `Path=/` are fixed. Browsers send the same cookie to every port on the host, so two instances on different ports share and overwrite each other's session cookie.

### 16.7 Login page headers and redirects

The login page embeds inline CSS and JavaScript and is served without a Content Security Policy, anti-framing headers, or other security headers.

The `next` value is clamped in page script to a path beginning with a single `/`; absolute URLs and `//` fall back to `/`. The server does not validate `next`. Logout clears the cookie but sends no `Clear-Site-Data`.

### 16.8 Session expiry and in-flight work

Logout and session expiry revoke the session and the kernel-format SSE stream. Agent turns, running tool calls, and background tasks continue. A write confirmation issued after logout needs a new authenticated admin session.

### 16.9 In-memory sessions and multiple processes

Sessions and CSRF tokens live in process memory. A second process or worker has a separate session table; a restart drops every session and requires a new login. Passwords and API tokens are file-backed and shared.

### 16.10 Audit log exposure

`data/auth/auth.log` records time, source IP, event, and request path or method. It is protected by the same permissions as the credential files. An append failure is reported through `report_error`; the authentication result is unchanged.

### 16.11 Health endpoint information

`/healthz` is public and returns the service name. After an auth directory fallback, it also exposes the fallback flag and the directory name (`auth2` through `auth9`). It does not return model or tool data; those remain on the authenticated `/health` endpoint.

### 16.12 Response caching

Auth endpoints and the login page send `Cache-Control: no-store`. Business responses do not set `no-store` globally, and logout does not send `Clear-Site-Data`, so browser back/forward caches can retain rendered pages.

### 16.13 Password hashing cost

Each login verification computes scrypt with `n=16384`, `r=8`, `p=1`. There is no cap on concurrent login attempts; the failure limiter locks per IP after `max_failures`, but concurrent attempts before the lock each consume CPU. Request bodies above 4 MB are ignored by the body reader.

### 16.14 Credential storage and backups

`data/auth/` holds password credentials, API tokens, the initial password file, and the audit log. Release and update packages exclude `data/`; the installer treats `data/` and `updates/` as runtime directories and leaves them out of its file backup.

### 16.15 HTTP method coverage

GET, POST, PUT, DELETE, HEAD, and OPTIONS pass the guard; HEAD and OPTIONS then return 405. Other method names receive the standard-library 501 response without reaching the guard. Absolute-form request targets and duplicate `Content-Length` headers are not normalized by the guard itself.

### 16.16 Password rotation

`--set-password` writes a new scrypt hash. It does not revoke sessions held by a running server or revoke API tokens; existing sessions remain valid until they expire or the process restarts. Tokens are revoked one name at a time with `--revoke-token`. There is no online reset flow.

## 17. Design decisions

```text
default mode auto; loopback requests bypass authentication
non-loopback bind requires credentials
no credentials or no TLS on a public bind refuses startup
passwords hashed with scrypt
cookie sessions with SameSite=Strict and a session-bound CSRF token
SSE authenticated at handshake; the kernel-format stream revalidated on every loop iteration
scripts and external systems use Bearer tokens with scopes
every plugin route passes the Handler guard
/health requires authentication; /healthz is public
Host allowlist on every handled request
reverse proxies use mode = required
```
