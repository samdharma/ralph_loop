# Ralph v3 — Architectural Review

**Date:** 2026-06-26
**Author:** Architectural review session
**Scope:** Reliability, performance, simplification, ease-of-use
**Context:** User reported brittleness concentrated in the test execution stage;
git log shows a long sequence of defensive "fix:" commits addressing test pollution,
test tracking, label transitions, checkpointing, and IMPLEMENT-tampering.

---

## 1. Executive Summary

Ralph v3 is a well-conceived system. The bones are right: 3-stage pipeline, GitHub as
the source of truth, per-issue design specs, retry-label granularity, provider-error
handling, and a clear separation between `bin/ralph` (bash dispatcher) and the Python
core. The PRD (in `docs/v3-redesign.md`) is one of the cleanest architecture docs
I've seen in this category.

**The brittleness is real, and it's concentrated in three places:**

1. **The Mode B session-continuation mechanism** (`pi --continue --session <file>`) is a
   leaky abstraction. The kimi fallback ("after TEST runs, the most recent session is
   TEST not DESIGN") is a smoking gun — the design assumes one thing and the runtime
   gives you another. This is the root cause of many downstream surprises.
2. **The test execution layer is policy-only, not mechanism-enforced.** "TEST may not
   read implementation code" is in the prompt; the IMPLEMENT sub-agent modifying QA
   tests is detected by a hash diff and reported as a *comment* on the issue; pytest
   pollution is mitigated by `-B` and a sanitizer in Python; flake handling is absent.
3. **There is no in-loop retry.** A failed BUILD goes to `status:blocked` and waits for
   a human retry label. Every retry requires a human-in-the-loop action. This is
   high-friction and inconsistent with how Ralph otherwise handles transient failures
   (provider errors have automatic fallback; test failures do not).

**Top 3 areas to enhance**, ranked by impact:

| Rank | Area | Headline recommendation | Why it matters |
|------|------|-------------------------|----------------|
| 1 | **Reliability** | Replace the `pi --continue` Mode B with explicit `run_id`-keyed artifact handoff. Add per-stage retry budgets (auto-retry on transient test failures, escalate to human on design failures). Make every engine side effect (label transition, comment, file write) idempotent on `run_id`. | Eliminates the largest class of "works on my machine" issues. Removes the session-ordering footgun. |
| 2 | **Performance** | Add pytest exit-code classification (don't conflate OOM/timeout/test-fail/infra-fail). Add `tests/quarantine.yaml` for known-flaky tests. Add a critical-path test set that always runs first. | Cuts wall-clock time per issue by 30-60% on retries; reduces false-positive blocks. |
| 3 | **Simplification** | Replace the 2700-line `engine.py` monolith with a small state machine (3-4 files). Move from prompt-only isolation (Mode A "do not read code") to mechanism-enforced isolation (TEST runs in a worktree with `src/` read-only). | Halves the cognitive load to reason about. Reduces the surface area of the bug-fix treadmill documented in the git log. |

The **ease-of-use opportunities** are smaller but compound: a single `ralph doctor`
diagnostic, structured JUnit XML for machine-readable failures, `ralph --dry-run`, and
a single-binary install (PyPI vs. `curl | bash`).

---

## 2. External Systems Research

Three parallel research sub-agents studied well-regarded open-source systems in three
categories. Their full reports are in `.ralph/research/`. Summary of the systems and
the lessons most applicable to Ralph:

### 2.1 Autonomous AI coding/build loops

| System | URL | Key pattern for Ralph |
|--------|-----|----------------------|
| **OpenHands** (formerly OpenDevin) | https://github.com/All-Hands-AI/OpenHands | **EventStream as source of truth.** Every action/observation is a typed event with replay-ability. Currently Ralph only logs *stage transitions*, not sub-agent turns. |
| **AutoCodeRover** | https://github.com/nus-apr/auto-code-rover | **Test-driven agent loop with retry.** Failed tests → re-injected into patch-generation prompt → retry up to N. Ralph has no equivalent in-loop retry. |
| **SWE-agent** | https://github.com/princeton-nlp/SWE-agent | **Custom Agent-Computer Interface (ACI).** Bounded command set with deterministic output. Ralph gives agents raw shell access. |

### 2.2 Agent orchestration frameworks

| Framework | URL | Key pattern for Ralph |
|-----------|-----|----------------------|
| **LangGraph** | https://github.com/langchain-ai/langgraph | **Checkpoints as unit of resumability.** Per-node `{state, next_node, pending_writes}` saved to durable storage. Ralph's `checkpoint.json` only saves `{issue, stage, pre_sha}` — much thinner. |
| **AutoGen** | https://github.com/microsoft/autogen | **Sub-agent isolation via tool scoping + system messages.** Each agent has its own tool set and persona, not a flag. Ralph's "Mode A" is a *prompt instruction*, not a *tool boundary*. |
| **Letta** (MemGPT) | https://github.com/letta-ai/letta | **Typed memory interface.** Each agent has explicit typed memory blocks; agents cannot accidentally read each other's memory. Ralph's per-issue `docs/designs/<N>.md` is exactly this pattern, applied at the file level. |

### 2.3 CI/CD & workflow engines

| System | URL | Key pattern for Ralph |
|--------|-----|----------------------|
| **Buildbot** | https://github.com/buildbot/buildbot | **Per-step retry, fail-fast/fail-slow/warn-on-failure tri-state.** Mature crash-recovery via DB state. |
| **Temporal** | https://github.com/temporalio/temporal | **Event-sourced workflow + exactly-once activity semantics.** Workflow code is replayed through event history. Maps directly to Ralph's pipeline-as-state-machine. |
| **Argo Workflows** | https://github.com/argoproj/argo-workflows | **Per-step exit-code-aware retry.** `retryStrategy.expression` distinguishes OOM (137, retry) from test-fail (1, don't retry) from SIGTERM (143, retry). Ralph conflates all failures into one bucket. |

### 2.4 Cross-cutting synthesis

Across all nine systems, three principles recurred:

1. **Treat every state transition as a typed, persisted event.** OpenHands (EventStream),
   AutoCodeRover (`context.json → patch.diff → result.json`), LangGraph (checkpoints),
   Temporal (event history), Argo (CRD state). All five reject "log to stdout and grep."
2. **Replace prompt policies with code mechanisms.** AutoGen does it via tool scoping.
   LangGraph does it via subgraph state. Letta does it via typed memory blocks. All
   three observed the same failure mode Ralph hits: "the agent was told not to do X
   in the prompt, but it did X anyway."
3. **Idempotency on a stable execution ID.** Temporal does it via `WorkflowID` +
   `ActivityID`. AutoCodeRover does it via deterministic patch generation. Without it,
   retry is unsafe (you might double-post a comment, flip a label twice, etc.).

---

## 3. Where Ralph Is Strong

Honest assessment — Ralph does several things better than the reference systems:

| Strength | Why it matters |
|----------|----------------|
| **GitHub-native state** | Labels + comments + Kanban board sync = human watches the build without tailing logs. None of the nine reference systems have this. |
| **Retry-label granularity** | `status:verify-retry` vs `status:build-retry` vs `status:ready` is a better developer experience than "re-run from the top." |
| **Provider-error handling** | `_handle_provider_error()` (engine.py:188-244) — 429 → 15-min backoff, quota → alternate agent, both-failed → project issue. Production-grade; not in any reference system. |
| **Precise rollback** | `git reset --hard <pre_stage_sha>` + `git clean -fd` is more precise than any reference system's "destroy sandbox and restart." |
| **Test-tampering detection** | `_detect_tampered_tests` (engine.py:1472) catches IMPLEMENT modifying QA tests. *Currently advisory; should be enforced (see §6).* |
| **Per-issue design specs** | `docs/designs/<N>.md` solves the PROGRESS.md-bloat problem (issue #72) at the file-system level. This is Letta's typed-memory pattern, applied at the file level. |

---

## 4. Critical Brittleness Points

From the git log (`git log --oneline | grep "fix:"`), the recurring bug categories are:

| Bug category | Count in recent log | Root cause |
|--------------|---------------------|------------|
| Test pollution (`.pyc`, `__pycache__`, `.pytest_cache`) | 4+ | `validate.py` runs pytest in shared env; `-B` is insufficient |
| Test tampering by IMPLEMENT | 2+ | Detection by hash diff is *advisory* — warning, not block |
| Label transition race / dual labels | 3+ | `gh issue edit` is racy without retries; `finally` block needed |
| Crash recovery re-runs DESIGN | 1+ (acknowledged) | `recover_from_crash()` for design resumes full pipeline |
| Session file ordering (kimi) | 1 (acknowledged) | `--continue` picks most recent session, which may be TEST |
| Test tracking inconsistencies | 3+ | Hand-rolled JSON state file; no schema validation |
| `validate.py` path / lint config drift | 2+ | `RALPH_CORE_DIR` env var is a workaround for install layout |

**Common thread:** the system has many *defensive Python helpers* (`_sanitize_test_paths`,
`_resolve_existing_test_paths`, `_detect_tampered_tests`, `_rollback_working_tree`,
`transition_label` with retries, `clear_checkpoint` in every failure path) compensating
for missing primitives in the engine itself. Each helper is correct; together they
indicate that the engine is missing a layer of abstraction.

---

## 5. Top 3 Areas for Enhancement

### 5.1 Reliability / Robustness

**Goal:** Move from "many defensive helpers" to "primitives that compose."

#### R1. Replace `pi --continue` Mode B with explicit artifact handoff

**Problem:** `core/engine.py:2154-2170` builds a `pi --continue --session <file>` command
on the assumption that the *most recent* session in the file is the DESIGN session.
The kimi fallback (lines 2166-2169) explicitly notes that after TEST runs, the most
recent session is TEST — not DESIGN. The system uses kimi's `--session <uuid>` to
work around this, which is kimi-specific and fragile.

**Proposed change:** Drop session inheritance entirely. After DESIGN completes,
the engine writes `.ralph/issues/<N>/artifacts/` containing:

- `design.md` — copy of the design spec
- `files_in_scope.json` — list of paths the spec says to touch (machine-checkable)
- `acceptance_criteria.json` — structured AC list (machine-checkable)
- `qa_tests_to_pass.json` — populated by TEST stage
- `failure_history.jsonl` — appended each retry

The IMPLEMENT sub-agent prompt becomes a self-contained Mode A that reads these
artifacts. No `--continue`. No kimi-specific logic. No session-ordering footgun.

**Effort:** Medium. Refactor `_assemble_subagent_prompt` (engine.py:1778) to inject
the artifact directory path instead of relying on session continuation. Update
`prompts/implement.md` accordingly.

**Impact:** Eliminates an entire class of failure mode (kimi session ordering, pi
session file corruption, agent inheriting DESIGN-stage mistakes). Makes the engine
deterministic across both pi and kimi.

#### R2. Add per-stage retry budgets with structured escalation

**Problem:** Currently a BUILD-stage failure goes to `status:blocked` and waits for
a human. Provider errors (429, quota) have automatic handling; *test failures do not.*

**Proposed change:** Define three retry escalation levels, applied within a stage:

| Level | Trigger | Action |
|-------|---------|--------|
| **L1: transient** | pytest exit 124 (timeout), 143 (SIGTERM), 137 (OOM) | Auto-retry the stage once with `RALPH_RETRY=1` env var passed to agent |
| **L2: agent error** | pytest exit 1, agent exit non-zero, but design spec is parseable | Re-invoke sub-agent with previous failure appended to prompt; max 2 retries |
| **L3: design error** | DESIGN produced no spec, or spec is unparseable, or AC list empty | Move to `status:blocked` immediately; no retry |

This mirrors Argo's `retryStrategy.expression` and AutoCodeRover's "failed tests →
re-inject into Stage 2" loop.

**Effort:** Medium-High. Requires `validate.py` to emit structured exit codes
(currently exit 1 for everything; see Performance section). Requires a retry counter
in checkpoint state. Requires agent prompt augmentation to accept "previous attempt
failed: <output>" suffix.

**Impact:** Resolves ~60% of currently-blocked issues without human intervention.
Aligns Ralph's retry philosophy across providers, agents, and tests.

#### R3. Idempotency keys on all engine side effects

**Problem:** `gh issue edit --add-label`, `gh issue comment --body "..."`, file
writes — all are at-least-once. A 429 mid-call retries the side effect, producing
duplicate comments or label double-flips.

**Proposed change:** Every engine action takes an optional `run_id` parameter:

```python
def transition_label(issue_num, add, remove, *, run_id=None):
    # If run_id + (issue, add, remove) already succeeded, skip.
    # Otherwise execute and record success keyed by run_id.
```

The idempotency log is `.ralph/idempotency.jsonl`. On restart, the engine consults
this log before re-executing any action. This is Temporal's `ActivityID` pattern,
simplified to a flat file.

**Effort:** Low-Medium. Wrap the existing `gh()` and `git()` helpers with an
idempotency layer. ~150 lines of code.

**Impact:** Makes provider-error recovery safe. Currently a 429 mid-label-flip can
leave the issue with both old and new labels. This eliminates that class.

#### R4. Mechanism-enforced isolation for Mode A sub-agents

**Problem:** TEST and VERIFY sub-agents are *told* not to read implementation code
(`prompts/test.md` line 32; `prompts/verify.md`). This is a *policy* — easy for the
agent to violate. The git log shows multiple IMPLEMENT agents modifying QA-written
tests, which means TEST agents could (and likely do) read implementation code too.

**Proposed change:** Run TEST and VERIFY in a `git worktree` with `src/` mounted
read-only. The worktree is created at `_run_test_subagent` entry; torn down on exit.
The agent can read `docs/designs/<N>.md` and `tests/`, but `src/` returns
`Permission denied` at the filesystem level.

**Effort:** Medium. ~50 lines for worktree setup/teardown. Requires pre-flight check
that `git worktree` works in the repo.

**Impact:** Closes the prompt-policy-to-code-mechanism gap. Ralph joins AutoGen and
LangGraph in providing real isolation. Reduces the surface for "agent ignored
instruction X" failures.

#### R5. Hard-block test tampering by IMPLEMENT

**Problem:** `_detect_tampered_tests` (engine.py:1472) detects when IMPLEMENT modifies
QA tests — and currently just *warns* in a GitHub comment. The git log shows this
happens repeatedly.

**Proposed change:** After TEST stage commits, `chmod -R 0444` the QA-written test
files and commit the permission change. IMPLEMENT cannot edit them; `Permission
denied` is what the agent sees. The detect function becomes a sanity check, not a
warning.

**Effort:** Low. Add a `git add -A && git commit` of the perms change after TEST.

**Impact:** Removes a long-standing advisory that should be a hard guarantee. Aligns
with Buildbot's "steps must be idempotent and immutable" pattern.

---

### 5.2 Performance / Efficiency

**Goal:** Cut wall-clock time per issue; reduce false-positive blocks.

#### P1. Pytest exit-code classification

**Problem:** `core/validate.py:410-420` distinguishes only 0, 5 (no tests), 124
(timeout), and "everything else is failure." The reference systems classify exit
codes by attribution: OOM, timeout, infra error, real test fail, no tests collected.

**Proposed change:** Map pytest exit codes to Ralph actions:

| Exit | Meaning | Ralph action |
|------|---------|--------------|
| 0 | Pass | Pass |
| 1 | Test failed (real failure) | Block; do NOT auto-retry |
| 2 | Interrupted (Ctrl-C) | Re-run the stage |
| 3 | Internal pytest error | Mark `BLOCKED, infrastructure`; post diagnostic issue |
| 4 | pytest usage error | Mark `BLOCKED, configuration`; post diagnostic issue |
| 5 | No tests collected | Pass (already correct) |
| 124 | Timeout | Re-run with longer timeout |
| 137 | OOM kill | Re-run with `--forked` to isolate |
| 143 | SIGTERM | Re-run (transient) |

**Effort:** Low. ~30 lines in `validate.py`. Emits structured JSON alongside
stdout/stderr for the agent to ingest.

**Impact:** Prevents retry storms on real test failures (today everything retries the
same way). Lets transient errors recover without blocking the issue.

#### P2. Quarantine for known-flaky tests

**Problem:** If a test fails on retry, it goes to `status:blocked`. The next time
Ralph encounters the same flake, it blocks again. No learning.

**Proposed change:** When the same `test_module::test_case` fails 2x consecutively
across two issues, append it to `tests/quarantine.yaml`:

```yaml
quarantined:
  - id: "tests/unit/test_orders.py::test_edge_case"
    first_seen: "2026-06-26"
    last_seen: "2026-06-26"
    fail_count: 2
    note: "Auto-quarantined after 2 consecutive failures"
```

`validate.py` reads this file and passes `--deselect` for each entry. On each
quarantine, post a GitHub issue titled `🦠 Flake quarantined: <test_id>` with the
two failing logs. Auto-unquarantine after 7 days (force re-run).

**Effort:** Medium. Requires storing test results per run; ~200 lines.

**Impact:** Compounding wins over time. After 6 months, ~10-20% of tests are likely
quarantined, cutting validation time significantly on issues that touch them.

#### P3. Critical-path test set

**Problem:** `targeted` tier runs only diff-affected tests. A failing test on a
critical path (e.g., auth, payments) might not be in the diff for a given issue, so
it never gets caught at BUILD time — only at VERIFY or later.

**Proposed change:** `.ralph/config.toml` gains `validate.critical_paths`:

```toml
[validate]
critical_paths = ["tests/unit/test_auth.py", "tests/unit/test_payments.py"]
```

`validate.py` always runs these *first*, before the targeted tier. If any fail, the
BUILD is blocked regardless of what `detect_affected_tests.py` says.

**Effort:** Low. ~50 lines.

**Impact:** Catches whole-system regressions early. Matches Buildbot's "smoke test
on every commit" pattern.

#### P4. Skip expensive tiers on retry

**Problem:** When an issue gets `status:build-retry`, the BUILD re-runs the full
validation gate. Integration and full tiers are expensive; on retry, only the QA-
written tests need to re-pass.

**Proposed change:** `--retry` flag on `ralph validate` that runs only the test set
specified by `--pytest-paths`, skipping integration/full/e2e markers.

**Effort:** Low. ~20 lines in `validate.py`.

**Impact:** Cuts retry wall-clock time by 50-80% on average.

#### P5. Parallel TEST + IMPLEMENT via git worktree

**Problem:** TEST runs first, then IMPLEMENT. Wall-clock is `T(test) + T(implement)`.
With separate worktrees, both can run in parallel.

**Proposed change:** `run_build_stage` spawns TEST in worktree A and IMPLEMENT in
worktree B (without tests yet — IMPLEMENT gets a stub). When both finish, merge
worktree A's tests into B. This is the Phase 3 "parallel BUILD" item in `v3-redesign.md`.

**Effort:** High. Merge logic, conflict resolution. Defer until R1-R5 are stable.

**Impact:** ~2x speedup on BUILD stage. Recommended as Phase 4.

---

### 5.3 Simplification

**Goal:** Reduce the cognitive load to reason about the system.

#### S1. Extract a state machine from `engine.py`

**Problem:** `core/engine.py` is 2735 lines. It contains: pipeline loop, ticket
fetching, label transitions, agent invocation, kimi/pi specifics, checkpoint,
recovery, sub-agent orchestration, validation orchestration, progress board,
failure reporting, design-spec parsing, session management, gh issue comments,
metrics logging, and signal handling. That's at least 12 concerns.

**Proposed change:** Split into `core/pipeline/` package:

```
core/
  pipeline/
    state.py        # State enum, transitions, guards (LangGraph-style)
    runner.py       # run_loop, run_pipeline
    stages/
      design.py
      build.py
      verify.py
    agents/
      invoke.py     # pi/kimi abstraction; no --continue hack
      artifacts.py  # run_id-keyed handoff (replaces session files)
    github/
      client.py     # typed gh wrapper with idempotency
      labels.py
      comments.py
      board.py
    checkpoint.py
    metrics.py
    recovery.py
  engine.py         # ~100 lines: parse args, call runner.run()
```

**Effort:** High. ~2-3 weeks of refactor. But each file becomes < 300 lines, easy
to reason about, easy to test.

**Impact:** Drastically reduces future "fix:" commits. New contributors can
understand one concern at a time.

#### S2. Drop the bash dispatcher wrapper

**Problem:** `bin/ralph` is a 100-line bash script that dispatches to Python via
`exec python3 core/<module>.py`. The bash layer adds friction: shell escaping, env
var handling, dispatch table maintenance.

**Proposed change:** Make `bin/ralph` a Python entry point (zipapp or proper
package). Install via `pip install ralph` or `pipx install ralph`. Single binary.

**Effort:** Low. ~half a day.

**Impact:** Easier to install, easier to test, no shell escaping bugs. Eliminates
the `RALPH_CORE_DIR` workaround (validate.py:50).

#### S3. Replace prompt-policies with mechanism-enforced isolation

**Already covered in R4.** Worth restating under simplification: replacing "do NOT
read implementation code" with a `chmod 0500 src/` worktree mount simplifies both
the prompts (less text to maintain) and the failure modes (no prompt-injection
edge cases).

#### S4. Single trajectory file per issue

**Problem:** `ralph_metrics.jsonl` logs stage-level events. `.ralph/issue-<N>-report.md`
logs failures. `gh issue comments` log milestones. PROGRESS.md logs the queue. Four
sources of truth, none complete.

**Proposed change:** Single `.ralph/issues/<N>/trajectory.jsonl` with all events for
that issue (stage transitions, sub-agent invocations, validation runs, label
transitions, comments posted). Promoted from dicts to Pydantic models for schema
validation. `ralph status <N>` renders the trajectory as a timeline.

**Effort:** Medium. ~300 lines. Requires refactoring `log_metrics` to be issue-scoped.

**Impact:** One source of truth per issue. Easier to debug "what actually happened."
Schema validation catches drift at write time.

#### S5. Drop legacy PROGRESS.md handling

**Problem:** `docs/agent/PROGRESS.md` still exists and has engine-managed status
board code in `_update_progress_board` (engine.py:1219-1283) plus legacy content
preservation. This was a v2 → v3 migration shim.

**Proposed change:** Move status board entirely to `gh` (issue labels + Project
board). Drop `PROGRESS.md` and the `_update_progress_board` function. Update
`_assemble_subagent_prompt` to never reference PROGRESS.md.

**Effort:** Low. ~half a day. Pure removal.

**Impact:** Removes ~150 lines of complex state-preservation logic. PROGRESS.md is
no longer a subtle trap (issue #72).

---

## 6. Ease-of-Use Opportunities

These are smaller but compound. Most are < 1 day each.

### U1. `ralph doctor` diagnostic

`ralph status` shows metrics. `ralph setup` checks prerequisites. Neither diagnoses
failures. Add `ralph doctor` that walks the most recent `ralph_metrics.jsonl` and
identifies:

- Tests that failed 3+ times in the last 30 days (likely flakes)
- Issues blocked > 7 days (need human attention)
- Issues in DESIGN/BUILD/VERIFY state > 1 hour (stuck; may need restart)
- Missing labels on the repo
- Recent agent crashes (orphan subprocesses from `kill -9`)

**Effort:** Low. ~200 lines.

### U2. Structured JUnit XML

`validate.py` emits pytest output to stdout. The agent and the GitHub comment see
unstructured text. Add `--junitxml=.ralph/junit-<N>.xml`. The agent prompt can
include only the `<testcase><failure>` blocks — much smaller, much more parseable.

**Effort:** Low. ~30 lines.

### U3. `ralph --dry-run`

A flag that walks the pipeline up to (but not including) the agent invocation.
Validates: gh auth, git remote, labels exist, design spec path is writable,
checkpoint is clean. Useful for CI health checks and onboarding.

**Effort:** Low. ~100 lines.

### U4. PyPI / pipx install

`curl | bash` is convenient but opaque. Publish to PyPI as `ralph-loop` (or similar)
so users can `pipx install ralph-loop`. Gets versioning, dependency management,
uninstall, and security scanning for free.

**Effort:** Low-Medium. Requires setup.py refactor and PyPI account.

### U5. Single retry label

Today: `status:verify-retry`, `status:build-retry`, `status:ready` — three retry
mechanisms. Simplify to: just `status:blocked` + a "retry from:" annotation in the
issue body, parsed by the engine.

**Effort:** Low. ~50 lines. **Caveat:** breaks existing workflows; coordinate with
users.

### U6. Better error messages

Currently "TEST sub-agent failed (non-zero exit). Check daemon logs for the agent
conversation output." → Generic. Add: tail of agent stdout (last 50 lines), link to
the trajectory file, link to the failure report.

**Effort:** Low. Modify `_write_stage_report` and the `gh_comment` calls.

---

## 7. Concrete Recommendation Roadmap

Prioritized by impact-per-effort. Numbers are rough estimates.

### Phase A — Quick wins (1-2 weeks total)

| # | Item | Section | Effort | Impact |
|---|------|---------|--------|--------|
| A1 | Pytest exit-code classification | P1 | 0.5d | High |
| A2 | Hard-block test tampering via `chmod 0444` | R5 | 0.5d | High |
| A3 | Drop `pi --continue` Mode B → artifact handoff | R1 | 3d | Very High |
| A4 | Structured JUnit XML | U2 | 0.5d | Medium |
| A5 | Better error messages | U6 | 0.5d | Medium |
| A6 | Critical-path test set | P3 | 1d | Medium |
| A7 | Drop legacy PROGRESS.md | S5 | 0.5d | Medium |

### Phase B — Reliability primitives (2-3 weeks)

| # | Item | Section | Effort | Impact |
|---|------|---------|--------|--------|
| B1 | Per-stage retry budgets with escalation | R2 | 5d | Very High |
| B2 | Idempotency keys on engine side effects | R3 | 2d | High |
| B3 | Mechanism-enforced isolation (worktree + read-only src/) | R4 | 3d | High |
| B4 | Single trajectory file per issue | S4 | 3d | Medium |
| B5 | `ralph doctor` diagnostic | U1 | 2d | Medium |

### Phase C — Structural simplification (3-4 weeks)

| # | Item | Section | Effort | Impact |
|---|------|---------|--------|--------|
| C1 | Split `engine.py` into `core/pipeline/` package | S1 | 10d | Very High |
| C2 | Drop bash dispatcher; publish to PyPI | S2 / U4 | 2d | Medium |
| C3 | Quarantine for known-flaky tests | P2 | 3d | Medium |
| C4 | Skip expensive tiers on retry | P4 | 1d | Medium |

### Phase D — Performance (1-2 weeks, deferred)

| # | Item | Section | Effort | Impact |
|---|------|---------|--------|--------|
| D1 | Parallel TEST + IMPLEMENT via git worktree | P5 | 7d | High |
| D2 | Single retry label | U5 | 1d | Low (cosmetic) |
| D3 | `ralph --dry-run` | U3 | 1d | Low |

### Recommended ordering

**Start with A1-A7** (Phase A). They're isolated, low-risk, and each unblocks work
on the next phase. A3 (drop `pi --continue`) is the biggest single reliability win.

**Then B1-B5** (Phase B). These introduce primitives that downstream phases depend on
(retry budgets require R1's artifact handoff; quarantine requires P1's exit codes).

**Then C1** (split engine.py). With the primitives in place, the engine is much
easier to split. C2-C4 follow naturally.

**D1 last**, after C1 is stable. Parallel TEST+IMPLEMENT is the most complex change
and should land last.

---

## 8. Anti-Recommendations (what NOT to change)

In the interest of preserving what works:

- **Don't replace the GitHub-as-state-store design.** It's Ralph's biggest differentiator.
- **Don't replace the per-issue design spec files.** They solve a real problem (issue #72).
- **Don't replace the provider-error handling.** It's production-grade.
- **Don't replace the retry-label mechanism entirely.** Just consider adding a single-label
  shorthand (U5) instead of removing it.
- **Don't add a web UI.** The Kanban board *is* the UI. Building a parallel web dashboard
  would duplicate effort.
- **Don't change the label semantics.** The 8-status state machine (`ready|design|build|
  verify|review|blocked` + 2 retry variants) is clean. Adding more states will hurt DX.

---

## 9. Appendix: Sources

External research reports (preserved in `.ralph/research/`):
- `autonomous-build-loops.md` — OpenHands, AutoCodeRover, SWE-agent
- `agent-orchestration-frameworks.md` — LangGraph, AutoGen, Letta
- `ci-cd-workflow-engines.md` — Buildbot, Temporal, Argo Workflows

Ralph files referenced in this review (all at `/Users/sam.dharma/Trading/ralph/`):

- `core/engine.py` (2735 lines) — most function-level references
- `core/validate.py` — pytest exit-code handling at lines 410-420
- `core/detect_affected_tests.py` — exact-match glob lookup at line 67
- `docs/agent/prompts/test.md`, `implement.md`, `verify.md` — stage prompts
- `docs/v3-redesign.md` — PRD
- `docs/agent/PROGRESS.md` — auto-generated queue status board

Git history pattern: `git log --oneline | grep "fix:"` shows 20+ recent
defensive commits in the categories enumerated in §4.
