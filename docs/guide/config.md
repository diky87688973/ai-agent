**English** | [中文](config.zh.md)

# Configuration

The configuration file is `config.ini` in the repository root. It is checked in and holds only non-sensitive host configuration; when the file is absent, code defaults apply. Models are not configured here; they are maintained in `plugins/multi_model/plugin-config.ini` and on the multi-model settings page. All keys and defaults are listed below.

The plugin manifest is a separate file, `plugins.ini` in the project root. It is checked in, contains no secrets, and lists which plugins to load. See [Plugins](../subsystems/plugins.md).

## `[agent]`

```ini
[agent]
reasoning_effort = max
backup_retention_days = 7
max_passes = 64
plugin_tree_only = 0
```

| Key | Default | Meaning |
|---|---|---|
| `reasoning_effort` | `max` | Global reasoning level. `max` = deep reasoning, `high` = standard reasoning. It can be changed per session; the session-level choice takes precedence and is persisted per session under `data/session_state/`. |
| `backup_retention_days` | `7` | Retention period for versioned backups, in days. Versions older than this are pruned at startup; `0` = keep forever. |
| `max_passes` | `64` | Model round-trip limit per turn; values below 1 are treated as 1. Each round trip may call zero or more tools; this is not a tool-call limit. |
| `plugin_tree_only` | `0` | When `1`, only plugin directories inside the `plugins/` tree may be loaded; absolute or external `path` entries in the manifest are rejected. The `AI_AGENT_PLUGIN_TREE_ONLY` environment variable takes precedence. |

The repository's `config.ini` uses `high` for `reasoning_effort` and `512` for `max_passes`; the defaults in the table come from the code.

`reasoning_effort` is sent as the request body's `reasoning_effort` field by providers that support it; providers that do not support the field ignore it. Invalid values fall back to `max`.

Rules are not configured here. Rule files live in `rules/` at the project root and are injected in full by the `plugins/rules` plugin; see [Rules](../subsystems/rules.md).

`backup_retention_days` is read once at process start; a change takes effect after restarting the service.

## File backups

Before a write tool overwrites a file, it preserves the original content for `file_undo` rollback. Versions are grouped by the path of the file that was changed; each version is a self-describing directory:

```text
<data-root>/temp/file_backup/
├── 40523ae2c2b5f07f/                    ← first 16 hex digits of the MD5 of the absolute path
│   ├── 20261012_193315_269_0000_c00c/   ← version directory: YYYYMMDD_HHMMSS_mmm_sequence_random
│   │   ├── original                     original file bytes
│   │   └── metadata.json                mod_id / path / time / bytes / encoding / original_sha256 / mode / diff_text
│   └── 20261012_195719_270_033b/
└── c9e965b3ee74285f/
```

`mod_id` has the form `<path hash>:<version directory name>`; `file_undo` uses it to locate versions for both `diff` and `undo`.

Version directory names carry a millisecond timestamp, a zero-padded sequence, and a random suffix, so name order matches creation order.

`metadata.json` records how the version was produced: `mode` is the change type (`write` / `literal` / `edits` / `lines` / `patch` / `read_write` / `undo`), and `diff_text` is the unified diff from old to new (truncated at 2000 characters, with a truncation marker appended). If the target file does not exist, no version is recorded because there is no original content to preserve.

- **Versions are grouped by a hash of the target file's absolute path.** File names may contain Chinese characters, spaces, or be very long; sanitized names collide, while path hashes keep every version of one file in a single directory.
- **The version directory name starts with the date**, so pruning can parse the name alone; the file path, time, and checksum are stored in each version's `metadata.json`.
- When every version of a file has expired, its hash directory is removed.

Delete operations (`delete_file` / `file_ops`) do not erase files; they move them to `<data-root>/recycle/<YYYYMMDD>/`, where they can be recovered manually.

At startup, expired versions are pruned according to `[agent] backup_retention_days`. A pruning failure is reported and does not block startup.

## `[context]`

Context compaction. A session keeps recent memory verbatim and compacts earlier rounds into a summary: the last `full_user_rounds` user rounds are not compacted; only the rounds before them are. When no earlier rounds can be compacted, those trailing rounds are compacted as well.

```ini
[context]
summary_token_fallback   = 64000
full_user_rounds         = 5
summary_output_max_chars = 5000
image_turns              = 1
image_max                = 8
reasoning_replay_tokens  = 8000
```

