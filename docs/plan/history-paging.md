**English** | [中文](history-paging.zh.md)

**Status:** Implemented. The English and Chinese documents are synchronized.

## 0. Pre-implementation baseline

Backend:

- `Inbound.history(cid, store=None)` read every event in one pass, called `history_items(events)` to fold them, then registered attachments as a whole and returned `items` / `context_layout` / `todo_list`.
- `Inbound._load_events()` called `store.load(cid)`; `load()` drops the line-position fallback, so it could not serve as a source of paging anchors.
- `/api/chat/history` in `web_routes.py` called `classic.history(conversation_id)` directly; it parsed neither `before` nor `meta`.
- `classic_adapter/history.py` was a single-file folding implementation with no separate round structure or page selection.
- `ClassicState.put_attachments()` replaced the whole set; `Inbound.remember_attachments()` also called it.
- `SessionActions.history` and the subagent `/api/subagents/history` remained full-history endpoints without paging.

Frontend:

- `makeConversationTab()` had no `historyBefore` / `historyState` fields; `historyLoaded` was a runtime field added on demand.
- `loadConversationHistory()` set `t.historyLoaded=true` before the request and never reset it on failure; it had no `before` parameter.
- `loadConversationHistory()` rendered history only when the message area was empty or held a single node, and relied on the global `msgs`.
- `refreshConversationContextLayout()` still requested the full `/api/chat/history`; it did not use the summary-only `meta` form.
- `renderHistoryItems()` wrote directly to the global `msgs`; there was no detached-container rendering or prepend viewport anchoring.

Conclusion: the core data foundation for paging (fact log, `_seq`, folding rules, attachment cache, SSE) already existed; the gaps were round folding, page selection, attachment merging, frontend state, and scroll prepending.

# Session history paging

## 1. Background and goals

On page refresh, the classic UI calls `GET /api/chat/history` and receives the whole conversation history in one response. The endpoint folds the entire `.raw` fact log into `items` (user bubbles, thinking, assistant text, tool cards with their result payloads, and attachments), and the frontend builds a DOM node for each item. The larger the conversation, the slower the refresh, the more DOM nodes, and the greater the memory pressure.

Goals:

1. Render only the newest page on first paint; refresh time and memory use are decoupled from total conversation length.
2. Fetch earlier pages on demand when scrolling up, until exhausted.
3. Do not change the fact-log format, the kernel event interface, or SSE replay semantics.
4. Place page boundaries on user rounds so that no page contains half a round.

## 2. Terminology

| Term | Meaning |
|---|---|
| Round | Everything from one `input_claimed` fact up to the next `input_claimed` |
| Round ID | The `_seq` of that round's `input_claimed` fact: its global storage coordinate, monotonic and unique |
| `before` | **Exclusive** page boundary: only rounds whose round ID is lower than it are returned |
| `next_before` | Round ID of the earliest round in this page, which is the `before` of the next request; `null` when `has_more=false` |
| Page | An item sequence made of several **consecutive complete rounds** |
| Character cost | Number of characters in one `item` converted to text; measured as described in 5.3 |

The design does not use the word `cursor`: in this project `cursor` refers specifically to the global storage coordinate used for SSE reconnect and replay (`cursor_of` / `replay_after` / `Last-Event-ID`). A page boundary is a round ID; the two are different, and mixing the words would conflate "going further back" with "replaying from a breakpoint".

A round may contain: a user bubble and its attachments, thinking blocks, one or more assistant messages, and one or more tool cards (arguments, result `preview`, diff, images).

## 3. Invariants

1. The unit of paging is the round, not the message count or the event count.
2. A page accumulates from the newest round toward older ones and stops when the cumulative character cost **reaches or exceeds** `10000`; the round that crosses the threshold is included **as a whole**. A page is therefore "the smallest set of whole rounds whose cumulative cost is at least `10000` characters".
3. The round ID is `input_claimed._seq`. No round field is added and the on-disk format is unchanged.
4. Paging happens only in the classic-UI projection layer. The kernel's raw event endpoint (`SessionActions.history`) does not take part in paging.
5. `context_layout` and `todo_list` are whole-conversation summaries; they are returned in full on every page and do not take part in paging.
6. `before` is exclusive: only rounds whose round ID is **lower than** it belong to the result.

