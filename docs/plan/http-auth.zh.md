[English](http-auth.md) | **中文**

# HTTP 鉴权

Web 壳在 Handler 入口、路由分发之前校验每个已处理请求。内置路由与插件路由经过同一闸门，插件不能自行跳过。

## 1. 范围

鉴权面向单操作者，不做多租户。未认证的网络客户端不能：

```text
发送消息
执行工具
读取文件
修改设置
触发更新
建立 SSE 连接
```

服务默认绑定 `127.0.0.1`。`--host` 可绑定其他地址；非回环绑定要求凭据，并且在未显式放行时要求 TLS。

## 2. 威胁模型

处理：

```text
公网任意调用
CSRF
暴力破解
会话窃取
Token 泄露到 URL 或日志
插件路由绕过鉴权
静态资源或 SSE 绕过鉴权
反向代理把公网请求伪装成本机请求
```

不处理：

```text
已经取得本机管理员权限的攻击者
已经控制浏览器或操作系统的攻击者
键盘记录器
被授权的恶意操作者
```

## 3. 鉴权模式

```ini
[auth]
mode = auto
```

```text
auto      回环绑定下回环请求免登录；其他请求需要鉴权
required  每个请求都需要鉴权
local     只接受回环绑定
```

### auto

回环旁路同时满足两个条件时生效：

```text
服务绑定回环地址
请求对端地址为回环地址
```

这类请求按本地操作者处理，拥有全部 scope。来自其他对端的请求需要会话 Cookie 或 Bearer Token。

### required

回环旁路关闭，绑定回环地址时也一样。每个请求都需要会话 Cookie 或 Bearer Token。反向代理、公网映射与远程访问使用此模式。

### local

只接受回环绑定地址。非回环绑定以退出码 2 结束。绑定回环地址时，回环请求与 `auto` 一样免鉴权。

### 启动检查

```text
非回环绑定，无密码且无已加载 provider
  → 退出码 2
  → 提示 agent-web --set-password

非回环绑定，无 TLS 且未指定 --allow-insecure-public
  → 退出码 2
  → 提示 TLS 或反向代理配置

mode = local 且绑定非回环地址
  → 退出码 2
```

公网绑定不会在无鉴权的情况下启动。已配置的 provider 加载失败时同样阻止公网绑定，即使已有密码。

## 4. 密码凭据

创建或替换密码：

```bash
agent-web --set-password
```

输入规则：

```text
交互式输入，不回显
输入两次并比对
至少 12 位
不接受命令行参数传入密码
明文不写入 config.ini
```

存储位置：`data/auth/credentials.json`

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

哈希只使用标准库：

```text
hashlib.scrypt
hmac.compare_digest
secrets.token_bytes
```

不新增密码库依赖。

文件权限：

```text
Windows：DACL 仅限当前用户、SYSTEM、Administrators 与 OWNER RIGHTS；
         关闭继承；出现额外允许 ACE 即校验失败
POSIX：  目录 0700，文件 0600；所有者为当前用户；
         组与其他权限位为 0
macOS：  清除并校验扩展 ACL 为空
```

已有凭据、Token、初始密码与审计文件在启动时重新收紧权限。权限无法收紧的文件会阻止启动。鉴权目录本身无法收紧时，运行时回退到 `data/auth2`、`data/auth3`……`data/auth9`；使用第一个可用目录，原目录保留。回退通过 stderr、`report_error` 与 `/healthz` 载荷上报。

GUI 自动配置：

```text
mode = required
desktop_auto_login = 1
进程由 GUI 启动
没有凭据文件
→ 生成随机密码
→ 写入 data/auth/credentials.json
→ 写入 data/auth/initial-password.txt，内容为明文密码
```

浏览器登录使用 `initial-password.txt` 中的密码。`--set-password` 写入新密码后不会撤销已有会话或 API Token；会话保存在进程内存，重启后清空。

## 5. 会话

### 登录

```http
POST /auth/login
Content-Type: application/json

{"password": "..."}
```

成功：

