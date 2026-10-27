[English](core.md) | **中文**

# 内核

`agent/core/` 是 L0 层，不依赖任何其它层。它提供四样东西：数据契约、模块抽象、链执行器、宿主循环。

## 数据契约

| 文件 | 内容 |
|---|---|
| `event_name.py` | 26 个事件名常量。纯字符串，零依赖 |
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
| `suspend` | 回合结束，控制权交回宿主；由外部事件另起回合恢复 |
| `stopped` | 被取消信号终止 |

`Outcome` **只带控制信号，不带数据**（`reason` 是终态说明，不是载荷）。正文、用量、进度全部经 `ports.emit()` 发出。这个约束让模块之间没有共享可变状态。

## 模块抽象

```python
class ModuleBase:
    # 生成器契约：yield 事实，return 控制信号
    def execute(self, ports: Ports) -> Iterator[Event]: ...
```

行为面只有这一个方法。执行期模块只拿到 `Ports`，拿不到回合上下文对象，模块之间也不互相引用。

五个具体模块在 `agent/core/modules/` 包：

| 模块 | 做什么 | 主要事件 |
|---|---|---|
| `InputModule` | 把本回合新用户输入认领成事实 | `input_started` / `input_claimed` / `input_ended` |
| `QueuedInputModule` | 把待发送队列中标记插入的消息收进上下文 | `input_claimed` |
| `CompressModule` | 拼入前预算检查，超阈值压缩 | `compress_started` / `context_compacted` / `compress_ended` |
| `ModelModule` | 发请求、消费流、聚合工具调用 | `llm_started` / `assistant_delta` / `reasoning_delta` / `llm_done` / `llm_failed` / `llm_ended` / `model_message` / `usage` / `context_segments` |
| `ToolModule` | 执行工具、回灌结果 | `tool_started` / `tool_progress` / `tool_done` / `tool_failed` / `tool_canceled` / `tool_suspended` / `tool_ended` |

`build_default_chain()` 按 `输入 → 待发送队列插入 → 压缩 → 模型 → 工具` 的顺序组装。

### 各模块的判定依据

**`InputModule`**：有输入就发 `input_claimed` 并返回 `ok`；**无输入时不发 `input_claimed`**，只发终态 `input_ended`。原因是：接口确认触发的恢复轮没有用户发言，此时凭空发一条空的 `input_claimed` 会让消息序列变成 `…assistant(tool_calls) → user("") → tool`，模型接口直接拒绝。

**`QueuedInputModule`**：位置固定在压缩之前。插入消息会变成新的用户轮次，压缩得看得见它们，否则插入后立即按旧预算压缩会把新消息挤掉。一次执行消费全部待插入请求。

**`CompressModule`**：做拼入前的上下文预算检查，超阈值压缩。从不要求续行——压缩是准备动作。压缩器缺省或出错一律放行：压缩是增强项，绝不阻断回合。

**`ModelModule`**：从事实末端向前判定跑不跑：先遇到新用户输入（`input_claimed`）或工具结果（`tool_ended`）→ 跑；先遇到模型自己的消息（`model_message`）→ 不跑。

**`ToolModule`**：本链的收尾模块。找到最新模型消息里要求了但尚无结果的调用并执行；已被挂起的调用不重复执行。需要外部输入时发 `tool_suspended` 与 `tool_ended`，取消同批剩余调用，并返回 `Outcome.suspend(...)`（交回控制权，不阻塞）；否则，执行过调用就返回 `next`。

## 链执行器

`chain.py` 回答"一趟怎么跑"：

```python
run_chain_iter(modules, ports) -> _Pass
run_chain(modules, ports)      -> PassResult
step(module, ports)            -> (list[Event], Outcome)
```

`run_chain_iter` 返回可迭代的 `_Pass`：迭代时逐个产出事件，迭代结束后读 `.result`。`PassResult` 记录这一趟的终态（若有）与是否有模块要求续行。`run_chain` 遇到任一终态（`halt` / `suspend` / `stopped`）立即中断，不再跑后续模块。`step` 是单模块的窄入口（测试、装配校验用）。

