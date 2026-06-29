# Changelog

All notable changes to Ralph are documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and Ralph adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 3.1.3 — 2026-06-28 (Phase D complete — release candidate)

### New features

- **D1 (P5):** Parallel TEST + IMPLEMENT scheduler. When
  `RALPH_PARALLEL_BUILD=true` (or `[performance] parallel_build = true`
  in `.ralph/config.toml`), the BUILD stage runs TEST and IMPLEMENT in
  two separate git worktrees concurrently, then merges the results
  per the path-domain policy (`tests/` → TEST wins, `src/` → IMPLEMENT
  wins, anywhere else → FAIL FAST and fall back to sequential). Wall-
  clock BUILD time on typical issues is reduced; per-issue measurement
  is left to operators via the new `build_parallel_started` and
  `build_fallback_to_sequential` metrics emitted to
  `logs/ralph_metrics.jsonl`. The flag defaults to **off**; operators
  opt in. Per plan §3 R-8 the E2E gate must demonstrate ≥30% speedup
  before the default flips.
- **D2 (U5):** Single `status:retry` label (additive). The new
  `status:retry` label works alongside the existing
  `status:build-retry` and `status:verify-retry` labels. No
  deprecation in v3.1 — the old labels continue to work. Per spec
  §3.5 this is the only allowed `status:*` label addition in v3.1.x.
- **D3 (U3):** `ralph daemon --dry-run` and `ralph status --dry-run`.
  Dry-run walks the pipeline up to (but not including) agent
  invocation. It validates `gh auth status`, `git remote -v`, and the
  presence of all 8 status labels on the repo (via `gh label list`).
  Useful for CI health checks. No agent subprocess (`pi` / `kimi`)
  is invoked. Exit codes: 0 = healthy, 2 = gh auth failed,
  3 = git remote missing, 4 = labels missing, 5 = `.ralph/` missing.

### Internal changes

- New helpers in `core/pipeline/stages/build.py`:
  `_is_parallel_build_enabled`, `_parallel_create_worktrees`,
  `_parallel_run_subagents`, `_conflict_policy`,
  `_post_parallel_validate`.
- New helpers in `core/pipeline/agents/base.py`: `merge_worktrees`,
  `OverlapError`, `_classify_paths`. The merge applies
  `git merge -X ours -- tests/` (TEST wins) and
  `git merge -X theirs -- src/` (IMPLEMENT wins) per plan §3 R-8.
- New helper in `core/pipeline/daemon.py`: `dry_run` — validates
  gh/git/labels/paths without invoking the agent. Wired into the
  `--dry-run` flag on the `daemon` subcommand.
- New helper in `core/status.py`: `_dry_run` — same logic for the
  `status` subcommand. Status does NOT list issues on dry-run.
- `core/pipeline/issue_ops.RETRY_LABEL_MAP` now includes
  `status:retry` → `build` (additive, per D2 / spec §3.5). Old
  labels continue to map to their existing stages.
- `fetch_retry_issue()` now returns `(issue, resume_stage, label)`
  (3-tuple) so the daemon can transition off the exact matched label.
- `create_worktree()` and `_worktree_path()` accept `int | str` so
  the parallel scheduler can pass `"{N}-test"` / `"{N}-impl"`.

### Deprecated

- None.

## 3.1 — 2026-06-28 (Stable release)

The Ralph v3.1 series ships four phases of reliability, structural,
and performance improvements on top of the v3 baseline. v3.1 is the
recommended version for new and existing projects.

### Series summary

- **v3.1.0 (Phase A — Quick wins, 2026-06-27):** `ralph migrate`,
  pytest exit-code classification, hard-block test tampering,
  artifact-based agent handoff, JUnit XML, better failure comments,
  critical-path test set, drop legacy `PROGRESS.md`.
- **v3.1.1 (Phase B — Reliability primitives, 2026-06-27):**
  Per-stage retry budgets, idempotency keys, mechanism-enforced
  isolation (worktree + read-only `src/`), single trajectory file,
  `ralph doctor`.
