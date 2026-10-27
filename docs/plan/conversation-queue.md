**English** | [中文](conversation-queue.zh.md)

# Conversation message queue

## Goals

When a conversation is busy, user input and Agent deliveries enter the same pending queue. Input is not blocked, and no message or image is lost.

The queue provides:

- automatic delivery at turn end
- insertion at the next safe model pass
- edit and restore to the input box
- cancellation
- Agent origin marking

## Boundaries

- The queue is not part of conversation facts and does not write `data/sessions/*.raw`.
- A queue item produces an `INPUT_CLAIMED` fact only after delivery.
- The queue does not change the order in which the model context is assembled.
- The queue does not retain delivered messages.
- User input and Agent delivery share one queue with stable item IDs and one state machine; there is no separate pending-message path.

## Asset ownership

| Asset | Owner |
|---|---|
| Queue storage, state machine, attachments | `agent/mechanisms/conversation_queue.py` |
| Service registration | `SERVICE_CONVERSATION_QUEUE` in `agent/core/context.py` |
| Turn-end scheduling | `agent/shell/session/runner.py`, `agent/shell/session/queue.py` |
| Safe insertion point injection | `agent/core/modules/queued_input_mod.py` |
| Input facts | `agent/core/modules/input_mod.py` |
| HTTP endpoints | `agent/shell/web/web_routes.py`, `agent/shell/web/web_chat.py`, `agent/shell/web/web_api.py` |
| SSE contract | `agent/core/event_name.py`, `agent/shell/classic_adapter/` |
| UI | `agent/shell/web/web_assets/classic/js/chat/queue.js`, `agent/shell/web/web_assets/classic/css/chat-queue.css`, `agent/shell/web/web_assets/classic/agent-ui.html` |
| Queue data | `data/queues/<cid>/` |

`MeshState` retains:

- Agent registry
- run placeholder and active set
- session existence checks
- atomic delivery through `submit`

Queue storage and queue state belong to `ConversationQueue`.

## Data model

```text
id              queue item ID
cid             conversation ID
origin          user | agent | system
content         text
attachments     attachment metadata
sender          Agent origin metadata
delivery        after_turn | next_pass
state           queued | inserting | claimed | draft
seq             queue order
created_at
updated_at
payload         internal metadata: resume result, notice kind, source, ID, batch
```

A queue item does not carry a revision. Each conversation has one queue revision, stored in `data/queues/<cid>/revision` and incremented on every queue change.

`sender`:

```text
cid
name
thread_id
requires_reply
```

`attachments`:

```text
id
mime
size
width
height
```

The blob path is internal and is not returned to the frontend.

Background-task notices and resume results are internal `system` items. They do not appear in the queue snapshot but keep their place in delivery order.

## State machine

```text
queued
  ├─ insert send → inserting
  ├─ edit → draft
  └─ cancel → removed

inserting
  ├─ safe insertion point → claimed
  ├─ turn ends early → stays inserting
  └─ cancel → removed

draft
  ├─ resubmit → new queued item
  └─ discard → removed

claimed
  ├─ input fact emitted (insert) → removed
  ├─ turn completes (after_turn) → removed
  └─ process restart → queued
```

A queue row in `inserting` is shown as Inserted; edit, cancel, and insert again are disabled.

Rules:

- After `claimed`, edit and cancel return 409.
- Cancel removes the item from the queue view immediately.
- A delivered item is removed from the queue.
- A persistence failure returns an error and leaves the input box unchanged.
- On process restart, items persisted as `claimed` return to `queued`; `inserting` items stay `inserting` and are delivered at the next safe point.

## Image rules

The queue has no separate image cap.

The input box, `/api/chat/send`, and the queue use one attachment rule:

```text
agent/core/input_attachments.py
  MAX_IMAGES
  IMAGE_MIMES
  normalize_images()
```

- The input box and the queue accept the same number of images.
- The limit is defined by `MAX_IMAGES`; the UI reads it from `/health` as `max_images`.
- The server request body limit is controlled by `MAX_BODY_BYTES`.
- The queue stores only attachments that passed input validation.
- The queue adds no cap or filter beyond the shared attachment rule.
- Attachments that pass validation are stored in full and are not dropped silently.

Attachment storage:

```text
data/queues/<cid>/
  revision
  <item_id>/
    meta.json
    <attachment_id>
```

`meta.json` stores the item and its attachment metadata; each original image is stored as a separate blob named `a0`, `a1`, and so on.

The queue list returns attachment metadata, not full base64 images. Recall reads the blobs and returns them as `data_base64` for the input box.

## Delivery policy

### Idle conversation

`POST /api/chat/send` starts a new turn directly. The message is not queued.

### Busy conversation

```text
POST /api/chat/send
→ enqueue, delivery=after_turn
→ return queue_item
→ clear the input box
→ add a queue row
```

At turn end:

```text
the current turn ends
→ SessionRunner still holds the run placeholder
→ ConversationQueue claims the first after_turn item
→ renew the placeholder for the next turn
→ start a new turn
→ remove the item after that turn completes
```

The queue takes priority over goal and autonomous continuation.

`after_turn` delivery consumes one item per turn and does not merge messages.

### Stop

Stop ends only the current turn:

- it does not consume the queue automatically
- queue items keep their current state
- the user can still insert, edit, and cancel
- only the next explicit send or insert continues

