**English** | [中文](tools.zh.md)

# Tools

Tools are the actions the model can take on the outside world. Implementations live in `agent/capabilities/`; the execution pipeline and write gate live in `agent/core/tool_call.py` and `agent/mechanisms/quality/`.

## Registration

```python
class ToolPlugin:
    name: str = ""
    description: str = ""
    parameters: Dict[str, Any] = {}          # parameter name → JSON Schema fragment
    label: str = ""                          # short display name
    icon: str = ""                           # one-character icon
    parallel_safe: bool = False
    needs_preview: bool = False              # write preview: plugin tools use the same gate
    write_path_keys: Tuple[str, ...] = ()    # key order for the write target path
    needs_reread: bool = False               # content writes: read again before the next write

    def execute(self, arguments: Dict[str, Any]) -> Any: ...
```

Register with `ToolRegistry`:

```python
registry.register(plugin)   # returns a disposer (unregister handle)
registry.get(name)          # None when not registered
registry.names()            # registered tool names (sorted)
registry.schemas()          # model-visible tool declarations
```

Three constraints:

- **The registry stores; it never executes.** Dispatch and gating live in the pipeline, the only entry point.
- `name` must be unique. Empty names, duplicate names, a non-callable `execute`, and non-dict `parameters` are rejected at registration.
- `execute` returns any serializable value. **The pipeline catches exceptions** and feeds them back as structured failures; one failed call does not end the turn.

Registration returns an idempotent disposer; calling it unregisters the plugin. This is the basis for hot plugging.

## Conditional registration and lifecycle

Some tools depend on runtime services and are not registered in assemblies without them:

| Tool | Registration condition | Lifecycle | Dependency boundary |
|---|---|---|---|
| `subagent` | `build_app(store=...)` injects a persistent store | Parent-session tool; created with `SubagentManager`, closed by `App.dispose()` | `agent/subagent` owns batches and sessions; the shell only calls the service |
| `subagent_send` | Same, child-session tool view only | Child-session tool; follows the parent manager's lifecycle | Sends only to the direct parent session |

The default assembly without a store does not register either tool, so `catalog/tools.json` does not list them. This is conditional registration, not a missing entry.

## Execution pipeline

The turn loop **never calls a tool function directly**; every call goes through `ToolPipeline`. There is no second path.

The pipeline has three segments:

| Segment | When | What it can do |
|---|---|---|
| `pre_tool` | Before execution | Decide (allow / reject) and **rewrite arguments in place** |
| Execution | — | Call `plugin.execute(arguments)` |
| `post_tool` | After execution | **Rewrite the result in place** and observe |

Decisions are `GateDecision`: allow or reject, with a reason. When execution needs external input, the tool raises an exception carrying `await_user`; the pipeline maps it to `ToolResult.await_user` / `deferred`, and the turn suspends.

## Write four-step protocol

The commit-time checks live in the `pre_tool` segment:

```
preview → confirm → commit with confirm_id → reread
```

1. **Preview**: Every tool that declares `needs_preview=True` (built-in writes and plugin writes follow the same rule) returns a preview first. On success, the pipeline registers the write arguments as a snapshot and injects `confirm_id`; nothing is written to disk. If the result carries `needs_commit=false` (`already_applied`, `already_absent`, `skipped`), no snapshot is registered, so confirmation and commit are unnecessary. `copy` / `move` / `rename` with a missing source returns `ok=false` / `source_missing`; a destination conflict with `on_exists=error` returns `ok=false` / `dest_exists_conflict`. Both carry structured `data`, are not registered, and are not treated as applied. The pipeline and the system-prompt write-tool list read this metadata from the registry only; there is no static `preview_tools` bypass. With a `confirm_id`, `review_conclusion(cancel_preview=true)` discards an uncommitted snapshot. Only the latest uncommitted snapshot per write target path is kept; a session holds at most `MAX_PENDING_PREVIEWS` (100), and when full the oldest registration is evicted. Write-target parameter order comes only from the tool's `write_path_keys` (looked up through the registry; `path` is never assumed). `needs_reread` decides whether a write must be followed by `read_file` before the same path changes again.
2. **Confirm**: `QualityGate.confirm(confirm_id)` marks the snapshot reviewed; `review_conclusion` calls it for the model's review.
3. **Commit**: `commit_write` takes only `confirm_id`. The gate **restores the write arguments from the snapshot**; the model does not resend them.
4. **Reread**: When the same file must change again after landing, call `read_file` first to check the current content and line numbers. Re-reading does not invalidate an unlocked `confirm_id`; after confirming, submit with the original ID.