- **v3.1.2 (Phase C — Structural simplification, 2026-06-28):**
  `engine.py` split into `core/pipeline/` package (every module
  <500 lines), GitHub Releases distribution, quarantine for known-
  flaky tests, `--retry` validation flag.
- **v3.1.3 (Phase D — Performance, 2026-06-28):** Parallel TEST +
  IMPLEMENT (opt-in), single `status:retry` label, `ralph --dry-run`.

### Migration notes

**Action required for v3 users:** Run `ralph migrate` once after
upgrading to v3.1 (introduced in v3.1.0). The migration is
idempotent and supports `--dry-run`. It migrates state files
(`.ralph/issue-<N>-*.json|.md`) to the per-issue directory layout
introduced in v3.1 and regenerates stage prompts that match the v3
defaults (customized prompts are left alone with a warning). A
backup is created at `.ralph/migration-archive/<timestamp>/`.

```bash
git clone https://github.com/samdharma/Ralph_loop
cd Ralph_loop
git checkout ralph-v3.1
./scripts/install.sh
cd <your-project>
ralph migrate             # Required for v3 users
ralph daemon              # Start as usual
```

### Contributors

Thanks to everyone who tested and reviewed the v3.1 series.

## 3.1.2 — 2026-06-28 (Phase C complete)

### Refactor

- **C1 (S1):** Split `engine.py` into `core/pipeline/` package.
  - New subpackages: `core/pipeline/{state,runner,stages,agents,github}`
    and `core/pipeline/{checkpoint,metrics,recovery}.py`.
  - `core/pipeline/__init__.py` re-exports the full public surface
    (Stage, PipelineState, run_loop, DesignStage, AgentBase, etc.)
    so callers can do `from core.pipeline import X`.
  - **No behavior change** in the C1 refactor. All 209 unit tests + 52
    integration tests pass, and the snapshot regression guard (38 active
    fixtures) detects no behavior drift.
  - `core/engine.py` reduced to a ~190-line CLI entrypoint. Business
    logic moved to focused `core/pipeline/` modules:
    `runner.py`, `daemon.py`, `issue_ops.py`, `git_ops.py`,
    `reporting.py`, `test_tracking.py`, `artifacts_ops.py`,
    `prompts.py`, `shell.py`, plus the existing `state`, `retry`,
    `providers`, `checkpoint`, `metrics`, `recovery`, `github/`,
    `agents/`, and `stages/` subpackages. Every module stays <500 lines.
  - mypy passes on `core/validate.py` and all of `core/pipeline/`.
  - The snapshot regression guard was regenerated where the fixed
    import cycle changed the expected end state (imports of
    `core.engine` now succeed).

### New features

- **C2 (S2):** Distribute via GitHub Releases.
  - New `scripts/release.sh` automates tag + push + `gh release create`.
  - `make release PART=patch` invokes `version_bump.py` then `release.sh`.
  - README install section updated in Phase A (A-036) to reference
    `make install` and the `bin/ralph` symlink flow (preserved per
    spec §3.7).

- **C3 (P2):** Quarantine for known-flaky tests — fully wired.
  - New `tests/quarantine.yaml` with schema `{test_id, added_at, reason,
    auto_added}`. Listed tests are deselected from pytest invocations
    via `--deselect` flag.
  - Every pytest run records failures/passes to
    `.ralph/test-failure-history.jsonl`; after 2 consecutive failures
    (no intervening pass), the test is auto-added to quarantine with
    `auto_added: true` and a `🦠 Flake quarantined: <test_id>` issue
    is posted with both failure timestamps. Idempotent via
    `.ralph/quarantine-issue-idempotency.jsonl`.
  - Stale entries are auto-removed at the start of each validation
    run (>7 days) and via the explicit
    `bin/ralph validate --unquarantine-stale` flag.

- **C4 (P4):** Skip expensive tiers on retry — fully wired.
  - `bin/ralph validate --retry` runs only the pytest-paths tier;
    integration/full/e2e tiers are skipped.
  - BUILD retry paths (retry label and crash-recovery resume) pass
    `--retry` to the validation gate so retry attempts stay fast.

### Internal / Test infrastructure

