**English** | [中文](visual-operator.zh.md)

# Visual Operator plugin

Visual Operator gives the agent observation and input on a desktop. Four coordinate tools form the baseline; window, app launch, and open tools are registered with the P1 interaction layer:

| Tool | Role | Capability |
|---|---|---|
| `desktop_eye` | observe | Capture the full screen, a region, or a window; overlay a coordinate grid; return the image to the model. `hover` can reveal hover-only controls before capture. |
| `desktop_mouse` | act | Move, click, drag, scroll, or query the cursor. A receipt can include `hit`, `changed`, and an optional `shot`. |
| `desktop_keyboard` | act | Type text, press one key, or press a key combination. An optional `shot` returns the resulting screen. |
| `desktop_wait` | wait | Wait for a screen region to change or for a window to appear or disappear, returning as soon as the condition holds. |
| `desktop_window` | window | List, activate, wait for, and read top-level windows; returns a stable hwnd. |
| `desktop_app` | launch | Launch a local program and wait for its main window; returns pid and hwnd. |
| `desktop_open` | open | Open a URL, scheme, or file with the system handler. |
| `desktop_find` | locate | Find controls by text through UIA; return rect and clickable point. |
| `desktop_click_text` | act | Locate a text control and click it. |
| `desktop_type_into` | act | Locate a text control, focus it, and type. |
| `desktop_click_region` | act | Click the center of a visual rectangle instead of estimating a center. |
| `desktop_type_into` | act | Locate a text control, focus it, and type. |
| `desktop_act` | batch | Multi-step execution, assertions, stop-on-failure, final/failure frames. |

`desktop_wait` is read-only and does not take the input lock. The window and open tools share the selected backend. The parameter-level contract is maintained in [visual-operator.md](../subsystems/visual-operator.md).

The plugin exposes tools instead of one multi-action tool. The mouse, keyboard, and eye capabilities have separate parameter surfaces: coordinates, key names, text, and capture options. A single action would have to describe when each parameter applies, which makes parameter mismatch more likely. A shared action matrix in `tools/_params.py` rejects parameters that belong to another action instead of silently ignoring them.

The plugin has a `[plugin:visual_operator]` section in `plugins.ini` and is enabled by default. Setting `enabled = 0` preserves the section and unregisters the tools; enabling it again loads the plugin without restarting the process. Registration is platform-independent: all tools are declared on every host, and platform capability is checked at execution. The generated `catalog/tools.json` includes all tools.

The plugin contributes no panel, endpoint, context injection, or startup script. Its visible surface is the tool declarations and tool cards.

## 1. Invariants

1. Tool registration does not depend on the platform. The four baseline tools and the L2/L3 tools are registered everywhere. A platform without a usable backend returns a structured error at execution, so the tool set is identical across hosts.
2. There is one coordinate space: screen coordinates, using physical pixels on Windows and display points on macOS. Capture rectangles, grid labels, mouse parameters, and cursor positions all use this space. Backend-specific scaling is confined to image processing and does not appear in the tool contract.
3. Screenshots are returned as `ToolResult.attach` attachments and are not saved as files. The macOS backend writes a temporary file for `screencapture`, then deletes it in a `finally` block. There is no on-disk path that the model must read with an image tool.
4. Image scaling does not change coordinate meaning. Grid labels use screen coordinates by default; the grid step is expressed in screen coordinates, not image pixels. `grid_unit=image` selects image pixels explicitly and requires `capture_id` for mouse input. The two spaces are never mixed silently.
5. Each capability has an independent switch. When `eye`, `mouse`, `keyboard`, or `wait` is `0`, that tool is not registered; it is not registered and then made to reject calls.
6. Plan mode blocks mouse and keyboard input and any cursor movement. Screenshot capture without `hover` remains available, although restoring a minimized target or requesting `activate=true` can still change window state. Cursor-only mouse queries and condition waits also remain available.
7. Mouse and keyboard actions are serialized by one process-wide lock, so actions from different sessions cannot interleave. A drag cannot be split by a click from another session. The lock timeout is 10 seconds, after which the call fails with `DesktopBusy`.
8. Input to a named target requires that target to be active. When `window` or `hwnd` is supplied to a mouse or keyboard action, the tool brings that window to the front and verifies that it actually reached the foreground. If activation fails, no input is delivered.
9. Failures state an executable next step: which permission to grant, which platforms are supported, or which action accepts the supplied parameters.
10. The plugin does not import `agent.app` or `agent.entry`. It depends only on `agent.capabilities`, `agent.mechanisms`, and `agent.core`.
11. Platform modules are imported only on their own platform. `backends/__init__.py` imports them lazily from `load_backend()` after checking `sys.platform`; a non-Windows host never executes `WinDLL`, and a non-macOS host never loads CoreGraphics.

## 2. Package layout

```text
plugins/visual_operator/
  plugin.py                    entry point: read config, select backend, register tools by switch
  plugin-config.ini            plugin configuration
  plugin-meta.json             plugin identity metadata
  config.py                    [config] parsing, defaults, and clamping
  capture_store.py             short-lived capture metadata registry
  coords.py                    screen points, rectangles, intersection, and geometry ratios
  keys.py                      canonical key names, aliases, and hotkey validation
  errors.py                    desktop error hierarchy
  canvas.py                    resize, coordinate grid, cursor overlay, PNG encoding
  diff.py                      region comparison between two captures
  ports.py                     backend protocols and data structures
  guard.py                     Plan-mode rejection
  input_lock.py                process-wide input lock
  backends/__init__.py         lazy platform selection and unavailable fallback
  backends/win32.py            Windows capture, activation, input, and hit probing
  backends/win32_common.py     Win32 types, constants, DPI, and display metrics
  backends/macos.py            macOS capture, permissions, and CoreGraphics input
  backends/_unavailable.py     explicit unsupported-platform backend
  tools/__init__.py            tool exports
  tools/_params.py             argument parsing and action-matrix validation
  tools/_windows.py            window lookup, candidate ordering, and activation
  tools/_capture.py            capture, rendering, receipts, and notes
  tools/eye.py                 DesktopEyeTool
  tools/mouse.py               DesktopMouseTool
  tools/keyboard.py            DesktopKeyboardTool
  tools/wait.py                DesktopWaitTool
```

