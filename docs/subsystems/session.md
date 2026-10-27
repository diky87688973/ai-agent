**English** | [中文](session.zh.md)

# Session storage and collaboration

`agent/mechanisms/session_store.py` persists session facts. `agent/mechanisms/run_registry.py` tracks running turns, `agent/mechanisms/mesh.py` handles cross-session delivery, `agent/mechanisms/session_title.py` generates titles, `agent/mechanisms/live_state.py` holds per-session state, and `agent/mechanisms/file_safety.py` provides versioned backups and a recycle area.

## Fact log

### Layout

```
<data_root>/sessions/<cid>.raw      one log per session; JSONL, one event per line
<data_root>/cache/session_encryption.key   encryption key (created in local mode)
```

A session id must match `^[A-Za-z0-9_-]{8,128}$`; anything else is rejected. This check is the first boundary against path traversal.

### Append-only

The log is an **append-only fact stream**: every event appends one line, and existing lines are not rewritten.

The structural guarantee "model-visible ⟺ recorded" is enforced here: all filtering, cleanup, and formatting must happen **before** the write; a persisted row is never rewritten.

### Row format

```json
{"t":"assistant_delta","d":{"text":"好"},"s":226310}
```

Only what the disk needs is written; anything recoverable elsewhere is omitted. Most rows in a session log are streaming deltas with only a few characters of payload, so key names and redundant fields are multiplied by the number of rows:

| Key | Meaning |
|---|---|
| `t` | event type |
| `d` | event payload |
| `s` | global storage coordinate. `emit` stamps `_seq` into the payload when the event is produced; at write time it is lifted to top-level `s` and removed from `d`, so each row carries one copy |
| (none) | `conversation_id` is not persisted: the file name is the session id (`<cid>.raw`), and the reader already has it |

`s` cannot be omitted: SSE `id:` lines use it. On reconnect the browser sends it back through `Last-Event-ID`, and the server resumes from that position (see `cursor_of` / `replay_after`).

`s` is drawn from a counter that is shared across sessions and never reset, so a session's first coordinate is the value the global counter had reached. Coordinates are not guaranteed contiguous: events take a number when they are produced, and numbers for events that never reach disk are skipped. A cursor requires monotonic uniqueness, not continuity.

On read, both are restored (`event_from_obj`): the coordinate comes from `s`, and `conversation_id` is filled in from the session file name. Events in memory always carry `conversation_id`; SSE uses it to route frames to the correct session page.

### Sequence numbers

`allocate_seq(count)` reserves a contiguous block of coordinates; `_observe(seq)` records the highest coordinate seen. Consumers use the coordinate to decide where to continue; SSE reconnects rely on it. The allocator seeds from the largest coordinate already on disk before its first allocation.

### Encryption

Two modes:

| Mode | Behavior |
|---|---|
| `none` | plaintext rows |
| `local` | each row is encrypted into its own JSON envelope; standard-library encrypt-then-MAC with HMAC-SHA256 |

Per-row encryption means an append does not rewrite or re-encrypt the whole log, and a damaged row does not destroy the rest.

Plaintext and encrypted rows can coexist; a row that cannot be decrypted or parsed is skipped.

`MAGIC = "__fan_agent_session_encrypted__"` identifies the envelope and is the on-disk format marker for encrypted logs; changing it makes those logs unreadable.

### Read tolerance

Malformed rows are skipped, a missing file returns an empty list, and rows that do not yield an event type are ignored. Because plaintext and encrypted rows are detected per row, a log stays readable regardless of which mode wrote each row.

## Cross-process lock

### Cross-process

The same-session "record offset → append → roll back" sequence is a read-modify-write. An in-process lock cannot exclude another process: concurrent writes to the same `.raw` lose rows silently, and the exit code is still 0.

Writes therefore take a per-file **cross-process** exclusive lock: `msvcrt.locking` on Windows and `fcntl.flock` on POSIX. Windows retries non-blocking attempts in a loop; POSIX takes a blocking `flock`.

### Semantics

| Case | Behavior |
|---|---|
| Lock acquired | write normally |
| Contention timeout (Windows polling path; default 30 s, adjustable with `AI_AGENT_LOCK_TIMEOUT`) | raises; the batch enters the retry queue; no fallback to an unlocked write |
| No lock mechanism on the platform | logs a warning and degrades to the in-process lock only; an environment limit, not contention |

On POSIX, `flock` blocks until the lock is available.

### Lock file

The lock is taken on the log path plus `.lock` (`<cid>.raw.lock`). The file is zero bytes and is never deleted: deleting it would race with another process that already has it open, producing a lock on a deleted file.

## Retry queue

Batches that fail to write (lock timeout, disk error) enter a retry queue; `flush_pending()` and `flush_all()` resubmit them later.

When a failed batch is queued again, `_pending_only_new()` filters by sequence against facts already queued or already on disk, so each fact is written once.

