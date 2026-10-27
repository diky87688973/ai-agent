**English** | [中文](subagent.zh.md)

# Subagent capability

## Goal

Add persistent multi-turn subagents inside the existing conversation system.

Core capabilities:

```text
parent session creates a subagent
subagent runs an independent session
bidirectional parent-child messages
batch-based discovery
background list and detail tab
survives application restart
```

Scope boundaries:

```text
multi-turn subagents only
no one-shot subagents
no nested subagents
no sibling messaging
no hot-plug subagent plugins
```

## Decisions

| Item | Decision |
|---|---|
| Batch ownership | The batch belongs to the current parent session. |
| No batch supplied | Create a batch automatically and return it. |
| Batch limit | 10 subagents per batch. |
| `fork` | Copy the stored parent events through the last completed turn; the in-progress turn is excluded. |
| `fresh` | Empty history; the child uses the shared model policy and working directory, with the child role tool view. |
| Restart | Child sessions are kept; status returns to idle; no turn is replayed. |
| Messaging | Parent to child and child to parent; child to child is rejected; parent and child remain reachable across batches. |
| Forced insert | Insert at the next safe point of the current turn; no option to disable insertion. |
| Images | Reuse the existing attachment and image input path. |
| Storage | Child session facts live in `data/subagent/sessions`; other data stays under the `data` root. |
| Key | Share `data/cache/session_encryption.key` with the main session. |
| UI | Create silently; the child appears in the subagent list; a tab opens only from the list. |
| Plugin boundary | The lifecycle is owned by a core service, not implemented as a plugin. |

## Design choices

Adopted:

```text
local persistent multi-turn subagents
explicit batch grouping
independent child session storage
lifecycle owned by a core service
fork copies completed turns only
parent holds child membership
```

Not adopted:

```text
one-shot subagents
nested subagents
child sessions in the main session list
a hot-pluggable owner for a running lifecycle
```

Fork stops at the last `turn_ended`, so a child never sees a partial turn from the parent.

## Domain model

### Subagent

```text
child_id       child session id
parent_cid     parent session id
batch          batch id
label          task title; required
context        fork / fresh
created_at     creation time
```

Status is not persisted:

```text
busy = the child session has a running turn
idle = no running turn
```

### Batch

```text
batch          sb-<random string>
parent_cid     owning parent session
children       subagent records
created_at     creation time
```

A batch is not written to a global registry.
Each parent session has one directory; each batch is one JSON file; one file holds at most 10 subagent records.

Constraints:

```text
a batch belongs to exactly one parent session
a parent session may have several batches
a batch holds at most 10 subagents
children of one parent may be spread across batches
```

### Parent-child relation

```text
parent → any of its own subagents
child → its direct parent session
child → child: rejected
child → another parent session: rejected
```

Cross-batch membership does not affect parent-child messaging.
The child-side send path fixes the target to the direct parent; no target parameter is exposed.

## Architecture

```text
agent/subagent/
  manager.py      facade: composes the boundaries and child turn-end notices
  lifecycle.py    create, first-turn start, status, listing, result
  messaging.py    parent-child messages, forced insert, images
  repository.py   child session paths, batch records, fork seeding, history/result reads
  batches.py      batch metadata file reads and writes
  seed.py         fork prefix from completed turns
  models.py       dataclasses and errors

agent/capabilities/builtin/subagent_tools.py
  parent tool: subagent
  child tool: subagent_send

agent/shell/web/web_subagents.py
  list, history, send actions

agent/shell/web/web_assets/classic/js/chat/subagents.js
  subagent list and tab opening

agent/shell/web/web_assets/classic/css/subagents.css
  right-side stacked panel styles
```

Responsibilities:

| Module | Sole responsibility | Not responsible for |
|---|---|---|
| `manager.py` | Facade, public use cases, child turn-end completion notices | file I/O, running-state computation |
| `lifecycle.py` | Create, first-turn start, status, listing, result | direct batch file I/O |
| `messaging.py` | Parent-child messages, forced insert, images | child session management |
| `repository.py` | Child session paths, batch records, fork seeding, history/result reads | starting turns, sending messages |
| `batches.py` | Atomic batch file reads and writes | running-state decisions |
| `seed.py` | Fork prefix construction | paths and permissions |

Dependency direction:

