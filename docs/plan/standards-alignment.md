**English** | [中文](standards-alignment.zh.md)

# Standards alignment

> Standard: `production-standards.md` (MUST / SHOULD).
> Scope: existing engineering debt only. The feature plans are [history-paging.md](history-paging.md) and [multi-model.md](multi-model.md).
> All 13 MUST and 2 SHOULD findings from the audit are addressed by the design below; current gate and budget values are in §0.4.

## 0. Conclusions first

### 0.1 Why the alignment comes first

| Feature plan | Property it relies on | Consequence without it |
|---|---|---|
| History paging | `A2`: no dependency cycles | With cycles present, a new module cannot be shown to lie outside them; once they are removed, every new dependency edge has a reference |
| History paging / multi-model | `X5`: coverage counted only `agent/core` and `agent/mechanisms` | New modules under `agent/shell` and `plugins` fall outside every floor, so they are effectively untested |
| Multi-model | `K4`: no concurrency contention job | `ModelCatalog` locks could only be reviewed by eye; atomic replacement had no machine proof |
| Both | `Y1`: `ci.yml` and `ci_steps.py` were not from one source (the coverage step existed only in the yml) | A green local run did not imply a green CI run, or the reverse |
| Both | `D3`: `docs/unit-tests.md` had no drift check | New tests necessarily made the document stale, and nobody noticed |

### 0.2 Findings and their design

| # | Rule | Finding | Severity | Where the design lives |
|---|---|---|---|---|
| 1 | `C5` | Four `assert` statements under `agent/` participated in control flow | MUST | Explicit `RuntimeError` in `agent/core/host.py` and `agent/core/chain.py`; no `assert` remains under `agent/` |
| 2 | `A2` | Two dependency cycles spanning 11 modules | MUST | `agent/entry/` layer; `check_imports.py`; `tests/test_import_graph.py` |
| 3 | `B1` | `PluginSegments.items` / `counts` were mutable lists on a frozen dataclass | MUST | `__post_init__` freezes them to tuples; `tests/test_context_assembly.py` |
| 4 | `X2` | Nine gates had no negative case | MUST | `tests/test_gate_negative.py`, with per-gate tests for the silent-exception and dependency-graph gates |
| 5 | `X5` / `X6` | Coverage was absent from `ci_steps`, had no per-package floors, and missed `agent/shell` and `plugins` | MUST | `scripts/run_coverage.py`, `scripts/check_coverage.py`, `COVERAGE_FLOORS` |
| 6 | `X7` | The acceptance-skip cap equalled the allowlist length, so it could never trigger | MUST | `ACCEPTANCE_SKIP_BUDGET` is independent; `acceptance_skip_problems()` |
| 7 | `E2a` | Silent exception handling had no count, no budget, and no decreasing constraint | MUST | Strict AST gate in `scripts/check_silent_except.py`; no budget by design |
| 8 | `R1` | Files and functions over threshold were held in an exemption registry | MUST | `check_complexity.py` fails on any item; no exemptions |
| 9 | `T4` | Config drifted with no validation; tracked real config had no schema | MUST | `agent/config_schema.py`; `scripts/check_config_drift.py` |
| 10 | `D3` | `docs/unit-tests.md` had drifted and the generator had no `--check` | MUST | `scripts/gen_unit_tests_md.py --check` |
| 11 | `K4` | No concurrency contention job | MUST | `tests/test_concurrency.py`; `-X dev` CI step |
| 12 | `0.5` | No `docs/applicability.md` | MUST | `docs/applicability.md`; `scripts/check_applicability.py` |
| 13 | `Y1` | `ci.yml` and `ci_steps.py` were not from one source; the validator allowed the extra coverage step | MUST | `scripts/gen_ci_workflow.py`; `scripts/check_ci_workflow.py` |
| 14 | `B3` | `Any`-typed interfaces in `agent/core/ports.py` | SHOULD | `Protocol` ports; remaining `Any` uses are JSON payloads or opaque handles |
| 15 | `R2` | A duplicated comment fragment in the pane container | SHOULD | Two-sentence comment in `agent/shell/web/web_assets/classic/js/panels/panes.js`; `check_comment_style.py` |

### 0.3 Order of work

```text
P0 complexity gate skeleton → P1 local defects (assert / immutability / comment / quality cycle)
→ P2 split the shell↔app cycle (introduce the entry layer)  ← feature work can start after this
→ P3 gate hardening (coverage / skip / budget / drift / generated yml)
→ P4 negative cases + concurrency job → P5 close-out (B3 / full acceptance)
```

### 0.4 Current values