```http
200 OK
Set-Cookie: ai_agent_session=<random>; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200; Secure
Cache-Control: no-store

{"ok": true, "csrf": "<token>"}
```

请求为 HTTPS 或 `cookie_secure = true` 时包含 `Secure`。`Max-Age` 为 `session_hours × 3600`。

失败：

```text
401 invalid_credentials   密码不匹配
429 rate_limited          来源被锁定；Retry-After 为 lock_seconds
503 setup_required        没有凭据文件
503 auth_unavailable      凭据文件不可读
```

401 响应不带 `WWW-Authenticate` 头。

### 会话规则

```text
256 位随机会话 Token
服务端只保存 Token 的 SHA-256
每次成功登录都创建新会话与 CSRF Token
闲置 session_hours 后过期（默认 12 小时）
最多 128 个活动会话；超出时淘汰最早过期的条目
logout 立即撤销会话
过期会话在访问与创建时清理
```

Cookie 的 `Max-Age` 在登录时固定；服务端过期时间由每次已认证请求刷新。

### Cookie

```text
HttpOnly
SameSite=Strict
Path=/
Max-Age = session_hours × 3600
HTTPS 请求带 Secure；cookie_secure = true 时始终带 Secure
```

`POST /auth/logout` 需要已认证会话与有效 CSRF Token；撤销会话并清除 Cookie。

### 桌面引导

GUI 启动器生成一次性 Token，在 WebView 中打开 `/desktop-login#<token>`。页面从 URL fragment 读取 Token，从地址栏移除，再提交到 `/auth/desktop`。

```text
对端必须为回环地址
Token 必须匹配且只消费一次
使用共享登录限流器，按桌面场景单独计数
成功后创建普通会话 Cookie 并返回 CSRF Token
```

Fragment 不随 HTTP 请求发送，Token 不出现在请求行或日志中。

## 6. 请求守卫

### 管线

```text
Handler
  → Host 守卫（allowed_hosts）
  → 公开路由处理（/login、/desktop-login、/healthz、/auth/status、
    /auth/login、/auth/desktop）
  → Authenticator（本地旁路 / provider / Bearer Token / Cookie 会话 → AuthIdentity）
  → RoutePolicy（公开路径与所需 scope）
  → Authorizer（Principal + Policy → Allow / Deny）
  → CsrfGuard（Cookie 会话的非安全方法）
  → 业务路由或插件路由
```

### 职责边界

```text
Authenticator
  解析凭据并返回 AuthIdentity
  不检查路径，不写 HTTP 响应

RoutePolicy
  回答路径是否公开、需要哪个 scope
  不解析 Cookie，不校验密码

Authorizer
  根据 Principal 与路径给出允许或拒绝
  不做 I/O

CsrfGuard
  比对请求 Token 与会话 Token
  不处理登录与业务逻辑

AuthRoutes
  处理 /auth/login、/auth/logout、/auth/csrf、/auth/status、/auth/desktop
  不处理业务 API

Handler
  把 Allow / Deny 映射为 200 / 302 / 401 / 403 / 429
  不校验密码，不保存会话
```

### 公开路由

```text
GET  /login
GET  /desktop-login
GET  /healthz
GET  /auth/status
POST /auth/login
POST /auth/desktop
```

`/auth/csrf` 不在公开列表：需要已认证的 Cookie 会话，否则返回 401。

### 受保护路由

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
插件路由
```

其余所有路径同样需要认证，包括全部插件路由。

### 健康检查端点

`/health` 返回模型配置、工具数量与模型列表，需要认证。

`/healthz` 公开，返回：

```json
{"ok": true, "service": "agent.web"}
```

鉴权目录发生回退后，载荷同时带 `auth_fallback` 与 `auth_fallback_to`。

## 7. 未认证与拒绝响应

API：

```http
401 Unauthorized

{"ok": false, "error": "unauthorized"}
```

不发送 `WWW-Authenticate` 头。

`/api/`、`/auth/`、`/assets/` 之外的页面请求：

```http
302 Location: /login?next=<percent-encoded path>
```

静态资源：

```text
401 application/json
```

权限不足：

```http
403 Forbidden