```text
app assembly
  → SubagentManager (facade)
    → SubagentRepository → BatchStore / SessionStore / seed
    → SubagentLifecycle → SubagentRepository / SubagentMessenger
    → SubagentMessenger → SubagentRepository / MeshState / ConversationQueue
    → EventBus (turn started / turn ended)
```

Tool visibility:

```text
parent view: all registered tools except subagent_send and the session tools
session tools: session_send / session_multisend / session_broadcast / session_create / session_list
child view: all registered tools except subagent, the session tools, and tools that their owning plugin hides from subagents
child keeps: subagent_send
parent keeps: subagent
```

Service registration:

```text
SERVICE_SUBAGENTS
```

`build_app()` registers it with the background task manager and `SessionRunner`; `SubagentManager` receives `MeshState` and the conversation queue.
Without a parent store, the manager and both tools are not created.

## Session storage

### Directory

```text
data/
  sessions/
    <cid>.raw                     main session facts
  cache/
    session_encryption.key        shared by parent and child sessions
  batches/
    <parent_cid>/
      <batch_id>.json             subagent batch metadata, at most 10 entries
  subagent/
    sessions/
      <child_id>.raw              child session facts
```

Ownership:

| Asset | Owner | Note |
|---|---|---|
| Child session facts | `data/subagent/sessions/` | The only session data under the subagent directory. |
| Batch metadata | `data/batches/` | Belongs to the parent session, not the child. |
| Pending messages | `data/queues/` | Existing queue, keyed by child cid. |
| Agent identity | `data/mesh/agents.json` | Existing collaboration mesh. |
| Encryption key | `data/cache/session_encryption.key` | Shared by parent and child. |
| Tool output | Project directory or existing `data/` location | No separate path for subagents. |

Constraints:

```text
data/subagent/sessions holds child session facts only
data/batches is split by parent session and batch; a batch belongs to the parent, not the child session directory
there is no global registry.json
the parent title, log files, attachment store, and queue are not duplicated
files produced by child tools stay in the project directory or their existing data/ location
```

A batch file holds at most 10 subagent records. Its size is bounded by the child cap and the 120-character label cap.
A parent's batch count grows as files in its directory; no single append-only file accumulates every batch.

Batch file:

```json
{
  "schema": 1,
  "batch": "sb-...",
  "parent_cid": "...",
  "created_at": 0,
  "children": [
    {
      "child_id": "...",
      "label": "task title",
      "context": "fork",
      "created_at": 0
    }
  ]
}
```

Write path:

```text
temp file + os.replace
one in-process lock serializes batch writes
a batch file rewrites only that batch's records (up to 10)
```

The child's first `subagent/created` event also records:

```text
parent_cid
batch
label
context
```

The batch file is the authority for membership. A missing batch file is not rebuilt from child session metadata; the child remains on disk but is not listed.

### SessionStore configuration

`SessionStore` resolves session facts to `data_root/sessions/<cid>.raw` and the key to `data_root/cache/session_encryption.key` by default.

Optional arguments:

```text
sessions_dir     custom session directory
key_path         custom key path
sequence_source  external sequence allocator
scan_dirs        additional directories to scan
```

`add_scan_dir(path)` adds a scan directory after construction.

Child store:

```text
sessions_dir = data/subagent/sessions
key_path = parent store key path
sequence_source = parent store
```

Parent store scan:

```text
data/sessions
data/subagent/sessions
```

This keeps the SSE global `seq` unique.

### Session history routing

Main session list:

```text
SessionActions.sessions()
  scans data/sessions only
  does not read data/subagent
```

Child history:

```text
GET /api/subagents/history?conversation_id=<parent>&child_id=<child>
  resolves the child store through SubagentManager
  returns the child session history
```

An unknown `child_id` returns 404; a parent mismatch returns 403.

## Execution flow

### Create

Parent tool call:

```json
{
  "action": "create",
  "prompt": "task content",
  "batch": "optional; the batch id returned earlier",
  "label": "required; title shown in the UI",
  "context": "fork",
  "images": []
}
```

Flow:

```text
validate the parent id; reject a subagent caller
validate label: non-empty, at most 120 characters
resolve or create the batch; validate ownership and capacity
generate child_id
seed the child session facts for the context
add the child to the batch file
register the child in MeshState
start the first prompt
return ok + batch + child_id + label + status + queued
do not open a UI tab
```

`label` is required and is the display title in the UI list and the child tab; a missing or blank label rejects creation.

