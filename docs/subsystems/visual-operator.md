**English** | [中文](visual-operator.zh.md)

# Visual Operator (`visual_operator` plugin)

Visual Operator turns screen viewing and mouse/keyboard operation into four tools, letting the model read the screen, locate targets, click, type, and wait on a real desktop. Screenshots are returned as image attachments; the plugin keeps only coordinate-mapping metadata and does not retain screenshot files. Mouse and keyboard input actions are serialized through an input lock. The plugin mechanism itself is described in [plugins.md](plugins.md).

## Package layout

```
plugins/visual_operator/
  plugin.py                  entry point: loads config, selects backend, registers four tools
  plugin-config.ini          configuration read at load time
  plugin-meta.json           identity metadata
  config.py                  [config] reading, fallback, and clamping
  capture_store.py           screenshot mapping registry (metadata only, no image bytes)
  keys.py                    key names, aliases, and hotkey validation
  coords.py                  screen rects / points / geometry
  ports.py                   backend ports and data structures
  canvas.py                  scaling, coordinate grid, cursor crosshair, PNG encoding
  diff.py                    region comparison before and after an action
  guard.py                   Plan-mode gating
  input_lock.py              input lock shared by mouse and keyboard
  errors.py                  exception hierarchy
  tools/
    _params.py               argument parsing and action matrix
    _windows.py              window / hwnd resolution, candidates, and foreground activation
    _capture.py              single implementation of capture, rendering, receipt, and notes
    eye.py                   desktop_eye
    mouse.py                 desktop_mouse
    keyboard.py              desktop_keyboard
    wait.py                  desktop_wait
  backends/
    __init__.py              backend selection by platform
    win32.py                 Windows: GDI + SendInput + hit probing
    macos.py                 macOS: screencapture + CoreGraphics
    _unavailable.py          other platforms: report a clear reason at call time
```

## Four tools

| Tool | Direction | Capability |
|---|---|---|
| `desktop_eye` | Model input | Captures the full screen, a region, or a window, overlays a coordinate grid, and returns the result as an image attachment; `hover` can expand hover-only controls before capture |
| `desktop_mouse` | Desktop output | `move` / `click` / `drag` / `scroll` / `cursor` |
| `desktop_keyboard` | Desktop output | `type` arbitrary Unicode text / `key` a single key / `hotkey` a key combination |
| `desktop_wait` | Condition wait | Waits for a screen change, a window to appear, or a window to disappear; returns as soon as the condition holds |

Each tool declares its own complete JSON Schema instead of sharing one multi-action tool. The action matrix in `tools/_params.py` validates which arguments belong to each action: arguments for another action are rejected rather than silently ignored.

### `desktop_eye`

| Parameter | Description |
|---|---|
| `x` / `y` / `width` / `height` | Region; supply all four or none, and width and height must be positive. A region is clipped to the screen (and to the selected window when one is given); a region with no intersection is rejected |
| `window` / `hwnd` | Capture the window's own content. Choose one; `hwnd` is a positive handle and is exact. Implemented by the Windows backend |
| `activate` | Whether to bring the window to the foreground before capture; default `false` restores a minimized window without changing the foreground. Only valid with `window` / `hwnd` |
| `hover` | `[x, y]` in screen coordinates: move the cursor there before capture to expand control bars, drop-down menus, or tooltips |
| `hover_path` | `[[x, y], ...]`: 1–4 intermediate points walked before `hover`; requires `hover` |
| `hover_settle_ms` | Milliseconds to wait after the cursor move for the interface to expand, `0–5000`; defaults to the plugin configuration |
| `hover_approach_ms` | Milliseconds used to move to the target, `0–2000`, default `120`; `0` = a single jump |
| `hover_wiggle` | Whether to make a few 1–2 px moves near the target after arrival; default `true` |
| `grid` | Whether to overlay the grid and labels; default `true` |
| `grid_step` | Grid spacing in screen coordinates, `20–500`; defaults to the plugin configuration. Use `20–40` for small targets |
| `grid_unit` | Label unit: `screen` screen coordinates (default) / `image` image pixels |
| `max_side` | Long-side limit, `0–8192`; `0` disables scaling; defaults to the plugin configuration |
| `annotate` | `annotated` returns only the annotated image (default) / `raw` returns only the original / `both` returns the annotated image then the original; `attachment_order` states the order |

