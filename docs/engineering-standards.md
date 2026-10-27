**English** | [中文](engineering-standards.zh.md)

# Engineering standards

These rules are mandatory for module structure, single responsibility, and asset ownership. Where the implementation conflicts with them, the rules take precedence; update the rules and the gates before changing structure.

## 1. Requirement levels

| Level | Meaning |
|---|---|
| MUST | Invariant; a violation blocks merge |
| SHOULD | Default practice; a deviation requires a verifiable reason in review |
| MAY | Optional; stay consistent within a module |

## 2. Module structure

### 2.1 Layering

The dependency direction is fixed:

```text
entry → shell → capabilities → mechanisms → core
```

`agent/app.py` is the composition root and belongs to none of the five layers; it is the only file that may reference all five layers and register process-level services. The lower layers — core, mechanisms, capabilities, and shell — must not import `agent/app.py` or `agent/entry/` at runtime; the entry layer imports the composition root. Pure type-checking imports under `if TYPE_CHECKING:` are exempt.

### 2.2 Module ownership

| Path | Responsibility | Does not own |
|---|---|---|
| `agent/core/` | Module chain, host loop, ports, event contracts, session fact contracts | Providers, plugins, UI, concrete tools |
| `agent/core/modules/` | Single-step modules: input, queued input, compaction, model, tools | Service assembly, HTTP, plugin loading |
| `agent/mechanisms/providers/base.py` | `ModelProvider` protocol and `ModelRequestError` | Concrete gateway requests, UI |
| `agent/mechanisms/providers/sse.py` | SSE frame splitting, stream total timeout, close diagnostics | Provider request bodies, business messages |
| `agent/mechanisms/providers/` | Requests and stream parsing for compatible and native protocols | Echo, routing, assembly |
| `agent/mechanisms/providers/echo.py` | Network-free fake model | Real gateways, routing |
| `agent/mechanisms/providers/missing.py` | Placeholder used when no model is available | Real gateways, routing |
| `agent/mechanisms/providers/debug.py` | Shared debug switches | Request conversion, stream parsing |
| `agent/mechanisms/providers/tool_schema.py` | Tool schema conversion | Provider assembly, routing |
| `agent/mechanisms/provider_registry.py` | The only assembly point for gateway providers | Routing rules, request conversion |
| `agent/mechanisms/provider_router.py` | Selects a provider per model entry | Concrete provider implementations |
| `agent/mechanisms/context/rounds.py` | `Round`, `ContextChunk`, turn and tool-chain boundaries | Layout, summaries, storage |
| `agent/mechanisms/context/tokens.py` | Token estimation and reasoning trimming | Assembly, sources, policy |
| `agent/mechanisms/context/layout.py` | Segment layout, compaction ranges, render statistics | Source registration, compactor state |
| `agent/mechanisms/context/sources.py` | `ContextSources`, plugin segments, source metadata | Pipeline assembly, providers |
| `agent/mechanisms/context/contract.py` | Narrow interface the compactor depends on | Pipeline internal state |
| `agent/mechanisms/context/pipeline.py` | Three-part assembly, segment assembly | Summary generation, HTTP, plugin loading |
| `agent/mechanisms/compaction/compactor.py` | Compaction triggers, covered prefixes, summary integration | Pipeline internals, UI |
| `agent/mechanisms/quality/` | Write gates, checks, pending-confirmation state | Tool implementations, HTTP |
| `agent/mechanisms/session_store.py` | Fact log reads and writes, seq, atomic append/rollback; line codec, encryption, and locking live in sibling modules of the same package | Session display, UI fields |
| `agent/capabilities/registry.py` | Tool registry and tool protocol | Concrete tools, service assembly |
| `agent/capabilities/builtin/` | Built-in tools, one tool domain per file | Task protocol, plugin loading |
| `agent/capabilities/tasks/` | Task tools: run_type, todo_list, user_confirm, goal | Kernel chain, HTTP |
| `agent/capabilities/plugins.py` | Plugin loading and Host; `PluginContext` / contribution ledger live in `plugin_context.py` / `plugin_ledger.py` | Kernel business, concrete plugin names |
| `agent/shell/web/server.py` | HTTP service assembly and startup | Route dispatch, static assets, SSE frames |
| `agent/shell/web/web_routes.py` | HTTP verb and path dispatch, request body and error exits | Concrete business actions, classic page implementation |
| `agent/shell/web/web_static.py` | Shell static assets, paths, protocol constants | Plugin-private assets |
| `agent/shell/web/web_classic.py` | Classic pages and classic SSE | JSON API business |
| `agent/shell/web/web_plugin.py` | Plugin endpoints and plugin asset forwarding | Plugin-internal business |
| `agent/shell/web/web_api.py` | `WebShell` entry and connection/runtime state; business actions split by mixin into `web_chat.py` / `web_sessions.py` / `web_files.py` / `web_contributions.py` / `web_state.py` / `web_subagents.py` | Route dispatch |
| `agent/shell/session/runner.py` | Turn thread, cancellation, queue draining, lifecycle | Queue, goal, prompt, and recovery implementations |
| `agent/shell/session/queue.py` | Queue claim, release, re-delivery | Turn loop |
| `agent/shell/session/goal.py` | Goal and autonomous-continuation decision | Run thread |
| `agent/shell/session/prompt.py` | System prompt and runtime tail | Model calls |
| `agent/shell/session/resume.py` | External tool result recovery | Turn loop |
| `agent/shell/session/heartbeat.py` | Runtime heartbeat | Turn terminal state |
| `agent/shell/classic_adapter/inbound.py` | Inbound facade and API shape | History folding, layout, state |
| `agent/shell/classic_adapter/outbound.py` | Facade translating kernel events into classic events; tool and turn events split into `outbound_tools.py` / `outbound_turns.py` | Business state, HTTP dispatch |
| `agent/shell/classic_adapter/history.py` | History folding, attachments, tool echo | Layout, session list |
| `agent/shell/classic_adapter/layout.py` | Classic context layout, coverage, scaling | History storage |
| `agent/shell/classic_adapter/state.py` | Classic session-level state | Fact log |
| `agent/shell/classic_adapter/sessions.py` | Session titles, date grouping | Session runs |
| `agent/shell/classic_adapter/contract.py` | Classic event and field constants | Business implementation |
| `agent/shell/context_dump.py` | Read-only context snapshot | Model requests |
| `agent/entry/` | Process entry: read config, build App, start shell | Business implementation |
| `plugins/<name>/` | Plugin-owned tools, configuration, UI, theme assets | Kernel layer, shell public assets |

