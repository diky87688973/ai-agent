**English** | [中文](skills.zh.md)

# Skills (`skills` plugin)

Skills are **instruction documents the model can read on demand**: a set of `.md` files, each with a name and a description. The `plugins/skills` plugin provides the skill library, the `skills` tool, two context-injection sources, and the `## 资源目录` system-prompt section. Removing the `[plugin:skills]` section removes all of these capabilities together; the kernel is unaffected. Skills have two sources: a built-in directory shipped with the repository and an external directory configured by the user.

For how plugins are organized and how extension points work, see [plugins.md](plugins.md).

## Progressive disclosure

Skill bodies are **not placed into the request in full**. They are supplied in three layers:

| Layer | Content | When it enters context |
|---|---|---|
| First layer | Catalog of ordinary skills (name + description) | Present on every request |
| Second layer | Bodies of skills under `auto_load/` | Present on every request |
| Third layer | Bodies of all other skills | **Not in context**; the model reads them on demand with `skills action=read` |

An empty catalog or an empty resident body is not injected. The catalog alone is enough to decide which skill to use; the body is read after that decision. The catalog is the index, the body is the content: keeping the two separate is the point of this disclosure scheme.

## Directory layout

The built-in source is fixed at `<project-root>/skills`. A sample layout:

```text
<project-root>/skills/
  auto_load/            skills in this subdirectory always travel with the context
    python-coding.md
  engineering/
    code-review.md      the subdirectory name becomes part of the skill name: `engineering/code-review`
  context-dump.md       context-export guidance at the root
  writing.md            a skill at the root
```

The external source is set by `dir` and has the same layout:

```text
<user dir>/
  auto_load/
  engineering/
  writing.md
```

Both sources are scanned. When both produce the same skill name, the external one overrides the built-in one. A skill name is its path relative to its own root with `.md` removed; skills under `auto_load/` keep that prefix (`auto_load/python-coding`).

## Configuration

```ini
; plugins/skills/plugin-config.ini
[config]
dir =
max_file_size = 200000
```

Identity is in `plugin-meta.json`; the switch is in `plugins.ini`.

| Key | Description |
|---|---|
| `plugin-meta.json` | Identity: `name`, `desc`, `icon`, `version` |
| `dir` | **User external** skills directory. Relative paths resolve against the project root; the built-in source remains available when this is unset or missing |
| `max_file_size` | Per-skill byte limit; files above it are truncated. Empty defaults to 200000 |

The built-in source is fixed at `<project-root>/skills` and is not affected by `dir`. The configuration file is inside the plugin's own directory, so it is deployed and removed with the plugin; the kernel's `config.ini` has no such section. The `AI_AGENT_SKILLS_DIR` environment variable overrides `dir`, giving tests and CI an independent external-directory entry point.

## Metadata

`library.SkillManager` scans both sources. A skill's name is its path relative to the source root with `.md` removed; `description` comes from frontmatter. A `name` field in frontmatter does not override the path-derived name.

```markdown
---
name: python-coding
description: Engineering conventions to follow before and after writing .py files
---

Body text...
```

Without frontmatter, the description stays empty (shown as `（无描述）` in the catalog); the name still comes from the path. Scan results are cached against file modification times; a change triggers a rescan.

## Two injections and their headings

The plugin registers **two context injection sources**, both under its own segment key (the plugin name, `skills`):

| Segment | Content | Heading |
|---|---|---|
| `Skills 清单` | One instruction line, then one row per listed skill with name and description | `【Skills 清单】`, with `【内置 Skills 清单】` / `【用户 Skills 清单】` groups (each present when non-empty) |
| `Skills 常驻` | Bodies of `auto_load/` skills from both sources, one message per skill | `【内置 Skills <name>】` / `【用户 Skills <name>】` |

Both injections occupy their own row in the context breakdown.

## System prompt: resource directory

The plugin registers the `## 资源目录` section with the system prompt. The built-in and user skill roots are computed by the plugin at runtime; no absolute path is hard-coded.

```text
## 资源目录
- 内置skills: <project-root>/skills
- 外置skills: <user dir>
```

When no external directory is configured, the section reads:

```text
## 资源目录
- 内置skills: <project-root>/skills
- 外置skills: 未配置
  外置skills目录为用户skills目录，当前未配置外置skills目录，必要时提醒用户在"Skills"插件中配置dir即可
```

When `dir` is set but the directory does not exist, the line becomes `- 外置skills: <path>（不存在）`.

This section is part of the system prompt and does not occupy a context segment of its own. The Rules plugin appends its own `- 规则rules:` line and editing hint to the same section; that literal is a model-facing marker.

Source headings are model-facing only; the UI does not show source attribution, and the two context segments keep their labels and counts. The headings let the model distinguish skill instructions from user dialogue and knowledge-base material. Both context injections sit after the system prompt and before the knowledge base, following the plugin order in `plugins.ini`; `## 资源目录` belongs to the system prompt itself. They change only when files or configuration change (see [context.md](context.md)).

## Available skill count

In the context breakdown, the `Skills 清单` row shows a count in the form `N个`. The number is the length of `SkillManager.list_skills()`, so it counts ordinary skills only; resident `auto_load/` skills are excluded. It is not computed by counting lines in the catalog body.

## The `skills` tool

```json
{"action": "list"}
{"action": "read", "name": "engineering/code-review"}
```

| action | Behavior |
|---|---|
| `list` | List ordinary skills (name + description) |
| `read` | Read one skill body (truncated above the limit); when the name is not found, raises `SkillLookupError` with the available names |

The user skills root is written into the `## 资源目录` section of the system prompt; the `skills` tool description is fixed and carries no environment paths. When no external directory is configured, the resource-directory section says so explicitly and tells the model to remind the user, when necessary, to set `dir` in the Skills plugin. When a configured directory does not exist, the line is marked `（不存在）`. `skills` only lists and reads; it does not copy, move, or write files.

## Loading and configuration

Loading is controlled by the `[plugin:skills]` section in `plugins.ini`: without that section the plugin is not loaded, and `enabled = 0` keeps it in the manifest but skips loading. The plugin's settings file is `plugins/skills/plugin-config.ini`.

## Further reading

- [plugins.md](plugins.md): plugin system contract, extension points, UI assets
- [context.md](context.md): assembly order and kernel-plugin collaboration
- [guide/config.md](../guide/config.md): kernel configuration items