| Item | Value | Command |
|---|---|---|
| Pipeline steps | 30: 18 gates, unit tests, 10 acceptance scripts, per-package coverage | `python scripts/ci.py --list` |
| Dependency cycles | 0 groups | `python scripts/check_imports.py --scc` |
| Silent exceptions | 0 violations (400 files, 698 handlers) | `python scripts/check_silent_except.py` |
| Applicability declarations | 0 of 95 rules (N/A 0.0%) | `python scripts/check_applicability.py` |
| Test cases | 1985 | `python scripts/check_readme.py` |
| Config drift | Real files are a subset of the schema | `python scripts/check_config_drift.py` |
| Coverage floors | 10 packages | `scripts/quality_budgets.py` |
| Generated workflow | Byte-identical to the rendered step list | `python scripts/check_ci_workflow.py` |

## 1. Audit method (reproducible)

All commands run from the repository root; the numbers in this document come from them.

```bash
# dependency cycles: runtime imports only; imports inside `if TYPE_CHECKING:` are skipped
python scripts/check_imports.py --scc

# assert
rg -n "\bassert\b" agent --glob "*.py"

# complexity
python scripts/check_complexity.py --list

# silent exceptions
python scripts/check_silent_except.py

# generated docs and workflow
python scripts/gen_unit_tests_md.py --check
python scripts/gen_complexity_md.py --check
python scripts/check_ci_workflow.py

# tracked config files
git ls-files "*.ini" "*.example"
```

### 1.1 Import graph resolution rules

The rules are fixed before counting, otherwise the cycle count changes with the implementer's taste.

| Form | Edge target | Reason |
|---|---|---|
| `import a.b.c` | `a.b.c` | Direct module dependency |
| `from a.b.c import name` | `a.b.c`; plus `a.b.c.name` when that is a module | The name may be a submodule |
| `from a.b import sub` where `a/b/sub.py` exists | `a.b` and `a.b.sub` | Python imports the submodule, and the package `__init__` also runs |
| `from a.b import symbol` | `a.b` (the package `__init__`) | The package initializer really runs at import time |
| Inside `if TYPE_CHECKING:` | **No edge** | Type-only; not loaded at runtime, but it must really be used only for annotations |
| `try: import x` / `except ImportError:` | Edge | An optional dependency is still a dependency direction |

Under these rules, `classic_adapter/__init__.py → adapter.py` and `adapter.py → contract.py` are one-way and do not form a cycle.

### 1.2 Measurement

The audit found two cycles: the `quality` package (`__init__`, `gate`, `pipeline_bridge`) and the shell/assembly-root group (`agent.app`, the classic adapter's `__init__` / `adapter` / `inbound` / `outbound`, and the web shell's `web`, `web_api`, `web_routes`). Neither cycle remains; `--scc` reports **0 groups**. §2.2 records the design that removes them.

## 2. MUST findings

### 2.1 `C5`: no `assert` in control flow

**Rule.** `assert` is a development-time invariant; it must not carry runtime control flow, because `python -O` removes it.

| Pattern | Why it fails |
|---|---|
| `assert result is not None`, then store `result` | Under `-O` the check disappears and `None` is stored; the error surfaces later at an attribute access |
| `assert self.last_result is not None` before returning it | Same; under `-O` `None` continues down the call path |
| `assert isinstance(outcome, Outcome)` after a validator already checked it | Duplicate check; the validator raises `TypeError` naming the module |
| `assert self.result is not None` before returning it | Under `-O` a wrong type is returned |

The root cause is treating an internal invariant as input validation while assuming the interpreter is not run with `-O`.

**Design.**

1. `agent/core/host.py` checks the result after iteration and raises `RuntimeError` naming the conversation and pass; `run_iter` records an `abandoned` result when the consumer stops early, so a finished iteration always leaves a result.
2. `agent/core/chain.py` validates the module outcome through `_require_outcome`, which raises `TypeError`; `drain()` raises `RuntimeError` when the chain ended without an `Outcome`.
3. `agent/` contains no `assert`. The architecture hygiene gate does not have a dedicated `assert` rule; the invariant is held by the audit command and by running the affected tests under `-O`.

**Verification.** `rg -n "\bassert\b" agent --glob "*.py"` returns no hits; `python -O -m unittest tests.test_core` passes.

**Risk.** Low. Under `-O` the behavior changes from silent continuation to an explicit error, which is the intended correction.

### 2.2 `A2`: remove dependency cycles

The standard requires a machine-provable zero cycles. A function-local import hides an edge but does not remove it: if the graph models call time, the strongly connected component still contains it. The fix is a layer change.

#### Cycle 1: the `quality` package

**Cause.** `from package import submodule` executes the package `__init__` first, and the `__init__` imports `gate`, so `gate`'s own imports close the cycle. `pipeline_bridge` is pulled into the same component by the re-entry.

**Design.** Import the submodules by absolute module path, not through the package namespace:

```python
import agent.mechanisms.quality.checks as _checks
import agent.mechanisms.quality.diagnose as _diagnose
```

