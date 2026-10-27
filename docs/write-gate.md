**English** | [中文](write-gate.zh.md)

# Write gate: design intent and current flow

The actual behavior and design intent of the write gate are as follows. The authoritative implementation is in `agent/mechanisms/quality/` (entry points `QualityGate` / `build_pipeline_gate`); the conclusion tool is `agent/capabilities/builtin/review_conclusion.py`.

Related code:

| Location | Role |
|---|---|
| `QualityGate.check_write` | Decides allow or reject before a commit, in a fixed order |
| `QualityGate.confirm` | Stamps a preview with the real-write count at that moment |
| `QualityGate.review_done` | Clears the post-write reminder bookkeeping and closes the patch gate |
| `QualityGate.note_committed` | Records a successful commit |
| `review_conclusion` | On a non-cancel call, confirms the preview (when a `confirm_id` is given), then calls `review_done` |
| `build_pipeline_gate` | After a successful `commit_write`, passes the result's main path (not other files) to `note_committed` |

## Design intent

Writes follow preview → `review_conclusion` → `commit_write`. This is **not** a compliance or audit requirement: no external rule constrains whether the model gets a write right on the first attempt or on the hundredth. The gate aims to make the model **use as few tools as possible and get the write right in one pass**: see what will be written first, pass through a review step, then let it land.

`pending_review` / `reviewed_ok` are a **session-level soft reminder**, not a requirement to re-read the file that was just written at the correct path:

- Turn it on after a real write succeeds: remind the model that the file changed and to watch line numbers and context.
- Any successful non-cancel `review_conclusion` call (whichever preview it reviews, whatever the conclusion says) calls `review_done` and turns it off.
- Delivering the reminder is enough. Most models become more careful; if a particular model reviews another file to clear the check, that does not affect the reminder's role — it is not designed around "the reviewed object must be correct".
- Therefore, **recording "watch after a write" in one global state is intentional**; binding it to `confirm_id` or a path would change the friction cost of the soft reminder.

Hard constraints and soft reminders are separate:

| Layer | Example | Nature |
|---|---|---|
| Hard constraint | No commit without `confirm`; `confirm_id` is single-use; a path written just before cannot be committed again without `read` (when the preview path is the target file); a post-write red light limits the paths that may be changed | Blocks wrong writes and blind edits |
| Soft reminder | `pending_review` / `reviewed_ok` / any review clears the global reminder | Lowers friction and prompts the model to notice changes |

## Current state

These fields are session-scoped, not recorded per file:

| Field | Meaning |
|---|---|
| `_pending[confirm_id]` | One preview snapshot. `confirmed` means reviewed; `confirmed_generation` is the real-write count at review time. On registration only the latest preview with the same snapshot path is kept; the cap is `MAX_PENDING_PREVIEWS` (100), and when full the oldest registration is evicted. |
| `_write_generation` | Number of successful commits, starting at 0. |
| `pending_review` | Paths used by the post-write soft reminder (main paths from real writes since the last clear; the whole list is cleared when the reminder is turned off). |
| `reviewed_ok` | When false, a cross-file commit requires a preceding `review_conclusion` call (unless the preview was unlocked before the latest successful commit). |
| `needs_reread` | Paths just written that must be `read` before they are changed again (hard constraint). |
| `apply_patch_pending` | Whether an `apply_patch` has landed and has not been cleared by `review_done`. |
| `pending_diagnose_red` / `fixable_paths` | When a post-write red light is on, only the listed paths may be changed (if the list is empty, `pending_review` is used instead). A successful commit adds its main path to `fixable_paths`; the list is cleared by `review_done` once no red light remains. |

`review_conclusion` has a fixed order:

1. When `cancel_preview` is true and `confirm_id` is present, only that preview is discarded and the call returns: no confirmation, no `review_done`. Without `confirm_id`, cancel has no effect and the call proceeds as a review.
2. With `confirm_id`, `confirm`: the snapshot is marked reviewed and `confirmed_generation` is set to the current real-write count.
3. On a non-cancel call, regardless of which file was reviewed, `review_done` is called: `pending_review` is cleared, `reviewed_ok = True`, `apply_patch_pending = False`. The large-delete red light is also cleared. Diagnostic red lights (syntax, JSON failure) are not cleared by this call. If no red light remains, `fixable_paths` is cleared as well. This is the soft reminder's off switch, not "only the reviewed preview is authorized".

