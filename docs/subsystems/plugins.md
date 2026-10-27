**English** | [中文](plugins.zh.md)

# Plugins

Plugins are the capability extension points outside the kernel: tools, event subscriptions, context injection, tool-pipeline gating, executors for write tools, HTTP endpoints, and UI are all declared by plugins. **The kernel knows no specific plugin**; it only provides contribution registries and HTTP forwarding.

Built-in capabilities follow the same path: the knowledge base and Skills are plugins. When a plugin's manifest section is removed, its injection sources, tools, panels, buttons, and endpoints are revoked together, with no effect on the kernel.

## Package layout

A plugin is a directory under `plugins/`; the directory name is the plugin name and the name used in the manifest:

```
plugins/<plugin-name>/
  plugin.py             required. Sole entry point; exposes register(ctx)
  plugin-meta.json      identity metadata: name / desc / icon / version / settings_tab (read by the settings page)
  plugin-config.ini     optional. The plugin's own configuration; committed when it has no sensitive data, kept out of version control when it carries credentials (as for multi_model)
  settings-schema.json  optional. Structured form declaration for the settings page
  ui/                   optional. Panel styles and scripts
  <other files>         optional. The plugin's own data files, libraries, templates
```

The minimal form is a directory containing only `plugin.py`: it subscribes to events and registers no tools or UI.

`register(ctx)` returns a disposer, a list of disposers, or nothing. **Every `ctx.add_*` returns a disposer**, and the host records it in the plugin's ledger as it is called (including `add_panel` / `add_route` / `add_action` / `add_boot_script` / `add_ctx_segment_style`). Returned disposers are merged with that ledger and deduplicated by identity; on unload they run in reverse order. If `register` raises, every registration made through `ctx` is rolled back, so the plugin leaves no partial state.

A plugin may split its implementation into modules in the same directory and reference them with relative imports:

```python
from .library import Thing
```

Subpackages work the same way (`from .tools.eye import DesktopEyeTool`): the loader supplies the `fan_agent_plugins` parent package, and relative imports inside the plugin directory resolve within the package.

## Manifest: `plugins.ini`

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

### Mode overlays

A run mode overrides only the differences; it does not copy the full manifest:

```ini
# plugins.headless.ini
[profile]
base = plugins.ini

[plugin:ai_speak]
enabled = 0
```

`[profile] base` reads the base manifest first, then overrides explicit fields by plugin name; plugins not mentioned inherit the base, and new plugins are appended at the end. `agent.entry.headless` loads `plugins.headless.ini` by default, `agent.entry.cli` loads `plugins.cli.ini`, and the Web entry continues to use `plugins.ini`. An overlay writes only `path` / `enabled` differences.

<a id="插件自己的配置" name="插件自己的配置"></a>

## Plugin configuration

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

Permission boundary: plugin configuration that contains secrets is not committed; a process on the same machine that can read the plugin directory can read its configuration. This is the same boundary as "a plugin is as trusted as local code" (see below).

## Extension points

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
| `add_panel(id, ...)` / `add_action(id, ...)` | Panel / composer button | Contribution registry (the shell enumerates data) |
| `add_ctx_segment_style(label=..., color=...)` | Context-segment appearance | Contribution registry → `/api/ctx-segment-styles` |
| `add_boot_script(rel_path)` | Startup preload script (works without a panel) | Contribution registry → `/api/boot-scripts` |
| `add_model_catalog(entries)` | Model entries (static sequence or hot-read callable) | `ModelCatalog` (single authoritative source) |
| `set_runtime(obj)` | The plugin's runtime instance | `plugin_host.runtime(name)` returns the same object |

### Context injection

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

### System prompt sections

```python
ctx.add_prompt_section("## 资源目录", fn)
```

`fn(conversation_id) -> str | list[str]` returns the section body; `section` is the full heading (including `## `). Several plugins may register the same heading; bodies merge in plugin-manifest order, and the heading appears once. Sections enter the system prompt and do not create a `CHUNK_PLUGIN` segment; a failing source or an empty body is skipped.

### Tools

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

### Commit executors for write tools

A write tool that previews through `confirm_id` obtains its executor by tool name from `commit_write` at commit time:

```python
ctx.add_executor("my_tool", my_executor)   # my_executor(arguments) -> dict
```

Using a registry rather than a static table passed at assembly time decouples the two moments: registration happens at plugin load and lookup at tool call, so their order does not matter; adding another plugin does not require changes to kernel assembly code.

### Event subscriptions

```python
ctx.subscribe(ev.TURN_ENDED, handler)   # handler(event) -> None
```

Event names are defined in `agent/core/event_name.py` (`ev.*`); the event protocol is described in [architecture.md](../architecture.md). Subscriptions observe; they do not change control flow.

### Tool-pipeline gates and observers

```python
ctx.add_pre_gate(gate)       # gate(call, ctx) -> GateDecision | None
ctx.add_post_observer(obs)   # obs(call, result, ctx) -> None
```

`pre` gates run before execution; returning `GateDecision(allow=False, reason=...)` rejects the call. `post` observers run after execution. **Gates can add checks, not remove guarantees**: a plugin can block more calls, but it cannot let a call pass that the kernel's own checks would reject.

