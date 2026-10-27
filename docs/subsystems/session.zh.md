[English](session.md) | **中文**

# 会话存储与协作

`agent/mechanisms/session_store.py` 负责会话事实落盘；`agent/mechanisms/run_registry.py` 跟踪正在跑的回合，
`agent/mechanisms/mesh.py` 负责跨会话投递，`agent/mechanisms/session_title.py` 生成标题，
`agent/mechanisms/live_state.py` 持有会话状态，`agent/mechanisms/file_safety.py` 提供版本化备份与回收目录。

## 事实日志

### 布局

```
<data_root>/sessions/<cid>.raw      每会话一条日志，JSONL，每行一条事件
<data_root>/cache/session_encryption.key    加密密钥（local 模式创建）
```

会话 id 必须匹配 `^[A-Za-z0-9_-]{8,128}$`，不合法一律拒绝。这道校验也是防路径穿越的第一道边界。

### 只追加

日志是 **append-only 的事实流**：每发生一件事追加一行，不改写已有行。

「模型可见 ⟺ 已记录」这条结构保证就落在这里：任何过滤、清理、格式化必须发生在落盘**之前**，落盘后不可改写。

### 行格式

```json
{"t":"assistant_delta","d":{"text":"好"},"s":226310}
```

只写磁盘需要的东西，能从别处还原的一律不写。会话日志里绝大多数行是流式增量，
每行载荷只有几个字，键名与冗余字段都会按行数放大：

| 键 | 说明 |
|---|---|
| `t` | 事件类型 |
| `d` | 事件载荷 |
| `s` | 全局存储坐标。事件产出瞬间由 `emit` 标进载荷 `_seq`，落盘时提到顶层 `s` 并从 `d` 删掉，每行只留一份 |
| （无） | `conversation_id` 不落盘：文件名就是会话 id（`<cid>.raw`），读盘的人手上已经有它 |

`s` 不能省：SSE 的 `id:` 行用它。浏览器断线重连时经 `Last-Event-ID` 带回，
服务端据此从该位置续传（见 `cursor_of` / `replay_after`）。

`s` 取自一个跨会话共享、从不重置的全局计数器，所以一个会话的首个坐标取决于该计数器当时的值。
坐标不保证连续：事件在产出瞬间就拿号，没落盘的那些号会被跳过。游标只要求单调唯一，不要求连续。

读回时两样都补回来（`event_from_obj`）：坐标从 `s` 取，`conversation_id` 按会话文件名填。
内存里的事件一律带 `conversation_id`，SSE 靠它把帧分派到正确的会话页面。

### 序号

`allocate_seq(count)` 预留一段连续坐标，`_observe(seq)` 记录已见的最大坐标。
消费方用坐标判断从哪里继续，SSE 断线重连靠它。分配器首次分配前会用磁盘上的最大坐标初始化。

### 加密

两种模式：

| 模式 | 说明 |
|---|---|
| `none` | 明文行 |
| `local` | 每行独立加密成 JSON envelope，纯标准库 encrypt-then-MAC（HMAC-SHA256） |

行级独立加密意味着追加不必重写或重新加密整个日志，单行损坏也不会毁掉其余行。

明文与密文行可以混存；无法解密或解析的行会被跳过。

`MAGIC = "__fan_agent_session_encrypted__"` 是 envelope 的标识，也是加密日志的落盘格式标记；
改动它会使这些日志无法读回。

### 读取容错

坏行跳过，缺文件返回空列表，不能产出事件类型的行忽略。
明文与密文按行识别，所以无论每行由哪种模式写入，日志都保持可读。

## 跨进程锁

### 跨进程

同会话的「记偏移 → 追加 → 回滚」是读改写。进程内锁挡不住别的进程：
并发写同一个 `.raw` 会静默丢行，退出码仍为 0。

因此写入按文件加一层 **跨进程** 排它锁：Windows 用 `msvcrt.locking`，POSIX 用 `fcntl.flock`。
Windows 在循环中重试非阻塞加锁；POSIX 阻塞在 `flock` 上。

### 语义

| 情况 | 行为 |
|---|---|
| 拿到锁 | 正常写入 |
| 争用超时（Windows 轮询路径；默认 30 秒，`AI_AGENT_LOCK_TIMEOUT` 可调） | 抛错；批次进入待重试队列；不降级为无锁写 |
| 本平台没有任何锁机制 | 打印警告并降级为仅进程内锁；这是环境限制，不是争用 |

POSIX 上 `flock` 会一直阻塞到锁可用。

### 锁文件

锁文件是日志路径加上 `.lock`（`<cid>.raw.lock`）。文件为零字节、常驻不删：
删除会与别的进程已打开的句柄形成「锁的是已删除文件」的竞态。

## 待重试队列

写入失败（锁超时、磁盘错误）的批次进入待重试队列，`flush_pending()` / `flush_all()` 稍后重投。

失败批次重新入队时，`_pending_only_new()` 按序号比对已排队或已落盘的事实，同一条事实只写一次。

每个会话的队列上限为 `_PENDING_MAX_BATCHES = 64` 批；溢出时丢弃最旧的批并写 stderr 警告。

