**English** | [中文](silent-exceptions.zh.md)

# Silent exception governance

## 1. Goals

Exception handling gives every failure a definite owner instead of turning the gate green:

- the caller knows which state a failure produces;
- the runtime surface can see the failure;
- recovery is limited to the local scope;
- tests cover the failure path.

Target state:

```text
except Exception / BaseException + pass/continue: 0
silent except without a report: 0
IDIOMS regex exemption table: 0
silent-exception budget: 0
```

## 2. Permitted exception handling

### 2.1 Narrow catch and explicit recovery

```python
try:
    text = path.read_text(encoding="utf-8")
except (OSError, UnicodeDecodeError) as exc:
    report_error("config.read", exc, path=str(path))
    return None
```

Requirements:

- catch the narrowest type that covers the failure;
- the return value is a definite state the caller understands;
- a failure is never disguised as empty data without a trace.

### 2.2 Batch item-by-item handling

```python
except (OSError, ValueError) as exc:
    report_error("batch.item", exc, item=str(item))
    continue
```

`continue` is allowed only after a report; a bare `continue` is not.

### 2.3 Cleanup and close

```python
with contextlib.suppress(OSError):
    handle.close()
```

Only a specific exception type is allowed; `suppress(Exception)` is forbidden.

### 2.4 Plugin and request boundary isolation

```python
except Exception as exc:
    report_error("plugin.load", exc, plugin=name)
    return PluginUnavailable(name)
```

A wide catch is allowed only at an isolation boundary, and must do one of the following:

- report the failure, then return a definite state;
- convert it into a definite result object, such as an assignment of `ToolResult(ok=False, error=...)`;
- wrap it and re-raise.

### 2.5 Last-resort fallback

When the logging system itself fails, one centralized, narrow fallback function is allowed:

```python
def write_stderr(message: str) -> None:
    try:
        os.write(2, message.encode("utf-8", "replace"))
    except OSError:
        return
```

Business code does not copy this fallback.

## 3. Forbidden forms

```python
except Exception:
    pass

except Exception:
    continue

except BaseException:
    pass

except Exception:
    return None
```

The last form is forbidden only for a wide catch without a report; a narrow catch may return an explicit default.

Comments are not an exemption. Labels, regexes, and budgets are not exemptions.

## 4. Policy per layer

| Layer | Policy |
|---|---|
| `agent/core` | Fail fast when an invariant breaks; optional capabilities use a narrow catch with an explicit state |
| `agent/mechanisms` | Authoritative state writes are never silent; logging, metrics, and other side channels may degrade but must report |
| `agent/capabilities` | Tool failures become definite tool errors; batch processing reports each item |
| `agent/shell` | Request boundaries become user-visible errors; disconnects and empty queues are explicit control flow |
| `plugins` | Plugin failures are isolated, then reported, disabled, or skipped; the main flow is unaffected |
| `scripts` / `tests` | Only a narrow catch with a trace on stderr, or `suppress(SpecificError)` |

## 5. Gate

`scripts/check_silent_except.py` performs AST structure checks only: it reads no regex table and no budget. It scans `.py` files under `agent/`, `tests/`, `scripts/`, and `plugins/`, skipping paths that contain `__pycache__` or `retired`.

1. An `except` body that contains `pass`, or whose only statement is `continue`: fail.
2. A bare `except`: fail.
3. A wide catch — `Exception`, `BaseException`, or a tuple containing either — with no report and no conversion: fail. This includes a handler whose only statement returns or assigns a constant default such as `None` or an empty container.
4. A narrow catch with an explicit return: allowed.
5. `contextlib.suppress(SpecificError)`: allowed; `suppress(Exception)` and `suppress(BaseException)`: fail.
6. The `write_stderr` fallback: allowed.

A report is `report_error(...)` with at least two positional arguments, `write_stderr(...)` with at least one positional argument, or `print(..., file=sys.stderr)`. A conversion is a `raise` or an assignment of a `ToolResult(...)` call; a bare `return ToolResult(...)` is not recognized as one.

The script prints the scanned file count and the checked handler count, then a success marker, and exits 0. Each problem is printed as `[FAIL] path:line reason` and the script exits 1; a file that does not parse is reported as a syntax error at its line. Every failure line names the file, the line number, and the violation reason.

## 6. Remediation order

Order remediation by failure impact, not by file name:

1. Core data and state: `session_store`, `run_registry`, `file_safety`, `fspaths`, `session_title`.
2. Persistence and queues: model registry, metadata, log rotation, session queue.
3. External input parsing: JSON, config, encoding, paths.
4. Side channels: progress, metrics, optional capabilities, cleanup.
5. Tests and acceptance scripts.

After each batch:

- run the affected module's unit tests;
- run `check_silent_except.py`;
- check that the failure paths have tests;
- update this document or the quality gate docs.

## 7. Acceptance

```text
python scripts/check_silent_except.py
python -m unittest tests.test_silent_except_gate
python -m unittest tests.test_gate_negative
```

Required:

- zero silent `pass`/`continue`;
- no `IDIOMS` table;
- no budget constant;
- every gate negative case fails as expected;
- critical persistence paths have fault-injection tests;
- full CI passes (run only on request).

## 8. Rollback

Roll back per file batch, not as a whole-tree revert:

- back up the original file before each batch;
- each batch changes only exception handling and the matching tests;
- on a behavior regression, restore that batch's original files, then narrow the change;
- do not revert other batches that already passed.

## 9. Acceptance results

```text
files scanned: 400
except handlers checked: 698
silent pass/continue: 0
IDIOMS table: absent
silent-exception budget: absent
```

`tests.test_silent_except_gate` and `tests.test_gate_negative` pass; the silent-exception negative cases fail the gate as designed.

A wide catch has two permitted exits:

```text
report_error(...) / write_stderr(...)
→ reported

re-raise, or an assignment of an explicit result object
→ definite state
```
