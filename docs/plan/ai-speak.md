**English** | [中文](ai-speak.zh.md)

# AI Speak plugin design

## Design summary

The `plugins/ai_speak` plugin provides AI Speak: it exposes a single tool, `ai_speak`, and the model hands it what it wants to say at the current step. The backend validates the text, segments it, and synthesizes speech, then sends the audio segment by segment over SSE; the browser player queues the segments and plays them in order.

## Goals

1. The model calls `ai_speak` at every step and reports progress in the current role's first person, in human spoken language.
2. The tool exposes only `msg`; when validation fails it returns a failure with an actionable rule.
3. Speech is synthesized on the backend and never written to disk; each segment is pushed as soon as it is ready, and the browser plays while receiving.
4. Tool calls join the existing tool fact stream; the chat tool card shows "AI说话 | message", and the expanded detail keeps the default request/response payloads.
5. The settings toggle loads and unloads the plugin; disabling it stops playback and clears the queues.
6. Configuration uses `engine` / `voice` / `max_segment_chars` and adds a serial playback gap, a synchronous playback switch, and a rate multiplier.

## Out of scope

- Per-step emotion, tone, and character voice parameters; the tool contract is only `msg`.
- Browser-side speech synthesis.
- Audio files on disk, history replay, and resume after a disconnect.
- Multiple voices, several characters speaking at once, subtitles, speech recognition.

## Terminology

| Term | Meaning |
|---|---|
| `msg` | The tool's only parameter: one passage the model wants to say |
| Clause | Text between two boundary punctuation marks; boundaries are listed under "Segmentation" |
| Segment | One synthesis, one SSE push, one player queue item; a segment packs several clauses greedily up to `max_segment_chars` |
| Segment index | Position of a segment within one tool call, starting at 0; used for queue deduplication and playback progress |
| Tool fact | `tool_started` / `tool_done` / `tool_failed` / `tool_ended`, recorded by the kernel |
| Plugin event | An SSE frame of type `plugin_event`; not persisted and not replayed after a reconnect |
| Player page | Each browser tab has its own player; playback state is kept per conversation, and only the active conversation is audible in a tab |

## Invariants

1. The kernel and mechanism layers contain no `ai_speak`; the plugin depends only on public kernel interfaces (`core`, `capabilities`, and the shared `agent.config` loader) and the `SERVICE_PLUGIN_EVENTS` service, and does not import `agent.app` / `agent.entry` / `agent.shell`.
2. Speech is synthesized only on the backend. The frontend does not call browser TTS and stores no audio files.
3. The kernel produces tool facts; audio frames are a realtime side channel, are not written to the fact log, and do not participate in SSE replay.
4. Validation completes once at the tool entry. A validation failure fails the whole call and produces no partial enqueue.
5. The segment limit is `max_segment_chars` (default 128; 300, 1000, and other positive integers are allowed); one `msg` holds at most 512 characters.
6. Synthesis is serial within a conversation: a later segment's synthesis and push never overtake an earlier one.
7. Each browser tab creates its own player; one conversation is audible in only one tab at a time (where the browser provides Web Locks).
8. Disabling the plugin clears the page's queues and stops the current audio; when the user stops a turn or presses stop, the conversation's queue is cleared and the current audio stops.
9. Plugin event frames have no top-level `seq`. `seq` is the storage coordinate for SSE replay; audio segment order is expressed with `index` / `total`.
10. The configuration template and the parser use the same key set; the parser's set is `CONFIG_KEYS`.

## Overall structure

`msg` is already a complete string when the tool runs, so there is no character-level stream; the backend assembles continuous text into clauses. After segmentation it synthesizes and pushes one segment at a time, and the frontend only queues and plays. Plugin HTTP routes return JSON or text and cannot carry binary audio; audio travels as base64 over SSE and is played from a Blob URL.

```
model
  └─ ai_speak(msg)
       ├─ text.split_message()   character rules, pairing, length, ending
       ├─ runtime.enqueue()      per-conversation serial queue
       │    └─ worker            edge-tts synthesis → base64
       │         └─ ClassicAdapter.announce_plugin_event()
       │              └─ SSE plugin_event
       │                   └─ player queue → <audio> in order
       ├─ tool_started / tool_done / tool_ended (kernel facts)
       └─ chat tool card (plugin tool view)

settings toggle
  └─ sync_plugins → plugin_host.load / unload
       ├─ load: register tool, boot scripts, read-only routes
       └─ unload: withdraw tool/routes/boot scripts, stop synthesis, broadcast stop
            └─ SSE plugins_changed / player stops
```

| Component | Location | Responsibility |
|---|---|---|
| Tool | `plugins/ai_speak/tool.py` | Validate `msg`, resolve the conversation and event publisher, enqueue, wait in synchronous mode |
| Text | `plugins/ai_speak/text.py` | Character and pairing validation, segmentation and packing, pre-synthesis cleanup (pure functions) |
| Configuration | `plugins/ai_speak/config.py` | Read `[config]`, apply defaults, validate ranges (no side effects) |
| Synthesis | `plugins/ai_speak/provider.py` | edge-tts port and adapter, availability probe, timeout, error classification |
| Runtime | `plugins/ai_speak/runtime.py` | Per-conversation worker management, playback waiters, stop, counters and status |
| Worker | `plugins/ai_speak/runtime_worker.py` | Per-conversation serial synthesis, base64 encoding, event publishing, playback waiting |
| Entry point | `plugins/ai_speak/plugin.py` | Assembly, registration of tool/routes/boot scripts/event subscriptions/prompt tail |
| Player | `plugins/ai_speak/ui/player.js` | Per-conversation queue, audio elements, cross-tab lock, pause/stop |
| Styles | `plugins/ai_speak/ui/player.css` | Player bar styles, class prefix `ai-speak-` |
| Tool card | `plugins/ai_speak/ui/tool-view.js` | Chat title and summary, default request/response panels |
| Common event outlet | `agent/core/context.py`, `agent/app.py`, `agent/shell/classic_adapter/` | `SERVICE_PLUGIN_EVENTS` + `PluginEventPublisher` + `plugin_event_frame` + `announce_plugin_event` |
| Player toggle notice | `agent/shell/web/web_assets/classic/js/plugins/host.js` | Turn `plugins_changed` into a DOM event |

