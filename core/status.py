#!/usr/bin/env python3
"""
Ralph v3 — Status Dashboard

Shows project health: daemon PID, active issue, recent metrics.

Usage:
    ralph status
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))
PID_FILE = Path("/tmp") / f"ralph_daemon_{PROJECT_ROOT.name}.pid"
METRICS_FILE = PROJECT_ROOT / "logs" / "ralph_metrics.jsonl"
CHECKPOINT_FILE = PROJECT_ROOT / ".ralph" / "checkpoint.json"


def get_recent_metrics(limit: int = 10) -> list[dict]:
    """Read the last N entries from ralph_metrics.jsonl."""
    if not METRICS_FILE.exists():
        return []
    lines = METRICS_FILE.read_text(encoding="utf-8").strip().splitlines()
    recent = lines[-limit:]
    return [json.loads(line) for line in recent if line.strip()]


def main() -> int:
    print("=" * 50)
    print("Ralph v3 — Status")
    print("=" * 50)
    print()

    # ── Daemon status ──
    print("── Daemon ──")
    if PID_FILE.exists():
        pid = PID_FILE.read_text().strip()
        try:
            os.kill(int(pid), 0)
            print(f"  Status:  Running (PID {pid})")
        except (OSError, ValueError):
            print(f"  Status:  Stopped (stale PID file: {pid})")
    else:
        print("  Status:  Stopped")
    print()

    # ── Active issue (from checkpoint) ──
    print("── Active Issue ──")
    if CHECKPOINT_FILE.exists():
        try:
            data = json.loads(CHECKPOINT_FILE.read_text())
            print(f"  Issue:       #{data.get('issue', '?')}")
            print(f"  Started:     {data.get('started_at', '?')}")
            pre_sha = data.get("pre_commit_sha", "")[:8]
            print(f"  Pre-commit:  {pre_sha}")
        except Exception:
            print("  (corrupt checkpoint file)")
    else:
        print("  None (idle)")
    print()

    # ── Recent metrics ──
    print("── Recent Events ──")
    metrics = get_recent_metrics(10)
    if not metrics:
        print("  No metrics yet.")
    else:
        for m in metrics:
            ts = m.get("timestamp", "?")[:19].replace("T", " ")
            event = m.get("event", "?")
            issue = m.get("issue", "")
            stage = m.get("stage", "")
            result = m.get("result", "")
            agent = m.get("agent", "")

            parts = [f"  {ts} | {event}"]
            if issue:
                parts.append(f"#{issue}")
            if stage:
                parts.append(f"stage={stage}")
            if result:
                parts.append(f"result={result}")
            if agent:
                parts.append(f"agent={agent}")
            print(" ".join(parts))

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
