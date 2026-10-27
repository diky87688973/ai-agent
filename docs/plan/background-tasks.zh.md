[English](background-tasks.md) | **中文**

# 后台任务管理器

状态：已实现。

## 名称

```text
工具：background_task
服务：BackgroundTaskManager
记录：BackgroundTaskRecord
执行器：BackgroundTaskExecutor
状态：字符串常量（queued / running / completed / failed / timed_out / cancelled）
输出：output 动作返回的 dict
业务身份：task_id
```

统一使用 `task`，不混用 `job`。

## 工具接口

```text
background_task(action="create", argv, cwd?, timeout_sec, label, batch?)
background_task(action="list", batch, task_id?, status?)
background_task(action="cancel", task_id, reason?)
background_task(action="output", task_id, wait?, timeout_ms?)
```

`create` 必须提供非空 `label`，最长 120 字；它是工具壳展示的任务小标题，允许同名。
`argv` 是非空字符串数组，直接交给 `Popen`，不经过 shell；参数中的分号、管道符等按普通字符处理。
`create` 返回 `task_id` 和 `batch`。首次创建生成 `batch`；后续创建传回这个 `batch` 即归入同一批。cid 内不存在的批次返回 `batch_not_found`。
排队中的任务 `pid=null`，不承诺立即有进程。`task_id` 是业务身份；`pid` 只用于内部诊断和展示。

`list` 必须提供 `batch`；返回该批次的全部任务，不翻页。
`list` 同时接受精确 `task_id` 过滤和可选 `status` 过滤。

`timeout_sec` 必填，范围 1–86400，从 `create` 时刻开始计时，包含排队与执行。

## 队列

每个 cid 一份队列：

```text
pending   待执行
running   执行中
history   所有终态记录，只追加不删除
```

限制：

```text
MAX_RUNNING_PER_CID = 10
MAX_PENDING_PER_CID = 10
```

`pending` 达到 10 时 `create` 返回 `task_queue_full`，任务不入队。
`running` 达到 10 时不再启动新任务，任务留在 pending。

同一 cid 严格 FIFO。不同 cid 独立调度，各自最多 10 个 running。

## 状态

```text
queued
running
completed
failed
timed_out
cancelled
```

这些值是模块级字符串；`TERMINAL` 是四个终态值的集合。
内部字段 `cancel_requested` 表示已请求取消但进程尚未退出；对外状态仍为 `running` 直到真正终态。

状态迁移：

```text
create -> queued
queued -> running | timed_out | cancelled
running -> completed | failed | timed_out | cancelled
```

终态定义：

```text
completed   exit_code == 0
failed      启动失败或非零退出
timed_out   排队超时或执行超时
cancelled   用户或模型取消
```

`timed_out` 与 `failed` 分开，避免把超时误报为普通失败。

## 超时

`deadline_at = created_at + timeout_sec`。

```text
排队期间到期：不启动进程，标 timed_out，detail=queue_timeout
执行期间到期：杀进程树，标 timed_out，detail=execution_timeout
```

待执行任务在调度器下一次有空闲 running 位处理时结算；running 已满 10 个时，它的状态可能在到期后仍保持 `queued`。
超时后不重试。

## 输出

每个任务每条流各一份有界缓冲（256 KiB）：

```text
stdout / stderr 分开
每个任务一个 stdout_cursor 和一个 stderr_cursor
每次 output 调用同时消费两条流并推进两个游标
模型工具与经典界面的任务详情通过同一个 output 动作读取，共享消费
后续调用只返回此前任何调用都未消费的字节
```

`output` 返回：

```json
{
  "task_id": "bt-...",
  "status": "running",
  "output": "...",
  "stderr": "...",
  "truncated": false,
  "exit_code": null
}
```

`output` 只能查询 running 或终态任务；仍在 pending 的任务返回 `task_not_found`。
`truncated` 每个任务一个标志，任一流的字节因上限被丢弃后为 true。

`wait=true` 等待任务终态或 `timeout_ms` 到期；等待超时返回 `running`，不杀任务。`timeout_ms` 默认 30000，上限 600000。

裁剪时按丢弃字节数回退该流游标（并夹到新长度），后续读取从同一个未消费字节开始，不会停在旧偏移或空尾部。因上限丢弃的字节不可恢复。

## 取消

```text
queued：立即标 cancelled，不产生 pid
running：标记 cancel_requested，杀整棵进程树；进程退出后标 cancelled
终态：返回当前状态，不报错
```