## 运行态登记

`run_registry.py` 回答一个问题：**某个会话的回合是否正在运行**。

这个答案必须能从服务端查询，中途打开的页面才能显示运行状态与停止控件。

| 实现 | 用途 |
|---|---|
| `InMemoryRunRegistry` | 纯内存；单实例与测试；不给目录时选它 |
| `FileRunRegistry` | 落盘（默认装配下为 `<data_root>/mesh/runs/<cid>.json`）；跨实例可见 |

`build_run_registry(directory)` 按目录选实现：`None` 返回纯内存版本。

判定「在跑」需要两个条件同时成立：

1. 心跳未过期（TTL 默认 900 秒）；
2. 记录里那个进程还活着。

占位期间读取也会续心跳（`running()` 调用 `touch`），并受最小间隔限制，长工具调用不会被误判成回合结束。

pid 检查覆盖 TTL 窗口：进程被强杀后心跳冻结在最后一次写入，文件在最长 15 分钟内仍显得新鲜；
比对 pid 可以立即识别。

### 进程探活

Windows 用 `ctypes` 的 `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`：

| 结果 | 判定 |
|---|---|
| 拿到有效 handle | 进程存在 → 活着 |
| `last_error == 87`（`ERROR_INVALID_PARAMETER`） | 确知该 pid 不存在 → 已死 |
| 其它错误 | 说不准 → 按活着处理 |

不能用 `os.kill(pid, 0)`：在没有控制台的进程里（Windows 服务、计划任务、`pythonw`、分离启动），
它对活着的进程也抛 `OSError [WinError 87]`。把它当成已死会让并发保护与停止控件同时失效。

非 Windows 回落 `os.kill`，只认 `ProcessLookupError` 为确知已死。

说不准的结果按活着处理，交给 TTL 过期回收。

## 协作网格

`mesh.py` 的 `MeshState` 在会话之间投递消息。

| 能力 | 说明 |
|---|---|
| Agent 注册表 | 已登记的 Agent 及其元数据，落 `agents.json`（mesh 目录） |
| 待发送队列 | 目标忙或无法激活时用户与 Agent 消息排队，落 `data/queues/<cid>/` |
| 原子投递 | 忙闲检查与投递决策在同一把锁内完成 |

队列内容由 `ConversationQueue` 保存。回合结束后由运行器抽干队列；
插入请求经 `QueuedInputModule` 在压缩前收进上下文。回合因工具挂起（用户确认、审批等）时，
队列保持暂停，不自动起新回合。忙闲状态来自运行态登记，所以网格与 `/api/chat/ui-state` 读取同一事实源。

## 标题

`session_title.py` 发起一次无工具的模型调用。输入是会话首条用户输入加首条模型回复（各自截断），
输出清洗成不超过 18 字的标题，落盘 `<data_root>/titles/<cid>.title`。

失败（无 provider、异常、空文本、退化占位）时回落到首条用户输入的前缀（没有用户输入则为空），不阻断任何流程。
标题是派生缓存，可以重新生成，所以与事实日志分开存放。

## 会话状态

`LiveState` 在 `live_state.py` 中持有按会话分键的可变状态。落盘与内存字段分开看：

| 字段 | 落盘 | 说明 |
|---|---|---|
| `model` | 是 | 会话级模型选择；空串回落 `default_model` |
| `mode` | 是 | 只有 `plan` / `execute` 落盘；`auto` 摘掉该键 |
| `effort` | 是 | `high` / `max`；空回落全局 `default_effort` |
| `todo` | 是 | 嵌套在 `todo` 键下，字段为 `list_id` / `items` / `collapsed` |
| 自主 / 目标 | 否 | 进程内状态，重启即失效 |

一个会话一份 JSON：`<data_root>/session_state/<cid>.json`。

```json
{"model": "upstream-flash", "mode": "plan", "effort": "max",
 "todo": {"list_id": "l-1", "items": [{"id": "1", "text": "x", "done": false}], "collapsed": false}}
```

三条规则：

1. **缺键即默认**。任一分量为空就不写这个键，不存空值与「未选择」占位；四个分量全空则删文件。
2. **写前先读**。四个分量同住一份文件，任一路径写入前都要 `_ensure_loaded`，否则会覆盖其它分量。
3. **只认这一种形状**。读路径只接受这种结构，没有第二套结构的兼容分支。

cid 必须匹配 `[A-Za-z0-9_-]{8,128}` 才拼路径，非法 cid 直接不落盘。

## 文件安全设施

`file_safety.py` 包含两个类：

| 类 | 作用 |
|---|---|
| `FileBackups` | 写盘前对文件原内容做版本化备份，供 `file_undo` 比对与回滚 |
| `Recycle` | 删除操作的回收目录，使删除可恢复 |

两者默认落在数据根下（`data/temp/file_backup/`、`data/recycle/`），随数据根迁移。

## 延伸阅读

- [architecture.zh.md](../architecture.zh.md)：事实与投影
- [tools.md](tools.md)：写盘四步协议
- [shell.md](shell.md)：SSE 断线重连与序号