If a captured window was minimized, capture restores it first and marks `restored` in the receipt.

`hover` is what makes "move the cursor and capture" reliable: hover controls usually collapse within 2–3 seconds, while the model round trip between two tool calls takes longer. For window capture, the cursor move runs after the window is restored or activated and before the actual capture; with the reverse order the image would show either an unexpanded control or a control expanded on another window. Because `hover` changes desktop state, Plan mode rejects `desktop_eye` calls that include it; calls without `hover` remain available.

Movement is not a single jump: the tool walks the `hover_path` points first, moves continuously to the target using `hover_approach_ms`, and then makes a few 1–2 px moves near the target. Auto-hiding controls in players and web pages use continuous `WM_MOUSEMOVE` to decide that the pointer is moving; a single `SetCursorPos` followed by no movement is treated as no movement. The trajectory and the wiggle are real cursor movement, not only numbers in the receipt. After the wiggle the actual cursor is read back and returned to the target; if the target window steals the cursor and it cannot be returned, the call raises `DesktopError` rather than treating the shifted position as the target.

The receipt's `hover.hit` identifies the window under the cursor. If it is not the same window captured for this call, `note` says so: a player surface is often a separate top-level window, while a title lookup selects another window that hosts the detail page. Changing `y` does not change that target; `hwnd` selects the cursor's window.

With `hover` but no `window` / `hwnd` and no region, the capture target is the window under the cursor (receipt `window.auto="hover.hit"`): the window's own pixels, unobstructed; `max_side` still applies. In that hover case, omitting the window and region arguments captures only the cursor-layer window; a full-screen or different-window capture requires explicit arguments.

Return value (`data`):

```json
{
  "platform": "win32",
  "screen": {"x": 0, "y": 0, "width": 2560, "height": 1440},
  "capture": {"x": 0, "y": 0, "width": 2560, "height": 1440},
  "source": "screen",
  "annotate": "annotated",
  "image": {"width": 2560, "height": 1440, "sent_width": 1920, "sent_height": 1080,
            "scale": 1.3333, "bytes": 548735},
  "image_to_screen": {"scale_x": 1.3333, "scale_y": 1.3333, "ox": 0, "oy": 0},
  "capture_id": "a1b2c3d4e5f6",
  "dpi": "96 dpi",
  "cursor": {"x": 734, "y": 709},
  "grid": {"step": 100, "unit": "screen", "scale": 1.3333},
  "note": "图片已从 2560x1440 缩到 1920x1080；…"
}
```

The image is returned by `ToolResult.attach` as an `image/png` attachment. Attachments occupy a separate field of the result envelope, not `data`, and no temporary file is retained. With `annotate=both`, two attachments are returned, ordered by `attachment_order`: `["annotated", "raw"]`; `raw_image` describes the original image.

`capture_id` is a key into an in-memory map, not a file path: the registry stores only the `capture` rect, image dimensions, hwnd, and creation time, never the PNG. Entries expire after 300 seconds and each plugin instance keeps at most 64; after a restart or eviction an old ID is invalid and a new screenshot is required. `image_to_screen` is the readable form of the same mapping for diagnostics and UI; the server performs the conversion, so the model does not use it for multiplication.

With `grid_unit=image`, grid labels and the cursor label are in image pixels; the default `screen` keeps screen coordinates, and `hover`, region arguments, and `desktop_wait` regions remain in screen coordinates. To click in image coordinates, capture with an image-unit grid and pass the `capture_id` plus image x/y to `desktop_mouse`.

