[English](structural-remediation.md) | **中文**

# 结构整改

## 目标

代码按职责归属组织，不在单个文件里堆积多个关注点。结构保持以下约束：

```text
层间单向依赖
同层模块不依赖兄弟模块的私有符号
单一职责
高内聚
无兼容再导出
无临时旁路
无职责重叠
```

范围只有结构、依赖与测试边界；产品行为不变。

## 模块布局

```text
agent/mechanisms/
  providers/
    base.py            Provider 协议、错误类型
    sse.py             SSE 行解析、流总超时
    debug.py           共享调试开关
    tool_schema.py     工具 schema 规范化
    openai.py          兼容适配
    anthropic.py       原生 Messages 适配
    echo.py            Echo 假模型
    missing.py         未配置模型时的占位
  provider_router.py   按模型路由
  provider_registry.py 网关 Provider 装配
  context/
    rounds.py          Round、ContextChunk、轮次与工具链边界
    tokens.py          token 估算与推理裁剪
    layout.py          分段布局与压缩区间
    sources.py         ContextSources、PluginSegments
    constants.py       分段标签
    contract.py        压缩器依赖的窄接口
    pipeline.py        上下文装配
  compaction/
    compactor.py       ContextCompactor 与摘要生成

agent/shell/
  session/
    runner.py          回合运行器
    queue.py           队列领取、释放与重投
    goal.py            目标与自主续跑
    prompt.py          系统提示词与运行态尾部
    resume.py          外部结果恢复
    heartbeat.py       运行态心跳
  classic_adapter/
    history.py         历史折叠
    layout.py          上下文布局
    state.py           会话级状态
    sessions.py        会话列表与标题
    contract.py        经典事件常量
    inbound.py         入站门面
    outbound.py        出站门面
    outbound_tools.py  工具事件族
    outbound_turns.py  回合与模型事件族
  web/
    server.py          HTTP 服务装配
    web_routes.py      路由分发
    web_static.py      静态资源
    web_classic.py     经典页面与 SSE
    web_plugin.py      插件路由
    web_api.py         JSON API 与壳层运行态

agent/capabilities/tasks/
  run_type.py
  todo.py
  confirm.py
  goal.py
  common.py

agent/app.py           装配根，不属于任何层
agent/entry/          进程入口
```

## 依赖规则

### 层间

```text
entry → shell → capabilities → mechanisms → core
```

禁止反向导入。`agent/app.py` 是装配根，不属于任何层；下层不得在运行期导入装配根，`entry` 可以导入。

### mechanisms 内

```text
providers/openai.py      → providers/base.py, providers/sse.py,
                            providers/debug.py, providers/tool_schema.py
providers/anthropic.py   → providers/base.py, providers/sse.py,
                            providers/debug.py, providers/tool_schema.py
providers/echo.py        → providers/base.py
providers/missing.py     → providers/base.py

provider_router.py       → providers/base.py
provider_registry.py     → providers/openai.py, providers/anthropic.py,
                            providers/base.py

context/pipeline.py      → context/rounds.py, context/tokens.py,
                            context/layout.py, context/sources.py,
                            context/contract.py, context/constants.py
compaction/compactor.py  → context/contract.py
```

禁止：

```text
具体 Provider 导入另一个具体 Provider
provider_router.py 导入具体 Provider
compactor.py 导入 context 内部实现（pipeline、layout、rounds、sources、tokens）
```

### shell 内

```text
session/runner.py → session/queue.py, session/goal.py,
                    session/prompt.py, session/resume.py,
                    session/heartbeat.py
classic_adapter/inbound.py → history.py, layout.py, state.py,
                             sessions.py, contract.py
classic_adapter/outbound.py → outbound_tools.py, outbound_turns.py, contract.py
web/server.py → web_routes.py, web_static.py, web_api.py
web_routes.py → web_static.py, web_classic.py, web_plugin.py, web_api.py
```

`session/runner.py` 只做编排，不实现队列、目标、提示词、恢复和心跳。

## 模块职责

