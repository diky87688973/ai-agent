**English** | [中文](README.zh.md)

# AI Agent

<p align="center">
  <strong>An extensible, composable AI Agent foundation</strong>
  <br>
  Runs locally or as a service. Inspectable execution, controlled writes.<br>
  Extend and compose models, tools, plugins, and business integrations.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-v0.1.5-blue" alt="version">
  <img src="https://img.shields.io/badge/Python-3.10%2B-brightgreen" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
</p>

## Download

Open [Releases](https://github.com/diky87688973/ai-agent/releases), choose a version, and download from **Assets**.

### Windows

- `ai-agent-<version>-full-pack-windows.zip`
  For first-time use. Unzip and run `agent-gui.exe`.

- `ai-agent-<version>-update-pack-windows.zip`
  Only for automatic updates of an installed copy. It cannot run standalone.

### macOS

- `ai-agent-<version>-full-pack-macos.zip`
- `ai-agent-<version>-update-pack-macos.zip`

macOS packages are not built yet. Current releases provide Windows packages only.

## Highlights

- **Local-first, model-endpoint agnostic** — sessions, files, tools, and write gates run on the local machine. Configure model endpoints and reasoning levels as needed.
- **Four entry points, one kernel** — desktop GUI, Web UI, interactive terminal, and headless execution share sessions, tools, and gates. Switching entry points does not change behavior.
- **Service-ready** — the kernel is not tied to a UI. The Web entry provides local HTTP/SSE and health checks. The headless entry targets scripts, CI, tickets, and external systems. Plugins can add their own HTTP endpoints.
- **Access control** — browser login, one-time GUI auto-login, scrypt passwords, HttpOnly sessions, CSRF, scoped tokens, login rate limiting, and TLS for public bindings.
- **Plugin extensions** — tools, executors, context, prompts, gates, model catalogs, HTTP endpoints, and UI assets can be added without changing the kernel. Built-in plugins include Skills, Rules, Knowledge, Multi-model, Visual Operator, and AI Speak.
- **Multi-agent collaboration** — subagents are created in batches with independent sessions and role-specific tool views. Parent/child messaging, queues, and work reports are supported.
- **Manageable long-running work** — background tasks are isolated per session with concurrency limits, timeouts, cancellation, and output retrieval. Goals, todos, and message queues support multi-turn progress.
- **Reviewable writes** — preview → review → commit → re-read. Automatic backup before edits, backup and rollback, and recycle-directory deletion.
- **Inspectable context, resumable sessions** — segment budgets, over-budget summaries, context usage, and request snapshots. Persisted fact streams and SSE resume by event coordinates.
- **Safe updates** — update-pack hash checks, staging, health checks, and rollback on failure. Regular files are replaced; `*.ini` files merge user settings.

## Quick start

### Desktop

Keep the project directory intact and double-click `agent-gui.exe` in the root.

Requires Python 3.10+ and WebView2. The first run prepares `pywebview` online. The desktop shell uses fixed port `3156`.

<img src="docs/assets/desktop.png" alt="Desktop window" width="960">

### Command line

Install:

```bash
python3 -m pip install -e ".[gui,tts]" -c constraints.txt
```

#### Web UI

```bash
agent-web --host 127.0.0.1 --port 8765
```

Open <http://127.0.0.1:8765/>. On Windows, double-click `start.bat`; on Linux/macOS, run `./start.sh`.

#### Interactive terminal

```bash
agent-cli
agent-cli --session <session-id>
```

#### Headless execution

```bash
agent-headless "question"
agent-headless --session <session-id> "question"
```

Prints the event stream and session ID. Suitable for tickets, troubleshooting, CI, and scripts.

#### Desktop window

```bash
python3 -m agent.gui.launcher
```

Uses port `3156`; independent of `agent-web` on `8765`.

## Documentation

Documentation is available in English and Chinese; English pages are canonical.

### User guides

| Document | Contents |
|---|---|
| [Configuration](docs/guide/config.md) | Configuration keys, launch arguments, environment variables |
| [Desktop entry](docs/guide/desktop.md) | `agent-gui.exe`, Python desktop shell, prerequisites |

### Developer documentation

| Document | Contents |
|---|---|
| [Architecture](docs/architecture.md) | Five layers, module chain, ports, event protocol, state lifecycle |
| [Engineering standards](docs/engineering-standards.md) | Module structure, single responsibility, asset ownership, extension paths, gates |
| [Glossary](docs/glossary.md) | Project-specific terms |
| [Kernel](docs/subsystems/core.md) | Module contracts, chain executor, host loop |
| [Context](docs/subsystems/context.md) | Three-part assembly, segment accounting, compaction and summaries |
| [Model calls](docs/subsystems/llm.md) | Request bodies, streaming, tool-call merging, error mapping |
| [Tools](docs/subsystems/tools.md) | Registration, execution pipeline, four-step write protocol, built-in tools |
| [Plugins](docs/subsystems/plugins.md) | Plugin packages, contributions, UI assets, lifecycle, boundaries |
| [Knowledge](docs/subsystems/knowledge.md) | File ingestion, selection state, injection, endpoints |
| [Multi-model](docs/subsystems/multi-model.md) | Catalog entries, settings forms, model pickers |
| [Skills](docs/subsystems/skills.md) | Three-layer disclosure, built-in/external sources, `skills` tool |
| [Rules](docs/subsystems/rules.md) | `rules/` markdown injection and hot toggle |
| [Visual Operator](docs/subsystems/visual-operator.md) | Screenshots, coordinate grid, mouse/keyboard tools |
| [AI Speak](docs/subsystems/ai-speak.md) | Text normalization, speech synthesis, plugin events, player |
| [Sessions and collaboration](docs/subsystems/session.md) | Fact logs, cross-process locks, runtime registry, collaboration mesh |
| [Subagents](docs/subsystems/subagent.md) | Parent/child sessions, batches, tool visibility, messaging |
| [Shell](docs/subsystems/shell.md) | HTTP routes, SSE, UI bundling, adapter layer |

### Internal design notes

Design records and trade-offs, not user manuals.

<details>
<summary>Expand design notes</summary>

| Document | Contents |
|---|---|
| [Background tasks](docs/plan/background-tasks.md) | Per-cid queues, concurrency limits, timeouts, cancellation, output, aggregate notices |
| [Software updates](docs/plan/software-update.md) | Version checks, hash validation, per-file switch, backup, rollback |
| [Conversation queue](docs/plan/conversation-queue.md) | Busy-time enqueue, turn-end delivery, safe insertion, edit recovery |
| [Standards alignment](docs/plan/standards-alignment.md) | Dependency cycles, gate trust, coverage accounting, budgets |
| [Structural remediation](docs/plan/structural-remediation.md) | Provider, context, shell, and gate responsibility split |
| [History paging](docs/plan/history-paging.md) | Turn paging, cursors, prepend, delayed rendering of oversized payloads |
| [Multi-model](docs/plan/multi-model.md) | Model catalogs, provider routing, protocol adapters |
| [AI Speak](docs/plan/ai-speak.md) | Text slicing, SSE, player design |
| [Visual Operator interaction](docs/plan/visual-operator-interaction.md) | Screenshots, UIA, coordinate-control decisions |
| [Visual Operator](docs/plan/visual-operator.md) | Visual Operator design record |
| [ADR: plugin subprocess isolation](docs/adr/plugin-subprocess-isolation.md) | Isolation decision record |

</details>

## Development

### Environment

Dependencies use a lock file shared with CI:

```bash
pip install -e . -c constraints.txt
```

### CI

`scripts/ci.py` runs 30 steps: 18 gates → unit tests → 10 acceptance scripts → package coverage.

The 18 gates cover dependency direction, architecture constraints, config drift, generated-doc consistency, static checks, UI/copy, complexity, applicability, and concurrency. Run `--list` for the full list.

The single source of truth for gates is `scripts/ci_steps.py`, kept aligned with GitHub Actions by `check_ci_workflow`.

```bash
python scripts/ci.py           # all checks
python scripts/ci.py --fast    # skip acceptance
python scripts/ci.py --list    # list checks
```

### Tests

`docs/unit-tests.md` is a generated readable test catalog; the source of truth is `tests/`.

Unit tests (1937 cases):

```bash
python -m unittest discover -s tests -p "test_*.py" -t tests
```

### Debugging tools

Dump the real request context of a session:

```bash
python scripts/dump_context.py --cid <session-id> --format json --out context.json
```

Inspect context segments and compaction decisions:

```bash
python scripts/inspect_compact.py                 # list sessions with logs
python scripts/inspect_compact.py <session-id>    # inspect one
python scripts/inspect_compact.py <session-id> --digest
```

Audit local JS event bindings:

```bash
python scripts/scan_js_events.py
```

## Author

- Author: Fan
- Email: diky87@qq.com

## License

[MIT License](LICENSE). Third-party notices are in [NOTICE](NOTICE).
