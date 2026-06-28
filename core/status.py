#!/usr/bin/env python3
"""
Ralph v3 — Status Dashboard

Shows project health: daemon PID, active issue, recent metrics.

Usage:
    ralph status
    ralph status --dry-run    # Validate env without listing (CI health check)
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure the project root (parent of ``core/``) is on sys.path so
# ``from core.pipeline.shell import ...`` works whether status.py is
# invoked as ``python core/status.py`` (bin/ralph flow) or as a
# module.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))
PID_FILE = Path("/tmp") / f"ralph_daemon_{PROJECT_ROOT.name}.pid"
METRICS_FILE = PROJECT_ROOT / "logs" / "ralph_metrics.jsonl"
CHECKPOINT_FILE = PROJECT_ROOT / ".ralph" / "checkpoint.json"

# Per spec §10.4 D3 + daemon.dry_run — the 8 status labels that the
# dry-run health-check validates exist on the GitHub repo. Kept in sync
# with ``core.pipeline.daemon._REQUIRED_STATUS_LABELS``.
_REQUIRED_STATUS_LABELS: tuple[str, ...] = (
    "status:ready",
    "status:design",
    "status:build",
    "status:verify",
    "status:review",
    "status:blocked",
    "status:build-retry",
    "status:verify-retry",
)


def get_recent_metrics(limit: int = 10) -> list[dict]:
    """Read the last N entries from ralph_metrics.jsonl."""
    if not METRICS_FILE.exists():
        return []
    lines = METRICS_FILE.read_text(encoding="utf-8").strip().splitlines()
    recent = lines[-limit:]
    return [json.loads(line) for line in recent if line.strip()]


def _dry_run() -> int:
    """Validate gh auth + git remote + 8 status labels. Exits 0 on success.

    Per spec §10.4 D3: intended for CI health checks. Does NOT list
    issues. Returns the same exit codes as
    ``core.pipeline.daemon.dry_run`` so callers (CI scripts) get
    consistent semantics across ``daemon --dry-run`` and
    ``status --dry-run``.
    """
    from core.pipeline.shell import gh, git

    # ── 1. gh auth ──
    try:
        gh_result = gh("auth", "status")
    except Exception as e:  # noqa: BLE001
        print(
            f"[ralph] gh not authenticated: {e}. Run `gh auth login`.", file=sys.stderr
        )
        return 2
    if gh_result.returncode != 0:
        print(
            "[ralph] gh is not authenticated; run `gh auth login`.",
            file=sys.stderr,
        )
        return 2

    # ── 2. git remote ──
    try:
        git_result = git("remote", "-v")
    except Exception as e:  # noqa: BLE001
        print(f"[ralph] git remote check failed: {e}", file=sys.stderr)
        return 3
    if git_result.returncode != 0 or not (git_result.stdout or "").strip():
        print(
            "[ralph] No git remote configured. `git remote add origin <url>`.",
            file=sys.stderr,
        )
        return 3

    # ── 3. status labels ──
    try:
        label_result = gh("label", "list", "--json", "name")
    except Exception as e:  # noqa: BLE001
        print(f"[ralph] gh label list failed: {e}", file=sys.stderr)
        return 4

    try:
        labels_data = json.loads(label_result.stdout or "[]")
    except json.JSONDecodeError as e:
        print(f"[ralph] could not parse gh label list output: {e}", file=sys.stderr)
        return 4

    existing = {label["name"] for label in labels_data if "name" in label}
    missing = [label for label in _REQUIRED_STATUS_LABELS if label not in existing]
    if missing:
        print(
            f"[ralph] Missing required labels: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 4

    print(
        "[ralph] status --dry-run OK. gh auth, git remote, 8 status labels validated."
    )
    return 0


def main() -> int:
    # ── Parse CLI flags ──
    parser = argparse.ArgumentParser(
        prog="ralph status",
        description="Ralph v3 — Status Dashboard",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate gh/git/labels without listing issues (CI health check).",
    )
    args = parser.parse_args()

    if args.dry_run:
        return _dry_run()

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
            pre_sha = data.get("pre_stage_sha", "")[:8]
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
