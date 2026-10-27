**English** | [中文](shell.zh.md)

# Shell

`agent/shell/` is the L3 layer; it wraps the kernel as a runnable service and UI.

| File | Responsibility |
|---|---|
| `web/server.py` | HTTP + SSE service assembly and startup; auth runtime injection |
| `web/web_routes.py` | HTTP verb and path dispatch |
| `web/web_auth.py` | Auth middleware: host, identity and CSRF checks |
| `web/auth/` | Password, login sessions, API tokens, CSRF, rate limiting, audit and route policy |
| `web/web_static.py` | Static assets, path and protocol constants |
| `web/web_classic.py` | Classic page and classic SSE |
| `web/web_plugin.py` | Plugin endpoints and plugin asset forwarding |
| `web/web_api.py` | WebShell entry, SSE connections and run state |
| `web/web_chat.py` / `web/web_sessions.py` / `web/web_files.py` / `web/web_contributions.py` / `web/web_subagents.py` / `web/web_state.py` | WebShell actions for chat, sessions, files, contributions, subagents and UI state |
| `sse.py` | SSE transport |
| `session/runner.py` | Turn scheduling, cancellation, queue draining and lifecycle |
| `session/queue.py` | Queue claim, release and pending-fact flush |
| `session/goal.py` | Goal and autonomous-continuation decisions |
| `session/prompt.py` | System prompt and runtime tail |
| `session/resume.py` | External tool-result recovery |
| `session/heartbeat.py` | Run-state heartbeat |
| `prompts.py` | System prompt |
| `environment_info.py` | `## 环境信息` section of the system prompt |
| `web/ui_bundle.py` | Inline UI asset bundling |
| `web/web_ui_config.py` | UI display switches from `web-ui-config.ini` |
| `settings_panel.py` / `settings_io.py` / `plugin_settings.py` / `plugin_editor.py` | Settings host configuration, INI primitives, plugin configuration and editor views |
| `cli/interactive.py` | Interactive dialogue shell (command line) |
| `cli/headless.py` | Run one turn without a UI and print the event stream |
| `fspaths.py` | Visible-root sources, path boundary checks and display forms |
| `classic_adapter/` | Event translation, inbound requests, history replay, confirmation loop |
| `web/web_assets/` | Shell page, styles and front-end scripts |

Token issue and revoke take an in-process thread lock plus a cross-process `tokens.json.lock` file lock. A duplicate name is rejected, and an unavailable lock produces a readable error instead of a stack trace.

## Usage and hit-rate conventions

**The hit rate is computed only from provider-returned values.** After each model call the API reports `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` in `usage`. The kernel records them verbatim as a `usage` fact, and the adapter forwards them unchanged (field names: `SSE_USAGE_FIELDS` in `classic_adapter/contract.py`). The UI shows hit / (hit + miss) from those two official values; no estimate is mixed in.

**The context-occupancy denominator is the model window**, read from the model entry's `context_window`; the adapter adds `model_max_context_tokens` to the `context_layout` payload it emits. It is not the compaction threshold: the threshold is the budget at which compaction is triggered, while the window is the physical limit. The window follows the session's current model; after a model switch, the next turn uses the new denominator. When the catalog has no window for the model, the UI falls back to the budget.

**Tokens in the segment overlay are estimates**: they sum the assembled messages, with CJK at one token per character, other text at four characters per token, and images at a fixed per-image allowance. They differ from the official `prompt_tokens` in the usage bar: one approximates a segment, the other is what the call actually consumed.

## Startup

```bash
python -m agent.entry.web --host 127.0.0.1 --port 8765
```

`main()` in `agent/entry/web.py` parses arguments, handles the auth command-line paths, builds the app and calls `serve()`. `serve()` starts auth, applies TLS, prints the addresses and blocks in `serve_forever()`.

`create_server()` returns `(server, shell)` without starting it. `auth` must be passed explicitly; a missing `AuthRuntime` raises `TypeError`.

`serve()` receives an assembled app and decides where the visible roots, title directory and workspace directory live, then blocks. `build_shell_app()` is the entry-layer assembly function: it creates a `MissingProvider` unless a provider is injected, plus a session store. The shell never imports the assembly root.

Missing model configuration does not block startup: the service starts with `MissingProvider`, the page opens, and the model picker is empty. Saving plugin configuration reloads the plugin and calls `app.refresh_model_config()`, which recomputes the model route and list from the catalog; once the multi-model catalog provides models, it becomes the authoritative source.

