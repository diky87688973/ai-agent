**English** | [中文](architecture.zh.md)

# Architecture

The code is organized into five layers. Each request flows through entry, shell, capabilities, mechanisms, and core.

For module structure, single responsibility, and asset ownership rules, see [Engineering standards](engineering-standards.md).

## Five-layer structure

Dependencies may only point from outer to inner layers. Reverse imports and cycles are checked from the AST by `scripts/check_imports.py`; any violation fails.

```
entry  →  shell  →  capabilities  →  mechanisms  →  core
```

| Layer | Directory | Responsibility | Depends on |
|---|---|---|---|
| L0 Core | `agent/core/` | Module chain, host loop, event and data contracts, ports | None |
| L1 Mechanisms | `agent/mechanisms/` | Model calls, context pipeline and compaction, write gates, session storage, collaboration mesh | core |
| L2 Capabilities | `agent/capabilities/` | Tool registry, built-in tools, plugin loading | core, mechanisms |
| L3 Shell | `agent/shell/` | HTTP + SSE service, UI bundling, system prompts, classic UI adapter | All lower layers |
| L4 Entry | `agent/entry/` | Process entry: read config → build `App` → hand to shell | All lower layers |

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
| `plugins/<name>/` | Plugin-owned tools, configuration, UI, themes, and icons |

`agent/app.py` is the **composition root** and belongs to no layer. It is the only file that references all five layers; it builds `AppContext` and registers services.
The lower four layers must not import the composition root or entry at runtime (pure type-checking imports under `if TYPE_CHECKING:` are exempt); entry may import the composition root.
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

The request contract is `LogicalRequest`: model-independent `messages` / `tools` / `system` / `effort` / `model` / `conversation_id`. A provider translates it into a gateway's wire format.

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

## Composition

`build_app()` in `app.py` performs four steps in order:

1. Read configuration (`agent/config.py`) to decide provider, data root, Skills source, and plugin manifest.
2. Build the tool registry and gates, assemble the tool pipeline, event bus, and plugin host; plugins in the manifest load here.
3. Assemble context-pipeline and compressor factories.
4. Build `AppContext`, register every process-level service in reverse order (which is the cleanup order), and return `App`, whose attributes are shortcuts to `context.get(name)`.

`build_shell_app()` in `agent/entry/web.py` wraps this: it builds the real provider and session store from configuration, then passes them to `build_app()`.
The composition root (`app.py`) and entry layer (`entry/`) are the top two layers: the lower four layers must not import them at runtime, and no layer may import `entry/`. Entry imports the composition root. `python -m agent.entry.web` / `agent.entry.cli` / `agent.entry.headless` are the three process entries.

## Architecture hard constraints

The following constraints are checked with zero exceptions by `scripts/check_architecture_hygiene.py` and unit tests:

- `ToolCallScope` fills `app` and `session` during execution; tools read `current_context().session.gate` and do not open a global gate bypass (no `gate=` / `_fallback_gate` / `gate_resolver`).
- `gate_for` raises without `session_contexts`; `build_pipeline_gate` requires `registry` and `sessions`; previewing only honors a tool's `needs_preview` (no `preview_tools=`).
- The system prompt's write-tool list is generated dynamically by `preview_write_tools_line(registry)` from `needs_preview`, not a handwritten enumeration. Generation failure must raise; silent empty strings are forbidden.
- Write-path keys only come from a tool's declared `write_path_keys` (looked up through the registry). There is no process-global key table and no default guessing of `path`; whether a post-write re-read is required comes from `needs_reread`.
- Write gates only use `agent.mechanisms.quality`; the compatibility module `quality_gate` and `mechanisms.quality_gate` re-entry are forbidden.
- `agent/core` and `agent/mechanisms` contain no concrete plugin names (including `skill_manage` and `plugins/` directory names).
- Plugin contributions such as `add_panel` / `add_route` / `add_action` are tracked by disposers and cleaned up in reverse order on unload.
- External `path=` plugins resolve their asset root through `plugin_root`; `plugins/<name>` is not hardcoded.
- Segment-color-only registrations use `add_ctx_segment_style` and do not attach an empty panel.
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
