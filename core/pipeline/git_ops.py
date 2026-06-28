"""Git operations for stage commits, push retries, and rollback.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, helpers that commit stage
changes, push with retry, and roll back the working tree live here.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

# Bootstrap sys.path so ``from core.pipeline...`` and the
# engine module can be resolved when this file is loaded via pytest
# from a tests/ subdirectory.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CORE_DIR = _PROJECT_ROOT / "core"
for p in (str(_PROJECT_ROOT), str(_CORE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from core.pipeline.checkpoint import CHECKPOINT_FILE  # noqa: E402
from core.pipeline.recovery import _check_interrupt  # noqa: E402
from core.pipeline.shell import git, run  # noqa: E402


def commit_stage(issue_num: int, stage: str):
    """Commit all changes after a pipeline stage completes and push to origin."""
    msg = f"[ralph] {stage}: #{issue_num}"
    committed = False
    try:
        git("add", "-A")
        git("commit", "-m", msg)
        print(f"[ralph] Committed: {msg}")
        committed = True
    except subprocess.CalledProcessError:
        # No changes to commit (e.g., DESIGN stage may not change files)
        print(f"[ralph] Nothing to commit for {stage}")

    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if _has_unpushed_commits(branch):
        _push_with_retry(branch)
    elif committed:
        print(f"[ralph] No unpushed commits on {branch}")


def _push_with_retry(branch: str, retries: int = 3, backoff: float = 2.0):
    """Push current branch to origin with retries. Raises on final failure."""
    for attempt in range(1, retries + 1):
        try:
            git("push", "-u", "origin", branch)
            print(f"[ralph] Pushed to origin/{branch}")
            return
        except subprocess.CalledProcessError as e:
            if attempt < retries:
                wait = backoff**attempt
                print(
                    f"[ralph] Push failed (attempt {attempt}/{retries}), "
                    f"retrying in {wait:.0f}s..."
                )
                _check_interrupt()
                time.sleep(wait)
            else:
                print(
                    f"[ralph] ERROR: Push to origin/{branch} failed after "
                    f"{retries} attempts: {e}"
                )
                raise


def _rollback_working_tree():
    """Discard all uncommitted changes so stale files don't pollute later stages.

    Uses the checkpoint's pre_stage_sha for a precise rollback to the exact
    state before the BUILD stage started. This avoids two problems with the
    old approach (git clean -fd + git checkout -- .):

    1. git clean -fd destroys entire untracked directories (e.g. a new
       adapters/ subpackage created by the IMPLEMENT agent). On retry the
       agent may not recreate them, causing "missing __init__.py" lint errors.

    2. git checkout -- . resets to the index, not HEAD. If stray staged
       changes exist, the restore is imprecise.
    """
    try:
        # Read pre_stage_sha from checkpoint for precise rollback
        pre_sha = None
        if CHECKPOINT_FILE.exists():
            try:
                data = json.loads(CHECKPOINT_FILE.read_text())
                pre_sha = data.get("pre_stage_sha")
            except Exception:
                pass

        if pre_sha:
            # Reset tracked files + index to pre-build state
            run(["git", "reset", "--hard", pre_sha], check=False, capture=True)
            # Remove untracked files and directories
            run(["git", "clean", "-fd"], check=False, capture=True)
            print(
                f"[ralph] Working tree rolled back to checkpoint " f"SHA {pre_sha[:8]}."
            )
        else:
            # Fallback: restore tracked files to HEAD
            run(["git", "clean", "-fd"], check=False, capture=True)
            run(["git", "checkout", "--", "."], check=False, capture=True)
            print("[ralph] Working tree rolled back after BUILD failure (fallback).")
    except Exception as e:
        print(f"[ralph] WARNING: rollback failed: {e}")


def _has_commits() -> bool:
    """Check if the repo has any commits (vs. fresh repo)."""
    try:
        result = git("rev-list", "--count", "HEAD")
        return int(result.stdout.strip()) >= 2
    except Exception:
        return False


def _has_unpushed_commits(branch: str) -> bool:
    """Return True if the local branch has commits not yet pushed to origin."""
    try:
        result = git("rev-list", "--count", f"origin/{branch}..{branch}")
        return int(result.stdout.strip()) > 0
    except subprocess.CalledProcessError:
        # No upstream or origin branch missing — assume nothing to push.
        return False


__all__ = [
    "commit_stage",
    "_push_with_retry",
    "_rollback_working_tree",
    "_has_commits",
    "_has_unpushed_commits",
]
