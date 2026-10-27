**English** | [中文](multi-model.zh.md)

# Multi-model (`multi_model` plugin)

`multi_model` registers its model entries as the kernel's model-catalog source: each entry carries its gateway, protocol, and credentials, and the kernel routes a request by its model id to the matching provider instance. The plugin also renders the model dropdown in the composer and declares the 「模型」 entry on the settings page.

For the plugin mechanism itself, see [plugins.md](plugins.md); for protocol request bodies and stream parsing, see [llm.md](llm.md).

## Package layout

```
plugins/multi_model/
  plugin.py                  entry: configuration parsing, catalog source and endpoint, boot script
  plugin-config.ini          actual configuration (not committed)
  plugin-config.ini.example  configuration template (committed)
  plugin-meta.json           identity metadata (name / desc / icon / version / settings_tab)
  settings-schema.json       structured form declaration for the settings page
  ui/model-picker.js         composer model dropdown
  ui/model-picker.css        dropdown styles
```

## Configuration

One section per model, `[model:<id>]`:

```ini
[model:model-a]
provider = anthropic
base_url =
api_key =
model =
label =
context_window =
compression_percent = 70
max_tokens =
thinking = 0
```

| Key | Default | Notes |
|---|---|---|
| Section name | Required | `[model:<id>]`; the form generates `id` from the entry's position and does not show it in the UI |
| `provider` | `openai` | Protocol and endpoint form: `openai` (Chat Completions) or `anthropic` (Messages); an unknown value invalidates only this entry |
| `base_url` | empty | Gateway address; it must accept this key |
| `api_key` | empty | Authentication key; a template placeholder (for example `sk-changeme`) does not count as configured |
| `model` | equal to `id` | Wire-format model name sent to the gateway |
| `label` | equal to `id` | Display name in the dropdown and the top bar |
| `context_window` | Required | Maximum context window of the model (tokens); used for the usage percentage and the compaction threshold |
| `compression_percent` | `70` | Compaction trigger percentage, 10–90; threshold = floor(window × percentage / 100) |
| `default` | none | `1` on at most one entry; with none marked, the first valid entry is the default |
| `max_tokens` | `16000` | Messages only: **reply** token limit, not the context length |
| `thinking` | `1` | Messages only: `1` sends `enabled`, `0` sends `disabled` explicitly; when omitted the adapter enables thinking |
| `thinking_budget_tokens` | `4096` | Messages only: thinking budget, ≥ 1024 and smaller than `max_tokens` |

An invalid entry affects only itself: a missing `api_key` or `base_url`, an unknown `provider` value, or a malformed number drops that entry from the catalog while the rest stay usable. Duplicate ids or duplicate section names invalidate the whole file. Diagnostics go to stderr as `[plugin:multi_model] <file> [model:<id>] <key> 无效：<reason>`.

The file is read with `utf-8-sig`, so a BOM is accepted.

### One gateway, two protocols

`provider` determines the protocol and endpoint form; `model` only sets the model name sent to the gateway. When one gateway serves both protocols, write one section per protocol under different ids:

```ini
[model:chat]
provider = openai
base_url =
api_key  =
model    =

[model:messages]
provider = anthropic
base_url =
api_key  =
model    =
max_tokens =
```

INI section names must be unique, so the two protocols cannot share one id.

### Thinking mode

- `thinking = 0` disables thinking explicitly: the request body carries `{"type":"disabled"}`. When the key is omitted, the adapter enables thinking with `thinking_budget_tokens`.
- `thinking_budget_tokens` must be ≥ 1024 and smaller than `max_tokens`. Otherwise the adapter writes a stderr diagnostic and turns thinking off for the turn; the request is still sent.
- Thinking depth: the Messages protocol uses `budget_tokens`, the Chat Completions protocol uses the request's `reasoning_effort`, which comes from the session setting. The adapter does not send `output_config`.
- Some gateways ignore `temperature` in thinking mode; the Messages adapter sends no `temperature` field.
- In a turn with tools, thinking blocks must be replayed verbatim with `tool_use`; without them the gateway returns 400. Historical turns do not replay them. When a block is missing and cannot be restored, the adapter turns thinking off for the turn and leaves a diagnostic.
- In thinking mode the key must match the gateway that `base_url` points at; otherwise the gateway rejects it.

## Catalog authority

Once the plugin is loaded, the model catalog is the only source; when no entry is valid the service still starts and the model dropdown on the main page is empty. Saving the plugin configuration takes effect without a restart.

`GET /api/plugin/multi_model/catalog` returns a catalog snapshot without `api_key` or `base_url`:

```json
{
  "ok": true,
  "models": [{"id": "1", "label": "Model A", "provider": "openai",
              "context_window": 1000000, "default": true}],
  "default": "1",
  "invalid": []
}
```

## Settings page

The plugin declares `settings-schema.json`, and the settings page renders it as a structured form: one card per entry, with add, delete, and per-field editing; fields such as `max_tokens` and `thinking` are shown or hidden in place when `provider` changes. Saving rewrites only the `[model:*]` sections and keeps every other section byte for byte; a secret field reports only whether it is configured, and an empty value keeps the stored one.

The settings page has no kernel model section; model configuration is edited only through this plugin's structured form.
The plugin declares `settings_tab` as 「模型」 in `plugin-meta.json`, so once it is enabled the settings sidebar shows the 「模型」 entry directly; it opens the same multi-model form without a back button.

## Model dropdown

The plugin registers a boot script with `ctx.add_boot_script("ui/model-picker.js")`; the shell provides only the `#modelPickerSlot` container. The script reads entries from `/catalog` through `window.aiAgentPlugins.for()`, uses `window.aiAgentShell.models` to read the current selection and write changes back, and falls back to `shell.models.list()` when the catalog endpoint is unavailable. Styles are injected through `window.aiAgentShell.styles.load()`. The bridge contract is in [plugins.md](plugins.md#壳层公共桥).

Neither the button nor the menu caps its width: the model name is the only way to tell entries apart, and cutting the two entries for one gateway (`model-a-openai`, `model-a-anthropic`) to a shared prefix would hide which one is selected. The menu follows its items with `width:max-content` and is clamped only at the viewport edge (`100vw - 24px`).

## Further reading

- [plugins.md](plugins.md): plugin package shape, extension points, UI assets, lifecycle
- [llm.md](llm.md): request bodies, address derivation, stream parsing, error mapping
- [../guide/config.md](../guide/config.md): host configuration keys