## 4. Interface contract

### 4.1 Request

```text
GET /api/chat/history?conversation_id=<cid>[&before=<seq>][&meta=1]
```

| Parameter | Required | Meaning |
|---|---|---|
| `conversation_id` | Yes | Conversation ID |
| `before` | No | Exclusive boundary (round ID). When omitted, the newest page is returned |
| `meta` | No | `1` requests only `context_layout` and `todo_list`; `items` is not folded and `page` is not returned |

### 4.2 Response

```json
{
  "ok": true,
  "conversation_id": "…",
  "items": [
    { "role": "user", "content": "…" },
    { "role": "tool", "tool_call_id": "…", "script": "…", "status": "done" }
  ],
  "page": {
    "budget_chars": 10000,
    "chars": 9832,
    "has_more": true,
    "next_before": 1203
  },
  "context_layout": {},
  "todo_list": []
}
```

Field rules:

1. `next_before` is the round ID of the **earliest round** in this page, and is exactly the `before` of the next request.
2. When `has_more` is `false`, `next_before` must be `null`.
3. `page.chars` is the sum of the character costs of the items in this page; it is diagnostic and is not read by the frontend.
4. The `items` order is exactly the same as in a full fold; prepending does not change relative order.
5. For a normal request the `page` key set is exactly `budget_chars` / `chars` / `has_more` / `next_before`.

`page` is a new optional key, forward-compatible only:

- `meta=1` returns neither `page` nor `items`;
- the frontend checks that `j.page` exists before reading it; a client that ignores the key can still render this page's `items`, but cannot page further back;
- the server does not fail when `before` is absent; the default is the newest page;
- no `page_version` field is added: it has no consumer, and adding one would create a dead contract.

### 4.3 Errors and degradation

| Case | Behavior |
|---|---|
| `before` is not a non-negative integer | `ok:false`, `error:"invalid before"`, `items:[]`, no `page` |
| `before` is older than the earliest round | `items:[]`, `page.has_more:false`, `page.next_before:null` |
| Conversation does not exist or has no events | `items:[]`, empty `page`, `context_layout` / `todo_list` returned as usual |
| `meta=1` | `items:[]`, no `page`, summary fields returned as usual |

The endpoint keeps the existing `ok` semantics: when it is not `true`, the frontend does not render and does not continue paging.

Parsing and rejection of `before` happen in exactly one place, `web_routes.py`: absent → `None`, invalid → early return as `ok:false`. The adapter receives an already validated `int | None` and does not validate its shape again. Splitting the validation point would make invalid input produce two different results on two paths.

## 5. Backend design

### 5.1 Modules and dependencies

The implementation adds `agent/shell/classic_adapter/history_page.py`. The module is a **pure-function module**:

- it imports no `store`, HTTP, or adapter code, and no layer above `agent.capabilities`;
- its input is events together with their storage coordinates; its output is rounds and pages;
- the event-to-item folding rules still live in `history_items` in `classic_adapter/history.py`; `history_page.fold_rounds` calls it once per round and existing callers are unaffected.

Dependency direction remains `shell → capabilities → mechanisms → core`.

### 5.2 Data structures

```python
@dataclass(frozen=True)
class Round:
    anchor: int | None                 # round ID; None = residual events before the first input_claimed
    items: tuple[dict, ...]
    attachments: tuple[dict, ...]
    chars: int

@dataclass(frozen=True)
class Page:
    items: tuple[dict, ...]
    attachments: tuple[dict, ...]
    start: int
    end: int
    chars: int
    has_more: bool
    next_before: int | None
```

