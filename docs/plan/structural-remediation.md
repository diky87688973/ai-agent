# 结构整改方案

## 目标

把当前按文件堆积的实现拆成按职责归属的模块，恢复以下约束：

```text
层间单向依赖
同层模块不依赖具体兄弟实现
单一职责
高内聚
无兼容再导出
无临时旁路
无职责重叠
```

本方案只调整结构、依赖和测试边界，不改变产品行为。

## 当前主要问题

| 编号 | 位置 | 问题 |
|---|---|---|
| P0-1 | `agent/mechanisms/model_provider.py` | 协议、假模型、OpenAI 实现、SSE、超时、消息转换、工具 schema、错误映射混在一个文件 |
| P0-2 | `agent/mechanisms/anthropic_provider.py` | 具体 Anthropic 实现直接依赖 `model_provider.py` 中的 OpenAI 实现与私有辅助 |
| P0-3 | `agent/mechanisms/provider_router.py` | 路由依赖具体 OpenAI 模块，而不是只依赖协议与错误类型 |
| P1-1 | `agent/mechanisms/context_pipeline.py` | 数据模型、token 裁剪、轮次、布局、来源、装配、压缩区间集中在一个文件 |
| P1-2 | `agent/mechanisms/context_compactor.py` | 压缩策略依赖上下文管线的具体内部函数 |
| P1-3 | `agent/shell/session_runner.py` | 运行循环、队列、目标、取消、心跳、提示词、恢复拼接集中在一个类 |
| P1-4 | `agent/shell/classic_adapter/inbound.py` | 历史、布局、状态、标题、附件、会话查询混在一个文件 |
| P1-5 | `agent/shell/classic_adapter/outbound.py` | 所有内核事件翻译集中在一个类 |
| P1-6 | `agent/shell/web_routes.py` | HTTP 服务、静态资源、经典页面、SSE、全部 API 混在一个处理器 |
| P2-1 | `agent/capabilities/builtin/task_tools.py` | 六类任务工具与确认协议混在一个文件 |
| P2-2 | `agent/shell/fspaths.py`、`agent/shell/sse.py`、`agent/mechanisms/context_pipeline.py` | 依赖旧导入路径的兼容再导出 |
| P2-3 | `agent/app.py` | 装配根同时承担模型目录、上下文预算、会话创建、工具执行 |

## 目标结构

```text
agent/mechanisms/
  providers/
    base.py          Provider 协议、错误类型
    sse.py           SSE 行解析、流总超时
    openai.py        OpenAI 兼容实现
    anthropic.py     Anthropic Messages 实现
    echo.py          Echo 假模型
    missing.py       Missing 占位
  context/
    rounds.py        Round、ContextChunk
    tokens.py        token 估算与裁剪
    layout.py        分段布局
    sources.py       ContextSources、PluginSegments
    contract.py      压缩器所需的窄接口
    pipeline.py      ContextPipeline 装配
  compaction/
    compactor.py     ContextCompactor
    summarizer.py    摘要生成与摘要请求

agent/shell/
  session/
    runner.py        会话运行器
    queue.py         队列协调
    goal.py          目标续跑
    prompt.py        系统提示词与运行态尾部
    resume.py        外部结果恢复
  classic_adapter/
    history.py       历史回放
    layout.py        上下文布局
    state.py         会话级状态
    sessions.py      会话列表与标题
    inbound.py       入站门面
    outbound.py      出站门面
  web/
    server.py        HTTP 服务与分发
    static.py        静态资源
    classic.py       经典页面与 SSE
    api.py           JSON API

agent/capabilities/tasks/
  run_type.py
  todo.py
  confirm.py
  sleep.py
  goal.py
```

## 依赖规则

### 层间

```text
entry → shell → capabilities → mechanisms → core
```

反向导入禁止。

### mechanisms 内

```text
providers/openai.py      → providers/base.py, providers/sse.py
providers/anthropic.py   → providers/base.py, providers/sse.py
providers/echo.py        → providers/base.py
providers/missing.py     → providers/base.py

provider_router.py       → providers/base.py
provider_registry.py     → providers/*.py

context/pipeline.py      → context/rounds.py, context/tokens.py,
                           context/layout.py, context/sources.py
compaction/compactor.py  → context/contract.py
```

禁止：

```text
anthropic.py → openai.py
anthropic.py → model_provider.py
provider_router.py → openai.py
context_compactor.py → context_pipeline.py 的内部实现
任何 provider 文件互相导入私有符号
```

### shell 内

```text
session/runner.py → session/queue.py, session/goal.py,
                    session/prompt.py, session/resume.py
classic_adapter/inbound.py → history.py, layout.py, state.py, sessions.py
web/server.py → web/static.py, web/classic.py, web/api.py
```

`session/runner.py` 不再自己实现队列、目标、提示词和恢复拼接。

## 整改工作包