This binds the submodules without re-running the package initializer. `checks.py` and `diagnose.py` reference `QualityGate` only under `TYPE_CHECKING`; that stays as is.

**Verification.** `check_imports.py --scc` does not list the group; `python -c "import agent.mechanisms.quality"` succeeds; the quality gate unit tests pass.

#### Cycle 2: `shell` ↔ `app`

**Cause.** Three upward edges closed the cycle; the fourth is the composition root's correct downward edge:

| Edge | Purpose |
|---|---|
| shell web → `agent.app` | `build_shell_app()` and `__main__` startup |
| `web_api` → `agent.app` | Type annotation only |
| classic adapter inbound → shell web (function-local import) | Reuse of `date_group` |
| `app` → shell | Composition root, direction correct by design |

The function-local import hid the cycle, which the standard forbids. The adapter reached into the web API for `date_group`; that function is a dependency-free utility, and forwarding it was a duplicate implementation.

**Design (the `entry` layer).**

1. Add a top-level `agent/entry/`, which only assembles and starts a process. It may depend on `agent.app` and `agent.shell`; no lower layer may import it.
   ```text
   agent/entry/web.py       # build the app, then agent.shell.web.server.serve(app, ...)
   agent/entry/cli.py       # build the app, then the interactive CLI main
   agent/entry/headless.py  # build the app, then the headless main
   ```
2. `agent/shell/web/server.py` keeps `serve(app, ...)` and `create_server(app, ...)` and does not import the composition root.
3. `agent/shell/web/web_api.py` annotates `App` under `TYPE_CHECKING` with a string annotation. The shell never performs `isinstance(x, App)`; a runtime check uses a protocol, and a runtime import kept only for an annotation is not allowed.
4. `date_group` lives in `agent/shell/timefmt.py` (a pure function with no internal dependencies). The classic adapter's session module and the web session list both import it. The adapter does not forward the web API's private function, and no private re-export is kept.
5. The interactive CLI and the headless shell take a ready app: `agent/shell/cli/interactive.py` exposes `build_session(argv, app=...)` and `main(argv, app_factory=...)`; `agent/shell/cli/headless.py` exposes `run(app, text)` and `main(argv, app_factory=...)`. `agent/entry/*` constructs the app.
6. `LAYERS` becomes `("core", "mechanisms", "capabilities", "shell", "entry")` in both `check_imports.py` and `check_architecture_hygiene.py`; `entry` may only point down. `COMPOSITION_ROOTS` is `{"app", "entry"}`: `app` may import any layer, and no lower layer may import either root at runtime.
7. Startup uses `python -m agent.entry.web`; `start.bat`, `start.sh`, the README, and `docs/subsystems/shell.md` change in the same step.

**Verification.**

- `python -m agent.entry.web --host 127.0.0.1 --port 8765` starts the service; the home page and `/api/chat/history` work.
- `python scripts/check_imports.py --scc` → 0 groups.
- `python -m agent.entry.headless` smoke test; the web acceptance script passes.
- Importing `agent.shell.web.server`, `agent.shell.cli.interactive`, and `agent.shell.cli.headless` does not load `agent.app` (`sys.modules` assertion); `tests/test_import_graph.py` pins both directions.

**Risk.** Medium. The entry path is user-visible (`start.bat`). Following `R5`, there is no compatibility layer for the old command: scripts, README, and subsystem documentation change together.

### 2.3 `B1`: deep immutability of `PluginSegments`

**Rule.** A frozen dataclass must not expose mutable containers.

**Violation.**

```python
@dataclass(frozen=True)
class PluginSegments:
    items: List[Tuple[str, str, str]] = field(default_factory=list)
    counts: List[int] = field(default_factory=list)
```

`frozen=True` freezes field binding only; `items.append(...)` still mutates the object. This is the "tuple on the surface" problem the standard names.

**Design.** The fields are `Tuple[Tuple[str, str, str], ...]` and `Tuple[int, ...]`, defaulting to `()`. `__post_init__` copies every entry into a tuple and validates the `(key, label, body)` shape, raising `ValueError` for a wrong shape. Callers may pass lists; the stored value is always a tuple. Body elements stay as they are, because the assembly side may expand them.

**Verification.** `tests/test_context_assembly.py` (`PluginSegmentsImmutableTest`): mutating the source list after construction does not change the object; `segments.items.append(...)` raises `AttributeError`; `segments.counts[0] = 9` raises `TypeError`; a two-part entry raises `ValueError`.

**Risk.** Low. Only post-construction mutation changes behavior; constructor call shapes are unchanged.

### 2.4 `X2`: gate negative cases

A gate that is only tested against the current clean repository is not tested: a checker that returns `[]` unconditionally would pass. Each gate therefore gets a minimal input that must fail and a valid input that must pass.

