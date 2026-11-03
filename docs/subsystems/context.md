**English** | [中文](context.zh.md)

# Context

## 1. Overview

The context module assembles one model request into a stable message prefix: system prompt, plugin-provided context segments, summary, and dialogue.

It handles generic capabilities only. It does not recognize specific plugins, business domains, or tools; plugins contribute through context slots and the module assembles the registered results.

## 2. Flowchart

```text
SessionRunner.build_engine
  ├─ session_prompt()
  ├─ ContextPipeline.append_system()  -> CHUNK_SYSTEM
  ├─ ContextSources.collect_segments() -> CHUNK_PLUGIN
  ├─ Compactor                         -> CHUNK_MEM
  ├─ SessionLog.derive_messages()      -> CHUNK_FULL
  └─ mode_note / request tail
```

## 3. Slots

### 3.1 Exposed

| Slot path | Capability | Key attributes | Replacement / override |
|---|---|---|---|
| `app/kernel/modules/compress` | Context compaction module entry | `scope=session`, `order=2`, `master=true`; implements `ModuleBase.execute(ports)` and emits events | Override at the same path with `replace=true`; restore on unload |
| `backend/context/sources` | Plugin context text registration | `fn(conversation_id) -> list[str]`; each item becomes one `system` message; `SourceMeta(key,label,prefix,count,plugin_rank)`; plugin manifest order; per-source failure isolated; returns disposer | Override at the same path with `replace=true`; restore on unload |
| `backend/context/assembly-hooks` | Post-assembly message hook | `hook(messages, conversation_id) -> list[dict] or None`; registration order; invalid/exception is logged and skipped; returns disposer | Override at the same path with `replace=true`; restore on unload |
| `backend/context/usage-segments` | Segment usage observation | `{key,label,tokens,pct}` per segment plus `remaining`; read-only | Override at the same path with `replace=true`; restore on unload |
### 3.2 Required

| Dependency path | Capability | Provider | Why | Impact when unavailable |
|---|---|---|---|---|
| `app/host/services/prompt_sections` | Render system-prompt sections | Host service | Produces `CHUNK_SYSTEM` | Head is incomplete |
| `app/host/services/context_sources` | Collect plugin text segments | Host service | Produces `CHUNK_PLUGIN` | Plugin segments are missing |
| `app/host/services/context_hooks` | Transform assembled messages | Host service | Adds hook content | Hook contributions are missing |
| `app/host/services/prompt_tail` | Request-tail fragments | Host service | Appends mode/plugin tails | Tail is missing |
| `app/host/services/provider` | Model calls | Host service | Generates compaction summaries | No compaction; original dialogue remains |
| `app/host/services/session_factory` | Per-session context pipeline factory | Host service | Isolates context by `conversation_id` | Session has no context pipeline |
| `app/host/services/compactor_factory` | Compactor factory | Host service | Creates the compactor | No compaction; context may exceed the window |

The module depends on capability interfaces only, not plugin implementations or paths.

## 4. Slot capabilities

### 4.1 System prompt: `app/host/services/prompt_sections`

`PromptSections` renders the sections; context receives the final text in `CHUNK_SYSTEM`.

- Input: section renderers.
- Output: one system-prompt text.
- Boundary: context does not reinterpret section semantics or plugin names.

### 4.2 Plugin segments: `backend/context/sources`

Each source registers a function and `SourceMeta`:

```python
def source(conversation_id: str) -> list[str]:
    ...
```

- `key`: segment key used by the UI anchor.
- `label`: display label.
- `prefix`: optional prefix.
- `count`: optional subject-count callback.
- `plugin_rank`: manifest order.

Each string becomes a separate `system` message; one source failure does not affect others.

### 4.3 Assembly hooks: `backend/context/assembly-hooks`

A hook runs after the message list is assembled:

```python
def hook(messages: list[dict], conversation_id: str) -> list[dict]:
    ...
```

- `None` means no change.
- A returned list replaces the current result.
- Invalid values or exceptions are logged and skipped.

### 4.4 Compaction module: `app/kernel/modules/compress`

This slot exposes the compaction module with `scope=session`, `order=2`, `master=true`.

It reads `ModuleBase.execute(ports)` context and emits events; policy comes from `compactor_factory`, summaries from `provider`.

### 4.5 Usage observation: `backend/context/usage-segments`

The layout reports:

```text
CHUNK_SYSTEM / CHUNK_PLUGIN / CHUNK_MEM / CHUNK_FULL
```

Each row has `key`, `label`, `tokens`, `pct`; a final `remaining` row is appended. It is read-only.

### 4.6 History summary: `app/host/services/compactor_factory`

The history summary is a user checkpoint, not a system message:

```text
<compacted-summary>
nine-section summary
</compacted-summary>
```

- Exactly one current summary is kept; each compaction replaces the previous one.
- It sits after system/plugin segments and before the current dialogue, as established background.
- It is not a new user request; never auto-execute `Pending Jobs` or `Next Step`.
- The summarization call reuses the exact prefix of the last normal request and appends one user compression instruction.

## 5. Details

### 补充

A compaction request reuses the same head and replaces only the tail instruction.



- `CHUNK_MODE` is a reserved empty block; runtime mode uses the request tail.
- Mode notes are not persisted in session facts and do not enter the system prompt.
- Tail content is stripped before compaction.
- A user turn is atomic; tool round-trips are not split.
- Images follow `[context]` `image_turns` / `image_max`; removed images remain in facts.
- Tokens are estimated: about 1 per CJK character, 1 per 4 other characters, fixed `IMAGE_TOKENS_PER_IMAGE` per image.
- Context failure propagates as request failure; there is no silent empty fallback.

## 6. Further reading

| Topic | Document |
|---|---|
| Architecture | [architecture.md](../architecture.md) |
| Kernel | [core.md](core.md) |
| Plugins | [plugins.md](plugins.md) |
| Configuration | [config.md](../guide/config.md) |
