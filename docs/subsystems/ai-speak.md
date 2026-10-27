**English** | [中文](ai-speak.zh.md)

# AI Speak (`ai_speak` plugin)

AI Speak sends the model's current step to the backend for speech synthesis and delivers it to the browser player bar as plugin events. The tool receives, validates, and queues the text, and in synchronous mode waits for playback to finish; synthesis, playback, and the enable toggle are handled separately.

## Package layout

```
plugins/ai_speak/
  plugin.py                    entry: config, runtime, tool/routes/boot scripts/subscriptions
  config.py                    [config] reading and validation
  text.py                      character rules, segmentation, pre-synthesis cleanup
  provider.py                  edge-tts port and adapter
  runtime.py                   runtime: worker management, playback waiters, stop, counters
  runtime_worker.py            playback waiters, per-session serial synthesis, SSE publishing, stop
  tool.py                      the ai_speak tool
  plugin-meta.json             identity metadata
  plugin-config.ini            real configuration (checked in)
  ui/player.js                 player bar above the composer and its queue
  ui/player.css                player-bar styles
  ui/tool-view.js              chat tool card
```

## Tool

```python
name = "ai_speak"
label = "AI说话"
icon = "🔊"
parameters = {"msg": {"type": "string"}}
```

The tool description asks the model to speak as the current role, in human spoken language, and to say each step directly. Asynchronous mode returns `{"accepted": true, "segments": N, "characters": N}`; synchronous mode returns `{"accepted": true, "played": true, "segments": N, "characters": N, "waited_ms": N}` after playback ends. The kernel wraps either result in the standard tool envelope. The tool raises on validation failure, a missing engine, a missing Web connection, or a full queue, and the kernel turns that into `ok=false`.

Tool calls automatically produce `tool_started`, one result fact (`tool_done` / `tool_failed`), and `tool_ended`. The chat tool card is registered by `ui/tool-view.js`: its title is "AI说话", its summary shows `msg`, and its expanded body holds the default request/response payloads.

## Text rules

