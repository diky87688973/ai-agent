**English** | [中文](cli-confirm-backlog.zh.md)

# CLI two-stage confirmation backlog

Status: pending.

## Scope

`agent/shell/cli/interactive.py` currently handles write-preview confirmation only:

```text
write preview → _ask_confirm → gate.confirm(confirm_id) → commit_write
```

When a tool emits `tool_suspended` for `user_confirm` or `approval_confirm`, the CLI prints `[工具等待确认]` and has no input path for the pending envelope.

## Required changes

```text
read the suspended envelope
show title / confirms / approval options in the terminal
write the chosen value as the tool result for the original call_id
start the continuation turn and clear pending_confirm
```

## Acceptance

```text
user_confirm first stage suspends and records pending_confirm
CLI accepts a choice and writes it as the original call result
the next turn receives the choice without a synthetic user message
cancel and approval agree/reject paths work
no direct tool call with hidden confirm arguments
```
