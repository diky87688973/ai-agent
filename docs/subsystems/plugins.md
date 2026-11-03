# Plugins

## 1. Overview

Plugins are the capability extension points outside the kernel: tools, event subscriptions, context injection, tool-pipeline gating, executors for write tools, HTTP endpoints, and UI are all declared by plugins. **The kernel knows no specific plugin**; it only provides contribution registries and HTTP forwarding.

Built-in capabilities follow the same path: the knowledge base and Skills are plugins. When a plugin's manifest section is removed, its injection sources, tools, panels, buttons, and endpoints are revoked together, with no effect on the kernel.

A plugin is the install/enable unit; it derives slots; the plugin tree describes contributions, and the slot tree is the assembled result. The plugin protocol covers the package, entry, ledger, and lifecycle; the slot protocol covers paths, parent/child structure, replacement, and frozen subtrees.

## 2. Flowchart

```text
plugin root
  │ discover
  ▼
<name>/plugin.py exists? ──no──> skip
  │yes
  ▼
plugins.ini enabled? ──no──> skip
  │yes
  ▼
importlib loads plugin.py
  │
  ▼
register(ctx) -> tools/context/UI/routes
  │
  ▼
ready
  │ unload
  ▼
disposers reverse -> clear contributions -> drop module cache
```

## 3. Slots

Which paths a particular plugin contributes is documented in that plugin's
subsystem guide; the host guide does not enumerate them.

### Exposed

| Slot path | Capability | Key attributes | Replacement / override |
|---|---|---|---|
| `app/boot/plugins` | boot node | owner=module; assembled by SlotTree; failure follows master | Boot-tree nodes are overlaid by path; runtime read-only slots are not replaced |
| `backend/runtime/*` | module contribution | owner=plugin; declared path; removed on unload | Override at the same path with `replace=true`; restore on unload |
| `app/shell/web-ui/*` | UI slot | owner=plugin; declared path; removed on unload | Boot-tree nodes are overlaid by path; runtime read-only slots are not replaced |
| `backend/http/routes/*` | HTTP endpoint | owner=plugin; declared path; removed on unload | Override at the same path with `replace=true`; restore on unload |
### Required

| Dependency path | Capability | Provider | Why |
|---|---|---|---|
| `app/boot/facade` | boot node | host | must be ready before assembly; unavailable propagates as startup/request failure |

## 4. Slot capabilities

### Package layout
A plugin is a directory under `plugins/`; the directory name is the plugin name and the name used in the manifest:

```
plugins/<plugin-name>/
  plugin.py             required. Sole entry point; exposes register(ctx)
  plugin-ui.json      optional. UI path declarations for navigation, input, panes, actions, and settings
  plugin-assembly.json  optional. Startup assembly overlay replacing kernel, host, tool, or shell nodes under app/...
  plugin-meta.json      identity metadata: name / desc / icon / version / settings_tab (read by the settings page)
  plugin-config.ini     optional. The plugin's own configuration; committed when it has no sensitive data, kept out of version control when it carries credentials (as for multi_model)
  settings-schema.json  optional. Structured form declaration for the settings page
  ui/                   optional. Panel styles and scripts
  <other files>         optional. The plugin's own data files, libraries, templates
```

The minimal form is a directory containing only `plugin.py`: it subscribes to events and registers no tools or UI.

`plugin-ui.json` declares UI paths only; backend contributions still come from `add_*` calls in `register(ctx)`. Plugin code must not assemble `app/` paths itself; the tree data is authoritative.

`plugin-assembly.json` is merged into the assembly tree at startup. Any non-frozen node can be replaced, and an `app/...` subtree can be added. Its presence auto-loads the plugin; `"auto_load": true` in `plugin-meta.json` also auto-loads. `enabled = 0` in `plugins.ini` wins over auto-load. Startup nodes take effect after a restart.

Authentication assembly is a frozen subtree: a node with `"frozen": true` cannot be replaced, deleted, or modified by plugins, including its descendants. The auth module remains plugin-shaped, but only the host assembles it.

