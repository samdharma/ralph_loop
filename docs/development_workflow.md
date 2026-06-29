# Development Workflow

This guide is for contributors and operators working on Ralph. It documents the
branch strategy, release cadence, and contributor workflows used in Ralph v3.1.x.

## Branch strategy

Ralph v3.1 uses a **single `ralph-v3.1` branch** as the only release branch.
Every phase ships as a single squash-merged PR against `ralph-v3.1`. Phase tags
(`ralph-v3.1.0` through `ralph-v3.1.3`) mark the merge commit for each phase.

| Branch | Purpose |
|--------|---------|
| `main` | Frozen historical branch — no direct pushes |
| `ralph-v3` | Frozen development line for Ralph v3.x (no further work) |
| `ralph-v3.1` | **The active release branch.** All PRs target this branch. |

**Hard rule:** Never force-push to `main` or `ralph-v3.1`. Branch protection
applies on both.

## Release cadence

Ralph v3.1 ships in four sequential phases (per `docs/IMPROVEMENT_ROADMAP_SPEC.md`):

| Phase | Tag | Scope |
|-------|-----|-------|
| A — Quick wins | `ralph-v3.1.0` | Exit-code classification, artifact handoff, JUnit XML, etc. |
| B — Reliability | `ralph-v3.1.1` | Per-stage retry budgets, idempotency keys, worktree isolation |
| C — Simplification | `ralph-v3.1.2` | Engine split into `core/pipeline/`, GitHub Releases |
| D — Performance | `ralph-v3.1.3` | Parallel BUILD, single retry label, `--dry-run` |

After Phase D passes the E2E gate, the release is promoted to `ralph-v3.1`
(final). Until then, `ralph-v3.1.0` … `ralph-v3.1.3` are intermediate tags.

## PR review checklist (spec §13)

Every PR to `ralph-v3.1` must pass the 8-item checklist in
`docs/IMPROVEMENT_ROADMAP_SPEC.md` §13 before merge. For v3.1.0 specifically,
a ninth item applies (migration tested on a real v3 project). See
`.github/PULL_REQUEST_TEMPLATE.md` for the auto-populated checklist and
`.github/REVIEWER_CHECKLIST.md` for what each item means in practice.

## E2E test repo

All end-to-end tests use **`samdharma/ralph-e2e-test`** (default branch
`master`). That repo carries the canonical 8-status label set for v3.1.x:

- `status:ready`
- `status:design`
- `status:build`
- `status:verify`
- `status:review`
- `status:blocked`
- `status:build-retry`
- `status:verify-retry`

Phase D additionally adds `status:retry` (additive — the engine recognizes both
the new label and the legacy retry labels).

E2E issues use the title prefix `[e2e-phase-<X>-run-<timestamp>]`. Successful
issues are auto-closed; failed issues are left open for operator review and
auto-close after 30 days via `.github/workflows/e2e-cleanup.yml`.

To run an E2E test locally:

```bash
RALPH_E2E=1 pytest tests/e2e/test_ralph_e2e_repo.py -v
```

To find recent E2E issues on the test repo:

```bash
gh issue list --repo samdharma/ralph-e2e-test \
  --search "[e2e-phase- in:title" \
  --state all \
  --json number,title,state,createdAt \
  --jq '.[] | select(.createdAt > (now - 604800 | todate))'
```

## Upgrading v3 → v3.1

v3 projects must run `ralph migrate` once after upgrading to v3.1.0:

```bash
git clone https://github.com/samdharma/Ralph_loop
cd Ralph_loop
git checkout ralph-v3.1
./scripts/install.sh
cd <your-project>
ralph migrate             # Migrate state files + regenerate default stage prompts
ralph daemon              # Start as usual
```

`ralph migrate` is:

- **Idempotent** — running twice produces identical filesystem state
- **Refuses to run** while the daemon PID file exists (prevents race)
- **Supports `--dry-run`** — outputs JSON listing every action it WOULD take
- **Backs up before modifying** — every renamed/moved file is first copied to
  `.ralph/migration-archive/<timestamp>/`

## Migration archive cleanup

The `.ralph/migration-archive/` directory is **never auto-pruned**. Backups are
typically a few MB even with dozens of archives, and they live only on the
operator's machine (the `.ralph/` directory is gitignored).

To remove all migration archives after you've verified the migration succeeded:

```bash
# Remove all migration archives (irreversible; do this only when confident)
rm -rf .ralph/migration-archive/
```

## Phase-complete verification (per spec §10)

After every phase PR is merged (before tagging the release), run:

```bash
make test            # Unit + integration tests pass
make lint            # black, isort, flake8, mypy all pass
make validate        # ralph validates itself (--tier=targeted)
gh workflow run e2e.yml --ref ralph-v3.1   # Manual E2E trigger
# Confirm an [e2e-phase-<phase>-run-*] issue reaches status:review
```

For Phase B and later, additional E2E criteria apply — see the per-phase
verification section of `docs/IMPROVEMENT_ROADMAP_TASKS.md`.

## Local development loop

```bash
# Make your change in a topic branch off ralph-v3.1
git checkout -b feat/my-change ralph-v3.1

# Run tests as you go
make test-unit           # <1 minute; catches regressions in the changed module
make lint                # <30 seconds; catches style + mypy regressions

# For changes to core/engine.py or core/pipeline/
make test-integration    # <5 minutes; catches behavioral regressions

# Before pushing — full quality gate
make test                # unit + integration
make lint
make validate

# Open a PR against ralph-v3.1; the template will list the 8-9 checklist items
```

## Useful one-liners

```bash
# Find all E2E issues from the last 7 days
gh issue list --repo samdharma/ralph-e2e-test \
  --search "[e2e-phase- in:title" \
  --state all

# Find failed E2E issues still open
gh issue list --repo samdharma/ralph-e2e-test \
  --search "[e2e-phase- in:title status:blocked in:body" \
  --state open

# Close a stale failed E2E issue
gh issue close <N> --repo samdharma/ralph-e2e-test \
  --comment "Closing stale E2E failure."

# Run Ralph self-validation
ralph validate --tier=targeted
```