## Package layout

```
plugins/ai_speak/
  plugin.py                 entry: read config → build runtime → register tool/routes/boot scripts/subscriptions
                            `_config_path()` delegates to `config.config_path()`
  config.py                 AISpeakConfig + load_config() (pure)
  text.py                   split_message / to_speech_text (pure)
  provider.py               SpeechAudio / TTSProvider / EdgeTTSProvider
  runtime.py                AISpeakRuntime + playback waiters
  runtime_worker.py         _SessionWorker + serial synthesis + SSE publishing
  tool.py                   AISpeakTool
  plugin-config.ini         [config]
  plugin-meta.json          identity metadata
  ui/player.js              player bar above the composer and its queues
  ui/player.css             player bar styles
  ui/tool-view.js           chat tool card
```

Responsibility boundaries:

| File | Does only | Does not |
|---|---|---|
| `plugin.py` | Assembly and registration, event subscriptions, route handlers, prompt tail | Character validation, synthesis calls |
| `config.py` | Read and validate configuration, export defaults and key set | Create threads, access the network |
| `text.py` | Validation, segmentation, pre-synthesis cleanup | Read or write configuration, synthesize |
| `provider.py` | Call edge-tts, availability probe, timeout, error classification | Queues, SSE, conversation state |
| `runtime.py` | Worker management, playback waiters, stop, counters, status | Parse configuration, validate text |
| `runtime_worker.py` | Consume the queue, call synthesis, base64, publish events | Parse configuration, validate text |
| `tool.py` | Resolve conversation/publisher, call the runtime, wait, return results | Synthesize directly, broadcast directly |

Every Python module and frontend script stays under 800 lines, and every function under 80 lines.

## Tool contract

```python
class AISpeakTool(ToolPlugin):
    name = "ai_speak"
    label = "AI说话"
    icon = "🔊"
    parallel_safe = False
    needs_preview = False
    write_path_keys = ()

    parameters = {
        "msg": {
            "type": "string",
            "description": "要说的话；当前角色口吻、人类口语；单次最多 512 字。",
        }
    }
```

Model-visible description:

```
Say directly what you want to tell the user. Use the current role's first person and human
spoken language, as if reporting in person; avoid an announcer tone and written style, and do
not explain that you are calling a tool. Call it once after each completed step; do not wait
until everything is done.

Allowed: Chinese, English, digits, and spaces; Chinese punctuation ，。？！；、：“”‘’（）;
English punctuation . , ? ! ; : ' " ( ); arithmetic symbols + - * / × ÷ (including full-width
＋－＊／); percent sign % or ％. English words may contain - and '. Quotes and brackets must be
paired (including 「」 and 《》). Other symbols and emoji need not be deleted deliberately:
symbols that cannot be pronounced are removed before synthesis. Line breaks, tabs, Markdown,
code, and links are forbidden.

Each clause ends with boundary punctuation; the backend packs clauses greedily, and the segment
limit is the plugin's max_segment_chars (default 128 characters). Exceeding it fails and returns
the rule. One call holds at most 512 characters. For example, 「进度 10%。」 is read as
「进度 百分之十。」; 「5+3。」 is read as 「五加三。」.

Example: 主子，文件已经写好了，您要不要看一眼？
```

Success response:

```json
{
  "accepted": true,
  "segments": 3,
  "characters": 210
}
```

Synchronous mode adds `"played": true` and `"waited_ms": N` after playback finishes. The kernel wraps either result in `{"ok": true, "data": {...}}` for the model; the tool card's response panel shows the same envelope.

Failure responses:

| Exception | Trigger | Top-level result |
|---|---|---|
| `MessageValidationError` | Empty text, more than 512 characters, control characters, pairing errors, wrong leading or trailing position, percent/arithmetic context errors, a clause over the limit | `{"ok": false, "error": "..."}` |
| `SpeechEngineUnavailable` | `edge-tts` not installed, missing conversation or tool-call context, no plugin event outlet, no connected Web UI, plugin unloaded | Same, with an actionable message |
| `SpeechBusy` | The conversation reached its pending-segment limit | Same, with the current queue length and limit |
| `SpeechSynthesisFailed` | A segment failed to synthesize in synchronous mode | Same, with the reason from the engine |
| `SpeechPlaybackFailed` | Playback timed out, was stopped, errored, or the audio never arrived in synchronous mode | Same, with the playback status and elapsed wait |

Tool success only means "accepted and queued"; in asynchronous mode it does not mean the audio has been synthesized or played. A per-segment synthesis failure is delivered to the player as an `error` plugin event and counted in `/status`; the asynchronous result is unaffected. In synchronous mode a synthesis failure or unfinished playback fails the tool, which the kernel turns into `ok=false`.

## Text rules

### Validation

Character validation rejects only control characters that break structure (Unicode category `C`: newline, tab, carriage return, and so on); both half-width and full-width spaces are allowed. Everything else passes: symbols that cannot be pronounced are not rejected here and are removed by "Speech text" before synthesis.

| Category | Rule |
|---|---|
| Chinese, English, digits | Allowed |
| Spaces | Half-width `U+0020`, full-width `U+3000` |
| Chinese and English punctuation | Allowed; quotes and brackets must be paired, see "Pairing and structure" |
| Arithmetic symbols | `+` `-` `*` `/` `×` `÷` `＋` `－` `＊` `／`; position rules under "Arithmetic symbols" |
| Percent sign | `%`, `％`, only after a number, see "Percent sign" |
| Other symbols, emoji | Pass validation; symbols that cannot be pronounced are removed before synthesis |
| Control characters | Rejected: newline, tab, carriage return, and so on |

