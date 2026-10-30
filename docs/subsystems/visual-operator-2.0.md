**English** | [中文](visual-operator-2.0.zh.md)

# Visual Operator 2.0 (`visual_operator_2` plugin)

Visual Operator 2.0 gives the model continuous visual context and authorized desktop input. It is a separate plugin from the legacy `visual_operator` plugin; the legacy plugin remains disabled. The kernel injects a current frame into the model context, while tools perform explicit focus, pointer, click, and keyboard actions.

## Responsibility boundary

```text
kernel: screenshot cadence, frame injection, tool registry, context assembly
plugin: authorization state, frames, focus, pointer/keyboard actions, SSE events
```

The plugin does not use UIA, OCR, window control trees, or shell commands to drive the target application. Those capabilities belong to the optional desktop tools described below.

## Authorization lifecycle

```text
vision_request_open -> user confirms -> vision_start -> visual tools
                                             |
                                             +-> vision_stop (close eyes)
```

- `vision_request_open` creates a consent request. The UI prompts the user.
- `vision_start` consumes the consent and opens the eyes. It fails if the consent is missing, expired, or reused.
- `vision_stop` closes the eyes, clears frames, focus, grants, and pending requests.
- User takeover (mouse movement beyond the configured distance) closes the eyes immediately and emits `eye_closed` / `control_returned`.
- Every visual action rejects when the eyes are closed, the session is not the owner, or the user has taken over.

## Continuous frames

While the eyes are open, the runtime captures at `fps` and keeps the most recent `queue_size` frames. At model-turn assembly the current frame is attached to the context; the model does not need an explicit “look” call for the normal loop.

```ini
[vision]
fps = 3
queue_size = 2
focus_width = 512
focus_height = 512
focus_zoom = 1
settle_ms = 100
takeover_distance = 100
```

The full frame is scaled to `image_max_side`; the model reads coordinates in the delivered image. `vision_eye` is separate: it captures one window or region and returns that image without replacing the continuous frame.

## Coordinates and calibration

Absolute pointer tools receive model-image coordinates plus the image center and original size:

```text
vision_move_point(x, y, center_x, center_y, image_width, image_height)
vision_click_sequence(points, center_x, center_y, image_width, image_height)
```

When calibration is enabled, the current frame contains one random `C1` marker. Absolute move and click-sequence calls must pass `check_points` with the marker center read from the full frame. The runtime maps the marker to physical screen coordinates and rejects a mismatch beyond `calibration_tolerance_px`.

`vision_focus` and `vision_move_focus` are recovery paths and do not require `check_points`. A focus region is clipped to the screen and must remain at least 10×10 pixels; a partially off-screen region is clipped, not padded.

## Tools

### Vision core

| Tool | Purpose |
|---|---|
| `vision_request_open` | Request user consent |
| `vision_start` | Open the eyes with a valid consent |
| `vision_stop` | Close the eyes and clear visual state |
| `vision_focus` | Set a fixed focus region; next frame includes a 1:1 focus image |
| `vision_move` | Relative pointer movement |
| `vision_move_point` | Absolute pointer move with calibration |
| `vision_move_focus` | Move within the focus image |
| `vision_click` | Click at the current pointer position |
| `vision_click_sequence` | Move and click multiple points with calibration |
| `vision_key` | Send a key or hotkey through the Windows input backend |

`vision_click_sequence` requires `check_points`; `vision_move_point` requires it; `vision_focus` and `vision_move_focus` do not.

### Migrated desktop tools

These tools require the eyes to be open and are intended for system-level actions that vision alone cannot perform.

| Tool | Purpose |
|---|---|
| `vision_app` | Start a local application and wait for its window |
| `vision_window` | List, activate, wait for, or measure windows |
| `vision_eye` | One-shot screenshot of a window or region |
| `vision_type_into` | Type into a UIA control or a screenshot rectangle |
| `vision_keyboard` | Type Unicode text or send a single key; hotkeys use `vision_key` |
| `vision_wait` | Wait for screen change or a window event |
| `vision_find` | Find a UIA control by text |
| `vision_click_text` | Click a UIA text control |
| `vision_mouse` | Scroll or drag; pointer movement and clicks use the vision core |
| `vision_open` | Open a URL, file, or protocol |

`vision_eye` is an independent look, not a replacement for continuous frames. `vision_mouse` only accepts `drag` / `scroll`. `vision_keyboard` only accepts `type` / `key`; combinations use `vision_key`. `vision_click_text` is for standard UIA controls; self-drawn interfaces use the vision chain.

## Input backend

The 2.0 core backend is Windows-only:

```text
capture: GDI / ImageGrab
pointer: SetCursorPos / SendInput
keyboard: SendInput, keybd_event fallback
```

Key injection is reported as a structured receipt. If `SendInput` inserts fewer events than requested, the backend falls back to `keybd_event`; Alt+Tab is reported as successful with a warning, while Win and Ctrl+Esc are reported as failures because the shell does not accept the injected system hotkey in this environment. A failure is not reported as success.

The migrated desktop tools use the existing `visual_operator` desktop backend. The 2.0 core does not add macOS input or window/UIA support.

## Configuration

`plugin-config.ini`:

```ini
[vision]
fps = 3
queue_size = 2
focus_width = 512
focus_height = 512
focus_zoom = 1
settle_ms = 100
takeover_distance = 100
move_settle_ms = 50
move_duration_ms = 200
calibration_enabled = 1
calibration_tolerance_px = 32

[image]
format = webp
quality = 80
square_size = 0
image_max_side = 1600
focus_max_side = 512
```

`calibration_enabled=0` disables `C1` generation and `check_points` validation. `calibration_tolerance_px` is the maximum distance between the reported marker and the real mapped point.

## Logs and events

Step logs are JSONL and rotate at 2 MB:

```text
data/logs/visual_operator_2.steps.log
```

Each tool call records `tool_start`, `tool_done`, or `tool_failed`, plus `key_inject` and `click_inject` receipts. The UI listens for `eye_opened`, `eye_closed`, `control_returned`, and `vision_frame`; the eye toggle is an icon button that is hidden when the eyes are closed.

## Tests

`tests/test_visual_operator_2.py` covers focus bounds, the 10×10 minimum, no-`check_points` focus movement, authorization, takeover, pointer/click contracts, key injection receipts, migrated-tool authorization, and step-log path resolution. The desktop tools use the legacy backend; tests do not move the real pointer or inject real input.

## Related

- [plugins.md](plugins.md): plugin lifecycle and extension points
- [tools.md](tools.md): tool registration and execution
- [visual-operator-2.0.zh.md](visual-operator-2.0.zh.md): Chinese version
