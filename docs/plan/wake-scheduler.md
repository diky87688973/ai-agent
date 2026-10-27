**English** | [中文](wake-scheduler.zh.md)

# Wake scheduler overview

Status: minimal implementation; single-process process lock, single-thread scheduling, JSON persistence, delivery reuses `MeshState.submit`.

## Goals

After the model registers a wake job, it ends the current turn immediately. When the job is due, the host scheduler delivers the wake message to the target conversation.
A wake occupies no model, command, or conversation thread, and it does not block the message queue.

## Boundaries

```text
model tool: register, cancel, and query only
host scheduler: timing, persistence, and due delivery
conversation queue: receive wake messages and decide whether to start a turn or queue
command tools: do not wait
```

Prohibited:

```text
time.sleep inside a tool
one sleeping thread per job
using run_command to execute sleep instead of waking
the model holding a turn open to wait
```

## Components

```text
WakeScheduler
  single-threaded timer
  nearest due job
  cancellation and shutdown

WakeJobStore
  jobs.json persistence
  startup recovery
  state machine

Delivery
  convert due jobs into wake messages
  reuse MeshState.submit (idle start / busy queue)
  queue dedupe by wake_job_id
```

## Job fields

```text
job_id
target_cid
owner_cid
due_at
payload
status
created_at
updated_at
last_error
```

```text
status:
  scheduled
  claimed
  delivered
  canceled
  failed
```

## Tool contract

```text
task_sleep
  seconds
  reminder
  → returns job_id without blocking

task_schedule
  at
  reminder
  → returns job_id without blocking

task_wake_cancel
  job_id

task_wake_list
  target_cid
```

Time parameters must be validated explicitly:

```text
delay must be greater than 0
an absolute time must include a time zone or be interpreted in the host's local time zone
a time in the past must not be silently changed to immediate execution
```

## Due delivery

```text
scheduler reaches a due time
  ↓
atomically mark as claimed
  ↓
assemble wake message
  ↓
target idle: start a new turn
target busy: enter the target queue
  ↓
mark as delivered
```

Each wake message remains a separate item and is never merged into another.
When the target is busy, multiple wakes are delivered separately at the next safe model pass.

## Persistence

```text
persist jobs to disk
atomic writes
load at startup
an overdue job is delivered only once on recovery
job_id is idempotent
corrupt jobs are retained for diagnostics and do not block other jobs
```

If the target conversation does not exist, has been deleted, or its owning parent conversation is no longer valid, the job is marked failed and is not retried indefinitely.

## Concurrency

```text
exactly one scheduler thread
no thread created per job
the timer waits only for the nearest due time
delivery does not hold the conversation lock
races between cancellation and expiry are resolved by the state machine
```

## Restart

```text
load unfinished jobs
overdue and undelivered: deliver once on recovery
already delivered: do not deliver again
canceled: do not revive
```

## Relationship to the existing queue

```text
wakes are independent messages with a system origin
regular messages are still delivered at turn end
inserted messages are still injected as a batch at the next safe model pass
wakes do not change the independent-item semantics of inserted messages
```

## Failures and diagnostics

```text
invalid job time
target conversation does not exist
target queue rejects the message
job file is corrupt
unfinished jobs remain when the scheduler shuts down
```

Each failure above must record the job ID, target cid, and error reason; none may be dropped silently.

## Acceptance

```text
the tool returns immediately after registration
the model turn has ended before the job is due
the target conversation is woken when the job is due
a busy target does not block other messages
multiple wakes become separate messages
a job that is not yet due remains active after restart
a delivered job is not delivered again after restart
a canceled job is not delivered
```

## Non-goals

```text
no cron-style recurring jobs
no cross-process scheduling
no model-initiated blocking wait
not a replacement for the regular conversation queue
```