### 2.3 Single responsibility

MUST:

1. A module has exactly one primary axis of change; its name must explain why it exists.
2. A facade only composes and reshapes; business rules, state machines, and compaction policy must not hide inside a facade.
3. Provider implementations must not import one another. Gateway providers are assembled only by `provider_registry.py`; the fake and placeholder providers are referenced directly by the assembly root and entry.
4. `provider_router.py` may depend, within the provider package, only on `providers/base.py`.
5. `ContextCompactor` may use context capabilities only through `context/contract.py`; it must not import the internals of `pipeline.py`, `layout.py`, `rounds.py`, `sources.py`, or `tokens.py`.
6. `SessionRunner` only orchestrates; queues, goals, prompts, recovery, and heartbeat belong to the modules under `session/`.
7. Classic `inbound.py` is an inbound facade only; history, layout, state, and session lists live in `history.py`, `layout.py`, `state.py`, and `sessions.py`.
8. Each built-in task tool has its own file; shared exceptions and argument validation live only in `tasks/common.py`.
9. HTTP routes only dispatch; static assets, classic pages, and plugin endpoints belong to `web_static.py`, `web_classic.py`, and `web_plugin.py`; JSON business actions belong to `web_api.py` and its action mixins.
10. A file over 800 lines, a function over 80 lines, or a file with more than 40 functions fails `scripts/check_complexity.py`; there is no exemption table. `docs/complexity.md` is a generated report and must be regenerated after any change that moves or resizes code.

Prohibited:

```text
provider implementations importing one another
router importing a concrete provider
compactor importing context internals
web_routes executing business logic
inbound directly owning history/layout/state implementations
the same responsibility implemented in both a facade and a submodule
re-exports kept for old import paths
```

### 2.4 Contracts and state

