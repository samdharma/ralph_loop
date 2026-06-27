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

The skeleton (B5.1, this module) provides the framework. The 5
diagnostic categories (B5.2 — stuck issues, long-blocked, repeat
failures, orphan subprocesses, environment checks) are added in B-031.
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


def run_doctor(issue_num: Optional[int]) -> int:
    """Run the doctor diagnostic. Returns the exit code.

    Per spec §10.2 B5 / plan §3 R-11 the exit code is:

      - 0 if nothing is wrong (no findings),
      - 1 if there are non-blocking warnings,
      - 2 if there are blocking errors.

    The skeleton (B5.1) does not yet implement the 5 diagnostic
    categories — see B-031 for the full implementation.
    """
    if issue_num is None:
        issues = _list_known_issues()
        if not issues:
            print(
                "Ralph doctor: no issues on record. "
                "(Looking under "
                f"{_issues_root()}/)"
            )
            print("Status: HEALTHY (no data)")
            return 0
        print(f"Ralph doctor: scanning {len(issues)} issue(s)…")
        return _scan_all_issues(issues)
    else:
        print(f"Ralph doctor: focusing on issue #{issue_num}")
        return _scan_single_issue(issue_num)


def _scan_all_issues(issues: list[int]) -> int:
    """Scan all known issues. Skeleton: just lists them.

    The full implementation in B-031 invokes each of the 5 diagnostic
    category detectors and aggregates their severities. For now we
    only check that the issue directory exists.
    """
    severities: list[int] = []
    for n in issues:
        sev = _scan_single_issue(n)
        severities.append(sev)
    if not severities:
        return 0
    return max(severities)


def _scan_single_issue(issue_num: int) -> int:
    """Scan a single issue. Skeleton: directory existence only.

    Returns the severity (0, 1, or 2) for this issue. Currently
    always returns 0 (no findings) unless the issue directory is
    missing.
    """
    issue_dir = _issues_root() / str(issue_num)
    if not issue_dir.exists():
        print(f"  #{issue_num}: ⚠️  no per-issue directory at {issue_dir}")
        return 1
    print(f"  #{issue_num}: ✓ healthy (B5.1 skeleton; no detectors yet)")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point for ``python -m core.doctor``.

    Usage:
        python core/doctor.py            # scan all
        python core/doctor.py 42         # focus on #42
        bin/ralph doctor [N]
    """
    import argparse

    parser = argparse.ArgumentParser(description="Diagnose Ralph's runtime health.")
    parser.add_argument(
        "issue_num",
        type=int,
        nargs="?",
        default=None,
        help="Optional GitHub issue number to focus the diagnostic on.",
    )
    args = parser.parse_args(argv)

    return run_doctor(args.issue_num)


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["run_doctor", "main", "PROJECT_ROOT"]
