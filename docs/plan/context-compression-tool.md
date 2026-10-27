**English** | [中文](context-compression-tool.zh.md)

# Context compression tool (paused)

**Status:** Paused; not implemented.

## 1. Goal

Let the model choose low-value rounds and supply a compressed summary. Before the next model request, the context removes those rounds according to a removal list. Threshold compaction remains the fallback.

Difference from threshold compaction:

```text
Tool compression: the model chooses arbitrary rounds by current value
Threshold compaction: prefix fallback when over budget, without value judgment
```

## 2. Boundaries

- The tool can select any historical round; the selection does not need to be a contiguous prefix.
- Only the last round is protected. Older rounds, including previously high-value ones, remain selectable.
- The fact log is append-only; removal applies only to the derived context view.
- A tool call only records a compression request. Removal and summary injection happen in the compression stage before the next model request.
- The summary is supplied by the model in the tool arguments; the query interface does not generate summaries.
- Rounds removed by threshold compaction enter the same removal list.

## 3. Round IDs

A round ID comes from the `_seq` of the first `input_claimed` event in that round:

```text
round_id = "r_" + str(_seq)
```

The model-visible form is a prefix on the user message:

```text
[r_102] User text
```

Rules:

- The prefix is added only while assembling the model request; it is not written into conversation facts.
- Only rounds that begin with a real user input get a prefix. System notices, sub-conversation messages, and tool-fed messages do not fabricate round IDs.
- The UI reads the original fact content and does not display the prefix.
- Prefixes on older rounds are stable; new rounds append at the tail, without a per-request front index.
- The model sees the ID next to the round body and copies that ID into `compress`.

## 4. Context shape

```text
[system prompt][skills][summary][knowledge][r_101 a][r_102 b][r_103 c][current round][suffix]
```

After compressing b:

```text
[system prompt][skills][summary + b summary][knowledge][r_101 a][r_103 c][current round][suffix]
```

The bodies of a and c stay unchanged; b's body no longer enters the derived view.

## 5. Compression tool

Tool name: `compress`.

Arguments:

```json
{
  "round_ids": ["r_102"],
  "summary": "Final constraints, conclusions, conflict resolutions, and open items from round b"
}
```

The tool description must state:

- Listed rounds are removed from subsequent model context.
- `summary` is inserted as a system summary message in the front section of the context.
- Only rounds that still exist and are not the last round may be selected.
- Argument IDs must come from current user-message prefixes.

The tool only records the request; it does not modify the fact log.

## 6. Compression stage

`CompressModule` runs before each model call:

```text
read pending compression requests
  → validate round_ids, last round, summary shape
  → add round IDs to removed_rounds
  → remove those rounds from the full derived view
  → append summary to the summary area
  → write a context_compacted event
  → recompute the effective context

still over threshold
  → run prefix threshold compaction
  → add the compressed round IDs to removed_rounds too
```

The tool request takes effect before the next model request; an already-issued request is not changed retroactively.

## 7. View and persistence

- `removed_rounds`: a monotonically growing set union of removed round IDs.
- `summaries`: tool summaries and threshold summaries each become system summary messages.
- `context_compacted` persists `removed_rounds` and the summaries; restoring them rebuilds the view.
- A removed round cannot be selected again.
- A repeated request for the same round is treated as already removed and does not append another summary.
- Physical facts and raw conversation records remain for recovery and audit.

## 8. Protection and validation

```text
The last round cannot be removed
Tool calls / tool results in the current round are not separate rounds
Unknown round_id → reject the whole request
Empty summary → reject
Summary over the length limit → reject
The summary is written into the system area; it does not replace system prompt, skills, or knowledge
```

A validation failure changes no `removed_rounds`, writes no summary, and does not trigger threshold compaction.

## 9. KV cache

- Round ID prefixes belong to their user messages; old message content does not change when new rounds arrive.
- No per-request front round index is introduced.
- Tool compression changes the derived view; the common prefix from the first removed round onward is invalidated, which is the cost of compression itself.
- Threshold compaction invalidates from its own compression point without adding index invalidation.

## 10. Not implemented

```text
compress tool
compression request events
removed_rounds derived view
user-message round prefix injection
summary-area merging
manual branch in CompressModule
restore and UI presentation
unit tests and real-session acceptance
```

The corresponding rule is paused: `rules/CONTEXT_CLEANUP_RULES.md.paused`.