Responsibilities:

| File | Does | Does not |
|---|---|---|
| `plugin.py` | Read configuration, select one backend, assemble tools | Branch on platform, validate arguments |
| `backends/*` | Call system APIs, convert points and pixels, probe permissions | Process images, assemble user-facing notes |
| `canvas.py` | Resize, draw the grid and cursor overlay, encode PNG | Call system APIs, define coordinate semantics |
| `tools/*` | Validate arguments, call ports, assemble receipts | Call system APIs, encode images |
| `capture_store.py` | Map `capture_id` to a rectangle and image dimensions | Store PNG bytes or session history |
| `ports.py` | Define protocols and data classes | Provide an implementation |

## 3. Tool contracts

### 3.1 `desktop_eye`

```python
name = "desktop_eye"
label = "View screen"
icon = "👁"
parallel_safe = False
description = (
    "Capture the desktop as an image for direct viewing; this is not OCR. "
    "Supports the full screen, a region, and a named window, with a coordinate grid "
    "whose labels use the same screen coordinates as desktop_mouse. "
    "hover moves the cursor before capture to reveal hover-only controls; "
    "annotate selects annotated, raw, or both images."
)
parameters = {
    "x": {"type": "integer", "description": "region left x (screen coordinates); give with y/width/height"},
    "y": {"type": "integer", "description": "region top y (screen coordinates)"},
    "width": {"type": "integer", "description": "region width (screen coordinates)"},
    "height": {"type": "integer", "description": "region height (screen coordinates)"},
    "window": {"type": "string", "description": "window title substring; capture the window's own content, unaffected by occlusion"},
    "hwnd": {"type": "integer", "description": "window handle; use instead of window; more precise"},
    "activate": {"type": "boolean", "description": "bring the window to the front before capture (default false: restore only)"},
    "hover": {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 2,
              "description": "move the cursor here [x, y] before capture to reveal hover-only controls"},
    "hover_path": {"type": "array", "items": {"type": "array", "items": {"type": "integer"},
                                              "minItems": 2, "maxItems": 2},
                   "description": "up to four intermediate points walked before hover"},
    "hover_settle_ms": {"type": "integer", "description": "wait after moving before capture, 0–5000; defaults to plugin config"},
    "hover_approach_ms": {"type": "integer", "description": "time to move to the target, 0–2000 (default 120); 0 = jump"},
    "hover_wiggle": {"type": "boolean", "description": "make a few 1–2 px moves near the target (default true)"},
    "grid": {"type": "boolean", "description": "overlay the coordinate grid and labels (default true)"},
    "grid_step": {"type": "integer", "description": "grid spacing in screen coordinates, 20–500; defaults to plugin config"},
    "grid_unit": {"type": "string", "enum": ["screen", "image"],
                  "description": "grid label unit: screen coordinates (default) or image pixels"},
    "max_side": {"type": "integer", "description": "longest image side, 0–8192; 0 = no resize; defaults to plugin config"},
    "annotate": {"type": "string", "enum": ["annotated", "raw", "both"],
                 "description": "annotated only (default) / raw only / annotated then raw"},
}
```

`desktop_eye` returns PNG attachments plus a JSON receipt. Without `window` or `hwnd`, it captures the screen composite, which can include occluding windows. With either parameter, it targets the window's own content, so occlusion does not normally affect the result; if the window does not paint, the call can fall back to a screen capture. `window` matches a title substring; `hwnd` selects an exact window. The two parameters are mutually exclusive.

A minimized window is restored before capture. With the default `activate=false` it is restored without changing the foreground window; with `activate=true` it is restored and brought to the front. `restored` records that restoration happened. `activated` appears only when `activate=true` and records whether the window actually reached the foreground. A failed activation is reported but does not discard a window capture that succeeded.

If the window's own content remains uniform after the repaint wait, the backend falls back to a screen capture, sets `source` to `screen`, and adds a note that occluding content may appear. The receipt never presents a screen fallback as window content.

`hover` moves the real cursor, waits for the interface to settle, and then captures, all within one call. Splitting the move and the capture into separate tool calls usually fails: hover-only controls often collapse within two to three seconds, which is shorter than a model round trip. When `window` or `hwnd` is supplied, the cursor move happens after the window is restored or activated and before the capture, so the revealed control belongs to the target window. When neither is supplied and the backend has window and hit ports, the auto target is the top-level window under the cursor; a window capture avoids screen occlusion, though `max_side` still applies. Without a window port, the call remains a screen capture. The receipt marks an auto target with `window.auto = "hover.hit"`.

The cursor path is not a single jump. Intermediate `hover_path` points are visited first, then the cursor moves to `hover` over `hover_approach_ms`, and finally makes a few 1–2 px moves when `hover_wiggle` is enabled. These are real cursor movements because auto-hiding controls react to consecutive mouse-move events; a single jump followed by no movement is ignored by many interfaces. After the wiggle, the cursor is read back and returned to the target. If the target window moves the cursor and it cannot be returned, the call fails rather than treating the displaced position as the target.

The grid is drawn after resizing, so labels are rendered at their final size. Grid labels use screen coordinates by default, even when the image was scaled or the capture has a negative origin. `grid_unit=image` switches labels to image pixels and is intended to be paired with `capture_id`. The cursor overlay is controlled by `cursor_mark` in the plugin configuration; it is independent of the `grid` switch.

