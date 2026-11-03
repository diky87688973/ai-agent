**English** | [中文](architecture.zh.md)

# Architecture

The application is assembled from a plugin tree. Tools, models, UI, settings, and business integrations register as plugin contributions, and can be replaced, enabled, or composed per node without changing the kernel or shell.

For module structure, single responsibility, and asset ownership rules, see [Engineering standards](engineering-standards.md).

## Plugins and composition

### Startup assembly

The app starts its own base assembly tree first, then scans extra plugins; plugin assembly declarations are merged before recursive assembly.

```text
Startup flow (whole app)
App starts
  |
  |-- read agent/boot/slot_tree.json
  |     `-- base tree: kernel / host / tools / shell / facade
  |
  |-- scan plugins/ (plugin tree: enabled plugins + declarations)
  |     |-- plugins.ini           enable + order
  |     `-- plugin-assembly.json  extra plugin assembly declarations
  |
  |-- merge
  |     |-- replace / add app/... subtree
  |     `-- auth subtree: frozen
  |
  `-- SlotTree recursive assembly
        |
        v
     App facade ready (no component list)

App runtime
  plugin.py -- register(ctx) --> backend slots / UI slots / settings / routes
                                `-- dynamic nodes attach to the same SlotTree
```

### Slot-tree boot model

The **slot tree itself is the boot assembly graph**. `app.py` is an application facade, not the assembler.

```text
app
→ host
   → services
      → background_tasks
      → <new service id>
→ kernel
   → modules
      → context
      → <new module id>
→ backend
   → tools / context / prompt / models / runtime / ...
