# Plugins

## Declaration and assembly

The sole capability declaration is plugin-slots.json. See the [canonical protocol](../plan/plugin-slots-protocol.md) and [implementation boundaries](../plan/plugin2-hotplug.md).

Discovery reads plugin-meta.json, applies the manifest, merges and validates fragments, constructs nodes, binds projections with SlotBinder, and publishes a frozen snapshot. Python factories receive BuildContext and declared requires dependencies; they return implementations rather than registering capabilities. Pure declarative plugins need no Python entry. There is no register(ctx) or ctx.add_* contribution API.

## Extension points

Use tool for model tools, route with method for namespaced plugin HTTP endpoints, event for host notifications, event-channel for plugin event definitions, provider with props.target for context/prompt/model catalog contributions, assembly-hook, executor, setting, runtime, and the ui-* kinds for UI. Message renderers are declared through ui-tool-shell.props.renderer and bound only against the effective catalog with matching ownership.

A plugin event is identified by its full declaration path app/plugins/<owner>/events/<name>. An event subscriber uses requires.event to reference that declaration. Missing or invalid dependencies reject the candidate configuration; strong dependencies do not silently degrade.

## Lifecycle

Plugin contributions support hotplug with read leases, candidate construction, rollback, reverse resource disposal and queryable deferred operation outcomes. Explicit reload reads filesystem changes. Host or kernel replacement requires restart. extend/wrap composition is not implemented and is rejected. Disabled mount providers make UI contributions dormant; missing strong requires dependencies still reject publication.

Registries are projections, not independent declaration sources. New tools, routes and displays need no concrete plugin branches in the kernel. New fundamental protocol kinds remain host architecture changes.

## Ownership and trust

Private UI, configuration, icons, libraries and licenses belong inside plugins/<name>/. Shared presentation infrastructure belongs to agent/shell/web/. Asset delivery does not imply capability activation. Plugin code has local-code trust, not a Python sandbox. Path restrictions constrain origins; source hashes are diagnostics, not signature verification. Secrets must not enter version control. BuildContext.data_dir supplies the plugin-owned runtime data directory.

## Configuration and references

### Plugin configuration
A plugin's own configuration lives in **`plugin-config.ini` in the plugin directory** and contains only the plugin's own keys. The plugin reads it with `agent.config.load_ini()`:

```
plugins/<plugin-name>/plugin-config.ini     ← plugin settings only
plugins/<plugin-name>/plugin-meta.json      ← identity declaration
```

**The kernel's `config.ini` contains kernel settings only; no plugin settings belong there.** Plugin settings live in the plugin directory and are installed, removed, and deleted with the plugin. `plugin-config.ini` is the only configuration file the plugin reads; when it does not exist, the plugin uses code defaults. A format example such as `plugin-config.ini.example` is never read at runtime. Configuration for AI Speak, Visual Operator, the knowledge base, and Skills is committed; `multi_model` configuration is excluded by `.gitignore`.

The file name is fixed as `plugin-config.ini` (not `config.ini`): `config.ini` refers to kernel configuration, and two files with the same name would be ambiguous.

**The settings page can edit only the plugin's own sections.** Identity and the switch are not in this file: `name` / `desc` / `icon` / `version` / `settings_tab` come from `plugin-meta.json`, and `enabled` from `plugins.ini`. When `settings_tab` is non-empty and the plugin is enabled and configurable, the settings page adds a sidebar entry with that name; clicking it opens the plugin's configuration editor directly. The editor has three kinds:

- `kind: sections`: renders schema-driven entries that can be added and removed;
- `kind: fields`: renders a schema-driven field form; saving updates only the declared fields;
- anything else: a text editor for the plugin's own keys; saving replaces the corresponding sections.

