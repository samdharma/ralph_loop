"""Crash recovery and daemon signal handling (C1 step 3 — per plan §1.1 C1).

Per docs/IMPROVEMENT_ROADMAP_SPEC.md §6.1, crash recovery and the
SIGINT/SIGTERM signal-handling machinery live at
``core/pipeline/recovery.py``. They were extracted from
``core/engine.py`` during the Phase C-followup extraction (the
documented Phase C deviation in ``docs/PHASE_C_VERIFICATION.md``).

The module owns three concerns:

  1. :func:`recover_from_crash` — read ``.ralph/checkpoint.json``,
     roll the working tree back to the pre-stage SHA, and re-apply
     the correct ``status:<stage>`` label so the pipeline can resume
     from the right stage on the next daemon start.

  2. SIGINT/SIGTERM handling — :class:`RalphInterrupted` (raised when
     a shutdown signal arrives mid-stage), :func:`_handle_signal` (the
     signal handler itself), :func:`_check_interrupt` (called from
     long-running stages to abort on signal), and the module-level
     ``_shutdown_requested`` / ``_in_cleanup`` flags.

  3. PID file management — :func:`acquire_pid_file` and
     :func:`release_pid_file`. The PID file prevents two daemons from
     fighting over the same checkout.

Dependencies on engine.py are intentionally lazy to avoid the
import cycle at module-load time (engine.py imports this module
for re-export of the moved symbols; this module imports engine.py
only inside function bodies, by which time engine.py is fully
loaded).
"""

from __future__ import annotations

import json
import os
import signal
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

# PROJECT_ROOT is the directory containing ``.ralph/`` and the daemon's
# PID file parent. Tests override this via ``monkeypatch.setattr``.
PROJECT_ROOT = Path(os.environ.get("RALPH_PROJECT_DIR", Path.cwd()))
# CHECKPOINT_FILE is canonical in core.pipeline.checkpoint (C1 step 2).
from core.pipeline.checkpoint import CHECKPOINT_FILE  # noqa: E402,F401

PID_FILE = Path("/tmp") / f"ralph_daemon_{PROJECT_ROOT.name}.pid"


# ─────────────────────────────────────────────────────────
# Crash recovery
# ─────────────────────────────────────────────────────────


def _run_git(argv: list[str]) -> "subprocess.CompletedProcess[bytes]":
    """Invoke ``git`` with the given arguments. Tests patch this seam."""
    return subprocess.run(  # noqa: S603
        ["git", *argv],
        capture_output=True,
        check=False,
        cwd=PROJECT_ROOT,
    )


def _run_gh(argv: list[str]) -> "subprocess.CompletedProcess[bytes]":
    """Invoke ``gh`` with the given arguments. Tests patch this seam."""
    return subprocess.run(  # noqa: S603
        ["gh", *argv],
        capture_output=True,
        check=False,
    )


def recover_from_crash() -> Optional[dict]:
    """Check for interrupted work from previous run.

    If a checkpoint exists, roll back to the pre-stage SHA, re-apply
    the correct ``status:<stage>`` label after rollback, and return
    ``{"issue": issue, "resume_stage": stage}`` so the daemon can
    resume. If no checkpoint exists, returns ``None``.
    """
    if not CHECKPOINT_FILE.exists():
        return None

    print("[ralph] Found checkpoint from previous run — recovering...")
    try:
        data = json.loads(CHECKPOINT_FILE.read_text())
        issue_num = data["issue"]
        stage = data.get("stage", "design")
        pre_sha = data.get("pre_stage_sha", "")

        # Roll back to pre-stage state (stay on the current branch).
        if pre_sha:
            print(f"[ralph] Rolling back to commit {pre_sha[:8]} (before {stage})...")
            _run_git(["reset", "--hard", pre_sha])

        # Fetch the issue body so we can resume.
        result = _run_gh(
            ["issue", "view", str(issue_num), "--json", "number,title,body"]
        )
        issue = json.loads(result.stdout)

        # Re-apply the correct status:<stage> label after rollback.
        stage_label_map = {
            "design": "status:design",
            "build": "status:build",
            "verify": "status:verify",
        }
        target_label = stage_label_map.get(stage, "status:design")
        for lbl in [
            "status:design",
            "status:build",
            "status:verify",
            "status:ready",
            "status:review",
            "status:blocked",
        ]:
            if lbl != target_label:
                try:
                    _run_gh(
                        [
                            "issue",
                            "edit",
                            str(issue_num),
                            "--remove-label",
                            lbl,
                        ]
                    )
                except subprocess.CalledProcessError:
                    pass  # Label wasn't present — fine.
        try:
            _run_gh(
                [
                    "issue",
                    "edit",
                    str(issue_num),
                    "--add-label",
                    target_label,
                ]
            )
        except subprocess.CalledProcessError as e:
            print(f"[ralph] Warning: could not apply label {target_label}: {e}")

        print(
            f"[ralph] Resuming #{issue_num} at stage: {stage} (label: {target_label})"
        )

        # Lazy import — log_metrics still lives in core.engine at
        # this point in the cascade (it will move to retry.py later).
        from core.engine import log_metrics as _engine_log_metrics

        _engine_log_metrics("crash_recovery", issue=str(issue_num), stage=stage)

        return {"issue": issue, "resume_stage": stage}

    except Exception as e:
        print(f"[ralph] Recovery error: {e}")
        # Lazy import to avoid cycles.
        from core.pipeline.checkpoint import clear_checkpoint as _engine_clear

        _engine_clear()
        return None


# ─────────────────────────────────────────────────────────
# Daemon signal handling
# ─────────────────────────────────────────────────────────


_shutdown_requested = False
_in_cleanup = False


class RalphInterrupted(BaseException):
    """Raised when the daemon receives SIGINT/SIGTERM during a stage."""

    pass


def _handle_signal(signum, frame):
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    print(f"\n[ralph] Received {sig_name} — shutting down gracefully...")
    _shutdown_requested = True


def _check_interrupt():
    """Abort the current operation if a shutdown signal has been received."""
    if _shutdown_requested and not _in_cleanup:
        raise RalphInterrupted()


# ─────────────────────────────────────────────────────────
# PID file management
# ─────────────────────────────────────────────────────────


def acquire_pid_file() -> bool:
    """Create PID file. Returns False if another daemon is already running."""
    if PID_FILE.exists():
        old_pid = PID_FILE.read_text().strip()
        # Check if the process is still alive.
        try:
            os.kill(int(old_pid), 0)
            print(f"[ralph] Daemon already running (PID {old_pid}). Exiting.")
            return False
        except (OSError, ValueError):
            # Stale PID file — remove it.
            PID_FILE.unlink()

    PID_FILE.write_text(str(os.getpid()))
    return True


def release_pid_file():
    """Remove PID file on exit."""
    if PID_FILE.exists():
        PID_FILE.unlink()


__all__ = [
    "recover_from_crash",
    "RalphInterrupted",
    "_handle_signal",
    "_check_interrupt",
    "_shutdown_requested",
    "_in_cleanup",
    "acquire_pid_file",
    "release_pid_file",
    "PROJECT_ROOT",
    "CHECKPOINT_FILE",
    "PID_FILE",
]  # noqa: D401
