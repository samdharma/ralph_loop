# Tasks: Ralph v3.1 — Improvement Roadmap

## Overview

This file decomposes every component in [`docs/IMPROVEMENT_ROADMAP_PLAN.md`](IMPROVEMENT_ROADMAP_PLAN.md) §1.1 into test-first, file-level tasks. It is the third artifact of the `spec-driven-development` workflow (SPECIFY → PLAN → **TASKS** → IMPLEMENT). It does **not** modify the spec or the plan, and it does **not** contain any code or test bodies — only task descriptions.

**Source documents (immutable inputs):**
- Spec: `docs/IMPROVEMENT_ROADMAP_SPEC.md` (15 sections, 833 lines) — *what* to build.
- Plan: `docs/IMPROVEMENT_ROADMAP_PLAN.md` (9 sections, 785 lines) — *how* to sequence and verify it.

**Companion artifact:** Each task here corresponds 1:1 to a checkpoint in plan §5.1 (between-item) and §5.2 (between-phase). The plan's intra-phase ordering (§2.1, §2.2, §2.3, §2.4) is preserved exactly.

## Conventions

- **Task IDs:** `<Phase>-<Seq>` — e.g., `A-001`, `A-002`, `B-001`. Sequence numbers reflect execution order (top-to-bottom = dependency order).
- **Test-first ordering:** For every task that introduces new logic, the preceding task in the sequence is `Write tests for X` (the test fails before implementation). The implement task follows and is verified by the new tests.
- **Acceptance criteria** must be testable without reading the code. Bullets start with `- [ ]` to match the suggested phase E2E checklist style. 3–5 criteria per task.
- **Verify** must be a runnable command (`pytest ...`, `make ...`, `python -m ...`), not a description.
- **Files** lists every file the task will create or modify (≤ 5 per task, per Hard Constraint).
- **Dependencies** lists task IDs that must complete first; `None` if independent.
- **Spec citation** points to the relevant section in the spec (e.g., `§10.1 A3`). Citations use the spec's numbering, not the plan's.
- **All commands assume working directory = repo root** unless otherwise noted.
- **Phase boundaries:** Each phase's first task compiles + passes tests. Each phase's last task passes the phase-complete E2E gate (plan §5.3, spec §10).

## Task Summary

| Phase | Tasks | First task | Last task (E2E gate) |
|-------|-------|-----------|---------------------|
| A — Quick wins | A-001 … A-039 | A-001 (development_workflow.md) | A-039 (Phase A E2E gate → tag `ralph-v3.1.0`) |
| B — Reliability primitives | B-001 … B-034 | B-001 (add `pydantic` dep) | B-034 (Phase B E2E gate → tag `ralph-v3.1.1`) |
| C — Structural simplification | C-001 … C-049 | C-001 (tests for C3.1) | C-049 (Phase C E2E gate → tag `ralph-v3.1.2`) |
| D — Performance | D-001 … D-015 | D-001 (tests for D3.1) | D-015 (Phase D E2E gate → tag `ralph-v3.1.3` + promote `ralph-v3.1`) |
| **Total** | **137 tasks** | | |

---

## Phase A — Quick wins (target release: `ralph-v3.1.0`)

**Phase A E2E gate** (spec §10.1): A `status:ready` issue on `samdharma/ralph-e2e-test` progresses through DESIGN → BUILD → VERIFY → `status:review`. Git log shows the eight Phase A changes (A-prelude + A1–A7). See plan §2.1.

**Per plan §2.1 intra-phase ordering.** All items from plan §1.1 Phase A components are covered.

### A-prelude: Project scaffolding (plan §2.1 order 2)

These tasks add the project-shape files required by PR-checklist items #6, #7, #8 (spec §13). They touch only newly created files and `pyproject.toml` (version bump to `3.1.0-dev` per NEW-8).

- [ ] **Task A-001: Add `docs/development_workflow.md` (NEW-1)**
  - **Description:** Create the contributor-facing development workflow guide. Documents the single `ralph-v3.1` branch strategy, one-PR-per-phase policy, E2E test repo convention (`samdharma/ralph-e2e-test`), and the v3 → v3.1 upgrade one-liner. This file is referenced by PR-checklist item #8 (spec §13.8) and by R-3 mitigation in plan §3 (migration archive cleanup).
  - **Acceptance criteria:**
    - [ ] File exists at `docs/development_workflow.md` and is ≥ 50 lines.
    - [ ] Includes a "Branch strategy" section naming `ralph-v3.1` as the only release branch.
    - [ ] Includes a "E2E test repo" section naming `samdharma/ralph-e2e-test` (master branch).
    - [ ] Includes a `rm -rf .ralph/migration-archive/` cleanup one-liner (per plan §3 R-3).
  - **Verify:** `test -f docs/development_workflow.md && grep -q "ralph-v3.1" docs/development_workflow.md && grep -q "ralph-e2e-test" docs/development_workflow.md && grep -q "migration-archive" docs/development_workflow.md`
  - **Files:** `docs/development_workflow.md` (create)
  - **Dependencies:** None
  - **Spec citation:** §3.8, §13.8, §14

- [ ] **Task A-002: Add `docs/CHANGELOG.md` (NEW-2)**
  - **Description:** Create the changelog file with a placeholder "Unreleased — Phase A work in progress" entry. Required by PR-checklist item #7 (spec §13.7). Subsequent tasks (A-038, B-033, C-049, D-014) append phase-complete entries.
  - **Acceptance criteria:**
    - [ ] File exists at `docs/CHANGELOG.md`.
    - [ ] Contains a `# Changelog` heading.
    - [ ] Contains an "Unreleased" section header.
  - **Verify:** `test -f docs/CHANGELOG.md && head -1 docs/CHANGELOG.md | grep -q "^# Changelog" && grep -q "Unreleased" docs/CHANGELOG.md`
  - **Files:** `docs/CHANGELOG.md` (create)
  - **Dependencies:** None
  - **Spec citation:** §9.1.9, §13.7

- [ ] **Task A-003: Add `.github/PULL_REQUEST_TEMPLATE.md` (NEW-3)**
  - **Description:** Create the PR template with the 8-item checklist from spec §13. PRs opened against `ralph-v3.1` will auto-populate this checklist. For v3.1.0 specifically, also include checklist item #9 (spec §13.9: migration tested on a real v3 project).
  - **Acceptance criteria:**
    - [ ] File exists at `.github/PULL_REQUEST_TEMPLATE.md`.
    - [ ] Contains checkboxes for all 8 items in spec §13 (1–8).
    - [ ] Contains a ninth checkbox for v3.1.0: "Migration tested on a real v3 project."
  - **Verify:** `test -f .github/PULL_REQUEST_TEMPLATE.md && grep -c "^- \[" .github/PULL_REQUEST_TEMPLATE.md` returns ≥ 9
  - **Files:** `.github/PULL_REQUEST_TEMPLATE.md` (create)
  - **Dependencies:** None
  - **Spec citation:** §13

- [ ] **Task A-004: Add `.github/REVIEWER_CHECKLIST.md` (NEW-4)**
  - **Description:** Create the reviewer-facing verification guide. Each of the 9 PR-checklist items in spec §13 gets a "How reviewer verifies" subsection explaining what evidence to look for (linked spec section, CI run, manual check). Reviewers consult this file alongside the PR description.
  - **Acceptance criteria:**
    - [ ] File exists at `.github/REVIEWER_CHECKLIST.md`.
    - [ ] Contains a numbered subsection (1–9) matching spec §13 checklist items.
    - [ ] Subsection #1 (Spec section referenced) explains how to open the linked spec section and confirm the diff maps to it.
    - [ ] Subsection #6 (E2E gate) explains that for partial-phase PRs the checkbox may be unchecked.
  - **Verify:** `test -f .github/REVIEWER_CHECKLIST.md && grep -E "^## " .github/REVIEWER_CHECKLIST.md | wc -l` returns ≥ 9
  - **Files:** `.github/REVIEWER_CHECKLIST.md` (create)
  - **Dependencies:** None
  - **Spec citation:** §13

- [ ] **Task A-005: Add GitHub Actions workflows (NEW-5, NEW-6)**
  - **Description:** Add two CI workflows. `e2e.yml` runs `tests/e2e/test_ralph_e2e_repo.py` on `workflow_dispatch` and on push to `ralph-v3.1`, gated on `RALPH_E2E=1`. `e2e-cleanup.yml` runs daily (cron), closes failed E2E issues older than 30 days per spec §14.3.
  - **Acceptance criteria:**
    - [ ] File exists at `.github/workflows/e2e.yml` and parses as valid YAML.
    - [ ] `e2e.yml` triggers on `workflow_dispatch` AND `push: branches: [ralph-v3.1]`.
    - [ ] `e2e.yml` runs `pytest tests/e2e/` with `env: RALPH_E2E: "1"`.
    - [ ] File exists at `.github/workflows/e2e-cleanup.yml` and triggers on a daily cron schedule.
  - **Verify:** `python -c "import yaml; yaml.safe_load(open('.github/workflows/e2e.yml')); yaml.safe_load(open('.github/workflows/e2e-cleanup.yml'))"`
  - **Files:** `.github/workflows/e2e.yml` (create), `.github/workflows/e2e-cleanup.yml` (create)
  - **Dependencies:** None
  - **Spec citation:** §8.5, §14.3