`prompt` is the first task. Creation immediately starts the child session with it; status becomes busy and the user does not send again.
If the batch file cannot be written, no first turn starts. If the first turn fails to start, the child and batch records are kept, the call raises a retryable error, and the child is idle.

Response:

```json
{
  "ok": true,
  "batch": "sb-...",
  "child_id": "...",
  "label": "task title",
  "status": "busy",
  "queued": false
}
```

### Fork seeding

```text
append subagent/created with parent_cid, batch, label, context
read the parent events
find the last turn_ended
take the prefix through that event
drop subagent/* events from the prefix
append the prefix to the child store
allocate new global seq values
```

The child receives one `subagent/created` event; no additional fork marker is written.

Parent live state is not copied:

```text
the parent's in-progress turn
the parent's pending queue
the parent's pending confirmation state
the parent's UI state
```

With no completed turn, seeding falls back to `fresh`.

### Fresh

```text
no copied parent events; the created marker is the only initial fact
the same system prompt assembly, with role-specific tool and prompt-tail visibility
the model resolved for the child conversation from the shared policy
the child role tool view
the same working directory
```

### Activation

Reuse:

```text
MeshState.submit
SessionRunner
ConversationQueue
RunRegistry
```

`SessionRunner` resolves a store per conversation:

```text
store_for(cid)
  main session → main store
  subagent → child store
```

`App.session(..., store=...)` accepts an explicit child store.
Tools, context, event bus, queue, and session contexts share the same assembly.

## Messaging

### Parent to child

Parent tool call:

```json
{
  "action": "send",
  "child_id": "...",
  "msg": "message",
  "images": []
}
```

Behavior:

```text
validate that the child belongs to the current parent
idle: start the child session
busy: enqueue for the child
forced insert: mark the queue item inserting; inject at the next safe point
batch injection: every backlogged inserting item, including system notices, Agent messages, and user inserts
each message becomes an independent input fact; messages are not merged
return ok, target_id, queued, inserted, run_id
```

Parent-child sends use forced insertion when the target is busy; the send path offers no non-inserting mode. An idle target starts a turn directly.
When the target is busy, the message enters its queue; at the next safe insertion point `QueuedInputModule` injects all backlogged inserting messages.

### Child to parent

Child tool call:

```json
{
  "msg": "message",
  "images": []
}
```

The target is always the direct parent; no target parameter is exposed.
Behavior is symmetric with parent to child:

```text
parent idle: start the parent session
parent busy: enqueue for the parent
forced insert into the parent's current turn
turn end: the latest non-empty model output in the child session is delivered to the parent inbox
```

### Message source

The submitted message payload carries:

```text
_sender             sender cid
_sender_name        subagent label or parent name
_sender_role        subagent / parent
_agent_peer_message true
_message_kind       peer
```

The queued/input path keeps the sender cid and sender name.

Reuse the existing `peer_message` event and `addPeerMessage()`:

```text
the inbox shows the source avatar, source name, and short conversation id
the bubble style matches session_send
```

### Images

Reuse:

```text
normalize_images
ConversationQueue attachments
Engine.start_turn(attachments=...)
```

Both directions support images.
A message with images and no text is valid.

## Status and listing

### Status

```text
busy = mesh.is_running(child_id)
idle = otherwise
```

A queued message with no running turn leaves status idle; the list also returns `pending`.
No `stopped` state exists.

### List

Parent query:

```text
GET /api/subagents?conversation_id=<parent>&batch=<optional>
```

Response:

```json
{
  "ok": true,
  "batches": [
    {
      "batch": "sb-...",
      "created_at": 0,
      "children": [
        {
          "child_id": "...",
          "label": "task title",
          "context": "fork",
          "created_at": 0,
          "status": "busy",
          "pending": 0
        }
      ]
    }
  ],
  "counts": {"busy": 0, "idle": 1}
}
```

Ordering:

```text
batches newest first by created_at
children in batch creation order
no status-based reordering
```

### Restart recovery

At construction:

```text
read every batch file under data/batches/
index each child by child_id with its parent and batch
start no turns
do not open the child session file
```

Status is derived from the run registry, so children are idle after a restart.

Restart does not inspect the child's last event:

```text
keep the stored events unchanged
append no interrupted terminator
do not fabricate model output
```

The next message starts a new turn; `SessionRunner` loads the child store and runs it.