### HTTP endpoints

```python
ctx.add_route("GET", "tasks", list_tasks)          # -> /api/plugin/<plugin-name>/tasks
ctx.add_route("GET", "tasks/:sid", get_task)       # path parameters matched by position
ctx.add_route("PUT", "checked", put_checked)
ctx.add_route("DELETE", "tasks/:sid", drop_task)
```

`handler(args)` returns `(status, payload)`; a dict or list payload is returned as JSON (a list is wrapped as `{"ok": true, "items": [...]}`). `args` contains the **query string, path parameters, and request body** (under the `body` key when a body is present).

Supported methods are `GET` / `POST` / `PUT` / `DELETE`. Paths live under `/api/plugin/<plugin-name>/` and **do not support wildcards** apart from `:name` parameter segments: the path must match the declared shape segment by segment, with the same number of segments. "Which endpoints a plugin exposes" is therefore always enumerable and auditable.

### UI

```python
ctx.add_panel("notes", title="便签", html="<div id='notes'></div>",
              script_file="ui/panel.js", css_file="ui/panel.css", pinned=False)
ctx.add_action("notes", label="🗒 便签", title="便签")   # a button below the composer; opens the same-named panel
```

A panel joins the tab container in the right column, next to the Steps pane. Its title is the tab label, and the panel body has no heading row of its own. A panel with `pinned=True` shows no close button.

Division of responsibility:

| Who | Responsibility |
|---|---|
| Plugin | Panel HTML fragment, script, and styles; how content is rendered |
| Shell | Tab container, enumeration from data, delivering assets by path, same-origin injection |

## Subagent tool visibility

A plugin declares its tool list with `ctx.set_subagent_tools([...])`:

```text
not called: all tools from this plugin are visible to subagents
empty list: no tool from this plugin is visible to subagents
tool-name list: only the listed tools are visible to subagents
```

The kernel filters only the subagent model tool view by this list; it does not copy the registry and does not branch on plugin names. The parent conversation view is unaffected. The tool remains registered; declaring a new list changes visibility again.

A plugin can also use `ctx.is_subagent(cid)` to learn the current conversation role and decide whether to inject request-tail text. `ai_speak` declares an empty tool list and registers its voice prompt tail with `subagent_visible=False`, so the tail is not rendered into subagent requests.

## Request tail

`ctx.add_mode_tail(fn, *, subagent_visible=True)` registers `fn(conversation_id) -> str`. The text is appended after the execution mode and Todo progress; it enters only the current request tail, not the system-prompt prefix. Loading or unloading a plugin changes only the tail and leaves the system-prompt prefix unchanged. An empty string takes no space, and a failing source is isolated.

## UI assets

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

### Script loading

**Context-segment appearance** is registered with `add_ctx_segment_style`; at startup the shell fetches `/api/ctx-segment-styles` and calls `ctxSegments.register`, so a segment color does not need an empty panel script.

**Panel scripts** are preloaded in sequence at startup (`preloadPluginScripts()`), while **styles are injected when the panel first opens**. Styles are needed only while the panel is open; injecting them earlier would load bytes that most pages never use.

**Boot scripts** are registered with `add_boot_script(rel_path)` (a tool-card view, for example); at startup the shell fetches `/api/boot-scripts` and preloads them after the panel scripts, so JS can be injected without a panel.

Preloading is **serial**: a script reads the global `window.aiAgentPluginCurrent` to know which plugin it belongs to, and parallel loading would overwrite that value.

Because panel scripts are preloaded before the panel DOM exists, the shell dispatches `ai-agent:panel-opened` each time a panel opens; a panel script renders on that event.

<a id="壳层公共桥" name="壳层公共桥"></a>

### Shell bridge

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

Plugin changes are applied without a page refresh: the shell reloads panels, actions, segment styles, and boot scripts, closes panels of unloaded plugins, and clears the script and style caches so that re-enabling a plugin runs its scripts again.

### Conversation switch notification

When panel content carries per-conversation state (selections, for example), it must refetch on every conversation switch. The shell broadcasts a generic event and **whoever needs it subscribes**:

```js
document.addEventListener("ai-agent:conversation-changed", function () {
  if (document.getElementById("kbBody")) render();
});
```

The shell names no plugin and does not require plugins to know about the shell.

## Resources owned by a plugin

| Resource | How to obtain it | Notes |
|---|---|---|
| Dedicated data directory | `ctx.data_dir` | `<data-root>/plugin/<plugin-name>/`; created on first access |
| Kernel App | `ctx.app` | Kernel services already registered, e.g. `ctx.app.registry` / `ctx.app.mesh`; `None` before assembly completes |
| Own runtime | `ctx.set_runtime(obj)` | Registered so the shell can retrieve the same instance by name |
| Manifest rank | Written by the host | Used for assembly order; the plugin neither sees nor manages it |

`ctx.data_dir` means a plugin **sees only its own layer** and does not need to know where the outer directory is. Plugin directories are isolated from each other, so identically named files cannot collide. State belongs here rather than in the plugin directory: the plugin directory is code, the data root is data.

