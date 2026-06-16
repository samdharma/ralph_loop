#!/usr/bin/env python3
"""
Ralph v3 — Loop Observability Dashboard (non-intrusive)

Reads local Ralph state and polls GitHub via `gh` to show what the daemon is
doing right now.  It does NOT modify issues, labels, or the build loop.

Usage:
    ./scripts/ralph-watch.py              # one-time snapshot
    ./scripts/ralph-watch.py --watch      # refresh every 5 seconds
    ./scripts/ralph-watch.py --interval 2 # refresh every 2 seconds
    ./scripts/ralph-watch.py --metrics 20 # show last 20 metrics events

Environment:
    RALPH_PROJECT_DIR  Project root (default: current working directory)
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd())).resolve()
PID_FILE = Path("/tmp") / f"ralph_daemon_{PROJECT_ROOT.name}.pid"
CHECKPOINT_FILE = PROJECT_ROOT / ".ralph" / "checkpoint.json"
METRICS_FILE = PROJECT_ROOT / "logs" / "ralph_metrics.jsonl"

STATUS_LABELS = [
    "status:ready",
    "status:design",
    "status:build",
    "status:verify",
    "status:review",
    "status:blocked",
]


def _fmt_ts(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return iso


def _shorten(sha: str) -> str:
    return (sha or "")[:8]


def daemon_status() -> str:
    if not PID_FILE.exists():
        return "Stopped (no PID file)"
    pid_text = PID_FILE.read_text().strip()
    try:
        pid = int(pid_text)
        os.kill(pid, 0)
        return f"Running (PID {pid})"
    except (OSError, ValueError):
        return f"Stopped (stale PID file: {pid_text})"


def active_issue() -> Optional[dict]:
    if not CHECKPOINT_FILE.exists():
        return None
    try:
        return json.loads(CHECKPOINT_FILE.read_text())
    except Exception:
        return {"error": "corrupt checkpoint"}


def recent_metrics(limit: int = 10) -> list[dict]:
    if not METRICS_FILE.exists():
        return []
    try:
        lines = METRICS_FILE.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(line) for line in lines[-limit:] if line.strip()]
    except Exception:
        return []


def _gh_json(args: list[str], timeout: int = 15) -> list[dict]:
    """Run `gh ... --json ...` and return parsed JSON list."""
    if shutil.which("gh") is None:
        return []
    try:
        result = subprocess.run(
            ["gh", *args, "--json", "number,title,labels,state,updatedAt"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=timeout,
        )
        if result.returncode != 0:
            return []
        return json.loads(result.stdout)
    except Exception:
        return []


def gh_label_counts() -> dict[str, int]:
    """Count open issues per Ralph status label."""
    counts: dict[str, int] = {}
    for label in STATUS_LABELS:
        issues = _gh_json(
            ["issue", "list", "--state", "open", "--label", label, "--limit", "100"]
        )
        counts[label] = len(issues)
    return counts


def gh_active_issue_details(issue_num: int) -> Optional[dict]:
    if shutil.which("gh") is None:
        return None
    try:
        result = subprocess.run(
            ["gh", "issue", "view", str(issue_num), "--json", "number,title,labels,state,comments"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=15,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except Exception:
        return None


def _render_snapshot(metrics_limit: int = 10) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("Ralph v3 — Loop Observability")
    lines.append(f"Project: {PROJECT_ROOT}")
    lines.append("=" * 60)
    lines.append("")

    # Daemon status
    lines.append("── Daemon ──")
    lines.append(f"  {daemon_status()}")
    lines.append("")

    # Active issue from local checkpoint
    lines.append("── Active Issue (local checkpoint) ──")
    cp = active_issue()
    if cp is None:
        lines.append("  None (idle)")
    elif "error" in cp:
        lines.append(f"  {cp['error']}")
    else:
        started = _fmt_ts(cp.get("started_at", ""))
        lines.append(f"  Issue:       #{cp.get('issue', '?')}")
        lines.append(f"  Stage:       {cp.get('stage', '?')}")
        lines.append(f"  Started:     {started}")
        lines.append(f"  Pre-commit:  {_shorten(cp.get('pre_stage_sha', ''))}")

        # Enrich with live GitHub data if available
        try:
            issue_num = int(cp.get("issue", ""))
            details = gh_active_issue_details(issue_num)
            if details:
                labels = [l["name"] for l in details.get("labels", [])]
                lines.append(f"  GH labels:   {', '.join(labels) or '(none)'}")
                lines.append(f"  GH state:    {details.get('state', '?')}")
        except Exception:
            pass
    lines.append("")

    # GitHub label counts
    lines.append("── GitHub Issue Pipeline ──")
    counts = gh_label_counts()
    for label in STATUS_LABELS:
        name = label.replace("status:", "")
        lines.append(f"  {name:10s}: {counts.get(label, 0):3d}")
    lines.append("")

    # Recent metrics
    lines.append(f"── Recent Metrics (last {metrics_limit}) ──")
    metrics = recent_metrics(metrics_limit)
    if not metrics:
        lines.append("  No metrics yet.")
    else:
        for m in metrics:
            ts = _fmt_ts(m.get("timestamp", ""))[:19]
            event = m.get("event", "?")
            extra = []
            for key in ("issue", "stage", "subagent", "result", "agent"):
                if key in m:
                    extra.append(f"{key}={m[key]}")
            extra_str = " ".join(extra)
            lines.append(f"  {ts}  {event:20s} {extra_str}")
    lines.append("")

    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Non-intrusive Ralph loop observability dashboard."
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Continuously refresh the dashboard.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Refresh interval in seconds (default: 5).",
    )
    parser.add_argument(
        "--metrics",
        type=int,
        default=10,
        help="Number of recent metrics events to show (default: 10).",
    )
    args = parser.parse_args(argv)

    # Set up a graceful exit for --watch mode
    stop = {"flag": False}

    def _on_signal(signum, _frame):
        stop["flag"] = True

    if args.watch:
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, _on_signal)

    while True:
        output = _render_snapshot(metrics_limit=args.metrics)
        if args.watch:
            # Clear screen in a terminal-friendly way
            sys.stdout.write("\033[2J\033[H")
        sys.stdout.write(output)
        sys.stdout.flush()

        if not args.watch:
            break

        # Sleep in small chunks so Ctrl-C is responsive
        for _ in range(args.interval):
            if stop["flag"]:
                sys.stdout.write("\nStopping ralph-watch.\n")
                return 0
            time.sleep(1)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