Returned fields:

```json
{
  "platform": "win32",
  "screen": {"x": -1920, "y": 0, "width": 3840, "height": 1080},
  "capture": {"x": -1920, "y": 0, "width": 3840, "height": 1080},
  "source": "window",
  "annotate": "annotated",
  "image": {"width": 3840, "height": 1080, "sent_width": 1920, "sent_height": 540,
            "scale": 2.0, "bytes": 548735},
  "image_to_screen": {"scale_x": 2.0, "scale_y": 2.0, "ox": -1920, "oy": 0},
  "capture_id": "a1b2c3d4e5f6",
  "dpi": "96 dpi",
  "cursor": {"x": 412, "y": 300},
  "grid": {"step": 50, "unit": "screen", "scale": 2.0},
  "window": {"hwnd": 123456, "title": "Example window",
             "rect": {"x": -1920, "y": 0, "width": 3840, "height": 1080},
             "minimized": false, "visible": true, "foreground": true},
  "restored": true,
  "note": "The window was minimized; it was restored without activation before capture."
}
```

`window`, `restored`, and `activated` appear only when a window is targeted. `window.matched` and `window.alternatives` appear when a title matches more than one visible window. `hover.hit` identifies the window under the hover point. `capture_id` is an in-memory reference, not a file path; it expires after 300 seconds or when the per-plugin cache reaches 64 entries, and it is scoped to the current session. `note` is emitted only for actionable conditions: resizing, restoration or activation, screen fallback, a blank image, inconsistent multi-monitor scaling, duplicate title matches, a hover layer that differs from the captured window, or an automatically selected hover target.

Validation:

- `x`, `y`, `width`, and `height` are supplied together or omitted together. Width and height must be positive. A region outside the screen is clipped; a region with no intersection fails with the screen rectangle.
- `window` and `hwnd` are mutually exclusive. `hwnd` must be a positive integer. `window` must be a non-empty substring.
- `activate` is valid only with `window` or `hwnd`. Supplying it for a full-screen capture fails.
- A capture over 40 million pixels fails with a request for a smaller region. The check stops the call before rendering.
- `hover_path` requires `hover`, may contain one to four points, and every point must be inside the virtual screen. `hover` must also be inside the screen.
- `grid_step` is 20–500. `max_side` is 0–8192. `hover_settle_ms` is 0–5000. `hover_approach_ms` is 0–2000. Unknown arguments are rejected.

#### Window capture and activation

| Window state | `activate=false` (default) | `activate=true` |
|---|---|---|
| Visible, including occluded | No window-state change; capture the window's own content | Bring to front, then capture |
| Minimized | Restore with `SW_SHOWNOACTIVATE`, then capture; the foreground window is unchanged | Restore and bring to front; equivalent to clicking the taskbar |

Restoration is mandatory: a minimized window has an off-screen rectangle and produces no useful window content. The backend restores it, waits for a real repaint, and retries the capture for up to 1.2 seconds. If the frame is still uniform, it falls back to a screen capture. An explicit activation that fails is reported with `activated=false`; the capture is still returned if the window content is available, and a note tells the caller that the window is not in the foreground.

### 3.2 `desktop_mouse`

```python
name = "desktop_mouse"
label = "Mouse"
icon = "🖱"
description = (
    "Operate the mouse: move, click, drag, scroll, or query the cursor. "
    "Coordinates are screen coordinates by default; a capture_id switches to image "
    "pixel coordinates and the tool performs the conversion. "
    "With window or hwnd, restore and activate the target before acting; "
    "if activation fails, no input is delivered."
)
parameters = {
    "action": {"type": "string", "enum": ["move", "click", "drag", "scroll", "cursor"]},
    "x": {"type": "integer", "description": "x; screen coordinates by default, image pixels with capture_id"},
    "y": {"type": "integer", "description": "y; screen coordinates by default, image pixels with capture_id"},
    "to_x": {"type": "integer", "description": "drag end x; same coordinate space as x"},
    "to_y": {"type": "integer", "description": "drag end y; same coordinate space as y"},
    "space": {"type": "string", "enum": ["screen", "image"],
              "description": "coordinate space: screen (default) or image; image requires capture_id"},
    "capture_id": {"type": "string", "description": "capture_id from a desktop_eye receipt"},
    "button": {"type": "string", "enum": ["left", "right", "middle"], "description": "button (default left)"},
    "count": {"type": "integer", "description": "click count 1–3 (default 1)"},
    "amount": {"type": "integer", "description": "scroll amount -50 to 50; positive is down or right"},
    "horizontal": {"type": "boolean", "description": "horizontal scroll (default false)"},
    "duration_ms": {"type": "integer", "description": "move or drag duration 0–5000; 0 = jump"},
    "window": {"type": "string", "description": "target window title substring; activate before acting"},
    "hwnd": {"type": "integer", "description": "target window handle; use instead of window"},
    "shot": {"type": "boolean", "description": "capture the result in the same call (default false)"},
    "shot_region": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4,
                    "description": "capture region [x, y, width, height] in screen coordinates"},
    "shot_max_side": {"type": "integer", "description": "longest side of the shot; defaults to plugin config"},
}
```

Action matrix:

| `action` | Required | Action-specific optional | Rejected |
|---|---|---|---|
| `move` | `x`, `y` | `duration_ms` | `to_x`, `to_y`, `amount`, `button`, `count`, `horizontal` |
| `click` | none; omitted `x`, `y` use the current cursor | `x`, `y`, `button`, `count` | `to_x`, `to_y`, `amount`, `horizontal`, `duration_ms` |
| `drag` | `x`, `y`, `to_x`, `to_y` | `button`, `duration_ms` | `amount`, `count`, `horizontal` |
| `scroll` | `amount` | `x`, `y`, `horizontal` | `to_x`, `to_y`, `button`, `count`, `duration_ms` |
| `cursor` | none | none | all other action parameters, plus `space`, `capture_id`, and the `shot` group |

