**English** | [中文](multi-model.zh.md)

# Multi-model configuration design

## 1. Background and goals

The model path has three parts:

- `agent/mechanisms/providers/` holds one adapter per protocol; every adapter implements `ModelProvider.stream()`.
- Model configuration is supplied only by `plugins/multi_model/plugin-config.ini`.
- The session model selection is stored in `live_state` and reaches the provider as `LogicalRequest.model`.

Goals:

1. Each model independently declares its provider, gateway, credential, and wire model id; models may span gateways and protocols.
2. A Messages protocol adapter supports text, tool calls, and extended thinking.
3. Model configuration is plugin-owned, with the same shape as the knowledge plugin: its own configuration file, endpoint, and UI assets.
4. The UI exposes a model dropdown; a selection is persisted per conversation and broadcast to other tabs of the same conversation and to the header.
5. When the plugin is disabled or has no valid entry, the model list is empty; there is no fallback to kernel configuration.

## 2. Invariants

1. The sole authority for model configuration is `plugins/multi_model/plugin-config.ini`.
   The plugin provides models while it is enabled and has at least one valid entry; with no valid entry the catalog is empty.
2. Credentials stay on the server. No HTTP response contains `api_key` or `base_url`.
3. Dependency direction is fixed: `shell → capabilities → mechanisms → core`.
   Plugins sit outside the package and may only depend downward; `mechanisms` and `core` never import a plugin and never contain a plugin directory name (`check_architecture_hygiene.py` scans at word boundaries).
4. Provider adapters emit only `StreamDelta`. The kernel does not understand a wire format, a thinking block, or a signature.
5. Disabling a plugin removes its contributions: dropdown, routes, boot script, and styles are unregistered together. The fallback path must not raise.
6. An unconfigured model id fails the request; there is no fallback to the default model.
7. A configuration error invalidates the affected entry and is reported. A state with no usable model is a degraded state, visible in `/health`; it is never silently replaced by a hidden default.
8. `provider_meta` is passed through opaquely. It only travels between `model_message` and assistant messages.

## 3. Layers and components

| Layer | Component | Responsibility |
|---|---|---|
| core | `StreamDelta`, `LogicalRequest` | stream frame contract, request contract, `PROVIDER_META_KEY` |
| core | `session_log.derive_messages` | folds facts into logical messages, carrying `provider_meta` |
| mechanisms | `AnthropicProvider` | Messages wire format, SSE, message and tool conversion |
| mechanisms | `OpenAICompatibleProvider` | Chat Completions wire format and SSE |
| mechanisms | `provider_registry` | kind → builder; the only place that constructs a provider |
| mechanisms | `ProviderRouter` | selects a provider instance for `request.model` |
| capabilities | `ModelCatalog` | model descriptor registry, provider cache, authority decision |
| capabilities | `PluginContext.add_model_catalog` | plugin registration point |
| assembly | `app.build_app` | creates the catalog and router, loads plugins, decides authority and degraded state |
| shell | `web_api`, `web_state` | serve the model list, persist the selection, broadcast changes |
| shell | `classic_adapter` | announces conversation model changes |
| shell | web assets, plugin host | model bridge and style bridge |
| plugins | `plugins/multi_model` | configuration parsing, catalog source, dropdown UI |

## 4. Model catalog

### 4.1 Data structures

The catalog is `agent/capabilities/model_catalog.py`. It has exactly one authoritative source, and its semantics are replacement, not merge:

```python
@dataclass(frozen=True)
class ModelEntry:
    id: str
    provider: str                 # provider_registry key: "openai" | "anthropic"
    options_json: str = "{}"      # canonical JSON; the catalog does not interpret it
    label: str = ""
    is_default: bool = False

    @classmethod
    def from_options(cls, *, id, provider, label="", options=None, is_default=False):
        ...

    @property
    def options(self) -> dict:    # a fresh copy on every read
        ...

    @property
    def context_window(self) -> int:        # 0 when not declared
        ...

    @property
    def compression_percent(self) -> int:   # 70 when missing or malformed
        ...

@dataclass(frozen=True)
class CatalogSnapshot:
    entries: tuple[ModelEntry, ...]
    default_id: str
    authoritative: bool
    source: str                   # "" means no source

    def entry(self, model_id: str) -> ModelEntry | None:
        ...

class ModelCatalog:
    def set_source(self, source, entries) -> Disposer: ...
    def snapshot(self) -> CatalogSnapshot: ...
    def ids(self) -> tuple[str, ...]: ...
    def default_id(self) -> str: ...
    def provider_for(self, model_id: str) -> ModelProvider | None: ...
```

`options` is stored as canonical JSON rather than a shared dictionary. A `frozen` dataclass protects field assignment, but a mutable dictionary inside a field can still be rewritten by a caller; a read-only view built that way is not read-only. Storing JSON and returning a copy on each access also removes a mutable cache key.

`context_window` and `compression_percent` are model metadata derived from `options`. The context window is the denominator for the compaction threshold and for the UI occupancy display; the compression percentage is the trigger ratio. A missing window is reported as `0`, and a missing or out-of-range percentage falls back to `70`.

`provider_for` returns `ModelProvider | None`, not `Any`. The only contract between the catalog and a provider is `stream()`, so the base class is sufficient; the port does not need to expose an arbitrary extension point.

### 4.2 Behavior

1. `set_source` replaces. Calling it again with the same `source` means the configuration changed; the whole batch is replaced, not appended. This matches the single-authority rule: a merge registry would make `default_id` ambiguous as soon as a second source exists.
2. `entries` may be a callback. It is evaluated on every `snapshot()`, so a plugin can decide whether to re-read its configuration file; configuration changes do not require a process restart.
3. A second source is rejected. `set_source` raises `RuntimeError` when a different source is already registered. `PluginContext.add_model_catalog` catches it, reports a diagnostic naming both sources, and returns an empty disposer. Plugin loading continues and the first source is unchanged. The behavior must be deterministic: load order is not a contract, but the result must be auditable.
4. Authority is computed, not stored: `authoritative = len(valid_entries) > 0`. A boolean fixed at registration time would keep pointing at an empty catalog after the configuration changes from three entries to zero.
5. An `entries` callback failure means "this read failed". The snapshot retains the last good entry set; if there is none, the result is empty. A diagnostic naming the source and the exception is recorded. A duplicate id is a configuration error, not a transient read failure: `set_source` rejects the batch with `ValueError`, and `snapshot()` keeps the last good batch.
6. The provider cache is rebuilt by batch. The fingerprint is the ordered tuple of `(id, provider, options_json)`; when it changes, all cached instances are dropped and the next lookup builds the one it needs. With a dozen entries the rebuild cost is negligible, and it avoids "a wrong fingerprint returned a stale instance" failures.
7. When the `Disposer` fires, it clears the source's entries and every cached provider instance. A generation counter ensures an old disposer cannot clear a newer registration.
8. Entries with an unknown `provider` are skipped during normalization with a diagnostic (`provider_registry` raises `ValueError` for an unknown kind).
9. Entries with an empty id, or values that are not `ModelEntry` instances, are skipped with a diagnostic. A malformed `options_json` yields an empty options dictionary for that entry only.
10. `default_id` is the first entry marked `is_default`, otherwise the first entry; it is `""` when the catalog is empty.

