**English** | [中文](glossary.zh.md)

# Glossary

Some terms in the project are custom and have fixed meanings. This page is the **only place** where they are defined.

## Structure

**Module chain**
The kernel's behavioral structure. The host repeatedly runs a fixed sequence of modules, each implementing only `execute(ports) -> Outcome`. The order is `input → queued input insertion → compaction → model → tools`. See [Architecture](architecture.md).

**Composition root**
`agent/app.py`. The only file that references all five layers at once; it builds `AppContext` and registers services. It belongs to no layer.

**Dual track**
Two independent tracks: the decision chain and the event bus. The decision chain participates in control flow; the event bus only delivers notifications. See [Architecture](architecture.md).

**Ports**
`Ports`. The **only** path through which modules act on the outside world. Modules cannot obtain the context object, nor can they touch files, the network, or tool implementations directly.

## Data

**Fact**
Something that has happened and cannot be rewritten once persisted. Each fact is an event (`Event`), shaped as "type + payload".

**Fact stream**
The append-only log of all facts in a session, in occurrence order, one event per line, stored at `<data_root>/sessions/<cid>.raw`.

**Projection**
A live view of facts. The SSE stream shown in the UI is a projection, not a second source of truth.

**Contract**
A data object passed across layers, fixed in `core/`. Layers exchange only contract objects, never bare dicts.

**Round**
A round begins with a `user` message and includes the assistant and tool messages that follow it. Context retention, compaction, and boundaries operate on whole rounds.

**Chunk**
A named section of the context; the recent-memory chunk holds the conversation rounds. There are five chunks in a fixed order. See [Context management](subsystems/context.md).

**Turn**
All activity triggered by one input, until no module requests another pass or the module chain terminates.

**Pass**
One complete run of the module chain from start to finish. A turn usually contains several passes.

## Control

**Outcome**
The only shape of a module's execution result, carrying **control signals only**: `ok` / `next` / `halt` / `suspend` / `stopped`. Data does not travel through it.

**Continuation**
`Outcome.next` means "this pass is done, but another pass is needed". One of the host's exit conditions is that no module requests continuation.

**Suspend**
`Outcome.suspend` means "external input is required; control returns to the caller". It does not block the thread.

**Gate**
An interception rule on the decision chain that can block the main flow. Event-bus subscribers cannot block the main flow and have no defined execution order, so gates do not use the event bus.

**Write four-step protocol**
The strictest rule for write tools: preview → confirm → commit with a `confirm_id` → re-read. See [Tools](subsystems/tools.md).

**confirm_id**
The identifier for one write preview. A commit uses only this id; the gate restores the write arguments from the snapshot, and the model does not resend them. The id is evicted and becomes invalid when the same path is previewed again or the number of uncommitted snapshots reaches its limit.

**review**
A prerequisite for writing. The model must provide a conclusion grounded in an actual review and supporting verification evidence before a preview is unlocked.

## Context

**Retention window**
The preferred range of trailing user rounds kept verbatim. Its width is set by `full_user_rounds`; compaction may still consume these rounds when no earlier history can be reduced.

**Summary**
Text distilled from history rounds that have already been compacted, stored in the "memory file" chunk.

**Compaction**
The act of condensing over-limit rounds into a summary. It is triggered when the estimated token count exceeds the threshold.

**Estimated tokens**
An estimate rather than an exact count, derived from character types and message structure. Images use a fixed value.

## Sessions

**Session id (cid)**
The session identifier. It must match `^[A-Za-z0-9_-]{8,128}$`; new sessions use UUID4. It also serves as the on-disk file name, so this validation is a path-traversal boundary.

**Conversation queue**
A session-level staging area for messages. When a session is busy, user and agent messages are queued; after the turn ends they are delivered one per turn. Messages marked for insertion enter the context at the next safe model pass.

**Mesh**
A mechanism that lets multiple sessions deliver messages to one another: a roster, run claims, and atomic delivery based on busy/idle state.

**Runtime registry**
An on-disk record that answers whether a session's turn is running. A run counts as active only when the heartbeat has not expired **and** the recorded process is still alive.

**Cross-process lock**
An exclusive lock per log file. For a session, "note the offset → append → roll back" is a read-modify-write sequence; an in-process lock cannot stop another process, and concurrent writes silently lose lines.

## Shell

**Adapter layer**
`agent/shell/classic_adapter/`. Performs bidirectional translation between the classic UI and the kernel; the preferred place to handle behavioral differences.

**Inline bundling**
Inlines all UI assets into a single HTML file, so the running page makes no additional requests.

**SSE**
The one-way event channel between the UI and the server. Each frame carries a session id and sequence number; reconnection resumes from the sequence.

**Visible root**
The directory scope visible to the file viewer and path completion, specified by `--fs-root`.