`note_committed` after a successful `commit_write`:

1. `_write_generation` is incremented.
2. Content tools (`write_file`, `replace_in_file`, `apply_patch`, `read_write`, `file_undo`) add the main path to `needs_reread`. Delete, move, and copy do not require a re-read.
3. The main path is appended to `pending_review`, and `reviewed_ok` is set to false (turning the post-write reminder on).
4. When the tool name is `apply_patch`, `apply_patch_pending` is set to true.

The main path is also added to `fixable_paths`. The path used for bookkeeping comes from the commit result's `path`. For `apply_patch`, that `path` is the first target file in the patch; the remaining files in the same patch do not enter `pending_review`, `needs_reread`, or `fixable_paths`.

A preview snapshot's `path` is resolved from the tool's declared `write_path_keys`. `apply_patch` declares `path`, which is the patch root directory, so the pre-commit checks compare the root directory, not the target files; the commit result's top-level `path` is the first target file.

## Pre-commit decision order

`check_write` returns on the first match and does not evaluate later rules. The pipeline also applies a Plan/Execute mode gate before `check_write`; the list below is only the `check_write` order.

1. `confirm_id` does not exist or was consumed: reject.
2. The preview is not `confirm`ed: reject; the message requires `review_conclusion` first.
3. No path can be resolved from the snapshot: reject.
4. The intent is troubleshooting or debugging and there is no read-only evidence yet: reject.
5. A post-write red light is on and the snapshot path is not in `fixable_paths` (if that list is empty, `pending_review` is used instead): reject.
6. `pending_review` is non-empty and `reviewed_ok` is false, the snapshot path is not in that list, and the preview was not unlocked before the write: reject, with the message "the review of the last real write is not complete".
7. The tool is `apply_patch` and `apply_patch_pending` is true, and the preview was not unlocked before the write: reject, with the message "the last real `apply_patch` write has not been reviewed".
8. The snapshot path is in `needs_reread`: reject; require `read` first.
9. A single `replace_in_file` replacement exceeds the size rules (`MAX_DIFF_LINES`, 80): reject.
10. Otherwise allow.

The "unlocked before the write" test: `confirmed_generation` is an integer and is strictly less than the current `_write_generation`. If the review happened before the latest successful commit, the condition is true. If it happened after that commit, the stamped count equals the current count and the condition is false.

`_in_paths` decides whether two paths count as "the same file": equal after normalization, or one is the other with a `/`-prefixed suffix. `bar.txt` and `foo/bar.txt` are treated as the same path. `_in_paths` is used by the cross-file reminder (step 6) and the red-light scope (step 5); the re-read check (step 8) compares the snapshot path exactly.

## Four single-file chains

Below, A and B are two unrelated paths, and the tool is a `write_file`-style entry that writes one file at a time.

| Order | Current result | Why it is allowed |
|---|---|---|
| Preview A → review A → preview B → review B → commit A → commit B | Pass | Both stamps are applied before any real write. Committing A sets `reviewed_ok` back to false; when B is committed, its stamp still predates that real write. |
| Preview A → review A → preview B → commit A → review B → commit B | Pass | B is reviewed after committing A. B's own stamp does not predate that real write; reviewing B calls `review_done`, which clears the post-write reminder, so committing B is allowed. |
| Preview A → preview B → review A → review B → commit A → commit B | Pass | Same as the first row: both are stamped before any real write. |
| Preview A → preview B → review A → commit A → review B → commit B | Pass | Same as the second row: the review call clears the reminder. |

Submitting an unconfirmed preview is still rejected. For a tool whose preview path is the target file (such as `write_file`), committing the same path again without `read` is blocked at step 8; this is a different rule from the four rows above. Because the `apply_patch` preview path is the patch root directory, step 8 does not hit its target files.

Reviewing C (any preview) after committing A also clears the reminder: this is the intended behavior of the soft reminder, not "C wrongly performed a path-level review for A".

## Current behavior with batched changes

One `apply_patch` is one `confirm_id`, one review, and one commit. The gate performs one check before this commit; the multiple files inside the patch do not each pass through `check_write`.

After a successful commit:

- `pending_review`, `needs_reread`, and `fixable_paths` gain only the first target file.
- `apply_patch_pending` becomes true. This flag does not record which files the patch changed; every later `apply_patch` consults it until a `review_done` (the same off switch as the post-write soft reminder).
- The post-write quality report covers only the main path.

