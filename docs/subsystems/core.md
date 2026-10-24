# 内核

`agent/core/` 是 L0 层，不依赖任何其它层。它提供四样东西：数据契约、模块抽象、链执行器、宿主循环。

## 数据契约

| 文件 | 内容 |
|---|---|
| `event_name.py` | 25 个事件名常量。纯字符串，零依赖 |
| `events.py` | `Event` 数据类 + `make_event()`。一件事实的形状：类型 + 载荷 |
| `outcome.py` | `Outcome`：模块执行结果的唯一形状 |
| `model_call.py` | `StreamDelta`：模型流帧 |
| `tool_call.py` | `ToolCallRequest` / `ToolResult` / `GateDecision` / `ToolPipeline` |
| `ports.py` | `Ports` / `ModelPort` / `ToolPort` / `LogicalRequest` |

跨层只传这些对象，不传裸 dict。

## 控制信号

```python
class Outcome:
    status: str    # ok / next / halt / suspend / stopped
    reason: str
```

| 状态 | 含义 |
|---|---|
| `ok` | 本趟结束，不要求续行 |
| `next` | 本趟结束，**要求再跑一趟** |
| `halt` | 立刻停止整条链 |
| `suspend` | 挂起，等待外部事件唤醒 |
| `stopped` | 被取消信号终止 |

`Outcome` **只带控制信号，不带数据**（`reason` 是终态说明，不是载荷）。正文、用量、进度全部经 `ports.emit()` 发出。这个约束让模块之间没有共享可变状态。

## 模块抽象

```python
class ModuleBase:
    # 生成器契约：yield 事实，return 控制信号
    def execute(self, ports: Ports) -> Iterator[Event]: ...
```

行为面只有这一个方法。模块拿到的是 `Ports`，看不到上下文对象，也看不到别的模块。

五个具体模块在 `agent/core/modules/` 包：

| 模块 | 做什么 | 产出的事件 |
|---|---|---|
| `InputModule` | 把本轮新用户输入认领成事实 | `input_started` / `input_claimed` / `input_ended` |
| `QueuedInputModule` | 把待发送队列中标记插入的消息收进上下文 | `input_claimed` |
| `CompressModule` | 拼入前预算检查，超阈值压缩 | `compress_started` / `context_compacted` / `compress_ended` |
| `ModelModule` | 发请求、消费流、聚合工具调用 | `llm_started` / `assistant_delta` / `reasoning_delta` / `llm_done` / `llm_failed` / `llm_ended` |
| `ToolModule` | 执行工具、回灌结果 | `tool_started` / `tool_progress` / `tool_done` / `tool_failed` / `tool_canceled` / `tool_suspended` / `tool_ended` |

`build_default_chain()` 按 `输入 → 待发送队列插入 → 压缩 → 模型 → 工具` 的顺序组装。

### 各模块的判定依据

**`InputModule`**：有输入就发 `input_claimed` 并返回 `ok`；**无输入时不发 `input_claimed`**，只发终态 `input_ended`。后者是硬要求——接口确认触发的恢复轮没有用户发言，此时凭空发一条空的 `input_claimed` 会让消息序列变成 `…assistant(tool_calls) → user("") → tool`，模型接口直接拒绝。

**`QueuedInputModule`**：位置固定在压缩之前。插入消息会变成新的用户轮次，压缩得看得见它们，否则"刚插入消息就按旧预算压缩"会把新消息挤掉。每次最多消费一条插入请求。

**`CompressModule`**：把循环里的三处预算检查收拢成一个模块。从不要求续行——压缩是准备动作。压缩器缺省或出错一律放行：压缩是增强项，绝不阻断回合。

**`ModelModule`**：只看事实末端决定跑不跑。末端是新用户输入或未消费的工具结果 → 跑；末端已是模型自己的消息 → 不跑。

**`ToolModule`**：本链的收尾模块。找到最新模型消息里要求了但尚无结果的调用并执行；需要外部输入时发 `tool_suspended` 并返回 `Outcome.suspend(...)`（交回控制权，不阻塞）；执行过调用就返回 `next`。

## 链执行器

`chain.py` 回答"一趟怎么跑"：

```python
run_chain_iter(modules, ports) -> Iterator[PassResult]
run_chain(modules, ports)      -> PassResult
step(module, ports)            -> Outcome
```

`PassResult` 记录这一趟里每个模块的 `Outcome`。`run_chain` 在遇到 `halt` 时立即中断，不再跑后续模块。

## 宿主循环

`host.py` 回答"跑到什么时候停"，并划定回合边界。

```python
class Host:
    def run(...) -> TurnResult
```

退出条件（三条同时满足）：

1. 没有待回灌的工具结果；
2. 待发送队列没有新输入；
3. 没有任何模块要求续行（`Outcome.next`）。

有安全阀 `MAX_PASSES_DEFAULT = 64`：一个回合最多跑这么多趟，防止续行信号形成死循环。

`TurnResult` 汇总一个回合的结果：结束原因（`done` / `halted` / `suspended` / `stopped` / `max_passes` / `abandoned`）、跑过的趟数与终态说明。事实本身在 `SessionLog` 里，不在它身上。

## 引擎外观

`engine.py` 的 `Engine` 把模块链包成壳层要的两面：

- **开始回合**：投递输入、启动宿主循环；
- **事件流**：把内核事件以迭代器形式交出去。

`App.session(cid, system_prompt, cancel)` 每次构建一个新的 `Engine`，会话之间不共享回合状态。

## 会话作用域

`session_scope.py` 解决"工具在深层调用里怎么知道自己在哪个会话"。

```python
set_session_scope(cid) / reset_session_scope() / current_session_id()
set_tool_turn_context(ctx) / reset_tool_turn_context() / current_context()
set_progress_reporter(fn) / emit_progress(payload)
```

用 contextvar 实现，每会话一线程。工具与管道钩子经 `current_session_id()` 取会话 id，再向 `SessionContexts` 解析会话上下文。这是会话隔离的执行手段。

## 视觉嵌图

`image_embed.py` 处理"附件图片怎么进请求体"，属于"消息派生"的一段：把事实折叠成请求的那一方负责这件事。

- `shrink_image()` / `shrink_path()`：本地按长边缩放，压 base64 预算（长边上限 `EMBED_MAX_SIDE = 800`）；
- `build_embed_parts()`：拼成 Compatible 的 `image_url` 内容块；
- `strip_old_images()`：只留最近几轮用户发言里的图，并在这些轮内设总量上限（`keep_turns` / `max_images`，默认 1 轮 / 8 张，来自 `[context]` 的 `image_turns` / `image_max`）。超量的从**最老的那一轮**开始砍，所以最近一轮优先保住；
- `placeholder_text()`：图片被剥离后留下的占位文本。

被剥掉的图只从**发给模型的这一份**里消失：事实流里的 base64 一个字节都不动，历史回显与重新提问都还能拿到原图。

## 上下文容器

`context.py` 有两个类：

| 类 | 作用 |
|---|---|
| `AppContext` | 进程级服务登记表：`register(name, svc)` / `get(name)` / 注销句柄。未注册的 name 由 `get` 抛 `KeyError`，存在性用 `has(name)` 问 |
| `ToolTurnContext` | 单回合内工具轮次的最小状态 |

服务名常量集中在 `core/context.py` 顶部，装配点与使用方引用同一常量。

## 延伸阅读

- [architecture.md](../architecture.md)：五层结构与装配
- [context.md](context.md)：上下文管理
- [tools.md](tools.md)：工具执行管道