### 4.3 Plugin extension point

`PluginContext` gains a method at the same level as `add_panel` and `add_context_source`:

```python
def add_model_catalog(self, entries) -> Disposer
```

`PluginContext` calls `catalog.set_source(self.name, entries)` with the plugin name as the source and records the returned disposer in its own reclamation list. The argument is either an entry sequence or a callback that returns one; a plugin does not import kernel code and does not construct providers.

`PluginHost` gains a `model_catalog` constructor parameter, created and injected by the assembly root.

## 5. Provider registry

The registry is `agent/mechanisms/provider_registry.py`:

```python
def build_provider(kind: str, options: Mapping[str, Any]) -> ModelProvider
def known_kinds() -> tuple[str, ...]
```

1. The implementation is a `kind → builder` mapping with two rows: `openai` and `anthropic`.
2. Adding a provider means adding one adapter file and one mapping row. The router, the catalog, and the plugin are unchanged.
3. An unknown `kind` raises `ValueError(kind)`. The caller decides whether that means "skip this entry" or "fail startup".
4. Option keys are interpreted by each constructor; the registry only dispatches and filters. Each kind has a whitelist so a stray configuration key cannot turn a typo into a `TypeError`:
   - `openai`: `base_url`, `api_key`, `model`, `timeout`, `replay_history_reasoning`, `extra_headers`;
   - `anthropic`: `base_url`, `api_key`, `model`, `max_tokens`, `thinking`, `thinking_budget_tokens`, `anthropic_version`, `timeout`, `extra_headers`.
   Values that are `None` are dropped, so the constructor keeps its own default.

## 6. Provider routing

The router is `agent/mechanisms/provider_router.py`:

```python
class ProviderRouter(ModelProvider):
    def __init__(self, *, default, resolve, allowed_ids=(), default_id="",
                 fallback_to_default=False): ...
    def reload_policy(self, *, allowed_ids, default_id, fallback_to_default): ...
    def reload_default(self, provider): ...
    @property
    def model(self) -> str: ...
    @property
    def allowed_models(self) -> tuple[str, ...]: ...
    @property
    def default_provider(self) -> ModelProvider: ...
    def stream(self, request): ...
```

Rules:

1. `mid = request.model or default_id`; when `mid` is empty the default provider is used directly.
2. `provider = resolve(mid)`; on a hit, the request is dispatched to `provider.stream()`. The catalog id is the routing key, while the wire model name belongs to the provider (`options.model`). The router replaces `request.model` with the provider's wire model name before calling `stream()`; the two values may differ.
3. If there is no hit, `fallback_to_default` is true, and `mid` is in `allowed_ids`, the default provider handles the request. This flag is a policy knob for embedders that run without an authoritative catalog; the standard assembly passes `false`.
4. Otherwise the router raises `ModelRequestError("未配置的模型：<id>")`. It never silently substitutes a model.
5. `resolve` is an injected callback. The assembly root connects it to `ModelCatalog.provider_for`. The router does not read INI files, does not import plugins, and does not know provider names.
6. `model` returns `default_id`, or the default provider's model name when no default id is set; it is used by `ModelPort.name()` and logging.
7. `reload_default(provider)` replaces the default instance under the lock. It is the only entry point that may change the default.
8. `reload_policy(...)` refreshes the allowed list, default id, and fallback flag after plugins are loaded, when the authoritative list is known. `default_provider` exposes the current default instance without allowing mutation.

## 7. Messages adapter

The Messages adapter is `agent/mechanisms/providers/anthropic.py`:

```python
class AnthropicProvider(ModelProvider):
    def __init__(self, *, base_url, api_key, model,
                 max_tokens=16000, thinking=True, thinking_budget_tokens=4096,
                 anthropic_version="2023-06-01", timeout=300.0,
                 extra_headers=None): ...
    def stream(self, request) -> Iterator[StreamDelta]: ...
```

### 7.1 Request

Address construction:

| Base URL form | Result |
|---|---|
| ends with `/messages` | used as is |
| ends with `/v1` | append `/messages` |
| anything else | append `/v1/messages` |

Request headers: `x-api-key`, `anthropic-version`, and `content-type: application/json; charset=utf-8`. Additional headers from the configuration are merged last.

Request body:

```json
{
  "model": "model-id",
  "max_tokens": 16000,
  "stream": true,
  "system": "merged text of the system prompt and all system segments",
  "messages": [],
  "tools": [
    { "name": "read_file", "description": "…", "input_schema": { "type": "object", "properties": {} } }
  ],
  "tool_choice": { "type": "auto" },
  "thinking": { "type": "enabled", "budget_tokens": 4096 }
}
```

Constraints:

1. The adapter does not send `temperature` at all. In thinking mode the parameter has no effect, so sending it would only add a field whose meaning differs between gateways.
2. Thinking is effective only when `budget_tokens >= 1024` and `max_tokens > budget_tokens`. If either condition fails, thinking is disabled and a diagnostic is written to stderr, but the request is still sent; a configuration blemish must not fail the turn.
   Disabling must be explicit: send `{"type": "disabled"}`. Omitting the field leaves the gateway's default behavior in place, which may keep thinking on; in thinking mode an assistant message with `tool_use` must return its thinking blocks, so a silent omission makes the next tool turn fail with 400.
