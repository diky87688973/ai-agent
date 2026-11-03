English | [中文](session-storage-refactor.zh.md)

**Status:** design, not implemented.

# Session Storage Refactor

## 1. Goals

Replace session persistence with incremental segmented storage and bounded reads:

1. Append only; never rewrite history.
2. A character window of 10,000; the whole turn touched by the boundary is included.
3. Round-range reads such as `[1, 10]`.
4. Reject every full read.
5. Support many concurrent sessions with resident memory independent of total history.
6. Keep all data in local files.
7. No legacy-data compatibility and no fallback branch for old formats.

## 2. Red Lines

| Rule | Level |
|---|---|
| An online read must not load the whole session | MUST |
| `chars=0` and `before=0` must not mean full read | MUST |
| No `read_all` / `load_all` / `read_from_start` | MUST |
| A window must not split `assistant(tool_calls)` from tool results | MUST |
| Per-read memory depends only on the window and current turn | MUST |
| Legacy `.raw` is not read, migrated, or deleted | MUST |
| Read path uses no global lock | MUST |
| One writer per session | MUST |
| Crash recovery never rewrites committed records | MUST |
| Core modules do not import storage implementations | MUST |
| Plugins never open session files directly | MUST |

Parameter semantics:

```text
chars = 10000       # default; <= 0 is invalid
from_round = 1      # 1-based
to_round = 10       # 1-based, must be >= from_round
before_round = None # latest page; 0 is never latest
```

Errors:

```text
WINDOW_INVALID
WINDOW_TOO_LARGE
ROUND_WINDOW_TOO_LARGE
ROUND_NOT_FOUND
INDEX_MISSING
INDEX_CORRUPT
CORRUPT_RECORD
SESSION_NOT_FOUND
```

## 3. DSH Comparison

DSH persistence baseline:

```text
JSONL
immutable generations
append + fsync
header / format version
projection cache
turn outline
```

DSH full-read limits:

```text
readSession replays the complete log
readSurface / filterEvents load the complete logical log
cold observation materializes all events on first read
```

This design keeps append and format isolation, but removes full-read paths:

| Capability | DSH | This design |
|---|---|---|
| Full history | `readSession` replay | forbidden |
| Event context | at most 50 raw events before/after | 10K chars + whole-turn boundary |
| Round read | `turnOutline` full fold | direct `rounds.idx` lookup |
| Cold read | materializes complete events | materializes a window only |
| Session memory | may retain complete log | window + current turn only |
| Large output | written into event JSONL | blob + bounded preview |
| Concurrent reads | complete observation | segmented index + lock-free reads |

## 4. Layers and Ownership

### 4.1 Layers

```text
agent/core/history_port.py
  HistoryPort: bounded reads only; no files

agent/mechanisms/session_history/
  format.py    format, encoding, validation
  index.py     segment and round indexes
  writer.py    append, sequence, recovery
  reader.py    snapshots, windows, round reads
  cache.py     window/round caches and byte budgets
  service.py   host service implementation

agent/shell/classic_adapter/
  history_page.py  UI page model; no direct file access
```

Dependency direction:

```text
entry -> shell -> capabilities -> mechanisms -> core
```

`core` does not import `mechanisms.session_history`; core modules depend only on `HistoryPort`.

### 4.2 Plugin 2.0 Boundary

```text
Storage belongs to mechanisms, not to any plugin.
SessionHistoryService is registered as a host service.
Plugins never read data/session directly.
Classic UI consumes windows over HTTP/SSE.
Plugins use the host service protocol, not file handles.
```

Assembly:

```text
app/host/services/session_history
  factory: boot/host_factories.py
  dependencies: data_root, config
  lifecycle: open allocator at startup; close handles at shutdown
```

No concrete module branch in `app.py`.

### 4.3 Data Ownership

```text
New data root: <data_root>/session/v2/
Legacy root:   <data_root>/session/raw/
```

Legacy files remain untouched. The new service does not scan, list, or recognize them.

## 5. File Layout

```text
<data_root>/session/v2/
  _stream/
    head.json                 # global stream seq high-water mark
  <session_id>/
    header.json               # identity, format, encryption, creation time
    manifest.json             # generation, segments, committed watermark
    seg-000001.log            # append-only JSONL
    seg-000001.idx            # fixed-width index
    seg-000001.rounds.idx     # per-segment round index
    blobs/
      <sha256>.bin            # large results, content-addressed
    projections/
      rounds.json             # final round summaries, rebuildable
```

### 5.1 Event Row

```json
{"seq":123456,"round":7,"type":"tool_done","ts":1760000000123,"chars":842,"data":{}}
```