`window` and `hwnd` are accepted by every action; `cursor` does not activate because it performs no input. Non-cursor actions also accept `space`, `capture_id`, `shot`, `shot_region`, and `shot_max_side`. A rejected parameter raises `ValueError`, names the parameter, and names the action that accepts it.

Coordinates:

- Screen coordinates are the default. Supplying `capture_id` switches to the image coordinates of that capture; `space=image` states the same explicitly. Supplying `capture_id` with `space=screen` is an error. An unknown, expired, or cross-session `capture_id` fails instead of falling back to screen coordinates.
- Image coordinates must be given as a point and must lie inside the image. The tool converts them with `screen_x = capture.x + image_x * capture.width / image.width` and the corresponding y formula.
- `click` and `scroll` may omit `x` and `y`; they then act at the current cursor position. `move` and `drag` require their points. Image coordinates are never inferred from the current cursor.
- `amount` is nonzero and lies in -50 to 50. Positive values scroll down or right; `horizontal` selects the horizontal axis.
- `duration_ms` is 0–5000. Its default is 0 for `move` (a jump) and 300 for `drag`.

Returns:

```json
{"action": "click", "space": "screen", "cursor": {"x": 300, "y": 400},
 "screen": {"x": 0, "y": 0, "width": 2560, "height": 1440},
 "hit": {"hwnd": 123456, "class": "ExampleClass", "title": "Example window"},
 "changed": 0.34, "changed_scope": "point_200",
 "window_changed": {"changed": true, "navigated": true}}
```

```json
{"action": "drag", "space": "screen", "cursor": {"x": 300, "y": 400},
 "screen": {"x": 0, "y": 0, "width": 2560, "height": 1440}}
```

```json
{"action": "scroll", "space": "screen", "cursor": {"x": 800, "y": 500},
 "screen": {"x": 0, "y": 0, "width": 2560, "height": 1440}}
```

```json
{"action": "cursor", "cursor": {"x": 412, "y": 300},
 "screen": {"x": 0, "y": 0, "width": 2560, "height": 1440}}
```

`click`, `drag`, and `scroll` additionally report evidence when the backend supports it:

- `hit` gives the window handle and class under the landing point, plus the title of the top-level window. It is omitted when hit probing is unavailable.
- `changed` is the fraction of changed pixels in a 200×200 region around the point, from 0 to 1. `changed_scope` is `point_200`. A value of 0 means only that the local region did not change; it does not prove the click missed. If the first sample is below 0.005, the tool waits 250 ms and samples once more; `changed` becomes the larger value and `changed_late` and `changed_note` describe the second sample.
- `window_changed` compares the top-level window before and after the action. `opened` and `closed` list up to three windows, with counts in `opened_more` and `closed_more`. `changed` is true when a window was opened or closed, or when the hit window changed. `navigated` is true when the local region did not change but the window layer did, which is the expected receipt for a click that opens a detail page or a new window.

`shot=true` captures the screen in the same call. The default shot target is the top-level window under the landing point (`shot_of: "hit"`), not a window resolved again from the title. An explicit `window` or `hwnd` overrides this (`shot_of: "window"` or `"hwnd"`); if neither a hit nor a focus target exists, the shot is the full screen. The shot receipt uses the same overlay as `desktop_eye`, and the action receipt is nested under `performed`. When the default shot follows the landing window and that window differs from the activated window, `note` names both handles. `shot` is available for `move`, `click`, `drag`, and `scroll`; `cursor` is read-only and rejects it.

A drag always sends the button release in a `finally` block. If movement raises, the release still runs, so a failed drag does not leave the button down.

### 3.3 `desktop_keyboard`

```python
name = "desktop_keyboard"
label = "Keyboard"
icon = "⌨"
description = (
    "Operate the keyboard: type Unicode text, press one key, or press a key combination. "
    "With window or hwnd, restore and activate the target before typing; "
    "if activation fails, no input is delivered."
)
parameters = {
    "action": {"type": "string", "enum": ["type", "key", "hotkey"]},
    "text": {"type": "string", "description": "text for action=type"},
    "key": {"type": "string", "description": "key name for action=key, such as enter / esc / f5 / a"},
    "keys": {"type": "string", "description": "key combination for action=hotkey, such as \"ctrl+c\" or \"alt+tab\""},
    "repeat": {"type": "integer", "description": "repeat count for key or hotkey, 1–20 (default 1)"},
    "window": {"type": "string", "description": "target window title substring; activate before typing"},
    "hwnd": {"type": "integer", "description": "target window handle; use instead of window"},
    "shot": {"type": "boolean", "description": "capture the result in the same call (default false)"},
    "shot_max_side": {"type": "integer", "description": "longest side of the shot; defaults to plugin config"},
}
```

`type` sends text as Unicode units and does not depend on the active keyboard layout. A line feed or carriage return is sent as Enter; a tab is sent as Tab. `key` presses one canonical key. `hotkey` presses two to four keys, with modifiers in the order given and released in reverse order.

Returns:

```json
{"action": "type", "chars": 12}
{"action": "key", "key": "enter", "repeat": 1}
{"action": "hotkey", "keys": ["ctrl", "c"], "repeat": 1}
```

`window` and `hwnd` add a `focus` receipt. A failed activation aborts the call before any key is sent. With `shot=true`, the receipt is a capture payload and the keyboard result is nested under `performed`; the capture target follows explicit `window`/`hwnd` and otherwise uses the full screen.

Key names:

- Canonical names: `enter`, `tab`, `esc`, `space`, `backspace`, `delete`, `insert`, `home`, `end`, `pageup`, `pagedown`, `left`, `up`, `right`, `down`, `capslock`, `f1` through `f20`, `ctrl`, `shift`, `alt`, `win`, `cmd`, and single ASCII letters, digits, and the punctuation keys `-`, `=`, `[`, `]`, `;`, `'`, `,`, `.`, `/`, `\`, and `` ` ``.
- Aliases: `return` → `enter`, `escape` → `esc`, `control` → `ctrl`, `option` → `alt`, `command` / `meta` / `super` → `cmd`, `windows` → `win`, `page_up` / `pgup` → `pageup`, `page_down` / `pgdn` → `pagedown`, plus the common named punctuation aliases.
- An unknown key fails with `ValueError` and a short list of accepted names. It never falls back to pressing the first character.
- `keys` is declared as a string. It is split on `+` or `,`, so `"ctrl+c"` and `"ctrl,c"` are equivalent. An array is also accepted by the parser, but the schema presents the string form.
- A combination must contain 2–4 keys and at least one non-modifier. An all-modifier combination fails.

Integer arguments accept numeric strings such as `"300"` but reject booleans and floating-point values. A fractional value fails with `ValueError`; it is never silently truncated.

### 3.4 `desktop_wait`

| Parameter | Meaning |
|---|---|
| `until` | `change`: wait for a region to change. `window_appears`: wait for a window to appear. `window_disappears`: wait for a window to disappear. |
| `window` | Window title substring. For `change`, restricts the compared region. For `window_appears` and `window_disappears`, required. |
| `hwnd` | Window handle. Valid for `change` as an alternative to `window`; the wait for a window appearance or disappearance is title-based. |
| `x`, `y`, `width`, `height` | Region for `change`; supplied together or omitted together. Defaults to the window rectangle or the full screen. |
| `timeout_ms` | Maximum wait, 50–60000; default 3000. |
| `interval_ms` | Poll interval, 50–2000; defaults to plugin configuration. |
| `threshold` | Change threshold from 0 to 1 for `change`; default 0.02. Smaller values are more sensitive. |

`until=change` captures a baseline and compares later captures of the same region. It uses the screen composite and does not activate a window. A minimized window cannot be compared and fails immediately instead of waiting on an off-screen rectangle. `until=window_appears` and `window_disappears` search visible top-level windows by title. A platform without a window port fails with `DesktopUnavailable`.

A timeout is not an error. The tool returns `satisfied: false` with the last measured value; the caller decides whether to change the action or wait longer. If the condition is already true on the first probe, `already` is set and the note explains that no waiting occurred.

`desktop_wait` is read-only. It does not take the input lock, does not move the cursor, and remains available in Plan mode.

Example receipts:

```json
{"until": "change", "satisfied": true, "waited_ms": 420,
 "changed": 0.18, "threshold": 0.02,
 "capture": {"x": 100, "y": 100, "width": 800, "height": 600}}
```

```json
{"until": "window_appears", "satisfied": false, "waited_ms": 3000,
 "note": "The window with the requested title did not appear before the timeout."}
```

## 4. Configuration

`plugins/visual_operator/plugin-config.ini`:

```ini
[config]
eye = 1
mouse = 1
keyboard = 1
wait = 1
max_side = 1920
grid_step = 50
cursor_mark = 1
settle_ms = 60
type_interval_ms = 12
hover_settle_ms = 250
hover_approach_ms = 120
hover_wiggle = 1
wait_interval_ms = 200
```

| Key | Default | Range | Effect |
|---|---|---|---|
| `eye` | 1 | 0/1 | Register `desktop_eye` |
| `mouse` | 1 | 0/1 | Register `desktop_mouse` |
| `keyboard` | 1 | 0/1 | Register `desktop_keyboard` |
| `wait` | 1 | 0/1 | Register `desktop_wait` |
| `max_side` | 1920 | 0–8192 | Longest side of a sent capture; 0 = no resize |
| `grid_step` | 50 | 20–500 | Grid spacing in screen coordinates |
| `cursor_mark` | 1 | 0/1 | Draw the cursor crosshair and coordinate label |
| `settle_ms` | 60 | 0–2000 | Pause after a mouse or keyboard action |
| `type_interval_ms` | 12 | 0–200 | Delay between typed characters |
| `hover_settle_ms` | 250 | 0–2000 | Wait after a hover move for the interface to settle |
| `hover_approach_ms` | 120 | 0–2000 | Duration of the hover move; 0 = one jump |
| `hover_wiggle` | 1 | 0/1 | Perform 1–2 px moves near the hover target |
| `wait_interval_ms` | 200 | 50–2000 | Default poll interval for `desktop_wait` |

Per-call arguments override the corresponding configuration. `grid_step`, `max_side`, `hover_settle_ms`, `hover_approach_ms`, and `hover_wiggle` are the main capture overrides; the input tools use their configured timing values, and `desktop_wait` uses its `interval_ms` argument, defaulting to the configured value.

Parsing rules in `config.py`:

- A missing file or a missing `[config]` section yields defaults.
- An integer key with a non-integer value falls back to its default. An out-of-range value is clamped to the nearest boundary.
- A switch accepts `1` / `0`, `true` / `false`, `yes` / `no`, and `on` / `off`, case-insensitively. Any other value falls back to the default.
- Unknown keys are ignored. Comments and other sections in the file do not prevent loading.
- Parsing and fallback do not write logs, and a configuration error does not prevent the plugin from loading. Effective values can be read back from the `grid` and `image` fields of a `desktop_eye` receipt.

## 5. Coordinates, images, and scaling

### 5.1 Coordinate space