The queue is capped at `_PENDING_MAX_BATCHES = 64` batches per session; when it overflows, the oldest batch is dropped with a stderr warning.

## Run registry

`run_registry.py` answers one question: **whether a turn is running for this session**.

The answer must be queryable from the server so a page opened mid-turn can show the running state and the stop control.

| Implementation | Use |
|---|---|
| `InMemoryRunRegistry` | memory-only; single instance and tests; selected when no directory is supplied |
| `FileRunRegistry` | on disk (`<data_root>/mesh/runs/<cid>.json` in the default assembly); visible across instances |

`build_run_registry(directory)` selects the implementation: `None` gives the in-memory version.

Two conditions must both hold for "running":

1. the heartbeat is within its TTL (default 900 s);
2. the process recorded in the entry is still alive.

Reads during a run also renew the heartbeat (`running()` calls `touch`), subject to a minimum interval, so a long tool call is not mistaken for a finished turn.

The pid check closes the TTL window: after a process is killed, its heartbeat freezes at the last write and the file still looks fresh until the TTL expires (15 minutes by default); checking the pid detects it immediately.

### Process probe

Windows uses `ctypes` `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`:

| Result | Verdict |
|---|---|
| Valid handle | process exists → alive |
| `last_error == 87` (`ERROR_INVALID_PARAMETER`) | the pid is known not to exist → dead |
| Any other error | unknown → treated as alive |

`os.kill(pid, 0)` cannot be used: in a process without a console (Windows service, scheduled task, `pythonw`, detached start) it raises `OSError [WinError 87]` even for a live process. Treating that as dead disables both the concurrent-run guard and the stop control.

On non-Windows platforms the probe falls back to `os.kill`; only `ProcessLookupError` means definitely dead.

Unknown results are treated as alive and left to TTL expiry.

## Collaboration mesh

`MeshState` in `mesh.py` delivers messages between sessions.

| Capability | Behavior |
|---|---|
| Agent roster | registered agents and their metadata, persisted to `agents.json` in the mesh directory |
| Pending queue | user and agent messages wait while the target is busy or cannot be activated; persisted under `data/queues/<cid>/` |
| Atomic delivery | the busy check and the delivery decision happen under one lock |

Queue contents are held by `ConversationQueue`. After a turn the runner drains the queue; insertion requests enter context through `QueuedInputModule` before compaction. While a turn is paused on a tool (user confirmation, approval), the queue stays paused and no new turn starts. Busy state comes from the run registry, so the mesh and `/api/chat/ui-state` read the same source.

## Titles

`session_title.py` makes one model call with no tools. The input is the first user input plus the first model reply, each truncated; the output is cleaned to at most 18 characters and written to `<data_root>/titles/<cid>.title`.

On failure (no provider, exception, empty text, placeholder result) the title falls back to a prefix of the first user input (empty when there is none) and does not block any flow. Titles are a derived cache and can be regenerated, so they are stored separately from session facts.

## Live state

`LiveState` in `live_state.py` holds mutable state keyed by session. Persisted and in-memory fields:

| Field | Persisted | Notes |
|---|---|---|
| `model` | yes | per-session model choice; an empty string falls back to `default_model` |
| `mode` | yes | only `plan` / `execute` are stored; `auto` removes the key |
| `effort` | yes | `high` / `max`; empty falls back to the global `default_effort` |
| `todo` | yes | nested under `todo`, with `list_id` / `items` / `collapsed` |
| autonomy / goal | no | process-local; lost on restart |

One JSON file per session: `<data_root>/session_state/<cid>.json`.

```json
{"model": "upstream-flash", "mode": "plan", "effort": "max",
 "todo": {"list_id": "l-1", "items": [{"id": "1", "text": "x", "done": false}], "collapsed": false}}
```

Three rules:

1. **Absent key means default.** A component with an empty value is not written; no empty value or "unselected" placeholder is stored. When all four components are empty, the file is deleted.
2. **Read before write.** The four components share one file; every write path calls `_ensure_loaded` first, otherwise it would overwrite the other components.
3. **One shape only.** The read path accepts only this shape; there is no compatibility branch for a second layout.

A cid must match `[A-Za-z0-9_-]{8,128}` before a path is built; an invalid cid is not persisted.

## File safety

`file_safety.py` contains two classes:

| Class | Role |
|---|---|
| `FileBackups` | versioned backup of a file's original content before a write, for `file_undo` comparison and rollback |
| `Recycle` | recycle directory for delete operations, making deletion recoverable |

Both sit under the data root by default (`data/temp/file_backup/` and `data/recycle/`), so they move with the data root.

## Further reading

- [architecture.md](../architecture.md): facts and projections
- [tools.md](tools.md): four-step write protocol
- [shell.md](shell.md): SSE reconnection and sequence numbers
