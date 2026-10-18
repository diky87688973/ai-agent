# 会话存储与协作

本页覆盖会话事实的落盘（`mechanisms/session_store.py`）、运行态登记（`run_registry.py`）、跨会话协作（`mesh.py`）、标题生成（`session_title.py`）、会话状态（`live_state.py`）与文件安全设施（`file_safety.py`）。

## 事实日志

### 布局

```
<data_root>/sessions/<cid>.raw     每会话一条日志，JSONL，每行一条事件
<data_root>/cache/session_encryption.key   加密密钥
```

会话 id 必须匹配 `^[A-Za-z0-9_-]{8,128}$`，不合法一律拒绝。这道校验也是防路径穿越的第一道边界。

### 只追加

日志是 **append-only 的事实流**：每发生一件事追加一行，不改写已有行。

「模型可见 ⟺ 已记录」这条结构保证就落在这里：任何过滤、清理、格式化必须发生在落盘**之前**，落盘后不可改写。

### 行格式

```json
{"t":"assistant_delta","d":{"text":"好"},"s":226310}
```

**只写磁盘需要的东西**，能从别处还原的一律不写 —— 会话日志里绝大多数行是流式增量，
每行 payload 只有几个字，键名与冗余字段都会按行数放大：

| 键 | 说明 |
|---|---|
| `t` | 事件类型 |
| `d` | 事件载荷 |
| `s` | 全局存储坐标。事件产出瞬间由 `emit` 标进载荷 `_seq`，落盘时**提到顶层 `s` 并从 `d` 删掉**，每行只留一份 |
| （无） | `conversation_id` **不落盘**：文件名就是会话 ID（`<cid>.raw`），读盘的人手上已经有它 |

`s` 不能省：SSE 的 `id:` 行用它，浏览器断线重连时经 `Last-Event-ID` 带回，
服务端据此从该位置续传（见 `cursor_of` / `replay_after`）。

它**跨会话共享、从不重置**，所以与行号差一个常数（会话第一次分配坐标时全局计数器到哪）。
它也**不保证连续**：事件在产出瞬间就拿号，而没落盘的那些号会被跳过。
游标只要求单调唯一，不要求连续，所以跳号无害。

读回时两样都补回来（`_event_from_obj`）：坐标从 `s` 取，`conversation_id` 按会话填 ——
**内存里的事件一律带 `conversation_id`**，SSE 靠它把帧分派到正确的会话页面。

### 序号

`allocate_seq(count)` 分配连续序号，`_observe(seq)` 记录已见的最大序号。序号让消费方能判断"从哪里继续"，SSE 断线重连靠它。

### 加密

两种模式：

| 模式 | 说明 |
|---|---|
| `none` | 明文行 |
| `local` | 每行独立加密成 JSON envelope，纯标准库 encrypt-then-MAC（HMAC-SHA256） |

行级独立加密的好处：追加时不必读全文件；单行损坏不会毁掉整档。

解析兼容明文与密文混存；损坏行返回 `None`，调用方跳过。

`MAGIC = "__fan_agent_session_encrypted__"` 是 envelope 的标识，**同时是既有加密会话的落盘格式标记** —— 改动它会导致旧会话读不出来。

### 读取容错

坏行跳过、缺文件返回空、未知事件类型跳过。这三点合起来保证旧格式会话在新代码下照常可读。

## 跨进程锁

### 跨进程

同会话的"记偏移 → 追加 → 回滚"是**读改写**。进程内锁挡不住别的进程：并发写同一个 `.raw` 会**静默丢行**，退出码仍为 0。

所以按文件加一层**跨进程**排它锁：Windows 用 `msvcrt.locking`，POSIX 用 `fcntl.flock`，非阻塞轮询。

### 语义

| 情况 | 行为 |
|---|---|
| 拿到锁 | 正常写入 |
| 争用超时（默认 30 秒，`AI_AGENT_LOCK_TIMEOUT` 可调） | **抛错**，数据进待重试队列。不降级为无锁写 |
| 本平台没有任何锁机制 | 留痕降级（打印警告），环境限制而非争用 |

### 锁文件

锁加在 `<日志>.lock` 上，文件为零字节、常驻不删：删除会与别的进程已打开的句柄形成"锁的是已删除文件"的竞态。

每趟开关开销约 +2.5ms/条，相对回合本身（秒级）可忽略。

## 待重试队列

写入失败（锁超时、磁盘错误）的批次进待重试队列，`flush_pending()` / `flush_all()` 稍后重投。

`_pending_only_new()` 在重投时按磁盘已有的序号过滤，**同一条事实只写一次**。

队列上限 `_PENDING_MAX_BATCHES = 64` 批。

## 运行态登记

`run_registry.py` 回答一个问题：**某个会话的回合是不是正在跑**。

会话是否在跑必须能从服务端问出来：只放在进程内存里的判定在另一个进程或另一个实例里看不见，中途打开的页面既发不出消息（必 409）也停不掉任务。