- The origin of screen coordinates is the top-left corner of the virtual desktop. With multiple monitors, either coordinate may be negative. Windows uses physical pixels; macOS uses global display points.
- `screen` is the virtual-desktop rectangle. `capture` is the rectangle actually captured. A screen region is clipped to the virtual desktop before capture, and a window region is clipped again to the window.
- Grid labels use screen coordinates by default and are computed as `screen.x + offset`, not as image pixels.
- Mouse parameters use the same screen space, and each backend delivers them in that space. When image coordinates are selected, `capture_id` provides the mapping to screen coordinates.

### 5.2 Processing order

```text
screen or window capture
  -> window restore/activation, then optional hover move
  -> crop to the requested region
  -> blank-frame detection
  -> resize so the longest side is at most max_side (LANCZOS)
  -> grid and cursor overlay on the final canvas
  -> PNG encoding
  -> ToolResult.attach
```

Blank detection adds a note instead of rejecting the capture; the receipt has no separate blank field. A window capture can fall back to the screen before processing, in which case `source` reflects the fallback.

The overlay is applied after resizing. Labels are therefore rendered at their final size and do not become blurred through a second scaling pass. The mapping from screen coordinates to overlay pixels is:

```text
image_x = (screen_x - capture.x) * sent_width / capture.width
image_y = (screen_y - capture.y) * sent_height / capture.height
```

The inverse mapping is reported as `image_to_screen.scale_x`, `scale_y`, `ox`, and `oy`. It is available for diagnostics and for interface display; a caller using screen coordinates or grid labels does not need to apply it.

### 5.3 Grid and cursor overlay

- Minor grid lines are drawn every `grid_step` screen units. Every fifth line is major and carries a label. Vertical lines are labeled at the top and bottom edges; horizontal lines are labeled at the left and right edges. Labels are clamped inside the image.
- When the gap between minor lines is less than 8 image pixels, minor lines are omitted and only major lines remain. This avoids turning a dense grid into a solid tint.
- Minor lines are blue and 1–2 pixels wide; major lines are red and 2–3 pixels wide. Grid labels use an embedded font with a dark stroke, at 8–18 pixels depending on image width.
- The cursor overlay is drawn only when `cursor_mark` is enabled and the cursor lies inside the captured rectangle. It is independent of `grid`.
- The overlay consists of a short bright-green crosshair with a black halo and a white separator, a small ring, and a `CURSOR` badge containing the coordinates. The center of the crosshair is left open so the pixel under the cursor remains visible.
- When the shorter side is below 90 pixels, no cursor label is drawn; the coordinates remain in the `cursor` receipt. When it is below 140 pixels, the compact label omits the `CURSOR` title and the dark background.
- With `grid_unit=image`, both grid labels and the cursor label use image pixels. `desktop_mouse`, `desktop_click_region`, or `desktop_type_into` then need `capture_id` and `space=image`; screen and image coordinates must not be combined in one action.

### 5.4 Size and history

- A capture over 40 million pixels is rejected with a request for a smaller region. The check runs before rendering; a screen capture is rejected before its bitmap is allocated, while a window capture may already have been taken when the limit is checked.
- Returned screenshots are image attachments in the tool result and can be replayed from conversation history. The `[context]` configuration limits that replay: `image_turns` controls how many recent image-bearing user rounds are included, and `image_max` caps the total number of images in a request, including tool attachments. Both are independent of the capture size limit.
- `max_side` changes only the sent image. It does not change the coordinate contract: grid labels remain screen coordinates unless `grid_unit=image` is requested. `image.scale` is the original width divided by the sent width; the receipt describes a resize with a one-step conversion example.

## 6. Platform backends

### 6.1 Common contract

```python
class ScreenPort(Protocol):
    def geometry(self) -> ScreenGeometry: ...
    def capture(self, region: ScreenRect | None) -> Screenshot: ...

class MousePort(Protocol):
    def cursor(self) -> ScreenPoint: ...
    def move(self, point: ScreenPoint, duration_ms: int) -> None: ...
    def click(self, point: ScreenPoint | None, button: str, count: int) -> None: ...
    def drag(self, start: ScreenPoint, end: ScreenPoint, button: str, duration_ms: int) -> None: ...
    def scroll(self, point: ScreenPoint | None, amount: int, horizontal: bool) -> None: ...

class KeyboardPort(Protocol):
    def type_text(self, text: str, interval_ms: int) -> None: ...
    def press(self, key: str, repeat: int) -> None: ...
    def hotkey(self, keys: Sequence[str], repeat: int) -> None: ...
```

`Screenshot` carries `png`, `rect`, `source`, `restored`, `foreground`, and `activation`. `Backend` is a frozen data class with `platform`, `screen`, `mouse`, and `keyboard`, plus optional `windows` and `hit` ports. `windows` supplies window lookup, activation, and window capture. `hit` supplies landing-point probing. When either is absent, the corresponding receipt fields are omitted or the operation fails with `DesktopUnavailable`.

`load_backend()` selects a platform module lazily:

```python
if sys.platform == "win32":
    from .win32 import Win32Backend
    return Win32Backend()
if sys.platform == "darwin":
    from .macos import MacOSBackend
    return MacOSBackend()
return unavailable_backend()
```

Backend assembly failure is caught, reported once to stderr, and replaced by the unavailable backend. Its ports raise `DesktopUnavailable` on every method with the current platform and the supported platforms in the message. The tools remain registered, so a missing system library changes the execution result, not the tool list.

### 6.2 Windows

