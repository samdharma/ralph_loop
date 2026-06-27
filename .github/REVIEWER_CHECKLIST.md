# Reviewer Checklist

This file is the reviewer-facing companion to `.github/PULL_REQUEST_TEMPLATE.md`.
It explains how to verify each of the 9 items in the PR template.

For the canonical source of the checklist itself, see
[`docs/IMPROVEMENT_ROADMAP_SPEC.md` §13](../docs/IMPROVEMENT_ROADMAP_SPEC.md).

---

## 1. Spec section referenced

**What it means:** The PR description names the section of
`docs/IMPROVEMENT_ROADMAP_SPEC.md` that this PR implements (e.g., `§10.1 A3`).

**How to verify:**
- Open the linked spec section.
- Confirm the PR's changes map to the acceptance criteria listed there.
- Reject if the PR implements something not in the spec.

---

## 2. Phase declared

**What it means:** The PR description states which phase (A / B / C / D) this
PR is part of.

**How to verify:**
- Confirm the phase matches `docs/CHANGELOG.md` placement.
- A phase-complete PR should declare the phase explicitly in its title
  (e.g., `Phase A: drop pi --continue Mode B`).

---

## 3. Acceptance criteria met

**What it means:** Every acceptance criterion from spec §10 for this item is
checked off in the PR description.

**How to verify:**
- Open spec §10 for the declared phase.
- Cross-reference each acceptance-criterion bullet against the PR description's
  checklist.
- Reject if any spec criterion is unchecked or missing.

---

## 4. `make test` green

**What it means:** Unit + integration tests pass locally and in CI.

**How to verify:**
- Click the CI link in the PR description.
- Confirm the workflow run is green.
- If CI is red, request changes and link the failing job.

---

## 5. `make lint` green

**What it means:** `black`, `isort`, `flake8`, and `mypy` all pass.

**How to verify:**
- Same as #4 — click the CI link.
- Local reproduction: `make lint` in the PR branch.
- For changes to `core/pipeline/` (Phase C+), confirm `mypy --strict` passes.

---

## 6. E2E gate passed (if applicable)

**What it means:** For phase-complete PRs, an E2E run on
`samdharma/ralph-e2e-test` succeeded.

**How to verify:**
- For phase-complete PRs: the PR description MUST link to an E2E run log. Open
  it; confirm a `[e2e-phase-<X>-run-*]` issue reached `status:review`.
- For partial-phase PRs (mid-phase increments): this checkbox may be unchecked.
  Note "partial-phase, E2E deferred" in the review.

---

## 7. `CHANGELOG.md` updated

**What it means:** A new entry under "Unreleased" in `docs/CHANGELOG.md`
describes the change in plain English.

**How to verify:**
- `git diff docs/CHANGELOG.md` shows a new entry.
- The entry is user-facing (not a code-level change log).
- Release-tag PRs move the entry out of "Unreleased" into the version section.

---

## 8. Migration story documented (if applicable)

**What it means:** For schema-changing PRs, `docs/development_workflow.md` (or
another doc) describes how operators migrate their v3 projects.

**How to verify:**
- `git diff docs/development_workflow.md` shows a new section, OR
- The PR description explicitly says "no migration needed" (schema is unchanged).

---

## 9. Migration tested on a real v3 project (v3.1.0 only)

**What it means:** `tests/integration/test_v3_migration.py` passes against a
v3-format fixture repo, demonstrating that `ralph migrate` works end-to-end.

**How to verify:**
- The PR description links to the test output (CI run or local command).
- This item ONLY applies to the v3.1.0 release PR (the one that closes Phase A).
- For all later releases, remove this item from the review.

---

## Rejecting a PR

If any item fails, request changes with a specific reason linked to one of the
items above. Common reasons to reject:

- "Spec section not referenced" — PR description is missing the link.
- "Acceptance criterion unchecked" — one or more bullets in spec §10 are not
  satisfied by the diff.
- "E2E gate not run for phase-complete PR" — the PR claims to close a phase but
  has no E2E evidence.
- "CHANGELOG entry missing" — the user-facing impact is undocumented.
- "Migration untested" — the v3.1.0 PR lacks evidence that `ralph migrate`
  works against a real v3 project.

For more guidance, see [`docs/development_workflow.md`](../docs/development_workflow.md).