**English** | [中文](structural-remediation.zh.md)

# Structural remediation

## Goals

The code is organized by responsibility, not by accumulating multiple concerns in one file. The structure keeps these constraints:

```text
one-way dependencies between layers
same-layer modules do not depend on the private symbols of sibling modules
single responsibility
high cohesion
no compatibility re-exports
no temporary bypasses
no overlapping ownership
```

Only structure, dependencies, and test boundaries are in scope; product behavior is unchanged.

## Module layout

```text
agent/mechanisms/
  providers/
    base.py            provider protocol and error type
    sse.py             SSE line parsing and total stream timeout
    debug.py           shared debug switches
    tool_schema.py     tool schema normalization
    openai.py          compatible adapter
    anthropic.py       native Messages adapter
    echo.py            fake model
    missing.py         placeholder when no model is configured
  provider_router.py   per-model routing
  provider_registry.py gateway provider assembly
  context/
    rounds.py          Round, ContextChunk, turn and tool-chain boundaries
    tokens.py          token estimation and reasoning trimming
    layout.py          segment layout and compaction ranges
    sources.py         ContextSources, PluginSegments
    constants.py       segment labels
    contract.py        narrow interface used by the compactor
    pipeline.py        context assembly
  compaction/
    compactor.py       ContextCompactor and summary generation

agent/shell/
  session/
    runner.py          turn runner
    queue.py           queue claim, release, and re-delivery
    goal.py            goal and autonomous continuation
    prompt.py          system prompt and runtime tail
    resume.py          external result recovery
    heartbeat.py       runtime heartbeat
  classic_adapter/
    history.py         history folding
    layout.py          context layout
    state.py           session-level state
    sessions.py        session list and titles
    contract.py        classic event constants
    inbound.py         inbound facade
    outbound.py        outbound facade
    outbound_tools.py  tool event family
    outbound_turns.py  turn and model event family
  web/
    server.py          HTTP service assembly
    web_routes.py      route dispatch
    web_static.py      static assets
    web_classic.py     classic page and SSE
    web_plugin.py      plugin routes
    web_api.py         JSON API and shell runtime state

agent/capabilities/tasks/
  run_type.py
  todo.py
  confirm.py
  goal.py
  common.py

agent/app.py           composition root, outside the layers
agent/entry/          process entry
```

## Dependency rules

### Between layers

```text
entry → shell → capabilities → mechanisms → core
```

Reverse imports are forbidden. `agent/app.py` is the composition root and belongs to no layer; lower layers must not import it at runtime, while `entry` may.

### Within mechanisms

```text
providers/openai.py      → providers/base.py, providers/sse.py,
                            providers/debug.py, providers/tool_schema.py
providers/anthropic.py   → providers/base.py, providers/sse.py,
                            providers/debug.py, providers/tool_schema.py
providers/echo.py        → providers/base.py
providers/missing.py     → providers/base.py

provider_router.py       → providers/base.py
provider_registry.py     → providers/openai.py, providers/anthropic.py,
                            providers/base.py

context/pipeline.py      → context/rounds.py, context/tokens.py,
                            context/layout.py, context/sources.py,
                            context/contract.py, context/constants.py
compaction/compactor.py  → context/contract.py
```

Prohibited:

```text
a concrete provider importing another concrete provider
provider_router.py importing a concrete provider
compactor.py importing context internals (pipeline, layout, rounds, sources, tokens)
```

### Within the shell

```text
session/runner.py → session/queue.py, session/goal.py,
                    session/prompt.py, session/resume.py,
                    session/heartbeat.py
classic_adapter/inbound.py → history.py, layout.py, state.py,
                             sessions.py, contract.py
classic_adapter/outbound.py → outbound_tools.py, outbound_turns.py, contract.py
web/server.py → web_routes.py, web_static.py, web_api.py
web_routes.py → web_static.py, web_classic.py, web_plugin.py, web_api.py
```

`session/runner.py` only orchestrates; it does not implement the queue, goal, prompt, recovery, or heartbeat.

