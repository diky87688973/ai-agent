**English** | [中文](core.zh.md)

# Kernel

`agent/core/` is the L0 layer and depends on no other layer. It provides four things: data contracts, the module abstraction, the chain executor, and the host loop.

## Data contracts

| File | Contents |
|---|---|
| `event_name.py` | 26 event-name constants. Plain strings, zero dependencies |
| `events.py` | `Event` dataclass + `make_event()`. The shape of a fact: type + payload |
| `outcome.py` | `Outcome`: the single shape of a module execution result |
| `model_call.py` | `StreamDelta`: a model stream frame |
| `tool_call.py` | `ToolCallRequest` / `ToolResult` / `GateDecision` / `ToolPipeline` |
| `ports.py` | `Ports` / `ModelPort` / `ToolPort` / `LogicalRequest` |

Only these objects cross layer boundaries; bare dicts are not passed.

## Control signals

```python
class Outcome:
    status: str    # ok / next / halt / suspend / stopped
    reason: str
```

| Status | Meaning |
|---|---|
| `ok` | This pass is done; no continuation requested |
| `next` | This pass is done; **another pass is required** |
| `halt` | Stop the whole chain immediately |
| `suspend` | End the turn and return control to the host; a later external event starts a new turn |
| `stopped` | Terminated by a cancel signal |

`Outcome` carries **only control signals, never data** (`reason` describes the terminal state, not a payload). Message text, usage, and progress all leave through `ports.emit()`. This separation keeps modules from sharing mutable turn state.

## Module abstraction

```python
class ModuleBase:
    # generator contract: yield facts, return the control signal
    def execute(self, ports: Ports) -> Iterator[Event]: ...
```

The behavioral surface is this one method. At execution time a module receives only `Ports`; it does not receive the turn context object, and modules do not reference each other.

Five concrete modules live in the `agent/core/modules/` package:

| Module | What it does | Principal events |
|---|---|---|
| `InputModule` | Claims the new user input for this turn as facts | `input_started` / `input_claimed` / `input_ended` |
| `QueuedInputModule` | Takes messages marked for insertion from the pending queue into context | `input_claimed` |
| `CompressModule` | Checks the budget before assembly and compacts above the threshold | `compress_started` / `context_compacted` / `compress_ended` |
| `ModelModule` | Sends requests, consumes the stream, aggregates tool calls | `llm_started` / `assistant_delta` / `reasoning_delta` / `llm_done` / `llm_failed` / `llm_ended` / `model_message` / `usage` / `context_segments` |
| `ToolModule` | Executes tools and feeds results back | `tool_started` / `tool_progress` / `tool_done` / `tool_failed` / `tool_canceled` / `tool_suspended` / `tool_ended` |

`build_default_chain()` assembles them in the order input → queued input insertion → compaction → model → tools.

### How each module decides

**`InputModule`**: with input it emits `input_claimed` and returns `ok`; **with no input it emits no `input_claimed`**, only the terminal `input_ended`. This is required because a resume turn triggered by an interface confirmation has no user utterance; emitting an empty `input_claimed` there would make the message sequence `…assistant(tool_calls) → user("") → tool`, which the model API rejects.

**`QueuedInputModule`**: its position is fixed before compaction. Inserted messages become new user turns, and compaction must see them; otherwise compacting against the old budget immediately after an insertion would drop the new messages. It consumes all pending insertion requests in one execution.

**`CompressModule`**: performs the context budget check before assembly and compacts above the threshold. It never requests another pass: compaction is preparation. A missing or failing compactor always passes through: compaction is an enhancement and never blocks a turn.

**`ModelModule`**: it decides whether to run by scanning the fact tail: new user input (`input_claimed`) or a tool result (`tool_ended`) → run; a `model_message` → do not run.

**`ToolModule`**: the closing module of the chain. It finds calls requested by the newest model message that still have no result and executes them; calls already suspended are not executed again. When external input is required it emits `tool_suspended` and `tool_ended`, cancels the rest of the batch, and returns `Outcome.suspend(...)` (control returns to the host; it does not block). Otherwise, if it executed any call, it returns `next`.

## Chain executor

`chain.py` answers "how one pass runs":

```python
run_chain_iter(modules, ports) -> _Pass
run_chain(modules, ports)      -> PassResult
step(module, ports)            -> (list[Event], Outcome)
```

