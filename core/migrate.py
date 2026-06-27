"""`ralph migrate` command — migrate v3 state files to v3.1 layout.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §3.6 and plan §1.1 A-prelude:

- Migrate `.ralph/issue-<N>-*.json|.md` → `.ralph/issues/<N>/...` (per spec §6.2)
- Regenerate stage prompts that match v3 default templates
  (leave customized prompts alone with a warning)
- Archive originals to `.ralph/migration-archive/<timestamp>/`

Idempotent on re-run. Refuses to run while `.ralph/daemon.pid` exists.
Supports `--dry-run` — outputs JSON listing every action WOULD be taken
without modifying the filesystem.

This is the A-008 stub. Full implementation lands in task A-010.
"""

from __future__ import annotations

from typing import Any


def migrate(dry_run: bool = False) -> dict[str, Any]:
    """Migrate v3 state to v3.1 layout. Stub raises NotImplementedError.

    Args:
        dry_run: If True, return a JSON-serializable report of planned actions
            without modifying the filesystem.

    Returns:
        A dict with keys: `actions` (list of planned/executed actions),
        `archive_dir` (path to the archive directory), `errors` (list of
        encountered errors). Suitable for `json.dumps`.
    """
    raise NotImplementedError("ralph migrate not yet implemented (A-008 stub)")