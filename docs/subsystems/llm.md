**English** | [中文](llm.zh.md)

# Model calls

`agent/mechanisms/providers/` defines the model-call protocol and its concrete implementations; routing lives only in `provider_router.py`.

## Reasoning replay budget

In thinking mode the model produces a chain of thought each turn (`reasoning_content`). It is an **intermediate draft** produced by the model: replaying it in full adds a large block to every request that is **guaranteed to miss the cache**, and the prefix changes with every request within the same turn, so the prefix cache cannot take hold.

The budget is controlled by `[context] reasoning_replay_tokens` (tokens):

| Value | Behavior |
|---|---|
| `-1` | No budget clipping (the form the official documentation uses when `tools` are present); historical turns still follow the replay rule below |
| `0` | Replay nothing |
| Positive (default `8000`) | Over budget, **keep both ends and replace the middle with an omission marker that states the approximate number of omitted tokens** |

Keeping both ends instead of only the tail works because the beginning of the reasoning says what the model intends to do and the end says what it concluded; the model can infer the middle from those ends.

**The key must not be dropped**: in Upstream thinking mode, an assistant message carrying `tool_calls` must pass `reasoning_content` back to the API (an empty string is accepted); a missing key causes a 400 `The reasoning_content in the thinking mode must be passed back to the API`. Historical tool messages therefore clear only the content and keep the key; older records that never stored reasoning for tool messages get an empty string added. Plain-text assistant messages have no such requirement, and historical turns still drop the key entirely. If a historical tool message loses the key, **the whole session gets a 400 on the second question**.

Budget trimming happens at **assembly time** (`set_dialogue` calls `clip_reasoning`), not on the wire: segment accounting, budget estimation, and the assembled request all see the same copy. If they diverged, the UI would count the window as full and compaction would trigger too early or too late. The fact stream is unaffected: recorded facts and UI events still carry the full reasoning. When building the wire request, the adapter only applies the historical-replay rule above to reasoning; it does not re-run budget trimming.

## Protocol

```python
class ModelProvider:
    def stream(self, request: LogicalRequest) -> Iterator[StreamDelta]: ...
```

Consumers depend only on this interface. Changing the gateway or model requires only a different provider instance.

| Implementation | Purpose |
|---|---|
| `EchoProvider` | Network-free; the first request issues one `echo` tool call, and after the result arrives it returns a text response |
| `MissingProvider` | Placeholder used when no model is available; does not access the network |
| `CompatibleProvider` | Adapter for the Compatible protocol; parses the SSE stream |
| `NativeProvider` | Adapter for Native Messages; consumes native event frames |

## Request body

`CompatibleProvider.stream()` builds this request body:

```json
{
  "model": "<model selected for this session>",
  "messages": [...],
  "reasoning_effort": "<from LogicalRequest.effort>",
  "thinking": {"type": "enabled"},
  "temperature": 0.2,
  "stream": true
}
```

Value sources and local handling:

- **`reasoning_effort` comes from the request** (`LogicalRequest.effort`, resolved from session-level settings), not from a hard-coded constant. The official values are `none` / `low` / `high` / `max`; the default is `high`, and non-empty values are sent as-is.
- **`temperature` has no effect in thinking mode**: Upstream's official documentation states that thinking mode does not support the parameter (**it does not error, but it also has no effect**), so `0.2` only matters for non-thinking requests or other compatible gateways.
- **Local models strip the `thinking` / `reasoning_effort` / `temperature` keys entirely.** `_is_local_model()` decides this (the model name is `local-model` or starts with it); the local model behind the browser page does not support these parameters.

## Address derivation

`_chat_completions_url(base_url)` expands a base URL into the full endpoint and is idempotent:

| Base URL form | Result |
|---|---|
| Already contains `/chat/completions` | Unchanged |
| Last segment is a version segment (`v1` / `v4` …) | Append `/chat/completions` directly |
| Anything else | Append `/v1/chat/completions` |

## Stream parsing

`parse_sse_lines()` processes only `data:` lines and skips `event:` / `id:` / comments; `[DONE]` terminates the stream; a line whose JSON fails to parse is **skipped without aborting**.

`_assemble_stream_deltas()` converts the chunk sequence into `StreamDelta`s:

| Delta type | Source field |
|---|---|
| Text | `delta.content` |
| Reasoning | `delta.reasoning_content` or `delta.reasoning`; the final snapshot uses the longer field (`_best_reasoning_field()`) and fills in a missing suffix |
| Tool calls | `delta.tool_calls` fragments |
| Usage | `usage` (the last non-empty value in the stream) |

## Tool-call fragment merging

In a streamed response a tool call may be split across fragments: the first fragment carries the `id` and the function name, and later fragments carry only string pieces of `arguments`.

`_merge_tool_call_fragments()` merges fragments by array index to build a complete `ToolCallRequest`.

`_tool_calls_from_snapshot_message()` is a fallback: some gateways provide a complete `message.tool_calls` in the final frame, used only when fragment merging produced no calls.

## Images

Images are **sent through unchanged**: capability is not guessed from the model name, and no lossy downgrade strips them — stripping is lossy, and one wrong guess means the user sent an image while the model sees only a placeholder. Whether images are included, and how many, is controlled by `[context]`'s `image_turns` / `image_max` (see [context.md](context.md)).

## Error mapping

`ModelRequestError` carries a user-facing detail and the HTTP status code.

`_http_error()` maps Upstream gateway status codes to readable hints (400 / 401 / 402 / 422 / 429 / 500 / 503) and appends the upstream message (truncated to 800 characters). Non-Upstream gateways get the raw text (truncated to 8000 characters).

These hints are **shown directly to the user**, so the wording only describes which side failed.

A gateway counts as Upstream only when the model name starts with the Upstream provider's identifier or the base URL contains that identifier.

## Request tracing

Before sending, the adapter prints the URL and a one-line summary built by `describe_request()`: model name, message count, tool count, image count, and request body size.

- `AI_AGENT_LOG_REQUESTS=0` disables it;
- `AI_AGENT_LLM_LOG` sets the output path; when empty, the log goes to `%TEMP%\fan_agent_llm_requests.log` (falling back to the current directory when both `TEMP` and `TMP` are missing).

Both stderr and the log file receive the summary; image details are listed one by one (message index, role, image count, and character count per image).

## Further reading

- [architecture.md](../architecture.md): ports and request contract
- [context.md](context.md): assembly of `messages`
- [guide/config.md](../guide/config.md): host configuration