- Control flow uses return values; business data uses events. Modules must not share mutable business state.
- Every piece of mutable state has exactly one authoritative holder: process level in `AppContext`, session level in `LiveState` / `SessionContext`, turn level in `ToolTurnContext`.
- Cross-module access goes only through existing ports, events, registries, or narrow interfaces; private names must not cross layers.
- Appends must be atomic per batch; failures are handled by the same retry queue, and upper layers must not compensate twice.

## 3. Asset ownership

An asset must belong to the module accountable for its lifecycle, failure behavior, and contract. Before adding or moving an asset, answer: why it belongs here, why no other module can own it, whether it can be derived from existing fields, where the single registration point is, whether a duplicate copy exists, and who is affected when it is missing or unloaded.

| Asset | Authoritative owner | Registration/load point | Constraint |
|---|---|---|---|
| Kernel modules and ports | `agent/core/` | `core/modules/__init__.py`, `core/engine_factory.py` | No concrete plugin names or concrete providers |
| Provider protocol and implementations | `agent/mechanisms/providers/` | `provider_registry.py` for gateway providers; the fake and placeholder providers are referenced by the assembly root and entry | Implementations do not import one another; the router depends only on `base` |
| Model selection rules | `provider_router.py` | Assembled in `app.py` | Holds no concrete gateway logic |
| Context model, layout, sources | `agent/mechanisms/context/` | `app.py` builds `ContextPipeline` | One axis of change per module |
| Compaction policy and summary integration | `agent/mechanisms/compaction/` | `app.py` builds the compactor factory | Only through `context/contract.py` |
| Tool protocol and registry | `agent/capabilities/registry.py` | `app.py` builds `ToolRegistry` | A tool registers exactly once |
| Built-in tools | `agent/capabilities/builtin/` | `build_plugins` calls in `app.py` | Tool arguments and schema belong to the tool |
| Task tools and confirmation protocol | `agent/capabilities/tasks/` | `tasks.build_plugins` → `app.py` | Shared exceptions live only in `common.py` |
| Plugin tools/endpoints/panels | `plugins/<name>/` | `PluginHost` + `ContributionRegistry` | Plugin-private assets never enter the shell |
| Plugin switches and configuration | `plugins.ini`, plugin `plugin-config.ini` | `PluginHost`, settings API | Plugin keys belong to the plugin; host keys belong to `config.ini` |
| Host config keys/defaults | `agent/config.py`, `config.ini` | Read by the assembly root | New keys must be registered in `agent/config_schema.py` and documented in the configuration docs |
| Model catalog | `capabilities/model_catalog.py` + multi-model plugin | Refreshed by the plugin at runtime | Model configuration and credentials stay with the plugin |
| Event names and payloads | `agent/core/event_name.py`, `agent/core/events.py` | Module `ports.emit` | Unknown events are skipped; field changes must declare compatibility |
| Classic event/field projection | `classic_adapter/contract.py` | `outbound*.py` / `inbound.py` | The adapter layer only translates shape |
| HTTP authentication | `shell/web/auth/`, `shell/web/web_auth.py` | `server.create_server` injects `AuthRuntime` | Passwords, sessions, tokens, CSRF, and policy belong to the shell; never to core |
| HTTP routes | `shell/web/web_routes.py` | `server.create_server` binds `Handler` | Business actions live in `web_api.py` and its action mixins |
| Classic page/SSE | `shell/web/web_classic.py` | Mixed into `Handler` | Does not copy the JSON API |
| Plugin HTTP endpoints | `shell/web/web_plugin.py` | `PluginContext.add_route` | Exact match; no wildcards |
| Shell public UI/CSS/JS | `shell/web/web_assets/`, `shell/web/ui_bundle.py` | Inline manifest in `ui_bundle` | Public assets belong to the shell |
| Plugin UI/themes/icons | `plugins/<name>/ui/` | Plugin `add_panel` / `add_ctx_segment_style` | Use the resolved plugin root; never hardcode `plugins/<name>` |
| UI configuration | `web-ui-config.ini` | Read by the shell | Not plugin-private configuration |
| Session facts | `data/sessions/*.raw` | `mechanisms/session_store.py` | Append-only; never rewrite in place |
| Runtime data | `data/{queues,mesh,wake,plugin,session_state,recycle,logs,auth,auth2..auth9,subagent,batches,cache}` | The owning mechanisms, shell, and subagent services | Access only through the owning service; never duplicate authoritative state |
| Rule assets | `rules/*.md` | `rules` plugin, injected through `ContextSources` | User and project rules belong to the plugin, not the shell |
| Skill assets | `skills/**` | `skills` plugin, injected through `ContextSources` | Skill bodies belong to the skill library, not the kernel |
| Tool catalog | `catalog/tools.json` | Generated by `scripts/gen_catalog.py`, validated by `check_catalog.py` | Generated; never edit by hand |
| Titles/workspace | `data/titles/`, `data/workspace/` | Owned by the shell and storage respectively | Not in the source tree; paths follow the data root |
| Runtime registration | `mechanisms/live_state.py`, `mesh.py`, `run_registry.py` | Assembly root | Single authority; never cache a second copy |
| Tests | `tests/` | unittest discovery | Never write `data/`; use a temporary data root |
| Generated docs | `docs/complexity.md`, `docs/unit-tests.md` | Generators + `--check` | Gates must regenerate and compare |
| Temporary artifacts | `data/temp/` | The assembly root creates `file_backup`; manual and acceptance artifacts | Not in source or release packages |