Character validation rejects only control characters that break structure (Unicode category `C`: newline, tab, carriage return, and so on); everything else passes. Symbols that cannot be pronounced are not rejected at validation; [pre-synthesis cleanup](#pre-synthesis-cleanup) removes them.

Quotes and brackets must be paired; nesting is allowed, crossing is not; empty pairs are rejected. Supported pairs: `“”` `‘’` `（）` `《》` `「」` `""` `()` `''`. `-` may be a hyphen inside an English word, a binary minus, or a negative prefix; `+` `*` `/` `×` `÷` must be binary operators. The text ends with boundary punctuation; `...` and `?!` count as one continuous boundary.

A dot in a file name does not end a clause: when `.` follows a name character (letter, digit, `_`, or `-`) and precedes 1–5 letters that are not followed by another name character (`USER_RULES.md`, `a/b.py`), the whole run is read as one piece.

Boundary punctuation: Chinese `，。？！；、：`, English `. , ? ! ; :`. Inside numbers, `.`, `,`, and `:` are the decimal point, thousands separator, and time separator and do not split; punctuation inside quotes or brackets does not split.

One `msg` holds at most 512 characters. `max_segment_chars` bounds a single segment (default 128, any integer ≥ 1, no upper limit); segments are packed greedily up to that size. A single clause longer than the configured value fails instead of being cut mid-word.

## Pre-synthesis cleanup

Cleanup keeps only characters that can be pronounced: everything left has a sound.

Kept: letters and digits (including full-width forms), spaces, clause boundaries, the file-name symbols `_ . / \ -`, and apostrophes inside words. All other symbols (quotation marks and brackets of every kind, including `「」` and `《》`, arrows, emoji) are removed.

Three pronunciation rewrites:

- `number%` / `number％` become "百分之" plus the Chinese number, for example `10%` → `百分之十`;
- arithmetic between numbers is read in Chinese, for example `5+3` → `五加三`, `10/2` → `十除以二`, `-5` → `负五`; the `-` in dates and inside English words is left unchanged;
- thousands separators inside numbers are removed; decimal points are kept.

Finally, runs of spaces collapse to one.

## Configuration

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

Identity metadata lives in `plugin-meta.json`; the enable flag lives in `plugins.ini`.

| Key | Default | Range | Notes |
|---|---|---|---|
| `engine` | `edge` | `edge` only | Synthesis engine; any other value fails at load time |
| `voice` | `zh-CN-XiaoxiaoNeural` | non-empty | edge-tts voice name |
| `user_salutation` | `陛下` | non-empty; empty falls back to the default | How the model addresses the user |
| `assistant_salutation` | `臣妾` | non-empty; empty falls back to the default | How the model refers to itself |
| `tone` | `温婉` | non-empty; empty falls back to the default | Tone constraint on the model's speech |
| `max_segment_chars` | 128 | integer ≥ 1, no upper limit | Per-segment character limit |
| `play_interval_ms` | 0 | ≥ 0 | Playback gap between segments (ms) |
| `sync_playback` | 0 | `0` / `1` | 1 = the tool waits for the front end to finish playback |
| `speed` | `1.0` | `0.5`–`2.0` | Synthesis rate multiplier; `1.0` is normal speed |

The configuration file is `plugin-config.ini` in the plugin directory; the parser reads the same keys. `edge-tts>=7.3.1` is an optional dependency; install it with `pip install -e ".[tts]"`. It is imported lazily: the plugin loads without the library, and the tool returns an install hint when it runs.

## Instruction injection

When the plugin is enabled, it appends an instruction with `add_mode_tail` after the execution mode and the Todo-List; the instruction does not enter the system-prompt prefix, and the tail is not rendered into subagent requests. It asks the model to call `ai_speak` proactively to communicate with the user and is omitted when the speech engine is unavailable.

## Events and playback

Each synthesized segment is broadcast as one `plugin_event` through the publisher registered under `SERVICE_PLUGIN_EVENTS`, implemented by `ClassicAdapter.announce_plugin_event()`. The front end's `stream.js` turns it into an `ai-agent:plugin-event` DOM event:

| Event | Fields |
|---|---|
| `segment` | `conversation_id`, `call_id`, `index`, `total`, `text`, `voice`, `mime`, `audio`, `bytes`, `gap_ms`, `speed` |
| `error` | `conversation_id`, `call_id`, `index`, `code`, `message` |
| `stop` | `conversation_id`, `reason` |

`audio` is standard base64; audio is never written to disk. Plugin event frames have no top-level `seq`: `seq` is the SSE resume cursor and must not be used. The player turns each segment into a Blob URL, queues it, plays segments serially in arrival order, and waits `gap_ms` between segments.

Player state is per `conversation_id`: each conversation has its own queue and audio element, and queues and acknowledgements do not mix. Switching the active conversation pauses the one that was playing. In browsers with Web Locks, only one player per conversation id is allowed across tabs; other tabs stay paused, while different ids can play in different tabs. `pause` / `play` events on the audio element, including those from system media controls, keep the button state and subtitle animation in sync.

The player provides pause/resume, stop, and "click to play"; when the browser blocks autoplay, the queue is kept. The `stop` event filters the queue by conversation or call; when the plugin unloads, the backend publishes `stop` and the shell dispatches `ai-agent:plugins-changed` as a second stop signal.

## Synchronous playback

With `sync_playback = 1`, `ai_speak` does not return as soon as the segments are queued: the tool first registers the `call_id`, then waits until the front end confirms that the last segment finished playing. The model therefore does not continue before playback completes.

The player counts segments by `call_id` and, after the final segment's `ended` event, sends `POST /api/plugin/ai_speak/played`:

| Field | Description |
|---|---|
| `conversation_id` | Conversation id; when omitted, the backend matches by unique `call_id` |
| `call_id` | `ai_speak` tool-call id; must match the one used when queueing |
| `status` | `played` / `stopped` / `error` / `incomplete` |
| `detail` | Optional failure reason, truncated to 300 characters |

`incomplete` means the player dropped an item from its queue; the backend records it as `dropped`. Synthesis failure is reported separately as `synthesis_failed`: the tool raises `SpeechSynthesisFailed` with the engine's reason. The tool raises `SpeechPlaybackFailed` on playback errors, user stops, an SSE connection lost during playback, or a timeout; unfinished playback is never reported as finished. In synchronous mode the stop button also requests `/api/chat/stop`, so the tool wait and the turn cancellation settle together; while waiting, the tool checks the turn's cancellation flag so the tool thread cannot hang.

The safety timeout is computed from text length: `max(30s, min(600s, 15s + characters × 0.35))`. When autoplay is blocked, the player does not acknowledge and waits for the user to click play; if the user never does, the wait times out. With Web Locks, only one tab per conversation id plays and the other tabs do not acknowledge; different ids report independently.

## Boundaries

- Synthesis uses edge-tts only; no custom synthesis endpoint is supported.
- Audio stays in memory and is never written to a file; it is not replayed after a refresh or reconnect.
- Per-segment audio limit: 4 MB; per-session pending-segment limit: 1024; front-end queue limit: 512.
- Disabling the plugin unloads the tool, routes, and boot scripts, and stops current synthesis.
- Failure paths (missing engine, a failed segment, no SSE connection, a full queue, invalid text) each yield actionable information; a failed segment is isolated and does not terminate the session worker.