Preview and commit are **two separate tool entries**; they do not share a function.

### Result envelope for the model

Tool messages derived into model context (`SessionLog.derive_messages`) have the same shape for success and failure:

- Success: `{"ok": true, "data": <tool return>}`
- Failure: `{"ok": false, "error": "<type and message>"}` (optional `data`)

Inside the pipeline the result is still `ToolResult(ok/data/error)`; the event stream still emits `tool_done` / `tool_failed`. The envelope applies to the model-facing layer. The classic UI `tool_end.preview` uses the same top-level `ok` / `error` / `data` shape.

### Review and unlock

`review_conclusion` is the model workflow's unlock path: it records a conclusion based on the actual review, with verification evidence, and unlocks the preview. The conclusion must be at least 30 characters and `file_name` is required; when cancelling a preview with a `confirm_id`, the conclusion may be omitted. With `confirm_id` and `cancel_preview=true`, the call discards that preview instead. An unconfirmed preview cannot be committed.

### Other gate rules

| Rule | Content |
|---|---|
| Path resolution | The write target comes from the snapshot via the tool's `write_path_keys`; if no path resolves, the commit is rejected |
| Same-path reread | After a content write, changing the same path again requires `read_file` first |
| Cross-file review | After a real write, committing another file requires a review unless that preview was unlocked before the latest write |
| Red-light scope | While a post-write diagnostic red light is active, only paths in `fixable_paths` (or `pending_review` when that list is empty) may be changed |
| Large-delete detection | A diff deleting at least 30 lines raises a red light when it has no additions or additions below 35% of the deletions |
| Mode gate | Plan mode rejects writes; Execute mode requires a non-empty todo list before a commit |

## Built-in tools

`catalog/tools.json` is the checked-in tool manifest, generated from the assembled registry by `scripts/gen_catalog.py`; `scripts/check_catalog.py` fails on drift.

**Display metadata belongs to the tool**: `label` (short display name) and `icon` (one character) are declared on `ToolPlugin` and reach the page through `registry.display_list()` and the shell's `/api/tool-labels`. Adding a plugin tool needs no UI change; without a declaration the UI falls back to the tool name and a neutral icon.

### File read and write

| Tool | What it does |
|---|---|
| `read_file` | Read a text file; supports a line range and truncation |
| `write_file` | Preview a write (no disk write) and return `confirm_id`; identical content returns `status=already_applied` (no commit needed) |
| `replace_in_file` | Preview a text replacement: literal (single or `edits` batch) or a `line_start` / `line_end` line-range replacement |
| `apply_patch` | Preview applying a unified diff; existing files under the root only, no file creation or deletion |
| `read_write` | Preview a pipeline write: take a slice of a source file and write it to a destination |
| `delete_file` | Preview a delete; an absent path returns `already_absent`; the commit moves the file to the recycle directory |
| `file_ops` | Preview copy / move / rename / delete; `on_exists` = error / overwrite / skip; missing source `source_missing`, destination conflict `dest_exists_conflict`, already-applied / skipped states have explicit `status` |
| `file_undo` | Version rollback: list history / diff / rollback; rollback previews first and commits with `confirm_id` |
| `commit_write` | Commit a write preview with `confirm_id` |
| `review_conclusion` | Submit a review conclusion and unlock a preview |
| `present` | Show file cards; validate paths and return metadata without reading the body |

### File cards

`present` accepts a list of file paths or `{path, title}` objects and returns name, size, kind, and MIME without reading the body. The shell renders the result as file cards in the conversation; clicking a card opens the file viewer in the right pane. Cards are driven only by successful tool results, never inferred from model text.

Markdown links to local text-file paths also open in the right pane; local media paths go to the media preview. Inline code paths in the body (for example `` `E:\test.txt` ``) are treated as local file references.

### Location and search

| Tool | What it does |
|---|---|
| `glob_files` | List paths by glob pattern; `.git/` and `__pycache__/` are pruned by default; the reply reports the skipped directory count in `skipped_derived_dirs` |
| `grep_files` | Fast directory content search: `path` must be a directory; returns path, line number, and match; does not support context lines, gitignore filtering, or encoding sniffing |
| `file_search` | General content search over files or directories: literal or regex search, context lines, gitignore filtering, and encoding sniffing |
| `find_in_file` | Single-file single-point lookup: select an occurrence (0-based) and return `region` plus line and column |
| `regex_locate` | Regex lookup over a file or directory: returns matches up to `limit` with `region`, line number, and content |
| `text_diff` | Generate a unified diff for left and right text (read-only) |

### Command execution

