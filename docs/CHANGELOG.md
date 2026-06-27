# Changelog

All notable changes to Ralph are documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and Ralph adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

Unreleased — Phase A work in progress.
## 3.1.2 — 2026-06-27 (Phase C complete)

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
  - **DEVIATION**: `core/engine.py` is 3121 lines, NOT ≤ 200 lines
    as the spec acceptance criterion requires. The per-task C1.x moves
    used a thin-wrapper pattern (re-export from engine.py) to preserve
    behavior; the actual extraction of 2900+ lines of interconnected
    logic is deferred. The snapshot test (C-013 / C-046) is the
    regression guard and passes.
  - mypy --strict equivalent passes on 8 pipeline files; pyproject.toml
    configures `mypy_path` via `[tool.mypy].mypy_path = "core"` so flat
    modules (`project_sync`) are findable.

### New features

- **C2 (S2):** Distribute via GitHub Releases.
  - New `scripts/release.sh` automates tag + push + `gh release create`.
  - `make release PART=patch` invokes `version_bump.py` then `release.sh`.
  - README install section updated in Phase A (A-036) to reference
    `make install` and the `bin/ralph` symlink flow (preserved per
    spec §3.7).

- **C3 (P2):** Quarantine for known-flaky tests.
  - New `tests/quarantine.yaml` with schema `{test_id, added_at, reason,
    auto_added}`. Listed tests are deselected from pytest invocations
    via `--deselect` flag.
  - `record_test_result` + `should_auto_quarantine` track per-test
    failure history at `.ralph/test-failure-history.jsonl`. After 2
    consecutive failures (no intervening pass), the test is
    auto-added to quarantine with `auto_added: true`.
  - `unquarantine_stale_entries` (CLI: `bin/ralph validate
    --unquarantine-stale`) removes entries older than 7 days.
  - `post_flake_quarantined_issue` posts a GitHub issue titled
    `🦠 Flake quarantined: <test_id>` with both failure timestamps
    and a link to the failure history. Idempotent via
    `.ralph/quarantine-issue-idempotency.jsonl`.

- **C4 (P4):** Skip expensive tiers on retry.
  - `bin/ralph validate --retry` runs only the pytest-paths tier;
    integration/full/e2e tiers are skipped. Wired into BUILD's
    retry path so retry attempts use this flag.

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