## Tools and API

### Parent tool

```text
subagent
  action=create
  action=list
  action=status
  action=result
  action=send
```

Create parameters:

```text
prompt
batch
label       required; UI list and tab title; non-empty; at most 120 characters
context=fork|fresh
images
```

List parameters:

```text
batch
```

Send parameters:

```text
child_id
msg
images
```

`status` and `result` take `child_id`.

### Child tool

```text
subagent_send
  msg
  images
```

The target is always the parent.
The child tool view excludes `subagent`, so a child cannot create another child; the lifecycle also rejects a create call whose caller is a subagent.

### HTTP

```text
GET  /api/subagents
GET  /api/subagents/history
POST /api/subagents/send
```

`POST /api/subagents/send` serves only input from the UI child tab.
Tool calls use `SubagentManager` and do not depend on HTTP.

## UI

### Layout

```text
[left control column 50%] [right control column 50%]
[inbox queue]             [subagent panel]
[queue draft]             [background task panel]
[AI speech]
[input --------------------------------------------------]
```

Right column:

```text
.composer-right-col
  .subagent-panel
  .bg-task-panel
```

Left column:

```text
.composer-left-col
  #chatQueue
  #queueDraft
  #aiSpeakSlot
```

### Subagent panel

Collapsed header:

```text
子智能体
[0 已完成] [0 进行中]
```

Expanded rows:

```text
[status dot] [batch id] [label] [打开会话]
```

Clicking a row or the open-session button:

```text
opens the child session tab
does not switch the main session list
does not open a newly created subagent automatically
```

Panel polling:

```text
read the parent list every 3 seconds
clear the timer on window unload
```

The panel is hidden when the parent has no children, and while a child tab is active.
The dynamic list uses event delegation; rows are not bound individually.

### Child session tab

Tab metadata:

```text
subagent: true
parentCid
batch
title
```

Tab behavior:

```text
accepts input
sends through forced insertion when the child is busy
accepts images
closing the tab releases UI run state only; it does not delete the child session
a busy tab cannot be closed
the child does not appear in the session list
```

### Inbox source

Reuse the peer bubble:

```text
source name = subagent label
source short id = first 8 characters of child_id
```

The sender role is carried in the message payload but is not rendered in the inbox bubble.

## Plugin boundary

The subagent lifecycle is not a hot-pluggable plugin.

Reasons:

```text
a subagent may be running a long task
unloading a plugin cannot revoke an accepted run
hot plugging would leave creation, messaging, and status queries half-available
lifecycle, capacity, permissions, and persistence must be owned by one core service
```

Core:

```text
SubagentManager
batch file storage
session store routing
MeshState / SessionRunner integration
fork seeding
permissions and status
```

May be pluggable:

```text
external providers (ACP / remote Agent)
optional tool schema extensions
UI panels
```

An external execution backend may be unloaded; unloading only blocks new creation, and accepted runs must finish. A plugin cannot own the lifecycle of a running subagent.

## Test scope

### Unit

```text
batch creation, automatic batch, 10-subagent cap
a batch belongs to one parent session
fork takes completed turns only
fresh has empty history
busy/idle status
parent → child / child → parent
sibling rejection
parent-child across batches allowed
forced insert marks the item inserting
image messages
restart restores idle
child sessions do not enter the main session list
sequence values do not collide
```

### Web

```text
list polling
collapse/expand
opening a child tab
child tab input
inbox source display
no one-shot mode
```

### Acceptance

```text
a parent creates two subagents in one batch
both subagents run
the parent receives messages from both sources
a child-to-child send is rejected
after a restart both subagents are listed and idle
the parent continues to message the subagents
```

## Risks

| Risk | Handling |
|---|---|
| Global `seq` collision | Shared sequence allocator; both session directories are scanned. |
| Child sessions pollute the main list | The main list scans `data/sessions` only. |
| Key split | Parent and child share the parent store key path. |
| Recursive subagents | The child view excludes `subagent`; the lifecycle rejects a subagent caller. |
| Sibling privilege | Messages are validated by the parent-child relation; the child tool has no target parameter. |
| Hot plug interrupts a run | The lifecycle is owned by a core service. |
| Restart leaves a half turn | No automatic replay; stored facts are kept and no model output is synthesized. |
| Closing a tab deletes data | Closing releases UI state only and does not delete `.raw`. |
