# Ralph v3 — Observability

Ralph is observable by default. Every pipeline state change is visible through
three channels: the Kanban board, `ralph status`, and structured metrics.

---

## Kanban Board

The primary dashboard. When `ticket.project` is configured, every label transition
moves the card between columns in real time. No CLI tailing needed.

If the project is not configured, labels still update — the board column just won't
change automatically. See [Getting Started](getting_started.md) for setup.

---

## `ralph status`

```bash
ralph status
```

Shows:
- Daemon PID and running state
- Currently active issue, stage, and start time
- Recent metrics events (last 10)

---

## Metrics Log

Structured JSONL at `logs/ralph_metrics.jsonl`:

| Event | Fields | When |
|-------|--------|------|
| `daemon_start` / `daemon_stop` / `daemon_idle` | — | Lifecycle |
| `pipeline_start` | `issue`, `agent`, `resume_stage` | Issue enters pipeline |
| `pipeline_complete` | `issue`, `result` (`review`/`blocked`/`closed`) | Pipeline exits |
| `stage_start` / `stage_complete` | `issue`, `stage` (`design`/`build`/`verify`) | Per stage |
| `subagent_start` / `subagent_complete` | `issue`, `subagent` (`test`/`implement`/`verify`), `mode` (`A`/`B`) | Per sub-agent |
| `agent_invoke` | `issue`, `agent` (`pi`/`kimi`) | Agent invocation |
| `crash_recovery` | `issue`, `stage` | Restart after crash |
| `daemon_error` | `error` | Unhandled exception |
| `provider_rate_limit_pause` | `issue`, `agents` | All agents rate-limited, pausing 15 min |
| `agent_fallback` | `issue`, `from_agent`, `to_agent`, `reason` | Agent failed, fell back to alternate |
| `provider_exhausted` | `agent`, `issue_url` | All agents exhausted (quota/rate-limit) |

Example:

```json
{"timestamp":"2026-06-14T10:30:00+00:00","event":"pipeline_start","issue":"31","resume_stage":""}
{"timestamp":"2026-06-14T10:32:10+00:00","event":"stage_complete","issue":"31","stage":"design"}
{"timestamp":"2026-06-14T10:36:05+00:00","event":"pipeline_complete","issue":"31","result":"review"}
```

---

## Querying with `gh`

Because labels are the state machine, you can query pipeline state directly:

```bash
# Count issues by stage
for status in ready design build verify review blocked; do
  count=$(gh issue list --label "status:$status" --state open --json number --jq 'length')
  echo "status:$status → $count"
done

# View active issue with labels and comments
gh issue view 31 --json number,title,labels,state,comments

# List all open issues with status labels
gh issue list --state open --json number,title,labels \
  --jq '.[] | {number, title, status: [.labels[].name | select(startswith("status:"))][0]}'
```

---

## Daemon Output

Agent output is streamed to stdout. Capture it for a persistent log:

```bash
# Background with log
nohup ralph daemon >> logs/ralph_daemon.log 2>&1 &

# Tail live
tail -f logs/ralph_daemon.log
```

---

## External Tools

The metrics log is line-delimited JSON — forward it to any log system:

```bash
# Count completed pipelines per day
jq -r 'select(.event == "pipeline_complete") | .timestamp[:10]' \
  logs/ralph_metrics.jsonl | sort | uniq -c

# Alert on blocked pipelines
jq -c 'select(.event == "pipeline_complete" and .result == "blocked")' \
  logs/ralph_metrics.jsonl

# Find issues that were retried
jq -c 'select(.event == "pipeline_start" and .resume_stage != "")' \
  logs/ralph_metrics.jsonl
```

---

## `ralph report`

```bash
ralph report                 # daily summary
ralph report --period=week   # weekly summary
```

Generates a summary from metrics + GitHub issue history: issues processed,
pass/fail rates, blocked issues, retries.

*Last updated: 2026-06-21. Provider error metrics added (rate_limit_pause, agent_fallback, provider_exhausted).*