| Field | Meaning |
|---|---|
| `seq` | globally monotonic; gaps allowed |
| `round` | 1-based round |
| `type` | event type |
| `ts` | write time |
| `chars` | canonical text character count |
| `data` | event payload |

Only durable fields are written. `conversation_id` is the session directory, not repeated per row.

### 5.2 Segment Index

Fixed-width binary:

```text
seq         uint64
round       uint32
offset      uint64
length      uint32
chars       uint32
event_type  uint16
flags       uint16
crc32       uint32
```

The index holds no body; it locates records and supports window accounting.

### 5.3 Round Index

```text
round_no
first_seq
last_seq
first_offset
last_offset
chars
message_count
status
```

Round rows hold summaries; bodies remain in segments.

## 6. Write Protocol

### 6.1 Single Writer

```text
One writer per session at a time
Process lock + cross-process .lock
Readers never take the write lock
```

### 6.2 Batch Commit

```text
1. reserve a seq block from the global allocator
2. write the whole batch to the active segment
3. fsync when configured
4. append .idx records
5. fsync the index
6. atomically update the manifest watermark
```

Commit order:

```text
log -> idx -> manifest
```

On failure:

```text
batch is not visible
committed prefix is not rolled back
batch enters a bounded retry queue
```

### 6.3 Crash Recovery

```text
partial tail after manifest: truncate; never index it
log written, index missing: bounded rescan from index_end to committed_end
index written, manifest not committed: ignore rows above the watermark
manifest committed: normal reads
```

Recovery scans at most the active segment, never the whole history.

### 6.4 Global Sequence

Do not scan all logs at startup to find the maximum sequence.

```text
_stream/head.json
  next_block
  block_size = 1024
```

- A writer reserves 1024 sequence numbers at a time.
- A file lock plus atomic replace updates the high-water mark.
- A crash wastes a reserved block; it never rolls the sequence back.
- Readers read only `head.json`; they never scan logs.

## 7. Read Protocol

```text
HistoryPort:
  head(session_id)
  stats(session_id)
  read_latest(session_id, chars=10000)
  read_before(session_id, before_round, chars=10000)
  read_rounds(session_id, from_round, to_round)
  read_round(session_id, round_no)
  read_record(session_id, seq)
  read_blob(session_id, blob_id, offset, length)
```

There is no:

```text
read_all
load_all
load
load_with_seq
read_from_start
```

### 7.1 Snapshot

Each read binds:

```text
snapshot = (generation, committed_seq, committed_end)
```

- Only data before `committed_seq` is read.
- Appends during a read do not change that read.
- The result carries `snapshot_seq`.
- A half-written record is never returned.

### 7.2 Page Shape

```json
{
  "items": [],
  "rounds": [8, 9, 10],
  "chars": 11240,
  "has_more": true,
  "next_before_round": 8,
  "snapshot_seq": 123456,
  "oversized_round": false
}
```

Pages contain whole rounds only. `next_before_round` supports upward paging without duplicating the boundary round.

## 8. Character Window

### 8.1 Character Accounting

Count Unicode code points:

```text
user content                 counted
assistant content            counted
tool result text             counted
tool argument JSON           counted
tool name / status / UI      not counted
image base64                 not counted
image placeholder text       counted
```

`chars` is computed once at append time and stored in the index.

### 8.2 Rounds Are Atomic

A user round runs from one `input_claimed` to the next.

The window accumulates whole rounds from newest to oldest:

```text
accumulate round chars
stop when the total reaches or exceeds 10000
include the whole round touched by the boundary
```

If one round exceeds 10K:

```text
return the whole round
oversized_round=true
do not truncate
do not extend to older rounds
```

Whole-round atomicity guarantees:

```text
assistant(tool_calls) is never separated from tool results
a tool pair is never split
all tool calls in the round stay together
```

### 8.3 Upward Paging

```text
read_before(before_round=10, chars=10000)
```

- If rounds 8-10 are returned, `next_before_round=8`.
- The next page starts before round 8 and does not duplicate it.
- `has_more=false` means round 1 was reached.

### 8.4 Invalid Arguments

```text
chars <= 0
before_round = 0
from_round < 1
to_round < from_round
```

All return `WINDOW_INVALID`.

Zero is never a full read and never a latest-page shortcut.

## 9. Round Range Reads

```text
read_rounds(from_round=1, to_round=10)
```

Use the round index directly:

```text
rounds.idx -> first_offset / last_offset
pread target records
fold only those rounds
```

Hard limits:

```text
max_rounds = 64
max_bytes = 2 MiB
max_records = 4096
```

Exceeding a limit returns `ROUND_WINDOW_TOO_LARGE`; there is no full-read fallback.

### 9.1 Round Cache

```text
RoundWindowCache
  key = session_id + snapshot_revision + round_no
  value = folded messages + last_seq + chars
```