`run_chain_iter` returns a `_Pass`. Iterating it yields events as they are produced; after iteration, `.result` holds the pass result. `PassResult` records the pass's terminal outcome, if any, and whether any module requested another pass. `run_chain` stops immediately on any terminal outcome (`halt`, `suspend`, or `stopped`) and runs no further modules. `step` is the narrow single-module entry used by tests and assembly checks.

## Host loop

`host.py` answers "when to stop" and defines turn boundaries.

```python
class Host:
    def run(...) -> TurnResult
```

A terminal outcome (`halt` / `suspend` / `stopped`) ends the turn. Otherwise, with the default chain, a turn ends when three conditions hold at the end of a pass:

1. no tool result is waiting to be fed back;
2. the pending queue held no insertion when this pass began;
3. no module requests another pass (`Outcome.next`).

Of these, the host checks only condition 3 directly, through `PassResult.wants_another`; conditions 1 and 2 come from module behavior. `ToolModule` returns `next` after executing calls, and `QueuedInputModule` consumes insertions before compaction.

`MAX_PASSES_DEFAULT = 64` is a safety valve: a turn runs at most this many passes, preventing continuation signals from looping forever.

`TurnResult` summarizes one turn: the ending reason (`done` / `halted` / `suspended` / `stopped` / `max_passes` / `abandoned`), the number of passes run, and a terminal explanation. Facts live in `SessionLog`, not on `TurnResult`.

## Engine facade

`Engine` in `engine.py` wraps the module chain in the two faces the shell needs:

- **Start a turn**: deliver input and start the host loop;
- **Event stream**: hand kernel events out as an iterator.

`App.session(conversation_id, *, system_prompt, cancel, ...)` builds a new `Engine` each time; turn state is not shared between sessions.

## Session scope

`session_scope.py` answers how a tool deep in a call knows which session it belongs to.

```python
set_session_scope(cid) / reset_session_scope() / current_session_id()
set_tool_turn_context(ctx) / reset_tool_turn_context() / current_context()
set_progress_reporter(fn) / emit_progress(stream=..., text=..., done=...)
```

Implemented with contextvars. Tools and pipeline hooks take the session id from `current_session_id()` and resolve the session context through `SessionContexts`. This is the execution mechanism for session isolation.

## Image embedding

`image_embed.py` handles how attachment images enter the request body. It belongs to request derivation: the side that folds facts into a request owns this.

- `shrink_image()` / `shrink_path()`: resize locally by the long edge to reduce base64 payload (long-edge limit `EMBED_MAX_SIDE = 800`);
- `build_embed_parts()`: assemble `image_url` content blocks for the request;
- `strip_old_images()`: retain images from the most recent image-bearing user messages and from tool messages. `keep_turns` limits how many recent image-bearing user messages contribute; `max_images` caps the total (defaults 1 turn / 8 images, from `[context]` `image_turns` / `image_max`). Images excluded by the window or above the cap are stripped oldest first by message time, keeping the newest; within one message, the earliest images are stripped first;
- `placeholder_text()`: placeholder text for images skipped by the size budget;
- `_drop_selected_blocks()`: when an image is stripped by the turn window or total cap, the placeholder carries the original `attachment_id`, so the model can re-read it with `read_image(attachment_id=...)`;
- `strip_attachment_meta()`: removes the `attachment_id` used only for placeholder resolution before the request is sent, so internal references do not reach the provider;
- `read_image` rejects a repeated read of the same attachment in one turn with a structured error, breaking the read → strip → read-again loop.

A stripped image disappears only from **the copy sent to the model**: the base64 in the fact stream is untouched, so history replay and re-asking can still obtain the original image.

## Context container

`context.py` contains two classes:

| Class | Role |
|---|---|
| `AppContext` | Process-level service registry: `register(name, svc)` / `get(name)` / a disposer handle. `get` raises `KeyError` for an unregistered name; use `has(name)` to check existence |
| `ToolTurnContext` | Minimal state for a tool turn within one turn |

Service-name constants are at the top of `core/context.py`; assembly points and consumers reference the same constants.

## Further reading

- [architecture.md](../architecture.md): five-layer structure and assembly
- [context.md](context.md): context management
- [tools.md](tools.md): tool execution pipeline