`frozen=True` only prevents attribute assignment; it does not prevent `page.items.append(...)`, which would create hidden state visible inside the object but not through its public surface. Every collection field is a `tuple`, normalized with `tuple(...)` before construction. `Round` and `Page` are **pure values**: callers that receive them cannot rewrite a paging result.

The `dict` objects inside `items` and the `list` objects inside `attachments` / `images` are still mutable, so the paging functions copy their output before returning: top-level `dict` and nested `list` objects are newly created, the attachment cache and the output share no mutable objects, and a caller modifying a returned value does not affect the next call. JSON requires `list`, so `MappingProxyType` cannot be used (`json.dumps` does not accept it).

`attachments` collects only the bytes that this page needs to register in the attachment cache, so paging does not re-register the whole conversation's attachments. Images in tool results remain inline as `data_base64` in `items` and do not enter `attachments`.

### 5.3 Character cost

`item_cost(item)` approximates the amount of text in the UI payload area:

| item | Counted |
|---|---|
| `user` | `content` length; attachments by their public `name` length |
| `think` | `content` length |
| `assistant` | `content` length |
| `tool` | `script` + compact JSON of `args` + `preview` + `error` + `output` + the full `images` JSON, including `data_base64` |

Rules:

1. JSON uses `ensure_ascii=False` and separators without spaces. The UI formats `preview` as indented JSON, so this measure is a lower bound, not an exact character match.
2. User attachment bytes are not carried in `items`; the attachment endpoint serves them separately, and they do not count toward character cost. Tool images are counted through their inline `images` JSON, including `data_base64`.
3. `None` and missing fields count as 0.
4. The threshold constant `HISTORY_PAGE_CHARS = 10_000` is defined in this module; it is not read from configuration.

### 5.4 Round folding

`fold_rounds(events)`:

1. Scan events in order and produce items with the existing folding rules (the original `history_items` implementation).
2. Start a new round at each `input_claimed`, with `anchor = event.data["_seq"]`.
3. `tool_started` creates the tool item; later `tool_done` / `tool_failed` / `tool_canceled` / `tool_suspended` / `tool_ended` and `tool_progress` events merge into the existing tool item by `call_id` and stay in the current round.
4. Events before the first `input_claimed` go into a residual round with `anchor=None`, placed first.
5. Accumulate `chars` per round, keeping `chars == sum(item_cost(i) for i in items)`.

`history_items(events)` keeps its signature and remains the single implementation of event-to-item folding; it does not call `fold_rounds`. `fold_rounds` only splits events at `input_claimed` boundaries and calls `history_items` once per round, so existing callers and tests see the same output.

### 5.5 Page selection

```python
def select_page(rounds, *, before, budget=HISTORY_PAGE_CHARS):
    end = len(rounds)
    if before is not None:
        end = len(rounds)
        for index, rnd in enumerate(rounds):
            if rnd.anchor is not None and rnd.anchor >= before:
                end = index
                break

    start = end
    chars = 0
    while start > 0:
        start -= 1
        chars += rounds[start].chars
        if chars >= budget:
            break

    page = rounds[start:end]
    has_more = start > 0
    return Page(
        items=tuple(flatten(page)),
        attachments=tuple(collect_attachments(page)),
        start=start,
        end=end,
        chars=chars,
        has_more=has_more,
        next_before=rounds[start].anchor if has_more else None,
    )
```

Boundaries:

1. When a single round costs more than `budget`, that round is returned whole and `chars` truthfully exceeds the budget.
2. A residual round (`anchor=None`) can only be included as the last page; once it is included, `has_more` is false.
3. When `before` equals a round's ID exactly, that round is not returned.
4. `end == 0` returns an empty page with `start == end == 0` and `has_more` false.
5. The round ID is `event.data["_seq"]`. History loading uses `store.load_with_seq()`, which returns `(seq, event)`: a persisted row with `s` uses it, and an old row without `s` uses its line position, written back to `_seq` before folding. `store.load()` discards the line-position fallback, so old rows without `s` come back without `_seq`.

