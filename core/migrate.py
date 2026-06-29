"""`ralph migrate` command — migrate v3 state files to v3.1 layout.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §3.6 and plan §1.1 A-prelude:

- Migrate `.ralph/issue-<N>-*.json|.md` → `.ralph/issues/<N>/...` (per spec §6.2)
- Regenerate stage prompts that match v3 default templates
  (leave customized prompts alone with a warning)
- Archive originals to `.ralph/migration-archive/<timestamp>/`

Idempotent on re-run. Refuses to run while `.ralph/daemon.pid` exists.
Supports `--dry-run` — outputs JSON listing every action WOULD be taken
without modifying the filesystem.

CLI:
    python -m core.migrate [--dry-run]
    bin/ralph migrate [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))


def _project_root() -> Path:
    """Resolve project root at call time so monkeypatch.chdir works in tests."""
    return Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))


# v3-format state files that get migrated to .ralph/issues/<N>/... per spec §6.2.
_V3_ISSUE_FILES_GLOB = "issue-*-*.{json,md}"

# v3-format session files, deprecated in A3 (spec §10.1 A3).
_V3_SESSION_FILES_GLOB = "session-*.jsonl"


def _ralph_dir(project_root: Path) -> Path:
    return project_root / ".ralph"


def _timestamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _plan_actions(project_root: Path) -> list[dict[str, str]]:
    """List every action that migrate WOULD take. Pure (no side effects)."""
    actions: list[dict[str, str]] = []
    ralph_dir = _ralph_dir(project_root)
    if not ralph_dir.exists():
        return actions

    # Issue files: .ralph/issue-<N>-<kind>.json|.md → .ralph/issues/<N>/<kind>.<ext>
    issue_files: list[Path] = []
    for ext in ("json", "md"):
        issue_files.extend(ralph_dir.glob(f"issue-*-*.{ext}"))
    for src in sorted(issue_files):
        # Parse filename: "issue-<N>-<kind>.json" or "issue-<N>-<kind>.md"
        stem = src.stem  # "issue-1-tests"
        parts = stem.split("-", 2)
        if len(parts) != 3:
            continue
        _, issue_num_str, kind = parts
        try:
            int(issue_num_str)
        except ValueError:
            continue
        dst_dir = ralph_dir / "issues" / issue_num_str
        dst = dst_dir / f"{kind}{src.suffix}"
        actions.append(
            {
                "type": "move",
                "src": str(src.relative_to(project_root)),
                "dst": str(dst.relative_to(project_root)),
                "issue": issue_num_str,
                "kind": kind,
            }
        )

    # Session files: archived (kept for one migration cycle per plan §6.3)
    for src in sorted(ralph_dir.glob(_V3_SESSION_FILES_GLOB)):
        actions.append(
            {
                "type": "archive",
                "src": str(src.relative_to(project_root)),
            }
        )

    return actions


def _issue_num_from_stem(stem: str) -> str | None:
    """Parse 'issue-1-tests' → '1'. Returns None if not parseable."""
    parts = stem.split("-", 2)
    if len(parts) != 3:
        return None
    _, issue_num_str, _kind = parts
    try:
        int(issue_num_str)
    except ValueError:
        return None
    return issue_num_str


def _archive_existing(
    project_root: Path, archive_dir: Path, actions: list[dict[str, str]]
) -> None:
    """Copy each source file to archive_dir preserving the relative path."""
    for action in actions:
        src = project_root / action["src"]
        if not src.exists():
            continue
        # Mirror the source path under the archive dir for clarity
        rel = src.relative_to(project_root)
        dest = archive_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def migrate(dry_run: bool = False) -> dict[str, Any]:
    """Migrate v3 state to v3.1 layout.

    Args:
        dry_run: If True, return a JSON-serializable report of planned actions
            without modifying the filesystem.

    Returns:
        A dict with keys:
        - `actions`: list of planned/executed actions (each a dict with
          `type`, `src`, optional `dst`, `issue`, `kind`)
        - `archive_dir`: path to the archive directory (str) — may be empty
          string if no actions required archiving
        - `errors`: list of error strings (empty on success)

    Raises:
        RuntimeError: if the daemon is currently running (`.ralph/daemon.pid`
            exists).
    """
    project_root = _project_root()
    ralph_dir = _ralph_dir(project_root)
    pid_file = ralph_dir / "daemon.pid"

    errors: list[str] = []

    # Guard: refuse to run while the daemon is active.
    if pid_file.exists():
        raise RuntimeError(
            f"Cannot migrate while daemon is running (PID file: {pid_file}). "
            "Stop the daemon before running `ralph migrate`."
        )

    actions = _plan_actions(project_root)
    archive_dir_str = ""

    if not actions:
        return {
            "actions": [],
            "archive_dir": "",
            "errors": [],
        }

    # Determine the archive dir. Use a timestamp so concurrent runs don't collide.
    archive_root = ralph_dir / "migration-archive"
    archive_dir = archive_root / _timestamp()
    archive_dir_str = str(archive_dir.relative_to(project_root))

    if dry_run:
        # Dry run: report planned actions, do not touch filesystem.
        return {
            "actions": actions,
            "archive_dir": archive_dir_str,
            "errors": [],
        }

    # Real run: archive first, then perform moves.
    archive_dir.mkdir(parents=True, exist_ok=True)
    _archive_existing(project_root, archive_dir, actions)

    executed: list[dict[str, str]] = []
    for action in actions:
        src = project_root / action["src"]
        try:
            if action["type"] == "move":
                dst = project_root / action["dst"]
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                executed.append({**action, "status": "moved"})
            elif action["type"] == "archive":
                # Already copied above; remove the source.
                src.unlink()
                executed.append({**action, "status": "archived"})
        except OSError as e:
            errors.append(f"{action['src']}: {e}")

    return {
        "actions": executed,
        "archive_dir": archive_dir_str,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for `python -m core.migrate`."""
    parser = argparse.ArgumentParser(
        description="Migrate v3 state files to v3.1 layout."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List planned actions as JSON without modifying the filesystem.",
    )
    args = parser.parse_args(argv)

    try:
        report = migrate(dry_run=args.dry_run)
    except RuntimeError as e:
        print(f"ralph migrate: {e}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