{"ok": false, "error": "forbidden"}
```

CSRF 失败：

```http
403 Forbidden

{"ok": false, "error": "csrf_failed"}
```

限流：

```http
429 Too Many Requests
Retry-After: <lock_seconds>
```

Host 非法：

```http
400 Bad Request

{"ok": false, "error": "invalid_host"}
```

`HEAD` 与 `OPTIONS` 通过守卫后返回 405，`Allow: GET, POST, PUT, DELETE`。

## 8. CSRF

Cookie 会话用与会话绑定的 Token 保护非安全请求：

```text
SameSite=Strict
X-CSRF-Token: <session csrf token>
```

流程：

```text
登录成功的 JSON 响应返回 CSRF Token
GET /auth/csrf 返回当前 Cookie 会话的 Token
POST / PUT / PATCH / DELETE 必须发送 X-CSRF-Token
```

规则：

```text
GET、HEAD、OPTIONS：不要求 Token
Bearer Token 请求：不校验 CSRF
缺失或不匹配的 Token：403 csrf_failed
比较使用 hmac.compare_digest
```

守卫不检查 `Origin` 或 `Referer`。

### 前端

页面在 `window.fetch` 上安装一个包装器：

```text
设置 credentials: same-origin
对 POST / PUT / PATCH / DELETE，获取一次 /auth/csrf 并设置 X-CSRF-Token
收到 401 时跳转 /login
```

调用方照常使用 `fetch`；CSRF 处理不在各模块重复。

## 9. SSE

`EventSource` 不能设置 Authorization 头，浏览器 SSE 使用会话 Cookie 认证。非浏览器客户端可以发送 Bearer Token。

规则：

```text
握手经过同一守卫；未认证请求收到 401
不接受 URL 中的 Token
内核格式的事件流在每次循环重新认证，并在会话撤销、会话过期或
  Token 撤销后关闭连接
经典格式的事件流在握手时认证
```

启动顺序：

```text
GET /auth/status
  已认证 → 建立事件流
  未认证 → 跳转 /login