### 5.6 Adapter and routing

`Inbound.history` is the paging entry point. `ClassicAdapter` inherits it directly; no forwarding layer is added, and `before` / `meta` take effect through the method signature. The kernel raw event endpoint remains outside paging.

1. `classic_adapter/inbound.py`
   - `history(cid, store=None, *, before=None, meta=False)`; `before` is already the validated `int | None`, and `store` lets subagent history supply its own store.
   - `_load_events` reads `(seq, event)` pairs: an event that already has `_seq` keeps it, old rows are numbered by their `load_with_seq()` line positions, and the coordinate is written into an event copy before folding; it does not rely on `store.load()`.
   - `meta=True`: compute only `context_layout` and `todo_list`, skip folding, and return `items:[]` without `page`.
   - Otherwise: `fold_rounds` → `select_page` → build the response from `Page.items`; attachments are registered with the merge rule in 5.7.
   - The response adds optional `page`; all other fields keep their existing shape.
2. `classic_adapter/adapter.py`: `ClassicAdapter` inherits `Inbound.history` directly; `before` / `meta` take effect through the method signature.
3. `web_routes.py`: the only place that parses `before` / `meta`; an invalid `before` returns `ok:false` immediately, `meta` is read as a `1` / `0` flag, and valid values pass through.
4. `SessionActions.history` in `web_sessions.py` (the kernel raw event endpoint) is unchanged.

### 5.7 Attachment registration

`ClassicState.put_attachments` is a **whole replacement** (`attachments[cid] = list(items)`), not an append. If each page called it with only its own bytes after paging, page 2 would remove page 1's already-rendered bubble attachments from the cache. The attachment endpoint re-runs `history(cid)` as a fallback when an id is missing, but after paging that call fetches only the newest page, so older pages' attachments are never registered again; those `<img>` requests would 404 without any UI error.

Therefore `ClassicState.merge_attachments(cid, items)` is added:

1. Merge by `id`; a duplicate `id` takes the new content but keeps its first position; new ids are appended after.
2. `Inbound.history` applies `ATTACH_REGISTER_MAX_COUNT` / `ATTACH_REGISTER_MAX_BYTES` before calling merge; `merge_attachments` only merges the cache and does not interpret count or byte policy.
3. Do not trim globally: the cache bound is 24 images per page × loaded pages, with each image at most 2 MB. If memory pressure appears, add a global bound and evict pages that have left the viewport; that requires a new eviction set and is a separate design, not part of this one.
4. `ClassicState` remains the single authority: `inbound` supplies only the current page's increment and keeps no second copy.
5. Conversation switches and clears continue to use `clear_attachments`, unchanged.
6. `remember_attachments` (registration when sending images) also merges; calling `put_attachments` there would clear loaded pages' attachments after paging.
7. `merge_attachments` and `get_attachment` complete under the same lock; paging and sending images concurrently cannot wipe registered attachments through a whole replacement.

## 6. Frontend design

### 6.1 Per-conversation state

`historyLoaded` records whether the first screen has rendered; `historyBefore` and `historyState` drive older-page loading. All three are explicit fields initialized by `makeConversationTab()`:

```js
historyLoaded: false,     // whether the first screen has rendered
historyBefore: null,      // before for the next page; null = not fetched yet
historyState: "idle"      // "idle" | "loading" | "exhausted" | "error"
```

`historyState` is an **exhaustive four-state** value, not two booleans:

| State | Meaning | Behavior when scrolling to the top |
|---|---|---|
| `idle` | Earlier pages are still available | Send a request |
| `loading` | A request is in flight | Send no second request |
| `exhausted` | No earlier rounds remain | Send no request |
| `error` | The last attempt failed and has not recovered | **Send no request**; wait for the user to click retry |