`-` has three legal positions: between two ASCII letters or digits (`well-known`, `GPT-4`, `2026-10-19`); as a binary minus (`5-3`, `5 - 3`); and as a negative prefix (`-5`). `-abc`, `abc-`, and `a--b` are invalid. A `'` between two ASCII letters is an English apostrophe and does not participate in quote pairing; elsewhere `'` is an English single quote and must be paired.

### Pairing and structure

1. Quotes and brackets must be paired: `“”`, `‘’`, `（）`, `《》`, `「」`, `""`, `''`, `()`; nesting is allowed, crossing is not; a Chinese opener can only be closed by the matching Chinese closer, and the same holds for English.
2. Empty pairs `“”`, `‘’`, `（）`, `《》`, `「」`, `""`, `''`, `()` are rejected.
3. The text cannot start with boundary punctuation or a closing quote/bracket.
4. The text cannot end with an opening quote/bracket.
5. Consecutive boundary punctuation forms one boundary unit, so English forms such as `...` and `?!` are allowed.
6. The text must end with boundary punctuation, or with a closing quote/bracket that immediately follows it.

### Percent sign

`%` / `％` must be preceded by an ASCII digit, optionally with spaces in between; the number may contain a decimal point and thousands separators. Before synthesis, "number + percent sign" is converted as a whole to the Chinese "百分之" plus the number:

| Source | Speech text |
|---|---|
| `10%` | `百分之十` |
| `3.5%` | `百分之三点五` |
| `100%` | `百分之百` |
| `1,000%` | `百分之一千` |
| `0%` | `百分之零` |

Integers are written with Chinese numeric units: `10` is 十, `11` is 十一, `20` is 二十, `101` is 一百零一, `100` is 一百, and `1000` is 一千; in `100%` the integer part is read 百, not 一百. Decimals are read digit by digit, and the decimal point is read 点. Thousands separators inside a number are removed from the speech text; the decimal point is kept. A `%` not preceded by an ASCII digit fails validation with the position reported. The table above shows speech-text fragments; a complete `msg` must still end with boundary punctuation, for example `进度 10%。`.

### Arithmetic symbols

`+` `-` `*` `/` `×` `÷` and the full-width `＋` `－` `＊` `／` are all allowed. Position rules:

- `+`/`＋`, `*`/`＊`, `/`/`／`, `×`, and `÷` must be binary: each side needs a non-space operand; a missing side at the start, at the end, or next to a space is rejected;
- operands are letters (including Chinese), digits, closing brackets, closing quotes, or a percent sign; boundary punctuation is not an operand;
- `-`/`－` may be a binary minus, a negative prefix, or an English hyphen;
- arithmetic symbols cannot be consecutive (`5--3` and `3**4` are rejected).

Before synthesis, simple arithmetic between numbers is converted to Chinese reading:

| Source | Speech text |
|---|---|
| `5+3` | `五加三` |
| `10-2` | `十减二` |
| `3*4`, `3×4` | `三乘四` |
| `10/2`, `10÷2` | `十除以二` |
| `-5` | `负五` |
| `well-known` | `well-known` |
| `2026-10-19` | `2026-10-19` |

Only "number + symbol + number" and "negative prefix" are converted; full-width symbols follow the same rules. English hyphens and the `-` in dates are kept verbatim. Symbols between letters are not converted: `/` and `-` are kept, while `+`, `*`, and the like are removed by cleanup; the resulting text goes to edge-tts.

### Length

| Item | Limit | Meaning |
|---|---|---|
| Segment | `max_segment_chars` (default 128, a positive integer, no configured upper bound) | Text length of one synthesis, one SSE frame, one queue item |
| Clause | `max_segment_chars` (same) | Text between two boundary punctuation marks; exceeding the limit fails |
| One `msg` | 512 characters | Raw text length of one tool call; larger input is rejected |

With `max_segment_chars = 300`, packing is greedy up to 300 characters; with `max_segment_chars = 1000`, up to 1000 characters. There is no hard 128 cap; 128 is only the default. A clause longer than the configured value fails the tool with the clause number, its length, and the configured limit, and is never cut mid-word.

## Segmentation

### Boundaries

Boundary punctuation:

- Chinese: `，` `。` `？` `！` `；` `、` `：`
- English: `.` `,` `?` `!` `;` `:`

Arithmetic symbols and the percent sign are not boundaries, so `5+3` and `10%` are never split at the symbol. The scan maintains a stack of expected closing symbols:

- `“` pushes `”`, `‘` pushes `’`, `（` pushes `）`, `《` pushes `》`, `「` pushes `」`;
- `"` pushes `"`, and `(` pushes `)`;
- `'` between two ASCII letters is an apostrophe and is not pushed; elsewhere it pushes `'`;
- a closing symbol must match the top of the stack, otherwise validation fails;
- a boundary mark encountered while the stack is empty ends a clause;
- consecutive boundary marks (`...`, `?!`) merge into one boundary unit;
- if the text ends with closing symbols and the last non-closing character is boundary punctuation, the end is also a boundary.

Three English punctuation marks have special meaning inside numbers and do not split:

| Form | Handling |
|---|---|
| `3.14` | `.` is the decimal point and stays inside the number |
| `1,000` | `,` is a thousands separator and stays inside the number; it is removed from the speech text |
| `10:30` | `:` is the time separator and stays inside the number |

A dot in a file name does not split either: when `.` follows a file-name character (letter, digit, `_`, `-`) and is followed by 1–5 ASCII letters with no further file-name character, the whole name is kept together, as in `USER_RULES.md` and `a/b.py`.