## HTTP routes

### GET

| Path | Purpose |
|---|---|
| `/` | Single-page UI |
| `/health` | Health check: tool count, model and allowed list, global default reasoning effort, SSE channel count, paused and pending-confirmation sessions, kernel name |
| `/favicon.ico` | Site icon |
| `/assets/*` | Static assets |
| `/workspace/*` | Workspace files (rewrite target for images and video in the UI) |
| `/api/events/stream` | **SSE event stream** (classic format by default; `format=kernel` passes kernel events through) |
| `/api/chat/history` | Session history |
| `/api/chat/sessions` | Session list (with date groups) |
| `/api/chat/ui-state` | Session state: mode, model and available models, reasoning effort, todo, goal, autonomy, running (with `conversation_id`); without an id, only which sessions are running (does not store client layout) |
| `/api/chat/attachment` | Inline attachment read |
| `/api/fs/list` `/api/fs/read` | Right-pane file viewer |
| `/api/dir-browse` | Directory browsing for `@` completion |
| `/api/panels` `/api/actions` | Plugin-contributed right-pane panels and composer action list |
| `/api/ctx-segment-styles` `/api/boot-scripts` `/api/tool-labels` | Plugin-contributed context-segment styles, boot scripts, and tool display names and icons |
| `/api/plugin/<plugin>/<path>` | Plugin endpoint namespace (matches registered shapes; `:name` segments take positional parameters; `_asset/<relative path>` forwards plugin files) |
| `/api/settings` | Settings-page catalog. A secret field's `value` is always empty; `configured` and `placeholder` are supplied instead |
| `/api/settings/plugins` | Plugin cards: name, description, icon, version, enabled, configurable |
| `/api/settings/plugin-file` | Editor view of a plugin's `plugin-config.ini`; secret fields in structured forms report only whether they are configured |
| `/api/reasoning-effort` | Session reasoning effort and the global default |
| `/api/chat/queue` | Pending-send queue snapshot for the current session |
| `/api/usage-accumulator` | Accumulated usage |
| `/api/media` | Media proxy; the path must fall within the configured media root, or all visible roots when none is configured |
| `/api/subagents` `/api/subagents/history` | Subagent list and child-session history |
| `/api/background/tasks` | Background-task snapshot or filtered list |
| `/api/update/status` `/api/update/logs` | Update state and log tail |

### POST

| Path | Purpose |
|---|---|
| `/api/chat/send` | Start a dialogue turn; if the session is already running, the message enters the pending queue; `draft_id` re-sends a recalled draft |
| `/api/chat/queue/<id>/insert` | Mark a queued message for insertion at the next safe turn; if the session is idle, start a turn immediately |
| `/api/chat/queue/<id>/recall` | Recall a queued message and return its text, images and source |
| `/api/chat/stop` | Stop the current turn (cooperative cancellation) |
| `/api/chat/user-confirm` | Submit a user confirmation: write-plan confirmation, `user_confirm` answer, and approval (agree/reject) share this endpoint |
| `/api/chat/title` | Generate or read the cached session title |
| `/api/chat/autonomous` | Toggle session autonomy |
| `/api/chat/goal` | Read and write the goal; also pause/resume/done/delete transitions |
| `/api/chat/command-input` | stdin input for an interactive command |
| `/api/subagents/send` | Send input to a UI child session |
| `/api/background/tasks/create` `/cancel` `/output` | Create, cancel and read output from background tasks |
| `/api/update/check` `/download` `/apply` | Check, download and apply an update (apply is refused while background tasks or queued messages exist) |
| `/api/settings` | Write host configuration. An empty secret field is not written; content replaces the value in the file |
| `/api/settings/plugins` | Plugin switch: writes `enabled` in `plugins.ini` and loads or unloads immediately |
| `/api/settings/plugin-file` | Write a plugin's editable sections; the rest of the file is preserved |
| `/api/settings/pick-dir` | Open the system directory picker (Windows) |

### DELETE

| Path | Purpose |
|---|---|
| `/api/chat/sessions` | Close a session and release its in-process runtime (the session log is untouched) |
| `/api/chat/queue/<id>` | Cancel an unsent queued message |
| `/api/plugin/<plugin>/…` | Plugin endpoints |

### PUT

`/api/chat/ui-state`, `/api/reasoning-effort`, `/api/usage-accumulator`, and plugin endpoints (`/api/plugin/<plugin>/…`).