**A plugin with no editable settings declares it**: with `"config": "false"` in `plugin-meta.json`, the settings page does not render a Settings button (the criterion is the plugin's declaration, not the kernel guessing whether a configuration file exists). `plugins/rules` is one such plugin: it has a switch but no configuration.

In schema-driven forms, secret fields report only whether a value is configured; leaving the field empty keeps the stored value.

The plugin reads and interprets its own keys: the kernel does not parse plugin configuration, and `agent/config.py` has no reader for plugin sections. Relative paths such as `dir` resolve against the **project root** (not the plugin directory), matching kernel configuration. A plugin does not need a kernel API to locate itself: `Path(__file__).resolve().parent` is its directory.

Permission boundary: plugin configuration that contains secrets is not committed; a process on the same machine that can read the plugin directory can read its configuration. This is the same boundary as "a plugin is as trusted as local code" (see "Plugin trust model").

## 6. Further reading

| Topic | Document |
|---|---|
| how injection sources enter context and how assembly order is determined | [context.md](context.md) |
| file collection, selection, and injection in `knowledge` | [knowledge.md](knowledge.md) |
| catalog entries and the settings form in `multi_model` | [multi-model.md](multi-model.md) |
| three-layer disclosure and the `skills` tool | [skills.md](skills.md) |
| screenshots, coordinate contract, and platform backends | [visual-operator.md](visual-operator.md) |
| tool registration, execution pipeline, and disk-write protocol | [tools.md](tools.md) |
| HTTP routing and UI bundling | [shell.md](shell.md) |
| full configuration reference | [config.md](../guide/config.md) |

<a id="壳层公共桥"></a>

#### Shell bridge

When a plugin places UI **outside a panel** (composer, page header), it uses the shell bridge instead of building URLs, reading shell internals, or touching `document.head`:

```js
// Models: list() → Promise<[{id,label,provider}]>; current() → string;
// select(id) → Promise<boolean>; onChange(fn) → unsubscribe function.
const models = window.aiAgentShell.models;
const stop = models.onChange((id) => renderLabel(id));
await models.select("target");
stop();

// Styles: relPath is relative to the plugin directory; each path is injected once.
window.aiAgentShell.styles.load("ui/model-picker.css");
```

`aiAgentShell` is a peer of `aiAgentPlugins`: the former provides shell capabilities, the latter the plugin's own endpoints. The bridge **does not hold the current model**; `current()` reads the active tab on every call, because multiple copies of that state would diverge. `select()` updates the UI optimistically, then writes `/api/chat/ui-state` and broadcasts; if the write fails it rolls back and returns `false`. Values delivered by the server (session restore / SSE) are not restricted by the local list.

`styles.load()` reuses the panel-style deduplication table and the `/api/plugin/<plugin>/_asset/` route; absolute paths, drive letters, protocols, and `..` return `false`. After a plugin is disabled, `applyPluginsChanged` removes `<link>` elements carrying `data-plugin-style` and clears children of `#modelPickerSlot` whose `data-plugin` is no longer in the loaded set.

Plugin changes are applied without a page refresh: the shell refreshes the UI catalog and loaded-plugin set, closes panels of unloaded plugins, and clears the script and style caches so that re-enabling a plugin runs its scripts again.

#### Host settings panels and items

Settings are registered through the plugin settings registry, not through host DOM. A plugin may add a panel with `add_settings_panel(panel_id, title=...)` and an item with `add_settings_item(parent, item_id, kind=..., save=..., load=...)`.

Supported item kinds are `text`, `search`, `number`, `select`, `checkbox`, `textarea`, and `password`; `select` requires an explicit option list. Item IDs are namespaced as `settings/<panel>/<item>`.

The plugin that owns an item provides its `save` callback. The host only renders the typed control and submits all changed plugin values to the generic settings entry. The plugin system dispatches each item to its owner's callback; the callback persists and applies its own value, then returns success or failure. A plugin must not create, patch, or query settings DOM.

When a plugin is unloaded, its panels and items disappear immediately; the plugin's own persisted value is retained for the next enable.

#### Conversation switch notification

When panel content carries per-conversation state (selections, for example), it must refetch on every conversation switch. The shell broadcasts a generic event and **whoever needs it subscribes**:

```js
document.addEventListener("ai-agent:conversation-changed", function () {
  if (document.getElementById("kbBody")) render();
});
```

The shell names no plugin and does not require plugins to know about the shell.


<a id="插件信任模型"></a>

Plugins have local-code trust as described above; origin restrictions are not a sandbox.
