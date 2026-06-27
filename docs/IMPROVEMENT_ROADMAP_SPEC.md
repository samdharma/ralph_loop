# Spec: Ralph v3.1 — Improvement Roadmap

**Status:** DRAFT (awaiting human review)
**Date:** 2026-06-26
**Author:** Spec-driven development session
**Reference doc:** [`docs/architectural-review-2026-06-26.md`](architectural-review-2026-06-26.md)
**Target version:** `ralph-v3.1` (semantic minor bump — additive, no breaking CLI changes)

---

## 1. Objective

### 1.1 What we're building

Ralph v3.1 implements the improvements outlined in [`docs/architectural-review-2026-06-26.md`](architectural-review-2026-06-26.md), executed in the recommended sequence: **Phase A → B → C → D**.

The improvement targets three concrete pain points:

1. **Brittleness in test execution** — prompt-only isolation that the agent can violate; no in-loop retry on transient failures; advisory-only detection of test tampering.
2. **Single point of failure in Mode B** — the `pi --continue --session <file>` mechanism is fragile across `pi` and `kimi` (kimi's `--continue` resumes the *most recent* session, which after TEST runs is the TEST session, not the DESIGN session).
3. **Monolithic engine** — `core/engine.py` is 2,735 lines spanning 12+ concerns, making every change risky.

### 1.2 Target users

**Primary:** Developers building with AI agent loops. They run `ralph daemon` on their own projects, watch the Kanban board, and inspect failures when issues get blocked. They expect:

- A working binary they can download and start using with only the README.
- Stable CLI — no breaking changes between minor versions.
- Self-healing on transient failures — they shouldn't have to manually retry every flake.
- Clear, actionable error messages — they shouldn't have to grep the daemon log.

**Secondary:** Ralph maintainers — engineers reading or modifying the codebase. They expect:

- Small, focused modules (< 500 lines each).
- Type-safe state representations (no stringly-typed status fields).
- Per-issue trajectory files for debugging individual failures.
- Schema validation catching drift at write time.

### 1.3 Success signal

**Done = working software downloadable from the GitHub repo and startable using only the README.** Each phase must be validated by a full E2E run on [`samdharma/ralph-e2e-test`](https://github.com/samdharma/ralph-e2e-test) — a real GitHub repo with the Ralph label set, an active Kanban board, and historical issues closed via the pipeline. The acceptance test for each phase is: create a `status:ready` issue on that repo, run `ralph daemon`, and observe the issue progress through all stages to `status:review` (or `status:blocked` if a real failure is expected).

---

## 2. Scope

### 2.1 In scope (from the architectural review)

Every recommendation from `docs/architectural-review-2026-06-26.md` §7 (the roadmap), with their original IDs preserved:

**Phase A — Quick wins (1-2 weeks):**
- A1 → **P1** Pytest exit-code classification
- A2 → **R5** Hard-block test tampering via `chmod 0444`
- A3 → **R1** Drop `pi --continue` Mode B → artifact handoff
- A4 → **U2** Structured JUnit XML
- A5 → **U6** Better error messages
- A6 → **P3** Critical-path test set
- A7 → **S5** Drop legacy `PROGRESS.md`

**Phase B — Reliability primitives (2-3 weeks):**
- B1 → **R2** Per-stage retry budgets with structured escalation
- B2 → **R3** Idempotency keys on engine side effects
- B3 → **R4** Mechanism-enforced isolation (worktree + read-only `src/`)
- B4 → **S4** Single trajectory file per issue (Pydantic-typed)
- B5 → **U1** `ralph doctor` diagnostic

**Phase C — Structural simplification (3-4 weeks):**
- C1 → **S1** Split `engine.py` into `core/pipeline/` package
- C2 → **S2** Drop bash dispatcher; distribute via GitHub Releases
- C3 → **P2** Quarantine for known-flaky tests
- C4 → **P4** Skip expensive tiers on retry

**Phase D — Performance (1-2 weeks):**
- D1 → **P5** Parallel TEST + IMPLEMENT via git worktree
- D2 → **U5** Single retry label (additive — old labels still work)
- D3 → **U3** `ralph --dry-run`

### 2.2 Out of scope

- **Replacing the GitHub-as-state-store design** — Ralph's biggest differentiator. Do not change.
- **Replacing the per-issue design spec files** (`docs/designs/<N>.md`) — solved a real problem (issue #72).
- **Replacing provider-error handling** — production-grade; not in scope.
- **Adding a web UI** — the Kanban board *is* the UI.
- **Adding new status labels** — the 8-state machine (`ready|design|build|verify|review|blocked` + 2 retry variants) is clean.

### 2.3 Deferred (Phase E or later, not in v3.1)

- Multi-tenant support (multiple projects per daemon instance).
- Distributed daemon (multiple workers processing tickets in parallel).
- Webhook-driven triggers (instead of polling).
- Support for AI agents other than `pi` and `kimi` (e.g., direct API integration with Claude or GPT).
- Migrating to a typed issue schema beyond GitHub Issues.

---

## 3. New Assumptions (surfaced this session)

These emerged from the user's answers and from validating the test repo state. All confirmed during the requirements interview (2026-06-26):

1. **Version target is `ralph-v3.1`** (not v4). SemVer: minor bump because all CLI changes are additive — old `ralph daemon`, `ralph setup`, `ralph status`, `ralph validate`, `ralph report`, `ralph init`, `ralph generate-test-map` continue to work unchanged.
2. **Distribution is GitHub Releases only** (no PyPI). Each phase completion produces a tagged release (`ralph-v3.1.0` after Phase A, `ralph-v3.1.1` after Phase B, etc.). The README's install instructions change from `curl | bash` to a curl-to-tarball or `git clone && make install` flow.
3. **The E2E test repo is `samdharma/ralph-e2e-test`** (default branch `master`). All 8 status labels are present. Has 6 historical closed issues validating prior end-to-end runs.
4. **Pydantic v2 is approved as a new top-level dependency** for typed events (S4) and state (C1). Rationale in §4.2.
5. **U5 (single retry label) is implemented additively** — the new label works alongside the existing 3 (`status:ready`, `status:build-retry`, `status:verify-retry`). No deprecation in v3.1. A future v3.2 may deprecate the old labels.
6. **Explicit `ralph migrate` command for v3 projects.** Projects on Ralph v3 must run `ralph migrate` once after upgrading to v3.1 before starting the daemon. The command is idempotent, supports `--dry-run`, refuses to run if the daemon PID file exists, and outputs a JSON report. Behavior is aggressive (Q5-B): migrates state files AND regenerates stage prompts IF they match the v3 default templates; user-customized prompts are left alone with a warning.
7. **The bash dispatcher (`bin/ralph`) is preserved through v3.1.x** even though S2 plans to drop it. The C2 release keeps `bin/ralph` working but makes the Python entry point (`python3 -m core.engine`) the documented path.
8. **Branch strategy is single `ralph-v3.1` branch, one PR per phase.** Each phase ships as a single squash-merged PR. Phase tags (`ralph-v3.1.0` through `ralph-v3.1.3`) mark the merge commit. Detailed development workflow is documented for the user community in `docs/development_workflow.md`.
9. **E2E test data lifecycle:** Successful E2E issues are auto-closed after asserting they reached `status:review`. Failed E2E issues are left open at the stage where they failed. Both use a `[e2e-phase-<X>-run-<timestamp>]` title prefix. Failed issues auto-close after 30 days untouched via a separate scheduled workflow (or manual pass).
10. **`ralph doctor` covers 5 diagnostic categories:** stuck issues, long-blocked issues, repeat failures, orphan subprocesses, environment checks. Exit codes 0/1/2 by severity.
11. **PR review checklist is enforced** via `.github/PULL_REQUEST_TEMPLATE.md` with 8 checkboxes (see §13).

---

## 4. Tech Stack

### 4.1 Unchanged

| Component | Version | Role |
|-----------|---------|------|
| Python | 3.10+ | Core orchestrator |
| `git` | 2.30+ | Version control |
| `gh` (GitHub CLI) | 2.0+ | Issue read/write, label management |
| `pytest` | project-pinned | Test runner |
| `pi` or `kimi` | latest | AI agent for code generation |

### 4.2 New: Pydantic v2

**Decision: Add `pydantic>=2.0` as a new top-level dependency.**

**Rationale (evaluated on the user's behalf):**

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| **Pydantic v2** | Schema validation at write time; 5x faster than v1; IDE autocomplete; self-documenting; used in 8 of the 9 reference systems studied | ~3MB install; learning curve for advanced validators; opinionated | ✅ **Chosen** |
| `dataclasses` (stdlib) | No new dependency; zero runtime overhead; familiar | No validation; manual `__post_init__`; less self-documenting | Used for simple internal records that don't need validation |
| `attrs` | Less opinionated than Pydantic; faster than dataclasses for some uses | Adds a dep anyway; smaller ecosystem; not used by reference systems | Rejected — no compelling advantage over Pydantic |
| `msgspec` | Fastest of the four; no deps; supports JSON Schema | Smaller community; less mature; no equivalent of Pydantic's validation language | Rejected — premature optimization for our scale |

**Where Pydantic is used:**
- `core/pipeline/state.py` — `Stage` enum, `PipelineState` model
- `core/pipeline/agents/artifacts.py` — `DesignArtifact`, `TestArtifact`, `ImplementationArtifact`
- `core/pipeline/metrics.py` — `TrajectoryEvent` union type
- `core/pipeline/checkpoint.py` — `CheckpointState` model
- `core/pipeline/github/client.py` — `Issue`, `Comment`, `Label` typed wrappers

**Where `dataclasses(frozen=True)` is used** (no validation needed):
- Internal lookup tables (e.g., retry-policy-by-exit-code)
- Pure data carriers within a single function

### 4.3 Not added

- **No new testing frameworks.** pytest + the existing test suite is sufficient.
- **No new build tooling.** No `poetry`, `pdm`, `hatch`, etc. — keep `pyproject.toml` minimal.
- **No new linting tools.** Existing `flake8` + `black` + `isort` + `mypy` continue.
- **No async runtime** (no `asyncio`, no `aiohttp`). Subprocess + `subprocess.run` is enough for the daemon's workload.

---

## 5. Commands

### 5.1 Existing CLI surface (preserved)

```bash
ralph init [dir]                # Scaffold a Ralph project (default: current directory)
ralph setup                     # Check prerequisites and prepare local dirs
ralph daemon [opts]             # Start the build loop (foreground — use & for background)
ralph status                    # Show project health dashboard
ralph validate [opts]           # Run the validation gate
ralph report                    # Generate daily/weekly summary
ralph generate-test-map         # Auto-generate TEST_MAP.yaml from project structure
ralph version                   # Show version
ralph help                      # Show help
```

### 5.2 New commands (additive)

```bash
ralph doctor [N]                # Diagnose recent failures; if N given, focus on issue #N
ralph trajectory <N>            # Show per-issue trajectory as a timeline
ralph validate --retry          # Run only --pytest-paths (skip integration/full/e2e)
ralph daemon --dry-run          # Walk pipeline up to (not including) agent invocation
ralph migrate [--dry-run]       # Migrate v3 state files and stage prompts to v3.1 format
```

### 5.3 New flags on existing commands

```bash
ralph daemon --dry-run                              # Validate gh/git/labels without invoking agent
ralph validate --retry                              # Skip expensive tiers; only run --pytest-paths
ralph validate --critical                           # Run only critical_paths tests
ralph validate --junitxml=<path>                    # Emit JUnit XML for machine-parseable failures
```

### 5.4 Build / test / lint

```bash
# Install (new for v3.1, replaces curl|bash)
make install                    # Symlinks bin/ralph into PATH
# OR
git clone https://github.com/samdharma/Ralph_loop
cd Ralph_loop
git checkout ralph-v3.1
./scripts/install.sh

# Development
make test                       # pytest tests/unit/ tests/integration/
make test-unit                  # pytest tests/unit/
make test-integration           # pytest tests/integration/
make lint                       # black --check + isort --check-only + flake8 + mypy
make format                     # black + isort --apply
make validate                   # ralph validate --tier=targeted against self

# Release (internal)
make version-show               # Print current version
make version-bump PART=minor    # Bump pyproject.toml + bin/ralph + tag
```

### 5.5 Versioning

```bash
# Versions are tracked in three places, kept in sync via make version-bump:
#   pyproject.toml  → [project].version
#   core/__init__.py → __version__
#   bin/ralph       → cmd_version output

# Tags follow ralph-v<MAJOR>.<MINOR>.<PATCH>
git tag ralph-v3.1.0 -m "Phase A complete"
git push origin ralph-v3.1.0
gh release create ralph-v3.1.0 --generate-notes
```

---

## 6. Project Structure

### 6.1 Target layout (after C1)

```
Ralph_loop/
├── bin/
│   └── ralph                          # Bash dispatcher (kept for v3.1; drop in v3.2)
├── core/
│   ├── __init__.py                    # __version__ = "3.1.0"
│   ├── engine.py                      # CLI entrypoint: ~150 lines (parse args, call runner)
│   ├── init.py                        # Project scaffolding (unchanged from v3)
│   ├── setup.py                       # Prereq checks (unchanged)
│   ├── status.py                      # Dashboard (unchanged)
│   ├── validate.py                    # Validation gate (extended with P1, U2, P3, P4)
│   ├── report.py                      # Report generator (unchanged)
│   ├── generate_test_map.py           # Test-map generator (unchanged)
│   ├── detect_affected_tests.py       # Affected-test detection (extended with globs)
│   ├── project_sync.py                # Board sync (unchanged)
│   │
│   ├── pipeline/                      # NEW in C1
│   │   ├── __init__.py
│   │   ├── state.py                   # Pydantic: Stage, PipelineState, transitions
│   │   ├── runner.py                  # run_loop, run_pipeline orchestrator
│   │   ├── stages/
│   │   │   ├── __init__.py
│   │   │   ├── base.py                # Stage ABC: artifact_io, run, verify
│   │   │   ├── design.py              # DESIGN stage
│   │   │   ├── build.py               # BUILD stage (TEST + IMPLEMENT sub-agents)
│   │   │   └── verify.py              # VERIFY stage
│   │   ├── agents/
│   │   │   ├── __init__.py
│   │   │   ├── base.py                # Agent abstraction (no --continue hack)
│   │   │   ├── pi.py                  # pi wrapper
│   │   │   ├── kimi.py                # kimi wrapper
│   │   │   └── artifacts.py           # R1: run_id-keyed artifact handoff
│   │   ├── github/
│   │   │   ├── __init__.py
│   │   │   ├── client.py              # R3: idempotency-wrapped gh wrapper
│   │   │   ├── labels.py              # transition_label
│   │   │   ├── comments.py            # gh_comment (idempotent)
│   │   │   └── board.py               # sync_status, sync_closed
│   │   ├── checkpoint.py              # save_checkpoint, clear_checkpoint, recover_from_crash
│   │   ├── metrics.py                 # ralph_metrics.jsonl + S4 trajectory
│   │   └── recovery.py                # Crash recovery logic (split out of engine.py)
│   │
│   └── schemas/                       # NEW: Pydantic models shared across modules
│       ├── __init__.py
│       ├── events.py                  # TrajectoryEvent union type
│       ├── artifacts.py               # DesignArtifact, TestArtifact, ImplementationArtifact
│       └── checkpoint.py              # CheckpointState
│
├── tests/
│   ├── unit/
│   │   ├── core/
│   │   │   ├── pipeline/
│   │   │   │   ├── test_state.py
│   │   │   │   ├── test_runner.py
│   │   │   │   ├── stages/
│   │   │   │   │   ├── test_design.py
│   │   │   │   │   ├── test_build.py
│   │   │   │   │   └── test_verify.py
│   │   │   │   ├── agents/
│   │   │   │   │   ├── test_pi.py
│   │   │   │   │   ├── test_kimi.py
│   │   │   │   │   └── test_artifacts.py
│   │   │   │   └── github/
│   │   │   │       ├── test_client.py
│   │   │   │       ├── test_labels.py
│   │   │   │       └── test_comments.py
│   │   │   ├── test_validate.py       # P1, U2, P3, P4 tests
│   │   │   └── test_engine.py         # CLI entrypoint tests
│   │   └── schemas/
│   │       ├── test_events.py
│   │       └── test_artifacts.py
│   ├── integration/
│   │   ├── test_pipeline_e2e.py       # Full pipeline against mocked gh/agent
│   │   └── test_artifact_handoff.py   # R1: artifact-based flow
│   └── e2e/
│       └── test_ralph_e2e_repo.py     # Real GitHub repo test (gated on env var)
│
├── docs/
│   ├── IMPROVEMENT_ROADMAP_SPEC.md    # THIS FILE
│   ├── IMPROVEMENT_ROADMAP_PLAN.md     # Phase-by-phase plan (separate doc)
│   ├── architectural-review-2026-06-26.md
│   ├── v3-redesign.md
│   ├── getting_started.md
│   ├── observability.md
│   ├── progress-isolation.md
│   ├── system_test.md
│   ├── development_workflow.md         # NEW: contributor-facing guide (branch strategy, PRs, releases)
│   ├── CHANGELOG.md                   # NEW: tracks v3.1.x changes
│   └── agent/
│       ├── PROMPT.md
│       ├── PROGRESS.md                # Deprecated in S5; removed at end of A
│       └── prompts/
│           ├── design.md              # Updated for R1 (no longer relies on session)
│           ├── test.md                # Updated for R1, R5 (no test file modification)
│           ├── implement.md           # Updated for R1 (artifact-based, no --continue)
│           └── verify.md              # Updated for R4 (no implementation reading)
│
├── scripts/
│   ├── install.sh                     # Updated for v3.1 (no curl|bash; git clone flow)
│   └── release.sh                     # NEW: tag + gh release automation
│
├── .github/
│   ├── PULL_REQUEST_TEMPLATE.md       # NEW: 8-item review checklist (§13)
│   ├── REVIEWER_CHECKLIST.md          # NEW: what each checklist item means
│   └── workflows/
│       └── e2e.yml                    # NEW: gated E2E workflow (workflow_dispatch + push to ralph-v3.1)
│
├── Makefile                           # NEW: install, test, lint, format, version targets
├── CHANGELOG.md                       # NEW (or symlink to docs/CHANGELOG.md)
├── pyproject.toml                     # Add pydantic dep; bump version
├── README.md                          # Updated install instructions
├── AGENTS.md                          # Updated tools line; add --pi-flag note
├── .gitignore                         # Add __pycache__/, .pytest_cache/, *.egg-info
└── config/                            # Project-level config (unchanged)
    ├── ralph_preflight.sh
    └── TEST_MAP.yaml                  # Now supports globs (detect_affected_tests.py)
```

### 6.2 Per-issue artifacts (new in v3.1)

```
.ralph/
├── checkpoint.json                    # Existing; now Pydantic-typed
├── session-<N>.jsonl                  # DEPRECATED in R1; kept for migration
├── issue-<N>-tests.json               # Existing; promoted to Pydantic
├── issue-<N>-report.md                # Existing
└── issues/
    └── <N>/
        ├── trajectory.jsonl            # NEW (S4): every event for this issue
        ├── artifacts/
        │   ├── design.md               # Copy of design spec (R1)
        │   ├── files_in_scope.json     # R1: machine-checkable list of paths
        │   ├── acceptance_criteria.json # R1: structured AC list
        │   └── qa_tests_to_pass.json   # Populated by TEST stage (R1)
        ├── failure_history.jsonl       # R2: appended each retry
        └── idempotency.jsonl           # R3: which engine actions succeeded
```

---

## 7. Code Style

### 7.1 Conventions (preserved from v3)

- **Naming:** `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE` for constants.
- **Imports:** stdlib first, third-party second, local third; alphabetical within each group.
- **Type hints:** Required on all new public functions. `Optional[X]` for nullable; `X | None` accepted in 3.10+ syntax.
- **Docstrings:** Google style. One-line summary + blank line + extended description. Args/Returns/Raises sections where applicable.
- **Line length:** 100 characters (matches existing `flake8` config in `.flake8`).
- **String quotes:** Double quotes by default. Single quotes only when the string contains double quotes.

### 7.2 New conventions (introduced for v3.1)

**Pydantic over dicts for state:**

```python
# BAD (v3 style, now forbidden in pipeline/)
checkpoint = {"issue": 42, "stage": "build", "pre_sha": "abc1234"}

# GOOD (v3.1 style)
from core.schemas.checkpoint import CheckpointState
checkpoint = CheckpointState(issue=42, stage=Stage.BUILD, pre_sha="abc1234")
```

**Frozen dataclasses for lookup tables:**

```python
# GOOD
@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    backoff_seconds: float
    applies_to: frozenset[int]  # pytest exit codes

PYTEST_TIMEOUT_RETRY = RetryPolicy(
    max_attempts=1,
    backoff_seconds=0,
    applies_to=frozenset({124}),
)
```

**Enum over string literals for stage/transition states:**

```python
# BAD (v3 style)
def transition_label(issue_num, add, remove):
    # "status:build", "status:design", etc. as raw strings

# GOOD (v3.1 style)
class Stage(str, Enum):
    READY = "ready"
    DESIGN = "design"
    BUILD = "build"
    VERIFY = "verify"
    REVIEW = "review"
    BLOCKED = "blocked"

STATUS_LABEL = {s: f"status:{s.value}" for s in Stage}
```

**Idempotent side effects via `run_id`:**

```python
# BAD (v3 style)
def gh_comment(issue_num, body):
    gh("issue", "comment", str(issue_num), "--body", body)

# GOOD (v3.1 style, in core/pipeline/github/client.py)
class GitHubClient:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.idempotency_log = PROJECT_ROOT / ".ralph" / "idempotency.jsonl"

    def comment(self, issue_num: int, body: str) -> bool:
        key = (self.run_id, "comment", issue_num, hash(body))
        if self._already_executed(key):
            return True
        result = gh("issue", "comment", str(issue_num), "--body", body)
        self._record(key, result)
        return result.returncode == 0
```

**Artifact-based agent handoff (R1):**

```python
# GOOD: agents read from disk, not from session continuation
def invoke_implement_agent(issue_num: int, artifact_dir: Path) -> bool:
    design = (artifact_dir / "design.md").read_text()
    files_in_scope = json.loads((artifact_dir / "files_in_scope.json").read_text())
    acceptance = json.loads((artifact_dir / "acceptance_criteria.json").read_text())
    qa_tests = json.loads((artifact_dir / "qa_tests_to_pass.json").read_text())

    prompt = _build_implement_prompt(design, files_in_scope, acceptance, qa_tests)
    cmd = [agent_bin, "--print", "--no-skills", prompt]
    result = run(cmd, check=False, capture=True, timeout=None)
    return result.returncode == 0
    # No --continue. No session file. No kimi-specific logic.
```

### 7.3 Linting (enforced on every build)

Same toolchain as v3, with stricter config:

- **`black`** at line-length 100 (matches existing `.flake8`)
- **`isort`** with profile `black`
- **`flake8`** with existing config + `mypy` type-check passes for `core/pipeline/` and `core/schemas/`
- **`mypy`** at `--strict` for `core/pipeline/` (relaxed for `core/init.py` since it has Jinja-like template strings)

---

## 8. Testing Strategy

### 8.1 Test pyramid

```
        ┌─────────────────┐
        │   E2E (1 test)  │  ← Real GitHub repo, real agent, gated on env var
        ├─────────────────┤
        │  Integration    │  ← Pipeline run against mocked gh + agent
        │  (~10 tests)    │
        ├─────────────────┤
        │   Unit tests    │  ← Pure functions, no I/O
        │  (~100 tests)   │
        └─────────────────┘
```

### 8.2 Test locations

| Type | Location | Naming | Speed target |
|------|----------|--------|--------------|
| Unit | `tests/unit/` | `test_*.py` | <1s per test |
| Integration | `tests/integration/` | `test_*.py` | <30s per test |
| E2E | `tests/e2e/` | `test_*.py` | <5min per test |

### 8.3 Coverage expectations

- **`core/pipeline/`**: 90%+ line coverage required. This is the heart of the daemon.
- **`core/schemas/`**: 100% line coverage. Pure data classes; should be trivial.
- **`core/validate.py`**: 80%+ line coverage. Already covered; new P1/U2/P3/P4 paths must be tested.
- **CLI commands** (`core/engine.py`, `bin/ralph`): Smoke-tested via subprocess in `tests/integration/`.

### 8.4 Mocking strategy

| External dependency | Mock approach |
|---------------------|---------------|
| `gh` CLI | `subprocess.run` patched; `tests/integration/conftest.py` provides a `mock_gh` fixture that records calls and returns canned responses |
| `git` CLI | Same — `mock_git` fixture |
| `pi` / `kimi` agent | `subprocess.run` patched; canned stdout (exit 0 / exit 1 / rate-limit pattern) |
| Filesystem | Use `tmp_path` fixture from pytest |
| Network | Blocked at `conftest.py`; E2E test opt-in via `RALPH_E2E=1` env var |

### 8.5 E2E test (gated)

**`tests/e2e/test_ralph_e2e_repo.py`:**

```python
import os
import time
import pytest

@pytest.mark.skipif(
    os.environ.get("RALPH_E2E") != "1",
    reason="E2E tests require RALPH_E2E=1 and a real GitHub repo",
)
def test_full_pipeline_on_e2e_repo(tmp_path):
    """
    End-to-end: clone samdharma/ralph-e2e-test, create a status:ready issue,
    run ralph daemon, observe issue progresses through DESIGN → BUILD → VERIFY.
    On success: issue is auto-closed at status:review.
    On failure: issue is left open at the failing stage for debugging.
    """
    run_id = time.strftime("%Y%m%d-%H%M%S")
    title_prefix = f"[e2e-phase-{PHASE}-run-{run_id}]"

    # 1. Clone the test repo into tmp_path
    # 2. Copy Ralph source into the repo
    # 3. ralph setup
    # 4. Create a status:ready issue with title_prefix via gh
    # 5. ralph daemon --issue=<N> (single-issue mode)
    # 6. Assert: issue transitioned through expected stages
    # 7. Assert: trajectory.jsonl exists and has expected events
    # 8. Assert: at least one commit was made to the test repo
    # 9. On success: gh issue close <N> with comment "E2E test successful"
    # 10. On failure: leave issue open at failing stage for operator review
    # 11. Cleanup: remove local clone (issue state retained per §8.5 lifecycle)
```

**E2E acceptance gate per phase:**

| Phase | E2E acceptance test |
|-------|---------------------|
| A | A `status:ready` issue on `samdharma/ralph-e2e-test` progresses through DESIGN → BUILD → VERIFY → `status:review` (or `status:blocked` for a known-bad issue) |
| B | Same as A, plus: kill -9 the daemon mid-BUILD, restart, observe resume at BUILD (not DESIGN) |
| C | Same as A, plus: `ralph engine.py` has no module >500 lines |
| D | Same as A, plus: a flaky test quarantines itself after 2 consecutive failures |

### 8.6 Regression testing

For every change to `core/pipeline/`:

1. Run `make test` — all unit + integration tests pass.
2. Run `make validate` — Ralph validates itself (uses its own pipeline to ensure the validate script works).
3. Run E2E gate (only on main branch, only with `RALPH_E2E=1`).

---

## 9. Boundaries

### 9.1 Always do

- **Preserve the `gh` CLI as the only GitHub interface.** All issue read/write goes through `gh`. Do not introduce direct GitHub API calls (REST or GraphQL) from Python.
- **Preserve the public `ralph` CLI surface.** No command may be renamed or removed in v3.1. New commands and flags are additive only.
- **Maintain idempotency on all engine side effects.** Every label transition, comment, file write, and commit must be safe to retry (keyed by `run_id`).
- **Preserve the 8-state label machine.** No new `status:*` labels may be added without human review.
- **Validate inputs at the boundary.** Use Pydantic for any external data entering the system (issue body, design spec JSON, gh CLI output). Validation failures must produce clear errors, not silent fallback.
- **Run `make test` before any commit.** CI must pass. No exceptions.
- **Update the spec when decisions change.** If we discover the data model needs to change, update this doc first, then implement.
- **Every PR must pass the 8-item checklist in §13** before merge. PR template at `.github/PULL_REQUEST_TEMPLATE.md` enforces this.
- **Update `CHANGELOG.md` on every phase PR.** New entries go under "Unreleased" in plain English. Released at phase tag time.

### 9.2 Ask first about

- **Major tech stack changes outside this spec.** Adding async, switching to a different agent binary, replacing `gh` with direct API calls, etc. — surface and wait for approval.
- **Major structural changes outside this spec.** New top-level packages, new CLI commands that change user workflow, new external dependencies beyond Pydantic.
- **Removing code paths.** Especially anything in `core/engine.py` (R1, S1), `core/validate.py` (P1, U2), or the stage prompts. Removing a path is a breaking change for any project that customized those files.
- **Schema changes to artifact files.** If we change the structure of `docs/designs/<N>.md`, `.ralph/issue-<N>-tests.json`, or `config/TEST_MAP.yaml`, existing projects need a migration story.
- **Adding or changing `status:*` labels.**
- **Changing `bin/ralph` install flow** (it's preserved in v3.1.x per Assumption 7; only v3.2 may drop it).

### 9.3 Never do

- **Move away from `gh` for issue/ticket management.** Direct GitHub API calls, custom REST clients, or non-`gh` issue stores are forbidden in v3.1.
- **Deviate from CLI best practice.** Commands must be discoverable (`ralph help` lists them), composable (flags don't shadow each other), and follow Unix conventions (exit 0 = success, non-zero = failure; `--help` available on every command).
- **Commit secrets.** GitHub tokens, API keys, passwords — never in source, never in commits.
- **Edit the `vendor/` or `tests/` directories of the E2E test repo** (`samdharma/ralph-e2e-test`). It's a shared resource.
- **Remove failing tests without approval.** A failing test is a signal. If it's wrong, fix the test. If the behavior it tests is wrong, fix the behavior. Never delete.
- **Force-push to `main` or `ralph-v3.1`.** Branch protection applies.
- **Merge without passing CI.** Green build is required.

---

## 10. Phase-by-Phase Success Criteria

Each phase has its own success criteria. The full phase only "completes" when all criteria are met.

### 10.1 Phase A — Quick wins

**Goal:** Ship 7 small, isolated improvements that unblock later work.

| # | Item | Acceptance criteria |
|---|------|---------------------|
| A1 (P1) | Pytest exit-code classification | `validate.py` emits structured JSON `{exit_code, classification, action}` on every run. Pytest exit 124, 137, 143 each trigger distinct handling. |
| A2 (R5) | Hard-block test tampering | After TEST stage, QA-written test files have `chmod 0444`. IMPLEMENT agent attempting to edit receives `Permission denied`. `_detect_tampered_tests` is now a sanity check, not a warning. |
| A3 (R1) | Drop `pi --continue` Mode B | `_run_implement_subagent` reads from `.ralph/issues/<N>/artifacts/` directory. No `--continue` flag in any `pi` or `kimi` invocation. kimi works identically to pi (no session-UUID workaround). |
| A4 (U2) | Structured JUnit XML | `validate.py --junitxml=<path>` emits JUnit XML. Agent prompts include only `<failure>` blocks when tests fail. |
| A5 (U6) | Better error messages | Every failure comment includes: last 50 lines of agent stdout, link to trajectory file (when available), link to failure report. |
| A6 (P3) | Critical-path test set | `.ralph/config.toml` accepts `[validate] critical_paths = [...]`. These tests run first; failure blocks BUILD. |
| A7 (S5) | Drop legacy `PROGRESS.md` | `docs/agent/PROGRESS.md` no longer written by the engine. `_update_progress_board` removed. Status board exists only on GitHub (labels + Kanban). |

**Phase A E2E gate:** Create a `status:ready` issue on `samdharma/ralph-e2e-test`, run `ralph daemon`, observe issue progress to `status:review`. Verify the trajectory file (when implemented) or git log shows the 7 changes.

**Phase A release:** `ralph-v3.1.0` tagged and released on GitHub.

### 10.2 Phase B — Reliability primitives

| # | Item | Acceptance criteria |
|---|------|---------------------|
| B1 (R2) | Per-stage retry budgets | BUILD stage auto-retries on pytest 124/137/143 (up to 1 retry). Re-invokes sub-agent with failure output on exit 1 (up to 2 retries). DESIGN failures block immediately. |
| B2 (R3) | Idempotency keys | All engine actions (label transitions, comments, file writes) keyed by `run_id`. Crash + restart does not double-execute. `.ralph/issues/<N>/idempotency.jsonl` exists per issue. |
| B3 (R4) | Mechanism-enforced isolation | TEST and VERIFY sub-agents run in git worktrees. `src/` is mounted read-only. Agent cannot read implementation code at the filesystem level. |
| B4 (S4) | Single trajectory file | `.ralph/issues/<N>/trajectory.jsonl` exists per issue. All events (stage transitions, sub-agent invocations, validation runs, label transitions) written here. Pydantic-typed. |
| B5 (U1) | `ralph doctor` | `ralph doctor` runs without args and diagnoses recent failures. `ralph doctor <N>` focuses on issue #N. Output is human-readable, includes actionable next steps. |

**Phase B E2E gate:** Same as A. Plus: `kill -9 <daemon pid>` mid-BUILD, restart daemon, observe resume at BUILD (not DESIGN). Verify `idempotency.jsonl` exists and is consistent.

**Phase B release:** `ralph-v3.1.1`.

### 10.3 Phase C — Structural simplification

| # | Item | Acceptance criteria |
|---|------|---------------------|
| C1 (S1) | Split `engine.py` | `core/engine.py` is <200 lines (CLI entrypoint only). All business logic in `core/pipeline/`. Each file <500 lines. `make test` passes; behavior is unchanged. |
| C2 (S2) | Distribute via GitHub Releases | `gh release create ralph-v3.1.2 --generate-notes` works. README install instructions updated to use the tarball URL. `scripts/release.sh` automates tag + push + release. `Makefile` exposes `make release`. |
| C3 (P2) | Quarantine for known-flaky tests | `tests/quarantine.yaml` exists. `validate.py` deselects quarantined tests. Quarantine is auto-added on 2 consecutive failures; auto-removed after 7 days. `🦠 Flake quarantined: <test_id>` issue is posted to GitHub. |
| C4 (P4) | Skip expensive tiers on retry | `ralph validate --retry` runs only `--pytest-paths`. Integration/full/e2e tiers skipped. |

**Phase C E2E gate:** Same as B. Plus: a flake on `samdharma/ralph-e2e-test` quarantines itself after 2 consecutive failures. The `ralph-v3.1.2` release appears on the GitHub Releases page.

**Phase C release:** `ralph-v3.1.2`.

### 10.4 Phase D — Performance

| # | Item | Acceptance criteria |
|---|------|---------------------|
| D1 (P5) | Parallel TEST + IMPLEMENT | BUILD stage runs TEST and IMPLEMENT in parallel git worktrees. Wall-clock time on a typical issue is reduced by 30%+ vs. sequential. |
| D2 (U5) | Single retry label (additive) | New `status:retry` label works alongside existing retry labels. Engine recognizes both. Old labels are not deprecated in v3.1. |
| D3 (U3) | `ralph --dry-run` | `ralph daemon --dry-run` walks the pipeline up to (not including) agent invocation. Validates gh auth, git remote, labels, paths. Useful for CI health checks. |

**Phase D E2E gate:** Same as C. Plus: `ralph daemon --dry-run` exits 0 on the E2E repo. Parallel BUILD measured at <30% time of sequential.

**Phase D release:** `ralph-v3.1.3`. **This is the v3.1 release candidate.** If green, the release is promoted to `ralph-v3.1` (final).

---

## 11. Open Questions

All initial questions have been resolved during the requirements interview (2026-06-26). The spec is ready for human review.

### Resolved in this session

| # | Question | Resolution |
|---|----------|------------|
| 1 | Makefile target set | A — Full 11-target Makefile |
| 2 | E2E test gating | A — Local via env var; CI via workflow_dispatch + push |
| 3 | Migration story | B — Explicit `ralph migrate` command |
| 4 | Branch strategy | A — Single `ralph-v3.1` branch + community documentation |
| 5 | `ralph migrate` semantics | B — Aggressive: state files + regenerated stage prompts (only if matching v3 defaults) |
| 6 | E2E test data lifecycle | B — Auto-close successful issues; leave failed issues open |
| 7 | `ralph doctor` scope | A — All 5 diagnostic categories |
| 8 | PR review checklist | A — All 8 checks enforced via PR template |

### Remaining decisions deferred to PLAN phase

These need to be resolved when we PLAN each phase (not now):

1. **Phase A first PR scope:** Should the Phase A PR be one mega-PR (all 7 items) or split into 2-3 smaller PRs? My current recommendation is one PR per phase, but Phase A has 7 items which may strain review capacity. Defer to PLAN.
2. **Migration ordering:** `ralph migrate` must land before any schema change that breaks v3. Specifically: A3 (artifact handoff) and B4 (trajectory schema) are the breaking changes. PLAN phase will sequence `ralph migrate` ahead of those.
3. **CHANGELOG.md initial content:** Should the v3.1.0 changelog include a "Breaking changes for v3 users" section explicitly listing `ralph migrate` as the required upgrade step? My recommendation: yes. Defer to PLAN.
4. **Test repo archival:** After v3.1 ships (Phase D complete), should `samdharma/ralph-e2e-test` be archived in favor of a v3.1-specific test repo? My recommendation: keep the same repo; the existing label set is correct for v3.1. Defer to PLAN.

---

## 12. Glossary

| Term | Meaning |
|------|---------|
| **Agent** | An AI coding assistant invoked by Ralph — `pi` or `kimi`. |
| **Artifact** | A file under `.ralph/issues/<N>/artifacts/` written by one stage and read by the next (R1). |
| **BUILD stage** | The middle pipeline stage. Spawns TEST and IMPLEMENT sub-agents. |
| **DESIGN stage** | First pipeline stage. Architect persona writes a design spec. |
| **E2E test** | End-to-end test against `samdharma/ralph-e2e-test`, gated on `RALPH_E2E=1`. |
| **Issue** | A GitHub Issue used as a Ralph ticket. |
| **Idempotency key** | A `(run_id, action, target, body_hash)` tuple that prevents duplicate execution (R3). |
| **Mode A** | Isolated sub-agent session. No prior context. (Replaced by artifact handoff in R1.) |
| **Mode B** | Sub-agent session inheriting prior context via `--continue`. (Deprecated in R1.) |
| **Pipeline** | The 3-stage flow: DESIGN → BUILD → VERIFY. |
| **QA tests** | Tests written by the TEST sub-agent (independent of implementation). |
| **`run_id`** | A unique identifier per pipeline run for an issue. Used for idempotency (R3). |
| **Sub-agent** | An agent invocation spawned by the parent agent (TEST, IMPLEMENT, VERIFY). |
| **Trajectory** | Per-issue JSONL log of every event (S4). Replaces fragmented sources of truth. |
| **VERIFY stage** | Final pipeline stage. Independent reviewer checks diff against spec. |

---

## 13. PR Review Checklist

Every PR to `ralph-v3.1` must pass these 8 checks before merge. The PR template at `.github/PULL_REQUEST_TEMPLATE.md` enforces this; reviewers consult `.github/REVIEWER_CHECKLIST.md` for verification guidance.

| # | Check | What it means | How reviewer verifies |
|---|-------|---------------|----------------------|
| 1 | **Spec section referenced** | PR description links to the section of `docs/IMPROVEMENT_ROADMAP_SPEC.md` this PR implements. | Open the linked spec section; confirm the PR's changes map to it. |
| 2 | **Phase declared** | PR description declares which phase (A/B/C/D) this PR is part of. | Confirm phase matches `CHANGELOG.md` placement. |
| 3 | **Acceptance criteria met** | PR description checks off every acceptance criterion from §10 of the spec for this item. | Cross-reference §10 against PR description's checklist. |
| 4 | **`make test` green** | Unit + integration tests pass locally. CI link attached. | Click CI link; confirm green. |
| 5 | **`make lint` green** | black, isort, flake8, mypy all pass. | Same as #4. |
| 6 | **E2E gate passed (if applicable)** | For phase-complete PRs: link to a successful E2E run on `samdharma/ralph-e2e-test`. For partial-phase PRs: not required. | Open the E2E run log; confirm phase-tagged issues reached expected terminal state. |
| 7 | **`CHANGELOG.md` updated** | New entry under "Unreleased" describing the change in plain English. | `git diff docs/CHANGELOG.md` shows new entry. |
| 8 | **Migration story documented (if applicable)** | For schema-changing PRs: section in `docs/development_workflow.md` describes the migration path. | `git diff docs/development_workflow.md` shows new section, OR PR description explicitly says "no migration needed." |

**For the v3.1.0 release (end of Phase A), an additional check is added:**

| 9 | **Migration tested on a real v3 project** | The PR has been run against a v3-format project to verify `ralph migrate` works end-to-end. | PR description links to the test output (E2E-style run). |

This check only applies to v3.1.0; later releases do not introduce migration-breaking changes.

---

## 14. E2E Test Data Lifecycle

The E2E test creates real GitHub issues on `samdharma/ralph-e2e-test`. To prevent unbounded growth while preserving debugging context, issues follow this lifecycle:

### 14.1 Issue creation

```python
# tests/e2e/conftest.py
import time

def make_e2e_issue(phase: str, description: str) -> int:
    run_id = time.strftime("%Y%m%d-%H%M%S")
    title = f"[e2e-phase-{phase}-run-{run_id}] {description}"
    body = f"""E2E test issue created by `tests/e2e/test_ralph_e2e_repo.py`.

Phase: {phase}
Run ID: {run_id}

This issue will be auto-closed on successful pipeline completion.
If it reaches `status:blocked`, it is left open for operator review.
"""
    issue_num = gh("issue", "create", "--title", title, "--body", body,
                   "--label", "type:task", "--label", "status:ready")
    return issue_num
```

### 14.2 Issue outcomes

| Outcome | Detection | Action |
|---------|-----------|--------|
| **Success** | Issue transitions to `status:review` | Test posts comment "✅ E2E test successful. Auto-closing per development workflow." → `gh issue close <N>` |
| **Expected failure** | Issue transitions to `status:blocked` AND the failure is a known-flaky scenario | Test exits 0 (failure is the expected outcome); issue left open |
| **Unexpected failure** | Issue transitions to `status:blocked` AND the failure is unexpected | Test exits non-zero; issue left open for operator review |
| **Hang/timeout** | Test's internal timeout (5 minutes per stage, 20 minutes total) elapses | Test exits non-zero; issue left at whatever stage it was in |

### 14.3 Retention

| State | Retention |
|-------|-----------|
| Successful issues (closed) | Permanent — kept as historical record |
| Failed issues (open) | 30 days from creation. A scheduled workflow (`/.github/workflows/e2e-cleanup.yml`) closes issues older than 30 days with comment "Auto-closed: stale E2E failure (>30 days old)." Manual override available. |

### 14.4 Discovery helpers

The `docs/development_workflow.md` guide includes shell snippets for common E2E queries:

```bash
# Find all E2E issues from the last 7 days
gh issue list --repo samdharma/ralph-e2e-test \
  --search "[e2e-phase- in:title" \
  --state all \
  --json number,title,state,createdAt \
  --jq '.[] | select(.createdAt > (now - 604800 | todate))'

# Find failed E2E issues still open
gh issue list --repo samdharma/ralph-e2e-test \
  --search "[e2e-phase- in:title status:blocked in:body" \
  --state open

# Close a stale failed E2E issue
gh issue close <N> --repo samdharma/ralph-e2e-test \
  --comment "Closing stale E2E failure."
```

---

## 15. References

- **Architectural review:** [`docs/architectural-review-2026-06-26.md`](architectural-review-2026-06-26.md) — Source of all recommendations in this spec.
- **v3 PRD:** [`docs/v3-redesign.md`](v3-redesign.md) — Ralph v3 baseline.
- **E2E test repo:** https://github.com/samdharma/ralph-e2e-test — Real GitHub repo for validation.
- **External research reports:** `.ralph/research/*.md` — Detailed analyses of OpenHands, AutoCodeRover, SWE-agent, LangGraph, AutoGen, Letta, Buildbot, Temporal, Argo Workflows.
- **PR template:** `.github/PULL_REQUEST_TEMPLATE.md` — 8-item review checklist (§13).
- **Reviewer guide:** `.github/REVIEWER_CHECKLIST.md` — How to verify each checklist item.
- **Development workflow:** [`docs/development_workflow.md`](development_workflow.md) — User-facing guide for contributors and operators.

---

*Last updated: 2026-06-26. All initial open questions resolved; awaiting final human review before implementation begins.*