Punctuation inside quotes or brackets does not split, so a quotation is not cut in two. A clause spanning quotes is handled as one unit in a single scan.

### Packing

1. Split clauses at boundaries; every clause must be non-empty.
2. A clause may not exceed `max_segment_chars`; otherwise return a failure that names the clause number, its length, and the configured limit.
3. Pack greedily in order: add the next clause to the current segment while the configured limit is not exceeded, otherwise close the current segment first.
4. Every segment ends with boundary punctuation; closing quotes or brackets may follow.
5. The number of segments has no separate cap; it is bounded by the 512-character `msg` limit.

Examples (`max_segment_chars = 128`):

| Input | Result |
|---|---|
| `主子，文件写好了，您看一眼？` | 1 segment: `主子，文件写好了，您看一眼？` |
| `第一句。第二句！` | 1 segment (total length within 128, several clauses merged) |
| A 70-character clause + a 70-character clause | 2 segments |
| `他说“好。”` | 1 segment; it ends with a closing quote, and the last non-closing character is `。` |
| `Wait... what?` | 1 segment; `...` and `?` form boundary units |
| `进度 10%。` | 1 segment; the speech text is `进度 百分之十。` |
| `a` × 129 with no punctuation | Failure: no boundary, and the single clause exceeds 128 |
| `hello-world don't` | Characters are valid; there is no boundary, so it fails: the text must end with boundary punctuation |

With `max_segment_chars = 300` the same input packs at 300 characters; with `max_segment_chars = 1000` it packs at 1000 characters.

### Speech text

Before synthesis:

1. Remove the quote and bracket symbols `“”‘’（）"()` themselves while keeping their contents; keep apostrophes inside words and remove apostrophes elsewhere;
2. Protect date forms (`2026-10-19`) so they are not read as subtraction;
3. Convert "number + `%` / `％`" to "百分之 + Chinese number", see "Percent sign";
4. Convert simple arithmetic between numbers and negative prefixes to Chinese reading, see "Arithmetic symbols";
5. Remove thousands separators from numbers and keep the decimal point;
6. Collapse runs of spaces to one and trim the ends;
7. Keep only speakable characters: letters and digits (including full-width forms), spaces, boundary punctuation, `_ . \ / -`, and apostrophes; remove all other symbols (`@`, `#`, `&`, `《》`, `「」`, arrows, emoji, and so on).

The `text` sent over SSE is the original segment text, and the player displays the original; synthesis uses the cleaned text.

## Backend synthesis

### Port

```python
@dataclass(frozen=True, slots=True)
class SpeechAudio:
    data: bytes
    mime: str = "audio/mpeg"
    voice: str = ""


class TTSProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def synthesize(self, text: str, *, voice: str, timeout_s: float,
                   speed: float = 1.0) -> SpeechAudio: ...
```

### edge-tts adapter

- Import `edge_tts` lazily; `available()` decides whether the tool is usable, and the plugin still loads without the library.
- Synthesis uses the asynchronous stream: inside `asyncio.run`, `asyncio.wait_for` wraps `Communicate.stream()` and collects chunks whose `type == "audio"`; `speed` becomes a `rate` percentage.
- Timeout, no audio, network errors, and an unknown voice all become `SpeechSynthesisError`, with the voice name and the reason; the underlying stack is never handed to the model.
- A segment over 4 MB is treated as a failure and that segment fails; a 512-character segment is usually far below that size.
- The synthesized audio stays in memory and is never written to disk.

`engine` accepts only `edge`; any other value fails at load time and the plugin card shows the reason.

### Timeout

A single segment times out after 15 seconds. On timeout that segment fails, an `error` event is published, and the next segment is processed; the same segment is not retried, so the queue cannot stall.

## SSE contract

### Common outlet

Add a service name in `agent/core/context.py`:

```python
SERVICE_PLUGIN_EVENTS = "plugin_events"
```

Add to `agent/shell/classic_adapter/contract.py`:

```python
EV_PLUGIN_EVENT = "plugin_event"

def plugin_event_frame(
    plugin: str,
    event: str,
    payload: dict | None = None,
) -> dict: ...
```

Rules:

1. After trimming, `plugin` / `event` must be 1–64-character identifiers: the first character is a letter or digit, the rest are letters, digits, `_`, or `-`.
2. `payload` must be a dict or None; the function returns a new dict and does not modify the caller's object.
3. The reserved keys `type`, `plugin`, `event`, and `seq` may not appear in the payload; their presence raises `ValueError`. The SSE transport uses `seq` as the replay cursor, so plugin events cannot occupy it.
4. The frame shape is always `{"type": "plugin_event", "plugin": ..., "event": ...}` plus the payload.

`ClassicAdapter` (`ChannelMixin` in `agent/shell/classic_adapter/channel.py`) gains a public method:

```python
def announce_plugin_event(self, plugin: str, event: str,
                          payload: dict | None = None) -> int:
    return self._broadcast(C.plugin_event_frame(plugin, event, payload))
```

The method bypasses `translate()`, writes nothing to disk, and does not participate in `replay_after()`; it returns the number of SSE connections the frame was broadcast to. `_broadcast` also returns the connection count and drops the oldest frame when a channel queue is full, never blocking the event stream. `PluginEventPublisher` in `agent/shell/classic_adapter/plugin_events.py` wraps the method and exposes `__call__` and `connected()`; `build_app()` registers it as `SERVICE_PLUGIN_EVENTS` before plugins load. Plugins obtain it through `current_context().app.get(SERVICE_PLUGIN_EVENTS)` and never import `agent.shell`. With zero connections the tool returns "no connected Web UI" and neither queues nor synthesizes.

### Frame types