Rules:

- Load once at the start of a round.
- Reuse for every tool call in that round.
- Append tool results incrementally to the active round.
- Freeze the round at turn end; evict later.
- Per-session cap 2 MiB; global cap 64 MiB.

## 10. Concurrency and Service

### 10.1 No Global Read Lock

```text
sealed segments are immutable
each read uses its own handle
reads never take the session write lock
manifest snapshot updates do not affect a started read
```

### 10.2 Handle Budget

```text
global handle limit: 64
LRU eviction of idle handles
one request holds at most the current segment count
release at request end
```

### 10.3 Memory Budget

```text
per read <= 2 MiB
per-session round cache <= 2 MiB
global window/round cache <= 64 MiB
index is mmap'd or read on demand
```

### 10.4 Service Model

```text
SessionHistoryService
  one snapshot per request
  one write lock per session
  no global events table
  no whole-store scans
  read concurrency controlled by the shell thread pool
  bounded write queue
```

A thousand idle sessions retain only headers and manifests, not complete event arrays.

### 10.5 Platform Reads

```text
POSIX: os.pread
Windows: per-request file handle + seek/read
sealed segment: read-only mmap over committed length
active segment: read only up to committed_end
```

Never share a seek position or a file object across threads.

## 11. Large Records and Blobs

```text
canonical text <= max_inline_record_chars (suggested 64 KiB)
  write directly into the event row

above the limit:
  write the body to blobs/<sha256>.bin
  keep preview + blob_id + blob_length in the event row
  count only the preview in window chars
```

Reads:

```text
history windows read only the preview
read_blob requires offset and length
never read a complete blob in one call
```

## 12. Failure Handling

| Failure | Behavior |
|---|---|
| Missing manifest | `SESSION_NOT_FOUND` |
| Missing round index | `INDEX_MISSING`; no full scan |
| Corrupt index | `INDEX_CORRUPT`; repair only the current segment |
| Partial tail | truncate the uncommitted tail |
| Log written, index missing | bounded rescan of the active segment |
| Disk full | batch is invisible; enter retry |
| Stale manifest during read | return the old snapshot; do not block writes |
| Corrupt record | `CORRUPT_RECORD` |
| Window over limit | explicit error; no full fallback |

## 13. Security

```text
session_id must match ^[A-Za-z0-9_-]{8,128}$
all paths resolve under data_root; reject ..
reject symlink escapes
index, records, and blobs carry CRC or hash
continue the existing local line encryption
indexes never store plaintext keys
error logs never include bodies
plugins never open data/session/v2 directly
```

## 14. Observability

```text
history_read_bytes
history_read_records
history_window_chars
history_round_cache_hit
history_window_cache_hit
history_snapshot_lag
history_active_handles
history_cache_bytes
full_read_rejected_total
```

`full_read_rejected_total` increments for every invalid full-read request. A full read on an online path is an incident.

## 15. Tests and Gates

### 15.1 Unit

```text
whole-round boundary inclusion
single round over 10K
round range [1,10]
before_round semantics
zero/negative rejection
missing index does not fall back
partial-tail recovery
encrypted row reads
blob range reads
```

### 15.2 Concurrency

```text
one writer and many readers per session
concurrent appends across sessions
1000 session open/close cycles
handle LRU does not leak
cache evicts over budget
snapshot never sees a partial record
```

### 15.3 Red Lines

```text
no read_all / load_all in code
no read exceeds its window budget
startup with legacy .raw does not read it
legacy session id returns not found
```

### 15.4 Performance Budgets

```text
10K window: does not grow with total events
round read: touches only the target rounds
append: never rewrites old files
1M events in one session: resident memory does not grow with event count
1000 idle sessions: only headers and manifests
```

### 15.5 Gates

```text
ruff
check_imports
check_architecture_hygiene
check_complexity + gen_complexity_md
gen_unit_tests_md --check
check_readme
check_comment_style
affected unit tests
```

## 16. Implementation Order

```text
1. HistoryPort / error codes / window semantics
2. v2 format, indexes, manifest
3. append + global seq + crash recovery
4. character windows + round ranges + round cache
5. UI history paging
6. model current-round and history windows
7. delete old full-read paths
8. concurrency, memory, and crash-injection tests
```

Each step must pass its gates; do not connect UI before storage.

## 17. Explicitly Out of Scope

```text
.raw compatibility
legacy migration
legacy session listing
full-read fallback when an index is missing
startup full-store scan
global event-list cache
special read_all branch
```

## 18. Unverified

```text
Windows mmap and handle-limit behavior
random-read throughput under encryption
p95 for 1000 concurrent reads
final blob and tool-result thresholds
product fallback for an oversized single round
```

These are design boundaries, not implemented behavior or benchmark results.
