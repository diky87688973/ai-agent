**English** | [中文](visual-operator-interaction.zh.md)

# Desktop operation interaction layer

## 1. Summary

The desktop tool surface exposes coordinate primitives: the model chooses which window to look at, estimates where a control is, and infers from a later screenshot whether its action worked. On a real task this becomes repeated attempts to bring a window to the foreground, coordinates read from a scaled screenshot, and text delivered to a window other than the intended one. Three gaps produce that loop: input has no target validation, actions return no receipt, and there is no window layer.

The design raises the tool surface from coordinate primitives to intent verbs, then closes batches with assertions.

Observation and input have different foreground requirements, and that difference shapes the design:

- Window content and window structure can be read without the target in the foreground: an occluded window returns its own content, and a minimized window is restored before capture. Neither case requires the target to hold the foreground.
- Input only reaches the foreground window. Text typed while the target is behind another window lands in whichever window holds focus.
- `SetForegroundWindow` is not a success signal: it can return `true` while the target is still minimized, and `GetForegroundWindow()` can point at that same target. The usable signal is whether the target content can be captured afterwards.

An action that changes the desktop therefore returns a screenshot in the same call (`shot`), and activation success is measured by the content that follows it, not by the API return.

Three layers, built in order and not merged:

| Layer | Content | Problem solved |
|---|---|---|
| L1 receipts | Changing actions return `focus` / `hit` / `changed` where the platform can observe them; input actions can return a screenshot (`shot`) | A mis-click is visible immediately instead of being inferred from the next screenshot |
| L2 semantic verbs | `desktop_window` / `desktop_find` / `desktop_click_text` / `desktop_type_into` / `desktop_app` | Locating is no longer estimated by the model |
| L3 batch pipeline | `desktop_act`: several steps in one call, each with `expect`, stop on failure | Round trips for a stable task drop from N to 1 |

The decision in `docs/plan/visual-operator.md` stands: the four baseline tools stay separate, and 15 actions are not folded into one `desktop_action`. L2 verbs compose L0 calls; L3 is a new independent tool, not a flattened parameter matrix. Baseline parameter semantics do not change, and new parameters are optional.

> **No OCR in the tool surface.** The model reads screenshots itself; a screenshot is its input. When text is unreadable, the fault is the captured window, the image scale, or a control that never expanded, not a missing recognition layer. Locating uses UI Automation (UIA) or coordinates only.

## 2. Interaction gaps

The first three are the structural gaps in the summary; the others are separate interaction costs.

| # | Gap | Effect | Design response |
|---|---|---|---|
| 1 | Input has no precondition | The target window and the landing point are unchecked; text can land in another window | Action receipts and batch `expect` |
| 2 | No window layer | Observation and action address the whole screen, so occlusion and stacking decide what is seen and hit | `desktop_window` and window-scoped capture |
| 3 | Actions return no receipt | A window that closed can only be inferred from later screenshots | `focus` / `hit` / `changed` / `window_changed` |
| 4 | Coordinates are read from a scaled image | A small control loses the pixels that identify it, and the estimated center falls outside | Structured locating with UIA rectangles; vision only confirms |
| 5 | One action per round trip, no wait semantics | The screenshot after an action shows the previous frame | `shot` and condition waits |
| 6 | Observation redundancy | Most frames in a turn add no information | Diff, dedup, and region crops |

Four constraints follow:

- **Observation does not require the foreground.** Window content comes from the window's own rendering, so occlusion does not change what is captured. A minimized window is restored with `SW_SHOWNOACTIVATE`, which triggers a real repaint without changing the foreground window or keyboard focus. Bringing it forward is a separate, explicit choice.
- **Input requires the target in the foreground.** When activation fails, delivery is refused and the receipt names the window that actually holds the foreground.
- **Success is evidenced, not asserted.** Every write is checked by a pixel or structural diff; a provider read-back never counts as evidence.
- **Window identity is part of the result.** The window under the cursor, the window that received the click, the captured window, and the activated window can be four different handles.