Two booleans `historyHasMore` + `historyLoading` cannot express `error`: after a failure `hasMore` is still true, so scrolling to the top retries forever and turns one network failure into an infinite loop.

The four states live only in the current tab's runtime memory and are not written to `saveRuntimeStateToTab` / `loadRuntimeStateFromTab`; after a refresh, `loadConversationHistory` rebuilds them.

### 6.2 First screen

1. `loadConversationHistory(t)` sends no `before`.
2. Set `loading` while the request is in flight; do not set `historyLoaded=true` in advance. On success, set `historyLoaded=true`, set `historyBefore=j.page.next_before`, and set `exhausted` or `idle` from `has_more`; on failure set `error`, keep `historyLoaded=false`, and show a retry hint once.
3. Keep the existing rule: when the message area already contains live content, do not clear it; render only this page.
4. Scroll to the bottom after the first screen renders.

### 6.3 Paging upward

All of the following must hold:

- the scroll container's `scrollTop <= 4`;
- `t.historyState === "idle"`.

Both entry points share one function, `loadOlderHistory(t)`:

1. Reuse each tab's existing `trackMsgsBottom` scroll listener; find the owning tab by container in its callback and add no second scroll listener.
2. A global `wheel` capture listener (`passive: true`) handles the case where the container is already at the top and the user keeps scrolling up: no `scroll` event is produced, so `deltaY < 0` is required to keep fetching pages.
3. Send `before = t.historyBefore`; when `historyBefore` is `null`, send no request.
4. Set `loading` during the request, show a lightweight theme-aware hint at the top of the message area (dark background and secondary text in the dark theme), and remove it when done.
5. On success, prepend and preserve the viewport anchor:

```js
var anchor = msgs.scrollHeight - msgs.scrollTop;
msgs.prepend(fragment);
msgs.scrollTop = msgs.scrollHeight - anchor;
```

6. On failure set `error`; the top hint becomes "加载更早的对话失败 · 点击重试" and stays in place. Only clicking retry returns to `idle` and requests again. Failures must leave a trace: `console.error` with `cid`, `before`, and the HTTP status; a silent `catch(e){}` is not allowed. Failures are **not retried automatically**: automatic retry would make "the network is down" look like "scrolling is stuck and the CPU is spinning".

Stop conditions (any one sets `exhausted`):

1. `has_more` is false;
2. `next_before` equals this request's `before` (guards against a server boundary that does not advance);
3. empty `items` are returned.

A quick-jump-to-bottom button sits outside the composer's upper-right corner and delegates clicks through `data-chat-jump-bottom`. It is visible only when the active tab's message area is scrollable and not at the bottom; clicking calls `scrollToBottom`, and reaching the bottom hides it. Its position and theme colors come from `chat-messages.css`.

### 6.4 Render context switching

`add()`, `onToolStart()`, `onToolEnd()`, `appendChatToolRow()`, and `appendStep()` all read and write the globals `msgs` / `steps` / `streamAssistantEl`. Paging temporarily switches them with a guard function:

```js
function withRenderContext(msgsEl, stepsEl, fn) {
  var prevMsgs = msgs, prevSteps = steps;
  var prevStream = streamAssistantEl, prevText = streamAssistantText;
  msgs = msgsEl;
  steps = stepsEl;
  streamAssistantEl = null;
  streamAssistantText = "";
  try {
    return fn();
  } finally {
    msgs = prevMsgs;
    steps = prevSteps;
    streamAssistantEl = prevStream;
    streamAssistantText = prevText;
  }
}
```

The render targets are two detached containers; after rendering, their child nodes are prepended to the real message area and steps area respectively. Tool cards, thinking blocks, and attachment strips therefore share the same render functions as the live path, with no second implementation. The guard saves and restores values the same way `withConversationContext` does, but points the targets at detached containers.

### 6.5 Delayed rendering of oversized tool payloads