Writes travel in the request body; reads in the query string. Authentication endpoints (`/login`, `/desktop-login`, `/healthz`, `/auth/*`) are handled by the auth layer before these routes.

The settings button sits in the header, at the right. The page reads and writes `config.ini`, `web-ui-config.ini`, and each plugin's `plugin-config.ini`. Secret fields in the host form and in structured plugin forms are overwrite-only: leaving the field empty keeps the file's value; content replaces it. `GET /api/settings` never returns the secret; it reports whether one is configured. A configured secret shows the placeholder `已设置秘钥,可重新设置并替换`; an unconfigured one shows `未配置秘钥`. A plugin edited as raw text shows the section as stored, secret values included.

Save stores and closes the window (it stays open on failure); Apply stores without closing. Plugin identity and the enable switch are not part of the plugin configuration; the editor covers only the plugin's own sections. Plugins with `settings-schema.json` render a structured form (`sections`: editable entries such as the multi-model entries; `fields`: a form for the declared fields); a plugin without a schema shows the `[config]` body without the header; when no `[config]` exists, all sections are editable, with headers shown when there is more than one. Secret fields in structured forms report only whether they are configured; an empty value keeps the stored one.

Model configuration is maintained only by the multi-model plugin; the host settings page has no kernel model section and does not write model credentials. Loading or unloading plugins makes the plugin host refresh the model route and list.

## SSE event stream

`/api/events/stream` is the projection the UI sees. It has two formats: with no `format` or `format=classic`, it serves frames translated by the classic adapter; `format=kernel` passes kernel events through unchanged for probes and other interaction layers. The page uses the classic format.

Classic frames carry `conversation_id`, and the page dispatches by session. Heartbeat and process-wide announcement frames (`heartbeat`, `global_sse_ready`, `plugins_changed`, `settings_changed`, `plugin_config_changed`) are not conversation-scoped; `plugin_event` frames carry the fields supplied by the plugin.

Frames translated from a fact carry its storage coordinate and are sent as `id: <seq>` plus `data: <json>`. On reconnect the browser returns the last coordinate in `Last-Event-ID` (a non-browser client can pass `?last_event_id=`), and the server replays the facts after that coordinate, at most 512 facts per resume. Without a cursor there is no replay: the page renders existing content from `/api/chat/history`, and a page opened mid-turn obtains the authoritative running state from `/api/chat/ui-state`.

Each connection has its own bounded queue; a slow consumer loses the oldest frame instead of blocking the broadcast. The classic adapter subscribes to the event bus only while at least one connection exists, and unsubscribes when the last one closes.

The classic stream keeps its connection table in the adapter; the kernel passthrough keeps it in `WebShell`. A disconnect removes the channel from the corresponding table. The kernel passthrough sends only new events, performs no reconnect replay, and revalidates the connection's identity on each loop; a revoked login session or token ends it.

## Runtime state and concurrency protection

