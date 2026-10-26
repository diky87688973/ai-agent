# HTTP 鉴权方案

## 1. 现状

Web 服务默认绑定 `127.0.0.1`，但允许通过 `--host` 绑定公网地址：

```text
agent-web --host 0.0.0.0
```

当前 `agent/shell/web/web_routes.py` 的 `do_GET` / `do_POST` / `do_PUT` / `do_DELETE` 直接进入路由分发，没有统一鉴权。

暴露后的可调用面包括：

```text
/api/chat/*
/api/settings/*
/api/update/*
/api/events/stream
/api/attachments/*
/api/media/*
插件注册的 HTTP 路由
```

其中 `/health` 还会返回模型、工具数量、模型列表等运行信息，不应公开。

目标不是做多租户，而是：

```text
未认证的网络客户端
  → 不能发送消息
  → 不能执行工具
  → 不能读文件
  → 不能改设置
  → 不能触发更新
  → 不能建立 SSE
```

## 2. 威胁模型

需要防：

```text
公网任意调用
CSRF
暴力破解
会话窃取
Token 泄露到 URL / 日志
插件路由绕过鉴权
静态资源或 SSE 绕过鉴权
反向代理把公网请求伪装成本机请求
```

不防：

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

支持：

```text
auto      回环地址免登录；非回环地址强制登录
required  任何地址都必须登录
local     只允许回环地址，非回环启动失败
```

### auto

```text
host 是 127.0.0.1 / ::1
  → 本机免登录

host 是 0.0.0.0 / :: / 非回环地址
  → 必须已设置密码
  → 否则启动失败
```

`auto` 只根据绑定地址判断，不根据请求来源判断。

### required

```text
任何地址都必须登录
```

反向代理、公网映射、远程访问使用此模式。

### local

```text
只允许回环地址
host 非回环 → 启动失败
```

### 启动检查

```text
非回环 host + 无密码
  → 退出码 2
  → 输出 agent-web --set-password

非回环 host + 无 TLS + 未显式允许
  → 退出码 2
  → 输出 TLS 或反向代理配置说明
```

不允许静默启动一个无鉴权的公网服务。

## 4. 密码凭据

首次设置：

```bash
agent-web --set-password
```

要求：

```text
交互式输入，不回显
输入两次
最少 12 位
不通过命令行参数传密码
不把明文写入 config.ini
```

存储位置：

```text
data/auth/credentials.json
```

结构：

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

使用 Python 标准库：

```text
hashlib.scrypt
hmac.compare_digest
secrets.token_bytes
```

不新增密码库依赖。

文件权限：

```text
Windows：仅当前用户可读写
Linux / macOS：0600
```

## 5. 会话

登录：

```http
POST /auth/login
Content-Type: application/json

{"password": "..."}
```

成功：

```http
200 OK
Set-Cookie: ai_agent_session=<random>; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200
Cache-Control: no-store
```

失败：

```http
401 Unauthorized
{"ok": false, "error": "invalid_credentials"}
```

会话规则：

```text
256-bit 随机 session id
服务端只保存 session id 的 hash
登录成功重新生成 session
默认 12 小时过期
支持 logout 立即撤销
支持过期清理
```

Cookie：

```text
HttpOnly
SameSite=Strict
Path=/
Secure：HTTPS 时强制
```

公网或反向代理场景必须开启 Secure。

## 6. 统一请求守卫

不能在每个业务路由里分别判断。必须在 Handler 入口拦截，但不能把所有职责塞进一个 `AuthGuard`。

```text
Handler（HTTP 协议）
  → AuthRoutes（仅 /auth/*）
  → Authenticator（会话 / Bearer token → Principal）
  → RoutePolicy（公开路径 / 所需 scope）
  → Authorizer（Principal + Policy → Allow / Deny）
  → CsrfGuard（Cookie 会话的写请求）
  → 原业务路由或插件路由
```

职责边界：