| Key | Default when absent or blank | Meaning | Recommended range |
|---|---|---|---|
| `summary_token_fallback` | `64000` | Fallback compaction threshold used only when the current model does not declare a `context_window`; not exposed on the settings page | Positive integer |
| `full_user_rounds` | `5` | Number of trailing user rounds retained during compaction; earlier rounds are compacted. When no earlier rounds can be compacted, these rounds are compacted too. | `1`–`10` |
| `summary_output_max_chars` | `5000` | Maximum summary length in characters. It is written into the summary prompt as a constraint; the actual length depends on how closely the model follows it. | `2000`–`8000` |
| `image_turns` | `1` | Only images from the most recent N user rounds are kept in the model request; images from earlier user rounds become text placeholders. `0` = no images from user rounds; negative = unlimited. Images returned by tools are not limited by this key. | `0` / positive / negative |
| `image_max` | `8` | Maximum total number of images in the model request. The most recent images are kept first; excess images are dropped oldest first. `0` = no images; negative = unlimited. | `0` / positive / negative |
| `reasoning_replay_tokens` | `8000` | Reasoning replay budget in tokens. `-1` = replay all; `0` = replay none; a positive value keeps the beginning and end and replaces the middle with an omission marker that states the approximate number of omitted tokens (the model can infer the middle from context). Reasoning is intermediate output that never hits the cache, so replaying it in full adds those tokens to every request. | `-1` / `0` / positive |

With a model window, the effective compaction threshold is `floor(context_window × compression_percent / 100)`. `compression_percent` is a model-entry field with default `70` and range `10`–`90`; values outside that range fall back to `70`. Without a model window, `summary_token_fallback` is used.

Images are removed only from the request sent to the model; the bytes in the fact stream are unchanged, so history replay and re-asking still have access to the originals.

"Default when absent or blank" is the value used when `config.ini` lacks the section or key.

For mechanism details, see [context.md](../subsystems/context.md).

## `[update]`

```ini
[update]
check_interval_minutes = 30
```

| Key | Default | Meaning |
|---|---|---|
| `check_interval_minutes` | `30` | Interval between update checks, in minutes. Values are clamped to `1`–`1440`. |

## Plugins

Plugins are loaded from a separate file, `plugins.ini` in the project root. A section makes the plugin a load candidate; the switch is `enabled` in that section (default `1`). Name, description, icon, and version are declared in `plugin-meta.json`. Plugin-specific keys live in the plugin's own `plugin-config.ini`; most plugins use `[config]`, while `multi_model` uses `[model:<id>]` sections.

```ini
[plugin:skills]

[plugin:knowledge]
enabled = 1
```

| Name | Capability | Own configuration file |
|---|---|---|
| `skills` | Skills library (built-in and external) and the `skills` tool | `plugins/skills/plugin-config.ini` |
| `rules` | Injects every `.md` under `rules/` into the context | No configuration (switch only); see [Rules](../subsystems/rules.md) |
| `knowledge` | Local knowledge-base retrieval | `plugins/knowledge/plugin-config.ini` |
| `ai_speak` | Spoken narration and audio playback | `plugins/ai_speak/plugin-config.ini` |

**Section order is context assembly order**: plugins that change less often come first.

**Each plugin's configuration lives with the plugin.** The configurations of `ai_speak`, `visual_operator`, `knowledge`, and `skills` are checked in; `multi_model`'s secret configuration is excluded by `.gitignore`; the kernel's `config.ini` contains no plugin settings. For plugin directory layout, contributed capabilities, and development, see [Plugins](../subsystems/plugins.md).

## HTTP authentication

The web service binds to `127.0.0.1` by default. When bound to a loopback address, `auto` and `local` modes bypass login. In `auto` and `required` modes, binding to a non-loopback address requires credentials; `local` refuses it. Set the password with:

```bash
agent-web --set-password
```

`[auth]`:

```ini
[auth]
; auto / required / local
mode = required
session_hours = 12
max_failures = 5
lock_seconds = 300
trusted_proxies =
allowed_hosts = 127.0.0.1,localhost,::1
cookie_secure = auto
provider_module =
; GUI one-time bootstrap auto-login; browsers always require login
desktop_auto_login = 1
```

```text
auto      loopback binding bypasses login; non-loopback requires login; public binding allowed
required  every address requires login
local     loopback binding bypasses login; non-loopback binding is refused at startup
```

`local` and `auto` behave the same on loopback. The difference is that `local` refuses non-loopback binding, while `auto` allows public binding but requires login.

A non-loopback address without credentials refuses to start.

In `required` mode, browsers always require login. The desktop GUI establishes a session with a one-time bootstrap token generated by the launcher and passed only in the WebView URL fragment; browsers cannot obtain it.

`allowed_hosts` is the Host allowlist and defaults to `127.0.0.1`, `localhost`, and `::1`. Public or reverse-proxy domain names must be added explicitly. `trusted_proxies` accepts IP addresses or CIDR ranges; `X-Forwarded-For` and `X-Forwarded-Proto` are read only when the request comes from a listed proxy.

If the `[auth]` section is absent, `mode` falls back to `auto`; the repository's `config.ini` uses `required`. In `required` mode, a non-GUI service without credentials refuses to start; run `agent-web --set-password` first.