3. On the Chat Completions gateway, `budget_tokens` is ignored and thinking depth follows `output_config.effort` (`low`, `high`, `max`). The adapter does not send `output_config`, because the Messages endpoint rejects that unknown field and one adapter serves both protocols. `LogicalRequest.effort` therefore has no effect on this adapter; the gateway uses its server-side default (`high`). To control depth by level, use a Chat Completions entry for the same model.
4. Thinking plus tool calls: both protocols require the thinking blocks of the current turn's assistant messages with `tool_use` to be returned unchanged. Cross-turn replay is not required, so `strip_stale_thinking` keeps only the current turn. If a block is missing and cannot be recovered (the signature was dropped, or the history came from another protocol entry), `_tool_turn_missing_thinking` disables thinking for the request so the conversation does not become permanently unusable.
5. When `tools` is empty, neither `tools` nor `tool_choice` is sent.
6. `max_tokens` is required by this API. The constructor default is used when the entry does not override it.
7. `input_schema` must be an object schema with a `type`. `ToolRegistry.schemas()` returns `parameters` as a property map, which is normalized by the shared `tool_parameters()` in `agent/mechanisms/providers/tool_schema.py` before it is sent. Passing the map directly produces `type: null`, and the Messages endpoint rejects it with `Invalid schema for function ...` (400). The Chat Completions gateway does not validate this field, so the defect only appears on the Messages protocol.
8. Images support `source.type=base64` for `data:` URLs and `source.type=url` for `http(s)` URLs. Accepting only base64 would silently drop image links on a Messages entry while the same image is sent normally on a Chat Completions entry.

### 7.2 Message conversion

Conversion is split into pure functions and a final assembly step, so "faithful folding" and "repair for downstream constraints" stay separate:

```python
def strip_stale_thinking(messages, turn_start): ...   # keep only this turn's thinking blocks
def drop_dangling_tool_results(messages): ...          # drop tool results without a tool_use
def _to_anthropic_messages(messages, turn_start, *, keep_thinking=True): ...
```

Mapping:

| Logical message | Wire format |
|---|---|
| `role=system` | extract the text and append it to the top-level `system` field in order, separated by blank lines |
| `role=user` with string `content` | `{role:"user", content:[{type:"text", text}]}` |
| `role=user` with a multimodal array | `text` is passed through; a `data:` URL in `image_url` becomes `{type:"image", source:{type:"base64", media_type, data}}`; an `http(s)` URL becomes a `url` source |
| `role=assistant` | non-empty `content` becomes a `text` block; each `tool_calls` item becomes a `tool_use` block |
| `role=tool` | becomes `role:"user"` with `content:[{type:"tool_result", tool_use_id, content}]` |
| assistant `provider_meta.anthropic.thinking_blocks` | inserted at the front of the content in original order, only when the message index is `>= turn_start` and thinking is enabled for this request |

Repair rules, all pure functions and unit-testable:

1. Consecutive `role=tool` messages are merged into one `role:"user"` content array, preserving order.
2. Adjacent user messages are merged as well, because two consecutive messages with the same role are rejected.
3. An empty tool result gets a placeholder text so the `content` array is never empty.
4. The first message must be `user`; leading assistant messages are dropped because they have no `tool_result` waiting for an answer.
5. A `tool_result` without a matching `tool_use` is dropped. Keeping it causes the API to reject the whole conversation.
6. If `tool_use.id` repeats within one request, the second and later occurrences get `_2`, `_3` suffixes. The assistant `tool_use` and its `tool_result` must be renamed together, or the pairing breaks.
7. Assistant messages before `turn_start` carry no thinking blocks. When thinking is disabled, no message carries them.

### 7.3 Stream event mapping

SSE is parsed line by line from `data:` payloads. The event type comes from `data.type` in the payload, never from the `event:` line: two copies of "what event is this" eventually diverge. The `event:` line is skipped, not used as a decision input.

| `data.type` | Handling |
|---|---|
| `message_start` | record `usage.input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`; missing values count as 0 |
| `content_block_start` | create a block by `index`: `text`, `thinking`, or `tool_use` (record `id` and `name`; non-empty `input` becomes the initial value). Initial text and thinking are emitted immediately |
| `content_block_delta` | `text_delta` → `kind="text"`; `thinking_delta` → `kind="reasoning"`; `signature_delta` accumulates `delta.signature`; `input_json_delta` accumulates `partial_json` |
| `content_block_stop` | a `tool_use` block parses its JSON into a `ToolCallRequest`; a `thinking` block records `{thinking, signature}`. A block without a signature is dropped, and a warning is written when it had text |
| `message_delta` | record `stop_reason` and `usage.output_tokens` |
| `message_stop` | end the stream |
| `error` | raise `ModelRequestError(error.message)`, with the message truncated to 800 characters |
| `ping` | ignored |

`input_json_delta` merging:

1. Accumulate `partial_json` by block `index`; parse once at `content_block_stop`.
2. A parse failure degrades to empty arguments `{}`; the call is still emitted and the tool side reports the error.
3. An empty `tool_use` id falls back to `call_<random>`, matching the Chat Completions adapter.

`stop_reason` is written to the diagnostic log only. It does not extend the stream frame contract: `StreamDelta` has no `finish_reason` and does not gain one, matching the Chat Completions adapter.

### 7.4 Stream-end order

The order is fixed so the model module can collect by type:

1. Text and reasoning deltas stream as they arrive; they are not accumulated into a list.
2. `kind="meta"` is emitted only when this turn has thinking blocks and at least one tool call. The payload is `{"anthropic": {"thinking_blocks": [...]}}`. Without a tool call the signature has nowhere to be returned, so there is no reason to persist it.
3. `kind="tool_call"` is emitted in ascending block `index`.
4. `kind="usage"` carries the mapped usage; it is omitted when every field is zero.

### 7.5 Usage mapping

```text
prompt_tokens            = input_tokens + cache_read_input_tokens + cache_creation_input_tokens
completion_tokens        = output_tokens
prompt_cache_hit_tokens  = cache_read_input_tokens
prompt_cache_miss_tokens = input_tokens + cache_creation_input_tokens
```

The field names match the Chat Completions adapter, so the UI and the accumulator need no branch.

### 7.6 Error mapping

| Status | User-facing meaning |
|---|---|
| 400 | Invalid request parameters; check the model and parameter configuration. |
| 401 | Authentication failed; check the API key. |
| 403 | Access denied; check the key's permission scope. |
| 404 | Model or endpoint not found; check `base_url` and the model id. |
| 413 | Request body too large; reduce historical images or context. |
| 429 | Too many requests; retry later. |
| 500 | Model server error; retry later. |
| 529 | Model service overloaded; retry later. |

