# Subagent

## 1. Overview

This module is described below.

## 2. Flowchart

```text
build_app(store=None)
  → SubagentManager is not created
  → subagent / subagent_send are not registered

build_app(store=...)
  → SubagentManager is created
  → parent view: subagent
  → child view: subagent_send
  → SERVICE_SUBAGENTS is registered
  → App.dispose() calls shutdown
```

## 3. Slots

### Exposed

| Slot path | Capability | Key attributes | Replacement / override |
|---|---|---|---|
| `app/host/services/subagents` | host service | owner=module; assembled by SlotTree; failure follows master | Boot-tree nodes are overlaid by path; runtime read-only slots are not replaced |
| `app/boot/tools/subagent` | tool or executor | owner=module; assembled by SlotTree; failure follows master | Boot-tree nodes are overlaid by path; runtime read-only slots are not replaced |
| `backend/tools/subagents/visibility/*` | tool or executor | owner=plugin; declared path; removed on unload | Override at the same path with `replace=true`; restore on unload |
### Required

| Dependency path | Capability | Provider | Why |
|---|---|---|---|
| `app/host/services/store` | host service | host | must be ready before assembly; unavailable propagates as startup/request failure |
| `app/host/services/mesh` | host service | host | must be ready before assembly; unavailable propagates as startup/request failure |
| `app/host/services/queue` | host service | host | must be ready before assembly; unavailable propagates as startup/request failure |
| `app/host/services/event_bus` | host service | host | must be ready before assembly; unavailable propagates as startup/request failure |

## 4. Slot capabilities

### Boundaries
```text
agent/subagent/
  models.py       data objects and errors
  batches.py      batch metadata
  repository.py   child sessions, batches, fork seeding
  lifecycle.py    create, start, status, list, result
  messaging.py    parent-child message delivery
  manager.py      public facade and completion notices
```

`agent/subagent` depends only on `agent/core` and `agent/mechanisms`.
`agent/app.py` assembles it; `agent/shell/web` calls it only through `SERVICE_SUBAGENTS` and does not hold the repository or batch files directly.

### Data ownership
```text
data/batches/<parent_cid>/<batch>.json
  batch metadata, subagent ids, labels, context

data/subagent/sessions/<child_id>.raw
  child session facts

data/subagent/sessions/<child_id>.raw.lock
  child session lock
```

`data/batches` is the only entry point for batch metadata.
Child sessions share the parent store's global sequence source; they do not appear in the main session list.

### Messages and completion
```text
Parent → child
  subagent.send
  → child busy: enqueue, mark inserting, then inject the backlog at the next safe insertion point
  → child idle: start a turn

Child → parent
  subagent_send
  → parent busy: enqueue, mark inserting, then inject the backlog at the next safe insertion point
  → parent idle: start a turn

Child turn ends
  → read the latest non-empty model_message after the most recent turn_started only
  → do not report a turn driven solely by system-notice inputs
  → report a normal task turn once even when notices were inserted during it
  → deliver a fixed notice when there is no model output
  → skip duplicate turn_ended callbacks and text already sent during that turn
```

Both directions use forced insertion when the target is busy; the send path has no non-inserting mode. `QueuedInputModule` claims inserting messages in bulk, and each keeps its own `input_claimed` fact.
Ordinary queued messages are still delivered at turn end.

### Tools
Parent tool:

```text
subagent
  create
  list
  status
  result
  send
```

Child tool:

```text
subagent_send
```

`create` requires `label`; a batch holds at most 10 subagents; `context` is `fork` or `fresh`.
`fork` copies only the parent's completed turns. `result` returns the child session's most recent non-empty model output and does not use status in place of the result.

## 5. Details

### 补充

Without a persistent store, the subagent tools are not provided.
`subagent` is only for parent sessions, and `subagent_send` is only for child sessions. `ToolRegistryView` filters the parent and child tool views; the tool implementations stay in the same registry.



### Failures and shutdown
```text
Batch creation failure: batch writes are atomic; a failed batch leaves no visible subagent
First-turn start failure: keep the subagent record and raise a retryable error
Child-session storage failure: record the failure; do not fabricate model output
Manager shutdown: unsubscribe events first, then flush child sessions
```

## 6. Further reading

| Topic | Document |
|---|---|
| Architecture | [architecture.md](../architecture.md) |
| Plugins | [plugins.md](plugins.md) |