1. The constant `LAZY_TOOL_TEXT_CHARS = 100000` is defined in `chat-tool-views.js`.
2. Route every long-text write through `setLazyText(el, text)`:
   - at or below the threshold: write directly;
   - above the threshold: write only the summary line; keep the full text on the element and insert it into the DOM on expansion.
3. The existing delegated expand click (`.chat-tool-head`) calls `materializeLazy(el)` when expanding.
4. The mechanism keys on text length, not tool name, and is shared by the live and history paths.
5. Collapsing changes only when text is written to the DOM; it does not change the character budget or paging results.

### 6.6 Summary-state refresh

`refreshConversationContextLayout(t)` requests `?meta=1`, so it fetches only `context_layout` and `todo_list`; a summary refresh therefore does not fold a page of `items`. `meta=1` returns neither `items` nor `page`, so this path cannot reuse the first-screen rendering path.

## 7. File inventory

| Action | File |
|---|---|
| Add | `agent/shell/classic_adapter/history_page.py` |
| Modify | `agent/shell/classic_adapter/history.py` |
| Modify | `agent/shell/classic_adapter/inbound.py` |
| Modify | `agent/shell/classic_adapter/state.py` |
| Modify | `agent/shell/web/web_routes.py` |
| Add | `agent/shell/web/web_assets/classic/js/history-paging.js` |
| Modify | `agent/shell/web/web_assets/classic/js/chat/conversation.js` |
| Modify | `agent/shell/web/web_assets/classic/js/chat-tool-views.js` |
| Modify | `agent/shell/web/web_assets/classic/css/chat-messages.css` |
| Modify | `agent/shell/web/ui_bundle.py` |

Paging logic goes into the new file `history-paging.js` rather than accumulating in the conversation module: the classic UI's main script is already split into modules by responsibility (see `ui_bundle.UI_JS_MODULES`), and individual files generally stay within a few hundred lines.

The new file is registered in `UI_JS_MODULES`: `scripts/check_ui_js.py` takes its file list from the same list, so no separate registration is needed; modules share one `<script>` scope and can call main-script functions directly. Startup code lives in `core/boot.js` and `layout/splitters.js`; if the new file depends on globals in that scope, place it after those modules.

`setLazyText` / `materializeLazy` belong to tool views and live in `chat-tool-views.js`, not in the paging file: they serve "any long text", not "history paging".

## 8. Tests and acceptance

Unit tests (`tests/test_history_page.py`):

1. Character cost: each item kind and attachments, empty fields, an oversized `preview`.
2. Round folding: a single round, multiple rounds, tool events merged across events, residual events before the first `input_claimed`, and line-position backfill for old rows without `_seq`.
3. Page selection:
   - the threshold falls exactly on a round boundary;
   - the threshold falls inside a round, which is then included whole;
   - one round exceeds the budget;
   - `before` is exclusive;
   - `before` is out of range;
   - `has_more` and `next_before` on the last page.
4. `items` order matches a full fold.
5. Returned values are immutable: `page.items` / `round.items` are `tuple`, so `append` raises `AttributeError`; modifying `page.items[0]["content"]` and requesting again yields the baseline result; modifying the elements of `page.items[0]["attachments"]` leaves the object returned by `get_attachment` unchanged.
6. Attachment merge: after two `merge_attachments` calls, the first call's `id` is still available through `get_attachment`; a second registration of the same `id` overrides it; exceeding the per-call cap truncates only the incoming batch.
7. An invalid `before` is rejected at the routing layer and the adapter is not called (a stub asserts zero calls).
8. Concurrent page requests and `merge_attachments`: each page's `items` are self-consistent, attachment ids are not lost, and no page references an attachment that has been cleared.

Frontend behavior:

1. Offline, scrolling to the top: the hint "加载更早的对话失败 · 点击重试" appears and no further requests are sent; after the network recovers, clicking retry resumes paging.
2. When `next_before` equals this request's `before`, the state becomes `exhausted` immediately and no second request is sent.

Integration and manual acceptance:

