#!/usr/bin/env python3
"""
Ralph v3 — Report Generator

Generates daily/weekly summaries from ralph_metrics.jsonl + gh issue history.

Usage:
    ralph report              # Show summary to stdout
    ralph report --period=day # Daily summary (default)
    ralph report --period=week # Weekly summary
"""

import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))
METRICS_FILE = PROJECT_ROOT / "logs" / "ralph_metrics.jsonl"


def load_metrics(since: datetime) -> list[dict]:
    """Load all metrics entries since the given timestamp."""
    if not METRICS_FILE.exists():
        return []
    entries = []
    for line in METRICS_FILE.read_text(encoding="utf-8").strip().splitlines():
        if not line.strip():
            continue
        try:
            e = json.loads(line)
            ts = e.get("timestamp", "")
            if ts:
                dt = datetime.fromisoformat(ts)
                if dt >= since:
                    entries.append(e)
        except json.JSONDecodeError:
            pass
    return entries


def get_gh_issues_since(since: datetime) -> list[dict]:
    """Fetch issues updated since the given time via gh CLI."""
    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--state",
                "all",
                "--search",
                f"updated:>={since.strftime('%Y-%m-%d')}",
                "--json",
                "number,title,state,labels",
                "--limit",
                "50",
            ],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass
    return []


def summarize(entries: list[dict], issues: list[dict], period: str):
    """Print a summary report."""
    print("=" * 60)
    print(f"Ralph v3 — {period.capitalize()} Report")
    print(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)
    print()

    # ── Pipeline stats from metrics ──
    pipeline_starts = [e for e in entries if e["event"] == "pipeline_start"]
    pipeline_completes = [e for e in entries if e["event"] == "pipeline_complete"]
    successes = [e for e in pipeline_completes if e.get("result") == "review"]
    failures = [e for e in pipeline_completes if e.get("result") != "review"]
    errors = [e for e in entries if e["event"] == "daemon_error"]

    print("── Pipeline Activity ──")
    print(f"  Issues processed: {len(pipeline_starts)}")
    print(f"  Passed → review:  {len(successes)}")
    print(f"  Failed/blocked:   {len(failures)}")
    if errors:
        print(f"  Daemon errors:    {len(errors)}")
    print()

    # ── Issue state from GitHub ──
    if issues:
        print("── Issue Summary ──")
        by_state = Counter(i["state"] for i in issues)
        for state, count in sorted(by_state.items()):
            state_display = "🔴 Open" if state == "OPEN" else "🟢 Closed"
            print(f"  {state_display}: {count}")
        print()

    # ── Recent timeline ──
    print("── Recent Events ──")
    for e in entries[-20:]:
        ts = e.get("timestamp", "?")[:19].replace("T", " ")
        event = e.get("event", "?")
        issue = e.get("issue", "")
        result = e.get("result", "")
        stage = e.get("stage", "")

        line = f"  {ts}  {event:20s}"
        if issue:
            line += f"  #{issue}"
        if stage:
            line += f"  [{stage}]"
        if result:
            line += f"  → {result}"
        print(line)

    print()
    print("=" * 60)


def main() -> int:
    period = "day"
    args = sys.argv[1:]
    for a in args:
        if a.startswith("--period="):
            period = a.split("=", 1)[1]

    # Calculate time window
    now = datetime.now(timezone.utc)
    if period == "week":
        since = now - timedelta(days=7)
    elif period == "month":
        since = now - timedelta(days=30)
    else:
        since = now - timedelta(days=1)

    entries = load_metrics(since)
    issues = get_gh_issues_since(since)
    summarize(entries, issues, period)
    return 0


if __name__ == "__main__":
    sys.exit(main())