Screenshot scale varies: a full-screen capture is downscaled to `max_side`, while a window capture usually fits under the limit and is sent at its original size. The same screen coordinate therefore corresponds to different image pixels in the two, and a coordinate read from one does not transfer to the other.

## 3. Design principles

1. **Vision decides, it does not locate.** Vision answers "is this the player" and "is this a login dialog"; UIA answers "where is the search box". Coordinates are the last fallback, and a receipt that uses them must say so with `source` and confidence. No OCR: when text is unreadable, check the captured window, the image scale, and whether the control is expanded.
2. **Actions have preconditions and postconditions.** Every input must answer who received it, what was hit, and whether the frame changed.
3. **Results are handles.** The next step references the previous output by name; the model does not copy numbers.
4. **A batch must assert.** A batch without `expect` can fail five steps in a row inside one call.
5. **Context carries only frames with information gain.** Last frame on success, failure frame on failure; intermediate frames stay out.

## 4. Tool surface

| Layer | Tools | Nature |
|---|---|---|
| L0 | `desktop_eye` / `desktop_mouse` / `desktop_keyboard` / `desktop_wait` | baseline |
| L1 | optional `shot`; receipts `focus` / `hit` / `changed` / `window_changed` | extension of L0 |
| L2 | `desktop_window` / `desktop_find` / `desktop_click_text` / `desktop_type_into` / `desktop_app` | new |
| L3 | `desktop_act` | new |

The L2 verbs are compositions of L0 calls. They add no system-call surface and share the L0 input lock and Plan gating.

### 4.1 Handle contract

The pipeline passes handles, not copied numbers. Locating results and action receipts use this shape:

```json
{
  "cursor": {"x": 914, "y": 512},
  "hit": {"hwnd": 15404862, "title": "Media Player", "class": "PlayerWindow",
          "rect": {"x": 251, "y": 10, "width": 1418, "height": 1020},
          "element": {"role": "Edit", "name": "Search",
                      "rect": {"x": 498, "y": 30, "width": 502, "height": 22},
                      "source": "uia"}},
  "focus": {"hwnd": 15404862, "title": "Media Player"},
  "changed": 0.18,
  "diff_rect": {"x": 1020, "y": 60, "width": 620, "height": 380}
}
```

`source` is `uia` or `point`. A `uia` result is exact and carries no confidence; a `point` result carries `confidence` in 0–1. A coordinate without `source` is not a locating result.

### 4.2 Parameters of the new verbs

| Tool | Parameters | Contract |
|---|---|---|
| `desktop_window` | `action`: `list` / `activate` / `wait` / `rect`; `title` / `hwnd` / `class` / `timeout_ms` | `activate` restores and brings the target forward; success means the content can be captured afterwards, not that the foreground API returned `true`. `wait` returns when the window exists and is not minimized |
| `desktop_find` | `text`, `region`, `match` (`contains` / `exact` / `regex`), `source` (`auto` / `uia` / `point`), `limit` | Returns `matches[]`, each with `rect` / `index` / `source` / `confidence` |
| `desktop_click_text` | `text`, `index`, `region`, `button`, `count`, `shot`, `expect` | Internally: find, validate the hit (unique or nth), click, receipt |
| `desktop_type_into` | `target` (text or rect), `text`, `clear`, `submit`, `interval_ms`, `shot`, `expect` | Internally: locate, focus, clear, type, optional enter, wait for change |
| `desktop_app` | `name` / `path`, `args`, `timeout_ms`, `shot` | Launch, wait for the main window, activate; returns `pid` / `hwnd` / `rect` |

`desktop_app` and `desktop_open` (URL scheme or default browser) remain separate: the former waits for a window, the latter does not.

## 5. Two-step compositions

Baseline counts round trips with the four L0 tools; pipelined counts them after L1 and L2.

