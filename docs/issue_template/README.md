# Issue Templates

This folder contains templates for creating well-structured Issues in the Ralph project.
Each template is tailored to a specific workload type. Pick the one that matches the work you are describing.

## Available Templates

| Template | Use When |
|---|---|
| [`bug_report.md`](./bug_report.md) | Something is broken, crashing, or behaving unexpectedly. |
| [`feature_request.md`](./feature_request.md) | You want to propose a new capability or improvement. |
| [`task.md`](./task.md) | Technical work that is neither a bug nor a feature (refactor, spike, cleanup, config change). |
| [`performance_regression.md`](./performance_regression.md) | The system is slower, uses more memory, or degrades under load. |
| [`docs_request.md`](./docs_request.md) | Documentation is missing, wrong, or needs clarification. |

## Quick References

For more detailed descriptions of project concepts, see:

- [`docs/getting_started.md`](../getting_started.md) — Project overview, setup, and first steps.
- [`docs/observability.md`](../observability.md) — Metrics, logging, and debugging guidance.
- [`docs/system_test.md`](../system_test.md) — How system tests are organized and run.
- [`docs/v3-redesign.md`](../v3-redesign.md) — High-level redesign notes and architecture decisions.

## Writing a Good Issue

1. **Use a specific title.** Prefer `area: short description` (e.g., `engine: test map cache returns stale entries`).
2. **Fill every required section.** Empty sections slow down triage.
3. **Provide reproduction steps for bugs.** If it cannot be reproduced, it usually cannot be fixed.
4. **Include environment details.** Ralph runs across different Python versions, OSs, and project layouts.
5. **Link related issues/PRs.** Use `#<number>` so the timeline stays connected.
6. **Attach logs or screenshots.** Console output and `logs/ralph_metrics.jsonl` excerpts are often decisive.