→ settings
→ shell
```

Rules:

1. `app` is the only root. Every node path must fall under `app/*`; `backend/*` must also become `app/backend/*`.
2. Container nodes assemble children only; leaf nodes provide a factory or instance.
3. A node contract contains at least:

   ```text
   path
   kind
   factory / provider
   dependencies
   lifecycle
   enabled
   scope
   children policy
   ```

4. The bootstrapper validates the dependency graph first, then assembles in topological order. Missing dependencies, cycles, duplicate nodes, and factory failures fail explicitly.
5. `app` depends only on the slot tree, node contracts, and the generic assembler. It does not import concrete modules or branch on module ids.
6. A new module is a new node plus a factory; `app` main flow does not change.
7. Disable, replace, and unload are handled by node bindings and lifecycle. Failed boot rolls back without half-assembled instances.
8. Modules depend only on public contracts. Containers and `app` do not know module internals. Each module remains independently testable.

Acceptance:

```text
app.py contains no concrete module imports
adding app/host/services/<id> does not change app.py
adding app/kernel/modules/<id> does not change app.py
removing a node fails explicitly when dependencies are missing
all paths have a single app root
failed boot rolls back atomically
each module can be tested alone
```

Current status:

- `SlotTree` / `SlotRuntime` / `SlotComponent` / `SlotContainer` live in `agent/core/`.
- The boot manifest is [slot_tree.json](../agent/boot/slot_tree.json); it currently contains 67 nodes under `app/boot`, `app/host`, `app/kernel`, and the frozen `app/auth` boundary, plus 23 backend slot declarations.
- `App` is no longer the composition root; [bootstrap.py](../agent/boot/bootstrap.py) loads the manifest, creates roots, and assembles recursively.
- Node contracts include `path`, `factory`, `requires`, `master`, `enabled`, and `metadata`; containers assemble direct children only.
- Host services, built-in tools, shell components, and kernel module descriptors are assembled from boot nodes.
- UI, settings, route, and backend contribution paths are data in `plugins/<name>/plugin-ui.json`; backend containers are declared in `backend_slots` in `agent/boot/slot_tree.json`; `PluginContext` registers them as dynamic nodes of the same `SlotTree`.
- `SlotRegistry` remains the runtime binding and snapshot mechanism for plugin extension points; boot components and plugin contributions are both held by `SlotTree`.
- `app.py` is an application facade for session, binding, and command entry.

The boot path is now tree-driven. Plugin-owned contributions remain runtime extension points.

### Plugin settings contract

Plugins declare settings panels and items; they do not render host settings DOM.

```text
plugin: add_settings_panel(panel_id, title)
plugin: add_settings_item(parent, item_id, kind, label, options, save, load)
host:   renders typed controls and submits plugin values through the generic settings entry
plugin: save callback persists and applies its own value, then returns success/failure
```

Settings IDs are `settings`, `settings/<panel>`, and `settings/<panel>/<item>`. The registered `kind` determines the control: `text`, `search`, `number`, `select`, `checkbox`, `textarea`, `password`. Save callbacks belong to the registering plugin; the plugin system only routes, aggregates, and broadcasts. Unloading a plugin removes its panels and items immediately; the plugin retains its own persisted values for the next enable.

### Composition

`boot_app()` performs startup in order:

1. Read configuration (`agent/config.py`) to decide provider, data root, Skills source, and plugin manifest.
2. Load `agent/boot/slot_tree.json`; `SlotTree` materializes roots and assembles recursively.
3. The `facade` node builds `AppContext` and `App`; the `plugins` node loads plugins and attaches contributions as dynamic nodes of the same tree.
4. Return `App`, whose attributes are shortcuts to `context.get(name)`.

`build_shell_app()` in `agent/entry/web.py` wraps this: it builds the real provider and session store from configuration, then passes them to `build_app()`.
The composition root (`boot/`) and entry layer (`entry/`) are the top two layers: the lower four layers must not import them at runtime, and no layer may import `entry/`. Entry imports the composition root. `python -m agent.entry.web` / `agent.entry.cli` / `agent.entry.headless` are the three process entries.

The five layers below are the base the plugin tree runs on; they are not the plugin list.

## Five-layer structure

Dependencies may only point from outer to inner layers. Reverse imports and cycles are checked from the AST by `scripts/check_imports.py`; any violation fails.

```
entry  →  shell  →  capabilities  →  mechanisms  →  core
```

| Layer | Directory | Responsibility | Depends on |
|---|---|---|---|
| L0 Core | `agent/core/` | Module chain, host loop, event and data contracts, ports | common |
| L1 Mechanisms | `agent/mechanisms/` | Model calls, context pipeline and compaction, write gates, session storage, collaboration mesh | core, common |
| L2 Capabilities | `agent/capabilities/` | Tool registry, built-in tools, plugin loading | core, mechanisms, common |
| L3 Shell | `agent/shell/` | HTTP + SSE service, UI bundling, system prompts, classic UI adapter | All lower layers, common |
| L4 Entry | `agent/entry/` | Process entry: read config → build `App` → hand to shell | All lower layers, common |

`agent/common/` is shared status vocabulary imported by all layers. It has no dependencies and is not a layer.

### Packages within layers

| Package | Responsibility |
|---|---|
| `agent/mechanisms/providers/` | Provider protocol, SSE, compatible/native/Echo/Missing implementations; wiring only in `provider_registry.py` |
| `agent/mechanisms/context/` | Turns, tokens, layout, sources, narrow compaction interfaces, three-part assembly |
| `agent/mechanisms/compaction/` | Compaction triggers, covered prefixes, summary integration |
| `agent/capabilities/tasks/` | Task tools and confirmation protocol; one file per tool |
| `agent/shell/session/` | Turn execution, queues, goals, prompts, recovery, heartbeat |
| `agent/shell/classic_adapter/` | Inbound/outbound facade, history, layout, state, sessions, classic contracts |
| `agent/shell/web/` | Routes, static assets, classic page/SSE, plugin endpoints, WebShell actions |
| `agent/subagent/` | Parent/child session repository, batches, lifecycle, message delivery; injected by the composition root, not implemented by shell |
| `agent/common/` | Shared status vocabulary for subsystems; no behavior and no imports from layers |
| `plugins/<name>/` | Plugin-owned tools, configuration, UI, themes, and icons |

`agent/boot/` is the **composition root** and belongs to no layer. `boot_app` reads `slot_tree.json`, assembles recursively, and produces the application facade.
The lower four layers must not import the composition root, the application facade, or entry at runtime (pure type-checking imports under `if TYPE_CHECKING:` are exempt); entry may import the composition root.
The same gate enforces this rule and layer direction. `--scc` prints package-level strongly connected components for auditing.

## Two tracks: decision chain and event bus

The system runs two independent tracks.

| Track | Mechanism | Responsibility | Participates in control flow |
|---|---|---|---|
| Decision chain | Module chain + ordered interceptors with return values | Data movement, gating, interception, rewriting | Yes |
| Event bus | Broadcast subscriptions | UI updates, logs, metrics, progress | No; notifications only |

`EventBus` lives in `core/event_bus.py`. Gates live on the decision chain: subscribers cannot block the main flow, and execution order is not guaranteed.

## Module chain

The kernel's behavioral surface is one method:

```python
class ModuleBase:
    def execute(self, ports: Ports) -> Outcome: ...
```

The host runs the whole chain repeatedly until no module requests continuation. Five modules run in a fixed order:

```
input → queued input insertion → compaction → model → tools
```

| Module | Role |
|---|---|
| `InputModule` | Claims new user input for this turn as facts; **emits only `input_ended(claimed=False)` when there is no input** |
| `QueuedInputModule` | Adds messages marked for insertion from the pending queue to context; runs before compaction so compaction sees them |
| `CompressModule` | Checks the budget before assembly and compacts history above threshold; compaction failure always passes through and never blocks the turn |
| `ModelModule` | Decides from the fact tail whether to run; sends requests, consumes stream deltas, and records `model_message` |
| `ToolModule` | Executes tool calls requested by the model that still have no result; requests continuation after execution |

All implementations live in `agent/core/modules/` and are assembled by `build_default_chain()`:
`input_mod.py`, `queued_input_mod.py`, `compress_mod.py`, `model_mod.py`, `tool_mod.py`, `assemble.py`, `dialogue.py`, `mode_note.py`, `tool_facts.py`, `stderr.py`.

`chain.py` defines how one pass runs (`run_chain_iter` / `run_chain`); `host.py` defines when to stop and the turn boundary.

### Control flow and data flow are separate

- **Control flow uses return values**: `Outcome` carries only control signals (`ok` / `next` / `halt` / `suspend` / `stopped`), never data.
- **Data flow uses events**: text, usage, and progress are emitted through `ports.emit(...)`.

This separation means modules share no mutable state: a module decides what happens next, while data leaves through the event channel.

## Ports

Modules cannot touch files, networks, session storage, or tool implementations directly. They may only call interfaces declared on `Ports`.

```python
class Ports:
    model_port: ModelPort   # start a model request
    tool_port: ToolPort     # execute a tool
    log: SessionLog         # read-only view of the fact log
    def emit(type_, **data) # produce a fact: append to log, then emit event
    def canceled()          # whether the host requested a stop
```

The request contract is `LogicalRequest`: model-independent `messages` / `tools` / `effort` / `model` / `turn_start` / `conversation_id`. A provider translates it into a gateway's wire format.

Available entries on `Ports`: `model_port`, `tool_port`, `log` (read-only fact view), `conversation_id`, `emit`, and `canceled`. Every external capability a module needs goes through these entries.

## Event protocol

Module lifecycle events share the shape `<domain>_started` → result → `<domain>_ended`.

| Module | Start | Result | End |
|---|---|---|---|
| Input | `input_started` | `input_claimed` | `input_ended` |
| Compaction | `compress_started` | `context_compacted` | `compress_ended` |
| Model | `llm_started` | `llm_done` / `llm_failed` | `llm_ended` |
| Tools | `tool_started` | `tool_done` / `tool_failed` / `tool_canceled` / `tool_suspended` | `tool_ended` |

Two rules:

- **`tool_ended` carries no result**. The result is in the earlier `tool_done`; consumers look it up by `call_id`.
- **`_ended` is the completion boundary**. Whether a call has finished is always determined by it.

Event-name constants live in `core/event_name.py` (26 constants); event envelopes live in `core/events.py`.

## Three-level state lifecycle

Mutable state is stored at three levels by lifetime. Mixing them causes hard-to-diagnose bugs such as state leaking across sessions.

| Level | Container | Contents | Lifetime |
|---|---|---|---|
| Process | `AppContext` (`core/context.py`) | Tool registry, execution pipeline, model providers, session store, event bus, plugin host, collaboration mesh, factories | Whole process |
| Session | `SessionContext` / `SessionContexts` (`core/session_context.py`) | Write gates, live state | Lazily created per `conversation_id` |
| Turn | `ToolTurnContext` (`core/context.py`) | Tool-turn state within one turn | One turn |

The session registry `SessionContexts` is the **only entry point** for cross-boundary access: `sessions.resolve()` or `sessions.get(cid)`. Tools and pipeline hooks obtain the current session during execution through `current_session_id()` in `core/session_scope.py`. Session state must not be stored in global singletons or read across sessions.

## Facts and projections

A conversation record is an **append-only fact stream**: every event appends a row, and existing rows are never rewritten.

- Persistence is implemented in `mechanisms/session_store.py` (one JSONL `.raw` per session).
- The SSE stream shown in the UI is a **live projection** of those facts, not another source of truth.
- When the context pipeline needs history, it **derives** it from the fact stream instead of storing another copy.

This yields a structural guarantee: **model-visible ⟺ recorded**. Filtering, cleanup, and formatting must happen before persistence; persisted facts are immutable.

Event format is forward-compatible: **unknown event types are skipped on read**, so old sessions remain readable under new code.

## Architecture hard constraints

The following constraints are checked with zero exceptions by `scripts/check_architecture_hygiene.py` and unit tests:

- `ToolCallScope` fills `app` and `session` during execution; tools read `current_context().session.gate` and do not open a global gate bypass (no `gate=` / `_fallback_gate` / `gate_resolver`).
- `gate_for` raises without `session_contexts`; `build_pipeline_gate` requires `registry` and `sessions`; previewing only honors a tool's `needs_preview` (no `preview_tools=`).
- The system prompt's write-tool list is generated dynamically by `preview_write_tools_line(registry)` from `needs_preview`, not a handwritten enumeration. Generation failure must raise; silent empty strings are forbidden.
- Write-path keys only come from a tool's declared `write_path_keys` (looked up through the registry). There is no process-global key table and no default guessing of `path`; whether a post-write re-read is required comes from `needs_reread`.
- Write gates only use `agent.mechanisms.quality`; the compatibility module `quality_gate` and `mechanisms.quality_gate` re-entry are forbidden.
- `agent/core` and `agent/mechanisms` contain no concrete plugin names (including `skill_manage` and `plugins/` directory names).
- Plugin contributions such as `add_route` and `add_ui_item` are tracked by disposers and cleaned up in reverse order on unload.
- External `path=` plugins resolve their asset root through `plugin_root`; `plugins/<name>` is not hardcoded.
- Context-segment appearance is registered as a `web-ui/left-panel/context_usage/<key>` UI item and consumed by the context bar.
- Classic shell JS and `prompts.py` contain no `skill_manage` (the tool name exists only on the plugin side).
- Plugins declare their own UI and live events; the kernel only provides generic contribution points and event outlets.
- Private cross-layer imports (`from agent.X import _priv`) are forbidden; same-layer private imports are allowed.
- `SERVICE_CLASSIC_ADAPTER` lives only in the shell key table and never enters `core`.
- No stale `changeset_mod_ids` references remain.
- Closing a session releases the corresponding `SessionContext` bucket.

## Further reading

| Topic | Document |
|---|---|
| Glossary | [glossary.md](glossary.md) |
| Kernel modules and events | [subsystems/core.md](subsystems/core.md) |
| Context management | [subsystems/context.md](subsystems/context.md) |
| Model calls | [subsystems/llm.md](subsystems/llm.md) |
| Tools and plugins | [subsystems/tools.md](subsystems/tools.md), [subsystems/plugins.md](subsystems/plugins.md) |
| Knowledge | [subsystems/knowledge.md](subsystems/knowledge.md) |
| Skills | [subsystems/skills.md](subsystems/skills.md) |
| Multi-model | [subsystems/multi-model.md](subsystems/multi-model.md) |
| Session storage and collaboration | [subsystems/session.md](subsystems/session.md) |
| HTTP service and UI | [subsystems/shell.md](subsystems/shell.md) |
| Configuration | [guide/config.md](guide/config.md) |
| Write-gate status and optimization | [write-gate.md](write-gate.md) |