The `error.message` from the response body is appended to the hint and truncated to 800 characters. The Messages error table is separate from the Chat Completions table; unknown statuses return the raw HTTP body, truncated to 8000 characters.

## 8. Thinking signature return

Extended thinking on the Messages protocol requires thinking blocks, including their `signature`, to be returned unchanged within the same tool loop; otherwise later requests in that turn are rejected. The existing fact field `reasoning_content` holds only text, so the signature would be lost.

The design adds a `provider_meta` field to the `model_message` fact that the kernel does not interpret.

1. `agent/core/model_call.py` exports `PROVIDER_META_KEY = "provider_meta"`. `StreamDelta` gains `meta: Optional[Dict[str, Any]] = None`, and `kind` gains the value `"meta"`.
2. `agent/core/modules/model_mod.py` collects `kind=="meta"` payloads, merges them, and writes the result to `model_message[PROVIDER_META_KEY]`; the field is omitted when empty.
3. `agent/core/session_log.py` `derive_messages()` copies the key unchanged into the assistant message. Reader and writer use the same constant instead of repeating the string.
4. `agent/mechanisms/providers/openai.py` `_to_wire_messages` pops `PROVIDER_META_KEY` so an unknown field is never sent to a Chat Completions gateway.
5. Replay scope: thinking blocks are included only for message indexes `>= request.turn_start`. Cross-turn blocks are dropped so an expired signature is never replayed.

`provider_meta` constraints:

1. It must be JSON-serializable; both persistence and loading use the existing `default=str` fallback.
2. The kernel does not read its internal structure and does not use it for segment accounting, token estimation, or compaction decisions.
3. When the compactor drops messages in a compacted range, their `provider_meta` is dropped with them.
4. It stores only `{thinking, signature}` blocks, not a whole response. The text is not truncated: truncation invalidates the signature, and the replayed block is then rejected.
5. It is an optional, forward-only key in the persisted format. Old logs without the key are read as having no thinking blocks; readers ignore unknown vendor subkeys; no migration or rollback is required. No reader may require the key.

## 9. Assembly

### 9.1 Wiring

`agent/app.py` `build_app()`:

1. Create `ModelCatalog`, add the service name `SERVICE_MODEL_CATALOG` to the process-level service vocabulary in `agent/core/context.py`, and inject it into `PluginHost`.
2. Register `ProviderRouter` as `SERVICE_PROVIDER` from the start; a bare provider is never exposed:
   - `default`: the provider supplied by the entry point, or an echo provider in a bare assembly;
   - `resolve`: `catalog.provider_for`;
   - `allowed_ids` and `default_id`: initial values, recomputed after plugin loading through `reload_policy`;
   - `fallback_to_default`: `false` in the standard assembly.
3. After `plugin_host.load_manifest(...)`, compute `app.model_config_state` once:

   | Value | Condition |
   |---|---|
   | `"catalog"` | the catalog is authoritative and its entries are non-empty |
   | `"config"` | the catalog is not authoritative, but a provider was injected explicitly at assembly |
   | `"none"` | neither of the above |

4. In the `"catalog"` state, use the catalog's `ids()` and `default_id()` to override `app._available_models` and `live_state.default_model`; otherwise keep the values established at assembly.
5. Converge stale values: when `live_state.get_model(cid)` is not in `available_models()`, fall back to the default id, write it back, and record a diagnostic. After a plugin configuration change, an old tab does not keep a deleted id and fail the next request.
6. `MissingProvider.stream()` raises `ModelRequestError("未配置任何模型")`. The message contains no plugin directory name: a plugin name inside `mechanisms` would violate the kernel architecture gate and would embed operational guidance in the kernel.
7. The web entry and the shell perform no credential prechecks and construct no providers of their own; both go through `build_app`.
   When no model is configured, the web shell still starts, prints a warning that points at the settings path, and reports `"none"` in `/health`. An unexpected assembly exception still exits non-zero. A missing model set is a visible degraded state; the process never substitutes a hidden default.
8. `/health` gains:

   ```json
   "model_config": { "source": "catalog|config|none", "authoritative": true, "degraded": false }
   ```

   Any "started but no model is available" state must appear in the health check, not only in a log line.

### 9.2 Fallback matrix

| Plugin state | Explicit provider injected | Default model / `default` instance | `model_config_state` | `/health.allowed_models` |
|---|---|---|---|---|
| enabled with valid entries | either | catalog `default_id`; the `default` instance does not take part in routing | `catalog` | catalog ids |
| enabled with zero valid entries | no | none (`MissingProvider`) | `none` | `[]` |
| enabled with zero valid entries | yes | injected provider | `config` | provider model list |
| disabled or missing | no | none (`MissingProvider`) | `none` | `[]` |
| disabled or missing | yes | injected provider | `config` | provider model list |
| enabled with entries, all invalid | no | none (`MissingProvider`) | `none` | `[]` |

The last row is the important one: "enabled" does not mean "usable". Authority counts valid entries, not the enable flag.

`config.ini` does not carry model credentials or a model list. The `"config"` state is established when the app is assembled with an explicitly injected provider, as an embedder or a test does. A runtime plugin unload calls `refresh_model_config()`, which moves the app to `"none"` and installs `MissingProvider`; it does not return to an injected provider.

In the authoritative state the `default` instance is barely used. Every request carries a catalog id and `resolve` hits; the default only guards the case where the allowed list is empty or the fallback flag is enabled. An absent default credential therefore does not affect conversation, and the default may be `MissingProvider`.

### 9.3 Settings save

`settings_panel.apply_host()` does not mutate provider attributes. After the router wraps the provider, `getattr(app, "provider")` returns the router, `hasattr(provider, "base_url")` is false, and a direct write would be silently skipped while the page reports "saved" — the process would still use the old model.

The model configuration path is:

1. The plugin declares `settings-schema.json`; the settings page renders one card per `[model:<id>]` entry, with add, delete, and per-field editing.
2. Saving rewrites only the `[model:*]` sections and preserves every other section byte for byte. A blank secret field keeps the existing key.
3. After the write, plugin synchronization calls `app.refresh_model_config()`:
   - catalog authoritative: refresh `_available_models`, `live_state.default_model`, and `router.reload_policy`;
   - not authoritative: set `model_config_state = "none"`, clear the list and default id, and install `MissingProvider` through `reload_default`.
4. `app.reload_model_config()` reports the current model source; it does not rebuild a provider from `config.ini` and is not a provider factory.
5. The settings page provides no kernel model section; the only model editor is the plugin form. Unit tests lock the plugin save path and the authority refresh separately.