```text
Authenticator
  只解析凭据并返回 Principal
  不判断路径，不写 HTTP 响应

RoutePolicy
  只回答：这条路径是否公开、需要什么 scope
  不解析 Cookie，不验证密码

Authorizer
  只做授权判断
  不读文件，不写响应

CsrfGuard
  只校验 CSRF
  不处理登录，不处理业务

AuthRoutes
  只处理 /auth/login、/auth/logout、/auth/csrf、/auth/status
  不处理业务 API

Handler
  负责把 Allow / Deny 映射成 200 / 401 / 403 / 302
  不实现密码校验或会话存储
```

公开路由只允许：

```text
GET  /login
GET  /assets/login/*
POST /auth/login
GET  /auth/status
GET  /healthz
```

`/auth/csrf` 不在公开列表：它必须绑定已认证会话，未认证请求返回 401。

其余全部需要认证：

```text
GET  /
GET  /assets/*（登录资源除外）
GET  /favicon.ico
GET  /health
GET  /api/events/stream
GET  /api/chat/*
GET  /api/settings/*
GET  /api/subagents/*
GET  /api/update/*
GET  /api/media/*
POST /api/*
PUT  /api/*
DELETE /api/*
插件注册的全部路由
```

`/health` 含有运行信息，必须认证。
新增 `/healthz` 只返回：

```json
{"ok": true}
```

供负载均衡或探针使用。

所有插件路由也必须经过同一 Guard，不能由插件自行决定是否鉴权。

## 7. 未认证响应

API：

```http
401 Unauthorized
WWW-Authenticate: Bearer
{"ok": false, "error": "unauthorized"}
```

页面：

```http
302 Location: /login?next=<安全路径>
```

静态资源：

```http
401 或 403
```

权限不足：

```http
403 Forbidden
{"ok": false, "error": "forbidden"}
```

限流：

```http
429 Too Many Requests
Retry-After: N
```

## 8. CSRF

Cookie 会话必须启用 CSRF 防护：

```text
SameSite=Strict
+ Origin / Referer 校验
+ X-CSRF-Token
```

流程：

```text
GET /auth/csrf
  → 返回当前会话绑定的 token

POST / PUT / PATCH / DELETE
  → 必须带 X-CSRF-Token
```

规则：

```text
GET / HEAD / OPTIONS 不要求
Bearer token 请求不要求
跨站 Origin 直接拒绝
缺失或错误 CSRF token → 403
```

前端所有写请求必须走同一个 `apiFetch()` 包装：

```text
自动附加 X-CSRF-Token
收到 401 时跳转登录
收到 403 时显示可读错误
```

禁止在多个业务模块里各自手写 CSRF 逻辑。

## 9. SSE

`EventSource` 不能设置 Authorization header。

规则：

```text
SSE 使用会话 Cookie 或 Bearer Token 鉴权
SSE 不接受 URL 中的 token
握手前检查身份，事件循环按 principal 重新认证
会话/Toke 撤销或过期后关闭连接
```

前端启动顺序：

```text
GET /auth/status
  → 已认证：启动 SSE
  → 未认证：跳转 /login
```

不要依赖 EventSource 的错误事件判断 HTTP 状态。

## 10. 限流与锁定

登录失败：

```text
同一 IP：
  5 次失败 → 锁定 5 分钟
同一账户：
  连续失败计数
  成功后清零
```

必须：

```text
使用 constant-time 比较
延迟随失败次数增加
不泄露“账号不存在”与“密码错误”的区别
限制并发登录尝试
限制请求体大小
```

反向代理场景：

```text
默认不信任 X-Forwarded-For
配置 trusted_proxies 后才读取
否则使用 TCP 对端地址
```

鉴权日志：

```text
data/auth/auth.log
```

只记录：

```text
时间
来源 IP
结果
失败原因类别
```

禁止记录：

```text
密码
Cookie
Authorization
Token 明文
```

## 11. API Token

用于脚本、CI、外部系统：

```bash
agent-web --issue-token NAME --scope chat,read
agent-web --revoke-token NAME
```

请求：

```http
Authorization: Bearer <token>
```

存储：

```text
data/auth/tokens.json
```

只存：

```text
token 的 SHA-256
名称
scope
创建时间
最后使用时间
```