1. A conversation of about 50,000 characters across 10 rounds: the first screen contains only the newest whole rounds, their cumulative cost is at least `10000`, and the earliest round is complete.
2. Scrolling to the top prepends automatically without moving the viewport content; after reaching the earliest page, no more requests are sent.
3. A single round with 50,000 characters of tool output: the whole round is returned, the payload is collapsed by default, and expansion shows the full text.
4. Refreshing a 10 MB conversation: the first-screen DOM contains only one page of items, and the `history` response does not contain all `items`.
5. `meta=1` returns only `context_layout` and `todo_list`.
6. Paging back while a turn is running: the streaming bubble stays at the bottom and prepending does not interrupt it.

## 9. Boundaries and costs

1. Each page request still reads the full event log and folds it, O(n). This design adds no round index; a separate index structure is worth designing only if latency becomes visible.
2. No viewport virtualization; loaded old pages are not unloaded. Old pages appear only after the user pages back.
3. No `round` field is added; neither the frontend nor the server keeps extra round accounting.
4. The kernel event interface and SSE reconnect replay are unchanged.
5. Paging affects only the classic-UI projection; other clients read the kernel's raw event endpoint and behave as before.
6. Images in tool results are returned inline as `data_base64` with `items`, and `item_cost` counts their full `images` JSON toward the character budget; user attachment bytes are not counted. The image bytes of a page are determined by the round count and their content, not by the character threshold.
7. After a process restart the attachment cache is empty, and the attachment endpoint's fallback fetches only the newest page; images in already-loaded older pages may 404 until those pages are fetched again.
8. The subagent history route (`/api/subagents/history`) sends no `before` and returns only the newest page; paging back for subagent conversations is outside this design.

## 10. Implementation sequence and acceptance

### 10.1 Step 1: pure-function paging layer

Add `agent/shell/classic_adapter/history_page.py` with only round folding, character cost, and page selection:

1. Add round and page selection to `history_page`; keep the original `history_items` implementation and compatible signature, and call it per round from `fold_rounds` without moving the folding rules.
2. `fold_rounds()` accepts ordered events or event copies carrying `_seq`; `input_claimed` opens a round, the tool lifecycle merges by `call_id`, and `_load_events` numbers old rows missing `_seq` by their `load_with_seq()` line position.
3. `select_page()` applies `before` as an exclusive boundary, accumulates from newest to oldest, includes whole rounds, and returns an immutable `Page`; single-round over-budget, residual-round, and empty-page cases all need tests.
4. Add `tests/test_history_page.py`, with no HTTP yet; use real `.raw` fragments and synthetic events to cover the 8 boundary classes.

Completion criterion: the existing `history_items` output is unchanged and the new module's `pytest` tests pass.

### 10.2 Step 2: backend interface

1. Change `Inbound._load_events()` to use `load_with_seq()` and keep the `store` injection; with no `store`, it still returns empty rather than raising.
2. Add `before` / `meta` to `Inbound.history()`; `meta` skips folding; the normal path runs `fold_rounds → select_page`.
3. `web_routes.py` parses the parameters: absent `before` is `None`, an invalid `before` returns `ok:false` early, and `meta` is read as a `1` / `0` flag; the adapter receives only validated values.
4. The response adds only optional `page`; `items`, `context_layout`, `todo_list`, and `ok` are unchanged; `meta=1` returns no `page`.
5. Tests: invalid parameters are rejected at the route and do not reach the adapter, `before` is exclusive, `has_more` / `next_before` are correct, old clients ignore `page`, and the `meta=1` shape is correct.

Completion criterion: the old full-history request still returns the complete history; a new request returns one page; SSE and the kernel event endpoint are unchanged.

### 10.3 Step 3: attachment cache merge