A single screenshot is limited to 40 million pixels; above that the call fails and asks for a region instead.

### Windows with the same title

On Windows, `window` is a case-insensitive title fragment, and several windows may match at once (self-drawn applications commonly have a main window, a player layer, and a hidden helper window). Candidates are ordered by foreground → Z-order → area (largest first), not by area alone: the window in front of the user is almost always the intended target, while the largest window may be a player layer covering the content.

When more than one window matches, the receipt's `window` includes `matched` and `alternatives` (up to four), and `note` states how many matched, which one was selected, and the other hwnds. A bare match count does not identify the remaining windows, so the receipt names them.

### Scaling and conversion

Full-screen images are usually shrunk to `max_side`; window images often stay below the limit and are sent at native size. Image coordinates may be scaled, and the origin may be negative for window shadows.

When `desktop_mouse` receives a `capture_id` plus image x/y, it converts with the registry's `capture` rect and image dimensions; the model does not multiply:

```
screen_x = capture.x + image_x * capture.width / image.width
screen_y = capture.y + image_y * capture.height / image.height
```

`space=image` declares image coordinates explicitly; providing only a `capture_id` also implies image coordinates. `space=screen` (default) still accepts screen coordinates; the two spaces are not mixed. An ID that is unknown, expired, or belongs to another session is rejected, not retried as screen coordinates.

For detail that is hard to read, capture a region: regions are usually sent at native size. For small targets, `grid_step=20–40` gives a finer grid so coordinates can be read directly instead of estimated within a 100 px cell.

### `desktop_mouse`

| `action` | Required | Optional |
|---|---|---|
| `move` | `x`, `y` | `duration_ms` (0–5000, default 0) |
| `click` | — | `x`, `y`, `button` (left / right / middle), `count` (1–3) |
| `drag` | `x`, `y`, `to_x`, `to_y` | `button`, `duration_ms` (default 300, 0–5000) |
| `scroll` | `amount` (-50–50, nonzero; positive scrolls down / right) | `x`, `y`, `horizontal` |
| `cursor` | — | — |

`window` / `hwnd` are accepted by every action; actions other than `cursor` restore and bring the target to the foreground before acting, and a failed activation aborts the action instead of clicking through an occluding window. `cursor` does not activate because it sends no input.

`x` / `y` / `to_x` / `to_y` default to screen coordinates. With `capture_id` they are interpreted as image pixels of that capture; adding `space=image` states this explicitly. `space=screen` rejects `capture_id`, so one set of numbers is not interpreted by two coordinate systems. Image coordinates require a point inside the image; they do not fall back to the current cursor position.

`click` / `scroll` without coordinates act at the current cursor position. After an action the tool returns the cursor position and screen rect; `cursor` is read-only and does not trigger Plan-mode gating.

Actions that change the interface (`click` / `drag` / `scroll`) also return three pieces of evidence:

| Field | Meaning |
|---|---|
| `hit` | Window handle, control class, and owning top-level window title under the point; omitted when the backend has no hit probing |
| `changed` / `changed_scope` | Pixel change ratio (0–1, three decimals) in up to 200×200 around the point, clipped to the screen; `scope` is always `point_200`; reports only whether the local area moved |
| `window_changed` | Window-layer comparison: `hit_before` / `hit_after`, `opened` / `closed`, `changed`, `navigated` |

`hit` answers what was hit; `changed` answers whether the local area responded. Navigation clicks (card → detail page, opening a new window) change the window layer: `changed` may remain `0.0`, in which case `window_changed.navigated=true` indicates navigation. When the first `changed` sample is below 0.005, the tool waits 250 ms and samples again; the second value is `changed_late`. If it is larger, `changed` takes it and `changed_note` records the reason.

`window_changed` includes `opened` / `closed` only when the window set actually changed (up to three each; `opened_more` / `closed_more` count the rest). A failed window-list read skips that observation without turning a delivered action into a failure.