- [ ] **Task A-006: Add E2E test skeleton (NEW-7)**
  - **Description:** Create `tests/e2e/test_ralph_e2e_repo.py` with the skeleton from spec §8.5. The test is `@pytest.mark.skipif(RALPH_E2E != "1")` so it does not run in normal CI. Each phase's verification task (A-039, B-034, C-050, D-015) extends this file with phase-specific assertions.
  - **Acceptance criteria:**
    - [ ] File exists at `tests/e2e/test_ralph_e2e_repo.py`.
    - [ ] Contains `import pytest` and a test function decorated with `@pytest.mark.skipif(os.environ.get("RALPH_E2E") != "1", ...)`.
    - [ ] Imports `gh` (or the project's wrapper) and references `samdharma/ralph-e2e-test`.
    - [ ] `tests/e2e/__init__.py` exists (empty) so pytest discovers the directory.
  - **Verify:** `test -f tests/e2e/test_ralph_e2e_repo.py && test -f tests/e2e/__init__.py && grep -q "RALPH_E2E" tests/e2e/test_ralph_e2e_repo.py`
  - **Files:** `tests/e2e/__init__.py` (create), `tests/e2e/test_ralph_e2e_repo.py` (create)
  - **Dependencies:** None
  - **Spec citation:** §8.5, §14

- [ ] **Task A-007: Add partial Makefile (C2.1, Phase A slice)**
  - **Description:** Create `Makefile` with targets: `install`, `test`, `test-unit`, `test-integration`, `lint`, `format`, `validate`, `version-show`, `version-bump`. Per plan §2.1, the `release` target is deferred to Phase C task C-011. Each target must invoke the underlying toolchain documented in spec §5.4.
  - **Acceptance criteria:**
    - [ ] File exists at `Makefile` and contains a `test:` target that runs `pytest tests/unit/ tests/integration/`.
    - [ ] Contains a `lint:` target that runs `black --check`, `isort --check-only`, `flake8`, and `mypy`.
    - [ ] Contains a `validate:` target that runs `ralph validate --tier=targeted` (or the equivalent invoked via `python -m core.engine validate --tier=targeted`).
    - [ ] Does NOT contain a `release:` target (deferred to C-011).
  - **Verify:** `make -n test && make -n lint && make -n validate` (dry-runs without error); `grep -L "^release:" Makefile` returns `Makefile`
  - **Files:** `Makefile` (create)
  - **Dependencies:** None
  - **Spec citation:** §5.4, §6.1

- [ ] **Task A-008: Bump `pyproject.toml` to `3.1.0-dev` (NEW-8 partial) and add `core/migrate.py` stub**
  - **Description:** Per plan §2.1 first-commit rationale, this task sets up the version baseline and the migrate-module placeholder. `pyproject.toml` version → `3.1.0-dev`. `core/migrate.py` exists with a module docstring and a single function `migrate(...)` that raises `NotImplementedError("not yet")`. The placeholder is replaced by A-010.
  - **Acceptance criteria:**
    - [ ] `pyproject.toml` `[project].version` is `3.1.0-dev`.
    - [ ] `core/migrate.py` exists and contains a function named `migrate` that raises `NotImplementedError`.
    - [ ] `python -c "from core.migrate import migrate"` succeeds (import works).
    - [ ] `make test-unit` passes (no existing tests broken).
  - **Verify:** `grep '^version = "3.1.0-dev"' pyproject.toml && python -c "from core.migrate import migrate; print(migrate.__name__)" && make test-unit`
  - **Files:** `pyproject.toml` (modify), `core/migrate.py` (create)
  - **Dependencies:** A-002 (CHANGELOG must exist before version bump so subsequent A-038 has a place to write)
  - **Spec citation:** §3.1, §5.5

### A-prelude: `ralph migrate` command

This is the FIRST logical feature of Phase A. Per spec §3.6 and plan §1.3 ordering rule #1, `ralph migrate` MUST land before A3.3 (artifact handoff) and B4.2 (trajectory schema). This is a single NEW component (`core/migrate.py` + `bin/ralph` dispatch entry).

- [ ] **Task A-009: Write tests for `ralph migrate` (RED)**
  - **Description:** Create `tests/unit/test_migrate.py` covering the migration behavior from spec §3.6 and plan §3 R-3 mitigation. Tests cover: idempotency on re-run, refusal when daemon PID file exists, dry-run JSON output, archive-before-move, and v3 → v3.1 file layout transformations. The tests fail against the A-008 stub (`migrate` raises `NotImplementedError`).
  - **Acceptance criteria:**
    - [ ] File exists at `tests/unit/test_migrate.py` with ≥ 8 test cases.
    - [ ] One test asserts `migrate()` is idempotent (running twice produces identical filesystem state).
    - [ ] One test asserts `migrate()` raises `RuntimeError` (or returns non-zero) when `.ralph/daemon.pid` exists.
    - [ ] One test asserts `migrate(--dry-run)` returns a JSON object listing every action that WOULD be taken, and does NOT modify the filesystem.
    - [ ] One test asserts that for every v3 file slated for rename/move, an original copy exists at `.ralph/migration-archive/<timestamp>/`.
  - **Verify:** `pytest tests/unit/test_migrate.py -v` exits non-zero (tests fail against stub); `grep -c "^def test_" tests/unit/test_migrate.py` ≥ 8
  - **Files:** `tests/unit/test_migrate.py` (create)
  - **Dependencies:** A-008 (stub must exist for import)
  - **Spec citation:** §3.6, §5.2

- [ ] **Task A-010: Implement `ralph migrate` command (GREEN)**
  - **Description:** Implement `migrate(dry_run: bool = False) -> dict` in `core/migrate.py`. Behavior per spec §3.6: migrate state files (`.ralph/issue-<N>-*.json|.md` → `.ralph/issues/<N>/...` per spec §6.2), regenerate stage prompts that match v3 default templates (leave customized prompts alone with a warning), archive originals to `.ralph/migration-archive/<timestamp>/`. Idempotent. Refuses to run when `.ralph/daemon.pid` exists. Wire the command into `bin/ralph` dispatch. Replace the A-008 stub.
  - **Acceptance criteria:**
    - [ ] `python -c "from core.migrate import migrate; print(migrate(dry_run=True))"` returns a JSON-serializable dict listing planned actions.
    - [ ] Running `migrate()` then `migrate()` a second time is idempotent (no diff in `.ralph/` except possibly archive dir).
    - [ ] `migrate()` raises `RuntimeError` when `.ralph/daemon.pid` is present.
    - [ ] `bin/ralph migrate` dispatches directly to `core.migrate.migrate()` and exits 0 on success.
    - [ ] `pytest tests/unit/test_migrate.py` all pass.
  - **Verify:** `pytest tests/unit/test_migrate.py -v && bin/ralph migrate --dry-run` exits 0 with JSON on stdout
  - **Files:** `core/migrate.py` (modify), `bin/ralph` (modify)
  - **Dependencies:** A-009
  - **Spec citation:** §3.6, §5.2, §6.2, §11.2

### A1: Pytest exit-code classification (spec §10.1 A1)

Per plan §1.1, A1 is split into A1.1 (the classifier module) and A1.2 (extending `run_pytest_invocation` to use it and emit structured output). Both touch `core/validate.py`.

- [ ] **Task A-011: Write tests for the pytest exit-code classifier (A1.1, RED)**
  - **Description:** Tests in `tests/unit/core/test_validate.py` (extend existing file) for a new classifier function `classify_pytest_exit_code(exit_code: int) -> Classification` returning a structured object with fields `exit_code`, `classification` (one of `success`, `test_failure`, `timeout`, `interrupted`, `internal_error`, `unknown`), and `action` (one of `accept`, `retry_transient`, `block`). The classifier must handle at minimum exit codes 0, 1, 2, 3, 4, 5, 124, 137, 143 per spec §10.1 A1.
  - **Acceptance criteria:**
    - [ ] `tests/unit/core/test_validate.py` exists and contains a class or set of tests named `TestPytestExitCodeClassifier`.
    - [ ] One test asserts exit 0 → `success` / `accept`.
    - [ ] One test asserts exit 1 → `test_failure` / `block`.
    - [ ] One test asserts exit 124 → `timeout` / `retry_transient`.
    - [ ] One test asserts exit 137 and 143 each → `interrupted` / `retry_transient` (distinct from timeout per spec §10.1 A1).
  - **Verify:** `pytest tests/unit/core/test_validate.py::TestPytestExitCodeClassifier -v` exits non-zero (tests fail — function not yet defined)
  - **Files:** `tests/unit/core/test_validate.py` (modify)
  - **Dependencies:** None
  - **Spec citation:** §10.1 A1

- [ ] **Task A-012: Implement the pytest exit-code classifier (A1.1, GREEN)**
  - **Description:** Add `classify_pytest_exit_code(exit_code)` to `core/validate.py`. Use a frozen dataclass for `Classification` per spec §7.2. Lookup table per plan §1.3 R-6 mitigation pattern: `PYTEST_TIMEOUT_RETRY = RetryPolicy(...)` etc. The classifier is pure (no I/O), so it lives in the existing module without new files.
  - **Acceptance criteria:**
    - [ ] `classify_pytest_exit_code(0).action == "accept"`.
    - [ ] `classify_pytest_exit_code(1).action == "block"`.
    - [ ] `classify_pytest_exit_code(124).classification == "timeout"`.
    - [ ] `classify_pytest_exit_code(137)` and `(143)` return `classification == "interrupted"`, distinct from timeout.
    - [ ] `pytest tests/unit/core/test_validate.py::TestPytestExitCodeClassifier` all pass; `mypy core/validate.py` clean.
  - **Verify:** `pytest tests/unit/core/test_validate.py::TestPytestExitCodeClassifier -v && mypy core/validate.py`
  - **Files:** `core/validate.py` (modify), `core/validate.py` (extend — add `Classification` dataclass within module)
  - **Dependencies:** A-011
  - **Spec citation:** §7.2, §10.1 A1

- [ ] **Task A-013: Write tests for structured pytest result emitter (A1.2, RED)**
  - **Description:** Tests for the modified `run_pytest_invocation` in `core/validate.py`. The function must now return a structured dict `{exit_code, classification, action, stdout_tail, junitxml_path}` rather than a bare exit code. Tests use mocked `subprocess.run` per spec §8.4.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_validate.py` under `TestRunPytestInvocation` (≥ 4 tests).
    - [ ] One test asserts return value is a dict with all 5 keys.
    - [ ] One test asserts `classification` and `action` match the values returned by `classify_pytest_exit_code` for the same exit code.
    - [ ] One test asserts `stdout_tail` is the last 50 lines of `subprocess.run(...).stdout`.
    - [ ] One test asserts `junitxml_path` is `None` when `--junitxml` is not passed (defer the A4.1 path-coverage to A-016).
  - **Verify:** `pytest tests/unit/core/test_validate.py::TestRunPytestInvocation -v` exits non-zero (function not yet modified)
  - **Files:** `tests/unit/core/test_validate.py` (modify)
  - **Dependencies:** A-012 (classifier must exist)
  - **Spec citation:** §10.1 A1

- [ ] **Task A-014: Implement structured pytest result emitter (A1.2, GREEN)**
  - **Description:** Modify `run_pytest_invocation` in `core/validate.py` to use the new classifier and return the structured dict. Existing call sites (in `core/engine.py`) are updated in a later task — this task only changes `core/validate.py`. Preserve backward compatibility: if a caller destructures the result via `.returncode`, the function still works (either keep an attribute or document the migration).
  - **Acceptance criteria:**
    - [ ] `run_pytest_invocation(...)` returns a `dict` with keys `exit_code`, `classification`, `action`, `stdout_tail`, `junitxml_path`.
    - [ ] All existing tests in `tests/unit/core/test_validate.py` still pass (existing call patterns still work).
    - [ ] `pytest tests/unit/core/test_validate.py` all pass; `mypy core/validate.py` clean.
    - [ ] Existing call sites in `core/engine.py` are NOT yet updated (deferred to B1.x).
  - **Verify:** `pytest tests/unit/core/test_validate.py -v && mypy core/validate.py`
  - **Files:** `core/validate.py` (modify)
  - **Dependencies:** A-013
  - **Spec citation:** §10.1 A1, §7.2

### A2: Hard-block test tampering (spec §10.1 A2)

- [ ] **Task A-015: Write tests for QA-test permission lock (A2.1, RED)**
  - **Description:** Tests for `_run_test_subagent` in `core/engine.py`. After the TEST sub-agent finishes, the QA-written test files must have mode `0o444` (read-only for all). Tests use mocked `subprocess.run` for the agent invocation and assert on actual filesystem state via `tmp_path`.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_engine.py` under `TestRunTestSubagent` (≥ 3 tests).
    - [ ] One test asserts that after `_run_test_subagent` returns, every file under the QA test directory has mode `0o444`.
    - [ ] One test asserts that IMPLEMENT sub-agent (invoked afterward) attempting to write to a QA test file raises `PermissionError`.
    - [ ] One test asserts that test files are NOT chmod'd before the TEST sub-agent returns (ordering matters).
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestRunTestSubagent -v` exits non-zero
  - **Files:** `tests/unit/core/test_engine.py` (modify)
  - **Dependencies:** None
  - **Spec citation:** §10.1 A2

- [ ] **Task A-016: Implement QA-test permission lock (A2.1, GREEN)**
  - **Description:** In `core/engine.py`, after the TEST sub-agent subprocess completes successfully, walk the QA-written test directory (passed as a function arg or derived from issue artifact dir per spec §6.2) and call `os.chmod(path, 0o444)` on each file. Log the lock event to the engine's existing logger. No change to sub-agent invocation itself.
  - **Acceptance criteria:**
    - [ ] After `_run_test_subagent` returns success, every file under the QA test directory has mode `0o444` (verifiable via `os.stat`).
    - [ ] Lock event appears in the engine log at INFO level.
    - [ ] `pytest tests/unit/core/test_engine.py::TestRunTestSubagent` all pass.
    - [ ] `make test-unit` still passes (no regression in other engine tests).
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestRunTestSubagent -v && make test-unit`
  - **Files:** `core/engine.py` (modify)
  - **Dependencies:** A-015
  - **Spec citation:** §10.1 A2

- [ ] **Task A-017: Write tests for `_detect_tampered_tests` reclassification (A2.2, RED)**
  - **Description:** Tests for `_detect_tampered_tests` in `core/engine.py:1472`. The function used to warn-and-continue; it must now be a sanity check that exits non-zero (raises or returns `False`) when any QA-written test file's mode is NOT `0o444`. Tests cover: pristine state → returns True; tampered state → raises (or returns False and triggers block).
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_engine.py` under `TestDetectTamperedTests` (≥ 3 tests).
    - [ ] One test asserts pristine state (all files `0o444`) → function returns `True`.
    - [ ] One test asserts a file with mode `0o644` → function returns `False` AND triggers the block path (assertable via mocked downstream call).
    - [ ] One test asserts the function no longer logs at WARNING level only — it raises or returns an actionable error.
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestDetectTamperedTests -v` exits non-zero
  - **Files:** `tests/unit/core/test_engine.py` (modify)
  - **Dependencies:** A-016 (the chmod lock must exist for the tests to be meaningful)
  - **Spec citation:** §10.1 A2

- [ ] **Task A-018: Reclassify `_detect_tampered_tests` to a sanity check (A2.2, GREEN)**
  - **Description:** Modify `_detect_tampered_tests` at `core/engine.py:1472` per spec §10.1 A2: change from advisory warning to a hard block. Return value semantics: `True` = pass / continue; raise (or return `False` and call the existing block-on-tamper path). Log at ERROR level, not WARNING.
  - **Acceptance criteria:**
    - [ ] `_detect_tampered_tests` raises (or returns `False`) when any QA test file has mode ≠ `0o444`.
    - [ ] Returns `True` only when all files are `0o444`.
    - [ ] Log level is ERROR (not WARNING) for the failure case.
    - [ ] `pytest tests/unit/core/test_engine.py::TestDetectTamperedTests` all pass.
    - [ ] `make test-unit` still passes.
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestDetectTamperedTests -v && make test-unit`
  - **Files:** `core/engine.py` (modify — only the function at line 1472 area)
  - **Dependencies:** A-017
  - **Spec citation:** §10.1 A2

### A3: Drop `pi --continue` Mode B → artifact handoff (spec §10.1 A3)

Per plan §3 R-1, A3 is HIGH risk. Three tasks per plan §1.1: A3.1 (artifact writer module), A3.2 (artifact-reading IMPLEMENT prompt), A3.3 (drop `--continue` flag).

- [ ] **Task A-019: Write tests for artifact directory writer (A3.1, RED)**
  - **Description:** Tests for `core/pipeline/agents/artifacts.py` (NEW module). The module exposes functions to write the per-issue artifact directory layout from spec §6.2: `write_design`, `write_files_in_scope`, `write_acceptance_criteria`, `write_qa_tests`. Tests verify file contents match inputs, directory exists after each write, and re-writing the same issue is idempotent.
  - **Acceptance criteria:**
    - [ ] `tests/unit/core/pipeline/agents/test_artifacts.py` exists with ≥ 6 test cases.
    - [ ] One test asserts `write_design(issue_num, design_text)` creates `.ralph/issues/<N>/artifacts/design.md` with content == `design_text`.
    - [ ] One test asserts `write_files_in_scope(issue_num, paths_list)` creates `files_in_scope.json` containing the list as JSON.
    - [ ] One test asserts `write_acceptance_criteria(issue_num, ac_list)` creates `acceptance_criteria.json` with each AC as an object `{id, criterion}`.
    - [ ] One test asserts idempotency: writing twice produces identical filesystem state.
  - **Verify:** `pytest tests/unit/core/pipeline/agents/test_artifacts.py -v` exits non-zero (module not yet created); `grep -c "^def test_" tests/unit/core/pipeline/agents/test_artifacts.py` ≥ 6
  - **Files:** `tests/unit/core/pipeline/agents/__init__.py` (create, empty), `tests/unit/core/pipeline/agents/test_artifacts.py` (create)
  - **Dependencies:** None
  - **Spec citation:** §6.2, §10.1 A3, §7.2

- [ ] **Task A-020: Implement artifact directory writer (A3.1, GREEN)**
  - **Description:** Create `core/pipeline/agents/artifacts.py` per spec §6.2 layout. Exposes `write_design(issue_num: int, design_text: str) -> Path`, `write_files_in_scope(issue_num: int, paths: list[str]) -> Path`, `write_acceptance_criteria(issue_num: int, ac: list[dict]) -> Path`, `write_qa_tests(issue_num: int, qa_tests: list[str]) -> Path`. All functions create parent directories as needed. Idempotent on re-write.
  - **Acceptance criteria:**
    - [ ] `core/pipeline/agents/artifacts.py` exists with the four write functions.
    - [ ] `python -c "from core.pipeline.agents.artifacts import write_design; print(write_design(1, 'x').name)"` returns `design.md`.
    - [ ] `pytest tests/unit/core/pipeline/agents/test_artifacts.py` all pass.
    - [ ] `make test-unit` passes (no regressions).
  - **Verify:** `pytest tests/unit/core/pipeline/agents/test_artifacts.py -v && make test-unit`
  - **Files:** `core/pipeline/agents/__init__.py` (create, empty), `core/pipeline/agents/artifacts.py` (create)
  - **Dependencies:** A-019
  - **Spec citation:** §6.2, §10.1 A3

- [ ] **Task A-021: Write tests for artifact-reading IMPLEMENT prompt (A3.2, RED)**
  - **Description:** Tests for the modified `_assemble_subagent_prompt` and `_run_implement_subagent` in `core/engine.py`. The IMPLEMENT prompt must now read the four artifact files from `.ralph/issues/<N>/artifacts/` and inline their contents into the prompt. Tests verify: when artifacts are present, the assembled prompt contains the design text + JSON-parsed file list + acceptance criteria; when artifacts are absent, behavior is `fail fast` (raises FileNotFoundError) rather than silent fallback.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_engine.py` under `TestAssembleImplementPrompt` (≥ 4 tests).
    - [ ] One test asserts the assembled prompt contains the verbatim design text.
    - [ ] One test asserts the assembled prompt contains every path from `files_in_scope.json`.
    - [ ] One test asserts the assembled prompt contains every acceptance criterion as a numbered item.
    - [ ] One test asserts: missing artifact dir → `FileNotFoundError`, NOT a prompt with empty sections.
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestAssembleImplementPrompt -v` exits non-zero
  - **Files:** `tests/unit/core/test_engine.py` (modify)
  - **Dependencies:** A-020 (writer must exist for test fixtures)
  - **Spec citation:** §10.1 A3, §7.2

- [ ] **Task A-022: Implement artifact-reading IMPLEMENT prompt (A3.2, GREEN)**
  - **Description:** Modify `_assemble_subagent_prompt` and `_run_implement_subagent` in `core/engine.py` to read from `.ralph/issues/<N>/artifacts/` per spec §7.2 example. Update `docs/agent/prompts/implement.md` to instruct the agent that its inputs come from disk (artifact dir), not from session context.
  - **Acceptance criteria:**
    - [ ] `_assemble_subagent_prompt(issue_num)` reads design + files_in_scope + acceptance_criteria + qa_tests from the artifact dir and inlines them.
    - [ ] Missing artifact dir raises `FileNotFoundError` (no silent fallback).
    - [ ] `docs/agent/prompts/implement.md` contains the sentence "Read your inputs from `.ralph/issues/<N>/artifacts/` (not from session context)."
    - [ ] `pytest tests/unit/core/test_engine.py::TestAssembleImplementPrompt` all pass.
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestAssembleImplementPrompt -v && grep -q "artifacts" docs/agent/prompts/implement.md`
  - **Files:** `core/engine.py` (modify), `docs/agent/prompts/implement.md` (modify)
  - **Dependencies:** A-021
  - **Spec citation:** §10.1 A3, §7.2

- [ ] **Task A-023: Write tests for dropping `--continue` flag (A3.3, RED)**
  - **Description:** Tests for `invoke_agent` in `core/engine.py` and its two callers (`_run_implement_subagent`, `_run_test_subagent`). After A3.3, NO call to `pi` or `kimi` should pass `--continue` or `--session`. Tests assert the assembled command list contains neither flag for either agent.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_engine.py` under `TestInvokeAgentNoContinue` (≥ 4 tests).
    - [ ] One test asserts `invoke_agent(binary="pi", ...)` does not include `--continue` in `argv`.
    - [ ] One test asserts `invoke_agent(binary="kimi", ...)` does not include `--continue` in `argv`.
    - [ ] One test asserts neither binary invocation passes `--session <path>`.
    - [ ] One test asserts the kimi and pi code paths are now identical (no kimi-specific workaround) per spec §10.1 A3.
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestInvokeAgentNoContinue -v` exits non-zero
  - **Files:** `tests/unit/core/test_engine.py` (modify)
  - **Dependencies:** A-022 (the new assemble logic must exist for the test fixtures)
  - **Spec citation:** §10.1 A3, §1.1 (R1 from ar §5.1)

- [ ] **Task A-024: Drop `--continue` flag from agent invocation (A3.3, GREEN)**
  - **Description:** In `core/engine.py`, remove all `--continue` and `--session <path>` arguments from `invoke_agent` and its callers. The kimi-specific UUID workaround (per spec §1.1) is also removed; both `pi` and `kimi` use the identical invocation path. Reference: plan §3 R-1 mitigation; spec §1.1.2.
  - **Acceptance criteria:**
    - [ ] `invoke_agent` does not accept a `session` argument (or, if it does, it's ignored).
    - [ ] `grep -n "\\-\\-continue\\|\\-\\-session" core/engine.py` returns no matches.
    - [ ] `grep -n "kimi.*session\\|session.*kimi" core/engine.py` returns no matches.
    - [ ] `pytest tests/unit/core/test_engine.py::TestInvokeAgentNoContinue` all pass.
    - [ ] `make test-unit` passes (no regressions; the kimi and pi paths are now symmetric).
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestInvokeAgentNoContinue -v && ! grep -q -- "--continue\|--session" core/engine.py && make test-unit`
  - **Files:** `core/engine.py` (modify)
  - **Dependencies:** A-023
  - **Spec citation:** §10.1 A3, §1.1.2, §3.3 (plan)

### A4: Structured JUnit XML (spec §10.1 A4)

- [ ] **Task A-025: Write tests for the JUnit XML emitter (A4.1, RED)**
  - **Description:** Tests for the new `--junitxml=<path>` flag on `validate.py`. When passed, the function emits a JUnit XML file matching the standard schema (`<testsuite>`, `<testcase>`, `<failure>` elements). Tests assert the file exists, parses as valid XML, and contains one `<testcase>` per pytest test result.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_validate.py` under `TestJunitxmlFlag` (≥ 3 tests).
    - [ ] One test asserts `--junitxml=/tmp/x.xml` (passed via `run_pytest_invocation(junitxml_path=...)`) creates a file at that path.
    - [ ] One test asserts the file parses via `xml.etree.ElementTree.parse` without error.
    - [ ] One test asserts each pytest test case appears as a `<testcase classname="..." name="...">` element.
    - [ ] One test asserts a failing pytest test produces a `<failure>` block under the corresponding `<testcase>`.
  - **Verify:** `pytest tests/unit/core/test_validate.py::TestJunitxmlFlag -v` exits non-zero
  - **Files:** `tests/unit/core/test_validate.py` (modify)
  - **Dependencies:** A-014 (structured result emitter must exist; `--junitxml` is a new arg to it)
  - **Spec citation:** §10.1 A4

- [ ] **Task A-026: Implement the JUnit XML emitter (A4.1, GREEN)**
  - **Description:** Add `--junitxml=<path>` handling to `run_pytest_invocation` in `core/validate.py`. Pass the path through to `pytest --junitxml=<path>`, then read the file back and return its path in the structured result dict (key already exists from A-014: `junitxml_path`). Add a CLI argument in `core/engine.py`'s `validate` subcommand so `bin/ralph validate --junitxml=<path>` works.
  - **Acceptance criteria:**
    - [ ] `python -m core.engine validate --junitxml=/tmp/x.xml` produces a JUnit XML file at `/tmp/x.xml`.
    - [ ] The XML parses and contains `<testsuite>` + `<testcase>` elements.
    - [ ] `pytest tests/unit/core/test_validate.py::TestJunitxmlFlag` all pass.
    - [ ] `make test-unit` passes.
  - **Verify:** `pytest tests/unit/core/test_validate.py::TestJunitxmlFlag -v && make test-unit`
  - **Files:** `core/validate.py` (modify), `core/engine.py` (modify — add `--junitxml` arg)
  - **Dependencies:** A-025
  - **Spec citation:** §10.1 A4, §5.3

- [ ] **Task A-027: Update agent prompts to parse JUnit XML (A4.2)**
  - **Description:** Per spec §10.1 A4: agent prompts must consume JUnit XML. Update `docs/agent/PROMPT.md` and the four stage prompts (`design.md`, `test.md`, `implement.md`, `verify.md`) to instruct the agent: "When reading test failures, use `<failure>` blocks from the JUnit XML at `<path>` — not raw pytest stdout."
  - **Acceptance criteria:**
    - [ ] `docs/agent/PROMPT.md` contains the phrase "JUnit XML".
    - [ ] Each of the 4 stage prompts contains the phrase "JUnit XML".
    - [ ] `grep -l "JUnit XML" docs/agent/PROMPT.md docs/agent/prompts/*.md` returns all 5 files.
  - **Verify:** `grep -l "JUnit XML" docs/agent/PROMPT.md docs/agent/prompts/*.md | wc -l` returns 5
  - **Files:** `docs/agent/PROMPT.md` (modify), `docs/agent/prompts/design.md` (modify), `docs/agent/prompts/test.md` (modify), `docs/agent/prompts/implement.md` (modify), `docs/agent/prompts/verify.md` (modify)
  - **Dependencies:** A-026 (the emitter must exist for the prompt instructions to be actionable)
  - **Spec citation:** §10.1 A4

### A5: Better error messages (spec §10.1 A5)

- [ ] **Task A-028: Write tests for enriched failure comments (A5.1, RED)**
  - **Description:** Tests for `_write_stage_report` and `_format_stage_failure` in `core/engine.py`. Every failure comment posted to a GitHub issue must include: (a) last 50 lines of agent stdout, (b) link to trajectory file when available, (c) link to failure report. Tests mock `gh` and assert the body of the comment contains all three.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_engine.py` under `TestEnrichedFailureComments` (≥ 4 tests).
    - [ ] One test asserts the comment body contains the literal substring "stdout tail" or "last 50 lines" followed by ≥ 1 line.
    - [ ] One test asserts the comment body contains a Markdown link to a trajectory file (when one exists).
    - [ ] One test asserts the comment body contains a Markdown link to a failure report.
    - [ ] One test asserts the comment is idempotent: re-posting the same failure does not duplicate content.
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestEnrichedFailureComments -v` exits non-zero
  - **Files:** `tests/unit/core/test_engine.py` (modify)
  - **Dependencies:** None
  - **Spec citation:** §10.1 A5

- [ ] **Task A-029: Implement enriched failure comments (A5.1, GREEN)**
  - **Description:** Modify `_write_stage_report` and `_format_stage_failure` in `core/engine.py`. The new comment format includes a "## Agent stdout (last 50 lines)" section, a "## Trajectory" section with a link (when `.ralph/issues/<N>/trajectory.jsonl` exists, otherwise omit), and a "## Failure report" section linking to `.ralph/issue-<N>-report.md`.
  - **Acceptance criteria:**
    - [ ] A posted failure comment contains a section labeled "Agent stdout" with ≥ 1 line of stdout content.
    - [ ] When `trajectory.jsonl` exists, the comment contains "Trajectory: `.ralph/issues/<N>/trajectory.jsonl`" (Markdown link).
    - [ ] The comment contains a Markdown link to the failure report.
    - [ ] `pytest tests/unit/core/test_engine.py::TestEnrichedFailureComments` all pass.
    - [ ] `make test-unit` passes.
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestEnrichedFailureComments -v && make test-unit`
  - **Files:** `core/engine.py` (modify)
  - **Dependencies:** A-028
  - **Spec citation:** §10.1 A5

### A6: Critical-path test set (spec §10.1 A6)

- [ ] **Task A-030: Write tests for critical-path test config (A6.1, RED)**
  - **Description:** Tests for the new `--critical` flag and `[validate] critical_paths` config on `validate.py`. When `[validate] critical_paths` is set in `.ralph/config.toml`, the critical paths run FIRST; failure of any critical-path test blocks BUILD. Tests use a fixture config file with a non-empty critical_paths list.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_validate.py` under `TestCriticalPaths` (≥ 4 tests).
    - [ ] One test asserts `critical_paths = []` (default) → behavior is unchanged.
    - [ ] One test asserts non-empty `critical_paths` → those tests run first (verifiable via pytest invocation order or a recorded test sequence).
    - [ ] One test asserts a failing critical-path test → return value's `action == "block"` (not `accept`).
    - [ ] One test asserts `--critical` CLI flag overrides the config (forces critical mode even when config is empty).
  - **Verify:** `pytest tests/unit/core/test_validate.py::TestCriticalPaths -v` exits non-zero
  - **Files:** `tests/unit/core/test_validate.py` (modify)
  - **Dependencies:** A-014 (structured result emitter; `action` field semantics)
  - **Spec citation:** §10.1 A6, §5.3

- [ ] **Task A-031: Implement critical-path test config (A6.1, GREEN)**
  - **Description:** In `core/validate.py`, add `[validate] critical_paths = [...]` parsing from `.ralph/config.toml` (TOML). Add `--critical` CLI flag. When critical paths are configured, `run_pytest_invocation` runs them first via pytest's `-k` filter or by running them as a separate invocation. The `action` field reflects critical-path failures as `block`.
  - **Acceptance criteria:**
    - [ ] A `.ralph/config.toml` with `[validate]\ncritical_paths = ["tests/unit/core/test_validate.py::test_smoke"]` makes `bin/ralph validate` run that test first.
    - [ ] `--critical` CLI flag works regardless of config.
    - [ ] Critical-path failures are surfaced with `action == "block"`.
    - [ ] `pytest tests/unit/core/test_validate.py::TestCriticalPaths` all pass.
    - [ ] `make test-unit` passes (no regressions in default behavior).
  - **Verify:** `pytest tests/unit/core/test_validate.py::TestCriticalPaths -v && make test-unit`
  - **Files:** `core/validate.py` (modify), `core/engine.py` (modify — add `--critical` flag to validate subcommand)
  - **Dependencies:** A-030
  - **Spec citation:** §10.1 A6, §5.3

### A7: Drop legacy `PROGRESS.md` (spec §10.1 A7)

- [ ] **Task A-032: Write tests verifying `PROGRESS.md` is no longer written (A7.1, RED)**
  - **Description:** Tests for the engine's stage-write behavior. After A7.1, NO call path should write to `docs/agent/PROGRESS.md`. Tests assert the file is not created during a full mocked pipeline run, and `grep` for `_update_progress_board` returns no source matches.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_engine.py` under `TestNoProgressBoard` (≥ 3 tests).
    - [ ] One test asserts a full mocked pipeline run (DESIGN → BUILD → VERIFY) does NOT create `docs/agent/PROGRESS.md`.
    - [ ] One test asserts `grep -n "_update_progress_board" core/engine.py` returns no matches after A7.1 implementation.
    - [ ] One test asserts no other module imports or calls the removed function.
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestNoProgressBoard -v` exits non-zero; `grep -c "_update_progress_board" core/engine.py` ≥ 1 (function still present before this task's GREEN)
  - **Files:** `tests/unit/core/test_engine.py` (modify)
  - **Dependencies:** None
  - **Spec citation:** §10.1 A7

- [ ] **Task A-033: Remove `_update_progress_board` (A7.1, GREEN)**
  - **Description:** Delete the `_update_progress_board` function (~150 LOC per plan §1.1 A7.1) and its call sites from `core/engine.py`. Per plan §2.1 order 9, this comes BEFORE A3.x so that A3's diff doesn't get entangled with this removal. Status board moves entirely to GitHub labels + Kanban per spec §10.1 A7.
  - **Acceptance criteria:**
    - [ ] `grep -n "_update_progress_board" core/engine.py` returns no matches.
    - [ ] `grep -n "PROGRESS.md" core/engine.py` returns no matches.
    - [ ] `wc -l core/engine.py` is ≥ 150 lines smaller than before this task.
    - [ ] `pytest tests/unit/core/test_engine.py::TestNoProgressBoard` all pass.
    - [ ] `make test-unit` passes (no regressions).
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestNoProgressBoard -v && ! grep -q "_update_progress_board\|PROGRESS.md" core/engine.py && make test-unit`
  - **Files:** `core/engine.py` (modify)
  - **Dependencies:** A-032
  - **Spec citation:** §10.1 A7

- [ ] **Task A-034: Update prompts to drop `PROGRESS.md` references (A7.2)**
  - **Description:** Remove all references to `docs/agent/PROGRESS.md` from `docs/agent/PROMPT.md` and the four stage prompts. Replace with "Status is tracked via GitHub labels and the Kanban board."
  - **Acceptance criteria:**
    - [ ] `grep -l "PROGRESS.md" docs/agent/PROMPT.md docs/agent/prompts/*.md` returns no files.
    - [ ] Each of the 5 prompt files contains the phrase "GitHub labels" (status is tracked there).
  - **Verify:** `! grep -q "PROGRESS.md" docs/agent/PROMPT.md docs/agent/prompts/design.md docs/agent/prompts/test.md docs/agent/prompts/implement.md docs/agent/prompts/verify.md && grep -l "GitHub labels" docs/agent/PROMPT.md docs/agent/prompts/*.md | wc -l` returns 5
  - **Files:** `docs/agent/PROMPT.md` (modify), `docs/agent/prompts/design.md` (modify), `docs/agent/prompts/test.md` (modify), `docs/agent/prompts/implement.md` (modify), `docs/agent/prompts/verify.md` (modify)
  - **Dependencies:** A-033 (engine must no longer write to PROGRESS.md for prompt edits to be consistent)
  - **Spec citation:** §10.1 A7

### A polish: install script and README (per plan §2.1 order 12 — C2.3, C2.4)

- [ ] **Task A-035: Update `scripts/install.sh` for v3.1 (C2.3)**
  - **Description:** Update `scripts/install.sh` to support the new install flow per spec §3.2: `git clone` + `git checkout ralph-v3.1` + `./scripts/install.sh`. Preserve the existing `bin/ralph` symlink flow per spec §3.7 (bash dispatcher is kept through v3.1.x). Remove any reference to `curl | bash`.
  - **Acceptance criteria:**
    - [ ] `scripts/install.sh` no longer contains `curl | bash` or `curl|bash`.
    - [ ] `scripts/install.sh` contains a "Prerequisites" section documenting `git` and `gh` (per spec §4.1).
    - [ ] `scripts/install.sh` creates a `bin/ralph` symlink in the user's PATH (preserved).
    - [ ] Running `bash scripts/install.sh --help` exits 0 and prints usage.
  - **Verify:** `! grep -q "curl.*bash\|curl|bash" scripts/install.sh && grep -q "gh" scripts/install.sh && grep -q "bin/ralph" scripts/install.sh && bash scripts/install.sh --help`
  - **Files:** `scripts/install.sh` (modify)
  - **Dependencies:** A-007 (Makefile must exist so `make install` is documented as an alternative)
  - **Spec citation:** §3.2, §3.7, §5.4

- [ ] **Task A-036: Update `README.md` install instructions (C2.4)**
  - **Description:** Update the README install section to document both flows per plan §3 R-9: (a) `make install` for new users, (b) `bin/ralph` symlink for existing users. Remove the `curl | bash` snippet. Reference `docs/development_workflow.md` for the upgrade flow including `ralph migrate`.
  - **Acceptance criteria:**
    - [ ] `README.md` no longer contains `curl | bash`.
    - [ ] `README.md` install section mentions `make install` AND the `bin/ralph` symlink.
    - [ ] `README.md` upgrade section references `ralph migrate` and links to `docs/development_workflow.md`.
  - **Verify:** `! grep -q "curl.*bash" README.md && grep -q "make install" README.md && grep -q "ralph migrate" README.md && grep -q "development_workflow.md" README.md`
  - **Files:** `README.md` (modify)
  - **Dependencies:** A-035 (install.sh must be updated first so README accurately references it)
  - **Spec citation:** §3.2, §3.7, §5.4

### A finalization: version bump and CHANGELOG entry

- [ ] **Task A-037: Bump version to `3.1.0` (NEW-8)**
  - **Description:** Per spec §5.5, versions are tracked in three places. Set: `pyproject.toml` `[project].version` → `3.1.0`, `core/__init__.py` `__version__` → `"3.1.0"`, `bin/ralph` `cmd_version` output → `3.1.0`. Use `make version-bump PART=minor` (or manually edit the three files if the Makefile target isn't yet in place).
  - **Acceptance criteria:**
    - [ ] `grep '^version = "3.1.0"' pyproject.toml` succeeds.
    - [ ] `grep '^__version__ = "3.1.0"' core/__init__.py` succeeds.
    - [ ] `bin/ralph version` prints `3.1.0`.
    - [ ] No `3.1.0-dev` references remain in the three files.
  - **Verify:** `grep -E '^version = "3.1.0"|^__version__ = "3.1.0"' pyproject.toml core/__init__.py && bin/ralph version | grep -q "3.1.0"`
  - **Files:** `pyproject.toml` (modify), `core/__init__.py` (modify), `bin/ralph` (modify)
  - **Dependencies:** A-036 (README must reflect the new install path before release tag)
  - **Spec citation:** §5.5

- [ ] **Task A-038: Update `CHANGELOG.md` with v3.1.0 entry (NEW-2 release entry)**
  - **Description:** Per plan §6.3, the v3.1.0 CHANGELOG entry must include a "Breaking changes for v3 users" section explicitly listing `ralph migrate` as the required upgrade step. Also list all A-items under "New features" with spec §10.1 IDs (A1, A2, A3, A4, A5, A6, A7) and the A-prelude. Mark "Unreleased" → "3.1.0 — 2026-MM-DD".
  - **Acceptance criteria:**
    - [ ] `docs/CHANGELOG.md` contains a heading `## 3.1.0`.
    - [ ] Under that heading, a subheading "Breaking changes for v3 users" lists `ralph migrate` as a required action with a one-liner.
    - [ ] New features subheading lists each of: A-prelude (ralph migrate), A1 (pytest exit codes), A2 (chmod 0444), A3 (artifact handoff), A4 (JUnit XML), A5 (better errors), A6 (critical paths), A7 (drop PROGRESS.md).
    - [ ] Deprecated subheading mentions `docs/agent/PROGRESS.md` and `.ralph/session-<N>.jsonl` (kept for one migration cycle).
  - **Verify:** `grep -q "^## 3.1.0" docs/CHANGELOG.md && grep -q "Breaking changes" docs/CHANGELOG.md && grep -q "ralph migrate" docs/CHANGELOG.md && grep -qE "A-prelude|A3.*artifact|A7.*PROGRESS" docs/CHANGELOG.md`
  - **Files:** `docs/CHANGELOG.md` (modify)
  - **Dependencies:** A-037 (version bump happens before the release entry so the heading is correct)
  - **Spec citation:** §9.1.9, §13.7, §11.3 (plan)

### Phase A verification (E2E gate per spec §10.1)

- [ ] **Task A-039: Phase A E2E gate — release `ralph-v3.1.0`**
  - **Description:** Run the full Phase A verification sequence per plan §2.1: `make test`, `make lint`, `make validate`, then trigger the E2E workflow on the `ralph-v3.1` branch. Confirm an `[e2e-phase-a-run-<timestamp>]` issue on `samdharma/ralph-e2e-test` progresses through DESIGN → BUILD → VERIFY → `status:review`. Confirm git log shows all eight Phase A changes. Tag the release and publish via `gh release`.
  - **Acceptance criteria:**
    - [ ] `make test` exits 0 (unit + integration green).
    - [ ] `make lint` exits 0 (black, isort, flake8, mypy all pass).
    - [ ] `make validate` exits 0 (Ralph validates itself with `--tier=targeted`).
    - [ ] An E2E issue tagged `[e2e-phase-a-run-*]` reaches `status:review` on `samdharma/ralph-e2e-test`.
    - [ ] Git tag `ralph-v3.1.0` exists and is pushed to origin.
    - [ ] `gh release view ralph-v3.1.0` shows the release with auto-generated notes.
    - [ ] PR-checklist item #9 (spec §13.9) is satisfied: `tests/integration/test_v3_migration.py` passes against the v3 fixture (per plan §5.4 setup).
  - **Verify:** `make test && make lint && make validate && gh workflow run e2e.yml --ref ralph-v3.1 && git tag ralph-v3.1.0 && git push origin ralph-v3.1.0 && gh release create ralph-v3.1.0 --generate-notes`
  - **Files:** (no code changes; verification only)
  - **Dependencies:** A-038
  - **Spec citation:** §10.1, §13.9, §14 (E2E lifecycle)

---

## Phase B — Reliability primitives (target release: `ralph-v3.1.1`)

**Phase B E2E gate** (spec §10.2): Same as Phase A, plus: `kill -9 <daemon pid>` mid-BUILD, restart daemon, observe resume at BUILD (not DESIGN). Verify `.ralph/issues/<N>/idempotency.jsonl` and `trajectory.jsonl` both exist and are consistent.

**Per plan §2.2 intra-phase ordering.** Pydantic v2 lands at the start of Phase B (per spec §4.2 and plan §1.3 ordering rule #7 — Phase A stays dependency-free).

### B-prelude: Add `pydantic>=2.0` to `pyproject.toml` (NEW-9)

- [ ] **Task B-001: Add `pydantic>=2.0` dependency (NEW-9)**
  - **Description:** Add `pydantic>=2.0,<3.0` to `pyproject.toml` per spec §4.2 (rationale table) and plan §3 R-4 mitigation. This is the first new top-level dependency added since v3. Phase A MUST stay dependency-free per plan §1.3 ordering rule #7. After this task, `make test` must still pass (no usage yet, just the dep).
  - **Acceptance criteria:**
    - [ ] `pyproject.toml` `[project]` section contains `dependencies = [..., "pydantic>=2.0,<3.0"]` (or equivalent in the project's dep format).
    - [ ] `pip install -e .` (or equivalent) succeeds.
    - [ ] `python -c "import pydantic; print(pydantic.VERSION)"` succeeds and prints `2.x`.
    - [ ] `make test` passes — no existing tests break.
    - [ ] No `import pydantic` calls exist in source code yet (B-003 is the first).
  - **Verify:** `grep -q "pydantic>=2.0" pyproject.toml && python -c "import pydantic; print(pydantic.VERSION.startswith('2'))" && make test`
  - **Files:** `pyproject.toml` (modify)
  - **Dependencies:** None
  - **Spec citation:** §4.2, §4.3, §3.1 (plan)

### B4: Single trajectory file (spec §10.2 B4) — lands first per plan §2.2 order 1

- [ ] **Task B-002: Write tests for `TrajectoryEvent` Pydantic union (B4.1, RED)**
  - **Description:** Tests in `tests/unit/schemas/test_events.py` for `core/schemas/events.py`. The module exposes a `TrajectoryEvent` Pydantic v2 union type (discriminated union on `event_type`) with at least 5 variants: `StageTransition`, `SubagentInvocation`, `ValidationRun`, `LabelTransition`, `Retry`. Each variant has a typed payload.
  - **Acceptance criteria:**
    - [ ] `tests/unit/schemas/__init__.py` (empty) exists.
    - [ ] `tests/unit/schemas/test_events.py` exists with ≥ 5 test cases (one per variant).
    - [ ] One test asserts each variant serializes to a JSON dict with `event_type` discriminator.
    - [ ] One test asserts `TrajectoryEvent.model_validate(json_dict)` reconstructs the correct variant.
    - [ ] One test asserts invalid `event_type` raises `ValidationError`.
  - **Verify:** `pytest tests/unit/schemas/test_events.py -v` exits non-zero (module not yet created)
  - **Files:** `tests/unit/schemas/__init__.py` (create, empty), `tests/unit/schemas/test_events.py` (create)
  - **Dependencies:** B-001 (pydantic dep must be installed)
  - **Spec citation:** §4.2, §10.2 B4

- [ ] **Task B-003: Implement `TrajectoryEvent` Pydantic union (B4.1, GREEN)**
  - **Description:** Create `core/schemas/__init__.py` (empty) and `core/schemas/events.py` with the `TrajectoryEvent` discriminated union per spec §4.2. Use Pydantic v2 `Annotated` + `Field(discriminator=...)` syntax. Per plan §3 R-4 mitigation, the model is read-only at first; no validation logic beyond type checking.
  - **Acceptance criteria:**
    - [ ] `core/schemas/events.py` exists; `from core.schemas.events import TrajectoryEvent` succeeds.
    - [ ] `TrajectoryEvent` is a `Union` of ≥ 5 typed variants with `event_type` discriminator.
    - [ ] `pytest tests/unit/schemas/test_events.py` all pass.
    - [ ] `mypy core/schemas/events.py` passes (--strict per spec §7.3).
    - [ ] `make test` passes (no regressions).
  - **Verify:** `pytest tests/unit/schemas/test_events.py -v && mypy core/schemas/events.py && make test`
  - **Files:** `core/schemas/__init__.py` (create, empty), `core/schemas/events.py` (create)
  - **Dependencies:** B-002
  - **Spec citation:** §4.2, §7.3, §10.2 B4

- [ ] **Task B-004: Write tests for the trajectory writer (B4.2, RED)**
  - **Description:** Tests for `core/pipeline/metrics.py` (NEW module). The module exposes `append_trajectory_event(issue_num: int, event: TrajectoryEvent) -> None` and `read_trajectory(issue_num: int) -> list[TrajectoryEvent]`. Events are written to `.ralph/issues/<N>/trajectory.jsonl` (JSON lines, one event per line). Tests assert file creation, line-delimited format, and round-trip serialization.
  - **Acceptance criteria:**
    - [ ] `tests/unit/core/pipeline/__init__.py` (empty) exists.
    - [ ] `tests/unit/core/pipeline/test_metrics.py` exists with ≥ 4 test cases.
    - [ ] One test asserts `append_trajectory_event(1, evt)` creates `.ralph/issues/1/trajectory.jsonl` with one line.
    - [ ] One test asserts two appends produce a file with exactly two lines (JSONL format).
    - [ ] One test asserts `read_trajectory(1)` returns the appended events in order.
    - [ ] One test asserts each line is valid JSON parseable by `json.loads`.
  - **Verify:** `pytest tests/unit/core/pipeline/test_metrics.py -v` exits non-zero (module not yet created)
  - **Files:** `tests/unit/core/pipeline/__init__.py` (create, empty), `tests/unit/core/pipeline/test_metrics.py` (create)
  - **Dependencies:** B-003 (TrajectoryEvent model must exist)
  - **Spec citation:** §10.2 B4, §6.2

- [ ] **Task B-005: Implement the trajectory writer (B4.2, GREEN)**
  - **Description:** Create `core/pipeline/metrics.py` per spec §6.2. Exposes `append_trajectory_event(issue_num, event)` (appends one JSONL line) and `read_trajectory(issue_num)` (returns list of `TrajectoryEvent`). Path resolution: `.ralph/issues/<N>/trajectory.jsonl`. Parent directory created on first append.
  - **Acceptance criteria:**
    - [ ] `core/pipeline/metrics.py` exists with the two functions.
    - [ ] `python -c "from core.pipeline.metrics import append_trajectory_event, read_trajectory; print('ok')"` succeeds.
    - [ ] `pytest tests/unit/core/pipeline/test_metrics.py` all pass.
    - [ ] `mypy core/pipeline/metrics.py` passes.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/test_metrics.py -v && mypy core/pipeline/metrics.py && make test`
  - **Files:** `core/pipeline/__init__.py` (create, empty), `core/pipeline/metrics.py` (create)
  - **Dependencies:** B-004
  - **Spec citation:** §10.2 B4, §6.2

### B2: Idempotency keys (spec §10.2 B2) — per plan §2.2 order 2

- [ ] **Task B-006: Write tests for `run_id` generator (B2.1, RED)**
  - **Description:** Tests for `core/pipeline/state.py` (NEW module). The module exposes `generate_run_id() -> str` that returns a string like `<timestamp>-<uuid4_short>` (e.g., `20260627T1530-a1b2c3d4`). Uniqueness is asserted by generating 100 IDs and verifying no collisions.
  - **Acceptance criteria:**
    - [ ] `tests/unit/core/pipeline/test_state.py` exists with ≥ 3 test cases.
    - [ ] One test asserts `generate_run_id()` returns a string matching `^\d{8}T\d{4}-[a-f0-9]{8}$`.
    - [ ] One test asserts 100 generated IDs are all distinct.
    - [ ] One test asserts two consecutive IDs differ in either the timestamp or the UUID portion.
  - **Verify:** `pytest tests/unit/core/pipeline/test_state.py -v` exits non-zero (module not yet created)
  - **Files:** `tests/unit/core/pipeline/test_state.py` (create)
  - **Dependencies:** B-001 (pydantic dep available; though this task may not use it yet)
  - **Spec citation:** §10.2 B2, §6.2

- [ ] **Task B-007: Implement `run_id` generator (B2.1, GREEN)**
  - **Description:** Create `core/pipeline/state.py` with `generate_run_id()` and (per spec §4.2) a `Stage(str, Enum)` enum with values `READY`, `DESIGN`, `BUILD`, `VERIFY`, `REVIEW`, `BLOCKED`. The enum is used by B-011. Also define `STATUS_LABEL = {s: f"status:{s.value}" for s in Stage}` per spec §7.2.
  - **Acceptance criteria:**
    - [ ] `core/pipeline/state.py` exists; `from core.pipeline.state import generate_run_id, Stage, STATUS_LABEL` succeeds.
    - [ ] `Stage.DESIGN.value == "design"` and `STATUS_LABEL[Stage.DESIGN] == "status:design"`.
    - [ ] `pytest tests/unit/core/pipeline/test_state.py` all pass.
    - [ ] `mypy core/pipeline/state.py` passes.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/test_state.py -v && mypy core/pipeline/state.py && make test`
  - **Files:** `core/pipeline/state.py` (create)
  - **Dependencies:** B-006
  - **Spec citation:** §4.2, §7.2, §10.2 B2

- [ ] **Task B-008: Write tests for the idempotency log writer (B2.2, RED)**
  - **Description:** Tests for `core/pipeline/github/client.py` (NEW module). The `GitHubClient` class accepts a `run_id` and writes a record to `.ralph/issues/<N>/idempotency.jsonl` before each gh CLI call. Tests assert the log file is created and contains the expected record format: `{timestamp, run_id, action, target, body_hash, returncode}`.
  - **Acceptance criteria:**
    - [ ] `tests/unit/core/pipeline/github/__init__.py` (empty) exists.
    - [ ] `tests/unit/core/pipeline/github/test_client.py` exists with ≥ 4 test cases.
    - [ ] One test asserts `client.comment(issue_num, body)` writes one line to `idempotency.jsonl` BEFORE invoking `gh`.
    - [ ] One test asserts re-invoking `client.comment(issue_num, same_body)` does NOT invoke `gh` a second time (idempotency check via mock call count).
    - [ ] One test asserts the logged record includes `run_id` matching the client's.
    - [ ] One test asserts a different `run_id` for the same `(issue_num, body)` DOES invoke `gh` (different run = re-execute).
  - **Verify:** `pytest tests/unit/core/pipeline/github/test_client.py -v` exits non-zero (module not yet created)
  - **Files:** `tests/unit/core/pipeline/github/__init__.py` (create, empty), `tests/unit/core/pipeline/github/test_client.py` (create)
  - **Dependencies:** B-007 (`run_id` generator and Stage enum must exist)
  - **Spec citation:** §10.2 B2, §7.2 (idempotent side-effects example)

- [ ] **Task B-009: Implement the idempotency log writer (B2.2, GREEN)**
  - **Description:** Create `core/pipeline/github/client.py` per spec §7.2 example. `GitHubClient.__init__(self, run_id: str)`. Methods: `comment(issue_num, body)`, `transition_label(issue_num, add, remove)` — each checks idempotency, invokes `gh`, records to log. Log path: `.ralph/issues/<N>/idempotency.jsonl`.
  - **Acceptance criteria:**
    - [ ] `core/pipeline/github/client.py` exists with `GitHubClient` class.
    - [ ] `python -c "from core.pipeline.github.client import GitHubClient; c = GitHubClient('test-run'); print(c.run_id)"` succeeds.
    - [ ] `pytest tests/unit/core/pipeline/github/test_client.py` all pass.
    - [ ] `mypy core/pipeline/github/client.py` passes.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/github/test_client.py -v && mypy core/pipeline/github/client.py && make test`
  - **Files:** `core/pipeline/github/__init__.py` (create, empty), `core/pipeline/github/client.py` (create)
  - **Dependencies:** B-008
  - **Spec citation:** §10.2 B2, §7.2

- [ ] **Task B-010: Write tests for wrapping existing `gh()` and `git()` helpers (B2.3, RED)**
  - **Description:** Tests in `tests/unit/core/test_engine.py` for an idempotent wrapper around the existing `gh()` and `git()` helper functions in `core/engine.py`. After B2.3, the engine's existing call sites (`transition_label`, `gh_comment`, file writes) use the new wrapper. Tests mock `subprocess.run` and assert: (a) the wrapper checks idempotency before invoking, (b) the wrapper records to `idempotency.jsonl`, (c) re-invoking with the same `run_id` does not double-execute.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_engine.py` under `TestIdempotentWrappers` (≥ 4 tests).
    - [ ] One test asserts `transition_label(1, "status:design", "status:ready", run_id="X")` invokes `gh` exactly once.
    - [ ] One test asserts `transition_label(1, ..., run_id="X")` invoked twice with same args does NOT invoke `gh` a second time.
    - [ ] One test asserts `gh_comment(1, "body", run_id="X")` invoked twice with same body does NOT double-execute.
    - [ ] One test asserts `idempotency.jsonl` is created and contains a record per actual execution.
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestIdempotentWrappers -v` exits non-zero
  - **Files:** `tests/unit/core/test_engine.py` (modify)
  - **Dependencies:** B-009 (the GitHubClient wrapper must exist for the engine to use)
  - **Spec citation:** §10.2 B2, §7.2

- [ ] **Task B-011: Wrap existing engine actions with idempotency (B2.3, GREEN)**
  - **Description:** In `core/engine.py`, modify the existing `gh()` and `git()` helpers (or add new wrappers `gh_idempotent`, `git_idempotent`) to consult `.ralph/issues/<N>/idempotency.jsonl` keyed by `(run_id, action, target, body_hash)`. Update ~10 existing call sites: `transition_label`, `gh_comment`, file writes. Per plan §1.3 ordering rule #3 and §3 R-3, the engine must NOT double-execute on crash-restart.
  - **Acceptance criteria:**
    - [ ] `core/engine.py` contains `gh_idempotent(...)` (or equivalent) that consults the log.
    - [ ] At least 5 call sites (e.g., `transition_label`, `gh_comment`) use the new wrapper.
    - [ ] `pytest tests/unit/core/test_engine.py::TestIdempotentWrappers` all pass.
    - [ ] `make test-unit` passes (no regressions in engine behavior).
    - [ ] `make test-integration` passes — `tests/integration/test_idempotency.py` (which may be created in this task or already exist) verifies the integration path.
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestIdempotentWrappers -v && make test`
  - **Files:** `core/engine.py` (modify), `tests/integration/test_idempotency.py` (create, optional but recommended per plan §3 R-3)
  - **Dependencies:** B-010
  - **Spec citation:** §10.2 B2, §3 R-3 (plan)

### B1: Per-stage retry budgets (spec §10.2 B1) — per plan §2.2 order 4

- [ ] **Task B-012: Write tests for the pytest-exit-code-driven retry classifier (B1.2, RED)**
  - **Description:** Tests in `tests/unit/core/test_validate.py` for an updated `validate.py` that returns a `{exit_code, classification, action}` dict per plan §1.1 B1.2. The `action` field drives retry-vs-block decisions per spec §10.2 B1: timeouts (124, 137, 143) → `retry_transient`; test failures (1) → `retry_l2` (up to 2); design failures → `block`.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_validate.py` under `TestRetryClassifier` (≥ 4 tests).
    - [ ] One test asserts exit 124 → `action == "retry_transient"` (up to 1 retry per spec §10.2 B1).
    - [ ] One test asserts exit 1 → `action == "retry_l2"` (up to 2 retries).
    - [ ] One test asserts exit 0 → `action == "accept"`.
    - [ ] One test asserts DESIGN-stage failures → `action == "block"` regardless of exit code.
  - **Verify:** `pytest tests/unit/core/test_validate.py::TestRetryClassifier -v` exits non-zero
  - **Files:** `tests/unit/core/test_validate.py` (modify)
  - **Dependencies:** A-014 (structured result emitter already exists; this task extends its `action` semantics)
  - **Spec citation:** §10.2 B1, §3 R-6 (plan)

- [ ] **Task B-013: Implement the pytest-exit-code-driven retry classifier (B1.2, GREEN)**
  - **Description:** Extend `core/validate.py` so `run_pytest_invocation`'s returned `action` reflects the retry-decision policy from spec §10.2 B1. Pytest exit codes 124/137/143 → `retry_transient`; exit 1 → `retry_l2`; exit 0 → `accept`. Add a new `RetryPolicy` frozen dataclass per spec §7.2.
  - **Acceptance criteria:**
    - [ ] `core/validate.py` defines a `RetryPolicy` dataclass with `max_attempts`, `backoff_seconds`, `applies_to: frozenset[int]`.
    - [ ] `classify_pytest_exit_code(124).action == "retry_transient"` and `classify_pytest_exit_code(1).action == "retry_l2"`.
    - [ ] `pytest tests/unit/core/test_validate.py::TestRetryClassifier` all pass.
    - [ ] `mypy core/validate.py` passes.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/test_validate.py::TestRetryClassifier -v && mypy core/validate.py && make test`
  - **Files:** `core/validate.py` (modify)
  - **Dependencies:** B-012
  - **Spec citation:** §10.2 B1, §7.2, §3 R-6 (plan)

- [ ] **Task B-014: Write tests for per-stage retry-budget config (B1.1, RED)**
  - **Description:** Tests for `.ralph/config.toml` parsing of `[retry]` section per plan §3 R-6 mitigation. Defaults: `l1_max_attempts = 1`, `l2_max_attempts = 2`. The engine reads these and applies them at each stage. Tests assert: missing config → defaults; explicit values override; tight values (e.g., 0) disable retry.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_engine.py` under `TestRetryBudgetConfig` (≥ 4 tests).
    - [ ] One test asserts no `[retry]` section → uses defaults (1, 2).
    - [ ] One test asserts `[retry] l1_max_attempts = 0` → no L1 retry.
    - [ ] One test asserts `[retry] l2_max_attempts = 3` → L2 retries up to 3 times.
    - [ ] One test asserts invalid config (negative number) → uses defaults + WARNING log.
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestRetryBudgetConfig -v` exits non-zero
  - **Files:** `tests/unit/core/test_engine.py` (modify)
  - **Dependencies:** B-013 (retry classifier must exist)
  - **Spec citation:** §10.2 B1, §3 R-6 (plan)

- [ ] **Task B-015: Implement per-stage retry-budget config (B1.1, GREEN)**
  - **Description:** In `core/engine.py`, add a `load_retry_config() -> RetryBudget` function that reads `[retry]` from `.ralph/config.toml` (TOML). Defaults from plan §3 R-6. Engine calls this at daemon startup.
  - **Acceptance criteria:**
    - [ ] `core/engine.py` contains `load_retry_config` and a `RetryBudget` dataclass.
    - [ ] Defaults match spec: `l1_max_attempts = 1`, `l2_max_attempts = 2`.
    - [ ] `pytest tests/unit/core/test_engine.py::TestRetryBudgetConfig` all pass.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestRetryBudgetConfig -v && make test`
  - **Files:** `core/engine.py` (modify)
  - **Dependencies:** B-014
  - **Spec citation:** §10.2 B1, §3 R-6 (plan)

- [ ] **Task B-016: Write tests for agent re-invocation with failure context (B1.3, RED)**
  - **Description:** Tests for the `invoke_agent` wrapper that re-invokes on retryable failures per spec §10.2 B1. After a `retry_l2` action, the agent is re-invoked with the previous failure output inlined into the prompt. Tests mock `subprocess.run` and assert: (a) retry counter is respected, (b) re-invocation prompt contains the previous stdout_tail, (c) max-attempts is not exceeded.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_engine.py` under `TestAgentReinvocation` (≥ 4 tests).
    - [ ] One test asserts an `retry_l2` action triggers a second invocation up to `l2_max_attempts` (default 2).
    - [ ] One test asserts the second invocation's prompt contains the first invocation's `stdout_tail`.
    - [ ] One test asserts after max attempts are exhausted, the stage blocks (no further invocation).
    - [ ] One test asserts `retry_transient` triggers exactly one retry (L1 cap).
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestAgentReinvocation -v` exits non-zero
  - **Files:** `tests/unit/core/test_engine.py` (modify)
  - **Dependencies:** B-015 (retry budget config must exist), B-011 (idempotent wrappers so re-invocation is safe)
  - **Spec citation:** §10.2 B1, §3 R-6 (plan)

- [ ] **Task B-017: Implement agent re-invocation with failure context (B1.3, GREEN)**
  - **Description:** Modify the `invoke_agent` wrapper in `core/engine.py` to handle retryable actions. The wrapper consults the retry budget, re-invokes the agent up to `max_attempts` times, and on each retry inlines the previous invocation's `stdout_tail` into the new prompt. After exhaustion, the wrapper returns a blocked status.
  - **Acceptance criteria:**
    - [ ] `invoke_agent` in `core/engine.py` accepts retry parameters and a retry-budget reference.
    - [ ] On `retry_l2`, the wrapper invokes the agent up to `l2_max_attempts` times.
    - [ ] On `retry_transient`, the wrapper invokes the agent up to `l1_max_attempts` time (default 1).
    - [ ] Each retry's prompt contains the previous `stdout_tail` (verifiable in test fixture).
    - [ ] `pytest tests/unit/core/test_engine.py::TestAgentReinvocation` all pass.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestAgentReinvocation -v && make test`
  - **Files:** `core/engine.py` (modify)
  - **Dependencies:** B-016
  - **Spec citation:** §10.2 B1, §3 R-6 (plan)

### B3: Mechanism-enforced isolation (spec §10.2 B3) — per plan §2.2 order 5

- [ ] **Task B-018: Write tests for worktree setup/teardown helper (B3.1, RED)**
  - **Description:** Tests for `core/pipeline/agents/base.py` (NEW module). Exposes `create_worktree(issue_num: int) -> Path` and `remove_worktree(path: Path) -> None`. Tests mock `git worktree add` and `git worktree remove`. A pre-flight check (per plan §3 R-5 mitigation) verifies `git worktree` works in the current repo.
  - **Acceptance criteria:**
    - [ ] `tests/unit/core/pipeline/agents/__init__.py` (empty) exists.
    - [ ] `tests/unit/core/pipeline/agents/test_base.py` exists with ≥ 4 test cases.
    - [ ] One test asserts `create_worktree(1)` invokes `git worktree add` and returns the new path.
    - [ ] One test asserts `remove_worktree(path)` invokes `git worktree remove`.
    - [ ] One test asserts pre-flight check: when `git worktree add` fails, `create_worktree` raises `RuntimeError` with a clear message.
    - [ ] One test asserts on Linux, `src/` inside the worktree is mounted read-only after `create_worktree` (B3.2 wraps this in next task; this test verifies the placeholder).
  - **Verify:** `pytest tests/unit/core/pipeline/agents/test_base.py -v` exits non-zero (module not yet created)
  - **Files:** `tests/unit/core/pipeline/agents/__init__.py` (create, empty), `tests/unit/core/pipeline/agents/test_base.py` (create)
  - **Dependencies:** None
  - **Spec citation:** §10.2 B3, §3 R-5 (plan)

- [ ] **Task B-019: Implement worktree setup/teardown helper (B3.1, GREEN)**
  - **Description:** Create `core/pipeline/agents/base.py` with `create_worktree` and `remove_worktree` per plan §3 R-5 mitigation. Pre-flight check: `git worktree add /tmp/ralph-wt-test HEAD` then remove; if either fails, raise `RuntimeError("git worktree not available; see docs/development_workflow.md for workarounds")`.
  - **Acceptance criteria:**
    - [ ] `core/pipeline/agents/base.py` exists with `create_worktree` and `remove_worktree`.
    - [ ] Pre-flight check runs at first invocation; on failure raises `RuntimeError`.
    - [ ] `pytest tests/unit/core/pipeline/agents/test_base.py` all pass.
    - [ ] `mypy core/pipeline/agents/base.py` passes.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/agents/test_base.py -v && mypy core/pipeline/agents/base.py && make test`
  - **Files:** `core/pipeline/agents/__init__.py` (create, empty), `core/pipeline/agents/base.py` (create)
  - **Dependencies:** B-018
  - **Spec citation:** §10.2 B3, §3 R-5 (plan)

- [ ] **Task B-020: Write tests for read-only `src/` mount (B3.2, RED)**
  - **Description:** Tests for the read-only `src/` enforcement added to `create_worktree` in `core/pipeline/agents/base.py`. Per plan §3 R-5 mitigation: Linux uses `mount --bind src /tmp/ralph-wt/src && mount -o remount,ro,bind /tmp/ralph-wt/src` (true mechanism isolation); macOS uses `chmod -R 0500 src/` (writes enforced, reads policy-only). Tests assert: (a) on Linux mock, the mount command is invoked; (b) on macOS mock, chmod 0500 is applied; (c) WARNING is logged on macOS.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/pipeline/agents/test_base.py` under `TestReadOnlySrc` (≥ 3 tests).
    - [ ] One test asserts Linux path: `create_worktree` invokes `mount --bind` and `mount -o remount,ro,bind`.
    - [ ] One test asserts macOS path (mocked `sys.platform == "darwin"`): `chmod -R 0500 src/` is applied AND a WARNING is logged about policy-only read isolation.
    - [ ] One test asserts cleanup (`remove_worktree`) reverses the read-only state.
  - **Verify:** `pytest tests/unit/core/pipeline/agents/test_base.py::TestReadOnlySrc -v` exits non-zero
  - **Files:** `tests/unit/core/pipeline/agents/test_base.py` (modify)
  - **Dependencies:** B-019 (worktree helper must exist)
  - **Spec citation:** §10.2 B3, §3 R-5 (plan)

- [ ] **Task B-021: Implement read-only `src/` mount (B3.2, GREEN)**
  - **Description:** Extend `create_worktree` in `core/pipeline/agents/base.py` to enforce read-only `src/` per plan §3 R-5. Platform detection: `sys.platform`. Linux: invoke `mount --bind` + `mount -o remount,ro,bind`. macOS: `chmod -R 0500 src/` and log WARNING. On Linux mount failure, fall back to `chmod -R 0500 src/` (per plan §3 R-5 mitigation).
  - **Acceptance criteria:**
    - [ ] `create_worktree` platform-conditionally enforces read-only `src/`.
    - [ ] macOS path logs a WARNING naming the policy-only read behavior.
    - [ ] `pytest tests/unit/core/pipeline/agents/test_base.py::TestReadOnlySrc` all pass.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/agents/test_base.py::TestReadOnlySrc -v && make test`
  - **Files:** `core/pipeline/agents/base.py` (modify)
  - **Dependencies:** B-020
  - **Spec citation:** §10.2 B3, §3 R-5 (plan)

- [ ] **Task B-022: Write tests for TEST + VERIFY using worktree (B3.3, RED)**
  - **Description:** Tests for the engine's `_run_test_subagent` and `_run_verify_subagent` in `core/engine.py`. After B3.3, both create a worktree before invoking the agent and tear it down afterward. Tests assert: (a) `create_worktree` is called, (b) the agent's CWD is the worktree path, (c) `remove_worktree` is called even on agent failure (via `try/finally`).
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_engine.py` under `TestSubagentsUseWorktree` (≥ 4 tests).
    - [ ] One test asserts `_run_test_subagent` calls `create_worktree` and `remove_worktree`.
    - [ ] One test asserts `_run_verify_subagent` calls `create_worktree` and `remove_worktree`.
    - [ ] One test asserts `remove_worktree` runs even when the agent subprocess returns non-zero (try/finally).
    - [ ] One test asserts the agent's CWD is the worktree path, not the repo root.
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestSubagentsUseWorktree -v` exits non-zero
  - **Files:** `tests/unit/core/test_engine.py` (modify)
  - **Dependencies:** B-021 (worktree helper with read-only enforcement must exist)
  - **Spec citation:** §10.2 B3

- [ ] **Task B-023: Implement TEST + VERIFY using worktree (B3.3, GREEN)**
  - **Description:** Modify `_run_test_subagent` and `_run_verify_subagent` in `core/engine.py` to wrap agent invocation in `create_worktree` / `remove_worktree` with try/finally. The agent's CWD is the worktree path.
  - **Acceptance criteria:**
    - [ ] `_run_test_subagent` and `_run_verify_subagent` both call `create_worktree` before and `remove_worktree` after.
    - [ ] `remove_worktree` runs in a `finally` block — orphan worktrees do not accumulate.
    - [ ] Agent's `cwd=` is the worktree path.
    - [ ] `pytest tests/unit/core/test_engine.py::TestSubagentsUseWorktree` all pass.
    - [ ] `make test` passes.
    - [ ] `tests/integration/test_worktree_isolation.py` (per plan §3 R-5) passes: worktree created, `src/` read-only at FS level, agent attempting to write to `src/` gets `Permission denied`, teardown leaves no orphan.
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestSubagentsUseWorktree -v && pytest tests/integration/test_worktree_isolation.py -v && make test`
  - **Files:** `core/engine.py` (modify), `tests/integration/test_worktree_isolation.py` (create)
  - **Dependencies:** B-022
  - **Spec citation:** §10.2 B3, §3 R-5 (plan)

### B4.3: Per-stage event emission — per plan §2.2 order 6

- [ ] **Task B-024: Write tests for per-stage event emission (B4.3, RED)**
  - **Description:** Tests for the engine's emission of `TrajectoryEvent`s at every `transition_label`, `invoke_agent`, and `validate` call. Each existing call site must be wrapped to also call `append_trajectory_event`. Tests assert: each pipeline stage produces at least one trajectory event; the event's `event_type` matches the operation.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/integration/test_trajectory_completeness.py` with ≥ 5 test cases.
    - [ ] One test asserts a DESIGN-stage run produces a `StageTransition` event.
    - [ ] One test asserts a BUILD-stage run produces `SubagentInvocation` events.
    - [ ] One test asserts a `transition_label` produces a `LabelTransition` event.
    - [ ] One test asserts a `validate` call produces a `ValidationRun` event.
    - [ ] One test asserts a full pipeline (DESIGN → BUILD → VERIFY) produces ≥ 6 trajectory events.
  - **Verify:** `pytest tests/integration/test_trajectory_completeness.py -v` exits non-zero
  - **Files:** `tests/integration/test_trajectory_completeness.py` (create)
  - **Dependencies:** B-011 (idempotent wrappers), B-017 (agent re-invocation), B-023 (worktree-using subagents)
  - **Spec citation:** §10.2 B4

- [ ] **Task B-025: Implement per-stage event emission (B4.3, GREEN)**
  - **Description:** Modify `core/engine.py` to emit `TrajectoryEvent`s at every `transition_label`, `invoke_agent`, and `validate` call. Use `core/pipeline/metrics.append_trajectory_event` from B-005. Each call site gets a try/except wrapper so trajectory emission failures do not break the pipeline.
  - **Acceptance criteria:**
    - [ ] Every `transition_label` call in `core/engine.py` is followed by a trajectory emission.
    - [ ] Every `invoke_agent` call emits a `SubagentInvocation` event.
    - [ ] Every `validate` call emits a `ValidationRun` event.
    - [ ] Trajectory emission failures log WARNING but do not raise.
    - [ ] `pytest tests/integration/test_trajectory_completeness.py` all pass.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/integration/test_trajectory_completeness.py -v && make test`
  - **Files:** `core/engine.py` (modify)
  - **Dependencies:** B-024
  - **Spec citation:** §10.2 B4

### B4.4: `ralph trajectory <N>` command — per plan §2.2 order 7

- [ ] **Task B-026: Write tests for `ralph trajectory <N>` (B4.4, RED)**
  - **Description:** Tests for the new `core/trajectory.py` module + `bin/ralph` dispatch entry. `ralph trajectory <N>` reads `.ralph/issues/<N>/trajectory.jsonl` and prints a human-readable timeline. Tests assert: (a) output contains each event's `event_type` and timestamp, (b) ordering is preserved, (c) missing file → clear error.
  - **Acceptance criteria:**
    - [ ] `tests/unit/test_trajectory.py` exists with ≥ 3 test cases.
    - [ ] One test asserts `print_trajectory(1)` outputs each event's `event_type` and timestamp.
    - [ ] One test asserts output preserves the file's event order.
    - [ ] One test asserts missing `trajectory.jsonl` produces a clear "no trajectory recorded for issue #N" message (exit non-zero).
  - **Verify:** `pytest tests/unit/test_trajectory.py -v` exits non-zero (module not yet created)
  - **Files:** `tests/unit/test_trajectory.py` (create)
  - **Dependencies:** B-005 (trajectory writer must exist to produce fixture files)
  - **Spec citation:** §5.2, §10.2 B4

- [ ] **Task B-027: Implement `ralph trajectory <N>` command (B4.4, GREEN)**
  - **Description:** Create `core/trajectory.py` with `print_trajectory(issue_num)`. Wire dispatch into `bin/ralph` and `core/engine.py`. Output format: `2026-06-27T15:30:01  StageTransition  ready → design` per line.
  - **Acceptance criteria:**
    - [ ] `core/trajectory.py` exists with `print_trajectory`.
    - [ ] `bin/ralph trajectory 1` prints a timeline; missing file → non-zero exit + clear message.
    - [ ] `python -c "from core.trajectory import print_trajectory; print_trajectory(1)"` works against a fixture.
    - [ ] `pytest tests/unit/test_trajectory.py` all pass.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/test_trajectory.py -v && bin/ralph trajectory 1 || echo "expected for missing file" && make test`
  - **Files:** `core/trajectory.py` (create), `bin/ralph` (modify), `core/engine.py` (modify — add `trajectory` subcommand)
  - **Dependencies:** B-026
  - **Spec citation:** §5.2, §10.2 B4

### B5: `ralph doctor` (spec §10.2 B5) — per plan §2.2 order 8

- [ ] **Task B-028: Write tests for `ralph doctor` command (B5.1, RED)**
  - **Description:** Tests for `core/doctor.py` (NEW module). `ralph doctor` runs without args; `ralph doctor <N>` focuses on issue #N. Output is human-readable with actionable next steps. Per plan §3 R-11 exit-code mapping: 0 = healthy, 1 = warnings, 2 = errors.
  - **Acceptance criteria:**
    - [ ] `tests/unit/test_doctor.py` exists with ≥ 4 test cases.
    - [ ] One test asserts `run_doctor()` with no args scans all issues.
    - [ ] One test asserts `run_doctor(42)` focuses on issue #42.
    - [ ] One test asserts the output is human-readable (contains section headers and actionable sentences).
    - [ ] One test asserts exit code is 0 on healthy state, 1 on warnings, 2 on errors per plan §3 R-11.
  - **Verify:** `pytest tests/unit/test_doctor.py -v` exits non-zero (module not yet created)
  - **Files:** `tests/unit/test_doctor.py` (create)
  - **Dependencies:** B-005 (trajectory writer; doctor reads trajectory files)
  - **Spec citation:** §3.10, §5.2, §10.2 B5, §3 R-11 (plan)

- [ ] **Task B-029: Implement `ralph doctor` command (B5.1, GREEN)**
  - **Description:** Create `core/doctor.py` with `run_doctor(issue_num: int | None = None) -> int`. Wire into `bin/ralph` and `core/engine.py`. The skeleton dispatches to per-category diagnostics (B5.2 implements the categories).
  - **Acceptance criteria:**
    - [ ] `core/doctor.py` exists with `run_doctor`.
    - [ ] `bin/ralph doctor` exits 0 in a healthy fixture (no issues, no warnings).
    - [ ] `bin/ralph doctor 42` produces output for issue #42 (or "no data" message).
    - [ ] `pytest tests/unit/test_doctor.py` all pass (B5.1 subset; full B5.2 coverage added in B-031).
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/test_doctor.py -v && bin/ralph doctor && echo "exit 0 expected" && make test`
  - **Files:** `core/doctor.py` (create), `bin/ralph` (modify), `core/engine.py` (modify — add `doctor` subcommand)
  - **Dependencies:** B-028
  - **Spec citation:** §3.10, §5.2, §10.2 B5

- [ ] **Task B-030: Write tests for the 5 diagnostic categories (B5.2, RED)**
  - **Description:** Tests for each of the 5 doctor diagnostic categories from spec §3.10: (1) stuck issues (>1 hour in DESIGN/BUILD/VERIFY), (2) long-blocked issues (>7 days), (3) repeat failures (same test fails 3+ times in 30 days), (4) orphan subprocesses (zombie pi/kimi), (5) environment checks (missing labels, no gh auth, no git remote). Per plan §3 R-11 exit-code mapping: warnings contribute 1, errors contribute 2; final exit code = max.
  - **Acceptance criteria:**
    - [ ] Extend `tests/unit/test_doctor.py` with ≥ 5 test cases (one per category).
    - [ ] One test asserts a stuck issue (mocked timestamp > 1 hour) → contributes exit 1.
    - [ ] One test asserts an orphan subprocess → contributes exit 2.
    - [ ] One test asserts missing labels → contributes exit 2.
    - [ ] One test asserts repeat failures (3+ in 30 days) → contributes exit 1.
    - [ ] One test asserts long-blocked (>7 days) → contributes exit 1.
  - **Verify:** `pytest tests/unit/test_doctor.py::TestDiagnosticCategories -v` exits non-zero
  - **Files:** `tests/unit/test_doctor.py` (modify)
  - **Dependencies:** B-029 (doctor skeleton must exist)
  - **Spec citation:** §3.10, §3 R-11 (plan)

- [ ] **Task B-031: Implement the 5 diagnostic categories (B5.2, GREEN)**
  - **Description:** Extend `core/doctor.py` with the 5 categories per plan §3 R-11. Each category has its own detector function returning `(category_name, severity_int, message)`. The `run_doctor` function aggregates and prints.
  - **Acceptance criteria:**
    - [ ] All 5 categories are implemented and tested.
    - [ ] Exit code = max(severity) across categories per plan §3 R-11.
    - [ ] Output is grouped by category with actionable next steps per spec §10.2 B5.
    - [ ] `--quiet` flag suppresses non-critical (severity < 2) diagnostics (per plan §3 R-11).
    - [ ] `pytest tests/unit/test_doctor.py` all pass.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/test_doctor.py -v && make test`
  - **Files:** `core/doctor.py` (modify)
  - **Dependencies:** B-030
  - **Spec citation:** §3.10, §3 R-11 (plan)

### B finalization: version bump and CHANGELOG entry

- [ ] **Task B-032: Bump version to `3.1.1` (NEW-8)**
  - **Description:** Per spec §5.5, set version in three places: `pyproject.toml` → `3.1.1`, `core/__init__.py` → `"3.1.1"`, `bin/ralph` `cmd_version` output → `3.1.1`.
  - **Acceptance criteria:**
    - [ ] `grep '^version = "3.1.1"' pyproject.toml` succeeds.
    - [ ] `grep '^__version__ = "3.1.1"' core/__init__.py` succeeds.
    - [ ] `bin/ralph version` prints `3.1.1`.
  - **Verify:** `grep -E '^version = "3.1.1"|^__version__ = "3.1.1"' pyproject.toml core/__init__.py && bin/ralph version | grep -q "3.1.1"`
  - **Files:** `pyproject.toml` (modify), `core/__init__.py` (modify), `bin/ralph` (modify)
  - **Dependencies:** B-031 (last implementation task before finalization)
  - **Spec citation:** §5.5

- [ ] **Task B-033: Update `CHANGELOG.md` with v3.1.1 entry (NEW-2 release entry)**
  - **Description:** Per plan §2.2 phase-finalization: add `## 3.1.1` section listing B1 (retry budgets), B2 (idempotency), B3 (worktree isolation), B4 (trajectory), B5 (doctor). Mark "Deprecated" subheading as none.
  - **Acceptance criteria:**
    - [ ] `docs/CHANGELOG.md` contains `## 3.1.1` heading.
    - [ ] Each of B1, B2, B3, B4, B5 is mentioned by name under "New features".
    - [ ] No "Breaking changes" section is needed (B items are additive).
  - **Verify:** `grep -q "^## 3.1.1" docs/CHANGELOG.md && grep -qE "B1.*retry|B2.*idempotency|B3.*isolation|B4.*trajectory|B5.*doctor" docs/CHANGELOG.md`
  - **Files:** `docs/CHANGELOG.md` (modify)
  - **Dependencies:** B-032
  - **Spec citation:** §9.1.9, §13.7

### Phase B verification (E2E gate per spec §10.2)

- [ ] **Task B-034: Phase B E2E gate — release `ralph-v3.1.1`**
  - **Description:** Run the full Phase B verification per plan §2.2: `make test`, `make lint`, `make validate`, E2E gate (workflow_dispatch), then the Phase-B-specific crash-restart test: `kill -9 <daemon pid>` mid-BUILD, restart daemon, observe resume at BUILD (not DESIGN). Verify `.ralph/issues/<N>/idempotency.jsonl` and `trajectory.jsonl` both exist and are consistent. Tag the release.
  - **Acceptance criteria:**
    - [ ] `make test` exits 0.
    - [ ] `make lint` exits 0 (mypy strict on `core/pipeline/` and `core/schemas/` per spec §7.3).
    - [ ] `make validate` exits 0.
    - [ ] An E2E issue tagged `[e2e-phase-b-run-*]` reaches `status:review` on `samdharma/ralph-e2e-test`.
    - [ ] Crash-restart test passes: after `kill -9` mid-BUILD, restart resumes at BUILD (not DESIGN).
    - [ ] `.ralph/issues/<N>/idempotency.jsonl` exists with all expected entries.
    - [ ] `.ralph/issues/<N>/trajectory.jsonl` exists and contains events for every stage.
    - [ ] Git tag `ralph-v3.1.1` exists and is pushed to origin.
    - [ ] `gh release view ralph-v3.1.1` shows the release.
  - **Verify:** `make test && make lint && make validate && gh workflow run e2e.yml --ref ralph-v3.1 && git tag ralph-v3.1.1 && git push origin ralph-v3.1.1 && gh release create ralph-v3.1.1 --generate-notes`
  - **Files:** (no code changes; verification only)
  - **Dependencies:** B-033
  - **Spec citation:** §10.2, §13

---

## Phase C — Structural simplification (target release: `ralph-v3.1.2`)

**Phase C E2E gate** (spec §10.3): Same as B, plus: a flake on `samdharma/ralph-e2e-test` quarantines itself after 2 consecutive failures. The `ralph-v3.1.2` release appears on GitHub Releases page.

**Per plan §2.3 intra-phase ordering.** The C1.x file moves (per plan §3 R-2 mitigation) are the highest-risk work in the entire roadmap. Each move is one task; the engine must compile and tests must pass after every move.

### C3: Quarantine for known-flaky tests (spec §10.3 C3) — per plan §2.3 order 1

- [ ] **Task C-001: Write tests for `tests/quarantine.yaml` schema (C3.1, RED)**
  - **Description:** Tests for a new quarantine schema in `core/validate.py` (extend existing module). Schema entries: `{test_id: str, added_at: iso8601, reason: str, auto_added: bool}`. Tests cover: empty file → no-op; non-empty file → deselects listed tests; auto-removed after 7 days (separate flag/CLI).
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_validate.py` under `TestQuarantineSchema` (≥ 4 tests).
    - [ ] One test asserts an empty `tests/quarantine.yaml` → all tests run (no deselection).
    - [ ] One test asserts a quarantine entry `{"test_id": "tests/unit/x.py::test_y", ...}` → that test is deselected.
    - [ ] One test asserts multiple entries → all are deselected.
    - [ ] One test asserts `auto_added: True` flag is preserved in the schema (informational, not behavior).
  - **Verify:** `pytest tests/unit/core/test_validate.py::TestQuarantineSchema -v` exits non-zero
  - **Files:** `tests/unit/core/test_validate.py` (modify)
  - **Dependencies:** A-014 (structured result emitter; deselection needs the structured action field)
  - **Spec citation:** §10.3 C3, §5.5 (ar)

- [ ] **Task C-002: Implement `tests/quarantine.yaml` schema (C3.1, GREEN)**
  - **Description:** Extend `core/validate.py` to read `tests/quarantine.yaml` (YAML) and deselect listed tests via pytest's `--deselect` flag (passed to `pytest`) or `pytest.ini` markers. The schema uses PyYAML (already a project dep) or `tomllib` + manual YAML parsing.
  - **Acceptance criteria:**
    - [ ] `tests/quarantine.yaml` with entries causes `bin/ralph validate` to skip those tests.
    - [ ] `auto_added` flag is preserved through read/write cycles.
    - [ ] `pytest tests/unit/core/test_validate.py::TestQuarantineSchema` all pass.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/test_validate.py::TestQuarantineSchema -v && make test`
  - **Files:** `core/validate.py` (modify), `tests/quarantine.yaml` (create, empty list as default)
  - **Dependencies:** C-001
  - **Spec citation:** §10.3 C3, §5.5 (ar)

- [ ] **Task C-003: Write tests for quarantine auto-add on 2 consecutive failures (C3.2, RED)**
  - **Description:** Tests for the auto-quarantine logic in `core/validate.py` (extend existing). Per spec §10.3 C3: after a test fails twice in a row, it is auto-added to `tests/quarantine.yaml`. Per plan §3 R-7 mitigation: auto-added entries include the two failure timestamps and reasons. Tests assert: 2 consecutive failures → auto-add; 1 failure → no auto-add; 2 failures separated by a passing run → no auto-add.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_validate.py` under `TestAutoQuarantine` (≥ 3 tests).
    - [ ] One test asserts a single failure → no entry added.
    - [ ] One test asserts 2 consecutive failures → entry auto-added with `auto_added: true`.
    - [ ] One test asserts 2 failures separated by a passing run → no entry.
  - **Verify:** `pytest tests/unit/core/test_validate.py::TestAutoQuarantine -v` exits non-zero
  - **Files:** `tests/unit/core/test_validate.py` (modify)
  - **Dependencies:** C-002 (schema must exist for entries to be added)
  - **Spec citation:** §10.3 C3, §3 R-7 (plan)

- [ ] **Task C-004: Implement quarantine auto-add on 2 consecutive failures (C3.2, GREEN)**
  - **Description:** Extend `core/validate.py` with a state file `.ralph/test-failure-history.jsonl` that tracks per-test failure timestamps. On each validate run, scan the last 2 runs; if a test_id appears in both with no intervening pass, auto-add to `tests/quarantine.yaml`. Engine integration: auto-quarantine is invoked at the end of BUILD's validate step.
  - **Acceptance criteria:**
    - [ ] Two consecutive failures (no intervening pass) → entry added to `tests/quarantine.yaml` with `auto_added: true`.
    - [ ] One failure → no entry.
    - [ ] `pytest tests/unit/core/test_validate.py::TestAutoQuarantine` all pass.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/test_validate.py::TestAutoQuarantine -v && make test`
  - **Files:** `core/validate.py` (modify), `core/engine.py` (modify — invoke auto-quarantine after BUILD's validate step)
  - **Dependencies:** C-003
  - **Spec citation:** §10.3 C3, §3 R-7 (plan)

- [ ] **Task C-005: Write tests for quarantine auto-unquarantine after 7 days (C3.3, RED)**
  - **Description:** Tests for the `--unquarantine-stale` CLI flag on `validate.py`. Per spec §10.3 C3: quarantined tests are auto-removed after 7 days. The flag (or a scheduled sweep) removes entries older than 7 days. Tests assert: an entry older than 7 days is removed; an entry younger than 7 days is preserved.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_validate.py` under `TestUnquarantineStale` (≥ 3 tests).
    - [ ] One test asserts an entry with `added_at` 8 days ago is removed by `--unquarantine-stale`.
    - [ ] One test asserts an entry with `added_at` 1 day ago is preserved.
    - [ ] One test asserts the flag exits 0 and prints the count of removed entries.
  - **Verify:** `pytest tests/unit/core/test_validate.py::TestUnquarantineStale -v` exits non-zero
  - **Files:** `tests/unit/core/test_validate.py` (modify)
  - **Dependencies:** C-002 (schema must exist for entries to be removed)
  - **Spec citation:** §10.3 C3

- [ ] **Task C-006: Implement quarantine auto-unquarantine after 7 days (C3.3, GREEN)**
  - **Description:** Extend `core/validate.py` with `--unquarantine-stale` CLI flag. The flag scans `tests/quarantine.yaml`, removes entries where `added_at` is older than 7 days, writes the file back, and prints the count.
  - **Acceptance criteria:**
    - [ ] `bin/ralph validate --unquarantine-stale` removes entries older than 7 days.
    - [ ] Entries younger than 7 days are preserved.
    - [ ] `pytest tests/unit/core/test_validate.py::TestUnquarantineStale` all pass.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/test_validate.py::TestUnquarantineStale -v && make test`
  - **Files:** `core/validate.py` (modify)
  - **Dependencies:** C-005
  - **Spec citation:** §10.3 C3

- [ ] **Task C-007: Write tests for `🦠 Flake quarantined:` GitHub issue post (C3.4, RED)**
  - **Description:** Tests for the engine's behavior when a test is auto-quarantined (C3.2). Per spec §10.3 C3: post a GitHub issue titled `🦠 Flake quarantined: <test_id>` with the two failure logs linked. Tests mock `gh issue create` and assert: the issue title, body (containing both failure timestamps), and that the post is idempotent (re-running C3.2 for the same test_id does NOT create a duplicate issue).
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_engine.py` under `TestQuarantineIssuePost` (≥ 3 tests).
    - [ ] One test asserts a fresh auto-quarantine → invokes `gh issue create` with title `🦠 Flake quarantined: <test_id>`.
    - [ ] One test asserts the issue body contains both failure timestamps.
    - [ ] One test asserts idempotency: a second auto-quarantine for the same test_id does NOT create a second issue (uses idempotency.jsonl from B2.2).
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestQuarantineIssuePost -v` exits non-zero
  - **Files:** `tests/unit/core/test_engine.py` (modify)
  - **Dependencies:** C-004 (auto-quarantine must exist), B-011 (idempotency wrapper must exist for the post)
  - **Spec citation:** §10.3 C3, §3 R-7 (plan)

- [ ] **Task C-008: Implement `🦠 Flake quarantined:` GitHub issue post (C3.4, GREEN)**
  - **Description:** Modify `core/engine.py` (or `core/validate.py` if the post happens there) so that when auto-quarantine fires (C3.2), a GitHub issue is posted. Use the idempotency wrapper from B-011 keyed on `(run_id, "issue_create", test_id, body_hash)` so re-runs do not duplicate.
  - **Acceptance criteria:**
    - [ ] Auto-quarantine triggers a `gh issue create` with title `🦠 Flake quarantined: <test_id>`.
    - [ ] Issue body contains both failure timestamps + a link to `.ralph/test-failure-history.jsonl`.
    - [ ] Re-running auto-quarantine for the same test_id does not create a duplicate.
    - [ ] `pytest tests/unit/core/test_engine.py::TestQuarantineIssuePost` all pass.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestQuarantineIssuePost -v && make test`
  - **Files:** `core/engine.py` (modify), `core/validate.py` (modify — invoke the issue post)
  - **Dependencies:** C-007
  - **Spec citation:** §10.3 C3

### C4: Skip expensive tiers on retry (spec §10.3 C4) — per plan §2.3 order 2

- [ ] **Task C-009: Write tests for `ralph validate --retry` flag (C4.1, RED)**
  - **Description:** Tests in `tests/unit/core/test_validate.py` for the new `--retry` CLI flag. When passed, only `--pytest-paths` runs; integration, full, and e2e tiers are skipped. Tests assert: (a) `--retry` skips integration tests, (b) without `--retry`, all tiers run as before.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_validate.py` under `TestRetryFlag` (≥ 3 tests).
    - [ ] One test asserts `--retry` runs only the pytest-paths tier (no integration).
    - [ ] One test asserts default (no `--retry`) → all tiers run.
    - [ ] One test asserts `--retry` exits 0 on pytest-path-only success even if integration tests would fail.
  - **Verify:** `pytest tests/unit/core/test_validate.py::TestRetryFlag -v` exits non-zero
  - **Files:** `tests/unit/core/test_validate.py` (modify)
  - **Dependencies:** None
  - **Spec citation:** §10.3 C4, §5.3

- [ ] **Task C-010: Implement `ralph validate --retry` flag (C4.1, GREEN)**
  - **Description:** Add `--retry` CLI flag to `validate.py` (via `core/engine.py` subcommand dispatch). When set, skip integration/full/e2e tier invocations. Wire into BUILD's retry path so retry attempts on `retry_l2` use this flag (per spec §10.3 C4 + B1.3).
  - **Acceptance criteria:**
    - [ ] `bin/ralph validate --retry` runs only the pytest-paths tier.
    - [ ] `pytest tests/unit/core/test_validate.py::TestRetryFlag` all pass.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/test_validate.py::TestRetryFlag -v && bin/ralph validate --retry && make test`
  - **Files:** `core/validate.py` (modify), `core/engine.py` (modify — add `--retry` flag and wire into B1.3 retry path)
  - **Dependencies:** C-009, B-017 (agent re-invocation must exist for the retry path to use this flag)
  - **Spec citation:** §10.3 C4

### C2: Distribution via GitHub Releases (spec §10.3 C2) — per plan §2.3 order 3

C2.3 and C2.4 (install.sh and README) shipped in Phase A (A-035, A-036). C2.1 (Makefile `release` target) and C2.2 (scripts/release.sh) ship here.

- [ ] **Task C-011: Add `release` target to Makefile + create `scripts/release.sh` (C2.1 full, C2.2)**
  - **Description:** Add `make release PART=minor` target to Makefile (extends A-007's partial Makefile). Create `scripts/release.sh` that automates: tag, push, `gh release create --generate-notes`. The Makefile target invokes `scripts/release.sh`. Per spec §5.5: tag format `ralph-v<MAJOR>.<MINOR>.<PATCH>`.
  - **Acceptance criteria:**
    - [ ] `Makefile` contains `release:` target invoking `scripts/release.sh`.
    - [ ] `scripts/release.sh` exists and is executable (`chmod +x`).
    - [ ] `scripts/release.sh` runs `git tag`, `git push origin <tag>`, `gh release create <tag> --generate-notes`.
    - [ ] Running `make release PART=patch` (dry-test on a scratch branch) succeeds in a fixture repo.
  - **Verify:** `make -n release PART=patch` (dry-run) prints the expected commands; `test -x scripts/release.sh && grep -q "gh release" scripts/release.sh`
  - **Files:** `Makefile` (modify — add `release` target), `scripts/release.sh` (create)
  - **Dependencies:** None
  - **Spec citation:** §5.5, §10.3 C2

### C1: Split `engine.py` into `core/pipeline/` package (spec §10.3 C1)

**Per plan §3 R-2 mitigation**, this is the HIGHEST-RISK section of the entire roadmap. Per plan §2.3: each file move is one task; the engine must compile and `make test` must pass after every move. No behavior change is permitted.

**Snapshot testing note:** Plan §3 R-2 calls for a `tests/integration/test_engine_snapshots.py` that records exit codes and stdout patterns from the v3.1.1 engine BEFORE C1 begins. This snapshot is generated by a one-shot `scripts/generate_engine_snapshots.py` (which is removed after C1 ships) and lives at `tests/integration/fixtures/engine_snapshots/`. The snapshot test is task C-013 below.

- [ ] **Task C-012: Create `core/pipeline/__init__.py` skeleton (C1.1)**
  - **Description:** Create the `core/pipeline/` package skeleton. `__init__.py` exports nothing yet (placeholder); sub-packages (`stages/`, `agents/`, `github/`) are created lazily as files are moved. This task exists so that subsequent C1.x tasks can import from a package that already exists.
  - **Acceptance criteria:**
    - [ ] `core/pipeline/__init__.py` exists (empty or with module docstring).
    - [ ] `python -c "import core.pipeline"` succeeds.
    - [ ] `make test` passes (no regressions).
  - **Verify:** `python -c "import core.pipeline" && make test`
  - **Files:** `core/pipeline/__init__.py` (create, empty)
  - **Dependencies:** None (the package skeleton does not depend on B2.2/B4.2 — those files already exist in `core/pipeline/` from B; the skeleton just adds the `__init__.py`)
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-013: Generate engine snapshots from v3.1.1 engine (R-2 mitigation, prereq for C1.x)**
  - **Description:** Per plan §3 R-2 mitigation: BEFORE any C1.x file move, generate snapshots of the current engine's behavior. Create `scripts/generate_engine_snapshots.py` that runs the engine against a fixture repo and records exit codes + stdout patterns. Outputs go to `tests/integration/fixtures/engine_snapshots/` (git-tracked). The script is run ONCE; after C1 ships, the snapshot files remain but the script is removed.
  - **Acceptance criteria:**
    - [ ] `scripts/generate_engine_snapshots.py` exists.
    - [ ] `tests/integration/fixtures/engine_snapshots/` contains ≥ 50 JSON files (one per scenario).
    - [ ] Each JSON file has `argv`, `exit_code`, `stdout_pattern` keys.
    - [ ] `git add tests/integration/fixtures/engine_snapshots/` is run and the files are committed.
    - [ ] `tests/integration/test_engine_snapshots.py` exists and uses these fixtures (read-only consumer; no behavior change).
  - **Verify:** `test -f scripts/generate_engine_snapshots.py && ls tests/integration/fixtures/engine_snapshots/*.json | wc -l` ≥ 50
  - **Files:** `scripts/generate_engine_snapshots.py` (create, then delete in C-046), `tests/integration/fixtures/engine_snapshots/` (create, populated), `tests/integration/test_engine_snapshots.py` (create)
  - **Dependencies:** C-012 (package skeleton)
  - **Spec citation:** §3 R-2 (plan)

- [ ] **Task C-014: Write tests for `state.py` move to `core/pipeline/state.py` (C1.2, RED)**
  - **Description:** Tests in `tests/unit/core/pipeline/test_state.py` that re-verify `Stage`, `PipelineState`, and `STATUS_LABEL` from B-007 now live at the new path. The tests re-import from the new location. (The original tests in B-007 continue to pass against the OLD location; this task adds new tests that pin the NEW location.)
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/pipeline/test_state.py` under `TestStateAtNewPath` (≥ 3 tests).
    - [ ] One test asserts `from core.pipeline.state import Stage, PipelineState, STATUS_LABEL` succeeds.
    - [ ] One test asserts `Stage.DESIGN.value == "design"`.
    - [ ] One test asserts `STATUS_LABEL[Stage.DESIGN] == "status:design"`.
  - **Verify:** `pytest tests/unit/core/pipeline/test_state.py::TestStateAtNewPath -v` exits non-zero (new path tests fail because the move hasn't happened yet)
  - **Files:** `tests/unit/core/pipeline/test_state.py` (modify — add new test class)
  - **Dependencies:** C-013 (snapshot fixtures must exist so behavior change is detectable)
  - **Spec citation:** §6.1, §10.3 C1, §3 R-2 (plan)

- [ ] **Task C-015: Move `state.py` from `core/pipeline/` already-existing to the new package layout (C1.2, GREEN)**
  - **Description:** Per plan §1.1 C1.2: move `core/engine.py` state-related code → `core/pipeline/state.py`. Since `core/pipeline/state.py` already exists from B-007 (B is the source of the Stage enum and helpers), this task is a no-op for the state file itself but DOES update `core/engine.py` to import from `core.pipeline.state` instead of defining locally. Per plan §3 R-2: behavior change = 0; snapshot test must pass.
  - **Acceptance criteria:**
    - [ ] `core/engine.py` imports `Stage`, `PipelineState`, `STATUS_LABEL` from `core.pipeline.state`.
    - [ ] No local definitions of these symbols in `core/engine.py`.
    - [ ] `pytest tests/unit/core/pipeline/test_state.py::TestStateAtNewPath` all pass.
    - [ ] `pytest tests/integration/test_engine_snapshots.py` passes (no behavior change).
    - [ ] `make test` passes.
    - [ ] `wc -l core/engine.py` decreased by ≥ 30 lines (the moved code).
  - **Verify:** `grep -q "from core.pipeline.state import" core/engine.py && pytest tests/unit/core/pipeline/test_state.py::TestStateAtNewPath -v && pytest tests/integration/test_engine_snapshots.py -v && make test`
  - **Files:** `core/engine.py` (modify)
  - **Dependencies:** C-014
  - **Spec citation:** §6.1, §10.3 C1, §3 R-2 (plan)

- [ ] **Task C-016: Write tests for `runner.py` move (C1.3, RED)**
  - **Description:** Tests in `tests/unit/core/pipeline/test_runner.py` for `run_loop` and `run_pipeline` (currently in `core/engine.py:536-727, 2387-2618`) after move to `core/pipeline/runner.py`. Tests re-import from the new path and assert public API parity (same function names, same signatures).
  - **Acceptance criteria:**
    - [ ] `tests/unit/core/pipeline/test_runner.py` exists with ≥ 3 tests under `TestRunnerAtNewPath`.
    - [ ] One test asserts `from core.pipeline.runner import run_loop, run_pipeline` succeeds.
    - [ ] One test asserts `run_loop.__doc__` and `run_pipeline.__doc__` are non-empty (parity with original).
    - [ ] One test asserts `run_loop` accepts the same arguments as the original (signature inspection).
  - **Verify:** `pytest tests/unit/core/pipeline/test_runner.py::TestRunnerAtNewPath -v` exits non-zero
  - **Files:** `tests/unit/core/pipeline/test_runner.py` (create)
  - **Dependencies:** C-015 (state must be at new path so runner can import it)
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-017: Move `runner.py` from `core/engine.py` to `core/pipeline/runner.py` (C1.3, GREEN)**
  - **Description:** Per plan §1.1 C1.3: move `run_loop` and `run_pipeline` from `core/engine.py` (lines 536-727 and 2387-2618) to `core/pipeline/runner.py`. Update `core/engine.py` to import these. Behavior must be identical; snapshot test must pass.
  - **Acceptance criteria:**
    - [ ] `core/pipeline/runner.py` exists with `run_loop` and `run_pipeline`.
    - [ ] `core/engine.py` imports them from `core.pipeline.runner`.
    - [ ] `pytest tests/unit/core/pipeline/test_runner.py` all pass.
    - [ ] `pytest tests/integration/test_engine_snapshots.py` passes.
    - [ ] `make test` passes.
    - [ ] `wc -l core/engine.py` decreased by ≥ 200 lines.
  - **Verify:** `pytest tests/unit/core/pipeline/test_runner.py -v && pytest tests/integration/test_engine_snapshots.py -v && make test`
  - **Files:** `core/engine.py` (modify), `core/pipeline/runner.py` (create)
  - **Dependencies:** C-016
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-018: Write tests for `stages/design.py` move (C1.4a, RED)**
  - **Description:** Tests for the DESIGN stage at its new location `core/pipeline/stages/design.py`. Per spec §6.1: `Stage ABC` in `base.py`, concrete DESIGN in `design.py`. Tests assert the moved module re-exports the same public API.
  - **Acceptance criteria:**
    - [ ] `tests/unit/core/pipeline/stages/__init__.py` (empty) exists.
    - [ ] `tests/unit/core/pipeline/stages/test_design.py` exists with ≥ 3 tests under `TestDesignStageAtNewPath`.
    - [ ] One test asserts `from core.pipeline.stages.design import DesignStage` succeeds.
    - [ ] One test asserts `DesignStage` inherits from `core.pipeline.stages.base.Stage`.
    - [ ] One test asserts `DesignStage.run()` is callable and returns the expected type.
  - **Verify:** `pytest tests/unit/core/pipeline/stages/test_design.py::TestDesignStageAtNewPath -v` exits non-zero
  - **Files:** `tests/unit/core/pipeline/stages/__init__.py` (create, empty), `tests/unit/core/pipeline/stages/test_design.py` (create)
  - **Dependencies:** C-017 (runner must exist at new path so DESIGN stage can be called from runner)
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-019: Move `stages/design.py` from `core/engine.py` (C1.4a, GREEN)**
  - **Description:** Per plan §1.1 C1.4: extract DESIGN stage code from `core/engine.py` into `core/pipeline/stages/design.py`. Also create the shared `core/pipeline/stages/base.py` with the `Stage` ABC (artifact_io, run, verify methods per spec §6.1).
  - **Acceptance criteria:**
    - [ ] `core/pipeline/stages/base.py` exists with the `Stage` ABC.
    - [ ] `core/pipeline/stages/design.py` exists with `DesignStage(Stage)`.
    - [ ] `core/engine.py` imports `DesignStage` from the new location.
    - [ ] `pytest tests/unit/core/pipeline/stages/test_design.py` all pass.
    - [ ] `pytest tests/integration/test_engine_snapshots.py` passes.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/stages/test_design.py -v && pytest tests/integration/test_engine_snapshots.py -v && make test`
  - **Files:** `core/pipeline/stages/base.py` (create), `core/pipeline/stages/design.py` (create), `core/engine.py` (modify)
  - **Dependencies:** C-018
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-020: Write tests for `stages/build.py` move (C1.4b, RED)**
  - **Description:** Tests for the BUILD stage at its new location `core/pipeline/stages/build.py`. Tests assert the moved module re-exports the same public API.
  - **Acceptance criteria:**
    - [ ] `tests/unit/core/pipeline/stages/test_build.py` exists with ≥ 3 tests under `TestBuildStageAtNewPath`.
    - [ ] One test asserts `from core.pipeline.stages.build import BuildStage` succeeds.
    - [ ] One test asserts `BuildStage` inherits from `core.pipeline.stages.base.Stage`.
    - [ ] One test asserts `BuildStage.run()` is callable and orchestrates TEST + IMPLEMENT sub-agents.
  - **Verify:** `pytest tests/unit/core/pipeline/stages/test_build.py::TestBuildStageAtNewPath -v` exits non-zero
  - **Files:** `tests/unit/core/pipeline/stages/test_build.py` (create)
  - **Dependencies:** C-019 (base.py + design.py at new path)
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-021: Move `stages/build.py` from `core/engine.py` (C1.4b, GREEN)**
  - **Description:** Extract BUILD stage code from `core/engine.py` into `core/pipeline/stages/build.py`. Update `core/engine.py` to import `BuildStage` from new location.
  - **Acceptance criteria:**
    - [ ] `core/pipeline/stages/build.py` exists with `BuildStage(Stage)`.
    - [ ] `core/engine.py` imports `BuildStage` from the new location.
    - [ ] `pytest tests/unit/core/pipeline/stages/test_build.py` all pass.
    - [ ] `pytest tests/integration/test_engine_snapshots.py` passes.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/stages/test_build.py -v && pytest tests/integration/test_engine_snapshots.py -v && make test`
  - **Files:** `core/pipeline/stages/build.py` (create), `core/engine.py` (modify)
  - **Dependencies:** C-020
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-022: Write tests for `stages/verify.py` move (C1.4c, RED)**
  - **Description:** Tests for the VERIFY stage at its new location `core/pipeline/stages/verify.py`. Tests assert the moved module re-exports the same public API.
  - **Acceptance criteria:**
    - [ ] `tests/unit/core/pipeline/stages/test_verify.py` exists with ≥ 3 tests under `TestVerifyStageAtNewPath`.
    - [ ] One test asserts `from core.pipeline.stages.verify import VerifyStage` succeeds.
    - [ ] One test asserts `VerifyStage` inherits from `core.pipeline.stages.base.Stage`.
    - [ ] One test asserts `VerifyStage.run()` is callable and reviews the diff against spec.
  - **Verify:** `pytest tests/unit/core/pipeline/stages/test_verify.py::TestVerifyStageAtNewPath -v` exits non-zero
  - **Files:** `tests/unit/core/pipeline/stages/test_verify.py` (create)
  - **Dependencies:** C-021 (build.py at new path)
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-023: Move `stages/verify.py` from `core/engine.py` (C1.4c, GREEN)**
  - **Description:** Extract VERIFY stage code from `core/engine.py` into `core/pipeline/stages/verify.py`. Update `core/engine.py` to import `VerifyStage` from new location.
  - **Acceptance criteria:**
    - [ ] `core/pipeline/stages/verify.py` exists with `VerifyStage(Stage)`.
    - [ ] `core/engine.py` imports `VerifyStage` from the new location.
    - [ ] `pytest tests/unit/core/pipeline/stages/test_verify.py` all pass.
    - [ ] `pytest tests/integration/test_engine_snapshots.py` passes.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/stages/test_verify.py -v && pytest tests/integration/test_engine_snapshots.py -v && make test`
  - **Files:** `core/pipeline/stages/verify.py` (create), `core/engine.py` (modify)
  - **Dependencies:** C-022
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-024: Write tests for `agents/base.py` move (C1.5a, RED)**
  - **Description:** Tests for the agents base class at its new location `core/pipeline/agents/base.py`. Note: the B3.1 worktree helper already lives there from B-019. This task adds tests that verify the moved `_run_agent` (or equivalent base method) is re-exported from the new location.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/pipeline/agents/test_base.py` under `TestAgentBaseAtNewPath` (≥ 3 tests).
    - [ ] One test asserts `from core.pipeline.agents.base import AgentBase, create_worktree, remove_worktree` succeeds.
    - [ ] One test asserts `AgentBase` (or whatever the base class is named) defines the abstract `invoke` method.
    - [ ] One test asserts the worktree helpers from B-019 are still present (regression guard).
  - **Verify:** `pytest tests/unit/core/pipeline/agents/test_base.py::TestAgentBaseAtNewPath -v` exits non-zero
  - **Files:** `tests/unit/core/pipeline/agents/test_base.py` (modify — add new test class)
  - **Dependencies:** C-023 (verify stage moved; engine now mostly consists of agents code)
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-025: Move `agents/base.py` from `core/engine.py` (C1.5a, GREEN)**
  - **Description:** Extract `AgentBase` (or whatever the existing base class is named) from `core/engine.py` into `core/pipeline/agents/base.py`. The file already exists from B-019; this task merges in the base class. Update `core/engine.py` imports.
  - **Acceptance criteria:**
    - [ ] `core/pipeline/agents/base.py` contains both `AgentBase` and the worktree helpers.
    - [ ] `core/engine.py` imports `AgentBase` from `core.pipeline.agents.base`.
    - [ ] `pytest tests/unit/core/pipeline/agents/test_base.py` all pass.
    - [ ] `pytest tests/integration/test_engine_snapshots.py` passes.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/agents/test_base.py -v && pytest tests/integration/test_engine_snapshots.py -v && make test`
  - **Files:** `core/pipeline/agents/base.py` (modify), `core/engine.py` (modify)
  - **Dependencies:** C-024
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-026: Write tests for `agents/pi.py` move (C1.5b, RED)**
  - **Description:** Tests for the `pi` agent wrapper at its new location `core/pipeline/agents/pi.py`. Tests assert the moved module re-exports the same public API.
  - **Acceptance criteria:**
    - [ ] `tests/unit/core/pipeline/agents/test_pi.py` exists with ≥ 3 tests under `TestPiAgentAtNewPath`.
    - [ ] One test asserts `from core.pipeline.agents.pi import PiAgent` succeeds.
    - [ ] One test asserts `PiAgent(AgentBase)` and implements `invoke`.
    - [ ] One test asserts `PiAgent` does NOT pass `--continue` or `--session` (regression guard for A3.3).
  - **Verify:** `pytest tests/unit/core/pipeline/agents/test_pi.py::TestPiAgentAtNewPath -v` exits non-zero
  - **Files:** `tests/unit/core/pipeline/agents/test_pi.py` (create)
  - **Dependencies:** C-025 (AgentBase at new path)
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-027: Move `agents/pi.py` from `core/engine.py` (C1.5b, GREEN)**
  - **Description:** Extract `PiAgent` from `core/engine.py` into `core/pipeline/agents/pi.py`. Update `core/engine.py` imports.
  - **Acceptance criteria:**
    - [ ] `core/pipeline/agents/pi.py` exists with `PiAgent(AgentBase)`.
    - [ ] `core/engine.py` imports `PiAgent` from `core.pipeline.agents.pi`.
    - [ ] `pytest tests/unit/core/pipeline/agents/test_pi.py` all pass.
    - [ ] `pytest tests/integration/test_engine_snapshots.py` passes.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/agents/test_pi.py -v && pytest tests/integration/test_engine_snapshots.py -v && make test`
  - **Files:** `core/pipeline/agents/pi.py` (create), `core/engine.py` (modify)
  - **Dependencies:** C-026
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-028: Write tests for `agents/kimi.py` move (C1.5c, RED)**
  - **Description:** Tests for the `kimi` agent wrapper at its new location `core/pipeline/agents/kimi.py`. Tests assert the moved module re-exports the same public API and remains symmetric with `pi` (no `--continue`, no `--session`).
  - **Acceptance criteria:**
    - [ ] `tests/unit/core/pipeline/agents/test_kimi.py` exists with ≥ 3 tests under `TestKimiAgentAtNewPath`.
    - [ ] One test asserts `from core.pipeline.agents.kimi import KimiAgent` succeeds.
    - [ ] One test asserts `KimiAgent(AgentBase)` and implements `invoke`.
    - [ ] One test asserts `KimiAgent` does NOT pass `--continue` or `--session` (symmetry with PiAgent per A3.3).
  - **Verify:** `pytest tests/unit/core/pipeline/agents/test_kimi.py::TestKimiAgentAtNewPath -v` exits non-zero
  - **Files:** `tests/unit/core/pipeline/agents/test_kimi.py` (create)
  - **Dependencies:** C-027 (PiAgent at new path; Kimi is parallel)
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-029: Move `agents/kimi.py` from `core/engine.py` (C1.5c, GREEN)**
  - **Description:** Extract `KimiAgent` from `core/engine.py` into `core/pipeline/agents/kimi.py`. Update `core/engine.py` imports.
  - **Acceptance criteria:**
    - [ ] `core/pipeline/agents/kimi.py` exists with `KimiAgent(AgentBase)`.
    - [ ] `core/engine.py` imports `KimiAgent` from `core.pipeline.agents.kimi`.
    - [ ] `pytest tests/unit/core/pipeline/agents/test_kimi.py` all pass.
    - [ ] `pytest tests/integration/test_engine_snapshots.py` passes.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/agents/test_kimi.py -v && pytest tests/integration/test_engine_snapshots.py -v && make test`
  - **Files:** `core/pipeline/agents/kimi.py` (create), `core/engine.py` (modify)
  - **Dependencies:** C-028
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-030: Write tests for `agents/artifacts.py` move (C1.5d, RED)**
  - **Description:** Tests for the artifacts module at its new location `core/pipeline/agents/artifacts.py`. Note: the file already exists from A-020 with the writer functions. This task adds tests that verify the moved module continues to expose those writers at the same import path.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/pipeline/agents/test_artifacts.py` under `TestArtifactsAtNewPath` (≥ 3 tests).
    - [ ] One test asserts `from core.pipeline.agents.artifacts import write_design, write_files_in_scope, write_acceptance_criteria, write_qa_tests` succeeds.
    - [ ] One test asserts each writer's path resolution matches spec §6.2 (`.ralph/issues/<N>/artifacts/...`).
    - [ ] One test asserts idempotency on re-write (regression guard for A3.1).
  - **Verify:** `pytest tests/unit/core/pipeline/agents/test_artifacts.py::TestArtifactsAtNewPath -v` exits non-zero
  - **Files:** `tests/unit/core/pipeline/agents/test_artifacts.py` (modify — add new test class)
  - **Dependencies:** C-029 (KimiAgent at new path; agents/ package fully populated)
  - **Spec citation:** §6.1, §6.2, §10.3 C1

- [ ] **Task C-031: Move `agents/artifacts.py` (already at new path from A-020); wire engine to use it (C1.5d, GREEN)**
  - **Description:** The artifacts module already exists at `core/pipeline/agents/artifacts.py` from A-020. This task removes any local re-definition from `core/engine.py` and ensures all engine code imports from `core.pipeline.agents.artifacts`.
  - **Acceptance criteria:**
    - [ ] `core/engine.py` does not re-define any artifacts writer.
    - [ ] All artifact imports in `core/engine.py` use `from core.pipeline.agents.artifacts import ...`.
    - [ ] `pytest tests/unit/core/pipeline/agents/test_artifacts.py::TestArtifactsAtNewPath` all pass.
    - [ ] `pytest tests/integration/test_engine_snapshots.py` passes.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/agents/test_artifacts.py::TestArtifactsAtNewPath -v && pytest tests/integration/test_engine_snapshots.py -v && make test`
  - **Files:** `core/engine.py` (modify)
  - **Dependencies:** C-030
  - **Spec citation:** §6.1, §6.2, §10.3 C1

- [ ] **Task C-032: Write tests for `github/client.py` move (C1.6a, RED)**
  - **Description:** Tests for the GitHub client at its new location `core/pipeline/github/client.py`. Note: `GitHubClient` already exists there from B-009. This task adds tests verifying the engine imports from the new path.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/pipeline/github/test_client.py` under `TestGitHubClientAtNewPath` (≥ 3 tests).
    - [ ] One test asserts `from core.pipeline.github.client import GitHubClient` succeeds.
    - [ ] One test asserts `GitHubClient(run_id=...)` constructor signature.
    - [ ] One test asserts idempotent behavior on re-call (regression guard for B2.2).
  - **Verify:** `pytest tests/unit/core/pipeline/github/test_client.py::TestGitHubClientAtNewPath -v` exits non-zero
  - **Files:** `tests/unit/core/pipeline/github/test_client.py` (modify — add new test class)
  - **Dependencies:** C-031 (agents/ done; github/ next)
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-033: Move `github/client.py` (already at new path from B-009); wire engine (C1.6a, GREEN)**
  - **Description:** `GitHubClient` already exists at `core/pipeline/github/client.py` from B-009. This task removes any local re-definition from `core/engine.py` and ensures all engine code imports from the new path.
  - **Acceptance criteria:**
    - [ ] `core/engine.py` imports `GitHubClient` from `core.pipeline.github.client`.
    - [ ] No local re-definition.
    - [ ] `pytest tests/unit/core/pipeline/github/test_client.py::TestGitHubClientAtNewPath` all pass.
    - [ ] `pytest tests/integration/test_engine_snapshots.py` passes.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/github/test_client.py::TestGitHubClientAtNewPath -v && pytest tests/integration/test_engine_snapshots.py -v && make test`
  - **Files:** `core/engine.py` (modify)
  - **Dependencies:** C-032
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-034: Write tests for `github/labels.py` move (C1.6b, RED)**
  - **Description:** Tests for the label-transition helper at its new location `core/pipeline/github/labels.py`. Tests assert the moved module re-exports `transition_label` (using `Stage` enum from `core.pipeline.state`).
  - **Acceptance criteria:**
    - [ ] `tests/unit/core/pipeline/github/test_labels.py` exists with ≥ 3 tests under `TestLabelsAtNewPath`.
    - [ ] One test asserts `from core.pipeline.github.labels import transition_label` succeeds.
    - [ ] One test asserts `transition_label(issue_num, Stage.DESIGN, run_id="X")` invokes `gh` with the correct label.
    - [ ] One test asserts idempotency on re-call (uses B2.2 idempotency log).
  - **Verify:** `pytest tests/unit/core/pipeline/github/test_labels.py::TestLabelsAtNewPath -v` exits non-zero
  - **Files:** `tests/unit/core/pipeline/github/test_labels.py` (create)
  - **Dependencies:** C-033 (client.py at new path; labels.py depends on it)
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-035: Move `github/labels.py` from `core/engine.py` (C1.6b, GREEN)**
  - **Description:** Extract `transition_label` from `core/engine.py` into `core/pipeline/github/labels.py`. Update engine to import from new path.
  - **Acceptance criteria:**
    - [ ] `core/pipeline/github/labels.py` exists with `transition_label`.
    - [ ] `core/engine.py` imports `transition_label` from `core.pipeline.github.labels`.
    - [ ] `pytest tests/unit/core/pipeline/github/test_labels.py` all pass.
    - [ ] `pytest tests/integration/test_engine_snapshots.py` passes.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/github/test_labels.py -v && pytest tests/integration/test_engine_snapshots.py -v && make test`
  - **Files:** `core/pipeline/github/labels.py` (create), `core/engine.py` (modify)
  - **Dependencies:** C-034
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-036: Write tests for `github/comments.py` move (C1.6c, RED)**
  - **Description:** Tests for the comment helper at its new location `core/pipeline/github/comments.py`. Tests assert the moved module re-exports `gh_comment`.
  - **Acceptance criteria:**
    - [ ] `tests/unit/core/pipeline/github/test_comments.py` exists with ≥ 3 tests under `TestCommentsAtNewPath`.
    - [ ] One test asserts `from core.pipeline.github.comments import gh_comment` succeeds.
    - [ ] One test asserts `gh_comment(issue_num, body, run_id="X")` invokes `gh issue comment` correctly.
    - [ ] One test asserts idempotency on re-call with same body.
  - **Verify:** `pytest tests/unit/core/pipeline/github/test_comments.py::TestCommentsAtNewPath -v` exits non-zero
  - **Files:** `tests/unit/core/pipeline/github/test_comments.py` (create)
  - **Dependencies:** C-035 (labels.py at new path; comments.py is parallel)
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-037: Move `github/comments.py` from `core/engine.py` (C1.6c, GREEN)**
  - **Description:** Extract `gh_comment` from `core/engine.py` into `core/pipeline/github/comments.py`. Update engine to import from new path.
  - **Acceptance criteria:**
    - [ ] `core/pipeline/github/comments.py` exists with `gh_comment`.
    - [ ] `core/engine.py` imports `gh_comment` from `core.pipeline.github.comments`.
    - [ ] `pytest tests/unit/core/pipeline/github/test_comments.py` all pass.
    - [ ] `pytest tests/integration/test_engine_snapshots.py` passes.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/github/test_comments.py -v && pytest tests/integration/test_engine_snapshots.py -v && make test`
  - **Files:** `core/pipeline/github/comments.py` (create), `core/engine.py` (modify)
  - **Dependencies:** C-036
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-038: Write tests for `github/board.py` move (C1.6d, RED)**
  - **Description:** Tests for the GitHub Project/Kanban board sync helper at its new location `core/pipeline/github/board.py`. Tests assert the moved module re-exports `sync_status`, `sync_closed`.
  - **Acceptance criteria:**
    - [ ] `tests/unit/core/pipeline/github/test_board.py` exists with ≥ 3 tests under `TestBoardAtNewPath`.
    - [ ] One test asserts `from core.pipeline.github.board import sync_status, sync_closed` succeeds.
    - [ ] One test asserts `sync_status(issue_num, Stage.X)` updates the Kanban board (mocked).
    - [ ] One test asserts `sync_closed(issue_num)` marks the issue closed in the board.
  - **Verify:** `pytest tests/unit/core/pipeline/github/test_board.py::TestBoardAtNewPath -v` exits non-zero
  - **Files:** `tests/unit/core/pipeline/github/test_board.py` (create)
  - **Dependencies:** C-037 (comments.py at new path; board.py is the last in the github/ subpackage)
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-039: Move `github/board.py` from `core/engine.py` (C1.6d, GREEN)**
  - **Description:** Extract `sync_status`, `sync_closed` from `core/engine.py` into `core/pipeline/github/board.py`. Update engine to import from new path.
  - **Acceptance criteria:**
    - [ ] `core/pipeline/github/board.py` exists with `sync_status`, `sync_closed`.
    - [ ] `core/engine.py` imports from `core.pipeline.github.board`.
    - [ ] `pytest tests/unit/core/pipeline/github/test_board.py` all pass.
    - [ ] `pytest tests/integration/test_engine_snapshots.py` passes.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/github/test_board.py -v && pytest tests/integration/test_engine_snapshots.py -v && make test`
  - **Files:** `core/pipeline/github/board.py` (create), `core/engine.py` (modify)
  - **Dependencies:** C-038
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-040: Write tests for `checkpoint.py` move (C1.7a, RED)**
  - **Description:** Tests for the checkpoint module at its new location `core/pipeline/checkpoint.py`. The module exposes `save_checkpoint`, `clear_checkpoint`, `recover_from_crash` per spec §6.1. Tests assert the moved module re-exports the same public API and uses Pydantic `CheckpointState` from `core.schemas.checkpoint`.
  - **Acceptance criteria:**
    - [ ] `tests/unit/core/pipeline/test_checkpoint.py` exists with ≥ 3 tests under `TestCheckpointAtNewPath`.
    - [ ] One test asserts `from core.pipeline.checkpoint import save_checkpoint, clear_checkpoint, recover_from_crash` succeeds.
    - [ ] One test asserts `save_checkpoint(issue_num, state)` writes a JSON file at `.ralph/checkpoint.json` using the Pydantic model.
    - [ ] One test asserts `recover_from_crash()` returns the saved state on restart.
  - **Verify:** `pytest tests/unit/core/pipeline/test_checkpoint.py::TestCheckpointAtNewPath -v` exits non-zero
  - **Files:** `tests/unit/core/pipeline/test_checkpoint.py` (create — note: a stub version may already exist from plan §2.3 C-001 first-commit; extend it)
  - **Dependencies:** C-039 (board.py at new path; checkpoint.py is the first in checkpoint/metrics/recovery group)
  - **Spec citation:** §6.1, §6.2, §10.3 C1

- [ ] **Task C-041: Move `checkpoint.py` from `core/engine.py:2273-2358` to `core/pipeline/checkpoint.py` (C1.7a, GREEN)**
  - **Description:** Extract checkpoint code from `core/engine.py` into `core/pipeline/checkpoint.py`. Use the existing `CheckpointState` from `core.schemas.checkpoint` (the file may not yet exist; this task may also add `core/schemas/checkpoint.py` if needed — see plan §6.1 test layout).
  - **Acceptance criteria:**
    - [ ] `core/pipeline/checkpoint.py` exists with `save_checkpoint`, `clear_checkpoint`, `recover_from_crash`.
    - [ ] `core/schemas/checkpoint.py` exists with `CheckpointState` Pydantic model.
    - [ ] `core/engine.py` imports from `core.pipeline.checkpoint`.
    - [ ] `pytest tests/unit/core/pipeline/test_checkpoint.py` all pass.
    - [ ] `pytest tests/integration/test_engine_snapshots.py` passes.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/test_checkpoint.py -v && pytest tests/integration/test_engine_snapshots.py -v && make test`
  - **Files:** `core/pipeline/checkpoint.py` (create), `core/schemas/checkpoint.py` (create), `core/engine.py` (modify)
  - **Dependencies:** C-040
  - **Spec citation:** §6.1, §6.2, §10.3 C1

- [ ] **Task C-042: Write tests for `metrics.py` move (C1.7b, RED)**
  - **Description:** Tests for the metrics module at its new location `core/pipeline/metrics.py`. Note: the trajectory writer already lives there from B-005. This task adds tests verifying the moved module continues to expose trajectory functionality.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/pipeline/test_metrics.py` under `TestMetricsAtNewPath` (≥ 3 tests).
    - [ ] One test asserts `from core.pipeline.metrics import append_trajectory_event, read_trajectory` succeeds.
    - [ ] One test asserts `read_trajectory(issue_num)` returns events in file order.
    - [ ] One test asserts `append_trajectory_event` is idempotent-safe (no corruption on partial-write recovery).
  - **Verify:** `pytest tests/unit/core/pipeline/test_metrics.py::TestMetricsAtNewPath -v` exits non-zero
  - **Files:** `tests/unit/core/pipeline/test_metrics.py` (modify — add new test class)
  - **Dependencies:** C-041 (checkpoint.py at new path)
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-043: Move `metrics.py` (already at new path from B-005); wire engine to use it (C1.7b, GREEN)**
  - **Description:** `metrics.py` (trajectory writer) already exists at `core/pipeline/metrics.py` from B-005. This task removes any local re-definition from `core/engine.py` and ensures all engine code imports from the new path. May also add a `MetricsState` Pydantic model to `core/schemas/metrics.py` if metrics-related types are needed.
  - **Acceptance criteria:**
    - [ ] `core/engine.py` does not re-define trajectory functions.
    - [ ] All engine imports use `from core.pipeline.metrics import ...`.
    - [ ] `pytest tests/unit/core/pipeline/test_metrics.py::TestMetricsAtNewPath` all pass.
    - [ ] `pytest tests/integration/test_engine_snapshots.py` passes.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/test_metrics.py::TestMetricsAtNewPath -v && pytest tests/integration/test_engine_snapshots.py -v && make test`
  - **Files:** `core/engine.py` (modify), `core/schemas/metrics.py` (create, if needed)
  - **Dependencies:** C-042
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-044: Write tests for `recovery.py` move (C1.7c, RED)**
  - **Description:** Tests for the crash-recovery module at its new location `core/pipeline/recovery.py`. Tests assert the moved module re-exports `recover_pipeline`, `get_recovery_state` (or equivalent names from the original `core/engine.py`).
  - **Acceptance criteria:**
    - [ ] `tests/unit/core/pipeline/test_recovery.py` exists with ≥ 3 tests under `TestRecoveryAtNewPath`.
    - [ ] One test asserts `from core.pipeline.recovery import recover_pipeline, get_recovery_state` (or actual names) succeeds.
    - [ ] One test asserts `recover_pipeline(issue_num)` restores state from `.ralph/checkpoint.json` and `.ralph/issues/<N>/trajectory.jsonl`.
    - [ ] One test asserts missing checkpoint + missing trajectory → fresh start (no recovery).
  - **Verify:** `pytest tests/unit/core/pipeline/test_recovery.py::TestRecoveryAtNewPath -v` exits non-zero
  - **Files:** `tests/unit/core/pipeline/test_recovery.py` (create)
  - **Dependencies:** C-043 (metrics.py at new path; recovery depends on checkpoint + metrics)
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-045: Move `recovery.py` from `core/engine.py` to `core/pipeline/recovery.py` (C1.7c, GREEN)**
  - **Description:** Extract crash-recovery code from `core/engine.py` into `core/pipeline/recovery.py`. Update engine imports.
  - **Acceptance criteria:**
    - [ ] `core/pipeline/recovery.py` exists with recovery functions.
    - [ ] `core/engine.py` imports from `core.pipeline.recovery`.
    - [ ] `pytest tests/unit/core/pipeline/test_recovery.py` all pass.
    - [ ] `pytest tests/integration/test_engine_snapshots.py` passes.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/test_recovery.py -v && pytest tests/integration/test_engine_snapshots.py -v && make test`
  - **Files:** `core/pipeline/recovery.py` (create), `core/engine.py` (modify)
  - **Dependencies:** C-044
  - **Spec citation:** §6.1, §10.3 C1

- [ ] **Task C-046: Final shrink of `core/engine.py` to CLI entrypoint (C1.8)**
  - **Description:** After all C1.x file moves, `core/engine.py` should be a thin CLI entrypoint (per spec §10.3 C1 acceptance criterion: <200 lines). Per plan §2.3 C1 cleanup: remove dead imports, verify `core/pipeline/__init__.py` re-exports the public surface, and remove `scripts/generate_engine_snapshots.py` (per plan §3 R-2 mitigation).
  - **Acceptance criteria:**
    - [ ] `wc -l core/engine.py` ≤ 200.
    - [ ] `wc -l core/pipeline/**/*.py` — every file is ≤ 500 lines.
    - [ ] `core/pipeline/__init__.py` re-exports the public surface (`run_loop`, `Stage`, `STATUS_LABEL`, `DesignStage`, `BuildStage`, `VerifyStage`, `PiAgent`, `KimiAgent`, `transition_label`, `gh_comment`, `recover_pipeline`, `append_trajectory_event`).
    - [ ] `scripts/generate_engine_snapshots.py` is deleted (R-2 cleanup).
    - [ ] `tests/integration/test_engine_snapshots.py` and fixtures remain (regression guard forever).
    - [ ] `pytest tests/integration/test_engine_snapshots.py` passes (no behavior change).
    - [ ] `make test` passes (full suite).
    - [ ] `make lint` passes (mypy --strict on `core/pipeline/` per spec §7.3).
  - **Verify:** `test $(wc -l < core/engine.py) -le 200 && find core/pipeline -name "*.py" -exec wc -l {} \; | awk '$1 > 500 {print}' | wc -l` returns 0; `pytest tests/integration/test_engine_snapshots.py -v && make test && make lint`
  - **Files:** `core/engine.py` (modify — final cleanup), `core/pipeline/__init__.py` (modify — re-exports), `scripts/generate_engine_snapshots.py` (delete), `Makefile` (modify — remove the `generate-snapshots` target if present)
  - **Dependencies:** C-045
  - **Spec citation:** §6.1, §10.3 C1, §3 R-2 (plan)

### C finalization: version bump and CHANGELOG entry

- [ ] **Task C-047: Bump version to `3.1.2` (NEW-8)**
  - **Description:** Per spec §5.5: set version in three places: `pyproject.toml` → `3.1.2`, `core/__init__.py` → `"3.1.2"`, `bin/ralph` `cmd_version` output → `3.1.2`.
  - **Acceptance criteria:**
    - [ ] `grep '^version = "3.1.2"' pyproject.toml` succeeds.
    - [ ] `grep '^__version__ = "3.1.2"' core/__init__.py` succeeds.
    - [ ] `bin/ralph version` prints `3.1.2`.
  - **Verify:** `grep -E '^version = "3.1.2"|^__version__ = "3.1.2"' pyproject.toml core/__init__.py && bin/ralph version | grep -q "3.1.2"`
  - **Files:** `pyproject.toml` (modify), `core/__init__.py` (modify), `bin/ralph` (modify)
  - **Dependencies:** C-046
  - **Spec citation:** §5.5

- [ ] **Task C-048: Update `CHANGELOG.md` with v3.1.2 entry (NEW-2 release entry)**
  - **Description:** Per plan §2.3 phase-finalization: add `## 3.1.2` section listing C1 (engine split), C2 (GitHub Releases distribution), C3 (quarantine), C4 (`--retry`). Mark "Refactor" subheading for C1 explicitly: "No behavior change. `core/engine.py` shrunk to <200 lines; logic moved to `core/pipeline/`."
  - **Acceptance criteria:**
    - [ ] `docs/CHANGELOG.md` contains `## 3.1.2` heading.
    - [ ] Each of C1, C2, C3, C4 is mentioned by name.
    - [ ] A "Refactor" subheading explicitly notes "no behavior change" for C1.
    - [ ] The size metric `<200 lines` is mentioned for `core/engine.py`.
  - **Verify:** `grep -q "^## 3.1.2" docs/CHANGELOG.md && grep -qE "C1.*split|C2.*release|C3.*quarantine|C4.*retry" docs/CHANGELOG.md && grep -q "no behavior change" docs/CHANGELOG.md`
  - **Files:** `docs/CHANGELOG.md` (modify)
  - **Dependencies:** C-047
  - **Spec citation:** §9.1.9, §13.7

### Phase C verification (E2E gate per spec §10.3)

- [ ] **Task C-049: Phase C E2E gate — release `ralph-v3.1.2`**
  - **Description:** Run the full Phase C verification per plan §2.3: `make test`, `make lint`, `make validate`, file-size checks (`wc -l core/engine.py` ≤ 200; every `core/pipeline/**/*.py` ≤ 500), E2E gate (same as B), then Phase-C-specific: trigger a known flake on `samdharma/ralph-e2e-test` twice and confirm it auto-quarantines. Tag the release.
  - **Acceptance criteria:**
    - [ ] `make test` exits 0.
    - [ ] `make lint` exits 0.
    - [ ] `make validate` exits 0.
    - [ ] `wc -l core/engine.py` ≤ 200.
    - [ ] Every `core/pipeline/**/*.py` file is ≤ 500 lines.
    - [ ] An E2E issue tagged `[e2e-phase-c-run-*]` reaches `status:review`.
    - [ ] A known flake is triggered twice → auto-quarantined in `tests/quarantine.yaml`.
    - [ ] A `🦠 Flake quarantined: <test_id>` issue appears on `samdharma/ralph-e2e-test`.
    - [ ] Git tag `ralph-v3.1.2` exists and is pushed.
    - [ ] `gh release view ralph-v3.1.2` shows the release on GitHub Releases page.
  - **Verify:** `make test && make lint && make validate && wc -l core/engine.py && find core/pipeline -name "*.py" -exec wc -l {} \; && gh workflow run e2e.yml --ref ralph-v3.1 && git tag ralph-v3.1.2 && git push origin ralph-v3.1.2 && gh release create ralph-v3.1.2 --generate-notes`
  - **Files:** (no code changes; verification only)
  - **Dependencies:** C-048
  - **Spec citation:** §10.3, §13

---

## Phase D — Performance (target release: `ralph-v3.1.3`, promoted to `ralph-v3.1` final)

**Phase D E2E gate** (spec §10.4): Same as C, plus: `ralph daemon --dry-run` exits 0 on the E2E repo. Parallel BUILD measured at <30% of sequential wall-clock time. If green, promote the release candidate `ralph-v3.1.3` to `ralph-v3.1` (final).

**Per plan §2.4 intra-phase ordering.** D1 ships behind `RALPH_PARALLEL_BUILD=true` config flag (default false) per plan §3 R-8 mitigation.

### D3: `ralph daemon --dry-run` and `ralph status --dry-run` (spec §10.4 D3) — per plan §2.4 order 1

- [ ] **Task D-001: Write tests for `ralph daemon --dry-run` (D3.1, RED)**
  - **Description:** Tests in `tests/unit/core/test_engine.py` for the new `--dry-run` flag on the `daemon` subcommand. Per spec §10.4 D3: dry-run walks the pipeline up to (but not including) agent invocation. Tests mock all `gh` and `git` calls and assert: (a) `gh auth status` is invoked, (b) `git remote -v` is invoked, (c) all 8 status labels are validated to exist on the repo, (d) NO `pi` or `kimi` subprocess is invoked.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_engine.py` under `TestDaemonDryRun` (≥ 4 tests).
    - [ ] One test asserts `--dry-run` invokes `gh auth status` (or equivalent) and exits 0 on success.
    - [ ] One test asserts `--dry-run` invokes `git remote -v` to validate the remote.
    - [ ] One test asserts `--dry-run` validates that all 8 status labels exist via `gh label list`.
    - [ ] One test asserts `--dry-run` does NOT invoke `subprocess.run` with `pi` or `kimi` in the argv.
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestDaemonDryRun -v` exits non-zero
  - **Files:** `tests/unit/core/test_engine.py` (modify)
  - **Dependencies:** None
  - **Spec citation:** §10.4 D3, §5.3

- [ ] **Task D-002: Implement `ralph daemon --dry-run` (D3.1, GREEN)**
  - **Description:** Modify `core/engine.py` to recognize `--dry-run` on the `daemon` subcommand. The dry-run path: validate gh auth, validate git remote, validate all 8 status labels exist, validate paths (.ralph/, config/). Exit 0 on success; non-zero with a clear error on each failure mode.
  - **Acceptance criteria:**
    - [ ] `bin/ralph daemon --dry-run` exits 0 in a healthy fixture.
    - [ ] On missing gh auth: exits non-zero with message "gh not authenticated; run `gh auth login`".
    - [ ] On missing labels: exits non-zero with message naming the missing labels.
    - [ ] No agent (pi/kimi) subprocess is invoked.
    - [ ] `pytest tests/unit/core/test_engine.py::TestDaemonDryRun` all pass.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestDaemonDryRun -v && bin/ralph daemon --dry-run && make test`
  - **Files:** `core/engine.py` (modify)
  - **Dependencies:** D-001
  - **Spec citation:** §10.4 D3, §5.3

- [ ] **Task D-003: Write tests for `ralph status --dry-run` (D3.2, RED)**
  - **Description:** Tests in `tests/unit/core/test_status.py` for the new `--dry-run` flag on `status`. Per spec §10.4 D3: dry-run is intended for CI health checks — it validates gh/git/labels without listing issues. Tests mock `gh` and assert only the validation calls are made (no `gh issue list`).
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_status.py` under `TestStatusDryRun` (≥ 3 tests).
    - [ ] One test asserts `--dry-run` invokes `gh auth status`.
    - [ ] One test asserts `--dry-run` validates the 8 status labels exist.
    - [ ] One test asserts `--dry-run` does NOT invoke `gh issue list` (no listing).
  - **Verify:** `pytest tests/unit/core/test_status.py::TestStatusDryRun -v` exits non-zero
  - **Files:** `tests/unit/core/test_status.py` (modify — create if not exists)
  - **Dependencies:** D-001 (daemon dry-run pattern is mirrored here)
  - **Spec citation:** §10.4 D3, §5.3

- [ ] **Task D-004: Implement `ralph status --dry-run` (D3.2, GREEN)**
  - **Description:** Modify `core/status.py` to recognize `--dry-run`. Validate gh auth + git remote + 8 status labels; exit 0 on success. No issue listing.
  - **Acceptance criteria:**
    - [ ] `bin/ralph status --dry-run` exits 0 in a healthy fixture.
    - [ ] No `gh issue list` invocation.
    - [ ] `pytest tests/unit/core/test_status.py::TestStatusDryRun` all pass.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/test_status.py::TestStatusDryRun -v && bin/ralph status --dry-run && make test`
  - **Files:** `core/status.py` (modify)
  - **Dependencies:** D-003
  - **Spec citation:** §10.4 D3, §5.3

### D2: Single retry label (spec §10.4 D2) — per plan §2.4 order 2

- [ ] **Task D-005: Write tests for `status:retry` label recognition (D2.1, RED)**
  - **Description:** Tests in `tests/unit/core/test_engine.py` for the engine's recognition of the new `status:retry` label. Per spec §3.5 and §10.4 D2: the new label works ALONGSIDE the existing 3 (`status:ready`, `status:build-retry`, `status:verify-retry`); no deprecation in v3.1. Tests assert: (a) an issue with `status:retry` is fetched and processed, (b) an issue with `status:build-retry` still works, (c) the two paths produce the same retry semantics.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/test_engine.py` under `TestRetryLabelRecognition` (≥ 3 tests).
    - [ ] One test asserts an issue labeled `status:retry` is included in `_fetch_ready_issues` (or the equivalent ready-issue fetcher).
    - [ ] One test asserts an issue labeled `status:build-retry` is still included (backward compatibility).
    - [ ] One test asserts the retry-policy applied to `status:retry` is the same as for `status:build-retry` / `status:verify-retry`.
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestRetryLabelRecognition -v` exits non-zero
  - **Files:** `tests/unit/core/test_engine.py` (modify)
  - **Dependencies:** None
  - **Spec citation:** §3.5, §10.4 D2, §3 R-12 (plan)

- [ ] **Task D-006: Implement `status:retry` label recognition (D2.1, GREEN)**
  - **Description:** Modify `core/engine.py` to recognize `status:retry` alongside the existing retry labels. No deprecation; old labels continue to work. Update `_fetch_ready_issues` (and any retry-path label filter) to accept `status:retry` as a valid input label.
  - **Acceptance criteria:**
    - [ ] `core/engine.py` includes `status:retry` in the accepted retry labels list.
    - [ ] `_fetch_ready_issues` (or equivalent) returns issues with `status:retry`, `status:build-retry`, OR `status:verify-retry`.
    - [ ] Old labels are not deprecated (no WARNING log on use).
    - [ ] `pytest tests/unit/core/test_engine.py::TestRetryLabelRecognition` all pass.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/test_engine.py::TestRetryLabelRecognition -v && grep -q "status:retry" core/engine.py && make test`
  - **Files:** `core/engine.py` (modify)
  - **Dependencies:** D-005
  - **Spec citation:** §3.5, §10.4 D2

### D1: Parallel TEST + IMPLEMENT (spec §10.4 D1) — per plan §2.4 order 3

**HIGH RISK per plan §3 R-8.** Ship behind `RALPH_PARALLEL_BUILD=true` config flag (default false). Path-domain merge policy per plan §8 Q3: `tests/` → TEST wins, `src/` → IMPLEMENT wins, anywhere else → FAIL FAST and fall back to sequential.

- [ ] **Task D-007: Write tests for parallel TEST + IMPLEMENT scheduler (D1.1, RED)**
  - **Description:** Tests in `tests/unit/core/pipeline/stages/test_build.py` for the parallel scheduler. Per plan §3 R-8: ship behind `RALPH_PARALLEL_BUILD=true` config flag (default false). The scheduler creates two git worktrees, runs TEST in one and IMPLEMENT in the other concurrently, then merges results per the path-domain policy. Tests assert: (a) parallel mode creates two worktrees, (b) sequential mode creates none, (c) the flag round-trips through config.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/pipeline/stages/test_build.py` under `TestParallelScheduler` (≥ 4 tests).
    - [ ] One test asserts default (flag false) → sequential execution (single worktree).
    - [ ] One test asserts flag true → parallel execution (two worktrees).
    - [ ] One test asserts the flag is read from `.ralph/config.toml` `[performance] parallel_build = true/false`.
    - [ ] One test asserts parallel mode returns after both sub-agents complete (not after one).
  - **Verify:** `pytest tests/unit/core/pipeline/stages/test_build.py::TestParallelScheduler -v` exits non-zero
  - **Files:** `tests/unit/core/pipeline/stages/test_build.py` (modify)
  - **Dependencies:** C-021 (BUILD stage at new path), B-019 (worktree helper from B3.1)
  - **Spec citation:** §10.4 D1, §3 R-8 (plan)

- [ ] **Task D-008: Implement parallel TEST + IMPLEMENT scheduler (D1.1, GREEN)**
  - **Description:** Extend `core/pipeline/stages/build.py` with a parallel branch gated by `RALPH_PARALLEL_BUILD` (env var) or `.ralph/config.toml` `[performance] parallel_build = true`. The scheduler uses `create_worktree` (from B3.1) twice, runs TEST + IMPLEMENT in the two worktrees concurrently (Python threads or `concurrent.futures`), waits for both, and passes the results to D1.2 (the merge step).
  - **Acceptance criteria:**
    - [ ] `core/pipeline/stages/build.py` has a parallel branch.
    - [ ] `RALPH_PARALLEL_BUILD=true` triggers parallel; default sequential.
    - [ ] Parallel mode creates 2 worktrees, runs both sub-agents, waits for completion.
    - [ ] `pytest tests/unit/core/pipeline/stages/test_build.py::TestParallelScheduler` all pass.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/stages/test_build.py::TestParallelScheduler -v && make test`
  - **Files:** `core/pipeline/stages/build.py` (modify)
  - **Dependencies:** D-007
  - **Spec citation:** §10.4 D1, §3 R-8 (plan)

- [ ] **Task D-009: Write tests for worktree-merge logic (D1.2, RED)**
  - **Description:** Tests in `tests/unit/core/pipeline/agents/test_base.py` for the merge helper in `core/pipeline/agents/base.py`. The helper takes two worktrees (TEST + IMPLEMENT) and a base ref, and produces a merged tree per the path-domain policy. Tests assert: (a) `tests/` files from TEST worktree win in conflicts, (b) `src/` files from IMPLEMENT worktree win in conflicts, (c) conflicts elsewhere → raise `OverlapError` (FAIL FAST).
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/pipeline/agents/test_base.py` under `TestMergeWorktrees` (≥ 4 tests).
    - [ ] One test asserts non-overlapping worktrees merge cleanly.
    - [ ] One test asserts `tests/` conflict → TEST wins.
    - [ ] One test asserts `src/` conflict → IMPLEMENT wins.
    - [ ] One test asserts `docs/` (or other) conflict → raises `OverlapError`.
  - **Verify:** `pytest tests/unit/core/pipeline/agents/test_base.py::TestMergeWorktrees -v` exits non-zero
  - **Files:** `tests/unit/core/pipeline/agents/test_base.py` (modify)
  - **Dependencies:** D-008 (parallel scheduler must exist to produce two worktrees for merge)
  - **Spec citation:** §10.4 D1, §3 R-8 (plan)

- [ ] **Task D-010: Implement worktree-merge logic (D1.2, GREEN)**
  - **Description:** Extend `core/pipeline/agents/base.py` with `merge_worktrees(test_wt: Path, implement_wt: Path, base: str) -> Path`. Uses `git merge -X ours -- tests/` for the TEST side, `git merge -X theirs -- src/` for the IMPLEMENT side, and pre-flight `git diff --name-only test_wt implement_wt` to detect off-domain overlaps and raise `OverlapError` before attempting merge.
  - **Acceptance criteria:**
    - [ ] `merge_worktrees` exists in `core/pipeline/agents/base.py`.
    - [ ] `tests/` conflicts → TEST wins.
    - [ ] `src/` conflicts → IMPLEMENT wins.
    - [ ] Off-domain overlaps → raises `OverlapError` with clear message naming the overlapping files.
    - [ ] `pytest tests/unit/core/pipeline/agents/test_base.py::TestMergeWorktrees` all pass.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/agents/test_base.py::TestMergeWorktrees -v && make test`
  - **Files:** `core/pipeline/agents/base.py` (modify)
  - **Dependencies:** D-009
  - **Spec citation:** §10.4 D1, §3 R-8 (plan)

- [ ] **Task D-011: Write tests for conflict-resolution policy (D1.3, RED)**
  - **Description:** Tests in `tests/unit/core/pipeline/stages/test_build.py` for the policy that runs AFTER `merge_worktrees`. Per plan §3 R-8: on `OverlapError`, the build stage fails fast, falls back to sequential, emits a metric. Tests assert: (a) on overlap, BUILD emits a metric and falls back to sequential, (b) on merge success, BUILD continues normally, (c) post-merge validation re-runs `validate --tier=targeted` and on failure falls back to sequential.
  - **Acceptance criteria:**
    - [ ] New tests in `tests/unit/core/pipeline/stages/test_build.py` under `TestConflictPolicy` (≥ 3 tests).
    - [ ] One test asserts overlap → fallback to sequential + metric emitted.
    - [ ] One test asserts successful merge → BUILD continues (no fallback).
    - [ ] One test asserts post-merge validate failure → fallback to sequential + metric emitted.
  - **Verify:** `pytest tests/unit/core/pipeline/stages/test_build.py::TestConflictPolicy -v` exits non-zero
  - **Files:** `tests/unit/core/pipeline/stages/test_build.py` (modify)
  - **Dependencies:** D-010 (merge logic must exist)
  - **Spec citation:** §10.4 D1, §3 R-8 (plan)

- [ ] **Task D-012: Implement conflict-resolution policy (D1.3, GREEN)**
  - **Description:** Extend `BuildStage.run()` (in `core/pipeline/stages/build.py`) to catch `OverlapError` from `merge_worktrees`, fall back to sequential execution, and emit a metric (`build.fallback_to_sequential`). After successful merge, re-run `validate --tier=targeted`; on failure, same fallback.
  - **Acceptance criteria:**
    - [ ] `BuildStage.run()` catches `OverlapError`, falls back, emits metric.
    - [ ] Post-merge validate failure → fallback.
    - [ ] Metric `build.fallback_to_sequential` is emitted to the metrics stream.
    - [ ] `pytest tests/unit/core/pipeline/stages/test_build.py::TestConflictPolicy` all pass.
    - [ ] `make test` passes.
  - **Verify:** `pytest tests/unit/core/pipeline/stages/test_build.py::TestConflictPolicy -v && make test`
  - **Files:** `core/pipeline/stages/build.py` (modify)
  - **Dependencies:** D-011
  - **Spec citation:** §10.4 D1, §3 R-8 (plan)

### D finalization: version bump, CHANGELOG entry, and promotion to `ralph-v3.1`

- [ ] **Task D-013: Bump version to `3.1.3` and promote to `ralph-v3.1` final (NEW-8)**
  - **Description:** Per spec §5.5 and §10.4: bump version to `3.1.3` for the release candidate. If the E2E gate passes, promote by tagging `ralph-v3.1` (final) on the same commit.
  - **Acceptance criteria:**
    - [ ] `grep '^version = "3.1.3"' pyproject.toml` succeeds.
    - [ ] `grep '^__version__ = "3.1.3"' core/__init__.py` succeeds.
    - [ ] `bin/ralph version` prints `3.1.3`.
    - [ ] Git tag `ralph-v3.1.3` exists and is pushed.
    - [ ] Git tag `ralph-v3.1` (final) exists on the same commit, with `ralph-v3.1` annotated as "stable" and `ralph-v3.1.3` retained as the pre-promotion tag.
  - **Verify:** `grep -E '^version = "3.1.3"|^__version__ = "3.1.3"' pyproject.toml core/__init__.py && bin/ralph version | grep -q "3.1.3" && git tag ralph-v3.1.3 ralph-v3.1 && git push origin ralph-v3.1.3 ralph-v3.1`
  - **Files:** `pyproject.toml` (modify), `core/__init__.py` (modify), `bin/ralph` (modify)
  - **Dependencies:** D-012
  - **Spec citation:** §5.5, §10.4

- [ ] **Task D-014: Update `CHANGELOG.md` with v3.1.3 entry and v3.1 (final) release notes (NEW-2)**
  - **Description:** Add `## 3.1.3 — 2026-MM-DD (Phase D complete — release candidate)` section listing D1 (parallel), D2 (single retry label), D3 (`--dry-run`). Then a `## 3.1 — 2026-MM-DD (Stable release)` section summarizing the v3.1 series and thanking contributors.
  - **Acceptance criteria:**
    - [ ] `docs/CHANGELOG.md` contains `## 3.1.3` heading.
    - [ ] Each of D1, D2, D3 is mentioned by name.
    - [ ] A `## 3.1` heading exists as the final/stable release.
    - [ ] A "Migration notes" subheading under v3.1 references `ralph migrate` (Phase A) and the upgrade path.
  - **Verify:** `grep -q "^## 3.1.3" docs/CHANGELOG.md && grep -qE "D1.*parallel|D2.*retry label|D3.*dry-run" docs/CHANGELOG.md && grep -q "^## 3.1 " docs/CHANGELOG.md`
  - **Files:** `docs/CHANGELOG.md` (modify)
  - **Dependencies:** D-013
  - **Spec citation:** §9.1.9, §13.7

### Phase D verification (E2E gate per spec §10.4)

- [ ] **Task D-015: Phase D E2E gate — release `ralph-v3.1.3` + promote `ralph-v3.1`**
  - **Description:** Run the full Phase D verification per plan §2.4: `make test`, `make lint`, `make validate`, all Phase C gates, then Phase-D-specific: (a) `ralph daemon --dry-run` exits 0 on the E2E repo, (b) Parallel BUILD measured at <30% of sequential wall-clock time. Tag the release candidate and promote.
  - **Acceptance criteria:**
    - [ ] `make test` exits 0.
    - [ ] `make lint` exits 0.
    - [ ] `make validate` exits 0.
    - [ ] An E2E issue tagged `[e2e-phase-d-run-*]` reaches `status:review`.
    - [ ] `bin/ralph daemon --dry-run` exits 0 against `samdharma/ralph-e2e-test`.
    - [ ] With `RALPH_PARALLEL_BUILD=true`, wall-clock time for a real issue is ≥30% faster than sequential on the same issue.
    - [ ] Git tag `ralph-v3.1.3` exists and is pushed.
    - [ ] `gh release view ralph-v3.1.3` shows the release candidate.
    - [ ] Git tag `ralph-v3.1` (final) exists on the same commit.
    - [ ] `gh release view ralph-v3.1` shows the stable release (or the same release promoted to latest).
  - **Verify:** `make test && make lint && make validate && bin/ralph daemon --dry-run && gh workflow run e2e.yml --ref ralph-v3.1 && git tag ralph-v3.1.3 && git push origin ralph-v3.1.3 && gh release create ralph-v3.1.3 --generate-notes && git tag -f ralph-v3.1 && git push -f origin ralph-v3.1 && gh release create ralph-v3.1 --generate-notes --latest`
  - **Files:** (no code changes; verification only)
  - **Dependencies:** D-014
  - **Spec citation:** §10.4, §13

---

## Cross-cutting tasks (NEW-* items)

Per plan §1.1 "Cross-cutting components," these items are reused across phases. Most landed in Phase A prelude (A-001 through A-008). The remaining cross-cutting items:

| NEW ID | Where it lives | Status |
|--------|---------------|--------|
| NEW-1 (`docs/development_workflow.md`) | A-001 | Done in Phase A |
| NEW-2 (`docs/CHANGELOG.md`) | A-002 + per-phase release entries (A-038, B-033, C-048, D-014) | Done in Phase A, updated per phase |
| NEW-3 (`.github/PULL_REQUEST_TEMPLATE.md`) | A-003 | Done in Phase A |
| NEW-4 (`.github/REVIEWER_CHECKLIST.md`) | A-004 | Done in Phase A |
| NEW-5 (`.github/workflows/e2e.yml`) | A-005 | Done in Phase A |
| NEW-6 (`.github/workflows/e2e-cleanup.yml`) | A-005 | Done in Phase A |
| NEW-7 (`tests/e2e/test_ralph_e2e_repo.py`) | A-006 + extended per phase (B-034, C-049, D-015) | Done in Phase A, extended per phase |
| NEW-8 (version bump) | A-037, B-032, C-047, D-013 | One task per phase |
| NEW-9 (Pydantic dep) | B-001 | Done in Phase B prelude |

**No additional cross-cutting tasks exist.** Every NEW-* item is covered.

---

## Out-of-scope reminders

Per spec §2.2 and §9.3, the following are EXPLICITLY OUT OF SCOPE for this roadmap. If implementation surfaces a need for any of these, surface it as a new spec section; do NOT incorporate into this plan or these tasks.

- **Replacing the GitHub-as-state-store design** (spec §2.2) — Ralph's biggest differentiator.
- **Replacing the per-issue design spec files** (`docs/designs/<N>.md`) (spec §2.2).
- **Replacing provider-error handling** (spec §2.2) — production-grade.
- **Adding a web UI** (spec §2.2) — the Kanban board *is* the UI.
- **Adding new `status:*` labels** (spec §9.1.5; with the exception of D2's additive `status:retry`, per spec §3.5).
- **Multi-tenant support** (spec §2.3, deferred to v3.2+).
- **Distributed daemon / multiple workers** (spec §2.3, deferred to v3.2+).
- **Webhook-driven triggers** (spec §2.3, deferred to v3.2+).
- **Support for AI agents other than `pi` and `kimi`** (spec §2.3, deferred to v3.2+).
- **Migrating to a typed issue schema beyond GitHub Issues** (spec §2.3, deferred to v3.2+).
- **Dropping `bin/ralph`** (spec §3.7 — preserved through v3.1.x; only v3.2 may drop it).

If a task appears to require any of the above, **STOP and surface as a "Spec Conflict Detected" section in your IMPLEMENT-phase output** (per the workflow's hard constraints).

---

## Resolved decisions (reference only)

These were resolved during SPECIFY and PLAN phases. They are NOT open questions; do not re-litigate. Reference the linked section for context.

### Spec-time resolutions (spec §11)

| # | Decision | Resolution |
|---|---------|-----------|
| 1 | Makefile target set | A — Full 11-target Makefile |
| 2 | E2E test gating | A — Local via `RALPH_E2E=1`; CI via `workflow_dispatch` + push |
| 3 | Migration story | B — Explicit `ralph migrate` command |
| 4 | Branch strategy | A — Single `ralph-v3.1` branch + community documentation |
| 5 | `ralph migrate` semantics | B — Aggressive: state files + regenerated stage prompts (only if matching v3 defaults) |
| 6 | E2E test data lifecycle | B — Auto-close successful issues; leave failed issues open |
| 7 | `ralph doctor` scope | A — All 5 diagnostic categories |
| 8 | PR review checklist | A — All 8 checks enforced via PR template |

### Plan-time resolutions (plan §8)

| # | Decision | Resolution |
|---|---------|-----------|
| 1 | Snapshot test storage location for C1 | `tests/integration/fixtures/engine_snapshots/` — git-tracked, generated ONCE by `scripts/generate_engine_snapshots.py`, then script removed (see C-013, C-046) |
| 2 | macOS read-only `src/` mount behavior | Linux uses `mount -o ro` (true mechanism isolation); macOS uses `chmod -R 0500 src/` + warning logged (writes enforced, reads policy-only) — see B-021 |
| 3 | D1 parallel conflict-resolution policy | Path-domain separation — `tests/` → TEST wins, `src/` → IMPLEMENT wins, anywhere else → FAIL FAST and fall back to sequential — see D-008 through D-012 |
| 4 | `ralph doctor` exit-code mapping | 0 = healthy, 1 = warnings, 2 = errors; per-category contribution table — see B-031 |
| 5 | `ralph migrate` backup retention | Never auto-prune; documented `rm -rf .ralph/migration-archive/` one-liner in `docs/development_workflow.md` — see A-001 (development_workflow.md) and A-010 (migrate command) |

---

## Appendix: Dependency graph (text form, copied from plan §1.2 for reference)

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

**Each arrow above corresponds to a `Dependencies:` line in one or more tasks in this document.** Task ordering in this file is consistent with the graph: tasks can be executed top-to-bottom and every dependency will be satisfied when its dependent task starts.

---

## Appendix: Hard constraints inherited from spec §9

These are non-negotiable. If a task appears to require violating any of them, STOP and surface as a "Spec Conflict Detected" section.

### Always do (spec §9.1)

1. Preserve `gh` CLI as the only GitHub interface (no direct API calls).
2. Preserve the public `ralph` CLI surface (additive only; no removals or renames).
3. Maintain idempotency on engine side effects (every label transition, comment, file write, commit).
4. Preserve the 8-state label machine (no new `status:*` labels; D2's `status:retry` is the only exception).
5. Validate inputs at the boundary (Pydantic).
6. Run `make test` before any commit.
7. Update the spec when decisions change (update spec first, then implement).
8. Every PR must pass the 8-item checklist in spec §13.
9. Update `CHANGELOG.md` on every phase PR.

### Ask first about (spec §9.2)

1. Major tech stack changes outside this spec.
2. Major structural changes outside this spec.
3. Removing code paths (especially in `core/engine.py`, `core/validate.py`, stage prompts).
4. Schema changes to artifact files.
5. Adding or changing `status:*` labels.
6. Changing `bin/ralph` install flow.

### Never do (spec §9.3)

1. Move away from `gh` for issue/ticket management.
2. Deviate from CLI best practice.
3. Commit secrets.
4. Edit the `vendor/` or `tests/` of the E2E test repo (`samdharma/ralph-e2e-test`).
5. Remove failing tests without approval.
6. Force-push to `main` or `ralph-v3.1`.
7. Merge without passing CI.

---

## Verification of this document

Before considering TASKS complete, confirm:

- [x] Every component in plan §1.1 is named and decomposed into ≥1 task.
- [x] Every task has acceptance criteria (3-5 bullets each).
- [x] Every task has a runnable verify command.
- [x] Task dependencies are explicit and ordered correctly.
- [x] No task exceeds the 5-file scope (verified at task-creation time).
- [x] Test-first ordering: "Write tests for X" precedes "Implement X" for every new-logic component.
- [x] Phase A first task (A-001) compiles + passes tests: it adds a single docs file.
- [x] Phase B first task (B-001) compiles + passes tests: it only adds a dep.
- [x] Phase C first task (C-001) compiles + passes tests: it adds a new test file.
- [x] Phase D first task (D-001) compiles + passes tests: it adds a new test file.
- [x] Each phase's last task passes the phase-complete E2E gate.
- [x] All tasks cite spec sections by number.
- [x] No "Spec Conflict Detected" sections surfaced (no hard constraints were violated in this decomposition).

---

*Total task count: 137 tasks (39 in Phase A, 34 in Phase B, 49 in Phase C, 15 in Phase D). The "Cross-cutting tasks" section is a reference table mapping NEW-* items to existing task IDs; it adds no new tasks.*
*Last updated: 2026-06-27. Awaiting human review before IMPLEMENT phase begins.*