Because the preview snapshot's path is the patch root directory, while `pending_review` and `needs_reread` hold the first target file, steps 5, 6, and 8 compare the root directory, not the file. In practice `_in_paths(root, ...)` is false, and the root does not equal a file in `needs_reread`.

As a result, the second file from the same patch can be changed immediately with another preview; the re-read check does not block it. A separate patch that was already reviewed before this real write satisfies the generation condition, so steps 6 and 7 are both skipped. A patch reviewed after this real write goes through `review_conclusion`, which calls `review_done` and clears the conditions for steps 6 and 7, so it can be committed subject to the remaining checks; if only `confirm` is called without `review_conclusion`, step 6 rejects it first, and the patch-specific wording at step 7 is not reached — the preview path is the patch root, which does not equal the file in `pending_review`.

For `file_ops`, the bookkeeping path is the first non-empty value in the order `dest`, `source`. The other end of a move is not recorded. These operations do not enter `needs_reread`, but they still set `reviewed_ok` back to false.

## Behavior consequences (by design, not defects)

### Reviewing any preview clears the post-write reminder

After a successful non-cancel review, `review_conclusion` calls the global `review_done`. In chains 2 and 4, committing B succeeds because of this clear. After committing A, reviewing C also allows C to be committed — because the reminder has been cleared, not because the system decided that "C reviewed A".

The soft reminder only requires the review step to happen; it does not require the reviewed object to match the file just written.

### A stamp can bypass a later reminder

`confirmed_generation < _write_generation` compares counts only. A preview stamped before a real write can skip the reminder checks at steps 6 and 7 when it is committed. This is consistent with "commit a batch of already-reviewed previews consecutively", and it also lets a preview that was stamped early, followed by other writes, and left uncommitted still commit while the reminder is on — a result of the generation rule, not a path-level audit.

## Adjustable points

The three items below are independent of the global soft reminder and do not change its session-level design.

### A patch records only the first file

The other files written by the same `apply_patch`:

- are not in `needs_reread`, so changing them later does not require reading the current content first (`needs_reread` is a hard constraint; this narrow bookkeeping can affect "read before changing a file that has already landed");
- are not in `pending_review` (this has little effect on the soft reminder: the reminder is not tied to "the reviewed path must be correct");
- are not covered by the post-write syntax, JSON, or large-delete checks.

In addition, the `apply_patch` preview path is the patch root directory, and step 8 compares it for exact equality with `needs_reread`; even if the main path has entered `needs_reread`, the next `apply_patch` is not blocked by the re-read check. Only a tool whose preview path equals the target file is hit.

A more complete bookkeeping approach would put every path in the result's `files` into `needs_reread` and the post-write checks, and resolve the preview path per target file. Whether the patch gate remains a global boolean can be decided separately, but "any `review_conclusion` clears the reminder" stays unchanged.

### The two rules overlap, and the second is rarely reached

The post-write reminder at step 6 and the patch gate at step 7 use the same "unlocked before the write" test. If another file is only confirmed after the write (without a `review_conclusion` call), step 6 rejects first, so the step 7 message is not reached in this case. Reading the rejection reason, one would think only the cross-file reminder applies and miss that the patch gate is also on. Merging the messages or hints would solve this; the state model does not need to change.

### Paths are matched as the same file by suffix

`_in_paths` treats `bar.txt` and `foo/bar.txt` as a hit. The cross-file reminder (step 6) and the red-light scope (step 5) may therefore mix up different files; the re-read check (step 8) compares exact paths and does not use `_in_paths`. For the same path with different slashes, normalized full-path equality is sufficient; whether to remove suffix matching can be evaluated separately.

## Modification constraints

- `pending_review` / `reviewed_ok` stay session-scoped: requiring a review of a specific path or `confirm_id` to clear the reminder would change the soft reminder's friction cost.
- `review_conclusion` still calls `review_done` after unlocking a preview; removing that step would require another mechanism to clear the post-write reminder while keeping friction low.
- The three-step sequence serves "use fewer tools, write correctly" and "remind the model to notice file changes"; it does not carry compliance or audit responsibility.

Hard constraints (`needs_reread`, diagnostic red lights, no commit without `confirm`, patch multi-file bookkeeping) and the soft reminder are evaluated in separate layers and are not coupled.
