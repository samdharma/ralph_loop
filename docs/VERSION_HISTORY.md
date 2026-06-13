# Version History — Ralph Wiggum Loop Build System

> Release notes, breaking changes, and migration notes.

---

## v1.2.0 — 4-Stage Pipeline (2026-06-13)

### New: Independent TEST Phase

The 3-stage pipeline (design → implement → verify) has been upgraded to 4 stages
with an independent test-writing phase:

```
DESIGN → TEST → IMPLEMENT → VERIFY
```

**Why**: The implement session was writing its own functional tests — the AI agent
was "marking its own homework." The new TEST stage writes functional, system, and
integration tests from the design spec **before any code exists**. The IMPLEMENT
session then writes code to pass those tests (plus unit tests for internal logic).
This is true independent verification.

### New Commands

```bash
ralph test --ticket=<id> [--agent=pi|kimi]
```

### New Files
- `templates/prompts/sessions/test.md` — TEST session prompt
- `tests/e2e/ralph_4stage_pipeline_e2e_test.sh` — 33-test e2e suite

### Changed Files
- `bin/ralph` — added `ralph test` command, updated help
- `templates/prompts/sessions/design.md` — explicitly no test-writing
- `templates/prompts/sessions/implement.md` — test-first: read TEST plan, run failing tests, write code + unit tests only
- `init.py` — 4-stage output messages
- `README.md`, `DEPLOYMENT.md`, `scripts/install.sh` — 4-stage docs

### E2E Tests: 33/33 passing

---

## v1.1.0 — 3-Session Pipeline + Bug Fixes (2026-06-13)

### New: 3-Session Pipeline (Option B CLI Commands)

Added explicit session commands for the design → implement → verify workflow:

```bash
ralph design --ticket=<id> [--agent=pi|kimi]
ralph implement --ticket=<id> [--agent=pi|kimi]
ralph verify --ticket=<id> [--agent=pi|kimi]
```

Each command invokes `ralph_loop.sh --session=<phase>` with session-specific prompts.

### New: Session Prompt Templates
- `templates/prompts/sessions/design.md`
- `templates/prompts/sessions/implement.md`
- `templates/prompts/sessions/verify.md`

### Enhanced Installer
- Comprehensive prerequisite validation (git, python 3.10+, beads, AI agent, GitHub)
- Pass/warn/fail reporting with install instructions
- Post-install verification of core scripts and templates
- Dependency summary on completion

### Bug Fixes
- Fixed legacy validation paths: `bash scripts/ralph/ralph_validate.sh` → `ralph validate`
- Fixed repo URL inconsistency: `gastownhall/ralph` → `samdharma/Ralph_loop`

---

## v1.0.x — Initial Release (2026-05-24)

### Global Tool Architecture

Ralph is a **global CLI tool** installed at `~/.ralph/`. Core build scripts live there.
Projects carry only config files (`~/.ralph/config.toml` + project-specific configs).
No build scripts in project repos.

### Commands
- `ralph init` — scaffold new project
- `ralph setup` — post-clone setup (beads init + dolt pull)
- `ralph status` — project health dashboard
- `ralph loop` — build loop (foreground)
- `ralph daemon` — build loop (background)
- `ralph validate` — validation gate
- `ralph health` — health check
- `ralph report` — operational report
- `ralph metrics` — metrics viewer
- `ralph sync` — remote sync status
- `ralph migrate` — legacy project migration

### Core Scripts (12 files)
`ralph_loop.sh`, `run_ralph_loop.sh`, `ralph_preflight.sh`, `ralph_validate.sh`,
`ralph_health.sh`, `ralph_metrics.sh`, `ralph_metrics_viewer.py`, `ralph_report.sh`,
`ralph_report.py`, `ralph_check_specs.py`, `ralph_performance_check.sh`,
`detect_affected_tests.py`

### Documentation
- 10 markdown docs + single-page HTML with Mermaid diagrams
- Deployment, getting started, daily usage, troubleshooting, FAQ

---

## Migration Notes

### v1.1 → v1.2

No breaking changes. Existing projects continue to work. New projects get the 4-stage
session prompts on `ralph init`. To upgrade an existing project:

```bash
cp ~/.ralph/templates/prompts/sessions/test.md docs/agent/prompts/sessions/
```

### v1.0 → v1.1

No breaking changes. The 3-session commands are added alongside the existing
all-in-one `ralph loop` and `ralph daemon`. Upgrading Ralph globally (git pull
in `~/.ralph/`) gives all projects access to the new commands.