scope：

```text
read    只读状态、历史、文件
chat    发消息、停止任务
write   写盘、确认、提交
admin   设置、更新、插件管理、令牌管理
read    插件主题与图标资产（GET /api/plugin/*/_asset/*）
```

高风险接口只允许 admin：

```text
/api/settings/*
/api/update/*
/api/chat/user-confirm
/api/chat/command-input
```

## 12. TLS 与反向代理

纯 HTTP 公网不能只靠密码，否则密码和会话可被窃听。

建议：

```text
非回环 host
  → 必须 TLS
  → 或部署在可信反向代理后面
  → 否则拒绝启动
```

支持：

```text
--tls-cert
--tls-key
```

或：

```ini
[auth]
mode = required
cookie_secure = true
trusted_proxies = 127.0.0.1
```

反向代理注意：

```text
不能因为请求来自 127.0.0.1 就免鉴权
否则代理成为绕过入口
```

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

; 反向代理
trusted_proxies =
cookie_secure = auto

; 外部认证方式模块，可选
; 模块必须提供 build_provider(data_root, config) -> AuthProvider
provider_module =
```

CLI：

```bash
agent-web --set-password
agent-web --issue-token NAME --scope chat,read
agent-web --revoke-token NAME
agent-web --host 127.0.0.1
agent-web --host 0.0.0.0
```

## 14. 架构归属

HTTP 鉴权属于壳层，不属于 core，也不属于 capabilities/mechanisms。

```text
agent/entry/web.py
  只做 CLI 参数与进程启动
  --set-password / --issue-token 调用 auth 的公开入口
  不实现密码、会话、守卫

agent/shell/web/server.py
  负责绑定地址、TLS、构造 AuthRuntime
  负责把 auth 依赖注入 Handler
  不实现密码校验

agent/shell/web/auth/
  只依赖 core.error_report 等基础能力
  不导入 entry、app、plugins
  不承载业务路由

agent/shell/web/web_routes.py
  只调用 Authenticator / RoutePolicy / Authorizer / CsrfGuard
  不直接读 credentials.json
  不直接比较密码
