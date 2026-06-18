---
name: 🐛 Bug Report
about: Report a defect or unexpected behavior
labels: bug, triage
---

<!--
Template: docs/issue_template/bug_report.md
References:
- docs/getting_started.md
- docs/observability.md
- docs/system_test.md
- docs/v3-redesign.md
-->

## Summary

One-sentence description of the bug.

Example: `engine: crash when test map contains a deleted source file`

## Steps to Reproduce

1. Step one
2. Step two
3. Step three

Provide the exact commands, inputs, or UI interactions needed to trigger the bug.

## Expected Behavior

What you expected to happen.

## Actual Behavior

What actually happened. Include error messages, stack traces, or unexpected output.

## Environment

- **OS:** (e.g., macOS 14, Ubuntu 22.04)
- **Python version:** (e.g., 3.11.4)
- **Ralph version/commit:** (e.g., `ralph --version` output or commit SHA)
- **Project layout:** (monorepo, single package, etc.)

## Logs / Evidence

Paste relevant output, screenshots, or excerpts from `logs/ralph_metrics.jsonl`.

```text
# paste logs here
```

## Severity

- [ ] Critical — crash, data loss, or security issue
- [ ] Major — core feature is broken
- [ ] Minor — feature works but has rough edges
- [ ] Low — cosmetic issue

## Additional Context

Any workarounds, related issues, or recent changes that might be relevant.

<!--
Before submitting:
- Check existing issues for duplicates.
- Include enough detail that someone else can reproduce the bug.
-->