### 3.1 Asset ownership rules

- One asset has exactly one authoritative copy; a cache derives from the authoritative source and can be invalidated.
- Configuration keys, event fields, tool arguments, and API fields are defined by the owning module; callers must not assemble them as raw strings.
- A new model tool must ship its argument schema, registration point, and failure tests; adding a handler alone is not enough.
- A new front-end asset must be registered in the `ui_bundle` manifest or a plugin contribution; no orphan file may remain in the repository.
- A new static asset must state its load path, cache policy, and behavior when missing.
- Plugin assets must not be placed in `agent/shell/web/web_assets/`; shell public assets must not be placed in plugin directories.
- Test fixtures, screenshots, context exports, caches, and backups must not enter the source tree or release packages.

## 4. Extension paths

| New capability | Only add/modify |
|---|---|
| Provider | `providers/<name>.py` + assembly in `provider_registry.py`; the router is unchanged |
| Context source | Public registration point in `context/sources.py` + plugin contribution; pipeline branches unchanged |
| Compaction policy | `context/contract.py` + `compaction/`; model and tools unchanged |
| Built-in tool | `capabilities/builtin/<tool>.py` + registration point; kernel unchanged |
| Task tool | `capabilities/tasks/<tool>.py` + `build_plugins`; shell unchanged |
| Plugin | `plugins/<name>/` + `plugins.ini`; no concrete names in the kernel or shell |
| Shell page/API | `web_routes.py` dispatch + `web_api.py` action mixin; no business logic in routes |
| UI assets | Shell public assets through `ui_bundle`; plugin-private assets through plugin contributions |

## 5. Gates

| Constraint | Gate |
|---|---|
| Layer direction; runtime dependency on the composition root | `scripts/check_imports.py` |
| Cross-layer private names, kernel plugin names, gate bypasses | `scripts/check_architecture_hygiene.py` |
| Provider mutual imports | `scripts/check_architecture_hygiene.py` |
| Compactor directly depending on context internals | `scripts/check_architecture_hygiene.py` |
| Silent exception swallowing | `scripts/check_silent_except.py` |
| Complexity thresholds and generated docs | `scripts/check_complexity.py`, `scripts/gen_complexity_md.py --check` |
| Configuration drift | `scripts/check_config_drift.py` |
| Test documentation consistency | `scripts/gen_unit_tests_md.py --check` |
| README facts and `data/` subdirectories | `scripts/check_readme.py` |
| Full acceptance | `python scripts/ci.py` |

New constraints require both a gate and a negative test; rules that cannot be machine-checked go on the review checklist.

## 6. Change rules

1. Establish asset ownership before changing code.
2. A structural move changes ownership and imports only; do not carry behavior changes with it.
3. Before changing a contract field, check producers, consumers, persistence readers, and documentation.
4. When removing an old entry point, remove re-exports, aliases, and compatibility forwarding; do not keep two implementations.
5. A new module requires a responsibility statement, tests, and the necessary complexity and asset documentation.
6. After a change, run the affected tests, static checks, and architecture and complexity gates; run full CI only when explicitly requested.