| Event | Fields | Meaning |
|---|---|---|
| `segment` | `conversation_id`, `call_id`, `index`, `total`, `text`, `voice`, `mime`, `audio`, `bytes`, `gap_ms`, `speed` | One segment's audio is ready |
| `error` | `conversation_id`, `call_id`, `index`, `code`, `message` | One segment failed to synthesize; the player reports it and continues |
| `stop` | `conversation_id`, `reason` | Stop playback for that conversation; without `conversation_id` it applies to the active conversation of the current tab |

`segment.audio` is standard base64 without a `data:` prefix; `mime` is always `audio/mpeg`. `gap_ms` is the server-configured serial playback gap; the player uses the most recent frame, so a saved configuration takes effect without reloading the boot script. `speed` is the synthesis rate multiplier and is diagnostic only; the player does not read it.

Example:

```json
{
  "type": "plugin_event",
  "plugin": "ai_speak",
  "event": "segment",
  "conversation_id": "0f3c...",
  "call_id": "call-7",
  "index": 0,
  "total": 3,
  "text": "主子，文件已经写好了。",
  "voice": "zh-CN-XiaoxiaoNeural",
  "mime": "audio/mpeg",
  "audio": "SUQz...",
  "bytes": 18234,
  "gap_ms": 0,
  "speed": 1.0
}
```

### Order and loss

- A conversation's worker synthesizes and publishes serially; `index` increases strictly.
- Segments from different conversations interleave on the global channel in arrival order; the player plays in arrival order.
- A slow SSE connection drops its oldest frame; audio frames are not replayed. The player does not detect gaps and does not request retransmission; in synchronous mode a missing segment means no acknowledgement, and the wait times out and fails the tool.
- A reconnect restores tool facts and UI state only; audio already missed is not replayed.

### Frame size

A single segment is capped at 4 MB, about 5.3 MB as base64. One connection queue holds at most 512 frames and drops the oldest when full. The cap is enforced at synthesis; the player does no additional size check on a frame.

## Frontend player

### Form

The slot `#aiSpeakSlot` sits above the composer on the left, the same width as the pending queue; when the slot is absent the bar floats at the bottom right:

```
┌──────────────────────────────────────┐
│ 🔊 AI说话  current…        queue 3  ⏸  ■ │
└──────────────────────────────────────┘
```

- The current segment is shown in full; when it is wider than the bar it scrolls horizontally in step with the audio, and the full text is in `title`.
- The count shows the number of pending items and is hidden at 0.
- Pause/resume button; the stop button clears the queue and hides the bar.
- When the browser blocks autoplay, the bar shows "点击播放" and keeps the queue.
- The bar does not steal focus; buttons carry `aria-label` and `title`.

### Queue

Playback state is per conversation; each conversation owns one `<audio>` and one queue:

```js
items = [
  { cid, callId, index, total, text, mime, url }
]
```

- `enqueue(frame)`: decode base64 into a Blob URL; deduplicate by `(callId, index)`; push; when the queue exceeds 512 items, drop the oldest pending item, count it, mark that call `incomplete`, and stop the call's remaining segments; start `playNext()` when idle.
- `playNext()`: take the head, set `<audio>`, and call `play()` inside the Web Lock.
- `ended`: revoke the URL, record the segment; after the whole call finishes, acknowledge `played`, wait `gap_ms`, and play the next item.
- `error` event: show the error text and acknowledge `error`; an audio-element error likewise acknowledges `error` and moves on.
- `stop(cid?, callId?)`: pause and release the current item; filter the queue by scope; an empty scope clears the conversation.
- `pause()` / `resume()`: pause or resume the current audio; pausing during a gap clears the timer.
- A non-active conversation pauses when the user switches away and resumes when it becomes active again.

### Autoplay

When the Promise returned by `audio.play()` rejects with `NotAllowedError`:

1. keep the current item and the queue;
2. set `blocked = true` and show "点击播放";
3. on the user's click clear `blocked` and call `play()` again; a new rejection sets it back;
4. treat other errors as playback failures, acknowledge the failure, and continue with the next item.

### Multiple tabs

Each browser tab creates its own player, `<audio>` elements, and queues. Playback of one conversation is serialized with `navigator.locks` under `ai-speak-playback:<conversation_id>`: the tab that holds the lock plays and the others stay paused until the user resumes them. `pause` and `stop` propagate to other tabs of the same conversation through the `BroadcastChannel` `ai-speak-player:<conversation_id>`. Different conversations can play in different tabs at the same time; there is no segment-level synchronization across tabs. Without Web Locks the tabs play independently.

### Synchronous playback

With `sync_playback = 1` the tool registers `(conversation_id, call_id)` before queueing and returns only after the frontend has played the last segment. The player counts segments by `call_id`, and after the last `ended` calls `POST /api/plugin/ai_speak/played`; `status` is `played`, `stopped`, `error`, or `incomplete`.

- `incomplete` is handled as `dropped`; a queue drop, a missing SSE connection, or a synthesis failure can never be reported as played.
- When the user stops, the player also requests `/api/chat/stop`; while waiting, the tool checks the turn's cancellation flag.
- The wait timeout is computed from text length: `max(30s, min(600s, 15s + characters × 0.35))`.
- When autoplay is blocked the player does not acknowledge; it acknowledges only after the user clicks play and playback finishes.
- At most 64 waiters are kept; beyond that the oldest is resolved as `dropped`.
- A waiter is keyed by `(conversation_id, call_id)` and holds the status and detail; the audio frame contract is unchanged.

### Configuration

The boot script calls `GET /api/plugin/ai_speak/config`:

```json
{"ok": true, "engine": "edge", "voice": "zh-CN-XiaoxiaoNeural",
 "user_salutation": "陛下", "assistant_salutation": "臣妾", "tone": "温婉",
 "max_segment_chars": 128, "play_interval_ms": 0,
 "sync_playback": false, "speed": 1.0}
```