```

禁止：

```text
把鉴权放进 core
把 session store 放进 AppContext
把 CSRF 校验散落在每个业务 route
让插件自己决定是否鉴权
让单个守卫模块同时负责密码、限流、CSRF、HTTP 响应
把 auth 配置键写进 core 模块
```

## 14.1 模块职责

```text
agent/shell/web/auth/
  config.py         读取 [auth] 配置；唯一配置归属
  models.py         Principal / Session / Token / Decision 数据形状
  password.py       仅 scrypt 哈希和校验
  credentials.py    凭据文件读写；不接触 HTTP
  sessions.py       会话创建、校验、撤销、过期；不接触 HTTP
  tokens.py         API token 哈希、scope、撤销；不接触 HTTP
  rate_limit.py     登录失败计数与锁定；只被登录流程使用
  csrf.py           CSRF token 生成与校验；绑定 session
  providers.py      AuthProvider 协议与模块加载；不决定路由策略
  policy.py         公开路径、受保护路径、所需 scope；唯一路由策略
  authenticator.py  从请求头/Cookie 构造 Principal；不写响应
  authorizer.py     Principal + Policy → Decision；不写响应
  runtime.py        composition root：组装上述依赖，不承载业务规则
  routes.py         /auth/* 的 HTTP 处理
  page.py           登录页 HTML/CSS/JS
```

依赖方向：

```text
routes/page
  → authorizer/csrf
  → authenticator
  → sessions/tokens/password
  → credentials/config
  → 标准库与 core.error_report

policy 不依赖 sessions/tokens
password 不依赖 sessions/tokens
sessions 不依赖 HTTP
tokens 不依赖 HTTP
```

`AuthRuntime` 是组合根，不是业务上帝对象。它只负责把依赖装好，不提供 `authenticate_and_authorize_and_write_response()` 这类聚合方法。

## 14.2 代码落点

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
  policy.py
  authenticator.py
  authorizer.py
  runtime.py
  routes.py
  page.py
```

`Handler` 只依赖：

```text
auth_runtime.authenticator
auth_runtime.policy
auth_runtime.authorizer
auth_runtime.csrf
auth_runtime.routes
```

不依赖 `password.py`、`sessions.py`、`tokens.py` 的内部实现。

## 15. 实施顺序

```text
1. auth/config.py + password.py + credentials.py
2. sessions.py + tokens.py
3. policy.py + authenticator.py + authorizer.py
4. csrf.py + rate_limit.py
5. runtime.py 组合根
6. routes.py + /auth/login、/auth/status、/auth/csrf、/auth/logout
7. Handler 统一拦截全部请求方法
8. SSE 鉴权
9. 登录页与前端 401/403 处理
10. 统一 apiFetch 附加 CSRF
11. 公网启动检查与 TLS
12. 测试、文档、发布
```

## 16. 测试清单

```text
未登录 GET /                 → 302 /login
未登录 GET /api/*            → 401
未登录 SSE                   → 401
错误密码                     → 401
连续错误密码                 → 429
正确密码                     → 会话 Cookie
CSRF 缺失                    → 403
CSRF 正确                    → 200
SSE 已登录                   → 事件流
静态登录资源                 → 公开
其他静态资源                 → 需要认证
API token 正确 scope         → 200
API token 越权               → 403
Logout                       → 会话失效
绑定 0.0.0.0 无密码          → 启动失败
绑定 0.0.0.0 无 TLS          → 启动失败
伪装 X-Forwarded-For         → 不绕过限流
会话过期                     → 401
```

## 17. 残余风险

### 17.1 反向代理回环绕过

`auto` 模式依据绑定地址判断：

```text
反向代理 → 127.0.0.1:8765
```

服务端看到的是本机连接，若配置错误仍可能免登录。

必须：

```text
反向代理场景显式 mode = required
文档明确禁止在 auto 模式下挂公网代理
启动时检测到 X-Forwarded-* 且 mode=auto 时拒绝或告警
```

这是必须写入部署检查的最高优先级风险。

### 17.2 DNS Rebinding 与 Host 头

攻击页面可以把域名解析到 `127.0.0.1`，再向本机服务发请求。

必须：

```text
校验 Host 头
只接受配置的 host/port
拒绝未知 Host
Origin 只作为辅助，不能代替 Host 校验
```

### 17.3 CSRF 覆盖不完整

现有前端有大量直接 `fetch()` 调用。

风险：

```text
只给 /api/chat/send 加 CSRF
漏掉 /api/settings
漏掉 /api/update/apply
漏掉插件路由
```

必须统一 `apiFetch()`，并对所有写方法做服务端强制校验，不能依赖前端自觉。

### 17.4 SSE 资源耗尽

SSE 是长连接，未认证连接可能耗尽线程和内存。

必须：

```text
认证后才建立 SSE
限制单 IP 并发连接数
限制总会话数
会话过期后关闭流
心跳识别死连接
```

### 17.5 认证后的本机全盘访问

当前 `--fs-root` 默认覆盖本机各盘根。

鉴权只解决“谁能进来”，不解决“进来后能碰哪些路径”。

高风险：

```text
token scope 为 write
仍可写用户可写的任意文件
```

应在后续把文件根限制为显式配置，或至少将全盘访问限定为 admin session，不对普通 API token 开放。

### 17.6 会话共享与多端口

多个 Web 实例共享同一主机时：

```text
Cookie 名相同
Host 相同
端口不同
```

浏览器会把同一 Cookie 发给不同端口，造成会话串用或认证失败。

应：

```text
Cookie 名带实例标识
或在文档中声明单实例
```

### 17.7 登录页 XSS / 开放重定向

`next` 参数必须只允许站内相对路径：

```text
拒绝 http://evil
拒绝 //evil
拒绝 javascript:
```

登录页必须使用 CSP，禁止外部脚本。

### 17.8 会话过期后的在途任务

用户登出或会话过期时，已经运行的 Agent 回合可能继续执行工具。

必须明确：

```text
登出是否停止当前任务
会话过期是否终止运行中的写盘/命令
```

建议：

```text
登出不强制终止后台任务，但立即撤销会话和 SSE
高风险写盘确认必须重新认证
```

### 17.9 多进程与内存会话

内存会话只适用于单进程单实例。

若未来使用多 worker：

```text
会话存入共享存储
或使用签名 Cookie + 撤销列表
```

当前单进程可以接受。

### 17.10 认证日志本身的泄露

`auth.log` 可能包含 IP 和访问时间，但不得包含：

```text
密码
Cookie
Bearer token
完整请求体
```

日志写入失败不能吞掉登录错误，应走 `report_error`。

### 17.11 健康检查泄露

`/health` 目前返回模型、工具数量、模型列表等信息。

必须：

```text
/healthz 公开且只返回 ok
/health 认证后返回完整信息
```

### 17.12 静态资源与缓存

登录页资源可以公开，但：

```text
其他静态资源必须鉴权
API 响应禁止缓存
登出后禁止 back/forward cache 继续展示敏感页面
```

建议：

```text
Cache-Control: no-store
Clear-Site-Data: "cache", "cookies", "storage" 在登出时
```

### 17.13 认证限流自身被 DoS

scrypt 每次登录计算成本较高，攻击者可并发打满 CPU。

必须：

```text
限制登录并发
限制请求体大小
限制每 IP 尝试频率
限制全局失败队列长度
```

### 17.14 备份与认证凭据

`data/auth/` 属于运行态敏感目录：

```text
不进入发布包
不进入源码
不进入普通数据备份
不得通过更新包覆盖
```

### 17.15 HTTP 方法与解析边界

必须覆盖：

```text
HEAD / OPTIONS
绝对 URI 请求行
重复 Content-Length
异常 Host
路径中的 ../ 与编码变体
```

不能只给 `GET`、`POST` 加守卫。
`BaseHTTPRequestHandler` 对未实现的方法可能返回 501，但 501 本身也必须经过统一鉴权边界，不能让未知方法成为探测面。

### 17.16 XSS 会绕过 CSRF

CSRF token 能阻止其他站点伪造请求，但阻止不了同源 XSS。

必须：

```text
CSP 禁止外部脚本
不把会话 token 放进 localStorage
不把 CSRF token 写进 URL
登录页和设置页不使用未受控的 innerHTML
```

现有页面大量内联脚本，接入严格 CSP 前需要 nonce/hash 方案，否则会破坏界面。
这是实施阶段必须单独验证的兼容性风险。

### 17.17 登录 CSRF 与缺失 Origin

登录请求本身也可能被跨站发起。
浏览器对跨站 POST 通常会带 `Origin`，但非浏览器客户端可能不带。

规则应明确：

```text
浏览器请求：Origin 必须匹配当前 Host
无 Origin 的请求：只允许 Bearer token 或明确的本机 CLI 调用
Cookie 会话的 POST：必须有 Origin 或 CSRF token
```

不能让“没有 Origin”自动等同于可信。

### 17.18 密码重置与令牌轮换

必须提供本地恢复路径：

```text
agent-web --set-password
  → 覆盖密码
  → 撤销现有会话
  → 可选撤销全部 API token
```

禁止在线“忘记密码”流程。
能执行 CLI 的人已经具备本机权限，不需要再增加远程重置面。

## 18. 推荐决策

```text
默认 auto
回环免登录
非回环强制登录
无密码拒绝公网启动
密码 scrypt
Cookie 会话 + SameSite=Strict + CSRF
SSE 走 Cookie 或 Bearer，逐事件复检
外部脚本走 Bearer Token + scope
所有插件路由统一经过 Handler 的鉴权管线：Authenticator → RoutePolicy → Authorizer → CsrfGuard
/health 认证，/healthz 公开
Host 校验 + Origin 校验
非回环无 TLS 拒绝启动
反向代理必须显式 required
```

实现状态：鉴权内核、CSRF、SSE 复检、Token scope、Host/代理与 Windows DACL 已落地；Linux/macOS ACL 分支待在对应平台实机验证。
