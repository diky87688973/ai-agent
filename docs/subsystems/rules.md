**English** | [中文](rules.zh.md)

# Rules (`rules` plugin)

Rules is a **rule directory**: every `.md` file under `<project-root>/rules/` enters context as a `system` message, one file per message. For the plugin mechanism itself, see [plugins.md](plugins.md).

**Naming**: Rules is the whole rule system; user rules are one kind within it (system rules are also possible). The plugin, documentation, and UI therefore use **Rules**, not "user rules". The model-facing markers are `- 规则rules:` (resource-directory line) and `【规则 Rules <path>】` (body heading).

## Two `rules` locations

| Path | What it is |
|---|---|
| `plugins/rules/` | Plugin code (`plugin.py` + `plugin-meta.json`) |
| `<project-root>/rules/` | Rule-file directory, sibling to `skills/`. **User-edited rules live here** |

The plugin directory has no `plugin-config.ini`, no `settings-schema.json`, and no `ui/`. This plugin has no editable settings, so the settings page does not show a Settings button (declared by `config: "false"` in `plugin-meta.json`; see [plugins.md](plugins.md)).

## Package layout

```
plugins/rules/
  plugin.py            entry: rule-directory scan, read, injection, resource-directory section
  plugin-meta.json     identity metadata (name / desc / icon / version / config)
rules/                 rule-file directory (sibling to skills/)
  USER_RULES.md        built-in rule file (initially empty; content takes effect when added)
  <other rules>.md
```

`USER_RULES.md` is the **conventional landing file**: when the system writes rules for the user, or when a user states a rule that should be recorded, write it here. It is treated exactly like any other `.md` file in the directory; there is no special logic.

## Collection

- Recursively scan `<project-root>/rules/` and collect only `.md` files.
- Skip hidden paths whose segment starts with `.`, and skip `__pycache__`.
- Sort by relative path for a stable injection order.
- Per-file limit: **200000 bytes** (code constant, not configurable). Files over the limit are skipped and recorded as a `rules.too_large` error; they are not silently dropped.
- Empty files (body is only whitespace) do not count as entries. `USER_RULES.md` starts empty, so the Rules segment count is 0 at that point.
- If the directory does not exist, the plugin still exists (segment placeholder, count 0) but injects no body.

## Injection

Each rule file produces one `system` message whose heading is the relative path:

```
【规则 Rules project-audit.md】
<file body>
```

`label` is `Rules`; `count` is the number of injected files. Both are declared with the injection source. Assembly position comes from `plugins.ini` (this plugin is after `skills`); see [context.md](context.md).

Body reads are cached by `(path, mtime_ns, size)`: multiple collections in one assembly pass read the disk once, and cache entries invalidate automatically after a file changes.

The rules segment does not participate in summary compaction: plugin segments are re-collected on every assembly pass, so rules do not disappear because of compaction. The cost is paying their tokens every turn.

## System prompt: resource directory

The plugin appends two lines to the `## 资源目录` section (the same heading used by Skills; bodies merge by manifest order):

```
- 规则rules: <project-root>/rules
  Rule files (*.md) in this directory are injected into context automatically. Edit rules in this directory; USER_RULES.md is the default user-rule file.
```

If the directory does not exist, the line is marked `- 规则rules: <path>（不存在）` and indicates that the directory is missing.

## Usage in the context view

The segment key in the context breakdown is `plugin:rules`; segment name is `Rules` (green). The UI row shows “Rules | share | N items | tokens”, meaning rule-file count and token usage. See [context.md](context.md).

## Hot toggle

The `[plugin:rules]` section in `plugins.ini` controls loading. Toggling it in settings immediately unloads or loads the plugin:

- Unload: injection source, the two `## 资源目录` lines, and segment color are all removed (three disposers).
- Load: re-register; injection resumes immediately.

Without a page refresh, injection in the current session already reflects the change because it happens during server-side assembly. The on-screen segment color refreshes only on the next page load (the same known limitation as other plugins).

## Further reading

- [plugins.md](plugins.md): plugin packages, extension points, lifecycle
- [context.md](context.md): how injection sources enter assembly, segment accounting, assembly order
- [skills.md](skills.md): another contributor to the same `## 资源目录` section