`shot=true` captures within the same call after the action and returns the image attachment, avoiding another `desktop_eye` round trip:

| Parameter | Description |
|---|---|
| `shot` | Whether to return an image with the action; default `false` |
| `shot_region` | `[x, y, width, height]`; defaults to the window under the point or the full screen. Clipped to the capture target |
| `shot_max_side` | Long-side limit for the returned image; defaults to the plugin configuration |

With `shot`, the returned body is the capture receipt and the action result is in `performed`. The image follows the window where the action actually landed (`shot_of: "hit"`), not a re-resolution by `window` title: a click may land on a separate top-level player window while the title selects another window hosting the detail page. An explicit `window` / `hwnd` takes precedence (`shot_of: "window"` / `"hwnd"`); when neither is present and no landed window is available, the capture falls back to the screen (optionally `shot_region`). If the landed window differs from the activated window, `note` states both hwnds. `shot` is available for `move` / `click` / `drag` / `scroll`; `cursor` is a read-only query and rejects it. `move` returns an image only and does not compute `hit` / `changed`: movement does not change the interface, but hovering may expand controls, so the image remains useful.

### `desktop_keyboard`

| `action` | Parameters |
|---|---|
| `type` | `text` (any Unicode, including newlines and tabs; newline is sent as Enter, tab as Tab) |
| `key` | `key`, `repeat` (1–20) |
| `hotkey` | `keys` (`"ctrl+c"` / `"alt+tab"`), `repeat` (1–20) |

All actions also accept `window` / `hwnd`: the target is restored and brought to the foreground before input, and the receipt includes `focus`; a failed activation aborts the input instead of typing into another window. `shot` / `shot_max_side` return an image after the action.

