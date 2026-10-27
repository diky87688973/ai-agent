**English** | [中文](context-dump.zh.md)

# Context dump (developer CLI)

`scripts/dump_context.py` reads a session's facts through the production assembly and reconstructs the full context of the latest request. It is read-only, does not call the model, and is not registered as a model tool.

## Usage

```bash
python scripts/dump_context.py --cid <session-id>
python scripts/dump_context.py --cid <session-id> --format json --out context.json
python scripts/dump_context.py --cid <session-id> --format json --include-tools --out context.json
```

Optional arguments:

| Argument | Meaning |
|---|---|
| `--data-root` | Data root; defaults to the project configuration |
| `--plugins-dir` | Plugin root; defaults to the project configuration |
| `--plugins-path` | Plugin manifest; defaults to the project configuration |
| `--out` | Output file; defaults to stdout |
| `--format` | `text` / `json` |
| `--include-tools` | Include full tool schemas in the JSON output |

## Assembly boundary

```text
build_app() reads the real config.ini / plugins.ini
→ SessionStore reads the session facts
→ SessionRunner provides the system prompt and mode tail
→ ContextCompactor restores the summary and covered_end
→ ContextPipeline assembles the header, dialogue, and tail
```

The output contains:

```text
messages          actual request messages
system_prompt     system prompt
mode_note         execution mode + Todo-List + plugin prompt tail
segments          plugin segment names and counts
event_count       number of facts
covered_end       compaction coverage point
tools_count       number of tools
```

The script does not write session facts or call the model. Context may contain user data; output is written only to stdout or a local file.

The script is not registered as a model tool. The model-side entry point is the built-in Skill:

```text
skills/context-dump.md
```

When the user asks to export context, the model reads that Skill first, then runs the script with its commands through `run_command`. The Skill specifies the current session ID, the output directory, the JSON/TXT dual export, and the acceptance summary.