| Capability | Implementation |
|---|---|
| DPI awareness | `SetProcessDpiAwarenessContext(-4)`, then `shcore.SetProcessDpiAwareness(2)`, then `SetProcessDPIAware()`; if the host already declared awareness, its choice is kept |
| Virtual screen | `SM_XVIRTUALSCREEN`, `SM_YVIRTUALSCREEN`, `SM_CXVIRTUALSCREEN`, `SM_CYVIRTUALSCREEN` |
| Screen capture | `GetDC(NULL)` → compatible DC and bitmap → `BitBlt` with `SRCCOPY` and `CAPTUREBLT` → `GetDIBits` with 32-bit `BI_RGB` and negative height for top-down rows → Pillow `BGRX` |
| Window capture | `GetWindowDC` → `PrintWindow(PW_RENDERFULLCONTENT)` → `GetDIBits`; wait up to 1.2 s for a non-uniform frame; fall back to a screen capture when the window frame remains uniform |
| Restore | `ShowWindow(SW_SHOWNOACTIVATE)` for capture; `SW_RESTORE` when the window must also be activated |
| Activation | `SwitchToThisWindow` first, `SetForegroundWindow` as fallback; success is decided by `GetForegroundWindow` plus `IsIconic`, not by the API return value |
| Cursor | `GetCursorPos` |
| Move | `SetCursorPos`; with `duration_ms > 0`, interpolate over at most 120 steps across `duration_ms` |
| Click | `SendInput` down and up; 20 ms between repeated clicks |
| Drag | Set the start point, press, interpolate to the end point, release in `finally` |
| Scroll | `MOUSEEVENTF_WHEEL` or `MOUSEEVENTF_HWHEEL`; vertical values are negated before multiplying by 120 |
| Keyboard | `SendInput` with `KEYEVENTF_UNICODE`; function and named keys use virtual-key codes; hotkeys press in order and release in reverse |
| Hit probing | `WindowFromPoint`, `GetAncestor(GA_ROOT)`, and `GetClassNameW`; absent results omit `hit` instead of inventing an answer |
| Window list | `EnumWindows` over visible top-level windows; order is foreground → Z order → area, excluding tool windows and off-screen helper windows |

`SetCursorPos` is used instead of normalized `MOUSEEVENTF_ABSOLUTE` input because the latter covers only the primary monitor without `VIRTUALDESK`, and its normalization can introduce error under mixed DPI. `SetCursorPos` accepts virtual-desktop pixel coordinates directly.

Known boundaries: a higher-integrity window (for example, an elevated process) silently discards `SendInput` from a normal-integrity process. The lock screen and the secure desktop produce black captures. Mixed-DPI monitor layouts can still show small coordinate offsets.

### 6.3 macOS

| Capability | Implementation |
|---|---|
| Screen-recording permission | `CGPreflightScreenCaptureAccess()`; a missing symbol is treated as not applicable |
| Accessibility permission | `AXIsProcessTrusted()` |
| Capture | `/usr/sbin/screencapture -x -t png -R x,y,w,h <temporary file>`; read the file, then delete it in `finally` |
| Geometry | `CGGetActiveDisplayList` + `CGDisplayBounds` (points) + `CGDisplayPixelsWide` / `CGDisplayPixelsHigh` (pixels) |
| Cursor | `CGEventCreate(nil)` + `CGEventGetLocation` + `CFRelease` |
| Move, click, drag | `CGEventCreateMouseEvent` + `CGEventPost(kCGHIDEventTap)`; repeated clicks increment `kCGMouseEventClickState` |
| Scroll | `CGEventCreateScrollWheelEvent` in line units; positive scrolls down or right |
| Keyboard | `CGEventCreateKeyboardEvent`; text uses `CGEventKeyboardSetUnicodeString`; hotkeys use `CGEventSetFlags` for the command, shift, option, and control masks |

The screenshot contains physical pixels while event coordinates are display points. The tool contract stays in points. `geometry()` reports `pixel_ratio = pixel width / point width`; multiple monitors with different ratios set `mixed_scale=true` and add a note. `screencapture -R` accepts points, and the output size is points multiplied by the display ratio. The overlay maps from the capture rectangle to the sent image size, so its labels and cursor position do not depend on the display ratio.

The macOS backend provides screen capture, mouse, and keyboard ports only. It has no window port and no hit port. `window`, `hwnd`, window-scoped `desktop_wait` conditions, and window activation therefore fail with `DesktopUnavailable`. Input goes to the current foreground application; the caller must bring the target application forward by other means.

The screen-recording and accessibility checks return `DesktopPermissionDenied` with the relevant System Settings pane. A missing screen-recording grant blocks capture; a missing accessibility grant blocks input events.

## 7. Safety and gating

| Mechanism | Location | Behavior |
|---|---|---|
| Plan mode | `guard.py`, called from each tool's execution path | Reject input and cursor-moving actions with `ModeConflict`. `desktop_mouse action=cursor` returns before the check because it is read-only; `desktop_eye activate=true` is not intercepted by this gate. |
| Capability switches | `plugin.py` | Each tool is registered only when its `[config]` switch is on; turning it off unregisters the tool. |
| Input serialization | `input_lock.py` | Mouse and keyboard actions share one `threading.Lock`. A 10-second timeout raises `DesktopBusy`. |
| Target assertion | `tools/_windows.py` | A window-targeted mouse or keyboard action activates the window and verifies the foreground before sending input. Failure aborts the action with no input delivered. |
| Default enable | `plugins.ini` | The plugin has a manifest section. Setting `enabled=0` preserves the section and removes the tools. |
| Capture | no additional gate | Capture without `hover` is allowed in Plan mode. A minimized target is restored, and `activate=true` can still bring a window forward. |

Plan mode by operation:

| Operation | Plan mode |
|---|---|
| `desktop_eye` without `hover` and without `activate=true` | Allowed; a minimized target may still be restored |
| `desktop_eye` with `activate=true` and without `hover` | Allowed, but target activation is not gated |
| `desktop_eye` with `hover` | Rejected: the call moves the real cursor |
| `desktop_mouse action=cursor` | Allowed |
| Other `desktop_mouse` actions | Rejected |
| All `desktop_keyboard` actions | Rejected |
| `desktop_wait` | Allowed: read-only, no cursor movement, no input |