## 10. Plugin

### 10.1 Directory

```text
plugins/multi_model/
  plugin.py
  plugin-config.ini
  plugin-config.ini.example
  plugin-meta.json
  settings-schema.json
  ui/model-picker.js
  ui/model-picker.css
```

`plugins.ini` gains a `[plugin:multi_model]` section.
`plugin-config.ini` is listed in `.gitignore` (`plugins/multi_model/plugin-config.ini`); the real configuration stays in the workspace. `git ls-files` verifies that the history and the index contain no real configuration.

The directory name is the plugin identity: it appears in URLs, context segment keys, and log prefixes. `multi_model` names the capability rather than a single implementation. The kernel must not contain the name; the architecture gate scans for every plugin directory name at word boundaries.

### 10.2 Configuration format

```ini
[model:chat]
provider = openai
base_url = https://api.example.com
api_key = sk-…
model = chat-model
label = Chat
context_window = 128000
compression_percent = 70
default = 1

[model:messages]
provider = anthropic
base_url = https://api.example.com/messages
api_key = sk-…
model = messages-model
label = Messages
context_window = 200000
compression_percent = 70
max_tokens = 16000
thinking = 1
thinking_budget_tokens = 4096
```

### 10.3 Parsing rules

1. The section name is `[model:<id>]`; `id` is the unique key used by requests and the UI.
2. `model` defaults to `id`.
3. `provider` defaults to `openai`. A value not in `known_kinds()` invalidates the entry and records a diagnostic listing the accepted values.
4. A missing `api_key` or `base_url` invalidates the entry. An obvious template placeholder does not count as configured, so a model cannot take over routing while still carrying a stub key.
5. `context_window` is required and must be a positive integer; it is the denominator for compaction and occupancy.
6. `compression_percent` defaults to `70` and must be an integer in 10–90.
7. At most one `default = 1` is honored. When none is marked, the first valid entry becomes the default. When several are marked, the first wins and the rest are recorded as non-default.
8. `max_tokens`, `thinking`, and `thinking_budget_tokens` apply only to `anthropic` entries. A malformed value invalidates the entry; the same keys on an `openai` entry are ignored.
9. A bad entry affects only itself. A duplicate section or a malformed file is a file-level error: the whole file yields no entries and one invalid record with an empty id.
10. The file is read with `utf-8-sig`. A UTF-8 file saved by a Windows editor may carry a BOM; reading it as plain `utf-8` produces a `MissingSectionHeaderError` that does not point at the real cause.
11. Every diagnostic locates the problem: `[plugin:multi_model] <file path> [model:<id>] <key> invalid: <reason>`. "The configuration is invalid" without a file, entry, and key is not enough to act on.

### 10.4 register

`register(ctx)` does three things:

1. `ctx.add_model_catalog(entries)`
   - `entries` is a callback that re-reads `plugin-config.ini` and returns the `ModelEntry` list;
   - no factory or provider instance is passed; vendor dispatch lives in `provider_registry`.
2. `ctx.add_route("GET", "catalog", handler)`:
   returns `{"ok":true,"models":[{"id","label","provider","context_window","default"}],"default":id,"invalid":[{id,reason}]}`.
   It never returns `api_key` or `base_url`. `invalid` is operational surface: a bad entry must not live only in a log.
3. `ctx.add_boot_script("ui/model-picker.js")`.

`register` returns the disposer list, and the plugin host reclaims it. The plugin also parses the configuration once at startup so a broken file leaves a trace before the user opens the dropdown.

Styles do not go through the backend: the first line of `model-picker.js` calls `window.aiAgentShell.styles.load("ui/model-picker.css")`. The reason is in 11.2.2.

## 11. Shell and UI

### 11.1 Model list source

`WebApi.available_models()` returns `app.available_models()`. That method returns the catalog `ids()` while the snapshot is authoritative, and the assembly-time list otherwise. `/health` and `ui-state` read the same source. Credential fields never appear in a response. `/health` also returns `model_labels`, a map from id to display label, because the shell must render labels without knowing the plugin.

### 11.2 UI bridge

#### 11.2.1 Model bridge

The shell defines the bridge in `agent/shell/web/web_assets/classic/js/plugins/host.js`, next to `window.aiAgentPlugins`:

```js
window.aiAgentShell = window.aiAgentShell || {};
window.aiAgentShell.models = {
  list:     function () { /* → Promise<[{id,label,provider}]> */ },
  current:  function () { /* → string */ },
  select:   function (id) { /* → Promise<boolean> */ },
  onChange: function (fn) { /* → unsubscribe function */ }
};
```

It is not attached to `window.AIA`: `AIA` is the attachment and lightbox namespace of `image-lightbox.js` (`AIA.buildMsgAttachStrip` and similar). Putting models there would create two different things under one name. `aiAgentShell` is a public shell contract, peer to `aiAgentPlugins` and complementary in responsibility.

`list()` reads `/health`: `allowed_models` supplies the ids and `model_labels` supplies the labels. Each item is `{id, label, provider}`, and `provider` is empty because the shell does not know plugin catalogs; the plugin's own `/catalog` endpoint supplies protocol and provider details.

Constraints:

1. The plugin creates its button and menu inside `#modelPickerSlot`; styles come from its own CSS.
2. The plugin does not read shell internals, does not build `/api/chat/send`, and does not modify header elements.
3. `select` is shell-owned: it updates the UI optimistically, writes `/api/chat/ui-state`, and rolls back on failure. The plugin only updates its button text.
4. The bridge remains after the plugin is disabled; there are simply no subscribers and no dropdown.
5. The bridge holds no state. `current()` reads the active tab's model field and `onChange` only forwards. Multiple copies of "the current model" would inevitably diverge.

#### 11.2.2 Style bridge

Plugin assets have two delivery paths, and the model dropdown can use neither directly:

| Path | Endpoint | Injection time |
|---|---|---|
| panel script / panel style | `/api/plugin/<plugin>/_asset/<relative path>` | when the panel opens (`loadPluginStyle`) |
| boot script | `/api/boot-scripts` | page load |
| boot style | none | — |

The dropdown button lives in the composer and belongs to no panel, so it needs a style that takes effect at boot. Instead of adding a backend extension point (`add_boot_style` plus `/api/boot-styles` would touch `PluginContext`, `contributions`, `web_api`, and `web_routes` just to deliver one `<link>`), the shell exposes its existing `loadPluginStyle` on the bridge:

```js
window.aiAgentShell.styles = {
  load: function (relPath) { /* → Promise<boolean>; relPath is relative to the plugin directory */ }
};
```

1. The shell builds `/api/plugin/<plugin>/_asset/<relPath>` using `window.aiAgentPluginCurrent`; the plugin does not build the URL and does not touch `document.head`.
2. It reuses the existing `_pluginStylesLoaded` deduplication table, so the same path is injected once.
3. The injected `<link>` carries `data-plugin-style="<plugin>"`.
4. `applyPluginsChanged` prunes every `<link data-plugin-style>` whose plugin is not in the loaded list, so a disabled plugin does not leave its stylesheet behind.
5. Only paths relative to the plugin directory are accepted. A leading slash is stripped, a URI scheme and any `..` or `.` segment are rejected, and the server resolves the final path and checks it stays inside the plugin directory. String-prefix comparison is not used.
6. When the path is rejected or loading fails, `load` resolves to `false` and injects nothing.

### 11.3 Dropdown and broadcast

1. `agent-ui.html` provides the `#modelPickerSlot` mount point. The built-in `#modelPicker`, `#modelPickerBtn`, and `#modelPickerMenu` controls and their JavaScript and CSS are absent; the slot is the only model mount point.
2. The header keeps `#hdrModel`; `applyModel` writes `模型: <label>` into it.
3. `applyModel(id)` has three responsibilities:
   - write the active tab's `selectedModel`;
   - write the header;
   - notify `aiAgentShell.models.onChange` subscribers.
   A server-provided value is applied even when it is missing from the local cache; the server validates the value when `send` or `ui_state_put` writes it.
4. Conversation-level persistence: the `model` field of `POST /api/chat/send` and `PUT /api/chat/ui-state` is written to `live_state`; the value must be in the model list.
5. Broadcast: `ClassicAdapter.announce_model(cid, model)` pushes `{"type":"conversation","conversation_id":cid,"model":model}` to every SSE channel, structured like `announce_plugins` and not disguised as a kernel event.
6. Trigger points: `send` and `ui_state_put`, when the model value changes.
7. The frontend `conversation` branch handles `ev.model`: only the initiator writes to the server; other tabs update only the header and their local tab field. A receiver writing `live_state` again would cause duplicate writes and races. Display synchronization and state writing are separate concerns.
8. Timing: boot scripts may load before the conversation is restored, so the plugin reads `current()` once at initialization and also subscribes to `onChange`; it cannot rely on the event alone.
9. When the plugin is disabled, `applyPluginsChanged` clears the contents of `#modelPickerSlot` and removes its stylesheet. Without that, the button would remain on the page and call an endpoint that does not exist.
10. Re-enabling works without a page refresh: `applyPluginsChanged` removes the plugin's script node and clears its deduplication entry, `prunePluginMounts` removes its DOM, and the picker's own teardown removes listeners before rebuilding. If this pruning path fails, a refresh is the fallback.

### 11.4 Settings page

1. The settings page has no kernel model section; model entries are maintained only by the multi-model plugin form.
2. The plugin's `settings-schema.json` drives structured editing (add, delete, edit per entry). Saving replaces only the `[model:*]` sections and preserves every other section byte for byte.
3. The save endpoint writes only the plugin's own sections, never kernel configuration.
4. The schema declares the protocol enum, the numeric fields, and the conditional visibility of `max_tokens`, `thinking`, and `thinking_budget_tokens` for `anthropic` entries. Secret fields display only whether a key is configured; an empty value keeps the existing key.

## 12. File list

| File | Role |
|---|---|
| `agent/mechanisms/providers/anthropic.py` | Messages adapter |
| `agent/mechanisms/providers/openai.py` | Chat Completions adapter; strips `provider_meta` from wire messages |
| `agent/mechanisms/providers/tool_schema.py` | shared tool schema normalization |
| `agent/mechanisms/providers/sse.py` | SSE line parsing and stream timeout |
| `agent/mechanisms/provider_registry.py` | kind → builder mapping |
| `agent/mechanisms/provider_router.py` | model id routing and default hot swap |
| `agent/capabilities/model_catalog.py` | catalog, provider cache, authority |
| `agent/capabilities/plugin_context.py` | `add_model_catalog` |
| `agent/capabilities/plugins.py` | `PluginHost(model_catalog=...)` |
| `agent/app.py` | assembly: catalog, router, authority state |
| `agent/app_model_policy.py` | available models, stale model convergence, context window and compaction threshold |
| `agent/core/model_call.py` | `StreamDelta.meta`, `PROVIDER_META_KEY` |
| `agent/core/modules/model_mod.py` | collects `meta` deltas into `model_message` |
| `agent/core/session_log.py` | carries `provider_meta` into assistant messages |
| `agent/core/context.py` | `SERVICE_MODEL_CATALOG` |
| `agent/shell/web/web_api.py` | model list, labels, `/health` model config |
| `agent/shell/web/web_state.py` | `ui-state` model read/write and broadcast |
| `agent/shell/web/web_chat.py` | send-time model validation |
| `agent/shell/web/web_routes.py` | route dispatch for the model endpoints |
| `agent/shell/web/server.py` | startup warning when no model is configured |
| `agent/shell/settings_panel.py` | host settings apply; no model section |
| `agent/shell/plugin_settings.py` | plugin sync and catalog refresh |
| `agent/shell/classic_adapter/channel.py` | `announce_model` |
| `agent/shell/classic_adapter/contract.py` | conversation event contract |
| `agent/shell/web/web_assets/classic/agent-ui.html` | `#modelPickerSlot`, `#hdrModel` |
| `agent/shell/web/web_assets/classic/js/plugins/host.js` | `aiAgentShell.models` and `aiAgentShell.styles` |
| `agent/shell/web/web_assets/classic/js/composer/pickers.js` | `applyModel` |
| `agent/shell/web/web_assets/classic/js/composer/model-sync.js` | conversation model hydration, allowed-list cache |
| `agent/shell/web/web_assets/classic/js/chat/stream.js` | SSE `conversation` branch |
| `plugins/multi_model/plugin.py` | config parsing, catalog source, `/catalog`, boot script |
| `plugins/multi_model/plugin-config.ini` | real configuration, not committed |
| `plugins/multi_model/plugin-config.ini.example` | configuration template with no credentials |
| `plugins/multi_model/plugin-meta.json` | plugin identity and settings tab |
| `plugins/multi_model/settings-schema.json` | structured settings form |
| `plugins/multi_model/ui/model-picker.js` | composer model dropdown |
| `plugins/multi_model/ui/model-picker.css` | dropdown styles |
| `plugins.ini` | `[plugin:multi_model]` |
| `docs/subsystems/plugins.md` | plugin extension points and shell bridges |
| `docs/subsystems/multi-model.md` | plugin configuration and catalog behavior |
| `tests/test_anthropic_provider.py` | Messages adapter tests |
| `tests/test_provider_router.py` | router tests |
| `tests/test_model_catalog.py` | catalog tests |
| `tests/test_multi_model_plugin.py` | plugin tests |
| `tests/test_provider_meta.py` | signature pass-through tests |
| `tests/test_model_provider.py` | wire message tests |
| `tests/test_settings_panel.py` | settings and plugin form tests |
| `README.md` | unit test count |
| `docs/unit-tests.md` | generated test index |