`gap_ms` on a `segment` frame overrides the local value. If the configuration cannot be read, `gap_ms` is 0 and the player bar still works.

### Settings toggle

- The player listens for `ai-agent:plugins-changed`; when `loaded` does not contain `ai_speak` it calls `destroy()` and removes the bar and audio elements.
- On unload the plugin backend publishes `stop` (best effort); either path stops playback.

### Resource release

- Every Blob URL is revoked with `URL.revokeObjectURL` on `ended`, `error`, `stop`, and queue drop.
- Timers are cleared on stop, pause, and plugin disable; page teardown releases the remaining memory.
- Removing the bar unbinds all listeners; re-initialization calls the previous instance's `destroy()` first.

## Tool card

The plugin registers through the boot script with `window.aiAgentChatTools.register`:

| Attribute | Value |
|---|---|
| `match` | `chatToolName(script) === "ai_speak"` |
| `title` | `AI说话` |
| `summary` | `args.msg`, trimmed |
| `mount` | Build the default `请求` and `响应` panels |
| `fill` | Fill the response panel with `chatToolResponseText` |

The shell draws a vertical divider between title and summary, visually "AI说话 │ message"; the full summary text is in the `title` attribute and long messages are ellipsized by CSS. Expanded detail remains the default request/response payloads; no custom detail view is registered.

The left step card shows only the tool name "AI说话"; the chat tool card shows the message summary. Both share the `tool_call_id` of the same tool call.

## Lifecycle and toggle

### Load

1. Read `[config]` from `plugin-config.ini`, validate `engine`, and parse numbers; fallback warnings are recorded through `report_error`.
2. Build `AISpeakRuntime`; no thread is created at this point.
3. Register `AISpeakTool`.
4. Declare an empty subagent tool list so the tool is not exposed to subagents.
5. Register two boot scripts: `ui/player.js` and `ui/tool-view.js`.
6. Register the read-only routes `GET config` and `GET status`, plus `POST played` for playback completion.
7. Subscribe to `turn_ended` and `error` to stop the conversation's queue when the turn is stopped or interrupted.
8. Append the voice instruction with `add_mode_tail`; it is not rendered into subagent requests and is empty when the engine is unavailable.
9. Call `ctx.set_runtime(runtime)` so the shell and tests can resolve the same instance by name.
10. At execution time the tool resolves `SERVICE_PLUGIN_EVENTS` from `current_context().app`; if it is missing or reports zero connections, the tool returns an unavailable error.
11. Return the disposer list; if any registration fails, call `runtime.dispose()` and re-raise.

### Unload

1. The host runs the disposers in reverse order.
2. `runtime.dispose()`: stop accepting new segments, wake workers, clear queues, publish `stop`, and resolve waiters.
3. The host withdraws the tool, routes, and boot scripts.
4. The settings page broadcasts `plugins_changed`; the frontend's `applyPluginsChanged` dispatches `ai-agent:plugins-changed`, and the player stops and removes the bar.

### Re-enable

Boot scripts are deduplicated by URL; on unload the shell's `prunePluginScripts` removes the script tags and clears the load table, so a re-enable executes them again. The player destroys the previous instance before initializing, avoiding duplicate `<audio>` elements and listeners.

### Turn stop

When `turn_ended` arrives with `stopped` or `halted` set, the conversation's queue stops; a normal `done` does not interrupt queued audio, letting the last few sentences finish. An `error` event also stops that conversation's queue.

## Configuration

`plugins/ai_speak/plugin-config.ini` holds these keys; the defaults are shown below:

```ini
[config]
engine = edge
voice = zh-CN-XiaoxiaoNeural
user_salutation = 陛下
assistant_salutation = 臣妾
tone = 温婉
max_segment_chars = 128
play_interval_ms = 0
sync_playback = 0
speed = 1.0
```

| Key | Default | Range | Notes |
|---|---|---|---|
| `engine` | `edge` | `edge` only | Synthesis engine; any other value fails at load time |
| `voice` | `zh-CN-XiaoxiaoNeural` | non-empty | edge-tts voice name; an unknown voice fails during synthesis |
| `user_salutation` | `陛下` | non-empty | How the model addresses the user |
| `assistant_salutation` | `臣妾` | non-empty | How the model refers to itself |
| `tone` | `温婉` | non-empty | Tone constraint on the model's speech |
| `max_segment_chars` | 128 | integer ≥ 1, no upper limit | Segment character limit; 300 packs at 300, 1000 packs at 1000 |
| `play_interval_ms` | 0 | ≥ 0 | Playback gap between segments (ms) |
| `sync_playback` | 0 | `0` / `1`, also accepts `true` / `false` and similar | 1 = the tool waits for playback to finish |
| `speed` | 1.0 | 0.5–2.0 | Rate multiplier; 1.0 is normal speed |

Parsing rules:

- Missing file → all defaults; the real configuration is produced by the settings page.
- Integer keys: a non-number falls back to the default; `max_segment_chars` below 1 falls back to 128; `play_interval_ms` below 0 becomes 0. `max_segment_chars` has no upper limit. Each fallback adds a warning, which the plugin records through `report_error`.
- `speed` that is not a number or outside 0.5–2.0 falls back to 1.0.
- The enable flag lives in `plugins.ini`; `0` means not loaded.
- Unknown `[config]` keys are ignored and do not block loading.
- A non-`edge` engine, an empty `voice`, or a parse error records `report_error` and makes the plugin fail to load; the error appears in the plugin list and on stderr.

The parser's key set is declared by `CONFIG_KEYS`, and the configuration template must match it.

## Concurrency and resources

### Runtime structures

```python
class AISpeakRuntime:
    _workers: dict[str, _SessionWorker]
    _lock: threading.Lock
    _playback: dict[tuple[str, str], PlaybackWaiter]
    _disposed: bool
    _totals: dict[str, int]
```

