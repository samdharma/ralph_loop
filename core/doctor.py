"""``ralph doctor`` command.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §3.10, §5.2, §10.2 B5.

Diagnostic command for inspecting Ralph's runtime health. Two modes:

  - ``run_doctor(None)`` — scan all known issues for stale state,
    orphans, and environment problems.
  - ``run_doctor(issue_num)`` — focus on a single issue, surfacing its
    trajectory, idempotency log, and any blockers.

Per plan §3 R-11 the exit-code mapping is:

  - 0 = healthy (no issues found)
  - 1 = warnings (non-blocking findings)
  - 2 = errors (blocking findings)

Five diagnostic categories per spec §3.10:

  1. Stuck issues (>1 hour in DESIGN/BUILD/VERIFY) — warning
  2. Long-blocked issues (>7 days) — warning
  3. Repeat failures (3+ same-test failures in 30 days) — warning
  4. Orphan subprocesses (zombie pi/kimi) — error
  5. Environment problems (missing labels, no gh auth, no git remote)
     — error
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))


def _issues_root() -> Path:
    """Return the path under which per-issue directories live."""
    return PROJECT_ROOT / ".ralph" / "issues"


def _list_known_issues() -> list[int]:
    """List all issue numbers with a ``.ralph/issues/<N>/`` directory."""
    root = _issues_root()
    if not root.exists():
        return []
    issues: list[int] = []
    for child in root.iterdir():
        if child.is_dir() and child.name.isdigit():
            issues.append(int(child.name))
    return sorted(issues)


# Per spec §3.10 / plan §3 R-11 the per-category severity contributions:
#   stuck / long-blocked / repeat-failure → 1 (warning)
#   orphan subprocess / environment problem → 2 (error)


def _detect_stuck_issues() -> list[tuple[int, str]]:
    """Detect issues that have been in DESIGN/BUILD/VERIFY > 1 hour.

    Returns a list of ``(issue_num, description)``. Walks each
    issue's trajectory.jsonl (if present) and checks the timestamp of
    the latest event. Issues with no trajectory are skipped (no
    false positives on cold starts).
    """
    import json
    from datetime import datetime, timezone

    findings: list[tuple[int, str]] = []
    cutoff_seconds = 3600  # 1 hour
    now = datetime.now(timezone.utc)
    for n in _list_known_issues():
        traj = _issues_root() / str(n) / "trajectory.jsonl"
        if not traj.exists():
            continue
        try:
            last_event_ts: Optional[datetime] = None
            for raw in traj.read_text(encoding="utf-8").splitlines():
                rec = json.loads(raw)
                ts_str = rec.get("timestamp")
                if not ts_str:
                    continue
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if last_event_ts is None or ts > last_event_ts:
                    last_event_ts = ts
            if last_event_ts is None:
                continue
            age = (now - last_event_ts).total_seconds()
            if age > cutoff_seconds:
                findings.append((n, f"no progress for {age / 60:.0f} min"))
        except Exception:
            continue
    return findings


def _detect_long_blocked() -> list[tuple[int, str]]:
    """Detect issues blocked for >7 days.

    Heuristic: an issue is considered long-blocked if its trajectory
    contains a ``label_transition`` event adding ``status:blocked``
    more than 7 days ago AND no later event exists.
    """
    import json
    from datetime import datetime, timedelta, timezone

    findings: list[tuple[int, str]] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    for n in _list_known_issues():
        traj = _issues_root() / str(n) / "trajectory.jsonl"
        if not traj.exists():
            continue
        try:
            blocked_at: Optional[datetime] = None
            later_event_ts: Optional[datetime] = None
            for raw in traj.read_text(encoding="utf-8").splitlines():
                rec = json.loads(raw)
                ts_str = rec.get("timestamp")
                if not ts_str:
                    continue
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if later_event_ts is None or ts > later_event_ts:
                    later_event_ts = ts
                if rec.get("event_type") == "label_transition" and "status:blocked" in (
                    rec.get("added") or []
                ):
                    if blocked_at is None or ts < blocked_at:
                        blocked_at = ts
            if blocked_at is None:
                continue
            if (
                later_event_ts is None
                or (later_event_ts - blocked_at).total_seconds() < 1
            ):
                # Blocked and no later activity → still blocked.
                age_days = (
                    datetime.now(timezone.utc) - blocked_at
                ).total_seconds() / 86400
                if blocked_at < cutoff:
                    findings.append((n, f"blocked for {age_days:.1f} days"))
        except Exception:
            continue
    return findings


def _detect_repeat_failures() -> list[tuple[str, int]]:
    """Detect tests failing 3+ times in the last 30 days.

    Reads ``.ralph/test-failure-history.jsonl``. Each record is expected
    to have at least ``test`` (test identifier) and ``timestamp`` (ISO
    datetime) fields. Returns a list of ``(test_id, failure_count)`` for
    tests that failed 3 or more times within the last 30 days.
    """
    import json
    from datetime import datetime, timedelta, timezone

    history = PROJECT_ROOT / ".ralph" / "test-failure-history.jsonl"
    if not history.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    counts: dict[str, int] = {}
    for raw in history.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
            test_id = rec.get("test")
            ts_str = rec.get("timestamp")
            if not test_id or not ts_str:
                continue
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                counts[test_id] = counts.get(test_id, 0) + 1
        except Exception:
            continue

    return [(test_id, count) for test_id, count in counts.items() if count >= 3]


def _detect_orphan_subprocesses() -> list[tuple[int, str, str]]:
    """Detect zombie pi/kimi subprocesses.

    Returns a list of ``(pid, name, description)``. Walks ``/proc``
    on POSIX; tests stub this function out.
    """
    if not os.path.isdir("/proc"):
        return []
    findings: list[tuple[int, str, str]] = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/comm", encoding="utf-8") as f:
                name = f.read().strip()
            if name in ("pi", "kimi"):
                findings.append((int(entry), name, "zombie agent process"))
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    return findings


def _detect_environment_problems() -> list[tuple[str, str]]:
    """Detect missing labels, missing gh auth, missing git remote.

    Returns a list of ``(problem, description)``. Each is severity 2
    per plan §3 R-11.
    """
    findings: list[tuple[str, str]] = []
    try:
        import subprocess

        result = subprocess.run(
            ["gh", "label", "list", "--json", "name"],
            capture_output=True,
            check=False,
            timeout=5,
        )
        if result.returncode != 0:
            findings.append(("no_gh_auth", "gh CLI not authenticated"))
        else:
            import json

            labels = json.loads(result.stdout or b"[]")
            label_names = {label.get("name", "") for label in labels}
            required = {
                "status:ready",
                "status:design",
                "status:build",
                "status:verify",
                "status:review",
                "status:blocked",
            }
            missing = required - label_names
            for name in sorted(missing):
                findings.append(("missing_label", name))
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    try:
        import subprocess

        result = subprocess.run(
            ["git", "remote"],
            capture_output=True,
            check=False,
            timeout=5,
        )
        if result.returncode == 0 and not (result.stdout or b"").strip():
            findings.append(("no_git_remote", "no git remote configured"))
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    return findings


def _aggregate_severities() -> int:
    """Run all detectors and return the max severity per plan §3 R-11.

    Per-category contribution (per spec §3.10):
      - stuck issue             → 1 (warning)
      - long-blocked            → 1 (warning)
      - repeat failure          → 1 (warning)
      - orphan subprocess       → 2 (error)
      - environment problem     → 2 (error)

    Final exit code = max(severity) across categories.
    """
    severities: list[int] = []

    if _detect_stuck_issues():
        severities.append(1)
    if _detect_long_blocked():
        severities.append(1)
    if _detect_repeat_failures():
        severities.append(1)
    if _detect_orphan_subprocesses():
        severities.append(2)
    if _detect_environment_problems():
        severities.append(2)

    return max(severities) if severities else 0


def _print_findings(quiet: bool = False) -> None:
    """Pretty-print findings grouped by category.

    When ``quiet`` is True, suppress non-critical findings (severity < 2).
    """
    categories = [
        ("Stuck issues", list(_detect_stuck_issues()), 1),
        ("Long-blocked issues", list(_detect_long_blocked()), 1),
        ("Repeat failures", list(_detect_repeat_failures()), 1),
        ("Orphan subprocesses", list(_detect_orphan_subprocesses()), 2),
        ("Environment problems", list(_detect_environment_problems()), 2),
    ]
    for label, findings, severity in categories:
        if not findings:
            continue
        if quiet and severity < 2:
            continue
        print(f"\n=== {label} (severity {severity}) ===")
        for finding in findings:  # type: ignore[attr-defined]
            print(f"  - {finding}")  # type: ignore[attr-defined]


def run_doctor(issue_num: Optional[int], quiet: bool = False) -> int:
    """Run the doctor diagnostic. Returns the exit code."""
    if issue_num is None:
        issues = _list_known_issues()
        if not issues:
            print(
                f"Ralph doctor: no issues on record. (Looking under {_issues_root()}/)"
            )
            print("Status: HEALTHY (no data)")
            return 0
        if not quiet:
            print(f"Ralph doctor: scanning {len(issues)} issue(s)…")
        sev = _aggregate_severities()
        _print_findings(quiet=quiet)
        if sev == 0:
            print("\nStatus: HEALTHY")
        elif sev == 1:
            print("\nStatus: WARNINGS (exit 1)")
        else:
            print("\nStatus: ERRORS (exit 2)")
        return sev
    else:
        print(f"Ralph doctor: focusing on issue #{issue_num}")
        issue_dir = _issues_root() / str(issue_num)
        if not issue_dir.exists():
            print(f"  #{issue_num}: ⚠️  no per-issue directory at {issue_dir}")
            return 1
        traj = issue_dir / "trajectory.jsonl"
        idemp = issue_dir / "idempotency.jsonl"
        print(f"  trajectory.jsonl: {'present' if traj.exists() else 'absent'}")
        print(f"  idempotency.jsonl: {'present' if idemp.exists() else 'absent'}")
        stuck = [s for s in _detect_stuck_issues() if s[0] == issue_num]
        if stuck:
            for _, desc in stuck:
                print(f"  ⚠️  stuck: {desc}")
            return 1
        return 0


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point for ``python -m core.doctor``."""
    import argparse

    parser = argparse.ArgumentParser(description="Diagnose Ralph's runtime health.")
    parser.add_argument(
        "issue_num",
        type=int,
        nargs="?",
        default=None,
        help="Optional GitHub issue number to focus the diagnostic on.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-critical (severity < 2) diagnostics.",
    )
    args = parser.parse_args(argv)

    return run_doctor(args.issue_num, quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "run_doctor",
    "main",
    "PROJECT_ROOT",
    "_aggregate_severities",
    "_detect_stuck_issues",
    "_detect_long_blocked",
    "_detect_repeat_failures",
    "_detect_orphan_subprocesses",
    "_detect_environment_problems",
]