## Module responsibilities

| Area | Modules | Rule |
|---|---|---|
| Provider base | `providers/base.py`, `providers/sse.py`, `providers/debug.py`, `providers/tool_schema.py` | The protocol and error type are separate from the adapters; SSE and timeout are independently testable; debug switches and schema normalization are shared by the gateway adapters |
| Compatible adapter | `providers/openai.py` | Owns only request, response, and error mapping for the compatible protocol |
| Native Messages adapter | `providers/anthropic.py` | Owns only the Messages wire format; depends on neutral provider modules and core contracts |
| Routing and assembly | `provider_router.py`, `provider_registry.py` | Within the provider package, the router depends only on `providers/base.py`; the registry is the only assembly point for gateway providers |
| Context model | `context/rounds.py`, `tokens.py`, `layout.py`, `sources.py`, `constants.py` | One axis of change per file |
| Context assembly | `context/pipeline.py`, `context/contract.py` | The pipeline only assembles; the contract is the narrow interface the compactor sees |
| Compaction | `compaction/compactor.py` | Triggers, covered prefixes, and summary integration; no context internals |
| Session runner | `session/runner.py` | Orchestration only |
| Session support | `session/queue.py`, `goal.py`, `prompt.py`, `resume.py`, `heartbeat.py` | One concern per file |
| Classic adapter | `classic_adapter/inbound.py`, `outbound.py`, and submodules | Facades only compose and reshape; history, layout, state, session list, and event families are separate |
| Web | `web/server.py`, `web_routes.py`, `web_static.py`, `web_classic.py`, `web_plugin.py`, `web_api.py` | Dispatch, transport, classic page, plugin endpoints, and JSON business actions are separate |
| Task tools | `capabilities/tasks/*.py` | One file per tool; shared exceptions and argument validation live in `common.py` |
| Assembly and entry | `agent/app.py`, `agent/entry/` | Assembly and entry only |

## Tests

The tests below lock each responsibility boundary; a structural change must not alter these behaviors.

### Providers

```text
compatible and native adapters are tested for SSE parsing separately
tool-call fragments merge into one call
thinking blocks return their signatures
HTTP errors map to user-facing messages
the stream total timeout is enforced
a failed close is reported
a consumer that closes early releases the response
```

### Context

```text
round boundaries
complete tool chains
per-segment token accounting
summary coverage
compaction ranges
plugin segment merging
stable cache prefix
```

### Shell

```text
run loop
cancellation
queue claim and completion
goal continuation
resume splicing
history replay
context layout
SSE frame order
```

### Structural gates

The structural gates are `scripts/check_imports.py`, `scripts/check_architecture_hygiene.py`, and `scripts/check_complexity.py`.

```text
layer direction and reverse dependency on the composition root
a concrete provider importing another concrete provider
the compactor importing context internals
cross-layer private imports; same-layer private imports within budget
file and function complexity thresholds
```

## Change rules

```text
a structural change alters ownership and imports only
behavior changes are never mixed into a structural change
no compatibility re-export, forwarding module, or second implementation
no temporary switch, dual write, dual entry, or forwarding layer
legitimate same-layer dependencies use an explicit allowlist; rules are never relaxed to pass a change
```

## Acceptance

```text
every file under providers owns one provider or one base concern
the native Messages adapter does not import the compatible adapter
the router does not import a concrete provider
the compactor does not import context internals
the session runner only orchestrates
inbound, outbound, and web routes do not own multiple responsibility domains
no compatibility re-exports
the structural gates pass
documentation and the directory layout agree
the full CI pipeline passes
```

## Responsibility boundaries

```text
providers: model protocol and gateway adaptation
context: context data model, tokens, layout, sources, and assembly
compaction: compaction policy and summary integration
session: turn execution plus queue, goal, prompt, recovery, and heartbeat
classic_adapter: event and history adaptation
web: HTTP and static transport
capabilities/tasks: task tool capabilities
app / entry: assembly and process entry only
```
