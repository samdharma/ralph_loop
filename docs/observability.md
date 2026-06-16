# Ralph v3 — Loop Observability Guide

This document shows how to observe the Ralph daemon while it is running, without
modifying the core build loop.  All approaches below are **read-only** (or use
external wrapping) so they cannot break the pipeline.

---

## 1. What Ralph already exposes

Ralph is designed to be observable through three native channels:

| Channel | Source | What you see |
|---------|--------|--------------|
| **GitHub labels** | `gh issue edit --add-label status:*` | Real-time pipeline stage on the Kanban board |
| **Metrics log** | `logs/ralph_metrics.jsonl` | Structured JSONL events from the loop |
| **Checkpoint file** | `.ralph/checkpoint.json` | Currently active issue + stage |
| **PID file** | `/tmp/ralph_daemon_<project>.pid` | Whether the daemon process is alive |
| **Stdout/stderr** | `ralph daemon` terminal output | Human-readable progress, agent output, errors |

### Native CLI commands

```bash
# Dashboard: PID, active issue, recent metrics
ralph status

# Periodic summary: issues processed, pass/fail, recent events
ralph report
ralph report --period=week

# Watch the metrics log directly
tail -f logs/ralph_metrics.jsonl | jq .
```

### Metrics events

`core/engine.py` writes the following events to `logs/ralph_metrics.jsonl`:

- `daemon_start` / `daemon_stop` / `daemon_idle`
- `pipeline_start` / `pipeline_complete` (with `result=review|blocked|closed`)
- `stage_start` / `stage_complete` (with `stage=design|build|verify`)
- `subagent_start` / `subagent_complete` (with `subagent=test|implement|verify`)
- `agent_invoke` (with `agent=pi|kimi`)
- `crash_recovery`
- `daemon_error`

Example:

```json
{"timestamp":"2026-06-14T10:30:00+00:00","event":"pipeline_start","issue":"31"}
{"timestamp":"2026-06-14T10:32:10+00:00","event":"stage_complete","issue":"31","stage":"design"}
{"timestamp":"2026-06-14T10:36:05+00:00","event":"pipeline_complete","issue":"31","result":"review"}
```

---

## 2. Live loop dashboard — `scripts/ralph-watch.py`

A non-intrusive watcher is included at `scripts/ralph-watch.py`.  It combines the
local state files with live GitHub label counts so you can see what Ralph is
doing right now.

### Usage

```bash
# From the project root
./scripts/ralph-watch.py

# Live refresh every 5 seconds
./scripts/ralph-watch.py --watch

# Customize refresh and number of metrics events
./scripts/ralph-watch.py --watch --interval 2 --metrics 20
```

### What it shows

```text
============================================================
Ralph v3 — Loop Observability
Project: /Users/you/project
============================================================

── Daemon ──
  Running (PID 12345)

── Active Issue (local checkpoint) ──
  Issue:       #31
  Stage:       build
  Started:     2026-06-14 10:34:56 UTC
  Pre-commit:  a1b2c3d4
  GH labels:   status:build, type:task
  GH state:    OPEN

── GitHub Issue Pipeline ──
  ready     :   2
  design    :   1
  build     :   0
  verify    :   0
  review    :   3
  blocked   :   1

── Recent Metrics (last 10) ──
  2026-06-14 10:34:00  stage_start          issue=31 stage=build
  ...
```

The script only reads `logs/ralph_metrics.jsonl`, `.ralph/checkpoint.json`, the
PID file, and runs `gh issue list` / `gh issue view`.  It never writes to the
repo or to GitHub.

---

## 3. Extracting status from GitHub (`gh`)

Because Ralph uses GitHub labels as its state machine, the GitHub board is the
system-of-record for loop progress.  You can query it directly with the GitHub
CLI.

### Count issues by pipeline stage

```bash
for status in ready design build verify review blocked; do
  count=$(gh issue list --label "status:$status" --state open --json number --jq 'length')
  echo "status:$status -> $count"
done
```

### Watch the active issue

If you know the active issue number (from `ralph status` or the checkpoint),
view its labels and recent comments:

```bash
ISSUE=31
gh issue view "$ISSUE" --json number,title,labels,state,comments,updatedAt
```

### List all open issues with their status labels

```bash
gh issue list --state open \
  --json number,title,labels \
  --jq '.[] | {number, title, status: [.labels[].name | select(startswith("status:"))][0]}'
```

### Use GitHub Projects as a Kanban board

Create a GitHub Project with these columns mapped to labels:

| Column | Label |
|--------|-------|
| Ready | `status:ready` |
| In Design | `status:design` |
| In Build | `status:build` |
| In Verify | `status:verify` |
| Review | `status:review` |
| Blocked | `status:blocked` |

Ralph updates the labels automatically, so cards move between columns in real
time.

---

## 4. Capturing the daemon’s terminal output

Agent output (`pi`/`kimi`) is streamed directly to stdout and is **not** written
to the metrics log.  To keep a persistent log without changing Ralph, redirect
the daemon output when you start it:

```bash
# Foreground with tee
ralph daemon 2>&1 | tee -a logs/ralph_daemon.log

# Background with nohup
nohup ralph daemon >> logs/ralph_daemon.log 2>&1 &

# Then tail the log
tail -f logs/ralph_daemon.log
```

If you want log rotation, wrap the daemon in a small shell script:

```bash
# scripts/ralph-daemon-logged.sh
#!/usr/bin/env bash
set -euo pipefail
mkdir -p logs
exec ralph daemon "$@" 2>&1 | tee -a "logs/ralph_daemon.log"
```

---

## 5. Integrating with external observability tools

Because the metrics log is line-delimited JSON, you can forward it to any
log/metrics system without touching the engine.

### Examples

```bash
# Pretty-print events with jq
cat logs/ralph_metrics.jsonl | jq -c 'select(.event == "pipeline_complete")'

# Count completed pipelines per day
jq -r 'select(.event == "pipeline_complete") | .timestamp[:10]' \
  logs/ralph_metrics.jsonl | sort | uniq -c

# Alert when a pipeline is blocked
jq -c 'select(.event == "pipeline_complete" and .result == "blocked")' \
  logs/ralph_metrics.jsonl
```

You can also write a small cron job or service that periodically:

1. Reads `logs/ralph_metrics.jsonl`.
2. Queries `gh issue list --label status:blocked`.
3. Sends a Slack/Discord notification or writes to Prometheus/Loki.

---

## 6. Summary of recommended workflow

1. **Start the daemon** and capture its output:
   ```bash
   nohup ralph daemon >> logs/ralph_daemon.log 2>&1 &
   ```

2. **Watch the live dashboard** in another terminal:
   ```bash
   ./scripts/ralph-watch.py --watch
   ```

3. **Glance at the GitHub Project board** for high-level pipeline state.

4. **Run reports** when you want a summary:
   ```bash
   ralph report
   ralph report --period=week
   ```

5. **Parse `logs/ralph_metrics.jsonl`** for automated alerting or custom
dashboards.

None of these steps require changes to `core/engine.py`, `bin/ralph`, or the
core modules — they are purely observational.
