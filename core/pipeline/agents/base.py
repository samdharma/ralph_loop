"""Worktree setup/teardown for sub-agent isolation.

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §10.2 B3 and plan §3 R-5 mitigation.

``create_worktree`` and ``remove_worktree`` wrap ``git worktree add``
and ``git worktree remove`` so the engine can run TEST and VERIFY
sub-agents in isolated working copies. The plan §3 R-5 mitigation
calls out that ``git worktree`` is the closest thing to a built-in
mechanism for agent isolation; without it, agents would share the
parent repo's working tree and a stray write could corrupt the
check-out.

Pre-flight check (per plan §3 R-5): the first invocation runs a
``git worktree add /tmp/ralph-wt-test HEAD`` to confirm the host
supports git worktrees. If that fails, ``create_worktree`` raises
``RuntimeError`` with a clear remediation message — there is no
silent fallback that would surprise the user later.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))


def _run_git(argv: list[str]) -> "subprocess.CompletedProcess[bytes]":
    """Invoke git with the given arguments. Tests patch this seam."""
    return subprocess.run(  # noqa: S603
        ["git", *argv],
        capture_output=True,
        check=False,
        cwd=PROJECT_ROOT,
    )


def _worktree_path(issue_num: int) -> Path:
    """Return the on-disk path for issue ``issue_num``'s worktree."""
    return PROJECT_ROOT / ".ralph" / "worktrees" / str(issue_num)


def _preflight_check() -> None:
    """Run a one-shot ``git worktree add`` to verify support.

    Per plan §3 R-5: failure here aborts the worktree-based pipeline
    rather than silently falling back, so the operator sees a clear
    message and can act (upgrade git, enable worktree config, etc.).
    """
    probe_path = PROJECT_ROOT / ".ralph" / ".worktree-probe"
    if probe_path.exists():
        # Clean up any prior probe.
        _run_git(["worktree", "remove", "--force", str(probe_path)])
        if probe_path.exists():
            import shutil

            shutil.rmtree(probe_path, ignore_errors=True)

    probe_path.parent.mkdir(parents=True, exist_ok=True)
    result = _run_git(["worktree", "add", "--detach", str(probe_path), "HEAD"])
    if result.returncode != 0:
        raise RuntimeError(
            "git worktree not available on this host "
            "(see docs/development_workflow.md for workarounds). "
            f"stderr: {result.stderr.decode('utf-8', errors='replace')}"
        )
    # Clean up the probe worktree.
    _run_git(["worktree", "remove", "--force", str(probe_path)])


def create_worktree(issue_num: int) -> Path:
    """Create a worktree for issue ``issue_num`` and return its path.

    On first call (per-process), runs the pre-flight check. Subsequent
    calls skip the check (it's a per-process one-shot).
    """
    if not getattr(create_worktree, "_preflight_done", False):
        _preflight_check()
        create_worktree._preflight_done = True  # type: ignore[attr-defined]

    wt_path = _worktree_path(issue_num)
    wt_path.parent.mkdir(parents=True, exist_ok=True)

    result = _run_git(
        [
            "worktree",
            "add",
            "--detach",
            str(wt_path),
            "HEAD",
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git worktree add failed for issue #{issue_num} at {wt_path}: "
            f"{result.stderr.decode('utf-8', errors='replace')}"
        )
    # In tests the mocked _run_git doesn't actually create the
    # directory; ensure the path exists on disk so callers can cwd
    # into it. Real git worktree add creates it; this is a no-op in
    # that path.
    wt_path.mkdir(parents=True, exist_ok=True)
    return wt_path


def remove_worktree(path: Path) -> None:
    """Remove a worktree at ``path``. No-op if the worktree doesn't exist."""
    if not path.exists():
        return
    result = _run_git(["worktree", "remove", "--force", str(path)])
    if result.returncode != 0:
        # Best-effort: log a warning but don't raise. The worktree may
        # already be gone (e.g., from a prior failed cleanup).
        import sys

        print(
            f"[ralph] WARNING: git worktree remove failed for {path}: "
            f"{result.stderr.decode('utf-8', errors='replace')}",
            file=sys.stderr,
        )


__all__ = ["create_worktree", "remove_worktree", "PROJECT_ROOT"]