取消和超时共用同一套进程树清理逻辑。

## 沙箱

采用进程级隔离：

```text
cwd 必须位于允许根目录内
路径 resolve 后比对，拒绝 .. 与符号链接逃逸
清理继承环境，只保留运行所需白名单；未知变量与凭据不传入
stdin 指向 DEVNULL
不接受模型传入 env
Windows：以 CREATE_NO_WINDOW 启动；取消和超时用 taskkill /F /T
Unix：以 start_new_session（setsid）启动；取消和超时向进程组发信号，先 SIGTERM 再 SIGKILL
```

明确边界：

```text
进程级隔离不是文件系统沙箱
命令内部仍可能访问允许根之外的路径
```

不允许把“进程级”表述为“安全沙箱”。

允许根是项目根和数据根；默认 cwd 为项目根。

## 通知

每个 cid 只发一条通知：active 数量（pending + running）降到 0 时触发；history 不参与。自上次通知以来结算的批次合并到一条消息里，用 `、` 连接。

消息内容：

```text
<<系统通知>>
本消息为 任务管理器 触发的系统通知
任务批次：<batch> 已完结，请查看结果。
```

通知消息的元数据：

```text
role=user
kind=system_notice
source=background_tasks
notice_id=<唯一 id>
batch=<批次号；多个用 、 连接>
content 仍以 <<系统通知>> 开头
```

契约只认 `kind` 与 `source`：`kind=system_notice` 且 `source=background_tasks` 时才渲染系统通知卡片；前缀只留给模型识别，不参与信任判断。普通用户消息即使以该前缀开头，也不会被渲染成系统通知。

经典界面把符合条件的 user 消息渲染成对话区顶部的系统通知卡片，不复用普通用户气泡。
卡片宽度为对话区的 50%，居中，贴合上边框，顶部左右无圆角。
默认 6 秒后自动消失；用户展开详情后暂停自动消失，折叠后 4 秒再消失；新通知到达时用新卡片替换旧卡片。

模型忙时通知进入 ConversationQueue，`origin=system`、`delivery=next_pass`，入队后立即置为 inserting；队列 UI 不显示系统通知。模型空闲时直接启动一个回合；启动失败时回退到队列。

注入字段：

```text
直接回合 meta：kind=system_notice、source=background_tasks、notice_id、batch
入队 payload：在上述字段上增加 rule=user 和 internal=true
```

从 payload 只读回 `kind`、`source`、`notice_id`、`batch`；`rule` 与 `internal` 写入但不读取。会话标题生成跳过内容以 `<<系统通知>>` 开头的用户消息（允许前导空白）。

只有应用停机调用 `BackgroundTaskManager.shutdown`：杀掉运行中的任务进程，并逐个最多等待 3 秒结算；待执行任务留在队列。释放或关闭会话（`release_conversation` / `drop_session`）不取消后台任务。

## 模块

```text
agent/mechanisms/background_tasks.py
agent/capabilities/builtin/background_task.py
```

装配：

```text
BackgroundTaskManager 在 app 中创建，注册到 AppContext 的 background_tasks
background_task 工具取当前会话 cid 后调用 manager
app 装配 manager 的通知回调：正在运行的 cid 进 ConversationQueue，空闲的 cid 走 SessionRunner.start
App.dispose 调用 shutdown；会话释放不触碰任务
```

## 与前台命令工具的分工

`run_command` 与 `background_task` 并列，不是兼容层，也不下线。

前台同步短命令、交互、安装构建使用 `run_command`；后台长任务、服务、并行、取消轮询使用 `background_task`。
`background_task` 使用独立参数、进程、超时、输出和取消语义。

## 测试

```text
每个 cid 10 个 running + 10 个 pending；第 11 个 pending 返回 task_queue_full
另一个 cid 看不到任务
取消 queued（无 pid）与 running（结算为 cancelled）
执行超时结算为 timed_out
cwd 越界拒绝
继承环境保留用户路径、丢弃未知密钥
label 必填且可同名；batch 归组任务并支持精确 task_id 过滤
list 返回整批任务，不翻页
argv 不经 shell 解释
plan 模式拒绝 create
工具分发 create / list / output / cancel
系统通知元数据经过队列与历史折叠后仍保留
已完成任务可读输出与历史；一条通知带 <<系统通知>> 前缀和批次号
app 注册 manager 与工具
```