**Design.** Every gate module separates judgment from I/O: the judgment lives in functions that take a path, text, or measured data, and `main()` only reads/writes files and sets the exit code. The input shape decides the function name, so the modules are consistent without sharing one signature:

| Gate | Testable entry point |
|---|---|
| `check_imports.py` | `check(package_root)`; `cycles()` backs `--scc` |
| `check_architecture_hygiene.py` | `check(...)`, plus one function per rule (`check_cross_layer_private_imports`, `check_kernel_plugin_names`, ...) |
| `check_silent_except.py` | AST predicates (`_broad`, `_only_pass_continue`, `_reports`, `_transforms`, `_broad_suppress`) and `main()` over a patched root |
| `check_readme.py` | `check(readme, acceptance, tests, data_dirs, steps, gates)` |
| `check_comment_style.py` | `scan_text(text, suffix, rules)` |
| `check_ci_workflow.py` | `check()` |
| `check_python_floor.py` | `_violations(tree)` |
| `check_ui_js.py` | `_undefined_called(text)`, `model_id_literals(text)` |
| `check_confirm_wording.py` | `check_texts(texts)` |
| `check_acceptance_skips.py` | `acceptance_skip_problems(names)` in `ci_steps.py` |
| `check_config_drift.py` | `compare_subset`, `compare_plugin_model_real`, `compare_model_example` |
| `check_applicability.py` | `check(text, known_ids)` |
| `check_complexity.py` | `check(root, docs, ...)` |
| `check_coverage.py` | `check(measured, floors)` |
| `check_catalog.py` | `check(catalog_path)` |
| `check_secrets.py` | `scan_text(text)` |
| Generated docs | `gen_unit_tests_md.main(["--check"])`, `gen_complexity_md.build()` / `main(["--check"])` |

Negative cases live in `tests/test_gate_negative.py`, with additional suites in `tests/test_catalog.py`, `tests/test_silent_except_gate.py`, and `tests/test_import_graph.py`. They build temporary directories or strings and never modify a repository file; assertions require a non-empty result and, where the gate prints a location, that the message carries it.

**Acceptance.** Every covered gate has at least one failing and one passing input. `check_secrets.py` scans tracked files; it is not part of the negative-case matrix in §6.

### 2.5 `X5` / `X6`: coverage

**Rule.** Coverage is enforced per top-level package, over all shipped Python code, from one threshold source.

**Design.**

1. `scripts/run_coverage.py` runs the suite with `--branch --source=agent,plugins --omit=*/web_assets/*`, writes `.coverage.tmp.<pid>`, then publishes `.coverage` with `os.replace` under `.locks/coverage.lock`. A reader sees either the complete old file or the complete new file.
2. `scripts/check_coverage.py` maps measured files to ten groups by path prefix and compares each group against `COVERAGE_FLOORS` in `scripts/quality_budgets.py`.
3. A missing `.coverage` file, an uninstalled `coverage` package, or a data file rewritten during the check returns exit code `2` (SKIP). A SKIP is visible in the CI output and is not counted as a pass. A group with no measured data is a failure, not a skip.
4. `check_coverage.py` reports the per-package table and, on failure, the package, measured value, floor, and statement counts. Coverage is measured once, in the 3.12 matrix; the HTML report is uploaded from there.
5. JS and CSS are outside Python coverage; `check_ui_js.py` covers them.
6. No `fail_under` exists anywhere. The only thresholds are in `quality_budgets.py`; floors may only increase, and a decrease requires a reason plus new tests in the same change.

The floors:

| Package | Floor |
|---|---|
| `agent/core` | 85% |
| `agent/mechanisms` | 80% |
| `agent/capabilities` | 75% |
| `agent/shell` | 70% |
| `agent/entry` | 60% |
| `agent/gui` | 25% |
| `agent/update` | 60% |
| `agent/subagent` | 85% |
| `agent (top-level)` | 90% |
| `plugins` | 60% |

The `agent/gui` floor is low because the desktop shell depends on a platform-bound embedded browser; CI covers only the platform-free branches.

**Verification.** `python scripts/run_coverage.py` then `python scripts/check_coverage.py`; `--print` shows the measured values without judging. A floor violation or missing group fails; the negative cases in `tests/test_gate_negative.py` (`CoverageGateTest`) feed measured dictionaries directly.

### 2.6 `X7`: acceptance-skip cap

**Rule.** The cap on skipped acceptance scripts is independent of the allowlist; a larger allowlist must not relax the cap.