## 13. Tests and acceptance

### 13.1 Unit tests

`tests/test_anthropic_provider.py`:

1. SSE: text deltas, thinking and `signature`, `tool_use` fragment merging, `message_delta` usage, `error`, `ping`, and missing cache fields counted as 0.
2. Message conversion: system merged to the top level, consecutive `tool_result` merged, image `data:` URL and `http(s)` URL, assistant `tool_calls`, leading assistant dropped, dangling `tool_result` dropped, duplicate `tool_use.id` suffixed with its pair renamed.
3. `provider_meta` is replayed only within the current turn and dropped across turns; when thinking is disabled no block is sent; a thinking block without a signature is skipped with a warning.
4. Address construction, HTTP error mapping, and thinking disabled when the budget is insufficient.
5. Event type comes only from `data.type`: deleting the `event:` lines does not change parsing.

`tests/test_provider_router.py`: select an instance by `request.model`, default when the model is empty, `fallback_to_default` behavior for an allowed id, error for an unknown model, `reload_default` effective on the next request, `reload_policy` updates, and substitution of the wire model name.

`tests/test_model_catalog.py`: replace semantics, second source raises `RuntimeError`, `authoritative` follows the current entry count and flips when the catalog becomes empty, callback failure retains the last good set, duplicate id rejected without clobbering the old catalog, provider cache rebuilt after an entry change, disposer unregisters and clears the cache, `options` returns a copy.

`tests/test_multi_model_plugin.py`: a missing file yields an empty catalog without diagnostics; defaults and first-entry default; a BOM file is readable; `context_window` is required and `compression_percent` is range-checked; `anthropic` options are typed and ignored on an `openai` entry; a bad entry affects only itself; placeholder keys are rejected; duplicate sections invalidate the file; the `default` selection rules; the `catalog` response carries no credentials; `register` contributes three disposers and hot-reads the file.

`tests/test_provider_meta.py`: the kernel passes `provider_meta` through unchanged; an unknown subkey is carried rather than validated; an old log without the key still derives its messages; `_to_wire_messages` strips the key from wire messages.

`tests/test_model_provider.py`: wire message construction, tool declaration wrapping, and the reasoning replay rules (a tool message in history keeps its key with empty content; a plain assistant message drops the key).

`tests/test_settings_panel.py`: the kernel model section is absent; the plugin schema renderer masks secrets, rejects an empty required field, and preserves other sections on save; a host settings save does not touch the model catalog.

### 13.2 Integration and acceptance

1. `/health` and `ui-state` return catalog ids; the response body contains no `api_key` or `base_url`.
2. Disabling the plugin empties the model list and sets `/health.model_config.source` to `none`.
3. With no valid model, the web shell starts with a warning, `build_app` still constructs, and a send fails with a clear "no model configured" error.
4. Switching the model updates the header, updates a second tab of the same conversation, and writes the server state exactly once.
5. An unconfigured model id is rejected by both `send` and `ui_state_put`.
6. A bad entry in `plugins/multi_model` does not affect other entries or startup, and appears in `invalid` on the `catalog` endpoint.
7. After the plugin deletes the current model, the next read or send from an old tab converges to the default entry instead of failing.
8. Disabling the plugin clears `#modelPickerSlot` and removes the `<link data-plugin-style>`; re-enabling rebuilds the dropdown without a page refresh.
9. `aiAgentShell.styles.load("../x.css")`, a URI scheme, and an empty path resolve to `false` and inject nothing; the server-side asset route independently rejects paths that escape the plugin directory.
10. `python scripts/ci.py` passes; `check_imports.py` and `check_architecture_hygiene.py` pass, and the kernel contains no `multi_model` occurrence.

## 14. Boundaries and risks

1. `provider_meta` stores thinking text that duplicates `reasoning_content`. That duplication is the price of replaying thinking blocks; compaction and segment accounting do not read it.
2. The key is an optional addition to the persisted format and only moves forward. Old logs without it are read as having no thinking blocks.
3. A model id conflict routes to the wrong gateway, so duplicate ids must be rejected and reported. The id is the shared identity across the configuration file, the UI, and requests; aliases are not supported.
4. A single entry that fails to parse becomes "that entry is invalid" and never prevents the service from starting. A file-level error, such as a duplicate section, invalidates the whole file. If no entry remains valid, `model_config_state` becomes `none` and the shell reports it.
5. The shell has no built-in model picker. Any other client must use `aiAgentShell.models`; it cannot rely on `#modelPickerBtn`.
6. `max_tokens` is required by the Messages protocol and must be greater than the thinking budget; otherwise thinking is disabled for that request.
7. `effort` has no effect on a Messages entry. Depth control by level requires a Chat Completions entry for the same model.
8. The settings page has no kernel model section; models are maintained only by the multi-model plugin.
9. Every `snapshot()` re-reads the plugin configuration. At the current scale the file read is negligible; caching by mtime would add invalidation complexity that is not justified now.
10. Re-enabling a plugin relies on script and mount pruning. If that path regresses, the dropdown does not return until the page is refreshed.

## 15. Engineering constraints

Related standards: [standards-alignment.md](standards-alignment.md).