| Tool | What it does |
|---|---|
| `run_command` | Run a command synchronously in the foreground; waits for exit and returns stdout/stderr/exit_code. For short, interactive, install, and build commands |
| `background_task` | Run a command asynchronously in the background; returns `task_id` immediately and manages create / list / output / cancel; argv does not go through a shell |
| `python_inline` | Run Python synchronously in the foreground inside the Agent process; no shell, no child process, cannot be hard-interrupted. There is no timeout parameter; use `background_task` for a timeout |
| `env_probe` | Probe the local command-line environments (cmd / powershell / pwsh / bash / python / py) and return usage advice |

Background children inherit only PATH, system directories, TEMP, HOME, Windows user paths (LOCALAPPDATA, APPDATA, USERPROFILE, and so on), and locale; they do not inherit API keys, tokens, or other credentials. This allowlist only reduces environment leakage and missing paths; it provides no filesystem, network, or privilege isolation and is not a security sandbox.

`run_command` passes a safety layer first: blacklist, content-level interception, `safe_mode`, process lifecycle management, and output sanitization; it inherits the full parent environment.
`background_task` starts the process from argv directly and does not apply `safe_mode`, but it is still subject to the allowed cwd, timeout, and process-termination management; it inherits only the minimal environment allowlist above, not API keys or tokens.
`run_command`, `python_inline`, and the create action of `background_task` are rejected in Plan mode.

### Network

| Tool | What it does |
|---|---|
| `web_fetch` | Fetch a web page and extract plain text; supports timeout, length limits, acceptance checks, and saving the result |
| `web_fetch_render` | Fetch JS-rendered pages with a headless browser (optional dependency) |
| `ip_geolocate` | IP geolocation lookup (free API, no key) |
| `open_meteo_weather` | Weather forecast (free API, no key) with place-name, coordinate, or IP sources; Chinese summary output |

### Data and media

| Tool | What it does |
|---|---|
| `data_table` | Preview, filter, sort, summarize, and export table files (csv/tsv/xlsx) |
| `archive` | Archive list / extract / create |
| `read_image` | Read a local image or a historical `attachment_id` and give the image to the model; repeat reads of the same attachment in one turn are rejected |
| `image_ocr` | OCR for images with optional region cropping; requires an optional OCR engine |
| `git_workspace` | Read-only Git workspace queries: worktree / log / blame / show; no write commands |

### Sessions and tasks

| Tool | What it does |
|---|---|
| `run_type` | Query or switch the session run mode |
| `todo_list` | Session todo list |
| `user_confirm` | Suspend on the first segment and wait for a host answer; `confirm` / `confirm_id` are host-filled fields and are not exposed to the model |
| `goal` | Manage this session's goal text |
| `session_send` | Send a message to a target session and trigger execution |
| `session_multisend` | Send the same message to several targets |
| `session_broadcast` | Broadcast to a group by tag |
| `session_create` | Create free agent sessions |
| `session_list` | List free agent sessions in the collaboration mesh |

### Diagnostics

| Tool | What it does |
|---|---|
| `unified_diagnose` | Run AST syntax diagnostics on Python files under a directory; also runs ruff when it is on PATH |
| `echo` | Echo the input text |

## Plugin tools

Plugins contribute tools to the registry with `ctx.register_tool(tool)`; execution still goes through the same pipeline. A tool that declares `needs_preview=True` is also subject to the four-step write protocol.

`plugins/visual_operator` contributes `desktop_eye` / `desktop_mouse` / `desktop_keyboard` / `desktop_wait`: screenshots are fed back to the model as image attachments, and mouse and keyboard actions are Plan-gated per session. The coordinate contract and platform backends are in [visual-operator.md](visual-operator.md).

`plugins/ai_speak` contributes `ai_speak`: the model speaks the current step in human spoken language; the backend synthesizes speech and sends it to the frontend player bar as plugin events. Text rules and configuration are in [ai-speak.md](ai-speak.md).

`plugins/skills` contributes `skills` (list / read); see [skills.md](skills.md).

Plugin package form, manifest, extension points, and lifecycle are in [plugins.md](plugins.md); runtime instance registration (`ctx.set_runtime` / `plugin_host.runtime`) is described there as well.

## Further reading

- [architecture.md](../architecture.md): `ToolPort` and the module chain
- [plugins.md](plugins.md): plugin system and tool extension points
- [visual-operator.md](visual-operator.md): image attachments and input gating from a plugin tool
- [guide/config.md](../guide/config.md): configuration keys
- [session.md](session.md): the mesh behind cross-session collaboration tools
