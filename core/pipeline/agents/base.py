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

Read-only ``src/`` enforcement (per plan §3 R-5): after creating a
worktree, ``create_worktree`` invokes :func:`_enforce_readonly_src`
which:

  - on Linux: runs ``mount --bind`` + ``mount -o remount,ro,bind``.
  - on macOS: runs ``chmod -R 0500 src/`` and logs a WARNING that
    read isolation is policy-only on this platform.

``remove_worktree`` reverses the read-only state via
:func:`_cleanup_readonly_src` before invoking ``git worktree remove``.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))
_LOG = logging.getLogger(__name__)


def _run_git(argv: list[str]) -> "subprocess.CompletedProcess[bytes]":
    """Invoke git with the given arguments. Tests patch this seam."""
    return subprocess.run(  # noqa: S603
        ["git", *argv],
        capture_output=True,
        check=False,
        cwd=PROJECT_ROOT,
    )


def _run_mount(argv: list[str]) -> "subprocess.CompletedProcess[bytes]":
    """Invoke ``mount`` with the given arguments. Tests patch this seam."""
    return subprocess.run(  # noqa: S603
        ["mount", *argv],
        capture_output=True,
        check=False,
    )


def _run_umount(argv: list[str]) -> "subprocess.CompletedProcess[bytes]":
    """Invoke ``umount`` with the given arguments. Tests patch this seam."""
    return subprocess.run(  # noqa: S603
        ["umount", *argv],
        capture_output=True,
        check=False,
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


def _enforce_readonly_src(wt_path: Path) -> None:
    """Make ``src/`` inside the worktree read-only.

    Per spec §10.2 B3 + plan §3 R-5:

      - Linux: ``mount --bind <src> <wt>/src && mount -o
        remount,ro,bind <wt>/src`` (true mechanism isolation —
        writes fail at the kernel level).
      - macOS: ``chmod -R 0500 <wt>/src`` (writes enforced; reads
        remain policy-only because macOS lacks ``mount -o ro,bind``).
        A WARNING is logged so the operator knows.

    On Linux mount failure, fall back to ``chmod -R 0500 src/`` and
    log a WARNING — the worktree still gets policy-only isolation.
    """
    wt_src = wt_path / "src"
    if not wt_src.exists():
        return

    host_platform = sys.platform
    if host_platform.startswith("linux"):
        result = _run_mount(["--bind", str(PROJECT_ROOT / "src"), str(wt_src)])
        if result.returncode == 0:
            result = _run_mount(["-o", "remount,ro,bind", str(wt_src)])
            if result.returncode != 0:
                _LOG.warning(
                    "mount remount,ro,bind failed for %s; falling back to chmod 0500",
                    wt_src,
                )
                _chmod_readonly(wt_src)
        else:
            _LOG.warning(
                "mount --bind failed for %s; falling back to chmod 0500", wt_src
            )
            _chmod_readonly(wt_src)
    else:
        # macOS / other: policy-only read isolation via chmod.
        _LOG.warning(
            "Read isolation is policy-only on %s; relying on chmod 0500",
            host_platform,
        )
        _chmod_readonly(wt_src)


def _chmod_readonly(directory: Path) -> None:
    """Recursively chmod a directory to 0o500 (read+execute, no write)."""
    if not directory.exists():
        return
    for root, dirs, files in os.walk(directory):
        os.chmod(root, 0o500)
        for fname in files:
            os.chmod(Path(root) / fname, 0o500)


def _cleanup_readonly_src(wt_path: Path) -> None:
    """Reverse the read-only state applied by :func:`_enforce_readonly_src`.

    On Linux the mount is unmounted. On macOS the directory is simply
    removed (no umount needed because no mount was performed).
    """
    wt_src = wt_path / "src"
    if not wt_src.exists():
        return

    host_platform = sys.platform
    if host_platform.startswith("linux"):
        _run_umount([str(wt_src)])
    # On macOS no umount is needed.


def create_worktree(issue_num: int) -> Path:
    """Create a worktree for issue ``issue_num`` and return its path.

    On first call (per-process), runs the pre-flight check. Subsequent
    calls skip the check (it's a per-process one-shot). After the
    worktree is created, :func:`_enforce_readonly_src` is invoked so
    the sub-agent cannot write to ``src/``.
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
    _enforce_readonly_src(wt_path)
    return wt_path


def remove_worktree(path: Path) -> None:
    """Remove a worktree at ``path``. No-op if the worktree doesn't exist."""
    if not path.exists():
        return
    _cleanup_readonly_src(path)
    result = _run_git(["worktree", "remove", "--force", str(path)])
    if result.returncode != 0:
        # Best-effort: log a warning but don't raise. The worktree may
        # already be gone (e.g., from a prior failed cleanup).
        print(
            f"[ralph] WARNING: git worktree remove failed for {path}: "
            f"{result.stderr.decode('utf-8', errors='replace')}",
            file=sys.stderr,
        )


__all__ = [
    "AgentBase",
    "create_worktree",
    "remove_worktree",
    "PROJECT_ROOT",
    "_enforce_readonly_src",
    "_cleanup_readonly_src",
]


# ─────────────────────────────────────────────────────────
# C1.5a — AgentBase abstract class (per spec §6.1)
# ─────────────────────────────────────────────────────────


class AgentBase(ABC):
    """Abstract base for agent wrappers.

    Concrete subclasses (``PiAgent``, ``KimiAgent``) implement
    ``invoke()`` to delegate to the engine's agent-invocation
    machinery. Per spec §6.1, this is the type contract for the
    agents/ subpackage; concrete implementations live in pi.py and
    kimi.py respectively.
    """

    name: str = ""  # subclass sets; e.g. "pi" or "kimi"

    @abstractmethod
    def invoke(self, *args, **kwargs):
        """Invoke the agent. Subclasses implement this."""
        raise NotImplementedError