Kernel, host, tool, and shell startup nodes live in `agent/boot/slot_tree.json`, not in a plugin's `plugin-ui.json`. Replacing a factory there replaces that module; runtime replacement is limited to `scope=session` nodes.

#### Startup assembly overlay

`plugin-assembly.json` nodes are merged after `slot_tree.json` and before assembly:

```json
{
  "version": 1,
  "kind": "assembly",
  "nodes": [
    {
      "path": "app/kernel/modules/model",
      "factory": "assembly:make_model"
    }
  ]
}
```

`factory` is a `module:attribute` inside the plugin directory; the module may use relative imports for sibling files. The factory receives `BuildContext` and returns a `SlotComponent` whose path matches the node. A kernel module can return `KernelModulePlugin` directly. A node with only `metadata` / `requires` keeps the base factory, which replaces a builder or dependency. `replace` defaults to `true`; an explicit `false` rejects an existing path and fails startup. A new node can use any `app/...` path; when its parent does not exist, add the parent in the same declaration.

`frozen: true` marks a host-reserved subtree; overriding the node or any descendant fails startup.

The file's presence auto-adds the plugin to the load manifest; `enabled = 0` in `plugins.ini` disables it. Startup nodes take effect after a restart.

`register(ctx)` returns a disposer, a list of disposers, or nothing. **Every `ctx.add_*` returns a disposer**, and the host records it in the plugin's ledger as it is called (including `add_route` / `add_ui_item` / settings items / context hooks). Returned disposers are merged with that ledger and deduplicated by identity; on unload they run in reverse order. If `register` raises, every registration made through `ctx` is rolled back, so the plugin leaves no partial state.

A plugin may split its implementation into modules in the same directory and reference them with relative imports:

```python
from .library import Thing
```

Subpackages work the same way (`from .tools.eye import DesktopEyeTool`): the loader supplies the `fan_agent_plugins` parent package, and relative imports inside the plugin directory resolve within the package.

### Manifest: `plugins.ini`
The project-root `plugins.ini` lists plugins. A section makes the plugin a load candidate; its `enabled` key is the switch.

```ini
[plugin:skills]

[plugin:knowledge]

[plugin:local-lab]
path = /opt/local/my-plugin
enabled = 1
```

| Field | Required | Description |
|---|---|---|
| Section name | yes | Fixed form `[plugin:<name>]`. The name is the module-name suffix and the default directory name, and must match `[A-Za-z0-9][A-Za-z0-9_-]*` |
| `path` | no | Plugin directory (may be outside `plugins/`). Relative paths resolve against the plugin root; when empty, `plugins/<name>`. After loading, the host resolves assets and the settings editor through `plugin_root(name)`, not a hard-coded `plugins/<name>` |
| `enabled` | no | `0` does not load; absent means `1`. The settings-page switch writes this key |

**Section order matters**: it is the plugin's load position and the **assembly order of plugin segments in context** (see [context.md](context.md#assembly-order)). Plugins less likely to change are placed earlier.

Manifest errors are visible: an invalid name, a missing directory, or a missing `plugin.py` records an `error` report. Startup is not blocked, and the entry is not silently ignored.

#### Mode overlays

A run mode overrides only the differences; it does not copy the full manifest:

```ini
# plugins.headless.ini
[profile]
base = plugins.ini

[plugin:ai_cosplay]
enabled = 0
```

`[profile] base` reads the base manifest first, then overrides explicit fields by plugin name; plugins not mentioned inherit the base, and new plugins are appended at the end. `agent.entry.headless` loads `plugins.headless.ini` by default, `agent.entry.cli` loads `plugins.cli.ini`, and the Web entry continues to use `plugins.ini`. An overlay writes only `path` / `enabled` differences.

<a id="插件自己的配置" name="插件自己的配置"></a>

### Extension points
Every `add_*` on `PluginContext` returns a disposer.