`_SessionWorker`:

```python
class _SessionWorker:
    _queue: queue.Queue[tuple[_SegmentJob, Publisher] | None]
    _thread: threading.Thread
    _stop: threading.Event
    _generation: int
```

### Serial guarantee

- One worker per conversation; `enqueue` checks queue capacity under the runtime lock and inserts the whole batch at once, avoiding a partial enqueue.
- The worker takes, synthesizes, and publishes one segment at a time; `index` increases strictly within a conversation.
- Workers for different conversations run in parallel; each conversation in each browser tab has its own queue and plays in arrival order.

### Stop and cancellation

- `stop_cid(cid, reason)`: resolve that conversation's playback waiters, remove its worker, drain pending segments, publish `stop`, and wait at most 0.2 seconds; the worker checks `_stop` before each synthesis and each publish.
- `dispose()`: set `_disposed`, resolve all waiters, set `_stop` for every worker, push `None`, and wait up to 3 seconds; a worker still alive records one `report_error` and is abandoned (daemon thread).
- Stop order: stop accepting new segments → stop workers → clear queues → publish stop. Counters are kept for `/status`.

### Queue limits

| Queue | Limit | Behavior at the limit |
|---|---|---|
| Pending segments per conversation | 1024 | The tool returns `SpeechBusy` and the whole batch is rejected |
| Playback waiters | 64 | The oldest is resolved as `dropped` |
| Pending items in the frontend | 512 | Drop the oldest pending item, count it, and mark the call `incomplete` |
| One audio frame | 4 MB | That segment fails and an `error` is published |

### Concurrency tests

`tests/test_concurrency.py` covers concurrent enqueue into the same conversation without losing segments; stop, full queue, and concurrent enqueue are covered by `RuntimeTest` in `tests/test_ai_speak_runtime.py`.

## Errors and observability

### Error classes

| Class | Producer | Handling |
|---|---|---|
| Validation failure | `text.split_message` | The tool raises `MessageValidationError`; top-level `ok=false`; no audio produced |
| Dependency unavailable | `provider` / context / publisher | The tool raises `SpeechEngineUnavailable`; the message points to installation or enablement |
| Queue busy | `runtime.enqueue` | The tool raises `SpeechBusy`; the message gives the queue length and limit |
| Synthesis failure | worker | Publish an `error` event; record `report_error`; continue with the next segment |
| Playback unfinished | synchronous waiter | The tool raises `SpeechPlaybackFailed` with the status and elapsed wait |
| Playback failure | frontend | Show it in the bar; skip the current item; acknowledge the failure status |
| Invalid event | `plugin_event_frame` | Raise `ValueError`; the plugin records it; nothing is broadcast |

### Status endpoint

`GET /api/plugin/ai_speak/status`:

```json
{
  "ok": true,
  "engine": "edge",
  "engine_ready": true,
  "voice": "zh-CN-XiaoxiaoNeural",
  "max_segment_chars": 128,
  "play_interval_ms": 0,
  "sync_playback": false,
  "speed": 1.0,
  "playback_waiting": 0,
  "sessions": [
    {"conversation_id": "0f3c...", "queued": 2, "spoken": 5, "failed": 0, "dropped": 0}
  ],
  "totals": {"queued": 12, "spoken": 10, "failed": 1, "dropped": 0},
  "last_error": {"code": "synthesis_failed", "message": "..."}
}
```

No secrets are returned (the plugin has none); `last_error` keeps only the most recent entry so the status cannot grow without bound.

### Logging

- Configuration errors, synthesis errors, and stop timeouts go through `report_error` under the `plugin.ai_speak.*` scope.
- Per-segment success writes nothing to stderr, avoiding one line per sentence; counters are exposed by `/status`.
- Player errors are shown in the bar and acknowledged to the backend; the player does not write console errors, and server text is never inserted as HTML.

## Security and trust

| Item | Constraint |
|---|---|
| Trust boundary | The plugin is trusted like local code; it runs in the same process after loading, with no sandbox |
| Input validation | Completed once at the tool entry; downstream code does not guess whether a character is legal |
| DOM injection | Server text is assigned through `textContent` only; it never enters `innerHTML` |
| Style isolation | Class prefix `ai-speak-`; styles are served by the plugin asset route |
| Audio size | 4 MB per segment at synthesis; base64 only produces an in-memory Blob |
| Files | No disk writes, no user files read, no path construction |
| Network | Only edge-tts contacts its service; the plugin makes no other requests |
| Secrets | The plugin has no credentials; the configuration template contains none |
| Event outlet | `plugin_event_frame` validates plugin name, event name, and reserved keys; no arbitrary routing |

Each browser tab creates its own player and queues, and SSE broadcasts to every page. Playback of one conversation is serialized by the browser lock, and `BroadcastChannel` propagates pause and stop; different conversations do not affect each other. The player keeps only in-page memory state.

## Tests

### Unit tests

`tests/test_ai_speak_text.py`

| Class | Coverage |
|---|---|
| `SplitTest` | Chinese and English clauses, packing to the limit, 300/1000 limits, 512-character limit, a clause over the limit, quoted ending, numeric separators |
| `ValidationTest` | Empty text and missing ending, control characters, non-speakable symbols accepted, rule text in errors, invisible characters named, file names and book-title marks, unmatched and empty pairs, bracket quotes, arithmetic context, percent without a number, leading boundary |
| `SpeechTextTest` | Quotes and apostrophes, removal of book-title marks and brackets, removal of non-speakable symbols, percent, arithmetic to Chinese, dates and identifiers, thousands separators |
| `ConfigTest` | Missing file defaults, values and ranges, invalid engine and empty voice |

`tests/test_ai_speak_runtime.py`

