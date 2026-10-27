**English** | [中文](background-tasks.zh.md)

# Background task manager

Status: implemented.

## Naming

```text
tool: background_task
service: BackgroundTaskManager
record: BackgroundTaskRecord
executor: BackgroundTaskExecutor
status: string constants (queued / running / completed / failed / timed_out / cancelled)
output: dict returned by the output action
business identity: task_id
```

`task` is used uniformly; `job` is not mixed in.

## Tool interface

```text
background_task(action="create", argv, cwd?, timeout_sec, label, batch?)
background_task(action="list", batch, task_id?, status?)
background_task(action="cancel", task_id, reason?)
background_task(action="output", task_id, wait?, timeout_ms?)
```

`create` must provide a non-empty `label` of at most 120 characters; it is the short task title shown in the tool card, and labels may repeat.
`argv` is a non-empty string array passed directly to `Popen`, not through a shell; semicolons, pipe characters, and other shell metacharacters in arguments are treated as ordinary characters.
`create` returns `task_id` and `batch`. The first create generates `batch`; passing that `batch` to later creates puts those tasks in the same batch. A batch that does not exist in the cid is rejected with `batch_not_found`.
A queued task has `pid=null`; no process is guaranteed to exist immediately. `task_id` is the business identity; `pid` is only for internal diagnostics and display.

`list` must provide `batch`; it returns every task in that batch without pagination.
`list` also accepts an exact `task_id` filter and an optional `status` filter.

`timeout_sec` is required and ranges from 1 to 86400. It starts at `create` and covers both queueing and execution.

## Queue

Each cid has one queue:

```text
pending   waiting to run
running   executing
history   all terminal records; append-only
```

Limits:

```text
MAX_RUNNING_PER_CID = 10
MAX_PENDING_PER_CID = 10
```

When `pending` reaches 10, `create` returns `task_queue_full` and the task is not queued.
When `running` reaches 10, no new task starts and tasks stay in pending.

Tasks within a cid are strictly FIFO. Different cids are scheduled independently, each with at most 10 running tasks.

## States

```text
queued
running
completed
failed
timed_out
cancelled
```

The values are module-level strings; `TERMINAL` is the set of the four terminal values.
The internal field `cancel_requested` means cancellation has been requested but the process has not exited; the public status remains `running` until a terminal state is reached.

Transitions:

```text
create -> queued
queued -> running | timed_out | cancelled
running -> completed | failed | timed_out | cancelled
```

Terminal states:

```text
completed   exit_code == 0
failed      spawn failure or non-zero exit
timed_out   queue timeout or execution timeout
cancelled   cancelled by the user or the model
```

`timed_out` is separate from `failed` so that a timeout is not misreported as an ordinary failure.

## Timeouts

`deadline_at = created_at + timeout_sec`.

```text
expires while queued: no process is started; status timed_out, detail=queue_timeout
expires while running: the process tree is killed; status timed_out, detail=execution_timeout
```

A pending task past its deadline is settled when the scheduler next has a free running slot to consider it; while all 10 running slots are occupied, its status can remain `queued` past the deadline.
No retry after a timeout.

## Output

Each task has one bounded buffer per stream (256 KiB):

```text
stdout / stderr kept separate
one stdout_cursor and one stderr_cursor per task
every output call consumes both streams and advances both cursors
the model tool and the classic UI's task detail view read through the same output action, so they share consumption
a later call returns only bytes that no earlier call consumed
```

`output` returns:

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

`output` resolves only running or terminal tasks; a task still in pending returns `task_not_found`.
`truncated` is one flag per task and becomes true when either stream drops bytes at the cap.

`wait=true` waits for a terminal state or until `timeout_ms` expires; if the wait expires, it returns `running` and does not kill the task. `timeout_ms` defaults to 30000 and is capped at 600000.

A trim subtracts the dropped byte count from the stream cursor (clamped to the new length). Later reads therefore start at the same unconsumed byte instead of an old offset or an empty tail. Bytes dropped by the cap are not recoverable.

## Cancellation

```text
queued: mark cancelled immediately; no pid is created
running: set cancel_requested and kill the whole process tree; mark cancelled after the process exits
terminal: return the current status without an error
```

