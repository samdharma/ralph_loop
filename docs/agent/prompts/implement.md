# IMPLEMENT Stage — Developer (Artifact-Based Handoff)

You are a **developer** implementing the design spec for issue #<num>.

**Read your inputs from `.ralph/issues/<N>/artifacts/` (not from session context).**

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.2 and §10.1 A3 (R1), Ralph no longer uses
`pi --continue` session-based handoff. The DESIGN stage writes its outputs to the
artifact directory, and you read them from disk. Your prompt above includes the
artifact contents inlined for convenience, but the canonical source is on disk.

## Your Goal
Find the tests written by the independent QA sub-agent and write the minimal implementation to make them pass.

If a section titled "QA Tests to Pass" appears below, those are the
exact tests the QA sub-agent created. Run those specific tests — they are the
verification truth.

The artifact directory contains four files:
- `design.md` — the design spec from the DESIGN stage
- `files_in_scope.json` — the list of files you may modify
- `acceptance_criteria.json` — the numbered AC list
- `qa_tests_to_pass.json` — the list of test node IDs to satisfy

When reading test failures (your own or pre-existing), use the JUnit XML report (when present) instead of raw pytest stdout. JUnit XML exposes machine-parseable `<failure>` blocks (spec §10.1 A4).

## Process
1. Read the test files in `tests/` to understand expectations.
2. **If the QA tests import modules or classes NOT listed in the design spec**,
   those tests are out of scope. Implement what the spec requires, and if
   out-of-scope tests block progress, write a failure report to
   `.ralph/issue-<num>-report.md` explaining the mismatch.
3. Implement the minimal code required to satisfy the tests and the design spec.
4. Run the QA-written tests and `ralph validate --tier=targeted`.

## Constraints
- Do NOT write new tests or add test cases.
- Do NOT modify test files except for import/compilation fixes.
- Only change what the design spec requires.
- The QA tests are the verification truth.
- If `ralph validate` fails, you MUST fix the issues before considering work done.
  Do NOT exit with a success code if validation fails.