| Extension point | What is registered | Where it lands in the kernel |
|---|---|---|
| `register_tool(tool)` | One `ToolPlugin` | Tool registry (execution still goes through the same pipeline) |
| `set_subagent_tools(tools)` | Tool names this plugin exposes to subagents | Subagent model tool view; an empty list hides all |
| `add_executor(name, fn)` | Commit executor for a write tool | `ExecutorRegistry` (looked up by name when `commit_write` commits) |
| `subscribe(event_type, handler)` | Event handler `handler(event)` | Event bus |
| `add_context_source(fn, meta?)` | Context injection source | `ContextSources` (next section) |
| `add_mode_tail(fn)` | Request-tail text appended after the mode and Todo block | `PromptTail` (see "Request tail") |
| `add_prompt_section(section, fn)` | System-prompt section body | `PromptSections` (same heading merges) |
| `add_pre_gate(gate)` | Pre-execution tool gate | Tool pipeline |
| `add_post_observer(obs)` | Post-execution observer | Tool pipeline |
| `add_route(method, path, handler)` | HTTP endpoint | `/api/plugin/<plugin-name>/…` |
| `add_ui_item(path, kind=..., props=..., order=...)` | UI catalog item: navigation, input, right-panel, runtime, or context segment | UI path registry; `order` is optional, omitted means after the ordered region |
| `add_settings_panel(panel_id, title=...)` | Settings panel | Plugin settings registry → generic settings catalog |
| `add_settings_item(parent, id, kind=..., save=..., load=...)` | Settings item in a panel | Plugin settings registry; save callback is owned by the registering plugin |
| `add_model_catalog(entries)` | Model entries (static sequence or hot-read callable) | `ModelCatalog` (single authoritative source) |
| `set_runtime(obj)` | The plugin's runtime instance | `plugin_host.runtime(name)` returns the same object |

#### Context injection

```python
ctx.add_context_source(fn)   # fn(conversation_id: str) -> list[str]
```

The pipeline calls it whenever it assembles a request, and the produced text is flushed into the plugin segment of the context. Content is **per conversation**: one plugin can inject different material for different sessions.

With metadata, the source also declares the segment's identity in the UI and its subject count:

```python
ctx.add_context_source(
    runtime.build_system_messages,
    {"label": "示例来源",                   # segment name, shown in the UI
     "prefix": "【示例：a.md】\n",           # injection prefix identifying the content
     "count": runtime.attached_count},     # fn(cid) -> int, subject count
)
```

The self-reported `count` aligns **entry by entry** with the returned bodies: when one source returns several bodies, only the first carries the reported count and the rest count as one each. The kernel reads counts by position and never substitutes another segment's number.

- `label` defaults to the plugin name;
- `prefix` is supplied by the source and applied by the host during collection;
- `count` is the callable that supplies the UI's "N items"; without it, a non-empty segment counts as 1 and an empty one as 0;
- the segment key is always the **plugin name** (`plugin:<plugin-name>`); one plugin may register several sources, which share this key and are laid out as separate rows (rows with the same key and label are merged);
- the host writes the assembly position from the manifest; plugins do not declare it.

`plugins/skills` registers several sources: one for the catalog and one for resident bodies; the resource directory goes through a system-prompt section and does not occupy a separate context segment.

#### System prompt sections

```python
ctx.add_prompt_section("## 资源目录", fn)
```

`fn(conversation_id) -> str | list[str]` returns the section body; `section` is the full heading (including `## `). Several plugins may register the same heading; bodies merge in plugin-manifest order, and the heading appears once. Sections enter the system prompt and do not create a `CHUNK_PLUGIN` segment; a failing source or an empty body is skipped.

#### Tools

```python
class MyTool(ToolPlugin):
    name = "my_tool"
    description = "……"
    label = "示例工具"      # short name shown in the UI
    icon = "🧰"            # UI icon (one character)
    parameters = {...}
    def execute(self, arguments): ...

def register(ctx):
    return [ctx.register_tool(MyTool())]
```

`label` and `icon` are **UI display information declared by the tool itself**: the page learns about all tools, including plugin tools, from `/api/tool-labels`, so the frontend does not maintain a table of tool names — otherwise every new plugin tool would require a UI change.