## Insertion send

The insertion point is the next safe model pass:

```text
the current model stream ends
→ every tool in the current batch finishes
→ tool results are persisted
→ the next pass starts
→ QueuedInputModule
→ CompressModule
→ ModelModule
```

Insertion never happens:

- during model streaming
- during tool execution
- between a tool_call and its tool_result

When the conversation is idle, an insert starts a new turn immediately; the item is that turn's input.

At one safe point, all items in `inserting` are claimed in queue order and each emits its own `INPUT_CLAIMED` fact.

An item that is `inserting` when the turn ends early stays `inserting`; it is delivered at the next safe point.

Interrupting the current turn immediately is a stop followed by a new turn, not queue insertion.

## Agent messages

When the target conversation is busy, an Agent message enters the queue:

```text
origin=agent
sender={cid,name,thread_id,requires_reply}
delivery=after_turn
```

When the target is idle, the message starts a turn directly and is not queued.

A queued subagent peer message is marked `inserting` (`delivery=next_pass`) and is delivered at the next safe point.

Display:

```text
[#1] [🤖 AgentName] [message] [Insert] [Edit] [Cancel]
```

After delivery it is rendered as an Agent message, not as an ordinary user message.

Ordinary Agent messages are not injected into the current turn. Queued subagent peer messages use the next safe point.

## Edit and origin preservation

Editing a user message:

1. recall the queue item
2. change its state to `draft` and remove it from the queue view
3. restore text and images to the input box
4. resubmit to create a new queue item

Editing an Agent message:

1. recall returns `origin=agent`, sender metadata, and `draft_queue_id`
2. the input box shows the origin marker
3. resubmit carries `draft_queue_id`
4. the server verifies that the draft belongs to the conversation
5. the new queue item keeps `origin=agent` and the sender

The browser cannot declare Agent identity by itself.

## API

```text
POST   /api/chat/send
GET    /api/chat/queue?conversation_id=...
POST   /api/chat/queue/<item_id>/insert
POST   /api/chat/queue/<item_id>/recall
DELETE /api/chat/queue/<item_id>
```

Queue operations carry `conversation_id`: query for GET and DELETE, body for POST.

Busy `POST /api/chat/send` response:

```json
{
  "ok": true,
  "conversation_id": "cid",
  "run_id": "",
  "queued": true,
  "queue_item": {"id": "<item_id>", "position": 1},
  "revision": 12
}
```

`recall` response:

```json
{
  "ok": true,
  "draft_queue_id": "<item_id>",
  "item": {
    "id": "<item_id>",
    "origin": "user",
    "content": "text",
    "sender": null,
    "attachments": [
      {"mime": "image/png", "data_base64": "..."}
    ]
  },
  "revision": 12
}
```

Queue snapshot:

```json
{
  "conversation_id": "cid",
  "revision": 12,
  "items": [
    {
      "id": "<item_id>",
      "position": 1,
      "origin": "user",
      "content": "text",
      "state": "queued",
      "delivery": "after_turn",
      "attachments": [
        {"id": "a0", "mime": "image/png", "size": 1234}
      ]
    }
  ]
}
```

SSE:

```text
queue_updated
```

The event carries the conversation snapshot and revision. The frontend replaces its queue with that snapshot; it does not apply increments.

## UI

Position: above the input box on the left, half the input width. The voice playback bar sits below the queue.

User message:

```text
[#1] [Handle xxxx for me] [Insert] [Edit] [Cancel]
```

Agent message:

```text
[#1] [🤖 AgentName] [Coordination message...] [Insert] [Edit] [Cancel]
```

Behavior:

- a busy conversation does not block sending
- in the queued path, the input box is cleared only after a successful response
- queue items are shown by `position`
- an `inserting` row cannot be clicked again
- edit restores text, images, and the origin marker
- cancel removes the row immediately
- an empty queue hides itself
- each conversation tab has its own queue
- a refresh restores the queue from the snapshot

## Input facts

User messages and Agent messages use the same input fact shape:

```json
{
  "content": "text",
  "attachments": [],
  "_sender": "agent-cid",
  "_sender_name": "Agent Name"
}
```

A user message has no `_sender`.

Both input paths emit this shape and pass attachments through `with_attachment_ids()`; any field added to one path is added to the other.

## Tests

### Queue mechanism

- enqueue while busy; direct send while idle
- persistence failure leaves the input intact
- queue order and revision
- image save and restore
- no queue-specific image cap; same rule as the input box
- edit and cancel state machine
- claimed rejects edit and cancel
- restart recovery: claimed returns to queued, inserting is preserved
- stop does not deliver automatically

### Turn scheduling

- one after_turn message per turn
- goal and autonomous continuation do not preempt the queue
- insertion runs after the tool batch and before the next model request
- an inserting item stays inserting when the turn ends early
- conversations are isolated from each other
- Agent messages keep their origin on delivery

### API and UI

- a busy send returns queued
- queue snapshot and revision
- recall returns text, images, and origin
- insert takes effect
- cancel takes effect
- SSE replaces the snapshot
- edit then send preserves Agent origin
- image preview is restored

### Regression

- `session_send`, `session_multisend`, `session_broadcast`
- `requires_reply`
- confirmation and resume turns
- stop
- goal and autonomous continuation
- conversation history