**Design.** `ACCEPTANCE_SKIP_BUDGET = 1` lives in `scripts/quality_budgets.py`; `MAX_ACCEPTANCE_SKIPS` in `ci_steps.py` reads it. The allowlist is `{"acceptance_mvp3"}`. `acceptance_skip_problems(names)` de-duplicates names (after stripping a BOM and whitespace), compares the count against the budget **first**, then checks the allowlist, and returns one message per problem. `check_acceptance_skips.py` reads the names from `ACC_SKIP_FILE`; when the variable is unset it prints the allowlist and the budget and passes, so a local run does not depend on a stale temporary file.

**The value is one.** `acceptance_mvp3` skips by design in CI because real-model acceptance requires explicit enablement. A budget of 0 would keep CI permanently red. One is the only expected skip.

**Verification.** Negative cases: two skips fail against a budget of 1; a non-allowlisted name fails; one allowlisted name passes; duplicate names do not count twice.

### 2.7 `E2a`: silent exceptions

**Rule.** Every failure has a definite owner and leaves a trace. Swallowing an exception is not a design option, so there is no budget and no idiom allowlist.

| Form | Verdict |
|---|---|
| `except Exception:` with `pass`, or whose only statement is `continue` | Fail |
| Bare `except:` | Fail |
| Wide catch (`Exception` / `BaseException`, or a tuple containing either) with no report and no conversion | Fail |
| Wide catch returning or assigning a constant default (`None`, an empty container) without a report | Fail |
| `suppress(Exception)` / `suppress(BaseException)` | Fail |
| Narrow catch with an explicit return | Allowed |
| `suppress(SpecificError)` | Allowed |
| Wide catch at an isolation boundary that reports and returns a definite state, converts to `ToolResult(...)`, or re-raises | Allowed |

**Design.** `scripts/check_silent_except.py` is an AST structural check over `.py` files under `agent/`, `tests/`, `scripts/`, and `plugins/`, skipping `__pycache__` and `retired`. It reads no regex table and no budget; comments are not an exemption. A report is `report_error(...)` with at least two positional arguments, `write_stderr(...)`, or `print(..., file=sys.stderr)`. A conversion is a `raise`, or an assignment whose value is a `ToolResult(...)` call. The policy is documented in [silent-exceptions.md](../silent-exceptions.md).

**Verification.** `python scripts/check_silent_except.py` scans 400 files and 698 handlers with 0 violations; negative cases in `tests/test_silent_except_gate.py` cover `pass`, a multi-statement `pass`, a narrow return, `suppress(Exception)`, a report without a payload, and `main()` over a patched root.

**Risk.** Behavior risk is low: every reported failure already had an explicit result, and the gate only rejects the silent forms. The maintenance cost is that a legitimate cleanup handler must name a specific exception type.

### 2.8 `R1`: complexity thresholds

**Rule.** The thresholds are hard limits: 800 lines per file, 80 lines per function, 40 functions per file. There is no exemption registry.

**Design.** `scripts/quality_budgets.py` holds `MAX_FILE_LINES`, `MAX_FUNCTION_LINES`, and `MAX_FILE_FUNCTIONS`. `scripts/check_complexity.py` scans `agent/`, `scripts/`, and `plugins/` (skipping `__pycache__` and `retired`), fails on any file or function over its threshold, and also fails when `docs/complexity.md` differs from the scan. `scripts/gen_complexity_md.py` generates that document; `--list` prints the current over-threshold items.

| Item | Current |
|---|---|
| Files scanned | 303 |
| Functions scanned | 2527 |
| Files over 800 lines | 0 |
| Functions over 80 lines | 0 |
| Files over 40 functions | 0 |

Exceeding any threshold means splitting the file or function, not registering it.

**Verification.** `python scripts/gen_complexity_md.py --check` shows zero difference; adding one line to an 800-line file fails; `tests/test_gate_negative.py` (`ComplexityGateTest`) covers the over-threshold file and the generated-doc drift.

### 2.9 `T4`: config drift

**Rule.** A real configuration file may only use registered sections and keys. Missing keys fall back to defaults; unknown keys fail.

**Design.**

1. `agent/config_schema.py` is the single list of allowed sections and keys: `SCHEMA` for `config.ini`, `WEB_UI_SCHEMA` for `web-ui-config.ini`, and `MULTI_MODEL_SCHEMA` for the multi-model plugin's `[model:*]` sections. The values are defaults used for documentation and template consistency; reading stays in `config.py`, and a missing key falls back to the caller's default.
2. Both main config files are tracked in the repository, so no separate example is needed: the defaults are in the schema. Only the multi-model plugin config carries credentials; its real file stays local, and a tracked `plugin-config.ini.example` is required.
3. `scripts/check_config_drift.py` compares a real file against the schema as a subset: an unregistered section or key fails, with the key's line number found by a text scan. For the multi-model plugin it checks the real `[model:*]` keys as a subset and the example against the schema in both directions (missing and extra keys both fail).
4. A missing real file prints a `[SKIP]` note (code defaults apply, or the plugin is not configured) and passes. This is the visible skip required by `E5`.