1. `ClassicState` gains `merge_attachments(cid, items)`, merging by id without interpreting count/byte policy; `Inbound.history` trims this page's attachments with `ATTACH_REGISTER_MAX_COUNT/BYTES` before the call. Merge and read complete under the same lock.
2. `Inbound.history()` registers this page's attachments through merge; `remember_attachments()` also merges and must not call `put_attachments` again.
3. `get_attachment()` remains the only read entry; `clear_attachments()` still clears on conversation switches.
4. Tests: old ids from two consecutive pages remain readable; the same id is overridden; sending images does not evict loaded pages; exceeding the per-call cap truncates only the incoming batch.

Completion criterion: older pages' images no longer 404 after paging, and sending images does not clear loaded attachments.

### 10.4 Step 4: frontend first screen and state machine

1. Add `historyLoaded:false`, `historyBefore:null`, and `historyState:"idle"` to `makeConversationTab()`.
2. `loadConversationHistory()` no longer sets `historyLoaded` in advance; it sets `loading` before the request, writes the page cursor and state on success, and sets `error` with retry allowed on failure.
3. Keep the current rule that live content in the message area is not cleared; the first screen renders only this page and still scrolls to the bottom.
4. Add `history-paging.js` and register it in `UI_JS_MODULES` (after `chat/conversation.js`; before or after `chat/stream.js` is acceptable, but not before the global functions it depends on).
5. Tests: the first-screen request has no `before`; a missing `page` degrades to the old full render; retry works after failure.
6. The quick-jump button appears when not at the bottom and hides after clicking back to the bottom.

### 10.5 Step 5: paging upward and render isolation

1. Reuse each tab's `trackMsgsBottom` scroll listener; trigger only when `scrollTop<=4` and `historyState==="idle"`; do not re-enter while loading.
2. Add a `wheel` capture listener for "already at the top and still scrolling up"; send `historyBefore`; do not request when `historyBefore===null`.
3. Use `withRenderContext(msgsEl, stepsEl, fn)` to render the older page in detached containers, then preserve the viewport by measuring `scrollHeight`, prepending, and restoring `scrollTop`; do not write the global `msgs` directly.
4. On failure set `error`; the top hint is clickable for retry; any of `has_more=false`, `next_before===before`, or empty `items` sets `exhausted`.
5. Tests: scrolling to the top sends one request; prepending does not jump; no automatic retry after a network drop; the live streaming bubble stays at the bottom during paging.

### 10.6 Step 6: long payloads and summary state

1. Add `LAZY_TOOL_TEXT_CHARS`, `setLazyText()`, and `materializeLazy()` to `chat-tool-views.js`; delay DOM writes only, without changing the paging character budget.
2. Route every long-text entry through `setLazyText()`; the expand delegate calls `materializeLazy()`.
3. Change `refreshConversationContextLayout()` to `?meta=1`; `meta=1` does not trigger `renderHistoryItems` and does not change `historyState`.
4. Tests: a 100,000-character tool result is collapsed on the first screen and expands to full text; `meta=1` adds no `items`.

### 10.7 Step 7: integration acceptance

1. A conversation of about 50,000 characters over 10 rounds: one page on the first screen, cumulative cost at least `10000`, earliest round complete.
2. Page continuously to the earliest page: no duplicates, no missing rounds, and no further requests.
3. A single round with 50,000 characters of tool output: returned whole, collapsed by default, full text on expansion.
4. Refreshing a 10 MB conversation: both the first-screen response and the DOM contain only one page.
5. Paging back while a turn is running: the live bubble stays at the bottom and prepending does not interrupt it.
6. One regression each for attachments, subagent history, invalid `before`, and offline retry.

### 10.8 Delivery boundaries

1. Land the backend pure functions and interface first, then the frontend; each step keeps old clients usable.
2. Add no round index; every request still folds the full log in O(n), and a separate index design is justified only when measured first-screen latency is unacceptable.
3. Perform no viewport virtualization and do not unload loaded old pages; both would enlarge the DOM lifetime and the cache-eviction surface.
4. The English and Chinese documents are maintained in sync.
