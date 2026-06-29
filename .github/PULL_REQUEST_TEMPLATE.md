<!-- Ralph v3.1 PR template — see docs/IMPROVEMENT_ROADMAP_SPEC.md §13 for full checklist -->

## Summary

<!-- One- or two-sentence description of what this PR changes and why. -->

## Spec section referenced

<!-- Link to the section of docs/IMPROVEMENT_ROADMAP_SPEC.md this PR implements. -->

## Phase

<!-- Declare which phase (A / B / C / D) this PR is part of. -->

## Acceptance criteria

<!-- Check off every acceptance criterion from spec §10 for this item. -->

- [ ]

## PR review checklist (spec §13)

<!-- Reviewers verify each item. See .github/REVIEWER_CHECKLIST.md for guidance. -->

- [ ] **1. Spec section referenced** — PR description links to the relevant section of `docs/IMPROVEMENT_ROADMAP_SPEC.md`.
- [ ] **2. Phase declared** — PR description names the phase (A/B/C/D).
- [ ] **3. Acceptance criteria met** — Every bullet from spec §10 for this item is checked off.
- [ ] **4. `make test` green** — Unit + integration tests pass locally. CI link attached.
- [ ] **5. `make lint` green** — `black`, `isort`, `flake8`, `mypy` all pass. CI link attached.
- [ ] **6. E2E gate passed (if applicable)** — For phase-complete PRs: link to a successful E2E run on `samdharma/ralph-e2e-test`. For partial-phase PRs: N/A.
- [ ] **7. `CHANGELOG.md` updated** — New entry under "Unreleased" describing the change in plain English.
- [ ] **8. Migration story documented (if applicable)** — For schema-changing PRs: section in `docs/development_workflow.md` describes the migration path. Otherwise: "no migration needed."

## Phase A only (spec §13.9)

<!-- This item applies ONLY to PRs that close Phase A (the v3.1.0 release). Remove for B/C/D PRs. -->

- [ ] **9. Migration tested on a real v3 project** — `tests/integration/test_v3_migration.py` passes against a v3-format fixture repo. Test output linked in the PR description.

## How to verify locally

<!-- Commands the reviewer should run before approving. -->

```bash
make test
make lint
make validate
```

## Linked issues

<!-- Use `Closes #N` or `Refs #N` to link GitHub issues. -->