A tool enters the kernel registry and goes through **the same execution pipeline** as built-in tools: gating, confirmation, and the four-step disk-write protocol still apply. A plugin cannot bypass the pipeline.

**A tool exists only while its plugin is loaded**: tools registered by a plugin disappear when its `[plugin:<name>]` section is removed.

#### Commit executors for write tools

A write tool that previews through `confirm_id` obtains its executor by tool name from `commit_write` at commit time:

```python
ctx.add_executor("my_tool", my_executor)   # my_executor(arguments) -> dict
```

Using a registry rather than a static table passed at assembly time decouples the two moments: registration happens at plugin load and lookup at tool call, so their order does not matter; adding another plugin does not require changes to kernel assembly code.

#### Event subscriptions

```python
ctx.subscribe(ev.TURN_ENDED, handler)   # handler(event) -> None
```

Event names are defined in `agent/core/event_name.py` (`ev.*`); the event protocol is described in [architecture.md](../architecture.md). Subscriptions observe; they do not change control flow.

#### Tool-pipeline gates and observers

```python
ctx.add_pre_gate(gate)       # gate(call, ctx) -> GateDecision | None
ctx.add_post_observer(obs)   # obs(call, result, ctx) -> None
```

`pre` gates run before execution; returning `GateDecision(allow=False, reason=...)` rejects the call. `post` observers run after execution. **Gates can add checks, not remove guarantees**: a plugin can block more calls, but it cannot let a call pass that the kernel's own checks would reject.

#### HTTP endpoints

```python
ctx.add_route("GET", "tasks", list_tasks)          # -> /api/plugin/<plugin-name>/tasks
ctx.add_route("GET", "tasks/:sid", get_task)       # path parameters matched by position
ctx.add_route("PUT", "checked", put_checked)
ctx.add_route("DELETE", "tasks/:sid", drop_task)
```

`handler(args)` returns `(status, payload)`; a dict or list payload is returned as JSON (a list is wrapped as `{"ok": true, "items": [...]}`). `args` contains the **query string, path parameters, and request body** (under the `body` key when a body is present).

Supported methods are `GET` / `POST` / `PUT` / `DELETE`. Paths live under `/api/plugin/<plugin-name>/` and **do not support wildcards** apart from `:name` parameter segments: the path must match the declared shape segment by segment, with the same number of segments. "Which endpoints a plugin exposes" is therefore always enumerable and auditable.

#### UI

```python
ctx.add_ui_item(
    "web-ui/right-panel/notes", kind="panel",
    props={"label": "Notes", "action": "notes.open",
           "html": "<div id='notes'></div>",
           "scripts": ["ui/panel.js"], "styles": ["ui/panel.css"]},
    order=10,
)
```

A catalog panel joins the right-column tab container. Its title is the tab label, and the panel body has no heading row of its own. Panel HTML, scripts, and styles are declared by the owning plugin.

Division of responsibility:

| Who | Responsibility |
|---|---|
| Plugin | Panel HTML fragment, script, and styles; how content is rendered |
| Shell | Tab container, enumeration from data, delivering assets by path, same-origin injection |

### Subagent tool visibility
A plugin declares its tool list with `ctx.set_subagent_tools([...])`:

```text
not called: all tools from this plugin are visible to subagents
empty list: no tool from this plugin is visible to subagents
tool-name list: only the listed tools are visible to subagents
```

The kernel filters only the subagent model tool view by this list; it does not copy the registry and does not branch on plugin names. The parent conversation view is unaffected. The tool remains registered; declaring a new list changes visibility again.

A plugin can also use `ctx.is_subagent(cid)` to learn the current conversation role and decide whether to inject request-tail text. `ai_cosplay` declares an empty tool list and registers its voice prompt tail with `subagent_visible=False`, so the tail is not rendered into subagent requests.

