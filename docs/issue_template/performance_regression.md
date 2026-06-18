---
name: 🐌 Performance Regression
about: Report slow execution, high memory usage, or degraded throughput
labels: performance, triage
---

<!--
Template: docs/issue_template/performance_regression.md
References:
- docs/observability.md
- docs/getting_started.md
-->

## Summary

What is slow or resource-heavy? How was it discovered?

## Reproduction Steps

1. Step one
2. Step two
3. Measure with: (command/tool used)

## Expected Performance

What performance did you expect? Include numbers if possible.

## Actual Performance

What performance did you observe? Include numbers, percent change, or latency/memory figures.

```text
# paste benchmark output here
```

## Environment

- **OS:**
- **Python version:**
- **Ralph version/commit:**
- **Repository size:** (number of files, lines of code)
- **Hardware profile:** (CPU, RAM, disk type)

## Metrics / Profiles

Attach or link to:

- `logs/ralph_metrics.jsonl` excerpts
- CPU/memory profiles
- Flame graphs
- Before/after comparisons

## References

- docs/observability.md
- #<related-issue-number>