| 区域 | 模块 | 规则 |
|---|---|---|
| Provider 基础 | `providers/base.py`、`providers/sse.py`、`providers/debug.py`、`providers/tool_schema.py` | 协议与错误类型独立于具体适配；SSE 与超时独立可测；调试开关和 schema 规范化由网关适配器共用 |
| 兼容适配 | `providers/openai.py` | 只负责兼容协议的请求、响应与错误映射 |
| 原生 Messages 适配 | `providers/anthropic.py` | 只负责 Messages 线格式；只依赖中性 Provider 模块与 core 契约 |
| 路由与装配 | `provider_router.py`、`provider_registry.py` | 在 Provider 包内，路由只依赖 `providers/base.py`；注册表是网关 Provider 的唯一装配点 |
| 上下文模型 | `context/rounds.py`、`tokens.py`、`layout.py`、`sources.py`、`constants.py` | 每个文件只有一个变更轴 |
| 上下文装配 | `context/pipeline.py`、`context/contract.py` | 管线只做装配；契约是压缩器看到的窄接口 |
| 压缩 | `compaction/compactor.py` | 触发条件、覆盖前缀与摘要集成；不导入上下文内部实现 |
| 会话运行器 | `session/runner.py` | 只做编排 |
| 会话支撑 | `session/queue.py`、`goal.py`、`prompt.py`、`resume.py`、`heartbeat.py` | 每个文件一个关注点 |
| 经典适配 | `classic_adapter/inbound.py`、`outbound.py` 及子模块 | 门面只做组合与形状转换；历史、布局、状态、会话列表与事件族各自独立 |
| Web | `web/server.py`、`web_routes.py`、`web_static.py`、`web_classic.py`、`web_plugin.py`、`web_api.py` | 分发、传输、经典页面、插件端点与 JSON 业务分离 |
| 任务工具 | `capabilities/tasks/*.py` | 每个工具一个文件；共享异常与参数校验在 `common.py` |
| 装配与入口 | `agent/app.py`、`agent/entry/` | 只做装配与入口 |

## 测试

下列测试锁定各职责边界；结构变更不得改变这些行为。

### Provider

```text
兼容与原生适配分别测试 SSE 解析
工具调用分片归并为一次调用
thinking 块回传签名
HTTP 错误映射为面向用户的提示
流总超时生效
关闭失败有告警
消费者提前关闭时释放响应
```

### 上下文

```text
轮次边界
工具链完整
分段 token 统计
摘要覆盖
压缩区间
插件段合并
缓存前缀稳定
```

### 壳层

```text
运行循环
取消
队列领取与完成
目标续跑
恢复拼接
历史回放
上下文布局
SSE 帧顺序
```

### 结构门禁

结构门禁是 `scripts/check_imports.py`、`scripts/check_architecture_hygiene.py` 与 `scripts/check_complexity.py`。

```text
层间方向与装配根反向依赖
具体 Provider 导入另一个具体 Provider
压缩器导入上下文内部实现
跨层私有导入；同层私有导入不超预算
文件与函数复杂度阈值
```

## 变更规则

```text
结构变更只改归属与导入
行为改动不混入结构变更
不保留兼容再导出、转发模块或第二份实现
不引入临时开关、双写、双入口或转发层
合法同层依赖使用显式允许表，不放宽规则换取通过
```

## 验收

```text
providers 下每个文件只承担一个 Provider 或一项基础职责
原生 Messages 适配不导入兼容适配
路由不导入具体 Provider
压缩器不导入上下文内部实现
会话运行器只做编排
入站、出站与 Web 路由不承担多个职责域
无兼容再导出
结构门禁通过
文档与目录布局一致
全量 CI 通过
```

## 责任边界

```text
providers：模型协议与网关适配
context：上下文数据模型、token、布局、来源与装配
compaction：压缩策略与摘要集成
session：回合运行与队列、目标、提示词、恢复、心跳
classic_adapter：事件与历史适配
web：HTTP 与静态传输
capabilities/tasks：任务工具能力
app / entry：只做装配与入口
```