## 宿主循环

`host.py` 回答"跑到什么时候停"，并划定回合边界。

```python
class Host:
    def run(...) -> TurnResult
```

出现终态（`halt` / `suspend` / `stopped`）时回合结束。否则，默认链下回合在以下三条同时成立时结束：

1. 没有待回灌的工具结果；
2. 本趟开始时待发送队列里没有待插入消息；
3. 没有任何模块要求续行（`Outcome.next`）。

这三条中，宿主只直接检查第 3 条（`PassResult.wants_another`），前两条由模块行为产生：`ToolModule` 执行过调用就返回 `next`，`QueuedInputModule` 在压缩前消费插入请求。

有安全阀 `MAX_PASSES_DEFAULT = 64`：一个回合最多跑这么多趟，防止续行信号形成死循环。

`TurnResult` 汇总一个回合的结果：结束原因（`done` / `halted` / `suspended` / `stopped` / `max_passes` / `abandoned`）、跑过的趟数与终态说明。事实本身在 `SessionLog` 里，不在它身上。

## 引擎外观

`engine.py` 的 `Engine` 把模块链包成壳层要的两面：

- **开始回合**：投递输入、启动宿主循环；
- **事件流**：把内核事件以迭代器形式交出去。

`App.session(conversation_id, *, system_prompt, cancel, ...)` 每次构建一个新的 `Engine`，会话之间不共享回合状态。

## 会话作用域

`session_scope.py` 解决"工具在深层调用里怎么知道自己在哪个会话"。

```python
set_session_scope(cid) / reset_session_scope() / current_session_id()
set_tool_turn_context(ctx) / reset_tool_turn_context() / current_context()
set_progress_reporter(fn) / emit_progress(stream=..., text=..., done=...)
```

用 contextvar 实现。工具与管道钩子经 `current_session_id()` 取会话 id，再向 `SessionContexts` 解析会话上下文。这是会话隔离的执行手段。

## 视觉嵌图

`image_embed.py` 处理"附件图片怎么进请求体"，属于"消息派生"的一段：把事实折叠成请求的那一方负责这件事。

- `shrink_image()` / `shrink_path()`：本地按长边缩放，减小 base64 体积（长边上限 `EMBED_MAX_SIDE = 800`）；
- `build_embed_parts()`：拼成请求的 `image_url` 内容块；
- `strip_old_images()`：保留最近若干条带图用户消息与工具消息里的图片。`keep_turns` 限制参与保留的最近带图用户消息条数，`max_images` 限制总张数（默认 1 轮 / 8 张，来自 `[context]` 的 `image_turns` / `image_max`）。被轮次窗口排除或超出总量上限时，按消息时间从最老的图片开始剥，最新图片优先保留；同一条消息内先剥最早的图片；
- `placeholder_text()`：图片因体积预算被跳过时的占位文本；
- `_drop_selected_blocks()`：图片因轮次窗口/总量配额被剥离时，占位文本携带原图的 `attachment_id`，模型可用 `read_image(attachment_id=...)` 重新读取；
- `strip_attachment_meta()`：请求发出前移除仅供占位解析的 `attachment_id`，不把内部引用发给 provider；
- `read_image` 对同一回合内重复读取同一附件给出结构化错误，阻断"读图 → 被剥 → 再读"的循环。

被剥掉的图只从**发给模型的这一份**里消失：事实流里的 base64 一个字节都不动，历史回显与重新提问都还能拿到原图。

## 上下文容器

`context.py` 有两个类：

| 类 | 作用 |
|---|---|
| `AppContext` | 进程级服务登记表：`register(name, svc)` / `get(name)` / 注销句柄。未注册的 name 由 `get` 抛 `KeyError`，存在性用 `has(name)` 问 |
| `ToolTurnContext` | 单回合内工具往返的最小状态 |

服务名常量集中在 `core/context.py` 顶部，装配点与使用方引用同一常量。

## 延伸阅读

- [architecture.zh.md](../architecture.zh.md)：五层结构与装配
- [context.md](context.zh.md)：上下文管理
- [tools.md](tools.zh.md)：工具执行管道