Key names are normalized before dispatch: `return` → `enter`, `escape` → `esc`, `control` → `ctrl`, `option` → `alt`, `command` / `meta` / `super` → `cmd`, `windows` → `win`, `pgup` / `page_up` → `pageup`, `pgdn` / `page_down` → `pagedown`; direction keys, `f1`–`f20`, letters, digits, and the single-character keys `-`, `=`, `[`, `]`, `;`, `'`, `,`, `.`, `/`, `\`, and the backtick. Hotkeys contain 2–4 keys, at least one of which is not a modifier, separated by `+` or `,`.

### `desktop_wait`

| Parameter | Description |
|---|---|
| `until` | `change` screen change / `window_appears` window appears / `window_disappears` window disappears |
| `window` / `hwnd` | For `change`, limits the comparison region to the window rect. For `window_appears` / `window_disappears`, `window` is required and `hwnd` alone is rejected |
| `x` / `y` / `width` / `height` | Comparison region for `change`; supply all four together, width and height positive. Defaults to the window rect or the full screen. An explicit region takes precedence over the window rect |
| `timeout_ms` | Maximum wait, `50–60000`, default 10000 |
| `interval_ms` | Poll interval, `50–2000`; defaults to the plugin configuration |
| `threshold` | Change threshold for `change`, `0–1`, default `0.02` |

Timeout is not an error: the tool returns `satisfied: false` with the measured values, leaving the next action to the model. A fixed-duration sleep ties the wait to a guess; a condition wait returns as soon as the condition holds.

`until=change` compares screen composites and does not activate windows; when a window is occluded, it still compares what is on screen. When the comparison region comes from a minimized window, the call fails instead of polling the `(-32000,...)` empty frame until timeout.

For `window_appears` / `window_disappears`, when the condition is already true at the first probe, the result includes `already: true` and a note that no actual wait occurred. Otherwise the tool polls until the condition holds or the timeout expires.

`desktop_wait` is read-only and available in Plan mode. It does not take the input lock.

## Interface display

Each tool title is followed by a one-line execution summary. The summary uses the target from the arguments when present and is completed from the receipt after execution:

| Tool | Summary | Examples |
|---|---|---|
| `desktop_eye` | `看屏 · target` | `看屏 · 窗口 -> 编辑器`, `看屏 · 局部 -> (x, y, width×height)` |
| `desktop_mouse` | `鼠标 · action -> target (position)` | `鼠标 · 点击 -> 编辑器 (x, y)`, `鼠标 · 移动 -> (x, y)` |
| `desktop_keyboard` | `键盘 · action -> content` | `键盘 · 输入 -> 示例文本` |
| `desktop_wait` | `等待条件 · condition` | `等待条件 · 窗口出现 -> 编辑器` |

Summaries are display-only: they do not participate in gating and do not invent targets absent from the arguments. For `desktop_eye` and mouse or keyboard actions with `shot=true`, the detail pane shows the receipt image directly (the same renderer as `read_image`), so no second `desktop_eye` call is needed to inspect the result.

The detail view matches `read_image`: the custom view contains the image and metadata lines (size; an optional sent-size line when scaled; then the window or screen), while the request and response are behind the `查看报文` button. A custom view does not mount its own `请求` / `响应` panes: when `.chat-tool-layer--req/res` is present, the shell treats the row as the default view and skips the packet wrapper, leaving JSON above the image.

The countdown is computed entirely in the frontend from the arguments; the server does not push timer frames. The `desktop_wait` timeout is only an upper bound: if the count reaches zero before the tool result arrives, the summary changes to `已超时 3 秒` and keeps counting until `tool_end`. On completion the timer stops and the title appends the actual wait from the receipt (`窗口出现 -> 编辑器 · 0 秒`); no “satisfied” or “not satisfied” text is added, since completion is expressed by `done` and the title color. Duration text is rendered in seconds, minutes, hours, and days, so `86400 秒` becomes `1 天` and multi-day waits need no conversion. A history replay (page refresh, switching back to a session) does not restart the countdown: that wait has already finished, and counting down from the total again would read as still waiting.

## Coordinate contract

- The default coordinate space is screen coordinates: physical pixels on Windows, global display points on macOS. With `grid_unit=image`, grid and cursor labels use image pixels; image coordinates reach `desktop_mouse` only through `capture_id` and are not used directly as screen coordinates.
- On high-DPI macOS displays a screenshot has twice as many pixels as points: `pixel_ratio` records the ratio, and mouse coordinates are still delivered in points.
- Grid lines are placed by the ratio from the screen rect to the sent image size; with `grid_unit=image`, label values are derived from the same ratio. High-DPI captures are not offset by half a screen.
- `capture` is the screen rect of the screenshot; its origin is the top-left of the window or crop and may be negative. `image_to_screen` provides `scale_x` / `scale_y` / `ox` / `oy`; conversion is server-side.
- With multiple monitors, the screen rect is the union of the virtual desktop; the top-left may be negative (a secondary display left of the main display). When scaling differs, a `note` reports that cross-screen coordinates may be slightly off.

## Capture processing

`canvas.render()` is the shared post-processing path for every platform:

1. Decode the PNG; a decode failure raises `ScreenCaptureFailed`.
2. Detect an all-black image (lock screen, UAC secure desktop, protected content) and add a `note` to the return value.
3. If the long side exceeds `max_side`, downscale with Lanczos and record `scale`.
4. With `grid` enabled, overlay the grid: a thin blue line every `grid_step` screen coordinates, and a thick red line with labels every fifth line; when the spacing is below 8 px, only major lines are drawn. Lines have a black halo, and line width grows with image width so they do not disappear after compression. Labels are rendered at the final size; with `grid_unit=image` the label text uses image pixels while line positions still follow `grid_step` screen coordinates.
5. With `cursor_mark` enabled, draw a short crosshair near the cursor only: black halo, white separator, bright green core, a small ring, and a `CURSOR` label with the coordinates. The crosshair center is left empty so the target pixel remains visible, and it does not cover the whole image. For a short side below 140, only the coordinates are drawn, without the `CURSOR` prefix and without a black background; below 90, no label is drawn and the coordinates come only from the receipt's `cursor` field. Font size is derived from the image scale and short side so the on-screen appearance is consistent across scales; label units follow `grid_unit`.
6. Encode as PNG for `desktop_eye` to attach.

## Configuration

Identity is in `plugin-meta.json`. The plugin is enabled in `plugins.ini`; capability switches and timing values are in `plugin-config.ini`.

```ini
[config]
eye = 1
mouse = 1
keyboard = 1
wait = 1
max_side = 1920
grid_step = 100
cursor_mark = 1
settle_ms = 60
type_interval_ms = 12
hover_settle_ms = 250
hover_approach_ms = 120
hover_wiggle = 1
wait_interval_ms = 200
```

| Key | Default | Description |
|---|---|---|
| `eye` / `mouse` / `keyboard` / `wait` | `1` | Capability switches; a disabled capability is not registered |
| `max_side` | `1920` | Long-side limit before sending, `0` disables scaling; clamped to `0–8192` |
| `grid_step` | `100` | Grid spacing in screen coordinates; clamped to `20–500` |
| `cursor_mark` | `1` | Whether the capture draws the cursor crosshair |
| `settle_ms` | `60` | Milliseconds to wait for the interface after an input action; clamped to `0–2000` |
| `type_interval_ms` | `12` | Interval between typed characters; clamped to `0–200` |
| `hover_settle_ms` | `250` | Milliseconds to wait after a hover cursor move; clamped to `0–2000` |
| `hover_approach_ms` | `120` | Milliseconds used to move to the hover target; clamped to `0–2000`, `0` = a single jump |
| `hover_wiggle` | `1` | Whether to make 1–2 px moves after arrival, for player controls that only wake on continuous mousemove |
| `wait_interval_ms` | `200` | Default poll interval for `desktop_wait`; clamped to `50–2000` |

A missing file, a missing section, or an unparsable value falls back to the default; out-of-range integers are clamped to the boundary. Configuration errors do not block tool registration. When the grid is enabled, the effective `grid_step` appears in the receipt; the scaling produced by `max_side` appears in `image` and `note`. Other keys are not echoed.

## Platform backends

### Windows

- Capture: full-screen capture uses `GetDC(NULL)` + `BitBlt(SRCCOPY | CAPTUREBLT)` + `GetDIBits` over virtual-desktop coordinates, including secondary displays at negative coordinates. Window capture uses `PrintWindow(PW_RENDERFULLCONTENT)` to obtain the window's own redraw, so occluded content is available. Pixels are encoded directly from `BGRX` as PNG with no extra flip.
- Fallback: when `PrintWindow` returns a uniform frame (including all black), the backend retries until the repaint deadline. If content is still unavailable and the window is visible, it falls back to a screen grab and sets `source` to `screen`; an invisible window that yields no content raises `ScreenCaptureFailed`.
- Hit probing: `WindowFromPoint` gets the child window at the coordinate, `GetAncestor(GA_ROOT)` gets its top-level window, and `GetClassNameW` gets the control class. When probing fails, `hit` is omitted rather than guessed.
- Window list: `EnumWindows` enumerates visible top-level windows, skipping tool windows and off-screen helper windows. It is used only for `window_changed` comparisons and never enters the context.
- DPI: awareness is declared at load time as per-monitor v2; if the host has already declared awareness, the host's choice remains in effect. On failure the backend falls back to `SetProcessDpiAwareness` and then `SetProcessDPIAware`.
- Input: positioning uses `SetCursorPos`; buttons and keys use `SendInput`. Text uses `KEYEVENTF_UNICODE` (surrogate pairs are split into two UTF-16 units); function keys and hotkeys use virtual-key codes.
- Known boundaries: lock screens and the UAC secure desktop cannot be captured; input sent to a window at a higher integrity level is dropped by the system; mixed-scale multi-monitor layouts may still have small offsets at the system level.
- Window capture, hit probing, and the window list are implemented only in the Windows backend.

### macOS

- Capture: `/usr/sbin/screencapture -x -t png -R x,y,w,h <tempfile>`, with the region in global display coordinates (points). Image pixels are scaled by the display ratio; `geometry` reports `pixel_ratio` using `CGDisplayPixelsWide`. The temporary file is removed after reading.
- Input: CoreGraphics `CGEventCreateMouseEvent` / `CGEventCreateKeyboardEvent`; text is injected with `CGEventKeyboardSetUnicodeString`, and hotkeys set modifier flags on the events.
- Permissions: screen recording is required for capture and accessibility for input. A missing permission raises `DesktopPermissionDenied`, and the message points to the corresponding switch under System Settings → Privacy & Security.
- Capability boundary: the macOS backend has no window port or hit port. `window` / `hwnd` on `desktop_eye`, on `desktop_mouse` actions other than `cursor`, on `desktop_keyboard`, and in window-based `desktop_wait` conditions or window-region comparisons raises `DesktopUnavailable`. `desktop_eye(hover=...)` moves the cursor and captures the screen composite but does not auto-select the window under the cursor. `hit` is absent, and `window_changed` reports only `changed: false`. Input goes to the current foreground application; the caller brings the target forward by other means.

### Other platforms

Linux and unrecognized platforms use the unavailable backend: tools are still registered, and screen capture or input raises `DesktopUnavailable`. This keeps the tool table stable across machines and CI, so the model sees a clear reason instead of tools that disappear. A backend assembly failure writes one diagnostic to stderr and falls back to the same unavailable backend.

## Gating and concurrency

- Plan mode: `desktop_eye` without `hover` is allowed; with `hover` it is rejected because it moves the real cursor. The gate does not inspect `activate`, so `activate=true` can still bring a window to the foreground in Plan mode. `desktop_mouse` allows only `cursor`; every other action, and every `desktop_keyboard` action, raises `ModeConflict`. `desktop_wait` is read-only and allowed. The gate reads `live_state` per session; when it is unavailable at load time it is read at execution time, and if no state is available no gate is applied.
- Input lock: `desktop_mouse` and `desktop_keyboard` share one process-wide lock, so only one of their actions delivers input at a time; waiting more than 10 seconds raises `DesktopBusy`. Drag down and up are always paired. Cursor movement for `desktop_eye` hover does not take this lock.
- Coordinate validation: before an action, target points are checked against the screen rect; off-screen coordinates raise. Actions without coordinates use the current cursor position and have no point to validate.

## Failure messages

| Exception | Meaning |
|---|---|
| `DesktopUnavailable` | Platform unsupported, Pillow missing, or backend assembly failed |
| `DesktopPermissionDenied` | macOS screen-recording or accessibility permission missing |
| `ScreenCaptureFailed` | GDI / `screencapture` failure, screenshot data cannot be decoded, or an invisible window yields no content |
| `DesktopBusy` | Another desktop action holds the input lock |
| `DesktopError` | Other system-call failure, with a WinError or the call name |

## Tests

`tests/test_visual_operator.py` covers coordinates, key names, configuration, capture processing (scaling, grid, blank frames, bad data), the action matrices and return values of the four tools, `hover` / `hover_path` / `hover_wiggle` / `shot` / `hit` / `changed` / `window_changed` / `navigated`, condition waits, same-title window disambiguation, Plan gating, the input lock, and the platform tables plus backend availability. On Windows it additionally checks that the virtual-key table covers every canonical key name and that UTF-16 surrogate pairs are split. Backends in tests are recording doubles; the tests do not move the real cursor or inject real keys.

## Further reading

- [plugins.md](plugins.md): plugin package form, extension points, and lifecycle
- [tools.md](tools.md): tool registration, execution pipeline, and image attachments
- [llm.md](llm.md): image blocks in multimodal requests