Authentication files are written under `data/auth/`. Windows uses a DACL; Linux and macOS use a `0700` directory and `0600` files. If no authentication directory can be tightened, startup is refused. When permissions have been widened externally, startup resets and tightens them; if tightening still fails (for example, a Windows deny ACE prevents `icacls /reset`), startup falls back to `data/auth2` through `data/auth9`. The old directory is left in place but is no longer read; the new directory does not copy the old password or tokens. In `required` mode with `desktop_auto_login` enabled, a GUI start without credentials generates a new password and continues; a non-GUI start without credentials refuses and requires `agent-web --set-password`.

When a GUI starts in that situation, the generated password is written to `initial-password.txt` in the active authentication directory (`data/auth/` by default). The GUI still opens directly through the bootstrap token; browser logins use the password from that file.

Public binding requires TLS:

```bash
agent-web --host 0.0.0.0 --tls-cert cert.pem --tls-key key.pem
```

Or explicitly allow HTTP without TLS:

```bash
agent-web --host 0.0.0.0 --allow-insecure-public
```

A reverse proxy must use `mode = required`; it cannot rely on the loopback login bypass.

Passwords, sessions, and API tokens:

```bash
agent-web --set-password
agent-web --issue-token ci --scope chat,read
agent-web --revoke-token ci
```

Credentials are written to `data/auth/` and are not included in the release package.

## Launch arguments

| Argument | Default | Description |
|---|---|---|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8765` | Port |
| `--data-root` | `<project root>/data` | Data directory |
| `--fs-root` | Drive roots on this machine; project root on other platforms | Visible file scope. **Repeatable** |
| `--media-root` | Empty; all `--fs-root` | Explicit root readable by `/api/media`; empty uses every visible root |
| `--open` | Off | Open the browser after startup |
| `--set-password` | None | Interactively set the access password, then exit (at least 12 characters) |
| `--issue-token NAME` | None | Create an API token, then exit; refuses an existing name |
| `--revoke-token NAME` | None | Revoke an API token, then exit |
| `--scope` | `read` | API token scopes, comma-separated; accepts `read`, `chat`, `write`, and `admin` |
| `--tls-cert` | Empty | TLS certificate; required for public binding unless `--allow-insecure-public` is set |
| `--tls-key` | Empty | TLS private key; required for public binding unless `--allow-insecure-public` is set |
| `--allow-insecure-public` | Off | Explicitly allow public HTTP without TLS |

`--fs-root` can be repeated: `--fs-root D:\ --fs-root E:\`.

The root of `/workspace/*` is fixed at `<data-root>/workspace` and is not affected by `--media-root`.

## Environment variables

All are optional.

| Variable | Description |
|---|---|
| `AI_AGENT_DATA_ROOT` | Data root directory |
| `AI_AGENT_FS_ROOT` | Visible file roots, separated by the platform path separator (`;` on Windows) |
| `AI_AGENT_MEDIA_ROOT` | Root readable by `/api/media` |
| `AI_AGENT_PLUGIN_TREE_ONLY` | `1` loads only from the `plugins/` tree; overrides `[agent] plugin_tree_only` |
| `AI_AGENT_LOCK_TIMEOUT` | Cross-process lock wait in seconds; default `30` |
| `AI_AGENT_LOG_REQUESTS` | Set to `0` to disable the request summary printed before sending; enabled by default |
| `AI_AGENT_LLM_LOG` | Path for the outgoing model-request log; defaults to `%TEMP%\fan_agent_llm_requests.log` |

## Data directories

Runtime data lives under `data/` and is not tracked by version control. Point it elsewhere with `--data-root` or `AI_AGENT_DATA_ROOT`.

| Directory | Contents |
|---|---|
| `data/sessions/` | Session fact log |
| `data/titles/` | Session titles (plain-text derived cache) |
| `data/session_state/` | Session state (model / mode / reasoning level / checklist; one JSON file per session) |
| `data/temp/` | Temporary artifacts (pre-write backups are described under File backups) |
| `data/mesh/` | Cross-session collaboration (`agents.json` roster plus runtime state) |
| `data/queues/` | Pending message queue per session (user and agent messages, attachments) |
| `data/mesh/runs/` | Runtime registry (`<cid>.json`) |
| `data/workspace/` | Root of the `/workspace/` static route |
| `data/recycle/` | Recycle directory for delete operations |
| `data/plugin/<plugin name>/` | Plugin-owned storage (a plugin sees only its own directory) |
| `data/cache/` | Derived cache, including the session encryption key |
| `data/auth/` | Password credentials, API tokens, and the authentication log; excluded from release packages |
| `data/logs/errors.log` | Process error log (JSONL; kernel/plugin assembly and host runtime failures; tool business failures are returned as `ToolResult` and are not recorded here; rotates to `errors.log.1` at about 2 MB) |

Directories are created lazily: a fresh checkout has no `data/`, and only the directories used by a run appear.

## Further reading

- [Architecture](../architecture.md)
- [Glossary](../glossary.md)
- [Context management](../subsystems/context.md)
