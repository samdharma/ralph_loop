# Changelog

All notable changes to Ralph are documented in this file.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and Ralph adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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