| Constraint | How the design satisfies it | Verification |
|---|---|---|
| Dependency direction | new files stay inside existing layers; the plugin depends downward only | `check_imports.py` |
| Extension by addition | a new provider is one adapter file plus one registry row; the plugin constructs no instances | review and unit tests |
| The kernel does not know plugin names | the plugin name appears only in the plugin; `MissingProvider` text names no path | `check_architecture_hygiene.py` |
| A single assembly point | `build_app` is the only place that decides authority and degraded state | review |
| Minimal extension | the boot style reuses the existing `loadPluginStyle`; no new HTTP endpoint or contribution type | file list |
| Genuinely immutable read views | entries store canonical JSON; `options` and `snapshot` return copies and tuples | unit test: mutate a returned value and read again |
| Few `Any` | `provider_for` returns `ModelProvider` or `None`; options are the only dictionary | review |
| One name per concept | functions are named for their role; no abbreviation with two meanings | review |
| Folding and repair are separate | `strip_stale_thinking` and `drop_dangling_tool_results` are pure functions | unit tests |
| Contract versioning | `provider_meta` is an optional new key; old logs need no migration | documentation and unit tests |
| Exhaustive end states | `model_config_state` has three values and `/health` exposes all of them | acceptance |
| True streaming | text and reasoning deltas are emitted as they arrive, not accumulated into a list | review |
| One owner per state | the catalog is the only authority; the frontend has no model seed; stale `live_state` values converge at read | unit tests and `check_ui_js.py` |
| Concurrency | `set_source` replaces a reference atomically; `snapshot` is consistent | concurrency test |
| Errors are not lost | bad entries, callback failures, and rejected saves carry location information | unit tests |
| No global exemption | no gate is bypassed for this design | review |
| Key names are not hard-coded | `PROVIDER_META_KEY` is exported by core and shared by reader and writer | review |
| No legacy compatibility layer | no built-in picker, aliases, or empty guards remain | review and file list |
| Secrets do not enter the repository | the real configuration is ignored by Git | `git ls-files` |
| Configuration errors are locatable | `utf-8-sig`; diagnostics include file, section, key, and reason | unit test with a BOM file |
| Configuration drift is checked | the plugin's key set is compared with `settings-schema.json` | `check_config_drift.py` |
| Visible degradation | `none` is reported at startup and in `/health`; no hidden fallback | acceptance |
| Negative tests | duplicate ids, no `provider_meta` on the wire, unknown subkeys ignored, missing signature degraded | unit tests |
| Failure paths are tested | BOM, bad entry, insufficient budget, dangling `tool_result`, unconfigured model | unit tests |
| Coverage ownership | the plugin and the new modules fall inside the `agent` and `plugins` coverage scope | `check_coverage.py` |
| Complexity budgets | per-file limits are enforced by `check_complexity.py`; no new file is added to the allowlist | `check_complexity.py` |
| Documentation matches code | README test count, generated test index, plugin extension points | gates |

### 15.1 Catalog concurrency

`ModelCatalog` is accessed by HTTP request threads and by configuration reloads at the same time. "Replace the catalog" must be atomic:

1. Use `threading.Lock`, not `RLock`. While the lock is held, only a reference swap or a reference read happens; no public method is called. An `RLock` would hide a re-entrancy mistake.
2. `set_source(entries)`: parse, validate, deduplicate, and check id conflicts outside the lock, then build a complete new tuple. Enter the lock only to swap one reference, then leave.
3. `snapshot()`: take the current tuple reference under the lock, leave the lock, and return a `tuple`, never an internal object.
4. Invariant: any snapshot sees either the entire old entry set or the entire new one; a mixture is impossible. No I/O, provider call, or `live_state` write happens while the lock is held.
5. Concurrency test (`tests/test_concurrency.py`): writers alternate two complete batches `a` and `b` while readers take snapshots; every snapshot must come from one batch, `authoritative` must match the entry count, and `default_id` must belong to the snapshot. A second test rotates entry options while readers request providers, and asserts the cache never returns an instance built from the other batch's options.

### 15.2 No model seed in the frontend

The shell must not ship a hardcoded model list. `allowedModels` is only a runtime cache populated from `/health` and `ui-state`; it is not the authority and it is never seeded with model names. When `/health` is unavailable the list may be empty, and the plugin disables the dropdown with a reason in its title. No hardcoded list is used as a fallback.

`check_ui_js.py` rejects vendor model id literals in `agent/shell/web/web_assets/**/*.js`; a negative test feeds a script containing such a literal and asserts failure.

### 15.3 Model display ownership

| Symbol | Owner | Behavior |
|---|---|---|
| `#modelPickerSlot` | shell | mount point only; the plugin renders the button and menu |
| `#hdrModel` | shell | read-only display of `模型: <label>` |
| `applyModel` | shell | writes the active tab's `selectedModel`, the header, and notifies subscribers |
| model list and click validation | plugin and server | the plugin sends the clicked id; the server rejects an id outside the list in `send` and `ui_state_put` |
| `#modelPicker` and its menu | removed | no built-in picker, no dead guard |

Model selection belongs to the plugin; model display belongs to the shell. They are two rendering points, not competing owners.

### 15.4 Deep immutability

- `ModelEntry` is `frozen=True`, and `options` stores canonical JSON.
- `options` returns `dict(entry.options)` on every call; options are flat configuration values, and changing the returned dictionary cannot change the catalog.
- `snapshot()` returns `tuple[ModelEntry, ...]`; a caller cannot mutate the catalog.
- Unit test: mutate the value returned by `options()` or an element of `snapshot()`, read again, and assert the catalog is unchanged.

### 15.5 Negative assertions

1. Two entries with the same `id`: `set_source` rejects the batch, the previous catalog stays, and the error names the source and the id.
2. The wire format produced by either adapter never contains `provider_meta`; it is a kernel-side key only.
3. An unknown `provider_meta` subkey is ignored without raising; the contract is forward-only.
4. A thinking block without a `signature` is not replayed, a visible degradation log is written, and the request is not failed outright.

### 15.6 Documentation and configuration

- `docs/unit-tests.md` is regenerated and checked by `gen_unit_tests_md.py --check`.
- `docs/subsystems/plugins.md` documents the multi-model extension points: catalog authority, `aiAgentShell.models`, and the style bridge.
- `README.md` keeps the unit test count in sync.
- The key set of `plugins/multi_model/plugin-config.ini` matches `settings-schema.json` in both directions and is checked by `check_config_drift.py`.

### 15.7 Complexity and coverage

Coverage is measured over `agent` and `plugins`; the new modules and the plugin fall inside that scope. Per-file complexity limits are enforced by `check_complexity.py`, and no new file is added to the complexity allowlist. A module is not claimed as covered until it is inside the measured scope.