Cancellation and timeouts share the same process-tree cleanup logic.

## Sandbox

Process-level isolation:

```text
cwd must be inside an allowed root
paths are resolved before comparison; .. and symlink escapes are rejected
the inherited environment is filtered to an execution whitelist; unknown variables and credentials are not passed
stdin points to DEVNULL
env passed by the model is not accepted
Windows: spawn with CREATE_NO_WINDOW; cancellation and timeout use taskkill /F /T
Unix: spawn with start_new_session (setsid); cancellation and timeout signal the process group, SIGTERM then SIGKILL
```

Explicit boundary:

```text
process-level isolation is not a filesystem sandbox
the command itself can still reach paths outside the allowed roots
```

Process-level isolation is not a security sandbox.

Allowed roots are the project root and the data root; the default cwd is the project root.

## Notifications

A single notification fires per cid when its active count (pending + running) drops to 0; history does not participate. All batches settled since the previous notification are listed in one message, joined with `、`.

Message content:

```text
<<系统通知>>
本消息为 任务管理器 触发的系统通知
任务批次：<batch> 已完结，请查看结果。
```

Metadata of a notification message:

```text
role=user
kind=system_notice
source=background_tasks
notice_id=<unique id>
batch=<batch ids; multiple joined with 、>
content still starts with <<系统通知>>
```

The contract relies only on `kind` and `source`: a system-notice card is rendered only when `kind=system_notice` and `source=background_tasks`; the prefix is left for the model to recognize and does not participate in trust decisions. An ordinary user message that starts with that prefix is not rendered as a system notice.

The classic UI renders a matching user message as a system-notice card at the top of the conversation pane, without reusing the ordinary user bubble.
The card is half the width of the conversation pane, centered, flush with the top edge, with square top corners.
It disappears automatically after 6 seconds by default; expanding the details pauses automatic dismissal, and collapsing them dismisses it after 4 more seconds; when a new notice arrives, the old card is replaced by the new one.

When the cid is busy, the notice enters ConversationQueue with `origin=system` and `delivery=next_pass`, and is set to `inserting` immediately after enqueueing; the queue UI filters out system notices. When the cid is idle, it starts a turn directly; if that start fails, it falls back to the queue.

Injection fields:

```text
direct turn meta: kind=system_notice, source=background_tasks, notice_id, batch
queued payload: those fields plus rule=user and internal=true
```

Only `kind`, `source`, `notice_id`, and `batch` are read back from the payload; `rule` and `internal` are written but not read. Session-title generation skips a user message whose content starts with `<<系统通知>>` (leading whitespace allowed).

Only application shutdown calls `BackgroundTaskManager.shutdown`, which kills the running task processes and waits up to 3 seconds for each to settle; pending tasks are left queued. Releasing or closing a session (`release_conversation` / `drop_session`) does not cancel background tasks.

## Modules

```text
agent/mechanisms/background_tasks.py
agent/capabilities/builtin/background_task.py
```

Assembly:

```text
BackgroundTaskManager is created in the app and registered in AppContext as background_tasks
the background_task tool resolves the current session cid and calls the manager
the app wires the manager's notice callback: busy cid -> ConversationQueue, idle cid -> SessionRunner.start
App.dispose calls shutdown; session release does not touch tasks
```

## Relation to the foreground command tool

`run_command` and `background_task` are peers, not a compatibility layer; both remain available.

Use `run_command` for short synchronous foreground commands, interactive sessions, and installs or builds; use `background_task` for long-running background work, services, parallelism, and cancellation or polling.
`background_task` has its own argument, process, timeout, output, and cancellation semantics.

## Tests

```text
10 running + 10 pending per cid; the 11th pending returns task_queue_full
another cid sees no tasks
cancel queued (no pid) and running (settles cancelled)
execution timeout settles timed_out
cwd outside the allowed roots is rejected
the inherited environment keeps user paths and drops an unknown secret
label is required and may repeat; batch groups tasks and filters an exact task_id
list returns every task in the batch without pagination
argv is not shell-interpreted
plan mode rejects create
the tool dispatches create / list / output / cancel
system-notice metadata survives the queue and history folding
a completed task exposes output and history; one notice carries the <<系统通知>> prefix and batch
the app registers the manager and the tool
```