| 实现 | 用途 |
|---|---|
| `InMemoryRunRegistry` | 纯内存，单实例 / 测试；不给目录时选它 |
| `FileRunRegistry` | 落盘（`<data_root>/mesh/runs/<cid>.json`），跨实例可见 |

`build_run_registry(dir)` 按目录是否为 `None` 选实现。

判定"在跑"需要两个条件同时成立：

1. 心跳未过期（TTL 默认 900 秒）；
2. 记录里那个进程**还活着**。

占位期间**读取也会续心跳**（`running()` 读取时刷新），所以长任务执行中途不会被误判成"已结束"。

第二条件解决的是 TTL 窗口内的误判：进程被强杀后心跳冻结在死前那一刻，而 TTL 还有十几分钟，这期间文件看起来完全"新鲜"。判一下 pid 就能立刻识破。

### 进程探活

Windows 用 `ctypes` 的 `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`：

| 结果 | 判定 |
|---|---|
| 拿到有效 handle | 进程存在 → 活着 |
| `last_error == 87`（`ERROR_INVALID_PARAMETER`） | 确知该 pid 不存在 → 已死 |
| 其它错误 | 说不准 → 按活着处理 |

**不能**用 `os.kill(pid, 0)`：在没有控制台的进程里（Windows 服务、计划任务、`pythonw`、分离启动），它对**活着的**进程也抛 `OSError [WinError 87]`。把它当成"已死"会让并发保护与停止键同时失效。

非 Windows 回落 `os.kill`，只认 `ProcessLookupError` 为"确知已死"。

"说不准就当活着"由 TTL 兜底回收：误判"死了"会让正在跑的任务失去保护，误判"活着"最多让过期记录多留一会儿。

## 协作网格

`mesh.py` 的 `MeshState` 让多个会话互相投递消息。

| 能力 | 说明 |
|---|---|
| 会话名册 | 记录有哪些会话、各自状态（落 `agents.json`） |
| inbox 队列 | 目标忙时消息排队，不丢（落 `inbox/<cid>.jsonl`） |
| 忙闲原子投递 | 投递与状态判定在一个原子步内完成 |

队列内容经 `InboxModule` 在回合开始前收进上下文（见 [core.md](core.md)）。忙闲状态来自运行态登记，所以"目标忙不忙"的判定与 `/api/chat/ui-state` 用的是同一个事实源。

## 标题

`session_title.py`：一次无工具的模型调用，输入是会话首条用户输入加首条模型回复（截断），输出清洗成不超过 18 字的标题，落盘 `<data_root>/titles/<cid>.title`。

失败（无 provider / 异常 / 空文本 / 退化占位）回落到**首条用户输入的前缀**，不阻断任何流程。标题是**派生缓存**：可以重新生成，因此不与用户意图共用文件。

## 会话状态

`live_state.py` 的 `LiveState` 持有按会话分键的可变状态。落盘与内存分开看：

| 字段 | 落盘 | 说明 |
|---|---|---|
| `model` | 是 | 会话级模型选择；空串回落 `default_model` |
| `mode` | 是 | `plan` / `execute` 才算覆盖，`auto` 不写文件 |
| `effort` | 是 | `high` / `max`；空回落全局 `default_effort` |
| `todo` | 是 | 嵌套在 `todo` 键下，字段为 `list_id` / `items` / `collapsed` |
| 自主 / 休眠 / 目标 | 否 | 回合内临时事实，进程重启即失效 |

一个会话一份 JSON：`<data_root>/session_state/<cid>.json`。

```json
{"model": "deepseek-flash", "mode": "plan", "effort": "max",
 "todo": {"list_id": "l-1", "items": [{"id": "1", "text": "x", "done": false}], "collapsed": false}}
```

三条纪律：

1. **缺键即默认**。任一分量为空就不写这个键，不存空值与"未选择"占位；四项全空则删文件。
2. **写前先读**。四个分量同住一份文件，任一路径写入前都要 `_ensure_loaded`，否则会覆盖其它分量（关闭清单时连带清掉模型即属此类）。
3. **只认这一种形状**。读路径不做结构兼容：兼容分支会让两套结构长期并存，每次改动都要同时证明两套都对。

cid 必须匹配 `[A-Za-z0-9_-]{8,128}` 才拼路径，非法 cid 直接不落盘（防穿越）。

## 文件安全设施

`file_safety.py` 两个类：

| 类 | 作用 |
|---|---|
| `FileBackups` | 写盘前的版本化备份，供 `file_undo` 比对与回滚 |
| `Recycle` | 删除操作的回收目录，使删除可恢复 |

两者都落在数据根下（`data/temp/file_backup/`、`data/recycle/`），随数据根一起迁移。

## 延伸阅读

- [architecture.md](../architecture.md)：事实与投影的关系
- [tools.md](tools.md)：写盘四步协议
- [shell.md](shell.md)：SSE 断线重连与序号