- **Snapshot regression guard (plan §3 R-2):** `tests/integration/
  test_engine_snapshots.py` re-runs 53 engine scenarios and asserts
  exit codes + stdout patterns match fixtures at `tests/integration/
  fixtures/engine_snapshots/`. The one-shot generator
  (`scripts/generate_engine_snapshots.py`) was removed at end of
  Phase C; the fixtures remain as a permanent regression baseline.
- **Engine snapshot count:** 53 fixtures; 38 active regression guards;
  15 marked `skip_runtime` (validate tiers, daemon, doctor no-args)
  for fast feedback (~2.5s test runtime).

## 3.1.1 — 2026-06-27 (Phase B complete)

### New features

- **B1 (R2):** Per-stage retry budgets. Engine consults
  `[retry] l1_max_attempts` (default 1) and `l2_max_attempts` (default 2)
  from `.ralph/config.toml`. Pytest exit-code classifier extended with
  `retry_l2` for test failures. Re-invocation helper inlines previous
  stdout into the retry prompt.
- **B2 (R3):** Idempotency keys. New `core.pipeline.github.client.GitHubClient`
  wraps every `gh` call in a pre-flight check against
  `.ralph/issues/<N>/idempotency.jsonl`. Keys are `(run_id, action, target,
  body_hash)`. Survives daemon `SIGKILL` — the next process can safely
  re-attempt any step without double-posting.
- **B3 (S4):** Mechanism-enforced isolation. TEST + VERIFY sub-agents now
  run inside git worktrees; `src/` is mounted read-only (Linux) or
  chmod-0500'd (macOS, with WARNING logged). Pre-flight `git worktree add`
  check raises `RuntimeError` with a clear remediation message.
- **B4 (S4):** Single trajectory file. New `core.pipeline.metrics`
  appends JSONL events to `.ralph/issues/<N>/trajectory.jsonl`. Pydantic
  v2 `TrajectoryEvent` discriminated union (5 variants: StageTransition,
  SubagentInvocation, ValidationRun, LabelTransition, Retry).
- **B5 (U1):** `ralph doctor` — diagnostic command with 5 categories
  (stuck issues, long-blocked, repeat failures, orphan subprocesses,
  environment checks). Exit code per plan §3 R-11: 0 healthy, 1 warnings,
  2 errors.

### Internal changes

- Pydantic v2 (`>=2.0,<3.0`) added as a dependency (first new dep in
  Phase B per spec §4.2). All B2.x / B4.x / C1.x code uses it.
- `core.pipeline.state` introduces `Stage` enum (str mixin) and
  `STATUS_LABEL` mapping per spec §7.2.
- `core.schemas.events.TrajectoryEvent` is a Pydantic v2 `RootModel`
  wrapping the discriminated union; callers use either
  `TrajectoryEvent.model_validate({...})` or `TrajectoryEvent(root=evt)`.

### Deprecated

- None.

### New features

- **B1 (R2):** Per-stage retry budgets. Engine consults
  `[retry] l1_max_attempts` (default 1) and `l2_max_attempts` (default 2)
  from `.ralph/config.toml`. Pytest exit-code classifier extended with
  `retry_l2` for test failures. Re-invocation helper inlines previous
  stdout into the retry prompt.
- **B2 (R3):** Idempotency keys. New `core.pipeline.github.client.GitHubClient`
  wraps every `gh` call in a pre-flight check against
  `.ralph/issues/<N>/idempotency.jsonl`. Keys are `(run_id, action, target,
  body_hash)`. Survives daemon `SIGKILL` — the next process can safely
  re-attempt any step without double-posting.
- **B3 (S4):** Mechanism-enforced isolation. TEST + VERIFY sub-agents now
  run inside git worktrees; `src/` is mounted read-only (Linux) or
  chmod-0500'd (macOS, with WARNING logged). Pre-flight `git worktree add`
  check raises `RuntimeError` with a clear remediation message.
- **B4 (S4):** Single trajectory file. New `core.pipeline.metrics`
  appends JSONL events to `.ralph/issues/<N>/trajectory.jsonl`. Pydantic
  v2 `TrajectoryEvent` discriminated union (5 variants: StageTransition,
  SubagentInvocation, ValidationRun, LabelTransition, Retry).