**Verification.** Adding an unregistered key to `config.ini` or `web-ui-config.ini` fails with section, key, and line; an unregistered section fails; an example missing a schema key fails; a missing real file skips and passes. `tests/test_gate_negative.py` (`ConfigDriftGateTest`, `ConfigModelExampleGateTest`) covers each case.

### 2.10 `D3`: generated documentation drift

**Rule.** A generated document must match its source; a readable test index is not maintained by hand.

**Design.** `scripts/gen_unit_tests_md.py` renders `docs/unit-tests.md` from the discovered `unittest` suite (`render()`), and `--check` compares the rendered text with the file, reports a mismatch, and exits 1. `docs/unit-tests.md` currently lists 1985 cases. `scripts/gen_complexity_md.py` provides `build()` and follows the same shape for `docs/complexity.md`. Both checks are gate steps, one per generated document. A change regenerates first, then runs the check.

**Verification.** Deleting any line from the document fails the check; regenerating passes. `tests/test_gate_negative.py` (`GeneratedArtifactDriftTest`, `GeneratedComplexityDocGateTest`) covers drift, a missing file, and extra content.

### 2.11 `K4`: concurrency contention

**Rule.** Shared mutable state needs tests that run real threads and assert invariants, not tests that only observe the absence of a crash.

**Design.** `tests/test_concurrency.py` contains 11 tests over five objects: the preview-snapshot store (`PendingStore`), the context-source registry (`ContextSources`), session live state (`LiveState`), the model catalog (`ModelCatalog`), and the AI-speak runtime. Each starts 8 threads at a barrier and asserts a definite property: the capacity is never exceeded, one latest snapshot per path, take is exactly once, a collect sees a consistent snapshot, a replacement is never mixed, or the provider cache is keyed by the entry fingerprint. Assertions target invariants; the only sleep is a bounded poll for an asynchronous queue to drain, not a way to create ordering.

CI runs the module as its own gate step with `-X dev` (developer mode exposes `ResourceWarning` and unclosed threads), with a 3-minute timeout. The normal unit-test step also runs it, without `-X dev`; both must pass.

**Verification.** Removing the `ModelCatalog` lock makes the contention test fail, which is its negative proof. `python -X dev -m unittest tests.test_concurrency` passes.

### 2.12 `0.5`: applicability declarations

**Rule.** Every standard item is applicable unless it is declared otherwise, with a reason and a risk bearer.

**Design.** `docs/applicability.md` holds a four-column table: rule, declaration, reason, risk bearer. Only non-applicable rows are declared; an undeclared rule remains applicable. `scripts/check_applicability.py` validates the shape and the content:

- exactly four columns; the ID matches the rule-ID pattern and is unique;
- the declaration is `Not applicable`;
- the reason has at least 20 characters;
- the risk bearer is present;
- the ID exists in the set in `scripts/standards_rules.py` (95 declarable MUST / SHOULD IDs); an unknown ID is a stale declaration and fails.

The checker prints the handbook version and a declared/total count with the N/A share, so a rising N/A share is visible. The current table declares nothing: 0 of 95 rules, N/A 0.0%.

**Verification.** Negative cases: an unknown ID, a short reason, and a missing table each fail; a well-formed row and an English-header table with the English declaration pass. Running the check against the real ID set is the end-to-end case.

### 2.13 `Y1`: single source for CI

**Rule.** `scripts/ci_steps.py` is the only step list; the workflow is generated from it, never hand-edited.

**Design.**

1. `CiStep(label, kind, script_key, argv, timeout_minutes)` describes one step. `kind` is `gate`, `unittest`, `acceptance`, or `post`. `catalog(fast)` orders gates, unit tests, acceptance scripts, and the coverage post-step; `--fast` drops the last two.
2. `scripts/gen_ci_workflow.py` renders the whole workflow file. The gate block and the acceptance block come from the step records (name, timeout, command, skip wrapper). The fixed parts — checkout/setup, the per-file unit-test loop, the acceptance-skip file prelude, the coverage step (3.12 matrix only), the report upload, and the `data/` check — are templates in the generator.
3. `scripts/check_ci_workflow.py` re-renders and compares byte for byte. On a mismatch it prints the first differing line with the actual and expected text. There is no `_ALLOWED_EXTRA` and no logic that guesses a step from a script name.
4. The current list is 30 steps: 18 gates, one unit-test step, 10 acceptance scripts, one coverage post-step. `python scripts/ci.py --list` prints it.

**Verification.** Changing any line of `ci.yml` fails the gate and names the line; `python scripts/ci.py --list` and the workflow contain the same step set. `tests/test_gate_negative.py` (`GeneratedArtifactDriftTest`) appends a line to a rendered workflow and asserts the failure.