| Class | Coverage |
|---|---|
| `ProviderTest` | Fake edge-tts stream, missing library, empty audio, timeout |
| `RuntimeTest` | Publish order and base64, wait timeout and cancellation, isolated synthesis failure, no SSE stops the worker, stop clears the queue and publishes stop, full queue rejects the batch, enqueue rejected after dispose |
| `ToolTest` | Successful enqueue, synchronous ack wait, synchronous timeout, synchronous synthesis failure, release on stop, validation failure, missing publisher, no connection, missing engine, tool contract, envelope |
| `RegistrationTest` | Tool/routes/boot scripts/subscriptions/runtime registration; everything reclaimed on unload; config and status routes |

`tests/test_ai_speak_plugin.py`

| Class | Coverage |
|---|---|
| `AISpeakAppTest` | `build_app` loads tool/routes/boot scripts/runtime; the voice instruction enters the request tail; publisher connection counting; everything reclaimed on unload |

`tests/test_classic_adapter.py`

| Class | Coverage |
|---|---|
| `PluginEventTest` | `plugin_event_frame` shape, reserved keys, invalid plugin/event names, payload copy; `announce_plugin_event` reaches every channel and returns the connection count |

`tests/test_concurrency.py`

| Class | Coverage |
|---|---|
| `AISpeakRuntimeContentionTest` | Many threads enqueue into the same conversation without losing segments, with stable order and no duplicates |

### Acceptance

- `scripts/acceptance_phase3.py`: load `ai_speak` plus the knowledge plugin from a temporary manifest; assert the tool exists, two boot scripts are contributed, endpoint contributions are in place, two event subscriptions exist, and the runtime is registered; after unload everything is gone.
- `scripts/acceptance_web_player.py` (invoked by `acceptance_web.py`): open the page, confirm the player bar is injected, dispatch `plugin_event` and `plugins-changed`, and assert there are no uncaught exceptions and that disabling the plugin removes the bar. Real audio is not verified by automation; it is covered by manual regression.
- Manual regression:
  1. Start the service, enable AI Speak in the settings page, and confirm the plugin card and tool list.
  2. Let the model run a multi-step task; confirm it calls the tool at each step, the bar plays segment by segment, and the gap takes effect. Run once with `max_segment_chars` set to 300 and once to 1000, and confirm that packing follows the configuration.
  3. Pause, resume, and stop; the current audio stops immediately on stop.
  4. Disable the plugin in the settings page; confirm playback stops, the queue is cleared, and the tool disappears. Re-enable it and confirm the tool returns.
  5. Open two tabs on the same conversation and confirm only one tab is audible while the others stay paused; different conversations can play independently.
  6. When browser autoplay is blocked, confirm the "点击播放" button works.
  7. Remove `edge-tts` and confirm the tool returns an actionable installation hint.
  8. Enter a message containing emoji and confirm it is accepted and the emoji is not spoken; enter a newline, more than 512 characters, or a clause over the configured limit, and confirm the failure message names the position and the rule. Enter `进度 10%。` and confirm it is read as `进度 百分之十。`; enter `5+3。`, `10-2。`, `3*4。`, `10/2。`, and `-5。` and confirm the corresponding Chinese reading.
  9. Confirm no new audio files appear under `data/`.

### Coverage

`run_coverage.py` already includes `plugins`, with a 60% floor. Pure logic modules target 85% or more; the edge-tts adapter covers success, exception, and timeout paths through a fake module.

## Risks and limitations

| Item | Impact | Handling |
|---|---|---|
| Browser autoplay policy | The first play may be rejected | The "点击播放" button keeps the queue |
| edge-tts needs the network | No audio when offline or the service is unavailable | Tool failure gives an install/network hint; `/status` records the last error |
| base64 size | Large segments use memory and bandwidth | Configured segment limit, 4 MB synthesis cap, queue limits |
| SSE frame loss | A slow consumer drops the oldest frame | No retransmission; a synchronous wait times out and fails |
| Multiple tabs | The same segment reaches several pages | Where Web Locks are available, one tab per conversation plays; pause/stop broadcast to the same conversation |
| Multiple conversations | Queues in one page interleave | Play in arrival order; each item carries its conversation id and can be stopped by scope |
| Small configured value | A clause may exceed the configured limit | Validation fails and names the effective limit; no hard word cut |
| Symbol set | Code, URLs, formulas, and `@`/`#`/`&` cannot be pronounced | The model uses words instead; unspeakable symbols are removed before synthesis; `%` becomes a Chinese percentage |
| Wrong voice name | edge-tts synthesis fails | Per-segment error event; `/status` records it |
| No audio on disk | No replay after a refresh or reconnect | Tool facts remain; audio is a realtime side channel |

## Implementation rules

1. `max_segment_chars` defaults to 128 and accepts any integer ≥ 1 with no upper limit; 300 packs greedily at 300 characters and 1000 at 1000 characters. A clause over the value fails instead of being cut mid-word.
2. Character validation rejects only control characters (newline, tab, carriage return, and so on); everything else passes. Quotes and brackets must be paired, including `《》` and `「」`. Arithmetic symbols `+` `-` `*` `/` `×` `÷` (including full-width forms) are checked by position; `%`/`％` are allowed only after a number and are converted to a Chinese percentage. Unspeakable symbols and emoji are removed before synthesis.
3. Chinese and English boundary punctuation both end clauses; inside numbers, `.`, `,`, and `:` are the decimal point, thousands separator, and time separator, and a dot in a file-name extension does not split either; arithmetic symbols and the percent sign are not boundaries. A segment may contain several clauses, and it always ends with boundary punctuation.
4. One `msg` holds at most 512 characters; larger input is rejected. The number of segments has no separate cap.
5. Each browser tab creates its own player; where Web Locks are available, one conversation is audible in only one tab at a time, and different conversations are not synchronized.