- **B5 (U1):** `ralph doctor` — diagnostic command with 5 categories
  (stuck issues, long-blocked, repeat failures, orphan subprocesses,
  environment checks). Exit code per plan §3 R-11: 0 healthy, 1 warnings,
  2 errors.

### Internal changes

- Pydantic v2 (`>=2.0,<3.0`) added as a dependency (first new dep in
  Phase B per spec §4.2). All B2.x / B4.x / C1.x code uses it.
- `core.pipeline.state` introduces `Stage` enum (str mixin) and
  `STATUS_LABEL` mapping per spec §7.2.
- `core.schemas.events.TrajectoryEvent` is a Pydantic v2 `RootModel`
  wrapping the discriminated union; callers use either
  `TrajectoryEvent.model_validate({...})` or `TrajectoryEvent(root=evt)`.

### Deprecated

- None.

## 3.1.0 — 2026-06-27 (Phase A complete)

### Breaking changes for v3 users

**Action required:** Run `ralph migrate` once after upgrading to v3.1.0.

```bash
git clone https://github.com/samdharma/Ralph_loop
cd Ralph_loop
git checkout ralph-v3.1
./scripts/install.sh
cd <your-project>
ralph migrate             # Migrate state files + regenerate default stage prompts
ralph daemon              # Start as usual
```

The migration tool is idempotent, supports `--dry-run`, and refuses to run while
the daemon is active. It migrates state files (`.ralph/issue-<N>-*.json|.md`) to
the new per-issue directory layout, archives originals to
`.ralph/migration-archive/<timestamp>/`, and regenerates stage prompts that
match v3 defaults (leaves customized prompts alone with a warning).

### New features

- **A-prelude:** `ralph migrate` command — migrate v3 state files and stage
  prompts to v3.1 layout (idempotent, supports `--dry-run`)
- **A1:** Pytest exit-code classification in `core/validate.py` — emits
  structured `{exit_code, classification, action}` per invocation. Codes 124,
  137, 143 each trigger distinct handling.
- **A2:** Hard-block test tampering — QA-written test files get `chmod 0444`
  after the TEST stage, so the IMPLEMENT agent cannot edit them
  (`PermissionError` on POSIX).
- **A3:** Drop `pi --continue` Mode B in favor of artifact-based handoff.
  Sub-agents read inputs from `.ralph/issues/<N>/artifacts/` instead of
  inheriting session context. Both `pi` and `kimi` use the same invocation
  path.
- **A4:** Structured JUnit XML via `ralph validate --junitxml=<path>`. Agent
  prompts are updated to read `<failure>` blocks from the XML instead of raw
  pytest stdout.
- **A5:** Better failure comments — every stage failure includes the last 50
  lines of agent stdout, a link to the trajectory file (when present), and a
  link to the failure report.
- **A6:** Critical-path test set — `[validate] critical_paths` in
  `.ralph/config.toml` (or the `--critical` CLI flag) runs tests first and
  blocks BUILD on failure.
- **A7:** Drop legacy `PROGRESS.md` — status board is now GitHub labels +
  Kanban Project board only.

### Project-shape (no behavior change for new users)

- New Makefile (`make test`, `make lint`, `make validate`, etc.)
- GitHub Actions E2E workflow (`.github/workflows/e2e.yml`)
- E2E test repo cleanup workflow (`.github/workflows/e2e-cleanup.yml`)
- PR template with 8-item checklist (`.github/PULL_REQUEST_TEMPLATE.md`)
- Reviewer guide (`.github/REVIEWER_CHECKLIST.md`)
- Development workflow guide (`docs/development_workflow.md`)
- E2E test skeleton (`tests/e2e/test_ralph_e2e_repo.py`)

### Deprecated

- `docs/agent/PROGRESS.md` — no longer written or read by the engine
- `.ralph/session-<N>.jsonl` — deprecated in A3, kept for one migration cycle

## 3.0.0 — 2026-06-XX

Ralph v3 baseline. See `docs/v3-redesign.md` and `docs/getting_started.md`.

## Unreleased
