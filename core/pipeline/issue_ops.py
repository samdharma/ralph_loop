"""GitHub issue fetchers and dependency checking.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, the ticket fetcher helpers
live here so the daemon loop can delegate ticket discovery without
keeping that logic in ``core/engine.py``.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Bootstrap sys.path so ``from core.pipeline...`` and the
# engine module can be resolved when this file is loaded via pytest
# from a tests/ subdirectory.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CORE_DIR = _PROJECT_ROOT / "core"
for p in (str(_PROJECT_ROOT), str(_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.pipeline.shell import gh  # noqa: E402
from core.project_sync import sync_status  # noqa: E402


def fetch_ready_ticket() -> Optional[dict]:
    """
    Fetch the open status:ready issue with the smallest number.
    Checks dependencies — skips issues with unmet deps.
    Returns issue dict {number, title, body} or None.
    """
    # Get ready issues sorted by number
    result = gh(
        "issue",
        "list",
        "--label",
        "status:ready",
        "--state",
        "open",
        "--json",
        "number,title,body",
        "--limit",
        "20",
    )

    issues = json.loads(result.stdout)
    if not issues:
        return None

    # Sort by number for determinism
    issues.sort(key=lambda i: i["number"])

    for issue in issues:
        if _dependencies_met(issue):
            return issue
        else:
            print(f"[ralph] Skipping #{issue['number']} — unmet dependencies")

    return None


# Retry labels let humans re-queue a blocked issue without re-running all stages.
# Ordered smallest scope first — verify-only is faster than build+verify.
RETRY_LABEL_MAP = {
    "status:verify-retry": "verify",
    "status:build-retry": "build",
}


def fetch_retry_issue() -> Optional[tuple[dict, str]]:
    """
    Fetch the open retry-labeled issue with the smallest number.

    Checks status:verify-retry first (fastest), then status:build-retry.
    Returns (issue_dict, resume_stage) or None.
    """
    for label, resume_stage in RETRY_LABEL_MAP.items():
        try:
            result = gh(
                "issue",
                "list",
                "--label",
                label,
                "--state",
                "open",
                "--json",
                "number,title,body",
                "--limit",
                "10",
            )
            issues = json.loads(result.stdout)
            if not issues:
                continue
            issues.sort(key=lambda i: i["number"])
            for issue in issues:
                if _dependencies_met(issue):
                    return issue, resume_stage
                else:
                    print(f"[ralph] Skipping #{issue['number']} — unmet dependencies")
        except subprocess.CalledProcessError:
            continue
    return None


def sync_ready_board():
    """
    Ensure all open status:ready issues are in the Ready board column.
    This fixes the common case where an issue was added to the project in the
    default Backlog column even though it already has the status:ready label.
    """
    try:
        result = gh(
            "issue",
            "list",
            "--label",
            "status:ready",
            "--state",
            "open",
            "--json",
            "number",
            "--limit",
            "50",
        )
        issues = json.loads(result.stdout)
        for issue in issues:
            sync_status(issue["number"], "status:ready")
    except Exception as e:
        # Fail-soft: board sync must never break the pipeline.
        print(f"[ralph] WARNING: could not sync ready tickets: {e}")


def fetch_issue_by_number(issue_num: int) -> Optional[dict]:
    """Fetch a specific GitHub issue by number.

    Returns the issue dict {number, title, body, state} or None if:
    - The issue doesn't exist
    - The issue is closed
    - Dependencies are unmet
    """
    try:
        result = gh(
            "issue",
            "view",
            str(issue_num),
            "--json",
            "number,title,body,state",
        )
        issue = json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None

    if issue.get("state") != "OPEN":
        return None

    if not _dependencies_met(issue):
        return None

    return issue


def _dependencies_met(issue: dict) -> bool:
    """Check if all 'Depends on: #N' references in the body are closed."""
    body = issue.get("body") or ""
    deps = _parse_depends_on(body)
    for dep_num in deps:
        try:
            result = gh(
                "issue", "view", str(dep_num), "--json", "state", "--jq", ".state"
            )
            state = result.stdout.strip()
            if state != "CLOSED":
                print(
                    f"[ralph] #{issue['number']} depends on #{dep_num} (still {state})"
                )
                return False
        except subprocess.CalledProcessError:
            print(f"[ralph] #{issue['number']} depends on #{dep_num} (not found)")
            return False
    return True


def _parse_depends_on(body: str) -> list[int]:
    """Extract issue numbers from 'Depends on: #42' patterns in the body."""
    deps = []
    for line in body.splitlines():
        match = re.search(r"Depends\s+on:\s*#(\d+)", line, re.IGNORECASE)
        if match:
            deps.append(int(match.group(1)))
    return deps


__all__ = [
    "fetch_ready_ticket",
    "fetch_retry_issue",
    "RETRY_LABEL_MAP",
    "sync_ready_board",
    "fetch_issue_by_number",
    "_dependencies_met",
    "_parse_depends_on",
]