| 编号 | 工作包 | 主要文件 | 验收 |
|---|---|---|---|
| SR-01 | Provider 基础层 | `providers/base.py`、`providers/sse.py` | 协议与错误不再放在 OpenAI 文件；SSE 与超时独立可测 |
| SR-02 | OpenAI 实现独立 | `providers/openai.py` | 只保留 OpenAI 请求、响应、错误映射；不承载协议与其他 provider |
| SR-03 | Anthropic 解耦 | `providers/anthropic.py` | 只依赖 `base.py`、`sse.py` 与 core 契约；不导入 OpenAI 模块 |
| SR-04 | Router / Registry 收口 | `provider_router.py`、`provider_registry.py` | router 只依赖 base；registry 是唯一具体实现装配点 |
| SR-05 | 上下文管线拆分 | `context/rounds.py`、`tokens.py`、`layout.py`、`sources.py`、`pipeline.py` | 每个文件只有一个变更轴；pipeline 只做装配 |
| SR-06 | 压缩器接口化 | `context/contract.py`、`compaction/compactor.py` | compactor 不导入 pipeline 内部函数；通过窄接口取视图与区间 |
| SR-07 | SessionRunner 拆分 | `session/runner.py`、`queue.py`、`goal.py`、`prompt.py`、`resume.py` | runner 只编排，不直接持有队列/目标/提示词实现 |
| SR-08 | 经典适配层拆分 | `classic_adapter/history.py`、`layout.py`、`state.py`、`sessions.py` | inbound 只做门面；历史、布局、状态、会话各自独立 |
| SR-09 | Web 路由拆分 | `web/server.py`、`static.py`、`classic.py`、`api.py` | HTTP 分发、静态资源、经典 SSE、JSON API 分离 |
| SR-10 | 任务工具拆分 | `capabilities/tasks/*.py` | 每个工具一个文件；共享异常与参数校验单独放置 |
| SR-11 | 兼容层清除 | `context_pipeline.py`、`fspaths.py`、`sse.py` | 删除旧导入再导出；调用方直接导入新归属 |
| SR-12 | 结构门禁 | `scripts/check_imports.py`、`scripts/check_architecture_hygiene.py` | 新增同层具体依赖、私有跨模块导入、兼容再导出的失败检查 |

## 实施顺序

### 第一阶段：Provider

```text
SR-01 → SR-02 → SR-03 → SR-04
```

先建立 base 与 sse，再移动 OpenAI，最后改 Anthropic 与 router。

### 第二阶段：上下文

```text
SR-05 → SR-06
```

先拆数据模型、布局、来源与装配，再给压缩器建立窄接口。

### 第三阶段：壳层

```text
SR-07 → SR-08 → SR-09
```

先拆运行器，再拆经典适配层，最后拆 HTTP 路由。

### 第四阶段：工具与门禁

```text
SR-10 → SR-11 → SR-12
```

最后清兼容层并把结构约束写进门禁。

## 每个工作包的实施步骤

```text
1. 先补 characterization 测试，锁住当前外部行为
2. 新建目标模块，只搬运代码，不改行为
3. 修改调用方导入，删除旧入口
4. 运行该模块相关单测与静态检查
5. 运行全量 CI
6. 单独提交，不与其他工作包混合
```

禁止：

```text
先搬代码再补测试
保留旧模块做兼容转发
同时改行为与结构
一个提交覆盖多个工作包
```

## 测试要求

### Provider

```text
OpenAI / Anthropic 各自的 SSE 解析
工具调用分片归并
thinking 块签名回传
HTTP 错误映射
流总超时
close 失败告警
consumer 提前关闭
```

### 上下文

```text
轮边界
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

```text
禁止同层具体 provider 互导
禁止从兄弟模块导入私有符号
禁止兼容再导出
禁止单文件承担多个职责域
文件与函数复杂度不得新增未登记债务
```

## 兼容与回滚

不保留兼容层。

每个工作包单独提交，出问题时只回滚该提交。

不引入临时开关、双写、双入口或转发层。

## 完成标准

```text
providers 下每个文件只包含一个 provider 或一个基础职责
Anthropic 不导入 OpenAI
router 不导入具体 provider
compactor 不导入 pipeline 内部实现
session runner 只做编排
inbound/outbound/web routes 不再承担多个职责域
无兼容再导出
新增结构门禁通过
全量 CI 通过
文档与目录登记一致
```

## 风险与处理

| 风险 | 处理 |
|---|---|
| 拆 provider 改变流式行为 | 先锁定 SSE、tool_call、thinking、error、timeout 测试 |
| 拆上下文改变压缩前缀 | 使用现有装配快照与缓存前缀测试 |
| 拆运行器改变取消/续跑时序 | 先补并发、取消、队列、恢复用例 |
| 拆壳层改变 SSE 帧顺序 | 使用经典适配层事件序列测试 |
| 大范围移动导致审查困难 | 一个工作包一个提交，禁止混合行为改动 |
| 门禁误伤合法同层依赖 | 使用显式允许表，不为通过而放宽规则 |

## 责任边界

```text
providers：模型协议与厂商适配
context：上下文数据模型、布局、来源与装配
compaction：压缩策略
session：回合运行与队列/目标/恢复
classic_adapter：事件与历史适配
web：HTTP 与静态传输
capabilities/tasks：任务工具能力
app / entry：只做装配与入口
```