| # | Composition | Baseline | Pipelined | Data passed | Note |
|---|---|---|---|---|---|
| 1 | move, then click | 2 | 1 | `move.cursor` | The cursor handle is referenced directly |
| 2 | click, then view | 2 | 1 | — | `shot=true` |
| 3 | view, then click a given text | 2 | 1 | `find.matches[i].rect` | Locating comes from UIA |
| 4 | click, then type | 2 | 1 | inherited focus | `type_into` |
| 5 | type, then enter | 2 | 1 | — | `submit=true` |
| 6 | enter, then wait for change | 2 | 1 | `changed` | `desktop_wait(until="change")` |
| 7 | scroll, then view | 2 | 1 | — | `shot=true` |
| 8 | activate, then view | 2 | 1 | `window.rect` | `desktop_window(activate)` |
| 9 | launch, then wait for the main window | 2 | 1 | `window.hwnd` | Replaces a fixed sleep followed by a screenshot |
| 10 | view, then crop a region | 2 | 1 | grid cell or `element.rect` | Only the region is returned |
| 11 | click, then diff | 2 | 1 | `diff_rect` | Only the changed region is returned |
| 12 | drag, then view | 2 | 1 | — | `shot=true` |
| 13 | view, then zoom a region | 2 | 1 | `shot_region` | The region is captured directly instead of through the full-screen scale; the long-edge limit still applies |
| 14 | query the cursor, then move relative | 2 | 1 | `cursor` | Fine-tunes the landing point |
| 15 | hotkey, then view | 2 | 1 | — | `shot=true` |

## 6. Three-step compositions

| # | Composition | Baseline | Pipelined | Key point |
|---|---|---|---|---|
| 1 | activate, click the input, type and enter | 4 | 1 | One command performs the search and stays bound to the target window |
| 2 | view, find text, click and view | 3 | 1 | The click is verified immediately; a mis-click surfaces at once |
| 3 | move, click, type | 3 | 1 | Validate `hit` before typing |
| 4 | click the input, clear, type, enter | 4 | 1 | `clear=true` |
| 5 | view, scroll, view | 3 | 1 | Returns the last frame |
| 6 | list windows, activate, view | 3 | 1 | Resolves same-title windows |
| 7 | launch, wait for the main window, view | 3 | 1 | Replaces a fixed wait |
| 8 | click, wait, view | 3 | 1 | Popovers and loading |
| 9 | drag, view, diff | 3 | 1 | Verifies the drag result |
| 10 | find text, click the nth match, find the next | 3 | 1 | `index` selects explicitly |
| 11 | click, crop a region | 3 | 1 | Returns only the result region, captured directly |
| 12 | hotkey select-all, type, enter | 3 | 1 | Replaces the content |

## 7. Batch `desktop_act`

### 7.1 Request

```json
{
  "steps": [
    {"app": "Media Player", "expect": {"window": "Media Player"}},
    {"type_into": {"target": "Search box", "text": "Example", "submit": true},
     "expect": {"text": "Example", "timeout_ms": 3000}},
    {"click_text": {"text": "Example", "index": 0},
     "expect": {"changed": true, "timeout_ms": 5000}},
    {"expect": {"text": "Play"}, "capture": "final"}
  ],
  "on_error": "stop",
  "capture": "failure",
  "timeout_ms": 30000
}
```

### 7.2 Semantics

| Item | Rule |
|---|---|
| Step failure | `on_error="stop"` (default) stops at once and returns that step's screenshot and the step log; `on_error="continue"` is allowed only for read-only steps |
| Assertions | `expect` accepts `window` / `text` / `changed` / `rect_contains`, each with its own `timeout_ms` |
| Variable references | `$<step>.<field>`, for example `$2.hit.rect`; the type is fixed to `point` / `rect` / `window` / `element` / `text` |
| Destructive actions | When a target text matches a close, delete, pay, purchase, or unsubscribe pattern, the whole batch is rejected and the steps must run one at a time with confirmation |
| Images | Only the final frame and the failure frame are returned; intermediate frames contribute only size and `changed` to the step log |
| Limits | At most 12 steps and 60 seconds per batch; exceeding either is an error at the call site, not a silent truncation |

### 7.3 Boundary