```

`/auth/status` 对未认证请求返回 200 与 `authenticated: false`。客户端不从 `EventSource` 错误事件推断 HTTP 状态。

## 10. 限流与审计

### 登录限流

```text
key：客户端 IP
失败 max_failures 次（默认 5）→ 锁定 lock_seconds（默认 300）
登录成功清零
```

检查在密码校验之前执行；密码错误累加计数。被锁定的来源收到 429 与 `Retry-After: <lock_seconds>`。

桌面引导使用同一限流器，按客户端 IP 使用独立 key。

### 客户端地址

```text
默认：TCP 对端地址
X-Forwarded-For：第一个合法 IP，仅当对端在 trusted_proxies 中时读取
X-Forwarded-Proto：仅从 trusted_proxies 读取
trusted_proxies 接受精确地址与 CIDR 网段
```

### 审计日志

`data/auth/auth.log`，每行一个 JSON 对象：

```json
{"ts": "2026-10-27T08:00:00+0800", "event": "login_failed", "level": "info", "remote_ip": "203.0.113.9", "reason": "invalid_credentials"}
```

事件：`login_success`、`login_failed`、`desktop_success`、`desktop_failed`、`csrf_failed`、`host_rejected`。

字段：`ts`、`event`、`level`、`remote_ip`、`path`、`method`、`reason`。

不写入：密码、Cookie、Authorization、Token 明文、请求体。

追加失败经 `report_error` 上报，不改变鉴权结果。

## 11. API Token

用于脚本、CI 与外部系统：

```bash
agent-web --issue-token NAME --scope chat,read
agent-web --revoke-token NAME
```

`--scope` 默认 `read`。

请求：

```http
Authorization: Bearer <token>
```

Token 只从 `Authorization` 头接受；URL 参数与 Cookie 不是 Token 传递方式。

存储位置：`data/auth/tokens.json`

只保存这些字段：

```text
Token 的 SHA-256
名称
scope
created_at
```

不保存最后使用时间。Token 形式为 `ai_<random>`。

签发与撤销同时持有进程内线程锁和跨进程锁文件 `tokens.json.lock`。同名 Token 被拒绝；锁不可用时拒绝写入，CLI 以非零码退出。

### Scope

```text
read   GET 与 HEAD：状态、历史、文件、插件资产
chat   /api/chat/* 下的非安全请求，admin 端点除外
write  其他非安全请求，admin 路径除外
admin  设置、更新、插件管理、确认、命令输入
```

`admin` 满足全部 scope。

admin 端点：

```text
/api/settings/*
/api/update/*
/api/plugin/*            除外 GET .../_asset/*
/api/chat/user-confirm
/api/chat/command-input
```

`GET /api/plugin/<name>/_asset/<path>` 需要 `read`。Bearer 请求免除 CSRF。

## 12. TLS 与反向代理

公网接口上的纯 HTTP 会暴露密码与会话 Cookie。

```text
非回环绑定
  → TLS 证书与私钥，或
  → --allow-insecure-public
  → 否则退出码 2
```

TLS：

```bash
agent-web --host 0.0.0.0 --tls-cert cert.pem --tls-key key.pem
```

服务器用 TLS 包装套接字，并强制会话 Cookie 带 `Secure`。`--allow-insecure-public` 允许非回环地址使用 HTTP；未强制 Secure 时进程给出警告。

反向代理：

```ini
[auth]
mode = required
trusted_proxies = 127.0.0.1
```

```text
X-Forwarded-For 与 X-Forwarded-Proto 只从 trusted_proxies 中的对端读取
代理终止 TLS 时，代理位于 trusted_proxies 中，转发协议才使 Cookie 带 Secure
Host 必须匹配 allowed_hosts
同机代理前的 mode = auto 保留回环旁路，不认证任何请求
```

`allowed_hosts` 默认 `127.0.0.1,localhost,::1`。公网或代理域名要加入该列表；否则每个请求返回 400 `invalid_host`。

## 13. 配置

```ini
[auth]
; auto / required / local
mode = auto

; 会话有效期，小时
session_hours = 12

; 登录失败限流
max_failures = 5
lock_seconds = 300

; 反向代理与 Host 白名单
trusted_proxies =
allowed_hosts = 127.0.0.1,localhost,::1
cookie_secure = auto

; 可选外部认证 provider 模块
; 模块提供 build_provider(data_root, config) -> AuthProvider
provider_module =

; GUI 一次性引导登录；浏览器仍需登录
desktop_auto_login = 1
```

CLI：

```bash
agent-web --set-password
agent-web --issue-token NAME --scope chat,read
agent-web --revoke-token NAME
agent-web --host 127.0.0.1
agent-web --host 0.0.0.0 --tls-cert cert.pem --tls-key key.pem
agent-web --host 0.0.0.0 --allow-insecure-public
```

## 14. 架构归属

HTTP 鉴权属于壳层，不属于 core、capabilities 或 mechanisms；鉴权状态不登记进 `AppContext`。

```text
agent/entry/web.py
  CLI 参数与进程启动
  --set-password / --issue-token / --revoke-token 调用 auth 的公开入口
  不实现密码、会话或守卫逻辑

agent/shell/web/server.py
  绑定地址、应用 TLS、构造 AuthRuntime
  执行启动策略（凭据、TLS、仅回环模式）
  不做密码校验

agent/shell/web/auth/
  鉴权基础能力、策略与执行
  不承载业务路由

agent/shell/web/web_auth.py
  把鉴权结果映射为 HTTP 状态码与重定向
  在 Handler 请求上执行 CSRF 校验

agent/shell/web/web_routes.py
  每个请求方法在分发前调用一次守卫
  不直接读取 credentials.json，不直接比较密码
```

禁止：

```text
把鉴权放进 core
把会话存储放进 AppContext
把 CSRF 校验散落在各业务路由
让插件自行决定是否鉴权
让单个守卫同时负责密码、限流、CSRF 与 HTTP 响应
把 auth 配置键写进 core 模块
```

### 14.1 模块职责

```text
config.py         读取 [auth]；默认值来自 agent/config_schema.py
models.py         Principal、Session、AuthIdentity、AuthDecision、Cookie 名、scope
password.py       scrypt 哈希与校验
credentials.py    credentials.json 读写；不接触 HTTP
sessions.py       进程内会话创建、查询、撤销、过期；不接触 HTTP
tokens.py         Token 签发、校验、撤销；哈希、scope、文件锁
rate_limit.py     按 key 的失败计数与锁定；只被登录与桌面引导使用
csrf.py           CSRF 要求与会话 Token 的常量时间比较
providers.py      AuthProvider 协议与模块加载
policy.py         公开路径、受保护路径、所需 scope
authenticator.py  请求头与 Cookie → AuthIdentity；不写响应
authorizer.py     Principal + policy → AuthDecision；不写响应
request.py        客户端 IP、HTTPS 判定、Host 白名单
security.py       DACL/POSIX 权限、校验后原子写入、日志追加
audit.py          auth.log JSON 行
bootstrap.py      GUI 一次性引导 Token
startup.py        当前绑定是否允许启动
runtime.py        组合根；装配各组件
routes.py         登录页、桌面页与 /auth/* 响应
```

依赖约束：

```text
policy 不依赖 sessions 与 tokens
password 不依赖 sessions 与 tokens
sessions 与 tokens 不依赖 HTTP
tokens 通过 mechanisms.session_locking 使用跨进程锁
config 拥有 [auth] 配置键
runtime 解析鉴权数据目录；security 执行其权限约束
runtime 只装配组件，不提供 authenticate-and-respond 聚合方法
```

### 14.2 代码落点

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

Handler 使用运行时的 authenticator、authorizer、routes、配置、审计与 Cookie 设置，不导入 `password.py`、`sessions.py`、`tokens.py` 的内部实现。

## 15. 验证

```text
未认证 GET /                         → 302 /login
未认证 GET /api/*                    → 401
未认证 GET /healthz                  → 200
未认证 GET /auth/status              → 200，authenticated=false
未认证 SSE                           → 401
错误密码                             → 401
连续错误密码                         → 429
正确密码                             → 会话 Cookie 与 CSRF Token
Cookie 会话 POST 缺少 CSRF           → 403
CSRF 正确                            → 200
已认证 SSE                           → 事件流
静态资源                             → 401
scope 匹配的 Token                   → 200
scope 不足的 Token                   → 403
logout                               → 会话失效
绑定 0.0.0.0 且无密码                → 启动失败
绑定 0.0.0.0 且无 TLS                → 启动失败
不可信对端伪造 X-Forwarded-For       → 忽略
会话过期                             → 401
Host 非法                            → 400
Token 重名                           → 拒绝
鉴权目录不可用                       → 回退 data/auth2
```

## 16. 残余风险

### 16.1 反向代理回环绕过

绑定地址与对端地址都是回环地址时，`auto` 关闭鉴权。同机的反向代理从回环地址连接，因此代理后的 `auto` 服务会无鉴权接受请求。

```text
required 对所有绑定地址关闭回环旁路
启动过程不检查 X-Forwarded-* 来识别这种配置
```

### 16.2 Host 头与 DNS Rebinding

Host 守卫把 Host 头与 `allowed_hosts` 比对，不匹配时返回 400。只接受精确主机名；端口被忽略。攻击者无法给出允许的 Host 值时，解析到回环地址的 DNS Rebinding 被阻断。

`Origin` 与 `Referer` 不参与校验。

### 16.3 CSRF 覆盖与 XSS

服务端拒绝缺少匹配 `X-CSRF-Token` 的 Cookie 会话非安全请求。登录与桌面引导的 POST 端点公开且未认证；它们依赖密码、一次性桌面 Token 与限流。

同源 XSS 可以读取 `/auth/csrf` 并发出合法请求。登录页与应用界面使用内联脚本；响应不发送 Content Security Policy。

### 16.4 SSE 连接数

SSE 在握手时要求认证。没有按 IP 或全局的连接数上限。内核格式的事件流在每次循环重新校验身份；经典格式的事件流只在握手时校验，被撤销的会话在连接关闭前仍能收到事件。

### 16.5 认证后的文件与命令范围

Windows 下默认文件根为本机各盘根；其他平台默认为项目根。鉴权决定谁能进入，不决定哪些路径可达。

`read` Token 可以读取配置根下的文件。`write` Token 可以创建后台任务，以服务用户身份执行任意命令。`chat` Token 可以发起回合，但不能批准写盘确认，因为 `/api/chat/user-confirm` 与 `/api/chat/command-input` 需要 `admin`。

### 16.6 跨端口会话共享

Cookie 名与 `Path=/` 固定。浏览器会把同一 Cookie 发往主机的所有端口，同机不同端口的两个实例会共享并互相覆盖会话 Cookie。

### 16.7 登录页头部与重定向

登录页内联 CSS 与 JavaScript，响应不带 Content Security Policy、防嵌入头或其他安全头。

`next` 由页面脚本限制为以单个 `/` 开头的路径；绝对 URL 与 `//` 回退到 `/`。服务端不校验 `next`。logout 清除 Cookie，但不发送 `Clear-Site-Data`。

### 16.8 会话过期与在途任务

logout 与会话过期撤销会话及内核格式的 SSE 事件流。Agent 回合、正在执行的工具调用与后台任务继续运行。logout 之后发出的写盘确认需要新的已认证 admin 会话。

### 16.9 内存会话与多进程

会话与 CSRF Token 保存在进程内存。第二个进程或 worker 拥有独立会话表；重启清空全部会话并要求重新登录。密码与 API Token 保存在文件，跨进程共享。

### 16.10 审计日志暴露

`data/auth/auth.log` 记录时间、来源 IP、事件与请求路径或方法，受与凭据文件相同的权限保护。追加失败经 `report_error` 上报，鉴权结果不变。

### 16.11 健康检查信息

`/healthz` 公开并返回服务名。鉴权目录回退后，它还暴露回退标志与目录名（`auth2` 至 `auth9`）。它不返回模型或工具数据；这些信息保留在需要认证的 `/health`。

### 16.12 响应缓存

鉴权端点与登录页发送 `Cache-Control: no-store`。业务响应没有全局设置 `no-store`，logout 也不发送 `Clear-Site-Data`，浏览器前进/后退缓存可以保留已渲染页面。

### 16.13 密码哈希成本

每次登录校验计算 scrypt，`n=16384`、`r=8`、`p=1`。登录尝试没有并发上限；失败限流在 `max_failures` 次后按 IP 锁定，但锁定前的并发尝试各自消耗 CPU。超过 4 MB 的请求体被请求体读取器忽略。

### 16.14 凭据存储与备份

`data/auth/` 保存密码凭据、API Token、初始密码文件与审计日志。发布包与更新包排除 `data/`；安装器把 `data/` 与 `updates/` 视为运行态目录，不纳入其文件备份。

### 16.15 HTTP 方法覆盖

GET、POST、PUT、DELETE、HEAD、OPTIONS 经过守卫；HEAD 与 OPTIONS 随后返回 405。其他方法名收到标准库的 501 响应，不经过守卫。绝对 URI 请求行与重复 `Content-Length` 头不由守卫本身规范化。

### 16.16 密码轮换

`--set-password` 写入新的 scrypt 哈希。它不撤销运行中服务器持有的会话，也不撤销 API Token；已有会话在过期或进程重启前继续有效。Token 通过 `--revoke-token` 按名称逐个撤销。没有在线重置流程。

## 17. 设计决策

```text
默认 mode auto；回环请求免鉴权
非回环绑定要求凭据
公网绑定无凭据或无 TLS 时拒绝启动
密码用 scrypt 哈希
Cookie 会话 + SameSite=Strict + 会话绑定的 CSRF Token
SSE 在握手时认证；内核格式事件流每次循环复检
脚本与外部系统使用带 scope 的 Bearer Token
所有插件路由经过 Handler 守卫
/health 需要认证；/healthz 公开
每个已处理请求校验 Host 白名单
反向代理使用 mode = required
```