The Plan check happens before any input event. For mouse actions, it also happens before window activation; a target window is not brought forward merely to discover that the input is forbidden. Without `window` or `hwnd`, mouse and keyboard input goes to the current foreground and no target assertion is possible. When the host cannot provide session live state, the plugin has no mode to consult and does not block; normal assembly supplies the state at execution time.

No shortcut blacklist is applied. The keyboard can already synthesize arbitrary commands, including opening a system surface and then typing into it. A blacklist would not stop that path and would create a false sense of safety. The real boundaries are whether the plugin is enabled, whether the session is in Plan mode, and whether an operator is present.

After enablement, any content that can influence model input — a web page, a file, a tool result — can become a real click or keystroke. This is the same risk class as command execution; the entry point differs. Enabling the plugin is a grant of desktop control, not a content-level trust decision.

Screenshots may contain credentials, personal data, or other sensitive material and are sent to the model as attachments. The plugin does not redact them. The controls are the per-capability switches, the `[context]` image replay limits, and the Plan-mode restriction on cursor movement; Plan mode does not block capture itself.

## 8. Errors

| Exception | Trigger | Message requirement |
|---|---|---|
| `DesktopUnavailable` | Unsupported platform, missing image dependency, or backend assembly failure | State the missing dependency, the current platform, or the supported platforms, as applicable |
| `DesktopPermissionDenied` | macOS screen-recording or accessibility permission is missing | Name the exact System Settings pane and the program that needs the grant |
| `ScreenCaptureFailed` | `BitBlt`, `PrintWindow`, `screencapture`, or image decoding fails | Include the system error or process exit status; never substitute an empty image |
| `DesktopBusy` | The input lock is held for 10 seconds | State that another desktop input action has not finished |
| `ModeConflict` | Mouse or keyboard input in Plan mode | Use the same wording as the built-in command gate |
| `ValueError` | Missing, out-of-range, or mismatched parameters; coordinates outside the screen or image; invalid or expired `capture_id` | Name the parameter and the valid values or action |
| `DesktopError` | Another system call fails, no active display is available, or a required window cannot be activated | Include the failing operation and enough context to retry or change approach |

The tool pipeline converts these exceptions into a structured `ok=false` result; one failed step does not terminate the turn. Error text never includes a Python traceback or an internal repository path.

## 9. Verification

| Area | Required behavior |
|---|---|
| Registration | All tools register with all switches on; a single switch registers only its tool; all switches off register none; an unavailable backend still registers all tools. |
| Capture | Attachments contain the expected number of PNG files; region clipping, window selection, fallback, and oversized-region rejection are covered; `annotate` ordering is correct. |
| Coordinates and grid | Image coordinates map with negative origins and scaling; grid and cursor pixels land on the expected positions; labels respect the size thresholds; blank detection works. |
| Mouse and keyboard | The action matrix rejects foreign parameters; drag order is press → move → release; scroll amount and direction agree with the contract; key names, aliases, hotkey shape, and text encoding are covered. |
| Wait and safety | Change and window conditions return on satisfaction; timeouts return `satisfied=false`; Plan mode blocks input and hover, while cursor queries, capture, and wait remain available and capture activation is not gated; the input lock serializes concurrent actions and times out. |
| Backends | Platform call sequences and permission failures are exercised through a fake FFI layer on non-native hosts; real desktop behavior must be exercised on each supported platform. |

The test surface must not move the real cursor or inject real keys on a non-desktop host. Backends are substituted through the ports, and the tests operate on synthetic images and fake window records.

## 10. Known limitations

| Limitation | Impact | Handling |
|---|---|---|
| macOS has no window or hit port | Window capture, window-scoped waits, and window activation are unavailable; input goes to the current foreground application | Report `DesktopUnavailable`; use full-screen or region capture and switch applications by other means |
| Mixed-DPI layouts | A secondary monitor with a different scale can show a small coordinate offset | Return `dpi` and `mixed_scale`; add a note |
| Higher-integrity windows | Input is discarded silently by the system | Documented boundary; an elevated service may be required |
| Secure desktop or lock screen | Captures are black | Blank detection adds a note; the frame is still returned |
| Keyboard layout and scan codes | Unicode injection is ineffective in some games and custom-drawn controls that read scan codes | Documented boundary; the affected application needs another input path |
| Screenshot accumulation | Replaying full-screen images inflates requests | `[context]` `image_turns` and `image_max` cap the replay |
| Plan-mode window activation | `desktop_eye` with `activate=true` can bring a window forward in Plan mode because the gate covers cursor movement and input, not capture activation | Avoid this combination when the foreground must not change; use capture without activation, or leave Plan mode for deliberate activation |
| Prompt injection | Observed content can induce clicks and keystrokes | Plan mode, per-capability switches, plugin disablement, and operator review |
| Process-local input lock | It does not coordinate with other processes or a human using the same keyboard and mouse | Treat desktop control as exclusive while a session is acting |
| Hover outside the input lock | `desktop_eye hover` moves the cursor without taking the input lock, so it can interleave with another session's drag or mouse action | Do not mix hover capture with concurrent input; serialize at the session level |
| Window content fallback | A screen capture can include occluding windows when the target does not repaint | `source=screen` and the note distinguish it from window content |

## 11. Out of scope

| Capability | Reason |
|---|---|
| OCR or text recognition | The model can read the screenshot directly. OCR adds latency and can hide framing or scaling defects behind a recognition error. |
| Clipboard read or write | Reading the clipboard can place credentials the user copied for another purpose into the model context. |
| Pointer acceleration settings | This changes a user preference in the operating system, not a single desktop action. |
| Circular pointer gestures | Useful for demonstrations, not for model-driven tasks. |
| Port-level rate limiting | A conversation turn is already bounded. Plan mode and the capability switches provide the primary control. |