A batch is not a flattened parameter matrix. Each step remains a separate `{verb: parameters}` object, and an unknown verb fails the call and lists the valid verbs. `desktop_act` carries no implicit state beyond L0 primitives: the previous step's cursor position is not inherited, and a click on it must be written as `{"click": {"point": "$1.cursor"}}`.

## 8. Locating pipeline

Two levels, each carrying `source`; results below UIA also carry `confidence`:

| Level | Means | Read | Write | Limit |
|---|---|---|---|---|
| 1 | UIA (`IUIAutomation`, Windows) | Reliable: returns control rectangles while the target is in the background | **Unreliable**: `ValuePattern.SetValue` can report success on self-rendered windows while the interface does not change | Providers can return cached values, so read-back validation is fooled the same way |
| 2 | Coordinates | — | Requires a hit test first | Accuracy is bounded by image reading |

Writes go through coordinates plus a hit test: UIA resolves the coordinate to a concrete control, the tool confirms that the control is editable, and only then is input delivered. The UIA write path exists as a fast path for native controls and must pass a pixel diff.

**No OCR.** When text cannot be read, check the observation side first: whether the wrong window was captured (`hover.hit` and the screenshot window differ), whether the whole screen was downscaled, and whether the control is expanded. These are the actual causes of a failed hover; OCR would mask them as a recognition error.

Acceptance criteria:

- `desktop_find("Search")` on a client that exposes a UIA tree must return the input rectangle, or explicitly return `source="point"` with low confidence. A plausible-looking coordinate must never be returned silently.
- `desktop_type_into` must end with a pixel diff. Judging success only from a read-back of `ValuePattern.Value` does not pass.

## 9. Observation and context

| Means | Rule |
|---|---|
| `shot` | Capture the target window content after the action; default `false`; semantic verbs default to `true` |
| Source | A screenshot captures the window content by `hwnd`, not the whole screen; the screen is used only when no window is known |
| `diff` | Compare with the previous frame block by block and return only the `diff_rect` region; when nothing changed, report `changed=0` without an image |
| Dedup | An identical frame (same hash) does not enter the context twice; the receipt returns `same_as: <shot_id>` |
| Region | Region screenshots take precedence over window screenshots, and window screenshots over the full screen; the full screen is the fallback when no window can be determined |
| Budget | At most one image per result; anything beyond that follows the existing budget rules of `build_tool_parts` |

A window capture comes from the window's own render pass (`PrintWindow` with full-content rendering), not from a screen copy; that is why occlusion does not affect it. When the window render still yields no content, capture falls back to the screen and reports `source="screen"`. A full-screen capture downscales small controls until a coordinate read from the image no longer identifies them. Region and window captures start from the real pixels of the target, so they keep more detail than a full-screen frame; `max_side` still caps the long edge.

## 10. Safety and gating

1. Plan mode uses `reject_in_plan`: reads and queries are allowed; anything that changes desktop state is refused. That covers input, cursor movement, and explicit activation. `desktop_eye` without `hover` or `activate=true` only reads and stays available; `hover` and `activate=true` are refused. `desktop_wait` is read-only and available. Mouse actions other than `cursor`, and all keyboard actions, are refused.
2. Destructive actions: a batch that targets close, delete, pay, purchase, or unsubscribe text is rejected as a whole.
3. The input lock reuses `input_guard()`; a batch holds the lock for its entire duration so that a click from another session cannot land between steps.
4. Host window avoidance is out of scope: the page can report `screenX` / `screenY` / `outerWidth` / `outerHeight` to derive the host window rectangle, and input tools can then refuse coordinates inside it.

## 11. Invariants

Continuing the ten invariants in `docs/plan/visual-operator.md`:

11. Every action that changes the desktop and targets a window returns `focus`; when the landing point is known, it also returns `hit`.
12. Vision is not a final locating method. Coordinate locating must mark `source="point"` in the receipt.
13. A batch stops on failure and returns the failure frame; a failed step is never skipped silently.
14. New parameters are optional; the baseline tools behave the same when they are omitted.
15. Observation requires no foreground; input requires the target to hold the foreground. A failed activation refuses delivery and reports the actual foreground.
16. Verification of a write action must come from a pixel or structural diff; a provider read-back is never success evidence.
17. A coordinate click requires a hit test first. When no concrete control resolves, mark `source="point"` with lower confidence and never click silently.
18. `desktop_eye` and hand actions accept `window` / `hwnd`: capture reads window content, input activates first.
19. Capture does not activate by default. A minimized window is restored with `SW_SHOWNOACTIVATE`, which triggers a real repaint, and neither the foreground window nor keyboard focus moves. Bringing a window forward is an explicit `activate=true` from the model, not an implicit side effect.
20. Targeted hand actions always activate before delivery, and this cannot be turned off. Input only reaches the foreground, so a failed activation must refuse delivery.

## 12. Phases

| Phase | Change | Files | Acceptance |
|---|---|---|---|
| P0 | Action receipts, `shot`, restore without activation, foreground check | `tools/mouse.py`, `tools/keyboard.py`, `tools/_capture.py`, `tools/_windows.py`, `diff.py`, `ports.py`, `backends/win32.py` | A mis-click is visible in the first receipt: `hit` points at the window control button, not the content area. An occluded target still yields its own content |
| P1 | `desktop_window`, `desktop_app` | new `tools/window.py`, `tools/app.py` | Activation takes one round trip, and failure is not read from an API return |
| P2 | `desktop_find`, `desktop_click_text`, `desktop_type_into` | new `tools/find.py`, `tools/click_text.py`, `tools/type_into.py`, `locate.py` | The search box resolves in one call, or the result is explicitly low confidence |
| P3 | `desktop_act` | new `tools/act.py`, `pipeline.py` | The target scenario completes in at most 3 round trips |

Acceptance budget: at most 15 round trips after P0, 8 after P1, 5 after P2, and 3 after P3.

## 13. Out of scope

1. No third-party desktop automation or window packages. The Windows backend stays on `ctypes`; UIA is reached through COM (`ctypes` calls or a pure-Python implementation), so no new compiled dependency is added.
2. No cross-platform UIA abstraction. The macOS AX interface is out of scope.
3. No general record-and-replay; it needs its own interaction design.
4. No single `desktop_action` that takes every action.
5. No batch without `expect`.

## 14. Risks

| Risk | Mitigation |
|---|---|
| The UIA tree is empty for self-rendered windows | Degrade to coordinates and expose `source` in the receipt; a per-class locating strategy table can be added when needed |
| A provider reports success while the interface does not change | Every write is verified by a pixel or structural diff; read-back values go to the log only |
| `SetForegroundWindow` returns `true` but the window is unusable | `activate` concludes with whether content can be captured, not with the return value |
| Unreadable text is mistaken for a missing OCR layer | Documentation and receipts point at window identity and image scale first; OCR stays excluded |
| Assertions are too strict and stop runs unnecessarily | `expect` has an independent `timeout_ms`; the failure receipt includes the last frame |
| A batch reduces observability | The step log is part of the result; the failure frame is always returned |
| Window titles are localized or duplicated | `desktop_window` accepts `hwnd` / `class`; `list` returns `pid` and `rect` for disambiguation |

## 15. Receipts

Receipt fields are additive. An absent field means the platform could not observe it; it does not mean nothing happened.

### 15.1 Activation

Input actions given a target window activate it before delivery and report the attempt:

| Field | Contract |
|---|---|
| `focus` | `hwnd`, `title`, `rect`, `active`, `restored`, `foreground`; `matched` and `alternatives` when several windows share the title |
| `active` | The target holds the foreground and is not minimized. The API return is not consulted |
| Failure | Input is not delivered; the error names the window that actually holds the foreground |

`desktop_eye` with `activate=true` reports `activated` and the window metadata instead.

### 15.2 Action evidence