## 3. SHOULD findings

### 3.1 `B3`: typing in `ports.py`

**Rule.** Module-facing capabilities are typed by `Protocol`; `Any` is reserved for values that are genuinely JSON-shaped or opaque.

**Design.** `agent/core/ports.py` defines `ProviderPort` (`model`, `stream`), `RegistryPort` (`schemas`), `PipelinePort` (`execute`), `SessionsPort` (`resolve_sync`), `ProgressSink`, and `CancelCheck`. `ModelPort` and `ToolPort` depend on these protocols. `Any` remains in eleven uses, all of one of three kinds: JSON payload shapes (`Dict[str, Any]`, message and tool-declaration lists), the process-level application/session handle, and event payloads. No new type checker is added to CI.

**Verification.** `rg -c "\bAny\b" agent/core/ports.py` reports 12 lines: the import plus eleven uses, all in the categories above; the protocol classes are covered by the existing core tests.

### 3.2 `R2`: comment text

**Rule.** A comment explains why the code is the way it is, not what the code does; fragments and duplicates fail.

**Design.** The pane container's comment is two sentences: tabs and panels are driven by `data-pane`, and a plugin-injected panel carries only that identity, so traversal must follow the data. That states the reason a new panel needs no change in this module instead of restating the loop.

**Design check.** `scripts/check_comment_style.py` rejects leftover memos, instructions to or about the reader, correction history, version phrasing, design defense, and Markdown emphasis in comments. It reads comments and docstrings, not string literals or code; a clean comment passes.

**Verification.** `python scripts/check_comment_style.py` passes; `tests/test_gate_negative.py` (`CommentStyleGateTest`) covers a TODO comment, an imperative comment, Markdown emphasis, a string literal that must not match, and a clean comment.

## 4. Target structure

### 4.1 Layers

```text
agent/entry/        process entry and assembly (may depend on app, shell)
agent/app.py        composition root (may depend on capabilities, mechanisms, core, shell)
agent/shell/        HTTP / SSE / adapters (may depend on capabilities, mechanisms, core)
agent/capabilities/ tools and the plugin host (may depend on mechanisms, core)
agent/mechanisms/   mechanisms (may depend on core)
agent/core/         kernel (no upward dependencies)
plugins/            depends downward on agent, from outside the package
```

Only downward edges are allowed; `entry` is the top layer. `app.py` is not in `LAYERS`, but it is constrained separately: it may import any layer, and the four lower layers may not import `agent.app` or `agent.entry` at runtime. `if TYPE_CHECKING:` annotations are exempt because they are not loaded at runtime. `plugins/` stays outside `LAYERS`; its downward dependency on `agent` is a package convention, not an import-graph rule.

### 4.2 Single source for budgets

`scripts/quality_budgets.py` is the only place for numbers: coverage floors, the acceptance-skip budget, the same-layer private-import budget, and the complexity thresholds. Gates and generated documents read from there; a gate script must not define its own threshold. The silent-exception gate has no budget by design.

### 4.3 Testable gate shape

Every `scripts/check_*.py` keeps judgment in functions that take a path, text, or measured data, with `main()` driving I/O. Gates that scan the real tree expose the root or target file as a module-level parameter that tests can replace (`ROOT`, `DOCS`, `WORKFLOW`, `SCAN_DIRS`). The contract is the same: return a list of problems, empty when clean. This is the precondition for `X2`: a negative case can import the function and pass a temporary tree or string, without starting a subprocess or touching the real repository.

## 5. Work breakdown

The phases are ordered by dependency: each one removes a blocker for the next, and feature work can start once P2 is complete. All phases are implemented in the current tree.

### P0 Gate skeleton

| Action | File |
|---|---|
| Budget single source | `scripts/quality_budgets.py` (new) |
| Complexity thresholds and generation | `scripts/check_complexity.py`, `scripts/gen_complexity_md.py`, `docs/complexity.md` |
| Applicability table | `docs/applicability.md`, `scripts/standards_rules.py`, `scripts/check_applicability.py` |
| Gate list documentation | `docs/quality-gates.md` |
| CI wiring | `scripts/ci_steps.py` and the generated `ci.yml` (byte-verified) |

### P1 Local defects

The four `assert` sites, `PluginSegments` immutability, the two `quality` package imports, and the pane comment.

### P2 Split the `shell` ↔ `app` cycle

New `agent/entry/`, the `timefmt.py` extraction, the `TYPE_CHECKING` closure, the startup scripts and documentation, and `entry` added to `LAYERS`. With P2 complete, SCC is 0 and the feature plans can start.

### P3 Gate hardening

Coverage in the step list with per-package floors, the independent skip budget, the strict silent-exception gate, the config schema and drift check, generated-document `--check`, and the generated workflow replacing the hand-written yml.