`WebShell` holds an SSE connection table and a per-session active-run map (`conversation_id → run_id`). The authoritative busy state comes from the run registry (see [session.md](session.md#run-registry)), the same source the `session_send` tool uses to decide whether the target is busy. A page opened mid-turn can therefore learn that the session is running and show the stop control. On the classic stream, `GET /api/chat/ui-state` without `conversation_id` returns `state.running`.

**Client layout (which tabs are open, which one is active) lives in the browser's `localStorage`**: layout belongs to one browser, and the server neither provides nor accepts it. With several clients activating different sessions, a single server-side field would be overwritten by the last writer, and an earlier client would be taken to another session after a refresh. The classic `PUT /api/chat/ui-state` accepts the request body and stores nothing.

`/api/chat/send` queues concurrent submissions for the same session under the same registration.

## Turn scheduling

`SessionRunner` in `session/runner.py` runs turns in the background: it takes the turn input, builds an engine and runs the module chain, and publishes events to the event bus that feeds SSE. After a turn it drains the pending queue, starts an insertion turn when a queued message was marked for insertion, and otherwise asks the goal/autonomy rule whether to continue; automatic continuations are capped at 50 rounds. External tool results are spliced back as `tool_done` / `tool_failed` plus `tool_ended` before the turn, deduplicated by `call_id`.

A side heartbeat thread renews the run registration every 60 seconds, so a long tool call is not treated as expired. The registration is released when the turn ends, is cancelled, or the process aborts. `/api/chat/stop` sets the cancel signal; the kernel stops at its checkpoints and the run thread releases the registration.

## System prompt

`build_system_prompt(registry=…)` in `prompts.py` assembles the base prompt in this order: identity, reply language, `## 动手指令`, extra sections (plugin sections and `## 环境信息`), `## 编码准则`, terminology, `## 工具使用纪律`, the mode section, and the tool summary. The preview-write tool list in discipline item 2 is generated by `preview_write_tools_line(registry)` from tools whose `needs_preview` is set.

`resolve_system_prompt()` handles the session-level override and otherwise requires `registry`. It removes the mode section with `split_mode_section()`, which deletes only that section and keeps the plugin sections and tool summary after it.

Plugin sections arrive through `PromptSections` (`## 资源目录` is one); the session runner appends `## 环境信息` with the operating system and this session's ID. The tool summary keeps one line per tool — name and the first line of its description, at most 40 tools — and the full schemas travel in the request's `tools` field.

Execution mode is produced by `resolve_mode_note()` and appended as a transient suffix on the request tail, only in the copy sent to the model. The runner's tail also carries the Todo-List progress line and the plugin request tail; with an explicit system prompt, the mode note and the Todo-List line are omitted. See [context.md](context.md#execution-mode-is-a-transient-suffix-on-the-request-tail).

## UI bundling

`web/ui_bundle.py` inlines UI assets into a single HTML page, so the page needs no separate CSS or JS requests at runtime.

```python
build_inline_css()      # CSS modules in manifest order + dark code-highlight theme + light code-highlight theme scoped to light
build_inline_js()       # pre-scripts (theme / Markdown parser / syntax highlighter / code highlighting / image lightbox) -> main modules -> post scripts (tool views / file icons / edited files / settings)
scope_hljs_css()        # prefixes .hljs selectors with a scope such as html[data-ui-theme="light"]
inline_ui_html()        # assembles the complete page
```

Light-theme code highlighting is isolated at runtime: `scope_hljs_css()` prefixes `.hljs` selectors with `html[data-ui-theme="light"]`, so the two themes coexist on one page without overriding each other. No modified copy of the CSS is stored.

The module lists are the single source of order: JS files share one `<script>` scope, and CSS files cascade in list order. Assets are split by function into multiple `classic/js/**` and `classic/css/**` modules; the manifests inline them in order. `inline_ui_html()` is cached with `@lru_cache`, so changes to UI assets take effect after a service restart.

The model picker is not built-in shell UI: the shell provides only the `#modelPickerSlot` mount point, and the button and menu are rendered by `plugins/multi_model/ui/`. Their styles are injected through `window.aiAgentShell.styles.load()`, and the shell's shared styles do not include them. The two public bridges and unload cleanup are covered in [plugins.md](plugins.md#壳层公共桥).

### Edited files in this turn

`edited-files.js` assembles the list in page memory only: a preview leaves a `confirm_id → diff` entry, `commit_write` leaves a confirmed id, and on turn `done` or `stopped` the intersection is rendered as `.edited-files`; a `done` while paused for user confirmation does not render the list. Nothing enters the kernel, and a refresh does not replay it. A valid new message sent through `POST /api/chat/send` calls `clearLiveEdits` for that session; `POST /api/chat/user-confirm` does not clear it.

## Chat-area minimum width

The chat area and the right pane are separated by a draggable splitter (`classic/js/layout/splitters.js`; the width is stored in `localStorage` under `aiAgent.classicMainSplit`). The drag has a target lower bound of `670px` for the chat area (`MIN_CHAT_PX`) and `300px` for the right pane (`MIN_STEPS_PX`; the stylesheet sets `.side{min-width:300px}`). When the splitter is dragged to its limit, the right pane stops at `300px` and the chat area is not squeezed further.

The bound is the width at which the current composer row still fits: below it, the row (attach / mode / reasoning / model picker / plugin buttons / send hint / goal / send) crosses the pane's right edge. Plugin action buttons widen that row, so `MIN_CHAT_PX` is tied to the current row.

Window narrowing is not constrained by this pair: `.chat` has `min-width:0`, so the chat area can shrink below `670px` and the composer buttons wrap.

## Chat-area Markdown

Prose blocks are rendered by the bundled Markdown parser (`web/web_assets/classic/js/vendor/marked.min.js`): block-level markdown rules such as loose-list spacing, tables, task lists and nested lists are handled there.

`renderMarkdown()` in `classic/js/render/markdown.js` splits the text by code fences first. Fenced blocks go to the existing logic (`diff` / `patch` become diff cards; others get syntax highlighting); only prose blocks go to `renderMarkdownBlocks()`.

`renderMarkdownBlocks()` parses with `gfm:true`, `breaks:false`, `html:false`, then runs the result through `sanitizeRenderedHtml()`. GFM enables tables and task lists; `breaks:false` keeps CommonMark newline behavior; raw HTML stays out of the output.

Image and media links rewrite `src` through `markedImageHref()`: workspace files go to `/workspace/<rel>`, and other local absolute paths go to `/api/media?path=`. A bare local path cannot be used as `src`; the browser does not resolve it.

Streaming rendering is merged to at most one render per animation frame (`scheduleStreamRender()`): the parser re-parses the whole text each time, so rendering every delta would parse the same text dozens of times.

## Adapter layer

`classic_adapter/` translates kernel events into the shapes the classic UI understands, and translates UI requests into kernel calls.

| File | Direction |
|---|---|
| `outbound.py` / `outbound_tools.py` / `outbound_turns.py` | Kernel events → UI events (stream facade; tool and turn frame families) |
| `inbound.py` | UI request → kernel call → response body the UI expects |
| `history.py` | History folding, attachments, tool echo |
| `layout.py` | Context segment layout, plugin-segment overlay, budget scaling |
| `state.py` | Classic session-scoped state (usage, command input, attachments) |
| `sessions.py` | Session title and date grouping |
| `contract.py` | Event and field constants; the adapter's single source of truth |
| `channel.py` | SSE connections, broadcast, heartbeat and reconnect replay |
| `confirm.py` | Pause state and the user-confirmation loop |
| `plugin_events.py` | Plugin event frames |
| `adapter.py` | `ClassicAdapter` facade: per-session translation streams, health snapshot, session teardown |

The adapter is where behavioral differences are settled: the UI and the kernel keep their own shapes, and the adapter flattens the difference in between.

## Command-line shells

```bash
agent-cli --session <cid>                      # interactive, real model + tools + write gate
agent-headless "question"                      # single turn, prints the event stream and session id
agent-headless --session <cid> --timeout 300 "question"
agent-web                                      # web service
agent-gui                                      # native launcher + Python desktop shell
```

`headless` uses the same full system prompt, plugin prompt sections, compaction and session store as the web shell. It loads the `plugins.headless.ini` profile, which disables `ai_speak`. At the end of the run it prints:

```text
[session] <cid>
```

Exit codes: `0` normal, `1` failure/stop/cancel, `2` waiting for user confirmation, `3` timeout.

`build_session()` in `cli/interactive.py` uses `SessionRunner.build_engine()` when a runner is present, sharing the full system prompt, plugin sections and dynamic tail with web and headless; `run_one()` only handles terminal I/O and write confirmation. The CLI loads `plugins.cli.ini`, which disables `ai_speak`.

## Path visibility

`fspaths.py` owns which paths are visible and readable: `--fs-root` sets a visible root (repeatable), and `/api/fs/list` / `/api/fs/read` stay inside those roots. On Windows the default is every existing drive root; on other platforms it is the project root; `AI_AGENT_FS_ROOT` can set it too (separator `os.pathsep`). Paths are resolved before the boundary check, and containment is decided by `relative_to`, not string prefixes. `/api/dir-browse`, which feeds `@` completion, starts from a base directory but can navigate elsewhere; the file-viewer endpoints are bounded, the completion browser is not.

`/workspace/*` is rooted at `<data_root>/workspace`. `/api/media` serves only paths inside the configured media root (all visible roots when unset), not the workspace root. See [guide/config.md](../guide/config.md).

## Diagnostic script

`scripts/inspect_compact.py` prints the context segments and compaction decision for one session. It is read-only:

```bash
python scripts/inspect_compact.py                 # list sessions with logs
python scripts/inspect_compact.py <session id>    # inspect one of them
python scripts/inspect_compact.py <session id> --digest
```

The output includes the fact count, derived message count, user-round count, full estimated tokens against the threshold and the resulting verdict, the rounds kept verbatim, the rounds that will be summarized, the half-open range of that excerpt, and per-chunk token estimates.

`--digest` adds the compactor view: view message count, stored summary count and their text, the assembled estimate, and whether this run would produce a compaction event.

## Further reading

- [architecture.md](../architecture.md): five-layer structure and assembly
- [tools.md](tools.md): write gate
- [guide/config.md](../guide/config.md): parameters and environment variables