| Field | Contract |
|---|---|
| `hit` | Window handle, control class, and top-level title under the landing point; omitted when probing is unsupported |
| `changed` / `changed_scope` | Pixel difference ratio 0–1 in a 200×200 region around the landing point; `changed_scope` is `point_200` |
| `window_changed` | Window-layer comparison: `hit_before` / `hit_after`, `opened` / `closed`, `changed`, `navigated` |
| `changed_late` / `changed_late_after_ms` | A second sample 250 ms after a near-zero local change; `changed` takes the larger value and `changed_note` records why |

`hit` answers what was struck; `changed` answers whether that spot reacted. A navigation click can leave `changed` at 0 while the window layer changes; `window_changed.navigated=true` is then the signal, and the same coordinate must not be repeated.

### 15.3 Screenshots returned by actions

| Parameter | Contract |
|---|---|
| `shot` | Attach a screenshot in the same call; default `false` |
| `shot_region` | `[x, y, width, height]`; otherwise the hit window or the screen |
| `shot_max_side` | Long-edge limit; defaults from configuration |

The screenshot follows the window where the action landed (`shot_of="hit"`), not a new title lookup. An explicit `window` / `hwnd` wins (`shot_of="window"` / `"hwnd"`); the screen is used only when neither the landing window nor a target is known. When the landing window and the activation window differ, `note` names both handles. `desktop_mouse` accepts all three parameters; `desktop_keyboard` accepts `shot` and `shot_max_side`. `move` returns a screenshot but no `hit` or `changed`: moving does not change the interface, although hovering can expand a control.

### 15.4 Waiting

`desktop_wait` waits on `until=change`, `window_appears`, or `window_disappears`. `timeout_ms` is an upper bound; a timeout returns `satisfied=false` with the last observed state and is not an error. A fixed `task_sleep` is not a valid wait in a desktop flow.

## 16. Hover and window identity

Hover capture and hit probing exist because a window title does not identify the window that owns the pixels. The player surface can be a separate top-level window while the title resolves to the shell that hosts the detail page; the cursor can be over one window while the screenshot shows another.

| Problem | Rule | Field |
|---|---|---|
| The cursor layer is unknown | Probe the window under the cursor after hovering | `hover.hit` |
| The cursor layer differs from the captured layer | State both handles and the one to use | `note` |
| A jump produces no continuous mousemove | Move through `hover_path`, over `hover_approach_ms`, then a small `hover_wiggle` | `hover.path` / `hover.approach_ms` / `hover.wiggle` |
| `changed=0` is read as a miss | Compare the window layer and report navigation | `window_changed.navigated` |
| Repaint after navigation lags | Re-sample 250 ms later when the landing point did not move | `changed_late` |
| `shot` re-resolves by title | Follow the landing window | `shot_of` / `note` |

`desktop_eye(hover=[x, y])` moves the cursor, waits for the interface to expand, and captures in one call; `hover_settle_ms` sets that wait. Hover controls typically collapse within 2–3 seconds, while two tool calls are separated by a model round trip, so splitting the move and the capture misses the control. Hovering a background window can land on whatever covers it; `activate=true` is required when the hovered control must receive the pointer. Without `window` / `hwnd`, the capture target is the window under the cursor (`window.auto="hover.hit"`), taken from that window instead of the full screen; `max_side` still applies.

`window` is a title fragment, and several windows can match it. Candidates are ranked foreground, then Z-order, then area, because the window in front is usually the intended one and the largest can be an overlay. When more than one matches, the receipt carries `window.matched`, `window.alternatives` (up to four candidates), and a `note` naming the selected `hwnd` and the others. A bare count would leave the model to guess; its usual fallback, a full-screen capture, changes the scale.

Acceptance criteria:

- A `hover` receipt must include `hover.hit` when the platform supports hit probing; when it differs from the captured window, `note` must be present.
- A mouse action with `shot` must not report `shot_of="screen"` when landing-point probing is supported.
- When `changed=0` and `window_changed.changed=true`, the model must not repeat the same coordinate.
- No OCR dependency is added; `image_ocr` is not part of a desktop flow.