### Request tail
`ctx.add_mode_tail(fn, *, subagent_visible=True)` registers `fn(conversation_id) -> str`. The text is appended after the execution mode and Todo progress; it enters only the current request tail, not the system-prompt prefix. Loading or unloading a plugin changes only the tail and leaves the system-prompt prefix unchanged. An empty string takes no space, and a failing source is isolated.

### UI assets
A panel may ship its own styles and scripts, declared as **paths relative to the plugin directory**. The shell serves them at `/api/plugin/<plugin-name>/_asset/<relative-path>`; the **directory root comes from** `plugin_host.plugin_root(plugin-name)` (an external directory declared with `path=` works the same way). Paths are relative and contain no `..`; only text extensions (`.js` `.mjs` `.css` `.html` `.json` `.svg`) are served. CSS class names carry the plugin's own prefix; styles are injected same-origin, with no sandbox.

After a panel script loads, it calls **its own** endpoints through the client provided by the shell, without knowing the URL prefix:

```js
const api = window.aiAgentPlugins.for(window.aiAgentPluginCurrent);
const res = await api.get("files");                       // GET  /api/plugin/<plugin-name>/files
await api.post("generate", { prompt: "..." });            // POST, same prefix
await api.put("checked", { conversation_id, checked });
await api.del("tasks/t-1");                               // DELETE
```

`res` has the shape `{ status, ok, data }`. `api.url(path)` only builds a URL; it sends no request.

#### Script loading

**Context-segment appearance** is registered as a `web-ui/left-panel/context_usage/<key>` UI item with `label` and `color` props. The UI catalog publishes the resulting map through `ai-agent:context-segments`; the context bar does not keep a second color registry.

**Plugin UI scripts and styles** come from the UI catalog item's `props.scripts` / `props.styles`. The catalog loader injects styles first and then executes scripts serially, setting `window.aiAgentPluginCurrent` for each plugin. A panel script renders when its catalog entry is opened.

There is no separate boot-script API, panel list endpoint, or action list endpoint. UI extensions exist only under a declared UI path and are discovered from `GET /api/ui/catalog`.

<a id="壳层公共桥" name="壳层公共桥"></a>

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

### Resources owned by a plugin
| Resource | How to obtain it | Notes |
|---|---|---|
| Dedicated data directory | `ctx.data_dir` | `<data-root>/plugin/<plugin-name>/`; created on first access |
| Kernel App | `ctx.app` | Kernel services already registered, e.g. `ctx.app.registry` / `ctx.app.mesh`; `None` before assembly completes |
| Own runtime | `ctx.set_runtime(obj)` | Registered so the shell can retrieve the same instance by name |
| Manifest rank | Written by the host | Used for assembly order; the plugin neither sees nor manages it |

`ctx.data_dir` means a plugin **sees only its own layer** and does not need to know where the outer directory is. Plugin directories are isolated from each other, so identically named files cannot collide. State belongs here rather than in the plugin directory: the plugin directory is code, the data root is data.

`ctx.app` is for **handler code**, not `register`: plugins load at the end of assembly, when the App has not yet been handed to the host, and handlers run only when a request arrives. `ctx.set_runtime` is called during `register`.

### Model catalog source
`add_model_catalog(entries)` gives a set of model entries to the kernel's `ModelCatalog`. Entries are `ModelEntry` objects with `id` / `provider` / `label` / `options` / `is_default`; provider-specific keys such as `base_url`, `api_key`, and `model` live in `options`. The kernel resolves the request's id to the matching provider instance; an unknown id is an error and is not silently routed to another model.

The catalog is the single authoritative source for model routing while its plugin is loaded; with no valid entries the model list is empty. Entry construction is the plugin's responsibility; the kernel normalizes, validates, and consumes snapshots. Only one source may be registered: a second source is refused and logged, and the plugin still loads.

`multi_model` implements this extension point; its configuration and behavior are documented in [multi-model.md](multi-model.md).

### Boundaries
<a id="插件信任模型" name="插件信任模型"></a>

#### Plugin trust model

