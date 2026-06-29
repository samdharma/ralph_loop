# Implementation Plan: Ralph v3.1 — Improvement Roadmap

**Status:** DRAFT (awaiting human review)
**Date:** 2026-06-27
**Author:** Spec-driven development PLAN phase
**Approved spec:** [`docs/IMPROVEMENT_ROADMAP_SPEC.md`](IMPROVEMENT_ROADMAP_SPEC.md) — DO NOT modify while implementing this plan; if a decision must change, update the spec first (§9.1.7).
**Architectural source:** [`docs/architectural-review-2026-06-26.md`](architectural-review-2026-06-26.md)
**Target:** 4 phased PRs against the `ralph-v3.1` branch, releasing `ralph-v3.1.0` → `ralph-v3.1.3` per §3.2 and §10.

---

## 0. How to read this plan

This document is the **technical implementation plan** that breaks the spec into ordered, verifiable work. It is NOT the TASKS phase (per `skills/spec-driven-development/SKILL.md` Phase 3). TASKS is a separate, finer-grained decomposition that will be produced after this plan is approved.

**Citation convention:** `(spec §X.Y)` refers to `docs/IMPROVEMENT_ROADMAP_SPEC.md`. `(ar §Z)` refers to `docs/architectural-review-2026-06-26.md`.

**Branch strategy reminder:** Single `ralph-v3.1` branch, one PR per phase (per spec §3.8). Detailed contributor workflow lives in `docs/development_workflow.md` (item NEW-1, §6.1).

**Methodology:** All implementation follows `skills/incremental-implementation/SKILL.md` (vertical slices, one thing at a time, each increment compiles and passes tests) and `skills/test-driven-development/SKILL.md` (write tests first, then code).

---

## 1. Components and Dependencies

This section names every component the spec calls for, organized by **phase**, with explicit dependencies. A component cannot ship until its dependencies are present.

### 1.1 Component catalog

#### Phase A components (all paths relative to repo root)

| ID | Component | Path | Type | Deps |
|----|-----------|------|------|------|
| A-prelude | `ralph migrate` command | `core/migrate.py` + `bin/ralph` (cmd) | NEW | none |
| A1.1 | Pytest exit-code classifier | `core/validate.py` (new module) | NEW | none |
| A1.2 | Structured pytest result emitter | `core/validate.py` (extend `run_pytest_invocation`) | MODIFY | A1.1 |
| A2.1 | QA-test permission lock | `core/engine.py` (`_run_test_subagent`) | MODIFY | none |
| A2.2 | `_detect_tampered_tests` reclassification | `core/engine.py:1472` | MODIFY | A2.1 |
| A3.1 | Artifact directory writer | `core/pipeline/agents/artifacts.py` | NEW | none |
| A3.2 | Artifact-reading IMPLEMENT prompt | `core/engine.py` (`_run_implement_subagent`, `_assemble_subagent_prompt`) + `docs/agent/prompts/implement.md` | MODIFY | A3.1, A-prelude |
| A3.3 | Drop `--continue` flag from agent invocation | `core/engine.py` (`invoke_agent`) | MODIFY | A3.2 |
| A4.1 | JUnit XML emitter | `core/validate.py` (new `--junitxml`) | NEW | A1.2 |
| A4.2 | Agent JUnit parsing | `docs/agent/PROMPT.md` + stage prompts | MODIFY | A4.1 |
| A5.1 | Enriched failure comments | `core/engine.py` (`_write_stage_report`, `_format_stage_failure`) | MODIFY | none |
| A6.1 | Critical-path test config | `core/validate.py` (new `--critical`, `[validate] critical_paths`) | NEW | none |
| A7.1 | Drop `docs/agent/PROGRESS.md` writes | `core/engine.py` (remove `_update_progress_board` ~150 lines) | MODIFY | none |
| A7.2 | Update prompts to drop PROGRESS.md references | `docs/agent/PROMPT.md` + 4 stage prompts | MODIFY | A7.1 |

#### Phase B components

| ID | Component | Path | Type | Deps |
|----|-----------|------|------|------|
| B1.1 | Per-stage retry-budget config | `core/pipeline/state.py` (new), `core/engine.py` | NEW | A1.2, A3.2 |
| B1.2 | Pytest-exit-code-driven retry classifier | `core/validate.py` (return `{exit_code, classification, action}`) | MODIFY | A1.2 |
| B1.3 | Agent re-invocation with previous-failure context | `core/engine.py` (`invoke_agent` wrapper) | MODIFY | A3.2, B1.1 |
| B2.1 | `run_id` generator | `core/pipeline/state.py` | NEW | none |
| B2.2 | Idempotency log writer | `core/pipeline/github/client.py` (new module) | NEW | A3.1 (for log path) |
| B2.3 | Wrap existing `gh()` and `git()` helpers with idempotency | `core/engine.py` (~10 sites: `transition_label`, `gh_comment`, file writes) | MODIFY | B2.2 |
| B3.1 | Worktree setup/teardown helper | `core/pipeline/agents/base.py` (new) | NEW | none |
| B3.2 | Read-only `src/` mount | `core/pipeline/agents/base.py` | NEW | B3.1 |
| B3.3 | TEST + VERIFY use worktree | `core/engine.py` (`_run_test_subagent`, `_run_verify_subagent`) | MODIFY | B3.1, B3.2 |
| B4.1 | `TrajectoryEvent` Pydantic union | `core/schemas/events.py` | NEW | none (first Pydantic use per §4.2) |
| B4.2 | Trajectory writer | `core/pipeline/metrics.py` (new module) | NEW | B4.1 |
| B4.3 | Per-stage event emission | `core/engine.py` (every `transition_label`, `invoke_agent`, `validate` call) | MODIFY | B4.2 |
| B4.4 | `ralph trajectory <N>` command | `core/trajectory.py` + `bin/ralph` | NEW | B4.2 |
| B5.1 | `ralph doctor` command | `core/doctor.py` + `bin/ralph` | NEW | B4.2 |
| B5.2 | 5 diagnostic categories per §3.10 | `core/doctor.py` | NEW | B5.1 |

#### Phase C components

| ID | Component | Path | Type | Deps |
|----|-----------|------|------|------|
| C1.1 | `core/pipeline/__init__.py` (package skeleton) | `core/pipeline/__init__.py` | NEW | B2.2, B4.2 |
| C1.2 | Move `state.py` (Stage enum, PipelineState) | `core/engine.py` → `core/pipeline/state.py` | MOVE | C1.1 |
| C1.3 | Move `runner.py` (run_loop, run_pipeline) | `core/engine.py:536-727, 2387-2618` → `core/pipeline/runner.py` | MOVE | C1.1 |
| C1.4 | Move `stages/` (design, build, verify) | `core/engine.py` → `core/pipeline/stages/*.py` | MOVE | C1.1, C1.3 |
| C1.5 | Move `agents/` (base, pi, kimi, artifacts) | `core/engine.py` → `core/pipeline/agents/*.py` | MOVE | C1.1, A3.x, B3.x |
| C1.6 | Move `github/` (client, labels, comments, board) | `core/engine.py` → `core/pipeline/github/*.py` | MOVE | C1.1, B2.3 |
| C1.7 | Move `checkpoint.py`, `metrics.py`, `recovery.py` | `core/engine.py:2273-2358` → `core/pipeline/{checkpoint,metrics,recovery}.py` | MOVE | C1.1, B4.2 |
| C1.8 | `core/engine.py` shrinks to CLI entrypoint (<200 lines) | `core/engine.py` | SHRINK | C1.2–C1.7 |
| C2.1 | `Makefile` (install, test, lint, format, version, release) | `Makefile` | NEW | none |
| C2.2 | `scripts/release.sh` automation | `scripts/release.sh` | NEW | C2.1 |
| C2.3 | `scripts/install.sh` updated for v3.1 | `scripts/install.sh` | MODIFY | none |
| C2.4 | README updated install instructions | `README.md` | MODIFY | C2.3 |
| C3.1 | `tests/quarantine.yaml` schema | `core/validate.py` | NEW | A1.2 |
| C3.2 | Quarantine auto-add on 2 consecutive failures | `core/validate.py` + `core/engine.py` | NEW | A1.2 |
| C3.3 | Quarantine auto-unquarantine after 7 days | `core/validate.py` (CLI flag `--unquarantine-stale`) | NEW | C3.1 |
| C3.4 | `🦠 Flake quarantined:` GitHub issue post | `core/engine.py` | NEW | C3.2, B2.2 (idempotent comment) |
| C4.1 | `ralph validate --retry` flag | `core/validate.py` | NEW | A1.2 |