### P4 Negative cases and concurrency

`tests/test_gate_negative.py`, `tests/test_concurrency.py`, and `tests/test_import_graph.py`.

### P5 Close-out

`ports.py` protocols, a comment sweep, the `entry` layer in `docs/architecture.md`, and the README documentation index.

## 6. Negative test matrix

| Gate | Negative input | Expected |
|---|---|---|
| `check_imports` | Temporary `agent/core` module importing `agent.shell` | Reports the file and both layers |
| `check_architecture_hygiene` | Cross-layer private import; plugin name in `agent/core`; `quality_gate` shim import; same-layer private import over budget | One `file:line` line per violation |
| `check_silent_except` | `except Exception: pass`; a bare `except`; `suppress(Exception)`; a report without a payload | File, line, and reason |
| `check_python_floor` | A PEP 695 generic parsed under the 3.10 floor | Reports the syntax feature and the file |
| `check_comment_style` | A TODO memo; an imperative comment; Markdown emphasis in a comment | Rule name and line |
| `check_ui_js` | A call to an undefined helper; a model-ID literal | File and line |
| `check_readme` | A wrong step, gate, acceptance, or test count; an unknown `data/` subdirectory | Expected and actual values |
| `check_ci_workflow` | A workflow with one extra byte | The first differing line with actual and expected text |
| `check_config_drift` | A real config with an extra key; an unknown section; a plugin `[model:*]` extra key; an example missing a key | Section, key, and line |
| `check_applicability` | An unknown ID; a short reason; a missing table | One message per problem |
| `check_complexity` | An 801-line file; a drifted `docs/complexity.md` | File and line count, or the drift |
| `gen_*_md --check` | A document with one line removed | A mismatch report and exit 1 |
| `check_coverage` | A measured value below the floor; a package with no data | Package, measured value, floor |
| `check_acceptance_skips` | Two skips against a budget of 1; a non-allowlisted name | Count and allowlist |
| `check_catalog` | A missing, corrupt, or drifted catalog | File and reason |

Every negative case builds a temporary directory or string; none modifies a repository file.

## 7. Acceptance commands

```bash
python -O -m unittest tests.test_core
python scripts/check_imports.py --scc          # expect: 0 groups
python scripts/check_architecture_hygiene.py
python scripts/check_silent_except.py
python scripts/check_config_drift.py
python scripts/check_complexity.py
python scripts/check_applicability.py
python scripts/gen_unit_tests_md.py --check
python scripts/gen_complexity_md.py --check
python scripts/check_ci_workflow.py
python scripts/run_coverage.py                 # publish .coverage
python scripts/check_coverage.py               # per-package floors
python scripts/ci.py                           # every step
```

`scripts/ci.py` is the only entry point; any step that runs only in CI and not locally means `Y1` is unfinished.

## 8. Relationship to the feature plans

| Feature work | Prerequisite | Provided by |
|---|---|---|
| Add `agent/shell/classic_adapter/history_page.py` and `agent/shell/web/web_assets/classic/js/history-paging.js` | P2: layers and the entry point are fixed | `agent/entry/`; 0 dependency cycles |
| Add `plugins/multi_model/*` | P2; plugin directories stay outside `LAYERS` | The layer list; the downward plugin convention |
| Add test files | P3: the coverage scope includes the new files | `COVERAGE_FLOORS` and the `agent,plugins` source scope |
| Ship the feature | P4: negative cases and the concurrency job are in place | `tests/test_gate_negative.py`, `tests/test_concurrency.py` |

The feature plans reference this document for existing debt instead of repeating it.

## 9. Risks and rollback

| Risk | Trigger | Mitigation |
|---|---|---|
| The entry migration breaks a user's startup | `start.bat` / `start.sh` change | README, `docs/subsystems/shell.md`, and the release notes change in the same step; no compatibility shim for the old command |
| Coverage floors turn CI red | The first full measurement | Floors are the measured values rounded down; the baseline lands before enforcement |
| Complexity thresholds become a legal debt list | No exemption table | Over-threshold code is split; no registry |
| Generated workflow diverges from the remote CI semantics | Replacing the hand-written yml | Render equivalent content first, diff manually, then replace; keep `workflow_dispatch` |
| A schema change affects every reader | `get_*` defaults | The schema and the gate land first; the affected unit tests run at each step |

## 10. Conclusion

- Of the 13 MUST findings, the two that affect architecture are `A2` (cycles) and `X5` (coverage scope); the rest concern gate trustworthiness and missing registration.
- All phases are implemented. The change set adds no feature and no protocol change; the UI behavior is unchanged except that startup now targets `agent.entry`.
- The prerequisites for both feature plans are met: the layer and entry structure (P2), the coverage scope (P3), and negative and concurrency coverage (P4).
