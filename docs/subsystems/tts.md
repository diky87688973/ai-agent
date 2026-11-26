# Speech synthesis (`tts` plugin)

## 1. Overview

`tts` is the multi-engine entry point for speech synthesis: it translates upstream
intent (voice, emotion, speed) into parameters a concrete engine accepts, and falls
back to Edge when the local model is unavailable. Upstream plugins only describe the
voice they want; they do not know who synthesises it.

## 2. Slot protocol

### Exposed

| Slot path | Capability | Key properties | Replace/override |
|---|---|---|---|
| `app/plugins/tts/service` | In-process service | owner=plugin; built at assembly, released on exit | Replace at the same path with `replace=true` |
| `backend/http/routes/tts-config` | HTTP endpoint | owner=plugin; path from declaration; removed on unload | Replace at the same path with `replace=true` |
| `backend/http/routes/tts-status` | HTTP endpoint | owner=plugin; path from declaration; removed on unload | Replace at the same path with `replace=true` |

### Depends on

| Dependency path | Capability | Provider | Why |
|---|---|---|---|
| — | — | — | Bottom-most synthesis capability; only depends on `agent.common.tts_contract` and the standard library |

## 3. Capabilities

### Package layout

```
plugins/tts/
  plugin.py                    Entry: build service, two read-only endpoints
  config.py                    [config] parsing and validation
  provider.py                  Engine registry: build by engine name
  service.py                   Facade: primary + fallback + status snapshot
  edge_provider.py             Edge engine (network synthesis)
  breeze_provider.py           Local Breeze TTS 2 engine (HTTP)
  supervisor.py                Local server process lifecycle
  pinyin.py                    Edge-only polyphone hints
  models.py                    Installable model catalog and layout
  plugin-meta.json             Identity metadata
  plugin-config.ini            Real config (tracked)
  settings-schema.json         Settings fields
```

### Contract

The contract lives in `agent/common/tts_contract.py` and is shared by both sides:

| Name | Meaning |
|---|---|
| `TTSRequest` | `text`, `voice` (intent, not an engine parameter), `instruction`, `speed`, `cfg_scale`, `timeout_s` |
| `TTSResult` | `audio` (in memory), `sample_rate`, `mime`, `engine` |
| `TTSCapabilities` | `supports_instruction`, `supports_speed`, `supports_cfg`, `needs_pinyin_hints` |
| `TTSUnavailable` | Engine unavailable; subclasses `TTSEngineUnavailable`, `TTSNotInstalled` |
| `TTSSynthesisError` | One segment failed; the caller isolates it |

### Engines

| Capability | Edge | Breeze (local) |
|---|---|---|
| `supports_instruction` | no | yes |
| `supports_speed` | yes (rate percentage) | yes (natural-language phrasing) |
| `supports_cfg` | no | yes |
| `needs_pinyin_hints` | yes | no |
| Voice source | `edge_voice` config | Upstream intent folded into the instruction |

Speed is always a number; each engine maps it:

```text
speed < 1   -> "语速慢，约正常速度的 0.8 倍"
speed = 1   -> "语速正常"
speed > 1   -> "语速快，约正常速度的 1.2 倍"
```

Edge uses a `rate` percentage; the local engine has no numeric speed parameter, so the
result follows the direction but is not exact.

### Selection and fallback

```text
engine = breeze
  |-- built ok  -> primary=breeze, fallback=edge (when fallback_to_edge=1)
  `-- build fail -> primary=edge, no fallback, reason kept in status
Failures are classified only two ways:
  TTSUnavailable    -> switch to the fallback engine
  TTSSynthesisError -> do not switch; report the segment as failed
```

A single failed segment never switches engines; doing so would disguise a real fault as
a success.

### Voice and speaker

The model has no fixed speaker. Without `voice_id` the timbre is re-sampled from the
instruction and the current text: the same sentence replays identically (fixed seed),
but the next sentence is a different voice.

To pin a voice, register a reference voice first (see the `tts-setup` skill) and set
`voice_id`. Once set, `voice_desc` no longer enters the instruction; only emotion and
speed remain.

### Local server lifecycle

```text
missing files  -> TTSNotInstalled with install guidance
stopped        -> spawn, poll /health until startup_timeout
ready          -> plain HTTP; concurrent requests do not spawn twice
idle timeout   -> stop and release ~3.8 GiB of VRAM
process died   -> spawned again on the next request
```

The server binds `127.0.0.1` only, and loopback requests bypass the system proxy.

Server processes are adopted into a job object with `KILL_ON_JOB_CLOSE`: whether the
agent exits normally or is force-killed, the OS terminates them, so no orphan keeps
holding VRAM.

### Status endpoint

`GET /api/plugin/tts/status` exposes `engine`, `primary_ready`, `fallback_engine`,
`fallback_ready`, `last_fallback_reason`, `capabilities` and `warnings`.

## 4. Details

### Configuration

| Key | Default | Range | Meaning |
|---|---|---|---|
| `engine` | `breeze` | `breeze` / `edge` | Invalid values fail at load time |
| `model_dir` | empty | directory | Install root for model and server |
| `default_model` | `breeze-tts-2-q4k` | registered id | Unregistered ids are rejected |
| `server_port` | 8137 | 1–65535 | Local server port |
| `startup_timeout` | 20 | ≥1 | Seconds allowed for startup |
| `idle_timeout` | 600 | ≥0; 0 disables | Idle seconds before stopping |
| `cfg_scale` | 2 | 1–5 | Instruction guidance strength |
| `voice_desc` | sample description | non-empty | Default voice intent |
| `voice_id` | empty | registered voice name | Pins the speaker; empty re-samples per sentence and the voice drifts |
| `emotion` | 平静 | free text | Emotion preset |
| `speed` | 1.0 | 0.5–2.0 | Speed multiplier |
| `edge_voice` | `zh-CN-XiaoxiaoNeural` | non-empty | Edge only |
| `fallback_to_edge` | 1 | `0` / `1` | Fallback on/off |

### Installation guidance

Installing, quantising and self-checking the local engine is covered by the `tts-setup`
skill. The catalog registers only the verified model; adding another requires editing
`models.py` as well.

### Boundaries

- Audio stays in memory; nothing is written to disk.
- One segment is capped at 800 characters; larger input fails and the caller must split.
- No streaming in the first version: the full clip is returned before the caller sees it.
- The local engine is an optional enhancement: a build failure does not block the plugin,
  it degrades to Edge and records why.

## 5. Further reading

| Topic | Document |
|---|---|
| AI role-play | [ai-cosplay.md](ai-cosplay.md) |
| Plugins | [plugins.md](plugins.md) |