#### Phase D components

| ID | Component | Path | Type | Deps |
|----|-----------|------|------|------|
| D1.1 | Parallel TEST + IMPLEMENT scheduler | `core/pipeline/stages/build.py` | NEW | B3.1 |
| D1.2 | Worktree-merge logic | `core/pipeline/agents/base.py` | NEW | B3.1, D1.1 |
| D1.3 | Conflict-resolution policy | `core/pipeline/stages/build.py` | NEW | D1.2 |
| D2.1 | `status:retry` label recognition | `core/engine.py` (`_fetch_ready_issues` + retry path) | MODIFY | none |
| D3.1 | `ralph daemon --dry-run` | `core/engine.py` | MODIFY | none |
| D3.2 | `ralph status --dry-run` for CI | `core/status.py` | MODIFY | none |

#### Cross-cutting components (any phase, but reused)

| ID | Component | Path | Type | Owner phase |
|----|-----------|------|------|-------------|
| NEW-1 | `docs/development_workflow.md` | `docs/development_workflow.md` | NEW | A (under A-prelude; required for #8 of PR checklist) |
| NEW-2 | `docs/CHANGELOG.md` | `docs/CHANGELOG.md` | NEW | A (per #7 of PR checklist) |
| NEW-3 | `.github/PULL_REQUEST_TEMPLATE.md` | `.github/PULL_REQUEST_TEMPLATE.md` | NEW | A (per §13) |
| NEW-4 | `.github/REVIEWER_CHECKLIST.md` | `.github/REVIEWER_CHECKLIST.md` | NEW | A |
| NEW-5 | `.github/workflows/e2e.yml` | `.github/workflows/e2e.yml` | NEW | A (PR #6 verification gate) |
| NEW-6 | E2E cleanup workflow | `.github/workflows/e2e-cleanup.yml` | NEW | A (per §14.3) |
| NEW-7 | `tests/e2e/test_ralph_e2e_repo.py` | `tests/e2e/test_ralph_e2e_repo.py` | NEW | A (skeleton) + E (extension per phase) |
| NEW-8 | Version bump: `pyproject.toml`, `core/__init__.py`, `bin/ralph` | three files | MODIFY | Each phase release |
| NEW-9 | Bump Python deps in `pyproject.toml` | `pyproject.toml` | MODIFY | A (pydantic dep added at B4.1 per §4.2) |

### 1.2 Dependency graph (text form)

```
A-prelude ──┬─→ A3.1 ──→ A3.2 ──→ A3.3
            │
A1.1 ──→ A1.2 ──┬─→ A4.1 ──→ A4.2
                 ├─→ A6.1
                 ├─→ B1.2 ──→ B1.1 ──→ B1.3
                 ├─→ C3.1 ──→ C3.2 ──→ C3.3
                 │       └─→ C3.4
                 └─→ C4.1
A2.1 ──→ A2.2
A5.1 (independent)
A7.1 ──→ A7.2

[B2] B2.1 ──→ B2.2 ──→ B2.3 ────────────────────────────→ (consumed by C1.6, C3.4, D3)
[B3] B3.1 ──→ B3.2 ──→ B3.3
[B4] B4.1 ──→ B4.2 ──→ B4.3
                       └─→ B4.4 (ralph trajectory)
                       └─→ B5.1 ──→ B5.2 (ralph doctor)

[C1] C1.1 ──→ C1.2 ──→ C1.3 ──┬─→ C1.4
                                ├─→ C1.5  (depends on A3.x, B3.x being already in engine.py)
                                ├─→ C1.6  (depends on B2.3)
                                ├─→ C1.7  (depends on B4.2)
                                └─→ C1.8  (final shrink)
[C2] C2.1 ──→ C2.2
       C2.3 (independent) ──→ C2.4
[C3] C3.1 ──→ C3.2 ──┬─→ C3.3
                     └─→ C3.4
[C4] C4.1 (depends on A1.2)

[D1] B3.1 ──→ D1.1 ──→ D1.2 ──→ D1.3
[D2] D2.1 (independent)
[D3] D3.1, D3.2 (independent)
```

### 1.3 Critical sequencing rules (do not violate)

1. **`ralph migrate` (A-prelude) MUST land before A3.3 and before B4.2** (per spec §11.2). A3.3 changes how the IMPLEMENT agent is invoked — v3 projects that have customized prompts must be able to upgrade first. B4.2 introduces a new `.ralph/issues/<N>/trajectory.jsonl` file and the `core/pipeline/` namespace; v3 projects' state files at `.ralph/issue-<N>-*.{json,md}` need migration.
2. **A1.2 (structured exit codes) MUST land before B1.2, C3.1, C4.1** — they all consume the structured exit-code classification.
3. **B2.2 (idempotency log) MUST land before C1.6, C3.4** — they wrap existing engine actions with idempotency.
4. **B3.1 (worktree primitive) MUST land before C1.5, D1.1** — they are the consumers.
5. **B4.2 (trajectory writer) MUST land before B5.1 (ralph doctor) and before C1.7** — both consume trajectory events.
6. **C1.1 (package skeleton) MUST land before any C1.x move** — package must exist before files are moved into it.
7. **Pydantic is introduced at B4.1** (per spec §4.2), NOT in Phase A. Phase A stays free of new dependencies.

---

## 2. Implementation Order Within Each Phase

For each phase, this section gives: the first commit (smallest compiling, tested change), the intra-phase order with rationale, the phase-complete PR scope, and the phase-complete verification command.

### 2.1 Phase A — Quick wins (target release: `ralph-v3.1.0`)

**Goal:** Ship 8 items (A-prelude + A1–A7). Each is small and isolated; together they unblock Phase B.

**Phase A E2E gate** (per spec §10.1): A `status:ready` issue on `samdharma/ralph-e2e-test` progresses to `status:review` (or `status:blocked` for a known-bad issue).

**First commit of Phase A (smallest compiling, tested change):**

> Commit A-001: Add the `Makefile` (C2.1, partial — only `install`, `test`, `lint`, `format`, `validate` targets; defer `release`). Bump `pyproject.toml` to `3.1.0-dev` (NEW-8). Add empty `core/migrate.py` stub raising `NotImplementedError("not yet")`. Add `docs/CHANGELOG.md` (NEW-2) with one entry: "Unreleased — Phase A work in progress." Add `.github/PULL_REQUEST_TEMPLATE.md` (NEW-3) and `.github/REVIEWER_CHECKLIST.md` (NEW-4). Add `.github/workflows/e2e.yml` (NEW-5) and `.github/workflows/e2e-cleanup.yml` (NEW-6). Add `tests/e2e/test_ralph_e2e_repo.py` skeleton (NEW-7, skipped if `RALPH_E2E != 1`).
>
> Verification: `make test`, `make lint`, `make validate` all pass. The new files exist and the E2E workflow file is valid YAML.

This commit makes the project shape consistent with the spec §6 without changing behavior. All subsequent A-commits slot into this skeleton.

**Intra-phase order with rationale:**

| Order | Items | Rationale |
|-------|-------|-----------|
| 1 | NEW-1 (development_workflow.md) | Required by PR checklist #8 (spec §13.8). Must exist before any PR can be merged. |
| 2 | NEW-2, NEW-3, NEW-4, NEW-5, NEW-6, NEW-7, C2.1 (partial Makefile) | Project-shape scaffolding per spec §6.1. |
| 3 | **A-prelude** (`ralph migrate`) | MUST land before A3.3 and B4.2 per spec §11.2. Has its own scope: `core/migrate.py` (~250 LOC), `bin/ralph` dispatch (5 LOC), `tests/unit/test_migrate.py` (~150 LOC). Idempotent on re-run. |
| 4 | A1.1 → A1.2 (exit codes) | No dependencies. Foundational: A6, B1, C3, C4 all consume the structured exit-code classification. |
| 5 | A4.1 (JUnit XML) | Depends only on A1.2. Pure additive flag — no behavior change. |
| 6 | A6.1 (critical paths) | Depends only on A1.2. Pure additive — default `critical_paths = []`. |
| 7 | A5.1 (better error messages) | Independent. Cosmetic improvement, no migration needed. |
| 8 | A2.1 → A2.2 (chmod 0444) | Independent. One file commit after TEST stage. |
| 9 | A7.1 → A7.2 (drop PROGRESS.md) | Independent removal. Must come BEFORE A3.x because A3.x also touches `_assemble_subagent_prompt`, and we want each commit's diff to be reviewable in isolation. |
| 10 | A3.1 → A3.2 → A3.3 (artifact handoff) | The biggest single reliability win (ar §5.1 R1). Land last so the artifact dir convention is set; the IMPLEMENT prompt rewrite is the largest single change. |
| 11 | A4.2 (agent JUnit parsing) | Updates prompts to use JUnit XML output. Depends on A4.1 being live. |
| 12 | C2.3, C2.4 (install.sh + README) | Polish. Defer to last commit of Phase A so the install instructions match the new make targets. |
| 13 | Bump version to `3.1.0` (NEW-8) | Phase A is done; tag `ralph-v3.1.0`. |

**Last commit of Phase A:** Version bump + `CHANGELOG.md` updated with v3.1.0 entry including the "Breaking changes for v3 users" section explicitly listing `ralph migrate` as the required upgrade step (per §11.3 — see §6.1 of this plan).

**Phase A complete verification (single command sequence):**

```bash
make test          # All unit + integration tests green (NEW-7 skipped without RALPH_E2E=1)
make lint          # black, isort, flake8, mypy all pass
make validate      # Ralph validates itself
gh workflow run e2e.yml --ref ralph-v3.1  # Manual E2E trigger
# Confirm: a [e2e-phase-a-run-...] issue on samdharma/ralph-e2e-test transitions to status:review
git tag ralph-v3.1.0 && git push origin ralph-v3.1.0
gh release create ralph-v3.1.0 --generate-notes
```

### 2.2 Phase B — Reliability primitives (target release: `ralph-v3.1.1`)

**Goal:** Ship 5 items (B1–B5). These add primitives that downstream phases depend on.

**Phase B E2E gate** (per spec §10.2): Same as A, plus: `kill -9 <daemon pid>` mid-BUILD, restart daemon, observe resume at BUILD (not DESIGN). Verify `idempotency.jsonl` exists.

**First commit of Phase B:**

> Commit B-001: Add `core/pipeline/__init__.py` (empty), `core/pipeline/state.py` (empty Pydantic skeleton: `Stage(str, Enum)`, `PipelineState(BaseModel)`), `core/schemas/__init__.py`, `core/schemas/events.py` (`TrajectoryEvent` union stub with one variant). Add `pydantic>=2.0` to `pyproject.toml` (NEW-9). Bump version to `3.1.1-dev`.
>
> Verification: `make test` (existing tests untouched), `mypy core/pipeline/state.py` passes. No engine.py changes yet.

**Intra-phase order with rationale:**

| Order | Items | Rationale |
|-------|-------|-----------|
| 1 | B4.1 → B4.2 (TrajectoryEvent + writer) | First Pydantic use per spec §4.2. Other Phase B items emit events here; must be present before them. |
| 2 | B2.1 → B2.2 (run_id + idempotency log) | Independent of B4. Land second because B1.3 and B3.x benefit from idempotency. |
| 3 | B2.3 (wrap existing actions) | Touches ~10 sites in engine.py. Test exhaustively via `tests/integration/test_idempotency.py`. |
| 4 | B1.2 → B1.1 → B1.3 (retry budgets) | Depends on A1.2 (exit codes) and B2.3 (idempotent re-invocation). Build/test the retry loop with mocked agents. |
| 5 | B3.1 → B3.2 → B3.3 (worktree isolation) | Depends on A3.x and B2.3. Pre-flight check ensures `git worktree` works. |
| 6 | B4.3 (per-stage event emission) | Now wire trajectory events into every existing site. Test: `tests/integration/test_trajectory_completeness.py` asserts every stage transition produces a corresponding event. |
| 7 | B4.4 (ralph trajectory command) | Read-only consumer of B4.2. Trivial. |
| 8 | B5.1 → B5.2 (ralph doctor) | Reads trajectory file (B4.2) + recent validate runs. |
| 9 | Bump version to `3.1.1` + CHANGELOG entry. |

**Phase B complete verification:**

```bash
make test
make lint
make validate
# E2E gate (workflow_dispatch on .github/workflows/e2e.yml):
# 1. Create [e2e-phase-b-run-...] issue, run daemon, observe progress to status:review
# 2. Mid-BUILD: kill -9 <daemon pid>
# 3. Restart daemon: ralph daemon
# 4. Confirm: issue resumes at BUILD (not DESIGN)
# 5. Confirm: .ralph/issues/<N>/idempotency.jsonl exists with all expected entries
# 6. Confirm: .ralph/issues/<N>/trajectory.jsonl has all stages
git tag ralph-v3.1.1 && git push origin ralph-v3.1.1
gh release create ralph-v3.1.1 --generate-notes
```

### 2.3 Phase C — Structural simplification (target release: `ralph-v3.1.2`)

**Goal:** Ship 4 items (C1–C4). The big refactor lands here, with C1 as the highest-risk item.

**Phase C E2E gate** (per spec §10.3): Same as B, plus: a flake on `samdharma/ralph-e2e-test` quarantines itself after 2 consecutive failures. The `ralph-v3.1.2` release appears on GitHub Releases page.

**First commit of Phase C:**

> Commit C-001: Add `core/pipeline/checkpoint.py`, `core/pipeline/recovery.py` (empty stubs importing from `core.engine`). Add `tests/unit/core/pipeline/test_checkpoint.py` with one test verifying the stub imports. NO engine.py changes yet.
>
> Verification: `make test` (existing tests untouched). New test passes.

This commit introduces the `core/pipeline/` package skeleton (parallel to spec §6.1) without yet moving anything. It proves the import structure compiles.

**Intra-phase order with rationale:**

| Order | Items | Rationale |
|-------|-------|-----------|
| 1 | C3.1 → C3.2 → C3.3 → C3.4 (quarantine) | Independent of C1. Land first so the validate.py changes are isolated from the big engine.py split. |
| 2 | C4.1 (--retry flag) | Trivial additive flag. 20 LOC. |
| 3 | C2.1 (full Makefile incl. `release`) + C2.2 (scripts/release.sh) | Independent of C1. Enables the release automation that C1 will rely on. |
| 4 | C2.3 + C2.4 (install.sh + README) | Cosmetic polish. |
| 5 | **C1.2 → C1.3** (move state.py + runner.py) | First two real moves. Each commit must leave engine.py smaller and the package module equivalent. |
| 6 | **C1.4** (move stages/) | Three files: `design.py`, `build.py`, `verify.py`. Each file is a unit of one commit. |
| 7 | **C1.5** (move agents/) | Depends on A3.x and B3.x being already in engine.py (they are by this point). Four files. |
| 8 | **C1.6** (move github/) | Depends on B2.3. Four files. |
| 9 | **C1.7** (move checkpoint, metrics, recovery) | Three files. |
| 10 | **C1.8** (shrink engine.py to CLI entrypoint) | Final commit of C1. `core/engine.py` must be < 200 lines. |
| 11 | C1 cleanup: remove dead imports, verify `core/pipeline/__init__.py` re-exports public surface. | |
| 12 | Bump version to `3.1.2` + CHANGELOG entry. |

**C1 file-by-file commitment (most critical section of this plan):**

The 2700-line engine.py split is the single biggest risk. Per the spec §10.3 acceptance criterion, `core/engine.py` must be < 200 lines AND each file in `core/pipeline/` must be < 500 lines. We commit to:

- Each C1.x commit moves ONE file (or one logical group if < 200 lines).
- After each C1.x commit, `make test` MUST be green. No exceptions. If a single move breaks a test, fix the move before proceeding.
- Each moved file gets a corresponding `tests/unit/core/pipeline/<area>/test_<file>.py` BEFORE the file is moved (TDD per skill).
- No behavior change is permitted during the moves. The PR title MUST include "refactor: no behavior change."
- **Do not** merge C1 until `core/engine.py` is < 200 lines AND every test passes AND the E2E gate from Phase B still passes.

**Phase C complete verification:**

```bash
make test
make lint  # includes mypy --strict on core/pipeline/
make validate
wc -l core/engine.py core/pipeline/**/*.py  # Assert engine.py < 200, all pipeline/ files < 500
# E2E gate: same as B, plus:
# 1. Trigger a known flake (e.g., a test that times out intermittently) twice
# 2. Confirm: 3rd run auto-quarantines via tests/quarantine.yaml
# 3. Confirm: '🦠 Flake quarantined: <test_id>' issue appears on GitHub
make release PART=minor  # uses scripts/release.sh
git tag ralph-v3.1.2 && git push origin ralph-v3.1.2
gh release create ralph-v3.1.2 --generate-notes
```

### 2.4 Phase D — Performance (target release: `ralph-v3.1.3`)

**Goal:** Ship 3 items (D1–D3). The v3.1 release candidate; promote to `ralph-v3.1` (final) if green.

**Phase D E2E gate** (per spec §10.4): Same as C, plus: `ralph daemon --dry-run` exits 0 on the E2E repo. Parallel BUILD measured at <30% time of sequential.

**First commit of Phase D:**

> Commit D-001: Add `core/pipeline/stages/build.py` (parallel scaffold with a `--parallel` flag defaulting to `False`). Add `tests/unit/core/pipeline/stages/test_build.py` with one test that the flag round-trips. No behavior change yet.
>
> Verification: `make test`, `make validate`. Existing sequential path is unchanged.

**Intra-phase order with rationale:**

| Order | Items | Rationale |
|-------|-------|-----------|
| 1 | D3.1 + D3.2 (`--dry-run` on daemon + status) | Independent, trivial. Land first so E2E gate for D can use it. |
| 2 | D2.1 (single retry label) | Trivial additive. Document both labels accepted (per spec §3.5). |
| 3 | D1.1 → D1.2 → D1.3 (parallel TEST + IMPLEMENT) | The high-risk item. Depends on B3.1 (worktree primitive). Land behind a config flag `RALPH_PARALLEL_BUILD=true` (default false) so it can be A/B tested. After measurement confirms ≥30% speedup, flip the default. |
| 4 | Bump version to `3.1.3` + CHANGELOG entry. Promote to `ralph-v3.1` (final). | |

**Phase D complete verification:**

```bash
make test
make lint
make validate
# E2E gate (all of C, plus):
# 1. ralph daemon --dry-run exits 0 on samdharma/ralph-e2e-test
# 2. Parallel BUILD: RALPH_PARALLEL_BUILD=true ralph daemon --issue=<N>
# 3. Confirm: wall-clock reduced by ≥30% vs sequential on the same issue
git tag ralph-v3.1.3 && git push origin ralph-v3.1.3
gh release create ralph-v3.1.3 --generate-notes
# Final promotion:
git tag ralph-v3.1 && git push origin ralph-v3.1
```

---

## 3. Risks and Mitigations

Each high-risk change has an explicit mitigation. Mitigations are pre-committed; if a risk materializes during implementation, the mitigation triggers BEFORE the next commit.

### R-1. **A3.3 — Drop `pi --continue` Mode B** (HIGH risk; largest single reliability win per ar §5.1 R1)

- **Risk:** The agent invocation path is the most heavily-used code path in engine.py. Changing it from `--continue` to artifact-based can break projects that depend on session-level state (e.g., customized prompts that rely on session context).
- **Mitigation:**
  - Write `tests/integration/test_artifact_handoff.py` BEFORE changing `_run_implement_subagent`. The test mocks both `pi` and `kimi`, asserts the assembled command contains no `--continue` and no `--session` flags, and asserts the artifact directory is populated.
  - Add an integration test that runs both pi and kimi against a fixture issue (gated on `RALPH_E2E_AGENT=1`).
  - E2E gate at the end of Phase A exercises both agents (one issue with `RALPH_AGENT=pi`, one with `RALPH_AGENT=kimi`).
  - If a regression is detected post-merge, the rollback path is the previous commit; the session files (`session-<N>.jsonl`) are still on disk for one cycle.

### R-2. **C1 — Split `engine.py` into `core/pipeline/` package** (HIGH risk; 2700-line refactor per ar §5.3 S1)

- **Risk:** Behavior change during the move. Tests don't cover every code path. Merge breaks working pipelines.
- **Mitigation:**
  - **Character-by-character file moves**, one file per C1.x commit. Each commit is independently revertable.
  - **After every C1.x commit, `make test` MUST be green.** If not, fix the move before the next commit (per skill `incremental-implementation` Rule 2).
  - **Snapshot tests** at `tests/integration/test_engine_snapshots.py` record exit codes and stdout patterns from the v3.1.1 engine BEFORE C1 begins. The test runs every C1.x commit and asserts identical output. Fixtures live at `tests/integration/fixtures/engine_snapshots/` (resolved in §8, Q1) — git-tracked, ~100-300 JSON files, generated ONCE by `scripts/generate_engine_snapshots.py` against the pre-C1 engine.py, then the script is removed. The snapshot test file is temporary and removed after C1 ships.
  - **Do not** combine C1.x commits. Each commit's diff must show ONLY the file move + import adjustments.
  - **Review burden:** the C1 PR will be large. Per spec §13 the reviewer must verify "no behavior change" via the snapshot test results linked in the PR description.

### R-3. **`ralph migrate` running on real v3 projects** (MEDIUM-HIGH risk; spec §11.5 calls this out)

- **Risk:** v3 projects may have state files we haven't enumerated (e.g., manually placed files, edge cases in `ralph init`). Migration could destroy data.
- **Mitigation:**
  - **`ralph migrate --dry-run` ships first** (per spec §5.2). It outputs a JSON report listing every action it WOULD take. No file system changes.
  - **Idempotency:** running `ralph migrate` twice produces the same end state. Tested in `tests/integration/test_migrate_idempotent.py`.
  - **Refuses to run if daemon PID file exists.** Prevents race with live daemon.
  - **Auto-archive before move:** any v3 file that would be renamed/moved is first copied to `.ralph/migration-archive/<timestamp>/`. (This is a 30-line addition to `core/migrate.py`.)
  - **Backup retention (resolved in §8, Q5):** archives are **never auto-pruned**. The `.ralph/` directory is gitignored and lives only on the operator's machine; even dozens of archives are unlikely to exceed a few MB. Operators who want to clean up run the documented one-liner in `docs/development_workflow.md`:

    ```bash
    # Remove all migration archives (irreversible; do this only when confident)
    rm -rf .ralph/migration-archive/
    ```
  - **Per spec §13 checklist item 9 (v3.1.0 only):** The Phase A PR description MUST link to E2E-style test output demonstrating `ralph migrate` works against a real v3 project. See §5.4 of this plan for how that test is set up.

### R-4. **Pydantic v2 introduction** (MEDIUM risk; touches every state-holding module per spec §4.2)

- **Risk:** Pydantic v2 has a learning curve; mypy strict mode may flag pre-existing dict-typed code.
- **Mitigation:**
  - **Pydantic lands at B4.1**, NOT in Phase A. Phase A stays dependency-free.
  - **First Pydantic use is the simplest possible:** `TrajectoryEvent` union type, no validation logic. The model is read-only at first.
  - **`mypy --strict` only on `core/pipeline/`, NOT on legacy code.** Per spec §7.3, `core/init.py` is explicitly relaxed.
  - **Pydantic adoption is incremental:** each B.x and C.x commit that introduces new state may use Pydantic; pre-existing state stays as dicts until the file is touched for other reasons. No "convert everything to Pydantic" PR.
  - **Pydantic dep is `>=2.0,<3.0`** — pin to a major version. Document in `pyproject.toml`.

### R-5. **B3 — Mechanism-enforced isolation via git worktree** (MEDIUM risk; per ar §5.1 R4)

- **Risk:** `git worktree` may not work in all repo layouts (e.g., shallow clones, submodules, certain CI runners). Read-only `src/` mount may not be supported on the user's filesystem.
- **Mitigation:**
  - **Pre-flight check at daemon startup:** `git worktree add /tmp/ralph-wt-test HEAD && git worktree remove /tmp/ralph-wt-test`. If this fails, daemon emits a clear error and suggests the workaround (or refuses to start with a clear message).
  - **On read-only mount failure (Linux):** fall back to `chmod -R 0500 src/`.
  - **macOS-specific behavior (resolved in §8, Q2):** APFS does not enforce the standard Unix read-only file mode the same way as Linux. macOS uses `chmod -R 0500 src/` and **accepts policy-only read isolation** — write/edit attempts return `EACCES` (mechanism-enforced for writes) but read attempts succeed at the syscall level (policy-only for reads). The daemon logs `WARNING: macOS read isolation is policy-only; src/ may be readable by the agent` at startup and emits a metric for visibility. Linux continues to use `mount --bind src /tmp/ralph-wt/src && mount -o remount,ro,bind /tmp/ralph-wt/src` for true mechanism isolation on both reads and writes.
  - **TEST in `tests/integration/test_worktree_isolation.py`** asserts: (a) worktree created; (b) `src/` is read-only at the FS level; (c) agent attempting to write to `src/` gets `Permission denied`; (d) teardown leaves no orphan worktree.

### R-6. **B1 — Per-stage retry budgets with escalation** (MEDIUM risk; per ar §5.1 R2)

- **Risk:** Aggressive retry on transient failures could mask real regressions. L1 auto-retry on timeout could loop indefinitely on a hung test.
- **Mitigation:**
  - **Cap each retry level explicitly.** L1: 1 retry. L2: 2 retries. L3: 0 retries (immediate block). Per spec §10.2.
  - **All retry attempts are recorded** in `.ralph/issues/<N>/failure_history.jsonl` (per spec §6.2). A human reading the trajectory can see every retry and decide if the threshold is wrong.
  - **Configuration knob:** `.ralph/config.toml` gains `[retry] l1_max_attempts = 1`, `[retry] l2_max_attempts = 2`. Operators can tighten (down to 0) or loosen (up to 3) without code changes.
  - **Tests:** `tests/integration/test_retry_escalation.py` mocks every exit code and asserts the correct retry-or-block decision.

### R-7. **C3 — Quarantine auto-add on 2 consecutive failures** (MEDIUM risk; per ar §5.2 P2)

- **Risk:** Auto-quarantining masks regressions. A real bug (not a flake) could be silently de-prioritized.
- **Mitigation:**
  - **Quarantine is auto-added but auto-removed after 7 days** (per spec §5.5 of architectural review + §10.3 acceptance criterion C3.3).
  - **Each auto-quarantine posts a GitHub issue:** `🦠 Flake quarantined: <test_id>` with the two failing logs linked. A human sees every quarantine event.
  - **`--strict` flag** on `ralph validate` disables quarantine for that run (use case: "I want this to fail loudly right now").
  - **Quarantine file is git-tracked** (`tests/quarantine.yaml`). Every change is reviewed in a PR.

### R-8. **D1 — Parallel TEST + IMPLEMENT via git worktree** (HIGH risk; per ar §5.2 P5)

- **Risk:** Conflict resolution between two worktrees is genuinely hard. The merged result may be broken.
- **Mitigation:**
  - **Ship behind `RALPH_PARALLEL_BUILD=true` config flag**, defaulting to `False` (per §2.4 of this plan). Operators opt in.
  - **Path-domain merge policy (resolved in §8, Q3):**
    - Conflicts in `tests/` → TEST wins (`git merge -X ours -- tests/`)
    - Conflicts in `src/` → IMPLEMENT wins (`git merge -X theirs -- src/`)
    - Conflicts anywhere else (`docs/`, root-level `__init__.py`, etc.) → **FAIL FAST**: abort parallel run, fall back to sequential, emit a metric. The overlap indicates the design spec wasn't precise enough; D1 surfaces this rather than papering over it.
  - **Pre-merge overlap detection:** `git diff --name-only` between the two worktrees. If any path appears in both lists AND is not under `src/` or `tests/`, FAIL FAST before attempting merge.
  - **Post-merge validation:** after the merge, run `ralph validate --tier=targeted` again. If it fails, fall back to sequential and emit a metric.
  - **A/B measurement required** before flipping the default. E2E gate requires ≥30% speedup on a real issue.

### R-9. **README install instructions change (C2)** (LOW-MEDIUM risk; spec §3.2)

- **Risk:** Existing users on the `curl | bash` flow may break if we don't preserve `bin/ralph`. Spec §3.7 explicitly says bash dispatcher is kept through v3.1.x.
- **Mitigation:**
  - **`bin/ralph` is preserved.** Document both flows in README: (a) `make install` for new users, (b) `bin/ralph` symlink for existing users.
  - **Drop `curl | bash` only at v3.2.** This plan does NOT touch the install script's curl entry point during v3.1.x.
  - **Document the change** in CHANGELOG: "C2 changes the recommended install path but preserves the `bin/ralph` symlink for backward compatibility."

### R-10. **E2E test dependency on real GitHub repo** (LOW risk; mitigations in spec §14)

- **Risk:** PRs may be merged without E2E verification if the CI gate isn't enforced.
- **Mitigation:**
  - **PR template checkbox #6** (per spec §13.6) is checked by the reviewer. For phase-complete PRs the box is REQUIRED.
  - **`.github/workflows/e2e.yml` runs on push to `ralph-v3.1`** and on `workflow_dispatch`. Failure blocks merge via branch protection (manual setup step; documented in `docs/development_workflow.md`).
  - **E2E failures are visible on the PR** via the GitHub Actions summary.

### R-11. **`ralph doctor` accuracy** (LOW risk; per spec §3.10)

- **Risk:** False positives (flag a recently-fixed issue as stuck) erode trust.
- **Mitigation:**
  - **All doctor output is advisory.** Exit codes 0/1/2 are the only machine-readable signal; humans decide.
  - **Configurable thresholds:** stuck issue timeout, repeat-failure threshold, etc. all come from `.ralph/config.toml`.
  - **`--quiet` flag** suppresses non-critical diagnostics (for CI use).
  - **Exit-code mapping (resolved in §8, Q4):** final exit code = `max(contributions)` across the 5 diagnostic categories:

    | Diagnostic category | Exit contribution |
    |--------------------|-------------------|
    | Stuck issues (>1 hour in DESIGN/BUILD/VERIFY) | 1 (warning) |
    | Long-blocked issues (>7 days) | 1 (warning) |
    | Repeat failures (same test fails 3+ times in 30 days) | 1 (warning) |
    | Orphan subprocesses (zombie `pi`/`kimi` from `kill -9`) | 2 (error) |
    | Environment checks (missing labels, no gh auth, no git remote) | 2 (error) |

    Examples: a healthy daemon → exit 0. A daemon with one stuck issue and one long-blocked issue → exit 1. A daemon with one orphan subprocess (regardless of other warnings) → exit 2. A daemon with missing labels AND a long-blocked issue → exit 2. Matches the systemd / Nagios / common-lint-tool tri-state convention.

### R-12. **Single retry label confusion (D2)** (LOW risk; spec §3.5 calls this out)

- **Risk:** Operators don't know which label to use. Old labels may be silently ignored.
- **Mitigation:**
  - **Both labels work in v3.1.** Engine recognizes `status:retry` (new) AND `status:build-retry`, `status:verify-retry` (existing).
  - **CHANGELOG entry** explicitly documents: "Both `status:retry` and the existing `status:build-retry` / `status:verify-retry` are accepted in v3.1. A future v3.2 may deprecate the old labels."
  - **`ralph doctor` lists which labels exist** on the repo.

---

## 4. Parallel vs Sequential Work

This section identifies which items can be worked on in parallel by multiple contributors and which have hard ordering. We ship ONE PR per phase per spec §3.8, but the PLAN surfaces parallelism for development velocity (e.g., two engineers can split work across two consecutive days).

### 4.1 Phase A parallelism

| Item | Parallel with | Coordination required | Notes |
|------|---------------|----------------------|-------|
| A-prelude (`ralph migrate`) | A1, A2, A4, A5, A6, A7 (all) | None — A-prelude writes only `core/migrate.py` and `bin/ralph`; A1-A7 touch different files | A-prelude must land BEFORE A3.3 in the final PR, but in development branches it can be worked on in parallel |
| A1.1 → A1.2 | A4 (depends on A1.2) | A1.2 and A4 both touch `core/validate.py` but different functions | **Sequential in code**, but A4 work can START (test stubs) before A1.2 is merged |
| A2.1 → A2.2 | A1, A4, A5, A6, A7 | None — A2 touches `core/engine.py:1472` and `_run_test_subagent` | Fully parallel |
| A4.1 | A1.2 (must be merged first); A5, A6, A7 | After A1.2 merges, A4.1 work is independent | **Sequential after A1.2** |
| A5.1 | A1, A2, A4, A6, A7 | None — touches `_write_stage_report` and `_format_stage_failure` in `core/engine.py` | Fully parallel; can be developed on a branch that rebases onto A1/A2/A4 merges |
| A6.1 | A1.2 (must be merged first); A4, A5, A7 | After A1.2 merges, A6.1 work is independent | **Sequential after A1.2** |
| A7.1 → A7.2 | All other A items | A7.1 removes `_update_progress_board` (~150 lines). This function is NOT called by other A items being developed in parallel, BUT it is in the same file. **Coordinate via separate branches and rebase before final merge.** | Mostly parallel; conflict risk on `core/engine.py` imports |
| A3.1 → A3.2 → A3.3 | None — A3 is the last A item per §2.1 order | A3.x touches `_run_implement_subagent` and `_assemble_subagent_prompt`. Both are NOT touched by A1/A2/A4/A5/A6/A7. So in theory A3 is parallel too. **But** A3 is the largest single change; we sequence it last so its commit is reviewable in isolation. | Sequenced last by policy, not by dependency |

**Summary for Phase A:** Up to 4 contributors can work in parallel: (1) A-prelude + A1, (2) A2 + A7, (3) A4 + A6, (4) A5 + (later) A3. Final PR is a single squash merge that combines all branches.

### 4.2 Phase B parallelism

| Item | Parallel with | Coordination required |
|------|---------------|-----------------------|
| B4.1 → B4.2 | B2.1, B2.2, B5 (skeleton) | None — different files |
| B2.1 → B2.2 | B4.x, B5 (skeleton) | None |
| B2.3 | None — wraps ~10 sites in engine.py that other B items also touch | **Sequential** (do after B1.x and B3.x to avoid double-touching) |
| B1.x | B3.x (different engine.py functions) | B1.x and B3.x both modify `_run_*_subagent` paths. Coordinate via separate branches. |
| B3.1 → B3.2 → B3.3 | B1.x | See above |
| B4.3 | All — emits events at existing engine.py call sites | **Sequential last** (after B1.x, B2.3, B3.x are stable, then wire events into them) |
| B4.4 (ralph trajectory) | B5 (ralph doctor) | Both read trajectory.jsonl. **Parallel.** |
| B5.1 → B5.2 | B4.4 | Parallel |

**Summary for Phase B:** Two parallel streams: (Stream 1: B1.x, Stream 2: B3.x). Both share engine.py but different functions; use separate branches and rebase before final merge. B2.x can be developed by a third contributor in parallel. B4.x and B5.x are sequenced last.

### 4.3 Phase C parallelism

| Item | Parallel with | Coordination required |
|------|---------------|-----------------------|
| C3.1–C3.4 | C4.1, C2.x | C3 touches `core/validate.py` and `core/engine.py` (quarantine issue post); C4 touches only `core/validate.py`. **Coordinate C3 and C4 on the same file.** |
| C4.1 | C3.x, C2.x | Same file as C3. Coordinate. |
| C2.x | C3, C4, C1 (skeleton) | Different files. Parallel. |
| **C1.x** | **None** | **Strictly sequential.** Each C1.x commit depends on the previous. Per §2.3, C1 is the highest-risk refactor; we serialize it on purpose. |

**Summary for Phase C:** Three contributors can work in parallel: (1) C3.x, (2) C4.1, (3) C2.x. C1.x is single-track and consumes the most calendar time. Calendar estimate: C1.x is 10 working days; C3.x + C4.1 + C2.x is ~7 working days in parallel.

### 4.4 Phase D parallelism

| Item | Parallel with | Coordination required |
|------|---------------|-----------------------|
| D3.1, D3.2 | D2.1 | Different files. Parallel. |
| D2.1 | D3.x | Different files. Parallel. |
| **D1.x** | **None** | **Strictly sequential.** Per §2.4, D1 is behind a config flag and the merge logic is hard to parallelize. |

**Summary for Phase D:** Two contributors can work in parallel: (1) D3.x, (2) D2.1. D1.x is single-track and consumes the most calendar time.

### 4.5 Hard orderings (do not violate)

These are non-negotiable sequencing rules:

1. `ralph migrate` → A3.3, B4.2 (per spec §11.2)
2. A1.2 (structured exit codes) → B1.x, C3.x, C4.1 (consumers)
3. B2.2 (idempotency log) → C1.6, C3.4, D3 (consumers)
4. B3.1 (worktree primitive) → C1.5, D1.x (consumers)
5. B4.2 (trajectory writer) → B4.3, B4.4, B5.x, C1.7 (consumers)
6. C1.1 (package skeleton) → every other C1.x move
7. C1.x files MUST be moved in the order: state → runner → stages → agents → github → checkpoint/metrics/recovery → engine.py shrink. Each move must compile before the next.

---

## 5. Verification Checkpoints

### 5.1 Between-item checkpoints (within a phase)

After every commit in any phase, the following commands MUST pass:

```bash
make test-unit           # <1 minute; catches regressions in the changed module
make lint                # <30 seconds; catches style + mypy regressions
# If the commit touched core/engine.py or core/pipeline/:
make test-integration    # <5 minutes; catches behavioral regressions
```

If any of the above fails, fix before committing the next increment. Per skill `incremental-implementation` Rule 2 (keep it compilable).

### 5.2 Between-phase checkpoints

After every phase PR is merged (before tagging the release), the full gate runs:

```bash
make test                # unit + integration
make lint
make validate            # Ralph validates itself using --tier=targeted
gh workflow run e2e.yml --ref ralph-v3.1   # Manual E2E trigger
# Confirm the E2E phase-tagged issue reaches status:review
```

For Phase B and later, additional E2E criteria per §2.2, §2.3, §2.4 of this plan.

### 5.3 Phase-complete PR verification (per spec §13)

For each phase-complete PR, the PR description must include:

| # | Check | Verification artifact |
|---|-------|----------------------|
| 1 | Spec section referenced | PR description links to spec §10.X for the phase |
| 2 | Phase declared | PR description states "Phase A/B/C/D" |
| 3 | Acceptance criteria met | PR description checks off each item in spec §10 |
| 4 | `make test` green | CI link to passing workflow run |
| 5 | `make lint` green | CI link to passing workflow run |
| 6 | E2E gate passed | Link to E2E run on `samdharma/ralph-e2e-test` |
| 7 | `CHANGELOG.md` updated | PR shows diff to `docs/CHANGELOG.md` |
| 8 | Migration story documented (if applicable) | PR shows diff to `docs/development_workflow.md` OR says "no migration needed" |

For v3.1.0 specifically (check #9, per spec §13):

| 9 | Migration tested on a real v3 project | PR description links to test output of `ralph migrate` on a v3-format project |

### 5.4 Setting up the v3.1.0 migration test (checklist #9)

This test is unique to v3.1.0 and is the most concrete deliverable to set up before Phase A ships.

**Test setup steps:**

1. **Create a v3 fixture repo** at `samdharma/ralph-v3-migration-fixture` (or use a git tag in this repo at v3.0.0). The fixture contains:
   - `.ralph/issue-1-tests.json` (a sample v3 test tracking file)
   - `.ralph/issue-1-report.md` (a sample v3 failure report)
   - `.ralph/session-1.jsonl` (a sample v3 session file, to be deprecated in A3)
   - `docs/agent/prompts/test.md`, `implement.md`, `verify.md` matching the v3 defaults byte-for-byte
   - `.ralph/config.toml` WITHOUT `[validate] critical_paths` (to verify A6 default behavior)

2. **Test script:** `tests/integration/test_v3_migration.py`

   ```python
   def test_v3_migration_full_cycle(tmp_path):
       # 1. Set up v3 fixture in tmp_path
       # 2. Verify pre-migration state: v3 paths exist
       # 3. Run `ralph migrate --dry-run`, parse JSON report
       #    Assert: report lists expected migrations
       # 4. Run `ralph migrate`, assert idempotent on second run
       # 5. Verify post-migration state:
       #    - .ralph/issue-1-tests.json moved/renamed per spec
       #    - .ralph/session-1.jsonl archived (per R-3 mitigation)
       #    - .ralph/migration-archive/<timestamp>/ contains original files
       #    - Stage prompts match v3.1 defaults (regenerated)
       # 6. Run `ralph daemon --dry-run` on the migrated project
       #    Assert: exits 0
       # 7. Optionally: run an actual `status:ready` issue through the pipeline
       #    Assert: reaches status:review (full end-to-end)
   ```

3. **Run the test in CI** as part of the Phase A PR check. The PR description links to the test output (per check #9).

### 5.5 E2E gate for each phase

Per spec §8.5, the E2E test at `tests/e2e/test_ralph_e2e_repo.py` is gated on `RALPH_E2E=1`. The phase-specific acceptance criteria:

| Phase | Additional E2E check (beyond spec §10) |
|-------|----------------------------------------|
| A | Issue progresses DESIGN → BUILD → VERIFY → `status:review`. Trajectory file (B4.x) NOT yet required at A; git log shows the 7 changes. |
| B | Mid-BUILD `kill -9`; restart; resume at BUILD (not DESIGN). `idempotency.jsonl` exists. `trajectory.jsonl` (B4) exists. |
| C | A flake on `samdharma/ralph-e2e-test` quarantines itself after 2 consecutive failures. `ralph-v3.1.2` release appears on GitHub Releases page. |
| D | `ralph daemon --dry-run` exits 0 on E2E repo. Parallel BUILD measured at <30% of sequential wall-clock time. |

The E2E test must be run for EACH phase; the test code extends to cover phase-specific checks. Each phase's `.github/workflows/e2e.yml` invocation updates the test's expectations.

---

## 6. Resolutions of Deferred Decisions

Spec §11 deferred four decisions to the PLAN phase. This section resolves each.

### 6.1 Phase A first PR scope (spec §11.1)

**Decision: ONE PR per phase.**

Rationale: Phase A has 8 items (A-prelude + A1–A7) totaling ~6.5 days of work (per architectural review §7 estimates: A1 0.5d, A2 0.5d, A3 3d, A4 0.5d, A5 0.5d, A6 1d, A7 0.5d, A-prelude ~1d). Splitting into 2-3 PRs would force intermediate merges where E2E cannot pass because the suite isn't complete. The 8-item single PR is bounded — reviewers can verify each item against spec §10.1's checklist.

The PR will be large (~1500 LOC of changes plus tests) but each item has a clear acceptance criterion in spec §10.1. Reviewers consult `.github/REVIEWER_CHECKLIST.md` (NEW-4) for verification guidance.

### 6.2 Migration ordering (spec §11.2)

**Decision: Land `ralph migrate` as item A-prelude, BEFORE A1-A7 in the same Phase A PR.**

Rationale: Spec §11.2 explicitly states "`ralph migrate` must land before any schema change that breaks v3. Specifically: A3 (artifact handoff) and B4 (trajectory schema) are the breaking changes." Sequencing `ralph migrate` as A-prelude (the first item in Phase A) ensures:

- v3 users have the migration tool available immediately on upgrading to v3.1.0.
- The migration tool can be tested against a real v3 project (checklist #9) before the breaking changes ship.
- The Phase A PR review can verify the migration path as part of acceptance.

In the development workflow, A-prelude is developed in its own branch and merged FIRST into the Phase A integration branch, then A1-A7 follow. Final PR is a single squash merge that shows A-prelude at the top of the commit log.

### 6.3 CHANGELOG.md initial content (spec §11.3)

**Decision: Yes, include a "Breaking changes for v3 users" section explicitly listing `ralph migrate` as the required upgrade step.**

CHANGELOG structure for v3.1.0:

```markdown
# Changelog

## Unreleased

## 3.1.0 — 2026-MM-DD (Phase A complete)

### Breaking changes for v3 users

**Action required:** Run `ralph migrate` once after upgrading to v3.1.0.

```bash
git clone https://github.com/samdharma/Ralph_loop
cd Ralph_loop
git checkout ralph-v3.1
./scripts/install.sh
cd <your-project>
ralph migrate             # Migrate v3 state files and stage prompts
ralph daemon              # Start as usual
```

The migration tool is idempotent and supports `--dry-run`. It will not run if the daemon is active. It migrates state files (`.ralph/issue-<N>-*.json|.md`) to the new per-issue directory layout, regenerates stage prompts that match v3 defaults (leaves customized prompts alone with a warning), and creates a backup at `.ralph/migration-archive/<timestamp>/`.

### New features
- A1: Pytest exit-code classification (validate.py emits structured JSON)
- A3: Artifact-based agent handoff (no more session file fragility)
- ... (etc for A2, A4, A5, A6, A7)

### Bug fixes
- (none — A3 in particular CHANGES behavior, see above)

### Deprecated
- `docs/agent/PROGRESS.md` is no longer written; use GitHub labels + Kanban board
- `.ralph/session-<N>.jsonl` is deprecated in favor of artifacts (kept for migration)
```

### 6.4 Test repo archival (spec §11.4)

**Decision: Keep the same E2E test repo (`samdharma/ralph-e2e-test`) for v3.1.x. Defer the v3.2-specific test repo decision to v3.2 planning.**

Rationale:

- The E2E repo's 8 labels (`ready|design|build|verify|review|blocked` + 2 retry variants) are unchanged in v3.1.x.
- D2 adds `status:retry` ADDS a new label; existing labels still work. The repo can absorb the new label without re-architecting.
- The existing 6 historical closed issues serve as a stable baseline for E2E comparisons across versions.
- Creating a new repo would fragment the issue history and require re-establishing labels + Project board + permissions.
- If v3.2 introduces changes that conflict with the existing label set (unlikely but possible), we can revisit then.

**Action item:** Update `docs/development_workflow.md` (NEW-1) to document the E2E repo convention: "All E2E tests use `samdharma/ralph-e2e-test` (master branch). The repo's 8-status label set is canonical for v3.1.x."

---

## 7. Out-of-Scope Reminders

Per spec §2.2 and §9, the following are EXPLICITLY OUT OF SCOPE for this plan. If implementation surfaces a need for any of these, surface it as a new spec section; do NOT incorporate into this plan.

- Replacing the GitHub-as-state-store design (spec §2.2)
- Replacing the per-issue design spec files (`docs/designs/<N>.md`) (spec §2.2)
- Replacing provider-error handling (spec §2.2)
- Adding a web UI (spec §2.2)
- Adding new status labels (spec §9.1.5; with the exception of D2's additive `status:retry`, per spec §3.5)
- Multi-tenant support, distributed daemon, webhook triggers, non-pi/kimi agent support, typed issue schema (spec §2.3, deferred to v3.2+)
- Any of the 23 recommendations NOT in scope for v3.1.x (the spec is exhaustive; nothing else is approved)

---

## 8. Resolved Plan-Time Decisions

The following questions emerged during planning and have been resolved (each via a one-at-a-time interview on 2026-06-27). All resolutions are reflected in the relevant mitigation sections above.

| # | Question | Resolution | Where in plan |
|---|----------|-----------|---------------|
| 1 | Snapshot test storage location for C1 | `tests/integration/fixtures/engine_snapshots/` — git-tracked, generated ONCE by `scripts/generate_engine_snapshots.py`, then script removed | R-2 mitigation (§3) |
| 2 | macOS read-only `src/` mount behavior | Option A: Linux uses `mount -o ro` (true mechanism isolation); macOS uses `chmod -R 0500 src/` + warning logged (writes enforced, reads policy-only) | R-5 mitigation (§3) |
| 3 | D1 parallel conflict-resolution policy | Option C: path-domain separation — `tests/` → TEST wins, `src/` → IMPLEMENT wins, anywhere else → FAIL FAST and fall back to sequential | R-8 mitigation (§3) |
| 4 | `ralph doctor` exit-code mapping | Option A: 0 = healthy, 1 = warnings, 2 = errors; per-category contribution table in R-11 | R-11 mitigation (§3) |
| 5 | `ralph migrate` backup retention | Option A: never auto-prune; documented `rm -rf .ralph/migration-archive/` one-liner in `docs/development_workflow.md` | R-3 mitigation (§3) |

No open questions remain. The plan is complete and ready for review.

---

## 9. Plan Acceptance Checklist

Before approving this plan, confirm:

- [ ] Every component in the spec is named in §1.1 with a path.
- [ ] Every dependency is captured in §1.2 with hard-ordering rules in §1.3.
- [ ] Every phase has a first commit, intra-phase order, last commit, and verification (§2).
- [ ] Every high-risk change has a risk and mitigation (§3).
- [ ] Parallelism is surfaced for each phase (§4) and hard orderings are explicit (§4.5).
- [ ] Verification checkpoints exist for between-item, between-phase, and PR gates (§5).
- [ ] The v3.1.0 migration test setup is concrete (§5.4).
- [ ] The four deferred decisions are resolved (§6).
- [ ] Out-of-scope items are restated (§7).
- [ ] All open questions are surfaced but not blocking (§8).

**Approval of this plan authorizes the TASKS phase to decompose each item in §1.1 into test-first, file-level tasks. Implementation does not begin until TASKS is reviewed.**

---

*Last updated: 2026-06-27. Awaiting human review before TASKS phase begins.*