`ctx.app` is for **handler code**, not `register`: plugins load at the end of assembly, when the App has not yet been handed to the host, and handlers run only when a request arrives. `ctx.set_runtime` is called during `register`.

## Lifecycle

```
discover     scan the plugin root for <name>/plugin.py — enumerate plugins on disk
load         load each manifest entry: importlib with a dynamic module name → register(ctx)
             called at the end of assembly, when kernel services are registered and handlers can obtain ctx.app
unload       call disposers in reverse; then clear contributions by plugin name, drop the runtime, and remove module cache entries
```

Discovery skips directories whose names start with `_` or `.`.

`importlib` loads each plugin under a dynamic module name, so the shell cannot import the same module object. A plugin that wants the shell to operate on its runtime must register it with `ctx.set_runtime(obj)`; `plugin_host.runtime("<plugin-name>")` returns that same instance. Without registration, the two sides hold separate copies of the state.

The unload fallback removes panels, actions, routes, segment styles, and boot scripts by plugin name. Event subscriptions are removed by the disposers registered through `ctx.subscribe`.

## Model catalog source

`add_model_catalog(entries)` gives a set of model entries to the kernel's `ModelCatalog`. Entries are `ModelEntry` objects with `id` / `provider` / `label` / `options` / `is_default`; provider-specific keys such as `base_url`, `api_key`, and `model` live in `options`. The kernel resolves the request's id to the matching provider instance; an unknown id is an error and is not silently routed to another model.

The catalog is the single authoritative source for model routing while its plugin is loaded; with no valid entries the model list is empty. Entry construction is the plugin's responsibility; the kernel normalizes, validates, and consumes snapshots. Only one source may be registered: a second source is refused and logged, and the plugin still loads.

`multi_model` implements this extension point; its configuration and behavior are documented in [multi-model.md](multi-model.md).

## Built-in plugins

| Plugin | Registers | Form |
|---|---|---|
| `plugins/skills` | `skills` tool + two context sources + system-prompt section + segment style + boot tool-card script | no panel; context segments + boot script; see [skills.md](skills.md) |
| `plugins/rules` | one context source (one message per `.md` file) + system-prompt section + segment style | no panel, no configuration, no endpoints; see [rules.md](rules.md) |
| `plugins/knowledge` | context source + panel + composer action + segment style + three endpoints | injection, panel, action, and endpoints all present; state in `ctx.data_dir`; see [knowledge.md](knowledge.md) |
| `plugins/multi_model` | model catalog + read-only `/catalog` + boot dropdown script | each entry carries its gateway and provider; see [multi-model.md](multi-model.md) |
| `plugins/visual_operator` | four tools (screenshot / mouse / keyboard / wait) + platform backends + input lock | backend assembled by platform; when unavailable it reports at execution rather than disappearing; see [visual-operator.md](visual-operator.md) |
| `plugins/ai_speak` | `ai_speak` tool + two read-only endpoints + playback-ack endpoint + two boot scripts + two event subscriptions + voice tail | backend synthesis, frontend player bar; see [ai-speak.md](ai-speak.md) |

Each plugin's configuration and behavior are documented in its own subsystem page; this table only lists the extension points it uses.

## Boundaries

<a id="插件信任模型" name="插件信任模型"></a>

### Plugin trust model

**A plugin is as trusted as local code.** Once loaded, `plugin.py` runs in the same process and interpreter: it can read the whole disk, make network requests, and register tools and HTTP endpoints; panel HTML fragments and scripts are injected into the page's same-origin context. **There is no sandbox.**

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
- render-related data (segment name and color, tool label and icon) is declared by plugins and served by the shell; layout belongs to the shell. The server provides data (segment key / name / count); plugin UI scripts render their own panels and injected content.

## Adding a plugin

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

4. **Register UI** (optional): panels, composer actions, boot scripts, and segment colors via `add_panel` / `add_action` / `add_boot_script` / `add_ctx_segment_style`. Assets live in the plugin directory and are served at `/api/plugin/<name>/_asset/<relative-path>`.

5. **Add it to the manifest**: write a `[plugin:<name>]` section in `plugins.ini`, optionally with `path` / `enabled`. A section makes it a candidate; `enabled` decides whether it loads.

6. **Validate**: `python scripts/ci.py` runs dependency-direction, architecture, comment-style, and unit-test gates; plugin endpoints and UI are covered by acceptance scripts such as `scripts/acceptance_web.py`.

## Further reading

- [Context management](context.md): how injection sources enter context and how assembly order is determined
- [Knowledge base](knowledge.md): file collection, selection, and injection in `knowledge`
- [Multi-model](multi-model.md): catalog entries and the settings form in `multi_model`
- [Skills](skills.md): three-layer disclosure and the `skills` tool
- [Visual Operator](visual-operator.md): screenshots, coordinate contract, and platform backends
- [Tools](tools.md): tool registration, execution pipeline, and disk-write protocol
- [Shell](shell.md): HTTP routing and UI bundling
- [Configuration](../guide/config.md): full configuration reference
