# Image generation (image_gen)

Generates images with a local diffusion model. Weights and the runtime live under `model_dir`;
the plugin itself only handles confirmation, scheduling and result hand-off, and loads no
diffusion dependency in the main process.

## Asset ownership

| Owner | Location |
| --- | --- |
| Tool declaration and action flow | `plugins/image_gen/plugin.py` (`ToolPlugin`; a single tool `image_gen`) |
| Environment probing, config merge, command assembly, task index | `plugins/image_gen/engine.py` |
| Model catalog (size / suggested VRAM / mirror / auth) | `plugins/image_gen/models.py` |
| Generation subprocess (load → sample → save → exit) | `plugins/image_gen/runner.py` |
| Download subprocess | `plugins/image_gen/fetcher.py` |
| Config template (committed, empty by default) | `plugins/image_gen/plugin-config.ini` |
| Runtime state (`task-index.json`) | `data/plugin/image_gen/` (injected by the host via `ctx.data_dir`) |
| Generated images | `<model_dir>/output/` |

Configuration has a single source, `plugin-config.ini`; runtime state holds only the task index.

`plugin-config.ini` is committed as an empty template and filled in by install guidance or the user;
runtime task index lives under the ignored `data/`. The plugin never assembles the data path itself and
fails loudly when the injection is missing.

## Configuration

Configuration lives in `plugin-config.ini` (committed, all three keys empty by default) and is filled in by install guidance or by the user:

| Key | Meaning |
| --- | --- |
| `model_dir` | Install directory. When it contains `models/`, that subdirectory is the weight root; otherwise the directory itself is. Images and downloads live here |
| `runtime_python` | Interpreter with torch / diffusers / transformers; generation and download run as its subprocesses |
| `default_model` | Default model id. Empty means unconfigured, so `model` must be passed explicitly; filled in by install guidance or by the user |

All three keys are filled in only during install guidance or by the user; the plugin ships no defaults.
The directory confirmed there, together with the model picked, is written back to the same
`plugin-config.ini`.

## Tool actions

| Action | Behaviour |
| --- | --- |
| `generate` (default) | An omitted `model` falls back to the configured `default_model`; when both are absent it errors out. The model gate runs first: empty `model_dir` or no installed model returns `needs_setup` with the catalog and local GPU advice; otherwise a background task is created and `task_id` is returned immediately |
| `check` | Probes GPU and installed models only |
| `download` | Requires `confirmed=true`; gated repositories return `needs_auth` with anonymous alternatives; a missing directory returns `need_model_dir` |
| `status` | Reads the result file for a `task_id` and returns `image_path`; never reads background task output |

Long-running work reuses the host background task service (`SERVICE_BACKGROUND_TASKS`); the
plugin does not build its own queue.

## Dependencies

Main process: `requests` (see `plugins/image_gen/requirements.txt`).
`runtime_python` side: `torch`, `diffusers`, `transformers`, `safetensors`, `accelerate`, `gguf`, `Pillow`.

## Weight licensing

No weights ship with the plugin; users download from the catalog:

| Model | Licence |
| --- | --- |
| FLUX.1-dev (including community quants) | BFL Non-Commercial License, non-commercial use only |
| FLUX.1-schnell | Apache-2.0 |
| SDXL base 1.0 | OpenRAIL++ |

## Failure behaviour

| Situation | Result |
| --- | --- |
| `model_dir` unset / no installed model | `needs_setup` with catalog and recommendation |
| VRAM below the catalog suggestion | Subprocess reports and writes a result file; `status` returns `failed` with the reason |
| Download source returns 401 | `needs_auth`; the plugin never silently swaps models |
| Config or index read failure | Reported, then defaults are used; a parse failure is not treated as a normal empty value |
| Result file write failure | Subprocess logs to stderr; `status` falls back to the task state |
