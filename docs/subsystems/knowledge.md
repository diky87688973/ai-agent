**English** | [中文](knowledge.zh.md)

# Knowledge base (`knowledge` plugin)

The knowledge base injects selected text and spreadsheet files from a local directory into the conversation context as attached material. Configuration checks, path safety, file reading, selection state, injection, and the UI are all provided by this plugin; the kernel only provides generic extension points. For the plugin mechanism itself, see [plugins.md](plugins.md).

## Package layout

```
plugins/knowledge/
  plugin.py            entry: config checks, file layer, selection state, injection, endpoints
  plugin-config.ini    actual configuration (committed)
  plugin-meta.json     identity metadata
  ui/panel.js          right-panel script
  ui/panel.css         panel styles
```

## Configuration

```ini
; plugins/knowledge/plugin-config.ini
[config]
max_file_size = 200000
extra_suffixes =
```

Identity is in `plugin-meta.json`; the switch is in `plugins.ini`.

| Key | Default | Description |
|---|---|---|
| `dir` | empty | Knowledge-base root. Relative paths resolve against the **project root**; when empty, missing, or not a directory, the plugin provides no files, and the file list and injection output are empty |
| `max_file_size` | `200000` | Per-file byte limit; files above it are not read. `0` means unlimited |
| `extra_suffixes` | empty | Additional accepted extensions, comma-separated; `txt` and `.txt` are equivalent; a malformed entry is ignored |

When `enabled` is `0` in `plugins.ini`, the plugin stays in the manifest but is not loaded. `name` / `icon` come from `plugin-meta.json` and supply the panel title and the input-area button label.

## Accepted files

- Text extensions are listed in `TEXT_SUFFIXES` (`.md` `.txt` `.csv` `.json` `.yaml` `.ini` `.py` `.js` `.html` `.css`, and others), plus `extra_suffixes` from configuration;
- `.xlsx` / `.xls` / `.xlsm` are parsed as spreadsheets and require `openpyxl`; without the library such a file cannot be selected, and validation returns an installation hint;
- Files without an extension are treated as text (`Dockerfile` / `Makefile` / `README`, and others);
- Hidden paths (any segment starting with `.`), `__pycache__`, and non-text files are not listed; hidden paths and non-text files are also rejected during selection validation.

`list_files()` filters only by hidden path, `__pycache__`, and text type; the byte limit and table dependency are checked again when a selection is written, so an oversized file or a spreadsheet without `openpyxl` can appear in the list but cannot be selected.

## Path safety

`safe_resolve(rel)` resolves a relative path to a real file under the root; it returns `None` if any condition fails:

- an empty value, an absolute path, or a path that escapes the root through `..`;
- a hidden path where any segment starts with `.`;
- the resolved real path is outside the root;
- the target is not a file or does not exist.

The per-file byte limit, accepted types, and table dependency are re-checked in `file_allowed()`; validation runs again before a selection is written and before every injection, so replacing a file on disk cannot bypass the rules.

## Selection state

Selections are recorded **per conversation**: the key is the conversation id and the value is a set of relative paths.

- State is stored at `<data-root>/plugin/knowledge/checked_state.json` and loaded in full at startup;
- if the file is missing or corrupt, the set stays empty with no error;
- disk-write failures are silent: selection is a UI preference and does not block injection for the current conversation;
- writes replace the whole set: an empty list clears that conversation's selection;
- paths that fail validation are dropped; the return value contains the paths actually accepted.

A selection change calls `bump_context_sources` on the host registry, making the assembly side discard cached collection results; when the hook is unavailable, the change takes effect on the next round.

## Injection

`build_system_messages(cid)` produces one system message per selected file:

```
【知识库：docs/guide.md】
<file body>
```

Body reads are cached by `(path, mtime_ns, size)`; multiple collections in one assembly pass read the disk only once, and the cache invalidates automatically after the file changes. Spreadsheets are rendered as a `[Sheet: name]` line per sheet, followed by tab-separated rows; a failed spreadsheet parse produces only a one-line note and does not affect other files in the same batch. Empty files are not injected.

The injection source declares `label` and `count`: the segment name is used by the UI and the context breakdown, and `count` is the number of files that are actually injectable. Assembly position is determined by plugin order in `plugins.ini`; see [context.md](context.md#assembly-order).

## Endpoints

The prefix is `/api/plugin/knowledge/`:

| Method and path | Request | Response |
|---|---|---|
| `GET files` | — | `{ok, enabled, files: [{path, name, mtime}]}`; `files` is empty when the plugin is disabled |
| `GET checked` | query string `conversation_id` | `{ok, checked: [relative paths]}` |
| `PUT checked` | body `{conversation_id, checked: [...]}` | `{ok, checked: [accepted paths]}`; a missing conversation id returns 400 |

`path` is always a POSIX-style path relative to the root; the UI sends back the same shape.

## Panel

The right panel loads `ui/panel.js` and `ui/panel.css`; the script calls this plugin's endpoints through `window.aiAgentPlugins`. The panel fetches selections by conversation and refetches when the conversation changes; the refresh button on the right of the hint bar rereads the knowledge-base directory. When the directory is unconfigured, empty, or fails to load, the panel shows the corresponding state without hiding the panel itself.

The plugin registers a context-segment appearance (`add_ctx_segment_style`, color `blue`) and an input-area action button; clicking the button opens the panel with the same id.

## Further reading

- [plugins.md](plugins.md): plugin packages, extension points, lifecycle
- [context.md](context.md): how injection sources enter assembly and segment accounting
- [tools.md](tools.md): disk-write protocol (the knowledge base itself is read-only)
- [../guide/config.md](../guide/config.md): configuration reference