**A plugin is as trusted as local code.** Once loaded, `plugin.py` runs in the same process and interpreter: it can read the whole disk, make network requests, and register tools and HTTP endpoints; UI catalog HTML fragments and scripts are injected into the page's same-origin context. **There is no sandbox.**

Therefore:

| Can expect | Cannot expect |
|---|---|
| Conventions and namespace constraints (endpoint prefix, asset path validation) | A malicious or tampered plugin stopped by the runtime |
| Load-time source path and entry-file summary recorded in the log (sha256 prefix / mtime / bytes) | Subprocess isolation or privilege reduction (see the [evaluation note](../adr/plugin-subprocess-isolation.md)) |
| With the switch enabled, loading refused for paths outside the `plugins/` tree | Automatic immunity to "bad code in a trusted directory" |

The trust boundary rests on three constraints:

- `plugins.ini` and the plugin directories are part of version control or the deployment manifest;
- `[agent] plugin_tree_only = 1` (or the environment variable `AI_AGENT_PLUGIN_TREE_ONLY=1`) restricts loading to the `plugins/` tree;
- the load log has the form `[plugin.load] <name> source=… sha256=… mtime=… bytes=…` and can be compared with deployment hashes.

UI and endpoint conventions:

- CSS class names carry the plugin's own prefix, and styles are injected same-origin;
- endpoint registration is limited to the `/api/plugin/<plugin-name>/` namespace; kernel routes are not open for registration;
- panel data comes from the plugin's own endpoints;
- segment name and color, tool label and icon are declared through the UI catalog and consumed by the shell. The server provides data (segment key / name / count); plugin UI scripts render their own panels.

### Adding a plugin
1. **Create the directory**: `plugins/<name>/`. The directory name is the plugin name and the section-name suffix in `plugins.ini`. Names must match `[A-Za-z0-9][A-Za-z0-9_-]*`.

2. **Write the entry point**: `plugin.py` exposes `register(ctx)`. A minimal implementation registers one capability:

   ```python
   def ping(args):
       return 200, {"ok": True}

   def register(ctx):
       ctx.add_route("GET", "ping", ping)
   ```

   To split files, use modules in the same directory with relative imports (`from .library import Thing`).

3. **Add metadata and form**: `plugin-meta.json` declares `name` / `desc` / `icon` / `version`. For a structured form, add `settings-schema.json` declaring `kind` and `fields` (for `sections`, also `section_prefix` and `identity`). Commit `plugin-config.ini` when it holds no secrets; secret-bearing plugin configuration is excluded by `.gitignore`.

4. **Register UI** (optional): `ctx.add_ui_item(path, kind=..., props=..., order=...)` under a declared UI path. Assets live in the plugin directory and are served at `/api/plugin/<name>/_asset/<relative-path>`. `order` is optional; positive values run first, omitted values run after positives, and negative values run last (`-1` is last, `-2` second last).

5. **Add it to the manifest**: write a `[plugin:<name>]` section in `plugins.ini`, optionally with `path` / `enabled`. A section makes it a candidate; `enabled` decides whether it loads.

6. **Validate**: `python scripts/ci.py` runs dependency-direction, architecture, comment-style, and unit-test gates; plugin endpoints and UI are covered by acceptance scripts such as `scripts/acceptance_web.py`.

## 5. Details

### 补充

```
discover     scan the plugin root for <name>/plugin.py — enumerate plugins on disk
load         load each manifest entry: importlib with a dynamic module name → register(ctx)
             called at the end of assembly, when kernel services are registered and handlers can obtain ctx.app
unload       call disposers in reverse; then clear contributions by plugin name, drop the runtime, and remove module cache entries
```

Discovery skips directories whose names start with `_` or `.`.

`importlib` loads each plugin under a dynamic module name, so the shell cannot import the same module object. A plugin that wants the shell to operate on its runtime must register it with `ctx.set_runtime(obj)`; `plugin_host.runtime("<plugin-name>")` returns that same instance. Without registration, the two sides hold separate copies of the state.

The unload fallback removes routes and UI catalog entries by plugin name. Event subscriptions are removed by the disposers registered through `ctx.subscribe`.



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
